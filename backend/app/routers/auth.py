"""账号与 API Key 管理。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..config import settings
from ..deps import anon_rate_limit, web_user
from ..schemas import ChangePasswordIn, KeyCreateIn, KeyPatchIn, LoginIn, RegisterIn
from ..security import create_api_key, create_token, hash_password, verify_password

router = APIRouter(tags=["账号与 API Key"])


def _public_user(u: dict[str, Any]) -> dict[str, Any]:
    return {k: u.get(k) for k in ("id", "username", "display_name", "team", "role", "is_active", "created_at",
                                   "rate_limit_per_min")}


@router.post("/auth/login", summary="登录，获取 JWT 令牌", dependencies=[Depends(anon_rate_limit)])
def login(body: LoginIn) -> dict[str, Any]:
    name = body.username.strip()
    if "@" in name:
        name = name.lower()  # 邮箱不区分大小写
    user = db.query_one("SELECT * FROM users WHERE username = ?", [name])
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被停用，请联系管理员")
    return {"access_token": create_token(user), "token_type": "bearer", "user": _public_user(user)}


@router.post("/auth/register", summary="注册新用户", dependencies=[Depends(anon_rate_limit)])
def register(body: RegisterIn) -> dict[str, Any]:
    if not settings.ALLOW_REGISTER:
        raise HTTPException(status_code=403, detail="平台已关闭自助注册，请联系管理员开通账号")
    email = body.username.strip().lower()
    if db.query_one("SELECT id FROM users WHERE username = ?", [email]):
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")
    uid = db.insert(
        "users",
        {
            "username": email,
            "password_hash": hash_password(body.password),
            "display_name": body.display_name or email.split("@")[0],
            "team": body.team or "默认团队",
            "role": "user",
            "created_at": db.now(),
        },
    )
    user = db.query_one("SELECT * FROM users WHERE id = ?", [uid])
    assert user
    return {"access_token": create_token(user), "token_type": "bearer", "user": _public_user(user)}


@router.get("/auth/me", summary="当前用户信息")
def me(user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    return _public_user(user)


@router.post("/auth/change-password", summary="修改密码")
def change_password(body: ChangePasswordIn, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    row = db.query_one("SELECT password_hash FROM users WHERE id = ?", [user["id"]])
    if not row or not verify_password(body.old_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码错误")
    db.update("users", user["id"], {"password_hash": hash_password(body.new_password)})
    return {"message": "密码已修改"}


# ---------------- API Key ----------------
@router.get("/keys", summary="我的 API Key 列表")
def list_keys(user: dict[str, Any] = Depends(web_user)) -> list[dict[str, Any]]:
    return db.query(
        "SELECT id, name, key_prefix, rate_limit_per_min, is_active, calls, created_at, last_used_at "
        "FROM api_keys WHERE user_id = ? ORDER BY id DESC",
        [user["id"]],
    )


@router.post("/keys", summary="创建 API Key（明文只显示一次）")
def new_key(body: KeyCreateIn, user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    n = db.query_one("SELECT COUNT(*) AS n FROM api_keys WHERE user_id = ? AND is_active = 1", [user["id"]])
    if n and n["n"] >= 10:
        raise HTTPException(status_code=400, detail="每个用户最多 10 个有效 API Key")
    rate = body.rate_limit_per_min if user["role"] == "admin" else None
    raw, key_id = create_api_key(user["id"], body.name, rate)
    return {"id": key_id, "api_key": raw, "message": "请立即复制保存，关闭后将无法再次查看完整 Key"}


@router.patch("/keys/{key_id}", summary="启用/停用 API Key，调整限额（限额仅管理员）")
def patch_key(key_id: int, body: KeyPatchIn, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    row = db.query_one("SELECT * FROM api_keys WHERE id = ?", [key_id])
    if not row or (row["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(status_code=404, detail="API Key 不存在")
    data: dict[str, Any] = {}
    if body.is_active is not None:
        data["is_active"] = 1 if body.is_active else 0
    if body.rate_limit_per_min is not None:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="只有管理员可以调整限额")
        data["rate_limit_per_min"] = body.rate_limit_per_min
    db.update("api_keys", key_id, data)
    return {"message": "已更新"}


@router.delete("/keys/{key_id}", summary="删除 API Key")
def delete_key(key_id: int, user: dict[str, Any] = Depends(web_user)) -> dict[str, str]:
    row = db.query_one("SELECT * FROM api_keys WHERE id = ?", [key_id])
    if not row or (row["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(status_code=404, detail="API Key 不存在")
    db.execute("DELETE FROM api_keys WHERE id = ?", [key_id])
    return {"message": "已删除"}
