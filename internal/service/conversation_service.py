import logging
from typing import Any
from uuid import UUID

from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy

from internal.entity.conversation_entity import (
    SUMMARIZER_TEMPLATE,
    CONVERSATION_NAME_TEMPLATE,
    ConversationInfo,
    SUGGEST_QUESTIONS_TEMPLATE,
    SuggestedQuestions,
    InvokeFrom,
)
from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent
from internal.model import Conversation, Message, MessageAgentThought

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

@inject
@dataclass
class ConversationService(BaseService):
    """会话服务"""
    db: SQLAlchemy

    @classmethod
    def summary(cls, human_message: str, ai_message: str, old_summary: str = "") -> str:
        """根据传递的人类消息、AI消息还有原始的摘要信息总结生成一段新的摘要"""
        prompt = ChatPromptTemplate.from_template(SUMMARIZER_TEMPLATE)
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
        summary_chain = prompt | llm | StrOutputParser()

        new_summary = summary_chain.invoke({
            "summary": old_summary,
            "new_lines": f"Human: {human_message}\nAI: {ai_message}",
        })

        return new_summary

    @classmethod
    def generate_conversation_name(cls, query: str) -> str:
        """根据传递的query生成对应的会话名字, 并语言与用户输入的保持一致"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", CONVERSATION_NAME_TEMPLATE),
            ("human", "{query}")
        ])

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(ConversationInfo)

        chain = prompt | structured_llm

        if len(query) > 2000:
            query = query[:300] + "...[TRUNCATED]..." + query[-300:]
        query = query.replace("\n", " ")

        conversation_info = chain.invoke({"query": query})

        name = "新的会话"
        try:
            if conversation_info and hasattr(conversation_info, "subject"):
                name = conversation_info.subject
        except Exception as e:
            logging.exception("提取名称会话错误")

        if len(name) > 75:
            name = name[:75] + "..."

        return name

    @classmethod
    def generate_suggested_questions(cls, histories: str) -> list[str]:
        """根据传递的历史信息生成最多不超过3个的建议问题"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", SUGGEST_QUESTIONS_TEMPLATE),
            ("human", "{histories}")
        ])

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(SuggestedQuestions)

        chain = prompt | structured_llm

        suggested_questions = chain.invoke({"histories": histories})

        questions = []
        try:
            if suggested_questions and hasattr(suggested_questions, "questions"):
                questions = suggested_questions.questions
        except Exception as e:
            logging.exception("提取问题建议错误")

        if len(questions) > 3:
            questions = questions[:3]

        return questions

    def save_agent_thoughts(
            self,
            account_id: UUID,
            app_id: UUID,
            conversation_id: UUID,
            message_id: UUID,
            agent_thoughts: list[AgentThought],
            app_config: dict[str, Any]
    ) -> None:
        """存储智能体推理步骤消息"""
        position = 0
        latency = 0

        conversation = self.get(Conversation, conversation_id)
        message = self.get(Message, message_id)

        for agent_thought in agent_thoughts:
            if agent_thought.event in [
                QueueEvent.LONG_TERM_MEMORY_RECALL,
                QueueEvent.AGENT_THOUGHT,
                QueueEvent.AGENT_MESSAGE,
                QueueEvent.AGENT_ACTION,
                QueueEvent.DATASET_RETRIEVAL,
            ]:

                position += 1
                latency += agent_thought.latency

                self.create(
                    MessageAgentThought,
                    app_id=app_id,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    invoke_from=InvokeFrom.DEBUGGER,
                    created_by=account_id,
                    position=position,
                    event=agent_thought.event,
                    thought=agent_thought.thought,
                    observation=agent_thought.observation,
                    tool=agent_thought.tool,
                    tool_input=agent_thought.tool_input,
                    message=agent_thought.message,
                    answer=agent_thought.answer,
                    latency=agent_thought.latency
                )

                if agent_thought.event == QueueEvent.AGENT_MESSAGE:
                    self.update(
                        message,
                        message=agent_thought.message,
                        message_token_count=agent_thought.message_token_count,
                        message_unit_price=agent_thought.message_unit_price,
                        message_price_unit=agent_thought.message_price_unit,
                        answer=agent_thought.answer,
                        answer_token_count=agent_thought.answer_token_count,
                        answer_unit_price=agent_thought.answer_unit_price,
                        answer_price_unit=agent_thought.answer_price_unit,
                        total_token_count=agent_thought.total_token_count,
                        total_price=agent_thought.total_price,
                        latency=latency,
                    )

                    if app_config["long_term_memory"]["enable"]:
                        new_summary = self.summary(
                            message.query,
                            agent_thought.answer,
                            conversation.summary
                        )
                        self.update(
                            conversation,
                            summary=new_summary,
                        )

                    if conversation.is_new:
                        new_conversation_name = self.generate_conversation_name(message.query)
                        self.update(
                            conversation,
                            name=new_conversation_name,
                        )

                if agent_thought.event in [QueueEvent.TIMEOUT, QueueEvent.STOP, QueueEvent.ERROR]:
                    self.update(
                        message,
                        status=agent_thought.event,
                        error=agent_thought.observation
                    )
                    break