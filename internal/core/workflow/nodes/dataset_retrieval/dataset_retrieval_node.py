from typing import Optional, Any
from uuid import UUID

from flask import Flask
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_core.pydantic_v1 import PrivateAttr

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.entities.variable_entity import VariableValueType, VariableTypeDefaultValueMap
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus

from .dataset_retrieval_entity import DatasetRetrievalNodeData


class DatasetRetrievalNode(BaseNode):
    """知识库检索节点"""
    _node_data_cls = DatasetRetrievalNodeData
    _retrieval_tool: BaseTool = PrivateAttr(None)

    def __init__(
            self,
            *args: Any,
            flask_app: Flask,
            account_id: UUID,
            node_data: dict[str, Any],
            **kwargs: Any
    ):
        """构造函数, 完成节点的初始化"""
        super().__init__(*args, node_data=node_data, **kwargs)

        from app.http.module import injector
        from internal.service import RetrievalService

        retrieval_service = injector.get(RetrievalService)

        self._retrieval_tool = retrieval_service.create_langchain_tool_from_search(
            flask_app=flask_app,
            dataset_ids=self.node_data.dataset_ids,
            account_id=account_id,
            **self.node_data.retrieval_config.dict(),
        )

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """执行相应的知识库检索后返回"""
        query_input = self.node_data.inputs[0]

        inputs_dict = {}
        if query_input.value.type == VariableValueType.LITERAL:
            inputs_dict[query_input.name] = query_input.value.content
        else:
            for node_result in state["node_results"]:
                if node_result.node_data.id == query_input.value.content.ref_node_id:
                    inputs_dict[query_input.name] = node_result.outputs.get(
                        query_input.value.content.ref_var_name,
                        VariableTypeDefaultValueMap.get(query_input.type)
                    )

        combine_documents = self._retrieval_tool.invoke(inputs_dict)

        outputs = {}
        if self.node_data.outputs:
            outputs[self.node_data.outputs[0].name] = combine_documents
        else:
            outputs["combine_documents"] = combine_documents

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