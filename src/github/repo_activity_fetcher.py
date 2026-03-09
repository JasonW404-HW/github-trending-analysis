"""仓库活动抓取器：获取近窗口期的 Issue / PR 活动摘要。"""

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from src.config import FETCH_REQUEST_DELAY, GITHUB_API_BASE, GITHUB_TOKEN
from src.util.retry_utils import execute_with_429_retry
from src.util.print_util import logger


class RepoActivityFetcher:
    """抓取仓库近窗口期的 Issue / PR 活动。"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or GITHUB_TOKEN
        self.api_base = GITHUB_API_BASE
        self.delay = FETCH_REQUEST_DELAY

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "GitHub-Topics-Trending/1.0",
            }
        )

        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, object]] = None,
        timeout: int = 30,
        context: str = "GitHub Activity API",
    ) -> requests.Response:
        """执行 GitHub Activity 请求并对 429 进行自动冷却重试。"""

        def operation() -> requests.Response:
            response = self.session.get(url, params=params, timeout=timeout)
            if response.status_code == 429:
                raise requests.HTTPError(
                    f"429 Too Many Requests: {response.text}",
                    response=response,
                )
            return response

        return execute_with_429_retry(operation, context=context)

    @staticmethod
    def _truncate_text(value: object, max_length: int) -> str:
        """按最大长度截断文本。"""
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."

    @staticmethod
    def _normalize_labels(labels: object, max_items: int = 4) -> List[str]:
        """规范化标签数组。"""
        if not isinstance(labels, list):
            return []

        normalized: List[str] = []
        for label in labels:
            if not isinstance(label, dict):
                continue
            name = str(label.get("name") or "").strip()
            if not name or name in normalized:
                continue
            normalized.append(name)

        return normalized[:max_items]

    @staticmethod
    def _normalize_activity_item(item: Dict) -> Dict:
        """规范化 Issue/PR 活动项。"""
        updated_at = str(item.get("updated_at") or "")
        created_at = str(item.get("created_at") or "")
        user = item.get("user") if isinstance(item.get("user"), dict) else {}

        return {
            "number": item.get("number"),
            "title": str(item.get("title") or "").strip(),
            "state": str(item.get("state") or "").strip(),
            "updated_at": updated_at,
            "created_at": created_at,
            "comments": int(item.get("comments") or 0),
            "author": str(user.get("login") or "").strip(),
            "labels": RepoActivityFetcher._normalize_labels(item.get("labels")),
        }

    @staticmethod
    def _normalize_comment_item(item: Dict, max_body_length: int = 280) -> Dict:
        """规范化评论项。"""
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        return {
            "author": str(user.get("login") or "").strip(),
            "created_at": str(item.get("created_at") or "").strip(),
            "updated_at": str(item.get("updated_at") or "").strip(),
            "body": RepoActivityFetcher._truncate_text(item.get("body"), max_body_length),
        }

    @staticmethod
    def _select_focus_items(items: List[Dict], limit: int) -> List[Dict]:
        """按讨论热度优先选择二阶段深挖条目。"""
        bounded_limit = max(0, int(limit))
        if bounded_limit <= 0:
            return []

        ranked = sorted(
            items,
            key=lambda entry: (
                int(entry.get("comments") or 0),
                str(entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return ranked[:bounded_limit]

    def _fetch_issue_comments_tail(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        tail_limit: int = 4,
    ) -> List[Dict]:
        """获取 Issue/PR 对话尾部评论。"""
        bounded_tail = max(1, int(tail_limit))
        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        params = {
            "sort": "created",
            "direction": "desc",
            "per_page": min(100, bounded_tail),
        }

        try:
            response = self._request_with_retry(
                url=url,
                params=params,
                context=f"GitHub Activity Comments {owner}/{repo}#{issue_number}",
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            logger.warning(f"   ⚠️ 获取评论失败 {owner}/{repo}#{issue_number}: {error}")
            return []

        if not isinstance(payload, list):
            return []

        normalized = [
            self._normalize_comment_item(item)
            for item in payload[:bounded_tail]
            if isinstance(item, dict)
        ]
        normalized.reverse()
        return normalized

    def _build_thread_snapshot(
        self,
        owner: str,
        repo: str,
        raw_item: Dict,
        tail_comments: int = 4,
    ) -> Dict:
        """构建二阶段深挖条目（原始内容 + 尾部对话）。"""
        number = raw_item.get("number")
        comments_total = int(raw_item.get("comments") or 0)

        comments: List[Dict] = []
        if isinstance(number, int):
            comments = self._fetch_issue_comments_tail(
                owner=owner,
                repo=repo,
                issue_number=number,
                tail_limit=tail_comments,
            )

        return {
            "number": number,
            "title": str(raw_item.get("title") or "").strip(),
            "state": str(raw_item.get("state") or "").strip(),
            "updated_at": str(raw_item.get("updated_at") or "").strip(),
            "comments_total": comments_total,
            "body": self._truncate_text(raw_item.get("body"), 1200),
            "last_comments": comments,
        }

    def fetch_recent_activity(
        self,
        owner: str,
        repo: str,
        window_days: int = 30,
        issues_limit: int = 6,
        prs_limit: int = 6,
        detail_issues_limit: int = 2,
        detail_prs_limit: int = 2,
        detail_last_comments: int = 4,
    ) -> Dict[str, object]:
        """获取近窗口期仓库活动并拆分为 Issue 与 PR。"""
        bounded_window = max(1, int(window_days))
        bounded_issues_limit = max(1, int(issues_limit))
        bounded_prs_limit = max(1, int(prs_limit))
        bounded_detail_issues_limit = max(0, int(detail_issues_limit))
        bounded_detail_prs_limit = max(0, int(detail_prs_limit))
        bounded_detail_last_comments = max(1, int(detail_last_comments))

        since_dt = datetime.now(timezone.utc) - timedelta(days=bounded_window)
        since = since_dt.isoformat().replace("+00:00", "Z")

        per_page = min(100, max(30, bounded_issues_limit + bounded_prs_limit + 8))
        url = f"{self.api_base}/repos/{owner}/{repo}/issues"
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "since": since,
            "per_page": per_page,
        }

        try:
            response = self._request_with_retry(
                url=url,
                params=params,
                context=f"GitHub Activity {owner}/{repo}",
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            logger.warning(f"   ⚠️ 获取活动失败 {owner}/{repo}: {error}")
            return {
                "window_days": bounded_window,
                "issues": [],
                "pull_requests": [],
                "focus_issue_threads": [],
                "focus_pr_threads": [],
                "detail_last_comments": bounded_detail_last_comments,
            }

        if not isinstance(payload, list):
            payload = []

        issues: List[Dict] = []
        pull_requests: List[Dict] = []
        issue_raw_map: Dict[str, Dict] = {}
        pr_raw_map: Dict[str, Dict] = {}

        for item in payload:
            if not isinstance(item, dict):
                continue

            normalized = self._normalize_activity_item(item)
            is_pull_request = isinstance(item.get("pull_request"), dict)
            number = normalized.get("number")
            number_key = str(number)

            if is_pull_request:
                if len(pull_requests) < bounded_prs_limit:
                    pull_requests.append(normalized)
                    pr_raw_map[number_key] = item
            elif len(issues) < bounded_issues_limit:
                issues.append(normalized)
                issue_raw_map[number_key] = item

            if len(issues) >= bounded_issues_limit and len(pull_requests) >= bounded_prs_limit:
                break

        selected_issues = self._select_focus_items(issues, bounded_detail_issues_limit)
        selected_prs = self._select_focus_items(pull_requests, bounded_detail_prs_limit)

        focus_issue_threads: List[Dict] = []
        for selected in selected_issues:
            number = selected.get("number")
            raw_item = issue_raw_map.get(str(number))
            if not isinstance(raw_item, dict):
                continue
            focus_issue_threads.append(
                self._build_thread_snapshot(
                    owner=owner,
                    repo=repo,
                    raw_item=raw_item,
                    tail_comments=bounded_detail_last_comments,
                )
            )

        focus_pr_threads: List[Dict] = []
        for selected in selected_prs:
            number = selected.get("number")
            raw_item = pr_raw_map.get(str(number))
            if not isinstance(raw_item, dict):
                continue
            focus_pr_threads.append(
                self._build_thread_snapshot(
                    owner=owner,
                    repo=repo,
                    raw_item=raw_item,
                    tail_comments=bounded_detail_last_comments,
                )
            )

        return {
            "window_days": bounded_window,
            "issues": issues,
            "pull_requests": pull_requests,
            "focus_issue_threads": focus_issue_threads,
            "focus_pr_threads": focus_pr_threads,
            "detail_last_comments": bounded_detail_last_comments,
        }

    def batch_fetch_recent_activity(
        self,
        repos: List[Dict],
        window_days: int = 30,
        issues_limit: int = 6,
        prs_limit: int = 6,
        detail_issues_limit: int = 2,
        detail_prs_limit: int = 2,
        detail_last_comments: int = 4,
        delay: Optional[float] = None,
    ) -> Dict[str, Dict[str, object]]:
        """批量获取仓库近窗口期活动。"""
        delay = self.delay if delay is None else delay
        activities: Dict[str, Dict[str, object]] = {}

        logger.info(f"📥 开始批量获取近 {max(1, int(window_days))} 天 Issue/PR 活动...")

        for index, repo in enumerate(repos, 1):
            repo_name = repo.get("repo_name") or repo.get("name", "")
            if not repo_name or "/" not in repo_name:
                continue

            owner, repo_name_only = repo_name.split("/", 1)
            logger.info(f"  [{index}/{len(repos)}] {repo_name}")

            activity = self.fetch_recent_activity(
                owner=owner,
                repo=repo_name_only,
                window_days=window_days,
                issues_limit=issues_limit,
                prs_limit=prs_limit,
                detail_issues_limit=detail_issues_limit,
                detail_prs_limit=detail_prs_limit,
                detail_last_comments=detail_last_comments,
            )
            activities[repo_name] = activity

            if index < len(repos):
                time.sleep(delay)

        logger.info(f"✅ 成功获取 {len(activities)} 个仓库的活动摘要")
        return activities


def fetch_recent_activity(
    owner: str,
    repo: str,
    window_days: int = 30,
    issues_limit: int = 6,
    prs_limit: int = 6,
    detail_issues_limit: int = 2,
    detail_prs_limit: int = 2,
    detail_last_comments: int = 4,
) -> Dict[str, object]:
    """便捷函数：获取仓库近窗口期活动。"""
    fetcher = RepoActivityFetcher()
    return fetcher.fetch_recent_activity(
        owner=owner,
        repo=repo,
        window_days=window_days,
        issues_limit=issues_limit,
        prs_limit=prs_limit,
        detail_issues_limit=detail_issues_limit,
        detail_prs_limit=detail_prs_limit,
        detail_last_comments=detail_last_comments,
    )


def batch_fetch_recent_activity(
    repos: List[Dict],
    window_days: int = 30,
    issues_limit: int = 6,
    prs_limit: int = 6,
    detail_issues_limit: int = 2,
    detail_prs_limit: int = 2,
    detail_last_comments: int = 4,
) -> Dict[str, Dict[str, object]]:
    """便捷函数：批量获取仓库近窗口期活动。"""
    fetcher = RepoActivityFetcher()
    return fetcher.batch_fetch_recent_activity(
        repos=repos,
        window_days=window_days,
        issues_limit=issues_limit,
        prs_limit=prs_limit,
        detail_issues_limit=detail_issues_limit,
        detail_prs_limit=detail_prs_limit,
        detail_last_comments=detail_last_comments,
    )
