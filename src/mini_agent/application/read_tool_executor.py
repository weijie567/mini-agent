"""Durably fenced execution of the single P0 ``get_order`` Read Tool."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from mini_agent.application.ports import GetOrderPort, RuntimeRecordPort
from mini_agent.application.records import (
    ConditionalWriteResult,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    FinalizeToolCallCommand,
    InsertOnlyWriteResult,
    ObservationWriteResult,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
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
)
from mini_agent.core.tool_system import (
    AuthorizedToolCommand,
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
    ToolResultOutcome,
)


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
    ) -> ReadToolExecution:
        if type(owner_scope) is not TrustedOwnerScope:
            raise ReadToolExecutionError("trusted owner scope required")
        if type(authorized_command) is not AuthorizedToolCommand:
            raise ReadToolExecutionError("authorized command required")
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
            )

        result = await self._get_order_port.get_order(
            GetOrderQuery(
                customer_id=owner_scope.customer_id,
                order_id=order_id,
            )
        )
        finished_at = self._clock()
        observation: OrderObservation | None = None
        if result.outcome is GetOrderOutcome.FOUND:
            summary = result.order_summary
            if summary is None:
                raise ReadToolExecutionError("FOUND result missing safe projection")
            terminal_status = ToolCallStatus.SUCCEEDED
            safe_failure_code = None
            tool_outcome = ToolResultOutcome.SUCCESS
            result_ref = self._uuid_factory()
        elif result.outcome is GetOrderOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE:
            terminal_status = ToolCallStatus.FAILED
            safe_failure_code = "NOT_FOUND_OR_NOT_ACCESSIBLE"
            tool_outcome = ToolResultOutcome.BUSINESS_FAILURE
            result_ref = None
        else:
            terminal_status = ToolCallStatus.FAILED
            safe_failure_code = "ORDER_SERVICE_UNAVAILABLE"
            tool_outcome = ToolResultOutcome.SYSTEM_FAILURE
            result_ref = None

        terminal = _project_tool_call(
            running,
            status=terminal_status,
            finished_at=finished_at,
            failure_code=safe_failure_code,
            result_ref=result_ref,
        )
        finalized_attempt = ToolAttemptRecord(
            tool_call_id=running.tool_call_id,
            attempt_no=1,
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

        if result.outcome is GetOrderOutcome.FOUND:
            summary = result.order_summary
            if summary is None:
                raise ReadToolExecutionError("FOUND result missing safe projection")
            observation = OrderObservation(
                observation_id=self._uuid_factory(),
                source_tool="get_order",
                source_resource_ref=summary.order_number,
                normalized_type="ORDER_SUMMARY",
                normalized_value=summary,
                observed_at=finished_at,
                recorded_at=finished_at,
                visibility=ObservationVisibility.MODEL_VISIBLE,
            )
            observation_result = await self._runtime_record_port.save_observation(
                SaveObservationCommand(
                    owner_scope=owner_scope,
                    observation_record=observation,
                    source_tool_call_record=terminal,
                )
            )
            if observation_result not in {
                ObservationWriteResult.INSERTED,
                ObservationWriteResult.ALREADY_APPLIED,
            }:
                raise ReadToolExecutionError("Observation source conflict")

        return ReadToolExecution(
            created_tool_call=created,
            dispatch_fence_result=fence_result,
            terminal_tool_call=terminal,
            finalized_attempt=finalized_attempt,
            get_order_outcome=result.outcome,
            observation=observation,
        )
