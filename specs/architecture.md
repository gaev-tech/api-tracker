# Техническая архитектура

Документ описывает техническую архитектуру облачного трекера задач. Включает: стек технологий, декомпозицию на сервисы, модель коммуникации, базы данных, инфраструктуру, деплой, наблюдаемость.

## 1. Обзор

### 1.1. Стиль архитектуры

Микросервисная архитектура. Сервисы разделены по bounded context'ам, каждый владеет собственной БД (database-per-service). Общение между сервисами:
- асинхронно — через Apache Kafka (event-driven интеграция);
- синхронно — через gRPC (межсервисные вызовы).

Публичное API для внешних клиентов и UI — HTTP/JSON через единый API Gateway.

### 1.2. Стек технологий

**Backend:**
- **Язык backend-сервисов:** Go.
- **HTTP-фреймворк:** Gin.
- **Reverse proxy и API Gateway:** Nginx.
- **Шина событий:** Apache Kafka.
- **Синхронный межсервисный RPC:** gRPC (контракты в `.proto`, кодогенерация).

**Frontend:**
- **Язык:** TypeScript.
- **Фреймворк:** Angular (последняя LTS).
- **Реактивность:** Angular Signals.
- **Асинхронные запросы:** RxJS поверх Angular HttpClient.
- **Роутинг:** Angular Router (с lazy loading по страницам).
- **Формы:** Angular Reactive Forms.
- **Сборщик:** Vite (через Angular builder).
- **Markdown-редактор:** Milkdown (в полях описания задач).
- **Runtime-валидация моделей:** Zod.
- **API-клиент:** генерируется автоматически из OpenAPI-спецификации backend.

**Хранилища и кеш:**
- **Базы данных:**
  - PostgreSQL для identity-service, billing-service, files-service.
  - Citus (распределённый PostgreSQL) для workspace-service, events-service, automations-service.
- **Кеш:** Redis — кеш PAT-валидаций в api-gateway.
- **Объектное хранилище:** S3-совместимое (облачное S3 или MinIO) — для вложений и CSV-импортов.

**Инфраструктура и деплой:**
- **Оркестрация:** Kubernetes.
- **Контейнеризация:** Docker — все сервисы (backend, frontend-приложения, вспомогательные) собираются в Docker-образы. Локальная разработка — через Docker Compose.
- **Платёжная интеграция:** ЮKassa.
- **Observability:** Prometheus (метрики) + Grafana (дашборды) + Sentry (ошибки) + Loki + Promtail (логи).
- **CI/CD:** GitHub Actions + GitHub Container Registry (ghcr.io). Push-деплой через `helm upgrade`.
- **Организация кода:** monorepo.
- **Миграции БД:** встроенные в сервис (выполняются при старте перед приёмом трафика).

### 1.3. Высокоуровневая диаграмма

```
                         ┌─────────────────────────────┐
                         │    External clients         │
                         │  (scripts, CI/CD, browsers) │
                         └──────────────┬──────────────┘
                                        │ HTTPS / HTTP/JSON
                                        ▼
                         ┌─────────────────────────────┐
                         │     api-gateway (Nginx)     │
                         │  TLS, routing, PAT-check,   │
                         │  rate-limit, Redis-cache    │
                         └──────────────┬──────────────┘
                                        │ HTTP/JSON
                  ┌─────────────────────┼─────────────────────┐
                  │             ┌───────┴───────┐             │
                  ▼             ▼               ▼             ▼
           ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
           │  identity  │  │ workspace  │  │automations │  │   events   │
           │            │  │            │  │            │  │            │
           │ PostgreSQL │  │   Citus    │  │   Citus    │  │   Citus    │
           └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
                 │               │               │               │
                 │         ┌─────┴───────┐       │               │
                 │         ▼             ▼       │               │
                 │  ┌────────────┐ ┌──────────┐  │               │
                 │  │  billing   │ │  files   │  │               │
                 │  │ PostgreSQL │ │PostgreSQL│  │               │
                 │  └─────┬──────┘ └────┬─────┘  │               │
                 │        │             │        │               │
                 │        │            S3        │               │
                 │        │                      │               │
                 └────────┴──────┬───────────────┴───────────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │    Kafka     │
                         │ (event bus)  │
                         └──────────────┘
```

Все сервисы публикуют события в Kafka (через transactional outbox) и потребляют нужные им топики. Синхронные связи между сервисами реализуются через gRPC (не отражены стрелками, чтобы не загромождать диаграмму).

---

## 2. Декомпозиция на сервисы

### 2.1. identity-service

**Ответственность.** Управление пользователями и аутентификация.

**Владеет таблицами:**
- `users` (включая `parent_user_id`, `is_active`, `email_verified_at`, `email_verification_token`)
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

**Внутренние функции через gRPC:**
- Валидация PAT → возврат `user_id`, `is_active`, `parent_user_id` (вызывается api-gateway).
- Получение профиля пользователя по `id` (fallback для других сервисов, когда локальный кеш пуст).

**Отправляет email:** отправляет письма подтверждения email и сброса пароля напрямую (SMTP-клиент или через Transactional Email Provider). Отдельного notifications-service нет.

**БД:** обычный PostgreSQL. Таблицы небольшие, сильно нормализованные, шардирование не нужно.

**Публикует в Kafka:**
- Топик `user-events`: `user.created`, `user.updated`, `user.deleted`, `user.managed_created`, `user.managed_email_verified`, `user.managed_deactivated`, `user.managed_reactivated`, `user.managed_password_reset`.
- Топик `pat-events`: `pat.created`, `pat.revoked` (опционально — для аудита).

**Потребляет из Kafka:** ничего.

### 2.2. workspace-service

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

### 2.3. automations-service

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

### 2.4. events-service

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

### 2.5. billing-service

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

### 2.6. files-service

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

### 2.7. api-gateway

**Ответственность.** Единая точка входа публичного API и WebSocket-подключений.

**Компонент:** Nginx с `auth_request` модулем.

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

## 3. Коммуникация между сервисами

### 3.1. Асинхронная — Kafka

**Шина событий** — Apache Kafka. Сервисы публикуют доменные события в топики по сущностям (`user-events`, `task-events`, `project-events`, `team-events`, `automation-events`, `file-events`, `tariff-events`, `blocking-events`).

**Transactional outbox pattern.** Producer-сервисы не пишут в Kafka напрямую из кода бизнес-логики. Вместо этого:
1. В той же локальной транзакции, что и изменение данных сервиса, в таблицу `<service>_outbox` вставляется запись события.
2. Отдельный фоновый процесс (outbox-relay) читает из outbox и публикует события в Kafka.
3. После успешной публикации запись в outbox помечается как отправленная.

Это даёт гарантию «изменение + событие атомарно». Без этого паттерна существует риск: данные изменены, но событие не улетело (или наоборот). Outbox реализуется как отдельная горутина в каждом producer-сервисе.

**Consumer groups.** Каждый сервис-потребитель имеет свою consumer group на нужные топики. Это позволяет разным сервисам независимо потреблять один и тот же поток событий.

**Retention.** По умолчанию 7 дней в Kafka (для устойчивости к сбоям потребителей). Долгосрочное хранение всей истории событий — в events-service.

**Схема событий.** Формат — JSON. Контракты событий описываются в общих proto-файлах (в monorepo), используются для кодогенерации типов в Go. Эволюция схем — через совместимые расширения (новые optional-поля).

### 3.2. Синхронная — gRPC

**Контракты.** Все gRPC-сервисы описаны в `.proto`-файлах в monorepo (директория `proto/`). Каждый сервис публикует свой `.proto`, другие сервисы подключают его через import. Go-клиенты и серверы генерируются в CI-пайплайне.

**Где применяется:**
- api-gateway → identity-service: `ValidatePAT(token)` → `{user_id, parent_user_id, is_active}`.
- workspace-service → automations-service: создание, обновление, удаление, включение, выключение автоматизации, чтение истории. Все операции, инициированные пользователем через публичный API, проходят сначала через workspace для проверки прав R-11, затем через gRPC в automations.
- workspace-service → billing-service: `CheckTariffLimit(user_id, entity_type)` перед созданием сущности (задача, проект, команда, автоматизация, managed).
- automations-service → workspace-service: получение секретов проекта по ID (с кешем).
- files-service → workspace-service: `CheckTaskAccess(task_id, user_id)` при скачивании файла вложения.
- files-service → billing-service: проверка квоты хранилища перед загрузкой.
- identity-service → billing-service: `CheckManagedLimit(parent_user_id)` перед созданием managed-пользователя.
- любой сервис → identity-service: `GetUser(user_id)` как fallback, если локального кеша нет.

**Таймауты и ретраи.** gRPC-вызовы имеют таймаут 5 секунд по умолчанию. Ретраи только на идемпотентных операциях, с экспоненциальной задержкой, не более 3 попыток. Кружок выключателя (circuit breaker) — через клиентскую библиотеку (например, `gobreaker`).

### 3.3. Публичное API — HTTP/JSON

Через api-gateway клиент попадает к нужному сервису. Каждый сервис экспонирует HTTP-API согласно спецификации в `api-spec.md`. Формат — JSON. Аутентификация — Bearer-токен (PAT).

---

## 4. Базы данных

### 4.1. Принцип «database per service»

Каждый сервис владеет своей БД. Другие сервисы не имеют прямого доступа к чужим таблицам — общение только через API или события.

### 4.2. PostgreSQL vs Citus

**Обычный PostgreSQL** используется в сервисах с умеренными объёмами и сильно связанными таблицами:
- identity-service: users, PATs, verification tokens.
- billing-service: subscriptions, bank layers, payment transactions.
- files-service: метаданные файлов.

**Citus** используется в сервисах с высокой нагрузкой и естественным ключом шардирования:
- workspace-service: шардирование по `owner_id` (projects, teams), `author_id` (tasks), `project_id` (связанные таблицы), `team_id`, `task_id`. Co-location настраивается для связанных таблиц.
- events-service: шардирование по `created_at` (временное) либо `actor_id`. Позволяет параллельный read из разных партиций.
- automations-service: шардирование по `project_id` (automations, automation_runs), `id` (tasks_cache).

### 4.3. Денормализация через события

Денормализованные копии данных между сервисами создаются там, где часты межсервисные чтения на hot path:

- **workspace.users_cache** — `(user_id, email, is_active)` для проверки assignee-email в CSV-импорте и отображения email'ов в ответах. Обновляется по `user-events`.
- **automations.tasks_cache** — поля задач, нужные для RSQL-условий. Обновляется по `task-events`.

Эти кеши eventually consistent. Читаемые через них данные могут отставать на секунды от источника (acceptable trade-off, так как чтения не критичны к абсолютной свежести).

### 4.4. Миграции

Миграции хранятся в репозитории рядом с кодом сервиса (директория `migrations/` внутри сервиса). Инструмент — `goose` или `golang-migrate`.

При старте сервиса (до начала приёма трафика) выполняется `goose up` / `migrate up` до последней версии. Если миграция не проходит — сервис не стартует, deployment останавливается. Helm-чарт использует `readinessProbe`, которая становится OK только после успеха миграций.

Для устойчивости к откатам миграции пишутся обратно-совместимыми: новая версия сервиса должна работать со старой и новой схемой. Несовместимые миграции разбиваются на несколько релизов.

---

## 5. Инфраструктура

### 5.1. Kubernetes

Все сервисы развёрнуты как Deployments с HorizontalPodAutoscaler. Минимум 2 реплики на сервис в production.

Компоненты кластера:
- **Ingress:** Nginx Ingress Controller. TLS-сертификаты — через cert-manager и Let's Encrypt.
- **Service Mesh:** на старте не используется; при необходимости добавляется Linkerd (лёгкий аналог Istio).
- **Kafka:** через Strimzi Operator — декларативное управление кластером Kafka в K8s. Минимум 3 брокера в production.
- **PostgreSQL и Citus:** managed-сервис облачного провайдера (предпочтительно) или через оператор (Zalando Postgres Operator / CloudNativePG) для self-hosted. Citus может быть развёрнут отдельно через Citus Community Operator.
- **Redis:** через оператор (Redis Operator) или managed-сервис.
- **Prometheus + Grafana + Loki:** через `kube-prometheus-stack` (Grafana Operator) и Loki Helm chart.
- **Sentry:** self-hosted через Helm либо облачный Sentry.
- **MinIO** (если не managed S3): через MinIO Operator.

### 5.2. Топология окружений

Минимум два окружения:
- **staging** — отдельный namespace (или отдельный кластер для изоляции) для интеграционного тестирования.
- **production** — основная среда.

Dev-окружение разработчика — локальный Kubernetes (Kind / Minikube / Docker Desktop) либо Docker Compose с минимальным набором зависимостей (Postgres, Kafka, Redis).

### 5.3. Секреты

Секреты хранятся в Kubernetes Secret, на старте инжектятся в pods через env / volume. Для боевого управления секретами может использоваться HashiCorp Vault или SealedSecrets — решение откладывается на более поздний этап.

---

## 6. Наблюдаемость

### 6.1. Метрики

**Prometheus** собирает метрики со всех сервисов:
- **Golden signals:** latency, traffic, errors, saturation для каждого сервиса.
- **HTTP-метрики:** из middleware Gin (request count, duration, status code).
- **gRPC-метрики:** из interceptor'ов (аналогично HTTP).
- **Kafka-метрики:** producer offset, consumer lag, commit rate.
- **БД-метрики:** pool size, active connections, slow queries (через pg_stat_statements в PostgreSQL/Citus).
- **Доменные метрики:** число созданных задач, проектов, автоматизаций в единицу времени; срабатываний автоматизаций; неуспешных срабатываний.

**Grafana** строит дашборды:
- Общий dashboard системы: здоровье всех сервисов, ошибки, latency.
- Dashboard каждого сервиса: свои метрики + потребление ресурсов.
- Dashboard Kafka: lag по consumer groups (особенно automations-service и events-service).
- Dashboard по тарифам: распределение пользователей по тарифам, доход, отказы платежей.

### 6.2. Ошибки

**Sentry** собирает все unhandled-исключения и HTTP 5xx-ошибки из сервисов через Go SDK. Context обогащается: user_id (если аутентифицирован), request_id, service name.

### 6.3. Логи

**Loki + Promtail.**
- Все сервисы пишут структурированные логи в stdout (JSON-формат).
- Promtail как DaemonSet на каждой ноде собирает логи pod'ов и отправляет в Loki.
- Loki индексирует метки (service, pod, severity), сам текст хранит сжатыми chunk'ами.
- Grafana предоставляет UI для поиска логов (LogQL).

**Стандартные поля в логе:** `timestamp`, `level`, `service`, `request_id`, `user_id`, `message`, `error` (если есть).

### 6.4. Request tracing

Распределённая трассировка на старте не подключается. Вместо этого — `request_id` в заголовке `X-Request-ID`, генерируется api-gateway, пробрасывается через все синхронные и асинхронные вызовы (в HTTP-заголовке, gRPC-metadata, в payload события). Логи всех сервисов по одному `request_id` выгребаются через Loki.

Если в будущем потребуется полноценный distributed tracing — добавляется OpenTelemetry + Grafana Tempo (совместим со стеком Grafana-Loki).

---

## 7. CI/CD и деплой

### 7.1. Monorepo-структура

Monorepo разделён на верхнем уровне по экосистемам и ролям артефактов:

```
/
├── backend/                        # всё, что бежит на Go
│   ├── services/                   # микросервисы
│   │   ├── identity/
│   │   │   ├── cmd/                # точка входа (main.go)
│   │   │   ├── internal/           # приватный код сервиса
│   │   │   ├── migrations/         # goose-миграции БД
│   │   │   ├── Dockerfile
│   │   │   └── go.mod
│   │   ├── workspace/
│   │   ├── automations/
│   │   ├── events/
│   │   ├── billing/
│   │   └── files/
│   ├── api-gateway/                # Nginx-конфиг + auth-sidecar для PAT-валидации
│   ├── pkg/                        # shared Go-модули
│   │   ├── service-template/       # базовый шаблон сервиса
│   │   ├── outbox/                 # transactional outbox relay
│   │   ├── grpc/                   # клиент/сервер обёртки
│   │   ├── kafka/                  # producer/consumer обёртки
│   │   ├── logging/                # структурированное логирование
│   │   ├── metrics/                # Prometheus-middleware
│   │   ├── sentry/                 # Sentry-интеграция
│   │   └── rsql/                   # парсер RSQL для backend
│   └── go.work                     # Go workspace для всех модулей
│
├── frontend/                       # Angular Workspace целиком
│   ├── angular.json
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── Dockerfile                  # multistage (node build → nginx:alpine)
│   ├── projects/
│   │   ├── app/                    # основное приложение
│   │   │   └── src/
│   │   │       ├── app/
│   │   │       ├── pages/
│   │   │       ├── core/
│   │   │       ├── services/
│   │   │       ├── components/
│   │   │       └── assets/
│   │   └── docs/                   # лендинг-документация
│   │       └── src/
│   │           ├── app/
│   │           ├── pages/
│   │           └── assets/
│   └── libs/                       # библиотеки workspace
│       ├── design-system/          # токены, базовые компоненты, иконки
│       ├── api-client/             # сгенерированный TS-клиент + Zod-схемы
│       ├── shared-widgets/         # кросс-экранные виджеты
│       ├── shared-utils/           # утилиты форматирования, i18n
│       ├── rsql/                   # клиентский парсер RSQL
│       └── markdown-editor/        # Milkdown-обёртка
│
├── contracts/                      # общие контракты между backend и frontend
│   ├── proto/                      # gRPC-контракты и схемы событий Kafka
│   │   ├── identity/
│   │   │   └── v1/                 # *.proto + сгенерированные *.pb.go, *_grpc.pb.go (коммитятся в репо)
│   │   ├── workspace/
│   │   │   └── v1/
│   │   ├── automations/
│   │   │   └── v1/
│   │   ├── events/
│   │   │   └── v1/
│   │   ├── billing/
│   │   │   └── v1/
│   │   ├── files/
│   │   │   └── v1/
│   │   ├── ping/                   # эталонный proto для проверки инфраструктуры codegen (I-17)
│   │   │   └── v1/                 # ping.proto + ping.pb.go + ping_grpc.pb.go
│   │   ├── buf.yaml
│   │   └── buf.gen.yaml            # конфигурация кодогенерации (local plugins, paths=source_relative)
│   └── openapi/                    # актуальная OpenAPI-спецификация (артефакт CI)
│       └── openapi.yaml
│
├── deploy/                         # всё, связанное с деплоем
│   ├── helm/                       # Helm-чарты
│   │   ├── identity/
│   │   ├── workspace/
│   │   ├── automations/
│   │   ├── events/
│   │   ├── billing/
│   │   ├── files/
│   │   ├── api-gateway/
│   │   ├── web-app/                # статика app за Nginx
│   │   ├── web-docs/               # статика docs за Nginx
│   │   └── infra/                  # kafka, postgres, citus, redis, minio, monitoring
│   └── compose/
│       └── docker-compose.yml      # локальное dev-окружение
│
├── docs-source/                    # markdown-исходники документации
│   ├── overview/                   # описание продукта
│   ├── scenarios/                  # ценностные сценарии
│   ├── guides/                     # «первые 10 минут» и др.
│   └── api-templates/              # шаблоны curl-примеров
│
├── tools/                          # вспомогательные скрипты
│   ├── openapi-gen/                # генерация OpenAPI из Go-сервисов
│   ├── openapi-to-ts/              # генерация TS-клиента + Zod из OpenAPI
│   ├── migrations/                 # утилиты работы с миграциями
│   └── scripts/
│
├── .gitlab-ci.yml
├── Makefile
└── README.md
```

**Принципы структуры:**

- **`backend/` и `frontend/` на верхнем уровне.** Разработчик сразу видит два понятных входа. Go-ориентированные артефакты (`go.work`, `pkg/`) не смешиваются со стандартными файлами Angular Workspace (`angular.json`, `package.json`, `node_modules/`).
- **`contracts/` отдельно.** Proto и OpenAPI — это межстековые контракты, не принадлежат ни backend, ни frontend эксклюзивно. Backend публикует `openapi.yaml` в этот каталог как CI-артефакт; frontend потребляет его через codegen. Это подчёркивает API-first характер продукта: контракт первичен.
- **`deploy/` объединяет helm и compose.** Оба относятся к развёртыванию: Helm-чарты для Kubernetes, `docker-compose.yml` для локального dev-окружения.
- **`docs-source/` отдельно.** Контент-авторы работают с markdown-исходниками, не касаясь `frontend/projects/docs/`. Angular-приложение docs при сборке подтягивает контент из этой директории.
- **`tools/` кросс-стековый.** Скрипты часто затрагивают оба стека (например, OpenAPI-генератор читает Go-код и генерирует TS-клиент).

### 7.2. Pipeline

Каждый push/merge запускает в GitHub Actions:

1. **Lint & static check:** `go vet`, `golangci-lint`, `buf lint` для proto-файлов.
2. **Code generation:** `buf generate` для proto → Go-типы.
3. **Unit-тесты.**
4. **Integration-тесты:** поднимаются через docker-compose (Postgres, Kafka).
5. **Build images:** для изменившихся сервисов. Path-based триггеры (`paths:` в workflow): изменение в `services/workspace/` → собирается только workspace. Image tagging: `ghcr.io/<owner>/<repo>/<service>:<commit-sha>`, плюс `:latest` для главной ветки. Теги branch-name не используются.
6. **Push в GitHub Container Registry (ghcr.io):** только при мерже в main. В pull request образы собираются (для проверки Dockerfile), но не публикуются. Все Docker-джобы находятся в `.github/workflows/ci-backend.yml` (отдельный файл для Docker не создаётся).
7. **Deploy на staging** (автоматически после успешного pipeline в main).
8. **Deploy на production** — ручное подтверждение (`environment: production` с required reviewers).

### 7.3. Деплой в Kubernetes

**Инструмент:** `helm upgrade --install <release> helm/<service>` из CI-job.

Helm-чарт каждого сервиса содержит:
- `Deployment` с указанием image-тега.
- `Service` для внутреннего gRPC/HTTP.
- `Ingress` (для сервисов с публичным API — фактически только api-gateway).
- `HorizontalPodAutoscaler`.
- `ServiceMonitor` (для Prometheus).
- ConfigMaps / Secrets.

**Стратегия обновления:** RollingUpdate. Один под обновляется за раз, старый pod'ы работают до готовности нового.

### 7.4. Откат

Откат через `helm rollback <release> <revision>` — возврат к предыдущему relised-тегу. Поскольку миграции обратно-совместимы, откат возможен без дополнительных шагов с БД.

---

## 8. Безопасность

### 8.1. Аутентификация

- **PAT** — единственный способ аутентификации на публичном API. Валидируется api-gateway, кешируется в Redis.
- **Мультиавторизация клиента.** Клиент (UI или стороннее приложение) может одновременно использовать несколько PAT, принадлежащих разным пользователям (например, управляемым пользователям одной организации). Каждый вызов несёт один конкретный PAT — сервер не оперирует понятием «сессии» или «активного пользователя клиента», эта логика полностью на стороне клиента.
- **WebSocket** — аутентификация через query-параметр `token` при установке соединения; валидация один раз при handshake через тот же путь identity-service (с Redis-кешем).
- **Внутренние вызовы между сервисами** через gRPC защищены mTLS (сертификаты генерируются cert-manager, раздаются сервисам как Kubernetes Secrets).

### 8.2. Авторизация

Все проверки прав (R-1…R-14, владение, права на управление managed) — внутри сервиса, владеющего соответствующими данными. api-gateway не делает авторизационных решений, кроме базовой PAT-валидации.

### 8.3. Rate limiting

На api-gateway: rate limit per-PAT (например, 100 запросов в секунду) и per-IP для неавторизованных endpoint'ов (регистрация, логин).

### 8.4. Хранение секретов

- `password_hash` в identity-service: Argon2id.
- `value_encrypted` в `project_secrets`: AES-256-GCM; ключ шифрования — в Kubernetes Secret, инжектится в workspace-service.
- `token` PAT хранится в открытом виде в БД identity-service (по продуктовому требованию: токен всегда видим владельцу через API), под строгим ограничением доступа к БД.
- **Клиентское хранение токенов.** PAT хранится клиентами в локальном хранилище (в случае UI — `localStorage`). Это осознанный trade-off: PAT доступен JavaScript и теоретически может быть эксфильтрован при XSS-атаке, но взамен поддерживается мультиавторизация и переживание перезагрузки страницы. Защита: строгий CSP, Angular-санитизация, отсутствие небезопасных DOM-операций (`innerHTML`, `eval`), санитизация пользовательского markdown через Milkdown.

### 8.5. Валидация входных данных

- Все HTTP-запросы валидируются через struct-теги в Go (например, `go-playground/validator`).
- RSQL-выражения парсятся и валидируются строго (лимит 4096 символов, лимит 1000 операндов в `=in=`).
- MIME загружаемых файлов проверяется через magic bytes, не только по Content-Type.

---

## 9. Frontend

### 9.1. Структура клиентских приложений

Два клиентских приложения:

- **app** — основное приложение-трекер: все экраны для работы пользователей (регистрация, логин, задачи, проекты, команды, автоматизации, события, тарифы, managed-пользователи). Аудитория — авторизованные пользователи.
- **docs** — лендинг-документация: публичный сайт с описанием продукта, документацией API (автогенерация из OpenAPI), примерами использования, шаблонами API-вызовов. Аудитория — как публика (без аутентификации), так и существующие пользователи, изучающие API.

Оба приложения реализованы на Angular, собираются как один Angular Workspace с общими библиотеками.

### 9.2. Angular Workspace

Единый `angular.json`, два приложения и несколько `libs` для переиспользуемого кода (детальная структура приведена в разделе 7.1 monorepo-структуры). Корень Angular Workspace — `/frontend/`:

```
/frontend/
├── angular.json
├── package.json
├── tsconfig.json
├── vite.config.ts
├── Dockerfile
├── projects/
│   ├── app/                    # основное приложение
│   └── docs/                   # лендинг-документация
└── libs/                       # библиотеки workspace
    ├── design-system/
    ├── api-client/
    ├── shared-widgets/
    ├── shared-utils/
    ├── rsql/
    └── markdown-editor/
```

Lib'ы — независимые модули Angular, импортируемые в приложениях через TypeScript path-mapping (`tsconfig.json` → `compilerOptions.paths`).

### 9.3. Структура приложения

Внутри каждого приложения код организован в стандартной Angular-модели с разделением на страницы, переиспользуемые компоненты и бизнес-логику:

```
/frontend/projects/app/src/
├── app/                         # корневая точка входа, AppComponent, глобальный routing
├── pages/                       # страничные компоненты; маршруты lazy-load по pages/*
│   ├── tasks-list/
│   ├── task-detail/
│   ├── projects-list/
│   ├── project-detail/
│   └── ...
├── core/                        # singleton-сервисы (аутентификация, guards, interceptors, хранилище токена)
├── services/                    # доменные сервисы (оболочки над api-client для tasks, projects, teams и т.д.)
├── components/                  # локальные переиспользуемые компоненты, не претендующие на shared-libs
└── assets/                      # статика (изображения, локализация и т.п.)
```

Переиспользуемые компоненты, работающие в обоих приложениях (app и docs), выносятся в `libs/*` Workspace (`design-system`, `shared-widgets`, `markdown-editor`, `api-client` и т.д.). Внутренние локальные компоненты конкретного приложения остаются в `frontend/projects/app/src/components/`.

### 9.4. Lazy loading страниц

Каждая страница (`pages/*`) подключается через Angular Router с `loadComponent` (или `loadChildren` для группировки). Это уменьшает начальный bundle — пользователь грузит только код той страницы, на которую он перешёл.

### 9.5. Дизайн-система

#### Иерархия дизайн-токенов

Три уровня токенов, каждый уровень может ссылаться только на предыдущий:

**1. Базовые токены (global).** Сырой палитр цветов, шрифтовые сетки, единицы отступов и скруглений. Примеры: `--color-blue-500: #3B82F6`, `--font-family-sans: "Inter", sans-serif`, `--space-4: 16px`.

**2. Семантические токены (semantic).** Осмысленные роли, ссылающиеся на базовые токены. Примеры: `--color-primary: var(--color-blue-500)`, `--color-text-default: var(--color-gray-900)`, `--color-background-surface: var(--color-white)`, `--color-danger: var(--color-red-600)`. При переключении темы (light/dark) семантические токены переопределяются на другие базовые.

**3. Компонентные токены (component).** Локальные токены конкретных компонентов, ссылающиеся на семантические. Примеры: `--button-primary-background: var(--color-primary)`, `--button-primary-text: var(--color-text-on-primary)`. Изменение этого уровня затрагивает только один компонент, не ломая общую тему.

Токены реализуются как CSS custom properties, что позволяет переключать темы без пересборки.

#### Типография

Единая шкала размеров и стилей (например, `text-xs`, `text-sm`, `text-base`, `text-lg`, `text-xl`, `text-2xl`). Шрифт — Inter (или аналог). Все текстовые стили применяются через утилитные классы или компонентные токены.

#### Иконки

Набор иконок оформлен как SVG-спрайт или отдельные SVG-компоненты. Библиотека иконок (например, Lucide или Heroicons) + кастомные иконки продукта. Единый компонент `<ds-icon name="..." size="..." />`.

#### Базовые компоненты

Реализованы в `libs/design-system`:
- Кнопки (primary, secondary, tertiary, danger; размеры xs/sm/md/lg; состояния loading/disabled).
- Инпуты (text, textarea, number, email, password, search).
- Селекты, мультиселекты.
- Чекбоксы, радио, свитчи.
- Модальные окна (dialog, confirmation, form).
- Попапы, тултипы, dropdown'ы.
- Чипы, бейджи.
- Таблицы (с сортировкой, пагинацией, чекбоксами строк).
- Avatar, иконки статусов.
- Алерты, тосты.
- Skeleton-loader'ы, спиннеры.
- Табы, аккордеоны.
- Date picker, date-range picker.

Все компоненты ориентируются на токены дизайн-системы, поддерживают тёмную тему из коробки.

### 9.6. API-клиент: OpenAPI codegen + Zod

**Генерация клиента.** В CI-пайплайне `docs` приложение читает OpenAPI-спецификацию backend (`openapi.yaml`, публикуемую backend'ом в CI-артефакт) и генерирует TypeScript-клиенты через `openapi-zod-client` или аналогичный инструмент. Результат — готовые функции-обёртки для каждого endpoint'а с типизированными запросом и ответом.

**Zod для runtime-валидации.** Сгенерированные TypeScript-типы дополняются соответствующими Zod-схемами. При получении ответа от API клиент прогоняет его через `Schema.parse()` — это защищает от несоответствия между реальным ответом сервера и ожидаемой моделью (например, при несовпадении версий client/server). При несовпадении валидации — ошибка с подробностями уходит в Sentry.

**Обёртка поверх HttpClient.** Сгенерированные функции используют Angular HttpClient под капотом. Параметры запросов кодируются стандартно (RSQL-выражения — как query-параметр, файлы — как multipart). RxJS Observable возвращается из каждой функции.

### 9.7. Milkdown для markdown-полей

Поле описания задачи (`description`) — markdown. В UI используется Milkdown как WYSIWYG-редактор с поддержкой markdown. Обёрнут в компонент `<ds-markdown-editor>` в `libs/markdown-editor`.

Вложения (изображения, файлы в описании) встраиваются inline через функционал редактора — при drop'е файла в редактор выполняется загрузка в files-service (`POST /files` с `task_id`), возвращённая ссылка вставляется в markdown. Просмотр без редактирования — через markdown-рендерер (обычно часть Milkdown).

### 9.8. Сборка и деплой

#### Docker-образы

Оба приложения собираются в Docker-образы (в multistage-Dockerfile: `node:alpine` → `ng build` → статика копируется в `nginx:alpine`-образ). Итоговый образ — минимальный Nginx, отдающий статические файлы.

#### Kubernetes-деплой

Два дополнительных Kubernetes Deployment в кластере:

- **web-app** — pod с Nginx, отдающий статику `frontend/projects/app`. Ingress на `app.example.com`.
- **web-docs** — pod с Nginx, отдающий статику `frontend/projects/docs`. Ingress на `docs.example.com` (или корневой `example.com`).

Оба ingress'а используют тот же cert-manager для TLS.

#### CI-пайплайн

В GitHub Actions path-based триггеры для frontend (`paths:` в workflow):
- Изменения в `frontend/projects/app/` или `frontend/libs/**` — пересборка и деплой web-app.
- Изменения в `frontend/projects/docs/` или `docs-source/` — пересборка и деплой web-docs.
- Публикация OpenAPI-спеки backend'ом (в отдельном job после сборки backend) триггерит пересборку docs и регенерацию `frontend/libs/api-client` — чтобы автогенерированные страницы API и TS-клиент всегда соответствовали актуальной спеке.

Таким образом, docs «автоматически собирается и деплоится вместе с приложением» — любой merge в main, меняющий API или UI, запускает синхронное обновление обоих клиентов.

#### Docker Compose для локальной разработки

Один `docker-compose.yml` в корне репозитория поднимает:
- PostgreSQL, Citus (в упрощённой конфигурации), Redis, Kafka, MinIO (S3-эмулятор);
- все backend-сервисы (identity, workspace, automations, events, billing, files) + api-gateway;
- оба frontend-приложения (app и docs) с hot-reload через Vite dev server.

Разработчик выполняет `docker compose up` и получает полный стенд на локальной машине.

### 9.9. Взаимодействие с API

Оба клиентских приложения вызывают backend через api-gateway (`https://api.example.com`). Аутентификация — Bearer-токен в заголовке `Authorization` для HTTP-запросов; для WebSocket — через query-параметр `token` при установке соединения.

**Мультиавторизация в app.** Приложение поддерживает одновременно несколько авторизованных аккаунтов. Токены и мета-информация сохраняются в `localStorage` в следующей структуре:

```json
{
  "accounts": [
    {
      "user_id": "uuid",
      "email": "user@company.com",
      "display_name": "Иван Иванов",
      "parent_user_id": "uuid-or-null",
      "token": "pat_...",
      "added_at": "ISO 8601"
    }
  ],
  "active_user_id": "uuid"
}
```

При каждом HTTP-запросе Angular HttpInterceptor читает `active_user_id` из сервиса аккаунтов и подставляет соответствующий токен. При переключении аккаунта меняется `active_user_id`, приложение сбрасывает кеши данных пользовательского контекста и перезагружает текущую страницу (или делает soft-refresh). При «Выйти» — запись удаляется из `accounts`, вызывается `POST /auth/logout` для отзыва PAT на сервере, активным становится следующий аккаунт из списка.

**Trade-off хранения в localStorage.** PAT доступен JavaScript → теоретически уязвим к XSS-атаке. Защита — на уровне приложения: строгий CSP (Content Security Policy), отсутствие опасных DOM-операций, санитизация пользовательского markdown через Milkdown. Преимущество — переживание перезагрузки и мультиавторизация без повторного логина.

**WebSocket-подключение.** UI-приложение устанавливает одно WebSocket-подключение к `wss://api.example.com/v1/events/stream?token=<PAT>` с токеном активного аккаунта. При переключении аккаунта — существующее соединение закрывается, открывается новое с новым токеном. Основное использование — получение счётчика pending-приглашений в реальном времени для отображения в сайдбаре.

**Docs-клиент.** Не требует аутентификации для большинства страниц (описание продукта, документация API). Для интерактивного «Try it out» в документации — опционально, пользователь может ввести свой PAT, который используется только внутри вкладки (в памяти, без записи в localStorage).

---



## 10. Масштабирование

### 10.1. Горизонтальное масштабирование сервисов

Все stateless-сервисы (identity, workspace, automations, events, billing, files, api-gateway) масштабируются через HPA по метрикам CPU и RPS.

### 10.2. Масштабирование БД

- **Citus-кластеры** (workspace, events, automations): добавление воркер-нод, ребаланс шардов.
- **PostgreSQL-сервисы** (identity, billing, files): вертикальное масштабирование; read replicas для read-heavy endpoint'ов (например, `GET /events` мог бы использовать реплики events-service, но там уже Citus).

### 10.3. Масштабирование Kafka

Добавление брокеров, увеличение числа партиций в топиках. Consumer group'ы автоматически перераспределяются.

### 10.4. Гео-распределение

На старте — один регион. Переход на multi-region — отдельный проект, вне текущего роадмапа.
