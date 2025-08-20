from uuid import UUID
from celery import shared_task


@shared_task
def build_documents(document_ids: list[UUID]) -> None:
    """根据传递的文档id列表, 构建文档"""
    from app.http.module import injector
    from internal.service.indexing_service import IndexService

    indexing_service = injector.get(IndexService)
    indexing_service.build_documents(document_ids)