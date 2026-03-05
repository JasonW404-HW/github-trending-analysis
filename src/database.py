"""
SQLite 数据库操作模块
管理 GitHub 仓库趋势数据的存储和查询
"""
import os
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.config import DB_PATH, DB_RETENTION_DAYS


class Database:
    """SQLite 数据库操作类"""

    def __init__(self, db_path: str = None):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        self.db_path = db_path or DB_PATH
        self._ensure_db_dir()
        self.conn = None

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def connect(self):
        """建立数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 返回字典格式

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _table_columns(self, table_name: str) -> List[str]:
        """获取表字段列表"""
        self.connect()
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [row["name"] for row in cursor.fetchall()]

    def _ensure_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """确保表存在指定字段（用于轻量 schema 迁移）"""
        columns = self._table_columns(table_name)
        if column_name in columns:
            return

        cursor = self.conn.cursor()
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        self.conn.commit()
        print(f"🔧 数据库迁移: {table_name} 新增字段 {column_name}")

    def init_db(self) -> None:
        """初始化数据库表"""
        self.connect()
        cursor = self.conn.cursor()

        # 1. repos_daily - 每日快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repos_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                rank INTEGER NOT NULL,
                repo_name TEXT NOT NULL,
                owner TEXT NOT NULL,
                stars INTEGER NOT NULL,
                stars_delta INTEGER DEFAULT 0,
                forks INTEGER,
                issues INTEGER,
                language TEXT,
                url TEXT,
                repo_updated_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, repo_name)
            )
        """)

        # 2. repos_details - 仓库详情缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repos_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT UNIQUE NOT NULL,
                summary TEXT NOT NULL,
                description TEXT,
                use_case TEXT,
                solves TEXT,
                tags TEXT,
                purpose_assessment TEXT,
                category TEXT NOT NULL,
                category_zh TEXT NOT NULL,
                topics TEXT,
                language TEXT,
                readme_summary TEXT,
                owner TEXT NOT NULL,
                url TEXT NOT NULL,
                repo_updated_at TEXT,
                prompt_hash TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. repos_history - 历史趋势表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repos_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                date TEXT NOT NULL,
                rank INTEGER NOT NULL,
                stars INTEGER NOT NULL,
                forks INTEGER,
                UNIQUE(repo_name, date)
            )
        """)

        # 4. github_fetch_state - GitHub 抓取状态缓存
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS github_fetch_state (
                request_key TEXT PRIMARY KEY,
                etag TEXT,
                last_checked_at TEXT,
                last_success_at TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 兼容旧库：补充新增字段
        self._ensure_column("repos_daily", "repo_updated_at", "TEXT")
        self._ensure_column("repos_details", "repo_updated_at", "TEXT")
        self._ensure_column("repos_details", "tags", "TEXT")
        self._ensure_column("repos_details", "prompt_hash", "TEXT")
        self._ensure_column("repos_details", "purpose_assessment", "TEXT")

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON repos_daily(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_repo ON repos_daily(repo_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_rank ON repos_daily(date, rank)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_details_category ON repos_details(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_details_owner ON repos_details(owner)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_details_language ON repos_details(language)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_repo ON repos_history(repo_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_date ON repos_history(date)")

        self.conn.commit()
        print(f"✅ 数据库初始化完成: {self.db_path}")

    def save_today_data(self, date: str, repos: List[Dict]) -> None:
        """
        保存今日数据

        Args:
            date: 日期 YYYY-MM-DD
            repos: 仓库列表
        """
        self.connect()
        cursor = self.conn.cursor()

        for repo in repos:
            cursor.execute("""
                INSERT OR REPLACE INTO repos_daily
                (date, rank, repo_name, owner, stars, stars_delta, forks, issues, language, url, repo_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                repo.get("rank"),
                repo.get("repo_name"),
                repo.get("owner"),
                repo.get("stars"),
                repo.get("stars_delta", 0),
                repo.get("forks"),
                repo.get("issues"),
                repo.get("language"),
                repo.get("url", ""),
                repo.get("updated_at", "")
            ))

            # 同时写入历史表
            cursor.execute("""
                INSERT OR REPLACE INTO repos_history
                (repo_name, date, rank, stars, forks)
                VALUES (?, ?, ?, ?, ?)
            """, (
                repo.get("repo_name"),
                date,
                repo.get("rank"),
                repo.get("stars"),
                repo.get("forks")
            ))

        self.conn.commit()
        print(f"✅ 保存今日数据: {len(repos)} 条记录")

    def get_repos_by_date(self, date: str) -> List[Dict]:
        """
        获取指定日期的数据

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            仓库列表
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT rank, repo_name, owner, stars, stars_delta, forks, issues, language, url,
                   repo_updated_at AS updated_at
            FROM repos_daily
            WHERE date = ?
            ORDER BY rank
        """, (date,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_yesterday_data(self, date: str) -> List[Dict]:
        """
        获取昨日数据

        Args:
            date: 当前日期 YYYY-MM-DD

        Returns:
            昨日的仓库列表
        """
        yesterday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.get_repos_by_date(yesterday)

    def save_repo_details(self, details: List[Dict], verbose: bool = True) -> None:
        """
        保存/更新仓库详情

        Args:
            details: AI 分析的仓库详情列表
        """
        if not details:
            return

        self.connect()
        cursor = self.conn.cursor()

        for detail in details:
            solves_json = json.dumps(detail.get("solves", []), ensure_ascii=False)
            tags_json = json.dumps(detail.get("tags", []), ensure_ascii=False)
            topics_json = json.dumps(detail.get("topics", []), ensure_ascii=False)
            purpose_assessment_json = json.dumps(detail.get("purpose_assessment", {}), ensure_ascii=False)

            cursor.execute("""
                INSERT OR REPLACE INTO repos_details
                (repo_name, summary, description, use_case, solves, tags, category, category_zh,
                 purpose_assessment, topics, language, readme_summary, owner, url, repo_updated_at, prompt_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                detail.get("repo_name"),
                detail.get("summary"),
                detail.get("description"),
                detail.get("use_case"),
                solves_json,
                tags_json,
                detail.get("category"),
                detail.get("category_zh"),
                purpose_assessment_json,
                topics_json,
                detail.get("language"),
                detail.get("readme_summary"),
                detail.get("owner"),
                detail.get("url"),
                detail.get("repo_updated_at"),
                detail.get("prompt_hash", "")
            ))

        self.conn.commit()
        if verbose:
            print(f"✅ 保存仓库详情: {len(details)} 条记录")

    def save_repo_detail(self, detail: Dict, verbose: bool = False) -> None:
        """保存单条仓库详情（用于每次成功请求及时落库）"""
        self.save_repo_details([detail], verbose=verbose)

    def get_repo_details(self, repo_name: str) -> Optional[Dict]:
        """
        获取仓库详情

        Args:
            repo_name: 仓库全名 (owner/repo)

        Returns:
            仓库详情字典，如果不存在返回 None
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
               SELECT repo_name, summary, description, use_case, solves, tags, category, category_zh,
                 purpose_assessment, topics, language, readme_summary, owner, url, repo_updated_at, prompt_hash
            FROM repos_details
            WHERE repo_name = ?
        """, (repo_name,))

        row = cursor.fetchone()
        if row:
            result = dict(row)
            # 解析 JSON 字段
            if result.get("solves"):
                result["solves"] = json.loads(result["solves"])
            if result.get("tags"):
                result["tags"] = json.loads(result["tags"])
            if result.get("purpose_assessment"):
                result["purpose_assessment"] = json.loads(result["purpose_assessment"])
            if result.get("topics"):
                result["topics"] = json.loads(result["topics"])
            return result
        return None

    def get_all_repo_details(self) -> Dict[str, Dict]:
        """
        获取所有仓库详情

        Returns:
            {repo_name: detail_dict} 的字典
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
               SELECT repo_name, summary, description, use_case, solves, tags, category, category_zh,
                 purpose_assessment, topics, language, readme_summary, owner, url, repo_updated_at, prompt_hash
            FROM repos_details
        """)

        result = {}
        for row in cursor.fetchall():
            detail = dict(row)
            if detail.get("solves"):
                detail["solves"] = json.loads(detail["solves"])
            if detail.get("tags"):
                detail["tags"] = json.loads(detail["tags"])
            if detail.get("purpose_assessment"):
                detail["purpose_assessment"] = json.loads(detail["purpose_assessment"])
            if detail.get("topics"):
                detail["topics"] = json.loads(detail["topics"])
            result[detail["repo_name"]] = detail

        return result

    def get_repo_details_if_fresh(
        self,
        repo_name: str,
        repo_updated_at: str,
        prompt_hash: str = "",
    ) -> Optional[Dict]:
        """
        获取指定仓库的最新分析结果（按 repo_name + repo_updated_at + prompt_hash 匹配）
        """
        if not repo_updated_at:
            return None

        detail = self.get_repo_details(repo_name)
        if not detail:
            return None

        if detail.get("repo_updated_at") != repo_updated_at:
            return None

        if prompt_hash and detail.get("prompt_hash", "") != prompt_hash:
            return None

        if detail.get("repo_updated_at") == repo_updated_at:
            return detail

        return None

    def get_github_fetch_state(self, request_key: str) -> Optional[Dict]:
        """获取 GitHub 抓取状态"""
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT request_key, etag, last_checked_at, last_success_at, updated_at
            FROM github_fetch_state
            WHERE request_key = ?
        """, (request_key,))

        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_github_fetch_state(
        self,
        request_key: str,
        etag: Optional[str],
        last_checked_at: Optional[str],
        last_success_at: Optional[str],
    ) -> None:
        """写入/更新 GitHub 抓取状态"""
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO github_fetch_state
            (request_key, etag, last_checked_at, last_success_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(request_key) DO UPDATE SET
                etag = excluded.etag,
                last_checked_at = excluded.last_checked_at,
                last_success_at = COALESCE(excluded.last_success_at, github_fetch_state.last_success_at),
                updated_at = CURRENT_TIMESTAMP
        """, (request_key, etag, last_checked_at, last_success_at))

        self.conn.commit()

    def cleanup_old_data(self, days: int = None) -> int:
        """
        清理过期数据

        Args:
            days: 保留天数，默认使用配置中的值

        Returns:
            删除的记录数
        """
        retention_days = days or DB_RETENTION_DAYS
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")

        self.connect()
        cursor = self.conn.cursor()

        # 清理每日快照
        cursor.execute("""
            DELETE FROM repos_daily
            WHERE date < ?
        """, (cutoff_date,))

        deleted_daily = cursor.rowcount

        # 清理历史数据
        cursor.execute("""
            DELETE FROM repos_history
            WHERE date < ?
        """, (cutoff_date,))

        deleted_history = cursor.rowcount

        self.conn.commit()
        total_deleted = deleted_daily + deleted_history

        if total_deleted > 0:
            print(f"🗑️ 清理过期数据: {total_deleted} 条记录 (早于 {cutoff_date})")

        return total_deleted

    def get_repo_history(self, repo_name: str, days: int = 30) -> List[Dict]:
        """
        获取仓库历史趋势

        Args:
            repo_name: 仓库全名
            days: 查询天数

        Returns:
            历史数据列表，按日期升序排列
        """
        self.connect()
        cursor = self.conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT date, rank, stars, forks
            FROM repos_history
            WHERE repo_name = ? AND date >= ?
            ORDER BY date ASC
        """, (repo_name, cutoff_date))

        return [dict(row) for row in cursor.fetchall()]

    def get_available_dates(self, limit: int = 30) -> List[str]:
        """
        获取可用的日期列表

        Args:
            limit: 返回的最大日期数

        Returns:
            日期列表，按降序排列（最新的在前）
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT DISTINCT date
            FROM repos_daily
            ORDER BY date DESC
            LIMIT ?
        """, (limit,))

        return [row["date"] for row in cursor.fetchall()]

    def get_category_stats(self, date: str) -> List[Dict]:
        """
        获取指定日期的分类统计

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            分类统计列表
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT d.category, d.category_zh, COUNT(*) as count
            FROM repos_daily r
            LEFT JOIN repos_details d ON r.repo_name = d.repo_name
            WHERE r.date = ?
            GROUP BY d.category
            ORDER BY count DESC
        """, (date,))

        return [dict(row) for row in cursor.fetchall()]

    def get_repos_by_category(self, category: str, limit: int = 50) -> List[Dict]:
        """
        获取指定分类的仓库

        Args:
            category: 分类名称
            limit: 返回数量

        Returns:
            仓库列表
        """
        self.connect()
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT r.repo_name, r.owner, r.stars, r.forks, r.language, r.url,
                   d.summary, d.description, d.category, d.category_zh
            FROM repos_details d
            JOIN repos_daily r ON d.repo_name = r.repo_name
            WHERE d.category = ?
            ORDER BY r.stars DESC
            LIMIT ?
        """, (category, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_top_movers(self, date: str, limit: int = 5) -> Dict[str, List[Dict]]:
        """
        获取排名变化最大的仓库

        Args:
            date: 日期 YYYY-MM-DD
            limit: 返回数量

        Returns:
            {"rising": [...], "falling": [...]}
        """
        self.connect()
        cursor = self.conn.cursor()

        # 上升最多
        cursor.execute("""
            SELECT r.repo_name, r.rank, r.stars_delta, d.summary, d.category
            FROM repos_daily r
            LEFT JOIN repos_details d ON r.repo_name = d.repo_name
            WHERE r.date = ? AND r.stars_delta > 0
            ORDER BY r.stars_delta DESC, r.rank ASC
            LIMIT ?
        """, (date, limit))

        rising = [dict(row) for row in cursor.fetchall()]

        # 下降最多
        cursor.execute("""
            SELECT r.repo_name, r.rank, r.stars_delta, d.summary, d.category
            FROM repos_daily r
            LEFT JOIN repos_details d ON r.repo_name = d.repo_name
            WHERE r.date = ? AND r.stars_delta < 0
            ORDER BY r.stars_delta ASC, r.rank ASC
            LIMIT ?
        """, (date, limit))

        falling = [dict(row) for row in cursor.fetchall()]

        return {"rising": rising, "falling": falling}

    def get_language_stats(self, date: str = None, limit: int = 20) -> List[Dict]:
        """
        获取语言统计

        Args:
            date: 日期 YYYY-MM-DD，None 表示使用最新数据
            limit: 返回数量

        Returns:
            语言统计列表
        """
        self.connect()
        cursor = self.conn.cursor()

        if date:
            cursor.execute("""
                SELECT language, COUNT(*) as count, AVG(stars) as avg_stars
                FROM repos_daily
                WHERE date = ? AND language IS NOT NULL AND language != ''
                GROUP BY language
                ORDER BY count DESC
                LIMIT ?
            """, (date, limit))
        else:
            cursor.execute("""
                SELECT language, COUNT(*) as count, AVG(stars) as avg_stars
                FROM repos_details
                WHERE language IS NOT NULL AND language != ''
                GROUP BY language
                ORDER BY count DESC
                LIMIT ?
            """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _safe_parse_json_text(value: Optional[str], default: Any) -> Any:
        """安全解析 JSON 字符串"""
        if not value:
            return default

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    def get_opportunity_report(
        self,
        date: str,
        min_level: str = "strong",
        limit: int = 50,
    ) -> Dict:
        """
        获取目标机会报表（用于运营复盘）

        Args:
            date: 日期 YYYY-MM-DD
            min_level: 商业价值阈值 strong/weak
            limit: 返回项目上限

        Returns:
            结构化机会报表
        """
        threshold = (min_level or "strong").lower().strip()
        if threshold not in {"strong", "weak"}:
            threshold = "strong"

        allowed_levels = {"strong"} if threshold == "strong" else {"strong", "weak"}

        self.connect()
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT r.rank, r.repo_name, r.owner, r.stars, r.stars_delta, r.language, r.url,
                 d.summary, d.description, d.use_case, d.tags, d.purpose_assessment
            FROM repos_daily r
            LEFT JOIN repos_details d ON r.repo_name = d.repo_name
            WHERE r.date = ?
            ORDER BY r.rank ASC
            """,
            (date,),
        )

        rows = [dict(row) for row in cursor.fetchall()]
        projects: List[Dict] = []
        strong_count = 0
        weak_count = 0

        for row in rows:
            purpose = self._safe_parse_json_text(row.get("purpose_assessment"), default={})
            if not isinstance(purpose, dict):
                purpose = {}

            commercial_level = str(purpose.get("commercial_value_level", "none")).lower()
            recommended = bool(purpose.get("recommended_for_push", False))

            if not recommended or commercial_level not in allowed_levels:
                continue

            if commercial_level == "strong":
                strong_count += 1
            elif commercial_level == "weak":
                weak_count += 1

            tags = self._safe_parse_json_text(row.get("tags"), default=[])
            if not isinstance(tags, list):
                tags = []

            projects.append(
                {
                    "rank": row.get("rank"),
                    "repo_name": row.get("repo_name"),
                    "owner": row.get("owner"),
                    "stars": row.get("stars", 0),
                    "stars_delta": row.get("stars_delta", 0),
                    "language": row.get("language", ""),
                    "url": row.get("url", ""),
                    "summary": row.get("summary", ""),
                    "description": row.get("description", ""),
                    "use_case": row.get("use_case", ""),
                    "tags": tags,
                    "domain": purpose.get("domain", ""),
                    "domain_barrier_level": purpose.get("domain_barrier_level", ""),
                    "domain_barrier_reason": purpose.get("domain_barrier_reason", ""),
                    "maturity_level": purpose.get("maturity_level", ""),
                    "is_model_service_project": bool(purpose.get("is_model_service_project", False)),
                    "model_service_focus": purpose.get("model_service_focus", ""),
                    "commercial_value_level": commercial_level,
                    "commercial_value_reason": purpose.get("commercial_value_reason", ""),
                    "recommended_for_push": recommended,
                    "private_deploy_fit": purpose.get("private_deploy_fit", ""),
                    "implemented_features": purpose.get("implemented_features", []) or [],
                    "current_issues": purpose.get("current_issues", []) or [],
                    "roadmap_signals": purpose.get("roadmap_signals", []) or [],
                    "future_directions": purpose.get("future_directions", []) or [],
                    "infra_transformation_opportunities": purpose.get("infra_transformation_opportunities", []) or [],
                }
            )

        limited_projects = projects[: max(1, limit)]

        return {
            "date": date,
            "min_level": threshold,
            "total_scanned": len(rows),
            "total_candidates": len(projects),
            "strong_count": strong_count,
            "weak_count": weak_count,
            "projects": limited_projects,
        }


def get_database() -> Database:
    """获取数据库实例（便捷函数）"""
    return Database()
