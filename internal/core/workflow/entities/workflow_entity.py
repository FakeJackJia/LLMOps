import re
from typing import Any, TypedDict, Annotated
from uuid import UUID

from langchain_core.pydantic_v1 import BaseModel, Field, root_validator

from internal.exception import ValidateErrorException

from .edge_entity import BaseEdgeData
from .node_entity import NodeResult, BaseNodeData, NodeType

# 工作流配置校验信息
WORKFLOW_CONFIG_NAME_PATTERN = r'^[A-Za-z][A-Za-z0-9_]*$'
WORKFLOW_CONFIG_DESCRIPTION_MAX_LENGTH = 1024

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
    nodes: list[BaseNodeData] = Field(default_factory=list) # 工作流对应的节点
    edges: list[BaseEdgeData] = Field(default_factory=list) # 工作流对应的边

    @root_validator(pre=True)
    def validate_workflow_config(cls, values: dict[str, Any]):
        """校验工作流的所有参数配置"""
        name = values.get("name", None)
        if not name or not re.match(WORKFLOW_CONFIG_NAME_PATTERN, name):
            raise ValidateErrorException("工作流名字仅支持字母、数字和下划线, 且以字母开头")

        description = values.get("description", None)
        if not description or len(description) > WORKFLOW_CONFIG_DESCRIPTION_MAX_LENGTH:
            raise ValidateErrorException("工作流描述长度不能超过1024字符")

        nodes = values.get("nodes", [])
        edges = values.get("edges", [])

        if not isinstance(nodes, list) or len(nodes) ==0 :
            raise ValidateErrorException("工作流节点列表信息错误")
        if not isinstance(edges, list) or len(edges) ==0 :
            raise ValidateErrorException("工作流边列表信息错误")

        from internal.core.workflow.nodes import (
            CodeNodeData,
            DatasetRetrievalNodeData,
            EndNodeData,
            HttpRequestNodeData,
            LLMNodeData,
            StartNodeData,
            ToolNodeData,
            TemplateTransformNodeData,
        )

        node_data_classes = {
            NodeType.START: StartNodeData,
            NodeType.END: EndNodeData,
            NodeType.LLM: LLMNodeData,
            NodeType.TEMPLATE_TRANSFORM: TemplateTransformNodeData,
            NodeType.DATASET_RETRIEVAL: DatasetRetrievalNodeData,
            NodeType.CODE: CodeNodeData,
            NodeType.TOOL: ToolNodeData,
            NodeType.HTTP_REQUEST: HttpRequestNodeData,
        }

        node_data_dict = {}
        for node in nodes:
            if not isinstance(node, dict):
                raise ValidateErrorException("工作流节点数据类型出错")

            node_type = node.get("node_type", "")
            node_data_cls = node_data_classes.get(node_type, None)
            if not node_data_cls:
                raise ValidateErrorException("工作流节点类型出错")

            node_data = node_data_cls(**node)

            node_data_dict[node_data.id] = node_data

        edge_data_dict = {}
        for edge in edges:
            if not isinstance(edge, dict):
                raise ValidateErrorException("工作流边数据类型出错")

            edge_data = BaseEdgeData(**edge)
            edge_data_dict[edge_data.id] = edge_data

        values["nodes"] = list(node_data_dict.values())
        values["edges"] = list(edge_data_dict.values())

        return values

class WorkflowState(TypedDict):
    """工作流图程序状态字典"""
    inputs: Annotated[dict[str, Any], _process_dict] # 工作流的最初始输
    outputs: Annotated[dict[str, Any], _process_dict] # 工作流的最终输出结果
    node_results: Annotated[list[NodeResult], _process_node_results] # 各节点的运行结果