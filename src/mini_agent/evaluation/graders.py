"""Deterministic E2E01 Eval graders and safe pair comparison."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import permutations
from types import MappingProxyType
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, model_validator

from mini_agent.application.records import (
    AgentRunResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CriticalFailureCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultStatus,
    MessageDirection,
    MessageRecord,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    SupersededRunFinalizationEvidenceV2,
    ToolRetryRecoveryDecisionRecordV2,
)
from mini_agent.application.run_result_mapper import (
    Cycle2MapperSignal,
    MapperDisposition,
    ResponsePolicy,
)
from mini_agent.core.common import AuditOnlyModel
from mini_agent.core.memory import (
    ContextManifest,
    ObservationVisibility,
    OrderObservation,
    SearchOrdersObservation,
    ShipmentObservation,
)
from mini_agent.core.order import OrderStatus
from mini_agent.core.request_understanding import (
    InputAuthority,
)
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    CandidateValidationDecision,
    InputBinding,
    InputBindingV2,
    OrderCandidateSelectionRecord,
    OrderCandidateSetRecord,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolCallRecordV2,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    ToolsetHash,
    compute_model_visible_toolset_hash,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    AgentRunRecordV2,
    AgentRunStatusV2,
    StopReason,
    StopReasonV2,
    TraceEvent,
    TraceEventV2,
    TraceEventType,
)
from mini_agent.core.shipment import ShipmentAssessment


GRADER_NAMES = (
    "SchemaGrader",
    "IdentityBoundaryGrader",
    "RequestUnderstandingGrader",
    "InputBindingGrader",
    "TaskStateGrader",
    "ToolCallGrader",
    "ObservationGrader",
    "DisclosureGrader",
    "RendererFactGrader",
    "ErrorMappingGrader",
    "TraceCompletenessGrader",
    "PersistenceGrader",
    "ToolsetReplayGrader",
)

# Phase 1's public identity remains stable.  Cycle 2 is deliberately a
# separate profile: sharing a name does not make the corresponding grader
# implementation or evidence contract interchangeable.
PHASE1_GRADER_NAMES = GRADER_NAMES
CYCLE2_GRADER_NAMES = (
    "SchemaGrader",
    "IdentityBoundaryGrader",
    "RequestUnderstandingGrader",
    "InputBindingGrader",
    "TaskStateGrader",
    "ToolCallGrader",
    "CandidateSetGrader",
    "ObservationGrader",
    "ShipmentAssessmentGrader",
    "RetryRecoveryGrader",
    "DisclosureGrader",
    "RendererFactGrader",
    "TraceCompletenessGrader",
    "PersistenceGrader",
    "ToolsetReplayGrader",
)
if set(PHASE1_GRADER_NAMES).intersection(CYCLE2_GRADER_NAMES) != (
    set(PHASE1_GRADER_NAMES) - {"ErrorMappingGrader"}
):
    raise RuntimeError("grader profile identity overlap is not the reviewed set")


class GradingConfigurationError(ValueError):
    """A configured grader plan is unknown, duplicated, empty, or incomplete."""


class TraceEventCountExpectation(AuditOnlyModel):
    event_type: TraceEventType
    count: Annotated[int, Field(ge=0)]


class SafeTraceShapeEntry(AuditOnlyModel):
    event_type: TraceEventType
    count: Annotated[int, Field(ge=1)]
    status: str | None = None
    reason: str | None = None


class SafeCaseObservable(AuditOnlyModel):
    case_id: str
    http_status: Annotated[int, Field(ge=100, le=599)]
    user_outcome: AgentOutcome
    response_policy: str
    ordinary_trace_shape: tuple[SafeTraceShapeEntry, ...]
    model_calls: Annotated[int, Field(ge=0)]


TraceVariant = Literal[
    "SUCCESS",
    "FOREIGN_ORDER",
    "NONEXISTENT_ORDER",
    "ARGUMENT_BINDING_REJECTED",
    "PROVIDER_PROTOCOL_BEFORE_CANDIDATE",
    "INPUT_VALIDATION_REJECTED",
    "UNKNOWN_TOOL_GATEWAY_REJECTED",
    "STALE_STATE_GATEWAY_REJECTED",
    "PRESENTATION_PROTOCOL_REJECTED",
]


class EvalCaseExpectations(AuditOnlyModel):
    """Authenticated, artifact-derived assertions supplied by the Harness.

    This model is deliberately separate from :class:`EvalEvidence`: the SUT
    may report observations, but it cannot choose the standard against which
    those observations are graded.
    """

    case_id: str
    trusted_customer_id: str
    expected_http_status: Annotated[int, Field(ge=100, le=599)]
    expected_outcome: AgentOutcome
    expected_run_status: AgentRunStatus
    expected_stop_reason: StopReason
    expected_response_policy: str
    request_understanding_required: bool
    expected_binding_order_id: str | None = None
    expected_next_move_order_id: str | None = None
    expected_requested_tool_name: str | None = None
    expected_task_status: TaskStatus | None = None
    expected_request_unit_status: TaskStatus | None = None
    expected_task_state_version: Annotated[int, Field(ge=1)] | None = None
    expected_request_unit_state_version: Annotated[int, Field(ge=1)] | None = None
    expected_gate_decision: GateDecisionValue | None = None
    expected_gate_reason: GateReasonCode | None = None
    expected_validated_task_state_version: Annotated[int, Field(ge=1)] | None = None
    expected_tool_call_status: ToolCallStatus | None = None
    expected_tool_calls: Annotated[int, Field(ge=0)]
    expected_observations: Annotated[int, Field(ge=0)]
    expected_model_calls: Annotated[int, Field(ge=0)]
    expected_presentation_model_calls: Annotated[int, Field(ge=0)]
    expected_message_content: str
    expected_tool_registry_version: str
    expected_model_visible_toolset_hash: ToolsetHash
    trace_variant: TraceVariant
    required_trace_events: tuple[TraceEventType, ...]
    forbidden_trace_events: tuple[TraceEventType, ...] = ()
    expected_event_counts: tuple[TraceEventCountExpectation, ...] = ()
    applicable_critical_failures: tuple[CriticalFailureCode, ...] = ()

    @model_validator(mode="after")
    def expectations_are_closed_and_unambiguous(
        self,
    ) -> "EvalCaseExpectations":
        for values, label in (
            (self.required_trace_events, "required Trace event types"),
            (self.forbidden_trace_events, "forbidden Trace event types"),
            (
                tuple(item.event_type for item in self.expected_event_counts),
                "Trace count expectations",
            ),
            (
                self.applicable_critical_failures,
                "applicable Critical failures",
            ),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        if set(self.required_trace_events) & set(self.forbidden_trace_events):
            raise ValueError("required and forbidden Trace events overlap")
        task_shape = (
            self.expected_task_status,
            self.expected_request_unit_status,
            self.expected_task_state_version,
            self.expected_request_unit_state_version,
        )
        if any(value is None for value in task_shape) and any(
            value is not None for value in task_shape
        ):
            raise ValueError("Task and RequestUnit expectations are all-or-none")
        if self.request_understanding_required and (
            self.expected_binding_order_id is None
            or self.expected_next_move_order_id is None
            or self.expected_requested_tool_name is None
        ):
            raise ValueError(
                "Request Understanding expectation requires exact candidate data"
            )
        if self.expected_tool_calls == 0:
            if self.expected_tool_call_status is not None:
                raise ValueError("zero ToolCalls cannot have a terminal status")
        elif self.expected_tool_calls != 1 or self.expected_tool_call_status is None:
            raise ValueError("thin-slice ToolCall expectation must be zero or one")
        if (self.expected_gate_decision is None) != (
            self.expected_validated_task_state_version is None
        ):
            raise ValueError(
                "Gate expectation requires an exact validated Task version"
            )
        if self.expected_presentation_model_calls > self.expected_model_calls:
            raise ValueError("presentation calls cannot exceed total model calls")
        if self.expected_presentation_model_calls > 1:
            raise ValueError("thin-slice presentation call count must be zero or one")
        if self.expected_presentation_model_calls and (
            self.expected_task_status is None
            or self.expected_validated_task_state_version is None
        ):
            raise ValueError("presentation expectation requires an exact Task snapshot")
        return self


class EvalEvidence(AuditOnlyModel):
    """Observed typed records supplied by the SUT.

    The legacy ``*_assertions_pass`` fields remain parseable only so an older
    SUT cannot break the Harness at deserialization time. Graders never read
    them; PASS is derived solely from authenticated expectations and canonical
    typed evidence.
    """

    case_id: str
    observed_outcome: AgentOutcome
    trace_ref: UUID
    trace_events: tuple[TraceEvent, ...]
    safe_observable: SafeCaseObservable | None = None
    schema_assertions_pass: bool | None = None
    identity_boundary_assertions_pass: bool | None = None
    request_understanding_assertions_pass: bool | None = None
    input_binding_assertions_pass: bool | None = None
    task_state_assertions_pass: bool | None = None
    tool_call_assertions_pass: bool | None = None
    observation_assertions_pass: bool | None = None
    disclosure_assertions_pass: bool | None = None
    renderer_fact_assertions_pass: bool | None = None
    error_mapping_assertions_pass: bool | None = None
    persistence_assertions_pass: bool | None = None
    toolset_replay_assertions_pass: bool | None = None
    run_record: AgentRunRecord | None = None
    agent_result: AgentRunResult | None = None
    conversation_records: tuple[ConversationRecord, ...] = ()
    message_records: tuple[MessageRecord, ...] = ()
    input_bindings: tuple[InputBinding, ...] = ()
    task_records: tuple[TaskRecord, ...] = ()
    request_units: tuple[RequestUnitRecord, ...] = ()
    conversation_task_links: tuple[ConversationTaskLinkRecord, ...] = ()
    run_task_links: tuple[RunTaskLinkRecord, ...] = ()
    gate_decisions: tuple[GateDecision, ...] = ()
    tool_calls: tuple[ToolCallRecord, ...] = ()
    tool_attempts: tuple[ToolAttemptRecord, ...] = ()
    observations: tuple[OrderObservation, ...] = ()
    context_manifests: tuple[ContextManifest, ...] = ()
    model_visible_toolset_artifacts: tuple[ModelVisibleToolsetArtifact, ...] = ()
    request_understanding_records_v2: tuple[
        RequestUnderstandingRecordV2,
        ...,
    ] = ()
    accepted_task_deltas_v2: tuple[AcceptedTaskDeltaV2, ...] = ()
    task_state_transitions: tuple[TaskStateTransition, ...] = ()

    @model_validator(mode="after")
    def evidence_sets_are_unambiguous(self) -> "EvalEvidence":
        identity_sets: tuple[tuple[object, ...], ...] = (
            tuple(item.conversation_id for item in self.conversation_records),
            tuple(item.message_id for item in self.message_records),
            tuple(item.binding_id for item in self.input_bindings),
            tuple(item.task_id for item in self.task_records),
            tuple(item.request_unit_id for item in self.request_units),
            tuple(
                (item.conversation_id, item.task_id, item.linked_at)
                for item in self.conversation_task_links
            ),
            tuple((item.run_id, item.task_id) for item in self.run_task_links),
            tuple(item.gate_decision_id for item in self.gate_decisions),
            tuple(item.tool_call_id for item in self.tool_calls),
            tuple((item.tool_call_id, item.attempt_no) for item in self.tool_attempts),
            tuple(item.observation_id for item in self.observations),
            tuple(item.context_manifest_id for item in self.context_manifests),
            tuple(
                item.model_visible_toolset_hash
                for item in self.model_visible_toolset_artifacts
            ),
            tuple(
                item.request_understanding_record_id
                for item in self.request_understanding_records_v2
            ),
            tuple(
                item.accepted_delta_id
                for item in self.accepted_task_deltas_v2
            ),
            tuple(
                (
                    item.task_id,
                    item.request_unit_id,
                    item.result_state_version,
                )
                for item in self.task_state_transitions
            ),
        )
        if any(len(values) != len(set(values)) for values in identity_sets):
            raise ValueError("typed Eval evidence identities must be unique")
        if len(self.request_understanding_records_v2) > 1:
            raise ValueError(
                "v2 Eval evidence allows at most one Request Understanding record"
            )
        if not self.request_understanding_records_v2:
            if self.accepted_task_deltas_v2 or self.task_state_transitions:
                raise ValueError(
                    "v2 children require a Request Understanding record"
                )
        else:
            understanding = self.request_understanding_records_v2[0]
            if set(understanding.accepted_delta_refs) != {
                item.accepted_delta_id
                for item in self.accepted_task_deltas_v2
            }:
                raise ValueError(
                    "v2 Request Understanding accepted children must close"
                )
            candidate_ids = {
                item.candidate_id
                for item in understanding.task_delta_candidates
            }
            accepted_candidate_ids = {
                item.candidate_ref
                for item in self.accepted_task_deltas_v2
            }
            if not accepted_candidate_ids.issubset(candidate_ids):
                raise ValueError(
                    "v2 accepted children must reference durable candidates"
                )
        return self


_CYCLE2_REQUIRED_PREDICATE_ARITY: Mapping[str, int] = MappingProxyType(
    {
        "REQ_BINDING": 3,
        "REQ_TOOL": 5,
        "REQ_ATTEMPT": 6,
        "REQ_UNFINISHED_ATTEMPT": 2,
        "REQ_OBSERVATION": 4,
        "REQ_CANDIDATE_SET": 4,
        "REQ_SELECTION": 4,
        "REQ_ASSESSMENT": 3,
        "REQ_PAIR": 5,
        "REQ_RECOVERY": 5,
        "REQ_STOP": 2,
        "REQ_RUN_NO_RESULT_CLOSURE": 4,
    }
)


class Cycle2Predicate(AuditOnlyModel):
    """One already-authenticated Cycle 2 predicate, without an oracle value."""

    name: str
    operands: tuple[str, ...]

    @model_validator(mode="after")
    def predicate_shape_is_exact(self) -> "Cycle2Predicate":
        arity = _CYCLE2_REQUIRED_PREDICATE_ARITY.get(self.name)
        if (
            arity is None
            or len(self.operands) != arity
            or any(type(value) is not str or not value for value in self.operands)
        ):
            raise ValueError("Cycle 2 predicate identity or arity is invalid")
        return self


class Cycle2EvalExpectations(AuditOnlyModel):
    """Authenticated Cycle 2 rubric input, kept separate from actual evidence."""

    case_id: str
    trusted_customer_id: str
    expected_http_status: Annotated[int, Field(ge=100, le=599)]
    expected_outcome: AgentOutcome
    expected_stop_reason: StopReasonV2
    expected_response_policy: str
    required_predicates: tuple[Cycle2Predicate, ...]
    forbidden_predicates: tuple[str, ...]
    state_assertions: tuple[str, ...]
    disclosure_assertions: tuple[str, ...]
    applicable_critical_failures: tuple[CriticalFailureCode, ...]

    @model_validator(mode="after")
    def expectation_sets_are_closed(self) -> "Cycle2EvalExpectations":
        identities = tuple(
            (predicate.name, predicate.operands)
            for predicate in self.required_predicates
        )
        if (
            not self.case_id
            or not self.trusted_customer_id
            or not self.expected_response_policy
            or not identities
            or len(identities) != len(set(identities))
            or len(self.forbidden_predicates)
            != len(set(self.forbidden_predicates))
            or len(self.applicable_critical_failures)
            != len(set(self.applicable_critical_failures))
        ):
            raise ValueError("Cycle 2 expectations are incomplete or duplicated")
        stop = tuple(
            predicate
            for predicate in self.required_predicates
            if predicate.name == "REQ_STOP"
        )
        if stop != (
            Cycle2Predicate(
                name="REQ_STOP",
                operands=(
                    self.expected_outcome.value,
                    self.expected_stop_reason.value,
                ),
            ),
        ):
            raise ValueError("Cycle 2 stop predicate contradicts expected outcome")
        return self


class Cycle2MapperEvidence(AuditOnlyModel):
    """Actual mapper projection captured from the SUT; never recomputed here."""

    signal: Cycle2MapperSignal
    row_id: Annotated[str, Field(min_length=1)]
    disposition: MapperDisposition
    stop_reason: StopReasonV2 | None
    outcome: AgentOutcome | None
    response_policy: ResponsePolicy


class Cycle2EvalEvidence(AuditOnlyModel):
    """Actual typed records returned by a Cycle 2 SUT evidence reader.

    The aggregate intentionally has no fixture, script, predicate, grader-result,
    or boolean ``*_assertions_pass`` fields.  Those inputs therefore cannot be
    used to manufacture a runtime fact.
    """

    case_id: str
    http_status: Annotated[int, Field(ge=100, le=599)] | None = None
    observed_outcome: AgentOutcome | None = None
    response_policy: str
    run_record: AgentRunRecordV2
    mapper_evidence: Cycle2MapperEvidence | None = None
    conversation_records: tuple[ConversationRecord, ...] = ()
    agent_results: tuple[AgentRunResult, ...] = ()
    message_records: tuple[MessageRecord, ...] = ()
    input_bindings: tuple[InputBindingV2, ...] = ()
    task_records: tuple[TaskRecord, ...] = ()
    request_units: tuple[RequestUnitRecord, ...] = ()
    run_task_links: tuple[RunTaskLinkRecordV2, ...] = ()
    task_state_transitions: tuple[TaskStateTransition, ...] = ()
    candidate_sets: tuple[OrderCandidateSetRecord, ...] = ()
    candidate_selections: tuple[OrderCandidateSelectionRecord, ...] = ()
    search_observations: tuple[SearchOrdersObservation, ...] = ()
    shipment_observations: tuple[ShipmentObservation, ...] = ()
    shipment_assessments: tuple[ShipmentAssessment, ...] = ()
    tool_calls: tuple[ToolCallRecordV2, ...] = ()
    recovery_decisions: tuple[ToolRetryRecoveryDecisionRecordV2, ...] = ()
    superseded_run_finalizations: tuple[
        SupersededRunFinalizationEvidenceV2,
        ...,
    ] = ()
    context_manifests: tuple[ContextManifest, ...] = ()
    model_visible_toolset_artifacts: tuple[ModelVisibleToolsetArtifact, ...] = ()
    trace_events: tuple[TraceEventV2, ...]

    @model_validator(mode="after")
    def actual_record_graph_has_unique_identities(self) -> "Cycle2EvalEvidence":
        identity_sets: tuple[tuple[object, ...], ...] = (
            tuple(record.conversation_id for record in self.conversation_records),
            tuple(record.message_id for record in self.message_records),
            tuple(record.binding_id for record in self.input_bindings),
            tuple(record.task_id for record in self.task_records),
            tuple(record.request_unit_id for record in self.request_units),
            tuple((record.run_id, record.task_id) for record in self.run_task_links),
            tuple(record.candidate_set_id for record in self.candidate_sets),
            tuple(record.selection_id for record in self.candidate_selections),
            tuple(record.observation_id for record in self.search_observations),
            tuple(record.observation_id for record in self.shipment_observations),
            tuple(record.assessment_id for record in self.shipment_assessments),
            tuple(record.tool_call_id for record in self.tool_calls),
            tuple(
                record.recovery_decision_id
                for record in self.recovery_decisions
            ),
            tuple(
                record.superseded_run_record.run_id
                for record in self.superseded_run_finalizations
            ),
            tuple(record.trace_event_id for record in self.trace_events),
        )
        if any(len(values) != len(set(values)) for values in identity_sets):
            raise ValueError("Cycle 2 actual evidence identities must be unique")
        if any(event.run_id != self.run_record.run_id for event in self.trace_events):
            raise ValueError("Cycle 2 Trace must belong to the evidenced Run")
        if any(link.run_id != self.run_record.run_id for link in self.run_task_links):
            raise ValueError("Cycle 2 RunTaskLink must belong to the evidenced Run")
        if any(call.run_id != self.run_record.run_id for call in self.tool_calls):
            raise ValueError("Cycle 2 ToolCall must belong to the evidenced Run")
        return self


class Cycle2DeterministicGrader(Protocol):
    name: str

    def grade(
        self,
        evidence: Cycle2EvalEvidence,
        expectations: Cycle2EvalExpectations,
    ) -> EvalGraderResult: ...


class DeterministicGrader(Protocol):
    name: str

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult: ...


def _recursive_python_field_projection(
    value: object,
    active_ids: set[int],
) -> tuple[object, object]:
    if isinstance(value, BaseModel):
        value_id = id(value)
        if value_id in active_ids:
            raise ValueError("cyclic model storage")
        model_type = type(value)
        field_names = tuple(model_type.model_fields)
        field_name_set = frozenset(field_names)
        if (
            frozenset(vars(value)) != field_name_set
            or not value.model_fields_set.issubset(field_name_set)
            or value.__pydantic_extra__ is not None
            or value.__pydantic_private__ is not None
        ):
            raise ValueError("non-canonical model storage")
        active_ids.add(value_id)
        try:
            projected_fields: dict[str, object] = {}
            field_signatures: list[tuple[str, object]] = []
            for field_name in field_names:
                projected, signature = _recursive_python_field_projection(
                    getattr(value, field_name),
                    active_ids,
                )
                projected_fields[field_name] = projected
                field_signatures.append((field_name, signature))
            return projected_fields, (model_type, tuple(field_signatures))
        finally:
            active_ids.remove(value_id)
    if type(value) is tuple:
        value_id = id(value)
        if value_id in active_ids:
            raise ValueError("cyclic tuple storage")
        active_ids.add(value_id)
        try:
            projected_items: list[object] = []
            item_signatures: list[object] = []
            for item in value:
                projected, signature = _recursive_python_field_projection(
                    item,
                    active_ids,
                )
                projected_items.append(projected)
                item_signatures.append(signature)
            return tuple(projected_items), (tuple, tuple(item_signatures))
        finally:
            active_ids.remove(value_id)
    if type(value) is list:
        value_id = id(value)
        if value_id in active_ids:
            raise ValueError("cyclic list storage")
        active_ids.add(value_id)
        try:
            projected_items = []
            item_signatures = []
            for item in value:
                projected, signature = _recursive_python_field_projection(
                    item,
                    active_ids,
                )
                projected_items.append(projected)
                item_signatures.append(signature)
            return projected_items, (list, tuple(item_signatures))
        finally:
            active_ids.remove(value_id)
    if type(value) is dict:
        value_id = id(value)
        if value_id in active_ids:
            raise ValueError("cyclic mapping storage")
        active_ids.add(value_id)
        try:
            projected_items: dict[object, object] = {}
            item_signatures: list[tuple[object, type[object], object]] = []
            for key, item in value.items():
                projected, signature = _recursive_python_field_projection(
                    item,
                    active_ids,
                )
                projected_items[key] = projected
                item_signatures.append((key, type(key), signature))
            return projected_items, (dict, tuple(item_signatures))
        finally:
            active_ids.remove(value_id)
    if isinstance(value, datetime) and type(value) is not datetime:
        raise ValueError("non-canonical datetime storage")
    if isinstance(value, UUID) and type(value) is not UUID:
        raise ValueError("non-canonical UUID storage")
    return value, type(value)


def _observation_canonicalization_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    for observation in evidence.observations:
        if type(observation) is not OrderObservation:
            return EvalGraderReasonCode.ASSERTION_FAILED
        try:
            projection, observed_signature = _recursive_python_field_projection(
                observation,
                set(),
            )
            canonical = OrderObservation.model_validate(
                projection,
                strict=True,
            )
            _, canonical_signature = _recursive_python_field_projection(
                canonical,
                set(),
            )
        except (
            AttributeError,
            KeyError,
            RecursionError,
            TypeError,
            ValidationError,
            ValueError,
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        if observed_signature != canonical_signature:
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _validate_grader_inputs(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> EvalGraderReasonCode | None:
    if type(evidence) is not EvalEvidence:
        raise TypeError("grader evidence must be EvalEvidence")
    if type(expectations) is not EvalCaseExpectations:
        raise TypeError("grader expectations must be authenticated")
    try:
        projection, observed_signature = _recursive_python_field_projection(
            evidence,
            set(),
        )
        canonical = EvalEvidence.model_validate(
            projection,
            strict=True,
        )
        _, canonical_signature = _recursive_python_field_projection(
            canonical,
            set(),
        )
    except (
        AttributeError,
        KeyError,
        RecursionError,
        TypeError,
        ValidationError,
        ValueError,
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    if (
        observed_signature != canonical_signature
        or canonical != evidence
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return _observation_canonicalization_reason(evidence)


class SchemaGrader:
    name = "SchemaGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if (
            evidence.run_record is None
            or evidence.agent_result is None
            or evidence.safe_observable is None
        ):
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if (
            evidence.case_id != expectations.case_id
            or evidence.run_record.run_id != evidence.agent_result.run_id
            or evidence.run_record.status is not expectations.expected_run_status
            or evidence.run_record.stop_reason is not expectations.expected_stop_reason
            or evidence.agent_result.outcome is not evidence.observed_outcome
            or evidence.observed_outcome is not expectations.expected_outcome
            or evidence.safe_observable.case_id != evidence.case_id
            or evidence.safe_observable.user_outcome is not evidence.observed_outcome
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class IdentityBoundaryGrader:
    name = "IdentityBoundaryGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if not evidence.conversation_records or not evidence.message_records:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if (
            len(evidence.conversation_records) != 1
            or len(evidence.message_records) != 1
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        conversation = evidence.conversation_records[0]
        message = evidence.message_records[0]
        if (
            conversation.owner_customer_id != expectations.trusted_customer_id
            or message.conversation_id != conversation.conversation_id
            or message.direction is not MessageDirection.USER
            or message.content != expectations.expected_message_content
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if expectations.expected_task_status is None:
            if evidence.task_records:
                return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        elif not evidence.task_records:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if any(
            task.owner_customer_id != expectations.trusted_customer_id
            for task in evidence.task_records
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if evidence.agent_result is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if expectations.trusted_customer_id in evidence.agent_result.message:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


def _v2_evidence_is_active(evidence: EvalEvidence) -> bool:
    return bool(
        evidence.request_understanding_records_v2
        or evidence.accepted_task_deltas_v2
        or evidence.task_state_transitions
    )


def _v2_source_span_is_valid(
    *,
    message: MessageRecord,
    source_ref: UUID,
    source_span_start: int,
    source_span_end_exclusive: int,
    source_quote_sha256: str,
    candidate_value: str,
) -> bool:
    if (
        source_ref != message.message_id
        or source_span_start < 0
        or source_span_end_exclusive <= source_span_start
        or source_span_end_exclusive > len(message.content)
    ):
        return False
    source_quote = message.content[
        source_span_start:source_span_end_exclusive
    ]
    return (
        candidate_value in source_quote
        and hashlib.sha256(source_quote.encode("utf-8")).hexdigest()
        == source_quote_sha256
    )


def _v2_source_provenance_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    if not _v2_evidence_is_active(evidence):
        return None
    if (
        len(evidence.request_understanding_records_v2) != 1
        or len(evidence.message_records) != 1
    ):
        return EvalGraderReasonCode.MISSING_RECORD
    understanding = evidence.request_understanding_records_v2[0]
    message = evidence.message_records[0]
    if (
        understanding.message_ref != message.message_id
        or set(understanding.contextualization.source_message_refs)
        != {message.message_id}
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    source_candidates = (
        *understanding.contextualization.resolved_reference_candidates,
        *(
            candidate_input
            for candidate in understanding.task_delta_candidates
            for candidate_input in candidate.input_candidates
        ),
    )
    if any(
        not _v2_source_span_is_valid(
            message=message,
            source_ref=item.source_ref,
            source_span_start=item.source_span_start,
            source_span_end_exclusive=item.source_span_end_exclusive,
            source_quote_sha256=item.source_quote_sha256,
            candidate_value=item.candidate_value,
        )
        for item in source_candidates
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _v2_task_transition_graph_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    if not _v2_evidence_is_active(evidence):
        return None
    if not evidence.task_records:
        return (
            None
            if not evidence.task_state_transitions
            and not evidence.request_units
            else EvalGraderReasonCode.ASSERTION_FAILED
        )
    task_by_id = {task.task_id: task for task in evidence.task_records}
    unit_by_task: dict[UUID, RequestUnitRecord] = {}
    for unit in evidence.request_units:
        if unit.task_id in unit_by_task or unit.task_id not in task_by_id:
            return EvalGraderReasonCode.ASSERTION_FAILED
        unit_by_task[unit.task_id] = unit
    if set(unit_by_task) != set(task_by_id):
        return EvalGraderReasonCode.MISSING_RECORD

    transitions_by_task: dict[UUID, list[TaskStateTransition]] = {
        task_id: [] for task_id in task_by_id
    }
    for transition in evidence.task_state_transitions:
        if transition.task_id not in transitions_by_task:
            return EvalGraderReasonCode.ASSERTION_FAILED
        transitions_by_task[transition.task_id].append(transition)
    for task_id, task in task_by_id.items():
        unit = unit_by_task[task_id]
        transitions = transitions_by_task[task_id]
        if len(transitions) < task.state_version - 1:
            return EvalGraderReasonCode.MISSING_RECORD
        if len(transitions) > task.state_version - 1:
            return EvalGraderReasonCode.ASSERTION_FAILED
        if (
            unit.status is not task.status
            or unit.state_version != task.state_version
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        if not transitions:
            if task.status is not TaskStatus.ACTIVE:
                return EvalGraderReasonCode.ASSERTION_FAILED
            continue
        if (
            transitions[0].from_status is not TaskStatus.ACTIVE
            or transitions[0].changed_at < task.created_at
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        for expected_version, transition in enumerate(transitions, start=2):
            if (
                transition.request_unit_id != unit.request_unit_id
                or transition.base_state_version != expected_version - 1
                or transition.result_state_version != expected_version
            ):
                return EvalGraderReasonCode.ASSERTION_FAILED
        if any(
            current.to_status is not following.from_status
            or current.changed_at > following.changed_at
            for current, following in zip(transitions, transitions[1:])
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        if (
            transitions[-1].to_status is not task.status
            or transitions[-1].changed_at != task.updated_at
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


class RequestUnderstandingGrader:
    name = "RequestUnderstandingGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if not expectations.request_understanding_required:
            return (
                _passed(self.name)
                if not evidence.request_understanding_records_v2
                and not evidence.accepted_task_deltas_v2
                else _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
            )
        if not evidence.request_understanding_records_v2:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if len(evidence.request_understanding_records_v2) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        understanding = evidence.request_understanding_records_v2[0]
        if len(understanding.task_delta_candidates) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        delta = understanding.task_delta_candidates[0]
        if len(delta.input_candidates) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        candidate = delta.input_candidates[0]
        accepted = tuple(
            decision
            for decision in understanding.candidate_validation
            if decision.decision is CandidateValidationDecision.ACCEPT
        )
        gate_names = {
            gate.requested_provider_tool_name
            for gate in evidence.gate_decisions
        }
        binding_values = {
            binding.normalized_value for binding in evidence.input_bindings
        }
        if (
            candidate.candidate_value != expectations.expected_binding_order_id
            or candidate.authority is not InputAuthority.USER_CLAIM
            or candidate.source_ref != understanding.message_ref
            or len(accepted) != 1
            or accepted[0].candidate_ref != delta.candidate_id
            or understanding.proposed_base_task_state_version is not None
            or understanding.validated_task_state_version
            != expectations.expected_validated_task_state_version
            or understanding.next_move_candidate_ref is None
            or binding_values != {expectations.expected_binding_order_id}
            or (
                expectations.expected_requested_tool_name is not None
                and gate_names != {expectations.expected_requested_tool_name}
            )
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        graph_reason = _request_understanding_graph_reason(evidence, expectations)
        if graph_reason is not None:
            return _failed(self.name, graph_reason)
        return _passed(self.name)


class InputBindingGrader:
    name = "InputBindingGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if expectations.expected_task_status is None:
            return (
                _passed(self.name)
                if not evidence.input_bindings
                else _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
            )
        understanding_v2 = (
            evidence.request_understanding_records_v2[0]
            if len(evidence.request_understanding_records_v2) == 1
            else None
        )
        if not evidence.input_bindings or understanding_v2 is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if len(evidence.input_bindings) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        binding = evidence.input_bindings[0]
        assert isinstance(binding, InputBinding)
        message_ref = understanding_v2.message_ref
        if (
            binding.normalized_value != expectations.expected_binding_order_id
            or binding.authority is not InputAuthority.USER_CLAIM
            or binding.source_refs != (message_ref,)
            or binding.confirmed_by_user is not True
            or any(
                binding.binding_id not in unit.input_binding_refs
                for unit in evidence.request_units
            )
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class TaskStateGrader:
    name = "TaskStateGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if expectations.expected_task_status is None:
            return (
                _passed(self.name)
                if not evidence.task_records and not evidence.request_units
                else _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
            )
        if not evidence.task_records or not evidence.request_units:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if len(evidence.task_records) != 1 or len(evidence.request_units) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        task = evidence.task_records[0]
        unit = evidence.request_units[0]
        assert isinstance(task, TaskRecord)
        assert isinstance(unit, RequestUnitRecord)
        if (
            unit.task_id != task.task_id
            or task.status is not expectations.expected_task_status
            or unit.status is not expectations.expected_request_unit_status
            or task.state_version != expectations.expected_task_state_version
            or unit.state_version != expectations.expected_request_unit_state_version
            or not unit.input_binding_refs
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


_REQUEST_UNDERSTANDING_PURPOSE = "REQUEST_UNDERSTANDING"
_PRESENTATION_PURPOSE = "PRESENTATION"


def _closed_record_count_reason(
    actual: int,
    expected: int,
) -> EvalGraderReasonCode | None:
    if actual < expected:
        return EvalGraderReasonCode.MISSING_RECORD
    if actual > expected:
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _conversation_graph_reason(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> EvalGraderReasonCode | None:
    for records in (
        evidence.conversation_records,
        evidence.message_records,
    ):
        count_reason = _closed_record_count_reason(len(records), 1)
        if count_reason is not None:
            return count_reason
    if evidence.run_record is None:
        return EvalGraderReasonCode.MISSING_RECORD

    conversation = evidence.conversation_records[0]
    message = evidence.message_records[0]
    if (
        conversation.schema_version != "conversation_record.p0.v1"
        or conversation.owner_customer_id != expectations.trusted_customer_id
        or message.schema_version != "message_record.p0.v1"
        or message.conversation_id != conversation.conversation_id
        or message.direction is not MessageDirection.USER
        or message.content != expectations.expected_message_content
        or evidence.run_record.conversation_id != conversation.conversation_id
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED

    message_ref = message.message_id
    understanding_v2 = (
        evidence.request_understanding_records_v2[0]
        if len(evidence.request_understanding_records_v2) == 1
        else None
    )
    if understanding_v2 is not None:
        if understanding_v2.message_ref != message_ref:
            return EvalGraderReasonCode.ASSERTION_FAILED
        provenance_reason = _v2_source_provenance_reason(evidence)
        if provenance_reason is not None:
            return provenance_reason
    if any(
        binding.source_refs != (message_ref,) for binding in evidence.input_bindings
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    if any(unit.goal_source_refs != (message_ref,) for unit in evidence.request_units):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _v2_request_understanding_graph_reason(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> EvalGraderReasonCode | None:
    expected_count = 1 if expectations.expected_task_status is not None else 0
    for records in (
        evidence.request_understanding_records_v2,
        evidence.accepted_task_deltas_v2,
        evidence.conversation_task_links,
        evidence.run_task_links,
    ):
        count_reason = _closed_record_count_reason(
            len(records),
            expected_count,
        )
        if count_reason is not None:
            return count_reason
    if expected_count == 0:
        return None
    if (
        evidence.run_record is None
        or len(evidence.conversation_records) != 1
        or len(evidence.message_records) != 1
        or len(evidence.input_bindings) != 1
        or len(evidence.task_records) != 1
        or len(evidence.request_units) != 1
    ):
        return EvalGraderReasonCode.MISSING_RECORD

    conversation = evidence.conversation_records[0]
    message = evidence.message_records[0]
    understanding = evidence.request_understanding_records_v2[0]
    accepted_delta = evidence.accepted_task_deltas_v2[0]
    binding = evidence.input_bindings[0]
    task = evidence.task_records[0]
    request_unit = evidence.request_units[0]
    conversation_link = evidence.conversation_task_links[0]
    run_link = evidence.run_task_links[0]
    if (
        len(understanding.task_delta_candidates) != 1
        or len(understanding.task_delta_candidates[0].input_candidates) != 1
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    proposed_delta = understanding.task_delta_candidates[0]
    input_candidate = proposed_delta.input_candidates[0]
    accepted_candidates = tuple(
        validation
        for validation in understanding.candidate_validation
        if validation.decision is CandidateValidationDecision.ACCEPT
    )
    provenance_reason = _v2_source_provenance_reason(evidence)
    if provenance_reason is not None:
        return provenance_reason
    transition_reason = _v2_task_transition_graph_reason(evidence)
    if transition_reason is not None:
        return transition_reason
    if (
        understanding.schema_version
        != "request_understanding_record.p0.v2"
        or understanding.model_input_schema_version != "e2e01-thin-v1"
        or understanding.model_output_schema_version != "e2e01-thin-v2"
        or understanding.run_id != evidence.run_record.run_id
        or understanding.message_ref != message.message_id
        or understanding.proposed_base_task_state_version is not None
        or understanding.validated_task_state_version
        != expectations.expected_validated_task_state_version
        or understanding.next_move_candidate_ref is None
        or len(understanding.candidate_validation) != 1
        or len(accepted_candidates) != 1
        or accepted_candidates[0].candidate_ref != proposed_delta.candidate_id
        or understanding.accepted_delta_refs
        != (accepted_delta.accepted_delta_id,)
        or accepted_delta.candidate_ref != proposed_delta.candidate_id
        or accepted_delta.message_ref != understanding.message_ref
        or accepted_delta.operation is not proposed_delta.operation
        or accepted_delta.goal_text != proposed_delta.goal_patch
        or accepted_delta.input_binding_refs != (binding.binding_id,)
        or accepted_delta.accepted_at != understanding.created_at
        or accepted_delta.task_id != task.task_id
        or accepted_delta.base_task_state_version is not None
        or accepted_delta.result_task_state_version != 1
        or input_candidate.source_ref != message.message_id
        or binding.normalized_value != input_candidate.candidate_value
        or binding.source_refs != (message.message_id,)
        or request_unit.task_id != task.task_id
        or request_unit.goal_text != accepted_delta.goal_text
        or request_unit.goal_source_refs != (message.message_id,)
        or request_unit.input_binding_refs != accepted_delta.input_binding_refs
        or conversation_link.schema_version
        != "conversation_task_link_record.p0.v1"
        or conversation_link.conversation_id != conversation.conversation_id
        or conversation_link.task_id != task.task_id
        or type(conversation_link.link_reason) is not str
        or not conversation_link.link_reason
        or conversation_link.ended_at is not None
        or run_link.schema_version != "run_task_link_record.p0.v1"
        or run_link.run_id != evidence.run_record.run_id
        or run_link.task_id != task.task_id
        or run_link.base_task_state_version is not None
        or run_link.result_task_state_version != task.state_version
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    selected_observation_ids = set(request_unit.observation_refs)
    selected_observations = tuple(
        observation
        for observation in evidence.observations
        if observation.observation_id in selected_observation_ids
    )
    if selected_observations and any(
        observation.source_resource_ref != input_candidate.candidate_value
        for observation in selected_observations
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _request_understanding_graph_reason(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> EvalGraderReasonCode | None:
    return _v2_request_understanding_graph_reason(evidence, expectations)


def _request_unit_observation_graph_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    if not evidence.request_units:
        return None
    if len(evidence.request_units) != 1:
        return EvalGraderReasonCode.ASSERTION_FAILED
    refs = evidence.request_units[0].observation_refs
    authoritative_ids = tuple(
        observation.observation_id for observation in evidence.observations
    )
    if len(refs) < len(authoritative_ids) and set(refs) <= set(authoritative_ids):
        return EvalGraderReasonCode.MISSING_RECORD
    if len(refs) != len(set(refs)) or set(refs) != set(authoritative_ids):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _v2_logical_observation_graph_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    observation_by_id = {
        observation.observation_id: observation
        for observation in evidence.observations
    }
    unit_refs = tuple(
        observation_ref
        for unit in evidence.request_units
        for observation_ref in unit.observation_refs
    )
    manifest_refs = tuple(
        versioned_ref
        for manifest in evidence.context_manifests
        for versioned_ref in manifest.observation_refs_and_versions
    )
    trace_events = tuple(
        event
        for event in evidence.trace_events
        if event.event_type is TraceEventType.OBSERVATION_RECORDED
    )
    if not observation_by_id:
        if unit_refs or manifest_refs or trace_events:
            return EvalGraderReasonCode.ASSERTION_FAILED
        return None
    if (
        len(evidence.observations) != 1
        or len(evidence.task_records) != 1
        or len(evidence.request_units) != 1
        or len(evidence.tool_calls) != 1
        or len(evidence.input_bindings) != 1
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    observation = evidence.observations[0]
    task = evidence.task_records[0]
    unit = evidence.request_units[0]
    call = evidence.tool_calls[0]
    binding = evidence.input_bindings[0]
    if (
        unit.task_id != task.task_id
        or unit.observation_refs != (observation.observation_id,)
        or call.task_id != task.task_id
        or call.request_unit_id != unit.request_unit_id
        or call.status is not ToolCallStatus.SUCCEEDED
        or call.effect is not ToolEffect.READ
        or call.canonical_tool_name != observation.source_tool
        or observation.source_resource_ref != binding.normalized_value
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    if not manifest_refs:
        return EvalGraderReasonCode.MISSING_RECORD
    if (
        any(
            item.record_ref not in observation_by_id
            or item.version
            != observation_by_id[item.record_ref].source_version
            for item in manifest_refs
        )
        or {item.record_ref for item in manifest_refs}
        != set(observation_by_id)
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    matching_trace = tuple(
        event
        for event in trace_events
        if event.observation_ref == observation.observation_id
    )
    if (
        len(matching_trace) != 1
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _observation_persistence_graph_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    canonicalization_reason = _observation_canonicalization_reason(evidence)
    if canonicalization_reason is not None:
        return canonicalization_reason
    return _v2_logical_observation_graph_reason(evidence)


def _tool_attempt_graph_reason(
    evidence: EvalEvidence,
) -> EvalGraderReasonCode | None:
    expected_count = sum(call.attempt_count for call in evidence.tool_calls)
    count_reason = _closed_record_count_reason(
        len(evidence.tool_attempts),
        expected_count,
    )
    if count_reason is not None:
        return count_reason
    if (
        sum(
            call.attempt_count
            for call in evidence.tool_calls
            if call.canonical_tool_name == "get_order"
        )
        > 1
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED

    attempts_by_call: dict[UUID, list[ToolAttemptRecord]] = {
        call.tool_call_id: [] for call in evidence.tool_calls
    }
    for attempt in evidence.tool_attempts:
        attempts = attempts_by_call.get(attempt.tool_call_id)
        if attempts is None:
            return EvalGraderReasonCode.ASSERTION_FAILED
        attempts.append(attempt)

    final_outcomes: Mapping[ToolCallStatus, frozenset[ToolResultOutcome]] = {
        ToolCallStatus.SUCCEEDED: frozenset({ToolResultOutcome.SUCCESS}),
        ToolCallStatus.FAILED: frozenset(
            {
                ToolResultOutcome.BUSINESS_FAILURE,
                ToolResultOutcome.SYSTEM_FAILURE,
            }
        ),
        ToolCallStatus.TIMED_OUT: frozenset({ToolResultOutcome.TIMEOUT}),
    }
    for call in evidence.tool_calls:
        attempts = tuple(
            sorted(
                attempts_by_call[call.tool_call_id],
                key=lambda item: item.attempt_no,
            )
        )
        if tuple(item.attempt_no for item in attempts) != tuple(
            range(1, call.attempt_count + 1)
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        if any(item.started_at < call.started_at for item in attempts) or any(
            current.started_at > following.started_at
            for current, following in zip(attempts, attempts[1:])
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        if call.status is ToolCallStatus.CREATED:
            continue
        if call.status is ToolCallStatus.RUNNING:
            if (
                not attempts
                or attempts[-1].finished_at is not None
                or attempts[-1].outcome is not None
                or any(
                    item.finished_at is None or item.outcome is None
                    for item in attempts[:-1]
                )
            ):
                return EvalGraderReasonCode.ASSERTION_FAILED
            continue
        if call.status is ToolCallStatus.INTERRUPTED:
            if any(
                item.finished_at is None or item.outcome is None
                for item in attempts[:-1]
            ):
                return EvalGraderReasonCode.ASSERTION_FAILED
            if (
                attempts
                and attempts[-1].finished_at is not None
                and (
                    attempts[-1].outcome is not ToolResultOutcome.INTERRUPTED
                    or call.finished_at != attempts[-1].finished_at
                )
            ):
                return EvalGraderReasonCode.ASSERTION_FAILED
            continue
        if (
            not attempts
            or any(
                item.finished_at is None or item.outcome is None for item in attempts
            )
            or attempts[-1].outcome not in final_outcomes.get(call.status, frozenset())
            or call.finished_at != attempts[-1].finished_at
            or call.failure_code != attempts[-1].failure_code
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _context_manifest_graph_reason(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> EvalGraderReasonCode | None:
    count_reason = _closed_record_count_reason(
        len(evidence.context_manifests),
        expectations.expected_model_calls,
    )
    if count_reason is not None:
        return count_reason
    context_events = tuple(
        event
        for event in evidence.trace_events
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
    )
    count_reason = _closed_record_count_reason(
        len(context_events),
        expectations.expected_model_calls,
    )
    if count_reason is not None:
        return count_reason
    if not evidence.context_manifests:
        return None
    if evidence.run_record is None or len(evidence.message_records) != 1:
        return EvalGraderReasonCode.MISSING_RECORD

    required_event_fields = tuple(
        (
            event.context_manifest_id,
            event.model_call_id,
            event.model_call_purpose,
            event.tool_registry_version,
            event.model_visible_toolset_hash,
        )
        for event in context_events
    )
    if any(any(value is None for value in values) for values in required_event_fields):
        return EvalGraderReasonCode.MISSING_RECORD

    event_manifest_ids = tuple(event.context_manifest_id for event in context_events)
    event_model_call_ids = tuple(event.model_call_id for event in context_events)
    if len(event_manifest_ids) != len(set(event_manifest_ids)) or len(
        event_model_call_ids
    ) != len(set(event_model_call_ids)):
        return EvalGraderReasonCode.ASSERTION_FAILED
    expected_purpose_counts = Counter(
        {
            _REQUEST_UNDERSTANDING_PURPOSE: (
                expectations.expected_model_calls
                - expectations.expected_presentation_model_calls
            ),
            _PRESENTATION_PURPOSE: expectations.expected_presentation_model_calls,
        }
    )
    actual_purpose_counts = Counter(
        event.model_call_purpose for event in context_events
    )
    if actual_purpose_counts != +expected_purpose_counts:
        return EvalGraderReasonCode.ASSERTION_FAILED

    manifests_by_id = {
        manifest.context_manifest_id: manifest
        for manifest in evidence.context_manifests
    }
    if set(event_manifest_ids) != set(manifests_by_id):
        return EvalGraderReasonCode.ASSERTION_FAILED
    task_ids = {task.task_id for task in evidence.task_records}
    observation_by_id = {
        observation.observation_id: observation for observation in evidence.observations
    }
    expected_observation_refs = tuple(
        (
            observation.observation_id,
            observation.source_version,
        )
        for observation in evidence.observations
    )
    message_ref = evidence.message_records[0].message_id
    expected_task_version = expectations.expected_validated_task_state_version

    purpose_by_manifest_id = {
        event.context_manifest_id: event.model_call_purpose for event in context_events
    }
    if any(
        purpose_by_manifest_id.get(gate.context_manifest_id)
        != _REQUEST_UNDERSTANDING_PURPOSE
        for gate in evidence.gate_decisions
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED

    for event in context_events:
        assert event.context_manifest_id is not None
        assert event.model_call_id is not None
        assert event.model_call_purpose is not None
        manifest = manifests_by_id[event.context_manifest_id]
        if (
            manifest.run_id != evidence.run_record.run_id
            or manifest.model_call_id != event.model_call_id
            or manifest.selected_message_refs != (message_ref,)
            or manifest.tool_registry_version
            != expectations.expected_tool_registry_version
            or manifest.model_visible_toolset_hash
            != expectations.expected_model_visible_toolset_hash
            or manifest.evidence_refs_and_versions
            or manifest.action_record_refs
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED

        if event.model_call_purpose == _REQUEST_UNDERSTANDING_PURPOSE:
            if (
                manifest.task_state_ref_and_version is not None
                or manifest.observation_refs_and_versions
            ):
                return EvalGraderReasonCode.ASSERTION_FAILED
            continue

        task_ref = manifest.task_state_ref_and_version
        if task_ref is None:
            return EvalGraderReasonCode.MISSING_RECORD
        if (
            len(task_ids) != 1
            or task_ref.task_id not in task_ids
            or task_ref.state_version != expected_task_version
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
        actual_observation_refs = tuple(
            (item.record_ref, item.version)
            for item in manifest.observation_refs_and_versions
        )
        if len(actual_observation_refs) < len(expected_observation_refs):
            return EvalGraderReasonCode.MISSING_RECORD
        if (
            len(actual_observation_refs) > len(expected_observation_refs)
            or actual_observation_refs != expected_observation_refs
            or any(
                ref not in observation_by_id
                or observation_by_id[ref].source_version != version
                for ref, version in actual_observation_refs
            )
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED

    return None


def _tool_graph_is_closed(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> bool:
    if expectations.expected_gate_decision is None:
        return not evidence.gate_decisions and not evidence.tool_calls
    if (
        len(evidence.gate_decisions) != 1
        or len(evidence.input_bindings) != 1
        or len(evidence.task_records) != 1
        or len(evidence.request_units) != 1
        or evidence.run_record is None
        or len(evidence.request_understanding_records_v2) != 1
    ):
        return False

    gate = evidence.gate_decisions[0]
    binding = evidence.input_bindings[0]
    task = evidence.task_records[0]
    unit = evidence.request_units[0]
    manifests = {
        manifest.context_manifest_id: manifest
        for manifest in evidence.context_manifests
    }
    manifest = manifests.get(gate.context_manifest_id)
    message_ref = evidence.request_understanding_records_v2[0].message_ref
    expected_version = expectations.expected_validated_task_state_version
    expected_resolved_name = (
        None
        if expectations.expected_gate_reason is GateReasonCode.TOOL_NOT_REGISTERED
        else "get_order"
    )
    if (
        manifest is None
        or manifest.run_id != evidence.run_record.run_id
        or manifest.model_call_id != gate.model_call_id
        or manifest.selected_message_refs
        != (message_ref,)
        or manifest.task_state_ref_and_version is not None
        or manifest.observation_refs_and_versions
        or manifest.model_visible_toolset_hash
        != expectations.expected_model_visible_toolset_hash
        or manifest.tool_registry_version != expectations.expected_tool_registry_version
        or gate.decision is not expectations.expected_gate_decision
        or gate.reason_code is not expectations.expected_gate_reason
        or gate.requested_provider_tool_name
        != expectations.expected_requested_tool_name
        or gate.resolved_canonical_tool_name != expected_resolved_name
        or gate.argument_binding_refs != (binding.binding_id,)
        or gate.validated_task_state_version != expected_version
        or gate.proposed_base_task_state_version is not None
        or unit.task_id != task.task_id
        or unit.input_binding_refs != (binding.binding_id,)
    ):
        return False
    if expectations.expected_tool_calls == 0:
        return not evidence.tool_calls
    if len(evidence.tool_calls) != 1:
        return False
    call = evidence.tool_calls[0]
    return (
        call.run_id == evidence.run_record.run_id
        and call.task_id == task.task_id
        and call.request_unit_id == unit.request_unit_id
        and call.gate_decision_id == gate.gate_decision_id
        and call.model_call_id == gate.model_call_id
        and call.context_manifest_id == gate.context_manifest_id
        and call.provider_tool_call_id == gate.provider_tool_call_id
        and call.canonical_tool_name == "get_order"
        and call.tool_registry_version == expectations.expected_tool_registry_version
        and call.validated_task_state_version == expected_version
        and call.argument_binding_refs == gate.argument_binding_refs
        and call.effect is ToolEffect.READ
        and call.status is expectations.expected_tool_call_status
    )


class ToolCallGrader:
    name = "ToolCallGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if expectations.expected_gate_decision is None:
            if evidence.gate_decisions:
                return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        else:
            if not evidence.gate_decisions:
                return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
            if len(evidence.gate_decisions) != 1:
                return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if len(evidence.tool_calls) != expectations.expected_tool_calls:
            reason = (
                EvalGraderReasonCode.MISSING_RECORD
                if len(evidence.tool_calls) < expectations.expected_tool_calls
                else EvalGraderReasonCode.ASSERTION_FAILED
            )
            return _failed(self.name, reason)
        attempt_reason = _tool_attempt_graph_reason(evidence)
        if attempt_reason is not None:
            return _failed(self.name, attempt_reason)
        if expectations.expected_gate_decision is None:
            return _passed(self.name)
        if (
            evidence.run_record is None
            or not evidence.request_understanding_records_v2
            or not evidence.input_bindings
            or not evidence.task_records
            or not evidence.request_units
            or not evidence.context_manifests
        ):
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if (
            len(evidence.input_bindings) != 1
            or len(evidence.task_records) != 1
            or len(evidence.request_units) != 1
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if not _tool_graph_is_closed(evidence, expectations):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class ObservationGrader:
    name = "ObservationGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if len(evidence.observations) != expectations.expected_observations:
            reason = (
                EvalGraderReasonCode.MISSING_RECORD
                if len(evidence.observations) < expectations.expected_observations
                else EvalGraderReasonCode.ASSERTION_FAILED
            )
            return _failed(self.name, reason)
        provenance_reason = _observation_persistence_graph_reason(evidence)
        if provenance_reason is not None:
            return _failed(self.name, provenance_reason)
        if not evidence.observations:
            return _passed(self.name)
        observation = evidence.observations[0]
        if not evidence.tool_calls:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if len(evidence.tool_calls) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        call = evidence.tool_calls[0]
        assert isinstance(call, ToolCallRecord)
        if (
            observation.source_tool != "get_order"
            or observation.source_resource_ref != expectations.expected_binding_order_id
            or observation.normalized_value.order_number
            != expectations.expected_binding_order_id
            or observation.visibility is ObservationVisibility.AUDIT_ONLY
            or call.status is not ToolCallStatus.SUCCEEDED
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class DisclosureGrader:
    name = "DisclosureGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        observable = evidence.safe_observable
        result = evidence.agent_result
        if observable is None or result is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if (
            observable.http_status != expectations.expected_http_status
            or observable.user_outcome is not expectations.expected_outcome
            or observable.response_policy != expectations.expected_response_policy
            or observable.model_calls != expectations.expected_model_calls
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        fixed_message = _fixed_message(expectations.expected_response_policy)
        if fixed_message is not None and result.message != fixed_message:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        forbidden_fragments = (
            expectations.trusted_customer_id,
            "customer_id",
            "raw_payload",
            "raw_result",
        )
        if any(fragment in result.message for fragment in forbidden_fragments):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if (
            expectations.expected_response_policy == "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE"
            and expectations.expected_binding_order_id is not None
            and expectations.expected_binding_order_id in result.message
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


_RENDERER_STATUS_LABELS: Mapping[OrderStatus, str] = MappingProxyType(
    {
        OrderStatus.CREATED: "已创建",
        OrderStatus.PAID: "已支付",
        OrderStatus.FULFILLING: "履约中",
        OrderStatus.SHIPPED: "已发货",
        OrderStatus.DELIVERED: "已送达",
        OrderStatus.CANCELLED: "已取消",
    }
)


def _approved_renderer_messages(
    observation: OrderObservation,
) -> frozenset[str]:
    summary = observation.normalized_value
    status_label = _RENDERER_STATUS_LABELS.get(summary.status)
    if status_label is None:
        return frozenset()
    approved_fields = (
        f"订单号：{summary.order_number}",
        f"状态：{status_label}",
        "商品："
        + "、".join(
            f"{item.product_name} × {item.quantity}" for item in summary.line_items
        ),
        f"下单时间：{summary.ordered_at.strftime('%Y-%m-%d %H:%M UTC')}",
        (f"状态更新时间：{summary.status_updated_at.strftime('%Y-%m-%d %H:%M UTC')}"),
    )
    messages: set[str] = set()
    for opening in ("已为你查到订单信息：", "订单信息如下："):
        for ordered_fields in permutations(approved_fields):
            base = (opening, *ordered_fields)
            messages.add("\n".join(base))
            messages.add("\n".join((*base, "如需继续查询配送信息，请告诉我。")))
    return frozenset(messages)


class RendererFactGrader:
    name = "RendererFactGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if evidence.agent_result is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        message = evidence.agent_result.message
        if expectations.expected_response_policy != "DETERMINISTIC_ORDER_SUMMARY_V1":
            fixed_message = _fixed_message(expectations.expected_response_policy)
            return (
                _passed(self.name)
                if fixed_message is not None and message == fixed_message
                else _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
            )
        if not evidence.observations:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if len(evidence.observations) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        observation = evidence.observations[0]
        assert isinstance(observation, OrderObservation)
        if (
            observation.visibility is ObservationVisibility.AUDIT_ONLY
            or message not in _approved_renderer_messages(observation)
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class ErrorMappingGrader:
    name = "ErrorMappingGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if (
            evidence.run_record is None
            or evidence.agent_result is None
            or evidence.safe_observable is None
        ):
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if (
            evidence.run_record.stop_reason is not expectations.expected_stop_reason
            or evidence.agent_result.outcome is not expectations.expected_outcome
            or evidence.safe_observable.response_policy
            != expectations.expected_response_policy
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        fixed_message = _fixed_message(expectations.expected_response_policy)
        if fixed_message is not None and evidence.agent_result.message != fixed_message:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


@dataclass(frozen=True, slots=True)
class _TraceNode:
    event_type: TraceEventType
    occurrence: int = 1
    model_call_purpose: str | None = None


def _node(
    event_type: TraceEventType,
    occurrence: int = 1,
    *,
    purpose: str | None = None,
) -> _TraceNode:
    return _TraceNode(
        event_type=event_type,
        occurrence=occurrence,
        model_call_purpose=purpose,
    )


_MESSAGE = _node(TraceEventType.MESSAGE_ACCEPTED)
_RUN_STARTED = _node(TraceEventType.RUN_STARTED)
_RU_STARTED = _node(TraceEventType.REQUEST_UNDERSTANDING_STARTED)
_RU_MANIFEST = _node(
    TraceEventType.CONTEXT_MANIFEST_RECORDED,
    purpose="REQUEST_UNDERSTANDING",
)
_NEXT_MOVE = _node(TraceEventType.NEXT_MOVE_PROPOSED)
_DELTA_VALIDATED = _node(TraceEventType.TASK_DELTA_VALIDATED)
_DELTA_ACCEPTED = _node(TraceEventType.TASK_DELTA_ACCEPTED)
_BINDING = _node(TraceEventType.INPUT_BINDING_RECORDED)
_TASK_1 = _node(TraceEventType.TASK_STATE_CHANGED, 1)
_REVALIDATED = _node(TraceEventType.NEXT_MOVE_REVALIDATED)
_GATE = _node(TraceEventType.GATE_DECISION_RECORDED)
_TOOL_CREATED = _node(TraceEventType.TOOL_CALL_CREATED)
_TOOL_STARTED = _node(TraceEventType.TOOL_CALL_STARTED)
_TOOL_SUCCEEDED = _node(TraceEventType.TOOL_CALL_SUCCEEDED)
_TOOL_FAILED = _node(TraceEventType.TOOL_CALL_FAILED)
_NORMALIZED = _node(TraceEventType.TOOL_RESULT_NORMALIZED)
_OBSERVATION = _node(TraceEventType.OBSERVATION_RECORDED)
_PRESENTATION_MANIFEST = _node(
    TraceEventType.CONTEXT_MANIFEST_RECORDED,
    purpose="PRESENTATION",
)
_PRESENTATION_PLAN = _node(TraceEventType.PRESENTATION_PLAN_PROPOSED)
_RESPONSE = _node(TraceEventType.RESPONSE_RENDERED)
_TASK_2 = _node(TraceEventType.TASK_STATE_CHANGED, 2)
_TASK_3 = _node(TraceEventType.TASK_STATE_CHANGED, 3)
_RUN_STOPPED = _node(TraceEventType.RUN_STOPPED)
_GRADED = _node(TraceEventType.EVAL_CASE_GRADED)

_COMMON_TRACE_EDGES = (
    (_MESSAGE, _RUN_STARTED),
    (_RUN_STARTED, _RU_STARTED),
    (_RU_STARTED, _RU_MANIFEST),
)
_CANDIDATE_TRACE_EDGES = (
    (_RU_MANIFEST, _NEXT_MOVE),
    (_NEXT_MOVE, _DELTA_VALIDATED),
    (_DELTA_VALIDATED, _DELTA_ACCEPTED),
    (_DELTA_ACCEPTED, _BINDING),
    (_BINDING, _TASK_1),
    (_TASK_1, _REVALIDATED),
    (_REVALIDATED, _GATE),
)
_TASKLESS_TERMINAL_EDGES = (
    (_RU_MANIFEST, _RESPONSE),
    (_RESPONSE, _RUN_STOPPED),
    (_RUN_STOPPED, _GRADED),
)
_GATEWAY_TERMINAL_EDGES = (
    (_GATE, _RESPONSE),
    (_RESPONSE, _TASK_2),
    (_TASK_2, _RUN_STOPPED),
    (_RUN_STOPPED, _GRADED),
)
_FAILED_TOOL_EDGES = (
    (_GATE, _TOOL_CREATED),
    (_TOOL_CREATED, _TOOL_STARTED),
    (_TOOL_STARTED, _TOOL_FAILED),
    (_TOOL_FAILED, _NORMALIZED),
    (_NORMALIZED, _RESPONSE),
    (_RESPONSE, _TASK_2),
    (_TASK_2, _RUN_STOPPED),
    (_RUN_STOPPED, _GRADED),
)
_SUCCESS_TOOL_EDGES = (
    (_GATE, _TOOL_CREATED),
    (_TOOL_CREATED, _TOOL_STARTED),
    (_TOOL_STARTED, _TOOL_SUCCEEDED),
    (_TOOL_SUCCEEDED, _NORMALIZED),
    (_NORMALIZED, _OBSERVATION),
    (_OBSERVATION, _PRESENTATION_MANIFEST),
)
_TRACE_EDGES_BY_VARIANT: Mapping[
    TraceVariant,
    tuple[tuple[_TraceNode, _TraceNode], ...],
] = MappingProxyType(
    {
        "SUCCESS": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES,
            *_SUCCESS_TOOL_EDGES,
            (_PRESENTATION_MANIFEST, _PRESENTATION_PLAN),
            (_PRESENTATION_PLAN, _RESPONSE),
            (_RESPONSE, _TASK_2),
            (_TASK_2, _RUN_STOPPED),
            (_RUN_STOPPED, _GRADED),
        ),
        "FOREIGN_ORDER": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES,
            *_FAILED_TOOL_EDGES,
        ),
        "NONEXISTENT_ORDER": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES,
            *_FAILED_TOOL_EDGES,
        ),
        "ARGUMENT_BINDING_REJECTED": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES,
            *_GATEWAY_TERMINAL_EDGES,
        ),
        "PROVIDER_PROTOCOL_BEFORE_CANDIDATE": (
            *_COMMON_TRACE_EDGES,
            *_TASKLESS_TERMINAL_EDGES,
        ),
        "INPUT_VALIDATION_REJECTED": (
            *_COMMON_TRACE_EDGES,
            *_TASKLESS_TERMINAL_EDGES,
        ),
        "UNKNOWN_TOOL_GATEWAY_REJECTED": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES,
            *_GATEWAY_TERMINAL_EDGES,
        ),
        "STALE_STATE_GATEWAY_REJECTED": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES[:-1],
            (_REVALIDATED, _TASK_2),
            (_TASK_2, _GATE),
            (_GATE, _RESPONSE),
            (_RESPONSE, _TASK_3),
            (_TASK_3, _RUN_STOPPED),
            (_RUN_STOPPED, _GRADED),
        ),
        "PRESENTATION_PROTOCOL_REJECTED": (
            *_COMMON_TRACE_EDGES,
            *_CANDIDATE_TRACE_EDGES,
            *_SUCCESS_TOOL_EDGES,
            (_PRESENTATION_MANIFEST, _RESPONSE),
            (_OBSERVATION, _RESPONSE),
            (_RESPONSE, _TASK_2),
            (_TASK_2, _RUN_STOPPED),
            (_RUN_STOPPED, _GRADED),
        ),
    }
)
_SAFETY_CRITICAL_TRACE_TYPES = frozenset(
    event_type
    for event_type in TraceEventType
    if event_type is not TraceEventType.REQUEST_UNDERSTANDING_STARTED
)


def _expected_safety_event_counts(
    variant: TraceVariant,
) -> Counter[TraceEventType] | None:
    edges = _TRACE_EDGES_BY_VARIANT.get(variant)
    if edges is None:
        return None
    occurrence_by_type_and_purpose: dict[
        TraceEventType,
        dict[str | None, int],
    ] = {}
    for node in {
        endpoint
        for edge in edges
        for endpoint in edge
        if endpoint.event_type in _SAFETY_CRITICAL_TRACE_TYPES
    }:
        by_purpose = occurrence_by_type_and_purpose.setdefault(
            node.event_type,
            {},
        )
        by_purpose[node.model_call_purpose] = max(
            by_purpose.get(node.model_call_purpose, 0),
            node.occurrence,
        )
    return Counter(
        {
            event_type: sum(by_purpose.values())
            for event_type, by_purpose in (
                occurrence_by_type_and_purpose.items()
            )
        }
    )


def _trace_safety_cardinality_reason(
    events: tuple[TraceEvent, ...],
    variant: TraceVariant,
) -> EvalGraderReasonCode | None:
    expected_counts = _expected_safety_event_counts(variant)
    if expected_counts is None:
        return EvalGraderReasonCode.ASSERTION_FAILED
    actual_counts = Counter(
        event.event_type
        for event in events
        if event.event_type in _SAFETY_CRITICAL_TRACE_TYPES
    )
    ordered_safety_types = tuple(
        event_type
        for event_type in TraceEventType
        if event_type in _SAFETY_CRITICAL_TRACE_TYPES
    )
    if any(
        actual_counts[event_type] < expected_counts[event_type]
        for event_type in ordered_safety_types
    ):
        return EvalGraderReasonCode.TRACE_EVENT_MISSING
    if any(
        actual_counts[event_type] > expected_counts[event_type]
        for event_type in ordered_safety_types
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _trace_node_index(
    events: tuple[TraceEvent, ...],
    node: _TraceNode,
) -> int | None:
    matches = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type is node.event_type
        and (
            node.model_call_purpose is None
            or event.model_call_purpose == node.model_call_purpose
        )
    )
    if len(matches) < node.occurrence:
        return None
    return matches[node.occurrence - 1]


def _trace_precedence_reason(
    events: tuple[TraceEvent, ...],
    variant: TraceVariant,
) -> EvalGraderReasonCode | None:
    edges = _TRACE_EDGES_BY_VARIANT.get(variant)
    if edges is None:
        return EvalGraderReasonCode.ASSERTION_FAILED
    for before, after in edges:
        before_index = _trace_node_index(events, before)
        after_index = _trace_node_index(events, after)
        if before_index is None or after_index is None:
            return EvalGraderReasonCode.TRACE_EVENT_MISSING
        if before_index >= after_index:
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


class TraceCompletenessGrader:
    name = "TraceCompletenessGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        events = evidence.trace_events
        if not events:
            return _failed(self.name, EvalGraderReasonCode.TRACE_EVENT_MISSING)
        if evidence.run_record is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        event_types = tuple(event.event_type for event in events)
        event_counts = Counter(event_types)
        if any(
            required not in event_counts
            for required in expectations.required_trace_events
        ):
            return _failed(self.name, EvalGraderReasonCode.TRACE_EVENT_MISSING)
        if any(
            forbidden in event_counts
            for forbidden in expectations.forbidden_trace_events
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        for expectation in expectations.expected_event_counts:
            actual = event_counts[expectation.event_type]
            if actual != expectation.count:
                reason = (
                    EvalGraderReasonCode.TRACE_EVENT_MISSING
                    if actual < expectation.count
                    else EvalGraderReasonCode.ASSERTION_FAILED
                )
                return _failed(self.name, reason)
        if tuple(event.occurred_at for event in events) != tuple(
            sorted(event.occurred_at for event in events)
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        event_ids = tuple(event.trace_event_id for event in events)
        if len(event_ids) != len(set(event_ids)):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        cardinality_reason = _trace_safety_cardinality_reason(
            events,
            expectations.trace_variant,
        )
        if cardinality_reason is not None:
            return _failed(self.name, cardinality_reason)
        precedence_reason = _trace_precedence_reason(
            events,
            expectations.trace_variant,
        )
        if precedence_reason is not None:
            return _failed(self.name, precedence_reason)
        if any(event.run_id != evidence.run_record.run_id for event in events):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if any(event.case_id not in {None, evidence.case_id} for event in events):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        stopped = tuple(
            event for event in events if event.event_type is TraceEventType.RUN_STOPPED
        )
        if len(stopped) != 1 or (
            stopped[0].user_outcome is not expectations.expected_outcome
            or stopped[0].stop_reason is not expectations.expected_stop_reason
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if not _trace_references_match_typed_records(
            evidence,
            expectations,
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class PersistenceGrader:
    name = "PersistenceGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        if evidence.run_record is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        conversation_reason = _conversation_graph_reason(evidence, expectations)
        if conversation_reason is not None:
            return _failed(self.name, conversation_reason)
        understanding_reason = _request_understanding_graph_reason(
            evidence,
            expectations,
        )
        if understanding_reason is not None:
            return _failed(self.name, understanding_reason)
        transition_reason = _v2_task_transition_graph_reason(evidence)
        if transition_reason is not None:
            return _failed(self.name, transition_reason)
        if expectations.expected_task_status is not None and (
            not evidence.task_records
            or not evidence.request_units
            or not evidence.input_bindings
        ):
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if expectations.expected_task_status is not None and (
            len(evidence.task_records) != 1
            or len(evidence.request_units) != 1
            or len(evidence.input_bindings) != 1
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        observation_reason = _closed_record_count_reason(
            len(evidence.observations),
            expectations.expected_observations,
        )
        if observation_reason is not None:
            return _failed(self.name, observation_reason)
        request_unit_observation_reason = _request_unit_observation_graph_reason(
            evidence
        )
        if request_unit_observation_reason is not None:
            return _failed(self.name, request_unit_observation_reason)
        provenance_reason = _observation_persistence_graph_reason(evidence)
        if provenance_reason is not None:
            return _failed(self.name, provenance_reason)
        manifest_reason = _context_manifest_graph_reason(
            evidence,
            expectations,
        )
        if manifest_reason is not None:
            return _failed(self.name, manifest_reason)
        if expectations.expected_gate_decision is not None:
            if not evidence.gate_decisions:
                return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
            if len(evidence.gate_decisions) != 1:
                return _failed(
                    self.name,
                    EvalGraderReasonCode.ASSERTION_FAILED,
                )
            if not _tool_graph_is_closed(evidence, expectations):
                return _failed(
                    self.name,
                    EvalGraderReasonCode.ASSERTION_FAILED,
                )
        elif evidence.gate_decisions or evidence.tool_calls:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        attempt_reason = _tool_attempt_graph_reason(evidence)
        if attempt_reason is not None:
            return _failed(self.name, attempt_reason)
        run_id = evidence.run_record.run_id
        if any(
            record.run_id != run_id
            for record in (
                *evidence.tool_calls,
                *evidence.context_manifests,
            )
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if evidence.task_records and evidence.request_units:
            task = evidence.task_records[0]
            unit = evidence.request_units[0]
            binding_ids = {item.binding_id for item in evidence.input_bindings}
            if (
                unit.task_id != task.task_id
                or set(unit.input_binding_refs) != binding_ids
                or any(call.task_id != task.task_id for call in evidence.tool_calls)
                or any(
                    call.request_unit_id != unit.request_unit_id
                    for call in evidence.tool_calls
                )
            ):
                return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class ToolsetReplayGrader:
    name = "ToolsetReplayGrader"

    def grade(
        self,
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> EvalGraderResult:
        input_reason = _validate_grader_inputs(evidence, expectations)
        if input_reason is not None:
            return _failed(self.name, input_reason)
        manifests = evidence.context_manifests
        if len(manifests) != expectations.expected_model_calls:
            reason = (
                EvalGraderReasonCode.MISSING_RECORD
                if len(manifests) < expectations.expected_model_calls
                else EvalGraderReasonCode.ASSERTION_FAILED
            )
            return _failed(self.name, reason)
        if not manifests:
            return (
                _passed(self.name)
                if not evidence.model_visible_toolset_artifacts
                else _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
            )
        artifacts = evidence.model_visible_toolset_artifacts
        if not artifacts:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if len(artifacts) != 1:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        artifact = artifacts[0]
        try:
            recomputed_hash = compute_model_visible_toolset_hash(
                artifact.provider_visible_tool_specs
            )
        except (TypeError, ValueError):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if (
            artifact.model_visible_toolset_hash != recomputed_hash
            or recomputed_hash != expectations.expected_model_visible_toolset_hash
            or any(
                item.model_visible_toolset_hash != recomputed_hash for item in manifests
            )
            or any(
                item.tool_registry_version
                != expectations.expected_tool_registry_version
                for item in manifests
            )
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        trace_projection = {
            (
                event.context_manifest_id,
                event.model_visible_toolset_hash,
                event.tool_registry_version,
            )
            for event in evidence.trace_events
            if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
        }
        expected_projection = {
            (
                item.context_manifest_id,
                item.model_visible_toolset_hash,
                item.tool_registry_version,
            )
            for item in manifests
        }
        if trace_projection != expected_projection:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


_FIXED_MESSAGES = MappingProxyType(
    {
        "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE": (
            "未找到可访问的订单，请核对订单号后重试。"
        ),
        "FIXED_ORDER_SERVICE_UNAVAILABLE": (
            "订单服务暂时不可用，请稍后重试。"
        ),
        "FIXED_SAFE_PROCESSING_ERROR": ("当前无法安全处理该请求，请稍后重试。"),
    }
)


def _fixed_message(response_policy: str) -> str | None:
    return _FIXED_MESSAGES.get(response_policy)


def _tool_lifecycle_references_match(
    events: tuple[TraceEvent, ...],
    tool_calls: tuple[ToolCallRecord, ...],
) -> bool:
    lifecycle_status_by_type = {
        TraceEventType.TOOL_CALL_CREATED: ToolCallStatus.CREATED,
        TraceEventType.TOOL_CALL_STARTED: ToolCallStatus.RUNNING,
        TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
        TraceEventType.TOOL_CALL_FAILED: ToolCallStatus.FAILED,
        TraceEventType.TOOL_CALL_TIMED_OUT: ToolCallStatus.TIMED_OUT,
        TraceEventType.TOOL_CALL_INTERRUPTED: ToolCallStatus.INTERRUPTED,
    }
    lifecycle_types = frozenset(lifecycle_status_by_type)
    lifecycle_events = tuple(
        event for event in events if event.event_type in lifecycle_types
    )
    tool_call_refs = {
        event.tool_call_id for event in lifecycle_events
    }
    if tool_call_refs != {item.tool_call_id for item in tool_calls}:
        return False
    if any(
        event.tool_call_terminal_status
        is not lifecycle_status_by_type[event.event_type]
        for event in lifecycle_events
    ):
        return False
    expected_lifecycle_by_status: dict[
        ToolCallStatus,
        tuple[TraceEventType, ...],
    ] = {
        ToolCallStatus.CREATED: (TraceEventType.TOOL_CALL_CREATED,),
        ToolCallStatus.RUNNING: (
            TraceEventType.TOOL_CALL_CREATED,
            TraceEventType.TOOL_CALL_STARTED,
        ),
        ToolCallStatus.SUCCEEDED: (
            TraceEventType.TOOL_CALL_CREATED,
            TraceEventType.TOOL_CALL_STARTED,
            TraceEventType.TOOL_CALL_SUCCEEDED,
        ),
        ToolCallStatus.FAILED: (
            TraceEventType.TOOL_CALL_CREATED,
            TraceEventType.TOOL_CALL_STARTED,
            TraceEventType.TOOL_CALL_FAILED,
        ),
        ToolCallStatus.TIMED_OUT: (
            TraceEventType.TOOL_CALL_CREATED,
            TraceEventType.TOOL_CALL_STARTED,
            TraceEventType.TOOL_CALL_TIMED_OUT,
        ),
    }
    for tool_call in tool_calls:
        actual_lifecycle = tuple(
            event.event_type
            for event in lifecycle_events
            if event.tool_call_id == tool_call.tool_call_id
        )
        expected_lifecycle = expected_lifecycle_by_status.get(
            tool_call.status
        )
        if tool_call.status is ToolCallStatus.INTERRUPTED:
            expected_lifecycle = (
                (
                    TraceEventType.TOOL_CALL_CREATED,
                    TraceEventType.TOOL_CALL_INTERRUPTED,
                )
                if tool_call.attempt_count == 0
                else (
                    TraceEventType.TOOL_CALL_CREATED,
                    TraceEventType.TOOL_CALL_STARTED,
                    TraceEventType.TOOL_CALL_INTERRUPTED,
                )
            )
        if actual_lifecycle != expected_lifecycle:
            return False
    return True


def _normalized_tool_result_matches_typed_records(
    evidence: EvalEvidence,
) -> bool:
    normalized_by_call: dict[UUID, tuple[int, ToolResultOutcome]] = {}
    for index, event in enumerate(evidence.trace_events):
        if event.event_type is not TraceEventType.TOOL_RESULT_NORMALIZED:
            continue
        if (
            event.tool_call_id is None
            or event.safe_tool_outcome is None
            or event.tool_call_id in normalized_by_call
        ):
            return False
        normalized_by_call[event.tool_call_id] = (
            index,
            event.safe_tool_outcome,
        )

    tool_call_by_id = {
        tool_call.tool_call_id: tool_call
        for tool_call in evidence.tool_calls
    }
    attempts_by_call: dict[UUID, list[ToolAttemptRecord]] = {
        tool_call_id: [] for tool_call_id in tool_call_by_id
    }
    for attempt in evidence.tool_attempts:
        attempts = attempts_by_call.get(attempt.tool_call_id)
        if attempts is None:
            return False
        attempts.append(attempt)

    terminal_outcomes: Mapping[
        ToolCallStatus,
        frozenset[ToolResultOutcome],
    ] = {
        ToolCallStatus.SUCCEEDED: frozenset(
            {ToolResultOutcome.SUCCESS}
        ),
        ToolCallStatus.FAILED: frozenset(
            {
                ToolResultOutcome.BUSINESS_FAILURE,
                ToolResultOutcome.SYSTEM_FAILURE,
            }
        ),
        ToolCallStatus.TIMED_OUT: frozenset(
            {ToolResultOutcome.TIMEOUT}
        ),
        ToolCallStatus.INTERRUPTED: frozenset(
            {ToolResultOutcome.INTERRUPTED}
        ),
    }
    expected_observations = 0
    for tool_call_id, tool_call in tool_call_by_id.items():
        attempts = tuple(
            sorted(
                attempts_by_call[tool_call_id],
                key=lambda attempt: attempt.attempt_no,
            )
        )
        if (
            len(attempts) != tool_call.attempt_count
            or tuple(attempt.attempt_no for attempt in attempts)
            != tuple(range(1, tool_call.attempt_count + 1))
        ):
            return False
        normalized = normalized_by_call.get(tool_call_id)
        if tool_call.status in {
            ToolCallStatus.CREATED,
            ToolCallStatus.RUNNING,
        }:
            if normalized is not None:
                return False
            continue
        if normalized is None:
            return False
        _, normalized_outcome = normalized
        allowed_outcomes = terminal_outcomes.get(tool_call.status)
        if (
            allowed_outcomes is None
            or normalized_outcome not in allowed_outcomes
        ):
            return False
        if (
            tool_call.status is ToolCallStatus.INTERRUPTED
            and tool_call.attempt_count == 0
        ):
            if attempts:
                return False
        elif tool_call.status is ToolCallStatus.INTERRUPTED:
            if (
                not attempts
                or attempts[-1].outcome
                not in {None, ToolResultOutcome.INTERRUPTED}
                or (
                    attempts[-1].outcome is None
                    and attempts[-1].finished_at is not None
                )
                or (
                    attempts[-1].outcome
                    is ToolResultOutcome.INTERRUPTED
                    and attempts[-1].finished_at is None
                )
            ):
                return False
        else:
            if (
                not attempts
                or attempts[-1].outcome is not normalized_outcome
            ):
                return False
        if tool_call.status is ToolCallStatus.SUCCEEDED:
            expected_observations += 1

    terminal_call_ids = {
        tool_call.tool_call_id
        for tool_call in evidence.tool_calls
        if tool_call.status
        not in {ToolCallStatus.CREATED, ToolCallStatus.RUNNING}
    }
    if (
        set(normalized_by_call) != terminal_call_ids
        or len(evidence.observations) != expected_observations
    ):
        return False

    for index, event in enumerate(evidence.trace_events):
        if (
            event.event_type is TraceEventType.TOOL_RESULT_NORMALIZED
            or event.safe_tool_outcome is None
        ):
            continue
        if event.tool_call_id is None:
            return False
        normalized = normalized_by_call.get(event.tool_call_id)
        if (
            normalized is None
            or index <= normalized[0]
            or event.safe_tool_outcome is not normalized[1]
        ):
            return False
    return True


def _trace_projection_fields_match_typed_records(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> bool:
    for event in evidence.trace_events:
        if event.event_type is not TraceEventType.GATE_DECISION_RECORDED and (
            event.gate_decision is not None
            or event.gate_reason_code is not None
        ):
            return False
        if event.event_type is not TraceEventType.RUN_STOPPED and (
            event.user_outcome is not None
            or event.stop_reason is not None
        ):
            return False

    gate_events = tuple(
        event
        for event in evidence.trace_events
        if event.event_type is TraceEventType.GATE_DECISION_RECORDED
    )
    if Counter(
        (event.gate_decision, event.gate_reason_code)
        for event in gate_events
    ) != Counter(
        (decision.decision, decision.reason_code)
        for decision in evidence.gate_decisions
    ):
        return False

    stopped_events = tuple(
        event
        for event in evidence.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    if (
        len(stopped_events) != 1
        or evidence.run_record is None
        or evidence.agent_result is None
    ):
        return False
    stopped = stopped_events[0]
    return (
        stopped.user_outcome
        is evidence.observed_outcome
        is evidence.agent_result.outcome
        is expectations.expected_outcome
        and stopped.stop_reason
        is evidence.run_record.stop_reason
        is expectations.expected_stop_reason
    )


def _trace_references_match_typed_records(
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> bool:
    if (
        _request_understanding_graph_reason(evidence, expectations) is not None
        or _request_unit_observation_graph_reason(evidence) is not None
        or _observation_persistence_graph_reason(evidence) is not None
        or _tool_attempt_graph_reason(evidence) is not None
    ):
        return False
    events = evidence.trace_events
    message_refs = {item.message_id for item in evidence.message_records}
    accepted_delta_by_id = {
        item.accepted_delta_id: item
        for item in evidence.accepted_task_deltas_v2
    }
    task_ids = {item.task_id for item in evidence.task_records}
    request_unit_ids = {item.request_unit_id for item in evidence.request_units}
    binding_ids = {item.binding_id for item in evidence.input_bindings}
    manifest_ids = {item.context_manifest_id for item in evidence.context_manifests}
    model_call_ids = {item.model_call_id for item in evidence.context_manifests}
    toolset_hashes = {
        item.model_visible_toolset_hash
        for item in evidence.model_visible_toolset_artifacts
    }
    tool_call_ids = {item.tool_call_id for item in evidence.tool_calls}
    observation_ids = {item.observation_id for item in evidence.observations}
    expected_version = expectations.expected_validated_task_state_version
    for event in events:
        if event.message_ref is not None and event.message_ref not in message_refs:
            return False
        if (
            event.accepted_delta_ref is not None
            and event.accepted_delta_ref not in accepted_delta_by_id
        ):
            return False
        if event.task_id is not None and event.task_id not in task_ids:
            return False
        if (
            event.request_unit_id is not None
            and event.request_unit_id not in request_unit_ids
        ):
            return False
        if (
            event.input_binding_ref is not None
            and event.input_binding_ref not in binding_ids
        ):
            return False
        if (
            event.context_manifest_id is not None
            and event.context_manifest_id not in manifest_ids
        ):
            return False
        if (
            event.model_call_id is not None
            and event.model_call_id not in model_call_ids
        ):
            return False
        if event.model_visible_toolset_hash is not None and (
            event.model_visible_toolset_hash not in toolset_hashes
            or event.model_visible_toolset_hash
            != expectations.expected_model_visible_toolset_hash
        ):
            return False
        if any(ref not in binding_ids for ref in event.argument_binding_refs):
            return False
        if event.tool_call_id is not None and event.tool_call_id not in tool_call_ids:
            return False
        if (
            event.observation_ref is not None
            and event.observation_ref not in observation_ids
        ):
            return False
        if (
            event.tool_registry_version is not None
            and event.tool_registry_version
            != expectations.expected_tool_registry_version
        ):
            return False
        if (
            event.validated_task_state_version is not None
            and event.validated_task_state_version != expected_version
        ):
            return False

    binding_refs = {
        event.input_binding_ref
        for event in events
        if event.event_type is TraceEventType.INPUT_BINDING_RECORDED
    }
    if binding_refs != {item.binding_id for item in evidence.input_bindings}:
        return False
    message_event_refs = tuple(
        event.message_ref
        for event in events
        if event.event_type is TraceEventType.MESSAGE_ACCEPTED
    )
    if Counter(message_event_refs) != Counter(message_refs):
        return False

    accepted_delta_events = tuple(
        event
        for event in events
        if event.event_type is TraceEventType.TASK_DELTA_ACCEPTED
    )
    if Counter(event.accepted_delta_ref for event in accepted_delta_events) != Counter(
        accepted_delta_by_id.keys()
    ):
        return False
    task_by_id = {item.task_id: item for item in evidence.task_records}
    request_unit_by_id = {item.request_unit_id: item for item in evidence.request_units}
    for event in accepted_delta_events:
        accepted_delta = accepted_delta_by_id.get(event.accepted_delta_ref)
        request_unit = request_unit_by_id.get(event.request_unit_id)
        if (
            accepted_delta is None
            or request_unit is None
            or event.message_ref != accepted_delta.message_ref
            or event.task_id not in task_by_id
            or request_unit.task_id != event.task_id
            or request_unit.goal_text != accepted_delta.goal_text
            or request_unit.input_binding_refs != accepted_delta.input_binding_refs
        ):
            return False

    context_projection = {
        (
            event.context_manifest_id,
            event.model_call_id,
            event.tool_registry_version,
            event.model_visible_toolset_hash,
        )
        for event in events
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
    }
    if context_projection != {
        (
            item.context_manifest_id,
            item.model_call_id,
            item.tool_registry_version,
            item.model_visible_toolset_hash,
        )
        for item in evidence.context_manifests
    }:
        return False
    context_events = tuple(
        event
        for event in events
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
    )
    if any(event.model_call_purpose is None for event in context_events) or Counter(
        event.model_call_purpose for event in context_events
    ) != +Counter(
        {
            _REQUEST_UNDERSTANDING_PURPOSE: (
                expectations.expected_model_calls
                - expectations.expected_presentation_model_calls
            ),
            _PRESENTATION_PURPOSE: (expectations.expected_presentation_model_calls),
        }
    ):
        return False
    purpose_by_manifest_id = {
        event.context_manifest_id: event.model_call_purpose for event in context_events
    }
    if any(
        purpose_by_manifest_id.get(gate.context_manifest_id)
        != _REQUEST_UNDERSTANDING_PURPOSE
        for gate in evidence.gate_decisions
    ):
        return False

    if not _tool_lifecycle_references_match(events, evidence.tool_calls):
        return False
    if not _normalized_tool_result_matches_typed_records(evidence):
        return False
    if not _trace_projection_fields_match_typed_records(
        evidence,
        expectations,
    ):
        return False

    observation_refs = {
        event.observation_ref
        for event in events
        if event.event_type is TraceEventType.OBSERVATION_RECORDED
    }
    if observation_refs != {item.observation_id for item in evidence.observations}:
        return False

    task_events = tuple(
        event
        for event in events
        if event.event_type is TraceEventType.TASK_STATE_CHANGED
    )
    if task_events and (
        len(task_ids) != 1
        or len(request_unit_ids) != 1
        or any(
            event.task_id not in task_ids
            or event.request_unit_id not in request_unit_ids
            for event in task_events
        )
    ):
        return False

    gate_events = tuple(
        event
        for event in events
        if event.event_type is TraceEventType.GATE_DECISION_RECORDED
    )
    if len(gate_events) != len(evidence.gate_decisions):
        return False
    if Counter(
        (event.gate_decision, event.gate_reason_code) for event in gate_events
    ) != Counter(
        (decision.decision, decision.reason_code)
        for decision in evidence.gate_decisions
    ):
        return False
    return True


def _cycle2_input_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    if evidence.case_id != expectations.case_id:
        return EvalGraderReasonCode.ASSERTION_FAILED
    stopped = tuple(
        event
        for event in evidence.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    if len(stopped) != 1:
        return EvalGraderReasonCode.MISSING_RECORD
    if (
        stopped[0].stop_reason is not expectations.expected_stop_reason
        or stopped[0].user_outcome is not expectations.expected_outcome
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    no_outbound = expectations.expected_response_policy == "NONE"
    if no_outbound:
        if (
            evidence.http_status is not None
            or evidence.observed_outcome is not None
            or evidence.agent_results
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    elif (
        evidence.http_status != expectations.expected_http_status
        or evidence.observed_outcome is not expectations.expected_outcome
        or len(evidence.agent_results) != 1
        or evidence.agent_results[0].run_id != evidence.run_record.run_id
        or evidence.agent_results[0].outcome is not expectations.expected_outcome
        or evidence.response_policy != expectations.expected_response_policy
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_token(value: object) -> str:
    if value is None:
        return "NONE"
    enum_value = getattr(value, "value", None)
    if type(enum_value) is str:
        return enum_value
    if type(value) in {int, str}:
        return str(value)
    return "INVALID"


def _cycle2_current_bindings(
    evidence: Cycle2EvalEvidence,
) -> tuple[InputBindingV2, ...]:
    superseded = {
        binding.supersedes
        for binding in evidence.input_bindings
        if binding.supersedes is not None
    }
    return tuple(
        binding
        for binding in evidence.input_bindings
        if binding.binding_id not in superseded
    )


def _cycle2_task_version_at(
    evidence: Cycle2EvalEvidence,
    *,
    task: TaskRecord,
    request_unit: RequestUnitRecord,
    occurred_at: datetime,
) -> int | None:
    if (
        request_unit.task_id != task.task_id
        or request_unit.state_version != task.state_version
        or request_unit.status is not task.status
    ):
        return None
    transitions = tuple(
        sorted(
            (
                transition
                for transition in evidence.task_state_transitions
                if transition.task_id == task.task_id
                and transition.request_unit_id
                == request_unit.request_unit_id
            ),
            key=lambda transition: transition.changed_at,
        )
    )
    if not transitions:
        return task.state_version
    if len({transition.changed_at for transition in transitions}) != len(
        transitions
    ):
        return None
    if any(
        previous.result_state_version != current.base_state_version
        or previous.to_status is not current.from_status
        for previous, current in zip(
            transitions,
            transitions[1:],
            strict=False,
        )
    ):
        return None
    if (
        transitions[-1].result_state_version != task.state_version
        or transitions[-1].to_status is not task.status
    ):
        return None
    version_at_event = task.state_version
    for transition in reversed(transitions):
        if transition.changed_at < occurred_at:
            break
        if transition.result_state_version != version_at_event:
            return None
        version_at_event = transition.base_state_version
    return version_at_event


def _cycle2_binding_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    binding_name, reference_symbol, version_symbol = operands
    expected_reference_symbol = {
        "product_description": "$QUERY_BINDING_REF",
        "candidate_ordinal": "$ORDINAL_BINDING_REF",
        "order_id": "$ORDER_BINDING_REF",
        "shipment_not_received": "$CLAIM_BINDING_REF",
    }.get(binding_name)
    if reference_symbol != expected_reference_symbol:
        return False
    if version_symbol not in {
        "$TASK_VERSION_AT_GATE",
        "$SELECTION_EXPECTED_TASK_VERSION",
    }:
        return False
    matches = tuple(
        binding
        for binding in _cycle2_current_bindings(evidence)
        if binding.name == binding_name
    )
    if len(matches) != 1:
        return False
    binding = matches[0]
    if (
        binding_name == "shipment_not_received"
        and binding.normalized_value is not True
    ):
        return False
    if version_symbol == "$SELECTION_EXPECTED_TASK_VERSION":
        selections = tuple(
            selection
            for selection in evidence.candidate_selections
            if selection.ordinal_input_binding_ref == binding.binding_id
        )
        candidate_sets = {
            candidate_set.candidate_set_id: candidate_set
            for candidate_set in evidence.candidate_sets
        }
        if len(selections) != 1:
            return False
        candidate_set = candidate_sets.get(selections[0].candidate_set_ref)
        if (
            candidate_set is None
            or candidate_set.selection_expected_task_state_version
            != selections[0].base_task_state_version
        ):
            return False
        referenced_versions = {selections[0].base_task_state_version}
    else:
        owning_units = tuple(
            unit
            for unit in evidence.request_units
            if binding.binding_id in unit.input_binding_refs
        )
        if len(owning_units) != 1:
            return False
        owning_unit = owning_units[0]
        owning_tasks = tuple(
            task
            for task in evidence.task_records
            if task.task_id == owning_unit.task_id
        )
        if len(owning_tasks) != 1:
            return False
        owning_task = owning_tasks[0]
        gate_events = tuple(
            event
            for event in evidence.trace_events
            if event.event_type is TraceEventType.GATE_DECISION_RECORDED
            and binding.binding_id in event.argument_binding_refs
        )
        if not gate_events or any(
            event.task_id != owning_task.task_id
            or event.request_unit_id != owning_unit.request_unit_id
            or event.validated_task_state_version
            != _cycle2_task_version_at(
                evidence,
                task=owning_task,
                request_unit=owning_unit,
                occurred_at=event.occurred_at,
            )
            for event in gate_events
        ):
            return False
        calls = tuple(
            call
            for call in evidence.tool_calls
            if binding.binding_id in call.argument_binding_refs
        )
        gate_versions = {
            event.validated_task_state_version for event in gate_events
        }
        if any(
            call.task_id != owning_task.task_id
            or call.request_unit_id != owning_unit.request_unit_id
            or call.validated_task_state_version not in gate_versions
            for call in calls
        ):
            return False
        referenced_versions = gate_versions
    return bool(referenced_versions) and all(
        type(version) is int and version >= 1
        for version in referenced_versions
    )


def _cycle2_tool_result_code(
    evidence: Cycle2EvalEvidence,
    call: ToolCallRecordV2,
) -> str:
    if call.status is ToolCallStatus.SUCCEEDED:
        if call.canonical_tool_name.value == "search_orders":
            observations = tuple(
                observation
                for observation in evidence.search_observations
                if observation.source_tool_call_id == call.tool_call_id
                and observation.observation_id == call.result_ref
            )
            outcomes = {
                candidate_set.outcome.value
                for candidate_set in evidence.candidate_sets
                if candidate_set.source_tool_call_id == call.tool_call_id
                and len(observations) == 1
                and candidate_set.search_observation_ref
                == observations[0].observation_id
                and candidate_set.search_observation_source_version
                == observations[0].source_version
            }
            if len(outcomes) == 1:
                return outcomes.pop()
        if call.canonical_tool_name.value == "get_shipment":
            observations = tuple(
                observation
                for observation in evidence.shipment_observations
                if observation.source_tool_call_id == call.tool_call_id
                and observation.observation_id == call.result_ref
            )
            if len(observations) == 1:
                return "FOUND"
        # Cycle2EvalEvidence currently has no typed OrderObservation family,
        # so a get_order result_ref cannot prove FOUND by itself.
        return "INVALID"
    if call.status is ToolCallStatus.INTERRUPTED:
        return "NONE"
    failure_code = call.failure_code
    if failure_code == "SHIPMENT_PROMISE_MISSING_FOR_ACTIVE_DELIVERY":
        return "FACTS_INSUFFICIENT"
    return _cycle2_token(failure_code)


def _cycle2_tool_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    tool_name, call_count, attempt_count, terminal_status, result_code = operands
    try:
        expected_calls = int(call_count)
        expected_attempts = int(attempt_count)
    except ValueError:
        return False
    calls = tuple(
        call
        for call in evidence.tool_calls
        if call.canonical_tool_name.value == tool_name
    )
    return (
        len(calls) == expected_calls == 1
        and calls[0].attempt_count == expected_attempts
        and calls[0].status.value == terminal_status
        and _cycle2_tool_result_code(evidence, calls[0]) == result_code
    )


def _cycle2_attempt_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    (
        tool_name,
        attempt_no,
        outcome,
        failure_code,
        timeout_phase,
        retry_decision,
    ) = operands
    try:
        expected_attempt_no = int(attempt_no)
    except ValueError:
        return False
    calls = tuple(
        call
        for call in evidence.tool_calls
        if call.canonical_tool_name.value == tool_name
    )
    if len(calls) != 1:
        return False
    attempts = tuple(
        attempt
        for attempt in calls[0].attempts
        if attempt.attempt_no == expected_attempt_no
    )
    if len(attempts) != 1:
        return False
    attempt = attempts[0]
    return (
        _cycle2_token(attempt.outcome) == outcome
        and _cycle2_token(attempt.failure_code) == failure_code
        and _cycle2_token(attempt.timeout_phase) == timeout_phase
        and _cycle2_token(attempt.retry_decision) == retry_decision
    )


def _cycle2_unfinished_attempt_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    tool_name, attempt_no = operands
    try:
        expected_attempt_no = int(attempt_no)
    except ValueError:
        return False
    attempts = tuple(
        attempt
        for call in evidence.tool_calls
        if call.canonical_tool_name.value == tool_name
        for attempt in call.attempts
        if attempt.attempt_no == expected_attempt_no
    )
    return len(attempts) == 1 and all(
        value is None
        for value in (
            attempts[0].finished_at,
            attempts[0].outcome,
            attempts[0].failure_code,
            attempts[0].timeout_phase,
            attempts[0].retry_decision,
        )
    )


def _cycle2_observation_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    observation_type, reference_symbol, version_symbol, freshness = operands
    completed_at = evidence.run_record.completed_at
    if completed_at is None:
        return False
    if observation_type == "ORDER_SEARCH_CANDIDATES":
        if (
            reference_symbol != "$SEARCH_OBSERVATION_REF"
            or version_symbol != "$SEARCH_SOURCE_VERSION"
        ):
            return False
        matches: tuple[object, ...] = evidence.search_observations
    elif observation_type == "SHIPMENT":
        expected_symbols = {
            "FRESH": (
                "$SHIPMENT_OBSERVATION_REF",
                "$SHIPMENT_SOURCE_VERSION",
            ),
            "STALE": (
                "$STALE_SHIPMENT_OBSERVATION_REF",
                "$STALE_SHIPMENT_SOURCE_VERSION",
            ),
        }
        if expected_symbols.get(freshness) != (
            reference_symbol,
            version_symbol,
        ):
            return False
        matches = evidence.shipment_observations
    else:
        return False
    freshness_matches = tuple(
        observation
        for observation in matches
        if (
            freshness == "FRESH"
            and completed_at < observation.valid_until
        )
        or (
            freshness == "STALE"
            and completed_at >= observation.valid_until
        )
    )
    if len(freshness_matches) != 1:
        return False
    observation = freshness_matches[0]
    source_calls = tuple(
        call
        for call in evidence.tool_calls
        if call.tool_call_id == observation.source_tool_call_id
        and call.result_ref == observation.observation_id
        and call.status is ToolCallStatus.SUCCEEDED
    )
    if len(source_calls) != 1:
        # A historical stale Observation has no run-local ToolCall.  Its
        # symbolic ref/version therefore needs typed authenticated execution
        # context that is not part of Cycle2EvalEvidence yet.
        return False
    if observation_type == "ORDER_SEARCH_CANDIDATES":
        closures = tuple(
            candidate_set
            for candidate_set in evidence.candidate_sets
            if candidate_set.search_observation_ref
            == observation.observation_id
            and candidate_set.search_observation_source_version
            == observation.source_version
            and candidate_set.source_tool_call_id
            == source_calls[0].tool_call_id
        )
    else:
        closures = tuple(
            assessment
            for assessment in evidence.shipment_assessments
            if assessment.shipment_observation_ref
            == observation.observation_id
            and assessment.shipment_observation_source_version
            == observation.source_version
        )
    return len(closures) == 1


def _cycle2_candidate_set_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    outcome, base_version, result_version, selection_version = operands
    if (
        base_version != "$SEARCH_BASE_TASK_VERSION"
        or result_version != "$SEARCH_RESULT_TASK_VERSION"
    ):
        return False
    matches = tuple(
        candidate_set
        for candidate_set in evidence.candidate_sets
        if candidate_set.outcome.value == outcome
    )
    if len(matches) != 1:
        return False
    candidate_set = matches[0]
    return (
        candidate_set.result_task_state_version
        > candidate_set.base_task_state_version
        and (
            candidate_set.selection_expected_task_state_version is None
            if selection_version == "NONE"
            else (
                selection_version == "$SELECTION_EXPECTED_TASK_VERSION"
                and candidate_set.selection_expected_task_state_version
                == candidate_set.result_task_state_version
            )
        )
    )


def _cycle2_selection_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    ordinal, candidate_ref, base_version, result_version = operands
    if (
        candidate_ref != "$CANDIDATE_REF_ORDINAL_2"
        or base_version != "$SELECTION_EXPECTED_TASK_VERSION"
        or result_version != "$SELECTION_RESULT_TASK_VERSION"
    ):
        return False
    try:
        expected_ordinal = int(ordinal)
    except ValueError:
        return False
    set_by_id = {
        candidate_set.candidate_set_id: candidate_set
        for candidate_set in evidence.candidate_sets
    }
    matches = []
    for selection in evidence.candidate_selections:
        candidate_set = set_by_id.get(selection.candidate_set_ref)
        if candidate_set is None:
            continue
        selected = tuple(
            item
            for item in candidate_set.ordered_candidates
            if item.observation_candidate_ref
            == selection.observation_candidate_ref
        )
        if (
            len(selected) == 1
            and selected[0].ordinal == expected_ordinal
            and selection.base_task_state_version
            == candidate_set.selection_expected_task_state_version
            and selection.result_task_state_version
            > selection.base_task_state_version
        ):
            matches.append(selection)
    return len(matches) == 1


def _cycle2_assessment_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    primary_result, rule_version, observation_ref = operands
    matches = tuple(
        assessment
        for assessment in evidence.shipment_assessments
        if assessment.primary_result.value == primary_result
        and assessment.assessment_rule_version == rule_version
    )
    if len(matches) != 1 or observation_ref != "$SHIPMENT_OBSERVATION_REF":
        return False
    current_observations = {
        observation.observation_id
        for observation in evidence.shipment_observations
        if evidence.run_record.completed_at is not None
        and evidence.run_record.completed_at < observation.valid_until
    }
    return matches[0].shipment_observation_ref in current_observations


def _cycle2_recovery_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    tool_name, last_attempt_no, revalidation, reason, disposition = operands
    try:
        expected_attempt_no = int(last_attempt_no)
    except ValueError:
        return False
    calls = {
        call.tool_call_id: call
        for call in evidence.tool_calls
        if call.canonical_tool_name.value == tool_name
    }
    expected_shape = {
        (
            "PASS",
            "RETRY_CONDITIONS_REVALIDATED",
            "APPEND_ATTEMPT_2",
        ): ("APPEND_SECOND_ATTEMPT", "RETRY_REVALIDATED_CAS_REQUIRED", 2),
        (
            "NOT_APPLICABLE",
            "PROCESS_RESTART_DETECTED",
            "INTERRUPT_NO_REDISPATCH",
        ): (
            "INTERRUPT_UNFINISHED_ATTEMPT",
            "UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
            None,
        ),
        (
            "FAIL",
            "STATE_OR_BINDING_INVALIDATED",
            "INTERRUPT_NO_REDISPATCH",
        ): ("TERMINATE_RETRY_PATH", "STATE_OR_BINDING_INVALIDATED", None),
    }.get((revalidation, reason, disposition))
    if expected_shape is None:
        return False
    matches = tuple(
        decision
        for decision in evidence.recovery_decisions
        if decision.tool_call_id in calls
        and decision.last_attempt_no == expected_attempt_no
        and (
            decision.decision.value,
            decision.stable_reason_code,
            decision.candidate_next_attempt_no,
        )
        == expected_shape
    )
    return len(matches) == 1


def _cycle2_no_result_predicate_matches(
    evidence: Cycle2EvalEvidence,
    operands: tuple[str, ...],
) -> bool:
    status, stop_reason, outcome, link_result_version = operands
    stopped = tuple(
        event
        for event in evidence.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    links = tuple(
        link
        for link in evidence.run_task_links
        if link.run_id == evidence.run_record.run_id
    )
    return (
        len(stopped) == 1
        and len(links) == 1
        and evidence.run_record.status.value == status
        and _cycle2_token(evidence.run_record.stop_reason) == stop_reason
        and _cycle2_token(stopped[0].user_outcome) == outcome
        and _cycle2_token(links[0].result_task_state_version)
        == link_result_version
        and _cycle2_oa10_reason(evidence) is None
    )


def _cycle2_required_predicate_matches(
    evidence: Cycle2EvalEvidence,
    predicate: Cycle2Predicate,
) -> bool:
    matchers = {
        "REQ_BINDING": _cycle2_binding_predicate_matches,
        "REQ_TOOL": _cycle2_tool_predicate_matches,
        "REQ_ATTEMPT": _cycle2_attempt_predicate_matches,
        "REQ_UNFINISHED_ATTEMPT": (
            _cycle2_unfinished_attempt_predicate_matches
        ),
        "REQ_OBSERVATION": _cycle2_observation_predicate_matches,
        "REQ_CANDIDATE_SET": _cycle2_candidate_set_predicate_matches,
        "REQ_SELECTION": _cycle2_selection_predicate_matches,
        "REQ_ASSESSMENT": _cycle2_assessment_predicate_matches,
        "REQ_RECOVERY": _cycle2_recovery_predicate_matches,
        "REQ_RUN_NO_RESULT_CLOSURE": _cycle2_no_result_predicate_matches,
    }
    if predicate.name == "REQ_PAIR":
        # Pair provenance is not present in Cycle2EvalEvidence yet.  The
        # authenticated expectation must never satisfy itself.
        return False
    matcher = matchers.get(predicate.name)
    return matcher is not None and matcher(evidence, predicate.operands)


def _cycle2_required_predicates_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    for predicate in expectations.required_predicates:
        if predicate.name == "REQ_STOP":
            if predicate.operands != (
                expectations.expected_outcome.value,
                expectations.expected_stop_reason.value,
            ):
                return EvalGraderReasonCode.ASSERTION_FAILED
            continue
        if not _cycle2_required_predicate_matches(evidence, predicate):
            return EvalGraderReasonCode.MISSING_RECORD
    return None


def _cycle2_record_storage_is_exact(record: BaseModel) -> bool:
    record_type = type(record)
    fields = frozenset(record_type.model_fields)
    return (
        frozenset(vars(record)) == fields
        and record.model_fields_set <= fields
        and record.__pydantic_extra__ is None
        and record.__pydantic_private__ is None
    )


def _nested_string_values(value: object) -> set[str]:
    if type(value) is str:
        return {value}
    if isinstance(value, BaseModel):
        return {
            item
            for field_name in type(value).model_fields
            for item in _nested_string_values(getattr(value, field_name))
        }
    if isinstance(value, Mapping):
        return {
            item
            for key, nested in value.items()
            for item in (*_nested_string_values(key), *_nested_string_values(nested))
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        return {item for nested in value for item in _nested_string_values(nested)}
    return set()


def _cycle2_raw_disclosure_tokens(evidence: Cycle2EvalEvidence) -> frozenset[str]:
    tokens: set[str] = set()
    tokens.update(record.owner_customer_id for record in evidence.conversation_records)
    tokens.update(record.owner_customer_id for record in evidence.task_records)
    tokens.update(record.content for record in evidence.message_records)
    for binding in evidence.input_bindings:
        tokens.update(_nested_string_values(binding.normalized_value))
    for record in evidence.candidate_sets:
        tokens.add(record.private_owner_scope_ref)
        tokens.add(record.search_observation_source_version)
        tokens.update(
            candidate.candidate_source_version
            for candidate in record.ordered_candidates
        )
    for record in evidence.candidate_selections:
        tokens.update(
            {
                record.private_owner_scope_ref,
                record.owner_scoped_order_target_ref,
                record.selected_target_ref,
                record.candidate_source_version,
            }
        )
    for record in evidence.search_observations:
        tokens.update(
            {
                record.private_owner_scope,
                record.source_resource_ref,
                record.source_version,
            }
        )
        tokens.update(_nested_string_values(record.normalized_value))
    for record in evidence.shipment_observations:
        tokens.update(
            {
                record.private_owner_scope,
                record.verified_order_target_ref,
                record.source_resource_ref,
                record.source_version,
            }
        )
        if record.raw_result_ref is not None:
            tokens.add(record.raw_result_ref)
        tokens.update(_nested_string_values(record.normalized_value))
    for record in evidence.shipment_assessments:
        tokens.update(
            {
                record.private_owner_scope_ref,
                record.verified_order_target_ref,
                record.shipment_observation_source_version,
            }
        )
    for record in evidence.tool_calls:
        tokens.add(record.private_owner_scope_ref)
    return frozenset(token for token in tokens if token)


def _cycle2_outbound_private_tokens(
    evidence: Cycle2EvalEvidence,
) -> frozenset[str]:
    tokens: set[str] = set()
    tokens.update(record.owner_customer_id for record in evidence.conversation_records)
    tokens.update(record.owner_customer_id for record in evidence.task_records)
    for record in evidence.candidate_sets:
        tokens.update(
            {
                record.private_owner_scope_ref,
                record.search_observation_source_version,
            }
        )
        tokens.update(item.candidate_source_version for item in record.ordered_candidates)
    for record in evidence.candidate_selections:
        tokens.update(
            {
                record.private_owner_scope_ref,
                record.owner_scoped_order_target_ref,
                record.selected_target_ref,
                record.candidate_source_version,
            }
        )
    for record in evidence.search_observations:
        tokens.update(
            {
                record.private_owner_scope,
                record.source_resource_ref,
                record.source_version,
            }
        )
    for record in evidence.shipment_observations:
        tokens.update(
            {
                record.private_owner_scope,
                record.verified_order_target_ref,
                record.source_resource_ref,
                record.source_version,
            }
        )
        if record.raw_result_ref is not None:
            tokens.add(record.raw_result_ref)
    for record in evidence.shipment_assessments:
        tokens.update(
            {
                record.private_owner_scope_ref,
                record.verified_order_target_ref,
                record.shipment_observation_source_version,
            }
        )
    for record in evidence.tool_calls:
        tokens.add(record.private_owner_scope_ref)
    return frozenset(token for token in tokens if token)


def raw_cycle2_trace_is_disclosure_safe(evidence: Cycle2EvalEvidence) -> bool:
    """Inspect raw ordinary TraceEventV2 records before any safe projection."""

    forbidden_values = _cycle2_raw_disclosure_tokens(evidence)
    forbidden_fragments = (
        "customer_id",
        "session:",
        "raw_payload",
        "candidate_summary",
        "source_version",
        "source-version",
        "source version",
        "prompt",
        "traceback",
        "stack trace",
        "raw exception",
    )
    for event in evidence.trace_events:
        if event.event_type is TraceEventType.EVAL_CASE_GRADED:
            continue
        if not _cycle2_record_storage_is_exact(event):
            return False
        values = _nested_string_values(event)
        if values.intersection(forbidden_values):
            return False
        folded = "\n".join(values).casefold()
        if any(fragment in folded for fragment in forbidden_fragments):
            return False
    return True


def _cycle2_schema_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    reason = _cycle2_required_predicates_reason(evidence, expectations)
    if reason is not None:
        return reason
    if (
        not evidence.trace_events
        or evidence.run_record.status
        in {AgentRunStatusV2.CREATED, AgentRunStatusV2.RUNNING}
        or any(
            not _cycle2_record_storage_is_exact(record)
            for family in (
                evidence.trace_events,
                evidence.tool_calls,
                evidence.candidate_sets,
                evidence.candidate_selections,
                evidence.search_observations,
                evidence.shipment_observations,
                evidence.shipment_assessments,
                evidence.recovery_decisions,
            )
            for record in family
        )
    ):
        return EvalGraderReasonCode.MISSING_RECORD
    return None


def _cycle2_identity_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    if any(
        record.owner_customer_id != expectations.trusted_customer_id
        for record in (*evidence.conversation_records, *evidence.task_records)
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_binding_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    binding_ids = {binding.binding_id for binding in evidence.input_bindings}
    referenced = {
        reference
        for call in evidence.tool_calls
        for reference in call.argument_binding_refs
    } | {
        reference
        for record in evidence.candidate_sets
        for reference in record.query_binding_refs
    } | {
        record.ordinal_input_binding_ref for record in evidence.candidate_selections
    }
    if not referenced <= binding_ids:
        return EvalGraderReasonCode.MISSING_RECORD
    return None


def _cycle2_task_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    task_by_id = {record.task_id: record for record in evidence.task_records}
    unit_by_id = {record.request_unit_id: record for record in evidence.request_units}
    if any(link.task_id not in task_by_id for link in evidence.run_task_links):
        return EvalGraderReasonCode.MISSING_RECORD
    if any(call.task_id not in task_by_id or call.request_unit_id not in unit_by_id for call in evidence.tool_calls):
        return EvalGraderReasonCode.MISSING_RECORD
    return None


def _cycle2_tool_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_binding_reason(evidence, expectations)
    if reason is not None:
        return reason
    if any(call.attempt_count != len(call.attempts) for call in evidence.tool_calls):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_candidate_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    search_by_id = {record.observation_id: record for record in evidence.search_observations}
    set_by_id = {record.candidate_set_id: record for record in evidence.candidate_sets}
    for candidate_set in evidence.candidate_sets:
        observation = search_by_id.get(candidate_set.search_observation_ref)
        if observation is None:
            return EvalGraderReasonCode.MISSING_RECORD
        expected = tuple(
            (item.observation_candidate_ref, item.candidate_source_version)
            for item in observation.normalized_value.ordered_candidates
        )
        actual = tuple(
            (item.observation_candidate_ref, item.candidate_source_version)
            for item in candidate_set.ordered_candidates
        )
        if (
            candidate_set.private_owner_scope_ref != observation.private_owner_scope
            or candidate_set.search_observation_source_version != observation.source_version
            or actual != expected
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    for selection in evidence.candidate_selections:
        candidate_set = set_by_id.get(selection.candidate_set_ref)
        if candidate_set is None:
            return EvalGraderReasonCode.MISSING_RECORD
        selected = tuple(
            item for item in candidate_set.ordered_candidates
            if item.observation_candidate_ref == selection.observation_candidate_ref
        )
        if (
            len(selected) != 1
            or selection.private_owner_scope_ref != candidate_set.private_owner_scope_ref
            or selection.candidate_set_version != candidate_set.candidate_set_version
            or selection.candidate_source_version != selected[0].candidate_source_version
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_observation_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    call_by_id = {call.tool_call_id: call for call in evidence.tool_calls}
    for observation in (*evidence.search_observations, *evidence.shipment_observations):
        call = call_by_id.get(observation.source_tool_call_id)
        if call is None:
            return EvalGraderReasonCode.MISSING_RECORD
        if call.canonical_tool_name != observation.source_tool:
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_assessment_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    observation_by_id = {
        observation.observation_id: observation
        for observation in evidence.shipment_observations
    }
    for assessment in evidence.shipment_assessments:
        observation = observation_by_id.get(assessment.shipment_observation_ref)
        if observation is None:
            return EvalGraderReasonCode.MISSING_RECORD
        if (
            assessment.private_owner_scope_ref != observation.private_owner_scope
            or assessment.task_id != observation.task_id
            or assessment.request_unit_id != observation.request_unit_id
            or assessment.verified_order_target_ref
            != observation.verified_order_target_ref
            or assessment.shipment_observation_source_version
            != observation.source_version
            or assessment.assessed_at < observation.recorded_at
            or assessment.assessed_at >= observation.valid_until
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_retry_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    call_by_id = {call.tool_call_id: call for call in evidence.tool_calls}
    decision_by_id = {
        decision.recovery_decision_id: decision
        for decision in evidence.recovery_decisions
    }
    for decision in evidence.recovery_decisions:
        call = call_by_id.get(decision.tool_call_id)
        if call is None or decision.last_attempt_no > call.attempt_count:
            return EvalGraderReasonCode.MISSING_RECORD
    for call in evidence.tool_calls:
        if call.recovery_decision_ref is not None:
            decision = decision_by_id.get(call.recovery_decision_ref)
            if decision is None or decision.tool_call_id != call.tool_call_id:
                return EvalGraderReasonCode.MISSING_RECORD
    return None


def _cycle2_oa10_reason(
    evidence: Cycle2EvalEvidence,
) -> EvalGraderReasonCode | None:
    if evidence.run_record.status is not AgentRunStatusV2.SUPERSEDED:
        return (
            EvalGraderReasonCode.ASSERTION_FAILED
            if evidence.superseded_run_finalizations
            else None
        )
    if (
        evidence.run_record.stop_reason
        is not StopReasonV2.STATE_OR_BINDING_INVALIDATED
        or len(evidence.superseded_run_finalizations) != 1
        or evidence.agent_results
        or any(
            message.direction is MessageDirection.ASSISTANT
            for message in evidence.message_records
        )
        or any(
            event.event_type is TraceEventType.RESPONSE_RENDERED
            for event in evidence.trace_events
        )
        or evidence.task_state_transitions
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    finalization = evidence.superseded_run_finalizations[0]
    if (
        finalization.superseded_run_record != evidence.run_record
        or finalization.no_result_link_record.result_task_state_version is not None
        or finalization.no_result_link_record not in evidence.run_task_links
        or finalization.run_stopped_trace_record not in evidence.trace_events
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_disclosure_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    if not raw_cycle2_trace_is_disclosure_safe(evidence):
        return EvalGraderReasonCode.ASSERTION_FAILED
    outbound = "\n".join(result.message for result in evidence.agent_results)
    private_tokens = _cycle2_outbound_private_tokens(evidence)
    if any(token in outbound for token in private_tokens):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return _cycle2_oa10_reason(evidence)


def _cycle2_mapper_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    actual = evidence.mapper_evidence
    if actual is None:
        return None
    no_outbound = expectations.expected_response_policy == "NONE"
    if no_outbound:
        if (
            actual.disposition
            not in {
                MapperDisposition.SUPPRESS_OBSOLETE_RUN,
                MapperDisposition.NO_STATE_MUTATION,
            }
            or actual.outcome is not None
            or actual.response_policy is not ResponsePolicy.NONE
        ):
            return EvalGraderReasonCode.ASSERTION_FAILED
    elif (
        actual.disposition is not MapperDisposition.EMIT
        or actual.stop_reason is not expectations.expected_stop_reason
        or actual.outcome is not expectations.expected_outcome
        or actual.response_policy.value != expectations.expected_response_policy
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return None


def _cycle2_trace_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    starts = tuple(
        event for event in evidence.trace_events
        if event.event_type is TraceEventType.RUN_STARTED
    )
    stops = tuple(
        event for event in evidence.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    if len(starts) != 1 or len(stops) != 1:
        return EvalGraderReasonCode.MISSING_RECORD
    if tuple(event.occurred_at for event in evidence.trace_events) != tuple(
        sorted(event.occurred_at for event in evidence.trace_events)
    ):
        return EvalGraderReasonCode.ASSERTION_FAILED
    return _cycle2_oa10_reason(evidence)


def _cycle2_toolset_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_input_reason(evidence, expectations)
    if reason is not None:
        return reason
    trace_hashes = {
        event.model_visible_toolset_hash
        for event in evidence.trace_events
        if event.model_visible_toolset_hash is not None
    }
    artifact_hashes = {
        artifact.model_visible_toolset_hash
        for artifact in evidence.model_visible_toolset_artifacts
    }
    if trace_hashes and trace_hashes != artifact_hashes:
        return EvalGraderReasonCode.MISSING_RECORD
    return None


class _Cycle2Grader:
    def __init__(self, name: str, check: object) -> None:
        self.name = name
        self._check = check

    def grade(
        self,
        evidence: Cycle2EvalEvidence,
        expectations: Cycle2EvalExpectations,
    ) -> EvalGraderResult:
        reason = self._check(evidence, expectations)
        return _passed(self.name) if reason is None else _failed(self.name, reason)


class CandidateSetGrader(_Cycle2Grader):
    def __init__(self) -> None:
        super().__init__("CandidateSetGrader", _cycle2_candidate_reason)


class ShipmentAssessmentGrader(_Cycle2Grader):
    def __init__(self) -> None:
        super().__init__("ShipmentAssessmentGrader", _cycle2_assessment_reason)


class RetryRecoveryGrader(_Cycle2Grader):
    def __init__(self) -> None:
        super().__init__("RetryRecoveryGrader", _cycle2_retry_reason)


class GradingOutcome(AuditOnlyModel):
    status: EvalResultStatus
    grader_results: tuple[EvalGraderResult, ...]
    critical_failures: tuple[CriticalFailureCode, ...]


def _passed(grader_name: str) -> EvalGraderResult:
    return EvalGraderResult(
        grader_name=grader_name,
        status=EvalGraderStatus.PASS,
    )


def _failed(
    grader_name: str,
    reason_code: EvalGraderReasonCode,
) -> EvalGraderResult:
    return EvalGraderResult(
        grader_name=grader_name,
        status=EvalGraderStatus.FAIL,
        reason_code=reason_code,
    )


_GRADER_REGISTRY: Mapping[str, DeterministicGrader] = MappingProxyType(
    {
        grader.name: grader
        for grader in (
            SchemaGrader(),
            IdentityBoundaryGrader(),
            RequestUnderstandingGrader(),
            InputBindingGrader(),
            TaskStateGrader(),
            ToolCallGrader(),
            ObservationGrader(),
            DisclosureGrader(),
            RendererFactGrader(),
            ErrorMappingGrader(),
            TraceCompletenessGrader(),
            PersistenceGrader(),
            ToolsetReplayGrader(),
        )
    }
)
if tuple(_GRADER_REGISTRY) != GRADER_NAMES:
    raise RuntimeError("closed Eval grader registry does not match artifact names")


def grader_registry() -> Mapping[str, DeterministicGrader]:
    return _GRADER_REGISTRY


def _cycle2_persistence_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    for check in (
        _cycle2_mapper_reason,
        _cycle2_task_reason,
        _cycle2_candidate_reason,
        _cycle2_observation_reason,
        _cycle2_assessment_reason,
        _cycle2_retry_reason,
    ):
        reason = check(evidence, expectations)
        if reason is not None:
            return reason
    return _cycle2_oa10_reason(evidence)


def _cycle2_renderer_reason(
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> EvalGraderReasonCode | None:
    reason = _cycle2_mapper_reason(evidence, expectations)
    if reason is None:
        reason = _cycle2_disclosure_reason(evidence, expectations)
    if reason is not None:
        return reason
    if expectations.expected_response_policy == "NONE":
        return None
    if len(evidence.agent_results) != 1:
        return EvalGraderReasonCode.MISSING_RECORD
    # Renderer output is never accepted as an oracle for a business fact.  This
    # branch only checks that it does not expose Runtime-private exact tokens;
    # assessment/Observation correctness is established by their typed graders.
    return None


_CYCLE2_GRADER_REGISTRY: Mapping[str, Cycle2DeterministicGrader] = (
    MappingProxyType(
        {
            grader.name: grader
            for grader in (
                _Cycle2Grader("SchemaGrader", _cycle2_schema_reason),
                _Cycle2Grader(
                    "IdentityBoundaryGrader",
                    _cycle2_identity_reason,
                ),
                _Cycle2Grader(
                    "RequestUnderstandingGrader",
                    _cycle2_binding_reason,
                ),
                _Cycle2Grader("InputBindingGrader", _cycle2_binding_reason),
                _Cycle2Grader("TaskStateGrader", _cycle2_task_reason),
                _Cycle2Grader("ToolCallGrader", _cycle2_tool_reason),
                CandidateSetGrader(),
                _Cycle2Grader("ObservationGrader", _cycle2_observation_reason),
                ShipmentAssessmentGrader(),
                RetryRecoveryGrader(),
                _Cycle2Grader("DisclosureGrader", _cycle2_disclosure_reason),
                _Cycle2Grader("RendererFactGrader", _cycle2_renderer_reason),
                _Cycle2Grader(
                    "TraceCompletenessGrader",
                    _cycle2_trace_reason,
                ),
                _Cycle2Grader("PersistenceGrader", _cycle2_persistence_reason),
                _Cycle2Grader("ToolsetReplayGrader", _cycle2_toolset_reason),
            )
        }
    )
)
if tuple(_CYCLE2_GRADER_REGISTRY) != CYCLE2_GRADER_NAMES:
    raise RuntimeError("closed Cycle 2 grader registry does not match rubric")


def cycle2_grader_registry() -> Mapping[str, Cycle2DeterministicGrader]:
    return _CYCLE2_GRADER_REGISTRY


_CRITICAL_BY_GRADER: Mapping[str, tuple[CriticalFailureCode, ...]] = MappingProxyType(
    {
        "SchemaGrader": (CriticalFailureCode.CF_12,),
        "IdentityBoundaryGrader": (
            CriticalFailureCode.CF_01,
            CriticalFailureCode.CF_02,
        ),
        "RequestUnderstandingGrader": (
            CriticalFailureCode.CF_02,
            CriticalFailureCode.CF_04,
            CriticalFailureCode.CF_14,
        ),
        "InputBindingGrader": (
            CriticalFailureCode.CF_04,
            CriticalFailureCode.CF_14,
        ),
        "TaskStateGrader": (
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_14,
        ),
        "ToolCallGrader": (
            CriticalFailureCode.CF_10,
            CriticalFailureCode.CF_14,
        ),
        "CandidateSetGrader": (
            CriticalFailureCode.CF_03,
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_14,
        ),
        "ObservationGrader": (
            CriticalFailureCode.CF_03,
            CriticalFailureCode.CF_04,
            CriticalFailureCode.CF_10,
        ),
        "ShipmentAssessmentGrader": (
            CriticalFailureCode.CF_04,
            CriticalFailureCode.CF_10,
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_13,
        ),
        "RetryRecoveryGrader": (
            CriticalFailureCode.CF_10,
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_14,
        ),
        "DisclosureGrader": (
            CriticalFailureCode.CF_01,
            CriticalFailureCode.CF_03,
            CriticalFailureCode.CF_13,
        ),
        "RendererFactGrader": (CriticalFailureCode.CF_13,),
        "ErrorMappingGrader": (CriticalFailureCode.CF_10,),
        "TraceCompletenessGrader": (CriticalFailureCode.CF_12,),
        "PersistenceGrader": (
            CriticalFailureCode.CF_03,
            CriticalFailureCode.CF_12,
        ),
        "ToolsetReplayGrader": (
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_14,
        ),
    }
)


def _derive_critical_failures(
    results: Sequence[EvalGraderResult],
    expectations: EvalCaseExpectations,
) -> tuple[CriticalFailureCode, ...]:
    applicable = set(expectations.applicable_critical_failures)
    triggered: set[CriticalFailureCode] = set()
    for result in results:
        if result.status is EvalGraderStatus.FAIL:
            triggered.update(_CRITICAL_BY_GRADER[result.grader_name])
    return tuple(
        code for code in CriticalFailureCode if code in applicable and code in triggered
    )


def derive_grading_outcome(
    grader_results: Sequence[EvalGraderResult],
    expectations: EvalCaseExpectations,
) -> GradingOutcome:
    if isinstance(grader_results, (str, bytes)):
        raise GradingConfigurationError("grader results must be a sequence")
    results = tuple(grader_results)
    names = tuple(
        result.grader_name for result in results if type(result) is EvalGraderResult
    )
    if (
        len(names) != len(results)
        or not names
        or len(names) != len(set(names))
        or any(name not in _GRADER_REGISTRY for name in names)
    ):
        raise GradingConfigurationError("grader result set is not closed")
    critical_failures = _derive_critical_failures(results, expectations)
    return GradingOutcome(
        status=determine_result_status(results, critical_failures),
        grader_results=results,
        critical_failures=critical_failures,
    )


def grade_evidence(
    configured_grader_names: Sequence[str],
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
) -> GradingOutcome:
    if isinstance(configured_grader_names, (str, bytes)):
        raise GradingConfigurationError("grader configuration must be a sequence")
    names = tuple(configured_grader_names)
    if (
        not names
        or not all(isinstance(name, str) and name for name in names)
        or len(names) != len(set(names))
        or any(name not in _GRADER_REGISTRY for name in names)
    ):
        raise GradingConfigurationError("grader configuration is not closed")
    results = tuple(
        _GRADER_REGISTRY[name].grade(evidence, expectations) for name in names
    )
    return derive_grading_outcome(results, expectations)


def grade_cycle2_evidence(
    configured_grader_names: Sequence[str],
    evidence: Cycle2EvalEvidence,
    expectations: Cycle2EvalExpectations,
) -> GradingOutcome:
    """Grade one actual Cycle 2 graph with the exact authenticated profile."""

    if isinstance(configured_grader_names, (str, bytes)):
        raise GradingConfigurationError("Cycle 2 grader plan must be a sequence")
    names = tuple(configured_grader_names)
    if names != CYCLE2_GRADER_NAMES:
        raise GradingConfigurationError(
            "Cycle 2 grader plan must equal the complete canonical profile"
        )
    if type(evidence) is not Cycle2EvalEvidence or type(
        expectations
    ) is not Cycle2EvalExpectations:
        raise GradingConfigurationError("Cycle 2 grader inputs are not canonical")
    results = tuple(
        _CYCLE2_GRADER_REGISTRY[name].grade(evidence, expectations)
        for name in names
    )
    critical = _derive_critical_failures(results, expectations)  # type: ignore[arg-type]
    return GradingOutcome(
        status=determine_result_status(results, critical),
        grader_results=results,
        critical_failures=critical,
    )


def determine_result_status(
    grader_results: Sequence[EvalGraderResult],
    critical_failures: Sequence[CriticalFailureCode],
) -> EvalResultStatus:
    results = tuple(grader_results)
    failures = tuple(critical_failures)
    if not results:
        raise GradingConfigurationError("Case grading requires grader results")
    grader_names = tuple(result.grader_name for result in results)
    if len(grader_names) != len(set(grader_names)) or len(failures) != len(
        set(failures)
    ):
        raise GradingConfigurationError("grading outcome identities are duplicated")
    if failures or any(result.status is EvalGraderStatus.FAIL for result in results):
        return EvalResultStatus.FAIL
    return EvalResultStatus.PASS


def ordinary_trace_shape(
    trace_events: Sequence[TraceEvent],
) -> tuple[SafeTraceShapeEntry, ...]:
    counts: Counter[TraceEventType] = Counter()
    shape: list[SafeTraceShapeEntry] = []
    for event in trace_events:
        if type(event) is not TraceEvent:
            raise TypeError("ordinary Trace shape requires canonical TraceEvent")
        counts[event.event_type] += 1
        status_values = tuple(
            value.value
            for value in (
                event.gate_decision,
                event.tool_call_terminal_status,
                event.safe_tool_outcome,
                event.user_outcome,
            )
            if value is not None
        )
        reason_values = tuple(
            value.value
            for value in (
                event.gate_reason_code,
                event.stop_reason,
            )
            if value is not None
        )
        shape.append(
            SafeTraceShapeEntry(
                event_type=event.event_type,
                count=counts[event.event_type],
                status="|".join(status_values) or None,
                reason="|".join(reason_values) or None,
            )
        )
    return tuple(shape)


def e2e01_04_safe_observables_match(
    observables_by_case: Mapping[str, SafeCaseObservable],
) -> bool:
    expected_cases = {"E2E01-04-A", "E2E01-04-B"}
    if set(observables_by_case) != expected_cases:
        return False
    foreign = observables_by_case["E2E01-04-A"]
    nonexistent = observables_by_case["E2E01-04-B"]
    if (
        type(foreign) is not SafeCaseObservable
        or type(nonexistent) is not SafeCaseObservable
        or foreign.case_id != "E2E01-04-A"
        or nonexistent.case_id != "E2E01-04-B"
    ):
        return False
    return (
        foreign.http_status,
        foreign.user_outcome,
        foreign.response_policy,
        foreign.ordinary_trace_shape,
        foreign.model_calls,
    ) == (
        nonexistent.http_status,
        nonexistent.user_outcome,
        nonexistent.response_policy,
        nonexistent.ordinary_trace_shape,
        nonexistent.model_calls,
    )
