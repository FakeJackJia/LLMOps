from uuid import UUID

from langchain_core.pydantic_v1 import BaseModel

from internal.core.workflow.entities.node_entity import NodeType

class BaseEdgeData(BaseModel):
    """基础边数据"""
    id: UUID
    source: UUID
    source_type: NodeType
    target: UUID
    target_type: NodeType