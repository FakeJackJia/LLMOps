import os
import weaviate
from injector import inject
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_weaviate import WeaviateVectorStore
from weaviate import WeaviateClient
from weaviate.auth import AuthApiKey
from .embeddings_service import EmbeddingsService
from weaviate.collections import Collection

COLLECTION_NAME = "Dataset"

@inject
class VectorDatabaseService:
    """向量数据库服务"""
    client: WeaviateClient
    vector_store: WeaviateVectorStore
    embeddings_service: EmbeddingsService

    def __init__(self, embeddings_service: EmbeddingsService):
        self.embeddings_service = embeddings_service
        self.client = weaviate.connect_to_weaviate_cloud(
            cluster_url=os.getenv("WEAVIATE_URL"),
            auth_credentials=AuthApiKey(os.getenv("WEAVIATE_API_KEY"))
        )

        self.vector_store = WeaviateVectorStore(
            client=self.client,
            index_name=COLLECTION_NAME,
            text_key="text",
            embedding=self.embeddings_service.embeddings,
        )

    def get_retriever(self) -> VectorStoreRetriever:
        """获取检索器"""
        return self.vector_store.as_retriever()

    @property
    def collection(self) -> Collection:
        return self.client.collections.get(COLLECTION_NAME)