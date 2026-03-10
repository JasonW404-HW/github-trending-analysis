"""仓库文档提取器。"""

from pathlib import Path
from typing import Dict, List


def _is_doc_file(path: Path) -> bool:
    lower = path.name.lower()
    if lower.startswith("readme"):
        return True
    if path.suffix.lower() in {".md", ".rst", ".txt"} and "doc" in str(path.parent).lower():
        return True
    return False


def extract_repo_documents(repo_path: Path) -> List[Dict[str, str]]:
    """提取 README 和 docs 文本。"""
    docs: List[Dict[str, str]] = []

    if not repo_path.exists() or not repo_path.is_dir():
        return docs

    candidates = []
    for entry in repo_path.rglob("*"):
        if not entry.is_file():
            continue
        if ".git" in entry.parts:
            continue
        if _is_doc_file(entry):
            candidates.append(entry)

    for file_path in sorted(candidates):
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if not text:
            continue
        docs.append(
            {
                "path": str(file_path.relative_to(repo_path)),
                "text": text,
            }
        )

    return docs
