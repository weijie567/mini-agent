"""Core-facing Ports; concrete SDK, HTTP, and database code belongs elsewhere."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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
    ToolAttemptRecord,
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
class RuntimeRecordPort(Protocol):
    """Persistence boundary for W1 Core-owned record semantics."""

    async def save_run(self, record: AgentRunRecord) -> None: ...

    async def save_request_understanding(
        self, record: RequestUnderstandingRecord
    ) -> None: ...

    async def append_accepted_task_delta(self, record: AcceptedTaskDelta) -> None: ...

    async def save_input_binding(self, record: InputBinding) -> None: ...

    async def save_task(self, record: TaskRecord) -> None: ...

    async def save_request_unit(self, record: RequestUnitRecord) -> None: ...

    async def append_task_state_transition(
        self, record: TaskStateTransition
    ) -> None: ...

    async def save_context_manifest(self, record: ContextManifest) -> None: ...

    async def save_gate_decision(self, record: GateDecision) -> None: ...

    async def save_tool_call(self, record: ToolCallRecord) -> None: ...

    async def append_tool_attempt(self, record: ToolAttemptRecord) -> None: ...

    async def save_observation(self, record: OrderObservation) -> None: ...

    async def append_trace_event(self, record: TraceEvent) -> None: ...
