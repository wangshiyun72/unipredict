"""外部模型接入：把在平台之外训练好的模型导入平台，统一对外提供预测 API。

支持两种格式：
- ONNX（推荐）：跨框架标准格式，PyTorch / TensorFlow / scikit-learn 都可以导出；安全，不执行任意代码。
- joblib / pickle：scikit-learn 模型或 Pipeline。pickle 文件加载时可以执行任意代码，因此仅管理员可导入。

导入时需要提供输入特征列表（顺序与模型训练时一致）和任务类型。
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .base import FAMILY_EXTERNAL, ModelAdapter, register_adapter


@register_adapter
class OnnxAdapter(ModelAdapter):
    key = "external_onnx"
    name = "外部 ONNX 模型"
    family = FAMILY_EXTERNAL
    description = "导入 ONNX 格式的已训练模型（PyTorch/TensorFlow/sklearn 均可导出）。"
    requires = ("onnxruntime",)

    def load_bytes(self, data: bytes) -> "OnnxAdapter":
        self.model_bytes = data
        self._sess = None
        sess = self._session()
        self.input_name = sess.get_inputs()[0].name
        self.output_names = [o.name for o in sess.get_outputs()]
        return self

    def _session(self) -> Any:
        if getattr(self, "_sess", None) is None:
            import onnxruntime as ort

            self._sess = ort.InferenceSession(self.model_bytes, providers=["CPUExecutionProvider"])
        return self._sess

    def fit(self, X: np.ndarray, y: np.ndarray) -> "OnnxAdapter":
        raise RuntimeError("外部模型已经训练完成，不支持在平台内重新训练")

    def _run(self, X: np.ndarray) -> list[Any]:
        sess = self._session()
        return sess.run(None, {self.input_name: np.asarray(X, dtype=np.float32)})

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = np.asarray(self._run(X)[0])
        if self.task == "regression":
            return out.reshape(len(X), -1)[:, 0]
        if out.ndim == 2 and out.shape[1] > 1:  # 输出的是 logits / 概率
            return out.argmax(axis=1)
        return out.reshape(-1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        if self.task != "classification":
            return None
        outs = self._run(X)
        for o in outs[1:] + outs[:1]:
            if isinstance(o, list) and o and isinstance(o[0], dict):  # skl2onnx 的 ZipMap 输出
                keys = sorted(o[0].keys())
                return np.array([[row[k] for k in keys] for row in o], dtype=float)
            arr = np.asarray(o)
            if arr.ndim == 2 and arr.shape[1] > 1:
                if np.all(arr >= 0) and np.allclose(arr.sum(axis=1), 1, atol=1e-3):
                    return arr
                e = np.exp(arr - arr.max(axis=1, keepdims=True))
                return e / e.sum(axis=1, keepdims=True)
        return None

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["_sess"] = None
        return state


@register_adapter
class PickleAdapter(ModelAdapter):
    key = "external_pickle"
    name = "外部 scikit-learn 模型"
    family = FAMILY_EXTERNAL
    description = "导入 joblib/pickle 保存的 scikit-learn 模型或 Pipeline（仅管理员，需确认来源可信）。"

    def load_object(self, obj: Any) -> "PickleAdapter":
        if not hasattr(obj, "predict"):
            raise ValueError("导入的对象没有 predict 方法，不是有效的模型")
        self.model = obj
        classes = getattr(obj, "classes_", None)
        self.classes_ = [str(c) for c in classes] if classes is not None else None
        return self

    def fit(self, X: np.ndarray, y: np.ndarray) -> "PickleAdapter":
        raise RuntimeError("外部模型已经训练完成，不支持在平台内重新训练")

    def predict(self, X: Any) -> np.ndarray:
        return np.asarray(self.model.predict(X))

    def predict_proba(self, X: Any) -> np.ndarray | None:
        if self.task == "classification" and hasattr(self.model, "predict_proba"):
            return np.asarray(self.model.predict_proba(X))
        return None
