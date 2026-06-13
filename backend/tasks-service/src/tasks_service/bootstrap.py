import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.config import settings
from tasks_service.models import User

SERVICE_ROOT = Path(__file__).resolve().parents[2]
# В Docker-runtime alembic.ini лежит в /app, а не в /opt/venv;
# можно переопределить через env ALEMBIC_DIR.
import os as _os  # noqa: E402

ALEMBIC_DIR = Path(_os.environ.get("ALEMBIC_DIR", str(SERVICE_ROOT)))


def run_migrations() -> None:
    """Запуск Alembic upgrade head в entrypoint (architecture.md §3.3)."""
    import shutil

    alembic_bin = shutil.which("alembic")
    if alembic_bin is None:
        raise RuntimeError("alembic CLI not found in PATH")
    ini_path = ALEMBIC_DIR / "alembic.ini"
    if not ini_path.exists():
        # Fallback на SERVICE_ROOT (uv dev-окружение).
        ini_path = SERVICE_ROOT / "alembic.ini"
    subprocess.run(  # noqa: S603 — alembic_bin резолвится через which
        [alembic_bin, "-c", str(ini_path), "upgrade", "head"],
        check=True,
        cwd=str(ini_path.parent),
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
