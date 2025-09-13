import mimetypes
import os.path
from typing import Any
from injector import inject
from dataclasses import dataclass
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.core.tools.builtin_tools.categories import BuiltinCategoryManager
from langchain_core.pydantic_v1 import BaseModel
from internal.exception import NotFoundException
from flask import current_app

@inject
@dataclass
class BuiltinToolService:
    """内置工具服务"""
    builtin_provider_manager: BuiltinProviderManager
    builtin_category_manager: BuiltinCategoryManager

    def get_builtin_tools(self) -> list:
        """获取LLMOps项目中的所有内置提供商+工具对应的信息"""
        providers = self.builtin_provider_manager.get_providers()

        builtin_tools = []
        for provider in providers:
            provider_entity = provider.provider_entity
            builtin_tool = {**provider_entity.model_dump(exclude=["icon"]), "tools": []}

            for tool_entity in provider.get_tool_entities():
                tool = provider.get_tool(tool_entity.name)
                tool_dict = {
                    **tool_entity.model_dump(),
                    "inputs": self.get_tool_inputs(tool)
                }
                builtin_tool["tools"].append(tool_dict)

            builtin_tools.append(builtin_tool)

        return builtin_tools


    def get_provider_tool(self, provider_name: str, tool_name: str):
        """根据传递的提供商名字+工具名字获取指定工具的信息"""
        provider = self.builtin_provider_manager.get_provider(provider_name)
        if provider is None:
            raise NotFoundException(f"该提供商{provider_name}不存在")

        tool_entity = provider.get_tool_entity(tool_name)
        if tool_entity is None:
            raise NotFoundException(f"该工具{tool_name}不存在")

        provider_entity = provider.provider_entity
        tool = provider.get_tool(tool_name)

        builtin_tool = {
            "provider": {**provider_entity.model_dump(exclude=["icon", "created_at"])},
            **tool_entity.model_dump(),
            "created_at": provider_entity.created_at,
            "inputs": self.get_tool_inputs(tool)
        }

        return builtin_tool

    def get_provider_icon(self, provider_name: str) -> tuple[bytes, str]:
        """根据传递的提供商获取icon"""
        provider = self.builtin_provider_manager.get_provider(provider_name)
        if provider is None:
            raise NotFoundException(f"该提供商{provider_name}不存在")

        root_path = os.path.dirname(os.path.dirname(current_app.root_path))
        provider_path = os.path.join(
            root_path,
            "internal", "core", "tools", "builtin_tools", "providers", provider_name
        )
        icon_path = os.path.join(provider_path, "_asset", provider.provider_entity.icon)

        if not os.path.exists(icon_path):
            raise NotFoundException("该提供商未提供图标")

        mimetype, _ = mimetypes.guess_type(icon_path)
        mimetype = mimetype or "application/octet-stream"
        with open(icon_path, "rb") as f:
            byte_data = f.read()
            return byte_data, mimetype

    def get_categories(self) -> list[dict[str, Any]]:
        """获取所有内置提供商的分类信息"""
        category_map = self.builtin_category_manager.get_category_map()
        return [{
            "name": category["entity"].name,
            "category": category["entity"].category,
            "icon": category["icon"]
        } for category in category_map.values()]

    @classmethod
    def get_tool_inputs(cls, tool) -> list:
        """根据传入的工具获取inputs信息"""
        inputs = []
        if hasattr(tool, "args_schema") and issubclass(tool.args_schema, BaseModel):
            inputs = []
            for field_name, model_field in tool.args_schema.__fields__.items():
                inputs.append({
                    "name": field_name,
                    "description": model_field.field_info.description or "",
                    "required": model_field.required,
                    "type": model_field.outer_type_.__name__,
                })
        return inputs