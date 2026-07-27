from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from mini_agent.core.common import RuntimePrivateModel, require_utc
from mini_agent.core.identity import CustomerContext


class P0SessionFixture(RuntimePrivateModel):
    """Server-owned P0 identity fixture; never populated from request data."""

    model_config = ConfigDict(strict=True, extra="forbid")

    subject_ref: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    auth_scopes: frozenset[str]
    expires_at: datetime
    disabled: bool = False

    @field_validator("expires_at")
    @classmethod
    def expires_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="expires_at")


class P0SessionAuthAdapter:
    """Resolve opaque cookies against an in-memory server configuration."""

    def __init__(
        self,
        fixtures: Mapping[str, P0SessionFixture],
        *,
        clock: Callable[[], datetime],
    ) -> None:
        hashed_fixtures: dict[str, P0SessionFixture] = {}
        for opaque_session_id, fixture in fixtures.items():
            if not opaque_session_id:
                raise ValueError("P0 Session fixture key cannot be empty")
            digest = self._session_hash(opaque_session_id)
            if digest in hashed_fixtures:
                raise ValueError("P0 Session fixture hash collision")
            hashed_fixtures[digest] = P0SessionFixture.model_validate(
                fixture,
                strict=True,
            )
        self._fixtures_by_hash = hashed_fixtures
        self._clock = clock

    @staticmethod
    def _session_hash(opaque_session_id: str) -> str:
        return hashlib.sha256(opaque_session_id.encode("utf-8")).hexdigest()

    async def authenticate(
        self,
        opaque_session_id: str,
    ) -> CustomerContext | None:
        if not opaque_session_id:
            return None
        session_ref_hash = self._session_hash(opaque_session_id)
        fixture = self._fixtures_by_hash.get(session_ref_hash)
        if fixture is None:
            return None
        authenticated_at = require_utc(
            self._clock(),
            field_name="session authentication time",
        )
        if fixture.disabled or fixture.expires_at <= authenticated_at:
            return None
        return CustomerContext(
            subject_ref=fixture.subject_ref,
            customer_id=fixture.customer_id,
            auth_scopes=fixture.auth_scopes,
            authenticated_at=authenticated_at,
            session_ref_hash=session_ref_hash,
        )
