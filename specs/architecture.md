# Архитектура

Все ссылки вида (PRD §X) — на `product.md`. Все ссылки вида (TC §Y) — на `cli-test-cases.md`. (IPLAN §Z) — на `implementation-plan.md`.

## 1. Топология процессов

### 1.1 Сервисы и контейнеры (docker-compose на проде)

1.1.1 `nginx` — TLS-терминация, маршрутизация (см. 2).

1.1.2 `postgres` — единственный инстанс БД (см. 3).

1.1.3 `tasks-svc` — FastAPI, основная бизнес-логика.

1.1.4 `auth-svc` — FastAPI, регистрация и сессии (поднимается с M2, см. IPLAN §4).

1.1.5 `auth-client` — статика Angular, отдаётся через nginx (с M2).

1.1.6 `docs-client` — статика Angular, отдаётся через nginx (с M4).

1.1.7 `certbot` — авторенью Let's Encrypt сертификатов.

### 1.2 Сетевая изоляция

1.2.1 Compose-сеть `internal` соединяет `tasks-svc`, `auth-svc`, `postgres`; не выставляется наружу.

1.2.2 `nginx` имеет доступ в `internal` и слушает 80/443 на внешнем интерфейсе.

1.2.3 gRPC-канал tasks-svc ↔ auth-svc — внутри `internal`, порт 50051 на обоих сервисах.

## 2. Сетевая маршрутизация

2.1 `apitracker.ru` → 301 → `docs.apitracker.ru`.

2.2 `docs.apitracker.ru/` → docs-client (статика).

2.3 `auth.apitracker.ru/` → auth-client (статика).

2.4 `auth.apitracker.ru/api/*` → auth-svc (REST).

2.5 `api.apitracker.ru/*` → tasks-svc (REST).

2.6 Внутри compose: `tasks-svc:50051` ↔ `auth-svc:50051` (gRPC).

## 3. База данных

3.1 Один Postgres, две логические схемы: `auth` и `tasks`.

3.2 БД-пользователи:

3.2.1 `auth_app` — read/write только на схему `auth`.

3.2.2 `tasks_app` — read/write только на схему `tasks`.

3.3 Миграции — Alembic; запуск в entrypoint сервиса с advisory-lock против race при rolling-up.

3.4 Бэкап: `pg_dump` cron-ом ежедневно в 03:00 UTC, ретенция 14 дней, в `/var/backups/api-tracker/`.

### 3.5 Схема `tasks`

3.5.1 `users(user_id, email)` — кеш, наполняется gRPC-резолвом из auth-svc.

3.5.2 `tasks(id, title, description_md, labels[], status, assignee_id, created_at)`.

3.5.3 `task_blockers(task_id, blocked_by_task_id)`.

3.5.4 `task_user_shares(task_id, user_id, perms[])`.

3.5.5 `task_team_shares(task_id, team_id, perms[])`.

3.5.6 `teams(id, name, created_at)`.

3.5.7 `team_members(team_id, user_id, perms[])`.

3.5.8 `projects(id, name, created_at)`.

3.5.9 `project_user_members(project_id, user_id, perms[])`.

3.5.10 `project_team_members(project_id, team_id, perms[])`.

3.5.11 `project_tasks(project_id, task_id)`.

3.5.12 `automations(id, project_id, name, trigger_type, trigger_config, action_type, action_config, created_at)`.

3.5.13 `project_secrets(id, project_id, name, value_encrypted, created_at)`.

3.5.14 `audit_events(id, actor_user_id, target_type, target_id, event_type, payload_json, created_at)`.

3.5.15 `event_log(id, source_task_id, event_type, payload_json, created_at, processed_at)`.

3.5.16 `webhook_outbox(id, automation_id, attempt, scheduled_at, status, last_error, payload_json)`.

### 3.6 Схема `auth`

3.6.1 `users(id, email, created_at)`.

3.6.2 `magic_tokens(token_hash, email, intent, expires_at, used_at)`.

3.6.3 `refresh_tokens(id, user_id, kind, label, created_at, revoked_at, expires_at)`.

3.6.4 `sessions(refresh_token_id, last_seen_at, user_agent)`.

3.6.5 `cli_auth_codes(state, code_challenge, code, code_used_at, expires_at, user_id)`.

3.6.6 `device_codes(device_code, user_code, expires_at, user_id, approved_at)`.

## 4. Аутентификация

### 4.1 Режимы

4.1.1 `AUTH_MODE=disabled` (M0–M1): middleware tasks-svc игнорирует токен, проставляет `request.user_id = SOLO_USER.id`.

4.1.2 `AUTH_MODE=jwt` (M2+): middleware валидирует JWT по JWKS, проставляет `request.user_id`.

4.1.3 SOLO_USER создаётся при первом старте tasks-svc с `AUTH_MODE=disabled` в `tasks.users` (auth-svc может ещё не существовать).

### 4.2 Magic-link

4.2.1 `POST /api/magic/start {email, intent}` — генерит токен (32 байта random), хранит хеш в `auth.magic_tokens`, TTL 15 мин.

4.2.2 SMTP отправляет письмо с ссылкой `https://auth.apitracker.ru/magic?token=<plain>&intent=<intent>`.

4.2.3 `POST /api/magic/verify {token, intent}` — проверяет хеш, expiry, флаг `used_at`; помечает использованным; создаёт пользователя если нет; создаёт сессию (refresh + access).

### 4.3 CLI handoff (Pattern A — local callback, основной)

4.3.1 `apit login`:

4.3.1.1 Генерит state (random), code_verifier (random), code_challenge = SHA256(verifier).

4.3.1.2 Стартует локальный HTTP-сервер на `127.0.0.1:<rnd_port>`.

4.3.1.3 Открывает в браузере `https://auth.apitracker.ru/cli-login?state=...&redirect=http://127.0.0.1:<port>/cb&code_challenge=...`.

4.3.2 Auth-client после успешного логина показывает confirmation; на согласии `POST /api/cli/code {state, code_challenge}` → возвращает одноразовый `code`.

4.3.3 Auth-client редиректит браузер на `http://127.0.0.1:<port>/cb?state=...&code=...`.

4.3.4 CLI ловит callback, `POST /api/cli/exchange {code, code_verifier}` → `{access_token, refresh_token}`.

4.3.5 CLI сохраняет токены в keychain ОС или fallback `~/.config/apit/credentials` 0600.

### 4.4 CLI handoff (Pattern B — device code, fallback)

4.4.1 `apit login --device`:

4.4.1.1 `POST /api/cli/device-start` → `{device_code, user_code, verification_url, interval}`.

4.4.1.2 CLI печатает: "Открой <url>, введи код <user_code>".

4.4.2 Пользователь подтверждает в auth-client → `POST /api/cli/device-approve {user_code}`.

4.4.3 CLI поллит `POST /api/cli/device-poll {device_code}` каждые `interval` сек → `{access_token, refresh_token}` либо ошибка `authorization_pending` / `expired`.

### 4.5 JWT-формат

4.5.1 Алгоритм RS256.

4.5.2 Claims: `sub` (user_id UUID), `email`, `iat`, `exp` (1 час от iat).

4.5.3 Никаких прав в токене.

4.5.4 Приватный ключ — env `JWT_PRIVATE_KEY_B64` в auth-svc; публичный ключ публикуется через gRPC `GetJWKS` (см. 6.3).

### 4.6 Refresh-flow

4.6.1 Access TTL 1 час; refresh TTL 30 дней.

4.6.2 Любой refresh ротирует refresh-token (старый помечается `revoked_at`, выдаётся новый).

4.6.3 Browser: `POST /api/auth/refresh` (cookie); CLI: `POST /api/cli/refresh {refresh_token}`.

### 4.7 Сессии

4.7.1 Все refresh-токены пользователя видны в auth-client → `/sessions`.

4.7.2 Каждая помечена `kind` (`browser` | `cli`), `label`, `created_at`, `last_seen_at`.

4.7.3 Revoke по UI или `apit logout`.

## 5. Контракты и кодоген

### 5.1 REST OpenAPI

5.1.1 Источник правды — Pydantic-модели и FastAPI-эндпоинты с аннотациями типов.

5.1.2 `/openapi.json` экспортируется каждым сервисом.

5.1.3 CI-шаг `dump-openapi` поднимает сервис в test-mode, дампит `/openapi.json` в `contracts/openapi/{auth,tasks}.json`.

5.1.4 Custom OpenAPI extension `x-rsql-fields` на list/bulk эндпоинтах — описание разрешённых RSQL-полей и их операторов.

### 5.2 Frontend кодоген

5.2.1 Инструмент — `orval`.

5.2.2 Вход — `contracts/openapi/{auth,tasks}.json`.

5.2.3 Выход — TS-типы моделей, Angular HttpClient-сервисы, zod-схемы валидации.

5.2.4 Сгенерированный код в `frontend/<app>/src/generated/`; коммитится в репо.

5.2.5 CI-гейт: `npm run gen:api` локально; если изменения — git diff в PR; красный PR если есть несогласованность.

### 5.3 Zod runtime-валидация

5.3.1 Все ответы API проходят через zod-схему в `api.service.ts`.

5.3.2 Чтения из localStorage/sessionStorage/IndexedDB — через zod.

5.3.3 URL query-params в роут-резолверах — через zod.

5.3.4 Принцип: любая граница "снаружи → внутрь" SPA = zod.

### 5.4 gRPC protobuf

5.4.1 Источник — `contracts/proto/auth.proto`.

5.4.2 Линтинг и breaking-change проверка — `buf`.

5.4.3 Python кодоген — `grpc_tools.protoc` + `mypy-protobuf` для аннотаций.

5.4.4 Сгенерированный код в `backend/auth-service/generated/grpc_pb/` и `backend/tasks-service/generated/grpc_pb/`; коммитится.

## 6. Внутренние API (gRPC auth-svc → tasks-svc)

6.1 `GetUserByEmail(email) → User{id, email}` — резолв при создании шаринга и назначении.

6.2 `GetUsersByIds(ids[]) → Users[]` — батчевая гидрация при ответе CLI (резолв id → email).

6.3 `GetJWKS() → JWKS` — публичные ключи для верификации JWT; tasks-svc кеширует in-process, обновляет фоновой таской раз в 5 минут.

## 7. Публичные REST API

7.1 Базовый префикс tasks-svc: `https://api.apitracker.ru/v1/`.

7.2 Базовый префикс auth-svc: `https://auth.apitracker.ru/api/`.

7.3 Эндпоинты поэлементно не перечисляются: генерируются из FastAPI кода в OpenAPI (см. 5.1). Соответствие сценариям PRD §7 контролируется через тесты и `cli-test-cases.md`.

## 8. RSQL

8.1 Подмножество v1 — см. PRD §7.1.3.

8.2 Парсер — Python-библиотека; кандидаты определяются на M1 (`pyrsql`, ручная PEG-реализация).

8.3 Допустимые поля per-entity определяются OpenAPI extension `x-rsql-fields` (см. 5.1.4) и whitelist в коде сервиса.

8.4 Литерал `me` резолвится в `request.user_id` через email-лукап.

8.5 Невалидный RSQL → `400` с указанием позиции ошибки в строке.

## 9. Bulk vs Batch

9.1 Bulk (PRD §7.2): цикл по совпавшим задачам, каждая в отдельной транзакции; ответ 200 даже при наличии неуспешных позиций; статус каждой — в массиве `results`.

9.2 Batch (PRD §7.3): одна транзакция; первое же исключение по правам/валидации → rollback и 400.

9.3 Ограничение: bulk и batch ограничены 10 000 совпавших задач на запрос; при превышении — 400 `too_many_matches`.

## 10. История изменений

10.1 Триггер записи: каждая мутация в tasks-svc оборачивается middleware, который пишет в `audit_events` (см. 3.5.14) и в `event_log` (см. 3.5.15) одновременно с основной транзакцией.

### 10.2 Видимость

10.2.1 `apit history task <uuid>` — доступна при наличии ≥1 разрешения на задаче (PRD §6.1.8).

10.2.2 `apit history user <email>`:

10.2.2.1 Если запрашиваемый email == собственный email — все собственные события.

10.2.2.2 Если запрашиваемый email — другой пользователь, возвращаются только те события, цель которых (задача/проект/команда) доступна запрашивающему по 6.1.8; остальные события скрываются.

10.3 Курсор: opaque base64 из `(created_at, id)`; гарантирует стабильную последовательность.

10.4 Лимит фиксирован 50, переопределение не поддерживается.

## 11. Автоматизации (технически)

### 11.1 Хранение

11.1.1 Таблица `automations` (см. 3.5.12); `trigger_config` и `action_config` — JSONB.

### 11.2 Event-триггер flow

11.2.1 Каждая мутация задачи пишет в `event_log` в той же транзакции, что и мутация.

11.2.2 Фоновая asyncio-таска `reactive_matcher`: `SELECT new event_log records FOR UPDATE SKIP LOCKED`.

11.2.3 Для каждой записи: загружает все `automations` где `trigger_type=event AND project_id IN (проекты задачи) AND event_type=<event>`, проверяет RSQL-фильтр против состояния задачи.

11.2.4 Совпавшие автоматизации: action-record добавляется в `webhook_outbox` (для webhook-action) или сразу исполняется в воркере (для system_method-action).

11.2.5 Event помечается `processed_at`.

### 11.3 Cron-триггер flow

11.3.1 APScheduler с PostgreSQL-jobstore.

11.3.2 При запуске tasks-svc — загружает все `automations` где `trigger_type=cron` и регистрирует job-ы.

11.3.3 Job при срабатывании — ставит action-record в очередь.

### 11.4 Whitelist system-методов

11.4.1 `tasks.list(filter: str) → Task[]`.

11.4.2 `tasks.create(payload: TaskCreate) → Task`.

11.4.3 `tasks.bulk_update(filter: str, patch: dict) → BulkResult`.

11.4.4 `tasks.batch_update(filter: str, patch: dict) → BatchResult`.

11.4.5 `tasks.share(task_id: UUID, user_email: str | null, team_id: UUID | null, perms: list[str])`.

11.4.6 Расширения whitelist — отдельный PR с обновлением docs-client.

### 11.5 Jinja-контекст шаблонов

11.5.1 Event-trigger: `{ "task": Task, "event": Event, "secrets": { name: value } }`.

11.5.2 Cron-trigger: `{ "now": ISO8601, "query": function(rsql) → Task[], "secrets": { name: value } }`.

## 12. Webhook outbox

12.1 Схема — см. 3.5.16.

12.2 Воркер — фоновая asyncio-таска внутри tasks-svc.

12.3 `SELECT ready records FOR UPDATE SKIP LOCKED`, обрабатывает по N штук параллельно.

12.4 Стратегия backoff: 1с, 5с, 30с, 2мин, 10мин; число попыток фиксируется PRD §8.6.1.

12.5 После исчерпания попыток — статус `dead_letter`; запись остаётся для ручного анализа.

## 13. Секреты проекта

13.1 Хранение: `project_secrets.value_encrypted` — AES-256-GCM, ключ — env `MASTER_SECRET_KEY` (32 байта base64).

13.2 Чтение — только в момент рендера Jinja-шаблона автоматизации; в API не возвращается.

13.3 CRUD — через `apit secret set/list/delete` под правом `manage_secrets` (см. PRD §6.5.4).

## 14. Фоновые подсистемы в tasks-svc

14.1 Запускаются в основном процессе как asyncio-таски при startup:

14.1.1 `reactive_matcher` (см. 11.2).

14.1.2 `cron_scheduler` (см. 11.3).

14.1.3 `webhook_dispatcher` (см. 12).

14.1.4 `jwks_refresher` (см. 6.3).

14.1.5 `user_cache_refresher` — eviction старых записей в `tasks.users`.

14.2 Координация между репликами — Postgres advisory-locks и `FOR UPDATE SKIP LOCKED`; Redis не требуется.

## 15. CLI-архитектура

15.1 Стек — Python + typer.

15.2 Один бинарь `apit` (через pip install или standalone через `shiv`/`pyinstaller` — решается на M1).

15.3 Конфигурация: `~/.config/apit/config.yaml` (хост `api.apitracker.ru` по умолчанию, перекрывается env `APIT_API_URL`).

15.4 Креды — в keychain (см. 4.3.5).

15.5 Команды группируются: `task`, `team`, `project`, `share`, `history`, `automation`, `secret`, `login`, `logout`, `whoami`.

15.6 Каждая команда поддерживает `--output table|json`; default — table при TTY, json при пайпе.

### 15.7 Exit-коды

15.7.1 `0` — success.

15.7.2 `1` — runtime/API ошибка.

15.7.3 `2` — invalid argument/flag (typer-convention).

15.7.4 `3` — auth required (нет токена или 401).

15.7.5 `4` — forbidden (403).

## 16. Frontend-архитектура

### 16.1 Angular workspace

16.1.1 Версия Angular — 20.

16.1.2 Workspace содержит два apps: `auth-client`, `docs-client`.

16.1.3 Общие либы в `frontend/libs/` (если возникнет потребность; на старте без них).

### 16.2 Конвенции

16.2.1 Standalone-компоненты, OnPush change detection, zoneless mode.

16.2.2 Strict TypeScript, no-any.

16.2.3 HttpClient + Observable (без сторонних RxJS-обёрток).

16.2.4 Один файл — один экспорт, полные имена.

16.2.5 Readonly везде где возможно.

### 16.3 auth-client

16.3.1 Страницы: `/` (вход), `/magic` (callback), `/cli-login` (handoff confirm), `/sessions`, `/logout`.

16.3.2 Использует сгенерированный orval-клиент к auth-svc.

### 16.4 docs-client

16.4.1 SSR не используется; статика SPA с предсборкой маршрутов из markdown в `src/content/`.

16.4.2 Контент-источники: ручные туториалы + автогенерируемые справки (см. 16.5).

### 16.5 Автогенерация справки в docs-client (M4)

16.5.1 CLI reference: скрипт интроспектирует typer-приложение → markdown.

16.5.2 RSQL/schema reference: парсинг OpenAPI с `x-rsql-fields` → таблицы.

16.5.3 Event-type catalog: интроспекция enum `EventType` в Python-коде.

16.5.4 System-method catalog: интроспекция whitelist (см. 11.4) и сигнатур.

## 17. Деплой

### 17.1 Образы

17.1.1 Python-сервисы: базовый `python:3.13-slim`, multi-stage с `uv`.

17.1.2 Frontend: `nginx:alpine` с COPY готовой статики.

17.1.3 Registry: GHCR `ghcr.io/gaev-tech/api-tracker/<service>:<sha>`.

### 17.2 Compose

17.2.1 Файл — `deploy/docker-compose.prod.yml`.

17.2.2 Env-файл `.env.prod` на сервере (не в репо), содержит:

17.2.2.1 `POSTGRES_PASSWORD`.

17.2.2.2 `JWT_PRIVATE_KEY_B64`, `JWT_PUBLIC_KEY_B64`.

17.2.2.3 `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.

17.2.2.4 `MASTER_SECRET_KEY`.

17.2.2.5 `SOLO_USER_EMAIL` (для M0–M1).

17.2.2.6 `AUTH_MODE` (`disabled` или `jwt`).

17.2.3 Healthchecks: tasks-svc и auth-svc — GET `/healthz` (200 OK).

### 17.3 TLS

17.3.1 Сертификаты для `apitracker.ru`, `*.apitracker.ru` — Let's Encrypt через certbot.

17.3.2 Авторенью каждые 12 часов (контейнер с cron).

### 17.4 Rollback

17.4.1 GHA сохраняет SHA последнего успешного деплоя в repo-variable `LAST_DEPLOYED_SHA`.

17.4.2 `gh workflow run rollback.yml -f sha=<prev>` запускает деплой того образа.

17.4.3 БД-миграции необратимы автоматически: для отката нужна ручная down-миграция.

## 18. CI/CD

### 18.1 Pipeline на PR (feature-branches)

18.1.1 `lint`: `ruff check`, `ruff format --check`, `mypy --strict`, `ng lint`.

18.1.2 `test`: `pytest -q --cov`, `ng test --no-watch`.

18.1.3 `contracts-check`: запуск сервисов в test-mode → dump OpenAPI → diff против `contracts/openapi/*.json`; `buf lint` + `buf breaking origin/main`.

18.1.4 `frontend-codegen-check`: `npm run gen:api` → git diff должен быть пуст.

18.1.5 `cli-cases-coverage` (с M2): каждая запись в `cli-test-cases.md` должна иметь соответствующий test-id в `cli/tests/e2e/`.

18.1.6 `build`: docker build всех сервисов (без push).

### 18.2 Pipeline на push в main

18.2.1 Все шаги 18.1.

18.2.2 `push`: docker push в GHCR.

18.2.3 `deploy`: SSH на сервер, исполнение `~/api-tracker/pull-and-up.sh`.

18.2.4 `record-deploy`: обновление repo-variable `LAST_DEPLOYED_SHA`.

### 18.3 Coverage

18.3.1 Порог — 70% строк по бэкенду; устанавливается в `pyproject.toml` по итогам M1, до этого — soft-fail.

## 19. Стайлгайд кода

### 19.1 Python

19.1.1 Минимум Python 3.6 (требование "> 3.5"); target — 3.13.

19.1.2 Обязательные аннотации типов на всех функциях, методах, атрибутах класса.

19.1.3 `mypy --strict` без исключений.

19.1.4 `ruff` для линта и автоформата.

19.1.5 Pydantic v2 для всех моделей API.

19.1.6 Никаких `Any` без документированного обоснования.

### 19.2 Angular

19.2.1 См. 16.2.

### 19.3 SQL

19.3.1 Миграции через Alembic.

19.3.2 Naming: snake_case для таблиц и колонок, plural для таблиц, `*_id` для FK.
