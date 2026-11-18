"""平台全局配置。

所有配置项都可以通过环境变量覆盖（也可以写在 backend/.env 文件里，格式 KEY=VALUE）。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    APP_NAME = "通用模型预测服务平台"
    APP_NAME_EN = "UniPredict"
    VERSION = "1.0.0"
    API_PREFIX = "/api/v1"

    # ---------- 存储 ----------
    STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", BASE_DIR / "storage"))
    DB_PATH = STORAGE_DIR / "platform.db"
    DATASET_DIR = STORAGE_DIR / "datasets"
    MODEL_DIR = STORAGE_DIR / "models"
    TEMPLATE_DATA_DIR = STORAGE_DIR / "template_data"
    EXPORT_DIR = STORAGE_DIR / "exports"

    # ---------- 网络服务 ----------
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = _env_int("PORT", 8000)
    CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

    # ---------- 鉴权 ----------
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = _env_int("JWT_EXPIRE_MINUTES", 60 * 12)
    ALLOW_REGISTER = _env_bool("ALLOW_REGISTER", True)
    DEFAULT_ADMIN_USER = os.environ.get("DEFAULT_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")

    # ---------- 并发访问控制 ----------
    # 训练任务线程池大小（同时运行的训练任务数）
    TRAIN_WORKERS = _env_int("TRAIN_WORKERS", 2)
    # 每个用户同时排队+运行的训练任务上限
    MAX_JOBS_PER_USER = _env_int("MAX_JOBS_PER_USER", 2)
    # 任务队列总长度上限（超出直接拒绝，防止堆积）
    MAX_QUEUE_SIZE = _env_int("MAX_QUEUE_SIZE", 20)
    # 同时执行的预测请求上限（全局）
    PREDICT_CONCURRENCY = _env_int("PREDICT_CONCURRENCY", 8)
    # 预测请求排队等待上限（秒），超时返回 503
    PREDICT_QUEUE_TIMEOUT = _env_int("PREDICT_QUEUE_TIMEOUT", 15)
    # 同时占用 GPU 的推理/训练数（8GB 显存建议 1~2）
    GPU_CONCURRENCY = _env_int("GPU_CONCURRENCY", 2)
    # 默认限流：每分钟请求数
    RATE_LIMIT_USER_PER_MIN = _env_int("RATE_LIMIT_USER_PER_MIN", 300)
    RATE_LIMIT_KEY_PER_MIN = _env_int("RATE_LIMIT_KEY_PER_MIN", 60)
    RATE_LIMIT_ANON_PER_MIN = _env_int("RATE_LIMIT_ANON_PER_MIN", 30)
    # 内存中缓存的已加载模型数量
    MODEL_CACHE_SIZE = _env_int("MODEL_CACHE_SIZE", 8)

    # ---------- 数据限制 ----------
    MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 50)
    MAX_PREDICT_ROWS = _env_int("MAX_PREDICT_ROWS", 50000)
    MAX_TRAIN_ROWS = _env_int("MAX_TRAIN_ROWS", 200000)
    TABPFN_MAX_TRAIN_ROWS = _env_int("TABPFN_MAX_TRAIN_ROWS", 3000)

    # ---------- 模型 / 镜像 ----------
    # 国内访问 HuggingFace 使用镜像（TabPFN 权重从这里下载）
    HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
    DEVICE = os.environ.get("DEVICE", "auto")  # auto / cuda / cpu
    # 是否允许管理员导入 joblib/pickle 模型（pickle 可执行任意代码，仅限可信来源）
    ALLOW_PICKLE_IMPORT = _env_bool("ALLOW_PICKLE_IMPORT", True)

    # ---------- 接口文档静态资源（国内 CDN） ----------
    SWAGGER_JS_URL = os.environ.get(
        "SWAGGER_JS_URL",
        "https://registry.npmmirror.com/swagger-ui-dist/5.17.14/files/swagger-ui-bundle.js",
    )
    SWAGGER_CSS_URL = os.environ.get(
        "SWAGGER_CSS_URL",
        "https://registry.npmmirror.com/swagger-ui-dist/5.17.14/files/swagger-ui.css",
    )

    def __init__(self) -> None:
        for d in (self.STORAGE_DIR, self.DATASET_DIR, self.MODEL_DIR, self.TEMPLATE_DATA_DIR, self.EXPORT_DIR):
            Path(d).mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_ENDPOINT", self.HF_ENDPOINT)
        self.SECRET_KEY = os.environ.get("SECRET_KEY") or self._load_or_create_secret()

    def _load_or_create_secret(self) -> str:
        key_file = Path(self.STORAGE_DIR) / "secret.key"
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key = secrets.token_urlsafe(48)
        key_file.write_text(key, encoding="utf-8")
        return key


settings = Settings()
