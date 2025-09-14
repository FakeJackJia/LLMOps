from abc import ABC
from enum import Enum
from typing import Any, Optional

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.language_models import BaseLanguageModel as LCBaseLanguageModel

class DefaultModelParameterName(str, Enum):
    """默认的参数名字, 一般LLM共有的参数"""
    TEMPERATURE = "temperature"
    TOP_P = "top_p"
    PRESENCE_PENALTY = "presence_penalty"
    FREQUENCY_PENALTY = "frequency_penalty"

class ModelType(str, Enum):
    """模型类型枚举"""
    CHAT = "chat" # 聊天模型
    COMPLETION = "completion" # 文本生成模型

class ModelParameterType(str, Enum):
    """模型参数枚举"""
    FLOAT = "float"
    INT = "int"
    STRING = "string"
    BOOLEAN = "boolean"

class ModelParameterOption(BaseModel):
    """模型参数选项配置模型"""
    label: str # 配置选项标签
    value: Any # 配置选项对应的值

class ModelParameters(BaseModel):
    """模型参数实体信息"""
    name: str = "" # 参数名字
    label: str = "" # 参数标签
    type: ModelParameterType = ModelParameterType.STRING # 参数的类型
    help: str = "" # 帮助信息
    required: bool = False # 是否必填
    default: Optional[Any] = None # 默认参数值
    min: Optional[float] = None # 最小值 如果是float 或 int
    max: Optional[float] = None # 最大值 如果是float 或 int
    precision: int = 2 # 保留的小数位数
    options: list[ModelParameterOption]  = Field(default_factory=list) # 可选的参数配置 如果是str 或 bool

class ModelFeature(str, Enum):
    """模型特性, 如是否包含工具调用, 智能体推理, 图片输入"""
    TOOL_CALL = "tool_call"
    AGENT_THOUGHT = "agent_thought"
    IMAGE_INPUT = "image_input"

class ModelEntity(BaseModel):
    """语言模型实体, 记录模型的相关信息"""
    model_name: str = Field(default="", alias="model") # 模型名字
    label: str = "" # 模型标签
    model_type: ModelType = ModelType.CHAT # 模型类型
    features: list[ModelFeature] = Field(default_factory=list) # 模型特性
    context_window: int = 0 # 上下文窗口长度(输入+输出的总长度)
    max_output_tokens: int = 0 # 最大输出内容长度
    attributes: dict[str, Any] = Field(default_factory=dict) # 模型固定属性字典
    parameters: list[ModelParameters] = Field(default_factory=list) # 模型参数字段规则列表
    metadata: dict[str, Any] = Field(default_factory=dict) # 模型元数据, 记录价格, 词表等信息

class BaseLanguageModel(LCBaseLanguageModel, ABC):
    """基础语言模型"""
    features: list[ModelFeature] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)