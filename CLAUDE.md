# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This project is currently in the **specification phase** — only `specs/` exists. All implementation is planned but not yet written. The specs directory is the source of truth.

## Specification Files

| File | Contents |
|------|----------|
| `specs/product-spec.md` | Product overview, entity catalog, feature catalog, tariff system, access rights model |
| `specs/architecture.md` | Technology stack, high-level diagram, communication patterns (Kafka/gRPC), security |
| `specs/architecture-backend.md` | All 7 services (responsibilities, gRPC, Kafka topics, DB), DB strategy, migrations |
| `specs/architecture-infra.md` | Kubernetes, observability (Prometheus/Grafana/Sentry/Loki), CI/CD, monorepo structure, scaling |
| `specs/architecture-frontend.md` | Angular Workspace, design system, API-client codegen, multi-auth, WebSocket, Docker/K8s deploy |
| `specs/api-spec.md` | REST API conventions, complete endpoint catalog, data model definitions, error codes |
| `specs/db-schema.md` | PostgreSQL/Citus physical schema, all tables with columns/indexes, naming conventions |
| `specs/ui-spec.md` | Screen layouts, widget catalog, UI principles |
| `specs/roadmap.md` | DAG of implementation tasks (I-*, D-*, F-* prefixes) with dependencies and topological order |

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

API-first microservices system. All functionality is available through REST API; UI is secondary validation surface.

### Services

| Service | Responsibility | Database |
|---------|---------------|----------|
| `identity-service` | Auth, PATs, managed users | PostgreSQL |
| `workspace-service` | Projects, teams, tasks, access control | Citus (sharded on author/owner ID) |
| `automations-service` | Event-triggered automations with RSQL conditions + HTTP actions | Citus |
| `events-service` | Event log storage + event feed API | Citus (partitioned by month) |
| `billing-service` | Tariffs, subscriptions, usage counters, ЮKassa payments | PostgreSQL |
| `files-service` | File uploads/downloads to S3-compatible storage | PostgreSQL |
| `api-gateway` | Nginx reverse proxy — PAT validation via `auth_request`, rate limiting | — |

### Communication Patterns

- **Async:** Kafka with transactional outbox pattern. Services publish domain events; consumers maintain denormalized caches (`users_cache` in workspace, `tasks_cache` in automations).
- **Sync:** gRPC with 5s timeouts; retries only for idempotent operations.
- **Public:** HTTP/JSON via api-gateway with Bearer PAT token.
- **Observability:** `request_id` propagates through all HTTP, gRPC, and Kafka calls.

### Key Domain Concepts

- **Task access** = union of personal rights + team-based rights + direct (task-level) rights — 14 distinct rights (R-1..R-14).
- **Tasks are not required to belong to a project** — they can exist standalone via direct access.
- **Tariff system** blocks entities (tasks, projects, etc.) when usage limits are exceeded; blocked state fires Kafka events that can trigger automations.
- **RSQL** (REST Query String Language) is used for all list/filter endpoints.
- **Cursor-based pagination** throughout the API (no offset pagination).

### Monorepo Layout (planned)

```
backend/
  services/<service>/   # per-service Go module + Dockerfile + migrations/
  pkg/                  # shared Go libs (outbox, grpc, kafka, logging, service-template)
  go.work
frontend/
  projects/app/         # Angular app
  projects/docs/        # Documentation landing
  libs/                 # Shared Angular libs (design-system, api-client, rsql, etc.)
contracts/
  proto/                # gRPC .proto files
  openapi/              # Generated openapi.yaml
deploy/
  helm/                 # Helm charts per service
  docker-compose.yml
specs/                  # All specification documents
```

### Infrastructure

- **Kubernetes** (production), **Docker Compose** (local dev)
- **CI/CD:** GitHub Actions + GitHub Container Registry (ghcr.io) + Helm
- **Observability:** Prometheus + Grafana + Sentry + Loki/Promtail
- **Migrations:** Goose or golang-migrate, embedded per service, run at startup
