import asyncio
from datetime import UTC, datetime, timedelta, tzinfo
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
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolResultOutcome,
    ToolTimeoutPhase,
)
from mini_agent.core.trace import TraceEvent, TraceEventType

NOW = datetime(2030, 1, 1, tzinfo=UTC)
SYNTHETIC_SOURCE_VERSION = "mock-order-source-version.p0.v1:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class SourceVersionSubclass(str):
    pass


class StateKeySubclass(str):
    pass


class ArmedStateKeySubclass(str):
    armed = False

    def __hash__(self) -> int:
        if self.armed:
            raise RuntimeError("raw-customer-B-secret")
        return str.__hash__(self)


class ExplodingTzInfo(tzinfo):
    def utcoffset(self, _value: datetime | None):
        raise RuntimeError("raw-customer-B-secret")

    def dst(self, _value: datetime | None):
        return None

    def tzname(self, _value: datetime | None):
        return "exploding"


class AlwaysUtcTzInfo(tzinfo):
    def __init__(self) -> None:
        self.reads = 0

    def utcoffset(self, _value: datetime | None):
        self.reads += 1
        return timedelta(0)

    def dst(self, _value: datetime | None):
        self.reads += 1
        return timedelta(0)

    def tzname(self, _value: datetime | None):
        self.reads += 1
        return "raw-customer-B-secret"


class FlipTzInfo(tzinfo):
    def __init__(self) -> None:
        self.reads = 0

    def utcoffset(self, _value: datetime | None):
        self.reads += 1
        if self.reads <= 4:
            return timedelta(0)
        return timedelta(hours=8)

    def dst(self, _value: datetime | None):
        self.reads += 1
        return timedelta(0)

    def tzname(self, _value: datetime | None):
        self.reads += 1
        return "raw-customer-B-secret"


class TimestampSubclass(datetime):
    pass


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
        block_first_finalization: bool = False,
    ) -> None:
        self.events: list[str] = []
        self.fence_result = fence_result
        self.insert_result = insert_result
        self.finalize_result = finalize_result
        self.observation_result = observation_result
        self.block_first_finalization = block_first_finalization
        self.create_commands: list[object] = []
        self.dispatch_commands: list[object] = []
        self.finalize_commands: list[object] = []
        self.applied_finalize_commands: list[object] = []
        self.observation_commands: list[object] = []
        self.trace_events: list[TraceEvent] = []
        self.tool_call: ToolCallRecord | None = None
        self.attempt: ToolAttemptRecord | None = None
        self.finalization_started = asyncio.Event()
        self._release_finalization = asyncio.Event()

    async def insert_tool_call(self, command: object) -> InsertOnlyWriteResult:
        self.events.append("tool_call_created")
        self.create_commands.append(command)
        if self.insert_result is InsertOnlyWriteResult.INSERTED:
            self.tool_call = command.created_record
        return self.insert_result

    async def start_tool_call_if_created(
        self,
        command: object,
    ) -> ToolDispatchFenceWriteResult:
        self.events.append("dispatch_fence")
        self.dispatch_commands.append(command)
        if self.fence_result is ToolDispatchFenceWriteResult.APPLIED:
            assert self.tool_call == command.expected_created_record
            self.tool_call = command.running_record
            self.attempt = command.started_attempt
        return self.fence_result

    async def finalize_tool_call_attempt_if_running(
        self,
        command: object,
    ) -> ConditionalWriteResult:
        self.events.append("tool_call_finalized")
        self.finalize_commands.append(command)
        if self.block_first_finalization and len(self.finalize_commands) == 1:
            self.finalization_started.set()
            await self._release_finalization.wait()
        if self.finalize_result is not ConditionalWriteResult.APPLIED:
            return self.finalize_result
        if (
            self.tool_call != command.expected_running_record
            or self.attempt != command.expected_started_attempt
        ):
            return ConditionalWriteResult.PROJECTION_CONFLICT
        self.tool_call = command.terminal_record
        self.attempt = command.finalized_attempt
        self.applied_finalize_commands.append(command)
        return ConditionalWriteResult.APPLIED

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
                source_version=SYNTHETIC_SOURCE_VERSION,
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
    assert execution.observation.source_version == SYNTHETIC_SOURCE_VERSION


@pytest.mark.parametrize(
    "invalid_source_version",
    [
        None,
        "",
        " mock-order-source-version.p0.v1:sha256:"
        + ("a" * 64),
        "mock-order-source-version.p0.v1:sha256:" + ("A" * 64),
        b"mock-order-source-version.p0.v1:sha256:" + (b"a" * 64),
    ],
)
def test_found_with_unusable_source_version_fails_before_observation(
    invalid_source_version: object,
) -> None:
    candidate = GetOrderResult.model_construct(
        outcome=GetOrderOutcome.FOUND,
        order_summary=_summary(),
        source_version=invalid_source_version,
        failure_code=None,
    )

    execution, runtime, order = asyncio.run(_execute(result=candidate))

    assert len(order.queries) == 1
    assert runtime.events == [
        "tool_call_created",
        "dispatch_fence",
        "order_read",
        "tool_call_finalized",
    ]
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert execution.finalized_attempt is not None
    assert (
        execution.finalized_attempt.outcome
        is ToolResultOutcome.SYSTEM_FAILURE
    )
    if invalid_source_version not in {None, ""}:
        assert repr(invalid_source_version) not in str(execution)


@pytest.mark.parametrize(
    "corruption",
    [
        "root_fields_set",
        "root_legal_subset_fields_set",
        "root_state_key_subclass",
        "root_extra",
        "root_private",
        "summary_fields_set",
        "line_private",
        "source_version_subclass",
    ],
)
def test_found_with_noncanonical_recursive_state_fails_closed(
    corruption: str,
) -> None:
    candidate = GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=_summary(),
        source_version=SYNTHETIC_SOURCE_VERSION,
    )
    if corruption == "root_fields_set":
        object.__setattr__(
            candidate,
            "__pydantic_fields_set__",
            {"outcome", "raw-secret"},
        )
    elif corruption == "root_legal_subset_fields_set":
        object.__setattr__(
            candidate,
            "__pydantic_fields_set__",
            {"outcome"},
        )
    elif corruption == "root_state_key_subclass":
        state = vars(candidate)
        source_version = state.pop("source_version")
        state[StateKeySubclass("source_version")] = source_version
    elif corruption == "root_extra":
        object.__setattr__(
            candidate,
            "__pydantic_extra__",
            {"raw-secret": "must-not-survive"},
        )
    elif corruption == "root_private":
        object.__setattr__(
            candidate,
            "__pydantic_private__",
            {"raw-secret": "must-not-survive"},
        )
    elif corruption == "summary_fields_set":
        object.__setattr__(
            candidate.order_summary,
            "__pydantic_fields_set__",
            {"order_number", "raw-secret"},
        )
    elif corruption == "line_private":
        object.__setattr__(
            candidate.order_summary.line_items[0],
            "__pydantic_private__",
            {"raw-secret": "must-not-survive"},
        )
    elif corruption == "source_version_subclass":
        candidate = GetOrderResult.model_construct(
            outcome=GetOrderOutcome.FOUND,
            order_summary=_summary(),
            source_version=SourceVersionSubclass(
                SYNTHETIC_SOURCE_VERSION
            ),
            failure_code=None,
        )
    else:
        raise AssertionError("unsupported corruption")

    execution, runtime, order = asyncio.run(_execute(result=candidate))

    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert "raw-secret" not in str(execution)
    assert "must-not-survive" not in str(execution)


def test_candidate_leaf_exception_becomes_raw_free_system_failure() -> None:
    exploding_timestamp = datetime(
        2030,
        1,
        1,
        tzinfo=ExplodingTzInfo(),
    )
    summary = OrderSummaryProjection.model_construct(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=exploding_timestamp,
        status_updated_at=exploding_timestamp,
    )
    candidate = GetOrderResult.model_construct(
        outcome=GetOrderOutcome.FOUND,
        order_summary=summary,
        source_version=SYNTHETIC_SOURCE_VERSION,
        failure_code=None,
    )

    execution, runtime, order = asyncio.run(_execute(result=candidate))

    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert "raw-customer-B-secret" not in str(execution)
    assert "ExplodingTzInfo" not in str(execution)


def test_rebuild_exception_becomes_raw_free_system_failure() -> None:
    candidate = GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=_summary(),
        source_version=SYNTHETIC_SOURCE_VERSION,
    )
    state = vars(candidate)
    source_version = state.pop("source_version")
    armed_key = ArmedStateKeySubclass("source_version")
    state[armed_key] = source_version
    armed_key.armed = True

    execution, runtime, order = asyncio.run(_execute(result=candidate))

    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert "raw-customer-B-secret" not in str(execution)
    assert "ArmedStateKeySubclass" not in str(execution)


@pytest.mark.parametrize("timezone_type", [AlwaysUtcTzInfo, FlipTzInfo])
def test_custom_timezone_sidecar_fails_without_method_read(
    timezone_type: type[tzinfo],
) -> None:
    custom_timezone = timezone_type()
    timestamp = datetime(
        2030,
        1,
        1,
        tzinfo=custom_timezone,
    )
    summary = OrderSummaryProjection.model_construct(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=timestamp,
        status_updated_at=timestamp,
    )
    candidate = GetOrderResult.model_construct(
        outcome=GetOrderOutcome.FOUND,
        order_summary=summary,
        source_version=SYNTHETIC_SOURCE_VERSION,
        failure_code=None,
    )

    execution, runtime, order = asyncio.run(_execute(result=candidate))

    assert custom_timezone.reads == 0
    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert "raw-customer-B-secret" not in str(execution)
    assert timezone_type.__name__ not in str(execution)


def test_datetime_subclass_sidecar_fails_before_observation() -> None:
    timestamp = TimestampSubclass(
        2030,
        1,
        1,
        tzinfo=UTC,
    )
    timestamp.hidden_raw = "raw-customer-B-secret"
    summary = OrderSummaryProjection.model_construct(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=timestamp,
        status_updated_at=timestamp,
    )
    candidate = GetOrderResult.model_construct(
        outcome=GetOrderOutcome.FOUND,
        order_summary=summary,
        source_version=SYNTHETIC_SOURCE_VERSION,
        failure_code=None,
    )

    execution, runtime, order = asyncio.run(_execute(result=candidate))

    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert "raw-customer-B-secret" not in str(execution)
    assert "TimestampSubclass" not in str(execution)


@pytest.mark.parametrize("poisoned_field", ["outcome", "status"])
def test_poisoned_get_order_enum_singleton_fails_before_observation(
    poisoned_field: str,
) -> None:
    member = (
        GetOrderOutcome.FOUND
        if poisoned_field == "outcome"
        else OrderStatus.SHIPPED
    )
    storage = object.__getattribute__(member, "__dict__")
    original_items = tuple(
        (key, dict.__getitem__(storage, key))
        for key in dict.__iter__(storage)
    )
    object.__setattr__(
        member,
        "hidden_raw",
        "raw-customer-B-secret",
    )
    summary = OrderSummaryProjection.model_construct(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=NOW,
        status_updated_at=NOW,
    )
    candidate = GetOrderResult.model_construct(
        outcome=GetOrderOutcome.FOUND,
        order_summary=summary,
        source_version=SYNTHETIC_SOURCE_VERSION,
        failure_code=None,
    )

    try:
        execution, runtime, order = asyncio.run(_execute(result=candidate))
    finally:
        dict.clear(storage)
        for key, stored_value in original_items:
            dict.__setitem__(storage, key, stored_value)

    assert len(order.queries) == 1
    assert runtime.observation_commands == []
    assert execution.observation is None
    assert execution.get_order_outcome is GetOrderOutcome.SYSTEM_FAILURE
    assert execution.terminal_tool_call is not None
    assert execution.terminal_tool_call.status is ToolCallStatus.FAILED
    assert execution.terminal_tool_call.failure_code == (
        "ORDER_SERVICE_UNAVAILABLE"
    )
    assert "raw-customer-B-secret" not in str(execution)


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
                source_version=SYNTHETIC_SOURCE_VERSION,
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
            source_version=SYNTHETIC_SOURCE_VERSION,
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
                    source_version=SYNTHETIC_SOURCE_VERSION,
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


def test_cancel_during_terminal_finalization_closes_interrupted_once() -> None:
    async def scenario():
        runtime = RuntimeSpy(block_first_finalization=True)
        order = OrderSpy(
            GetOrderResult(
                outcome=GetOrderOutcome.FOUND,
                order_summary=_summary(),
                source_version=SYNTHETIC_SOURCE_VERSION,
            ),
            runtime.events,
        )
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
        await asyncio.wait_for(runtime.finalization_started.wait(), timeout=0.5)
        execution_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution_task
        return runtime, order

    runtime, order = asyncio.run(scenario())

    assert len(order.queries) == 1
    assert len(runtime.finalize_commands) == 2
    assert len(runtime.applied_finalize_commands) == 1
    finalization = runtime.applied_finalize_commands[0]
    assert finalization.terminal_record.status is ToolCallStatus.INTERRUPTED
    assert finalization.finalized_attempt.outcome is ToolResultOutcome.INTERRUPTED
    assert runtime.tool_call == finalization.terminal_record
    assert runtime.attempt == finalization.finalized_attempt
    assert runtime.observation_commands == []
    assert [event.event_type for event in runtime.trace_events] == [
        TraceEventType.TOOL_CALL_INTERRUPTED
    ]


def test_cancellation_finalization_conflict_preserves_cancelled_error() -> None:
    async def scenario():
        runtime = RuntimeSpy(
            finalize_result=ConditionalWriteResult.PROJECTION_CONFLICT
        )
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
        await asyncio.wait_for(order.started.wait(), timeout=0.5)
        execution_task.cancel()
        with pytest.raises(asyncio.CancelledError) as raised:
            await execution_task
        return runtime, order, raised.value

    runtime, order, cancellation = asyncio.run(scenario())

    assert len(order.queries) == 1
    assert len(runtime.finalize_commands) == 1
    assert runtime.applied_finalize_commands == []
    assert runtime.observation_commands == []
    assert runtime.trace_events == []
    assert any(
        "cancellation finalization raised ReadToolExecutionError" in note
        for note in cancellation.__notes__
    )


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
