#!/usr/bin/env bash
# Вызывается из GHA через SSH после push в main.
# См. specs/architecture.md §17.2, §18.2.3.

set -euo pipefail

REPO_DIR="/opt/api-tracker/repo"
COMPOSE_FILE="$REPO_DIR/deploy/docker-compose.prod.yml"
ENV_FILE="/opt/api-tracker/.env"

cd "$REPO_DIR"

echo "### git fetch + reset на origin/main"
git fetch --all --prune
git reset --hard origin/main

echo "### docker login в GHCR"
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

echo "### docker compose pull"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull

echo "### docker compose up -d"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans

echo "### docker image prune (старые образы)"
docker image prune -f --filter "until=72h"

echo "### Проверка /healthz"
sleep 5
curl -fsS https://apitracker.ru/healthz || {
  echo "ERROR: /healthz не вернул 200" >&2
  exit 1
}

echo "### Деплой успешен"
