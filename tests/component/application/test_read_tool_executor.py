import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from mini_agent.application.read_tool_executor import (
    ReadToolExecutionError,
    ReadToolExecutor,
)
from mini_agent.application.records import (
    ConditionalWriteResult,
    InsertOnlyWriteResult,
    ObservationWriteResult,
    ToolDispatchFenceWriteResult,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.order import (
    GetOrderOutcome,
    GetOrderQuery,
    GetOrderResult,
    OrderLineSummary,
    OrderStatus,
    OrderSummaryProjection,
)
from mini_agent.core.tool_system import (
    AuthorizedToolCommand,
    ExecutionPolicy,
    ToolCallStatus,
    ToolResultOutcome,
    ToolTimeoutPhase,
)
from mini_agent.core.trace import TraceEvent, TraceEventType

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class RuntimeSpy:
    def __init__(
        self,
        *,
        fence_result: ToolDispatchFenceWriteResult = (
            ToolDispatchFenceWriteResult.APPLIED
        ),
        insert_result: InsertOnlyWriteResult = InsertOnlyWriteResult.INSERTED,
        finalize_result: ConditionalWriteResult = ConditionalWriteResult.APPLIED,
        observation_result: ObservationWriteResult = (
            ObservationWriteResult.INSERTED
        ),
    ) -> None:
        self.events: list[str] = []
        self.fence_result = fence_result
        self.insert_result = insert_result
        self.finalize_result = finalize_result
        self.observation_result = observation_result
        self.create_commands: list[object] = []
        self.dispatch_commands: list[object] = []
        self.finalize_commands: list[object] = []
        self.observation_commands: list[object] = []
        self.trace_events: list[TraceEvent] = []

    async def insert_tool_call(self, command: object) -> InsertOnlyWriteResult:
        self.events.append("tool_call_created")
        self.create_commands.append(command)
        return self.insert_result

    async def start_tool_call_if_created(
        self,
        command: object,
    ) -> ToolDispatchFenceWriteResult:
        self.events.append("dispatch_fence")
        self.dispatch_commands.append(command)
        return self.fence_result

    async def finalize_tool_call_attempt_if_running(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("tool_call_finalized")
        self.finalize_commands.append(command)
        return self.finalize_result

    async def save_observation(
        self,
        command: object,
    ) -> ObservationWriteResult:
        self.events.append("observation_saved")
        self.observation_commands.append(command)
        return self.observation_result

    async def append_trace_event(self, record: TraceEvent) -> None:
        self.events.append(f"trace:{record.event_type.value}")
        self.trace_events.append(record)


class OrderSpy:
    def __init__(self, result: GetOrderResult, events: list[str]) -> None:
        self.result = result
        self.events = events
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


class UuidSequence:
    def __init__(self) -> None:
        self.values = [uuid4() for _ in range(8)]
        self.index = 0

    def __call__(self) -> UUID:
        value = self.values[self.index]
        self.index += 1
        return value


def _owner_scope(customer_id: str = "customer-A") -> TrustedOwnerScope:
    context = CustomerContext(
        subject_ref="subject-A",
        customer_id=customer_id,
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=NOW,
        session_ref_hash="sha256:session-A",
    )
    return TrustedOwnerScope.from_customer_context(context)


def _authorized(order_id: str = "O-1001") -> AuthorizedToolCommand:
    return AuthorizedToolCommand(
        gate_decision_id=uuid4(),
        canonical_tool_name="get_order",
        validated_arguments={"order_id": order_id},
        argument_binding_refs=(uuid4(),),
        validated_task_state_version=1,
        registry_snapshot_ref="runtime-tools-v1",
        trusted_context_ref="runtime-private-context-ref",
    )


def _summary() -> OrderSummaryProjection:
    return OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=NOW,
        status_updated_at=NOW,
    )


def _execution_policy(timeout_ms: int = 500) -> ExecutionPolicy:
    return ExecutionPolicy(
        timeout_ms=timeout_ms,
        max_attempts=1,
        interrupt_behavior="MARK_INTERRUPTED",
    )


async def _execute(
    *,
    result: GetOrderResult,
    runtime: RuntimeSpy | None = None,
):
    actual_runtime = runtime or RuntimeSpy()
    order = OrderSpy(result, actual_runtime.events)
    executor = ReadToolExecutor(
        runtime_record_port=actual_runtime,
        get_order_port=order,
        clock=lambda: NOW,
        uuid_factory=UuidSequence(),
    )
    execution = await executor.execute_get_order(
        owner_scope=_owner_scope(),
        authorized_command=_authorized(),
        run_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        provider_tool_call_id="provider-call-1",
        tool_registry_version="runtime-tools-v1",
        execution_policy=_execution_policy(),
        remaining_run_time_budget_ms=500,
    )
    return execution, actual_runtime, order


def test_found_read_is_durably_fenced_once_then_observed() -> None:
    execution, runtime, order = asyncio.run(
        _execute(
            result=GetOrderResult(
                outcome=GetOrderOutcome.FOUND,
                order_summary=_summary(),
            )
        )
    )

    assert runtime.events == [
        "tool_call_created",
        "dispatch_fence",
        "order_read",
        "tool_call_finalized",
        "observation_saved",
    ]
    assert order.queries == [
        GetOrderQuery(customer_id="customer-A", order_id="O-1001")
    ]
    assert len(runtime.create_commands) == 1
    assert len(runtime.dispatch_commands) == 1
    assert len(runtime.finalize_commands) == 1
    assert len(runtime.observation_commands) == 1
    assert execution.created_tool_call.status is ToolCallStatus.CREATED
    assert execution.terminal_tool_call.status is ToolCallStatus.SUCCEEDED
    assert execution.finalized_attempt.outcome is ToolResultOutcome.SUCCESS
    assert execution.observation is not None
    assert execution.observation.normalized_value.order_number == "O-1001"
    assert execution.observation.normalized_value == _summary()


@pytest.mark.parametrize(
    "fence_result",
    [
        ToolDispatchFenceWriteResult.STATUS_CONFLICT,
        ToolDispatchFenceWriteResult.NOT_APPLICABLE,
        ToolDispatchFenceWriteResult.ACTION_LEDGER_REQUIRED,
    ],
)
def test_every_non_applied_dispatch_fence_performs_zero_read(
    fence_result: ToolDispatchFenceWriteResult,
) -> None:
    runtime = RuntimeSpy(fence_result=fence_result)
    execution, runtime, order = asyncio.run(
        _execute(
            result=GetOrderResult(
                outcome=GetOrderOutcome.FOUND,
                order_summary=_summary(),
            ),
            runtime=runtime,
        )
    )

    assert execution.dispatch_fence_result is fence_result
    assert order.queries == []
    assert runtime.finalize_commands == []
    assert runtime.observation_commands == []
    assert runtime.events == ["tool_call_created", "dispatch_fence"]


def test_insert_conflict_performs_zero_fence_and_zero_read() -> None:
    runtime = RuntimeSpy(insert_result=InsertOnlyWriteResult.ALREADY_EXISTS)
    order = OrderSpy(
        GetOrderResult(
            outcome=GetOrderOutcome.FOUND,
            order_summary=_summary(),
        ),
        runtime.events,
    )
    executor = ReadToolExecutor(
        runtime_record_port=runtime,
        get_order_port=order,
        clock=lambda: NOW,
        uuid_factory=UuidSequence(),
    )

    with pytest.raises(ReadToolExecutionError, match="insert"):
        asyncio.run(
            executor.execute_get_order(
                owner_scope=_owner_scope(),
                authorized_command=_authorized(),
                run_id=uuid4(),
                task_id=uuid4(),
                request_unit_id=uuid4(),
                model_call_id=uuid4(),
                context_manifest_id=uuid4(),
                provider_tool_call_id=None,
                tool_registry_version="runtime-tools-v1",
                execution_policy=_execution_policy(),
                remaining_run_time_budget_ms=500,
            )
        )

    assert runtime.events == ["tool_call_created"]
    assert order.queries == []


@pytest.mark.parametrize(
    ("result", "expected_outcome", "expected_failure_code"),
    [
        (
            GetOrderResult(
                outcome=GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
            ),
            ToolResultOutcome.BUSINESS_FAILURE,
            "NOT_FOUND_OR_NOT_ACCESSIBLE",
        ),
        (
            GetOrderResult(
                outcome=GetOrderOutcome.SYSTEM_FAILURE,
                failure_code="raw-upstream-detail",
            ),
            ToolResultOutcome.SYSTEM_FAILURE,
            "ORDER_SERVICE_UNAVAILABLE",
        ),
    ],
)
def test_non_found_and_system_failures_finalize_without_observation(
    result: GetOrderResult,
    expected_outcome: ToolResultOutcome,
    expected_failure_code: str,
) -> None:
    execution, runtime, order = asyncio.run(_execute(result=result))

    assert len(order.queries) == 1
    assert len(runtime.finalize_commands) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.finalized_attempt.outcome is expected_outcome
    assert execution.terminal_tool_call.failure_code == expected_failure_code
    assert "raw-upstream-detail" not in str(execution)


def test_finalize_conflict_never_writes_an_observation() -> None:
    runtime = RuntimeSpy(
        finalize_result=ConditionalWriteResult.PROJECTION_CONFLICT
    )

    with pytest.raises(ReadToolExecutionError, match="finalization"):
        asyncio.run(
            _execute(
                result=GetOrderResult(
                    outcome=GetOrderOutcome.FOUND,
                    order_summary=_summary(),
                ),
                runtime=runtime,
            ),
        )

    assert runtime.events[-1] == "tool_call_finalized"
    assert runtime.observation_commands == []


def test_applied_hanging_read_uses_effective_budget_and_times_out() -> None:
    async def scenario():
        runtime = RuntimeSpy()
        order = HangingOrderSpy(runtime.events)
        executor = ReadToolExecutor(
            runtime_record_port=runtime,
            get_order_port=order,
            clock=lambda: NOW,
            uuid_factory=UuidSequence(),
        )
        execution = await executor.execute_get_order(
            owner_scope=_owner_scope(),
            authorized_command=_authorized(),
            run_id=uuid4(),
            task_id=uuid4(),
            request_unit_id=uuid4(),
            model_call_id=uuid4(),
            context_manifest_id=uuid4(),
            provider_tool_call_id=None,
            tool_registry_version="runtime-tools-v1",
            execution_policy=_execution_policy(timeout_ms=100),
            remaining_run_time_budget_ms=5,
        )
        return execution, runtime, order

    execution, runtime, order = asyncio.run(scenario())

    assert execution.effective_timeout_ms == 5
    assert len(order.queries) == 1
    assert len(runtime.finalize_commands) == 1
    assert runtime.observation_commands == []
    assert execution.terminal_tool_call.status is ToolCallStatus.TIMED_OUT
    assert execution.terminal_tool_call.timeout_phase is (
        ToolTimeoutPhase.AFTER_DISPATCH
    )
    assert execution.finalized_attempt.outcome is ToolResultOutcome.TIMEOUT
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE


def test_cancelled_applied_read_finalizes_interrupted_then_reraises() -> None:
    async def scenario():
        runtime = RuntimeSpy()
        order = HangingOrderSpy(runtime.events)
        executor = ReadToolExecutor(
            runtime_record_port=runtime,
            get_order_port=order,
            clock=lambda: NOW,
            uuid_factory=UuidSequence(),
        )
        execution_task = asyncio.create_task(
            executor.execute_get_order(
                owner_scope=_owner_scope(),
                authorized_command=_authorized(),
                run_id=uuid4(),
                task_id=uuid4(),
                request_unit_id=uuid4(),
                model_call_id=uuid4(),
                context_manifest_id=uuid4(),
                provider_tool_call_id=None,
                tool_registry_version="runtime-tools-v1",
                execution_policy=_execution_policy(timeout_ms=5_000),
                remaining_run_time_budget_ms=5_000,
            )
        )
        order_started = asyncio.create_task(order.started.wait())
        done, _pending = await asyncio.wait(
            {execution_task, order_started},
            timeout=0.5,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if execution_task in done:
            await execution_task
        assert order_started in done
        execution_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution_task
        return runtime, order

    runtime, order = asyncio.run(scenario())

    assert len(order.queries) == 1
    assert len(runtime.finalize_commands) == 1
    finalize = runtime.finalize_commands[0]
    assert finalize.terminal_record.status is ToolCallStatus.INTERRUPTED
    assert finalize.finalized_attempt.outcome is ToolResultOutcome.INTERRUPTED
    assert runtime.observation_commands == []
    assert [event.event_type for event in runtime.trace_events] == [
        TraceEventType.TOOL_CALL_INTERRUPTED
    ]


def test_read_executor_has_no_retry_parallel_or_action_execution_surface() -> None:
    public_methods = {
        name
        for name in dir(ReadToolExecutor)
        if not name.startswith("_")
    }

    assert public_methods == {"execute_get_order"}
    assert "attempt_no" not in ReadToolExecutor.execute_get_order.__annotations__
    assert all(
        forbidden not in public_methods
        for forbidden in ("retry", "execute_action", "parallel")
    )
