"""模型仓库：模型文件的保存/加载、内存缓存（LRU）、访问权限判断。"""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

import joblib

from .. import db
from ..config import settings
from ..core.pipeline import BasePipeline


def can_access(user: dict[str, Any], row: dict[str, Any], via_api_key: bool = False) -> bool:
    """访问控制：本人 / 管理员 / 同团队共享 / 公开。API Key 调用只能访问已发布的模型。"""
    if row is None:
        return False
    if via_api_key and "status" in row and row["status"] != "published" and row["owner_id"] != user["id"]:
        return False
    if user.get("role") == "admin" or row["owner_id"] == user["id"]:
        return True
    vis = row.get("visibility", "private")
    if vis == "public":
        return True
    if vis == "team":
        owner = db.query_one("SELECT team FROM users WHERE id=?", [row["owner_id"]])
        return bool(owner and owner["team"] == user.get("team"))
    return False


def can_modify(user: dict[str, Any], row: dict[str, Any]) -> bool:
    return user.get("role") == "admin" or row["owner_id"] == user["id"]


def visible_filter(user: dict[str, Any], alias: str = "") -> tuple[str, list[Any]]:
    """生成 SQL 条件：当前用户能看到的数据集/模型。"""
    p = f"{alias}." if alias else ""
    if user.get("role") == "admin":
        return "1=1", []
    return (
        f"({p}owner_id = ? OR {p}visibility = 'public' OR "
        f"({p}visibility = 'team' AND {p}owner_id IN (SELECT id FROM users WHERE team = ?)))",
        [user["id"], user.get("team")],
    )


def save_pipeline(pipe: BasePipeline) -> str:
    path = Path(settings.MODEL_DIR) / f"{uuid.uuid4().hex}.joblib"
    joblib.dump(pipe, path, compress=3)
    return str(path)


class ModelCache:
    """已加载模型的 LRU 缓存：常用模型常驻内存，避免每次预测都从磁盘加载。"""

    def __init__(self, size: int) -> None:
        self.size = size
        self._data: OrderedDict[int, BasePipeline] = OrderedDict()
        self._lock = threading.Lock()
        self._load_locks: dict[int, threading.Lock] = {}
        self.hits = 0
        self.misses = 0

    def get(self, model_id: int, path: str) -> BasePipeline:
        with self._lock:
            if model_id in self._data:
                self._data.move_to_end(model_id)
                self.hits += 1
                return self._data[model_id]
            lock = self._load_locks.setdefault(model_id, threading.Lock())
        with lock:  # 同一个模型只加载一次
            with self._lock:
                if model_id in self._data:
                    self.hits += 1
                    return self._data[model_id]
            pipe = joblib.load(path)
            with self._lock:
                self.misses += 1
                self._data[model_id] = pipe
                while len(self._data) > self.size:
                    self._data.popitem(last=False)
            return pipe

    def evict(self, model_id: int) -> None:
        with self._lock:
            self._data.pop(model_id, None)

    def stats(self) -> dict[str, Any]:
        return {"size": self.size, "loaded": list(self._data.keys()), "hits": self.hits, "misses": self.misses}


model_cache = ModelCache(settings.MODEL_CACHE_SIZE)
