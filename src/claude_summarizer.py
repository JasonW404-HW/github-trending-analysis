"""
Claude Summarizer - AI 总结和分类 GitHub 仓库
使用 Claude API 对仓库进行分析、总结和分类
"""

import json
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Deque, Dict, List, Optional

from anthropic import Anthropic

from src.config import (
    ANALYSIS_CUSTOM_PROMPT,
    ANTHROPIC_BASE_URL,
    CATEGORIES,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    MODEL_MAX_CONCURRENCY,
    MODEL_MAX_RPM,
    ZHIPU_API_KEY,
)
from src.retry_utils import execute_with_429_retry


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


class ClaudeSummarizer:
    """AI 总结和分类 GitHub 仓库"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_concurrency: Optional[int] = None,
        max_rpm: Optional[int] = None,
        extra_prompt: Optional[str] = None,
    ):
        """
        初始化 Claude 客户端配置

        Args:
            api_key: API 密钥，默认从环境变量读取
            base_url: API 基础 URL，默认从环境变量读取
            max_concurrency: 最大并发请求数
            max_rpm: 每分钟最大请求数
            extra_prompt: 自定义分析提示词（来自配置）
        """
        self.api_key = api_key or ZHIPU_API_KEY
        self.base_url = base_url or ANTHROPIC_BASE_URL
        self.model = CLAUDE_MODEL
        self.max_tokens = CLAUDE_MAX_TOKENS
        self.max_concurrency = max(1, max_concurrency or MODEL_MAX_CONCURRENCY)
        self.max_rpm = max(1, max_rpm or MODEL_MAX_RPM)
        self.extra_prompt = (extra_prompt if extra_prompt is not None else ANALYSIS_CUSTOM_PROMPT).strip()
        self._rpm_limiter = _RpmLimiter(self.max_rpm)

        if not self.api_key:
            raise ValueError("ZHIPU_API_KEY 环境变量未设置")

        try:
            self._create_client()
            print("✅ Claude 客户端初始化成功")
        except Exception as error:
            raise Exception(f"Claude 客户端初始化失败: {error}")

    def _create_client(self) -> Anthropic:
        """创建 Anthropic 客户端"""
        return Anthropic(base_url=self.base_url, api_key=self.api_key)

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

        print(
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
                    print(f"❌ 分析异常 {repo_name}: {error}")
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
        print(f"✅ AI 分析完成: 成功 {success_count}，降级 {fallback_count}")

        return ordered_results

    def _analyze_single_repo(self, repo: Dict) -> Optional[Dict]:
        """分析单个仓库"""
        repo_name = repo.get("repo_name") or repo.get("name", "unknown")
        prompt = self._build_single_prompt(repo)

        self._rpm_limiter.acquire()

        try:
            response = execute_with_429_retry(
                operation=lambda: self._create_client().messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=0.3,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                ),
                context=f"Claude 分析 {repo_name}",
            )

            result_text = self._extract_response_text(response)
            if not result_text:
                return None
            return self._parse_single_response(result_text, repo)

        except Exception as error:
            print(f"❌ Claude API 调用失败 {repo_name}: {error}")
            return None

    @staticmethod
    def _extract_response_text(response: object) -> str:
        """提取 Claude 响应中的文本内容"""
        content_blocks = getattr(response, "content", [])
        texts: List[str] = []

        for block in content_blocks:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                texts.append(text)

        return "\n".join(texts).strip()

    def _build_single_prompt(self, repo: Dict) -> str:
        """构建单仓库分析 Prompt"""
        repo_name = repo.get("repo_name")
        description = repo.get("description", "N/A")
        language = repo.get("language", "N/A")
        topics = repo.get("topics", [])
        readme = repo.get("readme_summary", "")
        keyword_hits = repo.get("keyword_hits", [])

        category_text = "\n".join([f"  - {key}: {zh}" for key, zh in REPO_CATEGORIES.items()])
        topic_text = ", ".join(topics[:8]) if topics else "N/A"
        keyword_text = ", ".join(keyword_hits) if keyword_hits else "N/A"
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

严格输出 JSON 对象，不要有任何额外说明：

```json
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
```
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

    def _parse_single_response(self, result_text: str, original_repo: Dict) -> Optional[Dict]:
        """解析单仓库响应"""
        cleaned = self._clean_json_text(result_text)

        try:
            parsed = json.loads(cleaned)

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

        except json.JSONDecodeError as error:
            repo_name = original_repo.get("repo_name") or original_repo.get("name", "unknown")
            print(f"❌ JSON 解析失败 {repo_name}: {error}")
            print(f"   原始响应: {cleaned[:400]}...")
            return None

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
    summarizer = ClaudeSummarizer()
    return summarizer.summarize_and_classify(repos)
