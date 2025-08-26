from abc import ABC, abstractmethod
from internal.core.agent.entities.agent_entity import AgentConfig
from langchain_core.messages import AnyMessage

class BaseAgent(ABC):
    """LLMOps项目基础Agent"""
    agent_config: AgentConfig

    def __init__(self, agent_config: AgentConfig):
        """初始化智能体"""
        self.agent_config = agent_config

    @abstractmethod
    def run(
            self,
            query: str,
            histories: list[AnyMessage] = None, # 短期记忆
            long_term_memory: str = "",
    ):
        """智能体运行函数, 传递原始问题query、长短期记忆, 并调用智能体生成相关内容"""
        raise NotImplementedError("Agent智能体run函数未实现")