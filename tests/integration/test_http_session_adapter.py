from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mini_agent.api.http import create_agent_app
from mini_agent.application.records import AgentRunCommand, AgentRunResult
from mini_agent.core.trace import AgentOutcome
from mini_agent.infrastructure.auth.p0_session import (
    P0SessionAuthAdapter,
    P0SessionFixture,
)

UTC_NOW = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
RAW_ACTIVE_SESSION = "p0-session-alice"


class RecordingHandler:
    def __init__(self) -> None:
        self.commands: list[AgentRunCommand] = []

    async def handle(self, command: AgentRunCommand) -> AgentRunResult:
        self.commands.append(command)
        return AgentRunResult(
            run_id=UUID(int=901),
            outcome=AgentOutcome.COMPLETED,
            message="已安全处理。",
        )


def _session_adapter() -> P0SessionAuthAdapter:
    fixtures = {
        RAW_ACTIVE_SESSION: P0SessionFixture(
            subject_ref="subject-alice",
            customer_id="customer-A",
            auth_scopes=frozenset({"orders:read"}),
            expires_at=UTC_NOW + timedelta(hours=1),
        ),
        "p0-session-expired": P0SessionFixture(
            subject_ref="subject-expired",
            customer_id="customer-A",
            auth_scopes=frozenset({"orders:read"}),
            expires_at=UTC_NOW - timedelta(seconds=1),
        ),
        "p0-session-disabled": P0SessionFixture(
            subject_ref="subject-disabled",
            customer_id="customer-A",
            auth_scopes=frozenset({"orders:read"}),
            expires_at=UTC_NOW + timedelta(hours=1),
            disabled=True,
        ),
    }
    return P0SessionAuthAdapter(fixtures, clock=lambda: UTC_NOW)


def _client(
    handler: RecordingHandler,
    *,
    session_adapter: P0SessionAuthAdapter | None = None,
) -> TestClient:
    return TestClient(
        create_agent_app(
            session_auth=session_adapter or _session_adapter(),
            handler=handler,
        )
    )


def test_authenticated_http_request_uses_server_identity_and_minimal_response() -> None:
    handler = RecordingHandler()
    client = _client(handler)

    response = client.post(
        "/v1/agent/runs",
        cookies={"p0_session": RAW_ACTIVE_SESSION},
        json={"message": "查订单 O-1001"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "00000000-0000-0000-0000-000000000385",
        "outcome": "COMPLETED",
        "message": "已安全处理。",
    }
    assert len(handler.commands) == 1
    command = handler.commands[0]
    assert command.message == "查订单 O-1001"
    assert command.customer_context.customer_id == "customer-A"
    assert command.customer_context.provenance == "SERVER_AUTH_ADAPTER"
    assert command.customer_context.session_ref_hash != RAW_ACTIVE_SESSION
    assert len(command.customer_context.session_ref_hash) == 64
    assert RAW_ACTIVE_SESSION not in command.model_dump_json()


@pytest.mark.parametrize(
    ("case_name", "cookies"),
    [
        ("missing", None),
        ("unknown", {"p0_session": "p0-session-unknown"}),
        ("expired", {"p0_session": "p0-session-expired"}),
        ("disabled", {"p0_session": "p0-session-disabled"}),
    ],
)
def test_session_failures_are_uniform_and_authenticate_before_handler(
    case_name: str,
    cookies: dict[str, str] | None,
) -> None:
    handler = RecordingHandler()
    client = _client(handler)

    response = client.post(
        "/v1/agent/runs",
        cookies=cookies,
        json={"message": "查订单 O-1001"},
    )

    assert response.status_code == 401, case_name
    assert response.json() == {"detail": "UNAUTHORIZED"}
    assert handler.commands == []
    assert "p0-session" not in response.text


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("customer_id", "customer-B"),
        ("auth_scope", ["orders:read"]),
        ("session_id", "p0-session-bob"),
        ("run_id", "00000000-0000-0000-0000-000000000001"),
        ("tool_name", "get_order"),
        ("tool_arguments", {"order_id": "O-2001"}),
    ],
)
def test_http_body_forbids_every_non_message_field_before_handler(
    field_name: str,
    field_value: object,
) -> None:
    handler = RecordingHandler()
    client = _client(handler)

    response = client.post(
        "/v1/agent/runs",
        cookies={"p0_session": RAW_ACTIVE_SESSION},
        json={"message": "查订单 O-1001", field_name: field_value},
    )

    assert response.status_code == 422, field_name
    assert handler.commands == []


def test_raw_cookie_is_absent_from_context_errors_and_log_capture(caplog) -> None:
    handler = RecordingHandler()
    client = _client(handler)

    response = client.post(
        "/v1/agent/runs",
        cookies={"p0_session": "raw-cookie-that-must-not-leak"},
        json={"message": "查订单 O-1001"},
    )

    assert response.status_code == 401
    assert "raw-cookie-that-must-not-leak" not in response.text
    assert "raw-cookie-that-must-not-leak" not in caplog.text
    assert handler.commands == []
