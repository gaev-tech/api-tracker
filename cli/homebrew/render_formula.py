"""Render Homebrew Formula from template.

Used by .github/workflows/release.yml (publish-homebrew job).

Reads the template at ``cli/homebrew/clite.rb.template``, substitutes
``${VERSION}``, ``${SHA256_ARM64}``, ``${SHA256_AMD64}`` placeholders, and
writes the rendered Formula to ``Formula/clite.rb`` inside the tap repo
checkout (path supplied via ``--out``).

Spec: architecture.md §15.9.4, implementation-plan.md §6.3.3.
"""

from __future__ import annotations

import argparse
import pathlib
import string
import sys


def render(template_path: pathlib.Path, mapping: dict[str, str]) -> str:
    """Render a ``string.Template`` from disk, raising on missing keys."""

    template = string.Template(template_path.read_text(encoding="utf-8"))
    return template.substitute(mapping)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=pathlib.Path,
        default=pathlib.Path(__file__).parent / "clite.rb.template",
        help="Path to Formula template (default: alongside this script).",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Release version without leading 'v' (e.g. 1.0.0).",
    )
    parser.add_argument(
        "--sha256-arm64",
        required=True,
        help="SHA256 of clite-darwin-arm64 binary.",
    )
    parser.add_argument(
        "--sha256-amd64",
        required=True,
        help="SHA256 of clite-darwin-amd64 binary.",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        required=True,
        help="Output path for rendered Formula (e.g. tap-repo/Formula/clite.rb).",
    )
    args = parser.parse_args(argv)

    mapping = {
        "VERSION": args.version,
        "SHA256_ARM64": args.sha256_arm64,
        "SHA256_AMD64": args.sha256_amd64,
    }
    rendered = render(args.template, mapping)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.out} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
