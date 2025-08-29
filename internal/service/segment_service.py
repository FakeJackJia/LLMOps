import logging
import uuid
from uuid import UUID
from datetime import datetime

from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy
from pkg.paginator import Paginator
from internal.schema.segment_schema import (
    GetSegmentsWithPageReq,
    CreateSegmentReq,
    UpdateSegmentReq,
)
from internal.model import Segment, Document, Account
from internal.entity.cache_entity import LOCK_SEGMENT_UPDATE_ENABLED, LOCK_EXPIRE_TIME
from internal.exception import NotFoundException, FailException, ValidateErrorException
from internal.entity.dataset_entity import SegmentStatus, DocumentStatus
from internal.lib.helper import generate_text_hash
from sqlalchemy import asc, func
from redis import Redis
from .keyword_table_service import KeywordTableService
from .vector_database_service import VectorDatabaseService
from .embeddings_service import EmbeddingsService
from .jieba_service import JiebaService
from langchain_core.documents import Document as LCDocument

@inject
@dataclass
class SegmentService(BaseService):
    """片段服务"""
    db: SQLAlchemy
    redis_client: Redis
    keyword_table_service: KeywordTableService
    vector_base_service: VectorDatabaseService
    embedding_service: EmbeddingsService
    jieba_service: JiebaService

    def create_segment(self, dataset_id: UUID, document_id: UUID, req: CreateSegmentReq, account: Account) -> Segment:
        """根据传递的信息新增文档片段"""
        token_count = self.embedding_service.calculate_token_count(req.content.data)
        if token_count > 1000:
            raise ValidateErrorException("片段的内容长度不能超过1000token")

        document = self.get(Document, document_id)
        if document is None or document.dataset_id != dataset_id or document.account_id != account.id:
            raise NotFoundException("该知识库文档不存在或无权限")

        if document.status != DocumentStatus.COMPLETED:
            raise FailException("当前文档不可新增片段")

        position = self.db.session.query(func.coalesce(func.max(Segment.position), 0)).filter(
            Segment.document_id == document_id,
        ).scalar()

        if req.keywords.data is None or len(req.keywords.data) == 0:
            req.keywords.data = self.jieba_service.extract_keywords(req.content.data, 10)

        segment = None
        try:
            position += 1
            segment = self.create(
                Segment,
                account_id=account.id,
                dataset_id=dataset_id,
                document_id=document_id,
                node_id=uuid.uuid4(),
                position=position,
                content=req.content.data,
                character_count=len(req.content.data),
                token_count=token_count,
                keywords=req.keywords.data,
                hash=generate_text_hash(req.content.data),
                enabled=True,
                processing_started_at=datetime.now(),
                indexing_completed_at=datetime.now(),
                completed_at=datetime.now(),
                status=SegmentStatus.COMPLETED
            )

            self.vector_base_service.vector_store.add_documents([LCDocument(
                page_content=req.content.data,
                metadata={
                    "account_id": str(document.account_id),
                    "dataset_id": str(document.dataset_id),
                    "document_id": str(document_id),
                    "segment_id": str(segment.id),
                    "node_id": str(segment.node_id),
                    "document_enabled": document.enabled,
                    "segment_enabled": segment.enabled
                }
            )], ids=[str(segment.node_id)])

            document_character_count, document_token_count = self.db.session.query(
                func.coalesce(func.sum(Segment.character_count), 0),
                func.coalesce(func.sum(Segment.token_count), 0)
            ).filter(
                Segment.document_id == document_id,
            ).first()

            self.update(
                document,
                character_count=document_character_count,
                token_count=document_token_count,
            )

            if document.enabled:
                self.keyword_table_service.add_keyword_table_from_ids(dataset_id, [segment.id])

        except Exception as e:
            logging.exception("新增文档片段异常")

            if segment:
                self.update(
                    segment,
                    error=str(e),
                    status=SegmentStatus.ERROR,
                    enabled=False,
                    disabled_at=datetime.now(),
                    stopped_at=datetime.now()
                )

            raise FailException("新增文档片段失败")


    def update_segment(self, dataset_id: UUID, document_id: UUID, segment_id: UUID, req: UpdateSegmentReq, account: Account) -> Segment:
        """根据传递的信息更新文档片段"""
        segment = self.get(Segment, segment_id)
        if (
                segment is None
                or segment.dataset_id != dataset_id
                or segment.account_id != account.id
                or segment.document_id != document_id
        ):
            raise NotFoundException("该知识库文档片段不存在或无权限")

        if segment.status != SegmentStatus.COMPLETED:
            raise FailException("当前片段不可修改状态")

        token_count = self.embedding_service.calculate_token_count(req.content.data)
        if token_count > 1000:
            raise ValidateErrorException("片段的内容长度不能超过1000token")

        if req.keywords.data is None or len(req.keywords.data) == 0:
            req.keywords.data = self.jieba_service.extract_keywords(req.content.data, 10)

        new_hash = generate_text_hash(req.content.data)
        required_update = segment.hash != new_hash

        try:
            self.update(
                segment,
                content=req.content.data,
                character_count=len(req.content.data),
                token_count=token_count,
                keywords=req.keywords.data,
                hash=new_hash,
            )

            self.keyword_table_service.delete_keyword_table_from_ids(dataset_id, [segment_id])
            self.keyword_table_service.add_keyword_table_from_ids(dataset_id, [segment_id])

            if required_update:
                document = segment.document

                document_character_count, document_token_count = self.db.session.query(
                    func.coalesce(func.sum(Segment.character_count), 0),
                    func.coalesce(func.sum(Segment.token_count), 0)
                ).filter(
                    Segment.document_id == document_id,
                ).first()

                self.update(
                    document,
                    character_count=document_character_count,
                    token_count=document_token_count,
                )

                self.vector_base_service.collection.data.update(
                    uuid=str(segment.node_id),
                    properties={
                        "text": req.content.data,
                    },
                    vector=self.embedding_service.embeddings.embed_query(req.content.data)
                )
        except Exception as e:
            logging.exception("更新文档片段异常")
            raise FailException("更新文档片段失败")

    def get_segments_with_page(
            self,
            dataset_id: UUID,
            document_id: UUID,
            req: GetSegmentsWithPageReq,
            account: Account
    ) -> tuple[list[Segment], Paginator]:
        """根据传递的信息获取片段分页信息"""
        document = self.get(Document, document_id)
        if document is None or document.dataset_id != dataset_id or document.account_id != account.id:
            raise NotFoundException("该知识库文档不存在或无权限")

        paginator = Paginator(db=self.db, req=req)

        filters = [
            Segment.document_id == document.id
        ]
        if req.search_word.data:
            filters.append(Segment.content.ilike(f"%{req.search_word.data}%"))
        segments = paginator.paginate(
            self.db.session.query(Segment).filter(*filters).order_by(asc("position"))
        )

        return segments, paginator

    def get_segment(self, dataset_id: UUID, document_id: UUID, segment_id: UUID, account: Account) -> Segment:
        """根据传递的信息获取文档片段信息"""
        segment = self.get(Segment, segment_id)
        if (
            segment is None
            or segment.dataset_id != dataset_id
            or segment.account_id != account.id
            or segment.document_id != document_id
        ):
            raise NotFoundException("该知识库文档片段不存在或无权限")

        return segment

    def update_segment_enabled(self, dataset_id: UUID, document_id: UUID, segment_id: UUID, enabled: bool, account: Account) -> Segment:
        """根据传递的信息更新片段状态信息"""
        segment = self.get(Segment, segment_id)
        if (
                segment is None
                or segment.dataset_id != dataset_id
                or segment.account_id != account.id
                or segment.document_id != document_id
        ):
            raise NotFoundException("该知识库文档片段不存在或无权限")

        if segment.status != SegmentStatus.COMPLETED:
            raise FailException("当前片段不可修改状态")

        if segment.enabled == enabled:
            raise FailException("片段状态修改错误")

        cache_key = LOCK_SEGMENT_UPDATE_ENABLED.format(segment_id=segment_id)
        cache_result = self.redis_client.get(cache_key)
        if cache_result is not None:
            raise FailException("当前文档片段正在修改, 请稍后")

        with self.redis_client.lock(cache_key, LOCK_EXPIRE_TIME):
            try:
                self.update(
                    segment,
                    enabled=enabled,
                    disabled_at=None if enabled else datetime.now()
                )

                document = segment.document
                if enabled and document.enabled:
                    self.keyword_table_service.add_keyword_table_from_ids(dataset_id, [segment.id])
                else:
                    self.keyword_table_service.delete_keyword_table_from_ids(dataset_id, [segment.id])

                self.vector_base_service.collection.data.update(
                    uuid=segment.node_id,
                    properties={"segment_enabled": enabled}
                )

            except Exception as e:
                logging.exception("更改文档片段启用状态出现异常")
                self.update(
                    segment,
                    error=str(e),
                    status=SegmentStatus.ERROR,
                    enabled=False,
                    disabled_at=datetime.now(),
                    stopped_at=datetime.now(),
                )
                raise FailException("更新文档片段启用失败")

    def delete_segment(self, dataset_id: UUID, document_id: UUID, segment_id: UUID, account: Account) -> Segment:
        """根据传递的信息删除指定片段"""
        segment = self.get(Segment, segment_id)
        if (
                segment is None
                or segment.dataset_id != dataset_id
                or segment.account_id != account.id
                or segment.document_id != document_id
        ):
            raise NotFoundException("该知识库文档片段不存在或无权限")

        if segment.status not in [SegmentStatus.COMPLETED, SegmentStatus.ERROR]:
            raise FailException("当前文档不可删除")

        document = segment.document
        self.delete(segment)

        self.keyword_table_service.delete_keyword_table_from_ids(dataset_id, [segment_id])

        try:
            self.vector_base_service.collection.data.delete_by_id(str(segment.node_id))
        except Exception as e:
            logging.exception("删除文档片段失败")

        document_character_count, document_token_count = self.db.session.query(
            func.coalesce(func.sum(Segment.character_count), 0),
            func.coalesce(func.sum(Segment.token_count), 0)
        ).filter(
            Segment.document_id == document_id,
        ).first()

        self.update(
            document,
            character_count=document_character_count,
            token_count=document_token_count,
        )

        return segment