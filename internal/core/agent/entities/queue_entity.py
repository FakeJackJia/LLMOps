from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field
from internal.entity.conversation_entity import MessageStatus

class QueueEvent(str, Enum):
    """队列事件枚举类型"""
    LONG_TERM_MEMORY_RECALL = "long_term_memory_recall"
    AGENT_THOUGHT = "agent_thought"
    AGENT_MESSAGE = "agent_message"
    AGENT_ACTION = "agent_action"
    DATASET_RETRIEVAL = "dataset_retrieval"
    AGENT_END = "agent_end"
    STOP = "stop"
    ERROR = "error"
    TIMEOUT = "timeout"
    PING = "ping"

class AgentThought(BaseModel):
    """智能体推理观察输出内容"""
    id: UUID
    task_id: UUID

    # 事件的观察和推理
    event: QueueEvent
    thought: str = ""
    observation: str = ""

    # 工具相关的字段
    tool: str = ""
    tool_input: dict = Field(default_factory=dict)

    # 消息相关的数据
    message: list[dict] = Field(default_factory=dict)
    message_token_count: int = 0
    message_unit_price: float = 0
    message_price_unit: float = 0

    # 答案相关的数据
    answer: str = ""
    answer_token_count: int = 0
    answer_unit_price: float = 0
    answer_price_unit: float = 0

    # Agent推理统计相关
    total_token_count: int = 0
    total_price: float = 0
    latency: float = 0

class AgentResult(BaseModel):
    """智能体推理观察最终结果"""
    query: str = "" # 原始用户提问

    message: list[dict] = Field(default_factory=list)
    message_token_count: int = 0
    message_unit_price: float = 0
    message_price_unit: float = 0

    answer: str = ""
    answer_token_count: int = 0
    answer_unit_price: float = 0
    answer_price_unit: float = 0

    total_token_count: int = 0
    total_price: float = 0
    latency: float = 0

    status: str = MessageStatus.NORMAL
    error: str = ""

    agent_thoughts: list[AgentThought] = Field(default_factory=list)