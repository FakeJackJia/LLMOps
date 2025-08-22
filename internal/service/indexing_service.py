import uuid
from datetime import datetime
import re
import logging
from uuid import UUID
from flask import Flask, current_app
from injector import inject
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy
from internal.model import Document, Segment
from internal.entity.dataset_entity import DocumentStatus, SegmentStatus
from langchain_core.documents import Document as LCDocument
from internal.core.file_extractor import FileExtractor
from internal.entity.cache_entity import (
    LOCK_DOCUMENT_UPDATED_ENABLED,
    LOCK_KEYWORD_TABLE_UPDATE_KEYWORD_TABLE,
    LOCK_EXPIRE_TIME
)
from .process_rule_service import ProcessRuleService
from .embeddings_service import EmbeddingsService
from sqlalchemy import func
from internal.lib.helper import generate_text_hash
from .jieba_service import JiebaService
from .keyword_table_service import KeywordTableService
from .vector_database_service import VectorDatabaseService
from weaviate.classes.query import Filter
from redis import Redis

@inject
@dataclass
class IndexService(BaseService):
    """索引构建服务"""
    db: SQLAlchemy
    file_extractor: FileExtractor
    process_rule_service: ProcessRuleService
    embedding_service: EmbeddingsService
    jieba_service: JiebaService
    keyword_table_service: KeywordTableService
    vector_database_service: VectorDatabaseService
    redis_client: Redis

    def build_documents(self, document_ids: list[UUID]) -> None:
        """根据传递的文档id列表构建知识库文档, 涵盖了加载、分割、索引构建、数据库储存等"""
        documents = self.db.session.query(Document).filter(
            Document.id.in_(document_ids)
        ).all()

        for document in documents:
            try:
                # 更新当前状态为解析中, 并记录开始处理时间
                self.update(document, status=DocumentStatus.PARSING, processing_started_at=datetime.now())

                # 执行文档加载步骤, 并更新文档的状态与时间
                lc_documents = self._parsing(document)

                # 执行文档分割步骤, 并更新文档状态与时间, 涵盖了片段的信息
                lc_segments = self._splitting(document, lc_documents)

                # 执行文档索引构建, 涵盖了关键词提取、并更新数据状态
                self._indexing(document, lc_segments)

                # 存储操作, 涵盖了文档状态更新, 以及向量数据库的存储
                self._completed(document, lc_segments)

            except Exception as e:
                logging.exception(f"构建文档发生错误, 错误信息: {str(e)}")
                self.update(
                    document,
                    status=DocumentStatus.ERROR,
                    error=str(e),
                    stopped_at=datetime.now()
                )

    def update_document_enabled(self, document_id: UUID) -> None:
        """根据传递的文档id更新文档状态, 同时修改weaviate向量数据库中的记录"""
        cached_key = LOCK_DOCUMENT_UPDATED_ENABLED.format(document_id=document_id)

        document = self.get(Document, document_id)

        segments = self.db.session.query(Segment).with_entities(Segment.id, Segment.node_id, Segment.enabled).filter(
            Segment.document_id == document_id,
            Segment.status == SegmentStatus.COMPLETED,
        ).all()

        segment_ids = [id for id, _, _ in segments]
        node_ids = [node_id for _, node_id, _ in segments]

        try:
            collection = self.vector_database_service.collection
            for node_id in node_ids:
                try:
                    collection.data.update(
                        uuid=node_id,
                        properties={
                            "document_enabled": document.enabled,
                        }
                    )
                except Exception as e:
                    with self.db.auto_commit():
                        self.db.session.query(Segment).filter(
                            Segment.node_id == node_id,
                        ).update({
                            "error": str(e),
                            "status": SegmentStatus.ERROR,
                            "enabled": False,
                            "disabled_at": datetime.now(),
                            "stopped_at": datetime.now()
                        })

            if document.enabled:
                enabled_segment_ids = [id for id, _, enabled in segments if enabled]
                self.keyword_table_service.add_keyword_table_from_ids(document.dataset_id, enabled_segment_ids)
            else:
                self.keyword_table_service.delete_keyword_table_from_ids(document.dataset_id, segment_ids)

        except Exception as e:
            logging.exception(f"修改向量数据库文档启用失败 文档id: {document.id}")
            origin_enabled = not document.enabled
            self.update(
                document,
                enabled=origin_enabled,
                disabled_at=None if origin_enabled else datetime.now(),
            )
        finally:
            self.redis_client.delete(cached_key)

    def delete_document(self, dataset_id: UUID, document_id: UUID) -> None:
        """根据传递的文档id+知识库id清除文档信息"""
        segment_ids = [
            id for id, in self.db.session.query(Segment).with_entities(Segment.id).filter(
                Segment.document_id == document_id,
            ).all()
        ]

        collection = self.vector_database_service.collection
        collection.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id),
        )

        with self.db.auto_commit():
            self.db.session.query(Segment).filter(
                Segment.document_id == document_id,
            ).delete()

        self.keyword_table_service.delete_keyword_table_from_ids(dataset_id, segment_ids)

    def _parsing(self, document: Document) -> list[LCDocument]:
        """解析传递的文档为langchain文档列表"""
        upload_file = document.upload_file
        lc_documents = self.file_extractor.load(upload_file, False, True)

        for lc_document in lc_documents:
            lc_document.page_content = self._clean_extra_text(lc_document.page_content)

        self.update(
            document,
            status=DocumentStatus.SPLITTING,
            parsing_completed_at=datetime.now(),
            character_count=sum([len(lc_document.page_content) for lc_document in lc_documents]),
        )

        return lc_documents

    def _splitting(self, document: Document, lc_documents: list[LCDocument]) -> list[LCDocument]:
        """根据传递的信息进行文档分割, 拆分成小块片段"""
        process_rule = document.process_rule
        text_splitter = self.process_rule_service.get_text_splitter_by_process_rule(
            process_rule,
            self.embedding_service.calculate_token_count,
        )

        for lc_document in lc_documents:
            lc_document.page_content = self.process_rule_service.clean_text_by_process_rule(
                lc_document.page_content,
                process_rule
            )

        lc_segments = text_splitter.split_documents(lc_documents)

        position = self.db.session.query(func.coalesce(func.max(Segment.position), 0)).filter(
            Segment.document_id == document.id,
        ).scalar()

        segments = []
        for lc_segment in lc_segments:
            position += 1
            content = lc_segment.page_content
            segment = self.create(
                Segment,
                account_id=document.account_id,
                dataset_id=document.dataset_id,
                document_id=document.id,
                node_id=uuid.uuid4(),
                position=position,
                content=content,
                character_count=len(content),
                token_count=self.embedding_service.calculate_token_count(content),
                hash=generate_text_hash(content),
                status=SegmentStatus.WAITING,
            )
            lc_segment.metadata = {
                "account_id": str(document.account_id),
                "dataset_id": str(document.dataset_id),
                "document_id": str(document.id),
                "segment_id": str(segment.id),
                "node_id": str(segment.node_id),
                "document_enabled": False,
                "segment_enabled": False,
            }
            segments.append(segment)

        self.update(
            document,
            token_count=sum([segment.token_count for segment in segments]),
            status=DocumentStatus.INDEXING,
            splitting_completed_at=datetime.now()
        )

        return lc_segments

    def _indexing(self, document: Document, lc_segments: list[LCDocument]) -> None:
        """根据传递的信息构建索引、涵盖关键词提取、词表构建"""
        for lc_segment in lc_segments:
            keywords = self.jieba_service.extract_keywords(lc_segment.page_content, 10)
            self.db.session.query(Segment).filter(
                Segment.id == lc_segment.metadata["segment_id"]
            ).update({
                "keywords": keywords,
                "status": SegmentStatus.INDEXING,
                "indexing_completed_at": datetime.now(),
            })

            keyword_table_record = self.keyword_table_service.get_keyword_table_from_dataset_id(document.dataset_id)
            keyword_table = {
                field: set(value) for field, value in keyword_table_record.keyword_table.items()
            }

            for keyword in keywords:
                if keyword not in keyword_table:
                    keyword_table[keyword] = set()
                keyword_table[keyword].add(lc_segment.metadata["segment_id"])

            self.update(
                keyword_table_record,
                keyword_table={field: list(value) for field, value in keyword_table.items()}
            )

        self.update(
            document,
            indexing_completed_at=datetime.now()
        )

    def _completed(self, document: Document, lc_segments: list[LCDocument]) -> None:
        """存储文档片段到向量数据库, 并完成状态更新"""
        for lc_segment in lc_segments:
            lc_segment.metadata["document_enabled"] = True
            lc_segment.metadata["segment_enabled"] = True

        # 每次向向量数据库存储10条数据, 避免一次传递过多数据
        def thread_func(flask_app: Flask, chunks: list[LCDocument], ids: list[UUID]) -> None:
            """线程函数, 执行向量数据库与postgre数据存储"""
            with flask_app.app_context():
                try:
                    self.vector_database_service.vector_store.add_documents(chunks, ids=ids)
                    with self.db.auto_commit():
                        self.db.session.query(Segment).filter(
                            Segment.node_id.in_(ids)
                        ).update({
                            "status": SegmentStatus.COMPLETED,
                            "completed_at": datetime.now(),
                            "enabled": True,
                        })
                except Exception as e:
                    logging.exception(f"构建文档片段索引发生异常, 错误信息: {str(e)}")
                    with self.db.auto_commit():
                        self.db.session.query(Segment).filter(
                            Segment.node_id.in_(ids)
                        ).update({
                            "status": SegmentStatus.ERROR,
                            "completed_at": None,
                            "stopped_at": datetime.now(),
                            "enabled": False,
                        })

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []

            for i in range(0, len(lc_segments), 10):
                chunks = lc_segments[i:i+10]
                ids = [chunk.metadata["node_id"] for chunk in chunks]
                futures.append(executor.submit(thread_func, current_app._get_current_object(), chunks, ids))

            for future in futures:
                future.result()

        self.update(
            document,
            status=DocumentStatus.COMPLETED,
            completed_at=datetime.now(),
            enabled=True,
        )

    @classmethod
    def _clean_extra_text(cls, text: str) -> str:
        """清除过滤多余的空白字符串"""
        text = re.sub(r'<\|', '<', text)
        text = re.sub(r'\|>', '>', text)
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\xEF\xBF\xBE]', '', text)
        text = re.sub('\uFFFE', '', text)
        return text
