"""模型仓库与预测服务 API。

预测相关接口同时支持网页登录（JWT）和外部终端（X-API-Key）访问：
    POST /api/v1/models/{id}/predict        JSON 预测（可选返回局部解释）
    POST /api/v1/models/{id}/predict-file   上传 CSV/Excel 批量预测，返回带预测列的 CSV
    GET  /api/v1/models/{id}/schema         查询模型需要的输入字段
"""
from __future__ import annotations

import io
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from .. import db
from ..concurrency import predict_gate
from ..config import settings
from ..core.adapters import get_adapter
from ..core.pipeline import ExternalPipeline
from ..core.preprocess import read_table
from ..deps import get_principal, web_user
from ..schemas import ModelPatchIn, PredictDatasetIn, PredictIn
from ..services.datasets import load_dataframe
from ..services.model_store import can_access, can_modify, model_cache, save_pipeline, visible_filter

router = APIRouter(tags=["模型与预测服务"])

LIST_FIELDS = ("id, owner_id, job_id, dataset_id, name, adapter, family, task, target, metrics_json, status, "
               "visibility, is_best, description, created_at")


def _get_model(model_id: int, principal: dict[str, Any]) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM models WHERE id = ?", [model_id])
    if not row or row["status"] == "archived" and row["owner_id"] != principal["id"] and principal["role"] != "admin":
        raise HTTPException(404, "模型不存在")
    if not can_access(principal, row, via_api_key=bool(principal.get("via_api_key"))):
        raise HTTPException(404, "模型不存在或无权访问（API Key 只能调用已发布的模型）")
    return row


# ======================= 模型仓库 =======================
@router.get("/models", summary="模型列表")
def list_models(principal: dict[str, Any] = Depends(get_principal), task: str | None = None,
                status: str | None = None, mine: bool = False) -> list[dict[str, Any]]:
    cond, params = visible_filter(principal, "m")
    where = [cond]
    if principal.get("via_api_key"):
        where.append("(m.status = 'published' OR m.owner_id = ?)")
        params.append(principal["id"])
    if task:
        where.append("m.task = ?")
        params.append(task)
    if status:
        where.append("m.status = ?")
        params.append(status)
    else:
        where.append("m.status != 'archived'")
    if mine:
        where.append("m.owner_id = ?")
        params.append(principal["id"])
    fields = ", ".join(f"m.{f.strip()}" for f in LIST_FIELDS.split(","))
    return db.query(
        f"SELECT {fields}, u.username AS owner_name, d.name AS dataset_name, "
        f"(SELECT COUNT(*) FROM prediction_logs p WHERE p.model_id = m.id) AS calls "
        f"FROM models m JOIN users u ON u.id = m.owner_id LEFT JOIN datasets d ON d.id = m.dataset_id "
        f"WHERE {' AND '.join(where)} ORDER BY m.id DESC",
        params,
    )


@router.get("/models/{model_id}", summary="模型详情：指标、可视化数据、特征重要性、归一化报告")
def model_detail(model_id: int, principal: dict[str, Any] = Depends(get_principal)) -> dict[str, Any]:
    row = _get_model(model_id, principal)
    row.pop("path", None)
    owner = db.query_one("SELECT username FROM users WHERE id = ?", [row["owner_id"]])
    row["owner_name"] = owner["username"] if owner else None
    try:
        cls = get_adapter(row["adapter"])
        row["adapter_name"] = cls.name
        row["adapter_description"] = cls.description
    except KeyError:
        row["adapter_name"] = row["adapter"]
    if row.get("job_id"):
        job = db.query_one("SELECT result_json FROM jobs WHERE id = ?", [row["job_id"]])
        if job and job.get("result"):
            row["leaderboard"] = job["result"].get("leaderboard")
    stats = db.query_one(
        "SELECT COUNT(*) AS calls, SUM(n_rows) AS rows, AVG(latency_ms) AS avg_latency FROM prediction_logs "
        "WHERE model_id = ? AND status_code = 200",
        [model_id],
    )
    row["usage"] = stats
    return row


@router.get("/models/{model_id}/schema", summary="模型输入字段说明（外部终端调用前查询）")
def model_schema(model_id: int, principal: dict[str, Any] = Depends(get_principal)) -> dict[str, Any]:
    row = _get_model(model_id, principal)
    example = {c["name"]: c.get("default") for c in row.get("input_schema") or []}
    return {"model_id": model_id, "name": row["name"], "task": row["task"], "target": row["target"],
            "inputs": row.get("input_schema"), "example_request": {"records": [example]}}


@router.patch("/models/{model_id}", summary="修改模型：重命名 / 发布 / 下线 / 共享范围")
def patch_model(model_id: int, body: ModelPatchIn, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    row = _get_model(model_id, user)
    if not can_modify(user, row):
        raise HTTPException(403, "只有模型创建者可以修改")
    db.update("models", model_id, body.model_dump(exclude_none=True))
    return {"message": "已更新"}


@router.delete("/models/{model_id}", summary="删除模型")
def delete_model(model_id: int, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    row = _get_model(model_id, user)
    if not can_modify(user, row):
        raise HTTPException(403, "只有模型创建者可以删除")
    db.execute("DELETE FROM models WHERE id = ?", [model_id])
    model_cache.evict(model_id)
    Path(row["path"]).unlink(missing_ok=True)
    return {"message": "已删除"}


# ======================= 外部模型接入 =======================
@router.post("/models/import", summary="接入外部训练好的模型（ONNX / joblib）")
async def import_model(
    file: UploadFile = File(..., description=".onnx 或 .joblib/.pkl 模型文件"),
    name: str = Form(...),
    task: str = Form(..., description="regression 或 classification"),
    target: str = Form("预测值"),
    features: str = Form(..., description="输入特征名，按模型输入顺序，用英文逗号分隔"),
    classes: str | None = Form(None, description="分类任务的类别名（按模型输出顺序，逗号分隔），可选"),
    sample_file: UploadFile | None = File(None, description="可选：一份样例数据，用于生成输入默认值和可解释性基线"),
    user: dict[str, Any] = Depends(web_user),
) -> dict[str, Any]:
    if task not in ("regression", "classification"):
        raise HTTPException(400, "task 只能是 regression 或 classification")
    feats = [f.strip() for f in features.split(",") if f.strip()]
    if not feats:
        raise HTTPException(400, "请填写输入特征名")
    cls_list = [c.strip() for c in classes.split(",")] if classes else None
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, "模型文件过大")
    fname = (file.filename or "").lower()
    sample = None
    if sample_file is not None and sample_file.filename:
        tmp = Path(settings.EXPORT_DIR) / f"sample_{uuid.uuid4().hex}{Path(sample_file.filename).suffix}"
        tmp.write_bytes(await sample_file.read())
        try:
            sample = read_table(str(tmp))
        finally:
            tmp.unlink(missing_ok=True)

    def build() -> ExternalPipeline:
        if fname.endswith(".onnx"):
            adapter_cls = get_adapter("external_onnx")
            ok, reason = adapter_cls.availability()
            if not ok:
                raise ValueError(f"ONNX 模型需要 onnxruntime：{reason}")
            adapter = adapter_cls(task).load_bytes(data)  # type: ignore[attr-defined]
        elif fname.endswith((".joblib", ".pkl", ".pickle")):
            if user["role"] != "admin" or not settings.ALLOW_PICKLE_IMPORT:
                raise PermissionError("joblib/pickle 文件可能包含可执行代码，仅管理员可以导入；普通用户请使用 ONNX 格式")
            import joblib

            obj = joblib.load(io.BytesIO(data))
            adapter = get_adapter("external_pickle")(task).load_object(obj)  # type: ignore[attr-defined]
        else:
            raise ValueError("仅支持 .onnx / .joblib / .pkl 格式")
        pipe = ExternalPipeline(adapter, feats, task, target,
                                classes=cls_list or getattr(adapter, "classes_", None), sample=sample)
        # 用默认值试跑一次，确认模型能正常推理
        probe = pd.DataFrame([{c["name"]: c.get("default", 0) for c in pipe.input_schema}])
        pipe.predict_df(probe)
        return pipe

    try:
        pipe = await run_in_threadpool(build)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except Exception as e:
        raise HTTPException(400, f"模型导入失败：{e}") from e
    path = await run_in_threadpool(save_pipeline, pipe)
    adapter_key = pipe.adapter.key
    model_id = db.insert(
        "models",
        {
            "owner_id": user["id"],
            "name": name,
            "adapter": adapter_key,
            "family": "external",
            "task": task,
            "target": target,
            "metrics_json": {},
            "detail_json": {"external": True, "features": feats, "classes": pipe.classes, "baseline": pipe.baseline,
                            "source_file": file.filename},
            "input_schema_json": pipe.input_schema,
            "path": path,
            "status": "ready",
            "visibility": "private",
            "created_at": db.now(),
        },
    )
    return {"model_id": model_id, "message": "模型已接入，可在模型仓库中发布并通过 API 调用"}


# ======================= 预测服务 =======================
def _log(principal: dict[str, Any], model_id: int, n_rows: int, latency: float, code: int, err: str | None) -> None:
    try:
        db.insert(
            "prediction_logs",
            {
                "user_id": principal["id"],
                "api_key_id": principal.get("api_key_id"),
                "model_id": model_id,
                "source": "api" if principal.get("via_api_key") else "web",
                "n_rows": n_rows,
                "latency_ms": round(latency, 2),
                "status_code": code,
                "error": err,
                "created_at": db.now(),
            },
        )
    except Exception:
        pass


def execute_prediction(row: dict[str, Any], principal: dict[str, Any], df: pd.DataFrame,
                       explain: bool = False) -> dict[str, Any]:
    """所有预测请求的统一执行入口：行数检查 → 并发闸门 → 加载模型（LRU 缓存）→ 预测 → 记录日志。"""
    if len(df) == 0:
        raise HTTPException(400, "没有待预测的数据")
    if len(df) > settings.MAX_PREDICT_ROWS:
        raise HTTPException(413, f"单次最多预测 {settings.MAX_PREDICT_ROWS} 条")
    if not predict_gate.acquire():
        _log(principal, row["id"], len(df), 0, 503, "并发已满，排队超时")
        db.insert("access_logs", {"identity": f"user:{principal['id']}", "path": f"/models/{row['id']}/predict",
                                  "status_code": 503, "reason": "预测并发已满，排队超时", "created_at": db.now()})
        raise HTTPException(503, "预测服务繁忙（并发已满），请稍后重试", headers={"Retry-After": "2"})
    t0 = time.perf_counter()
    code, err = 200, None
    try:
        pipe = model_cache.get(row["id"], row["path"])
        result = pipe.predict_df(df)
        if explain:
            result["explanations"] = pipe.explain_local(df, max_rows=5)
        result["model_id"] = row["id"]
        result["model_name"] = row["name"]
        result["n_rows"] = len(df)
        return result
    except ValueError as e:
        code, err = 400, str(e)
        raise HTTPException(400, f"输入数据有误：{e}") from e
    except Exception as e:
        code, err = 500, f"{type(e).__name__}: {e}"
        raise HTTPException(500, f"预测失败：{err}") from e
    finally:
        latency = (time.perf_counter() - t0) * 1000
        predict_gate.release(latency)
        _log(principal, row["id"], len(df), latency, code, err)


@router.post("/models/{model_id}/predict", summary="在线预测（JSON），支持网页与 API Key 调用")
async def predict(model_id: int, body: PredictIn, principal: dict[str, Any] = Depends(get_principal)) -> dict[str, Any]:
    row = _get_model(model_id, principal)
    df = pd.DataFrame(body.records)
    result = await run_in_threadpool(execute_prediction, row, principal, df, body.explain)
    return result


@router.post("/models/{model_id}/explain", summary="局部可解释性：每个特征对单条预测的贡献")
async def explain(model_id: int, body: PredictIn, principal: dict[str, Any] = Depends(get_principal)) -> dict[str, Any]:
    row = _get_model(model_id, principal)
    df = pd.DataFrame(body.records[:5])
    return await run_in_threadpool(execute_prediction, row, principal, df, True)


def _attach_predictions(df: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    col = f"预测_{result.get('target') or '结果'}"
    out[col] = result["predictions"]
    for i, probs in enumerate(result.get("probabilities") or []):
        for k, v in probs.items():
            out.loc[i, f"概率_{k}"] = v
    return out


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    preds = result["predictions"]
    if result["task"] == "regression":
        arr = np.array([p for p in preds if p is not None], dtype=float)
        if len(arr) == 0:
            return {}
        counts, edges = np.histogram(arr, bins=min(20, max(5, len(arr) // 5)))
        return {
            "mean": round(float(arr.mean()), 4), "std": round(float(arr.std()), 4),
            "min": round(float(arr.min()), 4), "max": round(float(arr.max()), 4),
            "hist": {"bins": [round(float((edges[i] + edges[i + 1]) / 2), 4) for i in range(len(counts))],
                     "counts": counts.tolist()},
        }
    vc = pd.Series(preds).value_counts()
    return {"class_counts": {str(k): int(v) for k, v in vc.items()}}


@router.post("/models/{model_id}/predict-file", summary="批量预测：上传 CSV/Excel，返回带预测结果的 CSV 文件")
async def predict_file(model_id: int, file: UploadFile = File(...),
                       principal: dict[str, Any] = Depends(get_principal)) -> Response:
    row = _get_model(model_id, principal)
    tmp = Path(settings.EXPORT_DIR) / f"in_{uuid.uuid4().hex}{Path(file.filename or 'x.csv').suffix}"
    tmp.write_bytes(await file.read())
    try:
        df = await run_in_threadpool(read_table, str(tmp))
    except Exception as e:
        raise HTTPException(400, f"文件读取失败：{e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    df = df.reset_index(drop=True)
    result = await run_in_threadpool(execute_prediction, row, principal, df, False)
    out = _attach_predictions(df, result)
    content = out.to_csv(index=False).encode("utf-8-sig")
    return Response(content, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''prediction_model{model_id}.csv"})


@router.post("/models/{model_id}/predict-dataset", summary="对平台中已上传的数据集做批量预测（网页使用）")
async def predict_dataset(model_id: int, body: PredictDatasetIn,
                          user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    row = _get_model(model_id, user)
    ds = db.query_one("SELECT * FROM datasets WHERE id = ?", [body.dataset_id])
    if not ds or not can_access(user, ds):
        raise HTTPException(404, "数据集不存在或无权访问")
    df = (await run_in_threadpool(load_dataframe, ds)).reset_index(drop=True)
    has_target = row.get("target") in df.columns
    result = await run_in_threadpool(execute_prediction, row, user, df, False)
    out = _attach_predictions(df, result)
    export_name = f"pred_{model_id}_{uuid.uuid4().hex[:8]}.csv"
    out.to_csv(Path(settings.EXPORT_DIR) / export_name, index=False, encoding="utf-8-sig")
    resp: dict[str, Any] = {
        "task": result["task"],
        "target": result["target"],
        "n_rows": len(out),
        "latency_ms": result["latency_ms"],
        "summary": _summary(result),
        "columns": [str(c) for c in out.columns],
        "rows": out.head(200).astype(object).where(out.head(200).notna(), None).to_dict(orient="records"),
        "export": export_name,
    }
    if has_target:  # 数据里本来就有真实值：顺便给出评估
        from ..core.evaluate import classification_metrics, regression_metrics

        y = df[row["target"]]
        if result["task"] == "regression":
            yt = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float)
            yp = np.array([np.nan if p is None else p for p in result["predictions"]], dtype=float)
            m = np.isfinite(yt) & np.isfinite(yp)
            if m.sum() > 1:
                resp["evaluation"] = regression_metrics(yt[m], yp[m])
                idx = np.where(m)[0][:400]
                resp["scatter"] = [[round(float(yt[i]), 4), round(float(yp[i]), 4)] for i in idx]
        else:
            resp["evaluation"] = classification_metrics([str(v) for v in y], [str(v) for v in result["predictions"]],
                                                        result.get("probabilities"),
                                                        (row.get("detail") or {}).get("classes") or [])
    return resp


@router.get("/exports/{name}", summary="下载预测结果文件")
def download_export(name: str, user: dict[str, Any] = Depends(web_user)) -> FileResponse:
    if "/" in name or "\\" in name or ".." in name or not name.startswith("pred_"):
        raise HTTPException(400, "非法文件名")
    try:
        model_id = int(name.split("_")[1])
    except (IndexError, ValueError):
        raise HTTPException(400, "非法文件名") from None
    _get_model(model_id, user)
    path = Path(settings.EXPORT_DIR) / name
    if not path.exists():
        raise HTTPException(404, "文件不存在或已过期")
    return FileResponse(path, media_type="text/csv", filename=name)
