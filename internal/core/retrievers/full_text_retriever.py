from typing import List
from uuid import UUID
from collections import Counter
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from langchain_core.retrievers import BaseRetriever
from langchain_core.pydantic_v1 import Field
from pkg.sqlalchemy import SQLAlchemy
from internal.service import JiebaService
from internal.model import KeywordTable, Segment, Document


class FullTextRetriever(BaseRetriever):
    """全文检索器"""
    db: SQLAlchemy
    dataset_ids: list[UUID]
    jieba_service: JiebaService
    search_kwargs: dict = Field(default_factory=dict)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[LCDocument]:
        """根据传递的query执行关键词检索"""
        keywords = self.jieba_service.extract_keywords(query, 10)

        keyword_tables = [
            keyword_table for keyword_table, in self.db.session.query(KeywordTable).with_entities(KeywordTable.keyword_table).filter(
            KeywordTable.dataset_id.in_(self.dataset_ids)
        ).all()]

        all_ids = []
        for keyword_table in keyword_tables:
            for keyword, segment_ids in keyword_table.items():
                if keyword in keywords:
                    all_ids.extend(segment_ids)

        if all_ids is None:
            return []

        id_counter = Counter(all_ids)
        k = self.search_kwargs.get("k", 4)
        top_k_ids = id_counter.most_common(k)

        segments = (self.db.session.query(Segment)
                    .join(Document, Segment.document_id == Document.id)
                    .filter(
            Segment.id.in_([id for id, _ in top_k_ids]),
            Segment.enabled==True,
            Document.enabled==True
        ).all())

        if not segments:
            return []

        segment_dict = {
            str(segment.id): segment for segment in segments
        }
        sorted_segments = [segment_dict[str(id)] for id,freq in top_k_ids if id in segment_dict]

        lc_documents = [LCDocument(
            page_content=segment.content,
            metadata={
                "account_id": str(segment.account_id),
                "dataset_id": str(segment.dataset_id),
                "document_id": str(segment.document_id),
                "segment_id": str(segment.id),
                "node_id": str(segment.node_id),
                "document_enabled": True,
                "segment_enabled": True,
                "score": 0,
            }
        ) for segment in sorted_segments]

        return lc_documents