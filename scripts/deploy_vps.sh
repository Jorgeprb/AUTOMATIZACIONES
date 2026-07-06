#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PRODUCTION_ENV_FILE:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production env file: $ENV_FILE" >&2
  echo "Copy .env.production.example to .env.production and fill secrets." >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "Pulling base images..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull --ignore-buildable || true

echo "Building and starting platform..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build

echo "Running migrations explicitly..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T api alembic upgrade head

echo "Services:"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

echo "Done. Check logs with:"
echo "docker compose -f docker-compose.prod.yml --env-file .env.production logs -f api sip-gateway caddy"
