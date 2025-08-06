from typing import Any
import importlib

def dynamic_import(module_name: str, symbol_name: str) -> Any:
    """动态导入特定模块下的特地功能"""
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)