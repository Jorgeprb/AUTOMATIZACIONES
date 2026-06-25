#!/usr/bin/env bash
set -euo pipefail

mkdir -p backups
timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
output="backups/clinic-${timestamp}.sql.gz"

docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  | gzip > "$output"

echo "Backup creado: $output"
