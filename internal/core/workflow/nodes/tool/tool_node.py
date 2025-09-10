import json
from typing import Optional, Any

from langchain_core.pydantic_v1 import PrivateAttr
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.tools.api_tools.entities import ToolEntity
from internal.model import ApiTool
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from internal.core.workflow.utils.helper import extract_variables_from_state
from internal.exception import NotFoundException, FailException

from .tool_entity import ToolNodeData

class ToolNode(BaseNode):
    """工具节点"""
    node_data: ToolNodeData
    _tool: BaseTool = PrivateAttr(None)

    def __init__(self, *args: Any, **kwargs: Any):
        """构造函数, 完成工具的初始化"""
        super().__init__(*args, **kwargs)

        from app.http.module import injector

        if self.node_data.tool_type == "builtin_tool":
            from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
            builtin_provider_manager = injector.get(BuiltinProviderManager)

            _tool = builtin_provider_manager.get_tool(self.node_data.provider_id, self.node_data.tool_id)
            if not _tool:
                raise NotFoundException("该内置工具不存在")

            self._tool = _tool(**self.node_data.params)
        else:
            from pkg.sqlalchemy import SQLAlchemy
            db = injector.get(SQLAlchemy)

            api_tool = db.session.query(ApiTool).filter(
                ApiTool.provider_id == self.node_data.provider_id,
                ApiTool.name == self.node_data.tool_id
            ).one_or_none()
            if not api_tool:
                raise NotFoundException("该API工具不存在")

            from internal.core.tools.api_tools.providers import ApiProviderManager
            api_provider_manager = injector.get(ApiProviderManager)

            self._tool = api_provider_manager.get_tool(ToolEntity(
                id=str(api_tool.id),
                name=api_tool.name,
                url=api_tool.url,
                method=api_tool.method,
                description=api_tool.description,
                headers=api_tool.provider.headers,
                parameters=api_tool.parameters
            ))

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """根据传递的信息调用预设的工具, 涵盖内置和自定义工具"""
        inputs_dict = extract_variables_from_state(self.node_data.inputs, state)

        try:
            result = self._tool.invoke(inputs_dict)
        except Exception as e:
            raise FailException(str(e))

        if not isinstance(result, str):
            result = json.dumps(result)

        outputs = {}
        if self.node_data.outputs:
            outputs[self.node_data.outputs[0].name] = result
        else:
            outputs["text"] = result

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