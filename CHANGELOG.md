# Changelog

All notable changes to this project are documented in this file.

---

## [Unreleased] - 2026-03-05

### Changed

- 重构代码分层：`main.py` 改为纯路由入口，业务编排下沉到 `src/application`
- `pipeline` 调整为清晰层级：`contracts` → `steps` → `workflows`
- 移除兼容壳文件，统一迁移到新结构引用

### Documentation

- 重写 `README.md`，移除与当前项目及当前作者无关内容
- 增加“开源引用说明”，明确上游项目来源与链接
- 补充 MIT 协议说明并新增 `LICENSE`

---

## [0.1.0] - 2026-03-04

### Added

- GitHub 抓取缓存（周期 + ETag）
- 模型并发与 RPM 限流配置
- 全链路 429 自动冷却重试
- 关键词筛选与自定义分析 Prompt
- 目标机会报表输出（`--opportunity-report`）

### Changed

- 主流程升级为先落库后分析
- 邮件与网页增加商业价值导向展示
