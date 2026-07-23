# Optimización de latencia de voz

## Causas encontradas

La ruta externa `VoIP Studio → VPS → OpenAI Realtime texto → Azure TTS → RTP`
contenía varias esperas acumulativas:

- hasta 80 ms para agrupar audio antes de enviarlo a Realtime;
- jitter buffer de 3 paquetes y flush de 80 ms;
- `server_vad` sin parámetros explícitos, por lo que dependía de defaults;
- 650 ms para liberar texto parcial hacia Azure;
- 800 ms de supresión tras finalizar la reproducción del bot;
- una conexión DNS/TCP/TLS nueva por cada fragmento Azure;
- resampling G.711 → PCM 24 kHz en entrada y PCM → G.711 en salida OpenAI;
- en Hosted SIP, una transacción PostgreSQL antes de procesar cada evento y antes
  de enviar cada evento de control.

## Cambios aplicados

- Audio SIP enviado a Realtime en PCMA/PCMU nativo cada 40 ms.
- Respuesta OpenAI directa solicitada en el mismo G.711 de la llamada.
- `server_vad`: 300 ms de silencio, 200 ms de prefijo y threshold 0.50.
- Alternativa configurable `semantic_vad` con `eagerness=high`.
- Noise reduction `near_field` configurable.
- Reasoning effort `low` para modelos `gpt-realtime-2*`.
- Jitter: profundidad 2 y flush 40 ms.
- Primer buffer RTP: 120 ms.
- Flush de texto TTS: 250 ms y mínimo 24 caracteres.
- Comas largas y frases se liberan antes; síntesis y lectura de deltas están
  desacopladas manteniendo el orden.
- Supresión de eco posterior reducida a 250 ms y ya no descarta audio mientras
  Azure solo está calculando, antes de reproducir.
- Pool HTTP persistente para Azure y caché de saludos por configuración.
- Persistencia Realtime Hosted SIP en lotes y fuera del camino crítico.
- `response.create` tras tools se serializa después de `response.done`.
- Métricas por turno para localizar VAD, modelo, tools y TTS.

## Perfiles recomendados

Configuración equilibrada de producción:

```env
OPENAI_REALTIME_VAD_MODE=server_vad
OPENAI_REALTIME_VAD_THRESHOLD=0.50
OPENAI_REALTIME_VAD_PREFIX_PADDING_MS=200
OPENAI_REALTIME_VAD_SILENCE_DURATION_MS=300
OPENAI_REALTIME_NOISE_REDUCTION=near_field
OPENAI_REALTIME_REASONING_EFFORT=low
OPENAI_INPUT_BATCH_MS=40
TTS_TEXT_FLUSH_TIMEOUT_MS=250
TTS_MIN_FLUSH_CHARS=24
INITIAL_INPUT_GUARD_MS=400
ECHO_SUPPRESSION_TAIL_MS=250
JITTER_BUFFER_DEPTH=2
JITTER_FLUSH_MS=40
RTP_INITIAL_BUFFER_MS=120
```

Para personas que hacen pausas frecuentes, subir `silence_duration_ms` a 400–450.
Para máxima rapidez, probar `semantic_vad` con eagerness `high` o server VAD entre
220–280 ms, comprobando que no interrumpa frases.

## OpenAI directo

La opción más inmediata dentro del VPS es:

```text
voice_provider=openai
call_audio_mode=vps_media_bridge
```

Elimina Azure TTS y la conversión de audio intermedia. Hosted SIP puede ser aún
más simple en media, pero requiere que el operador SIP entregue la llamada a
OpenAI mediante TLS/B2BUA; el redirect 302 no funcionó con el proveedor actual.

Modelos a evaluar mediante llamadas A/B:

- `gpt-realtime-2.1`: mejor comportamiento general de voz.
- `gpt-realtime-2.1-mini`: menor latencia/coste cuando la calidad sea suficiente.
- `gpt-realtime-1.5`: speech-to-speech rápido sin razonamiento extendido.

No se cambia automáticamente el modelo activo existente.

## Medición

Después de varias llamadas:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production \
  logs --since=30m sip-gateway api | python3 scripts/analyze_voice_latency.py
```

Métricas relevantes:

- `openai_vad_to_response_created_ms`
- `openai_turn_first_model_delta_ms`
- `azure_tts_first_chunk`
- `turn_speech_stop_to_audio_queued_ms`
- `openai_tool_execution_ms`
- equivalentes `realtime_*` para Hosted SIP
