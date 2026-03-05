"""CLI 应用层：负责命令执行编排。"""

import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from src.application.opportunity_report_builder import build_opportunity_report_markdown
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
    TOP_N_DETAILS,
    ZHIPU_API_KEY,
)
from src.database import Database
from src.email_reporter import EmailReporter
from src.pipeline.contracts import AnalysisRunResult, RepoSelectionResult
from src.pipeline.workflows import TrendingWorkflow
from src.resend import ResendSender
from src.web_generator import WebGenerator


def print_banner() -> None:
    """打印程序横幅。"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   GitHub Topics Trending Following System                    ║
║                                                              ║
║   GitHub API Data Fetching · AI Analysis                     ║
║   Trending Analysis · HTML & Email Report · Static Website   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def get_today_date() -> str:
    """获取今日日期 YYYY-MM-DD。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_environment() -> bool:
    """检查全量任务所需环境变量。"""
    errors: List[str] = []

    if not GITHUB_TOKEN:
        errors.append("GH_TOKEN 环境变量未设置 (请提供 GitHub Personal Access Token)")
    if not ZHIPU_API_KEY:
        errors.append("ZHIPU_API_KEY 环境变量未设置 (请提供 Claude API Key)")
    if not RESEND_API_KEY:
        errors.append("RESEND_API_KEY 环境变量未设置 (请提供 Resend API Key)")
    if not EMAIL_TO:
        errors.append("EMAIL_TO 环境变量未设置 (请提供收件人邮箱)")

    if errors:
        print("❌ 环境变量配置错误:")
        for error in errors:
            print(f"   - {error}")
        return False

    return True


def print_selection_summary(selection: RepoSelectionResult) -> None:
    """打印仓库筛选摘要。"""
    if selection.keywords:
        print(
            f"   关键词筛选: {selection.selected_count}/{selection.total_count} 命中 "
            f"(mode={selection.match_mode}, keywords={selection.keywords})"
        )
        return

    print(
        f"   分析入选: {selection.selected_count}/{selection.total_count} "
        "(未配置关键词，按排行榜顺序)"
    )


def print_analysis_summary(analysis: AnalysisRunResult) -> None:
    """打印分析执行摘要。"""
    stats = analysis.stats
    print(f"   缓存命中: {stats.cached_count} 个，待分析: {stats.pending_count} 个")
    print(f"   新增分析成功: {stats.success_count} 个，降级: {stats.fallback_count} 个")


def _print_runtime_header(today: str) -> None:
    print(f"[目标日期] {today}")
    print(f"[话题标签] #{TOPIC}")
    print(f"[缓存周期] {GITHUB_CACHE_MINUTES} 分钟")
    print(f"[推送阈值] 商业价值 >= {PUSH_MIN_COMMERCIAL_LEVEL}")
    if ANALYSIS_KEYWORDS:
        print(
            f"[检索关键词] {ANALYSIS_KEYWORDS} "
            f"(mode={ANALYSIS_KEYWORD_MATCH_MODE})"
        )
    if ANALYSIS_CUSTOM_PROMPT:
        print("[分析Prompt] 已启用自定义提示词")


def run_daily_command() -> int:
    """执行全量任务。"""
    print_banner()

    if not check_environment():
        return 1

    today = get_today_date()
    _print_runtime_header(today)
    print(f"   (UTC 时间: {datetime.now(timezone.utc)})")
    print()

    db = Database(DB_PATH)
    db.init_db()
    workflow = TrendingWorkflow(db)

    try:
        print("[步骤 1/8] 获取仓库排行榜（周期+ETag缓存）...")
        today_repos, cache_hit = workflow.fetch_rankings(date=today, limit=100)
        cache_desc = "命中缓存" if cache_hit else "实时拉取"
        print(f"   成功获取 {len(today_repos)} 个仓库 ({cache_desc})")
        print()

        print("[步骤 2/8] 保存抓取快照（分析前落库）...")
        workflow.persist_snapshot(date=today, repos=today_repos)
        print()

        print(f"[步骤 3/8] AI 分析 Top {TOP_N_DETAILS}（跳过已落库且未更新）...")
        selection = workflow.select_analysis_targets(repos=today_repos, top_n=TOP_N_DETAILS)
        print_selection_summary(selection)
        analysis = workflow.analyze_selected(selection)
        print_analysis_summary(analysis)
        print()

        print("[步骤 4/8] 计算趋势...")
        trends = workflow.calculate_trends(today_repos, today, analysis)
        print(f"   Top 20: {len(trends['top_20'])} 个")
        print(f"   上升: {len(trends['rising_top5'])} 个")
        print(f"   新晋: {len(trends['new_entries'])} 个")
        print(f"   跌出: {len(trends['dropped_entries'])} 个")
        print(f"   暴涨: {len(trends['surging'])} 个")
        print(f"   活跃: {len(trends['active'])} 个")
        print()

        print("[步骤 5/8] 生成 HTML 邮件...")
        email_reporter = EmailReporter()
        html_content = email_reporter.generate_email_html(trends, today)
        print(f"   HTML 长度: {len(html_content)} 字符")
        print()

        print("[步骤 6/8] 发送邮件...")
        sender = ResendSender(RESEND_API_KEY or "")
        result = sender.send_email(
            to=EMAIL_TO or "",
            subject=f"📊 GitHub Topics Daily - #{TOPIC} - {today}",
            html_content=html_content,
            from_email=RESEND_FROM_EMAIL,
        )
        if result["success"]:
            print(f"   ✅ 邮件发送成功! ID: {result['id']}")
        else:
            print(f"   ❌ 邮件发送失败: {result['message']}")
        print()

        print("[步骤 7/8] 生成 GitHub Pages 网站...")
        web_gen = WebGenerator(OUTPUT_DIR)
        web_files = web_gen.generate_all(trends, today, db)
        print(f"   生成 {len(web_files)} 个文件")
        print()

        print(f"[步骤 8/8] 清理 {DB_RETENTION_DAYS} 天前的数据...")
        db.cleanup_old_data(DB_RETENTION_DAYS)
        print()

        print("╔════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print("║   ✅ 任务完成!                                              ║")
        print("║                                                              ║")
        print(f"║   日期: {today}                                            ║")
        print(f"║   话题: #{TOPIC}                                            ║")
        print(f"║   仓库数: {len(today_repos)}                                    ║")
        print(f"║   新晋: {len(trends['new_entries'])} | 跌出: {len(trends['dropped_entries'])}                         ║")
        print(f"║   暴涨: {len(trends['surging'])}                                                ║")
        print("║                                                              ║")
        print("╚════════════════════════════════════════════════════════════╝")
        return 0

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        return 130
    except Exception as error:
        print(f"\n[错误] 执行过程出错: {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_fetch_only_command() -> int:
    """仅获取和分析数据，不发送邮件。"""
    print_banner()

    today = get_today_date()
    _print_runtime_header(today)
    print()

    db = Database(DB_PATH)
    db.init_db()
    workflow = TrendingWorkflow(db)

    try:
        print("[步骤 1/3] 获取仓库列表（周期+ETag缓存）...")
        repos, cache_hit = workflow.fetch_rankings(date=today, limit=100)
        cache_desc = "命中缓存" if cache_hit else "实时拉取"
        print(f"   成功获取 {len(repos)} 个仓库 ({cache_desc})")
        print()

        print("[步骤 2/3] 保存抓取快照（分析前落库）...")
        workflow.persist_snapshot(date=today, repos=repos)
        print()

        print(f"[步骤 3/3] AI 分析 Top {TOP_N_DETAILS}（跳过已落库且未更新）...")
        selection = workflow.select_analysis_targets(repos=repos, top_n=TOP_N_DETAILS)
        print_selection_summary(selection)
        analysis = workflow.analyze_selected(selection)
        print_analysis_summary(analysis)
        analyzed_count = len([summary for summary in analysis.summary_map.values() if not summary.get("fallback")])
        print(f"   可用分析记录: {len(analysis.summary_map)}（成功分析/缓存: {analyzed_count}）")
        print()

        print(f"✅ 完成! 获取 {len(repos)} 个仓库，输出分析 {len(analysis.summary_map)} 条")
        return 0
    except Exception as error:
        print(f"\n[错误] {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_opportunity_report_command() -> int:
    """仅输出目标机会报表，不执行抓取与分析。"""
    print_banner()

    date = get_today_date()
    print(f"[报表日期] {date}")
    print(f"[推送阈值] 商业价值 >= {PUSH_MIN_COMMERCIAL_LEVEL}")
    print()

    db = Database(DB_PATH)
    db.init_db()

    try:
        report = db.get_opportunity_report(date=date, min_level=PUSH_MIN_COMMERCIAL_LEVEL, limit=50)

        print("[目标机会报表]")
        print(f"   扫描项目: {report['total_scanned']}")
        print(f"   候选项目: {report['total_candidates']}")
        print(f"   Strong: {report['strong_count']} | Weak: {report['weak_count']}")
        print()

        projects = report.get("projects", [])
        if not projects:
            print("   当前阈值下暂无可推送候选项目")
        else:
            for project in projects[:20]:
                opportunities = project.get("infra_transformation_opportunities", []) or []
                print(
                    f"   #{project.get('rank')} {project.get('repo_name')} "
                    f"[{project.get('commercial_value_level')}]"
                )
                print(
                    f"      领域={project.get('domain', '-')}, 门槛={project.get('domain_barrier_level', '-')}, "
                    f"成熟度={project.get('maturity_level', '-')}, Stars={project.get('stars', 0)}"
                )
                if opportunities:
                    print(f"      机会点: {'；'.join(opportunities[:2])}")

        report_content = build_opportunity_report_markdown(report)
        report_dir = Path("data") / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"opportunity-report-{date}.md"
        report_path.write_text(report_content, encoding="utf-8")
        print()
        print(f"✅ 报表已生成: {report_path}")
        return 0
    except Exception as error:
        print(f"\n[错误] 报表生成失败: {error}")
        traceback.print_exc()
        return 1
    finally:
        db.close()


def run_cli(args: List[str]) -> int:
    """CLI 路由分发。"""
    if args and args[0] == "--fetch-only":
        return run_fetch_only_command()
    if args and args[0] == "--opportunity-report":
        return run_opportunity_report_command()
    return run_daily_command()
