from uuid import UUID

from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy
from internal.model import Account

@inject
@dataclass
class AccountService(BaseService):
    """账号服务"""
    db: SQLAlchemy

    def get_account(self, account_id: UUID) -> Account:
        """根据id获取指定的账号模型"""
        return self.get(Account, account_id)