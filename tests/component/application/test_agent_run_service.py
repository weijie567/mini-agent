import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

import mini_agent.application.agent_run_service as agent_run_service_module
from mini_agent.application.agent_run_service import (
    AgentRunExecutionError,
    AgentRunService,
)
from mini_agent.application.deterministic_renderer import (
    DeterministicRenderer,
    RendererInvariantError,
)
from mini_agent.application.read_tool_executor import ReadToolExecutor
from mini_agent.application.records import (
    AgentRunCommand,
    ConditionalWriteResult,
    InsertOnlyWriteResult,
    MessageDirection,
    ObservationWriteResult,
    ProviderProtocolError,
    ToolDispatchFenceWriteResult,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import TokenCounts
from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderQuery,
    GetOrderResult,
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
    PresentationTone,
)
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.core.task_state import (
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    GateReasonCode,
    RegistrySnapshot,
    ToolCallStatus,
    ToolEffect,
    ToolRegistration,
    get_order_tool_spec,
)
from mini_agent.core.trace import (
    AgentOutcome,
    StopReason,
    TraceEvent,
    TraceEventType,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class UuidSequence:
    def __init__(self) -> None:
        self.values = [uuid4() for _ in range(256)]
        self.index = 0

    def __call__(self) -> UUID:
        value = self.values[self.index]
        self.index += 1
        return value


class ArtifactSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.artifact: object | None = None

    async def put_toolset_artifact(self, artifact: object) -> None:
        self.events.append("artifact_put")
        self.artifact = artifact

    async def get_toolset_artifact(self, model_visible_toolset_hash: str):
        self.events.append("artifact_get")
        if (
            self.artifact is not None
            and self.artifact.model_visible_toolset_hash
            == model_visible_toolset_hash
        ):
            return self.artifact
        return None


class ConversationSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.conversations: list[object] = []
        self.messages: list[object] = []

    async def save_conversation(self, record: object) -> None:
        self.events.append("conversation_saved")
        self.conversations.append(record)

    async def append_message(self, record: object) -> None:
        direction = getattr(record, "direction")
        self.events.append(f"message:{direction.value}")
        self.messages.append(record)


class RuntimeSpy:
    def __init__(
        self,
        events: list[str],
        *,
        graph_result: ConditionalWriteResult = ConditionalWriteResult.APPLIED,
        finalize_run_result: ConditionalWriteResult = (
            ConditionalWriteResult.APPLIED
        ),
    ) -> None:
        self.events = events
        self.graph_result = graph_result
        self.finalize_run_result = finalize_run_result
        self.run_record: object | None = None
        self.task: TaskRecord | None = None
        self.request_unit: RequestUnitRecord | None = None
        self.input_binding: object | None = None
        self.run_task_link: object | None = None
        self.task_history: list[TaskRecord] = []
        self.request_unit_history: list[RequestUnitRecord] = []
        self.manifests: list[object] = []
        self.gates: list[object] = []
        self.create_tool_commands: list[object] = []
        self.dispatch_tool_commands: list[object] = []
        self.finalize_tool_commands: list[object] = []
        self.observation_commands: list[object] = []
        self.trace_events: list[TraceEvent] = []
        self.finalize_run_commands: list[object] = []

    async def insert_run(self, command: object) -> InsertOnlyWriteResult:
        self.events.append("run_inserted")
        self.run_record = command.created_record
        return InsertOnlyWriteResult.INSERTED

    async def start_run_if_created(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("run_started")
        self.run_record = command.next_record
        return ConditionalWriteResult.APPLIED

    async def finalize_run_if_active(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("run_finalized")
        self.finalize_run_commands.append(command)
        if self.finalize_run_result is ConditionalWriteResult.APPLIED:
            self.run_record = command.terminal_record
            if command.result_task_records:
                self.task = command.result_task_records[0]
        return self.finalize_run_result

    async def create_initial_task_graph_if_current(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("initial_graph_saved")
        if self.graph_result is ConditionalWriteResult.APPLIED:
            self.task = command.initial_task.initial_record
            self.request_unit = command.initial_request_unit.initial_record
            self.input_binding = command.input_bindings[0].record
            self.run_task_link = command.run_task_link.active_record
            self.task_history.append(self.task)
            self.request_unit_history.append(self.request_unit)
        return self.graph_result

    async def apply_task_transition_if_current(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append(
            f"task_transition:{command.next_task_record.status.value}:"
            f"v{command.next_task_record.state_version}"
        )
        if (
            self.task != command.expected_task_record
            or self.request_unit != command.expected_request_unit_record
        ):
            return ConditionalWriteResult.PROJECTION_CONFLICT
        self.task = command.next_task_record
        self.request_unit = command.next_request_unit_record
        self.task_history.append(self.task)
        self.request_unit_history.append(self.request_unit)
        return ConditionalWriteResult.APPLIED

    async def save_context_manifest(self, record: object) -> None:
        self.events.append(f"manifest:{len(self.manifests) + 1}")
        self.manifests.append(record)

    async def save_gate_decision(self, record: object) -> None:
        self.events.append("gate_saved")
        self.gates.append(record)

    async def insert_tool_call(self, command: object) -> InsertOnlyWriteResult:
        self.events.append("tool_call_created")
        self.create_tool_commands.append(command)
        return InsertOnlyWriteResult.INSERTED

    async def start_tool_call_if_created(
        self,
        command: object,
    ) -> ToolDispatchFenceWriteResult:
        self.events.append("dispatch_fence")
        self.dispatch_tool_commands.append(command)
        return ToolDispatchFenceWriteResult.APPLIED

    async def finalize_tool_call_attempt_if_running(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("tool_call_finalized")
        self.finalize_tool_commands.append(command)
        return ConditionalWriteResult.APPLIED

    async def save_observation(
        self,
        command: object,
    ) -> ObservationWriteResult:
        self.events.append("observation_saved")
        self.observation_commands.append(command)
        return ObservationWriteResult.INSERTED

    async def append_trace_event(self, record: TraceEvent) -> None:
        self.events.append(f"trace:{record.event_type.value}")
        self.trace_events.append(record)

    async def load_task_for_owner(
        self,
        *,
        owner_scope: object,
        task_id: UUID,
    ) -> TaskRecord | None:
        self.events.append("task_reloaded")
        if self.task is not None and self.task.task_id == task_id:
            return self.task
        return None

    async def load_request_unit_for_owner(
        self,
        *,
        owner_scope: object,
        request_unit_id: UUID,
    ) -> RequestUnitRecord | None:
        self.events.append("request_unit_reloaded")
        if (
            self.request_unit is not None
            and self.request_unit.request_unit_id == request_unit_id
        ):
            return self.request_unit
        return None


class OrderSpy:
    def __init__(
        self,
        events: list[str],
        result: GetOrderResult,
    ) -> None:
        self.events = events
        self.result = result
        self.queries: list[GetOrderQuery] = []

    async def get_order(self, query: GetOrderQuery) -> GetOrderResult:
        self.events.append("order_read")
        self.queries.append(query)
        return self.result


class ModelSpy:
    def __init__(
        self,
        events: list[str],
        *,
        bound_order_id: str = "O-1001",
        proposed_order_id: str = "O-1001",
        requested_tool_name: str = "get_order",
        ru_protocol_error: bool = False,
        input_fault: bool = False,
        presentation_protocol_error: bool = False,
    ) -> None:
        self.events = events
        self.bound_order_id = bound_order_id
        self.proposed_order_id = proposed_order_id
        self.requested_tool_name = requested_tool_name
        self.ru_protocol_error = ru_protocol_error
        self.input_fault = input_fault
        self.presentation_protocol_error = presentation_protocol_error
        self.next_move_calls = 0
        self.presentation_calls = 0

    async def propose_next_move(self, request: object):
        self.events.append("provider:request_understanding")
        self.next_move_calls += 1
        if self.ru_protocol_error:
            raise ProviderProtocolError()
        message_ref = request.message_ref
        output = RequestUnderstandingOutput(
            message_ref=message_ref,
            task_delta_candidates=(
                TaskDeltaCandidate(
                    candidate_id=uuid4(),
                    operation=TaskDeltaOperation.ADD_GOAL,
                    goal_patch="查询当前消息中的订单状态",
                    input_candidates=(
                        InputCandidate(
                            name="order_id",
                            candidate_value=self.bound_order_id,
                            semantic_role="TARGET_RESOURCE_IDENTIFIER",
                            authority=InputAuthority.USER_CLAIM,
                            source_kind=InputSourceKind.CURRENT_MESSAGE,
                            source_ref=message_ref,
                            source_quote=f"订单 {self.bound_order_id}",
                            confidence=0.99,
                        ),
                    ),
                    confidence=0.98,
                ),
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name=self.requested_tool_name,
                arguments={"order_id": self.proposed_order_id},
                base_task_state_version=None,
            ),
        )
        if self.input_fault:
            bad_candidate = output.task_delta_candidates[0].input_candidates[
                0
            ].model_copy(update={"authority": "MODEL_INFERENCE"})
            output = output.model_copy(
                update={
                    "task_delta_candidates": (
                        output.task_delta_candidates[0].model_copy(
                            update={"input_candidates": (bad_candidate,)}
                        ),
                    )
                }
            )
        return output

    async def plan_presentation(self, request: object) -> PresentationPlan:
        self.events.append("provider:presentation")
        self.presentation_calls += 1
        if self.presentation_protocol_error:
            raise ProviderProtocolError()
        return PresentationPlan(
            template_id="ORDER_STATUS_SUMMARY_V1",
            tone=PresentationTone.WARM,
            opening_variant=OpeningVariant.ACKNOWLEDGE,
            field_order=tuple(PresentationField),
            closing_variant=ClosingVariant.OFFER_FOLLOW_UP,
        )


class FailingRenderer:
    def __init__(self) -> None:
        self.delegate = DeterministicRenderer()
        self.render_calls = 0

    def render_order_summary(self, **_: object) -> str:
        self.render_calls += 1
        raise RendererInvariantError("bounded renderer failure")

    def map_result(self, **kwargs: object):
        return self.delegate.map_result(**kwargs)


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot.build(
        tool_registry_version="runtime-tools-v1",
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


def _context() -> CustomerContext:
    return CustomerContext(
        subject_ref="subject-A",
        customer_id="customer-A",
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="sha256:session-A",
    )


def _found_result() -> GetOrderResult:
    return GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
            ordered_at=NOW,
            status_updated_at=NOW,
        ),
    )


def _build(
    *,
    model: ModelSpy | None = None,
    order_result: GetOrderResult | None = None,
    runtime: RuntimeSpy | None = None,
    renderer: object | None = None,
    after_revalidation_hook: object | None = None,
):
    events: list[str] = model.events if model is not None else []
    actual_model = model or ModelSpy(events)
    actual_runtime = runtime or RuntimeSpy(events)
    artifact = ArtifactSpy(events)
    conversation = ConversationSpy(events)
    order = OrderSpy(events, order_result or _found_result())
    ids = UuidSequence()
    read_executor = ReadToolExecutor(
        runtime_record_port=actual_runtime,
        get_order_port=order,
        clock=lambda: NOW,
        uuid_factory=ids,
    )
    service = AgentRunService(
        model_provider=actual_model,
        registry_snapshot=_snapshot(),
        toolset_artifact_port=artifact,
        conversation_record_port=conversation,
        runtime_record_port=actual_runtime,
        read_tool_executor=read_executor,
        deterministic_renderer=renderer or DeterministicRenderer(),
        clock=lambda: NOW,
        uuid_factory=ids,
        provider_lane="scripted",
        redaction_policy_version="redaction-v1",
        after_revalidation_hook=after_revalidation_hook,
    )
    return (
        service,
        events,
        actual_model,
        actual_runtime,
        conversation,
        order,
        artifact,
    )


def _run(service: AgentRunService, order_id: str = "O-1001"):
    return asyncio.run(
        service.handle(
            AgentRunCommand(
                customer_context=_context(),
                message=f"请查询订单 {order_id}",
            )
        )
    )


def _index(events: list[str], value: str) -> int:
    return events.index(value)


def test_success_trajectory_has_exact_budgets_ordering_and_safe_trace() -> None:
    service, events, model, runtime, conversation, order, _artifact = _build()

    result = _run(service)

    assert result.outcome is AgentOutcome.COMPLETED
    assert "O-1001" in result.message
    assert model.next_move_calls == 1
    assert model.presentation_calls == 1
    assert len(runtime.create_tool_commands) == 1
    assert len(order.queries) == 1
    assert order.queries[0].customer_id == "customer-A"
    assert len(runtime.observation_commands) == 1
    assert len(runtime.manifests) == 2
    assert all(
        manifest.token_counts
        == TokenCounts(input_tokens=None, output_tokens=None)
        for manifest in runtime.manifests
    )
    assert runtime.task_history[0].status is TaskStatus.ACTIVE
    assert runtime.task_history[0].state_version == 1
    assert runtime.task_history[-1].status is TaskStatus.COMPLETED
    assert runtime.task_history[-1].state_version == 2
    assert conversation.messages[0].direction is MessageDirection.USER
    assert conversation.messages[-1].direction is MessageDirection.ASSISTANT

    assert _index(events, "artifact_get") < _index(events, "manifest:1")
    assert _index(events, "message:USER") < _index(
        events, "provider:request_understanding"
    )
    assert _index(events, "initial_graph_saved") < _index(events, "gate_saved")
    assert _index(events, "gate_saved") < _index(events, "tool_call_created")
    assert _index(events, "dispatch_fence") < _index(events, "order_read")
    assert _index(events, "observation_saved") < _index(events, "manifest:2")
    assert _index(events, "manifest:2") < _index(
        events, "provider:presentation"
    )
    assert _index(events, "task_transition:COMPLETED:v2") < _index(
        events, "run_finalized"
    )
    assert _index(events, "run_finalized") < events.index(
        "message:ASSISTANT"
    )

    trace_dump = " ".join(
        str(event.model_dump(mode="json")) for event in runtime.trace_events
    )
    assert "customer-A" not in trace_dump
    assert "轻量跑鞋" not in trace_dump
    assert "raw" not in trace_dump.casefold()
    assert any(
        event.event_type is TraceEventType.GATE_DECISION_RECORDED
        for event in runtime.trace_events
    )
    assert runtime.trace_events[-1].event_type is TraceEventType.RUN_STOPPED
    assert runtime.trace_events[-1].stop_reason is StopReason.GOAL_COMPLETED


@pytest.mark.parametrize("order_id", ["O-2001", "O-9999"])
def test_foreign_and_nonexistent_are_identical_and_skip_presentation(
    order_id: str,
) -> None:
    events: list[str] = []
    model = ModelSpy(
        events,
        bound_order_id=order_id,
        proposed_order_id=order_id,
    )
    service, _events, model, runtime, _conversation, order, _artifact = _build(
        model=model,
        order_result=GetOrderResult(
            outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
        ),
    )

    result = _run(service, order_id)

    assert result.outcome is AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
    assert result.message == "未找到可访问的订单，请核对订单号后重试。"
    assert model.next_move_calls == 1
    assert model.presentation_calls == 0
    assert len(runtime.create_tool_commands) == 1
    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert len(runtime.manifests) == 1
    assert runtime.task_history[-1].status is TaskStatus.COMPLETED
    assert runtime.task_history[-1].state_version == 2
    assert runtime.run_record.stop_reason is StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE


@pytest.mark.parametrize("replacement", ["O-2001", "O-9999"])
def test_argument_replacement_stops_at_gateway_with_zero_tool_side_effect(
    replacement: str,
) -> None:
    events: list[str] = []
    model = ModelSpy(events, proposed_order_id=replacement)
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert runtime.gates[-1].reason_code is (
        GateReasonCode.ARGUMENT_BINDING_MISMATCH
    )
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.observation_commands == []
    assert runtime.task_history[-1].status is TaskStatus.BLOCKED
    assert runtime.task_history[-1].state_version == 2


def test_unknown_tool_stops_at_gateway_with_zero_tool_side_effect() -> None:
    events: list[str] = []
    model = ModelSpy(events, requested_tool_name="delete_order")
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert runtime.gates[-1].reason_code is GateReasonCode.TOOL_NOT_REGISTERED
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.observation_commands == []
    assert runtime.task_history[-1].state_version == 2


def test_stale_hook_advances_v2_then_gateway_blocks_v3_without_tool() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(events)

    async def stale_hook(
        task: TaskRecord,
        request_unit: RequestUnitRecord,
    ) -> None:
        changed_at = NOW
        reason_ref = uuid4()
        next_task = TaskRecord(
            **{
                **task.model_dump(),
                "status": TaskStatus.WAITING_USER,
                "state_version": 2,
                "updated_at": changed_at,
                "last_outcome_ref": reason_ref,
            }
        )
        next_unit = RequestUnitRecord(
            **{
                **request_unit.model_dump(),
                "status": TaskStatus.WAITING_USER,
                "state_version": 2,
                "updated_at": changed_at,
            }
        )
        from mini_agent.application.records import ApplyTaskTransitionCommand

        transition = ApplyTaskTransitionCommand(
            expected_task_record=task,
            next_task_record=next_task,
            expected_request_unit_record=request_unit,
            next_request_unit_record=next_unit,
            task_state_transition=TaskStateTransition(
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                from_status=TaskStatus.ACTIVE,
                to_status=TaskStatus.WAITING_USER,
                base_state_version=1,
                result_state_version=2,
                reason_ref=reason_ref,
                changed_at=changed_at,
            ),
        )
        assert (
            await runtime.apply_task_transition_if_current(transition)
            is ConditionalWriteResult.APPLIED
        )
        await runtime.append_trace_event(
            TraceEvent(
                trace_event_id=uuid4(),
                event_type=TraceEventType.TASK_STATE_CHANGED,
                occurred_at=NOW,
                run_id=runtime.run_record.run_id,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
            )
        )

    model = ModelSpy(events)
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model,
        runtime=runtime,
        after_revalidation_hook=stale_hook,
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert runtime.gates[-1].reason_code is GateReasonCode.STATE_VERSION_MISMATCH
    assert [(task.status, task.state_version) for task in runtime.task_history] == [
        (TaskStatus.ACTIVE, 1),
        (TaskStatus.WAITING_USER, 2),
        (TaskStatus.BLOCKED, 3),
    ]
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert sum(
        event.event_type is TraceEventType.TASK_STATE_CHANGED
        for event in runtime.trace_events
    ) == 3


@pytest.mark.parametrize(
    ("ru_protocol_error", "input_fault", "expected_stop"),
    [
        (True, False, StopReason.PROVIDER_PROTOCOL_ERROR),
        (False, True, StopReason.INPUT_INVALID),
    ],
)
def test_request_understanding_faults_create_no_task_graph_or_gate(
    ru_protocol_error: bool,
    input_fault: bool,
    expected_stop: StopReason,
) -> None:
    events: list[str] = []
    model = ModelSpy(
        events,
        ru_protocol_error=ru_protocol_error,
        input_fault=input_fault,
    )
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert runtime.task_history == []
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.run_record.stop_reason is expected_stop


def test_order_system_failure_has_one_read_no_observation_or_presentation() -> None:
    service, _events, model, runtime, _conversation, order, _artifact = _build(
        order_result=GetOrderResult(
            outcome=GetOrderOutcome.SYSTEM_FAILURE,
            failure_code="private-upstream-detail",
        )
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert result.message == "订单服务暂时不可用，请稍后重试。"
    assert model.next_move_calls == 1
    assert model.presentation_calls == 0
    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert runtime.run_record.stop_reason is StopReason.ORDER_SERVICE_UNAVAILABLE
    assert "private-upstream-detail" not in result.message


def test_presentation_protocol_failure_retains_observation_without_plan_trace() -> None:
    events: list[str] = []
    model = ModelSpy(events, presentation_protocol_error=True)
    service, _events, model, runtime, _conversation, _order, _artifact = _build(
        model=model
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert len(runtime.observation_commands) == 1
    assert model.presentation_calls == 1
    assert not any(
        event.event_type is TraceEventType.PRESENTATION_PLAN_PROPOSED
        for event in runtime.trace_events
    )
    assert not any(
        event.event_type is TraceEventType.RESPONSE_RENDERED
        for event in runtime.trace_events
    )
    assert runtime.run_record.stop_reason is StopReason.PROVIDER_PROTOCOL_ERROR


def test_presentation_policy_rejection_never_reaches_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mini_agent.core.presentation_policy import PresentationPolicyError

    def reject_policy(**_: object) -> None:
        raise PresentationPolicyError("bounded policy rejection")

    monkeypatch.setattr(
        agent_run_service_module,
        "validate_presentation_plan",
        reject_policy,
    )
    renderer = FailingRenderer()
    service, _events, _model, runtime, _conversation, _order, _artifact = _build(
        renderer=renderer
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert renderer.render_calls == 0
    assert any(
        event.event_type is TraceEventType.PRESENTATION_PLAN_PROPOSED
        for event in runtime.trace_events
    )
    assert runtime.run_record.stop_reason is (
        StopReason.PRESENTATION_PLAN_REJECTED
    )


def test_renderer_invariant_failure_returns_no_partial_fact_message() -> None:
    renderer = FailingRenderer()
    service, _events, _model, runtime, _conversation, _order, _artifact = _build(
        renderer=renderer
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert result.message == "当前无法安全处理该请求，请稍后重试。"
    assert renderer.render_calls == 1
    assert runtime.run_record.stop_reason is StopReason.RENDERER_INVARIANT_FAILED


def test_conditional_graph_conflict_propagates_as_execution_failure() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(
        events,
        graph_result=ConditionalWriteResult.PROJECTION_CONFLICT,
    )
    model = ModelSpy(events)
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model,
        runtime=runtime,
    )

    with pytest.raises(AgentRunExecutionError, match="initial Task graph"):
        _run(service)

    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert order.queries == []


def test_after_revalidation_hook_defaults_to_noop_and_has_no_fixture_surface() -> None:
    service, _events, _model, _runtime, _conversation, _order, _artifact = _build()

    assert service.after_revalidation_hook is not None
    assert "script" not in vars(service)
    assert "fixture" not in vars(service)
