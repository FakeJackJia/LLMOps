from injector import inject
from dataclasses import dataclass
from flask_login import login_required, current_user
from internal.schema.ai_schema import OptimizePromptReq, GenerateSuggestedQuestionsReq
from internal.service import AIService
from pkg.response import validate_error_json, compact_generate_response,success_json

@inject
@dataclass
class AIHandler:
    """AI辅助模块处理器"""
    ai_service: AIService

    @login_required
    def optimize_prompt(self):
        """根据传递的预设prompt进行优化"""
        req = OptimizePromptReq()
        if not req.validate():
            return validate_error_json(req.errors)

        resp = self.ai_service.optimize_prompt(req.prompt.data)
        return compact_generate_response(resp)

    @login_required
    def generate_suggested_questions(self):
        """根据传递的消息id生成建议问题列表"""
        req = GenerateSuggestedQuestionsReq()
        if not req.validate():
            return validate_error_json(req.errors)

        suggested_questions = self.ai_service.generate_suggested_questions_from_message_id(
            req.message_id.data,
            current_user
        )
        return success_json(suggested_questions)