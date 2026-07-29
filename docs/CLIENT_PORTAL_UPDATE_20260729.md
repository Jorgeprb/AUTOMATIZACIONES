# Actualización de client.autogal.es — 2026-07-29

## Cambios de navegación

Los cambios se aplican únicamente al build con `VITE_PORTAL_MODE=client`:

- eliminada la entrada **Cuenta comercial**;
- eliminada la entrada **Flujos**;
- eliminada la entrada **Mi cuenta**;
- **Asistente** pasa a ser la primera opción bajo **Clínica activa**;
- se mantienen cierre de sesión y selección de clínica en la barra superior;
- las URL directas `/account`, `/settings` y `/clinics/:clinicId/flows` redirigen fuera de esas pantallas en el portal cliente.

El portal `admin.autogal.es` conserva sus opciones anteriores.

## Añadir clínicas desde “Mis clínicas”

- Se añadió un botón compacto `+` en la cabecera de **Mis clínicas**.
- Abre un formulario específico para nombre, zona horaria, teléfono, email y dirección.
- Usa el endpoint comercial existente `POST /auth/onboarding/clinics`.
- El teléfono puede dejarse vacío hasta la provisión del número.
- Los placeholders internos `pending-*` se generan de forma única, evitando que la segunda clínica falle por la restricción única de `main_phone_number`.
- Los duplicados reales devuelven `409` en vez de un error interno `500`.

## Corrección del error 500 de estadísticas

### Causa exacta

El endpoint construía los diccionarios de nombres con:

```python
dict(session.execute(statement).tuples())
```

En SQLAlchemy 2, `ChunkedIteratorResult` expone una interfaz que `dict()` interpreta como mapping, pero no admite indexación mediante `result[key]`. El resultado era:

```text
TypeError: 'ChunkedIteratorResult' object is not subscriptable
```

### Solución

- Se materializan explícitamente las filas con `.all()` y comprensiones de diccionario.
- La agregación se movió a `app/analytics_service.py` para poder probarla aisladamente.
- Se eliminó la consulta N+1 de precios de servicios.
- El filtro telefónico se aplica también a llamadas.
- Los rangos personalizados se interpretan en la zona horaria de la clínica y se validan.
- `scheduled` se mantiene como alias compatible de `pending + confirmed`.
- El frontend muestra por separado **Pendiente** y **Confirmada**.
- Al seleccionar rango personalizado se inicializan fechas válidas, evitando una petición incompleta.
- Se validan periodos y estados desconocidos con `422`, no con `500`.

## Migraciones

No se añadió ninguna migración porque no se modificó el esquema. La única cabeza continúa siendo:

```text
20260729_0022 (head)
```

## Validaciones ejecutadas

- `python -m compileall`: correcto.
- TypeScript estricto del frontend: correcto.
- Pruebas de regresión nuevas: 4 superadas.
- SIP gateway: 44 pruebas superadas.
- `git diff --check`: correcto.
- Alembic: una única cabeza lineal.

Vitest y Vite no pudieron arrancar en este entorno porque el `node_modules` adjunto contiene los binarios opcionales de Rollup para Windows y falta `@rollup/rollup-linux-x64-gnu`. El paquete final excluye `node_modules`; Docker o `npm ci` instalarán el binario Linux correcto.

## Despliegue

No es necesario ejecutar una migración nueva, aunque se puede confirmar la cabeza antes de levantar servicios.

```bash
cd /opt/AUTOMATIZACIONES

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  build --no-cache api frontend client-frontend

docker compose \
  -f docker-compose.prod.yml \
  --env-file .env.production \
  up -d --force-recreate api frontend client-frontend caddy
```

Comprobación:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps

docker compose -f docker-compose.prod.yml --env-file .env.production \
  logs --tail=200 api frontend client-frontend caddy
```

Al abrir Estadísticas, el backend debe registrar:

```text
GET /api/admin/clinics/<clinic_id>/analytics ... 200
```
