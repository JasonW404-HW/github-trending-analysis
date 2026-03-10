"""向量索引存储：FAISS 优先，失败时退化为 Numpy。"""

import json
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Tuple

np = importlib.import_module("numpy") if importlib.util.find_spec("numpy") else None

from src.config import RETRIEVAL_INDEX_DIR, VECTOR_BACKEND

faiss = importlib.import_module("faiss") if importlib.util.find_spec("faiss") else None


class VectorStore:
    """为单仓库维护向量索引及元数据。"""

    def __init__(self, index_dir: str = RETRIEVAL_INDEX_DIR, backend: str = VECTOR_BACKEND):
        self.base_dir = Path(index_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.backend = backend if backend in {"faiss", "numpy"} else "faiss"

    def _repo_files(self, repo_name: str) -> Tuple[Path, Path, Path]:
        safe = repo_name.replace("/", "__")
        repo_dir = self.base_dir / safe
        repo_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir / "index.faiss", repo_dir / "vectors.npy", repo_dir / "meta.json"

    def full_upsert(self, repo_name: str, vectors: List[List[float]], chunks: List[Dict]) -> Dict:
        index_path, npy_path, meta_path = self._repo_files(repo_name)
        dim = len(vectors[0]) if vectors else 0
        matrix = []
        if np is not None and vectors:
            matrix = np.array(vectors, dtype="float32")

        meta_payload = {
            "repo_name": repo_name,
            "dim": dim,
            "chunks": chunks,
            "size": len(chunks),
            "vectors": vectors,
        }

        if self.backend == "faiss" and faiss is not None and np is not None and dim > 0:
            index = faiss.IndexFlatIP(dim)
            index.add(matrix)
            faiss.write_index(index, str(index_path))
        elif np is not None:
            np.save(npy_path, matrix)

        meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False), encoding="utf-8")
        return {
            "index_path": str(index_path if index_path.exists() else npy_path),
            "chunk_count": len(chunks),
            "backend": self._effective_backend(dim),
        }

    def incremental_upsert(self, repo_name: str, chunks: List[Dict], vectors: List[List[float]]) -> Dict:
        """增量更新：当前实现基于 manifest 结果做重建，接口保持增量语义。"""
        return self.full_upsert(repo_name=repo_name, vectors=vectors, chunks=chunks)

    def query(self, repo_name: str, query_vector: List[float], top_k: int = 6) -> List[Dict]:
        index_path, npy_path, meta_path = self._repo_files(repo_name)
        if not meta_path.exists():
            return []

        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        chunks = payload.get("chunks", []) if isinstance(payload, dict) else []
        if not chunks:
            return []

        bounded_k = max(1, int(top_k))
        if self.backend == "faiss" and faiss is not None and np is not None and index_path.exists():
            query = np.array([query_vector], dtype="float32")
            index = faiss.read_index(str(index_path))
            scores, indices = index.search(query, bounded_k)
            result: List[Dict] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(chunks):
                    continue
                item = dict(chunks[idx])
                item["score"] = float(score)
                result.append(item)
            return result

        if np is not None and npy_path.exists():
            query = np.array([query_vector], dtype="float32")
            matrix = np.load(npy_path)
            if matrix.size == 0:
                return []
            sims = np.dot(matrix, query[0])
            order = np.argsort(sims)[::-1][:bounded_k]
            result = []
            for idx in order:
                item = dict(chunks[int(idx)])
                item["score"] = float(sims[int(idx)])
                result.append(item)
            return result

        vectors = payload.get("vectors") if isinstance(payload.get("vectors"), list) else []
        if vectors:
            scored: List[tuple[float, int]] = []
            for idx, vector in enumerate(vectors):
                if not isinstance(vector, list):
                    continue
                score = 0.0
                for left, right in zip(vector, query_vector):
                    score += float(left) * float(right)
                scored.append((score, idx))
            scored.sort(key=lambda item: item[0], reverse=True)
            result = []
            for score, idx in scored[:bounded_k]:
                if idx >= len(chunks):
                    continue
                item = dict(chunks[idx])
                item["score"] = float(score)
                result.append(item)
            return result

        return []

    def _effective_backend(self, dim: int) -> str:
        if self.backend == "faiss" and faiss is not None and np is not None and dim > 0:
            return "faiss"
        if np is not None:
            return "numpy"
        return "python"
