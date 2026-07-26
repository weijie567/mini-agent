import inspect
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

from mini_agent.application.ports import (
    ConversationRecordPort,
    EvalResultPort,
    GetOrderPort,
    ModelProvider,
    RestartRecoveryPort,
    RuntimeRecordPort,
    SessionAuthPort,
)
from mini_agent.application.records import (
    ConditionalWriteResult,
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
from mini_agent.core.task_state import RequestUnitRecord, TaskRecord
from mini_agent.core.tool_system import ToolCallRecord
from mini_agent.core.trace import AgentRunRecord


class CandidateOnlyProvider:
    async def propose_next_move(self, request: object) -> object:
        raise NotImplementedError

    async def plan_presentation(self, request: object) -> object:
        raise NotImplementedError


def _assert_signature(
    method: object,
    *,
    parameters: tuple[str, ...],
    type_hints: dict[str, object],
) -> None:
    signature = inspect.signature(method)
    assert tuple(signature.parameters) == ("self", *parameters)
    assert get_type_hints(method, include_extras=True) == type_hints


def test_model_provider_surface_only_proposes_validated_candidates() -> None:
    provider = CandidateOnlyProvider()

    assert isinstance(provider, ModelProvider)
    assert not hasattr(provider, "execute_tool")
    assert not hasattr(provider, "save_task")


def test_ports_are_protocols_owned_by_application() -> None:
    assert ModelProvider._is_protocol
    assert SessionAuthPort._is_protocol
    assert GetOrderPort._is_protocol
    assert ConversationRecordPort._is_protocol
    assert RuntimeRecordPort._is_protocol
    assert EvalResultPort._is_protocol
    assert RestartRecoveryPort._is_protocol


def test_runtime_record_port_preserves_append_only_causality_records() -> None:
    assert hasattr(RuntimeRecordPort, "append_accepted_task_delta")
    assert hasattr(RuntimeRecordPort, "append_task_state_transition")
    assert hasattr(RuntimeRecordPort, "append_trace_event")
    assert hasattr(ConversationRecordPort, "append_message")
    assert hasattr(RuntimeRecordPort, "compare_and_set_run_task_link")
    for bypass in (
        "save_run",
        "save_task",
        "save_request_unit",
        "save_tool_call",
        "append_tool_attempt",
    ):
        assert not hasattr(RuntimeRecordPort, bypass)


def test_initial_inserts_use_validated_commands_and_explicit_results() -> None:
    insert_methods = (
        (
            RuntimeRecordPort.insert_run,
            CreateRunCommand,
        ),
        (
            RuntimeRecordPort.insert_task,
            CreateTaskCommand,
        ),
        (
            RuntimeRecordPort.insert_request_unit,
            CreateRequestUnitCommand,
        ),
        (
            RuntimeRecordPort.create_run_task_link,
            CreateRunTaskLinkCommand,
        ),
        (
            RuntimeRecordPort.insert_tool_call,
            CreateToolCallCommand,
        ),
    )
    for method, command_type in insert_methods:
        _assert_signature(
            method,
            parameters=("command",),
            type_hints={
                "command": command_type,
                "return": InsertOnlyWriteResult,
            },
        )

    assert set(InsertOnlyWriteResult) == {
        InsertOnlyWriteResult.INSERTED,
        InsertOnlyWriteResult.ALREADY_EXISTS,
    }
    for method, _command_type in insert_methods:
        assert "never upsert" in (method.__doc__ or "") or "never overwrite" in (
            method.__doc__ or ""
        )


def test_normal_run_transition_is_an_exact_projection_cas() -> None:
    _assert_signature(
        RuntimeRecordPort.transition_run_if_active,
        parameters=("command",),
        type_hints={
            "command": TransitionRunCommand,
            "return": ConditionalWriteResult,
        },
    )
    assert set(ConditionalWriteResult) == {
        ConditionalWriteResult.APPLIED,
        ConditionalWriteResult.PROJECTION_CONFLICT,
        ConditionalWriteResult.NOT_APPLICABLE,
    }


def test_owner_scoped_reads_require_minimal_trusted_owner_scope() -> None:
    scoped_methods = (
        ConversationRecordPort.load_conversation_for_owner,
        ConversationRecordPort.list_messages_for_owner,
        ConversationRecordPort.list_conversation_task_links_for_owner,
        RuntimeRecordPort.load_run_for_owner,
        RuntimeRecordPort.load_task_for_owner,
        RuntimeRecordPort.load_request_unit_for_owner,
        RuntimeRecordPort.load_request_understanding_for_owner,
        RuntimeRecordPort.load_accepted_task_delta_for_owner,
        RuntimeRecordPort.load_input_binding_for_owner,
        RuntimeRecordPort.load_context_manifest_for_owner,
        RuntimeRecordPort.load_gate_decision_for_owner,
        RuntimeRecordPort.load_tool_call_for_owner,
        RuntimeRecordPort.load_observation_for_owner,
        RuntimeRecordPort.list_run_task_links_for_owner,
        RuntimeRecordPort.list_trace_events_for_owner,
    )

    for method in scoped_methods:
        signature = inspect.signature(method)
        assert "owner_scope" in signature.parameters
        assert "customer_context" not in signature.parameters
        assert "owner_customer_id" not in signature.parameters
        assert get_type_hints(method)["owner_scope"] is TrustedOwnerScope


def test_owner_scoped_read_shapes_hide_absent_vs_foreign_resources() -> None:
    optional_loads = (
        ConversationRecordPort.load_conversation_for_owner,
        RuntimeRecordPort.load_run_for_owner,
        RuntimeRecordPort.load_task_for_owner,
        RuntimeRecordPort.load_request_unit_for_owner,
        RuntimeRecordPort.load_request_understanding_for_owner,
        RuntimeRecordPort.load_accepted_task_delta_for_owner,
        RuntimeRecordPort.load_input_binding_for_owner,
        RuntimeRecordPort.load_context_manifest_for_owner,
        RuntimeRecordPort.load_gate_decision_for_owner,
        RuntimeRecordPort.load_tool_call_for_owner,
        RuntimeRecordPort.load_observation_for_owner,
    )
    empty_tuple_loads = (
        ConversationRecordPort.list_messages_for_owner,
        ConversationRecordPort.list_conversation_task_links_for_owner,
        RuntimeRecordPort.list_run_task_links_for_owner,
        RuntimeRecordPort.list_trace_events_for_owner,
    )

    for method in optional_loads:
        assert "None" in str(inspect.signature(method).return_annotation)
    for method in empty_tuple_loads:
        assert "tuple[" in str(inspect.signature(method).return_annotation)


def test_state_writes_expose_explicit_version_conflict_semantics() -> None:
    assert set(VersionedWriteResult) == {
        VersionedWriteResult.APPLIED,
        VersionedWriteResult.VERSION_CONFLICT,
        VersionedWriteResult.NOT_APPLICABLE,
    }
    state_methods = (
        (
            RuntimeRecordPort.compare_and_set_task,
            TaskRecord,
        ),
        (
            RuntimeRecordPort.compare_and_set_request_unit,
            RequestUnitRecord,
        ),
        (
            RestartRecoveryPort.compare_and_set_task_for_restart,
            TaskRecord,
        ),
        (
            RestartRecoveryPort.compare_and_set_request_unit_for_restart,
            RequestUnitRecord,
        ),
    )
    for method, record_type in state_methods:
        _assert_signature(
            method,
            parameters=("record", "expected_state_version"),
            type_hints={
                "record": record_type,
                "expected_state_version": PositiveStateVersion,
                "return": VersionedWriteResult,
            },
        )

    link_methods = (
        RuntimeRecordPort.compare_and_set_run_task_link,
        RestartRecoveryPort.compare_and_set_run_task_link_for_restart,
    )
    for method in link_methods:
        _assert_signature(
            method,
            parameters=("record", "expected_result_task_state_version"),
            type_hints={
                "record": RunTaskLinkRecord,
                "expected_result_task_state_version": (
                    PositiveStateVersion | None
                ),
                "return": VersionedWriteResult,
            },
        )


def test_tool_dispatch_requires_an_explicit_durable_fence_result() -> None:
    _assert_signature(
        RuntimeRecordPort.start_tool_call_if_created,
        parameters=("command",),
        type_hints={
            "command": DispatchToolCallCommand,
            "return": ToolDispatchFenceWriteResult,
        },
    )
    _assert_signature(
        RuntimeRecordPort.finalize_tool_call_attempt_if_running,
        parameters=("command",),
        type_hints={
            "command": FinalizeToolCallCommand,
            "return": ConditionalWriteResult,
        },
    )
    assert set(FinalizeToolCallCommand.model_fields) == {
        "expected_running_record",
        "expected_started_attempt",
        "terminal_record",
        "finalized_attempt",
    }
    assert "started-attempt" in (
        RuntimeRecordPort.finalize_tool_call_attempt_if_running.__doc__ or ""
    )
    assert set(ToolDispatchFenceWriteResult) == {
        ToolDispatchFenceWriteResult.APPLIED,
        ToolDispatchFenceWriteResult.STATUS_CONFLICT,
        ToolDispatchFenceWriteResult.NOT_APPLICABLE,
        ToolDispatchFenceWriteResult.ACTION_LEDGER_REQUIRED,
    }
    dispatch_doc = RuntimeRecordPort.start_tool_call_if_created.__doc__ or ""
    assert "CAS expected CREATED" in dispatch_doc
    assert "APPLIED is the only result" in dispatch_doc
    assert "finished_at=None" in dispatch_doc
    assert "outcome=None" in dispatch_doc
    assert "failure_code=None" in dispatch_doc
    assert "ACTION_LEDGER_REQUIRED" in dispatch_doc


def test_restart_recovery_is_a_system_only_data_capability() -> None:
    method_names = {
        name
        for name, value in inspect.getmembers(
            RestartRecoveryPort, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    }
    assert "claim_and_mark_run_incomplete_if_active" in method_names
    assert "interrupt_tool_call_if_active" in method_names
    assert {
        "list_runs_pending_restart_recovery",
        "list_tool_calls_pending_restart_recovery",
        "list_run_task_links_pending_restart_recovery",
        "list_tasks_pending_restart_recovery",
        "list_request_units_pending_restart_recovery",
    }.issubset(method_names)
    assert not any(
        forbidden in name
        for name in method_names
        for forbidden in ("execute", "resume", "invoke", "callback")
    )
    _assert_signature(
        RestartRecoveryPort.list_runs_pending_restart_recovery,
        parameters=(),
        type_hints={"return": tuple[AgentRunRecord, ...]},
    )
    recovery_lists = (
        (
            RestartRecoveryPort.list_tool_calls_pending_restart_recovery,
            tuple[ToolCallRecord, ...],
        ),
        (
            RestartRecoveryPort.list_run_task_links_pending_restart_recovery,
            tuple[RunTaskLinkRecord, ...],
        ),
        (
            RestartRecoveryPort.list_tasks_pending_restart_recovery,
            tuple[TaskRecord, ...],
        ),
        (
            RestartRecoveryPort.list_request_units_pending_restart_recovery,
            tuple[RequestUnitRecord, ...],
        ),
    )
    for method, return_type in recovery_lists:
        _assert_signature(
            method,
            parameters=("run_id",),
            type_hints={
                "run_id": UUID,
                "return": return_type,
            },
        )
    _assert_signature(
        RestartRecoveryPort.claim_and_mark_run_incomplete_if_active,
        parameters=("command",),
        type_hints={
            "command": MarkRunIncompleteForRecoveryCommand,
            "return": RecoveryWriteResult,
        },
    )
    _assert_signature(
        RestartRecoveryPort.interrupt_tool_call_if_active,
        parameters=("command",),
        type_hints={
            "command": InterruptToolCallForRecoveryCommand,
            "return": RecoveryWriteResult,
        },
    )

    annotations = " ".join(
        str(inspect.signature(getattr(RestartRecoveryPort, name)))
        for name in method_names
    )
    for forbidden_type in (
        "CustomerContext",
        "MessageRecord",
        "OrderObservation",
        "Prompt",
        "Callable",
    ):
        assert forbidden_type not in annotations
    assert "CREATED or RUNNING" in (
        RestartRecoveryPort.list_runs_pending_restart_recovery.__doc__ or ""
    )
    assert set(RecoveryWriteResult) == {
        RecoveryWriteResult.APPLIED,
        RecoveryWriteResult.STATUS_CONFLICT,
        RecoveryWriteResult.NOT_APPLICABLE,
        RecoveryWriteResult.RECONCILIATION_REQUIRED,
    }


def test_eval_result_port_is_isolated_from_runtime_records() -> None:
    _assert_signature(
        EvalResultPort.append_eval_result,
        parameters=("record",),
        type_hints={
            "record": EvalResultRecord,
            "return": InsertOnlyWriteResult,
        },
    )
    _assert_signature(
        EvalResultPort.load_eval_result,
        parameters=("eval_run_id", "case_id", "lane", "attempt"),
        type_hints={
            "eval_run_id": UUID,
            "case_id": NonEmptyString,
            "lane": NonEmptyString,
            "attempt": PositiveAttempt,
            "return": EvalResultRecord | None,
        },
    )
    _assert_signature(
        EvalResultPort.list_eval_results,
        parameters=("eval_run_id",),
        type_hints={
            "eval_run_id": UUID,
            "return": tuple[EvalResultRecord, ...],
        },
    )
    _assert_signature(
        EvalResultPort.append_eval_execution_failure,
        parameters=("record",),
        type_hints={
            "record": EvalExecutionFailureRecord,
            "return": type(None),
        },
    )
    _assert_signature(
        EvalResultPort.list_eval_execution_failures,
        parameters=("eval_run_id",),
        type_hints={
            "eval_run_id": UUID,
            "return": tuple[EvalExecutionFailureRecord, ...],
        },
    )
    load_signature = inspect.signature(EvalResultPort.load_eval_result)
    for parameter_name in ("eval_run_id", "case_id", "lane", "attempt"):
        assert (
            load_signature.parameters[parameter_name].kind
            is inspect.Parameter.KEYWORD_ONLY
        )
    assert "never overwrites history" in (
        EvalResultPort.append_eval_result.__doc__ or ""
    )
    assert not hasattr(RuntimeRecordPort, "append_eval_result")
    assert not hasattr(EvalResultPort, "save_task")


def test_protocol_contracts_do_not_claim_adapter_behavior_is_verified() -> None:
    for protocol in (RuntimeRecordPort, EvalResultPort, RestartRecoveryPort):
        assert "does not verify an Adapter" in (protocol.__doc__ or "")


def test_core_and_application_source_have_no_framework_or_adapter_imports() -> None:
    source_root = Path(__file__).parents[3] / "src" / "mini_agent"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for package in ("core", "application")
        for path in sorted((source_root / package).glob("*.py"))
    ).casefold()

    forbidden_imports = (
        "import fastapi",
        "from fastapi",
        "import sqlalchemy",
        "from sqlalchemy",
        "import psycopg",
        "from psycopg",
        "import httpx",
        "from httpx",
        "import openai",
        "from openai",
    )
    for forbidden_import in forbidden_imports:
        assert forbidden_import not in source
