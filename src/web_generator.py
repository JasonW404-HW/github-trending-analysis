"""
Web Generator - GitHub Pages 静态网站生成器
生成 GitHub Topics Trending 的静态网站页面
"""
import csv
import os
import json
from datetime import datetime
from typing import Dict, List
from pathlib import Path
from urllib.parse import urlparse

from src.config import (
    CATEGORIES,
    GITHUB_PAGES_URL,
    OUTPUT_DIR,
    PUSH_MIN_COMMERCIAL_LEVEL,
    SITE_META,
    TOPIC,
    format_number,
    get_theme,
)
from src.util.print_util import logger


class WebGenerator:
    """GitHub Pages 静态网站生成器"""

    def __init__(self, output_dir: str = None, theme: str = "blue"):
        """
        初始化

        Args:
            output_dir: 输出目录
            theme: 主题名称
        """
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.theme = get_theme(theme)
        self.topic = TOPIC
        self.meta = SITE_META
        self.base_path = self._resolve_base_path()

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        (self.output_dir / "trending").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "category").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "repo").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "exports").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "assets" / "css").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "assets" / "js").mkdir(parents=True, exist_ok=True)

    def generate_all(self, trends: Dict, date: str, db) -> List[str]:
        """
        生成所有页面

        Args:
            trends: 趋势数据
            date: 日期
            db: 数据库实例

        Returns:
            生成的文件路径列表
        """
        if self.base_path:
            logger.info(f"🌐 GitHub Pages Base Path: {self.base_path}")
        else:
            logger.info("🌐 GitHub Pages Base Path: /")

        files = []

        # 目标机会报表与导出文件
        opportunity_report = db.get_opportunity_report(
            date=date,
            min_level=PUSH_MIN_COMMERCIAL_LEVEL,
            limit=200,
        )
        export_files = self.generate_opportunity_exports(opportunity_report, date)
        files.extend(export_files.values())

        # 首页
        index_path = self.generate_index(
            trends=trends,
            date=date,
            opportunity_report=opportunity_report,
            export_files=export_files,
        )
        files.append(index_path)

        # 趋势页
        trending_path = self.generate_trending_page(
            trends=trends,
            date=date,
            opportunity_report=opportunity_report,
            export_files=export_files,
        )
        files.append(trending_path)

        # 分类页
        category_files = self.generate_category_pages(db)
        files.extend(category_files)

        # 静态资源
        css_path = self.generate_css()
        files.append(css_path)

        logger.info(f"✅ 生成网站文件: {len(files)} 个")

        return files

    def generate_opportunity_exports(self, report: Dict, date: str) -> Dict[str, str]:
        """生成目标机会导出文件（JSON/CSV/Markdown）"""
        export_dir = self.output_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        projects = report.get("projects", []) or []
        date_name = f"opportunity-report-{date}"

        json_path = export_dir / f"{date_name}.json"
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        csv_path = export_dir / f"{date_name}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow([
                "rank",
                "repo_name",
                "stars",
                "language",
                "domain",
                "domain_barrier_level",
                "maturity_level",
                "commercial_value_level",
                "private_deploy_fit",
                "summary",
                "commercial_value_reason",
                "infra_transformation_opportunities",
                "implemented_features",
                "current_issues",
                "roadmap_signals",
                "future_directions",
                "tags",
                "url",
            ])

            for project in projects:
                writer.writerow([
                    project.get("rank", ""),
                    project.get("repo_name", ""),
                    project.get("stars", 0),
                    project.get("language", ""),
                    project.get("domain", ""),
                    project.get("domain_barrier_level", ""),
                    project.get("maturity_level", ""),
                    project.get("commercial_value_level", "none"),
                    project.get("private_deploy_fit", ""),
                    project.get("summary", ""),
                    project.get("commercial_value_reason", ""),
                    " | ".join(project.get("infra_transformation_opportunities", []) or []),
                    " | ".join(project.get("implemented_features", []) or []),
                    " | ".join(project.get("current_issues", []) or []),
                    " | ".join(project.get("roadmap_signals", []) or []),
                    " | ".join(project.get("future_directions", []) or []),
                    " | ".join(project.get("tags", []) or []),
                    project.get("url", ""),
                ])

        markdown_path = export_dir / f"{date_name}.md"
        markdown_path.write_text(
            self._build_opportunity_markdown(report),
            encoding="utf-8",
        )

        latest_json = export_dir / "opportunity-report-latest.json"
        latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

        latest_csv = export_dir / "opportunity-report-latest.csv"
        latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")

        latest_md = export_dir / "opportunity-report-latest.md"
        latest_md.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")

        return {
            "json": str(json_path),
            "csv": str(csv_path),
            "md": str(markdown_path),
            "json_latest": str(latest_json),
            "csv_latest": str(latest_csv),
            "md_latest": str(latest_md),
        }

    def _build_opportunity_markdown(self, report: Dict) -> str:
        """构建机会报表 Markdown 内容"""
        projects = report.get("projects", []) or []
        lines: List[str] = [
            f"# 目标机会报表 - {report.get('date', '')}",
            "",
            f"- 商业价值阈值: `{report.get('min_level', 'strong')}`",
            f"- 扫描项目数: `{report.get('total_scanned', 0)}`",
            f"- 候选项目数: `{report.get('total_candidates', 0)}`",
            f"- Strong: `{report.get('strong_count', 0)}` | Weak: `{report.get('weak_count', 0)}`",
            "",
            "| Rank | Repo | Stars | Domain | Barrier | Maturity | Value |",
            "| --- | --- | ---: | --- | --- | --- | --- |",
        ]

        if not projects:
            lines.append("| - | - | 0 | - | - | - | - |")
            return "\n".join(lines)

        for project in projects:
            lines.append(
                f"| {project.get('rank', '')} | {project.get('repo_name', '')} | {project.get('stars', 0)} | "
                f"{project.get('domain', '')} | {project.get('domain_barrier_level', '')} | "
                f"{project.get('maturity_level', '')} | {project.get('commercial_value_level', '')} |"
            )

        return "\n".join(lines)

    def _resolve_base_path(self) -> str:
        """解析 GitHub Pages base path（优先环境变量，其次 GitHub Actions 上下文）"""
        from_env = self._normalize_base_path(GITHUB_PAGES_URL)
        if from_env:
            return from_env

        github_repository = os.getenv("GITHUB_REPOSITORY", "")
        if "/" not in github_repository:
            return ""

        owner, repo = github_repository.split("/", 1)
        if repo.lower() == f"{owner.lower()}.github.io":
            return ""

        return f"/{repo}"

    @staticmethod
    def _normalize_base_path(pages_url: str) -> str:
        """从完整 URL 中提取路径前缀，例如 /github-topics-trending"""
        if not pages_url:
            return ""

        parsed = urlparse(pages_url)
        path = (parsed.path or "").strip()
        if not path:
            return ""

        normalized = "/" + path.strip("/")
        if normalized == "/":
            return ""
        return normalized

    def _site_href(self, path: str) -> str:
        """生成站内链接，自动拼接 base path"""
        normalized_path = "/" + path.lstrip("/")
        if self.base_path:
            return f"{self.base_path}{normalized_path}"
        return normalized_path

    def generate_index(self, trends: Dict, date: str, opportunity_report: Dict, export_files: Dict[str, str]) -> str:
        """
        生成首页

        Args:
            trends: 趋势数据
            date: 日期
            opportunity_report: 目标机会报表
            export_files: 导出文件映射

        Returns:
            生成的文件路径
        """
        top_20 = trends.get("top_20", [])[:20]
        opportunities = opportunity_report.get("projects", []) or []
        opportunity_cards = "".join(self._format_opportunity_card(repo) for repo in opportunities[:12])
        if not opportunity_cards:
            opportunity_cards = self._format_empty_card("当前阈值下暂无候选机会项目，可将 PUSH_MIN_COMMERCIAL_LEVEL 调整为 weak 查看更多候选。")

        content = self._get_base_html(f"{self.meta['title']} - 首页", """
        <div class="hero">
            <h1>{title}</h1>
            <p class="subtitle">{subtitle}</p>
            <p class="date">{date}</p>
        </div>

        <div class="container">
            <section class="section">
                <h2 class="section-title">目标机会项目</h2>
                <div class="repo-list">
                    {opportunity_cards}
                </div>
            </section>

            <section class="section">
                <h2 class="section-title">报表导出</h2>
                {export_section}
            </section>

            <section class="section">
                <h2 class="section-title">Top 20 经典榜单</h2>
                <div class="repo-grid">
                    {repo_cards}
                </div>
            </section>

            <section class="section">
                <h2 class="section-title">按分类浏览</h2>
                <div class="category-grid">
                    {category_cards}
                </div>
            </section>
        </div>
        """.format(
            title=self.meta['title'],
            subtitle=self.meta['subtitle'],
            date=date,
            opportunity_cards=opportunity_cards,
            export_section=self._format_export_section(opportunity_report, export_files),
            repo_cards="".join(self._format_repo_card_small(repo) for repo in top_20),
            category_cards="".join(self._format_category_card(cat) for cat in CATEGORIES.values())
        ))

        path = self.output_dir / "index.html"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _get_target_opportunities(self, repos: List[Dict]) -> List[Dict]:
        """按商业价值阈值过滤目标机会项目"""
        allowed_levels = {"strong"}
        if PUSH_MIN_COMMERCIAL_LEVEL == "weak":
            allowed_levels = {"strong", "weak"}

        selected: List[Dict] = []
        for repo in repos:
            assessment = repo.get("purpose_assessment", {}) or {}
            level = str(assessment.get("commercial_value_level", "none")).lower()
            recommended = bool(assessment.get("recommended_for_push", False))
            if recommended and level in allowed_levels:
                selected.append(repo)
        return selected

    def _format_opportunity_card(self, repo: Dict) -> str:
        """格式化目标机会卡片（结构化展示）"""
        repo_name = repo.get("repo_name", "")
        url = repo.get("url", f"https://github.com/{repo_name}")
        assessment = repo.get("purpose_assessment", {}) or {}

        domain = repo.get("domain") or assessment.get("domain", "-")
        barrier = repo.get("domain_barrier_level") or assessment.get("domain_barrier_level", "-")
        maturity = repo.get("maturity_level") or assessment.get("maturity_level", "-")
        commercial_level = repo.get("commercial_value_level") or assessment.get("commercial_value_level", "none")
        private_fit = repo.get("private_deploy_fit") or assessment.get("private_deploy_fit", "-")
        model_service_focus = repo.get("is_model_service_project")
        if model_service_focus is None:
            model_service_focus = assessment.get("is_model_service_project", False)

        features = repo.get("implemented_features") or assessment.get("implemented_features", []) or []
        issues = repo.get("current_issues") or assessment.get("current_issues", []) or []
        roadmap = repo.get("roadmap_signals") or assessment.get("roadmap_signals", []) or []
        directions = repo.get("future_directions") or assessment.get("future_directions", []) or []
        opportunities = repo.get("infra_transformation_opportunities") or assessment.get("infra_transformation_opportunities", []) or []
        commercial_reason = repo.get("commercial_value_reason") or assessment.get("commercial_value_reason", "")
        summary = repo.get("summary", "") or assessment.get("summary", "")

        def _list_html(items: List[str], limit: int = 3) -> str:
            if not items:
                return "<li>-</li>"
            return "".join([f"<li>{item}</li>" for item in items[:limit]])

        return f"""
        <div class="repo-card">
            <h3><a href="{url}">{repo_name}</a></h3>
            <div class="badges">
                <span class="badge badge-category">商业价值: {commercial_level}</span>
                <span class="badge badge-language">领域: {domain}</span>
                <span class="badge badge-language">门槛: {barrier}</span>
                <span class="badge badge-language">成熟度: {maturity}</span>
                <span class="badge badge-language">私有化适配: {private_fit}</span>
                <span class="badge badge-language">模型服务导向: {'是' if model_service_focus else '否'}</span>
            </div>
            <p class="summary">{summary}</p>
            <div class="opportunity-meta">
                <p><strong>商业判断：</strong>{commercial_reason or '-'}</p>
                <p><strong>机会点：</strong>{'；'.join(opportunities[:3]) if opportunities else '-'}</p>
            </div>
            <div class="opportunity-table-wrap">
                <table class="opportunity-table">
                    <tr>
                        <td><strong>已实现</strong><ul>{_list_html(features)}</ul></td>
                        <td><strong>问题</strong><ul>{_list_html(issues)}</ul></td>
                    </tr>
                    <tr>
                        <td><strong>Roadmap</strong><ul>{_list_html(roadmap)}</ul></td>
                        <td><strong>未来方向</strong><ul>{_list_html(directions)}</ul></td>
                    </tr>
                </table>
            </div>
        </div>
        """

    def _to_site_export_href(self, file_path: str) -> str:
        """将输出文件绝对路径转换为站内可访问链接"""
        if not file_path:
            return self._site_href("/exports/")

        path_obj = Path(file_path)
        try:
            relative = path_obj.relative_to(self.output_dir)
        except ValueError:
            relative = Path("exports") / path_obj.name
        return self._site_href(f"/{relative.as_posix()}")

    def _format_export_section(self, report: Dict, export_files: Dict[str, str]) -> str:
        """渲染报表导出区块"""
        report_date = report.get("date", "")
        total_scanned = report.get("total_scanned", 0)
        total_candidates = report.get("total_candidates", 0)
        strong_count = report.get("strong_count", 0)
        weak_count = report.get("weak_count", 0)
        min_level = report.get("min_level", PUSH_MIN_COMMERCIAL_LEVEL)

        latest_json = self._to_site_export_href(export_files.get("json_latest", ""))
        latest_csv = self._to_site_export_href(export_files.get("csv_latest", ""))
        latest_md = self._to_site_export_href(export_files.get("md_latest", ""))
        date_json = self._to_site_export_href(export_files.get("json", ""))
        date_csv = self._to_site_export_href(export_files.get("csv", ""))
        date_md = self._to_site_export_href(export_files.get("md", ""))

        return f"""
        <p class="page-description">阈值 `{min_level}` | 扫描 {total_scanned} 个项目，筛出 {total_candidates} 个机会（Strong {strong_count} / Weak {weak_count}）。</p>
        <div class="export-grid">
            <div class="export-card">
                <h3>最新 JSON</h3>
                <p>机器可读结构化数据，适合二次处理</p>
                <a href="{latest_json}" download>下载 latest.json</a>
            </div>
            <div class="export-card">
                <h3>最新 CSV</h3>
                <p>适合表格查看与 BI 工具导入</p>
                <a href="{latest_csv}" download>下载 latest.csv</a>
            </div>
            <div class="export-card">
                <h3>最新 Markdown</h3>
                <p>适合运营复盘与周报引用</p>
                <a href="{latest_md}" download>下载 latest.md</a>
            </div>
            <div class="export-card">
                <h3>{report_date} JSON</h3>
                <p>按日期归档版本</p>
                <a href="{date_json}" download>下载 {report_date}.json</a>
            </div>
            <div class="export-card">
                <h3>{report_date} CSV</h3>
                <p>按日期归档版本</p>
                <a href="{date_csv}" download>下载 {report_date}.csv</a>
            </div>
            <div class="export-card">
                <h3>{report_date} Markdown</h3>
                <p>按日期归档版本</p>
                <a href="{date_md}" download>下载 {report_date}.md</a>
            </div>
        </div>
        """

    @staticmethod
    def _format_empty_card(message: str) -> str:
        """空结果占位卡片"""
        return f"""
        <div class="repo-card empty-state">
            <p class="summary">{message}</p>
        </div>
        """

    def generate_trending_page(self, trends: Dict, date: str, opportunity_report: Dict, export_files: Dict[str, str]) -> str:
        """
        生成趋势页

        Args:
            trends: 趋势数据
            date: 日期
            opportunity_report: 目标机会报表
            export_files: 导出文件映射

        Returns:
            生成的文件路径
        """
        content = self._get_base_html(f"趋势 - {date}", f"""
        <div class="container">
            <h1 class="page-title">趋势报告 - {date}</h1>

            <section class="section">
                <h2 class="section-title">目标机会快照</h2>
                <div class="repo-list">
                    {"".join(self._format_opportunity_card(repo) for repo in (opportunity_report.get("projects", []) or [])[:8]) or self._format_empty_card("当前暂无可展示的目标机会快照。")}
                </div>
            </section>

            <section class="section">
                <h2 class="section-title">报表导出</h2>
                {self._format_export_section(opportunity_report, export_files)}
            </section>

            <section class="section">
                <h2 class="section-title">星标增长 Top 5</h2>
                <div class="repo-list">
                    {"".join(self._format_repo_card_medium(repo) for repo in trends.get("rising_top5", []))}
                </div>
            </section>

            <section class="section">
                <h2 class="section-title">新晋项目</h2>
                <div class="repo-list">
                    {"".join(self._format_repo_card_medium(repo) for repo in trends.get("new_entries", [])[:10])}
                </div>
            </section>

            <section class="section">
                <h2 class="section-title">活跃项目</h2>
                <div class="repo-list">
                    {"".join(self._format_repo_card_medium(repo) for repo in trends.get("active", []))}
                </div>
            </section>
        </div>
        """)

        filename = f"{date}.html"
        path = self.output_dir / "trending" / filename
        path.write_text(content, encoding="utf-8")

        # 同时创建最新的链接
        latest_path = self.output_dir / "trending" / "latest.html"
        latest_path.write_text(content, encoding="utf-8")

        return str(path)

    def generate_category_pages(self, db) -> List[str]:
        """
        生成分类页面

        Args:
            db: 数据库实例

        Returns:
            生成的文件路径列表
        """
        files = []

        for key, info in CATEGORIES.items():
            repos = db.get_repos_by_category(key, limit=50)

            content = self._get_base_html(
                f"{info['name']} - 分类",
                f"""
        <div class="container">
            <h1 class="page-title">{info['icon']} {info['name']}</h1>
            <p class="page-description">{info['description']}</p>

            <div class="repo-list">
                {"".join(self._format_repo_card_medium(repo) for repo in repos)}
            </div>
        </div>
        """
            )

            path = self.output_dir / "category" / f"{key}.html"
            path.write_text(content, encoding="utf-8")
            files.append(str(path))

        return files

    def generate_css(self) -> str:
        """
        生成 CSS 文件

        Returns:
            生成的文件路径
        """
        t = self.theme
        css = f"""
/* GitHub Topics Trending - 主题样式 */
:root {{
    --primary: {t['primary']};
    --secondary: {t['secondary']};
    --bg: {t['bg']};
    --card: {t['card']};
    --text: {t['text']};
    --text-secondary: {t['text_secondary']};
    --border: {t['border']};
    --success: {t['success']};
    --warning: {t['warning']};
    --danger: {t['danger']};
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background-color: var(--bg);
    color: var(--text);
    line-height: 1.6;
}}

.container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}}

.hero {{
    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
    color: white;
    padding: 60px 20px;
    text-align: center;
}}

.hero h1 {{
    font-size: 2.5rem;
    margin-bottom: 10px;
}}

.hero .subtitle {{
    font-size: 1.2rem;
    opacity: 0.9;
}}

.hero .date {{
    margin-top: 20px;
    opacity: 0.8;
}}

.page-title {{
    font-size: 2rem;
    margin-bottom: 10px;
    padding: 20px 0;
}}

.page-description {{
    color: var(--text-secondary);
    margin-bottom: 30px;
}}

.section {{
    margin: 40px 0;
}}

.section-title {{
    font-size: 1.5rem;
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--primary);
}}

.repo-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 20px;
}}

.repo-list {{
    display: flex;
    flex-direction: column;
    gap: 15px;
}}

.repo-card {{
    background-color: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    transition: transform 0.2s, box-shadow 0.2s;
}}

.repo-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}}

.repo-card h3 {{
    font-size: 1.2rem;
    margin-bottom: 8px;
}}

.repo-card h3 a {{
    color: var(--primary);
    text-decoration: none;
}}

.repo-card h3 a:hover {{
    text-decoration: underline;
}}

.repo-card .stats {{
    display: flex;
    gap: 15px;
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin: 10px 0;
}}

.repo-card .summary {{
    color: var(--text-secondary);
    font-size: 0.95rem;
    margin-top: 10px;
}}

.empty-state {{
    text-align: center;
    border-style: dashed;
}}

.opportunity-meta {{
    margin-top: 12px;
    font-size: 0.9rem;
    color: var(--text-secondary);
}}

.opportunity-meta p {{
    margin-top: 4px;
}}

.opportunity-table-wrap {{
    margin-top: 12px;
}}

.opportunity-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.86rem;
}}

.opportunity-table td {{
    vertical-align: top;
    padding: 8px;
    border-top: 1px solid var(--border);
    width: 50%;
}}

.opportunity-table ul {{
    margin: 6px 0 0 14px;
    color: var(--text-secondary);
}}

.export-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 15px;
}}

.export-card {{
    background-color: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
}}

.export-card h3 {{
    margin-bottom: 8px;
    font-size: 1rem;
}}

.export-card p {{
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin-bottom: 10px;
}}

.export-card a {{
    color: var(--primary);
    text-decoration: none;
    font-weight: 500;
}}

.export-card a:hover {{
    text-decoration: underline;
}}

.repo-card .badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
}}

.badge {{
    display: inline-block;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
}}

.badge-category {{
    background-color: var(--primary);
    color: white;
}}

.badge-language {{
    background-color: var(--border);
    color: var(--text);
}}

.category-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 15px;
}}

.category-card {{
    background-color: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    transition: transform 0.2s;
}}

.category-card:hover {{
    transform: scale(1.05);
}}

.category-card a {{
    color: var(--text);
    text-decoration: none;
}}

.category-icon {{
    font-size: 2rem;
    margin-bottom: 10px;
}}

.category-name {{
    font-size: 1.1rem;
    font-weight: 600;
}}

.category-desc {{
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-top: 5px;
}}

.footer {{
    text-align: center;
    padding: 30px;
    color: var(--text-secondary);
    border-top: 1px solid var(--border);
    margin-top: 40px;
}}

.footer a {{
    color: var(--primary);
    text-decoration: none;
}}

/* 导航栏样式 */
.nav {{
    background-color: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 15px 0;
    position: sticky;
    top: 0;
    z-index: 100;
}}

.nav-content {{
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

.nav-logo {{
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--primary);
    text-decoration: none;
}}

.nav-links {{
    display: flex;
    gap: 20px;
}}

.nav-links a {{
    color: var(--text);
    text-decoration: none;
    font-size: 0.95rem;
    transition: color 0.2s;
}}

.nav-links a:hover {{
    color: var(--primary);
}}

@media (max-width: 768px) {{
    .nav-content {{
        flex-direction: column;
        gap: 10px;
    }}

    .repo-grid {{
        grid-template-columns: 1fr;
    }}

    .hero h1 {{
        font-size: 1.8rem;
    }}
}}
"""

        path = self.output_dir / "assets" / "css" / "style.css"
        path.write_text(css, encoding="utf-8")
        return str(path)

    def _get_base_html(self, title: str, body_content: str) -> str:
        """生成基础 HTML 结构"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {self.meta['title']}</title>
    <meta name="description" content="{self.meta['description']}">
    <link rel="stylesheet" href="{self._site_href('/assets/css/style.css')}">
</head>
<body>
    <nav class="nav">
        <div class="container nav-content">
            <a href="{self._site_href('/')}" class="nav-logo">{self.meta['title']}</a>
            <div class="nav-links">
                <a href="{self._site_href('/')}" >首页</a>
                <a href="{self._site_href('/trending/latest.html')}">趋势</a>
                <a href="{self._site_href('/category/plugin.html')}">分类</a>
                <a href="{self._site_href('/exports/opportunity-report-latest.md')}">导出</a>
            </div>
        </div>
    </nav>

    {body_content}

    <footer class="footer">
        <p>{self.meta['title']} - {self.meta['description']}</p>
        <p style="margin-top: 10px;">
            <a href="https://github.com/topics/{self.topic}">GitHub Topic: {self.topic}</a>
        </p>
    </footer>
</body>
</html>"""

    def _format_repo_card_small(self, repo: Dict) -> str:
        """格式化小型仓库卡片"""
        repo_name = repo.get("repo_name", "")
        stars = repo.get("stars", 0)
        summary = repo.get("summary", "") or repo.get("description", "")
        detail_link = repo.get("url", f"https://github.com/{repo_name}")

        return f"""
        <div class="repo-card">
            <h3><a href="{detail_link}">{repo_name}</a></h3>
            <div class="stats">
                <span>⭐ {format_number(stars)}</span>
            </div>
            <p class="summary">{summary[:80]}...</p>
        </div>
        """

    def _format_repo_card_medium(self, repo: Dict) -> str:
        """格式化中型仓库卡片"""
        repo_name = repo.get("repo_name", "")
        url = repo.get("url", f"https://github.com/{repo_name}")
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        language = repo.get("language", "")
        category_zh = repo.get("category_zh", "")
        summary = repo.get("summary", "") or repo.get("description", "")
        tags = repo.get("tags", [])
        if isinstance(tags, str):
            try:
                parsed_tags = json.loads(tags)
                tags = parsed_tags if isinstance(parsed_tags, list) else []
            except json.JSONDecodeError:
                tags = []

        badges = ""
        if category_zh:
            badges += f'<span class="badge badge-category">{category_zh}</span>'
        if language:
            badges += f'<span class="badge badge-language">{language}</span>'
        for tag in tags[:3]:
            badges += f'<span class="badge badge-language">#{tag}</span>'

        return f"""
        <div class="repo-card">
            <h3><a href="{url}">{repo_name}</a></h3>
            <div class="stats">
                <span>⭐ {format_number(stars)}</span>
                <span>🔱 {format_number(forks)}</span>
            </div>
            <p class="summary">{summary[:150]}</p>
            <div class="badges">{badges}</div>
        </div>
        """

    def _format_category_card(self, category: Dict) -> str:
        """格式化分类卡片"""
        key = [k for k, v in CATEGORIES.items() if v == category][0]
        category_link = self._site_href(f"/category/{key}.html")

        return f"""
        <div class="category-card">
            <a href="{category_link}">
                <div class="category-icon">{category['icon']}</div>
                <div class="category-name">{category['name']}</div>
                <div class="category-desc">{category['description']}</div>
            </a>
        </div>
        """


def generate_website(trends: Dict, date: str, db, output_dir: str = None) -> List[str]:
    """便捷函数：生成网站"""
    generator = WebGenerator(output_dir)
    return generator.generate_all(trends, date, db)
