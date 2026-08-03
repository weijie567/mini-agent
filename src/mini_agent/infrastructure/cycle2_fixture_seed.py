"""Closed authenticated W9 seed catalog and all-or-nothing business loader."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from types import MappingProxyType
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.tool_system import (
    RegistrySnapshot,
    compute_provider_mapping_digest,
    compute_registry_snapshot_digest,
)
from mini_agent.application.persistence import (
    P0PersistenceEnvelope,
    P0RecordCode,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ConversationRecord,
    ConversationTaskLinkRecord,
    MessageDirection,
    MessageRecord,
    RunTaskLinkRecordV2,
)
from mini_agent.core.memory import (
    ContextManifest,
    SearchObservationCandidateTargetBinding,
    SearchOrdersObservation,
    SearchOrdersObservationCandidate,
    SearchOrdersObservationValue,
    ShipmentObservation,
    TaskStateRefAndVersion,
    TokenCounts,
)
from mini_agent.core.order_search import (
    MatchedOrderLine,
    OrderCandidate,
    build_order_candidate_public_summary,
    build_search_orders_query,
    compute_order_candidate_source_version,
    compute_order_search_snapshot_source_version,
    sort_order_candidates,
)
from mini_agent.core.request_understanding import InputAuthority
from mini_agent.core.shipment import (
    GetShipmentFailureCode,
    ShipmentEventCode,
    ShipmentStatus,
    ShipmentSummaryProjection,
    compute_shipment_source_version,
)
from mini_agent.core.task_state import (
    InputBindingV2,
    InputValidationStatus,
    OrderCandidateAutoTargetRecord,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
    compute_order_candidate_set_version,
)
from mini_agent.infrastructure.auth.p0_session import P0SessionFixture
from mini_agent.infrastructure.cycle2_runtime import (
    Cycle2AttemptFault,
    Cycle2DetachedExecutionSetup,
    Cycle2ExecutionSetupAttachmentTarget,
    Cycle2FaultBoundary,
    Cycle2FaultDirective,
    Cycle2FaultDirectiveKind,
    Cycle2RestartKind,
    build_cycle2_detached_fault_controller,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    GateDecisionV2,
    GateDecisionValue,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecordV2,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    ToolRetryDecision,
    build_cycle2_registry_snapshot,
)
from mini_agent.core.trace import (
    AgentRunRecordV2,
    AgentRunStatusV2,
    StopReasonV2,
    TraceEventType,
    TraceEventV2,
)
from mini_agent.infrastructure.persistence.models import (
    MockOrderModel,
    MockOrderSearchDocumentModel,
    MockShipmentModel,
    P0RecordModel,
)

SEED_SCHEMA_VERSION = "cycle2-offline-seed.p0.v1"
TRUSTED_CLOCK_PROFILE_REF = "clock:cycle2-w9-v1"
TRUSTED_CLOCK = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
_SESSION_ALICE = "session:alice"
_OWNER_A = "customer-A"
_W12_SETUP_NAMESPACE_CLAIMS: set[tuple[str, str]] = set()
_W12_SETUP_NAMESPACE_CLAIMS_LOCK = RLock()


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


# W12 is intentionally a different authenticated setup contract.  The W9
# catalog above remains the direct-seam boundary and is never widened by these
# definitions.
W12_SETUP_SCHEMA_VERSION = "cycle2-execution-setup.p0.v1"
W12_FIXTURE_CATALOG_VERSION = "e2e01-cycle2-fixture-v1"
W12_TRUSTED_CLOCK_PROFILE_REF = "clock:cycle2-w12-v1"
W12_TRUSTED_CLOCK = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


class Cycle2W12FixtureRecipe(StrEnum):
    SEARCH_UNIQUE_FOREIGN = "SEARCH_UNIQUE_FOREIGN"
    SEARCH_NO_MATCH = "SEARCH_NO_MATCH"
    SEARCH_MULTIPLE = "SEARCH_MULTIPLE"
    ORDER_TARGETS = "ORDER_TARGETS"
    CANDIDATE_CURRENT = "CANDIDATE_CURRENT"
    CANDIDATE_EXPIRED = "CANDIDATE_EXPIRED"
    CANDIDATE_OTHER_TASK = "CANDIDATE_OTHER_TASK"
    VERIFIED_ORDER_TARGET = "VERIFIED_ORDER_TARGET"
    DYNAMIC_PAIR = "DYNAMIC_PAIR"
    STALE_SHIPMENT_OBSERVATION = "STALE_SHIPMENT_OBSERVATION"
    CANDIDATE_OWNER_MISMATCH = "CANDIDATE_OWNER_MISMATCH"
    CANDIDATE_SUPERSEDED = "CANDIDATE_SUPERSEDED"
    CANDIDATE_CARDINALITY = "CANDIDATE_CARDINALITY"
    CORRECTED_NOT_RECEIVED = "CORRECTED_NOT_RECEIVED"
    RETRY_SCHEDULED_OBSOLETE_RUN = "RETRY_SCHEDULED_OBSOLETE_RUN"
    SHIPMENT_STALLED = "SHIPMENT_STALLED"
    SHIPMENT_CURRENT = "SHIPMENT_CURRENT"
    SHIPMENT_MISSING_PROMISE = "SHIPMENT_MISSING_PROMISE"
    ORDER_ZERO_PACKAGE = "ORDER_ZERO_PACKAGE"
    SHIPMENT_DELAYED_BOUNDARY = "SHIPMENT_DELAYED_BOUNDARY"
    SHIPMENT_DELIVERED = "SHIPMENT_DELIVERED"
    SHIPMENT_BORN_STALE = "SHIPMENT_BORN_STALE"
    TWO_ACTIVE_PACKAGES = "TWO_ACTIVE_PACKAGES"


class Cycle2W12IntegrityVector(StrEnum):
    CANDIDATE_MAPPING_OWNER_MISMATCH = "CANDIDATE_MAPPING_OWNER_MISMATCH"
    TWO_CURRENT_CANDIDATE_SETS = "TWO_CURRENT_CANDIDATE_SETS"
    TWO_ACTIVE_PACKAGES = "TWO_ACTIVE_PACKAGES"


class Cycle2W12FixtureDefinitionV1(_SeedModel):
    fixture_ref: str = Field(min_length=1)
    fixture_kind: Cycle2FixtureKind
    owner_customer_id: Literal["customer-A"] = "customer-A"
    catalog_order: int = Field(strict=True, ge=1, le=23)
    recipe: Cycle2W12FixtureRecipe
    prerequisite_fixture_refs: tuple[str, ...] = ()
    integrity_vector: Cycle2W12IntegrityVector | None = None


class Cycle2ExecutionFaultPlanV1(_SeedModel):
    fault_ref: str = Field(min_length=1)
    canonical_tool_name: Literal[Cycle2ToolName.GET_SHIPMENT] = (
        Cycle2ToolName.GET_SHIPMENT
    )
    directives: tuple[Cycle2FaultDirective, ...]

    @field_validator("directives", mode="before")
    @classmethod
    def directives_are_exact_native_objects(cls, value: object) -> object:
        if type(value) is not tuple or not value or not all(
            type(item) is Cycle2FaultDirective for item in value
        ):
            raise ValueError("fault directives require exact native typed objects")
        return value

    @model_validator(mode="after")
    def directives_are_unique_and_ordered(self) -> Self:
        identities = tuple(
            (item.canonical_tool_name, item.attempt_no, item.boundary)
            for item in self.directives
        )
        if (
            len(identities) != len(set(identities))
            or any(
                item.canonical_tool_name is not Cycle2ToolName.GET_SHIPMENT
                for item in self.directives
            )
            or tuple(item.attempt_no for item in self.directives)
            != tuple(sorted(item.attempt_no for item in self.directives))
        ):
            raise ValueError("fault plan directives are not canonical")
        return self


class Cycle2BusinessSeedRowsV1(_SeedModel):
    order_seeds: tuple[MockOrderSeedV1, ...] = ()
    search_document_seeds: tuple[MockOrderSearchDocumentSeedV1, ...] = ()
    shipment_seeds: tuple[MockShipmentSeedV1, ...] = ()


class Cycle2ForeignControlRowsV1(_SeedModel):
    order_seeds: tuple[MockOrderSeedV1, ...] = ()
    search_document_seeds: tuple[MockOrderSearchDocumentSeedV1, ...] = ()

    @model_validator(mode="after")
    def rows_are_exact_owner_b_controls(self) -> Self:
        if any(
            seed.owner_customer_id != "customer-B"
            for family in (self.order_seeds, self.search_document_seeds)
            for seed in family
        ):
            raise ValueError("foreign controls must be exact customer-B rows")
        return self


Cycle2CanonicalRuntimeRecord = (
    ConversationRecord
    | ConversationTaskLinkRecord
    | MessageRecord
    | AgentRunRecordV2
    | RunTaskLinkRecordV2
    | TaskRecord
    | RequestUnitRecord
    | InputBindingV2
    | SearchOrdersObservation
    | ShipmentObservation
    | OrderCandidateSetRecord
    | OrderCandidateAutoTargetRecord
    | GateDecisionV2
    | ToolCallRecordV2
    | TraceEventV2
    | ContextManifest
    | ModelVisibleToolsetArtifact
)


class Cycle2RuntimeBaseRecordV1(_SeedModel):
    """One existing canonical record type selected by a closed builder."""

    fixture_ref: str = Field(min_length=1)
    record_role: str = Field(min_length=1, pattern=r"^[a-z0-9_.-]+$")
    record_code: P0RecordCode
    source_record: Cycle2CanonicalRuntimeRecord

    @model_validator(mode="after")
    def code_matches_exact_source_type(self) -> Self:
        expected: dict[P0RecordCode, tuple[type[BaseModel], ...]] = {
            P0RecordCode.CONVERSATION_RECORD: (ConversationRecord,),
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
                ConversationTaskLinkRecord,
            ),
            P0RecordCode.MESSAGE_RECORD: (MessageRecord,),
            P0RecordCode.AGENT_RUN_RECORD: (AgentRunRecordV2,),
            P0RecordCode.RUN_TASK_LINK_RECORD: (RunTaskLinkRecordV2,),
            P0RecordCode.TASK_RECORD: (TaskRecord,),
            P0RecordCode.REQUEST_UNIT_RECORD: (RequestUnitRecord,),
            P0RecordCode.INPUT_BINDING_RECORD: (InputBindingV2,),
            P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD: (
                SearchOrdersObservation,
            ),
            P0RecordCode.SHIPMENT_OBSERVATION_RECORD: (ShipmentObservation,),
            P0RecordCode.ORDER_CANDIDATE_SET_RECORD: (
                OrderCandidateSetRecord,
            ),
            P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD: (
                OrderCandidateAutoTargetRecord,
            ),
            P0RecordCode.GATE_DECISION_RECORD: (GateDecisionV2,),
            P0RecordCode.TOOL_CALL_RECORD: (ToolCallRecordV2,),
            P0RecordCode.TRACE_EVENT_RECORD: (TraceEventV2,),
            P0RecordCode.CONTEXT_MANIFEST_RECORD: (ContextManifest,),
            P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT: (
                ModelVisibleToolsetArtifact,
            ),
        }
        allowed = expected.get(self.record_code)
        if allowed is None or type(self.source_record) not in allowed:
            raise ValueError("runtime setup record code/source type mismatch")
        return self


class Cycle2RuntimeOverlayV1(_SeedModel):
    fixture_ref: Literal["fx-corrected-not-received-claim-owner-a-v1"]
    prerequisite_fixture_ref: Literal[
        "fx-verified-order-target-o1001-owner-a-v1"
    ]
    expected_pre_images: tuple[Cycle2RuntimeBaseRecordV1, ...]
    next_records: tuple[Cycle2RuntimeBaseRecordV1, ...]

    @model_validator(mode="after")
    def overlay_has_distinct_exact_identity(self) -> Self:
        if not self.expected_pre_images or not self.next_records:
            raise ValueError("overlay requires expected pre-images and next records")
        if self.expected_pre_images == self.next_records:
            raise ValueError("overlay pre-image and next records must differ")
        return self


class Cycle2RuntimeSetupV1(_SeedModel):
    base_records: tuple[Cycle2RuntimeBaseRecordV1, ...] = ()
    overlays: tuple[Cycle2RuntimeOverlayV1, ...] = ()
    historical_user_messages: tuple[MessageRecord, ...] = ()
    recovery_subject_run_id: UUID | None = None
    integrity_vectors: tuple[Cycle2W12IntegrityVector, ...] = ()

    @field_validator("historical_user_messages", mode="before")
    @classmethod
    def messages_are_exact_native_records(cls, value: object) -> object:
        if type(value) is not tuple or not all(
            type(item) is MessageRecord for item in value
        ):
            raise ValueError("runtime setup messages must be exact MessageRecord")
        return value

    @model_validator(mode="after")
    def recovery_message_exception_is_exact(self) -> Self:
        if any(
            message.direction is not MessageDirection.USER
            for message in self.historical_user_messages
        ):
            raise ValueError("runtime setup can only preseed historical USER messages")
        if (
            self.recovery_subject_run_id is None
            and self.historical_user_messages
        ):
            raise ValueError(
                "ordinary setup cannot use the recovery message family"
            )
        if self.recovery_subject_run_id is not None and (
            len(self.historical_user_messages) != 1
            or self.historical_user_messages[0].direction
            is not MessageDirection.USER
        ):
            raise ValueError("recovery setup requires one historical USER Message")
        base_messages = tuple(
            record.source_record
            for record in self.base_records
            if type(record.source_record) is MessageRecord
        )
        if self.recovery_subject_run_id is not None and (
            self.historical_user_messages[0] not in base_messages
            or base_messages.count(self.historical_user_messages[0]) != 1
        ):
            raise ValueError(
                "recovery message family must name one exact base Message"
            )
        identities = tuple(
            (record.record_code, record.record_role)
            for record in self.base_records
        )
        if len(identities) != len(set(identities)):
            raise ValueError("runtime base record roles must be unique")
        if len(self.integrity_vectors) != len(set(self.integrity_vectors)):
            raise ValueError("integrity vectors must be unique")
        return self


class Cycle2PairExecutionEvidenceV1(_SeedModel):
    pair_id: Literal["PAIR-E2E01-05-V1"] = "PAIR-E2E01-05-V1"
    registry_snapshot_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    model_visible_toolset_hash: Annotated[
        str,
        Field(pattern=r"^sha256:[0-9a-f]{64}$"),
    ]
    provider_mapping_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    owner_order_initial_state_digest: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{64}$"),
    ]


class Cycle2ExecutionSetupPlanV1(_SeedModel):
    setup_schema_version: Literal["cycle2-execution-setup.p0.v1"]
    fixture_catalog_version: Literal["e2e01-cycle2-fixture-v1"]
    trusted_context_fixture_ref: Literal["session:alice"]
    owner_customer_id: Literal["customer-A"]
    trusted_clock_profile_ref: Literal["clock:cycle2-w12-v1"]
    fixture_refs: tuple[str, ...]
    business_rows: Cycle2BusinessSeedRowsV1
    runtime_state: Cycle2RuntimeSetupV1
    foreign_control_rows: Cycle2ForeignControlRowsV1
    fault_plan: Cycle2ExecutionFaultPlanV1 | None
    pair_evidence: Cycle2PairExecutionEvidenceV1 | None
    setup_digest: Annotated[
        str,
        Field(pattern=r"^sha256:[0-9a-f]{64}$"),
    ]

    @model_validator(mode="before")
    @classmethod
    def nested_native_models_are_exact(cls, value: object) -> object:
        if type(value) is not dict:
            raise TypeError("setup plan requires an exact object")
        for field_name, expected in (
            ("business_rows", Cycle2BusinessSeedRowsV1),
            ("runtime_state", Cycle2RuntimeSetupV1),
            ("foreign_control_rows", Cycle2ForeignControlRowsV1),
        ):
            candidate = value.get(field_name)
            if type(candidate) not in {expected, dict}:
                raise ValueError(f"{field_name} is not an exact typed setup family")
        return value

    @model_validator(mode="after")
    def plan_is_closed_and_digest_bound(self) -> Self:
        if (
            not self.fixture_refs
            or len(self.fixture_refs) != len(set(self.fixture_refs))
            or self.setup_digest != _compute_w12_setup_digest_payload(
                self.model_dump(mode="json", exclude={"setup_digest"})
            )
        ):
            raise ValueError("W12 setup plan is not canonical or digest-bound")
        allowed_foreign = {
            "fx-search-unique-owner-a-with-foreign-decoy-v1",
            "fx-candidate-owner-mismatch-owner-a-v1",
        }
        if (
            (self.foreign_control_rows.order_seeds or self.foreign_control_rows.search_document_seeds)
            and not set(self.fixture_refs).intersection(allowed_foreign)
        ):
            raise ValueError("foreign controls are not allowed for this fixture plan")
        if (
            self.runtime_state.recovery_subject_run_id is not None
            and "fx-retry-scheduled-obsolete-run-owner-a-v1"
            not in self.fixture_refs
        ):
            raise ValueError("recovery subject is outside the closed fixture")
        if (
            self.pair_evidence is not None
            and "fx-dynamic-tool-pair-owner-a-v1" not in self.fixture_refs
        ):
            raise ValueError("pair evidence is outside the closed pair fixture")
        return self


def deterministic_cycle2_setup_uuid(fixture_ref: str, role: str) -> UUID:
    if (
        type(fixture_ref) is not str
        or not fixture_ref
        or type(role) is not str
        or not role
    ):
        raise TypeError("fixture_ref and role must be non-empty strings")
    raw = bytearray(
        hashlib.sha256(
            f"e2e01-cycle2-w12|{fixture_ref}|{role}".encode("utf-8")
        ).digest()[:16]
    )
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(raw))


def _fixture(
    order: int,
    fixture_ref: str,
    kind: Cycle2FixtureKind,
    recipe: Cycle2W12FixtureRecipe,
    *,
    prerequisites: tuple[str, ...] = (),
    integrity: Cycle2W12IntegrityVector | None = None,
) -> Cycle2W12FixtureDefinitionV1:
    return Cycle2W12FixtureDefinitionV1(
        fixture_ref=fixture_ref,
        fixture_kind=kind,
        catalog_order=order,
        recipe=recipe,
        prerequisite_fixture_refs=prerequisites,
        integrity_vector=integrity,
    )


_W12_FIXTURE_ROWS = (
    ("fx-search-unique-owner-a-with-foreign-decoy-v1", Cycle2FixtureKind.ORDER_SEARCH_SETUP, Cycle2W12FixtureRecipe.SEARCH_UNIQUE_FOREIGN, (), None),
    ("fx-search-no-match-owner-a-v1", Cycle2FixtureKind.ORDER_SEARCH_SETUP, Cycle2W12FixtureRecipe.SEARCH_NO_MATCH, (), None),
    ("fx-search-multiple-owner-a-v1", Cycle2FixtureKind.ORDER_SEARCH_SETUP, Cycle2W12FixtureRecipe.SEARCH_MULTIPLE, (), None),
    ("fx-order-targets-owner-a-v1", Cycle2FixtureKind.ORDER_SETUP, Cycle2W12FixtureRecipe.ORDER_TARGETS, (), None),
    ("fx-current-candidate-set-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CANDIDATE_CURRENT, (), None),
    ("fx-expired-candidate-set-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CANDIDATE_EXPIRED, (), None),
    ("fx-candidate-set-other-task-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CANDIDATE_OTHER_TASK, (), None),
    ("fx-verified-order-target-o1001-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.VERIFIED_ORDER_TARGET, (), None),
    ("fx-dynamic-tool-pair-owner-a-v1", Cycle2FixtureKind.TOOLSET_PAIR_SETUP, Cycle2W12FixtureRecipe.DYNAMIC_PAIR, (), None),
    ("fx-stale-shipment-observation-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.STALE_SHIPMENT_OBSERVATION, (), None),
    ("fx-candidate-owner-mismatch-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CANDIDATE_OWNER_MISMATCH, (), Cycle2W12IntegrityVector.CANDIDATE_MAPPING_OWNER_MISMATCH),
    ("fx-superseded-candidate-set-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CANDIDATE_SUPERSEDED, (), None),
    ("fx-zero-or-multiple-current-candidate-set-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CANDIDATE_CARDINALITY, (), Cycle2W12IntegrityVector.TWO_CURRENT_CANDIDATE_SETS),
    ("fx-corrected-not-received-claim-owner-a-v1", Cycle2FixtureKind.TASK_STATE_SETUP, Cycle2W12FixtureRecipe.CORRECTED_NOT_RECEIVED, ("fx-verified-order-target-o1001-owner-a-v1",), None),
    ("fx-retry-scheduled-obsolete-run-owner-a-v1", Cycle2FixtureKind.RUN_RECOVERY_SETUP, Cycle2W12FixtureRecipe.RETRY_SCHEDULED_OBSOLETE_RUN, (), None),
    ("fx-shipment-refresh-stalled-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.SHIPMENT_STALLED, (), None),
    ("fx-shipment-current-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.SHIPMENT_CURRENT, (), None),
    ("fx-shipment-missing-promise-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.SHIPMENT_MISSING_PROMISE, (), None),
    ("fx-order-zero-active-package-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.ORDER_ZERO_PACKAGE, (), None),
    ("fx-shipment-delayed-boundary-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.SHIPMENT_DELAYED_BOUNDARY, (), None),
    ("fx-shipment-delivered-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.SHIPMENT_DELIVERED, (), None),
    ("fx-shipment-refresh-born-stale-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.SHIPMENT_BORN_STALE, (), None),
    ("fx-two-active-packages-owner-a-v1", Cycle2FixtureKind.SHIPMENT_SETUP, Cycle2W12FixtureRecipe.TWO_ACTIVE_PACKAGES, (), Cycle2W12IntegrityVector.TWO_ACTIVE_PACKAGES),
)

_W12_FIXTURE_CATALOG = MappingProxyType(
    {
        fixture_ref: _fixture(
            index,
            fixture_ref,
            kind,
            recipe,
            prerequisites=prerequisites,
            integrity=integrity,
        )
        for index, (
            fixture_ref,
            kind,
            recipe,
            prerequisites,
            integrity,
        ) in enumerate(_W12_FIXTURE_ROWS, start=1)
    }
)


def _fault(
    fault_ref: str,
    *directives: Cycle2FaultDirective,
) -> Cycle2ExecutionFaultPlanV1:
    return Cycle2ExecutionFaultPlanV1(
        fault_ref=fault_ref,
        directives=tuple(directives),
    )


def _failure_directive(
    attempt_no: int,
    error_code: str,
) -> Cycle2FaultDirective:
    return Cycle2FaultDirective(
        canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
        attempt_no=attempt_no,
        boundary=Cycle2FaultBoundary.BEFORE_DISPATCH,
        kind=Cycle2FaultDirectiveKind.SYSTEM_FAILURE,
        error_code=error_code,
        retryable=(
            error_code
            == GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value
        ),
    )


_TRANSIENT = GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value
_INTEGRITY = GetShipmentFailureCode.SHIPMENT_SOURCE_INTEGRITY.value
_W12_FAULT_CATALOG = MappingProxyType(
    {
        "fault:get-shipment:transient-once-v1": _fault(
            "fault:get-shipment:transient-once-v1",
            _failure_directive(1, _TRANSIENT),
        ),
        "fault:get-shipment:transient-always-v1": _fault(
            "fault:get-shipment:transient-always-v1",
            _failure_directive(1, _TRANSIENT),
            _failure_directive(2, _TRANSIENT),
        ),
        "fault:get-shipment:source-integrity-v1": _fault(
            "fault:get-shipment:source-integrity-v1",
            _failure_directive(1, _INTEGRITY),
        ),
        "fault:get-shipment:timeout-after-dispatch-once-v1": _fault(
            "fault:get-shipment:timeout-after-dispatch-once-v1",
            Cycle2FaultDirective(
                canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                attempt_no=1,
                boundary=Cycle2FaultBoundary.AFTER_DISPATCH,
                kind=Cycle2FaultDirectiveKind.TIMEOUT,
                error_code="TOOL_CALL_TIMEOUT",
                retryable=True,
            ),
        ),
        "fault:get-shipment:restart-after-retry-finalize-v1": _fault(
            "fault:get-shipment:restart-after-retry-finalize-v1",
            Cycle2FaultDirective(
                canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                attempt_no=1,
                boundary=Cycle2FaultBoundary.AFTER_RETRY_FINALIZE,
                kind=Cycle2FaultDirectiveKind.PROCESS_RESTART,
                restart_kind=Cycle2RestartKind.RETRY_RECOVERY,
            ),
        ),
        "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1": _fault(
            "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1",
            Cycle2FaultDirective(
                canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                attempt_no=1,
                boundary=Cycle2FaultBoundary.AFTER_RETRY_FINALIZE,
                kind=Cycle2FaultDirectiveKind.PROCESS_RESTART,
                restart_kind=Cycle2RestartKind.RETRY_STATE_INVALIDATED,
            ),
        ),
        "fault:get-shipment:restart-with-unfinished-attempt-v1": _fault(
            "fault:get-shipment:restart-with-unfinished-attempt-v1",
            Cycle2FaultDirective(
                canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                attempt_no=1,
                boundary=Cycle2FaultBoundary.AFTER_ATTEMPT_START,
                kind=Cycle2FaultDirectiveKind.PROCESS_RESTART,
                restart_kind=Cycle2RestartKind.UNFINISHED_ATTEMPT,
            ),
        ),
    }
)


def cycle2_w12_fixture_catalog() -> Mapping[
    str,
    Cycle2W12FixtureDefinitionV1,
]:
    return _W12_FIXTURE_CATALOG


def cycle2_w12_fault_catalog() -> Mapping[str, Cycle2ExecutionFaultPlanV1]:
    return _W12_FAULT_CATALOG


def _foreign_order() -> MockOrderSeedV1:
    return MockOrderSeedV1(
        owner_customer_id="customer-B",
        order_id="O-9001",
        order_payload=OrderSummaryProjection(
            order_number="O-9001",
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at=datetime(2026, 7, 25, 11, 0, tzinfo=UTC),
            status_updated_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        ),
    )


def _foreign_search(order: MockOrderSeedV1) -> MockOrderSearchDocumentSeedV1:
    return MockOrderSearchDocumentSeedV1(
        owner_customer_id="customer-B",
        order_id=order.order_id,
        line_ordinal=1,
        ordered_at=order.order_payload.ordered_at,
        order_number=order.order_id,
        status=order.order_payload.status,
        product_name="轻量跑鞋",
        quantity=1,
        product_category="鞋",
        search_aliases=("跑鞋", "鞋"),
    )


def _shipment_payload(
    fixture_ref: str,
) -> tuple[MockShipmentSeedV1, ...]:
    payloads: dict[str, tuple[dict[str, object], ...]] = {
        "fx-shipment-refresh-stalled-owner-a-v1": (dict(_shipment(stalled=True).shipment_payload),),
        "fx-shipment-current-owner-a-v1": (dict(_shipment(stalled=False).shipment_payload),),
        "fx-shipment-missing-promise-owner-a-v1": ({
            "shipment_status": "IN_TRANSIT",
            "latest_event_code": "IN_TRANSIT",
            "latest_event_at": "2026-07-31T09:00:00Z",
            "promised_delivery_at": None,
            "delivered_at": None,
            "observed_at": "2026-07-31T11:59:00Z",
        },),
        "fx-shipment-delayed-boundary-owner-a-v1": ({
            "shipment_status": "IN_TRANSIT",
            "latest_event_code": "IN_TRANSIT",
            "latest_event_at": "2026-07-27T00:00:00Z",
            "promised_delivery_at": "2026-07-31T11:59:59.999999Z",
            "delivered_at": None,
            "observed_at": "2026-07-31T11:59:00Z",
        },),
        "fx-shipment-delivered-owner-a-v1": ({
            "shipment_status": "DELIVERED",
            "latest_event_code": "DELIVERED",
            "latest_event_at": "2026-07-31T11:00:00Z",
            "promised_delivery_at": "2026-08-02T18:00:00Z",
            "delivered_at": "2026-07-31T11:00:00Z",
            "observed_at": "2026-07-31T11:59:00Z",
        },),
        "fx-shipment-refresh-born-stale-owner-a-v1": ({
            "shipment_status": "IN_TRANSIT",
            "latest_event_code": "IN_TRANSIT",
            "latest_event_at": "2026-07-31T10:00:00Z",
            "promised_delivery_at": "2026-08-02T18:00:00Z",
            "delivered_at": None,
            "observed_at": "2026-07-31T11:54:59Z",
        },),
        "fx-two-active-packages-owner-a-v1": (
            dict(_shipment(stalled=False).shipment_payload),
            dict(_shipment(stalled=True).shipment_payload),
        ),
        "fx-dynamic-tool-pair-owner-a-v1": (dict(_shipment(stalled=False).shipment_payload),),
    }
    rows = payloads.get(fixture_ref, ())
    return tuple(
        MockShipmentSeedV1(
            owner_customer_id=_OWNER_A,
            order_id="O-1001",
            package_id=f"PKG-{1001 + index}",
            shipment_payload=payload,
        )
        for index, payload in enumerate(rows)
    )


def _owner_order_ref(customer_id: str, order_id: str) -> str:
    return (
        "mock-owner-order-ref.p0.v1:sha256:"
        + _canonical_sha256(
            {
                "ref_schema": "mock-owner-order-ref.p0.v1",
                "owner_customer_id": customer_id,
                "order_id": order_id,
            }
        )
    )


def _runtime_record(
    fixture_ref: str,
    role: str,
    code: P0RecordCode,
    record: Cycle2CanonicalRuntimeRecord,
) -> Cycle2RuntimeBaseRecordV1:
    return Cycle2RuntimeBaseRecordV1(
        fixture_ref=fixture_ref,
        record_role=role,
        record_code=code,
        source_record=record,
    )


def _candidate_for_order(
    order: MockOrderSeedV1,
    *,
    owner_ref: str | None = None,
) -> OrderCandidate:
    line = order.order_payload.line_items[0]
    matched = (
        MatchedOrderLine(
            line_ordinal=1,
            product_name=line.product_name,
            quantity=line.quantity,
            product_category="鞋",
            normalized_search_aliases=("跑鞋", "鞋"),
        ),
    )
    summary = build_order_candidate_public_summary(
        order_number=order.order_id,
        ordered_at=order.order_payload.ordered_at,
        status=order.order_payload.status,
        matched_lines=matched,
    )
    version = compute_order_candidate_source_version(
        owner_customer_id=order.owner_customer_id,
        order_id=order.order_id,
        ordered_at=order.order_payload.ordered_at,
        status=order.order_payload.status,
        matched_lines=matched,
        public_summary=summary,
    )
    return OrderCandidate(
        owner_scoped_order_ref=(
            owner_ref
            if owner_ref is not None
            else _owner_order_ref(order.owner_customer_id, order.order_id)
        ),
        order_number=order.order_id,
        ordered_at=order.order_payload.ordered_at,
        status=order.order_payload.status,
        matched_lines=matched,
        public_summary=summary,
        candidate_source_version=version,
    )


def _search_graph(
    fixture_ref: str,
    *,
    candidates: tuple[OrderCandidate, ...],
    recorded_at: datetime,
    current_task_version: int = 2,
    current_status: TaskStatus = TaskStatus.WAITING_USER,
    source_suffix: str = "search",
    unique_target: bool = False,
) -> tuple[Cycle2RuntimeBaseRecordV1, ...]:
    candidates = sort_order_candidates(candidates)
    conversation_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "conversation.current"
    )
    task_id = deterministic_cycle2_setup_uuid(fixture_ref, "task.current")
    unit_id = deterministic_cycle2_setup_uuid(fixture_ref, "request_unit.current")
    message_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"message.historical_user.{source_suffix}"
    )
    binding_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "binding.product_description"
    )
    observation_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"observation.search.{source_suffix}"
    )
    candidate_set_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"candidate_set.{source_suffix}"
    )
    run_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"supporting_run.{source_suffix}"
    )
    tool_call_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"supporting_tool.{source_suffix}"
    )
    manifest_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"context_manifest.{source_suffix}"
    )
    model_call_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"model_call.{source_suffix}"
    )
    started_at = recorded_at - timedelta(minutes=1)
    message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=message_id,
        conversation_id=conversation_id,
        direction=MessageDirection.USER,
        content="帮我查一下最近买的那双鞋。",
        received_at=started_at,
    )
    binding = InputBindingV2(
        binding_id=binding_id,
        name="product_description",
        normalized_value="跑鞋",
        authority=InputAuthority.USER_CLAIM,
        source_refs=(message_id,),
        validation_status=InputValidationStatus.ACCEPTED,
        confirmed_by_user=True,
        created_at=started_at,
        updated_at=started_at,
    )
    order_message = None
    order_binding = None
    if unique_target:
        order_message = MessageRecord(
            schema_version="message_record.p0.v1",
            message_id=deterministic_cycle2_setup_uuid(
                fixture_ref, "message.historical_user.order_id"
            ),
            conversation_id=conversation_id,
            direction=MessageDirection.USER,
            content="我要查询订单 O-1001。",
            received_at=started_at + timedelta(microseconds=1),
        )
        order_binding = InputBindingV2(
            binding_id=deterministic_cycle2_setup_uuid(
                fixture_ref, "binding.order_id"
            ),
            name="order_id",
            normalized_value="O-1001",
            authority=InputAuthority.USER_CLAIM,
            source_refs=(order_message.message_id,),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=order_message.received_at,
            updated_at=order_message.received_at,
        )
    candidate_refs = tuple(
        deterministic_cycle2_setup_uuid(
            fixture_ref,
            f"candidate.{source_suffix}.{index}",
        )
        for index in range(1, len(candidates) + 1)
    )
    source_version = compute_order_search_snapshot_source_version(
        query=build_search_orders_query(
            customer_id=_OWNER_A,
            product_description="跑鞋",
            trusted_now=started_at,
        ),
        ordered_candidates=candidates,
        truncated=False,
    )
    observation = SearchOrdersObservation(
        observation_id=observation_id,
        private_owner_scope=_OWNER_A,
        source_tool="search_orders",
        source_tool_call_id=tool_call_id,
        source_resource_ref=f"orders:{_OWNER_A}:window:{source_suffix}",
        source_version=source_version,
        candidate_target_bindings=tuple(
            SearchObservationCandidateTargetBinding(
                observation_candidate_ref=candidate_ref,
                owner_scoped_order_ref=candidate.owner_scoped_order_ref,
                candidate_source_version=candidate.candidate_source_version,
            )
            for candidate_ref, candidate in zip(
                candidate_refs, candidates, strict=True
            )
        ),
        normalized_type="ORDER_SEARCH_CANDIDATES",
        normalized_value=SearchOrdersObservationValue(
            ordered_candidates=tuple(
                SearchOrdersObservationCandidate(
                    observation_candidate_ref=candidate_ref,
                    candidate_source_version=candidate.candidate_source_version,
                    public_summary=candidate.public_summary,
                )
                for candidate_ref, candidate in zip(
                    candidate_refs, candidates, strict=True
                )
            ),
            truncated=False,
        ),
        observed_at=recorded_at,
        recorded_at=recorded_at,
        valid_until=recorded_at + timedelta(minutes=15),
    )
    outcome = (
        OrderCandidateSetOutcome.UNIQUE
        if unique_target
        else OrderCandidateSetOutcome.MULTIPLE
    )
    entries = tuple(
        OrderCandidateSetEntry(
            ordinal=index,
            observation_candidate_ref=candidate_ref,
            candidate_source_version=candidate.candidate_source_version,
        )
        for index, (candidate_ref, candidate) in enumerate(
            zip(candidate_refs, candidates, strict=True), start=1
        )
    )
    set_fields = {
        "candidate_set_id": candidate_set_id,
        "private_owner_scope_ref": _OWNER_A,
        "conversation_id": conversation_id,
        "task_id": task_id,
        "request_unit_id": unit_id,
        "outcome": outcome,
        "base_task_state_version": 1,
        "result_task_state_version": 2,
        "selection_expected_task_state_version": None if unique_target else 2,
        "query_binding_refs": (binding_id,),
        "source_tool_call_id": tool_call_id,
        "search_observation_ref": observation_id,
        "search_observation_record_schema_version": observation.record_schema_version,
        "search_observation_source_version": source_version,
        "ordered_candidates": entries,
        "created_at": recorded_at,
        "valid_until": recorded_at + timedelta(minutes=15),
        "supersedes_candidate_set_ref": None,
    }
    candidate_set = OrderCandidateSetRecord(
        **set_fields,
        candidate_set_version=compute_order_candidate_set_version(**set_fields),
    )
    task = TaskRecord(
        task_id=task_id,
        owner_customer_id=_OWNER_A,
        status=current_status,
        state_version=current_task_version,
        created_at=started_at,
        updated_at=recorded_at,
    )
    unit = RequestUnitRecord(
        request_unit_id=unit_id,
        task_id=task_id,
        goal_text="查询最近购买的跑鞋订单",
        goal_source_refs=(message_id,),
        input_binding_refs=(
            (binding_id,)
            if order_binding is None
            else (binding_id, order_binding.binding_id)
        ),
        open_questions=("请选择候选订单序号。",) if current_status is TaskStatus.WAITING_USER else (),
        observation_refs=(observation_id,),
        status=current_status,
        state_version=current_task_version,
        created_at=started_at,
        updated_at=recorded_at,
    )
    run = AgentRunRecordV2(
        run_id=run_id,
        conversation_id=conversation_id,
        status=AgentRunStatusV2.COMPLETED,
        provider_lane="scripted-cycle2",
        started_at=started_at,
        completed_at=recorded_at,
        stop_reason=(
            StopReasonV2.GOAL_COMPLETED
            if unique_target
            else StopReasonV2.CANDIDATE_CLARIFICATION_REQUIRED
        ),
    )
    attempt = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=started_at,
        finished_at=recorded_at,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    snapshot = build_cycle2_registry_snapshot()
    gate_id = deterministic_cycle2_setup_uuid(
        fixture_ref, f"gate.{source_suffix}"
    )
    gate = GateDecisionV2(
        gate_decision_id=gate_id,
        model_call_id=model_call_id,
        context_manifest_id=manifest_id,
        provider_tool_call_id=f"w12-{source_suffix}",
        requested_provider_tool_name=Cycle2ToolName.SEARCH_ORDERS.value,
        resolved_canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
        snapshot_match=True,
        registration_valid=True,
        schema_valid=True,
        trusted_field_valid=True,
        argument_binding_valid=True,
        argument_binding_refs=(binding_id,),
        budget_valid=True,
        progress_valid=True,
        proposed_base_task_state_version=1,
        validated_task_state_version=1,
        state_version_valid=True,
        action_boundary_valid=True,
        decision=GateDecisionValue.ACCEPT,
        decided_at=started_at,
        verified_target_ref=None,
        validated_arguments={"product_description": "跑鞋"},
    )
    tool = ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=run_id,
        task_id=task_id,
        request_unit_id=unit_id,
        model_call_id=model_call_id,
        context_manifest_id=manifest_id,
        gate_decision_id=gate_id,
        canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
        tool_registry_version=snapshot.tool_registry_version,
        private_owner_scope_ref=_OWNER_A,
        validated_task_state_version=1,
        argument_binding_refs=(binding_id,),
        verified_target_ref=None,
        effect=ToolEffect.READ,
        attempt_count=1,
        attempts=(attempt,),
        status=ToolCallStatus.SUCCEEDED,
        started_at=started_at,
        finished_at=recorded_at,
        result_ref=deterministic_cycle2_setup_uuid(
            fixture_ref, f"result.{source_suffix}"
        ),
    )
    manifest = ContextManifest(
        context_manifest_id=manifest_id,
        run_id=run_id,
        model_call_id=model_call_id,
        tool_registry_version=snapshot.tool_registry_version,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        selected_message_refs=(message_id,),
        task_state_ref_and_version=TaskStateRefAndVersion(
            task_id=task_id,
            state_version=1,
        ),
        redaction_policy_version="redaction.p0.v1",
        token_counts=TokenCounts(),
        assembled_at=started_at,
    )
    records = [
        _runtime_record(fixture_ref, "conversation.current", P0RecordCode.CONVERSATION_RECORD, ConversationRecord(schema_version="conversation_record.p0.v1", conversation_id=conversation_id, owner_customer_id=_OWNER_A, created_at=started_at)),
        _runtime_record(fixture_ref, f"message.historical_user.{source_suffix}", P0RecordCode.MESSAGE_RECORD, message),
        _runtime_record(fixture_ref, "task.current", P0RecordCode.TASK_RECORD, task),
        _runtime_record(fixture_ref, "request_unit.current", P0RecordCode.REQUEST_UNIT_RECORD, unit),
        _runtime_record(fixture_ref, "conversation_task_link.current", P0RecordCode.CONVERSATION_TASK_LINK_RECORD, ConversationTaskLinkRecord(schema_version="conversation_task_link_record.p0.v1", conversation_id=conversation_id, task_id=task_id, link_reason="cycle2-w12-fixture", linked_at=started_at)),
        _runtime_record(fixture_ref, "binding.product_description", P0RecordCode.INPUT_BINDING_RECORD, binding),
        _runtime_record(fixture_ref, f"observation.search.{source_suffix}", P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD, observation),
        _runtime_record(fixture_ref, f"candidate_set.{source_suffix}", P0RecordCode.ORDER_CANDIDATE_SET_RECORD, candidate_set),
        _runtime_record(fixture_ref, f"supporting_run.{source_suffix}", P0RecordCode.AGENT_RUN_RECORD, run),
        _runtime_record(fixture_ref, f"supporting_link.{source_suffix}", P0RecordCode.RUN_TASK_LINK_RECORD, RunTaskLinkRecordV2(run_id=run_id, task_id=task_id, base_task_state_version=1, result_task_state_version=2)),
        _runtime_record(fixture_ref, f"supporting_gate.{source_suffix}", P0RecordCode.GATE_DECISION_RECORD, gate),
        _runtime_record(fixture_ref, f"supporting_tool.{source_suffix}", P0RecordCode.TOOL_CALL_RECORD, tool),
        _runtime_record(fixture_ref, f"context_manifest.{source_suffix}", P0RecordCode.CONTEXT_MANIFEST_RECORD, manifest),
        _runtime_record(fixture_ref, "toolset_artifact", P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT, snapshot.artifact()),
    ]
    if unique_target:
        assert order_message is not None and order_binding is not None
        records.extend(
            (
                _runtime_record(
                    fixture_ref,
                    "message.historical_user.order_id",
                    P0RecordCode.MESSAGE_RECORD,
                    order_message,
                ),
                _runtime_record(
                    fixture_ref,
                    "binding.order_id",
                    P0RecordCode.INPUT_BINDING_RECORD,
                    order_binding,
                ),
            )
        )
        candidate = candidates[0]
        auto_target = OrderCandidateAutoTargetRecord(
            verified_target_ref=deterministic_cycle2_setup_uuid(
                fixture_ref, "auto_target.current"
            ),
            private_owner_scope_ref=_OWNER_A,
            conversation_id=conversation_id,
            task_id=task_id,
            request_unit_id=unit_id,
            query_input_binding_ref=binding_id,
            candidate_set_ref=candidate_set_id,
            candidate_set_version=candidate_set.candidate_set_version,
            source_tool_call_id=tool_call_id,
            search_observation_ref=observation_id,
            search_observation_record_schema_version=observation.record_schema_version,
            search_observation_source_version=source_version,
            observation_candidate_ref=candidate_refs[0],
            candidate_source_version=candidate.candidate_source_version,
            owner_scoped_order_target_ref=candidate.owner_scoped_order_ref,
            order_id=candidate.order_number,
            base_task_state_version=1,
            result_task_state_version=2,
            verified_at=recorded_at,
        )
        records.append(_runtime_record(fixture_ref, "auto_target.current", P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD, auto_target))
    return tuple(records)


def _replace_runtime_record(
    records: tuple[Cycle2RuntimeBaseRecordV1, ...],
    *,
    role: str,
    replacement: Cycle2RuntimeBaseRecordV1,
) -> tuple[Cycle2RuntimeBaseRecordV1, ...]:
    matches = tuple(index for index, item in enumerate(records) if item.record_role == role)
    if len(matches) != 1:
        raise Cycle2SeedError("runtime overlay pre-image role is not unique")
    mutable = list(records)
    mutable[matches[0]] = replacement
    return tuple(mutable)


def _add_stale_shipment_observation_graph(
    fixture_ref: str,
    records: tuple[Cycle2RuntimeBaseRecordV1, ...],
) -> tuple[Cycle2RuntimeBaseRecordV1, ...]:
    task = next(
        item.source_record for item in records if item.record_role == "task.current"
    )
    unit = next(
        item.source_record
        for item in records
        if item.record_role == "request_unit.current"
    )
    target = next(
        item.source_record
        for item in records
        if type(item.source_record) is OrderCandidateAutoTargetRecord
    )
    binding = next(
        item.source_record
        for item in records
        if type(item.source_record) is InputBindingV2
        and item.source_record.binding_id == target.query_input_binding_ref
    )
    assert type(task) is TaskRecord and type(unit) is RequestUnitRecord
    observed_at = datetime(2026, 7, 31, 11, 40, tzinfo=UTC)
    recorded_at = observed_at + timedelta(minutes=1)
    summary = ShipmentSummaryProjection(
        shipment_status=ShipmentStatus.IN_TRANSIT,
        latest_event_code=ShipmentEventCode.IN_TRANSIT,
        latest_event_at=datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
        promised_delivery_at=datetime(2026, 8, 2, 18, 0, tzinfo=UTC),
    )
    source_resource_ref = "PKG-1001"
    source_version = compute_shipment_source_version(
        owner_customer_id=_OWNER_A,
        order_id=target.order_id,
        source_resource_ref=source_resource_ref,
        observed_at=observed_at,
        safe_projection=summary,
    )
    observation_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "observation.shipment.stale"
    )
    run_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "supporting_run.shipment"
    )
    tool_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "supporting_tool.shipment"
    )
    result_ref = deterministic_cycle2_setup_uuid(fixture_ref, "result.shipment")
    manifest_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "context_manifest.shipment"
    )
    model_call_id = deterministic_cycle2_setup_uuid(
        fixture_ref, "model_call.shipment"
    )
    gate_id = deterministic_cycle2_setup_uuid(fixture_ref, "gate.shipment")
    snapshot = build_cycle2_registry_snapshot()
    attempt = ToolAttemptRecordV2(
        tool_call_id=tool_id,
        attempt_no=1,
        started_at=observed_at,
        finished_at=recorded_at,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    observation = ShipmentObservation(
        observation_id=observation_id,
        private_owner_scope=_OWNER_A,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        verified_order_target_ref=str(target.verified_target_ref),
        source_tool="get_shipment",
        source_tool_call_id=tool_id,
        source_resource_ref=source_resource_ref,
        source_version=source_version,
        normalized_type="SHIPMENT_SUMMARY",
        normalized_value=summary,
        observed_at=observed_at,
        recorded_at=recorded_at,
        valid_until=observed_at + timedelta(minutes=5),
        raw_result_ref=str(result_ref),
    )
    records = _replace_runtime_record(
        records,
        role="task.current",
        replacement=_runtime_record(
            fixture_ref,
            "task.current",
            P0RecordCode.TASK_RECORD,
            task.model_copy(update={"state_version": 3, "updated_at": recorded_at}),
        ),
    )
    records = _replace_runtime_record(
        records,
        role="request_unit.current",
        replacement=_runtime_record(
            fixture_ref,
            "request_unit.current",
            P0RecordCode.REQUEST_UNIT_RECORD,
            unit.model_copy(
                update={
                    "state_version": 3,
                    "observation_refs": (*unit.observation_refs, observation_id),
                    "updated_at": recorded_at,
                }
            ),
        ),
    )
    return records + (
        _runtime_record(fixture_ref, "observation.shipment.stale", P0RecordCode.SHIPMENT_OBSERVATION_RECORD, observation),
        _runtime_record(fixture_ref, "supporting_run.shipment", P0RecordCode.AGENT_RUN_RECORD, AgentRunRecordV2(run_id=run_id, conversation_id=target.conversation_id, status=AgentRunStatusV2.COMPLETED, provider_lane="scripted-cycle2", started_at=observed_at, completed_at=recorded_at, stop_reason=StopReasonV2.GOAL_COMPLETED)),
        _runtime_record(fixture_ref, "supporting_link.shipment", P0RecordCode.RUN_TASK_LINK_RECORD, RunTaskLinkRecordV2(run_id=run_id, task_id=task.task_id, base_task_state_version=2, result_task_state_version=3)),
        _runtime_record(fixture_ref, "supporting_gate.shipment", P0RecordCode.GATE_DECISION_RECORD, GateDecisionV2(gate_decision_id=gate_id, model_call_id=model_call_id, context_manifest_id=manifest_id, provider_tool_call_id="w12-stale-get-shipment", requested_provider_tool_name=Cycle2ToolName.GET_SHIPMENT.value, resolved_canonical_tool_name=Cycle2ToolName.GET_SHIPMENT, snapshot_match=True, registration_valid=True, schema_valid=True, trusted_field_valid=True, argument_binding_valid=True, argument_binding_refs=(binding.binding_id,), budget_valid=True, progress_valid=True, proposed_base_task_state_version=2, validated_task_state_version=2, state_version_valid=True, action_boundary_valid=True, decision=GateDecisionValue.ACCEPT, decided_at=observed_at, verified_target_ref=target.verified_target_ref, validated_arguments={"order_id": target.order_id})),
        _runtime_record(fixture_ref, "supporting_tool.shipment", P0RecordCode.TOOL_CALL_RECORD, ToolCallRecordV2(tool_call_id=tool_id, run_id=run_id, task_id=task.task_id, request_unit_id=unit.request_unit_id, model_call_id=model_call_id, context_manifest_id=manifest_id, gate_decision_id=gate_id, canonical_tool_name=Cycle2ToolName.GET_SHIPMENT, tool_registry_version=snapshot.tool_registry_version, private_owner_scope_ref=_OWNER_A, validated_task_state_version=2, argument_binding_refs=(binding.binding_id,), verified_target_ref=target.verified_target_ref, effect=ToolEffect.READ, attempt_count=1, attempts=(attempt,), status=ToolCallStatus.SUCCEEDED, started_at=observed_at, finished_at=recorded_at, result_ref=result_ref)),
        _runtime_record(fixture_ref, "context_manifest.shipment", P0RecordCode.CONTEXT_MANIFEST_RECORD, ContextManifest(context_manifest_id=manifest_id, run_id=run_id, model_call_id=model_call_id, tool_registry_version=snapshot.tool_registry_version, model_visible_toolset_hash=snapshot.model_visible_toolset_hash, selected_message_refs=binding.source_refs, task_state_ref_and_version=TaskStateRefAndVersion(task_id=task.task_id, state_version=2), redaction_policy_version="redaction.p0.v1", token_counts=TokenCounts(), assembled_at=observed_at)),
    )


def _candidate_runtime_graph(
    definition: Cycle2W12FixtureDefinitionV1,
) -> tuple[Cycle2RuntimeBaseRecordV1, ...]:
    ref = definition.fixture_ref
    recipe = definition.recipe
    candidate_a = _candidate_for_order(_ORDER_A1001)
    candidate_b = _candidate_for_order(_ORDER_A1002)
    if recipe is Cycle2W12FixtureRecipe.CANDIDATE_OWNER_MISMATCH:
        candidate_a = _candidate_for_order(
            _ORDER_A1001,
            owner_ref=_owner_order_ref("customer-B", "O-9001"),
        )
    if recipe in {
        Cycle2W12FixtureRecipe.VERIFIED_ORDER_TARGET,
        Cycle2W12FixtureRecipe.STALE_SHIPMENT_OBSERVATION,
        Cycle2W12FixtureRecipe.RETRY_SCHEDULED_OBSOLETE_RUN,
    }:
        records = _search_graph(
            ref,
            candidates=(candidate_a,),
            recorded_at=datetime(2026, 7, 31, 11, 30, tzinfo=UTC),
            current_status=TaskStatus.ACTIVE,
            unique_target=True,
        )
    elif recipe is Cycle2W12FixtureRecipe.CANDIDATE_OTHER_TASK:
        records = _search_graph(
            ref,
            candidates=(candidate_a, candidate_b),
            recorded_at=datetime(2026, 7, 31, 11, 50, tzinfo=UTC),
        )
        current_task_id = deterministic_cycle2_setup_uuid(ref, "task.session_current")
        current_unit_id = deterministic_cycle2_setup_uuid(ref, "request_unit.session_current")
        conversation = next(item.source_record for item in records if item.record_role == "conversation.current")
        message = next(item.source_record for item in records if item.record_role.startswith("message.historical_user"))
        binding = next(item.source_record for item in records if item.record_role == "binding.product_description")
        assert type(conversation) is ConversationRecord and type(message) is MessageRecord and type(binding) is InputBindingV2
        current_binding = binding.model_copy(update={"binding_id": deterministic_cycle2_setup_uuid(ref, "binding.session_current")})
        records = tuple(
            item
            for item in records
            if item.record_role != "conversation_task_link.current"
        ) + (
            _runtime_record(ref, "task.session_current", P0RecordCode.TASK_RECORD, TaskRecord(task_id=current_task_id, owner_customer_id=_OWNER_A, status=TaskStatus.WAITING_USER, state_version=2, created_at=message.received_at, updated_at=datetime(2026, 7, 31, 11, 50, tzinfo=UTC))),
            _runtime_record(ref, "request_unit.session_current", P0RecordCode.REQUEST_UNIT_RECORD, RequestUnitRecord(request_unit_id=current_unit_id, task_id=current_task_id, goal_text="选择当前会话订单", goal_source_refs=(message.message_id,), input_binding_refs=(current_binding.binding_id,), open_questions=("请选择候选订单序号。",), status=TaskStatus.WAITING_USER, state_version=2, created_at=message.received_at, updated_at=datetime(2026, 7, 31, 11, 50, tzinfo=UTC))),
            _runtime_record(ref, "binding.session_current", P0RecordCode.INPUT_BINDING_RECORD, current_binding),
            _runtime_record(ref, "conversation_task_link.current", P0RecordCode.CONVERSATION_TASK_LINK_RECORD, ConversationTaskLinkRecord(schema_version="conversation_task_link_record.p0.v1", conversation_id=conversation.conversation_id, task_id=current_task_id, link_reason="cycle2-w12-current-task", linked_at=message.received_at)),
        )
    else:
        recorded = (
            datetime(2026, 7, 31, 11, 40, tzinfo=UTC)
            if recipe is Cycle2W12FixtureRecipe.CANDIDATE_EXPIRED
            else datetime(2026, 7, 31, 11, 50, tzinfo=UTC)
        )
        records = _search_graph(
            ref,
            candidates=(candidate_a, candidate_b),
            recorded_at=recorded,
        )
    if recipe is Cycle2W12FixtureRecipe.STALE_SHIPMENT_OBSERVATION:
        records = _add_stale_shipment_observation_graph(ref, records)
    if recipe is Cycle2W12FixtureRecipe.CANDIDATE_SUPERSEDED:
        task_item = next(item for item in records if item.record_role == "task.current")
        unit_item = next(item for item in records if item.record_role == "request_unit.current")
        task = task_item.source_record
        unit = unit_item.source_record
        candidate_item = next(item for item in records if item.record_role == "candidate_set.search")
        candidate_set = candidate_item.source_record
        assert type(task) is TaskRecord and type(unit) is RequestUnitRecord and type(candidate_set) is OrderCandidateSetRecord
        records = _replace_runtime_record(records, role="task.current", replacement=_runtime_record(ref, "task.current", P0RecordCode.TASK_RECORD, task.model_copy(update={"state_version": 4})))
        records = _replace_runtime_record(records, role="request_unit.current", replacement=_runtime_record(ref, "request_unit.current", P0RecordCode.REQUEST_UNIT_RECORD, unit.model_copy(update={"state_version": 4, "open_questions": ()})))
        successor_fields = {
            **{field: getattr(candidate_set, field) for field in OrderCandidateSetRecord.model_fields if field != "candidate_set_version"},
            "candidate_set_id": deterministic_cycle2_setup_uuid(ref, "candidate_set.successor"),
            "base_task_state_version": 2,
            "result_task_state_version": 3,
            "selection_expected_task_state_version": 3,
            "supersedes_candidate_set_ref": candidate_set.candidate_set_id,
            "created_at": candidate_set.created_at + timedelta(microseconds=1),
            "valid_until": candidate_set.valid_until + timedelta(microseconds=1),
        }
        successor = OrderCandidateSetRecord(**successor_fields, candidate_set_version=compute_order_candidate_set_version(**successor_fields))
        records += (_runtime_record(ref, "candidate_set.successor", P0RecordCode.ORDER_CANDIDATE_SET_RECORD, successor),)
    if recipe is Cycle2W12FixtureRecipe.CANDIDATE_CARDINALITY:
        candidate_item = next(item for item in records if item.record_role == "candidate_set.search")
        candidate_set = candidate_item.source_record
        assert type(candidate_set) is OrderCandidateSetRecord
        duplicate_fields = {
            **{field: getattr(candidate_set, field) for field in OrderCandidateSetRecord.model_fields if field != "candidate_set_version"},
            "candidate_set_id": deterministic_cycle2_setup_uuid(ref, "candidate_set.second_current"),
        }
        duplicate = OrderCandidateSetRecord(**duplicate_fields, candidate_set_version=compute_order_candidate_set_version(**duplicate_fields))
        records += (_runtime_record(ref, "candidate_set.second_current", P0RecordCode.ORDER_CANDIDATE_SET_RECORD, duplicate),)
    return records


def _runtime_setup(
    definitions: tuple[Cycle2W12FixtureDefinitionV1, ...],
    *,
    authenticated_user_message: str | None,
) -> Cycle2RuntimeSetupV1:
    runtime_recipes = {
        Cycle2W12FixtureRecipe.CANDIDATE_CURRENT,
        Cycle2W12FixtureRecipe.CANDIDATE_EXPIRED,
        Cycle2W12FixtureRecipe.CANDIDATE_OTHER_TASK,
        Cycle2W12FixtureRecipe.VERIFIED_ORDER_TARGET,
        Cycle2W12FixtureRecipe.STALE_SHIPMENT_OBSERVATION,
        Cycle2W12FixtureRecipe.CANDIDATE_OWNER_MISMATCH,
        Cycle2W12FixtureRecipe.CANDIDATE_SUPERSEDED,
        Cycle2W12FixtureRecipe.CANDIDATE_CARDINALITY,
        Cycle2W12FixtureRecipe.RETRY_SCHEDULED_OBSOLETE_RUN,
    }
    graph_definitions = tuple(
        definition for definition in definitions if definition.recipe in runtime_recipes
    )
    if len(graph_definitions) > 1:
        raise Cycle2SeedError("closed W12 setup selected multiple base runtime graphs")
    base_records = (
        ()
        if not graph_definitions
        else _candidate_runtime_graph(graph_definitions[0])
    )
    recovery_ref = None
    messages: tuple[MessageRecord, ...] = ()
    if graph_definitions and graph_definitions[0].recipe is Cycle2W12FixtureRecipe.RETRY_SCHEDULED_OBSOLETE_RUN:
        if type(authenticated_user_message) is not str or not authenticated_user_message:
            raise Cycle2SeedError("recovery root requires the authenticated single USER message")
        fixture_ref = graph_definitions[0].fixture_ref
        recovery_ref = deterministic_cycle2_setup_uuid(fixture_ref, "recovery_root.run")
        target = next(
            item.source_record
            for item in base_records
            if type(item.source_record) is OrderCandidateAutoTargetRecord
        )
        query_binding = next(
            item.source_record
            for item in base_records
            if item.record_role == "binding.product_description"
            and type(item.source_record) is InputBindingV2
        )
        old_order_binding = next(
            item.source_record
            for item in base_records
            if item.record_role == "binding.order_id"
            and type(item.source_record) is InputBindingV2
        )
        task = next(
            item.source_record
            for item in base_records
            if item.record_role == "task.current"
            and type(item.source_record) is TaskRecord
        )
        unit = next(
            item.source_record
            for item in base_records
            if item.record_role == "request_unit.current"
            and type(item.source_record) is RequestUnitRecord
        )
        if (
            task.state_version != 2
            or unit.state_version != 2
            or unit.input_binding_refs
            != (query_binding.binding_id, old_order_binding.binding_id)
            or target.query_input_binding_ref != query_binding.binding_id
        ):
            raise Cycle2SeedError("recovery pre-CAS v2 snapshot is not exact")
        root_started = datetime(2026, 7, 31, 11, 49, tzinfo=UTC)
        attempt_finished = root_started + timedelta(seconds=1)
        invalidated_at = datetime(2026, 7, 31, 11, 50, tzinfo=UTC)
        historical = MessageRecord(
            schema_version="message_record.p0.v1",
            message_id=deterministic_cycle2_setup_uuid(fixture_ref, "message.historical_user.recovery"),
            conversation_id=deterministic_cycle2_setup_uuid(fixture_ref, "conversation.current"),
            direction=MessageDirection.USER,
            content=authenticated_user_message,
            received_at=root_started,
        )
        fresh_order_binding = InputBindingV2(
            binding_id=deterministic_cycle2_setup_uuid(
                fixture_ref, "binding.order_id.recovery_root"
            ),
            name="order_id",
            normalized_value="O-1001",
            authority=InputAuthority.USER_CLAIM,
            source_refs=(historical.message_id,),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=root_started,
            updated_at=root_started,
            supersedes=old_order_binding.binding_id,
        )
        final_binding_refs = tuple(
            fresh_order_binding.binding_id
            if ref == old_order_binding.binding_id
            else ref
            for ref in unit.input_binding_refs
        )
        base_records = _replace_runtime_record(
            base_records,
            role="task.current",
            replacement=_runtime_record(
                fixture_ref,
                "task.current",
                P0RecordCode.TASK_RECORD,
                task.model_copy(
                    update={"state_version": 4, "updated_at": invalidated_at}
                ),
            ),
        )
        base_records = _replace_runtime_record(
            base_records,
            role="request_unit.current",
            replacement=_runtime_record(
                fixture_ref,
                "request_unit.current",
                P0RecordCode.REQUEST_UNIT_RECORD,
                unit.model_copy(
                    update={
                        "state_version": 4,
                        "updated_at": invalidated_at,
                        "input_binding_refs": final_binding_refs,
                    }
                ),
            ),
        )
        base_records += (
            _runtime_record(
                fixture_ref,
                "message.historical_user.recovery",
                P0RecordCode.MESSAGE_RECORD,
                historical,
            ),
            _runtime_record(
                fixture_ref,
                "binding.order_id.recovery_root",
                P0RecordCode.INPUT_BINDING_RECORD,
                fresh_order_binding,
            ),
        )
        root_manifest_id = deterministic_cycle2_setup_uuid(
            fixture_ref, "recovery_root.context_manifest"
        )
        root_model_call_id = deterministic_cycle2_setup_uuid(
            fixture_ref, "recovery_root.model_call"
        )
        root_gate_id = deterministic_cycle2_setup_uuid(
            fixture_ref, "recovery_root.gate"
        )
        root_tool_id = deterministic_cycle2_setup_uuid(
            fixture_ref, "recovery_root.tool_call"
        )
        root_attempt = ToolAttemptRecordV2(
            tool_call_id=root_tool_id,
            attempt_no=1,
            started_at=root_started,
            finished_at=attempt_finished,
            outcome=ToolResultOutcome.SYSTEM_FAILURE,
            failure_code=GetShipmentFailureCode.SHIPMENT_SERVICE_TRANSIENT.value,
            retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
        )
        snapshot = build_cycle2_registry_snapshot()
        recovery_records = (
            _runtime_record(
                fixture_ref,
                "recovery_root.run",
                P0RecordCode.AGENT_RUN_RECORD,
                AgentRunRecordV2(
                    run_id=recovery_ref,
                    conversation_id=historical.conversation_id,
                    status=AgentRunStatusV2.RUNNING,
                    provider_lane="scripted-cycle2",
                    started_at=root_started,
                ),
            ),
            _runtime_record(
                fixture_ref,
                "recovery_root.link",
                P0RecordCode.RUN_TASK_LINK_RECORD,
                RunTaskLinkRecordV2(
                    run_id=recovery_ref,
                    task_id=task.task_id,
                    base_task_state_version=2,
                    result_task_state_version=None,
                ),
            ),
            _runtime_record(
                fixture_ref,
                "recovery_root.context_manifest",
                P0RecordCode.CONTEXT_MANIFEST_RECORD,
                ContextManifest(
                    context_manifest_id=root_manifest_id,
                    run_id=recovery_ref,
                    model_call_id=root_model_call_id,
                    tool_registry_version=snapshot.tool_registry_version,
                    model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
                    selected_message_refs=(historical.message_id,),
                    task_state_ref_and_version=TaskStateRefAndVersion(
                        task_id=task.task_id,
                        state_version=3,
                    ),
                    redaction_policy_version="redaction.p0.v1",
                    token_counts=TokenCounts(),
                    assembled_at=root_started,
                ),
            ),
            _runtime_record(
                fixture_ref,
                "recovery_root.gate",
                P0RecordCode.GATE_DECISION_RECORD,
                GateDecisionV2(
                    gate_decision_id=root_gate_id,
                    model_call_id=root_model_call_id,
                    context_manifest_id=root_manifest_id,
                    provider_tool_call_id="w12-recovery-get-shipment",
                    requested_provider_tool_name=Cycle2ToolName.GET_SHIPMENT.value,
                    resolved_canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                    snapshot_match=True,
                    registration_valid=True,
                    schema_valid=True,
                    trusted_field_valid=True,
                    argument_binding_valid=True,
                    argument_binding_refs=(query_binding.binding_id,),
                    budget_valid=True,
                    progress_valid=True,
                    proposed_base_task_state_version=3,
                    validated_task_state_version=3,
                    state_version_valid=True,
                    action_boundary_valid=True,
                    decision=GateDecisionValue.ACCEPT,
                    decided_at=root_started,
                    verified_target_ref=target.verified_target_ref,
                    validated_arguments={"order_id": target.order_id},
                ),
            ),
            _runtime_record(
                fixture_ref,
                "recovery_root.tool_call",
                P0RecordCode.TOOL_CALL_RECORD,
                ToolCallRecordV2(
                    tool_call_id=root_tool_id,
                    run_id=recovery_ref,
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                    model_call_id=root_model_call_id,
                    context_manifest_id=root_manifest_id,
                    gate_decision_id=root_gate_id,
                    canonical_tool_name=Cycle2ToolName.GET_SHIPMENT,
                    tool_registry_version=snapshot.tool_registry_version,
                    private_owner_scope_ref=_OWNER_A,
                    validated_task_state_version=3,
                    argument_binding_refs=(query_binding.binding_id,),
                    verified_target_ref=target.verified_target_ref,
                    effect=ToolEffect.READ,
                    attempt_count=1,
                    attempts=(root_attempt,),
                    status=ToolCallStatus.RUNNING,
                    started_at=root_started,
                ),
            ),
            _runtime_record(
                fixture_ref,
                "recovery_root.trace.message_accepted",
                P0RecordCode.TRACE_EVENT_RECORD,
                TraceEventV2(
                    trace_event_id=deterministic_cycle2_setup_uuid(
                        fixture_ref, "recovery_root.trace.message_accepted"
                    ),
                    event_type=TraceEventType.MESSAGE_ACCEPTED,
                    occurred_at=root_started,
                    run_id=recovery_ref,
                    message_ref=historical.message_id,
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                ),
            ),
        )
        base_records += recovery_records
        messages = (historical,)
    elif authenticated_user_message is not None:
        raise Cycle2SeedError("ordinary setup cannot accept the evaluated message")
    overlays: tuple[Cycle2RuntimeOverlayV1, ...] = ()
    if any(definition.recipe is Cycle2W12FixtureRecipe.CORRECTED_NOT_RECEIVED for definition in definitions):
        if not graph_definitions or graph_definitions[0].recipe is not Cycle2W12FixtureRecipe.VERIFIED_ORDER_TARGET:
            raise Cycle2SeedError("correction overlay requires the verified target base graph")
        fixture_ref = graph_definitions[0].fixture_ref
        task_item = next(item for item in base_records if item.record_role == "task.current")
        unit_item = next(item for item in base_records if item.record_role == "request_unit.current")
        conversation = next(
            item.source_record
            for item in base_records
            if item.record_role == "conversation.current"
        )
        task = task_item.source_record
        unit = unit_item.source_record
        assert (
            type(conversation) is ConversationRecord
            and type(task) is TaskRecord
            and type(unit) is RequestUnitRecord
        )
        true_message = MessageRecord(
            schema_version="message_record.p0.v1",
            message_id=deterministic_cycle2_setup_uuid(
                fixture_ref,
                "message.historical_user.shipment_not_received.true",
            ),
            conversation_id=conversation.conversation_id,
            direction=MessageDirection.USER,
            content="订单 O-1001 显示已送达，但我没有收到。",
            received_at=task.updated_at,
        )
        true_binding = InputBindingV2(
            binding_id=deterministic_cycle2_setup_uuid(
                fixture_ref, "binding.shipment_not_received.true"
            ),
            name="shipment_not_received",
            normalized_value=True,
            authority=InputAuthority.USER_CLAIM,
            source_refs=(true_message.message_id,),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=true_message.received_at,
            updated_at=true_message.received_at,
        )
        base_task = task.model_copy(
            update={"state_version": 3, "updated_at": true_binding.updated_at}
        )
        base_unit = unit.model_copy(
            update={
                "state_version": 3,
                "updated_at": true_binding.updated_at,
                "input_binding_refs": (
                    *unit.input_binding_refs,
                    true_binding.binding_id,
                ),
            }
        )
        base_records = _replace_runtime_record(base_records, role="task.current", replacement=_runtime_record(fixture_ref, "task.current", P0RecordCode.TASK_RECORD, base_task))
        base_records = _replace_runtime_record(base_records, role="request_unit.current", replacement=_runtime_record(fixture_ref, "request_unit.current", P0RecordCode.REQUEST_UNIT_RECORD, base_unit))
        base_records += (
            _runtime_record(
                fixture_ref,
                "message.historical_user.shipment_not_received.true",
                P0RecordCode.MESSAGE_RECORD,
                true_message,
            ),
            _runtime_record(fixture_ref, "binding.shipment_not_received.true", P0RecordCode.INPUT_BINDING_RECORD, true_binding),
        )
        false_ref = "fx-corrected-not-received-claim-owner-a-v1"
        false_message = MessageRecord(
            schema_version="message_record.p0.v1",
            message_id=deterministic_cycle2_setup_uuid(
                false_ref,
                "message.historical_user.shipment_not_received.false",
            ),
            conversation_id=conversation.conversation_id,
            direction=MessageDirection.USER,
            content="更正：订单 O-1001 已经收到了。",
            received_at=true_binding.updated_at + timedelta(microseconds=1),
        )
        false_binding = InputBindingV2(
            binding_id=deterministic_cycle2_setup_uuid(
                false_ref, "binding.shipment_not_received.false"
            ),
            name="shipment_not_received",
            normalized_value=False,
            authority=InputAuthority.USER_CLAIM,
            source_refs=(false_message.message_id,),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=false_message.received_at,
            updated_at=false_message.received_at,
            supersedes=true_binding.binding_id,
        )
        final_binding_refs = tuple(
            false_binding.binding_id
            if ref == true_binding.binding_id
            else ref
            for ref in base_unit.input_binding_refs
        )
        overlays = (
            Cycle2RuntimeOverlayV1(
                fixture_ref=false_ref,
                prerequisite_fixture_ref=fixture_ref,
                expected_pre_images=(
                    next(item for item in base_records if item.record_role == "task.current"),
                    next(item for item in base_records if item.record_role == "request_unit.current"),
                ),
                next_records=(
                    _runtime_record(
                        false_ref,
                        "message.historical_user.shipment_not_received.false",
                        P0RecordCode.MESSAGE_RECORD,
                        false_message,
                    ),
                    _runtime_record(
                        false_ref,
                        "task.current",
                        P0RecordCode.TASK_RECORD,
                        base_task.model_copy(
                            update={
                                "state_version": 4,
                                "updated_at": false_binding.updated_at,
                            }
                        ),
                    ),
                    _runtime_record(
                        false_ref,
                        "request_unit.current",
                        P0RecordCode.REQUEST_UNIT_RECORD,
                        base_unit.model_copy(
                            update={
                                "state_version": 4,
                                "updated_at": false_binding.updated_at,
                                "input_binding_refs": final_binding_refs,
                            }
                        ),
                    ),
                    _runtime_record(
                        false_ref,
                        "binding.shipment_not_received.false",
                        P0RecordCode.INPUT_BINDING_RECORD,
                        false_binding,
                    ),
                ),
            ),
        )
    vectors = tuple(definition.integrity_vector for definition in definitions if definition.integrity_vector is not None)
    return Cycle2RuntimeSetupV1(base_records=base_records, overlays=overlays, historical_user_messages=messages, recovery_subject_run_id=recovery_ref, integrity_vectors=vectors)


def _business_rows(
    definitions: tuple[Cycle2W12FixtureDefinitionV1, ...],
) -> Cycle2BusinessSeedRowsV1:
    fixture_refs = {definition.fixture_ref for definition in definitions}
    orders: list[MockOrderSeedV1] = []
    searches: list[MockOrderSearchDocumentSeedV1] = []
    shipments: list[MockShipmentSeedV1] = []
    if fixture_refs.intersection(
        {
            "fx-search-unique-owner-a-with-foreign-decoy-v1",
            "fx-search-multiple-owner-a-v1",
            "fx-order-targets-owner-a-v1",
            "fx-dynamic-tool-pair-owner-a-v1",
            "fx-order-zero-active-package-owner-a-v1",
            "fx-two-active-packages-owner-a-v1",
            "fx-verified-order-target-o1001-owner-a-v1",
            "fx-stale-shipment-observation-owner-a-v1",
            "fx-retry-scheduled-obsolete-run-owner-a-v1",
        }
    ):
        orders.append(_ORDER_A1001)
    if fixture_refs.intersection(
        {"fx-search-multiple-owner-a-v1", "fx-order-targets-owner-a-v1"}
    ):
        orders.append(_ORDER_A1002)
    if "fx-search-unique-owner-a-with-foreign-decoy-v1" in fixture_refs or (
        "fx-dynamic-tool-pair-owner-a-v1" in fixture_refs
    ):
        searches.append(_SEARCH_A1001)
    if "fx-search-multiple-owner-a-v1" in fixture_refs:
        searches.extend((_SEARCH_A1001, _SEARCH_A1002))
    for fixture_ref in fixture_refs:
        shipments.extend(_shipment_payload(fixture_ref))
    return Cycle2BusinessSeedRowsV1(
        order_seeds=tuple(
            _deduplicate_exact(orders, key_fields=("owner_customer_id", "order_id"))
        ),
        search_document_seeds=tuple(
            _deduplicate_exact(
                searches,
                key_fields=("owner_customer_id", "order_id", "line_ordinal"),
            )
        ),
        shipment_seeds=tuple(
            _deduplicate_exact(
                shipments,
                key_fields=("owner_customer_id", "order_id", "package_id"),
            )
        ),
    )


def _foreign_rows(
    fixture_refs: tuple[str, ...],
) -> Cycle2ForeignControlRowsV1:
    if not set(fixture_refs).intersection(
        {
            "fx-search-unique-owner-a-with-foreign-decoy-v1",
            "fx-candidate-owner-mismatch-owner-a-v1",
        }
    ):
        return Cycle2ForeignControlRowsV1()
    order = _foreign_order()
    return Cycle2ForeignControlRowsV1(
        order_seeds=(order,),
        search_document_seeds=(_foreign_search(order),),
    )


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _owner_order_fixture_digest(
    *,
    business_rows: Cycle2BusinessSeedRowsV1,
    runtime_state: Cycle2RuntimeSetupV1,
) -> str:
    final_runtime_records = fold_cycle2_runtime_records(runtime_state)
    return _canonical_sha256(
        {
            "digest_schema": "cycle2-owner-order-initial-state.p0.v1",
            "owner_customer_id": _OWNER_A,
            "business_rows": business_rows.model_dump(mode="json"),
            "runtime_records": [
                record.model_dump(mode="json")
                for record in final_runtime_records
            ],
        }
    )


def _compute_w12_setup_digest_payload(payload: object) -> str:
    return f"sha256:{_canonical_sha256(payload)}"


def compute_cycle2_execution_setup_digest(
    plan: Cycle2ExecutionSetupPlanV1,
) -> str:
    if type(plan) is not Cycle2ExecutionSetupPlanV1:
        raise TypeError("exact Cycle2ExecutionSetupPlanV1 required")
    return _compute_w12_setup_digest_payload(
        plan.model_dump(mode="json", exclude={"setup_digest"})
    )


def _runtime_record_envelope(
    record: Cycle2RuntimeBaseRecordV1,
    *,
    graph: tuple[Cycle2RuntimeBaseRecordV1, ...],
) -> P0PersistenceEnvelope:
    """Encode one closed setup record through the production PostgreSQL codec."""

    from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

    source = record.source_record
    if type(source) is InputBindingV2:
        request_unit_ids = {
            candidate.source_record.request_unit_id
            for candidate in graph
            if type(candidate.source_record) is RequestUnitRecord
            and source.binding_id in candidate.source_record.input_binding_refs
        }
        successors = tuple(
            candidate.source_record
            for candidate in graph
            if type(candidate.source_record) is InputBindingV2
            and candidate.source_record.supersedes == source.binding_id
        )
        if not request_unit_ids and len(successors) == 1:
            request_unit_ids = {
                candidate.source_record.request_unit_id
                for candidate in graph
                if type(candidate.source_record) is RequestUnitRecord
                and successors[0].binding_id
                in candidate.source_record.input_binding_refs
            }
        if len(successors) > 1:
            raise Cycle2SeedError("input binding has multiple direct successors")
        if len(request_unit_ids) != 1:
            raise Cycle2SeedError("input binding does not have one RequestUnit parent")
        return PostgresRecordAdapter._cycle2_encode_input_binding(
            source,
            request_unit_id=next(iter(request_unit_ids)),
        )
    if type(source) is OrderCandidateAutoTargetRecord:
        bindings = tuple(
            candidate.source_record
            for candidate in graph
            if type(candidate.source_record) is InputBindingV2
            and candidate.source_record.binding_id
            == source.query_input_binding_ref
        )
        if len(bindings) != 1 or len(bindings[0].source_refs) != 1:
            raise Cycle2SeedError("auto target lacks one exact source binding")
        selection = PostgresRecordAdapter._cycle2_auto_target_selection(
            auto_target=source,
            source_message_ref=bindings[0].source_refs[0],
        )
        return PostgresRecordAdapter._cycle2_encode(
            P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
            selection,
        )
    if type(source) is ToolCallRecordV2:
        return PostgresRecordAdapter._cycle2_encode(
            record.record_code,
            source,
            logical_children=source.attempts,
        )
    if type(source) is ModelVisibleToolsetArtifact:
        return encode_persistence_record(record.record_code, source)
    return PostgresRecordAdapter._cycle2_encode(record.record_code, source)


def _runtime_envelope_key(
    envelope: P0PersistenceEnvelope,
) -> tuple[P0RecordCode, str]:
    return (
        envelope.record_code,
        _runtime_identity_text(envelope.logical_identity),
    )


def _runtime_identity_text(identity: object) -> str:
    return (
        json.dumps(
            identity,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


def _runtime_source_for_role(
    graph: tuple[Cycle2RuntimeBaseRecordV1, ...],
    *,
    role: str,
    expected_type: type[object],
) -> object:
    matches = tuple(
        record.source_record
        for record in graph
        if record.record_role == role
        and type(record.source_record) is expected_type
    )
    if len(matches) != 1:
        raise Cycle2SeedError(f"runtime role {role} is not exact")
    return matches[0]


def _runtime_message_referrers(
    graph: tuple[Cycle2RuntimeBaseRecordV1, ...],
    *,
    message_id: UUID,
) -> tuple[str, ...]:
    referrers: list[str] = []
    for record in graph:
        source = record.source_record
        references: tuple[UUID, ...] = ()
        if type(source) is InputBindingV2:
            references = source.source_refs
        elif type(source) is RequestUnitRecord:
            references = source.goal_source_refs
        elif type(source) is ContextManifest:
            references = source.selected_message_refs
        elif type(source) is TraceEventV2 and source.message_ref is not None:
            references = (source.message_ref,)
        referrers.extend(
            record.record_role for reference in references if reference == message_id
        )
    return tuple(referrers)


def _recovery_task_state_snapshots(
    runtime_state: Cycle2RuntimeSetupV1,
    graph: tuple[Cycle2RuntimeBaseRecordV1, ...],
) -> tuple[
    TaskRecord,
    RequestUnitRecord,
    TaskRecord,
    RequestUnitRecord,
    TaskRecord,
    RequestUnitRecord,
] | None:
    if runtime_state.recovery_subject_run_id is None:
        return None
    final_task = _runtime_source_for_role(
        graph,
        role="task.current",
        expected_type=TaskRecord,
    )
    final_unit = _runtime_source_for_role(
        graph,
        role="request_unit.current",
        expected_type=RequestUnitRecord,
    )
    target = _runtime_source_for_role(
        graph,
        role="auto_target.current",
        expected_type=OrderCandidateAutoTargetRecord,
    )
    query_binding = _runtime_source_for_role(
        graph,
        role="binding.product_description",
        expected_type=InputBindingV2,
    )
    old_order_binding = _runtime_source_for_role(
        graph,
        role="binding.order_id",
        expected_type=InputBindingV2,
    )
    fresh_order_binding = _runtime_source_for_role(
        graph,
        role="binding.order_id.recovery_root",
        expected_type=InputBindingV2,
    )
    assert (
        type(final_task) is TaskRecord
        and type(final_unit) is RequestUnitRecord
        and type(target) is OrderCandidateAutoTargetRecord
        and type(query_binding) is InputBindingV2
        and type(old_order_binding) is InputBindingV2
        and type(fresh_order_binding) is InputBindingV2
    )
    version_2_task = final_task.model_copy(
        update={"state_version": 2, "updated_at": target.verified_at}
    )
    version_2_unit = final_unit.model_copy(
        update={
            "state_version": 2,
            "updated_at": target.verified_at,
            "input_binding_refs": (
                query_binding.binding_id,
                old_order_binding.binding_id,
            ),
        }
    )
    version_3_task = final_task.model_copy(
        update={
            "state_version": 3,
            "updated_at": fresh_order_binding.updated_at,
        }
    )
    version_3_unit = final_unit.model_copy(
        update={
            "state_version": 3,
            "updated_at": fresh_order_binding.updated_at,
        }
    )
    return (
        version_2_task,
        version_2_unit,
        version_3_task,
        version_3_unit,
        final_task,
        final_unit,
    )


def _validate_cycle2_w12_provenance_graph(
    runtime_state: Cycle2RuntimeSetupV1,
    graph: tuple[Cycle2RuntimeBaseRecordV1, ...],
) -> None:
    target_items = tuple(
        record
        for record in graph
        if record.record_role == "auto_target.current"
        and type(record.source_record) is OrderCandidateAutoTargetRecord
    )
    if not target_items:
        if runtime_state.recovery_subject_run_id is not None:
            raise Cycle2SeedError("recovery setup lacks its verified target")
        return
    if len(target_items) != 1:
        raise Cycle2SeedError("verified target provenance is not unique")

    fixture_ref = target_items[0].fixture_ref
    target = target_items[0].source_record
    conversation = _runtime_source_for_role(
        graph,
        role="conversation.current",
        expected_type=ConversationRecord,
    )
    search_message = _runtime_source_for_role(
        graph,
        role="message.historical_user.search",
        expected_type=MessageRecord,
    )
    order_message = _runtime_source_for_role(
        graph,
        role="message.historical_user.order_id",
        expected_type=MessageRecord,
    )
    query_binding = _runtime_source_for_role(
        graph,
        role="binding.product_description",
        expected_type=InputBindingV2,
    )
    old_order_binding = _runtime_source_for_role(
        graph,
        role="binding.order_id",
        expected_type=InputBindingV2,
    )
    task = _runtime_source_for_role(
        graph,
        role="task.current",
        expected_type=TaskRecord,
    )
    unit = _runtime_source_for_role(
        graph,
        role="request_unit.current",
        expected_type=RequestUnitRecord,
    )
    assert (
        type(target) is OrderCandidateAutoTargetRecord
        and type(conversation) is ConversationRecord
        and type(search_message) is MessageRecord
        and type(order_message) is MessageRecord
        and type(query_binding) is InputBindingV2
        and type(old_order_binding) is InputBindingV2
        and type(task) is TaskRecord
        and type(unit) is RequestUnitRecord
    )

    if (
        target.query_input_binding_ref != query_binding.binding_id
        or query_binding.source_refs != (search_message.message_id,)
        or unit.goal_source_refs != (search_message.message_id,)
    ):
        raise Cycle2SeedError("search query provenance was rewritten")
    if (
        order_message.message_id
        != deterministic_cycle2_setup_uuid(
            fixture_ref, "message.historical_user.order_id"
        )
        or order_message.conversation_id != conversation.conversation_id
        or order_message.direction is not MessageDirection.USER
        or order_message.content != "我要查询订单 O-1001。"
        or order_message.received_at <= search_message.received_at
        or old_order_binding.binding_id
        != deterministic_cycle2_setup_uuid(fixture_ref, "binding.order_id")
        or old_order_binding.name != "order_id"
        or old_order_binding.normalized_value != "O-1001"
        or old_order_binding.authority is not InputAuthority.USER_CLAIM
        or old_order_binding.validation_status
        is not InputValidationStatus.ACCEPTED
        or old_order_binding.confirmed_by_user is not True
        or old_order_binding.source_refs != (order_message.message_id,)
        or old_order_binding.supersedes is not None
        or old_order_binding.created_at != order_message.received_at
        or old_order_binding.updated_at != order_message.received_at
        or order_message.received_at > task.updated_at
        or order_message.received_at > unit.updated_at
        or _runtime_message_referrers(
            graph, message_id=order_message.message_id
        )
        != ("binding.order_id",)
    ):
        raise Cycle2SeedError("ordinary order Claim provenance is not exact")

    recovery = runtime_state.recovery_subject_run_id is not None
    if not recovery:
        if (
            runtime_state.historical_user_messages
            or unit.input_binding_refs.count(query_binding.binding_id) != 1
            or unit.input_binding_refs.count(old_order_binding.binding_id) != 1
        ):
            raise Cycle2SeedError("ordinary current binding closure is not exact")
    else:
        auxiliary = _runtime_source_for_role(
            graph,
            role="message.historical_user.recovery",
            expected_type=MessageRecord,
        )
        fresh_order_binding = _runtime_source_for_role(
            graph,
            role="binding.order_id.recovery_root",
            expected_type=InputBindingV2,
        )
        run = _runtime_source_for_role(
            graph,
            role="recovery_root.run",
            expected_type=AgentRunRecordV2,
        )
        link = _runtime_source_for_role(
            graph,
            role="recovery_root.link",
            expected_type=RunTaskLinkRecordV2,
        )
        manifest = _runtime_source_for_role(
            graph,
            role="recovery_root.context_manifest",
            expected_type=ContextManifest,
        )
        gate = _runtime_source_for_role(
            graph,
            role="recovery_root.gate",
            expected_type=GateDecisionV2,
        )
        tool = _runtime_source_for_role(
            graph,
            role="recovery_root.tool_call",
            expected_type=ToolCallRecordV2,
        )
        trace = _runtime_source_for_role(
            graph,
            role="recovery_root.trace.message_accepted",
            expected_type=TraceEventV2,
        )
        assert (
            type(auxiliary) is MessageRecord
            and type(fresh_order_binding) is InputBindingV2
            and type(run) is AgentRunRecordV2
            and type(link) is RunTaskLinkRecordV2
            and type(manifest) is ContextManifest
            and type(gate) is GateDecisionV2
            and type(tool) is ToolCallRecordV2
            and type(trace) is TraceEventV2
        )
        attempt = tool.attempts[0] if len(tool.attempts) == 1 else None
        if (
            runtime_state.historical_user_messages != (auxiliary,)
            or auxiliary.conversation_id != conversation.conversation_id
            or auxiliary.direction is not MessageDirection.USER
            or auxiliary.content != "订单 O-1001 到哪了？"
            or auxiliary.received_at != run.started_at
            or not (
                search_message.received_at
                < order_message.received_at
                < auxiliary.received_at
            )
            or fresh_order_binding.name != "order_id"
            or fresh_order_binding.normalized_value != "O-1001"
            or fresh_order_binding.authority is not InputAuthority.USER_CLAIM
            or fresh_order_binding.validation_status
            is not InputValidationStatus.ACCEPTED
            or fresh_order_binding.confirmed_by_user is not True
            or fresh_order_binding.source_refs != (auxiliary.message_id,)
            or fresh_order_binding.supersedes != old_order_binding.binding_id
            or fresh_order_binding.created_at != fresh_order_binding.updated_at
            or fresh_order_binding.created_at < auxiliary.received_at
            or fresh_order_binding.updated_at > manifest.assembled_at
            or fresh_order_binding.updated_at > gate.decided_at
            or fresh_order_binding.updated_at > tool.started_at
            or task.state_version != 4
            or unit.state_version != 4
            or task.updated_at != unit.updated_at
            or unit.input_binding_refs
            != (query_binding.binding_id, fresh_order_binding.binding_id)
            or old_order_binding.binding_id in unit.input_binding_refs
            or run.run_id != runtime_state.recovery_subject_run_id
            or run.status is not AgentRunStatusV2.RUNNING
            or link.run_id != run.run_id
            or link.task_id != task.task_id
            or link.base_task_state_version != 2
            or link.result_task_state_version is not None
            or manifest.run_id != run.run_id
            or manifest.selected_message_refs != (auxiliary.message_id,)
            or manifest.task_state_ref_and_version.task_id != task.task_id
            or manifest.task_state_ref_and_version.state_version != 3
            or gate.context_manifest_id != manifest.context_manifest_id
            or gate.argument_binding_refs != (query_binding.binding_id,)
            or gate.proposed_base_task_state_version != 3
            or gate.validated_task_state_version != 3
            or gate.verified_target_ref != target.verified_target_ref
            or tool.run_id != run.run_id
            or tool.context_manifest_id != manifest.context_manifest_id
            or tool.gate_decision_id != gate.gate_decision_id
            or tool.argument_binding_refs != (query_binding.binding_id,)
            or tool.validated_task_state_version != 3
            or tool.verified_target_ref != target.verified_target_ref
            or attempt is None
            or attempt.retry_decision is not ToolRetryDecision.RETRY_SCHEDULED
            or attempt.finished_at is None
            or task.updated_at <= attempt.finished_at
            or trace.event_type is not TraceEventType.MESSAGE_ACCEPTED
            or trace.message_ref != auxiliary.message_id
            or _runtime_message_referrers(
                graph, message_id=auxiliary.message_id
            )
            != (
                "binding.order_id.recovery_root",
                "recovery_root.context_manifest",
                "recovery_root.trace.message_accepted",
            )
        ):
            raise Cycle2SeedError("recovery v2-v3-v4 provenance is not exact")

    overlay_bindings = tuple(
        record
        for record in graph
        if record.record_role
        in {
            "binding.shipment_not_received.true",
            "binding.shipment_not_received.false",
        }
    )
    if overlay_bindings:
        true_message = _runtime_source_for_role(
            graph,
            role="message.historical_user.shipment_not_received.true",
            expected_type=MessageRecord,
        )
        false_message = _runtime_source_for_role(
            graph,
            role="message.historical_user.shipment_not_received.false",
            expected_type=MessageRecord,
        )
        true_binding = _runtime_source_for_role(
            graph,
            role="binding.shipment_not_received.true",
            expected_type=InputBindingV2,
        )
        false_binding = _runtime_source_for_role(
            graph,
            role="binding.shipment_not_received.false",
            expected_type=InputBindingV2,
        )
        assert (
            type(true_message) is MessageRecord
            and type(false_message) is MessageRecord
            and type(true_binding) is InputBindingV2
            and type(false_binding) is InputBindingV2
        )
        if (
            len(runtime_state.overlays) != 1
            or true_message.conversation_id != conversation.conversation_id
            or false_message.conversation_id != conversation.conversation_id
            or true_message.message_id == false_message.message_id
            or true_message.content
            != "订单 O-1001 显示已送达，但我没有收到。"
            or false_message.content != "更正：订单 O-1001 已经收到了。"
            or true_message.direction is not MessageDirection.USER
            or false_message.direction is not MessageDirection.USER
            or true_message.received_at >= false_message.received_at
            or true_binding.name != "shipment_not_received"
            or type(true_binding.normalized_value) is not bool
            or true_binding.normalized_value is not True
            or true_binding.source_refs != (true_message.message_id,)
            or true_binding.supersedes is not None
            or true_binding.created_at != true_message.received_at
            or true_binding.updated_at != true_message.received_at
            or false_binding.name != "shipment_not_received"
            or type(false_binding.normalized_value) is not bool
            or false_binding.normalized_value is not False
            or false_binding.source_refs != (false_message.message_id,)
            or false_binding.supersedes != true_binding.binding_id
            or false_binding.created_at != false_message.received_at
            or false_binding.updated_at != false_message.received_at
            or task.state_version != 4
            or unit.state_version != 4
            or task.updated_at != false_binding.updated_at
            or unit.updated_at != false_binding.updated_at
            or true_binding.binding_id in unit.input_binding_refs
            or unit.input_binding_refs.count(false_binding.binding_id) != 1
            or _runtime_message_referrers(
                graph, message_id=true_message.message_id
            )
            != ("binding.shipment_not_received.true",)
            or _runtime_message_referrers(
                graph, message_id=false_message.message_id
            )
            != ("binding.shipment_not_received.false",)
        ):
            raise Cycle2SeedError("corrected Claim provenance is not exact")


def fold_cycle2_runtime_records(
    runtime_state: Cycle2RuntimeSetupV1,
) -> tuple[Cycle2RuntimeBaseRecordV1, ...]:
    """Pre-check and fold the closed overlays exactly once, then close references."""

    if type(runtime_state) is not Cycle2RuntimeSetupV1:
        raise Cycle2SeedError("exact Cycle2RuntimeSetupV1 required")
    potential_graph = (
        *runtime_state.base_records,
        *(
            record
            for overlay in runtime_state.overlays
            for record in (*overlay.expected_pre_images, *overlay.next_records)
        ),
    )
    ordered: list[Cycle2RuntimeBaseRecordV1] = []
    by_key: dict[tuple[P0RecordCode, str], Cycle2RuntimeBaseRecordV1] = {}
    for record in runtime_state.base_records:
        envelope = _runtime_record_envelope(record, graph=potential_graph)
        key = _runtime_envelope_key(envelope)
        previous = by_key.get(key)
        if previous is not None:
            if previous.source_record != record.source_record:
                raise Cycle2SeedError("same runtime identity has conflicting payloads")
            continue
        by_key[key] = record
        ordered.append(record)

    applied: set[str] = set()
    for overlay in runtime_state.overlays:
        if overlay.fixture_ref in applied:
            raise Cycle2SeedError("runtime overlay can only fold once")
        for pre_image in overlay.expected_pre_images:
            key = _runtime_envelope_key(
                _runtime_record_envelope(pre_image, graph=potential_graph)
            )
            existing = by_key.get(key)
            if existing is None or existing.source_record != pre_image.source_record:
                raise Cycle2SeedError("runtime overlay pre-image mismatch")
        for next_record in overlay.next_records:
            key = _runtime_envelope_key(
                _runtime_record_envelope(next_record, graph=potential_graph)
            )
            existing = by_key.get(key)
            if existing is not None:
                index = ordered.index(existing)
                ordered[index] = next_record
            else:
                ordered.append(next_record)
            by_key[key] = next_record
        applied.add(overlay.fixture_ref)

    graph = tuple(ordered)
    envelopes = tuple(
        _runtime_record_envelope(record, graph=graph) for record in graph
    )
    keys = {_runtime_envelope_key(envelope) for envelope in envelopes}
    if len(keys) != len(envelopes):
        raise Cycle2SeedError("post-fold runtime identities are not unique")
    observation_identities = {
        key[1]
        for key in keys
        if key[0]
        in {
            P0RecordCode.OBSERVATION_RECORD,
            P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
            P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
        }
    }
    for envelope in envelopes:
        for reference in envelope.record_references:
            reference_key = (
                reference.target_record_code,
                _runtime_identity_text(reference.target_logical_identity),
            )
            if reference.target_record_code is P0RecordCode.OBSERVATION_RECORD:
                if reference_key[1] not in observation_identities:
                    raise Cycle2SeedError("runtime observation reference is dangling")
            elif reference_key not in keys:
                raise Cycle2SeedError("runtime record reference is dangling")
    if any(
        type(record.source_record) is MessageRecord
        and record.source_record.direction is not MessageDirection.USER
        for record in graph
    ):
        raise Cycle2SeedError("setup cannot preseed outbound Message authority")
    if any(
        type(record.source_record) is TaskRecord
        and record.source_record.owner_customer_id != _OWNER_A
        for record in graph
    ):
        raise Cycle2SeedError("runtime graph crossed the authenticated owner")
    if runtime_state.recovery_subject_run_id is not None:
        recovery_runs = tuple(
            record.source_record
            for record in graph
            if type(record.source_record) is AgentRunRecordV2
            and record.source_record.run_id == runtime_state.recovery_subject_run_id
        )
        if (
            len(recovery_runs) != 1
            or recovery_runs[0].status is not AgentRunStatusV2.RUNNING
            or recovery_runs[0].completed_at is not None
            or recovery_runs[0].stop_reason is not None
        ):
            raise Cycle2SeedError("recovery subject is not one non-terminal root")
    _validate_cycle2_w12_provenance_graph(runtime_state, graph)
    return graph


def _write_w12_business_rows(
    session: Session,
    *,
    business: Cycle2BusinessSeedRowsV1,
    foreign: Cycle2ForeignControlRowsV1,
) -> None:
    order_seeds = (*business.order_seeds, *foreign.order_seeds)
    search_seeds = (*business.search_document_seeds, *foreign.search_document_seeds)
    order_keys = {(seed.owner_customer_id, seed.order_id) for seed in order_seeds}
    if any(
        (seed.owner_customer_id, seed.order_id) not in order_keys
        for seed in (*search_seeds, *business.shipment_seeds)
    ):
        raise Cycle2SeedError("W12 business child lacks its exact order parent")
    for seed in order_seeds:
        session.add(
            MockOrderModel(
                customer_id=seed.owner_customer_id,
                order_id=seed.order_id,
                order_payload=seed.order_payload.model_dump(mode="json"),
            )
        )
    for seed in search_seeds:
        session.add(
            MockOrderSearchDocumentModel(
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
        )
    for seed in business.shipment_seeds:
        session.add(
            MockShipmentModel(
                customer_id=seed.owner_customer_id,
                order_id=seed.order_id,
                package_id=seed.package_id,
                shipment_payload=dict(seed.shipment_payload),
            )
        )


def apply_cycle2_execution_setup_plan(
    session_factory: sessionmaker[Session],
    plan: Cycle2ExecutionSetupPlanV1,
    *,
    attachment_target: Cycle2ExecutionSetupAttachmentTarget,
) -> Cycle2DetachedExecutionSetup:
    """Atomically install one immutable W12 business/runtime setup and attach it."""

    from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

    if (
        type(plan) is not Cycle2ExecutionSetupPlanV1
        or plan.setup_digest != compute_cycle2_execution_setup_digest(plan)
    ):
        raise Cycle2SeedError("exact digest-bound W12 setup plan required")
    graph = fold_cycle2_runtime_records(plan.runtime_state)
    recovery_snapshots = _recovery_task_state_snapshots(
        plan.runtime_state, graph
    )
    install_graph = graph
    if recovery_snapshots is not None:
        version_2_task, version_2_unit, _, _, _, _ = recovery_snapshots
        install_graph = _replace_runtime_record(
            install_graph,
            role="task.current",
            replacement=_runtime_record(
                next(
                    record.fixture_ref
                    for record in graph
                    if record.record_role == "task.current"
                ),
                "task.current",
                P0RecordCode.TASK_RECORD,
                version_2_task,
            ),
        )
        install_graph = _replace_runtime_record(
            install_graph,
            role="request_unit.current",
            replacement=_runtime_record(
                next(
                    record.fixture_ref
                    for record in graph
                    if record.record_role == "request_unit.current"
                ),
                "request_unit.current",
                P0RecordCode.REQUEST_UNIT_RECORD,
                version_2_unit,
            ),
        )
    envelopes = tuple(
        _runtime_record_envelope(record, graph=graph)
        for record in install_graph
    )
    controller = (
        None
        if plan.fault_plan is None
        else build_cycle2_detached_fault_controller(plan.fault_plan)
    )
    detached = Cycle2DetachedExecutionSetup(
        setup_digest=plan.setup_digest,
        trusted_context_fixture_ref=plan.trusted_context_fixture_ref,
        owner_customer_id=plan.owner_customer_id,
        trusted_clock=W12_TRUSTED_CLOCK,
        fault_controller=controller,
    )
    adapter = PostgresRecordAdapter(session_factory)
    try:
        with session_factory.begin() as session:
            namespace_row = session.execute(
                text("SELECT current_database(), current_schema()")
            ).one()
            namespace_identity = (namespace_row[0], namespace_row[1])
            if not all(type(item) is str and item for item in namespace_identity):
                raise Cycle2SeedError("W12 setup namespace identity is unavailable")
            with _W12_SETUP_NAMESPACE_CLAIMS_LOCK:
                if namespace_identity in _W12_SETUP_NAMESPACE_CLAIMS:
                    raise Cycle2SeedError(
                        "W12 setup namespace is already claimed or invalidated"
                    )
                _W12_SETUP_NAMESPACE_CLAIMS.add(namespace_identity)
            if any(
                session.scalar(select(model).limit(1)) is not None
                for model in (
                    MockOrderModel,
                    MockOrderSearchDocumentModel,
                    MockShipmentModel,
                    P0RecordModel,
                )
            ):
                raise Cycle2SeedError("W12 setup requires a fresh isolated namespace")
            _write_w12_business_rows(
                session,
                business=plan.business_rows,
                foreign=plan.foreign_control_rows,
            )
            public_envelopes = tuple(
                envelope
                for envelope in envelopes
                if envelope.record_code
                is P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT
            )
            private_envelopes = tuple(
                envelope for envelope in envelopes if envelope not in public_envelopes
            )
            adapter._persist_envelopes(session, public_envelopes)
            adapter._cycle2_insert(
                session,
                private_envelopes,
                owner_customer_id=plan.owner_customer_id,
            )
            if recovery_snapshots is not None:
                (
                    version_2_task,
                    version_2_unit,
                    version_3_task,
                    version_3_unit,
                    final_task,
                    final_unit,
                ) = recovery_snapshots

                def replace_state_record(
                    record_code: P0RecordCode,
                    logical_identity: tuple[tuple[str, object], ...],
                    expected_record: TaskRecord | RequestUnitRecord,
                    next_record: TaskRecord | RequestUnitRecord,
                ) -> None:
                    loaded = adapter._cycle2_row(
                        session,
                        owner_customer_id=plan.owner_customer_id,
                        record_code=record_code,
                        logical_identity=logical_identity,
                        for_update=True,
                    )
                    if loaded is None:
                        raise Cycle2SeedError(
                            "recovery Task snapshot row is missing"
                        )
                    adapter._cycle2_replace(
                        session,
                        loaded[0],
                        owner_customer_id=plan.owner_customer_id,
                        expected_record=expected_record,
                        next_envelope=adapter._cycle2_encode(
                            record_code, next_record
                        ),
                    )

                task_identity = (("task_id", final_task.task_id),)
                unit_identity = (
                    ("request_unit_id", final_unit.request_unit_id),
                )
                replace_state_record(
                    P0RecordCode.TASK_RECORD,
                    task_identity,
                    version_2_task,
                    version_3_task,
                )
                replace_state_record(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    unit_identity,
                    version_2_unit,
                    version_3_unit,
                )
                replace_state_record(
                    P0RecordCode.TASK_RECORD,
                    task_identity,
                    version_3_task,
                    final_task,
                )
                replace_state_record(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    unit_identity,
                    version_3_unit,
                    final_unit,
                )
            detached.attach(attachment_target)
    except Cycle2SeedError:
        try:
            if detached.is_attached:
                detached.detach()
        finally:
            detached.dispose()
        raise
    except Exception:
        try:
            if detached.is_attached:
                detached.detach()
        finally:
            detached.dispose()
        raise Cycle2SeedError("W12 setup transaction or attach failed") from None
    return detached


def resolve_cycle2_execution_setup_plan(
    *,
    trusted_context_fixture_ref: str,
    initial_state_fixture_refs: Iterable[str],
    environment_fixture_refs: Iterable[str],
    fault_ref: str | None,
    authenticated_user_message: str | None = None,
    registry_snapshot: RegistrySnapshot | None = None,
) -> Cycle2ExecutionSetupPlanV1:
    if trusted_context_fixture_ref != _SESSION_ALICE:
        raise Cycle2SeedError("unknown trusted context fixture")
    requested = tuple(initial_state_fixture_refs) + tuple(environment_fixture_refs)
    if not requested or len(requested) != len(set(requested)):
        raise Cycle2SeedError("W12 fixture refs must be non-empty and unique")
    unknown = set(requested) - set(_W12_FIXTURE_CATALOG)
    if unknown:
        raise Cycle2SeedError("unknown W12 fixture ref")
    requested_set = set(requested)
    definitions = tuple(
        definition
        for definition in _W12_FIXTURE_CATALOG.values()
        if definition.fixture_ref in requested_set
    )
    for definition in definitions:
        if not set(definition.prerequisite_fixture_refs).issubset(requested_set):
            raise Cycle2SeedError("W12 overlay prerequisite is missing")
    selected_fault = None
    if fault_ref is not None:
        selected_fault = _W12_FAULT_CATALOG.get(fault_ref)
        if selected_fault is None:
            raise Cycle2SeedError("unknown W12 fault ref")
    runtime_state = _runtime_setup(
        definitions,
        authenticated_user_message=authenticated_user_message,
    )
    business_rows = _business_rows(definitions)
    fixture_refs = tuple(definition.fixture_ref for definition in definitions)
    pair_evidence = None
    is_pair = "fx-dynamic-tool-pair-owner-a-v1" in fixture_refs
    if is_pair:
        if type(registry_snapshot) is not RegistrySnapshot:
            raise Cycle2SeedError("pair setup requires the actual RegistrySnapshot")
        final_runtime_records = fold_cycle2_runtime_records(runtime_state)
        toolset_artifacts = tuple(
            record.source_record
            for record in final_runtime_records
            if type(record.source_record) is ModelVisibleToolsetArtifact
        )
        manifests = tuple(
            record.source_record
            for record in final_runtime_records
            if type(record.source_record) is ContextManifest
        )
        if (
            toolset_artifacts
            and any(
                artifact != registry_snapshot.artifact()
                for artifact in toolset_artifacts
            )
        ) or any(
            manifest.tool_registry_version
            != registry_snapshot.tool_registry_version
            or manifest.model_visible_toolset_hash
            != registry_snapshot.model_visible_toolset_hash
            for manifest in manifests
        ):
            raise Cycle2SeedError(
                "pair runtime graph does not use the actual RegistrySnapshot"
            )
        pair_evidence = Cycle2PairExecutionEvidenceV1(
            registry_snapshot_digest=compute_registry_snapshot_digest(
                registry_snapshot
            ),
            model_visible_toolset_hash=(
                registry_snapshot.model_visible_toolset_hash
            ),
            provider_mapping_digest=compute_provider_mapping_digest(
                registry_snapshot
            ),
            owner_order_initial_state_digest=_owner_order_fixture_digest(
                business_rows=business_rows,
                runtime_state=runtime_state,
            ),
        )
    elif registry_snapshot is not None:
        raise Cycle2SeedError("non-pair setup cannot accept RegistrySnapshot evidence")
    values = {
        "setup_schema_version": W12_SETUP_SCHEMA_VERSION,
        "fixture_catalog_version": W12_FIXTURE_CATALOG_VERSION,
        "trusted_context_fixture_ref": _SESSION_ALICE,
        "owner_customer_id": _OWNER_A,
        "trusted_clock_profile_ref": W12_TRUSTED_CLOCK_PROFILE_REF,
        "fixture_refs": fixture_refs,
        "business_rows": business_rows,
        "runtime_state": runtime_state,
        "foreign_control_rows": _foreign_rows(fixture_refs),
        "fault_plan": selected_fault,
        "pair_evidence": pair_evidence,
    }
    digest_projection = {
        key: (
            value.model_dump(mode="json")
            if isinstance(value, BaseModel)
            else value
        )
        for key, value in values.items()
    }
    values["setup_digest"] = _compute_w12_setup_digest_payload(
        digest_projection
    )
    try:
        return Cycle2ExecutionSetupPlanV1(**values)
    except (TypeError, ValueError, ValidationError):
        raise Cycle2SeedError("W12 setup plan failed closed validation") from None
