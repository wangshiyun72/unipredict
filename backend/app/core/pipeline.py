"""预测流水线：把"特征化 → 自动归一化 → 模型适配器"串成一个整体。

训练完成后整个流水线被保存成一个文件，部署时加载即可对原始表格数据直接预测，
调用方（网页或外部终端）不需要关心预处理细节。
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from .adapters import ModelAdapter, get_adapter
from .featurize import SmilesFeaturizer
from .preprocess import AutoPreprocessor


class BasePipeline:
    task: str = "regression"
    target: str = ""
    classes: list[str] | None = None
    adapter: ModelAdapter
    input_schema: list[dict[str, Any]] = []
    baseline: dict[str, Any] = {}

    # 子类实现：原始 DataFrame → (预测值数组, 概率矩阵或 None)
    def _raw_predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray | None]:  # pragma: no cover
        raise NotImplementedError

    @property
    def feature_names(self) -> list[str]:
        return [c["name"] for c in self.input_schema]

    def predict_df(self, df: pd.DataFrame) -> dict[str, Any]:
        t0 = time.perf_counter()
        pred, proba = self._raw_predict(df)
        result: dict[str, Any] = {"task": self.task, "target": self.target}
        if self.task == "classification":
            labels = self.classes or []
            result["predictions"] = [labels[int(i)] if labels and 0 <= int(i) < len(labels) else str(i) for i in pred]
            if proba is not None:
                names = labels if labels and len(labels) == proba.shape[1] else [str(i) for i in range(proba.shape[1])]
                result["probabilities"] = [
                    {n: round(float(p), 6) for n, p in zip(names, row)} for row in proba
                ]
        else:
            result["predictions"] = [None if not np.isfinite(v) else round(float(v), 6) for v in pred]
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return result

    # ------------------------------------------------------------------
    # 局部可解释性：特征遮挡法（model-agnostic）
    # ------------------------------------------------------------------
    def _score(self, df: pd.DataFrame, target_class: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        pred, proba = self._raw_predict(df)
        if self.task == "classification":
            if proba is None:
                return pred, pred.astype(float)
            cls_idx = target_class if target_class is not None else pred.astype(int)
            cls_idx = np.clip(cls_idx.astype(int), 0, proba.shape[1] - 1)
            return pred, proba[np.arange(len(proba)), cls_idx]
        return pred, pred.astype(float)

    def explain_local(self, df: pd.DataFrame, max_rows: int = 5) -> list[dict[str, Any]]:
        """对每条样本：依次把某个特征替换成训练集的"典型值"（中位数/众数），
        观察预测值的变化。变化量即该特征对这条预测的贡献（正=推高，负=拉低）。"""
        if not self.baseline:
            return []
        df = df.head(max_rows).reset_index(drop=True)
        features = [f for f in self.feature_names if f in df.columns and f in self.baseline]
        explanations = []
        for i in range(len(df)):
            row = df.iloc[[i]]
            variants = [row]
            for f in features:
                r = row.copy()
                r[f] = self.baseline[f]
                variants.append(r)
            batch = pd.concat(variants, ignore_index=True)
            pred, _ = self._raw_predict(batch.iloc[[0]])
            target_class = np.full(len(batch), int(pred[0])) if self.task == "classification" else None
            _, scores = self._score(batch, target_class)
            base_score = float(scores[0])
            contribs = [
                {
                    "feature": f,
                    "value": _jsonable(row.iloc[0][f]),
                    "baseline": _jsonable(self.baseline[f]),
                    "contribution": round(base_score - float(scores[j + 1]), 6),
                }
                for j, f in enumerate(features)
            ]
            contribs.sort(key=lambda c: abs(c["contribution"]), reverse=True)
            explanations.append(
                {
                    "row": i,
                    "score": round(base_score, 6),
                    "score_meaning": "预测类别的概率" if self.task == "classification" else "预测值",
                    "contributions": contribs,
                }
            )
        return explanations


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


class TrainedPipeline(BasePipeline):
    """平台内训练得到的流水线。"""

    def __init__(self, target: str, task: str, adapter_key: str, params: dict[str, Any] | None = None,
                 scaler: str = "auto", random_state: int = 42):
        self.target = target
        self.task = task
        self.adapter_key = adapter_key
        self.params = params or {}
        self.scaler = scaler
        self.random_state = random_state
        self.featurizer = SmilesFeaturizer()
        self.preprocessor = AutoPreprocessor(scaler=scaler)
        self.classes: list[str] | None = None
        self.train_seconds = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "TrainedPipeline":
        t0 = time.perf_counter()
        X = X.copy()
        X.columns = [str(c) for c in X.columns]
        self.preprocessor.analyze(X)
        self.input_schema = self.preprocessor.input_schema
        self.featurizer.fit(X, self.preprocessor.smiles_cols)
        X_clean = self.preprocessor._coerce(X)
        X_feat = self.featurizer.transform(X_clean)
        extra = [c for col in self.preprocessor.smiles_cols for c in self.featurizer.output_columns(col)]
        self.preprocessor.fit(X_feat, extra)
        Xm = self.preprocessor.transform(X_feat)

        if self.task == "classification":
            y_str = y.astype(str)
            self.classes = sorted(y_str.unique().tolist())
            mapping = {c: i for i, c in enumerate(self.classes)}
            y_arr = y_str.map(mapping).to_numpy(dtype=np.int64)
        else:
            y_arr = pd.to_numeric(y, errors="coerce").to_numpy(dtype=np.float64)

        adapter_cls = get_adapter(self.adapter_key)
        self.adapter = adapter_cls(self.task, self.params, random_state=self.random_state)
        self.adapter.fit(Xm, y_arr)
        self.params = self.adapter.params

        # 局部解释用的基线：数值列取中位数，其他列取众数
        self.baseline = {}
        for col in self.feature_names:
            s = X_clean[col]
            if self.preprocessor.column_types.get(col) == "numeric":
                self.baseline[col] = _jsonable(pd.to_numeric(s, errors="coerce").median())
            else:
                mode = s.dropna().mode()
                self.baseline[col] = str(mode.iloc[0]) if len(mode) else ""
        self.train_seconds = round(time.perf_counter() - t0, 3)
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        df = df.copy()
        df.columns = [str(c) for c in df.columns]
        X_clean = self.preprocessor._coerce(df)
        X_feat = self.featurizer.transform(X_clean)
        return self.preprocessor.transform(X_feat)

    def _raw_predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray | None]:
        Xm = self.transform(df)
        pred = self.adapter.predict(Xm)
        proba = self.adapter.predict_proba(Xm) if self.task == "classification" else None
        return np.asarray(pred), proba

    def summary(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_key,
            "params": self.params,
            "preprocessing": self.preprocessor.summary(),
            "smiles_columns": self.featurizer.smiles_columns,
            "classes": self.classes,
            "train_seconds": self.train_seconds,
            "history": getattr(self.adapter, "history", None),
        }


class ExternalPipeline(BasePipeline):
    """外部导入模型：输入特征按指定顺序直接送入模型（预处理由外部模型自己负责）。"""

    def __init__(self, adapter: ModelAdapter, features: list[str], task: str, target: str,
                 classes: list[str] | None = None, sample: pd.DataFrame | None = None):
        self.adapter = adapter
        self.task = task
        self.target = target
        self.features = features
        self.classes = classes
        self.input_schema = []
        self.baseline = {}
        for f in features:
            item: dict[str, Any] = {"name": f, "type": "numeric", "default": 0.0}
            if sample is not None and f in sample.columns:
                s = pd.to_numeric(sample[f], errors="coerce")
                item.update({"min": _jsonable(s.min()), "max": _jsonable(s.max()), "default": _jsonable(s.median())})
                self.baseline[f] = item["default"]
            self.input_schema.append(item)

    def _raw_predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray | None]:
        df = df.copy()
        df.columns = [str(c) for c in df.columns]
        missing = [f for f in self.features if f not in df.columns]
        if missing:
            raise ValueError(f"输入数据缺少字段：{missing}")
        X = df[self.features].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(dtype=np.float32)
        if self.adapter.key == "external_pickle":
            X_in: Any = pd.DataFrame(X, columns=self.features)
        else:
            X_in = X
        pred = np.asarray(self.adapter.predict(X_in))
        proba = self.adapter.predict_proba(X_in) if self.task == "classification" else None
        if self.task == "classification" and self.classes and pred.dtype.kind not in "iu":
            # sklearn 模型直接返回原始类别名 → 映射回索引
            idx = {c: i for i, c in enumerate(self.classes)}
            pred = np.array([idx.get(str(p), 0) for p in pred])
        return pred, proba

    def summary(self) -> dict[str, Any]:
        return {"adapter": self.adapter.key, "features": self.features, "classes": self.classes, "external": True}
