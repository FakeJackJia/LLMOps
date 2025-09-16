import mimetypes
import os.path
from dataclasses import dataclass
from typing import Any
from flask import current_app
from injector import inject

from internal.core.language_model import LanguageModelManager
from internal.exception import NotFoundException
from internal.core.language_model.entities.model_entity import BaseLanguageModel

from langchain_openai import ChatOpenAI

from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService

@inject
@dataclass
class LanguageModelService(BaseService):
    """LLM服务"""
    db: SQLAlchemy
    language_model_manager: LanguageModelManager

    def get_language_models(self) -> list[dict[str, Any]]:
        """获取所有LLM提供商"""
        providers = self.language_model_manager.get_providers()

        language_models = []
        for provider in providers:
            provider_entity = provider.provider_entity
            model_entities = provider.get_model_entities()

            language_model = {
                "name": provider_entity.name,
                "position": provider.position,
                "label": provider_entity.label,
                "icon": provider_entity.icon,
                "description": provider_entity.description,
                "background": provider_entity.background,
                "support_model_types": provider_entity.supported_model_types,
                "models": [{
                    "model_name": model_entity.model_name,
                    "label": model_entity.label,
                    "model_type": model_entity.model_type,
                    "context_window": model_entity.context_window,
                    "max_output_tokens": model_entity.max_output_tokens,
                    "features": model_entity.features,
                    "attributes": model_entity.attributes,
                    "metadata": model_entity.metadata,
                    "parameters": [{
                        "name": parameter.name,
                        "label": parameter.label,
                        "type": parameter.type.value,
                        "help": parameter.help,
                        "required": parameter.required,
                        "default": parameter.default,
                        "min": parameter.min,
                        "max": parameter.max,
                        "precision": parameter.precision,
                        "options": [{"label": option.label, "value": option.value} for option in parameter.options],
                    } for parameter in model_entity.parameters],
                } for model_entity in model_entities]
            }
            language_models.append(language_model)

        return language_models

    def get_language_model(self, provider_name: str, model_name: str) -> dict[str, Any]:
        """获取指定LLM提供商下的指定模型"""
        provider = self.language_model_manager.get_provider(provider_name)
        model_entity = provider.get_model_entity(model_name)

        language_model = {
            "model_name": model_entity.model_name,
            "label": model_entity.label,
            "model_type": model_entity.model_type,
            "context_window": model_entity.context_window,
            "max_output_tokens": model_entity.max_output_tokens,
            "features": model_entity.features,
            "attributes": model_entity.attributes,
            "metadata": model_entity.metadata,
            "parameters": [{
                "name": parameter.name,
                "label": parameter.label,
                "type": parameter.type.value,
                "help": parameter.help,
                "required": parameter.required,
                "default": parameter.default,
                "min": parameter.min,
                "max": parameter.max,
                "precision": parameter.precision,
                "options": [{"label": option.label, "value": option.value} for option in parameter.options],
            } for parameter in model_entity.parameters],
        }

        return language_model

    def get_language_model_icon(self, provider_name: str) -> tuple[bytes, str]:
        """获取指定LLM提供商图标"""
        provider = self.language_model_manager.get_provider(provider_name)

        root_path = os.path.dirname(os.path.dirname(current_app.root_path))

        provider_path = os.path.join(
            root_path,
            "internal", "core", "language_model", "providers", provider_name,
        )

        icon_path = os.path.join(provider_path, "_asset", provider.provider_entity.icon)

        if not os.path.exists(icon_path):
            raise NotFoundException("该LLM提供商未提供图标")

        mimetype, _ = mimetypes.guess_type(icon_path)
        mimetype = mimetype or "application/octet-stream"

        with open(icon_path, "rb") as f:
            byte_data = f.read()
            return byte_data, mimetype

    def load_language_model(self, model_config: dict[str, Any]) -> BaseLanguageModel:
        """根据传递的模型配置加载LLM模型, 并返回其实例"""
        try:
            provider_name = model_config.get("provider", "")
            model_name = model_config.get("model", "")
            parameters = model_config.get("parameters", {})

            provider = self.language_model_manager.get_provider(provider_name)
            model_entity = provider.get_model_entity(model_name)
            model_cls = provider.get_model_class(model_entity.model_type)

            return model_cls(
                **model_entity.attributes,
                **parameters,
                features=model_entity.features,
                metadata=model_entity.metadata
            )
        except Exception as e:
            return self.load_default_language_model()

    @classmethod
    def load_default_language_model(cls) -> BaseLanguageModel:
        """加载默认LLM模型"""
        return ChatOpenAI(model="gpt-4o-mini", temperature=1, max_tokens=8192)