"""向量检索服务。"""

from typing import Dict, List

from src.config import RETRIEVAL_TOP_K
from src.retrieval.embedder import TextEmbedder
from src.retrieval.vector_store import VectorStore


class Retriever:
    """将查询文本映射到仓库向量索引。"""

    def __init__(self, vector_store: VectorStore, embedder: TextEmbedder, top_k: int = RETRIEVAL_TOP_K):
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = max(1, int(top_k))

    def query(self, repo_name: str, query_text: str, top_k: int | None = None) -> List[Dict]:
        text = (query_text or "").strip()
        if not text:
            return []

        vectors = self.embedder.embed_many([text])
        if not vectors:
            return []

        return self.vector_store.query(
            repo_name=repo_name,
            query_vector=vectors[0],
            top_k=top_k or self.top_k,
        )
