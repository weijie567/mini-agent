"""Core-facing Ports; concrete SDK, HTTP, and database code belongs elsewhere."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateInitialTaskGraphCommand,
    CreateRunCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    FinalizeRunCommand,
    FinalizeToolCallCommand,
    InsertOnlyWriteResult,
    MessageRecord,
    NonEmptyString,
    ObservationWriteResult,
    PositiveAttempt,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
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
class AgentRunHandler(Protocol):
    """Application use case accepting only trusted identity plus bounded message."""

    async def handle(self, command: AgentRunCommand) -> AgentRunResult: ...


@runtime_checkable
class ModelProvider(Protocol):
    """Return candidates only; implementations cannot mutate state or run Tools.

    An Adapter maps an untrusted response violation to a fresh parameterless
    ``ProviderProtocolError`` only after discarding the raw exception. The raised
    bounded signal must have ``__cause__`` and ``__context__`` set to ``None``;
    suppressing display with ``raise ... from None`` alone does not erase context.
    """

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

    async def start_run_if_created(
        self,
        command: TransitionRunCommand,
    ) -> ConditionalWriteResult:
        """CAS exactly CREATED to RUNNING without changing stable fields."""
        ...

    async def finalize_run_if_active(
        self,
        command: FinalizeRunCommand,
    ) -> ConditionalWriteResult:
        """Finalize RUNNING Run and every RunTaskLink atomically against Tasks."""
        ...

    async def create_initial_task_graph_if_current(
        self,
        command: CreateInitialTaskGraphCommand,
    ) -> ConditionalWriteResult:
        """Conditionally insert the complete owner-bound initial graph atomically."""
        ...

    async def apply_task_transition_if_current(
        self,
        command: ApplyTaskTransitionCommand,
    ) -> ConditionalWriteResult:
        """Conditionally advance Task, RequestUnit and transition atomically."""
        ...

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

    async def save_observation(
        self,
        command: SaveObservationCommand,
    ) -> ObservationWriteResult:
        """Insert/replay only against the exact successful source ToolCall.

        The Adapter must revalidate the persisted ToolCall/Run/Task/RequestUnit
        owner graph against ``command.owner_scope``; persisted identifiers alone
        never authorize the write.

        An identical complete envelope and source projection returns
        ALREADY_APPLIED. Source drift returns SOURCE_PROJECTION_CONFLICT with
        zero writes. A reused Observation identity with different facts,
        envelope metadata, or source references raises
        ``P0PersistenceIntegrityError`` rather than returning a result value.
        """
        ...

    async def append_trace_event(self, record: TraceEvent) -> None: ...

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
    """Recovery boundary; this Protocol alone does not verify an Adapter.

    Infrastructure owns database closed-set completeness. It must strict-decode
    the complete owner-root graph under one transactionally consistent snapshot
    or equivalent fence; the Application closure validates only the supplied
    graph and never proves that no row was omitted.
    """

    async def load_next_restart_recovery_closure(
        self,
    ) -> RestartRecoveryClosure | None:
        """Return None only when no active candidate exists.

        Decode, owner-graph, cardinality, or database closed-set completeness
        failure raises ``P0PersistenceIntegrityError`` and keeps readiness failed;
        it never returns a partial closure or skips the corrupt candidate.
        Infrastructure proves that completeness in one consistent snapshot/fence.
        For every capped closure family it must use ``LIMIT 2`` or an equivalent
        stream cutoff in that same snapshot/fence and detect a second row before
        materializing the tuple. Cap overflow is a bounded integrity failure that
        keeps readiness failed; an Adapter must not first load an unbounded set.
        """
        ...

    async def claim_and_apply_restart_recovery(
        self,
        command: ApplyRestartRecoveryCommand,
    ) -> RecoveryWriteResult:
        """Revalidate the exact closure fence and apply one atomic transaction.

        APPLIED requires a compliant Adapter to commit all state/link projections
        and every Core/Runtime-produced ``command.recovery_trace_events`` together
        in that transaction. ``RuntimeRecordPort.append_trace_event`` remains a
        normal Trace capability but cannot substitute for recovery atomicity.

        CLOSURE_CONFLICT, NOT_APPLICABLE, and RECONCILIATION_REQUIRED guarantee
        zero state writes and zero Trace writes. A RUNNING ACTION is always
        RECONCILIATION_REQUIRED: its candidate interruption projection may be
        carried for bijection, but neither INTERRUPTED nor any Run/Task/link
        projection may commit; Action RESULT_UNKNOWN reconciliation remains the
        Tool/Action owner path. Integrity failure raises instead of returning.
        """
        ...
