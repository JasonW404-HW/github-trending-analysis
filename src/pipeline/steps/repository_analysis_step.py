"""仓库分析步骤：仅负责缓存复用、README 补全与 LLM 分析。"""

import hashlib
from typing import Callable, List, Optional, Tuple

from src.claude_summarizer import ClaudeSummarizer
from src.config import (
    ANALYSIS_CUSTOM_PROMPT,
    FETCH_REQUEST_DELAY,
    GITHUB_ACTIVITY_DETAIL_ISSUES_LIMIT,
    GITHUB_ACTIVITY_DETAIL_LAST_COMMENTS,
    GITHUB_ACTIVITY_DETAIL_PRS_LIMIT,
    GITHUB_ACTIVITY_ISSUES_LIMIT,
    GITHUB_ACTIVITY_PRS_LIMIT,
    GITHUB_ACTIVITY_WINDOW_DAYS,
)
from src.database import Database
from src.pipeline.contracts import AnalysisRunResult, AnalysisRunStats, RepoData, SummaryMap
from src.readme_fetcher import ReadmeFetcher
from src.repo_activity_fetcher import RepoActivityFetcher


SummarizerFactory = Callable[..., ClaudeSummarizer]


class RepositoryAnalysisStep:
    """按仓库执行缓存复用、README 补全与 LLM 分析。"""

    def __init__(
        self,
        db: Database,
        readme_fetcher: Optional[ReadmeFetcher] = None,
        activity_fetcher: Optional[RepoActivityFetcher] = None,
        summarizer_factory: Optional[SummarizerFactory] = None,
        fetch_delay: Optional[float] = None,
        extra_prompt: Optional[str] = None,
        activity_window_days: Optional[int] = None,
        activity_issues_limit: Optional[int] = None,
        activity_prs_limit: Optional[int] = None,
        activity_detail_issues_limit: Optional[int] = None,
        activity_detail_prs_limit: Optional[int] = None,
        activity_detail_last_comments: Optional[int] = None,
    ):
        self.db = db
        self.readme_fetcher = readme_fetcher or ReadmeFetcher()
        self.activity_fetcher = activity_fetcher or RepoActivityFetcher()
        self.summarizer_factory = summarizer_factory or ClaudeSummarizer
        self.fetch_delay = FETCH_REQUEST_DELAY if fetch_delay is None else fetch_delay
        self.activity_window_days = max(
            1,
            GITHUB_ACTIVITY_WINDOW_DAYS if activity_window_days is None else int(activity_window_days),
        )
        self.activity_issues_limit = max(
            1,
            GITHUB_ACTIVITY_ISSUES_LIMIT if activity_issues_limit is None else int(activity_issues_limit),
        )
        self.activity_prs_limit = max(
            1,
            GITHUB_ACTIVITY_PRS_LIMIT if activity_prs_limit is None else int(activity_prs_limit),
        )
        self.activity_detail_issues_limit = max(
            0,
            GITHUB_ACTIVITY_DETAIL_ISSUES_LIMIT
            if activity_detail_issues_limit is None
            else int(activity_detail_issues_limit),
        )
        self.activity_detail_prs_limit = max(
            0,
            GITHUB_ACTIVITY_DETAIL_PRS_LIMIT
            if activity_detail_prs_limit is None
            else int(activity_detail_prs_limit),
        )
        self.activity_detail_last_comments = max(
            1,
            GITHUB_ACTIVITY_DETAIL_LAST_COMMENTS
            if activity_detail_last_comments is None
            else int(activity_detail_last_comments),
        )
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

        self._attach_recent_activity(pending_repos)
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
        strategy_salt = (
            "activity-v2|"
            f"{self.activity_window_days}|{self.activity_issues_limit}|{self.activity_prs_limit}|"
            f"{self.activity_detail_issues_limit}|{self.activity_detail_prs_limit}|"
            f"{self.activity_detail_last_comments}"
        )
        prompt_hash = self._build_prompt_hash(self.extra_prompt, strategy_salt=strategy_salt)
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

    def _attach_recent_activity(self, repos: List[RepoData]) -> None:
        """批量补全仓库近期 Issue / PR 活动。"""
        activities = self.activity_fetcher.batch_fetch_recent_activity(
            repos=repos,
            window_days=self.activity_window_days,
            issues_limit=self.activity_issues_limit,
            prs_limit=self.activity_prs_limit,
            detail_issues_limit=self.activity_detail_issues_limit,
            detail_prs_limit=self.activity_detail_prs_limit,
            detail_last_comments=self.activity_detail_last_comments,
            delay=self.fetch_delay,
        )

        for repo in repos:
            repo_name = repo.get("repo_name")
            if not repo_name or repo_name not in activities:
                continue

            activity = activities[repo_name]
            issues = activity.get("issues") if isinstance(activity, dict) else []
            pull_requests = activity.get("pull_requests") if isinstance(activity, dict) else []
            focus_issue_threads = activity.get("focus_issue_threads") if isinstance(activity, dict) else []
            focus_pr_threads = activity.get("focus_pr_threads") if isinstance(activity, dict) else []
            detail_last_comments = (
                activity.get("detail_last_comments") if isinstance(activity, dict) else self.activity_detail_last_comments
            )
            window_days = activity.get("window_days") if isinstance(activity, dict) else self.activity_window_days

            repo["recent_issues"] = issues if isinstance(issues, list) else []
            repo["recent_pull_requests"] = pull_requests if isinstance(pull_requests, list) else []
            repo["focus_issue_threads"] = focus_issue_threads if isinstance(focus_issue_threads, list) else []
            repo["focus_pr_threads"] = focus_pr_threads if isinstance(focus_pr_threads, list) else []
            repo["activity_detail_last_comments"] = (
                int(detail_last_comments)
                if str(detail_last_comments).isdigit()
                else self.activity_detail_last_comments
            )
            repo["activity_window_days"] = int(window_days) if str(window_days).isdigit() else self.activity_window_days

    @staticmethod
    def _build_prompt_hash(extra_prompt: str, strategy_salt: str = "") -> str:
        """计算分析提示词哈希。"""
        payload = "|".join([(extra_prompt or "").strip(), (strategy_salt or "").strip()]).strip("|")
        if not payload:
            return "default"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
