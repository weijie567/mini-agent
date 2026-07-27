from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from mini_agent.application.ports import EvalResultPort, ModelProvider
from mini_agent.application.records import (
    AgentRunResult,
    ConversationRecord,
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
    InputBinding,
    InputValidationStatus,
    RequestUnitRecord,
    TaskRecord,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateReasonCode,
    ModelVisibleToolsetArtifact,
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
    grade_evidence,
    ordinary_trace_shape,
)
from mini_agent.evaluation.harness import (
    EvalCaseSutResult,
    EvalHarnessCommandError,
    OfflineEvalHarness,
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


def _tool_spec() -> ToolSpec:
    return get_order_tool_spec()


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


def _synthetic_trace(
    *,
    expectations: EvalCaseExpectations,
    run_id: UUID,
    message_ref: UUID,
    binding: InputBinding | None,
    task: TaskRecord | None,
    request_unit: RequestUnitRecord | None,
    gate: GateDecision | None,
    tool_call: ToolCallRecord | None,
    observation: OrderObservation | None,
    manifests: tuple[ContextManifest, ...],
) -> tuple[TraceEvent, ...]:
    exact_counts = {
        item.event_type: item.count for item in expectations.expected_event_counts
    }
    events: list[TraceEvent] = []
    manifest_index = 0
    sequence = 0
    for event_type in expectations.required_trace_events:
        if event_type is TraceEventType.EVAL_CASE_GRADED:
            continue
        count = exact_counts.get(event_type, 1)
        for _ in range(count):
            sequence += 1
            values: dict[str, object] = {
                "trace_event_id": _case_uuid(
                    expectations.case_id,
                    f"trace:{sequence}",
                ),
                "event_type": event_type,
                "occurred_at": NOW + timedelta(milliseconds=sequence),
                "run_id": run_id,
                "case_id": expectations.case_id,
            }
            if event_type is TraceEventType.MESSAGE_ACCEPTED:
                values["message_ref"] = message_ref
            elif event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED:
                manifest = manifests[manifest_index]
                request_understanding_calls = (
                    expectations.expected_model_calls
                    - expectations.expected_presentation_model_calls
                )
                model_call_purpose = (
                    "REQUEST_UNDERSTANDING"
                    if manifest_index < request_understanding_calls
                    else "PRESENTATION"
                )
                manifest_index += 1
                values.update(
                    {
                        "context_manifest_id": manifest.context_manifest_id,
                        "model_call_id": manifest.model_call_id,
                        "model_call_purpose": model_call_purpose,
                        "tool_registry_version": (manifest.tool_registry_version),
                        "model_visible_toolset_hash": (
                            manifest.model_visible_toolset_hash
                        ),
                    }
                )
            elif event_type is TraceEventType.INPUT_BINDING_RECORDED:
                assert binding is not None
                values["input_binding_ref"] = binding.binding_id
            elif event_type is TraceEventType.TASK_STATE_CHANGED:
                assert task is not None and request_unit is not None
                values.update(
                    {
                        "task_id": task.task_id,
                        "request_unit_id": request_unit.request_unit_id,
                    }
                )
            elif event_type is TraceEventType.NEXT_MOVE_REVALIDATED:
                values["validated_task_state_version"] = 1
            elif event_type is TraceEventType.GATE_DECISION_RECORDED:
                assert gate is not None
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
                TraceEventType.TOOL_CALL_TIMED_OUT,
                TraceEventType.TOOL_CALL_INTERRUPTED,
            }:
                assert tool_call is not None
                status_by_type = {
                    TraceEventType.TOOL_CALL_CREATED: ToolCallStatus.CREATED,
                    TraceEventType.TOOL_CALL_STARTED: ToolCallStatus.RUNNING,
                    TraceEventType.TOOL_CALL_SUCCEEDED: ToolCallStatus.SUCCEEDED,
                    TraceEventType.TOOL_CALL_FAILED: ToolCallStatus.FAILED,
                    TraceEventType.TOOL_CALL_TIMED_OUT: ToolCallStatus.TIMED_OUT,
                    TraceEventType.TOOL_CALL_INTERRUPTED: (ToolCallStatus.INTERRUPTED),
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
                        "user_outcome": expectations.expected_outcome,
                        "stop_reason": expectations.expected_stop_reason,
                    }
                )
            events.append(TraceEvent(**values))
    return tuple(events)


def _synthetic_message(
    expectations: EvalCaseExpectations,
    observation: OrderObservation | None,
) -> str:
    if expectations.expected_response_policy == "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE":
        return "未找到可访问的订单，请核对订单号后重试。"
    if expectations.expected_response_policy == "FIXED_SAFE_PROCESSING_ERROR":
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

    async def execute_case(
        self,
        *,
        case: EvalCaseArtifact,
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
        script = ARTIFACTS.script_by_ref(scripted_provider.model_script_ref)
        expectations = build_authenticated_case_expectations(
            artifacts=ARTIFACTS,
            case=case,
            script=script,
        )
        request_output = await scripted_provider.propose_next_move(_request(case))
        if case.case_id == "E2E01-01":
            await scripted_provider.plan_presentation(_presentation_input())

        run_id = (
            RUN_ID if case.case_id == "E2E01-01" else _case_uuid(case.case_id, "run")
        )
        trace_ref = (
            TRACE_REF
            if case.case_id == "E2E01-01"
            else _case_uuid(case.case_id, "trace")
        )
        message_ref = request_output.message_ref
        conversation_id = _case_uuid(case.case_id, "conversation")
        binding: InputBinding | None = None
        task: TaskRecord | None = None
        request_unit: RequestUnitRecord | None = None
        if expectations.expected_task_status is not None:
            binding = InputBinding(
                binding_id=_case_uuid(case.case_id, "binding"),
                name="order_id",
                normalized_value=expectations.expected_binding_order_id,
                authority=InputAuthority.USER_CLAIM,
                source_refs=(message_ref,),
                validation_status=InputValidationStatus.ACCEPTED,
                confirmed_by_user=True,
                created_at=NOW,
                updated_at=NOW,
            )
            task = TaskRecord(
                task_id=_case_uuid(case.case_id, "task"),
                owner_customer_id=expectations.trusted_customer_id,
                status=expectations.expected_task_status,
                state_version=expectations.expected_task_state_version,
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            )
            request_unit = RequestUnitRecord(
                request_unit_id=_case_uuid(case.case_id, "request-unit"),
                task_id=task.task_id,
                goal_text="查询指定订单状态",
                goal_source_refs=(message_ref,),
                input_binding_refs=(binding.binding_id,),
                status=expectations.expected_request_unit_status,
                state_version=(expectations.expected_request_unit_state_version),
                created_at=NOW,
                updated_at=NOW + timedelta(seconds=1),
            )

        context_ids = tuple(
            _case_uuid(case.case_id, f"context:{index}")
            for index in range(expectations.expected_model_calls)
        )
        model_call_ids = tuple(
            _case_uuid(case.case_id, f"model-call:{index}")
            for index in range(expectations.expected_model_calls)
        )
        gate: GateDecision | None = None
        if expectations.expected_gate_decision is not None:
            assert binding is not None
            failed_field_by_reason = {
                GateReasonCode.ARGUMENT_BINDING_MISMATCH: ("argument_binding_valid"),
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
            if expectations.expected_gate_reason is not None:
                checks[failed_field_by_reason[expectations.expected_gate_reason]] = (
                    False
                )
            gate = GateDecision(
                gate_decision_id=_case_uuid(case.case_id, "gate"),
                model_call_id=model_call_ids[0],
                context_manifest_id=context_ids[0],
                provider_tool_call_id="synthetic-provider-call",
                requested_provider_tool_name=(
                    expectations.expected_requested_tool_name
                ),
                resolved_canonical_tool_name=(
                    None
                    if expectations.expected_gate_reason
                    is GateReasonCode.TOOL_NOT_REGISTERED
                    else "get_order"
                ),
                argument_binding_refs=(binding.binding_id,),
                proposed_base_task_state_version=None,
                validated_task_state_version=1,
                decision=expectations.expected_gate_decision,
                reason_code=expectations.expected_gate_reason,
                decided_at=NOW,
                **checks,
            )

        observation: OrderObservation | None = None
        if expectations.expected_observations == 1:
            projection = _presentation_input().order_summary
            observation = OrderObservation(
                observation_id=_case_uuid(case.case_id, "observation"),
                source_tool="get_order",
                source_resource_ref=expectations.expected_binding_order_id,
                source_version="order-v7",
                normalized_type="ORDER_SUMMARY",
                normalized_value=projection,
                observed_at=NOW,
                recorded_at=NOW,
                visibility=ObservationVisibility.MODEL_VISIBLE,
            )
        tool_call: ToolCallRecord | None = None
        if expectations.expected_tool_calls == 1:
            assert (
                binding is not None
                and task is not None
                and request_unit is not None
                and gate is not None
            )
            status = expectations.expected_tool_call_status
            tool_call = ToolCallRecord(
                tool_call_id=_case_uuid(case.case_id, "tool-call"),
                run_id=run_id,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                model_call_id=model_call_ids[0],
                context_manifest_id=context_ids[0],
                gate_decision_id=gate.gate_decision_id,
                provider_tool_call_id="synthetic-provider-call",
                canonical_tool_name="get_order",
                tool_registry_version=(expectations.expected_tool_registry_version),
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
                    observation.observation_id if observation is not None else None
                ),
            )
        request_understanding_calls = (
            expectations.expected_model_calls
            - expectations.expected_presentation_model_calls
        )
        manifests = tuple(
            ContextManifest(
                context_manifest_id=context_id,
                run_id=run_id,
                model_call_id=model_call_ids[index],
                tool_registry_version=(expectations.expected_tool_registry_version),
                model_visible_toolset_hash=(
                    expectations.expected_model_visible_toolset_hash
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
            expectations=expectations,
            run_id=run_id,
            message_ref=message_ref,
            binding=binding,
            task=task,
            request_unit=request_unit,
            gate=gate,
            tool_call=tool_call,
            observation=observation,
            manifests=manifests,
        )
        self.traces.seed(trace_ref, initial_trace)
        observable_values: dict[str, object] = {
            "case_id": case.case_id,
            "http_status": expectations.expected_http_status,
            "user_outcome": expectations.expected_outcome,
            "response_policy": expectations.expected_response_policy,
            "ordinary_trace_shape": ordinary_trace_shape(initial_trace),
            "model_calls": expectations.expected_model_calls,
        }
        observable_values.update(self.observable_overrides)
        observable = SafeCaseObservable(**observable_values)
        evidence_values: dict[str, object] = {
            "case_id": case.case_id,
            "observed_outcome": expectations.expected_outcome,
            "trace_ref": trace_ref,
            "trace_events": initial_trace,
            "safe_observable": observable,
            "run_record": AgentRunRecord(
                run_id=run_id,
                conversation_id=conversation_id,
                status=expectations.expected_run_status,
                provider_lane="offline_gate",
                started_at=NOW,
                completed_at=NOW + timedelta(seconds=1),
                stop_reason=expectations.expected_stop_reason,
            ),
            "agent_result": AgentRunResult(
                run_id=run_id,
                outcome=expectations.expected_outcome,
                message=_synthetic_message(expectations, observation),
            ),
            "conversation_records": (
                ConversationRecord(
                    schema_version="conversation_record.p0.v1",
                    conversation_id=conversation_id,
                    owner_customer_id=expectations.trusted_customer_id,
                    created_at=NOW,
                ),
            ),
            "message_records": (
                MessageRecord(
                    schema_version="message_record.p0.v1",
                    message_id=message_ref,
                    conversation_id=conversation_id,
                    direction=MessageDirection.USER,
                    content=expectations.expected_message_content,
                    received_at=NOW,
                ),
            ),
            "request_understanding_output": request_output,
            "input_bindings": (binding,) if binding is not None else (),
            "task_records": (task,) if task is not None else (),
            "request_units": ((request_unit,) if request_unit is not None else ()),
            "gate_decisions": (gate,) if gate is not None else (),
            "tool_calls": (tool_call,) if tool_call is not None else (),
            "observations": ((observation,) if observation is not None else ()),
            "context_manifests": manifests,
            "model_visible_toolset_artifacts": (
                ModelVisibleToolsetArtifact(
                    model_visible_toolset_hash=(
                        expectations.expected_model_visible_toolset_hash
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
        evidence = EvalEvidence(**evidence_values)
        return EvalCaseSutResult(
            evidence=evidence,
            safe_observable=observable,
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
    timeline = traces.timeline if traces is not None else []
    traces = traces or InMemoryTraceCallbacks(timeline)
    port = port or InMemoryResultPort(timeline)
    traces.timeline = timeline
    port.timeline = timeline
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

    harness, _sut, traces, port = _harness(
        traces=traces,
        port=port,
        grader_runner=recording_grader,
    )
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
    assert timeline[0].startswith("grade:SchemaGrader")
    assert timeline[-4:] == [
        "trace_append",
        "trace_reload",
        "grade:TraceCompletenessGrader",
        "result_append",
    ]
    final_trace = traces.events_by_ref[TRACE_REF]
    assert [event.event_type for event in final_trace].count(
        TraceEventType.EVAL_CASE_GRADED
    ) == 1


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
    harness, _sut, _traces, port = _harness()
    first = _run(harness)
    second = _run(harness)

    assert first.results == second.results
    assert len(port.results) == 1
    assert port.events.count("result_append") == 2


def test_incremented_attempt_is_appended_under_a_distinct_identity() -> None:
    harness, _sut, _traces, port = _harness()
    first = _run(harness, attempt=1)
    second = _run(harness, attempt=2)

    assert first.results[0].attempt == 1
    assert second.results[0].attempt == 2
    assert len(port.results) == 2


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
