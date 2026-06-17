# Тарифная сетка

Все ссылки вида (PRD §X) — на `product.md`. (ARCH §Y) — на `architecture.md`.

## 1. Назначение

1.1 Эта спека описывает per-user тарифы, метрики лимитов, механику фриза permission-записей и платёжный flow через ЮКассу.

1.2 Заменяет PRD §12.1: тарифные лимиты и фриз больше не PostMVP, реализуются по этой спеке.

1.3 Монетизация — per-user подписка с биллингом в RUB через ЮКассу.

1.4 Концепция workspace/организации не вводится; PRD §4.1 сохраняется (все пользователи равноправны).

## 2. Каталог тарифов

2.1 Три тарифа: `free`, `pro`, `max`.

2.2 Идентификаторы тиров в API и CLI: `free`, `pro`, `max`.

2.3 Валюта — только RUB.

2.4 Литерал unlimited в JSON-ответах — `null`. В человеко-читаемом выводе CLI — `∞`.

2.5 Free

2.5.1 `task_shares` = 200.

2.5.2 `projects` = 3.

2.5.3 `teams` = 3.

2.5.4 Цены нет.

2.6 Pro

2.6.1 `task_shares` = ∞.

2.6.2 `projects` = 10.

2.6.3 `teams` = 10.

2.6.4 `monthly_rub` = 99.

2.6.5 `annual_rub` = 990.

2.7 Max

2.7.1 `task_shares` = ∞.

2.7.2 `projects` = ∞.

2.7.3 `teams` = ∞.

2.7.4 `monthly_rub` = 499.

2.7.5 `annual_rub` = 4990.

2.8 Годовая цена = месячная × 10 (по умолчанию во всех тарифах с ценой).

2.9 Каталог хардкодится в коде auth-svc; отдельной таблицы каталога в БД нет.

## 3. Метрики счёта

3.1 `task_shares(U)` = `count(TaskUserShare WHERE user_id=U AND frozen=false)`.

3.2 `projects(U)` = `count(ProjectUserMember WHERE user_id=U AND frozen=false)`.

3.3 `teams(U)` = `count(TeamMember WHERE user_id=U AND frozen=false)`.

3.4 В метрики НЕ входят:

3.4.1 Доступы через `TaskTeamShare` (учитываются неявно через `teams`).

3.4.2 Доступы через `ProjectTeamMember` (учитываются неявно через `teams`).

3.4.3 Frozen-записи (см. §5).

3.5 Создание команды/проекта/задачи добавляет создателя в соответствующую permission-таблицу как первого участника (см. PRD §6.1.5, §6.6); эта запись считается наравне с любой другой.

3.6 Параллельный учёт путей доступа: если задача доступна одновременно через `TaskUserShare(T, U)` и через `ProjectUserMember(P, U)` для какого-то проекта P, содержащего T (PRD §6.2.1) — обе записи входят в счёт каждая в свой бакет.

## 4. Hard reject в норме

4.1 При попытке создать новую permission-запись, которая превысит лимит по соответствующей метрике для адресата — операция отклоняется с ошибкой `tariff_limit_exceeded`.

4.2 Точки контроля:

4.2.1 `team create` — проверяется `teams` создателя.

4.2.2 `team share user add` — проверяется `teams` приглашаемого.

4.2.3 `project create` — проверяется `projects` создателя.

4.2.4 `project share user add` — проверяется `projects` приглашаемого.

4.2.5 `task create` — для каждого `user_shares[i]` (включая самого создателя, если он в списке по PRD §6.6.1.2) проверяется `task_shares` упомянутого пользователя.

4.2.6 `task share user add` — проверяется `task_shares` адресата.

4.3 В bulk-семантике (PRD §7.2): ошибка отдаётся per-item в массиве `results` со статусом `tariff_limit_exceeded` (поля — см. §17.1.1).

4.4 В batch-семантике (PRD §7.3): первая же ошибка `tariff_limit_exceeded` откатывает всю операцию, как любая другая ошибка.

4.5 Проверка лимита атомарна с INSERT в одной транзакции (см. §18.5).

## 5. Frozen-записи

5.1 Permission-таблицы получают колонку `frozen: bool NOT NULL DEFAULT false`:

5.1.1 `tasks.task_user_shares.frozen`.

5.1.2 `tasks.project_user_members.frozen`.

5.1.3 `tasks.team_members.frozen`.

5.2 Семантика `frozen=true` для permission-записи `(entity, user)`:

5.2.1 Path A через frozen `TaskUserShare` не даёт доступа U к задаче (PRD §6.2.1.1 модифицируется: «не-frozen TaskUserShare»).

5.2.2 Path B через frozen `ProjectUserMember` не даёт U доступа к задачам проекта (PRD §6.2.1.2 модифицируется аналогично).

5.2.3 Frozen `TeamMember(team, U)` — U не получает ни прямого участия в команде, ни транзитивного доступа к задачам через `TaskTeamShare(_, team)` или `ProjectTeamMember(_, team)`.

5.3 Видимость владельцу:

5.3.1 Frozen-запись видна владельцу в соответствующих list-командах CLI только с флагом `--include-frozen` (см. §15.15).

5.3.2 В ответе list-команды добавляется поле `frozen: bool` всегда (и для active, и для frozen-записей).

5.3.3 По умолчанию `--include-frozen=false`; frozen-записи исключены.

5.3.4 get-команды (`team get`, `project get`) — frozen-запись доступна по ключу всегда, поле `frozen: true` в ответе.

5.4 Видимость другим участникам:

5.4.1 Другие участники команды/проекта НЕ видят, что данный пользователь frozen; для них он значится обычным участником.

5.4.2 Это означает, что frozen-юзер появляется в `share user list`/`project list members`/`team list members` у других — но реально не имеет доступа.

5.5 Self-revoke (PRD §6.1.4) на frozen-записи разрешён и эквивалентен полному удалению с каскадами PRD §6.1.6.

5.6 Frozen не блокирует операции других участников и не нарушает их инвариантов PRD §6.1.7.

## 6. Алгоритм freeze/unfreeze

6.1 Триггер freeze — снижение лимита по любой метрике, после которого `count(active) > new_limit`.

6.2 Алгоритм freeze:

6.2.1 Берётся множество permission-записей пользователя по метрике с `frozen=false`.

6.2.2 Сортировка по `created_at` permission-записи по убыванию (новейшие — первые).

6.2.3 Первые `count(active) - new_limit` записей получают `frozen=true`.

6.3 Триггер unfreeze (FIFO) — освобождение слота среди активных:

6.3.1 Self-revoke не-frozen permission-записи.

6.3.2 Upgrade на тариф с большим лимитом.

6.4 Алгоритм unfreeze:

6.4.1 Берётся множество permission-записей пользователя по метрике с `frozen=true`.

6.4.2 Сортировка по `created_at` по возрастанию (старейшие — первые).

6.4.3 Первые `min(active_slots_freed, count(frozen))` записей получают `frozen=false`.

6.5 Симметрия: freeze — LIFO, unfreeze — FIFO. Это даёт детерминированный результат правила «лимит = N самых старых активных».

6.6 Точки запуска RecomputeFreezeForUser (см. §18.3):

6.6.1 Любое изменение `tariff` пользователя.

6.6.2 Любое изменение `tariff_until` пользователя.

6.6.3 `tariff_bank_consumed`, `tariff_downgraded`, `tariff_upgraded`.

## 7. Состояние подписки в auth.users

7.1 Колонки, добавляемые в `auth.users`:

7.1.1 `tariff text NOT NULL DEFAULT 'free'` ∈ `{free, pro, max}`.

7.1.2 `tariff_until timestamptz NULL` — `NULL` для `tariff=free`; для остальных — конец оплаченного периода.

7.1.3 `tariff_auto_renew bool NOT NULL DEFAULT false`.

7.1.4 `pro_bank_days int NOT NULL DEFAULT 0` с `CHECK (pro_bank_days >= 0)`.

7.1.5 `payment_method_token text NULL` — токен ЮКассы; хранится в открытом виде (это идентификатор, не секрет PCI).

7.1.6 `payment_method_last4 text NULL` — последние 4 цифры карты.

7.1.7 `payment_method_brand text NULL` — бренд карты (`visa`, `mastercard`, `mir` и т.д.).

7.2 У свежезарегистрированного пользователя (PRD §10.4) все поля принимают DEFAULT-значения.

## 8. Auto-renew и истечение

8.1 Auto-renew списание запускается auth-svc'ом за N часов до `tariff_until` (значение N — реализационная деталь, спека не фиксирует).

8.2 При успехе списания:

8.2.1 `tariff_until += 1 period` (period = monthly | annual в зависимости от того, что было оплачено в последний раз).

8.2.2 Событие `tariff_renewed` с полями `payment_id`, `amount_rub`, `period`.

8.3 При неудаче списания:

8.3.1 Мгновенный фазовый переход в `tariff_until` (см. §12.6–12.8 для bank-логики).

8.3.2 Событие `tariff_renew_failed` с полем `error_code`.

8.4 Grace-периода нет (см. §20.1.1).

8.5 После `tariff cancel`:

8.5.1 Auto-renew не запускается.

8.5.2 В момент `tariff_until` происходит фазовый переход (см. §12.6–12.8).

8.5.3 Возвратов средств нет.

## 9. Upgrade flow

9.1 Команда CLI: `clite tariff upgrade <pro|max> --period <monthly|annual>`.

9.2 Шаги:

9.2.1 CLI шлёт `POST /api/auth/me/tariff/upgrade` с телом `{tier, period}`.

9.2.2 auth-svc валидирует: `tier` строго выше `current_tariff` по порядку `free < pro < max`. Иначе `tariff_not_an_upgrade`.

9.2.3 auth-svc создаёт payment intent в ЮКассе.

9.2.4 Ответ CLI: `{confirmation_url, payment_id}`.

9.2.5 CLI открывает `confirmation_url` в браузере (симметрично login-flow PRD §10.5).

9.2.6 После успешного колбэка от ЮКассы (см. §14) CLI печатает на stdout `success, press enter to continue` (см. PRD §10.5).

9.2.7 Пользователь жмёт Enter, CLI завершает команду.

9.3 Обработка успешного webhook от ЮКассы в auth-svc:

9.3.1 Если `current_tariff=pro AND target_tier=max AND tariff_until > now` → credit банка (см. §12.2–12.5).

9.3.2 `tariff = target_tier`.

9.3.3 `tariff_until = now + period` (1 месяц или 1 год от момента подтверждения).

9.3.4 `tariff_auto_renew = true`.

9.3.5 Сохранение `payment_method_token` (новый или подтверждение существующего), `payment_method_last4`, `payment_method_brand` из ответа ЮКассы.

9.3.6 Запись события `tariff_upgraded` с `from`, `to`, `period`, `amount_rub`, `payment_id`.

9.3.7 Вызов `RecomputeFreezeForUser` в tasks-svc (см. §18.3). Это размораживает frozen-записи, если новый тариф позволяет.

9.4 Ошибки upgrade:

9.4.1 `tariff_not_an_upgrade` — попытка перейти на текущий или нижний тариф.

9.4.2 `payment_declined` — ЮКасса отклонила списание.

## 10. Cancel

10.1 Команда CLI: `clite tariff cancel`.

10.2 Шаги:

10.2.1 CLI шлёт `POST /api/auth/me/tariff/cancel`.

10.2.2 auth-svc валидирует: `tariff != free` И `tariff_auto_renew = true`.

10.2.3 `tariff_auto_renew = false`.

10.2.4 `tariff` и `tariff_until` остаются прежними.

10.2.5 `payment_method_*` остаются прежними (для возможного повторного upgrade без повторного ввода карты).

10.2.6 Событие `tariff_cancelled`.

10.3 Ошибки cancel:

10.3.1 `tariff_not_active` — `tariff=free`.

10.3.2 `tariff_already_cancelled` — `tariff_auto_renew=false`.

10.4 Прямой `tariff downgrade <lower>` мид-периодом — не поддерживается (см. §20.2.1, §20.2.2).

## 11. Bank of Pro days

11.1 Поле `pro_bank_days` (см. §7.1.4) — целое неотрицательное число дней Pro, ожидающих активации.

11.2 Триггер credit: upgrade `pro → max` (§9.3) при `tariff_until > now`.

11.3 Формула credit: `credit = ceil((tariff_until - now).total_seconds() / 86400)`.

11.4 Применение: `pro_bank_days += credit`.

11.5 Событие `tariff_bank_credited` с полями `days_credited`, `new_bank_total`.

11.6 Триггер consume: фазовый переход в момент `tariff_until` при `tariff = max`, когда auto-renew не сработал (отменён или провалился).

11.7 Если `pro_bank_days > 0`:

11.7.1 `tariff = pro`.

11.7.2 `tariff_until = now + pro_bank_days * 1 day`.

11.7.3 `pro_bank_days = 0`.

11.7.4 `tariff_auto_renew = false` (банковая Pro-фаза не наследует auto-renew; после неё всегда Free).

11.7.5 Событие `tariff_bank_consumed` с полями `days_consumed`, `new_tariff_until`.

11.7.6 Вызов `RecomputeFreezeForUser`.

11.8 Иначе (`pro_bank_days = 0`): обычный downgrade на Free.

11.8.1 `tariff = free`.

11.8.2 `tariff_until = NULL`.

11.8.3 `tariff_auto_renew = false`.

11.8.4 Событие `tariff_downgraded` с `from`, `to=free`, `reason: expired|payment_failed`.

11.8.5 Вызов `RecomputeFreezeForUser`.

11.9 По окончании банковой Pro-фазы (`tariff_until` истекает при `tariff=pro AND tariff_auto_renew=false AND pro_bank_days=0`) — обычный downgrade на Free (§11.8.1–11.8.5).

11.10 Накопление многократное: bank может пополняться при каждом upgrade `pro → max`; верхнего лимита нет.

11.11 Ограничения банка:

11.11.1 Только Pro дни (Max нельзя банковать, так как нет «выше Max»).

11.11.2 Активация вручную «прямо сейчас на Max» — отсутствует.

11.11.3 Покупка Pro поверх Max для пополнения банка — запрещена правилом §9.2.2 (Pro не выше Max).

11.11.4 Конвертация банка в деньги — отсутствует.

11.11.5 Передача банка другому пользователю — отсутствует.

## 12. Payment method

12.1 Привязка карты происходит в рамках первого успешного upgrade (см. §9.3.5).

12.2 Просмотр: `GET /api/auth/me/payment-method` → `{present: bool, last4?: string, brand?: string}`.

12.3 Обновление: `POST /api/auth/me/payment-method` — flow аналогичен upgrade (§9.2):

12.3.1 auth-svc создаёт verification intent в ЮКассе (типовая «проверка карты» — pre-auth с автореверсом, без реального списания).

12.3.2 Ответ CLI: `{confirmation_url, payment_id}`.

12.3.3 CLI открывает URL в браузере, печатает `success, press enter to continue` после колбэка.

12.3.4 Webhook от ЮКассы → auth-svc заменяет `payment_method_token`, `payment_method_last4`, `payment_method_brand`. Старый токен инвалидируется на стороне ЮКассы.

12.3.5 Событие `payment_method_updated`.

12.4 Удаление: `DELETE /api/auth/me/payment-method`.

12.4.1 Очищает `payment_method_token`, `payment_method_last4`, `payment_method_brand` (`NULL`).

12.4.2 Имплицитно `tariff_auto_renew = false`.

12.4.3 `tariff_until` сохраняется — оплаченный период не теряется.

12.4.4 Событие `payment_method_removed`.

12.4.5 Если `tariff_auto_renew` переключился `true → false` — дополнительно событие `tariff_cancelled`.

12.5 Ошибки update:

12.5.1 `tariff_not_active` — `tariff = free`.

12.5.2 `payment_method_verification_failed` — ЮКасса отклонила верификацию.

12.6 Ошибки remove:

12.6.1 `tariff_not_active` — `tariff = free`.

12.6.2 `payment_method_absent` — карта уже не привязана.

12.7 Одна карта на пользователя (мульти-карты — см. §20.1.5).

12.8 Сверх `last4` и `brand` никакие метаданные карты не доступны (см. §20.1.6).

12.9 Отличие cancel (§10) от payment-method remove (§12.4): cancel сохраняет карту для возможного повторного upgrade без повторного ввода; remove очищает карту полностью.

## 13. ЮКасса webhook

13.1 Эндпоинт: `POST /api/auth/payments/yookassa-callback`.

13.2 Валидация HMAC-подписи по shared secret из заголовка запроса; невалидная подпись → `401`.

13.3 Идемпотентность по `payment_id` — повторный webhook с тем же `payment_id` не дублирует state transition.

13.4 Маршрутизация по контексту платежа (`metadata.purpose`):

13.4.1 `upgrade` — применяется flow §9.3.

13.4.2 `payment_method_verification` — применяется flow §12.3.4.

13.4.3 `renewal` — применяется flow §8.2 (успех) или §8.3 (отказ).

## 14. История платёжных событий

14.1 Хранятся в новой таблице `auth.payment_events`:

14.1.1 `id CHAR(40) PRIMARY KEY` — SHA1, генератор как в ARCH §3.7.5.

14.1.2 `user_id CHAR(40) NOT NULL`.

14.1.3 `event_type text NOT NULL`.

14.1.4 `payload_json jsonb NOT NULL`.

14.1.5 `created_at timestamptz NOT NULL DEFAULT now()`.

14.1.6 Индекс по `(user_id, created_at desc)`.

14.2 Типы событий:

14.2.1 `tariff_upgraded` — поля `from`, `to`, `period`, `amount_rub`, `payment_id`.

14.2.2 `tariff_renewed` — поля `tier`, `period`, `amount_rub`, `payment_id`.

14.2.3 `tariff_renew_failed` — поле `error_code`.

14.2.4 `tariff_downgraded` — поля `from`, `to`, `reason: expired|payment_failed`.

14.2.5 `tariff_cancelled` — без дополнительных полей.

14.2.6 `tariff_bank_credited` — поля `days_credited`, `new_bank_total`.

14.2.7 `tariff_bank_consumed` — поля `days_consumed`, `new_tariff_until`.

14.2.8 `payment_method_updated` — поля `last4`, `brand`.

14.2.9 `payment_method_removed` — без дополнительных полей.

14.3 Видимость: только владельцу через `clite tariff payments` (см. §15.5).

14.4 Пагинация курсорная, лимит фиксированный 50 (симметрично PRD §9.5).

14.5 Сортировка `created_at desc` (новейшие первые).

14.6 RSQL по `auth.payment_events` не поддерживается (симметрично PRD §9.6).

## 15. CLI команды

15.1 `clite tariff show` — выводит текущее состояние тарифа пользователя (auth обязателен).

15.2 `clite tariff catalog` — выводит каталог тарифов (см. §2); public, без auth.

15.3 `clite tariff upgrade <pro|max> --period <monthly|annual>` — flow §9 (auth обязателен).

15.4 `clite tariff cancel` — flow §10 (auth обязателен).

15.5 `clite tariff payments` — пагинированный список платёжных событий (auth обязателен).

15.6 `clite tariff payment-method show` — выводит инфо о карте.

15.7 `clite tariff payment-method update` — flow §12.3 (auth обязателен).

15.8 `clite tariff payment-method remove` — flow §12.4 (auth обязателен).

15.9 Все команды поддерживают флаг `--fields` (PRD §7.9.1) и рендерятся line-by-line `field: value` (PRD §7.9.4).

15.10 Поля `tariff show` (дефолтный набор):

15.10.1 `tariff`, `tariff_until`, `auto_renew`, `pro_bank_days`.

15.10.2 `usage_task_shares`, `limit_task_shares`.

15.10.3 `usage_projects`, `limit_projects`.

15.10.4 `usage_teams`, `limit_teams`.

15.10.5 `payment_method_present`, `payment_method_last4`, `payment_method_brand`.

15.11 Поля `tariff catalog` (дефолтный набор): `tier`, `task_shares`, `projects`, `teams`, `monthly_rub`, `annual_rub`. Для free `monthly_rub`/`annual_rub` отсутствуют.

15.12 Поля `tariff payments` (дефолтный набор): `at`, `event_type`, плюс контекстные поля из §14.2 для конкретного события.

15.13 Поля `tariff payment-method show` (дефолтный набор): `present`, `last4`, `brand`. Если `present=false` — `last4` и `brand` отсутствуют в выводе.

15.14 unlimited лимиты рендерятся как `∞` в человеко-читаемом выводе; в `--output json` — `null`.

15.15 Существующие list-команды получают флаг `--include-frozen`:

15.15.1 `clite team list [--include-frozen]`.

15.15.2 `clite project list [--include-frozen]`.

15.15.3 `clite share user list [--include-frozen]`.

15.16 По умолчанию `--include-frozen=false`; frozen-записи исключены из выдачи.

15.17 В выдаче этих команд добавляется поле `frozen: bool` всегда.

15.18 `clite team get <key>` и `clite project get <key>` — frozen-сущность доступна по ключу всегда; поле `frozen: bool` в ответе.

15.19 `clite task list --filter <rsql>` (PRD §7.1) — задачи, доступные пользователю ТОЛЬКО через frozen `TaskUserShare` (или frozen `ProjectUserMember`/`TeamMember`), не возвращаются.

15.20 Задачи, доступные одновременно через frozen-путь и активный путь, возвращаются как обычно.

## 16. REST API

16.1 Все эндпоинты тарифа живут в auth-svc; префикс — `apitracker.ru/api/auth/` (ARCH §7.2).

16.2 Список эндпоинтов:

16.2.1 `GET /api/auth/tariff/catalog` — public, без auth, возвращает §2.

16.2.2 `GET /api/auth/me/tariff` — обслуживает `tariff show`.

16.2.3 `GET /api/auth/me/tariff/payments?cursor=...` — обслуживает `tariff payments`.

16.2.4 `POST /api/auth/me/tariff/upgrade` — тело `{tier, period}`, ответ `{confirmation_url, payment_id}`.

16.2.5 `POST /api/auth/me/tariff/cancel` — без тела.

16.2.6 `GET /api/auth/me/payment-method` — обслуживает `payment-method show`.

16.2.7 `POST /api/auth/me/payment-method` — ответ `{confirmation_url, payment_id}`.

16.2.8 `DELETE /api/auth/me/payment-method` — без тела.

16.2.9 `POST /api/auth/payments/yookassa-callback` — webhook (см. §13).

16.3 Все эндпоинты, кроме `tariff/catalog` и `yookassa-callback`, требуют Bearer-токен (см. PRD §10).

16.4 OpenAPI генерируется FastAPI-кодом, как остальные эндпоинты auth-svc (ARCH §7.3, §5.1).

## 17. Коды ошибок

17.1 В tasks-svc:

17.1.1 `tariff_limit_exceeded` — поля `subject_email`, `metric: task_shares|projects|teams`, `limit: int|null`.

17.2 В auth-svc:

17.2.1 `tariff_not_an_upgrade`.

17.2.2 `tariff_not_active`.

17.2.3 `tariff_already_cancelled`.

17.2.4 `payment_method_absent`.

17.2.5 `payment_method_verification_failed`.

17.2.6 `payment_declined`.

## 18. gRPC контракты

18.1 Расширение раздела ARCH §6.

18.2 Новый метод tasks-svc → auth-svc (направление существующее):

18.2.1 `GetUserLimits(user_id) → {task_shares: int|null, projects: int|null, teams: int|null}`.

18.2.2 `null` означает unlimited.

18.2.3 Используется tasks-svc'ом для pre-check'ов §4.2, для алгоритмов §6.2–6.4 и §18.5.

18.3 Новый метод auth-svc → tasks-svc (новое направление — раньше отсутствовало):

18.3.1 `RecomputeFreezeForUser(user_id) → void`.

18.3.2 Вызывается auth-svc'ом синхронно после каждой записи нового `tariff` или `tariff_until` в `auth.users`.

18.3.3 Внутри tasks-svc: получает текущие лимиты через `GetUserLimits` и применяет §6.2 для каждой метрики, при этом для unlimited (null) дополнительно применяет §6.4 (полный unfreeze).

18.4 Транспортные детали (gRPC-порт, обратный канал) — реализационные; следуют конвенциям ARCH §1.2.3.

18.5 Атомарность limit-check'а в tasks-svc:

18.5.1 В одной транзакции: lock на cache-строке `auth.users` (через row-level lock в tasks-кеше §3.5.1 или application-level lock per user_id), SELECT count из соответствующей permission-таблицы, сравнение с лимитом, INSERT при успехе.

18.5.2 Конкретный механизм сериализации (advisory lock / row-lock / serializable transaction) — реализация.

## 19. Миграции БД

19.1 Схема `auth`:

19.1.1 ALTER `auth.users`: добавить колонки §7.1.

19.1.2 CREATE TABLE `auth.payment_events` (см. §14.1).

19.2 Схема `tasks`:

19.2.1 ALTER `tasks.task_user_shares`: ADD COLUMN `frozen bool NOT NULL DEFAULT false`.

19.2.2 ALTER `tasks.project_user_members`: ADD COLUMN `frozen bool NOT NULL DEFAULT false`.

19.2.3 ALTER `tasks.team_members`: ADD COLUMN `frozen bool NOT NULL DEFAULT false`.

19.2.4 CREATE INDEX `(user_id, frozen, created_at)` на каждой из трёх таблиц.

19.3 Миграции запускаются стандартным entrypoint-механизмом (ARCH §3.3).

19.4 Колонка `created_at` должна присутствовать на трёх permission-таблицах для FIFO-сортировки §6.2.2 и §6.4.2. Если отсутствует — добавляется этой же миграцией с дефолтом `now()`.

## 20. Не входит в скоуп

20.1 Биллинг и платежи:

20.1.1 Grace-период на неуспешное списание.

20.1.2 Возвраты средств.

20.1.3 Прорейтинг при апгрейде (вместо этого — банк §11).

20.1.4 Промокоды, рефералы, скидки.

20.1.5 Несколько сохранённых карт на одного пользователя.

20.1.6 Просмотр метаданных карты сверх `last4` и `brand` (срок действия, имя владельца).

20.1.7 Чеки и инвойсы как сущность системы (чеки приходят пользователю из ЮКассы стандартным механизмом).

20.1.8 Мульти-валюта.

20.2 Downgrade и переходы:

20.2.1 Прямой downgrade `pro → free` мид-периодом без cancel.

20.2.2 Прямой downgrade `max → pro` мид-периодом без cancel.

20.2.3 Бankование Max-дней.

20.2.4 Передача `pro_bank_days` между пользователями.

20.2.5 Конвертация `pro_bank_days` в деньги.

20.3 Метрики и enforcement:

20.3.1 Лимит на задачи, созданные пользователем.

20.3.2 Лимит на автоматизации.

20.3.3 Лимит на webhook deliveries.

20.3.4 Лимит на history retention.

20.3.5 Per-минутный rate-limit как часть тарифа (общий инфра-лимит на API rps — отдельный механизм, не зависит от тарифа).

20.3.6 Ручной freeze/unfreeze через CLI.

20.3.7 Видимость frozen-статуса участника другими членами команды/проекта.

20.3.8 RSQL по `tariff`, `tariff_until`, `pro_bank_days`.

20.4 Уведомления:

20.4.1 Email- и in-app-уведомления о приближении истечения, провале списания, размораживании (соответствует PRD §12.2).

20.5 Self-service по сети:

20.5.1 UI для управления тарифом в docs-client (соответствует PRD §1.2).

20.5.2 Анонимная покупка без логина.

20.6 Org / workspace:

20.6.1 Концепция workspace или организации.

20.6.2 Командные тарифы (один пользователь платит за нескольких).
