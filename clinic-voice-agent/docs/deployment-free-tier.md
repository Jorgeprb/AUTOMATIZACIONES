# Despliegue gratuito: Cloudflare Pages + Render Free + Supabase Free

Este modo mantiene el monorepo actual:

```text
Recepcionista_App/
├── clinic-voice-agent/   Backend FastAPI
├── frontend/             Panel React/Vite
└── render.yaml           Solo backend Render
```

No se usa PostgreSQL de Render ni Cloud SQL.

## Arquitectura

```text
Usuario navegador
  → Cloudflare Pages, frontend React/Vite
  → Render Free Web Service, backend FastAPI
  → Supabase Free, PostgreSQL

OpenAI Realtime SIP
  → https://BACKEND_RENDER_URL/webhooks/openai/realtime
  → FastAPI
  → Google Calendar / Supabase
```

## Supabase Free: PostgreSQL

1. Crea un proyecto en Supabase.
2. En **Project Settings > Database** copia la connection string.
3. Para este backend conviene empezar con **Direct connection** si Render puede
   conectar sin problema. Es simple para FastAPI, Alembic y SQLAlchemy.
4. Si la direct connection falla por red IPv4/IPv6 o hay muchas conexiones,
   usa **Session pooler**.
5. Evita **Transaction pooler** para este MVP salvo que se pruebe bien con
   SQLAlchemy/Alembic, porque puede ser mÃ¡s delicado con sesiones y
   transacciones largas.

Ejemplo direct connection:

```text
postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres
```

Ejemplo pooler:

```text
postgresql://postgres.PROJECT:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres
```

La aplicaciÃ³n acepta `postgresql://` y `postgres://`, los convierte a
`postgresql+psycopg://` y, si detecta host de Supabase sin `sslmode`, aÃ±ade:

```text
sslmode=require
```

## Render Free: backend FastAPI

El `render.yaml` de la raÃ­z crea solo un Web Service:

- root del repo: raÃ­z del monorepo;
- Dockerfile: `clinic-voice-agent/Dockerfile`;
- Docker context: `clinic-voice-agent`;
- plan: `free`;
- health check: `/health/ready`;
- comando:

```bash
sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"
```

Render inyecta `PORT`; localmente queda fallback `10000`.

Variables de entorno backend en Render:

```dotenv
APP_ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_URL=postgresql://...supabase...
PUBLIC_BASE_URL=https://BACKEND_RENDER_URL
FRONTEND_BASE_URL=https://FRONTEND_CLOUDFLARE_URL
CORS_ORIGINS=https://FRONTEND_CLOUDFLARE_URL
ADMIN_API_KEY=clave-larga-minimo-32-caracteres
INTERNAL_API_KEY=otra-clave-larga-minimo-32-caracteres

OPENAI_API_KEY=...
OPENAI_WEBHOOK_SECRET=...
OPENAI_PROJECT_ID=...
OPENAI_REALTIME_MODEL=gpt-realtime-2
OPENAI_REALTIME_VOICE=marin

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://BACKEND_RENDER_URL/auth/google/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=clave-fernet

CLINIC_TIMEZONE=Europe/Madrid
CLINIC_NAME=Clinica Demo
CLINIC_PHONE_NUMBER=+34910000000
```

Generar Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Cloudflare Pages: frontend React/Vite

En Cloudflare Pages:

- conecta el mismo repositorio;
- root directory: `frontend`;
- build command: `npm ci && npm run build`;
- output directory: `dist`;
- framework preset: React/Vite si aparece.

Variables de entorno frontend:

```dotenv
VITE_API_BASE_URL=https://BACKEND_RENDER_URL
VITE_ADMIN_API_KEY=misma-clave-que-ADMIN_API_KEY
VITE_ENABLE_DEV_FALLBACKS=false
```

El archivo `frontend/public/_redirects` mantiene funcionando las rutas React al
refrescar:

```text
/* /index.html 200
```

## CORS

En Render, configura:

```dotenv
FRONTEND_BASE_URL=https://FRONTEND_CLOUDFLARE_URL
CORS_ORIGINS=https://FRONTEND_CLOUDFLARE_URL
```

`FRONTEND_BASE_URL` tambiÃ©n se aÃ±ade automÃ¡ticamente a la lista CORS.

## Google OAuth

En el backend:

```dotenv
PUBLIC_BASE_URL=https://BACKEND_RENDER_URL
FRONTEND_BASE_URL=https://FRONTEND_CLOUDFLARE_URL
GOOGLE_REDIRECT_URI=https://BACKEND_RENDER_URL/auth/google/callback
```

En Google Cloud, cliente OAuth web:

- Authorized JavaScript origins:

  ```text
  https://FRONTEND_CLOUDFLARE_URL
  ```

- Authorized redirect URIs:

  ```text
  https://BACKEND_RENDER_URL/auth/google/callback
  ```

## OpenAI webhook y SIP

Webhook de OpenAI:

```text
https://BACKEND_RENDER_URL/webhooks/openai/realtime
```

Destino SIP:

```text
sip:${OPENAI_PROJECT_ID}@sip.api.openai.com;transport=tls
```

## Orden recomendado

1. Crea Supabase y copia `DATABASE_URL`.
2. Despliega backend en Render desde `render.yaml`.
3. Rellena variables backend en Render.
4. Comprueba:

   ```text
   https://BACKEND_RENDER_URL/health/live
   https://BACKEND_RENDER_URL/health/ready
   ```

5. Despliega frontend en Cloudflare Pages.
6. Rellena variables frontend en Cloudflare.
7. Actualiza `FRONTEND_BASE_URL` y `CORS_ORIGINS` en Render.
8. Configura Google OAuth con URLs pÃºblicas.
9. Configura webhook OpenAI.
10. Entra al panel, conecta Google y prueba la consola.

## Notas del plan gratis

- Render Free puede dormir tras inactividad; la primera llamada puede tardar.
- Supabase Free tambiÃ©n puede pausar o tener lÃ­mites.
- El login del frontend es solo barrera MVP en navegador.
- `ADMIN_API_KEY` sigue llegando al navegador; no es arquitectura final segura.

## Referencias oficiales

- Render Blueprints: <https://render.com/docs/blueprint-spec>
- Cloudflare Pages build config: <https://developers.cloudflare.com/pages/configuration/build-configuration/>
- Supabase Postgres connections: <https://supabase.com/docs/guides/database/connecting-to-postgres>
