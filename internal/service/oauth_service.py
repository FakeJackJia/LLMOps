import os
from datetime import datetime, timedelta
from typing import Any

from injector import inject
from flask import request
from dataclasses import dataclass
from .base_service import BaseService
from .account_service import AccountService
from .jwt_service import JwtService
from pkg.sqlalchemy import SQLAlchemy
from pkg.oauth import OAuth, GithubOAuth
from internal.exception import NotFoundException
from internal.model import AccountOAuth

@inject
@dataclass
class OAuthService(BaseService):
    """第三方授权认证服务"""
    db: SQLAlchemy
    account_service: AccountService
    jwt_service: JwtService

    @classmethod
    def get_all_oauth(cls) -> dict[str, OAuth]:
        """获取LLMOps集成的所有第三方授权认证方式"""
        github = GithubOAuth(
            client_id=os.getenv("GITHUB_CLIENT_ID"),
            client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
            redirect_uri=os.getenv("GITHUB_REDIRECT_URI")
        )

        return {
            "github": github,
        }

    @classmethod
    def get_oauth_by_provider(cls, provider_name: str) -> OAuth:
        """根据传递的服务提供商名字获取授权服务"""
        all_oauth = cls.get_all_oauth()
        oauth = all_oauth.get(provider_name)

        if oauth is None:
            raise NotFoundException("无该授权方式")

        return oauth

    def oauth_login(self, provider_name: str, code: str) -> dict[str, Any]:
        """第三方OAuth授权认证登录, 返回授权凭证以及过期时间"""
        oauth = self.get_oauth_by_provider(provider_name)
        oauth_access_token = oauth.get_access_token(code)
        oauth_user_info = oauth.get_user_info(oauth_access_token)

        account_oauth = self.account_service.get_account_oauth_by_provider_name_and_openid(
            provider_name,
            oauth_user_info.id,
        )
        if not account_oauth:
            account = self.account_service.get_account_by_email(oauth_user_info.email)
            if not account:
                account = self.account_service.create_account(
                    name=oauth_user_info.name,
                    email=oauth_user_info.email,
                )

            account_oauth = self.create(
                AccountOAuth,
                account_id=account.id,
                provider=provider_name,
                openid=oauth_user_info.id,
                encrypted_token=oauth_access_token,
            )
        else:
            account = self.account_service.get_account(account_oauth.account_id)

        # 更新账号信息, 涵盖最后一次登录时间, 以及ip地址
        self.update(
            account,
            last_login_at=datetime.now(),
            last_login_ip=request.remote_addr,
        )
        self.update(
            account_oauth,
            encrypted_token=oauth_access_token,
        )

        expire_at = int((datetime.now() + timedelta(days=30)).timestamp())
        payload = {
            "sub": str(account.id),
            "iss": "llmops",
            "exp": expire_at,
        }
        access_token = self.jwt_service.generate_token(payload)

        return {
            "expire_at": expire_at,
            "access_token": access_token,
        }