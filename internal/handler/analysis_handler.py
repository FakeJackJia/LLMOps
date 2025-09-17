from uuid import UUID
from injector import inject
from dataclasses import dataclass
from flask_login import current_user

from internal.service import AnalysisService
from pkg.response import success_json

@inject
@dataclass
class AnalysisHandler:
    """统计分析处理器"""
    analysis_service: AnalysisService

    def get_app_analysis(self, app_id: UUID):
        """根据传递的应用id获取应用统计信息"""
        app_analysis = self.analysis_service.get_app_analysis(app_id, current_user)
        return success_json(app_analysis)