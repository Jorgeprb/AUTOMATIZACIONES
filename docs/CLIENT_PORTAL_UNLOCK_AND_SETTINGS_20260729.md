# Portal cliente: desbloqueo comercial y nuevos ajustes

Fecha: 2026-07-29

## Objetivo

El portal `client.autogal.es` comienza en modo bienvenida. Hasta que la cuenta comercial
haya comprado un producto `phone_number` con pedido confirmado o tenga un número activo
asignado por superadministración, el usuario solo puede utilizar:

- Dashboard.
- Mis clínicas.
- Compras y suscripciones.

El resto de opciones permanece visible, atenuado y con candado. La restricción también se
aplica en FastAPI y no puede evitarse escribiendo manualmente una URL o utilizando otro Host.
Los superadministradores no están sujetos al bloqueo.

El desbloqueo es por `BillingAccount`: una compra permanente o un número activo habilita
las funciones para todas las clínicas de esa cuenta. La compra del número no depende de la
suscripción mensual para mantener desbloqueado el portal.

## Estados del Dashboard

### Sin compra ni número

Muestra una bienvenida que explica:

- que el número Autogal es un número VoIP fijo;
- que se pueden redirigir hacia él las llamadas del teléfono habitual;
- que existe un número de demostración configurable con `DEMO_PHONE_NUMBER`;
- que la entrega puede tardar hasta 24 horas;
- un botón directo a Compras y suscripciones.

### Compra confirmada y provisión pendiente

El portal se desbloquea inmediatamente. El Dashboard muestra un aviso hasta que la
provisión se marca como `active` desde administración global.

### Número activo

El aviso de provisión desaparece. El Dashboard muestra accesos directos a:

- Ajustes de la clínica.
- Configuración del asistente.

## Navegación cliente

Siempre accesible:

1. Dashboard.
2. Mis clínicas.
3. Compras y suscripciones.

Bajo Clínica activa:

1. Ajustes de la clínica.
2. Configuración del asistente.
3. Clientes.
4. Estadísticas.
5. Conversaciones.
6. Calendario.
7. Consola de prueba.

`Ajustes de la clínica` agrupa:

- datos generales;
- trabajadores;
- recursos;
- servicios;
- integración de calendario;
- conocimiento.

## Seguridad de números

En el portal cliente:

- no se listan registros técnicos de `PhoneNumber`;
- no se permite crear, editar o eliminar números;
- no se exponen `sip_target`, `webhook_url`, proveedor, ID externo ni notas de provisión;
- no se muestra la tarjeta “Conectar VoIP Studio”;
- el formulario de clínica no permite cambiar `main_phone_number`.

Los endpoints de números requieren `super_admin`. La administración global conserva la
edición completa y el panel de provisión.

## Aviso administrativo

La administración global muestra:

- contador de provisiones pendientes en el menú;
- tarjeta destacada en Negocio y provisión;
- acceso directo al primer pedido pendiente;
- formulario para asignar número, proveedor, SIP target, webhook y estado.

Al marcar la provisión como `active`, se crea o actualiza `PhoneNumber`; el portal cliente
queda desbloqueado y el aviso pendiente desaparece.

## Backend

El estado comercial se calcula con `PortalAccessState`:

- compra pagada que contenga `BillingProduct.code == "phone_number"`;
- o un `PhoneNumber.is_active == true` perteneciente a una clínica del `BillingAccount`.

Los pedidos de provisión `paid_pending_provisioning` y `provisioned` alimentan el aviso de
activación pendiente.

No se ha creado migración: el cambio utiliza las tablas empresariales existentes y mantiene
una única cabeza Alembic `20260729_0022`.

## Validación realizada

- `python -m compileall`: correcto.
- Import FastAPI/SQLAlchemy: 170 rutas, 37 tablas y mappers correctos.
- Alembic: una única cabeza `20260729_0022`.
- Pruebas de desbloqueo y creación de clínicas: 5 superadas.
- SIP gateway: 44 pruebas superadas.
- TypeScript estricto del frontend: correcto.

Vitest/build Vite no pudo ejecutarse en el entorno de análisis porque el `node_modules`
aportado contiene el binario opcional Rollup para Windows. El ZIP final no incluye
`node_modules`; Docker o `npm ci` instalarán la variante Linux.
