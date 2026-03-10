"""文本切片工具。"""

import hashlib
from typing import Dict, List


def chunk_documents(documents: List[Dict[str, str]], chunk_size: int, overlap: int) -> List[Dict[str, str]]:
    """将文档切分为稳定 chunk。"""
    bounded_size = max(200, int(chunk_size))
    bounded_overlap = max(0, min(int(overlap), bounded_size // 2))

    chunks: List[Dict[str, str]] = []
    step = max(1, bounded_size - bounded_overlap)

    for doc in documents:
        path = str(doc.get("path") or "")
        text = str(doc.get("text") or "")
        if not text:
            continue

        for offset in range(0, len(text), step):
            piece = text[offset:offset + bounded_size].strip()
            if not piece:
                continue
            chunk_id = hashlib.sha1(f"{path}:{offset}:{piece[:64]}".encode("utf-8")).hexdigest()[:24]
            chunk_hash = hashlib.sha1(piece.encode("utf-8")).hexdigest()
            chunks.append(
                {
                    "id": chunk_id,
                    "hash": chunk_hash,
                    "path": path,
                    "offset": str(offset),
                    "text": piece,
                }
            )

    return chunks
