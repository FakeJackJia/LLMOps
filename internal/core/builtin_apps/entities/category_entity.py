from pydantic import BaseModel, Field

class CategoryEntity(BaseModel):
    """内置工具分类实体"""
    category: str = Field(default="")
    name: str = Field(default="")