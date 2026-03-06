# GitHub Topics Trending

追踪 GitHub 话题下的热门项目趋势，AI 智能分析，每日趋势报告。

## 功能

- **数据采集**: 使用 GitHub API 按话题获取热门仓库
- **AI 分析**: 使用 LiteLLM 网关对仓库进行智能分类和摘要
- **趋势计算**: 计算星标变化、新晋项目、活跃项目等趋势
- **邮件报告**: 发送专业的 HTML 邮件报告
- **静态网站**: 生成 GitHub Pages 静态展示页面

## 使用方法

### 查看今日趋势

```bash
# 查看指定话题的趋势
cd /path/to/github-topics-trending
uv run main.py
```

### 仅获取数据

```bash
# 不发送邮件，仅获取和分析数据
uv run main.py --fetch-only

# 输出目标机会报表（基于已落库数据）
uv run main.py --opportunity-report
```

## 环境变量配置

| 变量 | 说明 | 必需 |
|------|------|------|
| `GH_TOKEN` | GitHub Personal Access Token | 是 |
| `TOPIC` | 要追踪的 GitHub Topic (默认: claude-code) | 否 |
| `MODEL_PROVIDER` | 模型供应商（如 MOONSHOT） | 是 |
| `MODEL_TOKEN` | 模型供应商 API Token | 是 |
| `MODEL_NAME` | 模型名称（如 moonshot/moonshot-v1-8k） | 是 |
| `MODEL_BASE_URL` | 供应商 Base URL（可留空） | 否 |
| `RESEND_API_KEY` | Resend 邮件服务 API Key | 是 |
| `EMAIL_TO` | 收件人邮箱（多个用逗号分隔） | 是 |
| `RESEND_FROM_EMAIL` | 发件人邮箱 | 否 |
| `DB_PATH` | 数据库路径 (默认: data/github-trending.db) | 否 |
| `DB_RETENTION_DAYS` | 数据保留天数 (默认: 90) | 否 |
| `GITHUB_CACHE_MINUTES` | GitHub 抓取缓存周期（分钟，默认: 30） | 否 |
| `MODEL_MAX_CONCURRENCY` | 模型请求最大并发（默认: 4） | 否 |
| `MODEL_MAX_RPM` | 模型请求每分钟上限（默认: 80） | 否 |
| `ANALYSIS_KEYWORDS` | 检索关键词（逗号分隔） | 否 |
| `ANALYSIS_KEYWORD_MATCH_MODE` | 关键词匹配模式（any/all，默认: any） | 否 |
| `ANALYSIS_CUSTOM_PROMPT` | 自定义模型分析提示词 | 否 |
| `PUSH_MIN_COMMERCIAL_LEVEL` | 商业价值推送阈值（strong/weak，默认: strong） | 否 |
| `HTTP_429_COOLDOWN_SECONDS` | 429 冷却秒数（默认: 60） | 否 |
| `HTTP_429_MAX_RETRIES` | 429 最大重试次数（默认: 3） | 否 |

## 仓库分类

- **插件**: Claude Code / VS Code 插件
- **工具**: 开发工具、CLI 工具
- **模板**: 项目模板、脚手架
- **文档**: 教程、文档、书籍
- **示例**: Demo 项目、示例代码
- **集成**: 集成工具、包装器
- **库**: Python/JS/其他库
- **应用**: 完整应用
- **其他**: 无法分类

## 输出内容

### 邮件报告包含

- Top 20 经典榜单
- 星标增长 Top 5
- 新晋项目
- 活跃项目
- 趋势统计

### 静态网站包含

- 首页
- 每日趋势页
- 分类浏览页
- 仓库详情页

## 相关链接

- GitHub: https://github.com/topics/claude-code
- API 文档: https://docs.github.com/en/rest
