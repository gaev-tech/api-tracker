# План реализации

Все ссылки вида (PRD §X) — на `product.md`. (ARCH §Y) — на `architecture.md`. (TC §Z) — на `cli-test-cases.md`.

## 1. Принципы планирования

1.1 Деление работы — на милстоуны M0..M4; каждый милстоун — деплоимый инкремент.

1.2 Внутри милстоуна — PR-слайсы; каждый слайс независимо проходит CI и деплоится.

1.3 Критерий "done" милстоуна — фича работает на проде и используется автором.

1.4 Главный приоритет — как можно более ранний dogfood (M1).

1.5 Перед началом M0 старые файлы спек (`api-spec.md`, `architecture-api.md`, `architecture-cli.md`, `architecture-ui.md`, `design-system.html`, `plan-design-system.html`, `prd.md`, `roadmap.md`) и предыдущая кодовая база (`backend/`, `frontend/`, `contracts/`, `deploy/`, `buf.yaml`, `Makefile`) удаляются.

## 2. M0 — Skeleton deploy

### 2.1 Цель

2.1.1 Пустой каркас на проде, доступный через TLS, с автодеплоем на push в main.

### 2.2 Делverables

2.2.1 Очистка репозитория от старого api-tracker (см. 1.5).

2.2.2 Монорепо-структура: `backend/auth-service/`, `backend/tasks-service/`, `cli/`, `frontend/auth-client/`, `frontend/docs-client/`, `contracts/proto/`, `contracts/openapi/`, `deploy/`.

2.2.3 Python tooling: `uv` (или poetry), `ruff`, `mypy --strict`, `pytest`.

2.2.4 Angular 20 workspace с двумя apps `auth-client` и `docs-client` (пустые скелеты).

2.2.5 DNS: A-запись `apitracker.ru` указана на сервер.

2.2.6 docker-compose на проде: `nginx`, `postgres`, `tasks-svc` (с эндпоинтами `/healthz` и `/v1/ping`).

2.2.7 TLS через certbot, авторенью (ARCH §17.3).

2.2.8 GHA pipeline: lint + test + build + push + deploy (ARCH §18.2).

2.2.9 Бэкап postgres ежедневно cron-ом (ARCH §3.4).

### 2.3 Done criteria

2.3.1 `curl https://apitracker.ru/healthz` → 200.

2.3.2 Push в main — новый образ деплоится за <5 мин без ручных шагов.

2.3.3 Сертификаты обновляются автоматически.

## 3. M1 — Solo dogfood

### 3.1 Цель

3.1.1 Автор начинает вести задачи разработки этого же проекта через `clite` без авторизации (`AUTH_MODE=disabled`).

### 3.2 Делverables

3.2.1 Модели tasks-svc: `Task`, `TaskBlocker`, `AuditEvent`; SOLO_USER создаётся при старте.

3.2.2 RSQL-парсер v1 (ARCH §8).

3.2.3 Эндпоинты:

3.2.3.1 `GET /api/v1/tasks?filter=&cursor=&limit=` (внутри tasks-svc — `/v1/tasks`, nginx стрипает `/api`).

3.2.3.2 `POST /api/v1/tasks/bulk-update?filter=`.

3.2.3.3 `POST /api/v1/tasks/batch-update?filter=`.

3.2.3.4 `POST /api/v1/tasks/bulk-create`.

3.2.3.5 `POST /api/v1/tasks/batch-create`.

(Single-task `POST /tasks` и `PATCH /tasks/{id}` удалены в M2.28 — все мутации проходят через bulk/batch.)

3.2.3.8 `GET /api/v1/history?task_id=&cursor=`.

3.2.4 Audit-логирование на каждой мутации.

3.2.5 CLI команды:

3.2.5.1 `clite task list`.

3.2.5.2 `clite task get <key>`.

3.2.5.3 `clite task create bulk <json-array | --file <path>>`.

3.2.5.4 `clite task create batch <json-array | --file <path>>`.

3.2.5.5 `clite task update bulk --filter <rsql> --set f=v`.

3.2.5.6 `clite task update batch --filter <rsql> --set f=v`.

(Single-task `clite task create` и `clite task update <id>` удалены в M2.28.)

3.2.5.9 `clite history task`.

3.2.6 Alembic-миграции в entrypoint (ARCH §3.3).

3.2.7 OpenAPI auto-export в `contracts/openapi/tasks.json` в CI.

3.2.8 Тесты: unit и integration (testcontainers с postgres) — минимум 1 happy path и 1 ошибочный сценарий на каждый эндпоинт.

3.2.9 Публичный репозиторий `gaev-tech/clite` создан со скелетным README "coming soon"; release-workflow в GHA настроен для одной платформы (macOS arm64) и публикует pre-release `v0.1.0-dev` (ARCH §15.8).

### 3.3 Done criteria

3.3.1 Автор переносит roadmap M2–M4 в систему и работает с ним через `clite`.

3.3.2 Coverage по бэкенду измеряется в M1 и фиксируется как порог для следующих милстоунов.

## 4. M2 — Multi-user и CLI test cases

### 4.1 Цель

4.1.1 Переключение в `AUTH_MODE=jwt`, шаринг и совместная работа, формализация CLI-тест-кейсов.

### 4.2 Делverables

#### 4.2.1 Auth-svc

4.2.1.1 Модели: `User`, `MagicToken`, `RefreshToken`, `Session`, `CliAuthCode`, `DeviceCode`.

4.2.1.2 SMTP-интеграция (ARCH §17.2.2.3).

4.2.1.3 REST endpoints: `/api/magic/start`, `/api/magic/confirm`, `/api/magic/poll/{login_session_id}`, `/api/cli/refresh`, `/api/auth/refresh`, `/api/auth/logout`, `/api/sessions`. (Browser-handoff `/api/cli/code|exchange|device-*` — deprecated, см. ARCH §4.4. Paste-code `/api/magic/verify` удалён в §4.2.9.)

4.2.1.4 gRPC-сервер: `GetUserByEmail`, `GetUsersByIds`, `GetJWKS` (ARCH §6).

4.2.1.5 Protobuf в `contracts/proto/auth.proto`.

#### 4.2.2 Tasks-svc

4.2.2.1 `AUTH_MODE=jwt` middleware, JWKS-кеш, gRPC-клиент к auth-svc.

4.2.2.2 Кеш `tasks.users` (ARCH §3.5.1) с фоновым refresher.

4.2.2.3 Новые модели: `TaskUserShare`, `TaskTeamShare`, `Team`, `TeamMember`, `Project`, `ProjectUserMember`, `ProjectTeamMember`, `ProjectTask`.

4.2.2.4 Эндпоинты team CRUD, project CRUD, share CRUD; anchor-rule валидация (PRD §6.6).

4.2.2.5 Effective-perm резолвер (PRD §6.2).

4.2.2.6 `GET /v1/history?user_id=<email>` с проверкой видимости (ARCH §10.2.2).

#### 4.2.3 Auth-client (Angular 20) — отменено

4.2.3.1 Решение пересмотрено в ходе M2: браузерный auth-клиент не входит в MVP. Аутентификация — terminal-only через CLI (ARCH §4.3, PRD §3.2, §10.5).

4.2.3.2 Если в Post-MVP потребуется admin-UI — задача будет переоткрыта.

#### 4.2.4 CLI

4.2.4.1 `clite login` (interactive email + magic-link click + poll, см. ARCH §4.3.1), `clite logout`, `clite whoami`. Browser-handoff и device-code-flow упразднены вместе с auth-client; paste-code заменён click-flow в §4.2.9.

4.2.4.2 `clite team create/get/update/list`, `clite team member set/remove`, `clite team leave`.

4.2.4.3 `clite project create/get/update/list`, `clite project member set/remove`, `clite project leave`, `clite project task add/remove`.

4.2.4.4 `clite share user set/remove`, `clite share team set/remove` на задаче.

4.2.4.5 `clite history user`.

#### 4.2.5 CLI test cases

4.2.5.1 Создание `cli-test-cases.md` (см. TC §1).

4.2.5.2 Бэкфил всех M1-команд (TC §3, §4).

4.2.5.3 Новые M2-команды: TC §5, §6, §7, §8.

4.2.5.4 Реализация автотестов в `cli/tests/e2e/` под testcontainers (поднимают auth-svc + tasks-svc + postgres + nginx-stub).

4.2.5.5 CI-шаг `cli-cases-coverage` (ARCH §18.1.5).

#### 4.2.6 Публичный CLI-репозиторий — production-ready

4.2.6.1 Release-workflow расширяется на полную matrix-сборку (ARCH §15.8.3): macOS arm64+amd64, Linux amd64, Windows amd64.

4.2.6.2 README в публичном репо: install-инструкции по 15.8.6, ссылка на apitracker.ru (docs).

4.2.6.3 Первый стабильный релиз `v1.0.0` создаётся к моменту "done" M2.

#### 4.2.7 SHA1-идентификаторы и prefix-lookup

4.2.7.1 Тип колонок `id` всех сущностей в схемах `tasks` и `auth.users.id` меняется с UUID на CHAR(40) (ARCH §3.5.0, §3.7).

4.2.7.2 Генератор SHA1 для новых записей: `SHA1(<deterministic-content> || \n || time.time_ns())` (ARCH §3.7.5, PRD §5.2.6).

4.2.7.3 Alembic data-миграция конвертирует существующие записи на проде; все FK обновляются по мапе (ARCH §3.7.1, §3.7.2).

4.2.7.4 Серверный resolver префикса: каждый запрос с идентификатором задачи/команды/проекта/автоматизации/секрета сначала разрешает префикс в полный ключ (PRD §5.2.7). Ошибки маппятся на HTTP 400 `prefix_too_short`, 404 `not_found`, 409 `ambiguous_prefix` с массивом кандидатов в теле ответа.

4.2.7.5 Pydantic-схема: ID — `str` с регексом `^[0-9a-f]{4,40}$`; OpenAPI x-format `sha1-prefix`.

4.2.7.6 CLI: аргументы типа `UUID` меняются на `str`; help указывает "SHA1 key or unique prefix"; ошибка ambiguous показывает список кандидатов с дискриминатором (TC §1.4, §3.6.3).

#### 4.2.8 `--fields` на get/list

4.2.8.1 Все get/list-команды CLI (PRD §7.9) принимают `--fields`; рендерер `output.py` фильтрует ключи перед `emit_table`/`emit_object`.

4.2.8.2 Сервер не меняется — фильтрация целиком CLI-сайд (ARCH §15.6.1).

4.2.8.3 Кеширование на CLI не вводится.

#### 4.2.9 Magic-link click-flow

4.2.9.1 Auth-svc:
- `POST /api/auth/magic/start` изменён (ARCH §4.2.1) — возвращает `login_session_id`;
- новый `GET /api/auth/magic/confirm?token=` отдаёт HTML 200/410 (ARCH §4.2.3);
- новый `GET /api/auth/magic/poll/{login_session_id}` (long-poll, ARCH §4.2.4);
- `POST /api/auth/magic/verify` удалён (ARCH §4.2.5).

4.2.9.2 Email-template содержит URL; plaintext-токен из тела удалён (ARCH §4.2.2).

4.2.9.3 Таблица `auth.magic_tokens` дополнена колонками `login_session_id UUID NOT NULL UNIQUE` и `confirmed_at TIMESTAMPTZ NULL` (ARCH §3.6.2).

4.2.9.4 CLI `clite login` переписывается под poll-цикл (ARCH §4.3.1); paste-code код удаляется.

4.2.9.5 Тест-кейсы 5.1, 5.2 обновляются (TC §5.1, §5.2).

#### 4.2.11 Drop single-task mutations

4.2.11.1 Удаляются эндпоинты `POST /v1/tasks` (single-create) и `PATCH /v1/tasks/{id}` (single-update). Все мутации задач проходят через bulk/batch с RSQL-фильтром (для update) либо с массивом объектов (для create).

4.2.11.2 CLI: удаляются `clite task create [opts]` (single) и `clite task update <id> [opts]` (single). Остаются `clite task create bulk/batch` и `clite task update bulk/batch`.

4.2.11.3 `clite task create bulk/batch` принимает inline JSON-массив как позиционный аргумент, либо `--file <path>` для чтения из файла (CSV — PostMVP, PRD §7.7).

4.2.11.4 Существующая логика `services.tasks.create_task` / `update_task` остаётся как internal API для bulk/batch итерации; внешних эндпоинтов на них больше нет.

#### 4.2.10 Fix: SMTP silent failure

4.2.10.1 Эндпоинт `/api/auth/magic/start` валидирует SMTP-конфиг до записи токена: при пустом `SMTP_HOST` возвращает 500 `email_delivery_not_configured` (ARCH §4.2.1.1).

4.2.10.2 Соответствующее env-значение задаётся в `.env.prod` на сервере (ARCH §17.2.2.3).

4.2.10.3 TC §5.2.4 переписан под новое поведение.

### 4.3 Done criteria

4.3.1 Автор приглашает второго пользователя по email; второй логинится через `clite login` (получает magic-link на email, кликает по ссылке, CLI печатает `success`).

4.3.2 Автор шарит задачу второму пользователю; второй видит её в `clite task list`.

4.3.3 Создание команды, добавление участника, шаринг команде задачи — работает.

4.3.4 Создание проекта, добавление задач в проект, выдача права через проект — работает.

4.3.5 Все CLI-команды покрыты кейсами и автотестами; CI green.

4.3.6 Второй пользователь устанавливает CLI по инструкции из README в публичном репо.

## 5. M3 — Автоматизации и webhooks

### 5.1 Цель

5.1.1 Проектные автоматизации с cron- и event-триггерами, webhook-доставка с retries, system-method вызовы.

### 5.2 Делverables

5.2.1 Модели: `Automation`, `ProjectSecret`, `EventLog`, `WebhookOutbox` (ARCH §3.5).

5.2.2 Новые project-permissions: `manage_automations`, `manage_secrets` (PRD §6.5.3, §6.5.4).

5.2.3 Эндпоинты CRUD для автоматизаций и секретов.

5.2.4 Event dispatcher: синхронная запись в `event_log` на каждую мутацию (ARCH §11.2).

5.2.5 Reactive matcher (фоновая asyncio-таска) (ARCH §11.2).

5.2.6 APScheduler с jobstore на postgres (ARCH §11.3).

5.2.7 Action-исполнитель: webhook и system_method (ARCH §11.4, §11.5, §12).

5.2.8 Jinja-рендер с подстановкой `{{secrets.*}}`, `task.*`, `query(...)` (ARCH §11.5).

5.2.9 CLI: `clite automation create/list/get/update/delete/run-now`, `clite secret set/list/delete`.

5.2.10 CLI-test-cases расширяются (TC §9, §10) и сопровождаются автотестами.

### 5.3 Done criteria

5.3.1 Автор настраивает cron-автоматизацию (например, "каждый день 9:00 экспортировать open-задачи через webhook"), она стабильно работает неделю.

5.3.2 Event-автоматизация на изменение статуса задачи работает с корректным Jinja-контекстом.

5.3.3 Webhook ретраит при 5xx ответе с корректным backoff; dead-letter после 5 неуспехов.

## 6. M4 — Docs-client

### 6.1 Цель

6.1.1 Публичный справочник по корню `apitracker.ru/` (ARCH §16.4).

### 6.2 Делverables

6.2.1 Angular SPA `docs-client` со sidebar-навигацией и поиском.

6.2.2 Build-time генератор справки:

6.2.2.1 CLI reference — интроспекция typer (ARCH §16.5.1).

6.2.2.2 Schema/RSQL reference — парсинг OpenAPI с `x-rsql-fields` (ARCH §16.5.2).

6.2.2.3 Event-type catalog (ARCH §16.5.3).

6.2.2.4 System-method catalog (ARCH §16.5.4).

6.2.3 Tutorials (markdown в `frontend/docs-client/src/content/`):

6.2.3.1 "Getting started" — установка CLI, первый логин, первая задача.

6.2.3.2 "RSQL primer" — операторы, поля, примеры.

6.2.3.3 "AI-driven workflow" — паттерны для использования AI-агента.

6.2.3.4 "Writing automations" — cron, event, секреты, шаблоны.

6.2.4 Executable examples: куски из `cli-test-cases.md` встраиваются в туториалы через md-include.

6.2.5 `apitracker.ru/` отдаёт docs-client напрямую.

### 6.3 Multi-channel дистрибуция CLI

6.3.1 Расширение release-workflow на дополнительные пакетные площадки (ARCH §15.9).

6.3.2 PyPI:

6.3.2.1 Регистрация имени пакета `clite` на pypi.org; создание API-token, добавление в repo-secret `PYPI_TOKEN`.

6.3.2.2 GHA-job `pypi-publish` с `uv build` + `uv publish`.

6.3.2.3 Проверка: `pipx install clite` ставит работоспособный CLI.

6.3.3 Homebrew:

6.3.3.1 Создание публичного репо `gaev-tech/homebrew-clite` с `Formula/clite.rb`.

6.3.3.2 GHA-job `homebrew-publish` обновляет Formula с новой версией и SHA256, пушит в tap-репо через GitHub App.

6.3.3.3 Проверка: `brew install gaev-tech/clite/clite` ставит работоспособный CLI на macOS.

6.3.4 APT:

6.3.4.1 На прод-сервере поднимается статический APT-репо в `/var/lib/api-tracker/apt/`, отдаваемый nginx по `apt.apitracker.ru`.

6.3.4.2 Генерация GPG-ключа для подписи, публикация публичного ключа в `apt.apitracker.ru/key.gpg`; приватный — в repo-secret `APT_GPG_KEY`.

6.3.4.3 GHA-job `apt-publish` собирает `.deb`, подписывает, обновляет репо через `aptly`, пушит по SSH.

6.3.4.4 nginx-конфиг `apt.apitracker.ru` с TLS Let's Encrypt.

6.3.4.5 Проверка: установка по инструкции (ARCH §15.9.5.4) на чистой Ubuntu даёт работоспособный CLI.

6.3.5 npm:

6.3.5.1 Регистрация имени `@gaev-tech/clite` на npmjs.com; создание токена, добавление в repo-secret `NPM_TOKEN`.

6.3.5.2 Пакет в `cli/npm-wrapper/` — postinstall-скрипт качает бинарь из GitHub Releases по OS+arch.

6.3.5.3 GHA-job `npm-publish` с `npm publish --registry https://registry.npmjs.org/`.

6.3.5.4 Проверка: `npx @gaev-tech/clite --version` и `npm install -g @gaev-tech/clite` работают.

6.3.6 Документация в docs-client: страница "Installation" перечисляет все каналы установки с командами.

### 6.4 Done criteria

6.4.1 Сторонний пользователь по apitracker.ru может разобраться, поставить CLI, залогиниться, создать задачу — без помощи автора.

6.4.2 Установка через каждый из 5 каналов (GitHub Releases binary, PyPI, Homebrew, APT, npm) даёт работоспособный `clite --version` соответствующей версии.

## 7. M5 — Free тариф и enforcement лимитов

### 7.1 Цель

7.1.1 Запуск Free-тарифа с серверным enforcement трёх метрик permission-записей. Pro/Max и платежи откладываются на M6 (см. `tariff.md` §1.5.1).

7.1.2 Существующие пользователи M2 grandfathered: их превышающие новые лимиты participations сохраняются как есть; новые добавления гейтятся.

### 7.2 Делverables

#### 7.2.1 Миграция БД

7.2.1.1 `auth.users.tariff text NOT NULL DEFAULT 'free'` (только эта колонка; остальные tariff.md §7.1.2–§7.1.7 — в M6).

7.2.1.2 Существующие записи получают `tariff='free'` по DEFAULT.

#### 7.2.2 Auth-svc — каталог Free и состояние

7.2.2.1 Каталог Free хардкодится в коде auth-svc (tariff.md §2.5).

7.2.2.2 REST: `GET /api/auth/tariff/catalog` — public, возвращает только Free (tariff.md §16.2.1); Pro/Max добавятся в M6.

7.2.2.3 REST: `GET /api/auth/me/tariff` — возвращает `{tariff: 'free', limit_task_shares, limit_projects, limit_teams, usage_task_shares, usage_projects, usage_teams}`. Поля `auto_renew`, `tariff_until`, `pro_bank_days`, `payment_method_*` в M5 не возвращаются.

7.2.2.4 Pydantic-модель ответа: M5-вариант с возможностью неинвазивного расширения в M6 (см. 8.2.2.2).

#### 7.2.3 gRPC GetUserLimits

7.2.3.1 `contracts/proto/auth.proto`: метод `GetUserLimits(user_id) → {task_shares: int, projects: int, teams: int}` (tariff.md §18.2; ARCH §6.4).

7.2.3.2 В M5 реализация всегда возвращает Free-значения (200, 3, 3). В M6 метод расширится — динамические лимиты по тарифу (см. 8.2.7.4).

7.2.3.3 Кодоген клиента в `backend/tasks-service/generated/grpc_pb/` (ARCH §5.4.4).

#### 7.2.4 Tasks-svc — limit enforcement

7.2.4.1 Pre-check `tariff_limit_exceeded` перед INSERT во всех точках tariff.md §4.2.

7.2.4.2 Лимиты получаются через gRPC `GetUserLimits` с in-process кешем; TTL 5 минут (значения в M5 статичны, кеш бесполезен — но даёт правильную форму для M6).

7.2.4.3 Атомарность: limit-check + INSERT в одной транзакции с advisory-lock на `user_id` адресата (tariff.md §18.5).

7.2.4.4 В bulk: per-item статус `tariff_limit_exceeded` с полями `subject_email`, `metric`, `limit` (tariff.md §4.3, §17.1.1).

7.2.4.5 В batch: первое `tariff_limit_exceeded` откатывает всю транзакцию (tariff.md §4.4).

#### 7.2.5 Grandfathering существующих пользователей

7.2.5.1 На момент миграции у части пользователей возможно состояние `count > limit` по любой из трёх метрик (создано до enforcement).

7.2.5.2 Эти permission-записи сохраняются как есть; freeze не применяется (инфраструктура freeze появится в M6).

7.2.5.3 Новые добавления после rollout гейтятся §7.2.4 на адресате — пользователь с `usage > limit` не принимается в новые сущности до self-revoke.

7.2.5.4 По мере self-revoke `usage` уменьшается; когда `usage ≤ limit` — пользователь снова может приниматься в новые сущности.

#### 7.2.6 CLI

7.2.6.1 Группа `clite tariff` с командами `show` и `catalog` (tariff.md §15.1–§15.2).

7.2.6.2 `tariff show` — поля `tariff`, `usage_task_shares`, `limit_task_shares`, `usage_projects`, `limit_projects`, `usage_teams`, `limit_teams`. Без `auto_renew`, `pro_bank_days`, `payment_method_*`.

7.2.6.3 `tariff catalog` — выводит Free.

7.2.6.4 Поддержка `--fields` и line-by-line рендер (PRD §7.9, 4.2.8).

7.2.6.5 Команды `tariff upgrade`, `tariff cancel`, `tariff payments`, `tariff payment-method *`, флаг `--include-frozen` — в M5 отсутствуют; появятся в M6.

#### 7.2.7 CLI test cases

7.2.7.1 Новая глава `TC §11` в `cli-test-cases.md` с под-главой `§11.1` для M5.

7.2.7.2 Кейсы: `tariff show` на свежем юзере; `tariff catalog` без auth; `tariff_limit_exceeded` при попытке создать 4-ю команду; per-item статус в bulk; полный откат batch; grandfathering: пользователь с 5 командами видит `usage_teams: 5, limit_teams: 3` и не принимается в новую; после self-revoke 3-х команд снова может приниматься.

7.2.7.3 Автотесты в `cli/tests/e2e/` под testcontainers (PostgreSQL + auth-svc + tasks-svc + nginx-stub).

### 7.3 Done criteria

7.3.1 `clite tariff show` показывает `tariff: free`, `limit_teams: 3`, `usage_teams` равен реальному количеству активных команд пользователя.

7.3.2 Free-пользователь получает `tariff_limit_exceeded` при попытке создать 4-ю команду.

7.3.3 Пользователь с 5 командами (созданными до rollout) видит `usage_teams: 5`, `limit_teams: 3`; новые приглашения в команды для него отбиваются с `tariff_limit_exceeded`.

7.3.4 После self-revoke из 3-х команд (становится `usage_teams: 2`) пользователь снова может приниматься в новые.

7.3.5 В bulk-операции с лимит-провалом — per-item статус с полями `subject_email`, `metric`, `limit`; в batch — полный откат.

7.3.6 CI green: новые TC §11.1 покрыты автотестами.

## 8. M6 — Pro/Max и ЮКасса биллинг

### 8.1 Цель

8.1.1 Запуск платных тарифов Pro и Max с биллингом через ЮКассу, freeze permission-записей при downgrade, банк Pro-дней при upgrade Pro→Max.

8.1.2 Завершает разделы `tariff.md`: §5–§6, §7.1.2–§7.1.7, §8–§14, §15.3–§15.8, §15.15–§15.20, §16.2.3–§16.2.9, §17.2.1–§17.2.6, §18.3, §19.1.2, §19.2.

### 8.2 Делverables

#### 8.2.1 Миграции БД

8.2.1.1 `auth.users` расширяется колонками `tariff_until`, `tariff_auto_renew`, `pro_bank_days`, `payment_method_token`, `payment_method_last4`, `payment_method_brand` (tariff.md §7.1.2–§7.1.7; ARCH §3.6.7).

8.2.1.2 Создаётся `auth.payment_events` (tariff.md §14.1, §19.1.2; ARCH §3.6.8).

8.2.1.3 `tasks.task_user_shares`, `tasks.project_user_members`, `tasks.team_members` получают `frozen bool NOT NULL DEFAULT false` (tariff.md §5.1, §19.2; ARCH §3.5.17).

8.2.1.4 Индексы `(user_id, frozen, created_at)` на трёх permission-таблицах из 8.2.1.3.

8.2.1.5 Колонка `created_at` гарантируется на трёх permission-таблицах; добавляется этой же миграцией с дефолтом `now()`, если отсутствует.

8.2.1.6 One-time freeze-миграция: для пользователей-grandfathered из M5 (где `usage > limit_free`) применяется первичный freeze новейших excess-записей по алгоритму tariff.md §6.2.

#### 8.2.2 Каталог расширяется и состояние

8.2.2.1 Catalog endpoint начинает возвращать Pro и Max (tariff.md §2.6, §2.7); цены и лимиты — из tariff.md.

8.2.2.2 `tariff show` возвращает дополнительные поля: `auto_renew`, `tariff_until`, `pro_bank_days`, `payment_method_present`, `payment_method_last4`, `payment_method_brand` (tariff.md §15.10).

8.2.2.3 Коды ошибок: `tariff_not_an_upgrade`, `tariff_not_active`, `tariff_already_cancelled`, `payment_method_absent`, `payment_method_verification_failed`, `payment_declined` (tariff.md §17.2).

#### 8.2.3 Auth-svc — ЮКасса интеграция

8.2.3.1 Клиент к ЮКасса API: создание payment intents для upgrade и для payment-method verification, токенизация и сохранение recurring-токена.

8.2.3.2 Webhook `POST /api/auth/payments/yookassa-callback` с HMAC-валидацией подписи (tariff.md §13, §16.2.9).

8.2.3.3 Идемпотентность webhook по `payment_id`.

8.2.3.4 Маршрутизация webhook по `metadata.purpose` ∈ `{upgrade, payment_method_verification, renewal}` (tariff.md §13.4).

8.2.3.5 Тест-стаб ЮКассы: локальный HTTP-сервер на pytest fixture, эмулирует полный жизненный цикл платежа (intent → confirmation → webhook) и подписи.

8.2.3.6 Env на проде: `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `YOOKASSA_WEBHOOK_SECRET` в `.env.prod` (ARCH §17.2.2.3).

#### 8.2.4 Auth-svc — upgrade / cancel / payment-method flow

8.2.4.1 REST: `POST /api/auth/me/tariff/upgrade` — валидирует strict-выше-текущего, создаёт payment intent, возвращает `{confirmation_url, payment_id}` (tariff.md §9, §16.2.4).

8.2.4.2 Webhook-обработчик upgrade применяет state-переходы из tariff.md §9.3, включая credit банка при Pro→Max (§11.2–§11.5).

8.2.4.3 REST: `POST /api/auth/me/tariff/cancel` — выключает `tariff_auto_renew`, событие `tariff_cancelled` (tariff.md §10, §16.2.5).

8.2.4.4 REST: `GET/POST/DELETE /api/auth/me/payment-method` — show / update / remove (tariff.md §12, §16.2.6–§16.2.8).

8.2.4.5 Webhook-обработчик payment-method verification заменяет токен карты, `last4`, `brand` (tariff.md §12.3.4).

8.2.4.6 `payment-method remove` имплицитно выключает auto-renew и пишет событие `tariff_cancelled` при переключении (tariff.md §12.4).

#### 8.2.5 Auth-svc — auto-renew и фазовые переходы

8.2.5.1 Фоновая asyncio-задача периодически опрашивает `auth.users` с `tariff_auto_renew=true AND tariff_until BETWEEN now AND now+N_HOURS` и инициирует рекуррентное списание через ЮКассу (tariff.md §8.1).

8.2.5.2 Обработка успешного списания (`tariff_renewed`): `tariff_until += 1 period` (tariff.md §8.2).

8.2.5.3 Обработка неуспешного списания (`tariff_renew_failed`): мгновенный фазовый переход в момент `tariff_until` (tariff.md §8.3, §11.6–§11.9).

8.2.5.4 Фоновая задача проверяет `tariff != free AND tariff_until < now` и инициирует фазовый переход (tariff.md §11.6).

8.2.5.5 Consume банка при `tariff=max AND tariff_until<now AND pro_bank_days>0` (tariff.md §11.7); иначе обычный downgrade на Free (§11.8).

8.2.5.6 По окончании банковой Pro-фазы — downgrade на Free (tariff.md §11.9).

#### 8.2.6 Auth-svc — журнал платёжных событий

8.2.6.1 Запись в `auth.payment_events` на каждом state-переходе (типы — tariff.md §14.2).

8.2.6.2 REST: `GET /api/auth/me/tariff/payments?cursor=` — курсорная пагинация, фиксированный лимит 50, сортировка `created_at desc` (tariff.md §14.4–§14.5, §16.2.3).

8.2.6.3 Курсор opaque base64 из `(created_at, id)` (симметрично ARCH §10.3).

#### 8.2.7 gRPC расширение

8.2.7.1 `contracts/proto/tasks.proto` (новый файл): метод `RecomputeFreezeForUser(user_id) → Empty` (tariff.md §18.3; ARCH §6.5.1).

8.2.7.2 Кодоген серверов и клиентов в `backend/auth-service/generated/grpc_pb/` и `backend/tasks-service/generated/grpc_pb/` (ARCH §5.4.4).

8.2.7.3 Auth-svc становится gRPC-клиентом tasks-svc — новое направление, порт 50051 (ARCH §1.2.3, §6.5).

8.2.7.4 `GetUserLimits` расширяется: вместо хардкода Free возвращает лимиты текущего тарифа пользователя; для Pro/Max — `null` (unlimited) на соответствующих полях.

8.2.7.5 Tasks-svc инвалидирует кеш лимитов конкретного пользователя по `RecomputeFreezeForUser` (для 7.2.4.2).

#### 8.2.8 Tasks-svc — frozen в effective-perm

8.2.8.1 Effective-perm резолвер из 4.2.2.5 расширяется: permission-запись с `frozen=true` не вносит вклад в Path A и Path B (PRD §6.2.1.3, tariff.md §5.2).

8.2.8.2 `task list` (PRD §7.1) исключает задачи, доступные исключительно через frozen-пути (tariff.md §15.19); задачи с хотя бы одним активным путём остаются (tariff.md §15.20).

8.2.8.3 RSQL-whitelist `x-rsql-fields` не включает поля тарифа/банка (tariff.md §20.3.8).

#### 8.2.9 Tasks-svc — RecomputeFreezeForUser сервер

8.2.9.1 gRPC-сервер в tasks-svc на порту 50051 для обработки входящих от auth-svc вызовов.

8.2.9.2 Реализация метода: для каждой из трёх permission-метрик получает текущий лимит через `GetUserLimits`, применяет алгоритм freeze (tariff.md §6.2) и unfreeze (§6.4).

8.2.9.3 После применения сбрасывает локальный кеш лимитов пользователя.

8.2.9.4 FIFO unfreeze при self-revoke active-записи: после удаления tasks-svc проверяет наличие frozen у того же пользователя по той же метрике и поднимает старейшую, если `count(active) < limit` (tariff.md §6.3).

#### 8.2.10 CLI: tariff группа расширяется

8.2.10.1 Команды `clite tariff upgrade`, `tariff cancel`, `tariff payments` (tariff.md §15.3–§15.5).

8.2.10.2 Группа `clite tariff payment-method` с командами `show`, `update`, `remove` (tariff.md §15.6–§15.8).

8.2.10.3 `tariff upgrade` и `payment-method update` — flow с открытием `confirmation_url` в браузере и `success, press enter to continue` (PRD §10.5).

8.2.10.4 Рендер unlimited: `∞` в TTY-выводе, `null` в `--output json`.

8.2.10.5 Флаг `--include-frozen` на `clite team list`, `clite project list`, `clite share user list` (tariff.md §15.15); по умолчанию `false`.

8.2.10.6 Поле `frozen: bool` всегда присутствует в выдаче этих list-команд (tariff.md §15.17).

8.2.10.7 `clite team get` и `clite project get` отдают `frozen: bool` (tariff.md §15.18).

#### 8.2.11 CLI test cases для платных тиров

8.2.11.1 Под-глава `TC §11.2` в `cli-test-cases.md` для M6.

8.2.11.2 Кейсы базового flow: happy-path upgrade на Pro через ЮКасса-stub; upgrade Pro→Max с проверкой `pro_bank_days`; `tariff cancel` и `tariff_auto_renew=false`; `payment-method update`; `payment-method remove` имплицитно выключает auto-renew.

8.2.11.3 Кейсы freeze/unfreeze: downgrade Pro→Free фризит новейшие excess-команды; `--include-frozen` показывает их; FIFO unfreeze при self-revoke; upgrade обратно — все размораживаются.

8.2.11.4 Кейс банка: upgrade Pro→Max при `tariff_until > now`; ускоренное истечение Max через прямой UPDATE в тесте; auto-переход в banked Pro; событие `tariff_bank_consumed`; банка обнуляется.

8.2.11.5 Кейсы webhook: невалидная HMAC-подпись → 401; повторный webhook с тем же `payment_id` → 200 без дубликата.

8.2.11.6 Кейс one-time freeze-миграции (8.2.1.6): grandfathered M5-пользователь с 5 командами после миграции получает 2 frozen-записи (новейшие); видны с `--include-frozen`.

8.2.11.7 Автотесты в `cli/tests/e2e/` под testcontainers + ЮКасса-stub из 8.2.3.5.

#### 8.2.12 Документация в docs-client

8.2.12.1 Страница каталога тарифов с источником `/api/auth/tariff/catalog`.

8.2.12.2 Без интерактива покупки (PRD §1.2; tariff.md §20.5.1).

### 8.3 Done criteria

8.3.1 На стейдже автор `clite tariff upgrade pro --period monthly` через ЮКасса-stub; `tariff show` показывает `pro`, `tariff_until` через 1 месяц, `payment_method_last4` непустой.

8.3.2 `tariff payments` показывает `tariff_upgraded` с полями `from=free, to=pro, period=monthly, amount_rub=99, payment_id`.

8.3.3 `tariff cancel` устанавливает `auto_renew=false`; ручной сдвиг `tariff_until` в прошлое запускает фазовый переход в Free.

8.3.4 Pro→Max upgrade зачисляет остаток в `pro_bank_days`; в `tariff payments` есть `tariff_bank_credited`; consume банка после истечения Max работает.

8.3.5 Downgrade Pro→Free при состоянии 5 команд: новейшие 2 видны с `--include-frozen` как frozen и не дают доступа к задачам через эти команды.

8.3.6 Self-revoke не-frozen команды при наличии frozen → старейшая frozen разморожена.

8.3.7 ЮКасса webhook отбивает невалидную подпись 401; повторный webhook идемпотентен.

8.3.8 One-time freeze-миграция фризит excess-записи у grandfathered M5-пользователей; видны с `--include-frozen`.

8.3.9 CI green: новые TC §11.2 покрыты автотестами; coverage не падает ниже порога M1.

## 9. Сквозные требования

9.1 Все Python-функции/методы/атрибуты — с аннотациями типов (PRD §11.2).

9.2 `mypy --strict` без исключений.

9.3 Любое изменение контракта (OpenAPI или proto) — пересгенерированные клиенты в том же PR (ARCH §18.1.3, §18.1.4).

9.4 Каждый деплой — миграции через Alembic в entrypoint (ARCH §3.3).

9.5 С M2: новая CLI-команда не мерджится без обновления `cli-test-cases.md` и соответствующего теста.

## 10. Зависимости между милстоунами

10.1 M0 → M1: M1 нуждается в готовом каркасе и автодеплое.

10.2 M1 → M2: M2 строит auth поверх рабочей tasks-svc; модели задач из M1 расширяются перм-моделями.

10.3 M2 → M3: автоматизации требуют project-модель, secrets-модель, multi-user (события генерируются разными актёрами).

10.4 M4 параллелен M2 и M3 после M1: автогенерация CLI/RSQL/event справки требует M3 в полном объёме (для каталога system-method), но скелет docs-client и tutorials могут начаться раньше.

10.5 M2 → M5: M5 требует auth-svc с magic-link-auth и tasks-svc с полной permission-моделью (для подсчёта `usage_*` и enforcement).

10.6 M5 → M6: M6 расширяет state-модель тарифа, добавляет freeze-инфраструктуру, ЮКасса-интеграцию, банк, payment-method.

10.7 M5 параллелен M3 и M4 после M2.

10.8 M6 параллелен M3 и M4 после M5.
