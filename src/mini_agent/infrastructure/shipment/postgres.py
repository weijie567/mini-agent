"""PostgreSQL implementation of the owner-scoped Shipment business read."""

from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.core.common import require_utc
from mini_agent.core.shipment import (
    GetShipmentFailureCode,
    GetShipmentInsufficiencyCode as ShipmentInsufficiencyCode,
    GetShipmentOutcome,
    GetShipmentQuery,
    GetShipmentResult,
    ShipmentEventCode,
    ShipmentStatus,
    ShipmentSummaryProjection,
    compute_shipment_source_version,
)
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockShipmentModel,
)

_UTC_RFC3339_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)$"
)
_OWNER_PACKAGE_REF_SCHEMA = "mock-owner-package-ref.p0.v1"
_SHIPMENT_PROMISE_MISSING = (
    ShipmentInsufficiencyCode.SHIPMENT_PROMISE_MISSING_FOR_ACTIVE_DELIVERY
)
_ALLOWED_LATEST_EVENTS = {
    ShipmentStatus.LABEL_CREATED: frozenset({ShipmentEventCode.LABEL_CREATED}),
    ShipmentStatus.IN_TRANSIT: frozenset(
        {
            ShipmentEventCode.PICKED_UP,
            ShipmentEventCode.IN_TRANSIT,
            ShipmentEventCode.ARRIVED_AT_FACILITY,
        }
    ),
    ShipmentStatus.OUT_FOR_DELIVERY: frozenset(
        {ShipmentEventCode.OUT_FOR_DELIVERY}
    ),
    ShipmentStatus.DELIVERED: frozenset({ShipmentEventCode.DELIVERED}),
}


class _ShipmentAuthorityPayload(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    shipment_status: ShipmentStatus
    latest_event_code: ShipmentEventCode | None = None
    latest_event_at: datetime | None = None
    promised_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    observed_at: datetime

    @field_validator(
        "latest_event_at",
        "promised_delivery_at",
        "delivered_at",
        "observed_at",
        mode="before",
    )
    @classmethod
    def timestamps_are_strict_utc(cls, value: object) -> object:
        if value is None:
            return None
        if type(value) is not str or _UTC_RFC3339_PATTERN.fullmatch(value) is None:
            raise ValueError("Shipment authority timestamps must be UTC RFC 3339")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return require_utc(parsed, field_name="Shipment authority timestamp")


def _owner_scoped_package_ref(
    *,
    customer_id: str,
    order_id: str,
    package_id: str,
) -> str:
    canonical_payload = {
        "ref_schema": _OWNER_PACKAGE_REF_SCHEMA,
        "owner_customer_id": customer_id,
        "order_id": order_id,
        "package_id": package_id,
    }
    canonical_bytes = json.dumps(
        canonical_payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        f"{_OWNER_PACKAGE_REF_SCHEMA}:sha256:"
        f"{sha256(canonical_bytes).hexdigest()}"
    )


def _facts_insufficient(
    code: ShipmentInsufficiencyCode,
) -> GetShipmentResult:
    return GetShipmentResult(
        outcome=GetShipmentOutcome.FACTS_INSUFFICIENT,
        insufficiency_code=code,
    )


class PostgresGetShipmentAdapter:
    """Resolve the closed own-order to active-Package relation in one query."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    async def get_shipment(self, query: GetShipmentQuery) -> GetShipmentResult:
        statement = (
            select(
                MockOrderModel.order_id.label("verified_order_id"),
                MockShipmentModel.package_id,
                MockShipmentModel.shipment_payload,
            )
            .select_from(MockOrderModel)
            .outerjoin(
                MockShipmentModel,
                and_(
                    MockShipmentModel.customer_id == MockOrderModel.customer_id,
                    MockShipmentModel.order_id == MockOrderModel.order_id,
                ),
            )
            .where(
                MockOrderModel.customer_id == query.customer_id,
                MockOrderModel.order_id == query.order_id,
            )
            .order_by(MockShipmentModel.package_id.asc())
        )
        try:
            with self.session_factory() as session:
                rows = tuple(session.execute(statement).all())

            if not rows:
                return GetShipmentResult(
                    outcome=GetShipmentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
                )
            if any(row.verified_order_id != query.order_id for row in rows):
                raise ValueError("Shipment relation escaped the verified order")

            packages = tuple(row for row in rows if row.package_id is not None)
            if not packages:
                return GetShipmentResult(outcome=GetShipmentOutcome.NO_SHIPMENT)
            if len(packages) > 1:
                return GetShipmentResult(
                    outcome=GetShipmentOutcome.SYSTEM_FAILURE,
                    failure_code=(
                        GetShipmentFailureCode.SHIPMENT_RELATION_CARDINALITY_VIOLATION
                    ),
                )

            package = packages[0]
            if type(package.package_id) is not str or not package.package_id:
                raise ValueError("Shipment package identity is incomplete")
            if type(package.shipment_payload) is not dict:
                raise TypeError("Shipment authority payload must be an object")
            authority = _ShipmentAuthorityPayload.model_validate_json(
                json.dumps(
                    package.shipment_payload,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )

            if (
                authority.latest_event_code is not None
                and authority.latest_event_code
                not in _ALLOWED_LATEST_EVENTS[authority.shipment_status]
            ):
                raise ValueError("Shipment status and latest event conflict")
            if (
                authority.latest_event_at is not None
                and authority.latest_event_at > authority.observed_at
            ):
                raise ValueError("Shipment latest event is after observed_at")
            if (
                authority.shipment_status is not ShipmentStatus.DELIVERED
                and authority.delivered_at is not None
            ):
                raise ValueError("Active Shipment cannot carry delivered_at")
            if (
                authority.shipment_status is ShipmentStatus.DELIVERED
                and authority.delivered_at is not None
                and authority.latest_event_at is not None
                and authority.delivered_at != authority.latest_event_at
            ):
                raise ValueError("Shipment delivered_at conflicts with latest event")

            if (
                authority.latest_event_code is None
                or authority.latest_event_at is None
            ):
                return _facts_insufficient(
                    ShipmentInsufficiencyCode.SHIPMENT_LATEST_EVENT_MISSING
                )
            if (
                authority.shipment_status is not ShipmentStatus.DELIVERED
                and authority.promised_delivery_at is None
            ):
                return _facts_insufficient(
                    _SHIPMENT_PROMISE_MISSING
                )
            if (
                authority.shipment_status is ShipmentStatus.DELIVERED
                and authority.delivered_at is None
            ):
                return _facts_insufficient(
                    ShipmentInsufficiencyCode.SHIPMENT_DELIVERED_AT_MISSING
                )

            summary = ShipmentSummaryProjection(
                shipment_status=authority.shipment_status,
                latest_event_code=authority.latest_event_code,
                latest_event_at=authority.latest_event_at,
                promised_delivery_at=authority.promised_delivery_at,
                delivered_at=authority.delivered_at,
            )
            source_resource_ref = _owner_scoped_package_ref(
                customer_id=query.customer_id,
                order_id=query.order_id,
                package_id=package.package_id,
            )
            source_version = compute_shipment_source_version(
                owner_customer_id=query.customer_id,
                order_id=query.order_id,
                source_resource_ref=source_resource_ref,
                observed_at=authority.observed_at,
                safe_projection=summary,
            )
            return GetShipmentResult(
                outcome=GetShipmentOutcome.FOUND,
                shipment_summary=summary,
                source_resource_ref=source_resource_ref,
                source_version=source_version,
                observed_at=authority.observed_at,
            )
        except SQLAlchemyError:
            return GetShipmentResult(
                outcome=GetShipmentOutcome.SYSTEM_FAILURE,
                failure_code=GetShipmentFailureCode.SHIPMENT_SERVICE_UNAVAILABLE,
            )
        except (
            ValidationError,
            TypeError,
            ValueError,
            UnicodeError,
            OverflowError,
        ):
            return GetShipmentResult(
                outcome=GetShipmentOutcome.SYSTEM_FAILURE,
                failure_code=GetShipmentFailureCode.SHIPMENT_SOURCE_INTEGRITY,
            )
