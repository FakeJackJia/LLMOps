from uuid import UUID
from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from .retriever_service import RetrievalService
from pkg.sqlalchemy import SQLAlchemy
from internal.schema.dataset_schema import (
    CreateDatasetReq,
    UpdateDatasetReq,
    GetDatasetWithPageReq,
    HitReq,
)
from internal.model import Dataset, Segment, DatasetQuery
from internal.exception import ValidateErrorException, NotFoundException
from internal.entity.dataset_entity import DEFAULT_DATASET_DESCRIPTION_FORMATTER
from internal.lib.helper import datetime_to_timestamp
from pkg.paginator import Paginator
from sqlalchemy import desc

@inject
@dataclass
class DatasetService(BaseService):
    db: SQLAlchemy
    retrieval_service: RetrievalService

    def create_dataset(self, req: CreateDatasetReq) -> Dataset:
        """根据传递的请求信息创建知识库"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        dataset = self.db.session.query(Dataset).filter_by(
            account_id=account_id,
            name=req.name.data
        ).one_or_none()
        if dataset:
            raise ValidateErrorException(f"该知识库{req.name.data}已经存在")

        if req.description.data is None or req.description.data.strip() == "":
            req.description.data = DEFAULT_DATASET_DESCRIPTION_FORMATTER.format(name=req.name.data)

        return self.create(
            Dataset,
            account_id=account_id,
            name=req.name.data,
            icon=req.icon.data,
            description=req.description.data
        )

    def get_dataset(self, dataset_id: UUID) -> Dataset:
        """根据传递的知识库id获取知识库记录"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        dataset = self.get(Dataset, dataset_id)
        if dataset is None or str(dataset.account_id) != account_id:
            raise NotFoundException("该知识库不存在")
        return dataset

    def update_dataset(self, dataset_id: UUID, req: UpdateDatasetReq) -> Dataset:
        """根据传递的知识库id+数据更新知识库"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        dataset = self.get(Dataset, dataset_id)
        if dataset is None or str(dataset.account_id) != account_id:
            raise NotFoundException("该知识库不存在")

        check_dataset = self.db.session.query(Dataset).filter(
            Dataset.account_id == account_id,
            Dataset.name == req.name.data,
            Dataset.id != dataset_id,
        ).one_or_none()
        if check_dataset:
            raise ValidateErrorException(f"该知识库名字{req.name.data}已存在")

        if req.description.data is None or req.description.data.strip() == "":
            req.description.data = DEFAULT_DATASET_DESCRIPTION_FORMATTER.format(name=req.name.data)

        self.update(dataset, name=req.name.data, icon=req.icon.data, description=req.description.data)
        return dataset

    def get_datasets_with_page(self, req: GetDatasetWithPageReq) -> tuple[list[Dataset], Paginator]:
        """根据传递到的信息获取知识库列表分页数据"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        paginator = Paginator(db=self.db, req=req)
        filters = [Dataset.account_id == account_id]
        if req.search_word.data:
            filters.append(Dataset.name.ilike(f"%{req.search_word.data}%"))

        datasets = paginator.paginate(
            self.db.session.query(Dataset).filter(*filters).order_by(desc("created_at"))
        )
        return datasets, paginator

    def hit(self, dataset_id: UUID, req: HitReq) -> list[dict]:
        """根据传递的知识库id+请求执行召回测试"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        dataset = self.get(Dataset, dataset_id)
        if dataset is None or str(dataset.account_id) != account_id:
            raise NotFoundException("该知识库不存在")

        lc_documents = self.retrieval_service.search_in_datasets(
            dataset_ids=[dataset_id],
            **req.data,
        )

        if not lc_documents:
            return []

        lc_document_dict = {str(lc_document.metadata["segment_id"]): lc_document for lc_document in lc_documents}

        segments = self.db.session.query(Segment).filter(
            Segment.id.in_([str(lc_document.metadata["segment_id"]) for lc_document in lc_documents])
        ).all()
        segment_dict = {str(segment.id): segment for segment in segments}

        sorted_segments = [
            segment_dict[str(lc_document.metadata["segment_id"])]
            for lc_document in lc_documents
            if str(lc_document.metadata["segment_id"]) in segment_dict
        ]

        hit_result = []
        for segment in sorted_segments:
            document = segment.document
            upload_file = document.upload_file
            hit_result.append({
                "id": segment.id,
                "document": {
                    "id": document.id,
                    "name": document.name,
                    "extension": upload_file.extension,
                    "mime_type": upload_file.mime_type,
                },
                "dataset_id": segment.dataset_id,
                "score": lc_document_dict[str(segment.id)].metadata["score"],
                "position": segment.position,
                "content": segment.content,
                "keywords": segment.keywords,
                "character_count": segment.character_count,
                "token_count": segment.token_count,
                "hit_count": segment.hit_count,
                "enabled": segment.enabled,
                "disabled_at": datetime_to_timestamp(segment.disabled_at),
                "status": segment.status,
                "error": segment.error,
                "updated_at": datetime_to_timestamp(segment.updated_at),
                "created_at": datetime_to_timestamp(segment.created_at),
            })

        return hit_result

    def get_dataset_queries(self, dataset_id: UUID) -> list[DatasetQuery]:
        """根据传递的知识库id获取最近的10条查询记录"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        dataset = self.get(Dataset, dataset_id)
        if dataset is None or str(dataset.account_id) != account_id:
            raise NotFoundException("该知识库不存在")

        dataset_queries = self.db.session.query(DatasetQuery).filter(
            DatasetQuery.dataset_id == dataset_id,
        ).order_by(desc("created_at")).limit(10).all()

        return dataset_queries
