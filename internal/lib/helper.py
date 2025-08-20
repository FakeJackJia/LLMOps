from typing import Any
import importlib
from hashlib import sha256

def dynamic_import(module_name: str, symbol_name: str) -> Any:
    """动态导入特定模块下的特地功能"""
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)

def add_attribute(attr_name: str, attr_value: Any):
    """装饰器函数, 为特定的函数添加相应的属性, 第一个参数为属性名字, 第二个参数为属性值"""
    def decorator(func):
        setattr(func, attr_name, attr_value)
        return func

    return decorator

def generate_text_hash(text: str) -> str:
    """根据传递的文本计算对应的哈希值"""
    text = str(text) + "None"
    return sha256(text.encode()).hexdigest()