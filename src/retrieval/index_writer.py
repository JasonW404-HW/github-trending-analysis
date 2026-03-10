"""向量索引写入：支持全量与增量。"""

from typing import Dict, List, Tuple

from src.retrieval.embedder import TextEmbedder
from src.retrieval.vector_store import VectorStore


class IndexWriter:
    """索引写入服务。"""

    def __init__(self, vector_store: VectorStore, embedder: TextEmbedder):
        self.vector_store = vector_store
        self.embedder = embedder

    @staticmethod
    def _build_manifest(chunks: List[Dict]) -> Dict[str, str]:
        return {str(chunk.get("id") or ""): str(chunk.get("hash") or "") for chunk in chunks if chunk.get("id")}

    def _delta_stats(self, previous_manifest: Dict[str, str], current_manifest: Dict[str, str]) -> Dict[str, float]:
        previous_ids = set(previous_manifest.keys())
        current_ids = set(current_manifest.keys())

        added_ids = current_ids - previous_ids
        removed_ids = previous_ids - current_ids
        changed_ids = {
            key for key in current_ids.intersection(previous_ids) if previous_manifest.get(key) != current_manifest.get(key)
        }

        changed_total = len(added_ids) + len(removed_ids) + len(changed_ids)
        base = max(1, len(current_ids.union(previous_ids)))
        return {
            "changed_ratio": min(1.0, changed_total / base),
            "added": float(len(added_ids)),
            "removed": float(len(removed_ids)),
            "changed": float(len(changed_ids)),
        }

    def write_full(self, repo_name: str, chunks: List[Dict]) -> Tuple[Dict, Dict[str, str]]:
        vectors = self.embedder.embed_many([str(chunk.get("text") or "") for chunk in chunks])
        store_info = self.vector_store.full_upsert(repo_name=repo_name, vectors=vectors, chunks=chunks)
        manifest = self._build_manifest(chunks)
        delta = {"changed_ratio": 1.0, "added": float(len(chunks)), "removed": 0.0, "changed": 0.0}
        return {**store_info, **delta}, manifest

    def write_incremental(
        self,
        repo_name: str,
        chunks: List[Dict],
        previous_manifest: Dict[str, str],
    ) -> Tuple[Dict, Dict[str, str]]:
        vectors = self.embedder.embed_many([str(chunk.get("text") or "") for chunk in chunks])
        store_info = self.vector_store.incremental_upsert(repo_name=repo_name, chunks=chunks, vectors=vectors)
        manifest = self._build_manifest(chunks)
        delta = self._delta_stats(previous_manifest=previous_manifest or {}, current_manifest=manifest)
        return {**store_info, **delta}, manifest
