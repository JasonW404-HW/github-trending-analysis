"""Repository Summarizer - AI 总结和分类 GitHub 仓库。"""

import json
import ast
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Deque, Dict, List, Optional, Tuple

from src.config import (
    ANALYSIS_CUSTOM_PROMPT,
    CATEGORIES,
    LLM_MAX_TOKENS,
    LLM_JSON_REPAIR_RETRIES,
    MODEL_MAX_CONCURRENCY,
    MODEL_MAX_RPM,
)
from src.util.retry_utils import execute_with_429_retry
from src.util.model_util import litellm_completion, resolve_model_name
from src.util.print_util import logger


def get_category_list() -> Dict[str, str]:
    """获取分类列表"""
    return {key: info["name"] for key, info in CATEGORIES.items()}


REPO_CATEGORIES = get_category_list()


class _RpmLimiter:
    """简单 RPM 限流器（滑动窗口）"""

    def __init__(self, max_rpm: int):
        self.max_rpm = max(1, max_rpm)
        self._timestamps: Deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """阻塞直到可发起下一次请求"""
        while True:
            wait_seconds = 0.0
            with self._lock:
                now = time.monotonic()

                while self._timestamps and (now - self._timestamps[0]) >= 60:
                    self._timestamps.popleft()

                if len(self._timestamps) < self.max_rpm:
                    self._timestamps.append(now)
                    return

                wait_seconds = max(0.05, 60 - (now - self._timestamps[0]))

            time.sleep(wait_seconds)


class RepositorySummarizer:
    """AI 总结和分类 GitHub 仓库"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_concurrency: Optional[int] = None,
        max_rpm: Optional[int] = None,
        extra_prompt: Optional[str] = None,
        json_repair_retries: Optional[int] = None,
    ):
        """
        初始化模型客户端配置

        Args:
            api_key: API 密钥，默认从环境变量读取
            base_url: API 基础 URL，默认从环境变量读取
            max_concurrency: 最大并发请求数
            max_rpm: 每分钟最大请求数
            extra_prompt: 自定义分析提示词（来自配置）
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = resolve_model_name()
        self.max_tokens = LLM_MAX_TOKENS
        self.max_concurrency = max(1, max_concurrency or MODEL_MAX_CONCURRENCY)
        self.max_rpm = max(1, max_rpm or MODEL_MAX_RPM)
        self.json_repair_retries = max(
            0,
            LLM_JSON_REPAIR_RETRIES if json_repair_retries is None else int(json_repair_retries),
        )
        self.extra_prompt = (extra_prompt if extra_prompt is not None else ANALYSIS_CUSTOM_PROMPT).strip()
        self._rpm_limiter = _RpmLimiter(self.max_rpm)

        try:
            logger.info("✅ LiteLLM 客户端初始化成功")
        except Exception as error:
            raise Exception(f"LiteLLM 客户端初始化失败: {error}")

    def summarize_and_classify(
        self,
        repos: List[Dict],
        on_success: Optional[Callable[[Dict], None]] = None,
    ) -> List[Dict]:
        """
        单仓库并发分析（支持并发与 RPM 限流）

        Args:
            repos: 待分析仓库列表
            on_success: 每次成功分析后的回调（用于及时落库）

        Returns:
            分析结果列表（失败项会使用降级结果）
        """
        if not repos:
            return []

        logger.info(
            f"🤖 正在分析 {len(repos)} 个仓库 "
            f"(并发={self.max_concurrency}, RPM={self.max_rpm})..."
        )

        result_map: Dict[str, Dict] = {}

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            future_map = {
                executor.submit(self._analyze_single_repo, repo): repo
                for repo in repos
            }

            for future in as_completed(future_map):
                repo = future_map[future]
                repo_name = repo.get("repo_name") or repo.get("name", "unknown")

                try:
                    result = future.result()
                except Exception as error:
                    logger.error(f"❌ 分析异常 {repo_name}: {error}")
                    result = None

                if result:
                    result_map[repo_name] = result
                    if on_success:
                        on_success(result)
                    continue

                result_map[repo_name] = self._fallback_summary(repo)

        ordered_results: List[Dict] = []
        for repo in repos:
            repo_name = repo.get("repo_name") or repo.get("name", "unknown")
            if repo_name in result_map:
                ordered_results.append(result_map[repo_name])

        success_count = len([result for result in ordered_results if not result.get("fallback")])
        fallback_count = len(ordered_results) - success_count
        logger.info(f"✅ AI 分析完成: 成功 {success_count}，降级 {fallback_count}")

        return ordered_results

    def _analyze_single_repo(self, repo: Dict) -> Optional[Dict]:
        """分析单个仓库"""
        repo_name = repo.get("repo_name") or repo.get("name", "unknown")
        prompt = self._build_single_prompt(repo)

        self._rpm_limiter.acquire()

        try:
            response = execute_with_429_retry(
                operation=lambda: litellm_completion(
                    model=self.model,
                    api_key=self.api_key,
                    max_tokens=self.max_tokens,
                    temperature=0.3,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                ),
                context=f"LLM 分析 {repo_name}",
            )

            result_text = self._extract_response_text(response)
            if not result_text:
                return None

            parsed = self._parse_single_response(result_text, repo)
            if parsed:
                return parsed

            if self.json_repair_retries <= 0:
                return None

            repair_source = result_text
            for attempt in range(1, self.json_repair_retries + 1):
                repaired_text = self._request_json_repair(
                    repo_name=repo_name,
                    broken_text=repair_source,
                    attempt=attempt,
                )
                if not repaired_text:
                    continue

                repaired = self._parse_single_response(
                    repaired_text,
                    repo,
                    log_error=False,
                )
                if repaired:
                    logger.info(f"♻️ JSON 修复成功 {repo_name} (attempt={attempt})")
                    return repaired

                repair_source = repaired_text

            logger.error(f"❌ JSON 修复失败 {repo_name}")
            return None

        except Exception as error:
            logger.error(f"❌ LLM API 调用失败 {repo_name}: {error}")
            return None

    @staticmethod
    def _extract_response_text(response: object) -> str:
        """提取 LiteLLM 响应中的文本内容"""
        choices = getattr(response, "choices", [])
        if not isinstance(choices, list) or not choices:
            return ""

        message = getattr(choices[0], "message", None)
        if message is None:
            return ""

        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()

        texts: List[str] = []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, str) and part.strip():
                    texts.append(part.strip())
                    continue
                if isinstance(part, dict):
                    text = str(part.get("text") or "").strip()
                    if text:
                        texts.append(text)
                    continue
                text = str(getattr(part, "text", "") or "").strip()
                if text:
                    texts.append(text)

        if texts:
            return "\n".join(texts).strip()

        return str(content or "").strip()

    @staticmethod
    def _remove_trailing_commas(text: str) -> str:
        """移除 JSON 中对象/数组闭合前的多余逗号。"""
        return re.sub(r",\s*([}\]])", r"\1", text)

    @staticmethod
    def _extract_fenced_json_blocks(text: str) -> List[str]:
        """提取 Markdown 代码块中的 JSON 文本。"""
        if not text:
            return []

        pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
        blocks: List[str] = []

        for match in pattern.finditer(text):
            block = str(match.group(1) or "").strip()
            if block:
                blocks.append(block)

        return blocks

    @staticmethod
    def _extract_first_balanced_json(text: str) -> str:
        """从文本中提取首个括号平衡的 JSON 片段（对象或数组）。"""
        if not text:
            return ""

        start = -1
        stack: List[str] = []
        in_string = False
        escaped = False

        for index, char in enumerate(text):
            if start < 0:
                if char in "[{":
                    start = index
                    stack.append(char)
                continue

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue

            if char in "[{":
                stack.append(char)
                continue

            if char in "]}":
                if not stack:
                    continue

                opener = stack[-1]
                if (opener == "{" and char == "}") or (opener == "[" and char == "]"):
                    stack.pop()
                    if not stack:
                        return text[start : index + 1].strip()
                else:
                    start = -1
                    stack = []
                    in_string = False
                    escaped = False

        return ""

    def _build_json_candidates(self, result_text: str) -> List[str]:
        """构建 JSON 解析候选文本列表。"""
        raw = str(result_text or "").strip()
        if not raw:
            return []

        candidates: List[str] = []
        seen: set[str] = set()

        def add_candidate(value: str) -> None:
            candidate = str(value or "").strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            candidates.append(candidate)

        cleaned = self._clean_json_text(raw)
        add_candidate(raw)
        add_candidate(cleaned)

        for block in self._extract_fenced_json_blocks(raw):
            add_candidate(block)

        add_candidate(self._extract_first_balanced_json(raw))
        add_candidate(self._extract_first_balanced_json(cleaned))

        return candidates

    def _build_json_variants(self, candidate: str) -> List[str]:
        """构建单条候选文本的修复变体。"""
        variants: List[str] = []
        seen: set[str] = set()

        def add_variant(value: str) -> None:
            variant = str(value or "").strip().lstrip("\ufeff")
            if not variant or variant in seen:
                return
            seen.add(variant)
            variants.append(variant)

        add_variant(candidate)

        normalized_quotes = (
            candidate.replace("“", '"')
            .replace("”", '"')
            .replace("‘", "'")
            .replace("’", "'")
        )
        add_variant(normalized_quotes)

        prefix_removed = re.sub(r"^\s*json\s*", "", normalized_quotes, flags=re.IGNORECASE)
        add_variant(prefix_removed)

        for variant in list(variants):
            add_variant(self._remove_trailing_commas(variant))

        return variants

    def _load_json_payload(self, result_text: str) -> Tuple[Optional[object], str]:
        """尝试从模型输出中加载 JSON 载荷。"""
        last_error = "empty response"

        for candidate in self._build_json_candidates(result_text):
            for variant in self._build_json_variants(candidate):
                try:
                    return json.loads(variant), ""
                except json.JSONDecodeError as error:
                    last_error = f"{error.msg} (line {error.lineno}, col {error.colno})"

                try:
                    literal = ast.literal_eval(variant)
                    if isinstance(literal, (dict, list)):
                        return literal, ""
                except (SyntaxError, ValueError):
                    continue

        return None, last_error

    def _request_json_repair(self, repo_name: str, broken_text: str, attempt: int) -> str:
        """调用模型进行 JSON 文本修复。"""
        clipped_text = self._clip_text(broken_text, 12000)
        prompt = f"""你是 JSON 修复器。请将输入修复为合法 JSON。

要求：
1. 只输出 JSON（对象或数组），不要解释、不要 Markdown 代码块。
2. 尽量保留原字段语义，不要凭空新增业务字段。
3. 字段名必须是双引号，移除多余逗号，补全缺失括号。

待修复文本：
{clipped_text}
"""

        self._rpm_limiter.acquire()

        try:
            response = execute_with_429_retry(
                operation=lambda: litellm_completion(
                    model=self.model,
                    api_key=self.api_key,
                    max_tokens=min(self.max_tokens, 2048),
                    temperature=0,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                ),
                context=f"LLM JSON 修复 {repo_name} (attempt={attempt})",
            )
        except Exception as error:
            logger.warning(f"⚠️ JSON 修复请求失败 {repo_name}: {error}")
            return ""

        return self._extract_response_text(response)

    @staticmethod
    def _format_recent_activity(items: object, max_items: int = 6) -> str:
        """将近期 Issue/PR 活动格式化为 Prompt 文本。"""
        if not isinstance(items, list) or not items:
            return "N/A"

        lines: List[str] = []
        for item in items[:max_items]:
            if not isinstance(item, dict):
                continue

            number = item.get("number")
            title = str(item.get("title") or "").strip()
            state = str(item.get("state") or "unknown").strip() or "unknown"
            updated_at = str(item.get("updated_at") or "").strip()
            comments = int(item.get("comments") or 0)

            raw_labels = item.get("labels")
            labels = raw_labels if isinstance(raw_labels, list) else []
            label_text = ",".join([str(label).strip() for label in labels if str(label).strip()][:3])
            if not label_text:
                label_text = "-"

            number_text = f"#{number}" if number else "#-"
            title_text = title[:120] if title else "(无标题)"
            lines.append(
                f"- {number_text} [{state}] {title_text} "
                f"(updated={updated_at or '-'}, comments={comments}, labels={label_text})"
            )

        return "\n".join(lines) if lines else "N/A"

    @staticmethod
    def _clip_text(value: object, max_length: int) -> str:
        """按长度限制截断文本。"""
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."

    def _format_focus_threads(
        self,
        items: object,
        last_comments_limit: int = 4,
        max_threads: int = 3,
    ) -> str:
        """格式化二阶段深挖条目（原始正文 + 尾部对话）。"""
        if not isinstance(items, list) or not items:
            return "N/A"

        lines: List[str] = []
        bounded_last_comments = max(1, int(last_comments_limit))

        for item in items[:max_threads]:
            if not isinstance(item, dict):
                continue

            number = item.get("number")
            title = str(item.get("title") or "").strip()
            state = str(item.get("state") or "").strip() or "unknown"
            updated_at = str(item.get("updated_at") or "").strip() or "-"
            comments_total = int(item.get("comments_total") or 0)
            number_text = f"#{number}" if number else "#-"
            title_text = title[:120] if title else "(无标题)"

            lines.append(
                f"- {number_text} [{state}] {title_text} "
                f"(updated={updated_at}, comments_total={comments_total})"
            )

            body = self._clip_text(item.get("body"), 900)
            lines.append("  原始内容:")
            lines.append(f"  {body if body else 'N/A'}")

            comments = item.get("last_comments") if isinstance(item.get("last_comments"), list) else []
            if not comments:
                lines.append("  最近对话: N/A")
                continue

            lines.append(f"  最近对话（最后{bounded_last_comments}条）:")
            for comment in comments[:bounded_last_comments]:
                if not isinstance(comment, dict):
                    continue
                author = str(comment.get("author") or "").strip() or "unknown"
                created_at = str(comment.get("created_at") or "").strip() or "-"
                comment_body = self._clip_text(comment.get("body"), 260)
                lines.append(f"  - @{author} {created_at}: {comment_body if comment_body else '(空内容)'}")

        return "\n".join(lines) if lines else "N/A"

    def _build_single_prompt(self, repo: Dict) -> str:
        """构建单仓库分析 Prompt"""
        repo_name = repo.get("repo_name")
        description = repo.get("description", "N/A")
        language = repo.get("language", "N/A")
        topics = repo.get("topics", [])
        readme = repo.get("readme_summary", "")
        keyword_hits = repo.get("keyword_hits", [])
        recent_issues = repo.get("recent_issues", [])
        recent_pull_requests = repo.get("recent_pull_requests", [])
        focus_issue_threads = repo.get("focus_issue_threads", [])
        focus_pr_threads = repo.get("focus_pr_threads", [])
        activity_detail_last_comments = repo.get("activity_detail_last_comments", 4)
        activity_window_days = repo.get("activity_window_days", 30)

        category_text = "\n".join([f"  - {key}: {zh}" for key, zh in REPO_CATEGORIES.items()])
        topic_text = ", ".join(topics[:8]) if topics else "N/A"
        keyword_text = ", ".join(keyword_hits) if keyword_hits else "N/A"
        issue_activity_text = self._format_recent_activity(recent_issues)
        pr_activity_text = self._format_recent_activity(recent_pull_requests)
        issue_focus_text = self._format_focus_threads(
            focus_issue_threads,
            last_comments_limit=int(activity_detail_last_comments) if str(activity_detail_last_comments).isdigit() else 4,
        )
        pr_focus_text = self._format_focus_threads(
            focus_pr_threads,
            last_comments_limit=int(activity_detail_last_comments) if str(activity_detail_last_comments).isdigit() else 4,
        )
        extra_prompt_text = self.extra_prompt if self.extra_prompt else "无"

        return f"""你是一个开源项目分析专家。请分析这个 GitHub 仓库并输出结构化结果。

【仓库信息】
名称: {repo_name}
描述: {description}
语言: {language}
Topics: {topic_text}
关键词命中: {keyword_text}

README 摘要:
{readme[:1000] if readme else 'N/A'}

近 {activity_window_days} 天 Issues 活动:
{issue_activity_text}

近 {activity_window_days} 天 PR 活动:
{pr_activity_text}

二阶段深挖（原始Issue + 最后{activity_detail_last_comments}条对话）:
{issue_focus_text}

二阶段深挖（原始PR + 最后{activity_detail_last_comments}条对话）:
{pr_focus_text}

---

【任务要求】

请输出以下字段：
1. summary: 一句话摘要（不超过30字）
2. description: 详细描述（50-100字）
3. use_case: 使用场景
4. solves: 解决的问题列表（3-5个）
5. category: 选择一个分类
6. category_zh: 中文分类名
7. tech_stack: 技术栈标签（可选）
8. tags: 标签数组（3-8个，短词，便于浏览）
9. purpose_assessment: 目的导向评估对象（见下方结构）

【评估目标（必须重点完成）】
- 判断该项目是否属于“使用模型服务，尤其基于 GPU 模型服务”的项目
- 评估其所在领域、领域门槛（高/中/低）与门槛理由
- 评估开发进展：已实现功能、当前问题、未来方向（作者 roadmap + 你推测的方向）
- 必须基于 README + 近窗口期 Issue/PR 活动，识别研发重点变化、需求趋势与交付节奏
- 对二阶段深挖条目，仅依据“原始Issue/PR内容 + 最近尾部对话”抽取结论，不要虚构缺失上下文
- 评估商业价值：
    - strong: 产品较成熟，且具备可私有化部署改造与差异化盈利机会（例如私有基建设备、NPU 替代 GPU 等）
    - weak: 产品尚不成熟，但符合行业趋势且持续贡献，并具备一定改造与盈利空间
    - none: 暂不具备明确商业价值
- 给出是否推荐推送：仅 strong/weak 才可推荐，none 不推荐

`purpose_assessment` 结构要求：
{{
    "is_model_service_project": true,
    "model_service_focus": "GPU-centric|Hybrid|Not-clear",
    "domain": "所属领域",
    "domain_barrier_level": "high|medium|low",
    "domain_barrier_reason": "门槛判断依据",
    "maturity_level": "mature|growing|early",
    "implemented_features": ["已实现功能1", "功能2"],
    "current_issues": ["当前问题1", "问题2"],
    "roadmap_signals": ["作者Roadmap线索或规划"],
    "future_directions": ["模型推测未来方向"],
    "private_deploy_fit": "high|medium|low",
    "infra_transformation_opportunities": ["私有化/NPU替代等机会"],
    "commercial_value_level": "strong|weak|none",
    "commercial_value_reason": "商业价值判断依据",
    "recommended_for_push": true
}}

额外分析要求（来自配置，可为空）:
{extra_prompt_text}

可选分类:
{category_text}

【输出格式】

严格输出 JSON 对象，不要有任何额外说明，也不要输出 Markdown 代码块标记（```）：

{{
  "repo_name": "{repo_name}",
  "summary": "一句话摘要",
  "description": "详细描述",
  "use_case": "使用场景",
  "solves": ["问题1", "问题2", "问题3"],
  "category": "tool",
  "category_zh": "工具",
  "tech_stack": ["Python"],
  "tags": ["自动化", "代码生成", "命令行"],
  "purpose_assessment": {{
    "is_model_service_project": true,
    "model_service_focus": "GPU-centric",
    "domain": "AI基础设施",
    "domain_barrier_level": "high",
    "domain_barrier_reason": "需要推理调度与模型工程能力",
    "maturity_level": "growing",
    "implemented_features": ["推理服务编排", "监控与告警"],
    "current_issues": ["GPU成本高", "多租户隔离不足"],
    "roadmap_signals": ["计划支持更多推理后端"],
    "future_directions": ["NPU后端适配", "企业私有化集成"],
    "private_deploy_fit": "high",
    "infra_transformation_opportunities": ["NPU替代部分GPU推理", "本地私有化交付"],
    "commercial_value_level": "strong",
    "commercial_value_reason": "具备私有化改造空间和清晰盈利路径",
    "recommended_for_push": true
  }}
}}
"""

    @staticmethod
    def _normalize_list_field(value: object, max_items: int = 8) -> List[str]:
        """标准化字符串列表字段"""
        if not isinstance(value, list):
            return []
        items: List[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text:
                continue
            if text not in items:
                items.append(text)
        return items[:max_items]

    @staticmethod
    def _normalize_choice(value: object, allowed: List[str], default: str) -> str:
        """标准化枚举字段"""
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in allowed:
                return lowered
        return default

    def _normalize_purpose_assessment(self, data: object) -> Dict:
        """标准化目的导向评估对象"""
        payload = data if isinstance(data, dict) else {}

        commercial_level = self._normalize_choice(
            payload.get("commercial_value_level"),
            ["strong", "weak", "none"],
            "none",
        )

        recommended = payload.get("recommended_for_push")
        if not isinstance(recommended, bool):
            recommended = commercial_level in {"strong", "weak"}

        return {
            "is_model_service_project": bool(payload.get("is_model_service_project", False)),
            "model_service_focus": payload.get("model_service_focus", "Not-clear"),
            "domain": payload.get("domain", ""),
            "domain_barrier_level": self._normalize_choice(
                payload.get("domain_barrier_level"),
                ["high", "medium", "low"],
                "low",
            ),
            "domain_barrier_reason": payload.get("domain_barrier_reason", ""),
            "maturity_level": self._normalize_choice(
                payload.get("maturity_level"),
                ["mature", "growing", "early"],
                "early",
            ),
            "implemented_features": self._normalize_list_field(payload.get("implemented_features"), max_items=10),
            "current_issues": self._normalize_list_field(payload.get("current_issues"), max_items=10),
            "roadmap_signals": self._normalize_list_field(payload.get("roadmap_signals"), max_items=10),
            "future_directions": self._normalize_list_field(payload.get("future_directions"), max_items=10),
            "private_deploy_fit": self._normalize_choice(
                payload.get("private_deploy_fit"),
                ["high", "medium", "low"],
                "low",
            ),
            "infra_transformation_opportunities": self._normalize_list_field(
                payload.get("infra_transformation_opportunities"),
                max_items=10,
            ),
            "commercial_value_level": commercial_level,
            "commercial_value_reason": payload.get("commercial_value_reason", ""),
            "recommended_for_push": recommended,
        }

    @staticmethod
    def _normalize_tags(tags: object) -> List[str]:
        """标准化标签数组"""
        if not isinstance(tags, list):
            return []

        normalized: List[str] = []
        for item in tags:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if not value:
                continue
            if value not in normalized:
                normalized.append(value)
        return normalized[:8]

    def _clean_json_text(self, result_text: str) -> str:
        """清理 markdown 代码块标记"""
        cleaned = result_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def _parse_single_response(
        self,
        result_text: str,
        original_repo: Dict,
        log_error: bool = True,
    ) -> Optional[Dict]:
        """解析单仓库响应"""
        parsed, parse_error = self._load_json_payload(result_text)
        if parsed is None:
            if log_error:
                repo_name = original_repo.get("repo_name") or original_repo.get("name", "unknown")
                cleaned = self._clean_json_text(result_text)
                logger.error(f"❌ JSON 解析失败 {repo_name}: {parse_error}")
                logger.info(f"   原始响应: {cleaned[:400]}...")
            return None

        if isinstance(parsed, list):
            if not parsed:
                return None
            parsed = parsed[0]

        if not isinstance(parsed, dict):
            return None

        repo_name = parsed.get("repo_name") or original_repo.get("repo_name")
        if not repo_name:
            return None

        category = parsed.get("category", "other")
        if category not in REPO_CATEGORIES:
            category = "other"

        model_tags = self._normalize_tags(parsed.get("tags", []))
        base_tags = self._normalize_tags(original_repo.get("search_tags", []))
        merged_tags = self._normalize_tags([*base_tags, *model_tags])
        purpose_assessment = self._normalize_purpose_assessment(parsed.get("purpose_assessment", {}))

        if purpose_assessment["commercial_value_level"] == "strong":
            merged_tags = self._normalize_tags([*merged_tags, "商业价值:强"])
        elif purpose_assessment["commercial_value_level"] == "weak":
            merged_tags = self._normalize_tags([*merged_tags, "商业价值:弱"])
        else:
            merged_tags = self._normalize_tags([*merged_tags, "商业价值:无"])

        return {
            "repo_name": repo_name,
            "summary": parsed.get("summary", f"{repo_name} 项目"),
            "description": parsed.get("description", ""),
            "use_case": parsed.get("use_case", ""),
            "solves": parsed.get("solves", []),
            "category": category,
            "category_zh": parsed.get("category_zh", REPO_CATEGORIES.get(category, "其他")),
            "tech_stack": parsed.get("tech_stack", []),
            "tags": merged_tags,
            "purpose_assessment": purpose_assessment,
            "language": original_repo.get("language", ""),
            "topics": original_repo.get("topics", []),
            "readme_summary": original_repo.get("readme_summary", ""),
            "owner": original_repo.get("owner", ""),
            "url": original_repo.get("url", ""),
            "repo_updated_at": original_repo.get("updated_at", ""),
        }

    def _fallback_summary(self, repo: Dict) -> Dict:
        """降级方案：生成基础摘要（不作为成功请求落库）"""
        repo_name = repo.get("repo_name") or repo.get("name", "unknown")
        description = repo.get("description", "")

        category = self.categorize_by_rules(repo)
        language = repo.get("language", "")

        return {
            "repo_name": repo_name,
            "summary": description[:50] + "..." if len(description) > 50 else description or f"{repo_name} 项目",
            "description": description or f"{repo_name} GitHub 项目",
            "use_case": "待分析",
            "solves": ["待分析"],
            "category": category,
            "category_zh": REPO_CATEGORIES.get(category, "其他"),
            "tech_stack": [language] if language else [],
            "tags": self._normalize_tags([*self._normalize_tags(repo.get("search_tags", [])), "商业价值:无"]),
            "purpose_assessment": {
                "is_model_service_project": False,
                "model_service_focus": "Not-clear",
                "domain": "",
                "domain_barrier_level": "low",
                "domain_barrier_reason": "待分析",
                "maturity_level": "early",
                "implemented_features": [],
                "current_issues": ["待分析"],
                "roadmap_signals": [],
                "future_directions": [],
                "private_deploy_fit": "low",
                "infra_transformation_opportunities": [],
                "commercial_value_level": "none",
                "commercial_value_reason": "模型分析失败，使用降级结果",
                "recommended_for_push": False,
            },
            "language": language,
            "topics": repo.get("topics", []),
            "readme_summary": repo.get("readme_summary", ""),
            "owner": repo.get("owner", ""),
            "url": repo.get("url", ""),
            "repo_updated_at": repo.get("updated_at", ""),
            "fallback": True,
        }

    def _fallback_summaries(self, repos: List[Dict]) -> List[Dict]:
        """批量降级（兼容旧调用）"""
        return [self._fallback_summary(repo) for repo in repos]

    def categorize_by_rules(self, repo: Dict) -> str:
        """
        基于规则快速分类（用于批量预分类）

        Args:
            repo: 仓库信息

        Returns:
            分类名称
        """
        repo_name = repo.get("repo_name", "").lower()
        name = repo.get("name", "").lower()
        description = (repo.get("description") or "").lower()
        topics = [topic.lower() for topic in repo.get("topics", [])]
        language = (repo.get("language") or "").lower()

        combined_text = f"{repo_name} {name} {description} {' '.join(topics)} {language}"

        if any(keyword in combined_text for keyword in ["plugin", "extension", "vscode", "chrome", "firefox"]):
            return "plugin"

        if any(keyword in combined_text for keyword in ["template", "starter", "boilerplate", "scaffold"]):
            return "template"

        if any(keyword in combined_text for keyword in ["demo", "example", "sample", "tutorial"]):
            return "demo"

        if any(keyword in combined_text for keyword in ["doc", "guide", "tutorial", "book", "documentation"]):
            return "docs"

        if any(keyword in combined_text for keyword in ["integration", "wrapper", "sdk", "api"]):
            return "integration"

        if any(keyword in combined_text for keyword in ["cli", "tool", "utility", "script"]):
            return "tool"

        if any(keyword in combined_text for keyword in ["app", "application", "webapp", "dashboard"]):
            return "app"

        if any(keyword in combined_text for keyword in ["lib", "library", "package", "framework"]):
            return "library"

        return "other"


def summarize_repos(repos: List[Dict]) -> List[Dict]:
    """便捷函数：总结和分类仓库"""
    summarizer = RepositorySummarizer()
    return summarizer.summarize_and_classify(repos)
