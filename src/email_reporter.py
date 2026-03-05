"""
Email Reporter - 生成 HTML 邮件报告
聚焦可读性：浅色背景、宽版布局、摘要表 + 详细展开
"""

from html import escape
from typing import Dict, List, Optional

from src.config import PUSH_MIN_COMMERCIAL_LEVEL, TOPIC, format_number, get_theme


class EmailReporter:
    """生成 HTML 邮件报告"""

    def __init__(self, theme: str = "blue"):
        self.theme = get_theme(theme)
        self.topic = TOPIC

    def generate_email_html(
        self,
        trends: Dict,
        date: str,
        report: Optional[Dict] = None,
        single_repo_mode: bool = False,
    ) -> str:
        """生成完整 HTML 邮件。"""
        projects = self._resolve_projects(trends=trends, report=report)

        html_parts = [self._get_header(date=date, single_repo_mode=single_repo_mode)]
        html_parts.append(self._render_overview(report=report, projects=projects, single_repo_mode=single_repo_mode))
        html_parts.append(self._render_summary_table(projects=projects))
        html_parts.append(self._render_project_details(projects=projects))
        html_parts.append(self._render_compact_trends(trends=trends))
        html_parts.append(self._get_footer(date=date))

        return "\n".join(html_parts)

    @staticmethod
    def _as_list(value: object) -> List[str]:
        if not isinstance(value, list):
            return []

        normalized: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            if text not in normalized:
                normalized.append(text)
        return normalized

    @staticmethod
    def _safe_text(value: object) -> str:
        return escape(str(value or "").strip())

    @staticmethod
    def _safe_multiline(value: object) -> str:
        text = escape(str(value or "").strip())
        return text.replace("\n", "<br>")

    def _filter_push_candidates(self, repos: List[Dict]) -> List[Dict]:
        """兼容旧路径：从 trends.top_20 中筛选商业候选。"""
        if not repos:
            return []

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

    def _normalize_project(self, project: Dict) -> Dict:
        """标准化项目结构，兼容 report 与 trends 两种来源。"""
        raw_assessment = project.get("purpose_assessment")
        assessment = raw_assessment if isinstance(raw_assessment, dict) else {}

        commercial_value_level = str(
            project.get("commercial_value_level")
            or assessment.get("commercial_value_level")
            or "none"
        ).lower()

        return {
            "rank": project.get("rank", 0),
            "repo_name": project.get("repo_name", ""),
            "owner": project.get("owner", ""),
            "url": project.get("url", ""),
            "stars": project.get("stars", 0),
            "stars_delta": project.get("stars_delta", 0),
            "language": project.get("language", ""),
            "summary": project.get("summary", "") or project.get("description", ""),
            "description": project.get("description", ""),
            "use_case": project.get("use_case", ""),
            "tags": self._as_list(project.get("tags", [])),
            "domain": project.get("domain") or assessment.get("domain", ""),
            "domain_barrier_level": project.get("domain_barrier_level") or assessment.get("domain_barrier_level", ""),
            "domain_barrier_reason": project.get("domain_barrier_reason") or assessment.get("domain_barrier_reason", ""),
            "maturity_level": project.get("maturity_level") or assessment.get("maturity_level", ""),
            "is_model_service_project": bool(
                project.get("is_model_service_project", assessment.get("is_model_service_project", False))
            ),
            "model_service_focus": project.get("model_service_focus") or assessment.get("model_service_focus", ""),
            "commercial_value_level": commercial_value_level,
            "commercial_value_reason": project.get("commercial_value_reason") or assessment.get("commercial_value_reason", ""),
            "recommended_for_push": bool(
                project.get("recommended_for_push", assessment.get("recommended_for_push", False))
            ),
            "private_deploy_fit": project.get("private_deploy_fit") or assessment.get("private_deploy_fit", ""),
            "implemented_features": self._as_list(
                project.get("implemented_features", assessment.get("implemented_features", []))
            ),
            "current_issues": self._as_list(
                project.get("current_issues", assessment.get("current_issues", []))
            ),
            "roadmap_signals": self._as_list(
                project.get("roadmap_signals", assessment.get("roadmap_signals", []))
            ),
            "future_directions": self._as_list(
                project.get("future_directions", assessment.get("future_directions", []))
            ),
            "infra_transformation_opportunities": self._as_list(
                project.get(
                    "infra_transformation_opportunities",
                    assessment.get("infra_transformation_opportunities", []),
                )
            ),
        }

    def _resolve_projects(self, trends: Dict, report: Optional[Dict]) -> List[Dict]:
        """解析邮件项目列表（优先 report.projects）。"""
        source_projects: List[Dict]

        if isinstance(report, dict):
            report_projects = report.get("projects", [])
            if isinstance(report_projects, list) and report_projects:
                source_projects = report_projects
            else:
                source_projects = self._filter_push_candidates(trends.get("top_20", []))
        else:
            source_projects = self._filter_push_candidates(trends.get("top_20", []))

        normalized = [self._normalize_project(project) for project in source_projects if isinstance(project, dict)]
        return [project for project in normalized if project.get("repo_name")]

    def _get_header(self, date: str, single_repo_mode: bool) -> str:
        """生成邮件头（浅色、宽版、紧凑）。"""
        mode_text = "单仓库定向分析" if single_repo_mode else "全量机会扫描"

        return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>GitHub Topics Daily - {self._safe_text(self.topic)}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #f3f4f6;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
    }}
    .container {{
      max-width: 920px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #e5e7eb;
    }}
    .header {{
      padding: 24px 28px;
      border-bottom: 1px solid #e5e7eb;
      background: #ffffff;
    }}
    .header h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.3;
      color: #111827;
      font-weight: 700;
    }}
    .header p {{
      margin: 8px 0 0;
      color: #4b5563;
      font-size: 13px;
    }}
    .section {{
      padding: 20px 28px;
      border-bottom: 1px solid #e5e7eb;
    }}
    .section-title {{
      margin: 0 0 12px;
      font-size: 16px;
      color: #111827;
      font-weight: 700;
    }}
    .muted {{
      color: #6b7280;
      font-size: 13px;
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      color: #111827;
      table-layout: fixed;
    }}
    .table th {{
      text-align: left;
      background: #f8fafc;
      color: #374151;
      font-weight: 600;
      border: 1px solid #e5e7eb;
      padding: 8px 10px;
      vertical-align: top;
    }}
    .table td {{
      border: 1px solid #e5e7eb;
      padding: 8px 10px;
      vertical-align: top;
      word-wrap: break-word;
      overflow-wrap: anywhere;
    }}
    .repo-link {{
      color: #0f4c81;
      text-decoration: none;
      font-weight: 600;
    }}
    .repo-link:hover {{
      text-decoration: underline;
    }}
    .kpi-grid {{
      width: 100%;
      border-collapse: collapse;
    }}
    .kpi-grid td {{
      border: 1px solid #e5e7eb;
      padding: 12px;
      background: #fafafa;
      text-align: center;
    }}
    .kpi-value {{
      font-size: 20px;
      font-weight: 700;
      color: #111827;
      line-height: 1.2;
    }}
    .kpi-label {{
      margin-top: 4px;
      font-size: 12px;
      color: #6b7280;
    }}
    details.project {{
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      margin-bottom: 12px;
      background: #ffffff;
    }}
    details.project summary {{
      cursor: pointer;
      list-style: none;
      padding: 10px 12px;
      background: #f8fafc;
      border-bottom: 1px solid #e5e7eb;
      color: #111827;
      font-weight: 600;
      font-size: 14px;
    }}
    details.project summary::-webkit-details-marker {{
      display: none;
    }}
    details.project .detail-body {{
      padding: 12px;
      font-size: 13px;
      color: #1f2937;
      line-height: 1.6;
    }}
    .badge {{
      display: inline-block;
      margin: 0 6px 6px 0;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      border: 1px solid #d1d5db;
      color: #374151;
      background: #f9fafb;
    }}
    .block-title {{
      margin: 10px 0 4px;
      font-size: 12px;
      color: #111827;
      font-weight: 700;
    }}
    .list {{
      margin: 4px 0 0;
      padding-left: 18px;
      color: #374151;
    }}
    .list li {{
      margin-bottom: 4px;
    }}
    .detail-grid {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }}
    .detail-grid td {{
      border: 1px solid #e5e7eb;
      padding: 8px;
      vertical-align: top;
    }}
    .detail-grid td:first-child {{
      width: 140px;
      background: #f9fafb;
      color: #111827;
      font-weight: 600;
      font-size: 12px;
    }}
    .footer {{
      padding: 18px 28px;
      color: #6b7280;
      font-size: 12px;
      text-align: center;
      background: #f9fafb;
    }}
    @media only screen and (max-width: 760px) {{
      .container {{
        max-width: 100% !important;
        border-left: none;
        border-right: none;
      }}
      .section, .header, .footer {{
        padding: 14px !important;
      }}
      .table, .table thead, .table tbody, .table th, .table td, .table tr {{
        display: block;
      }}
      .table thead {{
        display: none;
      }}
      .table td {{
        border-top: none;
      }}
    }}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"header\">
      <h1>GitHub 商业机会日报</h1>
      <p>Topic: #{self._safe_text(self.topic)} ｜ 日期: {self._safe_text(date)} ｜ 模式: {self._safe_text(mode_text)}</p>
    </div>"""

    def _get_footer(self, date: str) -> str:
        return f"""    <div class=\"footer\">
      <div>GitHub Topics Trending · {self._safe_text(date)}</div>
      <div style=\"margin-top:6px;\">Data source: <a href=\"https://github.com/topics/{self._safe_text(self.topic)}\" style=\"color:#0f4c81;text-decoration:none;\">github.com/topics/{self._safe_text(self.topic)}</a></div>
    </div>
  </div>
</body>
</html>"""

    def _render_overview(self, report: Optional[Dict], projects: List[Dict], single_repo_mode: bool) -> str:
        total_candidates = len(projects)
        strong_count = len(
            [project for project in projects if str(project.get("commercial_value_level", "")).lower() == "strong"]
        )
        weak_count = len(
            [project for project in projects if str(project.get("commercial_value_level", "")).lower() == "weak"]
        )

        if isinstance(report, dict):
            strong_count = int(report.get("strong_count", strong_count) or strong_count)
            weak_count = int(report.get("weak_count", weak_count) or weak_count)

        mode_desc = "仅展示指定仓库" if single_repo_mode else "按商业阈值筛选后全量展示"

        return f"""    <div class=\"section\">
      <h2 class=\"section-title\">摘要概览</h2>
      <table class=\"kpi-grid\" role=\"presentation\">
        <tr>
          <td>
            <div class=\"kpi-value\">{total_candidates}</div>
            <div class=\"kpi-label\">候选项目</div>
          </td>
          <td>
            <div class=\"kpi-value\">{strong_count}</div>
            <div class=\"kpi-label\">Strong</div>
          </td>
          <td>
            <div class=\"kpi-value\">{weak_count}</div>
            <div class=\"kpi-label\">Weak</div>
          </td>
          <td>
            <div class=\"kpi-value\">{self._safe_text(PUSH_MIN_COMMERCIAL_LEVEL)}</div>
            <div class=\"kpi-label\">阈值</div>
          </td>
        </tr>
      </table>
      <p class=\"muted\" style=\"margin:10px 0 0;\">展示策略：{self._safe_text(mode_desc)}</p>
    </div>"""

    def _render_summary_table(self, projects: List[Dict]) -> str:
        if not projects:
            return """    <div class=\"section\">
      <h2 class=\"section-title\">项目摘要表</h2>
      <p class=\"muted\">当前阈值下暂无候选项目。</p>
    </div>"""

        rows: List[str] = []
        for project in projects:
            rank = project.get("rank", "-")
            repo_name = self._safe_text(project.get("repo_name", ""))
            summary = self._safe_text(project.get("summary", "") or project.get("description", ""))
            url = self._safe_text(project.get("url", ""))
            commercial = self._safe_text(project.get("commercial_value_level", "none"))
            stars = format_number(int(project.get("stars", 0) or 0))

            rows.append(
                f"""        <tr>
          <td>{rank}</td>
          <td><a class=\"repo-link\" href=\"{url}\">{repo_name}</a></td>
          <td>{summary or '-'}</td>
          <td>{commercial}</td>
          <td>{stars}</td>
        </tr>"""
            )

        return f"""    <div class=\"section\">
      <h2 class=\"section-title\">项目摘要表</h2>
      <table class=\"table\" role=\"table\">
        <thead>
          <tr>
            <th style=\"width:56px;\">Rank</th>
            <th style=\"width:220px;\">项目</th>
            <th>摘要</th>
            <th style=\"width:80px;\">价值</th>
            <th style=\"width:80px;\">Stars</th>
          </tr>
        </thead>
        <tbody>
{''.join(rows)}
        </tbody>
      </table>
    </div>"""

    def _render_badges(self, project: Dict) -> str:
        badges = [
            f"<span class=\"badge\">价值:{self._safe_text(project.get('commercial_value_level', 'none'))}</span>",
            f"<span class=\"badge\">领域:{self._safe_text(project.get('domain', '-'))}</span>",
            f"<span class=\"badge\">门槛:{self._safe_text(project.get('domain_barrier_level', '-'))}</span>",
            f"<span class=\"badge\">成熟度:{self._safe_text(project.get('maturity_level', '-'))}</span>",
            f"<span class=\"badge\">私有化:{self._safe_text(project.get('private_deploy_fit', '-'))}</span>",
        ]

        if project.get("is_model_service_project"):
            focus = self._safe_text(project.get("model_service_focus", "Not-clear"))
            badges.append(f"<span class=\"badge\">模型服务:{focus}</span>")

        language = self._safe_text(project.get("language", ""))
        if language:
            badges.append(f"<span class=\"badge\">语言:{language}</span>")

        return "".join(badges)

    def _render_list(self, items: List[str]) -> str:
        if not items:
            return "<span class=\"muted\">无</span>"
        return "<ul class=\"list\">" + "".join([f"<li>{self._safe_text(item)}</li>" for item in items]) + "</ul>"

    def _render_project_details(self, projects: List[Dict]) -> str:
        if not projects:
            return """    <div class=\"section\">
      <h2 class=\"section-title\">项目详情</h2>
      <p class=\"muted\">暂无可展开的项目详情。</p>
    </div>"""

        blocks: List[str] = []
        for project in projects:
            rank = project.get("rank", "-")
            repo_name = self._safe_text(project.get("repo_name", ""))
            summary = self._safe_text(project.get("summary", "") or project.get("description", ""))
            url = self._safe_text(project.get("url", ""))

            tags = self._as_list(project.get("tags", []))
            tag_text = "、".join([self._safe_text(tag) for tag in tags[:12]]) if tags else "-"

            blocks.append(
                f"""      <details class=\"project\">
        <summary>#{rank} {repo_name} ｜ {summary or '点击展开查看详情'}</summary>
        <div class=\"detail-body\">
          <div style=\"margin-bottom:8px;\"><a class=\"repo-link\" href=\"{url}\">{url}</a></div>
          <div>{self._render_badges(project)}</div>

          <table class=\"detail-grid\" role=\"presentation\">
            <tr>
              <td>摘要</td>
              <td>{self._safe_multiline(project.get('summary', '') or '-')}</td>
            </tr>
            <tr>
              <td>详细描述</td>
              <td>{self._safe_multiline(project.get('description', '') or '-')}</td>
            </tr>
            <tr>
              <td>使用场景</td>
              <td>{self._safe_multiline(project.get('use_case', '') or '-')}</td>
            </tr>
            <tr>
              <td>商业价值依据</td>
              <td>{self._safe_multiline(project.get('commercial_value_reason', '') or '-')}</td>
            </tr>
            <tr>
              <td>领域门槛依据</td>
              <td>{self._safe_multiline(project.get('domain_barrier_reason', '') or '-')}</td>
            </tr>
            <tr>
              <td>Tags</td>
              <td>{tag_text}</td>
            </tr>
          </table>

          <div class=\"block-title\">机会点</div>
          {self._render_list(project.get('infra_transformation_opportunities', []))}

          <div class=\"block-title\">已实现功能</div>
          {self._render_list(project.get('implemented_features', []))}

          <div class=\"block-title\">当前问题</div>
          {self._render_list(project.get('current_issues', []))}

          <div class=\"block-title\">Roadmap 线索</div>
          {self._render_list(project.get('roadmap_signals', []))}

          <div class=\"block-title\">未来方向</div>
          {self._render_list(project.get('future_directions', []))}
        </div>
      </details>"""
            )

        return f"""    <div class=\"section\">
      <h2 class=\"section-title\">项目详情</h2>
{''.join(blocks)}
    </div>"""

    def _render_trend_table(self, title: str, repos: List[Dict], show_delta: bool = False, show_updated: bool = False) -> str:
        if not repos:
            return ""

        rows: List[str] = []
        for repo in repos[:20]:
            rank = repo.get("rank", "-")
            repo_name = self._safe_text(repo.get("repo_name", ""))
            url = self._safe_text(repo.get("url", ""))
            stars = format_number(int(repo.get("stars", 0) or 0))

            extra = "-"
            if show_delta:
                delta = int(repo.get("stars_delta", 0) or 0)
                extra = f"+{format_number(delta)}" if delta >= 0 else format_number(delta)
            elif show_updated:
                updated = str(repo.get("updated_at", "") or "")
                extra = self._safe_text(updated.split("T")[0] if updated else "-")

            rows.append(
                f"""        <tr>
          <td>{rank}</td>
          <td><a class=\"repo-link\" href=\"{url}\">{repo_name}</a></td>
          <td>{stars}</td>
          <td>{extra}</td>
        </tr>"""
            )

        extra_header = "增量" if show_delta else ("更新" if show_updated else "备注")

        return f"""      <h3 style=\"margin:14px 0 8px;font-size:14px;color:#111827;\">{self._safe_text(title)}</h3>
      <table class=\"table\" role=\"table\">
        <thead>
          <tr>
            <th style=\"width:56px;\">Rank</th>
            <th>项目</th>
            <th style=\"width:88px;\">Stars</th>
            <th style=\"width:88px;\">{extra_header}</th>
          </tr>
        </thead>
        <tbody>
{''.join(rows)}
        </tbody>
      </table>"""

    def _render_compact_trends(self, trends: Dict) -> str:
        """保留趋势附录，改为紧凑表格。"""
        parts: List[str] = []

        rising = trends.get("rising_top5", [])
        if rising:
            parts.append(self._render_trend_table("星标增长 Top", rising, show_delta=True))

        new_entries = trends.get("new_entries", [])
        if new_entries:
            parts.append(self._render_trend_table("新晋项目", new_entries))

        active = trends.get("active", [])
        if active:
            parts.append(self._render_trend_table("活跃项目", active, show_updated=True))

        if not parts:
            return ""

        return f"""    <div class=\"section\">
      <h2 class=\"section-title\">趋势附录（紧凑）</h2>
{''.join(parts)}
    </div>"""


def generate_email_html(
    trends: Dict,
    date: str,
    theme: str = "blue",
    report: Optional[Dict] = None,
    single_repo_mode: bool = False,
) -> str:
    """便捷函数：生成邮件 HTML。"""
    reporter = EmailReporter(theme)
    return reporter.generate_email_html(
        trends=trends,
        date=date,
        report=report,
        single_repo_mode=single_repo_mode,
    )
