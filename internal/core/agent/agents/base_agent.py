import uuid
from threading import Thread
from typing import Optional, Any, Iterator
from abc import abstractmethod

from internal.core.agent.entities.agent_entity import AgentConfig, AgentState
from internal.core.agent.entities.queue_entity import AgentThought, AgentResult, QueueEvent
from internal.exception import FailException
from .agent_queue_manager import AgentQueueManager
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.load import Serializable
from langchain_core.language_models import BaseLanguageModel
from langgraph.graph.state import CompiledStateGraph
from langchain_core.pydantic_v1 import PrivateAttr


class BaseAgent(Serializable, Runnable):
    """基于Runnable的基础智能体基类"""
    llm: BaseLanguageModel
    agent_config: AgentConfig
    _agent: CompiledStateGraph = PrivateAttr(None)
    _agent_queue_manager: AgentQueueManager = PrivateAttr(None)

    class Config:
        arbitrary_types_allowed = True

    def __init__(
            self,
            llm: BaseLanguageModel,
            agent_config: AgentConfig,
            *args,
            **kwargs
    ):
        """初始化智能体"""
        super().__init__(*args, llm=llm, agent_config=agent_config, **kwargs)
        self._agent = self._build_agent()
        self._agent_queue_manager = AgentQueueManager(
            user_id=agent_config.user_id,
            invoke_from=agent_config.invoke_from
        )

    @abstractmethod
    def _build_agent(self) -> CompiledStateGraph:
        """构建智能体函数"""
        raise NotImplementedError("Agent智能体_build_agent函数未实现")

    def invoke(self, input: AgentState, config: Optional[RunnableConfig] = None) -> AgentResult:
        """块内容响应, 一次性生成完整内容后返回"""
        agent_result = AgentResult(query=input["messages"][0].content)
        agent_thoughts = {}
        for agent_thought in self.stream(input, config):
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

                    agent_result.answer += agent_thought.answer
                else:
                    agent_thoughts[event_id] = agent_thought

                    if agent_thought.event in [QueueEvent.STOP, QueueEvent.TIMEOUT, QueueEvent.ERROR]:
                        agent_result.status = agent_thought.event
                        agent_result.error = agent_thought.observation if agent_thought.event == QueueEvent.ERROR else ""

        agent_result.agent_thoughts = [agent_thought for agent_thought in agent_thoughts.values()]
        agent_result.message = next(
            (agent_thought.message for agent_thought in agent_thoughts.values()
            if agent_thought.event == QueueEvent.AGENT_MESSAGE),
            []
        )

        agent_result.latency = sum([agent_thought.latency for agent_thought in agent_thoughts.values()])

        return agent_result

    def stream(
        self,
        input: AgentState,
        config: Optional[RunnableConfig] = None,
        **kwargs: Optional[Any],
    ) -> Iterator[AgentThought]:
        """流式输出, 每个Node节点或LLM每生成一个token时则会返回一个内容"""
        if not self._agent:
            raise FailException("智能体未成功构建")

        input["task_id"] = input.get("task_id", uuid.uuid4())
        input["history"] = input.get("history", [])
        input["iteration_count"] = input.get("iteration_count", 0)

        thread = Thread(
            target=self._agent.invoke,
            args=(input,)
        )
        thread.start()

        yield from self._agent_queue_manager.listen(input["task_id"])

    @property
    def agent_queue_manager(self) -> AgentQueueManager:
        """只读属性, 返回智能体队列管理器"""
        return self._agent_queue_manager