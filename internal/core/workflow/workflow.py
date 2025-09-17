from typing import Any, Optional, Iterator
from flask import current_app

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.utils import Input, Output
from langchain_core.tools import BaseTool
from langchain_core.pydantic_v1 import PrivateAttr, BaseModel, Field, create_model
from langgraph.graph.state import CompiledStateGraph, StateGraph

from internal.exception import ValidateErrorException

from .entities.node_entity import NodeType
from .entities.variable_entity import VARIABLE_TYPE_MAP
from .entities.workflow_entity import WorkflowConfig, WorkflowState
from .nodes import (
    StartNode,
    EndNode,
    LLMNode,
    TemplateTransformNode,
    DatasetRetrievalNode,
    CodeNode,
    ToolNode,
    HttpRequestNode
)

# 节点类映射
NodeClasses = {
    NodeType.START: StartNode,
    NodeType.END: EndNode,
    NodeType.LLM: LLMNode,
    NodeType.TEMPLATE_TRANSFORM: TemplateTransformNode,
    NodeType.DATASET_RETRIEVAL: DatasetRetrievalNode,
    NodeType.CODE: CodeNode,
    NodeType.TOOL: ToolNode,
    NodeType.HTTP_REQUEST: HttpRequestNode
}

class Workflow(BaseTool):
    """工作流LangChain工具类"""
    _workflow_config: WorkflowConfig = PrivateAttr(None)
    _workflow: CompiledStateGraph = PrivateAttr(None)

    def __init__(self, workflow_config: WorkflowConfig, **kwargs):
        """构造函数, 完成工作流函数的初始化"""
        super().__init__(
            name=workflow_config.name,
            description=workflow_config.description,
            args_schema=self._build_args_schema(workflow_config),
            **kwargs
        )

        self._workflow_config = workflow_config
        self._workflow = self._build_workflow()

    @classmethod
    def _build_args_schema(cls, workflow_config: WorkflowConfig) -> type[BaseModel]:
        """构建输入参数结构"""
        fields = {}
        inputs = next(
            (node.inputs for node in workflow_config.nodes if node.node_type == NodeType.START),
            []
        )
        for input in inputs:
            field_name = input.name
            field_type = VARIABLE_TYPE_MAP.get(input.type, str)
            field_required = input.required
            field_description = input.description

            fields[field_name] = (
                field_type if field_required else Optional[field_type],
                Field(description=field_description)
            )

        return create_model("DynamicModel", **fields)

    def _build_workflow(self) -> CompiledStateGraph:
        """构建编译后的工作流图程序"""
        graph = StateGraph(WorkflowState)

        nodes = self._workflow_config.nodes
        edges = self._workflow_config.edges

        for node in nodes:
            node_flag = f"{node.node_type.value}_{node.id}"
            if node.node_type == NodeType.START:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.START](node_data=node),
                )
            elif node.node_type == NodeType.LLM:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.LLM](node_data=node),
                )
            elif node.node_type == NodeType.TEMPLATE_TRANSFORM:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.TEMPLATE_TRANSFORM](node_data=node),
                )
            elif node.node_type == NodeType.DATASET_RETRIEVAL:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.DATASET_RETRIEVAL](
                        flask_app=current_app._get_current_object(),
                        account_id=self._workflow_config.account_id,
                        node_data=node,
                    ),
                )
            elif node.node_type == NodeType.CODE:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.CODE](node_data=node),
                )
            elif node.node_type == NodeType.TOOL:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.TOOL](node_data=node),
                )
            elif node.node_type == NodeType.HTTP_REQUEST:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.HTTP_REQUEST](node_data=node),
                )
            elif node.node_type == NodeType.END:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.END](node_data=node),
                )
            else:
                raise ValidateErrorException("工作流节点类型错误")

        parallel_edges = {} # key: 终点, value: 起点列表
        start_node = ""
        end_node = ""
        for edge in edges:
            # 计算并获取并行边
            source_node = f"{edge.source_type.value}_{edge.source}"
            target_node = f"{edge.target_type.value}_{edge.target}"

            if target_node not in parallel_edges:
                parallel_edges[target_node] = [source_node]
            else:
                parallel_edges[target_node].append(source_node)

            if edge.source_type == NodeType.START:
                start_node = source_node
            if edge.target_type == NodeType.END:
                end_node = target_node

        graph.set_entry_point(start_node)
        graph.set_finish_point(end_node)

        for target_node, source_nodes in parallel_edges.items():
            graph.add_edge(source_nodes, target_node)

        return graph.compile()

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """工作流组件基础run方法"""
        result = self._workflow.invoke({"inputs": kwargs})
        return result.get("outputs", {})

    def stream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Optional[Any],
    ) -> Iterator[Output]:
        """工作流流式输出每个节点对应的结果"""
        return self._workflow.stream({"inputs": input})