# Operación

## Despliegue

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

El servicio `migrate` debe terminar correctamente antes de iniciar `api`.
Durante un reinicio, el gateway deja de aceptar llamadas y cierra sus sesiones
de forma controlada.

## Comprobaciones

```bash
curl -fsS https://voice.autogal.es/health/ready
curl -fsS http://127.0.0.1:8088/health/ready
curl -fsS http://127.0.0.1:8088/metrics
```

Alertar por: crecimiento de `invite_failures`, `provider_errors`, puertos RTP
agotados, outbox en `dead_letter`, Calendar desconectado y webhook fallido.

## Copias y recuperación

Mantener backup PostgreSQL cifrado fuera del VPS y probar restauración. Antes
de desplegar una migración, crear snapshot. Los secretos se conservan fuera de
Git y no se alteran durante actualizaciones de código.
