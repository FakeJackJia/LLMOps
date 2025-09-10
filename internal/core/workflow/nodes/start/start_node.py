from typing import Optional

from langchain_core.runnables import RunnableConfig

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.exception import FailException
from internal.core.workflow.entities.variable_entity import VARIABLE_TYPE_DEFAULT_VALUE_MAP
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from .start_entity import StartNodeData

class StartNode(BaseNode):
    """开始节点"""
    node_data: StartNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """开始节点执行函数, 该函数会提取状态中的输入信息并生成节点结果"""
        inputs = self.node_data.inputs

        outputs = {}
        for input in inputs:
            input_value = state["inputs"].get(input.name, None)

            if input_value is None:
                if input.required:
                    raise FailException(f"工作流参数生成错误, {input.name}为必填参数")

                input_value = VARIABLE_TYPE_DEFAULT_VALUE_MAP.get(input.type)

            outputs[input.name] = input_value

        return {
            "node_results": [
                NodeResult(
                    node_data=self.node_data,
                    status=NodeStatus.SUCCEEDED,
                    inputs=state["inputs"],
                    outputs=outputs,
                )
            ]
        }