from internal.core.workflow.entities.node_entity import BaseNodeData
from internal.core.workflow.entities.variable_entity import VariableEntity

from langchain_core.pydantic_v1 import Field


# 默认的代码
DEFAULT_CODE = """
def main(params):
    return params
"""

class CodeNodeData(BaseNodeData):
    """Python代码执行节点数据"""
    code: str = DEFAULT_CODE # 需要执行的python代码
    inputs: list[VariableEntity] = Field(default_factory=list)
    outputs: list[VariableEntity] = Field(default_factory=list)