import logging
import random
import time
from uuid import UUID
from injector import inject
from dataclasses import dataclass
from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from internal.entity.dataset_entity import ProcessType
from internal.model import Document, Dataset, UploadFile, ProcessRule
from internal.exception import ForbiddenException, FailException
from internal.entity.upload_file_entity import ALLOWED_DOCUMENT_EXTENSION
from internal.task.document_task import build_documents


@inject
@dataclass
class DocumentService(BaseService):
    """文档服务"""
    db: SQLAlchemy

    def create_documents(
            self,
            dataset_id: UUID,
            upload_file_ids: list[UUID],
            process_type: str = ProcessType.AUTOMATIC,
            rule: dict = None
    ) -> tuple[list[Document], str]:
        """根据传递的信息创建文档列表并调用异步任务"""
        # todo: 等待授权认证模块完成进行切换调整
        account_id = "aab6b349-5ca3-4753-bb21-2bbab7712a51"

        dataset = self.get(Dataset, dataset_id)
        if dataset is None or str(dataset.account_id) != account_id:
            raise ForbiddenException("当前用户无该知识库权限或知识库不存在")

        upload_files = self.db.session.query(UploadFile).filter(
            UploadFile.account_id == account_id,
            UploadFile.id.in_(upload_file_ids),
        ).all()

        upload_files = [
            upload_file for upload_file in upload_files
            if upload_file.extension.lower() in ALLOWED_DOCUMENT_EXTENSION
        ]

        if len(upload_files) == 0:
            logging.warning(f"上传文档列表未解析到合法文件, account_id: {account_id}, dataset_id: {dataset_id}, upload_file_ids: {upload_file_ids}")
            raise FailException("暂未解析到合法文件")

        # 创建批次与处理规则并记录到数据库中
        batch = time.strftime("%Y%m%d%H%M%S") + str(random.randint(100000, 999999))
        process_rule = self.create(
            ProcessRule,
            account_id=account_id,
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
                account_id=account_id,
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

    def get_latest_document_position(self, dataset_id: UUID) -> int:
        """根据传递的知识库id获取最新的文档位置"""
        document = self.db.session.query(Document).filter(
            Document.dataset_id == dataset_id,
        ).order_by(desc("position")).first()
        return document.position if document else 0