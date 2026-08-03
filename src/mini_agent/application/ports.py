"""Core-facing Ports; concrete SDK, HTTP, and database code belongs elsewhere."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    AppendInitialToolAttemptV2Command,
    AppendRecoveredToolAttemptV2Command,
    ApplyContinuationInputBindingV2Command,
    ApplyContinuationTaskDeltaV3Command,
    ApplyOrderCandidateSelectionV2Command,
    ApplyOrderCandidateSelectionV3Command,
    ApplyOrderSearchOutcomeV2Command,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    CreateCycle2InitialTaskGraphCommand,
    CreateCycle2InitialTaskGraphV3Command,
    CreateCycle2RunRootCommand,
    Cycle2ReadDispatchGrant,
    Cycle2ControlPurpose,
    Cycle2CurrentSessionTaskClosure,
    Cycle2ExactRunEvidenceClosure,
    Cycle2WriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    ContinuationInputBindingReadClosure,
    CreateInitialTaskGraphV2Command,
    CreateInitialTaskGraphV3Command,
    CreateRunCommand,
    CreateToolCallCommand,
    CreateToolCallV2Command,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    ExactRunEvidenceClosure,
    FinalizeCycle2RunCommand,
    FinalizeRunCommand,
    FinalizeBudgetExhaustedToolRecoveryV2Command,
    FinalizeCreatedToolRecoveryV2Command,
    FinalizeStateInvalidatedToolRecoveryV2Command,
    FinalizeSupersededRunV2Command,
    FinalizeToolCallCommand,
    FinalizeToolAttemptV2Command,
    FinalizeUnfinishedToolRecoveryV2Command,
    InsertOnlyWriteResult,
    InitialToolCallV2ReadClosure,
    MessageRecord,
    NonEmptyString,
    ObservationWriteResult,
    OrderCandidateSelectionReadClosure,
    OrderSearchCurrentReadClosure,
    PositiveAttempt,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    SaveOrderObservationV2Command,
    SaveShipmentAssessmentV2Command,
    SaveShipmentObservationV2Command,
    SaveRequestUnderstandingV2NoTaskCommand,
    SaveRejectedContinuationUnderstandingV3Command,
    SaveRequestUnderstandingV3NoTaskCommand,
    SaveObservationCommand,
    StartCycle2RunCommand,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
    ToolRetryRecoveryReadClosureV2,
    ShipmentAssessmentReadClosure,
    SupersededRunReadClosure,
)
from mini_agent.application.run_result_mapper import (
    Cycle2ExecutionOutcomeObservationV1,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.memory import (
    ContextManifest,
    OrderObservation,
)
from mini_agent.core.order import (
    GetOrderQuery,
    GetOrderResult,
)
from mini_agent.core.order_search import SearchOrdersQuery, SearchOrdersResult
from mini_agent.core.presentation import (
    PresentationInput,
    PresentationPlan,
)
from mini_agent.core.request_understanding import (
    Cycle2ControlCandidate,
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2ContinuationRequestUnderstandingOutputV2,
    Cycle2InputCandidate,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
)
from mini_agent.core.task_state import (
    InputBinding,
    OrderCandidateSelectionRequest,
    RequestUnitRecord,
    TaskRecord,
)
from mini_agent.core.shipment import GetShipmentQuery, GetShipmentResult
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
class GetOrderPort(Protocol):
    """Perform one customer-scoped order lookup."""

    async def get_order(self, query: GetOrderQuery) -> GetOrderResult: ...


@runtime_checkable
class SearchOrdersPort(Protocol):
    """Perform one customer-scoped order search."""

    async def search_orders(
        self,
        query: SearchOrdersQuery,
    ) -> SearchOrdersResult: ...


@runtime_checkable
class GetShipmentPort(Protocol):
    """Perform one customer-scoped Shipment lookup."""

    async def get_shipment(
        self,
        query: GetShipmentQuery,
    ) -> GetShipmentResult: ...


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
        """Conditionally commit one complete terminal-turn aggregate.

        For a compliant Adapter, APPLIED means the exact active Run,
        RunTaskLink, Task and RequestUnit preconditions matched and the
        Task/RequestUnit transition, terminal Run/RunTaskLink, ASSISTANT Message
        and exact terminal Trace committed in one transaction. The validated
        terminal result is the return/message/Trace binding, not another
        persistence item.

        PROJECTION_CONFLICT and NOT_APPLICABLE mean zero writes across every
        Task/RequestUnit/transition, terminal Run/RunTaskLink, Message and Trace
        projection. Post-commit Message or terminal Trace writes cannot satisfy
        this contract.
        """
        ...

    async def save_request_understanding_v2_no_task_if_current(
        self,
        command: SaveRequestUnderstandingV2NoTaskCommand,
    ) -> ConditionalWriteResult:
        """Conditionally commit one owner-bound RU-v2 parent in one transaction.

        APPLIED requires every trusted root to remain exact and current. This
        route never creates a Task or any accepted child, InputBinding, or link.
        PROJECTION_CONFLICT and NOT_APPLICABLE guarantee zero writes. An absent
        and an unauthorized owner graph remain indistinguishable.
        """
        ...

    async def create_initial_task_graph_v2_if_current(
        self,
        command: CreateInitialTaskGraphV2Command,
    ) -> ConditionalWriteResult:
        """Conditionally commit the complete RU-v2 graph in one transaction.

        APPLIED requires every trusted root to remain exact and current and
        commits the parent, child, Task, RequestUnit, InputBinding, and links
        atomically. This route never degrades to the no-task route.
        PROJECTION_CONFLICT and NOT_APPLICABLE guarantee zero writes. An absent
        and an unauthorized owner graph remain indistinguishable.
        """
        ...

    async def save_request_understanding_v3_no_task_if_current(
        self,
        command: SaveRequestUnderstandingV3NoTaskCommand,
    ) -> Cycle2WriteResult:
        """Stage one exact generic v3 no-task closure; never fall back to v2."""
        ...

    async def create_initial_task_graph_v3_if_current(
        self,
        command: CreateInitialTaskGraphV3Command,
    ) -> Cycle2WriteResult:
        """Stage all generic v3 accepted effects in one identity-first write."""
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
class Cycle2RuntimeRecordPort(Protocol):
    """Inactive exact-v2 aggregate boundary; it does not extend v1 Ports.

    Every method is exact-version-only. A compliant Adapter must use one
    transactionally consistent owner-scoped snapshot for each read closure.
    Read closures are typed records, not caller-signed trust tokens. Every write
    must re-read and exact-compare its declared current graph in the same atomic
    CAS boundary, so a caller cannot replace, relabel, replay, or narrow it.
    The Adapter must use one atomic CAS transaction for each write command.
    Normal absent and
    unauthorized states are indistinguishable; once an owner root is selected,
    dangling, duplicate, wrong-owner, partial, mixed-version, or contradictory
    evidence fails closed rather than degrading to absence.

    ``APPLIED`` means the complete command aggregate committed. Every other
    result means zero writes. These declarations do not grant Tool dispatch,
    business-fact authority, or user-visible result authority.
    """

    async def load_current_session_task_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        session_ref_hash: str,
        trusted_now: datetime,
    ) -> Cycle2CurrentSessionTaskClosure | None:
        """Load the one exact current Task graph for this trusted session.

        ``None`` means no current Task, absent, or unauthorized. Once an owner
        root is selected, duplicate, dangling, mixed-owner, mixed-version, or
        incomplete current graphs fail closed rather than degrading to absence.
        """
        ...

    async def insert_cycle2_run_root_if_current(
        self,
        command: CreateCycle2RunRootCommand,
    ) -> Cycle2WriteResult:
        """Insert Conversation/Message/Run roots and current link atomically."""
        ...

    async def start_cycle2_run_if_created(
        self,
        command: StartCycle2RunCommand,
    ) -> Cycle2WriteResult:
        """Advance the exact CREATED Run to RUNNING in one CAS write."""
        ...

    async def create_cycle2_initial_task_graph_if_current(
        self,
        command: CreateCycle2InitialTaskGraphCommand,
    ) -> Cycle2WriteResult:
        """Create the reviewed initial Task graph against exact current roots."""
        ...

    async def create_cycle2_initial_task_graph_v3_if_current(
        self,
        command: CreateCycle2InitialTaskGraphV3Command,
    ) -> Cycle2WriteResult:
        """Stage the exact initial v3 closure without switching the active route."""
        ...

    async def finalize_cycle2_run_if_current(
        self,
        command: FinalizeCycle2RunCommand,
    ) -> Cycle2WriteResult:
        """Commit normal assistant result and exact terminal Run atomically."""
        ...

    async def load_cycle2_exact_run_evidence_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> Cycle2ExactRunEvidenceClosure | None:
        """Load one expectation-free exact normal-turn evidence closure."""
        ...

    async def load_continuation_input_binding_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        message_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_now: datetime,
    ) -> ContinuationInputBindingReadClosure | None:
        """Load one complete current existing-Task USER-message closure.

        ``None`` keeps absent and unauthorized graphs indistinguishable. The
        owner-scoped reader returns every current InputBindingV2 for the
        RequestUnit; dangling, duplicate, mixed-version, wrong-direction, or
        wrong-message graphs fail closed before a write command can form.
        """
        ...

    async def apply_continuation_input_binding_if_current(
        self,
        command: ApplyContinuationInputBindingV2Command,
    ) -> Cycle2WriteResult:
        """CAS one non-ordinal binding plus Task/RequestUnit v-to-v+1.

        The same transaction re-reads the exact closure and either commits the
        new binding, current RequestUnit refs, and both versions together or
        commits nothing. Every non-APPLIED result means zero writes. This
        method never accepts ``candidate_ordinal`` and grants no dispatch.
        """
        ...

    async def save_rejected_continuation_understanding_if_current(
        self,
        command: SaveRejectedContinuationUnderstandingV3Command,
    ) -> Cycle2WriteResult:
        """Stage one identity-first v3 REJECT with no accepted authority."""
        ...

    async def apply_continuation_task_delta_if_current(
        self,
        command: ApplyContinuationTaskDeltaV3Command,
    ) -> Cycle2WriteResult:
        """Stage one accepted v3 delta, all Bindings, Trace, and one Task CAS."""
        ...

    async def load_order_search_current_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        run_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_read_at: datetime,
    ) -> OrderSearchCurrentReadClosure | None:
        """Load current query, roots, and any current Search aggregate.

        ``None`` represents absent and unauthorized equivalently. More than one
        current query, CandidateSet, or Search aggregate, any unknown binding
        family, or a partial graph fails closed.
        """
        ...

    async def apply_order_search_outcome_if_current(
        self,
        command: ApplyOrderSearchOutcomeV2Command,
    ) -> Cycle2WriteResult:
        """Re-read exact roots/query/current Search graph, then commit atomically.

        The in-transaction read must equal ``command.loaded_read_closure`` through
        ``require_same_persisted_graph``. A mismatch returns zero writes.
        """
        ...

    async def load_order_candidate_selection_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        selection_request: OrderCandidateSelectionRequest,
        trusted_now: datetime,
    ) -> OrderCandidateSelectionReadClosure | None:
        """Load one exact current CandidateSet/Observation/target closure.

        ``None`` represents both absent and unauthorized. Integrity failure in a
        selected owner graph raises the bounded persistence-integrity error.
        """
        ...

    async def apply_order_candidate_selection_if_current(
        self,
        command: ApplyOrderCandidateSelectionV2Command,
    ) -> Cycle2WriteResult:
        """Commit ordinal binding and the complete selection effect in one CAS.

        The adapter must call ``command.require_live_target_issuance()``
        immediately before its in-transaction re-read; copied, deserialized,
        reconstructed, or replay-bound commands fail closed with zero writes.
        APPLIED atomically inserts InputBindingV2 and SelectionRecord, appends
        the RequestUnit binding ref, records the independent UUID target,
        closes the exact pending question, and advances Task/RequestUnit once.
        Every non-APPLIED result means zero writes across the full graph.
        """
        ...

    async def apply_order_candidate_selection_v3_if_current(
        self,
        command: ApplyOrderCandidateSelectionV3Command,
    ) -> Cycle2WriteResult:
        """Stage the v3 ordinal closure while retaining live target issuance."""
        ...

    async def load_initial_tool_call_v2_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_read_at: datetime,
    ) -> InitialToolCallV2ReadClosure | None:
        """Load the exact current Task/RequestUnit/InputBindingV2 closure.

        ``None`` represents absent and unauthorized identically. Any dangling,
        duplicate, mixed-version, stale, or partial selected graph fails closed.
        """
        ...

    async def insert_initial_tool_call_v2_if_current(
        self,
        command: CreateToolCallV2Command,
    ) -> Cycle2WriteResult:
        """Conditionally insert one clean CREATED ToolCallV2, never dispatch.

        The transaction re-reads the exact current closure and enforces one
        ToolCall per Gate. Only APPLIED inserts; every other result means zero
        writes and grants no Handler or external Tool dispatch authority.
        """
        ...

    async def append_initial_tool_attempt_if_current(
        self,
        command: AppendInitialToolAttemptV2Command,
    ) -> Cycle2ReadDispatchGrant:
        """Same-CAS revalidate current graph and append the attempt-1 fence.

        The transaction re-reads and exact-compares owner, active Run/link,
        current Task/RequestUnit, complete bindings/verified target, trusted
        server time, and versioned Run-budget policy. In that same transaction
        it computes ``min(500, authoritative remaining Run budget)`` in the
        strict ``1..500`` range. Only an APPLIED grant exact-bound to this
        tool_call_id and attempt_no=1 authorizes one dispatch. Every non-APPLIED
        grant has null authority fields, zero writes, and zero dispatch; the
        loaded closure or bare write enum grants no authority.
        """
        ...

    async def finalize_tool_attempt_if_current(
        self,
        command: FinalizeToolAttemptV2Command,
    ) -> Cycle2WriteResult:
        """Replace the exact unfinished child and project its parent atomically."""
        ...

    async def load_tool_retry_recovery_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        tool_call_id: UUID,
    ) -> ToolRetryRecoveryReadClosureV2 | None:
        """Load exact active Run/Task/bindings/ToolCall recovery evidence.

        The owner-scoped reader obtains trusted server time and the versioned
        Run-budget policy itself; it accepts no caller remaining-budget, clock,
        policy, decision, or dispatch authority. Duplicate, partial,
        mixed-version, wrong-owner, or contradictory graph evidence fails closed.
        """
        ...

    async def append_recovered_tool_attempt_if_current(
        self,
        command: AppendRecoveredToolAttemptV2Command,
    ) -> Cycle2ReadDispatchGrant:
        """Same-CAS re-read/recompute, decision-child plus attempt-2 fence.

        The transaction re-reads and exact-compares owner, active Run/link,
        current Task/RequestUnit, complete bindings/verified target, trusted
        server time, and versioned Run-budget policy, recomputes the decision,
        and commits both records atomically. In that same transaction it
        computes ``min(500, authoritative remaining Run budget)`` in the strict
        ``1..500`` range. It returns that timeout only in an APPLIED grant
        exact-bound to this tool_call_id and attempt_no=2. Every non-APPLIED
        grant has null authority fields, zero writes, and zero dispatch; old
        closure budget and bare write enum grant no authority.
        """
        ...

    async def finalize_unfinished_tool_recovery_if_current(
        self,
        command: FinalizeUnfinishedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        """Same-CAS append the decision child and parent-only terminal closure.

        APPLIED preserves the unfinished attempt. Every non-APPLIED result is
        zero-write and grants no dispatch.
        """
        ...

    async def finalize_created_tool_recovery_if_current(
        self,
        command: FinalizeCreatedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        """Same-CAS interrupt one CREATED zero-attempt ToolCall parent only.

        The transaction re-reads the exact owner/current closure. APPLIED writes
        only the exact INTERRUPTED parent. It creates no recovery decision child,
        attempt, result, recovery metadata/ref, or dispatch. Every non-APPLIED
        result is zero-write and zero-dispatch.
        """
        ...

    async def finalize_budget_exhausted_tool_recovery_if_current(
        self,
        command: FinalizeBudgetExhaustedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        """Same-CAS recompute budget and atomically close the exact parent.

        APPLIED appends RUN_BUDGET_EXHAUSTED and its R1 terminal projection.
        Every non-APPLIED result is zero-write and zero-dispatch.
        """
        ...

    async def finalize_state_invalidated_tool_recovery_if_current(
        self,
        command: FinalizeStateInvalidatedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        """Atomically compose Tool recovery with the exact OA-10 no-result closure.

        The same CAS re-reads both owner/current graphs. APPLIED writes the
        decision child, Tool parent, SUPERSEDED Run/link and audit Trace only;
        no Task, RequestUnit, Message, Result, outbound, or dispatch is allowed.
        Every non-APPLIED result means zero writes.
        """
        ...

    async def save_shipment_observation_if_current(
        self,
        command: SaveShipmentObservationV2Command,
    ) -> Cycle2WriteResult:
        """Commit one fresh exact-source Observation and current supersession."""
        ...

    async def save_order_observation_if_current(
        self,
        command: SaveOrderObservationV2Command,
    ) -> Cycle2WriteResult:
        """Commit get_order Observation plus Task/RequestUnit v-to-v+1 atomically."""
        ...

    async def load_shipment_assessment_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        verified_order_target_ref: NonEmptyString,
        trusted_assessed_at: datetime,
    ) -> ShipmentAssessmentReadClosure | None:
        """Load the complete durable Observation and InputBinding partitions.

        ``None`` represents both absent and unauthorized. Stale or contradictory
        selected graphs fail closed and cannot be returned as current facts. The
        caller cannot select, relabel, or omit a binding, Observation, or current
        Assessment; the owner-scoped reader determines and attests the complete
        current RequestUnit graph atomically.
        """
        ...

    async def save_shipment_assessment_if_current(
        self,
        command: SaveShipmentAssessmentV2Command,
    ) -> Cycle2WriteResult:
        """Re-read the complete graph, then commit deterministic derivation.

        The same write transaction must load every current typed binding, every
        Shipment Observation/supersession record, and the current Assessment,
        then exact-compare it with ``command.loaded_closure`` through
        ``require_same_persisted_graph``. Missing, relabeled, replayed, or newly
        added records return zero writes; caller-provided completeness is never
        trusted.
        """
        ...

    async def load_superseded_run_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        obsolete_run_id: UUID,
        replacement_run_id: UUID,
        request_unit_id: UUID,
    ) -> SupersededRunReadClosure | None:
        """Load the unique exact current evidence that an active Run is obsolete."""
        ...

    async def finalize_superseded_run_if_current(
        self,
        command: FinalizeSupersededRunV2Command,
    ) -> Cycle2WriteResult:
        """Atomically write OA-10 Run/link/audit Trace and no outbound result.

        The closed command has no Task, RequestUnit, Message, AgentRunResult, or
        ResponseRendered write projection. Contradictory or no-longer-current
        evidence means zero writes and never guesses a terminal state.
        """
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


@runtime_checkable
class Cycle2RequestUnderstandingProvider(Protocol):
    """Provider boundary for bounded Cycle 2 initial/continuation proposals."""

    async def propose_cycle2_initial(
        self,
        request: RequestUnderstandingInput,
    ) -> Cycle2InitialRequestUnderstandingOutputV2: ...

    async def propose_cycle2_continuation(
        self,
        request: RequestUnderstandingInput,
    ) -> Cycle2InputCandidate: ...

    async def propose_cycle2_continuation_v3(
        self,
        request: RequestUnderstandingInput,
    ) -> Cycle2ContinuationRequestUnderstandingOutputV2:
        """Staging-only exact envelope; never a fallback for the active v2 call."""
        ...

    async def propose_cycle2_control(
        self,
        request: RequestUnderstandingInput,
        purpose: Cycle2ControlPurpose,
    ) -> Cycle2ControlCandidate:
        """Return one argument-free choice for the actual closed control purpose."""
        ...


@runtime_checkable
class Cycle2ExecutionOutcomeObserver(Protocol):
    """Post-finalize in-process observation seam; grants no control authority."""

    def observe_cycle2_execution_outcome(
        self,
        observation: Cycle2ExecutionOutcomeObservationV1,
    ) -> None: ...


class NoOpCycle2ExecutionOutcomeObserver:
    """Production default that cannot change or fail normal execution."""

    def observe_cycle2_execution_outcome(
        self,
        observation: Cycle2ExecutionOutcomeObservationV1,
    ) -> None:
        if type(observation) is not Cycle2ExecutionOutcomeObservationV1:
            raise TypeError("exact Cycle2ExecutionOutcomeObservationV1 required")


@runtime_checkable
class ModelProviderV2(Protocol):
    """Bounded Request Understanding v2 and Presentation candidate provider.

    For a correctly framed Request Understanding target function, an Adapter
    validates the arguments as ``RequestUnderstandingOutputV2``. Rejection of its
    Pydantic shape, version, source, authority, ``InputBinding``, or trusted or
    private field is exposed as a fresh
    ``RequestUnderstandingCandidateInvalidError``.

    Request Understanding transport, HTTP, JSON, framing, zero, multiple, or
    wrong-name target-call failures remain a fresh ``ProviderProtocolError``.
    Presentation transport, framing, target-call, and ``PresentationPlan``
    validation failures also remain a fresh ``ProviderProtocolError``.

    Both bounded errors may be exposed only after discarding the raw exception
    and its raw diagnostic, with ``__cause__`` and ``__context__`` cleared.
    Suppressing display with ``raise ... from None`` alone does not erase context.
    """

    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutputV2: ...

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan: ...


@runtime_checkable
class ExactRunEvidencePort(Protocol):
    """Owner-scoped, expectation-free exact-Run logical evidence boundary.

    ``None only`` represents the indistinguishable pre-payload states absent,
    unauthorized, or ownership-unverified. Once Infrastructure selects the owner
    root, identity, version, decode, provenance, owner-graph, relation,
    cardinality, or database closed set failure raises the bounded
    ``P0PersistenceIntegrityError``.

    Infrastructure must strict-decode and prove the database closed set under one
    transactionally consistent snapshot or an equivalent exact fence. It cannot
    return a partial closure, skip-corrupt data, retry through another session, or
    stitch grader-facing evidence from independent Port calls.

    The returned logical closure does not authorize access, does not write, does
    not claim recovery, and does not construct Case, expectation, HTTP, or Eval
    Result projections.
    """

    async def load_exact_run_evidence_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> ExactRunEvidenceClosure | None: ...
