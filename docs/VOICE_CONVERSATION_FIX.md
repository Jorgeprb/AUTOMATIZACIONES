# Corrección del bucle de bienvenida en VPS Media Bridge

## Causas corregidas

1. El saludo se sintetizaba con Azure, pero no se añadía a la conversación de OpenAI. El modelo creía que todavía debía presentarse.
2. Mientras el bot hablaba, su propio audio podía volver por la línea y activar el VAD como un nuevo turno de usuario.
3. Una misma function call se procesaba tanto en `response.output_item.done` como en `response.function_call_arguments.done`, ejecutando tools dos veces.
4. Se enviaba `response.create` antes de que finalizase la respuesta que contenía la function call, provocando `conversation_already_has_active_response`.
5. El preset Sabela cambiaba silenciosamente el idioma del asistente a `gl-ES`, aunque el saludo estuviese configurado en castellano.

## Comportamiento nuevo

- El saludo externo se registra como mensaje `assistant/output_text` en Realtime.
- Las instrucciones indican de forma explícita que el saludo ya se reprodujo y no debe repetirse.
- El idioma conversacional y el locale TTS quedan separados.
- El preset Sabela conserva el idioma que ya estuviera seleccionado.
- Azure funciona en semidúplex por defecto: mientras se sintetiza o reproduce el bot, no se envía audio de retorno a OpenAI; se mantiene una cola de supresión de eco al terminar.
- Las tools se deduplican por `call_id`.
- La continuación después de una tool solo se crea tras `response.done`.
- Los errores transitorios `conversation_already_has_active_response` y `response_cancel_not_active` no reproducen el mensaje técnico.

## Variables opcionales

```env
EXTERNAL_TTS_HALF_DUPLEX=true
INITIAL_INPUT_GUARD_MS=1200
ECHO_SUPPRESSION_TAIL_MS=800
```

El modo semidúplex prioriza estabilidad y evita bucles por eco. Para volver a permitir interrupciones mientras Azure habla, se puede desactivar, pero debe existir cancelación de eco real o una calibración de VAD más estricta.

## Despliegue

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build api sip-gateway frontend

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate api sip-gateway frontend caddy
```

No requiere una migración de base de datos.
