from jinja2 import Template
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.entities.variable_entity import VariableValueType, VariableTypeDefaultValueMap
from .llm_entity import LLMNodeData

class LLMNode(BaseNode):
    """大语言模型节点"""
    _node_data_cls = LLMNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """大语言模型节点, 根据输入的字段+预设prompt生成对应内容后输出"""
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
        template = Template(self.node_data.prompt)
        prompt_value = template.render(**inputs_dict)

        # todo: 根据配置创建LLM实例, 等待多LLM
        llm = ChatOpenAI(
            model=self.node_data.language_model_config.get("model", "gpt-4o-mini"),
            **self.node_data.language_model_config.get("parameters", {})
        )

        content = llm.invoke(prompt_value).content

        outputs = {}
        if self.node_data.outputs:
            outputs[self.node_data.outputs[0].name] = content
        else:
            outputs["output"] = content

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
