"""训练流程：一次训练任务 = 同一份数据上训练多个模型 → 统一评估 → 排行榜 → 选出最优模型。"""
from __future__ import annotations

import time
import traceback
from typing import Any, Callable

import pandas as pd
from sklearn.model_selection import train_test_split

from .adapters import ADAPTERS, get_adapter
from .evaluate import evaluate, permutation_importance
from .pipeline import TrainedPipeline
from .preprocess import infer_task

ProgressFn = Callable[[float, str], None]
CancelFn = Callable[[], bool]


class TrainingCancelled(Exception):
    pass


def default_quick_models(task: str) -> list[str]:
    keys = []
    for key, cls in ADAPTERS.items():
        ok, _ = cls.availability()
        if ok and cls.quick_default and task in cls.tasks:
            keys.append(key)
    return keys


def prepare_xy(df: pd.DataFrame, target: str, max_rows: int | None = None) -> tuple[pd.DataFrame, pd.Series]:
    if target not in df.columns:
        raise ValueError(f"数据中没有目标列：{target}")
    df = df[df[target].notna()].reset_index(drop=True)
    if len(df) < 10:
        raise ValueError("有效样本少于 10 条，无法训练")
    if max_rows and len(df) > max_rows:
        df = df.sample(max_rows, random_state=42).reset_index(drop=True)
    y = df[target]
    X = df.drop(columns=[target])
    return X, y


def run_training(
    df: pd.DataFrame,
    target: str,
    model_keys: list[str],
    task: str | None = None,
    params: dict[str, dict[str, Any]] | None = None,
    scaler: str = "auto",
    test_size: float = 0.2,
    seed: int = 42,
    max_rows: int | None = None,
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
) -> dict[str, Any]:
    progress = progress or (lambda p, m: None)
    cancelled = cancelled or (lambda: False)
    params = params or {}
    X, y = prepare_xy(df, target, max_rows)
    task = task or infer_task(y)
    if task == "classification":
        counts = y.astype(str).value_counts()
        if counts.min() < 2:
            rare = counts[counts < 2].index.tolist()
            raise ValueError(f"类别 {rare[:5]} 只有 1 个样本，无法划分训练/测试集")
    if not model_keys:
        model_keys = default_quick_models(task)
    if not model_keys:
        raise ValueError("没有可用的模型，请检查依赖安装情况")

    stratify = y.astype(str) if task == "classification" else None
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=stratify)
    X_tr, X_te = X_tr.reset_index(drop=True), X_te.reset_index(drop=True)
    y_tr, y_te = y_tr.reset_index(drop=True), y_te.reset_index(drop=True)
    progress(0.03, f"数据划分完成：训练集 {len(X_tr)} 条，测试集 {len(X_te)} 条，任务类型：{'回归' if task == 'regression' else '分类'}")

    results: list[dict[str, Any]] = []
    n = len(model_keys)
    for i, key in enumerate(model_keys):
        if cancelled():
            raise TrainingCancelled()
        base = 0.05 + 0.9 * i / n
        item: dict[str, Any] = {"adapter": key, "status": "failed"}
        try:
            cls = get_adapter(key)
            item.update({"name": cls.name, "family": cls.family})
            ok, reason = cls.availability()
            if not ok:
                raise RuntimeError(reason)
            if task not in cls.tasks:
                raise RuntimeError(f"不支持{task}任务")
            progress(base, f"[{i + 1}/{n}] 正在训练 {cls.name} ...")
            t0 = time.perf_counter()
            pipe = TrainedPipeline(target, task, key, params.get(key), scaler=scaler, random_state=seed)
            pipe.fit(X_tr, y_tr)
            train_s = time.perf_counter() - t0
            progress(base + 0.5 * 0.9 / n, f"[{i + 1}/{n}] 正在评估 {cls.name} ...")
            ev = evaluate(pipe, X_te, y_te)
            t1 = time.perf_counter()
            imp = permutation_importance(pipe, X_te, y_te, n_repeats=2 if cls.uses_gpu else 3,
                                         max_rows=200 if cls.uses_gpu else 500)
            item.update(
                {
                    "status": "succeeded",
                    "metrics": ev["metrics"],
                    "charts": ev["charts"],
                    "importance": imp,
                    "train_seconds": round(train_s, 3),
                    "explain_seconds": round(time.perf_counter() - t1, 3),
                    "pipeline": pipe,
                }
            )
        except TrainingCancelled:
            raise
        except Exception as e:  # 单个模型失败不影响其他模型
            item["error"] = f"{type(e).__name__}: {e}"
            item["traceback"] = traceback.format_exc(limit=3)
        results.append(item)

    ok_results = [r for r in results if r["status"] == "succeeded"]
    if not ok_results:
        errors = "; ".join(f"{r.get('name', r['adapter'])}: {r.get('error')}" for r in results)
        raise RuntimeError(f"所有模型训练失败：{errors}")
    ok_results.sort(key=lambda r: r["metrics"].get("primary_value") or -1e9, reverse=True)
    best = ok_results[0]
    best["is_best"] = True
    progress(0.97, f"训练完成，最优模型：{best['name']}（{best['metrics']['primary_label']} = {best['metrics']['primary_value']}）")
    return {
        "task": task,
        "target": target,
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "results": results,
        "best_adapter": best["adapter"],
    }
