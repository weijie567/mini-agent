import pickle
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import get_type_hints
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field, ValidationError

import mini_agent.application.records as application_records_module
from mini_agent.application.records import (
    AcceptedOrderSearchQueryBindingReadClosure,
    AgentRunCommand,
    AgentRunResult,
    AppendInitialToolAttemptV2Command,
    AppendToolAttemptV2Command,
    ApplyContinuationInputBindingV2Command,
    ApplyOrderCandidateSelectionV2Command,
    ApplyOrderCandidateSelectionV3Command,
    ApplyOrderSearchOutcomeV2Command,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConversationRecord,
    ConversationTaskLinkRecord,
    ContinuationInputBindingReadClosure,
    Cycle2ControlPurpose,
    Cycle2CurrentSessionTaskClosure,
    Cycle2DispatchFenceWriteResult,
    Cycle2ExactRunEvidenceClosure,
    Cycle2ObservationSourceEdge,
    Cycle2ReadDispatchGrant,
    Cycle2RunBudgetPolicyEvidence,
    Cycle2WriteResult,
    CreateInitialTaskGraphV2Command,
    CreateRunCommand,
    CreateRequestUnitCommand,
    CreateRunTaskLinkCommand,
    CreateTaskCommand,
    CreateToolCallCommand,
    CreateToolCallV2Command,
    DispatchToolCallCommand,
    CriticalFailureCode,
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderResult,
    EvalGraderReasonCode,
    EvalGraderStatus,
    EvalLatencySummary,
    EvalResultRecord,
    EvalResultStatus,
    EvalUsageSummary,
    EvalVersionManifest,
    ExactRunEvidenceClosure,
    FinalizeRunCommand,
    AppendRecoveredToolAttemptV2Command,
    FinalizeBudgetExhaustedToolRecoveryV2Command,
    FinalizeCreatedToolRecoveryV2Command,
    FinalizeStateInvalidatedToolRecoveryV2Command,
    FinalizeSupersededRunV2Command,
    FinalizeToolCallCommand,
    FinalizeToolAttemptV2Command,
    FinalizeUnfinishedToolRecoveryV2Command,
    InterruptToolCallForRecoveryCommand,
    InitialToolCallV2ReadClosure,
    IssuedSelectedTargetRef,
    MarkRunIncompleteForRecoveryCommand,
    MessageDirection,
    MessageRecord,
    ObservationWriteResult,
    OrderCandidateSelectionReadClosure,
    OrderSearchCurrentReadClosure,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    SaveShipmentAssessmentV2Command,
    SaveShipmentObservationV2Command,
    SaveInputBindingCommand,
    SaveObservationCommand,
    SaveRequestUnderstandingV2AcceptedCommand,
    SaveRequestUnderstandingV2NoTaskCommand,
    SaveOrderObservationV2Command,
    TaskRecoveryAggregate,
    ShipmentAssessmentReadClosure,
    ShipmentNotReceivedClaimReadClosure,
    SupersededRunReadClosure,
    SupersededRunFinalizationEvidenceV2,
    SupersededRunInvalidationKind,
    ToolCallRecoveryAggregate,
    ToolRetryRecoveryDecisionRecordV2,
    ToolRetryRecoveryReadClosureV2,
    TransitionRunCommand,
    TrustedOwnerScope,
    build_order_candidate_selection_v2_command,
    build_order_candidate_selection_v3_command,
)
from mini_agent.core.common import ContractVisibility
from mini_agent.core.control_gateway import (
    Cycle2AcceptedBindingFacts,
    Cycle2GatewayBudgetFacts,
    Cycle2GatewayCandidate,
    Cycle2GatewayLoadedClosure,
    Cycle2GatewayProgressSnapshot,
    Cycle2TargetObservationFacts,
    Cycle2VerifiedOrderTargetFacts,
    build_cycle2_authorized_tool_command,
    evaluate_cycle2_control_gateway,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import (
    ContextManifest,
    ObservationVisibility,
    OrderObservation,
    SearchObservationCandidateTargetBinding,
    SearchOrdersObservation,
    SearchOrdersObservationCandidate,
    SearchOrdersObservationValue,
    ShipmentObservation,
    TaskStateRefAndVersion,
    TokenCounts,
    VersionedRecordRef,
)
from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderResult,
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.order_search import (
    OrderCandidateMatchingItem,
    OrderCandidatePublicSummary,
)
from mini_agent.core.request_understanding import (
    Cycle2ContinuationRequestUnderstandingOutputV2,
    Cycle2ContinuationTaskDeltaCandidateV2,
    Cycle2InputCandidate,
    InputAuthority,
    InputSourceKind,
    ModelVisibleTaskSummary,
    QueryContextualizationCandidateV2,
    RequestUnderstandingInput,
    TaskDeltaOperation,
)
from mini_agent.core.request_processing import (
    Cycle2ContinuationDecisionV3,
    Cycle2ContinuationIdentityAllocationV3,
    Cycle2OrdinalClaimPreparation,
    Cycle2OrdinalSelectionRejectionReason,
    reject_cycle2_ordinal_selection,
    reduce_cycle2_continuation_task_delta,
)
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    CandidateRejectionReasonCode,
    CandidateValidationDecision,
    CandidateValidationRecordV2,
    DurableInputCandidateV2,
    DurableQueryContextualizationCandidateV2,
    DurableTaskDeltaCandidateV2,
    InputBinding,
    InputBindingV2,
    InputValidationStatus,
    ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION,
    OrderCandidateAutoTargetRecord,
    OrderCandidateSelectionRecord,
    OrderCandidateSelectionRequest,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
    compute_order_candidate_set_version,
)
from mini_agent.core.tool_system import (
    AuthorizedToolCommandV2,
    Cycle2ToolName,
    GateDecision,
    GateDecisionV2,
    GateDecisionValue,
    GateReasonCode,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    ToolRetryDecision,
    ToolRecoveryDecision,
    ToolRecoveryDisposition,
    ToolTimeoutPhase,
    build_cycle2_registry_snapshot,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
    project_cycle2_budget_exhausted_recovery_terminal,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReason,
    StopReasonV2,
    TimingAndUsageSummary,
    TraceEvent,
    TraceEventV2,
    TraceEventType,
)
from mini_agent.core.shipment import (
    GetShipmentOutcome,
    GetShipmentResult,
    ShipmentAssessment,
    ShipmentEventCode,
    ShipmentStatus,
    ShipmentSummaryProjection,
    assess_shipment,
)

UTC_NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
NON_UTC_NOW = UTC_NOW.astimezone(timezone(timedelta(hours=8)))
SCHEMA_VERSION = "application-records-v1"


def _conversation(**updates: object) -> ConversationRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": uuid4(),
        "owner_customer_id": "customer-A",
        "created_at": UTC_NOW,
    }
    values.update(updates)
    return ConversationRecord(**values)


def _message(**updates: object) -> MessageRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "message_id": uuid4(),
        "conversation_id": uuid4(),
        "direction": MessageDirection.USER,
        "content": "查订单 O-1001",
        "received_at": UTC_NOW,
    }
    values.update(updates)
    return MessageRecord(**values)


def _conversation_task_link(
    **updates: object,
) -> ConversationTaskLinkRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": uuid4(),
        "task_id": uuid4(),
        "link_reason": "CURRENT_MESSAGE_ACCEPTED_DELTA",
        "linked_at": UTC_NOW,
        "ended_at": None,
    }
    values.update(updates)
    return ConversationTaskLinkRecord(**values)


def _run_task_link(**updates: object) -> RunTaskLinkRecord:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid4(),
        "task_id": uuid4(),
        "base_task_state_version": 1,
        "result_task_state_version": None,
    }
    values.update(updates)
    return RunTaskLinkRecord(**values)


def _run(**updates: object) -> AgentRunRecord:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "conversation_id": uuid4(),
        "status": AgentRunStatus.CREATED,
        "provider_lane": "scripted",
        "started_at": UTC_NOW,
    }
    values.update(updates)
    return AgentRunRecord(**values)


def _project_run(
    record: AgentRunRecord,
    **updates: object,
) -> AgentRunRecord:
    values = record.model_dump()
    values.update(updates)
    return AgentRunRecord(**values)


def _task(**updates: object) -> TaskRecord:
    values: dict[str, object] = {
        "task_id": uuid4(),
        "owner_customer_id": "customer-A",
        "status": TaskStatus.ACTIVE,
        "state_version": 1,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }
    values.update(updates)
    return TaskRecord(**values)


def _request_unit(**updates: object) -> RequestUnitRecord:
    values: dict[str, object] = {
        "request_unit_id": uuid4(),
        "task_id": uuid4(),
        "goal_text": "查询订单",
        "goal_source_refs": (uuid4(),),
        "input_binding_refs": (uuid4(),),
        "status": TaskStatus.ACTIVE,
        "state_version": 1,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }
    values.update(updates)
    return RequestUnitRecord(**values)


def _tool_call(
    *,
    status: ToolCallStatus,
    attempt_count: int,
    tool_call_id: UUID | None = None,
    effect: ToolEffect = ToolEffect.READ,
    finished_at: datetime | None = None,
    failure_code: str | None = None,
    interruption_reason: str | None = None,
    result_ref: UUID | None = None,
) -> ToolCallRecord:
    return ToolCallRecord(
        tool_call_id=tool_call_id or uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name="get_order",
        tool_registry_version="e2e01-thin-tools-v1",
        validated_task_state_version=1,
        argument_binding_refs=(uuid4(),),
        effect=effect,
        attempt_count=attempt_count,
        status=status,
        started_at=UTC_NOW,
        finished_at=finished_at,
        failure_code=failure_code,
        interruption_reason=interruption_reason,
        result_ref=result_ref,
    )


def _project_tool_call(
    record: ToolCallRecord,
    **updates: object,
) -> ToolCallRecord:
    values = record.model_dump()
    values.update(updates)
    return ToolCallRecord(**values)


def _customer_context(customer_id: str = "customer-A") -> CustomerContext:
    return CustomerContext(
        subject_ref=f"subject-{customer_id}",
        customer_id=customer_id,
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=UTC_NOW,
        session_ref_hash=f"safe-session-{customer_id}",
    )


def _owner_scope(customer_id: str = "customer-A") -> TrustedOwnerScope:
    return TrustedOwnerScope.from_customer_context(_customer_context(customer_id))


def _minimal_cycle2_exact_run_evidence() -> Cycle2ExactRunEvidenceClosure:
    conversation = _conversation()
    run_id = uuid4()
    run = AgentRunRecordV2(
        run_id=run_id,
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="offline_cycle2",
        started_at=UTC_NOW,
    )
    return Cycle2ExactRunEvidenceClosure(
        owner_scope=_owner_scope(),
        conversation_record=conversation,
        run_record=run,
        message_records=(
            _message(
                conversation_id=conversation.conversation_id,
                received_at=UTC_NOW,
            ),
        ),
        run_task_link_records=(),
        task_records=(),
        request_unit_records=(),
        input_binding_records=(),
        trace_records=(
            TraceEventV2(
                trace_event_id=uuid4(),
                event_type=TraceEventType.RUN_STARTED,
                occurred_at=UTC_NOW,
                run_id=run_id,
            ),
        ),
        terminal_result=None,
    )


def test_cycle2_exact_run_evidence_exposes_complete_expectation_free_families() -> None:
    closure = _minimal_cycle2_exact_run_evidence()
    expected_families = {
        "supporting_run_records",
        "task_state_transition_records",
        "candidate_set_records",
        "candidate_selection_records",
        "order_observation_records",
        "search_observation_records",
        "shipment_observation_records",
        "observation_source_edges",
        "shipment_assessment_records",
        "tool_call_records",
        "recovery_decision_records",
        "superseded_run_finalizations",
        "context_manifest_records",
        "model_visible_toolset_artifacts",
    }

    assert expected_families <= set(Cycle2ExactRunEvidenceClosure.model_fields)
    assert all(getattr(closure, field_name) == () for field_name in expected_families)
    assert not {
        "case_id",
        "fixture_ref",
        "predicates",
        "grader_results",
        "assertions_pass",
    }.intersection(Cycle2ExactRunEvidenceClosure.model_fields)


def test_cycle2_exact_run_evidence_rejects_raw_or_cross_run_children() -> None:
    closure = _minimal_cycle2_exact_run_evidence()
    closure_values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }
    raw_trace = closure.trace_records[0].model_copy(
        update={"event_type": TraceEventType.RUN_STARTED.value}
    )
    foreign_manifest = ContextManifest(
        context_manifest_id=uuid4(),
        run_id=uuid4(),
        model_call_id=uuid4(),
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        model_visible_toolset_hash=build_cycle2_registry_snapshot().model_visible_toolset_hash,
        selected_message_refs=(),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=UTC_NOW,
    )

    with pytest.raises(ValidationError, match="trace_records"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **closure_values,
                "trace_records": (raw_trace,),
            }
        )
    with pytest.raises(ValidationError, match="manifest root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **closure_values,
                "context_manifest_records": (foreign_manifest,),
            }
        )


def _cycle2_exact_run_evidence_with_task() -> Cycle2ExactRunEvidenceClosure:
    closure = _minimal_cycle2_exact_run_evidence()
    message = closure.message_records[0]
    task = _task()
    binding = _input_binding_v2(
        source_refs=(message.message_id,),
    )
    unit = _request_unit(
        task_id=task.task_id,
        goal_source_refs=(message.message_id,),
        input_binding_refs=(binding.binding_id,),
    )
    return Cycle2ExactRunEvidenceClosure(
        **{
            **{
                field_name: getattr(closure, field_name)
                for field_name in Cycle2ExactRunEvidenceClosure.model_fields
            },
            "run_task_link_records": (
                RunTaskLinkRecordV2(
                    run_id=closure.run_record.run_id,
                    task_id=task.task_id,
                ),
            ),
            "task_records": (task,),
            "request_unit_records": (unit,),
            "input_binding_records": (binding,),
        }
    )


def _cycle2_oa10_exact_run_evidence() -> Cycle2ExactRunEvidenceClosure:
    baseline = _cycle2_exact_run_evidence_with_task()
    task = baseline.task_records[0]
    unit = baseline.request_unit_records[0]
    link = baseline.run_task_link_records[0]
    completed_at = UTC_NOW + timedelta(seconds=1)
    run = _c2_project(
        baseline.run_record,
        status=AgentRunStatusV2.SUPERSEDED,
        completed_at=completed_at,
        stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
    )
    stopped = TraceEventV2(
        trace_event_id=uuid4(),
        event_type=TraceEventType.RUN_STOPPED,
        occurred_at=completed_at,
        run_id=run.run_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        user_outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
    )
    finalization = SupersededRunFinalizationEvidenceV2(
        superseded_run_record=run,
        no_result_link_record=link,
        run_stopped_trace_record=stopped,
    )
    return Cycle2ExactRunEvidenceClosure(
        **{
            **{
                field_name: getattr(baseline, field_name)
                for field_name in Cycle2ExactRunEvidenceClosure.model_fields
            },
            "run_record": run,
            "superseded_run_finalizations": (finalization,),
            "trace_records": (*baseline.trace_records, stopped),
        }
    )


def test_oa10_durable_projection_has_only_exact_persisted_triplet() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    projection = closure.superseded_run_finalizations[0]

    assert set(SupersededRunFinalizationEvidenceV2.model_fields) == {
        "superseded_run_record",
        "no_result_link_record",
        "run_stopped_trace_record",
    }
    assert projection.superseded_run_record == closure.run_record
    assert projection.no_result_link_record in closure.run_task_link_records
    assert projection.run_stopped_trace_record in closure.trace_records
    assert not {
        "loaded_closure",
        "replacement_run_record",
        "trusted_current_evidence_at",
        "fixture_ref",
        "expectations",
    }.intersection(SupersededRunFinalizationEvidenceV2.model_fields)


def test_oa10_durable_projection_rejects_contradictory_triplet() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    projection = closure.superseded_run_finalizations[0]
    run = projection.superseded_run_record
    link = projection.no_result_link_record
    trace = projection.run_stopped_trace_record
    completed_run = AgentRunRecordV2(
        **{
            **run.model_dump(mode="python"),
            "status": AgentRunStatusV2.COMPLETED,
            "stop_reason": StopReasonV2.GOAL_COMPLETED,
        }
    )
    invalid_children = (
        {"superseded_run_record": completed_run},
        {"no_result_link_record": _c2_project(link, run_id=uuid4())},
        {
            "no_result_link_record": _c2_project(
                link,
                result_task_state_version=1,
            )
        },
        {"run_stopped_trace_record": _c2_project(trace, run_id=uuid4())},
        {"run_stopped_trace_record": _c2_project(trace, task_id=uuid4())},
        {
            "run_stopped_trace_record": _c2_project(
                trace,
                occurred_at=trace.occurred_at + timedelta(microseconds=1),
            )
        },
        {
            "run_stopped_trace_record": _c2_project(
                trace,
                message_ref=uuid4(),
            )
        },
    )
    values = {
        field_name: getattr(projection, field_name)
        for field_name in SupersededRunFinalizationEvidenceV2.model_fields
    }

    for updates in invalid_children:
        with pytest.raises(ValidationError, match="OA-10"):
            SupersededRunFinalizationEvidenceV2(**{**values, **updates})


def test_oa10_durable_projection_rejects_raw_nested_records() -> None:
    projection = (
        _cycle2_oa10_exact_run_evidence().superseded_run_finalizations[0]
    )

    with pytest.raises(ValidationError, match="exact AgentRunRecordV2"):
        SupersededRunFinalizationEvidenceV2(
            superseded_run_record=projection.superseded_run_record.model_dump(
                mode="python"
            ),
            no_result_link_record=projection.no_result_link_record,
            run_stopped_trace_record=projection.run_stopped_trace_record,
        )


def test_oa10_exact_run_evidence_requires_one_rooted_projection() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    projection = closure.superseded_run_finalizations[0]
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="exactly one finalization"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "superseded_run_finalizations": ()}
        )
    with pytest.raises(ValidationError, match="identities must be unique"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "superseded_run_finalizations": (projection, projection),
            }
        )
    foreign_run = _c2_project(projection.superseded_run_record, run_id=uuid4())
    foreign = SupersededRunFinalizationEvidenceV2(
        superseded_run_record=foreign_run,
        no_result_link_record=_c2_project(
            projection.no_result_link_record,
            run_id=foreign_run.run_id,
        ),
        run_stopped_trace_record=_c2_project(
            projection.run_stopped_trace_record,
            run_id=foreign_run.run_id,
        ),
    )
    with pytest.raises(ValidationError, match="finalization root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "superseded_run_finalizations": (foreign,)}
        )


def test_completed_exact_run_evidence_has_no_oa10_projection() -> None:
    conversation = _conversation()
    run_id = uuid4()
    completed_at = UTC_NOW + timedelta(seconds=1)
    run = AgentRunRecordV2(
        run_id=run_id,
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.COMPLETED,
        provider_lane="offline_cycle2",
        started_at=UTC_NOW,
        completed_at=completed_at,
        stop_reason=StopReasonV2.GOAL_COMPLETED,
    )
    result = AgentRunResult(
        run_id=run_id,
        outcome=AgentOutcome.COMPLETED,
        message="已完成。",
    )
    user_message = _message(
        conversation_id=conversation.conversation_id,
    )
    assistant_message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=uuid4(),
        conversation_id=conversation.conversation_id,
        direction=MessageDirection.ASSISTANT,
        content=result.message,
        received_at=completed_at,
    )
    closure = Cycle2ExactRunEvidenceClosure(
        owner_scope=_owner_scope(),
        conversation_record=conversation,
        run_record=run,
        message_records=(user_message, assistant_message),
        run_task_link_records=(),
        task_records=(),
        request_unit_records=(),
        input_binding_records=(),
        trace_records=(
            TraceEventV2(
                trace_event_id=uuid4(),
                event_type=TraceEventType.RUN_STOPPED,
                occurred_at=completed_at,
                run_id=run_id,
                user_outcome=AgentOutcome.COMPLETED,
                stop_reason=StopReasonV2.GOAL_COMPLETED,
            ),
        ),
        terminal_result=result,
    )

    assert closure.superseded_run_finalizations == ()
    oa10 = _cycle2_oa10_exact_run_evidence().superseded_run_finalizations[0]
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }
    with pytest.raises(ValidationError, match="cannot carry a finalization"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "superseded_run_finalizations": (oa10,)}
        )


def test_oa10_exact_run_evidence_rejects_terminal_result() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="output or state mutation"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "terminal_result": AgentRunResult(
                    run_id=closure.run_record.run_id,
                    outcome=AgentOutcome.BLOCKED,
                    message="不应存在的 OA-10 结果。",
                ),
            }
        )


def test_oa10_exact_run_evidence_rejects_assistant_message() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="output or state mutation"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "message_records": (
                    *closure.message_records,
                    MessageRecord(
                        schema_version="message_record.p0.v1",
                        message_id=uuid4(),
                        conversation_id=closure.conversation_record.conversation_id,
                        direction=MessageDirection.ASSISTANT,
                        content="不应存在的 OA-10 assistant Message。",
                        received_at=closure.run_record.completed_at,
                    ),
                ),
            }
        )


def test_oa10_exact_run_evidence_rejects_response_rendered_trace() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="output or state mutation"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "trace_records": (
                    *closure.trace_records,
                    TraceEventV2(
                        trace_event_id=uuid4(),
                        event_type=TraceEventType.RESPONSE_RENDERED,
                        occurred_at=closure.run_record.completed_at,
                        run_id=closure.run_record.run_id,
                        presentation_plan_ref=uuid4(),
                    ),
                ),
            }
        )


def test_oa10_exact_run_evidence_rejects_task_state_transition() -> None:
    closure = _cycle2_oa10_exact_run_evidence()
    task = closure.task_records[0]
    unit = closure.request_unit_records[0]
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="output or state mutation"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "task_state_transition_records": (
                    TaskStateTransition(
                        task_id=task.task_id,
                        request_unit_id=unit.request_unit_id,
                        from_status=task.status,
                        to_status=TaskStatus.WAITING_USER,
                        base_state_version=task.state_version,
                        result_state_version=task.state_version + 1,
                        reason_ref=closure.message_records[0].message_id,
                        changed_at=closure.run_record.completed_at,
                    ),
                ),
            }
        )


def test_cycle2_exact_run_evidence_rejects_cross_paired_task_unit_child() -> None:
    closure = _cycle2_exact_run_evidence_with_task()
    message = closure.message_records[0]
    second_task = _task(
        status=TaskStatus.WAITING_USER,
        state_version=2,
        updated_at=UTC_NOW + timedelta(seconds=1),
    )
    second_binding = _input_binding_v2(source_refs=(message.message_id,))
    second_unit = _request_unit(
        task_id=second_task.task_id,
        goal_source_refs=(message.message_id,),
        input_binding_refs=(second_binding.binding_id,),
        status=TaskStatus.WAITING_USER,
        state_version=2,
        updated_at=UTC_NOW + timedelta(seconds=1),
    )
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="transition root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "run_task_link_records": (
                    *closure.run_task_link_records,
                    RunTaskLinkRecordV2(
                        run_id=closure.run_record.run_id,
                        task_id=second_task.task_id,
                    ),
                ),
                "task_records": (*closure.task_records, second_task),
                "request_unit_records": (
                    *closure.request_unit_records,
                    second_unit,
                ),
                "input_binding_records": (
                    *closure.input_binding_records,
                    second_binding,
                ),
                "task_state_transition_records": (
                    TaskStateTransition(
                        task_id=closure.task_records[0].task_id,
                        request_unit_id=second_unit.request_unit_id,
                        from_status=TaskStatus.ACTIVE,
                        to_status=TaskStatus.WAITING_USER,
                        base_state_version=1,
                        result_state_version=2,
                        reason_ref=message.message_id,
                        changed_at=UTC_NOW + timedelta(seconds=1),
                    ),
                ),
            }
        )


def test_cycle2_exact_run_evidence_rejects_order_observation_without_source_edge() -> None:
    closure = _cycle2_exact_run_evidence_with_task()
    observation = _observation()
    unit = closure.request_unit_records[0].model_copy(
        update={"observation_refs": (observation.observation_id,)}
    )
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="Observation source edge mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "request_unit_records": (unit,),
                "order_observation_records": (observation,),
            }
        )


def test_cycle2_exact_run_evidence_rejects_unresolved_candidate_graphs() -> None:
    owner, task, unit, source, observation, candidate_set, query_ref, ordinal_ref = (
        _c2_search_graph()
    )
    conversation = _conversation(
        conversation_id=candidate_set.conversation_id,
        owner_customer_id=owner.customer_id,
    )
    message = _message(
        message_id=unit.goal_source_refs[0],
        conversation_id=conversation.conversation_id,
    )
    run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="offline_cycle2",
        started_at=UTC_NOW,
    )
    query_binding = _input_binding_v2(
        binding_id=query_ref,
        name="product_description",
        normalized_value="示例鞋",
        source_refs=(message.message_id,),
    )
    ordinal_binding = _input_binding_v2(
        binding_id=ordinal_ref,
        name="candidate_ordinal",
        normalized_value=1,
        source_refs=(message.message_id,),
    )
    rooted_unit = _c2_project(
        unit,
        input_binding_refs=(query_ref, ordinal_ref),
        observation_refs=(observation.observation_id,),
    )
    selected = candidate_set.ordered_candidates[0]
    selection = OrderCandidateSelectionRecord(
        selection_id=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        conversation_id=conversation.conversation_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        source_message_ref=message.message_id,
        ordinal_input_binding_ref=ordinal_ref,
        candidate_set_ref=candidate_set.candidate_set_id,
        candidate_set_version=candidate_set.candidate_set_version,
        search_observation_ref=observation.observation_id,
        search_observation_record_schema_version=observation.record_schema_version,
        observation_candidate_ref=selected.observation_candidate_ref,
        candidate_source_version=selected.candidate_source_version,
        owner_scoped_order_target_ref=(
            observation.candidate_target_bindings[0].owner_scoped_order_ref
        ),
        selected_target_ref=str(uuid4()),
        base_task_state_version=3,
        result_task_state_version=4,
        selected_at=UTC_NOW + timedelta(seconds=2),
    )
    snapshot = build_cycle2_registry_snapshot()
    artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        provider_visible_tool_specs=snapshot.provider_visible_toolset,
    )
    source_manifest = ContextManifest(
        context_manifest_id=source.context_manifest_id,
        run_id=source.run_id,
        model_call_id=source.model_call_id,
        tool_registry_version=source.tool_registry_version,
        model_visible_toolset_hash=artifact.model_visible_toolset_hash,
        selected_message_refs=(message.message_id,),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=UTC_NOW,
    )
    supporting_run = AgentRunRecordV2(
        run_id=source.run_id,
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.COMPLETED,
        provider_lane="offline_cycle2",
        started_at=UTC_NOW,
        completed_at=source.finished_at,
        stop_reason=StopReasonV2.CANDIDATE_CLARIFICATION_REQUIRED,
    )
    source_edge = Cycle2ObservationSourceEdge(
        observation_ref=observation.observation_id,
        source_tool_call_id=source.tool_call_id,
        source_run_id=source.run_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
    )
    common = {
        "owner_scope": owner,
        "conversation_record": conversation,
        "run_record": run,
        "supporting_run_records": (supporting_run,),
        "message_records": (message,),
        "run_task_link_records": (
            RunTaskLinkRecordV2(run_id=run.run_id, task_id=task.task_id),
            RunTaskLinkRecordV2(
                run_id=source.run_id,
                task_id=task.task_id,
            ),
        ),
        "task_records": (task,),
        "request_unit_records": (rooted_unit,),
        "input_binding_records": (query_binding, ordinal_binding),
        "search_observation_records": (observation,),
        "observation_source_edges": (source_edge,),
        "tool_call_records": (source,),
        "context_manifest_records": (source_manifest,),
        "model_visible_toolset_artifacts": (artifact,),
        "trace_records": (
            TraceEventV2(
                trace_event_id=uuid4(),
                event_type=TraceEventType.RUN_STARTED,
                occurred_at=UTC_NOW,
                run_id=run.run_id,
            ),
        ),
    }

    historical = Cycle2ExactRunEvidenceClosure(
        **{
            **common,
            "candidate_set_records": (candidate_set,),
        }
    )
    assert historical.supporting_run_records == (supporting_run,)

    with pytest.raises(ValidationError, match="CandidateSet ToolCall mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **common,
                "supporting_run_records": (),
                "run_task_link_records": common["run_task_link_records"][:1],
                "candidate_set_records": (candidate_set,),
                "observation_source_edges": (),
                "tool_call_records": (),
                "context_manifest_records": (),
                "model_visible_toolset_artifacts": (),
            }
        )

    foreign_observation = observation.model_copy(
        update={"observation_id": uuid4()}
    )
    foreign_observation_unit = _c2_project(
        rooted_unit,
        observation_refs=(foreign_observation.observation_id,),
    )
    with pytest.raises(ValidationError, match="CandidateSet graph mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **common,
                "request_unit_records": (foreign_observation_unit,),
                "search_observation_records": (foreign_observation,),
                "candidate_set_records": (candidate_set,),
            }
        )
    with pytest.raises(ValidationError, match="Selection graph mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **common,
                "candidate_selection_records": (selection,),
            }
        )


def _input_binding(**updates: object) -> InputBinding:
    values: dict[str, object] = {
        "binding_id": uuid4(),
        "name": "order_id",
        "normalized_value": "O-1001",
        "authority": InputAuthority.USER_CLAIM,
        "source_refs": (uuid4(),),
        "validation_status": InputValidationStatus.ACCEPTED,
        "confirmed_by_user": True,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }
    values.update(updates)
    return InputBinding(**values)


def _input_binding_v2(**updates: object) -> InputBindingV2:
    values: dict[str, object] = {
        "binding_id": uuid4(),
        "name": "order_id",
        "normalized_value": "O-1001",
        "authority": InputAuthority.USER_CLAIM,
        "source_refs": (uuid4(),),
        "validation_status": InputValidationStatus.ACCEPTED,
        "confirmed_by_user": True,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
        "supersedes": None,
    }
    values.update(updates)
    return InputBindingV2(**values)


def _task_transition(**updates: object) -> TaskStateTransition:
    values: dict[str, object] = {
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "from_status": TaskStatus.ACTIVE,
        "to_status": TaskStatus.WAITING_USER,
        "base_state_version": 1,
        "result_state_version": 2,
        "reason_ref": uuid4(),
        "changed_at": UTC_NOW + timedelta(milliseconds=1),
    }
    values.update(updates)
    return TaskStateTransition(**values)


def _observation(**updates: object) -> OrderObservation:
    values: dict[str, object] = {
        "observation_id": uuid4(),
        "source_tool": "get_order",
        "source_resource_ref": "O-1001",
        "source_version": "order-v1",
        "normalized_type": "ORDER_SUMMARY",
        "normalized_value": OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at=UTC_NOW,
            status_updated_at=UTC_NOW,
        ),
        "observed_at": UTC_NOW,
        "recorded_at": UTC_NOW,
        "visibility": ObservationVisibility.MODEL_VISIBLE,
    }
    values.update(updates)
    return OrderObservation(**values)


def _rebuild(instance: BaseModel, **updates: object) -> BaseModel:
    values = {
        field_name: getattr(instance, field_name)
        for field_name in type(instance).model_fields
    }
    values.update(updates)
    return type(instance)(**values)


def _assert_validation_error_is_sanitized(
    error: ValidationError,
    *forbidden_values: str,
) -> None:
    projections = (
        str(error),
        repr(error),
        repr(error.args),
        repr(error.errors()),
        error.json(),
    )
    for forbidden_value in forbidden_values:
        assert all(forbidden_value not in projection for projection in projections)


_COMPLETED_TERMINAL_MATRIX = (
    (
        StopReason.GOAL_COMPLETED,
        True,
        AgentOutcome.COMPLETED,
        TaskStatus.COMPLETED,
    ),
    (
        StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
        True,
        AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        TaskStatus.COMPLETED,
    ),
    (
        StopReason.PROVIDER_PROTOCOL_ERROR,
        False,
        AgentOutcome.BLOCKED,
        None,
    ),
    (
        StopReason.PROVIDER_PROTOCOL_ERROR,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.INPUT_INVALID,
        False,
        AgentOutcome.BLOCKED,
        None,
    ),
    (
        StopReason.GATE_REJECTED,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.ORDER_SERVICE_UNAVAILABLE,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.PRESENTATION_PLAN_REJECTED,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
    (
        StopReason.RENDERER_INVARIANT_FAILED,
        True,
        AgentOutcome.BLOCKED,
        TaskStatus.BLOCKED,
    ),
)


def _terminal_task_transition(
    *,
    task_id: UUID,
    request_unit_id: UUID,
    terminal_status: TaskStatus,
    base_state_version: int = 1,
    changed_at: datetime = UTC_NOW + timedelta(milliseconds=1),
) -> ApplyTaskTransitionCommand:
    expected_task = _task(
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=base_state_version,
    )
    expected_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=base_state_version,
    )
    next_task = _rebuild(
        expected_task,
        status=terminal_status,
        state_version=base_state_version + 1,
        updated_at=changed_at,
    )
    next_unit = _rebuild(
        expected_unit,
        status=terminal_status,
        state_version=base_state_version + 1,
        updated_at=changed_at,
    )
    transition = _task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
        from_status=TaskStatus.ACTIVE,
        to_status=terminal_status,
        base_state_version=base_state_version,
        result_state_version=base_state_version + 1,
        changed_at=changed_at,
    )
    return ApplyTaskTransitionCommand(
        expected_task_record=expected_task,
        next_task_record=next_task,
        expected_request_unit_record=expected_unit,
        next_request_unit_record=next_unit,
        task_state_transition=transition,
    )


def _terminal_trace_events(
    *,
    run_id: UUID,
    stop_reason: StopReason,
    outcome: AgentOutcome,
    completed_at: datetime,
    task_transition: ApplyTaskTransitionCommand | None,
) -> tuple[TraceEvent, ...]:
    task_events = (
        (
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TASK_STATE_CHANGED,
                occurred_at=task_transition.task_state_transition.changed_at,
                run_id=run_id,
                task_id=task_transition.next_task_record.task_id,
                request_unit_id=(
                    task_transition.next_request_unit_record.request_unit_id
                ),
            ),
        )
        if task_transition is not None
        else ()
    )
    return (
        *task_events,
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=run_id,
            user_outcome=outcome,
            stop_reason=stop_reason,
        ),
    )


def _completed_finalization(
    *,
    stop_reason: StopReason = StopReason.GOAL_COMPLETED,
    outcome: AgentOutcome = AgentOutcome.COMPLETED,
    with_task: bool = True,
    task_status: TaskStatus | None = TaskStatus.COMPLETED,
    active_link_base_state_version: int | None = 1,
    transition_base_state_version: int = 1,
) -> FinalizeRunCommand:
    if with_task != (task_status is not None):
        raise ValueError("task_status must be present exactly when with_task is true")
    run_id = uuid4()
    conversation_id = uuid4()
    completed_at = UTC_NOW + timedelta(milliseconds=2)
    running = _run(
        run_id=run_id,
        conversation_id=conversation_id,
        status=AgentRunStatus.RUNNING,
    )
    terminal = _project_run(
        running,
        status=AgentRunStatus.COMPLETED,
        completed_at=completed_at,
        stop_reason=stop_reason,
    )
    terminal_result = AgentRunResult(
        run_id=run_id,
        outcome=outcome,
        message="这是经过确定性映射的终态回复。",
    )
    assistant_message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=uuid4(),
        conversation_id=conversation_id,
        direction=MessageDirection.ASSISTANT,
        content=terminal_result.message,
        received_at=completed_at,
    )

    if with_task:
        task_id = uuid4()
        request_unit_id = uuid4()
        assert task_status is not None
        task_transition = _terminal_task_transition(
            task_id=task_id,
            request_unit_id=request_unit_id,
            terminal_status=task_status,
            base_state_version=transition_base_state_version,
        )
        active_link = _run_task_link(
            run_id=run_id,
            task_id=task_id,
            base_task_state_version=active_link_base_state_version,
        )
        expected_active_links = (active_link,)
        terminal_links = (
            _rebuild(
                active_link,
                result_task_state_version=(
                    task_transition.next_task_record.state_version
                ),
            ),
        )
        result_task_records = (task_transition.next_task_record,)
    else:
        task_transition = None
        expected_active_links = ()
        terminal_links = ()
        result_task_records = ()

    return FinalizeRunCommand(
        expected_active_record=running,
        terminal_record=terminal,
        expected_active_links=expected_active_links,
        terminal_links=terminal_links,
        result_task_records=result_task_records,
        task_transition=task_transition,
        terminal_result=terminal_result,
        assistant_message=assistant_message,
        terminal_trace_events=_terminal_trace_events(
            run_id=run_id,
            stop_reason=stop_reason,
            outcome=outcome,
            completed_at=completed_at,
            task_transition=task_transition,
        ),
    )


def _failed_finalization(
    *,
    with_task: bool = True,
    active_link_base_state_version: int | None = 1,
    current_task_state_version: int = 1,
) -> FinalizeRunCommand:
    run_id = uuid4()
    running = _run(
        run_id=run_id,
        conversation_id=uuid4(),
        status=AgentRunStatus.RUNNING,
    )
    terminal = _project_run(
        running,
        status=AgentRunStatus.FAILED,
        completed_at=UTC_NOW + timedelta(milliseconds=2),
        stop_reason=None,
    )
    if with_task:
        task_id = uuid4()
        current_task = _task(
            task_id=task_id,
            status=TaskStatus.ACTIVE,
            state_version=current_task_state_version,
        )
        active_link = _run_task_link(
            run_id=run_id,
            task_id=task_id,
            base_task_state_version=active_link_base_state_version,
        )
        expected_active_links = (active_link,)
        terminal_links = (
            _rebuild(
                active_link,
                result_task_state_version=current_task_state_version,
            ),
        )
        result_task_records = (current_task,)
    else:
        expected_active_links = ()
        terminal_links = ()
        result_task_records = ()
    return FinalizeRunCommand(
        expected_active_record=running,
        terminal_record=terminal,
        expected_active_links=expected_active_links,
        terminal_links=terminal_links,
        result_task_records=result_task_records,
        task_transition=None,
        terminal_result=None,
        assistant_message=None,
        terminal_trace_events=(),
    )


def _updated_terminal_trace_events(
    command: FinalizeRunCommand,
    selected_event_type: TraceEventType,
    **updates: object,
) -> tuple[TraceEvent, ...]:
    events = list(command.terminal_trace_events)
    event_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type is selected_event_type
    )
    events[event_index] = events[event_index].model_copy(update=updates)
    return tuple(events)


def _recovery_trace_events(
    *,
    run_transition: MarkRunIncompleteForRecoveryCommand,
    task_transitions: tuple[ApplyTaskTransitionCommand, ...],
    tool_call_transitions: tuple[InterruptToolCallForRecoveryCommand, ...],
) -> tuple[TraceEvent, ...]:
    run_id = run_transition.expected_active_record.run_id
    return (
        TraceEvent(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=run_transition.incomplete_record.completed_at,
            run_id=run_id,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        ),
        *(
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TASK_STATE_CHANGED,
                occurred_at=transition.task_state_transition.changed_at,
                run_id=run_id,
                task_id=transition.next_task_record.task_id,
                request_unit_id=transition.next_request_unit_record.request_unit_id,
            )
            for transition in task_transitions
        ),
        *(
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TOOL_CALL_INTERRUPTED,
                occurred_at=transition.interrupted_record.finished_at,
                run_id=run_id,
                tool_call_id=transition.interrupted_record.tool_call_id,
                tool_call_terminal_status=ToolCallStatus.INTERRUPTED,
            )
            for transition in tool_call_transitions
        ),
    )


_RECOVERY_TRACE_COMMON_FIELDS = frozenset(
    {
        "trace_event_id",
        "event_type",
        "occurred_at",
        "run_id",
    }
)
_RECOVERY_TRACE_ALLOWED_FIELDS = {
    TraceEventType.RUN_STOPPED: _RECOVERY_TRACE_COMMON_FIELDS
    | {"user_outcome", "stop_reason"},
    TraceEventType.TASK_STATE_CHANGED: _RECOVERY_TRACE_COMMON_FIELDS
    | {"task_id", "request_unit_id"},
    TraceEventType.TOOL_CALL_INTERRUPTED: _RECOVERY_TRACE_COMMON_FIELDS
    | {"tool_call_id", "tool_call_terminal_status"},
}
_RECOVERY_TRACE_CONTAMINATION_CASES = tuple(
    (event_type, field_name)
    for event_type, allowed_fields in _RECOVERY_TRACE_ALLOWED_FIELDS.items()
    for field_name in sorted(set(TraceEvent.model_fields) - allowed_fields)
)
_TERMINAL_TRACE_COMMON_FIELDS = frozenset(
    {
        "trace_event_id",
        "event_type",
        "occurred_at",
        "run_id",
    }
)
_TERMINAL_TRACE_ALLOWED_FIELDS = {
    TraceEventType.TASK_STATE_CHANGED: _TERMINAL_TRACE_COMMON_FIELDS
    | {"task_id", "request_unit_id"},
    TraceEventType.RUN_STOPPED: _TERMINAL_TRACE_COMMON_FIELDS
    | {"user_outcome", "stop_reason"},
}
_TERMINAL_TRACE_CONTAMINATION_CASES = tuple(
    (event_type, field_name)
    for event_type, allowed_fields in _TERMINAL_TRACE_ALLOWED_FIELDS.items()
    for field_name in sorted(set(TraceEvent.model_fields) - allowed_fields)
)


def _non_empty_trace_optional_value(field_name: str) -> object:
    values: dict[str, object] = {
        "case_id": "E2E01-01",
        "message_ref": uuid4(),
        "accepted_delta_ref": uuid4(),
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "input_binding_ref": uuid4(),
        "model_call_id": uuid4(),
        "model_call_purpose": "REQUEST_UNDERSTANDING",
        "context_manifest_id": uuid4(),
        "provider_name": "scripted",
        "model_snapshot": "scripted-v1",
        "tool_registry_version": "e2e01-thin-tools-v1",
        "model_visible_toolset_hash": f"sha256:{'0' * 64}",
        "next_move_kind": "CALL_TOOL",
        "requested_tool_name": "get_order",
        "proposed_base_task_state_version": 1,
        "validated_task_state_version": 1,
        "argument_binding_refs": (uuid4(),),
        "gate_decision": GateDecisionValue.ACCEPT,
        "gate_reason_code": GateReasonCode.TOOL_NOT_REGISTERED,
        "tool_call_id": uuid4(),
        "tool_call_terminal_status": ToolCallStatus.FAILED,
        "safe_tool_outcome": ToolResultOutcome.SYSTEM_FAILURE,
        "observation_ref": uuid4(),
        "presentation_plan_ref": uuid4(),
        "user_outcome": AgentOutcome.BLOCKED,
        "stop_reason": StopReason.PROCESS_RESTART_DETECTED,
        "timing_and_usage_summary": TimingAndUsageSummary(duration_ms=1),
    }
    return values[field_name]


def _updated_recovery_trace_events(
    command: ApplyRestartRecoveryCommand,
    selected_event_type: TraceEventType,
    **updates: object,
) -> tuple[TraceEvent, ...]:
    events = list(command.recovery_trace_events)
    event_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type is selected_event_type
    )
    events[event_index] = events[event_index].model_copy(update=updates)
    return tuple(events)


def _initial_v2_graph() -> CreateInitialTaskGraphV2Command:
    conversation_id = uuid4()
    recent_message_id = uuid4()
    current_message_id = uuid4()
    run_id = uuid4()
    task_id = uuid4()
    request_unit_id = uuid4()
    binding_id = uuid4()
    accepted_delta_id = uuid4()
    candidate_id = uuid4()
    initial_at = UTC_NOW
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
        conversation_id=conversation_id,
        created_at=initial_at - timedelta(seconds=2),
    )
    recent_message = _message(
        schema_version="message_record.p0.v1",
        message_id=recent_message_id,
        conversation_id=conversation_id,
        direction=MessageDirection.ASSISTANT,
        content="你上次询问的是订单状态。",
        received_at=initial_at - timedelta(seconds=1),
    )
    current_message = _message(
        schema_version="message_record.p0.v1",
        message_id=current_message_id,
        conversation_id=conversation_id,
        content="查订单 o-1001",
        received_at=initial_at - timedelta(milliseconds=1),
    )
    run = _run(
        run_id=run_id,
        conversation_id=conversation_id,
        status=AgentRunStatus.RUNNING,
        started_at=initial_at - timedelta(milliseconds=1),
    )
    candidate = _durable_evidence_candidate(
        candidate_id=candidate_id,
        message=current_message,
        order_id="o-1001",
    )
    record = RequestUnderstandingRecordV2(
        request_understanding_record_id=uuid4(),
        run_id=run_id,
        message_ref=current_message_id,
        schema_version="request_understanding_record.p0.v2",
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-thin-v2",
        contextualization=DurableQueryContextualizationCandidateV2(
            text="结合最近消息查询当前订单",
            resolved_reference_candidates=(),
            uncertainties=(),
            source_message_refs=(recent_message_id, current_message_id),
        ),
        task_delta_candidates=(candidate,),
        candidate_validation=(
            CandidateValidationRecordV2(
                candidate_ref=candidate_id,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        accepted_delta_refs=(accepted_delta_id,),
        proposed_base_task_state_version=None,
        validated_task_state_version=1,
        next_move_candidate_ref=uuid4(),
        created_at=initial_at,
    )
    accepted_delta = AcceptedTaskDeltaV2(
        accepted_delta_id=accepted_delta_id,
        candidate_ref=candidate_id,
        message_ref=current_message_id,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text=candidate.goal_patch,
        input_binding_refs=(binding_id,),
        accepted_at=initial_at,
        task_id=task_id,
        base_task_state_version=None,
        result_task_state_version=1,
    )
    binding = _input_binding(
        binding_id=binding_id,
        normalized_value="O-1001",
        source_refs=(current_message_id,),
        created_at=initial_at,
        updated_at=initial_at,
        supersedes=None,
    )
    task = _task(
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=initial_at,
        updated_at=initial_at,
        last_outcome_ref=None,
    )
    request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        goal_text=candidate.goal_patch,
        goal_source_refs=(current_message_id,),
        contextualization_ref=None,
        constraint_refs=(),
        dependency_refs=(),
        input_binding_refs=(binding_id,),
        open_questions=(),
        observation_refs=(),
        evidence_binding_refs=(),
        pending_action_ref=None,
        result_refs=(),
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=initial_at,
        updated_at=initial_at,
    )
    return CreateInitialTaskGraphV2Command(
        owner_scope=_owner_scope(),
        expected_conversation_record=conversation,
        expected_message_records=(recent_message, current_message),
        expected_active_run_record=run,
        request_understanding=SaveRequestUnderstandingV2AcceptedCommand(
            record=record,
            accepted_delta=accepted_delta,
        ),
        initial_task=CreateTaskCommand(initial_record=task),
        initial_request_unit=CreateRequestUnitCommand(
            initial_record=request_unit
        ),
        input_binding=SaveInputBindingCommand(
            record=binding,
            request_unit_id=request_unit_id,
        ),
        conversation_task_link=ConversationTaskLinkRecord(
            schema_version="conversation_task_link_record.p0.v1",
            conversation_id=conversation_id,
            task_id=task_id,
            link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
            linked_at=initial_at,
            ended_at=None,
        ),
        run_task_link=CreateRunTaskLinkCommand(
            active_record=RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=run_id,
                task_id=task_id,
                base_task_state_version=None,
                result_task_state_version=None,
            )
        ),
    )


def _initial_v2_graph_exact_run_evidence(
    *,
    candidate_value: str = "o-1001",
    binding_value: str = "O-1001",
    include_extra_binding_source: bool = False,
) -> ExactRunEvidenceClosure:
    graph = _initial_v2_graph()
    record = graph.request_understanding.record
    candidate = record.task_delta_candidates[0]
    candidate_input = _rebuild(
        candidate.input_candidates[0],
        candidate_value=candidate_value,
    )
    projected_candidate = _rebuild(
        candidate,
        input_candidates=(candidate_input,),
    )
    projected_record = _rebuild(
        record,
        task_delta_candidates=(projected_candidate,),
    )
    projected_binding = _rebuild(
        graph.input_binding.record,
        normalized_value=binding_value,
        source_refs=(
            (
                *graph.input_binding.record.source_refs,
                graph.expected_message_records[0].message_id,
            )
            if include_extra_binding_source
            else graph.input_binding.record.source_refs
        ),
    )
    return ExactRunEvidenceClosure(
        conversation_record=graph.expected_conversation_record,
        run_record=graph.expected_active_run_record,
        message_records=graph.expected_message_records,
        request_understanding_record=projected_record,
        accepted_task_deltas=(
            graph.request_understanding.accepted_delta,
        ),
        input_binding_records=(projected_binding,),
        task_records=(graph.initial_task.initial_record,),
        task_state_transitions=(),
        request_unit_records=(graph.initial_request_unit.initial_record,),
        conversation_task_links=(graph.conversation_task_link,),
        run_task_links=(graph.run_task_link.active_record,),
        gate_decisions=(),
        tool_calls=(),
        tool_attempts=(),
        observation_records=(),
        context_manifests=(),
        model_visible_toolset_artifacts=(),
        trace_events=(),
    )


def _v2_no_task_command(
    *,
    zero_candidates: bool = False,
) -> SaveRequestUnderstandingV2NoTaskCommand:
    graph = _initial_v2_graph()
    accepted = graph.request_understanding
    record = accepted.record
    if zero_candidates:
        candidates: tuple[DurableTaskDeltaCandidateV2, ...] = ()
        decisions: tuple[CandidateValidationRecordV2, ...] = ()
    else:
        candidates = record.task_delta_candidates
        decisions = (
            CandidateValidationRecordV2(
                candidate_ref=candidates[0].candidate_id,
                decision=CandidateValidationDecision.REJECT,
                reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
            ),
        )
    no_task_record = _rebuild(
        record,
        task_delta_candidates=candidates,
        candidate_validation=decisions,
        accepted_delta_refs=(),
        proposed_base_task_state_version=None,
        validated_task_state_version=None,
        next_move_candidate_ref=None,
    )
    return SaveRequestUnderstandingV2NoTaskCommand(
        owner_scope=graph.owner_scope,
        expected_conversation_record=graph.expected_conversation_record,
        expected_message_records=graph.expected_message_records,
        expected_active_run_record=graph.expected_active_run_record,
        request_understanding_record=no_task_record,
    )


def _task_transition_command() -> ApplyTaskTransitionCommand:
    task_id = uuid4()
    request_unit_id = uuid4()
    expected_task = _task(task_id=task_id)
    expected_request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        status=TaskStatus.ACTIVE,
        state_version=1,
    )
    next_task = _task(
        task_id=task_id,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        created_at=expected_task.created_at,
        updated_at=UTC_NOW + timedelta(milliseconds=1),
    )
    next_request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        goal_text=expected_request_unit.goal_text,
        goal_source_refs=expected_request_unit.goal_source_refs,
        input_binding_refs=expected_request_unit.input_binding_refs,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        created_at=expected_request_unit.created_at,
        updated_at=UTC_NOW + timedelta(milliseconds=1),
    )
    transition = _task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
    )
    return ApplyTaskTransitionCommand(
        expected_task_record=expected_task,
        next_task_record=next_task,
        expected_request_unit_record=expected_request_unit,
        next_request_unit_record=next_request_unit,
        task_state_transition=transition,
    )


def _restart_recovery_closure() -> RestartRecoveryClosure:
    conversation_id = uuid4()
    run_id = uuid4()
    task_id = uuid4()
    request_unit_id = uuid4()
    tool_call_id = uuid4()
    transition = _task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
    )
    task = _task(
        task_id=task_id,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        updated_at=transition.changed_at,
    )
    request_unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        status=TaskStatus.WAITING_USER,
        state_version=2,
        updated_at=transition.changed_at,
    )
    tool_call = _tool_call(
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
        tool_call_id=tool_call_id,
    ).model_copy(
        update={
            "run_id": run_id,
            "task_id": task_id,
            "request_unit_id": request_unit_id,
            "validated_task_state_version": task.state_version,
            "argument_binding_refs": request_unit.input_binding_refs,
        }
    )
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=_conversation(
            schema_version="conversation_record.p0.v1",
            conversation_id=conversation_id,
        ),
        active_run_record=_run(
            run_id=run_id,
            conversation_id=conversation_id,
            status=AgentRunStatus.RUNNING,
        ),
        conversation_task_links=(
            ConversationTaskLinkRecord(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=conversation_id,
                task_id=task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=UTC_NOW,
            ),
        ),
        run_task_links=(
            RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=run_id,
                task_id=task_id,
                base_task_state_version=1,
                result_task_state_version=None,
            ),
        ),
        task_aggregates=(
            TaskRecoveryAggregate(
                task_record=task,
                task_state_transitions=(transition,),
            ),
        ),
        request_unit_records=(request_unit,),
        tool_call_aggregates=(
            ToolCallRecoveryAggregate(
                tool_call_record=tool_call,
                tool_attempt_records=(
                    ToolAttemptRecord(
                        tool_call_id=tool_call_id,
                        attempt_no=1,
                        started_at=UTC_NOW,
                    ),
                ),
            ),
        ),
    )


def _created_restart_recovery_closure() -> RestartRecoveryClosure:
    conversation_id = uuid4()
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
        conversation_id=conversation_id,
    )
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=conversation,
        active_run_record=_run(
            conversation_id=conversation_id,
            status=AgentRunStatus.CREATED,
        ),
        conversation_task_links=(),
        run_task_links=(),
        task_aggregates=(),
        request_unit_records=(),
        tool_call_aggregates=(),
    )


def _created_restart_recovery_command() -> ApplyRestartRecoveryCommand:
    closure = _created_restart_recovery_closure()
    active_run = closure.active_run_record
    run_transition = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=active_run,
        incomplete_record=_project_run(
            active_run,
            status=AgentRunStatus.INCOMPLETE,
            completed_at=UTC_NOW + timedelta(milliseconds=1),
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        ),
    )
    return ApplyRestartRecoveryCommand(
        expected_closure=closure,
        run_transition=run_transition,
        tool_call_transitions=(),
        task_transitions=(),
        terminal_run_task_links=(),
        recovery_trace_events=_recovery_trace_events(
            run_transition=run_transition,
            task_transitions=(),
            tool_call_transitions=(),
        ),
    )


def _restart_recovery_command() -> ApplyRestartRecoveryCommand:
    closure = _restart_recovery_closure()
    run = closure.active_run_record
    task = closure.task_aggregates[0].task_record
    request_unit = closure.request_unit_records[0]
    tool_call = closure.tool_call_aggregates[0].tool_call_record
    completed_at = UTC_NOW + timedelta(milliseconds=2)
    task_transition = ApplyTaskTransitionCommand(
        expected_task_record=task,
        next_task_record=_task(
            task_id=task.task_id,
            owner_customer_id=task.owner_customer_id,
            status=TaskStatus.BLOCKED,
            state_version=3,
            created_at=task.created_at,
            updated_at=completed_at,
            last_outcome_ref=task.last_outcome_ref,
        ),
        expected_request_unit_record=request_unit,
        next_request_unit_record=_request_unit(
            request_unit_id=request_unit.request_unit_id,
            task_id=request_unit.task_id,
            goal_text=request_unit.goal_text,
            goal_source_refs=request_unit.goal_source_refs,
            contextualization_ref=request_unit.contextualization_ref,
            constraint_refs=request_unit.constraint_refs,
            dependency_refs=request_unit.dependency_refs,
            input_binding_refs=request_unit.input_binding_refs,
            open_questions=request_unit.open_questions,
            observation_refs=request_unit.observation_refs,
            evidence_binding_refs=request_unit.evidence_binding_refs,
            pending_action_ref=request_unit.pending_action_ref,
            result_refs=request_unit.result_refs,
            status=TaskStatus.BLOCKED,
            state_version=3,
            created_at=request_unit.created_at,
            updated_at=completed_at,
        ),
        task_state_transition=_task_transition(
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            from_status=TaskStatus.WAITING_USER,
            to_status=TaskStatus.BLOCKED,
            base_state_version=2,
            result_state_version=3,
            changed_at=completed_at,
        ),
    )
    run_transition = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=run,
        incomplete_record=_project_run(
            run,
            status=AgentRunStatus.INCOMPLETE,
            completed_at=completed_at,
            stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        ),
    )
    tool_call_transitions = (
        InterruptToolCallForRecoveryCommand(
            active_record=tool_call,
            interrupted_record=_project_tool_call(
                tool_call,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=completed_at,
                interruption_reason="PROCESS_RESTART_DETECTED",
            ),
        ),
    )
    return ApplyRestartRecoveryCommand(
        expected_closure=closure,
        run_transition=run_transition,
        tool_call_transitions=tool_call_transitions,
        task_transitions=(task_transition,),
        terminal_run_task_links=(
            _rebuild(
                closure.run_task_links[0],
                result_task_state_version=3,
            ),
        ),
        recovery_trace_events=_recovery_trace_events(
            run_transition=run_transition,
            task_transitions=(task_transition,),
            tool_call_transitions=tool_call_transitions,
        ),
    )


def _valid_command_records() -> tuple[BaseModel, ...]:
    created_run = _run()
    running_run = _project_run(created_run, status=AgentRunStatus.RUNNING)
    incomplete_run = _project_run(
        running_run,
        status=AgentRunStatus.INCOMPLETE,
        completed_at=UTC_NOW + timedelta(milliseconds=1),
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )

    created = _tool_call(status=ToolCallStatus.CREATED, attempt_count=0)

    dispatch_id = uuid4()
    expected_created = _tool_call(
        status=ToolCallStatus.CREATED,
        attempt_count=0,
        tool_call_id=dispatch_id,
    )
    running = _project_tool_call(
        expected_created,
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
    )
    started_attempt = ToolAttemptRecord(
        tool_call_id=dispatch_id,
        attempt_no=1,
        started_at=UTC_NOW,
    )

    final_id = uuid4()
    finished_at = UTC_NOW + timedelta(milliseconds=1)
    expected_running = _tool_call(
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
        tool_call_id=final_id,
    )
    terminal = _project_tool_call(
        expected_running,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=finished_at,
        result_ref=uuid4(),
    )
    finalized_attempt = ToolAttemptRecord(
        tool_call_id=final_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=finished_at,
        outcome=ToolResultOutcome.SUCCESS,
    )

    interrupted = _project_tool_call(
        created,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=finished_at,
        interruption_reason="PROCESS_RESTART_DETECTED",
    )
    return (
        CreateRunCommand(created_record=created_run),
        TransitionRunCommand(
            expected_active_record=created_run,
            next_record=running_run,
        ),
        MarkRunIncompleteForRecoveryCommand(
            expected_active_record=running_run,
            incomplete_record=incomplete_run,
        ),
        CreateTaskCommand(initial_record=_task()),
        CreateRequestUnitCommand(initial_record=_request_unit()),
        CreateRunTaskLinkCommand(active_record=_run_task_link()),
        CreateToolCallCommand(created_record=created),
        DispatchToolCallCommand(
            expected_created_record=expected_created,
            running_record=running,
            started_attempt=started_attempt,
        ),
        FinalizeToolCallCommand(
            expected_running_record=expected_running,
            expected_started_attempt=ToolAttemptRecord(
                tool_call_id=final_id,
                attempt_no=1,
                started_at=UTC_NOW,
            ),
            terminal_record=terminal,
            finalized_attempt=finalized_attempt,
        ),
        InterruptToolCallForRecoveryCommand(
            active_record=created,
            interrupted_record=interrupted,
        ),
    )


def _version_manifest(**updates: object) -> EvalVersionManifest:
    values: dict[str, object] = {
        "dataset_version": "e2e01-thin-dataset-v1",
        "candidate_version": "candidate-source-revision",
        "fixture_versions": ("e2e01-thin-fixture-v1",),
        "model_config_version": "scripted-provider-v1",
        "runtime_version": "runtime-source-revision",
    }
    values.update(updates)
    return EvalVersionManifest(**values)


def _eval_execution_failure(**updates: object) -> EvalExecutionFailureRecord:
    values: dict[str, object] = {
        "schema_version": "eval-execution-failure-v1",
        "eval_run_id": uuid4(),
        "case_id": "E2E01-01",
        "lane": "offline_gate",
        "attempt": 1,
        "failure_phase": EvalExecutionFailurePhase.TRACE_PERSISTENCE,
        "safe_error_code": EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        "diagnostic_ref": uuid4(),
        "trace_ref": None,
        "version_manifest": _version_manifest(),
        "occurred_at": UTC_NOW,
    }
    values.update(updates)
    return EvalExecutionFailureRecord(**values)


def _passing_grader() -> EvalGraderResult:
    return EvalGraderResult(
        grader_name="IdentityBoundaryGrader",
        status=EvalGraderStatus.PASS,
    )


def _eval_result(**updates: object) -> EvalResultRecord:
    values: dict[str, object] = {
        "schema_version": "eval-result-v1",
        "eval_run_id": uuid4(),
        "case_id": "E2E01-01",
        "lane": "offline_gate",
        "attempt": 1,
        "status": EvalResultStatus.PASS,
        "grader_results": (_passing_grader(),),
        "critical_failures": (),
        "observed_outcome": AgentOutcome.COMPLETED,
        "trace_ref": uuid4(),
        "version_manifest": _version_manifest(),
        "latency_summary": EvalLatencySummary(total_duration_ms=12),
        "usage_summary": EvalUsageSummary(input_tokens=20, output_tokens=8),
        "completed_at": UTC_NOW,
    }
    values.update(updates)
    return EvalResultRecord(**values)


def test_persisted_records_are_strict_frozen_and_extra_forbid() -> None:
    record_types = (
        ConversationRecord,
        MessageRecord,
        ConversationTaskLinkRecord,
        RunTaskLinkRecord,
        EvalExecutionFailureRecord,
        EvalResultRecord,
    )
    for record_type in record_types:
        assert record_type.model_config["strict"] is True
        assert record_type.model_config["frozen"] is True
        assert record_type.model_config["extra"] == "forbid"
        assert record_type.model_json_schema()["additionalProperties"] is False

    with pytest.raises(ValidationError, match="UUID"):
        _conversation(conversation_id=str(uuid4()))
    with pytest.raises(ValidationError, match="Extra inputs"):
        ConversationRecord(
            schema_version=SCHEMA_VERSION,
            conversation_id=uuid4(),
            owner_customer_id="customer-A",
            created_at=UTC_NOW,
            unexpected="forbidden",
        )

    frozen = _conversation()
    with pytest.raises(ValidationError, match="frozen"):
        frozen.owner_customer_id = "customer-B"


def test_nested_eval_and_write_commands_are_strict_frozen_and_extra_forbid() -> None:
    instances = (
        _passing_grader(),
        _version_manifest(),
        EvalLatencySummary(total_duration_ms=12),
        EvalUsageSummary(input_tokens=20, output_tokens=8),
        *_valid_command_records(),
    )

    for instance in instances:
        record_type = type(instance)
        assert record_type.model_config["strict"] is True
        assert record_type.model_config["frozen"] is True
        assert record_type.model_config["extra"] == "forbid"
        assert record_type.model_json_schema()["additionalProperties"] is False

        first_field = next(iter(record_type.model_fields))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(instance, first_field, getattr(instance, first_field))

        values = {
            field_name: getattr(instance, field_name)
            for field_name in record_type.model_fields
        }
        with pytest.raises(ValidationError, match="Extra inputs"):
            record_type.model_validate({**values, "unexpected": "forbidden"})


@pytest.mark.parametrize(
    "factory",
    (
        _conversation,
        _message,
        _conversation_task_link,
        _run_task_link,
        _eval_execution_failure,
        _eval_result,
    ),
)
def test_persisted_records_require_non_empty_schema_version(factory: object) -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        factory(schema_version="")


def test_conversation_owner_and_raw_message_are_runtime_private() -> None:
    assert ConversationRecord.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert MessageRecord.contract_visibility is ContractVisibility.RUNTIME_PRIVATE

    for record_type in (
        ConversationTaskLinkRecord,
        RunTaskLinkRecord,
        EvalExecutionFailureRecord,
        EvalResultRecord,
    ):
        assert record_type.contract_visibility is ContractVisibility.AUDIT_ONLY
        assert record_type.contract_visibility not in {
            ContractVisibility.MODEL_VISIBLE,
            ContractVisibility.USER_VISIBLE,
        }


@pytest.mark.parametrize("timestamp", (datetime(2026, 7, 26, 8, 0), NON_UTC_NOW))
def test_record_timestamps_reject_naive_and_non_utc_values(
    timestamp: datetime,
) -> None:
    with pytest.raises(ValidationError, match="UTC"):
        _conversation(created_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _message(received_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _conversation_task_link(linked_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _conversation_task_link(ended_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _eval_execution_failure(occurred_at=timestamp)
    with pytest.raises(ValidationError, match="UTC"):
        _eval_result(completed_at=timestamp)


def test_trusted_owner_scope_is_a_minimal_application_projection() -> None:
    context = CustomerContext(
        subject_ref="subject-A",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=UTC_NOW,
        session_ref_hash="safe-session-hash",
    )
    owner_scope = TrustedOwnerScope.from_customer_context(context)

    assert owner_scope.customer_id == "customer-A"
    assert set(type(owner_scope).model_fields) == {"customer_id"}
    assert TrustedOwnerScope.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert TrustedOwnerScope.model_config["strict"] is True
    assert TrustedOwnerScope.model_config["frozen"] is True
    assert TrustedOwnerScope.model_config["extra"] == "forbid"
    assert "subject_ref" not in owner_scope.model_dump()
    assert "auth_scopes" not in owner_scope.model_dump()
    assert "authenticated_at" not in owner_scope.model_dump()
    assert "session_ref_hash" not in owner_scope.model_dump()
    with pytest.raises(ValidationError, match="derived from CustomerContext"):
        TrustedOwnerScope(customer_id="customer-A")
    with pytest.raises(ValidationError, match="derived from CustomerContext"):
        TrustedOwnerScope.model_validate(
            {"customer_id": "customer-B"},
            context={"customer_context": context},
        )
    with pytest.raises(ValidationError, match="derived from CustomerContext"):
        TrustedOwnerScope.model_validate(
            {
                "customer_id": "customer-A",
                "session_ref_hash": "must-not-cross-port",
            },
            context={"customer_context": context},
        )
    forged = TrustedOwnerScope.model_construct(
        customer_id="customer-A",
        _derivation_context=context,
    )
    with pytest.raises(ValueError, match="lacks CustomerContext derivation"):
        forged.require_trusted_derivation()
    malformed_context = CustomerContext.model_construct(customer_id="customer-A")
    with pytest.raises(ValueError, match="recursively canonical"):
        TrustedOwnerScope.from_customer_context(malformed_context)


def test_message_content_is_non_empty_and_bounded_at_4000_characters() -> None:
    assert len(_message(content="x" * 4000).content) == 4000
    with pytest.raises(ValidationError, match="at most 4000 characters"):
        _message(content="x" * 4001)
    with pytest.raises(ValidationError, match="at least 1 character"):
        _message(content="")


def test_conversation_task_link_lifecycle_is_ordered() -> None:
    active = _conversation_task_link()
    ended = _conversation_task_link(ended_at=UTC_NOW + timedelta(seconds=1))

    assert active.ended_at is None
    assert ended.ended_at is not None
    with pytest.raises(ValidationError, match="cannot precede"):
        _conversation_task_link(ended_at=UTC_NOW - timedelta(seconds=1))


def test_run_task_link_versions_cover_active_and_terminal_projections() -> None:
    active = _run_task_link(
        base_task_state_version=3,
        result_task_state_version=None,
    )
    terminal = _run_task_link(
        base_task_state_version=3,
        result_task_state_version=5,
    )
    new_task_terminal = _run_task_link(
        base_task_state_version=None,
        result_task_state_version=1,
    )

    assert active.result_task_state_version is None
    assert terminal.result_task_state_version == 5
    assert new_task_terminal.base_task_state_version is None
    with pytest.raises(ValidationError, match="cannot precede"):
        _run_task_link(
            base_task_state_version=3,
            result_task_state_version=2,
        )
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        _run_task_link(base_task_state_version=0)
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        _run_task_link(result_task_state_version=0)


def test_run_commands_freeze_insert_exact_start_and_recovery_claim() -> None:
    created = _run()
    running = _project_run(created, status=AgentRunStatus.RUNNING)
    completed_at = UTC_NOW + timedelta(milliseconds=1)
    incomplete = _project_run(
        running,
        status=AgentRunStatus.INCOMPLETE,
        completed_at=completed_at,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )

    assert CreateRunCommand(created_record=created).created_record.status is (
        AgentRunStatus.CREATED
    )
    assert (
        TransitionRunCommand(
            expected_active_record=created,
            next_record=running,
        ).next_record.status
        is AgentRunStatus.RUNNING
    )
    recovery = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=running,
        incomplete_record=incomplete,
    )
    assert recovery.incomplete_record.incomplete_reason is None
    with_reason = MarkRunIncompleteForRecoveryCommand(
        expected_active_record=running,
        incomplete_record=_project_run(
            incomplete,
            incomplete_reason="PROCESS_RESTART_DETECTED",
        ),
    )
    assert with_reason.incomplete_record.incomplete_reason == (
        "PROCESS_RESTART_DETECTED"
    )

    with pytest.raises(ValidationError, match="requires CREATED"):
        CreateRunCommand(created_record=running)
    with pytest.raises(ValidationError, match="change stable fields"):
        TransitionRunCommand(
            expected_active_record=created,
            next_record=_project_run(running, provider_lane="other-lane"),
        )
    with pytest.raises(ValidationError, match="expects CREATED"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=running,
        )
    with pytest.raises(ValidationError, match="expects CREATED"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=incomplete,
        )
    with pytest.raises(ValidationError, match="requires RUNNING"):
        TransitionRunCommand(
            expected_active_record=created,
            next_record=created,
        )
    with pytest.raises(ValidationError, match="incomplete_reason must be absent"):
        MarkRunIncompleteForRecoveryCommand(
            expected_active_record=running,
            incomplete_record=_project_run(
                incomplete,
                incomplete_reason="USER_CANCELLED",
            ),
        )
    with pytest.raises(ValidationError, match="cannot change stable fields"):
        MarkRunIncompleteForRecoveryCommand(
            expected_active_record=running,
            incomplete_record=_project_run(incomplete, conversation_id=uuid4()),
        )


def test_initial_write_commands_are_insert_only_version_one_projections() -> None:
    task = CreateTaskCommand(
        initial_record=_task(status=TaskStatus.WAITING_USER),
    )
    request_unit = CreateRequestUnitCommand(
        initial_record=_request_unit(status=TaskStatus.WAITING_USER),
    )
    link = CreateRunTaskLinkCommand(active_record=_run_task_link())

    assert task.initial_record.state_version == 1
    assert task.initial_record.status is TaskStatus.WAITING_USER
    assert request_unit.initial_record.state_version == 1
    assert request_unit.initial_record.status is TaskStatus.WAITING_USER
    assert link.active_record.result_task_state_version is None

    with pytest.raises(ValidationError, match="state_version = 1"):
        CreateTaskCommand(initial_record=_task(state_version=2))
    with pytest.raises(ValidationError, match="state_version = 1"):
        CreateRequestUnitCommand(initial_record=_request_unit(state_version=2))
    with pytest.raises(ValidationError, match="requires result_task_state_version"):
        CreateRunTaskLinkCommand(
            active_record=_run_task_link(result_task_state_version=2)
        )


def test_tool_create_and_dispatch_commands_freeze_the_durable_fence() -> None:
    created = _tool_call(status=ToolCallStatus.CREATED, attempt_count=0)
    running = _project_tool_call(
        created,
        status=ToolCallStatus.RUNNING,
        attempt_count=1,
    )
    attempt = ToolAttemptRecord(
        tool_call_id=created.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
    )

    create_command = CreateToolCallCommand(created_record=created)
    dispatch_command = DispatchToolCallCommand(
        expected_created_record=created,
        running_record=running,
        started_attempt=attempt,
    )
    assert create_command.created_record.status is ToolCallStatus.CREATED
    assert dispatch_command.running_record.attempt_count == 1
    assert dispatch_command.started_attempt.outcome is None

    with pytest.raises(ValidationError, match="requires CREATED"):
        CreateToolCallCommand(created_record=running)
    with pytest.raises(ValidationError, match="terminal or result"):
        CreateToolCallCommand(
            created_record=_project_tool_call(created, result_ref=uuid4())
        )
    with pytest.raises(ValidationError, match="immutable ToolCall"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=_project_tool_call(running, effect=ToolEffect.ACTION),
            started_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="ids must match"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=running,
            started_attempt=ToolAttemptRecord(
                tool_call_id=uuid4(),
                attempt_no=1,
                started_at=UTC_NOW,
            ),
        )
    with pytest.raises(ValidationError, match="first attempt only"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=_project_tool_call(running, attempt_count=2),
            started_attempt=ToolAttemptRecord(
                tool_call_id=created.tool_call_id,
                attempt_no=2,
                started_at=UTC_NOW,
            ),
        )
    with pytest.raises(ValidationError, match="unfinished attempt"):
        DispatchToolCallCommand(
            expected_created_record=created,
            running_record=running,
            started_attempt=ToolAttemptRecord(
                tool_call_id=created.tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )


def test_tool_finalize_command_freezes_expected_running_projection() -> None:
    running = _tool_call(status=ToolCallStatus.RUNNING, attempt_count=1)
    finished_at = UTC_NOW + timedelta(milliseconds=1)
    started_attempt = ToolAttemptRecord(
        tool_call_id=running.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
    )
    terminal = _project_tool_call(
        running,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=finished_at,
        result_ref=uuid4(),
    )
    attempt = ToolAttemptRecord(
        tool_call_id=running.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=finished_at,
        outcome=ToolResultOutcome.SUCCESS,
    )

    command = FinalizeToolCallCommand(
        expected_running_record=running,
        expected_started_attempt=started_attempt,
        terminal_record=terminal,
        finalized_attempt=attempt,
    )
    assert command.terminal_record.status is ToolCallStatus.SUCCEEDED
    assert command.finalized_attempt.outcome is ToolResultOutcome.SUCCESS

    with pytest.raises(ValidationError, match="must remain unfinished"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=attempt,
            terminal_record=terminal,
            finalized_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="immutable fields"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=_project_tool_call(terminal, effect=ToolEffect.ACTION),
            finalized_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="status and attempt outcome"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=_project_tool_call(
                terminal,
                status=ToolCallStatus.FAILED,
                result_ref=None,
            ),
            finalized_attempt=attempt,
        )
    with pytest.raises(ValidationError, match="timestamps must match"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=terminal,
            finalized_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW,
                finished_at=finished_at + timedelta(milliseconds=1),
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )
    with pytest.raises(ValidationError, match="preserve started attempt"):
        FinalizeToolCallCommand(
            expected_running_record=running,
            expected_started_attempt=started_attempt,
            terminal_record=terminal,
            finalized_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW + timedelta(microseconds=1),
                finished_at=finished_at,
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )
    with pytest.raises(ValidationError, match="first"):
        FinalizeToolCallCommand(
            expected_running_record=_project_tool_call(
                running,
                attempt_count=2,
            ),
            expected_started_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=2,
                started_at=UTC_NOW,
            ),
            terminal_record=_project_tool_call(
                terminal,
                attempt_count=2,
            ),
            finalized_attempt=ToolAttemptRecord(
                tool_call_id=running.tool_call_id,
                attempt_no=2,
                started_at=UTC_NOW,
                finished_at=finished_at,
                outcome=ToolResultOutcome.SUCCESS,
            ),
        )


def test_restart_tool_command_preserves_identity_attempt_and_action_effect() -> None:
    created_action = _tool_call(
        status=ToolCallStatus.CREATED,
        attempt_count=0,
        effect=ToolEffect.ACTION,
    )
    interrupted = _project_tool_call(
        created_action,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=UTC_NOW + timedelta(milliseconds=1),
        interruption_reason="PROCESS_RESTART_DETECTED",
    )
    command = InterruptToolCallForRecoveryCommand(
        active_record=created_action,
        interrupted_record=interrupted,
    )

    assert command.active_record.attempt_count == 0
    assert command.interrupted_record.effect is ToolEffect.ACTION
    with pytest.raises(ValidationError, match="PROCESS_RESTART_DETECTED"):
        InterruptToolCallForRecoveryCommand(
            active_record=created_action,
            interrupted_record=_project_tool_call(
                interrupted,
                interruption_reason="USER_CANCELLED",
            ),
        )
    with pytest.raises(ValidationError, match="preserve ToolCall identity"):
        InterruptToolCallForRecoveryCommand(
            active_record=created_action,
            interrupted_record=_project_tool_call(
                interrupted,
                effect=ToolEffect.READ,
            ),
        )
    dirty_active = _project_tool_call(created_action, result_ref=uuid4())
    with pytest.raises(ValidationError, match="cannot carry failure or result"):
        InterruptToolCallForRecoveryCommand(
            active_record=dirty_active,
            interrupted_record=_project_tool_call(
                dirty_active,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
                interruption_reason="PROCESS_RESTART_DETECTED",
            ),
        )

    running_retry = _tool_call(
        status=ToolCallStatus.RUNNING,
        attempt_count=2,
    )
    with pytest.raises(ValidationError, match="does not accept retry"):
        InterruptToolCallForRecoveryCommand(
            active_record=running_retry,
            interrupted_record=_project_tool_call(
                running_retry,
                status=ToolCallStatus.INTERRUPTED,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
                interruption_reason="PROCESS_RESTART_DETECTED",
            ),
        )


def test_v2_no_task_command_accepts_zero_or_all_reject_exact_message_closure() -> None:
    all_reject = _v2_no_task_command()
    zero = _v2_no_task_command(zero_candidates=True)

    assert all_reject.request_understanding_record.accepted_delta_refs == ()
    assert all(
        decision.decision is CandidateValidationDecision.REJECT
        for decision in all_reject.request_understanding_record.candidate_validation
    )
    assert zero.request_understanding_record.task_delta_candidates == ()
    assert zero.request_understanding_record.candidate_validation == ()
    assert {
        message.message_id for message in all_reject.expected_message_records
    } == set(
        all_reject.request_understanding_record.contextualization.source_message_refs
    )
    assert not any(
        field_name
        in SaveRequestUnderstandingV2NoTaskCommand.model_fields
        for field_name in (
            "accepted_delta",
            "initial_task",
            "initial_request_unit",
            "input_binding",
            "next_move_candidate",
        )
    )


def test_v2_no_task_command_rejects_owner_root_message_and_task_effect_tamper() -> None:
    command = _v2_no_task_command()
    record = command.request_understanding_record
    current = next(
        message
        for message in command.expected_message_records
        if message.message_id == record.message_ref
    )
    recent = next(
        message
        for message in command.expected_message_records
        if message.message_id != record.message_ref
    )

    with pytest.raises(ValidationError, match="owner"):
        _rebuild(command, owner_scope=_owner_scope("customer-B"))
    with pytest.raises(ValidationError, match="exact referenced Message"):
        _rebuild(command, expected_message_records=(current,))
    with pytest.raises(ValidationError, match="exact referenced Message"):
        _rebuild(
            command,
            expected_message_records=(
                *command.expected_message_records,
                _message(
                    conversation_id=(
                        command.expected_conversation_record.conversation_id
                    )
                ),
            ),
        )
    with pytest.raises(ValidationError, match="unique"):
        _rebuild(
            command,
            expected_message_records=(recent, current, current),
        )
    with pytest.raises(ValidationError, match="USER"):
        _rebuild(
            command,
            expected_message_records=(
                recent,
                _rebuild(current, direction=MessageDirection.ASSISTANT),
            ),
        )
    with pytest.raises(ValidationError, match="Conversation"):
        _rebuild(
            command,
            expected_message_records=(
                _rebuild(recent, conversation_id=uuid4()),
                current,
            ),
        )
    with pytest.raises(ValidationError, match="RUNNING"):
        _rebuild(
            command,
            expected_active_run_record=_project_run(
                command.expected_active_run_record,
                status=AgentRunStatus.CREATED,
            ),
        )
    with pytest.raises(ValidationError, match="exact Run"):
        _rebuild(command, request_understanding_record=_rebuild(record, run_id=uuid4()))

    accepted_graph = _initial_v2_graph()
    with pytest.raises(ValidationError, match="no Task effect"):
        SaveRequestUnderstandingV2NoTaskCommand(
            owner_scope=accepted_graph.owner_scope,
            expected_conversation_record=(
                accepted_graph.expected_conversation_record
            ),
            expected_message_records=accepted_graph.expected_message_records,
            expected_active_run_record=accepted_graph.expected_active_run_record,
            request_understanding_record=(
                accepted_graph.request_understanding.record
            ),
        )

    too_early = min(
        current.received_at,
        command.expected_active_run_record.started_at,
    ) - timedelta(microseconds=1)
    with pytest.raises(ValidationError, match="cannot precede"):
        _rebuild(
            command,
            request_understanding_record=_rebuild(
                record,
                created_at=too_early,
            ),
        )


def test_v2_accepted_wrapper_requires_exact_one_candidate_and_semantic_child() -> None:
    graph = _initial_v2_graph()
    accepted = graph.request_understanding
    record = accepted.record
    child = accepted.accepted_delta
    candidate = record.task_delta_candidates[0]

    assert child.candidate_ref == candidate.candidate_id
    assert child.goal_text == candidate.goal_patch
    assert child.message_ref == record.message_ref
    assert child.base_task_state_version is None
    assert child.result_task_state_version == 1
    assert record.validated_task_state_version == 1
    assert record.next_move_candidate_ref is not None

    with pytest.raises(ValidationError, match="candidate projection"):
        SaveRequestUnderstandingV2AcceptedCommand(
            record=record,
            accepted_delta=_rebuild(child, goal_text="被篡改的目标"),
        )
    with pytest.raises(ValidationError, match="candidate projection"):
        SaveRequestUnderstandingV2AcceptedCommand(
            record=record,
            accepted_delta=_rebuild(child, candidate_ref=uuid4()),
        )

    second_candidate = _rebuild(candidate, candidate_id=uuid4())
    partial_record = _rebuild(
        record,
        task_delta_candidates=(candidate, second_candidate),
        candidate_validation=(
            record.candidate_validation[0],
            CandidateValidationRecordV2(
                candidate_ref=second_candidate.candidate_id,
                decision=CandidateValidationDecision.REJECT,
                reason_code=CandidateRejectionReasonCode.INPUT_VALUE_INVALID,
            ),
        ),
    )
    with pytest.raises(ValidationError, match="exactly one emitted"):
        SaveRequestUnderstandingV2AcceptedCommand(
            record=partial_record,
            accepted_delta=child,
        )

    multi_record = _rebuild(
        record,
        task_delta_candidates=(candidate, second_candidate),
        candidate_validation=(
            record.candidate_validation[0],
            CandidateValidationRecordV2(
                candidate_ref=second_candidate.candidate_id,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        accepted_delta_refs=(child.accepted_delta_id, uuid4()),
    )
    with pytest.raises(ValidationError, match="exactly one emitted"):
        SaveRequestUnderstandingV2AcceptedCommand(
            record=multi_record,
            accepted_delta=child,
        )


def test_v2_initial_graph_closes_candidate_binding_task_and_clean_state() -> None:
    graph = _initial_v2_graph()
    record = graph.request_understanding.record
    child = graph.request_understanding.accepted_delta
    candidate_input = record.task_delta_candidates[0].input_candidates[0]
    binding = graph.input_binding.record
    task = graph.initial_task.initial_record
    unit = graph.initial_request_unit.initial_record

    assert binding.name == candidate_input.name
    assert binding.normalized_value == "O-1001"
    assert binding.authority is candidate_input.authority
    assert binding.source_refs == (candidate_input.source_ref,)
    assert child.task_id == task.task_id == unit.task_id
    assert unit.goal_text == child.goal_text
    assert unit.goal_source_refs == (record.message_ref,)
    assert unit.input_binding_refs == child.input_binding_refs == (
        binding.binding_id,
    )
    assert task.status is unit.status is TaskStatus.ACTIVE
    assert task.state_version == unit.state_version == 1
    assert task.last_outcome_ref is None
    assert unit.contextualization_ref is None
    assert unit.constraint_refs == ()
    assert unit.dependency_refs == ()
    assert unit.open_questions == ()
    assert unit.observation_refs == ()
    assert unit.evidence_binding_refs == ()
    assert unit.pending_action_ref is None
    assert unit.result_refs == ()
    assert binding.supersedes is None
    assert {
        record.created_at,
        child.accepted_at,
        task.created_at,
        task.updated_at,
        unit.created_at,
        unit.updated_at,
        binding.created_at,
        binding.updated_at,
        graph.conversation_task_link.linked_at,
    } == {UTC_NOW}


def test_v2_initial_graph_rejects_semantic_initial_state_and_link_tamper() -> None:
    graph = _initial_v2_graph()
    accepted = graph.request_understanding
    candidate = accepted.record.task_delta_candidates[0]
    binding_command = graph.input_binding
    binding = binding_command.record
    task = graph.initial_task.initial_record
    unit = graph.initial_request_unit.initial_record

    changed_candidate = _rebuild(
        candidate,
        input_candidates=(
            _rebuild(
                candidate.input_candidates[0],
                candidate_value="O-2002",
            ),
        ),
    )
    changed_record = _rebuild(
        accepted.record,
        task_delta_candidates=(changed_candidate,),
    )
    with pytest.raises(ValidationError, match="candidate InputBinding"):
        _rebuild(
            graph,
            request_understanding=SaveRequestUnderstandingV2AcceptedCommand(
                record=changed_record,
                accepted_delta=accepted.accepted_delta,
            ),
        )
    with pytest.raises(ValidationError, match="candidate InputBinding"):
        _rebuild(
            graph,
            input_binding=_rebuild(
                binding_command,
                record=_rebuild(binding, normalized_value="O-2002"),
            ),
        )
    with pytest.raises(ValidationError, match="candidate InputBinding"):
        _rebuild(
            graph,
            input_binding=_rebuild(
                binding_command,
                record=_rebuild(binding, source_refs=(uuid4(),)),
            ),
        )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            graph,
            input_binding=_rebuild(
                binding_command,
                record=binding.model_copy(
                    update={"authority": InputAuthority.MODEL_INFERENCE}
                ),
            ),
        )
    with pytest.raises(ValidationError, match="clean initial Task"):
        _rebuild(
            graph,
            initial_task=CreateTaskCommand(
                initial_record=_rebuild(task, last_outcome_ref=uuid4())
            ),
        )
    with pytest.raises(ValidationError, match="clean initial RequestUnit"):
        _rebuild(
            graph,
            initial_request_unit=CreateRequestUnitCommand(
                initial_record=_rebuild(unit, contextualization_ref=uuid4())
            ),
        )
    with pytest.raises(ValidationError, match="clean initial InputBinding"):
        _rebuild(
            graph,
            input_binding=_rebuild(
                binding_command,
                record=_rebuild(binding, supersedes=uuid4()),
            ),
        )
    with pytest.raises(ValidationError, match="ConversationTaskLink"):
        _rebuild(
            graph,
            conversation_task_link=_rebuild(
                graph.conversation_task_link,
                ended_at=UTC_NOW + timedelta(seconds=1),
            ),
        )
    with pytest.raises(ValidationError, match="RunTaskLink"):
        _rebuild(
            graph,
            run_task_link=CreateRunTaskLinkCommand(
                active_record=_rebuild(
                    graph.run_task_link.active_record,
                    base_task_state_version=1,
                )
            ),
        )


def test_v2_initial_graph_rejects_synchronized_timestamp_rollback() -> None:
    graph = _initial_v2_graph()
    rolled_back_at = min(
        graph.expected_active_run_record.started_at,
        next(
            message.received_at
            for message in graph.expected_message_records
            if message.message_id
            == graph.request_understanding.record.message_ref
        ),
    ) - timedelta(seconds=1)
    accepted = graph.request_understanding
    rolled_accepted = SaveRequestUnderstandingV2AcceptedCommand(
        record=_rebuild(accepted.record, created_at=rolled_back_at),
        accepted_delta=_rebuild(
            accepted.accepted_delta,
            accepted_at=rolled_back_at,
        ),
    )
    binding = graph.input_binding.record
    task = graph.initial_task.initial_record
    unit = graph.initial_request_unit.initial_record

    with pytest.raises(ValidationError, match="cannot precede"):
        _rebuild(
            graph,
            request_understanding=rolled_accepted,
            initial_task=CreateTaskCommand(
                initial_record=_rebuild(
                    task,
                    created_at=rolled_back_at,
                    updated_at=rolled_back_at,
                )
            ),
            initial_request_unit=CreateRequestUnitCommand(
                initial_record=_rebuild(
                    unit,
                    created_at=rolled_back_at,
                    updated_at=rolled_back_at,
                )
            ),
            input_binding=_rebuild(
                graph.input_binding,
                record=_rebuild(
                    binding,
                    created_at=rolled_back_at,
                    updated_at=rolled_back_at,
                ),
            ),
            conversation_task_link=_rebuild(
                graph.conversation_task_link,
                linked_at=rolled_back_at,
            ),
        )


def test_v2_commands_reject_subclass_and_undeclared_nested_state() -> None:
    graph = _initial_v2_graph()
    original_message = graph.expected_message_records[0]

    class MessageRecordSubclass(MessageRecord):
        pass

    subclass_message = MessageRecordSubclass(
        **original_message.model_dump(mode="python")
    )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            graph,
            expected_message_records=(
                subclass_message,
                graph.expected_message_records[1],
            ),
        )

    poisoned_record = graph.request_understanding.record.model_copy()
    object.__setattr__(
        poisoned_record,
        "_trusted_customer_id",
        "attacker-selected",
    )
    poisoned_wrapper = graph.request_understanding.model_copy(
        update={"record": poisoned_record}
    )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(graph, request_understanding=poisoned_wrapper)


def test_v2_commands_reject_noncanonical_nested_model_sidecars() -> None:
    class DictSubclass(dict):
        pass

    class SetSubclass(set):
        pass

    class StringSubclass(str):
        pass

    no_task = _v2_no_task_command()
    record = no_task.request_understanding_record

    missing_required_field = record.model_copy()
    missing_required_field.__pydantic_fields_set__.discard("run_id")

    constructed_with_missing_field = type(record).model_construct(
        _fields_set=record.model_fields_set - {"run_id"},
        **record.__dict__,
    )

    poisoned_state_container = record.model_copy()
    object.__setattr__(
        poisoned_state_container,
        "__dict__",
        DictSubclass(poisoned_state_container.__dict__),
    )

    poisoned_fields_container = record.model_copy()
    object.__setattr__(
        poisoned_fields_container,
        "__pydantic_fields_set__",
        SetSubclass(poisoned_fields_container.model_fields_set),
    )

    poisoned_fields_member = record.model_copy()
    poisoned_fields = set(poisoned_fields_member.model_fields_set)
    poisoned_fields.remove("run_id")
    poisoned_fields.add(StringSubclass("run_id"))
    object.__setattr__(
        poisoned_fields_member,
        "__pydantic_fields_set__",
        poisoned_fields,
    )

    poisoned_records = (
        missing_required_field,
        constructed_with_missing_field,
        poisoned_state_container,
        poisoned_fields_container,
        poisoned_fields_member,
    )
    for poisoned_record in poisoned_records:
        with pytest.raises(ValidationError, match="canonical"):
            _rebuild(
                no_task,
                request_understanding_record=poisoned_record,
            )

    graph = _initial_v2_graph()
    for poisoned_record in poisoned_records:
        poisoned_wrapper = graph.request_understanding.model_copy(
            update={"record": poisoned_record}
        )
        with pytest.raises(ValidationError, match="canonical"):
            _rebuild(
                graph,
                request_understanding=poisoned_wrapper,
            )


def test_v2_no_task_command_rejects_poisoned_primitive_subclasses() -> None:
    command = _v2_no_task_command()
    record = command.request_understanding_record

    class StringSubclass(str):
        pass

    class DateTimeSubclass(datetime):
        pass

    poisoned_schema_version = record.model_copy(
        update={
            "model_input_schema_version": StringSubclass(
                record.model_input_schema_version
            )
        }
    )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            command,
            request_understanding_record=poisoned_schema_version,
        )

    poisoned_created_at = record.model_copy(
        update={
            "created_at": DateTimeSubclass.fromtimestamp(
                record.created_at.timestamp(),
                tz=record.created_at.tzinfo,
            )
        }
    )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            command,
            request_understanding_record=poisoned_created_at,
        )


def test_v2_initial_graph_rejects_poisoned_primitive_subclasses() -> None:
    graph = _initial_v2_graph()
    child = graph.request_understanding.accepted_delta
    task = graph.initial_task.initial_record

    class StringSubclass(str):
        pass

    class DateTimeSubclass(datetime):
        pass

    poisoned_child = child.model_copy(
        update={"goal_text": StringSubclass(child.goal_text)}
    )
    poisoned_understanding = graph.request_understanding.model_copy(
        update={"accepted_delta": poisoned_child}
    )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            graph,
            request_understanding=poisoned_understanding,
        )

    poisoned_task = task.model_copy(
        update={
            "created_at": DateTimeSubclass.fromtimestamp(
                task.created_at.timestamp(),
                tz=task.created_at.tzinfo,
            )
        }
    )
    poisoned_task_command = graph.initial_task.model_copy(
        update={"initial_record": poisoned_task}
    )
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            graph,
            initial_task=poisoned_task_command,
        )


def test_task_transition_command_is_one_exact_task_request_unit_aggregate() -> None:
    command = _task_transition_command()

    assert command.task_state_transition.base_state_version == (
        command.expected_task_record.state_version
    )
    assert command.task_state_transition.result_state_version == (
        command.next_request_unit_record.state_version
    )
    assert command.expected_task_record.status is (
        command.task_state_transition.from_status
    )
    assert command.next_request_unit_record.status is (
        command.task_state_transition.to_status
    )

    with pytest.raises(ValidationError, match="Task identity"):
        _rebuild(
            command,
            next_task_record=_rebuild(
                command.next_task_record,
                task_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="Task owner"):
        _rebuild(
            command,
            next_task_record=_rebuild(
                command.next_task_record,
                owner_customer_id="customer-B",
            ),
        )
    with pytest.raises(ValidationError, match="Task stable fields"):
        _rebuild(
            command,
            next_task_record=_rebuild(
                command.next_task_record,
                created_at=UTC_NOW - timedelta(seconds=1),
            ),
        )
    with pytest.raises(ValidationError, match="RequestUnit identity"):
        _rebuild(
            command,
            next_request_unit_record=_rebuild(
                command.next_request_unit_record,
                request_unit_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="RequestUnit stable fields"):
        _rebuild(
            command,
            next_request_unit_record=_rebuild(
                command.next_request_unit_record,
                goal_text="另一个目标",
            ),
        )
    with pytest.raises(ValidationError, match="base version"):
        _rebuild(
            command,
            expected_task_record=_rebuild(
                command.expected_task_record,
                state_version=2,
            ),
        )
    with pytest.raises(ValidationError, match="status"):
        _rebuild(
            command,
            next_request_unit_record=_rebuild(
                command.next_request_unit_record,
                status=TaskStatus.BLOCKED,
            ),
        )


def test_observation_command_requires_exact_successful_read_get_order_source() -> None:
    observation = _observation()
    source = _tool_call(
        status=ToolCallStatus.SUCCEEDED,
        attempt_count=1,
        finished_at=UTC_NOW + timedelta(milliseconds=1),
        result_ref=uuid4(),
    )
    command = SaveObservationCommand(
        owner_scope=_owner_scope(),
        observation_record=observation,
        source_tool_call_record=source,
    )

    assert command.source_tool_call_record.tool_call_id != (
        command.observation_record.observation_id
    )
    assert command.source_tool_call_record.result_ref != (
        command.observation_record.observation_id
    )
    with pytest.raises(ValidationError, match="SUCCEEDED"):
        SaveObservationCommand(
            owner_scope=_owner_scope(),
            observation_record=observation,
            source_tool_call_record=_tool_call(
                status=ToolCallStatus.RUNNING,
                attempt_count=1,
            ),
        )
    with pytest.raises(ValidationError, match="READ"):
        SaveObservationCommand(
            owner_scope=_owner_scope(),
            observation_record=observation,
            source_tool_call_record=_tool_call(
                status=ToolCallStatus.SUCCEEDED,
                attempt_count=1,
                effect=ToolEffect.ACTION,
                finished_at=UTC_NOW + timedelta(milliseconds=1),
            ),
        )
    with pytest.raises(ValidationError, match="get_order"):
        SaveObservationCommand(
            owner_scope=_owner_scope(),
            observation_record=observation,
            source_tool_call_record=_project_tool_call(
                source,
                canonical_tool_name="create_refund",
            ),
        )
    assert set(ObservationWriteResult) == {
        ObservationWriteResult.INSERTED,
        ObservationWriteResult.ALREADY_APPLIED,
        ObservationWriteResult.SOURCE_PROJECTION_CONFLICT,
    }


@pytest.mark.parametrize(
    ("stop_reason", "with_task", "outcome", "task_status"),
    _COMPLETED_TERMINAL_MATRIX,
    ids=(
        "goal-completed-with-task",
        "not-found-with-task",
        "provider-protocol-without-task",
        "provider-protocol-with-task",
        "input-invalid-without-task",
        "gate-rejected-with-task",
        "order-service-unavailable-with-task",
        "presentation-plan-rejected-with-task",
        "renderer-invariant-failed-with-task",
    ),
)
def test_run_finalization_accepts_only_the_nine_completed_terminal_rows(
    stop_reason: StopReason,
    with_task: bool,
    outcome: AgentOutcome,
    task_status: TaskStatus | None,
) -> None:
    command = _completed_finalization(
        stop_reason=stop_reason,
        outcome=outcome,
        with_task=with_task,
        task_status=task_status,
    )

    assert command.terminal_record.status is AgentRunStatus.COMPLETED
    assert command.terminal_result is not None
    assert command.terminal_result.outcome is outcome
    assert command.assistant_message is not None
    assert command.assistant_message.content == command.terminal_result.message
    assert command.terminal_trace_events[-1].event_type is TraceEventType.RUN_STOPPED
    if with_task:
        assert command.task_transition is not None
        assert command.task_transition.next_task_record.status is task_status
        assert command.result_task_records == (
            command.task_transition.next_task_record,
        )
        assert tuple(
            event.event_type for event in command.terminal_trace_events
        ) == (
            TraceEventType.TASK_STATE_CHANGED,
            TraceEventType.RUN_STOPPED,
        )
    else:
        assert command.task_transition is None
        assert command.result_task_records == ()
        assert tuple(
            event.event_type for event in command.terminal_trace_events
        ) == (TraceEventType.RUN_STOPPED,)


def test_completed_run_requires_result_message_and_run_stopped() -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="Task transition"):
        _rebuild(command, task_transition=None)
    with pytest.raises(ValidationError, match="terminal result"):
        _rebuild(command, terminal_result=None)
    with pytest.raises(ValidationError, match="ASSISTANT Message"):
        _rebuild(command, assistant_message=None)
    with pytest.raises(ValidationError, match="RunStopped"):
        _rebuild(
            command,
            terminal_trace_events=(command.terminal_trace_events[0],),
        )
    no_task = _completed_finalization(
        stop_reason=StopReason.INPUT_INVALID,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )
    with pytest.raises(ValidationError, match="Task transition"):
        _rebuild(no_task, task_transition=command.task_transition)
    with pytest.raises(ValidationError, match="RunStopped"):
        _rebuild(no_task, terminal_trace_events=())


def test_completed_run_rejects_omitted_reason_outcome_task_cross_products() -> None:
    with_task = _completed_finalization()
    without_task = _completed_finalization(
        stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )

    unsupported_no_task_reason = StopReason.GATE_REJECTED
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            without_task,
            terminal_record=_project_run(
                without_task.terminal_record,
                stop_reason=unsupported_no_task_reason,
            ),
            terminal_trace_events=_updated_terminal_trace_events(
                without_task,
                TraceEventType.RUN_STOPPED,
                stop_reason=unsupported_no_task_reason,
            ),
        )

    unsupported_task_reason = StopReason.INPUT_INVALID
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            with_task,
            terminal_record=_project_run(
                with_task.terminal_record,
                stop_reason=unsupported_task_reason,
            ),
            terminal_trace_events=_updated_terminal_trace_events(
                with_task,
                TraceEventType.RUN_STOPPED,
                stop_reason=unsupported_task_reason,
            ),
        )

    for omitted_outcome in (
        AgentOutcome.ASK_USER,
        AgentOutcome.NEED_HUMAN,
        AgentOutcome.BLOCKED,
    ):
        with pytest.raises(ValidationError, match="closed terminal matrix"):
            _rebuild(
                with_task,
                terminal_result=_rebuild(
                    with_task.terminal_result,
                    outcome=omitted_outcome,
                ),
                terminal_trace_events=_updated_terminal_trace_events(
                    with_task,
                    TraceEventType.RUN_STOPPED,
                    user_outcome=omitted_outcome,
                ),
            )

    task_id = with_task.expected_active_links[0].task_id
    request_unit_id = (
        with_task.task_transition.next_request_unit_record.request_unit_id
    )
    blocked_transition = _terminal_task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
        terminal_status=TaskStatus.BLOCKED,
    )
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            with_task,
            task_transition=blocked_transition,
            result_task_records=(blocked_transition.next_task_record,),
            terminal_trace_events=_updated_terminal_trace_events(
                with_task,
                TraceEventType.TASK_STATE_CHANGED,
                task_id=blocked_transition.next_task_record.task_id,
                request_unit_id=(
                    blocked_transition.next_request_unit_record.request_unit_id
                ),
                occurred_at=blocked_transition.task_state_transition.changed_at,
            ),
        )

    cancelled_transition = _terminal_task_transition(
        task_id=task_id,
        request_unit_id=request_unit_id,
        terminal_status=TaskStatus.CANCELLED,
    )
    with pytest.raises(ValidationError, match="closed terminal matrix"):
        _rebuild(
            with_task,
            task_transition=cancelled_transition,
            result_task_records=(cancelled_transition.next_task_record,),
            terminal_trace_events=_updated_terminal_trace_events(
                with_task,
                TraceEventType.TASK_STATE_CHANGED,
                task_id=cancelled_transition.next_task_record.task_id,
                request_unit_id=(
                    cancelled_transition.next_request_unit_record.request_unit_id
                ),
                occurred_at=cancelled_transition.task_state_transition.changed_at,
            ),
        )


def test_completed_run_binds_every_foreign_identity_to_one_terminal_turn() -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="terminal result.*Run"):
        _rebuild(
            command,
            terminal_result=_rebuild(command.terminal_result, run_id=uuid4()),
        )
    with pytest.raises(ValidationError, match="ASSISTANT Message.*Conversation"):
        _rebuild(
            command,
            assistant_message=_rebuild(
                command.assistant_message,
                conversation_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="conversation_id"):
        _rebuild(
            command,
            terminal_record=_project_run(
                command.terminal_record,
                conversation_id=None,
            ),
        )

    foreign_transition = _terminal_task_transition(
        task_id=uuid4(),
        request_unit_id=uuid4(),
        terminal_status=TaskStatus.COMPLETED,
    )
    with pytest.raises(ValidationError, match="link Task"):
        _rebuild(
            command,
            task_transition=foreign_transition,
            result_task_records=(foreign_transition.next_task_record,),
        )

    same_task_foreign_unit = _terminal_task_transition(
        task_id=command.expected_active_links[0].task_id,
        request_unit_id=uuid4(),
        terminal_status=TaskStatus.COMPLETED,
    )
    with pytest.raises(ValidationError, match="TaskStateChanged"):
        _rebuild(
            command,
            task_transition=same_task_foreign_unit,
            result_task_records=(same_task_foreign_unit.next_task_record,),
        )

    with pytest.raises(ValidationError, match="terminal Trace.*Run"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.TASK_STATE_CHANGED,
                run_id=uuid4(),
            ),
        )
    with pytest.raises(ValidationError, match="terminal Trace.*Run"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                run_id=uuid4(),
            ),
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"schema_version": "message_record.p0.v2"},
        {"direction": MessageDirection.USER},
        {"content": "被篡改的回复"},
        {"received_at": UTC_NOW},
    ),
    ids=("schema", "user-direction", "content", "timestamp"),
)
def test_completed_run_rejects_non_exact_assistant_message(
    updates: dict[str, object],
) -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="ASSISTANT Message"):
        _rebuild(
            command,
            assistant_message=_rebuild(command.assistant_message, **updates),
        )


def test_completed_run_terminal_trace_is_complete_ordered_and_unique() -> None:
    command = _completed_finalization()
    task_changed, run_stopped = command.terminal_trace_events

    with pytest.raises(ValidationError, match="ordered"):
        _rebuild(
            command,
            terminal_trace_events=(run_stopped, task_changed),
        )
    with pytest.raises(ValidationError, match="identities must be unique"):
        _rebuild(
            command,
            terminal_trace_events=(
                task_changed,
                run_stopped.model_copy(
                    update={"trace_event_id": task_changed.trace_event_id}
                ),
            ),
        )
    with pytest.raises(ValidationError, match="ordered"):
        _rebuild(
            command,
            terminal_trace_events=(run_stopped, run_stopped),
        )
    with pytest.raises(ValidationError, match="ordered"):
        _rebuild(
            command,
            terminal_trace_events=(
                task_changed.model_copy(
                    update={"event_type": TraceEventType.RESPONSE_RENDERED}
                ),
                run_stopped,
            ),
        )

    no_task = _completed_finalization(
        stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )
    with pytest.raises(ValidationError, match="only RunStopped"):
        _rebuild(
            no_task,
            terminal_trace_events=(
                TraceEvent(
                    trace_event_id=uuid4(),
                    event_type=TraceEventType.TASK_STATE_CHANGED,
                    occurred_at=no_task.terminal_record.completed_at,
                    run_id=no_task.terminal_record.run_id,
                    task_id=uuid4(),
                    request_unit_id=uuid4(),
                ),
                *no_task.terminal_trace_events,
            ),
        )


def test_completed_run_binds_terminal_trace_timestamps_and_transition_time() -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError, match="RunStopped.*stop reason"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                stop_reason=StopReason.GATE_REJECTED,
            ),
        )
    with pytest.raises(ValidationError, match="RunStopped.*outcome"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                user_outcome=AgentOutcome.BLOCKED,
            ),
        )
    with pytest.raises(ValidationError, match="TaskStateChanged.*timestamp"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.TASK_STATE_CHANGED,
                occurred_at=UTC_NOW,
            ),
        )
    with pytest.raises(ValidationError, match="RunStopped.*timestamp"):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                occurred_at=UTC_NOW,
            ),
        )

    transition = command.task_transition
    changed_after_completion = command.terminal_record.completed_at + timedelta(
        milliseconds=1
    )
    late_transition = _terminal_task_transition(
        task_id=transition.next_task_record.task_id,
        request_unit_id=transition.next_request_unit_record.request_unit_id,
        terminal_status=TaskStatus.COMPLETED,
        changed_at=changed_after_completion,
    )
    with pytest.raises(ValidationError, match="cannot follow Run completion"):
        _rebuild(
            command,
            task_transition=late_transition,
            result_task_records=(late_transition.next_task_record,),
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                TraceEventType.TASK_STATE_CHANGED,
                occurred_at=changed_after_completion,
            ),
        )


@pytest.mark.parametrize(
    ("event_type", "field_name"),
    _TERMINAL_TRACE_CONTAMINATION_CASES,
)
def test_completed_run_terminal_trace_rejects_every_non_allowlisted_projection(
    event_type: TraceEventType,
    field_name: str,
) -> None:
    command = _completed_finalization()

    with pytest.raises(ValidationError):
        _rebuild(
            command,
            terminal_trace_events=_updated_terminal_trace_events(
                command,
                event_type,
                **{field_name: _non_empty_trace_optional_value(field_name)},
            ),
        )


def test_failed_run_closes_links_without_fabricating_terminal_projections() -> None:
    with_task = _failed_finalization()
    without_task = _failed_finalization(with_task=False)

    assert with_task.terminal_record.stop_reason is None
    assert with_task.task_transition is None
    assert with_task.terminal_result is None
    assert with_task.assistant_message is None
    assert with_task.terminal_trace_events == ()
    assert with_task.terminal_links[0].result_task_state_version == (
        with_task.result_task_records[0].state_version
    )
    assert without_task.expected_active_links == ()
    assert without_task.result_task_records == ()


def test_failed_run_rejects_all_four_terminal_turn_projections() -> None:
    failed = _failed_finalization()
    completed = _completed_finalization()
    projection_values = {
        "task_transition": completed.task_transition,
        "terminal_result": completed.terminal_result,
        "assistant_message": completed.assistant_message,
        "terminal_trace_events": completed.terminal_trace_events,
    }

    for field_name, value in projection_values.items():
        with pytest.raises(ValidationError, match="FAILED"):
            _rebuild(failed, **{field_name: value})
    with pytest.raises(ValidationError, match="FAILED.*stop_reason"):
        _rebuild(
            failed,
            terminal_record=_project_run(
                failed.terminal_record,
                stop_reason=StopReason.GOAL_COMPLETED,
            ),
        )


def test_terminal_turn_revalidates_coupled_result_and_message_content() -> None:
    command = _completed_finalization()
    tampered_result = command.terminal_result.model_copy(update={"message": ""})
    tampered_message = command.assistant_message.model_copy(update={"content": ""})

    with pytest.raises(ValidationError):
        _rebuild(tampered_result)
    with pytest.raises(ValidationError):
        _rebuild(tampered_message)
    with pytest.raises(ValidationError, match="canonical"):
        _rebuild(
            command,
            terminal_result=tampered_result,
            assistant_message=tampered_message,
        )


def test_terminal_turn_revalidates_message_identity_without_disclosure() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    tampered_message = command.assistant_message.model_copy(
        update={"message_id": secret}
    )

    with pytest.raises(ValidationError):
        _rebuild(tampered_message)
    with pytest.raises(ValidationError, match="canonical") as error:
        _rebuild(command, assistant_message=tampered_message)
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_semantic_error_does_not_retain_valid_private_content() -> None:
    command = _completed_finalization()
    customer_id = "customer-A"
    message_content = f"{customer_id} 的订单 O-1001"
    mismatched_message = _rebuild(
        command.assistant_message,
        content=message_content,
    )

    with pytest.raises(ValidationError, match="content") as error:
        _rebuild(command, assistant_message=mismatched_message)
    _assert_validation_error_is_sanitized(
        error.value,
        customer_id,
        message_content,
        "O-1001",
    )


@pytest.mark.parametrize(
    "validate",
    (
        lambda secret: FinalizeRunCommand(unexpected=secret),
        lambda secret: FinalizeRunCommand.model_validate(secret),
        lambda secret: FinalizeRunCommand.model_validate_json(f'"{secret}"'),
        lambda secret: FinalizeRunCommand.model_validate_strings(secret),
    ),
    ids=(
        "constructor",
        "model_validate",
        "model_validate_json",
        "model_validate_strings",
    ),
)
def test_terminal_turn_public_validation_entries_sanitize_raw_input(
    validate: Callable[[str], object],
) -> None:
    secret = "customer-A SECRET"

    with pytest.raises(ValidationError) as error:
        validate(secret)
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_sanitizer_preserves_strict_json_validation() -> None:
    command = _completed_finalization()

    rebuilt = FinalizeRunCommand.model_validate_json(
        command.model_dump_json(),
        strict=True,
    )

    assert rebuilt == command


def test_terminal_turn_model_copy_rejects_invalid_result_and_message() -> None:
    command = _completed_finalization()
    empty_result = command.terminal_result.model_copy(update={"message": ""})
    empty_message = command.assistant_message.model_copy(update={"content": ""})

    for update in (
        {"terminal_result": empty_result},
        {"assistant_message": empty_message},
        {
            "terminal_result": empty_result,
            "assistant_message": empty_message,
        },
    ):
        with pytest.raises(ValidationError, match="canonical"):
            command.model_copy(update=update)


@pytest.mark.parametrize("strict", (False, True))
@pytest.mark.parametrize("bypass", ("BaseModel.model_copy", "model_construct"))
def test_terminal_turn_model_validate_rejects_low_level_invalid_instance(
    strict: bool,
    bypass: str,
) -> None:
    command = _completed_finalization()
    secret = "customer-A 的订单 O-1001 SECRET"
    invalid_result = command.terminal_result.model_copy(
        update={"message": "", "secret": secret}
    )
    invalid_message = command.assistant_message.model_copy(
        update={"content": ""}
    )
    if bypass == "BaseModel.model_copy":
        invalid_outer = BaseModel.model_copy(
            command,
            update={
                "terminal_result": invalid_result,
                "assistant_message": invalid_message,
            },
        )
    else:
        values = {
            field_name: getattr(command, field_name)
            for field_name in FinalizeRunCommand.model_fields
        }
        values["terminal_result"] = invalid_result
        values["assistant_message"] = invalid_message
        invalid_outer = FinalizeRunCommand.model_construct(**values)

    with pytest.raises(ValidationError, match="canonical") as error:
        FinalizeRunCommand.model_validate(invalid_outer, strict=strict)
    _assert_validation_error_is_sanitized(
        error.value,
        secret,
        "customer-A",
        "O-1001",
    )


@pytest.mark.parametrize("strict", (False, True))
def test_terminal_turn_revalidation_rejects_hidden_outer_storage(
    strict: bool,
) -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    invalid_outer = BaseModel.model_copy(
        command,
        update={"secret": secret},
    )

    assert vars(invalid_outer)["secret"] == secret
    assert "secret" in invalid_outer.model_fields_set
    with pytest.raises(ValidationError, match="canonical") as error:
        FinalizeRunCommand.model_validate(invalid_outer, strict=strict)
    _assert_validation_error_is_sanitized(error.value, secret)

    with pytest.raises(ValidationError) as copy_error:
        command.model_copy(update={"secret": secret})
    _assert_validation_error_is_sanitized(copy_error.value, secret)


def test_terminal_turn_valid_copy_revalidation_and_pickle_remain_compatible() -> None:
    command = _completed_finalization()
    nested_field_names = (
        "expected_active_record",
        "terminal_record",
        "expected_active_links",
        "terminal_links",
        "result_task_records",
        "task_transition",
        "terminal_result",
        "assistant_message",
        "terminal_trace_events",
    )

    shallow = command.model_copy()
    deep = command.model_copy(deep=True)
    revalidated = FinalizeRunCommand.model_validate(command)
    strict_revalidated = FinalizeRunCommand.model_validate(command, strict=True)
    restored = pickle.loads(pickle.dumps(command))

    for rebuilt in (
        shallow,
        deep,
        revalidated,
        strict_revalidated,
        restored,
    ):
        assert type(rebuilt) is FinalizeRunCommand
        assert rebuilt == command
        assert rebuilt.model_fields_set == command.model_fields_set
    assert shallow is not command
    assert set(nested_field_names) == set(FinalizeRunCommand.model_fields)
    for field_name in nested_field_names:
        assert getattr(shallow, field_name) is getattr(command, field_name)
        assert getattr(deep, field_name) is not getattr(command, field_name)


def test_terminal_turn_subclass_copy_preserves_unset_default_factory_value() -> None:
    class FinalizeRunCommandWithNonce(FinalizeRunCommand):
        nonce: UUID = Field(default_factory=uuid4)
        payload: list[dict[str, str]] = Field(
            default_factory=lambda: [{"source": "default"}]
        )

    command = _completed_finalization()
    base_values = {
        field_name: getattr(command, field_name)
        for field_name in FinalizeRunCommand.model_fields
    }
    extended = FinalizeRunCommandWithNonce(**base_values)
    original_fields_set = extended.model_fields_set
    replacement_nonce = uuid4()
    replacement_payload = [{"source": "updated"}]

    shallow = extended.model_copy()
    deep = extended.model_copy(deep=True)
    updated = extended.model_copy(
        update={
            "nonce": replacement_nonce,
            "payload": replacement_payload,
        }
    )

    assert not {"nonce", "payload"} & original_fields_set
    assert shallow.nonce == extended.nonce
    assert deep.nonce == extended.nonce
    assert shallow.payload is extended.payload
    assert shallow.payload[0] is extended.payload[0]
    assert deep.payload == extended.payload
    assert deep.payload is not extended.payload
    assert deep.payload[0] is not extended.payload[0]
    assert shallow.model_fields_set == original_fields_set
    assert deep.model_fields_set == original_fields_set
    assert updated.nonce == replacement_nonce
    assert updated.payload == replacement_payload
    assert updated.model_fields_set == original_fields_set | {
        "nonce",
        "payload",
    }


def test_terminal_turn_frozen_assignment_sanitizes_raw_input() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"

    with pytest.raises(ValidationError, match="Instance is frozen") as error:
        command.assistant_message = secret
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_recursively_revalidates_nested_task_transition() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    transition = command.task_transition
    tampered_state_transition = transition.task_state_transition.model_copy(
        update={"reason_ref": secret}
    )
    tampered_transition = transition.model_copy(
        update={"task_state_transition": tampered_state_transition}
    )

    with pytest.raises(ValidationError):
        _rebuild(tampered_state_transition)
    with pytest.raises(ValidationError, match="canonical") as error:
        _rebuild(command, task_transition=tampered_transition)
    _assert_validation_error_is_sanitized(error.value, secret)


def test_terminal_turn_rejects_non_exact_new_projection_model_types() -> None:
    command = _completed_finalization()

    class ResultSubclass(AgentRunResult):
        pass

    class MessageSubclass(MessageRecord):
        pass

    class TaskTransitionSubclass(ApplyTaskTransitionCommand):
        pass

    class TraceEventSubclass(TraceEvent):
        pass

    forged_result = ResultSubclass(
        **{
            field_name: getattr(command.terminal_result, field_name)
            for field_name in AgentRunResult.model_fields
        }
    )
    forged_message = MessageSubclass(
        **{
            field_name: getattr(command.assistant_message, field_name)
            for field_name in MessageRecord.model_fields
        }
    )
    forged_transition = TaskTransitionSubclass(
        **{
            field_name: getattr(command.task_transition, field_name)
            for field_name in ApplyTaskTransitionCommand.model_fields
        }
    )
    task_changed, run_stopped = command.terminal_trace_events
    forged_task_changed = TraceEventSubclass(
        **{
            field_name: getattr(task_changed, field_name)
            for field_name in TraceEvent.model_fields
        }
    )

    for field_name, value in (
        ("terminal_result", forged_result),
        ("assistant_message", forged_message),
        ("task_transition", forged_transition),
        (
            "terminal_trace_events",
            (forged_task_changed, run_stopped),
        ),
    ):
        with pytest.raises(ValidationError, match="canonical|exact"):
            _rebuild(command, **{field_name: value})


def test_terminal_turn_rejects_hidden_outer_and_nested_model_storage() -> None:
    command = _completed_finalization()
    secret = "customer-A SECRET"
    tampered_result = command.terminal_result.model_copy(update={"secret": secret})
    tampered_message = command.assistant_message.model_copy(update={"secret": secret})
    tampered_next_task = command.task_transition.next_task_record.model_copy(
        update={"secret": secret}
    )
    tampered_transition = command.task_transition.model_copy(
        update={"next_task_record": tampered_next_task}
    )
    tampered_next_unit = (
        command.task_transition.next_request_unit_record.model_copy(
            update={"secret": secret}
        )
    )
    tampered_unit_transition = command.task_transition.model_copy(
        update={"next_request_unit_record": tampered_next_unit}
    )
    task_changed, run_stopped = command.terminal_trace_events
    tampered_task_changed = task_changed.model_copy(update={"secret": secret})

    for field_name, value in (
        ("terminal_result", tampered_result),
        ("assistant_message", tampered_message),
        ("task_transition", tampered_transition),
        ("task_transition", tampered_unit_transition),
        (
            "terminal_trace_events",
            (tampered_task_changed, run_stopped),
        ),
    ):
        with pytest.raises(ValidationError, match="canonical") as error:
            _rebuild(command, **{field_name: value})
        _assert_validation_error_is_sanitized(error.value, secret)


def test_completed_task_transition_respects_active_link_base_lower_bound() -> None:
    with pytest.raises(ValidationError, match="active link base Task version"):
        _completed_finalization(
            active_link_base_state_version=2,
            transition_base_state_version=1,
        )

    equal_base = _completed_finalization(
        active_link_base_state_version=2,
        transition_base_state_version=2,
    )
    advanced_before_terminal_turn = _completed_finalization(
        active_link_base_state_version=2,
        transition_base_state_version=3,
    )
    newly_created_task = _completed_finalization(
        active_link_base_state_version=None,
        transition_base_state_version=1,
    )
    failed_with_current_projection = _failed_finalization(
        active_link_base_state_version=2,
        current_task_state_version=3,
    )

    assert equal_base.task_transition.expected_task_record.state_version == 2
    assert equal_base.task_transition.next_task_record.state_version == 3
    assert (
        advanced_before_terminal_turn.task_transition.expected_task_record.state_version
        == 3
    )
    assert (
        advanced_before_terminal_turn.task_transition.next_task_record.state_version
        == 4
    )
    assert newly_created_task.expected_active_links[
        0
    ].base_task_state_version is None
    assert (
        failed_with_current_projection.terminal_links[
            0
        ].result_task_state_version
        == 3
    )


def test_run_finalization_preserves_existing_run_link_and_task_closure() -> None:
    command = _completed_finalization()
    running = command.expected_active_record
    terminal = command.terminal_record
    active_link = command.expected_active_links[0]
    result_task = command.result_task_records[0]

    assert command.terminal_links[0].result_task_state_version == (
        result_task.state_version
    )
    empty = _completed_finalization(
        stop_reason=StopReason.INPUT_INVALID,
        outcome=AgentOutcome.BLOCKED,
        with_task=False,
        task_status=None,
    )
    assert not empty.terminal_links

    with pytest.raises(ValidationError, match="RUNNING"):
        _rebuild(command, expected_active_record=terminal)
    with pytest.raises(ValidationError, match="dirty expected active Run"):
        _rebuild(
            command,
            expected_active_record=_project_run(
                running,
                incomplete_reason="PROCESS_RESTART_DETECTED",
            ),
        )
    with pytest.raises(ValidationError, match="terminal Run"):
        _rebuild(command, terminal_record=running)
    with pytest.raises(ValidationError, match="recovery-only stop reason"):
        _rebuild(
            command,
            terminal_record=_project_run(
                terminal,
                stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            ),
        )
    with pytest.raises(ValidationError, match="stable fields"):
        _rebuild(
            command,
            terminal_record=_project_run(terminal, conversation_id=uuid4()),
        )
    with pytest.raises(ValidationError, match="active RunTaskLink"):
        _rebuild(
            command,
            expected_active_links=(
                _rebuild(active_link, result_task_state_version=1),
            ),
        )
    with pytest.raises(ValidationError, match="exact RunTaskLink set"):
        _rebuild(command, terminal_links=())
    with pytest.raises(ValidationError, match="result Task"):
        _rebuild(
            command,
            result_task_records=(_rebuild(result_task, state_version=3),),
        )
    with pytest.raises(ValidationError, match="exact next Task"):
        _rebuild(
            command,
            result_task_records=(
                _rebuild(result_task, owner_customer_id="customer-B"),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild(
            command,
            result_task_records=(result_task, result_task),
        )


def test_application_inbound_models_are_strict_and_visibility_bounded() -> None:
    context = _customer_context()
    command = AgentRunCommand(
        customer_context=context,
        message="订单 O-1001 状态怎么样？",
    )
    result = AgentRunResult(
        run_id=uuid4(),
        outcome=AgentOutcome.COMPLETED,
        message="订单已发货。",
    )

    assert command.customer_context is context
    assert result.outcome is AgentOutcome.COMPLETED
    assert set(AgentRunCommand.model_fields) == {
        "customer_context",
        "message",
    }
    assert set(AgentRunResult.model_fields) == {"run_id", "outcome", "message"}
    assert AgentRunCommand.contract_visibility is (ContractVisibility.RUNTIME_PRIVATE)
    assert AgentRunResult.contract_visibility is ContractVisibility.USER_VISIBLE
    assert AgentRunCommand.model_config["strict"] is True
    assert AgentRunResult.model_config["strict"] is True

    with pytest.raises(ValidationError, match="CustomerContext instance"):
        AgentRunCommand(
            customer_context=context.model_dump(),
            message="订单 O-1001 状态怎么样？",
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        AgentRunCommand(
            customer_context=context,
            message="订单 O-1001 状态怎么样？",
            customer_id="customer-B",
        )
    with pytest.raises(ValidationError, match="UUID"):
        AgentRunResult(
            run_id=str(uuid4()),
            outcome=AgentOutcome.COMPLETED,
            message="订单已发货。",
        )
    with pytest.raises(ValidationError):
        AgentRunResult(
            run_id=uuid4(),
            outcome=AgentOutcome.COMPLETED.value,
            message="订单已发货。",
        )


def test_application_port_declaration_models_freeze_the_exact_field_surface() -> None:
    expected_fields = {
        SaveRequestUnderstandingV2AcceptedCommand: {
            "record",
            "accepted_delta",
        },
        SaveRequestUnderstandingV2NoTaskCommand: {
            "owner_scope",
            "expected_conversation_record",
            "expected_message_records",
            "expected_active_run_record",
            "request_understanding_record",
        },
        SaveInputBindingCommand: {"record", "request_unit_id"},
        CreateInitialTaskGraphV2Command: {
            "owner_scope",
            "expected_conversation_record",
            "expected_message_records",
            "expected_active_run_record",
            "request_understanding",
            "initial_task",
            "initial_request_unit",
            "input_binding",
            "conversation_task_link",
            "run_task_link",
        },
        ApplyTaskTransitionCommand: {
            "expected_task_record",
            "next_task_record",
            "expected_request_unit_record",
            "next_request_unit_record",
            "task_state_transition",
        },
        SaveObservationCommand: {
            "owner_scope",
            "observation_record",
            "source_tool_call_record",
        },
        FinalizeRunCommand: {
            "expected_active_record",
            "terminal_record",
            "expected_active_links",
            "terminal_links",
            "result_task_records",
            "task_transition",
            "terminal_result",
            "assistant_message",
            "terminal_trace_events",
        },
        AgentRunCommand: {"customer_context", "message"},
        AgentRunResult: {"run_id", "outcome", "message"},
        TaskRecoveryAggregate: {
            "task_record",
            "task_state_transitions",
        },
        ToolCallRecoveryAggregate: {
            "tool_call_record",
            "tool_attempt_records",
        },
        RestartRecoveryClosure: {
            "closure_fence",
            "conversation_record",
            "active_run_record",
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        },
        ApplyRestartRecoveryCommand: {
            "expected_closure",
            "run_transition",
            "tool_call_transitions",
            "task_transitions",
            "terminal_run_task_links",
            "recovery_trace_events",
        },
    }

    for model_type, fields in expected_fields.items():
        assert set(model_type.model_fields) == fields
        assert model_type.model_config["strict"] is True
        assert model_type.model_config["frozen"] is True
        assert model_type.model_config["extra"] == "forbid"
        assert model_type.model_json_schema()["additionalProperties"] is False

    closure = _restart_recovery_closure()
    with pytest.raises(ValidationError, match="UUID"):
        _rebuild(closure, closure_fence=str(closure.closure_fence))


def test_first_slice_application_tuple_cardinality_is_explicitly_bounded() -> None:
    optional_one_fields = (
        (FinalizeRunCommand, "expected_active_links"),
        (FinalizeRunCommand, "terminal_links"),
        (FinalizeRunCommand, "result_task_records"),
        (TaskRecoveryAggregate, "task_state_transitions"),
        (ToolCallRecoveryAggregate, "tool_attempt_records"),
        (RestartRecoveryClosure, "conversation_task_links"),
        (RestartRecoveryClosure, "run_task_links"),
        (RestartRecoveryClosure, "task_aggregates"),
        (RestartRecoveryClosure, "request_unit_records"),
        (RestartRecoveryClosure, "tool_call_aggregates"),
        (ApplyRestartRecoveryCommand, "tool_call_transitions"),
        (ApplyRestartRecoveryCommand, "task_transitions"),
        (ApplyRestartRecoveryCommand, "terminal_run_task_links"),
    )
    bounded_recovery_trace_fields = (
        (ApplyRestartRecoveryCommand, "recovery_trace_events"),
    )
    bounded_terminal_trace_fields = (
        (FinalizeRunCommand, "terminal_trace_events"),
    )
    bounded_v2_message_fields = (
        (SaveRequestUnderstandingV2NoTaskCommand, "expected_message_records"),
        (CreateInitialTaskGraphV2Command, "expected_message_records"),
    )
    for model_type, field_name in optional_one_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema.get("minItems", 0) == 0
        assert field_schema["maxItems"] == 1
    for model_type, field_name in bounded_recovery_trace_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema["minItems"] == 1
        assert field_schema["maxItems"] == 3
    for model_type, field_name in bounded_terminal_trace_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema.get("minItems", 0) == 0
        assert field_schema["maxItems"] == 2
    for model_type, field_name in bounded_v2_message_fields:
        field_schema = model_type.model_json_schema()["properties"][field_name]
        assert field_schema["minItems"] == 1
        assert field_schema["maxItems"] == 8

    finalization = _completed_finalization()
    empty_finalization = _failed_finalization(with_task=False)

    running_closure = _restart_recovery_closure()
    running_recovery = _restart_recovery_command()
    task_aggregate = running_closure.task_aggregates[0]
    tool_aggregate = running_closure.tool_call_aggregates[0]
    empty_task_aggregate = TaskRecoveryAggregate(
        task_record=_task(state_version=1),
        task_state_transitions=(),
    )
    empty_tool_aggregate = ToolCallRecoveryAggregate(
        tool_call_record=_tool_call(
            status=ToolCallStatus.CREATED,
            attempt_count=0,
        ),
        tool_attempt_records=(),
    )
    created_closure = _created_restart_recovery_closure()
    created_recovery = _created_restart_recovery_command()

    empty_instances_and_fields = (
        (empty_finalization, "expected_active_links"),
        (empty_finalization, "terminal_links"),
        (empty_finalization, "result_task_records"),
        (empty_finalization, "terminal_trace_events"),
        (empty_task_aggregate, "task_state_transitions"),
        (empty_tool_aggregate, "tool_attempt_records"),
        (created_closure, "conversation_task_links"),
        (created_closure, "run_task_links"),
        (created_closure, "task_aggregates"),
        (created_closure, "request_unit_records"),
        (created_closure, "tool_call_aggregates"),
        (created_recovery, "tool_call_transitions"),
        (created_recovery, "task_transitions"),
        (created_recovery, "terminal_run_task_links"),
    )
    for instance, field_name in empty_instances_and_fields:
        assert getattr(instance, field_name) == ()

    one_instances_and_fields = (
        (finalization, "expected_active_links"),
        (finalization, "terminal_links"),
        (finalization, "result_task_records"),
        (task_aggregate, "task_state_transitions"),
        (tool_aggregate, "tool_attempt_records"),
        (running_closure, "conversation_task_links"),
        (running_closure, "run_task_links"),
        (running_closure, "task_aggregates"),
        (running_closure, "request_unit_records"),
        (running_closure, "tool_call_aggregates"),
        (running_recovery, "tool_call_transitions"),
        (running_recovery, "task_transitions"),
        (running_recovery, "terminal_run_task_links"),
    )
    for instance, field_name in one_instances_and_fields:
        value = getattr(instance, field_name)
        assert len(value) == 1
        with pytest.raises(ValidationError):
            _rebuild(instance, **{field_name: (*value, value[0])})

    assert len(finalization.terminal_trace_events) == 2
    with pytest.raises(ValidationError):
        _rebuild(
            finalization,
            terminal_trace_events=(
                *finalization.terminal_trace_events,
                finalization.terminal_trace_events[0],
            ),
        )

    for model_type, field_name in (
        (InputBinding, "source_refs"),
        (RequestUnitRecord, "input_binding_refs"),
    ):
        source_field_schema = model_type.model_json_schema()["properties"][field_name]
        assert "maxItems" not in source_field_schema


def test_provider_protocol_error_is_fixed_and_adapter_discards_raw_context() -> None:
    error = ProviderProtocolError()
    safe_projection = " ".join((str(error), repr(error), repr(error.args)))

    assert error.args == ("PROVIDER_PROTOCOL_ERROR",)
    assert safe_projection.count("PROVIDER_PROTOCOL_ERROR") >= 3
    with pytest.raises(TypeError):
        ProviderProtocolError("raw provider payload")

    def translate_after_discarding_raw_exception() -> None:
        translated: ProviderProtocolError | None = None
        try:
            raise RuntimeError("Token VERY_SECRET Prompt private customer-A")
        except RuntimeError:
            translated = ProviderProtocolError()
        raise translated

    with pytest.raises(ProviderProtocolError) as raised:
        translate_after_discarding_raw_exception()
    translated = raised.value
    assert translated.__cause__ is None
    assert translated.__context__ is None
    projection = " ".join((str(translated), repr(translated), repr(translated.args)))
    for secret in ("VERY_SECRET", "Prompt private", "customer-A"):
        assert secret not in projection


def test_task_recovery_aggregate_requires_complete_contiguous_history() -> None:
    closure = _restart_recovery_closure()
    aggregate = closure.task_aggregates[0]
    transition = aggregate.task_state_transitions[0]

    assert transition.result_state_version == aggregate.task_record.state_version
    assert (
        TaskRecoveryAggregate(
            task_record=_task(state_version=1),
            task_state_transitions=(),
        ).task_state_transitions
        == ()
    )

    with pytest.raises(ValidationError, match="version 1"):
        TaskRecoveryAggregate(
            task_record=_task(
                task_id=transition.task_id,
                status=transition.to_status,
                state_version=1,
            ),
            task_state_transitions=(transition,),
        )
    with pytest.raises(ValidationError, match="complete contiguous"):
        TaskRecoveryAggregate(
            task_record=_rebuild(
                aggregate.task_record,
                state_version=3,
            ),
            task_state_transitions=(transition,),
        )
    with pytest.raises(ValidationError, match="Task identity"):
        TaskRecoveryAggregate(
            task_record=aggregate.task_record,
            task_state_transitions=(_rebuild(transition, task_id=uuid4()),),
        )
    with pytest.raises(ValidationError, match="terminal status"):
        TaskRecoveryAggregate(
            task_record=_rebuild(
                aggregate.task_record,
                status=TaskStatus.BLOCKED,
            ),
            task_state_transitions=(transition,),
        )
    with pytest.raises(ValidationError, match="before Task creation"):
        TaskRecoveryAggregate(
            task_record=_rebuild(
                aggregate.task_record,
                created_at=transition.changed_at + timedelta(milliseconds=1),
                updated_at=transition.changed_at + timedelta(milliseconds=1),
            ),
            task_state_transitions=(transition,),
        )


@pytest.mark.parametrize("transition_count", (0, 1))
def test_task_recovery_rejects_untrusted_large_version_without_range_materialization(
    monkeypatch: pytest.MonkeyPatch,
    transition_count: int,
) -> None:
    transition = _task_transition()
    transitions = (transition,) if transition_count else ()
    task = _task(
        task_id=transition.task_id,
        status=transition.to_status if transitions else TaskStatus.ACTIVE,
        state_version=100_000,
    )

    def fail_if_materialized(*_args: object) -> None:
        raise AssertionError(
            "untrusted state_version must not drive range materialization"
        )

    monkeypatch.setattr(
        application_records_module,
        "range",
        fail_if_materialized,
        raising=False,
    )
    with pytest.raises(ValidationError, match="complete contiguous"):
        TaskRecoveryAggregate(
            task_record=task,
            task_state_transitions=transitions,
        )


def test_tool_call_recovery_aggregate_requires_exact_attempt_history() -> None:
    aggregate = _restart_recovery_closure().tool_call_aggregates[0]
    call = aggregate.tool_call_record
    attempt = aggregate.tool_attempt_records[0]

    assert attempt.attempt_no == call.attempt_count == 1
    created = _tool_call(
        status=ToolCallStatus.CREATED,
        attempt_count=0,
    )
    assert (
        ToolCallRecoveryAggregate(
            tool_call_record=created,
            tool_attempt_records=(),
        ).tool_attempt_records
        == ()
    )
    with pytest.raises(ValidationError, match="exact attempt"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(),
        )
    with pytest.raises(ValidationError, match="ToolCall identity"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(_rebuild(attempt, tool_call_id=uuid4()),),
        )
    with pytest.raises(ValidationError, match="RUNNING"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(
                ToolAttemptRecord(
                    tool_call_id=call.tool_call_id,
                    attempt_no=1,
                    started_at=UTC_NOW,
                    finished_at=UTC_NOW + timedelta(milliseconds=1),
                    outcome=ToolResultOutcome.SUCCESS,
                ),
            ),
        )
    retry_call = _project_tool_call(call, attempt_count=2)
    with pytest.raises(ValidationError):
        ToolCallRecoveryAggregate(
            tool_call_record=retry_call,
            tool_attempt_records=(
                ToolAttemptRecord(
                    tool_call_id=call.tool_call_id,
                    attempt_no=1,
                    started_at=UTC_NOW,
                    finished_at=UTC_NOW + timedelta(milliseconds=1),
                    outcome=ToolResultOutcome.SYSTEM_FAILURE,
                    failure_code="FIRST_ATTEMPT_FAILED",
                ),
                ToolAttemptRecord(
                    tool_call_id=call.tool_call_id,
                    attempt_no=2,
                    started_at=UTC_NOW + timedelta(milliseconds=2),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="does not accept retry"):
        ToolCallRecoveryAggregate(
            tool_call_record=retry_call,
            tool_attempt_records=(attempt,),
        )
    for field_name, field_value in (
        ("failure_code", "STALE_FAILURE"),
        ("result_ref", uuid4()),
    ):
        with pytest.raises(
            ValidationError,
            match="active ToolCall cannot carry failure or result",
        ):
            ToolCallRecoveryAggregate(
                tool_call_record=_project_tool_call(
                    call,
                    **{field_name: field_value},
                ),
                tool_attempt_records=(attempt,),
            )
        with pytest.raises(
            ValidationError,
            match="active ToolCall cannot carry failure or result",
        ):
            ToolCallRecoveryAggregate(
                tool_call_record=_project_tool_call(
                    created,
                    **{field_name: field_value},
                ),
                tool_attempt_records=(),
            )


def test_tool_call_recovery_aggregate_binds_terminal_attempt_projection() -> None:
    finished_at = UTC_NOW + timedelta(milliseconds=1)
    call = _tool_call(
        status=ToolCallStatus.FAILED,
        attempt_count=1,
        finished_at=finished_at,
        failure_code="UPSTREAM_FAILURE",
    )
    attempt = ToolAttemptRecord(
        tool_call_id=call.tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=finished_at,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="UPSTREAM_FAILURE",
    )

    assert (
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(attempt,),
        ).tool_attempt_records[0]
        == attempt
    )
    with pytest.raises(ValidationError, match="timestamps must match"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(
                _rebuild(
                    attempt,
                    finished_at=finished_at + timedelta(milliseconds=1),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="failure_code must match"):
        ToolCallRecoveryAggregate(
            tool_call_record=call,
            tool_attempt_records=(_rebuild(attempt, failure_code="DIFFERENT_FAILURE"),),
        )


def test_restart_recovery_closure_rejects_cross_graph_duplicates_and_orphans() -> None:
    closure = _restart_recovery_closure()
    task_aggregate = closure.task_aggregates[0]
    request_unit = closure.request_unit_records[0]
    tool_aggregate = closure.tool_call_aggregates[0]

    assert closure.active_run_record.conversation_id == (
        closure.conversation_record.conversation_id
    )
    assert closure.run_task_links[0].task_id == task_aggregate.task_record.task_id
    assert request_unit.task_id == task_aggregate.task_record.task_id
    assert tool_aggregate.tool_call_record.request_unit_id == (
        request_unit.request_unit_id
    )
    for forbidden_claim in (
        "database_closed_set_complete",
        "snapshot_complete",
        "owner_scope",
        "recovery_ready",
    ):
        assert not hasattr(closure, forbidden_claim)

    with pytest.raises(ValidationError, match="active Run"):
        _rebuild(
            closure,
            active_run_record=_project_run(
                closure.active_run_record,
                status=AgentRunStatus.INCOMPLETE,
                completed_at=UTC_NOW + timedelta(seconds=1),
                stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            ),
        )
    with pytest.raises(ValidationError, match="incomplete_reason"):
        _rebuild(
            closure,
            active_run_record=_project_run(
                closure.active_run_record,
                incomplete_reason="PROCESS_RESTART_DETECTED",
            ),
        )
    with pytest.raises(ValidationError, match="Conversation"):
        _rebuild(
            closure,
            active_run_record=_project_run(
                closure.active_run_record,
                conversation_id=None,
            ),
        )
    with pytest.raises(ValidationError, match="owner"):
        _rebuild(
            closure,
            task_aggregates=(
                TaskRecoveryAggregate(
                    task_record=_rebuild(
                        task_aggregate.task_record,
                        owner_customer_id="customer-B",
                    ),
                    task_state_transitions=(task_aggregate.task_state_transitions),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="RunTaskLink"):
        _rebuild(
            closure,
            run_task_links=(_rebuild(closure.run_task_links[0], run_id=uuid4()),),
        )
    with pytest.raises(ValidationError, match="base version"):
        _rebuild(
            closure,
            run_task_links=(
                _rebuild(
                    closure.run_task_links[0],
                    base_task_state_version=3,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="ConversationTaskLink"):
        _rebuild(closure, conversation_task_links=())
    with pytest.raises(ValidationError, match="RequestUnit closed set"):
        _rebuild(closure, request_unit_records=())
    with pytest.raises(ValidationError):
        _rebuild(
            closure,
            request_unit_records=(request_unit, request_unit),
        )
    with pytest.raises(ValidationError, match="ToolCall owner graph"):
        _rebuild(
            closure,
            tool_call_aggregates=(
                ToolCallRecoveryAggregate(
                    tool_call_record=_project_tool_call(
                        tool_aggregate.tool_call_record,
                        run_id=uuid4(),
                    ),
                    tool_attempt_records=tool_aggregate.tool_attempt_records,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="validated Task version"):
        _rebuild(
            closure,
            tool_call_aggregates=(
                ToolCallRecoveryAggregate(
                    tool_call_record=_project_tool_call(
                        tool_aggregate.tool_call_record,
                        validated_task_state_version=1,
                    ),
                    tool_attempt_records=tool_aggregate.tool_attempt_records,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="argument bindings"):
        _rebuild(
            closure,
            tool_call_aggregates=(
                ToolCallRecoveryAggregate(
                    tool_call_record=_project_tool_call(
                        tool_aggregate.tool_call_record,
                        argument_binding_refs=(uuid4(),),
                    ),
                    tool_attempt_records=tool_aggregate.tool_attempt_records,
                ),
            ),
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "conversation_task_links",
        "run_task_links",
        "task_aggregates",
        "request_unit_records",
        "tool_call_aggregates",
    ),
)
def test_created_run_recovery_accepts_only_an_empty_pre_graph(
    field_name: str,
) -> None:
    created_closure = _created_restart_recovery_closure()
    running_closure = _restart_recovery_closure()

    assert created_closure.active_run_record.status is AgentRunStatus.CREATED
    assert all(
        getattr(created_closure, supplied_field) == ()
        for supplied_field in (
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        )
    )
    with pytest.raises(
        ValidationError, match="CREATED Run recovery graph must be empty"
    ):
        _rebuild(
            created_closure,
            **{field_name: getattr(running_closure, field_name)},
        )


def test_created_run_empty_recovery_apply_is_a_valid_total_projection() -> None:
    command = _created_restart_recovery_command()

    assert command.expected_closure.active_run_record.status is AgentRunStatus.CREATED
    assert command.run_transition.incomplete_record.status is AgentRunStatus.INCOMPLETE
    assert command.tool_call_transitions == ()
    assert command.task_transitions == ()
    assert command.terminal_run_task_links == ()
    assert len(command.recovery_trace_events) == 1
    assert command.recovery_trace_events[0].event_type is TraceEventType.RUN_STOPPED


def test_restart_recovery_requires_the_exact_bounded_trace_event_set() -> None:
    created_command = _created_restart_recovery_command()
    running_command = _restart_recovery_command()
    running_events = running_command.recovery_trace_events

    assert {event.event_type for event in running_events} == {
        TraceEventType.RUN_STOPPED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.TOOL_CALL_INTERRUPTED,
    }
    assert len({event.trace_event_id for event in running_events}) == 3

    with pytest.raises(ValidationError):
        _rebuild(created_command, recovery_trace_events=())
    with pytest.raises(ValidationError):
        _rebuild(
            running_command,
            recovery_trace_events=(*running_events, running_events[0]),
        )

    unrelated_event = TraceEvent(
        trace_event_id=uuid4(),
        event_type=TraceEventType.RUN_STARTED,
        occurred_at=created_command.run_transition.incomplete_record.completed_at,
        run_id=created_command.expected_closure.active_run_record.run_id,
    )
    with pytest.raises(ValidationError, match="recovery Trace event type"):
        _rebuild(
            created_command,
            recovery_trace_events=(
                created_command.recovery_trace_events[0],
                unrelated_event,
            ),
        )

    duplicate_id_events = list(running_events)
    duplicate_id_events[1] = duplicate_id_events[1].model_copy(
        update={"trace_event_id": duplicate_id_events[0].trace_event_id}
    )
    with pytest.raises(ValidationError, match="Trace event identities"):
        _rebuild(
            running_command,
            recovery_trace_events=tuple(duplicate_id_events),
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"trace_event_id": "not-a-uuid"},
        {"trace_event_id": []},
        {"case_id": ()},
        {"argument_binding_refs": None},
    ),
)
def test_restart_recovery_strictly_revalidates_nested_trace_event_known_fields(
    updates: dict[str, object],
) -> None:
    command = _restart_recovery_command()

    with pytest.raises(ValidationError):
        _rebuild(
            command,
            recovery_trace_events=_updated_recovery_trace_events(
                command,
                TraceEventType.RUN_STOPPED,
                **updates,
            ),
        )


def test_restart_recovery_rejects_hidden_nested_trace_event_fields() -> None:
    command = _restart_recovery_command()
    events = _updated_recovery_trace_events(
        command,
        TraceEventType.RUN_STOPPED,
        secret="must-not-cross-application-boundary",
    )
    injected_event = next(
        event for event in events if event.event_type is TraceEventType.RUN_STOPPED
    )

    assert "secret" in vars(injected_event)
    assert "secret" in injected_event.model_fields_set
    assert "secret" not in injected_event.model_dump(mode="python")
    with pytest.raises(ValidationError):
        _rebuild(command, recovery_trace_events=events)


@pytest.mark.parametrize(
    "storage_attribute",
    ("__pydantic_extra__", "__pydantic_private__"),
)
def test_restart_recovery_rejects_hidden_nested_trace_event_storage(
    storage_attribute: str,
) -> None:
    command = _restart_recovery_command()
    events = _updated_recovery_trace_events(
        command,
        TraceEventType.RUN_STOPPED,
    )
    injected_event = next(
        event for event in events if event.event_type is TraceEventType.RUN_STOPPED
    )
    object.__setattr__(
        injected_event,
        storage_attribute,
        {"secret": "must-not-be-silently-stripped"},
    )

    with pytest.raises(ValidationError):
        _rebuild(command, recovery_trace_events=events)


@pytest.mark.parametrize(
    ("missing_event_type", "error_match"),
    (
        (TraceEventType.RUN_STOPPED, "exactly one RunStopped"),
        (TraceEventType.TASK_STATE_CHANGED, "TaskStateChanged event set"),
        (TraceEventType.TOOL_CALL_INTERRUPTED, "ToolCallInterrupted event set"),
    ),
)
def test_restart_recovery_rejects_every_missing_event_family(
    missing_event_type: TraceEventType,
    error_match: str,
) -> None:
    command = _restart_recovery_command()
    events = tuple(
        event
        for event in command.recovery_trace_events
        if event.event_type is not missing_event_type
    )

    with pytest.raises(ValidationError, match=error_match):
        _rebuild(command, recovery_trace_events=events)


@pytest.mark.parametrize(
    ("event_type", "updates", "error_match"),
    (
        (
            TraceEventType.RUN_STOPPED,
            {"run_id": uuid4()},
            "same recovery Run",
        ),
        (
            TraceEventType.RUN_STOPPED,
            {"user_outcome": AgentOutcome.COMPLETED},
            "BLOCKED",
        ),
        (
            TraceEventType.RUN_STOPPED,
            {"stop_reason": StopReason.GOAL_COMPLETED},
            "PROCESS_RESTART_DETECTED",
        ),
        (
            TraceEventType.RUN_STOPPED,
            {"occurred_at": UTC_NOW},
            "Run completion timestamp",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"run_id": uuid4()},
            "same recovery Run",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"task_id": uuid4()},
            "TaskStateChanged event set",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"request_unit_id": uuid4()},
            "TaskStateChanged event set",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"occurred_at": UTC_NOW},
            "Task transition timestamp",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"run_id": uuid4()},
            "same recovery Run",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"tool_call_id": uuid4()},
            "ToolCallInterrupted event set",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"tool_call_terminal_status": ToolCallStatus.FAILED},
            "status must match|INTERRUPTED",
        ),
        (
            TraceEventType.TOOL_CALL_INTERRUPTED,
            {"occurred_at": UTC_NOW},
            "ToolCall interruption timestamp",
        ),
        (
            TraceEventType.TASK_STATE_CHANGED,
            {"event_type": TraceEventType.RUN_STARTED},
            "recovery Trace event type",
        ),
    ),
)
def test_restart_recovery_trace_binds_kind_identity_status_and_timestamp(
    event_type: TraceEventType,
    updates: dict[str, object],
    error_match: str,
) -> None:
    command = _restart_recovery_command()

    with pytest.raises(ValidationError, match=error_match):
        _rebuild(
            command,
            recovery_trace_events=_updated_recovery_trace_events(
                command,
                event_type,
                **updates,
            ),
        )


@pytest.mark.parametrize(
    ("event_type", "field_name"),
    _RECOVERY_TRACE_CONTAMINATION_CASES,
)
def test_restart_recovery_trace_rejects_every_cross_kind_or_unrelated_projection(
    event_type: TraceEventType,
    field_name: str,
) -> None:
    command = _restart_recovery_command()

    with pytest.raises(ValidationError):
        _rebuild(
            command,
            recovery_trace_events=_updated_recovery_trace_events(
                command,
                event_type,
                **{field_name: _non_empty_trace_optional_value(field_name)},
            ),
        )


def test_running_run_recovery_allows_zero_or_one_closed_graph() -> None:
    created_closure = _created_restart_recovery_closure()
    empty_running_closure = _rebuild(
        created_closure,
        active_run_record=_project_run(
            created_closure.active_run_record,
            status=AgentRunStatus.RUNNING,
        ),
    )
    one_graph_closure = _restart_recovery_closure()

    assert empty_running_closure.active_run_record.status is AgentRunStatus.RUNNING
    assert all(
        getattr(empty_running_closure, field_name) == ()
        for field_name in (
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        )
    )
    assert all(
        len(getattr(one_graph_closure, field_name)) == 1
        for field_name in (
            "conversation_task_links",
            "run_task_links",
            "task_aggregates",
            "request_unit_records",
            "tool_call_aggregates",
        )
    )


def test_restart_recovery_apply_is_bijective_and_fence_bound() -> None:
    command = _restart_recovery_command()
    closure = command.expected_closure

    assert command.run_transition.expected_active_record == (closure.active_run_record)
    assert {
        item.active_record.tool_call_id for item in command.tool_call_transitions
    } == {item.tool_call_record.tool_call_id for item in closure.tool_call_aggregates}
    assert {item.expected_task_record.task_id for item in command.task_transitions} == {
        item.task_record.task_id for item in closure.task_aggregates
    }
    assert command.terminal_run_task_links[0].result_task_state_version == 3

    with pytest.raises(ValidationError, match="expected closure Run"):
        _rebuild(
            command,
            run_transition=MarkRunIncompleteForRecoveryCommand(
                expected_active_record=_project_run(
                    closure.active_run_record,
                    provider_lane="other",
                ),
                incomplete_record=_project_run(
                    command.run_transition.incomplete_record,
                    provider_lane="other",
                ),
            ),
        )
    with pytest.raises(ValidationError, match="ToolCall transition set"):
        _rebuild(command, tool_call_transitions=())
    with pytest.raises(ValidationError, match="Task transition set"):
        _rebuild(command, task_transitions=())
    with pytest.raises(ValidationError, match="RunTaskLink set"):
        _rebuild(command, terminal_run_task_links=())
    with pytest.raises(ValidationError, match="result Task version"):
        _rebuild(
            command,
            terminal_run_task_links=(
                _rebuild(
                    command.terminal_run_task_links[0],
                    result_task_state_version=2,
                ),
            ),
        )

    assert set(RecoveryWriteResult) == {
        RecoveryWriteResult.APPLIED,
        RecoveryWriteResult.CLOSURE_CONFLICT,
        RecoveryWriteResult.NOT_APPLICABLE,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    }


def test_running_action_recovery_command_preserves_reconciliation_candidate() -> None:
    command = _restart_recovery_command()
    closure = command.expected_closure
    tool_aggregate = closure.tool_call_aggregates[0]
    action_call = _project_tool_call(
        tool_aggregate.tool_call_record,
        effect=ToolEffect.ACTION,
        canonical_tool_name="create_refund",
    )
    action_aggregate = ToolCallRecoveryAggregate(
        tool_call_record=action_call,
        tool_attempt_records=tool_aggregate.tool_attempt_records,
    )
    action_closure = _rebuild(
        closure,
        tool_call_aggregates=(action_aggregate,),
    )
    action_transition = InterruptToolCallForRecoveryCommand(
        active_record=action_call,
        interrupted_record=_project_tool_call(
            action_call,
            status=ToolCallStatus.INTERRUPTED,
            finished_at=UTC_NOW + timedelta(milliseconds=2),
            interruption_reason="PROCESS_RESTART_DETECTED",
        ),
    )
    action_command = ApplyRestartRecoveryCommand(
        expected_closure=action_closure,
        run_transition=command.run_transition,
        tool_call_transitions=(action_transition,),
        task_transitions=command.task_transitions,
        terminal_run_task_links=command.terminal_run_task_links,
        recovery_trace_events=_recovery_trace_events(
            run_transition=command.run_transition,
            task_transitions=command.task_transitions,
            tool_call_transitions=(action_transition,),
        ),
    )

    assert action_command.tool_call_transitions[0].active_record.effect is (
        ToolEffect.ACTION
    )
    assert action_command.tool_call_transitions[0].interrupted_record.status is (
        ToolCallStatus.INTERRUPTED
    )
    assert RecoveryWriteResult.RECONCILIATION_REQUIRED.value == (
        "RECONCILIATION_REQUIRED"
    )


def test_eval_projection_uses_explicit_validated_details() -> None:
    result = _eval_result()

    assert result.version_manifest.dataset_version == "e2e01-thin-dataset-v1"
    assert result.version_manifest.candidate_version == "candidate-source-revision"
    assert result.version_manifest.baseline_version is None
    assert result.version_manifest.fixture_versions == ("e2e01-thin-fixture-v1",)
    assert result.version_manifest.model_config_version == "scripted-provider-v1"
    with pytest.raises(ValidationError, match="Extra inputs"):
        EvalGraderResult(
            grader_name="TraceCompletenessGrader",
            status=EvalGraderStatus.PASS,
            arbitrary_details={"unsafe": "payload"},
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        _version_manifest(arbitrary_versions={"prompt": "floating"})
    with pytest.raises(ValidationError, match="fixture_versions must be unique"):
        _version_manifest(fixture_versions=("fixture-v1", "fixture-v1"))


@pytest.mark.parametrize(
    "code_shaped_secret",
    (
        "AKIAIOSFODNN7EXAMPLE",
        "PASSWORD_TOPSECRET",
        "CUSTOMER_EMAIL_ALICE_EXAMPLE_COM",
        "SSN_123_45_6789",
    ),
)
def test_eval_code_catalogs_reject_code_shaped_secrets(
    code_shaped_secret: str,
) -> None:
    with pytest.raises(ValidationError):
        _eval_execution_failure(safe_error_code=code_shaped_secret)
    with pytest.raises(ValidationError):
        EvalGraderResult(
            grader_name="TraceCompletenessGrader",
            status=EvalGraderStatus.FAIL,
            reason_code=code_shaped_secret,
        )
    with pytest.raises(ValidationError):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(_passing_grader(),),
            critical_failures=(code_shaped_secret,),
        )


def test_eval_execution_error_catalog_covers_every_failure_phase() -> None:
    catalog = {
        EvalExecutionFailurePhase.HARNESS_SETUP: (
            EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED
        ),
        EvalExecutionFailurePhase.CASE_SETUP: (
            EvalExecutionSafeErrorCode.CASE_SETUP_FAILED
        ),
        EvalExecutionFailurePhase.TRACE_PERSISTENCE: (
            EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE
        ),
        EvalExecutionFailurePhase.SYSTEM_UNDER_TEST: (
            EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED
        ),
        EvalExecutionFailurePhase.GRADING: (EvalExecutionSafeErrorCode.GRADING_FAILED),
        EvalExecutionFailurePhase.RESULT_PERSISTENCE: (
            EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED
        ),
        EvalExecutionFailurePhase.RESULT_COMPLETENESS: (
            EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED
        ),
    }

    assert set(catalog) == set(EvalExecutionFailurePhase)
    assert set(EvalExecutionSafeErrorCode) == {
        EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED,
        EvalExecutionSafeErrorCode.CASE_SETUP_FAILED,
        EvalExecutionSafeErrorCode.TRACE_PERSISTENCE_FAILED,
        EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED,
        EvalExecutionSafeErrorCode.GRADING_FAILED,
        EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED,
        EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED,
    }
    for phase, code in catalog.items():
        failure = _eval_execution_failure(
            failure_phase=phase,
            safe_error_code=code,
        )
        assert failure.safe_error_code is code
    with pytest.raises(ValidationError, match="must match failure_phase"):
        _eval_execution_failure(
            failure_phase=EvalExecutionFailurePhase.GRADING,
            safe_error_code=EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
        )


def test_eval_grader_and_critical_failure_catalogs_are_closed() -> None:
    assert set(EvalGraderReasonCode) == {
        EvalGraderReasonCode.TRACE_EVENT_MISSING,
        EvalGraderReasonCode.MISSING_RECORD,
        EvalGraderReasonCode.ASSERTION_FAILED,
    }
    expected_critical_values = {f"CF-{index:02d}" for index in range(1, 15)}
    assert {code.value for code in CriticalFailureCode} == expected_critical_values

    for code in CriticalFailureCode:
        result = _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(_passing_grader(),),
            critical_failures=(code,),
        )
        assert result.critical_failures == (code,)
    with pytest.raises(ValidationError):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(_passing_grader(),),
            critical_failures=("CF-15",),
        )


def test_eval_execution_failure_is_typed_and_does_not_fabricate_case_result() -> None:
    failure = _eval_execution_failure(
        case_id=None,
        attempt=None,
        failure_phase=EvalExecutionFailurePhase.HARNESS_SETUP,
        safe_error_code=EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED,
        diagnostic_ref=None,
    )

    assert failure.case_id is None
    assert failure.trace_ref is None
    assert "status" not in type(failure).model_fields
    assert "observed_outcome" not in type(failure).model_fields
    assert "grader_results" not in type(failure).model_fields
    assert set(EvalExecutionFailurePhase) == {
        EvalExecutionFailurePhase.HARNESS_SETUP,
        EvalExecutionFailurePhase.CASE_SETUP,
        EvalExecutionFailurePhase.TRACE_PERSISTENCE,
        EvalExecutionFailurePhase.SYSTEM_UNDER_TEST,
        EvalExecutionFailurePhase.GRADING,
        EvalExecutionFailurePhase.RESULT_PERSISTENCE,
        EvalExecutionFailurePhase.RESULT_COMPLETENESS,
    }
    with pytest.raises(ValidationError, match="attempt requires case_id"):
        _eval_execution_failure(case_id=None, attempt=1)
    with pytest.raises(ValidationError, match="Extra inputs"):
        _eval_execution_failure(raw_error="provider stack trace")


def test_eval_critical_failure_forces_fail_and_cannot_coexist_with_pass() -> None:
    critical_failure = (CriticalFailureCode.CF_01,)

    failed = _eval_result(
        status=EvalResultStatus.FAIL,
        grader_results=(_passing_grader(),),
        critical_failures=critical_failure,
    )
    assert failed.status is EvalResultStatus.FAIL

    for status in (
        EvalResultStatus.PASS,
        EvalResultStatus.SKIPPED,
        EvalResultStatus.NOT_RUN,
    ):
        with pytest.raises(ValidationError, match="critical failure"):
            _eval_result(status=status, critical_failures=critical_failure)


def test_eval_fail_does_not_require_a_critical_failure() -> None:
    failed = _eval_result(
        status=EvalResultStatus.FAIL,
        grader_results=(
            EvalGraderResult(
                grader_name="TraceCompletenessGrader",
                status=EvalGraderStatus.FAIL,
                reason_code=EvalGraderReasonCode.TRACE_EVENT_MISSING,
            ),
        ),
    )

    assert failed.critical_failures == ()
    with pytest.raises(ValidationError, match="at least one grader"):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(),
        )
    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=EvalResultStatus.SKIPPED,
            grader_results=failed.grader_results,
            observed_outcome=None,
            trace_ref=None,
        )


def test_eval_pass_requires_non_empty_passing_graders() -> None:
    with pytest.raises(ValidationError, match="at least one grader"):
        _eval_result(grader_results=())
    with pytest.raises(ValidationError, match="non-empty passing"):
        _eval_result(
            grader_results=(
                EvalGraderResult(
                    grader_name="PersistenceGrader",
                    status=EvalGraderStatus.FAIL,
                    reason_code=EvalGraderReasonCode.MISSING_RECORD,
                ),
            )
        )


@pytest.mark.parametrize(
    "status",
    (EvalResultStatus.SKIPPED, EvalResultStatus.NOT_RUN),
)
def test_eval_non_execution_statuses_carry_no_run_or_grading_data(
    status: EvalResultStatus,
) -> None:
    disposition = _eval_result(
        status=status,
        grader_results=(),
        critical_failures=(),
        observed_outcome=None,
        trace_ref=None,
        latency_summary=None,
        usage_summary=None,
    )
    assert disposition.status is status

    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=status,
            grader_results=(),
            critical_failures=(),
        )
    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=status,
            grader_results=(),
            critical_failures=(),
            observed_outcome=None,
            trace_ref=None,
            latency_summary=EvalLatencySummary(total_duration_ms=1),
            usage_summary=None,
        )
    with pytest.raises(ValidationError, match="cannot carry"):
        _eval_result(
            status=status,
            grader_results=(),
            critical_failures=(),
            observed_outcome=None,
            trace_ref=None,
            latency_summary=None,
            usage_summary=EvalUsageSummary(input_tokens=0, output_tokens=0),
        )


def test_eval_projection_rejects_duplicate_grader_and_failure_codes() -> None:
    grader = _passing_grader()
    with pytest.raises(ValidationError, match="unique grader"):
        _eval_result(grader_results=(grader, grader))
    with pytest.raises(ValidationError, match="unique stable codes"):
        _eval_result(
            status=EvalResultStatus.FAIL,
            grader_results=(grader,),
            critical_failures=(
                CriticalFailureCode.CF_01,
                CriticalFailureCode.CF_01,
            ),
        )


_EXACT_EVIDENCE_FIELD_NAMES = (
    "conversation_record",
    "run_record",
    "message_records",
    "request_understanding_record",
    "accepted_task_deltas",
    "input_binding_records",
    "task_records",
    "task_state_transitions",
    "request_unit_records",
    "conversation_task_links",
    "run_task_links",
    "gate_decisions",
    "tool_calls",
    "tool_attempts",
    "observation_records",
    "context_manifests",
    "model_visible_toolset_artifacts",
    "trace_events",
)


def _exact_evidence_artifact() -> ModelVisibleToolsetArtifact:
    tool_spec = get_order_tool_spec()
    return ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=compute_model_visible_toolset_hash((tool_spec,)),
        provider_visible_tool_specs=(tool_spec,),
    )


def _exact_evidence_trace(
    *,
    event_type: TraceEventType,
    run_id: UUID,
    occurred_at: datetime = UTC_NOW,
    **updates: object,
) -> TraceEvent:
    values: dict[str, object] = {
        "trace_event_id": uuid4(),
        "event_type": event_type,
        "occurred_at": occurred_at,
        "run_id": run_id,
    }
    values.update(updates)
    return TraceEvent(**values)


def _minimal_exact_run_evidence() -> ExactRunEvidenceClosure:
    conversation = _conversation(
        schema_version="conversation_record.p0.v1",
    )
    message = _message(
        schema_version="message_record.p0.v1",
        conversation_id=conversation.conversation_id,
    )
    run = _run(
        conversation_id=conversation.conversation_id,
        status=AgentRunStatus.COMPLETED,
        completed_at=UTC_NOW + timedelta(milliseconds=10),
        stop_reason=StopReason.INPUT_INVALID,
    )
    artifact = _exact_evidence_artifact()
    model_call_id = uuid4()
    manifest = ContextManifest(
        context_manifest_id=uuid4(),
        run_id=run.run_id,
        model_call_id=model_call_id,
        tool_registry_version="e2e01-thin-tools-v1",
        model_visible_toolset_hash=artifact.model_visible_toolset_hash,
        selected_message_refs=(message.message_id,),
        redaction_policy_version="e2e01-thin-redaction-v1",
        token_counts=TokenCounts(input_tokens=4, output_tokens=0),
        assembled_at=UTC_NOW,
    )
    traces = (
        _exact_evidence_trace(
            event_type=TraceEventType.MESSAGE_ACCEPTED,
            run_id=run.run_id,
            message_ref=message.message_id,
        ),
        _exact_evidence_trace(
            event_type=TraceEventType.CONTEXT_MANIFEST_RECORDED,
            run_id=run.run_id,
            model_call_id=model_call_id,
            context_manifest_id=manifest.context_manifest_id,
            model_visible_toolset_hash=artifact.model_visible_toolset_hash,
        ),
        _exact_evidence_trace(
            event_type=TraceEventType.RUN_STOPPED,
            run_id=run.run_id,
            occurred_at=run.completed_at,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=run.stop_reason,
        ),
    )
    return ExactRunEvidenceClosure(
        conversation_record=conversation,
        run_record=run,
        message_records=(message,),
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


def _rebuild_exact_run_evidence(
    closure: ExactRunEvidenceClosure,
    **updates: object,
) -> ExactRunEvidenceClosure:
    values = {
        field_name: getattr(closure, field_name)
        for field_name in ExactRunEvidenceClosure.model_fields
    }
    values.update(updates)
    return ExactRunEvidenceClosure(**values)


def _durable_evidence_candidate(
    *,
    candidate_id: UUID,
    message: MessageRecord,
    order_id: str,
) -> DurableTaskDeltaCandidateV2:
    start = message.content.index(order_id)
    end = start + len(order_id)
    quote_hash = sha256(message.content[start:end].encode("utf-8")).hexdigest()
    return DurableTaskDeltaCandidateV2(
        candidate_id=candidate_id,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch=f"查询订单 {order_id}",
        input_candidates=(
            DurableInputCandidateV2(
                name="order_id",
                candidate_value=order_id,
                semantic_role="TARGET_RESOURCE_IDENTIFIER",
                authority=InputAuthority.USER_CLAIM,
                source_kind=InputSourceKind.CURRENT_MESSAGE,
                source_ref=message.message_id,
                source_span_start=start,
                source_span_end_exclusive=end,
                source_quote_sha256=quote_hash,
                confidence=0.99,
            ),
        ),
        confidence=0.98,
    )


def _request_understanding_exact_run_evidence(
    *,
    candidate_count: int,
    accepted_count: int,
) -> ExactRunEvidenceClosure:
    if not 0 <= accepted_count <= candidate_count <= 2:
        raise ValueError("test fixture supports 0..2 candidates")
    base = _minimal_exact_run_evidence()
    stop_reason = (
        StopReason.GOAL_COMPLETED
        if accepted_count
        else StopReason.INPUT_INVALID
    )
    user_outcome = (
        AgentOutcome.COMPLETED
        if accepted_count
        else AgentOutcome.BLOCKED
    )
    completed_run = _project_run(
        base.run_record,
        stop_reason=stop_reason,
    )
    message = MessageRecord(
        schema_version="message_record.p0.v1",
        message_id=base.message_records[0].message_id,
        conversation_id=base.conversation_record.conversation_id,
        direction=MessageDirection.USER,
        content="查订单 O-1001 和 O-1002",
        received_at=UTC_NOW,
    )
    candidate_ids = tuple(uuid4() for _ in range(candidate_count))
    candidates = tuple(
        _durable_evidence_candidate(
            candidate_id=candidate_id,
            message=message,
            order_id=f"O-{1001 + index}",
        )
        for index, candidate_id in enumerate(candidate_ids)
    )
    decisions = tuple(
        CandidateValidationRecordV2(
            candidate_ref=candidate_id,
            decision=(
                CandidateValidationDecision.ACCEPT
                if index < accepted_count
                else CandidateValidationDecision.REJECT
            ),
            reason_code=(
                None
                if index < accepted_count
                else CandidateRejectionReasonCode.INPUT_VALUE_INVALID
            ),
        )
        for index, candidate_id in enumerate(candidate_ids)
    )

    children: list[AcceptedTaskDeltaV2] = []
    bindings: list[InputBinding] = []
    tasks: list[TaskRecord] = []
    units: list[RequestUnitRecord] = []
    transitions: list[TaskStateTransition] = []
    conversation_links: list[ConversationTaskLinkRecord] = []
    run_links: list[RunTaskLinkRecord] = []
    traces = [
        _exact_evidence_trace(
            event_type=TraceEventType.MESSAGE_ACCEPTED,
            run_id=completed_run.run_id,
            message_ref=message.message_id,
        ),
        _exact_evidence_trace(
            event_type=TraceEventType.CONTEXT_MANIFEST_RECORDED,
            run_id=completed_run.run_id,
            model_call_id=base.context_manifests[0].model_call_id,
            context_manifest_id=base.context_manifests[0].context_manifest_id,
            model_visible_toolset_hash=(
                base.model_visible_toolset_artifacts[0].model_visible_toolset_hash
            ),
        ),
    ]
    for index, candidate in enumerate(candidates[:accepted_count]):
        binding = _input_binding(
            normalized_value=f"O-{1001 + index}",
            source_refs=(message.message_id,),
        )
        task = _task(
            status=TaskStatus.COMPLETED,
            state_version=2,
            updated_at=UTC_NOW + timedelta(milliseconds=1),
        )
        unit = _request_unit(
            task_id=task.task_id,
            goal_text=candidate.goal_patch,
            goal_source_refs=(message.message_id,),
            input_binding_refs=(binding.binding_id,),
            status=TaskStatus.COMPLETED,
            state_version=2,
            updated_at=UTC_NOW + timedelta(milliseconds=1),
        )
        child = AcceptedTaskDeltaV2(
            accepted_delta_id=uuid4(),
            candidate_ref=candidate.candidate_id,
            message_ref=message.message_id,
            operation=candidate.operation,
            goal_text=candidate.goal_patch,
            input_binding_refs=(binding.binding_id,),
            accepted_at=UTC_NOW,
            task_id=task.task_id,
            base_task_state_version=None,
            result_task_state_version=1,
        )
        transition = _task_transition(
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            from_status=TaskStatus.ACTIVE,
            to_status=TaskStatus.COMPLETED,
            changed_at=UTC_NOW + timedelta(milliseconds=1),
        )
        children.append(child)
        bindings.append(binding)
        tasks.append(task)
        units.append(unit)
        transitions.append(transition)
        conversation_links.append(
            _conversation_task_link(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=base.conversation_record.conversation_id,
                task_id=task.task_id,
            )
        )
        run_links.append(
            _run_task_link(
                schema_version="run_task_link_record.p0.v1",
                run_id=base.run_record.run_id,
                task_id=task.task_id,
                base_task_state_version=None,
                result_task_state_version=2,
            )
        )
        traces.extend(
            (
                _exact_evidence_trace(
                    event_type=TraceEventType.TASK_DELTA_ACCEPTED,
                    run_id=completed_run.run_id,
                    message_ref=message.message_id,
                    accepted_delta_ref=child.accepted_delta_id,
                    task_id=task.task_id,
                ),
                _exact_evidence_trace(
                    event_type=TraceEventType.INPUT_BINDING_RECORDED,
                    run_id=completed_run.run_id,
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                    input_binding_ref=binding.binding_id,
                ),
                _exact_evidence_trace(
                    event_type=TraceEventType.TASK_STATE_CHANGED,
                    run_id=completed_run.run_id,
                    occurred_at=transition.changed_at,
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                ),
            )
        )
    record = RequestUnderstandingRecordV2(
        request_understanding_record_id=uuid4(),
        run_id=completed_run.run_id,
        message_ref=message.message_id,
        schema_version="request_understanding_record.p0.v2",
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-thin-v2",
        contextualization=DurableQueryContextualizationCandidateV2(
            text="查询当前消息中的订单",
            resolved_reference_candidates=(),
            uncertainties=(),
            source_message_refs=(message.message_id,),
        ),
        task_delta_candidates=candidates,
        candidate_validation=decisions,
        accepted_delta_refs=tuple(child.accepted_delta_id for child in children),
        proposed_base_task_state_version=None,
        validated_task_state_version=None,
        next_move_candidate_ref=None,
        created_at=UTC_NOW,
    )
    traces.append(
        _exact_evidence_trace(
            event_type=TraceEventType.RUN_STOPPED,
            run_id=completed_run.run_id,
            occurred_at=completed_run.completed_at,
            user_outcome=user_outcome,
            stop_reason=completed_run.stop_reason,
        )
    )
    return _rebuild_exact_run_evidence(
        base,
        run_record=completed_run,
        message_records=(message,),
        request_understanding_record=record,
        accepted_task_deltas=tuple(children),
        input_binding_records=tuple(bindings),
        task_records=tuple(tasks),
        task_state_transitions=tuple(transitions),
        request_unit_records=tuple(units),
        conversation_task_links=tuple(conversation_links),
        run_task_links=tuple(run_links),
        trace_events=tuple(traces),
    )


def _tool_exact_run_evidence() -> ExactRunEvidenceClosure:
    base = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    binding = base.input_binding_records[0]
    task = base.task_records[0]
    unit = base.request_unit_records[0]
    manifest = base.context_manifests[0]
    gate = GateDecision(
        gate_decision_id=uuid4(),
        model_call_id=manifest.model_call_id,
        context_manifest_id=manifest.context_manifest_id,
        requested_provider_tool_name="get_order",
        resolved_canonical_tool_name="get_order",
        snapshot_match=True,
        registration_valid=True,
        schema_valid=True,
        trusted_field_valid=True,
        argument_binding_valid=True,
        argument_binding_refs=(binding.binding_id,),
        budget_valid=True,
        progress_valid=True,
        proposed_base_task_state_version=None,
        validated_task_state_version=1,
        state_version_valid=True,
        action_boundary_valid=True,
        decision=GateDecisionValue.ACCEPT,
        decided_at=UTC_NOW + timedelta(microseconds=100),
    )
    observation = _observation(
        observed_at=UTC_NOW + timedelta(microseconds=300),
        recorded_at=UTC_NOW + timedelta(microseconds=300),
    )
    tool_call = ToolCallRecord(
        tool_call_id=uuid4(),
        run_id=base.run_record.run_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        model_call_id=manifest.model_call_id,
        context_manifest_id=manifest.context_manifest_id,
        gate_decision_id=gate.gate_decision_id,
        canonical_tool_name="get_order",
        tool_registry_version=manifest.tool_registry_version,
        validated_task_state_version=1,
        argument_binding_refs=(binding.binding_id,),
        effect=ToolEffect.READ,
        attempt_count=1,
        status=ToolCallStatus.SUCCEEDED,
        started_at=UTC_NOW + timedelta(microseconds=200),
        finished_at=UTC_NOW + timedelta(microseconds=300),
        result_ref=observation.observation_id,
    )
    attempt = ToolAttemptRecord(
        tool_call_id=tool_call.tool_call_id,
        attempt_no=1,
        started_at=tool_call.started_at,
        finished_at=tool_call.finished_at,
        outcome=ToolResultOutcome.SUCCESS,
    )
    updated_unit = _rebuild(
        unit,
        observation_refs=(observation.observation_id,),
    )
    traces = (
        *base.trace_events[:-1],
        _exact_evidence_trace(
            event_type=TraceEventType.TOOL_CALL_SUCCEEDED,
            run_id=base.run_record.run_id,
            occurred_at=tool_call.finished_at,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            context_manifest_id=manifest.context_manifest_id,
            argument_binding_refs=(binding.binding_id,),
            tool_call_id=tool_call.tool_call_id,
            tool_call_terminal_status=ToolCallStatus.SUCCEEDED,
        ),
        _exact_evidence_trace(
            event_type=TraceEventType.OBSERVATION_RECORDED,
            run_id=base.run_record.run_id,
            occurred_at=observation.recorded_at,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            tool_call_id=tool_call.tool_call_id,
            observation_ref=observation.observation_id,
        ),
        base.trace_events[-1],
    )
    return _rebuild_exact_run_evidence(
        base,
        request_unit_records=(updated_unit,),
        gate_decisions=(gate,),
        tool_calls=(tool_call,),
        tool_attempts=(attempt,),
        observation_records=(observation,),
        trace_events=traces,
    )


def test_request_understanding_candidate_invalid_error_is_bounded_and_distinct() -> None:
    first = RequestUnderstandingCandidateInvalidError()
    second = RequestUnderstandingCandidateInvalidError()

    assert first is not second
    assert first.args == ("REQUEST_UNDERSTANDING_CANDIDATE_INVALID",)
    assert not isinstance(first, ProviderProtocolError)
    assert not isinstance(first, ValueError)
    with pytest.raises(TypeError):
        RequestUnderstandingCandidateInvalidError("raw Pydantic secret")

    def translate_after_discarding_raw_exception() -> None:
        translated: RequestUnderstandingCandidateInvalidError | None = None
        try:
            raise ValidationError.from_exception_data(
                "RawProvider",
                [
                    {
                        "type": "value_error",
                        "loc": ("Token VERY_SECRET",),
                        "input": "customer-A",
                        "ctx": {"error": ValueError("Prompt private")},
                    }
                ],
            )
        except ValidationError:
            translated = RequestUnderstandingCandidateInvalidError()
        raise translated

    with pytest.raises(RequestUnderstandingCandidateInvalidError) as raised:
        translate_after_discarding_raw_exception()
    translated = raised.value
    assert translated.__cause__ is None
    assert translated.__context__ is None
    projection = " ".join((str(translated), repr(translated), repr(translated.args)))
    for secret in ("VERY_SECRET", "customer-A", "Prompt private"):
        assert secret not in projection


def test_exact_run_evidence_closure_has_exact_required_private_surface() -> None:
    expected_types = {
        "conversation_record": ConversationRecord,
        "run_record": AgentRunRecord,
        "message_records": tuple[MessageRecord, ...],
        "request_understanding_record": RequestUnderstandingRecordV2 | None,
        "accepted_task_deltas": tuple[AcceptedTaskDeltaV2, ...],
        "input_binding_records": tuple[InputBinding, ...],
        "task_records": tuple[TaskRecord, ...],
        "task_state_transitions": tuple[TaskStateTransition, ...],
        "request_unit_records": tuple[RequestUnitRecord, ...],
        "conversation_task_links": tuple[ConversationTaskLinkRecord, ...],
        "run_task_links": tuple[RunTaskLinkRecord, ...],
        "gate_decisions": tuple[GateDecision, ...],
        "tool_calls": tuple[ToolCallRecord, ...],
        "tool_attempts": tuple[ToolAttemptRecord, ...],
        "observation_records": tuple[OrderObservation, ...],
        "context_manifests": tuple[ContextManifest, ...],
        "model_visible_toolset_artifacts": tuple[ModelVisibleToolsetArtifact, ...],
        "trace_events": tuple[TraceEvent, ...],
    }
    assert tuple(ExactRunEvidenceClosure.model_fields) == _EXACT_EVIDENCE_FIELD_NAMES
    resolved_types = get_type_hints(ExactRunEvidenceClosure, include_extras=True)
    assert {
        field_name: resolved_types[field_name]
        for field_name in _EXACT_EVIDENCE_FIELD_NAMES
    } == expected_types
    assert all(
        field.is_required()
        for field in ExactRunEvidenceClosure.model_fields.values()
    )
    assert ExactRunEvidenceClosure.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    for forbidden in (
        "case_id",
        "customer_id",
        "eval_evidence",
        "agent_run_result",
        "persistence_envelope",
        "closure_fence",
    ):
        assert forbidden not in ExactRunEvidenceClosure.model_fields

    closure = _minimal_exact_run_evidence()
    with pytest.raises(ValidationError, match="frozen"):
        closure.run_record = closure.run_record
    values = {
        field_name: getattr(closure, field_name)
        for field_name in ExactRunEvidenceClosure.model_fields
    }
    values.pop("tool_calls")
    with pytest.raises(ValidationError, match="tool_calls"):
        ExactRunEvidenceClosure(**values)
    with pytest.raises(ValidationError, match="extra"):
        ExactRunEvidenceClosure(
            **{
                field_name: getattr(closure, field_name)
                for field_name in ExactRunEvidenceClosure.model_fields
            },
            case_id="E2E01-01",
        )


@pytest.mark.parametrize(
    ("candidate_count", "accepted_count"),
    ((0, 0), (2, 0), (2, 1), (2, 2)),
)
def test_exact_run_evidence_accepts_closed_ru_v2_candidate_shapes(
    candidate_count: int,
    accepted_count: int,
) -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=candidate_count,
        accepted_count=accepted_count,
    )
    assert len(closure.request_understanding_record.task_delta_candidates) == (
        candidate_count
    )
    assert len(closure.accepted_task_deltas) == accepted_count
    assert len(closure.task_records) == accepted_count


@pytest.mark.parametrize("candidate_value", ("o-1001", "O-1001"))
def test_exact_run_evidence_normalizes_accepted_candidate_binding_values(
    candidate_value: str,
) -> None:
    closure = _initial_v2_graph_exact_run_evidence(
        candidate_value=candidate_value,
    )
    assert closure.input_binding_records[0].normalized_value == "O-1001"


def test_exact_run_evidence_rejects_wrong_normalized_candidate_binding() -> None:
    with pytest.raises(
        ValidationError,
        match="accepted child bindings must preserve validated input values",
    ):
        _initial_v2_graph_exact_run_evidence(binding_value="O-9999")


def test_exact_run_evidence_rejects_invalid_candidate_without_raw_value() -> None:
    raw_value = "invalid-raw-order-secret"
    with pytest.raises(
        ValidationError,
        match="accepted child bindings must preserve validated input values",
    ) as exc_info:
        _initial_v2_graph_exact_run_evidence(candidate_value=raw_value)

    error = exc_info.value
    projections = (
        str(error),
        repr(error),
        error.json(include_url=False),
        repr(error.errors(include_url=False)),
        repr(error.__cause__),
        repr(error.__context__),
    )
    assert all(raw_value not in projection for projection in projections)
    assert error.errors(include_url=False)[0]["input"] is None
    assert error.__cause__ is None
    assert error.__context__ is None


def test_exact_run_evidence_rejects_extra_candidate_binding_source() -> None:
    with pytest.raises(
        ValidationError,
        match="accepted child bindings must preserve validated input values",
    ):
        _initial_v2_graph_exact_run_evidence(
            include_extra_binding_source=True,
        )


def test_exact_run_evidence_rejects_missing_extra_foreign_or_eval_graph_rows() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=2,
        accepted_count=1,
    )
    child = closure.accepted_task_deltas[0]
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(closure, accepted_task_deltas=())
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            accepted_task_deltas=(child, child),
        )
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            run_task_links=(
                _rebuild(closure.run_task_links[0], run_id=uuid4()),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            task_records=(
                _rebuild(
                    closure.task_records[0],
                    owner_customer_id="customer-B",
                ),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            message_records=(
                *closure.message_records,
                _message(
                    conversation_id=closure.conversation_record.conversation_id,
                ),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(
                *closure.trace_events,
                _exact_evidence_trace(
                    event_type=TraceEventType.RUN_STARTED,
                    run_id=closure.run_record.run_id,
                    case_id="E2E01-01",
                ),
            ),
        )


def test_exact_run_evidence_accepts_two_task_transitions_and_rejects_gaps() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    task = closure.task_records[0]
    unit = closure.request_unit_records[0]
    first = _task_transition(
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        from_status=TaskStatus.ACTIVE,
        to_status=TaskStatus.WAITING_USER,
        base_state_version=1,
        result_state_version=2,
        changed_at=UTC_NOW + timedelta(milliseconds=1),
    )
    second = _task_transition(
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        from_status=TaskStatus.WAITING_USER,
        to_status=TaskStatus.BLOCKED,
        base_state_version=2,
        result_state_version=3,
        changed_at=UTC_NOW + timedelta(milliseconds=2),
    )
    blocked_run = _project_run(
        closure.run_record,
        stop_reason=StopReason.GATE_REJECTED,
    )
    stopped = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    blocked_stopped = _rebuild(
        stopped,
        stop_reason=StopReason.GATE_REJECTED,
        user_outcome=AgentOutcome.BLOCKED,
    )
    stale = _rebuild_exact_run_evidence(
        closure,
        run_record=blocked_run,
        task_records=(
            _rebuild(
                task,
                status=TaskStatus.BLOCKED,
                state_version=3,
                updated_at=second.changed_at,
            ),
        ),
        task_state_transitions=(first, second),
        request_unit_records=(
            _rebuild(
                unit,
                status=TaskStatus.BLOCKED,
                state_version=3,
                updated_at=second.changed_at,
            ),
        ),
        run_task_links=(
            _rebuild(
                closure.run_task_links[0],
                result_task_state_version=3,
            ),
        ),
        trace_events=tuple(
            blocked_stopped if event is stopped else event
            for event in closure.trace_events
        ),
    )
    assert len(stale.task_state_transitions) == 2
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(stale, task_state_transitions=(first,))
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            stale,
            task_state_transitions=(first, _rebuild(second, base_state_version=3)),
        )


def test_exact_run_evidence_closes_tool_attempts_and_top_level_references() -> None:
    closure = _tool_exact_run_evidence()
    assert len(closure.tool_calls) == len(closure.tool_attempts) == 1
    assert len(closure.observation_records) == 1

    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(closure, tool_attempts=())
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            gate_decisions=(
                _rebuild(
                    closure.gate_decisions[0],
                    context_manifest_id=uuid4(),
                ),
            ),
        )
    with pytest.raises(ValidationError):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(
                *closure.trace_events,
                _exact_evidence_trace(
                    event_type=TraceEventType.RUN_STARTED,
                    run_id=closure.run_record.run_id,
                    message_ref=uuid4(),
                ),
            ),
        )


def test_exact_run_evidence_does_not_treat_payload_correlations_as_records() -> None:
    closure = _minimal_exact_run_evidence()
    correlation_event = _exact_evidence_trace(
        event_type=TraceEventType.PRESENTATION_PLAN_PROPOSED,
        run_id=closure.run_record.run_id,
        model_call_id=uuid4(),
        presentation_plan_ref=uuid4(),
    )
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, correlation_event),
    )
    assert rebuilt.trace_events[-1].presentation_plan_ref is not None


@pytest.mark.parametrize("family_name", ("task", "tool_attempt"))
def test_exact_run_evidence_rejects_large_persisted_scalars_without_range_materialization(
    monkeypatch: pytest.MonkeyPatch,
    family_name: str,
) -> None:
    closure = (
        _request_understanding_exact_run_evidence(
            candidate_count=1,
            accepted_count=1,
        )
        if family_name == "task"
        else _tool_exact_run_evidence()
    )
    updates: dict[str, object]
    expected_message: str
    if family_name == "task":
        task = closure.task_records[0]
        unit = closure.request_unit_records[0]
        updates = {
            "task_records": (
                _rebuild(task, state_version=100_000),
            ),
            "request_unit_records": (
                _rebuild(unit, state_version=100_000),
            ),
            "run_task_links": (
                _rebuild(
                    closure.run_task_links[0],
                    result_task_state_version=100_000,
                ),
            ),
        }
        expected_message = "complete and contiguous"
    else:
        updates = {
            "tool_calls": (
                _rebuild(closure.tool_calls[0], attempt_count=100_000),
            ),
        }
        expected_message = "exact contiguous attempt"

    def fail_if_materialized(*_args: object) -> None:
        raise AssertionError(
            "persisted scalar must not drive range materialization"
        )

    monkeypatch.setattr(
        application_records_module,
        "range",
        fail_if_materialized,
        raising=False,
    )
    with pytest.raises(ValidationError, match=expected_message):
        _rebuild_exact_run_evidence(closure, **updates)


def test_exact_run_evidence_binds_accepted_versions_to_task_and_run_link() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    child = closure.accepted_task_deltas[0]

    with pytest.raises(ValidationError, match="current Task history"):
        _rebuild_exact_run_evidence(
            closure,
            accepted_task_deltas=(
                _rebuild(
                    child,
                    base_task_state_version=2,
                    result_task_state_version=3,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="RunTaskLink base"):
        _rebuild_exact_run_evidence(
            closure,
            accepted_task_deltas=(
                _rebuild(
                    child,
                    base_task_state_version=1,
                    result_task_state_version=2,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="terminal RunTaskLink"):
        _rebuild_exact_run_evidence(
            closure,
            run_task_links=(
                _rebuild(
                    closure.run_task_links[0],
                    result_task_state_version=None,
                ),
            ),
        )


@pytest.mark.parametrize("swapped_field", ("input_binding_refs", "goal_text"))
def test_exact_run_evidence_binds_each_accepted_child_to_its_request_unit(
    swapped_field: str,
) -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=2,
        accepted_count=2,
    )
    first, second = closure.request_unit_records
    if swapped_field == "input_binding_refs":
        first_updates = {"input_binding_refs": second.input_binding_refs}
        second_updates = {"input_binding_refs": first.input_binding_refs}
    else:
        first_updates = {"goal_text": second.goal_text}
        second_updates = {"goal_text": first.goal_text}

    with pytest.raises(ValidationError, match="RequestUnit causality"):
        _rebuild_exact_run_evidence(
            closure,
            request_unit_records=(
                _rebuild(first, **first_updates),
                _rebuild(second, **second_updates),
            ),
        )


@pytest.mark.parametrize(
    ("state_version", "assembled_at"),
    (
        (999, UTC_NOW),
        (2, UTC_NOW),
    ),
)
def test_exact_run_evidence_rejects_impossible_manifest_task_versions(
    state_version: int,
    assembled_at: datetime,
) -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    task = closure.task_records[0]
    manifest = closure.context_manifests[0]
    invalid_manifest = _rebuild(
        manifest,
        task_state_ref_and_version=TaskStateRefAndVersion(
            task_id=task.task_id,
            state_version=state_version,
        ),
        assembled_at=assembled_at,
    )
    with pytest.raises(ValidationError, match="Manifest Task version"):
        _rebuild_exact_run_evidence(
            closure,
            context_manifests=(invalid_manifest,),
        )


def test_exact_run_evidence_binds_manifest_observation_version_exactly() -> None:
    closure = _tool_exact_run_evidence()
    observation = closure.observation_records[0]
    manifest = closure.context_manifests[0]
    invalid_manifest = _rebuild(
        manifest,
        observation_refs_and_versions=(
            VersionedRecordRef(
                record_ref=observation.observation_id,
                version="WRONG",
            ),
        ),
    )
    with pytest.raises(ValidationError, match="Observation version"):
        _rebuild_exact_run_evidence(
            closure,
            context_manifests=(invalid_manifest,),
        )


def test_exact_run_evidence_requires_each_observation_source_edge() -> None:
    closure = _tool_exact_run_evidence()
    traces_without_source = tuple(
        event
        for event in closure.trace_events
        if event.event_type is not TraceEventType.OBSERVATION_RECORDED
    )
    with pytest.raises(ValidationError, match="Observation source edge"):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=traces_without_source,
        )


def test_exact_run_evidence_cross_checks_accepted_trace_task() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=2,
        accepted_count=2,
    )
    first_child, second_child = closure.accepted_task_deltas
    traces = tuple(
        (
            _rebuild(event, task_id=second_child.task_id)
            if event.accepted_delta_ref == first_child.accepted_delta_id
            else event
        )
        for event in closure.trace_events
    )
    with pytest.raises(ValidationError, match="accepted child"):
        _rebuild_exact_run_evidence(closure, trace_events=traces)


def test_exact_run_evidence_cross_checks_trace_manifest_correlations() -> None:
    closure = _minimal_exact_run_evidence()
    context_event = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.CONTEXT_MANIFEST_RECORDED
    )
    with pytest.raises(ValidationError, match="Trace Manifest correlations"):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=tuple(
                (
                    _rebuild(context_event, model_call_id=uuid4())
                    if event is context_event
                    else event
                )
                for event in closure.trace_events
            ),
        )

    second_spec = _rebuild(get_order_tool_spec(), name="get_order_alternate")
    second_artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=compute_model_visible_toolset_hash(
            (second_spec,)
        ),
        provider_visible_tool_specs=(second_spec,),
    )
    with pytest.raises(ValidationError, match="Trace Manifest correlations"):
        _rebuild_exact_run_evidence(
            closure,
            model_visible_toolset_artifacts=(
                *closure.model_visible_toolset_artifacts,
                second_artifact,
            ),
            trace_events=tuple(
                (
                    _rebuild(
                        context_event,
                        model_visible_toolset_hash=(
                            second_artifact.model_visible_toolset_hash
                        ),
                    )
                    if event is context_event
                    else event
                )
                for event in closure.trace_events
            ),
        )


def test_exact_run_evidence_uses_conversation_link_composite_identity() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    original = closure.conversation_task_links[0]
    historical = _rebuild(
        original,
        ended_at=original.linked_at + timedelta(microseconds=1),
    )
    active = _rebuild(
        original,
        linked_at=original.linked_at + timedelta(microseconds=2),
    )
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        conversation_task_links=(historical, active),
    )
    assert len(rebuilt.conversation_task_links) == 2

    with pytest.raises(ValidationError, match="identities must be unique"):
        _rebuild_exact_run_evidence(
            closure,
            conversation_task_links=(
                historical,
                _rebuild(historical, link_reason="REOPENED"),
            ),
        )


def test_exact_run_evidence_run_task_link_lifecycle_is_symmetric() -> None:
    terminal = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    assert (
        terminal.run_task_links[0].result_task_state_version
        == terminal.task_records[0].state_version
    )

    active_run = _project_run(
        terminal.run_record,
        status=AgentRunStatus.RUNNING,
        completed_at=None,
        stop_reason=None,
    )
    active_traces = tuple(
        event
        for event in terminal.trace_events
        if event.event_type is not TraceEventType.RUN_STOPPED
    )
    active_link = _rebuild(
        terminal.run_task_links[0],
        result_task_state_version=None,
    )
    active = _rebuild_exact_run_evidence(
        terminal,
        run_record=active_run,
        run_task_links=(active_link,),
        trace_events=active_traces,
    )
    assert active.run_task_links[0].result_task_state_version is None

    with pytest.raises(ValidationError, match="active RunTaskLink"):
        _rebuild_exact_run_evidence(
            terminal,
            run_record=active_run,
            trace_events=active_traces,
        )


def test_exact_run_evidence_current_unit_matches_latest_same_task_delta() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=2,
        accepted_count=2,
    )
    first_child, second_child = closure.accepted_task_deltas
    first_task, second_task = closure.task_records
    first_unit, second_unit = closure.request_unit_records
    latest_child = _rebuild(
        second_child,
        task_id=first_task.task_id,
        base_task_state_version=1,
        result_task_state_version=2,
    )
    current_unit = _rebuild(
        first_unit,
        goal_text=latest_child.goal_text,
        input_binding_refs=latest_child.input_binding_refs,
    )
    second_task_state_trace_removed = False
    traces: list[TraceEvent] = []
    for event in closure.trace_events:
        if (
            event.event_type is TraceEventType.TASK_STATE_CHANGED
            and event.task_id == first_task.task_id
            and not second_task_state_trace_removed
        ):
            second_task_state_trace_removed = True
            continue
        updates: dict[str, object] = {}
        if event.task_id == second_task.task_id:
            updates["task_id"] = first_task.task_id
        if event.request_unit_id == second_unit.request_unit_id:
            updates["request_unit_id"] = first_unit.request_unit_id
        traces.append(_rebuild(event, **updates) if updates else event)

    rebuilt = _rebuild_exact_run_evidence(
        closure,
        accepted_task_deltas=(first_child, latest_child),
        task_records=(first_task,),
        task_state_transitions=(closure.task_state_transitions[0],),
        request_unit_records=(current_unit,),
        conversation_task_links=(closure.conversation_task_links[0],),
        run_task_links=(closure.run_task_links[0],),
        trace_events=tuple(traces),
    )
    assert tuple(
        child.result_task_state_version
        for child in rebuilt.accepted_task_deltas
    ) == (1, 2)
    assert rebuilt.request_unit_records[0].goal_text == latest_child.goal_text
    assert (
        rebuilt.request_unit_records[0].input_binding_refs
        == latest_child.input_binding_refs
    )


_TOOL_LIFECYCLE_EVENT_TYPES = frozenset(
    {
        TraceEventType.TOOL_CALL_CREATED,
        TraceEventType.TOOL_CALL_STARTED,
        TraceEventType.TOOL_CALL_SUCCEEDED,
        TraceEventType.TOOL_CALL_FAILED,
        TraceEventType.TOOL_CALL_TIMED_OUT,
        TraceEventType.TOOL_CALL_INTERRUPTED,
    }
)


def _active_tool_exact_run_evidence(
    status: ToolCallStatus,
) -> ExactRunEvidenceClosure:
    closure = _tool_exact_run_evidence()
    call = closure.tool_calls[0]
    attempt = closure.tool_attempts[0]
    traces = tuple(
        event
        for event in closure.trace_events
        if event.event_type not in _TOOL_LIFECYCLE_EVENT_TYPES
        and event.event_type is not TraceEventType.OBSERVATION_RECORDED
    )
    if status is ToolCallStatus.CREATED:
        projected_call = _project_tool_call(
            call,
            attempt_count=0,
            status=status,
            finished_at=None,
            result_ref=None,
        )
        attempts: tuple[ToolAttemptRecord, ...] = ()
        lifecycle_event_type = TraceEventType.TOOL_CALL_CREATED
    else:
        projected_call = _project_tool_call(
            call,
            status=status,
            finished_at=None,
            result_ref=None,
        )
        attempts = (
            _rebuild(
                attempt,
                finished_at=None,
                outcome=None,
            ),
        )
        lifecycle_event_type = TraceEventType.TOOL_CALL_STARTED
    lifecycle_event = _exact_evidence_trace(
        event_type=lifecycle_event_type,
        run_id=closure.run_record.run_id,
        occurred_at=projected_call.started_at,
        task_id=projected_call.task_id,
        request_unit_id=projected_call.request_unit_id,
        tool_call_id=projected_call.tool_call_id,
        tool_call_terminal_status=status,
    )
    return _rebuild_exact_run_evidence(
        closure,
        request_unit_records=(
            _rebuild(closure.request_unit_records[0], observation_refs=()),
        ),
        tool_calls=(projected_call,),
        tool_attempts=attempts,
        observation_records=(),
        trace_events=(*traces, lifecycle_event),
    )


@pytest.mark.parametrize(
    "status",
    (AgentRunStatus.CREATED, AgentRunStatus.RUNNING),
)
def test_exact_run_evidence_accepts_active_run_without_stopped_trace(
    status: AgentRunStatus,
) -> None:
    terminal = _minimal_exact_run_evidence()
    active = _project_run(
        terminal.run_record,
        status=status,
        completed_at=None,
        stop_reason=None,
    )
    rebuilt = _rebuild_exact_run_evidence(
        terminal,
        run_record=active,
        trace_events=tuple(
            event
            for event in terminal.trace_events
            if event.event_type is not TraceEventType.RUN_STOPPED
        ),
    )
    assert rebuilt.run_record.status is status


def test_exact_run_evidence_rejects_stopped_trace_for_active_run() -> None:
    terminal = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    active = _project_run(
        terminal.run_record,
        status=AgentRunStatus.RUNNING,
        completed_at=None,
        stop_reason=None,
    )
    with pytest.raises(ValidationError, match="active Run cannot have RunStopped"):
        _rebuild_exact_run_evidence(
            terminal,
            run_record=active,
            run_task_links=(
                _rebuild(
                    terminal.run_task_links[0],
                    result_task_state_version=None,
                ),
            ),
        )


def test_exact_run_evidence_closes_terminal_run_stopped_projection() -> None:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    stopped = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    assert stopped.stop_reason is closure.run_record.stop_reason
    assert stopped.occurred_at == closure.run_record.completed_at

    wrong_reason = _rebuild(stopped, stop_reason=StopReason.INPUT_INVALID)
    late = _rebuild(
        stopped,
        occurred_at=closure.run_record.completed_at + timedelta(seconds=1),
    )
    duplicate = _rebuild(stopped, trace_event_id=uuid4())
    without_stopped = tuple(
        event
        for event in closure.trace_events
        if event.event_type is not TraceEventType.RUN_STOPPED
    )
    for traces in (
        tuple(
            wrong_reason if event is stopped else event
            for event in closure.trace_events
        ),
        tuple(
            late if event is stopped else event
            for event in closure.trace_events
        ),
        without_stopped,
        (*closure.trace_events, duplicate),
    ):
        with pytest.raises(ValidationError, match="terminal RunStopped"):
            _rebuild_exact_run_evidence(closure, trace_events=traces)


def test_exact_run_evidence_accepts_incomplete_run_with_stopped_trace() -> None:
    terminal = _minimal_exact_run_evidence()
    incomplete = _project_run(
        terminal.run_record,
        status=AgentRunStatus.INCOMPLETE,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )
    stopped = next(
        event
        for event in terminal.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    incomplete_stopped = _rebuild(
        stopped,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )
    rebuilt = _rebuild_exact_run_evidence(
        terminal,
        run_record=incomplete,
        trace_events=tuple(
            incomplete_stopped if event is stopped else event
            for event in terminal.trace_events
        ),
    )
    assert rebuilt.run_record.status is AgentRunStatus.INCOMPLETE
    assert incomplete_stopped.occurred_at == rebuilt.run_record.completed_at


def test_exact_run_evidence_accepts_failed_run_without_stopped_trace() -> None:
    terminal = _minimal_exact_run_evidence()
    failed = _project_run(
        terminal.run_record,
        status=AgentRunStatus.FAILED,
        stop_reason=None,
    )
    rebuilt = _rebuild_exact_run_evidence(
        terminal,
        run_record=failed,
        trace_events=tuple(
            event
            for event in terminal.trace_events
            if event.event_type is not TraceEventType.RUN_STOPPED
        ),
    )
    assert rebuilt.run_record.status is AgentRunStatus.FAILED
    assert rebuilt.run_record.stop_reason is None


def test_exact_run_evidence_rejects_failed_run_with_stopped_trace() -> None:
    terminal = _minimal_exact_run_evidence()
    failed = _project_run(
        terminal.run_record,
        status=AgentRunStatus.FAILED,
        stop_reason=None,
    )
    with pytest.raises(
        ValidationError,
        match="FAILED Run cannot have RunStopped",
    ):
        _rebuild_exact_run_evidence(terminal, run_record=failed)


def test_exact_run_evidence_rejects_failed_run_with_stop_reason() -> None:
    terminal = _minimal_exact_run_evidence()
    failed = _project_run(
        terminal.run_record,
        status=AgentRunStatus.FAILED,
        stop_reason=StopReason.INPUT_INVALID,
    )
    with pytest.raises(
        ValidationError,
        match="FAILED Run must not carry stop_reason",
    ):
        _rebuild_exact_run_evidence(
            terminal,
            run_record=failed,
            trace_events=tuple(
                event
                for event in terminal.trace_events
                if event.event_type is not TraceEventType.RUN_STOPPED
            ),
        )


@pytest.mark.parametrize(
    "status",
    (ToolCallStatus.CREATED, ToolCallStatus.RUNNING),
)
def test_exact_run_evidence_accepts_current_active_tool_lifecycle(
    status: ToolCallStatus,
) -> None:
    closure = _active_tool_exact_run_evidence(status)
    assert closure.tool_calls[0].status is status


def test_exact_run_evidence_accepts_sparse_and_order_independent_tool_lifecycle() -> None:
    closure = _tool_exact_run_evidence()
    call = closure.tool_calls[0]
    created = _exact_evidence_trace(
        event_type=TraceEventType.TOOL_CALL_CREATED,
        run_id=call.run_id,
        occurred_at=call.started_at,
        task_id=call.task_id,
        request_unit_id=call.request_unit_id,
        tool_call_id=call.tool_call_id,
        tool_call_terminal_status=ToolCallStatus.CREATED,
    )
    started = _exact_evidence_trace(
        event_type=TraceEventType.TOOL_CALL_STARTED,
        run_id=call.run_id,
        occurred_at=call.started_at + timedelta(microseconds=1),
        task_id=call.task_id,
        request_unit_id=call.request_unit_id,
        tool_call_id=call.tool_call_id,
        tool_call_terminal_status=ToolCallStatus.RUNNING,
    )
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, started, created),
    )
    assert rebuilt.tool_calls[0].status is ToolCallStatus.SUCCEEDED


def test_exact_run_evidence_rejects_tool_lifecycle_that_conflicts_with_projection() -> None:
    closure = _tool_exact_run_evidence()
    succeeded = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.TOOL_CALL_SUCCEEDED
    )
    failed = _rebuild(
        succeeded,
        event_type=TraceEventType.TOOL_CALL_FAILED,
        tool_call_terminal_status=ToolCallStatus.FAILED,
    )
    with pytest.raises(ValidationError, match="ToolCall lifecycle"):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=tuple(
                failed if event is succeeded else event
                for event in closure.trace_events
            ),
        )


def _completed_row_exact_run_evidence(
    *,
    stop_reason: StopReason,
    user_outcome: AgentOutcome,
    task_statuses: tuple[TaskStatus, ...],
) -> ExactRunEvidenceClosure:
    if len(task_statuses) > 2:
        raise ValueError("test fixture supports at most two Tasks")
    closure = (
        _request_understanding_exact_run_evidence(
            candidate_count=len(task_statuses),
            accepted_count=len(task_statuses),
        )
        if task_statuses
        else _minimal_exact_run_evidence()
    )
    completed_run = _project_run(
        closure.run_record,
        status=AgentRunStatus.COMPLETED,
        stop_reason=stop_reason,
    )
    stopped = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    completed_stopped = _rebuild(
        stopped,
        occurred_at=completed_run.completed_at,
        user_outcome=user_outcome,
        stop_reason=stop_reason,
    )
    return _rebuild_exact_run_evidence(
        closure,
        run_record=completed_run,
        task_records=tuple(
            _rebuild(task, status=status)
            for task, status in zip(closure.task_records, task_statuses)
        ),
        task_state_transitions=tuple(
            _rebuild(transition, to_status=status)
            for transition, status in zip(
                closure.task_state_transitions,
                task_statuses,
            )
        ),
        request_unit_records=tuple(
            _rebuild(unit, status=status)
            for unit, status in zip(
                closure.request_unit_records,
                task_statuses,
            )
        ),
        trace_events=tuple(
            completed_stopped if event is stopped else event
            for event in closure.trace_events
        ),
    )


_EXACT_EVIDENCE_COMPLETED_OWNER_ROWS = tuple(
    sorted(
        application_records_module._COMPLETED_FINALIZATION_ROWS,
        key=lambda row: (
            row[0].value,
            row[1],
            row[2].value,
            row[3].value if row[3] is not None else "",
        ),
    )
)


@pytest.mark.parametrize(
    "row",
    _EXACT_EVIDENCE_COMPLETED_OWNER_ROWS,
    ids=lambda row: "-".join(
        (
            row[0].value,
            "task" if row[1] else "no-task",
            row[2].value,
            row[3].value if row[3] is not None else "none",
        )
    ),
)
def test_exact_run_evidence_accepts_all_completed_owner_rows(
    row: tuple[
        StopReason,
        bool,
        AgentOutcome,
        TaskStatus | None,
    ],
) -> None:
    stop_reason, has_task, user_outcome, task_status = row
    assert len(_EXACT_EVIDENCE_COMPLETED_OWNER_ROWS) == 9
    closure = _completed_row_exact_run_evidence(
        stop_reason=stop_reason,
        user_outcome=user_outcome,
        task_statuses=(
            (task_status,)
            if has_task and task_status is not None
            else ()
        ),
    )
    assert closure.run_record.stop_reason is stop_reason


def test_exact_run_evidence_accepts_same_status_multi_task_completed_row() -> None:
    closure = _completed_row_exact_run_evidence(
        stop_reason=StopReason.GOAL_COMPLETED,
        user_outcome=AgentOutcome.COMPLETED,
        task_statuses=(TaskStatus.COMPLETED, TaskStatus.COMPLETED),
    )
    assert tuple(task.status for task in closure.task_records) == (
        TaskStatus.COMPLETED,
        TaskStatus.COMPLETED,
    )


@pytest.mark.parametrize(
    ("stop_reason", "user_outcome", "task_statuses"),
    (
        pytest.param(
            StopReason.GOAL_COMPLETED,
            AgentOutcome.COMPLETED,
            (),
            id="goal-without-task",
        ),
        pytest.param(
            StopReason.INPUT_INVALID,
            AgentOutcome.BLOCKED,
            (TaskStatus.BLOCKED,),
            id="input-invalid-with-task",
        ),
        pytest.param(
            StopReason.PROCESS_RESTART_DETECTED,
            AgentOutcome.BLOCKED,
            (),
            id="process-restart-completed",
        ),
        pytest.param(
            StopReason.INPUT_INVALID,
            AgentOutcome.ASK_USER,
            (),
            id="ask-user-outcome",
        ),
        pytest.param(
            StopReason.INPUT_INVALID,
            AgentOutcome.NEED_HUMAN,
            (),
            id="need-human-outcome",
        ),
        pytest.param(
            StopReason.GOAL_COMPLETED,
            AgentOutcome.COMPLETED,
            (TaskStatus.COMPLETED, TaskStatus.BLOCKED),
            id="heterogeneous-tasks",
        ),
        pytest.param(
            StopReason.GOAL_COMPLETED,
            AgentOutcome.COMPLETED,
            (TaskStatus.WAITING_USER,),
            id="unknown-uniform-task-status",
        ),
    ),
)
def test_exact_run_evidence_rejects_unknown_completed_rows(
    stop_reason: StopReason,
    user_outcome: AgentOutcome,
    task_statuses: tuple[TaskStatus, ...],
) -> None:
    with pytest.raises(
        ValidationError,
        match="closed completed Run matrix",
    ):
        _completed_row_exact_run_evidence(
            stop_reason=stop_reason,
            user_outcome=user_outcome,
            task_statuses=task_statuses,
        )


def test_exact_run_evidence_rejects_non_blocked_incomplete_outcome() -> None:
    terminal = _minimal_exact_run_evidence()
    incomplete = _project_run(
        terminal.run_record,
        status=AgentRunStatus.INCOMPLETE,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )
    stopped = next(
        event
        for event in terminal.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    invalid_stopped = _rebuild(
        stopped,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
        user_outcome=AgentOutcome.ASK_USER,
    )
    with pytest.raises(
        ValidationError,
        match="INCOMPLETE RunStopped",
    ):
        _rebuild_exact_run_evidence(
            terminal,
            run_record=incomplete,
            trace_events=tuple(
                invalid_stopped if event is stopped else event
                for event in terminal.trace_events
            ),
        )


@pytest.mark.parametrize(
    "extra_field",
    ("message_ref", "context_manifest_id"),
)
def test_exact_run_evidence_rejects_run_stopped_payload_pollution(
    extra_field: str,
) -> None:
    closure = _minimal_exact_run_evidence()
    stopped = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    extra_value = (
        closure.message_records[0].message_id
        if extra_field == "message_ref"
        else closure.context_manifests[0].context_manifest_id
    )
    polluted = _rebuild(stopped, **{extra_field: extra_value})
    with pytest.raises(
        ValidationError,
        match="RunStopped Trace only allows its exact per-kind projection",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=tuple(
                polluted if event is stopped else event
                for event in closure.trace_events
            ),
        )


def _terminal_tool_exact_run_evidence(
    *,
    status: ToolCallStatus,
    outcome: ToolResultOutcome,
    interrupted_attempt: str = "finalized",
) -> ExactRunEvidenceClosure:
    closure = _tool_exact_run_evidence()
    if status is ToolCallStatus.SUCCEEDED:
        return closure

    call = closure.tool_calls[0]
    attempt = closure.tool_attempts[0]
    if status is ToolCallStatus.FAILED:
        terminal_call = _project_tool_call(
            call,
            status=status,
            failure_code="ORDER_LOOKUP_FAILED",
            result_ref=None,
        )
        attempts = (
            _rebuild(
                attempt,
                outcome=outcome,
                failure_code="ORDER_LOOKUP_FAILED",
            ),
        )
        lifecycle_event_type = TraceEventType.TOOL_CALL_FAILED
    elif status is ToolCallStatus.TIMED_OUT:
        terminal_call = _project_tool_call(
            call,
            status=status,
            failure_code="TOOL_TIMEOUT",
            timeout_phase=ToolTimeoutPhase.AFTER_DISPATCH,
            result_ref=None,
        )
        attempts = (
            _rebuild(
                attempt,
                outcome=outcome,
                failure_code="TOOL_TIMEOUT",
            ),
        )
        lifecycle_event_type = TraceEventType.TOOL_CALL_TIMED_OUT
    elif status is ToolCallStatus.INTERRUPTED:
        terminal_call = _project_tool_call(
            call,
            status=status,
            attempt_count=(0 if interrupted_attempt == "absent" else 1),
            interruption_reason="PROCESS_RESTART_DETECTED",
            result_ref=None,
        )
        if interrupted_attempt == "absent":
            attempts = ()
        elif interrupted_attempt == "unfinished":
            attempts = (
                _rebuild(
                    attempt,
                    finished_at=None,
                    outcome=None,
                ),
            )
        else:
            attempts = (_rebuild(attempt, outcome=outcome),)
        lifecycle_event_type = TraceEventType.TOOL_CALL_INTERRUPTED
    else:
        raise ValueError("test fixture requires a terminal ToolCall status")

    lifecycle_event = _exact_evidence_trace(
        event_type=lifecycle_event_type,
        run_id=terminal_call.run_id,
        occurred_at=terminal_call.finished_at,
        task_id=terminal_call.task_id,
        request_unit_id=terminal_call.request_unit_id,
        context_manifest_id=terminal_call.context_manifest_id,
        argument_binding_refs=terminal_call.argument_binding_refs,
        tool_call_id=terminal_call.tool_call_id,
        tool_call_terminal_status=status,
    )
    run_stopped = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.RUN_STOPPED
    )
    retained_traces = tuple(
        event
        for event in closure.trace_events
        if event.event_type not in _TOOL_LIFECYCLE_EVENT_TYPES
        and event.event_type is not TraceEventType.OBSERVATION_RECORDED
        and event is not run_stopped
    )
    return _rebuild_exact_run_evidence(
        closure,
        request_unit_records=(
            _rebuild(closure.request_unit_records[0], observation_refs=()),
        ),
        tool_calls=(terminal_call,),
        tool_attempts=attempts,
        observation_records=(),
        trace_events=(
            *retained_traces,
            lifecycle_event,
            run_stopped,
        ),
    )


def _normalized_tool_result_trace(
    closure: ExactRunEvidenceClosure,
    *,
    outcome: ToolResultOutcome,
) -> TraceEvent:
    call = closure.tool_calls[0]
    return _exact_evidence_trace(
        event_type=TraceEventType.TOOL_RESULT_NORMALIZED,
        run_id=call.run_id,
        occurred_at=call.finished_at or call.started_at,
        task_id=call.task_id,
        request_unit_id=call.request_unit_id,
        tool_call_id=call.tool_call_id,
        safe_tool_outcome=outcome,
    )


@pytest.mark.parametrize(
    ("status", "outcome", "interrupted_attempt"),
    (
        (
            ToolCallStatus.SUCCEEDED,
            ToolResultOutcome.SUCCESS,
            "finalized",
        ),
        (
            ToolCallStatus.FAILED,
            ToolResultOutcome.BUSINESS_FAILURE,
            "finalized",
        ),
        (
            ToolCallStatus.FAILED,
            ToolResultOutcome.SYSTEM_FAILURE,
            "finalized",
        ),
        (
            ToolCallStatus.TIMED_OUT,
            ToolResultOutcome.TIMEOUT,
            "finalized",
        ),
        (
            ToolCallStatus.INTERRUPTED,
            ToolResultOutcome.INTERRUPTED,
            "absent",
        ),
        (
            ToolCallStatus.INTERRUPTED,
            ToolResultOutcome.INTERRUPTED,
            "unfinished",
        ),
        (
            ToolCallStatus.INTERRUPTED,
            ToolResultOutcome.INTERRUPTED,
            "finalized",
        ),
    ),
)
def test_exact_run_evidence_accepts_normalized_terminal_tool_outcomes(
    status: ToolCallStatus,
    outcome: ToolResultOutcome,
    interrupted_attempt: str,
) -> None:
    closure = _terminal_tool_exact_run_evidence(
        status=status,
        outcome=outcome,
        interrupted_attempt=interrupted_attempt,
    )
    normalized = _normalized_tool_result_trace(
        closure,
        outcome=outcome,
    )
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, normalized),
    )
    assert normalized.safe_tool_outcome is outcome
    assert rebuilt.tool_calls[0].status is status


def test_exact_run_evidence_rejects_safe_outcome_on_non_normalized_event() -> None:
    closure = _tool_exact_run_evidence()
    succeeded = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.TOOL_CALL_SUCCEEDED
    )
    polluted = _rebuild(
        succeeded,
        safe_tool_outcome=ToolResultOutcome.SUCCESS,
    )
    with pytest.raises(
        ValidationError,
        match="safe_tool_outcome requires ToolResultNormalized",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=tuple(
                polluted if event is succeeded else event
                for event in closure.trace_events
            ),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-safe-outcome",
        "missing-tool-call",
        "wrong-timestamp",
        "wrong-status-outcome",
    ),
)
def test_exact_run_evidence_rejects_malformed_normalized_tool_result(
    mutation: str,
) -> None:
    closure = _tool_exact_run_evidence()
    call = closure.tool_calls[0]
    normalized = _normalized_tool_result_trace(
        closure,
        outcome=ToolResultOutcome.SUCCESS,
    )
    if mutation == "missing-safe-outcome":
        invalid = _rebuild(normalized, safe_tool_outcome=None)
    elif mutation == "missing-tool-call":
        invalid = _rebuild(normalized, tool_call_id=None)
    elif mutation == "wrong-timestamp":
        invalid = _rebuild(
            normalized,
            occurred_at=call.finished_at + timedelta(microseconds=1),
        )
    else:
        invalid = _rebuild(
            normalized,
            safe_tool_outcome=ToolResultOutcome.SYSTEM_FAILURE,
        )
    with pytest.raises(ValidationError, match="ToolResultNormalized"):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, invalid),
        )


def test_exact_run_evidence_rejects_duplicate_normalized_tool_result() -> None:
    closure = _tool_exact_run_evidence()
    first = _normalized_tool_result_trace(
        closure,
        outcome=ToolResultOutcome.SUCCESS,
    )
    second = _normalized_tool_result_trace(
        closure,
        outcome=ToolResultOutcome.SUCCESS,
    )
    with pytest.raises(
        ValidationError,
        match="ToolResultNormalized must be unique per ToolCall",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, first, second),
        )


@pytest.mark.parametrize(
    "status",
    (ToolCallStatus.CREATED, ToolCallStatus.RUNNING),
)
def test_exact_run_evidence_rejects_normalized_active_tool_call(
    status: ToolCallStatus,
) -> None:
    closure = _active_tool_exact_run_evidence(status)
    normalized = _normalized_tool_result_trace(
        closure,
        outcome=ToolResultOutcome.SUCCESS,
    )
    with pytest.raises(
        ValidationError,
        match="ToolResultNormalized requires a terminal ToolCall",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, normalized),
        )


def test_exact_run_evidence_rejects_normalized_final_attempt_mismatch() -> None:
    closure = _terminal_tool_exact_run_evidence(
        status=ToolCallStatus.FAILED,
        outcome=ToolResultOutcome.BUSINESS_FAILURE,
    )
    normalized = _normalized_tool_result_trace(
        closure,
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
    )
    with pytest.raises(
        ValidationError,
        match="ToolResultNormalized must match the final ToolAttempt",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, normalized),
        )


def _gate_decision_trace(
    closure: ExactRunEvidenceClosure,
    gate: GateDecision,
    **updates: object,
) -> TraceEvent:
    values: dict[str, object] = {
        "event_type": TraceEventType.GATE_DECISION_RECORDED,
        "run_id": closure.run_record.run_id,
        "occurred_at": gate.decided_at,
        "task_id": closure.task_records[0].task_id,
        "request_unit_id": closure.request_unit_records[0].request_unit_id,
        "model_call_id": gate.model_call_id,
        "context_manifest_id": gate.context_manifest_id,
        "requested_tool_name": gate.requested_provider_tool_name,
        "validated_task_state_version": gate.validated_task_state_version,
        "argument_binding_refs": gate.argument_binding_refs,
        "gate_decision": gate.decision,
        "gate_reason_code": gate.reason_code,
    }
    values.update(updates)
    return _exact_evidence_trace(**values)


def _rejected_gate_exact_run_evidence() -> ExactRunEvidenceClosure:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    manifest = closure.context_manifests[0]
    gate = GateDecision(
        gate_decision_id=uuid4(),
        model_call_id=manifest.model_call_id,
        context_manifest_id=manifest.context_manifest_id,
        requested_provider_tool_name="get_order",
        resolved_canonical_tool_name=None,
        snapshot_match=True,
        registration_valid=False,
        schema_valid=True,
        trusted_field_valid=True,
        argument_binding_valid=True,
        argument_binding_refs=(
            closure.input_binding_records[0].binding_id,
        ),
        budget_valid=True,
        progress_valid=True,
        proposed_base_task_state_version=None,
        validated_task_state_version=1,
        state_version_valid=True,
        action_boundary_valid=True,
        decision=GateDecisionValue.REJECT,
        reason_code=GateReasonCode.TOOL_NOT_REGISTERED,
        decided_at=UTC_NOW + timedelta(microseconds=100),
    )
    return _rebuild_exact_run_evidence(
        closure,
        gate_decisions=(gate,),
    )


@pytest.mark.parametrize(
    "closure_factory",
    (_tool_exact_run_evidence, _rejected_gate_exact_run_evidence),
)
def test_exact_run_evidence_accepts_owner_backed_gate_trace(
    closure_factory: Callable[[], ExactRunEvidenceClosure],
) -> None:
    closure = closure_factory()
    gate = closure.gate_decisions[0]
    gate_event = _gate_decision_trace(closure, gate)
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, gate_event),
    )
    assert gate_event.gate_decision is gate.decision
    assert len(rebuilt.gate_decisions) == 1


def test_exact_run_evidence_accepts_sparse_gate_trace() -> None:
    for closure in (
        _tool_exact_run_evidence(),
        _rejected_gate_exact_run_evidence(),
    ):
        rebuilt = _rebuild_exact_run_evidence(closure)
        assert not any(
            event.event_type is TraceEventType.GATE_DECISION_RECORDED
            for event in rebuilt.trace_events
        )


def test_exact_run_evidence_rejects_gate_trace_decision_forgery() -> None:
    closure = _tool_exact_run_evidence()
    gate_event = _gate_decision_trace(
        closure,
        closure.gate_decisions[0],
        gate_decision=GateDecisionValue.REJECT,
        gate_reason_code=GateReasonCode.TOOL_NOT_REGISTERED,
    )
    with pytest.raises(
        ValidationError,
        match="GateDecisionRecorded must match an owner GateDecision",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, gate_event),
        )


def test_exact_run_evidence_rejects_gate_trace_projection_forgery() -> None:
    closure = _tool_exact_run_evidence()
    gate_event = _gate_decision_trace(
        closure,
        closure.gate_decisions[0],
        requested_tool_name="forged_tool",
    )
    with pytest.raises(
        ValidationError,
        match="GateDecisionRecorded must match an owner GateDecision",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, gate_event),
        )


def test_exact_run_evidence_rejects_excess_gate_trace_projection() -> None:
    closure = _tool_exact_run_evidence()
    gate = closure.gate_decisions[0]
    first = _gate_decision_trace(closure, gate)
    second = _gate_decision_trace(closure, gate)
    with pytest.raises(
        ValidationError,
        match="GateDecisionRecorded must match an owner GateDecision",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, first, second),
        )


def test_exact_run_evidence_rejects_gate_fields_on_other_event_kinds() -> None:
    closure = _minimal_exact_run_evidence()
    accepted = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.MESSAGE_ACCEPTED
    )
    polluted = _rebuild(
        accepted,
        gate_decision=GateDecisionValue.REJECT,
        gate_reason_code=GateReasonCode.TOOL_NOT_REGISTERED,
    )
    with pytest.raises(
        ValidationError,
        match="Gate fields require GateDecisionRecorded",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=tuple(
                polluted if event is accepted else event
                for event in closure.trace_events
            ),
        )


def test_exact_run_evidence_rejects_terminal_fields_on_other_event_kinds() -> None:
    closure = _minimal_exact_run_evidence()
    accepted = next(
        event
        for event in closure.trace_events
        if event.event_type is TraceEventType.MESSAGE_ACCEPTED
    )
    polluted = _rebuild(
        accepted,
        user_outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReason.INPUT_INVALID,
    )
    with pytest.raises(
        ValidationError,
        match="terminal fields require RunStopped",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=tuple(
                polluted if event is accepted else event
                for event in closure.trace_events
            ),
        )


def test_exact_run_evidence_preserves_other_payload_correlations() -> None:
    closure = _minimal_exact_run_evidence()
    correlation_event = _exact_evidence_trace(
        event_type=TraceEventType.PRESENTATION_PLAN_PROPOSED,
        run_id=closure.run_record.run_id,
        model_call_id=closure.context_manifests[0].model_call_id,
        presentation_plan_ref=uuid4(),
    )
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, correlation_event),
    )
    assert correlation_event in rebuilt.trace_events


def _two_task_gate_exact_run_evidence(
    *,
    argument_binding_valid: bool,
    manifest_task_ref: bool = False,
) -> ExactRunEvidenceClosure:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=2,
        accepted_count=2,
    )
    manifest = closure.context_manifests[0]
    if manifest_task_ref:
        manifest = _rebuild(
            manifest,
            task_state_ref_and_version=TaskStateRefAndVersion(
                task_id=closure.task_records[0].task_id,
                state_version=1,
            ),
        )
        closure = _rebuild_exact_run_evidence(
            closure,
            context_manifests=(manifest,),
        )
    gate = GateDecision(
        gate_decision_id=uuid4(),
        model_call_id=manifest.model_call_id,
        context_manifest_id=manifest.context_manifest_id,
        requested_provider_tool_name="get_order",
        resolved_canonical_tool_name=(
            "get_order" if argument_binding_valid else None
        ),
        snapshot_match=True,
        registration_valid=True,
        schema_valid=True,
        trusted_field_valid=True,
        argument_binding_valid=argument_binding_valid,
        argument_binding_refs=(
            closure.input_binding_records[0].binding_id,
        ),
        budget_valid=True,
        progress_valid=True,
        proposed_base_task_state_version=None,
        validated_task_state_version=(2 if manifest_task_ref else 1),
        state_version_valid=True,
        action_boundary_valid=True,
        decision=(
            GateDecisionValue.ACCEPT
            if argument_binding_valid
            else GateDecisionValue.REJECT
        ),
        reason_code=(
            None
            if argument_binding_valid
            else GateReasonCode.ARGUMENT_BINDING_MISMATCH
        ),
        decided_at=UTC_NOW + timedelta(microseconds=100),
    )
    return _rebuild_exact_run_evidence(
        closure,
        gate_decisions=(gate,),
    )


@pytest.mark.parametrize(
    "missing_field",
    ("task_id", "request_unit_id"),
)
def test_exact_run_evidence_rejects_gate_trace_without_root_pair(
    missing_field: str,
) -> None:
    closure = _tool_exact_run_evidence()
    gate_event = _gate_decision_trace(
        closure,
        closure.gate_decisions[0],
        **{missing_field: None},
    )
    with pytest.raises(
        ValidationError,
        match="GateDecisionRecorded requires a root Task/RequestUnit pair",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, gate_event),
        )


def test_exact_run_evidence_rejects_binding_valid_gate_on_other_task() -> None:
    closure = _two_task_gate_exact_run_evidence(
        argument_binding_valid=True,
    )
    gate_event = _gate_decision_trace(
        closure,
        closure.gate_decisions[0],
        task_id=closure.task_records[1].task_id,
        request_unit_id=closure.request_unit_records[1].request_unit_id,
    )
    with pytest.raises(
        ValidationError,
        match="GateDecisionRecorded bindings must belong to its RequestUnit",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, gate_event),
        )


def test_exact_run_evidence_allows_binding_mismatch_gate_on_other_task() -> None:
    closure = _two_task_gate_exact_run_evidence(
        argument_binding_valid=False,
    )
    gate_event = _gate_decision_trace(
        closure,
        closure.gate_decisions[0],
        task_id=closure.task_records[1].task_id,
        request_unit_id=closure.request_unit_records[1].request_unit_id,
    )
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, gate_event),
    )
    assert gate_event.gate_reason_code is GateReasonCode.ARGUMENT_BINDING_MISMATCH
    assert len(rebuilt.task_records) == 2


def test_exact_run_evidence_closes_gate_trace_to_manifest_task_only() -> None:
    closure = _two_task_gate_exact_run_evidence(
        argument_binding_valid=False,
        manifest_task_ref=True,
    )
    gate = closure.gate_decisions[0]
    manifest = closure.context_manifests[0]
    matching_event = _gate_decision_trace(closure, gate)
    rebuilt = _rebuild_exact_run_evidence(
        closure,
        trace_events=(*closure.trace_events, matching_event),
    )
    assert manifest.task_state_ref_and_version.state_version == 1
    assert matching_event.validated_task_state_version == 2
    assert len(rebuilt.gate_decisions) == 1

    mismatching_event = _rebuild(
        matching_event,
        trace_event_id=uuid4(),
        task_id=closure.task_records[1].task_id,
        request_unit_id=closure.request_unit_records[1].request_unit_id,
    )
    with pytest.raises(
        ValidationError,
        match="GateDecisionRecorded Task must match ContextManifest",
    ):
        _rebuild_exact_run_evidence(
            closure,
            trace_events=(*closure.trace_events, mismatching_event),
        )


C2_SEARCH_SNAPSHOT_VERSION = (
    "mock-order-search-snapshot-source-version.p0.v1:sha256:" + "a" * 64
)
C2_CANDIDATE_VERSION_1 = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "1" * 64
)
C2_CANDIDATE_VERSION_2 = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "2" * 64
)
C2_SHIPMENT_VERSION = "mock-shipment-source-version.p0.v1:sha256:" + "b" * 64


def _c2_project(model: BaseModel, **updates: object) -> BaseModel:
    values = model.model_dump(mode="python")
    values.update(updates)
    return type(model).model_validate(values, strict=True)


def _c2_attempt(
    *,
    tool_call_id: UUID,
    attempt_no: int = 1,
    finished_at: datetime | None = None,
    outcome: ToolResultOutcome | None = None,
    failure_code: str | None = None,
    retry_decision: ToolRetryDecision | None = None,
) -> ToolAttemptRecordV2:
    return ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=attempt_no,
        started_at=UTC_NOW + timedelta(seconds=attempt_no - 1),
        finished_at=finished_at,
        outcome=outcome,
        failure_code=failure_code,
        retry_decision=retry_decision,
    )


def _c2_tool_call(
    *,
    name: Cycle2ToolName,
    owner: str = "customer-A",
    task_id: UUID | None = None,
    request_unit_id: UUID | None = None,
    validated_task_state_version: int = 3,
    argument_binding_refs: tuple[UUID, ...] | None = None,
    verified_target_ref: UUID | None = None,
    status: ToolCallStatus = ToolCallStatus.CREATED,
    attempts: tuple[ToolAttemptRecordV2, ...] = (),
    finished_at: datetime | None = None,
    result_ref: UUID | None = None,
    run_id: UUID | None = None,
    model_call_id: UUID | None = None,
    context_manifest_id: UUID | None = None,
    gate_decision_id: UUID | None = None,
    provider_tool_call_id: str | None = None,
    started_at: datetime = UTC_NOW,
) -> ToolCallRecordV2:
    tool_call_id = attempts[0].tool_call_id if attempts else uuid4()
    return ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=run_id or uuid4(),
        task_id=task_id or uuid4(),
        request_unit_id=request_unit_id or uuid4(),
        model_call_id=model_call_id or uuid4(),
        context_manifest_id=context_manifest_id or uuid4(),
        gate_decision_id=gate_decision_id or uuid4(),
        provider_tool_call_id=provider_tool_call_id,
        canonical_tool_name=name,
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref=owner,
        validated_task_state_version=validated_task_state_version,
        argument_binding_refs=argument_binding_refs or (uuid4(),),
        verified_target_ref=verified_target_ref,
        effect=ToolEffect.READ,
        attempt_count=len(attempts),
        attempts=attempts,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        result_ref=result_ref,
    )


def _c2_exact_run_evidence_with_recovered_attempt(
) -> tuple[
    Cycle2ExactRunEvidenceClosure,
    ToolRetryRecoveryDecisionRecordV2,
]:
    baseline = _cycle2_exact_run_evidence_with_task()
    task = baseline.task_records[0]
    unit = baseline.request_unit_records[0]
    binding = baseline.input_binding_records[0]
    run = _c2_project(
        baseline.run_record,
        status=AgentRunStatusV2.RUNNING,
        completed_at=None,
        stop_reason=None,
    )
    tool_call_id = uuid4()
    first = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=UTC_NOW + timedelta(milliseconds=500),
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="SHIPMENT_SERVICE_TRANSIENT",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    decided_at = UTC_NOW + timedelta(seconds=1)
    second = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=2,
        started_at=UTC_NOW + timedelta(seconds=2),
    )
    tool_call = _c2_tool_call(
        name=Cycle2ToolName.GET_SHIPMENT,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        validated_task_state_version=task.state_version,
        argument_binding_refs=(binding.binding_id,),
        status=ToolCallStatus.RUNNING,
        attempts=(first, second),
        run_id=run.run_id,
    )
    decision = ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=uuid4(),
        tool_call_id=tool_call.tool_call_id,
        last_attempt_no=1,
        decision=ToolRecoveryDecision.APPEND_SECOND_ATTEMPT,
        stable_reason_code="RETRY_REVALIDATED_CAS_REQUIRED",
        candidate_next_attempt_no=2,
        decided_at=decided_at,
    )
    snapshot = build_cycle2_registry_snapshot()
    artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        provider_visible_tool_specs=snapshot.provider_visible_toolset,
    )
    manifest = ContextManifest(
        context_manifest_id=tool_call.context_manifest_id,
        run_id=run.run_id,
        model_call_id=tool_call.model_call_id,
        tool_registry_version=tool_call.tool_registry_version,
        model_visible_toolset_hash=artifact.model_visible_toolset_hash,
        selected_message_refs=(baseline.message_records[0].message_id,),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=UTC_NOW,
    )
    return (
        Cycle2ExactRunEvidenceClosure(
            **{
                **{
                    field_name: getattr(baseline, field_name)
                    for field_name in Cycle2ExactRunEvidenceClosure.model_fields
                },
                "run_record": run,
                "tool_call_records": (tool_call,),
                "recovery_decision_records": (decision,),
                "context_manifest_records": (manifest,),
                "model_visible_toolset_artifacts": (artifact,),
            }
        ),
        decision,
    )


def test_cycle2_exact_run_evidence_closes_successful_recovery_append_without_parent_ref() -> None:
    closure, decision = _c2_exact_run_evidence_with_recovered_attempt()
    running = closure.tool_call_records[0]

    assert running.recovery_decision_ref is None
    assert running.attempt_count == 2
    assert closure.recovery_decision_records == (decision,)

    completed_second = _c2_project(
        running.attempts[1],
        finished_at=UTC_NOW + timedelta(seconds=3),
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    terminal = _c2_project(
        running,
        attempts=(running.attempts[0], completed_second),
        status=ToolCallStatus.SUCCEEDED,
        finished_at=completed_second.finished_at,
        result_ref=uuid4(),
    )
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    terminal_closure = Cycle2ExactRunEvidenceClosure(
        **{**values, "tool_call_records": (terminal,)}
    )
    assert terminal_closure.tool_call_records[0].recovery_decision_ref is None


def _c2_exact_run_evidence_with_terminal_recovery() -> tuple[
    Cycle2ExactRunEvidenceClosure,
    ToolRetryRecoveryDecisionRecordV2,
]:
    baseline = _cycle2_exact_run_evidence_with_task()
    task = baseline.task_records[0]
    unit = baseline.request_unit_records[0]
    binding = baseline.input_binding_records[0]
    run = baseline.run_record
    tool_call_id = uuid4()
    first = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=UTC_NOW + timedelta(milliseconds=500),
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="SHIPMENT_SERVICE_TRANSIENT",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    decided_at = UTC_NOW + timedelta(seconds=1)
    decision = ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=uuid4(),
        tool_call_id=tool_call_id,
        last_attempt_no=1,
        decision=ToolRecoveryDecision.TERMINATE_RETRY_PATH,
        stable_reason_code="STATE_OR_BINDING_INVALIDATED",
        decided_at=decided_at,
    )
    running = _c2_tool_call(
        name=Cycle2ToolName.GET_SHIPMENT,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        validated_task_state_version=task.state_version,
        argument_binding_refs=(binding.binding_id,),
        status=ToolCallStatus.RUNNING,
        attempts=(first,),
        run_id=run.run_id,
    )
    terminal = _c2_project(
        running,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=decided_at,
        interruption_reason="STATE_OR_BINDING_INVALIDATED",
        recovery_disposition=(
            ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
        ),
        recovery_decision_ref=decision.recovery_decision_id,
    )
    snapshot = build_cycle2_registry_snapshot()
    artifact = ModelVisibleToolsetArtifact(
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        provider_visible_tool_specs=snapshot.provider_visible_toolset,
    )
    manifest = ContextManifest(
        context_manifest_id=terminal.context_manifest_id,
        run_id=run.run_id,
        model_call_id=terminal.model_call_id,
        tool_registry_version=terminal.tool_registry_version,
        model_visible_toolset_hash=artifact.model_visible_toolset_hash,
        selected_message_refs=(baseline.message_records[0].message_id,),
        redaction_policy_version="redaction-v1",
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=UTC_NOW,
    )
    closure = Cycle2ExactRunEvidenceClosure(
        **{
            **{
                field_name: getattr(baseline, field_name)
                for field_name in Cycle2ExactRunEvidenceClosure.model_fields
            },
            "run_record": run,
            "tool_call_records": (terminal,),
            "recovery_decision_records": (decision,),
            "context_manifest_records": (manifest,),
            "model_visible_toolset_artifacts": (artifact,),
        }
    )

    return closure, decision


def test_cycle2_exact_run_evidence_closes_terminal_recovery_with_parent_ref() -> None:
    closure, decision = _c2_exact_run_evidence_with_terminal_recovery()
    terminal = closure.tool_call_records[0]

    assert closure.recovery_decision_records == (decision,)
    assert terminal.recovery_decision_ref == decision.recovery_decision_id


def test_cycle2_exact_run_evidence_rejects_mismatched_terminal_recovery_child() -> None:
    closure, decision = _c2_exact_run_evidence_with_terminal_recovery()
    terminal = closure.tool_call_records[0]
    assert terminal.finished_at is not None
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }
    wrong_kind = _c2_project(
        decision,
        decision=ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT,
        stable_reason_code="UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
    )
    wrong_reason = _c2_project(
        decision,
        stable_reason_code="RUN_BUDGET_EXHAUSTED",
    )
    wrong_attempt = _c2_project(
        decision,
        decision=ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT,
        stable_reason_code="UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
        last_attempt_no=2,
    )
    late_decision = _c2_project(
        decision,
        decided_at=terminal.finished_at + timedelta(microseconds=1),
    )

    for mismatched in (
        wrong_kind,
        wrong_reason,
        wrong_attempt,
        late_decision,
    ):
        with pytest.raises(ValidationError, match="recovery root mismatch"):
            Cycle2ExactRunEvidenceClosure(
                **{
                    **values,
                    "recovery_decision_records": (mismatched,),
                }
            )


@pytest.mark.parametrize("terminal_kind", ("unfinished", "budget_exhausted"))
def test_cycle2_exact_run_evidence_closes_other_terminal_recovery_shapes(
    terminal_kind: str,
) -> None:
    closure, state_decision = _c2_exact_run_evidence_with_terminal_recovery()
    state_terminal = closure.tool_call_records[0]
    first = state_terminal.attempts[0]
    if terminal_kind == "unfinished":
        attempt = _c2_project(
            first,
            finished_at=None,
            outcome=None,
            failure_code=None,
            retry_decision=None,
        )
        decision = _c2_project(
            state_decision,
            decision=ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT,
            stable_reason_code="UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
        )
        terminal = _c2_project(
            state_terminal,
            attempts=(attempt,),
            interruption_reason="PROCESS_RESTART_DETECTED",
            failure_code=None,
            recovery_disposition=(
                ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
            ),
        )
    else:
        decision = _c2_project(
            state_decision,
            stable_reason_code="RUN_BUDGET_EXHAUSTED",
        )
        terminal = _c2_project(
            state_terminal,
            status=ToolCallStatus.FAILED,
            failure_code=first.failure_code,
            interruption_reason=None,
            recovery_disposition=(
                ToolRecoveryDisposition.RETRY_SCHEDULED_RUN_BUDGET_EXHAUSTED
            ),
        )
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    rebuilt = Cycle2ExactRunEvidenceClosure(
        **{
            **values,
            "tool_call_records": (terminal,),
            "recovery_decision_records": (decision,),
        }
    )

    assert rebuilt.recovery_decision_records == (decision,)


def test_cycle2_exact_run_evidence_rejects_cross_tool_terminal_recovery_ref() -> None:
    closure, decision = _c2_exact_run_evidence_with_terminal_recovery()
    terminal = closure.tool_call_records[0]
    other_tool_call_id = uuid4()
    other_attempt = _c2_project(
        terminal.attempts[0],
        tool_call_id=other_tool_call_id,
    )
    other_terminal = _c2_project(
        terminal,
        tool_call_id=other_tool_call_id,
        attempts=(other_attempt,),
    )
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }

    with pytest.raises(ValidationError, match="recovery root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "tool_call_records": (terminal, other_terminal),
                "recovery_decision_records": (decision,),
            }
        )


def test_cycle2_exact_run_evidence_rejects_unclosed_recovery_children() -> None:
    closure, decision = _c2_exact_run_evidence_with_recovered_attempt()
    tool_call = closure.tool_call_records[0]
    values = {
        field_name: getattr(closure, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }
    missing_second = _c2_project(
        tool_call,
        attempts=(tool_call.attempts[0],),
        attempt_count=1,
    )
    wrong_kind = _c2_project(
        decision,
        decision=ToolRecoveryDecision.TERMINATE_RETRY_PATH,
        stable_reason_code="RUN_BUDGET_EXHAUSTED",
        candidate_next_attempt_no=None,
    )
    duplicate = _c2_project(decision, recovery_decision_id=uuid4())
    orphan = _c2_project(decision, tool_call_id=uuid4())
    late_decision = _c2_project(
        decision,
        decided_at=tool_call.attempts[1].started_at + timedelta(microseconds=1),
    )
    wrong_run_tool_call = _c2_project(tool_call, run_id=uuid4())

    with pytest.raises(ValidationError, match="recovery root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "tool_call_records": (missing_second,)}
        )
    with pytest.raises(ValidationError, match="recovery root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "recovery_decision_records": (wrong_kind,)}
        )
    with pytest.raises(ValidationError, match="recovery root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{
                **values,
                "recovery_decision_records": (decision, duplicate),
            }
        )
    with pytest.raises(ValidationError, match="recovery root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "recovery_decision_records": (orphan,)}
        )
    with pytest.raises(ValidationError, match="recovery root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "recovery_decision_records": (late_decision,)}
        )
    with pytest.raises(ValidationError, match="ToolCall root mismatch"):
        Cycle2ExactRunEvidenceClosure(
            **{**values, "tool_call_records": (wrong_run_tool_call,)}
        )


def _c2_search_graph() -> tuple[
    TrustedOwnerScope,
    TaskRecord,
    RequestUnitRecord,
    ToolCallRecordV2,
    SearchOrdersObservation,
    OrderCandidateSetRecord,
    UUID,
    UUID,
]:
    owner = _owner_scope()
    task_id = uuid4()
    request_unit_id = uuid4()
    query_binding_ref = uuid4()
    ordinal_binding_ref = uuid4()
    task = _task(task_id=task_id, state_version=3)
    unit = _request_unit(
        request_unit_id=request_unit_id,
        task_id=task_id,
        state_version=3,
        input_binding_refs=(query_binding_ref,),
    )
    source = _c2_tool_call(
        name=Cycle2ToolName.SEARCH_ORDERS,
        task_id=task_id,
        request_unit_id=request_unit_id,
        validated_task_state_version=3,
        argument_binding_refs=(query_binding_ref,),
    )
    successful_attempt = _c2_attempt(
        tool_call_id=source.tool_call_id,
        finished_at=UTC_NOW + timedelta(seconds=1),
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    source = _c2_project(
        source,
        attempts=(successful_attempt,),
        attempt_count=1,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=successful_attempt.finished_at,
        result_ref=uuid4(),
    )
    candidate_refs = (uuid4(), uuid4())
    observation = SearchOrdersObservation(
        observation_id=uuid4(),
        private_owner_scope=owner.customer_id,
        source_tool="search_orders",
        source_tool_call_id=source.tool_call_id,
        source_resource_ref="order-search-snapshot:1",
        source_version=C2_SEARCH_SNAPSHOT_VERSION,
        candidate_target_bindings=tuple(
            SearchObservationCandidateTargetBinding(
                observation_candidate_ref=candidate_ref,
                owner_scoped_order_ref=f"owner-order:{ordinal}",
                candidate_source_version=candidate_version,
            )
            for ordinal, (candidate_ref, candidate_version) in enumerate(
                zip(
                    candidate_refs,
                    (C2_CANDIDATE_VERSION_1, C2_CANDIDATE_VERSION_2),
                    strict=True,
                ),
                start=1,
            )
        ),
        normalized_type="ORDER_SEARCH_CANDIDATES",
        normalized_value=SearchOrdersObservationValue(
            ordered_candidates=tuple(
                SearchOrdersObservationCandidate(
                    observation_candidate_ref=candidate_ref,
                    candidate_source_version=candidate_version,
                    public_summary=OrderCandidatePublicSummary(
                        order_number=f"O-100{ordinal}",
                        ordered_on_utc=UTC_NOW.date(),
                        status=OrderStatus.SHIPPED,
                        matching_items=(
                            OrderCandidateMatchingItem(
                                product_name="示例鞋",
                                quantity=1,
                            ),
                        ),
                    ),
                )
                for ordinal, (candidate_ref, candidate_version) in enumerate(
                    zip(
                        candidate_refs,
                        (C2_CANDIDATE_VERSION_1, C2_CANDIDATE_VERSION_2),
                        strict=True,
                    ),
                    start=1,
                )
            ),
            truncated=False,
        ),
        observed_at=UTC_NOW,
        recorded_at=UTC_NOW + timedelta(seconds=1),
        valid_until=UTC_NOW + timedelta(minutes=15, seconds=1),
    )
    entries = tuple(
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
    candidate_values: dict[str, object] = {
        "candidate_set_id": uuid4(),
        "private_owner_scope_ref": owner.customer_id,
        "conversation_id": uuid4(),
        "task_id": task_id,
        "request_unit_id": request_unit_id,
        "outcome": OrderCandidateSetOutcome.MULTIPLE,
        "base_task_state_version": 3,
        "result_task_state_version": 4,
        "selection_expected_task_state_version": 4,
        "query_binding_refs": (query_binding_ref,),
        "source_tool_call_id": source.tool_call_id,
        "search_observation_ref": observation.observation_id,
        "search_observation_record_schema_version": (
            ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION
        ),
        "search_observation_source_version": observation.source_version,
        "ordered_candidates": entries,
        "created_at": observation.recorded_at,
        "valid_until": observation.valid_until,
        "supersedes_candidate_set_ref": None,
    }
    candidate_values["candidate_set_version"] = (
        compute_order_candidate_set_version(**candidate_values)
    )
    candidate_set = OrderCandidateSetRecord.model_validate(candidate_values)
    return (
        owner,
        task,
        unit,
        source,
        observation,
        candidate_set,
        query_binding_ref,
        ordinal_binding_ref,
    )


def _c2_search_runtime_fields(
    owner: TrustedOwnerScope,
    candidate_set: OrderCandidateSetRecord,
    source: ToolCallRecordV2,
    task: TaskRecord,
    unit: RequestUnitRecord,
) -> dict[str, object]:
    conversation = _conversation(
        conversation_id=candidate_set.conversation_id,
        owner_customer_id=owner.customer_id,
    )
    source_message = _message(
        conversation_id=conversation.conversation_id,
        content="查找最近买的示例鞋",
    )
    run = AgentRunRecordV2(
        run_id=source.run_id,
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW,
    )
    query = AcceptedOrderSearchQueryBindingReadClosure(
        binding_ref=candidate_set.query_binding_refs[0],
        normalized_query="示例鞋",
        private_owner_scope_ref=owner.customer_id,
        conversation_id=conversation.conversation_id,
        task_id=candidate_set.task_id,
        request_unit_id=candidate_set.request_unit_id,
        accepted_task_state_version=candidate_set.base_task_state_version,
        current_task_state_version=candidate_set.base_task_state_version,
        source_message_record=source_message,
        accepted_at=source_message.received_at,
    )
    loaded = OrderSearchCurrentReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        source_run_record=run,
        current_query_binding=query,
        current_task_record=task,
        current_request_unit_record=unit,
        trusted_read_at=candidate_set.created_at,
    )
    return {
        "loaded_read_closure": loaded,
        "trusted_conversation_record": conversation,
        "source_run_record": run,
        "current_query_binding": query,
    }


def _c2_multiple_search_command() -> ApplyOrderSearchOutcomeV2Command:
    owner, task, unit, source, observation, candidate_set, query_ref, _ = (
        _c2_search_graph()
    )
    return ApplyOrderSearchOutcomeV2Command(
        owner_scope=owner,
        **_c2_search_runtime_fields(owner, candidate_set, source, task, unit),
        expected_task_record=task,
        next_task_record=_c2_project(
            task,
            status=TaskStatus.WAITING_USER,
            state_version=4,
            updated_at=observation.recorded_at,
        ),
        expected_request_unit_record=unit,
        next_request_unit_record=_c2_project(
            unit,
            status=TaskStatus.WAITING_USER,
            state_version=4,
            updated_at=observation.recorded_at,
            open_questions=("请选择候选订单",),
            observation_refs=(observation.observation_id,),
        ),
        source_tool_call_record=source,
        search_observation_record=observation,
        candidate_set_record=candidate_set,
        current_query_binding_refs=(query_ref,),
        pending_candidate_set_ref=candidate_set.candidate_set_id,
    )


def _c2_unique_search_command() -> ApplyOrderSearchOutcomeV2Command:
    owner, task, unit, source, multiple, _, query_ref, _ = _c2_search_graph()
    binding = multiple.candidate_target_bindings[0]
    candidate = multiple.normalized_value.ordered_candidates[0]
    observation = SearchOrdersObservation(
        observation_id=uuid4(),
        private_owner_scope=owner.customer_id,
        source_tool="search_orders",
        source_tool_call_id=source.tool_call_id,
        source_resource_ref=multiple.source_resource_ref,
        source_version=multiple.source_version,
        candidate_target_bindings=(binding,),
        normalized_type="ORDER_SEARCH_CANDIDATES",
        normalized_value=SearchOrdersObservationValue(
            ordered_candidates=(candidate,),
            truncated=False,
        ),
        observed_at=multiple.observed_at,
        recorded_at=multiple.recorded_at,
        valid_until=multiple.valid_until,
    )
    candidate_values: dict[str, object] = {
        "candidate_set_id": uuid4(),
        "private_owner_scope_ref": owner.customer_id,
        "conversation_id": uuid4(),
        "task_id": task.task_id,
        "request_unit_id": unit.request_unit_id,
        "outcome": OrderCandidateSetOutcome.UNIQUE,
        "base_task_state_version": 3,
        "result_task_state_version": 4,
        "selection_expected_task_state_version": None,
        "query_binding_refs": (query_ref,),
        "source_tool_call_id": source.tool_call_id,
        "search_observation_ref": observation.observation_id,
        "search_observation_record_schema_version": (
            observation.record_schema_version
        ),
        "search_observation_source_version": observation.source_version,
        "ordered_candidates": (
            OrderCandidateSetEntry(
                ordinal=1,
                observation_candidate_ref=candidate.observation_candidate_ref,
                candidate_source_version=candidate.candidate_source_version,
            ),
        ),
        "created_at": observation.recorded_at,
        "valid_until": observation.valid_until,
        "supersedes_candidate_set_ref": None,
    }
    candidate_values["candidate_set_version"] = (
        compute_order_candidate_set_version(**candidate_values)
    )
    candidate_set = OrderCandidateSetRecord.model_validate(candidate_values)
    auto_target = OrderCandidateAutoTargetRecord(
        verified_target_ref=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        conversation_id=candidate_set.conversation_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        query_input_binding_ref=query_ref,
        candidate_set_ref=candidate_set.candidate_set_id,
        candidate_set_version=candidate_set.candidate_set_version,
        source_tool_call_id=source.tool_call_id,
        search_observation_ref=observation.observation_id,
        search_observation_record_schema_version=observation.record_schema_version,
        search_observation_source_version=observation.source_version,
        observation_candidate_ref=candidate.observation_candidate_ref,
        candidate_source_version=candidate.candidate_source_version,
        owner_scoped_order_target_ref=binding.owner_scoped_order_ref,
        order_id=candidate.public_summary.order_number,
        base_task_state_version=candidate_set.base_task_state_version,
        result_task_state_version=candidate_set.result_task_state_version,
        verified_at=observation.recorded_at,
    )
    return ApplyOrderSearchOutcomeV2Command(
        owner_scope=owner,
        **_c2_search_runtime_fields(owner, candidate_set, source, task, unit),
        expected_task_record=task,
        next_task_record=_c2_project(
            task,
            state_version=4,
            updated_at=observation.recorded_at,
        ),
        expected_request_unit_record=unit,
        next_request_unit_record=_c2_project(
            unit,
            state_version=4,
            updated_at=observation.recorded_at,
            observation_refs=(observation.observation_id,),
        ),
        source_tool_call_record=source,
        search_observation_record=observation,
        candidate_set_record=candidate_set,
        current_query_binding_refs=(query_ref,),
        resolved_owner_scoped_order_target_ref=binding.owner_scoped_order_ref,
        resolved_order_id=candidate.public_summary.order_number,
        auto_target_record=auto_target,
    )


def test_cycle2_application_contracts_are_additive_strict_and_closed() -> None:
    assert RunTaskLinkRecordV2.model_fields["record_schema_version"].default == (
        "run_task_link_record.p0.v2"
    )
    assert RunTaskLinkRecordV2.model_config["frozen"] is True
    assert RunTaskLinkRecordV2.model_config["extra"] == "forbid"
    assert ApplyOrderSearchOutcomeV2Command.model_config["strict"] is True
    assert tuple(Cycle2WriteResult) == (
        Cycle2WriteResult.APPLIED,
        Cycle2WriteResult.ALREADY_APPLIED,
        Cycle2WriteResult.PROJECTION_CONFLICT,
        Cycle2WriteResult.NOT_APPLICABLE,
    )
    assert tuple(Cycle2DispatchFenceWriteResult) == (
        Cycle2DispatchFenceWriteResult.APPLIED,
        Cycle2DispatchFenceWriteResult.ALREADY_APPLIED,
        Cycle2DispatchFenceWriteResult.PROJECTION_CONFLICT,
        Cycle2DispatchFenceWriteResult.NOT_APPLICABLE,
    )


def test_cycle2_search_outcome_closes_multiple_atomically() -> None:
    owner, task, unit, source, observation, candidate_set, query_ref, _ = (
        _c2_search_graph()
    )
    next_task = _c2_project(
        task,
        status=TaskStatus.WAITING_USER,
        state_version=4,
        updated_at=observation.recorded_at,
    )
    next_unit = _c2_project(
        unit,
        status=TaskStatus.WAITING_USER,
        state_version=4,
        updated_at=observation.recorded_at,
        open_questions=("请选择候选订单",),
        observation_refs=(observation.observation_id,),
    )
    command = ApplyOrderSearchOutcomeV2Command(
        owner_scope=owner,
        **_c2_search_runtime_fields(owner, candidate_set, source, task, unit),
        expected_task_record=task,
        next_task_record=next_task,
        expected_request_unit_record=unit,
        next_request_unit_record=next_unit,
        source_tool_call_record=source,
        search_observation_record=observation,
        candidate_set_record=candidate_set,
        current_query_binding_refs=(query_ref,),
        pending_candidate_set_ref=candidate_set.candidate_set_id,
    )
    assert command.candidate_set_record.outcome is OrderCandidateSetOutcome.MULTIPLE

    command_values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    with pytest.raises(ValidationError, match="pending clarification"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **command_values,
                "pending_candidate_set_ref": uuid4(),
            }
        )


def test_cycle2_unique_search_closes_without_pending_question() -> None:
    command = _c2_unique_search_command()

    assert command.candidate_set_record.outcome is OrderCandidateSetOutcome.UNIQUE
    assert command.next_task_record.status is TaskStatus.ACTIVE
    assert command.next_request_unit_record.open_questions == ()
    assert command.pending_candidate_set_ref is None
    assert command.auto_target_record is not None
    assert command.auto_target_record.verified_target_ref.version == 4

    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    with pytest.raises(ValidationError, match="UNIQUE search"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "next_request_unit_record": _c2_project(
                    command.next_request_unit_record,
                    open_questions=("不得夹带的澄清",),
                ),
            }
        )


def _c2_rebuild_candidate_set(
    record: OrderCandidateSetRecord,
    **updates: object,
) -> OrderCandidateSetRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in type(record).model_fields
        if field_name != "candidate_set_version"
    }
    values.update(updates)
    values["candidate_set_version"] = compute_order_candidate_set_version(**values)
    return OrderCandidateSetRecord.model_validate(values)


def _c2_earlier_query_superseding_search_commands() -> tuple[
    ApplyOrderSearchOutcomeV2Command,
    ApplyOrderSearchOutcomeV2Command,
]:
    current_seed = _c2_multiple_search_command()
    owner = current_seed.owner_scope
    conversation = current_seed.trusted_conversation_record
    query_ref = current_seed.current_query_binding.binding_ref
    task_v2 = _c2_project(current_seed.expected_task_record, state_version=2)
    unit_v2 = _c2_project(current_seed.expected_request_unit_record, state_version=2)
    query_v2 = AcceptedOrderSearchQueryBindingReadClosure(
        **{
            **{
                field_name: getattr(current_seed.current_query_binding, field_name)
                for field_name in type(
                    current_seed.current_query_binding
                ).model_fields
            },
            "accepted_task_state_version": 2,
            "current_task_state_version": 2,
        }
    )
    previous_source = _c2_tool_call(
        name=Cycle2ToolName.SEARCH_ORDERS,
        task_id=task_v2.task_id,
        request_unit_id=unit_v2.request_unit_id,
        validated_task_state_version=2,
        argument_binding_refs=(query_ref,),
    )
    previous_attempt = _c2_attempt(
        tool_call_id=previous_source.tool_call_id,
        finished_at=UTC_NOW,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    previous_source = _c2_project(
        previous_source,
        attempts=(previous_attempt,),
        attempt_count=1,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=UTC_NOW,
        result_ref=uuid4(),
    )
    previous_candidate_ref = uuid4()
    previous_candidate_version = (
        "mock-order-search-candidate-source-version.p0.v1:sha256:" + "3" * 64
    )
    previous_target = SearchObservationCandidateTargetBinding(
        observation_candidate_ref=previous_candidate_ref,
        owner_scoped_order_ref="owner-order:previous",
        candidate_source_version=previous_candidate_version,
    )
    previous_safe_candidate = SearchOrdersObservationCandidate(
        observation_candidate_ref=previous_candidate_ref,
        candidate_source_version=previous_candidate_version,
        public_summary=OrderCandidatePublicSummary(
            order_number="O-0999",
            ordered_on_utc=UTC_NOW.date(),
            status=OrderStatus.SHIPPED,
            matching_items=(
                OrderCandidateMatchingItem(product_name="示例鞋", quantity=1),
            ),
        ),
    )
    previous_observation = SearchOrdersObservation(
        observation_id=uuid4(),
        private_owner_scope=owner.customer_id,
        source_tool="search_orders",
        source_tool_call_id=previous_source.tool_call_id,
        source_resource_ref="order-search-snapshot:previous",
        source_version=(
            "mock-order-search-snapshot-source-version.p0.v1:sha256:"
            + "c" * 64
        ),
        candidate_target_bindings=(previous_target,),
        normalized_type="ORDER_SEARCH_CANDIDATES",
        normalized_value=SearchOrdersObservationValue(
            ordered_candidates=(previous_safe_candidate,),
            truncated=False,
        ),
        observed_at=UTC_NOW,
        recorded_at=UTC_NOW,
        valid_until=UTC_NOW + timedelta(minutes=15),
    )
    previous_values: dict[str, object] = {
        "candidate_set_id": uuid4(),
        "private_owner_scope_ref": owner.customer_id,
        "conversation_id": conversation.conversation_id,
        "task_id": task_v2.task_id,
        "request_unit_id": unit_v2.request_unit_id,
        "outcome": OrderCandidateSetOutcome.UNIQUE,
        "base_task_state_version": 2,
        "result_task_state_version": 3,
        "selection_expected_task_state_version": None,
        "query_binding_refs": (query_ref,),
        "source_tool_call_id": previous_source.tool_call_id,
        "search_observation_ref": previous_observation.observation_id,
        "search_observation_record_schema_version": (
            previous_observation.record_schema_version
        ),
        "search_observation_source_version": previous_observation.source_version,
        "ordered_candidates": (
            OrderCandidateSetEntry(
                ordinal=1,
                observation_candidate_ref=previous_candidate_ref,
                candidate_source_version=previous_candidate_version,
            ),
        ),
        "created_at": previous_observation.recorded_at,
        "valid_until": previous_observation.valid_until,
        "supersedes_candidate_set_ref": None,
    }
    previous_values["candidate_set_version"] = compute_order_candidate_set_version(
        **previous_values
    )
    previous_candidate_set = OrderCandidateSetRecord.model_validate(previous_values)
    previous_auto_target = OrderCandidateAutoTargetRecord(
        verified_target_ref=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        conversation_id=conversation.conversation_id,
        task_id=task_v2.task_id,
        request_unit_id=unit_v2.request_unit_id,
        query_input_binding_ref=query_ref,
        candidate_set_ref=previous_candidate_set.candidate_set_id,
        candidate_set_version=previous_candidate_set.candidate_set_version,
        source_tool_call_id=previous_source.tool_call_id,
        search_observation_ref=previous_observation.observation_id,
        search_observation_record_schema_version=(
            previous_observation.record_schema_version
        ),
        search_observation_source_version=previous_observation.source_version,
        observation_candidate_ref=previous_candidate_ref,
        candidate_source_version=previous_candidate_version,
        owner_scoped_order_target_ref=previous_target.owner_scoped_order_ref,
        order_id=previous_safe_candidate.public_summary.order_number,
        base_task_state_version=previous_candidate_set.base_task_state_version,
        result_task_state_version=previous_candidate_set.result_task_state_version,
        verified_at=previous_observation.recorded_at,
    )
    previous_run = AgentRunRecordV2(
        run_id=previous_source.run_id,
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW,
    )
    previous_loaded = OrderSearchCurrentReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        source_run_record=previous_run,
        current_query_binding=query_v2,
        current_task_record=task_v2,
        current_request_unit_record=unit_v2,
        trusted_read_at=previous_observation.recorded_at,
    )
    previous_command = ApplyOrderSearchOutcomeV2Command(
        owner_scope=owner,
        loaded_read_closure=previous_loaded,
        trusted_conversation_record=conversation,
        source_run_record=previous_run,
        current_query_binding=query_v2,
        expected_task_record=task_v2,
        next_task_record=_c2_project(task_v2, state_version=3),
        expected_request_unit_record=unit_v2,
        next_request_unit_record=_c2_project(
            unit_v2,
            state_version=3,
            observation_refs=(previous_observation.observation_id,),
        ),
        source_tool_call_record=previous_source,
        search_observation_record=previous_observation,
        candidate_set_record=previous_candidate_set,
        current_query_binding_refs=(query_ref,),
        resolved_owner_scoped_order_target_ref=(
            previous_target.owner_scoped_order_ref
        ),
        resolved_order_id=previous_safe_candidate.public_summary.order_number,
        auto_target_record=previous_auto_target,
    )

    current_candidate_set = _c2_rebuild_candidate_set(
        current_seed.candidate_set_record,
        supersedes_candidate_set_ref=previous_candidate_set.candidate_set_id,
    )
    query_v3 = AcceptedOrderSearchQueryBindingReadClosure(
        **{
            **{
                field_name: getattr(query_v2, field_name)
                for field_name in type(query_v2).model_fields
            },
            "current_task_state_version": 3,
        }
    )
    current_loaded = OrderSearchCurrentReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        source_run_record=current_seed.source_run_record,
        current_query_binding=query_v3,
        current_task_record=previous_command.next_task_record,
        current_request_unit_record=previous_command.next_request_unit_record,
        current_candidate_source_tool_call_record=previous_source,
        current_search_observation_record=previous_observation,
        current_candidate_set_record=previous_candidate_set,
        current_auto_target_records=(previous_auto_target,),
        trusted_read_at=current_seed.search_observation_record.recorded_at,
    )
    current_command = ApplyOrderSearchOutcomeV2Command(
        owner_scope=owner,
        loaded_read_closure=current_loaded,
        trusted_conversation_record=conversation,
        source_run_record=current_seed.source_run_record,
        current_query_binding=query_v3,
        expected_task_record=previous_command.next_task_record,
        next_task_record=_c2_project(
            previous_command.next_task_record,
            status=TaskStatus.WAITING_USER,
            state_version=4,
            updated_at=current_seed.search_observation_record.recorded_at,
        ),
        expected_request_unit_record=previous_command.next_request_unit_record,
        next_request_unit_record=_c2_project(
            previous_command.next_request_unit_record,
            status=TaskStatus.WAITING_USER,
            state_version=4,
            updated_at=current_seed.search_observation_record.recorded_at,
            open_questions=("请选择候选订单",),
            observation_refs=(
                previous_observation.observation_id,
                current_seed.search_observation_record.observation_id,
            ),
        ),
        source_tool_call_record=current_seed.source_tool_call_record,
        search_observation_record=current_seed.search_observation_record,
        candidate_set_record=current_candidate_set,
        previous_candidate_set_record=previous_candidate_set,
        current_query_binding_refs=(query_ref,),
        pending_candidate_set_ref=current_candidate_set.candidate_set_id,
    )
    return current_command, previous_command


def test_cycle2_search_accepts_earlier_still_current_query_and_supersedes_set() -> None:
    current, previous = _c2_earlier_query_superseding_search_commands()

    previous_source = previous.source_tool_call_record
    previous_observation = previous.search_observation_record
    previous_candidate_set = previous.candidate_set_record
    assert previous_candidate_set.outcome is OrderCandidateSetOutcome.UNIQUE
    assert previous.next_task_record == current.expected_task_record
    assert previous.next_request_unit_record == current.expected_request_unit_record
    assert current.expected_task_record.status is TaskStatus.ACTIVE
    assert current.expected_request_unit_record.open_questions == ()
    assert current.current_query_binding.accepted_task_state_version == 2
    assert current.current_query_binding.current_task_state_version == 3
    assert (
        previous_candidate_set.source_tool_call_id == previous_source.tool_call_id
    )
    assert previous_candidate_set.search_observation_ref == (
        previous_observation.observation_id
    )
    assert previous_candidate_set.created_at == previous_observation.recorded_at
    assert (
        current.candidate_set_record.source_tool_call_id
        != previous_candidate_set.source_tool_call_id
    )
    assert (
        current.candidate_set_record.search_observation_ref
        != previous_candidate_set.search_observation_ref
    )
    assert (
        current.candidate_set_record.supersedes_candidate_set_ref
        == previous_candidate_set.candidate_set_id
    )
    previous_refs = {
        candidate.observation_candidate_ref
        for candidate in previous_observation.normalized_value.ordered_candidates
    }
    current_refs = {
        candidate.observation_candidate_ref
        for candidate in current.search_observation_record.normalized_value.ordered_candidates
    }
    assert previous_refs.isdisjoint(current_refs)


def test_cycle2_search_current_read_rejects_partial_or_impossible_graph() -> None:
    current, _ = _c2_earlier_query_superseding_search_commands()
    closure = current.loaded_read_closure
    closure_values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }
    with pytest.raises(ValidationError, match="graph must be complete"):
        OrderSearchCurrentReadClosure(
            **{
                **closure_values,
                "current_candidate_source_tool_call_record": None,
            }
        )

    previous_source = closure.current_candidate_source_tool_call_record
    previous_observation = closure.current_search_observation_record
    previous_candidate_set = closure.current_candidate_set_record
    assert previous_source is not None
    assert previous_observation is not None
    assert previous_candidate_set is not None
    with pytest.raises(ValidationError, match="aggregate mismatch"):
        OrderSearchCurrentReadClosure(
            **{
                **closure_values,
                "current_candidate_source_tool_call_record": _c2_project(
                    previous_source,
                    private_owner_scope_ref="customer-B",
                ),
            }
        )
    with pytest.raises(ValidationError, match="aggregate mismatch"):
        OrderSearchCurrentReadClosure(
            **{
                **closure_values,
                "current_search_observation_record": SearchOrdersObservation(
                    **{
                        **{
                            field_name: getattr(previous_observation, field_name)
                            for field_name in type(
                                previous_observation
                            ).model_fields
                        },
                        "private_owner_scope": "customer-B",
                    }
                ),
            }
        )
    with pytest.raises(ValidationError, match="aggregate mismatch"):
        OrderSearchCurrentReadClosure(
            **{
                **closure_values,
                "current_search_observation_record": SearchOrdersObservation(
                    **{
                        **{
                            field_name: getattr(previous_observation, field_name)
                            for field_name in type(
                                previous_observation
                            ).model_fields
                        },
                        "source_tool_call_id": uuid4(),
                    }
                ),
            }
        )
    with pytest.raises(ValidationError):
        OrderSearchCurrentReadClosure(
            **{
                **closure_values,
                "current_candidate_set_record": _c2_rebuild_candidate_set(
                    previous_candidate_set,
                    search_observation_ref=uuid4(),
                ),
            }
        )

    active_task = _c2_project(
        current.next_task_record,
        status=TaskStatus.ACTIVE,
    )
    active_unit = _c2_project(
        current.next_request_unit_record,
        status=TaskStatus.ACTIVE,
        open_questions=(),
    )
    query_v4 = AcceptedOrderSearchQueryBindingReadClosure(
        **{
            **{
                field_name: getattr(current.current_query_binding, field_name)
                for field_name in type(current.current_query_binding).model_fields
            },
            "current_task_state_version": active_task.state_version,
        }
    )
    with pytest.raises(ValidationError, match="MULTIPLE CandidateSet Task effect"):
        OrderSearchCurrentReadClosure(
            owner_scope=current.owner_scope,
            trusted_conversation_record=current.trusted_conversation_record,
            source_run_record=current.source_run_record,
            current_query_binding=query_v4,
            current_task_record=active_task,
            current_request_unit_record=active_unit,
            current_candidate_source_tool_call_record=(
                current.source_tool_call_record
            ),
            current_search_observation_record=current.search_observation_record,
            current_candidate_set_record=current.candidate_set_record,
            trusted_read_at=current.search_observation_record.recorded_at,
        )


@pytest.mark.parametrize(
    ("attack", "error"),
    [
        ("same_tool", "distinct Search outcomes"),
        ("same_observation", "distinct Search outcomes"),
        ("candidate_ref_partial", "disjoint candidate refs"),
        ("candidate_ref_whole", "disjoint candidate refs"),
    ],
)
def test_cycle2_search_rejects_supersession_authority_reuse(
    attack: str,
    error: str,
) -> None:
    command, _ = _c2_earlier_query_superseding_search_commands()
    previous_source = command.loaded_read_closure.current_candidate_source_tool_call_record
    previous_observation = command.loaded_read_closure.current_search_observation_record
    previous_candidate_set = command.loaded_read_closure.current_candidate_set_record
    assert previous_source is not None
    assert previous_observation is not None
    assert previous_candidate_set is not None

    if attack == "candidate_ref_whole":
        whole_reuse_observation = SearchOrdersObservation(
            **{
                **{
                    field_name: getattr(previous_observation, field_name)
                    for field_name in type(previous_observation).model_fields
                },
                "candidate_target_bindings": (
                    command.search_observation_record.candidate_target_bindings
                ),
                "normalized_value": (
                    command.search_observation_record.normalized_value
                ),
            }
        )
        with pytest.raises(ValueError, match=error):
            application_records_module._require_disjoint_search_candidate_refs(
                previous=whole_reuse_observation,
                current=command.search_observation_record,
            )
        return

    if attack == "same_tool":
        shared_tool_call_id = command.source_tool_call_record.tool_call_id
        previous_attempts = tuple(
            _c2_project(attempt, tool_call_id=shared_tool_call_id)
            for attempt in previous_source.attempts
        )
        previous_source = _c2_project(
            previous_source,
            tool_call_id=shared_tool_call_id,
            attempts=previous_attempts,
        )
        previous_observation = SearchOrdersObservation(
            **{
                **{
                    field_name: getattr(previous_observation, field_name)
                    for field_name in type(previous_observation).model_fields
                },
                "source_tool_call_id": shared_tool_call_id,
            }
        )
        previous_candidate_set = _c2_rebuild_candidate_set(
            previous_candidate_set,
            source_tool_call_id=shared_tool_call_id,
        )
    elif attack == "same_observation":
        shared_observation_id = command.search_observation_record.observation_id
        previous_observation = SearchOrdersObservation(
            **{
                **{
                    field_name: getattr(previous_observation, field_name)
                    for field_name in type(previous_observation).model_fields
                },
                "observation_id": shared_observation_id,
            }
        )
        previous_candidate_set = _c2_rebuild_candidate_set(
            previous_candidate_set,
            search_observation_ref=shared_observation_id,
        )
    else:
        shared_candidate_ref = (
            command.search_observation_record.normalized_value.ordered_candidates[
                0
            ].observation_candidate_ref
        )
        old_target = previous_observation.candidate_target_bindings[0]
        old_candidate = previous_observation.normalized_value.ordered_candidates[0]
        shared_target = SearchObservationCandidateTargetBinding(
            observation_candidate_ref=shared_candidate_ref,
            owner_scoped_order_ref=old_target.owner_scoped_order_ref,
            candidate_source_version=old_target.candidate_source_version,
        )
        shared_safe_candidate = SearchOrdersObservationCandidate(
            observation_candidate_ref=shared_candidate_ref,
            candidate_source_version=old_candidate.candidate_source_version,
            public_summary=old_candidate.public_summary,
        )
        previous_observation = SearchOrdersObservation(
            **{
                **{
                    field_name: getattr(previous_observation, field_name)
                    for field_name in type(previous_observation).model_fields
                },
                "candidate_target_bindings": (shared_target,),
                "normalized_value": SearchOrdersObservationValue(
                    ordered_candidates=(shared_safe_candidate,),
                    truncated=False,
                ),
            }
        )
        previous_candidate_set = _c2_rebuild_candidate_set(
            previous_candidate_set,
            ordered_candidates=(
                OrderCandidateSetEntry(
                    ordinal=1,
                    observation_candidate_ref=shared_candidate_ref,
                    candidate_source_version=old_candidate.candidate_source_version,
                ),
            ),
        )

    previous_auto_target = command.loaded_read_closure.current_auto_target_records[0]
    previous_entry = previous_candidate_set.ordered_candidates[0]
    previous_auto_target = _c2_project(
        previous_auto_target,
        candidate_set_ref=previous_candidate_set.candidate_set_id,
        candidate_set_version=previous_candidate_set.candidate_set_version,
        source_tool_call_id=previous_source.tool_call_id,
        search_observation_ref=previous_observation.observation_id,
        search_observation_source_version=previous_observation.source_version,
        observation_candidate_ref=previous_entry.observation_candidate_ref,
        candidate_source_version=previous_entry.candidate_source_version,
    )
    loaded = OrderSearchCurrentReadClosure(
        **{
            **{
                field_name: getattr(command.loaded_read_closure, field_name)
                for field_name in type(command.loaded_read_closure).model_fields
            },
            "current_candidate_source_tool_call_record": previous_source,
            "current_search_observation_record": previous_observation,
            "current_candidate_set_record": previous_candidate_set,
            "current_auto_target_records": (previous_auto_target,),
        }
    )
    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }

    with pytest.raises(ValidationError, match=error):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "loaded_read_closure": loaded,
                "previous_candidate_set_record": previous_candidate_set,
            }
        )


def test_cycle2_search_rejects_forged_previous_record() -> None:
    command, _ = _c2_earlier_query_superseding_search_commands()
    previous = command.previous_candidate_set_record
    assert previous is not None
    forged = _c2_rebuild_candidate_set(previous, candidate_set_id=uuid4())
    current = _c2_rebuild_candidate_set(
        command.candidate_set_record,
        supersedes_candidate_set_ref=forged.candidate_set_id,
    )
    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }

    with pytest.raises(ValidationError, match="command/read closure mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "candidate_set_record": current,
                "previous_candidate_set_record": forged,
            }
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("goal_text", "被夹带改写的目标"),
        ("constraint_refs", (uuid4(),)),
        ("dependency_refs", (uuid4(),)),
        ("input_binding_refs", (uuid4(),)),
        ("result_refs", (uuid4(),)),
    ],
)
def test_cycle2_search_rejects_unauthorized_request_unit_drift(
    field_name: str,
    replacement: object,
) -> None:
    command = _c2_multiple_search_command()
    values = {
        field_name_: getattr(command, field_name_)
        for field_name_ in type(command).model_fields
    }
    with pytest.raises(ValidationError, match="non-authorized field"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "next_request_unit_record": _c2_project(
                    command.next_request_unit_record,
                    **{field_name: replacement},
                ),
            }
        )


def test_cycle2_search_rejects_task_drift_and_time_rollback() -> None:
    command = _c2_multiple_search_command()
    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    with pytest.raises(ValidationError, match="non-authorized field"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "next_task_record": _c2_project(
                    command.next_task_record,
                    last_outcome_ref=uuid4(),
                ),
            }
        )
    future_expected = _c2_project(
        command.expected_task_record,
        updated_at=command.search_observation_record.recorded_at
        + timedelta(seconds=1),
    )
    with pytest.raises(ValidationError, match="command/read closure mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "expected_task_record": future_expected,
                "next_task_record": _c2_project(
                    command.next_task_record,
                    created_at=future_expected.created_at,
                ),
            }
        )


def test_cycle2_search_requires_exact_tool_candidate_query_binding_closure() -> None:
    command = _c2_multiple_search_command()
    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    wrong_binding_ref = uuid4()
    wrong_source = _c2_project(
        command.source_tool_call_record,
        argument_binding_refs=(wrong_binding_ref,),
    )
    with pytest.raises(ValidationError, match="query binding closure"):
        ApplyOrderSearchOutcomeV2Command(
            **{**values, "source_tool_call_record": wrong_source}
        )
    with pytest.raises(ValidationError, match="at most 1 item"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "current_query_binding_refs": (
                    *command.current_query_binding_refs,
                    wrong_binding_ref,
                ),
            }
        )
    with pytest.raises(ValidationError, match="source graph mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "source_tool_call_record": _c2_project(
                    command.source_tool_call_record,
                    validated_task_state_version=2,
                ),
            }
        )


def test_cycle2_commands_reject_constructed_trusted_owner_scope() -> None:
    command = _c2_multiple_search_command()
    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    constructed = TrustedOwnerScope.model_construct(customer_id="customer-A")

    with pytest.raises(ValidationError, match="exact trusted projection"):
        ApplyOrderSearchOutcomeV2Command(
            **{**values, "owner_scope": constructed}
        )

    mutated = _owner_scope()
    mutated.__dict__["customer_id"] = "customer-B"
    with pytest.raises(ValidationError, match="exact trusted projection"):
        ApplyOrderSearchOutcomeV2Command(
            **{**values, "owner_scope": mutated}
        )

    private_sidecar = _owner_scope()
    private_sidecar.__pydantic_private__ = {"forged_authority": True}
    with pytest.raises(ValidationError, match="exact trusted projection"):
        ApplyOrderSearchOutcomeV2Command(
            **{**values, "owner_scope": private_sidecar}
        )


def _c2_continuation_command(
    *,
    name: str = "product_description",
    normalized_value: object = "跑鞋",
) -> ApplyContinuationInputBindingV2Command:
    owner = _owner_scope()
    conversation = _conversation(owner_customer_id=owner.customer_id)
    task = _task(state_version=3)
    existing = _input_binding_v2()
    unit = _request_unit(
        task_id=task.task_id,
        state_version=3,
        input_binding_refs=(existing.binding_id,),
    )
    message = _message(
        conversation_id=conversation.conversation_id,
        content="还是那双跑鞋",
        received_at=UTC_NOW + timedelta(seconds=1),
    )
    trusted_now = UTC_NOW + timedelta(seconds=2)
    closure = ContinuationInputBindingReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        current_conversation_task_link_record=_conversation_task_link(
            conversation_id=conversation.conversation_id,
            task_id=task.task_id,
        ),
        saved_user_message_record=message,
        current_task_record=task,
        current_request_unit_record=unit,
        current_input_binding_records=(existing,),
        trusted_now=trusted_now,
    )
    binding = _input_binding_v2(
        name=name,
        normalized_value=normalized_value,
        source_refs=(message.message_id,),
        created_at=trusted_now,
        updated_at=trusted_now,
    )
    return ApplyContinuationInputBindingV2Command(
        loaded_closure=closure,
        new_input_binding_record=binding,
        next_task_record=_c2_project(
            task,
            state_version=4,
            updated_at=trusted_now,
        ),
        next_request_unit_record=_c2_project(
            unit,
            state_version=4,
            updated_at=trusted_now,
            input_binding_refs=(existing.binding_id, binding.binding_id),
        ),
    )


def test_cycle2_continuation_binding_is_one_exact_nonordinal_cas() -> None:
    command = _c2_continuation_command()
    closure = command.loaded_closure
    assert command.new_input_binding_record.source_refs == (
        closure.saved_user_message_record.message_id,
    )
    assert command.next_task_record.state_version == 4
    assert command.next_request_unit_record.state_version == 4
    assert command.next_task_record.status is closure.current_task_record.status

    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    ordinal = _input_binding_v2(
        name="candidate_ordinal",
        normalized_value=2,
        source_refs=(closure.saved_user_message_record.message_id,),
        created_at=closure.trusted_now,
        updated_at=closure.trusted_now,
    )
    with pytest.raises(ValidationError, match="rejected selection decision"):
        ApplyContinuationInputBindingV2Command(
            **{**values, "new_input_binding_record": ordinal}
        )
    with pytest.raises(ValidationError, match="versions must close atomically"):
        ApplyContinuationInputBindingV2Command(
            **{
                **values,
                "next_request_unit_record": _c2_project(
                    command.next_request_unit_record,
                    state_version=5,
                ),
            }
        )
    with pytest.raises(ValidationError, match="non-authorized field"):
        ApplyContinuationInputBindingV2Command(
            **{
                **values,
                "next_request_unit_record": _c2_project(
                    command.next_request_unit_record,
                    goal_text="夹带目标改写",
                ),
            }
        )


def test_cycle2_rejected_ordinal_claim_is_one_binding_only_cas() -> None:
    ordinary = _c2_continuation_command()
    closure = ordinary.loaded_closure
    ordinal = _input_binding_v2(
        name="candidate_ordinal",
        normalized_value=6,
        source_refs=(closure.saved_user_message_record.message_id,),
        created_at=closure.trusted_now,
        updated_at=closure.trusted_now,
    )
    claim = Cycle2OrdinalClaimPreparation(
        ordinal_input_binding=ordinal,
        selection_request=OrderCandidateSelectionRequest(
            source_message_ref=closure.saved_user_message_record.message_id,
            ordinal_input_binding_ref=ordinal.binding_id,
            ordinal=6,
        ),
        base_task_state_version=closure.current_task_record.state_version,
        result_task_state_version=closure.current_task_record.state_version + 1,
    )
    rejected = reject_cycle2_ordinal_selection(
        claim=claim,
        reason=Cycle2OrdinalSelectionRejectionReason.OUT_OF_RANGE,
    )
    command = ApplyContinuationInputBindingV2Command(
        loaded_closure=closure,
        new_input_binding_record=ordinal,
        next_task_record=_c2_project(
            closure.current_task_record,
            state_version=4,
            updated_at=closure.trusted_now,
        ),
        next_request_unit_record=_c2_project(
            closure.current_request_unit_record,
            state_version=4,
            updated_at=closure.trusted_now,
            input_binding_refs=(
                *closure.current_request_unit_record.input_binding_refs,
                ordinal.binding_id,
            ),
        ),
        rejected_ordinal_selection=rejected,
    )

    assert command.rejected_ordinal_selection == rejected
    assert command.next_task_record.status is closure.current_task_record.status
    assert command.next_request_unit_record.open_questions == (
        closure.current_request_unit_record.open_questions
    )
    assert not {
        "selection_record",
        "selected_target_ref",
        "tool_call_record",
    }.intersection(type(command).model_fields)


def test_cycle2_continuation_supersedes_only_one_current_same_name_binding() -> None:
    command = _c2_continuation_command()
    closure = command.loaded_closure
    existing = closure.current_input_binding_records[0]
    trusted_now = closure.trusted_now
    replacement = _input_binding_v2(
        name="order_id",
        normalized_value="O-2002",
        source_refs=(closure.saved_user_message_record.message_id,),
        created_at=trusted_now,
        updated_at=trusted_now,
        supersedes=existing.binding_id,
    )
    replaced = ApplyContinuationInputBindingV2Command(
        loaded_closure=closure,
        new_input_binding_record=replacement,
        next_task_record=command.next_task_record,
        next_request_unit_record=_c2_project(
            command.next_request_unit_record,
            input_binding_refs=(replacement.binding_id,),
        ),
    )
    assert replaced.next_request_unit_record.input_binding_refs == (
        replacement.binding_id,
    )

    with pytest.raises(ValidationError, match="supersedes"):
        ApplyContinuationInputBindingV2Command(
            loaded_closure=closure,
            new_input_binding_record=_c2_project(
                replacement,
                supersedes=uuid4(),
            ),
            next_task_record=command.next_task_record,
            next_request_unit_record=replaced.next_request_unit_record,
        )


def test_cycle2_continuation_read_closure_rejects_wrong_owner_and_message() -> None:
    command = _c2_continuation_command()
    closure = command.loaded_closure
    values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }
    with pytest.raises(ValidationError, match="owner/Conversation/Message"):
        ContinuationInputBindingReadClosure(
            **{
                **values,
                "saved_user_message_record": _c2_project(
                    closure.saved_user_message_record,
                    direction=MessageDirection.ASSISTANT,
                ),
            }
        )
    with pytest.raises(ValidationError, match="Task owner"):
        ContinuationInputBindingReadClosure(
            **{**values, "owner_scope": _owner_scope("customer-B")}
        )
    with pytest.raises(ValidationError, match="exactly match RequestUnit refs"):
        ContinuationInputBindingReadClosure(
            **{
                **values,
                "current_input_binding_records": (_input_binding_v2(),),
            }
        )


def test_cycle2_candidate_selection_requires_exact_current_closure_and_cas() -> None:
    search_command, previous_search_command = (
        _c2_earlier_query_superseding_search_commands()
    )
    previous_candidate_set = previous_search_command.candidate_set_record
    owner = search_command.owner_scope
    task = search_command.expected_task_record
    unit = search_command.expected_request_unit_record
    observation = search_command.search_observation_record
    candidate_set = search_command.candidate_set_record
    query_ref = search_command.current_query_binding.binding_ref
    ordinal_ref = uuid4()
    current_task = search_command.next_task_record
    current_unit = _c2_project(
        search_command.next_request_unit_record,
        input_binding_refs=(query_ref,),
    )
    request = OrderCandidateSelectionRequest(
        source_message_ref=uuid4(),
        ordinal_input_binding_ref=ordinal_ref,
        ordinal=2,
    )
    conversation = search_command.trusted_conversation_record
    source_message = _message(
        message_id=request.source_message_ref,
        conversation_id=conversation.conversation_id,
        content="第二个",
        received_at=observation.recorded_at + timedelta(seconds=1),
    )
    query_binding_seed = search_command.current_query_binding
    assert isinstance(
        query_binding_seed,
        AcceptedOrderSearchQueryBindingReadClosure,
    )
    query_binding = AcceptedOrderSearchQueryBindingReadClosure(
        **{
            **{
                field_name: getattr(query_binding_seed, field_name)
                for field_name in AcceptedOrderSearchQueryBindingReadClosure.model_fields
            },
            "current_task_state_version": current_task.state_version,
        }
    )
    assert query_binding.accepted_task_state_version == 2
    assert candidate_set.supersedes_candidate_set_ref == (
        previous_candidate_set.candidate_set_id
    )
    current_run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=source_message.received_at,
    )
    selected_at = observation.recorded_at + timedelta(seconds=2)
    closure = OrderCandidateSelectionReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        current_run_record=current_run,
        current_run_task_link_record=RunTaskLinkRecordV2(
            run_id=current_run.run_id,
            task_id=current_task.task_id,
            base_task_state_version=current_task.state_version,
        ),
        current_task_record=current_task,
        current_request_unit_record=current_unit,
        current_candidate_set_record=candidate_set,
        search_observation_record=observation,
        selection_request=request,
        saved_selection_message_record=source_message,
        current_query_binding=query_binding,
        pending_candidate_set_ref=candidate_set.candidate_set_id,
        current_query_binding_refs=(query_ref,),
        resolved_owner_scoped_order_target_ref="owner-order:2",
        trusted_now=selected_at,
    )
    selected = candidate_set.ordered_candidates[1]
    issued_selected_target = IssuedSelectedTargetRef.fresh()
    selected_target_ref = issued_selected_target.selected_target_ref
    selection = OrderCandidateSelectionRecord(
        selection_id=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        conversation_id=candidate_set.conversation_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        source_message_ref=request.source_message_ref,
        ordinal_input_binding_ref=ordinal_ref,
        candidate_set_ref=candidate_set.candidate_set_id,
        candidate_set_version=candidate_set.candidate_set_version,
        search_observation_ref=observation.observation_id,
        search_observation_record_schema_version=(
            observation.record_schema_version
        ),
        observation_candidate_ref=selected.observation_candidate_ref,
        candidate_source_version=selected.candidate_source_version,
        owner_scoped_order_target_ref="owner-order:2",
        selected_target_ref=str(selected_target_ref),
        base_task_state_version=4,
        result_task_state_version=5,
        selected_at=selected_at,
    )
    command = build_order_candidate_selection_v2_command(
        loaded_closure=closure,
        ordinal_input_binding_record=_input_binding_v2(
            binding_id=ordinal_ref,
            name="candidate_ordinal",
            normalized_value=2,
            source_refs=(request.source_message_ref,),
            created_at=selected_at,
            updated_at=selected_at,
        ),
        issued_selected_target=issued_selected_target,
        next_task_record=_c2_project(
            current_task,
            status=TaskStatus.ACTIVE,
            state_version=5,
            updated_at=selection.selected_at,
        ),
        next_request_unit_record=_c2_project(
            current_unit,
            status=TaskStatus.ACTIVE,
            state_version=5,
            updated_at=selection.selected_at,
            input_binding_refs=(query_ref, ordinal_ref),
            open_questions=(),
        ),
        selection_record=selection,
        closed_pending_candidate_set_ref=candidate_set.candidate_set_id,
    )
    assert command.selection_record.owner_scoped_order_target_ref == "owner-order:2"
    assert command.selection_record.selected_target_ref == str(selected_target_ref)
    assert UUID(command.selection_record.selected_target_ref) == selected_target_ref
    command.require_live_target_issuance()

    snapshot = build_cycle2_registry_snapshot()
    focused = ModelVisibleTaskSummary(
        task_alias="task-1",
        request_unit_alias="unit-1",
        goal_summary=current_unit.goal_text,
        status=current_task.status.value,
        open_questions=current_unit.open_questions,
    )
    request_input_v3 = RequestUnderstandingInput(
        schema_version="e2e01-thin-v1",
        run_id=current_run.run_id,
        message_ref=source_message.message_id,
        original_query=source_message.content,
        active_task_summaries=(focused,),
        focused_task_summary=focused,
        provider_visible_tool_specs=snapshot.provider_visible_toolset,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
    )
    output_v3 = Cycle2ContinuationRequestUnderstandingOutputV2(
        schema_version="e2e01-cycle2-continuation.p0.v2",
        message_ref=source_message.message_id,
        contextualization=QueryContextualizationCandidateV2(
            text="选择当前订单候选",
            resolved_reference_candidates=(),
            uncertainties=(),
            source_message_refs=(source_message.message_id,),
        ),
        task_delta_candidates=(
            Cycle2ContinuationTaskDeltaCandidateV2(
                candidate_id=uuid4(),
                operation=TaskDeltaOperation.SUPPLY_INPUT,
                target_task_alias="task-1",
                target_request_unit_alias="unit-1",
                input_candidates=(
                    Cycle2InputCandidate(
                        name="candidate_ordinal",
                        candidate_value=2,
                        source_ref=source_message.message_id,
                        source_quote="第二",
                        confidence=0.99,
                    ),
                ),
                confidence=0.99,
            ),
        ),
    )
    current_query_binding = InputBindingV2(
        binding_id=query_ref,
        name="product_description",
        normalized_value=query_binding.normalized_query,
        authority=InputAuthority.USER_CLAIM,
        source_refs=(query_binding.source_message_record.message_id,),
        validation_status=InputValidationStatus.ACCEPTED,
        confirmed_by_user=True,
        created_at=query_binding.accepted_at,
        updated_at=query_binding.accepted_at,
    )
    decision_v3 = reduce_cycle2_continuation_task_delta(
        request_input=request_input_v3,
        output=output_v3,
        authoritative_messages={
            source_message.message_id: source_message.content
        },
        customer_context=_customer_context(),
        current_task=current_task,
        current_request_unit=current_unit,
        current_input_bindings=(current_query_binding,),
        identity_allocation=Cycle2ContinuationIdentityAllocationV3(
            request_understanding_record_id=uuid4(),
            accepted_delta_id=uuid4(),
            input_binding_ids=(ordinal_ref,),
        ),
        now=selected_at,
    )
    assert type(decision_v3) is Cycle2ContinuationDecisionV3
    issued_v3 = IssuedSelectedTargetRef.fresh_v3()
    selection_v3 = _c2_project(
        selection,
        selected_target_ref=str(issued_v3.selected_target_ref),
    )
    child_v3 = decision_v3.closure.accepted_task_deltas[0]
    effect_trace_records = tuple(
        TraceEventV2(
            trace_event_id=uuid4(),
            event_type=event_type,
            occurred_at=selected_at,
            run_id=current_run.run_id,
            message_ref=source_message.message_id,
            accepted_delta_ref=child_v3.accepted_delta_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            input_binding_ref=(
                ordinal_ref
                if event_type is TraceEventType.INPUT_BINDING_RECORDED
                else None
            ),
        )
        for event_type in (
            TraceEventType.TASK_DELTA_VALIDATED,
            TraceEventType.TASK_DELTA_ACCEPTED,
            TraceEventType.INPUT_BINDING_RECORDED,
            TraceEventType.TASK_STATE_CHANGED,
        )
    )
    command_v3 = build_order_candidate_selection_v3_command(
        loaded_closure=closure,
        ordinal_input_binding_record=decision_v3.input_bindings[0],
        issued_selected_target=issued_v3,
        next_task_record=command.next_task_record,
        next_request_unit_record=command.next_request_unit_record,
        selection_record=selection_v3,
        closed_pending_candidate_set_ref=candidate_set.candidate_set_id,
        decision=decision_v3,
        effect_trace_records=effect_trace_records,
    )
    assert type(command_v3) is ApplyOrderCandidateSelectionV3Command
    assert not isinstance(command_v3, ApplyOrderCandidateSelectionV2Command)
    command_v3.require_live_target_issuance()
    with pytest.raises(ValidationError, match="fresh v3 Application issuance"):
        build_order_candidate_selection_v3_command(
            loaded_closure=closure,
            ordinal_input_binding_record=decision_v3.input_bindings[0],
            issued_selected_target=issued_selected_target,
            next_task_record=command.next_task_record,
            next_request_unit_record=command.next_request_unit_record,
            selection_record=selection,
            closed_pending_candidate_set_ref=candidate_set.candidate_set_id,
            decision=decision_v3,
            effect_trace_records=effect_trace_records,
        )

    closure_values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }
    with pytest.raises(ValidationError, match="pre-CAS ordinal ref"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "current_request_unit_record": _c2_project(
                    current_unit,
                    input_binding_refs=(query_ref, ordinal_ref),
                ),
            }
        )
    command_values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }

    digest = sha256(
        closure.resolved_owner_scoped_order_target_ref.encode("utf-8")
    ).digest()
    derived_bytes = bytearray(digest[:16])
    derived_bytes[6] = (derived_bytes[6] & 0x0F) | 0x40
    derived_bytes[8] = (derived_bytes[8] & 0x3F) | 0x80
    derived_target_ref = UUID(bytes=bytes(derived_bytes))
    derived_selection = _c2_project(
        selection,
        selected_target_ref=str(derived_target_ref),
    )
    for absent_module_attribute in (
        "_ISSUED_SELECTED_TARGET_FACTORY_TOKEN",
        "_ORDER_SELECTION_COMMAND_FACTORY_TOKEN",
        "_ISSUED_SELECTED_TARGET_REFS",
        "_build_order_selection_target_issuer",
    ):
        assert not hasattr(
            application_records_module,
            absent_module_attribute,
        )
    guessed_contexts = (
        {},
        {"issued_selected_target_factory_token": object()},
        {"issued_selected_target_factory_context": object()},
        {"order_selection_command_factory_context": object()},
    )
    for guessed_context in guessed_contexts:
        with pytest.raises(ValidationError, match="created by fresh"):
            IssuedSelectedTargetRef.model_validate(
                {"selected_target_ref": derived_target_ref},
                strict=True,
                context=guessed_context,
            )
        with pytest.raises(ValidationError, match="Application factory"):
            ApplyOrderCandidateSelectionV2Command.model_validate(
                command_values,
                strict=True,
                context=guessed_context,
            )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            application_records_module,
            "uuid4",
            lambda: derived_target_ref,
        )
        closure_issued_target = IssuedSelectedTargetRef.fresh()
    assert closure_issued_target.selected_target_ref != derived_target_ref
    closure_issued_command = build_order_candidate_selection_v2_command(
        **{
            **command_values,
            "issued_selected_target": closure_issued_target,
            "selection_record": _c2_project(
                selection,
                selected_target_ref=str(
                    closure_issued_target.selected_target_ref
                ),
            ),
        }
    )
    closure_issued_command.require_live_target_issuance()
    with pytest.raises(ValidationError, match="fresh Application issuance"):
        build_order_candidate_selection_v2_command(
            **{
                **command_values,
                "issued_selected_target": closure_issued_target,
                "selection_record": closure_issued_command.selection_record,
            }
        )

    with pytest.raises(ValidationError, match="Application factory"):
        ApplyOrderCandidateSelectionV2Command(
            **{
                **command_values,
                "issued_selected_target": (
                    IssuedSelectedTargetRef.model_construct(
                        selected_target_ref=derived_target_ref
                    )
                ),
                "selection_record": derived_selection,
            }
        )
    forged_issued_target = IssuedSelectedTargetRef.model_construct(
        selected_target_ref=derived_target_ref
    )
    with pytest.raises(ValidationError, match="fresh Application issuance"):
        build_order_candidate_selection_v2_command(
            **{
                **command_values,
                "issued_selected_target": forged_issued_target,
                "selection_record": derived_selection,
            }
        )

    with pytest.raises(ValidationError, match="created by fresh"):
        IssuedSelectedTargetRef.model_validate(
            issued_selected_target.model_dump(mode="python"),
            strict=True,
        )
    with pytest.raises(ValidationError, match="created by fresh"):
        IssuedSelectedTargetRef(
            selected_target_ref=derived_target_ref,
        )
    inert_issued_targets = (
        issued_selected_target.model_copy(),
        issued_selected_target.model_copy(deep=True),
        IssuedSelectedTargetRef.model_construct(
            selected_target_ref=selected_target_ref
        ),
        pickle.loads(pickle.dumps(issued_selected_target)),
    )
    for inert_issued_target in inert_issued_targets:
        with pytest.raises(ValidationError, match="fresh Application issuance"):
            build_order_candidate_selection_v2_command(
                **{
                    **command_values,
                    "issued_selected_target": inert_issued_target,
                }
            )
    with pytest.raises(ValidationError, match="fresh Application issuance"):
        build_order_candidate_selection_v2_command(**command_values)

    with pytest.raises(ValidationError, match="Application factory"):
        ApplyOrderCandidateSelectionV2Command.model_validate(
            command.model_dump(mode="python"),
            strict=True,
        )
    inert_commands = (
        command.model_copy(),
        command.model_copy(deep=True),
        ApplyOrderCandidateSelectionV2Command.model_construct(**command_values),
        pickle.loads(pickle.dumps(command)),
    )
    for inert_command in inert_commands:
        with pytest.raises(ValueError, match="lacks fresh Application"):
            inert_command.require_live_target_issuance()
    command.require_live_target_issuance()

    with pytest.raises(ValidationError, match="append exactly"):
        build_order_candidate_selection_v2_command(
            **{
                **command_values,
                "next_request_unit_record": _c2_project(
                    command.next_request_unit_record,
                    input_binding_refs=(query_ref,),
                ),
            }
        )
    version_five_target = UUID(int=selected_target_ref.int, version=5)
    with pytest.raises(ValidationError, match="fresh independent canonical UUID"):
        build_order_candidate_selection_v2_command(
            **{
                **command_values,
                "issued_selected_target": (
                    IssuedSelectedTargetRef.model_construct(
                        selected_target_ref=version_five_target
                    )
                ),
                "selection_record": _c2_project(
                    selection,
                    selected_target_ref=str(version_five_target),
                ),
            }
        )
    with pytest.raises(ValidationError, match="Conversation/Run closure"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "current_run_task_link_record": _c2_project(
                    closure.current_run_task_link_record,
                    task_id=uuid4(),
                ),
            }
        )

    early_message = _c2_project(
        source_message,
        received_at=candidate_set.created_at - timedelta(seconds=1),
    )
    with pytest.raises(ValidationError, match="selection Message"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "saved_selection_message_record": early_message,
            }
        )

    arbitrary_existing = _c2_project(
        selection,
        source_message_ref=uuid4(),
        ordinal_input_binding_ref=uuid4(),
    )
    with pytest.raises(ValidationError, match="existing selection record graph"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "existing_selection_records": (arbitrary_existing,),
            }
        )

    late_selection = _c2_project(
        selection,
        selected_at=closure.trusted_now + timedelta(seconds=1),
    )
    with pytest.raises(ValidationError, match="trusted transaction time"):
        build_order_candidate_selection_v2_command(
            loaded_closure=closure,
            ordinal_input_binding_record=command.ordinal_input_binding_record,
            issued_selected_target=issued_selected_target,
            next_task_record=_c2_project(
                current_task,
                status=TaskStatus.ACTIVE,
                state_version=5,
                updated_at=late_selection.selected_at,
            ),
            next_request_unit_record=_c2_project(
                current_unit,
                status=TaskStatus.ACTIVE,
                state_version=5,
                updated_at=late_selection.selected_at,
                input_binding_refs=(query_ref, ordinal_ref),
                open_questions=(),
            ),
            selection_record=late_selection,
            closed_pending_candidate_set_ref=candidate_set.candidate_set_id,
        )

    with pytest.raises(ValidationError, match="expired"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "trusted_now": observation.valid_until,
            }
        )
    with pytest.raises(ValidationError, match="Task owner"):
        OrderCandidateSelectionReadClosure(
            **{**closure_values, "owner_scope": _owner_scope("customer-B")}
        )
    with pytest.raises(ValidationError, match="pending CandidateSet ref mismatch"):
        OrderCandidateSelectionReadClosure(
            **{**closure_values, "pending_candidate_set_ref": uuid4()}
        )
    with pytest.raises(ValidationError, match="reader result mismatch"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "resolved_owner_scoped_order_target_ref": "owner-order:wrong",
            }
        )
    version_five_task = _c2_project(current_task, state_version=5)
    version_five_unit = _c2_project(current_unit, state_version=5)
    with pytest.raises(ValidationError, match="expected Task version mismatch"):
        OrderCandidateSelectionReadClosure(
            **{
                **closure_values,
                "current_task_record": version_five_task,
                "current_request_unit_record": version_five_unit,
                "current_run_task_link_record": _c2_project(
                    closure.current_run_task_link_record,
                    base_task_state_version=5,
                ),
                "current_query_binding": AcceptedOrderSearchQueryBindingReadClosure(
                    **{
                        **{
                            field_name: getattr(
                                closure.current_query_binding,
                                field_name,
                            )
                            for field_name in AcceptedOrderSearchQueryBindingReadClosure.model_fields
                        },
                        "current_task_state_version": 5,
                    }
                ),
                }
            )


def _c2_initial_tool_call_command(
    tool_name: Cycle2ToolName = Cycle2ToolName.GET_ORDER,
) -> CreateToolCallV2Command:
    owner = _owner_scope()
    task = TaskRecord.model_validate(_task(state_version=3).model_dump())
    binding = _input_binding_v2()
    unit = RequestUnitRecord.model_validate(
        _request_unit(
            task_id=task.task_id,
            state_version=3,
            input_binding_refs=(binding.binding_id,),
        ).model_dump()
    )
    run_id = uuid4()
    model_call_id = uuid4()
    context_manifest_id = uuid4()
    target_ref = uuid4() if tool_name is Cycle2ToolName.GET_SHIPMENT else None
    source_observation_ref = uuid4()
    source_observation_version = "order-observation-v1"
    if target_ref is not None:
        unit = RequestUnitRecord.model_validate(
            _c2_project(
                unit,
                observation_refs=(source_observation_ref,),
            ).model_dump()
        )
    snapshot = build_cycle2_registry_snapshot()
    manifest = ContextManifest(
        context_manifest_id=context_manifest_id,
        run_id=run_id,
        model_call_id=model_call_id,
        tool_registry_version=snapshot.tool_registry_version,
        model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
        selected_message_refs=binding.source_refs,
        task_state_ref_and_version=None,
        observation_refs_and_versions=(
            (
                VersionedRecordRef(
                    record_ref=source_observation_ref,
                    version=source_observation_version,
                ),
            )
            if target_ref is not None
            else ()
        ),
        evidence_refs_and_versions=(),
        action_record_refs=(),
        redaction_policy_version="redaction-v1",
        truncation_decisions=(),
        token_counts=TokenCounts(input_tokens=None, output_tokens=None),
        assembled_at=UTC_NOW,
    )
    candidate = Cycle2GatewayCandidate(
        run_id=run_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        requested_provider_tool_name=tool_name.value,
        candidate_arguments={"order_id": "O-1001"},
        proposed_base_task_state_version=None,
        validated_task_state_version=task.state_version,
        argument_binding_refs=(binding.binding_id,),
        verified_target_ref=target_ref,
    )
    loaded = Cycle2GatewayLoadedClosure(
        customer_context=CustomerContext.model_validate(
            _customer_context().model_dump()
        ),
        private_owner_scope_ref=owner.customer_id,
        current_task=task,
        current_request_unit=unit,
        current_input_bindings=(
            Cycle2AcceptedBindingFacts(
                binding_id=binding.binding_id,
                private_owner_scope_ref=owner.customer_id,
                owner_customer_id=owner.customer_id,
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                task_state_version=task.state_version,
                name="order_id",
                normalized_value="O-1001",
                authority=InputAuthority.USER_CLAIM,
                validation_status="ACCEPTED",
                confirmed_by_user=True,
                source_refs=binding.source_refs,
                superseded_by=None,
            ),
        ),
        current_verified_order_targets=(
            (
                Cycle2VerifiedOrderTargetFacts(
                    verified_target_ref=target_ref,
                    private_owner_scope_ref=owner.customer_id,
                    owner_customer_id=owner.customer_id,
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                    task_state_version=task.state_version,
                    order_id="O-1001",
                    source_observation_ref=source_observation_ref,
                    source_observation_version=source_observation_version,
                    input_binding_refs=(binding.binding_id,),
                    superseded_by=None,
                ),
            )
            if target_ref is not None
            else ()
        ),
        current_target_observations=(
            (
                Cycle2TargetObservationFacts(
                    observation_ref=source_observation_ref,
                    observation_version=source_observation_version,
                    private_owner_scope_ref=owner.customer_id,
                    owner_customer_id=owner.customer_id,
                    task_id=task.task_id,
                    request_unit_id=unit.request_unit_id,
                    task_state_version=task.state_version,
                    verified_target_ref=target_ref,
                    input_binding_refs=(binding.binding_id,),
                    superseded_by=None,
                ),
            )
            if target_ref is not None
            else ()
        ),
        registry_snapshot=snapshot,
        context_manifest=manifest,
        budget=Cycle2GatewayBudgetFacts(
            run_id=run_id,
            context_manifest_id=context_manifest_id,
            tool_registry_version=snapshot.tool_registry_version,
            model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
            closure_complete=True,
            tool_calls_used=0,
            max_tool_calls=3,
            active_tool_calls=0,
            accepted_parallel_tool_calls=0,
            remaining_run_time_budget_ms=1500,
        ),
        progress_snapshot=Cycle2GatewayProgressSnapshot(
            run_id=run_id,
            context_manifest_id=context_manifest_id,
            tool_registry_version=snapshot.tool_registry_version,
            model_visible_toolset_hash=snapshot.model_visible_toolset_hash,
            task_state_version=task.state_version,
            history_complete=True,
            prior_tool_steps=(),
        ),
    )
    trusted_read_at = UTC_NOW + timedelta(seconds=1)
    gate = evaluate_cycle2_control_gateway(
        candidate=candidate,
        loaded_closure=loaded,
        gate_decision_id=uuid4(),
        provider_tool_call_id="provider-cycle2-call",
        decided_at=trusted_read_at,
    )
    authorized = build_cycle2_authorized_tool_command(
        gate_decision=gate,
        candidate=candidate,
        registry_snapshot_ref=snapshot.tool_registry_version,
        trusted_context_ref="cycle2-context-ref",
    )
    closure = InitialToolCallV2ReadClosure(
        owner_scope=owner,
        current_task_record=task,
        current_request_unit_record=unit,
        current_input_binding_records=(binding,),
        trusted_read_at=trusted_read_at,
    )
    created = _c2_tool_call(
        name=tool_name,
        owner=owner.customer_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        validated_task_state_version=task.state_version,
        argument_binding_refs=(binding.binding_id,),
        verified_target_ref=target_ref,
        run_id=run_id,
        model_call_id=model_call_id,
        context_manifest_id=context_manifest_id,
        gate_decision_id=gate.gate_decision_id,
        provider_tool_call_id=gate.provider_tool_call_id,
        started_at=trusted_read_at,
    )
    return CreateToolCallV2Command(
        loaded_closure=closure,
        gateway_candidate=candidate,
        gate_decision=gate,
        authorized_tool_command=authorized,
        created_record=created,
    )


def test_cycle2_initial_tool_call_requires_live_gateway_authorization_graph() -> None:
    command = _c2_initial_tool_call_command()
    assert command.gate_decision.decision is GateDecisionValue.ACCEPT
    assert isinstance(command.authorized_tool_command, AuthorizedToolCommandV2)
    assert command.gate_decision.decided_at <= command.created_record.started_at
    assert command.created_record.started_at == command.loaded_closure.trusted_read_at

    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    for inert_gate in (
        GateDecisionV2.model_validate(command.gate_decision.model_dump(), strict=True),
        command.gate_decision.model_copy(),
    ):
        with pytest.raises(ValidationError, match="live public Gateway authorization"):
            CreateToolCallV2Command(**{**values, "gate_decision": inert_gate})
    with pytest.raises(ValidationError, match="authorization graph"):
        CreateToolCallV2Command(
            **{
                **values,
                "created_record": _c2_project(
                    command.created_record,
                    argument_binding_refs=(uuid4(),),
                ),
            }
        )
    with pytest.raises(ValidationError, match="clean CREATED"):
        CreateToolCallV2Command(
            **{
                **values,
                "created_record": _c2_project(
                    command.created_record,
                    started_at=command.created_record.started_at
                    + timedelta(seconds=1),
                ),
            }
        )


def test_cycle2_initial_tool_call_closes_selected_target_and_exact_registry() -> None:
    command = _c2_initial_tool_call_command(Cycle2ToolName.GET_SHIPMENT)
    target = command.gate_decision.verified_target_ref
    assert target is not None
    assert command.gateway_candidate.verified_target_ref == target
    assert command.authorized_tool_command.verified_target_ref == target
    assert command.created_record.verified_target_ref == target
    assert command.authorized_tool_command.registry_snapshot_ref == (
        command.created_record.tool_registry_version
    )

    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    for replacement in (None, uuid4()):
        with pytest.raises(ValidationError, match="authorization graph"):
            CreateToolCallV2Command(
                **{
                    **values,
                    "created_record": _c2_project(
                        command.created_record,
                        verified_target_ref=replacement,
                    ),
                }
            )
    with pytest.raises(ValidationError, match="stale or belongs"):
        CreateToolCallV2Command(
            **{
                **values,
                "authorized_tool_command": _c2_project(
                    command.authorized_tool_command,
                    registry_snapshot_ref="wrong-registry",
                ),
            }
        )
    raw_created = command.created_record.model_copy(update={"attempt_count": True})
    with pytest.raises(ValidationError, match="recursively canonical"):
        CreateToolCallV2Command(**{**values, "created_record": raw_created})


def test_cycle2_tool_attempt_fences_preserve_append_only_evidence() -> None:
    owner = _owner_scope()
    created = _c2_tool_call(name=Cycle2ToolName.GET_SHIPMENT)
    first = _c2_attempt(tool_call_id=created.tool_call_id)
    running = _c2_project(
        created,
        status=ToolCallStatus.RUNNING,
        attempts=(first,),
        attempt_count=1,
    )
    append = AppendToolAttemptV2Command(
        owner_scope=owner,
        expected_record=created,
        next_running_record=running,
        started_attempt=first,
    )
    assert append.started_attempt.finished_at is None

    finalized = _c2_attempt(
        tool_call_id=created.tool_call_id,
        finished_at=UTC_NOW + timedelta(milliseconds=500),
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="SHIPMENT_SERVICE_TRANSIENT",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    retry_scheduled = _c2_project(running, attempts=(finalized,))
    finalize = FinalizeToolAttemptV2Command(
        owner_scope=owner,
        expected_running_record=running,
        finalized_attempt=finalized,
        next_record=retry_scheduled,
    )
    assert finalize.next_record.status is ToolCallStatus.RUNNING

    second = _c2_attempt(tool_call_id=created.tool_call_id, attempt_no=2)
    second_running = _c2_project(
        retry_scheduled,
        attempts=(finalized, second),
        attempt_count=2,
    )
    AppendToolAttemptV2Command(
        owner_scope=owner,
        expected_record=retry_scheduled,
        next_running_record=second_running,
        started_attempt=second,
    )
    with pytest.raises(ValidationError):
        AppendToolAttemptV2Command(
            owner_scope=owner,
            expected_record=second_running,
            next_running_record=second_running,
            started_attempt=second,
        )
    with pytest.raises(ValidationError, match="owner scope mismatch"):
        AppendToolAttemptV2Command(
            owner_scope=_owner_scope("customer-B"),
            expected_record=created,
            next_running_record=running,
            started_attempt=first,
        )


def _c2_shipment_inputs() -> tuple[
    TrustedOwnerScope,
    TaskRecord,
    RequestUnitRecord,
    ToolCallRecordV2,
    GetShipmentResult,
    ShipmentObservation,
]:
    owner = _owner_scope()
    task = _task(state_version=3)
    unit = _request_unit(task_id=task.task_id, state_version=3)
    target_ref = uuid4()
    source = _c2_tool_call(
        name=Cycle2ToolName.GET_SHIPMENT,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        validated_task_state_version=task.state_version,
        verified_target_ref=target_ref,
    )
    successful_attempt = _c2_attempt(
        tool_call_id=source.tool_call_id,
        finished_at=UTC_NOW + timedelta(seconds=1),
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    source = _c2_project(
        source,
        attempts=(successful_attempt,),
        attempt_count=1,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=successful_attempt.finished_at,
        result_ref=uuid4(),
    )
    observation = ShipmentObservation(
        observation_id=uuid4(),
        private_owner_scope=owner.customer_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        verified_order_target_ref=str(target_ref),
        source_tool="get_shipment",
        source_tool_call_id=source.tool_call_id,
        source_resource_ref="shipment:1",
        source_version=C2_SHIPMENT_VERSION,
        normalized_type="SHIPMENT_SUMMARY",
        normalized_value=ShipmentSummaryProjection(
            shipment_status=ShipmentStatus.IN_TRANSIT,
            latest_event_code=ShipmentEventCode.IN_TRANSIT,
            latest_event_at=UTC_NOW - timedelta(hours=1),
            promised_delivery_at=UTC_NOW + timedelta(minutes=1),
        ),
        observed_at=UTC_NOW,
        recorded_at=UTC_NOW + timedelta(seconds=1),
        valid_until=UTC_NOW + timedelta(minutes=5),
    )
    result = GetShipmentResult(
        outcome=GetShipmentOutcome.FOUND,
        shipment_summary=observation.normalized_value,
        source_resource_ref=observation.source_resource_ref,
        source_version=observation.source_version,
        observed_at=observation.observed_at,
    )
    return owner, task, unit, source, result, observation


def test_cycle2_order_observation_advances_task_graph_exactly_once() -> None:
    owner = _owner_scope()
    task = _task(state_version=3)
    unit = _request_unit(task_id=task.task_id, state_version=3)
    observation = _observation(
        recorded_at=UTC_NOW + timedelta(seconds=1),
        observed_at=UTC_NOW + timedelta(seconds=1),
        source_version=(
            "mock-order-source-version.p0.v1:sha256:" + "d" * 64
        ),
    )
    source = _c2_tool_call(
        name=Cycle2ToolName.GET_ORDER,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        validated_task_state_version=task.state_version,
    )
    successful_attempt = _c2_attempt(
        tool_call_id=source.tool_call_id,
        finished_at=observation.observed_at,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    source = _c2_project(
        source,
        attempts=(successful_attempt,),
        attempt_count=1,
        status=ToolCallStatus.SUCCEEDED,
        finished_at=observation.observed_at,
        result_ref=uuid4(),
    )
    result = GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=observation.normalized_value,
        source_version=observation.source_version,
    )
    next_task = _c2_project(
        task,
        state_version=task.state_version + 1,
        updated_at=observation.recorded_at,
    )
    next_unit = _c2_project(
        unit,
        state_version=unit.state_version + 1,
        updated_at=observation.recorded_at,
        observation_refs=(*unit.observation_refs, observation.observation_id),
    )

    command = SaveOrderObservationV2Command(
        owner_scope=owner,
        expected_task_record=task,
        next_task_record=next_task,
        expected_request_unit_record=unit,
        next_request_unit_record=next_unit,
        source_tool_call_record=source,
        source_result_ref=source.result_ref,
        source_result=result,
        observation_record=observation,
        trusted_acceptance_now=observation.recorded_at,
    )

    assert command.next_task_record.state_version == 4
    assert command.next_request_unit_record.observation_refs[-1] == (
        observation.observation_id
    )
    command_values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    with pytest.raises(ValidationError, match="Task effect"):
        SaveOrderObservationV2Command(
            **{
                **command_values,
                "next_request_unit_record": _c2_project(
                    next_unit,
                    observation_refs=unit.observation_refs,
                ),
            }
        )


def test_cycle2_shipment_observation_precedes_exact_deterministic_assessment() -> None:
    owner, task, unit, source, result, observation = _c2_shipment_inputs()
    expected_task = task
    expected_unit = unit
    task = _c2_project(
        expected_task,
        state_version=expected_task.state_version + 1,
        updated_at=observation.recorded_at,
    )
    unit = _c2_project(
        expected_unit,
        state_version=expected_unit.state_version + 1,
        updated_at=observation.recorded_at,
        observation_refs=(observation.observation_id,),
    )
    SaveShipmentObservationV2Command(
        owner_scope=owner,
        expected_task_record=expected_task,
        next_task_record=task,
        expected_request_unit_record=expected_unit,
        next_request_unit_record=unit,
        source_tool_call_record=source,
        source_result_ref=source.result_ref,
        source_result=result,
        observation_record=observation,
        trusted_acceptance_now=observation.recorded_at,
    )
    assessed_at = UTC_NOW + timedelta(minutes=2)
    conversation = _conversation(owner_customer_id=owner.customer_id)
    closure = ShipmentAssessmentReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        current_task_record=task,
        current_request_unit_record=unit,
        current_observation_record=observation,
        current_observation_ref=observation.observation_id,
        verified_order_target_ref=observation.verified_order_target_ref,
        trusted_assessed_at=assessed_at,
        current_input_binding_records=(
            _input_binding(binding_id=unit.input_binding_refs[0]),
        ),
    )
    assessment = assess_shipment(
        assessment_id=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        task_state_version=task.state_version,
        verified_order_target_ref=observation.verified_order_target_ref,
        shipment_observation_ref=observation.observation_id,
        shipment_observation_source_version=observation.source_version,
        shipment_summary=observation.normalized_value,
        observation_observed_at=observation.observed_at,
        observation_valid_until=observation.valid_until,
        assessed_at=assessed_at,
    )
    SaveShipmentAssessmentV2Command(
        loaded_closure=closure,
        assessment_record=assessment,
    )
    closure.require_same_persisted_graph(closure)
    authoritative_with_assessment = ShipmentAssessmentReadClosure(
        **{
            **{
                field_name: getattr(closure, field_name)
                for field_name in ShipmentAssessmentReadClosure.model_fields
            },
            "current_assessment_records": (assessment,),
        }
    )
    with pytest.raises(ValueError, match="persisted read fence mismatch"):
        closure.require_same_persisted_graph(authoritative_with_assessment)

    omitted_newer_ref = uuid4()
    newer_observation = _c2_project(
        observation,
        observation_id=omitted_newer_ref,
        source_version="mock-shipment-source-version.p0.v1:sha256:" + "c" * 64,
        observed_at=observation.observed_at + timedelta(seconds=1),
        recorded_at=observation.recorded_at + timedelta(seconds=1),
        valid_until=observation.valid_until + timedelta(seconds=1),
        supersedes=observation.observation_id,
    )
    unit_with_newer = _c2_project(
        unit,
        observation_refs=(observation.observation_id, omitted_newer_ref),
    )
    authoritative_with_newer = ShipmentAssessmentReadClosure(
        **{
            **{
                field_name: getattr(closure, field_name)
                for field_name in ShipmentAssessmentReadClosure.model_fields
            },
            "current_request_unit_record": unit_with_newer,
            "current_observation_record": newer_observation,
            "current_observation_ref": newer_observation.observation_id,
            "superseded_observation_records": (observation,),
        }
    )
    with pytest.raises(ValueError, match="persisted read fence mismatch"):
        closure.require_same_persisted_graph(authoritative_with_newer)
    wrong = ShipmentAssessment(
        **{
            **assessment.model_dump(mode="python"),
            "primary_result": "NORMAL",
            "reason_codes": ("NO_P0_SHIPMENT_EXCEPTION",),
        }
    )
    with pytest.raises(ValidationError, match="deterministic derivation"):
        SaveShipmentAssessmentV2Command(
            loaded_closure=closure,
            assessment_record=wrong,
        )
    with pytest.raises(ValidationError, match="Task owner"):
        SaveShipmentObservationV2Command(
            owner_scope=_owner_scope("customer-B"),
            expected_task_record=expected_task,
            next_task_record=task,
            expected_request_unit_record=expected_unit,
            next_request_unit_record=unit,
            source_tool_call_record=source,
            source_result_ref=source.result_ref,
            source_result=result,
            observation_record=observation,
            trusted_acceptance_now=observation.recorded_at,
        )
    with pytest.raises(ValidationError, match="source graph mismatch"):
        SaveShipmentObservationV2Command(
            owner_scope=owner,
            expected_task_record=expected_task,
            next_task_record=task,
            expected_request_unit_record=expected_unit,
            next_request_unit_record=unit,
            source_tool_call_record=source,
            source_result_ref=source.result_ref,
            source_result=result,
            observation_record=_c2_project(
                observation,
                source_tool_call_id=uuid4(),
            ),
            trusted_acceptance_now=observation.recorded_at,
        )
    late_finished_at = observation.recorded_at + timedelta(seconds=1)
    late_attempt = _c2_project(
        source.attempts[-1],
        finished_at=late_finished_at,
    )
    with pytest.raises(ValidationError, match="source graph mismatch"):
        SaveShipmentObservationV2Command(
            owner_scope=owner,
            expected_task_record=expected_task,
            next_task_record=task,
            expected_request_unit_record=expected_unit,
            next_request_unit_record=unit,
            source_tool_call_record=_c2_project(
                source,
                attempts=(late_attempt,),
                finished_at=late_finished_at,
            ),
            source_result_ref=source.result_ref,
            source_result=result,
            observation_record=observation,
            trusted_acceptance_now=observation.recorded_at,
        )
    with pytest.raises(ValidationError, match="fresh at acceptance"):
        SaveShipmentObservationV2Command(
            owner_scope=owner,
            expected_task_record=expected_task,
            next_task_record=task,
            expected_request_unit_record=expected_unit,
            next_request_unit_record=unit,
            source_tool_call_record=source,
            source_result_ref=source.result_ref,
            source_result=result,
            observation_record=observation,
            trusted_acceptance_now=observation.valid_until,
        )
    with pytest.raises(ValidationError, match="Claim binding"):
        ShipmentAssessmentReadClosure(
            owner_scope=owner,
            trusted_conversation_record=conversation,
            current_task_record=task,
            current_request_unit_record=unit,
            current_observation_record=observation,
            current_observation_ref=observation.observation_id,
            verified_order_target_ref=observation.verified_order_target_ref,
            trusted_assessed_at=assessed_at,
            current_input_binding_records=(),
            current_claim_bindings=(ShipmentNotReceivedClaimReadClosure(
                binding_ref=unit.input_binding_refs[0],
                private_owner_scope_ref=owner.customer_id,
                conversation_id=conversation.conversation_id,
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                task_state_version=task.state_version,
                verified_order_target_ref="owner-order:wrong",
                source_message_record=_message(
                    conversation_id=conversation.conversation_id,
                    content="我没有收到",
                ),
                accepted_at=UTC_NOW,
            ),),
        )


def test_cycle2_oa10_is_exact_no_result_closure() -> None:
    owner = _owner_scope()
    active = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=uuid4(),
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW,
    )
    link = RunTaskLinkRecordV2(
        run_id=active.run_id,
        task_id=uuid4(),
        base_task_state_version=3,
        result_task_state_version=None,
    )
    current_run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=active.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW + timedelta(seconds=1),
    )
    current_task = _task(
        task_id=link.task_id,
        state_version=4,
        updated_at=UTC_NOW + timedelta(seconds=1),
    )
    current_unit = _request_unit(
        task_id=link.task_id,
        state_version=4,
        updated_at=UTC_NOW + timedelta(seconds=1),
    )
    obsolete_task = _c2_project(
        current_task,
        state_version=3,
        updated_at=UTC_NOW,
    )
    obsolete_unit = _c2_project(
        current_unit,
        state_version=3,
        updated_at=UTC_NOW,
    )
    conversation = _conversation(
        conversation_id=active.conversation_id,
        owner_customer_id=owner.customer_id,
    )
    closure = SupersededRunReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        expected_active_run_record=active,
        expected_active_link_record=link,
        current_authoritative_run_record=current_run,
        current_authoritative_link_record=RunTaskLinkRecordV2(
            run_id=current_run.run_id,
            task_id=link.task_id,
            base_task_state_version=4,
            result_task_state_version=None,
        ),
        current_task_record=current_task,
        current_request_unit_record=current_unit,
        obsolete_task_record=obsolete_task,
        obsolete_request_unit_record=obsolete_unit,
        trusted_current_evidence_at=UTC_NOW + timedelta(seconds=1),
        invalidation_kind=(
            SupersededRunInvalidationKind.TASK_VERSION_ADVANCED
        ),
    )
    completed_at = UTC_NOW + timedelta(seconds=2)
    terminal = AgentRunRecordV2(
        **{
            **active.model_dump(mode="python"),
            "status": AgentRunStatusV2.SUPERSEDED,
            "completed_at": completed_at,
            "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
        }
    )
    trace = TraceEventV2(
        trace_event_id=uuid4(),
        event_type=TraceEventType.RUN_STOPPED,
        occurred_at=completed_at,
        run_id=active.run_id,
        task_id=link.task_id,
        request_unit_id=closure.current_request_unit_record.request_unit_id,
        user_outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
    )
    command = FinalizeSupersededRunV2Command(
        loaded_closure=closure,
        superseded_run_record=terminal,
        no_result_link_record=link,
        run_stopped_trace_record=trace,
    )
    assert command.no_result_link_record.result_task_state_version is None
    assert {
        "task_record",
        "request_unit_record",
        "agent_run_result",
        "message_record",
        "response_rendered",
    }.isdisjoint(FinalizeSupersededRunV2Command.model_fields)
    actual_evidence = _cycle2_oa10_exact_run_evidence()
    actual_values = {
        field_name: getattr(actual_evidence, field_name)
        for field_name in Cycle2ExactRunEvidenceClosure.model_fields
    }
    with pytest.raises(
        ValidationError,
        match="SupersededRunFinalizationEvidenceV2",
    ):
        Cycle2ExactRunEvidenceClosure(
            **{**actual_values, "superseded_run_finalizations": (command,)}
        )

    with pytest.raises(ValidationError, match="outbound or mutation refs"):
        FinalizeSupersededRunV2Command(
            loaded_closure=closure,
            superseded_run_record=terminal,
            no_result_link_record=link,
            run_stopped_trace_record=_c2_project(trace, message_ref=uuid4()),
        )

    closure_values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }
    same_version_task = _c2_project(
        closure.current_task_record,
        state_version=3,
    )
    same_version_unit = _c2_project(
        closure.current_request_unit_record,
        state_version=3,
    )
    with pytest.raises(ValidationError, match="obsolete Task snapshot/version graph"):
        SupersededRunReadClosure(
            **{
                **closure_values,
                "current_task_record": same_version_task,
                "current_request_unit_record": same_version_unit,
                "current_authoritative_link_record": _c2_project(
                    closure.current_authoritative_link_record,
                    base_task_state_version=3,
                ),
            }
        )
    with pytest.raises(ValidationError, match="Task owner"):
        SupersededRunReadClosure(
            **{
                **closure_values,
                "current_task_record": _c2_project(
                    closure.current_task_record,
                    owner_customer_id="customer-B",
                ),
            }
        )
    with pytest.raises(ValidationError, match="share Conversation"):
        SupersededRunReadClosure(
            **{
                **closure_values,
                "current_authoritative_run_record": _c2_project(
                    closure.current_authoritative_run_record,
                    conversation_id=uuid4(),
                ),
            }
        )
    with pytest.raises(ValidationError, match="authoritative RunTaskLink"):
        SupersededRunReadClosure(
            **{
                **closure_values,
                "current_authoritative_link_record": _c2_project(
                    closure.current_authoritative_link_record,
                    task_id=uuid4(),
                ),
            }
        )

    invalidated_ref = uuid4()
    binding_closure = SupersededRunReadClosure(
        **{
            **closure_values,
            "invalidation_kind": (
                SupersededRunInvalidationKind.BINDING_INVALIDATED
            ),
            "obsolete_binding_refs": (invalidated_ref,),
            "invalidated_binding_refs": (invalidated_ref,),
            "obsolete_request_unit_record": _c2_project(
                obsolete_unit,
                input_binding_refs=(
                    *current_unit.input_binding_refs,
                    invalidated_ref,
                ),
            ),
        }
    )
    assert binding_closure.invalidated_binding_refs == (invalidated_ref,)
    arbitrary_ref = uuid4()
    with pytest.raises(ValidationError, match="exact binding refs"):
        SupersededRunReadClosure(
            **{
                **closure_values,
                "invalidation_kind": (
                    SupersededRunInvalidationKind.BINDING_INVALIDATED
                ),
                "obsolete_binding_refs": (arbitrary_ref,),
                "invalidated_binding_refs": (arbitrary_ref,),
            }
        )
    with pytest.raises(ValidationError, match="exact binding refs"):
        SupersededRunReadClosure(
            **{
                **closure_values,
                "invalidation_kind": (
                    SupersededRunInvalidationKind.BINDING_INVALIDATED
                ),
                "obsolete_binding_refs": (
                    closure.current_request_unit_record.input_binding_refs[0],
                ),
                "invalidated_binding_refs": (
                    closure.current_request_unit_record.input_binding_refs[0],
                ),
            }
        )

    initial_link = _c2_project(link, base_task_state_version=None)
    initial_closure = SupersededRunReadClosure(
        **{
            **closure_values,
            "expected_active_link_record": initial_link,
            "obsolete_task_record": None,
            "obsolete_request_unit_record": None,
        }
    )
    FinalizeSupersededRunV2Command(
        loaded_closure=initial_closure,
        superseded_run_record=terminal,
        no_result_link_record=initial_link,
        run_stopped_trace_record=trace,
    )


def _c2_retry_recovery_closure(
    *,
    created: bool = False,
    unfinished: bool = False,
    timeout: bool = False,
    budget_ms: int = 10_000,
    current_state_version: int = 3,
) -> ToolRetryRecoveryReadClosureV2:
    owner = _owner_scope()
    binding = _input_binding_v2()
    task = _task(
        state_version=current_state_version,
        updated_at=UTC_NOW + timedelta(seconds=current_state_version - 3),
    )
    unit = _request_unit(
        task_id=task.task_id,
        state_version=current_state_version,
        input_binding_refs=(binding.binding_id,),
        updated_at=task.updated_at,
    )
    run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=uuid4(),
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW,
    )
    tool_call_id = uuid4()
    attempts = ()
    if not created:
        attempts = (
            ToolAttemptRecordV2(
                tool_call_id=tool_call_id,
                attempt_no=1,
                started_at=UTC_NOW,
                **(
                    {}
                    if unfinished
                    else {
                        "finished_at": UTC_NOW + timedelta(milliseconds=1),
                        "outcome": (
                            ToolResultOutcome.TIMEOUT
                            if timeout
                            else ToolResultOutcome.SYSTEM_FAILURE
                        ),
                        "failure_code": (
                            "TOOL_CALL_TIMEOUT"
                            if timeout
                            else "ORDER_SEARCH_TRANSIENT"
                        ),
                        "timeout_phase": (
                            ToolTimeoutPhase.AFTER_DISPATCH if timeout else None
                        ),
                        "retry_decision": ToolRetryDecision.RETRY_SCHEDULED,
                    }
                ),
            ),
        )
    tool_call = ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=run.run_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref=owner.customer_id,
        validated_task_state_version=3,
        argument_binding_refs=(binding.binding_id,),
        effect=ToolEffect.READ,
        attempt_count=len(attempts),
        attempts=attempts,
        status=(ToolCallStatus.CREATED if created else ToolCallStatus.RUNNING),
        started_at=UTC_NOW,
    )
    trusted_read_at = UTC_NOW + timedelta(seconds=current_state_version - 2)
    return ToolRetryRecoveryReadClosureV2(
        owner_scope=owner,
        active_run_record=run,
        active_run_task_link_record=RunTaskLinkRecordV2(
            run_id=run.run_id,
            task_id=task.task_id,
            base_task_state_version=3,
        ),
        current_task_record=task,
        current_request_unit_record=unit,
        current_input_binding_records=(binding,),
        tool_call_record=tool_call,
        recovery_decision_records=(),
        trusted_read_at=trusted_read_at,
        run_budget_policy=Cycle2RunBudgetPolicyEvidence(
            policy_version="cycle2-test-budget.v1",
            run_time_budget_ms=budget_ms,
        ),
    )


def _c2_recovery_decision_record(
    closure: ToolRetryRecoveryReadClosureV2,
) -> ToolRetryRecoveryDecisionRecordV2:
    decision = closure.derive_recovery_decision()
    return ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=uuid4(),
        tool_call_id=decision.tool_call_id,
        last_attempt_no=decision.last_attempt_no,
        decision=decision.decision,
        stable_reason_code=decision.stable_reason_code,
        candidate_next_attempt_no=decision.candidate_next_attempt_no,
        decided_at=decision.decided_at,
    )


def _c2_initial_append_command(
    closure: ToolRetryRecoveryReadClosureV2,
    *,
    started_at: datetime | None = None,
) -> AppendToolAttemptV2Command:
    attempt = ToolAttemptRecordV2(
        tool_call_id=closure.tool_call_record.tool_call_id,
        attempt_no=1,
        started_at=started_at or closure.trusted_read_at,
    )
    running = _c2_project(
        closure.tool_call_record,
        status=ToolCallStatus.RUNNING,
        attempts=(attempt,),
        attempt_count=1,
    )
    return AppendToolAttemptV2Command(
        owner_scope=closure.owner_scope,
        expected_record=closure.tool_call_record,
        next_running_record=running,
        started_attempt=attempt,
    )


def test_cycle2_read_dispatch_grant_has_exact_closed_matrix() -> None:
    tool_call_id = uuid4()
    applied = Cycle2ReadDispatchGrant(
        write_result=Cycle2DispatchFenceWriteResult.APPLIED,
        tool_call_id=tool_call_id,
        attempt_no=1,
        trusted_fenced_at=UTC_NOW,
        effective_timeout_ms=500,
    )
    assert applied.tool_call_id == tool_call_id
    assert applied.attempt_no == 1
    assert applied.effective_timeout_ms == 500
    assert applied.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    assert set(type(applied).model_fields) == {
        "write_result",
        "tool_call_id",
        "attempt_no",
        "trusted_fenced_at",
        "effective_timeout_ms",
    }
    assert "schema_version" not in type(applied).model_fields
    assert {
        "customer_id",
        "payload",
        "result_ref",
        "action_id",
        "idempotency_key",
    }.isdisjoint(type(applied).model_fields)
    persistence_source = Path(
        application_records_module.__file__
    ).with_name("persistence.py").read_text(encoding="utf-8")
    assert "Cycle2ReadDispatchGrant" not in persistence_source

    for write_result in Cycle2DispatchFenceWriteResult:
        if write_result is Cycle2DispatchFenceWriteResult.APPLIED:
            continue
        grant = Cycle2ReadDispatchGrant(write_result=write_result)
        assert grant.tool_call_id is None
        assert grant.attempt_no is None
        assert grant.trusted_fenced_at is None
        assert grant.effective_timeout_ms is None


def test_cycle2_read_dispatch_grant_rejects_partial_or_dirty_matrix() -> None:
    complete = {
        "tool_call_id": uuid4(),
        "attempt_no": 2,
        "trusted_fenced_at": UTC_NOW,
        "effective_timeout_ms": 1,
    }
    for missing_field in complete:
        with pytest.raises(ValidationError, match="every grant field"):
            Cycle2ReadDispatchGrant(
                write_result=Cycle2DispatchFenceWriteResult.APPLIED,
                **{
                    field_name: value
                    for field_name, value in complete.items()
                    if field_name != missing_field
                },
            )
    for write_result in (
        Cycle2DispatchFenceWriteResult.ALREADY_APPLIED,
        Cycle2DispatchFenceWriteResult.PROJECTION_CONFLICT,
        Cycle2DispatchFenceWriteResult.NOT_APPLICABLE,
    ):
        with pytest.raises(ValidationError, match="null grant fields"):
            Cycle2ReadDispatchGrant(
                write_result=write_result,
                **complete,
            )


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error"),
    [
        ("attempt_no", True, "valid integer"),
        ("attempt_no", 0, "greater than or equal to 1"),
        ("attempt_no", 3, "less than or equal to 2"),
        ("effective_timeout_ms", True, "valid integer"),
        ("effective_timeout_ms", 0, "greater than or equal to 1"),
        ("effective_timeout_ms", 501, "less than or equal to 500"),
        ("trusted_fenced_at", NON_UTC_NOW, "must use UTC"),
    ],
)
def test_cycle2_read_dispatch_grant_rejects_ambiguous_or_untrusted_fields(
    field_name: str,
    invalid_value: object,
    error: str,
) -> None:
    values = {
        "write_result": Cycle2DispatchFenceWriteResult.APPLIED,
        "tool_call_id": uuid4(),
        "attempt_no": 1,
        "trusted_fenced_at": UTC_NOW,
        "effective_timeout_ms": 500,
    }
    values[field_name] = invalid_value
    with pytest.raises(ValidationError, match=error):
        Cycle2ReadDispatchGrant(**values)


def test_cycle2_read_dispatch_grant_requires_exact_enum_and_uuid_identity() -> None:
    values = {
        "write_result": Cycle2DispatchFenceWriteResult.APPLIED,
        "tool_call_id": uuid4(),
        "attempt_no": 1,
        "trusted_fenced_at": UTC_NOW,
        "effective_timeout_ms": 500,
    }
    with pytest.raises(ValidationError):
        Cycle2ReadDispatchGrant(
            **{
                **values,
                "write_result": "APPLIED",
            }
        )
    with pytest.raises(ValidationError):
        Cycle2ReadDispatchGrant(
            **{
                **values,
                "tool_call_id": str(uuid4()),
            }
        )


def test_cycle2_initial_append_binds_created_closure_and_attempt_one() -> None:
    closure = _c2_retry_recovery_closure(created=True)
    append = _c2_initial_append_command(closure)
    command = AppendInitialToolAttemptV2Command(
        loaded_closure=closure,
        attempt_append_command=append,
    )
    assert set(type(command).model_fields) == {
        "loaded_closure",
        "attempt_append_command",
    }
    assert command.attempt_append_command.expected_record == (
        closure.tool_call_record
    )
    assert command.attempt_append_command.started_attempt.attempt_no == 1
    assert "recovery_decision_record" not in type(command).model_fields

    other = _c2_retry_recovery_closure(created=True)
    with pytest.raises(ValidationError, match="trusted closure"):
        AppendInitialToolAttemptV2Command(
            loaded_closure=other,
            attempt_append_command=append,
        )
    early_append = _c2_initial_append_command(
        closure,
        started_at=closure.tool_call_record.started_at,
    )
    with pytest.raises(ValidationError, match="trusted closure"):
        AppendInitialToolAttemptV2Command(
            loaded_closure=closure,
            attempt_append_command=early_append,
        )


def test_cycle2_initial_wrapper_rejects_recovery_attempt_two() -> None:
    closure = _c2_retry_recovery_closure()
    second = ToolAttemptRecordV2(
        tool_call_id=closure.tool_call_record.tool_call_id,
        attempt_no=2,
        started_at=closure.trusted_read_at,
    )
    running = _c2_project(
        closure.tool_call_record,
        attempts=(*closure.tool_call_record.attempts, second),
        attempt_count=2,
    )
    append = AppendToolAttemptV2Command(
        owner_scope=closure.owner_scope,
        expected_record=closure.tool_call_record,
        next_running_record=running,
        started_attempt=second,
    )
    with pytest.raises(ValidationError, match="CREATED attempt-0"):
        AppendInitialToolAttemptV2Command(
            loaded_closure=closure,
            attempt_append_command=append,
        )


def test_cycle2_created_recovery_is_parent_only_zero_attempt_terminal() -> None:
    closure = _c2_retry_recovery_closure(created=True)
    decision = closure.derive_recovery_decision()
    assert decision.decision is ToolRecoveryDecision.INTERRUPT_WITHOUT_ATTEMPT
    terminal = _c2_project(
        closure.tool_call_record,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=closure.trusted_read_at,
        interruption_reason="PROCESS_RESTART_DETECTED",
    )
    command = FinalizeCreatedToolRecoveryV2Command(
        loaded_closure=closure,
        terminal_tool_call_record=terminal,
    )
    assert set(type(command).model_fields) == {
        "loaded_closure",
        "terminal_tool_call_record",
    }
    assert command.terminal_tool_call_record.attempt_count == 0
    assert command.terminal_tool_call_record.attempts == ()
    assert command.terminal_tool_call_record.result_ref is None
    assert command.terminal_tool_call_record.recovery_disposition is None
    assert command.terminal_tool_call_record.recovery_decision_ref is None
    assert "recovery_decision_record" not in type(command).model_fields
    assert "finalize_tool_call_command" not in type(command).model_fields

    with pytest.raises(ValidationError, match="pre-dispatch interruption"):
        ToolCallRecordV2(
            **{
                **terminal.model_dump(mode="python"),
                "recovery_decision_ref": uuid4(),
            }
        )


def test_cycle2_recovery_closure_derives_budget_and_exact_decision_child() -> None:
    closure = _c2_retry_recovery_closure()
    assert closure.remaining_run_time_budget_ms() == 9_000
    decision = _c2_recovery_decision_record(closure)
    assert decision.decision is ToolRecoveryDecision.APPEND_SECOND_ATTEMPT
    assert decision.candidate_next_attempt_no == 2
    assert set(ToolRetryRecoveryDecisionRecordV2.model_fields) == {
        "recovery_decision_id",
        "tool_call_id",
        "last_attempt_no",
        "decision",
        "stable_reason_code",
        "candidate_next_attempt_no",
        "decided_at",
    }
    assert {
        "remaining_run_time_budget_ms",
        "customer_id",
        "result_ref",
        "payload",
        "observation_ref",
        "action_ref",
    }.isdisjoint(ToolRetryRecoveryDecisionRecordV2.model_fields)

    values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }
    with pytest.raises(ValidationError, match="owner"):
        ToolRetryRecoveryReadClosureV2(
            **{
                **values,
                "tool_call_record": _c2_project(
                    closure.tool_call_record,
                    private_owner_scope_ref="customer-B",
                ),
            }
        )
    with pytest.raises(ValidationError, match="run_time_budget_ms"):
        Cycle2RunBudgetPolicyEvidence(
            policy_version="cycle2-test-budget.v1",
            run_time_budget_ms=0,
        )


def test_cycle2_recovery_closure_accepts_initial_or_earlier_run_baseline() -> None:
    closure = _c2_retry_recovery_closure()
    values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }

    for base_version in (None, 2):
        rebuilt = ToolRetryRecoveryReadClosureV2(
            **{
                **values,
                "active_run_task_link_record": _c2_project(
                    closure.active_run_task_link_record,
                    base_task_state_version=base_version,
                ),
            }
        )
        assert (
            rebuilt.active_run_task_link_record.base_task_state_version
            == base_version
        )


def test_cycle2_recovered_append_is_one_atomic_decision_and_attempt_fence() -> None:
    closure = _c2_retry_recovery_closure()
    child = _c2_recovery_decision_record(closure)
    second = ToolAttemptRecordV2(
        tool_call_id=closure.tool_call_record.tool_call_id,
        attempt_no=2,
        started_at=closure.trusted_read_at,
    )
    next_record = _c2_project(
        closure.tool_call_record,
        attempts=(*closure.tool_call_record.attempts, second),
        attempt_count=2,
    )
    append = AppendToolAttemptV2Command(
        owner_scope=closure.owner_scope,
        expected_record=closure.tool_call_record,
        next_running_record=next_record,
        started_attempt=second,
    )
    command = AppendRecoveredToolAttemptV2Command(
        loaded_closure=closure,
        recovery_decision_record=child,
        attempt_append_command=append,
    )
    assert command.attempt_append_command.started_attempt.attempt_no == 2

    with pytest.raises(ValidationError, match="decision"):
        AppendRecoveredToolAttemptV2Command(
            loaded_closure=closure,
            recovery_decision_record=_c2_project(
                child,
                stable_reason_code="RUN_BUDGET_EXHAUSTED",
            ),
            attempt_append_command=append,
        )


def test_cycle2_unfinished_and_budget_recovery_terminal_commands_are_exact() -> None:
    unfinished = _c2_retry_recovery_closure(unfinished=True)
    unfinished_child = _c2_recovery_decision_record(unfinished)
    unfinished_terminal = _c2_project(
        unfinished.tool_call_record,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=unfinished.trusted_read_at,
        interruption_reason="PROCESS_RESTART_DETECTED",
        recovery_disposition=(
            ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
        ),
        recovery_decision_ref=unfinished_child.recovery_decision_id,
    )
    FinalizeUnfinishedToolRecoveryV2Command(
        loaded_closure=unfinished,
        recovery_decision_record=unfinished_child,
        terminal_tool_call_record=unfinished_terminal,
    )
    assert unfinished_terminal.attempts == unfinished.tool_call_record.attempts

    exhausted = _c2_retry_recovery_closure(budget_ms=500)
    exhausted_child = _c2_recovery_decision_record(exhausted)
    terminal = project_cycle2_budget_exhausted_recovery_terminal(
        tool_call=exhausted.tool_call_record,
        recovery_decision=exhausted.derive_recovery_decision(),
        recovery_decision_ref=exhausted_child.recovery_decision_id,
    )
    FinalizeBudgetExhaustedToolRecoveryV2Command(
        loaded_closure=exhausted,
        recovery_decision_record=exhausted_child,
        terminal_tool_call_record=terminal,
    )
    assert terminal.attempts == exhausted.tool_call_record.attempts
    assert terminal.result_ref is None

    timed_out = _c2_retry_recovery_closure(timeout=True, budget_ms=500)
    timeout_child = _c2_recovery_decision_record(timed_out)
    timeout_terminal = project_cycle2_budget_exhausted_recovery_terminal(
        tool_call=timed_out.tool_call_record,
        recovery_decision=timed_out.derive_recovery_decision(),
        recovery_decision_ref=timeout_child.recovery_decision_id,
    )
    FinalizeBudgetExhaustedToolRecoveryV2Command(
        loaded_closure=timed_out,
        recovery_decision_record=timeout_child,
        terminal_tool_call_record=timeout_terminal,
    )
    assert timeout_terminal.status is ToolCallStatus.TIMED_OUT
    assert timeout_terminal.failure_code == "TOOL_CALL_TIMEOUT"
    assert timeout_terminal.timeout_phase is ToolTimeoutPhase.AFTER_DISPATCH


def test_cycle2_state_invalidated_recovery_composes_exact_oa10_zero_result() -> None:
    closure = _c2_retry_recovery_closure(current_state_version=4)
    child = _c2_recovery_decision_record(closure)
    source = closure.tool_call_record
    terminal_tool = _c2_project(
        source,
        status=ToolCallStatus.INTERRUPTED,
        finished_at=closure.trusted_read_at,
        interruption_reason="STATE_OR_BINDING_INVALIDATED",
        recovery_disposition=(
            ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
        ),
        recovery_decision_ref=child.recovery_decision_id,
    )
    current_run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=closure.active_run_record.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW + timedelta(seconds=1),
    )
    obsolete_task = _c2_project(
        closure.current_task_record,
        state_version=3,
        updated_at=UTC_NOW,
    )
    obsolete_unit = _c2_project(
        closure.current_request_unit_record,
        state_version=3,
        updated_at=UTC_NOW,
    )
    oa10_closure = SupersededRunReadClosure(
        owner_scope=closure.owner_scope,
        trusted_conversation_record=_conversation(
            conversation_id=closure.active_run_record.conversation_id,
            owner_customer_id=closure.owner_scope.customer_id,
        ),
        expected_active_run_record=closure.active_run_record,
        expected_active_link_record=closure.active_run_task_link_record,
        current_authoritative_run_record=current_run,
        current_authoritative_link_record=RunTaskLinkRecordV2(
            run_id=current_run.run_id,
            task_id=closure.current_task_record.task_id,
            base_task_state_version=4,
        ),
        current_task_record=closure.current_task_record,
        current_request_unit_record=closure.current_request_unit_record,
        obsolete_task_record=obsolete_task,
        obsolete_request_unit_record=obsolete_unit,
        trusted_current_evidence_at=closure.trusted_read_at,
        invalidation_kind=SupersededRunInvalidationKind.TASK_VERSION_ADVANCED,
    )
    run_terminal = _c2_project(
        closure.active_run_record,
        status=AgentRunStatusV2.SUPERSEDED,
        completed_at=closure.trusted_read_at,
        stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
    )
    oa10 = FinalizeSupersededRunV2Command(
        loaded_closure=oa10_closure,
        superseded_run_record=run_terminal,
        no_result_link_record=closure.active_run_task_link_record,
        run_stopped_trace_record=TraceEventV2(
            trace_event_id=uuid4(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=closure.trusted_read_at,
            run_id=closure.active_run_record.run_id,
            task_id=closure.current_task_record.task_id,
            request_unit_id=closure.current_request_unit_record.request_unit_id,
            user_outcome=AgentOutcome.BLOCKED,
            stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
        ),
    )
    command = FinalizeStateInvalidatedToolRecoveryV2Command(
        loaded_closure=closure,
        recovery_decision_record=child,
        terminal_tool_call_record=terminal_tool,
        superseded_run_command=oa10,
    )
    assert command.superseded_run_command.no_result_link_record == (
        closure.active_run_task_link_record
    )
    assert {
        "task_record",
        "request_unit_record",
        "message_record",
        "agent_run_result",
        "result_ref",
    }.isdisjoint(FinalizeStateInvalidatedToolRecoveryV2Command.model_fields)


def test_cycle2_recovery_closure_fails_closed_on_stale_partial_or_duplicate_graph() -> None:
    closure = _c2_retry_recovery_closure()
    values = {
        field_name: getattr(closure, field_name)
        for field_name in type(closure).model_fields
    }
    child = _c2_recovery_decision_record(closure)
    variants = (
        ({"recovery_decision_records": (child,)}, "already exists"),
        (
            {"trusted_read_at": closure.active_run_record.started_at},
            "precedes current evidence",
        ),
        (
            {
                "active_run_task_link_record": _c2_project(
                    closure.active_run_task_link_record,
                    base_task_state_version=4,
                )
            },
            "RunTaskLink",
        ),
        (
            {
                "current_input_binding_records": (),
            },
            "at least 1",
        ),
        (
            {
                "tool_call_record": _c2_project(
                    closure.tool_call_record,
                    run_id=uuid4(),
                )
            },
            "identity",
        ),
    )
    for change, error in variants:
        with pytest.raises(ValidationError, match=error):
            ToolRetryRecoveryReadClosureV2(**{**values, **change})

    with pytest.raises(ValidationError, match="unknown reason"):
        ToolRetryRecoveryDecisionRecordV2(
            recovery_decision_id=uuid4(),
            tool_call_id=closure.tool_call_record.tool_call_id,
            last_attempt_no=1,
            decision=ToolRecoveryDecision.TERMINATE_RETRY_PATH,
            stable_reason_code="UNKNOWN_RECOVERY_REASON",
            decided_at=closure.trusted_read_at,
        )


def test_cycle2_unfinished_attempt_2_recovery_never_grants_another_append() -> None:
    closure = _c2_retry_recovery_closure()
    first = closure.tool_call_record.attempts[0]
    append_decision = _c2_recovery_decision_record(closure)
    second = ToolAttemptRecordV2(
        tool_call_id=closure.tool_call_record.tool_call_id,
        attempt_no=2,
        started_at=closure.trusted_read_at,
    )
    source = _c2_project(
        closure.tool_call_record,
        attempts=(first, second),
        attempt_count=2,
    )
    second_closure = ToolRetryRecoveryReadClosureV2(
        **{
            **{
                field_name: getattr(closure, field_name)
                for field_name in type(closure).model_fields
            },
            "tool_call_record": source,
            "recovery_decision_records": (append_decision,),
        }
    )
    decision = second_closure.derive_recovery_decision()
    assert decision.decision is ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT
    assert decision.last_attempt_no == 2
    assert decision.candidate_next_attempt_no is None


def test_cycle2_commands_reject_constructed_nested_bypass() -> None:
    owner, task, unit, source, observation, candidate_set, query_ref, _ = (
        _c2_search_graph()
    )
    malformed = candidate_set.model_construct(
        **{
            **{
                field_name: getattr(candidate_set, field_name)
                for field_name in type(candidate_set).model_fields
            },
            "candidate_set_version": (
                "order-candidate-set.p0.v1:sha256:" + "0" * 64
            ),
        },
    )
    with pytest.raises(ValidationError, match="recursively canonical"):
        ApplyOrderSearchOutcomeV2Command(
            owner_scope=owner,
            **_c2_search_runtime_fields(owner, candidate_set, source, task, unit),
            expected_task_record=task,
            next_task_record=_c2_project(
                task,
                status=TaskStatus.WAITING_USER,
                state_version=4,
                updated_at=observation.recorded_at,
            ),
            expected_request_unit_record=unit,
            next_request_unit_record=_c2_project(
                unit,
                status=TaskStatus.WAITING_USER,
                state_version=4,
                updated_at=observation.recorded_at,
                open_questions=("请选择候选订单",),
                observation_refs=(observation.observation_id,),
            ),
            source_tool_call_record=source,
            search_observation_record=observation,
            candidate_set_record=malformed,
            current_query_binding_refs=(query_ref,),
            pending_candidate_set_ref=candidate_set.candidate_set_id,
        )


def test_cycle2_search_rejects_multi_binding_singleton_spoof_and_wrong_conversation() -> None:
    command = _c2_multiple_search_command()
    command.loaded_read_closure.require_same_persisted_graph(
        command.loaded_read_closure
    )
    with pytest.raises(ValueError, match="persisted read fence mismatch"):
        command.loaded_read_closure.require_same_persisted_graph(
            _c2_multiple_search_command().loaded_read_closure
        )
    values = {
        field_name: getattr(command, field_name)
        for field_name in type(command).model_fields
    }
    query_refs = (
        command.current_query_binding.binding_ref,
        uuid4(),
    )
    source = _c2_project(
        command.source_tool_call_record,
        argument_binding_refs=query_refs,
    )
    candidate_values = command.candidate_set_record.model_dump(mode="python")
    candidate_values.pop("candidate_set_version")
    candidate_values["query_binding_refs"] = query_refs
    candidate_values["ordered_candidates"] = (
        command.candidate_set_record.ordered_candidates
    )
    candidate_values["candidate_set_version"] = compute_order_candidate_set_version(
        **candidate_values
    )
    candidate_set = OrderCandidateSetRecord.model_validate(candidate_values)

    expanded_expected_unit = _c2_project(
        command.expected_request_unit_record,
        input_binding_refs=query_refs,
    )
    with pytest.raises(ValidationError, match="current read closure mismatch"):
        OrderSearchCurrentReadClosure(
            **{
                **{
                    field_name: getattr(command.loaded_read_closure, field_name)
                    for field_name in OrderSearchCurrentReadClosure.model_fields
                },
                "current_request_unit_record": expanded_expected_unit,
            }
        )
    with pytest.raises(ValidationError, match="at most 1 item"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "expected_request_unit_record": expanded_expected_unit,
                "next_request_unit_record": _c2_project(
                    command.next_request_unit_record,
                    input_binding_refs=query_refs,
                ),
                "source_tool_call_record": source,
                "candidate_set_record": candidate_set,
                "current_query_binding_refs": query_refs,
            }
        )
    with pytest.raises(ValidationError, match="command/read closure mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "trusted_conversation_record": _conversation(
                    owner_customer_id=command.owner_scope.customer_id,
                ),
            }
        )

    with pytest.raises(ValidationError, match="command/read closure mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "source_run_record": _c2_project(
                    command.source_run_record,
                    run_id=uuid4(),
                ),
            }
        )

    tool_started_at = command.source_tool_call_record.started_at
    with pytest.raises(ValidationError, match="command/read closure mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "source_run_record": _c2_project(
                    command.source_run_record,
                    started_at=tool_started_at + timedelta(milliseconds=1),
                ),
            }
        )

    late_query_at = tool_started_at + timedelta(milliseconds=1)
    late_query_message = _c2_project(
        command.current_query_binding.source_message_record,
        received_at=late_query_at,
    )
    with pytest.raises(ValidationError, match="command/read closure mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "current_query_binding": _c2_project(
                    command.current_query_binding,
                    source_message_record=late_query_message,
                    accepted_at=late_query_at,
                ),
            }
        )

    late_finished_at = command.search_observation_record.recorded_at + timedelta(
        seconds=1
    )
    late_attempt = _c2_project(
        command.source_tool_call_record.attempts[-1],
        finished_at=late_finished_at,
    )
    with pytest.raises(ValidationError, match="source graph mismatch"):
        ApplyOrderSearchOutcomeV2Command(
            **{
                **values,
                "source_tool_call_record": _c2_project(
                    command.source_tool_call_record,
                    attempts=(late_attempt,),
                    finished_at=late_finished_at,
                ),
            }
        )


def test_cycle2_shipment_rejects_result_drift_and_sanitizes_constructed_closure() -> None:
    owner, task, unit, source, result, observation = _c2_shipment_inputs()
    expected_task = task
    expected_unit = unit
    task = _c2_project(
        expected_task,
        state_version=expected_task.state_version + 1,
        updated_at=observation.recorded_at,
    )
    unit = _c2_project(
        expected_unit,
        state_version=expected_unit.state_version + 1,
        updated_at=observation.recorded_at,
        observation_refs=(observation.observation_id,),
    )
    command_values = {
        "owner_scope": owner,
        "expected_task_record": expected_task,
        "next_task_record": task,
        "expected_request_unit_record": expected_unit,
        "next_request_unit_record": unit,
        "source_tool_call_record": source,
        "source_result_ref": source.result_ref,
        "source_result": result,
        "observation_record": observation,
        "trusted_acceptance_now": observation.recorded_at,
    }
    with pytest.raises(ValidationError, match="result projection mismatch"):
        SaveShipmentObservationV2Command(
            **{
                **command_values,
                "source_result": GetShipmentResult(
                    **{
                        **result.model_dump(mode="python"),
                        "source_resource_ref": "shipment:other",
                    }
                ),
            }
        )
    with pytest.raises(ValidationError, match="source graph mismatch"):
        SaveShipmentObservationV2Command(
            **{
                **command_values,
                "expected_task_record": _c2_project(
                    expected_task,
                    state_version=2,
                ),
                "expected_request_unit_record": _c2_project(
                    expected_unit,
                    state_version=2,
                ),
            }
        )

    conversation = _conversation(owner_customer_id=owner.customer_id)
    assessed_at = UTC_NOW + timedelta(minutes=2)
    closure = ShipmentAssessmentReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        current_task_record=task,
        current_request_unit_record=unit,
        current_observation_record=observation,
        current_observation_ref=observation.observation_id,
        verified_order_target_ref=observation.verified_order_target_ref,
        trusted_assessed_at=assessed_at,
        current_input_binding_records=(
            _input_binding(binding_id=unit.input_binding_refs[0]),
        ),
    )
    assessment = assess_shipment(
        assessment_id=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        task_state_version=task.state_version,
        verified_order_target_ref=observation.verified_order_target_ref,
        shipment_observation_ref=observation.observation_id,
        shipment_observation_source_version=observation.source_version,
        shipment_summary=observation.normalized_value,
        observation_observed_at=observation.observed_at,
        observation_valid_until=observation.valid_until,
        assessed_at=assessed_at,
    )
    constructed = ShipmentAssessmentReadClosure.model_construct(
        **{
            field_name: getattr(closure, field_name)
            for field_name in ShipmentAssessmentReadClosure.model_fields
        }
    )
    sanitized = SaveShipmentAssessmentV2Command(
        loaded_closure=constructed,
        assessment_record=assessment,
    )
    assert sanitized.loaded_closure is not constructed
    constructed.__dict__["hidden_authority"] = True
    with pytest.raises(ValidationError, match="recursively canonical"):
        SaveShipmentAssessmentV2Command(
            loaded_closure=constructed,
            assessment_record=assessment,
        )


def test_cycle2_assessment_requires_current_exact_claim_binding() -> None:
    owner, task, unit, _, _, observation = _c2_shipment_inputs()
    task = _c2_project(
        task,
        state_version=task.state_version + 1,
        updated_at=observation.recorded_at,
    )
    unit = _c2_project(
        unit,
        state_version=unit.state_version + 1,
        updated_at=observation.recorded_at,
        observation_refs=(observation.observation_id,),
    )
    conversation = _conversation(owner_customer_id=owner.customer_id)
    claim_ref = uuid4()
    unit = _c2_project(
        unit,
        input_binding_refs=(*unit.input_binding_refs, claim_ref),
    )
    source_message = _message(
        conversation_id=conversation.conversation_id,
        content="物流显示签收，但我没有收到",
    )
    claim = ShipmentNotReceivedClaimReadClosure(
        binding_ref=claim_ref,
        private_owner_scope_ref=owner.customer_id,
        conversation_id=conversation.conversation_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        task_state_version=task.state_version,
        verified_order_target_ref=observation.verified_order_target_ref,
        source_message_record=source_message,
        accepted_at=source_message.received_at,
    )
    delivered_observation = _c2_project(
        observation,
        normalized_value=ShipmentSummaryProjection(
            shipment_status=ShipmentStatus.DELIVERED,
            latest_event_code=ShipmentEventCode.DELIVERED,
            latest_event_at=UTC_NOW - timedelta(hours=1),
            delivered_at=UTC_NOW - timedelta(hours=1),
        ),
    )
    assessed_at = UTC_NOW + timedelta(minutes=2)
    closure = ShipmentAssessmentReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        current_task_record=task,
        current_request_unit_record=unit,
        current_observation_record=delivered_observation,
        current_observation_ref=delivered_observation.observation_id,
        verified_order_target_ref=delivered_observation.verified_order_target_ref,
        trusted_assessed_at=assessed_at,
        current_input_binding_records=(
            _input_binding(binding_id=unit.input_binding_refs[0]),
        ),
        current_claim_bindings=(claim,),
    )
    assessment = assess_shipment(
        assessment_id=uuid4(),
        private_owner_scope_ref=owner.customer_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        task_state_version=task.state_version,
        verified_order_target_ref=delivered_observation.verified_order_target_ref,
        shipment_observation_ref=delivered_observation.observation_id,
        shipment_observation_source_version=delivered_observation.source_version,
        shipment_summary=delivered_observation.normalized_value,
        observation_observed_at=delivered_observation.observed_at,
        observation_valid_until=delivered_observation.valid_until,
        assessed_at=assessed_at,
        claim_binding_ref=claim_ref,
    )
    saved = SaveShipmentAssessmentV2Command(
        loaded_closure=closure,
        assessment_record=assessment,
    )
    assert saved.assessment_record.claim_binding_ref == claim_ref

    relabelled_claim = ShipmentAssessmentReadClosure(
        **{
            **{
                field_name: getattr(closure, field_name)
                for field_name in ShipmentAssessmentReadClosure.model_fields
            },
            "current_claim_bindings": (),
            "current_input_binding_records": (
                *closure.current_input_binding_records,
                _input_binding(binding_id=claim_ref),
            ),
        }
    )
    with pytest.raises(ValueError, match="persisted read fence mismatch"):
        relabelled_claim.require_same_persisted_graph(closure)

    wrong_target_claim = ShipmentNotReceivedClaimReadClosure(
        **{
            **{
                field_name: getattr(claim, field_name)
                for field_name in ShipmentNotReceivedClaimReadClosure.model_fields
            },
            "verified_order_target_ref": "owner-order:wrong",
        }
    )
    with pytest.raises(ValidationError, match="Claim binding closure mismatch"):
        ShipmentAssessmentReadClosure(
            **{
                **{
                    field_name: getattr(closure, field_name)
                    for field_name in ShipmentAssessmentReadClosure.model_fields
                },
                "current_claim_bindings": (wrong_target_claim,),
            }
        )


def test_cycle2_oa10_accepts_completed_replacement_and_rejects_trace_sidecar() -> None:
    owner = _owner_scope()
    conversation = _conversation(owner_customer_id=owner.customer_id)
    old_run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=UTC_NOW,
    )
    task_id = uuid4()
    old_link = RunTaskLinkRecordV2(
        run_id=old_run.run_id,
        task_id=task_id,
        base_task_state_version=3,
    )
    replacement_completed_at = UTC_NOW + timedelta(seconds=2)
    replacement = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=conversation.conversation_id,
        status=AgentRunStatusV2.COMPLETED,
        provider_lane="scripted",
        started_at=UTC_NOW + timedelta(seconds=1),
        completed_at=replacement_completed_at,
        stop_reason=StopReasonV2.GOAL_COMPLETED,
    )
    task = _task(
        task_id=task_id,
        state_version=4,
        updated_at=replacement_completed_at,
    )
    unit = _request_unit(
        task_id=task_id,
        state_version=4,
        updated_at=replacement_completed_at,
    )
    closure = SupersededRunReadClosure(
        owner_scope=owner,
        trusted_conversation_record=conversation,
        expected_active_run_record=old_run,
        expected_active_link_record=old_link,
        current_authoritative_run_record=replacement,
        current_authoritative_link_record=RunTaskLinkRecordV2(
            run_id=replacement.run_id,
            task_id=task_id,
            base_task_state_version=3,
            result_task_state_version=4,
        ),
        current_task_record=task,
        current_request_unit_record=unit,
        obsolete_task_record=_c2_project(
            task,
            state_version=3,
            updated_at=UTC_NOW,
        ),
        obsolete_request_unit_record=_c2_project(
            unit,
            state_version=3,
            updated_at=UTC_NOW,
        ),
        trusted_current_evidence_at=replacement_completed_at,
        invalidation_kind=SupersededRunInvalidationKind.TASK_VERSION_ADVANCED,
    )
    terminal_at = replacement_completed_at + timedelta(seconds=1)
    terminal = AgentRunRecordV2(
        **{
            **old_run.model_dump(mode="python"),
            "status": AgentRunStatusV2.SUPERSEDED,
            "completed_at": terminal_at,
            "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
        }
    )
    trace = TraceEventV2(
        trace_event_id=uuid4(),
        event_type=TraceEventType.RUN_STOPPED,
        occurred_at=terminal_at,
        run_id=old_run.run_id,
        task_id=task_id,
        request_unit_id=unit.request_unit_id,
        user_outcome=AgentOutcome.BLOCKED,
        stop_reason=StopReasonV2.STATE_OR_BINDING_INVALIDATED,
    )
    FinalizeSupersededRunV2Command(
        loaded_closure=closure,
        superseded_run_record=terminal,
        no_result_link_record=old_link,
        run_stopped_trace_record=trace,
    )
    with pytest.raises(ValidationError, match="outbound or mutation refs"):
        FinalizeSupersededRunV2Command(
            loaded_closure=closure,
            superseded_run_record=terminal,
            no_result_link_record=old_link,
            run_stopped_trace_record=_c2_project(
                trace,
                provider_name="must-not-cross-oa10",
            ),
        )
    with pytest.raises(ValidationError, match="terminal time precedes"):
        FinalizeSupersededRunV2Command(
            loaded_closure=closure,
            superseded_run_record=AgentRunRecordV2(
                **{
                    **old_run.model_dump(mode="python"),
                    "status": AgentRunStatusV2.SUPERSEDED,
                    "completed_at": UTC_NOW + timedelta(seconds=1),
                    "stop_reason": StopReasonV2.STATE_OR_BINDING_INVALIDATED,
                }
            ),
            no_result_link_record=old_link,
            run_stopped_trace_record=_c2_project(
                trace,
                occurred_at=UTC_NOW + timedelta(seconds=1),
            ),
        )


def test_cycle2_application_control_and_rejection_fields_are_closed() -> None:
    assert {purpose.value for purpose in Cycle2ControlPurpose} == {
        "PROPOSE_GET_ORDER",
        "PROPOSE_FIXED_RESPONSE",
        "PROPOSE_CANDIDATE_QUESTION",
        "PROPOSE_POST_ORDER",
        "PROPOSE_SHIPMENT_ASSESSMENT",
    }
    assert set(ApplyContinuationInputBindingV2Command.model_fields) == {
        "loaded_closure",
        "new_input_binding_record",
        "next_task_record",
        "next_request_unit_record",
        "rejected_ordinal_selection",
    }
    assert {
        "current_order_observation_records",
        "current_shipment_observation_records",
        "ordinal_selection_rejection_hint",
    }.issubset(Cycle2CurrentSessionTaskClosure.model_fields)
