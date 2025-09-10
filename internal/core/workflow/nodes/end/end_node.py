from typing import Optional

from langchain_core.runnables import RunnableConfig

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from internal.core.workflow.utils.helper import extract_variables_from_state

from .end_entity import EndNodeData

class EndNode(BaseNode):
    """结束节点"""
    _node_data_cls = EndNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """结束节点结束函数, 提取出状态中需要展示的数据, 并更新outputs"""
        outputs_dict = extract_variables_from_state(self.node_data.outputs, state)

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