from injector import inject
from dataclasses import dataclass

@inject
@dataclass
class AnalysisHandler:
    """统计分析处理器"""