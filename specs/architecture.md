# Архитектура

Все ссылки вида (PRD §X) — на `product.md`. Все ссылки вида (TC §Y) — на `cli-test-cases.md`. (IPLAN §Z) — на `implementation-plan.md`.

## 1. Топология процессов

### 1.1 Сервисы и контейнеры (docker-compose на проде)

1.1.1 `nginx` — TLS-терминация, маршрутизация (см. 2).

1.1.2 `postgres` — единственный инстанс БД (см. 3).

1.1.3 `tasks-svc` — FastAPI, основная бизнес-логика.

1.1.4 `auth-svc` — FastAPI, регистрация и сессии (поднимается с M2, см. IPLAN §4).

1.1.5 `auth-client` — не входит в MVP (см. §16.3); место зарезервировано на Post-MVP.

1.1.6 `docs-client` — статика Angular, отдаётся через nginx (с M4).

1.1.7 `certbot` — авторенью Let's Encrypt сертификатов.

### 1.2 Сетевая изоляция

1.2.1 Compose-сеть `internal` соединяет `tasks-svc`, `auth-svc`, `postgres`; не выставляется наружу.

1.2.2 `nginx` имеет доступ в `internal` и слушает 80/443 на внешнем интерфейсе.

1.2.3 gRPC-канал tasks-svc ↔ auth-svc — внутри `internal`, порт 50051 на обоих сервисах.

## 2. Сетевая маршрутизация

2.1 Единственный домен — `apitracker.ru`; разводка по путям, поддоменов нет.

2.2 `apitracker.ru/healthz` → tasks-svc (мониторинг и проверка деплоя).

2.3 `apitracker.ru/api/v1/*` → tasks-svc (REST с публичных клиентов; nginx стрипает префикс `/api`).

2.4 `apitracker.ru/api/auth/*` → auth-svc (REST; nginx стрипает `/api`, передаёт `/auth/*`).

2.5 `apitracker.ru/*` (остальное) → docs-client (SPA; base href `/`).

2.6 Внутри compose: `tasks-svc:50051` ↔ `auth-svc:50051` (gRPC).

## 3. База данных

3.1 Один Postgres, две логические схемы: `auth` и `tasks`.

3.2 БД-пользователи:

3.2.1 `auth_app` — read/write только на схему `auth`.

3.2.2 `tasks_app` — read/write только на схему `tasks`.

3.3 Миграции — Alembic; запуск в entrypoint сервиса с advisory-lock против race при rolling-up.

3.4 Бэкап: `pg_dump` cron-ом ежедневно в 03:00 UTC, ретенция 14 дней, в `/var/backups/api-tracker/`.

### 3.5 Схема `tasks`

3.5.0 Все колонки `id` сущностей и FK на них — `CHAR(40)` SHA1-hex (PRD §5.2.6, миграция см. §3.7). Исключение — `users.user_id` тоже SHA1, синхронизируется с `auth.users.id`.

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

3.6.0 Колонки `id` — `CHAR(40)` SHA1-hex (см. §3.7, PRD §5.2.6).

3.6.1 `users(id, email, created_at)`.

3.6.2 `magic_tokens(token_hash, email, login_session_id, expires_at, used_at, confirmed_at)` — `login_session_id` UUID NOT NULL UNIQUE; `confirmed_at` NULL пока не кликнут.

3.6.3 `refresh_tokens(id, user_id, kind, label, created_at, revoked_at, expires_at)`.

3.6.4 `sessions(refresh_token_id, last_seen_at, user_agent)`.

3.6.5 `cli_auth_codes(state, code_challenge, code, code_used_at, expires_at, user_id)` — таблица сохранена для legacy browser-handoff (см. §4.4); в magic-link flow не используется.

3.6.6 `device_codes(device_code, user_code, expires_at, user_id, approved_at)` — см. §4.4.

### 3.7 Миграция UUID → SHA1 на проде

3.7.1 Одноразовая Alembic-миграция; для каждой записи в `auth.users`, `tasks.tasks`, `tasks.teams`, `tasks.projects`, `tasks.automations`, `tasks.project_secrets` вычисляется SHA1-ключ:

3.7.1.1 Для пользователя: `SHA1(email)` (без created_at — email уникален; одинаковый ключ для одного email в обеих логических БД auth/tasks; не зависит от того, в какой схеме вычисляется).

3.7.1.2 Для задачи: `SHA1(title || \n || description_md || \n || created_at_ns)`.

3.7.1.3 Для команды/проекта: `SHA1(name || \n || created_at_ns)`.

3.7.1.4 Для автоматизации/секрета: `SHA1(project_id || \n || name || \n || created_at_ns)` (project_id — уже мигрированный SHA1).

3.7.1.5 `created_at_ns` — `EXTRACT(EPOCH FROM created_at) * 1e9` округлённое до int.

3.7.2 Все FK (`assignee_id`, `task_id`, `blocked_by_task_id`, `team_id`, `project_id`, `target_id`, `actor_user_id`, `user_id` в шаринге и членствах, `source_task_id`, `automation_id`) обновляются по мапе old_uuid → new_sha1.

3.7.3 Тип колонок меняется с `UUID` на `CHAR(40)`; индексы и уникальные констрейнты пересоздаются.

3.7.4 Миграция запускается на проде один раз через стандартный entrypoint (§3.3); downtime — длительность миграции (для текущего объёма данных ~секунды).

3.7.5 Создание новых записей использует генератор `SHA1(<deterministic-content> || \n || time.time_ns())` (PRD §5.2.6); коллизии исключаются включением timestamp в наносекундах.

3.7.6 Prefix-lookup: для каждой таблицы существующий PK-индекс на `CHAR(40)` достаточен для эффективного поиска по префиксу через `WHERE id LIKE 'prefix%'`; дополнительные индексы не требуются.

## 4. Аутентификация

### 4.1 Режимы

4.1.1 `AUTH_MODE=disabled` (M0–M1): middleware tasks-svc игнорирует токен, проставляет `request.user_id = SOLO_USER.id`.

4.1.2 `AUTH_MODE=jwt` (M2+): middleware валидирует JWT по JWKS, проставляет `request.user_id`.

4.1.3 SOLO_USER создаётся при первом старте tasks-svc с `AUTH_MODE=disabled` в `tasks.users` (auth-svc может ещё не существовать).

### 4.2 Magic-link (click-to-confirm)

4.2.1 `POST /api/auth/magic/start {email}` — генерит токен (32 байта random) и `login_session_id` (UUID); хранит запись в `auth.magic_tokens` (см. §3.6.2), TTL 15 мин. Возвращает `{login_session_id, expires_in}`.

4.2.1.1 Перед записью токена эндпоинт валидирует `SMTP_HOST`; если не задан — возвращает 500 `email_delivery_not_configured` без записи в БД.

4.2.2 SMTP отправляет письмо с URL-ссылкой `https://apitracker.ru/api/auth/magic/confirm?token=<plaintext-token>` и подсказкой "после клика вернитесь в терминал". Plaintext-кода в письме нет.

4.2.3 `GET /api/auth/magic/confirm?token=<t>` (открывается в браузере по клику пользователя):

4.2.3.1 Проверяет хеш, expiry, флаг `used_at`.

4.2.3.2 Помечает токен `used_at = now()`, `confirmed_at = now()`.

4.2.3.3 Создаёт пользователя в `auth.users` если его нет (PRD §10.4).

4.2.3.4 Создаёт сессию `kind=cli` (refresh + access токены); связывает с `login_session_id` через `auth.magic_tokens.login_session_id`.

4.2.3.5 Возвращает `200 text/html` со страницей "Сессия подтверждена. Вернитесь в терминал." (минимальный inline-HTML, без зависимости от docs-client).

4.2.3.6 При истёкшем/использованном токене — `410 text/html` со страницей "Ссылка истекла. Запустите `clite login` повторно.".

4.2.4 `GET /api/auth/magic/poll/{login_session_id}` — long-poll-эндпоинт, который CLI вызывает в цикле:

4.2.4.1 Если `confirmed_at IS NULL` и токен не истёк → `202 {"status":"pending"}`.

4.2.4.2 Если подтверждён → `200 {access_token, refresh_token, expires_in}`. Возврат однократный: после первого 200 сессия помечается выданной, повторный poll того же `login_session_id` → `410`.

4.2.4.3 Если токен истёк без подтверждения → `410 {"status":"expired"}`.

4.2.4.4 Если `login_session_id` не существует → `404`.

4.2.5 Paste-code-эндпоинт `POST /api/auth/magic/verify` упразднён.

### 4.3 CLI login flow

4.3.1 `clite login`:

4.3.1.1 Интерактивно спрашивает email (или принимает `--email <e>`).

4.3.1.2 `POST /api/auth/magic/start {email}` → `{login_session_id, expires_in}`.

4.3.1.3 Печатает на stderr: `✉ Link sent to <email>. Click it from your inbox. Waiting…`.

4.3.1.4 Циклически вызывает `GET /api/auth/magic/poll/{login_session_id}` с бэкоффом 1с, 1с, 2с, 2с, 5с, далее каждые 5с до `expires_in`.

4.3.1.5 При 200 → сохраняет `{access_token, refresh_token, expires_in}` в `~/.config/clite/credentials.yaml` 0600, печатает на stdout `success, press enter to continue`, ждёт нажатия Enter, выходит exit 0.

4.3.1.6 При 410 → exit 1, stderr `magic link expired, run clite login again`.

4.3.1.7 При SIGINT (Ctrl-C) → exit 130; токен на сервере остаётся неиспользованным до `expires_in`.

4.3.2 Браузер пользователя задействован только для клика по ссылке из письма; CLI его не запускает.

### 4.4 Deprecated: browser-handoff endpoints

4.4.1 Эндпоинты `/api/auth/cli/code`, `/exchange`, `/device-start`, `/device-approve`, `/device-poll` остаются на проде как backward compat для старых clite-клиентов, но новые CLI-релизы их не используют.

4.4.2 В Post-MVP при добавлении браузерного admin-UI поток может вернуться; до тех пор код не развивается.

### 4.5 JWT-формат

4.5.1 Алгоритм RS256.

4.5.2 Claims: `sub` (user_id SHA1-hex), `email`, `iat`, `exp` (1 час от iat).

4.5.3 Никаких прав в токене.

4.5.4 Приватный ключ — env `JWT_PRIVATE_KEY_B64` в auth-svc; публичный ключ публикуется через gRPC `GetJWKS` (см. 6.3).

### 4.6 Refresh-flow

4.6.1 Access TTL 1 час; refresh TTL 30 дней.

4.6.2 Любой refresh ротирует refresh-token (старый помечается `revoked_at`, выдаётся новый).

4.6.3 CLI: `POST /api/auth/cli/refresh {refresh_token}`. Browser-flow (cookie) — deprecated.

### 4.7 Сессии

4.7.1 Все refresh-токены пользователя видны через `clite session list`.

4.7.2 Каждая помечена `kind` (`cli` в MVP), `label`, `created_at`, `last_seen_at`.

4.7.3 Revoke через `clite session revoke <label>` или `clite logout` (revoke текущей).

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

7.1 Базовый префикс tasks-svc: `https://apitracker.ru/api/v1/`.

7.2 Базовый префикс auth-svc: `https://apitracker.ru/api/auth/`.

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

10.2.1 `clite history task <key>` — доступна при наличии ≥1 разрешения на задаче (PRD §6.1.8).

10.2.2 `clite history user <email>`:

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

11.4.5 `tasks.share(task_id: str, user_email: str | null, team_id: str | null, perms: list[str])` — `task_id`/`team_id` принимают SHA1-ключ или префикс (PRD §5.2.7).

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

13.3 CRUD — через `clite secret set/list/delete` под правом `manage_secrets` (см. PRD §6.5.4).

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

15.2 Один бинарь `clite` (через pip install или standalone через `shiv`/`pyinstaller` — решается на M1).

15.3 Конфигурация: `~/.config/clite/config.yaml` (хост `https://apitracker.ru` по умолчанию, перекрывается env `APIT_API_URL`).

15.4 Креды — в keychain (см. 4.3.5).

15.5 Команды группируются: `task`, `team`, `project`, `share`, `history`, `automation`, `secret`, `login`, `logout`, `whoami`.

15.6 Каждая команда поддерживает `--output table|json`; default — table при TTY, json при пайпе.

15.6.1 Каждая get/list-команда поддерживает `--fields <a,b,c>` (PRD §7.9) — фильтрация полей рендера на стороне CLI; полный ответ всегда читается с сервера, кеширование отсутствует.

### 15.7 Exit-коды

15.7.1 `0` — success.

15.7.2 `1` — runtime/API ошибка.

15.7.3 `2` — invalid argument/flag (typer-convention).

15.7.4 `3` — auth required (нет токена или 401).

15.7.5 `4` — forbidden (403).

### 15.8 Распространение и релизы

15.8.1 Публичный репозиторий `gaev-tech/clite` — отдельный от приватного monorepo `gaev-tech/api-tracker`.

15.8.2 Содержимое публичного репо: README с инструкциями установки и GitHub Releases с бинарными артефактами; исходный код CLI остаётся в приватном monorepo (`cli/`).

15.8.3 Сборка бинарей — pyinstaller в GHA-matrix по операционным системам:

15.8.3.1 `macos-latest` (arm64) → артефакт `clite-vX.Y.Z-darwin-arm64`.

15.8.3.2 `macos-13` (amd64) → `clite-vX.Y.Z-darwin-amd64`.

15.8.3.3 `ubuntu-latest` → `clite-vX.Y.Z-linux-amd64`.

15.8.3.4 `windows-latest` → `clite-vX.Y.Z-windows-amd64.exe`.

15.8.4 Триггер релиза: git tag `vX.Y.Z` в приватном monorepo запускает release-workflow в GHA.

15.8.5 Release-workflow: собирает бинари по 15.8.3, создаёт GitHub Release в публичном репо через `gh release create` с использованием Personal Access Token из repo-secret `PUBLIC_REPO_TOKEN`.

15.8.6 README публичного репо содержит:

15.8.6.1 Краткое описание системы и ссылку на `apitracker.ru` (docs).

15.8.6.2 По одной команде установки на OS (curl/Invoke-WebRequest, chmod, mv в PATH).

15.8.6.3 Ссылка на последний релиз и список SHA256 артефактов для верификации.

15.8.7 Версионирование — semver `vX.Y.Z`; bump вручную через создание тега в monorepo.

15.8.8 Обновление CLI пользователем: повторная установка из README; команда `clite --version` показывает текущую версию.

### 15.9 Дистрибуция через пакетные площадки

15.9.1 Дополнительные каналы дистрибуции CLI помимо GitHub Releases (§15.8). Все каналы триггерятся одним и тем же тегом `vX.Y.Z` через расширение release-workflow.

15.9.2 GitHub Releases (§15.8) остаётся канонiчным источником бинарей; все остальные каналы либо переупаковывают их, либо ссылаются на них.

15.9.3 PyPI:

15.9.3.1 Пакет `clite` публикуется на `pypi.org`.

15.9.3.2 Сборка — `uv build` из `cli/`, публикация — `uv publish` или `twine` с токеном из repo-secret `PYPI_TOKEN`.

15.9.3.3 Установка пользователем: `pipx install clite` (рекомендуется) или `pip install clite`.

15.9.3.4 Зависимости пакета: те же, что у source-варианта; pyinstaller-обёртка не используется (pip ставит Python-источники).

15.9.4 Homebrew (macOS):

15.9.4.1 Отдельный публичный репозиторий `gaev-tech/homebrew-clite` со структурой Homebrew tap; содержит `Formula/clite.rb`.

15.9.4.2 Formula ссылается на GitHub Releases по URL — отдельный URL для darwin-arm64 и darwin-amd64, с SHA256.

15.9.4.3 Release-workflow генерирует обновлённый `Formula/clite.rb` и пушит в tap-репо через GitHub App token.

15.9.4.4 Установка пользователем: `brew install gaev-tech/clite/clite`.

15.9.5 APT (Debian/Ubuntu):

15.9.5.1 `.deb`-пакет собирается в release-workflow через `dpkg-deb` поверх ubuntu-latest linux-amd64 бинаря.

15.9.5.2 Хостинг репозитория: `apt.apitracker.ru/` — статический Debian-репо на том же проде (nginx раздаёт каталог `dists/` и `pool/`, генерация структуры через `aptly` в release-workflow с push по SSH).

15.9.5.3 Подпись пакетов GPG-ключом; публичный ключ выложен по `apt.apitracker.ru/key.gpg`.

15.9.5.4 Установка пользователем:

15.9.5.4.1 `curl -fsSL https://apt.apitracker.ru/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/apit.gpg`

15.9.5.4.2 `echo "deb [signed-by=/usr/share/keyrings/apit.gpg] https://apt.apitracker.ru stable main" | sudo tee /etc/apt/sources.list.d/apit.list`

15.9.5.4.3 `sudo apt update && sudo apt install clite`.

15.9.6 npm (binary-wrapper pattern):

15.9.6.1 Пакет `@gaev-tech/clite` публикуется на npmjs.com.

15.9.6.2 Структура — postinstall-скрипт определяет OS+arch и качает соответствующий бинарь из GitHub Releases (§15.8.3) в `node_modules/.bin/clite`.

15.9.6.3 Публикация — `npm publish --registry https://registry.npmjs.org/` с токеном из repo-secret `NPM_TOKEN`.

15.9.6.4 Установка пользователем: `npm install -g @gaev-tech/clite` или одноразовый запуск `npx @gaev-tech/clite ...`.

15.9.7 Release-workflow (расширение §15.8.5):

15.9.7.1 Job 1 — собрать бинари (§15.8.3).

15.9.7.2 Job 2 — `gh release create` в публичном GitHub-репо (§15.8.5).

15.9.7.3 Job 3 — `pypi-publish` через `uv publish`.

15.9.7.4 Job 4 — `homebrew-publish` через генерацию Formula и push в tap-репо.

15.9.7.5 Job 5 — `apt-publish` через `aptly` и SSH в `apt.apitracker.ru`.

15.9.7.6 Job 6 — `npm-publish` через `npm publish --registry https://registry.npmjs.org/`.

15.9.8 Чек-лист релиза: автоматический после успеха всех jobs — `clite --version` показывает корректную версию при установке из любого канала.

## 16. Frontend-архитектура

### 16.1 Angular workspace

16.1.1 Версия Angular — 20.

16.1.2 Workspace содержит `docs-client` (auth-client отложен до Post-MVP, см. §16.3).

16.1.3 Общие либы в `frontend/libs/` (если возникнет потребность; на старте без них).

### 16.2 Конвенции

16.2.1 Standalone-компоненты, OnPush change detection, zoneless mode.

16.2.2 Strict TypeScript, no-any.

16.2.3 HttpClient + Observable (без сторонних RxJS-обёрток).

16.2.4 Один файл — один экспорт, полные имена.

16.2.5 Readonly везде где возможно.

### 16.3 auth-client — не входит в MVP

16.3.1 Браузерный auth-клиент не входит в MVP (см. PRD §3.2). Аутентификация — terminal-only через CLI (см. §4.3).

16.3.2 В Post-MVP при появлении admin-UI здесь будет описана структура SPA для управления сессиями, email-настройками и т.п.

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

17.3.1 Сертификат для `apitracker.ru` — Let's Encrypt через certbot.

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
