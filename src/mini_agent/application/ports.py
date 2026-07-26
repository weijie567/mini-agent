"""Core-facing Ports; concrete SDK, HTTP, and database code belongs elsewhere."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mini_agent.application.records import (
    ConditionalWriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateRequestUnitCommand,
    CreateRunCommand,
    CreateRunTaskLinkCommand,
    CreateTaskCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    FinalizeToolCallCommand,
    InsertOnlyWriteResult,
    InterruptToolCallForRecoveryCommand,
    MarkRunIncompleteForRecoveryCommand,
    MessageRecord,
    NonEmptyString,
    PositiveAttempt,
    PositiveStateVersion,
    RecoveryWriteResult,
    RunTaskLinkRecord,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
    VersionedWriteResult,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import ContextManifest, OrderObservation
from mini_agent.core.order import GetOrderQuery, GetOrderResult
from mini_agent.core.presentation import (
    PresentationInput,
    PresentationPlan,
)
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
)
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    InputBinding,
    RequestUnderstandingRecord,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
)
from mini_agent.core.tool_system import (
    GateDecision,
    ModelVisibleToolsetArtifact,
    ToolCallRecord,
)
from mini_agent.core.trace import AgentRunRecord, TraceEvent


@runtime_checkable
class SessionAuthPort(Protocol):
    """Resolve an opaque session through trusted server-side authentication."""

    async def authenticate(self, opaque_session_id: str) -> CustomerContext | None: ...


@runtime_checkable
class ModelProvider(Protocol):
    """Return candidates only; implementations cannot mutate state or run Tools."""

    async def propose_next_move(
        self, request: RequestUnderstandingInput
    ) -> RequestUnderstandingOutput: ...

    async def plan_presentation(
        self, request: PresentationInput
    ) -> PresentationPlan: ...


@runtime_checkable
class GetOrderPort(Protocol):
    """Perform one customer-scoped order lookup."""

    async def get_order(self, query: GetOrderQuery) -> GetOrderResult: ...


@runtime_checkable
class ModelVisibleToolsetArtifactPort(Protocol):
    """Persist and resolve the safe content-addressed Toolset artifact."""

    async def put_toolset_artifact(
        self, artifact: ModelVisibleToolsetArtifact
    ) -> None: ...

    async def get_toolset_artifact(
        self, model_visible_toolset_hash: str
    ) -> ModelVisibleToolsetArtifact | None: ...


@runtime_checkable
class ConversationRecordPort(Protocol):
    """Application-owned Conversation store with trusted-owner reads."""

    async def save_conversation(self, record: ConversationRecord) -> None: ...

    async def append_message(self, record: MessageRecord) -> None: ...

    async def save_conversation_task_link(
        self, record: ConversationTaskLinkRecord
    ) -> None: ...

    async def load_conversation_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
    ) -> ConversationRecord | None:
        """Return ``None`` for both absent and unauthorized Conversations."""
        ...

    async def list_messages_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        limit: int,
    ) -> tuple[MessageRecord, ...]:
        """Return an empty tuple for absent or unauthorized Conversations."""
        ...

    async def list_conversation_task_links_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
    ) -> tuple[ConversationTaskLinkRecord, ...]:
        """Return an empty tuple for absent or unauthorized Conversations."""
        ...


@runtime_checkable
class RuntimeRecordPort(Protocol):
    """Core record boundary; this Protocol alone does not verify an Adapter."""

    async def insert_run(
        self,
        command: CreateRunCommand,
    ) -> InsertOnlyWriteResult:
        """Insert a validated CREATED Run; never overwrite its identity."""
        ...

    async def transition_run_if_active(
        self,
        command: TransitionRunCommand,
    ) -> ConditionalWriteResult:
        """CAS an exact active Run projection through a normal transition."""
        ...

    async def save_request_understanding(
        self, record: RequestUnderstandingRecord
    ) -> None: ...

    async def append_accepted_task_delta(self, record: AcceptedTaskDelta) -> None: ...

    async def save_input_binding(self, record: InputBinding) -> None: ...

    async def insert_task(
        self,
        command: CreateTaskCommand,
    ) -> InsertOnlyWriteResult:
        """Insert only a validated state-version-1 Task; never upsert."""
        ...

    async def insert_request_unit(
        self,
        command: CreateRequestUnitCommand,
    ) -> InsertOnlyWriteResult:
        """Insert only a validated state-version-1 RequestUnit; never upsert."""
        ...

    async def append_task_state_transition(
        self, record: TaskStateTransition
    ) -> None: ...

    async def save_context_manifest(self, record: ContextManifest) -> None: ...

    async def save_gate_decision(self, record: GateDecision) -> None: ...

    async def insert_tool_call(
        self,
        command: CreateToolCallCommand,
    ) -> InsertOnlyWriteResult:
        """Insert a validated CREATED ToolCall; never overwrite or dispatch."""
        ...

    async def start_tool_call_if_created(
        self,
        command: DispatchToolCallCommand,
    ) -> ToolDispatchFenceWriteResult:
        """CAS expected CREATED to RUNNING + first attempt before dispatch.

        ``command.started_attempt`` is the started projection: ``finished_at=None``,
        ``outcome=None``, and ``failure_code=None``. Completion conditionally
        finalizes that same attempt; P0 exposes no retry-append write boundary.
        APPLIED is the only result that permits a Read Tool dispatch. An Action
        additionally requires its STARTED/idempotency Ledger fence, so this
        capability returns ACTION_LEDGER_REQUIRED instead of authorizing it.
        """
        ...

    async def finalize_tool_call_attempt_if_running(
        self,
        command: FinalizeToolCallCommand,
    ) -> ConditionalWriteResult:
        """CAS expected RUNNING/started-attempt projections and finalize together."""
        ...

    async def save_observation(self, record: OrderObservation) -> None: ...

    async def append_trace_event(self, record: TraceEvent) -> None: ...

    async def create_run_task_link(
        self,
        command: CreateRunTaskLinkCommand,
    ) -> InsertOnlyWriteResult:
        """Insert only a validated active link; never overwrite its identity."""
        ...

    async def compare_and_set_run_task_link(
        self,
        record: RunTaskLinkRecord,
        *,
        expected_result_task_state_version: PositiveStateVersion | None,
    ) -> VersionedWriteResult:
        """Finalize a terminal Run link only from its expected projection."""
        ...

    async def compare_and_set_task(
        self,
        record: TaskRecord,
        *,
        expected_state_version: PositiveStateVersion,
    ) -> VersionedWriteResult:
        """Apply only from the expected Task version."""
        ...

    async def compare_and_set_request_unit(
        self,
        record: RequestUnitRecord,
        *,
        expected_state_version: PositiveStateVersion,
    ) -> VersionedWriteResult:
        """Apply only from the expected RequestUnit version."""
        ...

    async def load_run_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> AgentRunRecord | None:
        """Return ``None`` for both absent and unauthorized Runs."""
        ...

    async def load_task_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
    ) -> TaskRecord | None:
        """Return ``None`` for both absent and unauthorized Tasks."""
        ...

    async def load_request_unit_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        request_unit_id: UUID,
    ) -> RequestUnitRecord | None:
        """Return ``None`` for both absent and unauthorized RequestUnits."""
        ...

    async def load_request_understanding_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> RequestUnderstandingRecord | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def load_accepted_task_delta_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        accepted_delta_id: UUID,
    ) -> AcceptedTaskDelta | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def load_input_binding_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        binding_id: UUID,
    ) -> InputBinding | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def load_context_manifest_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        context_manifest_id: UUID,
    ) -> ContextManifest | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def load_gate_decision_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        gate_decision_id: UUID,
    ) -> GateDecision | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def load_tool_call_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        tool_call_id: UUID,
    ) -> ToolCallRecord | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def load_observation_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        observation_id: UUID,
    ) -> OrderObservation | None:
        """Return ``None`` for both absent and unauthorized records."""
        ...

    async def list_run_task_links_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> tuple[RunTaskLinkRecord, ...]:
        """Return an empty tuple for absent or unauthorized Runs."""
        ...

    async def list_trace_events_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> tuple[TraceEvent, ...]:
        """Return an empty tuple for absent or unauthorized Runs."""
        ...


@runtime_checkable
class EvalResultPort(Protocol):
    """Eval record boundary; this Protocol alone does not verify an Adapter."""

    async def append_eval_result(
        self,
        record: EvalResultRecord,
    ) -> InsertOnlyWriteResult:
        """Append one immutable ``(case, lane, attempt)`` result.

        Duplicate identity returns ALREADY_EXISTS and never overwrites history.
        """
        ...

    async def load_eval_result(
        self,
        *,
        eval_run_id: UUID,
        case_id: NonEmptyString,
        lane: NonEmptyString,
        attempt: PositiveAttempt,
    ) -> EvalResultRecord | None: ...

    async def list_eval_results(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalResultRecord, ...]:
        """Return all immutable attempts for one Eval Run."""
        ...

    async def append_eval_execution_failure(
        self, record: EvalExecutionFailureRecord
    ) -> None:
        """Append a failure that occurred before a complete Case result."""
        ...

    async def list_eval_execution_failures(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalExecutionFailureRecord, ...]: ...


@runtime_checkable
class RestartRecoveryPort(Protocol):
    """Recovery boundary; this Protocol alone does not verify an Adapter."""

    async def list_runs_pending_restart_recovery(
        self,
    ) -> tuple[AgentRunRecord, ...]:
        """Return only active Runs left CREATED or RUNNING."""
        ...

    async def list_tool_calls_pending_restart_recovery(
        self,
        *,
        run_id: UUID,
    ) -> tuple[ToolCallRecord, ...]:
        """Return only CREATED/RUNNING ToolCalls for the Run."""
        ...

    async def list_run_task_links_pending_restart_recovery(
        self,
        *,
        run_id: UUID,
    ) -> tuple[RunTaskLinkRecord, ...]:
        """Return only the Run-to-Task version projections needed for recovery."""
        ...

    async def list_tasks_pending_restart_recovery(
        self,
        *,
        run_id: UUID,
    ) -> tuple[TaskRecord, ...]:
        """Return only still-active Tasks linked to the interrupted Run."""
        ...

    async def list_request_units_pending_restart_recovery(
        self,
        *,
        run_id: UUID,
    ) -> tuple[RequestUnitRecord, ...]:
        """Return only still-active RequestUnits linked to the interrupted Run."""
        ...

    async def claim_and_mark_run_incomplete_if_active(
        self,
        command: MarkRunIncompleteForRecoveryCommand,
    ) -> RecoveryWriteResult:
        """Atomically claim and close a Run only while CREATED or RUNNING."""
        ...

    async def interrupt_tool_call_if_active(
        self,
        command: InterruptToolCallForRecoveryCommand,
    ) -> RecoveryWriteResult:
        """CAS a safely interruptible call without changing its attempt count.

        A CREATED pre-dispatch call retains attempt_count=0. A dispatched ACTION
        returns RECONCILIATION_REQUIRED and stays on its RESULT_UNKNOWN path.
        """
        ...

    async def compare_and_set_run_task_link_for_restart(
        self,
        record: RunTaskLinkRecord,
        *,
        expected_result_task_state_version: PositiveStateVersion | None,
    ) -> VersionedWriteResult:
        """Finalize a recovery link only from its expected projection."""
        ...

    async def compare_and_set_task_for_restart(
        self,
        record: TaskRecord,
        *,
        expected_state_version: PositiveStateVersion,
    ) -> VersionedWriteResult:
        """Block a Task only from the recovery scan's expected version."""
        ...

    async def compare_and_set_request_unit_for_restart(
        self,
        record: RequestUnitRecord,
        *,
        expected_state_version: PositiveStateVersion,
    ) -> VersionedWriteResult:
        """Block a RequestUnit only from the recovery scan's expected version."""
        ...
