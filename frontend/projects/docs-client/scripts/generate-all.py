"""Orchestrator for all build-time generators (ARCH §16.5).

Runs each sub-generator in sequence. Exits non-zero on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

GENERATORS = [
    "generate-cli-reference.py",
    "generate-rsql-reference.py",
    "generate-catalogs.py",
    "generate-search-index.py",
]


def main() -> int:
    for name in GENERATORS:
        path = SCRIPTS_DIR / name
        if not path.exists():
            # generators land milestone-by-milestone; skip absent ones silently
            print(f"[generate-all] skip {name} (not yet present)")
            continue
        print(f"[generate-all] run  {name}")
        result = subprocess.run(  # noqa: S603 — script paths are trusted
            [sys.executable, str(path)],
            check=False,
        )
        if result.returncode != 0:
            print(f"[generate-all] FAIL {name} (exit {result.returncode})")
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
