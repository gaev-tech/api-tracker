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

3.1.1 Автор начинает вести задачи разработки этого же проекта через `apit` без авторизации (`AUTH_MODE=disabled`).

### 3.2 Делverables

3.2.1 Модели tasks-svc: `Task`, `TaskBlocker`, `AuditEvent`; SOLO_USER создаётся при старте.

3.2.2 RSQL-парсер v1 (ARCH §8).

3.2.3 Эндпоинты:

3.2.3.1 `GET /api/v1/tasks?filter=&cursor=&limit=` (внутри tasks-svc — `/v1/tasks`, nginx стрипает `/api`).

3.2.3.2 `POST /api/v1/tasks` (single create).

3.2.3.3 `PATCH /api/v1/tasks/{id}`.

3.2.3.4 `POST /api/v1/tasks/bulk-update?filter=`.

3.2.3.5 `POST /api/v1/tasks/batch-update?filter=`.

3.2.3.6 `POST /api/v1/tasks/bulk-create`.

3.2.3.7 `POST /api/v1/tasks/batch-create`.

3.2.3.8 `GET /api/v1/history?task_id=&cursor=`.

3.2.4 Audit-логирование на каждой мутации.

3.2.5 CLI команды:

3.2.5.1 `apit task create`.

3.2.5.2 `apit task list`.

3.2.5.3 `apit task get`.

3.2.5.4 `apit task update`.

3.2.5.5 `apit task bulk-update`.

3.2.5.6 `apit task batch-update`.

3.2.5.7 `apit task bulk-create`.

3.2.5.8 `apit task batch-create`.

3.2.5.9 `apit history task`.

3.2.6 Alembic-миграции в entrypoint (ARCH §3.3).

3.2.7 OpenAPI auto-export в `contracts/openapi/tasks.json` в CI.

3.2.8 Тесты: unit и integration (testcontainers с postgres) — минимум 1 happy path и 1 ошибочный сценарий на каждый эндпоинт.

3.2.9 Публичный репозиторий `gaev-tech/cli-tracker` создан со скелетным README "coming soon"; release-workflow в GHA настроен для одной платформы (macOS arm64) и публикует pre-release `v0.1.0-dev` (ARCH §15.8).

### 3.3 Done criteria

3.3.1 Автор переносит roadmap M2–M4 в систему и работает с ним через `apit`.

3.3.2 Coverage по бэкенду измеряется в M1 и фиксируется как порог для следующих милстоунов.

## 4. M2 — Multi-user и CLI test cases

### 4.1 Цель

4.1.1 Переключение в `AUTH_MODE=jwt`, шаринг и совместная работа, формализация CLI-тест-кейсов.

### 4.2 Делverables

#### 4.2.1 Auth-svc

4.2.1.1 Модели: `User`, `MagicToken`, `RefreshToken`, `Session`, `CliAuthCode`, `DeviceCode`.

4.2.1.2 SMTP-интеграция (ARCH §17.2.2.3).

4.2.1.3 REST endpoints: `/api/magic/start`, `/api/magic/verify`, `/api/cli/code`, `/api/cli/exchange`, `/api/cli/device-start`, `/api/cli/device-approve`, `/api/cli/device-poll`, `/api/cli/refresh`, `/api/auth/refresh`, `/api/auth/logout`, `/api/sessions`.

4.2.1.4 gRPC-сервер: `GetUserByEmail`, `GetUsersByIds`, `GetJWKS` (ARCH §6).

4.2.1.5 Protobuf в `contracts/proto/auth.proto`.

#### 4.2.2 Tasks-svc

4.2.2.1 `AUTH_MODE=jwt` middleware, JWKS-кеш, gRPC-клиент к auth-svc.

4.2.2.2 Кеш `tasks.users` (ARCH §3.5.1) с фоновым refresher.

4.2.2.3 Новые модели: `TaskUserShare`, `TaskTeamShare`, `Team`, `TeamMember`, `Project`, `ProjectUserMember`, `ProjectTeamMember`, `ProjectTask`.

4.2.2.4 Эндпоинты team CRUD, project CRUD, share CRUD; anchor-rule валидация (PRD §6.6).

4.2.2.5 Effective-perm резолвер (PRD §6.2).

4.2.2.6 `GET /v1/history?user_id=<email>` с проверкой видимости (ARCH §10.2.2).

#### 4.2.3 Auth-client (Angular 20)

4.2.3.1 Страницы: `/`, `/magic`, `/cli-login`, `/sessions`, `/logout`.

4.2.3.2 orval-кодоген к auth-svc (ARCH §5.2).

4.2.3.3 Zod-валидация ответов и storage (ARCH §5.3).

#### 4.2.4 CLI

4.2.4.1 `apit login`, `apit login --device`, `apit logout`, `apit whoami`.

4.2.4.2 `apit team create/get/update/list`, `apit team member set/remove`, `apit team leave`.

4.2.4.3 `apit project create/get/update/list`, `apit project member set/remove`, `apit project leave`, `apit project task add/remove`.

4.2.4.4 `apit share user set/remove`, `apit share team set/remove` на задаче.

4.2.4.5 `apit history user`.

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

### 4.3 Done criteria

4.3.1 Автор приглашает второго пользователя по email; второй логинится через magic-link.

4.3.2 Автор шарит задачу второму пользователю; второй видит её в `apit task list`.

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

5.2.9 CLI: `apit automation create/list/get/update/delete/run-now`, `apit secret set/list/delete`.

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

6.3.2.1 Регистрация имени пакета `apit` на pypi.org; создание API-token, добавление в repo-secret `PYPI_TOKEN`.

6.3.2.2 GHA-job `pypi-publish` с `uv build` + `uv publish`.

6.3.2.3 Проверка: `pipx install apit` ставит работоспособный CLI.

6.3.3 Homebrew:

6.3.3.1 Создание публичного репо `gaev-tech/homebrew-apit` с `Formula/apit.rb`.

6.3.3.2 GHA-job `homebrew-publish` обновляет Formula с новой версией и SHA256, пушит в tap-репо через GitHub App.

6.3.3.3 Проверка: `brew install gaev-tech/cli-tracker/apit` ставит работоспособный CLI на macOS.

6.3.4 APT:

6.3.4.1 На прод-сервере поднимается статический APT-репо в `/var/lib/api-tracker/apt/`, отдаваемый nginx по `apt.apitracker.ru`.

6.3.4.2 Генерация GPG-ключа для подписи, публикация публичного ключа в `apt.apitracker.ru/key.gpg`; приватный — в repo-secret `APT_GPG_KEY`.

6.3.4.3 GHA-job `apt-publish` собирает `.deb`, подписывает, обновляет репо через `aptly`, пушит по SSH.

6.3.4.4 nginx-конфиг `apt.apitracker.ru` с TLS Let's Encrypt.

6.3.4.5 Проверка: установка по инструкции (ARCH §15.9.5.4) на чистой Ubuntu даёт работоспособный CLI.

6.3.5 npm:

6.3.5.1 Регистрация имени `@gaev-tech/cli-tracker` на npmjs.com; создание токена, добавление в repo-secret `NPM_TOKEN`.

6.3.5.2 Пакет в `cli/npm-wrapper/` — postinstall-скрипт качает бинарь из GitHub Releases по OS+arch.

6.3.5.3 GHA-job `npm-publish` с `npm publish --registry https://registry.npmjs.org/`.

6.3.5.4 Проверка: `npx @gaev-tech/cli-tracker --version` и `npm install -g @gaev-tech/cli-tracker` работают.

6.3.6 Документация в docs-client: страница "Installation" перечисляет все каналы установки с командами.

### 6.4 Done criteria

6.4.1 Сторонний пользователь по apitracker.ru может разобраться, поставить CLI, залогиниться, создать задачу — без помощи автора.

6.4.2 Установка через каждый из 5 каналов (GitHub Releases binary, PyPI, Homebrew, APT, npm) даёт работоспособный `apit --version` соответствующей версии.

## 7. Сквозные требования

7.1 Все Python-функции/методы/атрибуты — с аннотациями типов (PRD §11.2).

7.2 `mypy --strict` без исключений.

7.3 Любое изменение контракта (OpenAPI или proto) — пересгенерированные клиенты в том же PR (ARCH §18.1.3, §18.1.4).

7.4 Каждый деплой — миграции через Alembic в entrypoint (ARCH §3.3).

7.5 С M2: новая CLI-команда не мерджится без обновления `cli-test-cases.md` и соответствующего теста.

## 8. Зависимости между милстоунами

8.1 M0 → M1: M1 нуждается в готовом каркасе и автодеплое.

8.2 M1 → M2: M2 строит auth поверх рабочей tasks-svc; модели задач из M1 расширяются перм-моделями.

8.3 M2 → M3: автоматизации требуют project-модель, secrets-модель, multi-user (события генерируются разными актёрами).

8.4 M4 параллелен M2 и M3 после M1: автогенерация CLI/RSQL/event справки требует M3 в полном объёме (для каталога system-method), но скелет docs-client и tutorials могут начаться раньше.
