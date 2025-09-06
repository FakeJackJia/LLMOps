from injector import inject
from dataclasses import dataclass
from pkg.response import compact_generate_response, validate_error_json
from flask_login import login_required, current_user

from internal.schema.openapi_schema import OpenAPIChatReq
from internal.service import OpenAPIService

@inject
@dataclass
class OpenAPIHandler:
    """开放API处理器"""
    openapi_service: OpenAPIService

    @login_required
    def chat(self):
        """开放Chat对话接口"""
        req = OpenAPIChatReq()
        if not req.validate():
            return validate_error_json(req.errors)

        resp = self.openapi_service.chat(req, current_user)
        return compact_generate_response(resp)