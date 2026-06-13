---
name: prod-access
description: Connect to the api-tracker production server (apitracker.ru / 91.218.114.168) for diagnostics, log reading, container inspection. Use when needing to verify deploy status, read service logs, check container health, or troubleshoot prod issues that the public HTTP surface can't reveal.
---

# Prod Access — api-tracker

## How to connect

Prod is at **`91.218.114.168`** (DNS: `apitracker.ru`, `api.apitracker.ru`).
SSH as **`root`** using **`~/.ssh/id_ed25519`** (already authorized).

```bash
ssh -i ~/.ssh/id_ed25519 -o BatchMode=yes root@91.218.114.168 '<command>'
```

The deploy GHA workflow uses a separate `deploy@` user with `DEPLOY_SSH_KEY` secret — that key is **not** on this machine. Always use `root@` for diagnostics.

## Stack layout on the host

| Component | Where |
|-----------|-------|
| Compose project | `/opt/api-tracker/repo/deploy/` |
| Containers | `api-tracker-{tasks-svc, auth-svc, postgres, nginx, certbot}` |
| Nginx config | `/opt/api-tracker/repo/deploy/nginx/conf.d/apitracker.ru.conf` (mounted into nginx container) |
| Letsencrypt | `/opt/api-tracker/repo/deploy/certbot/` |
| Deploy script | `/opt/api-tracker/repo/deploy/scripts/pull-and-up.sh` |

## Common diagnostic commands

```bash
# Container status
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 \
  'docker ps --format "{{.Names}}\t{{.Status}}"'

# Service logs (tasks-svc | auth-svc | nginx | postgres)
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 \
  'docker logs --tail=100 api-tracker-auth-svc 2>&1'

# Image SHA actually running
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 \
  'docker inspect api-tracker-auth-svc --format "{{.Image}} {{.Config.Image}}"'

# Postgres query
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 \
  'docker exec api-tracker-postgres psql -U postgres -d tasks -c "select count(*) from tasks;"'

# Nginx config check / reload
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 'docker exec api-tracker-nginx nginx -t'
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 'docker exec api-tracker-nginx nginx -s reload'

# Pull latest images + recreate (manual deploy)
ssh -i ~/.ssh/id_ed25519 root@91.218.114.168 \
  'cd /opt/api-tracker/repo/deploy && ./scripts/pull-and-up.sh'
```

## Public URL conventions (important!)

Nginx routes paths to upstreams differently — **don't confuse smoke-test URLs**:

| Public path | Routes to | Notes |
|-------------|-----------|-------|
| `/healthz` | tasks-svc `/healthz` | no auth |
| `/v1/*` | tasks-svc `/v1/*` | auth_request → JWT required |
| `/api/auth/*` | auth-svc `/auth/*` (strips `/api`) | public REST |
| `/api/auth/healthz` | auth-svc `/healthz` | no auth |
| `/auth/*` (browser) | **static 503 "auth-client coming in M2"** | placeholder for SPA |
| `/docs/*` (browser) | static 503 "docs-client coming in M4" | placeholder |

**If you see 503 with "coming in M*" body — you hit the placeholder, not a real service. Switch to the `/api/*` path.**

## Auth-classifier behavior

Even with SSH allowed, the harness's **auto-mode classifier separately gates "Production Read" actions** (logs, container state, DB queries). It will block the first such call with a "user did not explicitly authorize this prod log dump" message.

To proceed: ask the user for one-shot authorization via `AskUserQuestion` before the first prod-read of the session, then continue freely until the session ends.

## When NOT to use prod-access

- For deploys: push to `main`; GHA handles it. Don't run `docker compose up` from SSH unless GHA is broken.
- For DB schema changes: write an Alembic migration; it runs on service startup via readiness probe. Don't `ALTER TABLE` directly.
- For config changes: edit `deploy/nginx/...` or `docker-compose.prod.yml`, commit, push. The pull-and-up script reloads nginx automatically.
- For secrets: rotate via `gh secret set`; never hand-edit `/opt/api-tracker/.env` and expect it to persist a redeploy.
