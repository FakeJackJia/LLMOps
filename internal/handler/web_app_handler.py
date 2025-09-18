from uuid import UUID

from injector import inject
from dataclasses import dataclass
from flask_login import login_required, current_user

from internal.schema.web_app_schema import WebAppChatReq, GetWebAppResp
from internal.service import WebAppService

from pkg.response import success_json, success_message, validate_error_json, compact_generate_response

@inject
@dataclass
class WebAppHandler:
    """WebApp处理器"""
    web_app_service: WebAppService

    @login_required
    def get_web_app(self, token: str):
        """根据传递的token凭证标识获取WebApp基础信息"""
        app = self.web_app_service.get_web_app(token)

        resp = GetWebAppResp()
        return success_json(resp.dump(app))

    @login_required
    def web_app_chat(self, token: str):
        """根据传递的token+query进行对话"""
        req = WebAppChatReq()
        if not req.validate():
            return validate_error_json(req.errors)

        response = self.web_app_service.web_app_chat(token, req, current_user)
        return compact_generate_response(response)

    @login_required
    def stop_web_app_chat(self, token: str, task_id: UUID):
        """根据传递的token+task_id停止与WebApp对话"""
        self.web_app_service.stop_web_app_chat(token, task_id, current_user)
        return success_message("停止WebApp对话成功")