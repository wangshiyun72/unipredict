"""SQLite 数据层（Python 标准库 sqlite3，无需额外安装数据库）。

WAL 模式下支持多线程并发读、串行写，对单机部署的预测平台足够。
需要扩展到多机部署时，可以把这一层替换为 PostgreSQL。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    team TEXT DEFAULT '默认团队',
    role TEXT NOT NULL DEFAULT 'user',          -- admin / user
    is_active INTEGER NOT NULL DEFAULT 1,
    rate_limit_per_min INTEGER,                  -- 为空时使用全局默认
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    rate_limit_per_min INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    calls INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    n_rows INTEGER, n_cols INTEGER,
    profile_json TEXT,
    template_key TEXT,
    description TEXT,
    visibility TEXT NOT NULL DEFAULT 'private', -- private / team / public
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,                          -- train
    status TEXT NOT NULL,                        -- queued / running / succeeded / failed / cancelled
    progress REAL NOT NULL DEFAULT 0,
    message TEXT,
    params_json TEXT,
    result_json TEXT,
    log_json TEXT,
    dataset_id INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id INTEGER,
    dataset_id INTEGER,
    name TEXT NOT NULL,
    adapter TEXT NOT NULL,
    family TEXT,
    task TEXT NOT NULL,
    target TEXT,
    metrics_json TEXT,
    detail_json TEXT,
    input_schema_json TEXT,
    path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',       -- ready / published / archived
    visibility TEXT NOT NULL DEFAULT 'private',
    is_best INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prediction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    api_key_id INTEGER,
    model_id INTEGER,
    source TEXT,                                 -- web / api
    n_rows INTEGER,
    latency_ms REAL,
    status_code INTEGER,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity TEXT,
    path TEXT,
    status_code INTEGER,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predlog_time ON prediction_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(owner_id, status);
"""

_local = threading.local()
_write_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(str(settings.DB_PATH), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=30000")
        _local.conn = c
    return c


def init_db() -> None:
    with _write_lock:
        c = conn()
        c.executescript(SCHEMA)
        c.commit()


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for k in list(d.keys()):
        if k.endswith("_json"):
            raw = d.pop(k)
            d[k[:-5]] = json.loads(raw) if raw else None
    return d


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur = conn().execute(sql, tuple(params))
    return [_row(r) for r in cur.fetchall()]  # type: ignore[misc]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cur = conn().execute(sql, tuple(params))
    return _row(cur.fetchone())


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """执行写操作，返回 lastrowid。写操作串行化，避免 SQLite 写锁冲突。"""
    with _write_lock:
        c = conn()
        cur = c.execute(sql, tuple(params))
        c.commit()
        return int(cur.lastrowid or 0)


def insert(table: str, data: dict[str, Any]) -> int:
    data = {k: (json.dumps(v, ensure_ascii=False, default=str) if k.endswith("_json") and v is not None else v)
            for k, v in data.items()}
    cols = ", ".join(data.keys())
    qs = ", ".join("?" for _ in data)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", data.values())


def update(table: str, row_id: int, data: dict[str, Any]) -> None:
    if not data:
        return
    data = {k: (json.dumps(v, ensure_ascii=False, default=str) if k.endswith("_json") and v is not None else v)
            for k, v in data.items()}
    sets = ", ".join(f"{k} = ?" for k in data)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*data.values(), row_id])
