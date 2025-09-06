from dataclasses import dataclass
from internal.model import Conversation, Message
from internal.entity.conversation_entity import MessageStatus
from pkg.sqlalchemy import SQLAlchemy
from sqlalchemy import asc
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import (
    AnyMessage,
    AIMessage,
    HumanMessage,
    trim_messages,
    get_buffer_string,
)

@dataclass
class TokenBufferMemory:
    """基于token计数的缓冲记忆组件"""
    db: SQLAlchemy
    conversation: Conversation
    model_instance: BaseLanguageModel

    def get_history_prompt_message(
            self,
            max_token_limit: int = 2000,
            message_limit: int = 10,
    ) -> list[AnyMessage]:
        """根据传递的token限制+消息条数限制获取指定会话模型的历史消息列表"""
        if self.conversation is None:
            return []

        messages = self.db.session.query(Message).filter(
            Message.conversation_id == self.conversation.id,
            Message.answer != "",
            Message.is_deleted == False,
            Message.status.in_([MessageStatus.NORMAL, MessageStatus.STOP, MessageStatus.TIMEOUT])
        ).order_by(asc("created_by")).limit(message_limit).all()

        prompt_messages = []
        for message in messages:
            prompt_messages.extend([
                HumanMessage(content=message.query),
                AIMessage(content=message.answer),
            ])

        return trim_messages(
            messages=prompt_messages,
            max_tokens=max_token_limit,
            token_counter=self.model_instance,
            strategy="last",
        )

    def get_history_prompt_text(
            self,
            human_prefix: str = "Human",
            ai_prefix: str = "AI",
            max_token_limit: int = 2000,
            message_limit: int = 10,
    ) -> str:
        """根据传递的数据获取指定会话历史消息提示文本, 用于文本生成模型"""
        messages = self.get_history_prompt_message(max_token_limit, message_limit)
        return get_buffer_string(messages, human_prefix, ai_prefix)