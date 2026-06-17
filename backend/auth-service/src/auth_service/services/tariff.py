"""Tariff каталог и состояние пользователя (M5 — Free only).

В M5 каталог хардкожен под единственный тариф Free; динамический выбор
тарифа и платные тиры — M6 (см. tariff.md §1.5.1).

Источник истины — tariff.md §2.5 (Free) и §7.1.1 (колонка tariff).
"""

from __future__ import annotations

from typing import Final

# Каталог Free (tariff.md §2.5). Pro/Max добавляются в M6.
FREE_TASK_SHARES: Final[int] = 200
FREE_PROJECTS: Final[int] = 3
FREE_TEAMS: Final[int] = 3


def get_user_limits(tariff: str) -> tuple[int, int, int]:
    """Лимиты по метрикам (task_shares, projects, teams) для тарифа.

    В M5: для любого тарифа возвращается Free-каталог (планировалось через
    `tariff IN (free, pro, max)`, но платные — это M6). См. IPLAN §7.2.3.2.
    """
    # tariff игнорируется — все пользователи в M5 эффективно на Free.
    return FREE_TASK_SHARES, FREE_PROJECTS, FREE_TEAMS
