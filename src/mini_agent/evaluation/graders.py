"""Deterministic E2E01 Eval graders and safe pair comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from uuid import UUID

from mini_agent.application.records import (
    AgentRunResult,
    CriticalFailureCode,
    EvalGraderResult,
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
    count: int


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


class DeterministicGrader(Protocol):
    name: str

    def grade(self, evidence: EvalEvidence) -> EvalGraderResult: ...


class _UnimplementedGrader:
    name = ""

    def grade(self, evidence: EvalEvidence) -> EvalGraderResult:
        raise NotImplementedError


class SchemaGrader(_UnimplementedGrader):
    name = "SchemaGrader"


class IdentityBoundaryGrader(_UnimplementedGrader):
    name = "IdentityBoundaryGrader"


class RequestUnderstandingGrader(_UnimplementedGrader):
    name = "RequestUnderstandingGrader"


class InputBindingGrader(_UnimplementedGrader):
    name = "InputBindingGrader"


class TaskStateGrader(_UnimplementedGrader):
    name = "TaskStateGrader"


class ToolCallGrader(_UnimplementedGrader):
    name = "ToolCallGrader"


class ObservationGrader(_UnimplementedGrader):
    name = "ObservationGrader"


class DisclosureGrader(_UnimplementedGrader):
    name = "DisclosureGrader"


class RendererFactGrader(_UnimplementedGrader):
    name = "RendererFactGrader"


class ErrorMappingGrader(_UnimplementedGrader):
    name = "ErrorMappingGrader"


class TraceCompletenessGrader(_UnimplementedGrader):
    name = "TraceCompletenessGrader"


class PersistenceGrader(_UnimplementedGrader):
    name = "PersistenceGrader"


class ToolsetReplayGrader(_UnimplementedGrader):
    name = "ToolsetReplayGrader"


class SafeTraceShapeEntry(AuditOnlyModel):
    event_type: TraceEventType
    count: int
    status: str | None = None
    reason: str | None = None


class SafeCaseObservable(AuditOnlyModel):
    case_id: str
    http_status: int
    user_outcome: AgentOutcome
    response_policy: str
    ordinary_trace_shape: tuple[SafeTraceShapeEntry, ...]
    model_calls: int


class GradingOutcome(AuditOnlyModel):
    status: EvalResultStatus
    grader_results: tuple[EvalGraderResult, ...]
    critical_failures: tuple[CriticalFailureCode, ...]


def grader_registry() -> Mapping[str, DeterministicGrader]:
    raise NotImplementedError


def grade_evidence(
    configured_grader_names: Sequence[str],
    evidence: EvalEvidence,
) -> GradingOutcome:
    raise NotImplementedError


def determine_result_status(
    grader_results: Sequence[EvalGraderResult],
    critical_failures: Sequence[CriticalFailureCode],
) -> EvalResultStatus:
    raise NotImplementedError


def ordinary_trace_shape(
    trace_events: Sequence[TraceEvent],
) -> tuple[SafeTraceShapeEntry, ...]:
    raise NotImplementedError


def e2e01_04_safe_observables_match(
    observables_by_case: Mapping[str, SafeCaseObservable],
) -> bool:
    raise NotImplementedError
