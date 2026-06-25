# Prompts dinámicos por clínica

Cada llamada SIP se resuelve estrictamente mediante un registro activo de
`PhoneNumber`. No se usa una clínica global ni se elige una clínica por
fallback.

El contexto de llamada carga únicamente datos de la clínica propietaria:

- configuración activa del asistente;
- trabajadores y servicios activos;
- precios publicados;
- horarios generales y de trabajadores;
- estado seguro de calendarios, sin tokens;
- políticas de reserva, cancelación y transferencia;
- elementos activos de conocimiento.

El prompt nunca incluye tokens OAuth, API keys, `sip_target`, webhooks, notas
internas, identificadores de base de datos ni datos de otras clínicas.

## Preview desde el panel

```http
POST /api/admin/clinics/{clinic_id}/assistant-configs/{config_id}/preview-prompt
X-Admin-API-Key: ...
```

Respuesta abreviada:

```json
{
  "clinic_id": "00000000-0000-0000-0000-000000000000",
  "config_id": "00000000-0000-0000-0000-000000000000",
  "realtime_model": "gpt-realtime-2",
  "realtime_voice": "marin",
  "language": "es",
  "first_message": "Hola. Soy el asistente virtual de Clínica Demo.",
  "prompt": "# Identidad\n\nEres el asistente virtual telefónico..."
}
```

## Ejemplo de fragmento renderizado

```text
# Identidad

Eres el asistente virtual telefónico de Clínica Demo.
Idioma principal: es.
Tono: profesional, cálido, breve, natural y adecuado para una llamada.

# Servicios y precios

- Consulta general: Servicio demo. Duración: 30 minutos.
  Precio: 50 €. Trabajadores: cualquier trabajador disponible.

# Base de conocimiento activa

- [location] Ubicación: Estamos en Calle Demo 10, Madrid.

# Regla de veracidad estricta

Nunca inventes precios, servicios, trabajadores, políticas ni huecos.
No presentes como disponible ningún horario que no provenga de propose_slots
o check_availability.
```

El webhook utiliza el mismo builder que este preview. El modelo, la voz, el
idioma y el primer mensaje proceden del `AssistantConfig` activo resuelto para
el número llamado.
