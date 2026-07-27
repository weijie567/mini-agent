"""Application orchestration for the first deterministic E2E-01 thin slice."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mini_agent.application.deterministic_renderer import (
    DeterministicRenderer,
    RendererInvariantError,
)
from mini_agent.application.ports import (
    ConversationRecordPort,
    ModelProvider,
    ModelVisibleToolsetArtifactPort,
    RuntimeRecordPort,
)
from mini_agent.application.read_tool_executor import (
    ReadToolExecution,
    ReadToolExecutor,
)
from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateInitialTaskGraphCommand,
    CreateRequestUnitCommand,
    CreateRunCommand,
    CreateRunTaskLinkCommand,
    CreateTaskCommand,
    FinalizeRunCommand,
    InsertOnlyWriteResult,
    MessageDirection,
    MessageRecord,
    ProviderProtocolError,
    RunTaskLinkRecord,
    SaveInputBindingCommand,
    SaveRequestUnderstandingCommand,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.control_gateway import (
    evaluate_control_gateway,
    resolve_validated_get_order_registration,
)
from mini_agent.core.memory import (
    ContextManifest,
    TaskStateRefAndVersion,
    TokenCounts,
    VersionedRecordRef,
)
from mini_agent.core.order import GetOrderOutcome
from mini_agent.core.presentation import PresentationInput, PresentationPurpose
from mini_agent.core.presentation_policy import (
    PresentationPolicyError,
    validate_presentation_plan,
)
from mini_agent.core.request_processing import (
    InitialRequestDecision,
    RequestProcessingError,
    revalidate_next_move,
    validate_and_reduce_initial_request,
)
from mini_agent.core.request_understanding import RequestUnderstandingInput
from mini_agent.core.task_state import (
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.tool_system import (
    AuthorizedToolCommand,
    GateDecision,
    GateDecisionValue,
    RegistrySnapshot,
    ToolCallStatus,
    ToolResultOutcome,
)
from mini_agent.core.trace import (
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEvent,
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
        task: TaskRecord,
        request_unit: RequestUnitRecord,
    ) -> Awaitable[None] | None: ...


async def _noop_after_revalidation(
    task: TaskRecord,
    request_unit: RequestUnitRecord,
) -> None:
    del task, request_unit


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
        model_provider: ModelProvider,
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
            context_manifest_id=manifest.context_manifest_id,
            tool_registry_version=manifest.tool_registry_version,
            model_visible_toolset_hash=manifest.model_visible_toolset_hash,
        )
        return manifest

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
            message_id=user_message.message_id,
        )
        request = RequestUnderstandingInput(
            run_id=running_run.run_id,
            message_ref=user_message.message_id,
            original_query=command.message,
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
        try:
            output = await self._model_provider.propose_next_move(request)
        except ProviderProtocolError:
            return await self._finish_without_task(
                running_run=running_run,
                conversation=conversation,
                stop_reason=StopReason.PROVIDER_PROTOCOL_ERROR,
                failure_state=failure_state,
            )

        try:
            decision = validate_and_reduce_initial_request(
                output=output,
                current_message_ref=user_message.message_id,
                current_message=command.message,
                customer_context=command.customer_context,
                run_id=running_run.run_id,
                accepted_delta_id=self._uuid_factory(),
                task_id=self._uuid_factory(),
                request_unit_id=self._uuid_factory(),
                binding_id=self._uuid_factory(),
                next_move_candidate_ref=self._uuid_factory(),
                now=self._clock(),
            )
        except RequestProcessingError:
            return await self._finish_without_task(
                running_run=running_run,
                conversation=conversation,
                stop_reason=StopReason.INPUT_INVALID,
                failure_state=failure_state,
            )

        initial_run_task_link = RunTaskLinkRecord(
            schema_version=_RUN_TASK_LINK_SCHEMA_VERSION,
            run_id=running_run.run_id,
            task_id=decision.task.task_id,
            base_task_state_version=None,
        )
        initial_graph = CreateInitialTaskGraphCommand(
            owner_scope=owner_scope,
            expected_conversation_record=conversation,
            expected_message_record=user_message,
            expected_active_run_record=running_run,
            request_understanding=SaveRequestUnderstandingCommand(
                record=decision.request_understanding,
                accepted_deltas=(decision.accepted_delta,),
            ),
            initial_task=CreateTaskCommand(initial_record=decision.task),
            initial_request_unit=CreateRequestUnitCommand(
                initial_record=decision.request_unit
            ),
            input_bindings=(
                SaveInputBindingCommand(
                    record=decision.input_binding,
                    request_unit_id=decision.request_unit.request_unit_id,
                ),
            ),
            conversation_task_link=ConversationTaskLinkRecord(
                schema_version=_CONVERSATION_TASK_LINK_SCHEMA_VERSION,
                conversation_id=conversation.conversation_id,
                task_id=decision.task.task_id,
                link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
                linked_at=self._clock(),
            ),
            run_task_link=CreateRunTaskLinkCommand(
                active_record=initial_run_task_link
            ),
        )
        graph_result = (
            await self._runtime_record_port.create_initial_task_graph_if_current(
                initial_graph
            )
        )
        if graph_result is not ConditionalWriteResult.APPLIED:
            raise AgentRunExecutionError("initial Task graph conflict")
        failure_state.active_link = initial_run_task_link
        failure_state.result_task = decision.task

        await self._append_initial_decision_trace(
            run_id=running_run.run_id,
            model_call_id=first_model_call_id,
            context_manifest_id=first_manifest.context_manifest_id,
            decision=decision,
        )
        revalidated_move = revalidate_next_move(
            decision=decision,
            current_task=decision.task,
            current_request_unit=decision.request_unit,
            current_input_binding=decision.input_binding,
        )
        await self._append_trace(
            event_type=TraceEventType.NEXT_MOVE_REVALIDATED,
            run_id=running_run.run_id,
            task_id=decision.task.task_id,
            request_unit_id=decision.request_unit.request_unit_id,
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
            decision.task,
            decision.request_unit,
        )
        if inspect.isawaitable(hook_result):
            await hook_result
        current_task = await self._runtime_record_port.load_task_for_owner(
            owner_scope=owner_scope,
            task_id=decision.task.task_id,
        )
        current_unit = (
            await self._runtime_record_port.load_request_unit_for_owner(
                owner_scope=owner_scope,
                request_unit_id=decision.request_unit.request_unit_id,
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
            current_input_binding=decision.input_binding,
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
                "order_id": decision.input_binding.normalized_value
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
        if observation is None:
            raise AgentRunExecutionError("FOUND read missing Observation")
        await self._append_trace(
            event_type=TraceEventType.OBSERVATION_RECORDED,
            run_id=running_run.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            tool_call_id=execution.terminal_tool_call.tool_call_id,
            observation_ref=observation.observation_id,
        )
        second_model_call_id = self._uuid_factory()
        second_manifest = await self._save_manifest(
            run_id=running_run.run_id,
            model_call_id=second_model_call_id,
            message_id=user_message.message_id,
            task=current_task,
            observation_ref=VersionedRecordRef(
                record_ref=observation.observation_id,
                version=(
                    observation.source_version
                    or "order-observation.p0.v1"
                ),
            ),
        )
        try:
            plan = await self._model_provider.plan_presentation(
                PresentationInput(
                    purpose=PresentationPurpose.ORDER_STATUS_SUMMARY,
                    order_summary=observation.normalized_value,
                )
            )
        except ProviderProtocolError:
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
                failure_state=failure_state,
            )
        await self._append_trace(
            event_type=TraceEventType.RESPONSE_RENDERED,
            run_id=running_run.run_id,
            task_id=current_task.task_id,
            request_unit_id=current_unit.request_unit_id,
            observation_ref=observation.observation_id,
            presentation_plan_ref=presentation_plan_ref,
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
        decision: InitialRequestDecision,
    ) -> None:
        await self._append_trace(
            event_type=TraceEventType.NEXT_MOVE_PROPOSED,
            run_id=run_id,
            message_ref=decision.request_understanding.message_ref,
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
            message_ref=decision.request_understanding.message_ref,
            accepted_delta_ref=decision.accepted_delta.accepted_delta_id,
        )
        await self._append_trace(
            event_type=TraceEventType.TASK_DELTA_ACCEPTED,
            run_id=run_id,
            message_ref=decision.request_understanding.message_ref,
            accepted_delta_ref=decision.accepted_delta.accepted_delta_id,
            task_id=decision.task.task_id,
            request_unit_id=decision.request_unit.request_unit_id,
        )
        await self._append_trace(
            event_type=TraceEventType.INPUT_BINDING_RECORDED,
            run_id=run_id,
            task_id=decision.task.task_id,
            request_unit_id=decision.request_unit.request_unit_id,
            input_binding_ref=decision.input_binding.binding_id,
        )
        await self._append_trace(
            event_type=TraceEventType.TASK_STATE_CHANGED,
            run_id=run_id,
            task_id=decision.task.task_id,
            request_unit_id=decision.request_unit.request_unit_id,
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
        rendered_message: str | None = None,
        failure_state: _RunFailureState | None = None,
    ) -> AgentRunResult:
        result = self._deterministic_renderer.map_result(
            run_id=running_run.run_id,
            stop_reason=stop_reason,
            rendered_message=rendered_message,
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
