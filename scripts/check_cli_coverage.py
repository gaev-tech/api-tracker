"""cli-cases-coverage — сверка `specs/cli-test-cases.md` ↔ `cli/tests/e2e/test_TC_*`.

ARCH §18.1.5: каждый кейс из спеки должен иметь test-id в коде.

Правила:
* Кейсы из секций 1 (Соглашения) и 2 (Общие негативные) — конвенции, без тестов.
* Кейс X.Y.Z из секций ≥ 3 должен иметь хотя бы одну функцию вида
  `def test_TC_X_Y_Z_…` в любом файле под `cli/tests/e2e/`.
* Orphan тест (test_TC_…, не сопоставимый со спекой) — **error**, ломает CI.
* Missing спек-кейс (есть в md, нет теста) — **warning**, перечисляется в выводе.

Усиление до error для missing — через `--strict`.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "specs" / "cli-test-cases.md"
TESTS_DIR = REPO_ROOT / "cli" / "tests" / "e2e"

CASE_LINE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\s+")
TEST_NAME_RE = re.compile(r"^def\s+test_TC_(\d+)_(\d+)_(\d+)_")

CONVENTION_SECTIONS = {1, 2}


def parse_spec_cases(spec_path: Path) -> set[tuple[int, int, int]]:
    cases: set[tuple[int, int, int]] = set()
    for line in spec_path.read_text(encoding="utf-8").splitlines():
        m = CASE_LINE_RE.match(line)
        if not m:
            continue
        section, group, item = int(m[1]), int(m[2]), int(m[3])
        if section in CONVENTION_SECTIONS:
            continue
        cases.add((section, group, item))
    return cases


def parse_test_cases(tests_dir: Path) -> set[tuple[int, int, int]]:
    cases: set[tuple[int, int, int]] = set()
    if not tests_dir.exists():
        return cases
    for py_file in tests_dir.rglob("*.py"):
        for line in py_file.read_text(encoding="utf-8").splitlines():
            m = TEST_NAME_RE.match(line.lstrip())
            if not m:
                continue
            cases.add((int(m[1]), int(m[2]), int(m[3])))
    return cases


def fmt(cases: Iterable[tuple[int, int, int]]) -> str:
    return ", ".join(f"{a}.{b}.{c}" for a, b, c in sorted(cases))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail also when spec cases are missing tests (default: warn only)",
    )
    args = parser.parse_args()

    spec_cases = parse_spec_cases(SPEC)
    test_cases = parse_test_cases(TESTS_DIR)

    missing = spec_cases - test_cases
    orphan = test_cases - spec_cases
    covered = spec_cases & test_cases

    total = len(spec_cases)
    pct = (100 * len(covered) / total) if total else 0.0
    print(
        f"cli-cases-coverage: {len(covered)}/{total} ({pct:.1f}%) covered, "
        f"{len(missing)} missing, {len(orphan)} orphan"
    )

    if orphan:
        print(f"ERROR orphan tests (нет в спеке): {fmt(orphan)}", file=sys.stderr)
    if missing:
        level = "ERROR" if args.strict else "WARN"
        print(
            f"{level} missing tests (есть в спеке, нет в коде): {fmt(missing)}",
            file=sys.stderr,
        )

    fail = bool(orphan) or (args.strict and bool(missing))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
