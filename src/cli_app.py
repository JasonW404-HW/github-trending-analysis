"""CLI 应用层：负责命令执行编排。"""

import traceback
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from src.config import (
    ANALYSIS_CUSTOM_PROMPT,
    ANALYSIS_KEYWORDS,
    ANALYSIS_KEYWORD_MATCH_MODE,
    DB_PATH,
    DB_RETENTION_DAYS,
    EMAIL_TO,
    GITHUB_CACHE_MINUTES,
    GITHUB_TOKEN,
    OUTPUT_DIR,
    PUSH_MIN_COMMERCIAL_LEVEL,
    RESEND_API_KEY,
    RESEND_FROM_EMAIL,
    TOPIC,
    TOP_N_REPOS_FOR_DETAILS,
    TOP_N_REPOS_FOR_LLM,
    MODEL,
)
from src.infrastructure.database import Database
from src.email import ResendSender
from src.web import EmailReporter
from src.pipeline import AnalysisRunResult, RepoSelectionResult, TrendingWorkflow
from src.util.print_util import banner, logger
from src.infrastructure.web_generator import WebGenerator


def print_banner() -> None:
    """打印程序横幅。"""
    banner_text = (
        "GitHub Topics Trending Following System\n\n"
        "GitHub API Data Fetching · AI Analysis\n"
        "Trending Analysis · HTML & Email Report · Static Website"
    )
    logger.info(banner(banner_text, max_width=64))


def get_today_date() -> str:
    """获取今日日期 YYYY-MM-DD。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_environment() -> bool:
    """检查全量任务所需环境变量。"""
    errors: List[str] = []

    if not GITHUB_TOKEN:
        errors.append("GH_TOKEN 环境变量未设置 (请提供 GitHub Personal Access Token)")
    if not MODEL:
        errors.append("MODEL 环境变量未设置 (示例: ollama/gemma3:4b)")
    elif "/" not in MODEL:
        errors.append("MODEL 格式错误 (需为 provider/model，例如 ollama/gemma3:4b)")
    if not RESEND_API_KEY:
        errors.append("RESEND_API_KEY 环境变量未设置 (请提供 Resend API Key)")
    if not EMAIL_TO:
        errors.append("EMAIL_TO 环境变量未设置 (请提供收件人邮箱，多个可用逗号分隔)")

    if errors:
        logger.error("❌ 环境变量配置错误:")
        for error in errors:
            logger.info(f"   - {error}")
        return False

    return True


def print_selection_summary(selection: RepoSelectionResult) -> None:
    """打印仓库筛选摘要。"""
    if selection.keywords:
        logger.info(
            f"   关键词筛选: {selection.selected_count}/{selection.total_count} 命中 "
            f"(mode={selection.match_mode}, keywords={selection.keywords})"
        )
        return

    logger.info(
        f"   分析入选: {selection.selected_count}/{selection.total_count} "
        "(未配置关键词，按排行榜顺序)"
    )


def print_analysis_summary(analysis: AnalysisRunResult) -> None:
    """打印分析执行摘要。"""
    stats = analysis.stats
    logger.info(f"   缓存命中: {stats.cached_count} 个，待分析: {stats.pending_count} 个")
    logger.info(f"   新增分析成功: {stats.success_count} 个，降级: {stats.fallback_count} 个")


def _build_email_report_payload(date: str, projects: List[dict]) -> dict:
    """构建邮件报表数据负载。"""
    strong_count = len(
        [
            project
            for project in projects
            if str(project.get("commercial_value_level", "")).lower() == "strong"
        ]
    )
    weak_count = len(
        [
            project
            for project in projects
            if str(project.get("commercial_value_level", "")).lower() == "weak"
        ]
    )

    return {
        "date": date,
        "min_level": PUSH_MIN_COMMERCIAL_LEVEL,
        "total_candidates": len(projects),
        "strong_count": strong_count,
        "weak_count": weak_count,
        "projects": projects,
    }


def _print_runtime_header(today: str) -> None:
    logger.info(f"[目标日期] {today}")
    logger.info(f"[话题标签] #{TOPIC}")
    logger.info(f"[缓存周期] {GITHUB_CACHE_MINUTES} 分钟")
    logger.info(f"[推送阈值] 商业价值 >= {PUSH_MIN_COMMERCIAL_LEVEL}")
    if ANALYSIS_KEYWORDS:
        logger.info(
            f"[检索关键词] {ANALYSIS_KEYWORDS} "
            f"(mode={ANALYSIS_KEYWORD_MATCH_MODE})"
        )
    if ANALYSIS_CUSTOM_PROMPT:
        logger.info("[分析Prompt] 已启用自定义提示词")


def _normalize_repo_identifier(raw_value: str) -> Optional[str]:
    """标准化仓库标识，支持 owner/repo 与 GitHub URL。"""
    value = (raw_value or "").strip()
    if not value:
        return None

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None

        parts = [part for part in (parsed.path or "").split("/") if part]
        if len(parts) < 2:
            return None

        owner, repo = parts[0], parts[1]
    else:
        normalized = value.rstrip("/")
        if normalized.endswith(".git"):
            normalized = normalized[:-4]

        if normalized.count("/") != 1:
            return None

        owner, repo = normalized.split("/", 1)

    owner = owner.strip()
    repo = repo.strip()
    if repo.endswith(".git"):
        repo = repo[:-4].strip()

    if not owner or not repo:
        return None

    return f"{owner}/{repo}"


def _extract_repo_argument(args: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """提取并校验 --repo 参数。"""
    repo_values: List[str] = []
    index = 0

    while index < len(args):
        argument = args[index]

        if argument == "--repo":
            if index + 1 >= len(args):
                return None, "参数 --repo 缺少仓库值（示例: owner/repo）"

            value = args[index + 1].strip()
            if not value or value.startswith("--"):
                return None, "参数 --repo 缺少仓库值（示例: owner/repo）"

            repo_values.append(value)
            index += 2
            continue

        if argument.startswith("--repo="):
            value = argument.split("=", 1)[1].strip()
            if not value:
                return None, "参数 --repo 缺少仓库值（示例: owner/repo）"
            repo_values.append(value)

        index += 1

    if not repo_values:
        return None, None

    if len(repo_values) > 1:
        return None, "参数 --repo 仅允许指定一次"

    normalized = _normalize_repo_identifier(repo_values[0])
    if not normalized:
        return None, "仓库格式无效，请使用 owner/repo 或 GitHub URL"

    return normalized, None


def run_daily_command() -> int:
    """执行全量任务。"""
    print_banner()

    if not check_environment():
        return 1

    today = get_today_date()
    _print_runtime_header(today)
    logger.info(f"   (UTC 时间: {datetime.now(timezone.utc)})")
    logger.info()

    db = Database(DB_PATH)
    db.init_db()
    workflow = TrendingWorkflow(db)

    try:
        logger.info("[步骤 1/8] 获取仓库排行榜（周期+ETag缓存）...")
        today_repos, cache_hit = workflow.fetch_rankings(date=today, limit=100)
        cache_desc = "命中缓存" if cache_hit else "实时拉取"
        logger.info(f"   成功获取 {len(today_repos)} 个仓库 ({cache_desc})")
        logger.info()

        logger.info("[步骤 2/8] 保存抓取快照（分析前落库）...")
        workflow.persist_snapshot(date=today, repos=today_repos)
        logger.info()

        logger.info(
            f"[步骤 3/8] 详情抓取 Top {TOP_N_REPOS_FOR_DETAILS}，"
            f"LLM 分析 Top {TOP_N_REPOS_FOR_LLM}（跳过已落库且未更新）..."
        )
        selection = workflow.select_analysis_targets(
            repos=today_repos,
            top_n=TOP_N_REPOS_FOR_DETAILS,
        )
        print_selection_summary(selection)
        analysis = workflow.analyze_selected(selection)
        print_analysis_summary(analysis)
        logger.info()

        logger.info("[步骤 4/8] 计算趋势...")
        trends = workflow.calculate_trends(today_repos, today, analysis)
        logger.info(f"   Top 20: {len(trends['top_20'])} 个")
        logger.info(f"   上升: {len(trends['rising_top5'])} 个")
        logger.info(f"   新晋: {len(trends['new_entries'])} 个")
        logger.info(f"   跌出: {len(trends['dropped_entries'])} 个")
        logger.info(f"   暴涨: {len(trends['surging'])} 个")
        logger.info(f"   活跃: {len(trends['active'])} 个")
        logger.info()

        logger.info("[步骤 5/8] 生成 HTML 邮件...")
        opportunity_report = db.get_opportunity_report(
            date=today,
            min_level=PUSH_MIN_COMMERCIAL_LEVEL,
            limit=1000,
        )
        email_reporter = EmailReporter()
        html_content = email_reporter.generate_email_html(
            trends,
            today,
            report=opportunity_report,
            single_repo_mode=False,
        )
        logger.info(f"   HTML 长度: {len(html_content)} 字符")
        logger.info()

        logger.info("[步骤 6/8] 发送邮件...")
        sender = ResendSender(RESEND_API_KEY or "")
        result = sender.send_email(
            to=EMAIL_TO or "",
            subject=f"📊 GitHub Topics Daily - #{TOPIC} - {today}",
            html_content=html_content,
            from_email=RESEND_FROM_EMAIL,
        )
        if result["success"]:
            logger.info(f"   ✅ 邮件发送成功! ID: {result['id']}")
        else:
            logger.error(f"   ❌ 邮件发送失败: {result['message']}")
        logger.info()

        logger.info("[步骤 7/8] 生成 GitHub Pages 网站...")
        web_gen = WebGenerator(OUTPUT_DIR)
        web_files = web_gen.generate_all(trends, today, db)
        logger.info(f"   生成 {len(web_files)} 个文件")
        logger.info()

        logger.info(f"[步骤 8/8] 清理 {DB_RETENTION_DAYS} 天前的数据...")
        db.cleanup_old_data(DB_RETENTION_DAYS)
        logger.info()

        completion_banner = banner(
            "\n".join(
                [
                    "✅ 任务完成!",
                    f"日期: {today}",
                    f"话题: #{TOPIC}",
                    f"仓库数: {len(today_repos)}",
                    (
                        f"新晋: {len(trends['new_entries'])} | "
                        f"跌出: {len(trends['dropped_entries'])}"
                    ),
                    f"暴涨: {len(trends['surging'])}",
                ]
            ),
            max_width=64,
        )
        logger.info(completion_banner)
        return 0

    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断")
        return 130
    except Exception as error:
        logger.error(f"\n[错误] 执行过程出错: {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_fetch_only_command() -> int:
    """仅获取和分析数据，不发送邮件。"""
    print_banner()

    today = get_today_date()
    _print_runtime_header(today)
    logger.info()

    db = Database(DB_PATH)
    db.init_db()
    workflow = TrendingWorkflow(db)

    try:
        logger.info("[步骤 1/3] 获取仓库列表（周期+ETag缓存）...")
        repos, cache_hit = workflow.fetch_rankings(date=today, limit=100)
        cache_desc = "命中缓存" if cache_hit else "实时拉取"
        logger.info(f"   成功获取 {len(repos)} 个仓库 ({cache_desc})")
        logger.info()

        logger.info("[步骤 2/3] 保存抓取快照（分析前落库）...")
        workflow.persist_snapshot(date=today, repos=repos)
        logger.info()

        logger.info(
            f"[步骤 3/3] 详情抓取 Top {TOP_N_REPOS_FOR_DETAILS}，"
            f"LLM 分析 Top {TOP_N_REPOS_FOR_LLM}（跳过已落库且未更新）..."
        )
        selection = workflow.select_analysis_targets(
            repos=repos,
            top_n=TOP_N_REPOS_FOR_DETAILS,
        )
        print_selection_summary(selection)
        analysis = workflow.analyze_selected(selection)
        print_analysis_summary(analysis)
        analyzed_count = len([summary for summary in analysis.summary_map.values() if not summary.get("fallback")])
        logger.info(f"   可用分析记录: {len(analysis.summary_map)}（成功分析/缓存: {analyzed_count}）")
        logger.info()

        logger.info(f"✅ 完成! 获取 {len(repos)} 个仓库，输出分析 {len(analysis.summary_map)} 条")
        return 0
    except Exception as error:
        logger.error(f"\n[错误] {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_single_repo_command(repo_identifier: str) -> int:
    """仅分析指定仓库，并发送邮件。"""
    print_banner()

    if not check_environment():
        return 1

    today = get_today_date()
    _print_runtime_header(today)
    logger.info(f"[目标仓库] {repo_identifier}")
    logger.info()

    db = Database(DB_PATH)
    db.init_db()
    workflow = TrendingWorkflow(db)

    try:
        logger.info("[步骤 1/5] 获取目标仓库信息...")
        repo = workflow.fetch_single_repository(repo_identifier)
        if not repo:
            logger.error(f"   ❌ 未找到仓库或无权限访问: {repo_identifier}")
            return 1
        logger.info(f"   成功获取仓库: {repo.get('repo_name', repo_identifier)}")
        logger.info()

        logger.info("[步骤 2/5] 保存仓库快照（写入 daily/history）...")
        workflow.persist_snapshot(date=today, repos=[repo])
        logger.info()

        logger.info("[步骤 3/5] AI 分析目标仓库...")
        selection = RepoSelectionResult(
            repos=[repo],
            total_count=1,
            selected_count=1,
            keywords=[],
            match_mode=ANALYSIS_KEYWORD_MATCH_MODE,
        )
        analysis = workflow.analyze_selected(selection)
        print_analysis_summary(analysis)
        logger.info()

        logger.info("[步骤 4/5] 计算单仓库趋势...")
        trends = workflow.calculate_trends([repo], today, analysis)
        logger.info(
            f"   Top: {len(trends.get('top_20', []))} 个, "
            f"新晋: {len(trends.get('new_entries', []))} 个, "
            f"活跃: {len(trends.get('active', []))} 个"
        )
        logger.info()

        logger.info("[步骤 5/5] 发送邮件...")
        summary = analysis.summary_map.get(repo_identifier) or analysis.summary_map.get(repo.get("repo_name", "")) or {}
        assessment = summary.get("purpose_assessment", {}) if isinstance(summary, dict) else {}
        if not isinstance(assessment, dict):
            assessment = {}

        single_project = {
            "rank": repo.get("rank", 1),
            "repo_name": repo.get("repo_name", repo_identifier),
            "owner": repo.get("owner", ""),
            "stars": repo.get("stars", 0),
            "stars_delta": repo.get("stars_delta", 0),
            "language": repo.get("language", ""),
            "url": repo.get("url", ""),
            "summary": summary.get("summary", ""),
            "description": summary.get("description", ""),
            "use_case": summary.get("use_case", ""),
            "tags": summary.get("tags", []) if isinstance(summary.get("tags", []), list) else [],
            "domain": assessment.get("domain", ""),
            "domain_barrier_level": assessment.get("domain_barrier_level", ""),
            "domain_barrier_reason": assessment.get("domain_barrier_reason", ""),
            "maturity_level": assessment.get("maturity_level", ""),
            "is_model_service_project": bool(assessment.get("is_model_service_project", False)),
            "model_service_focus": assessment.get("model_service_focus", ""),
            "commercial_value_level": assessment.get("commercial_value_level", "none"),
            "commercial_value_reason": assessment.get("commercial_value_reason", ""),
            "recommended_for_push": bool(assessment.get("recommended_for_push", True)),
            "private_deploy_fit": assessment.get("private_deploy_fit", ""),
            "implemented_features": assessment.get("implemented_features", []) or [],
            "current_issues": assessment.get("current_issues", []) or [],
            "roadmap_signals": assessment.get("roadmap_signals", []) or [],
            "future_directions": assessment.get("future_directions", []) or [],
            "infra_transformation_opportunities": assessment.get("infra_transformation_opportunities", []) or [],
        }

        email_report = _build_email_report_payload(today, [single_project])
        email_reporter = EmailReporter()
        html_content = email_reporter.generate_email_html(
            trends,
            today,
            report=email_report,
            single_repo_mode=True,
        )

        sender = ResendSender(RESEND_API_KEY or "")
        result = sender.send_email(
            to=EMAIL_TO or "",
            subject=f"📊 GitHub Repo Focus - {repo_identifier} - {today}",
            html_content=html_content,
            from_email=RESEND_FROM_EMAIL,
        )

        if result["success"]:
            logger.info(f"   ✅ 邮件发送成功! ID: {result['id']}")
        else:
            logger.error(f"   ❌ 邮件发送失败: {result['message']}")

        logger.info()
        logger.info(f"✅ 完成! 已分析仓库: {repo_identifier}")
        return 0
    except Exception as error:
        logger.error(f"\n[错误] 单仓库模式执行失败: {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_opportunity_report_command() -> int:
    """仅输出目标机会报表，不执行抓取与分析。"""
    print_banner()

    date = get_today_date()
    logger.info(f"[报表日期] {date}")
    logger.info(f"[推送阈值] 商业价值 >= {PUSH_MIN_COMMERCIAL_LEVEL}")
    logger.info()

    db = Database(DB_PATH)
    db.init_db()

    try:
        report = db.get_opportunity_report(date=date, min_level=PUSH_MIN_COMMERCIAL_LEVEL, limit=50)

        logger.info("[目标机会报表]")
        logger.info(f"   扫描项目: {report['total_scanned']}")
        logger.info(f"   候选项目: {report['total_candidates']}")
        logger.info(f"   Strong: {report['strong_count']} | Weak: {report['weak_count']}")
        logger.info()

        projects = report.get("projects", [])
        if not projects:
            logger.info("   当前阈值下暂无可推送候选项目")
        else:
            for project in projects[:20]:
                opportunities = project.get("infra_transformation_opportunities", []) or []
                logger.info(
                    f"   #{project.get('rank')} {project.get('repo_name')} "
                    f"[{project.get('commercial_value_level')}]"
                )
                logger.info(
                    f"      领域={project.get('domain', '-')}, 门槛={project.get('domain_barrier_level', '-')}, "
                    f"成熟度={project.get('maturity_level', '-')}, Stars={project.get('stars', 0)}"
                )
                if opportunities:
                    logger.info(f"      机会点: {'；'.join(opportunities[:2])}")

        reporter = EmailReporter()
        report_html = reporter.generate_email_html(
            trends={"top_20": []},
            date=date,
            report=report,
            single_repo_mode=False,
        )
        output_path = OUTPUT_DIR
        web_gen = WebGenerator(output_path)
        preview_path = web_gen.output_dir / "exports" / f"opportunity-report-{date}.html"
        preview_path.write_text(report_html, encoding="utf-8")
        logger.info()
        logger.info(f"✅ 报表预览已生成: {preview_path}")
        return 0
    except Exception as error:
        logger.error(f"\n[错误] 报表生成失败: {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_cli(args: List[str]) -> int:
    """CLI 路由分发。"""
    repo_identifier, repo_error = _extract_repo_argument(args)
    if repo_error:
        logger.error(f"❌ 参数错误: {repo_error}")
        logger.info("   用法: uv run main.py --repo owner/repo")
        logger.info("   或:  uv run main.py --repo https://github.com/owner/repo")
        return 2

    has_fetch_only = "--fetch-only" in args
    has_opportunity_report = "--opportunity-report" in args

    if repo_identifier and (has_fetch_only or has_opportunity_report):
        logger.error("❌ 参数冲突: --repo 不能与 --fetch-only 或 --opportunity-report 同时使用")
        return 2

    if repo_identifier:
        return run_single_repo_command(repo_identifier)

    if has_fetch_only:
        return run_fetch_only_command()
    if has_opportunity_report:
        return run_opportunity_report_command()
    return run_daily_command()
