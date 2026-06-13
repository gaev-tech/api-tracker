import os
import shutil
import subprocess
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = Path(os.environ.get("ALEMBIC_DIR", str(SERVICE_ROOT)))


def run_migrations() -> None:
    """Запуск Alembic upgrade head в entrypoint (architecture.md §3.3)."""
    alembic_bin = shutil.which("alembic")
    if alembic_bin is None:
        raise RuntimeError("alembic CLI not found in PATH")
    ini_path = ALEMBIC_DIR / "alembic.ini"
    if not ini_path.exists():
        ini_path = SERVICE_ROOT / "alembic.ini"
    subprocess.run(  # noqa: S603 — alembic_bin резолвится через which
        [alembic_bin, "-c", str(ini_path), "upgrade", "head"],
        check=True,
        cwd=str(ini_path.parent),
    )
