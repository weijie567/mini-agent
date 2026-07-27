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
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    FinalizeRunCommand,
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
    ToolSpec,
    ToolCallStatus,
    ToolEffect,
    ToolRegistration,
    ToolResultOutcome,
    ToolTimeoutPhase,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
SYNTHETIC_SOURCE_VERSION = "mock-order-source-version.p0.v1:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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
    def __init__(
        self,
        events: list[str],
        *,
        assistant_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.assistant_error = assistant_error
        self.conversations: list[object] = []
        self.messages: list[object] = []

    async def save_conversation(self, record: object) -> None:
        self.events.append("conversation_saved")
        self.conversations.append(record)

    async def append_message(self, record: object) -> None:
        direction = getattr(record, "direction")
        self.events.append(f"message:{direction.value}")
        if (
            direction is MessageDirection.ASSISTANT
            and self.assistant_error is not None
        ):
            raise self.assistant_error
        self.messages.append(record)


class RuntimeSpy:
    def __init__(
        self,
        events: list[str],
        *,
        graph_result: ConditionalWriteResult = ConditionalWriteResult.APPLIED,
        graph_error: Exception | None = None,
        finalize_run_result: ConditionalWriteResult = (
            ConditionalWriteResult.APPLIED
        ),
        finalize_run_effects: list[
            ConditionalWriteResult | BaseException
        ]
        | None = None,
        block_completed_finalize: bool = False,
        trace_error_event_type: TraceEventType | None = None,
    ) -> None:
        self.events = events
        self.graph_result = graph_result
        self.graph_error = graph_error
        self.finalize_run_result = finalize_run_result
        self.finalize_run_effects = list(finalize_run_effects or ())
        self.block_completed_finalize = block_completed_finalize
        self.completed_finalize_started = asyncio.Event()
        self.trace_error_event_type = trace_error_event_type
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
        self.finalize_run_commands: list[FinalizeRunCommand] = []
        self.aggregate_messages: list[object] = []
        self.aggregate_trace_events: list[TraceEvent] = []

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
        command: FinalizeRunCommand,
    ) -> ConditionalWriteResult:
        self.events.append("run_finalized")
        self.finalize_run_commands.append(command)
        if (
            self.block_completed_finalize
            and command.terminal_record.status is AgentRunStatus.COMPLETED
        ):
            self.completed_finalize_started.set()
            await asyncio.Event().wait()
        effect: ConditionalWriteResult | BaseException
        if self.finalize_run_effects:
            effect = self.finalize_run_effects.pop(0)
        else:
            effect = self.finalize_run_result
        if isinstance(effect, BaseException):
            raise effect
        if effect is not ConditionalWriteResult.APPLIED:
            return effect
        expected_links = (
            (self.run_task_link,) if self.run_task_link is not None else ()
        )
        if (
            self.run_record != command.expected_active_record
            or expected_links != command.expected_active_links
        ):
            return ConditionalWriteResult.PROJECTION_CONFLICT
        transition = command.task_transition
        if transition is not None:
            if (
                self.task != transition.expected_task_record
                or self.request_unit
                != transition.expected_request_unit_record
                or command.result_task_records
                != (transition.next_task_record,)
            ):
                return ConditionalWriteResult.PROJECTION_CONFLICT
        else:
            expected_tasks = (self.task,) if self.task is not None else ()
            if expected_tasks != command.result_task_records:
                return ConditionalWriteResult.PROJECTION_CONFLICT
        if transition is not None:
            self.task = transition.next_task_record
            self.request_unit = transition.next_request_unit_record
            self.task_history.append(self.task)
            self.request_unit_history.append(self.request_unit)
        self.run_record = command.terminal_record
        if command.terminal_links:
            self.run_task_link = command.terminal_links[0]
        if command.assistant_message is not None:
            self.aggregate_messages.append(command.assistant_message)
        self.aggregate_trace_events.extend(command.terminal_trace_events)
        self.trace_events.extend(command.terminal_trace_events)
        self.events.append("terminal_aggregate_applied")
        return ConditionalWriteResult.APPLIED

    async def create_initial_task_graph_if_current(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("initial_graph_saved")
        if self.graph_error is not None:
            raise self.graph_error
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
        if record.event_type is self.trace_error_event_type:
            raise RuntimeError("private trace persistence failure")
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


class HangingOrderSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.queries: list[GetOrderQuery] = []
        self.started = asyncio.Event()

    async def get_order(self, query: GetOrderQuery) -> GetOrderResult:
        self.events.append("order_read")
        self.queries.append(query)
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


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
        self.next_move_requests: list[object] = []

    async def propose_next_move(self, request: object):
        self.events.append("provider:request_understanding")
        self.next_move_calls += 1
        self.next_move_requests.append(request)
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


def _snapshot(*, timeout_ms: int = 500) -> RegistrySnapshot:
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
                    timeout_ms=timeout_ms,
                    max_attempts=1,
                    interrupt_behavior="MARK_INTERRUPTED",
                ),
            ),
        ),
    )


def test_get_order_agent_visible_schema_does_not_expose_source_version() -> None:
    assert (
        "source_version"
        not in get_order_tool_spec().output_schema["properties"]
    )


def _snapshot_with_provider_schema_drift() -> RegistrySnapshot:
    snapshot = _snapshot()
    canonical_spec = get_order_tool_spec()
    drifted_visible_spec = ToolSpec(
        name="get_order",
        description=canonical_spec.description,
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "order_ref": {
                    "type": "string",
                    "pattern": r"^O-[0-9]{4,20}$",
                }
            },
            "required": ["order_ref"],
        },
        output_schema=canonical_spec.output_schema,
    )
    return RegistrySnapshot(
        tool_registry_version=snapshot.tool_registry_version,
        canonical_registrations=snapshot.canonical_registrations,
        provider_visible_toolset=(drifted_visible_spec,),
        provider_name_to_canonical_name=(
            snapshot.provider_name_to_canonical_name
        ),
        model_visible_toolset_hash=compute_model_visible_toolset_hash(
            (drifted_visible_spec,)
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
        source_version=SYNTHETIC_SOURCE_VERSION,
    )


def _build(
    *,
    model: ModelSpy | None = None,
    order_result: GetOrderResult | None = None,
    runtime: RuntimeSpy | None = None,
    renderer: object | None = None,
    after_revalidation_hook: object | None = None,
    registry_snapshot: RegistrySnapshot | None = None,
    order_port: object | None = None,
    conversation: ConversationSpy | None = None,
):
    events: list[str] = model.events if model is not None else []
    actual_model = model or ModelSpy(events)
    actual_runtime = runtime or RuntimeSpy(events)
    artifact = ArtifactSpy(events)
    actual_conversation = conversation or ConversationSpy(events)
    order = order_port or OrderSpy(events, order_result or _found_result())
    ids = UuidSequence()
    read_executor = ReadToolExecutor(
        runtime_record_port=actual_runtime,
        get_order_port=order,
        clock=lambda: NOW,
        uuid_factory=ids,
    )
    service = AgentRunService(
        model_provider=actual_model,
        registry_snapshot=registry_snapshot or _snapshot(),
        toolset_artifact_port=artifact,
        conversation_record_port=actual_conversation,
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
        actual_conversation,
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


def _assert_complete_terminal_aggregate(
    command: FinalizeRunCommand,
    *,
    result: object,
    with_task: bool,
) -> None:
    assert command.terminal_record.status is AgentRunStatus.COMPLETED
    assert command.terminal_result == result
    assert command.assistant_message is not None
    assert command.assistant_message.direction is MessageDirection.ASSISTANT
    assert (
        command.assistant_message.conversation_id
        == command.terminal_record.conversation_id
    )
    assert command.assistant_message.content == command.terminal_result.message
    assert (
        command.assistant_message.received_at
        == command.terminal_record.completed_at
    )
    if with_task:
        assert command.task_transition is not None
        assert command.result_task_records == (
            command.task_transition.next_task_record,
        )
        assert tuple(
            event.event_type for event in command.terminal_trace_events
        ) == (
            TraceEventType.TASK_STATE_CHANGED,
            TraceEventType.RUN_STOPPED,
        )
        assert (
            command.terminal_trace_events[0].occurred_at
            == command.task_transition.task_state_transition.changed_at
        )
    else:
        assert command.task_transition is None
        assert command.expected_active_links == ()
        assert command.terminal_links == ()
        assert command.result_task_records == ()
        assert tuple(
            event.event_type for event in command.terminal_trace_events
        ) == (TraceEventType.RUN_STOPPED,)
    run_stopped = command.terminal_trace_events[-1]
    assert run_stopped.run_id == command.terminal_record.run_id
    assert run_stopped.stop_reason is command.terminal_record.stop_reason
    assert run_stopped.user_outcome is command.terminal_result.outcome
    assert run_stopped.occurred_at == command.terminal_record.completed_at


def _assert_failed_terminal_projection_is_empty(
    command: FinalizeRunCommand,
) -> None:
    assert command.terminal_record.status is AgentRunStatus.FAILED
    assert command.task_transition is None
    assert command.terminal_result is None
    assert command.assistant_message is None
    assert command.terminal_trace_events == ()


def _assert_no_standalone_terminal_writes(events: list[str]) -> None:
    assert "message:ASSISTANT" not in events
    assert f"trace:{TraceEventType.RUN_STOPPED.value}" not in events


def _trace_events_of_type(
    runtime: RuntimeSpy,
    event_type: TraceEventType,
) -> list[TraceEvent]:
    return [
        event
        for event in runtime.trace_events
        if event.event_type is event_type
    ]


def _assert_manifest_trace_purposes(
    runtime: RuntimeSpy,
    model: ModelSpy,
) -> None:
    context_events = _trace_events_of_type(
        runtime,
        TraceEventType.CONTEXT_MANIFEST_RECORDED,
    )
    expected_purposes = [
        *(["REQUEST_UNDERSTANDING"] * model.next_move_calls),
        *(["PRESENTATION"] * model.presentation_calls),
    ]
    assert [event.model_call_purpose for event in context_events] == (
        expected_purposes
    )
    assert [event.model_call_id for event in context_events] == [
        manifest.model_call_id for manifest in runtime.manifests
    ]
    assert [event.context_manifest_id for event in context_events] == [
        manifest.context_manifest_id for manifest in runtime.manifests
    ]


def _assert_one_response_rendered(
    runtime: RuntimeSpy,
    *,
    with_task: bool,
    observation_ref: UUID | None = None,
    presentation_plan_ref: UUID | None = None,
    expect_run_stopped: bool = True,
) -> TraceEvent:
    rendered_events = _trace_events_of_type(
        runtime,
        TraceEventType.RESPONSE_RENDERED,
    )
    assert len(rendered_events) == 1
    rendered = rendered_events[0]
    assert rendered.run_id == runtime.run_record.run_id
    if with_task:
        assert runtime.task is not None
        assert runtime.request_unit is not None
        assert rendered.task_id == runtime.task.task_id
        assert (
            rendered.request_unit_id
            == runtime.request_unit.request_unit_id
        )
    else:
        assert rendered.task_id is None
        assert rendered.request_unit_id is None
    assert rendered.observation_ref == observation_ref
    assert rendered.presentation_plan_ref == presentation_plan_ref

    stopped_events = _trace_events_of_type(
        runtime,
        TraceEventType.RUN_STOPPED,
    )
    if expect_run_stopped:
        assert len(stopped_events) == 1
        assert runtime.trace_events.index(rendered) < runtime.trace_events.index(
            stopped_events[0]
        )
    else:
        assert stopped_events == []
    return rendered


def _assert_no_response_rendered_or_run_stopped(
    runtime: RuntimeSpy,
) -> None:
    assert _trace_events_of_type(
        runtime,
        TraceEventType.RESPONSE_RENDERED,
    ) == []
    assert _trace_events_of_type(
        runtime,
        TraceEventType.RUN_STOPPED,
    ) == []


async def _advance_to_waiting_user(
    *,
    run_id: UUID,
    runtime: RuntimeSpy,
    task: TaskRecord,
    request_unit: RequestUnitRecord,
) -> None:
    reason_ref = uuid4()
    next_task = TaskRecord(
        **{
            **task.model_dump(),
            "status": TaskStatus.WAITING_USER,
            "state_version": 2,
            "updated_at": NOW,
            "last_outcome_ref": reason_ref,
        }
    )
    next_unit = RequestUnitRecord(
        **{
            **request_unit.model_dump(),
            "status": TaskStatus.WAITING_USER,
            "state_version": 2,
            "updated_at": NOW,
        }
    )
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
            changed_at=NOW,
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
            run_id=run_id,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
        )
    )


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
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    assert len(runtime.finalize_run_commands) == 1
    terminal_command = runtime.finalize_run_commands[0]
    _assert_complete_terminal_aggregate(
        terminal_command,
        result=result,
        with_task=True,
    )
    assert runtime.aggregate_messages == [terminal_command.assistant_message]
    assert runtime.aggregate_trace_events == list(
        terminal_command.terminal_trace_events
    )
    _assert_manifest_trace_purposes(runtime, model)
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
    )

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
    assert not any(
        event.startswith("task_transition:") for event in events
    )
    _assert_no_standalone_terminal_writes(events)
    assert _index(
        events,
        f"trace:{TraceEventType.RESPONSE_RENDERED.value}",
    ) < _index(events, "run_finalized")
    assert _index(events, "run_finalized") < _index(
        events, "terminal_aggregate_applied"
    )
    assert events[-1] == "terminal_aggregate_applied"

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


def test_model_visible_schema_drift_is_rejected_before_tool_execution() -> None:
    events: list[str] = []
    model = ModelSpy(events)
    snapshot = _snapshot_with_provider_schema_drift()
    service, _events, model, runtime, _conversation, order, _artifact = _build(
        model=model,
        registry_snapshot=snapshot,
    )

    result = _run(service)

    visible_spec = model.next_move_requests[0].provider_visible_tool_specs[0]
    assert visible_spec == snapshot.provider_visible_toolset[0]
    assert visible_spec.input_schema["required"] == ("order_ref",)
    assert result.outcome is AgentOutcome.BLOCKED
    assert runtime.gates[-1].reason_code is GateReasonCode.SCHEMA_INVALID
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.observation_commands == []
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


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
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


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
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


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
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


def test_stale_hook_advances_v2_then_gateway_blocks_v3_without_tool() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(events)
    hook_arguments: list[
        tuple[UUID, TaskRecord, RequestUnitRecord]
    ] = []

    async def stale_hook(
        run_id: UUID,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
    ) -> None:
        hook_arguments.append((run_id, task, request_unit))
        assert run_id == runtime.run_record.run_id
        assert task == runtime.task
        assert request_unit == runtime.request_unit
        assert "task_reloaded" not in events
        assert "request_unit_reloaded" not in events
        assert "gate_saved" not in events
        await _advance_to_waiting_user(
            run_id=run_id,
            runtime=runtime,
            task=task,
            request_unit=request_unit,
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
    terminal_command = runtime.finalize_run_commands[-1]
    assert terminal_command.task_transition is not None
    assert (
        terminal_command.task_transition.expected_task_record.status
        is TaskStatus.WAITING_USER
    )
    assert terminal_command.task_transition.expected_task_record.state_version == 2
    assert terminal_command.task_transition.next_task_record.status is (
        TaskStatus.BLOCKED
    )
    assert terminal_command.task_transition.next_task_record.state_version == 3
    assert "task_transition:WAITING_USER:v2" in events
    assert "task_transition:BLOCKED:v3" not in events
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert sum(
        event.event_type is TraceEventType.TASK_STATE_CHANGED
        for event in runtime.trace_events
    ) == 3
    assert hook_arguments == [
        (
            terminal_command.expected_active_record.run_id,
            runtime.task_history[0],
            runtime.request_unit_history[0],
        )
    ]
    assert _index(
        events,
        f"trace:{TraceEventType.NEXT_MOVE_REVALIDATED.value}",
    ) < _index(events, "task_transition:WAITING_USER:v2")
    assert _index(events, "task_transition:WAITING_USER:v2") < _index(
        events,
        "task_reloaded",
    )
    assert _index(events, "request_unit_reloaded") < _index(
        events,
        "gate_saved",
    )
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        terminal_command,
        result=result,
        with_task=True,
    )


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
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=False)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=False,
    )


def test_no_task_completion_commits_result_message_and_run_stopped_once() -> None:
    events: list[str] = []
    model = ModelSpy(events, ru_protocol_error=True)
    service, _events, _model, runtime, conversation, _order, _artifact = _build(
        model=model
    )

    result = _run(service)

    assert len(runtime.finalize_run_commands) == 1
    terminal_command = runtime.finalize_run_commands[0]
    _assert_complete_terminal_aggregate(
        terminal_command,
        result=result,
        with_task=False,
    )
    assert runtime.aggregate_messages == [terminal_command.assistant_message]
    assert runtime.aggregate_trace_events == list(
        terminal_command.terminal_trace_events
    )
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    assert not any(
        event.startswith("task_transition:") for event in events
    )
    _assert_no_standalone_terminal_writes(events)
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=False)
    assert events[-1] == "terminal_aggregate_applied"


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
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


def test_hanging_order_read_times_out_with_bounded_terminal_trace() -> None:
    async def scenario():
        events: list[str] = []
        model = ModelSpy(events)
        order = HangingOrderSpy(events)
        service, _events, _model, runtime, _conversation, _order, _artifact = (
            _build(
                model=model,
                registry_snapshot=_snapshot(timeout_ms=5),
                order_port=order,
            )
        )
        result = await asyncio.wait_for(
            service.handle(
                AgentRunCommand(
                    customer_context=_context(),
                    message="请查询订单 O-1001",
                )
            ),
            timeout=0.5,
        )
        return result, runtime, order, model

    result, runtime, order, model = asyncio.run(scenario())

    assert result.outcome is AgentOutcome.BLOCKED
    assert len(order.queries) == 1
    assert len(runtime.finalize_tool_commands) == 1
    finalization = runtime.finalize_tool_commands[0]
    assert finalization.terminal_record.status is ToolCallStatus.TIMED_OUT
    assert finalization.terminal_record.timeout_phase is (
        ToolTimeoutPhase.AFTER_DISPATCH
    )
    assert finalization.finalized_attempt.outcome is ToolResultOutcome.TIMEOUT
    assert runtime.observation_commands == []
    assert sum(
        event.event_type is TraceEventType.TOOL_CALL_TIMED_OUT
        for event in runtime.trace_events
    ) == 1
    assert runtime.run_record.stop_reason is StopReason.ORDER_SERVICE_UNAVAILABLE
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(runtime, with_task=True)
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


def test_cancelled_order_read_closes_tool_and_run_before_reraising() -> None:
    async def scenario():
        events: list[str] = []
        model = ModelSpy(events)
        order = HangingOrderSpy(events)
        service, _events, _model, runtime, conversation, _order, _artifact = (
            _build(
                model=model,
                registry_snapshot=_snapshot(timeout_ms=5_000),
                order_port=order,
            )
        )
        run_task = asyncio.create_task(
            service.handle(
                AgentRunCommand(
                    customer_context=_context(),
                    message="请查询订单 O-1001",
                )
            )
        )
        await asyncio.wait_for(order.started.wait(), timeout=0.5)
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
        return runtime, conversation, order

    runtime, conversation, order = asyncio.run(scenario())

    assert len(order.queries) == 1
    assert len(runtime.finalize_tool_commands) == 1
    finalization = runtime.finalize_tool_commands[0]
    assert finalization.terminal_record.status is ToolCallStatus.INTERRUPTED
    assert finalization.finalized_attempt.outcome is ToolResultOutcome.INTERRUPTED
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert runtime.observation_commands == []
    assert len(runtime.finalize_run_commands) == 1
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[0]
    )
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    assert sum(
        event.event_type is TraceEventType.TOOL_CALL_INTERRUPTED
        for event in runtime.trace_events
    ) == 1
    _assert_no_response_rendered_or_run_stopped(runtime)


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
    observation_event = _trace_events_of_type(
        runtime,
        TraceEventType.OBSERVATION_RECORDED,
    )[0]
    _assert_manifest_trace_purposes(runtime, model)
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=observation_event.observation_ref,
    )
    assert runtime.run_record.stop_reason is StopReason.PROVIDER_PROTOCOL_ERROR
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


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
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
    )
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
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
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
    )
    _assert_complete_terminal_aggregate(
        runtime.finalize_run_commands[-1],
        result=result,
        with_task=True,
    )


def test_conditional_graph_conflict_finalizes_failed_then_reraises() -> None:
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

    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert runtime.run_record.stop_reason is None
    assert len(runtime.finalize_run_commands) == 1
    finalization = runtime.finalize_run_commands[0]
    _assert_failed_terminal_projection_is_empty(finalization)
    assert finalization.expected_active_links == ()
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.observation_commands == []
    _assert_no_response_rendered_or_run_stopped(runtime)


def test_internal_graph_exception_finalizes_failed_then_reraises() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(
        events,
        graph_error=RuntimeError("private graph failure"),
    )
    model = ModelSpy(events)
    service, _events, _model, runtime, conversation, order, _artifact = _build(
        model=model,
        runtime=runtime,
    )

    with pytest.raises(RuntimeError, match="private graph failure"):
        _run(service)

    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert runtime.run_record.stop_reason is None
    assert len(runtime.finalize_run_commands) == 1
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[0]
    )
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.observation_commands == []
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    _assert_no_response_rendered_or_run_stopped(runtime)


def test_state_advanced_hook_error_reloads_current_task_before_failed_cas() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(events)

    async def advancing_hook(
        run_id: UUID,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
    ) -> None:
        await _advance_to_waiting_user(
            run_id=run_id,
            runtime=runtime,
            task=task,
            request_unit=request_unit,
        )
        raise RuntimeError("private hook failure")

    model = ModelSpy(events)
    service, _events, _model, runtime, conversation, order, _artifact = _build(
        model=model,
        runtime=runtime,
        after_revalidation_hook=advancing_hook,
    )

    with pytest.raises(RuntimeError, match="private hook failure"):
        _run(service)

    assert runtime.task is not None
    assert runtime.task.status is TaskStatus.WAITING_USER
    assert runtime.task.state_version == 2
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert len(runtime.finalize_run_commands) == 1
    finalization = runtime.finalize_run_commands[0]
    _assert_failed_terminal_projection_is_empty(finalization)
    assert finalization.result_task_records == (runtime.task,)
    assert finalization.terminal_links[0].result_task_state_version == 2
    assert runtime.gates == []
    assert order.queries == []
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    _assert_no_response_rendered_or_run_stopped(runtime)


def test_with_task_applied_aggregate_never_awaits_standalone_terminal_writes() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(
        events,
        trace_error_event_type=TraceEventType.RUN_STOPPED,
    )
    conversation = ConversationSpy(
        events,
        assistant_error=RuntimeError("private assistant persistence failure"),
    )
    model = ModelSpy(events)
    service, _events, _model, runtime, conversation, _order, _artifact = _build(
        model=model,
        runtime=runtime,
        conversation=conversation,
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.COMPLETED
    assert runtime.run_record.status is AgentRunStatus.COMPLETED
    assert runtime.run_record.stop_reason is StopReason.GOAL_COMPLETED
    assert len(runtime.finalize_run_commands) == 1
    terminal_command = runtime.finalize_run_commands[0]
    _assert_complete_terminal_aggregate(
        terminal_command,
        result=result,
        with_task=True,
    )
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    _assert_no_standalone_terminal_writes(events)
    assert runtime.aggregate_messages == [terminal_command.assistant_message]
    assert runtime.aggregate_trace_events == list(
        terminal_command.terminal_trace_events
    )
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
    )
    assert events[-1] == "terminal_aggregate_applied"


def test_no_task_applied_aggregate_never_awaits_standalone_terminal_writes() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(
        events,
        trace_error_event_type=TraceEventType.RUN_STOPPED,
    )
    conversation = ConversationSpy(
        events,
        assistant_error=RuntimeError("private assistant persistence failure"),
    )
    model = ModelSpy(events, ru_protocol_error=True)
    service, _events, _model, runtime, conversation, _order, _artifact = _build(
        model=model,
        runtime=runtime,
        conversation=conversation,
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert runtime.run_record.status is AgentRunStatus.COMPLETED
    assert runtime.run_record.stop_reason is StopReason.PROVIDER_PROTOCOL_ERROR
    assert len(runtime.finalize_run_commands) == 1
    terminal_command = runtime.finalize_run_commands[0]
    _assert_complete_terminal_aggregate(
        terminal_command,
        result=result,
        with_task=False,
    )
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    _assert_no_standalone_terminal_writes(events)
    assert runtime.aggregate_messages == [terminal_command.assistant_message]
    assert runtime.aggregate_trace_events == list(
        terminal_command.terminal_trace_events
    )
    _assert_one_response_rendered(runtime, with_task=False)
    assert events[-1] == "terminal_aggregate_applied"


@pytest.mark.parametrize(
    ("first_effect", "expected_error"),
    (
        (
            ConditionalWriteResult.PROJECTION_CONFLICT,
            AgentRunExecutionError,
        ),
        (
            RuntimeError("private terminal aggregate failure"),
            RuntimeError,
        ),
    ),
    ids=("conflict", "exception"),
)
def test_terminal_aggregate_failure_preserves_render_without_terminal_projection(
    first_effect: ConditionalWriteResult | BaseException,
    expected_error: type[BaseException],
) -> None:
    events: list[str] = []
    runtime = RuntimeSpy(
        events,
        finalize_run_effects=[
            first_effect,
            ConditionalWriteResult.APPLIED,
        ],
    )
    model = ModelSpy(events)
    service, _events, _model, runtime, conversation, _order, _artifact = _build(
        model=model,
        runtime=runtime,
    )

    with pytest.raises(expected_error):
        _run(service)

    assert len(runtime.finalize_run_commands) == 2
    attempted_terminal, failed_cleanup = runtime.finalize_run_commands
    _assert_complete_terminal_aggregate(
        attempted_terminal,
        result=attempted_terminal.terminal_result,
        with_task=True,
    )
    _assert_failed_terminal_projection_is_empty(failed_cleanup)
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert runtime.task is not None
    assert runtime.task.status is TaskStatus.ACTIVE
    assert runtime.task.state_version == 1
    assert failed_cleanup.result_task_records == (runtime.task,)
    assert (
        failed_cleanup.terminal_links[0].result_task_state_version == 1
    )
    assert [(task.status, task.state_version) for task in runtime.task_history] == [
        (TaskStatus.ACTIVE, 1)
    ]
    assert runtime.aggregate_messages == []
    assert runtime.aggregate_trace_events == []
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    assert not any(
        event.startswith("task_transition:") for event in events
    )
    _assert_no_standalone_terminal_writes(events)
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
        expect_run_stopped=False,
    )


def test_failed_cleanup_error_adds_only_bounded_type_note() -> None:
    events: list[str] = []
    runtime = RuntimeSpy(
        events,
        finalize_run_effects=[
            ConditionalWriteResult.PROJECTION_CONFLICT,
            RuntimeError("private failed-cleanup detail"),
        ],
    )
    model = ModelSpy(events)
    service, _events, _model, runtime, conversation, _order, _artifact = _build(
        model=model,
        runtime=runtime,
    )

    with pytest.raises(AgentRunExecutionError) as captured:
        _run(service)

    assert getattr(captured.value, "__notes__", []) == [
        "Run failure finalization raised RuntimeError"
    ]
    assert "private failed-cleanup detail" not in repr(
        getattr(captured.value, "__notes__", [])
    )
    assert len(runtime.finalize_run_commands) == 2
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[-1]
    )
    assert runtime.run_record.status is AgentRunStatus.RUNNING
    assert runtime.task is not None
    assert runtime.task.status is TaskStatus.ACTIVE
    assert runtime.task.state_version == 1
    assert runtime.aggregate_messages == []
    assert runtime.aggregate_trace_events == []
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    _assert_no_standalone_terminal_writes(events)
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
        expect_run_stopped=False,
    )


def test_terminal_aggregate_cancellation_preserves_render_without_terminal_projection() -> None:
    async def scenario():
        events: list[str] = []
        runtime = RuntimeSpy(events, block_completed_finalize=True)
        model = ModelSpy(events)
        service, _events, _model, runtime, conversation, _order, _artifact = (
            _build(
                model=model,
                runtime=runtime,
            )
        )
        run_task = asyncio.create_task(
            service.handle(
                AgentRunCommand(
                    customer_context=_context(),
                    message="请查询订单 O-1001",
                )
            )
        )
        await asyncio.wait_for(
            runtime.completed_finalize_started.wait(),
            timeout=0.5,
        )
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
        return events, runtime, conversation

    events, runtime, conversation = asyncio.run(scenario())

    assert len(runtime.finalize_run_commands) == 2
    attempted_terminal, failed_cleanup = runtime.finalize_run_commands
    _assert_complete_terminal_aggregate(
        attempted_terminal,
        result=attempted_terminal.terminal_result,
        with_task=True,
    )
    _assert_failed_terminal_projection_is_empty(failed_cleanup)
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert runtime.task is not None
    assert runtime.task.status is TaskStatus.ACTIVE
    assert runtime.task.state_version == 1
    assert failed_cleanup.result_task_records == (runtime.task,)
    assert runtime.aggregate_messages == []
    assert runtime.aggregate_trace_events == []
    assert [message.direction for message in conversation.messages] == [
        MessageDirection.USER
    ]
    assert not any(
        event.startswith("task_transition:") for event in events
    )
    _assert_no_standalone_terminal_writes(events)
    presentation_event = _trace_events_of_type(
        runtime,
        TraceEventType.PRESENTATION_PLAN_PROPOSED,
    )[0]
    _assert_one_response_rendered(
        runtime,
        with_task=True,
        observation_ref=presentation_event.observation_ref,
        presentation_plan_ref=presentation_event.presentation_plan_ref,
        expect_run_stopped=False,
    )


def test_after_revalidation_hook_defaults_to_noop_and_has_no_fixture_surface() -> None:
    service, _events, _model, _runtime, _conversation, _order, _artifact = _build()

    assert service.after_revalidation_hook is not None
    assert "script" not in vars(service)
    assert "fixture" not in vars(service)
