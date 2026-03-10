"""仓库变化量化：用于控制是否触发重分析。"""

from datetime import datetime, timezone
from typing import Dict, List, Optional


def _parse_iso(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _days_between(newer: Optional[str], older: Optional[str]) -> int:
    dt_newer = _parse_iso(newer or "")
    dt_older = _parse_iso(older or "")
    if not dt_newer or not dt_older:
        return 0
    return max(0, (dt_newer - dt_older).days)


def _normalize(value: float, divisor: float) -> float:
    if divisor <= 0:
        return 0.0
    return max(0.0, min(1.0, float(value) / float(divisor)))


def _bucket_rank(rank: int, top_bucket_size: int) -> str:
    bounded = max(1, int(top_bucket_size))
    if rank <= bounded:
        return "top"
    return "other"


def compute_change_score(
    repo: Dict,
    state: Optional[Dict],
    retrieval_delta: Optional[Dict] = None,
    metadata_weight: int = 35,
    activity_weight: int = 35,
    retrieval_weight: int = 30,
) -> float:
    """计算 0-100 的变化分值。"""
    if not state:
        return 100.0

    last_repo_updated_at = str(state.get("last_repo_updated_at") or "")
    repo_updated_at = str(repo.get("updated_at") or "")
    pushed_at = str(repo.get("pushed_at") or repo_updated_at)

    updated_days = _days_between(repo_updated_at, last_repo_updated_at)
    pushed_days = _days_between(pushed_at, last_repo_updated_at)
    metadata_signal = max(_normalize(updated_days, 30), _normalize(pushed_days, 14))

    recent_issues_raw = repo.get("recent_issues")
    recent_prs_raw = repo.get("recent_pull_requests")
    focus_issue_threads_raw = repo.get("focus_issue_threads")
    focus_pr_threads_raw = repo.get("focus_pr_threads")

    recent_issues = recent_issues_raw if isinstance(recent_issues_raw, list) else []
    recent_prs = recent_prs_raw if isinstance(recent_prs_raw, list) else []
    focus_issue_threads = focus_issue_threads_raw if isinstance(focus_issue_threads_raw, list) else []
    focus_pr_threads = focus_pr_threads_raw if isinstance(focus_pr_threads_raw, list) else []

    activity_count = len(recent_issues) + len(recent_prs) + (2 * len(focus_issue_threads)) + (2 * len(focus_pr_threads))
    activity_signal = _normalize(activity_count, 20)

    retrieval_delta = retrieval_delta or {}
    changed_ratio = float(retrieval_delta.get("changed_ratio") or 0)
    retrieval_signal = max(0.0, min(1.0, changed_ratio))

    total_weight = max(1, int(metadata_weight) + int(activity_weight) + int(retrieval_weight))
    score = (
        metadata_signal * int(metadata_weight)
        + activity_signal * int(activity_weight)
        + retrieval_signal * int(retrieval_weight)
    ) / total_weight

    return round(score * 100, 2)


def should_force_reanalysis(
    repo: Dict,
    state: Optional[Dict],
    prompt_hash: str,
    model: str,
    change_score: float,
    threshold: float,
    manual_force: bool,
    top_bucket_size: int,
) -> List[str]:
    """返回触发重分析原因列表；空列表表示可复用历史结果。"""
    reasons: List[str] = []
    if not state:
        return ["first_analysis"]

    if manual_force:
        reasons.append("manual_force")

    previous_prompt_hash = str(state.get("last_prompt_hash") or "")
    if previous_prompt_hash != (prompt_hash or ""):
        reasons.append("prompt_changed")

    previous_model = str(state.get("last_model") or "")
    if previous_model != (model or ""):
        reasons.append("model_changed")

    current_rank = int(repo.get("rank") or 999999)
    current_bucket = _bucket_rank(current_rank, top_bucket_size=top_bucket_size)
    previous_bucket = str(state.get("last_rank_bucket") or "other")
    if previous_bucket != "top" and current_bucket == "top":
        reasons.append("top_bucket_entered")

    if float(change_score or 0) >= float(threshold or 0):
        reasons.append("change_score_threshold")

    return reasons


def calc_days_since_last_analysis(state: Optional[Dict]) -> int:
    """计算距上次分析的天数。"""
    if not state:
        return 999999
    last = _parse_iso(str(state.get("last_analyzed_at") or ""))
    if not last:
        return 999999
    now = datetime.now(timezone.utc)
    return max(0, (now - last).days)
