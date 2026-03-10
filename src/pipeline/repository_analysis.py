"""仓库分析步骤：仅负责缓存复用、README 补全与 LLM 分析。"""

import hashlib
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

from src.analysis import RepositorySummarizer
from src.config import (
    ANALYSIS_CUSTOM_PROMPT,
    FORCE_REANALYSIS,
    FETCH_REQUEST_DELAY,
    GITHUB_ACTIVITY_DETAIL_ISSUES_LIMIT,
    GITHUB_ACTIVITY_DETAIL_LAST_COMMENTS,
    GITHUB_ACTIVITY_DETAIL_PRS_LIMIT,
    GITHUB_ACTIVITY_ISSUES_LIMIT,
    GITHUB_ACTIVITY_PRS_LIMIT,
    GITHUB_ACTIVITY_WINDOW_DAYS,
    MODEL,
    REPO_ANALYSIS_INTERVAL,
    REPO_CHANGE_SCORE_THRESHOLD,
    REPO_CHANGE_WEIGHT_ACTIVITY,
    REPO_CHANGE_WEIGHT_METADATA,
    REPO_CHANGE_WEIGHT_RETRIEVAL,
    REPO_TOP_BUCKET_SIZE,
    RETRIEVAL_CHUNK_OVERLAP,
    RETRIEVAL_CHUNK_SIZE,
    RETRIEVAL_TOP_K,
    TOP_N_REPOS_FOR_LLM,
)
from src.infrastructure.database import Database
from src.github import CloneManager, ReadmeFetcher, RepoActivityFetcher
from src.pipeline.models import AnalysisRunResult, AnalysisRunStats, RepoData, SummaryMap
from src.pipeline.change_scoring import calc_days_since_last_analysis, compute_change_score, should_force_reanalysis
from src.retrieval import (
    IndexWriter,
    Retriever,
    TextEmbedder,
    VectorStore,
    chunk_documents,
    extract_repo_documents,
)


SummarizerFactory = Callable[..., RepositorySummarizer]


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
        force_reanalysis: bool = False,
        analysis_interval_days: int = REPO_ANALYSIS_INTERVAL,
        change_score_threshold: int = REPO_CHANGE_SCORE_THRESHOLD,
        clone_manager: Optional[CloneManager] = None,
        vector_store: Optional[VectorStore] = None,
        embedder: Optional[TextEmbedder] = None,
        index_writer: Optional[IndexWriter] = None,
        retriever: Optional[Retriever] = None,
    ):
        self.db = db
        self.readme_fetcher = readme_fetcher or ReadmeFetcher()
        self.activity_fetcher = activity_fetcher or RepoActivityFetcher()
        self.summarizer_factory = summarizer_factory or RepositorySummarizer
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
        self.force_reanalysis = bool(FORCE_REANALYSIS or force_reanalysis)
        self.analysis_interval_days = max(1, int(analysis_interval_days or 1))
        self.change_score_threshold = max(0, int(change_score_threshold or 0))
        self.top_bucket_size = max(1, int(REPO_TOP_BUCKET_SIZE or 5))

        self.clone_manager = clone_manager or CloneManager()
        self.vector_store = vector_store or VectorStore()
        self.embedder = embedder or TextEmbedder()
        self.index_writer = index_writer or IndexWriter(self.vector_store, self.embedder)
        self.retriever = retriever or Retriever(self.vector_store, self.embedder, top_k=RETRIEVAL_TOP_K)

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

        llm_target_repos: List[RepoData] = []
        for repo in pending_repos:
            repo_name = str(repo.get("repo_name") or "")
            if not repo_name:
                continue

            state = self.db.get_repo_analysis_state(repo_name) if hasattr(self.db, "get_repo_analysis_state") else None
            if hasattr(self.db, "get_repo_details"):
                last_detail = self.db.get_repo_details(repo_name)
            else:
                last_detail = None
            retrieval_meta = self._prepare_retrieval_context(repo)
            change_score = compute_change_score(
                repo=repo,
                state=state,
                retrieval_delta=retrieval_meta,
                metadata_weight=REPO_CHANGE_WEIGHT_METADATA,
                activity_weight=REPO_CHANGE_WEIGHT_ACTIVITY,
                retrieval_weight=REPO_CHANGE_WEIGHT_RETRIEVAL,
            )
            force_reasons = should_force_reanalysis(
                repo=repo,
                state=state,
                prompt_hash=prompt_hash,
                model=MODEL,
                change_score=change_score,
                threshold=float(self.change_score_threshold),
                manual_force=self.force_reanalysis,
                top_bucket_size=self.top_bucket_size,
            )
            days_since_last = calc_days_since_last_analysis(state)

            if not force_reasons and last_detail:
                if days_since_last < self.analysis_interval_days:
                    summary_map[repo_name] = last_detail
                    self._record_analysis_reuse(
                        repo=repo,
                        summary=last_detail,
                        prompt_hash=prompt_hash,
                        strategy_hash="analysis-reuse-v1",
                        trigger_reason="reuse_interval_and_low_change",
                        change_score=change_score,
                    )
                    continue

                if change_score < self.change_score_threshold:
                    summary_map[repo_name] = last_detail
                    self._record_analysis_reuse(
                        repo=repo,
                        summary=last_detail,
                        prompt_hash=prompt_hash,
                        strategy_hash="analysis-reuse-v1",
                        trigger_reason="reuse_low_change",
                        change_score=change_score,
                    )
                    continue

            repo["change_score"] = change_score
            repo["reanalysis_reasons"] = force_reasons
            llm_target_repos.append(repo)

        llm_target_repos = llm_target_repos[:TOP_N_REPOS_FOR_LLM]
        if not llm_target_repos:
            return AnalysisRunResult(
                summary_map=summary_map,
                stats=AnalysisRunStats(
                    cached_count=cached_count,
                    pending_count=0,
                    success_count=0,
                    fallback_count=0,
                ),
            )

        summarizer = self.summarizer_factory(extra_prompt=self.extra_prompt)
        strategy_hash = "analysis-reuse-v1"

        def on_success(summary: RepoData) -> None:
            summary.setdefault("prompt_hash", prompt_hash)
            self.db.save_repo_detail(summary, verbose=False)

            repo_name = summary.get("repo_name")
            if repo_name:
                matched_repo = next((repo for repo in llm_target_repos if repo.get("repo_name") == repo_name), {})
                commit_sha = str(matched_repo.get("retrieval_commit_sha") or "")
                change_score = float(matched_repo.get("change_score") or 0)
                rank_bucket = self._build_rank_bucket(int(matched_repo.get("rank") or 999999))
                analyzed_at = self._now_iso()

                if hasattr(self.db, "upsert_repo_analysis_state"):
                    self.db.upsert_repo_analysis_state(
                        repo_name=repo_name,
                        last_analyzed_at=analyzed_at,
                        last_prompt_hash=prompt_hash,
                        last_model=MODEL,
                        last_repo_updated_at=str(matched_repo.get("updated_at") or summary.get("repo_updated_at") or ""),
                        last_commit_sha=commit_sha,
                        last_rank_bucket=rank_bucket,
                        last_change_score=change_score,
                    )
                if hasattr(self.db, "insert_repo_analysis_run"):
                    self.db.insert_repo_analysis_run(
                        repo_name=repo_name,
                        analyzed_at=analyzed_at,
                        model=MODEL,
                        prompt_hash=prompt_hash,
                        strategy_hash=strategy_hash,
                        commit_sha=commit_sha,
                        change_score=change_score,
                        reused=False,
                        trigger_reason=",".join(matched_repo.get("reanalysis_reasons") or []),
                        analysis=summary,
                    )
                summary_map[repo_name] = summary

        analyzed = summarizer.summarize_and_classify(llm_target_repos, on_success=on_success)

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
                pending_count=len(llm_target_repos),
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

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _build_rank_bucket(self, rank: int) -> str:
        return "top" if rank <= self.top_bucket_size else "other"

    def _build_retrieval_query(self, repo: RepoData) -> str:
        parts = [
            str(repo.get("repo_name") or ""),
            str(repo.get("description") or ""),
            " ".join(repo.get("keyword_hits") or []) if isinstance(repo.get("keyword_hits"), list) else "",
            " ".join(issue.get("title", "") for issue in (repo.get("recent_issues") or []) if isinstance(issue, dict)),
            " ".join(pr.get("title", "") for pr in (repo.get("recent_pull_requests") or []) if isinstance(pr, dict)),
        ]
        return "\n".join([part for part in parts if part]).strip()

    def _prepare_retrieval_context(self, repo: RepoData) -> dict:
        repo_name = str(repo.get("repo_name") or "")
        if not repo_name:
            return {"changed_ratio": 0.0}

        repo_url = str(repo.get("url") or "")
        if not repo_url:
            return {"changed_ratio": 0.0}
        try:
            repo_path = self.clone_manager.ensure_latest(repo_name=repo_name, repo_url=repo_url)
        except Exception:
            return {"changed_ratio": 0.0}

        commit_sha = self.clone_manager.get_head_commit_sha(repo_name=repo_name)
        repo["retrieval_commit_sha"] = commit_sha

        documents = extract_repo_documents(repo_path)
        chunks = chunk_documents(
            documents=documents,
            chunk_size=RETRIEVAL_CHUNK_SIZE,
            overlap=RETRIEVAL_CHUNK_OVERLAP,
        )

        if hasattr(self.db, "get_repo_index_state"):
            index_state = self.db.get_repo_index_state(repo_name) or {}
        else:
            index_state = {}
        previous_manifest = index_state.get("manifest_json") if isinstance(index_state.get("manifest_json"), dict) else {}
        indexed_commit_sha = str(index_state.get("indexed_commit_sha") or "")

        if not indexed_commit_sha:
            write_info, manifest = self.index_writer.write_full(repo_name=repo_name, chunks=chunks)
        else:
            write_info, manifest = self.index_writer.write_incremental(
                repo_name=repo_name,
                chunks=chunks,
                previous_manifest=previous_manifest,
            )

        if hasattr(self.db, "upsert_repo_index_state"):
            self.db.upsert_repo_index_state(
                repo_name=repo_name,
                index_backend=str(write_info.get("backend") or "faiss"),
                index_path=str(write_info.get("index_path") or ""),
                embedding_model=self.embedder.model,
                indexed_commit_sha=commit_sha,
                chunk_count=int(write_info.get("chunk_count") or 0),
                manifest=manifest,
            )

        query_text = self._build_retrieval_query(repo)
        snippets = self.retriever.query(repo_name=repo_name, query_text=query_text, top_k=RETRIEVAL_TOP_K)
        repo["retrieval_context_chunks"] = snippets

        return {
            "changed_ratio": float(write_info.get("changed_ratio") or 0),
            "chunk_count": int(write_info.get("chunk_count") or 0),
            "commit_sha": commit_sha,
        }

    def _record_analysis_reuse(
        self,
        repo: RepoData,
        summary: RepoData,
        prompt_hash: str,
        strategy_hash: str,
        trigger_reason: str,
        change_score: float,
    ) -> None:
        repo_name = str(repo.get("repo_name") or "")
        if not repo_name:
            return

        analyzed_at = self._now_iso()
        commit_sha = str(repo.get("retrieval_commit_sha") or "")
        rank_bucket = self._build_rank_bucket(int(repo.get("rank") or 999999))

        if hasattr(self.db, "upsert_repo_analysis_state"):
            self.db.upsert_repo_analysis_state(
                repo_name=repo_name,
                last_analyzed_at=analyzed_at,
                last_prompt_hash=prompt_hash,
                last_model=MODEL,
                last_repo_updated_at=str(repo.get("updated_at") or ""),
                last_commit_sha=commit_sha,
                last_rank_bucket=rank_bucket,
                last_change_score=float(change_score or 0),
            )
        if hasattr(self.db, "insert_repo_analysis_run"):
            self.db.insert_repo_analysis_run(
                repo_name=repo_name,
                analyzed_at=analyzed_at,
                model=MODEL,
                prompt_hash=prompt_hash,
                strategy_hash=strategy_hash,
                commit_sha=commit_sha,
                change_score=float(change_score or 0),
                reused=True,
                trigger_reason=trigger_reason,
                analysis=summary,
            )

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
