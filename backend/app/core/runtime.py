"""运行时资源：计算设备选择与 GPU 并发锁。"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

from ..config import settings

_gpu_semaphore = threading.BoundedSemaphore(max(1, settings.GPU_CONCURRENCY))
_gpu_stats = {"active": 0, "waiting": 0}
_stats_lock = threading.Lock()


def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except Exception:
        return False


def cuda_available() -> bool:
    if settings.DEVICE == "cpu":
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def get_device() -> str:
    if settings.DEVICE in ("cpu", "cuda"):
        return "cuda" if settings.DEVICE == "cuda" and cuda_available() else "cpu"
    return "cuda" if cuda_available() else "cpu"


@contextmanager
def gpu_slot(enabled: bool = True) -> Iterator[None]:
    """占用一个 GPU 并发名额。8GB 显存默认同一时间只允许 1 个 GPU 任务，避免显存溢出。"""
    if not enabled or get_device() != "cuda":
        yield
        return
    with _stats_lock:
        _gpu_stats["waiting"] += 1
    _gpu_semaphore.acquire()
    with _stats_lock:
        _gpu_stats["waiting"] -= 1
        _gpu_stats["active"] += 1
    try:
        yield
    finally:
        with _stats_lock:
            _gpu_stats["active"] -= 1
        _gpu_semaphore.release()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass


def gpu_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "device": get_device(),
        "torch": torch_available(),
        "cuda": cuda_available(),
        "gpu_concurrency": settings.GPU_CONCURRENCY,
        "gpu_active": _gpu_stats["active"],
        "gpu_waiting": _gpu_stats["waiting"],
    }
    if info["cuda"]:
        try:
            import torch

            idx = torch.cuda.current_device()
            free, total = torch.cuda.mem_get_info(idx)
            info.update(
                {
                    "gpu_name": torch.cuda.get_device_name(idx),
                    "memory_total_mb": round(total / 1024**2),
                    "memory_used_mb": round((total - free) / 1024**2),
                }
            )
        except Exception as e:  # pragma: no cover
            info["gpu_error"] = str(e)
    return info
