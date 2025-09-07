from typing import Any, Optional, Iterator

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.utils import Input, Output
from langchain_core.tools import BaseTool
from langchain_core.pydantic_v1 import PrivateAttr
from langgraph.graph.state import CompiledStateGraph, StateGraph

from .entities.workflow_entity import WorkflowConfig, WorkflowState


class Workflow(BaseTool):
    """工作流LangChain工具类"""
    _workflow_config: WorkflowConfig = PrivateAttr(None)
    _workflow: CompiledStateGraph = PrivateAttr(None)

    def __init__(self, workflow_config: WorkflowConfig, **kwargs):
        """构造函数, 完成工作流函数的初始化"""
        super().__init__(
            name=workflow_config.name,
            description=workflow_config.description,
            **kwargs
        )

        self._workflow_config = workflow_config
        self._workflow = self._build_workflow()

    def _build_workflow(self) -> CompiledStateGraph:
        """构建编译后的工作流图程序"""
        graph = StateGraph(WorkflowState)

        # todo: add nodes and edges

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