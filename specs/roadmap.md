# Roadmap

Задачи сгруппированы по направлениям. Зависимости указаны явно. MVP/PostMVP — метки из product-spec.

---

## Инфраструктура

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| INFRA-1 | CI/CD: GitHub Actions пайплайн (lint, test, build, deploy), CI base image в GHCR | — | — | mvp |
| INFRA-2 | K3s кластер: установка, kubeconfig, namespace структура | — | INFRA-3..11 | mvp |
| INFRA-3 | Nginx Ingress Controller + cert-manager (Let's Encrypt) | INFRA-2 | API-41, DOCS-1 | mvp |
| INFRA-4 | Kafka (Strimzi Operator) | INFRA-2 | — | mvp |
| INFRA-5 | PostgreSQL (CloudNativePG Operator) | INFRA-2 | API-8, API-13 | mvp |
| ~~INFRA-6~~ | ~~Citus (CloudNativePG Operator)~~ — убрано, все сервисы используют plain PostgreSQL (INFRA-5) | — | — | — |
| INFRA-7 | MinIO | INFRA-2 | — | postmvp |
| INFRA-8 | Prometheus + Grafana (дашборды per-service) | INFRA-2 | — | mvp |
| INFRA-9 | Loki + Promtail | INFRA-2 | — | mvp |
| INFRA-10 | Sentry (self-hosted) | INFRA-2 | — | mvp |
| INFRA-11 | Helm charts: структура монорепо, base chart, per-service чарты | INFRA-2 | DOCS-1 | mvp |

---

## API

### Общая основа (MVP)

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-1 | Монорепо: go.work, структура директорий, Makefile | — | API-2..7, API-8, API-13, API-22, API-37, API-45 | mvp |
| API-2 | pkg/logging (zap, structured JSON, request_id) | API-1 | API-8, API-13, API-22, API-45 | mvp |
| API-3 | pkg/metrics (Prometheus, стандартные HTTP-метрики) | API-1 | — | mvp |
| API-4 | pkg/grpc (клиент + сервер, mTLS, таймаут 5s, retry) | API-1 | API-18, API-35, API-45 | mvp |
| API-5 | pkg/kafka + pkg/outbox (producer, consumer, transactional outbox worker) | API-1 | API-8, API-12, API-19, API-20, API-33, API-34, API-36, API-38, API-45, API-46, API-48, API-50, API-54 | mvp |
| API-6 | pkg/rsql (парсер RSQL → SQL, поддержка `me`, массивов, `null`, дат) | API-1 | API-22, API-45, API-47, API-53 | mvp |
| API-7 | contracts/proto: .proto файлы всех gRPC-интерфейсов, codegen (buf) | API-1 | — | mvp |

### identity-service (MVP)

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-8 | Регистрация, подтверждение email (SMTP через identity-service: `SMTP_HOST/PORT/FROM/PASSWORD`), логин, логаут, refresh token | API-1, API-2, API-5, INFRA-5 | API-9, API-10, API-11, API-12, API-49 | mvp |
| API-9 | PAT: создание, список, получение по ID, обновление, отзыв | API-8 | API-42 | mvp |
| API-10 | Профиль: получение, обновление (name, theme, language), смена пароля, удаление аккаунта | API-8 | — | mvp |
| API-11 | Поиск пользователей по email (префикс) | API-8 | — | mvp |
| API-12 | Kafka publish: user.registered, user.email_verified, user.deleted, pat.created, pat.revoked | API-5, API-8 | API-33 | mvp |

### billing-service (MVP)

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-13 | Тарифы: модель данных, подписки, usage_counters | API-1, API-2, INFRA-5 | API-14..21, API-51, API-54 | mvp |
| API-14 | API тарифа: получение статуса + лимитов, список тарифов, история | API-13 | — | mvp |
| API-15 | Апгрейд / даунгрейд тарифа, отмена даунгрейда, банк дней | API-13 | — | mvp |
| API-16 | Enterprise-слоты: покупка, изменение, отмена | API-13 | — | mvp |
| API-17 | Заморозка сущностей (по created_at desc), API списка замороженных | API-13 | — | mvp |
| API-18 | gRPC: CheckLimit(user_id, entity_type) → allowed | API-4, API-13 | — | mvp |
| API-19 | Kafka consume: workspace.* → обновление usage_counters | API-5, API-13 | — | mvp |
| API-20 | Kafka publish: billing.entity.frozen, billing.entity.unfrozen, billing.tariff.changed | API-5, API-13 | API-36 | mvp |
| API-21 | Интеграция ЮKassa: платёжные транзакции | API-13 | — | mvp |

### workspace-service (MVP)

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-22 | Задачи: CRUD, PATCH (все поля включая projects), список (RSQL + пагинация, created_at asc) | API-1, API-2, API-6, INFRA-5 | API-23, API-24, API-25, API-27, API-32, API-34, API-35, API-52 | mvp |
| API-23 | Задачи: GET /projects/{id}/tasks | API-22 | — | mvp |
| API-24 | Прямые доступы к задачам: выдача, обновление, отзыв, список (subject_type: user/team) | API-22 | API-31 | mvp |
| API-25 | Проекты: CRUD, GET /projects + GET /projects/{id} | API-22 | API-26, API-29, API-30 | mvp |
| API-26 | Участники проекта: добавление, обновление прав, удаление | API-25 | API-31 | mvp |
| API-27 | Команды: CRUD | API-22 | API-28, API-29, API-30 | mvp |
| API-28 | Участники команды: добавление, обновление роли (admin/member), удаление | API-27 | — | mvp |
| API-29 | Приглашения: отправка в проект/команду, входящие, исходящие, принять/отклонить | API-25, API-27 | — | mvp |
| API-30 | Передача владения: инициирование, принятие, отмена (проект и команда) | API-25, API-27 | — | mvp |
| API-31 | Модель прав: вычисление итоговых прав (union из всех источников), проверка R-7 при выдаче | API-24, API-26 | — | mvp |
| API-32 | Правила жизни сущностей: автоудаление задач/проектов/команд | API-22 | — | mvp |
| API-33 | users_cache: денормализация, Kafka consume identity.user.* | API-5, API-12 | — | mvp |
| API-34 | Kafka publish: workspace.task.*, workspace.project.*, workspace.team.* | API-5, API-22 | — | mvp |
| API-35 | gRPC: GetTaskRights, GetProjectMembers | API-4, API-22 | — | mvp |
| API-36 | gRPC consume billing: заморозка сущностей по событиям billing.entity.* | API-5, API-20 | — | mvp |

### events-service (MVP)

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-37 | Таблица events (PostgreSQL, партиционирование по created_at по месяцам) | API-1, INFRA-5 | API-38, API-39 | mvp |
| API-38 | Kafka consume: все топики всех сервисов → запись в events | API-5, API-37 | — | mvp |
| API-39 | API событий: GET /events, GET /projects/{id}/events, GET /tasks/{id}/events (фильтры: тип, время, сущность) | API-37 | API-40 | mvp |
| API-40 | WebSocket: real-time пуш счётчика входящих приглашений | API-37, API-39 | — | mvp |

### API Gateway (MVP)

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-41 | Nginx: маршрутизация по префиксу к сервисам | INFRA-3 | API-42, API-43, API-44 | mvp |
| API-42 | auth_request → identity-service: валидация Bearer PAT на каждый запрос | API-9, API-41 | — | mvp |
| API-43 | Rate limiting per IP и per token | API-41 | — | mvp |
| API-44 | TLS termination, request_id в заголовках | API-41 | — | mvp |

### PostMVP

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| API-45 | automations-service: CRUD автоматизаций, секреты проектов (шифрование) | API-1, API-2, API-5, API-6, INFRA-5 | API-46, API-47, API-48 | postmvp |
| API-46 | automations-service: tasks_cache, Kafka consume workspace.task.* | API-5, API-45 | — | postmvp |
| API-47 | automations-service: выполнение HTTP-вызовов по триггерам, RSQL-условия | API-6, API-45 | — | postmvp |
| API-48 | automations-service: Kafka publish automation.* | API-5, API-45 | API-54 | postmvp |
| API-49 | identity-service: managed-пользователи (CRUD, деактивация, сброс пароля) | API-8 | API-50, API-51 | postmvp |
| API-50 | identity-service: Kafka publish user.managed_* | API-5, API-49 | — | postmvp |
| API-51 | billing-service: лимиты managed-пользователей по тарифам | API-13, API-49 | — | postmvp |
| API-52 | workspace-service: импорт задач из CSV (R-14, валидация, all-or-nothing, лимит 10k/10MB) | API-22 | — | postmvp |
| API-53 | workspace-service: массовые операции (bulk/batch по RSQL и по списку ID) | API-22, API-6 | — | postmvp |
| API-54 | billing-service: Kafka consume automations.* → обновление usage_counters автоматизаций | API-5, API-13, API-48 | — | postmvp |

---

## Документация

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| DOCS-1 | Angular app `docs`: структура, роутинг, деплой (Nginx + статика); OpenAPI codegen pipeline (генерация `openapi.yaml` из кода сервисов при сборке) | API-1..54, INFRA-3, INFRA-11 | DOCS-2, UI-1 | postmvp |
| DOCS-2 | Страницы: обзор системы, API Reference (из `openapi.yaml`), каталог событий, справочник RSQL с примерами, CLI-шаблоны для типовых операций | DOCS-1 | — | postmvp |

---

## CLI

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| CLI-1 | Скаффолд: go mod, Cobra setup, структура директорий; конфиг и профили (`~/.tracker/config.yaml`, команды `profile list/use/add/remove`), PAT приоритет (флаг → env → конфиг) | — | CLI-2 | postmvp |
| CLI-2 | Команды: вывод и пагинация (`--output table/json/plain`, `--limit/--cursor/--all`); `task`, `project`, `team`, `profile`, `pat`, `password`, `account`, `tariff`, `frozen`, `enterprise-slots`, `event` | CLI-1, API-8..44 | CLI-3 | postmvp |
| CLI-3 | Дистрибуция: GitHub Releases (Linux/macOS/Windows amd64/arm64), Homebrew tap, `curl \| sh` скрипт | CLI-2 | — | postmvp |

---

## UI

| ID | Задача | Зависит от | Блокирует | Milestone |
|----|--------|-----------|-----------|-----------|
| UI-1 | Скаффолд Angular Workspace: структура монорепо (`projects/app`, `projects/docs`), libs, CI/CD (path-based триггеры, ng build, Nginx образ, Helm); API-клиент: codegen из `openapi.yaml`, Zod runtime validation, Sentry-алерт при рассинхронизации | DOCS-1, API-8..44 | UI-2 | postmvp |
| UI-2 | Приложение: дизайн-система (трёхуровневые токены, темы light/dark), аутентификация (JWT + refresh, soft-refresh, multi-auth), сайдбар, роутинг, breadcrumbs, WebSocket счётчик приглашений; все страницы — задачи, проекты, команды, профиль, тариф, события, приглашения | UI-1 | — | postmvp |
