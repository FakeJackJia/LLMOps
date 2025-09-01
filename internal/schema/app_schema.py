from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length, URL
from marshmallow import Schema, fields, pre_dump
from internal.model import App
from internal.lib.helper import datetime_to_timestamp

class CreateAppReq(FlaskForm):
    """创建Agent应用请求结构体"""
    name = StringField("name", validators=[
        DataRequired("应用名称不能为空"),
        Length(max=40, message="应用名称长度最大不超过40个字符")
    ])
    icon = StringField("icon", validators=[
        DataRequired("应用图标不能为空"),
        URL(message="应用图标必须是图片URL链接")
    ])
    description = StringField("description", validators=[
        Length(max=800, message="应用描述不能超过800个字符")
    ])

class GetAppResp(Schema):
    """获取应用基础信息响应结构"""
    id = fields.UUID(dump_default="")
    debug_conversation_id = fields.UUID(dump_default="")
    name = fields.String(dump_default="")
    icon = fields.String(dump_default="")
    description = fields.String(dump_default="")
    status = fields.String(dump_default="")
    draft_updated_at = fields.Integer(dump_default=0)
    updated_at = fields.Integer(dump_default=0)
    created_at = fields.Integer(dump_default=0)

    @pre_dump
    def process_data(self, data: App, **kwargs):
        return {
            "id": data.id,
            "debug_conversation_id": data.debug_conversation_id if data.debug_conversation_id else "",
            "name": data.name,
            "icon": data.icon,
            "description": data.description,
            "status": data.status,
            "draft_updated_at": datetime_to_timestamp(data.draft_app_config.updated_at),
            "updated_at": datetime_to_timestamp(data.updated_at),
            "created_at": datetime_to_timestamp(data.created_at),
        }