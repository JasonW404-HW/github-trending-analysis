"""仓库分析步骤：仅负责缓存复用、README 补全与 LLM 分析。"""

import hashlib
from typing import Callable, List, Optional, Tuple

from src.claude_summarizer import ClaudeSummarizer
from src.config import ANALYSIS_CUSTOM_PROMPT, FETCH_REQUEST_DELAY
from src.database import Database
from src.pipeline.contracts import AnalysisRunResult, AnalysisRunStats, RepoData, SummaryMap
from src.readme_fetcher import ReadmeFetcher


SummarizerFactory = Callable[..., ClaudeSummarizer]


class RepositoryAnalysisStep:
    """按仓库执行缓存复用、README 补全与 LLM 分析。"""

    def __init__(
        self,
        db: Database,
        readme_fetcher: Optional[ReadmeFetcher] = None,
        summarizer_factory: Optional[SummarizerFactory] = None,
        fetch_delay: Optional[float] = None,
        extra_prompt: Optional[str] = None,
    ):
        self.db = db
        self.readme_fetcher = readme_fetcher or ReadmeFetcher()
        self.summarizer_factory = summarizer_factory or ClaudeSummarizer
        self.fetch_delay = FETCH_REQUEST_DELAY if fetch_delay is None else fetch_delay
        self.extra_prompt = (
            ANALYSIS_CUSTOM_PROMPT if extra_prompt is None else extra_prompt
        ).strip()

    def analyze(self, repos: List[RepoData]) -> AnalysisRunResult:
        """执行仓库分析并返回摘要映射与统计。"""
        if not repos:
            return AnalysisRunResult(
                summary_map={},
                stats=AnalysisRunStats(
                    cached_count=0,
                    pending_count=0,
                    success_count=0,
                    fallback_count=0,
                ),
            )

        summary_map, pending_repos, prompt_hash = self._split_cached_and_pending(repos)
        cached_count = len(summary_map)

        if not pending_repos:
            return AnalysisRunResult(
                summary_map=summary_map,
                stats=AnalysisRunStats(
                    cached_count=cached_count,
                    pending_count=0,
                    success_count=0,
                    fallback_count=0,
                ),
            )

        self._attach_readme_summaries(pending_repos)
        summarizer = self.summarizer_factory(extra_prompt=self.extra_prompt)

        def on_success(summary: RepoData) -> None:
            summary.setdefault("prompt_hash", prompt_hash)
            self.db.save_repo_detail(summary, verbose=False)

            repo_name = summary.get("repo_name")
            if repo_name:
                summary_map[repo_name] = summary

        analyzed = summarizer.summarize_and_classify(pending_repos, on_success=on_success)

        success_count = 0
        fallback_count = 0
        for summary in analyzed:
            repo_name = summary.get("repo_name")
            if not repo_name:
                continue

            summary_map[repo_name] = summary
            if summary.get("fallback"):
                fallback_count += 1
            else:
                success_count += 1

        return AnalysisRunResult(
            summary_map=summary_map,
            stats=AnalysisRunStats(
                cached_count=cached_count,
                pending_count=len(pending_repos),
                success_count=success_count,
                fallback_count=fallback_count,
            ),
        )

    def _split_cached_and_pending(
        self,
        repos: List[RepoData],
    ) -> Tuple[SummaryMap, List[RepoData], str]:
        """拆分缓存命中仓库和待分析仓库。"""
        prompt_hash = self._build_prompt_hash(self.extra_prompt)
        summary_map: SummaryMap = {}
        pending_repos: List[RepoData] = []

        for repo in repos:
            repo_name = repo.get("repo_name")
            repo_updated_at = repo.get("updated_at", "")

            if not repo_name:
                continue

            cached = self.db.get_repo_details_if_fresh(
                repo_name,
                repo_updated_at,
                prompt_hash=prompt_hash,
            )
            if cached:
                summary_map[repo_name] = cached
                continue

            pending_repos.append(dict(repo))

        return summary_map, pending_repos, prompt_hash

    def _attach_readme_summaries(self, repos: List[RepoData]) -> None:
        """批量补全仓库 README 摘要。"""
        summaries = self.readme_fetcher.batch_fetch_readmes(repos, delay=self.fetch_delay)

        for repo in repos:
            repo_name = repo.get("repo_name")
            if repo_name and repo_name in summaries:
                repo["readme_summary"] = summaries[repo_name]

    @staticmethod
    def _build_prompt_hash(extra_prompt: str) -> str:
        """计算分析提示词哈希。"""
        payload = (extra_prompt or "").strip()
        if not payload:
            return "default"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
