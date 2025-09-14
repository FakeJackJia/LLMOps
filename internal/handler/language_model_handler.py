import io
from injector import inject
from dataclasses import dataclass
from flask import send_file
from flask_login import login_required

from internal.service import LanguageModelService

from pkg.response import success_json


@inject
@dataclass
class LanguageModelHandler:
    """LLM处理器"""
    language_model_service: LanguageModelService

    @login_required
    def get_language_models(self):
        """获取所有LLM提供商"""
        return success_json(self.language_model_service.get_language_models())

    @login_required
    def get_language_model(self, provider_name: str, model_name: str):
        """获取指定LLM提供商下的指定模型"""
        return success_json(self.language_model_service.get_language_model(provider_name, model_name))

    def get_language_model_icon(self, provider_name: str):
        """获取指定LLM提供商的图标"""
        icon, mimetypes = self.language_model_service.get_language_model_icon(provider_name)
        return send_file(io.BytesIO(icon), mimetypes)