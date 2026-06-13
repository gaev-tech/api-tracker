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

echo "### nginx reload (для изменений в conf.d без recreate контейнера)"
docker exec api-tracker-nginx nginx -s reload 2>&1 || echo "nginx reload skipped (контейнер не запущен ещё)"

echo "### docker image prune (старые образы)"
docker image prune -f --filter "until=72h"

echo "### Wait for tasks-svc healthy"
for i in $(seq 1 30); do
  state=$(docker inspect --format '{{.State.Health.Status}}' api-tracker-tasks-svc 2>/dev/null || echo none)
  if [ "$state" = "healthy" ]; then
    echo "tasks-svc healthy after ${i}x2s"
    break
  fi
  sleep 2
done

echo "### Внутренняя проверка /healthz"
docker exec api-tracker-tasks-svc python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz').read().decode())" || {
  echo "ERROR: tasks-svc /healthz внутри контейнера не отвечает" >&2
  exit 1
}

echo "### Внешняя проверка (если TLS настроен)"
if curl -fsS --max-time 5 https://apitracker.ru/healthz 2>/dev/null; then
  echo "HTTPS /healthz OK"
else
  echo "NOTE: HTTPS /healthz пока недоступен (TLS не провижен или nginx не имеет валидных сертов). Это нормально на первом деплое."
fi

echo "### Деплой успешен"
