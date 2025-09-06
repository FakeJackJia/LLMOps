import json
from threading import Thread
from typing import Generator
from uuid import UUID

from injector import inject
from dataclasses import dataclass
from flask import current_app

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .base_service import BaseService
from .app_config_service import AppConfigService
from .app_service import AppService
from .retriever_service import RetrievalService
from .conversation_service import ConversationService

from pkg.sqlalchemy import SQLAlchemy
from pkg.response import Response

from internal.schema.openapi_schema import OpenAPIChatReq
from internal.model import Account, EndUser, Conversation, Message
from internal.entity.app_entity import AppStatus
from internal.exception import NotFoundException, ForbiddenException
from internal.core.agent.entities.agent_entity import InvokeFrom, AgentConfig
from internal.entity.conversation_entity import MessageStatus
from internal.core.memory import TokenBufferMemory
from internal.entity.dataset_entity import RetrievalSource
from internal.core.agent.agents import FunctionCallAgent
from internal.core.agent.entities.queue_entity import QueueEvent


@inject
@dataclass
class OpenAPIService(BaseService):
    """开放API服务"""
    db: SQLAlchemy
    app_config_service: AppConfigService
    app_service: AppService
    retrieval_service: RetrievalService
    conversation_service: ConversationService

    def chat(self, req: OpenAPIChatReq, account: Account):
        """根据传递的请求+账号信息发起聊天对话, 返回数据为块内容或生成器"""
        app = self.app_service.get_app(req.app_id.data, account)

        if app.status != AppStatus.PUBLISHED:
            raise NotFoundException("该应用未发布")

        if req.end_user_id.data:
            end_user = self.get(EndUser, req.end_user_id.data)
            if not end_user or end_user.app_id != app.id:
                raise ForbiddenException("当前账号不存在或不属于该应用")
        else:
            end_user = self.create(EndUser, **{"tenant_id": account.id, "app_id": app.id})

        if req.conversation_id.data:
            conversation = self.get(Conversation, req.conversation_id.data)
            if (
                not conversation
                or conversation.app_id != app.id
                or conversation.invoke_from != InvokeFrom.SERVICE_API
                or conversation.created_by != end_user.id
            ):
                raise ForbiddenException("该会话不存在或者不属于该应用/终端用户/调用方式")
        else:
            conversation = self.create(Conversation, **{
                "app_id": app.id,
                "name": "New Conversation",
                "invoke_from": InvokeFrom.SERVICE_API,
                "created_by": end_user.id
            })

        app_config = self.app_config_service.get_app_config(app)

        message = self.create(Message, **{
            "app_id": app.id,
            "conversation_id": conversation.id,
            "invoke_from": InvokeFrom.SERVICE_API,
            "created_by": end_user.id,
            "query": req.query.data,
            "status": MessageStatus.NORMAL,
        })

        # todo: 根据传递的model_config实例化不同的LLM模型, 等待多LLM后会发生变化
        llm = ChatOpenAI(
            model=app_config["model_config"]["model"],
            **app_config["model_config"]["parameters"]
        )

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

        # todo: 构建Agent智能体, 目前暂时使用FCAgent
        agent = FunctionCallAgent(
            llm=llm,
            agent_config=AgentConfig(
                user_id=end_user.id,
                invoke_from=InvokeFrom.SERVICE_API,
                preset_prompt=app_config["preset_prompt"],
                enable_long_term_memory=app_config["long_term_memory"]["enable"],
                tools=tools,
                review_config=app_config["review_config"]
            )
        )

        agent_state = {
            "messages": [HumanMessage(content=req.query.data)],
            "history": history,
            "long_term_memory": conversation.summary
        }

        if req.stream.data is True:
            agent_thoughts = {}
            def handle_stream() -> Generator:
                """流式事件处理器, python函数里有yield那么这个函数返回的一定是生成器"""
                for agent_thought in agent.stream(agent_state):
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
                        "end_user_id": str(end_user.id),
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

            return handle_stream()

        agent_result = agent.invoke(agent_state)

        thread = Thread(
            target=self.conversation_service.save_agent_thoughts,
            kwargs={
                "flask_app": current_app._get_current_object(),
                "account_id": account.id,
                "app_id": app.id,
                "conversation_id": conversation.id,
                "message_id": message.id,
                "agent_thoughts": agent_result.agent_thoughts,
                "app_config": app_config
            }
        )
        thread.start()

        return Response(data={
            "id": str(Message.id),
            "end_user_id": str(end_user.id),
            "conversation_id": str(conversation.id),
            "query": agent_result.query,
            "answer": agent_result.answer,
            "total_token_count": agent_result.total_token_count,
            "latency": agent_result.latency,
            "agent_thoughts": [{
                "id": str(agent_thought.id),
                "event": str(agent_thought.event),
                "thought": agent_thought.thought,
                "observation": agent_thought.observation,
                "tool": agent_thought.tool,
                "tool_input": agent_thought.tool_input,
                "latency": agent_thought.latency,
                "created_at": 0
            } for agent_thought in agent_result.agent_thoughts]
        })
