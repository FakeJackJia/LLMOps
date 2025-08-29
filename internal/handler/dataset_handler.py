from uuid import UUID
from injector import inject
from dataclasses import dataclass
from internal.schema.dataset_schema import (
    CreateDatasetReq,
    GetDatasetResp,
    UpdateDatasetReq,
    GetDatasetWithPageReq,
    GetDatasetWithPageResp,
    HitReq,
    GetDatasetQueriesResp,
)
from flask import request
from flask_login import login_required, current_user
from pkg.response import validate_error_json, success_message, success_json
from pkg.paginator import PageModel
from pkg.sqlalchemy import SQLAlchemy
from internal.service import DatasetService, EmbeddingsService, JiebaService
from internal.core.file_extractor import FileExtractor
from internal.model import UploadFile

@inject
@dataclass
class DatasetHandler:
    """知识库处理器"""
    dataset_service: DatasetService
    embedding_service: EmbeddingsService
    jieba_service: JiebaService
    file_extractor: FileExtractor
    db: SQLAlchemy

    @login_required
    def embedding_query(self):
        upload_file = self.db.session.query(UploadFile).get("b71e7122-267a-4f7d-a3c5-a5b2c3fd752f")
        content = self.file_extractor.load(upload_file, True)
        return success_json({"content": content})

    @login_required
    def hit(self, dataset_id: UUID):
        """根据传递的知识库id+检索参数执行召回测试"""
        req = HitReq()
        if not req.validate():
            return validate_error_json(req.errors)

        hit_result = self.dataset_service.hit(dataset_id, req, current_user)
        return success_json(hit_result)

    @login_required
    def get_dataset_queries(self, dataset_id: UUID):
        """根据传递的知识库id获取最近的10条查询记录"""
        dataset_queries = self.dataset_service.get_dataset_queries(dataset_id, current_user)

        resp = GetDatasetQueriesResp(many=True)
        return success_json(resp.dump(dataset_queries))

    @login_required
    def create_dataset(self):
        """创建知识库"""
        req = CreateDatasetReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.dataset_service.create_dataset(req, current_user)
        return success_message("知识库创建成功")

    @login_required
    def get_dataset(self, dataset_id: UUID):
        """根据传递的知识库id获取详情"""
        dataset = self.dataset_service.get_dataset(dataset_id, current_user)

        resp = GetDatasetResp()
        return success_json(resp.dump(dataset))

    @login_required
    def update_dataset(self, dataset_id: UUID):
        """根据传递的知识库id+信息更新数据库"""
        req = UpdateDatasetReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.dataset_service.update_dataset(dataset_id, req, current_user)
        return success_message("知识库更新成功")

    @login_required
    def get_datasets_with_page(self):
        """获取知识库分页+搜索列表数据"""
        req = GetDatasetWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        datasets, paginator = self.dataset_service.get_datasets_with_page(req, current_user)

        resp = GetDatasetWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(datasets), paginator=paginator))

    @login_required
    def delete_dataset(self, dataset_id: UUID):
        """删除指定知识库"""
        self.dataset_service.delete_dataset(dataset_id, current_user)
        return success_message("删除知识库成功")