# CLI Test Cases

Каталог сценариев тестирования CLI `clite`. Каждый кейс атомарен и имеет уникальный номер; автотесты в `cli/tests/e2e/` ссылаются на этот номер в имени теста (`test_TC_<номер>_*`).

Все ссылки вида (PRD §X) — на `product.md`. (ARCH §Y) — на `architecture.md`.

## 1. Соглашения

### 1.1 Структура кейса

1.1.1 Каждый кейс содержит: вход (флаги, stdin, состояние БД), ожидаемый exit-code, ожидаемый stdout (формат и ключевые поля), ожидаемый stderr, ожидаемое побочное состояние (БД, audit_event).

### 1.2 Exit-коды (ARCH §15.7)

1.2.1 `0` — успех.

1.2.2 `1` — runtime/API ошибка (5xx ответ, обрыв сети, нерезолвимая ошибка).

1.2.3 `2` — invalid argument/flag (typer-convention).

1.2.4 `3` — auth required (нет токена или 401).

1.2.5 `4` — forbidden (403).

### 1.3 Формат вывода

1.3.1 Default — построчный человеко-читаемый формат при TTY, json при пайпе.

1.3.2 `--output json` принудительно JSON.

1.3.3 `--output table` — построчный формат `field: value`, пустая строка между сущностями (PRD §7.9.4). Имя флага исторически `table`, реальный рендер не табличный.

1.3.4 `--fields a,b,c` — рендерить только указанные поля (применимо ко всем get/list-командам, PRD §7.9). Поле, отсутствующее в ответе, опускается. Без флага — дефолтный набор полей данной команды.

### 1.4 Идентификаторы и prefix-lookup

1.4.1 Любая команда, принимающая SHA1-ключ сущности (task, team, project, automation, secret), принимает также префикс ключа от 4 hex-символов (PRD §5.2.7).

1.4.2 Префикс короче 4 символов → exit 2, stderr `prefix too short (min 4 chars)`.

1.4.3 Префикс не найден → exit 1, stderr `<entity> not found`.

1.4.4 Префикс соответствует >1 сущности → exit 1, stderr `ambiguous prefix '<p>', candidates:\n  <sha1>  <discriminator>\n  ...`.

## 2. Общие негативные кейсы (применимы к любой команде)

2.1 Неизвестный флаг → exit 2, stderr содержит `unknown option`.

2.2 Отсутствует обязательный аргумент → exit 2, stderr содержит `missing argument` и имя.

2.3 Невалидный JSON в `--from <file>` → exit 2, stderr `invalid JSON at line N`.

2.4 Файл из `--from <file>` не существует → exit 2, stderr `file not found`.

2.5 Без токена при `AUTH_MODE=jwt` → exit 3, stderr `not authenticated, run clite login`.

2.6 401 от сервера → exit 3, stderr `session expired, run clite login`.

2.7 403 от сервера → exit 4, stderr `forbidden: <reason>`.

2.8 5xx от сервера → exit 1, stderr содержит request-id.

2.9 Обрыв сети → exit 1, stderr `connection failed`.

## 3. clite create / get / update tasks

M2.28 удалил single-task мутации. M2.30 перевёл поверхность на verb-first (v2.0.0): все task-операции через `clite create tasks`, `clite get tasks`, `clite update tasks`. Просмотр одной задачи — `clite get tasks --filter 'id==<prefix>'`. Прямое шарингование задач после создания через CLI отсутствует — `user_shares`/`team_shares` задаются только в JSON-массиве `create tasks`.

### 3.1 create tasks — позитивные

3.1.1 Минимальный: `create tasks --bulk '[{"title":"T1"}]'` → exit 0; в `results[0].task_id` — SHA1. БД: задача создана, `status="open"`, assignee = текущий пользователь.

3.1.2 С описанием: `--bulk '[{"title":"T2","description_md":"## Hello"}]'` → exit 0. БД: `description_md = "## Hello"`.

3.1.3 С метками: `--bulk '[{"title":"T3","labels":["bug","urgent"]}]'` → exit 0. БД: `labels = ["bug","urgent"]`.

3.1.4 С блокирующей задачей: `--bulk '[{"title":"T4","blocked_by":["<sha-or-prefix>"]}]'` → exit 0. БД: запись в `task_blockers`.

3.1.5 Статус: `--bulk '[{"title":"T5","status":"done"}]'` → exit 0. БД: `status="done"`.

3.1.6 С прямым шарингом пользователю: `--bulk '[{"title":"T6","user_shares":[{"email":"x@x.com","perms":["edit_title","edit_status"]}]}]'` → exit 0. БД: запись в `task_user_shares`.

3.1.7 С шарингом команде: `"team_shares":[{"team_id":"<key>","perms":["edit_title"]}]` → exit 0. БД: запись в `task_team_shares`.

3.1.8 С проектом: `"projects":["<project-key>"]` → exit 0. БД: запись в `project_tasks` (требует `manage_projects` в проекте).

3.1.9 `--file tasks.json` — массив из JSON-файла. exit 0.

3.1.10 `--file tasks.csv` — header-row = поля; массивы `labels,projects,blocked_by` — `;`-separated в ячейке (PRD §7.7). exit 0.

3.1.11 `--batch` вместо `--bulk` — атомарная семантика (PRD §7.3): первая же ошибка → exit 2, ничего не создано.

### 3.2 create tasks — негативные

3.2.1 Без `--bulk` и `--batch` → exit 2, stderr `requires exactly one of --bulk or --batch`.

3.2.2 С `--bulk` и `--batch` одновременно → exit 2, stderr `--bulk and --batch are mutually exclusive`.

3.2.3 Без `title` в одном из элементов → в `--bulk` per-item `status=validation_failed`; в `--batch` exit 2.

3.2.4 `status` не из enum → per-item `validation_failed` в `--bulk` / exit 2 в `--batch`.

3.2.5 `blocked_by` с несуществующим ключом → per-item `not_found` в `--bulk` / exit 1 в `--batch`.

3.2.6 Anchor-rule нарушен: нет ни `projects`, ни `user_shares` с self, ни `team_shares` со своей командой (PRD §6.6) → per-item `validation_failed`.

3.2.7 `team_shares` с командой, в которой я не состою (PRD §6.7.1) → exit 4 forbidden.

3.2.8 `user_shares` с правом выше своего (PRD §6.1.7) → exit 4 `cannot grant above self`.

3.2.9 `projects` с проектом без `manage_projects` → exit 4.

3.2.10 Невалидный JSON в позиционном аргументе → exit 2, stderr `invalid JSON`.

3.2.11 `--file` указывает на несуществующий файл → exit 2 (см. 2.4).

3.2.12 `--file <p.csv>` с некорректным header (отсутствует `title`) → exit 2.

### 3.3 get tasks — позитивные

3.3.1 Без фильтра → первые 50 задач, отсортированы по `created_at asc` (PRD §7.1.1, §7.1.2).

3.3.2 `--filter "status==open"` → только open.

3.3.3 `--filter "labels=in=(bug,urgent)"` → задачи с хотя бы одной из меток.

3.3.4 `--filter "assignee==me"` → задачи на текущего пользователя (PRD §7.1.4).

3.3.5 `--cursor <opaque>` → следующая страница.

3.3.6 `--limit 100` → 100 элементов.

3.3.7 `--output json` → ответ в JSON.

3.3.8 `--fields id,title,status` → в выводе только указанные поля (PRD §7.9).

### 3.4 get tasks — негативные

3.4.1 `--filter "invalid syntax"` → exit 2, stderr `RSQL parse error at position N`.

3.4.2 `--filter "nonexistent_field==1"` → exit 2, stderr `unknown field 'nonexistent_field'`.

3.4.3 `--limit 201` → exit 2, stderr `limit must be <= 200`.

3.4.4 `--limit -1` → exit 2.

3.4.5 `--cursor "garbage"` → exit 2, stderr `invalid cursor`.

### 3.5 get tasks через `--filter` (вместо удалённого single-get) — позитивные

3.5.1 `get tasks --filter 'id==<existing-SHA1>'` → exit 0; `items` содержит ровно одну задачу.

3.5.2 `get tasks --filter 'id==<prefix>'` (4+ hex) → exit 0; `items` содержит все задачи с этим префиксом (LIKE-match, PRD §5.2.7).

3.5.3 `--fields id,title` — в выводе только указанные поля.

### 3.6 get tasks через `--filter` — негативные

3.6.1 Несуществующий ключ → exit 0, `items: []` (list-семантика).

3.6.2 Задача существует, но у меня нет прав → отсутствует в `items` (видимость, PRD §6.2).

### 3.7 update tasks — позитивные

3.7.1 `update tasks --filter "labels=in=(bug)" --set status=done --bulk` → exit 0; stdout содержит `results`, `total`, `succeeded`.

3.7.2 `--set title=X --set description_md=...` — комбинация полей.

3.7.3 `--set add_labels=urgent --bulk` — добавление метки без перезаписи остальных.

3.7.4 `--set remove_labels=bug --bulk` — удаление одной метки.

3.7.5 `--set labels=a,b --bulk` — полная перезапись массива меток (CSV).

3.7.6 `--set assignee=other@x.com --bulk` — назначение через email.

3.7.7 `--set projects=K1,K2 --bulk` — привязка задач к проектам (CSV) (PRD §7.6a).

3.7.8 `--set projects= --bulk` (пустое значение) — отвязка от всех проектов.

3.7.9 `--set add_blockers=K --bulk` / `--set remove_blockers=K --bulk` — управление блокирующими задачами.

3.7.10 Изменение одной конкретной задачи: `update tasks --filter 'id==<prefix>' --set status=done --bulk` (на смену удалённому single-update, PRD §7.6a.4).

3.7.11 `--batch` — атомарная семантика: либо все совпавшие задачи обновлены, либо ни одна (PRD §7.3.1).

### 3.8 update tasks — негативные

3.8.1 Без `--filter` → exit 2 (required).

3.8.2 Без `--set` → exit 2 (требуется ≥1).

3.8.3 Без `--bulk` и `--batch` → exit 2 (см. 3.2.1).

3.8.4 `--set unknown_field=v` → exit 2, stderr `unknown field 'unknown_field'`.

3.8.5 `--set status=invalid` → per-item `validation_failed` в `--bulk` / exit 2 в `--batch`.

3.8.6 Часть задач без прав в `--bulk` → exit 0; в `results` есть `forbidden`; остальные применены (PRD §7.2).

3.8.7 Часть задач без прав в `--batch` → exit 4, stderr `atomic batch failed on task <id>: forbidden`; БД не изменилась (PRD §7.3.2).

3.8.8 Фильтр охватывает >10 000 задач → exit 1, stderr `too_many_matches` (ARCH §9.3).

## 4. clite get log

История событий — `clite get log` с обязательным ровно одним из `--task <key>` или `--user <email|me>` (PRD §9.3, §9.4).

### 4.1 get log --task — позитивные

4.1.1 `get log --task <key>` → exit 0, до 50 событий, отсортированы по `created_at desc`.

4.1.2 `--cursor <opaque>` → следующая страница.

4.1.3 `--fields at,event_type,actor` → в выводе только указанные поля (PRD §7.9).

### 4.2 get log --task — негативные

4.2.1 Несуществующий ключ → exit 1.

4.2.2 Нет прав чтения задачи → exit 4 (PRD §6.1.8).

### 4.3 get log --user — позитивные

4.3.1 `get log --user me` → собственные события; работает и для свежезалогиненного пользователя (страница может быть пустой), и после действий — события появляются.

4.3.2 `get log --user other@x.com` → события другого пользователя, фильтруются по видимости: только те, чья цель доступна мне (ARCH §10.2.2).

### 4.4 get log --user — негативные

4.4.1 Email несуществующего пользователя → exit 1.

4.4.2 Ни `--task`, ни `--user` (или оба) → exit 2, stderr `provide exactly one of --task or --user`.

## 5. clite login / logout / me (M2+)

Magic-link click-flow (ARCH §4.2). Пользователь кликает по ссылке в письме; ввода кода в терминал нет. M2.30 переименовал `whoami` → `me`.

### 5.1 login — позитивные

5.1.1 `clite login` (интерактивный): запрашивает email на stdin → POST /api/auth/magic/start → печатает stderr `✉ Link sent to <email>. Click it from your inbox. Waiting…` → пользователь кликает по ссылке (e2e-тест дёргает confirm-эндпоинт напрямую) → CLI получает 200 от poll → stdout `success, press enter to continue` → пользователь жмёт Enter → exit 0. credentials.yaml создан.

5.1.2 `clite login --email <e>`: пропускает первый prompt → дальше как 5.1.1.

5.1.3 `clite login --email <e> --no-wait`: возвращается сразу после `magic/start`, печатает `login_session_id` на stdout, exit 0; используется в скриптах для дальнейшего ручного poll.

### 5.2 login — негативные

5.2.1 Невалидный email формат → exit 2, stderr `invalid email`.

5.2.2 Magic-link истёк (expires_in прошёл без клика) → exit 1, stderr `magic link expired, run clite login again`.

5.2.3 Сеть до auth-svc недоступна → exit 1, stderr `connection failed`.

5.2.4 SMTP_HOST не настроен в auth-svc → POST /api/auth/magic/start возвращает 500 `email_delivery_not_configured`; CLI exit 1, stderr `email delivery not configured on server` (ARCH §4.2.1.1).

5.2.5 SIGINT во время ожидания → exit 130; токен остаётся неиспользованным до истечения.

### 5.3 logout — позитивные

5.3.1 `clite logout` → exit 0, credentials.yaml удалён. (Серверная revoke — Post-MVP.)

5.3.2 `clite logout` без credentials → exit 0 (idempotent), stderr `already logged out`.

### 5.4 me — позитивные

5.4.1 `clite me` после логина → exit 0, stdout — email (из локальных credentials).

### 5.5 me — негативные

5.5.1 Без credentials → exit 3, stderr `not authenticated, run clite login`.

## 6. clite team (M2+)

Команда в verb-first surface: `create team`, `get teams`/`get team <key>`, `rename team`, `leave team`, `add member <team-key>` (универсальная команда добавления для команд и проектов с авто-детектом контейнера по ключу).

### 6.1 create team — позитивные

6.1.1 `clite create team --name "Eng"` → exit 0, stdout — SHA1-ключ. БД: команда создана, создатель — единственный участник с правами `edit_team_name, manage_member_permissions`. Созданная команда видна в `clite get teams` (PRD §6.1.8).

### 6.2 add member (team) — позитивные

6.2.1 `clite add member <team-key> --email x@y.com --perm edit_team_name` → exit 0. БД: запись в `team_members`. Изменение существующего: повторный вызов с новым перм-набором заменяет флаги; пустой `--perm` (без флагов) удаляет участника (PRD §6.1.3).

### 6.3 add member (team) — негативные

6.3.1 Без права `manage_member_permissions` → exit 4.

6.3.2 `--perm` выше своих (PRD §6.1.7) → exit 4, stderr `cannot grant above self`.

6.3.3 Невалидный perm-флаг → exit 2.

6.3.4 Несуществующий email — резолвится через auth-svc; если пользователь ещё не зарегистрирован — он автоматически создаётся при добавлении (PRD §10.4).

### 6.4 leave team — позитивные

6.4.1 `clite leave team <key>` → exit 0 (PRD §7.8.2); я больше не участник. Если был единственным — команда удалена каскадом (PRD §6.1.6) и недоступна в `get team <key>` (404).

### 6.5 get team / get teams — позитивные

6.5.1 `get teams` → exit 0, мои команды (PRD §6.1.8).

6.5.2 `get team <key-or-prefix>` → exit 0, имя + участники с перм-флагами.

6.5.3 `--fields id,name` — в выводе только указанные поля (PRD §7.9).

### 6.6 rename team

6.6.1 `clite rename team <key> --to "NewName"` → exit 0. Требуется `edit_team_name`.

6.6.2 Без `edit_team_name` → exit 4.

## 7. clite project (M2+)

Проект в verb-first surface: `create project`, `get projects`/`get project <key>`, `rename project`, `leave project`, `add member <project-key>` (универсальная команда добавления). Привязка задач к проекту — через `update tasks --set projects=...` (PRD §7.6a).

### 7.1 create project — позитивные

7.1.1 `clite create project --name "P1"` → exit 0, stdout — SHA1-ключ. БД: я единственный участник со всеми правами проекта (PRD §6.5).

### 7.2 add member (project)

7.2.1 Позитив: `clite add member <project-key> --email x@y.com --perm edit_project_name --perm manage_member_permissions` → exit 0. БД: запись в `project_user_members`. Добавление команды: `--team <team-key>` вместо `--email` → запись в `project_team_members` (требует, чтобы я был в этой команде, PRD §6.7.2). Удаление участника: вызов без `--perm` (пустой массив) → запись удаляется.

7.2.2 Негатив без `manage_member_permissions` → exit 4. `--perm` выше своих → exit 4 (PRD §6.1.7). Добавление команды, в которой я не состою → exit 4 (PRD §6.7.2).

### 7.3 Привязка задач к проекту через `update tasks`

7.3.1 `update tasks --filter 'id==<prefix>' --set projects=<project-key> --bulk` → exit 0; задача добавлена в `project_tasks` (требует `manage_projects` в проекте).

7.3.2 Отвязка: `update tasks --filter 'id==<prefix>' --set projects= --bulk` (пустое значение) → задача удалена из всех проектов.

7.3.3 Без `manage_projects` в указанном проекте → per-item `forbidden` в `--bulk` / exit 4 в `--batch`.

### 7.5 leave project — позитивные

7.5.1 `clite leave project <key>` → exit 0 (PRD §7.8.3); я больше не участник. Задачи, видимые мне исключительно через этот проект, становятся недоступны. Если был единственным — проект удалён каскадом (PRD §6.1.6).

### 7.6 get project / get projects — позитивные

7.6.1 `get projects` → exit 0, мои проекты (PRD §6.1.8).

7.6.2 `get project <key-or-prefix>` → exit 0, имя + участники с перм-флагами + `task_ids` (видимые мне, PRD §6.2).

7.6.3 `--fields id,name` — фильтрация полей.

### 7.7 rename project

7.7.1 `clite rename project <key> --to "NewName"` → exit 0. Требуется `edit_project_name`.

7.7.2 Без `edit_project_name` → exit 4.

## 8. clite share (удалён в M2.30)

8.1 В v2.0.0 группа `clite share` удалена. Шаринг задач задаётся **только в момент создания** через JSON-массив `create tasks` — поля `user_shares` и `team_shares` (см. §3.1.6, §3.1.7).

8.2 Backend-эндпоинты `POST/DELETE /v1/tasks/{task_id}/share/...` физически остались (см. `tasks_service/routers/shares.py`), но CLI-обёртки нет. Modify-share после создания возможен только через прямые HTTP-запросы — не входит в supported surface.

8.3 Self-revoke прямого шаринга задачи (PRD §7.8.1) — соответствующей CLI-команды в v2.0.0 нет; для управления членством используются `leave team` (§6.6) и `leave project` (§7.7).

## 9. clite automation (M3+)

### 9.1 automation create — позитивные

9.1.1 Cron-триггер: `--project <key> --name "morning" --cron "0 9 * * *" --action-type webhook --action-url ... --action-body "..."` → exit 0, SHA1-ключ.

9.1.2 Event-триггер: `--event-type task.status_changed --filter "status==done" --action-type system_method --action-method tasks.list --action-args ...`.

9.1.3 С секретом в шаблоне: action-body содержит `{{secrets.token}}` и в БД есть secret `token` → exit 0.

### 9.2 automation create — негативные

9.2.1 Без `manage_automations` в проекте → exit 4.

9.2.2 Невалидный cron → exit 2 `invalid cron expression`.

9.2.3 Невалидный RSQL в filter → exit 2.

9.2.4 system_method не в whitelist → exit 2 `method not allowed` (ARCH §11.4).

9.2.5 Ссылка на несуществующий secret → exit 2 `unknown secret <name>`.

### 9.3 automation run-now — позитивные

9.3.1 `clite automation run-now <key>` → запускает action немедленно вне триггера; exit 0, stdout — результат action.

### 9.4 automation delete — позитивные

9.4.1 exit 0, в БД помечена удалённой; pending webhook_outbox-задачи отменяются.

## 10. clite secret (M3+)

### 10.1 secret set — позитивные

10.1.1 `clite secret set --project <key> --name token --value <plain>` → exit 0; в БД `value_encrypted`.

10.1.2 Перезапись существующего → exit 0.

### 10.2 secret set — негативные

10.2.1 Без `manage_secrets` → exit 4.

### 10.3 secret list — позитивные

10.3.1 `clite secret list --project <key>` → exit 0, перечислены имена БЕЗ значений.

### 10.4 secret delete — позитивные

10.4.1 exit 0, БД: секрет удалён; автоматизации, ссылающиеся на него, на следующий запуск получат ошибку рендера.
