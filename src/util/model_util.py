"""LiteLLM 配置与调用工具。"""

import os
import re
from typing import Any, Optional

from litellm import completion

from src.config import MODEL


def _normalize_provider_env_prefix(provider_name: str) -> str:
    """将 provider 名转换为环境变量前缀。"""
    provider = str(provider_name or "").strip().upper()
    if not provider:
        return ""
    return re.sub(r"[^A-Z0-9]+", "_", provider).strip("_")


def resolve_model_name(model: Optional[str] = None) -> str:
    """解析最终模型名，优先使用入参，其次读取 MODEL 环境变量。"""
    model_name = str(model if model is not None else MODEL).strip()
    if not model_name:
        raise ValueError("MODEL 环境变量未设置（示例: ollama/gemma3:4b）")
    return model_name


def resolve_model_api_key(model_name: str, api_key: Optional[str] = None) -> Optional[str]:
    """根据模型 provider 解析 API Key。

    优先级：
    1) 显式传入 api_key
    2) 自动读取 `<PROVIDER>_API_KEY`
    """
    explicit_key = str(api_key or "").strip()
    if explicit_key:
        return explicit_key

    provider = str(model_name or "").split("/", 1)[0].strip()
    provider_prefix = _normalize_provider_env_prefix(provider)
    if not provider_prefix:
        return None

    env_key = f"{provider_prefix}_API_KEY"
    env_value = str(os.getenv(env_key) or "").strip()
    return env_value or None


def build_completion_kwargs(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """构建 LiteLLM completion 的基础参数。"""
    model_name = resolve_model_name(model)
    options: dict[str, Any] = {"model": model_name}

    resolved_api_key = resolve_model_api_key(model_name, api_key)
    if resolved_api_key:
        options["api_key"] = resolved_api_key

    return options


def litellm_completion(
    *,
    messages: list[dict[str, Any]],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """统一入口调用 LiteLLM completion。"""
    options = build_completion_kwargs(model=model, api_key=api_key)
    return completion(messages=messages, **options, **kwargs)
