from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Optional, UUID
from marshmallow import Schema, pre_dump, fields

from internal.model import App

class WebAppChatReq(FlaskForm):
    """WebApp对话请求体"""
    conversation_id = StringField("conversation_id", validators=[
        Optional(),
        UUID(message="会话id格式必须为UUID")
    ])
    query = StringField("query", validators=[
        DataRequired(message="用户query不能为空")
    ])

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