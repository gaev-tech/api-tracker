# Архитектура бэкенда

Описание сервисов, их ответственности, таблиц, API и коммуникации. Изменяется при добавлении новых сервисов, endpoint'ов, изменении бизнес-логики.

Общие принципы архитектуры — в `architecture.md`. Инфраструктура — в `architecture-infra.md`.

---

## 1. Декомпозиция на сервисы

### 1.1. identity-service

**Ответственность.** Управление пользователями и аутентификация.

**Владеет таблицами:**
- `users` (включая `parent_user_id`, `is_active`, `email_verified_at`, `email_verification_token`)
- `refresh_tokens` — JWT refresh tokens (id, user_id, token_hash, expires_at, revoked_at, created_at)
- `pats`
- `password_reset_tokens`

**Публичные функции через API:**
- Регистрация, логин, логаут, смена пароля, сброс пароля.
- Подтверждение email по токену.
- CRUD PAT.
- Управление managed-пользователями (CRUD, деактивация/ре-активация, сброс пароля).
- Смена темы и языка пользователя.
- Поиск пользователей.
- Удаление собственного аккаунта.

**JWT:** RS256. Приватный ключ генерируется при деплое, хранится в K8s Secret `identity-jwt-keys`, инжектится в env `JWT_PRIVATE_KEY` (PEM). Публичный ключ экспонируется через `GET /.well-known/jwks.json` — api-gateway загружает при старте для локальной верификации JWT.

**Внутренние функции через gRPC:**
- Валидация PAT → возврат `user_id`, `is_active`, `parent_user_id` (вызывается api-gateway).
- Получение профиля пользователя по `id` (fallback для других сервисов, когда локальный кеш пуст).

**Отправляет email:** отправляет письма подтверждения email и сброса пароля напрямую (SMTP-клиент или через Transactional Email Provider). Отдельного notifications-service нет.

**БД:** обычный PostgreSQL. Таблицы небольшие, сильно нормализованные, шардирование не нужно.

**Публикует в Kafka:**
- Топик `user-events`: `user.created`, `user.updated`, `user.deleted`, `user.managed_created`, `user.managed_email_verified`, `user.managed_deactivated`, `user.managed_reactivated`, `user.managed_password_reset`.
- Топик `pat-events`: `pat.created`, `pat.revoked` (опционально — для аудита).

**Потребляет из Kafka:** ничего.

### 1.2. workspace-service

**Ответственность.** Основная бизнес-логика продукта: проекты, команды, задачи, доступы, массовые операции, импорт.

**Владеет таблицами:**
- `teams`, `team_members`, `team_invitations`, `team_ownership_transfers`
- `projects`, `project_members`, `project_teams`, `project_invitations`, `project_ownership_transfers`, `project_secrets`
- `tasks`, `task_projects`, `task_blockers`, `task_direct_accesses`
- `users_cache` — денормализованная копия `(user_id, email, is_active)` для валидации по email в CSV-импорте и отображения email в ответах API.

**Публичные функции через API:**
- CRUD задач, проектов, команд.
- Прямые доступы на задачи.
- Проектные и командные приглашения.
- Передача владения проектами и командами.
- Массовые операции над задачами (by filter / by ids).
- CSV-импорт.
- RSQL-парсинг и эвалюация.
- Управление автоматизациями в проекте: endpoint'ы на этом сервисе служат фасадом, они проверяют R-11 и далее вызывают automations-service по gRPC. Для клиента все endpoint'ы выглядят единообразно.

**Внутренние функции через gRPC:**
- Проверка прав пользователя на задачу (для files-service при выдаче URL скачивания).
- Проверка R-11 пользователя в проекте (для automations-service).
- Получение минимальных данных задачи по ID (для других сервисов).

**БД:** Citus. Distribution key — `owner_id` у верхних сущностей (projects, teams); связанные таблицы (`project_members`, `project_teams`, `project_invitations`, `project_secrets`) шардируются по `project_id` и co-locate с `projects`. Задачи не имеют владельца, но шардируются по `author_id` (со-локация с денормализованным `users_cache`). Дочерние таблицы задач (`task_projects`, `task_blockers`, `task_direct_accesses`) — по `task_id` co-locate с `tasks`.

**Публикует в Kafka:**
- Топик `task-events`: все события `task.*`.
- Топик `project-events`: все события `project.*`.
- Топик `team-events`: все события `team.*`.

**Потребляет из Kafka:**
- `user-events` → обновление `users_cache`.
- События `*.blocked_by_tariff` / `*.unblocked_by_tariff` от billing-service → применение флагов.

### 1.3. automations-service

**Ответственность.** Выполнение автоматизаций: подписка на события, применение RSQL-условий, HTTP-вызовы с ретраями.

**Владеет таблицами:**
- `automations` (включая поля: триггер, RSQL-условие, шаблон вызова, `is_enabled`, `consecutive_failures`, `is_blocked_by_tariff`).
- `automation_runs` — история срабатываний.
- `tasks_cache` — денормализованная копия полей задач, нужных для применения RSQL-условий (`id`, `title`, `status`, `assignee_id`, `author_id`, `tags`, `project_ids`, `created_at`, `updated_at`).

**Публичные функции через API:** отсутствуют напрямую — все клиентские запросы идут через workspace-service, который проверяет права и затем через gRPC вызывает automations-service.

**Внутренние функции через gRPC:**
- Создать, обновить, удалить автоматизацию.
- Включить/выключить автоматизацию.
- Получить автоматизацию / список автоматизаций проекта.
- Получить историю срабатываний автоматизации.

**Механика работы:**
1. Consumer Kafka-событий читает топики `task-events`, `project-events`, `team-events`, `automation-events`, `user-events`.
2. Для каждого события ищет подписанные автоматизации (`trigger_event_type == event.type`, `is_enabled = true`, `is_blocked_by_tariff = false`).
3. Применяет RSQL-условие к денормализованным данным задачи из `tasks_cache`.
4. Для прошедших условие — подставляет шаблон и делает HTTP-вызов (таймаут 30 сек).
5. При ошибке — retry с экспоненциальной задержкой (1 мин → 5 мин → 15 мин).
6. После 10 подряд неуспехов — выключает автоматизацию, публикует `automation.auto_disabled`.
7. Секреты проекта получает по gRPC из workspace-service; секреты кешируются в памяти с TTL.

**БД:** Citus. Distribution key — `project_id` для `automations` и `automation_runs`; `id` или `author_id` для `tasks_cache` (в зависимости от частых паттернов чтения — скорее всего `id`).

**Публикует в Kafka:** топик `automation-events`: `automation.enabled`, `automation.disabled`, `automation.auto_disabled`, `automation.blocked_by_tariff`, `automation.unblocked_by_tariff`.

**Потребляет из Kafka:** `task-events`, `project-events`, `team-events`, `user-events`, `automation-events` (для `tasks_cache` — `task-events`; для триггеров — все).

### 1.4. events-service

**Ответственность.** Долгосрочное хранение всех событий системы, отдача ленты событий через API и push-уведомления клиентам через WebSocket.

**Владеет таблицами:**
- `events` — партицированная по `created_at` (помесячно).

**Публичные функции через API:**
- `GET /events` с фильтрацией по автору, проекту, задачам, типу события, временному диапазону.
- `WS /events/stream` — WebSocket для push-уведомлений клиенту (актуальный счётчик pending-приглашений и потенциальные будущие типы сообщений).

**Внутренние функции через gRPC:** отсутствуют.

**Механика работы:**
- **Consumer Kafka:** подписан на все событийные топики. При получении события нормализует его и записывает в свою БД. Проверка прав пользователя при чтении ленты — через gRPC к workspace-service (видит ли пользователь задачу/проект/команду, к которой относится событие).
- **WebSocket:** при установке соединения валидирует PAT (gRPC в identity), ассоциирует соединение с `user_id`. Подписан на события `project-events` и `team-events` — при изменениях, влияющих на число pending-приглашений пользователя (создание приглашения, принятие/отклонение, отзыв), пушит обновлённый счётчик через открытое соединение. Если соединение с пользователем не установлено — ничего не делает (состояние восстановится при следующем подключении).
- **Состояние подключений** хранится в памяти сервиса. При масштабировании (несколько реплик) api-gateway применяет sticky routing по `user_id`, чтобы все соединения одного пользователя попадали в одну реплику.

**БД:** Citus. Distribution key — `created_at` (или `actor_id` при частых фильтрах по автору). Регулярная очистка старых партиций по политике retention (например, 1 год для Free, unlimited для платных — опционально, в рамках роадмапа).

**Публикует в Kafka:** ничего.

**Потребляет из Kafka:** все событийные топики.

### 1.5. billing-service

**Ответственность.** Тарифы, биллинг, лимиты, интеграция с ЮKassa.

**Владеет таблицами:**
- `subscriptions`
- `subscription_bank_layers`
- `subscription_history`
- `payment_transactions`
- `usage_counters` — агрегированные счётчики использования лимитов (задачи, проекты, команды, автоматизации, participants per project/team, managed users, storage bytes) per owner_user_id.

**Публичные функции через API:**
- Получить тарифы, подписку, использование, историю, заблокированные сущности.
- Апгрейд, даунгрейд, отмена даунгрейда.
- Покупка/уменьшение слотов Enterprise.
- Webhook от ЮKassa.

**Внутренние функции через gRPC:**
- Проверка «можно ли создать сущность типа X пользователю U» (вызывается workspace, files, automations перед созданием).
- Получение текущего состояния подписки по `user_id` (для ограничений на managed-операции в identity).

**Механика работы:**
- Consumer событий создания/удаления сущностей — обновляет счётчики в `usage_counters`.
- При смене тарифа / покупке/отмене слотов / деградации — пересчитывает лимиты, выставляет блокировки и публикует соответствующие события.
- Периодическая job-задача (cron) активирует запланированные даунгрейды и слои банка при наступлении `effective_at`.
- Webhook ЮKassa обрабатывает статусы платежей и применяет изменения (апгрейд, докупка слотов).

**БД:** обычный PostgreSQL. Таблицы небольшие, сильно связанные, без необходимости шардирования.

**Публикует в Kafka:**
- Топик `tariff-events`: `user.tariff_changed`, `user.tariff_bank_applied`.
- Топик `blocking-events`: все `*.blocked_by_tariff` / `*.unblocked_by_tariff`, `team.frozen_in_project`, `team.unfrozen_in_project`.

**Потребляет из Kafka:**
- `task-events`, `project-events`, `team-events`, `automation-events`, `user-events`, `file-events` — для подсчёта использования лимитов.

### 1.6. files-service

**Ответственность.** Хранение файлов: вложения в описания задач (inline в markdown) и CSV-файлы импорта.

**Владеет таблицами:**
- `files` — метаданные файла: `id`, `owner_user_id`, `task_id` (nullable; связь с задачей для attachment-файлов), `project_id` (nullable; для CSV-импортов), `s3_key`, `content_type`, `size_bytes`, `purpose` (`task_attachment` | `csv_import`), `uploaded_at`, `is_deleted`.

**Публичные функции через API:**
- `POST /files` — загрузка файла (multipart). Валидация MIME (magic bytes), размера (≤ 25 МБ), квоты. Сохранение в S3, запись метаданных. Возврат URL.
- `GET /files/{id}` — скачивание файла. Проверка прав через gRPC к workspace (при `task_id` — видит ли пользователь задачу).
- `DELETE /files/{id}` — удаление (soft-delete).

**Внутренние функции через gRPC:**
- Получить метаданные файла по `id` (для workspace при удалении задачи — каскадное удаление связанных файлов).

**Механика работы:**
- При загрузке — проверка MIME через magic bytes, проверка суммарного размера файлов пользователя через gRPC к billing-service, загрузка в S3 (streaming через сервис), сохранение записи в `files`.
- При скачивании — проверка прав через gRPC к workspace, отдача файла (streaming).
- Orphan-cleanup: фоновая job-задача находит файлы с `task_id` для удалённых задач и помечает `is_deleted = true`; файлы с `purpose = csv_import`, старше N дней — удаляются; S3-lifecycle-политика удаляет фактические объекты через M дней после пометки.

**Белый список MIME:**
- `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/svg+xml`
- `application/pdf`
- `text/*`
- `application/json`, `application/xml`
- `application/zip`, `application/x-gzip`, `application/x-tar`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/msword`
- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/vnd.ms-excel`
- `application/vnd.openxmlformats-officedocument.presentationml.presentation`, `application/vnd.ms-powerpoint`

**БД:** обычный PostgreSQL.

**Публикует в Kafka:** топик `file-events`: `file.uploaded`, `file.deleted`.

**Потребляет из Kafka:** `task-events` (на `task.deleted` — soft-delete связанных файлов).

### 1.7. api-gateway

**Ответственность.** Единая точка входа публичного API и WebSocket-подключений.

**Компонент:** Nginx **nginx:alpine** с `auth_request` модулем. В docker-compose окружении upstream DNS резолвится через Docker internal resolver (`resolver 127.0.0.11 valid=30s`) — это позволяет Nginx стартовать даже при отсутствии upstream-сервисов.

**Функции:**
- TLS termination (включая обработку TLS для WebSocket).
- Маршрутизация HTTP-запросов к нужным upstream-сервисам по префиксу URL.
- Проксирование WebSocket-подключений в events-service (`proxy_http_version 1.1`, `proxy_set_header Upgrade`/`Connection`; увеличенный `proxy_read_timeout` для длительных соединений).
- **Sticky routing для WebSocket** в events-service: используется Nginx upstream с `hash` по значению PAT (извлекается из query-параметра `token`) — все соединения одного пользователя попадают в одну реплику events-service. Это нужно потому, что состояние соединений в events-service in-memory; без sticky routing сервис не смог бы найти целевое соединение для push.
- PAT-валидация для обычных HTTP-запросов: при каждом запросе вызывается identity-service для проверки токена (с кешированием в Redis на TTL ≈ 60 сек).
- Передача результата валидации в headers: `X-User-Id`, `X-Parent-User-Id`, `X-Is-Active`.
- Rate limiting (per-PAT и per-IP).

**Маршрутизация (основная):**

| Префикс URL | Upstream |
|---|---|
| `/auth/*`, `/users/*`, `/pats/*`, `/managed-users/*` | identity-service |
| `/tasks/*`, `/projects/*`, `/teams/*`, `/invitations/*`, `/ownership-transfers/*` | workspace-service |
| `/projects/*/automations/*`, `/projects/*/secrets/*` | workspace-service (далее gRPC в automations/workspace внутри) |
| `/events`, `/events/stream` (WebSocket) | events-service |
| `/tariffs/*`, `/payments/*` | billing-service |
| `/files/*` | files-service |

---

## 2. Базы данных

### 2.1. Принцип «database per service»

Каждый сервис владеет своей БД. Другие сервисы не имеют прямого доступа к чужим таблицам — общение только через API или события.

### 2.2. PostgreSQL vs Citus

**Обычный PostgreSQL** используется в сервисах с умеренными объёмами и сильно связанными таблицами:
- identity-service: users, PATs, verification tokens.
- billing-service: subscriptions, bank layers, payment transactions.
- files-service: метаданные файлов.

**Citus** используется в сервисах с высокой нагрузкой и естественным ключом шардирования:
- workspace-service: шардирование по `owner_id` (projects, teams), `author_id` (tasks), `project_id` (связанные таблицы), `team_id`, `task_id`. Co-location настраивается для связанных таблиц.
- events-service: шардирование по `created_at` (временное) либо `actor_id`. Позволяет параллельный read из разных партиций.
- automations-service: шардирование по `project_id` (automations, automation_runs), `id` (tasks_cache).

### 2.3. Денормализация через события

Денормализованные копии данных между сервисами создаются там, где часты межсервисные чтения на hot path:

- **workspace.users_cache** — `(user_id, email, is_active)` для проверки assignee-email в CSV-импорте и отображения email'ов в ответах. Обновляется по `user-events`.
- **automations.tasks_cache** — поля задач, нужные для RSQL-условий. Обновляется по `task-events`.

Эти кеши eventually consistent. Читаемые через них данные могут отставать на секунды от источника (acceptable trade-off, так как чтения не критичны к абсолютной свежести).

### 2.4. Миграции

Миграции хранятся в репозитории рядом с кодом сервиса (директория `migrations/` внутри сервиса). Инструмент — `goose` или `golang-migrate`.

При старте сервиса (до начала приёма трафика) выполняется `goose up` / `migrate up` до последней версии. Если миграция не проходит — сервис не стартует, deployment останавливается. Helm-чарт использует `readinessProbe`, которая становится OK только после успеха миграций.

Для устойчивости к откатам миграции пишутся обратно-совместимыми: новая версия сервиса должна работать со старой и новой схемой. Несовместимые миграции разбиваются на несколько релизов.

---

## 3. Общие Go-пакеты (`backend/pkg/`)

Реализуются в I-16. Все пакеты — независимые Go-модули (или суб-пакеты единого модуля `backend/pkg/`), без циклических зависимостей.

### 3.1. `pkg/logging`

Обёртка над `log/slog` (стандартная библиотека Go 1.21+). Предоставляет:
- `New(service string) *slog.Logger` — создаёт logger с предустановленным полем `service`.
- Поля по умолчанию в каждом сообщении: `timestamp`, `level`, `service`.
- Gin middleware `RequestLogger(logger)` — добавляет к каждому запросу поля `request_id` (из заголовка `X-Request-ID`), `method`, `path`, `status`, `latency`.
- Формат вывода — JSON в stdout.

### 3.2. `pkg/metrics`

Gin middleware на базе `prometheus/client_golang`. Предоставляет:
- `Middleware(service string) gin.HandlerFunc` — счётчик запросов (`http_requests_total`, labels: `service`, `method`, `path`, `status`), гистограмма latency (`http_request_duration_seconds`).
- `Handler() http.Handler` — отдаёт `/metrics` endpoint для Prometheus scrape.

### 3.3. `pkg/sentry`

Стаб до реализации I-15. Предоставляет:
- `Init(dsn string) error` — no-op, возвращает nil. `// TODO: I-15 — подключить реальный Sentry SDK`.
- `CaptureError(ctx context.Context, err error)` — no-op. `// TODO: I-15`.

### 3.4. `pkg/grpc`

Обёртки для gRPC клиента и сервера. Предоставляет:
- `NewServer(opts ...grpc.ServerOption) *grpc.Server` — создаёт gRPC сервер с interceptor'ами: логирование, recovery, propagation `X-Request-ID` через metadata.
- `NewClient(target string, opts ...grpc.DialOption) (*grpc.ClientConn, error)` — создаёт клиент с таймаутом 5s по умолчанию, interceptor'ами логирования и propagation request_id.

### 3.5. `pkg/kafka`

Обёртки над `segmentio/kafka-go`. Предоставляет:
- `NewWriter(brokers []string, topic string) *kafka.Writer` — producer с настройками: batch, retry, required acks.
- `NewReader(brokers []string, topic, groupID string) *kafka.Reader` — consumer.

### 3.6. `pkg/outbox`

Реализация transactional outbox relay. Предоставляет:
- `Relay` struct — фоновая горутина, читающая из таблицы `<prefix>_outbox` неотправленные записи и публикующая их через `pkg/kafka` writer. Отмечает записи как `sent_at = now()` после успешной публикации.
- Таблица outbox (DDL в миграциях каждого сервиса): `id`, `topic`, `payload JSONB`, `created_at`, `sent_at`.

### 3.7. `pkg/rsql`

Парсер RSQL для Go. Предоставляет:
- `Parse(expr string) (Node, error)` — парсит RSQL-строку в AST.
- `ToSQL(node Node, allowedFields map[string]string) (string, []any, error)` — транслирует AST в SQL WHERE-фрагмент.
- Лимиты: максимум 4096 символов в выражении, максимум 1000 операндов в `=in=`.

### 3.8. Эталонный сервис `backend/services/ping/`

Минимальный рабочий сервис, использующий все pkg-пакеты. Назначение — проверить интеграцию стека и служить шаблоном для копирования при создании новых сервисов.

Структура:
```
backend/services/ping/
├── cmd/main.go          # точка входа
├── internal/
│   └── server.go        # Gin роутер + handlers
├── migrations/
│   └── 00001_init.sql   # пустая начальная миграция (goose)
├── Dockerfile
└── go.mod
```

Endpoints:
- `GET /healthz` → `200 OK` (liveness).
- `GET /readyz` → `200 OK` после успешных миграций (readiness).
- `GET /metrics` → Prometheus metrics (через `pkg/metrics`).

Инициализация при старте:
1. Читает конфиг из env: `PORT`, `DATABASE_URL`, `LOG_LEVEL`, `SENTRY_DSN`.
2. `pkg/sentry.Init(dsn)`.
3. `pkg/logging.New("ping")`.
4. Запускает миграции (`goose up` против `DATABASE_URL`).
5. Стартует HTTP-сервер.
6. Graceful shutdown по `SIGTERM`/`SIGINT` с таймаутом 30s.

Для локальной разработки — собственный PostgreSQL-контейнер `postgres-ping` в docker-compose (порт `:5435`, DB `ping_db`, user `ping_user`). Naming conventions из architecture-infra.md section 1.4.
