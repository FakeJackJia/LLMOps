from internal.core.language_model.entities.model_entity import BaseLanguageModel

from langchain_openai import ChatOpenAI


class Chat(BaseLanguageModel, ChatOpenAI):
    """OpenAI聊天模型基类"""
    pass