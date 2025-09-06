from injector import inject
from dataclasses import dataclass
from pkg.response import success_message
from flask_login import login_required

@inject
@dataclass
class OpenAPIHandler:
    """开放API处理器"""

    @login_required
    def chat(self):
        """开放Chat对话接口"""
        return success_message("开放Chat对话接口")