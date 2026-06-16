"""Opaque-курсор пагинации (architecture.md §10.3, §7.1.2).

Формат: base64-url(JSON {"t": iso8601_created_at, "i": sha1_id_str}).
"""

import base64
import json
from datetime import datetime

from tasks_service.rsql.parser import RSQLError


class CursorError(ValueError):
    """Невалидный cursor — нечитаемый или с неправильной структурой."""


def encode_cursor(created_at: datetime, item_id: str) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "i": item_id}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(token: str) -> tuple[datetime, str]:
    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + padding)
        data = json.loads(raw)
        return datetime.fromisoformat(data["t"]), str(data["i"])
    except (ValueError, KeyError, TypeError) as e:
        raise CursorError(f"invalid cursor: {token!r}") from e


def cursor_to_rsql_error_text(e: CursorError | RSQLError) -> str:
    return str(e)
