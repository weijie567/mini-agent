import asyncio
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from inspect import signature
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import TZPATH, ZoneInfo

import pytest

from mini_agent.application.read_tool_executor import (
    Cycle2ReadToolExecution,
    Cycle2ReadToolExecutor,
    ReadToolExecutionError,
    ReadToolExecutor,
)
from mini_agent.application.records import (
    ConditionalWriteResult,
    CreateToolCallV2Command,
    Cycle2DispatchFenceWriteResult,
    Cycle2ReadDispatchGrant,
    Cycle2RunBudgetPolicyEvidence,
    Cycle2WriteResult,
    InsertOnlyWriteResult,
    InitialToolCallV2ReadClosure,
    ObservationWriteResult,
    RunTaskLinkRecordV2,
    ToolDispatchFenceWriteResult,
    ToolRetryRecoveryReadClosureV2,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_understanding import InputAuthority
from mini_agent.core.task_state import (
    InputBindingV2,
    InputValidationStatus,
    RequestUnitRecord,
    TaskRecord,
    TaskStatus,
)
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
    Cycle2ToolName,
    ExecutionPolicy,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
    ToolResult,
    ToolRetryDecision,
    ToolTimeoutPhase,
)
from mini_agent.core.trace import (
    AgentRunRecordV2,
    AgentRunStatusV2,
    TraceEvent,
    TraceEventType,
)

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


def test_exact_builtin_named_utc_timezone_is_preserved() -> None:
    named_utc = timezone(timedelta(0), "Z")
    timestamp = datetime(2030, 1, 1, tzinfo=named_utc)
    summary = OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=timestamp,
        status_updated_at=timestamp,
    )

    execution, runtime, order = asyncio.run(
        _execute(
            result=GetOrderResult(
                outcome=GetOrderOutcome.FOUND,
                order_summary=summary,
                source_version=SYNTHETIC_SOURCE_VERSION,
            )
        )
    )

    assert len(order.queries) == 1
    assert len(runtime.observation_commands) == 1
    assert execution.get_order_outcome is GetOrderOutcome.FOUND
    assert execution.observation is not None
    assert (
        object.__getattribute__(
            execution.observation.normalized_value.ordered_at,
            "tzinfo",
        )
        is named_utc
    )
    assert execution.observation.source_version == SYNTHETIC_SOURCE_VERSION


def test_exact_zoneinfo_utc_is_preserved() -> None:
    zoneinfo_utc = ZoneInfo("UTC")
    timestamp = datetime(2030, 1, 1, tzinfo=zoneinfo_utc)
    summary = OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=timestamp,
        status_updated_at=timestamp,
    )

    execution, runtime, order = asyncio.run(
        _execute(
            result=GetOrderResult(
                outcome=GetOrderOutcome.FOUND,
                order_summary=summary,
                source_version=SYNTHETIC_SOURCE_VERSION,
            )
        )
    )

    assert len(order.queries) == 1
    assert len(runtime.observation_commands) == 1
    assert execution.get_order_outcome is GetOrderOutcome.FOUND
    assert execution.observation is not None
    assert (
        object.__getattribute__(
            execution.observation.normalized_value.ordered_at,
            "tzinfo",
        )
        is zoneinfo_utc
    )
    assert execution.observation.source_version == SYNTHETIC_SOURCE_VERSION


def test_builtin_timezone_name_sidecar_fails_before_observation() -> None:
    raw_timezone = timezone(
        timedelta(0),
        "raw-customer-B-secret",
    )
    timestamp = datetime(2030, 1, 1, tzinfo=raw_timezone)
    summary = OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=timestamp,
        status_updated_at=timestamp,
    )
    candidate = GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=summary,
        source_version=SYNTHETIC_SOURCE_VERSION,
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


def test_zoneinfo_key_sidecar_fails_before_observation() -> None:
    utc_tzif_path = next(
        (
            candidate
            for root in TZPATH
            if (candidate := Path(root) / "UTC").is_file()
        ),
        None,
    )
    assert utc_tzif_path is not None
    with utc_tzif_path.open("rb") as utc_tzif:
        raw_zone = ZoneInfo.from_file(
            utc_tzif,
            key="raw-customer-B-secret",
        )
    timestamp = datetime(2030, 1, 1, tzinfo=raw_zone)
    summary = OrderSummaryProjection(
        order_number="O-1001",
        status=OrderStatus.SHIPPED,
        line_items=(OrderLineSummary(product_name="轻量跑鞋", quantity=1),),
        ordered_at=timestamp,
        status_updated_at=timestamp,
    )
    candidate = GetOrderResult(
        outcome=GetOrderOutcome.FOUND,
        order_summary=summary,
        source_version=SYNTHETIC_SOURCE_VERSION,
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


class Cycle2RuntimeSpy:
    def __init__(
        self,
        *,
        created: ToolCallRecordV2,
        owner_scope: TrustedOwnerScope,
        initial_result: Cycle2DispatchFenceWriteResult = (
            Cycle2DispatchFenceWriteResult.APPLIED
        ),
        recovered_result: Cycle2DispatchFenceWriteResult = (
            Cycle2DispatchFenceWriteResult.APPLIED
        ),
        initial_grant_mutation: str | None = None,
        recovered_grant_mutation: str | None = None,
        initial_timeout_ms: int = 137,
        recovered_timeout_ms: int = 211,
        initial_insert_result: Cycle2WriteResult = Cycle2WriteResult.APPLIED,
        finalize_result: Cycle2WriteResult = Cycle2WriteResult.APPLIED,
        closure_available: bool = True,
        run_budget_ms: int = 10_000,
        trusted_read_times: list[datetime] | None = None,
        current_state_version: int | None = None,
    ) -> None:
        self.tool_call = created
        self.owner_scope = owner_scope
        self.initial_result = initial_result
        self.recovered_result = recovered_result
        self.initial_grant_mutation = initial_grant_mutation
        self.recovered_grant_mutation = recovered_grant_mutation
        self.initial_timeout_ms = initial_timeout_ms
        self.recovered_timeout_ms = recovered_timeout_ms
        self.initial_insert_result = initial_insert_result
        self.finalize_result = finalize_result
        self.closure_available = closure_available
        self.run_budget_ms = run_budget_ms
        self.trusted_read_times = list(trusted_read_times or [])
        self.closure_loads = 0
        self.initial_append_commands: list[object] = []
        self.initial_insert_commands: list[object] = []
        self.recovered_append_commands: list[object] = []
        self.finalize_commands: list[object] = []
        binding_id = created.argument_binding_refs[0]
        self.binding = InputBindingV2(
            binding_id=binding_id,
            name="order_id",
            normalized_value="O-1001",
            authority=InputAuthority.USER_CLAIM,
            source_refs=(uuid4(),),
            validation_status=InputValidationStatus.ACCEPTED,
            confirmed_by_user=True,
            created_at=NOW,
            updated_at=NOW,
        )
        state_version = current_state_version or created.validated_task_state_version
        state_updated_at = NOW + timedelta(
            seconds=state_version - created.validated_task_state_version
        )
        self.task = TaskRecord(
            task_id=created.task_id,
            owner_customer_id=owner_scope.customer_id,
            status=TaskStatus.ACTIVE,
            state_version=state_version,
            created_at=NOW,
            updated_at=state_updated_at,
        )
        self.unit = RequestUnitRecord(
            request_unit_id=created.request_unit_id,
            task_id=created.task_id,
            goal_text="查询订单",
            goal_source_refs=(uuid4(),),
            input_binding_refs=(binding_id,),
            status=TaskStatus.ACTIVE,
            state_version=state_version,
            created_at=NOW,
            updated_at=state_updated_at,
        )
        self.run = AgentRunRecordV2(
            run_id=created.run_id,
            conversation_id=uuid4(),
            status=AgentRunStatusV2.RUNNING,
            provider_lane="scripted",
            started_at=NOW,
        )

    async def insert_initial_tool_call_v2_if_current(self, command):
        self.initial_insert_commands.append(command)
        if self.initial_insert_result is Cycle2WriteResult.APPLIED:
            self.tool_call = command.created_record
        return self.initial_insert_result

    @staticmethod
    def _grant(
        *,
        result: Cycle2DispatchFenceWriteResult,
        command: object,
        timeout_ms: int,
        mutation: str | None,
        recovered: bool,
    ) -> Cycle2ReadDispatchGrant:
        if result is not Cycle2DispatchFenceWriteResult.APPLIED:
            return Cycle2ReadDispatchGrant(write_result=result)
        append = command.attempt_append_command if recovered else command.attempt_append_command
        attempt = append.started_attempt
        tool_call_id = append.expected_record.tool_call_id
        attempt_no = attempt.attempt_no
        trusted_fenced_at = attempt.started_at
        if mutation == "tool_call_id":
            tool_call_id = uuid4()
        elif mutation == "attempt_no":
            attempt_no = 2 if attempt_no == 1 else 1
        elif mutation == "trusted_fenced_at":
            trusted_fenced_at = attempt.started_at - timedelta(microseconds=1)
        return Cycle2ReadDispatchGrant(
            write_result=result,
            tool_call_id=tool_call_id,
            attempt_no=attempt_no,
            trusted_fenced_at=trusted_fenced_at,
            effective_timeout_ms=timeout_ms,
        )

    async def append_initial_tool_attempt_if_current(self, command):
        self.initial_append_commands.append(command)
        grant = self._grant(
            result=self.initial_result,
            command=command,
            timeout_ms=self.initial_timeout_ms,
            mutation=self.initial_grant_mutation,
            recovered=False,
        )
        if self.initial_result is Cycle2DispatchFenceWriteResult.APPLIED:
            self.tool_call = command.attempt_append_command.next_running_record
        return grant

    async def finalize_tool_attempt_if_current(self, command):
        self.finalize_commands.append(command)
        if self.finalize_result is Cycle2WriteResult.APPLIED:
            self.tool_call = command.next_record
        return self.finalize_result

    async def load_tool_retry_recovery_closure_for_owner(self, **_kwargs):
        self.closure_loads += 1
        if not self.closure_available:
            return None
        evidence_times = [
            self.run.started_at,
            self.task.updated_at,
            self.unit.updated_at,
            self.binding.updated_at,
            self.tool_call.started_at,
        ]
        if self.tool_call.attempts:
            last = self.tool_call.attempts[-1]
            evidence_times.append(last.started_at)
            if last.finished_at is not None:
                evidence_times.append(last.finished_at)
        trusted_read_at = (
            self.trusted_read_times.pop(0)
            if self.trusted_read_times
            else max(evidence_times)
        )
        return ToolRetryRecoveryReadClosureV2(
            owner_scope=self.owner_scope,
            active_run_record=self.run,
            active_run_task_link_record=RunTaskLinkRecordV2(
                run_id=self.run.run_id,
                task_id=self.task.task_id,
                base_task_state_version=self.tool_call.validated_task_state_version,
            ),
            current_task_record=self.task,
            current_request_unit_record=self.unit,
            current_input_binding_records=(self.binding,),
            tool_call_record=self.tool_call,
            recovery_decision_records=(),
            trusted_read_at=trusted_read_at,
            run_budget_policy=Cycle2RunBudgetPolicyEvidence(
                policy_version="cycle2-test-budget.v1",
                run_time_budget_ms=self.run_budget_ms,
            ),
        )

    async def append_recovered_tool_attempt_if_current(self, command):
        self.recovered_append_commands.append(command)
        grant = self._grant(
            result=self.recovered_result,
            command=command,
            timeout_ms=self.recovered_timeout_ms,
            mutation=self.recovered_grant_mutation,
            recovered=True,
        )
        if self.recovered_result is Cycle2DispatchFenceWriteResult.APPLIED:
            self.tool_call = command.attempt_append_command.next_running_record
        return grant


class Cycle2HandlerSpy:
    def __init__(
        self,
        results: list[tuple[ToolResultOutcome, str | None, datetime]],
    ) -> None:
        self.results = results
        self.calls: list[tuple[ToolCallRecordV2, ToolAttemptRecordV2, int]] = []
        self.produced_results: list[ToolResult] = []

    async def __call__(self, record, attempt, timeout_ms):
        self.calls.append((record, attempt, timeout_ms))
        outcome, error_code, completed_at = self.results.pop(0)
        result = ToolResult(
            tool_call_id=record.tool_call_id,
            canonical_tool_name=record.canonical_tool_name.value,
            outcome=outcome,
            error_code=error_code,
            retryable=True,
            completed_at=completed_at,
        )
        self.produced_results.append(result)
        return result


def _cycle2_created_tool(
    name: Cycle2ToolName = Cycle2ToolName.SEARCH_ORDERS,
) -> tuple[TrustedOwnerScope, ToolCallRecordV2]:
    owner = _owner_scope()
    return owner, ToolCallRecordV2(
        tool_call_id=uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        request_unit_id=uuid4(),
        model_call_id=uuid4(),
        context_manifest_id=uuid4(),
        gate_decision_id=uuid4(),
        canonical_tool_name=name,
        tool_registry_version="e2e01-cycle2-tools.p0.v1",
        private_owner_scope_ref=owner.customer_id,
        validated_task_state_version=3,
        argument_binding_refs=(uuid4(),),
        verified_target_ref=(uuid4() if name is Cycle2ToolName.GET_SHIPMENT else None),
        effect=ToolEffect.READ,
        attempt_count=0,
        attempts=(),
        status=ToolCallStatus.CREATED,
        started_at=NOW,
    )


def _cycle2_create_command(
    *,
    owner: TrustedOwnerScope,
    created: ToolCallRecordV2,
    runtime: Cycle2RuntimeSpy,
) -> CreateToolCallV2Command:
    closure = InitialToolCallV2ReadClosure(
        owner_scope=owner,
        current_task_record=runtime.task,
        current_request_unit_record=runtime.unit,
        current_input_binding_records=(runtime.binding,),
        trusted_read_at=NOW,
    )
    return CreateToolCallV2Command.model_construct(
        loaded_closure=closure,
        created_record=created,
    )


def test_cycle2_grants_control_both_dispatch_timeouts_and_preserve_attempt_one() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        initial_timeout_ms=73,
        recovered_timeout_ms=41,
        run_budget_ms=9_000,
    )
    handler = Cycle2HandlerSpy(
        [
            (ToolResultOutcome.SYSTEM_FAILURE, "ORDER_SEARCH_TRANSIENT", NOW + timedelta(seconds=1)),
            (ToolResultOutcome.SUCCESS, None, NOW + timedelta(seconds=2)),
        ]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    terminal = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert terminal.status is ToolCallStatus.SUCCEEDED
    assert terminal.tool_call_id == created.tool_call_id
    assert terminal.attempt_count == 2
    assert [call[2] for call in handler.calls] == [73, 41]
    assert terminal.attempts[0].outcome is ToolResultOutcome.SYSTEM_FAILURE
    assert terminal.attempts[0].retry_decision is ToolRetryDecision.RETRY_SCHEDULED
    assert terminal.attempts[1].outcome is ToolResultOutcome.SUCCESS
    assert len(runtime.initial_append_commands) == 1
    assert len(runtime.recovered_append_commands) == 1
    assert len(runtime.finalize_commands) == 2


def test_cycle2_typed_execution_returns_same_attempt_applied_result() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SUCCESS, None, NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor._execute_created_with_result(
            owner_scope=owner,
            created_record=created,
        )
    )

    assert type(execution) is Cycle2ReadToolExecution
    assert execution.terminal_tool_call.status is ToolCallStatus.SUCCEEDED
    assert execution.tool_result is handler.produced_results[0]
    assert execution.tool_result.tool_call_id == created.tool_call_id
    assert (
        execution.tool_result.completed_at
        == execution.terminal_tool_call.attempts[-1].finished_at
    )


def test_cycle2_legacy_execute_returns_only_terminal_tool_call() -> None:
    owner, created = _cycle2_created_tool(Cycle2ToolName.GET_ORDER)
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SUCCESS, None, NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    terminal = asyncio.run(
        executor.execute(
            create_command=_cycle2_create_command(
                owner=owner,
                created=created,
                runtime=runtime,
            )
        )
    )

    assert type(terminal) is ToolCallRecordV2
    assert terminal.status is ToolCallStatus.SUCCEEDED
    assert len(runtime.initial_insert_commands) == 1


def test_cycle2_typed_execution_insert_conflict_has_no_result_or_dispatch() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        initial_insert_result=Cycle2WriteResult.PROJECTION_CONFLICT,
    )
    handler = Cycle2HandlerSpy([(ToolResultOutcome.SUCCESS, None, NOW)])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor.execute_with_result(
            create_command=_cycle2_create_command(
                owner=owner,
                created=created,
                runtime=runtime,
            )
        )
    )

    assert execution.terminal_tool_call == created
    assert execution.tool_result is None
    assert len(runtime.initial_insert_commands) == 1
    assert runtime.initial_append_commands == []
    assert handler.calls == []


def test_cycle2_typed_execution_retry_exposes_only_final_attempt_result() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [
            (
                ToolResultOutcome.SYSTEM_FAILURE,
                "ORDER_SEARCH_TRANSIENT",
                NOW + timedelta(seconds=1),
            ),
            (ToolResultOutcome.SUCCESS, None, NOW + timedelta(seconds=2)),
        ]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor._execute_created_with_result(
            owner_scope=owner,
            created_record=created,
        )
    )

    assert execution.terminal_tool_call.attempt_count == 2
    assert len(handler.produced_results) == 2
    assert execution.tool_result is handler.produced_results[1]
    assert execution.tool_result is not handler.produced_results[0]


def test_cycle2_typed_execution_timeout_does_not_expose_handler_result() -> None:
    owner, created = _cycle2_created_tool(Cycle2ToolName.GET_ORDER)
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.TIMEOUT, "TOOL_CALL_TIMEOUT", NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor._execute_created_with_result(
            owner_scope=owner,
            created_record=created,
        )
    )

    assert execution.terminal_tool_call.status is ToolCallStatus.TIMED_OUT
    assert len(handler.produced_results) == 1
    assert execution.tool_result is None


def test_cycle2_typed_execution_applied_interruption_keeps_same_result() -> None:
    owner, created = _cycle2_created_tool(Cycle2ToolName.GET_ORDER)
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [
            (
                ToolResultOutcome.INTERRUPTED,
                "USER_MESSAGE_SUPERSEDED",
                NOW + timedelta(seconds=1),
            )
        ]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor._execute_created_with_result(
            owner_scope=owner,
            created_record=created,
        )
    )

    assert execution.terminal_tool_call.status is ToolCallStatus.INTERRUPTED
    assert execution.tool_result is handler.produced_results[0]


@pytest.mark.parametrize(
    "result",
    [
        Cycle2DispatchFenceWriteResult.ALREADY_APPLIED,
        Cycle2DispatchFenceWriteResult.PROJECTION_CONFLICT,
        Cycle2DispatchFenceWriteResult.NOT_APPLICABLE,
    ],
)
def test_cycle2_non_applied_initial_grant_has_zero_dispatch_and_further_write(
    result: Cycle2DispatchFenceWriteResult,
) -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        initial_result=result,
    )
    handler = Cycle2HandlerSpy([(ToolResultOutcome.SUCCESS, None, NOW)])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned == created
    assert handler.calls == []
    assert len(runtime.initial_append_commands) == 1
    assert runtime.finalize_commands == []
    assert runtime.recovered_append_commands == []


def test_cycle2_typed_execution_non_applied_initial_grant_has_no_result() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        initial_result=Cycle2DispatchFenceWriteResult.PROJECTION_CONFLICT,
    )
    handler = Cycle2HandlerSpy([(ToolResultOutcome.SUCCESS, None, NOW)])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor._execute_created_with_result(
            owner_scope=owner,
            created_record=created,
        )
    )

    assert execution.terminal_tool_call == created
    assert execution.tool_result is None
    assert handler.calls == []


@pytest.mark.parametrize(
    "mutation",
    ["tool_call_id", "attempt_no", "trusted_fenced_at"],
)
def test_cycle2_malformed_applied_initial_grant_has_zero_dispatch_and_further_write(
    mutation: str,
) -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        initial_grant_mutation=mutation,
    )
    handler = Cycle2HandlerSpy([(ToolResultOutcome.SUCCESS, None, NOW)])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned == created
    assert handler.calls == []
    assert len(runtime.initial_append_commands) == 1
    assert runtime.finalize_commands == []
    assert runtime.recovered_append_commands == []


@pytest.mark.parametrize(
    "result",
    [
        Cycle2DispatchFenceWriteResult.ALREADY_APPLIED,
        Cycle2DispatchFenceWriteResult.PROJECTION_CONFLICT,
        Cycle2DispatchFenceWriteResult.NOT_APPLICABLE,
    ],
)
def test_cycle2_non_applied_recovered_grant_stops_before_attempt_two_dispatch(
    result: Cycle2DispatchFenceWriteResult,
) -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        recovered_result=result,
    )
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SYSTEM_FAILURE, "ORDER_SEARCH_TRANSIENT", NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned.status is ToolCallStatus.RUNNING
    assert returned.attempt_count == 1
    assert returned.attempts[0].retry_decision is ToolRetryDecision.RETRY_SCHEDULED
    assert len(handler.calls) == 1
    assert len(runtime.finalize_commands) == 1
    assert len(runtime.recovered_append_commands) == 1


@pytest.mark.parametrize(
    "mutation",
    ["tool_call_id", "attempt_no", "trusted_fenced_at"],
)
def test_cycle2_malformed_applied_recovered_grant_stops_before_attempt_two_dispatch(
    mutation: str,
) -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        recovered_grant_mutation=mutation,
    )
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SYSTEM_FAILURE, "ORDER_SEARCH_TRANSIENT", NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned.status is ToolCallStatus.RUNNING
    assert returned.attempt_count == 1
    assert len(handler.calls) == 1
    assert len(runtime.finalize_commands) == 1
    assert len(runtime.recovered_append_commands) == 1


@pytest.mark.parametrize(
    ("tool_name", "outcome", "failure_code"),
    [
        (Cycle2ToolName.SEARCH_ORDERS, ToolResultOutcome.BUSINESS_FAILURE, "NO_MATCH"),
        (Cycle2ToolName.GET_ORDER, ToolResultOutcome.SYSTEM_FAILURE, "ORDER_SERVICE_UNAVAILABLE"),
    ],
)
def test_cycle2_deterministic_failure_and_get_order_never_retry(
    tool_name: Cycle2ToolName,
    outcome: ToolResultOutcome,
    failure_code: str,
) -> None:
    owner, created = _cycle2_created_tool(tool_name)
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy([(outcome, failure_code, NOW + timedelta(seconds=1))])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    terminal = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert terminal.status is ToolCallStatus.FAILED
    assert terminal.attempt_count == 1
    assert terminal.attempts[0].retry_decision is ToolRetryDecision.NOT_RETRYABLE
    assert len(handler.calls) == 1
    assert runtime.recovered_append_commands == []


def test_cycle2_get_shipment_retries_once_and_never_attempt_three() -> None:
    owner, created = _cycle2_created_tool(Cycle2ToolName.GET_SHIPMENT)
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [
            (ToolResultOutcome.SYSTEM_FAILURE, "SHIPMENT_SERVICE_TRANSIENT", NOW + timedelta(seconds=1)),
            (ToolResultOutcome.SYSTEM_FAILURE, "SHIPMENT_SERVICE_TRANSIENT", NOW + timedelta(seconds=2)),
        ]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    terminal = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert terminal.status is ToolCallStatus.FAILED
    assert terminal.attempt_count == 2
    assert [attempt.retry_decision for attempt in terminal.attempts] == [
        ToolRetryDecision.RETRY_SCHEDULED,
        ToolRetryDecision.MAX_ATTEMPTS_REACHED,
    ]
    assert len(handler.calls) == 2
    assert len(runtime.recovered_append_commands) == 1


def test_cycle2_non_applied_finalize_never_recovers_or_dispatches_attempt_two() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        finalize_result=Cycle2WriteResult.PROJECTION_CONFLICT,
    )
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SYSTEM_FAILURE, "ORDER_SEARCH_TRANSIENT", NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned.status is ToolCallStatus.RUNNING
    assert returned.attempts[0].finished_at is None
    assert len(handler.calls) == 1
    assert len(runtime.finalize_commands) == 1
    assert runtime.recovered_append_commands == []


def test_cycle2_typed_execution_finalize_conflict_discards_validated_result() -> None:
    owner, created = _cycle2_created_tool(Cycle2ToolName.GET_ORDER)
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        finalize_result=Cycle2WriteResult.PROJECTION_CONFLICT,
    )
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SUCCESS, None, NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    execution = asyncio.run(
        executor._execute_created_with_result(
            owner_scope=owner,
            created_record=created,
        )
    )

    assert execution.terminal_tool_call.status is ToolCallStatus.RUNNING
    assert len(handler.produced_results) == 1
    assert execution.tool_result is None


def test_cycle2_result_unknown_is_rejected_without_finalize_or_retry() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(created=created, owner_scope=owner)
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.RESULT_UNKNOWN, None, NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    with pytest.raises(ReadToolExecutionError, match="invalid Cycle 2 handler result"):
        asyncio.run(
            executor._execute_created(owner_scope=owner, created_record=created)
        )

    assert len(handler.calls) == 1
    assert runtime.finalize_commands == []
    assert runtime.recovered_append_commands == []


def test_cycle2_missing_initial_closure_has_zero_fence_and_dispatch() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        closure_available=False,
    )
    handler = Cycle2HandlerSpy([(ToolResultOutcome.SUCCESS, None, NOW)])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned == created
    assert runtime.initial_append_commands == []
    assert handler.calls == []


@pytest.mark.parametrize(
    "runtime_kwargs",
    [
        {"run_budget_ms": 500, "trusted_read_times": [NOW + timedelta(seconds=1)]},
        {"current_state_version": 4},
    ],
    ids=["zero-budget-at-fence", "state-drift-at-fence"],
)
def test_cycle2_writer_non_applied_revalidation_has_zero_dispatch(
    runtime_kwargs: dict[str, object],
) -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        initial_result=Cycle2DispatchFenceWriteResult.NOT_APPLICABLE,
        **runtime_kwargs,
    )
    handler = Cycle2HandlerSpy([(ToolResultOutcome.SUCCESS, None, NOW)])
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    returned = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert returned == created
    assert len(runtime.initial_append_commands) == 1
    assert handler.calls == []
    assert runtime.finalize_commands == []


def test_cycle2_retry_decision_uses_post_dispatch_trusted_budget() -> None:
    owner, created = _cycle2_created_tool()
    runtime = Cycle2RuntimeSpy(
        created=created,
        owner_scope=owner,
        run_budget_ms=500,
        trusted_read_times=[NOW, NOW + timedelta(seconds=1)],
        initial_timeout_ms=37,
    )
    handler = Cycle2HandlerSpy(
        [(ToolResultOutcome.SYSTEM_FAILURE, "ORDER_SEARCH_TRANSIENT", NOW + timedelta(seconds=1))]
    )
    executor = Cycle2ReadToolExecutor(
        runtime_record_port=runtime,
        handler=handler,
        uuid_factory=UuidSequence(),
    )

    terminal = asyncio.run(
        executor._execute_created(owner_scope=owner, created_record=created)
    )

    assert terminal.status is ToolCallStatus.FAILED
    assert terminal.attempts[0].retry_decision is ToolRetryDecision.RUN_BUDGET_EXHAUSTED
    assert [call[2] for call in handler.calls] == [37]
    assert runtime.recovered_append_commands == []


def test_cycle2_executor_surface_has_no_clock_budget_retry_or_action_inputs() -> None:
    public_methods = {
        name for name in dir(Cycle2ReadToolExecutor) if not name.startswith("_")
    }

    assert public_methods == {"execute", "execute_with_result"}
    assert set(signature(Cycle2ReadToolExecutor.execute).parameters) == {
        "self",
        "create_command",
    }
    assert set(signature(Cycle2ReadToolExecutor.execute_with_result).parameters) == {
        "self",
        "create_command",
    }
    constructor_inputs = set(signature(Cycle2ReadToolExecutor).parameters)
    assert "clock" not in constructor_inputs
    assert "remaining_run_time_budget_ms" not in constructor_inputs
    assert all(name not in public_methods for name in ("retry", "execute_action"))
