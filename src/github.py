"""
GitHub Fetcher - 从 GitHub API 获取仓库数据
使用 GitHub Search API 按话题获取仓库
"""
import time
import requests
from typing import Dict, List, Optional, Tuple, Mapping, Any
from datetime import datetime, timedelta, timezone

from src.config import (
    GITHUB_TOKEN, TOPIC, GITHUB_API_BASE,
    GITHUB_PER_PAGE, GITHUB_MAX_PAGES, GITHUB_SEARCH_SORT,
    GITHUB_SEARCH_ORDER, FETCH_REQUEST_DELAY, GITHUB_CACHE_MINUTES
)
from src.retry_utils import execute_with_429_retry


class GitHubFetcher:
    """从 GitHub API 获取仓库数据"""

    def __init__(self, token: Optional[str] = None, topic: Optional[str] = None):
        """
        初始化

        Args:
            token: GitHub Personal Access Token
            topic: 要搜索的 GitHub Topic
        """
        self.token = token or GITHUB_TOKEN
        self.topic = topic or TOPIC
        self.api_base = GITHUB_API_BASE
        self.per_page = GITHUB_PER_PAGE
        self.max_pages = GITHUB_MAX_PAGES
        self.delay = FETCH_REQUEST_DELAY

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Topics-Trending/1.0"
        })

        if self.token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}"
            })

        self.rate_limit_remaining = 5000
        self.rate_limit_reset = None

    def fetch(self, sort_by: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
        """
        获取指定话题下的仓库列表

        Args:
            sort_by: 排序方式 (stars, forks, updated)
            limit: 最大返回数量

        Returns:
            [
                {
                    "rank": 1,
                    "repo_name": "owner/repo",
                    "owner": "owner",
                    "stars": 1000,
                    "forks": 100,
                    "issues": 10,
                    "language": "Python",
                    "url": "https://github.com/owner/repo",
                    "description": "...",
                    "topics": ["topic1", "topic2"],
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z"
                },
                ...
            ]
        """
        sort_by = sort_by or GITHUB_SEARCH_SORT
        limit = limit or (self.per_page * self.max_pages)

        print(f"📡 正在获取话题 '{self.topic}' 的仓库列表...")
        print(f"   排序方式: {sort_by}")

        repos = []
        page = 1

        while page <= self.max_pages and len(repos) < limit:
            # 检查速率限制
            if self.rate_limit_remaining < 10:
                self._wait_for_rate_limit()

            page_result = self._fetch_page(page, sort_by)
            if not page_result:
                break

            data = page_result.get("data") or {}

            if not data or "items" not in data:
                break

            items = data["items"]
            if not items:
                break

            for item in items:
                repo = self._parse_repo_item(item, len(repos) + 1)
                repos.append(repo)

                if len(repos) >= limit:
                    break

            print(f"   第 {page} 页: 获取 {len(items)} 个仓库 (累计 {len(repos)})")

            # 如果返回数量少于 per_page，说明已经到最后一页
            if len(items) < self.per_page:
                break

            page += 1

            # 请求间隔
            if page <= self.max_pages and len(repos) < limit:
                time.sleep(self.delay)

        print(f"✅ 成功获取 {len(repos)} 个仓库")
        return repos

    def fetch_with_cache(
        self,
        db,
        date: str,
        sort_by: Optional[str] = None,
        limit: Optional[int] = None,
        cache_minutes: Optional[int] = None,
    ) -> Tuple[List[Dict], bool]:
        """
        带缓存的仓库抓取：周期内优先复用本地数据，周期外通过 ETag 验证

        Args:
            db: Database 实例
            date: 当日日期 YYYY-MM-DD
            sort_by: 排序方式
            limit: 抓取上限
            cache_minutes: 缓存周期（分钟）

        Returns:
            (repos, cache_hit)
        """
        sort_by = sort_by or GITHUB_SEARCH_SORT
        limit = limit or (self.per_page * self.max_pages)
        cache_minutes = cache_minutes or GITHUB_CACHE_MINUTES
        request_key = self._build_request_key(sort_by, limit)

        state: Dict[str, Optional[str]] = db.get_github_fetch_state(request_key) or {}
        cached_repos = db.get_repos_by_date(date)
        cached_has_updated_at = self._repos_have_updated_at(cached_repos)
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1) 周期内并且本地已有今日数据，直接命中
        if cached_repos and self._is_within_cache_window(state.get("last_checked_at"), cache_minutes) and cached_has_updated_at:
            print(f"♻️ GitHub 缓存命中（周期内 {cache_minutes} 分钟），复用本地数据")
            db.upsert_github_fetch_state(
                request_key=request_key,
                etag=state.get("etag"),
                last_checked_at=now_iso,
                last_success_at=state.get("last_success_at"),
            )
            return cached_repos, True

        if cached_repos and self._is_within_cache_window(state.get("last_checked_at"), cache_minutes) and not cached_has_updated_at:
            print("⚠️ 本地缓存缺少 updated_at，跳过周期直返，执行校验刷新")

        # 2) 周期外使用 ETag 做条件请求（仅检查第一页）
        first_etag = state.get("etag")
        first_page = self._fetch_page(1, sort_by, if_none_match=first_etag)

        if first_page and first_page.get("status_code") == 304 and cached_repos and cached_has_updated_at:
            print("♻️ GitHub ETag 命中，数据未变化，复用本地数据")
            db.upsert_github_fetch_state(
                request_key=request_key,
                etag=first_etag or first_page.get("etag"),
                last_checked_at=now_iso,
                last_success_at=state.get("last_success_at"),
            )
            return cached_repos, True

        if first_page and first_page.get("status_code") == 304 and cached_repos and not cached_has_updated_at:
            print("⚠️ ETag 命中但本地快照缺少 updated_at，执行一次全量刷新")
            first_page = self._fetch_page(1, sort_by, if_none_match=None)

        # 3) 304 但本地无今日缓存，强制全量拉取
        if first_page and first_page.get("status_code") == 304 and not cached_repos:
            print("⚠️ ETag 命中但本地无当日数据，执行全量拉取")
            first_page = self._fetch_page(1, sort_by, if_none_match=None)

        # 4) 请求失败时回退本地缓存
        if not first_page:
            if cached_repos:
                print("⚠️ GitHub 请求失败，回退到本地缓存数据")
                return cached_repos, True
            raise RuntimeError("GitHub 请求失败，且本地无可用缓存")

        data = first_page.get("data") or {}
        items = data.get("items") or []
        if first_page.get("status_code") != 200 or not items:
            if cached_repos:
                print("⚠️ GitHub 数据异常，回退到本地缓存数据")
                return cached_repos, True
            raise RuntimeError("GitHub 返回异常数据，且本地无可用缓存")

        repos = []
        for item in items:
            repos.append(self._parse_repo_item(item, len(repos) + 1))
            if len(repos) >= limit:
                break

        page = 2
        while page <= self.max_pages and len(repos) < limit:
            if self.rate_limit_remaining < 10:
                self._wait_for_rate_limit()

            page_result = self._fetch_page(page, sort_by)
            if not page_result:
                break

            page_data = page_result.get("data") or {}
            page_items = page_data.get("items") or []
            if not page_items:
                break

            for item in page_items:
                repos.append(self._parse_repo_item(item, len(repos) + 1))
                if len(repos) >= limit:
                    break

            if len(page_items) < self.per_page:
                break

            page += 1
            if page <= self.max_pages and len(repos) < limit:
                time.sleep(self.delay)

        db.upsert_github_fetch_state(
            request_key=request_key,
            etag=first_page.get("etag"),
            last_checked_at=now_iso,
            last_success_at=now_iso,
        )

        return repos, False

    def _fetch_page(self, page: int, sort_by: str, if_none_match: Optional[str] = None) -> Optional[Dict]:
        """
        获取单页数据

        Args:
            page: 页码
            sort_by: 排序方式

        Returns:
            API 响应数据及元信息
        """
        query = f"topic:{self.topic}"
        url = f"{self.api_base}/search/repositories"

        params = {
            "q": query,
            "sort": sort_by,
            "order": GITHUB_SEARCH_ORDER,
            "per_page": self.per_page,
            "page": page
        }

        headers = {}
        if if_none_match:
            headers["If-None-Match"] = if_none_match

        try:
            response = self._request_with_retry(
                url=url,
                params=params,
                headers=headers,
                context=f"GitHub Search API 第 {page} 页",
            )

            self._update_rate_limit(response.headers)

            if response.status_code == 304:
                return {
                    "status_code": 304,
                    "etag": response.headers.get("ETag"),
                    "data": None,
                }

            response.raise_for_status()
            return {
                "status_code": response.status_code,
                "etag": response.headers.get("ETag"),
                "data": response.json(),
            }

        except requests.RequestException as e:
            print(f"   ⚠️ 请求失败 (页 {page}): {e}")
            return None

    def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        context: str = "GitHub API",
    ) -> requests.Response:
        """执行 GitHub 请求并对 429 进行自动冷却重试"""

        def operation() -> requests.Response:
            response = self.session.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code == 429:
                raise requests.HTTPError(
                    f"429 Too Many Requests: {response.text}",
                    response=response,
                )
            return response

        return execute_with_429_retry(operation, context=context)

    def _parse_repo_item(self, item: Dict, rank: int) -> Dict:
        """
        解析仓库数据

        Args:
            item: GitHub API 返回的仓库项
            rank: 排名

        Returns:
            仓库信息字典
        """
        owner_data = item.get("owner") or {}
        owner = owner_data.get("login", "")
        name = item.get("name", "")
        repo_name = f"{owner}/{name}"

        return {
            "rank": rank,
            "repo_name": repo_name,
            "owner": owner,
            "name": name,
            "stars": item.get("stargazers_count", 0),
            "forks": item.get("forks_count", 0),
            "issues": item.get("open_issues_count", 0),
            "language": item.get("language", ""),
            "url": item.get("html_url", ""),
            "description": item.get("description", ""),
            "topics": item.get("topics", []),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "pushed_at": item.get("pushed_at", ""),
            "homepage": item.get("homepage", ""),
            "archived": item.get("archived", False),
        }

    def _update_rate_limit(self, headers: Mapping[str, str]):
        """
        更新速率限制信息

        Args:
            headers: API 响应头
        """
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")

        if remaining is not None:
            try:
                self.rate_limit_remaining = int(remaining)
            except ValueError:
                pass

        if reset is not None:
            try:
                self.rate_limit_reset = int(reset)
            except ValueError:
                pass

    def _wait_for_rate_limit(self):
        """等待速率限制重置"""
        if self.rate_limit_reset:
            now = int(time.time())
            wait_time = self.rate_limit_reset - now + 1

            if wait_time > 0:
                print(f"⏳ 速率限制已用尽，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

    def fetch_new_repos(self, days: int = 7) -> List[Dict]:
        """
        获取最近创建的仓库

        Args:
            days: 最近多少天

        Returns:
            仓库列表
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"topic:{self.topic} created:>{cutoff_date}"

        print(f"📡 正在获取最近 {days} 天创建的仓库...")

        repos = []
        page = 1

        while page <= self.max_pages:
            url = f"{self.api_base}/search/repositories"
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": self.per_page,
                "page": page
            }

            try:
                response = self._request_with_retry(
                    url=url,
                    params=params,
                    context=f"GitHub 新仓库搜索 第 {page} 页",
                )
                self._update_rate_limit(response.headers)
                response.raise_for_status()
                data = response.json()

                if not data or "items" not in data:
                    break

                items = data["items"]
                if not items:
                    break

                for item in items:
                    repo = self._parse_repo_item(item, len(repos) + 1)
                    repos.append(repo)

                print(f"   第 {page} 页: 获取 {len(items)} 个仓库")

                if len(items) < self.per_page:
                    break

                page += 1
                time.sleep(self.delay)

            except requests.RequestException as e:
                print(f"   ⚠️ 请求失败: {e}")
                break

        print(f"✅ 获取到 {len(repos)} 个新仓库")
        return repos

    def fetch_repo_details(self, owner: str, repo: str) -> Optional[Dict]:
        """
        获取单个仓库的详细信息

        Args:
            owner: 仓库拥有者
            repo: 仓库名称

        Returns:
            仓库详细信息
        """
        url = f"{self.api_base}/repos/{owner}/{repo}"

        try:
            response = self._request_with_retry(
                url=url,
                context=f"GitHub 仓库详情 {owner}/{repo}",
            )
            self._update_rate_limit(response.headers)
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"   ⚠️ 获取仓库详情失败 {owner}/{repo}: {e}")
            return None

    def fetch_single_repository(self, repo_identifier: str, rank: int = 1) -> Optional[Dict]:
        """获取并标准化单仓库数据（兼容 pipeline RepoData 结构）。"""
        normalized = (repo_identifier or "").strip()
        if not normalized or "/" not in normalized:
            return None

        owner, repo = normalized.split("/", 1)
        owner = owner.strip()
        repo = repo.strip()
        if not owner or not repo:
            return None

        print(f"📡 正在获取目标仓库 '{owner}/{repo}' ...")
        detail = self.fetch_repo_details(owner, repo)
        if not detail:
            return None

        return self._parse_repo_item(detail, rank=rank)

    def _build_request_key(self, sort_by: str, limit: int) -> str:
        """构建抓取状态缓存键"""
        return (
            f"topic={self.topic}|sort={sort_by}|order={GITHUB_SEARCH_ORDER}|"
            f"per_page={self.per_page}|limit={limit}"
        )

    @staticmethod
    def _repos_have_updated_at(repos: List[Dict]) -> bool:
        """判断缓存仓库快照是否包含可用的 updated_at 字段"""
        if not repos:
            return False
        return all(bool(repo.get("updated_at")) for repo in repos)

    @staticmethod
    def _is_within_cache_window(last_checked_at: Optional[str], cache_minutes: int) -> bool:
        """判断是否在缓存周期内"""
        if not last_checked_at:
            return False

        try:
            checked_time = datetime.fromisoformat(last_checked_at)
            if checked_time.tzinfo is None:
                checked_time = checked_time.replace(tzinfo=timezone.utc)
        except ValueError:
            return False

        age = datetime.now(timezone.utc) - checked_time
        return age < timedelta(minutes=cache_minutes)


def fetch_repos(sort_by: str = "stars", limit: int = 100) -> List[Dict]:
    """便捷函数：获取仓库列表"""
    fetcher = GitHubFetcher()
    return fetcher.fetch(sort_by=sort_by, limit=limit)
