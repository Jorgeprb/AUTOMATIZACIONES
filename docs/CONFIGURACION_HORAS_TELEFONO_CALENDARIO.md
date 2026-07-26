# Configuración de horas, teléfono y eventos de calendario

## Confirmación de temperatura y velocidad

La temperatura numérica se guarda en `assistant_configs.temperature` y se envía a las sesiones OpenAI Realtime con un rango de `0.60` a `1.20`.

La velocidad numérica se guarda en `assistant_configs.voice_speed` y se aplica a Azure Speech mediante SSML (`prosody rate`). El rango unificado es `0.50` a `2.00`.

## Forma de decir las horas

`time_reading_style` admite:

- `natural_quarters`: utiliza «en punto», «y cuarto», «y media» y «menos cuarto». Los minutos intermedios también se expresan verbalmente.
- `numeric`: conserva el formato de 24 horas, por ejemplo `17:15`.

Las herramientas de disponibilidad devuelven el valor técnico ISO y un campo `spoken_start_at` preparado para ser leído por el asistente.

## Uso del número entrante

`caller_phone_policy` admite:

- `ask_before_use`: el asistente pregunta una sola vez si puede utilizar el número desde el que se llama.
- `use_directly`: utiliza el Caller ID como `patient_phone` sin preguntar. Si el usuario proporciona expresamente otro número, prevalece el nuevo.

Si el Caller ID es privado, anónimo o no está disponible, el asistente solicita un número independientemente de la política seleccionada.

## Prompt general

El campo `system_prompt` se edita desde la página del asistente y se incorpora a las instrucciones Realtime de cada llamada.

## Evento de Google Calendar

Se pueden personalizar el título y la descripción del evento. Variables disponibles:

- `{patient_name}`
- `{patient_phone}`
- `{reason}`
- `{service_name}`
- `{worker_name}`
- `{clinic_name}`
- `{start_date}` / `{start_time}`
- `{end_date}` / `{end_time}`
- `{start_datetime}` / `{end_datetime}`
- `{appointment_id}`
- `{call_session_id}`

Las plantillas se validan en frontend y backend. No se permiten atributos, índices, conversiones ni variables no documentadas.

## Migración

La revisión `20260726_0020` añade los campos nuevos y unifica el rango de velocidad. Los valores históricos fuera de `0.50–2.00` se ajustan al límite más próximo antes de instalar la restricción.
