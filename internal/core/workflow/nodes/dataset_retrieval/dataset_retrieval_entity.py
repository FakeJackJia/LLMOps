from uuid import UUID

from internal.core.workflow.entities.node_entity import BaseNodeData
from internal.entity.dataset_entity import RetrievalStrategy
from internal.core.workflow.entities.variable_entity import (
    VariableEntity,
    VariableValueType,
    VariableType
)
from internal.exception import FailException

from langchain_core.pydantic_v1 import BaseModel, Field, validator

class RetrievalConfig(BaseModel):
    """检索配置"""
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.SEMANTIC
    k: int = 4
    score: float = 0

class DatasetRetrievalNodeData(BaseNodeData):
    """知识库检索节点数据"""
    dataset_ids: list[UUID] # 关联的知识库id
    retrieval_config: RetrievalConfig = Field(default_factory=RetrievalConfig)
    inputs: list[VariableEntity] = Field(default_factory=list)
    outputs: list[VariableEntity] = Field(
        exclude=True,
        default_factory=lambda :[
            VariableEntity(name="combine_documents", value={"type": VariableValueType.GENERATED})
        ]
    )

    @validator("inputs")
    def validate_inputs(cls, value: list[VariableEntity]) -> list[VariableEntity]:
        """校验输入变量信息"""
        if len(value) != 1:
            raise FailException("知识库节点输入变量信息出错")

        query_input = value[0]
        if query_input.name != "query" or query_input.type != VariableType.STRING or query_input.required is False:
            raise FailException("知识库节点输入变量名字/变量类型/必填属性出错")

        return value