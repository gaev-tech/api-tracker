#!/usr/bin/env bash
# Одноразовая провижка сертификатов Let's Encrypt для всех хостов.
# Запускается из /opt/api-tracker/repo/deploy/ один раз при первой
# установке. См. SETUP.md шаг 4.
#
# Источник: pattern от https://github.com/wmnnd/nginx-certbot

set -euo pipefail

DOMAINS=(
  apitracker.ru
)
RSA_KEY_SIZE=4096
EMAIL=""  # Заполните или установите через CERTBOT_EMAIL env
CERTBOT_DATA="/var/lib/api-tracker/certbot/conf"
CERTBOT_WWW="/var/lib/api-tracker/certbot/www"
STAGING=0  # 1 — staging Let's Encrypt (для отладки)

if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
  EMAIL="$CERTBOT_EMAIL"
fi

if [[ -z "$EMAIL" ]]; then
  echo "ERROR: задайте CERTBOT_EMAIL env или впишите в скрипт" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

# 1. Скачать рекомендованный TLS-конфиг от certbot, если его нет.
if [[ ! -e "$CERTBOT_DATA/options-ssl-nginx.conf" ]] || [[ ! -e "$CERTBOT_DATA/ssl-dhparams.pem" ]]; then
  echo "### Скачиваем TLS-конфиг от certbot..."
  sudo mkdir -p "$CERTBOT_DATA"
  sudo curl -fsSL "https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf" \
    -o "$CERTBOT_DATA/options-ssl-nginx.conf"
  sudo curl -fsSL "https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem" \
    -o "$CERTBOT_DATA/ssl-dhparams.pem"
fi

# 2. Сгенерировать временные dummy-сертификаты, чтобы nginx стартанул.
for domain in "${DOMAINS[@]}"; do
  cert_dir="$CERTBOT_DATA/live/$domain"
  if [[ -d "$cert_dir" ]]; then
    echo "### $domain: уже есть сертификат, пропуск dummy"
    continue
  fi
  echo "### $domain: создаём dummy-сертификат"
  sudo mkdir -p "$cert_dir"
  sudo docker run --rm --entrypoint sh -v "$CERTBOT_DATA:/etc/letsencrypt" \
    certbot/certbot:latest \
    -c "apk add --no-cache openssl >/dev/null 2>&1 || true; \
        openssl req -x509 -nodes -newkey rsa:$RSA_KEY_SIZE -days 1 \
          -keyout '/etc/letsencrypt/live/$domain/privkey.pem' \
          -out '/etc/letsencrypt/live/$domain/fullchain.pem' \
          -subj '/CN=localhost'"
done

# 3. Поднять nginx с dummy.
echo "### Поднимаем nginx с dummy-сертификатами..."
docker compose -f docker-compose.prod.yml up -d nginx

sleep 5

# 4. Удалить dummy и запросить реальные сертификаты.
for domain in "${DOMAINS[@]}"; do
  cert_dir="$CERTBOT_DATA/live/$domain"
  if sudo openssl x509 -in "$cert_dir/fullchain.pem" -noout -issuer | grep -q "CN=localhost"; then
    echo "### $domain: удаляем dummy"
    sudo rm -rf "$cert_dir" "$CERTBOT_DATA/archive/$domain" "$CERTBOT_DATA/renewal/$domain.conf"
  fi
done

echo "### Запрашиваем реальные сертификаты Let's Encrypt..."
staging_arg=""
if [[ "$STAGING" == "1" ]]; then staging_arg="--staging"; fi

domain_args=""
for d in "${DOMAINS[@]}"; do
  domain_args="$domain_args -d $d"
done

docker compose -f docker-compose.prod.yml run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    --email $EMAIL \
    $domain_args \
    --rsa-key-size $RSA_KEY_SIZE \
    --agree-tos \
    --no-eff-email \
    --force-renewal" certbot

# 5. Перезагрузить nginx.
echo "### Перезагружаем nginx..."
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

echo "### Готово! Проверьте: curl -I https://api.apitracker.ru/healthz"
