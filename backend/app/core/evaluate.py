"""模型评估与全局可解释性。

- 评估指标：回归 R² / MAE / RMSE；分类 准确率 / F1 / AUC
- 可视化数据：预测值-真实值散点、残差分布、混淆矩阵
- 全局可解释性：置换重要性（Permutation Importance）——在原始特征层面打乱某一列，
  看模型指标下降多少；与模型类型无关，所以通用模型、深度模型、轻量模型都能统一解释。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn import metrics as skm

from .pipeline import BasePipeline


def _r(x: float, n: int = 6) -> float | None:
    try:
        v = float(x)
        return round(v, n) if np.isfinite(v) else None
    except Exception:
        return None


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    return {
        "r2": _r(skm.r2_score(y_true, y_pred)),
        "mae": _r(skm.mean_absolute_error(y_true, y_pred)),
        "rmse": _r(np.sqrt(skm.mean_squared_error(y_true, y_pred))),
    }


def classification_metrics(y_true: list[str], y_pred: list[str], proba: list[dict[str, float]] | None,
                           classes: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "accuracy": _r(skm.accuracy_score(y_true, y_pred)),
        "f1_macro": _r(skm.f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "precision_macro": _r(skm.precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": _r(skm.recall_score(y_true, y_pred, average="macro", zero_division=0)),
    }
    if proba:
        try:
            P = np.array([[p.get(c, 0.0) for c in classes] for p in proba])
            if len(classes) == 2:
                out["auc"] = _r(skm.roc_auc_score([1 if t == classes[1] else 0 for t in y_true], P[:, 1]))
            elif len(set(y_true)) == len(classes):
                out["auc"] = _r(skm.roc_auc_score(y_true, P, multi_class="ovr", labels=classes))
        except Exception:
            pass
    return out


PRIMARY_METRIC = {"regression": ("r2", "R²"), "classification": ("f1_macro", "F1（宏平均）")}


def evaluate(pipeline: BasePipeline, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
    res = pipeline.predict_df(X)
    charts: dict[str, Any] = {}
    if pipeline.task == "regression":
        y_true = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float)
        y_pred = np.array([np.nan if p is None else p for p in res["predictions"]], dtype=float)
        mask = np.isfinite(y_true) & np.isfinite(y_pred)
        m = regression_metrics(y_true[mask], y_pred[mask])
        idx = np.where(mask)[0]
        if len(idx) > 400:
            idx = np.random.default_rng(0).choice(idx, 400, replace=False)
        charts["scatter"] = [[_r(y_true[i], 4), _r(y_pred[i], 4)] for i in idx]
        resid = (y_pred[mask] - y_true[mask])
        if len(resid):
            counts, edges = np.histogram(resid, bins=20)
            charts["residual_hist"] = {
                "bins": [_r((edges[i] + edges[i + 1]) / 2, 4) for i in range(len(counts))],
                "counts": counts.tolist(),
            }
    else:
        classes = pipeline.classes or sorted(set(map(str, y)))
        y_true = [str(v) for v in y]
        y_pred = [str(v) for v in res["predictions"]]
        m = classification_metrics(y_true, y_pred, res.get("probabilities"), classes)
        cm = skm.confusion_matrix(y_true, y_pred, labels=classes)
        charts["confusion_matrix"] = {"labels": classes, "matrix": cm.tolist()}
    key, label = PRIMARY_METRIC[pipeline.task]
    m["primary"] = key
    m["primary_label"] = label
    m["primary_value"] = m.get(key)
    m["n_test"] = int(len(X))
    return {"metrics": m, "charts": charts}


def permutation_importance(pipeline: BasePipeline, X: pd.DataFrame, y: pd.Series,
                           n_repeats: int = 3, max_rows: int = 500, seed: int = 0) -> list[dict[str, Any]]:
    """原始特征层面的置换重要性。返回按重要性降序排列的列表。"""
    rng = np.random.default_rng(seed)
    if len(X) > max_rows:
        idx = rng.choice(len(X), max_rows, replace=False)
        X, y = X.iloc[idx].reset_index(drop=True), y.iloc[idx].reset_index(drop=True)
    else:
        X, y = X.reset_index(drop=True), y.reset_index(drop=True)

    def score(Xs: pd.DataFrame) -> float:
        res = pipeline.predict_df(Xs)
        if pipeline.task == "regression":
            yp = np.array([np.nan if p is None else p for p in res["predictions"]], dtype=float)
            yt = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float)
            mask = np.isfinite(yp) & np.isfinite(yt)
            return float(skm.r2_score(yt[mask], yp[mask])) if mask.sum() > 1 else 0.0
        return float(skm.accuracy_score([str(v) for v in y], [str(v) for v in res["predictions"]]))

    base = score(X)
    features = [f for f in pipeline.feature_names if f in X.columns]
    # 一次性把所有打乱版本拼起来批量预测，减少模型调用次数（对 GPU 模型更友好）
    blocks, keys = [], []
    for f in features:
        for r in range(n_repeats):
            Xp = X.copy()
            Xp[f] = rng.permutation(Xp[f].to_numpy())
            blocks.append(Xp)
            keys.append(f)
    if not blocks:
        return []
    big = pd.concat(blocks, ignore_index=True)
    res = pipeline.predict_df(big)
    preds = res["predictions"]
    n = len(X)
    drops: dict[str, list[float]] = {f: [] for f in features}
    yt_num = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float) if pipeline.task == "regression" else None
    yt_str = [str(v) for v in y]
    for b, f in enumerate(keys):
        part = preds[b * n : (b + 1) * n]
        if pipeline.task == "regression":
            yp = np.array([np.nan if p is None else p for p in part], dtype=float)
            mask = np.isfinite(yp) & np.isfinite(yt_num)
            s = float(skm.r2_score(yt_num[mask], yp[mask])) if mask.sum() > 1 else 0.0
        else:
            s = float(skm.accuracy_score(yt_str, [str(v) for v in part]))
        drops[f].append(base - s)
    out = [
        {"feature": f, "importance": _r(np.mean(v)), "std": _r(np.std(v))}
        for f, v in drops.items()
    ]
    out.sort(key=lambda d: d["importance"] or 0, reverse=True)
    return out
