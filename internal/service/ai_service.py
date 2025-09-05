import json
from uuid import UUID
from typing import Generator
from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from .conversation_service import ConversationService
from pkg.sqlalchemy import SQLAlchemy

from internal.model import Account, Message
from internal.exception import ForbiddenException
from internal.entity.ai_entity import OPTIMIZE_PROMPT_TEMPLATE

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

@inject
@dataclass
class AIService(BaseService):
    """AI服务"""
    db: SQLAlchemy
    conversation_service: ConversationService

    @classmethod
    def optimize_prompt(cls, prompt: str) -> Generator[str, None, None]:
        """根据传递的prompt进行优化生成"""
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", OPTIMIZE_PROMPT_TEMPLATE),
            ("human", "{prompt}")
        ])
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)

        optimize_chain = prompt_template | llm | StrOutputParser()

        for optimize_prompt in optimize_chain.stream({"prompt": prompt}):
            data = {"optimize_prompt": optimize_prompt}
            yield f"event: optimize_prompt\ndata: {json.dumps(data)}\n\n"

    def generate_suggested_questions_from_message_id(self, message_id: UUID, account: Account) -> list[str]:
        """根据传递的消息id+账号生成建议问题列表"""
        message = self.db.session.get(Message, message_id)
        if not message or message.created_by != account.id:
            raise ForbiddenException("该消息不存在或无权限")

        histories = f"Human: {message.query}\nAI: {message.answer}"
        return self.conversation_service.generate_suggested_questions(histories)