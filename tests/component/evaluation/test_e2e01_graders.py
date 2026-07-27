from __future__ import annotations

from collections.abc import Callable
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mini_agent.application.persistence import (
    P0PersistenceEnvelope,
    P0RecordCode,
    P0RecordReference,
    encode_persistence_record,
)
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
)
from mini_agent.core.memory import (
    ContextManifest,
    ObservationVisibility,
    OrderObservation,
    TaskStateRefAndVersion,
    TokenCounts,
    VersionedRecordRef,
)
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    CandidateValidationDecision,
    CandidateValidationRecord,
    InputBinding,
    InputValidationStatus,
    RequestUnderstandingRecord,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateDecisionValue,
    GateReasonCode,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)
from mini_agent.evaluation.graders import (
    GRADER_NAMES,
    EvalCaseExpectations,
    EvalEvidence,
    GradingConfigurationError,
    SafeCaseObservable,
    TraceEventCountExpectation,
    determine_result_status,
    e2e01_04_safe_observables_match,
    grade_evidence,
    grader_registry,
    ordinary_trace_shape,
)


RUN_ID = UUID("00000000-0000-4000-8000-000000000501")
OTHER_RUN_ID = UUID("00000000-0000-4000-8000-000000000599")
CONVERSATION_ID = UUID("00000000-0000-4000-8000-000000000500")
TRACE_REF = UUID("00000000-0000-4000-8000-000000000502")
MESSAGE_REF = UUID("00000000-0000-4000-8000-000000000503")
CANDIDATE_ID = UUID("00000000-0000-4000-8000-000000000504")
ACCEPTED_DELTA_ID = UUID("00000000-0000-4000-8000-000000000515")
NEXT_MOVE_REF = UUID("00000000-0000-4000-8000-000000000516")
BINDING_ID = UUID("00000000-0000-4000-8000-000000000505")
TASK_ID = UUID("00000000-0000-4000-8000-000000000506")
REQUEST_UNIT_ID = UUID("00000000-0000-4000-8000-000000000507")
MODEL_CALL_1 = UUID("00000000-0000-4000-8000-000000000508")
MODEL_CALL_2 = UUID("00000000-0000-4000-8000-000000000509")
CONTEXT_1 = UUID("00000000-0000-4000-8000-000000000510")
CONTEXT_2 = UUID("00000000-0000-4000-8000-000000000511")
GATE_ID = UUID("00000000-0000-4000-8000-000000000512")
TOOL_CALL_ID = UUID("00000000-0000-4000-8000-000000000513")
OBSERVATION_ID = UUID("00000000-0000-4000-8000-000000000514")
TOOL_RESULT_REF = UUID("00000000-0000-4000-8000-000000000517")
NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
TOOLSET_HASH = compute_model_visible_toolset_hash((get_order_tool_spec(),))
LEAKY_DATETIME_SECRET = "leaky-datetime-secret"


class LeakyDatetime(datetime):
    strftime_calls = 0

    def strftime(self, format: str) -> str:
        type(self).strftime_calls += 1
        return f"{super().strftime(format)}{LEAKY_DATETIME_SECRET}"


class DerivedUUID(UUID):
    pass


REQUIRED_EVENTS = (
    TraceEventType.MESSAGE_ACCEPTED,
    TraceEventType.RUN_STARTED,
    TraceEventType.REQUEST_UNDERSTANDING_STARTED,
    TraceEventType.CONTEXT_MANIFEST_RECORDED,
    TraceEventType.NEXT_MOVE_PROPOSED,
    TraceEventType.TASK_DELTA_VALIDATED,
    TraceEventType.TASK_DELTA_ACCEPTED,
    TraceEventType.INPUT_BINDING_RECORDED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.NEXT_MOVE_REVALIDATED,
    TraceEventType.GATE_DECISION_RECORDED,
    TraceEventType.TOOL_CALL_CREATED,
    TraceEventType.TOOL_CALL_STARTED,
    TraceEventType.TOOL_CALL_SUCCEEDED,
    TraceEventType.TOOL_RESULT_NORMALIZED,
    TraceEventType.OBSERVATION_RECORDED,
    TraceEventType.PRESENTATION_PLAN_PROPOSED,
    TraceEventType.RESPONSE_RENDERED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)

LEGACY_ASSERTION_FIELDS = (
    "schema_assertions_pass",
    "identity_boundary_assertions_pass",
    "request_understanding_assertions_pass",
    "input_binding_assertions_pass",
    "task_state_assertions_pass",
    "tool_call_assertions_pass",
    "observation_assertions_pass",
    "disclosure_assertions_pass",
    "renderer_fact_assertions_pass",
    "error_mapping_assertions_pass",
    "persistence_assertions_pass",
    "toolset_replay_assertions_pass",
)


def _expectations(**overrides: object) -> EvalCaseExpectations:
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "trusted_customer_id": "customer-A",
        "expected_http_status": 200,
        "expected_outcome": AgentOutcome.COMPLETED,
        "expected_run_status": AgentRunStatus.COMPLETED,
        "expected_stop_reason": StopReason.GOAL_COMPLETED,
        "expected_response_policy": "DETERMINISTIC_ORDER_SUMMARY_V1",
        "request_understanding_required": True,
        "expected_binding_order_id": "O-1001",
        "expected_next_move_order_id": "O-1001",
        "expected_requested_tool_name": "get_order",
        "expected_task_status": TaskStatus.COMPLETED,
        "expected_request_unit_status": TaskStatus.COMPLETED,
        "expected_task_state_version": 2,
        "expected_request_unit_state_version": 2,
        "expected_gate_decision": GateDecisionValue.ACCEPT,
        "expected_gate_reason": None,
        "expected_validated_task_state_version": 1,
        "expected_tool_call_status": ToolCallStatus.SUCCEEDED,
        "expected_tool_calls": 1,
        "expected_observations": 1,
        "expected_model_calls": 2,
        "expected_presentation_model_calls": 1,
        "expected_message_content": "订单 O-1001 状态怎么样？",
        "expected_tool_registry_version": "e2e01-thin-tools-v1",
        "expected_model_visible_toolset_hash": TOOLSET_HASH,
        "trace_variant": "SUCCESS",
        "required_trace_events": REQUIRED_EVENTS,
        "forbidden_trace_events": (TraceEventType.TOOL_CALL_FAILED,),
        "expected_event_counts": (
            TraceEventCountExpectation(
                event_type=TraceEventType.CONTEXT_MANIFEST_RECORDED,
                count=2,
            ),
            TraceEventCountExpectation(
                event_type=TraceEventType.TASK_STATE_CHANGED,
                count=2,
            ),
            TraceEventCountExpectation(
                event_type=TraceEventType.EVAL_CASE_GRADED,
                count=1,
            ),
        ),
        "applicable_critical_failures": (
            CriticalFailureCode.CF_01,
            CriticalFailureCode.CF_02,
            CriticalFailureCode.CF_04,
            CriticalFailureCode.CF_10,
            CriticalFailureCode.CF_12,
            CriticalFailureCode.CF_13,
            CriticalFailureCode.CF_14,
        ),
    }
    values.update(overrides)
    return EvalCaseExpectations(**values)


def _request_understanding(
    *,
    binding_value: str = "O-1001",
    next_move_value: str = "O-1001",
    source_quote: str | None = None,
) -> RequestUnderstandingOutput:
    return RequestUnderstandingOutput(
        message_ref=MESSAGE_REF,
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=CANDIDATE_ID,
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询指定订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value=binding_value,
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=MESSAGE_REF,
                        source_quote=source_quote or binding_value,
                        confidence=1.0,
                    ),
                ),
                confidence=1.0,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": next_move_value},
            base_task_state_version=None,
        ),
    )


def _observation(
    *,
    order_id: str = "O-1001",
    supersedes: UUID | None = None,
    visibility: ObservationVisibility = ObservationVisibility.MODEL_VISIBLE,
) -> OrderObservation:
    return OrderObservation(
        observation_id=OBSERVATION_ID,
        source_tool="get_order",
        source_resource_ref=order_id,
        source_version="order-v7",
        normalized_type="ORDER_SUMMARY",
        normalized_value=OrderSummaryProjection(
            order_number=order_id,
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at=datetime(2026, 7, 20, 2, 15, tzinfo=UTC),
            status_updated_at=datetime(2026, 7, 24, 9, 30, tzinfo=UTC),
        ),
        observed_at=NOW,
        recorded_at=NOW,
        supersedes=supersedes,
        visibility=visibility,
    )


def _record_reference(
    relation: str,
    target_record_code: P0RecordCode,
    identity_field: str,
    identity_value: UUID,
) -> P0RecordReference:
    return P0RecordReference(
        relation=relation,
        target_record_code=target_record_code,
        target_logical_identity=((identity_field, str(identity_value)),),
    )


def _observation_envelope(
    observation: OrderObservation,
) -> P0PersistenceEnvelope:
    return encode_persistence_record(
        P0RecordCode.OBSERVATION_RECORD,
        observation,
        external_references=(
            _record_reference(
                "source_tool_call_id",
                P0RecordCode.TOOL_CALL_RECORD,
                "tool_call_id",
                TOOL_CALL_ID,
            ),
            _record_reference(
                "source_run_id",
                P0RecordCode.AGENT_RUN_RECORD,
                "run_id",
                RUN_ID,
            ),
            _record_reference(
                "source_task_id",
                P0RecordCode.TASK_RECORD,
                "task_id",
                TASK_ID,
            ),
            _record_reference(
                "source_request_unit_id",
                P0RecordCode.REQUEST_UNIT_RECORD,
                "request_unit_id",
                REQUEST_UNIT_ID,
            ),
        ),
    )


def _manifest(
    *,
    context_id: UUID,
    model_call_id: UUID,
    toolset_hash: str = TOOLSET_HASH,
    include_task: bool = False,
    include_observation: bool = False,
) -> ContextManifest:
    return ContextManifest(
        context_manifest_id=context_id,
        run_id=RUN_ID,
        model_call_id=model_call_id,
        tool_registry_version="e2e01-thin-tools-v1",
        model_visible_toolset_hash=toolset_hash,
        selected_message_refs=(MESSAGE_REF,),
        task_state_ref_and_version=(
            TaskStateRefAndVersion(
                task_id=TASK_ID,
                state_version=1,
            )
            if include_task
            else None
        ),
        observation_refs_and_versions=(
            (
                VersionedRecordRef(
                    record_ref=OBSERVATION_ID,
                    version="order-v7",
                ),
            )
            if include_observation
            else ()
        ),
        redaction_policy_version="p0-redaction-v1",
        token_counts=TokenCounts(),
        assembled_at=NOW,
    )


def _trace(
    event_type: TraceEventType,
    *,
    offset: int,
    context_index: int | None = None,
    case_id: str = "E2E01-01",
    outcome: AgentOutcome = AgentOutcome.COMPLETED,
    stop_reason: StopReason = StopReason.GOAL_COMPLETED,
    gate_decision: GateDecisionValue = GateDecisionValue.ACCEPT,
    gate_reason: GateReasonCode | None = None,
    safe_tool_outcome: ToolResultOutcome = ToolResultOutcome.SUCCESS,
) -> TraceEvent:
    values: dict[str, object] = {
        "trace_event_id": UUID(int=600 + offset),
        "event_type": event_type,
        "occurred_at": NOW + timedelta(milliseconds=offset),
        "run_id": RUN_ID,
        "case_id": case_id,
    }
    if event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED:
        values.update(
            {
                "context_manifest_id": (CONTEXT_1 if context_index == 1 else CONTEXT_2),
                "model_call_id": (MODEL_CALL_1 if context_index == 1 else MODEL_CALL_2),
                "model_call_purpose": (
                    "REQUEST_UNDERSTANDING" if context_index == 1 else "PRESENTATION"
                ),
                "tool_registry_version": "e2e01-thin-tools-v1",
                "model_visible_toolset_hash": TOOLSET_HASH,
            }
        )
    elif event_type is TraceEventType.MESSAGE_ACCEPTED:
        values["message_ref"] = MESSAGE_REF
    elif event_type is TraceEventType.TASK_DELTA_ACCEPTED:
        values.update(
            {
                "message_ref": MESSAGE_REF,
                "accepted_delta_ref": ACCEPTED_DELTA_ID,
                "task_id": TASK_ID,
                "request_unit_id": REQUEST_UNIT_ID,
            }
        )
    elif event_type is TraceEventType.INPUT_BINDING_RECORDED:
        values["input_binding_ref"] = BINDING_ID
    elif event_type is TraceEventType.TASK_STATE_CHANGED:
        values.update(
            {
                "task_id": TASK_ID,
                "request_unit_id": REQUEST_UNIT_ID,
            }
        )
    elif event_type is TraceEventType.NEXT_MOVE_REVALIDATED:
        values["validated_task_state_version"] = 1
    elif event_type is TraceEventType.GATE_DECISION_RECORDED:
        values.update(
            {
                "gate_decision": gate_decision,
                "gate_reason_code": gate_reason,
            }
        )
    elif event_type in {
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.TOOL_CALL_STARTED,
        TraceEventType.TOOL_CALL_SUCCEEDED,
        TraceEventType.TOOL_CALL_FAILED,
        TraceEventType.TOOL_CALL_TIMED_OUT,
        TraceEventType.TOOL_CALL_INTERRUPTED,
    }:
        status_by_type = {
            TraceEventType.TOOL_CALL_CREATED: ToolCallStatus.CREATED,
            TraceEventType.TOOL_CALL_STARTED: ToolCallStatus.RUNNING,
            TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
            TraceEventType.TOOL_CALL_FAILED: ToolCallStatus.FAILED,
            TraceEventType.TOOL_CALL_TIMED_OUT: ToolCallStatus.TIMED_OUT,
            TraceEventType.TOOL_CALL_INTERRUPTED: ToolCallStatus.INTERRUPTED,
        }
        values.update(
            {
                "tool_call_id": TOOL_CALL_ID,
                "tool_call_terminal_status": status_by_type[event_type],
            }
        )
    elif event_type is TraceEventType.TOOL_RESULT_NORMALIZED:
        values.update(
            {
                "tool_call_id": TOOL_CALL_ID,
                "safe_tool_outcome": safe_tool_outcome,
            }
        )
    elif event_type is TraceEventType.OBSERVATION_RECORDED:
        values["observation_ref"] = OBSERVATION_ID
    elif event_type is TraceEventType.RUN_STOPPED:
        values.update(
            {
                "user_outcome": outcome,
                "stop_reason": stop_reason,
            }
        )
    return TraceEvent(**values)


def _trace_events() -> tuple[TraceEvent, ...]:
    return (
        _trace(TraceEventType.MESSAGE_ACCEPTED, offset=0),
        _trace(TraceEventType.RUN_STARTED, offset=1),
        _trace(TraceEventType.REQUEST_UNDERSTANDING_STARTED, offset=2),
        _trace(
            TraceEventType.CONTEXT_MANIFEST_RECORDED,
            offset=3,
            context_index=1,
        ),
        _trace(TraceEventType.NEXT_MOVE_PROPOSED, offset=4),
        _trace(TraceEventType.TASK_DELTA_VALIDATED, offset=5),
        _trace(TraceEventType.TASK_DELTA_ACCEPTED, offset=6),
        _trace(TraceEventType.INPUT_BINDING_RECORDED, offset=7),
        _trace(TraceEventType.TASK_STATE_CHANGED, offset=8),
        _trace(TraceEventType.NEXT_MOVE_REVALIDATED, offset=9),
        _trace(TraceEventType.GATE_DECISION_RECORDED, offset=10),
        _trace(TraceEventType.TOOL_CALL_CREATED, offset=11),
        _trace(TraceEventType.TOOL_CALL_STARTED, offset=12),
        _trace(TraceEventType.TOOL_CALL_SUCCEEDED, offset=13),
        _trace(TraceEventType.TOOL_RESULT_NORMALIZED, offset=14),
        _trace(TraceEventType.OBSERVATION_RECORDED, offset=15),
        _trace(
            TraceEventType.CONTEXT_MANIFEST_RECORDED,
            offset=16,
            context_index=2,
        ),
        _trace(TraceEventType.PRESENTATION_PLAN_PROPOSED, offset=17),
        _trace(TraceEventType.RESPONSE_RENDERED, offset=18),
        _trace(TraceEventType.TASK_STATE_CHANGED, offset=19),
        _trace(TraceEventType.RUN_STOPPED, offset=20),
        _trace(TraceEventType.EVAL_CASE_GRADED, offset=21),
    )


@dataclass(frozen=True, slots=True)
class _TraceOccurrence:
    event_type: TraceEventType
    occurrence: int = 1


_SUCCESS_SAFETY_PRECEDENCE_EDGES = (
    (
        _TraceOccurrence(TraceEventType.MESSAGE_ACCEPTED),
        _TraceOccurrence(TraceEventType.RUN_STARTED),
    ),
    (
        _TraceOccurrence(TraceEventType.RUN_STARTED),
        _TraceOccurrence(TraceEventType.REQUEST_UNDERSTANDING_STARTED),
    ),
    (
        _TraceOccurrence(TraceEventType.REQUEST_UNDERSTANDING_STARTED),
        _TraceOccurrence(TraceEventType.CONTEXT_MANIFEST_RECORDED, 1),
    ),
    (
        _TraceOccurrence(TraceEventType.CONTEXT_MANIFEST_RECORDED, 1),
        _TraceOccurrence(TraceEventType.NEXT_MOVE_PROPOSED),
    ),
    (
        _TraceOccurrence(TraceEventType.NEXT_MOVE_PROPOSED),
        _TraceOccurrence(TraceEventType.TASK_DELTA_VALIDATED),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_DELTA_VALIDATED),
        _TraceOccurrence(TraceEventType.TASK_DELTA_ACCEPTED),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_DELTA_ACCEPTED),
        _TraceOccurrence(TraceEventType.INPUT_BINDING_RECORDED),
    ),
    (
        _TraceOccurrence(TraceEventType.INPUT_BINDING_RECORDED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 1),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 1),
        _TraceOccurrence(TraceEventType.NEXT_MOVE_REVALIDATED),
    ),
    (
        _TraceOccurrence(TraceEventType.NEXT_MOVE_REVALIDATED),
        _TraceOccurrence(TraceEventType.GATE_DECISION_RECORDED),
    ),
    (
        _TraceOccurrence(TraceEventType.GATE_DECISION_RECORDED),
        _TraceOccurrence(TraceEventType.TOOL_CALL_CREATED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_CALL_CREATED),
        _TraceOccurrence(TraceEventType.TOOL_CALL_STARTED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_CALL_STARTED),
        _TraceOccurrence(TraceEventType.TOOL_CALL_SUCCEEDED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_CALL_SUCCEEDED),
        _TraceOccurrence(TraceEventType.TOOL_RESULT_NORMALIZED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_RESULT_NORMALIZED),
        _TraceOccurrence(TraceEventType.OBSERVATION_RECORDED),
    ),
    (
        _TraceOccurrence(TraceEventType.OBSERVATION_RECORDED),
        _TraceOccurrence(TraceEventType.CONTEXT_MANIFEST_RECORDED, 2),
    ),
    (
        _TraceOccurrence(TraceEventType.CONTEXT_MANIFEST_RECORDED, 2),
        _TraceOccurrence(TraceEventType.PRESENTATION_PLAN_PROPOSED),
    ),
    (
        _TraceOccurrence(TraceEventType.PRESENTATION_PLAN_PROPOSED),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
    ),
    (
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
        _TraceOccurrence(TraceEventType.EVAL_CASE_GRADED),
    ),
)


_COMMON_PREFIX = (
    TraceEventType.MESSAGE_ACCEPTED,
    TraceEventType.RUN_STARTED,
    TraceEventType.REQUEST_UNDERSTANDING_STARTED,
    TraceEventType.CONTEXT_MANIFEST_RECORDED,
)
_CANDIDATE_PREFIX = (
    TraceEventType.NEXT_MOVE_PROPOSED,
    TraceEventType.TASK_DELTA_VALIDATED,
    TraceEventType.TASK_DELTA_ACCEPTED,
    TraceEventType.INPUT_BINDING_RECORDED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.NEXT_MOVE_REVALIDATED,
)
_COMMON_PREFIX_EDGES = _SUCCESS_SAFETY_PRECEDENCE_EDGES[:3]
_CANDIDATE_EDGES = _SUCCESS_SAFETY_PRECEDENCE_EDGES[3:10]
_TERMINAL_EDGE = (
    (
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
        _TraceOccurrence(TraceEventType.EVAL_CASE_GRADED),
    ),
)


@dataclass(frozen=True, slots=True)
class _TraceVariant:
    variant_id: str
    script_refs: tuple[str, ...]
    sequence: tuple[TraceEventType, ...]
    edges: tuple[tuple[_TraceOccurrence, _TraceOccurrence], ...]
    outcome: AgentOutcome
    stop_reason: StopReason
    response_policy: str
    task_status: TaskStatus | None
    task_state_version: int | None
    gate_decision: GateDecisionValue | None
    gate_reason: GateReasonCode | None
    tool_status: ToolCallStatus | None
    safe_tool_outcome: ToolResultOutcome
    observations: int
    model_calls: int
    presentation_model_calls: int


_TASKLESS_SEQUENCE = (
    *_COMMON_PREFIX,
    TraceEventType.RESPONSE_RENDERED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)
_TASKLESS_EDGES = (
    *_COMMON_PREFIX_EDGES,
    (
        _TraceOccurrence(TraceEventType.CONTEXT_MANIFEST_RECORDED),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
    ),
    *_TERMINAL_EDGE,
)
_GATEWAY_SEQUENCE = (
    *_COMMON_PREFIX,
    *_CANDIDATE_PREFIX,
    TraceEventType.GATE_DECISION_RECORDED,
    TraceEventType.RESPONSE_RENDERED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)
_GATEWAY_EDGES = (
    *_COMMON_PREFIX_EDGES,
    *_CANDIDATE_EDGES,
    (
        _TraceOccurrence(TraceEventType.GATE_DECISION_RECORDED),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
    ),
    *_TERMINAL_EDGE,
)
_STALE_SEQUENCE = (
    *_COMMON_PREFIX,
    TraceEventType.NEXT_MOVE_PROPOSED,
    TraceEventType.TASK_DELTA_VALIDATED,
    TraceEventType.TASK_DELTA_ACCEPTED,
    TraceEventType.INPUT_BINDING_RECORDED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.NEXT_MOVE_REVALIDATED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.GATE_DECISION_RECORDED,
    TraceEventType.RESPONSE_RENDERED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)
_STALE_EDGES = (
    *_COMMON_PREFIX_EDGES,
    *_CANDIDATE_EDGES[:-1],
    (
        _TraceOccurrence(TraceEventType.NEXT_MOVE_REVALIDATED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
        _TraceOccurrence(TraceEventType.GATE_DECISION_RECORDED),
    ),
    (
        _TraceOccurrence(TraceEventType.GATE_DECISION_RECORDED),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 3),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 3),
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
    ),
    *_TERMINAL_EDGE,
)
_FAILED_TOOL_SEQUENCE = (
    *_COMMON_PREFIX,
    *_CANDIDATE_PREFIX,
    TraceEventType.GATE_DECISION_RECORDED,
    TraceEventType.TOOL_CALL_CREATED,
    TraceEventType.TOOL_CALL_STARTED,
    TraceEventType.TOOL_CALL_FAILED,
    TraceEventType.TOOL_RESULT_NORMALIZED,
    TraceEventType.RESPONSE_RENDERED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)
_FAILED_TOOL_EDGES = (
    *_COMMON_PREFIX_EDGES,
    *_CANDIDATE_EDGES,
    (
        _TraceOccurrence(TraceEventType.GATE_DECISION_RECORDED),
        _TraceOccurrence(TraceEventType.TOOL_CALL_CREATED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_CALL_CREATED),
        _TraceOccurrence(TraceEventType.TOOL_CALL_STARTED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_CALL_STARTED),
        _TraceOccurrence(TraceEventType.TOOL_CALL_FAILED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_CALL_FAILED),
        _TraceOccurrence(TraceEventType.TOOL_RESULT_NORMALIZED),
    ),
    (
        _TraceOccurrence(TraceEventType.TOOL_RESULT_NORMALIZED),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
    ),
    *_TERMINAL_EDGE,
)
_PRESENTATION_FAULT_SEQUENCE = (
    *_COMMON_PREFIX,
    *_CANDIDATE_PREFIX,
    TraceEventType.GATE_DECISION_RECORDED,
    TraceEventType.TOOL_CALL_CREATED,
    TraceEventType.TOOL_CALL_STARTED,
    TraceEventType.TOOL_CALL_SUCCEEDED,
    TraceEventType.TOOL_RESULT_NORMALIZED,
    TraceEventType.OBSERVATION_RECORDED,
    TraceEventType.CONTEXT_MANIFEST_RECORDED,
    TraceEventType.RESPONSE_RENDERED,
    TraceEventType.TASK_STATE_CHANGED,
    TraceEventType.RUN_STOPPED,
    TraceEventType.EVAL_CASE_GRADED,
)
_PRESENTATION_FAULT_EDGES = (
    *_SUCCESS_SAFETY_PRECEDENCE_EDGES[:16],
    (
        _TraceOccurrence(TraceEventType.CONTEXT_MANIFEST_RECORDED, 2),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.OBSERVATION_RECORDED),
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
    ),
    (
        _TraceOccurrence(TraceEventType.RESPONSE_RENDERED),
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
    ),
    (
        _TraceOccurrence(TraceEventType.TASK_STATE_CHANGED, 2),
        _TraceOccurrence(TraceEventType.RUN_STOPPED),
    ),
    *_TERMINAL_EDGE,
)


_TRACE_VARIANTS = (
    _TraceVariant(
        variant_id="SUCCESS",
        script_refs=("script:e2e01-01:success",),
        sequence=tuple(event.event_type for event in _trace_events()),
        edges=_SUCCESS_SAFETY_PRECEDENCE_EDGES,
        outcome=AgentOutcome.COMPLETED,
        stop_reason=StopReason.GOAL_COMPLETED,
        response_policy="DETERMINISTIC_ORDER_SUMMARY_V1",
        task_status=TaskStatus.COMPLETED,
        task_state_version=2,
        gate_decision=GateDecisionValue.ACCEPT,
        gate_reason=None,
        tool_status=ToolCallStatus.SUCCEEDED,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=1,
        model_calls=2,
        presentation_model_calls=1,
    ),
    _TraceVariant(
        variant_id="FOREIGN_ORDER",
        script_refs=("script:e2e01-04-a:foreign-order",),
        sequence=_FAILED_TOOL_SEQUENCE,
        edges=_FAILED_TOOL_EDGES,
        outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
        response_policy="FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
        task_status=TaskStatus.COMPLETED,
        task_state_version=2,
        gate_decision=GateDecisionValue.ACCEPT,
        gate_reason=None,
        tool_status=ToolCallStatus.FAILED,
        safe_tool_outcome=ToolResultOutcome.BUSINESS_FAILURE,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="NONEXISTENT_ORDER",
        script_refs=("script:e2e01-04-b:nonexistent-order",),
        sequence=_FAILED_TOOL_SEQUENCE,
        edges=_FAILED_TOOL_EDGES,
        outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
        response_policy="FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
        task_status=TaskStatus.COMPLETED,
        task_state_version=2,
        gate_decision=GateDecisionValue.ACCEPT,
        gate_reason=None,
        tool_status=ToolCallStatus.FAILED,
        safe_tool_outcome=ToolResultOutcome.BUSINESS_FAILURE,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="ARGUMENT_BINDING_REJECTED",
        script_refs=(
            "script:sec-argument-binding:foreign-order",
            "script:sec-argument-binding:nonexistent-order",
        ),
        sequence=_GATEWAY_SEQUENCE,
        edges=_GATEWAY_EDGES,
        outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.GATE_REJECTED,
        response_policy="FIXED_SAFE_PROCESSING_ERROR",
        task_status=TaskStatus.BLOCKED,
        task_state_version=2,
        gate_decision=GateDecisionValue.REJECT,
        gate_reason=GateReasonCode.ARGUMENT_BINDING_MISMATCH,
        tool_status=None,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="PROVIDER_PROTOCOL_BEFORE_CANDIDATE",
        script_refs=(
            "script:fault-provider:zero-target-functions",
            "script:fault-provider:multiple-target-functions",
        ),
        sequence=_TASKLESS_SEQUENCE,
        edges=_TASKLESS_EDGES,
        outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
        response_policy="FIXED_SAFE_PROCESSING_ERROR",
        task_status=None,
        task_state_version=None,
        gate_decision=None,
        gate_reason=None,
        tool_status=None,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="INPUT_VALIDATION_REJECTED",
        script_refs=(
            "script:fault-provider:invalid-request-understanding-schema",
            "script:fault-provider:source-authority-mismatch",
            "script:fault-provider:trusted-field-override",
        ),
        sequence=_TASKLESS_SEQUENCE,
        edges=_TASKLESS_EDGES,
        outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.INPUT_INVALID,
        response_policy="FIXED_SAFE_PROCESSING_ERROR",
        task_status=None,
        task_state_version=None,
        gate_decision=None,
        gate_reason=None,
        tool_status=None,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="UNKNOWN_TOOL_GATEWAY_REJECTED",
        script_refs=("script:fault-provider:unknown-tool-name",),
        sequence=_GATEWAY_SEQUENCE,
        edges=_GATEWAY_EDGES,
        outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.GATE_REJECTED,
        response_policy="FIXED_SAFE_PROCESSING_ERROR",
        task_status=TaskStatus.BLOCKED,
        task_state_version=2,
        gate_decision=GateDecisionValue.REJECT,
        gate_reason=GateReasonCode.TOOL_NOT_REGISTERED,
        tool_status=None,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="STALE_STATE_GATEWAY_REJECTED",
        script_refs=("script:fault-runtime:state-advanced-before-gate",),
        sequence=_STALE_SEQUENCE,
        edges=_STALE_EDGES,
        outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.GATE_REJECTED,
        response_policy="FIXED_SAFE_PROCESSING_ERROR",
        task_status=TaskStatus.BLOCKED,
        task_state_version=3,
        gate_decision=GateDecisionValue.REJECT,
        gate_reason=GateReasonCode.STATE_VERSION_MISMATCH,
        tool_status=None,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=0,
        model_calls=1,
        presentation_model_calls=0,
    ),
    _TraceVariant(
        variant_id="PRESENTATION_PROTOCOL_REJECTED",
        script_refs=(
            "script:fault-presentation:zero-target-functions",
            "script:fault-presentation:multiple-target-functions",
            "script:fault-presentation:invalid-schema",
            "script:fault-presentation:fact-bearing-envelope",
        ),
        sequence=_PRESENTATION_FAULT_SEQUENCE,
        edges=_PRESENTATION_FAULT_EDGES,
        outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
        response_policy="FIXED_SAFE_PROCESSING_ERROR",
        task_status=TaskStatus.BLOCKED,
        task_state_version=2,
        gate_decision=GateDecisionValue.ACCEPT,
        gate_reason=None,
        tool_status=ToolCallStatus.SUCCEEDED,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
        observations=1,
        model_calls=2,
        presentation_model_calls=1,
    ),
)


def _occurrence_index(
    events: tuple[TraceEvent, ...],
    target: _TraceOccurrence,
) -> int:
    matches = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type is target.event_type
    )
    return matches[target.occurrence - 1]


def _swap_precedence_edge(
    events: tuple[TraceEvent, ...],
    before: _TraceOccurrence,
    after: _TraceOccurrence,
) -> tuple[TraceEvent, ...]:
    reordered = list(events)
    before_index = _occurrence_index(events, before)
    after_index = _occurrence_index(events, after)
    reordered[before_index], reordered[after_index] = (
        reordered[after_index],
        reordered[before_index],
    )
    return tuple(
        event.model_copy(
            update={"occurred_at": NOW + timedelta(milliseconds=index)}
        )
        for index, event in enumerate(reordered)
    )


def _variant_trace_events(variant: _TraceVariant) -> tuple[TraceEvent, ...]:
    context_occurrence = 0
    events: list[TraceEvent] = []
    for index, event_type in enumerate(variant.sequence):
        context_index: int | None = None
        if event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED:
            context_occurrence += 1
            context_index = context_occurrence
        events.append(
            _trace(
                event_type,
                offset=index,
                context_index=context_index,
                outcome=variant.outcome,
                stop_reason=variant.stop_reason,
                gate_decision=(
                    variant.gate_decision
                    if variant.gate_decision is not None
                    else GateDecisionValue.ACCEPT
                ),
                gate_reason=variant.gate_reason,
                safe_tool_outcome=variant.safe_tool_outcome,
            )
        )
    return tuple(events)


def _variant_expectations(variant: _TraceVariant) -> EvalCaseExpectations:
    event_counts = Counter(variant.sequence)
    counted_types = (
        TraceEventType.CONTEXT_MANIFEST_RECORDED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.OBSERVATION_RECORDED,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )
    optional_safety_types = (
        TraceEventType.NEXT_MOVE_PROPOSED,
        TraceEventType.TASK_DELTA_VALIDATED,
        TraceEventType.TASK_DELTA_ACCEPTED,
        TraceEventType.INPUT_BINDING_RECORDED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.NEXT_MOVE_REVALIDATED,
        TraceEventType.GATE_DECISION_RECORDED,
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.TOOL_CALL_STARTED,
        TraceEventType.TOOL_CALL_SUCCEEDED,
        TraceEventType.TOOL_CALL_FAILED,
        TraceEventType.TOOL_CALL_TIMED_OUT,
        TraceEventType.TOOL_CALL_INTERRUPTED,
        TraceEventType.TOOL_RESULT_NORMALIZED,
        TraceEventType.OBSERVATION_RECORDED,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )
    values: dict[str, object] = {
        "expected_outcome": variant.outcome,
        "expected_stop_reason": variant.stop_reason,
        "expected_response_policy": variant.response_policy,
        "request_understanding_required": variant.task_status is not None,
        "expected_binding_order_id": (
            "O-1001" if variant.task_status is not None else None
        ),
        "expected_next_move_order_id": (
            "O-1001" if variant.task_status is not None else None
        ),
        "expected_requested_tool_name": (
            "get_order" if variant.task_status is not None else None
        ),
        "expected_task_status": variant.task_status,
        "expected_request_unit_status": variant.task_status,
        "expected_task_state_version": variant.task_state_version,
        "expected_request_unit_state_version": variant.task_state_version,
        "expected_gate_decision": variant.gate_decision,
        "expected_gate_reason": variant.gate_reason,
        "expected_validated_task_state_version": (
            1 if variant.gate_decision is not None else None
        ),
        "expected_tool_call_status": variant.tool_status,
        "expected_tool_calls": 1 if variant.tool_status is not None else 0,
        "expected_observations": variant.observations,
        "expected_model_calls": variant.model_calls,
        "expected_presentation_model_calls": (
            variant.presentation_model_calls
        ),
        "required_trace_events": tuple(dict.fromkeys(variant.sequence)),
        "forbidden_trace_events": tuple(
            event_type
            for event_type in optional_safety_types
            if event_counts[event_type] == 0
        ),
        "expected_event_counts": tuple(
            TraceEventCountExpectation(
                event_type=event_type,
                count=event_counts[event_type],
            )
            for event_type in counted_types
        ),
    }
    if "trace_variant" in EvalCaseExpectations.model_fields:
        values["trace_variant"] = variant.variant_id
    return _expectations(**values)


def _variant_evidence(
    variant: _TraceVariant,
    *,
    trace_events: tuple[TraceEvent, ...] | None = None,
) -> EvalEvidence:
    base = _evidence()
    events = trace_events or _variant_trace_events(variant)
    run_record = base.run_record.model_copy(
        update={"stop_reason": variant.stop_reason}
    )
    agent_result = base.agent_result.model_copy(
        update={
            "outcome": variant.outcome,
            "message": (
                _rendered_message(base.observations[0])
                if variant.response_policy == "DETERMINISTIC_ORDER_SUMMARY_V1"
                else "当前无法安全处理该请求，请稍后重试。"
            ),
        }
    )
    observable = SafeCaseObservable(
        case_id="E2E01-01",
        http_status=200,
        user_outcome=variant.outcome,
        response_policy=variant.response_policy,
        ordinary_trace_shape=ordinary_trace_shape(events),
        model_calls=variant.model_calls,
    )
    common: dict[str, object] = {
        "observed_outcome": variant.outcome,
        "trace_events": events,
        "safe_observable": observable,
        "run_record": run_record,
        "agent_result": agent_result,
        "context_manifests": base.context_manifests[: variant.model_calls],
    }
    if variant.task_status is None:
        common.update(
            {
                "request_understanding_output": None,
                "request_understanding_records": (),
                "accepted_task_deltas": (),
                "input_bindings": (),
                "task_records": (),
                "request_units": (),
                "conversation_task_links": (),
                "run_task_links": (),
                "gate_decisions": (),
                "tool_calls": (),
                "tool_attempts": (),
                "observations": (),
                "observation_persistence_envelopes": (),
            }
        )
        return _evidence(**common)

    assert variant.task_state_version is not None
    task = base.task_records[0].model_copy(
        update={
            "status": variant.task_status,
            "state_version": variant.task_state_version,
        }
    )
    unit = base.request_units[0].model_copy(
        update={
            "status": variant.task_status,
            "state_version": variant.task_state_version,
            "observation_refs": (
                (OBSERVATION_ID,) if variant.observations == 1 else ()
            ),
        }
    )
    run_link = base.run_task_links[0].model_copy(
        update={"result_task_state_version": variant.task_state_version}
    )
    gate_decisions: tuple[GateDecision, ...] = ()
    if variant.gate_decision is not None:
        failed_check_by_reason = {
            GateReasonCode.ARGUMENT_BINDING_MISMATCH: "argument_binding_valid",
            GateReasonCode.STATE_VERSION_MISMATCH: "state_version_valid",
            GateReasonCode.TOOL_NOT_REGISTERED: "registration_valid",
        }
        gate_updates: dict[str, object] = {
            "decision": variant.gate_decision,
            "reason_code": variant.gate_reason,
        }
        if variant.gate_decision is GateDecisionValue.REJECT:
            assert variant.gate_reason in failed_check_by_reason
            gate_updates[failed_check_by_reason[variant.gate_reason]] = False
        gate_decisions = (
            base.gate_decisions[0].model_copy(
                update=gate_updates
            ),
        )
    tool_calls: tuple[ToolCallRecord, ...] = ()
    tool_attempts: tuple[ToolAttemptRecord, ...] = ()
    if variant.tool_status is not None:
        failure_code = (
            None
            if variant.tool_status is ToolCallStatus.SUCCEEDED
            else "NOT_FOUND_OR_NOT_ACCESSIBLE"
        )
        result_ref = (
            TOOL_RESULT_REF
            if variant.tool_status is ToolCallStatus.SUCCEEDED
            else None
        )
        tool_calls = (
            base.tool_calls[0].model_copy(
                update={
                    "status": variant.tool_status,
                    "failure_code": failure_code,
                    "result_ref": result_ref,
                }
            ),
        )
        tool_attempts = (
            base.tool_attempts[0].model_copy(
                update={
                    "outcome": variant.safe_tool_outcome,
                    "failure_code": failure_code,
                }
            ),
        )
    common.update(
        {
            "task_records": (task,),
            "request_units": (unit,),
            "run_task_links": (run_link,),
            "gate_decisions": gate_decisions,
            "tool_calls": tool_calls,
            "tool_attempts": tool_attempts,
            "observations": (
                base.observations if variant.observations == 1 else ()
            ),
            "observation_persistence_envelopes": (
                base.observation_persistence_envelopes
                if variant.observations == 1
                else ()
            ),
        }
    )
    return _evidence(**common)


def _rendered_message(observation: OrderObservation) -> str:
    summary = observation.normalized_value
    return "\n".join(
        (
            "已为你查到订单信息：",
            f"订单号：{summary.order_number}",
            "状态：已发货",
            "商品："
            + "、".join(
                f"{item.product_name} × {item.quantity}" for item in summary.line_items
            ),
            f"下单时间：{summary.ordered_at.strftime('%Y-%m-%d %H:%M UTC')}",
            (
                "状态更新时间："
                f"{summary.status_updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            "如需继续查询配送信息，请告诉我。",
        )
    )


def _evidence(**overrides: object) -> EvalEvidence:
    observation = _observation()
    trace_events = _trace_events()
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": TRACE_REF,
        "trace_events": trace_events,
        "safe_observable": SafeCaseObservable(
            case_id="E2E01-01",
            http_status=200,
            user_outcome=AgentOutcome.COMPLETED,
            response_policy="DETERMINISTIC_ORDER_SUMMARY_V1",
            ordinary_trace_shape=ordinary_trace_shape(trace_events),
            model_calls=2,
        ),
        "run_record": AgentRunRecord(
            run_id=RUN_ID,
            conversation_id=CONVERSATION_ID,
            status=AgentRunStatus.COMPLETED,
            provider_lane="offline_gate",
            started_at=NOW,
            completed_at=NOW + timedelta(seconds=1),
            stop_reason=StopReason.GOAL_COMPLETED,
        ),
        "agent_result": AgentRunResult(
            run_id=RUN_ID,
            outcome=AgentOutcome.COMPLETED,
            message=_rendered_message(observation),
        ),
        "conversation_records": (
            ConversationRecord(
                schema_version="conversation_record.p0.v1",
                conversation_id=CONVERSATION_ID,
                owner_customer_id="customer-A",
                created_at=NOW,
            ),
        ),
        "message_records": (
            MessageRecord(
                schema_version="message_record.p0.v1",
                message_id=MESSAGE_REF,
                conversation_id=CONVERSATION_ID,
                direction=MessageDirection.USER,
                content="订单 O-1001 状态怎么样？",
                received_at=NOW,
            ),
        ),
        "request_understanding_output": _request_understanding(),
        "request_understanding_records": (
            RequestUnderstandingRecord(
                run_id=RUN_ID,
                message_ref=MESSAGE_REF,
                schema_version="request_understanding_record.p0.v1",
                candidate_validation=(
                    CandidateValidationRecord(
                        candidate_ref=CANDIDATE_ID,
                        decision=CandidateValidationDecision.ACCEPT,
                    ),
                ),
                accepted_delta_refs=(ACCEPTED_DELTA_ID,),
                proposed_base_task_state_version=None,
                validated_task_state_version=1,
                next_move_candidate_ref=NEXT_MOVE_REF,
            ),
        ),
        "accepted_task_deltas": (
            AcceptedTaskDelta(
                accepted_delta_id=ACCEPTED_DELTA_ID,
                candidate_ref=CANDIDATE_ID,
                message_ref=MESSAGE_REF,
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_text="查询指定订单状态",
                input_binding_refs=(BINDING_ID,),
                accepted_at=NOW,
            ),
        ),
        "input_bindings": (
            InputBinding(
                binding_id=BINDING_ID,
                name="order_id",
                normalized_value="O-1001",
                authority=InputAuthority.USER_CLAIM,
                source_refs=(MESSAGE_REF,),
                validation_status=InputValidationStatus.ACCEPTED,
                confirmed_by_user=True,
                created_at=NOW,
                updated_at=NOW,
            ),
        ),
        "task_records": (
            TaskRecord(
                task_id=TASK_ID,
                owner_customer_id="customer-A",
                status=TaskStatus.COMPLETED,
                state_version=2,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            ),
        ),
        "request_units": (
            RequestUnitRecord(
                request_unit_id=REQUEST_UNIT_ID,
                task_id=TASK_ID,
                goal_text="查询指定订单状态",
                goal_source_refs=(MESSAGE_REF,),
                input_binding_refs=(BINDING_ID,),
                observation_refs=(OBSERVATION_ID,),
                status=TaskStatus.COMPLETED,
                state_version=2,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            ),
        ),
        "conversation_task_links": (
            ConversationTaskLinkRecord(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=CONVERSATION_ID,
                task_id=TASK_ID,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=NOW,
            ),
        ),
        "run_task_links": (
            RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=RUN_ID,
                task_id=TASK_ID,
                base_task_state_version=None,
                result_task_state_version=2,
            ),
        ),
        "gate_decisions": (
            GateDecision(
                gate_decision_id=GATE_ID,
                model_call_id=MODEL_CALL_1,
                context_manifest_id=CONTEXT_1,
                provider_tool_call_id="provider-call-1",
                requested_provider_tool_name="get_order",
                resolved_canonical_tool_name="get_order",
                snapshot_match=True,
                registration_valid=True,
                schema_valid=True,
                trusted_field_valid=True,
                argument_binding_valid=True,
                argument_binding_refs=(BINDING_ID,),
                budget_valid=True,
                progress_valid=True,
                proposed_base_task_state_version=None,
                validated_task_state_version=1,
                state_version_valid=True,
                action_boundary_valid=True,
                decision=GateDecisionValue.ACCEPT,
                decided_at=NOW,
            ),
        ),
        "tool_calls": (
            ToolCallRecord(
                tool_call_id=TOOL_CALL_ID,
                run_id=RUN_ID,
                task_id=TASK_ID,
                request_unit_id=REQUEST_UNIT_ID,
                model_call_id=MODEL_CALL_1,
                context_manifest_id=CONTEXT_1,
                gate_decision_id=GATE_ID,
                provider_tool_call_id="provider-call-1",
                canonical_tool_name="get_order",
                tool_registry_version="e2e01-thin-tools-v1",
                validated_task_state_version=1,
                argument_binding_refs=(BINDING_ID,),
                effect=ToolEffect.READ,
                attempt_count=1,
                status=ToolCallStatus.SUCCEEDED,
                started_at=NOW,
                finished_at=NOW + timedelta(milliseconds=500),
                result_ref=TOOL_RESULT_REF,
            ),
        ),
        "tool_attempts": (
            ToolAttemptRecord(
                tool_call_id=TOOL_CALL_ID,
                attempt_no=1,
                started_at=NOW,
                finished_at=NOW + timedelta(milliseconds=500),
                outcome=ToolResultOutcome.SUCCESS,
            ),
        ),
        "observations": (observation,),
        "observation_persistence_envelopes": (_observation_envelope(observation),),
        "context_manifests": (
            _manifest(
                context_id=CONTEXT_1,
                model_call_id=MODEL_CALL_1,
            ),
            _manifest(
                context_id=CONTEXT_2,
                model_call_id=MODEL_CALL_2,
                include_task=True,
                include_observation=True,
            ),
        ),
        "model_visible_toolset_artifacts": (
            ModelVisibleToolsetArtifact(
                model_visible_toolset_hash=TOOLSET_HASH,
                provider_visible_tool_specs=(get_order_tool_spec(),),
            ),
        ),
    }
    values.update({field: True for field in LEGACY_ASSERTION_FIELDS})
    values.update(overrides)
    return EvalEvidence(**values)


def _minimal_self_attested_evidence() -> EvalEvidence:
    events = (
        _trace(TraceEventType.RUN_STARTED, offset=1),
        _trace(TraceEventType.RUN_STOPPED, offset=2),
        _trace(TraceEventType.EVAL_CASE_GRADED, offset=3),
    )
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": TRACE_REF,
        "trace_events": events,
        "safe_observable": SafeCaseObservable(
            case_id="E2E01-01",
            http_status=200,
            user_outcome=AgentOutcome.COMPLETED,
            response_policy="DETERMINISTIC_ORDER_SUMMARY_V1",
            ordinary_trace_shape=ordinary_trace_shape(events),
            model_calls=2,
        ),
        "run_record": AgentRunRecord(
            run_id=RUN_ID,
            status=AgentRunStatus.COMPLETED,
            provider_lane="offline_gate",
            started_at=NOW,
            completed_at=NOW + timedelta(seconds=1),
            stop_reason=StopReason.GOAL_COMPLETED,
        ),
        "agent_result": AgentRunResult(
            run_id=RUN_ID,
            outcome=AgentOutcome.COMPLETED,
            message="SUT claims this is valid",
        ),
    }
    values.update({field: True for field in LEGACY_ASSERTION_FIELDS})
    return EvalEvidence(**values)


def _tampered(grader_name: str) -> EvalEvidence:
    evidence = _evidence()
    if grader_name == "SchemaGrader":
        return _evidence(
            agent_result=AgentRunResult(
                run_id=OTHER_RUN_ID,
                outcome=AgentOutcome.COMPLETED,
                message=evidence.agent_result.message,
            )
        )
    if grader_name == "IdentityBoundaryGrader":
        task = evidence.task_records[0].model_copy(
            update={"owner_customer_id": "customer-B"}
        )
        return _evidence(task_records=(task,))
    if grader_name == "RequestUnderstandingGrader":
        return _evidence(
            request_understanding_output=_request_understanding(
                next_move_value="O-2001"
            )
        )
    if grader_name == "InputBindingGrader":
        binding = evidence.input_bindings[0].model_copy(
            update={"normalized_value": "O-2001"}
        )
        return _evidence(input_bindings=(binding,))
    if grader_name == "TaskStateGrader":
        task = evidence.task_records[0].model_copy(update={"state_version": 3})
        return _evidence(task_records=(task,))
    if grader_name == "ToolCallGrader":
        call = evidence.tool_calls[0].model_copy(
            update={
                "status": ToolCallStatus.FAILED,
                "failure_code": "ORDER_LOOKUP_FAILED",
                "result_ref": None,
            }
        )
        return _evidence(tool_calls=(call,))
    if grader_name == "ObservationGrader":
        return _evidence(observations=(_observation(order_id="O-2001"),))
    if grader_name == "DisclosureGrader":
        observable = evidence.safe_observable.model_copy(
            update={"response_policy": "FIXED_SAFE_PROCESSING_ERROR"}
        )
        return _evidence(safe_observable=observable)
    if grader_name == "RendererFactGrader":
        return _evidence(
            agent_result=AgentRunResult(
                run_id=RUN_ID,
                outcome=AgentOutcome.COMPLETED,
                message="O-1001",
            )
        )
    if grader_name == "ErrorMappingGrader":
        run = evidence.run_record.model_copy(
            update={
                "stop_reason": StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
            }
        )
        return _evidence(run_record=run)
    if grader_name == "TraceCompletenessGrader":
        return _evidence(
            trace_events=tuple(
                event
                for event in evidence.trace_events
                if event.event_type is not TraceEventType.EVAL_CASE_GRADED
            )
        )
    if grader_name == "PersistenceGrader":
        unit = evidence.request_units[0].model_copy(update={"task_id": UUID(int=999)})
        return _evidence(request_units=(unit,))
    if grader_name == "ToolsetReplayGrader":
        manifest = _manifest(
            context_id=CONTEXT_2,
            model_call_id=MODEL_CALL_2,
            toolset_hash=f"sha256:{'b' * 64}",
            include_task=True,
            include_observation=True,
        )
        return _evidence(context_manifests=(evidence.context_manifests[0], manifest))
    raise AssertionError(f"unhandled grader {grader_name}")


_TRACE_VARIANT_SCRIPT_CASES = tuple(
    (variant, script_ref)
    for variant in _TRACE_VARIANTS
    for script_ref in variant.script_refs
)
_TRACE_VARIANT_EDGE_CASES = tuple(
    (variant, before, after)
    for variant in _TRACE_VARIANTS
    for before, after in variant.edges
)


@pytest.mark.parametrize(
    ("variant", "script_ref"),
    _TRACE_VARIANT_SCRIPT_CASES,
    ids=tuple(
        f"{variant.variant_id}:{script_ref}"
        for variant, script_ref in _TRACE_VARIANT_SCRIPT_CASES
    ),
)
def test_trace_precedence_canonical_passes_for_every_authenticated_script_ref(
    variant: _TraceVariant,
    script_ref: str,
) -> None:
    all_refs = tuple(
        ref for item in _TRACE_VARIANTS for ref in item.script_refs
    )
    assert len(_TRACE_VARIANTS) == 9
    assert len(all_refs) == len(set(all_refs)) == 16
    assert script_ref in variant.script_refs

    outcome = grade_evidence(
        ("TraceCompletenessGrader",),
        _variant_evidence(variant),
        _variant_expectations(variant),
    )

    assert outcome.status is EvalResultStatus.PASS


@pytest.mark.parametrize(
    ("variant", "before", "after"),
    _TRACE_VARIANT_EDGE_CASES,
    ids=tuple(
        (
            f"{variant.variant_id}:"
            f"{before.event_type.value}#{before.occurrence}-before-"
            f"{after.event_type.value}#{after.occurrence}"
        )
        for variant, before, after in _TRACE_VARIANT_EDGE_CASES
    ),
)
def test_reordered_trace_precedence_fails_for_every_structural_variant(
    variant: _TraceVariant,
    before: _TraceOccurrence,
    after: _TraceOccurrence,
) -> None:
    canonical = _variant_trace_events(variant)
    reordered = _swap_precedence_edge(canonical, before, after)

    assert {event.trace_event_id for event in reordered} == {
        event.trace_event_id for event in canonical
    }
    assert tuple(event.event_type for event in reordered).count(
        before.event_type
    ) == tuple(event.event_type for event in canonical).count(before.event_type)
    assert tuple(event.occurred_at for event in reordered) == tuple(
        sorted(event.occurred_at for event in reordered)
    )

    outcome = grade_evidence(
        ("TraceCompletenessGrader",),
        _variant_evidence(variant, trace_events=reordered),
        _variant_expectations(variant),
    )

    assert outcome.status is EvalResultStatus.FAIL
    assert outcome.grader_results[0].reason_code is (
        EvalGraderReasonCode.ASSERTION_FAILED
    )


@pytest.mark.parametrize(
    "variant",
    _TRACE_VARIANTS,
    ids=tuple(item.variant_id for item in _TRACE_VARIANTS),
)
def test_trace_precedence_missing_endpoint_fails_closed(
    variant: _TraceVariant,
) -> None:
    without_response = tuple(
        event
        for event in _variant_trace_events(variant)
        if event.event_type is not TraceEventType.RESPONSE_RENDERED
    )

    outcome = grade_evidence(
        ("TraceCompletenessGrader",),
        _variant_evidence(variant, trace_events=without_response),
        _variant_expectations(variant).model_copy(
            update={
                "required_trace_events": tuple(
                    event_type
                    for event_type in _variant_expectations(
                        variant
                    ).required_trace_events
                    if event_type is not TraceEventType.RESPONSE_RENDERED
                )
            }
        ),
    )

    assert outcome.status is EvalResultStatus.FAIL
    assert outcome.grader_results[0].reason_code is (
        EvalGraderReasonCode.TRACE_EVENT_MISSING
    )


@pytest.mark.parametrize(
    "variant",
    _TRACE_VARIANTS,
    ids=tuple(item.variant_id for item in _TRACE_VARIANTS),
)
def test_trace_precedence_allows_unrelated_legal_event_insertion(
    variant: _TraceVariant,
) -> None:
    canonical = list(_variant_trace_events(variant))
    insertion_index = next(
        index
        for index, event in enumerate(canonical)
        if event.event_type is TraceEventType.REQUEST_UNDERSTANDING_STARTED
    )
    canonical.insert(
        insertion_index + 1,
        _trace(
            TraceEventType.REQUEST_UNDERSTANDING_STARTED,
            offset=900,
            outcome=variant.outcome,
            stop_reason=variant.stop_reason,
        ),
    )
    with_extra = tuple(
        event.model_copy(
            update={"occurred_at": NOW + timedelta(milliseconds=index)}
        )
        for index, event in enumerate(canonical)
    )

    outcome = grade_evidence(
        ("TraceCompletenessGrader",),
        _variant_evidence(variant, trace_events=with_extra),
        _variant_expectations(variant),
    )

    assert outcome.status is EvalResultStatus.PASS


def test_trace_precedence_selects_context_manifest_by_authenticated_purpose() -> None:
    variant = next(
        item for item in _TRACE_VARIANTS if item.variant_id == "SUCCESS"
    )
    canonical = list(_variant_trace_events(variant))
    manifest_indexes = tuple(
        index
        for index, event in enumerate(canonical)
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
    )
    assert len(manifest_indexes) == 2
    first_index, second_index = manifest_indexes
    canonical[first_index], canonical[second_index] = (
        canonical[second_index],
        canonical[first_index],
    )
    reordered = tuple(
        event.model_copy(
            update={"occurred_at": NOW + timedelta(milliseconds=index)}
        )
        for index, event in enumerate(canonical)
    )

    outcome = grade_evidence(
        ("TraceCompletenessGrader",),
        _variant_evidence(variant, trace_events=reordered),
        _variant_expectations(variant),
    )

    assert outcome.status is EvalResultStatus.FAIL
    assert outcome.grader_results[0].reason_code is (
        EvalGraderReasonCode.ASSERTION_FAILED
    )


def test_registry_membership_is_exactly_the_13_artifact_names() -> None:
    registry = grader_registry()
    assert tuple(registry) == GRADER_NAMES
    assert len(registry) == 13
    assert all(registry[name].name == name for name in GRADER_NAMES)


def test_boolean_self_attestation_cannot_replace_typed_evidence() -> None:
    outcome = grade_evidence(
        GRADER_NAMES,
        _minimal_self_attested_evidence(),
        _expectations(),
    )

    assert outcome.status is EvalResultStatus.FAIL
    assert any(
        result.reason_code is EvalGraderReasonCode.MISSING_RECORD
        for result in outcome.grader_results
    )
    assert CriticalFailureCode.CF_14 in outcome.critical_failures


@pytest.mark.parametrize("grader_name", GRADER_NAMES)
def test_every_registered_grader_passes_valid_typed_evidence(
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _evidence(),
        _expectations(),
    )
    assert result == EvalGraderResult(
        grader_name=grader_name,
        status=EvalGraderStatus.PASS,
    )


@pytest.mark.parametrize("grader_name", GRADER_NAMES)
def test_each_grader_rejects_directed_typed_evidence_tamper(
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _tampered(grader_name),
        _expectations(),
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code in {
        EvalGraderReasonCode.MISSING_RECORD,
        EvalGraderReasonCode.ASSERTION_FAILED,
        EvalGraderReasonCode.TRACE_EVENT_MISSING,
    }


@pytest.mark.parametrize(
    "field_name",
    (
        "request_understanding_records",
        "accepted_task_deltas",
        "conversation_task_links",
        "run_task_links",
        "tool_attempts",
        "observation_persistence_envelopes",
    ),
)
def test_persistence_grader_requires_complete_authoritative_record_graph(
    field_name: str,
) -> None:
    result = grader_registry()["PersistenceGrader"].grade(
        _evidence(**{field_name: ()}),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


def test_persistence_and_trace_resolve_accepted_delta_refs_authoritatively() -> None:
    evidence = _evidence()
    foreign_ref = UUID(int=930)
    understanding = evidence.request_understanding_records[0].model_copy(
        update={"accepted_delta_refs": (foreign_ref,)}
    )
    events = tuple(
        event.model_copy(update={"accepted_delta_ref": foreign_ref})
        if event.event_type is TraceEventType.TASK_DELTA_ACCEPTED
        else event
        for event in evidence.trace_events
    )
    tampered = _evidence(
        request_understanding_records=(understanding,),
        trace_events=events,
    )

    for grader_name in ("PersistenceGrader", "TraceCompletenessGrader"):
        result = grader_registry()[grader_name].grade(
            tampered,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.FAIL
        assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_persistence_rejects_foreign_request_unit_observation_ref() -> None:
    evidence = _evidence()
    request_unit = evidence.request_units[0].model_copy(
        update={"observation_refs": (UUID(int=931),)}
    )

    result = grader_registry()["PersistenceGrader"].grade(
        _evidence(request_units=(request_unit,)),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def _assert_observation_provenance_fails(evidence: EvalEvidence) -> None:
    for grader_name in (
        "ObservationGrader",
        "PersistenceGrader",
        "TraceCompletenessGrader",
    ):
        result = grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.FAIL
        assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED

    canonical = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical.status is EvalResultStatus.FAIL


def test_observation_provenance_uses_canonical_refs_not_tool_result_ref() -> None:
    evidence = _evidence()

    assert evidence.tool_calls[0].result_ref == TOOL_RESULT_REF
    assert evidence.tool_calls[0].result_ref != evidence.observations[0].observation_id
    for grader_name in (
        "ObservationGrader",
        "PersistenceGrader",
        "TraceCompletenessGrader",
    ):
        result = grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.PASS

    canonical = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical.status is EvalResultStatus.PASS


def test_payload_correlation_ref_does_not_imply_an_observation_record() -> None:
    evidence = _evidence(
        observations=(),
        observation_persistence_envelopes=(),
    )

    assert evidence.tool_calls[0].result_ref == TOOL_RESULT_REF
    result = grader_registry()["ObservationGrader"].grade(
        evidence,
        _expectations(expected_observations=0),
    )
    assert result.status is EvalGraderStatus.PASS


def _observation_field_values(
    observation: OrderObservation,
) -> dict[str, object]:
    return {
        field_name: getattr(observation, field_name)
        for field_name in OrderObservation.model_fields
    }


def test_raw_string_audit_only_observation_fails_every_canonical_grader() -> None:
    canonical = _observation(visibility=ObservationVisibility.AUDIT_ONLY)
    raw_values = _observation_field_values(canonical)
    raw_values["visibility"] = "AUDIT_ONLY"
    raw_observation = OrderObservation.model_construct(**raw_values)
    evidence = _evidence(
        observations=(raw_observation,),
        observation_persistence_envelopes=(_observation_envelope(canonical),),
    )

    results = tuple(
        grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        for grader_name in GRADER_NAMES
    )
    assert all(result.status is EvalGraderStatus.FAIL for result in results)
    assert all(
        result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED
        for result in results
    )

    canonical_outcome = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical_outcome.status is EvalResultStatus.FAIL


def test_nested_raw_enum_observation_projection_fails_closed() -> None:
    canonical = _observation()
    raw_projection = canonical.normalized_value.model_copy(update={"status": "SHIPPED"})
    raw_observation = canonical.model_copy(update={"normalized_value": raw_projection})
    evidence = _evidence(
        observations=(raw_observation,),
        observation_persistence_envelopes=(_observation_envelope(canonical),),
    )

    results = tuple(
        grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        for grader_name in GRADER_NAMES
    )
    assert all(result.status is EvalGraderStatus.FAIL for result in results)
    assert all(
        result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED
        for result in results
    )


def test_leaky_datetime_subclass_fails_closed_before_renderer_use(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canonical = _observation()
    leaky_projection = canonical.normalized_value.model_copy(
        update={
            "ordered_at": LeakyDatetime(
                2026,
                7,
                20,
                2,
                15,
                tzinfo=UTC,
            )
        }
    )
    leaky_observation = canonical.model_copy(
        update={"normalized_value": leaky_projection}
    )
    untrusted_message = _rendered_message(leaky_observation)
    evidence = _evidence(
        observations=(leaky_observation,),
        observation_persistence_envelopes=(_observation_envelope(leaky_observation),),
        agent_result=AgentRunResult(
            run_id=RUN_ID,
            outcome=AgentOutcome.COMPLETED,
            message=untrusted_message,
        ),
    )
    assert LEAKY_DATETIME_SECRET in untrusted_message
    LeakyDatetime.strftime_calls = 0

    results = tuple(
        grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        for grader_name in GRADER_NAMES
    )
    assert tuple(result.grader_name for result in results) == GRADER_NAMES
    assert all(result.status is EvalGraderStatus.FAIL for result in results)
    assert all(
        result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED
        for result in results
    )

    canonical_outcome = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical_outcome.status is EvalResultStatus.FAIL
    assert LEAKY_DATETIME_SECRET not in canonical_outcome.model_dump_json()
    assert LEAKY_DATETIME_SECRET not in caplog.text
    assert LeakyDatetime.strftime_calls == 0


def test_uuid_subclass_observation_storage_fails_every_canonical_grader() -> None:
    canonical = _observation()
    derived_observation = canonical.model_copy(
        update={
            "observation_id": DerivedUUID(
                hex=canonical.observation_id.hex,
            )
        }
    )
    evidence = _evidence(
        observations=(derived_observation,),
        observation_persistence_envelopes=(_observation_envelope(canonical),),
    )

    results = tuple(
        grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        for grader_name in GRADER_NAMES
    )
    assert all(result.status is EvalGraderStatus.FAIL for result in results)
    assert all(
        result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED
        for result in results
    )

    canonical_outcome = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical_outcome.status is EvalResultStatus.FAIL


@pytest.mark.parametrize(
    "storage_attribute",
    ("field", "__pydantic_extra__", "__pydantic_private__"),
)
def test_hidden_observation_storage_fails_closed(
    storage_attribute: str,
) -> None:
    canonical = _observation()
    hidden = canonical.model_copy()
    if storage_attribute == "field":
        object.__setattr__(hidden, "hidden_secret", "must-not-be-serialized")
    else:
        object.__setattr__(
            hidden,
            storage_attribute,
            {"hidden_secret": "must-not-be-serialized"},
        )
    evidence = _evidence(
        observations=(hidden,),
        observation_persistence_envelopes=(_observation_envelope(canonical),),
    )

    results = tuple(
        grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        for grader_name in GRADER_NAMES
    )
    assert all(result.status is EvalGraderStatus.FAIL for result in results)
    assert all(
        result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED
        for result in results
    )


def test_valid_enum_audit_only_observation_cannot_be_rendered() -> None:
    observation = _observation(visibility=ObservationVisibility.AUDIT_ONLY)
    evidence = _evidence(
        observations=(observation,),
        observation_persistence_envelopes=(_observation_envelope(observation),),
    )

    for grader_name in ("ObservationGrader", "RendererFactGrader"):
        result = grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.FAIL
        assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED

    canonical = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical.status is EvalResultStatus.FAIL


@pytest.mark.parametrize(
    "relation",
    (
        "source_tool_call_id",
        "source_run_id",
        "source_task_id",
        "source_request_unit_id",
    ),
)
def test_observation_provenance_rejects_foreign_external_owner_ref(
    relation: str,
) -> None:
    evidence = _evidence()
    envelope = evidence.observation_persistence_envelopes[0]
    references = tuple(
        reference.model_copy(
            update={
                "target_logical_identity": (
                    (
                        reference.target_logical_identity[0][0],
                        str(UUID(int=940)),
                    ),
                )
            }
        )
        if reference.relation == relation
        else reference
        for reference in envelope.record_references
    )
    forged = envelope.model_copy(update={"record_references": references})

    _assert_observation_provenance_fails(
        _evidence(observation_persistence_envelopes=(forged,))
    )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("relation", "source_untrusted_id"),
        ("target_record_code", P0RecordCode.MESSAGE_RECORD),
        ("direct_owner_customer_id", "customer-A"),
    ),
)
def test_observation_provenance_rejects_envelope_contract_tamper(
    field_name: str,
    field_value: object,
) -> None:
    evidence = _evidence()
    envelope = evidence.observation_persistence_envelopes[0]
    if field_name == "direct_owner_customer_id":
        forged = envelope.model_copy(update={field_name: field_value})
    else:
        first_reference = envelope.record_references[0].model_copy(
            update={field_name: field_value}
        )
        forged = envelope.model_copy(
            update={
                "record_references": (
                    first_reference,
                    *envelope.record_references[1:],
                )
            }
        )

    _assert_observation_provenance_fails(
        _evidence(observation_persistence_envelopes=(forged,))
    )


@pytest.mark.parametrize(
    "reference_mutation",
    (
        lambda references: references[:-1],
        lambda references: (*references, references[-1]),
    ),
    ids=("missing-reference", "duplicate-reference"),
)
def test_observation_provenance_requires_exactly_four_external_refs(
    reference_mutation: Callable[
        [tuple[P0RecordReference, ...]],
        tuple[P0RecordReference, ...],
    ],
) -> None:
    evidence = _evidence()
    envelope = evidence.observation_persistence_envelopes[0]
    forged = envelope.model_copy(
        update={
            "record_references": reference_mutation(envelope.record_references),
        }
    )

    _assert_observation_provenance_fails(
        _evidence(observation_persistence_envelopes=(forged,))
    )


def test_canonical_supersedes_reference_is_additive_to_four_external_refs() -> None:
    observation = _observation(supersedes=UUID(int=942))
    envelope = _observation_envelope(observation)
    evidence = _evidence(
        observations=(observation,),
        observation_persistence_envelopes=(envelope,),
    )

    assert len(envelope.record_references) == 5
    assert (
        sum(
            reference.relation == "supersedes"
            for reference in envelope.record_references
        )
        == 1
    )
    for grader_name in GRADER_NAMES:
        result = grader_registry()[grader_name].grade(
            evidence,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.PASS

    canonical = grade_evidence(
        GRADER_NAMES,
        evidence,
        _expectations(),
    )
    assert canonical.status is EvalResultStatus.PASS


@pytest.mark.parametrize(
    "mutation",
    ("missing", "foreign", "tampered"),
)
def test_supersedes_reference_must_match_canonical_source_projection(
    mutation: str,
) -> None:
    observation = _observation(supersedes=UUID(int=942))
    envelope = _observation_envelope(observation)
    supersedes = next(
        reference
        for reference in envelope.record_references
        if reference.relation == "supersedes"
    )
    if mutation == "missing":
        references = tuple(
            reference
            for reference in envelope.record_references
            if reference.relation != "supersedes"
        )
    elif mutation == "foreign":
        references = tuple(
            reference.model_copy(
                update={
                    "target_logical_identity": (("observation_id", str(UUID(int=943))),)
                }
            )
            if reference is supersedes
            else reference
            for reference in envelope.record_references
        )
    else:
        references = tuple(
            reference.model_copy(
                update={"target_record_code": P0RecordCode.MESSAGE_RECORD}
            )
            if reference is supersedes
            else reference
            for reference in envelope.record_references
        )
    forged = envelope.model_copy(update={"record_references": references})

    _assert_observation_provenance_fails(
        _evidence(
            observations=(observation,),
            observation_persistence_envelopes=(forged,),
        )
    )


def test_coordinated_observation_id_swap_cannot_replace_persistence_owner() -> None:
    evidence = _evidence()
    foreign_observation_id = UUID(int=941)
    observation = evidence.observations[0].model_copy(
        update={"observation_id": foreign_observation_id}
    )
    request_unit = evidence.request_units[0].model_copy(
        update={"observation_refs": (foreign_observation_id,)}
    )
    tool_call = evidence.tool_calls[0].model_copy(
        update={"result_ref": foreign_observation_id}
    )
    manifests = tuple(
        manifest.model_copy(
            update={
                "observation_refs_and_versions": (
                    VersionedRecordRef(
                        record_ref=foreign_observation_id,
                        version=observation.source_version,
                    ),
                )
            }
        )
        if manifest.observation_refs_and_versions
        else manifest
        for manifest in evidence.context_manifests
    )
    trace_events = tuple(
        event.model_copy(update={"observation_ref": foreign_observation_id})
        if event.event_type is TraceEventType.OBSERVATION_RECORDED
        else event
        for event in evidence.trace_events
    )

    _assert_observation_provenance_fails(
        _evidence(
            observations=(observation,),
            request_units=(request_unit,),
            tool_calls=(tool_call,),
            context_manifests=manifests,
            trace_events=trace_events,
        )
    )


@pytest.mark.parametrize(
    "grader_name",
    ("ToolCallGrader", "PersistenceGrader"),
)
def test_tool_attempt_graph_must_match_authoritative_attempt_count(
    grader_name: str,
) -> None:
    evidence = _evidence()
    tool_call = evidence.tool_calls[0].model_copy(update={"attempt_count": 2})

    result = grader_registry()[grader_name].grade(
        _evidence(tool_calls=(tool_call,)),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


@pytest.mark.parametrize(
    ("first_outcome", "first_finished_at", "second_started_at"),
    (
        (
            ToolResultOutcome.SYSTEM_FAILURE,
            NOW + timedelta(milliseconds=100),
            NOW + timedelta(milliseconds=200),
        ),
        (
            ToolResultOutcome.SUCCESS,
            NOW + timedelta(milliseconds=100),
            NOW + timedelta(milliseconds=200),
        ),
        (
            ToolResultOutcome.BUSINESS_FAILURE,
            NOW + timedelta(milliseconds=100),
            NOW + timedelta(milliseconds=200),
        ),
        (
            ToolResultOutcome.SYSTEM_FAILURE,
            NOW + timedelta(milliseconds=300),
            NOW + timedelta(milliseconds=200),
        ),
    ),
    ids=(
        "system-failure-then-success",
        "success-then-success",
        "business-failure-then-success",
        "overlapping-attempt-windows",
    ),
)
def test_e2e01_thin_slice_rejects_fully_closed_retry_graphs(
    first_outcome: ToolResultOutcome,
    first_finished_at: datetime,
    second_started_at: datetime,
) -> None:
    evidence = _evidence()
    tool_call = evidence.tool_calls[0].model_copy(update={"attempt_count": 2})
    attempts = (
        ToolAttemptRecord(
            tool_call_id=TOOL_CALL_ID,
            attempt_no=1,
            started_at=NOW,
            finished_at=first_finished_at,
            outcome=first_outcome,
            failure_code=(
                None
                if first_outcome is ToolResultOutcome.SUCCESS
                else "ORDER_LOOKUP_FAILED"
            ),
        ),
        ToolAttemptRecord(
            tool_call_id=TOOL_CALL_ID,
            attempt_no=2,
            started_at=second_started_at,
            finished_at=tool_call.finished_at,
            outcome=ToolResultOutcome.SUCCESS,
        ),
    )
    tampered = _evidence(
        tool_calls=(tool_call,),
        tool_attempts=attempts,
    )

    for grader_name in (
        "ToolCallGrader",
        "PersistenceGrader",
        "TraceCompletenessGrader",
    ):
        result = grader_registry()[grader_name].grade(
            tampered,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.FAIL
        assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED

    canonical = grade_evidence(
        GRADER_NAMES,
        tampered,
        _expectations(),
    )
    assert canonical.status is EvalResultStatus.FAIL


def test_nonempty_alternative_conversation_task_link_reason_is_legal() -> None:
    evidence = _evidence()
    link = evidence.conversation_task_links[0].model_copy(
        update={"link_reason": "RESTORED_TASK_CONTEXT"}
    )
    alternative = _evidence(conversation_task_links=(link,))

    for grader_name in (
        "RequestUnderstandingGrader",
        "PersistenceGrader",
        "TraceCompletenessGrader",
    ):
        result = grader_registry()[grader_name].grade(
            alternative,
            _expectations(),
        )
        assert result.status is EvalGraderStatus.PASS

    canonical = grade_evidence(
        GRADER_NAMES,
        alternative,
        _expectations(),
    )
    assert canonical.status is EvalResultStatus.PASS


@pytest.mark.parametrize(
    "grader_name",
    ("RequestUnderstandingGrader", "PersistenceGrader"),
)
def test_source_quote_must_resolve_against_authoritative_message_and_observation(
    grader_name: str,
) -> None:
    result = grader_registry()[grader_name].grade(
        _evidence(
            request_understanding_output=_request_understanding(source_quote="O-2001")
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    "gate_update",
    [
        {"argument_binding_refs": (UUID(int=901),)},
        {"validated_task_state_version": 999},
        {"context_manifest_id": UUID(int=902)},
    ],
)
def test_tool_call_grader_closes_gate_and_tool_call_graph(
    gate_update: dict[str, object],
) -> None:
    evidence = _evidence()
    gate = evidence.gate_decisions[0].model_copy(update=gate_update)

    result = grader_registry()["ToolCallGrader"].grade(
        _evidence(gate_decisions=(gate,)),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    "grader_name",
    ("ToolCallGrader", "PersistenceGrader"),
)
def test_first_new_goal_manifest_cannot_claim_task_state(
    grader_name: str,
) -> None:
    evidence = _evidence()
    first_manifest = evidence.context_manifests[0].model_copy(
        update={
            "task_state_ref_and_version": TaskStateRefAndVersion(
                task_id=TASK_ID,
                state_version=1,
            )
        }
    )

    result = grader_registry()[grader_name].grade(
        _evidence(
            context_manifests=(
                first_manifest,
                evidence.context_manifests[1],
            )
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    "manifest_update",
    [
        {
            "task_state_ref_and_version": TaskStateRefAndVersion(
                task_id=UUID(int=920),
                state_version=1,
            )
        },
        {
            "task_state_ref_and_version": TaskStateRefAndVersion(
                task_id=TASK_ID,
                state_version=999,
            )
        },
        {
            "observation_refs_and_versions": (
                VersionedRecordRef(
                    record_ref=UUID(int=921),
                    version="order-v7",
                ),
            )
        },
        {
            "observation_refs_and_versions": (
                VersionedRecordRef(
                    record_ref=OBSERVATION_ID,
                    version="order-v999",
                ),
            )
        },
    ],
)
def test_persistence_grader_closes_presentation_manifest_internal_refs(
    manifest_update: dict[str, object],
) -> None:
    evidence = _evidence()
    presentation_manifest = evidence.context_manifests[1].model_copy(
        update=manifest_update
    )

    result = grader_registry()["PersistenceGrader"].grade(
        _evidence(
            context_manifests=(
                evidence.context_manifests[0],
                presentation_manifest,
            )
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    "manifest_update",
    [
        {"task_state_ref_and_version": None},
        {"observation_refs_and_versions": ()},
    ],
)
def test_persistence_grader_classifies_missing_presentation_refs(
    manifest_update: dict[str, object],
) -> None:
    evidence = _evidence()
    presentation_manifest = evidence.context_manifests[1].model_copy(
        update=manifest_update
    )

    result = grader_registry()["PersistenceGrader"].grade(
        _evidence(
            context_manifests=(
                evidence.context_manifests[0],
                presentation_manifest,
            )
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


@pytest.mark.parametrize(
    ("purpose", "expected_reason"),
    [
        (None, EvalGraderReasonCode.MISSING_RECORD),
        ("REQUEST_UNDERSTANDING", EvalGraderReasonCode.ASSERTION_FAILED),
    ],
)
def test_manifest_purpose_is_required_and_authenticated_by_expected_counts(
    purpose: str | None,
    expected_reason: EvalGraderReasonCode,
) -> None:
    trace_events = tuple(
        event.model_copy(update={"model_call_purpose": purpose})
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
        and event.context_manifest_id == CONTEXT_2
        else event
        for event in _trace_events()
    )

    result = grader_registry()["PersistenceGrader"].grade(
        _evidence(trace_events=trace_events),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is expected_reason


def test_manifest_purpose_is_bound_by_gate_graph_not_tuple_order() -> None:
    evidence = _evidence()
    reordered = grader_registry()["PersistenceGrader"].grade(
        _evidence(context_manifests=tuple(reversed(evidence.context_manifests))),
        _expectations(),
    )
    assert reordered.status is EvalGraderStatus.PASS

    swapped_purposes = tuple(
        event.model_copy(
            update={
                "model_call_purpose": (
                    "PRESENTATION"
                    if event.context_manifest_id == CONTEXT_1
                    else "REQUEST_UNDERSTANDING"
                )
            }
        )
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
        else event
        for event in evidence.trace_events
    )
    swapped = grader_registry()["PersistenceGrader"].grade(
        _evidence(trace_events=swapped_purposes),
        _expectations(),
    )

    assert swapped.status is EvalGraderStatus.FAIL
    assert swapped.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    ("manifests", "expected_reason"),
    [
        (
            lambda evidence: (evidence.context_manifests[0],),
            EvalGraderReasonCode.MISSING_RECORD,
        ),
        (
            lambda evidence: (
                *evidence.context_manifests,
                evidence.context_manifests[1].model_copy(
                    update={
                        "context_manifest_id": UUID(int=922),
                        "model_call_id": UUID(int=923),
                    }
                ),
            ),
            EvalGraderReasonCode.ASSERTION_FAILED,
        ),
    ],
)
def test_persistence_grader_distinguishes_missing_and_extra_manifests(
    manifests: Callable[[EvalEvidence], tuple[ContextManifest, ...]],
    expected_reason: EvalGraderReasonCode,
) -> None:
    evidence = _evidence()

    result = grader_registry()["PersistenceGrader"].grade(
        _evidence(context_manifests=manifests(evidence)),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is expected_reason


@pytest.mark.parametrize(
    "grader_name",
    ("PersistenceGrader", "TraceCompletenessGrader"),
)
def test_message_refs_resolve_only_from_authoritative_message_record(
    grader_name: str,
) -> None:
    evidence = _evidence()
    foreign_message_ref = UUID(int=924)
    assert evidence.request_understanding_output is not None
    output = evidence.request_understanding_output
    delta = output.task_delta_candidates[0]
    input_candidate = delta.input_candidates[0].model_copy(
        update={"source_ref": foreign_message_ref}
    )
    foreign_output = output.model_copy(
        update={
            "message_ref": foreign_message_ref,
            "task_delta_candidates": (
                delta.model_copy(update={"input_candidates": (input_candidate,)}),
            ),
        }
    )
    binding = evidence.input_bindings[0].model_copy(
        update={"source_refs": (foreign_message_ref,)}
    )
    request_unit = evidence.request_units[0].model_copy(
        update={"goal_source_refs": (foreign_message_ref,)}
    )
    manifests = tuple(
        manifest.model_copy(update={"selected_message_refs": (foreign_message_ref,)})
        for manifest in evidence.context_manifests
    )
    trace_events = tuple(
        event.model_copy(update={"message_ref": foreign_message_ref})
        if event.event_type is TraceEventType.MESSAGE_ACCEPTED
        else event
        for event in evidence.trace_events
    )

    result = grader_registry()[grader_name].grade(
        _evidence(
            request_understanding_output=foreign_output,
            input_bindings=(binding,),
            request_units=(request_unit,),
            context_manifests=manifests,
            trace_events=trace_events,
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_toolset_replay_rejects_consistent_untrusted_hash() -> None:
    evidence = _evidence()
    untrusted_hash = f"sha256:{'b' * 64}"
    manifests = tuple(
        manifest.model_copy(update={"model_visible_toolset_hash": untrusted_hash})
        for manifest in evidence.context_manifests
    )
    trace_events = tuple(
        event.model_copy(update={"model_visible_toolset_hash": untrusted_hash})
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
        else event
        for event in evidence.trace_events
    )

    result = grader_registry()["ToolsetReplayGrader"].grade(
        _evidence(
            context_manifests=manifests,
            trace_events=trace_events,
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_toolset_replay_requires_resolved_typed_artifact() -> None:
    result = grader_registry()["ToolsetReplayGrader"].grade(
        _evidence(model_visible_toolset_artifacts=()),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


def test_renderer_fact_grader_rejects_any_extra_unapproved_fact() -> None:
    evidence = _evidence()
    assert evidence.agent_result is not None
    result = grader_registry()["RendererFactGrader"].grade(
        _evidence(
            agent_result=evidence.agent_result.model_copy(
                update={
                    "message": (
                        f"{evidence.agent_result.message}\n"
                        "另一个订单 O-2001，商品：未授权商品，"
                        "地址：他人私有地址"
                    )
                }
            )
        ),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_trace_grader_rejects_tampered_task_state_top_level_refs() -> None:
    tampered_task_event = TraceEvent(
        trace_event_id=UUID(int=903),
        event_type=TraceEventType.TASK_STATE_CHANGED,
        occurred_at=NOW + timedelta(microseconds=9500),
        run_id=RUN_ID,
        case_id="E2E01-01",
        task_id=UUID(int=904),
        request_unit_id=UUID(int=905),
    )
    events = tuple(
        sorted(
            (*_trace_events(), tampered_task_event),
            key=lambda event: event.occurred_at,
        )
    )

    result = grader_registry()["TraceCompletenessGrader"].grade(
        _evidence(trace_events=events),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


@pytest.mark.parametrize(
    ("grader_name", "field_name"),
    [
        ("InputBindingGrader", "input_bindings"),
        ("TaskStateGrader", "task_records"),
        ("TaskStateGrader", "request_units"),
        ("ToolCallGrader", "gate_decisions"),
    ],
)
def test_extra_typed_record_is_mismatch_not_missing(
    grader_name: str,
    field_name: str,
) -> None:
    evidence = _evidence()
    records = getattr(evidence, field_name)
    identity_field = {
        "input_bindings": "binding_id",
        "task_records": "task_id",
        "request_units": "request_unit_id",
        "gate_decisions": "gate_decision_id",
    }[field_name]
    extra = records[0].model_copy(
        update={identity_field: UUID(int=910 + len(field_name))}
    )

    result = grader_registry()[grader_name].grade(
        _evidence(**{field_name: (*records, extra)}),
        _expectations(),
    )

    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_missing_applicable_observation_uses_stable_missing_record_reason() -> None:
    result = grader_registry()["ObservationGrader"].grade(
        _evidence(observations=()),
        _expectations(),
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.MISSING_RECORD


def test_trace_expectations_are_external_to_sut_evidence() -> None:
    evidence = _evidence(
        trace_events=tuple(
            event
            for event in _trace_events()
            if event.event_type is not TraceEventType.OBSERVATION_RECORDED
        )
    )
    result = grader_registry()["TraceCompletenessGrader"].grade(
        evidence,
        _expectations(),
    )
    assert result.status is EvalGraderStatus.FAIL
    assert result.reason_code is EvalGraderReasonCode.TRACE_EVENT_MISSING
    assert {
        "required_trace_events",
        "forbidden_trace_events",
        "expected_event_counts",
        "critical_failures",
    }.isdisjoint(EvalEvidence.model_fields)


@pytest.mark.parametrize(
    "configured",
    [
        (),
        ("SchemaGrader", "SchemaGrader"),
        ("UnknownGrader",),
        ("",),
    ],
)
def test_unknown_duplicate_or_missing_grader_configuration_fails_closed(
    configured: tuple[str, ...],
) -> None:
    with pytest.raises(GradingConfigurationError):
        grade_evidence(configured, _evidence(), _expectations())


def test_critical_failures_are_derived_from_typed_grader_failures() -> None:
    expectations = _expectations(
        applicable_critical_failures=(CriticalFailureCode.CF_14,)
    )
    outcome = grade_evidence(
        ("InputBindingGrader",),
        _tampered("InputBindingGrader"),
        expectations,
    )
    assert outcome.status is EvalResultStatus.FAIL
    assert outcome.critical_failures == (CriticalFailureCode.CF_14,)

    passing = (
        EvalGraderResult(
            grader_name="SchemaGrader",
            status=EvalGraderStatus.PASS,
        ),
    )
    assert (
        determine_result_status(passing, (CriticalFailureCode.CF_14,))
        is EvalResultStatus.FAIL
    )


def _safe_observable(
    case_id: str,
    **overrides: object,
) -> SafeCaseObservable:
    trace_events = (
        _trace(TraceEventType.RUN_STARTED, offset=1, case_id=case_id),
        TraceEvent(
            trace_event_id=UUID(int=702),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=NOW + timedelta(milliseconds=2),
            run_id=RUN_ID,
            case_id=case_id,
            user_outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
            stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
        ),
    )
    values: dict[str, object] = {
        "case_id": case_id,
        "http_status": 200,
        "user_outcome": AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        "response_policy": "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
        "ordinary_trace_shape": ordinary_trace_shape(trace_events),
        "model_calls": 1,
    }
    values.update(overrides)
    return SafeCaseObservable(**values)


def test_e2e01_04_requires_complete_equal_pair() -> None:
    foreign = _safe_observable("E2E01-04-A")
    nonexistent = _safe_observable("E2E01-04-B")
    assert e2e01_04_safe_observables_match(
        {"E2E01-04-A": foreign, "E2E01-04-B": nonexistent}
    )
    assert not e2e01_04_safe_observables_match({"E2E01-04-A": foreign})


@pytest.mark.parametrize(
    ("field", "different"),
    [
        ("http_status", 404),
        ("user_outcome", AgentOutcome.BLOCKED),
        ("response_policy", "DIFFERENT"),
        ("model_calls", 2),
        ("ordinary_trace_shape", "DIFFERENT_TRACE_SHAPE"),
    ],
)
def test_e2e01_04_rejects_difference_in_each_safe_observable(
    field: str,
    different: object,
) -> None:
    if different == "DIFFERENT_TRACE_SHAPE":
        different = ordinary_trace_shape(
            (_trace(TraceEventType.RUN_STARTED, offset=1),)
        )
    assert not e2e01_04_safe_observables_match(
        {
            "E2E01-04-A": _safe_observable("E2E01-04-A"),
            "E2E01-04-B": _safe_observable(
                "E2E01-04-B",
                **{field: different},
            ),
        }
    )


def test_ordinary_trace_shape_exposes_only_allowlisted_safe_fields() -> None:
    shape = ordinary_trace_shape(_evidence().trace_events)
    assert shape
    assert set(shape[0].model_dump(mode="json")) == {
        "event_type",
        "count",
        "status",
        "reason",
    }
    serialized = repr(tuple(item.model_dump(mode="json") for item in shape))
    for forbidden in (
        str(RUN_ID),
        str(TRACE_REF),
        "customer-A",
        "O-1001",
        "raw_payload",
    ):
        assert forbidden not in serialized


def test_evidence_aggregate_references_existing_records_without_copying_business_dto() -> (
    None
):
    evidence = _evidence()
    assert type(evidence.run_record) is AgentRunRecord
    assert type(evidence.agent_result) is AgentRunResult
    assert {
        "customer_id",
        "order_number",
        "raw_payload",
        "rendered_text",
    }.isdisjoint(EvalEvidence.model_fields)
