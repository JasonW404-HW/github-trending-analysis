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
- 数据持久化：SQLite 存储快照、历史、分析详情

---

## 架构分层

### 1) 入口层

- `main.py`：仅负责 CLI 参数路由

### 2) 应用层

- `src/application/cli_app.py`：命令执行编排（full / fetch-only / opportunity-report）
- `src/application/opportunity_report_builder.py`：机会报表 Markdown 构建

### 3) 流程层（Pipeline）

- `src/pipeline/contracts`：运行契约（数据模型）
- `src/pipeline/steps`：流程步骤（仓库筛选、仓库分析）
- `src/pipeline/workflows`：端到端工作流编排（TrendingWorkflow）

### 4) 基础设施层

- `src/github.py`：GitHub API 采集
- `src/readme_fetcher.py`：README 获取
- `src/claude_summarizer.py`：LLM 分析
- `src/database.py`：SQLite 数据访问
- `src/email_reporter.py` / `src/resend.py`：邮件内容与发送
- `src/web_generator.py`：静态网页生成

---

## 快速开始

### 环境要求

- Python 3.12+
- uv
- GitHub Personal Access Token
- ZHIPU API Key（Claude 兼容代理）
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
- `ZHIPU_API_KEY`
- `RESEND_API_KEY`
- `EMAIL_TO`

---

## 运行方式

```bash
# 完整流程：抓取 + 分析 + 邮件 + 网页
uv run main.py

# 仅抓取与分析
uv run main.py --fetch-only

# 仅生成目标机会报表（基于已落库数据）
uv run main.py --opportunity-report
```

---

## 关键配置

| 变量                          | 必需 | 说明                           |
| ----------------------------- | ---- | ------------------------------ |
| `GH_TOKEN`                    | 是   | GitHub Token                   |
| `TOPIC`                       | 否   | 追踪话题（默认 `claude-code`） |
| `ZHIPU_API_KEY`               | 是   | 模型 API Key                   |
| `RESEND_API_KEY`              | 是   | Resend API Key                 |
| `EMAIL_TO`                    | 是   | 收件人邮箱                     |
| `ANALYSIS_KEYWORDS`           | 否   | 关键词筛选（逗号分隔）         |
| `ANALYSIS_KEYWORD_MATCH_MODE` | 否   | `any` / `all`                  |
| `ANALYSIS_CUSTOM_PROMPT`      | 否   | 自定义分析提示词               |
| `PUSH_MIN_COMMERCIAL_LEVEL`   | 否   | `strong` / `weak`              |
| `GITHUB_CACHE_MINUTES`        | 否   | 抓取缓存分钟数                 |

---

## 输出内容

- 数据库：`data/github-trending.db`
- 运营报表：`data/reports/opportunity-report-YYYY-MM-DD.md`
- 网页输出：`docs/`
- 导出文件：`docs/exports/opportunity-report-*.{json,csv,md}`

---

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

---

## 开源引用说明

本项目基于开源项目 **github-topics-trending** 进行二次开发与结构调整：

- 原项目地址：https://github.com/geekjourneyx/github-topics-trending
- 当前项目沿用与原项目一致的 **MIT License**
- 详细引用与改造说明见 [NOTICE.md](NOTICE.md)
