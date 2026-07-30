# Homogeneización del portal administrador y gestión de usuarios/clínicas

Fecha: 2026-07-30

## Alcance

La modificación se limita a `admin.autogal.es` y al flujo administrativo de asignación de números. No cambia reservas, SIP, OpenAI Realtime, Stripe Checkout, portal cliente ni el esquema de PostgreSQL.

## Navegación de administración

Se elimina el Dashboard del portal administrador. La ruta `/` y el acceso inicial tras login redirigen a:

```text
/users
```

La sección pasa a llamarse **Usuarios y clínicas**.

La navegación de **Clínica activa** utiliza el mismo formato del portal cliente:

```text
Ajustes de la clínica
Configuración del asistente
Clientes
Estadísticas
Conversaciones
Consola de prueba
```

`Ajustes de la clínica` agrupa:

- Datos generales
- Trabajadores
- Recursos
- Servicios
- Integración de calendario
- Conocimiento

Las rutas antiguas se conservan para compatibilidad, pero el menú y los accesos desde la lista de clínicas llevan al formato agrupado.

## Usuarios y clínicas

`GET /api/admin/users` incorpora, dentro de cada membresía:

- números de teléfono de la clínica;
- estado activo/inactivo del número;
- compras de número pagadas pendientes de asignación;
- identificador de la provisión para abrir el panel técnico.

La página muestra todos los usuarios, sus clínicas y sus números. Las provisiones pendientes aparecen destacadas encima del listado y dentro de la clínica afectada.

## Asignación de números

El botón **Asignar número** redirige a:

```text
/business?provisioning=<id>&mode=assign
```

El panel de provisión se abre automáticamente con estado `active`. Al guardar:

1. valida que el número no pertenezca a otra clínica;
2. crea o actualiza `PhoneNumber` con un `label` válido;
3. normaliza el proveedor `voip_studio` a `voipstudio`;
4. copia SIP target, webhook, ID externo y notas;
5. actualiza `Clinic.main_phone_number`;
6. activa el entitlement del número;
7. encola el email `number_activated` mediante `IntegrationOutbox`.

El email se envía al `billing_email` configurado en la cuenta comercial. La clave de deduplicación evita notificaciones repetidas:

```text
number-active:<provisioning_order_id>
```

## Migraciones

No se crea migración. La cabeza sigue siendo:

```text
20260730_0023 (head)
```

## Validación realizada

- `python -m compileall`: correcto.
- Import FastAPI/SQLAlchemy: 170 rutas y 37 tablas.
- TypeScript estricto: correcto.
- Pruebas nuevas de usuarios/clínicas y provisión: 2 superadas.
- SIP gateway: 44 pruebas superadas.
- `git diff --check`: correcto.
- Alembic: una única cabeza.

El build Vite no pudo completarse en el entorno de análisis porque el `node_modules` adjunto carece del binario opcional Linux `@rollup/rollup-linux-x64-gnu`. El ZIP final no incluye `node_modules`; Docker ejecutará `npm ci` en Linux.

## Despliegue

No ejecutar migraciones.

```bash
cd /opt/AUTOMATIZACIONES

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  build --no-cache api frontend

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  up -d --force-recreate api frontend caddy
```

`client-frontend` utiliza el mismo código fuente, pero no contiene cambios funcionales para este alcance. Puede reconstruirse también si se desea mantener ambas imágenes sincronizadas.
