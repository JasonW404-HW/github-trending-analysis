from src.retrieval.index_writer import IndexWriter


class DummyEmbedder:
    def embed_many(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class DummyVectorStore:
    def full_upsert(self, repo_name, vectors, chunks):
        return {
            "index_path": f"/tmp/{repo_name}",
            "chunk_count": len(chunks),
            "backend": "python",
        }

    def incremental_upsert(self, repo_name, chunks, vectors):
        return {
            "index_path": f"/tmp/{repo_name}",
            "chunk_count": len(chunks),
            "backend": "python",
        }


def test_index_writer_full_and_incremental_modes():
    writer = IndexWriter(vector_store=DummyVectorStore(), embedder=DummyEmbedder())

    chunks_v1 = [
        {"id": "a", "hash": "h1", "text": "alpha"},
        {"id": "b", "hash": "h2", "text": "beta"},
    ]
    full_info, manifest_v1 = writer.write_full("owner/repo", chunks_v1)

    assert full_info["chunk_count"] == 2
    assert full_info["changed_ratio"] == 1.0
    assert manifest_v1 == {"a": "h1", "b": "h2"}

    chunks_v2 = [
        {"id": "a", "hash": "h1-new", "text": "alpha updated"},
        {"id": "c", "hash": "h3", "text": "gamma"},
    ]
    inc_info, manifest_v2 = writer.write_incremental("owner/repo", chunks_v2, manifest_v1)

    assert inc_info["chunk_count"] == 2
    assert inc_info["changed_ratio"] > 0
    assert manifest_v2 == {"a": "h1-new", "c": "h3"}
