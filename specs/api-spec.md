# API-спецификация

Markdown-каталог API-эндпоинтов и моделей данных. Документ описывает все публичные endpoint'ы продукта, группируя их по ресурсам. Для каждого endpoint'а указаны метод, путь, назначение, параметры, тело запроса и ответа, возможные ошибки.

## Общие соглашения

**Базовый URL:** `https://api.<domain>/v1`.

**Формат данных:** JSON (`Content-Type: application/json`) для всех тел запросов и ответов, кроме импорта CSV (`multipart/form-data`).

**Аутентификация:** Bearer-токен в заголовке `Authorization`. В качестве токена используется PAT.

```
Authorization: Bearer pat_a1b2c3d4e5f6...
```

Исключения: endpoint'ы `/auth/register`, `/auth/login`, `/auth/password-reset` — без аутентификации.

**Идентификаторы:** UUID v4 в виде строки `550e8400-e29b-41d4-a716-446655440000`.

**Даты и время:** ISO 8601 с таймзоной (`2025-04-21T10:00:00Z`).

**Пагинация:** курсорная. Ответы, возвращающие списки, содержат:
```json
{
  "items": [ ... ],
  "next_cursor": "opaque-cursor-string-or-null",
  "total": 1234
}
```
Запросы принимают `cursor` и `limit` (макс. 100, default 50) как query-параметры.

**Фильтрация списков:** через query-параметр `filter=<RSQL>` там, где применимо.

**Ошибки:** стандартный формат ответа:
```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable description",
    "details": { ... }
  }
}
```

Основные коды ошибок:
- `400 bad_request` — некорректный синтаксис запроса.
- `400 validation_error` — данные не прошли валидацию.
- `401 unauthorized` — отсутствует или недействителен токен.
- `403 forbidden` — у пользователя нет нужных прав.
- `404 not_found` — ресурс не существует или недоступен.
- `409 conflict` — конфликт состояния (например, дубликат pending-приглашения).
- `422 tariff_limit_exceeded` — превышен лимит тарифа.
- `429 rate_limit_exceeded` — превышение rate limit.
- `500 internal_error` — внутренняя ошибка.

---

# Модели данных

## User

```json
{
  "id": "uuid",
  "email": "string",
  "theme": "light | dark",
  "language": "string (ISO 639-1)",
  "parent_user_id": "uuid | null",
  "is_active": true,
  "email_verified_at": "ISO 8601 | null",
  "created_at": "ISO 8601"
}
```

- `parent_user_id`: `null` для обычных пользователей; `uuid` для managed-пользователей (ссылка на родителя).
- `is_active`: `false` — пользователь деактивирован, логин запрещён.
- `email_verified_at`: `null` — email не подтверждён, логин запрещён.

## ManagedUser

Возвращается в эндпоинтах управления managed-пользователями. Расширяет `User` статусом.

```json
{
  "id": "uuid",
  "email": "string",
  "parent_user_id": "uuid",
  "status": "pending_email_verification | active | deactivated",
  "is_active": true,
  "email_verified_at": "ISO 8601 | null",
  "created_at": "ISO 8601",
  "deactivated_at": "ISO 8601 | null"
}
```

Значения `status`:
- `pending_email_verification` — email ещё не подтверждён.
- `active` — email подтверждён, `is_active = true`.
- `deactivated` — `is_active = false`.

## PAT

```json
{
  "id": "uuid",
  "name": "string",
  "token": "string",
  "expires_at": "ISO 8601 | null",
  "created_at": "ISO 8601",
  "revoked_at": "ISO 8601 | null"
}
```

## Team

```json
{
  "id": "uuid",
  "name": "string",
  "owner_id": "uuid",
  "is_blocked_by_tariff": false,
  "created_at": "ISO 8601"
}
```

## TeamMember

```json
{
  "user_id": "uuid",
  "email": "string",
  "is_admin": true,
  "is_blocked_by_tariff": false,
  "joined_at": "ISO 8601"
}
```

## Project

```json
{
  "id": "uuid",
  "name": "string",
  "owner_id": "uuid",
  "is_blocked_by_tariff": false,
  "created_at": "ISO 8601"
}
```

## ProjectPermissions

Набор из 14 булевых флагов.

```json
{
  "r1_edit_title": false,
  "r2_edit_description": false,
  "r3_edit_tags": false,
  "r4_edit_blockers": false,
  "r5_edit_assignee": false,
  "r6_edit_status": false,
  "r7_share": false,
  "r8_delete": false,
  "r9_rename_project": false,
  "r10_manage_members": false,
  "r11_manage_automations": false,
  "r12_manage_attachments": false,
  "r13_delete_project": false,
  "r14_import": false
}
```

## TaskPermissions

Подмножество ProjectPermissions для прямых доступов на задачу — только R-1…R-8:

```json
{
  "r1_edit_title": false,
  "r2_edit_description": false,
  "r3_edit_tags": false,
  "r4_edit_blockers": false,
  "r5_edit_assignee": false,
  "r6_edit_status": false,
  "r7_share": false,
  "r8_delete": false
}
```

## ProjectMember (пользователь-участник)

```json
{
  "user_id": "uuid",
  "email": "string",
  "permissions": { /* ProjectPermissions */ },
  "is_blocked_by_tariff": false,
  "joined_at": "ISO 8601"
}
```

## ProjectTeamMember (команда-участник)

```json
{
  "team_id": "uuid",
  "team_name": "string",
  "permissions": { /* ProjectPermissions */ },
  "is_frozen_in_project": false,
  "joined_at": "ISO 8601"
}
```

## Task

```json
{
  "id": "uuid",
  "title": "string",
  "description": "string (markdown)",
  "status": "opened | progress | closed",
  "author_id": "uuid",
  "assignee_id": "uuid | null",
  "tags": ["string"],
  "project_ids": ["uuid"],
  "blocking_task_ids": ["uuid"],
  "blocked_task_ids": ["uuid"],
  "is_blocked_by_tariff": false,
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

## TaskDirectAccess

```json
{
  "id": "uuid",
  "task_id": "uuid",
  "grantee_user_id": "uuid | null",
  "grantee_team_id": "uuid | null",
  "granted_by": "uuid",
  "permissions": { /* TaskPermissions */ },
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

## Automation

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "name": "string",
  "trigger_event_type": "string (из каталога событий)",
  "condition_rsql": "string | null",
  "action": {
    "method": "GET | POST | PUT | PATCH | DELETE",
    "url": "string",
    "headers": { "Header-Name": "value" },
    "body": "string | null"
  },
  "is_enabled": true,
  "consecutive_failures": 0,
  "is_blocked_by_tariff": false,
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

## AutomationRun

```json
{
  "id": "uuid",
  "automation_id": "uuid",
  "event_id": "uuid",
  "attempt_number": 1,
  "status": "success | failed | retrying | timeout",
  "response_code": 200,
  "response_body_excerpt": "string | null",
  "error_message": "string | null",
  "started_at": "ISO 8601",
  "finished_at": "ISO 8601 | null"
}
```

## Event

```json
{
  "id": "uuid",
  "type": "string (из каталога событий)",
  "actor_id": "uuid | null",
  "task_id": "uuid | null",
  "project_id": "uuid | null",
  "team_id": "uuid | null",
  "automation_id": "uuid | null",
  "target_user_id": "uuid | null",
  "payload": { /* произвольный JSON */ },
  "created_at": "ISO 8601"
}
```

## Subscription

```json
{
  "user_id": "uuid",
  "plan": "free | pro | team | enterprise",
  "period": "monthly | yearly | null",
  "current_period_start": "ISO 8601 | null",
  "current_period_end": "ISO 8601 | null",
  "planned_downgrade": {
    "plan": "free | pro | team",
    "effective_at": "ISO 8601"
  },
  "enterprise_slots": 0,
  "enterprise_slots_pending_decrease": {
    "new_value": 50,
    "effective_at": "ISO 8601"
  },
  "bank_layers": [
    {
      "id": "uuid",
      "plan": "pro",
      "period": "monthly",
      "days_remaining": 7,
      "layer_order": 2
    }
  ]
}
```

## Invitation

Базовая модель для приглашений в команду/проект и передачи владения. Конкретные модели расширяют базовую.

```json
{
  "id": "uuid",
  "status": "pending | accepted | declined | revoked",
  "created_at": "ISO 8601",
  "resolved_at": "ISO 8601 | null",
  "invited_by": "uuid"
}
```

## Error

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": { /* опционально */ }
  }
}
```

---

# Endpoint'ы

## 1. Аутентификация и регистрация

### POST /auth/register

Создать аккаунт.

**Без аутентификации.**

Тело запроса:
```json
{
  "email": "string",
  "password": "string"
}
```

Ответ `201`:
```json
{
  "user": { /* User */ },
  "pat": { /* PAT */ }
}
```
При регистрации создаётся дефолтный PAT для первичного доступа.

Ошибки: `validation_error` (некорректный email, слабый пароль), `409 conflict` (email уже занят).

### POST /auth/login

Вход. Возвращает PAT для последующих вызовов.

**Без аутентификации.**

Тело запроса:
```json
{
  "email": "string",
  "password": "string"
}
```

Ответ `200`:
```json
{
  "pat": { /* PAT */ }
}
```

### POST /auth/logout

Отзыв текущего PAT, использованного для вызова.

Ответ `204`.

### POST /auth/password-reset/request

Инициировать сброс пароля.

**Без аутентификации.**

Тело запроса:
```json
{ "email": "string" }
```

Ответ `204` (всегда, вне зависимости от существования email).

### POST /auth/password-reset/confirm

Установить новый пароль по токену из email.

**Без аутентификации.**

Тело запроса:
```json
{
  "reset_token": "string",
  "new_password": "string"
}
```

Ответ `204`.

### POST /auth/email-verify

Подтвердить email по токену из письма, отправленного при создании managed-пользователя.

**Без аутентификации.**

Тело запроса:
```json
{ "verification_token": "string" }
```

Ответ `200`:
```json
{ "user_id": "uuid", "email": "string" }
```

Ошибки: `404 not_found` — токен недействителен или истёк.

### POST /auth/password/change

Смена пароля авторизованным пользователем.

Тело запроса:
```json
{
  "current_password": "string",
  "new_password": "string"
}
```

Ответ `204`.

---

## 2. Пользователи

### GET /users/me

Получить свой профиль.

Ответ `200`: `User`.

### PATCH /users/me

Изменить настройки профиля (тема, язык).

Тело:
```json
{
  "theme": "dark",
  "language": "ru"
}
```

Ответ `200`: `User`.

### GET /users/search

Поиск пользователей для добавления в команду / доступ / проект / assignee.

Query-параметры:
- `q` — строка поиска (по email). Мин. 2 символа.
- `limit` — default 20, max 50.

Ответ `200`:
```json
{
  "items": [ { "id": "...", "email": "..." } ]
}
```

### DELETE /users/me

Удалить свой аккаунт. Действие необратимое.

Вызывается пользователем любого типа — обычным или managed. Для managed альтернативой является удаление родителем через `/managed-users/{id}`.

Тело запроса:
```json
{ "confirmation_email": "string" }
```

Сервис проверяет, что `confirmation_email` совпадает с email вызывающего пользователя — иначе возвращает `validation_error`.

Ответ `204`.

Эффекты (см. раздел 3.10 основного документа):
- Каскадно удаляются: проекты и команды, где пользователь — владелец (вместе с их содержимым); managed-пользователи, где пользователь — родитель (рекурсивно); PAT; членства в чужих проектах и командах; прямые доступы, где пользователь — получатель; pending-приглашения с участием пользователя.
- В полях `author_id`, `assignee_id`, `granted_by`, `actor_id`, `target_user_id` ссылка становится `null`.

---

## 3. Managed-пользователи

Функции родителя по управлению своими managed-пользователями. Все endpoint'ы доступны только обычному пользователю (не managed) и работают с managed, у которых `parent_user_id` = вызывающий пользователь. Попытка обратиться к чужому managed → `404 not_found`.

### POST /managed-users

Создать managed-пользователя. На указанный email отправляется письмо с ссылкой подтверждения.

Тело:
```json
{
  "email": "string",
  "password": "string"
}
```

Ответ `201`: `ManagedUser` (`status = "pending_email_verification"`, `is_active = true`, `email_verified_at = null`).

Ошибки:
- `409 conflict` — email уже занят (глобальная уникальность).
- `tariff_limit_exceeded` — превышен лимит managed-пользователей у родителя по тарифу.
- `forbidden` — вызывающий является managed-пользователем (managed не могут создавать собственных managed).

### GET /managed-users

Список своих managed-пользователей.

Query: `status` (опц., фильтр), `cursor`, `limit`.

Ответ `200`:
```json
{ "items": [ /* ManagedUser */ ], "next_cursor": "...", "total": N }
```

### GET /managed-users/{id}

Получить managed-пользователя по ID.

Ответ `200`: `ManagedUser`.

### POST /managed-users/{id}/resend-verification

Переотправить письмо с подтверждением email (только для managed в статусе `pending_email_verification`).

Ответ `204`.

### POST /managed-users/{id}/deactivate

Деактивировать managed-пользователя.

Ответ `200`: `ManagedUser` (с `status = "deactivated"`, `is_active = false`).

Побочные эффекты:
- Все PAT managed отзываются.
- Все автоматизации, созданные managed, выключаются (`is_enabled = false`).
- Все pending-приглашения, связанные с managed (исходящие и входящие), отклоняются.
- Членство в проектах и командах сохраняется с пометкой «деактивирован».

### POST /managed-users/{id}/reactivate

Ре-активировать managed-пользователя.

Ответ `200`: `ManagedUser` (с `status = "active"`, `is_active = true`).

Автоматизации, выключенные при деактивации, не включаются автоматически.

### POST /managed-users/{id}/reset-password

Установить managed-пользователю новый пароль.

Тело:
```json
{ "new_password": "string" }
```

Ответ `204`.

### DELETE /managed-users/{id}

Удалить managed-пользователя окончательно. Действие необратимое, применяются те же эффекты, что при `DELETE /users/me`.

Ответ `204`.

---

## 4. Приватные ключи (PAT)

### GET /pats

Список своих PAT (со значениями токенов).

Ответ `200`:
```json
{ "items": [ /* PAT */ ] }
```

### POST /pats

Создать PAT.

Тело:
```json
{
  "name": "CI script",
  "expires_at": "2026-04-21T00:00:00Z"
}
```
`expires_at` опционально.

Ответ `201`: `PAT`.

### DELETE /pats/{id}

Отозвать PAT.

Ответ `204`.

---

## 5. Задачи

### GET /tasks

Получить список задач, доступных пользователю.

Query-параметры:
- `filter` — RSQL-выражение (опц.).
- `cursor`, `limit` — пагинация.
- `sort` — `created_at` / `updated_at` / `title` + `:asc` / `:desc`.

Ответ `200`:
```json
{
  "items": [ /* Task */ ],
  "next_cursor": "...",
  "total": 1234
}
```

### POST /tasks

Создать задачу.

Тело:
```json
{
  "title": "string (обязательно)",
  "description": "string (markdown, опц.)",
  "status": "opened | progress | closed (опц., default opened)",
  "assignee_id": "uuid | null (опц.)",
  "tags": ["string"],
  "project_ids": ["uuid"],
  "blocking_task_ids": ["uuid"]
}
```

Ответ `201`: `Task`.

Ошибки: `tariff_limit_exceeded` (лимит задач автора), `forbidden` (у автора нет R-12 хотя бы в одном из указанных проектов).

### GET /tasks/{id}

Получить задачу по ID.

Ответ `200`: `Task`.

### PATCH /tasks/{id}

Изменить задачу. Возможно изменение одного поля или нескольких за один запрос. Каждое редактируемое поле требует соответствующего права:

| Поле | Требуемое право |
|---|---|
| `title` | R-1 |
| `description` | R-2 |
| `tags` | R-3 |
| `blocking_task_ids` | R-4 |
| `assignee_id` | R-5 |
| `status` | R-6 |

Тело (все поля опциональны, передаются только изменяемые):
```json
{
  "title": "string",
  "description": "string",
  "status": "opened",
  "assignee_id": "uuid | null",
  "tags": ["string"],
  "blocking_task_ids": ["uuid"]
}
```

Ответ `200`: обновлённая `Task`.

Ошибки: `forbidden` (нет нужного права на одно из изменяемых полей) — операция атомарна, при недостатке прав ни одно из полей не изменяется.

### POST /tasks/{id}/projects

Прикрепить задачу к проекту.

Требуется R-12 в целевом проекте.

Тело:
```json
{ "project_id": "uuid" }
```

Ответ `204`.

### DELETE /tasks/{id}/projects/{project_id}

Открепить задачу от проекта.

Требуется R-12 в проекте.

Ответ `204`.

**Особенность.** Если это последний проект у задачи и у задачи нет прямых доступов с R-8 — задача автоматически удаляется без дополнительных подтверждений (см. основной документ, раздел 3.2).

### DELETE /tasks/{id}

Удалить задачу.

Требуется R-8.

Ответ `204`.

---

## 6. Прямые доступы на задачу

### GET /tasks/{id}/accesses

Получить список прямых доступов задачи.

Требуется R-7.

Ответ `200`:
```json
{ "items": [ /* TaskDirectAccess */ ] }
```

### POST /tasks/{id}/accesses

Выдать прямой доступ пользователю или команде.

Требуется R-7. Устанавливаемые права не могут превышать права текущего пользователя — эндпоинт проверяет это и возвращает ошибку при нарушении.

Тело (ровно одно из `grantee_user_id` / `grantee_team_id`):
```json
{
  "grantee_user_id": "uuid",
  "permissions": { /* TaskPermissions */ }
}
```

Ответ `201`: `TaskDirectAccess`.

Ошибки: `forbidden` (R-7 отсутствует или попытка выдать больше, чем есть), `409 conflict` (доступ этому получателю уже выдан).

### PATCH /tasks/{id}/accesses/{access_id}

Изменить состав прав у прямого доступа.

Требуется R-7 и правило «не больше, чем у себя».

Тело:
```json
{ "permissions": { /* TaskPermissions */ } }
```

Ответ `200`: `TaskDirectAccess`.

### DELETE /tasks/{id}/accesses/{access_id}

Отозвать прямой доступ.

Требуется R-7.

Ответ `204`.

**Особенность.** Если отзыв доступа приводит к исчезновению всех прямых доступов с R-8 у задачи, которая не прикреплена ни к одному проекту — задача удаляется.

---

## 7. Массовые операции над задачами

Обе точки транзакционны: при ошибке на любой задаче — вся операция откатывается. Лимит — 1000 задач на запрос. Общая форма тела запроса одинакова, различаются только способы выбора задач.

### POST /tasks/bulk/by-filter

Массовая операция по RSQL-фильтру.

Тело:
```json
{
  "filter": "status==opened;tags==urgent",
  "operation": {
    "type": "change_status",
    "status": "progress"
  }
}
```

### POST /tasks/bulk/by-ids

Массовая операция по списку ID.

Тело:
```json
{
  "task_ids": ["uuid", "uuid", "..."],
  "operation": {
    "type": "change_status",
    "status": "progress"
  }
}
```

### Поддерживаемые типы операций

Передаются в поле `operation.type`:

| `type` | Параметры | Требуемые права на каждой задаче |
|---|---|---|
| `change_status` | `"status": "opened\|progress\|closed"` | R-6 |
| `set_assignee` | `"assignee_id": "uuid\|null"` | R-5 |
| `add_tags` | `"tags": ["..."]` | R-3 |
| `remove_tags` | `"tags": ["..."]` | R-3 |
| `add_blockers` | `"blocking_task_ids": ["uuid", ...]` | R-4 |
| `remove_blockers` | `"blocking_task_ids": ["uuid", ...]` | R-4 |
| `attach_to_project` | `"project_id": "uuid"` | R-12 в целевом проекте |
| `detach_from_project` | `"project_id": "uuid"` | R-12 в проекте |
| `grant_access` | `"grantee_user_id" \| "grantee_team_id"`, `"permissions": { ... }` | R-7, правило «не больше, чем у себя» |
| `revoke_access` | `"grantee_user_id" \| "grantee_team_id"` | R-7 |
| `delete` | — | R-8 |

**Ответ при успехе `200`:**
```json
{
  "affected_count": 42
}
```

**Ответ при ошибке `400 / 403 / 422`:**
```json
{
  "error": {
    "code": "bulk_failed",
    "message": "Operation aborted: some tasks failed validation.",
    "details": {
      "failures": [
        { "task_id": "uuid", "reason": "forbidden", "message": "No R-6 on this task" },
        { "task_id": "uuid", "reason": "tariff_limit_exceeded", "message": "..." }
      ]
    }
  }
}
```

При ошибке ни одно изменение не применяется.

---

## 8. Проекты

### GET /projects

Список проектов пользователя.

Query-параметры:
- `q` — поиск по названию.
- `only_owned` — `true`/`false`.
- `cursor`, `limit`.

Ответ `200`: `{ "items": [ /* Project */ ], "next_cursor": "...", "total": N }`.

### POST /projects

Создать проект. Создатель становится владельцем с полным набором прав.

Тело:
```json
{ "name": "string" }
```

Ответ `201`: `Project`.

Ошибки: `tariff_limit_exceeded` (лимит проектов владельца).

### GET /projects/{id}

Получить проект.

Ответ `200`:
```json
{
  "project": { /* Project */ },
  "my_permissions": { /* ProjectPermissions */ }
}
```

### PATCH /projects/{id}

Переименовать проект. Требуется R-9.

Тело: `{ "name": "string" }`.

Ответ `200`: `Project`.

### DELETE /projects/{id}

Удалить проект. Требуется R-13.

Ответ `204`.

### POST /projects/{id}/import

Импорт задач из CSV. Требуется R-14.

Тело: `multipart/form-data`, поле `file` — CSV-файл.

Ограничения: макс. 10 000 строк / 10 МБ.

Ответ `200` (успех):
```json
{
  "imported_count": 142
}
```

Ответ `400 validation_error` (ошибки формата или тарифа):
```json
{
  "error": {
    "code": "csv_import_failed",
    "message": "Import aborted due to validation errors.",
    "details": {
      "row_errors": [
        { "row": 3, "column": "status", "message": "Unknown status value 'done'" },
        { "row": 7, "column": "assignee", "message": "User not found: foo@bar.com" }
      ]
    }
  }
}
```

---

## 9. Участники проекта (пользователи)

### GET /projects/{id}/members

Список участников-пользователей.

Требуется как минимум одно право в проекте, т.е. пользователь видит участников проекта, если он сам в нём состоит.

Ответ `200`: `{ "items": [ /* ProjectMember */ ] }`.

### PATCH /projects/{id}/members/{user_id}

Изменить набор прав участника. Требуется R-10.

Тело: `{ "permissions": { /* ProjectPermissions */ } }`.

Ответ `200`: `ProjectMember`.

### DELETE /projects/{id}/members/{user_id}

Удалить участника из проекта. Требуется R-10. Нельзя удалить владельца.

Ответ `204`.

---

## 10. Участники проекта (команды)

### GET /projects/{id}/team-members

Список команд-участников.

Ответ `200`: `{ "items": [ /* ProjectTeamMember */ ] }`.

### PATCH /projects/{id}/team-members/{team_id}

Изменить набор прав команды в проекте. Требуется R-10.

Тело: `{ "permissions": { /* ProjectPermissions */ } }`.

Ответ `200`: `ProjectTeamMember`.

### DELETE /projects/{id}/team-members/{team_id}

Удалить команду из проекта. Требуется R-10.

Ответ `204`.

---

## 11. Приглашения в проект

### POST /projects/{id}/invitations

Пригласить пользователя или команду в проект. Требуется R-10.

Тело (ровно одно из `invitee_user_id` / `invitee_team_id`):
```json
{
  "invitee_user_id": "uuid",
  "permissions": { /* ProjectPermissions */ }
}
```

Ответ `201`:
```json
{
  "id": "uuid",
  "status": "pending",
  "is_active": true,
  "created_at": "ISO 8601"
}
```

Если приглашение команды создано в условиях, когда её принятие сейчас превысит лимит участников проекта по тарифу — поле `is_active` будет `false`. Приглашение активируется автоматически при разрешении конфликта.

### GET /projects/{id}/invitations

Список pending-приглашений проекта. Требуется R-10.

Ответ `200`:
```json
{
  "items": [
    {
      "id": "uuid",
      "invitee_user_id": "uuid | null",
      "invitee_team_id": "uuid | null",
      "permissions": { /* ProjectPermissions */ },
      "status": "pending",
      "is_active": true,
      "invited_by": "uuid",
      "created_at": "..."
    }
  ]
}
```

### DELETE /projects/{id}/invitations/{invitation_id}

Отозвать приглашение. Требуется R-10.

Ответ `204`.

### POST /invitations/projects/{invitation_id}/accept

Принять приглашение в проект. Вызывается приглашённым пользователем (или админом приглашённой команды).

Ответ `200`: `ProjectMember` или `ProjectTeamMember`.

### POST /invitations/projects/{invitation_id}/decline

Отклонить приглашение в проект.

Ответ `204`.

---

## 12. Передача владения проектом

### POST /projects/{id}/ownership-transfers

Инициировать передачу владения. Вызывается текущим владельцем.

Тело:
```json
{ "to_user_id": "uuid" }
```

Ответ `201`:
```json
{
  "id": "uuid",
  "from_user_id": "uuid",
  "to_user_id": "uuid",
  "status": "pending",
  "created_at": "..."
}
```

### DELETE /projects/{id}/ownership-transfers/{transfer_id}

Отменить инициированную передачу. Вызывает инициатор.

Ответ `204`.

### POST /ownership-transfers/projects/{transfer_id}/accept

Принять передачу владения проектом. Вызывает целевой пользователь.

Ответ `200`: `Project`.

Ошибки: `tariff_limit_exceeded` (у нового владельца не хватает лимита проектов на его тарифе).

### POST /ownership-transfers/projects/{transfer_id}/decline

Отклонить передачу.

Ответ `204`.

---

## 13. Секреты проекта

### GET /projects/{id}/secrets

Список секретов (без значений). Требуется R-11.

Ответ `200`:
```json
{
  "items": [
    { "key": "slack_webhook", "created_at": "...", "updated_at": "..." }
  ]
}
```

### PUT /projects/{id}/secrets/{key}

Создать или обновить секрет. Требуется R-11.

Тело:
```json
{ "value": "string" }
```

Ответ `204`.

### DELETE /projects/{id}/secrets/{key}

Удалить секрет. Требуется R-11.

Ответ `204`.

---

## 14. Автоматизации

### GET /projects/{id}/automations

Список автоматизаций проекта.

Ответ `200`: `{ "items": [ /* Automation */ ] }`.

### POST /projects/{id}/automations

Создать автоматизацию. Требуется R-11.

Тело:
```json
{
  "name": "Notify Slack on close",
  "trigger_event_type": "task.status_changed",
  "condition_rsql": "status==closed;tags==release-blocker",
  "action": {
    "method": "POST",
    "url": "{{secrets.slack_webhook}}",
    "headers": { "Content-Type": "application/json" },
    "body": "{\"text\": \"Closed: {{task.title}} by {{event.author}}\"}"
  },
  "is_enabled": true
}
```

Ответ `201`: `Automation`.

Ошибки: `tariff_limit_exceeded` (лимит автоматизаций в проекте).

### GET /projects/{id}/automations/{automation_id}

Получить автоматизацию.

Ответ `200`: `Automation`.

### PATCH /projects/{id}/automations/{automation_id}

Изменить автоматизацию. Требуется R-11.

Тело — любое подмножество полей `Automation`, доступных для изменения.

Ответ `200`: `Automation`.

### POST /projects/{id}/automations/{automation_id}/enable

Включить автоматизацию. Требуется R-11. Также используется для ре-активации после автовыключения.

Ответ `200`: `Automation` (с `is_enabled=true`, `consecutive_failures=0`).

### POST /projects/{id}/automations/{automation_id}/disable

Выключить автоматизацию. Требуется R-11.

Ответ `200`: `Automation` (с `is_enabled=false`).

### DELETE /projects/{id}/automations/{automation_id}

Удалить автоматизацию. Требуется R-11.

Ответ `204`.

### GET /projects/{id}/automations/{automation_id}/runs

История срабатываний конкретной автоматизации.

Query-параметры: `cursor`, `limit`, `from`, `to`, `status`.

Ответ `200`: `{ "items": [ /* AutomationRun */ ], "next_cursor": "..." }`.

---

## 15. Команды

### GET /teams

Список команд пользователя.

Query: `q`, `only_owned`, `cursor`, `limit`.

Ответ `200`: `{ "items": [ /* Team */ ], ... }`.

### POST /teams

Создать команду. Создатель становится владельцем и единственным админом.

Тело: `{ "name": "string" }`.

Ответ `201`: `Team`.

Ошибки: `tariff_limit_exceeded`.

### GET /teams/{id}

Получить команду.

Ответ `200`:
```json
{
  "team": { /* Team */ },
  "is_member": true,
  "is_admin": true
}
```

### PATCH /teams/{id}

Переименовать команду. Доступно админам команды.

Тело: `{ "name": "string" }`.

Ответ `200`: `Team`.

### DELETE /teams/{id}

Удалить команду. Доступно админам.

Ответ `204`.

### GET /teams/{id}/members

Список участников команды. Доступно участникам команды.

Ответ `200`: `{ "items": [ /* TeamMember */ ] }`.

### PATCH /teams/{id}/members/{user_id}

Выдать или снять админство. Доступно админам команды.

Тело:
```json
{ "is_admin": true }
```

Ответ `200`: `TeamMember`.

### DELETE /teams/{id}/members/{user_id}

Удалить участника. Доступно админам. Нельзя удалить владельца.

Ответ `204`.

### GET /teams/search

Поиск команд для добавления в доступы/проекты.

Query: `q` (мин. 2 символа), `limit`.

Ответ `200`: `{ "items": [ { "id": "...", "name": "..." } ] }`.

---

## 16. Приглашения в команду

### POST /teams/{id}/invitations

Пригласить пользователя в команду. Доступно админам.

Тело: `{ "invitee_user_id": "uuid" }`.

Ответ `201`:
```json
{
  "id": "uuid",
  "status": "pending",
  "created_at": "..."
}
```

### GET /teams/{id}/invitations

Список pending-приглашений команды. Доступно админам.

### DELETE /teams/{id}/invitations/{invitation_id}

Отозвать приглашение.

Ответ `204`.

### POST /invitations/teams/{invitation_id}/accept

Принять приглашение в команду.

Ответ `200`: `TeamMember`.

### POST /invitations/teams/{invitation_id}/decline

Отклонить приглашение.

Ответ `204`.

---

## 17. Передача владения командой

### POST /teams/{id}/ownership-transfers

Инициировать передачу. Вызывает текущий владелец.

Тело: `{ "to_user_id": "uuid" }`.

Ответ `201`: объект передачи (см. ProjectOwnershipTransfer, аналог).

### DELETE /teams/{id}/ownership-transfers/{transfer_id}

Отменить.

Ответ `204`.

### POST /ownership-transfers/teams/{transfer_id}/accept

Принять передачу. Вызывает целевой пользователь.

Ответ `200`: `Team`. Ошибки: `tariff_limit_exceeded`.

### POST /ownership-transfers/teams/{transfer_id}/decline

Отклонить.

Ответ `204`.

---

## 18. Входящие приглашения

### GET /invitations/incoming

Сводный список всех входящих для текущего пользователя приглашений — в команды, в проекты, передач владения.

Query: `type` (опц., один из `team`, `project`, `team_ownership`, `project_ownership`), `status` (default `pending`), `cursor`, `limit`.

Ответ `200`:
```json
{
  "items": [
    {
      "type": "project",
      "id": "uuid",
      "project": { /* Project */ },
      "permissions": { /* ProjectPermissions */ },
      "invited_by": "uuid",
      "created_at": "..."
    },
    {
      "type": "team",
      "id": "uuid",
      "team": { /* Team */ },
      "invited_by": "uuid",
      "created_at": "..."
    },
    {
      "type": "project_ownership",
      "id": "uuid",
      "project": { /* Project */ },
      "from_user_id": "uuid",
      "created_at": "..."
    }
  ],
  "next_cursor": "..."
}
```

---

## 19. События

### GET /events

Получить ленту событий с фильтрацией.

Query-параметры (все опциональны):
- `actor_id` — один или несколько (`?actor_id=...&actor_id=...`).
- `project_id` — один или несколько.
- `task_id` — один или несколько.
- `type` — один или несколько типов событий из каталога.
- `from`, `to` — временной диапазон в ISO 8601.
- `cursor`, `limit`.

Ответ `200`:
```json
{
  "items": [ /* Event */ ],
  "next_cursor": "...",
  "total": 12345
}
```

Пользователь видит события только тех сущностей, к которым у него есть хотя бы какой-то доступ (либо он автор действия).

---

## 20. Тарифы

### GET /tariffs/plans

Список всех тарифов с их лимитами. Публично (без аутентификации).

Ответ `200`:
```json
{
  "plans": [
    {
      "id": "free",
      "name": "Free",
      "limits": {
        "tasks_total": 200,
        "projects_owned": 3,
        "teams_owned": 3,
        "automations_per_project": 3,
        "members_per_project_or_team": 10,
        "managed_users": 3,
        "storage_bytes": 524288000
      },
      "pricing": {
        "monthly": null,
        "yearly": null
      }
    },
    {
      "id": "pro",
      "name": "Pro",
      "limits": {
        "tasks_total": null,
        "projects_owned": 20,
        "teams_owned": 20,
        "automations_per_project": 20,
        "members_per_project_or_team": 50,
        "managed_users": 20,
        "storage_bytes": 10737418240
      },
      "pricing": {
        "monthly": { "amount": 490, "currency": "RUB" },
        "yearly": { "amount": 4990, "currency": "RUB" }
      }
    }
    // ...
  ]
}
```

`null` в поле limit означает unlimited. Значения `storage_bytes` — в байтах (500 МБ, 10 ГБ соответственно для Free и Pro; на Team — 107374182400, на Enterprise — `null`).

### GET /tariffs/subscription

Получить текущую подписку пользователя и состояние банка дней.

Ответ `200`: `Subscription`.

### GET /tariffs/usage

Текущее использование лимитов.

Ответ `200`:
```json
{
  "tasks_total": { "used": 42, "limit": 200 },
  "projects_owned": { "used": 2, "limit": 3 },
  "teams_owned": { "used": 1, "limit": 3 },
  "automations_per_project": {
    "worst_case": { "project_id": "uuid", "used": 2, "limit": 3 }
  },
  "members_per_project": {
    "worst_case": { "project_id": "uuid", "used": 8, "limit": 10 }
  },
  "members_per_team": {
    "worst_case": { "team_id": "uuid", "used": 6, "limit": 10 }
  },
  "managed_users": { "used": 1, "limit": 3 },
  "storage_bytes": { "used": 104857600, "limit": 524288000 }
}
```

`null` в `limit` означает unlimited. Для `managed_users` и `storage_bytes` значения общего пула (родитель + все его managed).

### GET /tariffs/history

История смен тарифа.

Query: `cursor`, `limit`.

Ответ `200`:
```json
{
  "items": [
    {
      "plan": "pro",
      "period": "monthly",
      "started_at": "...",
      "ended_at": "...",
      "reason": "upgrade"
    }
  ]
}
```

### GET /tariffs/blocked

Список сущностей, заблокированных тарифом.

Ответ `200`:
```json
{
  "tasks": [ { "id": "uuid", "title": "...", "blocked_at": "..." } ],
  "projects": [ { "id": "uuid", "name": "...", "blocked_at": "..." } ],
  "teams": [ ... ],
  "automations": [ { "id": "uuid", "name": "...", "project_id": "uuid", "blocked_at": "..." } ],
  "project_members": [ { "project_id": "uuid", "user_id": "uuid", "blocked_at": "..." } ],
  "team_members": [ { "team_id": "uuid", "user_id": "uuid", "blocked_at": "..." } ]
}
```

### POST /tariffs/upgrade

Инициировать апгрейд тарифа. Возвращает ссылку на оплату в ЮKassa.

Тело:
```json
{
  "plan": "pro | team | enterprise",
  "period": "monthly | yearly"
}
```

Ответ `200`:
```json
{
  "payment_url": "https://yoomoney.ru/checkout/payments/v2/...",
  "payment_id": "uuid"
}
```

После успешной оплаты (callback от ЮKassa) тариф активируется, старый оборачивается в слой банка. При неуспехе оплаты тариф не изменяется.

### POST /tariffs/downgrade

Запланировать даунгрейд — применяется с начала следующего периода.

Тело:
```json
{ "plan": "free | pro | team" }
```

Ответ `200`: `Subscription` (с установленным `planned_downgrade`).

### DELETE /tariffs/downgrade

Отменить запланированный даунгрейд. Возможно до `planned_downgrade.effective_at`.

Ответ `200`: `Subscription`.

### POST /tariffs/enterprise-slots

Купить дополнительные слоты Enterprise.

Тело:
```json
{ "slots_to_add": 25 }
```

Ответ `200`:
```json
{
  "payment_url": "https://...",
  "payment_id": "uuid"
}
```

### PATCH /tariffs/enterprise-slots

Запланировать уменьшение количества слотов Enterprise — применяется с конца оплаченного периода.

Тело:
```json
{ "new_total_slots": 50 }
```

`new_total_slots` меньше текущего `enterprise_slots`.

Ответ `200`: `Subscription` (с установленным `enterprise_slots_pending_decrease`).

### DELETE /tariffs/enterprise-slots/pending-decrease

Отменить запланированное уменьшение слотов.

Ответ `200`: `Subscription`.

---

## 21. ЮKassa-callback

### POST /payments/yukassa/webhook

Callback от ЮKassa для обновления статуса платежа. Вызывается платёжной системой, не пользователем. Аутентификация по подписи ЮKassa.

Ответ `200` (любой другой код приведёт к повторной отправке от ЮKassa).

---

# Коды событий для автоматизаций и ленты

Полный перечень значений `type` в `Event` и `trigger_event_type` в `Automation`:

**Task:** `task.created`, `task.title_changed`, `task.description_changed`, `task.status_changed`, `task.assignee_changed`, `task.tags_changed`, `task.blockers_changed`, `task.attached_to_project`, `task.detached_from_project`, `task.access_granted`, `task.access_revoked`, `task.access_changed`, `task.deleted`, `task.blocked_by_tariff`, `task.unblocked_by_tariff`.

**Project:** `project.created`, `project.renamed`, `project.member_added`, `project.member_removed`, `project.member_access_changed`, `project.owner_changed`, `project.deleted`, `project.blocked_by_tariff`, `project.unblocked_by_tariff`.

**Team:** `team.created`, `team.renamed`, `team.member_added`, `team.member_removed`, `team.admin_granted`, `team.admin_revoked`, `team.owner_changed`, `team.deleted`, `team.blocked_by_tariff`, `team.unblocked_by_tariff`, `team.frozen_in_project`, `team.unfrozen_in_project`.

**Automation:** `automation.enabled`, `automation.disabled`, `automation.auto_disabled`, `automation.blocked_by_tariff`, `automation.unblocked_by_tariff`.

**User / Tariff:** `user.tariff_changed`, `user.tariff_bank_applied`, `user.managed_created`, `user.managed_email_verified`, `user.managed_deactivated`, `user.managed_reactivated`, `user.managed_password_reset`, `user.deleted`.

---

# Шаблоны плейсхолдеров в автоматизациях

В полях `action.url`, `action.headers`, `action.body` поддерживаются плейсхолдеры вида `{{path.to.value}}`, которые подставляются при срабатывании.

Доступные контексты:

**Событие (всегда):**
- `{{event.id}}`, `{{event.type}}`, `{{event.created_at}}`, `{{event.actor}}` (email автора действия), `{{event.payload.*}}` — любые поля payload по точечной нотации.

**Задача** (при триггерах на события, связанные с задачами — `task.*`):
- `{{task.id}}`, `{{task.title}}`, `{{task.description}}`, `{{task.status}}`, `{{task.author}}` (email), `{{task.assignee}}` (email или пустая строка), `{{task.tags}}` (объединённая строка через запятую), `{{task.project_ids}}`.

**Проект** (при `project.*` и `task.attached_to_project` / `task.detached_from_project`):
- `{{project.id}}`, `{{project.name}}`, `{{project.owner}}` (email).

**Команда** (при `team.*`):
- `{{team.id}}`, `{{team.name}}`, `{{team.owner}}`.

**Секреты проекта:**
- `{{secrets.<key>}}` — подставляется значение секрета. Значения секретов не логируются и не видны в истории срабатываний.

**Пример:** тело POST-запроса в Slack:
```
{"text": "Task *{{task.title}}* was closed by {{event.actor}} in project {{project.name}}"}
```

**Экранирование.** Если в строке нужен буквальный фрагмент `{{…}}`, он удваивается: `{{{{…}}}}`.
