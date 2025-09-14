import json
from datetime import datetime
from threading import Thread
from typing import Generator
from uuid import UUID
from injector import inject
from dataclasses import dataclass

from sqlalchemy import desc
from flask import current_app

from .base_service import BaseService
from .conversation_service import ConversationService

from internal.model import Account, Message
from internal.core.agent.agents import AgentQueueManager
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.schema.assistant_agent_schema import (
    GetAssistantAgentMessagesWithPageReq,
)
from internal.core.memory import TokenBufferMemory
from internal.core.agent.agents import FunctionCallAgent
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import QueueEvent

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from pkg.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class AssistantAgentService(BaseService):
    """辅助Agent服务"""
    db: SQLAlchemy
    conversation_service: ConversationService

    def chat(self, query: str, account: Account) -> Generator:
        """辅助Agent会话"""
        assistant_agent_id = current_app.config.get("ASSISTANT_AGENT_ID")
        conversation = account.assistant_agent_conversation

        message = self.create(
            Message,
            app_id=assistant_agent_id,
            conversation_id=conversation.id,
            created_by=account.id,
            invoke_from=InvokeFrom.ASSISTANT_AGENT,
            query=query,
            status=MessageStatus.NORMAL,
        )

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8)

        token_buffer_memory = TokenBufferMemory(
            db=self.db,
            conversation=conversation,
            model_instance=llm,
        )
        history = token_buffer_memory.get_history_prompt_message(message_limit=3)

        tools = []

        agent = FunctionCallAgent(
            llm=llm,
            agent_config=AgentConfig(
                user_id=account.id,
                invoke_from=InvokeFrom.ASSISTANT_AGENT,
                enable_long_term_memory=True,
                tools=tools
            )
        )

        agent_thoughts = {}
        for agent_thought in agent.stream({
            "messages": [HumanMessage(query)],
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
                            "answer": agent_thoughts[event_id].answer + agent_thought.answer,
                            "latency": agent_thought.latency
                        })
                else:
                    agent_thoughts[event_id] = agent_thought

            data = {
                **agent_thought.model_dump(include={
                    "event", "thought", "observation", "tool", "tool_input", "answer", "latency"
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
                "app_id": assistant_agent_id,
                "conversation_id": conversation.id,
                "message_id": message.id,
                "agent_thoughts": [agent_thought for agent_thought in agent_thoughts.values()],
                "app_config": {"long_term_memory": {"enable": True}}
            }
        )
        thread.start()

    @classmethod
    def stop_chat(cls, task_id: UUID, account: Account) -> None:
        """停止辅助Agent会话"""
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.ASSISTANT_AGENT, account.id)

    def get_conversation_messages_with_page(
            self,
            req: GetAssistantAgentMessagesWithPageReq,
            account: Account
    ) -> tuple[list[Message], Paginator]:
        """获取辅助Agent的会话分页列表"""
        conversation = account.assistant_agent_conversation

        paginator = Paginator(db=self.db, req=req)
        filters = []
        if req.created_at.data is not None:
            # 将时间戳转换成DateTime
            created_at_datetime = datetime.fromtimestamp(req.created_at.data)
            filters.append(Message.created_at <= created_at_datetime)

        messages = paginator.paginate(
            self.db.session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.status.in_([MessageStatus.STOP, MessageStatus.NORMAL]),
                Message.answer != "",
                Message.is_deleted == False,
                *filters
            ).order_by(desc("created_at"))
        )

        return messages, paginator

    def delete_conversation(self, account: Account) -> None:
        """清空辅助Agent会话"""
        self.update(account, assistant_agent_conversation_id=None)