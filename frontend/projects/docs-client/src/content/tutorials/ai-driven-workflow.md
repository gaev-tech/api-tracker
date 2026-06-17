# AI-driven Workflow

api-tracker was designed to be driven primarily by AI agents. Every API and
every CLI surface optimizes for that: there is no single-row mutation, every
list is filterable with [RSQL](/rsql), and `me` is a literal so an agent
doesn't need to know its own email to query "what's mine".

This tutorial walks through the patterns that make agent-driven tracking
work.

## Pattern 1 — Bulk create from a structured plan

An agent that has just finished planning gives you a JSON array of work
items. Feed it directly to `clite create tasks --bulk`:

```bash
clite create tasks --bulk '[
  {
    "title": "Investigate flaky CI run #4218",
    "labels": ["ci", "p1"]
  },
  {
    "title": "Backfill audit log for August",
    "labels": ["data", "p2"],
    "assignee": "data-team@example.org"
  },
  {
    "title": "Sketch RFC: pluggable filter parsers",
    "labels": ["docs", "p3"]
  }
]'
```

The CLI returns the new task ids in source order:

```json
{"task_ids": ["a1b2...", "c3d4...", "e5f6..."]}
```

Keep that response — the agent can attach it to its planning artifact so
later turns know which task corresponds to which intent.

## Pattern 2 — `me` literal for self-targeting

An agent running with your credentials does not have to know your email:

```bash
clite get tasks --filter 'assignee==me;status=="open"'
```

This is so common that `me` is special-cased in the server's RSQL value
coercion for any `user_email`-typed field. See PRD §5.4.

If the agent operates on behalf of someone else, use the explicit email:

```bash
clite get tasks --filter 'assignee==alice@example.org;status=="open"'
```

## Pattern 3 — Batch update over a query

When the agent wants to "mark all of X done", use `--filter` + `--batch`:

```bash
clite update tasks --filter 'status=="open";labels=in=(closed-upstream)' \
                   --batch '{"status":"done"}'
```

`--batch` applies the same patch to every row. The response includes
`affected: N` so the agent can verify the count it expected matches what the
server applied. If it doesn't, the agent can:

1. Re-run `clite get tasks --filter ...` to inspect which rows it missed.
2. Tighten the filter and try again.

## Pattern 4 — Per-row patches with `--bulk`

Sometimes the patch differs per row:

```bash
clite update tasks --bulk '[
  {"filter": "id==a1b2c3d4", "patch": {"status":"done"}},
  {"filter": "id==e5f6g7h8", "patch": {"labels":["docs","p3"]}}
]'
```

This is the form to use when an agent has prepared a per-task plan rather
than a uniform sweep. The server processes each (filter, patch) in order
inside one transaction.

## Pattern 5 — History as audit trail

Every mutation lands in `history` so the agent can answer "what did I do
yesterday?" without re-querying the live state:

```bash
# What did I touch?
clite get log --user me@example.org

# What happened to this task?
clite get log --task a1b2c3d4
```

`history` is also queryable with RSQL — actor, action, time bounds:

```bash
clite get log --user me@example.org \
              --filter 'happened_at=ge=2026-06-16T00:00:00;action==updated'
```

(Field availability depends on the server's history-RSQL whitelist; see
[RSQL reference](/rsql).)

## Pattern 6 — Chain creates → updates → log

A typical agent loop:

```bash
# 1. plan
RESPONSE=$(clite create tasks --bulk '[
  {"title": "Step A", "labels": ["agent-run-42"]},
  {"title": "Step B", "labels": ["agent-run-42"]},
  {"title": "Step C", "labels": ["agent-run-42"]}
]')

# 2. perform Step A externally, then close it
clite update tasks --filter 'labels=in=(agent-run-42);title=="Step A"' \
                   --batch '{"status":"done"}'

# 3. summarise the run for the human
clite get log --user me@example.org --filter 'happened_at=ge=2026-06-17T00:00:00'
```

The `labels=in=(agent-run-42)` trick gives the agent a cheap, RSQL-friendly
correlation key across creates, updates, and history.

## Pattern 7 — Idempotent re-runs

If an agent's run is interrupted, it can use the run-label trick above to
detect what it already did:

```bash
# Are there any agent-run-42 tasks already?
clite get tasks --filter 'labels=in=(agent-run-42)' --fields id,title,status
```

If the set is non-empty, the agent knows to resume from the last
`status=="open"` row rather than re-create the whole plan.

## Pattern 8 — Output shaping with `--fields`

The default `clite get tasks` row is wide. For an agent, narrowing the
output reduces token cost on the parse side:

```bash
clite get tasks --filter 'status=="open";assignee==me' \
                --fields id,title,labels
```

The order of `--fields` is preserved in the output (PRD §7.1).

## See also

- [RSQL primer](/tutorials/rsql-primer) — the query language.
- [Writing automations](/tutorials/writing-automations) — when the agent
  should not be in the loop at all.
- [CLI: create tasks](/cli/create-tasks) — every flag.
- [CLI: update tasks](/cli/update-tasks) — every flag.
- [CLI: get log](/cli/get-log) — history reads.
