"""Unit tests for OAuth and Google Calendar operations using mocked clients."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.calendar.auth import (
    GOOGLE_CALENDAR_SCOPES,
    GoogleOAuthPersistenceError,
    GoogleOAuthProviderError,
    GoogleOAuthResult,
    complete_google_oauth,
    create_google_authorization_request,
    decode_google_oauth_state,
    diagnose_google_oauth_configuration,
    save_google_credentials,
)
from app.calendar.google_client import (
    create_calendar_for_worker,
    get_authorized_google_credentials,
    get_event_colors,
    link_calendar_to_worker,
    list_available_calendars,
)
from app.calendar.scheduler import build_worker_event_body, query_freebusy
from app.config import Settings, get_settings
from app.db import get_db
from app.main import create_app
from app.models import AppointmentSource, Clinic, GoogleCredential, Worker
from app.utils.security import TokenCipher

ADMIN_KEY = "test-admin-api-key-with-32-characters"
ADMIN_HEADERS = {"X-Admin-API-Key": ADMIN_KEY}


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return override


def _app(engine: Engine, settings: Settings) -> FastAPI:
    app = create_app(settings)
    app.dependency_overrides[get_db] = _db_override(_factory(engine))
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def _valid_oauth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "admin_api_key": ADMIN_KEY,
        "google_client_id": "1234567890-test.apps.googleusercontent.com",
        "google_client_secret": "GOCSPX-real-looking-secret",
        "google_redirect_uri": "https://voice.test/auth/google/callback",
        "google_token_encryption_key": "8O2kjVBitzftnS456ehnuY5iSmFpJbqJNUnWVallRe4=",
        "public_base_url": "https://voice.test",
        "frontend_base_url": "http://localhost:5173",
    }
    values.update(overrides)
    return Settings(**values)


def test_oauth_authorization_request_contains_offline_access() -> None:
    """OAuth start should preserve clinic context and request a refresh token."""
    settings = Settings(_env_file=None)
    clinic_id = uuid.uuid4()

    authorization = create_google_authorization_request(settings, clinic_id)
    query = parse_qs(urlparse(authorization.authorization_url).query)
    state = decode_google_oauth_state(settings, authorization.state)

    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["include_granted_scopes"] == ["true"]
    assert set(query["scope"][0].split(" ")) == set(GOOGLE_CALENDAR_SCOPES)
    assert query["code_challenge_method"] == ["S256"]
    assert state.clinic_id == clinic_id
    assert 43 <= len(state.code_verifier) <= 128


def test_credentials_are_encrypted_before_storage(db_session: Session) -> None:
    """OAuth token JSON must never be stored as plaintext."""
    settings = Settings(_env_file=None)
    clinic = Clinic(
        name="Clínica OAuth",
        timezone="Europe/Madrid",
        phone_number="+34910000100",
    )
    db_session.add(clinic)
    db_session.commit()
    token_json = json.dumps(
        {
            "token": "access-secret",
            "refresh_token": "refresh-secret",
        }
    )

    stored = save_google_credentials(
        db_session,
        settings,
        clinic_id=clinic.id,
        account_email="clinica@gmail.com",
        credentials_json=token_json,
    )

    assert "access-secret" not in stored.token_json_encrypted
    assert (
        TokenCipher(settings.google_token_encryption_key.get_secret_value()).decrypt(
            stored.token_json_encrypted
        )
        == token_json
    )


def test_oauth_callback_stores_connected_account_with_mocks(
    db_session: Session,
) -> None:
    """OAuth code exchange should persist the selected clinic account."""
    settings = Settings(_env_file=None)
    clinic = Clinic(
        name="Clínica Callback",
        timezone="Europe/Madrid",
        phone_number="+34910000103",
    )
    db_session.add(clinic)
    db_session.commit()
    state = create_google_authorization_request(settings, clinic.id).state

    credentials = MagicMock()
    credentials.to_json.return_value = json.dumps(
        {
            "token": "callback-access-token",
            "refresh_token": "callback-refresh-token",
        }
    )
    flow = MagicMock()
    flow.credentials = credentials
    oauth_service = MagicMock()
    oauth_service.userinfo.return_value.get.return_value.execute.return_value = {
        "email": "clinica@gmail.com"
    }

    oauth_state = decode_google_oauth_state(settings, state)
    with (
        patch(
            "app.calendar.auth._build_flow",
            return_value=flow,
        ) as build_flow,
        patch("app.calendar.auth.build", return_value=oauth_service),
    ):
        result = complete_google_oauth(
            db_session,
            settings,
            state=state,
            authorization_response=(
                "https://example.test/auth/google/callback"
                f"?state={state}&code=test-code"
            ),
        )

    stored = db_session.scalars(select(GoogleCredential)).one()
    build_flow.assert_called_once_with(
        settings,
        state=state,
        code_verifier=oauth_state.code_verifier,
    )
    flow.fetch_token.assert_called_once()
    assert result.account_email == "clinica@gmail.com"
    assert stored.account_email == "clinica@gmail.com"
    assert "callback-access-token" not in stored.token_json_encrypted


def test_expired_credentials_are_refreshed_and_reencrypted(
    db_session: Session,
) -> None:
    """Authorized-client loading should transparently refresh expired tokens."""
    settings = Settings(_env_file=None)
    clinic = Clinic(
        name="Clínica Refresh",
        timezone="Europe/Madrid",
        phone_number="+34910000101",
    )
    db_session.add(clinic)
    db_session.flush()
    encrypted = TokenCipher(
        settings.google_token_encryption_key.get_secret_value()
    ).encrypt(json.dumps({"token": "old-token"}))
    stored = GoogleCredential(
        clinic_id=clinic.id,
        account_email="clinica@gmail.com",
        token_json_encrypted=encrypted,
    )
    db_session.add(stored)
    db_session.commit()

    credentials = MagicMock()
    credentials.expired = True
    credentials.refresh_token = "refresh-token"
    credentials.valid = True
    credentials.to_json.return_value = json.dumps({"token": "new-token"})

    with (
        patch(
            "app.calendar.google_client.Credentials.from_authorized_user_info",
            return_value=credentials,
        ),
        patch("app.calendar.google_client.GoogleAuthRequest"),
    ):
        result = get_authorized_google_credentials(
            db_session,
            settings,
            clinic.id,
        )

    credentials.refresh.assert_called_once()
    assert result is credentials
    decrypted = TokenCipher(
        settings.google_token_encryption_key.get_secret_value()
    ).decrypt(stored.token_json_encrypted)
    assert json.loads(decrypted)["token"] == "new-token"


def test_list_calendars_and_colors_uses_mocked_google_client() -> None:
    """Calendar discovery should paginate and expose Google's event palette."""
    client = MagicMock()
    calendar_list = client.calendarList.return_value
    calendar_list.list.return_value.execute.side_effect = [
        {
            "items": [
                {
                    "id": "ana@calendar",
                    "summary": "Clínica - Ana",
                    "accessRole": "owner",
                    "timeZone": "Europe/Madrid",
                }
            ],
            "nextPageToken": "page-2",
        },
        {
            "items": [
                {
                    "id": "luis@calendar",
                    "summary": "Clínica - Luis",
                    "accessRole": "writer",
                    "colorId": "7",
                }
            ]
        },
    ]
    client.colors.return_value.get.return_value.execute.return_value = {
        "event": {
            "2": {"background": "#7ae7bf", "foreground": "#1d1d1d"},
            "7": {"background": "#46d6db", "foreground": "#1d1d1d"},
        }
    }

    calendars = list_available_calendars(client)
    colors = get_event_colors(client)

    assert [calendar.summary for calendar in calendars] == [
        "Clínica - Ana",
        "Clínica - Luis",
    ]
    assert [color.id for color in colors] == ["2", "7"]
    assert calendar_list.list.call_count == 2


def test_create_and_link_worker_calendars_with_mocked_client(
    db_session: Session,
) -> None:
    """Worker mappings should persist IDs returned by Google."""
    clinic = Clinic(
        name="Clínica",
        timezone="Europe/Madrid",
        phone_number="+34910000102",
    )
    ana = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id=None,
        color_id="2",
    )
    luis = Worker(
        clinic=clinic,
        name="Luis",
        role="Médico",
        calendar_id=None,
        color_id="7",
    )
    db_session.add_all([clinic, ana, luis])
    db_session.commit()

    client = MagicMock()
    client.calendars.return_value.insert.return_value.execute.return_value = {
        "id": "ana@calendar",
        "summary": "Clínica - Ana",
        "timeZone": "Europe/Madrid",
    }
    client.calendarList.return_value.get.return_value.execute.return_value = {
        "id": "luis@calendar",
        "summary": "Clínica - Luis",
        "accessRole": "owner",
    }

    created = create_calendar_for_worker(
        db_session,
        client,
        ana,
        summary="Clínica - Ana",
    )
    linked = link_calendar_to_worker(
        db_session,
        client,
        luis,
        calendar_id="luis@calendar",
    )

    assert created.id == "ana@calendar"
    assert linked.id == "luis@calendar"
    assert ana.calendar_id == "ana@calendar"
    assert luis.calendar_id == "luis@calendar"


def test_freebusy_and_event_metadata_support_independent_workers() -> None:
    """FreeBusy requests and event metadata should preserve worker separation."""
    client = MagicMock()
    time_min = datetime.now(UTC)
    time_max = time_min + timedelta(hours=1)
    client.freebusy.return_value.query.return_value.execute.return_value = {
        "calendars": {
            "ana@calendar": {
                "busy": [
                    {
                        "start": time_min.isoformat(),
                        "end": time_max.isoformat(),
                    }
                ]
            },
            "luis@calendar": {"busy": []},
        }
    }
    worker = Worker(
        id=uuid.uuid4(),
        clinic_id=uuid.uuid4(),
        name="Ana",
        role="Médica",
        calendar_id="ana@calendar",
        color_id="2",
    )

    busy = query_freebusy(
        client,
        calendar_ids=["ana@calendar", "luis@calendar"],
        time_min=time_min,
        time_max=time_max,
        timezone="Europe/Madrid",
    )
    event = build_worker_event_body(
        worker=worker,
        summary="Consulta general",
        start_at=time_min,
        end_at=time_max,
        timezone="Europe/Madrid",
        source=AppointmentSource.VOICE_BOT,
        call_id="call-test",
    )
    request_body: dict[str, Any] = client.freebusy.return_value.query.call_args.kwargs[
        "body"
    ]

    assert request_body["items"] == [
        {"id": "ana@calendar"},
        {"id": "luis@calendar"},
    ]
    assert len(busy["ana@calendar"]) == 1
    assert busy["luis@calendar"] == []
    assert event["colorId"] == "2"
    assert event["extendedProperties"]["private"] == {
        "worker_id": str(worker.id),
        "source": "voice_bot",
        "call_id": "call-test",
    }


def test_oauth_diagnostics_detect_invalid_fernet_key() -> None:
    """Bad token encryption keys should be reported before OAuth starts."""
    settings = _valid_oauth_settings(
        google_token_encryption_key="not-a-fernet-key",
    )

    diagnostics = diagnose_google_oauth_configuration(settings)

    assert diagnostics.configured is False
    assert diagnostics.can_start_oauth is False
    assert any(
        issue.variable == "GOOGLE_TOKEN_ENCRYPTION_KEY"
        and issue.severity == "error"
        and "Fernet" in issue.message
        for issue in diagnostics.issues
    )


@pytest.mark.anyio
async def test_google_oauth_bad_config_returns_clear_errors(
    database_engine: Engine,
) -> None:
    """Malformed .env values must not become an Internal Server Error."""
    settings = _valid_oauth_settings(
        google_client_id="replace-with-google-client-id",
        google_client_secret="replace-with-google-client-secret",
        google_redirect_uri="https://replace-me.ngrok-free.app/auth/google/callback",
        google_token_encryption_key="replace-with-a-generated-fernet-key",
    )
    clinic = Clinic(
        name="Clínica OAuth Bad",
        timezone="Europe/Madrid",
        phone_number="+34910000190",
    )
    factory = _factory(database_engine)
    with factory() as session:
        session.add(clinic)
        session.commit()
        clinic_id = clinic.id

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        diagnostics = await client.get(
            f"/api/admin/clinics/{clinic_id}/google-oauth/diagnostics",
            headers=ADMIN_HEADERS,
        )
        start_url = await client.get(
            f"/api/admin/clinics/{clinic_id}/google-oauth/start-url",
            headers=ADMIN_HEADERS,
        )
        public_start = await client.get(
            f"/auth/google/start?clinic_id={clinic_id}",
            follow_redirects=False,
        )

    assert diagnostics.status_code == 200
    payload = diagnostics.json()
    assert payload["configured"] is False
    assert payload["can_start_oauth"] is False
    assert "GOOGLE_TOKEN_ENCRYPTION_KEY" in {
        issue["variable"] for issue in payload["issues"]
    }
    assert start_url.status_code == 503
    assert "GOOGLE_TOKEN_ENCRYPTION_KEY" in start_url.text
    assert public_start.status_code == 503
    assert "GOOGLE_TOKEN_ENCRYPTION_KEY" in public_start.text


@pytest.mark.anyio
async def test_google_oauth_start_url_returns_google_url_when_configured(
    database_engine: Engine,
) -> None:
    """The panel should receive a usable Google OAuth URL when .env is valid."""
    settings = _valid_oauth_settings()
    clinic = Clinic(
        name="Clínica OAuth Good",
        timezone="Europe/Madrid",
        phone_number="+34910000191",
    )
    factory = _factory(database_engine)
    with factory() as session:
        session.add(clinic)
        session.commit()
        clinic_id = clinic.id

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/admin/clinics/{clinic_id}/google-oauth/start-url",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    authorization_url = response.json()["authorization_url"]
    query = parse_qs(urlparse(authorization_url).query)
    assert authorization_url.startswith("https://accounts.google.com/")
    assert query["redirect_uri"] == ["https://voice.test/auth/google/callback"]
    assert query["access_type"] == ["offline"]


@pytest.mark.anyio
async def test_google_oauth_callback_uses_configured_public_redirect_uri(
    database_engine: Engine,
) -> None:
    """Callback token exchange should use GOOGLE_REDIRECT_URI, not local HTTP."""
    settings = _valid_oauth_settings()
    clinic = Clinic(
        name="Clínica OAuth Callback URI",
        timezone="Europe/Madrid",
        phone_number="+34910000192",
    )
    factory = _factory(database_engine)
    with factory() as session:
        session.add(clinic)
        session.commit()
        clinic_id = clinic.id
    state = create_google_authorization_request(settings, clinic_id).state
    query = urlencode({"state": state, "code": "test-code"})

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://internal-localhost",
    ) as client:
        with patch(
            "app.api.google_auth.complete_google_oauth",
            return_value=GoogleOAuthResult(
                clinic_id=clinic_id,
                account_email="clinica@gmail.com",
            ),
        ) as complete:
            response = await client.get(
                f"/auth/google/callback?{query}",
                follow_redirects=False,
            )

    assert response.status_code == 302
    location = response.headers["location"]
    redirect_query = parse_qs(urlparse(location).query)
    assert redirect_query["google"] == ["connected"]
    assert redirect_query["reason"] == ["connected"]
    authorization_response = complete.call_args.kwargs["authorization_response"]
    assert authorization_response.startswith(
        "https://voice.test/auth/google/callback?"
    )
    assert "code=test-code" in authorization_response
    assert "state=" in authorization_response


@pytest.mark.anyio
async def test_google_oauth_callback_google_failure_redirects_with_reason(
    database_engine: Engine,
) -> None:
    """Google token exchange failures should redirect instead of returning 500."""
    settings = _valid_oauth_settings()
    clinic = Clinic(
        name="Clínica OAuth Google Fail",
        timezone="Europe/Madrid",
        phone_number="+34910000193",
    )
    factory = _factory(database_engine)
    with factory() as session:
        session.add(clinic)
        session.commit()
        clinic_id = clinic.id
    state = create_google_authorization_request(settings, clinic_id).state
    query = urlencode({"state": state, "code": "bad-code"})

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        with patch(
            "app.api.google_auth.complete_google_oauth",
            side_effect=GoogleOAuthProviderError("Google token exchange failed."),
        ):
            response = await client.get(
                f"/auth/google/callback?{query}",
                follow_redirects=False,
            )

    assert response.status_code == 302
    redirect_query = parse_qs(urlparse(response.headers["location"]).query)
    assert redirect_query["google"] == ["error"]
    assert redirect_query["reason"] == ["google_token_exchange_failed"]


@pytest.mark.anyio
async def test_google_oauth_callback_db_failure_redirects_with_reason(
    database_engine: Engine,
) -> None:
    """DB persistence failures should redirect instead of returning 500."""
    settings = _valid_oauth_settings()
    clinic = Clinic(
        name="Clínica OAuth DB Fail",
        timezone="Europe/Madrid",
        phone_number="+34910000194",
    )
    factory = _factory(database_engine)
    with factory() as session:
        session.add(clinic)
        session.commit()
        clinic_id = clinic.id
    state = create_google_authorization_request(settings, clinic_id).state
    query = urlencode({"state": state, "code": "test-code"})

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        with patch(
            "app.api.google_auth.complete_google_oauth",
            side_effect=GoogleOAuthPersistenceError(
                "Google credentials could not be stored in the database."
            ),
        ):
            response = await client.get(
                f"/auth/google/callback?{query}",
                follow_redirects=False,
            )

    assert response.status_code == 302
    redirect_query = parse_qs(urlparse(response.headers["location"]).query)
    assert redirect_query["google"] == ["error"]
    assert redirect_query["reason"] == ["db_save_failed"]


@pytest.mark.anyio
async def test_google_oauth_callback_invalid_state_redirects_with_reason(
    database_engine: Engine,
) -> None:
    """Bad Fernet/state input should redirect with a clear reason."""
    settings = _valid_oauth_settings()

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/auth/google/callback?state=bad-state&code=test-code",
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("http://localhost:5173/settings?")
    redirect_query = parse_qs(urlparse(location).query)
    assert redirect_query["google"] == ["error"]
    assert redirect_query["reason"] == ["invalid_state"]


def test_google_calendar_routes_are_registered() -> None:
    """The requested OAuth and Calendar endpoints should be present."""
    paths = set(create_app().openapi()["paths"])

    assert "/auth/google/start" in paths
    assert "/auth/google/callback" in paths
    assert "/api/calendar/status" in paths
    assert "/api/calendar/list" in paths
    assert "/api/workers/{worker_id}/create-calendar" in paths
    assert "/api/workers/{worker_id}/link-calendar" in paths
