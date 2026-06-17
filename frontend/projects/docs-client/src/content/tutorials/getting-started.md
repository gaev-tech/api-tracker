# Getting Started

This tutorial takes you from zero to your first task in under a minute. Most
api-tracker users — humans and AI agents alike — interact with the system
through the `clite` CLI.

## 1. Install the CLI

Pre-built binaries live on [GitHub Releases](https://github.com/gaev-tech/api-tracker/releases).
The recommended channel for most environments is `pipx`, which installs into an
isolated venv and exposes the `clite` entrypoint on your `$PATH`.

```bash
# Recommended — isolated install via pipx
pipx install clite

# Or: grab a static binary from GitHub Releases
curl -fsSL https://github.com/gaev-tech/api-tracker/releases/latest/download/clite-$(uname -s)-$(uname -m).tar.gz \
  | tar -xz -C /usr/local/bin
```

Other channels — PyPI, Homebrew, APT, npm wrapper — land in **M4.B**. See the
[Installation](/installation) page for the latest status.

Verify the install:

```bash
clite version
# 2.x.y
```

## 2. Log in

Authentication is magic-link based: you give the CLI your email, it asks the
server to mail you a link, and you click. No password.

```bash
clite login --email me@example.org
```

You'll see:

```
We sent a magic link to me@example.org. Click it to finish login.
Waiting...
✓ logged in as me@example.org
```

The credentials are stored in your XDG config directory
(`~/.config/clite/credentials.json` on Linux/macOS) and used by every
subsequent CLI call. To check who you are:

```bash
clite me
# email: me@example.org
# user_id: 4f2b...
```

## 3. Create your first task

Tasks are created in bulk — the design is AI-agent-first, so there is no
single-task mutation API. Even creating one task uses the bulk form.

```bash
clite create tasks --bulk '[{"title":"Try api-tracker"}]'
```

You'll get back a JSON object with the new task ids:

```json
{"task_ids": ["a1b2c3d4..."]}
```

A more typical "real" bulk create from an AI agent:

```bash
clite create tasks --bulk '[
  {"title":"Investigate flaky auth test",   "labels":["backend","p1"]},
  {"title":"Draft RSQL primer for docs",    "labels":["docs"]},
  {"title":"Profile rsql parser hot path",  "labels":["perf"]}
]'
```

## 4. Read tasks back

The read API uses RSQL — a small string-based query language with strict
typing per field. See the [RSQL](/rsql) page for the full grammar.

```bash
# All open tasks assigned to me
clite get tasks --filter 'status=="open";assignee==me'

# Trim columns
clite get tasks --filter 'status=="open"' --fields id,title,labels
```

By default, `clite get tasks` paginates by 50 ordered by
`created_at asc`. A `next_cursor` field appears in the JSON output when more
rows are available — pass it back with `--cursor` to continue.

## 5. Update tasks (bulk too)

There is no `clite update task <id>`. Instead, you express a set with RSQL and
either:

- `--bulk` to apply per-row patches (one patch per row), or
- `--batch` to apply the same patch to every row in one shot.

```bash
# Mark every "investigate" task done
clite update tasks --filter 'title=="*investigate*"' \
                   --batch '{"status":"done"}'
```

## 6. View history

Every mutation lands in `history`, queryable by task or by user:

```bash
# History for one task
clite get log --task a1b2c3d4

# History for one user (any tasks they touched)
clite get log --user me@example.org
```

## Where to go next

- [Quickstart](/quickstart) — the same flow, but as a checklist.
- [CLI Reference](/cli) — every command, every option, every example.
- [RSQL primer tutorial](/tutorials/rsql-primer) — the query language in
  depth, with copy-paste examples.
- [AI-driven workflow tutorial](/tutorials/ai-driven-workflow) — patterns
  optimized for letting an AI agent drive the tracker.
- [Writing automations tutorial](/tutorials/writing-automations) — cron and
  event-triggered actions that run as you.
