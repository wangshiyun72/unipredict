"""鉴权：密码哈希、JWT 令牌（网页登录）、API Key（外部终端调用）。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from . import db
from .config import settings

API_KEY_PREFIX = "upk_"


# ---------------- 密码 ----------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 200_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 200_000).hex()
    return hmac.compare_digest(calc, digest)


# ---------------- JWT ----------------
def create_token(user: dict[str, Any]) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user["id"]), "role": user["role"], "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ---------------- API Key ----------------
def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_api_key(user_id: int, name: str, rate_limit: int | None = None) -> tuple[str, int]:
    """生成 API Key。明文只在创建时返回一次，数据库只存哈希。"""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key_id = db.insert(
        "api_keys",
        {
            "user_id": user_id,
            "name": name,
            "key_prefix": raw[:12],
            "key_hash": _hash_key(raw),
            "rate_limit_per_min": rate_limit or settings.RATE_LIMIT_KEY_PER_MIN,
            "created_at": db.now(),
        },
    )
    return raw, key_id


def lookup_api_key(raw: str) -> dict[str, Any] | None:
    if not raw or not raw.startswith(API_KEY_PREFIX):
        return None
    return db.query_one(
        "SELECT k.*, u.username, u.role, u.team, u.is_active AS user_active FROM api_keys k "
        "JOIN users u ON u.id = k.user_id WHERE k.key_hash = ?",
        [_hash_key(raw)],
    )


def ensure_default_admin() -> None:
    if db.query_one("SELECT id FROM users WHERE role = 'admin'"):
        return
    db.insert(
        "users",
        {
            "username": settings.DEFAULT_ADMIN_USER,
            "password_hash": hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            "display_name": "平台管理员",
            "team": "平台管理",
            "role": "admin",
            "created_at": db.now(),
        },
    )
