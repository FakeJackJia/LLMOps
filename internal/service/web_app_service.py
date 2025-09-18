import json
from datetime import datetime
from threading import Thread
from typing import Generator
from uuid import UUID

from flask import current_app
from injector import inject
from dataclasses import dataclass
from langchain_core.messages import HumanMessage
from sqlalchemy import desc

from internal.model import App, Account, Conversation, Message
from internal.entity.app_entity import AppStatus
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.exception import NotFoundException, ForbiddenException
from internal.schema.web_app_schema import WebAppChatReq, GetConversationMessagesWithPageReq
from internal.core.memory import TokenBufferMemory
from internal.entity.dataset_entity import RetrievalSource
from internal.core.agent.agents import FunctionCallAgent, AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import QueueEvent

from .base_service import BaseService
from .app_config_service import AppConfigService
from .conversation_service import ConversationService
from .language_model_service import LanguageModelService
from .retriever_service import RetrievalService

from pkg.sqlalchemy import SQLAlchemy
from pkg.paginator import Paginator

@inject
@dataclass
class WebAppService(BaseService):
    """WebApp服务"""
    db: SQLAlchemy
    app_config_service: AppConfigService
    conversation_service: ConversationService
    retrieval_service: RetrievalService
    language_model_service: LanguageModelService

    def get_web_app(self, token: str) -> App:
        """获取WebApp信息"""
        app = self.db.session.query(App).filter(
            App.token == token,
        ).one_or_none()
        if not app or app.status != AppStatus.PUBLISHED:
            raise NotFoundException("该WebApp不存在或未发布")

        return app

    def web_app_chat(self, token: str, req: WebAppChatReq, account: Account) -> Generator:
        """与WebApp对话"""
        app = self.get_web_app(token)

        if req.conversation_id.data:
            conversation = self.get(Conversation, req.conversation_id.data)
            if (
                not conversation
                or conversation.app_id != app.id
                or conversation.invoke_from != InvokeFrom.WEB_APP
                or conversation.created_by != account.id
                or conversation.is_deleted is True
            ):
                raise ForbiddenException("该会话不存在, 或不属于当前应用/用户/调用方式")
        else:
            conversation = self.create(Conversation, **{
                "app_id": app.id,
                "name": "New Conversation",
                "invoke_from": InvokeFrom.WEB_APP,
                "created_by": account.id
            })

        app_config = self.app_config_service.get_app_config(app)

        message = self.create(
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            created_by=account.id,
            invoke_from=InvokeFrom.WEB_APP,
            query=req.query.data,
            status=MessageStatus.NORMAL,
        )

        llm = self.language_model_service.load_language_model(app_config.get("model_config", {}))

        token_buffer_memory = TokenBufferMemory(
            db=self.db,
            conversation=conversation,
            model_instance=llm,
        )
        history = token_buffer_memory.get_history_prompt_message(
            message_limit=app_config["dialog_round"],
        )

        tools = self.app_config_service.get_langchain_tools_by_tools_config(app_config["tools"])

        if app_config["datasets"]:
            dataset_retrieval = self.retrieval_service.create_langchain_tool_from_search(
                flask_app=current_app._get_current_object(),
                dataset_ids=[UUID(dataset["id"]) for dataset in app_config["datasets"]],
                account_id=account.id,
                retrieval_source=RetrievalSource.APP,
                **app_config["retrieval_config"]
            )
            tools.append(dataset_retrieval)

        if app_config["workflows"]:
            workflow_tools = self.app_config_service.get_langchain_tools_by_workflow_ids(
                [workflow["id"] for workflow in app_config["workflows"]]
            )
            tools.extend(workflow_tools)

        agent = FunctionCallAgent(
            llm=llm,
            agent_config=AgentConfig(
                user_id=account.id,
                invoke_from=InvokeFrom.WEB_APP,
                preset_prompt=app_config["preset_prompt"],
                enable_long_term_memory=app_config["long_term_memory"]["enable"],
                tools=tools,
                review_config=app_config["review_config"]
            )
        )

        agent_thoughts = {}
        for agent_thought in agent.stream({
            "messages": [HumanMessage(req.query.data)],
            "history": history,
            "long_term_memory": conversation.summary,
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
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "task_id": str(agent_thought.task_id)
            }

            yield f"event: {agent_thought.event}\ndata:{json.dumps(data)}\n\n"

        thread = Thread(
            target=self.conversation_service.save_agent_thoughts,
            kwargs={
                "flask_app": current_app._get_current_object(),
                "account_id": account.id,
                "app_id": app.id,
                "conversation_id": conversation.id,
                "message_id": message.id,
                "agent_thoughts": [agent_thought for agent_thought in agent_thoughts.values()],
                "app_config": app_config
            }
        )
        thread.start()

    def stop_web_app_chat(self, token: str, task_id: UUID, account: Account):
        """根据传递的token+task_id停止WebApp对话"""
        self.get_web_app(token)
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, account.id)

    def get_conversations(self, token: str, is_pinned: bool, account: Account) -> list[Conversation]:
        """获取WebApp会话列表"""
        app = self.get_web_app(token)

        conversations = self.db.session.query(Conversation).filter(
            Conversation.app_id == app.id,
            Conversation.created_by == account.id,
            Conversation.invoke_from == InvokeFrom.WEB_APP,
            Conversation.is_pinned == is_pinned,
            ~Conversation.is_deleted,
        ).order_by(desc("created_by")).all()

        return conversations

    def get_conversation(self, conversation_id: UUID, account: Account) -> Conversation:
        """获取指定会话"""
        conversation = self.get(Conversation, conversation_id)

        if not conversation or conversation.created_by != account.id or conversation.is_deleted:
            raise NotFoundException("未找到该会话")

        return conversation

    def get_conversation_messages_with_page(
            self,
            conversation_id: UUID,
            req: GetConversationMessagesWithPageReq,
            account: Account
    ) -> tuple[list[Message], Paginator]:
        """获取WebApp会话消息列表"""
        self.get_conversation(conversation_id, account)

        paginator = Paginator(db=self.db, req=req)
        filters = []
        if req.created_at.data is not None:
            created_at_datetime = datetime.fromtimestamp(req.created_at.data)
            filters.append(Message.created_at <= created_at_datetime)

        messages = paginator.paginate(
            self.db.session.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.status.in_([MessageStatus.STOP, MessageStatus.NORMAL]),
                Message.answer != "",
                Message.is_deleted == False,
                *filters
            ).order_by(desc("created_at"))
        )

        return messages, paginator