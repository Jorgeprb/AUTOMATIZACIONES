# Despliegue en Render

> Nota: esta guía describe la alternativa de ejecutar backend, frontend y
> PostgreSQL dentro de Render. La opción gratuita actual usa Render solo para
> el backend, Cloudflare Pages para el frontend y Supabase Free para
> PostgreSQL. Sigue [deployment-free-tier.md](deployment-free-tier.md) para esa
> configuración. El `render.yaml` actual de la raíz no crea Postgres de Render
> ni Static Site de Render.

Este proyecto se despliega en Render como monorepo:

- `clinic-voice-agent/`: backend FastAPI como Web Service Docker.
- `frontend/`: panel React/Vite como Static Site.
- PostgreSQL: base de datos gestionada por Render.

El archivo raíz `render.yaml` define los tres recursos.

## 1. Crear Blueprint

1. Sube el repositorio a GitHub.
2. En Render, crea un nuevo **Blueprint** desde el repositorio.
3. Render leerá `render.yaml` y creará:
   - `clinic-voice-agent-db`;
   - `clinic-voice-agent-api`;
   - `clinic-voice-agent-admin`.

No dividas el repositorio. Render usa rutas dentro del monorepo.

## 2. Backend: variables en Render

En el servicio `clinic-voice-agent-api`, Render rellena automáticamente:

```env
DATABASE_URL=<connectionString de clinic-voice-agent-db>
APP_ENVIRONMENT=production
```

Configura manualmente estas variables:

```env
PUBLIC_BASE_URL=https://BACKEND_RENDER_URL
FRONTEND_BASE_URL=https://FRONTEND_RENDER_URL
CORS_ORIGINS=https://FRONTEND_RENDER_URL

ADMIN_API_KEY=clave-larga-para-panel
INTERNAL_API_KEY=otra-clave-larga-para-endpoints-internos

OPENAI_API_KEY=...
OPENAI_WEBHOOK_SECRET=...
OPENAI_PROJECT_ID=...

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://BACKEND_RENDER_URL/auth/google/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=...
```

Genera `GOOGLE_TOKEN_ENCRYPTION_KEY` una sola vez y no la cambies después de
conectar Google:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`DATABASE_URL` puede venir de Render como `postgresql://...`; el backend lo
normaliza internamente a `postgresql+psycopg://...`.

## 3. Frontend: variables en Render

En el Static Site `clinic-voice-agent-admin`, configura:

```env
VITE_API_BASE_URL=https://BACKEND_RENDER_URL
VITE_ENABLE_DEV_FALLBACKS=false
```

El panel usa `/auth/login` y cookies HttpOnly. No configures claves administrativas
en variables `VITE_*`, porque todo valor de Vite es público.

## 4. Migraciones

El backend ejecuta:

```bash
alembic upgrade head
```

como `preDeployCommand` antes de arrancar. Si falla una migración, Render no
debe promover el nuevo deploy.

El arranque Docker usa el puerto de Render:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
```

## 5. Google OAuth en Render

En Google Cloud:

1. Habilita Google Calendar API.
2. Crea credenciales OAuth de tipo **Web application**.
3. Añade el origen JavaScript:

   ```text
   https://FRONTEND_RENDER_URL
   ```

4. Añade redirect URI:

   ```text
   https://BACKEND_RENDER_URL/auth/google/callback
   ```

5. Copia `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y
   `GOOGLE_REDIRECT_URI` al backend en Render.

Después abre el panel, entra en Calendario y pulsa “Conectar Google Calendar”.
Si falta algo en `.env`, el panel mostrará la variable exacta.

## 6. OpenAI y VoIP

En OpenAI configura el webhook:

```text
https://BACKEND_RENDER_URL/webhooks/openai/realtime
```

Render aloja API/panel, pero no sustituye al edge SIP UDP del VPS. VoIP
Studio debe apuntar siempre a:

```text
sip:bot@sip.autogal.es:6060;transport=udp
```

El destino Hosted SIP de OpenAI es interno y no se entrega al cliente.

## 7. Comprobaciones

Backend:

```bash
curl https://BACKEND_RENDER_URL/health/live
curl https://BACKEND_RENDER_URL/health/ready
```

Frontend:

```text
https://FRONTEND_RENDER_URL
```

En Render revisa logs del backend. Debes ver migraciones Alembic y arranque de
Uvicorn.
