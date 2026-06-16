"""Prefix-lookup для SHA1-ключей (PRD §5.2.7, ARCH §3.7.6).

Сценарий: пользователь передаёт префикс (4..40 hex-символов), сервис должен
найти ровно одну сущность с этим префиксом id, либо вернуть осмысленную
ошибку (too short / not found / ambiguous + кандидаты).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MIN_PREFIX_LEN = 4
FULL_ID_LEN = 40
_MAX_CANDIDATES = 10


class PrefixTooShort(Exception):
    """Префикс короче 4 символов."""


class PrefixNotFound(Exception):
    """Префикс ничему не соответствует."""


class AmbiguousPrefix(Exception):
    """Префикс соответствует >1 сущности; .candidates: [(id, discriminator), ...]."""

    def __init__(self, candidates: Sequence[tuple[str, str]]) -> None:
        self.candidates = list(candidates)
        super().__init__(f"ambiguous prefix; {len(self.candidates)} candidates")


def is_valid_key_or_prefix(value: str) -> bool:
    """Проверка формата: 4..40 hex-символов."""
    if not value:
        return False
    if not MIN_PREFIX_LEN <= len(value) <= FULL_ID_LEN:
        return False
    return all(c in "0123456789abcdef" for c in value)


async def resolve_prefix(
    session: AsyncSession,
    *,
    id_column: Any,
    discriminator_column: Any,
    key: str,
) -> str:
    """Разрешить префикс в полный id.

    Args:
        id_column: SQLAlchemy InstrumentedAttribute id-колонки модели.
        discriminator_column: колонка для отображения кандидатов (title/name).
        key: то, что прислал пользователь.

    Returns: полный 40-символьный id.
    Raises: PrefixTooShort, PrefixNotFound, AmbiguousPrefix.
    """
    if len(key) < MIN_PREFIX_LEN:
        raise PrefixTooShort()
    if len(key) == FULL_ID_LEN:
        # Полный ключ — проверим существование одним SELECT.
        result = await session.execute(
            select(id_column).where(id_column == key).limit(1)
        )
        if result.scalar_one_or_none() is None:
            raise PrefixNotFound()
        return key
    rows = (
        await session.execute(
            select(id_column, discriminator_column)
            .where(id_column.like(f"{key.lower()}%"))
            .limit(_MAX_CANDIDATES + 1)
        )
    ).all()
    if not rows:
        raise PrefixNotFound()
    if len(rows) == 1:
        return str(rows[0][0])
    raise AmbiguousPrefix([(str(r[0]), str(r[1])) for r in rows[:_MAX_CANDIDATES]])
