"""模型适配器（Model Adapter）。

平台里的所有模型——通用基础模型、轻量机器学习模型、深度学习模型、用户导入的外部模型——
都通过同一个适配器接口接入：

    fit(X, y)          训练（输入已经过自动归一化的数值矩阵）
    predict(X)         预测
    predict_proba(X)   分类概率（分类任务）

平台的其余部分（训练任务、预测 API、可解释性、可视化）只和这个接口打交道，
所以接入一个新模型只需要写一个适配器类并用 @register_adapter 注册。
详见 docs/模型接入指南.md。
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import numpy as np

# family 取值
FAMILY_UNIVERSAL = "universal"  # 通用（预训练基础）模型
FAMILY_LIGHTWEIGHT = "lightweight"  # 轻量机器学习模型
FAMILY_DEEP = "deep"  # 深度学习模型
FAMILY_EXTERNAL = "external"  # 外部导入模型

FAMILY_LABELS = {
    FAMILY_UNIVERSAL: "通用基础模型",
    FAMILY_LIGHTWEIGHT: "轻量模型",
    FAMILY_DEEP: "深度学习模型",
    FAMILY_EXTERNAL: "外部接入模型",
}


class ModelAdapter(ABC):
    key: ClassVar[str] = ""
    name: ClassVar[str] = ""
    family: ClassVar[str] = FAMILY_LIGHTWEIGHT
    description: ClassVar[str] = ""
    tasks: ClassVar[tuple[str, ...]] = ("classification", "regression")
    requires: ClassVar[tuple[str, ...]] = ()  # 依赖的 Python 包（import 名）
    uses_gpu: ClassVar[bool] = False
    max_train_rows: ClassVar[int | None] = None
    # 参数说明：供前端自动生成参数表单
    param_spec: ClassVar[list[dict[str, Any]]] = []
    # 是否参与"一键预测"的默认模型组合
    quick_default: ClassVar[bool] = False

    def __init__(self, task: str, params: dict[str, Any] | None = None, random_state: int = 42):
        if task not in self.tasks:
            raise ValueError(f"{self.name} 不支持 {task} 任务")
        self.task = task
        self.random_state = random_state
        self.params = self.default_params()
        if params:
            self.params.update({k: v for k, v in params.items() if k in self.params})
        self.n_classes_: int | None = None

    # ------------------------------------------------------------------
    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {p["name"]: p["default"] for p in cls.param_spec}

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        missing = []
        for pkg in cls.requires:
            try:
                importlib.import_module(pkg)
            except Exception:
                missing.append(pkg)
        if missing:
            return False, f"未安装依赖：{', '.join(missing)}"
        return True, "可用"

    @classmethod
    def info(cls) -> dict[str, Any]:
        ok, reason = cls.availability()
        return {
            "key": cls.key,
            "name": cls.name,
            "family": cls.family,
            "family_label": FAMILY_LABELS.get(cls.family, cls.family),
            "description": cls.description,
            "tasks": list(cls.tasks),
            "uses_gpu": cls.uses_gpu,
            "available": ok,
            "availability": reason,
            "params": cls.param_spec,
            "quick_default": cls.quick_default,
            "max_train_rows": cls.max_train_rows,
        }

    # ------------------------------------------------------------------
    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "ModelAdapter": ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray: ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        return None


# ----------------------------------------------------------------------
# 注册表
# ----------------------------------------------------------------------
ADAPTERS: dict[str, type[ModelAdapter]] = {}


def register_adapter(cls: type[ModelAdapter]) -> type[ModelAdapter]:
    if not cls.key:
        raise ValueError("适配器必须定义 key")
    ADAPTERS[cls.key] = cls
    return cls


def get_adapter(key: str) -> type[ModelAdapter]:
    if key not in ADAPTERS:
        raise KeyError(f"未知模型：{key}")
    return ADAPTERS[key]


def list_adapters(include_external: bool = False) -> list[dict[str, Any]]:
    order = {FAMILY_UNIVERSAL: 0, FAMILY_DEEP: 1, FAMILY_LIGHTWEIGHT: 2, FAMILY_EXTERNAL: 3}
    items = [
        cls.info()
        for cls in ADAPTERS.values()
        if include_external or cls.family != FAMILY_EXTERNAL
    ]
    return sorted(items, key=lambda x: (order.get(x["family"], 9), x["name"]))
