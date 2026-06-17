"""Jinja-рендеринг шаблонов автоматизаций (ARCH §11.5).

Используется sandboxed environment (`jinja2.sandbox.SandboxedEnvironment`),
чтобы шаблоны проектов не могли получить доступ к внутренним атрибутам
Python (например, `__class__.__subclasses__()`).

Контексты:
- event-trigger:  { "task": <task-dict>, "event": <event-dict>, "secrets": {...} }
- cron-trigger:   { "now": ISO8601, "query": fn(rsql)->list, "secrets": {...} }
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment


class RenderError(Exception):
    pass


def _env() -> SandboxedEnvironment:
    return SandboxedEnvironment(
        autoescape=False,  # webhook body — обычно JSON, escape не нужен
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render_event_context(
    template_str: str,
    *,
    task: dict[str, object],
    event: dict[str, object],
    secrets: dict[str, str],
) -> str:
    """Рендерит шаблон в event-trigger контексте."""
    return _render(template_str, {"task": task, "event": event, "secrets": secrets})


def render_cron_context(
    template_str: str,
    *,
    now: str,
    query: Callable[[str], list[dict[str, object]]],
    secrets: dict[str, str],
) -> str:
    """Рендерит шаблон в cron-trigger контексте."""
    return _render(template_str, {"now": now, "query": query, "secrets": secrets})


def _render(template_str: str, ctx: dict[str, Any]) -> str:
    try:
        tmpl = _env().from_string(template_str)
        return tmpl.render(**ctx)
    except UndefinedError as e:
        raise RenderError(f"undefined variable in template: {e}") from e
    except TemplateError as e:
        raise RenderError(f"template error: {e}") from e
