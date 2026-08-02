# Correcciones finales Autogal — registro, compra previa a clínica y regresiones

Fecha: 2026-08-02

## Alcance

Esta entrega parte de `Recepcionista_App(9).zip` y aplica exclusivamente las correcciones solicitadas para registro y sesión, primer acceso sin clínica, compra y provisión de números, carrito y Stripe Checkout, navegación cliente/admin, eliminación de configuraciones y clientes, trabajadores, Google Calendar, conversaciones, dashboard y desbloqueo comercial.

No se ha reescrito `models.py`, autenticación, SIP, OpenAI Realtime, Azure TTS ni reservas. Los cambios son acumulativos y mantienen el aislamiento multi-tenant.

## Causas raíz identificadas

### Registro y aparente cierre de sesión

El backend ya creaba la sesión de navegador y las cookies durante `POST /auth/register`, pero React ignoraba la identidad devuelta y redirigía al onboarding. Además, el middleware de desbloqueo comercial interceptaba `/auth/me` con `402` para una cuenta nueva. El frontend podía interpretar esa respuesta como un problema de sesión.

Corrección:

- el registro conserva exactamente el mismo sistema de `AdminSession`, cookie HttpOnly y CSRF que el login;
- React utiliza la identidad devuelta y navega al Dashboard;
- `/auth/me` y `/auth/logout` son accesibles aunque la cuenta comercial todavía esté bloqueada;
- la sesión solo se invalida si la comprobación de identidad confirma realmente `401`;
- se normalizan fechas timezone-naive de drivers históricos/SQLite antes de compararlas.

### Primer acceso sin clínica

La navegación suponía que siempre existía una clínica activa. Esto provocaba redirecciones, consultas tenant-scoped sin UUID válido y estados de carga permanentes.

Corrección:

- se elimina la redirección obligatoria al onboarding;
- Dashboard, Mis clínicas y Compras funcionan con `activeClinic=null`;
- las queries tenant-scoped quedan deshabilitadas hasta tener un `clinic_id` real;
- se limpia del almacenamiento cualquier clínica activa ya inexistente;
- la creación básica de clínica continúa disponible sin necesidad de haber comprado aún un número.

### Compra antes de crear clínica

`PurchaseOrder.clinic_id` ya era opcional, pero `PhoneProvisioningOrder.clinic_id` seguía siendo obligatorio. El webhook no podía representar una compra pagada pendiente de crear/vincular una clínica sin inventar un ID.

Corrección:

- `PhoneProvisioningOrder.clinic_id` pasa a ser nullable;
- la FK utiliza `ON DELETE SET NULL`;
- Stripe puede confirmar una compra permanente de número sin clínica;
- una suscripción mensual sí exige una clínica real;
- administración vincula después la provisión a una clínica del mismo `BillingAccount` antes de activar el número;
- no se generan clínicas ni UUID provisionales.

### Cesta y Checkout

La pantalla anterior no mantenía una cesta completa y estaba demasiado ligada a una clínica. También faltaba una ruta directa fiable desde el Dashboard.

Corrección:

- catálogo obtenido del servidor;
- cesta persistida en `localStorage`;
- `?add=phone_number` añade automáticamente una unidad del precio `phone_number_once`;
- aumentar, reducir y eliminar unidades;
- subtotales separados de pago único y mensualidad;
- protección frente a doble clic;
- selección de clínica solo cuando existen líneas recurrentes;
- el navegador envía únicamente `price_id` y cantidad;
- el servidor vuelve a consultar `BillingPrice` y calcula los importes reales;
- Checkout en modo `payment` o `subscription` según el contenido válido del pedido.

### Dashboard después de compra o asignación

Las consultas y serializadores asumían registros completos: SIP, webhook, relaciones y teléfonos no vacíos. También una compra confirmada sin clínica volvía a mostrar el CTA de compra.

Corrección:

- serialización segura de relaciones y cadenas opcionales/históricas;
- estados diferenciados: sin número, compra pagada sin clínica, pendiente, parcialmente provisionado y activo;
- una compra pagada sin clínica muestra el siguiente paso para crear/vincular una clínica;
- un número activo asignado manualmente desbloquea la cuenta aunque no exista pedido Stripe;
- el estado comercial se vuelve a consultar cada 15 segundos, al enfocar y al montar la página;
- el usuario no necesita cerrar sesión.

### Trabajadores

El listado dependía de `model_validate` sobre filas que podían contener campos nulos o antiguos incorporados por migraciones recientes, especialmente horarios y `inherit_clinic_hours`.

Corrección:

- serializer explícito y compatible con registros históricos;
- listado vacío estable;
- creación/edición de horario heredado o propio;
- eliminación segura;
- aislamiento por clínica conservado.

### Google Calendar

La falta de autorización o un fallo de Google podía convertirse en una respuesta similar a autenticación caducada.

Corrección:

- `428` cuando es necesario conectar/reconectar Google;
- `424` cuando falla la dependencia externa;
- nunca se usa `401` para una cuenta Google desconectada;
- serialización robusta de calendarios, colores y datos nulos;
- permisos y clínica se validan antes de acceder a Google.

### Conversaciones

La respuesta asumía que todas las llamadas tenían número, configuración, cliente, cita, análisis, transcripción y fechas completas. Los registros históricos podían carecer de varias relaciones.

Corrección:

- paginación y mapeo explícitos con SQLAlchemy 2;
- relaciones opcionales seguras;
- llamada fallida, sin análisis, sin cliente, sin número o con transcripción vacía;
- análisis con error;
- redacción que no sustituye cada carácter cuando el teléfono antiguo está vacío;
- aislamiento tenant-scoped conservado.

### Configuraciones del asistente

Existía el endpoint de borrado, pero no un comportamiento completo para la configuración activa ni la acción React.

Corrección:

- botón y confirmación;
- borrado tenant-scoped;
- si existe otra configuración, se activa una sustituta antes de eliminar la activa;
- si es la única activa, devuelve `409` claro para evitar dejar llamadas sin configuración;
- llamadas históricas no se eliminan;
- invalidación inmediata de React Query y mensajes de éxito/error.

### Clientes

La lista era visualmente pesada y la eliminación no estaba conectada en React.

Corrección:

- filas compactas con nombre, teléfono, email, profesional preferido, última interacción y acciones;
- confirmación de borrado;
- borrado físico solo cuando no existen citas ni llamadas relacionadas;
- anonimización cuando existe historial;
- snapshots históricos de llamada/cita se conservan;
- no se puede eliminar un cliente de otra clínica.

### Administración

La gestión de clínicas estaba fragmentada entre una página global y “Usuarios y clínicas”.

Corrección:

- se oculta la página global independiente y sus rutas antiguas redirigen a `/users`;
- botón `+ Clínicas y números` dentro de cada usuario;
- creación de clínica real asociada al usuario, membresía y `BillingAccount`;
- edición básica, números activos, provisiones pendientes y enlace de asignación;
- la asignación solo acepta una clínica real del mismo `BillingAccount`;
- cliente sigue sin poder modificar SIP, webhook o provisión técnica.

## Migración Alembic

Se ha creado una única migración lineal:

```text
20260730_0023 -> 20260802_0024
```

Archivo:

```text
clinic-voice-agent/alembic/versions/20260802_0024_unassigned_phone_provisioning.py
```

Operaciones:

```sql
ALTER TABLE phone_provisioning_orders
  DROP CONSTRAINT phone_provisioning_orders_clinic_id_fkey;

ALTER TABLE phone_provisioning_orders
  ALTER COLUMN clinic_id DROP NOT NULL;

ALTER TABLE phone_provisioning_orders
  ADD CONSTRAINT phone_provisioning_orders_clinic_id_fkey
  FOREIGN KEY (clinic_id) REFERENCES clinics(id) ON DELETE SET NULL;
```

No se ha modificado ninguna migración anterior y existe una sola cabeza:

```text
20260802_0024 (head)
```

## Endpoints principales corregidos

- `POST /auth/register`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /auth/onboarding/clinic`
- `POST /auth/onboarding/clinics`
- `GET /api/billing/catalog`
- `POST /api/billing/checkout`
- `GET /api/billing/summary`
- `GET /api/admin/clinics`
- `GET /api/admin/clinics/{clinic_id}/dashboard`
- `GET /api/admin/clinics/{clinic_id}/setup-status`
- CRUD de `/api/admin/clinics/{clinic_id}/workers`
- Calendar `/api/admin/clinics/{clinic_id}/calendar/*`
- conversaciones `/api/admin/clinics/{clinic_id}/calls`
- `DELETE /api/admin/clinics/{clinic_id}/assistant-configs/{config_id}`
- `DELETE /api/admin/clinics/{clinic_id}/customers/{customer_id}`
- `POST /api/admin/users/{user_id}/clinics`
- `PATCH /api/admin/provisioning/{order_id}`
- webhook Stripe y proyección de provisión pagada.

## Archivos modificados

Backend:

- `clinic-voice-agent/app/api/admin/accounts.py`
- `clinic-voice-agent/app/api/admin/activity.py`
- `clinic-voice-agent/app/api/admin/core.py`
- `clinic-voice-agent/app/api/admin/enterprise.py`
- `clinic-voice-agent/app/api/admin/overview.py`
- `clinic-voice-agent/app/api/auth.py`
- `clinic-voice-agent/app/api/billing.py`
- `clinic-voice-agent/app/api/calendar.py`
- `clinic-voice-agent/app/api/stripe_webhook.py`
- `clinic-voice-agent/app/api/workers.py`
- `clinic-voice-agent/app/auth.py`
- `clinic-voice-agent/app/calendar/google_client.py`
- `clinic-voice-agent/app/enterprise_schemas.py`
- `clinic-voice-agent/app/enterprise_service.py`
- `clinic-voice-agent/app/models.py`
- `clinic-voice-agent/app/utils/security.py`

Frontend:

- `frontend/src/App.tsx`
- `frontend/src/api/enterprise.ts`
- `frontend/src/api/users.ts`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/hooks/useActiveClinic.tsx`
- `frontend/src/hooks/useCommercialAccess.ts`
- `frontend/src/pages/AssistantConfigPage.tsx`
- `frontend/src/pages/BusinessAdminPage.tsx`
- `frontend/src/pages/ClientAccountsPage.tsx`
- `frontend/src/pages/CustomersPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/PurchasesPage.tsx`
- `frontend/src/pages/RegisterPage.tsx`

Migración y pruebas:

- `clinic-voice-agent/alembic/versions/20260802_0024_unassigned_phone_provisioning.py`
- `clinic-voice-agent/tests/test_final_regressions_20260802.py`

## Validaciones ejecutadas

### Correctas

- `python -m compileall`: correcto.
- Import FastAPI: 171 rutas.
- SQLAlchemy: 37 tablas y `configure_mappers()` correcto.
- `alembic heads`: `20260802_0024 (head)`.
- SQL PostgreSQL incremental de la migración: generado correctamente.
- Pruebas focalizadas de aceptación: 29 superadas, 1 omitida porque el índice parcial de configuración activa solo se representa fielmente en PostgreSQL.
- SIP gateway: 44 pruebas superadas.
- Frontend: `npm run typecheck` correcto.
- `git diff --check`: correcto.
- Compose: YAML válido y todos los contextos de build existen.

### Suite backend completa en SQLite con stubs locales

Se recolectaron 180 pruebas:

- 155 superadas;
- 5 omitidas;
- 20 fallidas.

No se declara la suite completa superada. Los fallos restantes se concentran en:

- tipos PostgreSQL no representables por SQLite (`JSONB`, UUID y el índice parcial de configuración activa);
- expectativas históricas de `403` donde el bloqueo comercial actual devuelve `402` antes de ejecutar una función no comprada;
- dobles locales mínimos de Google que devuelven `accounts.google.test` y no persisten un state OAuth real;
- doble local de OpenAI sin `webhooks`;
- tests históricos de consola que requieren un doble completo del modelo;
- una expectativa histórica de purga no relacionada con esta solicitud.

Estas limitaciones deben repetirse en PostgreSQL y con las dependencias reales dentro de Docker antes de promover a producción.

### No ejecutable en este entorno

- Vitest y Vite se detienen antes de cargar la aplicación porque el `node_modules` adjunto no contiene `@rollup/rollup-linux-x64-gnu`.
- Una instalación npm limpia tampoco es posible en el espejo disponible: no publica `zod@4.4.3`.
- La web pública no incluye dependencias instaladas en el entorno.
- No existen los binarios Docker ni Caddy.
- No hay PostgreSQL, Stripe ni Google reales.

El ZIP final no incluye `node_modules`; el build Docker del VPS debe ejecutar `npm ci` con acceso al registro npm normal.

## Despliegue en VPS

### 1. Backup

```bash
cd /opt
cp -a AUTOMATIZACIONES "AUTOMATIZACIONES.backup.$(date +%Y%m%d_%H%M%S)"
```

Realiza también un backup PostgreSQL/Supabase antes de migrar.

### 2. Sustituir el código

Extrae el ZIP completo en un directorio nuevo, conserva el `.env.production` real fuera del paquete y compara `.env.production.example` sin sobrescribir secretos.

### 3. Construir

```bash
cd /opt/AUTOMATIZACIONES

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  build --no-cache \
  migrate api sip-gateway frontend client-frontend public-frontend
```

### 4. Verificar cabeza antes de migrar

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  run --rm --entrypoint alembic migrate heads
```

Resultado esperado:

```text
20260802_0024 (head)
```

### 5. Migrar

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  run --rm migrate
```

No uses `alembic stamp` ni `docker compose down -v`.

### 6. Levantar

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  up -d --force-recreate \
  api sip-gateway frontend client-frontend public-frontend caddy
```

## Validación posterior al despliegue

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  logs --no-color --tail=300 \
  migrate api sip-gateway frontend client-frontend public-frontend caddy
```

```bash
docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  run --rm --entrypoint alembic migrate current
```

Debe indicar `20260802_0024`.

Pruebas en contenedores o entorno de desarrollo del VPS:

```bash
cd clinic-voice-agent
pytest
alembic heads

cd ../sip-gateway
pytest

cd ../frontend
npm ci
npm run typecheck
npm run test
npm run build

cd ../public-frontend
npm ci
npm run typecheck
npm run build
```

## Checklist manual de aceptación

### Usuario nuevo

- [ ] Se registra y recibe sesión sin volver al login.
- [ ] `/auth/me` responde 200 después del registro.
- [ ] Abre Dashboard, Mis clínicas y Compras conservando sesión.
- [ ] No se le obliga a crear una clínica.
- [ ] Dashboard muestra “Bienvenido a Autogal”.
- [ ] “Comprar un número” abre Compras con una unidad en la cesta.
- [ ] Puede modificar cantidad y completar Checkout sin clínica.
- [ ] No se producen peticiones tenant-scoped sin `clinic_id`.

### Después del pago

- [ ] Stripe test-mode confirma el pedido mediante webhook firmado.
- [ ] Se crea una provisión con `clinic_id=null` si aún no existe clínica.
- [ ] El Dashboard muestra compra confirmada/pendiente.
- [ ] El admin ve la provisión pendiente.
- [ ] El cliente puede crear una clínica básica y el admin vincularla.

### Asignación administrativa

- [ ] Admin selecciona una clínica real del mismo `BillingAccount`.
- [ ] Introduce y activa el número sin `500`.
- [ ] Se crea/actualiza `PhoneNumber` y `Clinic.main_phone_number`.
- [ ] Se encola un único email de activación.
- [ ] Desaparece el aviso pendiente.
- [ ] El estado comercial se actualiza sin cerrar sesión.
- [ ] Ajustes, Asistente, Clientes, Estadísticas, Conversaciones y Consola quedan accesibles.

### Funciones compartidas

- [ ] Trabajadores lista cero elementos sin error.
- [ ] Crea/edita trabajador con horario heredado.
- [ ] Crea/edita trabajador con horario propio.
- [ ] Calendar sin Google devuelve 428, no 401.
- [ ] Fallo externo de Google devuelve 424.
- [ ] Conversaciones carga llamadas incompletas/históricas.
- [ ] Se elimina una configuración no activa.
- [ ] La activa cambia a una sustituta o devuelve 409 si es la única.
- [ ] Cliente sin historial se elimina físicamente.
- [ ] Cliente con historial se anonimiza y conserva snapshots.
- [ ] No existe acceso cruzado entre clínicas.
- [ ] Cliente no puede modificar SIP, webhook ni provisión.
- [ ] Admin conserva acceso completo.
