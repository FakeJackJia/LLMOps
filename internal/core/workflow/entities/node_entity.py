from enum import Enum
from typing import Any
from uuid import UUID

from langchain_core.pydantic_v1 import BaseModel, Field

class BaseNodeData(BaseModel):
    """基础节点数据"""
    id: UUID # 节点id, 必须唯一
    title: str = "" # 节点标题, 必须唯一
    description: str = "" # 节点描述

class NodeStatus(str, Enum):
    """节点状态"""
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class NodeResult(BaseModel):
    """节点运行结果"""
    node_data: BaseNodeData # 节点基础数据
    status: NodeStatus = NodeStatus.RUNNING # 节点运行状态
    inputs: dict[str, Any] = Field(default_factory=dict) # 节点输入数据
    outputs: dict[str, Any] = Field(default_factory=dict) # 节点输出数据
    error: str = "" # 节点运行错误信息