# Ajustes del portal cliente y calendario — 2026-07-30

## Resumen

Esta revisión aplica cambios visuales y funcionales exclusivamente orientados a
`client.autogal.es`, conservando el portal global de administración, SIP, Stripe,
CRM, OAuth y el aislamiento por clínica.

La única modificación de esquema es la herencia del horario de clínica por los
trabajadores:

```text
20260729_0022 -> 20260730_0023
```

## Sesión y conexión con Google Calendar

Se corrigieron dos causas de cierres de sesión aparentes:

1. El estado OAuth guarda ahora el portal que inició la conexión (`admin` o
   `client`). Al terminar Google OAuth, el navegador vuelve a:
   - administración: `/clinics/{clinic_id}/calendar`;
   - cliente: `/clinics/{clinic_id}/settings/calendar`.
2. El cliente HTTP ya no considera que cualquier `401` funcional implica una
   sesión caducada. Antes de cerrar la sesión consulta `/auth/me`; solo emite el
   evento global de logout si esa comprobación también devuelve `401`.

Los endpoints que expresan “Google todavía no está autorizado” utilizan `428`
en vez de `401`, evitando mezclar un requisito de calendario con una sesión
caducada.

## Datos generales y horarios

- Se eliminó el aviso “Google Calendar no está conectado” de Datos generales.
- El horario general de la clínica ocupa una tarjeta principal.
- Email, zona horaria, idioma, dirección, web y retención se muestran en una
  tarjeta secundaria con menor presencia visual.
- El horario de la clínica se aplica a trabajadores con
  `inherit_clinic_hours=true`.
- Si un trabajador desmarca la herencia, el planificador utiliza su
  `working_hours_json` propio.
- Si la clínica todavía no tiene tramos configurados, la lógica conserva el
  horario individual como fallback.

## Trabajadores

- El diálogo de alta/edición usa `max-w-5xl` y scroll vertical controlado.
- Se añadió la casilla **Heredar el horario de la clínica** con explicación.
- Al heredar se muestra un resumen de solo lectura del horario de la clínica.
- Al desmarcar se habilita el editor del horario individual.

## Navegación y vistas simplificadas

- Se eliminó Calendario del menú lateral del portal cliente; permanece dentro
  de Ajustes de la clínica > Integración de calendario.
- Se retiraron las alertas de contexto/servicios de Configuración del asistente.
- Servicios y Conocimiento ya no muestran “Contexto efectivo del LLM”.
- La consola no muestra prompt final, proveedor, motor ni selección de
  calendario. El servidor fuerza OpenAI y calendario real con creación de
  eventos.
- Conversaciones muestra los filtros únicamente al pulsar **Filtrar**.
- Clientes ya no expone un estado activo/inactivo del cliente.
- Los colores de eventos de Google se seleccionan mediante muestras visuales,
  no mediante códigos.

## Migración

La revisión `20260730_0023` añade:

```sql
ALTER TABLE workers
ADD COLUMN inherit_clinic_hours BOOLEAN DEFAULT true NOT NULL;
```

No se modificó ninguna migración anterior ni se creó una segunda cabeza.

## Validaciones realizadas

- `python -m compileall`: correcto.
- Import FastAPI/SQLAlchemy con dependencias simuladas: 170 rutas y 37 tablas.
- Mappers SQLAlchemy: correctos.
- Alembic: una única cabeza `20260730_0023`.
- Tests de Google Calendar: 17 superados.
- Tests del planificador/horarios: 13 superados.
- SIP gateway: 44 superados.
- Transpilación sintáctica TypeScript de los archivos modificados: correcta.

El typecheck/build completo de Vite no pudo repetirse en este entorno porque el
`npm ci` quedó incompleto: el registro interno no proporciona todas las
versiones del lockfile. El ZIP final no incluye `node_modules`; el build Docker
o `npm ci` en Linux debe instalar las dependencias correctas.

## Despliegue

Esta revisión **sí requiere migración**:

```bash
cd /opt/AUTOMATIZACIONES

docker compose -f docker-compose.prod.yml --env-file .env.production \
  build --no-cache migrate api frontend client-frontend

docker compose -f docker-compose.prod.yml --env-file .env.production \
  run --rm --entrypoint alembic migrate heads

# Debe mostrar solo 20260730_0023 (head).

docker compose -f docker-compose.prod.yml --env-file .env.production \
  run --rm migrate

docker compose -f docker-compose.prod.yml --env-file .env.production \
  up -d --force-recreate api frontend client-frontend caddy
```

Después comprueba:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps

docker compose -f docker-compose.prod.yml --env-file .env.production \
  logs --no-color --tail=250 migrate api frontend client-frontend caddy
```

## Smoke tests prioritarios

1. Iniciar sesión en `client.autogal.es`.
2. Conectar Google desde Ajustes > Integración de calendario.
3. Confirmar que el callback vuelve a `client.autogal.es` sin pedir login.
4. Entrar en Compras y suscripciones y navegar de vuelta sin perder sesión.
5. Configurar el horario general de la clínica.
6. Crear un trabajador heredando el horario.
7. Crear otro trabajador con horario individual.
8. Consultar huecos para confirmar que cada uno usa el horario esperado.
