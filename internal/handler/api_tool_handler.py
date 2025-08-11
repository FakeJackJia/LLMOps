from injector import inject
from dataclasses import dataclass
from internal.schema.api_tool_schema import ValidateOpenAPISchemaReq, CreateApiToolReq
from pkg.response import validate_error_json, success_message
from internal.service import ApiToolService

@inject
@dataclass
class ApiToolHandler:
    """自定义API插件处理器"""
    api_tool_service: ApiToolService

    def create_api_tool(self):
        """创建自定义API工具"""
        req = CreateApiToolReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.api_tool_service.create_api_tool(req)

        return success_message("创建自定义API插件成功")

    def validate_openai_schema(self):
        """校验传递的openapi_schema字符串是否正确"""
        req = ValidateOpenAPISchemaReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.api_tool_service.parse_openapi_schema(req.openapi_schema.data)
        return success_message("数据校验成功")