import os
import yaml
from typing import Union, Type, Any

from langchain_core.pydantic_v1 import BaseModel, Field, root_validator

from internal.lib.helper import dynamic_import
from internal.exception import FailException, NotFoundException
from .model_entity import ModelType, ModelEntity, BaseLanguageModel
from .default_model_parameter_template import DEFAULT_MODEL_PARAMETER_TEMPLATE

class ProviderEntity(BaseModel):
    """模型提供商实体信息"""
    name: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""
    background: str = ""
    supported_model_types: list[ModelType] = Field(default_factory=list)

class Provider(BaseModel):
    """LLM服务提供商, 在该类下可以获取到该提供商下的所有LLM信息"""
    name: str = ""
    position: str = ""
    provider_entity: ProviderEntity
    model_entity_map: dict[str, ModelEntity] = Field(default_factory=dict) # 模型实体映射
    model_class_map: dict[str, Union[None, Type[BaseLanguageModel]]] = Field(default_factory=dict) # 模型类映射

    @root_validator(pre=False)
    def validate_provider(cls, provider: dict[str, Any]) -> dict[str, Any]:
        """模型提供商校验, 利用校验初始化"""
        provider_entity = provider["provider_entity"]

        for model_type in provider_entity.supported_model_types:
            symbol_name = model_type[0].upper() + model_type[1:]
            provider["model_class_map"][model_type] = dynamic_import(
                f"internal.core.language_model.providers.{provider_entity.name}.{model_type}",
                symbol_name
            )

        current_path = os.path.abspath(__file__)
        entities_path = os.path.dirname(current_path)
        provider_path = os.path.join(os.path.dirname(entities_path), "providers", provider_entity.name)

        positions_yaml_path = os.path.join(provider_path, "positions.yaml")
        with open(positions_yaml_path, encoding="utf-8") as f:
            positions_yaml_data = yaml.safe_load(f) or []
        if not isinstance(positions_yaml_data, list):
            raise FailException("positions.yaml数据格式错误")

        for model_name in positions_yaml_data:
            model_yaml_path = os.path.join(provider_path, f"{model_name}.yaml")
            with open(model_yaml_path, encoding="utf-8") as f:
                model_yaml_data = yaml.safe_load(f)

            yaml_parameters = model_yaml_data.get("parameters")
            parameters = []
            for parameter in yaml_parameters:
                use_template = parameter.get("use_template")
                if use_template:
                    # 使用了模板, 则使用模板补全数据, 并删除use_template
                    default_parameter = DEFAULT_MODEL_PARAMETER_TEMPLATE.get(use_template)
                    del parameter["use_template"]
                    parameters.append({**default_parameter, **parameter})
                else:
                    parameters.append(parameter)

            model_yaml_data["parameters"] = parameters
            provider["model_entity_map"][model_name] = ModelEntity(**model_yaml_data)

        return provider

    def get_model_class(self, model_type: ModelType) -> Type[BaseLanguageModel]:
        """根据传递的模型类型获取该提供者的模型类"""
        model_class =  self.model_class_map.get(model_type, None)
        if not model_class:
            raise NotFoundException("该模型类不存在")
        return model_class

    def get_model_entity(self, model_name: str) -> ModelEntity:
        """根据模型名字获取模型实体信息"""
        model_entity = self.model_entity_map.get(model_name, None)
        if not model_entity:
            raise NotFoundException("该模型实体不存在")
        return model_entity

    def get_model_entities(self) -> list[ModelEntity]:
        """获取该服务提供商的所有模型实体信息"""
        return self.model_entity_map.values()