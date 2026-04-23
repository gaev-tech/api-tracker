# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This project is currently in the **specification phase** — only `specs/` exists. All implementation is planned but not yet written. The specs directory is the source of truth.

## Specification Files

| File | Contents |
|------|----------|
| `specs/product-spec.md` | Product overview, clients, requirements (MVP + PostMVP), tariffs, access model, events, RSQL, function catalog, UI functions, CLI commands |
| `specs/architecture-api.md` | Microservices, tech stack, services responsibilities, Kafka/gRPC communication, security, DB strategy, infra, observability, CI/CD |
| `specs/architecture-ui.md` | Angular Workspace (app + docs), libs, design system, API client codegen, multi-auth, WebSocket, routing, UI patterns |
| `specs/architecture-cli.md` | CLI structure, auth, config, output formats, pagination, distribution |
| `specs/api-spec.md` | REST API conventions, complete endpoint catalog, data model definitions, error codes |
| `specs/roadmap.md` | Implementation tasks grouped by area (INFRA, API, CLI, DOCS, UI) with dependencies and MVP/PostMVP labels |

## Planned Build Commands

Once implemented, the monorepo will be structured as:

**Backend (Go):**
```bash
# Per-service, from backend/services/<service>/
go build ./...
go test ./...
go vet ./...

# Proto/gRPC codegen (from contracts/)
buf generate
```

**Frontend (Angular + TypeScript):**
```bash
npm --registry https://registry.npmjs.org/ install
npm run build
npm run lint
npm test
```

**Local dev:**
```bash
docker compose up  # from deploy/
```

**DB migrations:** Run automatically on service startup via readiness probe.

## Architecture Overview

API-first microservices system (Go + Kafka + gRPC + PostgreSQL/Citus). UI and CLI are plain API clients with no privileges. See `specs/architecture-api.md`, `specs/architecture-ui.md`, `specs/architecture-cli.md` for details.

### Key Domain Concepts

- **Task access** = union of personal rights + team-based rights + direct (task-level) rights — 14 distinct rights (R-1..R-14). Reading is determined by context, not a separate right.
- **Tasks exist** while attached to at least one project OR having at least one direct access with any right.
- **Tariff system** freezes entities (newest first by `created_at`) when usage limits are exceeded.
- **RSQL** is used for all list/filter endpoints; supports `me` literal for `assignee`/`author`.
- **Cursor-based pagination** throughout the API; tasks always sorted `created_at asc`.
