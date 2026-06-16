"""SMTP-отправитель писем (architecture.md §17.2.2.3)."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from loguru import logger

from auth_service.config import settings


def _send_blocking(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        # Dev-fallback: вывести письмо в лог на WARNING-уровне,
        # чтобы было видно при стандартной uvicorn-конфигурации.
        logger.warning(
            "SMTP_HOST not set — email NOT sent. to={} subject={!r}\n"
            "--- body ---\n{}\n--- end ---",
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
    # Port 465 = implicit TLS (SMTPS); 587 (и др.) = plain + STARTTLS.
    smtp_cls = smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
    with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        if not isinstance(s, smtplib.SMTP_SSL):
            s.starttls()
        # Многие провайдеры (Yandex, Gmail, SES) логинятся email-ом из FROM —
        # как делал прежний Go-сендер. SMTP_USER задаём, только если он
        # реально отличается от FROM.
        login_user = settings.smtp_user or settings.smtp_from
        if settings.smtp_password:
            s.login(login_user, settings.smtp_password)
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
