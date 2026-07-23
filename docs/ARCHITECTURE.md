# Arquitectura

## Entrada telefónica

VoIP Studio apunta siempre a `sip:bot@sip.autogal.es:6060;transport=udp`.
`sip-gateway` resuelve el contexto en la API y selecciona la ruta:

- `vps_media_bridge`: termina SIP/RTP, fija el origen RTP, procesa PCMA/PCMU,
  usa OpenAI como cerebro y el proveedor TTS configurado.
- `openai_hosted_sip`: no crea un WebSocket local. La ruta Hosted SIP queda
  aislada detrás del edge SIP y del webhook verificado del backend.

El gateway dispone de máquina de ciclo de vida idempotente, timeout de ACK,
colas acotadas, pacing RTP absoluto y métricas OpenMetrics.

## Administración

El navegador se autentica en `/auth/login`. La API emite una sesión opaca
revocable y un token CSRF. Los permisos se restringen por clínica y cada acción
administrativa queda en `admin_audit_logs`.

## Agenda

Las reservas vuelven a comprobar PostgreSQL y Google bajo bloqueo, usan una
clave de idempotencia y PostgreSQL impide solapamientos activos. Los fallos de
compensación se almacenan en `integration_outbox` y se reintentan con backoff.

## Webhooks y mantenimiento

Los webhooks se verifican criptográficamente y se deduplican en
`webhook_receipts`. Un proceso de mantenimiento exclusivo mediante advisory
lock purga sesiones/datos vencidos y procesa la outbox.
