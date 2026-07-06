"""Database helpers for the admin voice catalog."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import VoiceCatalog
from app.voice_providers import build_voice_providers, catalog_providers
from app.voice_providers.base import VoiceCatalogItem


def upsert_voice_catalog_item(session: Session, item: VoiceCatalogItem) -> VoiceCatalog:
    """Insert or update one voice catalog row."""
    row = session.scalar(
        select(VoiceCatalog).where(
            VoiceCatalog.provider == item.provider,
            VoiceCatalog.model == item.model,
            VoiceCatalog.voice_id == item.voice_id,
        )
    )
    values = {
        "display_name": item.display_name,
        "locale": item.locale,
        "language": item.language,
        "gender": item.gender,
        "supports_streaming": item.supports_streaming,
        "supports_telephony_codec": item.supports_telephony_codec,
        "supports_voice_clone": item.supports_voice_clone,
        "requires_consent": item.requires_consent,
        "recommended": item.recommended,
        "enabled": item.enabled,
    }
    if row is None:
        row = VoiceCatalog(
            provider=item.provider,
            model=item.model,
            voice_id=item.voice_id,
            **values,
        )
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    return row


def sync_voice_catalog(session: Session, settings: Settings) -> dict[str, int]:
    """Synchronize known provider voice catalogs into PostgreSQL."""
    synced: dict[str, int] = {}
    for provider in catalog_providers(settings):
        count = 0
        for item in provider.catalog():
            upsert_voice_catalog_item(session, item)
            count += 1
        synced[provider.provider_id] = count
    session.commit()
    return synced


def ensure_voice_catalog_seeded(session: Session, settings: Settings) -> None:
    """Seed static voice catalog entries when the table is empty."""
    exists = session.scalar(select(VoiceCatalog.id).limit(1))
    if exists is None:
        sync_voice_catalog(session, settings)


def list_catalog_for_provider(
    session: Session,
    settings: Settings,
    provider_id: str,
) -> list[VoiceCatalog]:
    """Return enabled DB catalog entries, seeding static entries when needed."""
    if provider_id not in build_voice_providers(settings):
        raise KeyError(provider_id)
    ensure_voice_catalog_seeded(session, settings)
    return list(
        session.scalars(
            select(VoiceCatalog)
            .where(
                VoiceCatalog.provider == provider_id,
                VoiceCatalog.enabled.is_(True),
            )
            .order_by(
                VoiceCatalog.recommended.desc(),
                VoiceCatalog.locale.asc().nullslast(),
                VoiceCatalog.display_name.asc(),
            )
        )
    )
