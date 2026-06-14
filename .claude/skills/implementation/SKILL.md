---
name: implementation
description: Workflow for implementing roadmap steps in api-tracker — single direct commit to main per step (no PRs, no branches), then close the corresponding task in clite. Use when working on any milestone item from specs/implementation-plan.md.
---

# Implementation Workflow — api-tracker

The canonical loop for advancing roadmap work. One step = one commit on `main` + one closed clite task.

## Per step

1. **Read the spec.** Locate the exact paragraph in `specs/implementation-plan.md` (e.g. §4.2.6.1) and the related sections in `architecture.md` / `product.md` if referenced.
2. **Implement** the change. Stay inside the scope of that paragraph — do not bundle unrelated cleanup.
3. **Verify locally** before committing:
   - `uv run pytest <service>/tests` for any touched Python service
   - `uv run mypy <service>/src`
   - `uv run ruff check <service>/src && uv run ruff format --check <service>/src`
   - For Angular / CLI changes — the analogous `npm run lint && npm test` or `uv run pytest cli/tests`.
   - All green is mandatory before `git commit`.
4. **Commit directly to `main`.** No feature branch, no PR. Stage only the files for this step (never `git add -A`).
5. **Push** to `origin main`.
6. **Close the clite task** that tracks this step (see "Closing tasks" below).

## Commit message format

Match existing repo style (see `git log`):

```
<type>(<area>): <milestone-tag> — <short summary>

<optional body with rationale; reference spec § numbers>
```

- `<type>`: `feat` | `fix` | `refactor` | `chore` | `style` | `docs`
- `<area>`: e.g. `tasks-svc`, `auth-svc`, `cli`, `ci`, `deploy`, `specs`
- `<milestone-tag>`: e.g. `M2.17`, `M3.4`
- **No `Co-Authored-By: Claude` lines.**
- **No `Closes #N`** for GitHub issues — closing happens in clite, not on GitHub.

## Closing tasks

Each roadmap step is mirrored as a task in the api-tracker production instance (we dogfood our own product). After the commit is pushed:

```bash
uv run clite task update <task-uuid> --status done
```

Statuses are limited to `open` and `done` (`backend/tasks-service/src/tasks_service/models.py` — `TaskStatus`). If the task UUID is unknown, find it with:

```bash
uv run clite task list --filter 'title=="<milestone-tag>*"'
```

If no clite task exists for the step yet, create one **before** starting the work:

```bash
uv run clite task create --title "<milestone-tag> — <short summary>"
```

## When NOT to follow this workflow

- **Hotfix / infra emergency** — still commit straight to `main`, but a clite task may not exist; create-and-close one after the fact for traceability.
- **Throwaway experiments** — do not commit to `main` at all; use a local branch and discard.
- **Cross-milestone refactors that span many services** — these can still go to `main`, but discuss the boundary with the user first; do not auto-decompose into many tiny commits.

## What this workflow replaces

This skill is the source of truth for the implementation loop. It supersedes any older guidance about feature branches, PR-per-feature, or `Closes #N` references — those patterns are no longer used for ongoing roadmap work.
