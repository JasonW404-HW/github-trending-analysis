"""Pipeline 运行契约数据模型。"""

from dataclasses import dataclass
from typing import Any, Dict, List


RepoData = Dict[str, Any]
SummaryMap = Dict[str, RepoData]


@dataclass
class RepoSelectionResult:
    """仓库筛选结果。"""

    repos: List[RepoData]
    total_count: int
    selected_count: int
    keywords: List[str]
    match_mode: str


@dataclass
class AnalysisRunStats:
    """分析执行统计。"""

    cached_count: int
    pending_count: int
    success_count: int
    fallback_count: int


@dataclass
class AnalysisRunResult:
    """分析执行结果。"""

    summary_map: SummaryMap
    stats: AnalysisRunStats


@dataclass
class PipelineRunResult:
    """端到端流水线执行结果。"""

    date: str
    repos: List[RepoData]
    cache_hit: bool
    selection: RepoSelectionResult
    analysis: AnalysisRunResult
    trends: Dict[str, Any]
