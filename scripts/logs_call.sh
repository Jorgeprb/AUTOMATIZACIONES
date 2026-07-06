#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PRODUCTION_ENV_FILE:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"
CALL_ID="${1:-}"

if [[ -z "$CALL_ID" ]]; then
  echo "Usage: scripts/logs_call.sh CALL_ID_OR_PHONE" >&2
  exit 1
fi

cd "$ROOT_DIR"

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --since 24h api sip-gateway caddy \
  | grep -F "$CALL_ID" || true
