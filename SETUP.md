# Первичная настройка (M0)

После мержа M0-коммитов в `main` необходимы ручные шаги для перехода с K8s на docker-compose.

## 1. GitHub Actions secrets

В `Settings → Secrets and variables → Actions` добавить:

| Имя | Значение |
|---|---|
| `DEPLOY_SSH_KEY` | Приватный OpenSSH-ключ (целиком, включая `-----BEGIN...-----`) с доступом на прод-сервер |
| `DEPLOY_HOST` | `91.218.114.168` |
| `DEPLOY_USER` | Имя SSH-пользователя на прод-сервере |
| `POSTGRES_PASSWORD` | Случайный пароль (32+ символа). Используется внутри compose-сети. |

Уже есть от старого api-tracker и используются:

| Имя | Назначение |
|---|---|
| `KUBECONFIG_B64` | Для одноразового `teardown-k8s` workflow |
| `GITHUB_TOKEN` | GHCR push (стандартный) |

## 2. Снос K8s (одноразово)

```bash
gh workflow run teardown-k8s.yml
gh run watch
```

После успеха старая инфра убрана из cluster, IP `91.218.114.168` свободен для docker-compose.

## 3. Подготовка сервера

SSH на сервер. Установить docker + compose plugin (если не установлены):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# перелогиниться
```

Создать рабочую директорию:

```bash
sudo mkdir -p /opt/api-tracker
sudo chown $USER:$USER /opt/api-tracker
cd /opt/api-tracker
```

Скопировать `deploy/.env.example` в `/opt/api-tracker/.env`, заполнить:

```bash
POSTGRES_PASSWORD=<тот же, что в GHA-секрете>
AUTH_MODE=disabled
SOLO_USER_EMAIL=<ваш email>
```

Создать каталоги под persistent volumes и backup:

```bash
sudo mkdir -p /var/lib/api-tracker/postgres /var/lib/api-tracker/certbot/conf \
              /var/lib/api-tracker/certbot/www /var/backups/api-tracker
sudo chown -R $USER:$USER /var/lib/api-tracker /var/backups/api-tracker
```

## 4. Первичная провижка TLS

```bash
cd /opt/api-tracker
git clone https://github.com/gaev-tech/api-tracker.git repo
cd repo/deploy
./certbot/init-letsencrypt.sh
```

Это поднимет nginx с временным self-signed сертификатом, выпустит реальные сертификаты Let's Encrypt через HTTP-01 challenge, и перезапустит nginx с правильными.

## 5. Установка backup-cron

```bash
sudo cp /opt/api-tracker/repo/deploy/scripts/backup-postgres.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/backup-postgres.sh
echo "0 3 * * * /usr/local/bin/backup-postgres.sh" | sudo crontab -
```

## 6. Первичный деплой

Любой push в `main` после этого автоматически задеплоит:

```bash
git commit --allow-empty -m "chore: trigger first deploy" && git push
```

Проверить:

```bash
curl https://api.apitracker.ru/healthz
# → {"status":"ok"}
```

## Откат

См. `architecture.md` §17.4.
