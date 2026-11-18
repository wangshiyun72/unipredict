"""训练任务队列。

训练是耗时操作，不能阻塞 HTTP 请求：提交后立即返回任务 ID，后台线程池按顺序执行，
前端轮询任务进度。并发控制：
- 线程池大小 TRAIN_WORKERS：同时运行的训练任务数
- MAX_JOBS_PER_USER：每个用户同时排队+运行的任务上限
- MAX_QUEUE_SIZE：全局排队上限
"""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import db
from .config import settings

logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    pass


class TaskManager:
    def __init__(self, workers: int) -> None:
        self.workers = workers
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="train")
        self._cancel_flags: dict[int, threading.Event] = {}
        self._lock = threading.Lock()

    def recover(self) -> None:
        """服务重启时，把上次未完成的任务标记为失败。"""
        db.execute(
            "UPDATE jobs SET status='failed', message='服务重启，任务中断', finished_at=? "
            "WHERE status IN ('queued','running')",
            [db.now()],
        )

    def counts(self) -> dict[str, int]:
        rows = db.query("SELECT status, COUNT(*) AS n FROM jobs WHERE status IN ('queued','running') GROUP BY status")
        out = {"queued": 0, "running": 0}
        for r in rows:
            out[r["status"]] = r["n"]
        return out

    def submit(self, owner_id: int, job_type: str, params: dict[str, Any],
               fn: Callable[[int, Callable[[float, str], None], Callable[[], bool]], dict[str, Any]],
               dataset_id: int | None = None) -> int:
        with self._lock:
            active = db.query_one(
                "SELECT COUNT(*) AS n FROM jobs WHERE owner_id=? AND status IN ('queued','running')", [owner_id]
            )
            if active and active["n"] >= settings.MAX_JOBS_PER_USER:
                raise QueueFullError(
                    f"每个用户最多同时运行/排队 {settings.MAX_JOBS_PER_USER} 个训练任务，请等待当前任务完成"
                )
            total = sum(self.counts().values())
            if total >= settings.MAX_QUEUE_SIZE:
                raise QueueFullError("服务器任务队列已满，请稍后再试")
            job_id = db.insert(
                "jobs",
                {
                    "owner_id": owner_id,
                    "type": job_type,
                    "status": "queued",
                    "progress": 0,
                    "message": "排队中",
                    "params_json": params,
                    "log_json": [],
                    "dataset_id": dataset_id,
                    "created_at": db.now(),
                },
            )
            self._cancel_flags[job_id] = threading.Event()
        self.pool.submit(self._run, job_id, fn)
        return job_id

    def cancel(self, job_id: int) -> bool:
        flag = self._cancel_flags.get(job_id)
        job = db.query_one("SELECT status FROM jobs WHERE id=?", [job_id])
        if not job or job["status"] not in ("queued", "running"):
            return False
        if flag:
            flag.set()
        if job["status"] == "queued":
            db.update("jobs", job_id, {"status": "cancelled", "message": "已取消", "finished_at": db.now()})
        return True

    def _run(self, job_id: int, fn: Callable[..., dict[str, Any]]) -> None:
        flag = self._cancel_flags.get(job_id) or threading.Event()
        job = db.query_one("SELECT status FROM jobs WHERE id=?", [job_id])
        if not job or job["status"] == "cancelled" or flag.is_set():
            return
        db.update("jobs", job_id, {"status": "running", "started_at": db.now(), "message": "开始运行"})
        log: list[str] = []

        def progress(p: float, msg: str) -> None:
            log.append(f"[{db.now()}] {msg}")
            db.update("jobs", job_id, {"progress": round(min(max(p, 0), 1), 4), "message": msg, "log_json": log})

        try:
            result = fn(job_id, progress, flag.is_set)
            if flag.is_set():
                raise _Cancelled()
            log.append(f"[{db.now()}] 任务完成")
            db.update(
                "jobs",
                job_id,
                {"status": "succeeded", "progress": 1, "message": "完成", "result_json": result,
                 "log_json": log, "finished_at": db.now()},
            )
        except _Cancelled:
            db.update("jobs", job_id, {"status": "cancelled", "message": "已取消", "log_json": log, "finished_at": db.now()})
        except Exception as e:
            from .core.trainer import TrainingCancelled

            if isinstance(e, TrainingCancelled):
                db.update("jobs", job_id, {"status": "cancelled", "message": "已取消", "log_json": log,
                                           "finished_at": db.now()})
            else:
                logger.exception("任务 %s 失败", job_id)
                log.append(f"[{db.now()}] 失败：{e}")
                db.update(
                    "jobs",
                    job_id,
                    {"status": "failed", "message": str(e)[:500], "log_json": log + [traceback.format_exc(limit=4)],
                     "finished_at": db.now()},
                )
        finally:
            self._cancel_flags.pop(job_id, None)


class _Cancelled(Exception):
    pass


task_manager = TaskManager(settings.TRAIN_WORKERS)
