from pydantic import BaseModel

class ToolEntity(BaseModel):
    """工具实体类, 储存的信息映射的是工具名.yaml里的数据"""
    name: str # 工具名字
    label: str # 工具标签
    description: str # 工具描述
    params: list = [] # 工具的参数信息