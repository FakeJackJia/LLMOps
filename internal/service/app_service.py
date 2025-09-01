from uuid import UUID
from dataclasses import dataclass
from injector import inject
from pkg.sqlalchemy import SQLAlchemy
from internal.model import App, Account, AppConfigVersion
from internal.schema.app_schema import CreateAppReq
from internal.exception import NotFoundException, ForbiddenException
from internal.entity.app_entity import AppStatus, AppConfigType, DEFAULT_APP_CONFIG
from .base_service import BaseService

@inject
@dataclass
class AppService(BaseService):
    """应用服务逻辑"""
    db: SQLAlchemy

    def create_app(self, req: CreateAppReq, account: Account) -> App:
        """创建Agent应用服务"""
        with self.db.auto_commit():
            app = App(
                account_id=account.id,
                name=req.name.data,
                icon=req.icon.data,
                description=req.description.data,
                status=AppStatus.DRAFT
            )
            self.db.session.add(app)
            self.db.session.flush()

            app_config_version = AppConfigVersion(
                app_id=app.id,
                version=0,
                config_type=AppConfigType.DRAFT,
                **DEFAULT_APP_CONFIG
            )
            self.db.session.add(app_config_version)
            self.db.session.flush()

            app.draft_app_config_id = app_config_version.id

        return app

    def get_app(self, app_id: UUID, account: Account) -> App:
        """根据传递的id获取应用基础信息"""
        app = self.get(App, app_id)

        if not app:
            raise NotFoundException("该应用不存在")

        if app.account_id != account.id:
            raise ForbiddenException("当前账号无权限访问该应用")

        return app