from injector import inject
from dataclasses import dataclass
from pkg.response import success_json, validate_error_json
from internal.service import OAuthService
from internal.schema.oauth_schema import AuthorizeReq, AuthorizeResp

@inject
@dataclass
class OAuthHandler:
    """第三方授权认证处理器"""
    oauth_service: OAuthService

    def provider(self, provider_name: str):
        """根据传递的提供商名字获取授权认证重定向地址"""
        oauth = self.oauth_service.get_oauth_by_provider(provider_name)
        redirect_url = oauth.get_authorization_url()
        return success_json({"redirect_url": redirect_url})

    def authorize(self, provider_name: str):
        """根据传递的提供商名字+code获取第三方授权信息"""
        req = AuthorizeReq()
        if not req.validate():
            return validate_error_json(req.errors)

        credential = self.oauth_service.oauth_login(provider_name, req.code.data)
        resp = AuthorizeResp()
        return success_json(resp.dump(credential))