# Writing Automations

An **automation** is a server-side action that fires either on a schedule
(`cron`) or in response to a task event. It runs as the **actor** (usually
the project owner), reads its configuration from your project, and calls a
whitelisted [system method](/system-methods).

This is how you take the AI agent out of the loop entirely for the routine
parts of tracking — daily digests, recurring cleanups, "when a P0 task is
created, also assign me" reactions.

## The shape

Every automation has:

- A **trigger** — `cron:'<spec>'` or `event:<event_type>`.
- An **action** — a `system_method` name plus a Jinja-rendered payload.
- An optional **secret name** reference for the payload.

The full reference is in the [CLI: create automation](/cli/create-automation)
page; here we focus on the recipes.

## Recipe 1 — Daily "what's mine?" digest

Print my open tasks every morning at 09:00:

```bash
clite create automation \
  --project P \
  --name daily-mine-digest \
  --trigger 'cron:0 9 * * *' \
  --action 'tasks.list' \
  --action-args '{"filter": "status==\"open\";assignee==me", "limit": 50}'
```

The automation runs as the actor (= the user that created it). At 09:00
each day it calls `tasks.list` with the embedded filter; the result lands in
the automation's run log, viewable via the dashboard or
`clite get log --automation <id>`.

## Recipe 2 — Reactive auto-label on creation

When a task with `labels` containing `p0` is created, also assign me:

```bash
clite create automation \
  --project P \
  --name p0-auto-assign \
  --trigger 'event:task.created' \
  --action 'tasks.bulk_update' \
  --action-args '{
    "filter": "id==\"{{ event.payload.task_id }}\";labels=in=(p0)",
    "patch":  {"assignee": "me@example.org"}
  }'
```

A few things to note:

- The event-trigger value (`task.created`) must be one of the entries on
  the [Events](/events) page.
- The payload is a Jinja template. `{{ event.payload.task_id }}` is the
  task id from the matched event.
- The filter has `labels=in=(p0)` so the automation does nothing if the
  newly-created task doesn't actually have the `p0` label.

## Recipe 3 — Status change → outbound webhook (via secret)

When a task transitions to `done`, post a JSON blob to an external URL kept
in a project secret:

```bash
# 1. store the secret (PRD §8.7, ARCH §13)
clite create secret --project P --name slack-webhook \
                    --value 'https://hooks.slack.com/services/...'

# 2. wire the automation
clite create automation \
  --project P \
  --name notify-on-done \
  --trigger 'event:task.status_changed' \
  --action 'http.post' \
  --action-args '{
    "url":   "{{ secrets.slack_webhook }}",
    "body":  {"text": "Task {{ event.payload.task_id }} is done."}
  }'
```

(The `http.post` system method is illustrative — only methods on the
[System Methods](/system-methods) page are actually whitelisted right now.
Update once `http.post` lands.)

## Recipe 4 — Nightly stale-task sweep

Mark every untouched `p3` task done at 02:00:

```bash
clite create automation \
  --project P \
  --name nightly-stale-sweep \
  --trigger 'cron:0 2 * * *' \
  --action 'tasks.bulk_update' \
  --action-args '{
    "filter": "status==\"open\";labels=in=(p3);created_at=lt=\"{{ (now() - timedelta(days=30)).isoformat() }}\"",
    "patch":  {"status": "done"}
  }'
```

The Jinja context has `now()` and `timedelta(...)` for date math (ARCH §11
template helpers).

## Inspecting and debugging

### List automations

```bash
clite get automations --project P
```

Each entry shows the trigger, action, last run, and next scheduled run (for
cron). Pass `--filter` to subset.

### Fire one immediately

To debug an automation without waiting for its trigger:

```bash
clite run automation <id>
```

This runs the action exactly once, as-if-triggered. The rendered payload
and the action's return value land in the response so you can see what
actually executed.

### Read the run log

Every action invocation lands in `history` with `actor = <automation
owner>`, `action = automation.run` (and similar). You can query it:

```bash
clite get log --user me@example.org --filter 'action==automation.run'
```

## Updating and deleting

Patches are partial — only the fields you mention change:

```bash
clite update automation <id> --trigger 'cron:0 10 * * *'    # move to 10am
clite update automation <id> --action-args '{"limit": 100}' # raise limit
```

Delete by id when you no longer want it:

```bash
clite delete automation <id>
```

## Security model in one paragraph

The action's actor is the user who created the automation. The actor's
project permissions are checked on every action — if the actor lost the
permission needed for the configured system method, the action will start
failing visibly in the run log. Secrets are stored encrypted at rest and
referenced by name in the Jinja template; their raw value never leaves the
server. See ARCH §13 for the storage detail.

## See also

- [System Methods](/system-methods) — the whitelist.
- [Events](/events) — the catalog of event-type strings.
- [CLI: create automation](/cli/create-automation) — every flag.
- [CLI: run automation](/cli/run-automation) — debug fire.
