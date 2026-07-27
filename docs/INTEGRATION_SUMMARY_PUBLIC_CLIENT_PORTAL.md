# Integración web pública y portal de clientes

## Entregado

- Web pública independiente en `public-frontend/`, convertida a Vite/React estándar.
- Eliminación total de metadatos, dependencias, configuraciones y nombres procedentes del generador original.
- Panel administrador existente compilado en modo `admin`.
- Nuevo panel de clientes compilado desde el mismo código en modo `client`.
- Aislamiento por `AdminMembership` para una o varias clínicas por cuenta.
- Gestión de clientes y asignación de clínicas desde el panel global.
- Google OpenID Connect con state de un solo uso, nonce y PKCE.
- Cookies de sesión compartidas de forma segura entre subdominios de `autogal.es`.
- Redirección automática al portal correspondiente según el rol.
- Caddy y Docker Compose para `www`, `client`, `admin`, `voice` y dominio raíz.
- Páginas públicas de aviso legal, privacidad y cookies preparadas para completar los datos legales del titular.

## Principio de seguridad

El frontend cliente no es una copia con datos descargados globalmente. Cada petición se autentica en FastAPI y los endpoints con `clinic_id` se validan contra las membresías de la cuenta. Las listas de clínicas se filtran en SQL. Un usuario cliente no puede eludirlo cambiando rutas, parámetros o llamadas HTTP.

## Alta recomendada

`GOOGLE_LOGIN_AUTO_PROVISION=false`: primero se crea el acceso desde el panel administrador, se indica el email Google exacto y se asignan las clínicas. Solo entonces esa cuenta puede iniciar sesión.
