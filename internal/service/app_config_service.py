from typing import Any, Union

from flask import request
from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy

from internal.model import App, ApiTool, Dataset, AppConfig, AppConfigVersion
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.core.tools.api_tools.providers import ApiProviderManager
from internal.lib.helper import datetime_to_timestamp
from internal.core.tools.api_tools.entities import ToolEntity

from langchain_core.tools import BaseTool


@inject
@dataclass
class AppConfigService(BaseService):
    """应用配置服务"""
    db: SQLAlchemy
    builtin_provider_manager: BuiltinProviderManager
    api_provider_manager: ApiProviderManager

    def get_draft_app_config(self, app: App) -> dict[str, Any]:
        """根据传递的应用获取该应用的草稿配置"""
        draft_app_config = app.draft_app_config

        # todo: 校验model_config配置信息, 等待多LLM实现的时候再来完成

        # 校验工具列表
        tools, validate_tools = self._process_and_validate_tools(draft_app_config.tools)

        if len(validate_tools) != len(draft_app_config.tools):
            self.update(draft_app_config, tools=validate_tools)

        datasets, validate_datasets = self._process_and_validate_datasets(draft_app_config.datasets)

        if len(validate_datasets) != len(draft_app_config.datasets):
            self.update(draft_app_config, datasets=validate_datasets)

        # todo: 校验工作流
        workflows = []

        return self._process_and_transform_app_config(tools, workflows, datasets, draft_app_config)

    def get_app_config(self, app: App) -> dict[str, Any]:
        """根据传递的应用获取该应用的运行配置"""

    def get_langchain_tools_by_tools_config(self, tools_config: list[dict]) -> list[BaseTool]:
        """根据传递的工具配置列表获langchain工具列表"""
        tools = []
        for tool in tools_config:
            if tool["type"] == "builtin_tool":
                builtin_tool = self.builtin_provider_manager.get_tool(
                    tool["provider"]["id"],
                    tool["tool"]["name"]
                )

                if not builtin_tool:
                    continue

                tools.append(builtin_tool(**tool["tool"]["params"]))
            else:
                api_tool = self.get(ApiTool, tool["tool"]["id"])

                if not api_tool:
                    continue

                tools.append(
                    self.api_provider_manager.get_tool(
                        ToolEntity(
                            id=str(api_tool.id),
                            name=api_tool.name,
                            url=api_tool.url,
                            method=api_tool.method,
                            description=api_tool.description,
                            headers=api_tool.provider.headers,
                            parameters=api_tool.parameters,
                        )
                    )
                )

        return tools

    @classmethod
    def _process_and_transform_app_config(
            cls,
            tools: list[dict],
            workflows: list[dict],
            datasets: list[dict],
            app_config: Union[AppConfig, AppConfigVersion]
    ) -> dict[str, Any]:
        """根据传递的工具列表, 工作流, 知识库以及应用配置信息返回配置"""
        return {
            "id": str(app_config.id),
            "model_config": app_config.model_config,
            "dialog_round": app_config.dialog_round,
            "preset_prompt": app_config.preset_prompt,
            "tools": tools,
            "workflows": workflows,
            "datasets": datasets,
            "retrieval_config": app_config.retrieval_config,
            "long_term_memory": app_config.long_term_memory,
            "opening_statement": app_config.opening_statement,
            "opening_questions": app_config.opening_questions,
            "speech_to_text": app_config.speech_to_text,
            "text_to_speech": app_config.text_to_speech,
            "suggested_after_answer": app_config.suggested_after_answer,
            "review_config": app_config.review_config,
            "updated_at": datetime_to_timestamp(app_config.updated_at),
            "created_at": datetime_to_timestamp(app_config.created_at),
        }

    def _process_and_validate_tools(self, origin_tools: list[dict]) -> tuple[list[dict], list[dict]]:
        """根据传递的原始工具信息进行处理和校验"""
        validate_tools = []
        tools = []
        for tool in origin_tools:
            if tool["type"] == "builtin_tool":
                provider = self.builtin_provider_manager.get_provider(tool["provider_id"])
                if not provider:
                    continue

                tool_entity = provider.get_tool_entity(tool["tool_id"])
                if not tool_entity:
                    continue

                param_keys = set([param.name for param in tool_entity.params])
                if set(tool["params"].keys()) - param_keys:
                    continue

                validate_tools.append(tool)

                # 组装内置工具展示信息
                provider_entity = provider.provider_entity
                tools.append({
                    "type": "builtin_tool",
                    "provider": {
                        "id": provider_entity.name,
                        "name": provider_entity.name,
                        "label": provider_entity.label,
                        "icon": f"{request.scheme}://{request.host}/builtin-tools/{provider_entity.name}/icon",
                        "description": provider_entity.description,
                    },
                    "tool": {
                        "id": tool_entity.name,
                        "name": tool_entity.name,
                        "label": tool_entity.label,
                        "description": tool_entity.description,
                        "params": tool["params"],
                    }
                })

            elif tool["type"] == "api_tool":
                tool_record = self.db.session.query(ApiTool).filter(
                    ApiTool.provider_id == tool["provider_id"],
                    ApiTool.name == tool["tool_id"],
                ).one_or_none()

                if not tool_record:
                    continue

                validate_tools.append(tool)

                provider = tool_record.provider
                tools.append({
                    "type": "api_tool",
                    "provider": {
                        "id": str(provider.id),
                        "name": provider.name,
                        "label": provider.name,
                        "icon": provider.icon,
                        "description": provider.description,
                    },
                    "tool": {
                        "id": str(tool_record.id),
                        "name": tool_record.name,
                        "label": tool_record.name,
                        "description": tool_record.description,
                        "params": {},
                    }
                })

        return tools, validate_tools

    def _process_and_validate_datasets(self, original_datasets: list[str]) -> tuple[list[dict], list[str]]:
        """根据传递的知识库进行处理和校验"""
        datasets = []
        dataset_records = self.db.session.query(Dataset).filter(Dataset.id.in_(original_datasets)).all()
        dataset_dict = {str(dataset_record.id): dataset_record for dataset_record in dataset_records}
        dataset_sets = set(dataset_dict.keys())
        validate_datasets = [dataset_id for dataset_id in original_datasets if dataset_id in dataset_sets]

        for dataset_id in validate_datasets:
            dataset = dataset_dict.get(str(dataset_id))
            datasets.append({
                "id": str(dataset_id),
                "name": dataset.name,
                "icon": dataset.icon,
                "description": dataset.description,
            })

        return datasets, validate_datasets