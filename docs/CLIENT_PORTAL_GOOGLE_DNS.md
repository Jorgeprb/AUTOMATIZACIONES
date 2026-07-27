# Web pública, portal de clientes, Google Login y DNS

## Arquitectura de dominios

| Dominio | Servicio |
|---|---|
| `autogal.es` | Redirección permanente a `www.autogal.es` |
| `www.autogal.es` | Web pública de Autogal e inicio de sesión con Google |
| `client.autogal.es` | Portal de clientes limitado a sus clínicas |
| `admin.autogal.es` | Panel global reservado a superadministradores |
| `voice.autogal.es` | API pública, webhooks y OAuth de Google Calendar |

El panel de cliente y el panel administrador comparten el mismo código frontend. Se compilan en modos distintos, pero el aislamiento no depende de la interfaz: la API obtiene las clínicas permitidas de `admin_memberships` y valida cada ruta con `clinic_id`.

## Registros DNS en OVHcloud

La IP utilizada actualmente por el VPS es `51.210.180.115`. Sustitúyela si el VPS cambia de IP.

Antes de añadir registros, elimina únicamente entradas A, AAAA o CNAME que entren en conflicto con los mismos nombres. No elimines MX, SPF, DKIM o DMARC del correo.

Configuración recomendada:

| Subdominio en OVH | Tipo | Destino | TTL inicial |
|---|---|---|---:|
| `@` | A | `51.210.180.115` | 300 |
| `www` | CNAME | `autogal.es.` | 300 |
| `admin` | A | `51.210.180.115` | 300 |
| `client` | A | `51.210.180.115` | 300 |
| `voice` | A | `51.210.180.115` | 300 |

Cuando todo esté verificado, el TTL puede subirse a 3600 segundos.

En el panel de OVHcloud: **Web Cloud → Dominios y DNS → Zonas DNS → autogal.es → Añadir una entrada**. Para el CNAME de `www`, OVH suele mostrar el destino con punto final: `autogal.es.`.

No crees registros AAAA salvo que el VPS tenga IPv6 configurada, publicada en Docker/Caddy y permitida en el firewall. Un AAAA incorrecto puede hacer que algunos navegadores intenten una dirección que no responde.

## Google Auth Platform

Puede reutilizarse el mismo proyecto y OAuth Client ID que Google Calendar. El login usa solo `openid email profile`; Calendar conserva su callback y sus scopes propios.

En **Google Cloud Console → Google Auth Platform → Clients**, edita el cliente web y añade:

### Authorized JavaScript origins

- `https://www.autogal.es`
- `https://client.autogal.es`
- `https://admin.autogal.es`
- `https://voice.autogal.es`

### Authorized redirect URIs

- `https://client.autogal.es/auth/login/google/callback`
- `https://admin.autogal.es/auth/login/google/callback`
- `https://voice.autogal.es/auth/google/callback` — callback existente de Google Calendar

Las URI deben coincidir exactamente, incluyendo `https`, dominio, ruta y ausencia de barra final adicional.

En **Branding**, configura:

- App name: `Autogal`
- Home page: `https://www.autogal.es`
- Privacy policy: una URL pública real dentro de `www.autogal.es`
- Terms of service: una URL pública real dentro de `www.autogal.es`
- Authorized domains: `autogal.es`

Para pruebas, añade las cuentas en **Audience → Test users**. Para uso general, publica la aplicación. Si Calendar solicita scopes sensibles, Google puede requerir verificación adicional; el login básico `openid email profile` está separado de esa autorización.

## Variables de `.env.production`

```dotenv
APP_PUBLIC_DOMAIN=autogal.es
APP_PUBLIC_WWW_DOMAIN=www.autogal.es
APP_CLIENT_DOMAIN=client.autogal.es
APP_ADMIN_DOMAIN=admin.autogal.es
APP_DOMAIN=voice.autogal.es
CADDY_EMAIL=tu-email@autogal.es

PUBLIC_BASE_URL=https://voice.autogal.es
FRONTEND_BASE_URL=https://admin.autogal.es
ADMIN_FRONTEND_BASE_URL=https://admin.autogal.es
CLIENT_FRONTEND_BASE_URL=https://client.autogal.es
PUBLIC_SITE_BASE_URL=https://www.autogal.es
ADMIN_PORTAL_HOST=admin.autogal.es
CLIENT_PORTAL_HOST=client.autogal.es
AUTH_COOKIE_DOMAIN=.autogal.es
CORS_ORIGINS=https://admin.autogal.es,https://client.autogal.es,https://www.autogal.es

GOOGLE_LOGIN_ENABLED=true
GOOGLE_LOGIN_ADMIN_REDIRECT_URI=https://admin.autogal.es/auth/login/google/callback
GOOGLE_LOGIN_CLIENT_REDIRECT_URI=https://client.autogal.es/auth/login/google/callback
GOOGLE_LOGIN_ALLOWED_DOMAIN=
GOOGLE_LOGIN_AUTO_PROVISION=false

# Se conserva para vincular calendarios de las clínicas:
GOOGLE_REDIRECT_URI=https://voice.autogal.es/auth/google/callback
```

Mantén `GOOGLE_LOGIN_AUTO_PROVISION=false`. De este modo, iniciar sesión con una cuenta Google desconocida no crea un usuario con acceso. El superadministrador debe invitar previamente el email y asignarle una o varias clínicas en **Clientes y accesos**.

## Alta de un cliente

1. Entra en `https://admin.autogal.es` con un superadministrador.
2. Abre **Clientes y accesos**.
3. Crea el acceso con el email exacto de Google del cliente.
4. Asigna una o varias clínicas.
5. Elige el rol:
   - `Administrador de clínica`: puede editar toda la configuración de sus clínicas.
   - `Operador`: puede realizar cambios operativos permitidos.
   - `Solo lectura`: no puede modificar datos.
6. El cliente entra en `https://client.autogal.es` o pulsa **Acceder** en la web pública.

Un cliente no puede entrar en `admin.autogal.es`; la API lo rechaza aunque manipule el frontend o llame directamente a las rutas.

## Despliegue

```bash
cd /opt/AUTOMATIZACIONES

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  run --rm migrate

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  up -d --build --force-recreate \
  api frontend client-frontend public-frontend caddy
```

Comprobación:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps

docker compose -f docker-compose.prod.yml --env-file .env.production \
  logs --tail=150 api frontend client-frontend public-frontend caddy
```

Pruebas rápidas:

```bash
curl -I https://autogal.es
curl -I https://www.autogal.es
curl -I https://client.autogal.es
curl -I https://admin.autogal.es
curl -I https://voice.autogal.es/health/ready
```
