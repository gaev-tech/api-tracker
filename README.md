# api-tracker

AI-first таск-трекер: REST API + CLI + два Angular SPA (auth, docs).

## Документация

Источник правды — `specs/`:

- [`specs/product.md`](specs/product.md) — назначение, value proposition, доменная модель, права.
- [`specs/architecture.md`](specs/architecture.md) — топология, БД, аутентификация, контракты, деплой.
- [`specs/implementation-plan.md`](specs/implementation-plan.md) — план реализации M0..M4.
- [`specs/cli-test-cases.md`](specs/cli-test-cases.md) — каталог сценариев CLI.

## Структура

```
backend/
  tasks-service/   — FastAPI, основная бизнес-логика
  auth-service/    — FastAPI, аутентификация (с M2)
cli/               — Python typer, CLI клиент `clite`
contracts/
  proto/           — gRPC protobuf
  openapi/         — авто-экспорт OpenAPI из сервисов
frontend/
  projects/
    auth-client/   — Angular 20 (с M2)
    docs-client/   — Angular 20 (с M4)
deploy/            — docker-compose, nginx, certbot, scripts
specs/             — спецификации
.github/workflows/ — CI/CD
```

## Локальная разработка

См. [`SETUP.md`](SETUP.md) для серверной настройки и GHA-секретов.

```bash
# Python (uv)
uv sync
uv run pytest

# Angular
cd frontend && npm install --registry https://registry.npmjs.org/
npm run build
```

## Production

Единый домен `cliteracker.ru` с path-based маршрутизацией (см. `specs/architecture.md` §2):

- `/` — docs-client (справка, M4)
- `/auth/` — auth-client (браузерная аутентификация, M2)
- `/api/v1/*` — tasks-svc REST (CLI)
- `/api/auth/*` — auth-svc REST (M2)
- `/healthz` — мониторинг

Деплой автоматический на push в `main`.
