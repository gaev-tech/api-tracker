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

1.3.1 Default — table при TTY, json при пайпе.

1.3.2 `--output json` принудительно JSON.

1.3.3 `--output table` принудительно table.

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

## 3. clite task

### 3.1 task create — позитивные

3.1.1 Минимальный: `--title "T1"` без других полей. exit 0. stdout содержит SHA1-ключ. БД: задача создана со статусом `open`, assignee = SOLO_USER (M1) или текущий пользователь (M2+).

3.1.2 С описанием: `--title "T2" --description "## Hello"`. exit 0. БД: `description_md = "## Hello"`.

3.1.3 С метками: `--title "T3" --label bug --label urgent`. exit 0. БД: `labels = ["bug", "urgent"]`.

3.1.4 С блокирующей задачей: `--title "T4" --blocked-by <key или префикс существующей задачи>`. exit 0. БД: запись в `task_blockers`.

3.1.5 Статус: `--title "T5" --status done`. exit 0. БД: `status = "done"`.

3.1.6 stdin JSON: `echo '{"title":"T6","labels":["x"]}' | clite task create -`. exit 0. БД: задача создана.

3.1.7 С шарингом (M2+): `--title "T7" --share-user other@x.com:edit_title,edit_status`. exit 0. БД: запись в `task_user_shares`.

3.1.8 С командой (M2+): `--title "T8" --share-team <key команды, в которой я>:edit_title`. exit 0.

3.1.9 С проектом (M2+): `--title "T9" --project <key проекта, в котором у меня manage_projects>`. exit 0.

### 3.2 task create — негативные

3.2.1 Без `--title` → exit 2, stderr `title required`.

3.2.2 `--status invalid_value` → exit 2, stderr `status must be one of open|done|archived`.

3.2.3 `--blocked-by` с несуществующим ключом → exit 1, stderr `task not found: <key>`.

3.2.4 `--label ""` пустая строка → exit 2, stderr `label cannot be empty`.

3.2.5 `--label` с дубликатом → exit 2, stderr `duplicate label`.

3.2.6 (M2+) Anchor-rule нарушен: `--title "X"` без `--project`, `--share-user`, `--share-team`. exit 2, stderr `task must have at least one anchor: --project, --share-user (with self), or --share-team (with own team)`.

3.2.7 (M2+) `--share-team` с командой, в которой я не состою → exit 4, stderr `forbidden: not a team member`.

3.2.8 (M2+) `--share-user other@x.com:<perm-выше-моих>` → exit 4, stderr `cannot grant permission higher than your own`.

3.2.9 (M2+) `--project` с проектом, в котором нет `manage_projects` → exit 4.

### 3.3 task list — позитивные

3.3.1 Без фильтра → первые 50 задач, отсортированы по `created_at asc`.

3.3.2 `--filter "status==open"` → только open.

3.3.3 `--filter "labels=in=(bug,urgent)"` → пересечение по меткам.

3.3.4 `--filter "assignee==me"` → задачи на текущего пользователя.

3.3.5 `--cursor <opaque>` → следующая страница.

3.3.6 `--limit 100` → 100 элементов.

3.3.7 `--output json` → ответ в JSON.

3.3.8 `--fields id,title,status` → table/json содержит только эти три колонки; остальные поля задачи опущены.

### 3.4 task list — негативные

3.4.1 `--filter "invalid syntax"` → exit 2, stderr `RSQL parse error at position N`.

3.4.2 `--filter "nonexistent_field==1"` → exit 2, stderr `unknown field 'nonexistent_field'`.

3.4.3 `--limit 201` → exit 2, stderr `limit must be <= 200`.

3.4.4 `--limit -1` → exit 2.

3.4.5 `--cursor "garbage"` → exit 2, stderr `invalid cursor`.

### 3.5 task get — позитивные

3.5.1 `clite task get <existing SHA1>` (полный 40-символьный ключ) → exit 0, вывод с полями задачи.

3.5.2 `clite task get <unique prefix>` (4+ hex-символов, единственное совпадение) → exit 0, вывод задачи (PRD §5.2.7.2).

3.5.3 `clite task get <existing SHA1> --fields id,title` → exit 0, в выводе только `id` и `title`.

### 3.6 task get — негативные

3.6.1 Несуществующий ключ → exit 1, stderr `task not found`.

3.6.2 (M2+) Задача существует, но у меня нет прав → exit 4 (или 1 task_not_found — окончательное решение фиксируется в M2).

3.6.3 Префикс соответствует нескольким задачам → exit 1, stderr `ambiguous prefix '<p>', candidates:\n  <sha1>  "<title>"\n  <sha1>  "<title>"` (PRD §5.2.7.3, TC §1.4.4).

3.6.4 Префикс короче 4 символов → exit 2, stderr `prefix too short (min 4 chars)` (TC §1.4.2).

### 3.7 task update — позитивные

3.7.1 `--title "new"` → exit 0. БД: title обновлён, audit_event с диффом.

3.7.2 `--status done`, `--assignee email@x.com` → exit 0.

3.7.3 `--add-label x --remove-label y` → exit 0.

3.7.4 `--add-blocker <key>` → exit 0.

### 3.8 task update — негативные

3.8.1 (M2+) Нет права `edit_title` → exit 4.

3.8.2 `--status invalid` → exit 2.

### 3.9 task bulk-update — позитивные

3.9.1 `--filter "labels=in=(bug)" --set status=done` → exit 0. stdout: `results: [...]`, `total = N`, `succeeded = K`.

3.9.2 Все попавшие задачи мне доступны → `succeeded == total`.

### 3.10 task bulk-update — негативные

3.10.1 (M2+) Часть задач без прав → exit 0, в `results` есть `forbidden`-записи; остальные применены.

3.10.2 Фильтр охватывает >10000 задач → exit 1, stderr `too_many_matches` (ARCH §9.3).

3.10.3 Невалидный `--set field=value` (тип не совпадает) → exit 2.

### 3.11 task batch-update — позитивные

3.11.1 `--filter ... --set ...` со всеми доступными мне задачами → exit 0, все обновлены.

### 3.12 task batch-update — негативные

3.12.1 (M2+) Хотя бы одна задача в выборке без прав → exit 4, stderr `atomic batch failed on task <id>: forbidden`. Состояние БД не изменилось.

3.12.2 Невалидное значение для одной из задач → exit 2, ничего не изменилось.

### 3.13 task bulk-create — позитивные

3.13.1 `--from tasks.json` с массивом из N валидных задач → exit 0, stdout — массив `results` с per-item статусом.

### 3.14 task bulk-create — негативные

3.14.1 Одна из задач не имеет якоря → exit 0, в `results` для этой задачи `status = validation_failed`.

3.14.2 Невалидный JSON → exit 2 (см. 2.3).

### 3.15 task batch-create

3.15.1 Все валидны → exit 0, все созданы.

3.15.2 Одна не валидна → exit 2, ничего не создано.

## 4. clite history

### 4.1 history task — позитивные

4.1.1 `clite history task <key>` → exit 0, до 50 событий, отсортированы по `created_at desc`.

4.1.2 С курсором → следующая страница.

### 4.2 history task — негативные

4.2.1 Несуществующий ключ → exit 1.

4.2.2 (M2+) Нет прав чтения задачи → exit 4.

### 4.3 history user (M2+) — позитивные

4.3.1 `clite history user me` → собственные события.

4.3.2 `clite history user other@x.com` → события другого пользователя, только те, что касаются доступных мне задач (ARCH §10.2.2).

### 4.4 history user (M2+) — негативные

4.4.1 Email несуществующего пользователя → exit 1.

## 5. clite login / logout / whoami (M2+)

Magic-link click-flow (ARCH §4.2). Пользователь кликает по ссылке в письме; ввода кода в терминал нет.

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

5.3.2 `clite logout` без credentials → exit 0, stderr `already logged out`.

### 5.4 whoami — позитивные

5.4.1 `clite whoami` после логина → exit 0, stdout — email.

### 5.5 whoami — негативные

5.5.1 Без credentials → exit 3, stderr `not authenticated, run clite login`.

## 6. clite team (M2+)

### 6.1 team create — позитивные

6.1.1 `clite team create --name "Eng"` → exit 0, stdout SHA1-ключ. БД: команда создана, создатель — единственный участник с правами `edit_team_name, manage_member_permissions`.

### 6.2 team member set — позитивные

6.2.1 `clite team member set <team-key> --email x@y.com --perms edit_team_name` → exit 0.

### 6.3 team member set — негативные

6.3.1 Без права `manage_member_permissions` → exit 4.

6.3.2 `--perms` выше своих → exit 4 `cannot grant above self`.

### 6.4 team leave — позитивные

6.4.1 `clite team leave <key>` → exit 0, я больше не участник.

6.4.2 Был единственным участником → команда удалена (cascade, PRD §6.1.6).

## 7. clite project (M2+)

### 7.1 project create — позитивные

7.1.1 `clite project create --name P1` → exit 0, SHA1-ключ. БД: я единственный участник со всеми правами.

### 7.2 project member set

7.2.1 Позитив: добавление с непустыми правами → exit 0.

7.2.2 Негатив без `manage_member_permissions` → exit 4.

7.2.3 `--perms` выше своих → exit 4.

### 7.3 project task add/remove — позитивные

7.3.1 Добавление задачи в проект при `manage_projects` → exit 0. БД: запись в `project_tasks`.

7.3.2 Удаление задачи из проекта при `manage_projects` → exit 0.

### 7.4 project task add — негативные

7.4.1 Без `manage_projects` → exit 4.

### 7.5 project leave — позитивные

7.5.1 Выход с потерей доступа ко всем задачам проекта, если не было прямого шаринга.

## 8. clite share (M2+)

### 8.1 share user set — позитивные

8.1.1 `clite share user set <task-key> --email x@y.com --perms edit_title,edit_status` → exit 0.

### 8.2 share user set — негативные

8.2.1 Без права `share` на задаче → exit 4.

8.2.2 `--perms` выше своих → exit 4.

### 8.3 share team set — позитивные

8.3.1 Шаринг команде, в которой я состою → exit 0.

### 8.4 share team set — негативные

8.4.1 Шаринг команде, в которой я НЕ состою → exit 4 (PRD §6.7.1).

### 8.5 share remove — позитивные

8.5.1 Self-revoke: `clite share user remove <task-key> --self` → exit 0.

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
