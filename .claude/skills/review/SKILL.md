---
name: review
description: Use before any implementation work — runs Product Specialist → Technical Architect → Project Manager reviews in sequence, updates specs and roadmap, then hands off to /implement.
user-invocable: true
---

# api-tracker: Pre-Implementation Review Workflow

## When to Use

Before implementing any new feature, changing existing behaviour, or adding tasks to the roadmap. The three roles always run in strict order. Each role is a gate — the next role cannot start until the current one finishes.

```
Product Specialist → Technical Architect → Project Manager → /implement
```

---

## Role 1 — Product Specialist

**Owns:** `specs/product-spec.md`
**Guards:** the **what** — which features exist, what they do, how entities are defined, access rights model, tariff limits, user-facing contracts.

### Responsibilities

- `product-spec.md` is the single source of truth for product decisions. All other specs must conform to it, not the other way around.
- Any proposal that changes *what the product does* (adds, removes, or redefines a feature, entity, right, or tariff rule) must be reflected in `product-spec.md` first.
- Changes that only affect *how* something is built (tech stack, DB schema, API shape, infra) do not require a product-spec change.

### Step 1.1 — Read product-spec

Read the relevant sections of `specs/product-spec.md` for the task at hand:

| Task area | Sections to read |
|-----------|-----------------|
| Auth, users, managed users | Section on Users + Access Rights |
| Tasks, projects, teams | Entity catalog + Access Rights model |
| Automations | Automations section |
| Billing, tariffs | Tariff system section |
| Any new feature | Full feature catalog scan |

### Step 1.2 — Check for product-spec violations

For the proposed change, answer each question:

1. **Does this add or remove a user-facing feature not in product-spec?** → If yes, update product-spec first or reject the change.
2. **Does this redefine an entity (add/remove fields visible to users, change ownership rules, change access rights model)?** → If yes, update product-spec first.
3. **Does this change tariff limits, what's included per plan, or what triggers blocking?** → If yes, update product-spec first.
4. **Does this change the meaning of an existing right (R-1..R-14)?** → If yes, update product-spec first.

If none of the above apply — product-spec is unaffected, proceed.

### Step 1.3 — Update product-spec if needed

If changes are required:
1. Edit `specs/product-spec.md` with the updated content.
2. Write a one-line summary of what changed and why (for the commit message).
3. Do **not** commit yet — all spec changes are committed together after all three roles finish.

### Step 1.4 — Product Specialist sign-off

State clearly: **"Product review: [passed / updated product-spec with: <summary>]"**

Then proceed to Role 2.

---

## Role 2 — Technical Architect

**Owns:** `specs/architecture.md`, `specs/architecture-backend.md`, `specs/architecture-infra.md`, `specs/architecture-frontend.md`, `specs/api-spec.md`, `specs/db-schema.md`
**Guards:** the **how** — service boundaries, communication patterns, DB schema, API contracts, infrastructure choices, security model.

### Responsibilities

- Architecture specs must reflect all non-obvious technical decisions. If a decision isn't in the spec, future implementors will guess wrong.
- Does **not** change what the product does — only how it's built. If a technical decision would change product behaviour, escalate to the Product Specialist first.
- The architecture specs must be internally consistent: API spec ↔ DB schema ↔ service architecture.

### Step 2.1 — Read relevant architecture specs

| Task area | Files to read |
|-----------|--------------|
| New backend service or endpoint | `specs/api-spec.md` relevant section + `specs/architecture-backend.md` relevant service |
| DB table or migration | `specs/db-schema.md` relevant section + `specs/architecture-backend.md` |
| Infrastructure change | `specs/architecture-infra.md` |
| Frontend screen or lib | `specs/architecture-frontend.md` |
| Security / auth change | `specs/architecture.md` section 3 |
| Communication pattern (Kafka/gRPC) | `specs/architecture.md` section 2 |

### Step 2.2 — Check for architecture spec gaps or conflicts

For the proposed change, answer each question:

1. **Is the new endpoint/method described in api-spec?** → If missing, add it.
2. **Are new DB tables/columns described in db-schema?** → If missing, add them.
3. **Does the proposed service interaction (gRPC call, Kafka topic, outbox event) match the existing patterns in architecture-backend?** → If it's a new interaction, document it.
4. **Does this introduce a new shared library, package, or infrastructure component?** → If yes, document it in the relevant architecture file.
5. **Does this change how auth, rate limiting, or secret storage works?** → If yes, update architecture.md section 3.
6. **Are there internal inconsistencies introduced** (e.g., api-spec says field X exists but db-schema doesn't have the column)? → Fix them.

### Step 2.3 — Update architecture specs if needed

For each gap or conflict found:
1. Edit the relevant spec file(s).
2. Keep changes minimal — document only what will actually be built, not hypothetical future extensions.
3. Write a one-line summary per file changed (for the commit message).

### Step 2.4 — Technical Architect sign-off

State clearly: **"Architecture review: [passed / updated: <file> — <summary>, ...]"**

Then proceed to Role 3.

---

## Role 3 — Project Manager

**Owns:** `specs/roadmap.md` + GitHub Issues
**Guards:** task existence, correctness of blockers, task scope, and sync between roadmap and GitHub.

### Responsibilities

- `specs/roadmap.md` is the authoritative task list. GitHub Issues mirror it — they don't drive it.
- Every task in the roadmap must have a corresponding open GitHub Issue.
- Tasks that no longer make sense (superseded, split, merged) are closed or updated.
- Blocker relationships in the roadmap DAG must be correct at all times.

### Step 3.1 — Read roadmap

Read `specs/roadmap.md`:
- Find where the proposed work fits in the DAG.
- Check what existing tasks it touches, blocks, or is blocked by.
- Check if the work is already covered by an existing task or needs a new one.

### Step 3.2 — Determine roadmap changes needed

For the proposed change, decide:

| Situation | Action |
|-----------|--------|
| Existing task covers the work exactly | No change needed |
| Existing task scope needs updating | Update description/criteria in roadmap |
| New work not covered by any task | Add new task to roadmap (assign next available I-N / D-N / F-N) |
| Task is now superseded or merged into another | Remove from DAG, update classDef |
| Blocker edges are wrong | Fix edges in the Mermaid graph |

### Step 3.3 — Update roadmap if needed

If roadmap changes are required, edit `specs/roadmap.md`:

**Adding a new task:**
1. Add node in the correct subgraph: `F-N[F-N<br/>Short label]`
2. Add dependency edges: `blocker --> F-N` and `F-N --> dependent` where applicable
3. Add to the `class` line at the bottom (func/infra/design)
4. Add a task description block in the flat list, in topological order, with:
   - Type, blockers, description, acceptance criteria
   - Use the same format as existing tasks

**Updating a task:** Edit the description block only. Do not renumber existing tasks.

**Removing a task:** Remove the node, edges, class entry, and description block. If it had a GitHub Issue, close it in Step 3.4.

### Step 3.4 — Sync GitHub Issues

After updating the roadmap, sync GitHub Issues using `gh` CLI:

**For each new task added to the roadmap:**
```bash
gh issue create --title "[F-N] Short label" --body "$(cat <<'BODY'
**Type:** функция / инфраструктура / дизайн
**Blockers:** F-X, I-Y (or —)

**Description:**
[paste task description from roadmap]

**Acceptance criteria:**
[paste criteria from roadmap]
BODY
)"
```

**For each task with updated description:**
```bash
gh issue edit <number> --body "..."
```

**For each removed task:**
```bash
gh issue close <number> --comment "Task removed from roadmap: [reason]"
```

**To find the issue number for a roadmap task:** search by title prefix:
```bash
gh issue list --search "[F-N]" --state open
```

### Step 3.5 — Project Manager sign-off

State clearly: **"Project Manager review: [passed / roadmap updated: <summary> / issues created: #N, #M / issues closed: #K]"**

---

## Step 4 — Commit All Spec Changes

After all three roles complete, commit any spec and roadmap changes together (before implementation):

```bash
git add specs/ .claude/
git commit -m "spec: <summary of what changed>

[one line per file changed, e.g.:]
- product-spec.md: [what changed]
- api-spec.md: [what changed]
- roadmap.md: [tasks added/updated/removed]
```

Do not mix spec commits with implementation commits.

---

## Step 5 — Hand Off to /implement

Once specs are committed and all three roles have signed off, invoke the `/implement` skill to begin implementation.

If the work was only a spec update (no code to write), stop here.

---

## Rules

- **Roles are sequential** — never run Role 2 before Role 1 signs off, never run Role 3 before Role 2 signs off.
- **Product Specialist cannot be skipped**, even for "pure technical" changes — the check takes 30 seconds and prevents silent scope creep.
- **Technical Architect cannot approve product changes** — if a technical decision would change what the product does, bounce back to Role 1.
- **Project Manager does not drive product decisions** — if a roadmap gap reveals a missing product feature, bounce back to Role 1.
- **GitHub Issues mirror roadmap, not the other way around** — never create an issue for work that isn't in the roadmap.
- **No Co-Authored-By** in any git commits.
