from typing import Any, Literal

from internal.core.workflow.entities.node_entity import BaseNodeData
from internal.core.workflow.entities.variable_entity import VariableEntity, VariableValueType

from langchain_core.pydantic_v1 import Field

class ToolNodeData(BaseNodeData):
    """工具节点数据"""
    tool_type: Literal["builtin_tool", "api_tool", ""] = Field(alias="type")
    provider_id: str
    tool_id: str
    params: dict[str, Any] = Field(default_factory=dict) # 内置工具的设置参数
    inputs: list[VariableEntity] = Field(default_factory=list)
    outputs: list[VariableEntity] = Field(
        exclude=True,
        default_factory=lambda :[
            VariableEntity(name="text", value={"type": VariableValueType.GENERATED})
        ]
    )