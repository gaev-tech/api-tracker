# Схема БД — PostgreSQL

Документ описывает физическую модель базы данных под PostgreSQL 14+. Указаны таблицы, их колонки, типы PostgreSQL, ключи, индексы и связи.

Общие соглашения:
- Первичные ключи — `UUID` (`gen_random_uuid()` из `pgcrypto` / `uuid-ossp`).
- Временные метки — `TIMESTAMPTZ` (с таймзоной).
- Длинные тексты — `TEXT`. Короткие строковые значения — `VARCHAR(n)` с явными лимитами.
- Массивы — нативные PostgreSQL-массивы (`TEXT[]`, `UUID[]`), кроме случаев, где нужна независимая жизнь элементов (тогда отдельная таблица связи).
- JSONB используется для слабоструктурированных блоков (payload событий, заголовки HTTP-запросов автоматизаций).
- Перечисления (`status`, `tariff_plan` и т.п.) реализованы как PostgreSQL `ENUM`-типы.

---

## 1. Перечисления (ENUM)

| Тип | Значения | Описание |
|---|---|---|
| `task_status` | `opened`, `progress`, `closed` | Статус задачи |
| `tariff_plan` | `free`, `pro`, `team`, `enterprise` | Тариф |
| `billing_period` | `monthly`, `yearly` | Период подписки |
| `subscription_change_reason` | `upgrade`, `downgrade`, `bank_activated`, `payment_failed`, `ownership_transfer` | Причина смены тарифа в истории |
| `invitation_status` | `pending`, `accepted`, `declined`, `revoked` | Статус приглашения |
| `automation_run_status` | `success`, `failed`, `retrying`, `timeout` | Статус срабатывания автоматизации |
| `event_type` | Все события системы (см. каталог событий в основном документе) | Тип события |

---

## 2. Пользователи и аутентификация

### 2.1. `users`

Пользователи системы.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | Идентификатор |
| `email` | `VARCHAR(255)` | NOT NULL, UNIQUE | Email (используется для идентификации в RSQL и CSV-импорте). Уникален глобально по всем пользователям (обычным и managed) |
| `password_hash` | `VARCHAR(255)` | NOT NULL | Хеш пароля |
| `theme` | `VARCHAR(32)` | NOT NULL, DEFAULT `'light'` | Тема UI |
| `language` | `VARCHAR(8)` | NOT NULL, DEFAULT `'en'` | Язык UI (ISO 639-1) |
| `parent_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE CASCADE | Родитель для managed-пользователя. NULL для обычных пользователей |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT `true` | Флаг активности. FALSE — пользователь не может логиниться (деактивирован) |
| `email_verified_at` | `TIMESTAMPTZ` | NULL | Время подтверждения email. NULL — email не подтверждён, логин невозможен |
| `email_verification_token` | `VARCHAR(128)` | NULL | Токен для подтверждения email. Очищается при успешной верификации |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Ограничения:
- `CHECK (parent_user_id <> id)` — пользователь не может быть своим родителем.

Индексы:
- `UNIQUE` на `email` (уже от ограничения).
- `idx_users_email_lower` — `LOWER(email)` для регистронезависимого поиска пользователей.
- `idx_users_parent_user_id` — для выборки managed-пользователей родителя.
- `UNIQUE` на `email_verification_token` (частичный, `WHERE email_verification_token IS NOT NULL`) — токены должны быть глобально уникальны.

Комментарий. Иерархия пользователей одноуровневая: managed-пользователь не может иметь собственных managed (контролируется на уровне приложения — при создании managed проверяется, что `parent_user_id` указывает на пользователя с `parent_user_id IS NULL`).

### 2.2. `pats`

Personal Access Tokens.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | Владелец токена |
| `name` | `VARCHAR(255)` | NOT NULL | Имя токена (задаётся пользователем) |
| `token` | `VARCHAR(128)` | NOT NULL, UNIQUE | Значение токена в открытом виде (по требованию: токен всегда видим владельцу) |
| `expires_at` | `TIMESTAMPTZ` | NULL | Срок истечения (NULL = бессрочный) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `revoked_at` | `TIMESTAMPTZ` | NULL | Время отзыва (NULL = активен) |

Индексы:
- `UNIQUE` на `token` — для быстрой аутентификации.
- `idx_pats_user_id` на `user_id`.

### 2.3. `password_reset_tokens`

Токены для восстановления пароля через email-ссылку.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | Пользователь, которому принадлежит токен |
| `token_hash` | `VARCHAR(128)` | NOT NULL, UNIQUE | Хеш токена (в email уходит открытый токен, в БД — хеш) |
| `expires_at` | `TIMESTAMPTZ` | NOT NULL | Срок истечения (обычно +24 часа от создания) |
| `used_at` | `TIMESTAMPTZ` | NULL | Момент использования (NULL = не использован) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `UNIQUE` на `token_hash`.
- `idx_password_reset_user_id` на `user_id`.

---

## 3. Команды

### 3.1. `teams`

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `name` | `VARCHAR(255)` | NOT NULL | Название команды |
| `owner_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | Владелец команды. При удалении владельца команда каскадно удаляется |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Команда заблокирована тарифом владельца |
| `blocked_at` | `TIMESTAMPTZ` | NULL | Время блокировки |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_teams_owner_id` на `owner_id`.

### 3.2. `team_members`

Участники команд.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `team_id` | `UUID` | NOT NULL, FK → `teams.id` ON DELETE CASCADE | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `is_admin` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Роль: админ команды или участник |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Участник сверхлимита — блокируется в порядке от новых к старым |
| `joined_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Используется для порядка блокировки |

Первичный ключ: `(team_id, user_id)`.

Индексы:
- `idx_team_members_user_id` на `user_id`.
- `idx_team_members_team_admins` на `(team_id) WHERE is_admin = true` — для быстрой проверки условия «команда существует, пока есть хотя бы один админ».

### 3.3. `team_invitations`

Приглашения пользователей в команды.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `team_id` | `UUID` | NOT NULL, FK → `teams.id` ON DELETE CASCADE | |
| `invitee_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | Приглашаемый пользователь |
| `invited_by` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Кто пригласил |
| `status` | `invitation_status` | NOT NULL, DEFAULT `'pending'` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `resolved_at` | `TIMESTAMPTZ` | NULL | Момент принятия/отклонения |

Индексы:
- `idx_team_invitations_invitee` на `(invitee_id, status)`.
- `UNIQUE (team_id, invitee_id) WHERE status = 'pending'` — не допускать двух pending-приглашений одному и тому же пользователю в одну и ту же команду.

### 3.4. `team_ownership_transfers`

Передача владения командой.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `team_id` | `UUID` | NOT NULL, FK → `teams.id` ON DELETE CASCADE | |
| `from_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Инициатор (текущий владелец) |
| `to_user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | Кандидат |
| `status` | `invitation_status` | NOT NULL, DEFAULT `'pending'` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `resolved_at` | `TIMESTAMPTZ` | NULL | |

Индексы:
- `idx_team_ownership_to_user` на `(to_user_id, status)`.
- `UNIQUE (team_id) WHERE status = 'pending'` — максимум один активный запрос на передачу владения командой.

---

## 4. Проекты

### 4.1. `projects`

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `name` | `VARCHAR(255)` | NOT NULL | |
| `owner_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | Владелец. При удалении владельца проект каскадно удаляется |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `blocked_at` | `TIMESTAMPTZ` | NULL | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_projects_owner_id` на `owner_id`.

### 4.2. `project_members`

Пользователи — участники проектов с индивидуальным набором прав.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `r1_edit_title` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-1 |
| `r2_edit_description` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-2 |
| `r3_edit_tags` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-3 |
| `r4_edit_blockers` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-4 |
| `r5_edit_assignee` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-5 |
| `r6_edit_status` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-6 |
| `r7_share` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-7 |
| `r8_delete` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-8 |
| `r9_rename_project` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-9 |
| `r10_manage_members` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-10 |
| `r11_manage_automations` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-11 |
| `r12_manage_attachments` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-12 |
| `r13_delete_project` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-13 |
| `r14_import` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Право R-14 |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Участник сверхлимита (владелец проекта никогда) |
| `joined_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Для порядка блокировки участников |

Первичный ключ: `(project_id, user_id)`.

Индексы:
- `idx_project_members_user_id` на `user_id`.
- `idx_project_members_r13` на `(project_id) WHERE r13_delete_project = true` — для быстрой проверки жизни проекта.

Комментарий. Отдельные boolean-колонки по правам выбраны ради явности схемы и возможности индексирования партиальными индексами. Альтернатива — `INTEGER` bitmask на 14 бит или `TEXT[]` с кодами прав, но в обоих случаях страдают читаемость и индексируемость.

### 4.3. `project_teams`

Команды — участники проектов.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `team_id` | `UUID` | NOT NULL, FK → `teams.id` ON DELETE CASCADE | |
| `r1_edit_title` … `r14_import` | `BOOLEAN` | NOT NULL, DEFAULT `false` | 14 колонок по правам (те же, что в `project_members`) |
| `is_frozen_in_project` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Заморозка команды в проекте из-за превышения лимита участников проекта |
| `frozen_at` | `TIMESTAMPTZ` | NULL | |
| `joined_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Первичный ключ: `(project_id, team_id)`.

Индексы:
- `idx_project_teams_team_id` на `team_id`.

### 4.4. `project_invitations`

Приглашения в проект — пользователя или команды. Ровно одно из `invitee_user_id` / `invitee_team_id` заполнено.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `invitee_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE CASCADE | |
| `invitee_team_id` | `UUID` | NULL, FK → `teams.id` ON DELETE CASCADE | |
| `invited_by` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | |
| `r1_edit_title` … `r14_import` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Предлагаемые права (14 колонок) |
| `status` | `invitation_status` | NOT NULL, DEFAULT `'pending'` | |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT `true` | FALSE для приглашений команды, созданных при превышении лимита — будут активированы, когда лимит позволит |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `resolved_at` | `TIMESTAMPTZ` | NULL | |

Ограничения уровня таблицы:
- `CHECK ((invitee_user_id IS NOT NULL) <> (invitee_team_id IS NOT NULL))` — ровно одно из полей.

Индексы:
- `idx_project_invitations_invitee_user` на `(invitee_user_id, status)`.
- `idx_project_invitations_invitee_team` на `(invitee_team_id, status)`.
- `UNIQUE (project_id, invitee_user_id) WHERE status = 'pending' AND invitee_user_id IS NOT NULL`.
- `UNIQUE (project_id, invitee_team_id) WHERE status = 'pending' AND invitee_team_id IS NOT NULL`.

### 4.5. `project_ownership_transfers`

Аналогично `team_ownership_transfers`, но для проектов.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `from_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | |
| `to_user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `status` | `invitation_status` | NOT NULL, DEFAULT `'pending'` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `resolved_at` | `TIMESTAMPTZ` | NULL | |

Индексы:
- `idx_project_ownership_to_user` на `(to_user_id, status)`.
- `UNIQUE (project_id) WHERE status = 'pending'`.

### 4.6. `project_secrets`

Секреты проекта, используемые в шаблонах автоматизаций.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `key` | `VARCHAR(255)` | NOT NULL | Имя секрета (используется в `{{secrets.<key>}}`) |
| `value_encrypted` | `BYTEA` | NOT NULL | Зашифрованное значение (шифруется на уровне приложения) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Ограничения:
- `UNIQUE (project_id, key)`.

---

## 5. Задачи

### 5.1. `tasks`

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `title` | `VARCHAR(500)` | NOT NULL | |
| `description` | `TEXT` | NOT NULL, DEFAULT `''` | Markdown |
| `status` | `task_status` | NOT NULL, DEFAULT `'opened'` | |
| `author_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Автор. При удалении пользователя становится NULL — ссылка на удалённого эквивалентна отсутствию |
| `assignee_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Ответственный (один или NULL) |
| `tags` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Теги как массив строк |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_tasks_author_id` на `author_id`.
- `idx_tasks_assignee_id` на `assignee_id`.
- `idx_tasks_status` на `status`.
- `idx_tasks_tags_gin` — GIN-индекс на `tags` для эффективной фильтрации по массиву (`tags @> ARRAY['urgent']` и т.п., используется в RSQL).
- `idx_tasks_created_at` на `created_at` (для фильтров по диапазону дат).
- `idx_tasks_updated_at` на `updated_at`.

Комментарий. Поле `blocked_tasks` (обратная сторона блокировок) не хранится — вычисляется на лету из таблицы `task_blockers`.

### 5.2. `task_projects`

Прикрепление задач к проектам (многие-ко-многим).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `task_id` | `UUID` | NOT NULL, FK → `tasks.id` ON DELETE CASCADE | |
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `attached_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Первичный ключ: `(task_id, project_id)`.

Индексы:
- `idx_task_projects_project_id` на `project_id`.

### 5.3. `task_blockers`

Связи блокировок между задачами.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `task_id` | `UUID` | NOT NULL, FK → `tasks.id` ON DELETE CASCADE | Блокируемая задача |
| `blocker_task_id` | `UUID` | NOT NULL, FK → `tasks.id` ON DELETE CASCADE | Блокирующая задача |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Первичный ключ: `(task_id, blocker_task_id)`.

Ограничения:
- `CHECK (task_id <> blocker_task_id)` — задача не может блокировать сама себя.

Индексы:
- `idx_task_blockers_blocker_task_id` на `blocker_task_id` — для быстрого построения `blocked_tasks`.

### 5.4. `task_direct_accesses`

Прямые доступы на задачу. Выдаются пользователю ИЛИ команде.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `task_id` | `UUID` | NOT NULL, FK → `tasks.id` ON DELETE CASCADE | |
| `grantee_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE CASCADE | |
| `grantee_team_id` | `UUID` | NULL, FK → `teams.id` ON DELETE CASCADE | |
| `granted_by` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Автор выдачи доступа |
| `r1_edit_title` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r2_edit_description` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r3_edit_tags` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r4_edit_blockers` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r5_edit_assignee` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r6_edit_status` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r7_share` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `r8_delete` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Ограничения:
- `CHECK ((grantee_user_id IS NOT NULL) <> (grantee_team_id IS NOT NULL))` — ровно одно из.
- `UNIQUE (task_id, grantee_user_id) WHERE grantee_user_id IS NOT NULL`.
- `UNIQUE (task_id, grantee_team_id) WHERE grantee_team_id IS NOT NULL`.

Индексы:
- `idx_task_direct_accesses_grantee_user` на `grantee_user_id`.
- `idx_task_direct_accesses_grantee_team` на `grantee_team_id`.
- `idx_task_direct_accesses_task_r8` на `(task_id) WHERE r8_delete = true` — для быстрой проверки условия жизни задачи «есть хотя бы один прямой доступ с R-8».

---

## 6. Автоматизации

### 6.1. `automations`

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | NOT NULL, FK → `projects.id` ON DELETE CASCADE | |
| `name` | `VARCHAR(255)` | NOT NULL | |
| `trigger_event_type` | `event_type` | NOT NULL | Тип события-триггера |
| `condition_rsql` | `TEXT` | NULL | RSQL-условие (опционально) |
| `action_method` | `VARCHAR(10)` | NOT NULL | HTTP-метод: GET/POST/PUT/PATCH/DELETE |
| `action_url` | `TEXT` | NOT NULL | URL-шаблон |
| `action_headers` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Заголовки-шаблоны |
| `action_body` | `TEXT` | NULL | Тело-шаблон |
| `is_enabled` | `BOOLEAN` | NOT NULL, DEFAULT `true` | |
| `consecutive_failures` | `INTEGER` | NOT NULL, DEFAULT `0` | Счётчик подряд идущих неуспехов — сбрасывается при успехе, триггерит авто-выключение на 10 |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_automations_project_id` на `project_id`.
- `idx_automations_trigger_event_type` на `(trigger_event_type) WHERE is_enabled = true AND is_blocked_by_tariff = false` — для быстрой выборки автоматизаций, подписанных на конкретный тип события.

### 6.2. `automation_runs`

История срабатываний автоматизаций (для ретраев и аудита).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `automation_id` | `UUID` | NOT NULL, FK → `automations.id` ON DELETE CASCADE | |
| `event_id` | `UUID` | NOT NULL, FK → `events.id` ON DELETE CASCADE | Событие-триггер |
| `attempt_number` | `SMALLINT` | NOT NULL | Номер попытки (1…4) |
| `status` | `automation_run_status` | NOT NULL | |
| `response_code` | `SMALLINT` | NULL | HTTP-код ответа, если ответ получен |
| `response_body_excerpt` | `VARCHAR(2000)` | NULL | Обрезка тела ответа для отладки |
| `error_message` | `TEXT` | NULL | Описание ошибки при неуспехе |
| `started_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `finished_at` | `TIMESTAMPTZ` | NULL | |

Индексы:
- `idx_automation_runs_automation_id` на `(automation_id, started_at DESC)`.
- `idx_automation_runs_event_id` на `event_id`.

---

## 7. События

### 7.1. `events`

Все события системы. Таблица растёт линейно; рекомендуется партицирование по `created_at` (например, помесячно) для производительности.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `type` | `event_type` | NOT NULL | Тип события |
| `actor_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Автор действия (NULL для системных событий, например `automation.auto_disabled`) |
| `task_id` | `UUID` | NULL, FK → `tasks.id` ON DELETE SET NULL | Затронутая задача, если применимо |
| `project_id` | `UUID` | NULL, FK → `projects.id` ON DELETE SET NULL | Затронутый проект, если применимо |
| `team_id` | `UUID` | NULL, FK → `teams.id` ON DELETE SET NULL | Затронутая команда, если применимо |
| `automation_id` | `UUID` | NULL, FK → `automations.id` ON DELETE SET NULL | Затронутая автоматизация, если применимо |
| `target_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Целевой пользователь для `user.*` и `*.member_*` событий |
| `payload` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Детали события: старое/новое значение, состав прав и т.п. |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы (с учётом фильтрации ленты событий по автору, проекту, задачам, типу, временному диапазону):
- `idx_events_created_at` на `created_at DESC` (основной индекс ленты; при партицировании — локальный в каждой партиции).
- `idx_events_actor_created` на `(actor_id, created_at DESC)`.
- `idx_events_project_created` на `(project_id, created_at DESC)`.
- `idx_events_task_created` на `(task_id, created_at DESC)`.
- `idx_events_type_created` на `(type, created_at DESC)`.

---

## 8. Тарификация

### 8.1. `subscriptions`

Текущая подписка пользователя (1-к-1 с `users`). Записи создаются при регистрации на Free-тариф.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `user_id` | `UUID` | PK, FK → `users.id` ON DELETE CASCADE | |
| `plan` | `tariff_plan` | NOT NULL, DEFAULT `'free'` | Текущий тариф |
| `period` | `billing_period` | NULL | NULL для `free`; `monthly`/`yearly` для платных |
| `current_period_start` | `TIMESTAMPTZ` | NULL | Начало текущего оплаченного периода |
| `current_period_end` | `TIMESTAMPTZ` | NULL | Конец текущего периода |
| `planned_downgrade_plan` | `tariff_plan` | NULL | Запланированный даунгрейд |
| `planned_downgrade_effective_at` | `TIMESTAMPTZ` | NULL | Момент активации даунгрейда |
| `enterprise_slots` | `INTEGER` | NOT NULL, DEFAULT `0` | Текущее количество докупленных слотов |
| `enterprise_slots_pending_decrease` | `INTEGER` | NULL | Запланированное новое значение слотов (меньше текущего) |
| `enterprise_slots_pending_effective_at` | `TIMESTAMPTZ` | NULL | Момент применения |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Ограничения:
- `CHECK (enterprise_slots >= 0)`.
- `CHECK (plan = 'enterprise' OR enterprise_slots = 0)`.

### 8.2. `subscription_bank_layers`

Слои банка дней (накопленных при апгрейдах). Активируются по окончании текущего тарифа сверху вниз.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `plan` | `tariff_plan` | NOT NULL | Тариф этого слоя |
| `period` | `billing_period` | NOT NULL | Период, из которого был создан слой |
| `days_remaining` | `INTEGER` | NOT NULL | Остаток дней на этом тарифе |
| `layer_order` | `INTEGER` | NOT NULL | Порядок активации: больший номер — ближе к вершине, активируется раньше |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Ограничения:
- `CHECK (days_remaining > 0)`.

Индексы:
- `idx_subscription_bank_user_order` на `(user_id, layer_order DESC)`.

### 8.3. `subscription_history`

История смен тарифа пользователя.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `plan` | `tariff_plan` | NOT NULL | |
| `period` | `billing_period` | NULL | |
| `started_at` | `TIMESTAMPTZ` | NOT NULL | |
| `ended_at` | `TIMESTAMPTZ` | NULL | NULL для текущей активной записи (если нужно — иначе история только о завершённых) |
| `reason` | `subscription_change_reason` | NOT NULL | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_subscription_history_user_started` на `(user_id, started_at DESC)`.

### 8.4. `payment_transactions`

Транзакции через ЮKassa.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `yukassa_payment_id` | `VARCHAR(128)` | NOT NULL, UNIQUE | Идентификатор платежа в ЮKassa |
| `amount` | `NUMERIC(12,2)` | NOT NULL | |
| `currency` | `VARCHAR(3)` | NOT NULL, DEFAULT `'RUB'` | |
| `purpose` | `VARCHAR(64)` | NOT NULL | Например: `subscription_upgrade`, `subscription_renewal`, `enterprise_slots`. |
| `status` | `VARCHAR(32)` | NOT NULL | `pending`, `succeeded`, `failed`, `canceled` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Индексы:
- `idx_payment_transactions_user_created` на `(user_id, created_at DESC)`.

---

## 9. Файлы

### 9.1. `files`

Метаданные файлов: inline-вложения в описания задач, CSV-импорты.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `owner_user_id` | `UUID` | NULL, FK → `users.id` ON DELETE SET NULL | Кто загрузил файл. При удалении пользователя становится NULL (файл остаётся связанным с задачей/проектом, если он там используется) |
| `task_id` | `UUID` | NULL, FK → `tasks.id` ON DELETE CASCADE | Для вложений: задача, в описании которой используется файл |
| `project_id` | `UUID` | NULL, FK → `projects.id` ON DELETE CASCADE | Для CSV-импортов: проект назначения |
| `s3_key` | `VARCHAR(512)` | NOT NULL, UNIQUE | Ключ объекта в S3 |
| `content_type` | `VARCHAR(128)` | NOT NULL | MIME-тип (определён при загрузке по magic bytes) |
| `size_bytes` | `BIGINT` | NOT NULL | Размер файла в байтах |
| `purpose` | `VARCHAR(32)` | NOT NULL | `task_attachment` \| `csv_import` |
| `uploaded_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `BOOLEAN` | NOT NULL, DEFAULT `false` | Soft-delete (физическое удаление через lifecycle S3) |
| `deleted_at` | `TIMESTAMPTZ` | NULL | |

Ограничения:
- `CHECK ((task_id IS NOT NULL) OR (project_id IS NOT NULL) OR (purpose = 'csv_import' AND project_id IS NOT NULL))` — у файла должен быть родительский контекст.

Индексы:
- `idx_files_owner_user_id` на `owner_user_id` (для учёта квоты).
- `idx_files_task_id` на `task_id` (для каскадного soft-delete при удалении задачи).
- `idx_files_project_id` на `project_id`.
- `idx_files_purpose_uploaded_at` на `(purpose, uploaded_at)` (для cleanup-джобы старых CSV-импортов).

---

## 10. Счётчики использования и счётчики биллинга

### 10.1. `usage_counters`

Агрегированные счётчики использования лимитов на пользователя. Обновляются consumer'ом событий биллинга (см. `architecture.md`, раздел 2.5 billing-service). Используются в `CheckTariffLimit` (gRPC) и в `GET /tariffs/usage` API.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `user_id` | `UUID` | PK, FK → `users.id` ON DELETE CASCADE | Владелец счётчика. Для managed-пользователя все его действия прибавляются к счётчикам родителя (агрегация в общий пул делается на уровне приложения, в таблице — «корневой» owner) |
| `tasks_total_used` | `INTEGER` | NOT NULL, DEFAULT `0` | Суммарное число задач (где user — автор) с учётом managed |
| `projects_owned_used` | `INTEGER` | NOT NULL, DEFAULT `0` | Проекты, где user — владелец (включая созданные его managed) |
| `teams_owned_used` | `INTEGER` | NOT NULL, DEFAULT `0` | Команды, где user — владелец |
| `managed_users_used` | `INTEGER` | NOT NULL, DEFAULT `0` | Число managed-пользователей у этого user |
| `storage_bytes_used` | `BIGINT` | NOT NULL, DEFAULT `0` | Суммарный размер файлов в байтах |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |

Счётчики `automations_per_project` и `members_per_project`/`members_per_team` не в этой таблице — они вычисляются по per-project/per-team метаданным; при gRPC `CheckTariffLimit` для таких лимитов billing читает агрегат из соответствующих таблиц workspace-service.

Индексы: PK достаточно.

---

## 11. Денормализованные копии и outbox

Эти таблицы — не основная доменная модель, а служебные структуры для реализации паттернов database-per-service и transactional outbox. В каждом сервисе они живут в его собственной БД.

### 11.1. `users_cache` (в БД workspace-service)

Денормализованная копия пользователей, необходимая для валидации assignee по email в CSV-импорте и отображения email в ответах API. Обновляется Kafka-consumer'ом на `user-events`.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `user_id` | `UUID` | PK | |
| `email` | `VARCHAR(255)` | NOT NULL | |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT `true` | |
| `parent_user_id` | `UUID` | NULL | Для поддержки общего пула лимитов managed-пользователей |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

Индексы: `UNIQUE` на `LOWER(email)`.

### 11.2. `tasks_cache` (в БД automations-service)

Денормализованная копия полей задач, необходимых для применения RSQL-условий при срабатывании автоматизаций.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `task_id` | `UUID` | PK | |
| `title` | `VARCHAR(500)` | NOT NULL | |
| `status` | `task_status` | NOT NULL | |
| `author_id` | `UUID` | NULL | |
| `assignee_id` | `UUID` | NULL | |
| `tags` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | |
| `project_ids` | `UUID[]` | NOT NULL, DEFAULT `'{}'` | Денормализация `task_projects` |
| `is_blocked_by_tariff` | `BOOLEAN` | NOT NULL, DEFAULT `false` | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

Индексы: `idx_tasks_cache_tags_gin` (GIN по `tags`); `idx_tasks_cache_project_ids_gin` (GIN по `project_ids`).

### 11.3. Outbox-таблицы

В каждом producer-сервисе (identity, workspace, automations, billing, files) есть собственная таблица `<service>_outbox` для transactional outbox pattern (см. `architecture.md` раздел 3.1).

Структура одинакова:

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | Последовательный ID для порядка отправки |
| `aggregate_type` | `VARCHAR(64)` | NOT NULL | Тип сущности (`task`, `project`, ...), используется как Kafka-key |
| `aggregate_id` | `UUID` | NOT NULL | ID сущности |
| `event_type` | `VARCHAR(128)` | NOT NULL | Тип события (например, `task.status_changed`) |
| `payload` | `JSONB` | NOT NULL | Тело события |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | |
| `sent_at` | `TIMESTAMPTZ` | NULL | Отметка об успешной публикации в Kafka |

Индексы:
- `idx_<service>_outbox_unsent` на `(id)` с `WHERE sent_at IS NULL` — для эффективной выборки неотправленных событий outbox-relay'ем.

Retention: после успешной отправки запись может быть удалена через cleanup-cron (например, старше 7 дней) — для ускорения сканирования `WHERE sent_at IS NULL`.

## 12. Связи между таблицами (обзор)

```
users 1 ── n pats
users 1 ── 1 subscriptions
users 1 ── n subscription_bank_layers
users 1 ── n subscription_history
users 1 ── n payment_transactions
users 1 ── n users                (managed, parent_user_id)
users 1 ── n password_reset_tokens

users 1 ── n teams              (owner)
teams 1 ── n team_members n ── 1 users
teams 1 ── n team_invitations
teams 1 ── n team_ownership_transfers

users 1 ── n projects           (owner)
projects 1 ── n project_members n ── 1 users
projects 1 ── n project_teams   n ── 1 teams
projects 1 ── n project_invitations
projects 1 ── n project_ownership_transfers
projects 1 ── n project_secrets
projects 1 ── n automations

users 1 ── n tasks              (author)
users 1 ── n tasks              (assignee, nullable)
tasks  1 ── n task_projects     n ── 1 projects
tasks  1 ── n task_blockers     n ── 1 tasks          (blocker)
tasks  1 ── n task_direct_accesses  (grantee_user | grantee_team)

automations 1 ── n automation_runs n ── 1 events

events  (actor_id, task_id, project_id, team_id, automation_id, target_user_id — все опциональные FK)

users 1 ── 1 usage_counters
users 1 ── n files                (owner_user_id)
tasks 1 ── n files                (task_id, вложения в описании)
projects 1 ── n files             (project_id, CSV-импорты)
```

---

## 13. Инварианты, поддерживаемые на уровне приложения

Ряд инвариантов бизнес-логики не выражается чистой SQL-схемой и должен поддерживаться приложением (триггеры / транзакции сервиса):

- **Жизнь задачи.** Задача существует, пока прикреплена хотя бы к одному проекту (`task_projects`) или имеет хотя бы один прямой доступ с `r8_delete = true` (`task_direct_accesses`). При нарушении условия — задача удаляется.
- **Жизнь проекта.** Проект существует, пока есть хотя бы один пользователь с `r13_delete_project = true` в `project_members`. При нарушении — проект удаляется.
- **Жизнь команды.** Команда существует, пока есть хотя бы один участник с `is_admin = true` в `team_members`. При нарушении — команда удаляется.
- **R-7 ограничение при выдаче.** При создании/обновлении записи в `task_direct_accesses` сервис проверяет, что состав устанавливаемых `r1`…`r8` ⊆ права, которыми обладает `granted_by` на момент операции.
- **Лимиты тарифа.** Проверяются сервисом до создания/обновления сущностей; блокировки сверхлимитных сущностей выставляются при пересчёте лимитов.
- **Порядок активации банка.** При окончании периода основной подписки активируется слой с максимальным `layer_order`.
- **Единственность владельца.** `projects.owner_id` и `teams.owner_id` всегда ссылаются на существующего пользователя. При удалении владельца весь проект/команда каскадно удаляются (`ON DELETE CASCADE`).
- **Шифрование секретов.** Значения в `project_secrets.value_encrypted` шифруются на уровне приложения перед сохранением; ключ шифрования не хранится в БД.

### Инварианты managed-пользователей

- **Одноуровневая иерархия.** При создании managed-пользователя сервис проверяет, что `parent_user_id` указывает на пользователя с `parent_user_id IS NULL`. Managed не может иметь собственных managed.
- **Владение создаваемых сущностей.** Когда managed-пользователь создаёт проект или команду, сервис устанавливает `owner_id = parent_user_id` managed'а. Managed при этом добавляется в `project_members` / `team_members` с полным набором прав (R-1…R-14 / `is_admin = true`) как обычный участник.
- **Запрет на managed-тариф.** При вызове тарифных endpoint'ов сервис возвращает `forbidden`, если у вызывающего `parent_user_id IS NOT NULL`. Тарифные лимиты вычисляются по `parent_user_id`.
- **Общий пул лимитов.** Счётчики использования лимитов тарифа суммируются по родителю и всем его managed. Владельцем рассматривается родитель (`owner_id` уже родительский, так как managed не становится владельцем).
- **Запрет на смену email у managed.** Сервис отклоняет попытки изменения `email` для пользователя с `parent_user_id IS NOT NULL`.
- **Управление managed.** Функции создания/деактивации/ре-активации/сброса пароля/удаления managed доступны только родителю — сервис проверяет, что вызывающий = `parent_user_id` управляемого. Передача управляющих прав другим пользователям невозможна.
- **Деактивация.** При `is_active = false` отклоняется логин, отзываются все PAT, выключаются автоматизации, созданные этим пользователем, отклоняются pending-приглашения, связанные с ним. Членства в проектах и командах сохраняются.
- **Верификация email при создании managed.** Пока `email_verified_at IS NULL`, логин невозможен. Сервис отправляет письмо с токеном из `email_verification_token`; endpoint подтверждения выставляет `email_verified_at = now()` и очищает `email_verification_token`.
- **Каскадное удаление при удалении пользователя.** Все managed (через `users.parent_user_id ON DELETE CASCADE`), проекты (через `projects.owner_id ON DELETE CASCADE`), команды (через `teams.owner_id ON DELETE CASCADE`), их подчинённые записи и PAT удаляются автоматически. В остальных местах, где встречаются FK на `users.id` с `ON DELETE SET NULL`, значение обнуляется. Ссылка на несуществующего пользователя трактуется приложением как NULL («удалённый пользователь»).
