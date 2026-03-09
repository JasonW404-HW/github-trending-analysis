"""
Trend Analyzer - 趋势计算引擎
计算仓库的排名变化、星标变化、新晋/掉榜等趋势
"""
from typing import Dict, List
from datetime import datetime, timedelta

from src.infrastructure.database import Database
from src.config import SURGE_THRESHOLD


class TrendAnalyzer:
    """趋势计算引擎"""

    def __init__(self, db: Database):
        """
        初始化

        Args:
            db: 数据库实例
        """
        self.db = db

    def calculate_trends(self, today_data: List[Dict], date: str, ai_summaries: Dict = None) -> Dict:
        """
        计算今日趋势

        Args:
            today_data: 今日仓库列表
            date: 今日日期 YYYY-MM-DD
            ai_summaries: AI 分析的仓库详情 {repo_name: detail}

        Returns:
            {
                "date": "2026-01-27",
                "top_20": [...],           # Top 20 (带 AI 总结)
                "rising_top5": [...],      # 星标增长 Top 5
                "falling_top5": [...],     # 星标下降 Top 5
                "new_entries": [...],      # 新晋榜单
                "dropped_entries": [...],  # 跌出榜单
                "surging": [],             # 星标暴涨 (>30%)
                "active": []               # 活跃项目
            }
        """
        # 获取昨日数据
        yesterday_data = self.db.get_yesterday_data(date)

        # 构建昨日数据的映射
        yesterday_map = {r["repo_name"]: r for r in yesterday_data} if yesterday_data else {}

        # 计算变化
        today_with_delta = self._calculate_deltas(today_data, yesterday_map)

        # 保存今日数据（包含变化值）
        self.db.save_today_data(date, today_with_delta)

        # 获取 AI 摘要
        if ai_summaries is None:
            ai_summaries = self.db.get_all_repo_details()

        # 找出各种趋势
        results = {
            "date": date,
            "top_20": self._get_top_20_with_summary(today_with_delta, ai_summaries),
            "rising_top5": self._get_top_movers(today_with_delta, direction="up", limit=5, ai_summaries=ai_summaries),
            "falling_top5": self._get_top_movers(today_with_delta, direction="down", limit=5, ai_summaries=ai_summaries),
            "new_entries": self._find_new_entries(today_with_delta, yesterday_map, ai_summaries),
            "dropped_entries": self._find_dropped_entries(today_with_delta, yesterday_map, ai_summaries),
            "surging": self._find_surging_repos(today_with_delta, ai_summaries),
            "active": self._find_active_repos(today_with_delta, ai_summaries)
        }

        return results

    def _calculate_deltas(self, today: List[Dict], yesterday_map: Dict[str, Dict]) -> List[Dict]:
        """
        计算排名和星标变化

        Args:
            today: 今日仓库列表
            yesterday_map: 昨日仓库映射 {repo_name: repo}

        Returns:
            包含变化值的仓库列表
        """
        for repo in today:
            repo_name = repo["repo_name"]

            if repo_name in yesterday_map:
                yesterday_repo = yesterday_map[repo_name]

                # 排名变化（昨日排名 - 今日排名，正数=上升）
                yesterday_rank = yesterday_repo.get("rank", repo["rank"])
                repo["rank_delta"] = yesterday_rank - repo["rank"]

                # 星标变化
                yesterday_stars = yesterday_repo.get("stars", repo["stars"])
                stars_delta = repo["stars"] - yesterday_stars
                repo["stars_delta"] = stars_delta

                # 星标变化率
                if yesterday_stars > 0:
                    repo["stars_rate"] = round(stars_delta / yesterday_stars, 4)
                else:
                    repo["stars_rate"] = 0
            else:
                # 新仓库，没有历史数据
                repo["rank_delta"] = 0
                repo["stars_delta"] = 0
                repo["stars_rate"] = 0

        return today

    def _get_top_20_with_summary(self, today: List[Dict], ai_summaries: Dict) -> List[Dict]:
        """
        获取 Top 20 并附加 AI 摘要

        Args:
            today: 今日仓库列表
            ai_summaries: AI 摘要映射

        Returns:
            Top 20 仓库列表（带 AI 摘要）
        """
        top_20 = today[:20]

        for repo in top_20:
            repo_name = repo["repo_name"]
            if repo_name in ai_summaries:
                summary = ai_summaries[repo_name]
                repo["summary"] = summary.get("summary", "")
                repo["description"] = summary.get("description", "")
                repo["use_case"] = summary.get("use_case", "")
                repo["solves"] = summary.get("solves", [])
                repo["tags"] = summary.get("tags") or []
                repo["purpose_assessment"] = summary.get("purpose_assessment", {}) or {}
                repo["category"] = summary.get("category", "")
                repo["category_zh"] = summary.get("category_zh", "")
            else:
                repo["summary"] = ""
                repo["description"] = ""
                repo["use_case"] = ""
                repo["solves"] = []
                repo["tags"] = []
                repo["purpose_assessment"] = {}
                repo["category"] = ""
                repo["category_zh"] = ""

        return top_20

    def _get_top_movers(self, today: List[Dict], direction: str = "up", limit: int = 5, ai_summaries: Dict = None) -> List[Dict]:
        """
        获取星标变化最大的仓库

        Args:
            today: 今日仓库列表
            direction: "up"=增长, "down"=下降
            limit: 返回数量
            ai_summaries: AI 摘要映射

        Returns:
            仓库列表
        """
        # 过滤有变化的仓库
        if direction == "up":
            movers = [r for r in today if r.get("stars_delta", 0) > 0]
            movers.sort(key=lambda x: x["stars_delta"], reverse=True)
        else:
            movers = [r for r in today if r.get("stars_delta", 0) < 0]
            movers.sort(key=lambda x: x["stars_delta"])

        # 取前 N 个
        result = movers[:limit]

        # 附加 AI 摘要
        if ai_summaries:
            for repo in result:
                repo_name = repo["repo_name"]
                if repo_name in ai_summaries:
                    summary = ai_summaries[repo_name]
                    repo["summary"] = summary.get("summary", "")
                    repo["tags"] = summary.get("tags") or []
                    repo["purpose_assessment"] = summary.get("purpose_assessment", {}) or {}
                    repo["category_zh"] = summary.get("category_zh", "")

        return result

    def _find_new_entries(self, today: List[Dict], yesterday_map: Dict[str, Dict], ai_summaries: Dict = None) -> List[Dict]:
        """
        找出新晋榜单的仓库

        Args:
            today: 今日仓库列表
            yesterday_map: 昨日仓库映射
            ai_summaries: AI 摘要映射

        Returns:
            新晋仓库列表
        """
        new_entries = [r for r in today if r["repo_name"] not in yesterday_map]

        # 附加 AI 摘要
        if ai_summaries:
            for repo in new_entries:
                repo_name = repo["repo_name"]
                if repo_name in ai_summaries:
                    summary = ai_summaries[repo_name]
                    repo["summary"] = summary.get("summary", "")
                    repo["tags"] = summary.get("tags") or []
                    repo["purpose_assessment"] = summary.get("purpose_assessment", {}) or {}
                    repo["category_zh"] = summary.get("category_zh", "")

        return new_entries

    def _find_dropped_entries(self, today: List[Dict], yesterday_map: Dict[str, Dict], ai_summaries: Dict = None) -> List[Dict]:
        """
        找出跌出榜单的仓库

        Args:
            today: 今日仓库列表
            yesterday_map: 昨日仓库映射
            ai_summaries: AI 摘要映射

        Returns:
            跌出榜单的仓库列表
        """
        today_names = {r["repo_name"] for r in today}
        dropped = []

        for repo_name, yesterday_repo in yesterday_map.items():
            if repo_name not in today_names:
                dropped.append({
                    "repo_name": repo_name,
                    "yesterday_rank": yesterday_repo.get("rank"),
                    "stars": yesterday_repo.get("stars", 0),
                    "url": yesterday_repo.get("url", "")
                })

                # 尝试附加 AI 摘要
                if ai_summaries and repo_name in ai_summaries:
                    summary = ai_summaries[repo_name]
                    dropped[-1]["summary"] = summary.get("summary", "")
                    dropped[-1]["tags"] = summary.get("tags") or []
                    dropped[-1]["purpose_assessment"] = summary.get("purpose_assessment", {}) or {}
                    dropped[-1]["category_zh"] = summary.get("category_zh", "")

        return dropped

    def _find_surging_repos(self, today: List[Dict], ai_summaries: Dict = None) -> List[Dict]:
        """
        找出星标暴涨的仓库

        Args:
            today: 今日仓库列表
            ai_summaries: AI 摘要映射

        Returns:
            暴涨仓库列表
        """
        surging = []

        for repo in today:
            rate = repo.get("stars_rate", 0)
            delta = repo.get("stars_delta", 0)
            # 暴涨定义: 变化率超过阈值 或 增长超过 100
            if rate >= SURGE_THRESHOLD or delta >= 100:
                surging.append(repo)

        # 附加 AI 摘要
        if ai_summaries:
            for repo in surging:
                repo_name = repo["repo_name"]
                if repo_name in ai_summaries:
                    summary = ai_summaries[repo_name]
                    repo["summary"] = summary.get("summary", "")
                    repo["tags"] = summary.get("tags") or []
                    repo["purpose_assessment"] = summary.get("purpose_assessment", {}) or {}
                    repo["category_zh"] = summary.get("category_zh", "")

        return surging

    def _find_active_repos(self, today: List[Dict], ai_summaries: Dict = None) -> List[Dict]:
        """
        找出活跃的仓库（最近更新）

        Args:
            today: 今日仓库列表
            ai_summaries: AI 摘要映射

        Returns:
            活跃仓库列表
        """
        # 按更新时间排序
        active = sorted(
            [r for r in today if r.get("updated_at")],
            key=lambda x: x["updated_at"],
            reverse=True
        )[:10]

        # 附加 AI 摘要
        if ai_summaries:
            for repo in active:
                repo_name = repo["repo_name"]
                if repo_name in ai_summaries:
                    summary = ai_summaries[repo_name]
                    repo["summary"] = summary.get("summary", "")
                    repo["tags"] = summary.get("tags") or []
                    repo["purpose_assessment"] = summary.get("purpose_assessment", {}) or {}
                    repo["category_zh"] = summary.get("category_zh", "")

        return active

    def get_category_summary(self, date: str) -> Dict:
        """
        获取分类汇总

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            分类汇总数据
        """
        stats = self.db.get_category_stats(date)
        return {
            "date": date,
            "categories": [
                {
                    "category": s["category"],
                    "category_zh": s["category_zh"],
                    "count": s["count"]
                }
                for s in stats
            ]
        }


def analyze_trends(today_data: List[Dict], date: str, db: Database = None, ai_summaries: Dict = None) -> Dict:
    """便捷函数：分析趋势"""
    if db is None:
        db = Database()
        db.connect()

    analyzer = TrendAnalyzer(db)
    return analyzer.calculate_trends(today_data, date, ai_summaries)
