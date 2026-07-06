# SIP Gateway

Servicio Python async independiente para recibir SIP/RTP en un VPS y conectar
la llamada con el backend FastAPI, OpenAI Realtime y el proveedor de voz/TTS
configurado en cada clínica.

No sustituye al flujo OpenAI Hosted SIP existente; convive con él. Usa este
servicio cuando `AssistantConfig.voice_provider != openai` o cuando quieras que
todo el media path pase por tu VPS.

## Flujo

```text
VoIP Studio
  -> SIP INVITE + RTP PCMU/PCMA
  -> sip-gateway
  -> /api/internal/voice/context en FastAPI
  -> OpenAI Realtime WebSocket
  -> audio OpenAI o texto + TTS externo
  -> RTP de vuelta al teléfono
```

## Variables

```env
SIP_BIND_HOST=0.0.0.0
SIP_PORT=6060
SIP_PUBLIC_IP=203.0.113.10
RTP_PORT_MIN=10000
RTP_PORT_MAX=20000
RTP_ADVERTISE_IP=203.0.113.10
SIP_ALLOWED_IPS=
BACKEND_INTERNAL_URL=http://app:8000
OPENAI_API_KEY=...
INTERNAL_API_KEY=...
MAX_CONCURRENT_CALLS=10
MAX_CALL_SECONDS=1800
INVITE_RATE_LIMIT_PER_MINUTE=60
```

`SIP_ALLOWED_IPS` acepta IPs o CIDR separados por coma. Si está vacío, acepta
tráfico SIP desde cualquier IP; en producción conviene limitarlo a VoIP Studio.

## Puertos

Abre en firewall/NAT del VPS:

- UDP `6060` para SIP.
- UDP `10000-20000` para RTP, o el rango que configures.

En VoIP Studio apunta el forwarding a:

```text
sip:bot@IP_PUBLICA:6060
```

## Capacidades implementadas

- SIP UDP mínimo: `INVITE`, `100 Trying`, `180 Ringing`, `200 OK` con SDP,
  `ACK`, `BYE`, `CANCEL`, `OPTIONS`.
- RTP PCMU/8000 y PCMA/8000.
- Pool de puertos RTP.
- Jitter buffer básico.
- Secuencia y timestamp RTP correctos para frames de 20 ms.
- Detección básica de silencio y barge-in.
- OpenAI Realtime server-to-server.
- TTS externo mediante el backend y capa `voice_providers`.
- Limpieza de WebSocket, RTP, tareas async y puerto al colgar.
- Logs JSON con `call_id`, `clinic_id`, `caller`, `callee`, proveedor, codec y
  latencias principales.

## Desarrollo

Desde la raíz del monorepo:

```powershell
docker compose build sip-gateway
docker compose up -d sip-gateway
docker compose logs -f sip-gateway
```

Tests/lint/type check:

```powershell
docker compose run --rm -v ${PWD}\sip-gateway:/gateway app sh -c "cd /gateway && ruff check src tests"
docker compose run --rm -v ${PWD}\sip-gateway:/gateway app sh -c "cd /gateway && PYTHONPATH=src mypy src"
docker compose run --rm -v ${PWD}\sip-gateway:/gateway app sh -c "cd /gateway && PYTHONPATH=src pytest -q"
```

## Limitaciones del MVP

- La interoperabilidad SIP real debe validarse con VoIP Studio porque algunos
  proveedores cambian cabeceras, NAT y formato SDP.
- Para proveedores externos, el gateway hace chunking por frases y pide audio
  al backend; los adaptadores streaming WebSocket específicos pueden ampliarse
  dentro de `voice_providers`.
- `audioop` se usa para conversión ligera en Python 3.11. Antes de migrar a
  Python 3.13 conviene sustituirlo.
