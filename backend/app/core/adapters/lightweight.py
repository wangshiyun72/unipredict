"""轻量机器学习模型适配器（scikit-learn / XGBoost / LightGBM）。"""
from __future__ import annotations

from typing import Any

import numpy as np

from .base import FAMILY_LIGHTWEIGHT, ModelAdapter, register_adapter


class _SklearnAdapter(ModelAdapter):
    family = FAMILY_LIGHTWEIGHT

    def build(self) -> Any:  # pragma: no cover - 子类实现
        raise NotImplementedError

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_SklearnAdapter":
        self.model = self.build()
        self.model.fit(X, y)
        if self.task == "classification":
            self.n_classes_ = int(len(np.unique(y)))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict(X))

    def predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        if self.task == "classification" and hasattr(self.model, "predict_proba"):
            return np.asarray(self.model.predict_proba(X))
        return None


@register_adapter
class LinearAdapter(_SklearnAdapter):
    key = "linear"
    name = "线性模型（Ridge / Logistic）"
    description = "最简单、可解释性最强的基线模型，训练只需毫秒级。"
    quick_default = True
    param_spec = [
        {"name": "alpha", "label": "正则化强度", "type": "float", "default": 1.0, "min": 0.0001, "max": 1000},
    ]

    def build(self) -> Any:
        from sklearn.linear_model import LogisticRegression, Ridge

        if self.task == "regression":
            return Ridge(alpha=float(self.params["alpha"]))
        return LogisticRegression(C=1.0 / max(float(self.params["alpha"]), 1e-6), max_iter=2000)


@register_adapter
class RandomForestAdapter(_SklearnAdapter):
    key = "random_forest"
    name = "随机森林"
    description = "稳健的集成树模型，对异常值和特征尺度不敏感，小样本表现好。"
    quick_default = True
    param_spec = [
        {"name": "n_estimators", "label": "树的数量", "type": "int", "default": 300, "min": 10, "max": 2000},
        {"name": "max_depth", "label": "最大深度（0=不限制）", "type": "int", "default": 0, "min": 0, "max": 100},
        {"name": "min_samples_leaf", "label": "叶子最小样本数", "type": "int", "default": 1, "min": 1, "max": 50},
    ]

    def build(self) -> Any:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

        cls = RandomForestRegressor if self.task == "regression" else RandomForestClassifier
        depth = int(self.params["max_depth"]) or None
        return cls(
            n_estimators=int(self.params["n_estimators"]),
            max_depth=depth,
            min_samples_leaf=int(self.params["min_samples_leaf"]),
            n_jobs=-1,
            random_state=self.random_state,
        )


@register_adapter
class HistGBAdapter(_SklearnAdapter):
    key = "hist_gb"
    name = "梯度提升树（HistGB）"
    description = "scikit-learn 自带的直方图梯度提升，速度快、精度高，适合中等规模表格数据。"
    quick_default = True
    param_spec = [
        {"name": "learning_rate", "label": "学习率", "type": "float", "default": 0.05, "min": 0.001, "max": 1},
        {"name": "max_iter", "label": "迭代轮数", "type": "int", "default": 400, "min": 10, "max": 5000},
        {"name": "max_leaf_nodes", "label": "最大叶子数", "type": "int", "default": 31, "min": 2, "max": 255},
    ]

    def build(self) -> Any:
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

        cls = HistGradientBoostingRegressor if self.task == "regression" else HistGradientBoostingClassifier
        return cls(
            learning_rate=float(self.params["learning_rate"]),
            max_iter=int(self.params["max_iter"]),
            max_leaf_nodes=int(self.params["max_leaf_nodes"]),
            early_stopping=True,
            random_state=self.random_state,
        )


@register_adapter
class SVMAdapter(_SklearnAdapter):
    key = "svm"
    name = "支持向量机（SVR / SVC）"
    description = "适合样本量较小（几千以内）、特征维度不高的数据。"
    max_train_rows = 20000
    param_spec = [
        {"name": "C", "label": "惩罚系数 C", "type": "float", "default": 1.0, "min": 0.001, "max": 1000},
        {"name": "kernel", "label": "核函数", "type": "choice", "default": "rbf", "choices": ["rbf", "linear", "poly"]},
    ]

    def build(self) -> Any:
        from sklearn.svm import SVC, SVR

        if self.task == "regression":
            return SVR(C=float(self.params["C"]), kernel=self.params["kernel"])
        return SVC(C=float(self.params["C"]), kernel=self.params["kernel"], probability=True, random_state=self.random_state)


@register_adapter
class KNNAdapter(_SklearnAdapter):
    key = "knn"
    name = "K 近邻"
    description = "基于相似样本的预测，依赖归一化，适合样本分布均匀的数据。"
    param_spec = [
        {"name": "n_neighbors", "label": "近邻数 K", "type": "int", "default": 7, "min": 1, "max": 100},
        {"name": "weights", "label": "权重", "type": "choice", "default": "distance", "choices": ["uniform", "distance"]},
    ]

    def build(self) -> Any:
        from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor

        cls = KNeighborsRegressor if self.task == "regression" else KNeighborsClassifier
        return cls(n_neighbors=int(self.params["n_neighbors"]), weights=self.params["weights"])


@register_adapter
class XGBoostAdapter(_SklearnAdapter):
    key = "xgboost"
    name = "XGBoost"
    description = "经典高性能梯度提升库，可选 GPU 加速。"
    requires = ("xgboost",)
    param_spec = [
        {"name": "n_estimators", "label": "树的数量", "type": "int", "default": 500, "min": 10, "max": 5000},
        {"name": "learning_rate", "label": "学习率", "type": "float", "default": 0.05, "min": 0.001, "max": 1},
        {"name": "max_depth", "label": "最大深度", "type": "int", "default": 6, "min": 1, "max": 20},
    ]

    def build(self) -> Any:
        import xgboost as xgb

        cls = xgb.XGBRegressor if self.task == "regression" else xgb.XGBClassifier
        return cls(
            n_estimators=int(self.params["n_estimators"]),
            learning_rate=float(self.params["learning_rate"]),
            max_depth=int(self.params["max_depth"]),
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=self.random_state,
            n_jobs=-1,
        )


@register_adapter
class LightGBMAdapter(_SklearnAdapter):
    key = "lightgbm"
    name = "LightGBM"
    description = "微软开源的高效梯度提升框架，大数据量下速度快。"
    requires = ("lightgbm",)
    param_spec = [
        {"name": "n_estimators", "label": "树的数量", "type": "int", "default": 500, "min": 10, "max": 5000},
        {"name": "learning_rate", "label": "学习率", "type": "float", "default": 0.05, "min": 0.001, "max": 1},
        {"name": "num_leaves", "label": "叶子数", "type": "int", "default": 31, "min": 2, "max": 255},
    ]

    def build(self) -> Any:
        import lightgbm as lgb

        cls = lgb.LGBMRegressor if self.task == "regression" else lgb.LGBMClassifier
        return cls(
            n_estimators=int(self.params["n_estimators"]),
            learning_rate=float(self.params["learning_rate"]),
            num_leaves=int(self.params["num_leaves"]),
            random_state=self.random_state,
            verbose=-1,
        )
