from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, UUID, Length


class OptimizePromptReq(FlaskForm):
    """优化预设prompt请求体结构"""
    prompt = StringField("prompt", validators=[
        DataRequired("预设prompt不能为空"),
        Length(max=2000, message="预设prompt长度不能超过2000字符")
    ])

class GenerateSuggestedQuestionsReq(FlaskForm):
    """生成问题建议列表请求结构体"""
    message_id = StringField("message_id", validators=[
        DataRequired("消息id不能为空"),
        UUID(message="消息id格式必须为uuid")
    ])