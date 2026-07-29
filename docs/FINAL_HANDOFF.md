# Entrega final para revisión con Codex en VPS

Fecha: 2026-07-29

## Estado de la entrega

Esta copia integra de forma acumulativa el CRM por clínica, reconocimiento de llamantes,
recursos, estadísticas, análisis asíncrono, registro/onboarding, cuentas comerciales,
catálogo, Stripe, provisión y entitlements. La única migración nueva es lineal:

```text
20260728_0020 -> 20260729_0022
```

No se incluyen `.env`, secretos, `.git`, `node_modules`, caches, backups ni scripts de
reparación temporales.

## Validaciones repetidas al empaquetar

- `python -m compileall`: correcto.
- `git diff --check`: correcto.
- `alembic heads`: una única cabeza `20260729_0022`.
- Frontend administrador/cliente: `npm run typecheck` correcto.
- SIP gateway: 43 pruebas superadas.
- Import completo FastAPI/SQLAlchemy: validado anteriormente con 170 rutas, 37 tablas y
  mappers correctos; no se pudo repetir en el empaquetado porque el runtime disponible no
  contiene `google-auth`, `stripe`, `phonenumbers` ni `psycopg` y el índice Python interno
  no ofrece esos paquetes.
- Web pública: no se pudo repetir TypeScript/build porque no están instaladas sus
  dependencias React/Vite. El paquete no incluye `node_modules`; Docker/npm debe instalar
  dependencias Linux desde `package-lock.json`.

## Comprobación recomendada con Codex

```bash
cd /opt/AUTOMATIZACIONES

# 1. Revisar secretos y completar variables nuevas.
cp .env.production.example .env.production.nueva
# Fusionar manualmente las nuevas claves en el .env.production real; no sustituir secretos.

# 2. Construir sin aplicar aún la migración.
docker compose -f docker-compose.prod.yml --env-file .env.production \
  build --no-cache migrate api sip-gateway frontend client-frontend public-frontend

# 3. Confirmar una única cabeza.
docker compose -f docker-compose.prod.yml --env-file .env.production \
  run --rm --entrypoint alembic migrate heads

# 4. Backup PostgreSQL antes de migrar.
# Usar pg_dump o el mecanismo de backup de Supabase/servicio PostgreSQL.

# 5. Aplicar migración.
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate

# 6. Levantar.
docker compose -f docker-compose.prod.yml --env-file .env.production \
  up -d --force-recreate api sip-gateway frontend client-frontend public-frontend caddy

# 7. Comprobar.
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production \
  logs --tail=250 migrate api sip-gateway frontend client-frontend public-frontend caddy
```

## Tests dentro de las imágenes o entorno Linux

```bash
cd clinic-voice-agent
python -m compileall -q app alembic
pytest
alembic heads

cd ../sip-gateway
pytest

cd ../frontend
npm ci
npm run typecheck
npm run test
npm run build

cd ../public-frontend
npm ci
npm run typecheck
npm run build
```

## Pruebas funcionales prioritarias

1. Login administrador y cliente, incluido Google OAuth.
2. Registro, verificación de correo, recuperación y onboarding.
3. Aislamiento entre dos usuarios y dos clínicas.
4. CRUD/importación/exportación/fusión/anonimización de clientes.
5. Reconocimiento de Caller ID dentro de la clínica correcta.
6. Reserva con cuadrícula, trabajador, recurso y Google Calendar.
7. Cierre SIP y generación posterior de `CallAnalysis`.
8. Stripe Checkout en modo test y reenvío idempotente de webhooks.
9. Provisión manual y activación/desactivación de entitlements.
10. Customer Portal, cancelación al final del periodo y reactivación.

## Precauciones

- No ejecutar `alembic stamp`.
- No ejecutar `docker compose down -v`.
- No exponer `STRIPE_WEBHOOK_SECRET`, claves Google, SMTP ni OpenAI.
- La activación de compras debe depender del webhook verificado, no de la success URL.
- Mantener snapshots históricos de teléfono/nombre al anonimizar clientes.
