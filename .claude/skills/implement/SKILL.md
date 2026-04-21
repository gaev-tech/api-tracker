---
name: implement
description: Use for any implementation task in the api-tracker project — reads relevant specs, asks clarifying questions, builds a full file-level plan, then applies all changes at once after approval.
user-invocable: true
---

# api-tracker: Implementation Workflow

## When to Use

Any time a task from the roadmap (I-*, D-*, F-*) or any other feature/fix is being implemented in this project.

**Prerequisites:** The `/review` skill must have completed before this skill is invoked. All three roles (Product Specialist, Technical Architect, Project Manager) must have signed off, and any spec/roadmap changes must already be committed.

---

## Step 1 — Read the Specs

Before doing anything else, identify which spec files are relevant to the task and read them:

| Task type | Spec files to read |
|-----------|-------------------|
| API endpoint, business logic | `specs/api-spec.md`, `specs/architecture.md`, `specs/architecture-backend.md` |
| Database table, migration | `specs/db-schema.md`, `specs/architecture-backend.md` |
| UI screen or component | `specs/ui-spec.md`, `specs/api-spec.md`, `specs/architecture-frontend.md` |
| Auth, users, PAT | `specs/api-spec.md` section Auth + `specs/architecture-backend.md` identity-service |
| Billing, tariffs | `specs/api-spec.md` section Billing + `specs/db-schema.md` |
| Automations | `specs/api-spec.md` section Automations + `specs/architecture-backend.md` |
| Infrastructure (I-* tasks) | `specs/architecture-infra.md`, `specs/architecture.md` |
| Frontend infra (F-74..F-80) | `specs/architecture-frontend.md`, `specs/architecture.md` |
| Design tokens, components | `specs/ui-spec.md`, `specs/architecture-frontend.md` |
| Any task | `specs/roadmap.md` — check blockers and what the task depends on |

Read only the relevant sections, not entire files.

---

## Step 2 — Ask Clarifying Questions

After reading the specs, ask the user clarifying questions **before writing any plan**. Focus on:

- Ambiguities in the spec that affect the implementation approach
- Edge cases that the spec doesn't explicitly address
- Technology choices where multiple valid options exist
- Integration points with other services (sync vs async, gRPC vs HTTP)
- Whether stubs/заглушки are acceptable for this iteration or full implementation is required
- Scope: exactly what is and isn't included in this task

Keep it to 3–6 questions max. Use numbered options (1/2/3) where the answer is a choice between alternatives. Do not ask questions whose answers are clearly specified in the spec.

Wait for the user to answer before proceeding.

---

## Step 2.5 — Update Specs Before Planning

After the user answers all clarifying questions, **before writing the plan**:

1. Identify which answers represent decisions not yet reflected in the specs
2. Update the relevant spec files (`specs/api-spec.md`, `specs/architecture.md`, `specs/db-schema.md`, etc.) to document those decisions
3. Commit the spec changes separately — do not mix spec updates with implementation commits
4. Re-read the updated sections and **repeat Step 2** if the spec changes surface new ambiguities

Only proceed to Step 3 once the specs are up to date.

**Why:** Specs and implementation must never diverge. Updating specs first ensures the plan is derived from accurate documentation, not from temporary decisions held only in conversation context.

---

## Step 3 — Write the Plan

Produce a plan in this exact format:

```
## Plan: [Task name]

### What we're building
[2–4 sentences describing the outcome]

### Spec references
- [File]: [relevant section or line range]
- ...

### File changes

**Added:**
- `path/to/new/file.go` — [what it contains]
- `path/to/migration.sql` — [table/columns being added]

**Modified:**
- `path/to/existing/file.go` — [what changes: new function, updated struct, etc.]
- `path/to/router.go` — [new routes registered]

**Removed:**
- `path/to/stub.go` — [reason: replaced by real implementation]

### Implementation order
1. [First thing to do and why]
2. [Second thing]
3. ...

### Open questions / assumptions
- [Any assumption made due to spec ambiguity]
- [Any decision made and rationale]
```

**Rules for the plan:**
- Every file that will be touched must appear in the list — no surprises during implementation
- Migration files always listed explicitly with the table/columns they create or alter
- If a file is both created and immediately used by another file, list the dependency in the order
- No code in the plan — only descriptions of what will go where
- If blockers (from the roadmap) are not yet implemented, call them out explicitly as stubs

Present the plan and wait for explicit approval: "approve", "go", "ок", "да", or similar.

---

## Step 4 — Apply All Changes

Only after the user approves the plan:

1. Apply **all** file changes from the plan in one pass — do not pause between files asking for approval
2. Follow the implementation order from the plan
3. After all files are written, run a build/lint check if applicable:
   - Backend: `go build ./...` and `go vet ./...` from the service directory
   - Frontend: `npm run build` and `npm run lint` from `frontend/`
4. If the build/lint fails, diagnose and fix before reporting completion
5. Report completion with a summary of exactly what was created/modified/removed
6. Remind the user to run `/review` (Phase 2 — post-implementation) after the PR is merged

---

## Rules

- **Never skip Step 1** (read specs) — even for "obvious" tasks
- **Never skip Step 2** (clarifying questions) — even one question is better than a wrong assumption
- **Never skip Step 2.5** (update specs) — specs must reflect decisions before implementation begins
- **Never start coding before the plan is approved**
- **Apply all plan changes at once** — do not implement half the plan and ask what to do next
- **No Co-Authored-By** lines in any git commits
- If during implementation you discover the plan needs to change (e.g., a file requires a different approach), stop, describe the deviation, and get approval before continuing
- Stub implementations must be clearly marked with `// TODO: [task-id]` comments
