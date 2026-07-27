"""Injected E2E01 Eval Harness with structured Result/Failure separation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Awaitable, Protocol
from uuid import UUID

from mini_agent.application.ports import EvalResultPort
from mini_agent.application.records import (
    EvalExecutionFailureRecord,
    EvalResultRecord,
)
from mini_agent.core.common import AuditOnlyModel
from mini_agent.core.trace import TraceEvent
from mini_agent.evaluation.artifacts import EvalCaseArtifact, LoadedE2E01Artifacts
from mini_agent.evaluation.graders import (
    EvalEvidence,
    GradingOutcome,
    SafeCaseObservable,
)
from mini_agent.evaluation.scripted_provider import (
    RuntimeFaultDirective,
    ScriptedModelProvider,
)


class EvalHarnessCommandError(RuntimeError):
    """Bounded command failure when even safe failure persistence is unavailable."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("EVAL_HARNESS_COMMAND_FAILED")


class EvalCaseSutResult(AuditOnlyModel):
    evidence: EvalEvidence
    safe_observable: SafeCaseObservable


class EvalCaseSut(Protocol):
    async def execute_case(
        self,
        *,
        case: EvalCaseArtifact,
        scripted_provider: ScriptedModelProvider,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None: ...


class EvalTraceCallbacks(Protocol):
    async def append_eval_case_graded(self, event: TraceEvent) -> None: ...

    async def reload_trace(self, trace_ref: UUID) -> tuple[TraceEvent, ...]: ...


GraderRunner = Callable[
    [Sequence[str], EvalEvidence],
    GradingOutcome,
]


class EvalLaneRunOutcome(AuditOnlyModel):
    lane: str
    results: tuple[EvalResultRecord, ...]
    execution_failures: tuple[EvalExecutionFailureRecord, ...]
    command_passed: bool


class QwenBaselinePreflight(AuditOnlyModel):
    ready: bool
    not_run_record: EvalResultRecord | None = None
    reason: str | None = None


class OfflineEvalHarness:
    def __init__(
        self,
        *,
        artifacts: LoadedE2E01Artifacts,
        sut: EvalCaseSut,
        trace_callbacks: EvalTraceCallbacks,
        result_port: EvalResultPort,
        clock: Callable[[], datetime],
        grader_runner: GraderRunner | None = None,
    ) -> None:
        raise NotImplementedError

    async def run_lane(
        self,
        *,
        eval_run_id: UUID,
        lane: str = "offline_gate",
        attempt: int = 1,
        case_ids: Sequence[str] | None = None,
        script_ref_by_case: Mapping[str, str] | None = None,
    ) -> EvalLaneRunOutcome:
        raise NotImplementedError


def build_qwen_baseline_preflight(
    *,
    artifacts: LoadedE2E01Artifacts,
    eval_run_id: UUID,
    case_id: str,
    attempt: int,
    environment: Mapping[str, str],
    real_sut: EvalCaseSut | None,
    completed_at: datetime,
) -> QwenBaselinePreflight:
    raise NotImplementedError


async def append_qwen_not_run_record(
    *,
    result_port: EvalResultPort,
    record: EvalResultRecord,
) -> EvalResultRecord:
    raise NotImplementedError
