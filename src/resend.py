"""
Resend Sender - Resend 邮件发送
使用 Resend API 发送 HTML 邮件
"""
import resend
from typing import Any, Dict

from src.retry_utils import execute_with_429_retry
from src.util.print_util import logger


class ResendSender:
    """Resend 邮件发送"""

    def __init__(self, api_key: str):
        """
        初始化

        Args:
            api_key: Resend API Key
        """
        self.api_key = api_key
        resend.api_key = api_key

    @staticmethod
    def _normalize_recipients(to: str | list[str]) -> list[str]:
        """标准化收件人列表，支持逗号分隔字符串或字符串列表。"""
        raw_items: list[str] = []

        if isinstance(to, str):
            raw_items = to.replace(";", ",").split(",")
        elif isinstance(to, list):
            for item in to:
                if not isinstance(item, str):
                    continue
                raw_items.extend(item.replace(";", ",").split(","))
        else:
            return []

        recipients: list[str] = []
        for item in raw_items:
            email = item.strip()
            if email and email not in recipients:
                recipients.append(email)

        return recipients

    def send_email(
        self,
        to: str | list[str],
        subject: str,
        html_content: str,
        from_email: str = "onboarding@resend.dev"
    ) -> Dict:
        """
        发送邮件

        Args:
            to: 收件人邮箱（支持单个邮箱、逗号分隔字符串或字符串列表）
            subject: 邮件标题
            html_content: HTML 内容
            from_email: 发件人邮箱

        Returns:
            {"success": bool, "message": str, "id": str}
        """
        recipients = self._normalize_recipients(to)
        if not recipients:
            return {"success": False, "message": "收件人邮箱为空"}

        try:
            recipients_text = ", ".join(recipients)
            logger.info(f"📧 正在发送邮件到: {recipients_text}")

            params: Any = {
                "from": from_email,
                "to": recipients,
                "subject": subject,
                "html": html_content,
            }

            response = execute_with_429_retry(
                lambda: resend.Emails.send(params),
                context=f"Resend 发送邮件 {recipients_text}",
            )

            logger.info(f"✅ 邮件发送成功! ID: {response.get('id')}")

            return {
                "success": True,
                "message": "邮件发送成功",
                "id": response.get("id"),
                "response": response
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 邮件发送失败: {error_msg}")

            return {
                "success": False,
                "message": error_msg,
                "id": None
            }

    def send_with_text(
        self,
        to: str | list[str],
        subject: str,
        html_content: str,
        text_content: str = "",
        from_email: str = "onboarding@resend.dev"
    ) -> Dict:
        """
        发送带纯文本备用的邮件

        Args:
            to: 收件人邮箱（支持单个邮箱、逗号分隔字符串或字符串列表）
            subject: 邮件标题
            html_content: HTML 内容
            text_content: 纯文本内容（备用）
            from_email: 发件人邮箱

        Returns:
            {"success": bool, "message": str, "id": str}
        """
        recipients = self._normalize_recipients(to)
        if not recipients:
            return {"success": False, "message": "收件人邮箱为空"}

        try:
            recipients_text = ", ".join(recipients)
            logger.info(f"📧 正在发送邮件到: {recipients_text}")

            params: Any = {
                "from": from_email,
                "to": recipients,
                "subject": subject,
                "html": html_content,
            }

            if text_content:
                params["text"] = text_content

            response = execute_with_429_retry(
                lambda: resend.Emails.send(params),
                context=f"Resend 发送邮件 {recipients_text}",
            )

            logger.info(f"✅ 邮件发送成功! ID: {response.get('id')}")

            return {
                "success": True,
                "message": "邮件发送成功",
                "id": response.get("id"),
                "response": response
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 邮件发送失败: {error_msg}")

            return {
                "success": False,
                "message": error_msg,
                "id": None
            }


def send_email(
    api_key: str,
    to: str | list[str],
    subject: str,
    html_content: str,
    from_email: str = "onboarding@resend.dev"
) -> Dict:
    """便捷函数：发送邮件"""
    sender = ResendSender(api_key)
    return sender.send_email(to, subject, html_content, from_email)
