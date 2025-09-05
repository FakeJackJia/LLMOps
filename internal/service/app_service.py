import json
from datetime import datetime
from threading import Thread
from typing import Any, Generator
from uuid import UUID
from flask import request, current_app, Flask
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
    MessageAgentThought
)
from internal.schema.app_schema import (
    CreateAppReq,
    GetPublishHistoriesWithPageReq,
    GetDebugConversationMessagesWithPageReq,
)
from internal.exception import NotFoundException, ForbiddenException
from internal.entity.app_entity import AppStatus, AppConfigType, DEFAULT_APP_CONFIG
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.lib.helper import datetime_to_timestamp
from internal.exception import ValidateErrorException, FailException
from internal.core.memory import TokenBufferMemory
from internal.core.tools.api_tools.providers import ApiProviderManager
from internal.core.tools.api_tools.entities import ToolEntity
from internal.entity.dataset_entity import RetrievalSource
from internal.core.agent.agents import FunctionCallAgent, AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import QueueEvent
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from .base_service import BaseService
from .retriever_service import RetrievalService
from .conversation_service import ConversationService

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
    redis_client: Redis

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

    def get_draft_app_config(self, app_id: UUID, account: Account) -> dict[str, Any]:
        """根据传递的应用id, 获取指定的应用草稿配置信息"""
        app = self.get_app(app_id, account)

        draft_app_config = app.draft_app_config

        # todo: 校验model_config配置信息, 等待多LLM实现的时候再来完成

        # 校验工具列表
        draft_tools = draft_app_config.tools
        validate_tools = []
        tools = []
        for draft_tool in draft_tools:
            if draft_tool["type"] == "builtin_tool":
                provider = self.builtin_provider_manager.get_provider(draft_tool["provider_id"])
                if not provider:
                    continue

                tool_entity = provider.get_tool_entity(draft_tool["tool_id"])
                if not tool_entity:
                    continue

                param_keys = set([param.name for param in tool_entity.params])
                if set(draft_tool["params"].keys()) - param_keys:
                    continue

                validate_tools.append(draft_tool)

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
                        "params": draft_tool["params"],
                    }
                })

            elif draft_tool["type"] == "api_tool":
                tool_record = self.db.session.query(ApiTool).filter(
                    ApiTool.provider_id == draft_tool["provider_id"],
                    ApiTool.name == draft_tool["tool_id"],
                ).one_or_none()

                if not tool_record:
                    continue

                validate_tools.append(draft_tool)

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

        if len(validate_tools) != len(draft_tools):
            self.update(draft_app_config, tools=validate_tools)

        datasets = []
        draft_datasets = draft_app_config.datasets
        dataset_records = self.db.session.query(Dataset).filter(Dataset.id.in_(draft_datasets)).all()
        dataset_dict = {str(dataset_record.id): dataset_record for dataset_record in dataset_records}
        dataset_sets = set(dataset_dict.keys())
        exist_dataset_ids = [dataset_id for dataset_id in draft_datasets if dataset_id in dataset_sets]

        if len(exist_dataset_ids) != len(draft_datasets):
            self.update(draft_app_config, datasets=exist_dataset_ids)

        for dataset_id in exist_dataset_ids:
            dataset = dataset_dict.get(str(dataset_id))
            datasets.append({
                "id": str(dataset_id),
                "name": dataset.name,
                "icon": dataset.icon,
                "description": dataset.description,
            })

        # todo: 校验工作流
        workflow = []

        return {
            "id": str(draft_app_config.id),
            "model_config": draft_app_config.model_config,
            "dialog_round": draft_app_config.dialog_round,
            "preset_prompt": draft_app_config.preset_prompt,
            "tools": tools,
            "workflows": workflow,
            "datasets": datasets,
            "retrieval_config": draft_app_config.retrieval_config,
            "long_term_memory": draft_app_config.long_term_memory,
            "opening_statement": draft_app_config.opening_statement,
            "opening_questions": draft_app_config.opening_questions,
            "speech_to_text": draft_app_config.speech_to_text,
            "text_to_speech": draft_app_config.text_to_speech,
            "suggested_after_answer": draft_app_config.suggested_after_answer,
            "review_config": draft_app_config.review_config,
            "updated_at": datetime_to_timestamp(draft_app_config.updated_at),
            "created_at": datetime_to_timestamp(draft_app_config.created_at),
        }

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
            draft_app_config_record,
            # todo: 由于目前使用server_onupdate, 所以该字段暂时需要手动传递
            updated_at=datetime.now(),
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
            # todo: 工作流模块完成后 该处可能发生变动
            workflows=draft_app_config["workflows"],
            retrieval_config=draft_app_config["retrieval_config"],
            long_term_memory=draft_app_config["long_term_memory"],
            opening_statement=draft_app_config["opening_statement"],
            opening_questions=draft_app_config["opening_questions"],
            speech_to_text=draft_app_config["speech_to_text"],
            text_to_speech=draft_app_config["text_to_speech"],
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
        remove_fields = ["id", "version", "config_type", "updated_at", "created_at", "_sa_instance_state"]
        for field in remove_fields:
            draft_app_config_copy.pop(field)

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
        remove_fields = ["id", "app_id", "version", "config_type", "updated_at", "created_at", "_sa_instance_state"]
        for field in remove_fields:
            draft_app_config_dict.pop(field)

        draft_app_config_dict = self._validate_draft_app_config(draft_app_config_dict, account)
        draft_app_config_record = app.draft_app_config
        self.update(
            draft_app_config_record,
            # todo: 更新时间补丁信息
            updated_at=datetime.now(),
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

        # todo: 根据传递的model_config实例化不同的LLM模型, 等待多LLM后会发生变化
        llm = ChatOpenAI(
            model=draft_app_config["model_config"]["model"],
            **draft_app_config["model_config"]["parameters"]
        )

        token_buffer_memory = TokenBufferMemory(
            db=self.db,
            conversation=debug_conversation,
            model_instance=llm,
        )
        history = token_buffer_memory.get_history_prompt_message(
            message_limit=draft_app_config["dialog_round"],
        )

        tools = []
        for tool in draft_app_config["tools"]:
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

        if draft_app_config["datasets"]:
            dataset_retrieval = self.retrieval_service.create_langchain_tool_from_search(
                flask_app=current_app._get_current_object(),
                dataset_ids=[UUID(dataset["id"]) for dataset in draft_app_config["datasets"]],
                account_id=account.id,
                retrieval_source=RetrievalSource.APP,
                **draft_app_config["retrieval_config"]
            )
            tools.append(dataset_retrieval)

        # todo: 构建Agent智能体, 目前暂时使用FCAgent
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
                        agent_thoughts[event_id] = {
                            "id": event_id,
                            "task_id": str(agent_thought.task_id),
                            "event": agent_thought.event,
                            "thought": agent_thought.thought,
                            "observation": agent_thought.observation,
                            "tool": agent_thought.tool,
                            "tool_input": agent_thought.tool_input,
                            "message": agent_thought.message,
                            "answer": agent_thought.answer,
                            "latency": agent_thought.latency
                        }
                    else:
                        agent_thoughts[event_id] = {
                            **agent_thoughts[event_id],
                            "thought": agent_thoughts[event_id]["thought"] + agent_thought.thought,
                            "answer": agent_thoughts[event_id]["answer"] + agent_thought.answer,
                            "latency": agent_thought.latency,
                        }
                else:
                    agent_thoughts[event_id] = {
                        "id": event_id,
                        "task_id": str(agent_thought.task_id),
                        "event": agent_thought.event,
                        "thought": agent_thought.thought,
                        "observation": agent_thought.observation,
                        "tool": agent_thought.tool,
                        "tool_input": agent_thought.tool_input,
                        "message": agent_thought.message,
                        "answer": agent_thought.answer,
                        "latency": agent_thought.latency
                    }

            data = {
                "id": event_id,
                "conversation_id": str(debug_conversation.id),
                "message_id": str(message.id),
                "task_id": str(agent_thought.task_id),
                "event": agent_thought.event,
                "thought": agent_thought.thought,
                "observation": agent_thought.observation,
                "tool": agent_thought.tool,
                "tool_input": agent_thought.tool_input,
                "answer": agent_thought.answer,
                "latency": agent_thought.latency
            }

            yield f"event: {agent_thought.event}\ndata:{json.dumps(data)}\n\n"

        thread = Thread(
            target=self._save_agent_thoughts,
            kwargs={
                "flask_app": current_app._get_current_object(),
                "account_id": account.id,
                "app_id": app.id,
                "conversation_id": debug_conversation.id,
                "message_id": message.id,
                "agent_thoughts": agent_thoughts,
                "draft_app_config": draft_app_config
            }
        )
        thread.start()

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
            filters.append(Message.created_at <= created_at_datetime)

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

    def _save_agent_thoughts(
            self,
            flask_app: Flask,
            account_id: UUID,
            app_id: UUID,
            conversation_id: UUID,
            message_id: UUID,
            agent_thoughts: dict[str, Any],
            draft_app_config: dict[str, Any]
    ) -> None:
        """存储智能体推理步骤信息"""
        with flask_app.app_context():
            position = 0
            latency = 0

            conversation = self.get(Conversation, conversation_id)
            message = self.get(Message, message_id)


            for key, item in agent_thoughts.items():
                if item["event"] in [
                    QueueEvent.LONG_TERM_MEMORY_RECALL,
                    QueueEvent.AGENT_THOUGHT,
                    QueueEvent.AGENT_MESSAGE,
                    QueueEvent.AGENT_ACTION,
                    QueueEvent.DATASET_RETRIEVAL,
                ]:

                    position += 1
                    latency += item["latency"]

                    self.create(
                        MessageAgentThought,
                        app_id=app_id,
                        conversation_id=conversation.id,
                        message_id=message.id,
                        invoke_from=InvokeFrom.DEBUGGER,
                        created_by=account_id,
                        position=position,
                        event=item["event"],
                        thought=item["thought"],
                        observation=item["observation"],
                        tool=item["tool"],
                        tool_input=item["tool_input"],
                        message=item["message"],
                        answer=item["answer"],
                        latency=item["latency"]
                    )

                    if item["event"] == QueueEvent.AGENT_MESSAGE:
                        self.update(
                            message,
                            message=item["message"],
                            answer=item["answer"],
                            latency=latency,
                        )

                        if draft_app_config["long_term_memory"]["enable"]:
                            new_summary = self.conversation_service.summary(
                                message.query,
                                item["answer"],
                                conversation.summary
                            )
                            self.update(
                                conversation,
                                summary=new_summary,
                            )

                        if conversation.is_new:
                            new_conversation_name = self.conversation_service.generate_conversation_name(message.query)
                            self.update(
                                conversation,
                                name=new_conversation_name,
                            )

                    if item["event"] in [QueueEvent.STOP, QueueEvent.ERROR]:
                        self.update(
                            message,
                            status=MessageStatus.STOP if item["event"] == QueueEvent.STOP else MessageStatus.ERROR
                        )
                        break

    def _validate_draft_app_config(self, draft_app_config: dict[str, Any], account: Account) -> dict[str, Any]:
        """校验传递的应用草稿配置信息"""
        acceptable_fields = [
            "model_config", "dialog_round", "preset_prompt",
            "tools", "workflows", "datasets", "retrieval_config",
            "long_term_memory", "opening_statement", "opening_questions",
            "speech_to_text", "text_to_speech", "suggested_after_answer", "review_config",
        ]

        if (
            not draft_app_config
            or not isinstance(draft_app_config, dict)
            or set(draft_app_config.keys()) - set(acceptable_fields)
        ):
            raise ValidateErrorException("草稿配置字段出错")

        # todo: 校验model_config字段, 等待多LLM实现

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

        # todo: 校验工作流, 等待工作流模块实现后
        if "workflows" in draft_app_config:
            draft_app_config["workflows"] = []

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

        if "speech_to_text" in draft_app_config:
            speech_to_text = draft_app_config["speech_to_text"]

            if not speech_to_text or not isinstance(speech_to_text, dict):
                raise ValidateErrorException("语音转文本设置格式错误")
            if (
                    set(speech_to_text.keys()) != {"enable"}
                    or not isinstance(speech_to_text["enable"], bool)
            ):
                raise ValidateErrorException("语音转文本设置格式错误")

        if "text_to_speech" in draft_app_config:
            text_to_speech = draft_app_config["text_to_speech"]

            if not isinstance(text_to_speech, dict):
                raise ValidateErrorException("文本转语音设置格式错误")
            if (
                    set(text_to_speech.keys()) != {"enable", "voice", "auto_play"}
                    or not isinstance(text_to_speech["enable"], bool)
                    # todo:等待多模态Agent实现时添加音色
                    or text_to_speech["voice"] not in ["echo"]
                    or not isinstance(text_to_speech["auto_play"], bool)
            ):
                raise ValidateErrorException("文本转语音设置格式错误")

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

