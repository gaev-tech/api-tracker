# Архитектура CLI

## Обзор

Консольный клиент для полного взаимодействия с API трекера. PostMVP. Предназначен для использования в терминале, скриптах и CI/CD-пайплайнах. Является обычным клиентом поверх публичного API — без привилегий.

## Стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Go |
| CLI-фреймворк | Cobra |
| HTTP-клиент | net/http (стандартная библиотека) |
| Конфиг | YAML (`~/.tracker/config.yaml`) |
| Вывод таблиц | tablewriter |
| Дистрибуция | GitHub Releases (бинари для Linux/macOS/Windows) |

## Аутентификация

Два способа аутентификации:

### Интерактивный логин (OAuth 2.0)

Команда `tracker login` запускает OAuth 2.0 Authorization Code Flow с PKCE:
1. CLI генерирует `code_verifier` (случайная строка) и `code_challenge` (SHA-256 хеш).
2. Поднимает временный HTTP-сервер на локальном порту.
3. Открывает браузер на клиенте авторизации с параметрами `client_id`, `redirect_uri=http://localhost:<port>/callback`, `code_challenge` и `code_challenge_method=S256`.
4. Пользователь логинится в браузере.
5. Клиент авторизации редиректит на localhost с authorization code.
6. CLI обменивает code + `code_verifier` на access + refresh token через identity-service.
7. Токены сохраняются в активный профиль конфига.

### PAT (для скриптов и CI/CD)

PAT используется для неинтерактивной аутентификации.

### Приоритет источников токена

1. Флаг `--token <pat>` в команде.
2. Переменная окружения `TRACKER_TOKEN`.
3. Токен в активном профиле конфига `~/.tracker/config.yaml` (PAT или токен от интерактивного логина).

Токены хранятся в конфиг-файле в открытом виде. Файл создаётся с правами `0600`.

## Конфигурация

Файл `~/.tracker/config.yaml`:

```yaml
current_profile: work
profiles:
  work:
    host: https://api.tracker.example.com
    token: pat_xxxxxxxxxxxx
  personal:
    host: https://api.tracker.example.com
    token: pat_yyyyyyyyyyyy
```

Команды для управления профилями и аутентификации:

```
tracker login                               # интерактивный логин через браузер
tracker profile list
tracker profile use <name>
tracker profile add <name> --host <url> --token <pat>
tracker profile remove <name>
```

## Структура команд

Схема: `tracker <ресурс> <действие> [аргументы] [флаги]`.

Составные ресурсы разделяются пробелом: `tracker task access grant`, `tracker project member add`.

Полный каталог команд — в `prd.md`, раздел 1.17 «CLI».

## Форматы вывода

По умолчанию — таблица (human-readable). Переключается флагом `--output`:

| Значение | Описание |
|----------|---------|
| `table` | Таблица (default) |
| `json` | JSON, пригоден для `jq` и скриптов |
| `plain` | Одно значение в строке (для `xargs`, `grep`) |

Пример:
```bash
tracker task list --filter "status==opened;assignee==me" --output json | jq '.[].id'
```

Глобальный дефолт формата настраивается в конфиге:
```yaml
output: json
```

## Обработка ошибок

- API-ошибки выводятся в stderr с кодом ошибки и сообщением из ответа.
- Exit code `0` — успех, `1` — ошибка API или валидации, `2` — ошибка конфигурации/сети.
- При `--output json` ошибка тоже выводится как JSON: `{"error": "...", "code": "..."}`.

## Пагинация

Команды `list` возвращают первую страницу по умолчанию. Флаги:

```
--limit <n>     # размер страницы (default: 20)
--cursor <str>  # курсор для следующей страницы
--all           # автоматически получить все страницы (осторожно на больших наборах)
```

При `--output table` с `--all` строки стримятся по мере получения страниц.

## CI/CD интеграция

Рекомендуемый паттерн для CI:

```bash
export TRACKER_TOKEN=${{ secrets.TRACKER_TOKEN }}
tracker task bulk update --filter "tags==release-1.2" --status closed --output json
```

## Дистрибуция

- Бинари публикуются в GitHub Releases для Linux (amd64, arm64), macOS (amd64, arm64), Windows (amd64).
- Установка через `curl | sh` скрипт и через Homebrew tap.
- Версионирование по semver, синхронизировано с версией API.
