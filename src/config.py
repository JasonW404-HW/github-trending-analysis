"""
配置模块 - GitHub Topics Trending 配置管理
"""
import os
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ============================================================================
# OpenAI API 配置 (兼容 Kimi/New API)
# ============================================================================
ANTHROPIC_BASE_URL = os.getenv(
    "ANTHROPIC_BASE_URL",
    "https://open.bigmodel.cn/api/anthropic"
)
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")

# Claude 模型配置
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
CLAUDE_MAX_TOKENS = 8192

# ============================================================================
# GitHub API 配置
# ============================================================================
GITHUB_TOKEN = os.getenv("GH_TOKEN")
TOPIC = os.getenv("TOPIC", "claude-code")
GITHUB_API_BASE = "https://api.github.com"
GITHUB_PER_PAGE = 100  # GitHub API max per page
GITHUB_MAX_PAGES = 10  # Maximum pages to fetch (1000 repos)

# GitHub 搜索配置
GITHUB_SEARCH_SORT = "stars"  # stars, forks, updated
GITHUB_SEARCH_ORDER = "desc"  # desc, asc

# ============================================================================
# 邮件通知配置
# ============================================================================
def _get_env_int(key: str, default: int) -> int:
    """获取整数环境变量，处理空字符串情况"""
    value = os.getenv(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_positive_int(key: str, default: int, minimum: int = 1) -> int:
    """获取正整数环境变量，处理空字符串和非法值"""
    value = _get_env_int(key, default)
    return max(minimum, value)


def _get_env_list(key: str) -> list[str]:
    """获取逗号分隔的字符串列表环境变量"""
    value = os.getenv(key, "")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = _get_env_int("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFICATION_TO = os.getenv("NOTIFICATION_TO")

# ============================================================================
# Resend 邮件配置
# ============================================================================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
EMAIL_TO = os.getenv("EMAIL_TO")

# ============================================================================
# 数据库配置
# ============================================================================
DB_PATH = os.getenv("DB_PATH", "data/github-trending.db")
DB_RETENTION_DAYS = _get_env_int("DB_RETENTION_DAYS", 90)

# ============================================================================
# GitHub Pages 配置
# ============================================================================
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "docs")
GITHUB_PAGES_URL = os.getenv("GITHUB_PAGES_URL", "")

# ============================================================================
# 告警阈值
# ============================================================================
def _get_env_float(key: str, default: float) -> float:
    """获取浮点数环境变量，处理空字符串和无效值情况"""
    value = os.getenv(key)
    if value is None or value == "":
        return default
    try:
        result = float(value)
        return max(0.0, min(1.0, result))  # 限制在 0-1 范围
    except ValueError:
        return default


SURGE_THRESHOLD = _get_env_float("SURGE_THRESHOLD", 0.3)  # 30% 暴涨阈值

# ============================================================================
# 采集配置
# ============================================================================
TOP_N_DETAILS = 50  # AI 分析数量
FETCH_REQUEST_DELAY = 0.5  # API 请求间隔（秒）
GITHUB_CACHE_MINUTES = _get_env_positive_int("GITHUB_CACHE_MINUTES", 30)

# 关键词检索 + 自定义分析 Prompt（通过配置文件设置）
ANALYSIS_KEYWORDS = _get_env_list("ANALYSIS_KEYWORDS")
ANALYSIS_CUSTOM_PROMPT = (os.getenv("ANALYSIS_CUSTOM_PROMPT") or "").strip()
ANALYSIS_KEYWORD_MATCH_MODE = (os.getenv("ANALYSIS_KEYWORD_MATCH_MODE") or "any").strip().lower()
if ANALYSIS_KEYWORD_MATCH_MODE not in {"any", "all"}:
    ANALYSIS_KEYWORD_MATCH_MODE = "any"

# 邮件推送商业价值阈值：strong（仅强商业价值）或 weak（包含较弱商业价值）
PUSH_MIN_COMMERCIAL_LEVEL = (os.getenv("PUSH_MIN_COMMERCIAL_LEVEL") or "strong").strip().lower()
if PUSH_MIN_COMMERCIAL_LEVEL not in {"strong", "weak"}:
    PUSH_MIN_COMMERCIAL_LEVEL = "strong"

# ============================================================================
# 模型请求限流配置
# ============================================================================
MODEL_MAX_CONCURRENCY = _get_env_positive_int("MODEL_MAX_CONCURRENCY", 4)
MODEL_MAX_RPM = _get_env_positive_int("MODEL_MAX_RPM", 80)

# ============================================================================
# 全链路 429 重试配置
# ============================================================================
HTTP_429_COOLDOWN_SECONDS = _get_env_positive_int("HTTP_429_COOLDOWN_SECONDS", 60)
HTTP_429_MAX_RETRIES = _get_env_positive_int("HTTP_429_MAX_RETRIES", 3, minimum=0)

# ============================================================================
# 仓库分类定义
# ============================================================================
CATEGORIES = {
    "plugin": {
        "name": "插件",
        "name_en": "Plugin",
        "icon": "🔌",
        "description": "Claude Code / VS Code 插件"
    },
    "tool": {
        "name": "工具",
        "name_en": "Tool",
        "icon": "🛠️",
        "description": "开发工具、CLI 工具"
    },
    "template": {
        "name": "模板",
        "name_en": "Template",
        "icon": "📋",
        "description": "项目模板、脚手架"
    },
    "docs": {
        "name": "文档",
        "name_en": "Documentation",
        "icon": "📚",
        "description": "教程、文档、书籍"
    },
    "demo": {
        "name": "示例",
        "name_en": "Demo",
        "icon": "🎨",
        "description": "Demo 项目、示例代码"
    },
    "integration": {
        "name": "集成",
        "name_en": "Integration",
        "icon": "🔗",
        "description": "集成工具、包装器"
    },
    "library": {
        "name": "库",
        "name_en": "Library",
        "icon": "📦",
        "description": "Python/JS/其他库"
    },
    "app": {
        "name": "应用",
        "name_en": "Application",
        "icon": "🚀",
        "description": "完整应用"
    },
    "other": {
        "name": "其他",
        "name_en": "Other",
        "icon": "📁",
        "description": "无法分类"
    }
}

# ============================================================================
# 网站元信息
# ============================================================================
SITE_META = {
    "title": "GitHub Topics Trending",
    "subtitle": f"{TOPIC} 话题趋势追踪",
    "description": f"追踪 {TOPIC} 话题下的热门 GitHub 项目，AI 智能分析，每日趋势报告",
    "author": "GitHub Topics Trending",
    "keywords": ["GitHub", "Trending", "Topics", TOPIC, "开源", "排行榜"]
}

# ============================================================================
# 主题配色方案
# ============================================================================
THEMES = {
    "blue": {
        "name": "科技蓝",
        "primary": "#0366d6",
        "secondary": "#58a6ff",
        "bg": "#0d1117",
        "card": "#161b22",
        "text": "#c9d1d9",
        "text_secondary": "#8b949e",
        "border": "#30363d",
        "success": "#238636",
        "warning": "#d29922",
        "danger": "#f85149"
    },
    "indigo": {
        "name": "深靛蓝",
        "primary": "#4f46e5",
        "secondary": "#818cf8",
        "bg": "#0f172a",
        "card": "#1e293b",
        "text": "#e2e8f0",
        "text_secondary": "#94a3b8",
        "border": "#334155",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "danger": "#ef4444"
    },
    "purple": {
        "name": "优雅紫",
        "primary": "#9333ea",
        "secondary": "#a855f7",
        "bg": "#1a0a2e",
        "card": "#2d1b3d",
        "text": "#f3e5f5",
        "text_secondary": "#d1c4e9",
        "border": "#4c1d95",
        "success": "#10b981",
        "warning": "#fbbf24",
        "danger": "#ef4444"
    }
}

DEFAULT_THEME = "blue"


def get_theme(theme_name: Optional[str] = None) -> dict:
    """获取指定主题配置"""
    theme_name = theme_name or DEFAULT_THEME
    return THEMES.get(theme_name, THEMES[DEFAULT_THEME])


def get_category_info(category_key: str) -> dict:
    """获取分类信息"""
    return CATEGORIES.get(category_key, CATEGORIES["other"])


def format_number(num: int) -> str:
    """格式化数字显示"""
    if num >= 1000000:
        return f"{num / 1000000:.1f}M"
    elif num >= 1000:
        return f"{num / 1000:.1f}K"
    return str(num)


def get_repo_url(owner: str, repo_name: str) -> str:
    """生成仓库 URL"""
    return f"https://github.com/{owner}/{repo_name}"
