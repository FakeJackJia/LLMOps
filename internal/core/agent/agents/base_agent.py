from typing import Generator
from abc import ABC, abstractmethod
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import AgentQueueEvent
from .agent_queue_manager import AgentQueueManager
from langchain_core.messages import AnyMessage

class BaseAgent(ABC):
    """LLMOps项目基础Agent"""
    agent_config: AgentConfig
    agent_queue_manager: AgentQueueManager

    def __init__(
            self,
            agent_config: AgentConfig,
            agent_queue_manager: AgentQueueManager,
    ):
        """初始化智能体"""
        self.agent_config = agent_config
        self.agent_queue_manager = agent_queue_manager

    @abstractmethod
    def run(
            self,
            query: str,
            histories: list[AnyMessage] = None, # 短期记忆
            long_term_memory: str = "",
    ) -> Generator[AgentQueueEvent, None, None]:
        """智能体运行函数, 传递原始问题query、长短期记忆, 并调用智能体生成相关内容"""
        raise NotImplementedError("Agent智能体run函数未实现")