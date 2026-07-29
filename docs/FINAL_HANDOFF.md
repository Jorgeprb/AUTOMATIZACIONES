# Entrega final Autogal Enterprise

Fecha: 2026-07-29

## Estado

Integración empresarial completada y validada. Cadena Alembic única:

```text
20260728_0020 -> 20260729_0022
```

El código registra 18 rutas FastAPI de primer nivel, 126 paths, 166 operaciones OpenAPI y 37 tablas SQLAlchemy.

## Cambios principales

- CRM tenant-safe, reconocimiento del llamante, campos personalizados, CSV, fusión y anonimización.
- Servicios y alias, profesional preferido, recursos, capacidades, reservas y estadísticas.
- Análisis asíncrono de llamadas y outbox.
- Registro, verificación, recuperación, sesiones, OAuth y onboarding multi-clínica.
- BillingAccount, catálogo, Checkout, Customer Portal, webhooks, suscripciones y entitlements.
- Provisión manual, SMTP, portales, web pública, SIP, Compose y Caddy.
- Migración 0022 corregida para UUID PostgreSQL, longitud de estados y reversibilidad.
- Eliminadas copias de código obsoletas; dependencias y builds quedan fuera de Git.

## Validación

- Backend: 138 pruebas; compileall, Ruff y mypy correctos.
- SIP: 43 pruebas; Ruff y mypy correctos.
- Frontend: 12 archivos y 38 pruebas; typecheck y build correctos.
- Web pública: 2 pruebas; typecheck y build correctos.
- PostgreSQL 16: upgrade vacío, downgrade temporal a 0020, upgrade a 0022 y alembic check correctos.
- Docker: imágenes migrate, api, sip-gateway, frontend, client-frontend y public-frontend construidas.
- Caddy: configuración válida usando variables de ejemplo.
- Compose: renderizado válido usando .env.production.example.
- No se contactó Stripe, Google, SMTP, OpenAI ni un carrier SIP reales.

La base de producción observada sigue en 20260728_0020. Aplicar 0022 solo durante el despliegue controlado.

## Despliegue

```bash
cd /opt/AUTOMATIZACIONES
docker compose -f docker-compose.prod.yml --env-file .env.production build migrate api sip-gateway frontend client-frontend public-frontend
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate api sip-gateway frontend client-frontend public-frontend caddy
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --entrypoint alembic migrate current
```

El último comando debe mostrar `20260729_0022 (head)`.

## Rollback

Preferido: restaurar el backup PostgreSQL previo y las imágenes anteriores. Solo sin datos Enterprise nuevos:

```bash
cd /opt/AUTOMATIZACIONES
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --entrypoint alembic migrate downgrade 20260728_0020
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate api sip-gateway frontend client-frontend public-frontend caddy
```

No usar `alembic stamp`, `docker compose down -v` ni eliminar volúmenes.
