from typing import Optional

from langchain_core.runnables import RunnableConfig

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.entities.variable_entity import (
    VariableValueType,
    VariableTypeDefaultValueMap
)
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus

from .end_entity import EndNodeData

class EndNode(BaseNode):
    """结束节点"""
    _node_data_cls = EndNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """结束节点结束函数, 提取出状态中需要展示的数据, 并更新outputs"""
        outputs = self.node_data.outputs

        outputs_dict = {}
        for output in outputs:
            if output.value.type == VariableValueType.LITERAL:
                outputs_dict[output.name] = output.value.content
            else:
                # 引用数据类型
                for node_result in state["node_results"]:
                    if node_result.node_data.id == output.value.content.ref_node_id:
                        outputs_dict[output.name] = node_result.outputs.get(
                            output.value.content.ref_var_name,
                            VariableTypeDefaultValueMap.get(output.type)
                        )

        return {
            "outputs": outputs_dict,
            "node_results": [
                NodeResult(
                    node_data=self.node_data,
                    status=NodeStatus.SUCCEEDED,
                    inputs={},
                    outputs=outputs_dict
                )
            ]
        }