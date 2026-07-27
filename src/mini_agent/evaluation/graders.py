"""Deterministic E2E01 Eval graders and safe pair comparison."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Annotated, ClassVar, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from mini_agent.application.records import (
    AgentRunResult,
    CriticalFailureCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultStatus,
)
from mini_agent.core.common import AuditOnlyModel
from mini_agent.core.memory import ContextManifest, OrderObservation
from mini_agent.core.request_understanding import RequestUnderstandingOutput
from mini_agent.core.task_state import InputBinding, RequestUnitRecord, TaskRecord
from mini_agent.core.tool_system import GateDecision, ToolCallRecord
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    TraceEvent,
    TraceEventType,
)


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


class GradingConfigurationError(ValueError):
    """A configured grader plan is unknown, duplicated, empty, or incomplete."""


class TraceEventCountExpectation(AuditOnlyModel):
    event_type: TraceEventType
    count: Annotated[int, Field(ge=0)]


class EvalEvidence(AuditOnlyModel):
    """Eval-only aggregate referencing canonical records and safe assertions."""

    case_id: str
    observed_outcome: AgentOutcome
    trace_ref: UUID
    trace_events: tuple[TraceEvent, ...]
    required_trace_events: tuple[TraceEventType, ...] = ()
    forbidden_trace_events: tuple[TraceEventType, ...] = ()
    expected_event_counts: tuple[TraceEventCountExpectation, ...] = ()
    schema_assertions_pass: bool | None = True
    identity_boundary_assertions_pass: bool | None = True
    request_understanding_assertions_pass: bool | None = True
    input_binding_assertions_pass: bool | None = True
    task_state_assertions_pass: bool | None = True
    tool_call_assertions_pass: bool | None = True
    observation_assertions_pass: bool | None = True
    disclosure_assertions_pass: bool | None = True
    renderer_fact_assertions_pass: bool | None = True
    error_mapping_assertions_pass: bool | None = True
    persistence_assertions_pass: bool | None = True
    toolset_replay_assertions_pass: bool | None = True
    critical_failures: tuple[CriticalFailureCode, ...] = ()
    run_record: AgentRunRecord | None = None
    agent_result: AgentRunResult | None = None
    request_understanding_output: RequestUnderstandingOutput | None = None
    input_bindings: tuple[InputBinding, ...] = ()
    task_records: tuple[TaskRecord, ...] = ()
    request_units: tuple[RequestUnitRecord, ...] = ()
    gate_decisions: tuple[GateDecision, ...] = ()
    tool_calls: tuple[ToolCallRecord, ...] = ()
    observations: tuple[OrderObservation, ...] = ()
    context_manifests: tuple[ContextManifest, ...] = ()

    @model_validator(mode="after")
    def evidence_sets_are_unambiguous(self) -> "EvalEvidence":
        if len(self.critical_failures) != len(set(self.critical_failures)):
            raise ValueError("critical_failures must contain unique codes")
        if len(self.required_trace_events) != len(
            set(self.required_trace_events)
        ):
            raise ValueError("required Trace event types must be unique")
        if len(self.forbidden_trace_events) != len(
            set(self.forbidden_trace_events)
        ):
            raise ValueError("forbidden Trace event types must be unique")
        count_types = tuple(
            expectation.event_type for expectation in self.expected_event_counts
        )
        if len(count_types) != len(set(count_types)):
            raise ValueError("Trace count expectations must be unique")
        return self


class DeterministicGrader(Protocol):
    name: str

    def grade(self, evidence: EvalEvidence) -> EvalGraderResult: ...


class _CheckGrader:
    name = ""
    check_field: ClassVar[str]

    def grade(self, evidence: EvalEvidence) -> EvalGraderResult:
        if type(evidence) is not EvalEvidence:
            raise TypeError("grader evidence must be EvalEvidence")
        check = getattr(evidence, self.check_field)
        if check is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if check is not True:
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class SchemaGrader(_CheckGrader):
    name = "SchemaGrader"
    check_field = "schema_assertions_pass"

    def grade(self, evidence: EvalEvidence) -> EvalGraderResult:
        result = super().grade(evidence)
        if result.status is EvalGraderStatus.FAIL:
            return result
        if evidence.run_record is None or evidence.agent_result is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        if (
            evidence.run_record.run_id != evidence.agent_result.run_id
            or evidence.agent_result.outcome is not evidence.observed_outcome
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return result


class IdentityBoundaryGrader(_CheckGrader):
    name = "IdentityBoundaryGrader"
    check_field = "identity_boundary_assertions_pass"


class RequestUnderstandingGrader(_CheckGrader):
    name = "RequestUnderstandingGrader"
    check_field = "request_understanding_assertions_pass"


class InputBindingGrader(_CheckGrader):
    name = "InputBindingGrader"
    check_field = "input_binding_assertions_pass"


class TaskStateGrader(_CheckGrader):
    name = "TaskStateGrader"
    check_field = "task_state_assertions_pass"


class ToolCallGrader(_CheckGrader):
    name = "ToolCallGrader"
    check_field = "tool_call_assertions_pass"


class ObservationGrader(_CheckGrader):
    name = "ObservationGrader"
    check_field = "observation_assertions_pass"


class DisclosureGrader(_CheckGrader):
    name = "DisclosureGrader"
    check_field = "disclosure_assertions_pass"


class RendererFactGrader(_CheckGrader):
    name = "RendererFactGrader"
    check_field = "renderer_fact_assertions_pass"


class ErrorMappingGrader(_CheckGrader):
    name = "ErrorMappingGrader"
    check_field = "error_mapping_assertions_pass"


class TraceCompletenessGrader:
    name = "TraceCompletenessGrader"

    def grade(self, evidence: EvalEvidence) -> EvalGraderResult:
        if type(evidence) is not EvalEvidence:
            raise TypeError("grader evidence must be EvalEvidence")
        events = evidence.trace_events
        if not events:
            return _failed(self.name, EvalGraderReasonCode.TRACE_EVENT_MISSING)
        if evidence.run_record is None:
            return _failed(self.name, EvalGraderReasonCode.MISSING_RECORD)
        event_types = tuple(event.event_type for event in events)
        event_counts = Counter(event_types)
        if set(evidence.required_trace_events) & set(
            evidence.forbidden_trace_events
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if any(
            required not in event_counts
            for required in evidence.required_trace_events
        ):
            return _failed(self.name, EvalGraderReasonCode.TRACE_EVENT_MISSING)
        if any(
            forbidden in event_counts
            for forbidden in evidence.forbidden_trace_events
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        for expectation in evidence.expected_event_counts:
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
        if any(event.run_id != evidence.run_record.run_id for event in events):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        if any(
            event.case_id not in {None, evidence.case_id} for event in events
        ):
            return _failed(self.name, EvalGraderReasonCode.ASSERTION_FAILED)
        return _passed(self.name)


class PersistenceGrader(_CheckGrader):
    name = "PersistenceGrader"
    check_field = "persistence_assertions_pass"


class ToolsetReplayGrader(_CheckGrader):
    name = "ToolsetReplayGrader"
    check_field = "toolset_replay_assertions_pass"


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


def grade_evidence(
    configured_grader_names: Sequence[str],
    evidence: EvalEvidence,
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
    results = tuple(_GRADER_REGISTRY[name].grade(evidence) for name in names)
    status = determine_result_status(results, evidence.critical_failures)
    return GradingOutcome(
        status=status,
        grader_results=results,
        critical_failures=evidence.critical_failures,
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
    if (
        len(grader_names) != len(set(grader_names))
        or len(failures) != len(set(failures))
    ):
        raise GradingConfigurationError("grading outcome identities are duplicated")
    if failures or any(
        result.status is EvalGraderStatus.FAIL for result in results
    ):
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
