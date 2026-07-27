from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from mini_agent.application.ports import EvalResultPort, ModelProvider
from mini_agent.application.records import (
    AgentRunResult,
    CriticalFailureCode,
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultRecord,
    EvalResultStatus,
    InsertOnlyWriteResult,
)
from mini_agent.core.order import (
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.presentation import PresentationInput, PresentationPurpose
from mini_agent.core.request_understanding import RequestUnderstandingInput
from mini_agent.core.tool_system import ToolSpec, compute_model_visible_toolset_hash
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
    load_e2e01_artifacts,
)
from mini_agent.evaluation.graders import (
    EvalEvidence,
    GradingOutcome,
    SafeCaseObservable,
    grade_evidence,
    ordinary_trace_shape,
)
from mini_agent.evaluation.harness import (
    EvalCaseSutResult,
    EvalHarnessCommandError,
    OfflineEvalHarness,
    append_qwen_not_run_record,
    build_qwen_baseline_preflight,
)
from mini_agent.evaluation.scripted_provider import (
    RuntimeFaultDirective,
    ScriptedModelProvider,
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


def _tool_spec() -> ToolSpec:
    return ToolSpec(
        name="get_order",
        description="查询当前用户订单。",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"outcome": {"type": "string"}},
            "required": ["outcome"],
        },
    )


def _request(case: EvalCaseArtifact) -> RequestUnderstandingInput:
    tool = _tool_spec()
    message = case.input["messages"][0]
    return RequestUnderstandingInput(
        run_id=RUN_ID,
        message_ref=UUID("00000000-0000-4000-8000-000000000804"),
        original_query=message["content"],
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
    def __init__(self) -> None:
        self.results: dict[
            tuple[UUID, str, str, int],
            EvalResultRecord,
        ] = {}
        self.failures: list[EvalExecutionFailureRecord] = []
        self.events: list[str] = []
        self.fail_result_append = False
        self.fail_failure_append = False
        self.fail_load = False

    async def append_eval_result(
        self,
        record: EvalResultRecord,
    ) -> InsertOnlyWriteResult:
        self.events.append("result_append")
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
            result
            for key, result in self.results.items()
            if key[0] == eval_run_id
        )

    async def append_eval_execution_failure(
        self,
        record: EvalExecutionFailureRecord,
    ) -> None:
        self.events.append("failure_append")
        if self.fail_failure_append:
            raise RuntimeError("raw-failure-store-secret")
        self.failures.append(record)

    async def list_eval_execution_failures(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalExecutionFailureRecord, ...]:
        return tuple(
            failure
            for failure in self.failures
            if failure.eval_run_id == eval_run_id
        )


class InMemoryTraceCallbacks:
    def __init__(self) -> None:
        self.events_by_ref: dict[UUID, list[TraceEvent]] = {}
        self.trace_ref_by_run: dict[UUID, UUID] = {}
        self.events: list[str] = []
        self.fail_append = False
        self.fail_reload = False
        self.drop_append = False

    def seed(self, trace_ref: UUID, events: Sequence[TraceEvent]) -> None:
        self.events_by_ref[trace_ref] = list(events)
        for event in events:
            self.trace_ref_by_run[event.run_id] = trace_ref

    async def append_eval_case_graded(self, event: TraceEvent) -> None:
        self.events.append("trace_append")
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
        if self.fail_reload:
            raise RuntimeError("raw-trace-store-secret")
        return tuple(self.events_by_ref[trace_ref])


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

    async def execute_case(
        self,
        *,
        case: EvalCaseArtifact,
        scripted_provider: ScriptedModelProvider,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None:
        self.calls += 1
        if self.fault == "sut":
            raise RuntimeError("raw-sut-secret customer-A O-1001")
        if self.fault == "missing":
            return None
        assert isinstance(scripted_provider, ModelProvider)
        await scripted_provider.propose_next_move(_request(case))
        if case.case_id == "E2E01-01":
            await scripted_provider.plan_presentation(_presentation_input())

        outcome = (
            AgentOutcome.COMPLETED
            if case.case_id == "E2E01-01"
            else AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
        )
        stop_reason = (
            StopReason.GOAL_COMPLETED
            if case.case_id == "E2E01-01"
            else StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE
        )
        initial_trace = (
            TraceEvent(
                trace_event_id=UUID(int=810),
                event_type=TraceEventType.RUN_STARTED,
                occurred_at=NOW,
                run_id=RUN_ID,
                case_id=case.case_id,
            ),
            TraceEvent(
                trace_event_id=UUID(int=811),
                event_type=TraceEventType.RUN_STOPPED,
                occurred_at=NOW + timedelta(seconds=1),
                run_id=RUN_ID,
                case_id=case.case_id,
                user_outcome=outcome,
                stop_reason=stop_reason,
            ),
        )
        self.traces.seed(TRACE_REF, initial_trace)
        evidence_values: dict[str, object] = {
            "case_id": case.case_id,
            "observed_outcome": outcome,
            "trace_ref": TRACE_REF,
            "trace_events": initial_trace,
            "required_trace_events": (
                TraceEventType.RUN_STARTED,
                TraceEventType.RUN_STOPPED,
                TraceEventType.EVAL_CASE_GRADED,
            ),
            "expected_event_counts": (
                {
                    "event_type": TraceEventType.EVAL_CASE_GRADED,
                    "count": 1,
                },
            ),
            "run_record": AgentRunRecord(
                run_id=RUN_ID,
                status=AgentRunStatus.COMPLETED,
                provider_lane="offline_gate",
                started_at=NOW,
                completed_at=NOW + timedelta(seconds=1),
                stop_reason=stop_reason,
            ),
            "agent_result": AgentRunResult(
                run_id=RUN_ID,
                outcome=outcome,
                message="合成结果",
            ),
        }
        evidence_values.update(self.evidence_overrides)
        evidence = EvalEvidence(**evidence_values)
        observable_values: dict[str, object] = {
            "case_id": case.case_id,
            "http_status": 200,
            "user_outcome": outcome,
            "response_policy": (
                "DETERMINISTIC_ORDER_SUMMARY_V1"
                if case.case_id == "E2E01-01"
                else "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE"
            ),
            "ordinary_trace_shape": ordinary_trace_shape(initial_trace),
            "model_calls": 2 if case.case_id == "E2E01-01" else 1,
        }
        observable_values.update(self.observable_overrides)
        return EvalCaseSutResult(
            evidence=evidence,
            safe_observable=SafeCaseObservable(**observable_values),
        )


def _harness(
    *,
    sut: SyntheticSut | None = None,
    traces: InMemoryTraceCallbacks | None = None,
    port: InMemoryResultPort | None = None,
    grader_runner=None,
) -> tuple[
    OfflineEvalHarness,
    SyntheticSut,
    InMemoryTraceCallbacks,
    InMemoryResultPort,
]:
    traces = traces or InMemoryTraceCallbacks()
    port = port or InMemoryResultPort()
    sut = sut or SyntheticSut(traces)
    harness = OfflineEvalHarness(
        artifacts=ARTIFACTS,
        sut=sut,
        trace_callbacks=traces,
        result_port=cast(EvalResultPort, port),
        clock=lambda: NOW + timedelta(seconds=2),
        grader_runner=grader_runner,
    )
    return harness, sut, traces, port


def _run(
    harness: OfflineEvalHarness,
    *,
    case_ids: Sequence[str] = ("E2E01-01",),
    script_ref_by_case: Mapping[str, str] | None = None,
    lane: str = "offline_gate",
):
    return asyncio.run(
        harness.run_lane(
            eval_run_id=EVAL_RUN_ID,
            lane=lane,
            attempt=1,
            case_ids=case_ids,
            script_ref_by_case=script_ref_by_case,
        )
    )


def test_complete_case_appends_graded_reloads_then_persists_pass() -> None:
    harness, _sut, traces, port = _harness()
    outcome = _run(harness)

    assert outcome.command_passed is True
    assert outcome.execution_failures == ()
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.status is EvalResultStatus.PASS
    assert result.observed_outcome is AgentOutcome.COMPLETED
    assert result.trace_ref == TRACE_REF
    assert result.grader_results
    assert result.critical_failures == ()
    assert result.usage_summary is None
    assert result.latency_summary is None
    assert traces.events == ["trace_append", "trace_reload"]
    assert port.events == ["result_append"]
    final_trace = traces.events_by_ref[TRACE_REF]
    assert [event.event_type for event in final_trace].count(
        TraceEventType.EVAL_CASE_GRADED
    ) == 1


def test_expected_assertion_and_critical_failure_persist_case_fail() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        evidence_overrides={
            "disclosure_assertions_pass": False,
            "critical_failures": (CriticalFailureCode.CF_01,),
        },
    )
    harness, _sut, _traces, _port = _harness(sut=sut, traces=traces)
    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert outcome.results[0].status is EvalResultStatus.FAIL
    assert outcome.results[0].critical_failures == (CriticalFailureCode.CF_01,)


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


def test_exact_same_lane_replay_returns_loaded_record_without_overwrite() -> None:
    harness, _sut, _traces, port = _harness()
    first = _run(harness)
    second = _run(harness)

    assert first.results == second.results
    assert len(port.results) == 1
    assert port.events.count("result_append") == 2


def test_conflicting_duplicate_attempt_routes_result_persistence_failure() -> None:
    harness, _sut, _traces, port = _harness()
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
    assert port.results[key].status is EvalResultStatus.FAIL


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


def test_e2e01_04_safe_difference_forces_both_case_results_fail() -> None:
    class PairSut(SyntheticSut):
        async def execute_case(self, **kwargs):
            case = kwargs["case"]
            self.observable_overrides = {
                "model_calls": 2 if case.case_id == "E2E01-04-B" else 1
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
    assert {result.status for result in outcome.results} == {
        EvalResultStatus.FAIL
    }
    for result in outcome.results:
        disclosure = next(
            item
            for item in result.grader_results
            if item.grader_name == "DisclosureGrader"
        )
        assert disclosure.status is EvalGraderStatus.FAIL
