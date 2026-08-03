import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
    ApplyTaskTransitionCommand,
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
    SaveInputBindingCommand,
    SaveObservationCommand,
    ToolRetryRecoveryDecisionRecordV2,
    TrustedOwnerScope,
)
from mini_agent.core.common import freeze_json_value
from mini_agent.core.identity import CustomerContext
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
    CandidateValidationDecision,
    InputBinding,
    InputValidationStatus,
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
request_understanding_record|contextualization.resolved_reference_candidates[].source_ref|TOP_LEVEL_P0_REFERENCE|contextualization_resolved_source_ref|message_record|0|-|0
request_understanding_record|contextualization.source_message_refs[]|TOP_LEVEL_P0_REFERENCE|contextualization_source_message_ref|message_record|1|-|1
request_understanding_record|task_delta_candidates[].input_candidates[].source_ref|TOP_LEVEL_P0_REFERENCE|task_delta_input_source_ref|message_record|0|-|0
request_understanding_record|accepted_delta_refs[]|LOGICAL_CHILD_CORRELATION|-|-|0|-|1
request_understanding_record|candidate_validation[].candidate_ref|PARENT_LOCAL_CORRELATION|-|-|0|-|1
request_understanding_record|next_move_candidate_ref?|PAYLOAD_CORRELATION|-|-|0|1|0
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
accepted_task_delta|task_id|CHILD_TOP_LEVEL_P0_REFERENCE|accepted_delta_task_id|task_record|1|1|0
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


def test_relation_aware_commands_supply_all_five_external_codec_relations() -> None:
    binding_case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    binding_command = SaveInputBindingCommand(
        record=binding_case.record,
        request_unit_id=_uuid(5),
    )
    binding_references = (
        _reference(
            "request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
            "request_unit_id",
            binding_command.request_unit_id,
        ),
    )
    binding_envelope = encode_persistence_record(
        P0RecordCode.INPUT_BINDING_RECORD,
        binding_command.record,
        external_references=binding_references,
    )

    observation_case = _case(P0RecordCode.OBSERVATION_RECORD)
    source_case = _case(P0RecordCode.TOOL_CALL_RECORD)
    source_values = source_case.record.model_dump()
    source_values.update(
        {
            "status": ToolCallStatus.SUCCEEDED,
            "finished_at": UTC_NOW + timedelta(minutes=1),
            "result_ref": _uuid(80),
        }
    )
    source_tool_call = ToolCallRecord(**source_values)
    observation_command = SaveObservationCommand(
        owner_scope=TrustedOwnerScope.from_customer_context(
            CustomerContext(
                subject_ref="subject-A",
                customer_id="customer-A",
                auth_scopes=frozenset({"orders:read"}),
                authenticated_at=UTC_NOW,
                session_ref_hash="safe-session-A",
            )
        ),
        observation_record=observation_case.record,
        source_tool_call_record=source_tool_call,
    )
    observation_references = (
        _reference(
            "source_tool_call_id",
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_id",
            observation_command.source_tool_call_record.tool_call_id,
        ),
        _reference(
            "source_run_id",
            P0RecordCode.AGENT_RUN_RECORD,
            "run_id",
            observation_command.source_tool_call_record.run_id,
        ),
        _reference(
            "source_task_id",
            P0RecordCode.TASK_RECORD,
            "task_id",
            observation_command.source_tool_call_record.task_id,
        ),
        _reference(
            "source_request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
            "request_unit_id",
            observation_command.source_tool_call_record.request_unit_id,
        ),
    )
    observation_envelope = encode_persistence_record(
        P0RecordCode.OBSERVATION_RECORD,
        observation_command.observation_record,
        external_references=observation_references,
    )

    external = (
        *binding_envelope.record_references,
        *observation_envelope.record_references,
    )
    external_relations = tuple(
        reference
        for reference in external
        if (reference.relation, reference.target_record_code)
        in {
            ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
            ("source_tool_call_id", P0RecordCode.TOOL_CALL_RECORD),
            ("source_run_id", P0RecordCode.AGENT_RUN_RECORD),
            ("source_task_id", P0RecordCode.TASK_RECORD),
            ("source_request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
        }
    )
    assert {
        (reference.relation, reference.target_record_code)
        for reference in external_relations
    } == {
        ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
        ("source_tool_call_id", P0RecordCode.TOOL_CALL_RECORD),
        ("source_run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("source_task_id", P0RecordCode.TASK_RECORD),
        ("source_request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
    }
    assert len(external_relations) == 5
    assert all(
        reference.target_logical_identity[0][1]
        != str(observation_command.source_tool_call_record.result_ref)
        for reference in observation_references
    )
    assert all(
        reference.target_logical_identity[0][1]
        != str(observation_command.observation_record.observation_id)
        for reference in observation_references
    )


def test_task_transition_command_is_sufficient_for_the_generic_codec() -> None:
    task_case = _case(P0RecordCode.TASK_RECORD)
    request_unit_case = _case(P0RecordCode.REQUEST_UNIT_RECORD)
    transition = task_case.logical_children[0]
    next_task = task_case.record
    next_request_unit = request_unit_case.record
    expected_task = TaskRecord(
        **{
            **next_task.model_dump(),
            "status": transition.from_status,
            "state_version": transition.base_state_version,
            "updated_at": UTC_NOW,
        }
    )
    expected_request_unit = RequestUnitRecord(
        **{
            **next_request_unit.model_dump(),
            "status": transition.from_status,
            "state_version": transition.base_state_version,
            "observation_refs": (),
            "updated_at": UTC_NOW,
        }
    )
    transition_command = ApplyTaskTransitionCommand(
        expected_task_record=expected_task,
        next_task_record=next_task,
        expected_request_unit_record=expected_request_unit,
        next_request_unit_record=next_request_unit,
        task_state_transition=transition,
    )
    task_envelope = encode_persistence_record(
        P0RecordCode.TASK_RECORD,
        transition_command.next_task_record,
        logical_children=(transition_command.task_state_transition,),
    )
    request_unit_envelope = encode_persistence_record(
        P0RecordCode.REQUEST_UNIT_RECORD,
        transition_command.next_request_unit_record,
    )
    assert (
        task_envelope.payload.logical_children[0].child_code
        is P0LogicalChildCode.TASK_STATE_TRANSITION
    )
    assert request_unit_envelope.logical_identity == _identity(
        "request_unit_id",
        transition_command.next_request_unit_record.request_unit_id,
    )


def test_command_derived_external_relations_still_fail_closed_when_swapped() -> None:
    observation_case = _case(P0RecordCode.OBSERVATION_RECORD)
    references = list(observation_case.external_references)
    run_index = next(
        index
        for index, reference in enumerate(references)
        if reference.relation == "source_run_id"
    )
    task_index = next(
        index
        for index, reference in enumerate(references)
        if reference.relation == "source_task_id"
    )
    references[run_index] = references[run_index].model_copy(
        update={
            "target_logical_identity": references[task_index].target_logical_identity
        }
    )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            observation_case.code,
            observation_case.record,
            external_references=tuple(references),
        )
    assert (
        raised.value.category is P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    )


def test_registry_is_exact_immutable_and_closed() -> None:
    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG
    non_ru = _non_ru_registry()
    ru_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD

    phase1_codes = tuple(P0RecordCode)[:17]
    assert tuple(code.value for code in phase1_codes) == EXPECTED_RECORD_CODES
    assert isinstance(P0_PERSISTENCE_REGISTRY, MappingProxyType)
    assert tuple(P0_PERSISTENCE_REGISTRY) == phase1_codes
    assert len(P0_PERSISTENCE_REGISTRY) == 17
    assert len({spec.source_model for spec in P0_PERSISTENCE_REGISTRY.values()}) == 17
    assert {
        spec.record_schema_version for spec in P0_PERSISTENCE_REGISTRY.values()
    } == {
        (
            RU_V2_SCHEMA_VERSION
            if code is ru_code
            else f"{code.value}.p0.v1"
        )
        for code in phase1_codes
    }
    assert P0_PERSISTENCE_REGISTRY[ru_code] is catalog[
        (ru_code, RU_V2_SCHEMA_VERSION)
    ]

    assert isinstance(non_ru, MappingProxyType)
    assert tuple(non_ru) == tuple(
        code for code in phase1_codes if code is not ru_code
    )
    assert len(non_ru) == 16
    for code in non_ru:
        v1_spec = catalog[(code, f"{code.value}.p0.v1")]
        assert non_ru[code] is v1_spec
        assert P0_PERSISTENCE_REGISTRY[code] is v1_spec

    with pytest.raises(TypeError):
        P0_PERSISTENCE_REGISTRY[P0RecordCode.CONVERSATION_RECORD] = (
            P0_PERSISTENCE_REGISTRY[P0RecordCode.MESSAGE_RECORD]
        )
    with pytest.raises(TypeError):
        non_ru[P0RecordCode.CONVERSATION_RECORD] = non_ru[
            P0RecordCode.MESSAGE_RECORD
        ]

    assert isinstance(P0_LOGICAL_CHILD_SPECS, MappingProxyType)
    assert tuple(P0_LOGICAL_CHILD_SPECS) == (
        P0LogicalChildCode.ACCEPTED_TASK_DELTA,
        P0LogicalChildCode.TASK_STATE_TRANSITION,
        P0LogicalChildCode.TOOL_ATTEMPT_RECORD,
    )
    assert len(P0_LOGICAL_CHILD_SPECS) == 3
    assert (
        P0LogicalChildCode.TOOL_RETRY_RECOVERY_DECISION_RECORD
        not in P0_LOGICAL_CHILD_SPECS
    )
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

    assert len(top_level_rules) == 70
    assert len(child_rules) == 8
    assert len(reference_rules) == 49
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
    assert total_references == 40


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
        P0RecordCode.TOOL_CALL_RECORD
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
        data["started_at"] = UTC_NOW
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
        P0RecordCode.TASK_RECORD,
        P0RecordCode.TOOL_CALL_RECORD,
    ),
)
@pytest.mark.parametrize("tamper", ("metadata", "code", "parent", "identity", "data"))
def test_all_generic_child_payloads_reject_each_tamper_surface(
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
        else P0RecordCode.TASK_RECORD
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
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
        P0RecordCode.RUN_TASK_LINK_RECORD,
        P0RecordCode.EVAL_RESULT_RECORD,
        P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD,
    ),
)
def test_all_six_generic_record_schema_mirrors_fail_closed(
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
def test_all_16_generic_records_strict_json_round_trip(case: RecordCase) -> None:
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


# Request Understanding v2 remains an exact-version-only codec contract.
import ast
import inspect
import warnings
from collections import Counter
from pathlib import Path

from mini_agent.core.request_understanding import (
    InputSourceKind,
    ReferenceSourceKindV2,
)
from mini_agent.core.task_state import (
    AcceptedAddGoalTaskDeltaV3,
    AcceptedSupplyInputTaskDeltaV3,
    AcceptedTaskDeltaV2,
    CandidateRejectionReasonCode,
    CandidateValidationRecordV2,
    DurableCycle2AddGoalTaskDeltaCandidateV3,
    DurableCycle2ContinuationTaskDeltaCandidateV3,
    DurableCycle2InputCandidateV3,
    DurableInputCandidateV2,
    DurablePhase1AddGoalTaskDeltaCandidateV3,
    DurableQueryContextualizationCandidateV2,
    DurableResolvedReferenceCandidateV2,
    DurableTaskDeltaCandidateV2,
    RequestUnderstandingRecordV2,
    RequestUnderstandingRecordV3,
)


RU_V2_SCHEMA_VERSION = "request_understanding_record.p0.v2"
RU_V3_SCHEMA_VERSION = "request_understanding_record.p0.v3"


def _non_ru_registry() -> MappingProxyType:
    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG
    return MappingProxyType(
        {
            code: catalog[(code, f"{code.value}.p0.v1")]
            for code in tuple(P0RecordCode)[:17]
            if code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
        }
    )


@dataclass(frozen=True, slots=True)
class RequestUnderstandingV2Case:
    record: RequestUnderstandingRecordV2
    children: tuple[AcceptedTaskDeltaV2, ...]


@dataclass(frozen=True, slots=True)
class RequestUnderstandingV3Case:
    record: RequestUnderstandingRecordV3
    children: tuple[
        AcceptedAddGoalTaskDeltaV3 | AcceptedSupplyInputTaskDeltaV3,
        ...,
    ]


def _durable_resolved_reference_v2(
    *,
    source_ref: UUID,
    order_id: str,
    seed: str,
) -> DurableResolvedReferenceCandidateV2:
    return DurableResolvedReferenceCandidateV2(
        name="order_id",
        candidate_value=order_id,
        source_kind=ReferenceSourceKindV2.RECENT_MESSAGE,
        source_ref=source_ref,
        source_span_start=0,
        source_span_end_exclusive=len(order_id),
        source_quote_sha256=seed * 64,
        confidence=0.9,
    )


def _durable_task_candidate_v2(
    *,
    candidate_id: UUID,
    message_ref: UUID,
    order_id: str,
    seed: str,
) -> DurableTaskDeltaCandidateV2:
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
                source_ref=message_ref,
                source_span_start=0,
                source_span_end_exclusive=len(order_id),
                source_quote_sha256=seed * 64,
                confidence=0.9,
            ),
        ),
        confidence=0.9,
    )


def _accepted_task_delta_v2(
    *,
    accepted_delta_id: UUID,
    candidate_ref: UUID,
    message_ref: UUID,
    input_binding_ref: UUID,
    task_id: UUID,
    base_version: int | None,
    result_version: int,
    order_id: str,
) -> AcceptedTaskDeltaV2:
    return AcceptedTaskDeltaV2(
        accepted_delta_id=accepted_delta_id,
        candidate_ref=candidate_ref,
        message_ref=message_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text=f"查询订单 {order_id}",
        input_binding_refs=(input_binding_ref,),
        accepted_at=UTC_NOW,
        task_id=task_id,
        base_task_state_version=base_version,
        result_task_state_version=result_version,
    )


def _request_understanding_v2_case(
    shape: str,
) -> RequestUnderstandingV2Case:
    message_ref = _uuid(202)
    recent_message_ref = _uuid(203)
    candidate_ids = (_uuid(211), _uuid(212), _uuid(213))
    accepted_ids = (_uuid(221), _uuid(222), _uuid(223))
    binding_ids = (_uuid(231), _uuid(232), _uuid(233))
    task_ids = (_uuid(241), _uuid(242))
    candidates = tuple(
        _durable_task_candidate_v2(
            candidate_id=candidate_id,
            message_ref=message_ref,
            order_id=f"O-{1001 + index}",
            seed=chr(ord("a") + index),
        )
        for index, candidate_id in enumerate(candidate_ids)
    )
    decisions = (
        CandidateValidationRecordV2(
            candidate_ref=candidate_ids[0],
            decision=CandidateValidationDecision.ACCEPT,
        ),
        CandidateValidationRecordV2(
            candidate_ref=candidate_ids[1],
            decision=CandidateValidationDecision.REJECT,
            reason_code=CandidateRejectionReasonCode.REFERENCE_UNRESOLVED,
        ),
        CandidateValidationRecordV2(
            candidate_ref=candidate_ids[2],
            decision=CandidateValidationDecision.ACCEPT,
        ),
    )
    children = (
        _accepted_task_delta_v2(
            accepted_delta_id=accepted_ids[0],
            candidate_ref=candidate_ids[0],
            message_ref=message_ref,
            input_binding_ref=binding_ids[0],
            task_id=task_ids[0],
            base_version=None,
            result_version=1,
            order_id="O-1001",
        ),
        _accepted_task_delta_v2(
            accepted_delta_id=accepted_ids[2],
            candidate_ref=candidate_ids[2],
            message_ref=message_ref,
            input_binding_ref=binding_ids[2],
            task_id=task_ids[0],
            base_version=1,
            result_version=2,
            order_id="O-1003",
        ),
    )

    if shape == "zero":
        selected_candidates: tuple[DurableTaskDeltaCandidateV2, ...] = ()
        selected_decisions: tuple[CandidateValidationRecordV2, ...] = ()
        selected_children: tuple[AcceptedTaskDeltaV2, ...] = ()
    elif shape == "all_reject":
        selected_candidates = candidates[:2]
        selected_decisions = tuple(
            CandidateValidationRecordV2(
                candidate_ref=candidate.candidate_id,
                decision=CandidateValidationDecision.REJECT,
                reason_code=CandidateRejectionReasonCode.REFERENCE_UNRESOLVED,
            )
            for candidate in selected_candidates
        )
        selected_children = ()
    elif shape == "partial":
        selected_candidates = candidates[:2]
        selected_decisions = decisions[:2]
        selected_children = children[:1]
    elif shape == "multi":
        # Candidate order is authoritative.  Decision order, accepted-ref order
        # and physical child order are intentionally different.
        selected_candidates = candidates
        selected_decisions = (decisions[2], decisions[0], decisions[1])
        selected_children = (children[1], children[0])
    else:
        raise AssertionError(shape)

    accepted_refs_by_candidate = {
        child.candidate_ref: child.accepted_delta_id for child in selected_children
    }
    accepted_refs = tuple(
        accepted_refs_by_candidate[candidate.candidate_id]
        for candidate in reversed(selected_candidates)
        if candidate.candidate_id in accepted_refs_by_candidate
    )
    record = RequestUnderstandingRecordV2(
        request_understanding_record_id=_uuid(201),
        run_id=_uuid(3),
        message_ref=message_ref,
        schema_version=RU_V2_SCHEMA_VERSION,
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-thin-v2",
        contextualization=DurableQueryContextualizationCandidateV2(
            text="结合当前消息与上一条消息查询订单",
            resolved_reference_candidates=(
                _durable_resolved_reference_v2(
                    source_ref=recent_message_ref,
                    order_id="O-1000",
                    seed="d",
                ),
                _durable_resolved_reference_v2(
                    source_ref=recent_message_ref,
                    order_id="O-1000",
                    seed="d",
                ),
            ),
            uncertainties=(),
            source_message_refs=(message_ref, recent_message_ref),
        ),
        task_delta_candidates=selected_candidates,
        candidate_validation=selected_decisions,
        accepted_delta_refs=accepted_refs,
        created_at=UTC_NOW,
    )
    return RequestUnderstandingV2Case(record=record, children=selected_children)


def _encode_v2(
    case: RequestUnderstandingV2Case,
) -> P0PersistenceEnvelope:
    return persistence_module.encode_persistence_record_versioned(
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        RU_V2_SCHEMA_VERSION,
        case.record,
        logical_children=case.children,
    )


def _decode_v2(
    envelope: P0PersistenceEnvelope | dict[str, object] | str | bytes,
) -> DecodedP0PersistenceRecord:
    return persistence_module.decode_persistence_record_versioned(
        envelope,
        expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        expected_schema_version=RU_V2_SCHEMA_VERSION,
        correlation_ref=_uuid(299),
    )


def _phase1_v3_case(shape: str) -> RequestUnderstandingV3Case:
    source = _request_understanding_v2_case(shape)
    candidates = tuple(
        DurablePhase1AddGoalTaskDeltaCandidateV3(**candidate.model_dump())
        for candidate in source.record.task_delta_candidates
    )
    child_by_candidate = {
        child.candidate_ref: AcceptedAddGoalTaskDeltaV3(**child.model_dump())
        for child in source.children
    }
    children = tuple(
        child_by_candidate[candidate.candidate_id]
        for candidate in candidates
        if candidate.candidate_id in child_by_candidate
    )
    return RequestUnderstandingV3Case(
        record=RequestUnderstandingRecordV3(
            request_understanding_record_id=(
                source.record.request_understanding_record_id
            ),
            run_id=source.record.run_id,
            message_ref=source.record.message_ref,
            record_schema_version=RU_V3_SCHEMA_VERSION,
            model_input_schema_version=(
                source.record.model_input_schema_version
            ),
            model_output_schema_version=(
                source.record.model_output_schema_version
            ),
            contextualization=source.record.contextualization,
            task_delta_candidates=candidates,
            candidate_validation=source.record.candidate_validation,
            accepted_delta_refs=source.record.accepted_delta_refs,
            proposed_base_task_state_version=(
                source.record.proposed_base_task_state_version
            ),
            validated_task_state_version=(
                source.record.validated_task_state_version
            ),
            next_move_candidate_ref=source.record.next_move_candidate_ref,
            created_at=source.record.created_at,
        ),
        children=children,
    )


def _cycle2_initial_v3_case() -> RequestUnderstandingV3Case:
    context = _request_understanding_v2_case("zero").record.contextualization
    message_ref = context.source_message_refs[0]
    candidate_ref = _uuid(320)
    accepted_delta_ref = _uuid(321)
    task_id = _uuid(322)
    binding_ref = _uuid(323)
    candidate = DurableCycle2AddGoalTaskDeltaCandidateV3(
        candidate_id=candidate_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_patch="查找轻量跑鞋订单",
        input_candidates=(
            DurableCycle2InputCandidateV3(
                name="product_description",
                normalized_candidate_value="轻量 跑鞋",
                authority=InputAuthority.USER_CLAIM,
                source_kind=InputSourceKind.CURRENT_MESSAGE,
                source_ref=message_ref,
                source_span_start=2,
                source_span_end_exclusive=7,
                source_quote_sha256="e" * 64,
                confidence=0.99,
            ),
        ),
        confidence=0.98,
    )
    record = RequestUnderstandingRecordV3(
        request_understanding_record_id=_uuid(324),
        run_id=_uuid(3),
        message_ref=message_ref,
        record_schema_version=RU_V3_SCHEMA_VERSION,
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-cycle2-initial.p0.v1",
        contextualization=context,
        task_delta_candidates=(candidate,),
        candidate_validation=(
            CandidateValidationRecordV2(
                candidate_ref=candidate_ref,
                decision=CandidateValidationDecision.ACCEPT,
            ),
        ),
        accepted_delta_refs=(accepted_delta_ref,),
        validated_task_state_version=1,
        next_move_candidate_ref=_uuid(325),
        created_at=UTC_NOW,
    )
    child = AcceptedAddGoalTaskDeltaV3(
        accepted_delta_id=accepted_delta_ref,
        candidate_ref=candidate_ref,
        message_ref=message_ref,
        operation=TaskDeltaOperation.ADD_GOAL,
        goal_text=candidate.goal_patch,
        input_binding_refs=(binding_ref,),
        accepted_at=UTC_NOW,
        task_id=task_id,
        base_task_state_version=None,
        result_task_state_version=1,
    )
    return RequestUnderstandingV3Case(record=record, children=(child,))


def _cycle2_continuation_v3_case(
    *,
    accepted: bool = True,
) -> RequestUnderstandingV3Case:
    context = _request_understanding_v2_case("zero").record.contextualization
    message_ref = context.source_message_refs[0]
    candidate_ref = _uuid(330)
    accepted_delta_ref = _uuid(331)
    candidate = DurableCycle2ContinuationTaskDeltaCandidateV3(
        candidate_id=candidate_ref,
        operation=TaskDeltaOperation.SUPPLY_INPUT,
        target_task_alias="task-current",
        target_request_unit_alias="unit-current",
        input_candidates=(
            DurableCycle2InputCandidateV3(
                name="order_id",
                normalized_candidate_value="O-1001",
                authority=InputAuthority.USER_CLAIM,
                source_kind=InputSourceKind.CURRENT_MESSAGE,
                source_ref=message_ref,
                source_span_start=4,
                source_span_end_exclusive=10,
                source_quote_sha256="f" * 64,
                confidence=0.99,
            ),
            DurableCycle2InputCandidateV3(
                name="shipment_not_received",
                normalized_candidate_value=True,
                authority=InputAuthority.USER_CLAIM,
                source_kind=InputSourceKind.CURRENT_MESSAGE,
                source_ref=message_ref,
                source_span_start=12,
                source_span_end_exclusive=16,
                source_quote_sha256="a" * 64,
                confidence=0.98,
            ),
        ),
        confidence=0.97,
    )
    validation = CandidateValidationRecordV2(
        candidate_ref=candidate_ref,
        decision=(
            CandidateValidationDecision.ACCEPT
            if accepted
            else CandidateValidationDecision.REJECT
        ),
        reason_code=(
            None
            if accepted
            else CandidateRejectionReasonCode.INPUT_VALUE_INVALID
        ),
    )
    record = RequestUnderstandingRecordV3(
        request_understanding_record_id=_uuid(332),
        run_id=_uuid(3),
        message_ref=message_ref,
        record_schema_version=RU_V3_SCHEMA_VERSION,
        model_input_schema_version="e2e01-thin-v1",
        model_output_schema_version="e2e01-cycle2-continuation.p0.v2",
        contextualization=context,
        task_delta_candidates=(candidate,),
        candidate_validation=(validation,),
        accepted_delta_refs=((accepted_delta_ref,) if accepted else ()),
        created_at=UTC_NOW,
    )
    children: tuple[AcceptedSupplyInputTaskDeltaV3, ...] = ()
    if accepted:
        children = (
            AcceptedSupplyInputTaskDeltaV3(
                accepted_delta_id=accepted_delta_ref,
                candidate_ref=candidate_ref,
                message_ref=message_ref,
                operation=TaskDeltaOperation.SUPPLY_INPUT,
                task_id=_uuid(333),
                target_request_unit_id=_uuid(334),
                input_binding_refs=(_uuid(335), _uuid(336)),
                accepted_at=UTC_NOW,
                base_task_state_version=3,
                result_task_state_version=4,
            ),
        )
    return RequestUnderstandingV3Case(record=record, children=children)


def _encode_v3(case: RequestUnderstandingV3Case) -> P0PersistenceEnvelope:
    return persistence_module.encode_persistence_record_versioned(
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        RU_V3_SCHEMA_VERSION,
        case.record,
        logical_children=case.children,
    )


def _decode_v3(
    envelope: P0PersistenceEnvelope | dict[str, object] | str | bytes,
) -> DecodedP0PersistenceRecord:
    return persistence_module.decode_persistence_record_versioned(
        envelope,
        expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        expected_schema_version=RU_V3_SCHEMA_VERSION,
        correlation_ref=_uuid(399),
    )


def test_ru_codec_surface_is_current_only_and_v1_absent() -> None:
    source_path = Path(inspect.getsourcefile(persistence_module) or "")
    source_tree = ast.parse(source_path.read_text())
    test_tree = ast.parse(Path(__file__).read_text())
    removed_v1_types = {
        "AcceptedTaskDelta",
        "CandidateValidationRecord",
        "RequestUnderstandingRecord",
    }

    def folded_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = folded_string(node.left)
            right = folded_string(node.right)
            return left + right if left is not None and right is not None else None
        return None

    for tree in (source_tree, test_tree):
        assert not any(
            (
                isinstance(node, ast.Import)
                and any(
                    alias.name == "mini_agent.core.task_state"
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and node.module == "mini_agent.core"
                and any(alias.name == "task_state" for alias in node.names)
            )
            for node in ast.walk(tree)
        )
        imported_v1_types = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "mini_agent.core.task_state"
            for alias in node.names
            if alias.name in removed_v1_types
        }
        assert not imported_v1_types
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module == "mini_agent.core.task_state"
            and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(tree)
        )
        assert not {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id in removed_v1_types
        }
        assert not {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in {
                *removed_v1_types,
                "getmodule",
                "task_state",
            }
        }
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and folded_string(node.args[1]) in removed_v1_types
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, ast.Subscript)
            and folded_string(node.slice) in removed_v1_types
            for node in ast.walk(tree)
        )
        assert not {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id
            in {
                "__import__",
                "globals",
                "locals",
                "vars",
            }
        }
        assert not {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr
            in {
                "import_module",
            }
        }
        assert not any(
            (
                isinstance(node, ast.Import)
                and any(
                    alias.name.split(".", maxsplit=1)[0]
                    in {"builtins", "importlib", "sys"}
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.split(".", maxsplit=1)[0]
                in {"builtins", "importlib", "sys"}
            )
            for node in ast.walk(tree)
        )

    assert not {
        node.id
        for node in ast.walk(source_tree)
        if isinstance(node, ast.Name)
        and node.id in {
            *removed_v1_types,
            "_P0_V1_PERSISTENCE_REGISTRY",
        }
    }
    assert "REQUEST_UNDERSTANDING_RECORD" not in inspect.getsource(
        persistence_module._child_payloads
    )

    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG
    ru_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    ru_v1_version = "request_understanding_record.p0.v1"
    assert isinstance(catalog, MappingProxyType)
    assert len(catalog) == 29
    assert len(P0_PERSISTENCE_REGISTRY) == 17
    assert tuple(P0_PERSISTENCE_REGISTRY) == tuple(P0RecordCode)[:17]
    assert {
        (code, spec.record_schema_version)
        for code, spec in P0_PERSISTENCE_REGISTRY.items()
    } < set(catalog)
    assert all(
        catalog[(code, spec.record_schema_version)] is spec
        for code, spec in P0_PERSISTENCE_REGISTRY.items()
    )
    assert (ru_code, ru_v1_version) not in catalog
    assert (ru_code, RU_V3_SCHEMA_VERSION) in catalog
    assert (
        P0_PERSISTENCE_REGISTRY[ru_code].record_schema_version
        == RU_V2_SCHEMA_VERSION
    )
    assert (
        P0_LOGICAL_CHILD_SPECS[
            P0LogicalChildCode.ACCEPTED_TASK_DELTA
        ].source_model
        is AcceptedTaskDeltaV2
    )

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
    assert (
        len(top_level_rules),
        len(child_rules),
        len(reference_rules),
    ) == (70, 8, 49)

    case = _request_understanding_v2_case("partial")
    envelope = _encode_v2(case)

    with pytest.raises(P0PersistenceIntegrityError) as generic_encode:
        encode_persistence_record(
            ru_code,
            case.record,
            logical_children=case.children,
        )
    assert (
        generic_encode.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )

    with pytest.raises(P0PersistenceIntegrityError) as generic_decode:
        decode_persistence_record(
            envelope.model_dump_json(),
            expected_record_code=ru_code,
            correlation_ref=_uuid(299),
        )
    assert (
        generic_decode.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )

    with pytest.raises(P0PersistenceIntegrityError) as versioned_v1:
        persistence_module.encode_persistence_record_versioned(
            ru_code,
            ru_v1_version,
            case.record,
            logical_children=case.children,
        )
    assert (
        versioned_v1.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )

    raw_v1_metadata = json.loads(envelope.model_dump_json())
    raw_v1_metadata["record_schema_version"] = ru_v1_version
    raw_v1_metadata["payload"]["record_schema_version"] = ru_v1_version
    with pytest.raises(P0PersistenceIntegrityError) as raw_v1:
        persistence_module.decode_persistence_record_versioned(
            raw_v1_metadata,
            expected_record_code=ru_code,
            expected_schema_version=ru_v1_version,
            correlation_ref=_uuid(299),
        )
    assert (
        raw_v1.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )


def test_version_catalog_is_exact_immutable_and_current_only() -> None:
    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG
    non_ru = _non_ru_registry()
    ru_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD

    assert isinstance(catalog, MappingProxyType)
    assert len(catalog) == 29
    assert {code for code, _ in catalog} == set(P0RecordCode)
    counts = Counter(code for code, _ in catalog)
    assert {count for count in counts.values()} == {1, 2}
    assert {
        code for code, count in counts.items() if count == 2
    } == {
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        P0RecordCode.INPUT_BINDING_RECORD,
        P0RecordCode.GATE_DECISION_RECORD,
        P0RecordCode.TOOL_CALL_RECORD,
        P0RecordCode.AGENT_RUN_RECORD,
        P0RecordCode.RUN_TASK_LINK_RECORD,
        P0RecordCode.TRACE_EVENT_RECORD,
    }
    for code, spec in non_ru.items():
        assert catalog[(code, f"{code.value}.p0.v1")] is spec
        assert P0_PERSISTENCE_REGISTRY[code] is spec
    assert (ru_code, f"{ru_code.value}.p0.v1") not in catalog

    v2_spec = catalog[
        (ru_code, RU_V2_SCHEMA_VERSION)
    ]
    v3_spec = catalog[(ru_code, RU_V3_SCHEMA_VERSION)]
    assert v2_spec.source_model is RequestUnderstandingRecordV2
    assert v2_spec.identity_fields == ("request_understanding_record_id",)
    assert v2_spec.version_mirror_field == "schema_version"
    assert v2_spec.allowed_child_codes == (
        P0LogicalChildCode.ACCEPTED_TASK_DELTA,
    )
    assert v3_spec.source_model is RequestUnderstandingRecordV3
    assert v3_spec.identity_fields == ("request_understanding_record_id",)
    assert v3_spec.version_mirror_field is None
    assert v3_spec.allowed_child_codes == (
        P0LogicalChildCode.ACCEPTED_TASK_DELTA,
    )
    with pytest.raises(TypeError):
        catalog[
            (P0RecordCode.MESSAGE_RECORD, "message_record.p0.v2")
        ] = v2_spec

    assert len(P0_PERSISTENCE_REGISTRY) == 17
    assert P0_PERSISTENCE_REGISTRY[ru_code] is v2_spec
    assert P0_PERSISTENCE_REGISTRY[ru_code].source_model is RequestUnderstandingRecordV2
    assert len(P0_LOGICAL_CHILD_SPECS) == 3
    assert (
        P0_LOGICAL_CHILD_SPECS[
            P0LogicalChildCode.ACCEPTED_TASK_DELTA
        ].source_model
        is AcceptedTaskDeltaV2
    )


def test_ru_v3_codec_is_explicitly_staged_without_active_registry_switch() -> None:
    ru_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG
    child_catalog = persistence_module.P0_LOGICAL_CHILD_SCHEMA_VERSION_CATALOG

    assert P0_PERSISTENCE_REGISTRY[ru_code] is catalog[
        (ru_code, RU_V2_SCHEMA_VERSION)
    ]
    assert catalog[(ru_code, RU_V3_SCHEMA_VERSION)].source_model is (
        RequestUnderstandingRecordV3
    )
    child_spec = child_catalog[
        (
            ru_code,
            RU_V3_SCHEMA_VERSION,
            P0LogicalChildCode.ACCEPTED_TASK_DELTA,
        )
    ]
    assert child_spec.source_model == (
        AcceptedAddGoalTaskDeltaV3,
        AcceptedSupplyInputTaskDeltaV3,
    )
    assert child_spec.closure_strategy.value == "LOCAL_CLOSED"

    case = _phase1_v3_case("partial")
    with pytest.raises(P0PersistenceIntegrityError) as direct:
        encode_persistence_record(
            ru_code,
            case.record,
            logical_children=case.children,
        )
    assert (
        direct.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )


@pytest.mark.parametrize(
    "case",
    (
        _phase1_v3_case("zero"),
        _phase1_v3_case("all_reject"),
        _phase1_v3_case("partial"),
        _phase1_v3_case("multi"),
        _cycle2_initial_v3_case(),
        _cycle2_continuation_v3_case(),
        _cycle2_continuation_v3_case(accepted=False),
    ),
    ids=(
        "phase1-zero",
        "phase1-all-reject",
        "phase1-partial",
        "phase1-multi",
        "cycle2-initial",
        "cycle2-continuation-dual",
        "cycle2-continuation-rejected",
    ),
)
def test_ru_v3_explicit_codec_round_trips_exact_closed_branches(
    case: RequestUnderstandingV3Case,
) -> None:
    envelope = _encode_v3(case)
    decoded = _decode_v3(envelope.model_dump_json())

    assert envelope.record_schema_version == RU_V3_SCHEMA_VERSION
    assert envelope.payload.record_schema_version == RU_V3_SCHEMA_VERSION
    assert decoded.source_record == case.record
    assert decoded.logical_children == case.children
    assert tuple(
        child.logical_identity
        for child in envelope.payload.logical_children
    ) == tuple(
        (("accepted_delta_id", str(child.accepted_delta_id)),)
        for child in case.children
    )
    assert tuple(
        child.data["operation"]
        for child in envelope.payload.logical_children
    ) == tuple(child.operation.value for child in case.children)

    for expected, payload in zip(
        case.children,
        envelope.payload.logical_children,
        strict=True,
    ):
        assert tuple(payload.data["input_binding_refs"]) == tuple(
            str(binding_ref) for binding_ref in expected.input_binding_refs
        )


def test_ru_v3_dual_binding_child_preserves_order_and_reference_closure() -> None:
    case = _cycle2_continuation_v3_case()
    envelope = _encode_v3(case)
    child = case.children[0]
    payload = envelope.payload.logical_children[0]

    assert type(child) is AcceptedSupplyInputTaskDeltaV3
    assert tuple(payload.data["input_binding_refs"]) == tuple(
        str(binding_ref) for binding_ref in child.input_binding_refs
    )
    assert {
        (
            reference.relation,
            reference.target_record_code,
            reference.target_logical_identity,
        )
        for reference in envelope.record_references
        if reference.relation in {"input_binding_ref", "accepted_delta_task_id"}
    } == {
        (
            "input_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
            (("binding_id", str(binding_ref)),),
        )
        for binding_ref in child.input_binding_refs
    } | {
        (
            "accepted_delta_task_id",
            P0RecordCode.TASK_RECORD,
            (("task_id", str(child.task_id)),),
        )
    }


def test_ru_v3_codec_rejects_cross_version_children_and_reordered_closure() -> None:
    v2 = _request_understanding_v2_case("partial")
    v3 = _phase1_v3_case("partial")
    with pytest.raises(P0PersistenceIntegrityError) as v2_child_under_v3:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V3_SCHEMA_VERSION,
            v3.record,
            logical_children=v2.children,
        )
    assert (
        v2_child_under_v3.value.category
        is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    )
    with pytest.raises(P0PersistenceIntegrityError) as v3_child_under_v2:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V2_SCHEMA_VERSION,
            v2.record,
            logical_children=v3.children,
        )
    assert (
        v3_child_under_v2.value.category
        is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    )

    multi = _phase1_v3_case("multi")
    with pytest.raises(P0PersistenceIntegrityError) as reordered:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V3_SCHEMA_VERSION,
            multi.record,
            logical_children=tuple(reversed(multi.children)),
        )
    assert (
        reordered.value.category
        is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    )


def test_ru_v3_decode_rejects_discriminator_and_version_mutation() -> None:
    envelope = _encode_v3(_cycle2_continuation_v3_case()).model_dump(
        mode="json"
    )
    operation_mutation = json.loads(json.dumps(envelope))
    operation_mutation["payload"]["logical_children"][0]["data"][
        "operation"
    ] = "ADD_GOAL"
    with pytest.raises(P0PersistenceIntegrityError) as wrong_branch:
        _decode_v3(operation_mutation)
    assert (
        wrong_branch.value.category
        is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    )

    inner_version_mutation = json.loads(json.dumps(envelope))
    inner_version_mutation["payload"]["data"]["record_schema_version"] = (
        RU_V2_SCHEMA_VERSION
    )
    with pytest.raises(P0PersistenceIntegrityError) as wrong_inner_version:
        _decode_v3(inner_version_mutation)
    assert wrong_inner_version.value.category in {
        P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
        P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH,
    }

    with pytest.raises(P0PersistenceIntegrityError) as wrong_expected_pair:
        persistence_module.decode_persistence_record_versioned(
            envelope,
            expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            expected_schema_version=RU_V2_SCHEMA_VERSION,
            correlation_ref=_uuid(399),
        )
    assert (
        wrong_expected_pair.value.category
        is P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
    )


@pytest.mark.parametrize(
    ("record", "children"),
    (
        (
            _phase1_v3_case("partial").record,
            (),
        ),
        (
            _phase1_v3_case("partial").record,
            _phase1_v3_case("partial").children * 2,
        ),
        (
            _phase1_v3_case("multi").record,
            _phase1_v3_case("multi").children[:1],
        ),
        (
            _phase1_v3_case("multi").record,
            (
                _phase1_v3_case("multi").children[0],
                _phase1_v3_case("multi").children[1].model_copy(
                    update={
                        "accepted_delta_id": (
                            _phase1_v3_case("multi")
                            .children[0]
                            .accepted_delta_id
                        )
                    }
                ),
            ),
        ),
        (
            _phase1_v3_case("multi").record,
            (
                _phase1_v3_case("multi").children[0],
                _phase1_v3_case("multi").children[1].model_copy(
                    update={
                        "task_id": (
                            _phase1_v3_case("multi").children[0].task_id
                        ),
                        "base_task_state_version": 2,
                        "result_task_state_version": 3,
                    }
                ),
            ),
        ),
    ),
    ids=(
        "missing-accepted-child",
        "extra-duplicate-child",
        "partial-multi-closure",
        "colliding-accepted-identity",
        "broken-task-chain",
    ),
)
def test_ru_v3_encode_rejects_incomplete_or_conflicting_closure(
    record: RequestUnderstandingRecordV3,
    children: tuple[object, ...],
) -> None:
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V3_SCHEMA_VERSION,
            record,
            logical_children=children,
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


@pytest.mark.parametrize(
    "mutation",
    ("missing-child", "extra-child", "provenance-source"),
)
def test_ru_v3_decode_rejects_closure_and_provenance_mutation(
    mutation: str,
) -> None:
    raw = _encode_v3(_cycle2_continuation_v3_case()).model_dump(mode="json")
    if mutation == "missing-child":
        raw["payload"]["logical_children"] = []
    elif mutation == "extra-child":
        raw["payload"]["logical_children"].append(
            raw["payload"]["logical_children"][0]
        )
    else:
        raw["payload"]["data"]["task_delta_candidates"][0][
            "input_candidates"
        ][0]["source_ref"] = str(_uuid(398))

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        _decode_v3(raw)
    assert raised.value.category in {
        P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
        P0PersistenceIntegrityCategory.CHILD_MISMATCH,
    }


def test_ru_v3_version_alias_never_falls_back_to_known_pair() -> None:
    case = _phase1_v3_case("partial")
    envelope = _encode_v3(case)
    alias = f"{RU_V3_SCHEMA_VERSION} "
    with pytest.raises(P0PersistenceIntegrityError) as encoded:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            alias,
            case.record,
            logical_children=case.children,
        )
    assert (
        encoded.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )
    with pytest.raises(P0PersistenceIntegrityError) as decoded:
        persistence_module.decode_persistence_record_versioned(
            envelope,
            expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            expected_schema_version=alias,
            correlation_ref=_uuid(399),
        )
    assert (
        decoded.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )


def test_versioned_codec_signatures_require_explicit_exact_pair() -> None:
    encode = inspect.signature(
        persistence_module.encode_persistence_record_versioned
    ).parameters
    assert tuple(encode) == (
        "record_code",
        "schema_version",
        "record",
        "external_references",
        "logical_children",
    )
    assert encode["schema_version"].default is inspect.Parameter.empty
    assert encode["external_references"].kind is inspect.Parameter.KEYWORD_ONLY
    assert encode["logical_children"].kind is inspect.Parameter.KEYWORD_ONLY

    decode = inspect.signature(
        persistence_module.decode_persistence_record_versioned
    ).parameters
    assert tuple(decode) == (
        "envelope",
        "expected_record_code",
        "expected_schema_version",
        "correlation_ref",
    )
    assert all(
        decode[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in (
            "expected_record_code",
            "expected_schema_version",
            "correlation_ref",
        )
    )
    assert decode["expected_schema_version"].default is inspect.Parameter.empty

    case = _case(P0RecordCode.MESSAGE_RECORD)
    with pytest.raises(TypeError):
        persistence_module.encode_persistence_record_versioned(
            case.code,
            record=case.record,
        )
    envelope = encode_persistence_record(case.code, case.record)
    with pytest.raises(TypeError):
        persistence_module.decode_persistence_record_versioned(
            envelope,
            expected_record_code=case.code,
            correlation_ref=_uuid(299),
        )


@pytest.mark.parametrize("case", _record_cases(), ids=lambda case: case.code.value)
def test_all_16_non_ru_pairs_have_generic_semantic_parity(
    case: RecordCase,
) -> None:
    version = _non_ru_registry()[case.code].record_schema_version
    versioned = persistence_module.encode_persistence_record_versioned(
        case.code,
        version,
        case.record,
        external_references=case.external_references,
        logical_children=case.logical_children,
    )
    generic = encode_persistence_record(
        case.code,
        case.record,
        external_references=case.external_references,
        logical_children=case.logical_children,
    )
    assert versioned == generic

    decoded = persistence_module.decode_persistence_record_versioned(
        versioned.model_dump_json(),
        expected_record_code=case.code,
        expected_schema_version=version,
        correlation_ref=_uuid(299),
    )
    generic_decoded = decode_persistence_record(
        generic.model_dump_json(),
        expected_record_code=case.code,
        correlation_ref=_uuid(299),
    )
    assert decoded == generic_decoded


def test_ru_v2_projection_specs_are_exact_8_and_4() -> None:
    top = persistence_module._REQUEST_UNDERSTANDING_V2_PROJECTIONS
    child = persistence_module._ACCEPTED_TASK_DELTA_V2_PROJECTIONS
    signatures = tuple(
        (
            rule.field_label,
            rule.classification.value,
            rule.relation,
            (
                rule.target_record_code.value
                if rule.target_record_code is not None
                else None
            ),
            rule.minimum,
            rule.maximum,
            rule.unique,
        )
        for rule in top
    )
    assert signatures == (
        (
            "run_id",
            "TOP_LEVEL_P0_REFERENCE",
            "run_id",
            "agent_run_record",
            1,
            1,
            False,
        ),
        (
            "message_ref",
            "TOP_LEVEL_P0_REFERENCE",
            "message_ref",
            "message_record",
            1,
            1,
            False,
        ),
        (
            "contextualization.resolved_reference_candidates[].source_ref",
            "TOP_LEVEL_P0_REFERENCE",
            "contextualization_resolved_source_ref",
            "message_record",
            0,
            None,
            False,
        ),
        (
            "contextualization.source_message_refs[]",
            "TOP_LEVEL_P0_REFERENCE",
            "contextualization_source_message_ref",
            "message_record",
            1,
            None,
            True,
        ),
        (
            "task_delta_candidates[].input_candidates[].source_ref",
            "TOP_LEVEL_P0_REFERENCE",
            "task_delta_input_source_ref",
            "message_record",
            0,
            None,
            False,
        ),
        (
            "accepted_delta_refs[]",
            "LOGICAL_CHILD_CORRELATION",
            None,
            None,
            0,
            None,
            True,
        ),
        (
            "candidate_validation[].candidate_ref",
            "PARENT_LOCAL_CORRELATION",
            None,
            None,
            0,
            None,
            True,
        ),
        (
            "next_move_candidate_ref?",
            "PAYLOAD_CORRELATION",
            None,
            None,
            0,
            1,
            False,
        ),
    )
    assert len(child) == 4
    assert tuple(
        (
            rule.field_label,
            rule.classification.value,
            rule.relation,
            (
                rule.target_record_code.value
                if rule.target_record_code is not None
                else None
            ),
        )
        for rule in child
    ) == (
        ("candidate_ref", "PARENT_LOCAL_CORRELATION", None, None),
        ("message_ref", "PARENT_FIELD_EQUALITY", None, None),
        (
            "input_binding_refs[]",
            "CHILD_TOP_LEVEL_P0_REFERENCE",
            "input_binding_ref",
            "input_binding_record",
        ),
        (
            "task_id",
            "CHILD_TOP_LEVEL_P0_REFERENCE",
            "accepted_delta_task_id",
            "task_record",
        ),
    )


@pytest.mark.parametrize("shape", ("zero", "all_reject", "partial", "multi"))
@pytest.mark.parametrize("input_kind", ("envelope", "mapping", "str", "bytes"))
def test_ru_v2_round_trip_closes_all_supported_shapes_and_json_forms(
    shape: str,
    input_kind: str,
) -> None:
    case = _request_understanding_v2_case(shape)
    envelope = _encode_v2(case)
    assert envelope.record_schema_version == RU_V2_SCHEMA_VERSION
    assert envelope.logical_identity == _identity(
        "request_understanding_record_id",
        case.record.request_understanding_record_id,
    )
    forms: dict[str, object] = {
        "envelope": envelope,
        "mapping": json.loads(envelope.model_dump_json()),
        "str": envelope.model_dump_json(),
        "bytes": envelope.model_dump_json().encode("utf-8"),
    }
    decoded = _decode_v2(forms[input_kind])
    assert type(decoded.source_record) is RequestUnderstandingRecordV2
    assert decoded.source_record == case.record
    assert all(type(child) is AcceptedTaskDeltaV2 for child in decoded.logical_children)
    assert {
        child.accepted_delta_id for child in decoded.logical_children
    } == {child.accepted_delta_id for child in case.children}


def test_ru_v2_references_are_exact_sorted_and_duplicate_paths_collapse() -> None:
    case = _request_understanding_v2_case("multi")
    envelope = _encode_v2(case)
    actual = tuple(
        (
            reference.relation,
            reference.target_record_code,
            reference.target_logical_identity,
        )
        for reference in envelope.record_references
    )
    assert actual == tuple(sorted(actual, key=lambda item: (item[0], item[1], str(item[2]))))
    assert len(actual) == len(set(actual))
    assert Counter(item[0] for item in actual) == Counter(
        {
            "accepted_delta_task_id": 1,
            "contextualization_resolved_source_ref": 1,
            "contextualization_source_message_ref": 2,
            "input_binding_ref": 2,
            "message_ref": 1,
            "run_id": 1,
            "task_delta_input_source_ref": 1,
        }
    )
    assert all(
        relation
        not in {
            "model_input_schema_version",
            "model_output_schema_version",
            "proposed_base_task_state_version",
            "validated_task_state_version",
        }
        for relation, _, _ in actual
    )


@pytest.mark.parametrize(
    ("pair", "record_kind", "category"),
    (
        (
            (P0RecordCode.REQUEST_UNDERSTANDING_RECORD, RU_V2_SCHEMA_VERSION),
            "message",
            P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH,
        ),
        (
            (
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                "request_understanding_record.p0.v1",
            ),
            "v2",
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
        (
            (P0RecordCode.MESSAGE_RECORD, RU_V2_SCHEMA_VERSION),
            "v2",
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH,
        ),
        (
            (
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                "request_understanding_record.p0.v99",
            ),
            "v2",
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
    ),
)
def test_versioned_encode_exact_pair_never_infers_or_falls_back(
    pair: tuple[P0RecordCode, str],
    record_kind: str,
    category: P0PersistenceIntegrityCategory,
) -> None:
    message_case = _case(P0RecordCode.MESSAGE_RECORD)
    v2_case = _request_understanding_v2_case("partial")
    record = message_case.record if record_kind == "message" else v2_case.record
    children = (
        message_case.logical_children
        if record_kind == "message"
        else v2_case.children
    )
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.encode_persistence_record_versioned(
            pair[0],
            pair[1],
            record,
            logical_children=children,
        )
    assert raised.value.category is category


def test_versioned_decode_rejects_cross_version_and_metadata_confusion() -> None:
    v2_envelope = _encode_v2(_request_understanding_v2_case("partial"))

    cases: tuple[
        tuple[object, str, P0PersistenceIntegrityCategory],
        ...,
    ] = (
        (
            v2_envelope,
            "request_understanding_record.p0.v1",
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
        (
            v2_envelope,
            "request_understanding_record.p0.v99",
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
    )
    for envelope, expected_version, category in cases:
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            persistence_module.decode_persistence_record_versioned(
                envelope,
                expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                expected_schema_version=expected_version,
                correlation_ref=_uuid(299),
            )
        assert raised.value.category is category

    outer = json.loads(v2_envelope.model_dump_json())
    outer["record_schema_version"] = "request_understanding_record.p0.v1"
    inner = json.loads(v2_envelope.model_dump_json())
    inner["payload"][
        "record_schema_version"
    ] = "request_understanding_record.p0.v1"
    source = json.loads(v2_envelope.model_dump_json())
    source["payload"]["data"][
        "schema_version"
    ] = "request_understanding_record.p0.v1"
    for raw, category in (
        (
            outer,
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
        (inner, P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH),
        (source, P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED),
    ):
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            _decode_v2(raw)
        assert raised.value.category is category


def test_current_switch_requires_exact_ru_v2_codec() -> None:
    ru_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG

    assert P0_PERSISTENCE_REGISTRY[ru_code] is catalog[
        (ru_code, RU_V2_SCHEMA_VERSION)
    ]
    assert (ru_code, f"{ru_code.value}.p0.v1") not in catalog

    case = _request_understanding_v2_case("partial")
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        encode_persistence_record(
            ru_code,
            case.record,
            logical_children=case.children,
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )

    envelope = _encode_v2(case)
    assert envelope.record_schema_version == RU_V2_SCHEMA_VERSION
    assert _decode_v2(envelope).source_record == case.record
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        decode_persistence_record(
            envelope,
            expected_record_code=ru_code,
            correlation_ref=_uuid(299),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )
    assert len(P0_PERSISTENCE_REGISTRY) == 17


@pytest.mark.parametrize(
    "tamper",
    (
        "missing_child",
        "extra_child",
        "wrong_candidate",
        "wrong_message",
        "wrong_time",
        "wrong_operation",
        "duplicate_binding",
        "duplicate_accepted_id",
    ),
)
def test_ru_v2_encode_revalidates_complete_child_closure(tamper: str) -> None:
    case = _request_understanding_v2_case("partial")
    record = case.record
    child = case.children[0]
    children: tuple[AcceptedTaskDeltaV2, ...] = case.children
    if tamper == "missing_child":
        children = ()
    elif tamper == "extra_child":
        children = (child, child)
    elif tamper == "wrong_candidate":
        children = (child.model_copy(update={"candidate_ref": _uuid(290)}),)
    elif tamper == "wrong_message":
        children = (child.model_copy(update={"message_ref": _uuid(290)}),)
    elif tamper == "wrong_time":
        children = (
            child.model_copy(update={"accepted_at": UTC_NOW + timedelta(seconds=1)}),
        )
    elif tamper == "wrong_operation":
        children = (child.model_copy(update={"operation": "DELETE_GOAL"}),)
    elif tamper == "duplicate_binding":
        children = (
            child.model_copy(
                update={
                    "input_binding_refs": (
                        child.input_binding_refs[0],
                        child.input_binding_refs[0],
                    )
                }
            ),
        )
    else:
        other_candidate = record.task_delta_candidates[1]
        accept_other = CandidateValidationRecordV2(
            candidate_ref=other_candidate.candidate_id,
            decision=CandidateValidationDecision.ACCEPT,
        )
        record = record.model_copy(
            update={
                "candidate_validation": (
                    record.candidate_validation[0],
                    accept_other,
                ),
                "accepted_delta_refs": (
                    child.accepted_delta_id,
                    child.accepted_delta_id,
                ),
            }
        )
        children = (
            child,
            child.model_copy(
                update={"candidate_ref": other_candidate.candidate_id}
            ),
        )

    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V2_SCHEMA_VERSION,
            record,
            logical_children=children,
        )
    assert raised.value.category in {
        P0PersistenceIntegrityCategory.CHILD_MISMATCH,
        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH,
        P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
    }


@pytest.mark.parametrize(
    ("tamper", "base", "result"),
    (
        ("fork", None, 1),
        ("gap", 2, 3),
        ("rollback", 1, 1),
    ),
)
def test_ru_v2_task_chain_rejects_fork_gap_and_rollback(
    tamper: str,
    base: int | None,
    result: int,
) -> None:
    case = _request_understanding_v2_case("multi")
    children_by_candidate = {
        child.candidate_ref: child for child in case.children
    }
    later_candidate = case.record.task_delta_candidates[2]
    later = children_by_candidate[later_candidate.candidate_id]
    forged = later.model_copy(
        update={
            "base_task_state_version": base,
            "result_task_state_version": result,
        }
    )
    children = tuple(
        forged if child.candidate_ref == later.candidate_ref else child
        for child in case.children
    )
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V2_SCHEMA_VERSION,
            case.record,
            logical_children=children,
        )
    assert (
        raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    ), tamper


def test_ru_v2_task_chain_uses_candidate_order_not_child_or_ref_order() -> None:
    case = _request_understanding_v2_case("multi")
    envelope = _encode_v2(case)
    assert tuple(
        child.logical_identity for child in envelope.payload.logical_children
    ) == tuple(
        sorted(
            (
                _identity("accepted_delta_id", child.accepted_delta_id)
                for child in case.children
            ),
            key=str,
        )
    )

    first, later = sorted(
        case.children,
        key=lambda child: (
            next(
                index
                for index, candidate in enumerate(
                    case.record.task_delta_candidates
                )
                if candidate.candidate_id == child.candidate_ref
            )
        ),
    )
    reordered = (
        first.model_copy(update={"candidate_ref": later.candidate_ref}),
        later.model_copy(update={"candidate_ref": first.candidate_ref}),
    )
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V2_SCHEMA_VERSION,
            case.record,
            logical_children=reordered,
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


@pytest.mark.parametrize(
    "surface",
    (
        "source_extra",
        "source_trusted",
        "nested_private",
        "child_extra",
        "constructed_span",
        "constructed_hash",
        "constructed_enum",
    ),
)
def test_ru_v2_rejects_undeclared_private_and_constructed_state_without_leak(
    surface: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "RAW-QUOTE-Token-VERY-SECRET"
    case = _request_understanding_v2_case("partial")
    record = case.record
    children = case.children
    if surface == "source_extra":
        record = record.model_copy(update={"unexpected_field": marker})
    elif surface == "source_trusted":
        record = record.model_copy(update={"customer_id": marker})
    elif surface == "nested_private":
        context = record.contextualization.model_copy(
            update={"_private_quote": marker}
        )
        record = record.model_copy(update={"contextualization": context})
    elif surface == "child_extra":
        children = (
            children[0].model_copy(update={"owner_customer_id": marker}),
        )
    else:
        resolved = record.contextualization.resolved_reference_candidates[0]
        values = resolved.model_dump()
        if surface == "constructed_span":
            values["source_span_end_exclusive"] = values["source_span_start"]
        elif surface == "constructed_hash":
            values["source_quote_sha256"] = marker
        else:
            values["source_kind"] = "NOT_A_SOURCE_KIND"
        forged_resolved = DurableResolvedReferenceCandidateV2.model_construct(
            **values
        )
        context = record.contextualization.model_copy(
            update={
                "resolved_reference_candidates": (
                    forged_resolved,
                    *record.contextualization.resolved_reference_candidates[1:],
                )
            }
        )
        record = record.model_copy(update={"contextualization": context})

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            persistence_module.encode_persistence_record_versioned(
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                RU_V2_SCHEMA_VERSION,
                record,
                logical_children=children,
            )
    assert raised.value.category in {
        P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
        P0PersistenceIntegrityCategory.CHILD_MISMATCH,
    }
    assert caught_warnings == []
    captured = capsys.readouterr()
    projection = " ".join(
        (
            captured.out,
            captured.err,
            str(raised.value),
            repr(raised.value),
            repr(raised.value.args),
        )
    )
    assert marker not in projection
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


def test_ru_v2_requires_exact_runtime_source_and_child_types() -> None:
    case = _request_understanding_v2_case("partial")

    class RequestUnderstandingRecordV2Subclass(RequestUnderstandingRecordV2):
        pass

    class AcceptedTaskDeltaV2Subclass(AcceptedTaskDeltaV2):
        pass

    invalid: tuple[tuple[object, tuple[object, ...]], ...] = (
        (case.record.model_dump(), case.children),
        (
            RequestUnderstandingRecordV2Subclass(**case.record.model_dump()),
            case.children,
        ),
        (case.record, (case.children[0].model_dump(),)),
        (
            case.record,
            (AcceptedTaskDeltaV2Subclass(**case.children[0].model_dump()),),
        ),
    )
    for record, children in invalid:
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            persistence_module.encode_persistence_record_versioned(
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                RU_V2_SCHEMA_VERSION,
                record,
                logical_children=children,
            )
        assert raised.value.category in {
            P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH,
            P0PersistenceIntegrityCategory.CHILD_MISMATCH,
        }


def test_ru_v2_decode_recomputes_identity_links_children_and_bounds_raw_error() -> None:
    envelope = _encode_v2(_request_understanding_v2_case("partial"))
    marker = "Token VERY_SECRET Prompt private Cookie=p0-session"
    mutations: list[tuple[dict[str, object], P0PersistenceIntegrityCategory]] = []
    identity = json.loads(envelope.model_dump_json())
    identity["logical_identity"][0][1] = marker
    mutations.append(
        (identity, P0PersistenceIntegrityCategory.IDENTITY_MISMATCH)
    )
    link = json.loads(envelope.model_dump_json())
    link["record_references"][0]["relation"] = marker
    mutations.append(
        (link, P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
    )
    child_parent = json.loads(envelope.model_dump_json())
    child_parent["payload"]["logical_children"][0][
        "parent_logical_identity"
    ][0][1] = marker
    mutations.append(
        (child_parent, P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    )
    child_data = json.loads(envelope.model_dump_json())
    child_data["payload"]["logical_children"][0]["data"]["message_ref"] = str(
        _uuid(290)
    )
    mutations.append(
        (child_data, P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    )

    for raw, category in mutations:
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            _decode_v2(raw)
        assert raised.value.category is category
        projection = " ".join(
            (str(raised.value), repr(raised.value), repr(raised.value.args))
        )
        assert marker not in projection
        assert raised.value.__context__ is None
        assert raised.value.__cause__ is None


def test_ru_v2_source_collection_duplicates_fail_but_reference_duplicates_collapse() -> None:
    case = _request_understanding_v2_case("zero")
    context = case.record.contextualization.model_copy(
        update={
            "source_message_refs": (
                case.record.message_ref,
                case.record.message_ref,
            )
        }
    )
    record = case.record.model_copy(update={"contextualization": context})
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            RU_V2_SCHEMA_VERSION,
            record,
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED

    # The canonical fixture has two identical resolved-reference paths; those
    # collapse at the envelope relation layer without weakening source rules.
    envelope = _encode_v2(case)
    assert (
        sum(
            reference.relation == "contextualization_resolved_source_ref"
            for reference in envelope.record_references
        )
        == 1
    )


def test_codec_dependencies_are_scoped_without_active_routing_or_authority_claim() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    codec_owner_files = {
        "src/mini_agent/application/persistence.py",
        "tests/component/application/test_persistence_contract.py",
    }
    catalog_dependency_files = {
        "src/mini_agent/infrastructure/persistence/models.py",
        "tests/integration/test_database_migrations.py",
    }
    versioned_encode_dependency_files = {
        "src/mini_agent/infrastructure/persistence/postgres.py",
        "tests/integration/test_database_migrations.py",
        "tests/integration/test_postgres_record_adapters.py",
        "tests/integration/test_postgres_v2_request_understanding_writes.py",
    }
    versioned_decode_dependency_files = {
        "src/mini_agent/infrastructure/persistence/postgres.py",
        "tests/integration/test_postgres_record_adapters.py",
    }

    def folded_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = folded_string(node.left)
            right = folded_string(node.right)
            return left + right if left is not None and right is not None else None
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    part = folded_string(value.value)
                else:
                    part = folded_string(value)
                if part is None:
                    return None
                parts.append(part)
            return "".join(parts)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], (ast.List, ast.Tuple))
        ):
            separator = folded_string(node.func.value)
            parts = tuple(folded_string(item) for item in node.args[0].elts)
            if separator is not None and all(part is not None for part in parts):
                return separator.join(
                    part for part in parts if part is not None
                )
        return None

    def imports_from_persistence(node: ast.ImportFrom) -> bool:
        return (
            node.module == "mini_agent.application.persistence"
            or (
                node.level > 0
                and node.module is not None
                and node.module.split(".")[-1] == "persistence"
            )
        )

    def files_referencing(*symbols: str) -> set[str]:
        # This inventories bounded static dependency syntax. It is not a
        # Python reflection sandbox or arbitrary cross-module data-flow proof.
        symbol_set = frozenset(symbols)
        is_versioned_codec_query = bool(
            symbol_set
            & {
                "decode_persistence_record_versioned",
                "encode_persistence_record_versioned",
            }
        )
        matches: set[str] = set()
        for root in ("src", "tests"):
            for path in (repository_root / root).rglob("*.py"):
                source = path.read_text()
                tree = ast.parse(source)
                relative_path = path.relative_to(repository_root).as_posix()
                parent_by_node = {
                    child: parent
                    for parent in ast.walk(tree)
                    for child in ast.iter_child_nodes(parent)
                }
                module_bindings: set[str] = set()
                sys_bindings: set[str] = set()
                sys_modules_bindings: set[str] = set()
                module_import_without_alias = False
                persistence_reflective_import = False
                persistence_star_import = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for imported in node.names:
                            if (
                                imported.name
                                == "mini_agent.application.persistence"
                            ):
                                if imported.asname is None:
                                    module_import_without_alias = True
                                else:
                                    module_bindings.add(imported.asname)
                            elif imported.name == "sys":
                                sys_bindings.add(imported.asname or "sys")
                    elif isinstance(node, ast.ImportFrom):
                        for imported in node.names:
                            imports_persistence = imports_from_persistence(node)
                            if (
                                imported.name == "*"
                                and imports_persistence
                            ):
                                persistence_star_import = True
                            elif (
                                imported.name.startswith("__")
                                and imports_persistence
                            ):
                                persistence_reflective_import = True
                            if imported.name == "sys":
                                sys_bindings.add(
                                    imported.asname or imported.name
                                )
                            elif (
                                node.module == "sys"
                                and imported.name == "modules"
                            ):
                                sys_modules_bindings.add(
                                    imported.asname or imported.name
                                )
                            if (
                                imported.name == "persistence"
                                and (
                                    node.module == "mini_agent.application"
                                    or (
                                        node.level > 0
                                        and (
                                            node.module is None
                                            or node.module.split(".")[-1]
                                            == "application"
                                        )
                                    )
                                )
                            ):
                                module_bindings.add(
                                    imported.asname or imported.name
                                )

                legacy_monkeypatch_calls = [
                    node
                    for node in ast.walk(tree)
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "monkeypatch"
                        and node.func.attr == "setattr"
                        and len(node.args) == 3
                        and isinstance(node.args[0], ast.Name)
                        and node.args[0].id in module_bindings
                        and isinstance(node.args[1], ast.Constant)
                        and node.args[1].value
                        in {
                            "decode_persistence_record",
                            "encode_persistence_record",
                        }
                        and isinstance(node.args[2], ast.Name)
                        and node.args[2].id == "forbidden"
                        and not node.keywords
                    )
                ]
                exact_legacy_monkeypatch_calls = (
                    relative_path
                    == (
                        "tests/integration/"
                        "test_postgres_v2_request_understanding_writes.py"
                    )
                    and len(legacy_monkeypatch_calls) == 2
                    and {
                        call.args[1].value
                        for call in legacy_monkeypatch_calls
                    }
                    == {
                        "decode_persistence_record",
                        "encode_persistence_record",
                    }
                )

                def is_allowed_legacy_monkeypatch_reference(
                    node: ast.Name,
                ) -> bool:
                    parent = parent_by_node[node]
                    return (
                        exact_legacy_monkeypatch_calls
                        and isinstance(parent, ast.Call)
                        and parent in legacy_monkeypatch_calls
                        and parent.args[0] is node
                    )

                dynamic_module_lookup = (
                    module_import_without_alias
                    or persistence_reflective_import
                    or persistence_star_import
                    or any(
                        isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id in module_bindings
                        and not is_allowed_legacy_monkeypatch_reference(node)
                        for node in ast.walk(tree)
                    )
                )
                unsafe_sys_module_use = any(
                    (
                        isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id in sys_bindings
                        and not (
                            isinstance(parent_by_node[node], ast.Attribute)
                            and parent_by_node[node].value is node
                            and parent_by_node[node].attr == "path"
                        )
                    )
                    or (
                        isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id in sys_modules_bindings
                    )
                    for node in ast.walk(tree)
                )
                dynamic_import_surface = any(
                    (
                        isinstance(node, ast.Import)
                        and any(
                            imported.name.split(".", maxsplit=1)[0]
                            in {"builtins", "importlib"}
                            for imported in node.names
                        )
                    )
                    or (
                        isinstance(node, ast.ImportFrom)
                        and node.module is not None
                        and node.module.split(".", maxsplit=1)[0]
                        in {"builtins", "importlib"}
                    )
                    or (
                        isinstance(node, ast.Name)
                        and node.id
                        in {
                            "__builtins__",
                            "__import__",
                            "compile",
                            "eval",
                            "exec",
                        }
                    )
                    or (
                        isinstance(node, ast.Attribute)
                        and node.attr == "import_module"
                    )
                    for node in ast.walk(tree)
                ) or unsafe_sys_module_use
                if (
                    any(symbol in source for symbol in symbol_set)
                    or any(
                        folded_string(node) in symbol_set
                        for node in ast.walk(tree)
                    )
                    or (
                        is_versioned_codec_query
                        and (dynamic_module_lookup or dynamic_import_surface)
                    )
                ):
                    matches.add(path.relative_to(repository_root).as_posix())
        return matches

    exact_reader_owner_files = {
        "src/mini_agent/application/ports.py",
        "tests/component/application/test_persistence_contract.py",
        "tests/component/application/test_ports_contract.py",
    }
    exact_reader_dependency_files = {
        "src/mini_agent/bootstrap.py",
        "src/mini_agent/infrastructure/persistence/postgres.py",
        "tests/integration/test_postgres_record_adapters.py",
        "src/mini_agent/evaluation/harness.py",
        "tests/component/evaluation/test_e2e01_artifact_consistency.py",
        "tests/e2e/test_e2e01_http_eval.py",
        "tests/integration/test_agent_run_service_v2_persistence.py",
        "tests/integration/evaluation/test_e2e01_offline_harness.py",
        "tests/integration/test_postgres_v2_request_understanding_writes.py",
    }
    exact_reader_matches = files_referencing(
        "ExactRunEvidencePort",
        "load_exact_run_evidence_for_owner",
    )
    assert exact_reader_owner_files <= exact_reader_matches
    assert exact_reader_matches <= (
        exact_reader_owner_files | exact_reader_dependency_files
    )

    catalog_matches = files_referencing("P0_RECORD_SCHEMA_VERSION_CATALOG")
    assert codec_owner_files <= catalog_matches
    assert catalog_matches <= codec_owner_files | catalog_dependency_files

    active_registry_matches = files_referencing("P0_PERSISTENCE_REGISTRY")
    assert active_registry_matches == codec_owner_files

    versioned_encode_matches = files_referencing(
        "encode_persistence_record_versioned"
    )
    assert codec_owner_files <= versioned_encode_matches
    assert versioned_encode_matches <= (
        codec_owner_files | versioned_encode_dependency_files
    )

    versioned_decode_matches = files_referencing(
        "decode_persistence_record_versioned"
    )
    assert codec_owner_files <= versioned_decode_matches
    assert versioned_decode_matches <= (
        codec_owner_files | versioned_decode_dependency_files
    )

    postgres_path = (
        repository_root / "src/mini_agent/infrastructure/persistence/postgres.py"
    )
    postgres_tree = ast.parse(postgres_path.read_text())
    parent_by_node = {
        child: parent
        for parent in ast.walk(postgres_tree)
        for child in ast.iter_child_nodes(parent)
    }
    versioned_codec_symbols = frozenset(
        {
            "encode_persistence_record_versioned",
            "decode_persistence_record_versioned",
        }
    )
    persistence_module_object_imports = [
        node
        for node in ast.walk(postgres_tree)
        if (
            isinstance(node, ast.Import)
            and any(
                imported.name == "mini_agent"
                or imported.name.startswith("mini_agent.application")
                for imported in node.names
            )
        )
        or (
            isinstance(node, ast.ImportFrom)
            and any(
                (
                    node.module == "mini_agent"
                    and imported.name == "application"
                )
                or (
                    node.module == "mini_agent.application"
                    and imported.name == "persistence"
                )
                or (
                    imports_from_persistence(node)
                    and (
                        imported.name == "*"
                        or imported.name.startswith("__")
                    )
                )
                or (
                    node.level > 0
                    and imported.name == "persistence"
                    and (
                        node.module is None
                        or node.module.split(".")[-1] == "application"
                    )
                )
                or (
                    node.level > 0
                    and imported.name == "application"
                    and (
                        node.module is None
                        or node.module.split(".")[-1] == "mini_agent"
                    )
                )
                for imported in node.names
            )
        )
    ]
    dynamic_imports = [
        node
        for node in ast.walk(postgres_tree)
        if (
            isinstance(node, ast.Import)
            and any(
                imported.name.split(".", maxsplit=1)[0]
                in {"builtins", "importlib", "sys"}
                for imported in node.names
            )
        )
        or (
            isinstance(node, ast.ImportFrom)
            and (
                (
                    node.module is not None
                    and node.module.split(".", maxsplit=1)[0]
                    in {"builtins", "importlib", "inspect", "sys"}
                )
                or any(imported.name == "sys" for imported in node.names)
            )
        )
    ]
    dynamic_namespace_references = [
        node
        for node in ast.walk(postgres_tree)
        if (
            isinstance(node, ast.Name)
            and node.id
            in {
                "__builtins__",
                "__import__",
                "compile",
                "eval",
                "exec",
                "globals",
                "locals",
                "vars",
            }
        )
        or (
            isinstance(node, ast.Attribute)
            and node.attr
            in {
                "__dict__",
                "__getattr__",
                "__getattribute__",
                "__globals__",
                "sys",
            }
        )
    ]
    allowed_getattr_fields = frozenset(
        {
            "attempt_count",
            "started_at",
            "state_version",
            "status",
        }
    )

    def is_exact_v3_state_version_getattr(node: ast.Call) -> bool:
        target = node.args[0] if node.args else None
        return (
            len(node.args) == 3
            and not node.keywords
            and isinstance(target, ast.Attribute)
            and target.attr == "source_record"
            and isinstance(target.value, ast.Name)
            and target.value.id == "desired_decoded"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "state_version"
            and isinstance(node.args[2], ast.Constant)
            and node.args[2].value is None
        )

    exact_v3_state_version_getattrs = [
        node
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and is_exact_v3_state_version_getattr(node)
    ]
    unsafe_getattr_calls = [
        node
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and not (
            is_exact_v3_state_version_getattr(node)
            or (
                len(node.args) in {2, 3}
                and not node.keywords
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in {"record", "row"}
                and (
                    (
                        isinstance(node.args[1], ast.Name)
                        and node.args[1].id == "field_name"
                    )
                    or (
                        isinstance(node.args[1], ast.Constant)
                        and node.args[1].value in allowed_getattr_fields
                    )
                )
            )
        )
    ]
    constructed_codec_symbols = [
        node
        for node in ast.walk(postgres_tree)
        if folded_string(node) in versioned_codec_symbols
    ]
    shadowing_bindings: list[ast.AST] = []
    for node in ast.walk(postgres_tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id in versioned_codec_symbols
        ):
            shadowing_bindings.append(node)
        elif isinstance(node, ast.arg) and node.arg in versioned_codec_symbols:
            shadowing_bindings.append(node)
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name in versioned_codec_symbols
        ):
            shadowing_bindings.append(node)
        elif (
            isinstance(node, ast.alias)
            and node.asname in versioned_codec_symbols
        ):
            shadowing_bindings.append(node)
        elif (
            isinstance(node, ast.alias)
            and node.name in versioned_codec_symbols
            and not (
                isinstance(parent_by_node[node], ast.ImportFrom)
                and parent_by_node[node].module
                == "mini_agent.application.persistence"
                and node.asname is None
            )
        ):
            shadowing_bindings.append(node)
        elif (
            isinstance(node, ast.ExceptHandler)
            and node.name in versioned_codec_symbols
        ):
            shadowing_bindings.append(node)
        elif (
            isinstance(node, (ast.MatchAs, ast.MatchStar))
            and node.name in versioned_codec_symbols
        ):
            shadowing_bindings.append(node)
        elif (
            isinstance(node, ast.MatchMapping)
            and node.rest in versioned_codec_symbols
        ):
            shadowing_bindings.append(node)

    assert not persistence_module_object_imports
    assert not dynamic_imports
    assert not dynamic_namespace_references
    assert len(exact_v3_state_version_getattrs) == 1
    assert not unsafe_getattr_calls
    assert not constructed_codec_symbols
    assert not shadowing_bindings

    encoder_imports = [
        imported
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "mini_agent.application.persistence"
        for imported in node.names
        if imported.name == "encode_persistence_record_versioned"
    ]
    encoder_name_references = [
        node
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.Name)
        and node.id == "encode_persistence_record_versioned"
    ]
    encoder_attribute_references = [
        node
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "encode_persistence_record_versioned"
    ]
    decoder_imports = [
        imported
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "mini_agent.application.persistence"
        for imported in node.names
        if imported.name == "decode_persistence_record_versioned"
    ]
    decoder_name_references = [
        node
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.Name)
        and node.id == "decode_persistence_record_versioned"
    ]
    decoder_attribute_references = [
        node
        for node in ast.walk(postgres_tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "decode_persistence_record_versioned"
    ]
    exact_reader_method_name = "load_exact_run_evidence_for_owner"
    exact_reader_method_references = [
        node
        for node in ast.walk(postgres_tree)
        if (
            isinstance(node, ast.Name)
            and node.id == exact_reader_method_name
        )
        or (
            isinstance(node, ast.Attribute)
            and node.attr == exact_reader_method_name
        )
    ]
    postgres_rel = postgres_path.relative_to(repository_root).as_posix()
    if postgres_rel in versioned_encode_matches:
        assert len(encoder_imports) == 1
        assert encoder_imports[0].asname is None
        assert len(encoder_name_references) == 1
        assert not encoder_attribute_references
        for reference in encoder_name_references:
            call = parent_by_node[reference]
            assert isinstance(call, ast.Call) and call.func is reference

            direct_method_child: ast.AST = call
            enclosing_function: ast.AST | None = parent_by_node.get(call)
            while enclosing_function is not None and not isinstance(
                enclosing_function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                assert not isinstance(
                    enclosing_function,
                    (
                        ast.ClassDef,
                        ast.DictComp,
                        ast.GeneratorExp,
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                    ),
                )
                direct_method_child = enclosing_function
                enclosing_function = parent_by_node.get(enclosing_function)
            assert isinstance(
                enclosing_function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            assert direct_method_child in enclosing_function.body
            assert not any(
                isinstance(descendant, (ast.Yield, ast.YieldFrom))
                for descendant in ast.walk(enclosing_function)
            )
            assert enclosing_function.name == "_ru_v2_write_encode"

            enclosing_class: ast.AST | None = enclosing_function
            while enclosing_class is not None and not isinstance(
                enclosing_class,
                ast.ClassDef,
            ):
                enclosing_class = parent_by_node.get(enclosing_class)
            assert isinstance(enclosing_class, ast.ClassDef)
            assert enclosing_class.name == "PostgresRecordAdapter"
            assert parent_by_node[enclosing_function] is enclosing_class
        encoder_methods = [
            node
            for node in ast.walk(postgres_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_ru_v2_write_encode"
            and isinstance(parent_by_node[node], ast.ClassDef)
            and parent_by_node[node].name == "PostgresRecordAdapter"
        ]
        assert len(encoder_methods) == 1
    else:
        assert not encoder_imports
        assert not encoder_name_references
        assert not encoder_attribute_references

    if postgres_rel in versioned_decode_matches:
        assert len(decoder_imports) == 1
        assert decoder_imports[0].asname is None
        assert len(decoder_name_references) == 11
        assert not decoder_attribute_references
        assert not exact_reader_method_references
        expected_decoder_owner_counts = {
            "_load_exact_run_evidence_for_owner_version": 2,
            "_ru_v2_write_decode_cycle2": 1,
            "_ru_v2_write_encode": 1,
            "_ru_v2_write_insert_targets": 1,
            "_ru_v2_write_target_rows": 1,
            "_ru_v2_write_validate_row": 1,
            "_ru_v3_envelope_is_exact": 2,
            "_ru_v3_generated_rows_state": 1,
            "_ru_v3_insert_phase1_envelopes": 1,
        }
        decoder_owner_counts = {
            owner_name: 0 for owner_name in expected_decoder_owner_counts
        }
        for reference in decoder_name_references:
            call = parent_by_node[reference]
            assert isinstance(call, ast.Call) and call.func is reference

            direct_method_child = call
            enclosing_function = parent_by_node.get(call)
            while enclosing_function is not None and not isinstance(
                enclosing_function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                assert not isinstance(
                    enclosing_function,
                    (
                        ast.ClassDef,
                        ast.DictComp,
                        ast.GeneratorExp,
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                    ),
                )
                direct_method_child = enclosing_function
                enclosing_function = parent_by_node.get(enclosing_function)
            assert isinstance(
                enclosing_function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            assert direct_method_child in enclosing_function.body
            assert not any(
                isinstance(descendant, (ast.Yield, ast.YieldFrom))
                for descendant in ast.walk(enclosing_function)
            )
            assert enclosing_function.name in expected_decoder_owner_counts
            decoder_owner_counts[enclosing_function.name] += 1

            enclosing_class: ast.AST | None = enclosing_function
            while enclosing_class is not None and not isinstance(
                enclosing_class,
                ast.ClassDef,
            ):
                enclosing_class = parent_by_node.get(enclosing_class)
            assert isinstance(enclosing_class, ast.ClassDef)
            assert enclosing_class.name == "PostgresRecordAdapter"
            assert parent_by_node[enclosing_function] is enclosing_class
        assert decoder_owner_counts == expected_decoder_owner_counts
        assert len(encoder_name_references) + len(decoder_name_references) == 12
    else:
        assert not decoder_imports
        assert not decoder_name_references
        assert not decoder_attribute_references

    non_ru = _non_ru_registry()
    ru_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    assert len(P0_PERSISTENCE_REGISTRY) == 17
    assert tuple(P0_PERSISTENCE_REGISTRY) == tuple(P0RecordCode)[:17]
    assert len(non_ru) == 16
    assert (
        P0_PERSISTENCE_REGISTRY[ru_code].record_schema_version
        == RU_V2_SCHEMA_VERSION
    )
    for code, spec in non_ru.items():
        assert spec.record_schema_version == f"{code.value}.p0.v1"
        assert P0_PERSISTENCE_REGISTRY[code] is spec

    decoded = _decode_v2(_encode_v2(_request_understanding_v2_case("partial")))
    for forbidden_claim in (
        "authorization_scope",
        "owner_graph_valid",
        "provenance_content_verified",
        "business_fact_verified",
        "postgres_routed",
        "active_routing",
        "readiness",
    ):
        assert not hasattr(decoded, forbidden_claim)


def test_current_codec_projection_counts_are_exact() -> None:
    top = tuple(
        rule
        for spec in P0_PERSISTENCE_REGISTRY.values()
        for rule in spec.projection_decisions
    )
    child = tuple(
        rule
        for spec in P0_LOGICAL_CHILD_SPECS.values()
        for rule in spec.projection_decisions
    )
    reference_classes = {
        "TOP_LEVEL_P0_REFERENCE",
        "EXTERNAL_REQUIRED_P0_REFERENCE",
        "CHILD_TOP_LEVEL_P0_REFERENCE",
    }
    references = tuple(
        rule
        for rule in (*top, *child)
        if rule.classification.value in reference_classes
    )
    assert (len(top), len(child), len(references)) == (70, 8, 49)


@pytest.mark.parametrize("selected_version", ("v1", "v2"))
@pytest.mark.parametrize("input_kind", ("mapping", "str", "bytes"))
@pytest.mark.parametrize(
    "unsafe_outer_version",
    (
        ["RAW-VERSION-Token-VERY-SECRET"],
        {"raw": "RAW-VERSION-Token-VERY-SECRET"},
    ),
    ids=("list", "mapping"),
)
def test_versioned_decode_bounds_non_string_outer_version_before_membership(
    selected_version: str,
    input_kind: str,
    unsafe_outer_version: object,
) -> None:
    marker = "RAW-VERSION-Token-VERY-SECRET"
    if selected_version == "v1":
        case = _case(P0RecordCode.MESSAGE_RECORD)
        envelope = encode_persistence_record(case.code, case.record)
        expected_record_code = case.code
        expected_schema_version = "message_record.p0.v1"
    else:
        envelope = _encode_v2(_request_understanding_v2_case("partial"))
        expected_record_code = P0RecordCode.REQUEST_UNDERSTANDING_RECORD
        expected_schema_version = RU_V2_SCHEMA_VERSION

    raw = json.loads(envelope.model_dump_json())
    raw["record_schema_version"] = unsafe_outer_version
    inputs: dict[str, object] = {
        "mapping": raw,
        "str": json.dumps(raw),
        "bytes": json.dumps(raw).encode("utf-8"),
    }
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.decode_persistence_record_versioned(
            inputs[input_kind],
            expected_record_code=expected_record_code,
            expected_schema_version=expected_schema_version,
            correlation_ref=_uuid(299),
        )
    assert (
        raised.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )
    projection = " ".join(
        (str(raised.value), repr(raised.value), repr(raised.value.args))
    )
    assert marker not in projection
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("case", _record_cases(), ids=lambda case: case.code.value)
def test_all_16_non_ru_versioned_decode_outer_categories_match_generic(
    case: RecordCase,
) -> None:
    non_ru_registry = _non_ru_registry()
    envelope = encode_persistence_record(
        case.code,
        case.record,
        external_references=case.external_references,
        logical_children=case.logical_children,
    )
    other_active_version = next(
        spec.record_schema_version
        for code, spec in non_ru_registry.items()
        if code is not case.code
    )

    missing = json.loads(envelope.model_dump_json())
    missing.pop("record_schema_version")
    other_v1 = json.loads(envelope.model_dump_json())
    other_v1["record_schema_version"] = other_active_version
    ru_v2 = json.loads(envelope.model_dump_json())
    ru_v2["record_schema_version"] = RU_V2_SCHEMA_VERSION
    unknown_future = json.loads(envelope.model_dump_json())
    unknown_future["record_schema_version"] = "unknown-future-record.p0.v99"

    mutations: tuple[
        tuple[
            dict[str, object],
            P0PersistenceIntegrityCategory,
            P0PersistenceIntegrityCategory,
        ],
        ...,
    ] = (
        (
            missing,
            P0PersistenceIntegrityCategory.MISSING_RECORD_SCHEMA_VERSION,
            P0PersistenceIntegrityCategory.MISSING_RECORD_SCHEMA_VERSION,
        ),
        (
            other_v1,
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH,
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH,
        ),
        (
            ru_v2,
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH,
        ),
        (
            unknown_future,
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
        ),
    )

    for raw, generic_category, versioned_category in mutations:
        with pytest.raises(P0PersistenceIntegrityError) as generic_raised:
            decode_persistence_record(
                raw,
                expected_record_code=case.code,
                correlation_ref=_uuid(299),
            )
        with pytest.raises(P0PersistenceIntegrityError) as versioned_raised:
            persistence_module.decode_persistence_record_versioned(
                raw,
                expected_record_code=case.code,
                expected_schema_version=non_ru_registry[
                    case.code
                ].record_schema_version,
                correlation_ref=_uuid(299),
            )
        assert generic_raised.value.category is generic_category
        assert versioned_raised.value.category is versioned_category


def test_cycle2_record_codes_and_exact_version_pairs_are_additive() -> None:
    expected_additive_codes = (
        "order_search_observation_record",
        "order_candidate_set_record",
        "order_candidate_selection_record",
        "shipment_observation_record",
        "shipment_assessment_record",
    )
    assert tuple(code.value for code in P0RecordCode)[-5:] == expected_additive_codes

    catalog = persistence_module.P0_RECORD_SCHEMA_VERSION_CATALOG
    expected_v2_pairs = {
        (P0RecordCode.INPUT_BINDING_RECORD, "input_binding_record.p0.v2"),
        (P0RecordCode.GATE_DECISION_RECORD, "gate_decision_record.p0.v2"),
        (P0RecordCode.TOOL_CALL_RECORD, "tool_call_record.p0.v2"),
        (P0RecordCode.AGENT_RUN_RECORD, "agent_run_record.p0.v2"),
        (P0RecordCode.RUN_TASK_LINK_RECORD, "run_task_link_record.p0.v2"),
        (P0RecordCode.TRACE_EVENT_RECORD, "trace_event_record.p0.v2"),
    }
    assert expected_v2_pairs <= set(catalog)


from mini_agent.core.memory import (
    SearchObservationCandidateTargetBinding,
    SearchOrdersObservation,
    SearchOrdersObservationCandidate,
    SearchOrdersObservationValue,
    ShipmentObservation,
)
from mini_agent.core.order_search import (
    OrderCandidateMatchingItem,
    OrderCandidatePublicSummary,
)
from mini_agent.core.shipment import (
    ShipmentAssessment,
    ShipmentAssessmentReason,
    ShipmentAssessmentResult,
    ShipmentEventCode,
    ShipmentStatus,
    ShipmentSummaryProjection,
)
from mini_agent.core.task_state import (
    InputBindingV2,
    OrderCandidateSelectionRecord,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    compute_order_candidate_set_version,
)
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    RegistrySnapshot,
    ToolAttemptRecordV2,
    ToolRecoveryDecision,
    ToolRecoveryDisposition,
    ToolRegistration,
    ToolResultOutcome,
    ToolRetryDecision,
    build_cycle2_registry_snapshot,
)


def _cycle2_new_record_cases() -> tuple[tuple[P0RecordCode, str, object], ...]:
    owner = "owner-scope:codec"
    snapshot_version = (
        "mock-order-search-snapshot-source-version.p0.v1:sha256:" + "a" * 64
    )
    candidate_version = (
        "mock-order-search-candidate-source-version.p0.v1:sha256:" + "b" * 64
    )
    candidate_ref = _uuid(401)
    search = SearchOrdersObservation(
        observation_id=_uuid(402),
        private_owner_scope=owner,
        source_tool="search_orders",
        source_tool_call_id=_uuid(403),
        source_resource_ref="order-search-snapshot:codec",
        source_version=snapshot_version,
        candidate_target_bindings=(
            SearchObservationCandidateTargetBinding(
                observation_candidate_ref=candidate_ref,
                owner_scoped_order_ref="owner-order:codec",
                candidate_source_version=candidate_version,
            ),
        ),
        normalized_type="ORDER_SEARCH_CANDIDATES",
        normalized_value=SearchOrdersObservationValue(
            ordered_candidates=(
                SearchOrdersObservationCandidate(
                    observation_candidate_ref=candidate_ref,
                    candidate_source_version=candidate_version,
                    public_summary=OrderCandidatePublicSummary(
                        order_number="O-4001",
                        ordered_on_utc=date(2026, 7, 25),
                        status=OrderStatus.SHIPPED,
                        matching_items=(
                            OrderCandidateMatchingItem(
                                product_name="轻量跑鞋",
                                quantity=1,
                            ),
                        ),
                    ),
                ),
            ),
            truncated=False,
        ),
        observed_at=UTC_NOW,
        recorded_at=UTC_NOW + timedelta(seconds=1),
        valid_until=UTC_NOW + timedelta(minutes=15, seconds=1),
    )
    entry = OrderCandidateSetEntry(
        ordinal=1,
        observation_candidate_ref=candidate_ref,
        candidate_source_version=candidate_version,
    )
    candidate_values: dict[str, object] = {
        "candidate_set_id": _uuid(404),
        "private_owner_scope_ref": owner,
        "conversation_id": _uuid(405),
        "task_id": _uuid(406),
        "request_unit_id": _uuid(407),
        "outcome": OrderCandidateSetOutcome.UNIQUE,
        "base_task_state_version": 3,
        "result_task_state_version": 4,
        "selection_expected_task_state_version": None,
        "query_binding_refs": (_uuid(408),),
        "source_tool_call_id": search.source_tool_call_id,
        "search_observation_ref": search.observation_id,
        "search_observation_record_schema_version": (
            "order_search_observation_record.p0.v1"
        ),
        "search_observation_source_version": snapshot_version,
        "ordered_candidates": (entry,),
        "created_at": search.recorded_at,
        "valid_until": search.valid_until,
        "supersedes_candidate_set_ref": None,
    }
    candidate_set = OrderCandidateSetRecord(
        **candidate_values,
        candidate_set_version=compute_order_candidate_set_version(
            **candidate_values
        ),
    )
    selection = OrderCandidateSelectionRecord(
        selection_id=_uuid(409),
        private_owner_scope_ref=owner,
        conversation_id=candidate_set.conversation_id,
        task_id=candidate_set.task_id,
        request_unit_id=candidate_set.request_unit_id,
        source_message_ref=_uuid(410),
        ordinal_input_binding_ref=_uuid(411),
        candidate_set_ref=candidate_set.candidate_set_id,
        candidate_set_version=candidate_set.candidate_set_version,
        search_observation_ref=search.observation_id,
        search_observation_record_schema_version=(
            "order_search_observation_record.p0.v1"
        ),
        observation_candidate_ref=candidate_ref,
        candidate_source_version=candidate_version,
        owner_scoped_order_target_ref="owner-order:codec",
        selected_target_ref="verified-target:codec",
        base_task_state_version=4,
        result_task_state_version=5,
        selected_at=UTC_NOW + timedelta(minutes=1),
    )
    shipment_version = (
        "mock-shipment-source-version.p0.v1:sha256:" + "c" * 64
    )
    shipment = ShipmentObservation(
        observation_id=_uuid(412),
        private_owner_scope=owner,
        task_id=_uuid(413),
        request_unit_id=_uuid(414),
        verified_order_target_ref="verified-target:codec",
        source_tool="get_shipment",
        source_tool_call_id=_uuid(415),
        source_resource_ref="shipment:codec",
        source_version=shipment_version,
        normalized_type="SHIPMENT_SUMMARY",
        normalized_value=ShipmentSummaryProjection(
            shipment_status=ShipmentStatus.IN_TRANSIT,
            latest_event_code=ShipmentEventCode.IN_TRANSIT,
            latest_event_at=UTC_NOW - timedelta(hours=1),
            promised_delivery_at=UTC_NOW + timedelta(days=1),
        ),
        observed_at=UTC_NOW,
        recorded_at=UTC_NOW + timedelta(minutes=1),
        valid_until=UTC_NOW + timedelta(minutes=5),
    )
    assessment = ShipmentAssessment(
        assessment_id=_uuid(416),
        private_owner_scope_ref=owner,
        task_id=shipment.task_id,
        request_unit_id=shipment.request_unit_id,
        task_state_version=5,
        verified_order_target_ref=shipment.verified_order_target_ref,
        shipment_observation_ref=shipment.observation_id,
        shipment_observation_source_version=shipment.source_version,
        primary_result=ShipmentAssessmentResult.NORMAL,
        reason_codes=(ShipmentAssessmentReason.NO_P0_SHIPMENT_EXCEPTION,),
        assessed_at=UTC_NOW + timedelta(minutes=2),
    )
    return (
        (
            P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
            "order_search_observation_record.p0.v1",
            search,
        ),
        (
            P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
            "order_candidate_set_record.p0.v1",
            candidate_set,
        ),
        (
            P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
            "order_candidate_selection_record.p0.v1",
            selection,
        ),
        (
            P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
            "shipment_observation_record.p0.v1",
            shipment,
        ),
        (
            P0RecordCode.SHIPMENT_ASSESSMENT_RECORD,
            "shipment_assessment_record.p0.v1",
            assessment,
        ),
    )


@pytest.mark.parametrize(
    ("record_code", "schema_version", "record"),
    _cycle2_new_record_cases(),
    ids=lambda value: value.value if isinstance(value, P0RecordCode) else None,
)
def test_cycle2_new_top_level_records_round_trip_exactly(
    record_code: P0RecordCode,
    schema_version: str,
    record: object,
) -> None:
    envelope = persistence_module.encode_persistence_record_versioned(
        record_code,
        schema_version,
        record,
    )
    decoded = persistence_module.decode_persistence_record_versioned(
        envelope.model_dump_json(),
        expected_record_code=record_code,
        expected_schema_version=schema_version,
        correlation_ref=_uuid(499),
    )
    assert decoded.source_record == record
    assert decoded.logical_children == ()
    assert envelope.direct_owner_customer_id == (
        getattr(record, "private_owner_scope", None)
        or getattr(record, "private_owner_scope_ref")
    )


def _tool_call_v2_with_unfinished_attempt() -> tuple[object, object]:
    attempt = ToolAttemptRecordV2(
        tool_call_id=_uuid(501),
        attempt_no=1,
        started_at=UTC_NOW,
    )
    source_v1 = _case(P0RecordCode.TOOL_CALL_RECORD).record
    record = persistence_module.ToolCallRecordV2(
        tool_call_id=attempt.tool_call_id,
        run_id=source_v1.run_id,
        task_id=source_v1.task_id,
        request_unit_id=source_v1.request_unit_id,
        model_call_id=source_v1.model_call_id,
        context_manifest_id=source_v1.context_manifest_id,
        gate_decision_id=source_v1.gate_decision_id,
        canonical_tool_name="search_orders",
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref="owner-scope:codec",
        validated_task_state_version=source_v1.validated_task_state_version,
        argument_binding_refs=source_v1.argument_binding_refs,
        effect=ToolEffect.READ,
        attempt_count=1,
        attempts=(attempt,),
        status=ToolCallStatus.RUNNING,
        started_at=UTC_NOW,
    )
    return record, attempt


def test_tool_call_v2_attempt_is_strict_parent_versioned_child() -> None:
    record, attempt = _tool_call_v2_with_unfinished_attempt()
    envelope = persistence_module.encode_persistence_record_versioned(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        record,
        logical_children=(attempt,),
    )
    decoded = persistence_module.decode_persistence_record_versioned(
        envelope,
        expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
        expected_schema_version="tool_call_record.p0.v2",
        correlation_ref=_uuid(599),
    )
    assert decoded.source_record == record
    assert decoded.logical_children == (attempt,)

    with pytest.raises(P0PersistenceIntegrityError) as missing:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v2",
            record,
        )
    assert missing.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH

    v1_attempt = _case(P0RecordCode.TOOL_CALL_RECORD).logical_children[0]
    with pytest.raises(P0PersistenceIntegrityError) as mixed:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v2",
            record,
            logical_children=(v1_attempt,),
        )
    assert mixed.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


def _recovered_tool_call_v2() -> tuple[object, object, object, object]:
    first = ToolAttemptRecordV2(
        tool_call_id=_uuid(520),
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=UTC_NOW + timedelta(seconds=1),
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="ORDER_SEARCH_TRANSIENT",
        retry_decision=ToolRetryDecision.RETRY_SCHEDULED,
    )
    decision = ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=_uuid(521),
        tool_call_id=first.tool_call_id,
        last_attempt_no=1,
        decision=ToolRecoveryDecision.APPEND_SECOND_ATTEMPT,
        stable_reason_code="RETRY_REVALIDATED_CAS_REQUIRED",
        candidate_next_attempt_no=2,
        decided_at=UTC_NOW + timedelta(seconds=2),
    )
    second = ToolAttemptRecordV2(
        tool_call_id=first.tool_call_id,
        attempt_no=2,
        started_at=decision.decided_at,
    )
    source, _ = _tool_call_v2_with_unfinished_attempt()
    parent = persistence_module.ToolCallRecordV2(
        **{
            **source.model_dump(),
            "tool_call_id": first.tool_call_id,
            "attempt_count": 2,
            "attempts": (first, second),
        }
    )
    return parent, first, decision, second


def test_tool_call_v2_recovery_decision_child_round_trips_in_append_order() -> None:
    parent, first, decision, second = _recovered_tool_call_v2()
    children = (first, decision, second)
    envelope = persistence_module.encode_persistence_record_versioned(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        parent,
        logical_children=children,
    )
    assert tuple(
        child.child_code for child in envelope.payload.logical_children
    ) == (
        P0LogicalChildCode.TOOL_ATTEMPT_RECORD,
        P0LogicalChildCode.TOOL_RETRY_RECOVERY_DECISION_RECORD,
        P0LogicalChildCode.TOOL_ATTEMPT_RECORD,
    )
    decoded = persistence_module.decode_persistence_record_versioned(
        envelope,
        expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
        expected_schema_version="tool_call_record.p0.v2",
        correlation_ref=_uuid(529),
    )
    assert decoded.source_record == parent
    assert decoded.logical_children == children

    finalized_second = ToolAttemptRecordV2(
        tool_call_id=second.tool_call_id,
        attempt_no=2,
        started_at=second.started_at,
        finished_at=second.started_at + timedelta(seconds=1),
        outcome=ToolResultOutcome.SYSTEM_FAILURE,
        failure_code="ORDER_SEARCH_TRANSIENT",
        retry_decision=ToolRetryDecision.MAX_ATTEMPTS_REACHED,
    )
    terminal_parent = persistence_module.ToolCallRecordV2(
        **{
            **parent.model_dump(),
            "attempts": (first, finalized_second),
            "status": ToolCallStatus.FAILED,
            "finished_at": finalized_second.finished_at,
            "failure_code": finalized_second.failure_code,
        }
    )
    terminal_envelope = persistence_module.encode_persistence_record_versioned(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        terminal_parent,
        logical_children=(first, decision, finalized_second),
    )
    terminal_decoded = persistence_module.decode_persistence_record_versioned(
        terminal_envelope,
        expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
        expected_schema_version="tool_call_record.p0.v2",
        correlation_ref=_uuid(528),
    )
    assert terminal_decoded.logical_children == (
        first,
        decision,
        finalized_second,
    )

    for malformed in (
        (first, second, decision),
        (first, decision, decision, second),
        (second, decision, first),
    ):
        with pytest.raises(P0PersistenceIntegrityError) as raised:
            persistence_module.encode_persistence_record_versioned(
                P0RecordCode.TOOL_CALL_RECORD,
                "tool_call_record.p0.v2",
                parent,
                logical_children=malformed,
            )
        assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


def _terminal_recovery_tool_calls_v2() -> tuple[tuple[object, object, object], ...]:
    running, unfinished = _tool_call_v2_with_unfinished_attempt()
    unfinished_decision = ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=_uuid(531),
        tool_call_id=unfinished.tool_call_id,
        last_attempt_no=1,
        decision=ToolRecoveryDecision.INTERRUPT_UNFINISHED_ATTEMPT,
        stable_reason_code="UNFINISHED_ATTEMPT_OUTCOME_UNKNOWN",
        decided_at=UTC_NOW + timedelta(seconds=2),
    )
    unfinished_parent = persistence_module.ToolCallRecordV2(
        **{
            **running.model_dump(),
            "status": ToolCallStatus.INTERRUPTED,
            "finished_at": unfinished_decision.decided_at,
            "interruption_reason": "PROCESS_RESTART_DETECTED",
            "recovery_disposition": (
                ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
            ),
            "recovery_decision_ref": (
                unfinished_decision.recovery_decision_id
            ),
        }
    )

    recovered, first, _, _ = _recovered_tool_call_v2()
    budget_decision = ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=_uuid(532),
        tool_call_id=first.tool_call_id,
        last_attempt_no=1,
        decision=ToolRecoveryDecision.TERMINATE_RETRY_PATH,
        stable_reason_code="RUN_BUDGET_EXHAUSTED",
        decided_at=UTC_NOW + timedelta(seconds=2),
    )
    budget_parent = persistence_module.ToolCallRecordV2(
        **{
            **recovered.model_dump(),
            "attempt_count": 1,
            "attempts": (first,),
            "status": ToolCallStatus.FAILED,
            "finished_at": budget_decision.decided_at,
            "failure_code": first.failure_code,
            "recovery_disposition": (
                ToolRecoveryDisposition.RETRY_SCHEDULED_RUN_BUDGET_EXHAUSTED
            ),
            "recovery_decision_ref": budget_decision.recovery_decision_id,
        }
    )
    state_decision = ToolRetryRecoveryDecisionRecordV2(
        recovery_decision_id=_uuid(533),
        tool_call_id=first.tool_call_id,
        last_attempt_no=1,
        decision=ToolRecoveryDecision.TERMINATE_RETRY_PATH,
        stable_reason_code="STATE_OR_BINDING_INVALIDATED",
        decided_at=UTC_NOW + timedelta(seconds=2),
    )
    state_parent = persistence_module.ToolCallRecordV2(
        **{
            **recovered.model_dump(),
            "attempt_count": 1,
            "attempts": (first,),
            "status": ToolCallStatus.INTERRUPTED,
            "finished_at": state_decision.decided_at,
            "interruption_reason": "STATE_OR_BINDING_INVALIDATED",
            "recovery_disposition": (
                ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
            ),
            "recovery_decision_ref": state_decision.recovery_decision_id,
        }
    )
    return (
        (unfinished_parent, unfinished, unfinished_decision),
        (budget_parent, first, budget_decision),
        (state_parent, first, state_decision),
    )


@pytest.mark.parametrize(
    ("parent", "attempt", "decision"),
    _terminal_recovery_tool_calls_v2(),
)
def test_tool_call_v2_terminal_recovery_child_closes_parent_reference(
    parent: object,
    attempt: object,
    decision: object,
) -> None:
    children = (attempt, decision)
    envelope = persistence_module.encode_persistence_record_versioned(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        parent,
        logical_children=children,
    )
    decoded = persistence_module.decode_persistence_record_versioned(
        envelope,
        expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
        expected_schema_version="tool_call_record.p0.v2",
        correlation_ref=_uuid(539),
    )
    assert decoded.logical_children == children

    with pytest.raises(P0PersistenceIntegrityError) as missing:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v2",
            parent,
            logical_children=(attempt,),
        )
    assert missing.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH

    wrong_ref_parent = parent.model_copy(
        update={"recovery_decision_ref": _uuid(538)}
    )
    with pytest.raises(P0PersistenceIntegrityError) as wrong_ref:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v2",
            wrong_ref_parent,
            logical_children=children,
        )
    assert wrong_ref.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


def test_recovery_decision_child_is_v2_tool_call_only_and_decode_fails_closed() -> None:
    parent, first, decision, second = _recovered_tool_call_v2()
    child_catalog = persistence_module.P0_LOGICAL_CHILD_SCHEMA_VERSION_CATALOG
    decision_code = P0LogicalChildCode.TOOL_RETRY_RECOVERY_DECISION_RECORD
    assert (
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        decision_code,
    ) in child_catalog
    assert (
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        decision_code,
    ) not in child_catalog
    assert decision_code not in P0_LOGICAL_CHILD_SPECS
    assert len(persistence_module._CYCLE2_NEW_TOP_LEVEL_SPECS) == 5
    assert len(persistence_module._CYCLE2_V2_PARENT_SPECS) == 6

    v1_parent = _case(P0RecordCode.TOOL_CALL_RECORD).record
    with pytest.raises(P0PersistenceIntegrityError) as v1:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v1",
            v1_parent,
            logical_children=(decision,),
        )
    assert v1.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH

    created = parent.model_copy(
        update={
            "attempt_count": 0,
            "attempts": (),
            "status": ToolCallStatus.CREATED,
        }
    )
    with pytest.raises(P0PersistenceIntegrityError) as dangling:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v2",
            created,
            logical_children=(decision,),
        )
    assert dangling.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH

    ordinary, ordinary_attempt = _tool_call_v2_with_unfinished_attempt()
    ordinary_decision = decision.model_copy(
        update={"tool_call_id": ordinary.tool_call_id}
    )
    with pytest.raises(P0PersistenceIntegrityError) as ordinary_extra:
        persistence_module.encode_persistence_record_versioned(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v2",
            ordinary,
            logical_children=(ordinary_attempt, ordinary_decision),
        )
    assert (
        ordinary_extra.value.category
        is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    )

    raw = persistence_module.encode_persistence_record_versioned(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        parent,
        logical_children=(first, decision, second),
    ).model_dump(mode="json")
    raw["payload"]["logical_children"][1]["logical_identity"] = [
        ["recovery_decision_id", str(_uuid(537))]
    ]
    with pytest.raises(P0PersistenceIntegrityError) as identity:
        persistence_module.decode_persistence_record_versioned(
            raw,
            expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
            expected_schema_version="tool_call_record.p0.v2",
            correlation_ref=_uuid(537),
        )
    assert identity.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH

    raw["payload"]["logical_children"][1]["logical_identity"] = [
        ["recovery_decision_id", str(decision.recovery_decision_id)]
    ]
    raw["payload"]["logical_children"].insert(
        2,
        dict(raw["payload"]["logical_children"][1]),
    )
    with pytest.raises(P0PersistenceIntegrityError) as duplicate_decode:
        persistence_module.decode_persistence_record_versioned(
            raw,
            expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
            expected_schema_version="tool_call_record.p0.v2",
            correlation_ref=_uuid(535),
        )
    assert (
        duplicate_decode.value.category
        is P0PersistenceIntegrityCategory.CHILD_MISMATCH
    )
    raw["payload"]["logical_children"].pop(2)
    raw["payload"]["logical_children"][1]["child_code"] = "unknown_child"
    with pytest.raises(P0PersistenceIntegrityError):
        persistence_module.decode_persistence_record_versioned(
            raw,
            expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
            expected_schema_version="tool_call_record.p0.v2",
            correlation_ref=_uuid(536),
        )


def _phase1_get_order_registry_snapshot() -> RegistrySnapshot:
    return RegistrySnapshot.build(
        tool_registry_version="e2e01-thin-tools-v1",
        registrations=(
            ToolRegistration(
                tool_spec=get_order_tool_spec(),
                provider_visible_name="get_order",
                effect=ToolEffect.READ,
                risk="LOW",
                idempotency="READ_ONLY",
                handler_ref="orders.get_order",
                execution_policy=ExecutionPolicy(
                    timeout_ms=500,
                    max_attempts=1,
                    interrupt_behavior="MARK_INTERRUPTED",
                ),
            ),
        ),
    )


def _trusted_codec_owner_scope(customer_id: str = "customer-A") -> TrustedOwnerScope:
    return TrustedOwnerScope.from_customer_context(
        CustomerContext(
            subject_ref=f"subject:{customer_id}",
            customer_id=customer_id,
            auth_scopes=frozenset({"orders:read"}),
            authenticated_at=UTC_NOW,
            session_ref_hash=f"session:{customer_id}",
        )
    )


def _phase1_tool_owner_graph() -> dict[str, object]:
    return {
        "owner_scope": _trusted_codec_owner_scope(),
        "source_task_record": _case(P0RecordCode.TASK_RECORD).record,
        "source_request_unit_record": _case(
            P0RecordCode.REQUEST_UNIT_RECORD
        ).record,
        "source_argument_binding_records": (
            _case(P0RecordCode.INPUT_BINDING_RECORD).record,
        ),
    }


def test_conversion_readiness_is_exact_zero_io_and_fail_closed() -> None:
    input_case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    ready = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.INPUT_BINDING_RECORD,
        "input_binding_record.p0.v1",
        "input_binding_record.p0.v2",
        input_case.record,
        active_schema_versions=("input_binding_record.p0.v1",),
        external_references=input_case.external_references,
    )
    assert ready.category is persistence_module.P0ConversionReadinessCategory.READY
    assert type(ready.target_record) is InputBindingV2
    assert ready.target_record.model_dump() == input_case.record.model_dump()

    mixed = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.INPUT_BINDING_RECORD,
        "input_binding_record.p0.v1",
        "input_binding_record.p0.v2",
        input_case.record,
        external_references=input_case.external_references,
        active_schema_versions=(
            "input_binding_record.p0.v1",
            "input_binding_record.p0.v2",
        ),
    )
    assert (
        mixed.category
        is persistence_module.P0ConversionReadinessCategory.MIXED_ACTIVE_VERSION
    )

    tool_case = _case(P0RecordCode.TOOL_CALL_RECORD)
    no_authority = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=tool_case.logical_children,
    )
    assert (
        no_authority.category
        is persistence_module.P0ConversionReadinessCategory.AUTHORITY_REQUIRED
    )
    tool_ready = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=tool_case.logical_children,
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        tool_ready.category
        is persistence_module.P0ConversionReadinessCategory.READY
    )
    assert tool_ready.target_record.verified_target_ref is None
    assert tuple(
        (attempt.tool_call_id, attempt.attempt_no)
        for attempt in tool_ready.target_logical_children
    ) == tuple(
        (attempt.tool_call_id, attempt.attempt_no)
        for attempt in tool_case.logical_children
    )
    assert all(
        type(child) is ToolAttemptRecordV2
        for child in tool_ready.target_logical_children
    )


def test_conversion_readiness_preserves_gate_run_link_and_trace_evidence() -> None:
    gate_case = _case(P0RecordCode.GATE_DECISION_RECORD)
    gate = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.GATE_DECISION_RECORD,
        "gate_decision_record.p0.v1",
        "gate_decision_record.p0.v2",
        gate_case.record,
        active_schema_versions=("gate_decision_record.p0.v1",),
    )
    assert gate.is_ready
    assert gate.target_record.verified_target_ref is None
    assert gate.target_record.validated_arguments is None
    assert {
        name: getattr(gate.target_record, name)
        for name in type(gate_case.record).model_fields
    } == {
        name: getattr(gate_case.record, name)
        for name in type(gate_case.record).model_fields
    }

    incomplete = AgentRunRecord(
        run_id=_uuid(601),
        status=AgentRunStatus.INCOMPLETE,
        provider_lane="scripted",
        started_at=UTC_NOW,
        completed_at=UTC_NOW + timedelta(seconds=1),
        stop_reason="PROCESS_RESTART_DETECTED",
        incomplete_reason="PROCESS_RESTART_DETECTED",
    )
    run = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.AGENT_RUN_RECORD,
        "agent_run_record.p0.v1",
        "agent_run_record.p0.v2",
        incomplete,
        active_schema_versions=("agent_run_record.p0.v1",),
    )
    assert run.is_ready
    assert run.target_record.status.value == "INCOMPLETE"
    assert run.target_record.stop_reason.value == "PROCESS_RESTART_DETECTED"
    assert run.target_record.status.value != "SUPERSEDED"

    failed = AgentRunRecord(
        run_id=_uuid(602),
        status=AgentRunStatus.FAILED,
        provider_lane="scripted",
        started_at=UTC_NOW,
        completed_at=UTC_NOW + timedelta(seconds=1),
    )
    failed_run = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.AGENT_RUN_RECORD,
        "agent_run_record.p0.v1",
        "agent_run_record.p0.v2",
        failed,
        active_schema_versions=("agent_run_record.p0.v1",),
    )
    assert failed_run.is_ready
    assert failed_run.target_record.status.value == "FAILED"

    active_link = RunTaskLinkRecord(
        schema_version="run_task_link_record.p0.v1",
        run_id=_uuid(603),
        task_id=_uuid(604),
        base_task_state_version=7,
        result_task_state_version=None,
    )
    link = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.RUN_TASK_LINK_RECORD,
        "run_task_link_record.p0.v1",
        "run_task_link_record.p0.v2",
        active_link,
        active_schema_versions=("run_task_link_record.p0.v1",),
    )
    assert link.is_ready
    assert link.target_record.result_task_state_version is None
    assert link.target_record.base_task_state_version == 7

    trace_case = _case(P0RecordCode.TRACE_EVENT_RECORD)
    trace = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TRACE_EVENT_RECORD,
        "trace_event_record.p0.v1",
        "trace_event_record.p0.v2",
        trace_case.record,
        active_schema_versions=("trace_event_record.p0.v1",),
    )
    assert trace.is_ready
    assert trace.target_record.model_dump(mode="json") == (
        trace_case.record.model_dump(mode="json")
    )

    input_case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    input_ready = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.INPUT_BINDING_RECORD,
        "input_binding_record.p0.v1",
        "input_binding_record.p0.v2",
        input_case.record,
        active_schema_versions=("input_binding_record.p0.v1",),
        external_references=input_case.external_references,
    )
    public_pairs = (
        (
            P0RecordCode.INPUT_BINDING_RECORD,
            "input_binding_record.p0.v2",
            input_ready.target_record,
            input_case.external_references,
        ),
        (
            P0RecordCode.GATE_DECISION_RECORD,
            "gate_decision_record.p0.v2",
            gate.target_record,
            (),
        ),
        (
            P0RecordCode.AGENT_RUN_RECORD,
            "agent_run_record.p0.v2",
            run.target_record,
            (),
        ),
        (
            P0RecordCode.RUN_TASK_LINK_RECORD,
            "run_task_link_record.p0.v2",
            link.target_record,
            (),
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "trace_event_record.p0.v2",
            trace.target_record,
            (),
        ),
    )
    for code, version, target, external in public_pairs:
        envelope = persistence_module.encode_persistence_record_versioned(
            code,
            version,
            target,
            external_references=external,
        )
        decoded = persistence_module.decode_persistence_record_versioned(
            envelope,
            expected_record_code=code,
            expected_schema_version=version,
            correlation_ref=_uuid(698),
        )
        assert decoded.source_record == target

    inactive_code, inactive_version, inactive_record = (
        _cycle2_new_record_cases()[0]
    )
    with pytest.raises(P0PersistenceIntegrityError) as generic:
        encode_persistence_record(inactive_code, inactive_record)
    assert (
        generic.value.category
        is P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )


def test_conversion_readiness_rejects_unknown_duplicate_and_ambiguous_graphs() -> None:
    input_case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    unknown = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.INPUT_BINDING_RECORD,
        "gate_decision_record.p0.v1",
        "input_binding_record.p0.v2",
        input_case.record,
        active_schema_versions=("gate_decision_record.p0.v1",),
    )
    assert (
        unknown.category
        is persistence_module.P0ConversionReadinessCategory.UNKNOWN_SOURCE_VERSION
    )

    tool_case = _case(P0RecordCode.TOOL_CALL_RECORD)
    duplicate = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=(
            tool_case.logical_children[0],
            tool_case.logical_children[0],
        ),
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert not duplicate.is_ready
    assert duplicate.target_record is None

    attempt = ToolAttemptRecord(
        tool_call_id=_uuid(605),
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=UTC_NOW + timedelta(milliseconds=100),
        outcome="SYSTEM_FAILURE",
        failure_code="SHIPMENT_SERVICE_TRANSIENT",
    )
    ambiguous_parent = ToolCallRecord(
        tool_call_id=attempt.tool_call_id,
        run_id=_uuid(606),
        task_id=_uuid(607),
        request_unit_id=_uuid(608),
        model_call_id=_uuid(609),
        context_manifest_id=_uuid(610),
        gate_decision_id=_uuid(611),
        canonical_tool_name="get_shipment",
        tool_registry_version="e2e01-tools.p0.v1",
        validated_task_state_version=2,
        argument_binding_refs=(_uuid(612),),
        effect=ToolEffect.READ,
        attempt_count=1,
        status=ToolCallStatus.FAILED,
        started_at=UTC_NOW,
        finished_at=attempt.finished_at,
        failure_code=attempt.failure_code,
    )
    ambiguous = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        ambiguous_parent,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=(attempt,),
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        ambiguous.category
        is persistence_module.P0ConversionReadinessCategory.CONTRADICTORY_GRAPH
    )
    assert ambiguous.target_record is None


def test_tool_call_v2_decode_rejects_child_parent_identity_tampering() -> None:
    record, attempt = _tool_call_v2_with_unfinished_attempt()
    envelope = persistence_module.encode_persistence_record_versioned(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v2",
        record,
        logical_children=(attempt,),
    ).model_dump(mode="json")
    envelope["payload"]["logical_children"][0]["parent_logical_identity"] = [
        ["tool_call_id", str(_uuid(699))]
    ]
    with pytest.raises(P0PersistenceIntegrityError) as raised:
        persistence_module.decode_persistence_record_versioned(
            envelope,
            expected_record_code=P0RecordCode.TOOL_CALL_RECORD,
            expected_schema_version="tool_call_record.p0.v2",
            correlation_ref=_uuid(699),
        )
    assert raised.value.category is P0PersistenceIntegrityCategory.CHILD_MISMATCH


def test_conversion_readiness_requires_explicit_exact_active_version_set() -> None:
    import inspect

    parameters = inspect.signature(
        persistence_module.classify_p0_conversion_readiness
    ).parameters
    assert parameters["active_schema_versions"].default is inspect.Parameter.empty
    assert parameters["active_schema_versions"].kind is inspect.Parameter.KEYWORD_ONLY

    input_case = _case(P0RecordCode.INPUT_BINDING_RECORD)
    with pytest.raises(TypeError):
        persistence_module.classify_p0_conversion_readiness(
            P0RecordCode.INPUT_BINDING_RECORD,
            "input_binding_record.p0.v1",
            "input_binding_record.p0.v2",
            input_case.record,
            external_references=input_case.external_references,
        )

    invalid_sets = (
        (),
        ("input_binding_record.p0.v1", "input_binding_record.p0.v1"),
        ("input_binding_record.p0.v1", "input_binding_record.p0.v2"),
        ("gate_decision_record.p0.v1",),
    )
    for active_versions in invalid_sets:
        result = persistence_module.classify_p0_conversion_readiness(
            P0RecordCode.INPUT_BINDING_RECORD,
            "input_binding_record.p0.v1",
            "input_binding_record.p0.v2",
            input_case.record,
            active_schema_versions=active_versions,
            external_references=input_case.external_references,
        )
        assert (
            result.category
            is persistence_module.P0ConversionReadinessCategory.MIXED_ACTIVE_VERSION
        )
        assert result.target_record is None


def test_tool_conversion_owner_and_registry_authority_are_not_free_inputs() -> None:
    import inspect

    parameters = inspect.signature(
        persistence_module.classify_p0_conversion_readiness
    ).parameters
    assert "private_owner_scope_ref" not in parameters
    assert "registry_snapshot" not in parameters

    tool_case = _case(P0RecordCode.TOOL_CALL_RECORD)
    with pytest.raises(TypeError):
        persistence_module.classify_p0_conversion_readiness(
            P0RecordCode.TOOL_CALL_RECORD,
            "tool_call_record.p0.v1",
            "tool_call_record.p0.v2",
            tool_case.record,
            active_schema_versions=("tool_call_record.p0.v1",),
            source_logical_children=tool_case.logical_children,
            private_owner_scope_ref="arbitrary-owner-a",
            registry_snapshot=build_cycle2_registry_snapshot(),
        )

    owner_mismatch = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=tool_case.logical_children,
        **{
            **_phase1_tool_owner_graph(),
            "owner_scope": _trusted_codec_owner_scope("customer-B"),
        },
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        owner_mismatch.category
        is persistence_module.P0ConversionReadinessCategory.CONTRADICTORY_GRAPH
    )

    forged_owner = TrustedOwnerScope.model_construct(customer_id="customer-A")
    forged = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=tool_case.logical_children,
        **{
            **_phase1_tool_owner_graph(),
            "owner_scope": forged_owner,
        },
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        forged.category
        is persistence_module.P0ConversionReadinessCategory.AUTHORITY_REQUIRED
    )

    wrong_source_snapshot = RegistrySnapshot.build(
        tool_registry_version="not-the-source-version",
        registrations=(
            _phase1_get_order_registry_snapshot().canonical_registrations[0],
        ),
    )
    registry_mismatch = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=tool_case.logical_children,
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=wrong_source_snapshot,
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        registry_mismatch.category
        is persistence_module.P0ConversionReadinessCategory.CONTRADICTORY_GRAPH
    )

    canonical_registration = (
        _phase1_get_order_registry_snapshot().canonical_registrations[0]
    )
    wrong_policy_registration = ToolRegistration(
        **{
            **canonical_registration.model_dump(),
            "execution_policy": ExecutionPolicy(
                timeout_ms=500,
                max_attempts=2,
                retryable_failure_codes=("TOOL_CALL_TIMEOUT",),
                interrupt_behavior="MARK_INTERRUPTED",
            ),
        }
    )
    wrong_policy_snapshot = RegistrySnapshot.build(
        tool_registry_version="e2e01-thin-tools-v1",
        registrations=(wrong_policy_registration,),
    )
    policy_mismatch = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        tool_case.record,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=tool_case.logical_children,
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=wrong_policy_snapshot,
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        policy_mismatch.category
        is persistence_module.P0ConversionReadinessCategory.CONTRADICTORY_GRAPH
    )


def test_phase1_get_order_timeout_converts_to_exact_max_attempts_decision() -> None:
    attempt = ToolAttemptRecord(
        tool_call_id=_uuid(701),
        attempt_no=1,
        started_at=UTC_NOW,
        finished_at=UTC_NOW + timedelta(milliseconds=500),
        outcome="TIMEOUT",
        failure_code="TOOL_CALL_TIMEOUT",
    )
    parent = ToolCallRecord(
        tool_call_id=attempt.tool_call_id,
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
        status=ToolCallStatus.TIMED_OUT,
        started_at=UTC_NOW,
        finished_at=attempt.finished_at,
        failure_code="TOOL_CALL_TIMEOUT",
        timeout_phase="AFTER_DISPATCH",
    )
    directly_converted = persistence_module._convert_tool_attempts_v1_to_v2(
        parent,
        (attempt,),
        build_cycle2_registry_snapshot(),
    )
    assert directly_converted[0].retry_decision.value == "MAX_ATTEMPTS_REACHED"

    result = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        parent,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=(attempt,),
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert result.is_ready
    converted_attempt = result.target_logical_children[0]
    assert converted_attempt.timeout_phase.value == "AFTER_DISPATCH"
    assert converted_attempt.retry_decision.value == "MAX_ATTEMPTS_REACHED"

    ambiguous_parent = parent.model_copy(
        update={
            "canonical_tool_name": "get_shipment",
            "tool_registry_version": "e2e01-cycle2-tools.p0.v1",
        }
    )
    ambiguous_attempt = attempt.model_copy(
        update={"tool_call_id": ambiguous_parent.tool_call_id}
    )
    with pytest.raises(LookupError):
        persistence_module._convert_tool_attempts_v1_to_v2(
            ambiguous_parent,
            (ambiguous_attempt,),
            build_cycle2_registry_snapshot(),
        )

    contradictory_attempt = attempt.model_copy(
        update={"failure_code": "ORDER_SERVICE_UNAVAILABLE"}
    )
    contradictory = persistence_module.classify_p0_conversion_readiness(
        P0RecordCode.TOOL_CALL_RECORD,
        "tool_call_record.p0.v1",
        "tool_call_record.p0.v2",
        parent,
        active_schema_versions=("tool_call_record.p0.v1",),
        source_logical_children=(contradictory_attempt,),
        **_phase1_tool_owner_graph(),
        source_registry_snapshot=_phase1_get_order_registry_snapshot(),
        target_registry_snapshot=build_cycle2_registry_snapshot(),
    )
    assert (
        contradictory.category
        is persistence_module.P0ConversionReadinessCategory.CONTRADICTORY_GRAPH
    )
