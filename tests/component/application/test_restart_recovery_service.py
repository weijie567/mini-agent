import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from mini_agent.application.records import (
    Cycle2DispatchFenceWriteResult,
    Cycle2ReadDispatchGrant,
    Cycle2RunBudgetPolicyEvidence,
    Cycle2WriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    SupersededRunInvalidationKind,
    SupersededRunReadClosure,
    TaskRecoveryAggregate,
    ToolCallRecoveryAggregate,
    ToolRetryRecoveryReadClosureV2,
    TrustedOwnerScope,
)
from mini_agent.application.restart_recovery_service import (
    Cycle2ToolRestartRecoveryService,
    RestartRecoveryService,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_understanding import InputAuthority
from mini_agent.core.task_state import (
    InputBindingV2,
    InputValidationStatus,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolRecoveryDisposition,
    ToolResultOutcome,
    ToolRetryDecision,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReason,
    StopReasonV2,
    TraceEventV2,
    TraceEventType,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class UuidSequence:
    def __init__(self) -> None:
        self.values = [uuid4() for _ in range(32)]
        self.index = 0

    def __call__(self) -> UUID:
        value = self.values[self.index]
        self.index += 1
        return value


class RecoveryPortSpy:
    def __init__(
        self,
        closure: RestartRecoveryClosure | None,
        write_result: RecoveryWriteResult,
    ) -> None:
        self.closure = closure
        self.write_result = write_result
        self.load_calls = 0
        self.apply_commands: list[object] = []

    async def load_next_restart_recovery_closure(
        self,
    ) -> RestartRecoveryClosure | None:
        self.load_calls += 1
        return self.closure

    async def claim_and_apply_restart_recovery(
        self,
        command: object,
    ) -> RecoveryWriteResult:
        self.apply_commands.append(command)
        return self.write_result


def _conversation() -> ConversationRecord:
    return ConversationRecord(
        schema_version="conversation_record.p0.v1",
        conversation_id=uuid4(),
        owner_customer_id="customer-A",
        created_at=NOW,
    )


def _run(
    *,
    conversation_id: UUID,
    status: AgentRunStatus,
) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=uuid4(),
        conversation_id=conversation_id,
        status=status,
        provider_lane="scripted",
        started_at=NOW,
    )


def _created_closure() -> RestartRecoveryClosure:
    conversation = _conversation()
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=conversation,
        active_run_record=_run(
            conversation_id=conversation.conversation_id,
            status=AgentRunStatus.CREATED,
        ),
        conversation_task_links=(),
        run_task_links=(),
        task_aggregates=(),
        request_unit_records=(),
        tool_call_aggregates=(),
    )


def _running_closure(
    *,
    include_tool: bool,
    effect: ToolEffect = ToolEffect.READ,
) -> RestartRecoveryClosure:
    conversation = _conversation()
    run = _run(
        conversation_id=conversation.conversation_id,
        status=AgentRunStatus.RUNNING,
    )
    task = TaskRecord(
        task_id=uuid4(),
        owner_customer_id=conversation.owner_customer_id,
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding_ref = uuid4()
    request_unit = RequestUnitRecord(
        request_unit_id=uuid4(),
        task_id=task.task_id,
        goal_text="查询订单",
        goal_source_refs=(uuid4(),),
        input_binding_refs=(binding_ref,),
        status=TaskStatus.ACTIVE,
        state_version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    tool_aggregates: tuple[ToolCallRecoveryAggregate, ...] = ()
    if include_tool:
        tool_call = ToolCallRecord(
            tool_call_id=uuid4(),
            run_id=run.run_id,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            model_call_id=uuid4(),
            context_manifest_id=uuid4(),
            gate_decision_id=uuid4(),
            canonical_tool_name=(
                "get_order" if effect is ToolEffect.READ else "create_refund"
            ),
            tool_registry_version="runtime-tools-v1",
            validated_task_state_version=1,
            argument_binding_refs=(binding_ref,),
            effect=effect,
            attempt_count=1,
            status=ToolCallStatus.RUNNING,
            started_at=NOW,
        )
        tool_aggregates = (
            ToolCallRecoveryAggregate(
                tool_call_record=tool_call,
                tool_attempt_records=(
                    ToolAttemptRecord(
                        tool_call_id=tool_call.tool_call_id,
                        attempt_no=1,
                        started_at=NOW,
                    ),
                ),
            ),
        )
    return RestartRecoveryClosure(
        closure_fence=uuid4(),
        conversation_record=conversation,
        active_run_record=run,
        conversation_task_links=(
            ConversationTaskLinkRecord(
                schema_version="conversation_task_link_record.p0.v1",
                conversation_id=conversation.conversation_id,
                task_id=task.task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=NOW,
            ),
        ),
        run_task_links=(
            RunTaskLinkRecord(
                schema_version="run_task_link_record.p0.v1",
                run_id=run.run_id,
                task_id=task.task_id,
                base_task_state_version=None,
            ),
        ),
        task_aggregates=(
            TaskRecoveryAggregate(
                task_record=task,
                task_state_transitions=(),
            ),
        ),
        request_unit_records=(request_unit,),
        tool_call_aggregates=tool_aggregates,
    )


def _recover(
    closure: RestartRecoveryClosure | None,
    write_result: RecoveryWriteResult = RecoveryWriteResult.APPLIED,
):
    port = RecoveryPortSpy(closure, write_result)
    service = RestartRecoveryService(
        restart_recovery_port=port,
        clock=lambda: NOW,
        uuid_factory=UuidSequence(),
    )
    result = asyncio.run(service.recover_pending())
    return result, port


def test_no_pending_closure_is_ready_without_apply_or_loop() -> None:
    result, port = _recover(None)

    assert result.ready is True
    assert result.closure_found is False
    assert result.write_result is None
    assert port.load_calls == 1
    assert port.apply_commands == []


def test_created_only_recovery_has_exact_single_run_stopped_event() -> None:
    closure = _created_closure()

    result, port = _recover(closure)

    assert result.ready is True
    assert result.write_result is RecoveryWriteResult.APPLIED
    assert port.load_calls == 1
    assert len(port.apply_commands) == 1
    command = port.apply_commands[0]
    assert command.expected_closure is closure
    assert command.task_transitions == ()
    assert command.tool_call_transitions == ()
    assert command.terminal_run_task_links == ()
    assert len(command.recovery_trace_events) == 1
    event = command.recovery_trace_events[0]
    assert event.event_type is TraceEventType.RUN_STOPPED
    assert event.user_outcome is AgentOutcome.BLOCKED
    assert event.stop_reason is StopReason.PROCESS_RESTART_DETECTED


def test_active_task_and_read_tool_have_exact_three_event_bijection() -> None:
    closure = _running_closure(include_tool=True)

    result, port = _recover(closure)

    assert result.ready is True
    command = port.apply_commands[0]
    assert len(command.task_transitions) == 1
    assert command.task_transitions[0].next_task_record.status is (
        TaskStatus.BLOCKED
    )
    assert command.task_transitions[0].next_task_record.state_version == 2
    assert len(command.tool_call_transitions) == 1
    assert command.tool_call_transitions[0].interrupted_record.status is (
        ToolCallStatus.INTERRUPTED
    )
    assert command.tool_call_transitions[0].interrupted_record.attempt_count == 1
    assert len(command.terminal_run_task_links) == 1
    assert (
        command.terminal_run_task_links[0].result_task_state_version == 2
    )
    assert tuple(event.event_type for event in command.recovery_trace_events) == (
        TraceEventType.RUN_STOPPED,
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.TOOL_CALL_INTERRUPTED,
    )


def test_running_action_returns_reconciliation_without_replay_or_state_claim() -> None:
    closure = _running_closure(
        include_tool=True,
        effect=ToolEffect.ACTION,
    )

    result, port = _recover(
        closure,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    )

    assert result.ready is False
    assert result.write_result is RecoveryWriteResult.RECONCILIATION_REQUIRED
    assert len(port.apply_commands) == 1
    command = port.apply_commands[0]
    assert command.tool_call_transitions[0].active_record.effect is (
        ToolEffect.ACTION
    )
    assert not hasattr(port, "append_trace_event")
    assert not hasattr(port, "resume")
    assert not hasattr(port, "execute_tool")


@pytest.mark.parametrize(
    "write_result",
    [
        RecoveryWriteResult.CLOSURE_CONFLICT,
        RecoveryWriteResult.NOT_APPLICABLE,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    ],
)
def test_every_non_applied_result_is_returned_non_ready_without_retry(
    write_result: RecoveryWriteResult,
) -> None:
    result, port = _recover(
        _running_closure(include_tool=False),
        write_result,
    )

    assert result.ready is False
    assert result.write_result is write_result
    assert port.load_calls == 1
    assert len(port.apply_commands) == 1


def test_recovery_service_surface_cannot_resume_replay_or_append_trace() -> None:
    public_methods = {
        name
        for name in dir(RestartRecoveryService)
        if not name.startswith("_")
    }

    assert public_methods == {"recover_pending"}
    assert all(
        forbidden not in public_methods
        for forbidden in (
            "resume",
            "replay",
            "execute",
            "append_trace_event",
        )
    )


class Cycle2RecoveryPortSpy:
    def __init__(
        self,
        closure: ToolRetryRecoveryReadClosureV2,
        *,
        fence_result: Cycle2DispatchFenceWriteResult = (
            Cycle2DispatchFenceWriteResult.APPLIED
        ),
        grant_mutation: str | None = None,
        effective_timeout_ms: int = 89,
        write_result: Cycle2WriteResult = Cycle2WriteResult.APPLIED,
        oa10_closure: SupersededRunReadClosure | None = None,
    ) -> None:
        self.closure = closure
        self.fence_result = fence_result
        self.grant_mutation = grant_mutation
        self.effective_timeout_ms = effective_timeout_ms
        self.write_result = write_result
        self.oa10_closure = oa10_closure
        self.commands: list[object] = []
        self.oa10_loads: list[dict[str, object]] = []

    async def load_tool_retry_recovery_closure_for_owner(self, **_kwargs):
        return self.closure

    async def append_recovered_tool_attempt_if_current(self, command):
        self.commands.append(command)
        if self.fence_result is not Cycle2DispatchFenceWriteResult.APPLIED:
            return Cycle2ReadDispatchGrant(write_result=self.fence_result)
        append = command.attempt_append_command
        attempt = append.started_attempt
        tool_call_id = append.expected_record.tool_call_id
        attempt_no = attempt.attempt_no
        trusted_fenced_at = attempt.started_at
        if self.grant_mutation == "tool_call_id":
            tool_call_id = uuid4()
        elif self.grant_mutation == "attempt_no":
            attempt_no = 1
        elif self.grant_mutation == "trusted_fenced_at":
            trusted_fenced_at = attempt.started_at - timedelta(microseconds=1)
        return Cycle2ReadDispatchGrant(
            write_result=self.fence_result,
            tool_call_id=tool_call_id,
            attempt_no=attempt_no,
            trusted_fenced_at=trusted_fenced_at,
            effective_timeout_ms=self.effective_timeout_ms,
        )

    async def finalize_created_tool_recovery_if_current(self, command):
        self.commands.append(command)
        return self.write_result

    async def finalize_unfinished_tool_recovery_if_current(self, command):
        self.commands.append(command)
        return self.write_result

    async def finalize_budget_exhausted_tool_recovery_if_current(self, command):
        self.commands.append(command)
        return self.write_result

    async def load_superseded_run_closure_for_owner(self, **kwargs):
        self.oa10_loads.append(kwargs)
        return self.oa10_closure

    async def finalize_state_invalidated_tool_recovery_if_current(self, command):
        self.commands.append(command)
        return self.write_result


def _cycle2_recovery_closure(
    *,
    created: bool = False,
    unfinished: bool = False,
    budget_ms: int = 10_000,
    current_state_version: int = 3,
) -> ToolRetryRecoveryReadClosureV2:
    owner = TrustedOwnerScope.from_customer_context(
        CustomerContext(
            subject_ref="subject-A",
            customer_id="customer-A",
            auth_scopes=frozenset({"orders:read"}),
            authenticated_at=NOW,
            session_ref_hash="safe-session-A",
        )
    )
    binding = InputBindingV2(
        binding_id=uuid4(),
        name="order_id",
        normalized_value="O-1001",
        authority=InputAuthority.USER_CLAIM,
        source_refs=(uuid4(),),
        validation_status=InputValidationStatus.ACCEPTED,
        confirmed_by_user=True,
        created_at=NOW,
        updated_at=NOW,
    )
    task = TaskRecord(
        task_id=uuid4(),
        owner_customer_id=owner.customer_id,
        status=TaskStatus.ACTIVE,
        state_version=current_state_version,
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=current_state_version - 3),
    )
    unit = RequestUnitRecord(
        request_unit_id=uuid4(),
        task_id=task.task_id,
        goal_text="查询订单",
        goal_source_refs=(uuid4(),),
        input_binding_refs=(binding.binding_id,),
        status=task.status,
        state_version=current_state_version,
        created_at=NOW,
        updated_at=task.updated_at,
    )
    run = AgentRunRecordV2(
        run_id=uuid4(),
        conversation_id=uuid4(),
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=NOW,
    )
    tool_call_id = uuid4()
    attempts = ()
    if not created:
        attempts = (
            ToolAttemptRecordV2(
                tool_call_id=tool_call_id,
                attempt_no=1,
                started_at=NOW,
                **(
                    {}
                    if unfinished
                    else {
                        "finished_at": NOW,
                        "outcome": ToolResultOutcome.SYSTEM_FAILURE,
                        "failure_code": "ORDER_SEARCH_TRANSIENT",
                        "retry_decision": ToolRetryDecision.RETRY_SCHEDULED,
                    }
                ),
            ),
        )
    tool = ToolCallRecordV2(
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
        status=ToolCallStatus.CREATED if created else ToolCallStatus.RUNNING,
        started_at=NOW,
    )
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
        tool_call_record=tool,
        recovery_decision_records=(),
        trusted_read_at=NOW + timedelta(seconds=current_state_version - 2),
        run_budget_policy=Cycle2RunBudgetPolicyEvidence(
            policy_version="cycle2-test-budget.v1",
            run_time_budget_ms=budget_ms,
        ),
    )


def _oa10_closure(
    closure: ToolRetryRecoveryReadClosureV2,
    *,
    replacement_run_id: UUID,
) -> SupersededRunReadClosure:
    current_task = closure.current_task_record
    current_unit = closure.current_request_unit_record
    replacement_run = AgentRunRecordV2(
        run_id=replacement_run_id,
        conversation_id=closure.active_run_record.conversation_id,
        status=AgentRunStatusV2.RUNNING,
        provider_lane="scripted",
        started_at=NOW + timedelta(seconds=1),
    )
    obsolete_task = TaskRecord.model_validate(
        {
            **current_task.model_dump(mode="python"),
            "state_version": 3,
            "updated_at": NOW,
        },
        strict=True,
    )
    obsolete_unit = RequestUnitRecord.model_validate(
        {
            **current_unit.model_dump(mode="python"),
            "state_version": 3,
            "updated_at": NOW,
        },
        strict=True,
    )
    return SupersededRunReadClosure(
        owner_scope=closure.owner_scope,
        trusted_conversation_record=ConversationRecord(
            schema_version="conversation_record.p0.v1",
            conversation_id=closure.active_run_record.conversation_id,
            owner_customer_id=closure.owner_scope.customer_id,
            created_at=NOW,
        ),
        expected_active_run_record=closure.active_run_record,
        expected_active_link_record=closure.active_run_task_link_record,
        current_authoritative_run_record=replacement_run,
        current_authoritative_link_record=RunTaskLinkRecordV2(
            run_id=replacement_run_id,
            task_id=current_task.task_id,
            base_task_state_version=current_task.state_version,
        ),
        current_task_record=current_task,
        current_request_unit_record=current_unit,
        obsolete_task_record=obsolete_task,
        obsolete_request_unit_record=obsolete_unit,
        trusted_current_evidence_at=closure.trusted_read_at,
        invalidation_kind=SupersededRunInvalidationKind.TASK_VERSION_ADVANCED,
    )


@pytest.mark.parametrize("created,unfinished", [(True, False), (False, True)])
def test_cycle2_created_and_unfinished_recovery_never_grant_dispatch(
    created: bool,
    unfinished: bool,
) -> None:
    closure = _cycle2_recovery_closure(created=created, unfinished=unfinished)
    port = Cycle2RecoveryPortSpy(closure)
    service = Cycle2ToolRestartRecoveryService(
        runtime_record_port=port,
        uuid_factory=UuidSequence(),
    )

    terminal, attempt, result = asyncio.run(
        service.recover_tool_call(
            owner_scope=closure.owner_scope,
            tool_call_id=closure.tool_call_record.tool_call_id,
        )
    )

    assert result is Cycle2WriteResult.APPLIED
    assert attempt is None
    assert terminal.status is ToolCallStatus.INTERRUPTED
    assert terminal.attempts == closure.tool_call_record.attempts
    if created:
        assert terminal.attempt_count == 0
        assert terminal.recovery_decision_ref is None
        assert not hasattr(port.commands[0], "recovery_decision_record")
    else:
        assert terminal.recovery_disposition is (
            ToolRecoveryDisposition.UNFINISHED_ATTEMPT_INTERRUPTED
        )
        command = port.commands[0]
        assert command.task_transition.expected_task_record is (
            closure.current_task_record
        )
        assert command.task_transition.next_task_record.status is (
            TaskStatus.BLOCKED
        )
        assert command.task_transition.next_task_record.state_version == 4
        assert command.task_transition.next_request_unit_record.status is (
            TaskStatus.BLOCKED
        )
        assert command.terminal_run_record.status is (
            AgentRunStatusV2.INCOMPLETE
        )
        assert command.terminal_run_record.stop_reason is (
            StopReasonV2.PROCESS_RESTART_DETECTED
        )
        assert command.terminal_run_task_link_record.result_task_state_version == 4
        assert tuple(
            trace.event_type for trace in command.recovery_trace_records
        ) == (
            TraceEventType.RUN_STOPPED,
            TraceEventType.TASK_STATE_CHANGED,
            TraceEventType.TOOL_CALL_INTERRUPTED,
        )
        assert not hasattr(command, "terminal_result")
        assert not hasattr(command, "assistant_message_record")


def test_cycle2_recovered_append_returns_only_exact_applied_dispatch_grant() -> None:
    closure = _cycle2_recovery_closure()
    for fence_result in Cycle2DispatchFenceWriteResult:
        port = Cycle2RecoveryPortSpy(closure, fence_result=fence_result)
        service = Cycle2ToolRestartRecoveryService(
            runtime_record_port=port,
            uuid_factory=UuidSequence(),
        )

        record, attempt, grant = asyncio.run(
            service.recover_tool_call(
                owner_scope=closure.owner_scope,
                tool_call_id=closure.tool_call_record.tool_call_id,
            )
        )

        assert type(grant) is Cycle2ReadDispatchGrant
        assert grant.write_result is fence_result
        if fence_result is Cycle2DispatchFenceWriteResult.APPLIED:
            assert attempt is not None and attempt.attempt_no == 2
            assert record.attempts[0] == closure.tool_call_record.attempts[0]
            assert grant.tool_call_id == record.tool_call_id
            assert grant.attempt_no == attempt.attempt_no
            assert grant.trusted_fenced_at == attempt.started_at
            assert grant.effective_timeout_ms == 89
        else:
            assert attempt is None
            assert record == closure.tool_call_record
            assert grant.tool_call_id is None
            assert grant.effective_timeout_ms is None


@pytest.mark.parametrize(
    "mutation",
    ["tool_call_id", "attempt_no", "trusted_fenced_at"],
)
def test_cycle2_malformed_applied_recovery_grant_has_no_dispatch_authority(
    mutation: str,
) -> None:
    closure = _cycle2_recovery_closure()
    port = Cycle2RecoveryPortSpy(closure, grant_mutation=mutation)
    service = Cycle2ToolRestartRecoveryService(
        runtime_record_port=port,
        uuid_factory=UuidSequence(),
    )

    record, attempt, grant = asyncio.run(
        service.recover_tool_call(
            owner_scope=closure.owner_scope,
            tool_call_id=closure.tool_call_record.tool_call_id,
        )
    )

    assert record == closure.tool_call_record
    assert attempt is None
    assert type(grant) is Cycle2ReadDispatchGrant
    assert grant.write_result is Cycle2DispatchFenceWriteResult.APPLIED
    assert len(port.commands) == 1


def test_cycle2_budget_exhaustion_preserves_attempt_one_and_has_no_result() -> None:
    closure = _cycle2_recovery_closure(budget_ms=500)
    port = Cycle2RecoveryPortSpy(closure)
    service = Cycle2ToolRestartRecoveryService(
        runtime_record_port=port,
        uuid_factory=UuidSequence(),
    )

    terminal, attempt, result = asyncio.run(
        service.recover_tool_call(
            owner_scope=closure.owner_scope,
            tool_call_id=closure.tool_call_record.tool_call_id,
        )
    )

    assert result is Cycle2WriteResult.APPLIED
    assert attempt is None
    assert terminal.attempts == closure.tool_call_record.attempts
    assert terminal.status is ToolCallStatus.FAILED
    assert terminal.result_ref is None
    assert terminal.recovery_disposition is (
        ToolRecoveryDisposition.RETRY_SCHEDULED_RUN_BUDGET_EXHAUSTED
    )


def test_cycle2_state_invalidation_composes_exact_oa10_no_result_closure() -> None:
    closure = _cycle2_recovery_closure(current_state_version=4)
    replacement_run_id = uuid4()
    oa10_closure = _oa10_closure(closure, replacement_run_id=replacement_run_id)
    port = Cycle2RecoveryPortSpy(closure, oa10_closure=oa10_closure)
    service = Cycle2ToolRestartRecoveryService(
        runtime_record_port=port,
        uuid_factory=UuidSequence(),
    )

    terminal, attempt, result = asyncio.run(
        service.recover_tool_call(
            owner_scope=closure.owner_scope,
            tool_call_id=closure.tool_call_record.tool_call_id,
            replacement_run_id=replacement_run_id,
        )
    )

    assert result is Cycle2WriteResult.APPLIED
    assert attempt is None
    assert terminal.status is ToolCallStatus.INTERRUPTED
    assert terminal.result_ref is None
    assert terminal.attempts == closure.tool_call_record.attempts
    assert terminal.recovery_disposition is (
        ToolRecoveryDisposition.RETRY_SCHEDULED_STATE_INVALIDATED
    )
    assert port.oa10_loads == [
        {
            "owner_scope": closure.owner_scope,
            "obsolete_run_id": closure.active_run_record.run_id,
            "replacement_run_id": replacement_run_id,
            "request_unit_id": closure.current_request_unit_record.request_unit_id,
        }
    ]
    command = port.commands[0]
    oa10 = command.superseded_run_command
    assert oa10.superseded_run_record.status is AgentRunStatusV2.SUPERSEDED
    assert oa10.superseded_run_record.stop_reason is (
        StopReasonV2.STATE_OR_BINDING_INVALIDATED
    )
    assert oa10.no_result_link_record.result_task_state_version is None
    assert oa10.run_stopped_trace_record == TraceEventV2.model_validate(
        oa10.run_stopped_trace_record.model_dump(mode="python"),
        strict=True,
    )
    assert {
        "task_record",
        "request_unit_record",
        "message_record",
        "agent_run_result",
        "result_ref",
    }.isdisjoint(type(command).model_fields)


@pytest.mark.parametrize(
    "write_result",
    [
        Cycle2WriteResult.ALREADY_APPLIED,
        Cycle2WriteResult.PROJECTION_CONFLICT,
        Cycle2WriteResult.NOT_APPLICABLE,
    ],
)
def test_cycle2_non_applied_terminal_recovery_returns_source_and_stops(
    write_result: Cycle2WriteResult,
) -> None:
    closure = _cycle2_recovery_closure(created=True)
    port = Cycle2RecoveryPortSpy(closure, write_result=write_result)
    service = Cycle2ToolRestartRecoveryService(
        runtime_record_port=port,
        uuid_factory=UuidSequence(),
    )

    returned, attempt, result = asyncio.run(
        service.recover_tool_call(
            owner_scope=closure.owner_scope,
            tool_call_id=closure.tool_call_record.tool_call_id,
        )
    )

    assert returned == closure.tool_call_record
    assert attempt is None
    assert result is write_result
    assert len(port.commands) == 1
    assert port.oa10_loads == []
