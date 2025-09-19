from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Optional, UUID, NumberRange, Length
from marshmallow import Schema, pre_dump, fields

from internal.model import App, Conversation, Message
from internal.lib.helper import datetime_to_timestamp
from pkg.paginator import PaginatorReq


class WebAppChatReq(FlaskForm):
    """WebApp对话请求体"""
    conversation_id = StringField("conversation_id", validators=[
        Optional(),
        UUID(message="会话id格式必须为UUID")
    ])
    query = StringField("query", validators=[
        DataRequired(message="用户query不能为空")
    ])

class GetConversationsReq(FlaskForm):
    """获取WebApp会话列表请求结构体"""
    is_pinned = BooleanField("is_pinned", default=False)

class GetConversationMessagesWithPageReq(PaginatorReq):
    """获取指定会话消息列表分页数据请求结构"""
    created_at = IntegerField("created_at", validators=[
        Optional(),
        NumberRange(min=0, message="created_at游标最小值为0")
    ])

class UpdateConversationNameReq(FlaskForm):
    """更新指定会话名字数据请求结构体"""
    name = StringField("name", validators=[
        DataRequired(message="会话名字必须不能为空"),
        Length(max=100, message="会话名字不能超过100个字符")
    ])

class UpdateConversationIsPinnedReq(FlaskForm):
    """更新指定会话置顶状态请求结构体"""
    is_pinned = BooleanField("is_pinned", default=False)

class GetConversationMessagesWithPageResp(Schema):
    """获取指定会话消息列表分页数据响应结构"""
    id = fields.UUID(dump_default="")
    conversation_id = fields.UUID(dump_default="")
    query = fields.String(dump_default="")
    answer = fields.String(dump_default="")
    total_token_count = fields.Integer(dump_default=0)
    latency = fields.Float(dump_default=0)
    agent_thoughts = fields.List(fields.Dict, dump_default=[])
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: Message, **kwargs):
        return {
            "id": data.id,
            "conversation_id": data.conversation_id,
            "query": data.query,
            "answer": data.answer,
            "total_token_count": data.total_token_count,
            "latency": data.latency,
            "agent_thoughts": [{
                "id": agent_thought.id,
                "position": agent_thought.position,
                "event": agent_thought.event,
                "thought": agent_thought.thought,
                "observation": agent_thought.observation,
                "tool": agent_thought.tool,
                "tool_input": agent_thought.tool_input,
                "latency": agent_thought.latency,
                "created_at": datetime_to_timestamp(agent_thought.created_at),
            } for agent_thought in data.agent_thoughts],
            "created_at": datetime_to_timestamp(data.created_at),
        }

class GetWebAppResp(Schema):
    """获取WebApp基础信息响应结构"""
    id = fields.UUID(dump_default="")
    icon = fields.String(dump_default="")
    name = fields.String(dump_default="")
    description = fields.String(dump_default="")
    app_config = fields.Dict(dump_default={})

    @pre_dump
    def process_data(self, data: App, **kwargs):
        app_config = data.app_config
        return {
            "id": data.id,
            "icon": data.icon,
            "name": data.name,
            "description": data.description,
            "app_config": {
                "opening_statement": app_config.opening_statement,
                "opening_questions": app_config.opening_questions,
                "suggested_after_answer": app_config.suggested_after_answer
            }
        }

class GetConversationsResp(Schema):
    """获取WebApp会话列表响应结构体"""
    id = fields.UUID(dump_default="")
    name = fields.String(dump_default="")
    summary = fields.String(dump_default="")
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: Conversation, **kwargs):
        return {
            "id": data.id,
            "name": data.name,
            "summary": data.summary,
            "created_at": datetime_to_timestamp(data.created_at),
        }