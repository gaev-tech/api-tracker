# Архитектура API

## Обзор

Микросервисная архитектура с принципом database-per-service. Все публичные операции доступны через единый API Gateway. Внутренние сервисы общаются асинхронно через Kafka и синхронно через gRPC.

## Стек

| Слой | Технология |
|------|-----------|
| Язык бэкенда | Go |
| HTTP-фреймворк | Gin |
| Реляционная БД | PostgreSQL (CloudNativePG Operator) |
| Очередь сообщений | Kafka (Strimzi) |
| Внутренние вызовы | gRPC |
| Gateway | Nginx |
| Миграции | Goose (embedded, запуск при старте сервиса) |
| Контейнеризация | Docker |
| Оркестрация | K3s (bare-metal, single node) |

## Монорепо

```
backend/
  services/
    identity-service/
    workspace-service/
    automations-service/
    events-service/
    billing-service/
  pkg/
    logging/       # структурированные логи (zap)
    metrics/       # Prometheus-метрики
    sentry/        # интеграция с Sentry
    grpc/          # клиент/сервер с retry и таймаутами
    kafka/         # producer/consumer с transactional outbox
    outbox/        # outbox worker
    rsql/          # парсер и транслятор RSQL → SQL
contracts/
  proto/           # .proto-файлы для gRPC
  openapi/         # openapi.yaml (генерируется)
deploy/
  helm/            # Helm-чарты per-service
  docker-compose.yml
```

## Сервисы

### identity-service

**Ответственность:** регистрация, аутентификация (OAuth 2.0 Authorization Code Flow), управление PAT, managed-пользователи (PostMVP).

Является authorization server системы: выдаёт authorization code, обменивает на access + refresh token, обновляет токены. Все клиенты (веб-приложение, CLI, клиент авторизации) аутентифицируются через единый OAuth 2.0 Authorization Code Flow с PKCE (Proof Key for Code Exchange) для public clients.

**БД:** PostgreSQL

Ключевые таблицы: `users`, `pats`, `refresh_tokens`, `oauth_clients`, `authorization_codes`.

Managed-пользователи хранятся в той же таблице `users` с полем `parent_user_id`; вложенность — один уровень, проверяется на уровне приложения.

**Kafka topics (publish):**
- `identity.user.registered`
- `identity.user.deleted`
- `identity.pat.created`
- `identity.pat.revoked`

**gRPC (internal):**
- `ValidateToken(token) → UserID` — вызывается Gateway при каждом запросе (поддерживает и access token, и PAT)
- `GetUser(id) → User` — вызывается workspace-service

---

### workspace-service

**Ответственность:** задачи, проекты, команды, доступы, приглашения, передача владения.

**БД:** PostgreSQL. Индексы по `owner_id` для проектов/команд.

Ключевые таблицы: `tasks`, `task_projects`, `task_blockers`, `task_direct_accesses`, `projects`, `project_members`, `project_invitations`, `project_ownership_transfers`, `teams`, `team_members`, `team_invitations`, `team_ownership_transfers`, `users_cache`.

`users_cache` — денормализованная копия данных пользователей, обновляется по Kafka-событиям от identity-service. Используется для поиска и отображения без gRPC-вызовов в hot path.

`task_direct_accesses` хранит 8 битовых флагов (R-1…R-8) в одном integer-поле.

**Kafka topics (publish):**
- `workspace.task.*`
- `workspace.project.*`
- `workspace.team.*`

**Kafka topics (consume):**
- `identity.user.*` — обновление `users_cache`

**gRPC (internal):**
- `GetTaskRights(user_id, task_id) → Rights` — вызывается automations-service
- `GetProjectMembers(project_id) → []Member`

---

### automations-service

**Ответственность:** автоматизации, секреты проектов, выполнение HTTP-вызовов по триггерам (PostMVP).

**БД:** PostgreSQL. Индексы по `project_id`.

Ключевые таблицы: `automations`, `automation_runs`, `project_secrets`, `tasks_cache`.

`tasks_cache` — денормализованная копия полей задач для оценки RSQL-условий без JOIN в workspace. Обновляется по Kafka.

Секреты хранятся зашифрованными; ключ шифрования — из переменной окружения (не в БД).

**Kafka topics (consume):**
- `workspace.task.*` — триггеры автоматизаций, обновление `tasks_cache`

**Kafka topics (publish):**
- `automations.automation.enabled`
- `automations.automation.disabled`
- `automations.automation.frozen`

---

### events-service

**Ответственность:** хранение всех доменных событий, API для чтения event feed, WebSocket для real-time уведомлений (счётчик входящих приглашений).

**БД:** PostgreSQL, таблица `events` партиционирована по `created_at` (нативный `PARTITION BY RANGE`, по месяцам).

**Kafka topics (consume):** все топики всех сервисов — записывает в `events`.

**WebSocket:** клиент подписывается на обновления; при появлении нового события `invitation.*` для пользователя — пуш счётчика.

---

### billing-service

**Ответственность:** тарифы, подписки, лимиты, заморозка сущностей, банк дней, Enterprise-слоты, оплата (ЮKassa).

**БД:** PostgreSQL.

Ключевые таблицы: `subscriptions`, `subscription_bank_days`, `subscription_history`, `payment_transactions`, `usage_counters`.

`usage_counters` — счётчики per-user per-entity-type (tasks, projects, teams, automations, members). Обновляются по Kafka-событиям от workspace/automations.

**Kafka topics (consume):**
- `workspace.*` — обновление счётчиков
- `automations.*` — обновление счётчиков автоматизаций

**Kafka topics (publish):**
- `billing.entity.frozen`
- `billing.entity.unfrozen`
- `billing.tariff.changed`

**gRPC (internal):**
- `CheckLimit(user_id, entity_type) → allowed bool` — вызывается workspace-service перед созданием сущности

---

## Коммуникация

### Kafka (async)

Используется transactional outbox pattern: сервис пишет событие в таблицу `<service>_outbox` в той же транзакции что и изменение данных. Отдельный outbox worker читает таблицу и публикует в Kafka.

Гарантия: at-least-once delivery. Консьюмеры идемпотентны.

### gRPC (sync)

Используется только для операций, требующих немедленного ответа (валидация токена, проверка лимита). Таймаут: 5 секунд. Retry только для идемпотентных операций. mTLS между сервисами.

## API Gateway (Nginx)

- Маршрутизация по префиксу пути к соответствующему сервису
- Валидация токена (access token или PAT) через `auth_request` → identity-service
- Rate limiting per IP и per token
- TLS termination, сертификаты через cert-manager (Let's Encrypt)

## Безопасность

- **Внешняя аутентификация:** OAuth 2.0 Authorization Code Flow с PKCE. Два типа Bearer-токенов в заголовке `Authorization`: access token (выдаётся через OAuth 2.0 flow) и PAT (для скриптов и CI/CD). Gateway валидирует оба типа через identity-service.
- **Клиент авторизации:** отдельное легковесное веб-приложение, единая точка входа для регистрации, логина и подтверждения email. Все клиенты (веб-приложение, CLI) аутентифицируются через redirect на клиент авторизации.
- **Внутренняя аутентификация:** mTLS между сервисами
- `request_id` propagates через все HTTP, gRPC и Kafka вызовы для сквозной трассировки

## База данных

### Стратегия выбора

| Сервис | БД | Причина |
|--------|----|---------|
| identity | PostgreSQL | Небольшой объём, сложные транзакции auth |
| workspace | PostgreSQL | Индексы по owner, партиционирование при необходимости |
| automations | PostgreSQL | Индексы по project_id |
| events | PostgreSQL | Партиционирование по времени (PARTITION BY RANGE), append-only |
| billing | PostgreSQL | Финансовые транзакции, строгая консистентность |

### Конвенции

- Имена БД: `<service>_db`
- Имена пользователей: `<service>_user`
- Миграции: Goose, embedded в бинарь сервиса, применяются при старте
- Все миграции backward-compatible (новые колонки с DEFAULT, без DROP до следующего релиза)

## Инфраструктура

**Кластер:** K3s bare-metal, single node (91.218.114.168).

**Компоненты:**
- Nginx Ingress Controller + cert-manager
- Kafka (Strimzi Operator)
- PostgreSQL (CloudNativePG Operator)
- MinIO (S3-совместимое хранилище)
- Prometheus + Grafana + Loki + Promtail
- Sentry (self-hosted)

## Observability

- **Метрики:** Prometheus, каждый сервис экспортирует `/metrics`. Grafana дашборды per-service.
- **Логи:** структурированные JSON-логи (zap), собираются Promtail → Loki → Grafana.
- **Ошибки:** Sentry SDK во всех сервисах, алерты на новые ошибки.
- **Трассировка:** `request_id` в каждом запросе, логируется на входе и выходе каждого сервиса.

## CI/CD

GitHub Actions + GitHub Container Registry (ghcr.io/gaev-tech) + Helm.

**Пайплайн:**
1. `lint` — golangci-lint, staticcheck
2. `test` — `go test ./...` с real PostgreSQL в Docker
3. `build` — `docker build`, push образа в GHCR с тегом по SHA коммита
4. `deploy` — `helm upgrade --install` в K3s кластер

Триггеры path-based: изменения в `backend/services/identity-service/**` запускают только пайплайн identity-service.

Базовый CI-образ с предустановленными зависимостями хранится в GHCR и обновляется при изменении `Dockerfile.ci`.
