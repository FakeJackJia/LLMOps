import hashlib
import os
import uuid
import datetime
from injector import inject
from dataclasses import dataclass
from werkzeug.datastructures import FileStorage
from qcloud_cos import CosConfig, CosS3Client
from internal.model import UploadFile, Account
from internal.exception import FailException
from .upload_file_service import UploadFileService
from internal.entity.upload_file_entity import ALLOWED_DOCUMENT_EXTENSION, ALLOWED_IMAGE_EXTENSION

@inject
@dataclass
class CosService:
    """腾讯云cos对象存储服务"""
    upload_file_service: UploadFileService

    def upload_file(self, file: FileStorage, only_image: bool, account: Account) -> UploadFile:
        """上传文件到腾讯云cos对象存储, 上传后返回文件的信息"""
        filename = file.filename
        extension = filename.rsplit('.', 1)[-1] if "." in filename else ""
        if extension.lower() not in (ALLOWED_IMAGE_EXTENSION + ALLOWED_DOCUMENT_EXTENSION):
            raise FailException(f"该.{extension}文件不能上传")
        elif only_image and extension not in ALLOWED_IMAGE_EXTENSION:
            raise FailException(f"该.{extension}图片不能上传")

        client = self._get_client()
        bucket = self._get_bucket()

        random_filename = str(uuid.uuid4()) + "." + extension
        now = datetime.datetime.now()
        upload_filename = f"{now.year}/{now.month:02d}/{now.day:02d}/{random_filename}"

        # 流式读取上传的数据并将其上传到cos
        file_content = file.stream.read()

        try:
            client.put_object(bucket, file_content, upload_filename)
        except Exception as e:
            raise FailException("上传文件失败, 请稍后再试")

        # 创建upload_file记录
        return self.upload_file_service.create_upload_file(
            account_id=account.id,
            name=filename,
            key=upload_filename,
            size=len(file_content),
            extension=extension,
            mime_type=file.mimetype,
            hash=hashlib.sha3_256(file_content).hexdigest(),
        )

    def download(self, key: str, target_file_path: str):
        """下载cos云端的文件到本地的指定路径"""
        client = self._get_client()
        bucket = self._get_bucket()

        client.download_file(bucket, key, target_file_path)

    @classmethod
    def get_file_url(cls, key: str) -> str:
        """根据传递的cos云端key获取图片的实际url地址"""
        cos_domain = os.getenv("COS_DOMAIN")

        if not cos_domain:
            bucket = os.getenv("COS_BUCKET")
            schema = os.getenv("COS_SCHEME")
            region = os.getenv("COS_REGION")
            cos_domain = f"{schema}://{bucket}.cos.{region}.myqcloud.com"

        return f"{cos_domain}/{key}"

    @classmethod
    def _get_client(cls) -> CosS3Client:
        """获取腾讯云cos对象存储客户端"""
        conf = CosConfig(
            Region=os.getenv("COS_REGION"),
            SecretId=os.getenv("COS_SECRET_ID"),
            SecretKey=os.getenv("COS_SECRET_KEY"),
            Token=None,
            Scheme=os.getenv("COS_SCHEME", "https")
        )
        return CosS3Client(conf)

    @classmethod
    def _get_bucket(cls) -> str:
        """获取存储桶的名字"""
        return os.getenv("COS_BUCKET")