"""Core-facing Ports; concrete SDK, HTTP, and database code belongs elsewhere."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    AppendToolAttemptV2Command,
    ApplyOrderCandidateSelectionV2Command,
    ApplyOrderSearchOutcomeV2Command,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    Cycle2DispatchFenceWriteResult,
    Cycle2WriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateInitialTaskGraphV2Command,
    CreateRunCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    ExactRunEvidenceClosure,
    FinalizeRunCommand,
    FinalizeSupersededRunV2Command,
    FinalizeToolCallCommand,
    FinalizeToolAttemptV2Command,
    InsertOnlyWriteResult,
    MessageRecord,
    NonEmptyString,
    ObservationWriteResult,
    OrderCandidateSelectionReadClosure,
    PositiveAttempt,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    RunTaskLinkRecord,
    SaveShipmentAssessmentV2Command,
    SaveShipmentObservationV2Command,
    SaveRequestUnderstandingV2NoTaskCommand,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
    ShipmentAssessmentReadClosure,
    SupersededRunReadClosure,
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
    RequestUnderstandingOutputV2,
)
from mini_agent.core.task_state import (
    InputBinding,
    OrderCandidateSelectionRequest,
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
    transactionally consistent owner-scoped snapshot for each read closure and
    one atomic CAS transaction for each write command. Normal absent and
    unauthorized states are indistinguishable; once an owner root is selected,
    dangling, duplicate, wrong-owner, partial, mixed-version, or contradictory
    evidence fails closed rather than degrading to absence.

    ``APPLIED`` means the complete command aggregate committed. Every other
    result means zero writes. These declarations do not grant Tool dispatch,
    business-fact authority, or user-visible result authority.
    """

    async def apply_order_search_outcome_if_current(
        self,
        command: ApplyOrderSearchOutcomeV2Command,
    ) -> Cycle2WriteResult:
        """Atomically commit Search Observation, CandidateSet, and Task effect."""
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
        """CAS SelectionRecord, selected target, and pending-question closure."""
        ...

    async def append_tool_attempt_if_current(
        self,
        command: AppendToolAttemptV2Command,
    ) -> Cycle2DispatchFenceWriteResult:
        """Append one unfinished attempt under CAS before external dispatch.

        Only ``APPLIED`` grants exactly one dispatch. Replay, conflict, and
        not-applicable results never grant dispatch, including after recovery.
        """
        ...

    async def finalize_tool_attempt_if_current(
        self,
        command: FinalizeToolAttemptV2Command,
    ) -> Cycle2WriteResult:
        """Replace the exact unfinished child and project its parent atomically."""
        ...

    async def save_shipment_observation_if_current(
        self,
        command: SaveShipmentObservationV2Command,
    ) -> Cycle2WriteResult:
        """Commit one fresh exact-source Observation and current supersession."""
        ...

    async def load_shipment_assessment_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        verified_order_target_ref: NonEmptyString,
        trusted_assessed_at: datetime,
        current_claim_binding_ref: UUID | None,
    ) -> ShipmentAssessmentReadClosure | None:
        """Load exact durable Observation/Task/Claim inputs for Assessment.

        ``None`` represents both absent and unauthorized. Stale or contradictory
        selected graphs fail closed and cannot be returned as current facts.
        """
        ...

    async def save_shipment_assessment_if_current(
        self,
        command: SaveShipmentAssessmentV2Command,
    ) -> Cycle2WriteResult:
        """Commit only the deterministic derivation of the exact read closure."""
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
