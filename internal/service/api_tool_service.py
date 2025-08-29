import json
from typing import Any
from uuid import UUID
from injector import inject
from dataclasses import dataclass
from internal.exception import ValidateErrorException, NotFoundException
from internal.core.tools.api_tools.entities import OpenAPISchema
from internal.schema.api_tool_schema import (
    CreateApiToolReq,
    GetApiToolProvidersWithPageReq,
    UpdateApiToolReq,
)
from internal.model import ApiToolProvider, ApiTool, Account
from internal.core.tools.api_tools.providers import ApiProviderManager
from pkg.sqlalchemy import SQLAlchemy
from pkg.paginator import Paginator
from .base_service import BaseService
from sqlalchemy import desc

@inject
@dataclass
class ApiToolService(BaseService):
    """自定义API插件服务"""
    db: SQLAlchemy
    api_provider_manager: ApiProviderManager

    def update_api_tool_provider(
            self,
            provider_id: UUID,
            req: UpdateApiToolReq,
            account: Account
    ):
        """根据传递的provider_id+req更新对应的API工具提供者信息"""
        api_tool_provider = self.get(ApiToolProvider, provider_id)
        if api_tool_provider is None or api_tool_provider.account_id != account.id:
            raise ValidateErrorException("该工具提供者不存在")

        openapi_schema = self.parse_openapi_schema(req.openapi_schema.data)
        check_api_tool_provider = self.db.session.query(ApiToolProvider).filter(
            ApiToolProvider.account_id == account.id,
            ApiToolProvider.name == req.name.data,
            ApiToolProvider.id != api_tool_provider.id,
        ).one_or_none()
        if check_api_tool_provider:
            raise ValidateErrorException(f"该工具提供者名字{req.name.data}已存在")

        with self.db.auto_commit():
            self.db.session.query(ApiTool).filter(
                ApiTool.provider_id == api_tool_provider.id,
                ApiTool.account_id == account.id
            ).delete()

        self.update(
            api_tool_provider,
            name=req.name.data,
            icon=req.icon.data,
            headers=req.headers.data,
            description=openapi_schema.description,
            openapi_schema=req.openapi_schema.data
        )

        for path, path_item in openapi_schema.paths.items():
            for method, method_item in path_item.items():
                self.create(
                    ApiTool,
                    account_id=account.id,
                    provider_id=api_tool_provider.id,
                    name=method_item.get("operationId"),
                    description=method_item.get("description"),
                    url=f"{openapi_schema.server}{path}",
                    method=method,
                    parameters=method_item.get("parameters", [])
                )

    def get_api_tool_providers_with_page(
            self,
            req: GetApiToolProvidersWithPageReq,
            account: Account
    ) -> tuple[list[Any], Paginator]:
        """获取自定义API工具服务提供者分页列表数据"""
        paginator = Paginator(db=self.db, req=req)

        # 筛选器
        filters = [ApiToolProvider.account_id == account.id]
        if req.search_word.data:
            filters.append(ApiToolProvider.name.ilike(f"%{req.search_word.data}%"))

        api_tool_providers = paginator.paginate(
            self.db.session.query(ApiToolProvider).filter(*filters).order_by(desc("created_at"))
        )

        return api_tool_providers, paginator

    def get_api_tool(self, provider_id: UUID, tool_name: str, account: Account) -> ApiTool:
        """根据传递的provider_id和tool_name获取对应工具的参数详情"""
        api_tool = self.db.session.query(ApiTool).filter_by(
            provider_id=provider_id,
            name=tool_name,
        ).one_or_none()
        if api_tool is None or str(api_tool.account_id) != account.id:
            raise NotFoundException("该工具不存在")

        return api_tool

    def get_api_tool_provider(self, provider_id: UUID, account: Account) -> ApiToolProvider:
        """根据传递的provider_id获取API工具提供者信息"""
        api_tool_provider = self.get(ApiToolProvider, provider_id)

        if api_tool_provider is None or str(api_tool_provider.account_id) != account.id:
            raise NotFoundException("该工具提供者不存在")

        return api_tool_provider

    def create_api_tool(self, req: CreateApiToolReq, account: Account) -> None:
        """根据传递的请求创建自定义API工具"""
        openapi_schema = self.parse_openapi_schema(req.openapi_schema.data)
        api_tool_provider = self.db.session.query(ApiToolProvider).filter_by(
            account_id=account.id,
            name=req.name.data,
        ).one_or_none()
        if api_tool_provider:
            raise ValidateErrorException(f"该工具提供者的名字{req.name.data}已存在")

        api_tool_provider = self.create(
            ApiToolProvider,
            account_id=account.id,
            name=req.name.data,
            icon=req.icon.data,
            description=openapi_schema.description,
            openapi_schema=req.openapi_schema.data,
            headers=req.headers.data
        )

        for path, path_item in openapi_schema.paths.items():
            for method, method_item in path_item.items():
                self.create(
                    ApiTool,
                    account_id=account.id,
                    provider_id=api_tool_provider.id,
                    name=method_item.get("operationId"),
                    description=method_item.get("description"),
                    url=f"{openapi_schema.server}{path}",
                    method=method,
                    parameters=method_item.get("parameters", [])
                )

    def delete_api_tool_provider(self, provider_id: UUID, account: Account):
        """根据传递的provider_id删除对应的工具提供商+工具所有信息"""
        api_tool_provider = self.get(ApiToolProvider, provider_id)
        if api_tool_provider is None or str(api_tool_provider.account_id) != account.id:
            raise NotFoundException("该工具提供者不存在")

        with self.db.auto_commit():
            self.db.session.query(ApiTool).filter(
                ApiTool.provider_id == provider_id,
                ApiTool.account_id == account.id
            ).delete()

            self.db.session.delete(api_tool_provider)

    @classmethod
    def parse_openapi_schema(cls, openapi_schema_str: str) -> OpenAPISchema:
        """解析传递的openapi_schema字符串, 如果出错则抛出错误"""
        try:
            data = json.loads(openapi_schema_str.strip())
            if not isinstance(data, dict):
                raise
        except Exception as e:
            raise ValidateErrorException("传递数据必须符合OpenAPI规范的JSON字符")

        return OpenAPISchema(**data)