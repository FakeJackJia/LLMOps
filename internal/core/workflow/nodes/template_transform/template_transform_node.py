from typing import Optional
from jinja2 import Template

from langchain_core.runnables import RunnableConfig

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.entities.variable_entity import VariableValueType, VariableTypeDefaultValueMap

from .template_transform_entity import TemplateTransformNodeData


class TemplateTransformNode(BaseNode):
    """模板转换节点, 将多个变量信息合并成一个"""
    _node_data_cls = TemplateTransformNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """模板转换节点, 将传递的多个变量合并成字符串返回"""
        inputs = self.node_data.inputs

        inputs_dict = {}
        for input in inputs:
            if input.value.type == VariableValueType.LITERAL:
                inputs_dict[input.name] = input.value.content
            else:
                for node_result in state["node_results"]:
                    if node_result.node_data.id == input.value.content.ref_node_id:
                        inputs_dict[input.name] = node_result.outputs.get(
                            input.value.content.ref_var_name,
                            VariableTypeDefaultValueMap.get(input.type)
                        )

        # 使用jinja2格式模板信息
        template = Template(self.node_data.template)
        template_value = template.render(**inputs_dict)

        outputs = {}
        if self.node_data.outputs:
            outputs[self.node_data.outputs[0].name] = template_value
        else:
            outputs["output"] = template_value

        return {
            "node_results": [
                NodeResult(
                    node_data=self.node_data,
                    status=NodeStatus.SUCCEEDED,
                    inputs=inputs_dict,
                    outputs=outputs
                )
            ]
        }