import logging
import random
import time
from datetime import datetime
from uuid import UUID
from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy
from pkg.paginator import Paginator
from sqlalchemy import desc, asc, func
from internal.entity.dataset_entity import ProcessType, SegmentStatus, DocumentStatus
from internal.model import Document, Dataset, UploadFile, ProcessRule, Segment, Account
from internal.exception import ForbiddenException, FailException, NotFoundException
from internal.entity.upload_file_entity import ALLOWED_DOCUMENT_EXTENSION
from internal.entity.cache_entity import LOCK_EXPIRE_TIME, LOCK_DOCUMENT_UPDATED_ENABLED
from internal.task.document_task import build_documents, update_document_enabled, delete_document
from internal.lib.helper import datetime_to_timestamp
from internal.schema.document_schema import GetDocumentsWithPageReq
from redis import Redis

@inject
@dataclass
class DocumentService(BaseService):
    """文档服务"""
    db: SQLAlchemy
    redis_client: Redis

    def create_documents(
            self,
            dataset_id: UUID,
            upload_file_ids: list[UUID],
            process_type: str = ProcessType.AUTOMATIC,
            rule: dict = None,
            account: Account = None
    ) -> tuple[list[Document], str]:
        """根据传递的信息创建文档列表并调用异步任务"""
        dataset = self.get(Dataset, dataset_id)
        if dataset is None or dataset.account_id != account.id:
            raise ForbiddenException("当前用户无该知识库权限或知识库不存在")

        upload_files = self.db.session.query(UploadFile).filter(
            UploadFile.account_id == account.id,
            UploadFile.id.in_(upload_file_ids),
        ).all()

        upload_files = [
            upload_file for upload_file in upload_files
            if upload_file.extension.lower() in ALLOWED_DOCUMENT_EXTENSION
        ]

        if len(upload_files) == 0:
            logging.warning(f"上传文档列表未解析到合法文件, account_id: {account.id}, dataset_id: {dataset_id}, upload_file_ids: {upload_file_ids}")
            raise FailException("暂未解析到合法文件")

        # 创建批次与处理规则并记录到数据库中
        batch = time.strftime("%Y%m%d%H%M%S") + str(random.randint(100000, 999999))
        process_rule = self.create(
            ProcessRule,
            account_id=account.id,
            dataset_id=dataset_id,
            mode=process_type,
            rule=rule,
        )

        # 获取当前知识库的最新文档位置
        position = self.get_latest_document_position(dataset_id)

        # 循环遍历文档列表并记录到数据库
        documents = []
        for upload_file in upload_files:
            position += 1
            document = self.create(
                Document,
                account_id=account.id,
                dataset_id=dataset_id,
                upload_file_id=upload_file.id,
                process_rule_id=process_rule.id,
                batch=batch,
                name=upload_file.name,
                position=position,
            )
            documents.append(document)

        # 调用异步任务完成后续操作
        build_documents.delay([document.id for document in documents])

        return documents, batch

    def get_documents_status(self, dataset_id: UUID, batch: str, account: Account) -> list[dict]:
        """根据传递的知识库id+处理批次获取文档列表状态"""
        dataset = self.get(Dataset, dataset_id)
        if dataset is None or dataset.account_id != account.id:
            raise ForbiddenException("当前用户无该知识库权限或知识库不存在")

        documents = self.db.session.query(Document).filter(
            Document.dataset_id == dataset_id,
            Document.batch == batch,
        ).order_by(asc("position")).all()

        if documents is None or len(documents) == 0:
            raise NotFoundException("该处理批次未发现文档")

        documents_status = []
        for document in documents:
            segment_count = self.db.session.query(func.count(Segment.id)).filter(
                Segment.document_id == document.id
            ).scalar()
            completed_segment_count = self.db.session.query(func.count(Segment.id)).filter(
                Segment.document_id == document.id,
                Segment.status == SegmentStatus.COMPLETED
            ).scalar()

            upload_file = document.upload_file
            documents_status.append({
                "id": document.id,
                "name": document.name,
                "size": upload_file.size,
                "extension": upload_file.extension,
                "mime_type": upload_file.mime_type,
                "position": document.position,
                "segment_count": segment_count,
                "completed_segment_count": completed_segment_count,
                "error": document.error,
                "status": document.status,
                "processing_started_at": datetime_to_timestamp(document.processing_started_at),
                "parsing_completed_at": datetime_to_timestamp(document.parsing_completed_at),
                "splitting_completed_at": datetime_to_timestamp(document.splitting_completed_at),
                "indexing_completed_at": datetime_to_timestamp(document.indexing_completed_at),
                "completed_at": datetime_to_timestamp(document.completed_at),
                "stopped_at": datetime_to_timestamp(document.stopped_at),
                "created_at": datetime_to_timestamp(document.created_at)
            })
        return documents_status

    def get_document(self, dataset_id: UUID, document_id: UUID, account: Account) -> Document:
        """根据传递的知识库id+文档id获取文档记录信息"""
        document = self.get(Document, document_id)
        if document is None:
            raise NotFoundException("该文档不存在")

        if document.dataset_id != dataset_id or document.account_id != account.id:
            raise ForbiddenException("当前用户无权限获取该文档, 请核实后重试")

        return document

    def update_document(self, dataset_id: UUID, document_id: UUID, account: Account, **kwargs) -> Document:
        """根据传递的知识库id+文档id, 更新文档列表"""
        document = self.get(Document, document_id)
        if document is None:
            raise NotFoundException("该文档不存在")

        if document.dataset_id != dataset_id or document.account_id != account.id:
            raise ForbiddenException("当前用户无权限修改该文档, 请核实后重试")

        return self.update(document, **kwargs)

    def update_document_enabled(
            self,
            dataset_id: UUID,
            document_id: UUID,
            enabled: bool,
            account: Account
    ) -> Document:
        """根据传递的知识库id+文档id, 更新文档启用状态, 同时会异步更新weaviate向量数据库中的数据"""
        document = self.get(Document, document_id)
        if document is None:
            raise NotFoundException("该文档不存在")

        if document.dataset_id != dataset_id or document.account_id != account.id:
            raise ForbiddenException("当前用户无权限修改该文档, 请核实后重试")

        if document.status != DocumentStatus.COMPLETED:
            raise ForbiddenException("当前文档处于不可修改状态, 请稍后重试")

        if document.enabled == enabled:
            raise FailException("文档状态修改错误")

        cached_key = LOCK_DOCUMENT_UPDATED_ENABLED.format(document_id=document.id)
        cached_result = self.redis_client.get(cached_key)
        if cached_result is not None:
            raise FailException("当前文档正在修改启用状态, 请稍后")

        # 设置缓存键, 缓存时间为600s
        self.update(
            document,
            enabled=enabled,
            disabled_at=None if enabled else datetime.now(),
        )

        self.redis_client.setex(cached_key, LOCK_EXPIRE_TIME, 1)

        # 启用异步任务
        update_document_enabled.delay(document.id)

        return document

    def delete_document(self, dataset_id: UUID, document_id: UUID, account: Account) -> Document:
        """根据传递的知识库id+文档id删除指定的文档信息, 包含文档片段删除、关键词表更新、weaviate向量数据库中的数据删除"""
        document = self.get(Document, document_id)
        if document is None:
            raise NotFoundException("该文档不存在")

        if document.dataset_id != dataset_id or document.account_id != account.id:
            raise ForbiddenException("当前用户无权限修改该文档, 请核实后重试")

        if document.status not in [DocumentStatus.COMPLETED, DocumentStatus.ERROR]:
            raise ForbiddenException("当前文档处于不可修改状态, 请稍后重试")

        self.delete(document)

        # 调用异步任务
        delete_document.delay(dataset_id, document_id)

        return document

    def get_documents_with_page(
            self,
            dataset_id: UUID,
            req: GetDocumentsWithPageReq,
            account: Account
    ) -> tuple[list[Document], Paginator]:
        """根据传递的知识库id+请求数据获取文档分页列表数据"""
        dataset = self.get(Dataset, dataset_id)
        if dataset is None or dataset.account_id != account.id:
            raise NotFoundException("该知识库不存在或无权限")

        paginator = Paginator(db=self.db, req=req)
        filters = [
            Document.account_id == account.id,
            Document.dataset_id == dataset_id,
        ]
        if req.search_word.data:
            filters.append(Document.name.ilike(f"%{req.search_word.data}%"))

        documents = paginator.paginate(
            self.db.session.query(Document).filter(*filters).order_by(desc("created_at"))
        )
        return documents, paginator


    def get_latest_document_position(self, dataset_id: UUID) -> int:
        """根据传递的知识库id获取最新的文档位置"""
        document = self.db.session.query(Document).filter(
            Document.dataset_id == dataset_id,
        ).order_by(desc("position")).first()
        return document.position if document else 0