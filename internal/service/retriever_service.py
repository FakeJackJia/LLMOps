from uuid import UUID

from injector import inject
from dataclasses import dataclass

from sqlalchemy import update

from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService
from .vector_database_service import VectorDatabaseService
from .jieba_service import JiebaService
from langchain_core.documents import Document as LCDocument
from langchain.retrievers import EnsembleRetriever
from internal.entity.dataset_entity import RetrievalStrategy, RetrievalSource
from internal.model import Dataset, DatasetQuery, Segment, Account
from internal.exception import NotFoundException

@inject
@dataclass
class RetrievalService(BaseService):
    """检索方法"""
    db: SQLAlchemy
    vector_database_service: VectorDatabaseService
    jieba_service: JiebaService

    def search_in_datasets(
            self,
            dataset_ids: list[UUID],
            query: str,
            account: Account,
            retrieval_strategy: str = RetrievalStrategy.SEMANTIC,
            k: int = 4,
            score: float = 0,
            retrieval_source: str = RetrievalSource.HIT_TESTING,
    ) -> list[LCDocument]:
        """根据传递的query+知识库列表执行检索, 并返回检索的文档+得分"""
        datasets = self.db.session.query(Dataset).filter(
            Dataset.id.in_(dataset_ids),
            Dataset.account_id == account.id,
        ).all()
        if datasets is None or len(datasets) == 0:
            raise NotFoundException("当前无知识库可执行检索")
        dataset_ids = [dataset.id for dataset in datasets]

        from internal.core.retrievers import SemanticRetriever, FullTextRetriever
        semantic_retriever = SemanticRetriever(
            dataset_ids=dataset_ids,
            vector_store=self.vector_database_service.vector_store,
            search_kwargs={
                "k": k,
                "score_threshold": score,
            }
        )
        full_text_retriever = FullTextRetriever(
            db=self.db,
            dataset_ids=dataset_ids,
            jieba_service=self.jieba_service,
            search_kwargs={
                "k": k
            }
        )
        hybrid_retriever = EnsembleRetriever(
            retrievers=[semantic_retriever, full_text_retriever],
            weights=[0.5, 0.5],
        )

        if retrieval_strategy == RetrievalStrategy.SEMANTIC:
            lc_documents = semantic_retriever.invoke(query)
        elif retrieval_strategy == RetrievalStrategy.FULL_TEXT:
            lc_documents = full_text_retriever.invoke(query)
        else:
            lc_documents = hybrid_retriever.invoke(query)

        if lc_documents is None:
            return []

        for lc_document in lc_documents:
            self.create(
                DatasetQuery,
                dataset_id=lc_document.metadata["dataset_id"],
                query=query,
                source=retrieval_source,
                # todo: 等待APP配置模块完成后进行调整
                source_app_id=None,
                created_by=account.id
            )

        with self.db.auto_commit():
            stmt = (
                update(Segment)
                .where(Segment.id.in_([lc_document.metadata["segment_id"] for lc_document in lc_documents]))
                .values(hit_count=Segment.hit_count + 1)
            )
            self.db.session.execute(stmt)

        return lc_documents