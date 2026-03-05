"""机会报表内容构建器。"""

from typing import Dict, List


def build_opportunity_report_markdown(report: Dict) -> str:
    """构建目标机会报表 Markdown 内容。"""
    lines: List[str] = []
    date = report.get("date", "")
    min_level = report.get("min_level", "strong")

    lines.append(f"# 目标机会报表 - {date}")
    lines.append("")
    lines.append(f"- 商业价值阈值: `{min_level}`")
    lines.append(f"- 扫描项目数: `{report.get('total_scanned', 0)}`")
    lines.append(f"- 候选项目数: `{report.get('total_candidates', 0)}`")
    lines.append(f"- Strong: `{report.get('strong_count', 0)}` | Weak: `{report.get('weak_count', 0)}`")
    lines.append("")

    projects = report.get("projects", [])
    if not projects:
        lines.append("> 当前阈值下暂无可推送候选项目")
        return "\n".join(lines)

    lines.append("| Rank | Repo | Stars | Domain | Barrier | Maturity | Value |")
    lines.append("| --- | --- | ---: | --- | --- | --- | --- |")
    for project in projects:
        lines.append(
            f"| {project.get('rank', '')} | {project.get('repo_name', '')} | {project.get('stars', 0)} | "
            f"{project.get('domain', '')} | {project.get('domain_barrier_level', '')} | "
            f"{project.get('maturity_level', '')} | {project.get('commercial_value_level', '')} |"
        )

    lines.append("")
    lines.append("## 项目详情")
    lines.append("")

    for project in projects:
        lines.append(f"### {project.get('rank', '')}. {project.get('repo_name', '')}")
        if project.get("url"):
            lines.append(f"- URL: {project['url']}")
        lines.append(f"- 摘要: {project.get('summary', '')}")
        lines.append(
            f"- 商业价值: `{project.get('commercial_value_level', '')}` "
            f"(私有化适配: `{project.get('private_deploy_fit', '')}`)"
        )
        lines.append(f"- 商业价值依据: {project.get('commercial_value_reason', '')}")

        opportunities = project.get("infra_transformation_opportunities", []) or []
        features = project.get("implemented_features", []) or []
        issues = project.get("current_issues", []) or []
        roadmap = project.get("roadmap_signals", []) or []
        directions = project.get("future_directions", []) or []

        lines.append(f"- 机会点: {'；'.join(opportunities[:3]) if opportunities else '无'}")
        lines.append(f"- 已实现: {'；'.join(features[:3]) if features else '无'}")
        lines.append(f"- 当前问题: {'；'.join(issues[:3]) if issues else '无'}")
        lines.append(f"- Roadmap 线索: {'；'.join(roadmap[:3]) if roadmap else '无'}")
        lines.append(f"- 未来方向: {'；'.join(directions[:3]) if directions else '无'}")
        lines.append("")

    return "\n".join(lines)
