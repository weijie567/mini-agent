"""Closed authenticated W9 seed catalog and all-or-nothing business loader."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.tool_system import Cycle2ToolName
from mini_agent.infrastructure.auth.p0_session import P0SessionFixture
from mini_agent.infrastructure.cycle2_runtime import Cycle2AttemptFault
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockOrderSearchDocumentModel,
    MockShipmentModel,
)

SEED_SCHEMA_VERSION = "cycle2-offline-seed.p0.v1"
TRUSTED_CLOCK_PROFILE_REF = "clock:cycle2-w9-v1"
TRUSTED_CLOCK = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
_SESSION_ALICE = "session:alice"
_OWNER_A = "customer-A"


class Cycle2SeedError(RuntimeError):
    """Fail-closed seed validation error raised before any business write."""


class Cycle2FixtureKind(StrEnum):
    TRUSTED_SESSION = "TRUSTED_SESSION"
    ORDER_SEARCH_SETUP = "ORDER_SEARCH_SETUP"
    ORDER_SETUP = "ORDER_SETUP"
    SHIPMENT_SETUP = "SHIPMENT_SETUP"
    TASK_STATE_SETUP = "TASK_STATE_SETUP"
    TOOLSET_PAIR_SETUP = "TOOLSET_PAIR_SETUP"
    RUN_RECOVERY_SETUP = "RUN_RECOVERY_SETUP"


class _SeedModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


class TrustedSessionSeedV1(_SeedModel):
    opaque_session_id: str = Field(min_length=1)
    owner_customer_id: str = Field(min_length=1)
    subject_ref: str = Field(min_length=1)
    auth_scopes: tuple[str, ...]
    expires_at: datetime


class MockOrderSeedV1(_SeedModel):
    owner_customer_id: str = Field(min_length=1)
    order_id: str = Field(pattern=r"^O-[0-9]{4,20}$")
    order_payload: OrderSummaryProjection

    @model_validator(mode="after")
    def identity_matches_payload(self):
        if self.order_payload.order_number != self.order_id:
            raise ValueError("order seed identity mismatch")
        return self


class MockOrderSearchDocumentSeedV1(_SeedModel):
    owner_customer_id: str = Field(min_length=1)
    order_id: str = Field(pattern=r"^O-[0-9]{4,20}$")
    line_ordinal: int = Field(ge=1)
    ordered_at: datetime
    order_number: str = Field(pattern=r"^O-[0-9]{4,20}$")
    status: OrderStatus
    product_name: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    product_category: str = Field(min_length=1)
    search_aliases: tuple[str, ...]

    @model_validator(mode="after")
    def row_is_canonical(self):
        if (
            self.order_id != self.order_number
            or self.search_aliases
            != tuple(sorted(set(self.search_aliases)))
        ):
            raise ValueError("search document seed is not canonical")
        return self


class MockShipmentSeedV1(_SeedModel):
    owner_customer_id: str = Field(min_length=1)
    order_id: str = Field(pattern=r"^O-[0-9]{4,20}$")
    package_id: str = Field(min_length=1)
    shipment_payload: Mapping[str, object]


class Cycle2FaultAttemptV1(_SeedModel):
    attempt_no: int = Field(ge=1, le=2)
    outcome: str = Field(min_length=1)
    failure_code: str | None
    retry_decision: str


class Cycle2ReadFaultPlanV1(_SeedModel):
    canonical_tool_name: Cycle2ToolName
    attempt_outcomes: tuple[Cycle2FaultAttemptV1, ...]


class Cycle2OfflineSeedV1(_SeedModel):
    seed_schema_version: str
    fixture_ref: str = Field(min_length=1)
    fixture_kind: Cycle2FixtureKind
    owner_customer_id: str = Field(min_length=1)
    trusted_clock_profile_ref: str
    session_seeds: tuple[TrustedSessionSeedV1, ...]
    order_seeds: tuple[MockOrderSeedV1, ...]
    search_document_seeds: tuple[MockOrderSearchDocumentSeedV1, ...]
    shipment_seeds: tuple[MockShipmentSeedV1, ...]
    initial_record_graph: tuple[object, ...]
    initial_record_references: tuple[object, ...]
    fault_plan: Cycle2ReadFaultPlanV1 | None

    @model_validator(mode="after")
    def envelope_is_dispatchable_and_empty(self):
        if (
            self.seed_schema_version != SEED_SCHEMA_VERSION
            or self.trusted_clock_profile_ref != TRUSTED_CLOCK_PROFILE_REF
            or self.initial_record_graph
            or self.initial_record_references
            or any(
                seed.owner_customer_id != self.owner_customer_id
                for family in (
                    self.session_seeds,
                    self.order_seeds,
                    self.search_document_seeds,
                    self.shipment_seeds,
                )
                for seed in family
            )
        ):
            raise ValueError("invalid Cycle 2 offline seed envelope")
        return self


class ResolvedCycle2SeedPlan(_SeedModel):
    owner_customer_id: str
    fixture_refs: tuple[str, ...]
    session_seeds: tuple[TrustedSessionSeedV1, ...]
    order_seeds: tuple[MockOrderSeedV1, ...]
    search_document_seeds: tuple[MockOrderSearchDocumentSeedV1, ...]
    shipment_seeds: tuple[MockShipmentSeedV1, ...]
    initial_record_graph: tuple[object, ...]
    initial_record_references: tuple[object, ...]
    attempt_faults: tuple[Cycle2AttemptFault, ...]

    @model_validator(mode="after")
    def plan_is_owner_closed(self):
        if (
            self.owner_customer_id != _OWNER_A
            or self.initial_record_graph
            or self.initial_record_references
            or any(
                seed.owner_customer_id != self.owner_customer_id
                for family in (
                    self.session_seeds,
                    self.order_seeds,
                    self.search_document_seeds,
                    self.shipment_seeds,
                )
                for seed in family
            )
        ):
            raise ValueError("resolved Cycle 2 seed plan escaped owner scope")
        return self

    def session_fixtures(self) -> Mapping[str, P0SessionFixture]:
        return MappingProxyType(
            {
                seed.opaque_session_id: P0SessionFixture(
                    subject_ref=seed.subject_ref,
                    customer_id=seed.owner_customer_id,
                    auth_scopes=frozenset(seed.auth_scopes),
                    expires_at=seed.expires_at,
                )
                for seed in self.session_seeds
            }
        )

    def session_owners_by_hash(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                hashlib.sha256(
                    seed.opaque_session_id.encode("utf-8")
                ).hexdigest(): seed.owner_customer_id
                for seed in self.session_seeds
            }
        )


def _order(
    order_id: str,
    *,
    status: OrderStatus,
    product_name: str,
    ordered_at: datetime,
    updated_at: datetime,
) -> MockOrderSeedV1:
    return MockOrderSeedV1(
        owner_customer_id=_OWNER_A,
        order_id=order_id,
        order_payload=OrderSummaryProjection(
            order_number=order_id,
            status=status,
            line_items=(
                OrderLineSummary(product_name=product_name, quantity=1),
            ),
            ordered_at=ordered_at,
            status_updated_at=updated_at,
        ),
    )


_ORDER_A1001 = _order(
    "O-1001",
    status=OrderStatus.SHIPPED,
    product_name="轻量跑鞋",
    ordered_at=datetime(2026, 7, 10, 9, 0, tzinfo=UTC),
    updated_at=datetime(2026, 7, 11, 8, 0, tzinfo=UTC),
)
_ORDER_A1002 = _order(
    "O-1002",
    status=OrderStatus.PAID,
    product_name="复古跑鞋",
    ordered_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
    updated_at=datetime(2026, 7, 20, 10, 5, tzinfo=UTC),
)


def _search(order: MockOrderSeedV1, product_name: str) -> MockOrderSearchDocumentSeedV1:
    return MockOrderSearchDocumentSeedV1(
        owner_customer_id=order.owner_customer_id,
        order_id=order.order_id,
        line_ordinal=1,
        ordered_at=order.order_payload.ordered_at,
        order_number=order.order_id,
        status=order.order_payload.status,
        product_name=product_name,
        quantity=1,
        product_category="鞋",
        search_aliases=("跑鞋", "鞋"),
    )


_SEARCH_A1001 = _search(_ORDER_A1001, "轻量跑鞋")
_SEARCH_A1002 = _search(_ORDER_A1002, "复古跑鞋")
_SESSION = TrustedSessionSeedV1(
    opaque_session_id=_SESSION_ALICE,
    owner_customer_id=_OWNER_A,
    subject_ref="fixture-subject:session:alice",
    auth_scopes=("orders:read",),
    expires_at=datetime(2027, 1, 1, tzinfo=UTC),
)


def _shipment(*, stalled: bool) -> MockShipmentSeedV1:
    return MockShipmentSeedV1(
        owner_customer_id=_OWNER_A,
        order_id="O-1001",
        package_id="PKG-1001",
        shipment_payload={
            "shipment_status": "IN_TRANSIT",
            "latest_event_code": (
                "ARRIVED_AT_FACILITY" if stalled else "IN_TRANSIT"
            ),
            "latest_event_at": (
                "2026-07-24T08:00:00Z"
                if stalled
                else "2026-07-31T09:00:00Z"
            ),
            "promised_delivery_at": (
                "2026-07-28T18:00:00Z"
                if stalled
                else "2026-08-02T18:00:00Z"
            ),
            "delivered_at": None,
            "observed_at": (
                "2026-07-31T11:59:00Z"
                if stalled
                else "2026-07-31T09:05:00Z"
            ),
        },
    )


def _envelope(
    fixture_ref: str,
    fixture_kind: Cycle2FixtureKind,
    *,
    sessions: tuple[TrustedSessionSeedV1, ...] = (),
    orders: tuple[MockOrderSeedV1, ...] = (),
    searches: tuple[MockOrderSearchDocumentSeedV1, ...] = (),
    shipments: tuple[MockShipmentSeedV1, ...] = (),
) -> Cycle2OfflineSeedV1:
    return Cycle2OfflineSeedV1(
        seed_schema_version=SEED_SCHEMA_VERSION,
        fixture_ref=fixture_ref,
        fixture_kind=fixture_kind,
        owner_customer_id=_OWNER_A,
        trusted_clock_profile_ref=TRUSTED_CLOCK_PROFILE_REF,
        session_seeds=sessions,
        order_seeds=orders,
        search_document_seeds=searches,
        shipment_seeds=shipments,
        initial_record_graph=(),
        initial_record_references=(),
        fault_plan=None,
    )


_CATALOG = MappingProxyType(
    {
        "fx-search-unique-owner-a-with-foreign-decoy-v1": _envelope(
            "fx-search-unique-owner-a-with-foreign-decoy-v1",
            Cycle2FixtureKind.ORDER_SEARCH_SETUP,
            sessions=(_SESSION,),
            orders=(_ORDER_A1001,),
            searches=(_SEARCH_A1001,),
        ),
        "fx-search-multiple-owner-a-v1": _envelope(
            "fx-search-multiple-owner-a-v1",
            Cycle2FixtureKind.ORDER_SEARCH_SETUP,
            sessions=(_SESSION,),
            orders=(_ORDER_A1001, _ORDER_A1002),
            searches=(_SEARCH_A1001, _SEARCH_A1002),
        ),
        "fx-dynamic-tool-pair-owner-a-v1": _envelope(
            "fx-dynamic-tool-pair-owner-a-v1",
            Cycle2FixtureKind.TOOLSET_PAIR_SETUP,
            sessions=(_SESSION,),
            orders=(_ORDER_A1001,),
            searches=(_SEARCH_A1001,),
            shipments=(_shipment(stalled=False),),
        ),
        "fx-shipment-refresh-stalled-owner-a-v1": _envelope(
            "fx-shipment-refresh-stalled-owner-a-v1",
            Cycle2FixtureKind.SHIPMENT_SETUP,
            shipments=(_shipment(stalled=True),),
        ),
        "fx-shipment-current-owner-a-v1": _envelope(
            "fx-shipment-current-owner-a-v1",
            Cycle2FixtureKind.SHIPMENT_SETUP,
            shipments=(_shipment(stalled=False),),
        ),
    }
)

_FAULT_REF = "fault:get-shipment:transient-once-v1"


def cycle2_dispatchable_fixture_catalog() -> Mapping[str, Cycle2OfflineSeedV1]:
    return _CATALOG


def _deduplicate_exact(records: Iterable[BaseModel], *, key_fields: tuple[str, ...]):
    by_key: dict[tuple[object, ...], BaseModel] = {}
    for record in records:
        key = tuple(getattr(record, field) for field in key_fields)
        previous = by_key.get(key)
        if previous is not None and previous != record:
            raise Cycle2SeedError("conflicting Cycle 2 seed row")
        by_key[key] = record
    return tuple(by_key[key] for key in sorted(by_key))


def resolve_cycle2_seed_plan(
    fixture_refs: Iterable[str],
) -> ResolvedCycle2SeedPlan:
    refs = tuple(fixture_refs)
    if not refs or len(refs) != len(set(refs)):
        raise Cycle2SeedError("fixture refs must be non-empty and unique")
    envelopes = []
    faults = []
    for ref in refs:
        if ref == _FAULT_REF:
            faults.append(
                Cycle2AttemptFault(
                    canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                    attempt_no=1,
                    error_code="SHIPMENT_SERVICE_TRANSIENT",
                )
            )
            continue
        envelope = _CATALOG.get(ref)
        if envelope is None:
            raise Cycle2SeedError("unknown or reference-only Cycle 2 fixture")
        envelopes.append(envelope)
    if not envelopes:
        raise Cycle2SeedError("fault ref cannot seed without a real fixture")
    owners = {envelope.owner_customer_id for envelope in envelopes}
    if owners != {_OWNER_A}:
        raise Cycle2SeedError("cross-owner Cycle 2 seed composition")
    sessions = _deduplicate_exact(
        (seed for envelope in envelopes for seed in envelope.session_seeds),
        key_fields=("opaque_session_id",),
    )
    orders = _deduplicate_exact(
        (seed for envelope in envelopes for seed in envelope.order_seeds),
        key_fields=("owner_customer_id", "order_id"),
    )
    searches = _deduplicate_exact(
        (
            seed
            for envelope in envelopes
            for seed in envelope.search_document_seeds
        ),
        key_fields=("owner_customer_id", "order_id", "line_ordinal"),
    )
    shipments = _deduplicate_exact(
        (seed for envelope in envelopes for seed in envelope.shipment_seeds),
        key_fields=("owner_customer_id", "order_id", "package_id"),
    )
    order_keys = {
        (seed.owner_customer_id, seed.order_id) for seed in orders
    }
    if any(
        (seed.owner_customer_id, seed.order_id) not in order_keys
        for seed in searches
    ):
        raise Cycle2SeedError("search seed lacks its exact order parent")
    return ResolvedCycle2SeedPlan(
        owner_customer_id=_OWNER_A,
        fixture_refs=tuple(sorted(refs)),
        session_seeds=sessions,
        order_seeds=orders,
        search_document_seeds=searches,
        shipment_seeds=shipments,
        initial_record_graph=(),
        initial_record_references=(),
        attempt_faults=tuple(faults),
    )


def compute_cycle2_pair_seed_digest(plan: ResolvedCycle2SeedPlan) -> str:
    projection = {
        "digest_schema": "cycle2-owner-order-initial-state.p0.v1",
        "owner_customer_id": plan.owner_customer_id,
        "session_refs": sorted(
            seed.opaque_session_id for seed in plan.session_seeds
        ),
        "order_seeds": [
            seed.model_dump(mode="json") for seed in plan.order_seeds
        ],
        "search_document_seeds": [
            seed.model_dump(mode="json")
            for seed in plan.search_document_seeds
        ],
        "shipment_seeds": [
            seed.model_dump(mode="json") for seed in plan.shipment_seeds
        ],
        "initial_record_graph": [],
        "initial_record_references": [],
    }
    encoded = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_cycle2_seed_plan(
    session_factory: sessionmaker[Session],
    plan: ResolvedCycle2SeedPlan,
) -> None:
    """Validate every input/current row, then apply one atomic business seed."""

    if type(plan) is not ResolvedCycle2SeedPlan:
        raise Cycle2SeedError("resolved typed Cycle 2 seed plan required")
    try:
        canonical = ResolvedCycle2SeedPlan.model_validate_json(
            plan.model_dump_json(),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError):
        raise Cycle2SeedError("non-canonical Cycle 2 seed plan") from None
    if canonical != plan:
        raise Cycle2SeedError("non-canonical Cycle 2 seed plan")
    with session_factory.begin() as session:
        existing_orders = {
            (row.customer_id, row.order_id): row
            for row in session.scalars(select(MockOrderModel))
        }
        existing_searches = {
            (row.customer_id, row.order_id, row.line_ordinal): row
            for row in session.scalars(select(MockOrderSearchDocumentModel))
        }
        existing_shipments = {
            (row.customer_id, row.order_id, row.package_id): row
            for row in session.scalars(select(MockShipmentModel))
        }
        for seed in plan.order_seeds:
            key = (seed.owner_customer_id, seed.order_id)
            existing = existing_orders.get(key)
            payload = seed.order_payload.model_dump(mode="json")
            if existing is not None and existing.order_payload != payload:
                raise Cycle2SeedError("conflicting existing order seed")
        for seed in plan.search_document_seeds:
            key = (seed.owner_customer_id, seed.order_id, seed.line_ordinal)
            existing = existing_searches.get(key)
            if existing is not None and any(
                (
                    existing.ordered_at != seed.ordered_at,
                    existing.order_number != seed.order_number,
                    existing.status != seed.status.value,
                    existing.product_name != seed.product_name,
                    existing.quantity != seed.quantity,
                    existing.product_category != seed.product_category,
                    tuple(existing.search_aliases) != seed.search_aliases,
                )
            ):
                raise Cycle2SeedError("conflicting existing search seed")
        available_orders = set(existing_orders) | {
            (seed.owner_customer_id, seed.order_id)
            for seed in plan.order_seeds
        }
        if any(
            (seed.owner_customer_id, seed.order_id) not in available_orders
            for seed in plan.shipment_seeds
        ):
            raise Cycle2SeedError("shipment seed lacks its exact order parent")

        for seed in plan.order_seeds:
            session.execute(
                insert(MockOrderModel)
                .values(
                    customer_id=seed.owner_customer_id,
                    order_id=seed.order_id,
                    order_payload=seed.order_payload.model_dump(mode="json"),
                )
                .on_conflict_do_nothing()
            )
        for seed in plan.search_document_seeds:
            session.execute(
                insert(MockOrderSearchDocumentModel)
                .values(
                    customer_id=seed.owner_customer_id,
                    order_id=seed.order_id,
                    line_ordinal=seed.line_ordinal,
                    ordered_at=seed.ordered_at,
                    order_number=seed.order_number,
                    status=seed.status.value,
                    product_name=seed.product_name,
                    quantity=seed.quantity,
                    product_category=seed.product_category,
                    search_aliases=list(seed.search_aliases),
                )
                .on_conflict_do_nothing()
            )
        for seed in plan.shipment_seeds:
            session.execute(
                insert(MockShipmentModel)
                .values(
                    customer_id=seed.owner_customer_id,
                    order_id=seed.order_id,
                    package_id=seed.package_id,
                    shipment_payload=dict(seed.shipment_payload),
                )
                .on_conflict_do_update(
                    index_elements=(
                        MockShipmentModel.customer_id,
                        MockShipmentModel.order_id,
                        MockShipmentModel.package_id,
                    ),
                    set_={"shipment_payload": dict(seed.shipment_payload)},
                )
            )
