from internal.core.language_model.entities.model_entity import BaseLanguageModel

from langchain_ollama import ChatOllama

class Chat(ChatOllama, BaseLanguageModel):
    """Ollama聊天模型"""
    pass