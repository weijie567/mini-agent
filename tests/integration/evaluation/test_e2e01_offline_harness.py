from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from inspect import signature
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from pydantic import ValidationError

from mini_agent.application.persistence import (
    P0PersistenceEnvelope,
    P0RecordCode,
    P0RecordReference,
    encode_persistence_record,
)
from mini_agent.application.ports import EvalResultPort, ModelProvider
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
    InsertOnlyWriteResult,
    MessageDirection,
    MessageRecord,
    ProviderProtocolError,
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
from mini_agent.core.presentation import PresentationInput, PresentationPurpose
from mini_agent.core.request_understanding import (
    InputAuthority,
    RequestUnderstandingInput,
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
EXECUTION_REF_1 = UUID("11111111-1111-4111-8111-111111111111")
SCRIPT_EXECUTION_REF_1 = UUID("22222222-2222-4222-8222-222222222222")
EXECUTION_REF_2 = UUID("33333333-3333-4333-8333-333333333333")
SCRIPT_EXECUTION_REF_2 = UUID("44444444-4444-4444-8444-444444444444")
EXECUTION_REF_3 = UUID("55555555-5555-4555-8555-555555555555")
SCRIPT_EXECUTION_REF_3 = UUID("66666666-6666-4666-8666-666666666666")
EXECUTION_REF_4 = UUID("77777777-7777-4777-8777-777777777777")
SCRIPT_EXECUTION_REF_4 = UUID("88888888-8888-4888-8888-888888888888")
UNKNOWN_EXECUTION_REF = UUID("99999999-9999-4999-8999-999999999999")
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
    *,
    observation: OrderObservation,
    run_id: UUID,
    task: TaskRecord,
    request_unit: RequestUnitRecord,
    tool_call: ToolCallRecord,
) -> P0PersistenceEnvelope:
    return encode_persistence_record(
        P0RecordCode.OBSERVATION_RECORD,
        observation,
        external_references=(
            _record_reference(
                "source_tool_call_id",
                P0RecordCode.TOOL_CALL_RECORD,
                "tool_call_id",
                tool_call.tool_call_id,
            ),
            _record_reference(
                "source_run_id",
                P0RecordCode.AGENT_RUN_RECORD,
                "run_id",
                run_id,
            ),
            _record_reference(
                "source_task_id",
                P0RecordCode.TASK_RECORD,
                "task_id",
                task.task_id,
            ),
            _record_reference(
                "source_request_unit_id",
                P0RecordCode.REQUEST_UNIT_RECORD,
                "request_unit_id",
                request_unit.request_unit_id,
            ),
        ),
    )


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
    accepted_delta: AcceptedTaskDelta,
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
        scripted_provider: ScriptedModelProvider,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None:
        self.calls += 1
        self.last_runtime_fault = runtime_fault
        if self.fault == "sut":
            raise RuntimeError("raw-sut-secret customer-A O-1001")
        if self.fault == "missing":
            return None
        assert isinstance(scripted_provider, ModelProvider)
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
        accepted_delta = AcceptedTaskDelta(
            accepted_delta_id=_case_uuid(identity_seed, "accepted-delta"),
            candidate_ref=proposed_delta.candidate_id,
            message_ref=message_ref,
            operation=proposed_delta.operation,
            goal_text=proposed_delta.goal_patch,
            input_binding_refs=(binding.binding_id,),
            accepted_at=NOW,
        )
        request_understanding_record = RequestUnderstandingRecord(
            run_id=run_id,
            message_ref=message_ref,
            schema_version="request_understanding_record.p0.v1",
            candidate_validation=(
                CandidateValidationRecord(
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
        observation_envelopes: tuple[P0PersistenceEnvelope, ...] = ()
        if observation is not None:
            assert task is not None
            assert request_unit is not None
            assert tool_call is not None
            observation_envelopes = (
                _observation_envelope(
                    observation=observation,
                    run_id=run_id,
                    task=task,
                    request_unit=request_unit,
                    tool_call=tool_call,
                ),
            )
        evidence_observations = (observation,) if observation is not None else ()
        if self.fault == "raw_observation_visibility":
            assert observation is not None
            assert task is not None
            assert request_unit is not None
            assert tool_call is not None
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
            observation_envelopes = (
                _observation_envelope(
                    observation=canonical_audit,
                    run_id=run_id,
                    task=task,
                    request_unit=request_unit,
                    tool_call=tool_call,
                ),
            )
        elif self.fault == "observation_supersedes":
            assert observation is not None
            assert task is not None
            assert request_unit is not None
            assert tool_call is not None
            superseding = observation.model_copy(
                update={
                    "supersedes": _case_uuid(
                        identity_seed,
                        "previous-observation",
                    )
                }
            )
            evidence_observations = (superseding,)
            observation_envelopes = (
                _observation_envelope(
                    observation=superseding,
                    run_id=run_id,
                    task=task,
                    request_unit=request_unit,
                    tool_call=tool_call,
                ),
            )
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
            "request_understanding_output": request_output,
            "request_understanding_records": (
                (request_understanding_record,)
                if request_understanding_record is not None
                else ()
            ),
            "accepted_task_deltas": (
                (accepted_delta,) if accepted_delta is not None else ()
            ),
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
            "observation_persistence_envelopes": observation_envelopes,
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
        evidence_values.update(self.evidence_overrides)
        evidence = UnboundEvalEvidence(**evidence_values)
        return EvalCaseSutResult(
            execution_ref=execution_input.execution_ref,
            evidence=evidence,
            safe_observable=observable,
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

    async def execute_case(self, **kwargs: object) -> EvalCaseSutResult | None:
        result = await self._delegate.execute_case(**kwargs)
        assert type(result) is EvalCaseSutResult
        if self._mutation == "unknown_execution_ref":
            return result.model_copy(
                update={"execution_ref": UNKNOWN_EXECUTION_REF}
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
            cycle: list[object] = []
            cycle.append(cycle)
            request_output = result.evidence.request_understanding_output
            assert request_output is not None
            object.__setattr__(
                request_output,
                "task_delta_candidates",
                cycle,
            )
            return result
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
    sut: object | None = None,
    traces: InMemoryTraceCallbacks | None = None,
    port: InMemoryResultPort | None = None,
    grader_runner=None,
    nonce_factory: Callable[..., UUID] | None = None,
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
        "artifacts": ARTIFACTS,
        "sut": sut,
        "trace_callbacks": traces,
        "result_port": cast(EvalResultPort, port),
        "clock": lambda: NOW + timedelta(seconds=2),
        "grader_runner": grader_runner,
    }
    if nonce_factory is not None:
        harness_arguments["nonce_factory"] = nonce_factory
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
    case = ARTIFACTS.case_by_id("E2E01-01")
    execution_input = EvalCaseExecutionInput(
        execution_ref=EXECUTION_REF_1,
        messages=(
            {
                "role": "user",
                "content": case.input["messages"][0]["content"],
            },
        ),
        trusted_context_fixture_ref=case.input[
            "trusted_context_fixture_ref"
        ],
    )
    provider = ScriptedModelProvider(
        ARTIFACTS.script_by_ref("script:e2e01-01:success"),
        script_execution_ref=SCRIPT_EXECUTION_REF_1,
    )
    actual = asyncio.run(
        provider.propose_next_move(_request(execution_input))
    )
    mismatched_move = actual.next_move_candidate.model_copy(
        update={"arguments": {"order_id": "O-2001"}}
    )
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        evidence_overrides={
            "request_understanding_output": actual.model_copy(
                update={"next_move_candidate": mismatched_move}
            )
        },
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
        evidence_overrides={"observation_persistence_envelopes": ()},
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


def test_raw_observation_visibility_fails_canonical_harness_grading() -> None:
    traces = InMemoryTraceCallbacks()
    sut = SyntheticSut(
        traces,
        fault="raw_observation_visibility",
    )
    harness, *_ = _harness(sut=sut, traces=traces)

    outcome = _run(harness)

    assert outcome.command_passed is False
    assert outcome.execution_failures == ()
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.status is EvalResultStatus.FAIL
    configured_names = tuple(ARTIFACTS.case_by_id("E2E01-01").grading["graders"])
    assert tuple(item.grader_name for item in result.grader_results) == configured_names
    assert all(
        item.status is EvalGraderStatus.FAIL
        and item.reason_code is EvalGraderReasonCode.ASSERTION_FAILED
        for item in result.grader_results
    )


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
        "request_understanding_records",
        "accepted_task_deltas",
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
