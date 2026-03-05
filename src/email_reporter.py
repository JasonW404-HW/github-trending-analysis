"""
Email Reporter - 生成 HTML 邮件报告
GitHub Topics Trending 专业邮件排版
"""
from typing import Dict, List
from src.config import TOPIC, PUSH_MIN_COMMERCIAL_LEVEL, get_theme, format_number


class EmailReporter:
    """生成 HTML 邮件报告"""

    def __init__(self, theme: str = "blue"):
        """
        初始化

        Args:
            theme: 主题名称
        """
        self.theme = get_theme(theme)
        self.topic = TOPIC

    def generate_email_html(self, trends: Dict, date: str) -> str:
        """
        生成完整的 HTML 邮件

        Args:
            trends: 趋势数据
            date: 日期

        Returns:
            HTML 字符串
        """
        html_parts = []

        # HTML 头部
        html_parts.append(self._get_header(date))

        # 高潜商业价值项目（仅推送目标项目）
        opportunities = self._filter_push_candidates(trends.get("top_20", []))
        html_parts.append(self._render_target_opportunities(opportunities))

        # 星标增长 Top 5
        rising = trends.get("rising_top5", [])
        if rising:
            html_parts.append(self._render_rising_top5(rising))

        # 新晋项目
        new_entries = trends.get("new_entries", [])
        if new_entries:
            html_parts.append(self._render_new_entries(new_entries))

        # 活跃项目
        active = trends.get("active", [])
        if active:
            html_parts.append(self._render_active(active))

        # 统计信息
        html_parts.append(self._render_stats(trends, opportunities))

        # HTML 尾部
        html_parts.append(self._get_footer(date))

        return "\n".join(html_parts)

    def _get_header(self, date: str) -> str:
        """生成 HTML 头部"""
        t = self.theme
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Topics Daily - {self.topic}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: {t['bg']};
            -webkit-font-smoothing: antialiased;
        }}
        .container {{
            max-width: 640px;
            margin: 0 auto;
            background-color: {t['card']};
        }}
        .header {{
            background: linear-gradient(135deg, {t['primary']} 0%, {t['secondary']} 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 26px;
            font-weight: 600;
            letter-spacing: -0.5px;
        }}
        .header p {{
            margin: 8px 0 0;
            font-size: 14px;
            opacity: 0.8;
            font-weight: 400;
        }}
        .section {{
            padding: 28px 30px;
            border-bottom: 1px solid {t['border']};
        }}
        .section:last-child {{
            border-bottom: none;
        }}
        .section-title {{
            margin: 0 0 20px;
            font-size: 15px;
            font-weight: 600;
            color: {t['text']};
            text-transform: uppercase;
            letter-spacing: 1px;
            padding-bottom: 12px;
            border-bottom: 2px solid {t['primary']};
        }}
        .repo-card {{
            margin-bottom: 16px;
            padding: 0;
            background-color: {t['card']};
        }}
        .repo-card:last-child {{
            margin-bottom: 0;
        }}
        .repo-main {{
            display: flex;
            align-items: baseline;
            padding: 14px 16px;
            background-color: {t['bg']};
            border-radius: 6px;
            border-left: 3px solid {t['primary']};
        }}
        .repo-rank {{
            font-size: 14px;
            font-weight: 700;
            color: {t['text']};
            min-width: 32px;
        }}
        .repo-name {{
            font-size: 15px;
            font-weight: 600;
            color: {t['text']};
            flex-grow: 1;
            margin: 0 10px;
        }}
        .repo-name a {{
            color: {t['text']};
            text-decoration: none;
        }}
        .repo-name a:hover {{
            text-decoration: underline;
        }}
        .repo-stats {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 13px;
        }}
        .rank-change {{
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 12px;
        }}
        .rank-up {{
            color: {t['success']};
            background-color: rgba(35, 134, 54, 0.2);
        }}
        .rank-down {{
            color: {t['danger']};
            background-color: rgba(248, 81, 73, 0.2);
        }}
        .rank-same {{
            color: {t['text_secondary']};
            background-color: {t['border']};
        }}
        .stars {{
            color: {t['text_secondary']};
            font-size: 13px;
        }}
        .repo-content {{
            padding: 12px 16px 0;
        }}
        .repo-summary {{
            color: {t['text_secondary']};
            font-size: 14px;
            line-height: 1.6;
            margin-bottom: 8px;
        }}
        .repo-meta {{
            font-size: 13px;
            color: {t['text_secondary']};
            margin-bottom: 10px;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            margin-right: 6px;
            margin-bottom: 4px;
        }}
        .badge-category {{
            background-color: {t['primary']};
            color: white;
        }}
        .badge-language {{
            background-color: {t['border']};
            color: {t['text']};
        }}
        .badge-new {{
            background-color: {t['success']};
            color: white;
        }}
        .solves-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .solve-tag {{
            background-color: {t['border']};
            color: {t['text_secondary']};
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }}
        .stat-item {{
            text-align: center;
            padding: 16px;
            background-color: {t['bg']};
            border-radius: 8px;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: 700;
            color: {t['primary']};
        }}
        .stat-label {{
            font-size: 12px;
            color: {t['text_secondary']};
            margin-top: 4px;
        }}
        .footer {{
            text-align: center;
            padding: 28px 20px;
            font-size: 12px;
            color: {t['text_secondary']};
            background-color: {t['bg']};
        }}
        .footer a {{
            color: {t['primary']};
            text-decoration: none;
            font-weight: 500;
        }}
        .footer a:hover {{
            text-decoration: underline;
        }}
        .compact-card {{
            padding: 12px 14px;
            margin-bottom: 8px;
            background-color: {t['bg']};
            border-radius: 6px;
            border-left: 3px solid {t['border']};
        }}
        .compact-card:last-child {{
            margin-bottom: 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>GitHub Topics Daily</h1>
            <p>#{self.topic} - {date}</p>
        </div>"""

    def _get_footer(self, date: str) -> str:
        """生成 HTML 尾部"""
        return f"""        <div class="footer">
            <p>GitHub Topics Trending - #{self.topic}</p>
            <p style="margin-top: 8px;">Data source: <a href="https://github.com/topics/{self.topic}">github.com/topics/{self.topic}</a></p>
        </div>
    </div>
</body>
</html>"""

    def _render_top_20(self, repos: List[Dict]) -> str:
        """渲染 Top 20 榜单"""
        if not repos:
            return self._section_html("Top 20 榜单", '<p style="text-align:center;color:#9ca3af;padding:24px;">暂无数据</p>')

        cards = []
        for repo in repos[:20]:
            cards.append(self._format_repo_card(repo, show_details=True))

        return self._section_html("Top 20 经典榜单", "\n".join(cards))

    def _filter_push_candidates(self, repos: List[Dict]) -> List[Dict]:
        """根据商业价值等级过滤邮件候选项目"""
        if not repos:
            return []

        allowed_levels = {"strong"}
        if PUSH_MIN_COMMERCIAL_LEVEL == "weak":
            allowed_levels = {"strong", "weak"}

        candidates: List[Dict] = []
        for repo in repos:
            assessment = repo.get("purpose_assessment", {}) or {}
            level = str(assessment.get("commercial_value_level", "none")).lower()
            recommended = bool(assessment.get("recommended_for_push", False))
            if recommended and level in allowed_levels:
                candidates.append(repo)

        return candidates

    def _render_target_opportunities(self, repos: List[Dict]) -> str:
        """渲染目标导向机会清单"""
        if not repos:
            return self._section_html(
                "目标机会项目",
                '<p style="text-align:center;color:#9ca3af;padding:24px;">未发现满足当前商业价值阈值的项目</p>',
            )

        rows: List[str] = []
        for repo in repos[:20]:
            rows.append(self._format_target_row(repo))

        table_html = f"""
        <table style="width:100%;border-collapse:collapse;background:{self.theme['bg']};border-radius:8px;overflow:hidden;">
            <thead>
                <tr style="background:{self.theme['border']};text-align:left;">
                    <th style="padding:10px 12px;font-size:12px;">项目</th>
                    <th style="padding:10px 12px;font-size:12px;">领域/门槛</th>
                    <th style="padding:10px 12px;font-size:12px;">成熟度</th>
                    <th style="padding:10px 12px;font-size:12px;">商业价值</th>
                    <th style="padding:10px 12px;font-size:12px;">关键机会</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """

        return self._section_html("目标机会项目", table_html)

    def _format_target_row(self, repo: Dict) -> str:
        """格式化目标机会项目行"""
        repo_name = repo.get("repo_name", "")
        url = repo.get("url", f"https://github.com/{repo_name}")
        assessment = repo.get("purpose_assessment", {}) or {}

        domain = assessment.get("domain", "-")
        barrier_level = assessment.get("domain_barrier_level", "-")
        maturity = assessment.get("maturity_level", "-")
        commercial_level = assessment.get("commercial_value_level", "none")
        opportunities = assessment.get("infra_transformation_opportunities", []) or []
        opportunity_text = "；".join(opportunities[:2]) if opportunities else "-"

        return f"""
        <tr style="border-top:1px solid {self.theme['border']};vertical-align:top;">
            <td style="padding:10px 12px;">
                <a href="{url}" style="color:{self.theme['text']};text-decoration:none;font-weight:600;">{repo_name}</a>
                <div style="margin-top:4px;color:{self.theme['text_secondary']};font-size:12px;">{repo.get('summary', '')}</div>
            </td>
            <td style="padding:10px 12px;font-size:12px;">
                <div>{domain}</div>
                <div style="color:{self.theme['text_secondary']};margin-top:4px;">门槛: {barrier_level}</div>
            </td>
            <td style="padding:10px 12px;font-size:12px;">{maturity}</td>
            <td style="padding:10px 12px;font-size:12px;">{commercial_level}</td>
            <td style="padding:10px 12px;font-size:12px;color:{self.theme['text_secondary']};">{opportunity_text}</td>
        </tr>
        """

    def _render_rising_top5(self, repos: List[Dict]) -> str:
        """渲染星标增长 Top 5"""
        cards = []
        for repo in repos:
            cards.append(self._format_compact_card(repo, trend="up"))

        return self._section_html("星标增长 Top 5", "\n".join(cards))

    def _render_new_entries(self, repos: List[Dict]) -> str:
        """渲染新晋项目"""
        if not repos:
            return ""

        cards = []
        for repo in repos[:10]:
            cards.append(self._format_compact_card(repo, is_new=True))

        return self._section_html(f"新晋项目 ({len(repos)})", "\n".join(cards))

    def _render_active(self, repos: List[Dict]) -> str:
        """渲染活跃项目"""
        if not repos:
            return ""

        cards = []
        for repo in repos[:10]:
            cards.append(self._format_active_card(repo))

        return self._section_html("活跃项目", "\n".join(cards))

    def _render_stats(self, trends: Dict, opportunities: List[Dict]) -> str:
        """渲染统计信息"""
        new_count = len(trends.get("new_entries", []))
        rising_count = len(trends.get("rising_top5", []))
        surging_count = len(trends.get("surging", []))
        active_count = len(trends.get("active", []))
        opportunity_count = len(opportunities)

        return self._section_html("趋势概览", f"""
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-value">{new_count}</div>
                <div class="stat-label">新晋项目</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{rising_count}</div>
                <div class="stat-label">上升项目</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{active_count}</div>
                <div class="stat-label">活跃项目</div>
            </div>
        </div>
        <div style="margin-top:12px;color:{self.theme['text_secondary']};font-size:12px;">
            商业机会候选（阈值 {PUSH_MIN_COMMERCIAL_LEVEL}）: <strong style="color:{self.theme['text']};">{opportunity_count}</strong>
        </div>
        """)

    def _format_repo_card(self, repo: Dict, show_details: bool = True) -> str:
        """格式化单个仓库卡片"""
        rank = repo.get("rank", 0)
        repo_name = repo.get("repo_name", "")
        stars_delta = repo.get("stars_delta", 0)
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        language = repo.get("language", "")
        url = repo.get("url", f"https://github.com/{repo_name}")

        # 星标变化指示
        if stars_delta > 0:
            stars_indicator = f'<span class="rank-change rank-up">+{format_number(stars_delta)}</span>'
        elif stars_delta < 0:
            stars_indicator = f'<span class="rank-change rank-down">{format_number(stars_delta)}</span>'
        else:
            stars_indicator = '<span class="rank-change rank-same">-</span>'

        # 语言标签
        language_badge = ""
        if language:
            language_badge = f'<span class="badge badge-language">{language}</span>'

        # 分类标签
        category_badge = ""
        if repo.get("category_zh"):
            category_badge = f'<span class="badge badge-category">{repo.get("category_zh")}</span>'

        # 解决的问题标签
        solves_html = ""
        if show_details and repo.get("solves"):
            solves_tags = [f'<span class="solve-tag">{s}</span>' for s in repo.get("solves", [])[:4]]
            solves_html = f'<div class="solves-list">{"".join(solves_tags)}</div>'

        tags_html = ""
        if show_details and repo.get("tags"):
            tag_items = [f'<span class="solve-tag">#{tag}</span>' for tag in repo.get("tags", [])[:4]]
            tags_html = f'<div class="solves-list" style="margin-top:6px;">{"".join(tag_items)}</div>'

        # 详细信息
        details_html = ""
        if show_details:
            summary = repo.get("summary", "")
            description = repo.get("description", "")

            detail_parts = []
            if summary:
                detail_parts.append(f'<p style="margin: 0 0 8px; color: {self.theme["text_secondary"]}; font-size: 14px; line-height: 1.5;">{summary}</p>')
            if description:
                detail_parts.append(f'<p style="margin: 0; color: {self.theme["text_secondary"]}; font-size: 13px; line-height: 1.5; opacity: 0.8;">{description}</p>')

            details_html = "\n".join(detail_parts)

        return f"""        <div class="repo-card">
            <div class="repo-main">
                <span class="repo-rank">#{rank}</span>
                <span class="repo-name"><a href="{url}">{repo_name}</a></span>
                <div class="repo-stats">
                    {stars_indicator}
                    <span class="stars">{format_number(stars)}</span>
                </div>
            </div>
            <div class="repo-content">
                {details_html}
                <div style="margin-top: 10px;">
                    {category_badge}
                    {language_badge}
                    {solves_html}
                    {tags_html}
                </div>
            </div>
        </div>"""

    def _format_compact_card(self, repo: Dict, trend: str = None, is_new: bool = False) -> str:
        """格式化紧凑卡片"""
        rank = repo.get("rank", 0)
        repo_name = repo.get("repo_name", "")
        url = repo.get("url", f"https://github.com/{repo_name}")
        stars = repo.get("stars", 0)

        # 变化指示
        change_html = ""
        if is_new:
            change_html = '<span class="badge badge-new">NEW</span>'
        elif trend == "up":
            stars_delta = repo.get("stars_delta", 0)
            change_html = f'<span class="rank-change rank-up">+{format_number(stars_delta)}</span>'

        summary_html = ""
        if repo.get("summary"):
            summary_html = f'<div style="padding: 8px 14px 0; font-size: 13px; color: {self.theme["text_secondary"]}; line-height: 1.5;">{repo.get("summary")}</div>'

        return f"""            <div class="compact-card">
                {change_html}
                <span style="font-weight: 600; min-width: 32px; font-size: 13px; color: {self.theme['text']};">#{rank}</span>
                <span style="flex-grow: 1; margin: 0 10px;">
                    <a href="{url}" style="color: {self.theme['text']}; text-decoration: none; font-size: 14px; font-weight: 500;">{repo_name}</a>
                </span>
                <span style="color: {self.theme['text_secondary']}; font-size: 12px;">{format_number(stars)}</span>
            </div>{summary_html}"""

    def _format_active_card(self, repo: Dict) -> str:
        """格式化活跃项目卡片"""
        repo_name = repo.get("repo_name", "")
        url = repo.get("url", f"https://github.com/{repo_name}")
        stars = repo.get("stars", 0)
        updated_at = repo.get("updated_at", "")

        # 简单的时间格式化
        time_ago = "最近"
        if updated_at:
            time_ago = updated_at.split("T")[0]

        summary_html = ""
        if repo.get("summary"):
            summary_html = f'<div style="padding: 8px 14px 0; font-size: 13px; color: {self.theme["text_secondary"]}; line-height: 1.5;">{repo.get("summary")}</div>'

        return f"""            <div class="compact-card">
                <span style="flex-grow: 1; margin: 0 10px;">
                    <a href="{url}" style="color: {self.theme['text']}; text-decoration: none; font-size: 14px; font-weight: 500;">{repo_name}</a>
                </span>
                <span style="color: {self.theme['text_secondary']}; font-size: 12px;">{format_number(stars)}</span>
                <span style="color: {self.theme['text_secondary']}; font-size: 11px; margin-left: 8px;">更新: {time_ago}</span>
            </div>{summary_html}"""

    def _section_html(self, title: str, content: str) -> str:
        """生成一个完整的 section"""
        return f"""        <div class="section">
            <h2 class="section-title">{title}</h2>
            {content}
        </div>"""


def generate_email_html(trends: Dict, date: str, theme: str = "blue") -> str:
    """便捷函数：生成邮件 HTML"""
    reporter = EmailReporter(theme)
    return reporter.generate_email_html(trends, date)
