from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired
from marshmallow import Schema, fields

class AuthorizeReq(FlaskForm):
    """第三方授权认证请求"""
    code = StringField("code", validators=[DataRequired("code不能为空")])

class AuthorizeResp(Schema):
    """第三方授权认证响应结构"""
    access_token = fields.String()
    expire_at = fields.Integer()