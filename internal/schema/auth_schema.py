from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Email, Length, regexp
from marshmallow import Schema, fields
from pkg.password import password_pattern

class PasswordLoginReq(FlaskForm):
    """账号密码登录请求登录结构"""
    email = StringField("email", validators=[
        DataRequired("邮箱不能为空"),
        Email("邮箱格式错误"),
        Length(min=5, max=254, message="登录邮箱再5-254")
    ])
    password = StringField("password", validators=[
        DataRequired("密码不能为空"),
        regexp(regex=password_pattern, message="密码规则校验失败, 至少包含一个字母一个数字且长度为8-16位")
    ])

class PasswordLoginResp(Schema):
    """账号密码授权认证响应结构"""
    access_token = fields.String()
    expire_at = fields.Integer()
