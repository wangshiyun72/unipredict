"""导入所有内置适配器，完成注册；并自动加载 plugins/ 目录下的自定义适配器。"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from . import deep, external, lightweight, universal  # noqa: F401  注册内置模型
from .base import ADAPTERS, FAMILY_LABELS, ModelAdapter, get_adapter, list_adapters, register_adapter

logger = logging.getLogger(__name__)


def load_plugins() -> list[str]:
    """自动导入 app/core/adapters/plugins/ 下的 .py 文件。新模型放进去即可被平台识别。"""
    loaded = []
    plugin_dir = Path(__file__).parent / "plugins"
    if not plugin_dir.exists():
        return loaded
    for mod in pkgutil.iter_modules([str(plugin_dir)]):
        name = f"{__name__}.plugins.{mod.name}"
        try:
            importlib.import_module(name)
            loaded.append(mod.name)
        except Exception as e:  # 插件出错不影响平台启动
            logger.warning("加载模型插件 %s 失败：%s", mod.name, e)
    return loaded


__all__ = [
    "ADAPTERS",
    "FAMILY_LABELS",
    "ModelAdapter",
    "get_adapter",
    "list_adapters",
    "register_adapter",
    "load_plugins",
]
