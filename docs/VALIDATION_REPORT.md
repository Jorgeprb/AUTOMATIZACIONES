# Informe de validación Enterprise

Fecha: 2026-07-29

## Resultado

| Área | Resultado |
|---|---|
| Backend | 138 pruebas superadas; compileall, Ruff y mypy correctos |
| SIP gateway | 43 pruebas superadas; Ruff y mypy correctos |
| Frontend admin/cliente | 12 archivos, 38 pruebas; typecheck y build correctos |
| Web pública | 2 pruebas; typecheck y build correctos |
| Alembic/PostgreSQL 16 | vacío e incremental correctos; esquema sin diferencias |
| Docker | 6 imágenes de aplicación construidas |
| Compose | renderizado correcto con .env.production.example |
| Caddy | configuración válida |
| SQLAlchemy/FastAPI | 37 tablas; 18 rutas base, 126 paths y 166 operaciones |

Head único: `20260729_0022`.

## Escenarios cubiertos

- Registro, sesión automática, verificación de correo de un solo uso y onboarding de dos clínicas.
- Revocación y bloqueo de sesiones; seguridad OAuth y separación de portales.
- Aislamiento por clínica, CRM, campos personalizados, recursos, reservas y Caller ID.
- Catálogo con precio calculado en servidor.
- Webhook Stripe firmado simulado, pago confirmado, idempotencia, entitlement y provisión.
- Realtime `gpt-realtime-2`, sin `session.temperature`, TTS externo y guardas de audio.
- Cierre SIP natural, espera de playout y análisis no bloqueante.
- Rutas, formularios y builds de los portales y la web pública.

## Migración

Validado en PostgreSQL temporal:

```text
base vacía -> 20260729_0022
20260729_0022 -> 20260728_0020 -> 20260729_0022
alembic check: No new upgrade operations detected
```

La revisión 0022 usa binds UUID explícitos, amplía `appointments.status` a 11 caracteres y revierte correctamente la constraint histórica. No se modificaron revisiones anteriores.

## Limitaciones reales

- No se hicieron llamadas a Stripe, Google OAuth, SMTP, OpenAI Realtime ni proveedor SIP reales.
- Bandit no está instalado en el entorno de test; Ruff y mypy sí fueron ejecutados.
- La configuración Compose real no se imprimió ni inspeccionó; se validó el ejemplo seguro.
- La base de producción permanece en 0020 hasta el despliegue autorizado.

## Postdespliegue

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=200 migrate api sip-gateway caddy
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --entrypoint alembic migrate current
curl -fsS https://voice.autogal.es/health/ready
```
