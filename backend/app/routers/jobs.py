"""训练任务与"一键预测"。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .. import db
from ..core.preprocess import infer_task
from ..core.trainer import default_quick_models
from ..deps import web_user
from ..schemas import TrainIn
from ..services.datasets import load_dataframe, save_dataset
from ..services.model_store import can_access
from ..tasks import QueueFullError, task_manager
from ..services.training import submit_training

router = APIRouter(tags=["训练任务"])


@router.post("/jobs/train", summary="提交训练任务（异步，返回任务 ID）")
def create_train_job(body: TrainIn, user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    ds = db.query_one("SELECT * FROM datasets WHERE id = ?", [body.dataset_id])
    if not ds or not can_access(user, ds):
        raise HTTPException(404, "数据集不存在或无权访问")
    cols = [c["name"] for c in (ds.get("profile") or [])]
    if body.target not in cols:
        raise HTTPException(400, f"目标列 {body.target} 不在数据集中")
    try:
        job_id = submit_training(user, ds, body.target, body.models, task=body.task, params=body.params,
                                 scaler=body.scaler, test_size=body.test_size, drop_columns=body.drop_columns,
                                 auto_publish=body.auto_publish)
    except QueueFullError as e:
        raise HTTPException(429, str(e)) from e
    except KeyError as e:
        raise HTTPException(400, str(e)) from e
    return {"job_id": job_id}


@router.post("/quick/predict", summary="一键预测：上传训练数据（+ 可选待预测数据），自动完成归一化、建模、评估、预测")
async def quick_predict(
    train_file: UploadFile = File(..., description="带目标列的历史数据"),
    target: str | None = Form(None, description="目标列，默认最后一列"),
    predict_file: UploadFile | None = File(None, description="待预测数据（不含目标列），可选"),
    user: dict[str, Any] = Depends(web_user),
) -> dict[str, Any]:
    content = await train_file.read()
    try:
        ds = await run_in_threadpool(save_dataset, user["id"], train_file.filename or "train.csv", content,
                                     None, None, "一键预测上传", "private")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    cols = [c["name"] for c in ds["profile"]]
    target = target or cols[-1]
    if target not in cols:
        raise HTTPException(400, f"目标列 {target} 不在数据中，可选列：{cols}")
    df = await run_in_threadpool(load_dataframe, ds)
    task = infer_task(df[target])
    models = default_quick_models(task)
    pred_ds_id = None
    if predict_file is not None and predict_file.filename:
        pcontent = await predict_file.read()
        try:
            pds = await run_in_threadpool(save_dataset, user["id"], predict_file.filename, pcontent,
                                          None, None, "一键预测-待预测数据", "private")
            pred_ds_id = pds["id"]
        except ValueError as e:
            raise HTTPException(400, f"待预测文件：{e}") from e
    try:
        job_id = submit_training(user, ds, target, models, task=task)
    except QueueFullError as e:
        raise HTTPException(429, str(e)) from e
    return {"job_id": job_id, "dataset_id": ds["id"], "predict_dataset_id": pred_ds_id, "target": target,
            "task": task, "models": models}


@router.get("/jobs", summary="任务列表")
def list_jobs(user: dict[str, Any] = Depends(web_user), limit: int = 50) -> list[dict[str, Any]]:
    cond, params = ("1=1", []) if user["role"] == "admin" else ("j.owner_id = ?", [user["id"]])
    return db.query(
        f"SELECT j.id, j.owner_id, j.type, j.status, j.progress, j.message, j.params_json, j.created_at, "
        f"j.started_at, j.finished_at, u.username AS owner_name FROM jobs j JOIN users u ON u.id = j.owner_id "
        f"WHERE {cond} ORDER BY j.id DESC LIMIT ?",
        [*params, min(limit, 200)],
    )


@router.get("/jobs/{job_id}", summary="任务详情：进度、日志、排行榜")
def job_detail(job_id: int, user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    job = db.query_one("SELECT * FROM jobs WHERE id = ?", [job_id])
    if not job or (job["owner_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "任务不存在")
    if job["status"] == "queued":
        ahead = db.query_one("SELECT COUNT(*) AS n FROM jobs WHERE status='queued' AND id < ?", [job_id])
        job["queue_position"] = (ahead or {"n": 0})["n"] + 1
    return job


@router.post("/jobs/{job_id}/cancel", summary="取消任务")
def cancel_job(job_id: int, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    job = db.query_one("SELECT * FROM jobs WHERE id = ?", [job_id])
    if not job or (job["owner_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "任务不存在")
    if not task_manager.cancel(job_id):
        raise HTTPException(400, "任务已结束，无法取消")
    return {"message": "已发送取消请求（正在训练的模型会在当前模型结束后停止）"}
