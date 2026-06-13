---
name: python-style-guide
description: Project-wide Python conventions (Google-based). Apply when writing or refactoring Python code in api-tracker — covers type annotations, naming, docstrings, formatting (ruff line=88), preferred libraries (pydantic, loguru, cyclopts).
---

# Python Style Guide (api-tracker)

Google's Python Style Guide adapted for this project. Apply on every Python edit.

## Language rules

- **Type annotations are mandatory** on public APIs. Use `list`, `dict`, `set` directly (Python 3.9+), not `typing.List`. Use `X | Y` instead of `Union[X, Y]`.
- **Mutable defaults forbidden** — `def f(b: list[int] | None = None): if b is None: b = []`.
- **Implicit false** — `if not users:`, not `if len(users) == 0`. Never compare to `True`/`False`.
- **f-strings** for formatting. No `"..." + str(...)` or `%` formatting (except in logger calls).
- **Comprehensions** for simple cases. Complex — plain loops.
- **`__init__.py` files MUST BE EMPTY.** No code, including `__version__`. Imports come from concrete modules.
- **`from __future__ import annotations`** at the top of every module to defer annotation evaluation.

## Formatting

- **Line length: 88** characters (not 100). Configured in `pyproject.toml` under `[tool.ruff]`.
- **4 spaces** indent, no tabs.
- **Two blank lines** between top-level definitions; **one blank line** between methods.
- **Trailing commas** in multi-line collections/args.

## Naming

| Kind | Convention |
|------|------------|
| Packages, modules | `lower_with_under` |
| Classes | `CapWords` |
| Functions, methods | `lower_with_under()` |
| Constants | `CAPS_WITH_UNDER` |
| Private | `_leading_underscore` |
| Type variables | `CapWords` (often single-letter `T`, `K`, `V`) |

Avoid single-character names except for trivial loop indices and well-known math notation.

## Docstrings

Google-style with `Args:`, `Returns:`, `Raises:`. Required for all public modules, classes, functions, methods.

```python
def fetch_user(user_id: UUID) -> User:
    """Fetch a user by id.

    Args:
        user_id: User identifier.

    Returns:
        User instance.

    Raises:
        UserNotFound: If no user exists with this id.
    """
```

## Preferred libraries

| Purpose | Library | Forbidden alternative |
|---------|---------|----------------------|
| Data validation / models | `pydantic` v2 | `dataclasses` for API I/O |
| Logging | `loguru` | stdlib `logging` |
| CLI | `cyclopts` + `rich` | `typer`, `click`, `argparse` |
| Testing | `pytest`, `pytest-mock`, `pytest-asyncio` | `unittest` |
| HTTP client | `httpx` | `requests` |
| ORM | SQLAlchemy 2.0 async + `asyncpg` | sync-only stacks |

## Logging (loguru)

```python
from loguru import logger

logger.info("Request from {} resulted in {}", ip_address, status_code)
logger.bind(request_id=req_id).warning("slow query: {}", duration_ms)
```

Lazy brace-style formatting (`{}`), no `.format()`, no f-strings inside log calls (defeats lazy eval).

## Modern Python (≥ 3.12)

- `from __future__ import annotations` for forward references without quotes.
- `match` statements for complex dispatch.
- `@dataclass(slots=True, frozen=True)` for value objects.
- `type Alias = ...` keyword for type aliases (PEP 695).
- `Self` from `typing` for fluent-builder return types.

## Errors / exceptions

- Custom exceptions inherit from a domain base (`class TasksError(Exception)`).
- Never `except:` or `except Exception:` without re-raising or logging.
- `raise X from e` to preserve cause when wrapping.

## Tools

- `ruff check` + `ruff format` on every save. Suppress only at the call site: `# noqa: RULE`.
- `mypy --strict` clean. `# type: ignore[code]` allowed only with a comment explaining why.
- `pytest` with `asyncio_default_fixture_loop_scope = "session"` for async test isolation.

## Project conflicts to fix on touch

1. `__init__.py` must be empty — remove `__version__` everywhere.
2. `pyproject.toml` `line-length = 88`.
3. CLI migrating from `typer` to `cyclopts` (big rework — by request).
4. `auth_service/email_sender.py` should use `loguru`.

**When editing any of the above files** — fix the conflict in the same change.
