# Corrección de build: WorkerForm

Fecha: 2026-07-30

## Error corregido

El build TypeScript fallaba porque `WorkerForm.test.tsx` no pasaba la nueva propiedad obligatoria `clinicHours` al componente `WorkerForm`.

Además, el test utilizaba `inherit_clinic_hours=true`, por lo que el editor de horario individual que intentaba manipular no debía estar visible.

## Cambio aplicado

El test ahora:

- pasa `clinicHours={workerDefaults.working_hours_json}`;
- establece `inherit_clinic_hours: false` para probar correctamente el horario personalizado;
- mantiene la comprobación de edición del lunes hasta las 18:00.

No cambia modelos, API, migraciones, lógica de producción ni configuración Docker.
