from injector import inject
from dataclasses import dataclass
from flask_login import logout_user, login_required
from pkg.response import success_message, validate_error_json, success_json
from internal.schema.auth_schema import PasswordLoginReq, PasswordLoginResp
from internal.service import AccountService

@inject
@dataclass
class AuthHandler:
    """LLMOps平台自有授权认证处理器"""
    account_service: AccountService

    def password_login(self):
        """账号密码登录"""
        req = PasswordLoginReq()
        if not req.validate():
            return validate_error_json(req.errors)

        credential = self.account_service.password_login(req.email.data, req.password.data)

        resp = PasswordLoginResp()
        return success_json(resp.dump(credential))

    @login_required
    def logout(self):
        """退出登录, 用于提示前端清除授权凭证, 伪实现(非侧重点)"""
        logout_user()
        return success_message("退出登录成功")