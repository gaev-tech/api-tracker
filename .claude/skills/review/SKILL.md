---
name: review
description: Two-phase review skill. Phase 1 (pre-implementation): Product Specialist → Technical Architect → Project Manager update specs/roadmap, then hand off to /implement. Phase 2 (post-implementation): same three roles verify the merged result and close completed work.
user-invocable: true
---

# api-tracker: Review Workflow

## Overview

Two phases, same three roles, same order every time:

```
Phase 1 — PRE-IMPLEMENTATION
  Product Specialist → Technical Architect → Project Manager → /implement

Phase 2 — POST-IMPLEMENTATION
  Product Specialist → Technical Architect → Project Manager → done
```

Invoke `/review` with the current context:
- **Before work starts** → Phase 1 runs.
- **After implementation is merged** → Phase 2 runs.

If invoked ambiguously, ask: "Pre- or post-implementation review?"

---

# PHASE 1 — Pre-Implementation

Runs before any code is written. Each role updates specs/roadmap to reflect the planned work, then hands off to `/implement`.

---

## Role 1 — Product Specialist (pre)

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

### Step 1.4 — Sign-off

State clearly: **"Product Specialist (pre): [passed / updated product-spec: <summary>]"**

Then proceed to Role 2.

---

## Role 2 — Technical Architect (pre)

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

### Step 2.4 — Sign-off

State clearly: **"Technical Architect (pre): [passed / updated: <file> — <summary>, ...]"**

Then proceed to Role 3.

---

## Role 3 — Project Manager (pre)

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

| Situation | Action |
|-----------|--------|
| Existing task covers the work exactly | No change needed |
| Existing task scope needs updating | Update description/criteria in roadmap |
| New work not covered by any task | Add new task (assign next available I-N / D-N / F-N) |
| Task is now superseded or merged into another | Remove from DAG, update classDef |
| Blocker edges are wrong | Fix edges in the Mermaid graph |

### Step 3.3 — Update roadmap if needed

**Adding a new task:**
1. Add node in the correct subgraph: `F-N[F-N<br/>Short label]`
2. Add dependency edges: `blocker --> F-N` and `F-N --> dependent` where applicable
3. Add to the `class` line at the bottom (func/infra/design)
4. Add a task description block in the flat list, in topological order

**Updating a task:** Edit the description block only. Do not renumber existing tasks.

**Removing a task:** Remove node, edges, class entry, and description block. Close GitHub Issue in Step 3.4.

### Step 3.4 — Sync GitHub Issues

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

**To find issue number for a roadmap task:**
```bash
gh issue list --search "[F-N]" --state open
```

### Step 3.5 — Sign-off

State clearly: **"Project Manager (pre): [passed / roadmap updated: <summary> / issues created: #N / issues closed: #K]"**

---

## Phase 1 — Step 4: Commit All Spec Changes

After all three roles complete, commit any spec and roadmap changes together (before implementation):

```bash
git add specs/ .claude/
git commit -m "spec: <summary of what changed>

- product-spec.md: [what changed, if anything]
- api-spec.md: [what changed, if anything]
- roadmap.md: [tasks added/updated/removed, if anything]"
```

Do not mix spec commits with implementation commits.

## Phase 1 — Step 5: Hand Off to /implement

Once specs are committed and all three roles have signed off, invoke the `/implement` skill.

If the work was only a spec/roadmap update (no code to write), stop here.

---
---

# PHASE 2 — Post-Implementation

Runs after the implementation branch is merged (or the PR is ready to merge). Each role verifies the result against the specs, then the PM closes completed work and cleans up open PRs.

---

## Role 1 — Product Specialist (post)

**Goal:** Verify that what was built matches what product-spec says should exist. Catch silent deviations — things that were implemented differently from spec without the spec being updated.

### Step 1.1 — Read the relevant product-spec sections

Same table as Phase 1 Step 1.1. Read the sections relevant to the implemented task.

### Step 1.2 — Review the implementation

Read the diff (via `git diff main...<branch>` or the merged PR) and answer:

1. **Does the implemented behaviour match product-spec exactly?**
   - All features described in the spec are present in the code.
   - No features were silently added that aren't in the spec.
   - No features were silently dropped or changed in meaning.

2. **Do user-visible field names, statuses, and values match the spec?**
   - Enum values, status names, right identifiers (R-1..R-14) match.
   - Error messages and codes match.

3. **Are edge cases described in product-spec handled?**
   - E.g. "task auto-deleted when last project detached and no direct accesses" — is this actually in the code?

### Step 1.3 — Handle deviations

| Deviation type | Action |
|---------------|--------|
| Implementation does more than spec says | Update product-spec to reflect the extra behaviour, or raise for removal from code |
| Implementation does less than spec says | Raise as a bug — open a new GitHub Issue for the gap |
| Implementation differs from spec (different logic) | Decide: update spec to match code, or raise as a bug. Either way, they must agree. |
| No deviations | Proceed |

If spec is updated: commit the change with message `spec: post-impl sync — product-spec: <what changed>`.

### Step 1.4 — Sign-off

State clearly: **"Product Specialist (post): [passed / deviations found: <summary> / spec updated / bug raised: #N]"**

Then proceed to Role 2.

---

## Role 2 — Technical Architect (post)

**Goal:** Verify that the implementation follows the architecture, API contracts, and DB schema. Catch patterns used incorrectly, undocumented design decisions baked into code, and spec drift.

### Step 2.1 — Read the relevant architecture specs

Same table as Phase 1 Step 2.1.

### Step 2.2 — Review the implementation

Read the diff and answer:

1. **Do new HTTP endpoints match api-spec exactly?** (path, method, request/response shape, error codes, pagination style)
2. **Do new DB tables/columns match db-schema exactly?** (column names, types, nullable, indexes, constraints)
3. **Are gRPC methods and Kafka events consistent with architecture-backend?** (service that publishes, topic name, consumers documented)
4. **Are shared packages used correctly?** (outbox for events, pkg/grpc wrappers, pkg/logging fields, pkg/metrics middleware)
5. **Are any tech decisions made in code that aren't in the specs?** (new library, new pattern, new infra component) → If yes, document them.
6. **Are migrations reversible and backward-compatible?** (new nullable columns, no destructive changes without multi-step rollout)
7. **Are there any security concerns?** (missing auth check, secret logged, MIME bypass, SQL injection surface)

### Step 2.3 — Handle deviations

| Deviation type | Action |
|---------------|--------|
| Code doesn't match api-spec | Raise as a bug (wrong implementation) or update spec if the code is actually better |
| Undocumented tech decision in code | Update the relevant architecture spec to document it |
| Pattern used incorrectly (e.g. direct Kafka write instead of outbox) | Raise as a bug |
| Missing migration backward-compat | Raise as a bug before merge |
| No deviations | Proceed |

If spec is updated: commit with message `spec: post-impl sync — <file>: <what changed>`.

### Step 2.4 — Sign-off

State clearly: **"Technical Architect (post): [passed / deviations found: <summary> / spec updated / bugs raised: #N, #M]"**

Then proceed to Role 3.

---

## Role 3 — Project Manager (post)

**Goal:** Close completed work. No completed task should stay open; no stale PR should be left dangling.

### Step 3.1 — Close the completed GitHub Issue

Find the issue for the task just implemented:
```bash
gh issue list --search "[F-N]" --state open
```

Close it, referencing the merged PR:
```bash
gh issue close <number> --comment "Implemented in #<PR-number>. Closing."
```

### Step 3.2 — Verify the PR is merged or close it

Check if the implementation PR is already merged:
```bash
gh pr view <number> --json state,mergedAt
```

- If merged — nothing to do.
- If open and approved — merge it:
  ```bash
  gh pr merge <number> --squash --delete-branch
  ```
- If open and stale (no activity in >7 days, blockers not resolved) — close it:
  ```bash
  gh pr close <number> --comment "Closing stale PR. Re-open when blockers are resolved."
  ```

### Step 3.3 — Audit open PRs

List all open PRs and check for staleness:
```bash
gh pr list --state open
```

For each open PR:

| State | Action |
|-------|--------|
| Approved, all checks pass | Merge if PM decision is to ship, otherwise leave and note |
| Changes requested, author inactive >7 days | Comment asking for update; close if no response in 3 days |
| Draft | Leave — work in progress |
| CI failing | Check if fixable; if blocking merge, raise to Technical Architect |
| No corresponding roadmap task | Ask: is this work planned? If not, close with explanation |

### Step 3.4 — Sign-off

State clearly: **"Project Manager (post): [issue #N closed / PR #M merged or closed / open PRs audited: <summary of any actions taken>]"**

---

## Phase 2 — Final

After all three post-implementation roles complete:

1. If any spec was updated in post-implementation review, commit it on a branch and open a PR:
   ```bash
   git checkout -b spec/[task-id]-post-impl-sync
   git add specs/
   git commit -m "spec: post-impl sync for [task-id]

   - [file]: [what changed]"
   git push -u origin spec/[task-id]-post-impl-sync
   gh pr create --title "spec: post-impl sync for [task-id]" --body "..."
   ```
   PM merges the PR (same as all other PRs — never push directly to main).

2. Confirm: all three roles signed off, issue closed, PR merged or closed, no stale PRs.

---

# Rules (both phases)

- **Roles are sequential** — never run Role 2 before Role 1 signs off; never run Role 3 before Role 2 signs off.
- **Product Specialist cannot be skipped**, even for "pure technical" tasks.
- **Technical Architect cannot approve product changes** — bounce back to Role 1.
- **Project Manager does not drive product decisions** — bounce back to Role 1 if a gap reveals a missing feature.
- **GitHub Issues mirror roadmap** — never create an issue for work that isn't in the roadmap.
- **Bugs found in post-review** are new GitHub Issues, not edits to the completed task.
- **Spec updates from post-review** are committed separately from any new implementation.
- **No Co-Authored-By** in any git commits.
