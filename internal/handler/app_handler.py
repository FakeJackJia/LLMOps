import json
import uuid
from threading import Thread
from typing import Dict, Any, Generator

from internal.schema import CompletionReq
from pkg.response import success_json, validate_error_json, success_message, compact_generate_response
from internal.service import (
    AppService,
    VectorDatabaseService,
    ApiToolService,
    ConversationService,
)
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.core.agent.agents import FunctionCallAgent, AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.entity.conversation_entity import InvokeFrom

from dataclasses import dataclass
from injector import inject
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.memory import BaseMemory
from langchain_core.tracers import Run
from langchain_openai import ChatOpenAI

from redis import Redis

@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService
    vector_database_service: VectorDatabaseService
    api_tool_service: ApiToolService
    builtin_provider_manager: BuiltinProviderManager
    conversation_service: ConversationService
    redis_client: Redis

    def create_app(self):
        """调用服务创建的APP记录"""
        app = self.app_service.create_app()

        return success_message(f"应用成功创建, id为{app.id}")

    def get_app(self, id: UUID):
        app = self.app_service.get_app(id)

        return success_message(f"应用已经成功获取, 名字是{app.name}")

    def update_app(self, id: UUID):
        app = self.app_service.update_app(id)

        return success_message(f"应用已经成功修改, 修改的名字是{app.name}")

    def delete_app(self, id: UUID):
        app = self.app_service.delete_app(id)

        return success_message(f"应用已经成功删除, id为:{app.id}")

    @classmethod
    def _load_memory_variables(cls, input: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        """加载记忆变量信息"""
        # 从config中获取configurable
        configurable = config.get("configurable", {})
        configurable_memory = configurable.get("memory", None)

        if configurable_memory is not None and isinstance(configurable_memory, BaseMemory):
            return configurable_memory.load_memory_variables(input)

        return {"history": []}

    @classmethod
    def _save_context(cls, run_obj: Run, config: RunnableConfig) -> None:
        """存储对应的上下文信息到记忆实体中"""
        configurable = config.get("configurable", {})
        configurable_memory = configurable.get("memory", None)

        if configurable_memory is not None and isinstance(configurable_memory, BaseMemory):
            configurable_memory.save_context(run_obj.inputs, run_obj.outputs)

    def debug(self, app_id: UUID):
        """应用会话调试聊天接口, 该接口为流式事件输出"""
        req = CompletionReq()
        if not req.validate():
            return validate_error_json(req.errors)

        tools = [
            self.builtin_provider_manager.get_tool("google", "google_serper")(),
            self.builtin_provider_manager.get_tool("gaode", "gaode_weather")(),
            self.builtin_provider_manager.get_tool("dalle", "dalle3")(),
        ]

        agent = FunctionCallAgent(
            AgentConfig(
                llm=ChatOpenAI(model="gpt-4o-mini"),
                enable_long_term_memory=True,
                tools=tools,
            ),
            AgentQueueManager(
                user_id=uuid.uuid4(),
                task_id=uuid.uuid4(),
                invoke_from=InvokeFrom.DEBUGGER,
                redis_client=self.redis_client,
            )
        )

        def stream_event_response() -> Generator:
            """流式事件输出响应"""
            for agent_queue_event in agent.run(req.query.data, [], "用户介绍自己叫jack"):
                data = {
                    "id": str(agent_queue_event.id),
                    "task_id": str(agent_queue_event.task_id),
                    "event": agent_queue_event.event,
                    "thought": agent_queue_event.thought,
                    "observation": agent_queue_event.observation,
                    "tool": agent_queue_event.tool,
                    "tool_input": agent_queue_event.tool_input,
                    "answer": agent_queue_event.answer,
                    "latency": agent_queue_event.latency,
                }

                yield f"event: {agent_queue_event.event}\ndata: {json.dumps(data)}\n\n"

        return compact_generate_response(stream_event_response())

    def ping(self):
        from internal.core.agent.agents import FunctionCallAgent
        from internal.core.agent.entities.agent_entity import AgentConfig
        from langchain_openai import ChatOpenAI

        agent = FunctionCallAgent(AgentConfig(
            llm=ChatOpenAI(model="gpt-4o-mini"),
            preset_prompt="你是一个20年的诗人 请根据用户输入写一首诗"
        ))
        state = agent.run("苹果")
        content = state["messages"][-1].content

        print(state, flush=True)
        return success_json(content)

        #raise FailException("数据未找到")