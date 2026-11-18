"""模型接入示例插件：极端随机树（Extra Trees）。

这个文件演示"如何把一个新模型接入平台"：
1. 继承 ModelAdapter（或这里的 _SklearnAdapter 简化基类）
2. 填写 key / name / family / param_spec
3. 实现 fit / predict（/ predict_proba）
4. 加上 @register_adapter 装饰器，放到 plugins/ 目录下

重启后端后，该模型会自动出现在前端"模型训练"页面的模型列表中。
"""
from __future__ import annotations

from typing import Any

from ..base import FAMILY_LIGHTWEIGHT, register_adapter
from ..lightweight import _SklearnAdapter


@register_adapter
class ExtraTreesAdapter(_SklearnAdapter):
    key = "extra_trees"
    name = "极端随机树（插件示例）"
    family = FAMILY_LIGHTWEIGHT
    description = "通过插件机制接入的模型示例，演示新模型如何零改动接入平台。"
    param_spec = [
        {"name": "n_estimators", "label": "树的数量", "type": "int", "default": 300, "min": 10, "max": 2000},
    ]

    def build(self) -> Any:
        from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor

        cls = ExtraTreesRegressor if self.task == "regression" else ExtraTreesClassifier
        return cls(n_estimators=int(self.params["n_estimators"]), n_jobs=-1, random_state=self.random_state)
