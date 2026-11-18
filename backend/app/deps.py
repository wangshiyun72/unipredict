"""FastAPI 依赖：身份认证 + 限流。

两种身份：
- 网页用户：请求头 Authorization: Bearer <JWT>
- 外部终端：请求头 X-API-Key: upk_xxx

每个请求进入业务逻辑前先经过令牌桶限流，超出返回 429，并在 access_logs 中记录。
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .concurrency import limiter
from .config import settings
from .security import decode_token, lookup_api_key

bearer_scheme = HTTPBearer(auto_error=False, description="网页登录后获得的 JWT 令牌")
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="外部终端调用使用的 API Key")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _log_reject(identity: str, path: str, code: int, reason: str) -> None:
    try:
        db.insert("access_logs", {"identity": identity, "path": path, "status_code": code, "reason": reason,
                                  "created_at": db.now()})
    except Exception:
        pass


def enforce_rate_limit(request: Request, identity: str, per_minute: int) -> None:
    ok, remaining, wait = limiter.check(identity, per_minute)
    request.state.rate_limit = per_minute
    request.state.rate_remaining = remaining
    if not ok:
        _log_reject(identity, request.url.path, 429, f"超过限流 {per_minute} 次/分钟")
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁：限额 {per_minute} 次/分钟，请 {wait:.1f} 秒后重试",
            headers={"Retry-After": str(int(wait) + 1), "X-RateLimit-Limit": str(per_minute),
                     "X-RateLimit-Remaining": "0"},
        )


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_scheme),
) -> dict[str, Any]:
    if api_key:
        rec = lookup_api_key(api_key)
        if not rec or not rec["is_active"] or not rec["user_active"]:
            _log_reject(f"ip:{client_ip(request)}", request.url.path, 401, "无效的 API Key")
            raise HTTPException(status_code=401, detail="API Key 无效或已停用")
        principal = {
            "id": rec["user_id"],
            "username": rec["username"],
            "role": rec["role"],
            "team": rec["team"],
            "via_api_key": True,
            "api_key_id": rec["id"],
        }
        enforce_rate_limit(request, f"key:{rec['id']}", rec["rate_limit_per_min"])
        db.execute("UPDATE api_keys SET calls = calls + 1, last_used_at = ? WHERE id = ?", [db.now(), rec["id"]])
        return principal
    if creds:
        payload = decode_token(creds.credentials)
        if payload:
            user = db.query_one("SELECT * FROM users WHERE id = ?", [int(payload["sub"])])
            if user and user["is_active"]:
                user.pop("password_hash", None)
                user["via_api_key"] = False
                user["api_key_id"] = None
                enforce_rate_limit(request, f"user:{user['id']}",
                                   user.get("rate_limit_per_min") or settings.RATE_LIMIT_USER_PER_MIN)
                return user
    raise HTTPException(status_code=401, detail="未登录或登录已过期", headers={"WWW-Authenticate": "Bearer"})


def web_user(principal: dict[str, Any] = Depends(get_principal)) -> dict[str, Any]:
    """只允许网页登录用户（管理类接口不对 API Key 开放）。"""
    if principal.get("via_api_key"):
        raise HTTPException(status_code=403, detail="该接口仅支持网页登录用户访问，API Key 只能调用预测相关接口")
    return principal


def admin_user(user: dict[str, Any] = Depends(web_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def anon_rate_limit(request: Request) -> None:
    """未登录接口（登录/注册）按 IP 限流，防止暴力破解。"""
    enforce_rate_limit(request, f"ip:{client_ip(request)}", settings.RATE_LIMIT_ANON_PER_MIN)
