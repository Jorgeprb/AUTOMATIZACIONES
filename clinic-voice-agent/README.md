# Clinic Voice Agent

MVP local y preparado para desplegar de un asistente telefónico para clínicas.
El proyecto proporciona la base de FastAPI, PostgreSQL, SQLAlchemy, Alembic,
OpenAI Realtime SIP y Google Calendar. Incluye un simulador local para validar
la conversación y las herramientas antes de conectar un número real.

## Estado actual del backend

- `GET /health` está operativo.
- `GET /health/live` comprueba el proceso y `GET /health/ready` comprueba
  PostgreSQL.
- PostgreSQL y la aplicación arrancan con Docker Compose.
- Las migraciones crean clínicas, trabajadores, servicios, llamadas, eventos,
  credenciales cifradas y citas.
- El logging de aplicación y peticiones se emite como JSON.
- Google Calendar usa OAuth de una cuenta de clínica y almacena los tokens
  cifrados en PostgreSQL.
- `POST /webhooks/openai/realtime` verifica la firma, acepta llamadas SIP y
  abre el WebSocket de control.
- `POST /dev/simulate-agent-turn` prueba el agente sin teléfono ni OpenAI.

### Estado verificado

La aplicación incluye backend, panel React, dashboard por clínica, checklist
de producción, consola de prueba y despliegue con Docker. Las migraciones
alcanzan `20260622_0007`. El dominio y los endpoints administrativos aíslan
recursos mediante `clinic_id`.

El panel usa una API key administrativa simple para este MVP. Antes de ofrecer
acceso a terceros debe sustituirse por autenticación de usuarios.

## Requisitos

- Docker Desktop o Docker Engine con Compose.
- Opcional para ejecución sin Docker: Python 3.11+.
- `ngrok` o `cloudflared` para exponer el servidor local.

## Arranque local

1. Crea el archivo de entorno canónico:

   ```bash
   cp .env.example .env
   ```

   En PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Sustituye los valores `replace-with-*`. No añadas `.env` al repositorio.
   Puedes generar una clave Fernet para cifrar futuros tokens de Google:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Arranca la aplicación y PostgreSQL:

   ```bash
   make dev
   ```

   Sin `make`:

   ```bash
   docker compose up --build
   ```

4. Aplica la migración inicial en otra terminal:

   ```bash
   make migrate
   ```

5. Opcionalmente crea la clínica demo con Ana, Luis y estos servicios:

   - `Consulta general`, 30 minutos.
   - `Revisión`, 45 minutos.
   - `Urgencia no médica`, 20 minutos.

   ```bash
   make seed
   ```

6. Configura OAuth de Google siguiendo la sección siguiente.

7. Comprueba el servicio:

   ```bash
   curl http://localhost:8000/health
   ```

   Swagger UI estará en <http://localhost:8000/docs>.

## Simulación local sin teléfono

El simulador crea una `CallSession` falsa. Usa el mismo motor de scheduling,
las mismas transacciones y el mismo dispatcher de herramientas que las
llamadas Realtime. No llama a OpenAI.

Modo recomendado, con calendario falso en memoria:

```bash
docker compose run --rm app python -m app.simulate_call --no-google
```

También puedes usar:

```bash
make simulate
```

Con Google Calendar real y la cuenta OAuth ya conectada:

```bash
docker compose run --rm app python -m app.simulate_call --google-real
```

O:

```bash
make simulate-google
```

Ejemplo de conversación:

```text
Tú: Quiero una cita con Ana mañana por la mañana. Me llamo Marta y mi teléfono es +34600123456.
Agente: Tengo estas opciones...
Tú: Elijo la primera.
Agente: ¿Confirmas la reserva?
Tú: Sí, confirmo.
Agente: Cita confirmada...
```

El modo `--no-google` asigna identificadores locales a trabajadores sin
calendario. Los eventos viven en memoria. Las citas y llamadas sí quedan en
PostgreSQL.

### Endpoint de desarrollo

Solo está disponible fuera de producción:

```http
POST /dev/simulate-agent-turn
Content-Type: application/json
```

Primer turno:

```json
{
  "clinic_id": "UUID_DE_CLINICA",
  "mode": "no-google",
  "message": "Quiero una cita con Ana mañana por la mañana. Me llamo Marta y mi teléfono es +34600123456."
}
```

Los siguientes turnos deben enviar el `call_session_id` devuelto:

```json
{
  "call_session_id": "UUID_DE_CALL_SESSION",
  "mode": "no-google",
  "message": "Elijo la primera"
}
```

La reserva solo se crea tras otro turno con una confirmación clara.

### Flujo completo antes de VoIP Studio

```bash
docker compose up
make migrate
make seed
```

Después:

1. Configura Google OAuth siguiendo esta guía.
2. Ejecuta `make calendar-demo`.
3. Ejecuta `make simulate-google`.
4. Pide una cita y confírmala.
5. Revisa el evento creado en el calendario Google del trabajador.

Para probar sin OAuth, usa `make simulate`.

## Túnel público

Con ngrok:

```bash
ngrok http 8000
```

Con Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

Actualiza `PUBLIC_BASE_URL` y `GOOGLE_REDIRECT_URI` en `.env` con la URL HTTPS
del túnel y reinicia la aplicación.

## Google Calendar OAuth

Este MVP usa una cuenta Google normal de la clínica, por ejemplo
`clinica@gmail.com`. No usa service accounts. La cuenta OAuth es propietaria de
un calendario secundario por trabajador, por lo que Ana y Luis pueden tener
citas simultáneas en calendarios distintos.

### Crear las credenciales en Google Cloud

1. Abre <https://console.cloud.google.com/> y crea o selecciona un proyecto.
2. En **APIs y servicios > Biblioteca**, habilita **Google Calendar API**.
3. En **Google Auth Platform > Branding**, configura nombre de aplicación,
   correo de soporte y datos de contacto.
4. En **Audience**:
   - usa `External` para una cuenta Gmail;
   - mientras la aplicación esté en pruebas, añade `clinica@gmail.com` como
     usuario de prueba.
5. En **Data Access**, configura los scopes utilizados por la aplicación:
   - `openid`
   - `https://www.googleapis.com/auth/userinfo.email`
   - `https://www.googleapis.com/auth/calendar`
6. En **Clients**, crea un cliente OAuth de tipo **Web application**.
7. Añade como **Authorized redirect URI** exactamente el valor de
   `GOOGLE_REDIRECT_URI`, por ejemplo:

   ```text
   https://tu-subdominio.ngrok-free.app/auth/google/callback
   ```

8. Copia el Client ID y Client Secret a:

   ```dotenv
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=https://tu-dominio/auth/google/callback
   ```

9. Genera una clave Fernet independiente para cifrar los tokens OAuth:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Guarda el resultado como `GOOGLE_TOKEN_ENCRYPTION_KEY`. Si pierdes o cambias
   esta clave, los tokens almacenados dejarán de poder descifrarse y tendrás
   que autorizar de nuevo la cuenta.

### Autorizar la cuenta de la clínica

Con la aplicación y el túnel arrancados:

1. Obtén el UUID de la clínica en PostgreSQL.
2. Abre en el navegador:

   ```text
   https://tu-dominio/auth/google/start?clinic_id=<UUID_DE_LA_CLINICA>
   ```

3. Inicia sesión como `clinica@gmail.com` y acepta el acceso.
4. El callback cifra y guarda access token y refresh token en
   `google_credentials`.

El acceso se solicita en modo offline. Cuando el access token caduca, la
aplicación utiliza el refresh token y vuelve a guardar el token actualizado de
forma cifrada.

### Endpoints de Calendar

```text
GET  /auth/google/start?clinic_id=...
GET  /auth/google/callback
GET  /api/calendar/status?clinic_id=...
GET  /api/calendar/list?clinic_id=...
POST /api/workers/{worker_id}/create-calendar
POST /api/workers/{worker_id}/link-calendar
POST /api/admin/clinics/{clinic_id}/workers/{worker_id}/test-freebusy
```

Para vincular un calendario existente:

```json
{
  "calendar_id": "calendar-id@group.calendar.google.com",
  "color_id": "7"
}
```

Para crear un calendario puedes omitir el body o personalizarlo:

```json
{
  "summary": "Clínica - Ana",
  "color_id": "2"
}
```

Tras ejecutar `make seed` y completar OAuth, crea o reutiliza los calendarios
demo exactos `Clínica - Ana` y `Clínica - Luis` con:

```bash
make calendar-demo
```

La capa Calendar también incluye:

- consulta FreeBusy independiente por `calendar_id`;
- listado de colores de eventos;
- inserción de eventos en el calendario del trabajador;
- soporte para `colorId`;
- `extendedProperties.private` con `worker_id`, `source` y `call_id`.

### Motor de scheduling

`app/calendar/scheduler.py` propone hasta tres huecos reales combinando:

- horario semanal `working_hours_json` de cada trabajador;
- duración del servicio y buffers anterior/posterior;
- FreeBusy de todos los calendarios candidatos;
- fecha y franja preferidas (`morning`, `afternoon`, `evening` o
  `HH:MM-HH:MM`);
- zona horaria IANA de la clínica, incluidos cambios de horario.

Los candidatos se generan en intervalos de 15 minutos. Cuando no se solicita
un trabajador concreto, se mantienen alternativas de calendarios diferentes,
incluso para la misma hora. Antes de insertar un evento debe ejecutarse
`check_slot_available(...)` para repetir la comprobación contra Google y evitar
reservas concurrentes.

### Endpoints internos del agente

Las herramientas del agente de voz consumen:

```text
POST /api/agent/check_availability
POST /api/agent/propose_slots
POST /api/agent/create_appointment
POST /api/agent/cancel_appointment
POST /api/agent/get_clinic_info
```

Todas las rutas `/api/*` requieren:

```text
X-Internal-API-Key: valor-de-INTERNAL_API_KEY
```

La creación de citas:

- bloquea transaccionalmente la fila del trabajador;
- comprueba solapes en PostgreSQL y vuelve a consultar Google FreeBusy;
- crea el evento con `appointment_id`, `worker_id`, `source` y
  `call_session_id` en `extendedProperties.private`;
- guarda el `google_event_id` y confirma la cita en PostgreSQL;
- elimina el evento de Google como compensación si falla la escritura local.

La cancelación elimina el evento de Google y marca la cita como `cancelled`;
el registro histórico nunca se borra.

## API administrativa multi-clínica

El panel React incluido puede gestionar clínicas, números, trabajadores, calendarios,
servicios, precios, configuraciones del asistente, prompts, conocimiento,
flujos, llamadas, conversaciones y citas bajo:

```text
/api/admin/clinics
/api/admin/clinics/{clinic_id}
/api/admin/clinics/{clinic_id}/phone-numbers
/api/admin/clinics/{clinic_id}/workers
/api/admin/clinics/{clinic_id}/services
/api/admin/clinics/{clinic_id}/assistant-configs
/api/admin/clinics/{clinic_id}/knowledge
/api/admin/clinics/{clinic_id}/flows
/api/admin/clinics/{clinic_id}/calls
/api/admin/clinics/{clinic_id}/appointments
/api/admin/clinics/{clinic_id}/calendar-status
/api/admin/clinics/{clinic_id}/calendars
/api/admin/clinics/{clinic_id}/workers/{worker_id}/create-calendar
/api/admin/clinics/{clinic_id}/workers/{worker_id}/link-calendar
/api/admin/clinics/{clinic_id}/workers/{worker_id}/test-freebusy
/api/admin/clinics/{clinic_id}/prompt-context-preview
/api/admin/assistant-options
/api/admin/clinics/{clinic_id}/assistant-configs/{config_id}/activate
```

Las colecciones aceptan `page` y `page_size`. Según el recurso también
aceptan filtros como `is_active`, `date`, `worker_id`, `service_id`, `status`
y `outcome`.

Todas estas rutas exigen una clave distinta de la API interna:

```text
X-Admin-API-Key: valor-de-ADMIN_API_KEY
```

Para este MVP no existe login de usuario, roles ni sesiones de navegador. No
expongas `ADMIN_API_KEY` directamente en código JavaScript público. El
frontend deberá llamar desde una capa servidor segura hasta implementar
autenticación de usuarios.

Solo puede existir una configuración de asistente activa por clínica. El
webhook SIP selecciona esa configuración y carga sus prompts y elementos de
conocimiento activos al aceptar una llamada.

Las citas creadas desde `/api/admin` se guardan como `admin_panel` y bloquean
disponibilidad local, pero no crean ni eliminan eventos de Google Calendar.
Las citas creadas por el agente continúan usando el flujo transaccional con
Google.

El panel React está en `../frontend`. Flujo operativo recomendado:

1. crear la clínica;
2. añadir el número y el destino SIP;
3. conectar la cuenta Google;
4. crear trabajadores y sus horarios;
5. crear o enlazar calendarios y probar FreeBusy;
6. crear servicios;
7. configurar el asistente;
8. probar la conversación.

El endpoint `prompt-context-preview` devuelve únicamente servicios,
trabajadores y elementos de conocimiento activos. También avisa cuando faltan
precios, servicios reservables, contexto o una configuración activa.

En el prompt final:

- nunca se inventan precios;
- un precio ausente se presenta como no especificado y se deriva a recepción;
- los servicios no reservables pueden explicarse, pero no se envían a las
  herramientas de reserva;
- los elementos de conocimiento inactivos quedan fuera del contexto.

### Configuración del asistente

Cada `AssistantConfig` guarda modelo, voz, idioma, saludo, prompts, políticas,
preferencias de transcripción/grabación y retención. La activación de una
configuración desactiva la configuración activa anterior de la misma clínica.

Los modelos y voces permitidos se publican desde `/api/admin/assistant-options`
y se configuran localmente con:

```dotenv
OPENAI_REALTIME_MODELS=gpt-realtime-2
OPENAI_REALTIME_VOICES=marin,cedar,alloy,ash,ballad,coral,echo,sage,shimmer,verse
```

OpenAI recomienda `marin` y `cedar` para mejor calidad. No existe una voz
documentada específica para español de España o gallego; el idioma y variante
se dirigen mediante `language` y las instrucciones.

La transcripción se aplica a nuevas llamadas según la configuración activa.
La preferencia de grabación se persiste en `CallSession`, pero este MVP aún no
captura ni almacena audio.

Referencias oficiales:

- <https://developers.google.com/identity/protocols/oauth2/web-server>
- <https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert>
- <https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query>
- <https://developers.google.com/workspace/calendar/api/v3/reference/events/insert>

## Flujo SIP

Según la guía oficial de OpenAI Realtime SIP:

1. Crea un webhook de proyecto en OpenAI apuntando a
   `https://tu-dominio/webhooks/openai/realtime`.
2. Configura el forwarding SIP de VoIP Studio hacia:

   ```text
   sip:<OPENAI_PROJECT_ID>@sip.api.openai.com;transport=tls
   ```

3. Cuando llega `realtime.call.incoming`, la API verifica la firma, crea la
   `CallSession`, acepta la llamada y abre el WebSocket asociado al `call_id`.

Documentación oficial:
<https://developers.openai.com/api/docs/guides/realtime-sip>

Prueba primero el flujo con el simulador local.

## Comandos

```text
make dev                         Arranca app + PostgreSQL
make test                        Ejecuta pytest en Docker
make lint                        Ejecuta Ruff y mypy
make migrate                     Aplica migraciones pendientes
make seed                        Crea datos demo de forma idempotente
make calendar-demo               Crea/vincula calendarios demo en Google
make simulate                    Simula una llamada con calendario en memoria
make simulate-google             Simula una llamada con Google Calendar real
make purge-calls                 Purga llamadas según data_retention_days
make revision MESSAGE="cambio"   Genera una migración
```

## Ejecución sin Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

En Windows, activa el entorno con `.venv\Scripts\Activate.ps1`.
Para conectar contra PostgreSQL publicado por Compose desde el host, cambia
`@postgres:5432` por `@localhost:5432` en `DATABASE_URL`.

## Despliegue posterior en VPS

Producción usa `docker-compose.prod.yml` y Caddy con TLS automático:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
chmod +x deploy.sh scripts/backup_postgres.sh
./deploy.sh
```

Guía completa:

- [Despliegue en VPS](docs/deployment-vps.md)
- [Despliegue gratuito Cloudflare + Render + Supabase](docs/deployment-free-tier.md)
- [Despliegue completo en Render](docs/deployment-render.md)
- [Privacidad del MVP](docs/privacy-mvp.md)
- [Prompts dinámicos por clínica](docs/dynamic-clinic-prompts.md)
- [VoIP Studio y OpenAI SIP](docs/voipstudio-openai-sip.md)

También puedes desplegar la opción gratuita con `../render.yaml`: backend
Docker en Render Free, frontend en Cloudflare Pages y PostgreSQL en Supabase
Free. El `render.yaml` actual no crea una base de datos Render. Render ejecuta
`alembic upgrade head` antes de arrancar y el backend usa `PORT`.

En producción:

- usa secretos gestionados fuera del repositorio;
- no publiques PostgreSQL en Internet;
- ejecuta `alembic upgrade head` durante el despliegue;
- configura backups, monitorización y rotación de logs;
- deja `ENABLE_CALL_TRANSCRIPTION=false` salvo necesidad justificada;
- programa `python -m scripts.purge_calls`;
- prueba la verificación de firma antes de recibir llamadas.

Endpoints de salud:

```text
GET /health/live
GET /health/ready
```

`/health/ready` comprueba PostgreSQL. Las rutas `/dev/*`, Swagger y OpenAPI no
se cargan en producción.

## Estructura

```text
app/
├── api/                 Endpoints HTTP
├── calendar/            Frontera de Google Calendar
├── openai_realtime/     Frontera de OpenAI Realtime SIP
├── utils/               Logging y seguridad
├── config.py            Pydantic Settings
├── db.py                SQLAlchemy
├── main.py              Aplicación FastAPI
├── models.py            Modelos ORM
├── prompts.py           Instrucciones del agente
└── schemas.py           Esquemas Pydantic
```
