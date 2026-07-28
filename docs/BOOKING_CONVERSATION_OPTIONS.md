# Opciones de conversación para reservas

Esta versión añade controles de comportamiento sin exponer detalles técnicos del agente.

## Identificación del servicio

`service_prompt_mode` admite:

- `list_services`: enumera una vez los servicios reservables reales y pregunta cuál necesita.
- `ask_open`: pregunta directamente qué servicio necesita y solo lista opciones si se las piden.
- `infer_confirm`: intenta asociar la petición a un único servicio real y lo confirma con una pregunta breve, por ejemplo «¿Para cortar el pelo?». Si existe ambigüedad, pregunta.

El modo nunca permite inventar un servicio ni utilizar uno inactivo o no reservable.

## Cuadrícula de inicios de cita

`slot_interval_minutes` admite 5, 10, 15, 20, 30 o 60 minutos. La cuadrícula se calcula en la zona horaria de la clínica y se aplica a:

- propuestas de huecos;
- comprobaciones exactas;
- creación final de citas.

Con 30 minutos solo se pueden crear citas que empiecen a `:00` o `:30`.

## Respuestas directas

- `direct_availability_response`: evita narrar que se va a consultar o que ya se consultó la agenda.
- `direct_booking_response`: evita anunciar que se va a reservar; el bot solo confirma después de que `create_appointment` devuelva éxito.

## Confirmación final

`booking_confirmation_datetime_enabled` hace que la herramienta devuelva una fecha preparada para voz, por ejemplo:

`el 26 de agosto a las doce de la mañana`

El agente debe usar ese valor y no leer el ISO técnico.

## Ayuda adicional y cierre

Con `post_booking_followup_enabled`, después de una reserva confirmada se formula `post_booking_followup_message`. Si el usuario solicita otra gestión, se resuelve y se vuelve a preguntar al terminar.

Con `hangup_after_no_more_help`, una respuesta negativa provoca una despedida breve y una llamada a `end_call`. El SIP gateway espera a que termine el audio y envía un BYE dentro del diálogo.

Con `hangup_on_natural_goodbye`, despedidas inequívocas como «adiós», «chao», «hasta luego» o «gracias, nada más» siguen el mismo cierre. Un «gracias» aislado no se interpreta necesariamente como despedida.

## Migración

La migración es:

`20260728_0020_booking_conversation_flow.py`

Los registros existentes conservan el sentido del antiguo `ask_service` y empiezan con una cuadrícula de 15 minutos para no alterar horarios ya utilizados.
