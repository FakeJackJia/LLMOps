from typing import Optional

from flask import Request
from injector import inject
from dataclasses import dataclass
from internal.model import Account
from internal.exception import UnauthorizedException
from internal.service import JwtService, AccountService, ApiKeyService

@inject
@dataclass
class Middleware:
    """应用中间件, 可以重写request_loader与unauthorized_handler"""
    jwt_service: JwtService
    account_service: AccountService
    api_key_service: ApiKeyService

    def request_loader(self, request: Request) -> Optional[Account]:
        """登录管理器的请求加载器"""
        # 单独为llmops路由蓝图创建请求加载器
        if request.blueprint == "llmops":
            access_token = self._validate_credential(request)

            # 解析token信息得到用户信息并返回
            payload = self.jwt_service.parse_token(access_token)
            account_id = payload.get("sub")
            return self.account_service.get_account(account_id)
        elif request.blueprint == "openapi":
            api_key = self._validate_credential(request)

            api_key_record = self.api_key_service.get_api_by_credential(api_key)

            if not api_key_record or not api_key_record.is_active:
                raise UnauthorizedException("该密钥不存在或未激活")

            return api_key_record.account
        else:
            return None

    @classmethod
    def _validate_credential(cls, request: Request) -> str:
        """校验请求头中的凭证信息, 涵盖access_token和api_key"""
        # 提取请求头headers中的信息
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise UnauthorizedException("该接口需要授权才能访问, 请登录后尝试")
        # 请求信息中没有空格分隔符, 则验证失败, Authorization: Bearer access_token
        if " " not in auth_header:
            raise UnauthorizedException("该接口需要授权才能访问, 验证格式失败")

        # 分割授权信息, 必须符合Bearer access_token
        auth_schema, credential = auth_header.split(None, 1)
        if auth_schema.lower() != "bearer":
            raise UnauthorizedException("该接口需要授权才能访问, 验证格式失败")

        return credential