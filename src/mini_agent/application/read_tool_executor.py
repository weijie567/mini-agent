"""Durably fenced execution of the single P0 ``get_order`` Read Tool."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, model_validator
from pydantic_core import TzInfo

from mini_agent.application.ports import (
    Cycle2RuntimeRecordPort,
    GetOrderPort,
    RuntimeRecordPort,
)
from mini_agent.application.records import (
    AppendInitialToolAttemptV2Command,
    AppendToolAttemptV2Command,
    ConditionalWriteResult,
    CreateToolCallV2Command,
    Cycle2DispatchFenceWriteResult,
    Cycle2ReadDispatchGrant,
    Cycle2WriteResult,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    FinalizeToolCallCommand,
    FinalizeToolAttemptV2Command,
    InsertOnlyWriteResult,
    ObservationWriteResult,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
    ToolRetryRecoveryReadClosureV2,
    TrustedOwnerScope,
)
from mini_agent.core.common import RuntimePrivateModel
from mini_agent.core.memory import (
    ObservationVisibility,
    OrderObservation,
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
    Cycle2RetryRevalidation,
    Cycle2ToolDispatchFacts,
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
    decide_cycle2_tool_retry,
    project_cycle2_tool_terminal,
)
from mini_agent.core.trace import TraceEvent, TraceEventType


class ReadToolExecutionError(RuntimeError):
    """Bounded internal execution conflict; no external detail is retained."""

    __slots__ = ()


class ReadToolExecution(RuntimePrivateModel):
    """Safe execution projection consumed by Runtime orchestration."""

    created_tool_call: ToolCallRecord
    dispatch_fence_result: ToolDispatchFenceWriteResult
    terminal_tool_call: ToolCallRecord | None = None
    finalized_attempt: ToolAttemptRecord | None = None
    get_order_outcome: GetOrderOutcome | None = None
    observation: OrderObservation | None = None
    effective_timeout_ms: int | None = None


_GET_ORDER_SOURCE_VERSION_PATTERN = re.compile(
    r"mock-order-source-version\.p0\.v1:sha256:[0-9a-f]{64}",
    flags=re.ASCII,
)


def _build_get_order_enum_member_snapshots() -> (
    tuple[
        tuple[
            type[Enum],
            tuple[tuple[Enum, tuple[tuple[str, object], ...]], ...],
        ],
        ...,
    ]
):
    snapshots_by_type = []
    for enum_type in (GetOrderOutcome, OrderStatus):
        member_snapshots = []
        for member in enum_type:
            storage = object.__getattribute__(member, "__dict__")
            if type(member) is not enum_type or type(storage) is not dict:
                raise RuntimeError(
                    "canonical get_order Enum storage changed"
                )
            storage_items = tuple(
                (
                    key,
                    dict.__getitem__(storage, key),
                )
                for key in dict.__iter__(storage)
            )
            if any(
                type(key) is not str
                or not (
                    stored_value is enum_type
                    or type(stored_value) in {int, str}
                )
                for key, stored_value in storage_items
            ):
                raise RuntimeError(
                    "canonical get_order Enum storage is not closed"
                )
            member_snapshots.append((member, storage_items))
        snapshots_by_type.append((enum_type, tuple(member_snapshots)))
    return tuple(snapshots_by_type)


_GET_ORDER_ENUM_MEMBER_SNAPSHOTS = (
    _build_get_order_enum_member_snapshots()
)


def _canonical_enum_member_is_closed(value: object) -> bool:
    enum_type = type(value)
    member_snapshots = next(
        (
            snapshots
            for candidate_type, snapshots in (
                _GET_ORDER_ENUM_MEMBER_SNAPSHOTS
            )
            if enum_type is candidate_type
        ),
        None,
    )
    if member_snapshots is None:
        return False
    snapshot = next(
        (
            candidate
            for candidate in member_snapshots
            if value is candidate[0]
        ),
        None,
    )
    if snapshot is None:
        return False
    storage = object.__getattribute__(value, "__dict__")
    expected_items = snapshot[1]
    if type(storage) is not dict or len(storage) != len(expected_items):
        return False
    stored_names = tuple(dict.__iter__(storage))
    if (
        any(type(name) is not str for name in stored_names)
        or stored_names
        != tuple(name for name, _ in expected_items)
    ):
        return False
    for name, expected_value in expected_items:
        stored_value = dict.__getitem__(storage, name)
        if expected_value is enum_type:
            if stored_value is not expected_value:
                return False
        elif (
            type(stored_value) is not type(expected_value)
            or stored_value != expected_value
        ):
            return False
    return True


def _is_closed_utc_datetime(value: object) -> bool:
    if type(value) is not datetime:
        return False
    timezone_value = object.__getattribute__(value, "tzinfo")
    if timezone_value is UTC:
        return True
    if type(timezone_value) is timezone:
        offset = timezone.utcoffset(timezone_value, value)
        name = timezone.tzname(timezone_value, value)
        return (
            type(offset) is timedelta
            and offset == timedelta(0)
            and type(name) is str
            and name in {"UTC", "Z"}
        )
    if type(timezone_value) is ZoneInfo:
        key = object.__getattribute__(timezone_value, "key")
        if type(key) is not str or key != "UTC":
            return False
        offset = ZoneInfo.utcoffset(timezone_value, value)
        return (
            type(offset) is timedelta
            and offset == timedelta(0)
        )
    if type(timezone_value) is not TzInfo:
        return False
    offset = TzInfo.utcoffset(timezone_value, value)
    return type(offset) is timedelta and offset == timedelta(0)


def _is_canonical_get_order_source_version(value: object) -> bool:
    return (
        type(value) is str
        and _GET_ORDER_SOURCE_VERSION_PATTERN.fullmatch(value) is not None
    )


def _has_exact_declared_model_state(
    value: object,
    expected_type: type[BaseModel],
) -> bool:
    if type(value) is not expected_type:
        return False
    declared_fields = frozenset(expected_type.model_fields)
    required_fields = frozenset(
        field_name
        for field_name, field_info in expected_type.model_fields.items()
        if field_info.is_required()
    )
    try:
        state = vars(value)
        fields_set = value.__pydantic_fields_set__
        extra = value.__pydantic_extra__
        private = value.__pydantic_private__
    except (AttributeError, TypeError):
        return False
    return (
        type(state) is dict
        and set(state) == declared_fields
        and all(type(field_name) is str for field_name in state)
        and type(fields_set) is set
        and all(type(field_name) is str for field_name in fields_set)
        and required_fields <= fields_set <= declared_fields
        and extra is None
        and private is None
    )


def _exact_recursive_value_matches(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, BaseModel):
        model_type = type(left)
        if (
            not _has_exact_declared_model_state(left, model_type)
            or not _has_exact_declared_model_state(right, model_type)
            or left.__pydantic_fields_set__
            != right.__pydantic_fields_set__
        ):
            return False
        return all(
            _exact_recursive_value_matches(
                getattr(left, field_name),
                getattr(right, field_name),
            )
            for field_name in model_type.model_fields
        )
    if type(left) is tuple:
        return len(left) == len(right) and all(
            _exact_recursive_value_matches(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def _project_tool_call(
    record: ToolCallRecord,
    **updates: object,
) -> ToolCallRecord:
    values: dict[str, Any] = {
        field_name: getattr(record, field_name)
        for field_name in ToolCallRecord.model_fields
    }
    values.update(updates)
    return ToolCallRecord(**values)


def _rebuild_canonical_get_order_result(
    value: object,
) -> GetOrderResult | None:
    if (
        not _has_exact_declared_model_state(value, GetOrderResult)
        or not _canonical_enum_member_is_closed(value.outcome)
        or (
            value.order_summary is not None
            and (
                not _has_exact_declared_model_state(
                    value.order_summary,
                    OrderSummaryProjection,
                )
                or not _canonical_enum_member_is_closed(
                    value.order_summary.status
                )
                or type(value.order_summary.line_items) is not tuple
                or any(
                    not _has_exact_declared_model_state(
                        line_item,
                        OrderLineSummary,
                    )
                    for line_item in value.order_summary.line_items
                )
                or not _is_closed_utc_datetime(
                    value.order_summary.ordered_at
                )
                or not _is_closed_utc_datetime(
                    value.order_summary.status_updated_at
                )
            )
        )
    ):
        return None
    try:
        payload = value.model_dump(
            mode="python",
            round_trip=True,
            exclude_unset=True,
            warnings="error",
        )
        rebuilt = GetOrderResult.model_validate(payload, strict=True)
    except (TypeError, ValueError):
        return None
    if (
        type(rebuilt) is not GetOrderResult
        or not _exact_recursive_value_matches(value, rebuilt)
        or (
            rebuilt.outcome is GetOrderOutcome.FOUND
            and not _is_canonical_get_order_source_version(
                rebuilt.source_version
            )
        )
    ):
        return None
    return rebuilt


def _canonical_get_order_result(
    value: object,
) -> GetOrderResult | None:
    try:
        return _rebuild_canonical_get_order_result(value)
    except Exception:
        return None


class ReadToolExecutor:
    """Execute one owner-scoped read only after an APPLIED durable fence."""

    def __init__(
        self,
        *,
        runtime_record_port: RuntimeRecordPort,
        get_order_port: GetOrderPort,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
    ) -> None:
        self._runtime_record_port = runtime_record_port
        self._get_order_port = get_order_port
        self._clock = clock
        self._uuid_factory = uuid_factory

    async def _finalize_running_attempt(
        self,
        *,
        running: ToolCallRecord,
        attempt: ToolAttemptRecord,
        terminal_status: ToolCallStatus,
        tool_outcome: ToolResultOutcome,
        safe_failure_code: str | None,
        result_ref: UUID | None = None,
        timeout_phase: ToolTimeoutPhase | None = None,
        interruption_reason: str | None = None,
    ) -> tuple[ToolCallRecord, ToolAttemptRecord]:
        finished_at = self._clock()
        terminal = _project_tool_call(
            running,
            status=terminal_status,
            finished_at=finished_at,
            failure_code=safe_failure_code,
            timeout_phase=timeout_phase,
            interruption_reason=interruption_reason,
            result_ref=result_ref,
        )
        finalized_attempt = ToolAttemptRecord(
            tool_call_id=running.tool_call_id,
            attempt_no=attempt.attempt_no,
            started_at=attempt.started_at,
            finished_at=finished_at,
            outcome=tool_outcome,
            failure_code=safe_failure_code,
        )
        finalize_result = (
            await self._runtime_record_port.finalize_tool_call_attempt_if_running(
                FinalizeToolCallCommand(
                    expected_running_record=running,
                    expected_started_attempt=attempt,
                    terminal_record=terminal,
                    finalized_attempt=finalized_attempt,
                )
            )
        )
        if finalize_result is not ConditionalWriteResult.APPLIED:
            raise ReadToolExecutionError("ToolCall finalization conflict")
        return terminal, finalized_attempt

    async def _append_interrupted_trace(
        self,
        *,
        terminal: ToolCallRecord,
    ) -> None:
        await self._runtime_record_port.append_trace_event(
            TraceEvent(
                trace_event_id=self._uuid_factory(),
                event_type=TraceEventType.TOOL_CALL_INTERRUPTED,
                occurred_at=terminal.finished_at,
                run_id=terminal.run_id,
                task_id=terminal.task_id,
                request_unit_id=terminal.request_unit_id,
                tool_call_id=terminal.tool_call_id,
                tool_call_terminal_status=ToolCallStatus.INTERRUPTED,
            )
        )

    async def execute_get_order(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        authorized_command: AuthorizedToolCommand,
        run_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        model_call_id: UUID,
        context_manifest_id: UUID,
        provider_tool_call_id: str | None,
        tool_registry_version: str,
        execution_policy: ExecutionPolicy,
        remaining_run_time_budget_ms: int,
    ) -> ReadToolExecution:
        if type(owner_scope) is not TrustedOwnerScope:
            raise ReadToolExecutionError("trusted owner scope required")
        if type(authorized_command) is not AuthorizedToolCommand:
            raise ReadToolExecutionError("authorized command required")
        if (
            type(execution_policy) is not ExecutionPolicy
            or execution_policy.max_attempts != 1
            or execution_policy.interrupt_behavior != "MARK_INTERRUPTED"
        ):
            raise ReadToolExecutionError(
                "validated single-attempt execution policy required"
            )
        if (
            type(remaining_run_time_budget_ms) is not int
            or remaining_run_time_budget_ms <= 0
        ):
            raise ReadToolExecutionError("positive remaining Run budget required")
        effective_timeout_ms = min(
            execution_policy.timeout_ms,
            remaining_run_time_budget_ms,
        )
        if (
            authorized_command.canonical_tool_name != "get_order"
            or authorized_command.registry_snapshot_ref != tool_registry_version
            or set(authorized_command.validated_arguments) != {"order_id"}
        ):
            raise ReadToolExecutionError("invalid get_order authorization")
        order_id = authorized_command.validated_arguments.get("order_id")
        if type(order_id) is not str:
            raise ReadToolExecutionError("invalid bound order_id")

        started_at = self._clock()
        created = ToolCallRecord(
            tool_call_id=self._uuid_factory(),
            run_id=run_id,
            task_id=task_id,
            request_unit_id=request_unit_id,
            model_call_id=model_call_id,
            context_manifest_id=context_manifest_id,
            gate_decision_id=authorized_command.gate_decision_id,
            provider_tool_call_id=provider_tool_call_id,
            canonical_tool_name="get_order",
            tool_registry_version=tool_registry_version,
            validated_task_state_version=(
                authorized_command.validated_task_state_version
            ),
            argument_binding_refs=authorized_command.argument_binding_refs,
            effect=ToolEffect.READ,
            attempt_count=0,
            status=ToolCallStatus.CREATED,
            started_at=started_at,
        )
        insert_result = await self._runtime_record_port.insert_tool_call(
            CreateToolCallCommand(created_record=created)
        )
        if insert_result is not InsertOnlyWriteResult.INSERTED:
            raise ReadToolExecutionError("ToolCall insert conflict")

        attempt = ToolAttemptRecord(
            tool_call_id=created.tool_call_id,
            attempt_no=1,
            started_at=self._clock(),
        )
        running = _project_tool_call(
            created,
            status=ToolCallStatus.RUNNING,
            attempt_count=1,
        )
        fence_result = (
            await self._runtime_record_port.start_tool_call_if_created(
                DispatchToolCallCommand(
                    expected_created_record=created,
                    running_record=running,
                    started_attempt=attempt,
                )
            )
        )
        if fence_result is not ToolDispatchFenceWriteResult.APPLIED:
            return ReadToolExecution(
                created_tool_call=created,
                dispatch_fence_result=fence_result,
                effective_timeout_ms=effective_timeout_ms,
            )

        try:
            try:
                async with asyncio.timeout(effective_timeout_ms / 1000):
                    candidate_result = await self._get_order_port.get_order(
                        GetOrderQuery(
                            customer_id=owner_scope.customer_id,
                            order_id=order_id,
                        )
                    )
            except TimeoutError:
                terminal, finalized_attempt = (
                    await self._finalize_running_attempt(
                        running=running,
                        attempt=attempt,
                        terminal_status=ToolCallStatus.TIMED_OUT,
                        tool_outcome=ToolResultOutcome.TIMEOUT,
                        safe_failure_code="TOOL_CALL_TIMEOUT",
                        timeout_phase=ToolTimeoutPhase.AFTER_DISPATCH,
                    )
                )
                return ReadToolExecution(
                    created_tool_call=created,
                    dispatch_fence_result=fence_result,
                    terminal_tool_call=terminal,
                    finalized_attempt=finalized_attempt,
                    get_order_outcome=GetOrderOutcome.SYSTEM_FAILURE,
                    effective_timeout_ms=effective_timeout_ms,
                )
            result = _canonical_get_order_result(candidate_result)
            candidate_result = None
            if result is None:
                result = GetOrderResult(
                    outcome=GetOrderOutcome.SYSTEM_FAILURE,
                    failure_code="ORDER_SERVICE_UNAVAILABLE",
                )

            observation: OrderObservation | None = None
            if result.outcome is GetOrderOutcome.FOUND:
                summary = result.order_summary
                if summary is None:
                    raise ReadToolExecutionError(
                        "FOUND result missing safe projection"
                    )
                terminal_status = ToolCallStatus.SUCCEEDED
                safe_failure_code = None
                tool_outcome = ToolResultOutcome.SUCCESS
                result_ref = self._uuid_factory()
            elif (
                result.outcome
                is GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
            ):
                terminal_status = ToolCallStatus.FAILED
                safe_failure_code = "NOT_FOUND_OR_NOT_ACCESSIBLE"
                tool_outcome = ToolResultOutcome.BUSINESS_FAILURE
                result_ref = None
            else:
                terminal_status = ToolCallStatus.FAILED
                safe_failure_code = "ORDER_SERVICE_UNAVAILABLE"
                tool_outcome = ToolResultOutcome.SYSTEM_FAILURE
                result_ref = None

            terminal, finalized_attempt = (
                await self._finalize_running_attempt(
                    running=running,
                    attempt=attempt,
                    terminal_status=terminal_status,
                    tool_outcome=tool_outcome,
                    safe_failure_code=safe_failure_code,
                    result_ref=result_ref,
                )
            )
            finished_at = terminal.finished_at

            if result.outcome is GetOrderOutcome.FOUND:
                summary = result.order_summary
                if summary is None:
                    raise ReadToolExecutionError(
                        "FOUND result missing safe projection"
                    )
                observation = OrderObservation(
                    observation_id=self._uuid_factory(),
                    source_tool="get_order",
                    source_resource_ref=summary.order_number,
                    normalized_type="ORDER_SUMMARY",
                    normalized_value=summary,
                    observed_at=finished_at,
                    recorded_at=finished_at,
                    visibility=ObservationVisibility.MODEL_VISIBLE,
                    source_version=result.source_version,
                )
                observation_result = (
                    await self._runtime_record_port.save_observation(
                        SaveObservationCommand(
                            owner_scope=owner_scope,
                            observation_record=observation,
                            source_tool_call_record=terminal,
                        )
                    )
                )
                if observation_result not in {
                    ObservationWriteResult.INSERTED,
                    ObservationWriteResult.ALREADY_APPLIED,
                }:
                    raise ReadToolExecutionError(
                        "Observation source conflict"
                    )

            return ReadToolExecution(
                created_tool_call=created,
                dispatch_fence_result=fence_result,
                terminal_tool_call=terminal,
                finalized_attempt=finalized_attempt,
                get_order_outcome=result.outcome,
                observation=observation,
                effective_timeout_ms=effective_timeout_ms,
            )
        except asyncio.CancelledError as cancellation:
            try:
                terminal, _finalized_attempt = (
                    await self._finalize_running_attempt(
                        running=running,
                        attempt=attempt,
                        terminal_status=ToolCallStatus.INTERRUPTED,
                        tool_outcome=ToolResultOutcome.INTERRUPTED,
                        safe_failure_code="TOOL_CALL_CANCELLED",
                        interruption_reason="TOOL_CALL_CANCELLED",
                    )
                )
            except (Exception, asyncio.CancelledError) as finalization_error:
                cancellation.add_note(
                    "ToolCall cancellation finalization raised "
                    f"{type(finalization_error).__name__}"
                )
            else:
                try:
                    await self._append_interrupted_trace(terminal=terminal)
                except (Exception, asyncio.CancelledError) as trace_error:
                    cancellation.add_note(
                        "ToolCallInterrupted Trace append raised "
                        f"{type(trace_error).__name__}"
                    )
            raise


Cycle2ReadHandler = Callable[
    [ToolCallRecordV2, ToolAttemptRecordV2, int],
    Awaitable[ToolResult],
]


class Cycle2ReadToolExecution(RuntimePrivateModel):
    """Ephemeral terminal ToolCall plus its same-attempt validated result."""

    terminal_tool_call: ToolCallRecordV2
    tool_result: ToolResult | None = None

    @model_validator(mode="after")
    def result_matches_terminal_attempt(self) -> Self:
        result = self.tool_result
        if result is None:
            return self
        terminal = self.terminal_tool_call
        if (
            terminal.status not in {
                ToolCallStatus.SUCCEEDED,
                ToolCallStatus.FAILED,
                ToolCallStatus.INTERRUPTED,
            }
            or not terminal.attempts
            or result.outcome in {
                ToolResultOutcome.TIMEOUT,
                ToolResultOutcome.RESULT_UNKNOWN,
            }
            or result.tool_call_id != terminal.tool_call_id
            or result.canonical_tool_name != terminal.canonical_tool_name.value
        ):
            raise ValueError("ToolResult does not identify the terminal ToolCall")
        attempt = terminal.attempts[-1]
        if (
            attempt.finished_at != result.completed_at
            or attempt.outcome is not result.outcome
            or attempt.failure_code != result.error_code
        ):
            raise ValueError("ToolResult does not match the terminal attempt")
        return self


def _project_cycle2_tool_call(
    record: ToolCallRecordV2,
    **updates: object,
) -> ToolCallRecordV2:
    values = record.model_dump(mode="python")
    values.update(updates)
    return ToolCallRecordV2.model_validate(values, strict=True)


def _grant_exactly_authorizes_attempt(
    grant: object,
    *,
    tool_call_id: UUID,
    attempt: ToolAttemptRecordV2,
) -> bool:
    return (
        type(grant) is Cycle2ReadDispatchGrant
        and grant.write_result is Cycle2DispatchFenceWriteResult.APPLIED
        and grant.tool_call_id == tool_call_id
        and grant.attempt_no == attempt.attempt_no
        and grant.trusted_fenced_at is not None
        and grant.trusted_fenced_at >= attempt.started_at
        and grant.effective_timeout_ms is not None
    )


class Cycle2ReadToolExecutor:
    """Execute inactive Cycle 2 Reads only behind reviewed durable grants."""

    def __init__(
        self,
        *,
        runtime_record_port: Cycle2RuntimeRecordPort,
        handler: Cycle2ReadHandler,
        uuid_factory: Callable[[], UUID],
    ) -> None:
        self._runtime_record_port = runtime_record_port
        self._handler = handler
        self._uuid_factory = uuid_factory

    async def execute(
        self,
        *,
        create_command: CreateToolCallV2Command,
    ) -> ToolCallRecordV2:
        execution = await self.execute_with_result(create_command=create_command)
        return execution.terminal_tool_call

    async def execute_with_result(
        self,
        *,
        create_command: CreateToolCallV2Command,
    ) -> Cycle2ReadToolExecution:
        if type(create_command) is not CreateToolCallV2Command:
            raise ReadToolExecutionError("exact live ToolCallV2 command required")
        inserted = await (
            self._runtime_record_port.insert_initial_tool_call_v2_if_current(
                create_command
            )
        )
        if inserted is not Cycle2WriteResult.APPLIED:
            return Cycle2ReadToolExecution(
                terminal_tool_call=create_command.created_record,
            )
        return await self._execute_created_with_result(
            owner_scope=create_command.loaded_closure.owner_scope,
            created_record=create_command.created_record,
        )

    async def _load_trusted_closure(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        expected_record: ToolCallRecordV2,
    ) -> ToolRetryRecoveryReadClosureV2 | None:
        closure = await (
            self._runtime_record_port.load_tool_retry_recovery_closure_for_owner(
                owner_scope=owner_scope,
                tool_call_id=expected_record.tool_call_id,
            )
        )
        if (
            type(closure) is not ToolRetryRecoveryReadClosureV2
            or closure.owner_scope != owner_scope
            or closure.tool_call_record != expected_record
        ):
            return None
        return closure

    @staticmethod
    def _retry_revalidation(
        *,
        closure: ToolRetryRecoveryReadClosureV2,
        expected_record: ToolCallRecordV2,
    ) -> Cycle2RetryRevalidation:
        parent = expected_record.dispatch_facts()
        current_binding_ids = {
            binding.binding_id
            for binding in closure.current_input_binding_records
        }
        current_argument_refs = tuple(
            ref
            for ref in parent.argument_binding_refs
            if ref in current_binding_ids
        )
        if not current_argument_refs:
            current_argument_refs = (
                closure.current_request_unit_record.input_binding_refs
            )
        current = Cycle2ToolDispatchFacts(
            tool_call_id=parent.tool_call_id,
            run_id=closure.active_run_record.run_id,
            private_owner_scope_ref=closure.owner_scope.customer_id,
            task_id=closure.current_task_record.task_id,
            request_unit_id=closure.current_request_unit_record.request_unit_id,
            validated_task_state_version=(
                closure.current_task_record.state_version
            ),
            argument_binding_refs=current_argument_refs,
            verified_target_ref=parent.verified_target_ref,
        )
        return Cycle2RetryRevalidation(
            parent_dispatch_facts=parent,
            expected_dispatch_facts=parent,
            current_dispatch_facts=current,
            remaining_run_time_budget_ms=(
                closure.remaining_run_time_budget_ms()
            ),
        )

    async def _execute_created(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        created_record: ToolCallRecordV2,
    ) -> ToolCallRecordV2:
        execution = await self._execute_created_with_result(
            owner_scope=owner_scope,
            created_record=created_record,
        )
        return execution.terminal_tool_call

    async def _execute_created_with_result(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        created_record: ToolCallRecordV2,
    ) -> Cycle2ReadToolExecution:
        if (
            type(owner_scope) is not TrustedOwnerScope
            or type(created_record) is not ToolCallRecordV2
            or created_record.status is not ToolCallStatus.CREATED
            or created_record.attempt_count != 0
            or created_record.attempts
        ):
            raise ReadToolExecutionError("clean owner-scoped CREATED ToolCallV2 required")
        closure = await self._load_trusted_closure(
            owner_scope=owner_scope,
            expected_record=created_record,
        )
        if closure is None:
            return Cycle2ReadToolExecution(terminal_tool_call=created_record)
        attempt = ToolAttemptRecordV2(
            tool_call_id=created_record.tool_call_id,
            attempt_no=1,
            started_at=closure.trusted_read_at,
        )
        running = _project_cycle2_tool_call(
            created_record,
            status=ToolCallStatus.RUNNING,
            attempts=(attempt,),
            attempt_count=1,
        )
        grant = await (
            self._runtime_record_port.append_initial_tool_attempt_if_current(
                AppendInitialToolAttemptV2Command(
                    loaded_closure=closure,
                    attempt_append_command=AppendToolAttemptV2Command(
                        owner_scope=owner_scope,
                        expected_record=created_record,
                        next_running_record=running,
                        started_attempt=attempt,
                    ),
                )
            )
        )
        if not _grant_exactly_authorizes_attempt(
            grant,
            tool_call_id=created_record.tool_call_id,
            attempt=attempt,
        ):
            return Cycle2ReadToolExecution(terminal_tool_call=created_record)
        return await self._dispatch_started_attempt_with_result(
            owner_scope=owner_scope,
            running_record=running,
            started_attempt=attempt,
            effective_timeout_ms=grant.effective_timeout_ms,
        )

    async def _dispatch_started_attempt(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        running_record: ToolCallRecordV2,
        started_attempt: ToolAttemptRecordV2,
        effective_timeout_ms: int,
    ) -> ToolCallRecordV2:
        execution = await self._dispatch_started_attempt_with_result(
            owner_scope=owner_scope,
            running_record=running_record,
            started_attempt=started_attempt,
            effective_timeout_ms=effective_timeout_ms,
        )
        return execution.terminal_tool_call

    async def _dispatch_started_attempt_with_result(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        running_record: ToolCallRecordV2,
        started_attempt: ToolAttemptRecordV2,
        effective_timeout_ms: int,
    ) -> Cycle2ReadToolExecution:
        timeout_phase: ToolTimeoutPhase | None = None
        tool_result: ToolResult | None = None
        try:
            async with asyncio.timeout(effective_timeout_ms / 1000):
                result = await self._handler(
                    running_record,
                    started_attempt,
                    effective_timeout_ms,
                )
        except TimeoutError:
            outcome = ToolResultOutcome.TIMEOUT
            failure_code = "TOOL_CALL_TIMEOUT"
            timeout_phase = ToolTimeoutPhase.AFTER_DISPATCH
            finished_at = None
        else:
            if (
                type(result) is not ToolResult
                or result.tool_call_id != running_record.tool_call_id
                or result.canonical_tool_name
                != running_record.canonical_tool_name.value
                or result.outcome is ToolResultOutcome.RESULT_UNKNOWN
                or result.completed_at < started_attempt.started_at
            ):
                raise ReadToolExecutionError("invalid Cycle 2 handler result")
            tool_result = result
            outcome = result.outcome
            failure_code = result.error_code
            finished_at = result.completed_at
            if outcome is ToolResultOutcome.TIMEOUT:
                timeout_phase = ToolTimeoutPhase.AFTER_DISPATCH

        closure = await self._load_trusted_closure(
            owner_scope=owner_scope,
            expected_record=running_record,
        )
        if closure is None:
            return Cycle2ReadToolExecution(terminal_tool_call=running_record)
        revalidation = self._retry_revalidation(
            closure=closure,
            expected_record=running_record,
        )
        if finished_at is None:
            finished_at = closure.trusted_read_at
        retry = decide_cycle2_tool_retry(
            canonical_tool_name=running_record.canonical_tool_name,
            attempt_no=started_attempt.attempt_no,
            outcome=outcome,
            failure_code=failure_code,
            revalidation=revalidation,
        )
        finalized = ToolAttemptRecordV2(
            tool_call_id=started_attempt.tool_call_id,
            attempt_no=started_attempt.attempt_no,
            started_at=started_attempt.started_at,
            finished_at=finished_at,
            outcome=outcome,
            failure_code=failure_code,
            timeout_phase=timeout_phase,
            retry_decision=retry,
        )
        if retry is ToolRetryDecision.RETRY_SCHEDULED:
            next_record = _project_cycle2_tool_call(
                running_record,
                attempts=(*running_record.attempts[:-1], finalized),
            )
        else:
            terminal = project_cycle2_tool_terminal(
                finalized,
                canonical_tool_name=running_record.canonical_tool_name,
            )
            next_record = _project_cycle2_tool_call(
                running_record,
                attempts=(*running_record.attempts[:-1], finalized),
                status=terminal.status,
                finished_at=terminal.finished_at,
                failure_code=terminal.failure_code,
                timeout_phase=terminal.timeout_phase,
                interruption_reason=terminal.interruption_reason,
                result_ref=(
                    self._uuid_factory()
                    if terminal.status is ToolCallStatus.SUCCEEDED
                    else None
                ),
            )
        finalized_result = await (
            self._runtime_record_port.finalize_tool_attempt_if_current(
                FinalizeToolAttemptV2Command(
                    owner_scope=owner_scope,
                    expected_running_record=running_record,
                    finalized_attempt=finalized,
                    next_record=next_record,
                )
            )
        )
        if finalized_result is not Cycle2WriteResult.APPLIED:
            return Cycle2ReadToolExecution(terminal_tool_call=running_record)
        if retry is not ToolRetryDecision.RETRY_SCHEDULED:
            return Cycle2ReadToolExecution(
                terminal_tool_call=next_record,
                tool_result=(
                    tool_result
                    if outcome is not ToolResultOutcome.TIMEOUT
                    else None
                ),
            )

        from mini_agent.application.restart_recovery_service import (
            Cycle2ToolRestartRecoveryService,
        )

        recovery = Cycle2ToolRestartRecoveryService(
            runtime_record_port=self._runtime_record_port,
            uuid_factory=self._uuid_factory,
        )
        recovered, second, grant = await recovery.recover_tool_call(
            owner_scope=owner_scope,
            tool_call_id=next_record.tool_call_id,
        )
        if (
            second is None
            or not _grant_exactly_authorizes_attempt(
                grant,
                tool_call_id=next_record.tool_call_id,
                attempt=second,
            )
        ):
            return Cycle2ReadToolExecution(terminal_tool_call=recovered)
        return await self._dispatch_started_attempt_with_result(
            owner_scope=owner_scope,
            running_record=recovered,
            started_attempt=second,
            effective_timeout_ms=grant.effective_timeout_ms,
        )
