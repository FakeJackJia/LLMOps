from langchain_community.tools import WikipediaQueryRun
from langchain_core.tools import BaseTool
from langchain_community.utilities import WikipediaAPIWrapper

def wikipedia_search(**kwargs) -> BaseTool:
    """返回维基百科搜索工具"""
    return WikipediaQueryRun(
        api_wrapper=WikipediaAPIWrapper()
    )