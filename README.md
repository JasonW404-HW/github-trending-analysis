# GitHub Topics Trending

> 自动追踪 GitHub Topic 热门仓库，进行 AI 总结与商业价值分析，并输出邮件、网页与机会报表。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

---

## 项目简介

本项目每天执行以下流程：

1. 获取指定 GitHub Topic 的热门仓库（支持缓存与 ETag）
2. 获取仓库 README 摘要
3. 调用 LLM 进行结构化总结与商业价值评估
4. 计算趋势数据并输出结论（邮件 / 静态网页 / 机会报表）

适用场景：

- 跟踪某个技术话题的生态变化
- 发现高潜力项目并进行运营复盘
- 自动化生成日报与趋势页面

---

## 功能特性

- GitHub 数据采集：按 Topic 抓取热门仓库，支持缓存周期与 ETag 校验
- README 摘要获取：批量抓取与文本清洗
- LLM 智能分析：结构化输出摘要、分类、标签、purpose_assessment
- 趋势计算：新晋、跌出、活跃、星标增长、暴涨检测
- 多渠道输出：HTML 邮件、GitHub Pages 页面、JSON/CSV/Markdown 报表
- 数据持久化：支持 SQLite / PostgreSQL，存储快照、历史、分析详情

---

## 架构分层

### 1) 入口层

- `main.py`：仅负责 CLI 参数路由

### 2) 应用层

- `src/cli_app.py`：命令执行编排（full / fetch-only / opportunity-report）

### 3) 流程层（Pipeline）

- `src/pipeline/models.py`：运行契约（数据模型）
- `src/pipeline/repository_selection.py`：流程步骤（仓库筛选）
- `src/pipeline/repository_analysis.py`：流程步骤（仓库分析）
- `src/trending_workflow.py`：端到端工作流编排（TrendingWorkflow）

### 4) 基础设施层

- `src/github/fetcher.py`：GitHub API 采集
- `src/github/readme_fetcher.py`：README 获取
- `src/analysis/repository_summarizer.py`：LLM 分析
- `src/analysis/trend_analyzer.py`：趋势分析
- `src/infrastructure/database.py`：SQLite / PostgreSQL 数据访问
- `src/email/reporter.py` / `src/email/sender.py`：邮件内容与发送
- `src/infrastructure/web_generator.py`：静态网页生成

---

## 快速开始

### 环境要求

- Python 3.12+
- uv
- GitHub Personal Access Token
- Model Provider Token（通过 LiteLLM 接入模型服务）
- Resend API Key

### 安装

```bash
git clone <your-repo-url>
cd github-topics-trending
uv sync --frozen
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env`，至少配置：

- `GH_TOKEN`
- `MODEL`（例如 `ollama/gemma3:4b`）
- `RESEND_API_KEY`
- `EMAIL_TO`（支持多个收件人，英文逗号分隔）

`MODEL` 的 provider/model 命名方式请参考：
https://docs.litellm.ai/docs/providers

示例：

```dotenv
EMAIL_TO=alice@example.com,bob@example.com
```

---

## 运行方式

```bash
# 完整流程：抓取 + 分析 + 邮件 + 网页
uv run main.py

# Debug：临时仅分析 2 个项目，降低调试开销
TOP_N_DETAILS=2 uv run main.py --fetch-only

# 单仓库模式：仅针对指定仓库执行分析 + 邮件
uv run main.py --repo CherryHQ/cherry-studio
# 或使用 GitHub URL
uv run main.py --repo https://github.com/CherryHQ/cherry-studio

# 仅抓取与分析
uv run main.py --fetch-only

# 仅生成目标机会报表（基于已落库数据）
uv run main.py --opportunity-report
```

### Ubuntu 定时运行（每天 09:00）

#### 方案 A：`systemd --user timer`（桌面/有用户会话）

```bash
chmod +x scripts/setup_ubuntu_timer.sh

# 安装定时任务（本地时区每天 09:00）
scripts/setup_ubuntu_timer.sh --run-at 09:00

# 查看下一次触发时间
systemctl --user list-timers github-topics-trending.timer --no-pager

# 手动立即执行一次（用于联调）
systemctl --user start github-topics-trending.service

# 查看执行日志
journalctl --user -u github-topics-trending.service -n 200 --no-pager
```

如果希望用户退出登录后依然触发定时任务：

```bash
sudo loginctl enable-linger $USER
```

移除定时任务：

```bash
scripts/setup_ubuntu_timer.sh --uninstall
```

#### 方案 B：`cron`（Ubuntu 服务器/无 user bus 场景）

当执行 `systemctl --user` 报错 `Failed to connect to bus` 时，使用该方案：

```bash
chmod +x scripts/setup_ubuntu_cron.sh

# 安装 cron（本地时区每天 09:00）
scripts/setup_ubuntu_cron.sh --run-at 09:00

# 查看当前托管的 cron 任务
scripts/setup_ubuntu_cron.sh --status

# 移除任务
scripts/setup_ubuntu_cron.sh --uninstall
```

默认日志输出到 `data/logs/scheduler.log`。

---

## 关键配置

| 变量                                   | 必需 | 说明                                 |
| -------------------------------------- | ---- | ------------------------------------ |
| `GH_TOKEN`                             | 是   | GitHub Token                         |
| `TOPIC`                                | 否   | 追踪话题（默认 `ai`）                |
| `MODEL`                                | 是   | 模型标识（格式 `provider/model`）    |
| `LLM_MAX_TOKENS`                       | 否   | 模型最大输出 token                   |
| `RESEND_API_KEY`                       | 是   | Resend API Key                       |
| `EMAIL_TO`                             | 是   | 收件人邮箱（多个用逗号分隔）         |
| `TOP_N_DETAILS`                        | 否   | AI 分析项目上限（debug 可设 2）      |
| `LLM_JSON_REPAIR_RETRIES`              | 否   | JSON 解析失败后修复重试次数          |
| `ANALYSIS_KEYWORDS`                    | 否   | 关键词筛选（逗号分隔）               |
| `ANALYSIS_KEYWORD_MATCH_MODE`          | 否   | `any` / `all`                        |
| `ANALYSIS_CUSTOM_PROMPT`               | 否   | 自定义分析提示词                     |
| `GITHUB_ACTIVITY_WINDOW_DAYS`          | 否   | 分析时纳入的 Issue/PR 窗口天数       |
| `GITHUB_ACTIVITY_ISSUES_LIMIT`         | 否   | 每仓库纳入 Prompt 的 Issue 条数      |
| `GITHUB_ACTIVITY_PRS_LIMIT`            | 否   | 每仓库纳入 Prompt 的 PR 条数         |
| `GITHUB_ACTIVITY_DETAIL_ISSUES_LIMIT`  | 否   | 二阶段深挖的 Issue 条数              |
| `GITHUB_ACTIVITY_DETAIL_PRS_LIMIT`     | 否   | 二阶段深挖的 PR 条数                 |
| `GITHUB_ACTIVITY_DETAIL_LAST_COMMENTS` | 否   | 二阶段每条保留的最后对话条数         |
| `PUSH_MIN_COMMERCIAL_LEVEL`            | 否   | `strong` / `weak`                    |
| `GITHUB_CACHE_MINUTES`                 | 否   | 抓取缓存分钟数                       |
| `DB_BACKEND`                           | 否   | `sqlite` / `postgres`（默认 sqlite） |
| `DB_PATH`                              | 否   | SQLite 文件路径                      |
| `PG_HOST`                              | 否   | PostgreSQL 主机（默认 `localhost`）  |
| `PG_PORT`                              | 否   | PostgreSQL 端口（默认 `5432`）       |
| `PG_DATABASE`                          | 否   | PostgreSQL 数据库名                  |
| `PG_USER`                              | 否   | PostgreSQL 用户名                    |
| `PG_PASSWORD`                          | 否   | PostgreSQL 密码                      |
| `DATABASE_URL`                         | 否   | PostgreSQL DSN（优先于 `PG_*`）      |

运行时注入规则：
- 项目仅使用 `MODEL` 指定模型名，API Key 不再要求写入 `.env`。
- 默认从系统环境变量读取 provider 对应密钥（例如 `OPENAI_API_KEY`、`OLLAMA_API_KEY` 等）。
- 若未提供所需密钥，将由 LiteLLM 在运行时报错提示。

---

## 输出内容

- 数据库：SQLite 默认 `data/github-trending.db`；PostgreSQL 由 `PG_*` 或 `DATABASE_URL` 决定
- 报表预览：`docs/exports/opportunity-report-YYYY-MM-DD.html`
- 网页输出：`docs/`
- 导出文件：`docs/exports/opportunity-report-*.{json,csv}`

---

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

---

## 开源引用说明

本项目基于开源项目 **github-topics-trending** 进行二次开发与结构调整：

- 原项目地址：https://github.com/geekjourneyx/github-topics-trending
- 当前项目沿用与原项目一致的 **MIT License**
- 详细引用与改造说明见 [NOTICE.md](NOTICE.md)
