import asyncio
import ast
import inspect
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

import mini_agent.application.agent_run_service as agent_run_service_module
from mini_agent.application.agent_run_service import (
    AgentRunExecutionError,
    AgentRunService,
    Cycle2AgentRunHandler,
    Cycle2AgentRunService,
    map_cycle2_get_shipment_tool_result,
    map_cycle2_search_orders_tool_result,
)
from mini_agent.application.deterministic_renderer import (
    DeterministicRenderer,
    RendererInvariantError,
)
from mini_agent.application.read_tool_executor import (
    Cycle2ReadToolExecution,
    ReadToolExecutor,
)
from mini_agent.application.run_result_mapper import (
    Cycle2ExecutionOutcomeObservationV1,
    Cycle2MappingSourceKind,
    Cycle2MapperSignal,
    ImportedMapperReference,
    MapperDisposition,
    PHASE1_RESULT_MAPPER_CONTRACT,
    ResponsePolicy,
    RunResultMapper,
)
from mini_agent.application.records import (
    AcceptedOrderSearchQueryBindingReadClosure,
    AgentRunCommand,
    AgentRunResult,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    ContinuationInputBindingReadClosure,
    Cycle2ControlPurpose,
    Cycle2CurrentSessionTaskClosure,
    Cycle2ExactRunEvidenceClosure,
    Cycle2WriteResult,
    FinalizeRunCommand,
    InsertOnlyWriteResult,
    InitialToolCallV2ReadClosure,
    MessageDirection,
    MessageRecord,
    ObservationWriteResult,
    OrderCandidateSelectionReadClosure,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
    ToolDispatchFenceWriteResult,
)
from mini_agent.core.control_gateway import (
    Cycle2TargetObservationFacts,
    Cycle2ToolProgressFact,
    Cycle2VerifiedOrderTargetFacts,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import (
    ObservationVisibility,
    OrderObservation,
    ShipmentObservation,
    TokenCounts,
)
from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderQuery,
    GetOrderResult,
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.order_search import (
    MatchedOrderLine,
    OrderCandidate,
    SearchOrdersOutcome,
    SearchOrdersResult,
    build_order_candidate_public_summary,
)
from mini_agent.core.presentation import (
    ClosingVariant,
    OpeningVariant,
    PresentationField,
    PresentationPlan,
    PresentationTone,
)
from mini_agent.core.request_processing import (
    Cycle2OrdinalSelectionRejectionReason,
    RequestUnderstandingV2Error,
)
from mini_agent.core.request_understanding import (
    Cycle2ControlCandidate,
    Cycle2ControlCandidateKind,
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InitialTaskDeltaCandidateV2,
    Cycle2InputCandidate,
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    RequestUnderstandingOutputV2,
    ResolvedReferenceCandidateV2,
    TaskDeltaCandidate,
    TaskDeltaOperation,
    UncertaintyReasonCodeV2,
    UncertaintyV2,
)
from mini_agent.core.task_state import (
    RequestUnderstandingAtomicFailureCodeV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    Cycle2ToolName,
    ExecutionPolicy,
    GateReasonCode,
    RegistrySnapshot,
    ToolSpec,
    ToolCallStatus,
    ToolAttemptRecordV2,
    ToolCallRecordV2,
    ToolEffect,
    ToolResult,
    ToolRegistration,
    ToolResultOutcome,
    ToolRetryDecision,
    ToolTimeoutPhase,
    cycle2_pydantic_model_graph_is_raw_closed,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)
from mini_agent.core.shipment import (
    GetShipmentOutcome,
    GetShipmentResult,
    SHIPMENT_FRESHNESS_TTL,
    ShipmentEventCode,
    ShipmentStatus,
    ShipmentSummaryProjection,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunStatus,
    StopReason,
    StopReasonV2,
    TraceEvent,
    TraceEventType,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
SYNTHETIC_SOURCE_VERSION = "mock-order-source-version.p0.v1:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class CandidateInvalidSignalSubclass(
    RequestUnderstandingCandidateInvalidError
):
    def __init__(self) -> None:
        Exception.__init__(self, "raw-customer-B-secret")


class ProviderProtocolSignalSubclass(ProviderProtocolError):
    def __init__(self) -> None:
        Exception.__init__(self, "raw-customer-B-secret")


class SourceVersionSubclass(str):
    pass


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

    async def load_conversation_for_owner(
        self,
        *,
        owner_scope: object,
        conversation_id: UUID,
    ):
        self.events.append("conversation_reloaded")
        if (
            self.conversations
            and self.conversations[-1].conversation_id == conversation_id
            and self.conversations[-1].owner_customer_id
            == owner_scope.customer_id
        ):
            return self.conversations[-1]
        return None

    async def list_messages_for_owner(
        self,
        *,
        owner_scope: object,
        conversation_id: UUID,
        limit: int,
    ):
        self.events.append("messages_reloaded")
        if (
            not self.conversations
            or self.conversations[-1].conversation_id != conversation_id
            or self.conversations[-1].owner_customer_id
            != owner_scope.customer_id
        ):
            return ()
        return tuple(
            message
            for message in self.messages[-limit:]
            if message.conversation_id == conversation_id
        )


class MessageReadOverrideConversationSpy(ConversationSpy):
    def __init__(
        self,
        events: list[str],
        *,
        read_mode: str,
    ) -> None:
        super().__init__(events)
        self.read_mode = read_mode

    async def list_messages_for_owner(
        self,
        *,
        owner_scope: object,
        conversation_id: UUID,
        limit: int,
    ):
        messages = await super().list_messages_for_owner(
            owner_scope=owner_scope,
            conversation_id=conversation_id,
            limit=limit,
        )
        if self.read_mode == "empty":
            return ()
        message = messages[0]
        if self.read_mode == "duplicate":
            return (message, message)
        if self.read_mode == "foreign_conversation":
            return (
                MessageRecord(
                    schema_version=message.schema_version,
                    message_id=message.message_id,
                    conversation_id=uuid4(),
                    direction=message.direction,
                    content=message.content,
                    received_at=message.received_at,
                ),
            )
        if self.read_mode == "stale_content":
            return (
                MessageRecord(
                    schema_version=message.schema_version,
                    message_id=message.message_id,
                    conversation_id=message.conversation_id,
                    direction=message.direction,
                    content="请查询订单 O-9999",
                    received_at=message.received_at,
                ),
            )
        raise AssertionError("unsupported test read mode")


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

    async def create_initial_task_graph_v2_if_current(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("initial_graph_v2_saved")
        if self.graph_error is not None:
            raise self.graph_error
        if self.graph_result is ConditionalWriteResult.APPLIED:
            self.task = command.initial_task.initial_record
            self.request_unit = command.initial_request_unit.initial_record
            self.input_binding = command.input_binding.record
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


class ObservationVersionOverrideExecutor:
    def __init__(
        self,
        delegate: ReadToolExecutor,
        source_version: object,
    ) -> None:
        self.delegate = delegate
        self.source_version = source_version

    async def execute_get_order(self, **kwargs: object):
        execution = await self.delegate.execute_get_order(**kwargs)
        observation = execution.observation
        assert observation is not None
        return execution.model_copy(
            update={
                "observation": observation.model_copy(
                    update={"source_version": self.source_version}
                )
            }
        )


class ModelSpy:
    def __init__(
        self,
        events: list[str],
        *,
        bound_order_id: str = "O-1001",
        proposed_order_id: str = "O-1001",
        requested_tool_name: str = "get_order",
        task_candidate_count: int = 1,
        reject_all_candidates: bool = False,
        ru_protocol_error: bool = False,
        input_fault: bool = False,
        ru_exception: Exception | None = None,
        presentation_protocol_error: bool = False,
        presentation_exception: Exception | None = None,
    ) -> None:
        self.events = events
        self.bound_order_id = bound_order_id
        self.proposed_order_id = proposed_order_id
        self.requested_tool_name = requested_tool_name
        self.task_candidate_count = task_candidate_count
        self.reject_all_candidates = reject_all_candidates
        self.ru_protocol_error = ru_protocol_error
        self.input_fault = input_fault
        self.ru_exception = ru_exception
        self.presentation_protocol_error = presentation_protocol_error
        self.presentation_exception = presentation_exception
        self.next_move_calls = 0
        self.presentation_calls = 0
        self.next_move_requests: list[object] = []

    async def propose_next_move(self, request: object):
        self.events.append("provider:request_understanding")
        self.next_move_calls += 1
        self.next_move_requests.append(request)
        if self.ru_protocol_error:
            raise ProviderProtocolError()
        if self.input_fault:
            raise RequestUnderstandingCandidateInvalidError()
        if self.ru_exception is not None:
            raise self.ru_exception
        message_ref = request.message_ref
        output = RequestUnderstandingOutputV2(
            schema_version="e2e01-thin-v2",
            message_ref=message_ref,
            contextualization=QueryContextualizationCandidateV2(
                text=request.original_query,
                resolved_reference_candidates=(
                    ResolvedReferenceCandidateV2(
                        name="order_id",
                        candidate_value=self.bound_order_id,
                        source_kind=ReferenceSourceKindV2.CURRENT_MESSAGE,
                        source_ref=message_ref,
                        source_quote=self.bound_order_id,
                        confidence=0.99,
                    ),
                ),
                uncertainties=(
                    (
                        UncertaintyV2(
                            name="order_id",
                            candidate_values=(),
                            reason_code=(
                                UncertaintyReasonCodeV2.MISSING_REFERENCE
                            ),
                            source_message_refs=(message_ref,),
                        ),
                    )
                    if self.reject_all_candidates
                    else ()
                ),
                source_message_refs=(message_ref,),
            ),
            task_delta_candidates=tuple(
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
                )
                for _ in range(self.task_candidate_count)
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name=self.requested_tool_name,
                arguments={"order_id": self.proposed_order_id},
                base_task_state_version=None,
            ),
        )
        return output

    async def plan_presentation(self, request: object) -> PresentationPlan:
        self.events.append("provider:presentation")
        self.presentation_calls += 1
        if self.presentation_protocol_error:
            raise ProviderProtocolError()
        if self.presentation_exception is not None:
            raise self.presentation_exception
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
        events, "messages_reloaded"
    )
    assert _index(events, "messages_reloaded") < _index(
        events, "provider:request_understanding"
    )
    assert _index(events, "initial_graph_v2_saved") < _index(
        events, "gate_saved"
    )
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


@pytest.mark.parametrize(
    "error_type",
    [
        CandidateInvalidSignalSubclass,
        ProviderProtocolSignalSubclass,
    ],
)
def test_provider_signal_subclasses_fail_without_product_classification(
    error_type: type[Exception],
) -> None:
    events: list[str] = []
    model = ModelSpy(events, ru_exception=error_type())
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model
    )

    with pytest.raises(
        AgentRunExecutionError,
        match="noncanonical Provider signal",
    ) as captured:
        _run(service)

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert "raw-customer-B-secret" not in repr(captured.value)
    assert runtime.task_history == []
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert len(runtime.finalize_run_commands) == 1
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[0]
    )
    _assert_no_response_rendered_or_run_stopped(runtime)


def test_atomic_request_understanding_failure_is_not_input_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_atomic_reduction(**_: object) -> None:
        raise RequestUnderstandingV2Error(
            RequestUnderstandingAtomicFailureCodeV2.DURABLE_CLOSURE_COMMIT_FAILED
        )

    monkeypatch.setattr(
        agent_run_service_module,
        "validate_and_reduce_initial_request_v2",
        fail_atomic_reduction,
    )
    service, _events, _model, runtime, _conversation, order, _artifact = _build()

    with pytest.raises(
        AgentRunExecutionError,
        match="Request Understanding internal failure",
    ) as captured:
        _run(service)

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert runtime.task_history == []
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert order.queries == []
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert len(runtime.finalize_run_commands) == 1
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[0]
    )
    assert "DURABLE_CLOSURE_COMMIT_FAILED" not in repr(
        runtime.trace_events
    )
    _assert_no_response_rendered_or_run_stopped(runtime)


@pytest.mark.parametrize(
    "read_mode",
    [
        "empty",
        "duplicate",
        "foreign_conversation",
        "stale_content",
    ],
)
def test_untrusted_authoritative_message_reads_fail_before_provider(
    read_mode: str,
) -> None:
    events: list[str] = []
    model = ModelSpy(events)
    conversation = MessageReadOverrideConversationSpy(
        events,
        read_mode=read_mode,
    )
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model,
        conversation=conversation,
    )

    with pytest.raises(
        AgentRunExecutionError,
        match="authoritative current Message unavailable",
    ):
        _run(service)

    assert model.next_move_calls == 0
    assert "initial_graph_v2_saved" not in events
    assert runtime.task_history == []
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert runtime.observation_commands == []
    assert order.queries == []
    assert runtime.run_record is None
    assert runtime.finalize_run_commands == []
    _assert_no_response_rendered_or_run_stopped(runtime)


@pytest.mark.parametrize(
    ("task_candidate_count", "reject_all_candidates"),
    [
        (0, False),
        (1, True),
        (2, False),
    ],
    ids=("zero", "all-reject", "multi-accept"),
)
def test_unscoped_v2_outcomes_fail_without_write_or_product_completion(
    task_candidate_count: int,
    reject_all_candidates: bool,
) -> None:
    events: list[str] = []
    model = ModelSpy(
        events,
        task_candidate_count=task_candidate_count,
        reject_all_candidates=reject_all_candidates,
    )
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model
    )

    with pytest.raises(
        AgentRunExecutionError,
        match="Request Understanding outcome is not routable",
    ):
        _run(service)

    assert "initial_graph_v2_saved" not in events
    assert runtime.task_history == []
    assert runtime.gates == []
    assert runtime.create_tool_commands == []
    assert runtime.observation_commands == []
    assert order.queries == []
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert len(runtime.finalize_run_commands) == 1
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[0]
    )
    _assert_no_response_rendered_or_run_stopped(runtime)


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


@pytest.mark.parametrize(
    "invalid_source_version",
    [
        None,
        "",
        "bad",
        "mock-order-source-version.p0.v1:sha256:" + ("A" * 64),
        b"mock-order-source-version.p0.v1:sha256:" + (b"a" * 64),
        SourceVersionSubclass(SYNTHETIC_SOURCE_VERSION),
    ],
)
def test_service_rejects_injected_noncanonical_observation_version(
    invalid_source_version: object,
) -> None:
    service, events, model, runtime, _conversation, order, _artifact = _build()
    service._read_tool_executor = ObservationVersionOverrideExecutor(
        service._read_tool_executor,
        invalid_source_version,
    )

    result = _run(service)

    assert result.outcome is AgentOutcome.BLOCKED
    assert result.message == "订单服务暂时不可用，请稍后重试。"
    assert model.presentation_calls == 0
    assert len(order.queries) == 1
    assert len(runtime.observation_commands) == 1
    assert len(runtime.manifests) == 1
    assert "manifest:2" not in events
    assert not any(
        event.event_type is TraceEventType.OBSERVATION_RECORDED
        for event in runtime.trace_events
    )
    assert runtime.run_record.stop_reason is StopReason.ORDER_SERVICE_UNAVAILABLE
    if invalid_source_version not in {None, ""}:
        assert repr(invalid_source_version) not in result.message


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


def test_presentation_protocol_subclass_fails_without_raw_context() -> None:
    events: list[str] = []
    model = ModelSpy(
        events,
        presentation_exception=ProviderProtocolSignalSubclass(),
    )
    service, _events, _model, runtime, _conversation, order, _artifact = _build(
        model=model
    )

    with pytest.raises(
        AgentRunExecutionError,
        match="noncanonical Presentation Provider signal",
    ) as captured:
        _run(service)

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert "raw-customer-B-secret" not in repr(captured.value)
    assert len(order.queries) == 1
    assert len(runtime.observation_commands) == 1
    assert model.presentation_calls == 1
    assert runtime.run_record.status is AgentRunStatus.FAILED
    assert len(runtime.finalize_run_commands) == 1
    _assert_failed_terminal_projection_is_empty(
        runtime.finalize_run_commands[0]
    )
    _assert_no_response_rendered_or_run_stopped(runtime)


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


def test_active_runtime_source_has_no_v1_or_source_version_fallback() -> None:
    source = inspect.getsource(agent_run_service_module.AgentRunService)

    assert "validate_and_reduce_initial_request(" not in source
    assert "SaveRequestUnderstandingCommand(" not in source
    assert ".create_initial_task_graph_if_current(" not in source
    assert 'or "order-observation.p0.v1"' not in source
    assert ".create_initial_task_graph_v2_if_current(" in source
    assert "validate_and_reduce_initial_request_v2(" in source


def test_active_runtime_and_owned_double_expose_only_ru_v2_symbols() -> None:
    legacy_symbols = {
        "ModelProvider",
        "RequestUnderstandingOutput",
        "validate_and_reduce_initial_request",
        "SaveRequestUnderstandingCommand",
        "CreateInitialTaskGraphCommand",
        "create_initial_task_graph_if_current",
    }
    runtime_tree = ast.parse(inspect.getsource(agent_run_service_module))
    runtime_symbols = {
        symbol
        for node in ast.walk(runtime_tree)
        for symbol in (
            (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name.rsplit(".", 1)[-1]
                if isinstance(node, ast.alias)
                else node.name
                if isinstance(
                    node,
                    (
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                        ast.FunctionDef,
                    ),
                )
                else None
            ),
        )
        if symbol is not None
    }
    owned_double_tree = ast.parse(inspect.getsource(RuntimeSpy))
    owned_double_methods = {
        node.name
        for node in ast.walk(owned_double_tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }

    assert legacy_symbols.isdisjoint(runtime_symbols)
    assert legacy_symbols.isdisjoint(owned_double_methods)
    assert {
        "ModelProviderV2",
        "validate_and_reduce_initial_request_v2",
        "CreateInitialTaskGraphV2Command",
        "create_initial_task_graph_v2_if_current",
    } <= runtime_symbols | owned_double_methods


def test_cycle2_mapper_is_complete_disjoint_and_imports_phase1_by_reference() -> None:
    mapper = RunResultMapper()

    assert mapper.imported_contract == PHASE1_RESULT_MAPPER_CONTRACT
    assert tuple(ref.value for ref in mapper.imported_references) == (
        "P1-RM-ORDER-SUCCESS",
        "P1-RM-GATE-REJECTED",
        "P1-RM-ORDER-SERVICE-UNAVAILABLE",
        "P1-RM-PROCESS-RESTART",
    )
    assert all(mapper.import_reference(ref) is ref for ref in ImportedMapperReference)
    rows = tuple(mapper.map_cycle2(signal) for signal in Cycle2MapperSignal)
    assert rows == mapper.delta_rows
    assert len(rows) == len(Cycle2MapperSignal) == 21
    assert len({row.row_id for row in rows}) == len(rows)
    assert {"RM-17", "RM-I03"}.isdisjoint(row.row_id for row in rows)
    assert {ref.value for ref in ImportedMapperReference}.isdisjoint(
        row.row_id for row in rows
    )


@pytest.mark.parametrize(
    ("signal", "row_id", "disposition"),
    [
        (Cycle2MapperSignal.SEARCH_MULTIPLE, "RM-02", MapperDisposition.EMIT),
        (
            Cycle2MapperSignal.INTERNAL_RETRY_AUTHORIZED,
            "RM-07",
            MapperDisposition.INTERNAL_RETRY,
        ),
        (
            Cycle2MapperSignal.ORDINARY_OBSOLETE_RUN,
            "RM-I01",
            MapperDisposition.SUPPRESS_OBSOLETE_RUN,
        ),
        (
            Cycle2MapperSignal.RETRY_RECOVERY_OBSOLETE_RUN,
            "RM-I04",
            MapperDisposition.SUPPRESS_OBSOLETE_RUN,
        ),
        (
            Cycle2MapperSignal.CONTRADICTORY_INTERRUPTION_EVIDENCE,
            "RM-I05",
            MapperDisposition.NO_STATE_MUTATION,
        ),
    ],
)
def test_cycle2_mapper_uses_exact_discriminators_without_first_match(
    signal: Cycle2MapperSignal,
    row_id: str,
    disposition: MapperDisposition,
) -> None:
    row = RunResultMapper().map_cycle2(signal)
    assert row.row_id == row_id
    assert row.disposition is disposition

    with pytest.raises(ValueError, match="canonical"):
        RunResultMapper().map_cycle2(signal.value)  # type: ignore[arg-type]


def test_cycle2_order_only_completion_preserves_phase1_and_has_no_shipment_call() -> None:
    service = Cycle2AgentRunService(
        runtime_record_port=object(),  # type: ignore[arg-type]
        deterministic_renderer=DeterministicRenderer(),
        uuid_factory=uuid4,
    )
    observation = OrderObservation(
        observation_id=uuid4(),
        source_tool="get_order",
        source_resource_ref="safe-order-ref",
        source_version=SYNTHETIC_SOURCE_VERSION,
        normalized_type="ORDER_SUMMARY",
        normalized_value=OrderSummaryProjection(
            order_number="O-1001",
            status=OrderStatus.SHIPPED,
            line_items=(
                OrderLineSummary(product_name="轻量跑鞋", quantity=1),
            ),
            ordered_at=NOW,
            status_updated_at=NOW,
        ),
        observed_at=NOW,
        recorded_at=NOW,
        visibility=ObservationVisibility.MODEL_VISIBLE,
    )
    plan = PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.NEUTRAL,
        opening_variant=OpeningVariant.DIRECT,
        field_order=tuple(PresentationField),
        closing_variant=ClosingVariant.NONE,
    )

    result = service.complete_order_only(
        run_id=uuid4(), observation=observation, plan=plan
    )

    assert result.outcome is AgentOutcome.COMPLETED
    assert "O-1001" in result.message
    source = inspect.getsource(Cycle2AgentRunService.complete_order_only)
    assert "get_shipment" not in source
    assert "_runtime_record_port" not in source


def test_cycle2_orchestration_source_keeps_selection_and_obsolete_fences_closed() -> None:
    ordinal_source = inspect.getsource(
        Cycle2AgentRunService.apply_ordinal_selection
    )
    obsolete_source = inspect.getsource(
        Cycle2AgentRunService.finalize_obsolete_run
    )
    recovery_obsolete_source = inspect.getsource(
        Cycle2AgentRunService.finalize_retry_recovery_obsolete
    )

    assert "apply_order_candidate_selection_if_current" in ordinal_source
    assert "search_orders" not in ordinal_source
    assert "apply_order_search_outcome" not in ordinal_source
    assert "finalize_superseded_run_if_current" in obsolete_source
    assert "map_cycle2_result" not in obsolete_source
    assert "outbound_result" not in obsolete_source
    assert "RETRY_RECOVERY_OBSOLETE_RUN" not in obsolete_source
    assert (
        "finalize_state_invalidated_tool_recovery_if_current"
        in recovery_obsolete_source
    )
    assert "RETRY_RECOVERY_OBSOLETE_RUN" in recovery_obsolete_source
    assert "outbound_result" not in recovery_obsolete_source


def _cycle2_typed_execution(
    *,
    tool: Cycle2ToolName,
    payload: dict[str, object],
) -> Cycle2ReadToolExecution:
    tool_call_id = uuid4()
    attempt = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=NOW,
        finished_at=NOW,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    terminal = ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name=tool,
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref="customer-A",
        validated_task_state_version=1,
        argument_binding_refs=(uuid4(),),
        verified_target_ref=(
            uuid4() if tool is Cycle2ToolName.GET_SHIPMENT else None
        ),
        effect=ToolEffect.READ,
        attempt_count=1,
        attempts=(attempt,),
        status=ToolCallStatus.SUCCEEDED,
        started_at=NOW,
        finished_at=NOW,
        result_ref=uuid4(),
    )
    return Cycle2ReadToolExecution(
        terminal_tool_call=terminal,
        tool_result=ToolResult(
            tool_call_id=tool_call_id,
            canonical_tool_name=tool.value,
            outcome=ToolResultOutcome.SUCCESS,
            payload=payload,
            retryable=False,
            completed_at=NOW,
        ),
    )


def test_cycle2_same_attempt_payload_maps_to_exact_typed_results() -> None:
    search = SearchOrdersResult(outcome=SearchOrdersOutcome.NO_MATCH)
    shipment = GetShipmentResult(outcome=GetShipmentOutcome.NO_SHIPMENT)

    mapped_search = map_cycle2_search_orders_tool_result(
        _cycle2_typed_execution(
            tool=Cycle2ToolName.SEARCH_ORDERS,
            payload=search.model_dump(mode="json"),
        )
    )
    mapped_shipment = map_cycle2_get_shipment_tool_result(
        _cycle2_typed_execution(
            tool=Cycle2ToolName.GET_SHIPMENT,
            payload=shipment.model_dump(mode="json"),
        )
    )

    assert mapped_search == search
    assert mapped_shipment == shipment


def test_cycle2_typed_result_mapper_rejects_partial_or_cross_tool_payload() -> None:
    payload = SearchOrdersResult(
        outcome=SearchOrdersOutcome.NO_MATCH
    ).model_dump(mode="json")
    payload.pop("failure_code")
    with pytest.raises(AgentRunExecutionError, match="typed mapping"):
        map_cycle2_search_orders_tool_result(
            _cycle2_typed_execution(
                tool=Cycle2ToolName.SEARCH_ORDERS,
                payload=payload,
            )
        )

    exact_payload = SearchOrdersResult(
        outcome=SearchOrdersOutcome.NO_MATCH
    ).model_dump(mode="json")
    with pytest.raises(AgentRunExecutionError, match="typed ToolResult"):
        map_cycle2_search_orders_tool_result(
            _cycle2_typed_execution(
                tool=Cycle2ToolName.GET_SHIPMENT,
                payload=exact_payload,
            )
        )


class _Cycle2ContextSink:
    async def save_context_manifest(self, _manifest: object) -> None:
        raise AssertionError("these handler tests must not reach Tool dispatch")


class _Cycle2UnusedExecutor:
    async def execute_with_result(self, **_kwargs: object) -> object:
        raise AssertionError("these handler tests inject the Tool result seam")


class _Cycle2ProviderHarness:
    def __init__(self, *, ordinal: int = 2) -> None:
        self.ordinal = ordinal
        self.control_purposes: list[Cycle2ControlPurpose] = []

    async def propose_cycle2_initial(
        self,
        request: object,
    ) -> Cycle2InitialRequestUnderstandingOutputV2:
        message_ref = request.message_ref
        return Cycle2InitialRequestUnderstandingOutputV2(
            schema_version="e2e01-cycle2-initial.p0.v1",
            message_ref=message_ref,
            contextualization=QueryContextualizationCandidateV2(
                text="查找最近购买的轻量跑鞋订单",
                resolved_reference_candidates=(),
                uncertainties=(),
                source_message_refs=(message_ref,),
            ),
            task_delta_candidates=(
                Cycle2InitialTaskDeltaCandidateV2(
                    candidate_id=uuid4(),
                    operation=TaskDeltaOperation.ADD_GOAL,
                    goal_patch="查找最近购买的轻量跑鞋订单",
                    input_candidates=(
                        Cycle2InputCandidate(
                            name="product_description",
                            candidate_value="轻量跑鞋",
                            source_ref=message_ref,
                            source_quote="轻量跑鞋",
                            confidence=0.99,
                        ),
                    ),
                    confidence=0.99,
                ),
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="search_orders",
                arguments={"product_description": "轻量跑鞋"},
                base_task_state_version=None,
            ),
        )

    async def propose_cycle2_continuation(
        self,
        request: object,
    ) -> Cycle2InputCandidate:
        return Cycle2InputCandidate(
            name="candidate_ordinal",
            candidate_value=self.ordinal,
            source_ref=request.message_ref,
            source_quote=request.original_query,
            confidence=0.99,
        )

    async def propose_cycle2_control(
        self,
        _request: object,
        purpose: Cycle2ControlPurpose,
    ) -> Cycle2ControlCandidate:
        self.control_purposes.append(purpose)
        tool_name = {
            Cycle2ControlPurpose.PROPOSE_GET_ORDER: "get_order",
            Cycle2ControlPurpose.PROPOSE_GET_SHIPMENT: "get_shipment",
        }.get(purpose)
        if tool_name is not None:
            return Cycle2ControlCandidate(
                kind=Cycle2ControlCandidateKind.CALL_TOOL,
                requested_tool_name=tool_name,
            )
        return Cycle2ControlCandidate(
            kind=Cycle2ControlCandidateKind.FINISH,
        )


class _Cycle2OrderIdProvider(_Cycle2ProviderHarness):
    async def propose_cycle2_continuation(
        self,
        request: object,
    ) -> Cycle2InputCandidate:
        return Cycle2InputCandidate(
            name="order_id",
            candidate_value="O-1001",
            source_ref=request.message_ref,
            source_quote="O-1001",
            confidence=0.99,
        )


class _StrictCycle2ControlProvider(_Cycle2ProviderHarness):
    def __init__(
        self,
        expected_purposes: tuple[Cycle2ControlPurpose, ...],
        *,
        wrong_candidate: bool = False,
    ) -> None:
        super().__init__()
        self.expected_purposes = list(expected_purposes)
        self.wrong_candidate = wrong_candidate

    async def propose_cycle2_control(
        self,
        request: object,
        purpose: Cycle2ControlPurpose,
    ) -> Cycle2ControlCandidate:
        if not self.expected_purposes:
            raise ProviderProtocolError()
        expected = self.expected_purposes.pop(0)
        if purpose is not expected:
            raise ProviderProtocolError()
        if self.wrong_candidate:
            self.control_purposes.append(purpose)
            return Cycle2ControlCandidate(
                kind=Cycle2ControlCandidateKind.CALL_TOOL,
                requested_tool_name="get_order",
            )
        return await super().propose_cycle2_control(request, purpose)

    def assert_exhausted(self) -> None:
        if self.expected_purposes:
            raise ProviderProtocolError()


class _Cycle2RuntimeHarness:
    def __init__(self) -> None:
        self.current_session: Cycle2CurrentSessionTaskClosure | None = None
        self.events: list[str] = []
        self.root_commands: list[object] = []
        self.running_records: list[object] = []
        self.initial_graph_command: object | None = None
        self.search_write_result = Cycle2WriteResult.APPLIED
        self.search_commands: list[object] = []
        self.selection_commands: list[object] = []
        self.selection_closure_available = True
        self.binding_commands: list[object] = []
        self.finalize_commands: list[object] = []
        self.search_load_count = 0

    async def load_current_session_task_for_owner(self, **kwargs: object):
        self.events.append("load-current-session")
        if self.current_session is not None:
            assert kwargs["owner_scope"] == self.current_session.owner_scope
        return self.current_session

    async def insert_cycle2_run_root_if_current(self, command: object):
        self.events.append("insert-run-root")
        self.root_commands.append(command)
        return Cycle2WriteResult.APPLIED

    async def start_cycle2_run_if_created(self, command: object):
        self.events.append("start-run")
        self.running_records.append(command.next_running_run_record)
        return Cycle2WriteResult.APPLIED

    async def create_cycle2_initial_task_graph_if_current(self, command: object):
        self.events.append("create-initial-graph")
        self.initial_graph_command = command
        return Cycle2WriteResult.APPLIED

    async def load_order_search_current_closure_for_owner(
        self,
        **kwargs: object,
    ):
        self.search_load_count += 1
        initial = self.initial_graph_command
        assert initial is not None
        graph = initial.reducer_decision.task_graph
        binding = graph.input_binding
        return agent_run_service_module.OrderSearchCurrentReadClosure(
            owner_scope=kwargs["owner_scope"],
            trusted_conversation_record=initial.expected_conversation_record,
            source_run_record=initial.expected_running_run_record,
            current_query_binding=AcceptedOrderSearchQueryBindingReadClosure(
                binding_ref=binding.binding_id,
                normalized_query=binding.normalized_value,
                private_owner_scope_ref=kwargs["owner_scope"].customer_id,
                conversation_id=initial.expected_conversation_record.conversation_id,
                task_id=graph.task.task_id,
                request_unit_id=graph.request_unit.request_unit_id,
                accepted_task_state_version=graph.task.state_version,
                current_task_state_version=graph.task.state_version,
                source_message_record=initial.expected_user_message_record,
                accepted_at=binding.created_at,
            ),
            current_task_record=graph.task,
            current_request_unit_record=graph.request_unit,
            trusted_read_at=kwargs["trusted_read_at"],
        )

    async def apply_order_search_outcome_if_current(self, command: object):
        self.search_commands.append(command)
        return self.search_write_result

    async def load_order_candidate_selection_closure_for_owner(
        self,
        **kwargs: object,
    ) -> OrderCandidateSelectionReadClosure | None:
        if not self.selection_closure_available:
            return None
        session = self.current_session
        initial = self.initial_graph_command
        assert session is not None and initial is not None
        candidate_set = session.current_candidate_set_records[0]
        observation = session.current_search_observation_records[0]
        request = kwargs["selection_request"]
        selected_entry = tuple(
            entry
            for entry in candidate_set.ordered_candidates
            if entry.ordinal == request.ordinal
        )[0]
        resolved = tuple(
            target
            for target in observation.candidate_target_bindings
            if target.observation_candidate_ref
            == selected_entry.observation_candidate_ref
        )[0]
        binding = session.current_input_binding_records[0]
        return OrderCandidateSelectionReadClosure(
            owner_scope=session.owner_scope,
            trusted_conversation_record=session.conversation_record,
            current_run_record=self.running_records[-1],
            current_run_task_link_record=(
                self.root_commands[-1].active_run_task_link_record
            ),
            current_task_record=session.current_task_record,
            current_request_unit_record=session.current_request_unit_record,
            current_candidate_set_record=candidate_set,
            search_observation_record=observation,
            selection_request=request,
            saved_selection_message_record=(
                self.root_commands[-1].user_message_record
            ),
            current_query_binding=AcceptedOrderSearchQueryBindingReadClosure(
                binding_ref=binding.binding_id,
                normalized_query=binding.normalized_value,
                private_owner_scope_ref=session.owner_scope.customer_id,
                conversation_id=session.conversation_record.conversation_id,
                task_id=session.current_task_record.task_id,
                request_unit_id=session.current_request_unit_record.request_unit_id,
                accepted_task_state_version=candidate_set.base_task_state_version,
                current_task_state_version=session.current_task_record.state_version,
                source_message_record=initial.expected_user_message_record,
                accepted_at=binding.created_at,
            ),
            pending_candidate_set_ref=candidate_set.candidate_set_id,
            current_query_binding_refs=candidate_set.query_binding_refs,
            resolved_owner_scoped_order_target_ref=resolved.owner_scoped_order_ref,
            trusted_now=kwargs["trusted_now"],
        )

    async def apply_order_candidate_selection_if_current(self, command: object):
        self.selection_commands.append(command)
        return Cycle2WriteResult.APPLIED

    async def load_continuation_input_binding_closure_for_owner(
        self,
        **kwargs: object,
    ):
        session = self.current_session
        assert session is not None
        return ContinuationInputBindingReadClosure(
            owner_scope=session.owner_scope,
            trusted_conversation_record=session.conversation_record,
            current_conversation_task_link_record=(
                session.current_conversation_task_link_record
            ),
            saved_user_message_record=self.root_commands[-1].user_message_record,
            current_task_record=session.current_task_record,
            current_request_unit_record=session.current_request_unit_record,
            current_input_binding_records=session.current_input_binding_records,
            trusted_now=kwargs["trusted_now"],
        )

    async def apply_continuation_input_binding_if_current(self, command: object):
        self.binding_commands.append(command)
        return Cycle2WriteResult.APPLIED

    async def finalize_cycle2_run_if_current(self, command: object):
        self.finalize_commands.append(command)
        return Cycle2WriteResult.APPLIED

    async def load_cycle2_exact_run_evidence_for_owner(self, **_kwargs: object):
        command = self.finalize_commands[-1]
        root = self.root_commands[-1]
        task = command.current_task_record
        unit = command.current_request_unit_record
        if task is None:
            tasks = ()
            units = ()
            links = ()
            bindings = ()
        else:
            tasks = (task,)
            units = (unit,)
            links = (command.terminal_run_task_link_record,)
            initial = self.initial_graph_command
            assert initial is not None
            initial_binding = initial.reducer_decision.task_graph.input_binding
            bindings = (initial_binding,)
        user_messages = tuple(
            root_command.user_message_record
            for root_command in self.root_commands
            if root_command.user_message_record.conversation_id
            == root.conversation_record.conversation_id
        )
        return Cycle2ExactRunEvidenceClosure(
            owner_scope=command.owner_scope,
            conversation_record=root.conversation_record,
            run_record=command.terminal_run_record,
            message_records=(*user_messages, command.assistant_message_record),
            run_task_link_records=links,
            task_records=tasks,
            request_unit_records=units,
            input_binding_records=bindings,
            trace_records=command.ordinary_trace_records,
            terminal_result=command.terminal_result,
        )


class _Cycle2OutcomeCapture:
    def __init__(self, runtime: _Cycle2RuntimeHarness | None = None) -> None:
        self.runtime = runtime
        self.observations: list[Cycle2ExecutionOutcomeObservationV1] = []

    def observe_cycle2_execution_outcome(
        self,
        observation: Cycle2ExecutionOutcomeObservationV1,
    ) -> None:
        if self.runtime is not None:
            assert self.runtime.finalize_commands
        self.observations.append(observation)


def _cycle2_handler(
    runtime: _Cycle2RuntimeHarness,
    provider: _Cycle2ProviderHarness,
    *,
    observer: Any | None = None,
    clock_now: datetime = NOW,
) -> Cycle2AgentRunHandler:
    return Cycle2AgentRunHandler(
        runtime_record_port=runtime,
        context_record_port=_Cycle2ContextSink(),
        request_understanding_provider=provider,
        read_tool_executor=_Cycle2UnusedExecutor(),
        deterministic_renderer=DeterministicRenderer(),
        clock=lambda: clock_now,
        uuid_factory=UuidSequence(),
        provider_lane="scripted-cycle2",
        redaction_policy_version="redaction-v1",
        execution_outcome_observer=observer,
    )


def _cycle2_multiple_search_result() -> SearchOrdersResult:
    def candidate(order_number: str, suffix: str) -> OrderCandidate:
        matched = MatchedOrderLine(
            line_ordinal=1,
            product_name="轻量跑鞋",
            quantity=1,
            product_category="鞋",
            normalized_search_aliases=("轻量跑鞋",),
        )
        return OrderCandidate(
            owner_scoped_order_ref=f"private-order-{suffix}",
            order_number=order_number,
            ordered_at=NOW,
            status=OrderStatus.SHIPPED,
            matched_lines=(matched,),
            public_summary=build_order_candidate_public_summary(
                order_number=order_number,
                ordered_at=NOW,
                status=OrderStatus.SHIPPED,
                matched_lines=(matched,),
            ),
            candidate_source_version=(
                "mock-order-search-candidate-source-version.p0.v1:sha256:"
                + suffix * 64
            ),
        )

    return SearchOrdersResult(
        outcome=SearchOrdersOutcome.MULTIPLE,
        candidates=(candidate("O-1001", "1"), candidate("O-1002", "2")),
        snapshot_resource_ref="orders:customer-A:window",
        snapshot_source_version=(
            "mock-order-search-snapshot-source-version.p0.v1:sha256:"
            + "a" * 64
        ),
        observed_at=NOW,
    )


def _cycle2_search_execution(
    *,
    turn: object,
    task: TaskRecord,
    unit: RequestUnitRecord,
    binding_ref: UUID,
    result: SearchOrdersResult,
) -> Cycle2ReadToolExecution:
    tool_call_id = uuid4()
    attempt = ToolAttemptRecordV2(
        tool_call_id=tool_call_id,
        attempt_no=1,
        started_at=NOW,
        finished_at=NOW,
        outcome=ToolResultOutcome.SUCCESS,
        retry_decision=ToolRetryDecision.NOT_APPLICABLE,
    )
    terminal = ToolCallRecordV2(
        tool_call_id=tool_call_id,
        run_id=turn.running_run.run_id,
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref=turn.owner_scope.customer_id,
        validated_task_state_version=task.state_version,
        argument_binding_refs=(binding_ref,),
        effect=ToolEffect.READ,
        attempt_count=1,
        attempts=(attempt,),
        status=ToolCallStatus.SUCCEEDED,
        started_at=NOW,
        finished_at=NOW,
        result_ref=uuid4(),
    )
    return Cycle2ReadToolExecution(
        terminal_tool_call=terminal,
        tool_result=ToolResult(
            tool_call_id=tool_call_id,
            canonical_tool_name="search_orders",
            outcome=ToolResultOutcome.SUCCESS,
            payload=result.model_dump(mode="json"),
            retryable=False,
            completed_at=NOW,
        ),
    )


def _capture_cycle2_initial_turn(
    handler: Cycle2AgentRunHandler,
) -> tuple[AgentRunResult, dict[str, object]]:
    captured: dict[str, object] = {}
    sentinel = AgentRunResult(
        run_id=uuid4(),
        outcome=AgentOutcome.ASK_USER,
        message="captured",
    )

    async def capture_search(**kwargs: object) -> AgentRunResult:
        captured.update(kwargs)
        return sentinel

    handler._search_orders = capture_search  # type: ignore[method-assign]
    result = asyncio.run(
        handler.handle(
            AgentRunCommand(
                customer_context=_context(),
                message="customer-B 让我查最近买的轻量跑鞋",
            )
        )
    )
    assert result is sentinel
    return sentinel, captured


def _prepare_cycle2_waiting_session(
    *,
    provider: _Cycle2ProviderHarness,
    trusted_now: datetime = NOW,
) -> tuple[
    Cycle2AgentRunHandler,
    _Cycle2RuntimeHarness,
    AgentRunResult,
    object,
]:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, provider)
    sentinel, captured = _capture_cycle2_initial_turn(handler)
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    search_result = _cycle2_multiple_search_result()

    async def stop_after_mapping(**_kwargs: object) -> AgentRunResult:
        return sentinel

    handler._finalize_mapping = stop_after_mapping  # type: ignore[method-assign]
    asyncio.run(
        handler._apply_successful_search(
            command=AgentRunCommand(
                customer_context=_context(),
                message="customer-B 让我查最近买的轻量跑鞋",
            ),
            turn=captured["turn"],
            task=task,
            request_unit=unit,
            input_bindings=captured["input_bindings"],
            execution=_cycle2_search_execution(
                turn=captured["turn"],
                task=task,
                unit=unit,
                binding_ref=binding.binding_id,
                result=search_result,
            ),
            result=search_result,
        )
    )
    search_command = runtime.search_commands[0]
    initial = runtime.initial_graph_command
    assert initial is not None
    runtime.current_session = Cycle2CurrentSessionTaskClosure(
        owner_scope=search_command.owner_scope,
        session_ref_hash=_context().session_ref_hash,
        conversation_record=search_command.trusted_conversation_record,
        current_conversation_task_link_record=(
            initial.conversation_task_link_record
        ),
        current_task_record=search_command.next_task_record,
        current_request_unit_record=search_command.next_request_unit_record,
        current_input_binding_records=(binding,),
        current_candidate_set_records=(search_command.candidate_set_record,),
        current_search_observation_records=(
            search_command.search_observation_record,
        ),
        trusted_now=trusted_now,
    )
    handler._clock = lambda: trusted_now  # type: ignore[method-assign]
    return handler, runtime, sentinel, search_command


def test_cycle2_handler_first_turn_builds_real_trusted_root_and_graph() -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())

    _, captured = _capture_cycle2_initial_turn(handler)

    root = runtime.root_commands[0]
    initial = runtime.initial_graph_command
    assert initial is not None
    assert runtime.events == [
        "load-current-session",
        "insert-run-root",
        "start-run",
        "create-initial-graph",
    ]
    assert root.current_session_closure is None
    assert root.owner_scope.customer_id == "customer-A"
    assert root.conversation_record.owner_customer_id == "customer-A"
    assert "customer-B" in root.user_message_record.content
    assert initial.reducer_decision.task_graph.task.owner_customer_id == "customer-A"
    assert initial.reducer_decision.task_graph.input_binding.normalized_value == (
        "轻量跑鞋"
    )
    assert captured["task"] == initial.reducer_decision.task_graph.task


def test_cycle2_initial_search_candidate_is_raw_closed_for_gateway() -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())

    _, captured = _capture_cycle2_initial_turn(handler)

    candidate = captured["candidate_factory"](
        InitialToolCallV2ReadClosure(
            owner_scope=captured["turn"].owner_scope,
            current_task_record=captured["task"],
            current_request_unit_record=captured["request_unit"],
            current_input_binding_records=captured["input_bindings"],
            trusted_read_at=NOW,
        ),
        uuid4(),
        uuid4(),
        None,
    )
    assert candidate.verified_target_ref is None
    assert candidate.__pydantic_fields_set__ == set(
        type(candidate).model_fields
    )


def test_cycle2_execute_tool_builds_raw_closed_gateway_loaded_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())
    _, captured = _capture_cycle2_initial_turn(handler)
    closure = InitialToolCallV2ReadClosure(
        owner_scope=captured["turn"].owner_scope,
        current_task_record=TaskRecord.model_validate(
            captured["task"].model_dump(mode="python")
        ),
        current_request_unit_record=RequestUnitRecord.model_validate(
            captured["request_unit"].model_dump(mode="python")
        ),
        current_input_binding_records=captured["input_bindings"],
        current_verified_order_targets=(),
        current_target_observations=(),
        trusted_read_at=NOW,
    )
    gateway_inputs: dict[str, object] = {}

    class _InitialClosureRuntime:
        async def load_initial_tool_call_v2_closure_for_owner(
            self,
            **_kwargs: object,
        ) -> InitialToolCallV2ReadClosure:
            return closure

    class _ManifestSink:
        async def save_context_manifest(self, record: object) -> None:
            gateway_inputs["manifest"] = record

    class _GatewayCaptured(Exception):
        pass

    real_gateway = agent_run_service_module.evaluate_cycle2_control_gateway

    def capture_gateway(**kwargs: object) -> object:
        gateway_inputs.update(kwargs)
        gateway_inputs["gate"] = real_gateway(**kwargs)
        raise _GatewayCaptured

    handler._runtime_record_port = _InitialClosureRuntime()  # type: ignore[assignment]
    handler._context_record_port = _ManifestSink()  # type: ignore[assignment]
    monkeypatch.setattr(
        agent_run_service_module,
        "evaluate_cycle2_control_gateway",
        capture_gateway,
    )

    with pytest.raises(_GatewayCaptured):
        asyncio.run(
            handler._execute_tool(
                command=AgentRunCommand(
                    customer_context=_context(),
                    message="customer-B 让我查最近买的轻量跑鞋",
                ),
                turn=captured["turn"],
                task_id=captured["task"].task_id,
                request_unit_id=captured["request_unit"].request_unit_id,
                candidate_factory=captured["candidate_factory"],
            )
        )

    assert cycle2_pydantic_model_graph_is_raw_closed(
        gateway_inputs["candidate"],
        gateway_inputs["loaded_closure"],
    )
    loaded = gateway_inputs["loaded_closure"]
    assert loaded.customer_context.provenance == "SERVER_AUTH_ADAPTER"
    assert loaded.context_manifest == gateway_inputs["manifest"]
    assert loaded.context_manifest.task_state_ref_and_version is None
    assert gateway_inputs["candidate"].proposed_base_task_state_version is None
    assert gateway_inputs["gate"].decision.value == "ACCEPT"
    assert gateway_inputs["gate"].reason_code is None


def test_cycle2_execute_tool_rebases_prior_progress_to_current_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())
    _, captured = _capture_cycle2_initial_turn(handler)
    turn = captured["turn"]
    previous_manifest_id = uuid4()
    previous_state_version = 9
    turn.tool_progress.append(
        Cycle2ToolProgressFact(
            tool_call_id=uuid4(),
            run_id=turn.running_run.run_id,
            context_manifest_id=previous_manifest_id,
            tool_registry_version=(
                handler._registry_snapshot.tool_registry_version
            ),
            model_visible_toolset_hash=(
                handler._registry_snapshot.model_visible_toolset_hash
            ),
            canonical_tool_name=Cycle2ToolName.SEARCH_ORDERS,
            validated_arguments={"product_description": "轻量跑鞋"},
            task_state_version=previous_state_version,
            argument_binding_refs=(
                captured["input_bindings"][0].binding_id,
            ),
            verified_target_ref=None,
        )
    )
    closure = InitialToolCallV2ReadClosure(
        owner_scope=turn.owner_scope,
        current_task_record=captured["task"],
        current_request_unit_record=captured["request_unit"],
        current_input_binding_records=captured["input_bindings"],
        current_verified_order_targets=(),
        current_target_observations=(),
        trusted_read_at=NOW,
    )
    captured_gateway: dict[str, object] = {}

    class _Runtime:
        async def load_initial_tool_call_v2_closure_for_owner(
            self,
            **_kwargs: object,
        ) -> InitialToolCallV2ReadClosure:
            return closure

    class _Context:
        async def save_context_manifest(self, _record: object) -> None:
            return None

    class _Captured(Exception):
        pass

    def capture_gateway(**kwargs: object) -> object:
        captured_gateway.update(kwargs)
        raise _Captured

    handler._runtime_record_port = _Runtime()  # type: ignore[assignment]
    handler._context_record_port = _Context()  # type: ignore[assignment]
    monkeypatch.setattr(
        agent_run_service_module,
        "evaluate_cycle2_control_gateway",
        capture_gateway,
    )

    with pytest.raises(_Captured):
        asyncio.run(
            handler._execute_tool(
                command=AgentRunCommand(
                    customer_context=_context(),
                    message="查找轻量跑鞋订单",
                ),
                turn=turn,
                task_id=captured["task"].task_id,
                request_unit_id=captured["request_unit"].request_unit_id,
                candidate_factory=captured["candidate_factory"],
            )
        )

    candidate = captured_gateway["candidate"]
    progress = captured_gateway["loaded_closure"].progress_snapshot
    assert progress.context_manifest_id == candidate.context_manifest_id
    assert progress.task_state_version == candidate.validated_task_state_version
    assert progress.prior_tool_steps[0].context_manifest_id == (
        candidate.context_manifest_id
    )
    assert progress.prior_tool_steps[0].task_state_version == (
        candidate.validated_task_state_version
    )
    assert turn.tool_progress[0].context_manifest_id == previous_manifest_id
    assert turn.tool_progress[0].task_state_version == previous_state_version


def test_cycle2_search_conflict_finalizes_from_pre_cas_task_version() -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())
    sentinel, captured = _capture_cycle2_initial_turn(handler)
    runtime.search_write_result = Cycle2WriteResult.PROJECTION_CONFLICT
    finalized: dict[str, object] = {}

    async def capture_finalize(**kwargs: object) -> AgentRunResult:
        finalized.update(kwargs)
        return sentinel

    handler._finalize_mapping = capture_finalize  # type: ignore[method-assign]
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    result = _cycle2_multiple_search_result()
    outbound = asyncio.run(
        handler._apply_successful_search(
            command=AgentRunCommand(
                customer_context=_context(),
                message="customer-B 让我查最近买的轻量跑鞋",
            ),
            turn=captured["turn"],
            task=task,
            request_unit=unit,
            input_bindings=captured["input_bindings"],
            execution=_cycle2_search_execution(
                turn=captured["turn"],
                task=task,
                unit=unit,
                binding_ref=binding.binding_id,
                result=result,
            ),
            result=result,
        )
    )

    assert outbound is sentinel
    assert runtime.search_commands[0].next_task_record.state_version == 2
    assert finalized["task"].state_version == 1
    assert finalized["request_unit"].state_version == 1
    assert finalized["step"].mapping.row_id == "RM-03"


def test_cycle2_unique_search_commits_target_at_result_state_version() -> None:
    runtime = _Cycle2RuntimeHarness()
    provider = _Cycle2ProviderHarness()
    handler = _cycle2_handler(runtime, provider)
    sentinel, captured = _capture_cycle2_initial_turn(handler)
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    multiple = _cycle2_multiple_search_result()
    result = SearchOrdersResult(
        outcome=SearchOrdersOutcome.UNIQUE,
        candidates=(multiple.candidates[0],),
        snapshot_resource_ref=multiple.snapshot_resource_ref,
        snapshot_source_version=multiple.snapshot_source_version,
        observed_at=multiple.observed_at,
        failure_code=None,
    )
    get_order: dict[str, object] = {}

    async def capture_get_order(**kwargs: object) -> AgentRunResult:
        get_order.update(kwargs)
        return sentinel

    handler._get_order = capture_get_order  # type: ignore[method-assign]

    outbound = asyncio.run(
        handler._apply_successful_search(
            command=AgentRunCommand(
                customer_context=_context(),
                message="查找轻量跑鞋订单",
            ),
            turn=captured["turn"],
            task=task,
            request_unit=unit,
            input_bindings=captured["input_bindings"],
            execution=_cycle2_search_execution(
                turn=captured["turn"],
                task=task,
                unit=unit,
                binding_ref=binding.binding_id,
                result=result,
            ),
            result=result,
        )
    )

    assert outbound is sentinel
    search_command = runtime.search_commands[0]
    assert search_command.auto_target_record.result_task_state_version == 2
    assert search_command.auto_target_record.request_unit_id == (
        search_command.next_request_unit_record.request_unit_id
    )
    assert get_order["task"] == search_command.next_task_record
    assert get_order["request_unit"] == search_command.next_request_unit_record
    assert (
        get_order["control_purpose"]
        is Cycle2ControlPurpose.PROPOSE_GET_ORDER
    )


def test_cycle2_handler_continues_multiple_with_ordinal_without_research() -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())
    sentinel, captured = _capture_cycle2_initial_turn(handler)
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    search_result = _cycle2_multiple_search_result()

    async def stop_after_multiple(**_kwargs: object) -> AgentRunResult:
        return sentinel

    handler._finalize_mapping = stop_after_multiple  # type: ignore[method-assign]
    asyncio.run(
        handler._apply_successful_search(
            command=AgentRunCommand(
                customer_context=_context(),
                message="customer-B 让我查最近买的轻量跑鞋",
            ),
            turn=captured["turn"],
            task=task,
            request_unit=unit,
            input_bindings=captured["input_bindings"],
            execution=_cycle2_search_execution(
                turn=captured["turn"],
                task=task,
                unit=unit,
                binding_ref=binding.binding_id,
                result=search_result,
            ),
            result=search_result,
        )
    )
    search_command = runtime.search_commands[0]
    initial = runtime.initial_graph_command
    assert initial is not None
    runtime.current_session = Cycle2CurrentSessionTaskClosure(
        owner_scope=search_command.owner_scope,
        session_ref_hash=_context().session_ref_hash,
        conversation_record=search_command.trusted_conversation_record,
        current_conversation_task_link_record=(
            initial.conversation_task_link_record
        ),
        current_task_record=search_command.next_task_record,
        current_request_unit_record=search_command.next_request_unit_record,
        current_input_binding_records=(binding,),
        current_candidate_set_records=(search_command.candidate_set_record,),
        current_search_observation_records=(
            search_command.search_observation_record,
        ),
        trusted_now=NOW,
    )
    get_order: dict[str, object] = {}

    async def capture_get_order(**kwargs: object) -> AgentRunResult:
        get_order.update(kwargs)
        return sentinel

    handler._get_order = capture_get_order  # type: ignore[method-assign]
    second = asyncio.run(
        handler.handle(
            AgentRunCommand(customer_context=_context(), message="2")
        )
    )

    assert second is sentinel
    assert runtime.search_load_count == 1
    assert len(runtime.search_commands) == 1
    assert len(runtime.selection_commands) == 1
    selection = runtime.selection_commands[0]
    assert selection.ordinal_input_binding_record.normalized_value == 2
    assert selection.next_task_record.status is TaskStatus.ACTIVE
    assert selection.next_task_record.state_version == 3
    assert get_order["task"] == selection.next_task_record
    assert get_order["request_unit"] == selection.next_request_unit_record
    assert (
        get_order["control_purpose"]
        is Cycle2ControlPurpose.PROPOSE_GET_ORDER
    )


def test_cycle2_rejected_ordinal_persists_claim_without_selection_or_tool() -> None:
    runtime = _Cycle2RuntimeHarness()
    provider = _Cycle2ProviderHarness(ordinal=6)
    handler = _cycle2_handler(runtime, provider)
    sentinel, captured = _capture_cycle2_initial_turn(handler)
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    search_result = _cycle2_multiple_search_result()

    async def stop_after_mapping(**_kwargs: object) -> AgentRunResult:
        return sentinel

    handler._finalize_mapping = stop_after_mapping  # type: ignore[method-assign]
    asyncio.run(
        handler._apply_successful_search(
            command=AgentRunCommand(
                customer_context=_context(),
                message="customer-B 让我查最近买的轻量跑鞋",
            ),
            turn=captured["turn"],
            task=task,
            request_unit=unit,
            input_bindings=captured["input_bindings"],
            execution=_cycle2_search_execution(
                turn=captured["turn"],
                task=task,
                unit=unit,
                binding_ref=binding.binding_id,
                result=search_result,
            ),
            result=search_result,
        )
    )
    search_command = runtime.search_commands[0]
    initial = runtime.initial_graph_command
    assert initial is not None
    runtime.current_session = Cycle2CurrentSessionTaskClosure(
        owner_scope=search_command.owner_scope,
        session_ref_hash=_context().session_ref_hash,
        conversation_record=search_command.trusted_conversation_record,
        current_conversation_task_link_record=(
            initial.conversation_task_link_record
        ),
        current_task_record=search_command.next_task_record,
        current_request_unit_record=search_command.next_request_unit_record,
        current_input_binding_records=(binding,),
        current_candidate_set_records=(search_command.candidate_set_record,),
        current_search_observation_records=(
            search_command.search_observation_record,
        ),
        trusted_now=NOW,
    )

    outbound = asyncio.run(
        handler.handle(
            AgentRunCommand(customer_context=_context(), message="第六个")
        )
    )

    assert outbound is sentinel
    assert runtime.selection_commands == []
    assert len(runtime.binding_commands) == 1
    rejected_command = runtime.binding_commands[0]
    assert rejected_command.new_input_binding_record.normalized_value == 6
    assert (
        rejected_command.rejected_ordinal_selection.rejection_reason.value
        == "OUT_OF_RANGE"
    )
    assert rejected_command.next_task_record.status is TaskStatus.WAITING_USER
    assert rejected_command.next_request_unit_record.open_questions == (
        search_command.next_request_unit_record.open_questions
    )


@pytest.mark.parametrize(
    ("reason", "ordinal", "shape", "trusted_now"),
    [
        (
            Cycle2OrdinalSelectionRejectionReason.OUT_OF_RANGE,
            6,
            "CURRENT",
            NOW,
        ),
        (
            Cycle2OrdinalSelectionRejectionReason.EXPIRED,
            2,
            "CURRENT",
            NOW + SHIPMENT_FRESHNESS_TTL * 4,
        ),
        (
            Cycle2OrdinalSelectionRejectionReason.CROSS_TASK,
            2,
            "EMPTY_HINT",
            NOW,
        ),
        (
            Cycle2OrdinalSelectionRejectionReason.OWNER_MISMATCH,
            2,
            "READER_ABSENT_HINT",
            NOW,
        ),
        (
            Cycle2OrdinalSelectionRejectionReason.SUPERSEDED,
            2,
            "SUPERSEDED_HINT",
            NOW,
        ),
        (
            Cycle2OrdinalSelectionRejectionReason.CURRENT_SET_CARDINALITY_NOT_ONE,
            2,
            "EMPTY_HINT",
            NOW,
        ),
    ],
)
def test_cycle2_all_typed_ordinal_rejections_use_binding_only_cas(
    reason: Cycle2OrdinalSelectionRejectionReason,
    ordinal: int,
    shape: str,
    trusted_now: datetime,
) -> None:
    provider = _Cycle2ProviderHarness(ordinal=ordinal)
    handler, runtime, sentinel, _search_command = (
        _prepare_cycle2_waiting_session(
            provider=provider,
            trusted_now=trusted_now,
        )
    )
    session = runtime.current_session
    assert session is not None
    updates: dict[str, object] = {}
    if shape in {"EMPTY_HINT", "SUPERSEDED_HINT"}:
        updates.update(
            current_candidate_set_records=(),
            current_search_observation_records=(),
            ordinal_selection_rejection_hint=reason,
        )
    elif shape == "READER_ABSENT_HINT":
        updates["ordinal_selection_rejection_hint"] = reason
        runtime.selection_closure_available = False
    if shape == "SUPERSEDED_HINT":
        updates["superseded_candidate_set_refs"] = (
            session.current_candidate_set_records[0].candidate_set_id,
        )
    if updates:
        runtime.current_session = Cycle2CurrentSessionTaskClosure(
            **{
                **{
                    field_name: getattr(session, field_name)
                    for field_name in type(session).model_fields
                },
                **updates,
            }
        )

    outbound = asyncio.run(
        handler.handle(
            AgentRunCommand(
                customer_context=_context(),
                message="第六个" if ordinal == 6 else "第二个",
            )
        )
    )

    assert outbound is sentinel
    assert runtime.selection_commands == []
    assert len(runtime.binding_commands) == 1
    rejected = runtime.binding_commands[0]
    assert rejected.rejected_ordinal_selection.rejection_reason is reason
    assert rejected.new_input_binding_record.normalized_value == ordinal
    assert rejected.next_task_record.status is TaskStatus.WAITING_USER
    assert rejected.next_request_unit_record.open_questions
    assert not hasattr(rejected, "selection_record")
    assert not hasattr(rejected, "selected_target_ref")
    assert not hasattr(rejected, "tool_call_record")


@pytest.mark.parametrize("has_current_shipment", [False, True])
def test_cycle2_direct_order_id_routes_from_actual_current_observation_state(
    has_current_shipment: bool,
) -> None:
    runtime = _Cycle2RuntimeHarness()
    provider = _Cycle2OrderIdProvider()
    handler = _cycle2_handler(runtime, provider)
    sentinel, _captured = _capture_cycle2_initial_turn(handler)
    initial = runtime.initial_graph_command
    assert initial is not None
    graph = initial.reducer_decision.task_graph
    unit = graph.request_unit
    shipment_records: tuple[ShipmentObservation, ...] = ()
    if has_current_shipment:
        observed_at = NOW - SHIPMENT_FRESHNESS_TTL * 2
        shipment = ShipmentObservation(
            observation_id=uuid4(),
            private_owner_scope="customer-A",
            task_id=graph.task.task_id,
            request_unit_id=unit.request_unit_id,
            verified_order_target_ref=str(uuid4()),
            source_tool="get_shipment",
            source_tool_call_id=uuid4(),
            source_resource_ref="private-shipment-O-1001",
            source_version=(
                "mock-shipment-source-version.p0.v1:sha256:" + "c" * 64
            ),
            normalized_type="SHIPMENT_SUMMARY",
            normalized_value=ShipmentSummaryProjection(
                shipment_status=ShipmentStatus.IN_TRANSIT,
                latest_event_code=ShipmentEventCode.IN_TRANSIT,
                latest_event_at=observed_at,
                promised_delivery_at=NOW + SHIPMENT_FRESHNESS_TTL * 100,
            ),
            observed_at=observed_at,
            recorded_at=observed_at,
            valid_until=observed_at + SHIPMENT_FRESHNESS_TTL,
            raw_result_ref=str(uuid4()),
        )
        shipment_records = (shipment,)
        unit = unit.model_copy(
            update={"observation_refs": (shipment.observation_id,)}
        )
    runtime.current_session = Cycle2CurrentSessionTaskClosure(
        owner_scope=initial.owner_scope,
        session_ref_hash=_context().session_ref_hash,
        conversation_record=initial.expected_conversation_record,
        current_conversation_task_link_record=(
            initial.conversation_task_link_record
        ),
        current_task_record=graph.task,
        current_request_unit_record=unit,
        current_input_binding_records=(graph.input_binding,),
        current_shipment_observation_records=shipment_records,
        trusted_now=NOW,
    )
    routed: list[str] = []

    async def capture_order(**_kwargs: object) -> AgentRunResult:
        routed.append("get_order")
        return sentinel

    async def capture_shipment(**_kwargs: object) -> AgentRunResult:
        routed.append("get_shipment")
        return sentinel

    handler._get_order = capture_order  # type: ignore[method-assign]
    handler._get_shipment = capture_shipment  # type: ignore[method-assign]

    outbound = asyncio.run(
        handler.handle(
            AgentRunCommand(
                customer_context=_context(),
                message="订单 O-1001 状态怎么样？",
            )
        )
    )

    assert outbound is sentinel
    assert routed == ["get_shipment" if has_current_shipment else "get_order"]
    assert len(runtime.binding_commands) == 1
    assert runtime.binding_commands[0].new_input_binding_record.name == "order_id"


def test_cycle2_terminal_control_and_actual_observation_follow_durable_evidence() -> None:
    runtime = _Cycle2RuntimeHarness()
    provider = _Cycle2ProviderHarness()
    observer = _Cycle2OutcomeCapture(runtime)
    handler = _cycle2_handler(runtime, provider, observer=observer)
    _, captured = _capture_cycle2_initial_turn(handler)

    outbound = asyncio.run(
        handler._finalize_mapping(
            turn=captured["turn"],
            step=handler._step_for_signal(
                run_id=captured["turn"].running_run.run_id,
                signal=Cycle2MapperSignal.SEARCH_NO_MATCH,
            ),
            task=captured["task"],
            request_unit=captured["request_unit"],
        )
    )

    assert outbound.outcome is AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
    assert provider.control_purposes == [
        Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE
    ]
    assert len(runtime.finalize_commands) == 1
    assert len(observer.observations) == 1
    observation = observer.observations[0]
    assert observation.cycle2_signal is Cycle2MapperSignal.SEARCH_NO_MATCH
    assert observation.mapper_row_id == "RM-05"
    assert observation.response_policy is ResponsePolicy.SAFE_NOT_FOUND_FIXED


def test_cycle2_two_control_path_consumes_get_shipment_then_assessment() -> None:
    runtime = _Cycle2RuntimeHarness()
    provider = _StrictCycle2ControlProvider(
        (
            Cycle2ControlPurpose.PROPOSE_GET_SHIPMENT,
            Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT,
        )
    )
    handler = _cycle2_handler(runtime, provider)
    sentinel, captured = _capture_cycle2_initial_turn(handler)
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    target_ref = uuid4()
    observation_ref = uuid4()
    unit_with_target = unit.model_copy(
        update={"observation_refs": (observation_ref,)}
    )
    target = Cycle2VerifiedOrderTargetFacts(
        verified_target_ref=target_ref,
        private_owner_scope_ref="customer-A",
        owner_customer_id="customer-A",
        task_id=task.task_id,
        request_unit_id=unit.request_unit_id,
        task_state_version=task.state_version,
        order_id="O-1001",
        source_observation_ref=observation_ref,
        source_observation_version="order-observation-v1",
        input_binding_refs=(binding.binding_id,),
    )
    closure = InitialToolCallV2ReadClosure(
        owner_scope=captured["turn"].owner_scope,
        current_task_record=task,
        current_request_unit_record=unit_with_target,
        current_input_binding_records=(binding,),
        current_verified_order_targets=(target,),
        current_target_observations=(
            Cycle2TargetObservationFacts(
                observation_ref=observation_ref,
                observation_version="order-observation-v1",
                private_owner_scope_ref="customer-A",
                owner_customer_id="customer-A",
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                task_state_version=task.state_version,
                verified_target_ref=target_ref,
                input_binding_refs=(binding.binding_id,),
            ),
        ),
        trusted_read_at=NOW,
    )

    move = asyncio.run(
        handler._materialize_tool_control(
            turn=captured["turn"],
            purpose=Cycle2ControlPurpose.PROPOSE_GET_SHIPMENT,
            closure=closure,
        )
    )
    assert move.requested_tool_name == "get_shipment"
    assert move.arguments == {"order_id": "O-1001"}

    async def stop_after_control(**kwargs: object) -> AgentRunResult:
        return kwargs["result"]  # type: ignore[return-value]

    handler._finalize = stop_after_control  # type: ignore[method-assign]
    asyncio.run(
        handler._finalize_mapping(
            turn=captured["turn"],
            step=handler._steps._outbound_step(
                run_id=captured["turn"].running_run.run_id,
                signal=Cycle2MapperSignal.SHIPMENT_ASSESSMENT_READY,
                rendered_message="物流状态已按当前 Observation 评估。",
            ),
            task=task,
            request_unit=unit,
        )
    )
    provider.assert_exhausted()
    assert provider.control_purposes == [
        Cycle2ControlPurpose.PROPOSE_GET_SHIPMENT,
        Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT,
    ]


@pytest.mark.parametrize("origin", ["UNIQUE", "ORDINAL"])
def test_cycle2_unique_and_ordinal_get_order_control_is_consumed_once(
    origin: str,
) -> None:
    runtime = _Cycle2RuntimeHarness()
    provider = _StrictCycle2ControlProvider(
        (Cycle2ControlPurpose.PROPOSE_GET_ORDER,)
    )
    handler = _cycle2_handler(runtime, provider)
    _, captured = _capture_cycle2_initial_turn(handler)
    task = captured["task"]
    unit = captured["request_unit"]
    binding = captured["input_bindings"][0]
    if origin == "ORDINAL":
        binding = binding.model_copy(
            update={"name": "candidate_ordinal", "normalized_value": 2}
        )
    target_ref = uuid4()
    observation_ref = uuid4()
    unit = unit.model_copy(
        update={
            "input_binding_refs": (binding.binding_id,),
            "observation_refs": (observation_ref,),
        }
    )
    closure = InitialToolCallV2ReadClosure(
        owner_scope=captured["turn"].owner_scope,
        current_task_record=task,
        current_request_unit_record=unit,
        current_input_binding_records=(binding,),
        current_verified_order_targets=(
            Cycle2VerifiedOrderTargetFacts(
                verified_target_ref=target_ref,
                private_owner_scope_ref="customer-A",
                owner_customer_id="customer-A",
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                task_state_version=task.state_version,
                order_id="O-1001",
                source_observation_ref=observation_ref,
                source_observation_version="order-observation-v1",
                input_binding_refs=(binding.binding_id,),
            ),
        ),
        current_target_observations=(
            Cycle2TargetObservationFacts(
                observation_ref=observation_ref,
                observation_version="order-observation-v1",
                private_owner_scope_ref="customer-A",
                owner_customer_id="customer-A",
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                task_state_version=task.state_version,
                verified_target_ref=target_ref,
                input_binding_refs=(binding.binding_id,),
            ),
        ),
        trusted_read_at=NOW,
    )

    move = asyncio.run(
        handler._materialize_tool_control(
            turn=captured["turn"],
            purpose=Cycle2ControlPurpose.PROPOSE_GET_ORDER,
            closure=closure,
        )
    )

    provider.assert_exhausted()
    assert provider.control_purposes == [
        Cycle2ControlPurpose.PROPOSE_GET_ORDER
    ]
    assert move.requested_tool_name == "get_order"
    assert move.arguments == {"order_id": "O-1001"}


@pytest.mark.parametrize(
    "mode",
    ["MISSING", "WRONG_PURPOSE", "WRONG_CANDIDATE", "DUPLICATE"],
)
def test_cycle2_control_cursor_fails_closed_for_negative_shapes(mode: str) -> None:
    if mode == "MISSING":
        expected: tuple[Cycle2ControlPurpose, ...] = ()
    elif mode == "WRONG_PURPOSE":
        expected = (Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION,)
    else:
        expected = (Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,)
    provider = _StrictCycle2ControlProvider(
        expected,
        wrong_candidate=mode == "WRONG_CANDIDATE",
    )
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, provider)
    _, captured = _capture_cycle2_initial_turn(handler)

    if mode == "DUPLICATE":
        asyncio.run(
            handler._propose_cycle2_control(
                turn=captured["turn"],
                purpose=Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
            )
        )
    with pytest.raises(agent_run_service_module._Cycle2ControlProtocolError):
        asyncio.run(
            handler._propose_cycle2_control(
                turn=captured["turn"],
                purpose=Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
            )
        )


def test_cycle2_control_cursor_rejects_unconsumed_extra_step() -> None:
    provider = _StrictCycle2ControlProvider(
        (
            Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
            Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION,
        )
    )
    handler = _cycle2_handler(_Cycle2RuntimeHarness(), provider)
    _, captured = _capture_cycle2_initial_turn(handler)
    asyncio.run(
        handler._propose_cycle2_control(
            turn=captured["turn"],
            purpose=Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
        )
    )
    with pytest.raises(ProviderProtocolError):
        provider.assert_exhausted()


def test_cycle2_imported_observation_is_emitted_only_after_durable_evidence() -> None:
    runtime = _Cycle2RuntimeHarness()
    observer = _Cycle2OutcomeCapture(runtime)
    handler = _cycle2_handler(
        runtime,
        _Cycle2ProviderHarness(),
        observer=observer,
    )
    _, captured = _capture_cycle2_initial_turn(handler)
    result = AgentRunResult(
        run_id=captured["turn"].running_run.run_id,
        outcome=AgentOutcome.COMPLETED,
        message="订单状态已安全汇总。",
    )

    outbound = asyncio.run(
        handler._finalize_imported(
            turn=captured["turn"],
            result=result,
            stop_reason=StopReasonV2.GOAL_COMPLETED,
            task=captured["task"],
            request_unit=captured["request_unit"],
            reference=ImportedMapperReference.ORDER_SUCCESS,
            response_policy=ResponsePolicy.DETERMINISTIC_ORDER_SUMMARY_V1,
            consume_control=False,
        )
    )

    assert outbound is result
    assert len(runtime.finalize_commands) == 1
    assert len(observer.observations) == 1
    observation = observer.observations[0]
    assert observation.mapping_source_kind is Cycle2MappingSourceKind.IMPORTED_PHASE1
    assert observation.imported_reference is ImportedMapperReference.ORDER_SUCCESS
    assert observation.cycle2_signal is None
    assert observation.mapper_disposition is None


def test_cycle2_observer_failure_propagates_after_durable_finalize() -> None:
    class _FailingObserver:
        def observe_cycle2_execution_outcome(
            self,
            _observation: Cycle2ExecutionOutcomeObservationV1,
        ) -> None:
            raise RuntimeError("offline capture failed")

    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(
        runtime,
        _Cycle2ProviderHarness(),
        observer=_FailingObserver(),
    )
    _, captured = _capture_cycle2_initial_turn(handler)

    with pytest.raises(RuntimeError, match="offline capture failed"):
        asyncio.run(
            handler._finalize_mapping(
                turn=captured["turn"],
                step=handler._step_for_signal(
                    run_id=captured["turn"].running_run.run_id,
                    signal=Cycle2MapperSignal.SEARCH_NO_MATCH,
                ),
                task=captured["task"],
                request_unit=captured["request_unit"],
            )
        )
    assert len(runtime.finalize_commands) == 1


def test_cycle2_default_noop_and_no_result_recovery_have_no_capture_failure() -> None:
    runtime = _Cycle2RuntimeHarness()
    handler = _cycle2_handler(runtime, _Cycle2ProviderHarness())
    _, captured = _capture_cycle2_initial_turn(handler)
    outbound = asyncio.run(
        handler._finalize_mapping(
            turn=captured["turn"],
            step=handler._step_for_signal(
                run_id=captured["turn"].running_run.run_id,
                signal=Cycle2MapperSignal.SEARCH_NO_MATCH,
            ),
            task=captured["task"],
            request_unit=captured["request_unit"],
        )
    )
    assert outbound.outcome is AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
    obsolete_source = inspect.getsource(
        Cycle2AgentRunService.finalize_obsolete_run
    )
    assert "observe_cycle2_execution_outcome" not in obsolete_source
    assert "propose_cycle2_control" not in obsolete_source


def test_cycle2_mapper_builds_mutually_exclusive_actual_observations() -> None:
    mapper = RunResultMapper()
    run_id = uuid4()
    delta = mapper.observe_cycle2(
        run_id=run_id,
        signal=Cycle2MapperSignal.SEARCH_NO_MATCH,
        observed_outcome=AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        stop_reason=StopReasonV2.NOT_FOUND_OR_NOT_ACCESSIBLE,
        response_policy=ResponsePolicy.SAFE_NOT_FOUND_FIXED,
        agent_result_emitted=True,
    )
    imported = mapper.observe_imported(
        run_id=run_id,
        reference=ImportedMapperReference.ORDER_SUCCESS,
        observed_outcome=AgentOutcome.COMPLETED,
        stop_reason=StopReasonV2.GOAL_COMPLETED,
        response_policy=ResponsePolicy.DETERMINISTIC_ORDER_SUMMARY_V1,
        agent_result_emitted=True,
    )

    assert type(delta) is Cycle2ExecutionOutcomeObservationV1
    assert delta.mapping_source_kind is Cycle2MappingSourceKind.CYCLE2_DELTA
    assert delta.imported_reference is None
    assert delta.cycle2_signal is Cycle2MapperSignal.SEARCH_NO_MATCH
    assert imported.mapping_source_kind is Cycle2MappingSourceKind.IMPORTED_PHASE1
    assert imported.imported_reference is ImportedMapperReference.ORDER_SUCCESS
    assert imported.cycle2_signal is None
    assert imported.mapper_disposition is None


def test_cycle2_control_candidate_remains_argument_free_at_application_boundary() -> None:
    candidate = Cycle2ControlCandidate(
        kind=Cycle2ControlCandidateKind.CALL_TOOL,
        requested_tool_name="get_order",
    )
    assert candidate.model_dump() == {
        "kind": Cycle2ControlCandidateKind.CALL_TOOL,
        "requested_tool_name": "get_order",
    }
    assert set(Cycle2ControlPurpose) == {
        Cycle2ControlPurpose.PROPOSE_GET_ORDER,
        Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
        Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION,
        Cycle2ControlPurpose.PROPOSE_ORDER_SUMMARY,
        Cycle2ControlPurpose.PROPOSE_GET_SHIPMENT,
        Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT,
    }
