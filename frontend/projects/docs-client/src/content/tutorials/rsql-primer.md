# RSQL Primer

RSQL — RESTful Service Query Language — is the small, string-friendly query
language used by every `--filter` flag in `clite`. It looks like a boolean
expression over field-comparison atoms. This page is the practical primer; the
[RSQL Reference](/rsql) page lists every operator and every field.

## Why RSQL?

api-tracker is API-first and meant to be driven by humans and AI agents over
the same surface. RSQL gives you:

- **One string per filter.** Easy to paste, easy to log, easy to round-trip
  through JSON.
- **Type-checked server-side.** Wrong field, wrong type, wrong operator → a
  400 with a precise reason. No silent SQL fallthrough.
- **A `me` literal** for `assignee` — so an agent's filter looks the same
  regardless of which session it runs in.

## Atoms

The smallest unit is a comparison: `<field><op><value>`.

```
status=="open"
created_at=gt=2026-01-01T00:00:00
labels=in=(backend,p1)
```

- The left-hand side is always a whitelisted field for the entity you're
  querying (task, history, …).
- Operators are written verbatim — `==`, `!=`, `=gt=`, `=ge=`, `=lt=`,
  `=le=`, `=in=(...)`, `=out=(...)`.
- Values are bare for identifiers, quoted with `"..."` for strings.
- Parenthesised lists like `(a,b,c)` are the RHS of `=in=` and `=out=`.

## Logic

Multiple atoms compose with `;` (AND) and `,` (OR). Group with `(...)`:

```
status=="open";assignee==me
status=="open",status=="blocked"
(labels=in=(p0,p1)),status=="open"
```

`;` binds tighter than `,` — so `a==1;b==2,c==3` is `(a==1 AND b==2) OR c==3`.

## Examples by field

### `status` (string)

```bash
clite get tasks --filter 'status=="open"'
clite get tasks --filter 'status!=done'                  # quotes optional for bare idents
clite get tasks --filter 'status=in=(open,blocked)'
```

### `assignee` (user_email; supports `me`)

```bash
clite get tasks --filter 'assignee==me'
clite get tasks --filter 'assignee==you@example.org'
clite get tasks --filter 'assignee=out=(me)'             # anything not mine
```

### `labels` (string_array; only set ops)

```bash
clite get tasks --filter 'labels=in=(backend)'           # has the "backend" label
clite get tasks --filter 'labels=in=(backend,frontend)'  # has any of these
clite get tasks --filter 'labels=out=(legacy)'           # does not have "legacy"
```

`labels` cannot use `==` or `!=` — it is an array and only set operators are
defined for it.

### `created_at` (datetime; ISO-8601)

```bash
clite get tasks --filter 'created_at=ge=2026-06-01T00:00:00'
clite get tasks --filter 'created_at=ge=2026-06-01T00:00:00;created_at=lt=2026-07-01T00:00:00'
```

### `id` (sha1_key; prefix or full)

```bash
clite get tasks --filter 'id==abc1234'                   # 4..40 hex chars
clite get tasks --filter 'id=in=(abc1234,def5678)'
```

## Putting it together

The everyday "what should I do next?" query:

```bash
clite get tasks --filter 'status=="open";assignee==me' \
                --fields id,title,labels
```

The everyday triage query:

```bash
clite get tasks --filter 'status=="open";labels=in=(p0)' \
                --fields id,title,assignee
```

The everyday cleanup query (used as an automation in
[Writing Automations](/tutorials/writing-automations)):

```bash
clite update tasks \
  --filter 'status=="open";labels=in=(stale);created_at=lt=2026-01-01T00:00:00' \
  --batch '{"status":"done"}'
```

## What if I get an error?

The server enforces a strict whitelist of fields and operators per entity. The
most common rejections:

- **Unknown field**: `unknown field 'foo' for entity 'task'` — check the
  [RSQL reference](/rsql) for the list.
- **Bad operator for type**: `operator '=gt=' not allowed for type 'string'`
  — comparison operators are only for `int` / `datetime`.
- **Bad value**: `invalid datetime '2026-06'` — datetimes are full ISO-8601.

## See also

- [RSQL Reference](/rsql) — exhaustive list of operators and fields.
- [CLI: get tasks](/cli/get-tasks) — every flag for the read command.
- [AI-driven workflow](/tutorials/ai-driven-workflow) — how to compose
  RSQL filters from agent context.
