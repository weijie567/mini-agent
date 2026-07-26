"""Runtime-private authenticated customer context."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from .common import RuntimePrivateModel, require_utc

NonEmptyString = Annotated[str, Field(min_length=1)]


class CustomerContext(RuntimePrivateModel):
    """Trusted identity derived only by a server-side authentication adapter."""

    provenance: Literal["SERVER_AUTH_ADAPTER"] = "SERVER_AUTH_ADAPTER"
    subject_ref: NonEmptyString
    customer_id: NonEmptyString
    auth_scopes: frozenset[NonEmptyString]
    authenticated_at: datetime
    session_ref_hash: NonEmptyString

    @field_validator("authenticated_at")
    @classmethod
    def authenticated_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="authenticated_at")


class RuntimePrivateContext(RuntimePrivateModel):
    """Per-Run private context passed only to deterministic control code."""

    run_id: UUID
    customer_context: CustomerContext
