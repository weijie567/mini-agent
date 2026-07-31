"""Observation and Context Manifest contracts; neither is free-form Memory."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, StrictStr, field_validator, model_validator

from .common import (
    AuditOnlyModel,
    ModelVisibleModel,
    RuntimePrivateModel,
    require_utc,
)
from .order import OrderSummaryProjection
from .order_search import (
    ORDER_SEARCH_MATCHING_RULE_VERSION,
    ORDER_SEARCH_MAX_CANDIDATES,
    OrderCandidatePublicSummary,
    OrderCandidateSourceVersion,
    OrderSearchSnapshotSourceVersion,
)
from .shipment import (
    SHIPMENT_FRESHNESS_TTL,
    ShipmentFreshnessDecisionResult,
    ShipmentSourceVersion,
    ShipmentSummaryProjection,
    decide_shipment_freshness,
)
from .task_state import (
    ORDER_CANDIDATE_SET_TTL,
    ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION,
    OrderCandidateSelectionRecord,
    OrderCandidateSelectionRequest,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    validate_current_candidate_selection,
)
from .tool_system import ToolsetHash

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveStateVersion = Annotated[int, Field(ge=1)]


class ObservationVisibility(StrEnum):
    MODEL_VISIBLE = "MODEL_VISIBLE"
    AUDIT_ONLY = "AUDIT_ONLY"
    USER_VISIBLE = "USER_VISIBLE"


class OrderObservation(AuditOnlyModel):
    """A safe Observation created only after scoped ownership validation."""

    observation_id: UUID
    source_tool: Literal["get_order"]
    source_resource_ref: NonEmptyString
    source_version: NonEmptyString | None = None
    normalized_type: Literal["ORDER_SUMMARY"]
    normalized_value: OrderSummaryProjection
    observed_at: datetime
    recorded_at: datetime
    valid_until: datetime | None = None
    supersedes: UUID | None = None
    raw_result_ref: NonEmptyString | None = None
    visibility: ObservationVisibility

    @field_validator("observed_at", "recorded_at", "valid_until")
    @classmethod
    def observation_timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_utc(value, field_name="OrderObservation timestamp")

    @model_validator(mode="after")
    def observation_dates_are_ordered(self) -> Self:
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.valid_until is not None and self.valid_until < self.observed_at:
            raise ValueError("valid_until cannot precede observed_at")
        return self


class TaskStateRefAndVersion(AuditOnlyModel):
    task_id: UUID
    state_version: PositiveStateVersion


class VersionedRecordRef(AuditOnlyModel):
    record_ref: UUID
    version: NonEmptyString


class TruncationDecision(AuditOnlyModel):
    source_ref: UUID
    reason_code: NonEmptyString


class TokenCounts(AuditOnlyModel):
    input_tokens: Annotated[int, Field(ge=0, strict=True)] | None = None
    output_tokens: Annotated[int, Field(ge=0, strict=True)] | None = None


class ContextManifest(AuditOnlyModel):
    """References actually projected to one model call, without private payloads."""

    context_manifest_id: UUID
    run_id: UUID
    model_call_id: UUID
    tool_registry_version: NonEmptyString
    model_visible_toolset_hash: ToolsetHash
    selected_message_refs: tuple[UUID, ...]
    task_state_ref_and_version: TaskStateRefAndVersion | None = None
    observation_refs_and_versions: tuple[VersionedRecordRef, ...] = ()
    evidence_refs_and_versions: tuple[VersionedRecordRef, ...] = ()
    action_record_refs: tuple[UUID, ...] = ()
    redaction_policy_version: NonEmptyString
    truncation_decisions: tuple[TruncationDecision, ...] = ()
    token_counts: TokenCounts
    assembled_at: datetime

    @field_validator("assembled_at")
    @classmethod
    def assembled_at_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, field_name="assembled_at")


SHIPMENT_OBSERVATION_RECORD_SCHEMA_VERSION = "shipment_observation_record.p0.v1"
StrictPrivateRef = Annotated[
    StrictStr,
    Field(min_length=1, pattern=r"^\S+$"),
]


class SearchObservationCandidateTargetBinding(RuntimePrivateModel):
    """Private one-to-one authority mapping for one search candidate."""

    observation_candidate_ref: UUID
    owner_scoped_order_ref: StrictPrivateRef
    candidate_source_version: OrderCandidateSourceVersion


class SearchOrdersObservationCandidate(AuditOnlyModel):
    observation_candidate_ref: UUID
    candidate_source_version: OrderCandidateSourceVersion
    public_summary: OrderCandidatePublicSummary


class SearchOrdersObservationValue(AuditOnlyModel):
    matching_rule_version: Literal["order-search-matching.p0.v1"] = (
        ORDER_SEARCH_MATCHING_RULE_VERSION
    )
    ordered_candidates: Annotated[
        tuple[SearchOrdersObservationCandidate, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    truncated: StrictBool

    @model_validator(mode="after")
    def normalized_candidates_are_unambiguous(self) -> Self:
        refs = tuple(
            candidate.observation_candidate_ref
            for candidate in self.ordered_candidates
        )
        versions = tuple(
            candidate.candidate_source_version
            for candidate in self.ordered_candidates
        )
        if len(refs) != len(set(refs)):
            raise ValueError("Observation candidate refs must be unique")
        if len(versions) != len(set(versions)):
            raise ValueError("Observation candidate source versions must be unique")
        if self.truncated and len(self.ordered_candidates) != (
            ORDER_SEARCH_MAX_CANDIDATES
        ):
            raise ValueError("truncated=true requires exactly five candidates")
        return self


class SearchOrdersObservation(AuditOnlyModel):
    """Audit-only owner-scoped search snapshot and its private target mapping."""

    record_schema_version: ClassVar[
        Literal["order_search_observation_record.p0.v1"]
    ] = ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION

    observation_id: UUID
    private_owner_scope: StrictPrivateRef
    source_tool: Literal["search_orders"]
    source_tool_call_id: UUID
    source_resource_ref: StrictPrivateRef
    source_version: OrderSearchSnapshotSourceVersion
    candidate_target_bindings: Annotated[
        tuple[SearchObservationCandidateTargetBinding, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    normalized_type: Literal["ORDER_SEARCH_CANDIDATES"]
    normalized_value: SearchOrdersObservationValue
    observed_at: datetime
    recorded_at: datetime
    valid_until: datetime
    visibility: Literal[ObservationVisibility.AUDIT_ONLY] = (
        ObservationVisibility.AUDIT_ONLY
    )

    @field_validator("observed_at", "recorded_at", "valid_until")
    @classmethod
    def search_observation_timestamps_are_utc(
        cls,
        value: datetime,
    ) -> datetime:
        return require_utc(value, field_name="SearchOrdersObservation timestamp")

    @model_validator(mode="after")
    def search_observation_closure_is_exact(self) -> Self:
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.valid_until != self.recorded_at + ORDER_CANDIDATE_SET_TTL:
            raise ValueError(
                "SearchOrdersObservation valid_until must equal recorded_at plus "
                "15 minutes"
            )
        safe_pairs = tuple(
            (
                candidate.observation_candidate_ref,
                candidate.candidate_source_version,
            )
            for candidate in self.normalized_value.ordered_candidates
        )
        private_pairs = tuple(
            (
                binding.observation_candidate_ref,
                binding.candidate_source_version,
            )
            for binding in self.candidate_target_bindings
        )
        if private_pairs != safe_pairs:
            raise ValueError(
                "safe candidates and private target bindings must exactly match"
            )
        target_refs = tuple(
            binding.owner_scoped_order_ref
            for binding in self.candidate_target_bindings
        )
        if len(target_refs) != len(set(target_refs)):
            raise ValueError("owner-scoped order target refs must be unique")
        return self


class SearchOrdersObservationSafeCandidate(ModelVisibleModel):
    ordinal: Annotated[
        int,
        Field(strict=True, ge=1, le=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    public_summary: OrderCandidatePublicSummary


class SearchOrdersObservationSafeProjection(ModelVisibleModel):
    """The only search Observation projection permitted across model boundaries."""

    matching_rule_version: Literal["order-search-matching.p0.v1"]
    ordered_candidates: Annotated[
        tuple[SearchOrdersObservationSafeCandidate, ...],
        Field(min_length=1, max_length=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    truncated: StrictBool

    @model_validator(mode="after")
    def safe_candidate_ordinals_are_contiguous(self) -> Self:
        ordinals = tuple(candidate.ordinal for candidate in self.ordered_candidates)
        if ordinals != tuple(range(1, len(self.ordered_candidates) + 1)):
            raise ValueError("safe candidate ordinals must be contiguous from one")
        if self.truncated and len(self.ordered_candidates) != (
            ORDER_SEARCH_MAX_CANDIDATES
        ):
            raise ValueError("truncated=true requires exactly five candidates")
        return self


def project_search_orders_observation_safe(
    observation: SearchOrdersObservation,
) -> SearchOrdersObservationSafeProjection:
    """Copy the exact safe whitelist after record integrity has validated."""

    return SearchOrdersObservationSafeProjection(
        matching_rule_version=observation.normalized_value.matching_rule_version,
        ordered_candidates=tuple(
            SearchOrdersObservationSafeCandidate(
                ordinal=ordinal,
                public_summary=candidate.public_summary,
            )
            for ordinal, candidate in enumerate(
                observation.normalized_value.ordered_candidates,
                start=1,
            )
        ),
        truncated=observation.normalized_value.truncated,
    )


def validate_search_candidate_set_observation_closure(
    *,
    candidate_set: OrderCandidateSetRecord,
    observation: SearchOrdersObservation,
) -> None:
    """Validate exact CandidateSet/Observation equality without persistence IO."""

    if candidate_set.private_owner_scope_ref != observation.private_owner_scope:
        raise ValueError("CandidateSet and Search Observation owner scope mismatch")
    if candidate_set.source_tool_call_id != observation.source_tool_call_id:
        raise ValueError("CandidateSet and Search Observation ToolCall mismatch")
    if candidate_set.search_observation_ref != observation.observation_id:
        raise ValueError("CandidateSet Search Observation ref mismatch")
    if candidate_set.search_observation_record_schema_version != (
        observation.record_schema_version
    ):
        raise ValueError("CandidateSet Search Observation schema mismatch")
    if candidate_set.search_observation_source_version != observation.source_version:
        raise ValueError("CandidateSet Search Observation source version mismatch")
    if candidate_set.created_at != observation.recorded_at:
        raise ValueError("CandidateSet created_at must equal Observation recorded_at")
    if candidate_set.valid_until != observation.valid_until:
        raise ValueError("CandidateSet and Observation TTL boundary mismatch")

    expected_entries = tuple(
        OrderCandidateSetEntry(
            ordinal=ordinal,
            observation_candidate_ref=candidate.observation_candidate_ref,
            candidate_source_version=candidate.candidate_source_version,
        )
        for ordinal, candidate in enumerate(
            observation.normalized_value.ordered_candidates,
            start=1,
        )
    )
    if candidate_set.ordered_candidates != expected_entries:
        raise ValueError(
            "CandidateSet candidates must exactly match Search Observation order"
        )
    expected_outcome = (
        OrderCandidateSetOutcome.UNIQUE
        if len(expected_entries) == 1
        else OrderCandidateSetOutcome.MULTIPLE
    )
    if candidate_set.outcome is not expected_outcome:
        raise ValueError("CandidateSet outcome does not match Observation cardinality")


class CandidateSelectionValidationDecision(RuntimePrivateModel):
    """Positive pure validation decision with no selected target or Tool grant."""

    decision: Literal["ACCEPT"] = "ACCEPT"
    candidate_set_ref: UUID
    search_observation_ref: UUID
    ordinal_input_binding_ref: UUID
    ordinal: Annotated[
        int,
        Field(strict=True, ge=1, le=ORDER_SEARCH_MAX_CANDIDATES),
    ]
    observation_candidate_ref: UUID
    candidate_source_version: OrderCandidateSourceVersion


def validate_candidate_selection_closure(
    *,
    current_candidate_sets: Sequence[OrderCandidateSetRecord],
    observation: SearchOrdersObservation,
    request: OrderCandidateSelectionRequest,
    trusted_owner_scope_ref: str,
    conversation_id: UUID,
    task_id: UUID,
    request_unit_id: UUID,
    pending_candidate_set_ref: UUID | None,
    current_task_state_version: int,
    current_query_binding_refs: Sequence[UUID],
    trusted_now: datetime,
    resolved_owner_scoped_order_target_ref: str | None,
    superseded_candidate_set_refs: Sequence[UUID] = (),
    existing_selection_records: Sequence[OrderCandidateSelectionRecord] = (),
) -> CandidateSelectionValidationDecision:
    """Close selection over already-loaded records without performing CAS or IO."""

    sets = tuple(current_candidate_sets)
    if len(sets) != 1:
        raise ValueError("selection requires exactly one current CandidateSet")
    candidate_set = sets[0]
    validate_search_candidate_set_observation_closure(
        candidate_set=candidate_set,
        observation=observation,
    )
    selected = validate_current_candidate_selection(
        current_candidate_sets=sets,
        request=request,
        trusted_owner_scope_ref=trusted_owner_scope_ref,
        conversation_id=conversation_id,
        task_id=task_id,
        request_unit_id=request_unit_id,
        pending_candidate_set_ref=pending_candidate_set_ref,
        current_task_state_version=current_task_state_version,
        current_query_binding_refs=current_query_binding_refs,
        trusted_now=trusted_now,
        superseded_candidate_set_refs=superseded_candidate_set_refs,
        existing_selection_records=existing_selection_records,
    )
    matching_target_bindings = tuple(
        binding
        for binding in observation.candidate_target_bindings
        if binding.observation_candidate_ref == selected.observation_candidate_ref
        and binding.candidate_source_version == selected.candidate_source_version
    )
    if len(matching_target_bindings) != 1:
        raise ValueError("candidate target mapping must resolve exactly once")
    if resolved_owner_scoped_order_target_ref is None:
        raise ValueError("owner-scoped exact target reader did not resolve a target")
    if (
        matching_target_bindings[0].owner_scoped_order_ref
        != resolved_owner_scoped_order_target_ref
    ):
        raise ValueError("owner-scoped exact target reader result mismatch")
    return CandidateSelectionValidationDecision(
        candidate_set_ref=candidate_set.candidate_set_id,
        search_observation_ref=observation.observation_id,
        ordinal_input_binding_ref=request.ordinal_input_binding_ref,
        ordinal=request.ordinal,
        observation_candidate_ref=selected.observation_candidate_ref,
        candidate_source_version=selected.candidate_source_version,
    )


class ShipmentObservation(AuditOnlyModel):
    """Audit-only accepted Shipment snapshot with exact business projection."""

    record_schema_version: ClassVar[
        Literal["shipment_observation_record.p0.v1"]
    ] = SHIPMENT_OBSERVATION_RECORD_SCHEMA_VERSION

    observation_id: UUID
    private_owner_scope: StrictPrivateRef
    task_id: UUID
    request_unit_id: UUID
    verified_order_target_ref: StrictPrivateRef
    source_tool: Literal["get_shipment"]
    source_tool_call_id: UUID
    source_resource_ref: StrictPrivateRef
    source_version: ShipmentSourceVersion
    normalized_type: Literal["SHIPMENT_SUMMARY"]
    normalized_value: ShipmentSummaryProjection
    observed_at: datetime
    recorded_at: datetime
    valid_until: datetime
    supersedes: UUID | None = None
    raw_result_ref: StrictPrivateRef | None = None
    visibility: Literal[ObservationVisibility.AUDIT_ONLY] = (
        ObservationVisibility.AUDIT_ONLY
    )

    @field_validator("observed_at", "recorded_at", "valid_until")
    @classmethod
    def shipment_observation_timestamps_are_utc(
        cls,
        value: datetime,
    ) -> datetime:
        return require_utc(value, field_name="ShipmentObservation timestamp")

    @model_validator(mode="after")
    def shipment_observation_is_fresh_at_acceptance(self) -> Self:
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.valid_until != self.observed_at + SHIPMENT_FRESHNESS_TTL:
            raise ValueError(
                "ShipmentObservation valid_until must equal observed_at plus 5 minutes"
            )
        if self.recorded_at >= self.valid_until:
            raise ValueError("ShipmentObservation cannot be born stale")
        if self.normalized_value.latest_event_at > self.observed_at:
            raise ValueError("Shipment latest_event_at cannot be after observed_at")
        if self.supersedes == self.observation_id:
            raise ValueError("ShipmentObservation cannot supersede itself")
        return self


def validate_shipment_observation_supersession(
    *,
    current: ShipmentObservation,
    previous: ShipmentObservation,
) -> None:
    """Validate an append-only same-owner/Task/target Shipment supersession."""

    if current.supersedes != previous.observation_id:
        raise ValueError("Shipment supersession ref does not identify previous record")
    for field_name in (
        "private_owner_scope",
        "task_id",
        "verified_order_target_ref",
    ):
        if getattr(current, field_name) != getattr(previous, field_name):
            raise ValueError(f"Shipment supersession {field_name} mismatch")
    if current.observed_at < previous.observed_at:
        raise ValueError("Shipment supersession cannot move observed_at backwards")
    if current.recorded_at < previous.recorded_at:
        raise ValueError("Shipment supersession cannot move recorded_at backwards")


def decide_loaded_shipment_observation_freshness(
    *,
    current_observations: Sequence[ShipmentObservation],
    trusted_freshness_now: datetime,
    trusted_owner_scope_ref: str,
    task_id: UUID,
    request_unit_id: UUID,
    verified_order_target_ref: str,
    source_resource_ref: str,
    source_version: str,
    superseded_observation_refs: Sequence[UUID] = (),
) -> ShipmentFreshnessDecisionResult:
    """Decide freshness over the unique loaded current Observation closure."""

    observations = tuple(current_observations)
    if len(observations) > 1:
        raise ValueError("Shipment freshness requires at most one current Observation")
    if not observations:
        return decide_shipment_freshness(
            observation_present=False,
            trusted_freshness_now=trusted_freshness_now,
            valid_until=None,
            target_binding_matches=False,
            source_version_matches=False,
        )
    observation = observations[0]
    if observation.observation_id in set(superseded_observation_refs):
        raise ValueError("current Shipment Observation is superseded")
    trusted_freshness_now = require_utc(
        trusted_freshness_now,
        field_name="trusted_freshness_now",
    )
    if trusted_freshness_now < observation.observed_at:
        raise ValueError("trusted_freshness_now cannot precede observed_at")
    target_matches = (
        observation.private_owner_scope == trusted_owner_scope_ref
        and observation.task_id == task_id
        and observation.request_unit_id == request_unit_id
        and observation.verified_order_target_ref == verified_order_target_ref
        and observation.source_resource_ref == source_resource_ref
    )
    return decide_shipment_freshness(
        observation_present=True,
        trusted_freshness_now=trusted_freshness_now,
        valid_until=observation.valid_until,
        target_binding_matches=target_matches,
        source_version_matches=observation.source_version == source_version,
    )
