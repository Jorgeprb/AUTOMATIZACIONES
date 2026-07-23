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
SIP_PUBLIC_DOMAIN=sip.autogal.es
SIP_PUBLIC_IP=51.210.180.115
RTP_PORT_MIN=10000
RTP_PORT_MAX=20000
RTP_ADVERTISE_IP=51.210.180.115
SIP_ALLOWED_IPS=
BACKEND_INTERNAL_URL=http://app:8000
OPENAI_HOSTED_SIP_STRATEGY=blocked
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
- UDP `10000-10100` para RTP por defecto, o el rango mínimo que configures.

En VoIP Studio apunta el forwarding a:

```text
sip:bot@sip.autogal.es:6060
```

OpenAI Hosted SIP no cambia. Úsalo para voces OpenAI. Usa este gateway para
Azure `gl-ES-SabelaNeural` y otras voces externas.

Si VoIP Studio llama siempre a este gateway, OpenAI Hosted SIP queda bloqueado
por defecto con SIP `488`. Esto evita el cuelgue por 302 UDP -> TLS. El B2BUA TLS
completo queda pendiente; `OPENAI_HOSTED_SIP_STRATEGY=redirect` conserva el 302
solo para pruebas.

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

## OpenAI Realtime GA y Azure Sabela

El gateway usa la interfaz GA de OpenAI Realtime por WebSocket:

```env
OPENAI_REALTIME_MODEL=gpt-realtime-2
OPENAI_REALTIME_WS_URL=wss://api.openai.com/v1/realtime
TELEPHONY_CODEC=pcma
```

No se debe enviar `OpenAI-Beta: realtime=v1`. La sesión se configura con `session.type=realtime`, `session.audio.input` y `output_modalities`. Para voces externas como Azure `gl-ES-SabelaNeural`, OpenAI se usa solo como cerebro y se solicita salida de texto; el texto se sintetiza con el TTS del backend y se envía de vuelta por RTP.

Si `TELEPHONY_CODEC=pcma` y VoIP Studio ofrece PCMA, el SDP responde `m=audio ... RTP/AVP 8` y `a=rtpmap:8 PCMA/8000`. Si el proveedor no ofrece el codec preferido, se usa el codec G.711 disponible.

Tras el `ACK`, el gateway reproduce inmediatamente por Azure/Sabela:

```text
Ola, son a asistente virtual da clínica. En que podo axudarche?
```

Logs esperados para validar el flujo:

```text
openai_ws_connecting
openai_ws_connected
openai_session_update_sent
openai_session_created
openai_error
openai_text_delta
openai_response_done
azure_tts_started
azure_tts_first_chunk
rtp_out_sent
```


## RTP saliente y pacing

El flujo VPS Media Bridge no envía chunks completos de TTS directamente por UDP. El TTS se convierte primero a PCMA/PCMU raw 8 kHz y entra en una cola de salida. Una tarea dedicada `rtp_sender` mantiene reloj RTP telefónico con planificación absoluta (`time.monotonic()`): 160 bytes cada 20 ms, timestamp +160, sequence +1 y SSRC estable por llamada.

Variables útiles:

    TELEPHONY_CODEC=pcma        # pcma => payload 8 PCMA/8000; pcmu => payload 0 PCMU/8000
    RTP_INITIAL_BUFFER_MS=240   # buffer de playout inicial para absorber jitter de TTS
    RTP_PACKET_LOG_EVERY=50     # frecuencia de logs agregados de RTP saliente
    EXTERNAL_TTS_HALF_DUPLEX=true  # evita que el eco de Azure cree turnos fantasma
    INITIAL_INPUT_GUARD_MS=1200    # no enviar audio a OpenAI durante el arranque/saludo
    ECHO_SUPPRESSION_TAIL_MS=800   # cola de supresión después de terminar el bot

Para Azure en llamadas, el backend debe devolver audio raw G.711:

- `pcma`: `raw-8khz-8bit-mono-alaw`, `audio/pcma`
- `pcmu`: `raw-8khz-8bit-mono-mulaw`, `audio/pcmu`

Los logs relevantes son `rtp_sender_started`, `rtp_out_sent`, `rtp_out_packet_sent`, `rtp_out_interval_ms`, `rtp_underrun`, `rtp_overrun`, `tts_audio_buffered_ms`, `tts_audio_bytes` y `packetizer_finished`.


## Estabilidad de conversación con TTS externo

Cuando `voice_provider=azure`, el saludo se reproduce fuera de OpenAI. El gateway
registra ese saludo como un mensaje previo del asistente en la conversación Realtime,
de modo que el modelo no vuelva a presentarse. Además, el audio entrante se bloquea
mientras Azure está sintetizando o reproduciendo y durante una pequeña cola de eco.
Esto evita que el propio altavoz del bot active el VAD como si fuese la persona usuaria.

Las llamadas de herramientas se deduplican por `call_id`. El resultado se entrega una
sola vez y la continuación `response.create` se envía después de `response.done`, nunca
mientras ya existe otra respuesta activa. Los errores transitorios
`conversation_already_has_active_response` y `response_cancel_not_active` no reproducen
el mensaje técnico al usuario.
