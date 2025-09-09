from typing import Any, Optional, Iterator

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.utils import Input, Output
from langchain_core.tools import BaseTool
from langchain_core.pydantic_v1 import PrivateAttr, BaseModel, Field, create_model
from langgraph.graph.state import CompiledStateGraph, StateGraph

from .entities.node_entity import NodeType
from .entities.variable_entity import VariableTypeMap
from .entities.workflow_entity import WorkflowConfig, WorkflowState
from .nodes import (
    StartNode,
    EndNode,
    LLMNode,
    TemplateTransformNode
)

# 节点类映射
NodeClasses = {
    NodeType.START: StartNode,
    NodeType.END: EndNode,
    NodeType.LLM: LLMNode,
    NodeType.TEMPLATE_TRANSFORM: TemplateTransformNode
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
            (node.get("inputs", []) for node in workflow_config.nodes if node.get("node_type") == NodeType.START),
            []
        )
        for input in inputs:
            field_name = input.get("name")
            field_type = VariableTypeMap.get(input.get("type"), str)
            field_required = input.get("required", True)
            field_description = input.get("description", "")

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
            node_flag = f"{node.get('node_type')}_{node.get('id')}"
            if node.get("node_type") == NodeType.START:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.START](node_data=node),
                )
            elif node.get("node_type") == NodeType.LLM:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.LLM](node_data=node),
                )
            elif node.get("node_type") == NodeType.TEMPLATE_TRANSFORM:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.TEMPLATE_TRANSFORM](node_data=node),
                )
            elif node.get("node_type") == NodeType.END:
                graph.add_node(
                    node_flag,
                    NodeClasses[NodeType.END](node_data=node),
                )

        for edge in edges:
            graph.add_edge(
                f"{edge.get('source_type')}_{edge.get('source')}",
                f"{edge.get('target_type')}_{edge.get('target')}"
            )

            if edge.get('source_type') == NodeType.START:
                graph.set_entry_point(f"{edge.get('source_type')}_{edge.get('source')}")
            elif edge.get('target_type') == NodeType.END:
                graph.set_finish_point(f"{edge.get('target_type')}_{edge.get('target')}")

        return graph.compile()

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """工作流组件基础run方法"""
        return self._workflow.invoke({"inputs": kwargs})

    def stream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Optional[Any],
    ) -> Iterator[Output]:
        """工作流流式输出每个节点对应的结果"""
        return self._workflow.stream({"inputs": input})