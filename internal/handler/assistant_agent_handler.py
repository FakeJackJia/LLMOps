from uuid import UUID
from flask_login import login_required, current_user
from flask import request
from injector import inject
from dataclasses import dataclass

from internal.service import AssistantAgentService
from internal.schema.assistant_agent_schema import (
    AssistantAgentChatReq,
    GetAssistantAgentMessagesWithPageReq,
    GetAssistantAgentMessagesWithPageResp
)

from pkg.paginator import PageModel
from pkg.response import validate_error_json, success_json, success_message, compact_generate_response

@inject
@dataclass
class AssistantAgentHandler:
    """辅助智能体处理器"""
    assistant_agent_service: AssistantAgentService

    @login_required
    def assistant_agent_chat(self):
        """与辅助智能体进行聊天"""
        req = AssistantAgentChatReq()
        if not req.validate():
            return validate_error_json(req.errors)

        response = self.assistant_agent_service.chat(req.query.data, current_user)
        return compact_generate_response(response)

    @login_required
    def stop_assistant_agent_chat(self, task_id: UUID):
        """停止与辅助智能体的对话聊天"""
        self.assistant_agent_service.stop_chat(task_id, current_user)
        return success_message("停止辅助Agent会话成功")

    @login_required
    def get_assistant_agent_messages_with_page(self):
        """获取与辅助智能体的聊天记录分页列表"""
        req = GetAssistantAgentMessagesWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        messages, paginator = self.assistant_agent_service.get_conversation_messages_with_page(
            req,
            current_user
        )

        resp = GetAssistantAgentMessagesWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(messages), paginator=paginator))

    @login_required
    def delete_assistant_agent_conversation(self):
        """清空与辅助智能体的聊天记录"""
        self.assistant_agent_service.delete_conversation(current_user)
        return success_message("清空辅助Agent会话成功")