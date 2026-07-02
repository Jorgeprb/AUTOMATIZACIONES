"""Helpers for assistant voice-profile prompts and finite audio previews."""

from __future__ import annotations

from typing import Protocol


class VoiceProfileLike(Protocol):
    """Small structural type for AssistantConfig and preview request objects."""

    @property
    def voice_instructions(self) -> str | None: ...

    @property
    def voice_preset(self) -> str | None: ...

    @property
    def realtime_voice(self) -> str: ...

    @property
    def tts_preview_voice(self) -> str | None: ...

    @property
    def fallback_voice(self) -> str | None: ...

    @property
    def speech_speed(self) -> str: ...

    @property
    def pause_style(self) -> str: ...

    @property
    def phone_reading_style(self) -> str: ...

    @property
    def date_reading_style(self) -> str: ...

    @property
    def price_reading_style(self) -> str: ...

    @property
    def allow_interruptions(self) -> bool: ...

    @property
    def idle_timeout_ms(self) -> int | None: ...

    @property
    def ai_disclosure_enabled(self) -> bool: ...

    @property
    def ai_disclosure_message(self) -> str | None: ...

    @property
    def preview_audio_format(self) -> str: ...


DEFAULT_AI_DISCLOSURE = "Soy un asistente virtual de la clinica."

SPEECH_SPEED_RULES = {
    "slow": "Habla algo mas despacio de lo normal, con claridad telefonica.",
    "normal": "Habla a velocidad natural de recepcionista.",
    "fast": "Habla agil, pero sin atropellar datos importantes.",
}

PAUSE_STYLE_RULES = {
    "short": "Usa pausas cortas y evita silencios largos.",
    "natural": "Usa pausas naturales entre ideas y antes de datos importantes.",
    "slow": "Usa pausas mas marcadas para que se entienda bien por telefono.",
}

PHONE_READING_RULES = {
    "digits": "Lee los telefonos digito a digito.",
    "groups": "Lee los telefonos en grupos naturales de dos o tres cifras.",
    "natural": "Lee los telefonos de forma natural y confirma si hay duda.",
}

DATE_READING_RULES = {
    "natural": (
        "Lee fechas y horas de forma natural, por ejemplo lunes por la manana."
    ),
    "numeric": "Lee fechas con dia, mes y hora de forma explicita y numerica.",
}

PRICE_READING_RULES = {
    "brief": (
        "Lee precios de forma breve, sin explicar impuestos salvo que esten "
        "escritos."
    ),
    "clear": "Lee precios de forma clara, con moneda y condiciones configuradas.",
    "detailed": (
        "Lee precios con mas detalle si el contexto incluye condiciones o rangos."
    ),
}

AUDIO_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "opus": "audio/ogg",
}


def _clean(value: str | None) -> str:
    """Normalize optional human-authored text."""
    return (value or "").strip()


def effective_preview_voice(profile: VoiceProfileLike) -> str:
    """Return the one-shot preview voice with backwards-compatible fallback."""
    return _clean(profile.tts_preview_voice) or profile.realtime_voice


def effective_disclosure_message(profile: VoiceProfileLike) -> str:
    """Return a safe disclosure message when enabled."""
    return _clean(profile.ai_disclosure_message) or DEFAULT_AI_DISCLOSURE


def audio_media_type(format_name: str) -> str:
    """Map a configured preview audio format to an HTTP media type."""
    return AUDIO_MEDIA_TYPES.get(format_name, "audio/mpeg")


def build_voice_instruction_block(profile: VoiceProfileLike) -> str:
    """Render voice-only instructions separate from conversation policy."""
    phone_rule = PHONE_READING_RULES.get(
        profile.phone_reading_style,
        PHONE_READING_RULES["groups"],
    )
    date_rule = DATE_READING_RULES.get(
        profile.date_reading_style,
        DATE_READING_RULES["natural"],
    )
    price_rule = PRICE_READING_RULES.get(
        profile.price_reading_style,
        PRICE_READING_RULES["clear"],
    )
    speed_rule = SPEECH_SPEED_RULES.get(
        profile.speech_speed,
        SPEECH_SPEED_RULES["normal"],
    )
    pause_rule = PAUSE_STYLE_RULES.get(
        profile.pause_style,
        PAUSE_STYLE_RULES["natural"],
    )
    interruption_rule = (
        "permitidas; corta la respuesta si la persona habla."
        if profile.allow_interruptions
        else "evitalas; termina frases breves."
    )
    timeout_rule = (
        f"{profile.idle_timeout_ms} ms antes de recuperar la conversacion."
        if profile.idle_timeout_ms
        else "usar valor por defecto de OpenAI."
    )
    lines = [
        "# Perfil de voz",
        "",
        "Estas instrucciones controlan como suena el asistente. No cambian "
        "las reglas de agenda ni seguridad.",
        f"- Voz Realtime principal: {profile.realtime_voice}.",
        f"- Voz de fallback: {_clean(profile.fallback_voice) or 'no configurada'}.",
        f"- Voz para previews TTS: {effective_preview_voice(profile)}.",
        f"- Preset de voz: {_clean(profile.voice_preset) or 'personalizado'}.",
        f"- Velocidad: {profile.speech_speed}. {speed_rule}",
        f"- Pausas: {profile.pause_style}. {pause_rule}",
        f"- Lectura de telefonos: {profile.phone_reading_style}. {phone_rule}",
        f"- Lectura de fechas y horas: {profile.date_reading_style}. {date_rule}",
        f"- Lectura de precios: {profile.price_reading_style}. {price_rule}",
        f"- Interrupciones del usuario: {interruption_rule}",
        f"- Timeout de inactividad: {timeout_rule}",
    ]
    if profile.ai_disclosure_enabled:
        lines.append(
            "- Disclosure IA: al inicio informa de forma natural: "
            f"\"{effective_disclosure_message(profile)}\""
        )
    else:
        lines.append("- Disclosure IA: desactivado por configuracion.")
    custom = _clean(profile.voice_instructions)
    if custom:
        lines.extend(["", "Instrucciones de voz personalizadas:", custom])
    return "\n".join(lines)
