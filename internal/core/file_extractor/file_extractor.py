import os
import tempfile
from pathlib import Path
from typing import Union
import requests
from injector import inject
from dataclasses import dataclass
from internal.service import CosService
from internal.model import UploadFile
from langchain_core.documents import Document as LCDocument
from langchain_community.document_loaders import (
    UnstructuredExcelLoader,
    UnstructuredPDFLoader,
    UnstructuredMarkdownLoader,
    UnstructuredHTMLLoader,
    UnstructuredCSVLoader,
    UnstructuredPowerPointLoader,
    UnstructuredXMLLoader,
    UnstructuredFileLoader,
    TextLoader
)

@inject
@dataclass
class FileExtractor:
    """文件提取器, 用于将远程文件、upload_file记录加载成LangChain对应的文档或字符串"""
    cos_service: CosService

    def load(
            self,
            upload_file: UploadFile,
            return_text: bool = False,
            is_unstructured: bool = True
    ) -> Union[list[LCDocument], str]:
        """加载传入的upload_file记录, 返回LangChain文档列表或者字符串"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, os.path.basename(upload_file.key))
            self.cos_service.download(upload_file.key, file_path)
            return self.load_from_file(file_path, return_text, is_unstructured)

    @classmethod
    def load_from_url(cls, url: str, return_text: bool = False) -> Union[list[LCDocument], str]:
        """从传入的URL中去加载数据库, 返回LangChain文档列表或者字符串"""
        response = requests.get(url)
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, os.path.basename(url))
            with open(file_path, "wb") as file:
                file.write(response.content)

            return cls.load_from_file(file_path, return_text)

    @classmethod
    def load_from_file(
            cls,
            file_path: str,
            return_text: bool = False,
            is_unstructured: bool = True,
    ) -> Union[list[LCDocument], str]:
        """从本地文件中加载数据, 返回LangChain文档列表或字符串"""
        delimiter = "\n\n"
        file_extension = Path(file_path).suffix.lower()

        if file_extension in [".xlsx", ".xls"]:
            loader = UnstructuredExcelLoader(file_path)
        elif file_extension == '.pdf':
            loader = UnstructuredPDFLoader(file_path)
        elif file_extension in [".md", ".markdown"]:
            loader = UnstructuredMarkdownLoader(file_path)
        elif file_extension in [".htm", ".html"]:
            loader = UnstructuredHTMLLoader(file_path)
        elif file_extension == ".csv":
            loader = UnstructuredCSVLoader(file_path)
        elif file_extension in [".ppt", ".pptx"]:
            loader = UnstructuredPowerPointLoader(file_path)
        elif file_extension == ".xml":
            loader = UnstructuredXMLLoader(file_path)
        else:
            loader = UnstructuredFileLoader(file_path) if is_unstructured else TextLoader(file_path)

        return delimiter.join([document.page_content for document in loader.load()]) if return_text else loader.load()