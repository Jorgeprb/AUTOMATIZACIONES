# Entrega reforzada — 23 de julio de 2026

Esta entrega aplica las mejoras de código e infraestructura que pueden
implementarse dentro del repositorio sin cambiar credenciales ni depender de
servicios externos nuevos.

## Cambios principales

- Autenticación administrativa persistente con cookie HttpOnly, CSRF, sesiones
  revocables, bloqueo de fuerza bruta, roles y permisos por clínica.
- Eliminación de credenciales administrativas del bundle y del proxy público.
- Auditoría de acciones administrativas y redacción de PII/secrets en logs.
- Importación de conocimiento protegida contra SSRF, redirects privados y
  respuestas excesivas.
- Reservas idempotentes, restricción PostgreSQL anti-solapamiento, compensación
  durable de Google Calendar y mantenimiento periódico con advisory lock.
- Webhooks OpenAI idempotentes y correlacionados.
- SIP/RTP reforzado: allowlists CIDR, transacciones duplicadas, timeout ACK,
  cierre idempotente, origen/SSRC fijados, parsing RTP completo, wrap de
  secuencia, colas acotadas, pacing absoluto y métricas OpenMetrics.
- OpenAI Realtime GA con colas acotadas, audio agrupado y resampling con estado.
- Docker no privilegiado, redes segmentadas, migración one-shot, healthchecks,
  drenaje y proxy de confianza limitado.
- Frontend con sesiones reales, CSRF, timeout/cancelación, Error Boundary y
  carga paginada de clínicas.
- CI, Dependabot, documentación operativa y empaquetado seguro.

## Migración

Antes de levantar la nueva versión:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

Las migraciones nuevas son:

- `20260723_0016_admin_security.py`
- `20260723_0017_reliability.py`

El primer usuario se crea desde `ADMIN_BOOTSTRAP_USERNAME` y
`ADMIN_BOOTSTRAP_PASSWORD`. Los valores existentes no se han cambiado.

## Verificación ejecutada

- Compilación Python de backend, tests y migraciones: correcta.
- Suite del SIP gateway: 27 tests correctos.
- TypeScript del frontend: correcto.
- YAML de Compose y GitHub Actions: válido.
- Comparación de todos los valores existentes en `.env*`: sin cambios.

La suite completa del backend y el build/Vitest del frontend deben ejecutarse
en CI o Docker limpio, porque el ZIP original incluía dependencias locales no
portables y el entorno de análisis no disponía de todas las dependencias Google.

## Mejoras que requieren infraestructura externa

No se presentan como activas porque no pueden resolverse únicamente con código
del monorepo: B2BUA TLS industrial para Hosted SIP, firewall del proveedor,
SRTP/AEC del operador, almacenamiento de backups off-site, collector
OpenTelemetry, SMS/WhatsApp, integración HIS/CRM y alta disponibilidad
multi-VPS. Consulta `IMPLEMENTATION_STATUS.md`, `ARCHITECTURE.md` y
`OPERATIONS.md`.
