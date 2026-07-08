#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose --env-file .env.production -f docker-compose.prod.yml)

if [ ! -f .env.production ]; then
  echo "Falta .env.production. Copia .env.production.example y edítalo."
  exit 1
fi

if grep -Eqi 'replace-|example\.com|changeme' .env.production; then
  echo ".env.production contiene valores de ejemplo."
  exit 1
fi

"${COMPOSE[@]}" build app frontend
"${COMPOSE[@]}" up -d postgres

echo "Esperando PostgreSQL..."
attempt=0
until "${COMPOSE[@]}" exec -T postgres sh -c \
  'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1
do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "PostgreSQL no está listo."
    exit 1
  fi
  sleep 2
done

"${COMPOSE[@]}" run --rm --no-deps app alembic upgrade head
"${COMPOSE[@]}" up -d app frontend caddy
"${COMPOSE[@]}" ps

APP_DOMAIN=$(sed -n 's/^APP_DOMAIN=//p' .env.production | tail -n 1)
APP_ADMIN_DOMAIN=$(sed -n 's/^APP_ADMIN_DOMAIN=//p' .env.production | tail -n 1)
echo "Despliegue terminado."
echo "Comprueba: https://${APP_DOMAIN}/health/ready"
echo "Panel: https://${APP_ADMIN_DOMAIN}"
