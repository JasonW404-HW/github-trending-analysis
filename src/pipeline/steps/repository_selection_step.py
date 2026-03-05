"""仓库筛选步骤：仅负责分析目标筛选。"""

from typing import List, Optional

from src.config import ANALYSIS_KEYWORDS, ANALYSIS_KEYWORD_MATCH_MODE
from src.pipeline.contracts import RepoData, RepoSelectionResult


def build_repository_search_text(repo: RepoData) -> str:
    """构建仓库检索文本。"""
    topics = [str(topic) for topic in (repo.get("topics") or []) if topic]
    parts = [
        str(repo.get("repo_name") or ""),
        str(repo.get("name") or ""),
        str(repo.get("owner") or ""),
        str(repo.get("description") or ""),
        str(repo.get("language") or ""),
        " ".join(topics),
    ]
    return " ".join(part for part in parts if part).lower()


def collect_keyword_matches(repo: RepoData, keywords: List[str]) -> List[str]:
    """收集命中的关键词。"""
    search_text = build_repository_search_text(repo)
    return [keyword for keyword in keywords if keyword.lower() in search_text]


def normalize_keywords(keywords: Optional[List[str]]) -> List[str]:
    """标准化关键词列表。"""
    source = ANALYSIS_KEYWORDS if keywords is None else keywords
    return [keyword.strip() for keyword in source if keyword and keyword.strip()]


def normalize_match_mode(match_mode: Optional[str]) -> str:
    """标准化匹配模式。"""
    normalized = (match_mode or ANALYSIS_KEYWORD_MATCH_MODE or "any").strip().lower()
    if normalized not in {"any", "all"}:
        return "any"
    return normalized


def select_repositories_for_analysis(
    repos: List[RepoData],
    top_n: int,
    keywords: Optional[List[str]] = None,
    match_mode: Optional[str] = None,
) -> RepoSelectionResult:
    """根据关键词策略筛选用于分析的仓库。"""
    if not repos or top_n <= 0:
        return RepoSelectionResult(
            repos=[],
            total_count=len(repos),
            selected_count=0,
            keywords=normalize_keywords(keywords),
            match_mode=normalize_match_mode(match_mode),
        )

    normalized_keywords = normalize_keywords(keywords)
    normalized_match_mode = normalize_match_mode(match_mode)

    if not normalized_keywords:
        selected = [dict(repo) for repo in repos[:top_n]]
        return RepoSelectionResult(
            repos=selected,
            total_count=len(repos),
            selected_count=len(selected),
            keywords=[],
            match_mode=normalized_match_mode,
        )

    selected: List[RepoData] = []
    for repo in repos:
        hits = collect_keyword_matches(repo, normalized_keywords)

        if normalized_match_mode == "all":
            matched = len(hits) == len(normalized_keywords)
        else:
            matched = len(hits) > 0

        if not matched:
            continue

        enriched = dict(repo)
        enriched["keyword_hits"] = hits
        enriched["search_tags"] = [f"kw:{hit}" for hit in hits]
        enriched["search_score"] = len(hits)
        selected.append(enriched)

    selected.sort(
        key=lambda item: (
            -item.get("search_score", 0),
            item.get("rank", 10**9),
        )
    )

    limited = selected[:top_n]
    return RepoSelectionResult(
        repos=limited,
        total_count=len(repos),
        selected_count=len(limited),
        keywords=normalized_keywords,
        match_mode=normalized_match_mode,
    )
