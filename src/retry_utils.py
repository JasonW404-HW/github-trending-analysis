"""
统一 429 冷却重试工具
"""
import time
from typing import Callable, TypeVar

import requests

from src.config import HTTP_429_COOLDOWN_SECONDS, HTTP_429_MAX_RETRIES


T = TypeVar("T")


def is_429_error(error: Exception) -> bool:
    """判断异常是否属于 429 限流错误"""
    response = getattr(error, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True

    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True

    message = str(error).lower()
    if "429" in message:
        return True

    if "engine_overloaded_error" in message:
        return True

    return False


def execute_with_429_retry(
    operation: Callable[[], T],
    context: str,
    cooldown_seconds: int = HTTP_429_COOLDOWN_SECONDS,
    max_retries: int = HTTP_429_MAX_RETRIES,
) -> T:
    """
    执行操作并在 429 错误时自动冷却重试

    Args:
        operation: 待执行操作
        context: 日志上下文
        cooldown_seconds: 冷却秒数
        max_retries: 最大重试次数
    """
    attempt = 0

    while True:
        try:
            return operation()
        except Exception as error:
            if not is_429_error(error):
                raise

            if attempt >= max_retries:
                raise

            attempt += 1
            print(
                f"⚠️ {context} 触发 429 限流，冷却 {cooldown_seconds} 秒后重试 "
                f"({attempt}/{max_retries})"
            )
            time.sleep(cooldown_seconds)
