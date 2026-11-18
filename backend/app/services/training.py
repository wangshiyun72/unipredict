"""训练服务：提交训练任务 → 后台训练 → 把每个模型登记到模型仓库。"""
from __future__ import annotations

from typing import Any

from .. import db
from ..config import settings
from ..core.adapters import get_adapter
from ..tasks import task_manager
from .datasets import load_dataframe
from .model_store import save_pipeline


def submit_training(user: dict[str, Any], ds: dict[str, Any], target: str, models: list[str],
                    task: str | None = None, params: dict[str, dict[str, Any]] | None = None,
                    scaler: str = "auto", test_size: float = 0.2, drop_columns: list[str] | None = None,
                    auto_publish: bool = True, name_prefix: str | None = None) -> int:
    job_params = {
        "dataset_id": ds["id"],
        "dataset_name": ds["name"],
        "target": target,
        "models": models,
        "task": task,
        "params": params or {},
        "scaler": scaler,
        "test_size": test_size,
        "drop_columns": drop_columns or [],
    }

    def run(job_id: int, progress, cancelled) -> dict[str, Any]:
        from ..core.trainer import run_training

        progress(0.01, f"读取数据集「{ds['name']}」")
        df = load_dataframe(ds)
        if drop_columns:
            df = df.drop(columns=[c for c in drop_columns if c in df.columns and c != target])
        out = run_training(
            df, target, models, task=task, params=params, scaler=scaler, test_size=test_size,
            max_rows=settings.MAX_TRAIN_ROWS, progress=progress, cancelled=cancelled,
        )
        leaderboard = []
        best_model_id = None
        for r in out["results"]:
            entry = {k: r.get(k) for k in ("adapter", "name", "family", "status", "error", "train_seconds")}
            if r["status"] == "succeeded":
                pipe = r["pipeline"]
                path = save_pipeline(pipe)
                is_best = bool(r.get("is_best"))
                summary = pipe.summary()
                model_id = db.insert(
                    "models",
                    {
                        "owner_id": user["id"],
                        "job_id": job_id,
                        "dataset_id": ds["id"],
                        "name": f"{name_prefix or ds['name']}-{r['name']}",
                        "adapter": r["adapter"],
                        "family": r.get("family"),
                        "task": out["task"],
                        "target": target,
                        "metrics_json": r["metrics"],
                        "detail_json": {
                            "charts": r["charts"],
                            "importance": r["importance"],
                            "preprocessing": summary["preprocessing"],
                            "params": summary["params"],
                            "classes": summary["classes"],
                            "history": summary.get("history"),
                            "smiles_columns": summary.get("smiles_columns"),
                            "baseline": pipe.baseline,
                            "train_seconds": r["train_seconds"],
                            "n_train": out["n_train"],
                            "n_test": out["n_test"],
                        },
                        "input_schema_json": pipe.input_schema,
                        "path": path,
                        "status": "published" if (is_best and auto_publish) else "ready",
                        "visibility": ds.get("visibility", "private"),
                        "is_best": 1 if is_best else 0,
                        "created_at": db.now(),
                    },
                )
                entry.update({"model_id": model_id, "metrics": r["metrics"], "is_best": is_best})
                if is_best:
                    best_model_id = model_id
            leaderboard.append(entry)
        progress(0.99, "模型已登记到模型仓库")
        return {
            "task": out["task"],
            "target": target,
            "n_train": out["n_train"],
            "n_test": out["n_test"],
            "leaderboard": leaderboard,
            "best_model_id": best_model_id,
        }

    # 参数检查放在提交前，尽早报错
    for key in models:
        get_adapter(key)
    return task_manager.submit(user["id"], "train", job_params, run, dataset_id=ds["id"])
