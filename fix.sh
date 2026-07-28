#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/AUTOMATIZACIONES}"
MODELS="$ROOT/clinic-voice-agent/app/models.py"
INTERNAL_VOICE="$ROOT/clinic-voice-agent/app/api/internal_voice.py"
VERSIONS="$ROOT/clinic-voice-agent/alembic/versions"

log() { printf '[assistant-config-fix] %s\n' "$*"; }
fail() { printf '[assistant-config-fix] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$MODELS" ]] || fail "No existe $MODELS"
[[ -d "$VERSIONS" ]] || fail "No existe $VERSIONS"

MIGRATION="$(grep -R -l --include='*.py' 'caller_phone_policy' "$VERSIONS" 2>/dev/null | head -n1 || true)"
if [[ -n "$MIGRATION" ]]; then
  log "Migración de presentación localizada: $MIGRATION"
else
  log "AVISO: no se encontró la migración que contiene caller_phone_policy."
  log "Se restaurará el modelo porque la base ya está en una revisión posterior."
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
cp -a "$MODELS" "$MODELS.bak-presentation-$STAMP"
[[ ! -f "$INTERNAL_VOICE" ]] || cp -a "$INTERNAL_VOICE" "$INTERNAL_VOICE.bak-presentation-$STAMP"
log "Backup creado: $MODELS.bak-presentation-$STAMP"

python3 - "$MODELS" "$INTERNAL_VOICE" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

models_path = Path(sys.argv[1])
internal_voice_path = Path(sys.argv[2])
text = models_path.read_text(encoding="utf-8")

class_start = text.find("class AssistantConfig(")
if class_start < 0:
    raise SystemExit("No se encontró class AssistantConfig")
next_class = text.find("\nclass ", class_start + 1)
class_end = len(text) if next_class < 0 else next_class
assistant_block = text[class_start:class_end]

field_blocks: list[tuple[str, str]] = [
    (
        "time_reading_style",
        '''    time_reading_style: Mapped[str] = mapped_column(\n        String(32),\n        default="natural_quarters",\n        nullable=False,\n    )\n''',
    ),
    (
        "caller_phone_policy",
        '''    caller_phone_policy: Mapped[str] = mapped_column(\n        String(32),\n        default="ask_before_use",\n        nullable=False,\n    )\n''',
    ),
    (
        "calendar_event_title_template",
        '''    calendar_event_title_template: Mapped[str] = mapped_column(\n        Text,\n        default="Cita - {patient_name}",\n        nullable=False,\n    )\n''',
    ),
    (
        "calendar_event_description_template",
        '''    calendar_event_description_template: Mapped[str] = mapped_column(\n        Text,\n        default=(\n            "Reserva creada por asistente telefónico.\\n"\n            "Paciente: {patient_name}\\n"\n            "Teléfono: {patient_phone}\\n"\n            "Servicio: {service_name}\\n"\n            "Profesional: {worker_name}\\n"\n            "Fecha: {start_date}\\n"\n            "Hora: {start_time}\\n"\n            "Motivo general: {reason}"\n        ),\n        nullable=False,\n    )\n''',
    ),
]

missing = [
    (name, block)
    for name, block in field_blocks
    if re.search(rf"^    {re.escape(name)}\s*:", assistant_block, re.MULTILINE) is None
]

if missing:
    anchor = "    allow_interruptions: Mapped[bool] = mapped_column("
    anchor_abs = text.find(anchor, class_start, class_end)
    if anchor_abs < 0:
        raise SystemExit("No se encontró el punto de inserción allow_interruptions")
    insertion = "".join(block for _, block in missing) + "\n"
    text = text[:anchor_abs] + insertion + text[anchor_abs:]

# Align metadata with the migration that reduced the accepted voice-speed range.
text = text.replace(
    '"voice_speed BETWEEN 0.25 AND 4.00"',
    '"voice_speed BETWEEN 0.50 AND 2.00"',
)

models_path.write_text(text, encoding="utf-8")

# Runtime fallback: a partially rolled-out container must ask before using the
# caller number instead of returning HTTP 500. The ORM mapping above remains
# the authoritative fix; these getattr calls only make staged deployments safe.
if internal_voice_path.is_file():
    iv = internal_voice_path.read_text(encoding="utf-8")
    iv = re.sub(
        r"(?<![\w\"'])config\.caller_phone_policy",
        'getattr(config, "caller_phone_policy", "ask_before_use")',
        iv,
    )
    iv = re.sub(
        r"(?<![\w\"'])config\.time_reading_style",
        'getattr(config, "time_reading_style", "natural_quarters")',
        iv,
    )
    internal_voice_path.write_text(iv, encoding="utf-8")

print("Campos añadidos:", ", ".join(name for name, _ in missing) or "ninguno; ya existían")
PY

python3 -m py_compile "$MODELS"
if [[ -f "$INTERNAL_VOICE" ]]; then
  python3 -m py_compile "$INTERNAL_VOICE"
fi

for field in \
  time_reading_style \
  caller_phone_policy \
  calendar_event_title_template \
  calendar_event_description_template; do
  grep -q "^[[:space:]]*$field:" "$MODELS" \
    || fail "No se pudo restaurar AssistantConfig.$field"
done

log "Campos de presentación restaurados y sintaxis validada."
log "No se ha modificado la base de datos ni Alembic."
log "Reconstruye api y después recrea api, sip-gateway y caddy."
