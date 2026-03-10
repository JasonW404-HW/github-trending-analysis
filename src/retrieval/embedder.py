"""文本向量化适配器。"""

import hashlib
from typing import List

try:
    import litellm
except ImportError:  # pragma: no cover
    litellm = None

from src.config import MODEL, RETRIEVAL_EMBED_MODEL


class TextEmbedder:
    """支持 LiteLLM embeddings，失败时退化为确定性本地向量。"""

    def __init__(self, model: str = RETRIEVAL_EMBED_MODEL):
        self.model = (model or "").strip()

    @staticmethod
    def _fallback_vector(text: str, dim: int = 64) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [digest[index % len(digest)] / 255.0 for index in range(dim)]
        norm = sum(value * value for value in values) ** 0.5 or 1.0
        return [value / norm for value in values]

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        payload = [str(text or "") for text in texts]
        if not payload:
            return []

        embed_model = self.model or MODEL
        if not embed_model or litellm is None:
            return [self._fallback_vector(text) for text in payload]

        try:
            response = litellm.embedding(model=embed_model, input=payload)
            data = response.get("data", []) if isinstance(response, dict) else []
            vectors = [item.get("embedding", []) for item in data if isinstance(item, dict)]
            if len(vectors) == len(payload):
                return vectors
        except Exception:
            pass

        return [self._fallback_vector(text) for text in payload]
