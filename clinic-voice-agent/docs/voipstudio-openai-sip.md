> **DOCUMENTO HISTÓRICO / NO USAR PARA CONFIGURAR CLIENTES**
>
> La arquitectura actual mantiene VoIP Studio siempre en
> `sip:bot@sip.autogal.es:6060;transport=udp`. El destino de OpenAI Hosted SIP
> es interno al edge/router y nunca debe configurarse en la cuenta del cliente.
> Este documento se conserva únicamente como referencia de la integración
> anterior directa. Consulta `deployment-vps-sip.md`.

# Migración de VoIP Studio a OpenAI Realtime SIP

## Objetivo

Conservar el número de VoIP Studio:

```text
+34 881 170 837
```

Quitar el agente actual de Retell AI. Enviar las llamadas entrantes a OpenAI
Realtime SIP.

No hay que portar el número. El número sigue en VoIP Studio.

## Estado actual y valoración

El destino SIP actual es:

```text
+34881170837@5t4n6j0wnrl.sip.livekit.cloud
```

Este destino no es de OpenAI.

El dominio `sip.livekit.cloud` pertenece a la infraestructura SIP de LiveKit.
La documentación de LiveKit construye sus direcciones con este formato:

```text
sip:{subdominio}.sip.livekit.cloud
```

Como al llamar responde el bot de Retell, la regla actual forma parte del flujo
Retell/LiveKit que está activo. No se puede demostrar solo con la URI quién es
el propietario del proyecto LiveKit. Sí se puede afirmar que no es el destino
SIP de OpenAI.

Antes de cambiar nada:

1. Haz una captura de la regla actual.
2. Copia el destino actual en un lugar seguro.
3. Anota el usuario, extensión, grupo o regla que recibe el número.
4. Prepara una ventana corta de prueba.

Esto permite volver temporalmente al destino anterior si la prueba falla.

## Arquitectura final

```text
Llamante
   |
   v
Número VoIP Studio +34 881 170 837
   |
   v
Call Forwarding / SIP Forwarding
   |
   v
sip:${OPENAI_PROJECT_ID}@sip.api.openai.com;transport=tls
   |
   v
OpenAI Realtime SIP
   |
   +--> webhook realtime.call.incoming
   |       |
   |       v
   |    FastAPI
   |       |
   |       +--> PostgreSQL: CallSession y CallEvent
   |       +--> WebSocket de control Realtime
   |       +--> herramientas de citas
   |                  |
   |                  v
   |             Google Calendar
   |
   +--> audio SIP gestionado por OpenAI
```

FastAPI no recibe RTP ni audio manual. Recibe el webhook. Después acepta la
llamada y abre el WebSocket de control usando el `call_id`.

## Datos necesarios

Configura estas variables en `.env`:

```dotenv
OPENAI_API_KEY=...
OPENAI_WEBHOOK_SECRET=...
OPENAI_PROJECT_ID=proj_...
OPENAI_REALTIME_MODEL=gpt-realtime-2
OPENAI_REALTIME_VOICE=marin

PUBLIC_BASE_URL=https://TU_DOMINIO
CLINIC_PHONE_NUMBER=+34881170837
```

Usa una API key del mismo proyecto de OpenAI que recibe el tráfico SIP.

Este MVP usa una sola clínica. Debe existir una fila de clínica con:

```text
phone_number = +34881170837
```

El webhook intenta resolver la clínica por la cabecera SIP `To`. Algunos
proveedores reescriben esa cabecera con el project ID. En ese caso, el código
usa `CLINIC_PHONE_NUMBER` o la única clínica existente como fallback.

## 1. Preparar el backend

Arranca la aplicación:

```bash
docker compose up -d --build
make migrate
make seed
```

Comprueba la salud:

```bash
curl http://localhost:8000/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "service": "clinic-voice-agent",
  "environment": "development"
}
```

Antes de tocar VoIP Studio, prueba el flujo sin teléfono:

```bash
make simulate
```

Si Google OAuth ya está configurado:

```bash
make simulate-google
```

## 2. Exponer FastAPI con HTTPS

### ngrok

```bash
ngrok http 8000
```

Ejemplo:

```text
https://abc123.ngrok-free.app
```

El webhook será:

```text
https://abc123.ngrok-free.app/webhooks/openai/realtime
```

### Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:8000
```

El webhook será:

```text
https://TU_SUBDOMINIO.trycloudflare.com/webhooks/openai/realtime
```

El túnel debe seguir abierto durante toda la llamada.

Actualiza `PUBLIC_BASE_URL` si cambia el dominio. Si el mismo túnel se usa para
Google OAuth, actualiza también `GOOGLE_REDIRECT_URI` y la URI autorizada en
Google Cloud.

## 3. Configurar OpenAI

### Obtener `OPENAI_PROJECT_ID`

1. Abre el panel de OpenAI.
2. Selecciona el proyecto que usará la clínica.
3. Abre **Settings > Project > General**.
4. Copia el ID con prefijo `proj_`.
5. Guárdalo como `OPENAI_PROJECT_ID`.

Ejemplo:

```dotenv
OPENAI_PROJECT_ID=proj_abc123
```

### Crear el webhook

1. En el mismo proyecto, abre **Settings > Project > Webhooks**.
2. Crea un webhook público.
3. Usa esta URL:

   ```text
   https://TU_DOMINIO/webhooks/openai/realtime
   ```

4. Suscribe el evento:

   ```text
   realtime.call.incoming
   ```

5. Copia el secreto de firma.
6. Guárdalo en:

   ```dotenv
   OPENAI_WEBHOOK_SECRET=...
   ```

7. Reinicia el backend después de cambiar `.env`.

El secreto del webhook no es la API key. Tampoco es el project ID.

### Construir el destino SIP

El formato oficial es:

```text
sip:${OPENAI_PROJECT_ID}@sip.api.openai.com;transport=tls
```

Ejemplo:

```text
sip:proj_abc123@sip.api.openai.com;transport=tls
```

El usuario SIP es el project ID. No uses el número `+34881170837` como usuario
del destino de OpenAI.

## 4. Cambiar VoIP Studio

Los nombres exactos del menú pueden variar según la versión y el tipo de
cuenta.

1. Abre el panel de VoIP Studio.
2. Localiza el número:

   ```text
   +34 881 170 837
   ```

3. Identifica a qué usuario, extensión, grupo, IVR o regla entra el número.
4. Localiza el **Call Forwarding**, **SIP Forwarding** o destino externo que
   contiene:

   ```text
   +34881170837@5t4n6j0wnrl.sip.livekit.cloud
   ```

5. Desactiva o elimina ese destino de la ruta activa.
6. No elimines el número de VoIP Studio.
7. Configura el nuevo destino:

   ```text
   sip:proj_...@sip.api.openai.com;transport=tls
   ```

8. Guarda la regla.
9. Comprueba que no queda otra regla paralela hacia Retell o LiveKit.

Si Retell sigue respondiendo, existe otra ruta activa. Revisa:

- desvíos del usuario;
- reglas del número;
- grupos de llamada;
- IVR;
- horario laboral y fuera de horario;
- desvío por no respuesta;
- destinos simultáneos.

## Formatos alternativos para VoIP Studio

Prueba primero el formato oficial completo:

```text
sip:proj_...@sip.api.openai.com;transport=tls
```

Si el campo añade `sip:` automáticamente:

```text
proj_...@sip.api.openai.com;transport=tls
```

Si el campo rechaza el parámetro `;transport=tls`, usa:

```text
proj_...@sip.api.openai.com
```

Después selecciona **TLS** en un campo de transporte separado.

Si VoIP Studio separa los datos:

```text
Usuario / destino: proj_...
Dominio / servidor: sip.api.openai.com
Transporte: TLS
Puerto: automático o el valor TLS exigido por VoIP Studio
```

No cambies a UDP por intuición. El destino oficial de OpenAI pide TLS.

Si ninguno funciona, pregunta a soporte de VoIP Studio:

> Necesito reenviar una llamada entrante a una URI SIP externa con usuario
> alfanumérico, dominio `sip.api.openai.com` y transporte TLS. ¿Qué formato
> acepta el campo de Call Forwarding?

## 5. Primera prueba real

Mantén abiertas tres terminales.

### Terminal 1: backend

```bash
docker compose up -d --build
docker compose logs -f app
```

### Terminal 2: túnel

```bash
ngrok http 8000
```

O:

```bash
cloudflared tunnel --url http://localhost:8000
```

### Terminal 3: base de datos

```bash
docker compose exec postgres psql -U clinic -d clinic
```

Pasos:

1. Comprueba que el webhook de OpenAI usa el dominio actual del túnel.
2. Comprueba que VoIP Studio apunta al project ID correcto.
3. Llama desde un móvil al `+34 881 170 837`.
4. Habla con el agente.
5. Pide una cita.
6. Confirma la reserva.
7. Revisa PostgreSQL y Google Calendar.

## 6. Señales esperadas

### Logs de aplicación

Busca estos eventos JSON:

```text
realtime_incoming_persisted
realtime_call_accepted
realtime_control_connected
```

Cada uno debe incluir el mismo `call_id`.

Otros eventos útiles:

```text
realtime_tool_completed
realtime_control_closed
realtime_call_completed
```

Errores útiles:

```text
openai_webhook_signature_invalid
realtime_accept_failed
realtime_control_start_failed
realtime_control_attempt_failed
realtime_control_failed
realtime_tool_failed
realtime_server_error
```

### Saludo enviado

El saludo inicial se envía por WebSocket como:

```text
response.create
```

El código actual no emite un log separado llamado `saludo_enviado`. Guarda el
evento bruto en `call_events` con tipo:

```text
client.response.create
```

### Consultar llamadas

En `psql`:

```sql
SELECT
    id,
    openai_call_id,
    caller_phone,
    called_number,
    status,
    started_at,
    ended_at
FROM call_sessions
ORDER BY created_at DESC
LIMIT 10;
```

### Consultar eventos

Sustituye el UUID:

```sql
SELECT
    event_type,
    created_at
FROM call_events
WHERE call_session_id = 'UUID_DE_CALL_SESSION'
ORDER BY created_at;
```

Debe aparecer al menos:

```text
realtime.call.incoming
client.response.create
```

Después aparecerán los eventos de conversación y herramientas.

## 7. Verificar Google Calendar

Comprueba primero el estado OAuth:

```bash
curl "http://localhost:8000/api/calendar/status?clinic_id=UUID_DE_CLINICA"
```

Lista calendarios:

```bash
curl "http://localhost:8000/api/calendar/list?clinic_id=UUID_DE_CLINICA"
```

Después de confirmar una cita:

1. Abre Google Calendar con la cuenta de la clínica.
2. Abre el calendario de Ana o Luis.
3. Busca un evento con título:

   ```text
   Cita - NOMBRE
   ```

4. Comprueba que PostgreSQL tiene la cita como `confirmed`.

## Troubleshooting

### No llega el webhook

Comprueba:

1. El móvil está llamando al número correcto.
2. VoIP Studio ya no apunta a `sip.livekit.cloud`.
3. El destino contiene el mismo project ID que el webhook.
4. El webhook está creado en **ese mismo proyecto** de OpenAI.
5. Está seleccionado `realtime.call.incoming`.
6. La URL es HTTPS y termina en:

   ```text
   /webhooks/openai/realtime
   ```

7. El túnel sigue activo.
8. `curl https://TU_DOMINIO/health` responde.
9. El panel de OpenAI muestra intentos de entrega del webhook.

Si Retell responde, el tráfico no ha salido todavía de la ruta antigua.

### Firma inválida

Síntoma:

```text
openai_webhook_signature_invalid
```

Comprueba:

- `OPENAI_WEBHOOK_SECRET` pertenece al webhook actual;
- no has puesto `OPENAI_API_KEY` en esa variable;
- no has puesto `OPENAI_PROJECT_ID` en esa variable;
- no estás usando el secreto de otro proyecto;
- reiniciaste la aplicación después de cambiar `.env`;
- el proxy no modifica el cuerpo bruto del webhook.

### VoIP Studio no acepta la URI SIP

Prueba los formatos alternativos de esta guía.

Comprueba si la interfaz:

- añade `sip:` automáticamente;
- tiene un selector separado para TLS;
- rechaza parámetros después de `;`;
- acepta usuarios alfanuméricos como `proj_...`;
- solo admite números E.164.

Si solo admite números, usa el fallback Asterisk/FreeSWITCH.

### La llamada corta inmediatamente

Busca:

```text
realtime_incoming_persisted
realtime_accept_failed
realtime_control_failed
```

Comprueba:

- API key válida;
- API key y project ID del mismo proyecto;
- modelo Realtime disponible para el proyecto;
- backend activo;
- conexión saliente HTTPS y WebSocket permitida;
- VoIP Studio usa TLS hacia OpenAI.

Si existe `realtime_incoming_persisted` pero no
`realtime_call_accepted`, el problema está en la aceptación.

Si la respuesta HTTP es `422` y aparece:

```text
No clinic matches the called SIP number.
```

comprueba `CLINIC_PHONE_NUMBER`, ejecuta `make seed` y confirma que solo está
activa la clínica correcta.

### No hay audio

No envíes audio manual desde FastAPI. El audio llega por SIP.

Comprueba:

- la llamada no está en silencio en VoIP Studio;
- el proveedor mantiene la señalización y el tráfico de medios;
- no hay una regla vieja que mezcle dos destinos;
- el firewall o NAT no rompe el flujo SIP/RTP;
- la llamada llega a OpenAI y el WebSocket permanece abierto.

Si el webhook, aceptación y WebSocket funcionan, pero no hay audio en ninguna
dirección, el problema probablemente está en la interoperabilidad SIP/media
entre VoIP Studio y OpenAI.

### OpenAI acepta pero no habla

Debe existir:

```text
realtime_call_accepted
realtime_control_connected
```

Después debe existir este evento en `call_events`:

```text
client.response.create
```

Si no existe, el WebSocket no llegó a enviar el saludo.

Si existe y no se oye nada, revisa audio, medios y compatibilidad SIP.

### Google Calendar no reserva

Comprueba:

1. OAuth está conectado.
2. El token no está revocado.
3. Ana y Luis tienen `calendar_id`.
4. La cuenta puede escribir en esos calendarios.
5. El horario laboral contiene el hueco.
6. FreeBusy no devuelve el hueco como ocupado.
7. El paciente confirmó verbalmente.

Busca:

```text
realtime_tool_failed
realtime_tool_unexpected_error
```

Repite la prueba con:

```bash
make simulate-google
```

Así separas un problema de Calendar de un problema telefónico.

## Rollback rápido

Si la prueba falla y necesitas recuperar el bot anterior:

1. Desactiva el destino de OpenAI.
2. Restaura temporalmente:

   ```text
   +34881170837@5t4n6j0wnrl.sip.livekit.cloud
   ```

3. Guarda la regla.
4. Llama de nuevo.

No borres el número. No cambies su titularidad.

## Fallback: Asterisk o FreeSWITCH en VPS

Usa este fallback solo si VoIP Studio no puede enviar directamente a una URI
SIP externa con usuario alfanumérico y TLS.

Arquitectura:

```text
VoIP Studio
   |
   v
Asterisk o FreeSWITCH en VPS
   |
   v
sip:${OPENAI_PROJECT_ID}@sip.api.openai.com;transport=tls
   |
   v
OpenAI Realtime SIP
   |
   v
Webhook FastAPI existente
```

Responsabilidades del SBC/PBX:

- aceptar el formato SIP que VoIP Studio sí soporte;
- conservar o reconstruir el caller ID;
- reenviar hacia OpenAI usando TLS;
- gestionar NAT, RTP y codecs;
- registrar trazas SIP;
- aplicar límites y seguridad.

La API FastAPI no cambia:

```text
POST /webhooks/openai/realtime
```

El webhook sigue creado en OpenAI. Google Calendar tampoco cambia.

No se incluye todavía configuración de Asterisk o FreeSWITCH. Debe diseñarse
después de confirmar qué limitación exacta tiene VoIP Studio.

## Checklist final

- [ ] El número `+34 881 170 837` sigue activo en VoIP Studio.
- [ ] La antigua URI LiveKit está anotada para rollback.
- [ ] El backend responde en `/health`.
- [ ] El túnel HTTPS está activo.
- [ ] El webhook está en el proyecto OpenAI correcto.
- [ ] `OPENAI_WEBHOOK_SECRET` corresponde a ese webhook.
- [ ] `OPENAI_PROJECT_ID` empieza por `proj_`.
- [ ] VoIP Studio apunta a `sip.api.openai.com`.
- [ ] La llamada crea `CallSession`.
- [ ] Los logs contienen el mismo `call_id`.
- [ ] Existe `client.response.create`.
- [ ] Se oyó el saludo.
- [ ] Se guardaron eventos en `CallEvent`.
- [ ] Una cita confirmada aparece en PostgreSQL.
- [ ] Una cita confirmada aparece en Google Calendar.

## Referencias oficiales

- OpenAI Realtime SIP:
  <https://developers.openai.com/api/docs/guides/realtime-sip>
- OpenAI Project settings:
  <https://platform.openai.com/settings>
- LiveKit SIP trunk setup:
  <https://docs.livekit.io/telephony/start/sip-trunk-setup/>
