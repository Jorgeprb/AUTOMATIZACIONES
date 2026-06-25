# Recepcionista App · V1

Plataforma multi-clínica con asistente telefónico, agenda Google Calendar,
OpenAI Realtime SIP y panel web de administración.

## Arranque local completo

Requisitos: Docker Desktop o Docker Engine con Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

El mismo comando:

- arranca PostgreSQL;
- aplica Alembic automáticamente;
- arranca FastAPI en <http://localhost:8000>;
- arranca el panel React en <http://localhost:5173>.

Swagger: <http://localhost:8000/docs>.

Para cargar la clínica demo:

```powershell
docker compose run --rm app python -m scripts.seed_demo
```

Comprueba:

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

## Variables necesarias

Copia [.env.example](./.env.example). Las variables principales son:

- `ADMIN_API_KEY` y `VITE_ADMIN_API_KEY`: deben coincidir.
- `OPENAI_API_KEY`, `OPENAI_WEBHOOK_SECRET`, `OPENAI_PROJECT_ID`.
- `PUBLIC_BASE_URL`: dominio HTTPS público de la API.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
- `GOOGLE_TOKEN_ENCRYPTION_KEY`: clave Fernet para tokens OAuth.
- `DATABASE_URL` es reemplazada por Docker en local.

No guardes `.env` ni secretos reales en Git.

## Puesta en marcha de una clínica

1. Crea la clínica y completa contacto, horario y mensaje de emergencia.
2. Añade el número de teléfono, destino SIP y webhook HTTPS.
3. Conecta Google Calendar mediante OAuth.
4. Crea trabajadores y enlaza un calendario secundario a cada uno.
5. Crea servicios, precios y contexto.
6. Activa una configuración del asistente y revisa el prompt.
7. Completa una conversación en la consola de prueba.
8. Configura el webhook OpenAI:
   `https://TU_DOMINIO/webhooks/openai/realtime`.
9. Configura VoIP Studio para reenviar a:
   `sip:${OPENAI_PROJECT_ID}@sip.api.openai.com;transport=tls`.
10. Haz una llamada real y comprueba el dashboard.

El dashboard muestra estadísticas y una checklist automática con enlaces a
cada pantalla pendiente.

## Google Calendar

En Google Cloud:

1. habilita Google Calendar API;
2. crea credenciales OAuth de aplicación web;
3. usa `https://TU_DOMINIO/auth/google/callback` como redirect URI;
4. conecta la cuenta desde la pantalla Calendario;
5. crea o enlaza un calendario por trabajador.

No se usan service accounts.

## Exposición local

```powershell
ngrok http 8000
```

o:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Actualiza `PUBLIC_BASE_URL` y `GOOGLE_REDIRECT_URI`, reinicia Compose y crea el
webhook público en OpenAI.

## VPS y HTTPS

La guía completa está en
[deployment-vps.md](./clinic-voice-agent/docs/deployment-vps.md).

Resumen:

1. apunta `voice.example.com` y `admin.voice.example.com` al VPS;
2. copia `clinic-voice-agent/.env.production.example` a `.env.production`;
3. configura `APP_DOMAIN`, `APP_ADMIN_DOMAIN` y todos los secretos;
4. ejecuta desde `clinic-voice-agent`:

   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

Caddy obtiene TLS automáticamente. La API queda en `APP_DOMAIN` y el panel en
`APP_ADMIN_DOMAIN`.

## Pruebas

Backend:

```powershell
cd clinic-voice-agent
docker compose run --rm app pytest
docker compose run --rm app ruff check app tests
docker compose run --rm app mypy app
```

Frontend:

```powershell
cd frontend
npm run test
npm run build
```

## Seguridad del MVP

El panel V1 envía `ADMIN_API_KEY` desde el navegador. Es suficiente para una
instalación privada controlada, pero no para una plataforma pública con
usuarios externos. La siguiente fase debe incorporar login, sesiones y roles.
