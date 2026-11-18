"""数据模板、数据集、可用模型列表。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .. import db
from ..core.adapters import list_adapters
from ..deps import web_user
from ..schemas import DatasetPatchIn, TemplateTrainIn
from ..services import templates as tpl
from ..services.datasets import preview, save_dataset
from ..services.model_store import can_access, can_modify, visible_filter
from ..services.training import submit_training
from ..tasks import QueueFullError

router = APIRouter()


# ======================= 可用模型 =======================
@router.get("/adapters", tags=["模型适配器"], summary="平台已接入的模型（含依赖可用状态与参数说明）")
def adapters(_: dict[str, Any] = Depends(web_user)) -> list[dict[str, Any]]:
    return list_adapters()


# ======================= 数据模板 =======================
@router.get("/templates", tags=["数据模板"], summary="化工/环境领域数据模板列表")
def templates(_: dict[str, Any] = Depends(web_user)) -> list[dict[str, Any]]:
    return tpl.list_templates()


@router.get("/templates/{key}", tags=["数据模板"], summary="模板详情与示例数据")
async def template_detail(key: str, _: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    if key not in tpl.TEMPLATES:
        raise HTTPException(404, "模板不存在")
    info = {**tpl.TEMPLATES[key], **tpl.template_status(key)}
    if info["ready"]:
        import pandas as pd

        df = pd.read_csv(tpl.template_path(key), encoding="utf-8-sig").head(10)
        info["preview"] = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    return info


@router.post("/templates/{key}/prepare", tags=["数据模板"], summary="准备模板数据（生成或下载公开数据集）")
async def template_prepare(key: str, _: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    if key not in tpl.TEMPLATES:
        raise HTTPException(404, "模板不存在")
    try:
        await run_in_threadpool(tpl.ensure_template_data, key)
    except Exception as e:
        raise HTTPException(502, str(e)) from e
    return tpl.template_status(key)


@router.get("/templates/{key}/download", tags=["数据模板"], summary="下载 CSV 填写模板（表头 + 示例行）")
async def template_download(key: str, _: dict[str, Any] = Depends(web_user)) -> Response:
    if key not in tpl.TEMPLATES:
        raise HTTPException(404, "模板不存在")
    content = await run_in_threadpool(tpl.blank_template_csv, key)
    return Response(content, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{key}_template.csv"})


def _template_dataset(user: dict[str, Any], key: str) -> dict[str, Any]:
    path = tpl.ensure_template_data(key)
    t = tpl.TEMPLATES[key]
    # 模板示例数据是公开数据/模拟数据，默认全平台公开；用它训练出的模型也随之公开
    return save_dataset(user["id"], f"{t['name']}.csv", Path(path).read_bytes(), name=f"{t['name']}（示例数据）",
                        template_key=key, description=t["description"], visibility="public")


@router.post("/templates/{key}/use", tags=["数据模板"], summary="把模板示例数据导入为我的数据集")
async def template_use(key: str, user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    if key not in tpl.TEMPLATES:
        raise HTTPException(404, "模板不存在")
    try:
        return await run_in_threadpool(_template_dataset, user, key)
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@router.post("/templates/{key}/quick-train", tags=["数据模板"], summary="一键演示：导入模板数据并用推荐模型训练")
async def template_quick_train(key: str, body: TemplateTrainIn | None = None,
                               user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    if key not in tpl.TEMPLATES:
        raise HTTPException(404, "模板不存在")
    t = tpl.TEMPLATES[key]
    try:
        ds = await run_in_threadpool(_template_dataset, user, key)
    except Exception as e:
        raise HTTPException(502, str(e)) from e
    from ..core.adapters import get_adapter

    models = (body.models if body and body.models else None) or [
        m for m in t["recommended_models"] if get_adapter(m).availability()[0]
    ]
    target = (body.target if body and body.target else None) or t["target"]
    try:
        job_id = submit_training(user, ds, target, models, task=t["task"], drop_columns=t.get("drop_for_training"))
    except QueueFullError as e:
        raise HTTPException(429, str(e)) from e
    return {"job_id": job_id, "dataset_id": ds["id"], "models": models, "target": target}


# ======================= 数据集 =======================
@router.post("/datasets", tags=["数据集"], summary="上传数据集（CSV / Excel）")
async def upload_dataset(
    file: UploadFile = File(..., description="CSV 或 Excel 文件"),
    name: str | None = Form(None),
    description: str | None = Form(None),
    visibility: str = Form("private"),
    user: dict[str, Any] = Depends(web_user),
) -> dict[str, Any]:
    if visibility not in ("private", "team", "public"):
        raise HTTPException(400, "visibility 只能是 private / team / public")
    content = await file.read()
    try:
        return await run_in_threadpool(save_dataset, user["id"], file.filename or "data.csv", content, name, None,
                                       description, visibility)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/datasets", tags=["数据集"], summary="我能访问的数据集")
def list_datasets(user: dict[str, Any] = Depends(web_user)) -> list[dict[str, Any]]:
    cond, params = visible_filter(user, "d")
    rows = db.query(
        f"SELECT d.id, d.owner_id, d.name, d.filename, d.n_rows, d.n_cols, d.template_key, d.description, "
        f"d.visibility, d.created_at, u.username AS owner_name, u.team AS owner_team "
        f"FROM datasets d JOIN users u ON u.id = d.owner_id WHERE {cond} ORDER BY d.id DESC",
        params,
    )
    return rows


def _get_dataset(ds_id: int, user: dict[str, Any]) -> dict[str, Any]:
    ds = db.query_one("SELECT * FROM datasets WHERE id = ?", [ds_id])
    if not ds or not can_access(user, ds):
        raise HTTPException(404, "数据集不存在或无权访问")
    return ds


@router.get("/datasets/{ds_id}", tags=["数据集"], summary="数据集详情：数据画像 + 前 20 行预览")
async def dataset_detail(ds_id: int, user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    ds = _get_dataset(ds_id, user)
    ds["preview"] = await run_in_threadpool(preview, ds)
    ds.pop("path", None)
    return ds


@router.patch("/datasets/{ds_id}", tags=["数据集"], summary="修改名称/共享范围")
def patch_dataset(ds_id: int, body: DatasetPatchIn, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    ds = _get_dataset(ds_id, user)
    if not can_modify(user, ds):
        raise HTTPException(403, "只有创建者可以修改")
    db.update("datasets", ds_id, body.model_dump(exclude_none=True))
    return {"message": "已更新"}


@router.delete("/datasets/{ds_id}", tags=["数据集"], summary="删除数据集")
def delete_dataset(ds_id: int, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    ds = _get_dataset(ds_id, user)
    if not can_modify(user, ds):
        raise HTTPException(403, "只有创建者可以删除")
    db.execute("DELETE FROM datasets WHERE id = ?", [ds_id])
    Path(ds["path"]).unlink(missing_ok=True)
    return {"message": "已删除"}
