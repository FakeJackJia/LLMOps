from langchain_core.tools import BaseTool
from langchain_community.tools import GoogleSerperRun
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_community.utilities import GoogleSerperAPIWrapper

class GoogleSerperArgsSchema(BaseModel):
    """谷歌SerperAPI搜索参数描述"""
    query: str = Field(description="需要检索查询的语句")

def google_serper(**kwargs) -> BaseTool:
    """谷歌Serp搜索"""
    return GoogleSerperRun(
        name="google_serper",
        description=(
            "一个低成本的谷歌搜索API"
            "当你需要回答有关实时问题时, 可以调用该工具"
            "该工具传递的参数是搜索查询语句"
        ),
        args_schema=GoogleSerperArgsSchema,
        api_wrapper=GoogleSerperAPIWrapper()
    )