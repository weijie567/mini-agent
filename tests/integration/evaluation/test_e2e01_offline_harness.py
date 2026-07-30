from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from enum import Enum, StrEnum
from inspect import signature
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, SafeUUID, UUID, uuid5

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from mini_agent.application.ports import EvalResultPort, ModelProviderV2
from mini_agent.application.records import (
    AgentRunResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CriticalFailureCode,
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultRecord,
    EvalResultStatus,
    ExactRunEvidenceClosure,
    InsertOnlyWriteResult,
    MessageDirection,
    MessageRecord,
    ProviderProtocolError,
    RunTaskLinkRecord,
)
from mini_agent.core.common import (
    FrozenJsonDict,
    FrozenJsonList,
    freeze_json_value,
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
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationInput,
    PresentationPlan,
    PresentationPurpose,
    PresentationTone,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    ResolvedReferenceCandidateV2,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    DurableInputCandidateV2,
    DurableQueryContextualizationCandidateV2,
    DurableResolvedReferenceCandidateV2,
    DurableTaskDeltaCandidateV2,
    InputBinding,
    InputValidationStatus,
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
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    ToolSpec,
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
from mini_agent.evaluation.artifacts import (
    EvalCaseArtifact,
    LoadedE2E01Artifacts,
    load_e2e01_artifacts,
)
from mini_agent.evaluation.graders import (
    EvalCaseExpectations,
    EvalEvidence,
    GradingOutcome,
    SafeCaseObservable,
    derive_grading_outcome,
    grade_evidence,
    ordinary_trace_shape,
)
import mini_agent.evaluation.harness as harness_module
from mini_agent.evaluation.harness import (
    EvalCaseExecutionInput,
    EvalCaseSutResult,
    EvalHarnessCommandError,
    OfflineEvalHarness,
    UnboundEvalEvidence,
    UnboundSafeCaseObservable,
    append_qwen_not_run_record,
    build_authenticated_case_expectations,
    build_qwen_baseline_preflight,
    _CANONICAL_RESULT_ENUM_TYPES,
    _DISCOVERED_SEMANTIC_SCHEMA_IDENTITY_FIELDS,
    _MAX_PAYLOAD_DEPTH,
    _MAX_PAYLOAD_EDGES,
    _is_semantic_identity_field,
    _PayloadTraversalState,
    _payload_tree_is_closed,
    _SAFE_IDENTITY_FIELD_TOKEN_TUPLES,
    _same_exact_value_tree,
    _SEMANTIC_SCHEMA_IDENTITY_FIELDS,
)
from mini_agent.evaluation.scripted_provider import (
    RuntimeFaultDirective,
    ScriptedModelProviderV2,
)
from mini_agent.infrastructure.model.qwen_responses import (
    QwenResponsesAdapterV2,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = load_e2e01_artifacts(
    REPO_ROOT,
    candidate_version="candidate:c35687d",
)
EVAL_RUN_ID = UUID("00000000-0000-4000-8000-000000000801")
RUN_ID = UUID("00000000-0000-4000-8000-000000000802")
TRACE_REF = UUID("00000000-0000-4000-8000-000000000803")
NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
EXECUTION_REF_1 = UUID("11111111-1111-4111-8111-111111111111")
SCRIPT_EXECUTION_REF_1 = UUID("22222222-2222-4222-8222-222222222222")
EXECUTION_REF_2 = UUID("33333333-3333-4333-8333-333333333333")
SCRIPT_EXECUTION_REF_2 = UUID("44444444-4444-4444-8444-444444444444")
EXECUTION_REF_3 = UUID("55555555-5555-4555-8555-555555555555")
SCRIPT_EXECUTION_REF_3 = UUID("66666666-6666-4666-8666-666666666666")
EXECUTION_REF_4 = UUID("77777777-7777-4777-8777-777777777777")
SCRIPT_EXECUTION_REF_4 = UUID("88888888-8888-4888-8888-888888888888")
UNKNOWN_EXECUTION_REF = UUID("99999999-9999-4999-8999-999999999999")
MAPPER_FIXTURE_IDENTITIES = (
    (
        UUID("a1111111-1111-4111-8111-111111111111"),
        UUID("a2222222-2222-4222-8222-222222222222"),
        UUID("a3333333-3333-4333-8333-333333333333"),
    ),
    (
        UUID("b1111111-1111-4111-8111-111111111111"),
        UUID("b2222222-2222-4222-8222-222222222222"),
        UUID("b3333333-3333-4333-8333-333333333333"),
    ),
    (
        UUID("c1111111-1111-4111-8111-111111111111"),
        UUID("c2222222-2222-4222-8222-222222222222"),
        UUID("c3333333-3333-4333-8333-333333333333"),
    ),
    (
        UUID("d1111111-1111-4111-8111-111111111111"),
        UUID("d2222222-2222-4222-8222-222222222222"),
        UUID("d3333333-3333-4333-8333-333333333333"),
    ),
    (
        UUID("e1111111-1111-4111-8111-111111111111"),
        UUID("e2222222-2222-4222-8222-222222222222"),
        UUID("e3333333-3333-4333-8333-333333333333"),
    ),
    (
        UUID("f1111111-1111-4111-8111-111111111111"),
        UUID("f2222222-2222-4222-8222-222222222222"),
        UUID("f3333333-3333-4333-8333-333333333333"),
    ),
    (
        UUID("01111111-1111-4111-8111-111111111111"),
        UUID("02222222-2222-4222-8222-222222222222"),
        UUID("03333333-3333-4333-8333-333333333333"),
    ),
)
MINIMAL_INPUT_INVALID_IDENTITIES = (
    UUID("10101010-1010-4010-8010-101010101001"),
    UUID("10101010-1010-4010-8010-101010101002"),
    UUID("10101010-1010-4010-8010-101010101003"),
    UUID("10101010-1010-4010-8010-101010101004"),
    UUID("10101010-1010-4010-8010-101010101005"),
    UUID("10101010-1010-4010-8010-101010101006"),
    UUID("10101010-1010-4010-8010-101010101007"),
    UUID("10101010-1010-4010-8010-101010101008"),
)
EXPECTED_TRACE_VARIANT_BY_SCRIPT_REF = {
    "script:e2e01-01:success": "SUCCESS",
    "script:e2e01-04-a:foreign-order": "FOREIGN_ORDER",
    "script:e2e01-04-b:nonexistent-order": "NONEXISTENT_ORDER",
    "script:sec-argument-binding:foreign-order": "ARGUMENT_BINDING_REJECTED",
    "script:sec-argument-binding:nonexistent-order": "ARGUMENT_BINDING_REJECTED",
    "script:fault-provider:zero-target-functions": (
        "PROVIDER_PROTOCOL_BEFORE_CANDIDATE"
    ),
    "script:fault-provider:multiple-target-functions": (
        "PROVIDER_PROTOCOL_BEFORE_CANDIDATE"
    ),
    "script:fault-provider:invalid-request-understanding-schema": (
        "INPUT_VALIDATION_REJECTED"
    ),
    "script:fault-provider:source-authority-mismatch": (
        "INPUT_VALIDATION_REJECTED"
    ),
    "script:fault-provider:trusted-field-override": (
        "INPUT_VALIDATION_REJECTED"
    ),
    "script:fault-provider:unknown-tool-name": "UNKNOWN_TOOL_GATEWAY_REJECTED",
    "script:fault-runtime:state-advanced-before-gate": (
        "STALE_STATE_GATEWAY_REJECTED"
    ),
    "script:fault-presentation:zero-target-functions": (
        "PRESENTATION_PROTOCOL_REJECTED"
    ),
    "script:fault-presentation:multiple-target-functions": (
        "PRESENTATION_PROTOCOL_REJECTED"
    ),
    "script:fault-presentation:invalid-schema": (
        "PRESENTATION_PROTOCOL_REJECTED"
    ),
    "script:fault-presentation:fact-bearing-envelope": (
        "PRESENTATION_PROTOCOL_REJECTED"
    ),
}


class SmuggledCaseIdentity(StrEnum):
    VALUE = "E2E01-01"


class SmuggledScriptIdentity(Enum):
    VALUE = "script:e2e01-01:success"


class InnerSmuggledCaseIdentity(Enum):
    VALUE = "E2E01-01"


class OuterSmuggledCaseIdentity(Enum):
    VALUE = InnerSmuggledCaseIdentity.VALUE


class IdentityString(str):
    pass


class SubclassSmuggledCaseIdentity(Enum):
    VALUE = IdentityString("E2E01-01")


class WrappedSemanticIdentity(Enum):
    VALUE = {"case_code": "business-opaque-value"}


class WrappedBundleIdentity(Enum):
    VALUE = {"metadata": "E2E01-04-A"}


class SemanticCaseCodeKey(Enum):
    VALUE = "case_code"


class InnerSemanticScriptUuidKey(Enum):
    VALUE = "script_uuid"


class OuterSemanticScriptUuidKey(Enum):
    VALUE = InnerSemanticScriptUuidKey.VALUE


class SemanticKeyString(str):
    pass


class SubclassSemanticCaseNumberKey(Enum):
    VALUE = SemanticKeyString("case_number")


class OrdinaryBusinessKey(Enum):
    VALUE = "customer_case_id"


class OrdinaryLexicalKey(Enum):
    VALUE = "showcasecode"


class SubclassOrdinaryLexicalKey(Enum):
    VALUE = SemanticKeyString("scripture")


class FlipMapping(Mapping[str, object]):
    def __init__(self) -> None:
        self.iterations = 0

    def __getitem__(self, key: str) -> object:
        if key != "metadata":
            raise KeyError(key)
        return (
            "ordinary-value"
            if self.iterations <= 1
            else "E2E01-01"
        )

    def __iter__(self):
        self.iterations += 1
        return iter(("metadata",))

    def __len__(self) -> int:
        return 1


class FlipList(list[object]):
    def __init__(self) -> None:
        super().__init__(("ordinary-value",))
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations == 1:
            return list.__iter__(self)
        return iter(("E2E01-01",))


class FlipTuple(tuple[object, ...]):
    def __new__(cls):
        return tuple.__new__(cls, ("ordinary-value",))

    def __init__(self) -> None:
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations == 1:
            return tuple.__iter__(self)
        return iter(("E2E01-01",))


class FlipSet(set[object]):
    def __init__(self) -> None:
        super().__init__(("ordinary-value",))
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations == 1:
            return set.__iter__(self)
        return iter(("E2E01-01",))


@dataclass
class EnumValueReadCounter:
    reads: int = 0


FLIP_ENUM_VALUE_READ_COUNTER = EnumValueReadCounter()


class FlipValueEnum(Enum):
    VALUE = "ordinary-value"

    def __getattribute__(self, name: str) -> object:
        if name == "value":
            FLIP_ENUM_VALUE_READ_COUNTER.reads += 1
            if FLIP_ENUM_VALUE_READ_COUNTER.reads == 1:
                return "ordinary-value"
            return "E2E01-01"
        return super().__getattribute__(name)


@dataclass
class StringMethodReadCounter:
    reads: int = 0


FLIP_STRING_METHOD_READ_COUNTER = StringMethodReadCounter()


class FlipString(str):
    def __new__(cls, value: str):
        return str.__new__(cls, value)

    def __str__(self) -> str:
        FLIP_STRING_METHOD_READ_COUNTER.reads += 1
        return "E2E01-01"


@dataclass
class SidecarMethodReadCounter:
    reads: int = 0


SIDECAR_METHOD_READ_COUNTER = SidecarMethodReadCounter()


class SneakyFieldsSet(set[str]):
    def issubset(self, other: object) -> bool:
        SIDECAR_METHOD_READ_COUNTER.reads += 1
        return True

    def __le__(self, other: object) -> bool:
        SIDECAR_METHOD_READ_COUNTER.reads += 1
        return True

    def __iter__(self):
        SIDECAR_METHOD_READ_COUNTER.reads += 1
        return iter(("safe_observable",))


class SneakyStorageKey(str):
    def __hash__(self) -> int:
        SIDECAR_METHOD_READ_COUNTER.reads += 1
        return str.__hash__(self)

    def __eq__(self, other: object) -> bool:
        SIDECAR_METHOD_READ_COUNTER.reads += 1
        return str.__eq__(self, other)


@dataclass
class TimezoneMethodReadCounter:
    reads: int = 0


TIMEZONE_METHOD_READ_COUNTER = TimezoneMethodReadCounter()


class EvilTz(tzinfo):
    secret = "E2E01-01"

    def utcoffset(self, value: datetime | None) -> timedelta:
        TIMEZONE_METHOD_READ_COUNTER.reads += 1
        return timedelta(0)

    def dst(self, value: datetime | None) -> timedelta:
        TIMEZONE_METHOD_READ_COUNTER.reads += 1
        return timedelta(0)

    def tzname(self, value: datetime | None) -> str:
        TIMEZONE_METHOD_READ_COUNTER.reads += 1
        return "E2E01-01"


@dataclass
class BoundaryMethodReadCounter:
    reads: int = 0


BOUNDARY_METHOD_READ_COUNTER = BoundaryMethodReadCounter()


class EvilEquality:
    def __eq__(self, other: object) -> bool:
        BOUNDARY_METHOD_READ_COUNTER.reads += 1
        raise RuntimeError("raw-boundary-equality-secret")

    def __ne__(self, other: object) -> bool:
        BOUNDARY_METHOD_READ_COUNTER.reads += 1
        raise RuntimeError("raw-boundary-equality-secret")


class EvilInt(int):
    def __and__(self, other: object) -> int:
        BOUNDARY_METHOD_READ_COUNTER.reads += 1
        raise RuntimeError("raw-nonce-secret")

    def __rand__(self, other: object) -> int:
        BOUNDARY_METHOD_READ_COUNTER.reads += 1
        raise RuntimeError("raw-nonce-secret")


class ReloadFlipTuple(tuple[object, ...]):
    def __new__(
        cls,
        values: Sequence[object],
    ) -> ReloadFlipTuple:
        return tuple.__new__(cls, values)

    def __iter__(self):
        BOUNDARY_METHOD_READ_COUNTER.reads += 1
        raise RuntimeError("raw-trace-store-secret")


def _canonical_enum_storage_is_pristine(
    member: Enum,
    expected_items: tuple[tuple[str, object], ...],
) -> bool:
    storage = object.__getattribute__(member, "__dict__")
    if type(storage) is not dict:
        return False
    names = tuple(dict.__iter__(storage))
    if names != tuple(name for name, _ in expected_items):
        return False
    return all(
        (
            dict.__getitem__(storage, name) is expected
            or (
                type(dict.__getitem__(storage, name))
                is type(expected)
                and dict.__getitem__(storage, name) == expected
            )
        )
        for name, expected in expected_items
    )


class NonceFactorySpy:
    def __init__(self, values: Sequence[UUID]) -> None:
        self._values = tuple(values)
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> UUID:
        self.calls.append((args, dict(kwargs)))
        if args or kwargs:
            raise AssertionError("nonce factory received semantic arguments")
        index = len(self.calls) - 1
        if index >= len(self._values):
            raise AssertionError("nonce factory called more often than expected")
        return self._values[index]


def _tool_spec() -> ToolSpec:
    return get_order_tool_spec()


def _request(
    source: EvalCaseArtifact | EvalCaseExecutionInput,
) -> RequestUnderstandingInput:
    tool = _tool_spec()
    if type(source) is EvalCaseExecutionInput:
        run_id = _case_uuid(str(source.execution_ref), "request-run")
        message_ref = _case_uuid(str(source.execution_ref), "message")
        original_query = source.messages[0].content
    else:
        message = source.input["messages"][0]
        run_id = RUN_ID
        message_ref = UUID("00000000-0000-4000-8000-000000000804")
        original_query = message["content"]
    return RequestUnderstandingInput(
        run_id=run_id,
        message_ref=message_ref,
        original_query=original_query,
        provider_visible_tool_specs=(tool,),
        model_visible_toolset_hash=compute_model_visible_toolset_hash((tool,)),
    )


def _presentation_input() -> PresentationInput:
    return PresentationInput(
        purpose=PresentationPurpose.ORDER_STATUS_SUMMARY,
        order_summary=OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at="2026-07-20T02:15:00Z",
            status_updated_at="2026-07-24T09:30:00Z",
        ),
    )


class InMemoryResultPort:
    def __init__(self, timeline: list[str] | None = None) -> None:
        self.results: dict[
            tuple[UUID, str, str, int],
            EvalResultRecord,
        ] = {}
        self.failures: list[EvalExecutionFailureRecord] = []
        self.events: list[str] = []
        self.fail_result_append = False
        self.fail_failure_append = False
        self.fail_load = False
        self.timeline = timeline if timeline is not None else []

    async def append_eval_result(
        self,
        record: EvalResultRecord,
    ) -> InsertOnlyWriteResult:
        self.events.append("result_append")
        self.timeline.append("result_append")
        if self.fail_result_append:
            raise RuntimeError("raw-result-store-secret")
        key = (
            record.eval_run_id,
            record.case_id,
            record.lane,
            record.attempt,
        )
        if key in self.results:
            return InsertOnlyWriteResult.ALREADY_EXISTS
        self.results[key] = record
        return InsertOnlyWriteResult.INSERTED

    async def load_eval_result(
        self,
        *,
        eval_run_id: UUID,
        case_id: str,
        lane: str,
        attempt: int,
    ) -> EvalResultRecord | None:
        if self.fail_load:
            raise RuntimeError("raw-load-secret")
        return self.results.get((eval_run_id, case_id, lane, attempt))

    async def list_eval_results(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalResultRecord, ...]:
        return tuple(
            result for key, result in self.results.items() if key[0] == eval_run_id
        )

    async def append_eval_execution_failure(
        self,
        record: EvalExecutionFailureRecord,
    ) -> None:
        self.events.append("failure_append")
        self.timeline.append("failure_append")
        if self.fail_failure_append:
            raise RuntimeError("raw-failure-store-secret")
        self.failures.append(record)

    async def list_eval_execution_failures(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalExecutionFailureRecord, ...]:
        return tuple(
            failure for failure in self.failures if failure.eval_run_id == eval_run_id
        )


class InMemoryTraceCallbacks:
    def __init__(self, timeline: list[str] | None = None) -> None:
        self.events_by_ref: dict[UUID, list[TraceEvent]] = {}
        self.trace_ref_by_run: dict[UUID, UUID] = {}
        self.events: list[str] = []
        self.fail_append = False
        self.fail_reload = False
        self.drop_append = False
        self.timeline = timeline if timeline is not None else []

    def seed(self, trace_ref: UUID, events: Sequence[TraceEvent]) -> None:
        self.events_by_ref[trace_ref] = list(events)
        for event in events:
            self.trace_ref_by_run[event.run_id] = trace_ref

    async def append_eval_case_graded(self, event: TraceEvent) -> None:
        self.events.append("trace_append")
        self.timeline.append("trace_append")
        if self.fail_append:
            raise RuntimeError("raw-trace-secret")
        if self.drop_append:
            return
        trace_ref = self.trace_ref_by_run[event.run_id]
        existing = self.events_by_ref[trace_ref]
        same_identity = [
            item for item in existing if item.trace_event_id == event.trace_event_id
        ]
        if same_identity:
            if same_identity != [event]:
                raise RuntimeError("trace-replay-conflict")
            return
        existing.append(event)

    async def reload_trace(self, trace_ref: UUID) -> tuple[TraceEvent, ...]:
        self.events.append("trace_reload")
        self.timeline.append("trace_reload")
        if self.fail_reload:
            raise RuntimeError("raw-trace-store-secret")
        return tuple(self.events_by_ref[trace_ref])


def _case_uuid(case_id: str, label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"synthetic:{case_id}:{label}")


@dataclass(frozen=True, slots=True)
class _SyntheticActualProfile:
    customer_id: str
    http_status: int
    outcome: AgentOutcome
    run_status: AgentRunStatus
    stop_reason: StopReason
    response_policy: str
    binding_order_id: str
    requested_tool_name: str
    task_status: TaskStatus
    task_state_version: int
    gate_decision: GateDecisionValue
    gate_reason: GateReasonCode | None
    tool_call_status: ToolCallStatus | None
    observation_count: int
    model_calls: int
    presentation_model_calls: int
    trace_path: str


_COMMON_TRACE_PREFIX = (
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
)
_TRACE_SEQUENCE_BY_PATH = {
    "SUCCESS": (
        *_COMMON_TRACE_PREFIX,
        TraceEventType.GATE_DECISION_RECORDED,
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.TOOL_CALL_STARTED,
        TraceEventType.TOOL_CALL_SUCCEEDED,
        TraceEventType.TOOL_RESULT_NORMALIZED,
        TraceEventType.OBSERVATION_RECORDED,
        TraceEventType.CONTEXT_MANIFEST_RECORDED,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
        TraceEventType.RESPONSE_RENDERED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.RUN_STOPPED,
    ),
    "FAILED_TOOL": (
        *_COMMON_TRACE_PREFIX,
        TraceEventType.GATE_DECISION_RECORDED,
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.TOOL_CALL_STARTED,
        TraceEventType.TOOL_CALL_FAILED,
        TraceEventType.TOOL_RESULT_NORMALIZED,
        TraceEventType.RESPONSE_RENDERED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.RUN_STOPPED,
    ),
    "GATEWAY_REJECTED": (
        *_COMMON_TRACE_PREFIX,
        TraceEventType.GATE_DECISION_RECORDED,
        TraceEventType.RESPONSE_RENDERED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.RUN_STOPPED,
    ),
    "STALE_STATE": (
        *_COMMON_TRACE_PREFIX,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.GATE_DECISION_RECORDED,
        TraceEventType.RESPONSE_RENDERED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.RUN_STOPPED,
    ),
    "PRESENTATION_FAULT": (
        *_COMMON_TRACE_PREFIX,
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
    ),
}


def _actual_profile(
    request_output,
    *,
    runtime_fault: RuntimeFaultDirective | None,
    presentation_failed: bool,
) -> _SyntheticActualProfile:
    candidate = request_output.task_delta_candidates[0]
    message_order_id = str(candidate.input_candidates[0].candidate_value)
    next_move_order_id = str(
        request_output.next_move_candidate.arguments["order_id"]
    )
    requested_tool_name = request_output.next_move_candidate.requested_tool_name
    common: dict[str, object] = {
        "customer_id": "customer-A",
        "http_status": 200,
        "run_status": AgentRunStatus.COMPLETED,
        "binding_order_id": message_order_id,
        "requested_tool_name": requested_tool_name,
        "model_calls": 1,
        "presentation_model_calls": 0,
    }
    if runtime_fault is not None:
        return _SyntheticActualProfile(
            **common,
            outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.GATE_REJECTED,
            response_policy="FIXED_SAFE_PROCESSING_ERROR",
            task_status=TaskStatus.BLOCKED,
            task_state_version=3,
            gate_decision=GateDecisionValue.REJECT,
            gate_reason=GateReasonCode.STATE_VERSION_MISMATCH,
            tool_call_status=None,
            observation_count=0,
            trace_path="STALE_STATE",
        )
    if message_order_id != next_move_order_id:
        return _SyntheticActualProfile(
            **common,
            outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.GATE_REJECTED,
            response_policy="FIXED_SAFE_PROCESSING_ERROR",
            task_status=TaskStatus.BLOCKED,
            task_state_version=2,
            gate_decision=GateDecisionValue.REJECT,
            gate_reason=GateReasonCode.ARGUMENT_BINDING_MISMATCH,
            tool_call_status=None,
            observation_count=0,
            trace_path="GATEWAY_REJECTED",
        )
    if requested_tool_name != "get_order":
        return _SyntheticActualProfile(
            **common,
            outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.GATE_REJECTED,
            response_policy="FIXED_SAFE_PROCESSING_ERROR",
            task_status=TaskStatus.BLOCKED,
            task_state_version=2,
            gate_decision=GateDecisionValue.REJECT,
            gate_reason=GateReasonCode.TOOL_NOT_REGISTERED,
            tool_call_status=None,
            observation_count=0,
            trace_path="GATEWAY_REJECTED",
        )
    if next_move_order_id != "O-1001":
        return _SyntheticActualProfile(
            **common,
            outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
            stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
            response_policy="FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
            task_status=TaskStatus.COMPLETED,
            task_state_version=2,
            gate_decision=GateDecisionValue.ACCEPT,
            gate_reason=None,
            tool_call_status=ToolCallStatus.FAILED,
            observation_count=0,
            trace_path="FAILED_TOOL",
        )
    if presentation_failed:
        return _SyntheticActualProfile(
            **{**common, "model_calls": 2, "presentation_model_calls": 1},
            outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
            response_policy="FIXED_SAFE_PROCESSING_ERROR",
            task_status=TaskStatus.BLOCKED,
            task_state_version=2,
            gate_decision=GateDecisionValue.ACCEPT,
            gate_reason=None,
            tool_call_status=ToolCallStatus.SUCCEEDED,
            observation_count=1,
            trace_path="PRESENTATION_FAULT",
        )
    return _SyntheticActualProfile(
        **{**common, "model_calls": 2, "presentation_model_calls": 1},
        outcome=AgentOutcome.COMPLETED,
        stop_reason=StopReason.GOAL_COMPLETED,
        response_policy="DETERMINISTIC_ORDER_SUMMARY_V1",
        task_status=TaskStatus.COMPLETED,
        task_state_version=2,
        gate_decision=GateDecisionValue.ACCEPT,
        gate_reason=None,
        tool_call_status=ToolCallStatus.SUCCEEDED,
        observation_count=1,
        trace_path="SUCCESS",
    )


def _synthetic_trace(
    *,
    profile: _SyntheticActualProfile,
    identity_seed: str,
    run_id: UUID,
    message_ref: UUID,
    accepted_delta: AcceptedTaskDeltaV2,
    binding: InputBinding,
    task: TaskRecord,
    request_unit: RequestUnitRecord,
    gate: GateDecision,
    tool_call: ToolCallRecord | None,
    observation: OrderObservation | None,
    manifests: tuple[ContextManifest, ...],
) -> tuple[TraceEvent, ...]:
    events: list[TraceEvent] = []
    manifest_index = 0
    for sequence, event_type in enumerate(
        _TRACE_SEQUENCE_BY_PATH[profile.trace_path],
        start=1,
    ):
        values: dict[str, object] = {
            "trace_event_id": _case_uuid(identity_seed, f"trace:{sequence}"),
            "event_type": event_type,
            "occurred_at": NOW + timedelta(milliseconds=sequence),
            "run_id": run_id,
            "case_id": None,
        }
        if event_type is TraceEventType.MESSAGE_ACCEPTED:
            values["message_ref"] = message_ref
        elif event_type is TraceEventType.TASK_DELTA_ACCEPTED:
            values.update(
                {
                    "message_ref": message_ref,
                    "accepted_delta_ref": accepted_delta.accepted_delta_id,
                    "task_id": task.task_id,
                    "request_unit_id": request_unit.request_unit_id,
                }
            )
        elif event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED:
            manifest = manifests[manifest_index]
            purpose = (
                "REQUEST_UNDERSTANDING"
                if manifest_index == 0
                else "PRESENTATION"
            )
            manifest_index += 1
            values.update(
                {
                    "context_manifest_id": manifest.context_manifest_id,
                    "model_call_id": manifest.model_call_id,
                    "model_call_purpose": purpose,
                    "tool_registry_version": manifest.tool_registry_version,
                    "model_visible_toolset_hash": (
                        manifest.model_visible_toolset_hash
                    ),
                }
            )
        elif event_type is TraceEventType.INPUT_BINDING_RECORDED:
            values["input_binding_ref"] = binding.binding_id
        elif event_type is TraceEventType.TASK_STATE_CHANGED:
            values.update(
                {
                    "task_id": task.task_id,
                    "request_unit_id": request_unit.request_unit_id,
                }
            )
        elif event_type is TraceEventType.NEXT_MOVE_REVALIDATED:
            values["validated_task_state_version"] = 1
        elif event_type is TraceEventType.GATE_DECISION_RECORDED:
            values.update(
                {
                    "gate_decision": gate.decision,
                    "gate_reason_code": gate.reason_code,
                }
            )
        elif event_type in {
            TraceEventType.TOOL_CALL_CREATED,
            TraceEventType.TOOL_CALL_STARTED,
            TraceEventType.TOOL_CALL_SUCCEEDED,
            TraceEventType.TOOL_CALL_FAILED,
        }:
            assert tool_call is not None
            status_by_type = {
                TraceEventType.TOOL_CALL_CREATED: ToolCallStatus.CREATED,
                TraceEventType.TOOL_CALL_STARTED: ToolCallStatus.RUNNING,
                TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
                TraceEventType.TOOL_CALL_FAILED: ToolCallStatus.FAILED,
            }
            values.update(
                {
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_call_terminal_status": status_by_type[event_type],
                }
            )
        elif event_type is TraceEventType.TOOL_RESULT_NORMALIZED:
            assert tool_call is not None
            values.update(
                {
                    "tool_call_id": tool_call.tool_call_id,
                    "safe_tool_outcome": (
                        ToolResultOutcome.SUCCESS
                        if tool_call.status is ToolCallStatus.SUCCEEDED
                        else ToolResultOutcome.BUSINESS_FAILURE
                    ),
                }
            )
        elif event_type is TraceEventType.OBSERVATION_RECORDED:
            assert observation is not None
            values["observation_ref"] = observation.observation_id
        elif event_type is TraceEventType.RUN_STOPPED:
            values.update(
                {
                    "user_outcome": profile.outcome,
                    "stop_reason": profile.stop_reason,
                }
            )
        events.append(TraceEvent(**values))
    return tuple(events)


def _synthetic_message(
    profile: _SyntheticActualProfile,
    observation: OrderObservation | None,
) -> str:
    if profile.response_policy == "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE":
        return "未找到可访问的订单，请核对订单号后重试。"
    if profile.response_policy == "FIXED_SAFE_PROCESSING_ERROR":
        return "当前无法安全处理该请求，请稍后重试。"
    assert observation is not None
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


class SyntheticSut:
    def __init__(
        self,
        traces: InMemoryTraceCallbacks,
        *,
        fault: str | None = None,
        evidence_overrides: Mapping[str, object] | None = None,
        observable_overrides: Mapping[str, object] | None = None,
    ) -> None:
        self.traces = traces
        self.fault = fault
        self.evidence_overrides = dict(evidence_overrides or {})
        self.observable_overrides = dict(observable_overrides or {})
        self.calls = 0
        self.last_runtime_fault: RuntimeFaultDirective | None = None
        self.last_trace_ref: UUID | None = None

    async def execute_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        scripted_provider: ScriptedModelProviderV2,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None:
        self.calls += 1
        self.last_runtime_fault = runtime_fault
        if self.fault == "sut":
            raise RuntimeError("raw-sut-secret customer-A O-1001")
        if self.fault == "missing":
            return None
        assert isinstance(scripted_provider, ModelProviderV2)
        request = _request(execution_input)
        request_output = await scripted_provider.propose_next_move(request)
        proposed_delta = request_output.task_delta_candidates[0]
        message_order_id = str(
            proposed_delta.input_candidates[0].candidate_value
        )
        next_move_order_id = str(
            request_output.next_move_candidate.arguments["order_id"]
        )
        presentation_failed = False
        if (
            runtime_fault is None
            and message_order_id == next_move_order_id == "O-1001"
            and request_output.next_move_candidate.requested_tool_name
            == "get_order"
        ):
            try:
                await scripted_provider.plan_presentation(
                    _presentation_input()
                )
            except ProviderProtocolError:
                presentation_failed = True
        profile = _actual_profile(
            request_output,
            runtime_fault=runtime_fault,
            presentation_failed=presentation_failed,
        )
        identity_seed = str(execution_input.execution_ref)
        run_id = request.run_id
        trace_ref = _case_uuid(identity_seed, "trace")
        self.last_trace_ref = trace_ref
        message_ref = request_output.message_ref
        conversation_id = _case_uuid(identity_seed, "conversation")
        binding = InputBinding(
            binding_id=_case_uuid(identity_seed, "binding"),
            name="order_id",
            normalized_value=profile.binding_order_id,
            authority=InputAuthority.USER_CLAIM,
            source_refs=(message_ref,),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=NOW,
            updated_at=NOW,
        )
        task = TaskRecord(
            task_id=_case_uuid(identity_seed, "task"),
            owner_customer_id=profile.customer_id,
            status=profile.task_status,
            state_version=profile.task_state_version,
            created_at=NOW,
            updated_at=NOW + timedelta(seconds=1),
        )
        request_unit = RequestUnitRecord(
            request_unit_id=_case_uuid(identity_seed, "request-unit"),
            task_id=task.task_id,
            goal_text="查询指定订单状态",
            goal_source_refs=(message_ref,),
            input_binding_refs=(binding.binding_id,),
            observation_refs=(
                (_case_uuid(identity_seed, "observation"),)
                if profile.observation_count == 1
                else ()
            ),
            status=profile.task_status,
            state_version=profile.task_state_version,
            created_at=NOW,
            updated_at=NOW + timedelta(seconds=1),
        )
        accepted_delta = AcceptedTaskDeltaV2(
            accepted_delta_id=_case_uuid(identity_seed, "accepted-delta"),
            candidate_ref=proposed_delta.candidate_id,
            message_ref=message_ref,
            operation=proposed_delta.operation,
            goal_text=proposed_delta.goal_patch,
            input_binding_refs=(binding.binding_id,),
            accepted_at=NOW,
            task_id=task.task_id,
            base_task_state_version=None,
            result_task_state_version=1,
        )
        source_text = execution_input.messages[0].content
        source_start = source_text.index(message_order_id)
        source_end = source_start + len(message_order_id)
        source_hash = hashlib.sha256(
            source_text[source_start:source_end].encode("utf-8")
        ).hexdigest()
        durable_input = DurableInputCandidateV2(
            name="order_id",
            candidate_value=message_order_id,
            semantic_role="TARGET_RESOURCE_IDENTIFIER",
            authority=InputAuthority.USER_CLAIM,
            source_kind=InputSourceKind.CURRENT_MESSAGE,
            source_ref=message_ref,
            source_span_start=source_start,
            source_span_end_exclusive=source_end,
            source_quote_sha256=source_hash,
            confidence=1.0,
        )
        durable_candidate = DurableTaskDeltaCandidateV2(
            candidate_id=proposed_delta.candidate_id,
            operation=proposed_delta.operation,
            goal_patch=proposed_delta.goal_patch,
            input_candidates=(durable_input,),
            confidence=proposed_delta.confidence,
        )
        request_understanding_record = RequestUnderstandingRecordV2(
            request_understanding_record_id=_case_uuid(
                identity_seed,
                "request-understanding-record",
            ),
            run_id=run_id,
            message_ref=message_ref,
            schema_version="request_understanding_record.p0.v2",
            model_input_schema_version="e2e01-thin-v1",
            model_output_schema_version="e2e01-thin-v2",
            contextualization=DurableQueryContextualizationCandidateV2(
                text=request_output.contextualization.text,
                resolved_reference_candidates=(
                    DurableResolvedReferenceCandidateV2(
                        name="order_id",
                        candidate_value=message_order_id,
                        source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                        source_ref=message_ref,
                        source_span_start=source_start,
                        source_span_end_exclusive=source_end,
                        source_quote_sha256=source_hash,
                        confidence=1.0,
                    ),
                ),
                uncertainties=(),
                source_message_refs=(message_ref,),
            ),
            task_delta_candidates=(durable_candidate,),
            candidate_validation=(
                CandidateValidationRecordV2(
                    candidate_ref=proposed_delta.candidate_id,
                    decision=CandidateValidationDecision.ACCEPT,
                ),
            ),
            accepted_delta_refs=(accepted_delta.accepted_delta_id,),
            proposed_base_task_state_version=(
                request_output.next_move_candidate.base_task_state_version
            ),
            validated_task_state_version=1,
            next_move_candidate_ref=_case_uuid(identity_seed, "next-move"),
            created_at=NOW,
        )
        transitions: tuple[TaskStateTransition, ...]
        if task.state_version == 2:
            transitions = (
                TaskStateTransition(
                    task_id=task.task_id,
                    request_unit_id=request_unit.request_unit_id,
                    from_status=TaskStatus.ACTIVE,
                    to_status=task.status,
                    base_state_version=1,
                    result_state_version=2,
                    reason_ref=_case_uuid(identity_seed, "transition-reason"),
                    changed_at=task.updated_at,
                ),
            )
        else:
            assert task.state_version == 3
            transitions = (
                TaskStateTransition(
                    task_id=task.task_id,
                    request_unit_id=request_unit.request_unit_id,
                    from_status=TaskStatus.ACTIVE,
                    to_status=TaskStatus.WAITING_USER,
                    base_state_version=1,
                    result_state_version=2,
                    reason_ref=_case_uuid(identity_seed, "state-advanced"),
                    changed_at=NOW + timedelta(milliseconds=500),
                ),
                TaskStateTransition(
                    task_id=task.task_id,
                    request_unit_id=request_unit.request_unit_id,
                    from_status=TaskStatus.WAITING_USER,
                    to_status=task.status,
                    base_state_version=2,
                    result_state_version=3,
                    reason_ref=_case_uuid(identity_seed, "gate"),
                    changed_at=task.updated_at,
                ),
            )
        conversation_task_link = ConversationTaskLinkRecord(
            schema_version="conversation_task_link_record.p0.v1",
            conversation_id=conversation_id,
            task_id=task.task_id,
            link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
            linked_at=NOW,
        )
        run_task_link = RunTaskLinkRecord(
            schema_version="run_task_link_record.p0.v1",
            run_id=run_id,
            task_id=task.task_id,
            base_task_state_version=None,
            result_task_state_version=task.state_version,
        )
        context_ids = tuple(
            _case_uuid(identity_seed, f"context:{index}")
            for index in range(profile.model_calls)
        )
        model_call_ids = tuple(
            _case_uuid(identity_seed, f"model-call:{index}")
            for index in range(profile.model_calls)
        )
        failed_field_by_reason = {
            GateReasonCode.ARGUMENT_BINDING_MISMATCH: "argument_binding_valid",
            GateReasonCode.STATE_VERSION_MISMATCH: "state_version_valid",
            GateReasonCode.TOOL_NOT_REGISTERED: "registration_valid",
        }
        checks = {
            "snapshot_match": True,
            "registration_valid": True,
            "schema_valid": True,
            "trusted_field_valid": True,
            "argument_binding_valid": True,
            "budget_valid": True,
            "progress_valid": True,
            "state_version_valid": True,
            "action_boundary_valid": True,
        }
        if profile.gate_reason is not None:
            checks[failed_field_by_reason[profile.gate_reason]] = False
        gate = GateDecision(
            gate_decision_id=_case_uuid(identity_seed, "gate"),
            model_call_id=model_call_ids[0],
            context_manifest_id=context_ids[0],
            provider_tool_call_id="synthetic-provider-call",
            requested_provider_tool_name=profile.requested_tool_name,
            resolved_canonical_tool_name=(
                None
                if profile.gate_reason is GateReasonCode.TOOL_NOT_REGISTERED
                else "get_order"
            ),
            argument_binding_refs=(binding.binding_id,),
            proposed_base_task_state_version=None,
            validated_task_state_version=1,
            decision=profile.gate_decision,
            reason_code=profile.gate_reason,
            decided_at=NOW,
            **checks,
        )

        observation: OrderObservation | None = None
        if profile.observation_count == 1:
            projection = _presentation_input().order_summary
            observation = OrderObservation(
                observation_id=_case_uuid(identity_seed, "observation"),
                source_tool="get_order",
                source_resource_ref=profile.binding_order_id,
                source_version="order-v7",
                normalized_type="ORDER_SUMMARY",
                normalized_value=projection,
                observed_at=NOW,
                recorded_at=NOW,
                visibility=ObservationVisibility.MODEL_VISIBLE,
            )
        tool_call: ToolCallRecord | None = None
        tool_attempt: ToolAttemptRecord | None = None
        if profile.tool_call_status is not None:
            status = profile.tool_call_status
            tool_call = ToolCallRecord(
                tool_call_id=_case_uuid(identity_seed, "tool-call"),
                run_id=run_id,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                model_call_id=model_call_ids[0],
                context_manifest_id=context_ids[0],
                gate_decision_id=gate.gate_decision_id,
                provider_tool_call_id="synthetic-provider-call",
                canonical_tool_name="get_order",
                tool_registry_version="e2e01-thin-tools-v1",
                validated_task_state_version=1,
                argument_binding_refs=(binding.binding_id,),
                effect=ToolEffect.READ,
                attempt_count=1,
                status=status,
                started_at=NOW,
                finished_at=NOW + timedelta(milliseconds=500),
                failure_code=(
                    None
                    if status is ToolCallStatus.SUCCEEDED
                    else "NOT_FOUND_OR_NOT_ACCESSIBLE"
                ),
                result_ref=(
                    _case_uuid(identity_seed, "tool-result")
                    if observation is not None
                    else None
                ),
            )
            attempt_outcome = {
                ToolCallStatus.SUCCEEDED: ToolResultOutcome.SUCCESS,
                ToolCallStatus.FAILED: ToolResultOutcome.BUSINESS_FAILURE,
                ToolCallStatus.TIMED_OUT: ToolResultOutcome.TIMEOUT,
                ToolCallStatus.INTERRUPTED: ToolResultOutcome.INTERRUPTED,
            }.get(status)
            tool_attempt = ToolAttemptRecord(
                tool_call_id=tool_call.tool_call_id,
                attempt_no=1,
                started_at=tool_call.started_at,
                finished_at=tool_call.finished_at,
                outcome=attempt_outcome,
                failure_code=tool_call.failure_code,
            )
        request_understanding_calls = (
            profile.model_calls - profile.presentation_model_calls
        )
        manifests = tuple(
            ContextManifest(
                context_manifest_id=context_id,
                run_id=run_id,
                model_call_id=model_call_ids[index],
                tool_registry_version="e2e01-thin-tools-v1",
                model_visible_toolset_hash=compute_model_visible_toolset_hash(
                    (get_order_tool_spec(),)
                ),
                selected_message_refs=(message_ref,),
                task_state_ref_and_version=(
                    TaskStateRefAndVersion(
                        task_id=task.task_id,
                        state_version=1,
                    )
                    if task is not None and index >= request_understanding_calls
                    else None
                ),
                observation_refs_and_versions=(
                    (
                        VersionedRecordRef(
                            record_ref=observation.observation_id,
                            version="order-v7",
                        ),
                    )
                    if observation is not None and index >= request_understanding_calls
                    else ()
                ),
                redaction_policy_version="p0-redaction-v1",
                token_counts=TokenCounts(),
                assembled_at=NOW + timedelta(milliseconds=index),
            )
            for index, context_id in enumerate(context_ids)
        )
        initial_trace = _synthetic_trace(
            profile=profile,
            identity_seed=identity_seed,
            run_id=run_id,
            message_ref=message_ref,
            accepted_delta=accepted_delta,
            binding=binding,
            task=task,
            request_unit=request_unit,
            gate=gate,
            tool_call=tool_call,
            observation=observation,
            manifests=manifests,
        )
        evidence_observations = (observation,) if observation is not None else ()
        if self.fault == "raw_observation_visibility":
            assert observation is not None
            canonical_audit = observation.model_copy(
                update={"visibility": ObservationVisibility.AUDIT_ONLY}
            )
            raw_values = {
                field_name: getattr(canonical_audit, field_name)
                for field_name in OrderObservation.model_fields
            }
            raw_values["visibility"] = "AUDIT_ONLY"
            raw_observation = OrderObservation.model_construct(**raw_values)
            evidence_observations = (raw_observation,)
        elif self.fault == "observation_supersedes":
            assert observation is not None
            superseding = observation.model_copy(
                update={
                    "supersedes": _case_uuid(
                        identity_seed,
                        "previous-observation",
                    )
                }
            )
            evidence_observations = (superseding,)
        self.traces.seed(trace_ref, initial_trace)
        observable_values: dict[str, object] = {
            "http_status": profile.http_status,
            "user_outcome": profile.outcome,
            "response_policy": profile.response_policy,
            "ordinary_trace_shape": ordinary_trace_shape(initial_trace),
            "model_calls": profile.model_calls,
        }
        observable_values.update(self.observable_overrides)
        observable = UnboundSafeCaseObservable(**observable_values)
        evidence_values: dict[str, object] = {
            "observed_outcome": profile.outcome,
            "trace_ref": trace_ref,
            "trace_events": initial_trace,
            "run_record": AgentRunRecord(
                run_id=run_id,
                conversation_id=conversation_id,
                status=profile.run_status,
                provider_lane="offline_gate",
                started_at=NOW,
                completed_at=NOW + timedelta(seconds=1),
                stop_reason=profile.stop_reason,
            ),
            "agent_result": AgentRunResult(
                run_id=run_id,
                outcome=profile.outcome,
                message=_synthetic_message(profile, observation),
            ),
            "conversation_records": (
                ConversationRecord(
                    schema_version="conversation_record.p0.v1",
                    conversation_id=conversation_id,
                    owner_customer_id=profile.customer_id,
                    created_at=NOW,
                ),
            ),
            "message_records": (
                MessageRecord(
                    schema_version="message_record.p0.v1",
                    message_id=message_ref,
                    conversation_id=conversation_id,
                    direction=MessageDirection.USER,
                    content=execution_input.messages[0].content,
                    received_at=NOW,
                ),
            ),
            "request_understanding_records_v2": (
                request_understanding_record,
            ),
            "accepted_task_deltas_v2": (accepted_delta,),
            "task_state_transitions": transitions,
            "input_bindings": (binding,) if binding is not None else (),
            "task_records": (task,) if task is not None else (),
            "request_units": ((request_unit,) if request_unit is not None else ()),
            "conversation_task_links": (
                (conversation_task_link,) if conversation_task_link is not None else ()
            ),
            "run_task_links": ((run_task_link,) if run_task_link is not None else ()),
            "gate_decisions": (gate,) if gate is not None else (),
            "tool_calls": (tool_call,) if tool_call is not None else (),
            "tool_attempts": ((tool_attempt,) if tool_attempt is not None else ()),
            "observations": evidence_observations,
            "context_manifests": manifests,
            "model_visible_toolset_artifacts": (
                ModelVisibleToolsetArtifact(
                    model_visible_toolset_hash=(
                        compute_model_visible_toolset_hash(
                            (get_order_tool_spec(),)
                        )
                    ),
                    provider_visible_tool_specs=(get_order_tool_spec(),),
                ),
            ),
            "schema_assertions_pass": True,
            "identity_boundary_assertions_pass": True,
            "request_understanding_assertions_pass": True,
            "input_binding_assertions_pass": True,
            "task_state_assertions_pass": True,
            "tool_call_assertions_pass": True,
            "observation_assertions_pass": True,
            "disclosure_assertions_pass": True,
            "renderer_fact_assertions_pass": True,
            "error_mapping_assertions_pass": True,
            "persistence_assertions_pass": True,
            "toolset_replay_assertions_pass": True,
        }
        if self.fault == "request_candidate_mismatch":
            candidate = request_understanding_record.task_delta_candidates[0]
            mismatched_input = candidate.input_candidates[0].model_copy(
                update={"candidate_value": "O-2001"}
            )
            evidence_values["request_understanding_records_v2"] = (
                request_understanding_record.model_copy(
                    update={
                        "task_delta_candidates": (
                            candidate.model_copy(
                                update={
                                    "input_candidates": (
                                        mismatched_input,
                                    )
                                }
                            ),
                        )
                    }
                ),
            )
        elif self.fault == "missing_observation_manifest_ref":
            evidence_values["context_manifests"] = tuple(
                manifest.model_copy(
                    update={"observation_refs_and_versions": ()}
                )
                for manifest in manifests
            )
        evidence_values.update(self.evidence_overrides)
        evidence = UnboundEvalEvidence(**evidence_values)
        return EvalCaseSutResult(
            execution_ref=execution_input.execution_ref,
            evidence=evidence,
            safe_observable=observable,
        )


def _rebuild_exact_closure(
    closure: ExactRunEvidenceClosure,
    **updates: object,
) -> ExactRunEvidenceClosure:
    values = {
        field_name: getattr(closure, field_name)
        for field_name in ExactRunEvidenceClosure.model_fields
    }
    values.update(updates)
    return ExactRunEvidenceClosure(**values)


def _exact_closure_from_synthetic_result(
    result: EvalCaseSutResult,
    *,
    request_understanding_record_id: UUID,
) -> ExactRunEvidenceClosure:
    evidence = result.evidence
    assert evidence.run_record is not None
    assert len(evidence.conversation_records) == 1
    assert len(evidence.message_records) == 1
    assert len(evidence.request_understanding_records_v2) == 1
    assert len(evidence.accepted_task_deltas_v2) == 1
    assert len(evidence.input_bindings) == 1
    assert len(evidence.task_records) == 1
    assert len(evidence.request_units) == 1
    conversation = evidence.conversation_records[0]
    task = evidence.task_records[0]
    unit = evidence.request_units[0]
    understanding = evidence.request_understanding_records_v2[0].model_copy(
        update={
            "request_understanding_record_id": (
                request_understanding_record_id
            )
        }
    )
    child = evidence.accepted_task_deltas_v2[0]
    transitions = evidence.task_state_transitions

    trace_events = list(evidence.trace_events)
    run_stopped_index = next(
        index
        for index, event in enumerate(trace_events)
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    trace_events[run_stopped_index] = trace_events[run_stopped_index].model_copy(
        update={"occurred_at": evidence.run_record.completed_at}
    )

    if evidence.gate_decisions:
        assert len(evidence.gate_decisions) == 1
        gate = evidence.gate_decisions[0]
        gate_index = next(
            index
            for index, event in enumerate(trace_events)
            if event.event_type is TraceEventType.GATE_DECISION_RECORDED
        )
        trace_events[gate_index] = trace_events[gate_index].model_copy(
            update={
                "model_call_id": gate.model_call_id,
                "context_manifest_id": gate.context_manifest_id,
                "requested_tool_name": gate.requested_provider_tool_name,
                "validated_task_state_version": (
                    gate.validated_task_state_version
                ),
                "argument_binding_refs": gate.argument_binding_refs,
                "task_id": task.task_id,
                "request_unit_id": unit.request_unit_id,
            }
        )

    tool_calls = evidence.tool_calls
    tool_attempts = evidence.tool_attempts
    observations = evidence.observations
    if tool_calls:
        assert len(tool_calls) == len(tool_attempts) == 1
        call = tool_calls[0]
        created_event = next(
            event
            for event in trace_events
            if event.event_type is TraceEventType.TOOL_CALL_CREATED
        )
        terminal_type = {
            ToolCallStatus.SUCCEEDED: TraceEventType.TOOL_CALL_SUCCEEDED,
            ToolCallStatus.FAILED: TraceEventType.TOOL_CALL_FAILED,
        }[call.status]
        terminal_event = next(
            event for event in trace_events if event.event_type is terminal_type
        )
        call = call.model_copy(
            update={
                "started_at": created_event.occurred_at,
                "finished_at": terminal_event.occurred_at,
            }
        )
        attempt = tool_attempts[0].model_copy(
            update={
                "started_at": call.started_at,
                "finished_at": call.finished_at,
            }
        )
        normalized_index = next(
            index
            for index, event in enumerate(trace_events)
            if event.event_type is TraceEventType.TOOL_RESULT_NORMALIZED
        )
        trace_events[normalized_index] = trace_events[
            normalized_index
        ].model_copy(update={"occurred_at": call.finished_at})
        tool_calls = (call,)
        tool_attempts = (attempt,)

    if observations:
        assert tool_calls
        call = tool_calls[0]
        observation_index = next(
            index
            for index, event in enumerate(trace_events)
            if event.event_type is TraceEventType.OBSERVATION_RECORDED
        )
        observation = observations[0].model_copy(
            update={
                "observed_at": trace_events[observation_index].occurred_at,
                "recorded_at": trace_events[observation_index].occurred_at,
            }
        )
        trace_events[observation_index] = trace_events[
            observation_index
        ].model_copy(
            update={
                "tool_call_id": call.tool_call_id,
                "task_id": call.task_id,
                "request_unit_id": call.request_unit_id,
            }
        )
        observations = (observation,)

    return ExactRunEvidenceClosure(
        conversation_record=conversation,
        run_record=evidence.run_record,
        message_records=evidence.message_records,
        request_understanding_record=understanding,
        accepted_task_deltas=(child,),
        input_binding_records=evidence.input_bindings,
        task_records=evidence.task_records,
        task_state_transitions=transitions,
        request_unit_records=evidence.request_units,
        conversation_task_links=evidence.conversation_task_links,
        run_task_links=evidence.run_task_links,
        gate_decisions=evidence.gate_decisions,
        tool_calls=tool_calls,
        tool_attempts=tool_attempts,
        observation_records=observations,
        context_manifests=evidence.context_manifests,
        model_visible_toolset_artifacts=(
            evidence.model_visible_toolset_artifacts
        ),
        trace_events=tuple(trace_events),
    )


def _exact_closure_for_script(
    script_ref: str,
    *,
    fixture_slot: int,
) -> tuple[ExactRunEvidenceClosure, AgentRunResult]:
    (
        sut_execution_ref,
        script_execution_ref,
        request_understanding_record_id,
    ) = MAPPER_FIXTURE_IDENTITIES[fixture_slot]
    order_number = {
        "script:e2e01-01:success": "O-1001",
        "script:e2e01-04-b:nonexistent-order": "O-9999",
        "script:fault-provider:unknown-tool-name": "O-1001",
        "script:fault-runtime:state-advanced-before-gate": "O-1001",
        "script:fault-presentation:invalid-schema": "O-1001",
    }[script_ref]

    async def execute() -> EvalCaseSutResult:
        traces = InMemoryTraceCallbacks()
        provider = ScriptedModelProviderV2(
            ARTIFACTS.script_by_ref(script_ref),
            script_execution_ref=script_execution_ref,
        )
        result = await SyntheticSut(traces).execute_case(
            execution_input=EvalCaseExecutionInput(
                execution_ref=sut_execution_ref,
                messages=(
                    {
                        "role": "user",
                        "content": f"订单 {order_number} 状态怎么样？",
                    },
                ),
                trusted_context_fixture_ref="session:alice",
            ),
            scripted_provider=provider,
            runtime_fault=provider.take_runtime_fault_directive(),
        )
        assert type(result) is EvalCaseSutResult
        return result

    result = asyncio.run(execute())
    assert result.evidence.agent_result is not None
    return (
        _exact_closure_from_synthetic_result(
            result,
            request_understanding_record_id=(
                request_understanding_record_id
            ),
        ),
        result.evidence.agent_result,
    )


def _minimal_input_invalid_closure() -> tuple[
    ExactRunEvidenceClosure,
    AgentRunResult,
]:
    (
        run_id,
        conversation_id,
        message_id,
        model_call_id,
        context_id,
        message_trace_id,
        context_trace_id,
        stopped_trace_id,
    ) = MINIMAL_INPUT_INVALID_IDENTITIES
    completed_at = NOW + timedelta(seconds=1)
    artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=compute_model_visible_toolset_hash(
            (get_order_tool_spec(),)
        ),
        provider_visible_tool_specs=(get_order_tool_spec(),),
    )
    manifest = ContextManifest(
        context_manifest_id=context_id,
        run_id=run_id,
        model_call_id=model_call_id,
        tool_registry_version="e2e01-thin-tools-v1",
        model_visible_toolset_hash=artifact.model_visible_toolset_hash,
        selected_message_refs=(message_id,),
        redaction_policy_version="p0-redaction-v1",
        token_counts=TokenCounts(),
        assembled_at=NOW,
    )
    traces = (
        TraceEvent(
            trace_event_id=message_trace_id,
            event_type=TraceEventType.MESSAGE_ACCEPTED,
            occurred_at=NOW,
            run_id=run_id,
            message_ref=message_id,
        ),
        TraceEvent(
            trace_event_id=context_trace_id,
            event_type=TraceEventType.CONTEXT_MANIFEST_RECORDED,
            occurred_at=NOW + timedelta(milliseconds=1),
            run_id=run_id,
            model_call_id=model_call_id,
            model_call_purpose="REQUEST_UNDERSTANDING",
            context_manifest_id=context_id,
            tool_registry_version=manifest.tool_registry_version,
            model_visible_toolset_hash=manifest.model_visible_toolset_hash,
        ),
        TraceEvent(
            trace_event_id=stopped_trace_id,
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=run_id,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.INPUT_INVALID,
        ),
    )
    closure = ExactRunEvidenceClosure(
        conversation_record=ConversationRecord(
            schema_version="conversation_record.p0.v1",
            conversation_id=conversation_id,
            owner_customer_id="customer-A",
            created_at=NOW,
        ),
        run_record=AgentRunRecord(
            run_id=run_id,
            conversation_id=conversation_id,
            status=AgentRunStatus.COMPLETED,
            provider_lane="offline_gate",
            started_at=NOW,
            completed_at=completed_at,
            stop_reason=StopReason.INPUT_INVALID,
        ),
        message_records=(
            MessageRecord(
                schema_version="message_record.p0.v1",
                message_id=message_id,
                conversation_id=conversation_id,
                direction=MessageDirection.USER,
                content="订单 O-1001 状态怎么样？",
                received_at=NOW,
            ),
        ),
        request_understanding_record=None,
        accepted_task_deltas=(),
        input_binding_records=(),
        task_records=(),
        task_state_transitions=(),
        request_unit_records=(),
        conversation_task_links=(),
        run_task_links=(),
        gate_decisions=(),
        tool_calls=(),
        tool_attempts=(),
        observation_records=(),
        context_manifests=(manifest,),
        model_visible_toolset_artifacts=(artifact,),
        trace_events=traces,
    )
    return (
        closure,
        AgentRunResult(
            run_id=run_id,
            outcome=AgentOutcome.BLOCKED,
            message="当前无法安全处理该请求，请稍后重试。",
        ),
    )


def _order_service_unavailable_closure() -> tuple[
    ExactRunEvidenceClosure,
    AgentRunResult,
]:
    closure, _result = _exact_closure_for_script(
        "script:e2e01-04-b:nonexistent-order",
        fixture_slot=5,
    )
    task = closure.task_records[0].model_copy(
        update={"status": TaskStatus.BLOCKED}
    )
    unit = closure.request_unit_records[0].model_copy(
        update={"status": TaskStatus.BLOCKED}
    )
    transition = closure.task_state_transitions[0].model_copy(
        update={"to_status": TaskStatus.BLOCKED}
    )
    call = closure.tool_calls[0].model_copy(
        update={"failure_code": "ORDER_SERVICE_UNAVAILABLE"}
    )
    attempt = closure.tool_attempts[0].model_copy(
        update={
            "outcome": ToolResultOutcome.SYSTEM_FAILURE,
            "failure_code": "ORDER_SERVICE_UNAVAILABLE",
        }
    )
    run = closure.run_record.model_copy(
        update={"stop_reason": StopReason.ORDER_SERVICE_UNAVAILABLE}
    )
    traces = tuple(
        event.model_copy(
            update={
                "safe_tool_outcome": ToolResultOutcome.SYSTEM_FAILURE,
            }
        )
        if event.event_type is TraceEventType.TOOL_RESULT_NORMALIZED
        else event.model_copy(
            update={
                "user_outcome": AgentOutcome.BLOCKED,
                "stop_reason": StopReason.ORDER_SERVICE_UNAVAILABLE,
            }
        )
        if event.event_type is TraceEventType.RUN_STOPPED
        else event
        for event in closure.trace_events
    )
    unavailable = _rebuild_exact_closure(
        closure,
        run_record=run,
        task_records=(task,),
        task_state_transitions=(transition,),
        request_unit_records=(unit,),
        tool_calls=(call,),
        tool_attempts=(attempt,),
        trace_events=traces,
    )
    return (
        unavailable,
        AgentRunResult(
            run_id=run.run_id,
            outcome=AgentOutcome.BLOCKED,
            message="订单服务暂时不可用，请稍后重试。",
        ),
    )


class BoundaryProbeSut:
    def __init__(self) -> None:
        self.received_calls: list[dict[str, object]] = []

    async def execute_case(self, **kwargs: object) -> None:
        self.received_calls.append(dict(kwargs))
        return None


class ResultBoundaryMutationSut:
    def __init__(self, delegate: SyntheticSut, *, mutation: str) -> None:
        self._delegate = delegate
        self._mutation = mutation
        self.injected_container: object | None = None
        self.injected_arguments: object | None = None

    def _replace_trace_events(
        self,
        result: EvalCaseSutResult,
        trace_events: tuple[TraceEvent, ...],
    ) -> EvalCaseSutResult:
        self._delegate.traces.seed(
            result.evidence.trace_ref,
            trace_events,
        )
        observable = result.safe_observable.model_copy(
            update={
                "ordinary_trace_shape": ordinary_trace_shape(
                    trace_events
                )
            }
        )
        evidence = result.evidence.model_copy(
            update={"trace_events": trace_events}
        )
        return result.model_copy(
            update={
                "evidence": evidence,
                "safe_observable": observable,
            }
        )

    def _replace_schema_payload(
        self,
        result: EvalCaseSutResult,
        payload: object,
    ) -> EvalCaseSutResult:
        artifact = result.evidence.model_visible_toolset_artifacts[0]
        spec = artifact.provider_visible_tool_specs[0].model_copy(
            update={"input_schema": payload}
        )
        updated_artifact = artifact.model_copy(
            update={"provider_visible_tool_specs": (spec,)}
        )
        evidence = result.evidence.model_copy(
            update={
                "model_visible_toolset_artifacts": (updated_artifact,)
            }
        )
        return result.model_copy(update={"evidence": evidence})

    def _schema_with_extra(
        self,
        result: EvalCaseSutResult,
        key: object,
        value: object,
    ) -> EvalCaseSutResult:
        artifact = result.evidence.model_visible_toolset_artifacts[0]
        schema = artifact.provider_visible_tool_specs[0].input_schema
        payload = tuple.__new__(
            FrozenJsonDict,
            (*tuple(schema.items()), (key, value)),
        )
        self.injected_arguments = payload
        return self._replace_schema_payload(result, payload)

    async def execute_case(self, **kwargs: object) -> EvalCaseSutResult | None:
        result = await self._delegate.execute_case(**kwargs)
        assert type(result) is EvalCaseSutResult
        if self._mutation == "unknown_execution_ref":
            return result.model_copy(
                update={"execution_ref": UNKNOWN_EXECUTION_REF}
            )
        if self._mutation == "behaviorful_execution_ref":
            return result.model_copy(
                update={"execution_ref": EvilEquality()}
            )
        if self._mutation == "provider_execution_ref":
            provider = kwargs["scripted_provider"]
            return result.model_copy(
                update={"execution_ref": provider.script_execution_ref}
            )
        if self._mutation in {
            "semantic_evidence_case_id",
            "semantic_observable_case_id",
        }:
            target = (
                result.evidence
                if self._mutation == "semantic_evidence_case_id"
                else result.safe_observable
            )
            object.__setattr__(target, "case_id", "E2E01-01")
            return result
        if self._mutation == "trace_case_id":
            trace_events = (
                result.evidence.trace_events[0].model_copy(
                    update={"case_id": "E2E01-01"}
                ),
                *result.evidence.trace_events[1:],
            )
            return result.model_copy(
                update={
                    "evidence": result.evidence.model_copy(
                        update={"trace_events": trace_events}
                    )
                }
            )
        if self._mutation == "nested_trace_semantic_case_id":
            object.__setattr__(
                result.evidence.trace_events[0],
                "semantic_case_id",
                "E2E01-01",
            )
            return result
        if self._mutation == "nested_payload_cycle":
            understanding = result.evidence.request_understanding_records_v2[0]
            object.__setattr__(
                understanding,
                "task_delta_candidates",
                (understanding,),
            )
            return result
        if self._mutation.startswith("pydantic_sidecar:"):
            _, sidecar_kind, location = self._mutation.split(":")
            target: BaseModel = result
            storage_field = "safe_observable"
            if location == "nested":
                target = result.evidence.request_understanding_records_v2[0]
                storage_field = "contextualization"
            else:
                assert location == "root"
            if sidecar_kind == "fields-set":
                object.__setattr__(
                    target,
                    "__pydantic_fields_set__",
                    SneakyFieldsSet({"E2E01-01"}),
                )
            else:
                assert sidecar_kind == "storage-key"
                storage = target.__dict__
                stored_value = dict.__getitem__(
                    storage,
                    storage_field,
                )
                dict.__delitem__(storage, storage_field)
                dict.__setitem__(
                    storage,
                    SneakyStorageKey(storage_field),
                    stored_value,
                )
            SIDECAR_METHOD_READ_COUNTER.reads = 0
            return result
        if self._mutation == "custom_datetime_tz":
            conversation = result.evidence.conversation_records[0]
            created_at = conversation.created_at.replace(
                tzinfo=EvilTz(),
            )
            conversation = conversation.model_copy(
                update={"created_at": created_at}
            )
            evidence = result.evidence.model_copy(
                update={"conversation_records": (conversation,)}
            )
            TIMEZONE_METHOD_READ_COUNTER.reads = 0
            return result.model_copy(update={"evidence": evidence})
        if self._mutation.startswith("canonical_enum_storage:"):
            drift = self._mutation.partition(":")[2]
            member = AgentOutcome.COMPLETED
            if drift == "hidden":
                object.__setattr__(
                    member,
                    "hidden_case_id",
                    "E2E01-01",
                )
            elif drift == "name":
                object.__setattr__(member, "_name_", "E2E01-01")
            else:
                assert drift == "value"
                object.__setattr__(member, "_value_", "E2E01-01")
            return result
        if self._mutation.startswith("uuid_internal:"):
            slot_name = self._mutation.partition(":")[2]
            conversation_id = (
                result.evidence.conversation_records[0].conversation_id
            )
            if slot_name == "int":
                object.__setattr__(
                    conversation_id,
                    "int",
                    "E2E01-01",
                )
            else:
                assert slot_name == "is-safe"
                object.__setattr__(
                    conversation_id,
                    "is_safe",
                    "E2E01-01",
                )
            return result
        if self._mutation.startswith("positional_type_substitution:"):
            substitution = self._mutation.partition(":")[2]
            if substitution == "arguments-tuple":
                return self._replace_schema_payload(
                    result,
                    ("ordinary-value",),
                )
            if substitution == "arguments-model":
                return self._replace_schema_payload(
                    result,
                    TokenCounts(input_tokens=1, output_tokens=1),
                )
            if substitution == "cross-enum":
                task_records = (
                    result.evidence.task_records[0].model_copy(
                        update={"status": AgentOutcome.COMPLETED}
                    ),
                )
                evidence = result.evidence.model_copy(
                    update={"task_records": task_records}
                )
                return result.model_copy(update={"evidence": evidence})
            if substitution == "typed-tuple-model":
                evidence = result.evidence.model_copy(
                    update={
                        "trace_events": (
                            result.evidence.task_records[0],
                        )
                    }
                )
                return result.model_copy(update={"evidence": evidence})
            if substitution == "shared-frozen-dag":
                payload: object = tuple.__new__(
                    FrozenJsonList,
                    ("ordinary-value",),
                )
                for _ in range(20):
                    payload = tuple.__new__(
                        FrozenJsonList,
                        (payload, payload),
                    )
            elif substitution == "deep-frozen":
                payload = "ordinary-value"
                for _ in range(_MAX_PAYLOAD_DEPTH + 1):
                    payload = tuple.__new__(FrozenJsonList, (payload,))
            else:
                assert substitution == "wide-frozen"
                payload = tuple.__new__(
                    FrozenJsonList,
                    ("ordinary-value",) * (_MAX_PAYLOAD_EDGES + 1),
                )
            return self._schema_with_extra(
                result,
                "metadata",
                payload,
            )
        if self._mutation.startswith("nested_argument_business_value:"):
            identity_key = self._mutation.partition(":")[2]
            return self._schema_with_extra(
                result,
                identity_key,
                "business-opaque-value",
            )
        if self._mutation.startswith("nested_argument_identity:"):
            identity_key = self._mutation.partition(":")[2]
            identity_value = (
                "script:e2e01-01:success"
                if "script" in identity_key.casefold()
                else "E2E01-01"
            )
            return self._schema_with_extra(
                result,
                identity_key,
                identity_value,
            )
        if self._mutation.startswith(
            "nested_argument_authenticated_bundle_identity:"
        ):
            identity_kind = self._mutation.partition(":")[2]
            identity_field, identity_value = {
                "other-case": (
                    "customer_case_id",
                    "E2E01-04-A",
                ),
                "other-script": (
                    "script_owner_id",
                    "script:e2e01-04-a:foreign-order",
                ),
            }[identity_kind]
            return self._schema_with_extra(
                result,
                identity_field,
                identity_value,
            )
        if self._mutation.startswith("nested_argument_enum_identity:"):
            identity_kind = self._mutation.partition(":")[2]
            if identity_kind == "cycle":
                cyclic_enum = Enum(
                    "CyclicSmuggledIdentity",
                    {"VALUE": "opaque-cycle-value"},
                )
                identity_value = cyclic_enum.VALUE
                object.__setattr__(
                    identity_value,
                    "_value_",
                    identity_value,
                )
                identity_field = "customer_case_id"
            else:
                identity_field, identity_value = {
                    "case": (
                        "customer_case_id",
                        SmuggledCaseIdentity.VALUE,
                    ),
                    "script": (
                        "script_owner_id",
                        SmuggledScriptIdentity.VALUE,
                    ),
                    "nested-case": (
                        "customer_case_id",
                        OuterSmuggledCaseIdentity.VALUE,
                    ),
                    "subclass-case": (
                        "customer_case_id",
                        SubclassSmuggledCaseIdentity.VALUE,
                    ),
                    "wrapped-semantic": (
                        "customer_case_id",
                        WrappedSemanticIdentity.VALUE,
                    ),
                    "wrapped-bundle": (
                        "customer_case_id",
                        WrappedBundleIdentity.VALUE,
                    ),
                }[identity_kind]
            return self._schema_with_extra(
                result,
                identity_field,
                identity_value,
            )
        if self._mutation.startswith("nested_argument_enum_key:"):
            key_kind = self._mutation.partition(":")[2]
            if key_kind == "cycle":
                cyclic_enum = Enum(
                    "CyclicSmuggledKey",
                    {"VALUE": "opaque-cycle-key"},
                )
                enum_key = cyclic_enum.VALUE
                object.__setattr__(enum_key, "_value_", enum_key)
            else:
                enum_key = {
                    "plain-semantic": SemanticCaseCodeKey.VALUE,
                    "nested-semantic": OuterSemanticScriptUuidKey.VALUE,
                    "subclass-semantic": (
                        SubclassSemanticCaseNumberKey.VALUE
                    ),
                    "ordinary-business": OrdinaryBusinessKey.VALUE,
                    "ordinary-lexical": OrdinaryLexicalKey.VALUE,
                    "ordinary-subclass": (
                        SubclassOrdinaryLexicalKey.VALUE
                    ),
                }[key_kind]
            return self._schema_with_extra(
                result,
                enum_key,
                "business-opaque-value",
            )
        if self._mutation.startswith("nested_argument_bytes_identity:"):
            identity_kind = self._mutation.partition(":")[2]
            identity_field, identity_value = {
                "selected-case": (
                    "customer_case_id",
                    b"E2E01-01",
                ),
                "other-script": (
                    "script_owner_id",
                    b"script:e2e01-04-a:foreign-order",
                ),
            }[identity_kind]
            return self._schema_with_extra(
                result,
                identity_field,
                identity_value,
            )
        if self._mutation.startswith(
            "nested_argument_noncanonical_container:"
        ):
            container_kind = self._mutation.partition(":")[2]
            container = {
                "dict": {"value": "ordinary-value"},
                "list": ["ordinary-value"],
                "tuple": ("ordinary-value",),
                "set": {"ordinary-value"},
                "frozenset": frozenset({"ordinary-value"}),
                "flip-mapping": FlipMapping(),
                "flip-list": FlipList(),
                "flip-tuple": FlipTuple(),
                "flip-set": FlipSet(),
            }[container_kind]
            self.injected_container = container
            return self._schema_with_extra(
                result,
                "metadata",
                container,
            )
        if self._mutation == "nested_argument_duplicate_frozen_identity":
            artifact = result.evidence.model_visible_toolset_artifacts[0]
            schema = artifact.provider_visible_tool_specs[0].input_schema
            payload = tuple.__new__(
                FrozenJsonDict,
                (
                    *tuple(schema.items()),
                    ("metadata", "ordinary-value"),
                    ("metadata", "E2E01-04-A"),
                ),
            )
            self.injected_arguments = payload
            return self._replace_schema_payload(result, payload)
        if self._mutation == "nested_argument_canonical_frozen_json":
            artifact = result.evidence.model_visible_toolset_artifacts[0]
            schema = dict(
                artifact.provider_visible_tool_specs[0].input_schema
            )
            schema["metadata"] = {
                "label": "ordinary-value",
                "items": [1, "two"],
            }
            payload = freeze_json_value(schema)
            self.injected_arguments = payload
            return self._replace_schema_payload(result, payload)
        if self._mutation.startswith("nested_argument_flip_enum:"):
            enum_location = self._mutation.partition(":")[2]
            FLIP_ENUM_VALUE_READ_COUNTER.reads = 0
            if enum_location == "key":
                return self._schema_with_extra(
                    result,
                    FlipValueEnum.VALUE,
                    "ordinary-value",
                )
            return self._schema_with_extra(
                result,
                "metadata",
                FlipValueEnum.VALUE,
            )
        if self._mutation.startswith("nested_argument_str_subclass:"):
            string_location = self._mutation.partition(":")[2]
            FLIP_STRING_METHOD_READ_COUNTER.reads = 0
            if string_location == "key":
                return self._schema_with_extra(
                    result,
                    FlipString("metadata"),
                    "ordinary-value",
                )
            return self._schema_with_extra(
                result,
                "metadata",
                (
                    FlipString("ordinary-value")
                    if string_location == "ordinary-value"
                    else IdentityString("E2E01-01")
                ),
            )
        if self._mutation == "allowed_business_identity_keys":
            return result
        if self._mutation.startswith("normalized_outcome:"):
            outcome_name = self._mutation.partition(":")[2]
            normalized_outcome = (
                None
                if outcome_name == "NONE"
                else ToolResultOutcome(outcome_name)
            )
            trace_events = tuple(
                (
                    event.model_copy(
                        update={"safe_tool_outcome": normalized_outcome}
                    )
                    if event.event_type
                    is TraceEventType.TOOL_RESULT_NORMALIZED
                    else event
                )
                for event in result.evidence.trace_events
            )
            return self._replace_trace_events(
                result,
                trace_events,
            )
        if self._mutation.startswith("gate_projection:"):
            target_type = TraceEventType(
                self._mutation.partition(":")[2]
            )
            trace_events = tuple(
                (
                    event.model_copy(
                        update={
                            "gate_decision": GateDecisionValue.REJECT,
                            "gate_reason_code": (
                                GateReasonCode.TOOL_NOT_REGISTERED
                            ),
                        }
                    )
                    if event.event_type is target_type
                    else event
                )
                for event in result.evidence.trace_events
            )
            return self._replace_trace_events(result, trace_events)
        if self._mutation.startswith("run_projection:"):
            target_type = TraceEventType(
                self._mutation.partition(":")[2]
            )
            trace_events = tuple(
                (
                    event.model_copy(
                        update={
                            "user_outcome": AgentOutcome.BLOCKED,
                            "stop_reason": StopReason.GATE_REJECTED,
                        }
                    )
                    if event.event_type is target_type
                    else event
                )
                for event in result.evidence.trace_events
            )
            return self._replace_trace_events(result, trace_events)
        if self._mutation.startswith("safe_outcome_projection:"):
            _, target_value, outcome_value = self._mutation.split(":", 2)
            target_type = TraceEventType(target_value)
            projected_outcome = ToolResultOutcome(outcome_value)
            tool_call = result.evidence.tool_calls[0]
            trace_events = tuple(
                (
                    event.model_copy(
                        update={
                            "tool_call_id": tool_call.tool_call_id,
                            "safe_tool_outcome": projected_outcome,
                        }
                    )
                    if event.event_type is target_type
                    else event
                )
                for event in result.evidence.trace_events
            )
            return self._replace_trace_events(result, trace_events)
        if self._mutation.startswith("safe_outcome_reference:"):
            reference_kind = self._mutation.partition(":")[2]
            trace_events = tuple(
                (
                    event.model_copy(
                        update={
                            "tool_call_id": (
                                None
                                if reference_kind == "missing"
                                else UUID(
                                    "00000000-0000-4000-8000-000000009999"
                                )
                            ),
                            "safe_tool_outcome": (
                                ToolResultOutcome.SUCCESS
                            ),
                        }
                    )
                    if event.event_type is TraceEventType.RUN_STOPPED
                    else event
                )
                for event in result.evidence.trace_events
            )
            return self._replace_trace_events(result, trace_events)
        if self._mutation == "observable_disagreement":
            mismatched_observable = result.safe_observable.model_copy(
                update={"user_outcome": AgentOutcome.BLOCKED}
            )
            return type(result)(
                execution_ref=result.execution_ref,
                evidence=result.evidence,
                safe_observable=mismatched_observable,
            )
        raise AssertionError(f"unknown result mutation {self._mutation}")


class ReplayWithoutProviderSut:
    def __init__(self, delegate: SyntheticSut) -> None:
        self._delegate = delegate
        self._first_result: EvalCaseSutResult | None = None
        self.calls = 0

    async def execute_case(self, **kwargs: object) -> EvalCaseSutResult | None:
        self.calls += 1
        if self._first_result is None:
            self._first_result = await self._delegate.execute_case(**kwargs)
            return self._first_result
        return self._first_result


class IncompleteThenStaleRefSut:
    def __init__(self, delegate: SyntheticSut) -> None:
        self._delegate = delegate
        self._incomplete_ref: UUID | None = None

    async def execute_case(self, **kwargs: object) -> EvalCaseSutResult | None:
        execution_input = kwargs["execution_input"]
        if self._incomplete_ref is None:
            self._incomplete_ref = execution_input.execution_ref
            return None
        result = await self._delegate.execute_case(**kwargs)
        assert type(result) is EvalCaseSutResult
        return result.model_copy(update={"execution_ref": self._incomplete_ref})


class CancellingSut:
    def __init__(self) -> None:
        self.calls = 0

    async def execute_case(self, **kwargs: object) -> None:
        self.calls += 1
        raise asyncio.CancelledError


def _harness(
    *,
    artifacts: LoadedE2E01Artifacts | None = None,
    sut: object | None = None,
    qwen_sut: object | None = None,
    traces: InMemoryTraceCallbacks | None = None,
    port: InMemoryResultPort | None = None,
    grader_runner=None,
    nonce_factory: Callable[..., UUID] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[
    OfflineEvalHarness,
    object,
    InMemoryTraceCallbacks,
    InMemoryResultPort,
]:
    timeline = traces.timeline if traces is not None else []
    traces = traces or InMemoryTraceCallbacks(timeline)
    port = port or InMemoryResultPort(timeline)
    traces.timeline = timeline
    port.timeline = timeline
    sut = sut or SyntheticSut(traces)
    harness_arguments: dict[str, object] = {
        "artifacts": artifacts or ARTIFACTS,
        "sut": sut,
        "trace_callbacks": traces,
        "result_port": cast(EvalResultPort, port),
        "clock": clock or (lambda: NOW + timedelta(seconds=2)),
        "grader_runner": grader_runner,
    }
    if nonce_factory is not None:
        harness_arguments["nonce_factory"] = nonce_factory
    if qwen_sut is not None:
        harness_arguments["qwen_sut"] = qwen_sut
    harness = OfflineEvalHarness(
        **harness_arguments,
    )
    return harness, sut, traces, port


def _run(
    harness: OfflineEvalHarness,
    *,
    case_ids: Sequence[str] = ("E2E01-01",),
    script_ref_by_case: Mapping[str, str] | None = None,
    lane: str = "offline_gate",
    attempt: int = 1,
):
    return asyncio.run(
        harness.run_lane(
            eval_run_id=EVAL_RUN_ID,
            lane=lane,
            attempt=attempt,
            case_ids=case_ids,
            script_ref_by_case=script_ref_by_case,
        )
    )


def test_execution_only_sut_input_excludes_case_oracle_and_nested_setup() -> None:
    source_case = ARTIFACTS.case_by_id("E2E01-01")
    case_values = source_case.model_dump(mode="json")
    source_message = dict(case_values["input"]["messages"][0])
    source_message["setup_answer"] = {
        "environment_fixture_ref": "order:oracle-only",
        "expected_user_outcome": "COMPLETED",
    }
    case_input = dict(case_values["input"])
    case_input["messages"] = [source_message]
    case_input["oracle_only_top_level"] = {
        "expected_control_result": "PASS",
    }
    case_values["input"] = case_input
    case = EvalCaseArtifact.model_validate(case_values)
    artifacts = ARTIFACTS.model_copy(
        update={
            "cases": tuple(
                case if item.case_id == case.case_id else item
                for item in ARTIFACTS.cases
            )
        }
    )
    probe = BoundaryProbeSut()
    traces = InMemoryTraceCallbacks()
    port = InMemoryResultPort()
    nonce_factory = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    harness = OfflineEvalHarness(
        artifacts=artifacts,
        sut=probe,
        trace_callbacks=traces,
        result_port=cast(EvalResultPort, port),
        clock=lambda: NOW + timedelta(seconds=2),
        nonce_factory=nonce_factory,
    )

    outcome = _run(harness)

    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert nonce_factory.calls == [((), {}), ((), {})]
    assert len(probe.received_calls) == 1
    received = probe.received_calls[0]
    assert set(received) == {
        "execution_input",
        "scripted_provider",
        "runtime_fault",
    }
    execution_input = received["execution_input"]
    assert set(type(execution_input).model_fields) == {
        "execution_ref",
        "messages",
        "trusted_context_fixture_ref",
    }
    assert execution_input.execution_ref == EXECUTION_REF_1
    assert execution_input.trusted_context_fixture_ref == (
        source_case.input["trusted_context_fixture_ref"]
    )
    assert execution_input.messages == (
        type(execution_input.messages[0])(
            role="user",
            content=source_case.input["messages"][0]["content"],
        ),
    )
    assert set(type(execution_input.messages[0]).model_fields) == {
        "role",
        "content",
    }
    assert execution_input.model_dump() == {
        "execution_ref": EXECUTION_REF_1,
        "messages": (
            {
                "role": "user",
                "content": source_case.input["messages"][0]["content"],
            },
        ),
        "trusted_context_fixture_ref": (
            source_case.input["trusted_context_fixture_ref"]
        ),
    }
    assert received["scripted_provider"].script_execution_ref == (
        SCRIPT_EXECUTION_REF_1
    )
    assert EXECUTION_REF_1 not in {
        uuid5(NAMESPACE_URL, source_case.case_id),
        uuid5(
            NAMESPACE_URL,
            tuple(source_case.input["model_script_refs"])[0],
        ),
    }
    with pytest.raises(ValidationError):
        type(execution_input)(
            **execution_input.model_dump(),
            case_id=source_case.case_id,
        )
    with pytest.raises(ValidationError):
        execution_input.messages[0].content = "tampered"
    message_type = type(execution_input.messages[0])
    input_type = type(execution_input)
    with pytest.raises(ValidationError):
        message_type(role="assistant", content="not allowed")
    with pytest.raises(ValidationError):
        message_type(role="user", content="")
    with pytest.raises(ValidationError):
        input_type(
            execution_ref=EXECUTION_REF_1,
            messages=(),
            trusted_context_fixture_ref=(
                source_case.input["trusted_context_fixture_ref"]
            ),
        )
    with pytest.raises(ValidationError):
        input_type(
            execution_ref=EXECUTION_REF_1,
            messages=(
                execution_input.messages[0],
                execution_input.messages[0],
            ),
            trusted_context_fixture_ref=(
                source_case.input["trusted_context_fixture_ref"]
            ),
        )


def test_execution_ref_result_correlation_has_zero_argument_nonce_seam() -> None:
    constructor_parameters = signature(OfflineEvalHarness.__init__).parameters

    assert "nonce_factory" in constructor_parameters
    assert set(EvalCaseSutResult.model_fields) == {
        "execution_ref",
        "evidence",
        "safe_observable",
    }
    evidence_type = EvalCaseSutResult.model_fields["evidence"].annotation
    observable_type = EvalCaseSutResult.model_fields["safe_observable"].annotation
    assert "case_id" not in evidence_type.model_fields
    assert "case_id" not in observable_type.model_fields


def _map_exact_result(
    *,
    execution_ref: UUID,
    closure: ExactRunEvidenceClosure,
    agent_result: AgentRunResult,
    http_status: int = 200,
) -> EvalCaseSutResult:
    mapper = getattr(
        harness_module,
        "map_exact_run_http_result_to_sut_result",
    )
    calls: list[dict[str, object]] = []

    def mapper_spy(**kwargs: object) -> EvalCaseSutResult:
        calls.append(kwargs)
        return mapper(**kwargs)

    result = mapper_spy(
        execution_ref=execution_ref,
        http_status=http_status,
        agent_result=agent_result,
        closure=closure,
    )
    assert calls == [
        {
            "execution_ref": execution_ref,
            "http_status": http_status,
            "agent_result": agent_result,
            "closure": closure,
        }
    ]
    return result


def _mapper_traceback_state(
    error: BaseException,
) -> tuple[tuple[str, ...], frozenset[str], frozenset[type[object]]]:
    visited: set[int] = set()
    strings: set[str] = set()
    value_types: set[type[object]] = set()

    def visit(value: object) -> None:
        value_type = type(value)
        value_types.add(value_type)
        if value_type is str:
            strings.add(value)
            return
        if value is None or value_type in {bool, int, float, bytes, UUID}:
            return
        value_id = id(value)
        if value_id in visited:
            return
        visited.add(value_id)
        if isinstance(value, BaseModel):
            for field_name in type(value).model_fields:
                visit(getattr(value, field_name))
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(key)
                visit(item)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                visit(item)
            return
        if hasattr(value, "__dict__"):
            visit(vars(value))

    frame_names: list[str] = []
    traceback = error.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_globals.get("__name__") == "mini_agent.evaluation.harness":
            frame_names.append(frame.f_code.co_name)
            visit(dict(frame.f_locals))
        traceback = traceback.tb_next
    return tuple(frame_names), frozenset(strings), frozenset(value_types)


def test_exact_run_mapper_surface_is_case_and_oracle_free() -> None:
    mapper_signature = signature(
        getattr(
            harness_module,
            "map_exact_run_http_result_to_sut_result",
        )
    )
    parameters = mapper_signature.parameters
    assert tuple(parameters) == (
        "execution_ref",
        "http_status",
        "agent_result",
        "closure",
    )
    assert all(item.kind.name == "KEYWORD_ONLY" for item in parameters.values())
    assert all(
        item.default is item.empty
        for item in parameters.values()
    )
    assert {
        name: item.annotation
        for name, item in parameters.items()
    } == {
        "execution_ref": "UUID",
        "http_status": "int",
        "agent_result": "AgentRunResult",
        "closure": "ExactRunEvidenceClosure",
    }
    assert mapper_signature.return_annotation == "EvalCaseSutResult"
    assert {
        "case_id",
        "expectations",
        "script",
        "provider",
        "customer_id",
        "persistence_envelope",
        "grader_results",
    }.isdisjoint(parameters)


def test_exact_run_fixture_identities_are_opaque_and_external_ref_independent() -> None:
    first_closure, first_result = _exact_closure_for_script(
        "script:e2e01-01:success",
        fixture_slot=0,
    )
    first_external_mapping = _map_exact_result(
        execution_ref=EXECUTION_REF_1,
        closure=first_closure,
        agent_result=first_result,
    )
    second_external_mapping = _map_exact_result(
        execution_ref=UNKNOWN_EXECUTION_REF,
        closure=first_closure,
        agent_result=first_result,
    )

    assert first_external_mapping.evidence == second_external_mapping.evidence
    assert (
        first_external_mapping.safe_observable
        == second_external_mapping.safe_observable
    )
    assert first_closure.run_record.run_id not in {
        EXECUTION_REF_1,
        UNKNOWN_EXECUTION_REF,
    }
    assert all(
        identity.version == 4
        for identity in MAPPER_FIXTURE_IDENTITIES[0]
    )
    minimal_closure, minimal_result = _minimal_input_invalid_closure()
    first_mapped = _map_exact_result(
        execution_ref=EXECUTION_REF_4,
        closure=minimal_closure,
        agent_result=minimal_result,
    )
    second_mapped = _map_exact_result(
        execution_ref=UNKNOWN_EXECUTION_REF,
        closure=minimal_closure,
        agent_result=minimal_result,
    )
    unavailable_closure, unavailable_result = (
        _order_service_unavailable_closure()
    )
    unavailable_mapped = _map_exact_result(
        execution_ref=EXECUTION_REF_3,
        closure=unavailable_closure,
        agent_result=unavailable_result,
    )

    external_refs = {
        EXECUTION_REF_1,
        EXECUTION_REF_2,
        EXECUTION_REF_3,
        EXECUTION_REF_4,
        UNKNOWN_EXECUTION_REF,
    }
    assert len(set(MINIMAL_INPUT_INVALID_IDENTITIES)) == 8
    assert all(
        identity.version == 4
        for identity in MINIMAL_INPUT_INVALID_IDENTITIES
    )
    assert set(MINIMAL_INPUT_INVALID_IDENTITIES).isdisjoint(external_refs)
    assert first_mapped.execution_ref == EXECUTION_REF_4
    assert second_mapped.execution_ref == UNKNOWN_EXECUTION_REF
    assert first_mapped.evidence == second_mapped.evidence
    assert first_mapped.safe_observable == second_mapped.safe_observable
    assert minimal_closure.run_record.run_id not in external_refs
    assert minimal_closure.conversation_record.conversation_id not in external_refs
    assert all(
        message.message_id not in external_refs
        for message in minimal_closure.message_records
    )
    assert unavailable_mapped.evidence.run_record == (
        unavailable_closure.run_record
    )
    assert unavailable_closure.run_record.run_id not in external_refs
    for evidence in (
        first_external_mapping.evidence,
        first_mapped.evidence,
        unavailable_mapped.evidence,
    ):
        assert _payload_tree_is_closed(
            evidence,
            forbidden_identity_values=frozenset(external_refs),
            allow_any_schema_identity_value=True,
            allow_semantic_json_keys=True,
        )


@pytest.mark.parametrize(
    ("fixture_slot", "script_ref", "execution_ref", "expected_policy"),
    [
        (
            0,
            "script:e2e01-01:success",
            EXECUTION_REF_1,
            "DETERMINISTIC_ORDER_SUMMARY_V1",
        ),
        (
            1,
            "script:e2e01-04-b:nonexistent-order",
            EXECUTION_REF_2,
            "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE",
        ),
        (
            2,
            "script:fault-provider:unknown-tool-name",
            EXECUTION_REF_3,
            "FIXED_SAFE_PROCESSING_ERROR",
        ),
        (
            3,
            "script:fault-runtime:state-advanced-before-gate",
            EXECUTION_REF_4,
            "FIXED_SAFE_PROCESSING_ERROR",
        ),
        (
            4,
            "script:fault-presentation:invalid-schema",
            EXECUTION_REF_1,
            "FIXED_SAFE_PROCESSING_ERROR",
        ),
    ],
)
def test_exact_run_mapper_projects_closed_terminal_paths_without_oracles(
    fixture_slot: int,
    script_ref: str,
    execution_ref: UUID,
    expected_policy: str,
) -> None:
    closure, agent_result = _exact_closure_for_script(
        script_ref,
        fixture_slot=fixture_slot,
    )
    result = _map_exact_result(
        execution_ref=execution_ref,
        closure=closure,
        agent_result=agent_result,
    )

    assert result.execution_ref == execution_ref
    assert result.evidence.trace_ref == closure.run_record.run_id
    assert result.evidence.run_record == closure.run_record
    assert result.evidence.agent_result == agent_result
    assert result.evidence.conversation_records == (
        closure.conversation_record,
    )
    assert result.evidence.message_records == closure.message_records
    assert result.evidence.request_understanding_records_v2 == (
        closure.request_understanding_record,
    )
    assert (
        result.evidence.accepted_task_deltas_v2
        == closure.accepted_task_deltas
    )
    assert (
        result.evidence.task_state_transitions
        == closure.task_state_transitions
    )
    assert result.evidence.trace_events == closure.trace_events
    assert result.safe_observable.response_policy == expected_policy
    assert result.safe_observable.user_outcome is agent_result.outcome
    assert result.safe_observable.ordinary_trace_shape == ordinary_trace_shape(
        closure.trace_events
    )
    assert result.safe_observable.model_calls == len(
        closure.context_manifests
    )


def test_exact_run_mapper_projects_logical_observation_source_version_chain() -> None:
    closure, agent_result = _exact_closure_for_script(
        "script:e2e01-01:success",
        fixture_slot=6,
    )
    result = _map_exact_result(
        execution_ref=EXECUTION_REF_1,
        closure=closure,
        agent_result=agent_result,
    )

    observation = result.evidence.observations[0]
    call = result.evidence.tool_calls[0]
    presentation_manifest = result.evidence.context_manifests[1]
    assert observation.source_tool == call.canonical_tool_name
    assert presentation_manifest.observation_refs_and_versions == (
        VersionedRecordRef(
            record_ref=observation.observation_id,
            version=observation.source_version,
        ),
    )


def test_exact_run_mapper_has_fixed_unavailable_source_policy_without_case_artifact() -> None:
    closure, agent_result = _order_service_unavailable_closure()
    result = _map_exact_result(
        execution_ref=EXECUTION_REF_3,
        closure=closure,
        agent_result=agent_result,
    )

    assert result.evidence.observed_outcome is AgentOutcome.BLOCKED
    assert result.safe_observable.response_policy == (
        "FIXED_ORDER_SERVICE_UNAVAILABLE"
    )
    assert agent_result.message == "订单服务暂时不可用，请稍后重试。"
    assert "case_id" not in type(result.evidence).model_fields


def test_exact_run_mapper_projects_input_invalid_without_synthetic_runtime_records() -> None:
    closure, agent_result = _minimal_input_invalid_closure()
    result = _map_exact_result(
        execution_ref=EXECUTION_REF_4,
        closure=closure,
        agent_result=agent_result,
    )

    assert result.evidence.run_record.stop_reason is StopReason.INPUT_INVALID
    assert result.evidence.observed_outcome is AgentOutcome.BLOCKED
    assert result.safe_observable.response_policy == "FIXED_SAFE_PROCESSING_ERROR"
    assert result.evidence.request_understanding_records_v2 == ()
    assert result.evidence.accepted_task_deltas_v2 == ()
    assert result.evidence.task_records == ()
    assert result.evidence.request_units == ()
    assert result.evidence.gate_decisions == ()
    assert result.evidence.tool_calls == ()


@pytest.mark.parametrize(
    "stop_reason",
    (
        StopReason.PROVIDER_PROTOCOL_ERROR,
        StopReason.RENDERER_INVARIANT_FAILED,
    ),
)
def test_exact_run_mapper_projects_terminal_protocol_and_renderer_failures(
    stop_reason: StopReason,
) -> None:
    if stop_reason is StopReason.RENDERER_INVARIANT_FAILED:
        closure, source_result = _order_service_unavailable_closure()
        agent_result = source_result.model_copy(
            update={"message": "当前无法安全处理该请求，请稍后重试。"}
        )
    else:
        closure, agent_result = _minimal_input_invalid_closure()
    run = closure.run_record.model_copy(update={"stop_reason": stop_reason})
    traces = tuple(
        event.model_copy(update={"stop_reason": stop_reason})
        if event.event_type is TraceEventType.RUN_STOPPED
        else event
        for event in closure.trace_events
    )
    terminal_closure = _rebuild_exact_closure(
        closure,
        run_record=run,
        trace_events=traces,
    )

    result = _map_exact_result(
        execution_ref=EXECUTION_REF_4,
        closure=terminal_closure,
        agent_result=agent_result,
    )
    remapped = _map_exact_result(
        execution_ref=UNKNOWN_EXECUTION_REF,
        closure=terminal_closure,
        agent_result=agent_result,
    )

    assert result.evidence.run_record.stop_reason is stop_reason
    assert result.evidence.observed_outcome is AgentOutcome.BLOCKED
    assert result.safe_observable.response_policy == "FIXED_SAFE_PROCESSING_ERROR"
    assert result.evidence == remapped.evidence
    assert result.safe_observable == remapped.safe_observable
    assert terminal_closure.run_record.run_id not in {
        EXECUTION_REF_4,
        UNKNOWN_EXECUTION_REF,
    }


@pytest.mark.parametrize(
    ("status", "stop_reason"),
    (
        (AgentRunStatus.COMPLETED, StopReason.PROCESS_RESTART_DETECTED),
        (AgentRunStatus.RUNNING, None),
    ),
)
def test_exact_run_mapper_rejects_restart_and_non_completed_runs(
    status: AgentRunStatus,
    stop_reason: StopReason | None,
) -> None:
    closure, agent_result = _minimal_input_invalid_closure()
    run = closure.run_record.model_copy(
        update={
            "status": status,
            "stop_reason": stop_reason,
            "completed_at": (
                closure.run_record.completed_at
                if status is AgentRunStatus.COMPLETED
                else None
            ),
        }
    )
    invalid_closure = closure.model_copy(update={"run_record": run})

    errors = []
    for execution_ref in (EXECUTION_REF_4, UNKNOWN_EXECUTION_REF):
        with pytest.raises(EvalHarnessCommandError) as caught:
            _map_exact_result(
                execution_ref=execution_ref,
                closure=invalid_closure,
                agent_result=agent_result,
            )
        errors.append(caught.value)
        assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
    assert errors[0] is not errors[1]
    assert closure.run_record.run_id not in {
        EXECUTION_REF_4,
        UNKNOWN_EXECUTION_REF,
    }


@pytest.mark.parametrize(
    "mutation",
    ["http", "execution_ref", "run_id", "outcome", "fixed_message"],
)
def test_exact_run_mapper_rejects_identity_outcome_and_policy_mismatch_boundedly(
    mutation: str,
) -> None:
    closure, agent_result = _minimal_input_invalid_closure()
    execution_ref = EXECUTION_REF_4
    http_status = 200
    if mutation == "http":
        http_status = 503
    elif mutation == "execution_ref":
        execution_ref = UUID(int=1)
    elif mutation == "run_id":
        agent_result = agent_result.model_copy(update={"run_id": UUID(int=2)})
    elif mutation == "outcome":
        agent_result = agent_result.model_copy(
            update={"outcome": AgentOutcome.COMPLETED}
        )
    else:
        agent_result = agent_result.model_copy(
            update={"message": "raw-policy-secret"}
        )

    errors = []
    for _ in range(2):
        with pytest.raises(EvalHarnessCommandError) as caught:
            _map_exact_result(
                execution_ref=execution_ref,
                http_status=http_status,
                closure=closure,
                agent_result=agent_result,
            )
        errors.append(caught.value)
        assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert "raw-policy-secret" not in str(caught.value)
        frame_names, strings, value_types = _mapper_traceback_state(
            caught.value
        )
        assert frame_names == ("map_exact_run_http_result_to_sut_result",)
        assert {
            "raw-policy-secret",
            "customer-A",
        }.isdisjoint(strings)
        assert AgentRunResult not in value_types
        assert ExactRunEvidenceClosure not in value_types
    assert errors[0] is not errors[1]


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_execution_ref",
        "provider_execution_ref",
        "semantic_evidence_case_id",
        "semantic_observable_case_id",
        "trace_case_id",
        "nested_trace_semantic_case_id",
        "nested_payload_cycle",
        "observable_disagreement",
    ],
)
def test_result_correlation_rejects_unbound_spoofing_before_grading(
    mutation: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(delegate, mutation=mutation)
    nonce_factory = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )

    outcome = _run(harness)

    assert nonce_factory.calls == [((), {}), ((), {})]
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_behaviorful_execution_ref_is_closed_before_equality() -> None:
    BOUNDARY_METHOD_READ_COUNTER.reads = 0
    traces = InMemoryTraceCallbacks()
    sut = ResultBoundaryMutationSut(
        SyntheticSut(traces),
        mutation="behaviorful_execution_ref",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("behaviorful execution ref reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert BOUNDARY_METHOD_READ_COUNTER.reads == 0
    assert grader_called is False
    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    ("sidecar_kind", "location"),
    (
        ("fields-set", "root"),
        ("fields-set", "nested"),
        ("storage-key", "root"),
        ("storage-key", "nested"),
    ),
)
def test_noncanonical_pydantic_sidecar_fails_without_method_read(
    sidecar_kind: str,
    location: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"pydantic_sidecar:{sidecar_kind}:{location}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("noncanonical Pydantic sidecar reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert SIDECAR_METHOD_READ_COUNTER.reads == 0
    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_custom_datetime_timezone_fails_without_method_read() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation="custom_datetime_tz",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("custom datetime timezone reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert TIMEZONE_METHOD_READ_COUNTER.reads == 0
    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize("drift", ("hidden", "name", "value"))
def test_canonical_enum_storage_drift_fails_before_grading(
    drift: str,
) -> None:
    member = AgentOutcome.COMPLETED
    storage = object.__getattribute__(member, "__dict__")
    original_items = tuple(
        (key, dict.__getitem__(storage, key))
        for key in dict.__iter__(storage)
    )
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"canonical_enum_storage:{drift}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("mutated canonical Enum reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    try:
        outcome = _run(harness)
    finally:
        storage = object.__getattribute__(member, "__dict__")
        dict.clear(storage)
        for key, stored_value in original_items:
            dict.__setitem__(storage, key, stored_value)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize("slot_name", ("int", "is-safe"))
def test_mutated_uuid_internal_state_fails_before_grading(
    slot_name: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"uuid_internal:{slot_name}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("mutated UUID reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "substitution",
    (
        "arguments-tuple",
        "arguments-model",
        "typed-tuple-model",
        "cross-enum",
        "shared-frozen-dag",
        "deep-frozen",
        "wide-frozen",
    ),
)
def test_schema_position_substitution_fails_before_grading(
    substitution: str,
    recwarn: pytest.WarningsRecorder,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"positional_type_substitution:{substitution}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("schema-position substitution reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert list(recwarn) == []
    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_sut_cancellation_propagates_after_correlation_is_retired() -> None:
    sut = CancellingSut()
    nonce_factory = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    harness, _sut, _traces, port = _harness(
        sut=sut,
        nonce_factory=nonce_factory,
    )

    with pytest.raises(asyncio.CancelledError):
        _run(harness)

    assert sut.calls == 1
    assert nonce_factory.calls == [((), {}), ((), {})]
    assert harness._pending_case_by_execution_ref == {}
    assert harness._retired_execution_refs == {EXECUTION_REF_1}
    assert port.results == {}
    assert port.failures == []


@pytest.mark.parametrize(
    "seam",
    (
        "nonce",
        "sut",
        "trace-append",
        "trace-reload",
        "grader",
        "result-append",
        "result-load",
        "failure-append",
        "clock",
    ),
)
def test_command_scope_restores_singletons_on_injected_base_exception(
    seam: str,
) -> None:
    class InjectedBoundaryAbort(BaseException):
        pass

    member = AgentOutcome.COMPLETED
    member_storage = object.__getattribute__(member, "__dict__")
    original_items = tuple(
        (key, dict.__getitem__(member_storage, key))
        for key in dict.__iter__(member_storage)
    )
    abort: BaseException = (
        asyncio.CancelledError("synthetic-cancellation")
        if seam == "sut"
        else InjectedBoundaryAbort("synthetic-boundary-abort")
    )

    def mutate_singleton() -> None:
        object.__setattr__(
            member,
            "hidden_case_id",
            "E2E01-01",
        )

    traces: InMemoryTraceCallbacks = InMemoryTraceCallbacks()
    port: InMemoryResultPort = InMemoryResultPort()
    sut: object = SyntheticSut(traces)
    nonce_factory: Callable[..., UUID] = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    grader_runner = None
    clock: Callable[[], datetime] | None = None

    if seam == "nonce":

        def aborting_nonce() -> UUID:
            mutate_singleton()
            raise abort

        nonce_factory = aborting_nonce
    elif seam == "sut":

        class MutatingCancellingSut:
            async def execute_case(self, **kwargs: object) -> None:
                mutate_singleton()
                raise abort

        sut = MutatingCancellingSut()
    elif seam == "trace-append":

        class AbortingAppendTraceCallbacks(InMemoryTraceCallbacks):
            async def append_eval_case_graded(
                self,
                event: TraceEvent,
            ) -> None:
                mutate_singleton()
                raise abort

        traces = AbortingAppendTraceCallbacks()
        sut = SyntheticSut(traces)
    elif seam == "trace-reload":

        class AbortingReloadTraceCallbacks(InMemoryTraceCallbacks):
            async def reload_trace(
                self,
                trace_ref: UUID,
            ) -> tuple[TraceEvent, ...]:
                mutate_singleton()
                raise abort

        traces = AbortingReloadTraceCallbacks()
        sut = SyntheticSut(traces)
    elif seam == "grader":

        def aborting_grader(*args: object) -> GradingOutcome:
            mutate_singleton()
            raise abort

        grader_runner = aborting_grader
    elif seam == "result-append":

        class AbortingResultAppendPort(InMemoryResultPort):
            async def append_eval_result(
                self,
                record: EvalResultRecord,
            ) -> InsertOnlyWriteResult:
                mutate_singleton()
                raise abort

        port = AbortingResultAppendPort()
    elif seam == "result-load":

        class AbortingResultLoadPort(InMemoryResultPort):
            async def append_eval_result(
                self,
                record: EvalResultRecord,
            ) -> InsertOnlyWriteResult:
                return InsertOnlyWriteResult.ALREADY_EXISTS

            async def load_eval_result(
                self,
                *,
                eval_run_id: UUID,
                case_id: str,
                lane: str,
                attempt: int,
            ) -> EvalResultRecord | None:
                mutate_singleton()
                raise abort

        port = AbortingResultLoadPort()
    elif seam == "failure-append":

        class AbortingFailureAppendPort(InMemoryResultPort):
            async def append_eval_execution_failure(
                self,
                record: EvalExecutionFailureRecord,
            ) -> None:
                mutate_singleton()
                raise abort

        port = AbortingFailureAppendPort()
        sut = SyntheticSut(traces, fault="sut")
    elif seam == "clock":

        def aborting_clock() -> datetime:
            mutate_singleton()
            raise abort

        clock = aborting_clock
        sut = SyntheticSut(traces, fault="sut")
    else:
        assert seam == "result-append"

    harness, *_ = _harness(
        sut=sut,
        traces=traces,
        port=port,
        grader_runner=grader_runner,
        nonce_factory=nonce_factory,
        clock=clock,
    )

    try:
        with pytest.raises(type(abort)) as caught:
            _run(harness)
        restored_by_harness = _canonical_enum_storage_is_pristine(
            member,
            original_items,
        )
    finally:
        member_storage = object.__getattribute__(
            member,
            "__dict__",
        )
        dict.clear(member_storage)
        for key, stored_value in original_items:
            dict.__setitem__(
                member_storage,
                key,
                stored_value,
            )

    if seam == "sut":
        assert caught.value.args == abort.args
    else:
        assert caught.value is abort
    assert restored_by_harness is True
    assert harness._pending_case_by_execution_ref == {}
    assert harness._persisted_stage_by_replay_key == {}
    assert port.results == {}
    assert port.failures == []
    assert port.events == []
    if seam == "nonce":
        assert harness._retired_execution_refs == set()
    else:
        assert harness._retired_execution_refs == {EXECUTION_REF_1}


@pytest.mark.parametrize(
    "identity_alias",
    (
        "case_ref",
        "caseId",
        "Case_ID",
        "case_identifier",
        "evaluation_case_id",
        "test_case_id",
        "case_key",
        "model_script_ref",
        "model_script_reference",
        "script_identifier",
        "case-identity",
        "EvaluationCaseReference",
        "semantic case key",
        "ModelScriptReference",
        "SCRIPT-IDENTIFIER",
        "evaluationcaseid",
        "TESTCASEID",
        "modelscriptreference",
        "semanticscriptkey",
        "canonical_case_id",
        "canonical-case-id",
        "canonical case id",
        "CanonicalCaseId",
        "canonicalcaseid",
        "CANONICAL_CASE_ID",
        "golden_case_id",
        "reference_case_id",
        "suite_case_id",
        "ground_truth_case_id",
        "groundTruthCaseId",
        "groundtruthcaseid",
        "canonical_script_reference",
        "CanonicalScriptReference",
        "canonicalscriptreference",
    ),
)
def test_nested_normalized_semantic_identity_alias_fails_completeness(
    identity_alias: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_identity:{identity_alias}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("semantic identity reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "semantic_field_name",
    (
        "case_code",
        "case-code",
        "case code",
        "caseCode",
        "CaseCode",
        "case_uuid",
        "case-uuid",
        "case uuid",
        "caseUuid",
        "CaseUUID",
        "case_number",
        "case-number",
        "case number",
        "caseNumber",
        "CaseNumber",
        "script_code",
        "script-code",
        "script code",
        "scriptCode",
        "ScriptCode",
        "script_uuid",
        "script-uuid",
        "script uuid",
        "scriptUuid",
        "ScriptUUID",
        "script_number",
        "script-number",
        "script number",
        "scriptNumber",
        "ScriptNumber",
        "model_script_code",
        "model-script-code",
        "model script code",
        "modelScriptCode",
        "ModelScriptCode",
        "model_script_uuid",
        "model-script-uuid",
        "model script uuid",
        "modelScriptUuid",
        "ModelScriptUUID",
        "evaluation_case_code",
        "evaluation-case-code",
        "evaluation case code",
        "evaluationCaseCode",
        "EvaluationCaseCode",
        "eval_case_uuid",
        "test-case-code",
        "semantic script uuid",
        "expectedCaseCode",
        "CanonicalScriptUUID",
        "casecode",
        "scriptuuid",
        "modelscriptcode",
        "modelscriptuuid",
        "evaluationcasecode",
        "evalcaseuuid",
        "requestcasecode",
        "runtimecaseuuid",
        "providerscriptcode",
        "java_script_uuid",
        "javaScriptUuid",
        "de_script_ion",
        "case_fold",
        "show_case_code",
        "showCaseCode",
        "tran_script_uuid",
        "stair_case_number",
        "lower_case_id",
    ),
)
def test_semantic_entity_field_with_opaque_value_fails_completeness(
    semantic_field_name: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"nested_argument_business_value:{semantic_field_name}"
        ),
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("semantic entity field reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "business_identity_key",
    (
        "order_id",
        "customer_id",
        "owner_customer_id",
        "task_id",
        "run_id",
        "message_ref",
        "tool_call_id",
        "request_unit_id",
        "observation_ref",
        "input_binding_ref",
        "showcase_id",
        "showcaseid",
        "transcript_reference",
        "script_version",
        "case_status",
        "use_case_label",
        "use_case_id",
        "usecaseid",
        "customer_case_id",
        "customerCaseId",
        "show_case_id",
        "showCaseId",
        "script_owner_id",
        "description",
        "description_id",
        "lowercase_id",
        "uppercase_reference",
        "javascript_ref",
        "staircase_key",
        "descriptionid",
        "lowercaseid",
        "uppercasereference",
        "javascriptref",
        "staircasekey",
        "showcase_code",
        "showcaseCode",
        "transcript_uuid",
        "transcriptUuid",
        "description_code",
        "javascript_uuid",
        "staircase_number",
        "showcasecode",
        "transcriptuuid",
        "javascriptuuid",
        "casefold",
        "scripture",
    ),
)
def test_business_identity_key_is_not_a_semantic_eval_identity(
    business_identity_key: str,
) -> None:
    assert _is_semantic_identity_field(business_identity_key) is False


def test_reviewed_safe_identity_field_tokens_are_exactly_pinned() -> None:
    assert _SAFE_IDENTITY_FIELD_TOKEN_TUPLES == frozenset(
        {
            ("case", "status"),
            ("casefold",),
            ("casestatus",),
            ("customer", "case", "id"),
            ("customercaseid",),
            ("description",),
            ("description", "code"),
            ("description", "id"),
            ("descriptioncode",),
            ("descriptionid",),
            ("javascript", "ref"),
            ("javascript", "uuid"),
            ("javascriptref",),
            ("javascriptuuid",),
            ("lowercase", "id"),
            ("lowercaseid",),
            ("script", "owner", "id"),
            ("script", "version"),
            ("scriptownerid",),
            ("scripture",),
            ("scriptversion",),
            ("show", "case", "id"),
            ("showcase", "code"),
            ("showcase", "id"),
            ("showcasecode",),
            ("showcaseid",),
            ("staircase", "key"),
            ("staircase", "number"),
            ("staircasekey",),
            ("staircasenumber",),
            ("transcript", "reference"),
            ("transcript", "uuid"),
            ("transcriptreference",),
            ("transcriptuuid",),
            ("uppercase", "reference"),
            ("uppercasereference",),
            ("use", "case", "id"),
            ("use", "case", "label"),
            ("usecaseid",),
            ("usecaselabel",),
        }
    )


def test_schema_controlled_tool_description_reaches_grading() -> None:
    assert get_order_tool_spec().description
    harness, _sut, _traces, _port = _harness(
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert len(outcome.results) == 1
    assert outcome.results[0].status is EvalResultStatus.PASS


def test_reachable_schema_identity_fields_match_reviewed_set() -> None:
    assert _DISCOVERED_SEMANTIC_SCHEMA_IDENTITY_FIELDS == frozenset(
        {"case_id"}
    )
    assert (
        _DISCOVERED_SEMANTIC_SCHEMA_IDENTITY_FIELDS
        == _SEMANTIC_SCHEMA_IDENTITY_FIELDS
    )


@pytest.mark.parametrize(
    "business_identity_key",
    (
        "customer_case_id",
        "use_case_id",
        "show_case_id",
        "script_owner_id",
        "description",
        "showcase_code",
        "showcaseCode",
        "transcript_uuid",
        "transcriptUuid",
        "description_code",
        "javascript_uuid",
        "staircase_number",
        "showcasecode",
        "transcriptuuid",
        "javascriptuuid",
        "casefold",
        "scripture",
    ),
)
def test_business_named_key_rejects_authenticated_eval_identity_value(
    business_identity_key: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_identity:{business_identity_key}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("authenticated Eval identity reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "identity_kind",
    ("other-case", "other-script"),
)
def test_other_authenticated_bundle_identity_fails_completeness(
    identity_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            "nested_argument_authenticated_bundle_identity:"
            f"{identity_kind}"
        ),
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError(
            "other authenticated bundle identity reached grading"
        )

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "identity_kind",
    ("case", "script", "nested-case", "subclass-case"),
)
def test_enum_wrapped_authenticated_identity_fails_completeness(
    identity_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_enum_identity:{identity_kind}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("Enum-wrapped Eval identity reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_cyclic_enum_value_fails_completeness_without_error_leak() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation="nested_argument_enum_identity:cycle",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("cyclic Enum value reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "identity_kind",
    ("wrapped-semantic", "wrapped-bundle"),
)
def test_enum_wrapped_mapping_fails_completeness(
    identity_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_enum_identity:{identity_kind}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("Enum-wrapped Mapping reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "key_kind",
    ("plain-semantic", "nested-semantic", "subclass-semantic"),
)
def test_enum_semantic_mapping_key_fails_completeness(
    key_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_enum_key:{key_kind}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("Enum semantic Mapping key reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "key_kind",
    (
        "ordinary-business",
        "ordinary-lexical",
        "ordinary-subclass",
    ),
)
def test_ordinary_enum_mapping_key_fails_completeness(
    key_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_enum_key:{key_kind}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("noncanonical Enum Mapping key reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_cyclic_enum_mapping_key_fails_completeness_without_error() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation="nested_argument_enum_key:cycle",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("cyclic Enum Mapping key reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "identity_kind",
    ("selected-case", "other-script"),
)
def test_bytes_wrapped_authenticated_identity_fails_completeness(
    identity_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_bytes_identity:{identity_kind}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("bytes-wrapped Eval identity reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "container_kind",
    (
        "dict",
        "list",
        "tuple",
        "set",
        "frozenset",
        "flip-mapping",
        "flip-list",
        "flip-tuple",
        "flip-set",
    ),
)
def test_noncanonical_json_container_fails_without_iteration(
    container_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            "nested_argument_noncanonical_container:"
            f"{container_kind}"
        ),
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("noncanonical container reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}
    if container_kind.startswith("flip-"):
        assert getattr(sut.injected_container, "iterations") == 0


def test_duplicate_raw_frozen_json_key_fails_completeness() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation="nested_argument_duplicate_frozen_identity",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("duplicate Frozen JSON key reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    arguments = sut.injected_arguments
    assert type(arguments) is FrozenJsonDict
    assert arguments["metadata"] == "ordinary-value"
    assert tuple(tuple.__iter__(arguments))[-1] == (
        "metadata",
        "E2E01-04-A",
    )
    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize("enum_location", ("key", "value"))
def test_behaviorful_unknown_enum_is_rejected_without_value_read(
    enum_location: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_flip_enum:{enum_location}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("behaviorful unknown Enum reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert FLIP_ENUM_VALUE_READ_COUNTER.reads == 0
    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "string_location",
    ("key", "ordinary-value", "identity-value"),
)
def test_direct_str_subclass_is_rejected_without_method_read(
    string_location: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"nested_argument_str_subclass:{string_location}",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("direct str subclass reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert FLIP_STRING_METHOD_READ_COUNTER.reads == 0
    assert grader_called is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_repeated_nonempty_immutable_tuple_is_rejected() -> None:
    shared: tuple[object, ...] = ("ordinary-value",)
    root = (shared, shared)
    traversal = _PayloadTraversalState()

    assert not _payload_tree_is_closed(
        root,
        forbidden_identity_values=frozenset(),
        traversal=traversal,
    )
    assert set(traversal.validation_counts.values()) == {1}
    assert traversal.active_ids == set()


def test_unique_depth_and_edge_budgets_fail_closed() -> None:
    deep: object = "ordinary-value"
    for _ in range(_MAX_PAYLOAD_DEPTH + 1):
        deep = tuple.__new__(FrozenJsonList, (deep,))
    depth_traversal = _PayloadTraversalState()

    assert not _payload_tree_is_closed(
        deep,
        forbidden_identity_values=frozenset(),
        traversal=depth_traversal,
    )
    assert depth_traversal.visited_edges == _MAX_PAYLOAD_DEPTH
    assert depth_traversal.active_ids == set()

    wide = tuple.__new__(
        FrozenJsonList,
        ("ordinary-value",) * (_MAX_PAYLOAD_EDGES + 1),
    )
    edge_traversal = _PayloadTraversalState()

    assert not _payload_tree_is_closed(
        wide,
        forbidden_identity_values=frozenset(),
        traversal=edge_traversal,
    )
    assert edge_traversal.visited_edges == _MAX_PAYLOAD_EDGES
    assert edge_traversal.active_ids == set()


def test_exact_tree_comparison_rejects_equal_cross_enum_values() -> None:
    assert AgentOutcome.COMPLETED == TaskStatus.COMPLETED
    assert not _same_exact_value_tree(
        AgentOutcome.COMPLETED,
        TaskStatus.COMPLETED,
    )


def test_canonical_result_enum_types_are_import_time_closed() -> None:
    assert {
        enum_type.__name__
        for enum_type in _CANONICAL_RESULT_ENUM_TYPES
    } == {
        "AgentOutcome",
        "AgentRunStatus",
        "CandidateRejectionReasonCode",
        "CandidateValidationDecision",
        "GateDecisionValue",
        "GateReasonCode",
        "InputAuthority",
        "InputSourceKind",
        "InputValidationStatus",
        "MessageDirection",
        "ObservationVisibility",
        "OrderStatus",
        "ReferenceSourceKindV2",
        "StopReason",
        "TaskDeltaOperation",
        "TaskStatus",
        "ToolCallStatus",
        "ToolEffect",
        "ToolResultOutcome",
        "ToolTimeoutPhase",
        "TraceEventType",
        "UncertaintyReasonCodeV2",
    }


def test_nested_business_identity_key_is_allowed_by_result_boundary() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation="allowed_business_identity_keys",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.PASS


@pytest.mark.parametrize(
    "replacement",
    (
        "NONE",
        ToolResultOutcome.BUSINESS_FAILURE.value,
        ToolResultOutcome.SYSTEM_FAILURE.value,
        ToolResultOutcome.TIMEOUT.value,
        ToolResultOutcome.INTERRUPTED.value,
        ToolResultOutcome.RESULT_UNKNOWN.value,
    ),
)
def test_success_normalized_outcome_must_match_authoritative_attempt(
    replacement: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"normalized_outcome:{replacement}",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    trace_grader = next(
        grader
        for grader in outcome.results[0].grader_results
        if grader.grader_name == "TraceCompletenessGrader"
    )
    assert trace_grader.status is EvalGraderStatus.FAIL
    assert trace_grader.reason_code is (
        EvalGraderReasonCode.ASSERTION_FAILED
    )
    assert CriticalFailureCode.CF_12 in (
        outcome.results[0].critical_failures
    )


@pytest.mark.parametrize(
    "replacement",
    (
        "NONE",
        ToolResultOutcome.SUCCESS.value,
        ToolResultOutcome.SYSTEM_FAILURE.value,
        ToolResultOutcome.TIMEOUT.value,
        ToolResultOutcome.INTERRUPTED.value,
        ToolResultOutcome.RESULT_UNKNOWN.value,
    ),
)
def test_business_failure_normalized_outcome_rejects_every_substitute(
    replacement: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"normalized_outcome:{replacement}",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (
                EXECUTION_REF_1,
                SCRIPT_EXECUTION_REF_1,
                EXECUTION_REF_2,
                SCRIPT_EXECUTION_REF_2,
            )
        ),
    )

    outcome = _run(
        harness,
        case_ids=("E2E01-04-A", "E2E01-04-B"),
    )

    assert outcome.execution_failures == ()
    assert len(outcome.results) == 2
    assert {result.status for result in outcome.results} == {
        EvalResultStatus.FAIL
    }
    for result in outcome.results:
        trace_grader = next(
            grader
            for grader in result.grader_results
            if grader.grader_name == "TraceCompletenessGrader"
        )
        assert trace_grader.status is EvalGraderStatus.FAIL
        assert trace_grader.reason_code is (
            EvalGraderReasonCode.ASSERTION_FAILED
        )


@pytest.mark.parametrize(
    "target_type",
    (
        TraceEventType.REQUEST_UNDERSTANDING_STARTED,
        TraceEventType.RUN_STARTED,
        TraceEventType.TOOL_RESULT_NORMALIZED,
        TraceEventType.RUN_STOPPED,
    ),
)
def test_gate_projection_is_rejected_outside_gate_event(
    target_type: TraceEventType,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"gate_projection:{target_type.value}",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    trace_grader = next(
        grader
        for grader in outcome.results[0].grader_results
        if grader.grader_name == "TraceCompletenessGrader"
    )
    assert trace_grader.status is EvalGraderStatus.FAIL


def test_gate_projection_must_match_authoritative_gate_record() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"gate_projection:"
            f"{TraceEventType.GATE_DECISION_RECORDED.value}"
        ),
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL


@pytest.mark.parametrize(
    "target_type",
    (
        TraceEventType.REQUEST_UNDERSTANDING_STARTED,
        TraceEventType.RUN_STARTED,
        TraceEventType.TOOL_RESULT_NORMALIZED,
    ),
)
def test_run_projection_is_rejected_outside_run_stopped(
    target_type: TraceEventType,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"run_projection:{target_type.value}",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    trace_grader = next(
        grader
        for grader in outcome.results[0].grader_results
        if grader.grader_name == "TraceCompletenessGrader"
    )
    assert trace_grader.status is EvalGraderStatus.FAIL


def test_run_stopped_projection_must_match_authoritative_result() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"run_projection:{TraceEventType.RUN_STOPPED.value}",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL


@pytest.mark.parametrize(
    "target_type",
    (
        TraceEventType.REQUEST_UNDERSTANDING_STARTED,
        TraceEventType.RUN_STARTED,
    ),
)
def test_safe_tool_outcome_is_rejected_before_normalization(
    target_type: TraceEventType,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"safe_outcome_projection:{target_type.value}:"
            f"{ToolResultOutcome.SUCCESS.value}"
        ),
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL


def test_later_matching_safe_tool_outcome_summary_is_allowed() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"safe_outcome_projection:{TraceEventType.RUN_STOPPED.value}:"
            f"{ToolResultOutcome.SUCCESS.value}"
        ),
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.PASS


def test_later_conflicting_safe_tool_outcome_summary_is_rejected() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"safe_outcome_projection:{TraceEventType.RUN_STOPPED.value}:"
            f"{ToolResultOutcome.BUSINESS_FAILURE.value}"
        ),
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL


def test_presentation_failure_keeps_tool_and_agent_outcomes_separate() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"safe_outcome_projection:{TraceEventType.RUN_STOPPED.value}:"
            f"{ToolResultOutcome.SUCCESS.value}"
        ),
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(
        harness,
        case_ids=("E2E01-01+FAULT-PRESENTATION-PROTOCOL",),
        script_ref_by_case={
            "E2E01-01+FAULT-PRESENTATION-PROTOCOL": (
                "script:fault-presentation:invalid-schema"
            )
        },
    )

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.PASS
    assert outcome.results[0].observed_outcome is AgentOutcome.BLOCKED
    assert delegate.last_trace_ref is not None
    final_trace = traces.events_by_ref[delegate.last_trace_ref]
    normalized = next(
        event
        for event in final_trace
        if event.event_type is TraceEventType.TOOL_RESULT_NORMALIZED
    )
    stopped = next(
        event
        for event in final_trace
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    assert normalized.safe_tool_outcome is ToolResultOutcome.SUCCESS
    assert stopped.tool_call_id == normalized.tool_call_id
    assert stopped.safe_tool_outcome is ToolResultOutcome.SUCCESS
    assert stopped.user_outcome is AgentOutcome.BLOCKED
    assert stopped.stop_reason is StopReason.PROVIDER_PROTOCOL_ERROR
    assert sum(
        event.event_type is TraceEventType.TOOL_CALL_SUCCEEDED
        for event in final_trace
    ) == 1
    assert sum(
        event.event_type is TraceEventType.OBSERVATION_RECORDED
        for event in final_trace
    ) == 1


def test_presentation_failure_rejects_conflicting_tool_outcome_summary() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=(
            f"safe_outcome_projection:{TraceEventType.RUN_STOPPED.value}:"
            f"{ToolResultOutcome.BUSINESS_FAILURE.value}"
        ),
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(
        harness,
        case_ids=("E2E01-01+FAULT-PRESENTATION-PROTOCOL",),
        script_ref_by_case={
            "E2E01-01+FAULT-PRESENTATION-PROTOCOL": (
                "script:fault-presentation:invalid-schema"
            )
        },
    )

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    trace_grader = next(
        grader
        for grader in outcome.results[0].grader_results
        if grader.grader_name == "TraceCompletenessGrader"
    )
    assert trace_grader.status is EvalGraderStatus.FAIL


@pytest.mark.parametrize("reference_kind", ("missing", "foreign"))
def test_later_safe_tool_outcome_summary_requires_authoritative_tool_call(
    reference_kind: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ResultBoundaryMutationSut(
        delegate,
        mutation=f"safe_outcome_reference:{reference_kind}",
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=NonceFactorySpy(
            (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL


def test_result_correlation_replay_wins_over_unexhausted_provider() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = ReplayWithoutProviderSut(delegate)
    nonce_factory = NonceFactorySpy(
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_2,
            SCRIPT_EXECUTION_REF_2,
        )
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )

    first = _run(harness, attempt=1)
    replayed = _run(harness, attempt=2)

    assert first.execution_failures == ()
    assert first.results[0].status is EvalResultStatus.PASS
    assert replayed.results == ()
    assert len(replayed.execution_failures) == 1
    assert replayed.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert sut.calls == 2
    assert nonce_factory.calls == [((), {})] * 4


def test_incomplete_exit_clears_correlation_before_later_stale_echo() -> None:
    traces = InMemoryTraceCallbacks()
    delegate = SyntheticSut(traces)
    sut = IncompleteThenStaleRefSut(delegate)
    nonce_factory = NonceFactorySpy(
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_2,
            SCRIPT_EXECUTION_REF_2,
        )
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )

    incomplete = _run(harness, attempt=1)
    stale_echo = _run(harness, attempt=2)

    assert incomplete.results == ()
    assert incomplete.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert stale_echo.results == ()
    assert stale_echo.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert nonce_factory.calls == [((), {})] * 4


def test_nonce_factory_values_are_used_verbatim_and_unique_across_attempts() -> None:
    probe = BoundaryProbeSut()
    nonce_values = (
        EXECUTION_REF_1,
        SCRIPT_EXECUTION_REF_1,
        EXECUTION_REF_2,
        SCRIPT_EXECUTION_REF_2,
    )
    nonce_factory = NonceFactorySpy(nonce_values)
    harness, _sut, _traces, _port = _harness(
        sut=probe,
        nonce_factory=nonce_factory,
    )

    first = _run(harness, attempt=1)
    second = _run(harness, attempt=2)

    assert all(
        item.failure_phase is EvalExecutionFailurePhase.RESULT_COMPLETENESS
        for outcome in (first, second)
        for item in outcome.execution_failures
    )
    assert nonce_factory.calls == [((), {})] * 4
    assert len(probe.received_calls) == 2
    assert tuple(
        call["execution_input"].execution_ref
        for call in probe.received_calls
    ) == (EXECUTION_REF_1, EXECUTION_REF_2)
    assert tuple(
        call["scripted_provider"].script_execution_ref
        for call in probe.received_calls
    ) == (SCRIPT_EXECUTION_REF_1, SCRIPT_EXECUTION_REF_2)
    assert len(set(nonce_values)) == len(nonce_values)


def test_nonce_factory_values_are_distinct_across_selected_cases() -> None:
    probe = BoundaryProbeSut()
    nonce_values = (
        EXECUTION_REF_1,
        SCRIPT_EXECUTION_REF_1,
        EXECUTION_REF_2,
        SCRIPT_EXECUTION_REF_2,
    )
    nonce_factory = NonceFactorySpy(nonce_values)
    harness, _sut, _traces, _port = _harness(
        sut=probe,
        nonce_factory=nonce_factory,
    )

    outcome = _run(
        harness,
        case_ids=("E2E01-04-A", "E2E01-04-B"),
    )

    assert outcome.results == ()
    assert all(
        failure.failure_phase is EvalExecutionFailurePhase.RESULT_COMPLETENESS
        for failure in outcome.execution_failures
    )
    assert nonce_factory.calls == [((), {})] * 4
    assert len(probe.received_calls) == 2
    assert tuple(
        call["execution_input"].execution_ref
        for call in probe.received_calls
    ) == (EXECUTION_REF_1, EXECUTION_REF_2)
    assert tuple(
        call["scripted_provider"].script_execution_ref
        for call in probe.received_calls
    ) == (SCRIPT_EXECUTION_REF_1, SCRIPT_EXECUTION_REF_2)


@pytest.mark.parametrize(
    "nonce_values",
    [
        (EXECUTION_REF_1, EXECUTION_REF_1),
        (
            uuid5(NAMESPACE_URL, "E2E01-01"),
            SCRIPT_EXECUTION_REF_1,
        ),
    ],
    ids=("execution-provider-collision", "deterministic-version-five-ref"),
)
def test_nonce_collision_or_non_uuid4_fails_result_completeness(
    nonce_values: tuple[UUID, UUID],
) -> None:
    probe = BoundaryProbeSut()
    nonce_factory = NonceFactorySpy(nonce_values)
    harness, _sut, _traces, port = _harness(
        sut=probe,
        nonce_factory=nonce_factory,
    )

    outcome = _run(harness)

    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert probe.received_calls == []
    assert port.results == {}
    assert all(args == () and kwargs == {} for args, kwargs in nonce_factory.calls)


def test_nonce_internal_state_is_closed_before_version_read() -> None:
    bad_nonce = UUID(str(EXECUTION_REF_1))
    object.__setattr__(
        bad_nonce,
        "int",
        EvilInt(bad_nonce.int),
    )
    BOUNDARY_METHOD_READ_COUNTER.reads = 0
    probe = BoundaryProbeSut()
    harness, _sut, _traces, port = _harness(
        sut=probe,
        nonce_factory=NonceFactorySpy(
            (bad_nonce, SCRIPT_EXECUTION_REF_1)
        ),
    )

    outcome = _run(harness)

    assert BOUNDARY_METHOD_READ_COUNTER.reads == 0
    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert probe.received_calls == []
    assert port.results == {}


def test_sut_nonce_copies_cannot_corrupt_private_correlation_state() -> None:
    class InputMutatingSut:
        def __init__(self) -> None:
            self.calls = 0

        async def execute_case(self, **kwargs: object) -> None:
            self.calls += 1
            execution_input = cast(
                EvalCaseExecutionInput,
                kwargs["execution_input"],
            )
            provider = cast(
                ScriptedModelProviderV2,
                kwargs["scripted_provider"],
            )
            object.__setattr__(
                execution_input.execution_ref,
                "int",
                1,
            )
            object.__setattr__(
                provider.script_execution_ref,
                "int",
                2,
            )
            return None

    nonce_values = (
        EXECUTION_REF_1,
        SCRIPT_EXECUTION_REF_1,
        EXECUTION_REF_2,
        SCRIPT_EXECUTION_REF_2,
    )
    sut = InputMutatingSut()
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        nonce_factory=NonceFactorySpy(nonce_values),
    )

    first = _run(harness, attempt=1)
    second = _run(harness, attempt=2)

    assert first.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert second.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert sut.calls == 2
    assert len(harness._issued_nonces) == 4
    assert all(value in harness._issued_nonces for value in nonce_values)
    assert harness._pending_case_by_execution_ref == {}
    assert harness._retired_execution_refs == {
        EXECUTION_REF_1,
        EXECUTION_REF_2,
    }


@pytest.mark.parametrize(
    "nonce_values",
    [
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_2,
        ),
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_2,
            SCRIPT_EXECUTION_REF_1,
        ),
    ],
    ids=("execution-ref-reuse", "script-execution-ref-reuse"),
)
def test_nonce_reuse_across_attempts_fails_before_second_sut_call(
    nonce_values: tuple[UUID, UUID, UUID, UUID],
) -> None:
    probe = BoundaryProbeSut()
    nonce_factory = NonceFactorySpy(nonce_values)
    harness, _sut, _traces, _port = _harness(
        sut=probe,
        nonce_factory=nonce_factory,
    )

    first = _run(harness, attempt=1)
    second = _run(harness, attempt=2)

    assert first.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert second.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert len(probe.received_calls) == 1
    assert nonce_factory.calls == [((), {})] * 4


def test_actual_mismatch_reaches_graders_and_persists_fail() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        fault="request_candidate_mismatch",
    )
    nonce_factory = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    harness, *_ = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )

    outcome = _run(harness)

    assert nonce_factory.calls == [((), {}), ((), {})]
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    request_grader = next(
        item
        for item in outcome.results[0].grader_results
        if item.grader_name == "RequestUnderstandingGrader"
    )
    assert request_grader.status is EvalGraderStatus.FAIL
    assert request_grader.reason_code is EvalGraderReasonCode.ASSERTION_FAILED


def test_complete_case_appends_graded_reloads_then_persists_pass() -> None:
    timeline: list[str] = []
    traces = InMemoryTraceCallbacks(timeline)
    port = InMemoryResultPort(timeline)

    def recording_grader(
        configured: Sequence[str],
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        timeline.append(f"grade:{','.join(configured)}")
        return grade_evidence(configured, evidence, expectations)

    harness, sut, traces, port = _harness(
        traces=traces,
        port=port,
        grader_runner=recording_grader,
    )
    outcome = _run(harness)

    assert outcome.command_passed is True
    assert outcome.execution_failures == ()
    assert len(outcome.results) == 1
    assert isinstance(sut, SyntheticSut)
    assert sut.last_trace_ref is not None
    result = outcome.results[0]
    assert result.status is EvalResultStatus.PASS
    assert result.observed_outcome is AgentOutcome.COMPLETED
    assert result.trace_ref == sut.last_trace_ref
    assert result.grader_results
    assert result.critical_failures == ()
    assert result.usage_summary is None
    assert result.latency_summary is None
    assert traces.events == ["trace_append", "trace_reload"]
    assert port.events == ["result_append"]
    assert timeline[0].startswith("grade:SchemaGrader")
    assert timeline[-4:] == [
        "trace_append",
        "trace_reload",
        "grade:TraceCompletenessGrader",
        "result_append",
    ]
    final_trace = traces.events_by_ref[sut.last_trace_ref]
    assert [event.event_type for event in final_trace].count(
        TraceEventType.EVAL_CASE_GRADED
    ) == 1
    assert all(
        event.case_id is None
        for event in final_trace
        if event.event_type is not TraceEventType.EVAL_CASE_GRADED
    )
    assert tuple(
        event.case_id
        for event in final_trace
        if event.event_type is TraceEventType.EVAL_CASE_GRADED
    ) == ("E2E01-01",)


def test_missing_observation_provenance_fails_canonical_harness_grading() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        fault="missing_observation_manifest_ref",
    )
    harness, *_ = _harness(sut=sut, traces=traces)

    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.status is EvalResultStatus.FAIL
    by_name = {item.grader_name: item for item in result.grader_results}
    expected_reasons = {
        "ObservationGrader": EvalGraderReasonCode.MISSING_RECORD,
        "PersistenceGrader": EvalGraderReasonCode.MISSING_RECORD,
        "TraceCompletenessGrader": EvalGraderReasonCode.ASSERTION_FAILED,
    }
    for grader_name, reason_code in expected_reasons.items():
        assert by_name[grader_name].status is EvalGraderStatus.FAIL
        assert by_name[grader_name].reason_code is reason_code


def test_raw_observation_visibility_fails_result_completeness() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        fault="raw_observation_visibility",
    )
    grader_called = False

    def forbidden_grader(*args: object) -> GradingOutcome:
        nonlocal grader_called
        grader_called = True
        raise AssertionError("noncanonical Observation reached grading")

    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        grader_runner=forbidden_grader,
    )

    outcome = _run(harness)

    assert grader_called is False
    assert outcome.command_passed is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_supersedes_provenance_passes_canonical_harness_grading() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        fault="observation_supersedes",
    )
    harness, *_ = _harness(sut=sut, traces=traces)

    outcome = _run(harness)

    assert outcome.command_passed is True
    assert outcome.execution_failures == ()
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.status is EvalResultStatus.PASS
    assert all(item.status is EvalGraderStatus.PASS for item in result.grader_results)


def test_authenticated_expectations_pin_message_and_toolset_projection() -> None:
    case = ARTIFACTS.case_by_id("E2E01-01")
    script_ref = tuple(case.input["model_script_refs"])[0]
    script = ARTIFACTS.script_by_ref(script_ref)

    expectations = build_authenticated_case_expectations(
        artifacts=ARTIFACTS,
        case=case,
        script=script,
    )

    assert (
        expectations.expected_message_content == (case.input["messages"][0]["content"])
    )
    assert expectations.expected_model_visible_toolset_hash == (
        compute_model_visible_toolset_hash((get_order_tool_spec(),))
    )


def test_authenticated_case_script_selects_closed_trace_variant() -> None:
    selected: dict[str, str] = {}
    for case in ARTIFACTS.cases:
        for script_ref in tuple(case.input["model_script_refs"]):
            script = ARTIFACTS.script_by_ref(script_ref)
            expectations = build_authenticated_case_expectations(
                artifacts=ARTIFACTS,
                case=case,
                script=script,
            )
            selected[script_ref] = expectations.trace_variant

    assert selected == EXPECTED_TRACE_VARIANT_BY_SCRIPT_REF
    assert len(selected) == 16
    assert len(set(selected.values())) == 9


def test_missing_typed_record_cannot_be_masked_by_true_self_assertions() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        evidence_overrides={"input_bindings": ()},
    )
    harness, _sut, _traces, _port = _harness(sut=sut, traces=traces)
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    assert CriticalFailureCode.CF_14 in outcome.results[0].critical_failures


@pytest.mark.parametrize(
    "field_name",
    (
        "conversation_task_links",
        "run_task_links",
        "tool_attempts",
    ),
)
def test_missing_authoritative_graph_record_forces_case_fail(
    field_name: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        evidence_overrides={field_name: ()},
    )
    harness, _sut, _traces, _port = _harness(sut=sut, traces=traces)
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    assert CriticalFailureCode.CF_12 in outcome.results[0].critical_failures


@pytest.mark.parametrize(
    ("event_type", "update"),
    [
        (
            TraceEventType.MESSAGE_ACCEPTED,
            {"message_ref": UUID(int=993)},
        ),
        (
            TraceEventType.CONTEXT_MANIFEST_RECORDED,
            {"model_visible_toolset_hash": f"sha256:{'b' * 64}"},
        ),
        (
            TraceEventType.TASK_DELTA_ACCEPTED,
            {"accepted_delta_ref": UUID(int=994)},
        ),
    ],
)
def test_physical_trace_reload_rejects_unresolved_authoritative_refs(
    event_type: TraceEventType,
    update: dict[str, object],
) -> None:
    class TamperingTraceCallbacks(InMemoryTraceCallbacks):
        async def reload_trace(
            self,
            trace_ref: UUID,
        ) -> tuple[TraceEvent, ...]:
            events = await super().reload_trace(trace_ref)
            return tuple(
                event.model_copy(update=update)
                if event.event_type is event_type
                else event
                for event in events
            )

    traces = TamperingTraceCallbacks()
    harness, *_ = _harness(traces=traces)
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    assert CriticalFailureCode.CF_12 in outcome.results[0].critical_failures


@pytest.mark.parametrize(
    "tamper_kind",
    ("tuple-subclass", "behaviorful-case-id", "runtime-case-id"),
)
def test_reload_boundary_closes_shape_before_reads_or_final_grading(
    tamper_kind: str,
) -> None:
    class BoundaryTamperingTraceCallbacks(InMemoryTraceCallbacks):
        async def reload_trace(
            self,
            trace_ref: UUID,
        ) -> tuple[TraceEvent, ...]:
            events = await super().reload_trace(trace_ref)
            if tamper_kind == "tuple-subclass":
                return cast(
                    tuple[TraceEvent, ...],
                    ReloadFlipTuple(events),
                )
            replacement_case_id: object = (
                EvilEquality()
                if tamper_kind == "behaviorful-case-id"
                else "E2E01-01"
            )
            return tuple(
                event.model_copy(
                    update={"case_id": replacement_case_id}
                )
                if event.event_type is TraceEventType.MESSAGE_ACCEPTED
                else event
                for event in events
            )

    BOUNDARY_METHOD_READ_COUNTER.reads = 0
    final_grader_calls = 0

    def recording_grader(
        configured: Sequence[str],
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        nonlocal final_grader_calls
        if "TraceCompletenessGrader" in configured:
            final_grader_calls += 1
        return grade_evidence(configured, evidence, expectations)

    traces = BoundaryTamperingTraceCallbacks()
    harness, _sut, _traces, port = _harness(
        traces=traces,
        grader_runner=recording_grader,
    )

    outcome = _run(harness)

    assert BOUNDARY_METHOD_READ_COUNTER.reads == 0
    assert final_grader_calls == 0
    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize("seam", ("append-event", "reload-ref"))
def test_trace_callback_inputs_do_not_alias_private_identity(
    seam: str,
) -> None:
    class IdentityMutatingTraceCallbacks(InMemoryTraceCallbacks):
        async def append_eval_case_graded(
            self,
            event: TraceEvent,
        ) -> None:
            await super().append_eval_case_graded(event)
            if seam == "append-event":
                object.__setattr__(
                    event.trace_event_id,
                    "int",
                    UNKNOWN_EXECUTION_REF.int,
                )

        async def reload_trace(
            self,
            trace_ref: UUID,
        ) -> tuple[TraceEvent, ...]:
            events = await super().reload_trace(trace_ref)
            if seam == "reload-ref":
                object.__setattr__(
                    trace_ref,
                    "int",
                    UNKNOWN_EXECUTION_REF.int,
                )
            return events

    traces = IdentityMutatingTraceCallbacks()
    harness, _sut, _traces, port = _harness(traces=traces)

    outcome = _run(harness)

    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


@pytest.mark.parametrize(
    "mutation_kind",
    ("uuid-int", "uuid-is-safe", "enum-sidecar"),
)
def test_post_await_raw_mutation_cannot_reach_final_grading(
    mutation_kind: str,
) -> None:
    class RetainingMutationSut:
        def __init__(self, delegate: SyntheticSut) -> None:
            self.delegate = delegate
            self.release: asyncio.Event | None = None
            self.task: asyncio.Task[None] | None = None

        async def execute_case(
            self,
            **kwargs: object,
        ) -> EvalCaseSutResult | None:
            result = await self.delegate.execute_case(**kwargs)
            assert type(result) is EvalCaseSutResult
            self.release = asyncio.Event()

            async def mutate_after_release() -> None:
                assert self.release is not None
                await self.release.wait()
                if mutation_kind == "enum-sidecar":
                    object.__setattr__(
                        AgentOutcome.COMPLETED,
                        "hidden_case_id",
                        "E2E01-01",
                    )
                    return
                raw_trace_ref = result.evidence.trace_ref
                if mutation_kind == "uuid-int":
                    object.__setattr__(
                        raw_trace_ref,
                        "int",
                        UNKNOWN_EXECUTION_REF.int,
                    )
                else:
                    object.__setattr__(
                        raw_trace_ref,
                        "is_safe",
                        "E2E01-01",
                    )

            self.task = asyncio.create_task(
                mutate_after_release()
            )
            return result

    class YieldingTraceCallbacks(InMemoryTraceCallbacks):
        def __init__(self, sut: RetainingMutationSut) -> None:
            super().__init__()
            self.sut = sut

        async def append_eval_case_graded(
            self,
            event: TraceEvent,
        ) -> None:
            await super().append_eval_case_graded(event)
            assert self.sut.release is not None
            assert self.sut.task is not None
            self.sut.release.set()
            await asyncio.sleep(0)
            await self.sut.task

    member = AgentOutcome.COMPLETED
    member_storage = object.__getattribute__(member, "__dict__")
    original_member_items = tuple(
        (key, dict.__getitem__(member_storage, key))
        for key in dict.__iter__(member_storage)
    )
    delegate_traces = InMemoryTraceCallbacks()
    retaining_sut = RetainingMutationSut(
        SyntheticSut(delegate_traces)
    )
    traces = YieldingTraceCallbacks(retaining_sut)
    retaining_sut.delegate.traces = traces
    mutated_grader_reads = 0
    final_grader_calls = 0

    def recording_grader(
        configured: Sequence[str],
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        nonlocal mutated_grader_reads, final_grader_calls
        if "TraceCompletenessGrader" in configured:
            final_grader_calls += 1
        if (
            type(evidence.trace_ref.int) is not int
            or type(evidence.trace_ref.is_safe) is not SafeUUID
            or not _canonical_enum_storage_is_pristine(
                AgentOutcome.COMPLETED,
                original_member_items,
            )
        ):
            mutated_grader_reads += 1
        return grade_evidence(configured, evidence, expectations)

    harness, _sut, _traces, port = _harness(
        sut=retaining_sut,
        traces=traces,
        grader_runner=recording_grader,
    )

    try:
        outcome = _run(harness)
    finally:
        member_storage = object.__getattribute__(
            member,
            "__dict__",
        )
        dict.clear(member_storage)
        for key, stored_value in original_member_items:
            dict.__setitem__(
                member_storage,
                key,
                stored_value,
            )

    assert mutated_grader_reads == 0
    assert final_grader_calls == 0
    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )
    assert port.results == {}


def test_grading_uses_detached_uuid_and_datetime_values() -> None:
    class ScalarRetainingSut:
        def __init__(self, delegate: SyntheticSut) -> None:
            self.delegate = delegate
            self.raw_trace_ref: UUID | None = None
            self.raw_created_at: datetime | None = None

        async def execute_case(
            self,
            **kwargs: object,
        ) -> EvalCaseSutResult | None:
            result = await self.delegate.execute_case(**kwargs)
            assert type(result) is EvalCaseSutResult
            self.raw_trace_ref = result.evidence.trace_ref
            self.raw_created_at = (
                result.evidence.conversation_records[0].created_at
            )
            return result

    traces = InMemoryTraceCallbacks()
    retaining_sut = ScalarRetainingSut(SyntheticSut(traces))
    detached_reads: list[bool] = []

    def recording_grader(
        configured: Sequence[str],
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        detached_reads.append(
            evidence.trace_ref is not retaining_sut.raw_trace_ref
            and evidence.conversation_records[0].created_at
            is not retaining_sut.raw_created_at
        )
        return grade_evidence(configured, evidence, expectations)

    harness, _sut, _traces, _port = _harness(
        sut=retaining_sut,
        traces=traces,
        grader_runner=recording_grader,
    )

    outcome = _run(harness)

    assert outcome.command_passed is True
    assert detached_reads == [True, True]


@pytest.mark.parametrize(
    ("reported_status", "reported_critical_failures"),
    [
        (EvalResultStatus.FAIL, ()),
        (EvalResultStatus.FAIL, (CriticalFailureCode.CF_05,)),
    ],
)
def test_injected_grader_outcome_must_match_authenticated_derivation(
    reported_status: EvalResultStatus,
    reported_critical_failures: tuple[CriticalFailureCode, ...],
) -> None:
    def inconsistent_grader(
        configured: Sequence[str],
        _evidence: EvalEvidence,
        _expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        return GradingOutcome(
            status=reported_status,
            grader_results=tuple(
                EvalGraderResult(
                    grader_name=name,
                    status=EvalGraderStatus.PASS,
                )
                for name in configured
            ),
            critical_failures=reported_critical_failures,
        )

    harness, *_ = _harness(grader_runner=inconsistent_grader)
    outcome = _run(harness)

    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.GRADING
    )


@pytest.mark.parametrize(
    "mode",
    ("forged_all_pass", "missing_result", "duplicate_result", "altered_result"),
)
def test_injected_grader_runner_cannot_replace_canonical_grading(
    mode: str,
) -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        evidence_overrides=(
            {"input_bindings": ()} if mode == "forged_all_pass" else None
        ),
    )

    def untrusted_grader(
        configured: Sequence[str],
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        passing = tuple(
            EvalGraderResult(
                grader_name=name,
                status=EvalGraderStatus.PASS,
            )
            for name in configured
        )
        if mode == "forged_all_pass":
            return GradingOutcome(
                status=EvalResultStatus.PASS,
                grader_results=passing,
                critical_failures=(),
            )
        if mode == "missing_result":
            return GradingOutcome(
                status=EvalResultStatus.PASS,
                grader_results=passing[:-1],
                critical_failures=(),
            )
        if mode == "duplicate_result":
            return GradingOutcome(
                status=EvalResultStatus.PASS,
                grader_results=(*passing, passing[-1]),
                critical_failures=(),
            )
        canonical = grade_evidence(configured, evidence, expectations)
        altered = canonical.grader_results[0].model_copy(
            update={
                "status": EvalGraderStatus.FAIL,
                "reason_code": EvalGraderReasonCode.ASSERTION_FAILED,
            }
        )
        return derive_grading_outcome(
            (altered, *canonical.grader_results[1:]),
            expectations,
        )

    harness, *_ = _harness(
        sut=sut,
        traces=traces,
        grader_runner=untrusted_grader,
    )
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.GRADING
    )


def test_injected_runner_raw_string_enums_from_model_construct_fail_closed() -> None:
    def raw_enum_grader(
        configured: Sequence[str],
        _evidence: EvalEvidence,
        _expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        return GradingOutcome.model_construct(
            status="PASS",
            grader_results=tuple(
                EvalGraderResult.model_construct(
                    grader_name=name,
                    status="PASS",
                    reason_code=None,
                )
                for name in configured
            ),
            critical_failures=(),
        )

    harness, *_ = _harness(grader_runner=raw_enum_grader)
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.results == ()
    assert len(outcome.execution_failures) == 1
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.GRADING
    )


@pytest.mark.parametrize("mutation_phase", ("initial", "final"))
def test_injected_grader_mutates_only_discarded_input_copies(
    mutation_phase: str,
) -> None:
    seen_evidence: list[EvalEvidence] = []
    seen_expectations: list[EvalCaseExpectations] = []

    def mutating_grader(
        configured: Sequence[str],
        evidence: EvalEvidence,
        expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        outcome = grade_evidence(
            configured,
            evidence,
            expectations,
        )
        is_final = configured == ("TraceCompletenessGrader",)
        if is_final == (mutation_phase == "final"):
            object.__setattr__(
                evidence,
                "observed_outcome",
                AgentOutcome.BLOCKED,
            )
            object.__setattr__(
                expectations,
                "expected_outcome",
                AgentOutcome.BLOCKED,
            )
        seen_evidence.append(evidence)
        seen_expectations.append(expectations)
        return outcome

    harness, _sut, _traces, port = _harness(
        grader_runner=mutating_grader,
    )

    outcome = _run(harness)

    assert outcome.command_passed is True
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.PASS
    assert outcome.results[0].observed_outcome is AgentOutcome.COMPLETED
    assert port.results[
        (EVAL_RUN_ID, "E2E01-01", "offline_gate", 1)
    ].observed_outcome is AgentOutcome.COMPLETED
    assert len(seen_evidence) == 2
    assert seen_evidence[0] is not seen_evidence[1]
    assert seen_expectations[0] is not seen_expectations[1]


def test_physical_trace_reload_rejects_tampered_task_graph_refs() -> None:
    class TamperingTraceCallbacks(InMemoryTraceCallbacks):
        async def reload_trace(
            self,
            trace_ref: UUID,
        ) -> tuple[TraceEvent, ...]:
            events = await super().reload_trace(trace_ref)
            return tuple(
                event.model_copy(
                    update={
                        "task_id": UUID(int=991),
                        "request_unit_id": UUID(int=992),
                    }
                )
                if event.event_type is TraceEventType.TASK_STATE_CHANGED
                else event
                for event in events
            )

    traces = TamperingTraceCallbacks()
    harness, *_ = _harness(traces=traces)
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    assert CriticalFailureCode.CF_12 in outcome.results[0].critical_failures


@pytest.mark.parametrize(
    ("mode", "phase", "code"),
    [
        (
            "harness",
            EvalExecutionFailurePhase.HARNESS_SETUP,
            EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED,
        ),
        (
            "case",
            EvalExecutionFailurePhase.CASE_SETUP,
            EvalExecutionSafeErrorCode.CASE_SETUP_FAILED,
        ),
        (
            "sut",
            EvalExecutionFailurePhase.SYSTEM_UNDER_TEST,
            EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED,
        ),
        (
            "grading",
            EvalExecutionFailurePhase.GRADING,
            EvalExecutionSafeErrorCode.GRADING_FAILED,
        ),
        (
            "trace_append",
            EvalExecutionFailurePhase.TRACE_PERSISTENCE,
            EvalExecutionSafeErrorCode.TRACE_PERSISTENCE_FAILED,
        ),
        (
            "trace_reload",
            EvalExecutionFailurePhase.TRACE_PERSISTENCE,
            EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        ),
        (
            "missing",
            EvalExecutionFailurePhase.RESULT_COMPLETENESS,
            EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED,
        ),
        (
            "completeness",
            EvalExecutionFailurePhase.RESULT_COMPLETENESS,
            EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED,
        ),
        (
            "result",
            EvalExecutionFailurePhase.RESULT_PERSISTENCE,
            EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED,
        ),
    ],
)
def test_execution_faults_write_safe_failure_not_fabricated_case_fail(
    mode: str,
    phase: EvalExecutionFailurePhase,
    code: EvalExecutionSafeErrorCode,
) -> None:
    traces = InMemoryTraceCallbacks()
    port = InMemoryResultPort()
    sut = SyntheticSut(
        traces,
        fault=mode if mode in {"sut", "missing"} else None,
    )
    if mode == "trace_append":
        traces.fail_append = True
    elif mode == "trace_reload":
        traces.fail_reload = True
    elif mode == "completeness":
        traces.drop_append = True
    elif mode == "result":
        port.fail_result_append = True

    def grading_fault(
        _configured: Sequence[str],
        _evidence: EvalEvidence,
        _expectations: EvalCaseExpectations,
    ) -> GradingOutcome:
        raise RuntimeError("raw-grader-secret")

    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        port=port,
        grader_runner=grading_fault if mode == "grading" else None,
    )
    if mode == "harness":
        outcome = _run(harness, lane="unknown_lane")
    elif mode == "case":
        outcome = _run(
            harness,
            script_ref_by_case={"E2E01-01": "script:missing"},
        )
    else:
        outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.results == ()
    assert len(port.results) == 0
    assert len(outcome.execution_failures) == 1
    failure = outcome.execution_failures[0]
    assert failure.failure_phase is phase
    assert failure.safe_error_code is code
    serialized = failure.model_dump_json()
    for secret in ("raw-", "customer-A", "O-1001"):
        assert secret not in serialized


def test_failure_store_unavailable_raises_bounded_command_error() -> None:
    traces = InMemoryTraceCallbacks()
    port = InMemoryResultPort()
    port.fail_failure_append = True
    sut = SyntheticSut(traces, fault="sut")
    harness, *_ = _harness(sut=sut, traces=traces, port=port)

    with pytest.raises(EvalHarnessCommandError) as caught:
        _run(harness)
    assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "clock_kind",
    ("raises", "custom-tz", "naive", "non-utc"),
)
def test_invalid_clock_value_raises_only_bounded_command_error(
    clock_kind: str,
) -> None:
    def invalid_clock() -> datetime:
        if clock_kind == "raises":
            raise RuntimeError("raw-clock-secret")
        if clock_kind == "custom-tz":
            return NOW.replace(tzinfo=EvilTz())
        if clock_kind == "naive":
            return NOW.replace(tzinfo=None)
        return NOW.astimezone(
            timezone(timedelta(hours=1))
        )

    TIMEZONE_METHOD_READ_COUNTER.reads = 0
    traces = InMemoryTraceCallbacks()
    harness, *_ = _harness(
        sut=SyntheticSut(traces, fault="sut"),
        traces=traces,
        clock=invalid_clock,
    )

    with pytest.raises(EvalHarnessCommandError) as caught:
        _run(harness)

    assert TIMEZONE_METHOD_READ_COUNTER.reads == 0
    assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("clock_kind", ("raises", "naive"))
def test_invalid_clock_restores_canonical_singletons_without_persistence(
    clock_kind: str,
) -> None:
    member = AgentOutcome.COMPLETED
    member_storage = object.__getattribute__(member, "__dict__")
    original_items = tuple(
        (key, dict.__getitem__(member_storage, key))
        for key in dict.__iter__(member_storage)
    )

    def invalid_clock() -> datetime:
        object.__setattr__(
            member,
            "hidden_case_id",
            "E2E01-01",
        )
        if clock_kind == "raises":
            raise RuntimeError("raw-clock-secret")
        return NOW.replace(tzinfo=None)

    traces = InMemoryTraceCallbacks()
    port = InMemoryResultPort()
    harness, *_ = _harness(
        sut=SyntheticSut(traces, fault="sut"),
        traces=traces,
        port=port,
        clock=invalid_clock,
    )

    try:
        with pytest.raises(EvalHarnessCommandError) as caught:
            _run(harness)
        restored_by_harness = _canonical_enum_storage_is_pristine(
            member,
            original_items,
        )
    finally:
        member_storage = object.__getattribute__(
            member,
            "__dict__",
        )
        dict.clear(member_storage)
        for key, stored_value in original_items:
            dict.__setitem__(
                member_storage,
                key,
                stored_value,
            )

    assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert restored_by_harness is True
    assert harness._persisted_stage_by_replay_key == {}
    assert port.results == {}
    assert port.failures == []
    assert port.events == []


def test_valid_clock_drift_on_failure_phase_is_restored_before_record() -> None:
    member = EvalExecutionFailurePhase.SYSTEM_UNDER_TEST
    member_storage = object.__getattribute__(member, "__dict__")
    original_items = tuple(
        (key, dict.__getitem__(member_storage, key))
        for key in dict.__iter__(member_storage)
    )

    def drifting_clock() -> datetime:
        object.__setattr__(
            member,
            "hidden_case_id",
            "E2E01-01",
        )
        return NOW

    traces = InMemoryTraceCallbacks()
    port = InMemoryResultPort()
    harness, *_ = _harness(
        sut=SyntheticSut(traces, fault="sut"),
        traces=traces,
        port=port,
        clock=drifting_clock,
    )

    try:
        with pytest.raises(EvalHarnessCommandError) as caught:
            _run(harness)
        restored_by_harness = _canonical_enum_storage_is_pristine(
            member,
            original_items,
        )
    finally:
        member_storage = object.__getattribute__(
            member,
            "__dict__",
        )
        dict.clear(member_storage)
        for key, stored_value in original_items:
            dict.__setitem__(
                member_storage,
                key,
                stored_value,
            )

    assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert restored_by_harness is True
    assert harness._persisted_stage_by_replay_key == {}
    assert port.results == {}
    assert port.failures == []
    assert port.events == []


def test_valid_clock_and_failure_port_receive_independent_copies() -> None:
    clock_value = NOW + timedelta(seconds=2)
    traces = InMemoryTraceCallbacks()
    harness, _sut, _traces, port = _harness(
        sut=SyntheticSut(traces, fault="sut"),
        traces=traces,
        clock=lambda: clock_value,
    )

    outcome = _run(harness)

    returned = outcome.execution_failures[0]
    stored = port.failures[0]
    assert returned.occurred_at == clock_value
    assert returned.occurred_at is not clock_value
    assert stored.occurred_at is not clock_value
    assert stored is not returned


def test_exact_same_lane_replay_returns_loaded_record_without_overwrite() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(traces)
    nonce_factory = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )
    first = _run(harness)
    second = _run(
        harness,
        script_ref_by_case={
            "E2E01-01": "script:e2e01-01:success",
        },
    )

    assert first.results == second.results
    assert sut.calls == 1
    assert nonce_factory.calls == [((), {}), ((), {})]
    assert len(traces.events_by_ref) == 1
    assert traces.events.count("trace_append") == 1
    assert traces.events.count("trace_reload") == 1
    assert len(port.results) == 1
    assert port.events.count("result_append") == 2


def test_public_result_mutation_does_not_change_private_replay_cache() -> None:
    harness, sut, traces, port = _harness()

    first = _run(harness)
    cached_stage = next(
        iter(harness._persisted_stage_by_replay_key.values())
    )

    assert first.results[0] is not cached_stage.result
    assert first.results[0] is not next(iter(port.results.values()))
    object.__setattr__(
        first.results[0],
        "status",
        EvalResultStatus.FAIL,
    )

    second = _run(harness)

    assert second.command_passed is True
    assert second.results[0].status is EvalResultStatus.PASS
    assert sut.calls == 1
    assert traces.events.count("trace_append") == 1
    assert port.events.count("result_append") == 2


def test_caller_eval_run_uuid_cannot_alias_private_replay_key() -> None:
    caller_eval_run_id = UUID(str(EVAL_RUN_ID))
    original_integer = caller_eval_run_id.int
    harness, sut, traces, port = _harness()

    first = asyncio.run(
        harness.run_lane(
            eval_run_id=caller_eval_run_id,
            case_ids=("E2E01-01",),
        )
    )
    object.__setattr__(
        caller_eval_run_id,
        "int",
        UNKNOWN_EXECUTION_REF.int,
    )
    second = asyncio.run(
        harness.run_lane(
            eval_run_id=UUID(int=original_integer),
            case_ids=("E2E01-01",),
        )
    )

    assert first.command_passed is True
    assert second.command_passed is True
    assert sut.calls == 1
    assert traces.events.count("trace_append") == 1
    assert len(port.results) == 1


def test_authenticated_artifacts_are_snapshotted_at_construction() -> None:
    caller_artifacts = load_e2e01_artifacts(
        REPO_ROOT,
        candidate_version="candidate:c35687d",
    )
    caller_case = caller_artifacts.case_by_id("E2E01-01")
    expected_dataset_version = caller_case.version_manifest[
        "dataset_version"
    ]
    harness, _sut, _traces, port = _harness(
        artifacts=caller_artifacts,
    )
    object.__setattr__(
        caller_case,
        "version_manifest",
        {
            "dataset_version": "caller-injected-version",
            "fixture_versions": ["caller-fixture"],
        },
    )

    outcome = _run(harness)

    assert outcome.command_passed is True
    result = outcome.results[0]
    assert result.version_manifest.dataset_version == (
        expected_dataset_version
    )
    assert "caller-injected-version" not in result.model_dump_json()
    assert "caller-fixture" not in next(
        iter(port.results.values())
    ).model_dump_json()


def test_incremented_attempt_is_appended_under_a_distinct_identity() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(traces)
    nonce_factory = NonceFactorySpy(
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_2,
            SCRIPT_EXECUTION_REF_2,
        )
    )
    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )
    first = _run(harness, attempt=1)
    second = _run(harness, attempt=2)

    assert first.results[0].attempt == 1
    assert second.results[0].attempt == 2
    assert sut.calls == 2
    assert nonce_factory.calls == [((), {})] * 4
    assert len(traces.events_by_ref) == 2
    assert len(port.results) == 2


def test_conflicting_duplicate_attempt_routes_result_persistence_failure() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(traces)
    nonce_factory = NonceFactorySpy(
        (EXECUTION_REF_1, SCRIPT_EXECUTION_REF_1)
    )
    harness, _sut, _traces, port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )
    first = _run(harness)
    original = first.results[0]
    key = (EVAL_RUN_ID, "E2E01-01", "offline_gate", 1)
    port.results[key] = EvalResultRecord(
        schema_version=original.schema_version,
        eval_run_id=original.eval_run_id,
        case_id=original.case_id,
        lane=original.lane,
        attempt=original.attempt,
        status=EvalResultStatus.FAIL,
        grader_results=(
            EvalGraderResult(
                grader_name="SchemaGrader",
                status=EvalGraderStatus.FAIL,
                reason_code=EvalGraderReasonCode.ASSERTION_FAILED,
            ),
        ),
        observed_outcome=original.observed_outcome,
        trace_ref=original.trace_ref,
        version_manifest=original.version_manifest,
        completed_at=original.completed_at,
    )
    second = _run(harness)

    assert second.results == ()
    assert second.execution_failures[0].safe_error_code is (
        EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED
    )
    assert sut.calls == 1
    assert nonce_factory.calls == [((), {}), ((), {})]
    assert port.results[key].status is EvalResultStatus.FAIL


def test_result_port_mutates_only_a_detached_append_copy() -> None:
    class MutatingResultPort(InMemoryResultPort):
        async def append_eval_result(
            self,
            record: EvalResultRecord,
        ) -> InsertOnlyWriteResult:
            write_result = await super().append_eval_result(record)
            object.__setattr__(
                record,
                "observed_outcome",
                AgentOutcome.BLOCKED,
            )
            return write_result

    port = MutatingResultPort()
    harness, _sut, _traces, _port = _harness(port=port)

    outcome = _run(harness)

    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_PERSISTENCE
    )


@pytest.mark.parametrize(
    "write_result",
    (
        InsertOnlyWriteResult.INSERTED,
        InsertOnlyWriteResult.ALREADY_EXISTS,
    ),
)
def test_result_port_return_singleton_storage_is_pinned(
    write_result: InsertOnlyWriteResult,
) -> None:
    class SingletonMutatingPort(InMemoryResultPort):
        async def append_eval_result(
            self,
            record: EvalResultRecord,
        ) -> InsertOnlyWriteResult:
            if write_result is InsertOnlyWriteResult.INSERTED:
                await super().append_eval_result(record)
            object.__setattr__(
                write_result,
                "hidden_case_id",
                "E2E01-01",
            )
            return write_result

    member_storage = object.__getattribute__(
        write_result,
        "__dict__",
    )
    original_items = tuple(
        (key, dict.__getitem__(member_storage, key))
        for key in dict.__iter__(member_storage)
    )
    port = SingletonMutatingPort()
    harness, _sut, _traces, _port = _harness(port=port)

    try:
        outcome = _run(harness)
        restored_by_harness = (
            _canonical_enum_storage_is_pristine(
                write_result,
                original_items,
            )
        )
    finally:
        member_storage = object.__getattribute__(
            write_result,
            "__dict__",
        )
        dict.clear(member_storage)
        for key, stored_value in original_items:
            dict.__setitem__(
                member_storage,
                key,
                stored_value,
            )

    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_PERSISTENCE
    )
    assert harness._persisted_stage_by_replay_key == {}
    assert restored_by_harness is True


def test_failure_port_mutation_cannot_alias_returned_failure() -> None:
    class MutatingFailurePort(InMemoryResultPort):
        async def append_eval_execution_failure(
            self,
            record: EvalExecutionFailureRecord,
        ) -> None:
            await super().append_eval_execution_failure(record)
            object.__setattr__(
                record,
                "diagnostic_ref",
                UNKNOWN_EXECUTION_REF,
            )

    traces = InMemoryTraceCallbacks()
    port = MutatingFailurePort()
    harness, *_ = _harness(
        sut=SyntheticSut(traces, fault="sut"),
        traces=traces,
        port=port,
    )

    with pytest.raises(EvalHarnessCommandError) as caught:
        _run(harness)

    assert caught.value.args == ("EVAL_HARNESS_COMMAND_FAILED",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_behaviorful_loaded_result_is_closed_before_equality() -> None:
    class BehaviorfulLoadPort(InMemoryResultPort):
        async def append_eval_result(
            self,
            record: EvalResultRecord,
        ) -> InsertOnlyWriteResult:
            self.events.append("result_append")
            return InsertOnlyWriteResult.ALREADY_EXISTS

        async def load_eval_result(
            self,
            *,
            eval_run_id: UUID,
            case_id: str,
            lane: str,
            attempt: int,
        ) -> EvalResultRecord | None:
            return cast(EvalResultRecord, EvilEquality())

    BOUNDARY_METHOD_READ_COUNTER.reads = 0
    port = BehaviorfulLoadPort()
    harness, _sut, _traces, _port = _harness(port=port)

    outcome = _run(harness)

    assert BOUNDARY_METHOD_READ_COUNTER.reads == 0
    assert outcome.results == ()
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_PERSISTENCE
    )


def test_different_script_selection_misses_exact_replay_cache() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(traces)
    nonce_factory = NonceFactorySpy(
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_2,
            SCRIPT_EXECUTION_REF_2,
        )
    )
    harness, _sut, _traces, _port = _harness(
        sut=sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )
    case_id = "E2E01-01+SEC-ARGUMENT-BINDING"

    first = _run(
        harness,
        case_ids=(case_id,),
        script_ref_by_case={
            case_id: "script:sec-argument-binding:foreign-order",
        },
    )
    second = _run(
        harness,
        case_ids=(case_id,),
        script_ref_by_case={
            case_id: "script:sec-argument-binding:nonexistent-order",
        },
    )

    assert first.execution_failures == ()
    assert len(first.results) == 1
    assert second.results == ()
    assert second.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_PERSISTENCE
    )
    assert sut.calls == 2
    assert nonce_factory.calls == [((), {})] * 4


def test_same_run_case_attempt_in_two_lanes_are_distinct_records() -> None:
    harness, _sut, _traces, port = _harness()
    offline = _run(harness).results[0]
    preflight = build_qwen_baseline_preflight(
        artifacts=ARTIFACTS,
        eval_run_id=EVAL_RUN_ID,
        case_id="E2E01-01",
        attempt=1,
        environment={},
        real_sut=None,
        completed_at=NOW + timedelta(seconds=3),
    )
    assert preflight.not_run_record is not None
    qwen = asyncio.run(
        append_qwen_not_run_record(
            result_port=cast(EvalResultPort, port),
            record=preflight.not_run_record,
        )
    )

    assert offline.lane == "offline_gate"
    assert qwen.lane == "qwen_baseline"
    assert len(port.results) == 2
    assert {
        (record.eval_run_id, record.case_id, record.lane, record.attempt)
        for record in port.results.values()
    } == {
        (EVAL_RUN_ID, "E2E01-01", "offline_gate", 1),
        (EVAL_RUN_ID, "E2E01-01", "qwen_baseline", 1),
    }


def test_incomplete_e2e01_04_pair_persists_no_partial_pass() -> None:
    harness, _sut, _traces, port = _harness()
    outcome = _run(
        harness,
        case_ids=("E2E01-04-A",),
    )
    assert outcome.results == ()
    assert len(port.results) == 0
    assert outcome.execution_failures[0].failure_phase is (
        EvalExecutionFailurePhase.RESULT_COMPLETENESS
    )


def test_complete_equal_e2e01_04_pair_persists_both_passes() -> None:
    harness, _sut, _traces, port = _harness()
    outcome = _run(
        harness,
        case_ids=("E2E01-04-A", "E2E01-04-B"),
    )

    assert outcome.command_passed is True
    assert len(outcome.results) == 2
    assert {result.status for result in outcome.results} == {EvalResultStatus.PASS}
    assert len(port.results) == 2


def test_e2e01_04_safe_difference_forces_both_case_results_fail() -> None:
    class PairSut(SyntheticSut):
        async def execute_case(self, **kwargs):
            execution_input = kwargs["execution_input"]
            self.observable_overrides = {
                "http_status": (
                    201
                    if execution_input.messages[0].content.endswith("O-9999")
                    else 200
                )
            }
            return await super().execute_case(**kwargs)

    traces = InMemoryTraceCallbacks()
    sut = PairSut(traces)
    harness, *_ = _harness(sut=sut, traces=traces)
    outcome = _run(
        harness,
        case_ids=("E2E01-04-A", "E2E01-04-B"),
    )

    assert len(outcome.results) == 2
    assert {result.status for result in outcome.results} == {EvalResultStatus.FAIL}
    for result in outcome.results:
        disclosure = next(
            item
            for item in result.grader_results
            if item.grader_name == "DisclosureGrader"
        )
        assert disclosure.status is EvalGraderStatus.FAIL
        assert {
            CriticalFailureCode.CF_01,
            CriticalFailureCode.CF_03,
        } <= set(result.critical_failures)


def test_runtime_fault_directive_is_passed_through_the_closed_sut_seam() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(traces)
    harness, sut, _traces, _port = _harness(sut=sut, traces=traces)
    outcome = _run(
        harness,
        case_ids=("E2E01-01+FAULT-PROVIDER-PROTOCOL",),
        script_ref_by_case={
            "E2E01-01+FAULT-PROVIDER-PROTOCOL": (
                "script:fault-runtime:state-advanced-before-gate"
            )
        },
    )

    assert outcome.results[0].status is EvalResultStatus.PASS
    assert sut.last_runtime_fault == RuntimeFaultDirective(
        behavior="ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE",
        boundary="AFTER_REVALIDATION_BEFORE_GATE",
    )


def _qwen_output_for_input(
    raw_input: Mapping[str, object],
) -> RequestUnderstandingOutputV2:
    message_ref = UUID(str(raw_input["message_ref"]))
    query = str(raw_input["original_query"])
    order_id = next(
        value
        for value in ("O-1001", "O-2001", "O-9999")
        if value in query
    )
    return RequestUnderstandingOutputV2(
        schema_version="e2e01-thin-v2",
        message_ref=message_ref,
        contextualization=QueryContextualizationCandidateV2(
            text=query,
            resolved_reference_candidates=(
                ResolvedReferenceCandidateV2(
                    name="order_id",
                    candidate_value=order_id,
                    source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                    source_ref=message_ref,
                    source_quote=order_id,
                    confidence=1.0,
                ),
            ),
            uncertainties=(),
            source_message_refs=(message_ref,),
        ),
        task_delta_candidates=(
            TaskDeltaCandidate(
                candidate_id=uuid5(
                    NAMESPACE_URL,
                    f"qwen-test:{message_ref}",
                ),
                operation=TaskDeltaOperation.ADD_GOAL,
                goal_patch="查询订单状态",
                input_candidates=(
                    InputCandidate(
                        name="order_id",
                        candidate_value=order_id,
                        semantic_role="TARGET_RESOURCE_IDENTIFIER",
                        authority=InputAuthority.USER_CLAIM,
                        source_kind=InputSourceKind.CURRENT_MESSAGE,
                        source_ref=message_ref,
                        source_quote=order_id,
                        confidence=1.0,
                    ),
                ),
                confidence=1.0,
            ),
        ),
        next_move_candidate=NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name="get_order",
            arguments={"order_id": order_id},
            base_task_state_version=None,
        ),
    )


def _qwen_plan() -> PresentationPlan:
    return PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.WARM,
        opening_variant=OpeningVariant.ACKNOWLEDGE,
        field_order=tuple(PresentationField),
        closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
    )


def _qwen_response(
    name: str,
    arguments: Mapping[str, object],
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": json.dumps(arguments),
                }
            ]
        },
    )


class QwenTransportFactorySpy:
    def __init__(self) -> None:
        self.seen_by_transport: list[list[str]] = []

    def __call__(self) -> httpx.AsyncBaseTransport:
        seen: list[str] = []
        self.seen_by_transport.append(seen)

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            tool_name = body["tool_choice"]["name"]
            seen.append(tool_name)
            if tool_name == "submit_next_move":
                arguments = _qwen_output_for_input(
                    body["input"],
                ).model_dump(mode="json")
            elif tool_name == "submit_presentation_plan":
                arguments = _qwen_plan().model_dump(mode="json")
            else:
                raise AssertionError("unexpected Qwen function")
            return _qwen_response(tool_name, arguments)

        return httpx.MockTransport(handler)


class QwenSyntheticSut(SyntheticSut):
    def __init__(self, traces: InMemoryTraceCallbacks) -> None:
        super().__init__(traces)
        self.qwen_calls: list[dict[str, object]] = []

    async def execute_qwen_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        qwen_provider: QwenResponsesAdapterV2,
    ) -> EvalCaseSutResult | None:
        self.qwen_calls.append(
            {
                "execution_input": execution_input,
                "qwen_provider": qwen_provider,
            }
        )
        return await super().execute_case(
            execution_input=execution_input,
            scripted_provider=qwen_provider,
            runtime_fault=None,
        )


def _run_qwen(
    harness: OfflineEvalHarness,
    *,
    environment: Mapping[str, str],
    case_ids: Sequence[str] | None = None,
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
):
    return asyncio.run(
        harness.run_qwen_baseline(
            eval_run_id=EVAL_RUN_ID,
            environment=environment,
            case_ids=case_ids,
            transport_factory=transport_factory,
        )
    )


def test_qwen_runner_missing_env_persists_three_not_run_without_network() -> None:
    class ForbiddenQwenSut:
        def __init__(self) -> None:
            self.calls = 0

        async def execute_qwen_case(self, **_kwargs: object) -> None:
            self.calls += 1
            raise AssertionError("missing preflight cannot execute SUT")

    qwen_sut = ForbiddenQwenSut()
    transport_calls = 0

    def forbidden_transport() -> httpx.AsyncBaseTransport:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("missing preflight cannot create transport")

    harness, _sut, _traces, port = _harness(qwen_sut=qwen_sut)
    existing_signature = signature(OfflineEvalHarness.run_lane)
    assert tuple(existing_signature.parameters) == (
        "self",
        "eval_run_id",
        "lane",
        "attempt",
        "case_ids",
        "script_ref_by_case",
    )
    qwen_signature = signature(OfflineEvalHarness.run_qwen_baseline)
    assert tuple(qwen_signature.parameters) == (
        "self",
        "eval_run_id",
        "environment",
        "attempt",
        "case_ids",
        "transport_factory",
    )

    outcome = _run_qwen(
        harness,
        environment={},
        transport_factory=forbidden_transport,
    )

    assert outcome.lane == "qwen_baseline"
    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert tuple(result.case_id for result in outcome.results) == (
        "E2E01-01",
        "E2E01-04-A",
        "E2E01-04-B",
    )
    assert len(port.results) == 3
    assert qwen_sut.calls == 0
    assert transport_calls == 0
    for result in outcome.results:
        assert result.status is EvalResultStatus.NOT_RUN
        assert result.observed_outcome is None
        assert result.trace_ref is None
        assert result.grader_results == ()
        assert result.critical_failures == ()
        assert result.latency_summary is None
        assert result.usage_summary is None


def test_qwen_runner_uses_distinct_adapters_without_script_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    traces = InMemoryTraceCallbacks()
    qwen_sut = QwenSyntheticSut(traces)
    transport_factory = QwenTransportFactorySpy()
    nonce_factory = NonceFactorySpy(
        (
            EXECUTION_REF_1,
            SCRIPT_EXECUTION_REF_1,
            EXECUTION_REF_2,
            SCRIPT_EXECUTION_REF_2,
            EXECUTION_REF_3,
            SCRIPT_EXECUTION_REF_3,
        )
    )
    harness, _sut, _traces, port = _harness(
        qwen_sut=qwen_sut,
        traces=traces,
        nonce_factory=nonce_factory,
    )

    def forbidden_scripted_provider(
        _self: object,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        raise AssertionError("qwen runner cannot build Scripted Provider")

    monkeypatch.setattr(
        ScriptedModelProviderV2,
        "__init__",
        forbidden_scripted_provider,
    )
    outcome = _run_qwen(
        harness,
        environment={
            "DASHSCOPE_API_KEY": "synthetic-secret",
            "DASHSCOPE_BASE_URL": "https://qwen.invalid/v1",
        },
        transport_factory=transport_factory,
    )

    assert outcome.command_passed is True
    assert outcome.execution_failures == ()
    assert len(outcome.results) == 3
    assert {result.status for result in outcome.results} == {
        EvalResultStatus.PASS
    }
    assert len(port.results) == 3
    assert len(qwen_sut.qwen_calls) == 3
    providers = tuple(
        call["qwen_provider"] for call in qwen_sut.qwen_calls
    )
    assert all(type(provider) is QwenResponsesAdapterV2 for provider in providers)
    assert len({id(provider) for provider in providers}) == 3
    assert len({id(provider._client) for provider in providers}) == 3
    assert transport_factory.seen_by_transport == [
        ["submit_next_move", "submit_presentation_plan"],
        ["submit_next_move"],
        ["submit_next_move"],
    ]
    assert all(
        set(call) == {"execution_input", "qwen_provider"}
        for call in qwen_sut.qwen_calls
    )
    projection = "".join(
        result.model_dump_json() for result in outcome.results
    )
    assert "synthetic-secret" not in projection
    assert "qwen.invalid" not in projection
