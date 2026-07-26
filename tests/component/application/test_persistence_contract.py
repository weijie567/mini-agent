import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from uuid import UUID

import pytest

import mini_agent.application.persistence as persistence_module
from mini_agent.application.persistence import (
    DecodedP0PersistenceRecord,
    P0_LOGICAL_CHILD_SPECS,
    P0_PERSISTENCE_REGISTRY,
    P0LogicalChildCode,
    P0PersistenceEnvelope,
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordReference,
    P0RecordCode,
    decode_persistence_record,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ConversationRecord,
    ConversationTaskLinkRecord,
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultRecord,
    EvalResultStatus,
    EvalVersionManifest,
    MessageDirection,
    MessageRecord,
    RunTaskLinkRecord,
)
from mini_agent.core.common import freeze_json_value
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
from mini_agent.core.request_understanding import InputAuthority, TaskDeltaOperation
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    CandidateValidationDecision,
    CandidateValidationRecord,
    InputBinding,
    InputValidationStatus,
    RequestUnderstandingRecord,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateDecisionValue,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    TraceEvent,
    TraceEventType,
)


EXPECTED_RECORD_CODES = (
    "conversation_record",
    "message_record",
    "request_understanding_record",
    "task_record",
    "request_unit_record",
    "conversation_task_link_record",
    "run_task_link_record",
    "input_binding_record",
    "model_visible_toolset_artifact",
    "agent_run_record",
    "gate_decision_record",
    "tool_call_record",
    "observation_record",
    "context_manifest_record",
    "trace_event_record",
    "eval_result_record",
    "eval_execution_failure_record",
)

EXTERNAL_REFERENCE_CASES = (
    (P0RecordCode.INPUT_BINDING_RECORD, "request_unit_id"),
    (P0RecordCode.OBSERVATION_RECORD, "source_tool_call_id"),
    (P0RecordCode.OBSERVATION_RECORD, "source_run_id"),
    (P0RecordCode.OBSERVATION_RECORD, "source_task_id"),
    (P0RecordCode.OBSERVATION_RECORD, "source_request_unit_id"),
)

EXPECTED_PROJECTION_SIGNATURES = """\
conversation_record|owner_customer_id|DIRECT_OWNER|-|-|1|1|0
message_record|conversation_id|TOP_LEVEL_P0_REFERENCE|conversation_id|conversation_record|1|1|0
request_understanding_record|run_id|TOP_LEVEL_P0_REFERENCE|run_id|agent_run_record|1|1|0
request_understanding_record|message_ref|TOP_LEVEL_P0_REFERENCE|message_ref|message_record|1|1|0
request_understanding_record|accepted_delta_refs[]|LOGICAL_CHILD_CORRELATION|-|-|0|-|1
request_understanding_record|candidate_validation[].candidate_ref,next_move_candidate_ref?|PAYLOAD_CORRELATION|-|-|0|-|0
task_record|owner_customer_id|DIRECT_OWNER|-|-|1|1|0
task_record|last_outcome_ref?|PAYLOAD_CORRELATION|-|-|0|1|0
request_unit_record|task_id|TOP_LEVEL_P0_REFERENCE|task_id|task_record|1|1|0
request_unit_record|goal_source_refs[]|TOP_LEVEL_P0_REFERENCE|goal_source_ref|message_record|1|-|1
request_unit_record|contextualization_ref?|PAYLOAD_CORRELATION|-|-|0|1|0
request_unit_record|constraint_refs[]|PAYLOAD_CORRELATION|-|-|0|-|1
request_unit_record|dependency_refs[]|PAYLOAD_CORRELATION|-|-|0|-|1
request_unit_record|input_binding_refs[]|TOP_LEVEL_P0_REFERENCE|input_binding_ref|input_binding_record|1|-|1
request_unit_record|observation_refs[]|TOP_LEVEL_P0_REFERENCE|observation_ref|observation_record|0|-|1
request_unit_record|evidence_binding_refs[]|P0_FIRST_SLICE_MUST_BE_EMPTY|-|-|0|0|0
request_unit_record|pending_action_ref?|P0_FIRST_SLICE_MUST_BE_EMPTY|-|-|0|0|0
request_unit_record|result_refs[]|PAYLOAD_CORRELATION|-|-|0|-|1
conversation_task_link_record|conversation_id|TOP_LEVEL_P0_REFERENCE|conversation_id|conversation_record|1|1|0
conversation_task_link_record|task_id|TOP_LEVEL_P0_REFERENCE|task_id|task_record|1|1|0
run_task_link_record|run_id|TOP_LEVEL_P0_REFERENCE|run_id|agent_run_record|1|1|0
run_task_link_record|task_id|TOP_LEVEL_P0_REFERENCE|task_id|task_record|1|1|0
input_binding_record|source_refs[]|TOP_LEVEL_P0_REFERENCE|source_ref|message_record|1|-|1
input_binding_record|supersedes?|TOP_LEVEL_P0_REFERENCE|supersedes|input_binding_record|0|1|0
input_binding_record|external request_unit_id|EXTERNAL_REQUIRED_P0_REFERENCE|request_unit_id|request_unit_record|1|1|0
agent_run_record|conversation_id?|TOP_LEVEL_P0_REFERENCE|conversation_id|conversation_record|0|1|0
gate_decision_record|context_manifest_id|TOP_LEVEL_P0_REFERENCE|context_manifest_id|context_manifest_record|1|1|0
gate_decision_record|argument_binding_refs[]|TOP_LEVEL_P0_REFERENCE|argument_binding_ref|input_binding_record|0|-|1
gate_decision_record|model_call_id,provider_tool_call_id?|PAYLOAD_CORRELATION|-|-|1|2|0
tool_call_record|run_id|TOP_LEVEL_P0_REFERENCE|run_id|agent_run_record|1|1|0
tool_call_record|task_id|TOP_LEVEL_P0_REFERENCE|task_id|task_record|1|1|0
tool_call_record|request_unit_id|TOP_LEVEL_P0_REFERENCE|request_unit_id|request_unit_record|1|1|0
tool_call_record|context_manifest_id|TOP_LEVEL_P0_REFERENCE|context_manifest_id|context_manifest_record|1|1|0
tool_call_record|gate_decision_id|TOP_LEVEL_P0_REFERENCE|gate_decision_id|gate_decision_record|1|1|0
tool_call_record|argument_binding_refs[]|TOP_LEVEL_P0_REFERENCE|argument_binding_ref|input_binding_record|1|-|1
tool_call_record|model_call_id,provider_tool_call_id?|PAYLOAD_CORRELATION|-|-|1|2|0
tool_call_record|result_ref?|PAYLOAD_CORRELATION|-|-|0|1|0
observation_record|supersedes?|TOP_LEVEL_P0_REFERENCE|supersedes|observation_record|0|1|0
observation_record|external source_tool_call_id|EXTERNAL_REQUIRED_P0_REFERENCE|source_tool_call_id|tool_call_record|1|1|0
observation_record|external source_run_id|EXTERNAL_REQUIRED_P0_REFERENCE|source_run_id|agent_run_record|1|1|0
observation_record|external source_task_id|EXTERNAL_REQUIRED_P0_REFERENCE|source_task_id|task_record|1|1|0
observation_record|external source_request_unit_id|EXTERNAL_REQUIRED_P0_REFERENCE|source_request_unit_id|request_unit_record|1|1|0
observation_record|raw_result_ref?|RESTRICTED_DIAGNOSTIC_CORRELATION|-|-|0|1|0
observation_record|source_resource_ref|PAYLOAD_CORRELATION|-|-|1|1|0
context_manifest_record|run_id|TOP_LEVEL_P0_REFERENCE|run_id|agent_run_record|1|1|0
context_manifest_record|selected_message_refs[]|TOP_LEVEL_P0_REFERENCE|selected_message_ref|message_record|0|-|1
context_manifest_record|task_state_ref_and_version?.task_id|TOP_LEVEL_P0_REFERENCE|task_state_ref|task_record|0|1|0
context_manifest_record|observation_refs_and_versions[].record_ref|TOP_LEVEL_P0_REFERENCE|observation_ref|observation_record|0|-|1
context_manifest_record|model_visible_toolset_hash|TOP_LEVEL_P0_REFERENCE|model_visible_toolset_hash|model_visible_toolset_artifact|1|1|0
context_manifest_record|evidence_refs_and_versions[],action_record_refs[]|P0_FIRST_SLICE_MUST_BE_EMPTY|-|-|0|0|0
context_manifest_record|model_call_id,truncation_decisions[].source_ref|PAYLOAD_CORRELATION|-|-|1|-|0
trace_event_record|run_id|TOP_LEVEL_P0_REFERENCE|run_id|agent_run_record|1|1|0
trace_event_record|message_ref?|TOP_LEVEL_P0_REFERENCE|message_ref|message_record|0|1|0
trace_event_record|task_id?|TOP_LEVEL_P0_REFERENCE|task_id|task_record|0|1|0
trace_event_record|request_unit_id?|TOP_LEVEL_P0_REFERENCE|request_unit_id|request_unit_record|0|1|0
trace_event_record|input_binding_ref?|TOP_LEVEL_P0_REFERENCE|input_binding_ref|input_binding_record|0|1|0
trace_event_record|context_manifest_id?|TOP_LEVEL_P0_REFERENCE|context_manifest_id|context_manifest_record|0|1|0
trace_event_record|model_visible_toolset_hash?|TOP_LEVEL_P0_REFERENCE|model_visible_toolset_hash|model_visible_toolset_artifact|0|1|0
trace_event_record|argument_binding_refs[]|TOP_LEVEL_P0_REFERENCE|argument_binding_ref|input_binding_record|0|-|1
trace_event_record|tool_call_id?|TOP_LEVEL_P0_REFERENCE|tool_call_id|tool_call_record|0|1|0
trace_event_record|observation_ref?|TOP_LEVEL_P0_REFERENCE|observation_ref|observation_record|0|1|0
trace_event_record|accepted_delta_ref?|LOGICAL_CHILD_CORRELATION|-|-|0|1|0
trace_event_record|model_call_id?,presentation_plan_ref?,case_id?|PAYLOAD_CORRELATION|-|-|0|3|0
eval_result_record|trace_ref?|CONDITIONAL_PAYLOAD_CORRELATION|-|-|0|1|0
eval_execution_failure_record|trace_ref?|PAYLOAD_CORRELATION|-|-|0|1|0
eval_execution_failure_record|diagnostic_ref?|RESTRICTED_DIAGNOSTIC_CORRELATION|-|-|0|1|0
accepted_task_delta|candidate_ref|PARENT_LOCAL_CORRELATION|-|-|1|1|0
accepted_task_delta|message_ref|PARENT_FIELD_EQUALITY|-|-|1|1|0
accepted_task_delta|input_binding_refs[]|CHILD_TOP_LEVEL_P0_REFERENCE|input_binding_ref|input_binding_record|1|-|1
task_state_transition|task_id|PARENT_FIELD_EQUALITY|-|-|1|1|0
task_state_transition|request_unit_id|CHILD_TOP_LEVEL_P0_REFERENCE|request_unit_id|request_unit_record|1|1|0
task_state_transition|reason_ref|PAYLOAD_CORRELATION|-|-|1|1|0
tool_attempt_record|tool_call_id|PARENT_FIELD_EQUALITY|-|-|1|1|0
""".splitlines()
UTC_NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def _uuid(index: int) -> UUID:
    return UUID(int=index)


def _identity(
    field_name: str, value: UUID | str | int
) -> tuple[tuple[str, str | int], ...]:
    projected = str(value) if isinstance(value, UUID) else value
    return ((field_name, projected),)


def _reference(
    relation: str,
    target_record_code: P0RecordCode,
    field_name: str,
    value: UUID | str | int,
) -> P0RecordReference:
    return P0RecordReference(
        relation=relation,
        target_record_code=target_record_code,
        target_logical_identity=_identity(field_name, value),
    )


def _version_manifest() -> EvalVersionManifest:
    return EvalVersionManifest(
        dataset_version="e2e01-thin-dataset-v1",
        candidate_version="candidate-source-revision",
        fixture_versions=("e2e01-thin-fixture-v1",),
        runtime_version="runtime-source-revision",
    )


@dataclass(frozen=True, slots=True)
class RecordCase:
    code: P0RecordCode
    record: object
    external_references: tuple[P0RecordReference, ...] = ()
    logical_children: tuple[object, ...] = ()


def _record_cases() -> tuple[RecordCase, ...]:
    tool_spec = get_order_tool_spec()
    toolset_hash = compute_model_visible_toolset_hash((tool_spec,))
    order_summary = OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=UTC_NOW,
        status_updated_at=UTC_NOW + timedelta(minutes=1),
    )
    accepted_delta = AcceptedTaskDelta(
        accepted_delta_id=_uuid(41),
        candidate_ref=_uuid(40),
        message_ref=_uuid(2),
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text="查询订单 O-1001",
        input_binding_refs=(_uuid(8),),
        accepted_at=UTC_NOW,
    )
    task_transition = TaskStateTransition(
        task_id=_uuid(4),
        request_unit_id=_uuid(5),
        from_status=TaskStatus.ACTIVE,
        to_status=TaskStatus.COMPLETED,
        base_state_version=1,
        result_state_version=2,
        reason_ref=_uuid(43),
        changed_at=UTC_NOW + timedelta(minutes=1),
    )
    tool_attempt = ToolAttemptRecord(
        tool_call_id=_uuid(12),
        attempt_no=1,
        started_at=UTC_NOW,
    )

    return (
        RecordCase(
            P0RecordCode.CONVERSATION_RECORD,
            ConversationRecord(
                schema_version="conversation_record.p0.v1",
                conversation_id=_uuid(1),
                owner_customer_id="customer-A",
                created_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.MESSAGE_RECORD,
            MessageRecord(
                schema_version="message_record.p0.v1",
                message_id=_uuid(2),
                conversation_id=_uuid(1),
                direction=MessageDirection.USER,
                content="查询订单 O-1001",
                received_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RequestUnderstandingRecord(
                run_id=_uuid(3),
                message_ref=_uuid(2),
                schema_version="request_understanding_record.p0.v1",
                candidate_validation=(
                    CandidateValidationRecord(
                        candidate_ref=_uuid(40),
                        decision=CandidateValidationDecision.ACCEPT,
                    ),
                ),
                accepted_delta_refs=(_uuid(41),),
                validated_task_state_version=1,
                next_move_candidate_ref=_uuid(42),
            ),
            logical_children=(accepted_delta,),
        ),
        RecordCase(
            P0RecordCode.TASK_RECORD,
            TaskRecord(
                task_id=_uuid(4),
                owner_customer_id="customer-A",
                status=TaskStatus.COMPLETED,
                state_version=2,
                created_at=UTC_NOW,
                updated_at=UTC_NOW + timedelta(minutes=1),
            ),
            logical_children=(task_transition,),
        ),
        RecordCase(
            P0RecordCode.REQUEST_UNIT_RECORD,
            RequestUnitRecord(
                request_unit_id=_uuid(5),
                task_id=_uuid(4),
                goal_text="查询订单 O-1001",
                goal_source_refs=(_uuid(2),),
                input_binding_refs=(_uuid(8),),
                observation_refs=(_uuid(13),),
                status=TaskStatus.COMPLETED,
                state_version=2,
                created_at=UTC_NOW,
                updated_at=UTC_NOW + timedelta(minutes=1),
            ),
        ),
        RecordCase(
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            ConversationTaskLinkRecord(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=_uuid(1),
                task_id=_uuid(4),
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.RUN_TASK_LINK_RECORD,
            RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=_uuid(3),
                task_id=_uuid(4),
                base_task_state_version=None,
                result_task_state_version=2,
            ),
        ),
        RecordCase(
            P0RecordCode.INPUT_BINDING_RECORD,
            InputBinding(
                binding_id=_uuid(8),
                name="order_id",
                normalized_value="O-1001",
                authority=InputAuthority.USER_CLAIM,
                source_refs=(_uuid(2),),
                validation_status=InputValidationStatus.ACCEPTED,
                confirmed_by_user=True,
                created_at=UTC_NOW,
                updated_at=UTC_NOW,
            ),
            external_references=(
                _reference(
                    "request_unit_id",
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    "request_unit_id",
                    _uuid(5),
                ),
            ),
        ),
        RecordCase(
            P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
            ModelVisibleToolsetArtifact(
                model_visible_toolset_hash=toolset_hash,
                provider_visible_tool_specs=(tool_spec,),
            ),
        ),
        RecordCase(
            P0RecordCode.AGENT_RUN_RECORD,
            AgentRunRecord(
                run_id=_uuid(3),
                conversation_id=_uuid(1),
                status=AgentRunStatus.CREATED,
                provider_lane="offline_gate",
                started_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.GATE_DECISION_RECORD,
            GateDecision(
                gate_decision_id=_uuid(11),
                model_call_id=_uuid(20),
                context_manifest_id=_uuid(14),
                requested_provider_tool_name="get_order",
                resolved_canonical_tool_name="get_order",
                snapshot_match=True,
                registration_valid=True,
                schema_valid=True,
                trusted_field_valid=True,
                argument_binding_valid=True,
                argument_binding_refs=(_uuid(8),),
                budget_valid=True,
                progress_valid=True,
                proposed_base_task_state_version=None,
                validated_task_state_version=2,
                state_version_valid=True,
                action_boundary_valid=True,
                decision=GateDecisionValue.ACCEPT,
                decided_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.TOOL_CALL_RECORD,
            ToolCallRecord(
                tool_call_id=_uuid(12),
                run_id=_uuid(3),
                task_id=_uuid(4),
                request_unit_id=_uuid(5),
                model_call_id=_uuid(20),
                context_manifest_id=_uuid(14),
                gate_decision_id=_uuid(11),
                canonical_tool_name="get_order",
                tool_registry_version="e2e01-thin-tools-v1",
                validated_task_state_version=2,
                argument_binding_refs=(_uuid(8),),
                effect=ToolEffect.READ,
                attempt_count=1,
                status=ToolCallStatus.RUNNING,
                started_at=UTC_NOW,
            ),
            logical_children=(tool_attempt,),
        ),
        RecordCase(
            P0RecordCode.OBSERVATION_RECORD,
            OrderObservation(
                observation_id=_uuid(13),
                source_tool="get_order",
                source_resource_ref="O-1001",
                source_version="order-v1",
                normalized_type="ORDER_SUMMARY",
                normalized_value=order_summary,
                observed_at=UTC_NOW,
                recorded_at=UTC_NOW,
                visibility=ObservationVisibility.MODEL_VISIBLE,
            ),
            external_references=(
                _reference(
                    "source_tool_call_id",
                    P0RecordCode.TOOL_CALL_RECORD,
                    "tool_call_id",
                    _uuid(12),
                ),
                _reference(
                    "source_run_id",
                    P0RecordCode.AGENT_RUN_RECORD,
                    "run_id",
                    _uuid(3),
                ),
                _reference(
                    "source_task_id",
                    P0RecordCode.TASK_RECORD,
                    "task_id",
                    _uuid(4),
                ),
                _reference(
                    "source_request_unit_id",
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    "request_unit_id",
                    _uuid(5),
                ),
            ),
        ),
        RecordCase(
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            ContextManifest(
                context_manifest_id=_uuid(14),
                run_id=_uuid(3),
                model_call_id=_uuid(20),
                tool_registry_version="e2e01-thin-tools-v1",
                model_visible_toolset_hash=toolset_hash,
                selected_message_refs=(_uuid(2),),
                task_state_ref_and_version=TaskStateRefAndVersion(
                    task_id=_uuid(4),
                    state_version=2,
                ),
                observation_refs_and_versions=(
                    VersionedRecordRef(
                        record_ref=_uuid(13),
                        version="order-observation-v1",
                    ),
                ),
                redaction_policy_version="e2e01-thin-redaction-v1",
                token_counts=TokenCounts(input_tokens=20, output_tokens=0),
                assembled_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.TRACE_EVENT_RECORD,
            TraceEvent(
                trace_event_id=_uuid(15),
                event_type=TraceEventType.NEXT_MOVE_REVALIDATED,
                occurred_at=UTC_NOW,
                run_id=_uuid(3),
                case_id="E2E01-01",
                message_ref=_uuid(2),
                accepted_delta_ref=_uuid(41),
                task_id=_uuid(4),
                request_unit_id=_uuid(5),
                input_binding_ref=_uuid(8),
                model_call_id=_uuid(20),
                context_manifest_id=_uuid(14),
                tool_registry_version="e2e01-thin-tools-v1",
                model_visible_toolset_hash=toolset_hash,
                argument_binding_refs=(_uuid(8),),
                tool_call_id=_uuid(12),
                observation_ref=_uuid(13),
            ),
        ),
        RecordCase(
            P0RecordCode.EVAL_RESULT_RECORD,
            EvalResultRecord(
                schema_version="eval_result_record.p0.v1",
                eval_run_id=_uuid(16),
                case_id="E2E01-01",
                lane="offline_gate",
                attempt=1,
                status=EvalResultStatus.PASS,
                grader_results=(
                    EvalGraderResult(
                        grader_name="PersistenceGrader",
                        status=EvalGraderStatus.PASS,
                    ),
                ),
                observed_outcome=AgentOutcome.COMPLETED,
                trace_ref=_uuid(50),
                version_manifest=_version_manifest(),
                completed_at=UTC_NOW,
            ),
        ),
        RecordCase(
            P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD,
            EvalExecutionFailureRecord(
                schema_version="eval_execution_failure_record.p0.v1",
                eval_run_id=_uuid(17),
                case_id="E2E01-01",
                lane="offline_gate",
                attempt=1,
                failure_phase=EvalExecutionFailurePhase.TRACE_PERSISTENCE,
                safe_error_code=EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
                diagnostic_ref=_uuid(51),
                trace_ref=_uuid(50),
                version_manifest=_version_manifest(),
                occurred_at=UTC_NOW,
            ),
        ),
    )


def _case(record_code: P0RecordCode) -> RecordCase:
    return next(item for item in _record_cases() if item.code is record_code)


def test_registry_is_exact_immutable_and_closed() -> None:
    assert tuple(code.value for code in P0RecordCode) == EXPECTED_RECORD_CODES
    assert isinstance(P0_PERSISTENCE_REGISTRY, MappingProxyType)
    assert tuple(P0_PERSISTENCE_REGISTRY) == tuple(P0RecordCode)
    assert len(P0_PERSISTENCE_REGISTRY) == 17
    assert len({spec.source_model for spec in P0_PERSISTENCE_REGISTRY.values()}) == 17
    assert {
        spec.record_schema_version for spec in P0_PERSISTENCE_REGISTRY.values()
    } == {f"{code.value}.p0.v1" for code in P0RecordCode}

    with pytest.raises(TypeError):
        P0_PERSISTENCE_REGISTRY[P0RecordCode.CONVERSATION_RECORD] = (
            P0_PERSISTENCE_REGISTRY[P0RecordCode.MESSAGE_RECORD]
        )

    assert isinstance(P0_LOGICAL_CHILD_SPECS, MappingProxyType)
    assert tuple(P0_LOGICAL_CHILD_SPECS) == tuple(P0LogicalChildCode)
    assert len(P0_LOGICAL_CHILD_SPECS) == 3
    assert not hasattr(persistence_module, "register")
    assert not hasattr(persistence_module, "_REGISTRY")
    assert not hasattr(persistence_module, "_CHILD_SPECS")


def test_projection_matrices_are_exact_and_reference_targets_are_closed() -> None:
    top_level_rules = tuple(
        rule
        for spec in P0_PERSISTENCE_REGISTRY.values()
        for rule in spec.projection_decisions
    )
    child_rules = tuple(
        rule
        for spec in P0_LOGICAL_CHILD_SPECS.values()
        for rule in spec.projection_decisions
    )
    reference_classes = {
        "TOP_LEVEL_P0_REFERENCE",
        "EXTERNAL_REQUIRED_P0_REFERENCE",
        "CHILD_TOP_LEVEL_P0_REFERENCE",
    }
    reference_rules = tuple(
        rule
        for rule in (*top_level_rules, *child_rules)
        if rule.classification.value in reference_classes
    )

    assert len(top_level_rules) == 66
    assert len(child_rules) == 7
    assert len(reference_rules) == 45
    assert (
        sum(
            rule.classification.value == "EXTERNAL_REQUIRED_P0_REFERENCE"
            for rule in top_level_rules
        )
        == 5
    )
    assert (
        sum(
            rule.classification.value == "P0_FIRST_SLICE_MUST_BE_EMPTY"
            for rule in top_level_rules
        )
        == 3
    )
    assert all(rule.target_record_code in P0RecordCode for rule in reference_rules)
    assert all(rule.relation for rule in reference_rules)


def test_all_projection_decision_signatures_match_the_canonical_matrix() -> None:
    actual = [
        "|".join(
            (
                owner_code.value,
                rule.field_label,
                rule.classification.value,
                rule.relation or "-",
                (
                    rule.target_record_code.value
                    if rule.target_record_code is not None
                    else "-"
                ),
                str(rule.minimum),
                str(rule.maximum) if rule.maximum is not None else "-",
                "1" if rule.unique else "0",
            )
        )
        for registry in (P0_PERSISTENCE_REGISTRY, P0_LOGICAL_CHILD_SPECS)
        for owner_code, spec in registry.items()
        for rule in spec.projection_decisions
    ]

    assert actual == EXPECTED_PROJECTION_SIGNATURES


def test_source_external_and_child_references_are_recomputed_and_sorted() -> None:
    expected: dict[P0RecordCode, tuple[tuple[str, P0RecordCode], ...]] = {
        P0RecordCode.CONVERSATION_RECORD: (),
        P0RecordCode.MESSAGE_RECORD: (
            ("conversation_id", P0RecordCode.CONVERSATION_RECORD),
        ),
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD: (
            ("input_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
            ("message_ref", P0RecordCode.MESSAGE_RECORD),
            ("run_id", P0RecordCode.AGENT_RUN_RECORD),
        ),
        P0RecordCode.TASK_RECORD: (
            ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
        ),
        P0RecordCode.REQUEST_UNIT_RECORD: (
            ("goal_source_ref", P0RecordCode.MESSAGE_RECORD),
            ("input_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
            ("observation_ref", P0RecordCode.OBSERVATION_RECORD),
            ("task_id", P0RecordCode.TASK_RECORD),
        ),
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
            ("conversation_id", P0RecordCode.CONVERSATION_RECORD),
            ("task_id", P0RecordCode.TASK_RECORD),
        ),
        P0RecordCode.RUN_TASK_LINK_RECORD: (
            ("run_id", P0RecordCode.AGENT_RUN_RECORD),
            ("task_id", P0RecordCode.TASK_RECORD),
        ),
        P0RecordCode.INPUT_BINDING_RECORD: (
            ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
            ("source_ref", P0RecordCode.MESSAGE_RECORD),
        ),
        P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT: (),
        P0RecordCode.AGENT_RUN_RECORD: (
            ("conversation_id", P0RecordCode.CONVERSATION_RECORD),
        ),
        P0RecordCode.GATE_DECISION_RECORD: (
            ("argument_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
            ("context_manifest_id", P0RecordCode.CONTEXT_MANIFEST_RECORD),
        ),
        P0RecordCode.TOOL_CALL_RECORD: (
            ("argument_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
            ("context_manifest_id", P0RecordCode.CONTEXT_MANIFEST_RECORD),
            ("gate_decision_id", P0RecordCode.GATE_DECISION_RECORD),
            ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
            ("run_id", P0RecordCode.AGENT_RUN_RECORD),
            ("task_id", P0RecordCode.TASK_RECORD),
        ),
        P0RecordCode.OBSERVATION_RECORD: (
            ("source_request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
            ("source_run_id", P0RecordCode.AGENT_RUN_RECORD),
            ("source_task_id", P0RecordCode.TASK_RECORD),
            ("source_tool_call_id", P0RecordCode.TOOL_CALL_RECORD),
        ),
        P0RecordCode.CONTEXT_MANIFEST_RECORD: (
            ("model_visible_toolset_hash", P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT),
            ("observation_ref", P0RecordCode.OBSERVATION_RECORD),
            ("run_id", P0RecordCode.AGENT_RUN_RECORD),
            ("selected_message_ref", P0RecordCode.MESSAGE_RECORD),
            ("task_state_ref", P0RecordCode.TASK_RECORD),
        ),
        P0RecordCode.TRACE_EVENT_RECORD: (
            ("argument_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
            ("context_manifest_id", P0RecordCode.CONTEXT_MANIFEST_RECORD),
            ("input_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
            ("message_ref", P0RecordCode.MESSAGE_RECORD),
            ("model_visible_toolset_hash", P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT),
            ("observation_ref", P0RecordCode.OBSERVATION_RECORD),
            ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
            ("run_id", P0RecordCode.AGENT_RUN_RECORD),
            ("task_id", P0RecordCode.TASK_RECORD),
            ("tool_call_id", P0RecordCode.TOOL_CALL_RECORD),
        ),
        P0RecordCode.EVAL_RESULT_RECORD: (),
        P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD: (),
    }

    total_references = 0
    for case in _record_cases():
        envelope = encode_persistence_record(
            case.code,
            case.record,
            external_references=case.external_references,
            logical_children=case.logical_children,
        )
        actual = tuple(
            (reference.relation, reference.target_record_code)
            for reference in envelope.record_references
        )
        assert actual == expected[case.code]
        assert len(envelope.record_references) == len(set(envelope.record_references))
        total_references += len(envelope.record_references)
    assert total_references == 43


@pytest.mark.parametrize(
    ("mutation", "category"),
    (
        ("missing", P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH),
        ("duplicate", P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH),
        ("wrong_target", P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH),
        ("wrong_identity", P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH),
    ),
)
def test_external_reference_contract_fails_closed(
    mutation: str,
    category: P0PersistenceIntegrityCategory,
) -> None:
    case = next(
        item
        for item in _record_cases()
        if item.code is P0RecordCode.INPUT_BINDING_RECORD
    )
    reference = case.external_references[0]
    external_references: tuple[P0RecordReference, ...]
    if mutation == "missing":
        external_references = ()
    elif mutation == "duplicate":
        external_references = (reference, reference)
    elif mutation == "wrong_target":
        external_references = (
            reference.model_copy(
                update={"target_record_code": P0RecordCode.TASK_RECORD}
            ),
        )
    else:
        external_references = (
            reference.model_copy(
                update={
                    "target_logical_identity": _identity(
                        "task_id",
                        _uuid(5),
                    )
                }
            ),
        )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record,
            external_references=external_references,
        )
    assert raised.value.category is category


@pytest.mark.parametrize(
    ("record_code", "relation"),
    EXTERNAL_REFERENCE_CASES,
    ids=lambda value: value.value if isinstance(value, P0RecordCode) else value,
)
@pytest.mark.parametrize("invalid_value", (None, True, 7, "not-a-uuid"))
def test_external_reference_identity_value_is_strictly_validated(
    record_code: P0RecordCode,
    relation: str,
    invalid_value: object,
) -> None:
    case = _case(record_code)
    references = list(case.external_references)
    index = next(
        index
        for index, reference in enumerate(references)
        if reference.relation == relation
    )
    field_name = references[index].target_logical_identity[0][0]
    references[index] = references[index].model_copy(
        update={"target_logical_identity": ((field_name, invalid_value),)}
    )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record,
            external_references=tuple(references),
        )
    assert (
        raised.value.category is P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("record_code", "relation"),
    EXTERNAL_REFERENCE_CASES,
    ids=lambda value: value.value if isinstance(value, P0RecordCode) else value,
)
@pytest.mark.parametrize(
    ("mutation", "category"),
    (
        ("extra_identity", P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH),
        ("wrong_relation", P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH),
        ("wrong_target", P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH),
        ("unknown_target", P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH),
        ("missing", P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH),
        ("duplicate", P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH),
    ),
)
def test_all_external_reference_rules_fail_closed(
    record_code: P0RecordCode,
    relation: str,
    mutation: str,
    category: P0PersistenceIntegrityCategory,
) -> None:
    case = _case(record_code)
    references = list(case.external_references)
    index = next(
        index
        for index, reference in enumerate(references)
        if reference.relation == relation
    )
    reference = references[index]
    if mutation == "extra_identity":
        references[index] = reference.model_copy(
            update={
                "target_logical_identity": (
                    *reference.target_logical_identity,
                    ("unexpected", str(_uuid(70))),
                )
            }
        )
    elif mutation == "wrong_relation":
        references[index] = reference.model_copy(
            update={"relation": f"{relation}_wrong"}
        )
    elif mutation == "wrong_target":
        references[index] = reference.model_copy(
            update={"target_record_code": P0RecordCode.CONVERSATION_RECORD}
        )
    elif mutation == "unknown_target":
        references[index] = reference.model_copy(
            update={"target_record_code": "not_registered"}
        )
    elif mutation == "missing":
        references.pop(index)
    else:
        references.append(reference)

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record,
            external_references=tuple(references),
        )
    assert raised.value.category is category
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


def test_forged_external_reference_fails_bounded_or_is_canonicalized() -> None:
    case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    invalid = P0RecordReference.model_construct(
        relation="request_unit_id",
        target_record_code="not_registered",
        target_logical_identity=(("request_unit_id", str(_uuid(5))),),
    )
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record,
            external_references=(invalid,),
        )
    assert (
        raised.value.category is P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None

    mutable_identity = [["request_unit_id", str(_uuid(5))]]
    canonicalizable = P0RecordReference.model_construct(
        relation="request_unit_id",
        target_record_code=P0RecordCode.REQUEST_UNIT_RECORD,
        target_logical_identity=mutable_identity,
    )
    envelope = encode_persistence_record(
        case.code,
        case.record,
        external_references=(canonicalizable,),
    )
    mutable_identity[0][1] = str(_uuid(70))
    stored = envelope.record_references[0]
    assert stored.target_logical_identity == _identity(
        "request_unit_id",
        _uuid(5),
    )
    assert isinstance(stored.target_logical_identity, tuple)
    assert isinstance(stored.target_logical_identity[0], tuple)


def test_model_copy_reference_alias_is_broken_and_cycle_fails_bounded() -> None:
    case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    reference = case.external_references[0]
    mutable_identity = [["request_unit_id", str(_uuid(5))]]
    copied = reference.model_copy(update={"target_logical_identity": mutable_identity})
    envelope = encode_persistence_record(
        case.code,
        case.record,
        external_references=(copied,),
    )
    mutable_identity[0][1] = str(_uuid(70))
    assert envelope.record_references[0].target_logical_identity == _identity(
        "request_unit_id",
        _uuid(5),
    )

    cyclic_identity: list[object] = []
    cyclic_identity.append(cyclic_identity)
    forged = reference.model_copy(update={"target_logical_identity": cyclic_identity})
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record,
            external_references=(forged,),
        )
    assert (
        raised.value.category is P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("input_kind", ("str", "bytes", "mapping"))
def test_deep_json_input_fails_bounded(input_kind: str) -> None:
    if input_kind == "mapping":
        deep_mapping: dict[str, object] = {}
        cursor = deep_mapping
        for _ in range(20_000):
            nested: dict[str, object] = {}
            cursor["nested"] = nested
            cursor = nested
        raw: object = deep_mapping
    else:
        deep_json = "[" * 20_000 + "0" + "]" * 20_000
        raw = deep_json if input_kind == "str" else deep_json.encode()

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            raw,
            expected_record_code=P0RecordCode.MESSAGE_RECORD,
            correlation_ref=_uuid(99),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


def test_mapping_input_rejects_non_string_key_at_any_depth() -> None:
    case = _case(P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT)
    envelope = encode_persistence_record(case.code, case.record)
    raw = json.loads(envelope.model_dump_json())
    schema = raw["payload"]["data"]["provider_visible_tool_specs"][0]["input_schema"]
    schema[1] = {"type": "string"}
    schema["1"] = {"type": "integer"}

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            raw,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    )


@pytest.mark.parametrize(
    "key_case",
    (1, True, None, "collision"),
    ids=("int", "bool", "none", "int-string-collision"),
)
def test_envelope_input_rejects_nested_non_string_keys(
    key_case: object,
) -> None:
    case = _case(P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT)
    envelope = encode_persistence_record(case.code, case.record)
    data = json.loads(envelope.model_dump_json())["payload"]["data"]
    properties = data["provider_visible_tool_specs"][0]["input_schema"]["properties"]
    if key_case == "collision":
        properties[1] = {"type": "string"}
        properties["1"] = {"type": "integer"}
    else:
        properties[key_case] = {"type": "string"}

    original_tool = case.record.provider_visible_tool_specs[0]
    coerced_tool = type(original_tool).model_validate_json(
        json.dumps(
            data["provider_visible_tool_specs"][0],
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        strict=True,
    )
    forged_hash = compute_model_visible_toolset_hash((coerced_tool,))
    data["model_visible_toolset_hash"] = forged_hash
    forged = envelope.model_copy(
        update={
            "logical_identity": (("model_visible_toolset_hash", forged_hash),),
            "payload": envelope.payload.model_copy(
                update={"data": freeze_json_value(data)}
            ),
        }
    )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            forged,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    "surface",
    (
        "payload_uuid",
        "child_datetime",
        "logical_identity_mutable",
        "reference_identity_cycle",
    ),
)
def test_envelope_input_rejects_non_native_python_values(
    surface: str,
) -> None:
    code = (
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD
        if surface == "child_datetime"
        else P0RecordCode.MESSAGE_RECORD
    )
    case = _case(code)
    envelope = encode_persistence_record(
        case.code,
        case.record,
        logical_children=case.logical_children,
    )
    if surface == "payload_uuid":
        data = json.loads(envelope.model_dump_json())["payload"]["data"]
        data["message_id"] = _uuid(2)
        forged = envelope.model_copy(
            update={
                "payload": envelope.payload.model_copy(
                    update={"data": freeze_json_value(data)}
                )
            }
        )
    elif surface == "child_datetime":
        child = envelope.payload.logical_children[0]
        data = json.loads(child.model_dump_json())["data"]
        data["accepted_at"] = UTC_NOW
        forged_child = child.model_copy(update={"data": freeze_json_value(data)})
        forged = envelope.model_copy(
            update={
                "payload": envelope.payload.model_copy(
                    update={"logical_children": (forged_child,)}
                )
            }
        )
    elif surface == "logical_identity_mutable":
        forged = envelope.model_copy(
            update={
                "logical_identity": [
                    ["message_id", str(_uuid(2))],
                ]
            }
        )
    else:
        cyclic_identity: list[object] = []
        cyclic_identity.append(cyclic_identity)
        forged_reference = envelope.record_references[0].model_copy(
            update={"target_logical_identity": cyclic_identity}
        )
        forged = envelope.model_copy(update={"record_references": (forged_reference,)})

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            forged,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


def test_forged_envelope_serialization_failure_is_bounded() -> None:
    case = _case(P0RecordCode.MESSAGE_RECORD)
    envelope = encode_persistence_record(case.code, case.record)
    cyclic_data: dict[str, object] = {}
    cyclic_data["nested"] = cyclic_data
    forged = envelope.model_copy(
        update={"payload": envelope.payload.model_copy(update={"data": cyclic_data})}
    )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            forged,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("record_code", "updates"),
    (
        (
            P0RecordCode.REQUEST_UNIT_RECORD,
            {"evidence_binding_refs": (_uuid(60),)},
        ),
        (
            P0RecordCode.REQUEST_UNIT_RECORD,
            {"pending_action_ref": _uuid(61)},
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            {
                "evidence_refs_and_versions": (
                    VersionedRecordRef(
                        record_ref=_uuid(62),
                        version="evidence-v1",
                    ),
                )
            },
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            {"action_record_refs": (_uuid(63),)},
        ),
    ),
)
def test_first_slice_must_be_empty_fields_fail_closed(
    record_code: P0RecordCode,
    updates: dict[str, object],
) -> None:
    case = _case(record_code)
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record.model_copy(update=updates),
            external_references=case.external_references,
            logical_children=case.logical_children,
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
    )


def test_duplicate_source_projection_fails_closed() -> None:
    case = _case(P0RecordCode.REQUEST_UNIT_RECORD)
    duplicate = case.record.model_copy(
        update={"goal_source_refs": (_uuid(2), _uuid(2))}
    )
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(case.code, duplicate)
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
    )


def test_accepted_delta_is_locally_closed_against_parent() -> None:
    case = _case(P0RecordCode.REQUEST_UNDERSTANDING_RECORD)
    child = case.logical_children[0]

    invalid_cases = (
        ((), P0PersistenceIntegrityCategory.CHILD_MISMATCH),
        (
            (child.model_copy(update={"message_ref": _uuid(70)}),),
            P0PersistenceIntegrityCategory.CHILD_MISMATCH,
        ),
        (
            (child.model_copy(update={"candidate_ref": _uuid(71)}),),
            P0PersistenceIntegrityCategory.CHILD_MISMATCH,
        ),
        (
            (child.model_copy(update={"input_binding_refs": (_uuid(8), _uuid(8))}),),
            P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH,
        ),
    )
    for children, expected_category in invalid_cases:
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            encode_persistence_record(
                case.code,
                case.record,
                logical_children=children,
            )
        assert raised.value.category is expected_category


def test_tool_attempt_children_exactly_cover_attempt_count() -> None:
    case = _case(P0RecordCode.TOOL_CALL_RECORD)
    child = case.logical_children[0]
    invalid_children = (
        (),
        (child.model_copy(update={"tool_call_id": _uuid(70)}),),
        (child, child),
        (child.model_copy(update={"attempt_no": 2}),),
    )
    for children in invalid_children:
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            encode_persistence_record(
                case.code,
                case.record,
                logical_children=children,
            )
        assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


def test_task_transition_is_locally_valid_but_remains_graph_required() -> None:
    case = _case(P0RecordCode.TASK_RECORD)
    child = case.logical_children[0]
    envelope = encode_persistence_record(
        case.code,
        case.record,
        logical_children=(child,),
    )
    assert (
        P0_LOGICAL_CHILD_SPECS[
            P0LogicalChildCode.TASK_STATE_TRANSITION
        ].closure_strategy.value
        == "GRAPH_REQUIRED"
    )
    assert not hasattr(envelope, "owner_graph_valid")
    assert not hasattr(envelope, "recovery_ready")
    decoded = decode_persistence_record(
        envelope,
        expected_record_code=case.code,
        correlation_ref=_uuid(99),
    )
    for forbidden_claim in (
        "auth_scope",
        "authorization_scope",
        "owner_graph_valid",
        "recovery_ready",
    ):
        assert not hasattr(decoded, forbidden_claim)

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            case.code,
            case.record,
            logical_children=(child.model_copy(update={"task_id": _uuid(70)}),),
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


@pytest.mark.parametrize(
    "record_code",
    (
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        P0RecordCode.TASK_RECORD,
        P0RecordCode.TOOL_CALL_RECORD,
    ),
)
@pytest.mark.parametrize("tamper", ("metadata", "code", "parent", "identity", "data"))
def test_all_three_child_payloads_reject_each_tamper_surface(
    record_code: P0RecordCode,
    tamper: str,
) -> None:
    case = _case(record_code)
    envelope = encode_persistence_record(
        case.code,
        case.record,
        logical_children=case.logical_children,
    )
    raw = json.loads(envelope.model_dump_json())
    child = raw["payload"]["logical_children"][0]
    if tamper == "metadata":
        child["parent_record_code"] = P0RecordCode.MESSAGE_RECORD.value
    elif tamper == "code":
        child["child_code"] = "not_registered_child"
    elif tamper == "parent":
        child["parent_logical_identity"][0][1] = str(_uuid(70))
    elif tamper == "identity":
        child["logical_identity"][0][1] = str(_uuid(70))
    else:
        identity_field = child["logical_identity"][0][0]
        child["data"][identity_field] = None

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            raw,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


def test_outer_and_inner_metadata_fail_with_bounded_categories() -> None:
    case = _case(P0RecordCode.MESSAGE_RECORD)
    envelope = encode_persistence_record(case.code, case.record)
    base = json.loads(envelope.model_dump_json())

    mutations: tuple[tuple[dict[str, object], P0PersistenceIntegrityCategory], ...] = ()
    missing_code = json.loads(envelope.model_dump_json())
    missing_code.pop("record_code")
    unknown_code = json.loads(envelope.model_dump_json())
    unknown_code["record_code"] = "not_registered"
    missing_version = json.loads(envelope.model_dump_json())
    missing_version.pop("record_schema_version")
    unknown_version = json.loads(envelope.model_dump_json())
    unknown_version["record_schema_version"] = "unknown.p0.v99"
    wrong_known_version = json.loads(envelope.model_dump_json())
    wrong_known_version["record_schema_version"] = "task_record.p0.v1"
    inner_code = json.loads(envelope.model_dump_json())
    inner_code["payload"]["record_code"] = "task_record"
    inner_version = json.loads(envelope.model_dump_json())
    inner_version["payload"]["record_schema_version"] = "task_record.p0.v1"
    mutations = (
        (missing_code, P0PersistenceIntegrityCategory.MISSING_RECORD_CODE),
        (unknown_code, P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE),
        (
            missing_version,
            P0PersistenceIntegrityCategory.MISSING_RECORD_SCHEMA_VERSION,
        ),
        (
            unknown_version,
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
        (
            wrong_known_version,
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH,
        ),
        (
            inner_code,
            P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH,
        ),
        (
            inner_version,
            P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH,
        ),
    )
    assert base["record_code"] == case.code.value

    for raw, expected_category in mutations:
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            decode_persistence_record(
                raw,
                expected_record_code=case.code,
                correlation_ref=_uuid(99),
            )
        assert raised.value.category is expected_category

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            envelope,
            expected_record_code=P0RecordCode.TASK_RECORD,
            correlation_ref=_uuid(99),
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.RECORD_CODE_MISMATCH


@pytest.mark.parametrize(
    ("tamper", "category"),
    (
        ("identity", P0PersistenceIntegrityCategory.IDENTITY_MISMATCH),
        ("owner", P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH),
        ("link", P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH),
        ("payload", P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED),
        ("child", P0PersistenceIntegrityCategory.CHILD_MISMATCH),
    ),
)
def test_decode_recomputes_all_metadata_and_rejects_tampering(
    tamper: str,
    category: P0PersistenceIntegrityCategory,
) -> None:
    code = (
        P0RecordCode.CONVERSATION_RECORD
        if tamper == "owner"
        else P0RecordCode.REQUEST_UNDERSTANDING_RECORD
        if tamper == "child"
        else P0RecordCode.MESSAGE_RECORD
    )
    case = _case(code)
    envelope = encode_persistence_record(
        case.code,
        case.record,
        external_references=case.external_references,
        logical_children=case.logical_children,
    )
    raw = json.loads(envelope.model_dump_json())
    if tamper == "identity":
        raw["logical_identity"][0][1] = str(_uuid(70))
    elif tamper == "owner":
        raw["direct_owner_customer_id"] = "customer-B"
    elif tamper == "link":
        raw["record_references"][0]["target_logical_identity"][0][1] = str(_uuid(70))
    elif tamper == "payload":
        raw["payload"]["data"]["message_id"] = 70
    else:
        raw["payload"]["logical_children"][0]["parent_logical_identity"][0][1] = str(
            _uuid(70)
        )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            raw,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert raised.value.category is category


def test_decode_rejects_python_values_inside_mapping_input() -> None:
    case = _case(P0RecordCode.MESSAGE_RECORD)
    envelope = encode_persistence_record(case.code, case.record)
    raw = json.loads(envelope.model_dump_json())
    raw["payload"]["data"]["message_id"] = _uuid(2)

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            raw,
            expected_record_code=case.code,
            correlation_ref=_uuid(99),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    )


@pytest.mark.parametrize("input_kind", ("envelope", "mapping", "str", "bytes"))
def test_decode_accepts_only_approved_json_input_forms(input_kind: str) -> None:
    case = _case(P0RecordCode.MESSAGE_RECORD)
    envelope = encode_persistence_record(case.code, case.record)
    inputs: dict[str, object] = {
        "envelope": envelope,
        "mapping": json.loads(envelope.model_dump_json()),
        "str": envelope.model_dump_json(),
        "bytes": envelope.model_dump_json().encode("utf-8"),
    }
    decoded = decode_persistence_record(
        inputs[input_kind],
        expected_record_code=case.code,
        correlation_ref=_uuid(99),
    )
    assert decoded.source_record == case.record


def test_exact_source_model_mirrors_and_specialized_version_are_enforced() -> None:
    conversation = _case(P0RecordCode.CONVERSATION_RECORD)
    message = _case(P0RecordCode.MESSAGE_RECORD)
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            P0RecordCode.CONVERSATION_RECORD,
            message.record,
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            conversation.code,
            conversation.record.model_copy(
                update={"schema_version": "application-records-v1"}
            ),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
    )

    toolset = _case(P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT)
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            toolset.code,
            toolset.record.model_copy(
                update={"artifact_schema_version": "wrong-toolset-version"}
            ),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.SPECIALIZED_VERSION_MISMATCH
    )


@pytest.mark.parametrize(
    "record_code",
    (
        P0RecordCode.CONVERSATION_RECORD,
        P0RecordCode.MESSAGE_RECORD,
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
        P0RecordCode.RUN_TASK_LINK_RECORD,
        P0RecordCode.EVAL_RESULT_RECORD,
        P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD,
    ),
)
def test_all_seven_record_schema_mirrors_fail_closed(
    record_code: P0RecordCode,
) -> None:
    case = _case(record_code)
    forged = case.record.model_copy(update={"schema_version": "wrong-record-version"})
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(case.code, forged)
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
    )


def test_source_model_subclass_is_not_an_exact_contract_match() -> None:
    class MessageRecordSubclass(MessageRecord):
        pass

    case = _case(P0RecordCode.MESSAGE_RECORD)
    subclass_record = MessageRecordSubclass(**case.record.model_dump())
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(case.code, subclass_record)
    assert raised.value.category is P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH


def test_integrity_error_is_bounded_opaque_and_discards_unsafe_context() -> None:
    case = _case(P0RecordCode.MESSAGE_RECORD)
    envelope = encode_persistence_record(case.code, case.record)
    raw = json.loads(envelope.model_dump_json())
    secret_markers = (
        "Token VERY_SECRET",
        "customer-A",
        "Cookie=p0-session-alice",
        "Prompt: private",
    )
    raw["logical_identity"][0][1] = "|".join(secret_markers)
    correlation_ref = _uuid(99)

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            raw,
            expected_record_code=case.code,
            correlation_ref=correlation_ref,
        )
    error = raised.value
    assert error.category is P0PersistenceIntegrityCategory.IDENTITY_MISMATCH
    assert error.correlation_ref == correlation_ref
    projection = " ".join((str(error), repr(error), repr(error.args)))
    assert all(marker not in projection for marker in secret_markers)
    assert error.__context__ is None
    assert error.__cause__ is None


@pytest.mark.parametrize("case", _record_cases(), ids=lambda case: case.code.value)
def test_all_17_records_strict_json_round_trip(case: RecordCase) -> None:
    envelope = encode_persistence_record(
        case.code,
        case.record,
        external_references=case.external_references,
        logical_children=case.logical_children,
    )

    assert isinstance(envelope, P0PersistenceEnvelope)
    assert envelope.record_code is case.code
    assert envelope.record_schema_version == f"{case.code.value}.p0.v1"
    raw_json = envelope.model_dump_json()
    assert json.loads(raw_json)["record_code"] == case.code.value

    decoded = decode_persistence_record(
        raw_json,
        expected_record_code=case.code,
        correlation_ref=_uuid(99),
    )
    assert isinstance(decoded, DecodedP0PersistenceRecord)
    assert decoded.record_code is case.code
    assert decoded.record_schema_version == envelope.record_schema_version
    assert decoded.source_record == case.record
    assert decoded.logical_children == case.logical_children
