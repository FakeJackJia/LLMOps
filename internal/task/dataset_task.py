from uuid import UUID

from celery import shared_task

@shared_task
def delete_dataset(dataset_id: UUID) -> None:
    """删除特定的知识库"""
    from app.http.app import injector
    from internal.service import IndexService

    indexing_service = injector.get(IndexService)
    indexing_service.delete_dataset(dataset_id)