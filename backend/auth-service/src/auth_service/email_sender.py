"""SMTP-отправитель писем (architecture.md §17.2.2.3)."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from auth_service.config import settings

logger = logging.getLogger(__name__)


def _send_blocking(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        # Dev-fallback: вывести письмо в лог на WARNING-уровне,
        # чтобы было видно при стандартной uvicorn-конфигурации.
        logger.warning(
            "SMTP_HOST not set — email NOT sent. to=%s subject=%r\n--- body ---\n%s\n--- end ---",
            to,
            subject,
            body,
        )
        return
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    """Отправить email; SMTP-вызов в thread, чтобы не блокировать asyncio."""
    await asyncio.to_thread(_send_blocking, to, subject, body)


def magic_link_email_body(link: str) -> str:
    return (
        f"Здравствуйте,\n\n"
        f"Для входа в apitracker.ru перейдите по ссылке:\n\n"
        f"{link}\n\n"
        f"Ссылка действительна 15 минут.\n"
        f"Если вы не запрашивали вход — проигнорируйте письмо.\n\n"
        f"— apitracker.ru\n"
    )
