"""Application orchestration for the first deterministic E2E-01 thin slice."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mini_agent.application.deterministic_renderer import (
    DeterministicRenderer,
    RendererInvariantError,
)
from mini_agent.application.ports import (
    ConversationRecordPort,
    Cycle2ExecutionOutcomeObserver,
    Cycle2RuntimeRecordPort,
    Cycle2RequestUnderstandingProvider,
    ModelProviderV2,
    ModelVisibleToolsetArtifactPort,
    NoOpCycle2ExecutionOutcomeObserver,
    RuntimeRecordPort,
)
from mini_agent.application.read_tool_executor import (
    Cycle2ReadToolExecutor,
    Cycle2ReadToolExecution,
    ReadToolExecution,
    ReadToolExecutor,
    _is_canonical_get_order_source_version,
)
from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    ApplyContinuationInputBindingV2Command,
    ApplyContinuationTaskDeltaV3Command,
    ApplyTaskTransitionCommand,
    ApplyOrderCandidateSelectionV2Command,
    ApplyOrderCandidateSelectionV3Command,
    ApplyOrderSearchOutcomeV2Command,
    ConditionalWriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    ContinuationInputBindingReadClosure,
    CreateInitialTaskGraphV2Command,
    CreateInitialTaskGraphV3Command,
    CreateCycle2InitialTaskGraphCommand,
    CreateCycle2InitialTaskGraphV3Command,
    CreateCycle2RunRootCommand,
    CreateToolCallV2Command,
    CreateRequestUnitCommand,
    CreateRunCommand,
    CreateRunTaskLinkCommand,
    CreateTaskCommand,
    FinalizeRunCommand,
    FinalizeCycle2RunCommand,
    FinalizeStateInvalidatedToolRecoveryV2Command,
    FinalizeSupersededRunV2Command,
    InitialToolCallV2ReadClosure,
    InitialAcceptedTaskGraphV3CommandItem,
    InsertOnlyWriteResult,
    MessageDirection,
    MessageRecord,
    OrderCandidateSelectionReadClosure,
    OrderSearchCurrentReadClosure,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    SaveInputBindingCommand,
    SaveOrderObservationV2Command,
    SaveRequestUnderstandingV2AcceptedCommand,
    SaveRejectedContinuationUnderstandingV3Command,
    SaveRequestUnderstandingV3NoTaskCommand,
    SaveShipmentAssessmentV2Command,
    SaveShipmentObservationV2Command,
    StartCycle2RunCommand,
    ShipmentAssessmentReadClosure,
    TransitionRunCommand,
    TrustedOwnerScope,
    Cycle2WriteResult,
    Cycle2ControlPurpose,
    Cycle2CurrentSessionTaskClosure,
    IssuedSelectedTargetRef,
    build_order_candidate_selection_v2_command,
    build_order_candidate_selection_v3_command,
)
from mini_agent.application.run_result_mapper import (
    Cycle2ExecutionOutcomeObservationV1,
    Cycle2MapperSignal,
    Cycle2ResultMapping,
    ImportedMapperReference,
    MapperDisposition,
    ResponsePolicy,
    RunResultMapper,
)
from mini_agent.core.control_gateway import (
    Cycle2AcceptedBindingFacts,
    Cycle2GatewayBudgetFacts,
    Cycle2GatewayCandidate,
    Cycle2GatewayLoadedClosure,
    Cycle2GatewayProgressSnapshot,
    Cycle2TargetObservationFacts,
    Cycle2ToolProgressFact,
    Cycle2VerifiedOrderTargetFacts,
    build_cycle2_authorized_tool_command,
    evaluate_cycle2_control_gateway,
    evaluate_control_gateway,
    resolve_validated_get_order_registration,
)
from mini_agent.core.common import thaw_json_value
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
    project_search_orders_observation_safe,
)
from mini_agent.core.order import GetOrderOutcome, GetOrderResult
from mini_agent.core.order_search import SearchOrdersResult
from mini_agent.core.order_search import SearchOrdersOutcome
from mini_agent.core.presentation import (
    CandidatePresentationPlan,
    ClosingVariant,
    OpeningVariant,
    PresentationInput,
    PresentationField,
    PresentationPlan,
    PresentationTone,
    PresentationPurpose,
    ShipmentPresentationPlan,
)
from mini_agent.core.presentation_policy import (
    PresentationPolicyError,
    validate_presentation_plan,
)
from mini_agent.core.request_processing import (
    Cycle2ContinuationBindingDecision,
    Cycle2AcceptedClaimRejectedSelection,
    Cycle2ContinuationDecisionV3,
    Cycle2ContinuationIdentityAllocationV3,
    Cycle2InitialRequestDecisionV2,
    Cycle2InitialRequestDecisionV3,
    Cycle2OrdinalClaimPreparation,
    Cycle2OrdinalSelectionRejectionReason,
    InitialTaskIdentityAllocationV2,
    InitialTaskIdentityAllocationV3,
    InitialRequestNoTaskDecisionV2,
    InitialRequestRoutableTaskGraphDecisionV2,
    InitialRequestUnroutedTaskGraphsDecisionV2,
    RequestProcessingError,
    RequestUnderstandingV2Error,
    RejectedCycle2ContinuationDecisionV3,
    RequestUnderstandingClosureV3,
    build_request_understanding_closure_v3,
    build_cycle2_unique_auto_target_record,
    materialize_cycle2_control_next_move,
    prepare_cycle2_ordinal_claim,
    prepare_cycle2_ordinal_selection,
    reject_cycle2_ordinal_selection,
    reduce_cycle2_continuation_candidate,
    reduce_cycle2_continuation_task_delta,
    revalidate_next_move_v2,
    route_cycle2_continuation_next_move,
    route_cycle2_selected_next_move,
    route_cycle2_unique_next_move,
    route_cycle2_verified_target_next_move,
    validate_and_reduce_cycle2_initial_request_v2,
    validate_and_reduce_cycle2_initial_request_v3,
    validate_and_reduce_initial_request_v2,
)
from mini_agent.core.request_understanding import (
    Cycle2ControlCandidate,
    Cycle2ControlCandidateKind,
    Cycle2InputCandidate,
    Cycle2ContinuationRequestUnderstandingOutputV2,
    ModelVisibleTaskSummary,
    NextMove,
    NextMoveKind,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
)
from mini_agent.core.task_state import (
    ORDER_CANDIDATE_SET_TTL,
    AcceptedAddGoalTaskDeltaV3,
    InputBindingV2,
    OrderCandidateAutoTargetRecord,
    OrderCandidateSelectionRecord,
    OrderCandidateSelectionRequest,
    OrderCandidateSetRecord,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    RequestUnderstandingAggregateFailureCodeV2,
    RequestUnderstandingAtomicFailureCodeV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
    compute_order_candidate_set_version,
)
from mini_agent.core.shipment import (
    SHIPMENT_FRESHNESS_TTL,
    GetShipmentOutcome,
    GetShipmentResult,
    assess_shipment,
)
from mini_agent.core.tool_system import (
    AuthorizedToolCommand,
    AuthorizedToolCommandV2,
    GateDecision,
    GateDecisionV2,
    GateDecisionValue,
    RegistrySnapshot,
    ToolCallStatus,
    ToolResultOutcome,
    ToolResult,
    Cycle2ToolName,
    ToolCallRecordV2,
    ToolEffect,
    build_cycle2_registry_snapshot,
    validate_cycle2_registry_snapshot,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatusV2,
    AgentRunStatus,
    StopReason,
    StopReasonV2,
    TraceEvent,
    TraceEventV2,
    TraceEventType,
)

_CONVERSATION_SCHEMA_VERSION = "conversation_record.p0.v1"
_MESSAGE_SCHEMA_VERSION = "message_record.p0.v1"
_CONVERSATION_TASK_LINK_SCHEMA_VERSION = "conversation_task_link_record.p0.v1"
_RUN_TASK_LINK_SCHEMA_VERSION = "run_task_link_record.p0.v1"


class AgentRunExecutionError(RuntimeError):
    """Bounded integration/persistence conflict outside normal product paths."""

    __slots__ = ()


class AfterRevalidationHook(Protocol):
    """Runtime-local post-revalidation/pre-Gateway fault seam."""

    def __call__(
        self,
        run_id: UUID,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
    ) -> Awaitable[None] | None: ...


async def _noop_after_revalidation(
    run_id: UUID,
    task: TaskRecord,
    request_unit: RequestUnitRecord,
) -> None:
    del run_id, task, request_unit


def _project_run(
    record: AgentRunRecord,
    **updates: object,
) -> AgentRunRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in AgentRunRecord.model_fields
    }
    values.update(updates)
    return AgentRunRecord(**values)


def _project_task(
    record: TaskRecord,
    **updates: object,
) -> TaskRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in TaskRecord.model_fields
    }
    values.update(updates)
    return TaskRecord(**values)


def _project_request_unit(
    record: RequestUnitRecord,
    **updates: object,
) -> RequestUnitRecord:
    values = {
        field_name: getattr(record, field_name)
        for field_name in RequestUnitRecord.model_fields
    }
    values.update(updates)
    return RequestUnitRecord(**values)


def _build_generic_initial_v3_command(
    *,
    owner_scope: TrustedOwnerScope,
    conversation: ConversationRecord,
    messages: tuple[MessageRecord, ...],
    running_run: AgentRunRecord,
    closure: RequestUnderstandingClosureV3,
    accepted_task_graphs: tuple[
        InitialAcceptedTaskGraphV3CommandItem,
        ...,
    ] = (),
) -> SaveRequestUnderstandingV3NoTaskCommand | CreateInitialTaskGraphV3Command:
    """Choose one exact generic v3 atomic command without routing it."""

    if accepted_task_graphs:
        return CreateInitialTaskGraphV3Command(
            owner_scope=owner_scope,
            expected_conversation_record=conversation,
            expected_message_records=messages,
            expected_active_run_record=running_run,
            request_understanding=closure,
            accepted_task_graphs=accepted_task_graphs,
        )
    return SaveRequestUnderstandingV3NoTaskCommand(
        owner_scope=owner_scope,
        expected_conversation_record=conversation,
        expected_message_records=messages,
        expected_active_run_record=running_run,
        request_understanding=closure,
    )


def _reduce_and_build_generic_initial_v3_command(
    *,
    owner_scope: TrustedOwnerScope,
    conversation: ConversationRecord,
    messages: tuple[MessageRecord, ...],
    running_run: AgentRunRecord,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    customer_context: CustomerContext,
    request_understanding_record_id: UUID,
    candidate_identity_allocations: tuple[InitialTaskIdentityAllocationV2, ...],
    next_move_candidate_ref: UUID,
    now: datetime,
) -> tuple[
    SaveRequestUnderstandingV3NoTaskCommand | CreateInitialTaskGraphV3Command,
    InitialRequestNoTaskDecisionV2
    | InitialRequestRoutableTaskGraphDecisionV2
    | InitialRequestUnroutedTaskGraphsDecisionV2,
]:
    """Run the generic reducer once, then project its authority into v3."""

    decision = validate_and_reduce_initial_request_v2(
        request_input=request_input,
        output=output,
        authoritative_messages={
            message.message_id: message.content for message in messages
        },
        customer_context=customer_context,
        request_understanding_record_id=request_understanding_record_id,
        candidate_identity_allocations=candidate_identity_allocations,
        next_move_candidate_ref=next_move_candidate_ref,
        now=now,
    )
    if type(decision) is InitialRequestNoTaskDecisionV2:
        graphs = ()
    elif type(decision) is InitialRequestRoutableTaskGraphDecisionV2:
        graphs = (decision.task_graph,)
    elif type(decision) is InitialRequestUnroutedTaskGraphsDecisionV2:
        graphs = decision.task_graphs
    else:
        raise AgentRunExecutionError("generic v3 reduction result is unavailable")
    accepted_children = tuple(
        AcceptedAddGoalTaskDeltaV3(
            **{
                field_name: getattr(graph.accepted_delta, field_name)
                for field_name in AcceptedAddGoalTaskDeltaV3.model_fields
            }
        )
        for graph in graphs
    )
    v2_record = decision.closure.record
    closure = build_request_understanding_closure_v3(
        request_input=request_input,
        output=output,
        authoritative_messages={
            message.message_id: message.content for message in messages
        },
        request_understanding_record_id=request_understanding_record_id,
        candidate_validation=v2_record.candidate_validation,
        accepted_task_deltas=accepted_children,
        proposed_base_task_state_version=(
            v2_record.proposed_base_task_state_version
        ),
        validated_task_state_version=v2_record.validated_task_state_version,
        next_move_candidate_ref=v2_record.next_move_candidate_ref,
        now=now,
    )
    accepted_items = tuple(
        InitialAcceptedTaskGraphV3CommandItem(
            accepted_delta=child,
            initial_task=CreateTaskCommand(initial_record=graph.task),
            initial_request_unit=CreateRequestUnitCommand(
                initial_record=graph.request_unit
            ),
            input_bindings=(
                SaveInputBindingCommand(
                    record=graph.input_binding,
                    request_unit_id=graph.request_unit.request_unit_id,
                ),
            ),
            conversation_task_link=ConversationTaskLinkRecord(
                schema_version=_CONVERSATION_TASK_LINK_SCHEMA_VERSION,
                conversation_id=conversation.conversation_id,
                task_id=graph.task.task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=now,
            ),
            run_task_link=CreateRunTaskLinkCommand(
                active_record=RunTaskLinkRecord(
                    schema_version=_RUN_TASK_LINK_SCHEMA_VERSION,
                    run_id=running_run.run_id,
                    task_id=graph.task.task_id,
                    base_task_state_version=None,
                )
            ),
        )
        for graph, child in zip(graphs, accepted_children, strict=True)
    )
    return (
        _build_generic_initial_v3_command(
            owner_scope=owner_scope,
            conversation=conversation,
            messages=messages,
            running_run=running_run,
            closure=closure,
            accepted_task_graphs=accepted_items,
        ),
        decision,
    )


def _build_v3_effect_trace_records(
    *,
    closure: RequestUnderstandingClosureV3,
    input_bindings: tuple[InputBindingV2, ...],
    task: TaskRecord,
    request_unit: RequestUnitRecord,
    trace_event_ids: tuple[UUID, ...],
) -> tuple[TraceEventV2, ...]:
    """Project the exact accepted-effect Trace sequence from trusted IDs."""

    if len(closure.accepted_task_deltas) != 1:
        raise AgentRunExecutionError("v3 effect Trace requires one accepted child")
    expected_count = len(input_bindings) + 3
    if (
        len(trace_event_ids) != expected_count
        or len(trace_event_ids) != len(set(trace_event_ids))
    ):
        raise AgentRunExecutionError("v3 effect Trace identity allocation mismatch")
    child = closure.accepted_task_deltas[0]
    event_types = (
        TraceEventType.TASK_DELTA_VALIDATED,
        TraceEventType.TASK_DELTA_ACCEPTED,
        *(
            TraceEventType.INPUT_BINDING_RECORDED
            for _binding in input_bindings
        ),
        TraceEventType.TASK_STATE_CHANGED,
    )
    input_binding_refs: tuple[UUID | None, ...] = (
        None,
        None,
        *(binding.binding_id for binding in input_bindings),
        None,
    )
    return tuple(
        TraceEventV2(
            trace_event_id=trace_event_id,
            event_type=event_type,
            occurred_at=closure.record.created_at,
            run_id=closure.record.run_id,
            message_ref=closure.record.message_ref,
            accepted_delta_ref=child.accepted_delta_id,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            input_binding_ref=input_binding_ref,
        )
        for trace_event_id, event_type, input_binding_ref in zip(
            trace_event_ids,
            event_types,
            input_binding_refs,
            strict=True,
        )
    )


def _project_continuation_binding_refs_v3(
    *,
    current_unit: RequestUnitRecord,
    current_bindings: tuple[InputBindingV2, ...],
    new_bindings: tuple[InputBindingV2, ...],
) -> tuple[UUID, ...]:
    refs = list(current_unit.input_binding_refs)
    current_by_name = {binding.name: binding for binding in current_bindings}
    for binding in new_bindings:
        previous = current_by_name.get(binding.name)
        if previous is None:
            refs.append(binding.binding_id)
        else:
            if binding.supersedes != previous.binding_id:
                raise AgentRunExecutionError("v3 continuation supersession mismatch")
            try:
                index = refs.index(previous.binding_id)
            except ValueError:
                raise AgentRunExecutionError(
                    "v3 continuation superseded ref is not current"
                ) from None
            refs[index] = binding.binding_id
        current_by_name[binding.name] = binding
    return tuple(refs)


def _build_continuation_v3_command(
    *,
    loaded_closure: ContinuationInputBindingReadClosure,
    decision: Cycle2ContinuationDecisionV3,
    trace_event_ids: tuple[UUID, ...],
    rejected_ordinal_selection: (
        Cycle2AcceptedClaimRejectedSelection | None
    ) = None,
) -> ApplyContinuationTaskDeltaV3Command:
    child = decision.closure.accepted_task_deltas[0]
    next_task = _project_task(
        loaded_closure.current_task_record,
        state_version=child.result_task_state_version,
        updated_at=decision.closure.record.created_at,
    )
    next_unit = _project_request_unit(
        loaded_closure.current_request_unit_record,
        input_binding_refs=_project_continuation_binding_refs_v3(
            current_unit=loaded_closure.current_request_unit_record,
            current_bindings=loaded_closure.current_input_binding_records,
            new_bindings=decision.input_bindings,
        ),
        state_version=child.result_task_state_version,
        updated_at=decision.closure.record.created_at,
    )
    traces = _build_v3_effect_trace_records(
        closure=decision.closure,
        input_bindings=decision.input_bindings,
        task=next_task,
        request_unit=next_unit,
        trace_event_ids=trace_event_ids,
    )
    return ApplyContinuationTaskDeltaV3Command(
        loaded_closure=loaded_closure,
        decision=decision,
        next_task_record=next_task,
        next_request_unit_record=next_unit,
        effect_trace_records=traces,
        rejected_ordinal_selection=rejected_ordinal_selection,
    )


def _routing_trigger_binding_v3(
    decision: Cycle2ContinuationDecisionV3,
) -> InputBindingV2:
    matching = tuple(
        binding
        for binding in decision.input_bindings
        if binding.binding_id == decision.routing_trigger_binding_ref
    )
    if len(matching) != 1:
        raise AgentRunExecutionError("v3 continuation trigger is unavailable")
    return matching[0]


def _build_order_selection_v3_staging_command(
    *,
    loaded_closure: OrderCandidateSelectionReadClosure,
    decision: Cycle2ContinuationDecisionV3,
    issued_selected_target: IssuedSelectedTargetRef,
    selection_id: UUID,
    trace_event_ids: tuple[UUID, ...],
) -> ApplyOrderCandidateSelectionV3Command:
    """Project one reducer-owned ordinal decision into its exact CAS command."""

    ordinal_binding = _routing_trigger_binding_v3(decision)
    if (
        ordinal_binding.name != "candidate_ordinal"
        or len(decision.input_bindings) != 1
    ):
        raise AgentRunExecutionError("v3 selection requires one ordinal binding")
    selected_entries = tuple(
        entry
        for entry in loaded_closure.current_candidate_set_record.ordered_candidates
        if entry.ordinal == ordinal_binding.normalized_value
    )
    if len(selected_entries) != 1:
        raise AgentRunExecutionError("v3 selected CandidateSet entry unavailable")
    selected = selected_entries[0]
    current_task = loaded_closure.current_task_record
    current_unit = loaded_closure.current_request_unit_record
    selected_at = decision.closure.record.created_at
    selection = OrderCandidateSelectionRecord(
        selection_id=selection_id,
        private_owner_scope_ref=loaded_closure.owner_scope.customer_id,
        conversation_id=loaded_closure.conversation_id,
        task_id=current_task.task_id,
        request_unit_id=current_unit.request_unit_id,
        source_message_ref=(
            loaded_closure.saved_selection_message_record.message_id
        ),
        ordinal_input_binding_ref=ordinal_binding.binding_id,
        candidate_set_ref=(
            loaded_closure.current_candidate_set_record.candidate_set_id
        ),
        candidate_set_version=(
            loaded_closure.current_candidate_set_record.candidate_set_version
        ),
        search_observation_ref=(
            loaded_closure.search_observation_record.observation_id
        ),
        search_observation_record_schema_version=(
            loaded_closure.search_observation_record.record_schema_version
        ),
        observation_candidate_ref=selected.observation_candidate_ref,
        candidate_source_version=selected.candidate_source_version,
        owner_scoped_order_target_ref=(
            loaded_closure.resolved_owner_scoped_order_target_ref
        ),
        selected_target_ref=str(issued_selected_target.selected_target_ref),
        base_task_state_version=current_task.state_version,
        result_task_state_version=current_task.state_version + 1,
        selected_at=selected_at,
    )
    next_task = _project_task(
        current_task,
        status=TaskStatus.ACTIVE,
        state_version=current_task.state_version + 1,
        updated_at=selected_at,
    )
    next_unit = _project_request_unit(
        current_unit,
        input_binding_refs=(
            *current_unit.input_binding_refs,
            ordinal_binding.binding_id,
        ),
        open_questions=(),
        status=TaskStatus.ACTIVE,
        state_version=current_unit.state_version + 1,
        updated_at=selected_at,
    )
    traces = _build_v3_effect_trace_records(
        closure=decision.closure,
        input_bindings=(ordinal_binding,),
        task=next_task,
        request_unit=next_unit,
        trace_event_ids=trace_event_ids,
    )
    return build_order_candidate_selection_v3_command(
        loaded_closure=loaded_closure,
        ordinal_input_binding_record=ordinal_binding,
        issued_selected_target=issued_selected_target,
        next_task_record=next_task,
        next_request_unit_record=next_unit,
        selection_record=selection,
        closed_pending_candidate_set_ref=(
            loaded_closure.pending_candidate_set_ref
        ),
        decision=decision,
        effect_trace_records=traces,
    )


def _project_cycle2_run(
    record: AgentRunRecordV2,
    **updates: object,
) -> AgentRunRecordV2:
    values = {
        field_name: getattr(record, field_name)
        for field_name in AgentRunRecordV2.model_fields
    }
    values.update(updates)
    return AgentRunRecordV2(**values)


def _cycle2_order_presentation_plan() -> PresentationPlan:
    return PresentationPlan(
        template_id="ORDER_STATUS_SUMMARY_V1",
        tone=PresentationTone.NEUTRAL,
        opening_variant=OpeningVariant.DIRECT,
        field_order=tuple(PresentationField),
        closing_variant=ClosingVariant.NONE,
    )


def _cycle2_candidate_presentation_plan() -> CandidatePresentationPlan:
    return CandidatePresentationPlan(
        tone=PresentationTone.NEUTRAL,
        opening_variant=OpeningVariant.DIRECT,
        closing_variant=ClosingVariant.NONE,
    )


def _cycle2_shipment_presentation_plan() -> ShipmentPresentationPlan:
    return ShipmentPresentationPlan(
        tone=PresentationTone.NEUTRAL,
        opening_variant=OpeningVariant.DIRECT,
        closing_variant=ClosingVariant.NONE,
    )


class _RunFailureState:
    """Local cursor for exceptional closure and the terminal commit point."""

    __slots__ = (
        "active_link",
        "committed_result",
        "owner_scope",
        "result_task",
        "running_run",
    )

    def __init__(self) -> None:
        self.running_run: AgentRunRecord | None = None
        self.active_link: RunTaskLinkRecord | None = None
        self.result_task: TaskRecord | None = None
        self.owner_scope: TrustedOwnerScope | None = None
        self.committed_result: AgentRunResult | None = None


class AgentRunService:
    """Coordinate one bounded controlled-ReAct read trajectory."""

    def __init__(
        self,
        *,
        model_provider: ModelProviderV2,
        registry_snapshot: RegistrySnapshot,
        toolset_artifact_port: ModelVisibleToolsetArtifactPort,
        conversation_record_port: ConversationRecordPort,
        runtime_record_port: RuntimeRecordPort,
        read_tool_executor: ReadToolExecutor,
        deterministic_renderer: DeterministicRenderer,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
        provider_lane: str,
        redaction_policy_version: str,
        run_time_budget_ms: int = 30_000,
        after_revalidation_hook: AfterRevalidationHook | None = None,
    ) -> None:
        if type(run_time_budget_ms) is not int or run_time_budget_ms <= 0:
            raise ValueError("run_time_budget_ms must be a positive integer")
        self._model_provider = model_provider
        self._registry_snapshot = registry_snapshot
        self._toolset_artifact_port = toolset_artifact_port
        self._conversation_record_port = conversation_record_port
        self._runtime_record_port = runtime_record_port
        self._read_tool_executor = read_tool_executor
        self._deterministic_renderer = deterministic_renderer
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._provider_lane = provider_lane
        self._redaction_policy_version = redaction_policy_version
        self._run_time_budget_ms = run_time_budget_ms
        self._after_revalidation_hook = (
            after_revalidation_hook or _noop_after_revalidation
        )

    @property
    def after_revalidation_hook(self) -> AfterRevalidationHook:
        return self._after_revalidation_hook

    async def _append_trace(
        self,
        *,
        event_type: TraceEventType,
        run_id: UUID,
        occurred_at: datetime | None = None,
        **fields: object,
    ) -> TraceEvent:
        event = TraceEvent(
            trace_event_id=self._uuid_factory(),
            event_type=event_type,
            occurred_at=occurred_at or self._clock(),
            run_id=run_id,
            **fields,
        )
        await self._runtime_record_port.append_trace_event(event)
        return event

    async def _save_manifest(
        self,
        *,
        run_id: UUID,
        model_call_id: UUID,
        model_call_purpose: str,
        message_id: UUID,
        task: TaskRecord | None = None,
        observation_ref: VersionedRecordRef | None = None,
    ) -> ContextManifest:
        manifest = ContextManifest(
            context_manifest_id=self._uuid_factory(),
            run_id=run_id,
            model_call_id=model_call_id,
            tool_registry_version=(
                self._registry_snapshot.tool_registry_version
            ),
            model_visible_toolset_hash=(
                self._registry_snapshot.model_visible_toolset_hash
            ),
            selected_message_refs=(message_id,),
            task_state_ref_and_version=(
                TaskStateRefAndVersion(
                    task_id=task.task_id,
                    state_version=task.state_version,
                )
                if task is not None
                else None
            ),
            observation_refs_and_versions=(
                (observation_ref,) if observation_ref is not None else ()
            ),
            redaction_policy_version=self._redaction_policy_version,
            token_counts=TokenCounts(
                input_tokens=None,
                output_tokens=None,
            ),
            assembled_at=self._clock(),
        )
        await self._runtime_record_port.save_context_manifest(manifest)
        await self._append_trace(
            event_type=TraceEventType.CONTEXT_MANIFEST_RECORDED,
            run_id=run_id,
            model_call_id=model_call_id,
            model_call_purpose=model_call_purpose,
            context_manifest_id=manifest.context_manifest_id,
            tool_registry_version=manifest.tool_registry_version,
            model_visible_toolset_hash=manifest.model_visible_toolset_hash,
        )
        return manifest

    async def _stage_generic_initial_turn_v3(
        self,
        *,
        command: AgentRunCommand,
        owner_scope: TrustedOwnerScope,
        conversation: ConversationRecord,
        messages: tuple[MessageRecord, ...],
        running_run: AgentRunRecord,
        request_input: RequestUnderstandingInput,
    ) -> tuple[
        Cycle2WriteResult,
        InitialRequestNoTaskDecisionV2
        | InitialRequestRoutableTaskGraphDecisionV2
        | InitialRequestUnroutedTaskGraphsDecisionV2
        | None,
    ]:
        """Persist generic v3 staging; only APPLIED exposes its Core result."""

        output = await self._model_provider.propose_next_move(request_input)
        now = self._clock()
        request_understanding_record_id = self._uuid_factory()
        allocations = tuple(
            InitialTaskIdentityAllocationV2(
                candidate_ref=candidate.candidate_id,
                accepted_delta_id=self._uuid_factory(),
                task_id=self._uuid_factory(),
                request_unit_id=self._uuid_factory(),
                binding_id=self._uuid_factory(),
            )
            for candidate in output.task_delta_candidates
        )
        next_move_candidate_ref = self._uuid_factory()
        staged, decision = _reduce_and_build_generic_initial_v3_command(
            owner_scope=owner_scope,
            conversation=conversation,
            messages=messages,
            running_run=running_run,
            request_input=request_input,
            output=output,
            customer_context=command.customer_context,
            request_understanding_record_id=(
                request_understanding_record_id
            ),
            candidate_identity_allocations=allocations,
            next_move_candidate_ref=next_move_candidate_ref,
            now=now,
        )
        if type(staged) is SaveRequestUnderstandingV3NoTaskCommand:
            result = await (
                self._runtime_record_port
                .save_request_understanding_v3_no_task_if_current(staged)
            )
        elif type(staged) is CreateInitialTaskGraphV3Command:
            result = await (
                self._runtime_record_port
                .create_initial_task_graph_v3_if_current(staged)
            )
        else:
            raise AgentRunExecutionError("generic v3 staging command unavailable")
        return result, decision if result is Cycle2WriteResult.APPLIED else None

    async def handle(self, command: AgentRunCommand) -> AgentRunResult:
        failure_state = _RunFailureState()
        try:
            return await self._handle(command, failure_state=failure_state)
        except asyncio.CancelledError as error:
            if failure_state.committed_result is None:
                await self._finalize_failed_run_after_error(
                    failure_state=failure_state,
                    original_error=error,
                )
            raise
        except Exception as error:
            if failure_state.committed_result is not None:
                # APPLIED already committed the complete terminal aggregate.
                return failure_state.committed_result
            await self._finalize_failed_run_after_error(
                failure_state=failure_state,
                original_error=error,
            )
            raise

    async def _handle(
        self,
        command: AgentRunCommand,
        *,
        failure_state: _RunFailureState,
    ) -> AgentRunResult:
        if type(command) is not AgentRunCommand:
            raise AgentRunExecutionError("canonical AgentRunCommand required")
        owner_scope = TrustedOwnerScope.from_customer_context(
            command.customer_context
        )
        failure_state.owner_scope = owner_scope

        artifact = self._registry_snapshot.artifact()
        await self._toolset_artifact_port.put_toolset_artifact(artifact)
        resolved_artifact = (
            await self._toolset_artifact_port.get_toolset_artifact(
                artifact.model_visible_toolset_hash
            )
        )
        if resolved_artifact != artifact:
            raise AgentRunExecutionError("Toolset Artifact is not resolvable")

        now = self._clock()
        conversation = ConversationRecord(
            schema_version=_CONVERSATION_SCHEMA_VERSION,
            conversation_id=self._uuid_factory(),
            owner_customer_id=owner_scope.customer_id,
            created_at=now,
        )
        user_message = MessageRecord(
            schema_version=_MESSAGE_SCHEMA_VERSION,
            message_id=self._uuid_factory(),
            conversation_id=conversation.conversation_id,
            direction=MessageDirection.USER,
            content=command.message,
            received_at=now,
        )
        await self._conversation_record_port.save_conversation(conversation)
        await self._conversation_record_port.append_message(user_message)
        authoritative_messages = (
            await self._conversation_record_port.list_messages_for_owner(
                owner_scope=owner_scope,
                conversation_id=conversation.conversation_id,
                limit=8,
            )
        )
        if (
            len(authoritative_messages) != 1
            or type(authoritative_messages[0]) is not MessageRecord
            or authoritative_messages[0] != user_message
            or authoritative_messages[0].direction
            is not MessageDirection.USER
        ):
            raise AgentRunExecutionError(
                "authoritative current Message unavailable"
            )
        user_message = authoritative_messages[0]

        created_run = AgentRunRecord(
            run_id=self._uuid_factory(),
            conversation_id=conversation.conversation_id,
            status=AgentRunStatus.CREATED,
            provider_lane=self._provider_lane,
            started_at=now,
        )
        insert_result = await self._runtime_record_port.insert_run(
            CreateRunCommand(created_record=created_run)
        )
        if insert_result is not InsertOnlyWriteResult.INSERTED:
            raise AgentRunExecutionError("Run insert conflict")
        running_run = _project_run(created_run, status=AgentRunStatus.RUNNING)
        start_result = await self._runtime_record_port.start_run_if_created(
            TransitionRunCommand(
                expected_active_record=created_run,
                next_record=running_run,
            )
        )
        if start_result is not ConditionalWriteResult.APPLIED:
            raise AgentRunExecutionError("Run start conflict")
        failure_state.running_run = running_run

        await self._append_trace(
            event_type=TraceEventType.MESSAGE_ACCEPTED,
            run_id=running_run.run_id,
            message_ref=user_message.message_id,
        )
        await self._append_trace(
            event_type=TraceEventType.RUN_STARTED,
            run_id=running_run.run_id,
        )
        first_model_call_id = self._uuid_factory()
        await self._append_trace(
            event_type=TraceEventType.REQUEST_UNDERSTANDING_STARTED,
            run_id=running_run.run_id,
            message_ref=user_message.message_id,
            model_call_id=first_model_call_id,
            model_call_purpose="REQUEST_UNDERSTANDING",
        )
        first_manifest = await self._save_manifest(
            run_id=running_run.run_id,
            model_call_id=first_model_call_id,
            model_call_purpose="REQUEST_UNDERSTANDING",
            message_id=user_message.message_id,
        )
        request = RequestUnderstandingInput(
            schema_version="e2e01-thin-v1",
            run_id=running_run.run_id,
            message_ref=user_message.message_id,
            original_query=user_message.content,
            provider_visible_tool_specs=(
                resolved_artifact.provider_visible_tool_specs
            ),
            model_visible_toolset_hash=(
                resolved_artifact.model_visible_toolset_hash
            ),
            output_constraints=(
                "Return exactly one current-message ADD_GOAL candidate.",
                "Never provide trusted identity fields.",
            ),
        )
        noncanonical_provider_signal = False
        try:
            output = await self._model_provider.propose_next_move(request)
        except RequestUnderstandingCandidateInvalidError as error:
            if type(error) is not RequestUnderstandingCandidateInvalidError:
                noncanonical_provider_signal = True
            else:
                return await self._finish_without_task(
                    running_run=running_run,
                    conversation=conversation,
                    stop_reason=StopReason.INPUT_INVALID,
                    failure_state=failure_state,
                )
        except ProviderProtocolError as error:
            if type(error) is not ProviderProtocolError:
                noncanonical_provider_signal = True
            else:
                return await self._finish_without_task(
                    running_run=running_run,
                    conversation=conversation,
                    stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
                    failure_state=failure_state,
                )
        if noncanonical_provider_signal:
            raise AgentRunExecutionError("noncanonical Provider signal")

        reduction_internal_error: str | None = None
        try:
            reduced_at = self._clock()
            decision = validate_and_reduce_initial_request_v2(
                request_input=request,
                output=output,
                authoritative_messages={
                    message.message_id: message.content
                    for message in authoritative_messages
                },
                customer_context=command.customer_context,
                request_understanding_record_id=self._uuid_factory(),
                candidate_identity_allocations=tuple(
                    InitialTaskIdentityAllocationV2(
                        candidate_ref=candidate.candidate_id,
                        accepted_delta_id=self._uuid_factory(),
                        task_id=self._uuid_factory(),
                        request_unit_id=self._uuid_factory(),
                        binding_id=self._uuid_factory(),
                    )
                    for candidate in output.task_delta_candidates
                ),
                next_move_candidate_ref=self._uuid_factory(),
                now=reduced_at,
            )
        except RequestUnderstandingV2Error as error:
            if (
                type(error) is not RequestUnderstandingV2Error
                or type(error.reason_code)
                is RequestUnderstandingAtomicFailureCodeV2
            ):
                reduction_internal_error = (
                    "Request Understanding internal failure"
                )
            elif (
                type(error.reason_code)
                is not RequestUnderstandingAggregateFailureCodeV2
            ):
                reduction_internal_error = (
                    "Request Understanding failure category unavailable"
                )
            else:
                return await self._finish_without_task(
                    running_run=running_run,
                    conversation=conversation,
                    stop_reason=StopReason.INPUT_INVALID,
                    failure_state=failure_state,
                )
        if reduction_internal_error is not None:
            raise AgentRunExecutionError(reduction_internal_error)
        if type(decision) is not InitialRequestRoutableTaskGraphDecisionV2:
            raise AgentRunExecutionError(
                "scoped Request Understanding outcome is not routable"
            )
        task_graph = decision.task_graph
        task = task_graph.task
        request_unit = task_graph.request_unit
        input_binding = task_graph.input_binding

        initial_run_task_link = RunTaskLinkRecord(
            schema_version=_RUN_TASK_LINK_SCHEMA_VERSION,
            run_id=running_run.run_id,
            task_id=task.task_id,
            base_task_state_version=None,
        )
        initial_graph = CreateInitialTaskGraphV2Command(
            owner_scope=owner_scope,
            expected_conversation_record=conversation,
            expected_message_records=authoritative_messages,
            expected_active_run_record=running_run,
            request_understanding=SaveRequestUnderstandingV2AcceptedCommand(
                record=decision.closure.record,
                accepted_delta=task_graph.accepted_delta,
            ),
            initial_task=CreateTaskCommand(initial_record=task),
            initial_request_unit=CreateRequestUnitCommand(
                initial_record=request_unit
            ),
            input_binding=SaveInputBindingCommand(
                record=input_binding,
                request_unit_id=request_unit.request_unit_id,
            ),
            conversation_task_link=ConversationTaskLinkRecord(
                schema_version=_CONVERSATION_TASK_LINK_SCHEMA_VERSION,
                conversation_id=conversation.conversation_id,
                task_id=task.task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=reduced_at,
            ),
            run_task_link=CreateRunTaskLinkCommand(
                active_record=initial_run_task_link
            ),
        )
        graph_result = (
            await self._runtime_record_port
            .create_initial_task_graph_v2_if_current(initial_graph)
        )
        if graph_result is not ConditionalWriteResult.APPLIED:
            raise AgentRunExecutionError("initial Task graph conflict")
        failure_state.active_link = initial_run_task_link
        failure_state.result_task = task

        await self._append_initial_decision_trace(
            run_id=running_run.run_id,
            model_call_id=first_model_call_id,
            context_manifest_id=first_manifest.context_manifest_id,
            decision=decision,
        )
        revalidated_move = revalidate_next_move_v2(
            decision=decision,
            current_task=task,
            current_request_unit=request_unit,
            current_input_binding=input_binding,
        )
        await self._append_trace(
            event_type=TraceEventType.NEXT_MOVE_REVALIDATED,
            run_id=running_run.run_id,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            model_call_id=first_model_call_id,
            requested_tool_name=(
                revalidated_move.requested_provider_tool_name
            ),
            proposed_base_task_state_version=(
                revalidated_move.proposed_base_task_state_version
            ),
            validated_task_state_version=(
                revalidated_move.validated_task_state_version
            ),
            argument_binding_refs=revalidated_move.argument_binding_refs,
        )

        hook_result = self._after_revalidation_hook(
            running_run.run_id,
            task,
            request_unit,
        )
        if inspect.isawaitable(hook_result):
            await hook_result
        current_task = await self._runtime_record_port.load_task_for_owner(
            owner_scope=owner_scope,
            task_id=task.task_id,
        )
        current_unit = (
            await self._runtime_record_port.load_request_unit_for_owner(
                owner_scope=owner_scope,
                request_unit_id=request_unit.request_unit_id,
            )
        )
        if current_task is None or current_unit is None:
            raise AgentRunExecutionError("current Task graph unavailable")
        failure_state.result_task = current_task

        gate = evaluate_control_gateway(
            revalidated_move=revalidated_move,
            customer_context=command.customer_context,
            current_task=current_task,
            current_request_unit=current_unit,
            current_input_binding=input_binding,
            registry_snapshot=self._registry_snapshot,
            context_manifest=first_manifest,
            gate_decision_id=self._uuid_factory(),
            model_call_id=first_model_call_id,
            provider_tool_call_id=None,
            decided_at=self._clock(),
            tool_calls_used=0,
            max_tool_calls=1,
            progress_valid=True,
        )
        await self._runtime_record_port.save_gate_decision(gate)
        await self._append_trace(
            event_type=TraceEventType.GATE_DECISION_RECORDED,
            run_id=running_run.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            model_call_id=first_model_call_id,
            context_manifest_id=first_manifest.context_manifest_id,
            requested_tool_name=gate.requested_provider_tool_name,
            validated_task_state_version=gate.validated_task_state_version,
            argument_binding_refs=gate.argument_binding_refs,
            gate_decision=gate.decision,
            gate_reason_code=gate.reason_code,
        )
        if gate.decision is GateDecisionValue.REJECT:
            return await self._finish_with_task(
                running_run=running_run,
                conversation=conversation,
                current_task=current_task,
                current_unit=current_unit,
                active_link=initial_run_task_link,
                stop_reason=StopReason.GATE_REJECTED,
                target_status=TaskStatus.BLOCKED,
                reason_ref=gate.gate_decision_id,
                failure_state=failure_state,
            )

        registration = resolve_validated_get_order_registration(
            registry_snapshot=self._registry_snapshot,
            requested_provider_name=gate.requested_provider_tool_name,
        )
        if registration is None:
            raise AgentRunExecutionError(
                "accepted Gate lacks a validated registration"
            )
        authorized = AuthorizedToolCommand(
            gate_decision_id=gate.gate_decision_id,
            canonical_tool_name="get_order",
            validated_arguments={
                "order_id": input_binding.normalized_value
            },
            argument_binding_refs=gate.argument_binding_refs,
            validated_task_state_version=gate.validated_task_state_version,
            registry_snapshot_ref=(
                self._registry_snapshot.tool_registry_version
            ),
            trusted_context_ref=f"trusted-context:{self._uuid_factory()}",
        )
        execution = await self._read_tool_executor.execute_get_order(
            owner_scope=owner_scope,
            authorized_command=authorized,
            run_id=running_run.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            model_call_id=first_model_call_id,
            context_manifest_id=first_manifest.context_manifest_id,
            provider_tool_call_id=None,
            tool_registry_version=(
                self._registry_snapshot.tool_registry_version
            ),
            execution_policy=registration.execution_policy,
            remaining_run_time_budget_ms=self._remaining_run_time_budget_ms(
                running_run
            ),
        )
        if (
            execution.terminal_tool_call is None
            or execution.finalized_attempt is None
            or execution.get_order_outcome is None
        ):
            raise AgentRunExecutionError("Read Tool dispatch was not applied")
        await self._append_tool_trace(execution)

        if (
            execution.get_order_outcome
            is GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
        ):
            return await self._finish_with_task(
                running_run=running_run,
                conversation=conversation,
                current_task=current_task,
                current_unit=current_unit,
                active_link=initial_run_task_link,
                stop_reason=StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE,
                target_status=TaskStatus.COMPLETED,
                reason_ref=self._uuid_factory(),
                failure_state=failure_state,
            )
        if execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE:
            return await self._finish_with_task(
                running_run=running_run,
                conversation=conversation,
                current_task=current_task,
                current_unit=current_unit,
                active_link=initial_run_task_link,
                stop_reason=StopReason.ORDER_SERVICE_UNAVAILABLE,
                target_status=TaskStatus.BLOCKED,
                reason_ref=self._uuid_factory(),
                failure_state=failure_state,
            )

        observation = execution.observation
        if observation is None or not (
            _is_canonical_get_order_source_version(
                observation.source_version
            )
        ):
            return await self._finish_with_task(
                running_run=running_run,
                conversation=conversation,
                current_task=current_task,
                current_unit=current_unit,
                active_link=initial_run_task_link,
                stop_reason=StopReason.ORDER_SERVICE_UNAVAILABLE,
                target_status=TaskStatus.BLOCKED,
                reason_ref=self._uuid_factory(),
                failure_state=failure_state,
            )
        await self._append_trace(
            event_type=TraceEventType.OBSERVATION_RECORDED,
            run_id=running_run.run_id,
            occurred_at=observation.recorded_at,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            tool_call_id=execution.terminal_tool_call.tool_call_id,
            observation_ref=observation.observation_id,
        )
        second_model_call_id = self._uuid_factory()
        second_manifest = await self._save_manifest(
            run_id=running_run.run_id,
            model_call_id=second_model_call_id,
            model_call_purpose="PRESENTATION",
            message_id=user_message.message_id,
            task=current_task,
            observation_ref=VersionedRecordRef(
                record_ref=observation.observation_id,
                version=observation.source_version,
            ),
        )
        noncanonical_presentation_signal = False
        try:
            plan = await self._model_provider.plan_presentation(
                PresentationInput(
                    purpose=PresentationPurpose.ORDER_STATUS_SUMMARY,
                    order_summary=observation.normalized_value,
                )
            )
        except ProviderProtocolError as error:
            if type(error) is not ProviderProtocolError:
                noncanonical_presentation_signal = True
            else:
                return await self._finish_with_task(
                    running_run=running_run,
                    conversation=conversation,
                    current_task=current_task,
                    current_unit=current_unit,
                    active_link=initial_run_task_link,
                    stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
                    target_status=TaskStatus.BLOCKED,
                    reason_ref=self._uuid_factory(),
                    observation_ref=observation.observation_id,
                    failure_state=failure_state,
                )
        if noncanonical_presentation_signal:
            raise AgentRunExecutionError(
                "noncanonical Presentation Provider signal"
            )

        presentation_plan_ref = self._uuid_factory()
        await self._append_trace(
            event_type=TraceEventType.PRESENTATION_PLAN_PROPOSED,
            run_id=running_run.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            model_call_id=second_model_call_id,
            context_manifest_id=second_manifest.context_manifest_id,
            observation_ref=observation.observation_id,
            presentation_plan_ref=presentation_plan_ref,
        )
        try:
            validated_plan = validate_presentation_plan(
                plan=plan,
                observation=observation,
            )
        except PresentationPolicyError:
            return await self._finish_with_task(
                running_run=running_run,
                conversation=conversation,
                current_task=current_task,
                current_unit=current_unit,
                active_link=initial_run_task_link,
                stop_reason=StopReason.PRESENTATION_PLAN_REJECTED,
                target_status=TaskStatus.BLOCKED,
                reason_ref=presentation_plan_ref,
                observation_ref=observation.observation_id,
                presentation_plan_ref=presentation_plan_ref,
                failure_state=failure_state,
            )
        try:
            rendered_message = (
                self._deterministic_renderer.render_order_summary(
                    observation=observation,
                    plan=validated_plan,
                )
            )
        except RendererInvariantError:
            return await self._finish_with_task(
                running_run=running_run,
                conversation=conversation,
                current_task=current_task,
                current_unit=current_unit,
                active_link=initial_run_task_link,
                stop_reason=StopReason.RENDERER_INVARIANT_FAILED,
                target_status=TaskStatus.BLOCKED,
                reason_ref=presentation_plan_ref,
                observation_ref=observation.observation_id,
                presentation_plan_ref=presentation_plan_ref,
                failure_state=failure_state,
            )
        return await self._finish_with_task(
            running_run=running_run,
            conversation=conversation,
            current_task=current_task,
            current_unit=current_unit,
            active_link=initial_run_task_link,
            stop_reason=StopReason.GOAL_COMPLETED,
            target_status=TaskStatus.COMPLETED,
            reason_ref=self._uuid_factory(),
            observation_ref=observation.observation_id,
            presentation_plan_ref=presentation_plan_ref,
            rendered_message=rendered_message,
            failure_state=failure_state,
        )

    def _remaining_run_time_budget_ms(
        self,
        running_run: AgentRunRecord,
    ) -> int:
        elapsed_ms = max(
            0.0,
            (self._clock() - running_run.started_at).total_seconds() * 1000,
        )
        remaining_ms = int(self._run_time_budget_ms - elapsed_ms)
        if remaining_ms <= 0:
            raise AgentRunExecutionError("Run time budget exhausted")
        return remaining_ms

    async def _finalize_failed_run_after_error(
        self,
        *,
        failure_state: _RunFailureState,
        original_error: BaseException,
    ) -> None:
        running_run = failure_state.running_run
        if running_run is None:
            return
        active_link = failure_state.active_link
        result_task = failure_state.result_task
        if (active_link is None) != (result_task is None):
            original_error.add_note(
                "Run failure finalization skipped: incomplete local graph cursor"
            )
            return

        expected_active_links: tuple[RunTaskLinkRecord, ...] = ()
        terminal_links: tuple[RunTaskLinkRecord, ...] = ()
        result_task_records: tuple[TaskRecord, ...] = ()
        if active_link is not None and result_task is not None:
            owner_scope = failure_state.owner_scope
            if owner_scope is not None:
                try:
                    current_task = (
                        await self._runtime_record_port.load_task_for_owner(
                            owner_scope=owner_scope,
                            task_id=result_task.task_id,
                        )
                    )
                except (Exception, asyncio.CancelledError) as reload_error:
                    original_error.add_note(
                        "Run failure Task reload raised "
                        f"{type(reload_error).__name__}; cached CAS retained"
                    )
                else:
                    if current_task is not None:
                        result_task = current_task
                        failure_state.result_task = current_task
            expected_active_links = (active_link,)
            terminal_links = (
                RunTaskLinkRecord(
                    schema_version=active_link.schema_version,
                    run_id=active_link.run_id,
                    task_id=active_link.task_id,
                    base_task_state_version=(
                        active_link.base_task_state_version
                    ),
                    result_task_state_version=result_task.state_version,
                ),
            )
            result_task_records = (result_task,)

        terminal_run = _project_run(
            running_run,
            status=AgentRunStatus.FAILED,
            completed_at=self._clock(),
            stop_reason=None,
        )
        try:
            finalize_result = (
                await self._runtime_record_port.finalize_run_if_active(
                    FinalizeRunCommand(
                        expected_active_record=running_run,
                        terminal_record=terminal_run,
                        expected_active_links=expected_active_links,
                        terminal_links=terminal_links,
                        result_task_records=result_task_records,
                        task_transition=None,
                        terminal_result=None,
                        assistant_message=None,
                        terminal_trace_events=(),
                    )
                )
            )
        except (Exception, asyncio.CancelledError) as finalization_error:
            original_error.add_note(
                "Run failure finalization raised "
                f"{type(finalization_error).__name__}"
            )
            return
        if finalize_result is not ConditionalWriteResult.APPLIED:
            original_error.add_note(
                "Run failure finalization was not applied"
            )

    async def _append_initial_decision_trace(
        self,
        *,
        run_id: UUID,
        model_call_id: UUID,
        context_manifest_id: UUID,
        decision: InitialRequestRoutableTaskGraphDecisionV2,
    ) -> None:
        record = decision.closure.record
        graph = decision.task_graph
        await self._append_trace(
            event_type=TraceEventType.NEXT_MOVE_PROPOSED,
            run_id=run_id,
            message_ref=record.message_ref,
            model_call_id=model_call_id,
            context_manifest_id=context_manifest_id,
            next_move_kind=decision.next_move_candidate.kind.value,
            requested_tool_name=(
                decision.next_move_candidate.requested_tool_name
            ),
            proposed_base_task_state_version=(
                decision.next_move_candidate.base_task_state_version
            ),
        )
        await self._append_trace(
            event_type=TraceEventType.TASK_DELTA_VALIDATED,
            run_id=run_id,
            message_ref=record.message_ref,
            accepted_delta_ref=graph.accepted_delta.accepted_delta_id,
        )
        await self._append_trace(
            event_type=TraceEventType.TASK_DELTA_ACCEPTED,
            run_id=run_id,
            message_ref=record.message_ref,
            accepted_delta_ref=graph.accepted_delta.accepted_delta_id,
            task_id=graph.task.task_id,
            request_unit_id=graph.request_unit.request_unit_id,
        )
        await self._append_trace(
            event_type=TraceEventType.INPUT_BINDING_RECORDED,
            run_id=run_id,
            task_id=graph.task.task_id,
            request_unit_id=graph.request_unit.request_unit_id,
            input_binding_ref=graph.input_binding.binding_id,
        )
        await self._append_trace(
            event_type=TraceEventType.TASK_STATE_CHANGED,
            run_id=run_id,
            task_id=graph.task.task_id,
            request_unit_id=graph.request_unit.request_unit_id,
        )

    async def _append_tool_trace(self, execution: ReadToolExecution) -> None:
        created = execution.created_tool_call
        terminal = execution.terminal_tool_call
        attempt = execution.finalized_attempt
        if terminal is None or attempt is None:
            raise AgentRunExecutionError("terminal Tool projection required")
        await self._append_trace(
            event_type=TraceEventType.TOOL_CALL_CREATED,
            run_id=created.run_id,
            occurred_at=created.started_at,
            task_id=created.task_id,
            request_unit_id=created.request_unit_id,
            model_call_id=created.model_call_id,
            context_manifest_id=created.context_manifest_id,
            validated_task_state_version=(
                created.validated_task_state_version
            ),
            argument_binding_refs=created.argument_binding_refs,
            tool_call_id=created.tool_call_id,
            tool_call_terminal_status=ToolCallStatus.CREATED,
        )
        await self._append_trace(
            event_type=TraceEventType.TOOL_CALL_STARTED,
            run_id=created.run_id,
            occurred_at=attempt.started_at,
            task_id=created.task_id,
            request_unit_id=created.request_unit_id,
            tool_call_id=created.tool_call_id,
            tool_call_terminal_status=ToolCallStatus.RUNNING,
        )
        terminal_event_by_status = {
            ToolCallStatus.SUCCEEDED: TraceEventType.TOOL_CALL_SUCCEEDED,
            ToolCallStatus.FAILED: TraceEventType.TOOL_CALL_FAILED,
            ToolCallStatus.TIMED_OUT: TraceEventType.TOOL_CALL_TIMED_OUT,
            ToolCallStatus.INTERRUPTED: TraceEventType.TOOL_CALL_INTERRUPTED,
        }
        terminal_event_type = terminal_event_by_status.get(terminal.status)
        if terminal_event_type is None:
            raise AgentRunExecutionError(
                "terminal ToolCall status required for Trace"
            )
        await self._append_trace(
            event_type=terminal_event_type,
            run_id=created.run_id,
            occurred_at=terminal.finished_at,
            task_id=created.task_id,
            request_unit_id=created.request_unit_id,
            tool_call_id=created.tool_call_id,
            tool_call_terminal_status=terminal.status,
        )
        await self._append_trace(
            event_type=TraceEventType.TOOL_RESULT_NORMALIZED,
            run_id=created.run_id,
            occurred_at=terminal.finished_at,
            task_id=created.task_id,
            request_unit_id=created.request_unit_id,
            tool_call_id=created.tool_call_id,
            safe_tool_outcome=attempt.outcome,
        )

    async def _finish_without_task(
        self,
        *,
        running_run: AgentRunRecord,
        conversation: ConversationRecord,
        stop_reason: StopReason,
        failure_state: _RunFailureState,
    ) -> AgentRunResult:
        result = self._deterministic_renderer.map_result(
            run_id=running_run.run_id,
            stop_reason=stop_reason,
        )
        await self._append_trace(
            event_type=TraceEventType.RESPONSE_RENDERED,
            run_id=running_run.run_id,
        )
        completed_at = self._clock()
        terminal_run = _project_run(
            running_run,
            status=AgentRunStatus.COMPLETED,
            completed_at=completed_at,
            stop_reason=stop_reason,
        )
        assistant_message = MessageRecord(
            schema_version=_MESSAGE_SCHEMA_VERSION,
            message_id=self._uuid_factory(),
            conversation_id=conversation.conversation_id,
            direction=MessageDirection.ASSISTANT,
            content=result.message,
            received_at=completed_at,
        )
        run_stopped = TraceEvent(
            trace_event_id=self._uuid_factory(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=running_run.run_id,
            user_outcome=result.outcome,
            stop_reason=stop_reason,
        )
        write_result = await self._runtime_record_port.finalize_run_if_active(
            FinalizeRunCommand(
                expected_active_record=running_run,
                terminal_record=terminal_run,
                expected_active_links=(),
                terminal_links=(),
                result_task_records=(),
                task_transition=None,
                terminal_result=result,
                assistant_message=assistant_message,
                terminal_trace_events=(run_stopped,),
            )
        )
        if write_result is not ConditionalWriteResult.APPLIED:
            raise AgentRunExecutionError("Run finalization conflict")
        failure_state.committed_result = result
        failure_state.running_run = None
        return result

    async def _finish_with_task(
        self,
        *,
        running_run: AgentRunRecord,
        conversation: ConversationRecord,
        current_task: TaskRecord,
        current_unit: RequestUnitRecord,
        active_link: RunTaskLinkRecord,
        stop_reason: StopReason,
        target_status: TaskStatus,
        reason_ref: UUID,
        observation_ref: UUID | None = None,
        presentation_plan_ref: UUID | None = None,
        rendered_message: str | None = None,
        failure_state: _RunFailureState | None = None,
    ) -> AgentRunResult:
        result = self._deterministic_renderer.map_result(
            run_id=running_run.run_id,
            stop_reason=stop_reason,
            rendered_message=rendered_message,
        )
        await self._append_trace(
            event_type=TraceEventType.RESPONSE_RENDERED,
            run_id=running_run.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            observation_ref=observation_ref,
            presentation_plan_ref=presentation_plan_ref,
        )
        changed_at = self._clock()
        next_task = _project_task(
            current_task,
            status=target_status,
            state_version=current_task.state_version + 1,
            updated_at=changed_at,
            last_outcome_ref=reason_ref,
        )
        observation_refs = current_unit.observation_refs
        if observation_ref is not None and observation_ref not in observation_refs:
            observation_refs = (*observation_refs, observation_ref)
        next_unit = _project_request_unit(
            current_unit,
            observation_refs=observation_refs,
            result_refs=(*current_unit.result_refs, reason_ref),
            status=target_status,
            state_version=current_unit.state_version + 1,
            updated_at=changed_at,
        )
        transition = ApplyTaskTransitionCommand(
            expected_task_record=current_task,
            next_task_record=next_task,
            expected_request_unit_record=current_unit,
            next_request_unit_record=next_unit,
            task_state_transition=TaskStateTransition(
                task_id=current_task.task_id,
                request_unit_id=current_unit.request_unit_id,
                from_status=current_task.status,
                to_status=target_status,
                base_state_version=current_task.state_version,
                result_state_version=current_task.state_version + 1,
                reason_ref=reason_ref,
                changed_at=changed_at,
            ),
        )
        terminal_link = RunTaskLinkRecord(
            schema_version=active_link.schema_version,
            run_id=active_link.run_id,
            task_id=active_link.task_id,
            base_task_state_version=active_link.base_task_state_version,
            result_task_state_version=next_task.state_version,
        )
        completed_at = self._clock()
        terminal_run = _project_run(
            running_run,
            status=AgentRunStatus.COMPLETED,
            completed_at=completed_at,
            stop_reason=stop_reason,
        )
        assistant_message = MessageRecord(
            schema_version=_MESSAGE_SCHEMA_VERSION,
            message_id=self._uuid_factory(),
            conversation_id=conversation.conversation_id,
            direction=MessageDirection.ASSISTANT,
            content=result.message,
            received_at=completed_at,
        )
        task_state_changed = TraceEvent(
            trace_event_id=self._uuid_factory(),
            event_type=TraceEventType.TASK_STATE_CHANGED,
            occurred_at=changed_at,
            run_id=running_run.run_id,
            task_id=next_task.task_id,
            request_unit_id=next_unit.request_unit_id,
        )
        run_stopped = TraceEvent(
            trace_event_id=self._uuid_factory(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=running_run.run_id,
            user_outcome=result.outcome,
            stop_reason=stop_reason,
        )
        finalize_result = (
            await self._runtime_record_port.finalize_run_if_active(
                FinalizeRunCommand(
                    expected_active_record=running_run,
                    terminal_record=terminal_run,
                    expected_active_links=(active_link,),
                    terminal_links=(terminal_link,),
                    result_task_records=(next_task,),
                    task_transition=transition,
                    terminal_result=result,
                    assistant_message=assistant_message,
                    terminal_trace_events=(
                        task_state_changed,
                        run_stopped,
                    ),
                )
            )
        )
        if finalize_result is not ConditionalWriteResult.APPLIED:
            raise AgentRunExecutionError("Run finalization conflict")
        if failure_state is not None:
            failure_state.result_task = next_task
            failure_state.committed_result = result
            failure_state.running_run = None
        return result


@dataclass(frozen=True, slots=True)
class Cycle2RuntimeStep:
    """One bounded Cycle 2 outbound result or private continuation."""

    mapping: Cycle2ResultMapping | None = None
    outbound_result: AgentRunResult | None = None
    verified_target_ref: UUID | None = None
    cycle2_signal: Cycle2MapperSignal | None = None


class _Cycle2ControlProtocolError(Exception):
    """One actual control boundary failed its closed Provider contract."""


def _map_cycle2_typed_tool_result(
    execution: Cycle2ReadToolExecution,
    *,
    canonical_tool_name: str,
    result_type: (
        type[SearchOrdersResult]
        | type[GetOrderResult]
        | type[GetShipmentResult]
    ),
) -> SearchOrdersResult | GetOrderResult | GetShipmentResult:
    """Map the same-attempt JSON envelope to one exact typed business result."""

    if (
        type(execution) is not Cycle2ReadToolExecution
        or type(execution.tool_result) is not ToolResult
        or execution.tool_result.canonical_tool_name != canonical_tool_name
        or execution.tool_result.payload is None
        or execution.tool_result.outcome
        in {
            ToolResultOutcome.TIMEOUT,
            ToolResultOutcome.INTERRUPTED,
            ToolResultOutcome.RESULT_UNKNOWN,
        }
    ):
        raise AgentRunExecutionError("exact terminal typed ToolResult required")
    try:
        payload = thaw_json_value(execution.tool_result.payload)
        if type(payload) is not dict or set(payload) != set(result_type.model_fields):
            raise ValueError("typed payload field set mismatch")
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        typed = result_type.model_validate_json(encoded, strict=True)
        canonical = typed.model_dump(mode="json", round_trip=True)
    except (TypeError, ValueError) as error:
        raise AgentRunExecutionError(
            "Cycle 2 ToolResult payload failed exact typed mapping"
        ) from error
    if canonical != payload:
        raise AgentRunExecutionError(
            "Cycle 2 ToolResult payload failed canonical round trip"
        )
    return typed


def map_cycle2_search_orders_tool_result(
    execution: Cycle2ReadToolExecution,
) -> SearchOrdersResult:
    result = _map_cycle2_typed_tool_result(
        execution,
        canonical_tool_name="search_orders",
        result_type=SearchOrdersResult,
    )
    if type(result) is not SearchOrdersResult:
        raise AgentRunExecutionError("search_orders typed result mismatch")
    return result


def map_cycle2_get_order_tool_result(
    execution: Cycle2ReadToolExecution,
) -> GetOrderResult:
    result = _map_cycle2_typed_tool_result(
        execution,
        canonical_tool_name="get_order",
        result_type=GetOrderResult,
    )
    if type(result) is not GetOrderResult:
        raise AgentRunExecutionError("get_order typed result mismatch")
    return result


def map_cycle2_get_shipment_tool_result(
    execution: Cycle2ReadToolExecution,
) -> GetShipmentResult:
    result = _map_cycle2_typed_tool_result(
        execution,
        canonical_tool_name="get_shipment",
        result_type=GetShipmentResult,
    )
    if type(result) is not GetShipmentResult:
        raise AgentRunExecutionError("get_shipment typed result mismatch")
    return result


class Cycle2AgentRunService:
    """Consume reviewed exact closures without manufacturing authority."""

    def __init__(
        self,
        *,
        runtime_record_port: Cycle2RuntimeRecordPort,
        deterministic_renderer: DeterministicRenderer,
        uuid_factory: Callable[[], UUID],
        result_mapper: RunResultMapper | None = None,
    ) -> None:
        self._runtime_record_port = runtime_record_port
        self._deterministic_renderer = deterministic_renderer
        self._uuid_factory = uuid_factory
        self._result_mapper = result_mapper or RunResultMapper()

    @property
    def result_mapper(self) -> RunResultMapper:
        return self._result_mapper

    def map_imported_phase1(
        self,
        reference: ImportedMapperReference,
    ) -> ImportedMapperReference:
        return self._result_mapper.import_reference(reference)

    def _outbound_step(
        self,
        *,
        run_id: UUID,
        signal: Cycle2MapperSignal,
        rendered_message: str | None = None,
    ) -> Cycle2RuntimeStep:
        mapping = self._result_mapper.map_cycle2(signal)
        return Cycle2RuntimeStep(
            mapping=mapping,
            outbound_result=self._deterministic_renderer.map_cycle2_result(
                run_id=run_id,
                mapping=mapping,
                rendered_message=rendered_message,
            ),
            cycle2_signal=signal,
        )

    async def apply_search_outcome(
        self,
        *,
        run_id: UUID,
        command: ApplyOrderSearchOutcomeV2Command,
        candidate_plan: CandidatePresentationPlan | None = None,
    ) -> Cycle2RuntimeStep:
        """Apply UNIQUE/MULTIPLE atomically and expose no private mapping."""

        if type(command) is not ApplyOrderSearchOutcomeV2Command:
            raise AgentRunExecutionError("exact search outcome command required")
        outcome = command.candidate_set_record.outcome
        if outcome is OrderCandidateSetOutcome.MULTIPLE:
            if type(candidate_plan) is not CandidatePresentationPlan:
                raise AgentRunExecutionError(
                    "MULTIPLE requires canonical candidate presentation plan"
                )
            candidate_rendered = (
                self._deterministic_renderer.render_candidate_summary(
                    projection=project_search_orders_observation_safe(
                        command.search_observation_record
                    ),
                    plan=candidate_plan,
                )
            )
        elif candidate_plan is not None:
            raise AgentRunExecutionError(
                "UNIQUE search cannot carry candidate presentation plan"
            )
        else:
            candidate_rendered = None
        applied = await (
            self._runtime_record_port.apply_order_search_outcome_if_current(
                command
            )
        )
        if applied is not Cycle2WriteResult.APPLIED:
            return self._outbound_step(
                run_id=run_id,
                signal=Cycle2MapperSignal.CANDIDATE_REFRESH_REQUIRED,
            )
        if outcome is OrderCandidateSetOutcome.MULTIPLE:
            return self._outbound_step(
                run_id=run_id,
                signal=Cycle2MapperSignal.SEARCH_MULTIPLE,
                rendered_message=candidate_rendered,
            )
        if outcome is not OrderCandidateSetOutcome.UNIQUE:
            raise AgentRunExecutionError("unsupported search outcome aggregate")
        target = command.auto_target_record
        if type(target) is not OrderCandidateAutoTargetRecord:
            raise AgentRunExecutionError(
                "UNIQUE search lacks reviewed durable auto target"
            )
        return Cycle2RuntimeStep(verified_target_ref=target.verified_target_ref)

    async def apply_ordinal_selection(
        self,
        *,
        run_id: UUID,
        command: ApplyOrderCandidateSelectionV2Command,
    ) -> Cycle2RuntimeStep:
        """Apply one current ordinal CAS; this path never re-runs search."""

        if type(command) is not ApplyOrderCandidateSelectionV2Command:
            raise AgentRunExecutionError("exact ordinal selection command required")
        applied = await (
            self._runtime_record_port.apply_order_candidate_selection_if_current(
                command
            )
        )
        if applied is not Cycle2WriteResult.APPLIED:
            return self._outbound_step(
                run_id=run_id,
                signal=Cycle2MapperSignal.CANDIDATE_REFRESH_REQUIRED,
            )
        return Cycle2RuntimeStep(
            verified_target_ref=command.selected_target_ref
        )

    def complete_order_only(
        self,
        *,
        run_id: UUID,
        observation: OrderObservation,
        plan: PresentationPlan,
    ) -> AgentRunResult:
        """Preserve imported Phase 1 success and perform no Shipment operation."""

        rendered = self._deterministic_renderer.render_order_summary(
            observation=observation,
            plan=plan,
        )
        return self._deterministic_renderer.map_result(
            run_id=run_id,
            stop_reason=StopReason.GOAL_COMPLETED,
            rendered_message=rendered,
        )

    async def assess_and_render_shipment(
        self,
        *,
        run_id: UUID,
        closure: ShipmentAssessmentReadClosure,
        plan: ShipmentPresentationPlan,
    ) -> Cycle2RuntimeStep:
        """Persist and render only a fresh exact deterministic Assessment."""

        if type(closure) is not ShipmentAssessmentReadClosure:
            raise AgentRunExecutionError(
                "exact Shipment Assessment closure required"
            )
        observation = closure.current_observation_record
        assessment = assess_shipment(
            assessment_id=self._uuid_factory(),
            private_owner_scope_ref=closure.owner_scope.customer_id,
            task_id=closure.current_task_record.task_id,
            request_unit_id=closure.current_request_unit_record.request_unit_id,
            task_state_version=closure.current_task_record.state_version,
            verified_order_target_ref=closure.verified_order_target_ref,
            shipment_observation_ref=observation.observation_id,
            shipment_observation_source_version=observation.source_version,
            shipment_summary=observation.normalized_value,
            observation_observed_at=observation.observed_at,
            observation_valid_until=observation.valid_until,
            assessed_at=closure.trusted_assessed_at,
            claim_binding_ref=closure.current_claim_binding_ref,
            supersedes_assessment_ref=(
                None
                if closure.current_assessment_record is None
                else closure.current_assessment_record.assessment_id
            ),
        )
        rendered = self._deterministic_renderer.render_shipment_assessment(
            observation=observation,
            assessment=assessment,
            plan=plan,
        )
        written = await (
            self._runtime_record_port.save_shipment_assessment_if_current(
                SaveShipmentAssessmentV2Command(
                    loaded_closure=closure,
                    assessment_record=assessment,
                )
            )
        )
        if written is not Cycle2WriteResult.APPLIED:
            return self._outbound_step(
                run_id=run_id,
                signal=Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY,
            )
        return self._outbound_step(
            run_id=run_id,
            signal=Cycle2MapperSignal.SHIPMENT_ASSESSMENT_READY,
            rendered_message=rendered,
        )

    async def finalize_obsolete_run(
        self,
        *,
        command: FinalizeSupersededRunV2Command,
    ) -> Cycle2RuntimeStep:
        """Apply an ordinary OA-10 closure and never construct an outbound result."""

        if type(command) is not FinalizeSupersededRunV2Command:
            raise AgentRunExecutionError("exact OA-10 command required")
        written = await (
            self._runtime_record_port.finalize_superseded_run_if_current(
                command
            )
        )
        signal = (
            Cycle2MapperSignal.CONTRADICTORY_INTERRUPTION_EVIDENCE
            if written is not Cycle2WriteResult.APPLIED
            else Cycle2MapperSignal.ORDINARY_OBSOLETE_RUN
        )
        return Cycle2RuntimeStep(mapping=self._result_mapper.map_cycle2(signal))

    async def finalize_retry_recovery_obsolete(
        self,
        *,
        command: FinalizeStateInvalidatedToolRecoveryV2Command,
    ) -> Cycle2RuntimeStep:
        """Consume only the exact retry-scheduled recovery OA-10 aggregate."""

        if type(command) is not FinalizeStateInvalidatedToolRecoveryV2Command:
            raise AgentRunExecutionError(
                "exact state-invalidated recovery command required"
            )
        written = await (
            self._runtime_record_port
            .finalize_state_invalidated_tool_recovery_if_current(command)
        )
        signal = (
            Cycle2MapperSignal.CONTRADICTORY_INTERRUPTION_EVIDENCE
            if written is not Cycle2WriteResult.APPLIED
            else Cycle2MapperSignal.RETRY_RECOVERY_OBSOLETE_RUN
        )
        return Cycle2RuntimeStep(mapping=self._result_mapper.map_cycle2(signal))

    def map_cycle2_tool_terminal(
        self,
        tool_call: ToolCallRecordV2,
    ) -> Cycle2ResultMapping | None:
        """Map terminal Cycle 2 Tool evidence; success needs business result."""

        if type(tool_call) is not ToolCallRecordV2:
            raise AgentRunExecutionError("exact ToolCallRecordV2 required")
        if tool_call.canonical_tool_name not in {
            Cycle2ToolName.SEARCH_ORDERS,
            Cycle2ToolName.GET_SHIPMENT,
        }:
            raise AgentRunExecutionError(
                "Phase 1 get_order terminal stays imported"
            )
        if tool_call.status is ToolCallStatus.SUCCEEDED:
            return None
        if tool_call.status is ToolCallStatus.INTERRUPTED:
            return self._result_mapper.map_cycle2(
                Cycle2MapperSignal.CONTRADICTORY_INTERRUPTION_EVIDENCE
            )
        if tool_call.status not in {
            ToolCallStatus.FAILED,
            ToolCallStatus.TIMED_OUT,
        }:
            raise AgentRunExecutionError("terminal ToolCall required")
        signal_by_code = {
            "ORDER_SEARCH_UNAVAILABLE": Cycle2MapperSignal.ORDER_SEARCH_UNAVAILABLE,
            "SHIPMENT_SERVICE_UNAVAILABLE": (
                Cycle2MapperSignal.SHIPMENT_SERVICE_UNAVAILABLE
            ),
            "SHIPMENT_RELATION_CARDINALITY_VIOLATION": (
                Cycle2MapperSignal.SHIPMENT_RELATION_CARDINALITY
            ),
            "ORDER_SEARCH_SOURCE_INTEGRITY": (
                Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
            ),
            "SHIPMENT_SOURCE_INTEGRITY": (
                Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
            ),
            "SHIPMENT_SOURCE_VERSION_INVALID": (
                Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
            ),
            "ORDER_SEARCH_TRANSIENT": Cycle2MapperSignal.RETRY_EXHAUSTED,
            "SHIPMENT_SERVICE_TRANSIENT": Cycle2MapperSignal.RETRY_EXHAUSTED,
            "TOOL_CALL_TIMEOUT": Cycle2MapperSignal.RETRY_EXHAUSTED,
        }
        signal = signal_by_code.get(
            tool_call.failure_code,
            Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY,
        )
        return self._result_mapper.map_cycle2(signal)


@dataclass(slots=True)
class _Cycle2Turn:
    owner_scope: TrustedOwnerScope
    conversation: ConversationRecord
    user_message: MessageRecord
    running_run: AgentRunRecordV2
    active_link: RunTaskLinkRecordV2 | None
    request_input: RequestUnderstandingInput
    tool_progress: list[Cycle2ToolProgressFact]


class Cycle2AgentRunHandler:
    """Run one real Cycle 2 turn from trusted input through exact v2 Ports."""

    def __init__(
        self,
        *,
        runtime_record_port: Cycle2RuntimeRecordPort,
        context_record_port: RuntimeRecordPort,
        request_understanding_provider: Cycle2RequestUnderstandingProvider,
        read_tool_executor: Cycle2ReadToolExecutor,
        deterministic_renderer: DeterministicRenderer,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
        provider_lane: str,
        redaction_policy_version: str,
        gateway_run_budget_ms: int = 30_000,
        execution_outcome_observer: Cycle2ExecutionOutcomeObserver | None = None,
    ) -> None:
        if (
            type(provider_lane) is not str
            or not provider_lane
            or type(redaction_policy_version) is not str
            or not redaction_policy_version
            or type(gateway_run_budget_ms) is not int
            or gateway_run_budget_ms <= 0
        ):
            raise ValueError("invalid Cycle 2 handler configuration")
        self._runtime_record_port = runtime_record_port
        self._context_record_port = context_record_port
        self._request_understanding_provider = request_understanding_provider
        self._read_tool_executor = read_tool_executor
        self._deterministic_renderer = deterministic_renderer
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._provider_lane = provider_lane
        self._redaction_policy_version = redaction_policy_version
        self._gateway_run_budget_ms = gateway_run_budget_ms
        self._execution_outcome_observer = (
            execution_outcome_observer
            if execution_outcome_observer is not None
            else NoOpCycle2ExecutionOutcomeObserver()
        )
        self._registry_snapshot = validate_cycle2_registry_snapshot(
            build_cycle2_registry_snapshot()
        )
        self._steps = Cycle2AgentRunService(
            runtime_record_port=runtime_record_port,
            deterministic_renderer=deterministic_renderer,
            uuid_factory=uuid_factory,
        )

    async def _propose_cycle2_control(
        self,
        *,
        turn: _Cycle2Turn,
        purpose: Cycle2ControlPurpose,
    ) -> Cycle2ControlCandidate:
        try:
            candidate = await (
                self._request_understanding_provider.propose_cycle2_control(
                    turn.request_input,
                    purpose,
                )
            )
        except (
            AttributeError,
            ProviderProtocolError,
            RequestUnderstandingCandidateInvalidError,
            TypeError,
            ValueError,
        ) as error:
            raise _Cycle2ControlProtocolError from error
        if type(candidate) is not Cycle2ControlCandidate:
            raise _Cycle2ControlProtocolError
        try:
            rebuilt = Cycle2ControlCandidate.model_validate(
                candidate.model_dump(),
                strict=True,
            )
        except (TypeError, ValueError) as error:
            raise _Cycle2ControlProtocolError from error
        if rebuilt != candidate:
            raise _Cycle2ControlProtocolError
        expected_tool = {
            Cycle2ControlPurpose.PROPOSE_GET_ORDER: "get_order",
        }.get(purpose)
        if purpose is Cycle2ControlPurpose.PROPOSE_POST_ORDER:
            if not (
                (
                    candidate.kind is Cycle2ControlCandidateKind.FINISH
                    and candidate.requested_tool_name is None
                )
                or (
                    candidate.kind is Cycle2ControlCandidateKind.CALL_TOOL
                    and candidate.requested_tool_name == "get_shipment"
                )
            ):
                raise _Cycle2ControlProtocolError
        elif expected_tool is None:
            if (
                candidate.kind is not Cycle2ControlCandidateKind.FINISH
                or candidate.requested_tool_name is not None
            ):
                raise _Cycle2ControlProtocolError
        elif (
            candidate.kind is not Cycle2ControlCandidateKind.CALL_TOOL
            or candidate.requested_tool_name != expected_tool
        ):
            raise _Cycle2ControlProtocolError
        return candidate

    async def _materialize_tool_control(
        self,
        *,
        turn: _Cycle2Turn,
        purpose: Cycle2ControlPurpose,
        closure: InitialToolCallV2ReadClosure,
    ) -> NextMove:
        if len(closure.current_verified_order_targets) != 1:
            raise _Cycle2ControlProtocolError
        candidate = await self._propose_cycle2_control(
            turn=turn,
            purpose=purpose,
        )
        try:
            return materialize_cycle2_control_next_move(
                candidate=candidate,
                current_task_state_version=(
                    closure.current_task_record.state_version
                ),
                verified_order_id=(
                    closure.current_verified_order_targets[0].order_id
                ),
            )
        except RequestProcessingError as error:
            raise _Cycle2ControlProtocolError from error

    @staticmethod
    def _materialize_post_order_shipment_control(
        *,
        candidate: Cycle2ControlCandidate,
        closure: InitialToolCallV2ReadClosure,
    ) -> NextMove:
        if (
            candidate.kind is not Cycle2ControlCandidateKind.CALL_TOOL
            or candidate.requested_tool_name != "get_shipment"
            or len(closure.current_verified_order_targets) != 1
            or len(closure.current_target_observations) != 1
        ):
            raise _Cycle2ControlProtocolError
        try:
            return materialize_cycle2_control_next_move(
                candidate=candidate,
                current_task_state_version=(
                    closure.current_task_record.state_version
                ),
                verified_order_id=(
                    closure.current_verified_order_targets[0].order_id
                ),
            )
        except RequestProcessingError as error:
            raise _Cycle2ControlProtocolError from error

    async def _load_post_order_control_closure(
        self,
        *,
        turn: _Cycle2Turn,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
    ) -> InitialToolCallV2ReadClosure:
        closure = await (
            self._runtime_record_port.load_initial_tool_call_v2_closure_for_owner(
                owner_scope=turn.owner_scope,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                trusted_read_at=self._clock(),
            )
        )
        if (
            type(closure) is not InitialToolCallV2ReadClosure
            or len(closure.current_verified_order_targets) != 1
            or len(closure.current_target_observations) != 1
        ):
            raise _Cycle2ControlProtocolError
        return closure

    def _route_post_order_shipment_candidate(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        closure: InitialToolCallV2ReadClosure,
        candidate: Cycle2ControlCandidate,
        model_call_id: UUID,
        manifest_id: UUID,
    ) -> Cycle2GatewayCandidate:
        try:
            next_move = self._materialize_post_order_shipment_control(
                candidate=candidate,
                closure=closure,
            )
            return self._route_verified_shipment_candidate(
                command=command,
                turn=turn,
                closure=closure,
                next_move=next_move,
                model_call_id=model_call_id,
                manifest_id=manifest_id,
            )
        except (AgentRunExecutionError, RequestProcessingError) as error:
            raise _Cycle2ControlProtocolError from error

    @staticmethod
    def _terminal_control_purpose(
        signal: Cycle2MapperSignal,
    ) -> Cycle2ControlPurpose:
        if signal is Cycle2MapperSignal.SEARCH_MULTIPLE:
            return Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION
        if signal is Cycle2MapperSignal.SHIPMENT_ASSESSMENT_READY:
            return Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT
        return Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE

    @staticmethod
    def _require_control_move(value: NextMove | None) -> NextMove:
        if type(value) is not NextMove:
            raise AgentRunExecutionError("actual control NextMove unavailable")
        return value

    async def handle(self, command: AgentRunCommand) -> AgentRunResult:
        if type(command) is not AgentRunCommand:
            raise AgentRunExecutionError("canonical AgentRunCommand required")
        owner_scope = TrustedOwnerScope.from_customer_context(
            command.customer_context
        )
        trusted_now = self._clock()
        current_session = await (
            self._runtime_record_port.load_current_session_task_for_owner(
                owner_scope=owner_scope,
                session_ref_hash=command.customer_context.session_ref_hash,
                trusted_now=trusted_now,
            )
        )
        conversation = (
            ConversationRecord(
                schema_version=_CONVERSATION_SCHEMA_VERSION,
                conversation_id=self._uuid_factory(),
                owner_customer_id=owner_scope.customer_id,
                created_at=trusted_now,
            )
            if current_session is None
            else current_session.conversation_record
        )
        user_message = MessageRecord(
            schema_version=_MESSAGE_SCHEMA_VERSION,
            message_id=self._uuid_factory(),
            conversation_id=conversation.conversation_id,
            direction=MessageDirection.USER,
            content=command.message,
            received_at=trusted_now,
        )
        created_run = AgentRunRecordV2(
            run_id=self._uuid_factory(),
            conversation_id=conversation.conversation_id,
            status=AgentRunStatusV2.CREATED,
            provider_lane=self._provider_lane,
            started_at=trusted_now,
        )
        active_link = (
            None
            if current_session is None
            else RunTaskLinkRecordV2(
                run_id=created_run.run_id,
                task_id=current_session.current_task_record.task_id,
                base_task_state_version=(
                    current_session.current_task_record.state_version
                ),
            )
        )
        root = CreateCycle2RunRootCommand(
            owner_scope=owner_scope,
            session_ref_hash=command.customer_context.session_ref_hash,
            current_session_closure=current_session,
            conversation_record=conversation,
            user_message_record=user_message,
            created_run_record=created_run,
            active_run_task_link_record=active_link,
        )
        if (
            await self._runtime_record_port.insert_cycle2_run_root_if_current(
                root
            )
            is not Cycle2WriteResult.APPLIED
        ):
            raise AgentRunExecutionError("Cycle 2 Run root conflict")
        running_run = _project_cycle2_run(
            created_run,
            status=AgentRunStatusV2.RUNNING,
        )
        if (
            await self._runtime_record_port.start_cycle2_run_if_created(
                StartCycle2RunCommand(
                    owner_scope=owner_scope,
                    expected_created_run_record=created_run,
                    next_running_run_record=running_run,
                    expected_active_run_task_link_record=active_link,
                )
            )
            is not Cycle2WriteResult.APPLIED
        ):
            raise AgentRunExecutionError("Cycle 2 Run start conflict")

        request_input = self._request_input(
            run=running_run,
            message=user_message,
            current_session=current_session,
        )
        turn = _Cycle2Turn(
            owner_scope=owner_scope,
            conversation=conversation,
            user_message=user_message,
            running_run=running_run,
            active_link=active_link,
            request_input=request_input,
            tool_progress=[],
        )
        if current_session is None:
            return await self._handle_initial_turn(
                command=command,
                turn=turn,
            )
        return await self._handle_continuation_turn(
            command=command,
            turn=turn,
            current_session=current_session,
        )

    def _request_input(
        self,
        *,
        run: AgentRunRecordV2,
        message: MessageRecord,
        current_session: object | None,
    ) -> RequestUnderstandingInput:
        if current_session is None:
            focused = None
            pending_question = None
        else:
            task = current_session.current_task_record
            unit = current_session.current_request_unit_record
            focused = ModelVisibleTaskSummary(
                task_alias="current-task",
                request_unit_alias="current-request",
                goal_summary=unit.goal_text,
                status=task.status.value,
                open_questions=unit.open_questions,
            )
            pending_question = (
                unit.open_questions[0] if unit.open_questions else None
            )
        return RequestUnderstandingInput(
            schema_version="e2e01-thin-v1",
            run_id=run.run_id,
            message_ref=message.message_id,
            original_query=message.content,
            pending_question=pending_question,
            active_task_summaries=(() if focused is None else (focused,)),
            focused_task_summary=focused,
            output_constraints=(
                "Return one bounded Cycle 2 proposal for the current message.",
                "Never supply trusted owner, target, record identity, or version.",
            ),
            provider_visible_tool_specs=(
                self._registry_snapshot.provider_visible_toolset
            ),
            model_visible_toolset_hash=(
                self._registry_snapshot.model_visible_toolset_hash
            ),
        )

    async def _stage_initial_turn_v3(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
    ) -> tuple[Cycle2WriteResult, Cycle2InitialRequestDecisionV3 | None]:
        """Build and persist the non-routed initial v3 staging aggregate."""

        output = await self._request_understanding_provider.propose_cycle2_initial(
            turn.request_input
        )
        reduced_at = self._clock()
        decision = validate_and_reduce_cycle2_initial_request_v3(
            request_input=turn.request_input,
            output=output,
            authoritative_messages={
                turn.user_message.message_id: turn.user_message.content
            },
            customer_context=command.customer_context,
            identity_allocation=InitialTaskIdentityAllocationV3(
                request_understanding_record_id=self._uuid_factory(),
                accepted_delta_id=self._uuid_factory(),
                candidate_ref=output.task_delta_candidates[0].candidate_id,
                task_id=self._uuid_factory(),
                request_unit_id=self._uuid_factory(),
                binding_id=self._uuid_factory(),
                next_move_candidate_ref=self._uuid_factory(),
            ),
            now=reduced_at,
        )
        graph = decision.task_graph
        conversation_link = ConversationTaskLinkRecord(
            schema_version=_CONVERSATION_TASK_LINK_SCHEMA_VERSION,
            conversation_id=turn.conversation.conversation_id,
            task_id=graph.task.task_id,
            link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
            linked_at=reduced_at,
        )
        active_link = RunTaskLinkRecordV2(
            run_id=turn.running_run.run_id,
            task_id=graph.task.task_id,
        )
        ordinary_traces = (
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.MESSAGE_ACCEPTED,
                occurred_at=turn.running_run.started_at,
                run_id=turn.running_run.run_id,
                message_ref=turn.user_message.message_id,
            ),
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.RUN_STARTED,
                occurred_at=turn.running_run.started_at,
                run_id=turn.running_run.run_id,
            ),
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.REQUEST_UNDERSTANDING_STARTED,
                occurred_at=reduced_at,
                run_id=turn.running_run.run_id,
                message_ref=turn.user_message.message_id,
                model_call_purpose="REQUEST_UNDERSTANDING",
            ),
        )
        effect_traces = _build_v3_effect_trace_records(
            closure=decision.closure,
            input_bindings=(graph.input_binding,),
            task=graph.task,
            request_unit=graph.request_unit,
            trace_event_ids=tuple(self._uuid_factory() for _ in range(4)),
        )
        staged = CreateCycle2InitialTaskGraphV3Command(
            owner_scope=turn.owner_scope,
            expected_conversation_record=turn.conversation,
            expected_user_message_record=turn.user_message,
            expected_running_run_record=turn.running_run,
            reducer_decision=decision,
            conversation_task_link_record=conversation_link,
            active_run_task_link_record=active_link,
            ordinary_trace_records=ordinary_traces,
            effect_trace_records=effect_traces,
        )
        result = await (
            self._runtime_record_port.create_cycle2_initial_task_graph_v3_if_current(
                staged
            )
        )
        return (
            result,
            decision if result is Cycle2WriteResult.APPLIED else None,
        )

    async def _stage_continuation_turn_v3(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        current_session: Cycle2CurrentSessionTaskClosure,
    ) -> tuple[
        Cycle2WriteResult,
        InputBindingV2 | None,
    ]:
        """Persist one v3 continuation decision but never route or dispatch it."""

        output = await (
            self._request_understanding_provider.propose_cycle2_continuation_v3(
                turn.request_input
            )
        )
        reduced_at = self._clock()
        input_count = len(output.task_delta_candidates[0].input_candidates)
        decision = reduce_cycle2_continuation_task_delta(
            request_input=turn.request_input,
            output=output,
            authoritative_messages={
                turn.user_message.message_id: turn.user_message.content
            },
            customer_context=command.customer_context,
            current_task=current_session.current_task_record,
            current_request_unit=current_session.current_request_unit_record,
            current_input_bindings=(
                current_session.current_input_binding_records
            ),
            identity_allocation=Cycle2ContinuationIdentityAllocationV3(
                request_understanding_record_id=self._uuid_factory(),
                accepted_delta_id=self._uuid_factory(),
                input_binding_ids=tuple(
                    self._uuid_factory() for _ in range(input_count)
                ),
            ),
            now=reduced_at,
        )
        loaded = await (
            self._runtime_record_port.load_continuation_input_binding_closure_for_owner(
                owner_scope=turn.owner_scope,
                conversation_id=turn.conversation.conversation_id,
                message_id=turn.user_message.message_id,
                task_id=current_session.current_task_record.task_id,
                request_unit_id=(
                    current_session.current_request_unit_record.request_unit_id
                ),
                trusted_now=reduced_at,
            )
        )
        if loaded is None:
            raise AgentRunExecutionError("v3 continuation closure unavailable")
        if type(decision) is RejectedCycle2ContinuationDecisionV3:
            result = await (
                self._runtime_record_port
                .save_rejected_continuation_understanding_if_current(
                    SaveRejectedContinuationUnderstandingV3Command(
                        loaded_closure=loaded,
                        decision=decision,
                    )
                )
            )
            return result, None
        if type(decision) is not Cycle2ContinuationDecisionV3:
            raise AgentRunExecutionError("v3 continuation decision unavailable")
        trigger = _routing_trigger_binding_v3(decision)
        if trigger.name == "candidate_ordinal":
            child = decision.closure.accepted_task_deltas[0]
            claim = Cycle2OrdinalClaimPreparation(
                ordinal_input_binding=trigger,
                selection_request=OrderCandidateSelectionRequest(
                    source_message_ref=turn.user_message.message_id,
                    ordinal_input_binding_ref=trigger.binding_id,
                    ordinal=trigger.normalized_value,
                ),
                base_task_state_version=child.base_task_state_version,
                result_task_state_version=child.result_task_state_version,
            )
            proposal = output.task_delta_candidates[0].input_candidates[0]
            try:
                preparation = prepare_cycle2_ordinal_selection(
                    request_input=turn.request_input,
                    candidate=proposal,
                    authoritative_messages={
                        turn.user_message.message_id: turn.user_message.content
                    },
                    customer_context=command.customer_context,
                    current_conversation_id=turn.conversation.conversation_id,
                    current_task=current_session.current_task_record,
                    current_request_unit=(
                        current_session.current_request_unit_record
                    ),
                    current_input_bindings=(
                        current_session.current_input_binding_records
                    ),
                    current_candidate_sets=(
                        current_session.current_candidate_set_records
                    ),
                    pending_candidate_set_ref=(
                        current_session.current_candidate_set_records[0]
                        .candidate_set_id
                        if current_session.current_candidate_set_records
                        else None
                    ),
                    superseded_candidate_set_refs=(
                        current_session.superseded_candidate_set_refs
                    ),
                    existing_selection_records=(
                        current_session.existing_selection_records
                    ),
                    binding_id=trigger.binding_id,
                    now=reduced_at,
                )
            except (RequestProcessingError, IndexError):
                rejected = reject_cycle2_ordinal_selection(
                    claim=claim,
                    reason=self._ordinal_rejection_reason(
                        current_session=current_session,
                        ordinal=trigger.normalized_value,
                        trusted_now=reduced_at,
                    ),
                )
                staged = _build_continuation_v3_command(
                    loaded_closure=loaded,
                    decision=decision,
                    trace_event_ids=tuple(
                        self._uuid_factory() for _index in range(4)
                    ),
                    rejected_ordinal_selection=rejected,
                )
                result = await (
                    self._runtime_record_port
                    .apply_continuation_task_delta_if_current(staged)
                )
                return result, None
            if preparation.ordinal_input_binding != trigger:
                raise AgentRunExecutionError(
                    "v3 ordinal preparation does not match reducer decision"
                )
            if preparation.selection_request != claim.selection_request:
                raise AgentRunExecutionError(
                    "v3 ordinal request does not match reducer decision"
                )
            selection_closure = await (
                self._runtime_record_port
                .load_order_candidate_selection_closure_for_owner(
                    owner_scope=turn.owner_scope,
                    conversation_id=turn.conversation.conversation_id,
                    task_id=current_session.current_task_record.task_id,
                    request_unit_id=(
                        current_session.current_request_unit_record.request_unit_id
                    ),
                    selection_request=preparation.selection_request,
                    trusted_now=reduced_at,
                )
            )
            if type(selection_closure) is not OrderCandidateSelectionReadClosure:
                rejected = reject_cycle2_ordinal_selection(
                    claim=claim,
                    reason=self._ordinal_rejection_reason(
                        current_session=current_session,
                        ordinal=trigger.normalized_value,
                        trusted_now=reduced_at,
                    ),
                )
                staged = _build_continuation_v3_command(
                    loaded_closure=loaded,
                    decision=decision,
                    trace_event_ids=tuple(
                        self._uuid_factory() for _index in range(4)
                    ),
                    rejected_ordinal_selection=rejected,
                )
                result = await (
                    self._runtime_record_port
                    .apply_continuation_task_delta_if_current(staged)
                )
                return result, None
            return await self._stage_order_selection_v3(
                loaded_closure=selection_closure,
                decision=decision,
            )
        staged = _build_continuation_v3_command(
            loaded_closure=loaded,
            decision=decision,
            trace_event_ids=tuple(
                self._uuid_factory()
                for _ in range(len(decision.input_bindings) + 3)
            ),
        )
        result = await (
            self._runtime_record_port.apply_continuation_task_delta_if_current(
                staged
            )
        )
        return (
            result,
            _routing_trigger_binding_v3(decision)
            if result is Cycle2WriteResult.APPLIED
            else None,
        )

    async def _stage_order_selection_v3(
        self,
        *,
        loaded_closure: OrderCandidateSelectionReadClosure,
        decision: Cycle2ContinuationDecisionV3,
    ) -> tuple[Cycle2WriteResult, InputBindingV2 | None]:
        """Persist ordinal v3 selection without entering the active route."""

        staged = _build_order_selection_v3_staging_command(
            loaded_closure=loaded_closure,
            decision=decision,
            issued_selected_target=IssuedSelectedTargetRef.fresh_v3(),
            selection_id=self._uuid_factory(),
            trace_event_ids=tuple(self._uuid_factory() for _index in range(4)),
        )
        result = await (
            self._runtime_record_port
            .apply_order_candidate_selection_v3_if_current(staged)
        )
        return (
            result,
            staged.ordinal_input_binding_record
            if result is Cycle2WriteResult.APPLIED
            else None,
        )

    async def _handle_initial_turn(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
    ) -> AgentRunResult:
        try:
            output = await (
                self._request_understanding_provider.propose_cycle2_initial(
                    turn.request_input
                )
            )
            reduced_at = self._clock()
            decision = validate_and_reduce_cycle2_initial_request_v2(
                request_input=turn.request_input,
                output=output,
                authoritative_messages={
                    turn.user_message.message_id: turn.user_message.content
                },
                customer_context=command.customer_context,
                identity_allocation=InitialTaskIdentityAllocationV2(
                    candidate_ref=output.task_delta_candidates[0].candidate_id,
                    accepted_delta_id=self._uuid_factory(),
                    task_id=self._uuid_factory(),
                    request_unit_id=self._uuid_factory(),
                    binding_id=self._uuid_factory(),
                ),
                next_move_candidate_ref=self._uuid_factory(),
                now=reduced_at,
            )
        except RequestUnderstandingCandidateInvalidError:
            return await self._finish_fixed_phase1(
                turn=turn,
                stop_reason_v1=StopReason.INPUT_INVALID,
                stop_reason_v2=StopReasonV2.INPUT_INVALID,
            )
        except ProviderProtocolError:
            return await self._finish_fixed_phase1(
                turn=turn,
                stop_reason_v1=StopReason.PROVIDER_PROTOCOL_ERROR,
                stop_reason_v2=StopReasonV2.PROVIDER_PROTOCOL_ERROR,
            )
        except (RequestProcessingError, RequestUnderstandingV2Error):
            return await self._finish_fixed_phase1(
                turn=turn,
                stop_reason_v1=StopReason.INPUT_INVALID,
                stop_reason_v2=StopReasonV2.INPUT_INVALID,
            )
        return await self._commit_initial_and_search(
            command=command,
            turn=turn,
            decision=decision,
            committed_at=reduced_at,
        )

    async def _commit_initial_and_search(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        decision: Cycle2InitialRequestDecisionV2,
        committed_at: datetime,
    ) -> AgentRunResult:
        graph = decision.task_graph
        conversation_link = ConversationTaskLinkRecord(
            schema_version=_CONVERSATION_TASK_LINK_SCHEMA_VERSION,
            conversation_id=turn.conversation.conversation_id,
            task_id=graph.task.task_id,
            link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
            linked_at=committed_at,
        )
        active_link = RunTaskLinkRecordV2(
            run_id=turn.running_run.run_id,
            task_id=graph.task.task_id,
        )
        trace_records = (
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.MESSAGE_ACCEPTED,
                occurred_at=turn.running_run.started_at,
                run_id=turn.running_run.run_id,
                message_ref=turn.user_message.message_id,
            ),
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.RUN_STARTED,
                occurred_at=turn.running_run.started_at,
                run_id=turn.running_run.run_id,
            ),
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.REQUEST_UNDERSTANDING_STARTED,
                occurred_at=committed_at,
                run_id=turn.running_run.run_id,
                message_ref=turn.user_message.message_id,
                model_call_purpose="REQUEST_UNDERSTANDING",
            ),
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.TASK_DELTA_ACCEPTED,
                occurred_at=committed_at,
                run_id=turn.running_run.run_id,
                message_ref=turn.user_message.message_id,
                accepted_delta_ref=graph.accepted_delta.accepted_delta_id,
                task_id=graph.task.task_id,
                request_unit_id=graph.request_unit.request_unit_id,
            ),
            TraceEventV2(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.INPUT_BINDING_RECORDED,
                occurred_at=committed_at,
                run_id=turn.running_run.run_id,
                task_id=graph.task.task_id,
                request_unit_id=graph.request_unit.request_unit_id,
                input_binding_ref=graph.input_binding.binding_id,
            ),
        )
        command_record = CreateCycle2InitialTaskGraphCommand(
            owner_scope=turn.owner_scope,
            expected_conversation_record=turn.conversation,
            expected_user_message_record=turn.user_message,
            expected_running_run_record=turn.running_run,
            reducer_decision=decision,
            conversation_task_link_record=conversation_link,
            active_run_task_link_record=active_link,
            ordinary_trace_records=trace_records,
        )
        if (
            await self._runtime_record_port.create_cycle2_initial_task_graph_if_current(
                command_record
            )
            is not Cycle2WriteResult.APPLIED
        ):
            raise AgentRunExecutionError("initial Cycle 2 Task graph conflict")
        turn.active_link = active_link
        return await self._search_orders(
            command=command,
            turn=turn,
            task=graph.task,
            request_unit=graph.request_unit,
            input_bindings=(graph.input_binding,),
            candidate_factory=lambda _closure, model_call_id, manifest_id, _move: Cycle2GatewayCandidate(
                run_id=turn.running_run.run_id,
                task_id=graph.task.task_id,
                request_unit_id=graph.request_unit.request_unit_id,
                model_call_id=model_call_id,
                context_manifest_id=manifest_id,
                requested_provider_tool_name=(
                    decision.next_move_candidate.requested_tool_name
                ),
                candidate_arguments=decision.next_move_candidate.arguments,
                proposed_base_task_state_version=(
                    decision.proposed_base_task_state_version
                ),
                validated_task_state_version=(
                    decision.validated_task_state_version
                ),
                argument_binding_refs=decision.argument_binding_refs,
                verified_target_ref=None,
            ),
        )

    def _step_for_signal(
        self,
        *,
        run_id: UUID,
        signal: Cycle2MapperSignal,
    ) -> Cycle2RuntimeStep:
        mapping = self._steps.result_mapper.map_cycle2(signal)
        return Cycle2RuntimeStep(
            mapping=mapping,
            outbound_result=self._deterministic_renderer.map_cycle2_result(
                run_id=run_id,
                mapping=mapping,
            ),
            cycle2_signal=signal,
        )

    async def _search_orders(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
        input_bindings: tuple[InputBindingV2, ...],
        candidate_factory: Callable[
            [InitialToolCallV2ReadClosure, UUID, UUID, NextMove | None],
            Cycle2GatewayCandidate,
        ],
    ) -> AgentRunResult:
        dispatched = await self._execute_tool(
            command=command,
            turn=turn,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            candidate_factory=candidate_factory,
        )
        if type(dispatched) is AgentRunResult:
            return await self._finalize_imported(
                turn=turn,
                result=dispatched,
                stop_reason=StopReasonV2.GATE_REJECTED,
                task=task,
                request_unit=request_unit,
                reference=ImportedMapperReference.GATE_REJECTED,
                response_policy=ResponsePolicy.INTEGRITY_BLOCKED_FIXED,
            )
        if (
            type(dispatched) is not Cycle2ReadToolExecution
            or dispatched.tool_result is None
        ):
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=task,
                request_unit=request_unit,
            )
        result = map_cycle2_search_orders_tool_result(dispatched)
        if result.outcome is SearchOrdersOutcome.NO_MATCH:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.SEARCH_NO_MATCH,
                ),
                task=task,
                request_unit=request_unit,
            )
        if result.outcome is SearchOrdersOutcome.SYSTEM_FAILURE:
            signal = (
                Cycle2MapperSignal.ORDER_SEARCH_UNAVAILABLE
                if getattr(result.failure_code, "value", None)
                == "ORDER_SEARCH_UNAVAILABLE"
                else Cycle2MapperSignal.RETRY_EXHAUSTED
            )
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=signal,
                ),
                task=task,
                request_unit=request_unit,
            )
        return await self._apply_successful_search(
            command=command,
            turn=turn,
            task=task,
            request_unit=request_unit,
            input_bindings=input_bindings,
            execution=dispatched,
            result=result,
        )

    async def _apply_successful_search(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
        input_bindings: tuple[InputBindingV2, ...],
        execution: Cycle2ReadToolExecution,
        result: SearchOrdersResult,
    ) -> AgentRunResult:
        terminal = execution.terminal_tool_call
        if (
            terminal.status is not ToolCallStatus.SUCCEEDED
            or terminal.finished_at is None
            or terminal.result_ref is None
            or result.observed_at is None
            or result.snapshot_resource_ref is None
            or result.snapshot_source_version is None
        ):
            raise AgentRunExecutionError("successful search source is incomplete")
        recorded_at = max(
            self._clock(),
            terminal.finished_at,
            result.observed_at,
        )
        candidate_refs = tuple(self._uuid_factory() for _ in result.candidates)
        observation = SearchOrdersObservation(
            observation_id=self._uuid_factory(),
            private_owner_scope=turn.owner_scope.customer_id,
            source_tool="search_orders",
            source_tool_call_id=terminal.tool_call_id,
            source_resource_ref=result.snapshot_resource_ref,
            source_version=result.snapshot_source_version,
            candidate_target_bindings=tuple(
                SearchObservationCandidateTargetBinding(
                    observation_candidate_ref=candidate_ref,
                    owner_scoped_order_ref=candidate.owner_scoped_order_ref,
                    candidate_source_version=(
                        candidate.candidate_source_version
                    ),
                )
                for candidate_ref, candidate in zip(
                    candidate_refs,
                    result.candidates,
                    strict=True,
                )
            ),
            normalized_type="ORDER_SEARCH_CANDIDATES",
            normalized_value=SearchOrdersObservationValue(
                ordered_candidates=tuple(
                    SearchOrdersObservationCandidate(
                        observation_candidate_ref=candidate_ref,
                        candidate_source_version=(
                            candidate.candidate_source_version
                        ),
                        public_summary=candidate.public_summary,
                    )
                    for candidate_ref, candidate in zip(
                        candidate_refs,
                        result.candidates,
                        strict=True,
                    )
                ),
                truncated=result.truncated,
            ),
            observed_at=result.observed_at,
            recorded_at=recorded_at,
            valid_until=recorded_at + ORDER_CANDIDATE_SET_TTL,
        )
        search_read = await (
            self._runtime_record_port.load_order_search_current_closure_for_owner(
                owner_scope=turn.owner_scope,
                conversation_id=turn.conversation.conversation_id,
                run_id=turn.running_run.run_id,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                trusted_read_at=recorded_at,
            )
        )
        if type(search_read) is not OrderSearchCurrentReadClosure:
            raise AgentRunExecutionError("search current closure unavailable")
        outcome = OrderCandidateSetOutcome(result.outcome.value)
        entries = tuple(
            OrderCandidateSetEntry(
                ordinal=ordinal,
                observation_candidate_ref=candidate_ref,
                candidate_source_version=candidate.candidate_source_version,
            )
            for ordinal, (candidate_ref, candidate) in enumerate(
                zip(candidate_refs, result.candidates, strict=True),
                start=1,
            )
        )
        candidate_set_id = self._uuid_factory()
        next_version = task.state_version + 1
        previous_set = search_read.current_candidate_set_record
        candidate_set_fields = {
            "candidate_set_id": candidate_set_id,
            "private_owner_scope_ref": turn.owner_scope.customer_id,
            "conversation_id": turn.conversation.conversation_id,
            "task_id": task.task_id,
            "request_unit_id": request_unit.request_unit_id,
            "outcome": outcome,
            "base_task_state_version": task.state_version,
            "result_task_state_version": next_version,
            "selection_expected_task_state_version": (
                next_version
                if outcome is OrderCandidateSetOutcome.MULTIPLE
                else None
            ),
            "query_binding_refs": terminal.argument_binding_refs,
            "source_tool_call_id": terminal.tool_call_id,
            "search_observation_ref": observation.observation_id,
            "search_observation_record_schema_version": (
                observation.record_schema_version
            ),
            "search_observation_source_version": observation.source_version,
            "ordered_candidates": entries,
            "created_at": recorded_at,
            "valid_until": observation.valid_until,
            "supersedes_candidate_set_ref": (
                None if previous_set is None else previous_set.candidate_set_id
            ),
        }
        candidate_set = OrderCandidateSetRecord(
            **candidate_set_fields,
            candidate_set_version=compute_order_candidate_set_version(
                **candidate_set_fields
            ),
        )
        waiting = outcome is OrderCandidateSetOutcome.MULTIPLE
        next_status = TaskStatus.WAITING_USER if waiting else TaskStatus.ACTIVE
        next_task = _project_task(
            task,
            status=next_status,
            state_version=next_version,
            updated_at=recorded_at,
        )
        next_unit = _project_request_unit(
            request_unit,
            status=next_status,
            state_version=next_version,
            updated_at=recorded_at,
            open_questions=(
                ("请选择候选订单序号。",) if waiting else ()
            ),
            observation_refs=(
                *request_unit.observation_refs,
                observation.observation_id,
            ),
        )
        if outcome is OrderCandidateSetOutcome.UNIQUE:
            resolved_candidate = result.candidates[0]
            auto_target = build_cycle2_unique_auto_target_record(
                customer_context=command.customer_context,
                current_conversation_id=turn.conversation.conversation_id,
                current_task=next_task,
                current_request_unit=next_unit,
                current_input_bindings=input_bindings,
                candidate_set=candidate_set,
                search_observation=observation,
                source_tool_argument_binding_refs=(
                    terminal.argument_binding_refs
                ),
                resolved_owner_scoped_order_target_ref=(
                    resolved_candidate.owner_scoped_order_ref
                ),
                resolved_order_id=resolved_candidate.order_number,
                verified_target_ref=self._uuid_factory(),
                current_auto_targets=(
                    search_read.current_auto_target_records
                ),
                trusted_now=recorded_at,
            )
        else:
            resolved_candidate = None
            auto_target = None
        aggregate = ApplyOrderSearchOutcomeV2Command(
            owner_scope=turn.owner_scope,
            loaded_read_closure=search_read,
            trusted_conversation_record=turn.conversation,
            source_run_record=turn.running_run,
            current_query_binding=search_read.current_query_binding,
            expected_task_record=task,
            next_task_record=next_task,
            expected_request_unit_record=request_unit,
            next_request_unit_record=next_unit,
            source_tool_call_record=terminal,
            search_observation_record=observation,
            candidate_set_record=candidate_set,
            previous_candidate_set_record=previous_set,
            current_query_binding_refs=terminal.argument_binding_refs,
            pending_candidate_set_ref=(candidate_set_id if waiting else None),
            resolved_owner_scoped_order_target_ref=(
                None
                if resolved_candidate is None
                else resolved_candidate.owner_scoped_order_ref
            ),
            resolved_order_id=(
                None
                if resolved_candidate is None
                else resolved_candidate.order_number
            ),
            auto_target_record=auto_target,
        )
        applied = await self._steps.apply_search_outcome(
            run_id=turn.running_run.run_id,
            command=aggregate,
            candidate_plan=(
                _cycle2_candidate_presentation_plan() if waiting else None
            ),
        )
        if applied.outbound_result is not None:
            search_state_committed = (
                applied.mapping is not None
                and applied.mapping.stop_reason
                is StopReasonV2.CANDIDATE_CLARIFICATION_REQUIRED
            )
            return await self._finalize_mapping(
                turn=turn,
                step=applied,
                task=next_task if search_state_committed else task,
                request_unit=(
                    next_unit if search_state_committed else request_unit
                ),
            )
        if (
            type(auto_target) is not OrderCandidateAutoTargetRecord
            or resolved_candidate is None
            or applied.verified_target_ref != auto_target.verified_target_ref
        ):
            raise AgentRunExecutionError("UNIQUE target was not committed")
        return await self._get_order(
            command=command,
            turn=turn,
            task=next_task,
            request_unit=next_unit,
            candidate_factory=lambda closure, model_call_id, manifest_id, control_move: (
                self._route_unique_candidate(
                    command=command,
                    turn=turn,
                    closure=closure,
                    next_move=self._require_control_move(control_move),
                    candidate_set=candidate_set,
                    observation=observation,
                    auto_target=auto_target,
                    resolved_owner_scoped_order_target_ref=(
                        resolved_candidate.owner_scoped_order_ref
                    ),
                    previous_candidate_set=previous_set,
                    model_call_id=model_call_id,
                    manifest_id=manifest_id,
                )
            ),
            control_purpose=Cycle2ControlPurpose.PROPOSE_GET_ORDER,
        )

    def _route_unique_candidate(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        closure: InitialToolCallV2ReadClosure,
        next_move: NextMove,
        candidate_set: OrderCandidateSetRecord,
        observation: SearchOrdersObservation,
        auto_target: OrderCandidateAutoTargetRecord,
        resolved_owner_scoped_order_target_ref: str,
        previous_candidate_set: OrderCandidateSetRecord | None,
        model_call_id: UUID,
        manifest_id: UUID,
    ) -> Cycle2GatewayCandidate:
        targets = tuple(
            target
            for target in closure.current_verified_order_targets
            if target.verified_target_ref == auto_target.verified_target_ref
        )
        if len(targets) != 1:
            raise AgentRunExecutionError("UNIQUE target facts unavailable")
        return route_cycle2_unique_next_move(
            request_input=turn.request_input,
            next_move=next_move,
            customer_context=command.customer_context,
            current_conversation_id=turn.conversation.conversation_id,
            current_task=closure.current_task_record,
            current_request_unit=closure.current_request_unit_record,
            current_input_bindings=closure.current_input_binding_records,
            candidate_set=candidate_set,
            search_observation=observation,
            auto_target_record=auto_target,
            resolved_owner_scoped_order_target_ref=(
                resolved_owner_scoped_order_target_ref
            ),
            current_auto_targets=(auto_target,),
            superseded_candidate_set_refs=(
                ()
                if previous_candidate_set is None
                else (previous_candidate_set.candidate_set_id,)
            ),
            superseded_verified_target_refs=(
                ()
                if auto_target.supersedes_verified_target_ref is None
                else (auto_target.supersedes_verified_target_ref,)
            ),
            verified_target=targets[0],
            model_call_id=model_call_id,
            context_manifest_id=manifest_id,
            trusted_now=closure.trusted_read_at,
        )

    async def _get_order(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
        candidate_factory: Callable[
            [InitialToolCallV2ReadClosure, UUID, UUID, NextMove | None],
            Cycle2GatewayCandidate,
        ],
        control_purpose: Cycle2ControlPurpose | None = None,
    ) -> AgentRunResult:
        try:
            dispatched = await self._execute_tool(
                command=command,
                turn=turn,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                candidate_factory=candidate_factory,
                control_purpose=control_purpose,
            )
        except _Cycle2ControlProtocolError:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY,
                ),
                task=task,
                request_unit=request_unit,
                consume_control=False,
            )
        if type(dispatched) is AgentRunResult:
            return await self._finalize_imported(
                turn=turn,
                result=dispatched,
                stop_reason=StopReasonV2.GATE_REJECTED,
                task=task,
                request_unit=request_unit,
                reference=ImportedMapperReference.GATE_REJECTED,
                response_policy=ResponsePolicy.INTEGRITY_BLOCKED_FIXED,
            )
        if (
            type(dispatched) is not Cycle2ReadToolExecution
            or dispatched.tool_result is None
        ):
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=task,
                request_unit=request_unit,
            )
        result = map_cycle2_get_order_tool_result(dispatched)
        if result.outcome is GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.PRIVATE_RESOURCE_NOT_FOUND,
                ),
                task=task,
                request_unit=request_unit,
            )
        if result.outcome is GetOrderOutcome.SYSTEM_FAILURE:
            result_outbound = self._deterministic_renderer.map_result(
                run_id=turn.running_run.run_id,
                stop_reason=StopReason.ORDER_SERVICE_UNAVAILABLE,
            )
            return await self._finalize_imported(
                turn=turn,
                result=result_outbound,
                stop_reason=StopReasonV2.ORDER_SERVICE_UNAVAILABLE,
                task=task,
                request_unit=request_unit,
                reference=ImportedMapperReference.ORDER_SERVICE_UNAVAILABLE,
                response_policy=ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
            )
        terminal = dispatched.terminal_tool_call
        summary = result.order_summary
        if (
            terminal.status is not ToolCallStatus.SUCCEEDED
            or terminal.finished_at is None
            or terminal.result_ref is None
            or summary is None
            or result.source_version is None
        ):
            raise AgentRunExecutionError("successful get_order source is incomplete")
        recorded_at = max(self._clock(), terminal.finished_at)
        observation = OrderObservation(
            observation_id=self._uuid_factory(),
            source_tool="get_order",
            source_resource_ref=summary.order_number,
            source_version=result.source_version,
            normalized_type="ORDER_SUMMARY",
            normalized_value=summary,
            observed_at=terminal.finished_at,
            recorded_at=recorded_at,
            visibility=ObservationVisibility.MODEL_VISIBLE,
        )
        next_task = _project_task(
            task,
            state_version=task.state_version + 1,
            updated_at=recorded_at,
        )
        next_unit = _project_request_unit(
            request_unit,
            state_version=request_unit.state_version + 1,
            updated_at=recorded_at,
            observation_refs=(
                *request_unit.observation_refs,
                observation.observation_id,
            ),
        )
        written = await self._runtime_record_port.save_order_observation_if_current(
            SaveOrderObservationV2Command(
                owner_scope=turn.owner_scope,
                expected_task_record=task,
                next_task_record=next_task,
                expected_request_unit_record=request_unit,
                next_request_unit_record=next_unit,
                source_tool_call_record=terminal,
                source_result_ref=terminal.result_ref,
                source_result=result,
                observation_record=observation,
                trusted_acceptance_now=recorded_at,
            )
        )
        if written is not Cycle2WriteResult.APPLIED:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=task,
                request_unit=request_unit,
        )
        try:
            await self._load_post_order_control_closure(
                turn=turn,
                task=next_task,
                request_unit=next_unit,
            )
            post_order_candidate = await self._propose_cycle2_control(
                turn=turn,
                purpose=Cycle2ControlPurpose.PROPOSE_POST_ORDER,
            )
        except _Cycle2ControlProtocolError:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=next_task,
                request_unit=next_unit,
                consume_control=False,
            )
        if post_order_candidate.kind is Cycle2ControlCandidateKind.FINISH:
            result_outbound = self._steps.complete_order_only(
                run_id=turn.running_run.run_id,
                observation=observation,
                plan=_cycle2_order_presentation_plan(),
            )
            return await self._finalize_imported(
                turn=turn,
                result=result_outbound,
                stop_reason=StopReasonV2.GOAL_COMPLETED,
                task=next_task,
                request_unit=next_unit,
                reference=ImportedMapperReference.ORDER_SUCCESS,
                response_policy=ResponsePolicy.DETERMINISTIC_ORDER_SUMMARY_V1,
                consume_control=False,
            )
        return await self._get_shipment(
            command=command,
            turn=turn,
            task=next_task,
            request_unit=next_unit,
            candidate_factory=lambda closure, model_call_id, manifest_id, _control_move: (
                self._route_post_order_shipment_candidate(
                    command=command,
                    turn=turn,
                    closure=closure,
                    candidate=post_order_candidate,
                    model_call_id=model_call_id,
                    manifest_id=manifest_id,
                )
            ),
            closure_unavailable_is_control_error=True,
        )

    def _route_verified_shipment_candidate(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        closure: InitialToolCallV2ReadClosure,
        next_move: NextMove,
        model_call_id: UUID,
        manifest_id: UUID,
    ) -> Cycle2GatewayCandidate:
        if (
            len(closure.current_verified_order_targets) != 1
            or len(closure.current_target_observations) != 1
        ):
            raise AgentRunExecutionError(
                "current verified Order target closure unavailable"
            )
        return route_cycle2_verified_target_next_move(
            request_input=turn.request_input,
            next_move=next_move,
            customer_context=command.customer_context,
            current_task=closure.current_task_record,
            current_request_unit=closure.current_request_unit_record,
            current_input_bindings=closure.current_input_binding_records,
            verified_target=closure.current_verified_order_targets[0],
            verified_target_observation=closure.current_target_observations[0],
            model_call_id=model_call_id,
            context_manifest_id=manifest_id,
            trusted_now=closure.trusted_read_at,
        )

    async def _get_shipment(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
        candidate_factory: Callable[
            [InitialToolCallV2ReadClosure, UUID, UUID, NextMove | None],
            Cycle2GatewayCandidate,
        ],
        control_purpose: Cycle2ControlPurpose | None = None,
        closure_unavailable_is_control_error: bool = False,
    ) -> AgentRunResult:
        try:
            dispatched = await self._execute_tool(
                command=command,
                turn=turn,
                task_id=task.task_id,
                request_unit_id=request_unit.request_unit_id,
                candidate_factory=candidate_factory,
                control_purpose=control_purpose,
                closure_unavailable_is_control_error=(
                    closure_unavailable_is_control_error
                ),
            )
        except _Cycle2ControlProtocolError:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY,
                ),
                task=task,
                request_unit=request_unit,
                consume_control=False,
            )
        if type(dispatched) is AgentRunResult:
            return await self._finalize_imported(
                turn=turn,
                result=dispatched,
                stop_reason=StopReasonV2.GATE_REJECTED,
                task=task,
                request_unit=request_unit,
                reference=ImportedMapperReference.GATE_REJECTED,
                response_policy=ResponsePolicy.INTEGRITY_BLOCKED_FIXED,
            )
        if (
            type(dispatched) is not Cycle2ReadToolExecution
            or dispatched.tool_result is None
        ):
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=task,
                request_unit=request_unit,
            )
        result = map_cycle2_get_shipment_tool_result(dispatched)
        signal_by_outcome = {
            GetShipmentOutcome.NO_SHIPMENT: Cycle2MapperSignal.NO_SHIPMENT,
            GetShipmentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE: (
                Cycle2MapperSignal.PRIVATE_RESOURCE_NOT_FOUND
            ),
            GetShipmentOutcome.FACTS_INSUFFICIENT: (
                Cycle2MapperSignal.SHIPMENT_FACTS_INSUFFICIENT
            ),
        }
        if result.outcome in signal_by_outcome:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=signal_by_outcome[result.outcome],
                ),
                task=task,
                request_unit=request_unit,
            )
        if result.outcome is GetShipmentOutcome.SYSTEM_FAILURE:
            code = getattr(result.failure_code, "value", None)
            signal = {
                "SHIPMENT_SERVICE_UNAVAILABLE": (
                    Cycle2MapperSignal.SHIPMENT_SERVICE_UNAVAILABLE
                ),
                "SHIPMENT_RELATION_CARDINALITY_VIOLATION": (
                    Cycle2MapperSignal.SHIPMENT_RELATION_CARDINALITY
                ),
                "SHIPMENT_SOURCE_INTEGRITY": (
                    Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                ),
                "SHIPMENT_SOURCE_VERSION_INVALID": (
                    Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                ),
            }.get(code, Cycle2MapperSignal.RETRY_EXHAUSTED)
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=signal,
                ),
                task=task,
                request_unit=request_unit,
            )
        terminal = dispatched.terminal_tool_call
        summary = result.shipment_summary
        if (
            terminal.status is not ToolCallStatus.SUCCEEDED
            or terminal.finished_at is None
            or terminal.result_ref is None
            or terminal.verified_target_ref is None
            or summary is None
            or result.source_resource_ref is None
            or result.source_version is None
            or result.observed_at is None
        ):
            raise AgentRunExecutionError(
                "successful get_shipment source is incomplete"
            )
        recorded_at = max(self._clock(), terminal.finished_at, result.observed_at)
        if recorded_at >= result.observed_at + SHIPMENT_FRESHNESS_TTL:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.SHIPMENT_BORN_STALE,
                ),
                task=task,
                request_unit=request_unit,
            )
        observation = ShipmentObservation(
            observation_id=self._uuid_factory(),
            private_owner_scope=turn.owner_scope.customer_id,
            task_id=task.task_id,
            request_unit_id=request_unit.request_unit_id,
            verified_order_target_ref=str(terminal.verified_target_ref),
            source_tool="get_shipment",
            source_tool_call_id=terminal.tool_call_id,
            source_resource_ref=result.source_resource_ref,
            source_version=result.source_version,
            normalized_type="SHIPMENT_SUMMARY",
            normalized_value=summary,
            observed_at=result.observed_at,
            recorded_at=recorded_at,
            valid_until=result.observed_at + SHIPMENT_FRESHNESS_TTL,
            raw_result_ref=str(terminal.result_ref),
        )
        next_task = _project_task(
            task,
            state_version=task.state_version + 1,
            updated_at=recorded_at,
        )
        next_unit = _project_request_unit(
            request_unit,
            state_version=request_unit.state_version + 1,
            updated_at=recorded_at,
            observation_refs=(
                *request_unit.observation_refs,
                observation.observation_id,
            ),
        )
        written = await (
            self._runtime_record_port.save_shipment_observation_if_current(
                SaveShipmentObservationV2Command(
                    owner_scope=turn.owner_scope,
                    expected_task_record=task,
                    next_task_record=next_task,
                    expected_request_unit_record=request_unit,
                    next_request_unit_record=next_unit,
                    source_tool_call_record=terminal,
                    source_result_ref=terminal.result_ref,
                    source_result=result,
                    observation_record=observation,
                    trusted_acceptance_now=recorded_at,
                )
            )
        )
        if written is not Cycle2WriteResult.APPLIED:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=task,
                request_unit=request_unit,
            )
        assessment_closure = await (
            self._runtime_record_port.load_shipment_assessment_closure_for_owner(
                owner_scope=turn.owner_scope,
                task_id=next_task.task_id,
                request_unit_id=next_unit.request_unit_id,
                verified_order_target_ref=str(terminal.verified_target_ref),
                trusted_assessed_at=recorded_at,
            )
        )
        if type(assessment_closure) is not ShipmentAssessmentReadClosure:
            raise AgentRunExecutionError(
                "Shipment Assessment closure unavailable"
            )
        step = await self._steps.assess_and_render_shipment(
            run_id=turn.running_run.run_id,
            closure=assessment_closure,
            plan=_cycle2_shipment_presentation_plan(),
        )
        return await self._finalize_mapping(
            turn=turn,
            step=step,
            task=next_task,
            request_unit=next_unit,
        )

    async def _handle_continuation_turn(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        current_session: Cycle2CurrentSessionTaskClosure,
    ) -> AgentRunResult:
        try:
            proposal = await (
                self._request_understanding_provider.propose_cycle2_continuation(
                    turn.request_input
                )
            )
        except (
            ProviderProtocolError,
            RequestUnderstandingCandidateInvalidError,
        ):
            signal = (
                Cycle2MapperSignal.CANDIDATE_REFRESH_REQUIRED
                if current_session.current_task_record.status
                is TaskStatus.WAITING_USER
                else Cycle2MapperSignal.SEARCH_BINDING_CLARIFICATION
            )
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=signal,
                ),
                task=current_session.current_task_record,
                request_unit=current_session.current_request_unit_record,
            )
        if type(proposal) is not Cycle2InputCandidate:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY,
                ),
                task=current_session.current_task_record,
                request_unit=current_session.current_request_unit_record,
            )
        if proposal.name == "candidate_ordinal":
            return await self._continue_with_ordinal(
                command=command,
                turn=turn,
                current_session=current_session,
                proposal=proposal,
            )
        return await self._continue_with_binding(
            command=command,
            turn=turn,
            current_session=current_session,
            proposal=proposal,
        )

    async def _continue_with_binding(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        current_session: Cycle2CurrentSessionTaskClosure,
        proposal: Cycle2InputCandidate,
    ) -> AgentRunResult:
        bound_at = self._clock()
        try:
            decision = reduce_cycle2_continuation_candidate(
                request_input=turn.request_input,
                candidate=proposal,
                authoritative_messages={
                    turn.user_message.message_id: turn.user_message.content
                },
                customer_context=command.customer_context,
                current_task=current_session.current_task_record,
                current_request_unit=(
                    current_session.current_request_unit_record
                ),
                current_input_bindings=(
                    current_session.current_input_binding_records
                ),
                binding_id=self._uuid_factory(),
                now=bound_at,
            )
        except RequestProcessingError:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.SEARCH_BINDING_CLARIFICATION,
                ),
                task=current_session.current_task_record,
                request_unit=current_session.current_request_unit_record,
            )
        closure = await (
            self._runtime_record_port.load_continuation_input_binding_closure_for_owner(
                owner_scope=turn.owner_scope,
                conversation_id=turn.conversation.conversation_id,
                message_id=turn.user_message.message_id,
                task_id=current_session.current_task_record.task_id,
                request_unit_id=(
                    current_session.current_request_unit_record.request_unit_id
                ),
                trusted_now=bound_at,
            )
        )
        if closure is None:
            raise AgentRunExecutionError("continuation binding closure unavailable")
        current_task = closure.current_task_record
        current_unit = closure.current_request_unit_record
        next_task = _project_task(
            current_task,
            state_version=decision.result_task_state_version,
            updated_at=bound_at,
        )
        replaced = decision.input_binding.supersedes
        next_refs = (
            tuple(
                decision.input_binding.binding_id if ref == replaced else ref
                for ref in current_unit.input_binding_refs
            )
            if replaced is not None
            else (*current_unit.input_binding_refs, decision.input_binding.binding_id)
        )
        next_unit = _project_request_unit(
            current_unit,
            input_binding_refs=next_refs,
            state_version=decision.result_task_state_version,
            updated_at=bound_at,
        )
        write = await (
            self._runtime_record_port.apply_continuation_input_binding_if_current(
                ApplyContinuationInputBindingV2Command(
                    loaded_closure=closure,
                    new_input_binding_record=decision.input_binding,
                    next_task_record=next_task,
                    next_request_unit_record=next_unit,
                )
            )
        )
        if write is not Cycle2WriteResult.APPLIED:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=(
                        Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                    ),
                ),
                task=current_task,
                request_unit=current_unit,
            )
        next_bindings = tuple(
            binding
            for binding in closure.current_input_binding_records
            if binding.binding_id != replaced
        ) + (decision.input_binding,)
        direct_tool_name = (
            "get_shipment"
            if decision.input_binding.name == "shipment_not_received"
            or (
                decision.input_binding.name == "order_id"
                and bool(current_session.current_shipment_observation_records)
            )
            else (
                "get_order"
                if decision.input_binding.name == "order_id"
                else "search_orders"
            )
        )
        candidate_factory = (
            lambda tool_closure, model_call_id, manifest_id, _control_move: (
                self._route_continuation_candidate(
                    command=command,
                    turn=turn,
                    closure=tool_closure,
                    decision=decision,
                    tool_name=direct_tool_name,
                    model_call_id=model_call_id,
                    manifest_id=manifest_id,
                )
            )
        )
        if decision.input_binding.name == "product_description":
            return await self._search_orders(
                command=command,
                turn=turn,
                task=next_task,
                request_unit=next_unit,
                input_bindings=next_bindings,
                candidate_factory=candidate_factory,
            )
        if decision.input_binding.name == "shipment_not_received":
            return await self._get_shipment(
                command=command,
                turn=turn,
                task=next_task,
                request_unit=next_unit,
                candidate_factory=candidate_factory,
            )
        if decision.input_binding.name == "order_id":
            if direct_tool_name == "get_shipment":
                return await self._get_shipment(
                    command=command,
                    turn=turn,
                    task=next_task,
                    request_unit=next_unit,
                    candidate_factory=candidate_factory,
                )
            return await self._get_order(
                command=command,
                turn=turn,
                task=next_task,
                request_unit=next_unit,
                candidate_factory=candidate_factory,
            )
        raise AgentRunExecutionError("unsupported Cycle 2 continuation binding")

    def _route_continuation_candidate(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        closure: InitialToolCallV2ReadClosure,
        decision: Cycle2ContinuationBindingDecision,
        tool_name: str,
        model_call_id: UUID,
        manifest_id: UUID,
    ) -> Cycle2GatewayCandidate:
        if decision.input_binding.name in {"shipment_not_received", "order_id"}:
            if (
                len(closure.current_verified_order_targets) != 1
                or len(closure.current_target_observations) != 1
            ):
                raise AgentRunExecutionError(
                    "continuation Shipment target closure unavailable"
                )
            target = closure.current_verified_order_targets[0]
            target_observation = closure.current_target_observations[0]
        else:
            target = None
            target_observation = None
        if tool_name == "search_orders":
            arguments = {
                "product_description": decision.input_binding.normalized_value,
            }
        else:
            if target is None:
                raise AgentRunExecutionError(
                    "continuation verified Order target unavailable"
                )
            arguments = {"order_id": target.order_id}
        next_move = NextMove(
            kind=NextMoveKind.CALL_TOOL,
            requested_tool_name=tool_name,
            arguments=arguments,
            base_task_state_version=decision.result_task_state_version,
        )
        return route_cycle2_continuation_next_move(
            request_input=turn.request_input,
            decision=decision,
            next_move=next_move,
            customer_context=command.customer_context,
            current_task=closure.current_task_record,
            current_request_unit=closure.current_request_unit_record,
            current_input_bindings=closure.current_input_binding_records,
            verified_target=target,
            verified_target_observation=target_observation,
            model_call_id=model_call_id,
            context_manifest_id=manifest_id,
            trusted_now=closure.trusted_read_at,
        )

    async def _continue_with_ordinal(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        current_session: Cycle2CurrentSessionTaskClosure,
        proposal: Cycle2InputCandidate,
    ) -> AgentRunResult:
        selected_at = self._clock()
        try:
            claim = prepare_cycle2_ordinal_claim(
                request_input=turn.request_input,
                candidate=proposal,
                authoritative_messages={
                    turn.user_message.message_id: turn.user_message.content
                },
                customer_context=command.customer_context,
                current_task=current_session.current_task_record,
                current_request_unit=(
                    current_session.current_request_unit_record
                ),
                current_input_bindings=(
                    current_session.current_input_binding_records
                ),
                binding_id=self._uuid_factory(),
                now=selected_at,
            )
        except RequestProcessingError:
            return await self._finalize_mapping(
                turn=turn,
                step=self._step_for_signal(
                    run_id=turn.running_run.run_id,
                    signal=Cycle2MapperSignal.CANDIDATE_REFRESH_REQUIRED,
                ),
                task=current_session.current_task_record,
                request_unit=current_session.current_request_unit_record,
            )
        try:
            preparation = prepare_cycle2_ordinal_selection(
                request_input=turn.request_input,
                candidate=proposal,
                authoritative_messages={
                    turn.user_message.message_id: turn.user_message.content
                },
                customer_context=command.customer_context,
                current_conversation_id=turn.conversation.conversation_id,
                current_task=current_session.current_task_record,
                current_request_unit=(
                    current_session.current_request_unit_record
                ),
                current_input_bindings=(
                    current_session.current_input_binding_records
                ),
                current_candidate_sets=(
                    current_session.current_candidate_set_records
                ),
                pending_candidate_set_ref=(
                    current_session.current_candidate_set_records[0].candidate_set_id
                    if current_session.current_candidate_set_records
                    else None
                ),
                superseded_candidate_set_refs=(
                    current_session.superseded_candidate_set_refs
                ),
                existing_selection_records=(
                    current_session.existing_selection_records
                ),
                binding_id=claim.ordinal_input_binding.binding_id,
                now=selected_at,
            )
        except (RequestProcessingError, IndexError):
            return await self._persist_rejected_ordinal_claim(
                turn=turn,
                current_session=current_session,
                claim=claim,
                reason=self._ordinal_rejection_reason(
                    current_session=current_session,
                    ordinal=claim.selection_request.ordinal,
                    trusted_now=selected_at,
                ),
            )
        selection_closure = await (
            self._runtime_record_port.load_order_candidate_selection_closure_for_owner(
                owner_scope=turn.owner_scope,
                conversation_id=turn.conversation.conversation_id,
                task_id=current_session.current_task_record.task_id,
                request_unit_id=(
                    current_session.current_request_unit_record.request_unit_id
                ),
                selection_request=preparation.selection_request,
                trusted_now=selected_at,
            )
        )
        if type(selection_closure) is not OrderCandidateSelectionReadClosure:
            return await self._persist_rejected_ordinal_claim(
                turn=turn,
                current_session=current_session,
                claim=claim,
                reason=self._ordinal_rejection_reason(
                    current_session=current_session,
                    ordinal=claim.selection_request.ordinal,
                    trusted_now=selected_at,
                ),
            )
        current_task = selection_closure.current_task_record
        current_unit = selection_closure.current_request_unit_record
        selected_entry = tuple(
            entry
            for entry in selection_closure.current_candidate_set_record.ordered_candidates
            if entry.ordinal == preparation.selection_request.ordinal
        )
        if len(selected_entry) != 1:
            raise AgentRunExecutionError("selected CandidateSet entry unavailable")
        issued_target = IssuedSelectedTargetRef.fresh()
        selection = OrderCandidateSelectionRecord(
            selection_id=self._uuid_factory(),
            private_owner_scope_ref=turn.owner_scope.customer_id,
            conversation_id=turn.conversation.conversation_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            source_message_ref=turn.user_message.message_id,
            ordinal_input_binding_ref=(
                preparation.ordinal_input_binding.binding_id
            ),
            candidate_set_ref=(
                selection_closure.current_candidate_set_record.candidate_set_id
            ),
            candidate_set_version=(
                selection_closure.current_candidate_set_record.candidate_set_version
            ),
            search_observation_ref=(
                selection_closure.search_observation_record.observation_id
            ),
            search_observation_record_schema_version=(
                selection_closure.search_observation_record.record_schema_version
            ),
            observation_candidate_ref=(
                selected_entry[0].observation_candidate_ref
            ),
            candidate_source_version=selected_entry[0].candidate_source_version,
            owner_scoped_order_target_ref=(
                selection_closure.resolved_owner_scoped_order_target_ref
            ),
            selected_target_ref=str(issued_target.selected_target_ref),
            base_task_state_version=current_task.state_version,
            result_task_state_version=current_task.state_version + 1,
            selected_at=selected_at,
        )
        next_task = _project_task(
            current_task,
            status=TaskStatus.ACTIVE,
            state_version=current_task.state_version + 1,
            updated_at=selected_at,
        )
        next_unit = _project_request_unit(
            current_unit,
            input_binding_refs=(
                *current_unit.input_binding_refs,
                preparation.ordinal_input_binding.binding_id,
            ),
            open_questions=(),
            status=TaskStatus.ACTIVE,
            state_version=current_unit.state_version + 1,
            updated_at=selected_at,
        )
        selection_command = build_order_candidate_selection_v2_command(
            loaded_closure=selection_closure,
            ordinal_input_binding_record=(
                preparation.ordinal_input_binding
            ),
            issued_selected_target=issued_target,
            next_task_record=next_task,
            next_request_unit_record=next_unit,
            selection_record=selection,
            closed_pending_candidate_set_ref=(
                selection_closure.pending_candidate_set_ref
            ),
        )
        applied = await self._steps.apply_ordinal_selection(
            run_id=turn.running_run.run_id,
            command=selection_command,
        )
        if applied.outbound_result is not None:
            return await self._finalize_mapping(
                turn=turn,
                step=applied,
                task=current_task,
                request_unit=current_unit,
            )
        return await self._get_order(
            command=command,
            turn=turn,
            task=next_task,
            request_unit=next_unit,
            candidate_factory=lambda closure, model_call_id, manifest_id, control_move: (
                self._route_selected_candidate(
                    command=command,
                    turn=turn,
                    closure=closure,
                    next_move=self._require_control_move(control_move),
                    candidate_set=(
                        selection_closure.current_candidate_set_record
                    ),
                    selection=selection,
                    model_call_id=model_call_id,
                    manifest_id=manifest_id,
                )
            ),
            control_purpose=Cycle2ControlPurpose.PROPOSE_GET_ORDER,
        )

    @staticmethod
    def _ordinal_rejection_reason(
        *,
        current_session: Cycle2CurrentSessionTaskClosure,
        ordinal: int,
        trusted_now: datetime,
    ) -> Cycle2OrdinalSelectionRejectionReason:
        hinted = current_session.ordinal_selection_rejection_hint
        if hinted is not None:
            return hinted
        candidate_sets = current_session.current_candidate_set_records
        if len(candidate_sets) != 1:
            if (
                len(candidate_sets) == 0
                and current_session.superseded_candidate_set_refs
            ):
                return Cycle2OrdinalSelectionRejectionReason.SUPERSEDED
            return (
                Cycle2OrdinalSelectionRejectionReason.CURRENT_SET_CARDINALITY_NOT_ONE
            )
        candidate_set = candidate_sets[0]
        if candidate_set.candidate_set_id in set(
            current_session.superseded_candidate_set_refs
        ):
            return Cycle2OrdinalSelectionRejectionReason.SUPERSEDED
        if trusted_now >= candidate_set.valid_until:
            return Cycle2OrdinalSelectionRejectionReason.EXPIRED
        if ordinal not in {
            entry.ordinal for entry in candidate_set.ordered_candidates
        }:
            return Cycle2OrdinalSelectionRejectionReason.OUT_OF_RANGE
        return (
            Cycle2OrdinalSelectionRejectionReason.CURRENT_SET_CARDINALITY_NOT_ONE
        )

    async def _persist_rejected_ordinal_claim(
        self,
        *,
        turn: _Cycle2Turn,
        current_session: Cycle2CurrentSessionTaskClosure,
        claim: Cycle2OrdinalClaimPreparation,
        reason: Cycle2OrdinalSelectionRejectionReason,
    ) -> AgentRunResult:
        closure = await (
            self._runtime_record_port.load_continuation_input_binding_closure_for_owner(
                owner_scope=turn.owner_scope,
                conversation_id=turn.conversation.conversation_id,
                message_id=turn.user_message.message_id,
                task_id=current_session.current_task_record.task_id,
                request_unit_id=(
                    current_session.current_request_unit_record.request_unit_id
                ),
                trusted_now=claim.ordinal_input_binding.created_at,
            )
        )
        if closure is None:
            raise AgentRunExecutionError(
                "rejected ordinal binding closure unavailable"
            )
        rejected = reject_cycle2_ordinal_selection(
            claim=claim,
            reason=reason,
        )
        current_task = closure.current_task_record
        current_unit = closure.current_request_unit_record
        next_task = _project_task(
            current_task,
            state_version=rejected.result_task_state_version,
            updated_at=closure.trusted_now,
        )
        next_unit = _project_request_unit(
            current_unit,
            input_binding_refs=(
                *current_unit.input_binding_refs,
                rejected.ordinal_input_binding.binding_id,
            ),
            state_version=rejected.result_task_state_version,
            updated_at=closure.trusted_now,
        )
        written = await (
            self._runtime_record_port.apply_continuation_input_binding_if_current(
                ApplyContinuationInputBindingV2Command(
                    loaded_closure=closure,
                    new_input_binding_record=rejected.ordinal_input_binding,
                    next_task_record=next_task,
                    next_request_unit_record=next_unit,
                    rejected_ordinal_selection=rejected,
                )
            )
        )
        terminal_task = next_task if written is Cycle2WriteResult.APPLIED else current_task
        terminal_unit = next_unit if written is Cycle2WriteResult.APPLIED else current_unit
        return await self._finalize_mapping(
            turn=turn,
            step=self._step_for_signal(
                run_id=turn.running_run.run_id,
                signal=Cycle2MapperSignal.CANDIDATE_REFRESH_REQUIRED,
            ),
            task=terminal_task,
            request_unit=terminal_unit,
        )

    def _route_selected_candidate(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        closure: InitialToolCallV2ReadClosure,
        next_move: NextMove,
        candidate_set: OrderCandidateSetRecord,
        selection: OrderCandidateSelectionRecord,
        model_call_id: UUID,
        manifest_id: UUID,
    ) -> Cycle2GatewayCandidate:
        targets = tuple(
            target
            for target in closure.current_verified_order_targets
            if str(target.verified_target_ref) == selection.selected_target_ref
        )
        if len(targets) != 1:
            raise AgentRunExecutionError("selected target facts unavailable")
        return route_cycle2_selected_next_move(
            request_input=turn.request_input,
            next_move=next_move,
            customer_context=command.customer_context,
            current_conversation_id=turn.conversation.conversation_id,
            current_task=closure.current_task_record,
            current_request_unit=closure.current_request_unit_record,
            current_input_bindings=closure.current_input_binding_records,
            candidate_set=candidate_set,
            selection_record=selection,
            verified_target=targets[0],
            model_call_id=model_call_id,
            context_manifest_id=manifest_id,
            trusted_now=closure.trusted_read_at,
        )

    async def _execute_tool(
        self,
        *,
        command: AgentRunCommand,
        turn: _Cycle2Turn,
        task_id: UUID,
        request_unit_id: UUID,
        candidate_factory: Callable[
            [InitialToolCallV2ReadClosure, UUID, UUID, NextMove | None],
            Cycle2GatewayCandidate,
        ],
        control_purpose: Cycle2ControlPurpose | None = None,
        closure_unavailable_is_control_error: bool = False,
    ) -> Cycle2ReadToolExecution | AgentRunResult:
        closure = await (
            self._runtime_record_port.load_initial_tool_call_v2_closure_for_owner(
                owner_scope=turn.owner_scope,
                task_id=task_id,
                request_unit_id=request_unit_id,
                trusted_read_at=self._clock(),
            )
        )
        if type(closure) is not InitialToolCallV2ReadClosure:
            if closure_unavailable_is_control_error:
                raise _Cycle2ControlProtocolError
            raise AgentRunExecutionError("current ToolCall closure unavailable")
        model_call_id = self._uuid_factory()
        manifest_id = self._uuid_factory()
        control_move = (
            None
            if control_purpose is None
            else await self._materialize_tool_control(
                turn=turn,
                purpose=control_purpose,
                closure=closure,
            )
        )
        candidate = candidate_factory(
            closure,
            model_call_id,
            manifest_id,
            control_move,
        )
        manifest = ContextManifest(
            context_manifest_id=manifest_id,
            run_id=turn.running_run.run_id,
            model_call_id=model_call_id,
            tool_registry_version=self._registry_snapshot.tool_registry_version,
            model_visible_toolset_hash=(
                self._registry_snapshot.model_visible_toolset_hash
            ),
            selected_message_refs=(turn.user_message.message_id,),
            task_state_ref_and_version=(
                None
                if candidate.proposed_base_task_state_version is None
                else TaskStateRefAndVersion(
                    task_id=closure.current_task_record.task_id,
                    state_version=candidate.proposed_base_task_state_version,
                )
            ),
            observation_refs_and_versions=tuple(
                VersionedRecordRef(
                    record_ref=observation.observation_ref,
                    version=observation.observation_version,
                )
                for observation in closure.current_target_observations
            ),
            evidence_refs_and_versions=(),
            action_record_refs=(),
            redaction_policy_version=self._redaction_policy_version,
            truncation_decisions=(),
            token_counts=TokenCounts(
                input_tokens=None,
                output_tokens=None,
            ),
            assembled_at=closure.trusted_read_at,
        )
        await self._context_record_port.save_context_manifest(manifest)
        binding_facts = tuple(
            Cycle2AcceptedBindingFacts(
                binding_id=binding.binding_id,
                private_owner_scope_ref=turn.owner_scope.customer_id,
                owner_customer_id=turn.owner_scope.customer_id,
                task_id=closure.current_task_record.task_id,
                request_unit_id=(
                    closure.current_request_unit_record.request_unit_id
                ),
                task_state_version=closure.current_task_record.state_version,
                name=binding.name,
                normalized_value=binding.normalized_value,
                authority=binding.authority,
                validation_status=binding.validation_status.value,
                confirmed_by_user=binding.confirmed_by_user,
                source_refs=binding.source_refs,
                superseded_by=None,
            )
            for binding in closure.current_input_binding_records
        )
        loaded_gateway = Cycle2GatewayLoadedClosure(
            customer_context=CustomerContext(
                provenance=command.customer_context.provenance,
                subject_ref=command.customer_context.subject_ref,
                customer_id=command.customer_context.customer_id,
                auth_scopes=command.customer_context.auth_scopes,
                authenticated_at=command.customer_context.authenticated_at,
                session_ref_hash=command.customer_context.session_ref_hash,
            ),
            private_owner_scope_ref=turn.owner_scope.customer_id,
            current_task=closure.current_task_record,
            current_request_unit=closure.current_request_unit_record,
            current_input_bindings=binding_facts,
            current_verified_order_targets=(
                closure.current_verified_order_targets
            ),
            current_target_observations=closure.current_target_observations,
            registry_snapshot=self._registry_snapshot,
            context_manifest=manifest,
            budget=Cycle2GatewayBudgetFacts(
                run_id=turn.running_run.run_id,
                context_manifest_id=manifest_id,
                tool_registry_version=(
                    self._registry_snapshot.tool_registry_version
                ),
                model_visible_toolset_hash=(
                    self._registry_snapshot.model_visible_toolset_hash
                ),
                closure_complete=True,
                tool_calls_used=len(turn.tool_progress),
                max_tool_calls=3,
                active_tool_calls=0,
                accepted_parallel_tool_calls=0,
                remaining_run_time_budget_ms=self._gateway_run_budget_ms,
            ),
            progress_snapshot=Cycle2GatewayProgressSnapshot(
                run_id=turn.running_run.run_id,
                context_manifest_id=manifest_id,
                tool_registry_version=(
                    self._registry_snapshot.tool_registry_version
                ),
                model_visible_toolset_hash=(
                    self._registry_snapshot.model_visible_toolset_hash
                ),
                task_state_version=closure.current_task_record.state_version,
                history_complete=True,
                prior_tool_steps=tuple(
                    progress.model_copy(
                        update={
                            "context_manifest_id": manifest_id,
                            "task_state_version": (
                                closure.current_task_record.state_version
                            ),
                        }
                    )
                    for progress in turn.tool_progress
                ),
            ),
        )
        gate = evaluate_cycle2_control_gateway(
            candidate=candidate,
            loaded_closure=loaded_gateway,
            gate_decision_id=self._uuid_factory(),
            provider_tool_call_id=None,
            decided_at=closure.trusted_read_at,
        )
        if type(gate) is not GateDecisionV2:
            raise AgentRunExecutionError("Cycle 2 Gateway result is not exact")
        if gate.decision is GateDecisionValue.REJECT:
            return self._deterministic_renderer.map_result(
                run_id=turn.running_run.run_id,
                stop_reason=StopReason.GATE_REJECTED,
            )
        authorized = build_cycle2_authorized_tool_command(
            gate_decision=gate,
            candidate=candidate,
            registry_snapshot_ref=self._registry_snapshot.tool_registry_version,
            trusted_context_ref=str(manifest.context_manifest_id),
        )
        created = ToolCallRecordV2(
            tool_call_id=self._uuid_factory(),
            run_id=turn.running_run.run_id,
            task_id=closure.current_task_record.task_id,
            request_unit_id=(
                closure.current_request_unit_record.request_unit_id
            ),
            model_call_id=model_call_id,
            context_manifest_id=manifest_id,
            gate_decision_id=gate.gate_decision_id,
            provider_tool_call_id=gate.provider_tool_call_id,
            canonical_tool_name=Cycle2ToolName(
                authorized.canonical_tool_name
            ),
            tool_registry_version=self._registry_snapshot.tool_registry_version,
            private_owner_scope_ref=turn.owner_scope.customer_id,
            validated_task_state_version=(
                closure.current_task_record.state_version
            ),
            argument_binding_refs=authorized.argument_binding_refs,
            verified_target_ref=authorized.verified_target_ref,
            effect=ToolEffect.READ,
            attempt_count=0,
            attempts=(),
            status=ToolCallStatus.CREATED,
            started_at=closure.trusted_read_at,
        )
        execution = await self._read_tool_executor.execute_with_result(
            create_command=CreateToolCallV2Command(
                loaded_closure=closure,
                gateway_candidate=candidate,
                gate_decision=gate,
                authorized_tool_command=authorized,
                created_record=created,
            )
        )
        if execution.terminal_tool_call.status in {
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.FAILED,
            ToolCallStatus.TIMED_OUT,
            ToolCallStatus.INTERRUPTED,
        }:
            turn.tool_progress.append(
                Cycle2ToolProgressFact(
                    tool_call_id=created.tool_call_id,
                    run_id=turn.running_run.run_id,
                    context_manifest_id=manifest_id,
                    tool_registry_version=(
                        self._registry_snapshot.tool_registry_version
                    ),
                    model_visible_toolset_hash=(
                        self._registry_snapshot.model_visible_toolset_hash
                    ),
                    canonical_tool_name=created.canonical_tool_name,
                    validated_arguments=authorized.validated_arguments,
                    task_state_version=created.validated_task_state_version,
                    argument_binding_refs=created.argument_binding_refs,
                    verified_target_ref=created.verified_target_ref,
                )
            )
        return execution

    async def _finish_fixed_phase1(
        self,
        *,
        turn: _Cycle2Turn,
        stop_reason_v1: StopReason,
        stop_reason_v2: StopReasonV2,
        task: TaskRecord | None = None,
        request_unit: RequestUnitRecord | None = None,
    ) -> AgentRunResult:
        result = self._deterministic_renderer.map_result(
            run_id=turn.running_run.run_id,
            stop_reason=stop_reason_v1,
        )
        return await self._finalize(
            turn=turn,
            result=result,
            stop_reason=stop_reason_v2,
            task=task,
            request_unit=request_unit,
        )

    async def _finalize_mapping(
        self,
        *,
        turn: _Cycle2Turn,
        step: Cycle2RuntimeStep,
        task: TaskRecord,
        request_unit: RequestUnitRecord,
        consume_control: bool = True,
    ) -> AgentRunResult:
        mapping = step.mapping
        result = step.outbound_result
        signal = step.cycle2_signal
        if (
            type(mapping) is not Cycle2ResultMapping
            or mapping.disposition is not MapperDisposition.EMIT
            or mapping.stop_reason is None
            or type(result) is not AgentRunResult
            or type(signal) is not Cycle2MapperSignal
        ):
            raise AgentRunExecutionError("Cycle 2 mapping is not outbound")
        if consume_control:
            try:
                await self._propose_cycle2_control(
                    turn=turn,
                    purpose=self._terminal_control_purpose(signal),
                )
            except _Cycle2ControlProtocolError:
                signal = Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY
                mapping = self._steps.result_mapper.map_cycle2(signal)
                result = self._deterministic_renderer.map_cycle2_result(
                    run_id=turn.running_run.run_id,
                    mapping=mapping,
                )
        return await self._finalize(
            turn=turn,
            result=result,
            stop_reason=mapping.stop_reason,
            task=task,
            request_unit=request_unit,
            cycle2_signal=signal,
            response_policy=mapping.response_policy,
        )

    async def _finalize_imported(
        self,
        *,
        turn: _Cycle2Turn,
        result: AgentRunResult,
        stop_reason: StopReasonV2,
        task: TaskRecord | None,
        request_unit: RequestUnitRecord | None,
        reference: ImportedMapperReference,
        response_policy: ResponsePolicy,
        consume_control: bool = True,
    ) -> AgentRunResult:
        if consume_control:
            try:
                await self._propose_cycle2_control(
                    turn=turn,
                    purpose=Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE,
                )
            except _Cycle2ControlProtocolError:
                return await self._finalize_mapping(
                    turn=turn,
                    step=self._step_for_signal(
                        run_id=turn.running_run.run_id,
                        signal=Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY,
                    ),
                    task=task,
                    request_unit=request_unit,
                    consume_control=False,
                )
        actual_reference = self._steps.map_imported_phase1(reference)
        return await self._finalize(
            turn=turn,
            result=result,
            stop_reason=stop_reason,
            task=task,
            request_unit=request_unit,
            imported_reference=actual_reference,
            response_policy=response_policy,
        )

    async def _finalize(
        self,
        *,
        turn: _Cycle2Turn,
        result: AgentRunResult,
        stop_reason: StopReasonV2,
        task: TaskRecord | None,
        request_unit: RequestUnitRecord | None,
        imported_reference: ImportedMapperReference | None = None,
        cycle2_signal: Cycle2MapperSignal | None = None,
        response_policy: ResponsePolicy | None = None,
    ) -> AgentRunResult:
        completed_at = self._clock()
        terminal_run = _project_cycle2_run(
            turn.running_run,
            status=AgentRunStatusV2.COMPLETED,
            completed_at=completed_at,
            stop_reason=stop_reason,
        )
        terminal_link = (
            None
            if turn.active_link is None
            else RunTaskLinkRecordV2(
                run_id=turn.running_run.run_id,
                task_id=turn.active_link.task_id,
                base_task_state_version=(
                    turn.active_link.base_task_state_version
                ),
                result_task_state_version=(
                    None if task is None else task.state_version
                ),
            )
        )
        assistant_message = MessageRecord(
            schema_version=_MESSAGE_SCHEMA_VERSION,
            message_id=self._uuid_factory(),
            conversation_id=turn.conversation.conversation_id,
            direction=MessageDirection.ASSISTANT,
            content=result.message,
            received_at=completed_at,
        )
        stopped = TraceEventV2(
            trace_event_id=self._uuid_factory(),
            event_type=TraceEventType.RUN_STOPPED,
            occurred_at=completed_at,
            run_id=turn.running_run.run_id,
            user_outcome=result.outcome,
            stop_reason=stop_reason,
        )
        finalized = await (
            self._runtime_record_port.finalize_cycle2_run_if_current(
                FinalizeCycle2RunCommand(
                    owner_scope=turn.owner_scope,
                    expected_running_run_record=turn.running_run,
                    expected_active_run_task_link_record=turn.active_link,
                    current_task_record=task,
                    current_request_unit_record=request_unit,
                    terminal_run_record=terminal_run,
                    terminal_run_task_link_record=terminal_link,
                    terminal_result=result,
                    assistant_message_record=assistant_message,
                    ordinary_trace_records=(stopped,),
                )
            )
        )
        if finalized is not Cycle2WriteResult.APPLIED:
            raise AgentRunExecutionError("Cycle 2 Run finalization conflict")
        evidence = await (
            self._runtime_record_port.load_cycle2_exact_run_evidence_for_owner(
                owner_scope=turn.owner_scope,
                run_id=turn.running_run.run_id,
            )
        )
        if (
            evidence is None
            or evidence.owner_scope != turn.owner_scope
            or evidence.run_record != terminal_run
            or evidence.terminal_result != result
            or assistant_message not in evidence.message_records
            or stopped not in evidence.trace_records
        ):
            raise AgentRunExecutionError("terminal Cycle 2 evidence unavailable")
        observation: Cycle2ExecutionOutcomeObservationV1 | None = None
        if imported_reference is not None:
            if cycle2_signal is not None or response_policy is None:
                raise AgentRunExecutionError("imported mapper observation mismatch")
            observation = self._steps.result_mapper.observe_imported(
                run_id=turn.running_run.run_id,
                reference=imported_reference,
                observed_outcome=result.outcome,
                stop_reason=stop_reason,
                response_policy=response_policy,
                agent_result_emitted=True,
            )
        elif cycle2_signal is not None:
            if response_policy is None:
                raise AgentRunExecutionError("Cycle 2 mapper observation mismatch")
            observation = self._steps.result_mapper.observe_cycle2(
                run_id=turn.running_run.run_id,
                signal=cycle2_signal,
                observed_outcome=result.outcome,
                stop_reason=stop_reason,
                response_policy=response_policy,
                agent_result_emitted=True,
            )
        elif response_policy is not None:
            raise AgentRunExecutionError("mapper observation source missing")
        if observation is not None:
            self._execution_outcome_observer.observe_cycle2_execution_outcome(
                observation
            )
        return result
