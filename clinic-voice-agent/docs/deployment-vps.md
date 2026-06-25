# Despliegue en VPS pequeño

## Requisitos

- Ubuntu o Debian actualizado.
- Docker Engine y Docker Compose.
- Dos nombres DNS apuntando a la IP del VPS:
  `voice.example.com` para API/webhooks y `admin.voice.example.com` para panel.
- Puertos TCP 80 y 443 abiertos.
- Puerto UDP 443 opcional para HTTP/3.
- Al menos 1 GB de RAM. Se recomiendan 2 GB.

PostgreSQL y FastAPI no publican puertos al host. Caddy es la única entrada
pública.

## Preparación

```bash
cp .env.production.example .env.production
chmod 600 .env.production
chmod +x deploy.sh scripts/backup_postgres.sh
```

Edita todos los valores. Genera secretos:

```bash
openssl rand -hex 32
```

Genera la clave Fernet:

```bash
docker run --rm python:3.12-slim \
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`APP_DOMAIN` debe coincidir con `PUBLIC_BASE_URL` y con el webhook de OpenAI.
`APP_ADMIN_DOMAIN` publica el panel React. Caddy obtiene TLS automáticamente
para ambos dominios.

## Despliegue

```bash
./deploy.sh
```

El script:

1. valida que existe `.env.production`;
2. construye la imagen;
3. arranca PostgreSQL;
4. ejecuta Alembic;
5. arranca FastAPI, el panel React y Caddy;
6. muestra el estado.

Comprobaciones:

```bash
curl https://voice.example.com/health/live
curl https://voice.example.com/health/ready
curl -I https://admin.voice.example.com
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

## Configuración de servicios externos

1. En OpenAI crea el webhook:
   `https://voice.example.com/webhooks/openai/realtime`.
2. Configura `OPENAI_PROJECT_ID` y reenvía VoIP Studio a:
   `sip:${OPENAI_PROJECT_ID}@sip.api.openai.com;transport=tls`.
3. En Google Cloud usa como redirect URI:
   `https://voice.example.com/auth/google/callback`.
4. Abre el panel en `https://admin.voice.example.com`.
5. Crea la clínica, número, trabajadores, calendarios, servicios y asistente.
6. Completa la consola simulada.
7. Haz una llamada real y revisa el dashboard y la checklist.

El panel MVP incluye `ADMIN_API_KEY` en el bundle del navegador. Debe
reemplazarse por autenticación de usuario antes de abrir el panel a terceros.

## Logs

FastAPI y Caddy escriben JSON en stdout. Docker rota los logs:

- tamaño máximo: 10 MB;
- archivos conservados: 5 en producción.

Consulta:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml logs -f app caddy
```

## Backup de PostgreSQL

Ejecuta:

```bash
./scripts/backup_postgres.sh
```

El resultado queda en:

```text
backups/clinic-YYYYMMDDTHHMMSSZ.sql.gz
```

Protege ese directorio. Contiene datos personales. Cópialo cifrado fuera del
VPS.

Ejemplo de cron diario a las 03:15:

```cron
15 3 * * * cd /opt/clinic-voice-agent && ./scripts/backup_postgres.sh
```

Prueba de restauración:

```bash
gzip -dc backups/clinic-FECHA.sql.gz | \
docker compose --env-file .env.production \
  -f docker-compose.prod.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Haz la restauración primero en una base de prueba. Un backup no probado no es
un backup fiable.

## Retención

Cada clínica tiene `data_retention_days`. El valor inicial es 30.

Vista previa:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml run --rm app \
  python -m scripts.purge_calls --dry-run
```

Purga:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml run --rm app \
  python -m scripts.purge_calls
```

Añade un cron diario. Solo se eliminan llamadas terminales. Las citas se
conservan y pierden la referencia a la llamada eliminada.

## Actualización

```bash
git pull
./deploy.sh
```

Antes de actualizar:

```bash
./scripts/backup_postgres.sh
```

## Rollback

Conserva una etiqueta de imagen estable antes de cambios grandes. Las
migraciones destructivas requieren una estrategia específica. No ejecutes
`alembic downgrade` automáticamente en producción.
