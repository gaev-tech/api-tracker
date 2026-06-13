import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.config import settings
from tasks_service.models import User

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def run_migrations() -> None:
    """Запуск Alembic upgrade head в entrypoint (architecture.md §3.3)."""
    import shutil

    alembic_bin = shutil.which("alembic")
    if alembic_bin is None:
        raise RuntimeError("alembic CLI not found in PATH")
    subprocess.run(  # noqa: S603 — alembic_bin резолвится через which
        [alembic_bin, "-c", str(SERVICE_ROOT / "alembic.ini"), "upgrade", "head"],
        check=True,
        cwd=SERVICE_ROOT,
    )


async def ensure_solo_user(session: AsyncSession) -> UUID:
    """SOLO_USER создаётся при первом старте в AUTH_MODE=disabled (architecture.md §4.1.3)."""
    result = await session.execute(select(User).where(User.email == settings.solo_user_email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user.id

    user = User(email=settings.solo_user_email)
    session.add(user)
    await session.flush()
    return user.id
