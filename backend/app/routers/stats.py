"""运行监控与系统管理。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..concurrency import limiter, predict_gate
from ..config import settings
from ..core.runtime import gpu_info
from ..deps import admin_user, web_user
from ..schemas import UserPatchIn
from ..services.model_store import model_cache
from ..tasks import task_manager

router = APIRouter()


@router.get("/stats/overview", tags=["运行监控"], summary="平台概览：数量统计、调用趋势、延迟")
def overview(user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    is_admin = user["role"] == "admin"
    own = "" if is_admin else " WHERE owner_id = ?"
    p = [] if is_admin else [user["id"]]

    def count(table: str, extra: str = "") -> int:
        sql = f"SELECT COUNT(*) AS n FROM {table}{own}"
        if extra:
            sql += (" AND " if own else " WHERE ") + extra
        r = db.query_one(sql, p)
        return int(r["n"]) if r else 0

    log_cond = "" if is_admin else " AND user_id = ?"
    trend = db.query(
        "SELECT substr(created_at, 1, 10) AS day, source, COUNT(*) AS calls, SUM(n_rows) AS rows, "
        "AVG(latency_ms) AS avg_latency FROM prediction_logs "
        f"WHERE created_at >= date('now', '-13 day', 'localtime'){log_cond} GROUP BY day, source ORDER BY day",
        p,
    )
    status = db.query(
        f"SELECT status_code, COUNT(*) AS n FROM prediction_logs WHERE 1=1{log_cond} GROUP BY status_code", p
    )
    top = db.query(
        "SELECT m.id, m.name, COUNT(*) AS calls, AVG(l.latency_ms) AS avg_latency FROM prediction_logs l "
        f"JOIN models m ON m.id = l.model_id WHERE 1=1{log_cond.replace('user_id', 'l.user_id')} "
        "GROUP BY m.id ORDER BY calls DESC LIMIT 8",
        p,
    )
    family = db.query(
        f"SELECT family, COUNT(*) AS n FROM models{own}{' AND' if own else ' WHERE'} status != 'archived' GROUP BY family",
        p,
    )
    totals = db.query_one(
        f"SELECT COUNT(*) AS calls, COALESCE(SUM(n_rows),0) AS rows, AVG(latency_ms) AS avg_latency "
        f"FROM prediction_logs WHERE status_code = 200{log_cond}",
        p,
    )
    return {
        "datasets": count("datasets"),
        "models": count("models", "status != 'archived'"),
        "published_models": count("models", "status = 'published'"),
        "jobs": count("jobs"),
        "users": int((db.query_one("SELECT COUNT(*) AS n FROM users") or {"n": 0})["n"]) if is_admin else None,
        "totals": totals,
        "trend": trend,
        "status_codes": status,
        "top_models": top,
        "model_families": family,
    }


@router.get("/stats/system", tags=["运行监控"], summary="服务器实时状态：并发、队列、限流、GPU、模型缓存")
def system(_: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    rejects = db.query(
        "SELECT status_code, COUNT(*) AS n FROM access_logs WHERE created_at >= datetime('now', '-1 day', 'localtime') "
        "GROUP BY status_code"
    )
    return {
        "predict_gate": predict_gate.stats(),
        "rate_limiter": {"allowed": limiter.allowed, "rejected": limiter.rejected},
        "jobs": {**task_manager.counts(), "workers": settings.TRAIN_WORKERS,
                 "max_jobs_per_user": settings.MAX_JOBS_PER_USER, "max_queue": settings.MAX_QUEUE_SIZE},
        "gpu": gpu_info(),
        "model_cache": model_cache.stats(),
        "rejects_24h": rejects,
        "config": {
            "predict_concurrency": settings.PREDICT_CONCURRENCY,
            "predict_queue_timeout": settings.PREDICT_QUEUE_TIMEOUT,
            "gpu_concurrency": settings.GPU_CONCURRENCY,
            "rate_limit_user_per_min": settings.RATE_LIMIT_USER_PER_MIN,
            "rate_limit_key_per_min": settings.RATE_LIMIT_KEY_PER_MIN,
            "max_predict_rows": settings.MAX_PREDICT_ROWS,
        },
    }


@router.get("/stats/calls", tags=["运行监控"], summary="最近的预测调用记录")
def recent_calls(user: dict[str, Any] = Depends(web_user), limit: int = 50) -> list[dict[str, Any]]:
    cond, p = ("1=1", []) if user["role"] == "admin" else ("l.user_id = ?", [user["id"]])
    return db.query(
        "SELECT l.*, m.name AS model_name, u.username FROM prediction_logs l LEFT JOIN models m ON m.id = l.model_id "
        f"LEFT JOIN users u ON u.id = l.user_id WHERE {cond} ORDER BY l.id DESC LIMIT ?",
        [*p, min(limit, 500)],
    )


# ======================= 管理员 =======================
@router.get("/admin/users", tags=["系统管理"], summary="用户列表")
def users(_: dict[str, Any] = Depends(admin_user)) -> list[dict[str, Any]]:
    return db.query(
        "SELECT u.id, u.username, u.display_name, u.team, u.role, u.is_active, u.rate_limit_per_min, u.created_at, "
        "(SELECT COUNT(*) FROM models m WHERE m.owner_id = u.id) AS models, "
        "(SELECT COUNT(*) FROM prediction_logs l WHERE l.user_id = u.id) AS calls "
        "FROM users u ORDER BY u.id"
    )


@router.patch("/admin/users/{user_id}", tags=["系统管理"], summary="修改用户角色/团队/状态/限额")
def patch_user(user_id: int, body: UserPatchIn, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, str]:
    if not db.query_one("SELECT id FROM users WHERE id = ?", [user_id]):
        raise HTTPException(404, "用户不存在")
    data = body.model_dump(exclude_none=True)
    if user_id == admin["id"] and (data.get("role") == "user" or data.get("is_active") is False):
        raise HTTPException(400, "不能取消自己的管理员权限或停用自己")
    if "is_active" in data:
        data["is_active"] = 1 if data["is_active"] else 0
    db.update("users", user_id, data)
    return {"message": "已更新"}


@router.get("/admin/access-logs", tags=["系统管理"], summary="被拒绝的访问记录（限流 429 / 并发满 503 / 认证失败 401）")
def access_logs(_: dict[str, Any] = Depends(admin_user), limit: int = 100) -> list[dict[str, Any]]:
    return db.query("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", [min(limit, 1000)])


@router.post("/admin/publish-best", tags=["系统管理"], summary="一键发布并公开所有最优模型（供所有注册用户使用）")
def publish_best(_: dict[str, Any] = Depends(admin_user), only_templates: bool = False) -> dict[str, Any]:
    cond = "m.is_best = 1 AND m.status != 'archived'"
    if only_templates:
        cond += " AND m.dataset_id IN (SELECT id FROM datasets WHERE template_key IS NOT NULL)"
    rows = db.query(f"SELECT m.id, m.dataset_id FROM models m WHERE {cond}")
    for r in rows:
        db.update("models", r["id"], {"status": "published", "visibility": "public"})
        if r.get("dataset_id"):
            db.update("datasets", r["dataset_id"], {"visibility": "public"})
    return {"published": len(rows), "message": f"已发布并公开 {len(rows)} 个最优模型，所有注册用户都可以使用"}
