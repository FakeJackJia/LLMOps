import os
from typing import Any, Optional, Type
import yaml
from injector import inject, singleton

from langchain_core.pydantic_v1 import BaseModel, Field, root_validator

from internal.exception import NotFoundException

from .entities.provider_entity import Provider, ProviderEntity
from .entities.model_entity import ModelType, BaseLanguageModel

@inject
@singleton
class LanguageModelManager(BaseModel):
    """LLM管理器"""
    provider_map: dict[str, Provider] = Field(default_factory=dict)

    @root_validator(pre=False)
    def validate_language_model_manager(cls, values: dict[str, Any]) -> dict[str, Any]:
        """校验提供商映射"""
        current_path = os.path.abspath(__file__)
        providers_path = os.path.join(os.path.dirname(current_path), "providers")
        providers_yaml_path = os.path.join(providers_path, "providers.yaml")

        with open(providers_yaml_path, encoding="utf-8") as f:
            providers_yaml_data = yaml.safe_load(f)

        values["provider_map"] = {}
        for index, provider_yaml_data in enumerate(providers_yaml_data):
            provider_entity = ProviderEntity(**provider_yaml_data)
            values["provider_map"][provider_entity.name] = Provider(
                name=provider_entity.name,
                position=index + 1,
                provider_entity=provider_entity
            )

        return values

    def get_provider(self, provider_name: str) -> Provider:
        """获取传递的提供商"""
        provider = self.provider_map.get(provider_name, None)
        if not provider:
            raise NotFoundException("该服务商不存在")
        return provider

    def get_providers(self) -> list[Provider]:
        """获取提供者列表"""
        return self.provider_map.values()

    def get_model_class_by_provider_and_type(
            self,
            provider_name: str,
            model_type: ModelType,
    ) -> Optional[Type[BaseLanguageModel]]:
        """根据提供者名字+模型类型获取模型类"""
        provider = self.get_provider(provider_name)
        return provider.get_model_class(model_type)

    def get_model_class_by_provider_and_model(
            self,
            provider_name: str,
            model_name: str
    ) -> Optional[Type[BaseLanguageModel]]:
        """根据传递的提供者名字+模型名字获取模型类"""
        provider = self.get_provider(provider_name)
        model_entity = provider.get_model_entity(model_name)

        return provider.get_model_class(model_entity.model_type)
