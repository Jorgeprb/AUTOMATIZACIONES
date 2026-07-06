"""Call audio routing and external voice provider policy helpers."""

from __future__ import annotations

CALL_AUDIO_MODE_OPENAI_HOSTED_SIP = "openai_hosted_sip"
CALL_AUDIO_MODE_VPS_MEDIA_BRIDGE = "vps_media_bridge"

CALL_AUDIO_MODES = (
    CALL_AUDIO_MODE_OPENAI_HOSTED_SIP,
    CALL_AUDIO_MODE_VPS_MEDIA_BRIDGE,
)

VOICE_PROVIDER_OPENAI = "openai"
VOICE_PROVIDERS = (
    VOICE_PROVIDER_OPENAI,
    "azure",
    "google",
    "elevenlabs",
    "amazon_polly",
    "deepgram",
    "cartesia",
    "resemble",
    "readspeaker",
    "acapela",
    "cereproc",
    "local_coqui",
    "local_chatterbox",
    "custom_http",
)

CLONED_OR_CUSTOM_VOICE_PROVIDERS = frozenset(
    {
        "elevenlabs",
        "resemble",
        "local_coqui",
        "local_chatterbox",
        "custom_http",
    }
)

TELEPHONY_CODECS = ("pcmu", "pcma", "pcm16")
OUTPUT_AUDIO_FORMATS = ("pcm16", "wav", "mp3", "opus")


def requires_vps_media_bridge(voice_provider: str) -> bool:
    """Return whether a voice provider needs our own SIP/RTP media bridge."""
    return voice_provider != VOICE_PROVIDER_OPENAI


def normalize_call_audio_mode(
    *,
    voice_provider: str,
    requested_mode: str,
) -> str:
    """Force the bridge when a non-OpenAI voice provider is selected."""
    if requires_vps_media_bridge(voice_provider):
        return CALL_AUDIO_MODE_VPS_MEDIA_BRIDGE
    return requested_mode


def requires_external_voice_legal_confirmation(voice_provider: str) -> bool:
    """Return whether a provider can represent cloned/custom voice use."""
    return voice_provider in CLONED_OR_CUSTOM_VOICE_PROVIDERS
