# Naturalidad, interrupciones y transcripciones

## Objetivo

Esta actualización simplifica la configuración del asistente y centra el producto en el comportamiento que percibe la persona que llama.

## Cambios de conversación

- El prompt prioriza respuestas breves, cercanas y específicas para teléfono.
- Se evita repetir el saludo, los datos ya conocidos y resúmenes innecesarios.
- Se hace una pregunta cada vez.
- Las confirmaciones naturales como «vale», «esa» o «me viene bien» se consideran válidas.
- Cuando la persona propone una fecha y una hora exactas, se consulta primero ese horario.
- Si está disponible, el asistente afirma que hay sitio y no ofrece alternativas.
- Las alternativas solo se buscan cuando el horario no está libre, la preferencia es abierta o la persona las solicita.
- Los resultados de las herramientas de disponibilidad incluyen una instrucción explícita para mantener este comportamiento.

## Interrupciones

- El panel permite activar o desactivar que la persona interrumpa al asistente.
- En Media Bridge, el audio del bot se suprime de la entrada para evitar que el asistente se responda a sí mismo.
- Se conserva un pequeño pre-roll para no perder el inicio de la intervención real.
- En Hosted SIP, la sesión utiliza detección de turno y `interrupt_response`.

## Transcripciones

- Las configuraciones activas pasan a tener transcripción habilitada mediante la migración `20260725_0018_enable_transcripts.py`.
- Media Bridge guarda turnos de paciente y asistente mediante el endpoint interno `/api/internal/voice/transcript`.
- Hosted SIP conserva su procesamiento de eventos de transcripción.
- La pantalla de conversación muestra los turnos en formato de chat.
- La exportación JSON incluye:
  - `call.transcript_text`;
  - `transcript_text` en la raíz;
  - `transcript`, una lista estructurada de turnos con rol, interlocutor y texto.

## Configuración simplificada

La interfaz muestra únicamente:

- idioma y voz;
- frase de bienvenida;
- tono, longitud, iniciativa, velocidad y pausas;
- interrupciones y confirmaciones naturales;
- reservas, cambios, cancelaciones y datos que se deben pedir;
- base de conocimiento, transcripción y retención;
- instrucciones de negocio y mensajes especiales.

El proveedor, modelo de Realtime, codec, formato de audio y modo de llamada se conservan en backend y se resuelven automáticamente al elegir una voz.

## Despliegue

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate

docker compose -f docker-compose.prod.yml --env-file .env.production \
  up -d --build --force-recreate api sip-gateway frontend caddy
```
