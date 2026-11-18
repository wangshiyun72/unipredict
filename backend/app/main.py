"""服务入口：python -m app.main 或 uvicorn app.main:app

    REST API：  http://<服务器IP>:8000/api/v1/...
    接口文档：  http://<服务器IP>:8000/docs
    网页界面：  开发时 http://localhost:5173（Vite），部署后由本服务直接提供 http://<服务器IP>:8000/
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import BASE_DIR, settings
from .core.adapters import list_adapters, load_plugins
from .core.runtime import gpu_info
from .routers import auth, data, jobs, models, stats
from .security import ensure_default_admin
from .tasks import task_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("unipredict")


def _prepare_templates_background() -> None:
    from .services.templates import prepare_all

    try:
        res = prepare_all()
        logger.info("数据模板准备结果：%s", res)
    except Exception as e:  # pragma: no cover
        logger.warning("数据模板准备失败：%s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    ensure_default_admin()
    task_manager.recover()
    plugins = load_plugins()
    threading.Thread(target=_prepare_templates_background, daemon=True).start()
    avail = [a["key"] for a in list_adapters() if a["available"]]
    logger.info("已加载模型插件：%s", plugins)
    logger.info("可用模型：%s", avail)
    logger.info("计算设备：%s", gpu_info())
    logger.info("接口文档：http://localhost:%s/docs", settings.PORT)
    yield
    task_manager.pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=settings.VERSION,
    description=(
        "基于服务器端通用模型的可访问式深度学习预测服务。\n\n"
        "**外部终端调用方式**：在网页「API 接入」页面创建 API Key，请求头加 `X-API-Key: upk_xxx`，"
        "调用 `POST /api/v1/models/{id}/predict`。\n\n"
        "**网页用户**：`POST /api/v1/auth/login` 获取令牌，请求头加 `Authorization: Bearer <token>`。"
    ),
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Process-Time-Ms", "Retry-After",
                    "Content-Disposition"],
)


@app.middleware("http")
async def timing_and_ratelimit_headers(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    limit = getattr(request.state, "rate_limit", None)
    if limit is not None:
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(getattr(request.state, "rate_remaining", ""))
    return response


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


for r in (auth.router, data.router, jobs.router, models.router, stats.router):
    app.include_router(r, prefix=settings.API_PREFIX)


@app.get("/api/v1/health", tags=["运行监控"], summary="健康检查（无需登录）")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.VERSION, "device": gpu_info()["device"]}


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    # 默认 Swagger 资源在 jsdelivr，国内经常打不开，这里改用 npmmirror 镜像
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{settings.APP_NAME} - 接口文档",
        swagger_js_url=settings.SWAGGER_JS_URL,
        swagger_css_url=settings.SWAGGER_CSS_URL,
        swagger_ui_parameters={"persistAuthorization": True, "docExpansion": "none"},
    )


# 生产部署：前端 npm run build 之后，由后端直接提供网页（单端口访问）
_dist = BASE_DIR.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    def index() -> dict[str, str]:
        return {"message": f"{settings.APP_NAME} 后端已启动", "docs": "/docs",
                "web": "前端尚未构建：开发模式请在 frontend 目录运行 npm run dev"}


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, workers=1, log_level="info")


if __name__ == "__main__":
    run()
