"""并发访问控制。

三层控制：
1. 限流（TokenBucketLimiter）：按身份（用户 / API Key / IP）的令牌桶，限制每分钟请求数，超出返回 429。
2. 预测并发闸门（PredictGate）：全局同时执行的预测请求数上限，排队超时返回 503，保护服务器不被压垮。
3. 训练任务队列（见 tasks.py）：线程池 + 每用户任务数上限 + 队列总长度上限。
另外 GPU 模型的训练和推理还要经过 GPU 并发锁（core/runtime.py）。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .config import settings


@dataclass
class _Bucket:
    capacity: float
    tokens: float
    refill_per_sec: float
    updated: float = field(default_factory=time.monotonic)


class TokenBucketLimiter:
    """令牌桶：容量 = 每分钟限额，按速率持续补充，允许短时突发。"""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self.rejected = 0
        self.allowed = 0

    def check(self, identity: str, per_minute: int) -> tuple[bool, int, float]:
        """返回 (是否放行, 剩余令牌, 建议重试等待秒数)。"""
        per_minute = max(1, int(per_minute))
        now = time.monotonic()
        with self._lock:
            b = self._buckets.get(identity)
            if b is None or b.capacity != per_minute:
                b = _Bucket(capacity=per_minute, tokens=per_minute, refill_per_sec=per_minute / 60.0)
                self._buckets[identity] = b
            b.tokens = min(b.capacity, b.tokens + (now - b.updated) * b.refill_per_sec)
            b.updated = now
            if b.tokens >= 1:
                b.tokens -= 1
                self.allowed += 1
                return True, int(b.tokens), 0.0
            self.rejected += 1
            wait = (1 - b.tokens) / b.refill_per_sec
            return False, 0, wait


class PredictGate:
    """全局预测并发闸门：信号量 + 排队超时 + 实时统计。"""

    def __init__(self, limit: int, timeout: float) -> None:
        self.limit = limit
        self.timeout = timeout
        self._sem = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self.active = 0
        self.waiting = 0
        self.peak_active = 0
        self.rejected = 0
        self.completed = 0
        self._latencies: deque[float] = deque(maxlen=500)

    def acquire(self) -> bool:
        with self._lock:
            self.waiting += 1
        ok = self._sem.acquire(timeout=self.timeout)
        with self._lock:
            self.waiting -= 1
            if ok:
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
            else:
                self.rejected += 1
        return ok

    def release(self, latency_ms: float | None = None) -> None:
        with self._lock:
            self.active -= 1
            self.completed += 1
            if latency_ms is not None:
                self._latencies.append(latency_ms)
        self._sem.release()

    def stats(self) -> dict[str, Any]:
        lat = sorted(self._latencies)

        def pct(p: float) -> float | None:
            if not lat:
                return None
            return round(lat[min(len(lat) - 1, int(p * len(lat)))], 2)

        return {
            "limit": self.limit,
            "active": self.active,
            "waiting": self.waiting,
            "peak_active": self.peak_active,
            "rejected": self.rejected,
            "completed": self.completed,
            "latency_p50_ms": pct(0.5),
            "latency_p95_ms": pct(0.95),
        }


limiter = TokenBucketLimiter()
predict_gate = PredictGate(settings.PREDICT_CONCURRENCY, settings.PREDICT_QUEUE_TIMEOUT)
