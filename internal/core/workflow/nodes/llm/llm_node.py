import time

from jinja2 import Template
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.utils.helper import extract_variables_from_state

from .llm_entity import LLMNodeData

class LLMNode(BaseNode):
    """大语言模型节点"""
    node_data: LLMNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """大语言模型节点, 根据输入的字段+预设prompt生成对应内容后输出"""
        start_at = time.perf_counter()
        inputs_dict = extract_variables_from_state(self.node_data.inputs, state)

        # 使用jinja2格式模板信息
        template = Template(self.node_data.prompt)
        prompt_value = template.render(**inputs_dict)

        # todo: 根据配置创建LLM实例, 等待多LLM
        llm = ChatOpenAI(
            model=self.node_data.language_model_config.get("model", "gpt-4o-mini"),
            **self.node_data.language_model_config.get("parameters", {})
        )


        content = ""
        for chunk in llm.stream(prompt_value):
            content += chunk.content

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
                    outputs=outputs,
                    latency=(time.perf_counter() - start_at)
                )
            ]
        }