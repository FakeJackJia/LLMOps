import uuid
from threading import Thread
from typing import Optional, Any, Iterator
from abc import abstractmethod

from internal.core.agent.entities.agent_entity import AgentConfig, AgentState
from internal.core.agent.entities.queue_entity import AgentThought, AgentResult
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