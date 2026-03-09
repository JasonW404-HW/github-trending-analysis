"""GitHub Topics 趋势分析工作流。"""

from typing import List, Optional, Tuple

from src.config import (
    ANALYSIS_KEYWORDS,
    ANALYSIS_KEYWORD_MATCH_MODE,
    GITHUB_CACHE_MINUTES,
    TOP_N_REPOS_FOR_DETAILS,
)
from src.infrastructure.database import Database
from src.github import GitHubFetcher
from src.pipeline.models import AnalysisRunResult, PipelineRunResult, RepoData, RepoSelectionResult
from src.pipeline.repository_analysis import RepositoryAnalysisStep
from src.pipeline.repository_selection import select_repositories_for_analysis
from src.analysis import TrendAnalyzer


class TrendingWorkflow:
    """聚合抓取、分析与趋势计算的业务工作流。"""

    def __init__(
        self,
        db: Database,
        fetcher: Optional[GitHubFetcher] = None,
        analysis_step: Optional[RepositoryAnalysisStep] = None,
        trend_analyzer: Optional[TrendAnalyzer] = None,
    ):
        self.db = db
        self.fetcher = fetcher or GitHubFetcher()
        self.analysis_step = analysis_step or RepositoryAnalysisStep(db=db)
        self.trend_analyzer = trend_analyzer or TrendAnalyzer(db)

    def fetch_rankings(
        self,
        date: str,
        limit: int = 100,
        cache_minutes: int = GITHUB_CACHE_MINUTES,
    ) -> Tuple[List[RepoData], bool]:
        """获取仓库排行（带缓存）。"""
        return self.fetcher.fetch_with_cache(
            db=self.db,
            date=date,
            sort_by="stars",
            limit=limit,
            cache_minutes=cache_minutes,
        )

    def persist_snapshot(self, date: str, repos: List[RepoData]) -> None:
        """保存抓取快照。"""
        self.db.save_today_data(date, repos)

    def fetch_single_repository(self, repo_identifier: str) -> Optional[RepoData]:
        """获取单仓库数据（owner/repo）。"""
        return self.fetcher.fetch_single_repository(repo_identifier, rank=1)

    def select_analysis_targets(
        self,
        repos: List[RepoData],
        top_n: int = TOP_N_REPOS_FOR_DETAILS,
    ) -> RepoSelectionResult:
        """按策略筛选待分析仓库。"""
        return select_repositories_for_analysis(
            repos=repos,
            top_n=top_n,
            keywords=ANALYSIS_KEYWORDS,
            match_mode=ANALYSIS_KEYWORD_MATCH_MODE,
        )

    def analyze_selected(self, selection: RepoSelectionResult) -> AnalysisRunResult:
        """执行选中仓库的 AI 分析。"""
        return self.analysis_step.analyze(selection.repos)

    def calculate_trends(
        self,
        repos: List[RepoData],
        date: str,
        analysis: AnalysisRunResult,
    ) -> dict:
        """计算趋势结果。"""
        return self.trend_analyzer.calculate_trends(repos, date, analysis.summary_map)

    def run(
        self,
        date: str,
        fetch_limit: int = 100,
        top_n: int = TOP_N_REPOS_FOR_DETAILS,
    ) -> PipelineRunResult:
        """执行完整工作流。"""
        repos, cache_hit = self.fetch_rankings(date=date, limit=fetch_limit)
        self.persist_snapshot(date=date, repos=repos)
        selection = self.select_analysis_targets(repos=repos, top_n=top_n)
        analysis = self.analyze_selected(selection)
        trends = self.calculate_trends(repos=repos, date=date, analysis=analysis)

        return PipelineRunResult(
            date=date,
            repos=repos,
            cache_hit=cache_hit,
            selection=selection,
            analysis=analysis,
            trends=trends,
        )
