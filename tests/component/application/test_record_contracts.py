from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from mini_agent.application.records import (
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateRunCommand,
    CreateRequestUnitCommand,
    CreateRunTaskLinkCommand,
    CreateTaskCommand,
    CreateToolCallCommand,
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
    FinalizeToolCallCommand,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    MessageDirection,
    MessageRecord,
    RunTaskLinkRecord,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.common import ContractVisibility
from mini_agent.core.identity import CustomerContext
from mini_agent.core.task_state import RequestUnitRecord, TaskRecord, TaskStatus
from mini_agent.core.tool_system import (
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
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
    assert (
        ConversationRecord.contract_visibility is ContractVisibility.RUNTIME_PRIVATE
    )
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
    assert (
        TrustedOwnerScope.contract_visibility
        is ContractVisibility.RUNTIME_PRIVATE
    )
    assert TrustedOwnerScope.model_config["strict"] is True
    assert TrustedOwnerScope.model_config["frozen"] is True
    assert TrustedOwnerScope.model_config["extra"] == "forbid"
    assert "subject_ref" not in owner_scope.model_dump()
    assert "auth_scopes" not in owner_scope.model_dump()
    assert "authenticated_at" not in owner_scope.model_dump()
    assert "session_ref_hash" not in owner_scope.model_dump()
    with pytest.raises(ValidationError, match="derived from CustomerContext"):
        TrustedOwnerScope(customer_id="customer-A")
    with pytest.raises(ValidationError, match="must match CustomerContext"):
        TrustedOwnerScope.model_validate(
            {"customer_id": "customer-B"},
            context={"customer_context": context},
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        TrustedOwnerScope.model_validate(
            {
                "customer_id": "customer-A",
                "session_ref_hash": "must-not-cross-port",
            },
            context={"customer_context": context},
        )


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


def test_run_commands_freeze_insert_normal_transition_and_recovery_claim() -> None:
    created = _run()
    running = _project_run(created, status=AgentRunStatus.RUNNING)
    completed_at = UTC_NOW + timedelta(milliseconds=1)
    completed = _project_run(
        running,
        status=AgentRunStatus.COMPLETED,
        completed_at=completed_at,
        stop_reason=StopReason.GOAL_COMPLETED,
    )
    incomplete = _project_run(
        running,
        status=AgentRunStatus.INCOMPLETE,
        completed_at=completed_at,
        stop_reason=StopReason.PROCESS_RESTART_DETECTED,
    )

    assert CreateRunCommand(created_record=created).created_record.status is (
        AgentRunStatus.CREATED
    )
    assert TransitionRunCommand(
        expected_active_record=created,
        next_record=running,
    ).next_record.status is AgentRunStatus.RUNNING
    assert TransitionRunCommand(
        expected_active_record=running,
        next_record=completed,
    ).next_record.status is AgentRunStatus.COMPLETED
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
    with pytest.raises(ValidationError, match="move status forward"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=running,
        )
    with pytest.raises(ValidationError, match="cannot create CREATED or INCOMPLETE"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=incomplete,
        )
    with pytest.raises(ValidationError, match="recovery-only stop reason"):
        TransitionRunCommand(
            expected_active_record=running,
            next_record=_project_run(
                completed,
                stop_reason=StopReason.PROCESS_RESTART_DETECTED,
            ),
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
        CreateRequestUnitCommand(
            initial_record=_request_unit(state_version=2)
        )
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


def test_eval_projection_uses_explicit_validated_details() -> None:
    result = _eval_result()

    assert result.version_manifest.dataset_version == "e2e01-thin-dataset-v1"
    assert result.version_manifest.candidate_version == "candidate-source-revision"
    assert result.version_manifest.baseline_version is None
    assert result.version_manifest.fixture_versions == (
        "e2e01-thin-fixture-v1",
    )
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
        EvalExecutionFailurePhase.GRADING: (
            EvalExecutionSafeErrorCode.GRADING_FAILED
        ),
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
