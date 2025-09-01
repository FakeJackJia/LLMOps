from flask_login import login_required, current_user
from pkg.response import success_json, validate_error_json
from internal.service import (
    AppService,
)
from internal.schema.app_schema import (
    CreateAppReq,
    GetAppResp,
)
from dataclasses import dataclass
from injector import inject
from uuid import UUID

@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService

    @login_required
    def create_app(self):
        """调用服务创建新的APP记录"""
        req = CreateAppReq()
        if not req.validate():
            return validate_error_json(req.errors)

        app = self.app_service.create_app(req, current_user)
        return success_json({"id": app.id})

    @login_required
    def get_app(self, app_id: UUID):
        """获取指定的应用基础信息"""
        app = self.app_service.get_app(app_id, current_user)

        resp = GetAppResp()
        return success_json(resp.dump(app))

    @login_required
    def get_draft_app_config(self, app_id: UUID):
        """根据传递的应用id获取应用的最新草稿配置"""
        draft_config = self.app_service.get_draft_app_config(app_id, current_user)
        return success_json(draft_config)

    @login_required
    def ping(self):
        pass