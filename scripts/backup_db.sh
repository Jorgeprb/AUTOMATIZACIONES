#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PRODUCTION_ENV_FILE:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

OUT="$BACKUP_DIR/postgres-$STAMP.sql.gz"
cd "$ROOT_DIR"

if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps -q postgres >/tmp/clinic-postgres-container 2>/dev/null \
  && [[ -s /tmp/clinic-postgres-container ]]; then
  echo "Backing up local docker Postgres to $OUT"
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
    pg_dump -U "${POSTGRES_USER:-clinic}" "${POSTGRES_DB:-clinic}" | gzip > "$OUT"
else
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required for external DB backup." >&2
    exit 1
  fi
  echo "Backing up external Postgres with postgres:16-alpine to $OUT"
  docker run --rm -i postgres:16-alpine pg_dump "$DATABASE_URL" | gzip > "$OUT"
fi

echo "$OUT"
