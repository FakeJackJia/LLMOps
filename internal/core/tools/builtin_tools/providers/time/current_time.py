from datetime import datetime
from typing import Any
from langchain_core.tools import BaseTool

class CurrentTimeTool(BaseTool):
    """一个用于获取当前时间的工具"""
    name = "current_time"
    description = "一个用于获取当前时间的工具"

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

def current_time(**kwargs) -> BaseTool:
    """返回获取当前时间的LangChain工具"""
    return CurrentTimeTool()