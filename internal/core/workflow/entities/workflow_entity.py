from typing import Any, TypedDict, Annotated
from uuid import UUID

from langchain_core.pydantic_v1 import BaseModel, Field
from .node_entity import NodeResult

def _process_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """工作流状态字典归纳函数"""
    left = left or {}
    right = right or {}

    return {**left, **right}

def _process_node_results(left: list[NodeResult], right: list[NodeResult]) -> list[NodeResult]:
    """工作流状态节点结果列表归纳函数"""
    left = left or []
    right = right or []

    return left + right

class WorkflowConfig(BaseModel):
    """工作流配置信息"""
    account_id: UUID # 用户账号id
    name: str = "" # 工作流名称, 必须是英文
    description: str = "" # 工作流描述用于告诉LLM什么时候调用workflow
    nodes: list[dict[str, Any]] = Field(default_factory=list) # 工作流对应的节点
    edges: list[dict[str, Any]] = Field(default_factory=list) # 工作流对应的边


class WorkflowState(TypedDict):
    """工作流图程序状态字典"""
    inputs: Annotated[dict[str, Any], _process_dict] # 工作流的最初始输
    outputs: Annotated[dict[str, Any], _process_dict] # 工作流的最终输出结果
    node_results: Annotated[list[NodeResult], _process_node_results] # 各节点的运行结果