"""Voice provider registry used by admin UI, previews, and media bridge."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from app.config import Settings
from app.voice_providers.amazon_polly_provider import AmazonPollyTTSProvider
from app.voice_providers.azure_provider import AzureTTSProvider
from app.voice_providers.base import (
    TTSProvider,
    VoiceCatalogProvider,
    VoiceProviderInfo,
)
from app.voice_providers.cartesia_provider import CartesiaTTSProvider
from app.voice_providers.custom_http_provider import CustomHTTPTTSProvider
from app.voice_providers.deepgram_provider import DeepgramTTSProvider
from app.voice_providers.elevenlabs_provider import ElevenLabsTTSProvider
from app.voice_providers.google_provider import GoogleTTSProvider
from app.voice_providers.local_provider import LocalTTSProvider
from app.voice_providers.openai_provider import OpenAITTSProvider
from app.voice_providers.resemble_provider import (
    EnterprisePlaceholderProvider,
    ResembleTTSProvider,
)

Provider = TTSProvider

PROVIDER_ORDER = (
    "openai",
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


def build_voice_providers(settings: Settings) -> dict[str, Provider]:
    """Instantiate all supported provider adapters for one settings object."""
    providers: dict[str, Provider] = {
        "openai": OpenAITTSProvider(settings),
        "azure": AzureTTSProvider(settings),
        "google": GoogleTTSProvider(settings),
        "elevenlabs": ElevenLabsTTSProvider(settings),
        "amazon_polly": AmazonPollyTTSProvider(settings),
        "deepgram": DeepgramTTSProvider(settings),
        "cartesia": CartesiaTTSProvider(settings),
        "resemble": ResembleTTSProvider(settings),
        "readspeaker": EnterprisePlaceholderProvider("readspeaker", "ReadSpeaker"),
        "acapela": EnterprisePlaceholderProvider("acapela", "Acapela"),
        "cereproc": EnterprisePlaceholderProvider("cereproc", "CereProc"),
        "local_coqui": LocalTTSProvider(settings, "local_coqui"),
        "local_chatterbox": LocalTTSProvider(settings, "local_chatterbox"),
        "custom_http": CustomHTTPTTSProvider(settings),
    }
    return {key: providers[key] for key in PROVIDER_ORDER}


def get_voice_provider(settings: Settings, provider_id: str) -> Provider:
    """Return one provider adapter or raise KeyError."""
    return build_voice_providers(settings)[provider_id]


def list_voice_provider_info(settings: Settings) -> list[VoiceProviderInfo]:
    """Return provider metadata sorted for UI display."""
    return [provider.info() for provider in build_voice_providers(settings).values()]


def catalog_providers(settings: Settings) -> Iterable[VoiceCatalogProvider]:
    """Yield providers that expose catalog entries."""
    for provider in build_voice_providers(settings).values():
        if hasattr(provider, "catalog"):
            yield cast(VoiceCatalogProvider, provider)
