from marshmallow import Schema, fields, pre_dump
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, regexp, Length, URL
from internal.model import Account
from internal.lib.helper import datetime_to_timestamp
from pkg.password import password_pattern

class UpdatePasswordRep(FlaskForm):
    """更新账号密码请求"""
    password = StringField("password", validators=[
        DataRequired("密码不能为空"),
        regexp(regex=password_pattern, message="密码规则校验失败, 至少包含一个字母一个数字且长度为8-16位")
    ])

class UpdateNameRep(FlaskForm):
    """更新账号名字请求"""
    name = StringField("name", validators=[
        DataRequired("账号名字不能为空"),
        Length(min=3, max=30, message="账号名字长度在3-30")
    ])

class UpdateAvatarRep(FlaskForm):
    """更新账号头像请求"""
    avatar = StringField("avatar", validators=[
        DataRequired("账号头像不能为空"),
        URL(message="账号头像必须是URL地址")
    ])

class GetCurrentUserResp(Schema):
    """获取当前账号信息响应"""
    id = fields.UUID(dump_default="")
    name = fields.String(dump_default="")
    email = fields.String(dump_default="")
    avatar = fields.String(dump_default="")
    last_login_at = fields.Integer(dump_default=0)
    last_login_ip = fields.String(dump_default="")
    created_at = fields.Integer(dump_default=0)


    @pre_dump
    def process_data(self, data: Account, **kwargs):
        return {
            "id": data.id,
            "name": data.name,
            "email": data.email,
            "avatar": data.avatar,
            "last_login_at": datetime_to_timestamp(data.last_login_at),
            "last_login_ip": data.last_login_ip,
            "created_at": datetime_to_timestamp(data.created_at)
        }