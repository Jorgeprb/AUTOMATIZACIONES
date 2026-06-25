# Privacidad del MVP

## Alcance

Este documento describe medidas técnicas básicas. No sustituye asesoramiento
legal ni una evaluación formal de RGPD.

## Datos guardados

El MVP puede guardar:

- nombre;
- teléfono;
- fecha y hora de cita;
- trabajador y servicio;
- motivo general breve;
- identificadores técnicos de llamada;
- eventos técnicos necesarios para depuración;
- credenciales OAuth de Google cifradas.

El motivo general admite como máximo 300 caracteres. No debe contener historia
clínica, diagnóstico, medicación, resultados ni notas médicas detalladas.

## Transcripción

En producción se recomienda:

```dotenv
ENABLE_CALL_TRANSCRIPTION=false
```

Con este valor:

- no se solicita transcripción de entrada en la sesión Realtime;
- no se guarda `transcript_text`;
- los eventos de transcripción se guardan sin texto y marcados como
  `transcript_redacted`.

Si se activa la transcripción, pueden almacenarse palabras pronunciadas por el
usuario. Debe existir una base jurídica, información al usuario y una política
de acceso y borrado adecuada.

## Resúmenes

Los resúmenes persistidos son administrativos y genéricos. Los resúmenes
libres enviados por herramientas de transferencia o cierre se redactan antes
de guardarse.

## Retención y borrado

Cada clínica define:

```text
data_retention_days
```

Valor inicial: 30 días.

El comando:

```bash
make purge-calls
```

borra llamadas terminadas que superan ese plazo. También borra sus
`CallEvent`. Las citas permanecen para conservar la agenda, pero su
`call_session_id` queda vacío.

Una llamada concreta puede borrarse mediante:

```http
DELETE /api/calls/{call_session_id}
X-Internal-API-Key: ...
```

## Acceso

- PostgreSQL no se expone públicamente en producción.
- Los endpoints `/api/*` usan `X-Internal-API-Key`.
- `/dev/*` no existe en producción.
- El webhook OpenAI exige firma válida y cuerpo limitado.
- Caddy gestiona TLS.
- Los logs se rotan.

## Backups

Los backups contienen datos personales.

- cifra las copias externas;
- limita acceso;
- define su propia retención;
- prueba restauraciones;
- destruye copias antiguas de forma controlada.

## Limitaciones del MVP

- El rate limit vive en memoria y no se comparte entre réplicas.
- No existe todavía panel de auditoría.
- No existe gestión granular de usuarios.
- No existe anonimización automática de citas.
- No debe usarse como historia clínica.
