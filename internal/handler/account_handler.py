from injector import inject
from dataclasses import dataclass
from flask_login import login_required, current_user
from internal.service import AccountService
from internal.schema.account_schema import (
    GetCurrentUserResp,
    UpdatePasswordRep,
    UpdateNameRep,
    UpdateAvatarRep,
)
from pkg.response import success_json, validate_error_json, success_message

@inject
@dataclass
class AccountHandler:
    """账号设置处理器"""
    account_service: AccountService

    @login_required
    def get_current_user(self):
        """获取当前登录账号信息"""
        resp = GetCurrentUserResp()
        return success_json(resp.dump(current_user))

    @login_required
    def update_password(self):
        """更新当前登录账号密码"""
        req = UpdatePasswordRep()
        if not req.validate():
            return validate_error_json(req.errors)

        self.account_service.update_password(req.password.data, current_user)
        return success_message("更新密码成功")

    @login_required
    def update_name(self):
        """更新当前登录账号名称"""
        req = UpdateNameRep()
        if not req.validate():
            return validate_error_json(req.errors)

        self.account_service.update_name(req.name.data, current_user)
        return success_message("更新账号名字成功")

    @login_required
    def update_avatar(self):
        """更新当前账号头像信息"""
        req = UpdateAvatarRep()
        if not req.validate():
            return validate_error_json(req.errors)

        self.account_service.update_avatar(req.avatar.data, current_user)
        return success_message("更新账号头像成功")
