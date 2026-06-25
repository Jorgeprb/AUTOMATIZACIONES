"""Unit tests for OAuth and Google Calendar operations using mocked clients."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar.auth import (
    GOOGLE_CALENDAR_SCOPES,
    complete_google_oauth,
    create_google_authorization_request,
    decode_google_oauth_state,
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
from app.config import Settings
from app.main import create_app
from app.models import AppointmentSource, Clinic, GoogleCredential, Worker
from app.utils.security import TokenCipher


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


def test_google_calendar_routes_are_registered() -> None:
    """The requested OAuth and Calendar endpoints should be present."""
    paths = set(create_app().openapi()["paths"])

    assert "/auth/google/start" in paths
    assert "/auth/google/callback" in paths
    assert "/api/calendar/status" in paths
    assert "/api/calendar/list" in paths
    assert "/api/workers/{worker_id}/create-calendar" in paths
    assert "/api/workers/{worker_id}/link-calendar" in paths
