"""通用基础模型适配器：TabPFN。

TabPFN（Hollmann et al., Nature 2025）是在海量合成表格数据上预训练的 Transformer 基础模型，
推理时把训练样本作为"上下文"输入，不需要针对具体任务做梯度训练，就能直接给出预测——
这就是项目里"通用模型"的含义：同一个预训练模型服务于不同学科的各种小样本表格预测任务。

本平台默认使用 TabPFN-2 权重（Prior Labs License，学术使用无需申请 token），
权重首次使用时会从 HuggingFace 下载，国内默认走 hf-mirror.com 镜像（见 config.HF_ENDPOINT）。
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ...config import settings
from ..runtime import get_device, gpu_slot
from .base import FAMILY_UNIVERSAL, ModelAdapter, register_adapter


@register_adapter
class TabPFNAdapter(ModelAdapter):
    key = "tabpfn"
    name = "TabPFN 通用表格基础模型"
    family = FAMILY_UNIVERSAL
    description = "预训练表格基础模型，无需针对任务训练即可直接预测，小样本（几千行以内）效果突出。"
    requires = ("tabpfn", "torch")
    uses_gpu = True
    quick_default = True
    max_train_rows = settings.TABPFN_MAX_TRAIN_ROWS
    param_spec = [
        {"name": "n_estimators", "label": "集成次数", "type": "int", "default": 4, "min": 1, "max": 16},
        {
            "name": "model_version",
            "label": "权重版本",
            "type": "choice",
            "default": "v2",
            "choices": ["v2", "default"],
            "help": "v2 为 Apache 许可；default 为当前 tabpfn 库默认版本（可能需要在 HuggingFace 接受许可）",
        },
    ]

    def _make_estimator(self) -> Any:
        from tabpfn import TabPFNClassifier, TabPFNRegressor

        cls = TabPFNRegressor if self.task == "regression" else TabPFNClassifier
        device = get_device()
        est = None
        if self.params.get("model_version", "v2") == "v2":
            try:
                from tabpfn.constants import ModelVersion

                est = cls.create_default_for_version(ModelVersion.V2)
            except (ImportError, AttributeError):
                est = None  # 旧版 tabpfn（2.0.x）默认就是 v2
        if est is None:
            est = cls()
        for k, v in {
            "device": device,
            "n_estimators": int(self.params["n_estimators"]),
            "ignore_pretraining_limits": True,
            "random_state": self.random_state,
        }.items():
            try:
                est.set_params(**{k: v})
            except Exception:
                pass
        return est

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TabPFNAdapter":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y)
        limit = self.max_train_rows or len(X)
        if len(X) > limit:
            # TabPFN 把训练集作为上下文，8GB 显存下限制上下文大小
            rng = np.random.default_rng(self.random_state)
            idx = rng.choice(len(X), size=limit, replace=False)
            X, y = X[idx], y[idx]
            self.subsampled_ = True
        if self.task == "classification":
            self.n_classes_ = int(len(np.unique(y)))
        self._X, self._y = X, y
        self._est = None
        self._ensure_fitted()
        return self

    def _ensure_fitted(self) -> None:
        if getattr(self, "_est", None) is None:
            with gpu_slot(get_device() == "cuda"):
                est = self._make_estimator()
                est.fit(self._X, self._y)
            self._est = est

    # 分块推理，控制 8GB 显存占用
    CHUNK = 2000

    def _chunked(self, fn_name: str, X: np.ndarray) -> np.ndarray:
        self._ensure_fitted()
        X = np.asarray(X, dtype=np.float32)
        outs = []
        with gpu_slot(get_device() == "cuda"):
            fn = getattr(self._est, fn_name)
            for start in range(0, len(X), self.CHUNK):
                outs.append(np.asarray(fn(X[start : start + self.CHUNK])))
        return np.concatenate(outs, axis=0) if outs else np.zeros((0,))

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._chunked("predict", X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        if self.task != "classification":
            return None
        return self._chunked("predict_proba", X)

    # 只保存上下文数据，不保存 PyTorch 对象；加载后首次预测时自动重建
    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["_est"] = None
        return state
