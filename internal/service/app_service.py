import json
from datetime import datetime
from threading import Thread
from typing import Any, Generator
from uuid import UUID
from flask import current_app
from dataclasses import dataclass
from injector import inject
from sqlalchemy import func, desc
from redis import Redis

from pkg.sqlalchemy import SQLAlchemy
from pkg.paginator import Paginator
from internal.model import (
    App,
    Account,
    AppConfigVersion,
    ApiTool,
    Dataset,
    AppConfig,
    AppDatasetJoin,
    Conversation,
    Message,
    Workflow
)
from internal.schema.app_schema import (
    CreateAppReq,
    GetPublishHistoriesWithPageReq,
    GetDebugConversationMessagesWithPageReq,
    GetAppsWithPageReq
)
from internal.exception import NotFoundException, ForbiddenException
from internal.entity.app_entity import AppStatus, AppConfigType, DEFAULT_APP_CONFIG
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.exception import ValidateErrorException, FailException
from internal.core.memory import TokenBufferMemory
from internal.core.tools.api_tools.providers import ApiProviderManager
from internal.entity.dataset_entity import RetrievalSource
from internal.entity.workflow_entity import WorkflowStatus
from internal.core.agent.agents import FunctionCallAgent, AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import QueueEvent
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.lib.helper import remove_fields, get_value_type, generate_random_string
from internal.core.language_model import LanguageModelManager
from internal.core.language_model.entities.model_entity import ModelParameterType

from .base_service import BaseService
from .retriever_service import RetrievalService
from .conversation_service import ConversationService
from .app_config_service import AppConfigService
from .language_model_service import LanguageModelService

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


@inject
@dataclass
class AppService(BaseService):
    """应用服务逻辑"""
    db: SQLAlchemy
    builtin_provider_manager: BuiltinProviderManager
    api_provider_manager: ApiProviderManager
    retrieval_service: RetrievalService
    conversation_service: ConversationService
    app_config_service: AppConfigService
    redis_client: Redis
    language_model_service: LanguageModelService
    language_model_manager: LanguageModelManager

    def create_app(self, req: CreateAppReq, account: Account) -> App:
        """创建Agent应用服务"""
        with self.db.auto_commit():
            app = App(
                account_id=account.id,
                name=req.name.data,
                icon=req.icon.data,
                description=req.description.data,
                status=AppStatus.DRAFT
            )
            self.db.session.add(app)
            self.db.session.flush()

            app_config_version = AppConfigVersion(
                app_id=app.id,
                version=0,
                config_type=AppConfigType.DRAFT,
                **DEFAULT_APP_CONFIG
            )
            self.db.session.add(app_config_version)
            self.db.session.flush()

            app.draft_app_config_id = app_config_version.id

        return app

    def get_app(self, app_id: UUID, account: Account) -> App:
        """根据传递的id获取应用基础信息"""
        app = self.get(App, app_id)

        if not app:
            raise NotFoundException("该应用不存在")

        if app.account_id != account.id:
            raise ForbiddenException("当前账号无权限访问该应用")

        return app

    def delete_app(self, app_id: UUID, account: Account) -> App:
        """根据传递的应用id+账号, 删除指定的应用信息, 目前仅删除应用信息即可"""
        app = self.get_app(app_id, account)
        self.delete(app)
        return app

    def update_app(self, app_id: UUID, account: Account, **kwargs) -> App:
        """根据传递的应用id+账号+信息, 更新指定的应用"""
        app = self.get_app(app_id, account)
        self.update(app, **kwargs)
        return app

    def get_apps_with_page(self, req: GetAppsWithPageReq, account: Account) -> tuple[list[App], Paginator]:
        """根据传递的分页参数获取当前登录账号下的应用分页列表数据"""
        paginator = Paginator(db=self.db, req=req)

        filters = [App.account_id == account.id]
        if req.search_word.data:
            filters.append(App.name.ilike(f"%{req.search_word.data}%"))

        apps = paginator.paginate(
            self.db.session.query(App).filter(*filters).order_by(desc("created_at"))
        )

        return apps, paginator

    def copy_app(self, app_id: UUID, account: Account) -> App:
        """根据传递的应用id拷贝Agent相关信息并创建一个新的Agent"""
        app = self.get_app(app_id, account)
        draft_app_config = app.draft_app_config

        app_dict = app.__dict__.copy()
        draft_app_config_dict = draft_app_config.__dict__.copy()

        app_remove_fields = [
            "id", "app_config_id", "draft_app_config_id", "debug_conversation_id",
            "status", "updated_at", "created_at", "_sa_instance_state"
        ]
        draft_app_config_remove_fields = [
             "id", "app_id", "version", "updated_at",
             "created_at", "_sa_instance_state"
        ]

        remove_fields(app_dict, app_remove_fields)
        remove_fields(draft_app_config_dict, draft_app_config_remove_fields)

        with self.db.auto_commit():
            new_app = App(**app_dict, status=AppStatus.DRAFT)
            self.db.session.add(new_app)
            self.db.session.flush()

            new_draft_app_config = AppConfigVersion(
                **draft_app_config_dict,
                app_id=new_app.id,
                version=0
            )
            self.db.session.add(new_draft_app_config)
            self.db.session.flush()

            new_app.draft_app_config_id = new_draft_app_config.id

        return new_app

    def get_draft_app_config(self, app_id: UUID, account: Account) -> dict[str, Any]:
        """根据传递的应用id, 获取指定的应用草稿配置信息"""
        app = self.get_app(app_id, account)
        return self.app_config_service.get_draft_app_config(app)

    def update_draft_app_config(
            self,
            app_id: UUID,
            draft_app_config: dict[str, Any],
            account: Account
    ) -> AppConfigVersion:
        """根据传递的应用id+草稿配置修改指定应用的最新草稿"""
        app = self.get_app(app_id, account)

        draft_app_config = self._validate_draft_app_config(draft_app_config, account)

        draft_app_config_record = app.draft_app_config
        self.update(
            draft_app_config_record
            **draft_app_config,
        )

        return draft_app_config_record

    def publish_draft_app_config(self, app_id: UUID, account: Account) -> App:
        """根据传递的应用id, 发布/更新指定的应用草稿配置为运行时配置"""
        app = self.get_app(app_id, account)
        draft_app_config = self.get_draft_app_config(app_id, account)

        app_config = self.create(
            AppConfig,
            app_id=app_id,
            model_config=draft_app_config["model_config"],
            dialog_round=draft_app_config["dialog_round"],
            preset_prompt=draft_app_config["preset_prompt"],
            tools=[
                {
                    "type": tool["type"],
                    "provider_id": tool["provider"]["id"],
                    "tool_id": tool["tool"]["name"],
                    "params": tool["tool"]["params"]
                }
                for tool in draft_app_config["tools"]
            ],
            workflows=[workflow["id"] for workflow in draft_app_config["workflows"]],
            retrieval_config=draft_app_config["retrieval_config"],
            long_term_memory=draft_app_config["long_term_memory"],
            opening_statement=draft_app_config["opening_statement"],
            opening_questions=draft_app_config["opening_questions"],
            suggested_after_answer=draft_app_config["suggested_after_answer"],
            review_config=draft_app_config["review_config"],
        )

        self.update(app, app_config_id=app_config.id, status=AppStatus.PUBLISHED)

        with self.db.auto_commit():
            self.db.session.query(AppDatasetJoin).filter(
                AppDatasetJoin.app_id == app_id,
            ).delete()

        for dataset in draft_app_config["datasets"]:
            self.create(AppDatasetJoin, app_id=app_id, dataset_id=dataset["id"])

        draft_app_config_copy = app.draft_app_config.__dict__.copy()
        remove_fields(
            draft_app_config_copy,
            ["id", "version", "config_type", "updated_at", "created_at", "_sa_instance_state"]
        )

        max_version = self.db.session.query(func.coalesce(func.max(AppConfigVersion.version), 0)).filter(
            AppConfigVersion.app_id == app_id,
            AppConfigVersion.config_type == AppConfigType.PUBLISHED,
        ).scalar()

        # 新增发布历史配置, 可用于回退
        self.create(
            AppConfigVersion,
            version=max_version + 1,
            config_type=AppConfigType.PUBLISHED,
            **draft_app_config_copy,
        )

        return app

    def cancel_publish_app_config(self, app_id: UUID, account: Account) -> App:
        """根据传递的应用id取消发布"""
        app = self.get_app(app_id, account)

        if app.status != AppStatus.PUBLISHED:
            raise FailException("当前应用未发布")

        self.update(app, status=AppStatus.DRAFT, app_config_id=None)

        with self.db.auto_commit():
            self.db.session.query(AppDatasetJoin).filter(
                AppDatasetJoin.app_id == app_id,
            ).delete()

        return app

    def get_publish_histories_with_page(
            self,
            app_id: UUID,
            req: GetPublishHistoriesWithPageReq,
            account: Account
    ) -> tuple[list[AppConfigVersion], Paginator]:
        """根据传递的应用id, 获取应用发布历史列表"""
        self.get_app(app_id, account)

        paginator = Paginator(db=self.db, req=req)
        app_config_versions =paginator.paginate(
            self.db.session.query(AppConfigVersion).filter(
                AppConfigVersion.app_id == app_id,
                AppConfigVersion.config_type == AppConfigType.PUBLISHED,
            ).order_by(desc("version"))
        )

        return app_config_versions, paginator

    def fallback_history_to_draft(
            self,
            app_id: UUID,
            app_config_version_id: UUID,
            account: Account
    ) -> AppConfigVersion:
        """根据传递的应用id+历史版本配置id, 回退到草稿中"""
        app = self.get_app(app_id, account)

        app_config_version = self.get(AppConfigVersion, app_config_version_id)
        if not app_config_version:
            raise NotFoundException("该历史版本不存在")

        draft_app_config_dict = app_config_version.__dict__.copy()
        remove_fields(
            draft_app_config_dict,
            ["id", "app_id", "version", "config_type", "updated_at", "created_at", "_sa_instance_state"]
        )

        draft_app_config_dict = self._validate_draft_app_config(draft_app_config_dict, account)
        draft_app_config_record = app.draft_app_config
        self.update(
            draft_app_config_record,
            **draft_app_config_dict
        )

        return draft_app_config_record

    def get_debug_conversation_summary(self, app_id: UUID, account: Account) -> str:
        """根据传递的应用id获取调试会话长期记忆"""
        app = self.get_app(app_id, account)

        draft_app_config = self.get_draft_app_config(app_id, account)
        if draft_app_config["long_term_memory"]["enable"] is False:
            raise FailException("该应用并未开启长期记忆")

        return app.debug_conversation.summary

    def update_debug_conversation_summary(self, app_id: UUID, summary: str, account: Account) -> Conversation:
        """根据传递的应用id+摘要信息更新调试会话长期记忆"""
        app = self.get_app(app_id, account)

        draft_app_config = self.get_draft_app_config(app_id, account)
        if draft_app_config["long_term_memory"]["enable"] is False:
            raise FailException("该应用并未开启长期记忆")

        debug_conversation = app.debug_conversation
        self.update(debug_conversation, summary=summary)
        return debug_conversation

    def delete_debug_conversation(self, app_id: UUID, account: Account) -> App:
        """根据传递的应用id, 清空该应用的调试会话记录"""
        app = self.get_app(app_id, account)

        if not app.debug_conversation_id:
            return app

        self.update(app, debug_conversation_id=None)
        return app

    def debug_chat(self, app_id: UUID, query: str, account: Account) -> Generator:
        """根据传递的应用id+提问query向特定的应用发起会话调试"""
        app = self.get_app(app_id, account)

        draft_app_config = self.get_draft_app_config(app_id, account)
        debug_conversation = app.debug_conversation

        message = self.create(
            Message,
            app_id=app_id,
            conversation_id=debug_conversation.id,
            created_by=account.id,
            invoke_from=InvokeFrom.DEBUGGER,
            query=query,
            status=MessageStatus.NORMAL,
        )

        llm = self.language_model_service.load_language_model(draft_app_config.get("model_config", {}))

        token_buffer_memory = TokenBufferMemory(
            db=self.db,
            conversation=debug_conversation,
            model_instance=llm,
        )
        history = token_buffer_memory.get_history_prompt_message(
            message_limit=draft_app_config["dialog_round"],
        )

        tools = self.app_config_service.get_langchain_tools_by_tools_config(draft_app_config["tools"])

        if draft_app_config["datasets"]:
            dataset_retrieval = self.retrieval_service.create_langchain_tool_from_search(
                flask_app=current_app._get_current_object(),
                dataset_ids=[UUID(dataset["id"]) for dataset in draft_app_config["datasets"]],
                account_id=account.id,
                retrieval_source=RetrievalSource.APP,
                **draft_app_config["retrieval_config"]
            )
            tools.append(dataset_retrieval)

        if draft_app_config["workflows"]:
            workflow_tools = self.app_config_service.get_langchain_tools_by_workflow_ids(
                [workflow["id"] for workflow in draft_app_config["workflows"]]
            )
            tools.extend(workflow_tools)

        agent = FunctionCallAgent(
            llm=llm,
            agent_config=AgentConfig(
                user_id=account.id,
                invoke_from=InvokeFrom.DEBUGGER,
                preset_prompt=draft_app_config["preset_prompt"],
                enable_long_term_memory=draft_app_config["long_term_memory"]["enable"],
                tools=tools,
                review_config=draft_app_config["review_config"]
            )
        )

        agent_thoughts = {}
        for agent_thought in agent.stream({
            "messages": [HumanMessage(query)],
            "history": history,
            "long_term_memory": debug_conversation.summary,
        }):
            event_id = str(agent_thought.id)

            if agent_thought.event != QueueEvent.PING:
                if agent_thought.event == QueueEvent.AGENT_MESSAGE:
                    if event_id not in agent_thoughts:
                        agent_thoughts[event_id] = agent_thought
                    else:
                        agent_thoughts[event_id] = agent_thoughts[event_id].model_copy(update={
                            "thought": agent_thoughts[event_id].thought + agent_thought.thought,
                            "message": agent_thought.message,
                            "message_token_count": agent_thought.message_token_count,
                            "message_unit_price": agent_thought.message_unit_price,
                            "message_price_unit": agent_thought.message_price_unit,
                            "answer": agent_thoughts[event_id].answer + agent_thought.answer,
                            "answer_token_count": agent_thought.answer_token_count,
                            "answer_unit_price": agent_thought.answer_unit_price,
                            "answer_price_unit": agent_thought.answer_price_unit,
                            "total_token_count": agent_thought.total_token_count,
                            "total_price": agent_thought.total_price,
                            "latency": agent_thought.latency
                        })
                else:
                    agent_thoughts[event_id] = agent_thought

            data = {
                **agent_thought.model_dump(include={
                    "event", "thought", "observation", "tool", "tool_input", "answer", "latency",
                    "total_token_count", "total_price"
                }),
                "id": event_id,
                "conversation_id": str(debug_conversation.id),
                "message_id": str(message.id),
                "task_id": str(agent_thought.task_id)
            }

            yield f"event: {agent_thought.event}\ndata:{json.dumps(data)}\n\n"

        self.conversation_service.save_agent_thoughts(**{
                "account_id": account.id,
                "app_id": app.id,
                "conversation_id": debug_conversation.id,
                "message_id": message.id,
                "agent_thoughts": [agent_thought for agent_thought in agent_thoughts.values()],
                "app_config": draft_app_config
            }
        )

    def stop_debug_chat(self, app_id: UUID, task_id: UUID, account: Account) -> None:
        """根据传递的应用id+任务id停止某个应用的指定调试会话"""
        self.get_app(app_id, account)

        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, account.id)

    def get_debug_conversation_messages_with_page(
            self,
            app_id: UUID,
            req: GetDebugConversationMessagesWithPageReq,
            account: Account
    ) -> tuple[list[Message], Paginator]:
        """根据传递的应用id+请求数据, 获取调试会话消息列表分页数据"""
        app = self.get_app(app_id, account)

        debug_conversation = app.debug_conversation

        paginator = Paginator(db=self.db, req=req)
        filters = []
        if req.created_at.data is not None:
            # 将时间戳转换成DateTime
            created_at_datetime = datetime.fromtimestamp(req.created_at.data)
            filters.append(Message.created_at >= created_at_datetime)

        messages = paginator.paginate(
            self.db.session.query(Message).filter(
                Message.conversation_id == debug_conversation.id,
                Message.status.in_([MessageStatus.STOP, MessageStatus.NORMAL]),
                Message.answer != "",
                Message.is_deleted == False,
                *filters
            ).order_by(desc("created_at"))
        )

        return messages, paginator

    def get_published_config(self, app_id: UUID, account: Account) -> dict[str, Any]:
        """获取应用发布需要的配置"""
        app = self.get_app(app_id, account)

        return {
            "web_app": {
                "token": app.token_with_default,
                "status": app.status
            }
        }

    def regenerate_web_app_token(self, app_id: UUID, account: Account) -> str:
        """重新生成WebApp凭证"""
        app = self.get_app(app_id, account)

        if app.status != AppStatus.PUBLISHED:
            raise FailException("应用未先发布")

        token = generate_random_string()
        self.update(app, token=token)

        return token

    def _validate_draft_app_config(self, draft_app_config: dict[str, Any], account: Account) -> dict[str, Any]:
        """校验传递的应用草稿配置信息"""
        acceptable_fields = [
            "model_config", "dialog_round", "preset_prompt",
            "tools", "workflows", "datasets", "retrieval_config",
            "long_term_memory", "opening_statement", "opening_questions",
            "suggested_after_answer", "review_config",
        ]

        if (
            not draft_app_config
            or not isinstance(draft_app_config, dict)
            or set(draft_app_config.keys()) - set(acceptable_fields)
        ):
            raise ValidateErrorException("草稿配置字段出错")

        if "model_config" in draft_app_config:
            model_config = draft_app_config["model_config"]
            if not isinstance(model_config, dict):
                raise ValidateErrorException("模型格式错误")

            if set(model_config.keys()) != {"provider", "model", "parameters"}:
                raise ValidateErrorException("模型key传递错误")

            if not model_config["provider"] or not isinstance(model_config["provider"], str):
                raise ValidateErrorException("模型provider类型必须是字符串")
            provider = self.language_model_manager.get_provider(model_config["provider"])
            if not provider:
                raise ValidateErrorException("该模型提供商不存在")

            if not model_config["model"] or not isinstance(model_config["model"], str):
                raise ValidateErrorException("模型model必须是字符串")
            model_entity = provider.get_model_entity(model_config["model"])
            if not model_entity:
                raise ValidateErrorException("该LLM模型不存在")

            if not model_config["parameters"] or not isinstance(model_config['parameters'], dict):
                model_config["parameters"] = {
                    parameter.name: parameter.default for parameter in model_entity.parameters
                }

            parameters = {}
            for parameter in model_entity.parameters:
                parameter_value = model_config["parameters"].get(parameter.name, parameter.default)

                if parameter.required:
                    if parameter_value is None or get_value_type(parameter_value) != parameter.type.value:
                        parameter_value = parameter.default
                else:
                    if parameter_value is not None:
                        if get_value_type(parameter_value) != parameter.type.value:
                            parameter_value = parameter.default

                if parameter.options and parameter_value not in parameter.options:
                    parameter_value = parameter.default

                if parameter.type in [ModelParameterType.INT, ModelParameterType.FLOAT] and parameters is not None:
                    if (
                            (parameter.min and parameter_value < parameter.min)
                            or (parameter.max and parameter_value > parameter.max)
                    ):
                        parameter_value = parameter.default

                parameters[parameter.name] = parameter_value

            model_config["parameters"] = parameters
            draft_app_config["model_config"] = model_config

        if "dialog_round" in draft_app_config:
            dialog_round  = draft_app_config["dialog_round"]
            if (
                not isinstance(dialog_round, int)
                or not (0 <= dialog_round <= 100)
            ):
                raise ValidateErrorException("携带上下文范围数为0-100")

        if "preset_prompt" in draft_app_config:
            preset_prompt = draft_app_config["preset_prompt"]
            if (
                not isinstance(preset_prompt, str)
                or len(preset_prompt) > 2000
            ):
                raise ValidateErrorException("人设与回复逻辑必须是字符串, 长度在0-2000个字符")

        if "tools" in draft_app_config:
            tools = draft_app_config["tools"]
            validate_tools = []

            if not isinstance(tools, list):
                raise ValidateErrorException("工具列表必须是列表型数据")
            if len(tools) > 5:
                raise ValidateErrorException("Agent绑定的工具数不能超过5")

            for tool in tools:
                if not tool or not isinstance(tool, dict):
                    raise ValidateErrorException("绑定插件工具参数出错")
                if set(tool.keys()) != {"type", "provider_id", "tool_id", "params"}:
                    raise ValidateErrorException("绑定插件工具参数出错")
                if tool["type"] not in ["builtin_tool", "api_tool"]:
                    raise ValidateErrorException("绑定插件工具参数出错")
                if (
                    not tool["provider_id"]
                    or not tool["tool_id"]
                    or not isinstance(tool["provider_id"], str)
                    or not isinstance(tool["tool_id"], str)
                ):
                    raise ValidateErrorException("插件提供者或者插件标识参数出错")
                if not isinstance(tool["params"], dict):
                    raise ValidateErrorException("插件自定义参数格式错误")
                if tool["type"] == "builtin_tool":
                    builtin_tool = self.builtin_provider_manager.get_tool(tool["provider_id"], tool["tool_id"])
                    if not builtin_tool:
                        continue
                else:
                    api_tool = self.db.session.query(ApiTool).filter(
                        ApiTool.provider_id == tool["provider_id"],
                        ApiTool.name == tool["tool_id"],
                        ApiTool.account_id == account.id,
                    ).one_or_none()
                    if not api_tool:
                        continue

                validate_tools.append(tool)

            check_tools = [f"{tool['provider_id']}_{tool['tool_id']}" for tool in validate_tools]
            if len(set(check_tools)) != len(validate_tools):
                raise ValidateErrorException("绑定插件存在重复")

            draft_app_config["tools"] = validate_tools

        if "workflows" in draft_app_config:
            workflows = draft_app_config["workflows"]

            if not isinstance(workflows, list):
                raise ValidateErrorException("绑定工作流列表错误")

            if len(workflows) > 5:
                raise ValidateErrorException("Agent最多绑定5个工作流")

            for workflow_id in workflows:
                try:
                    UUID(workflow_id)
                except Exception:
                    raise ValidateErrorException("工作流列表参数必须是UUID")

            if len(set(workflows)) != len(workflows):
                raise ValidateErrorException("工作流重复绑定")

            workflow_records = self.db.session.query(Workflow).filter(
                Workflow.id.in_(workflows),
                Workflow.account_id == account.id,
                Workflow.status == WorkflowStatus.PUBLISHED
            ).all()
            workflow_sets = set([str(workflow_record.id) for workflow_record in workflow_records])
            draft_app_config["workflows"] = [workflow_id for workflow_id in workflows if workflow_id in workflow_sets]

        if "datasets" in draft_app_config:
            datasets = draft_app_config["datasets"]

            if not isinstance(datasets, list):
                raise ValidateErrorException("绑定知识库列表参数格式错误")
            if len(datasets) > 5:
                raise ValidateErrorException("Agent绑定的知识库数量不能超过5个")

            for dataset_id in datasets:
                try:
                    UUID(dataset_id)
                except Exception as e:
                    raise ValidateErrorException("知识库列表参数必须是UUID")

            if len(set(datasets)) != len(datasets):
                raise ValidateErrorException("绑定知识库存在重复")

            dataset_records = self.db.session.query(Dataset).filter(
                Dataset.id.in_(datasets),
                Dataset.account_id == account.id,
            ).all()
            dataset_sets = set([str(dataset_record.id) for dataset_record in dataset_records])
            draft_app_config["datasets"] = [dataset_id for dataset_id in datasets if dataset_id in dataset_sets]

        if "retrieval_config" in draft_app_config:
            retrieval_config = draft_app_config["retrieval_config"]

            if not retrieval_config or not isinstance(retrieval_config, dict):
                raise ValidateErrorException("检索配置格式错误")
            if set(retrieval_config.keys()) != {"retrieval_strategy", "k", "score"}:
                raise ValidateErrorException("检索配置格式错误")
            if retrieval_config["retrieval_strategy"] not in ["semantic", "full_text", "hybrid"]:
                raise ValidateErrorException("检索策略格式错误")
            if not isinstance(retrieval_config["k"], int) or not (0 <= retrieval_config["k"] <= 10):
                raise ValidateErrorException("最大召回数量范围为0-10")
            if not isinstance(retrieval_config["score"], float) or not (0 <= retrieval_config["score"] <= 1):
                raise ValidateErrorException("最小匹配范围为0-1")

        if "long_term_memory" in draft_app_config:
            long_term_memory = draft_app_config["long_term_memory"]

            if not long_term_memory or not isinstance(long_term_memory, dict):
                raise ValidateErrorException("长期记忆设置格式错误")
            if (
                set(long_term_memory.keys()) != {"enable"}
                or not isinstance(long_term_memory["enable"], bool)
            ):
                raise ValidateErrorException("长期记忆设置格式错误")

        if "opening_statement" in draft_app_config:
            opening_statement = draft_app_config["opening_statement"]

            if not isinstance(opening_statement, str) or len(opening_statement) > 2000:
                raise ValidateErrorException("对话开场白的长度范围是0-2000")

        if "opening_questions" in draft_app_config:
            opening_questions = draft_app_config["opening_questions"]

            if not isinstance(opening_questions, list) or len(opening_questions) > 3:
                raise ValidateErrorException("开场建议问题不能超过3个")
            for opening_question in opening_questions:
                if not isinstance(opening_question, str):
                    raise ValidateErrorException("开场建议问题必须是字符串")

        if "suggested_after_answer" in draft_app_config:
            suggested_after_answer = draft_app_config["suggested_after_answer"]

            if not suggested_after_answer or not isinstance(suggested_after_answer, dict):
                raise ValidateErrorException("回答后建议问题设置格式错误")
            if (
                    set(suggested_after_answer.keys()) != {"enable"}
                    or not isinstance(suggested_after_answer["enable"], bool)
            ):
                raise ValidateErrorException("回答后建议问题设置格式错误")

        if "review_config" in draft_app_config:
            review_config = draft_app_config["review_config"]

            if not review_config or not isinstance(review_config, dict):
                raise ValidateErrorException("审核配置格式错误")
            if set(review_config.keys()) != {"enable", "keywords", "inputs_config", "outputs_config"}:
                raise ValidateErrorException("审核配置格式错误")
            if not isinstance(review_config["enable"], bool):
                raise ValidateErrorException("审核enable格式错误")
            if (
                    not isinstance(review_config["keywords"], list)
                    or (review_config["enable"] and len(review_config["keywords"]) == 0)
                    or len(review_config["keywords"]) > 100
            ):
                raise ValidateErrorException("审核keywords非空且不能超过100个关键词")
            for keyword in review_config["keywords"]:
                if not isinstance(keyword, str):
                    raise ValidateErrorException("审核keywords敏感词必须是字符串")
            if (
                    not review_config["inputs_config"]
                    or not isinstance(review_config["inputs_config"], dict)
                    or set(review_config["inputs_config"].keys()) != {"enable", "preset_response"}
                    or not isinstance(review_config["inputs_config"]["enable"], bool)
                    or not isinstance(review_config["inputs_config"]["preset_response"], str)
            ):
                raise ValidateErrorException("审核inputs_config必须是一个字典")
            if (
                    not review_config["outputs_config"]
                    or not isinstance(review_config["outputs_config"], dict)
                    or set(review_config["outputs_config"].keys()) != {"enable"}
                    or not isinstance(review_config["outputs_config"]["enable"], bool)
            ):
                raise ValidateErrorException("审核outputs_config格式错误")
            if review_config["enable"]:
                if (
                        review_config["inputs_config"]["enable"] is False
                        and review_config["outputs_config"]["enable"] is False
                ):
                    raise ValidateErrorException("输入审核和输出审核至少需要开启一项")

                if (
                        review_config["inputs_config"]["enable"]
                        and review_config["inputs_config"]["preset_response"].strip() == ""
                ):
                    raise ValidateErrorException("输入审核预设响应不能为空")

        return draft_app_config