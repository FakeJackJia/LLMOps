from uuid import UUID
from injector import inject
from dataclasses import dataclass
from flask import request
from internal.schema.segment_schema import (
    GetSegmentsWithPageReq,
    GetSegmentsWithPageResp,
    GetSegmentResp,
    UpdateSegmentEnabledReq,
    CreateSegmentReq,
)
from internal.service import SegmentService
from pkg.paginator import PageModel
from pkg.response import validate_error_json, success_json, success_message

@inject
@dataclass
class SegmentHandler:
    """片段处理器"""
    segment_service: SegmentService

    def create_segment(self, dataset_id: UUID, document_id: UUID):
        """根据传递的信息创建知识库文档片段"""
        req = CreateSegmentReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.segment_service.create_segment(dataset_id, document_id, req)
        return success_message("新增文档片段成功")

    def get_segments_with_page(self, dataset_id: UUID, document_id: UUID):
        """获取指定知识库文档的片段列表信息"""
        req = GetSegmentsWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        segments, paginator = self.segment_service.get_segments_with_page(dataset_id, document_id, req)

        resp = GetSegmentsWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(segments), paginator=paginator))

    def get_segment(self, dataset_id: UUID, document_id: UUID, segment_id: UUID):
        """获取指定的文档片段信息"""
        segment = self.segment_service.get_segment(dataset_id, document_id, segment_id)
        resp = GetSegmentResp()
        return success_json(resp.dump(segment))

    def update_segment_enabled(self, dataset_id: UUID, document_id: UUID, segment_id: UUID):
        """更新指定的文档片段启用状态"""
        req = UpdateSegmentEnabledReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.segment_service.update_segment_enabled(dataset_id, document_id, segment_id, req.enabled.data)
        return success_message("修改片段状态成功")