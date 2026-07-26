import inspect
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

from mini_agent.application.ports import (
    AgentRunHandler,
    ConversationRecordPort,
    EvalResultPort,
    GetOrderPort,
    ModelProvider,
    RestartRecoveryPort,
    RuntimeRecordPort,
    SessionAuthPort,
)
from mini_agent.application.records import (
    AgentRunCommand,
    AgentRunResult,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    CreateInitialTaskGraphCommand,
    CreateRunCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    FinalizeRunCommand,
    FinalizeToolCallCommand,
    InsertOnlyWriteResult,
    NonEmptyString,
    ObservationWriteResult,
    PositiveAttempt,
    ProviderProtocolError,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
)


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


def test_application_inbound_handler_and_provider_failure_surface_are_exact() -> None:
    _assert_signature(
        AgentRunHandler.handle,
        parameters=("command",),
        type_hints={
            "command": AgentRunCommand,
            "return": AgentRunResult,
        },
    )
    assert "trusted" in (AgentRunHandler.__doc__ or "").casefold()
    provider_doc = ModelProvider.__doc__ or ""
    assert "ProviderProtocolError" in provider_doc
    assert "from None" in provider_doc
    assert "__cause__" in provider_doc
    assert "__context__" in provider_doc
    assert "after discarding the raw exception" in provider_doc
    assert inspect.signature(ProviderProtocolError).parameters == {}


def test_ports_are_protocols_owned_by_application() -> None:
    assert ModelProvider._is_protocol
    assert AgentRunHandler._is_protocol
    assert SessionAuthPort._is_protocol
    assert GetOrderPort._is_protocol
    assert ConversationRecordPort._is_protocol
    assert RuntimeRecordPort._is_protocol
    assert EvalResultPort._is_protocol
    assert RestartRecoveryPort._is_protocol


def test_runtime_record_port_preserves_only_safe_append_causality_records() -> None:
    assert hasattr(RuntimeRecordPort, "append_trace_event")
    assert hasattr(ConversationRecordPort, "append_message")
    for bypass in (
        "save_run",
        "save_task",
        "save_request_unit",
        "save_tool_call",
        "append_tool_attempt",
        "save_request_understanding",
        "append_accepted_task_delta",
        "save_input_binding",
        "insert_task",
        "insert_request_unit",
        "create_run_task_link",
        "append_task_state_transition",
        "compare_and_set_task",
        "compare_and_set_request_unit",
        "transition_run_if_active",
        "compare_and_set_run_task_link",
    ):
        assert not hasattr(RuntimeRecordPort, bypass)
    assert not hasattr(ConversationRecordPort, "save_conversation_task_link")


def test_independent_inserts_are_limited_to_run_and_tool_call_roots() -> None:
    insert_methods = (
        (
            RuntimeRecordPort.insert_run,
            CreateRunCommand,
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


def test_run_start_and_atomic_finalization_are_separate_exact_projection_cas() -> None:
    _assert_signature(
        RuntimeRecordPort.start_run_if_created,
        parameters=("command",),
        type_hints={
            "command": TransitionRunCommand,
            "return": ConditionalWriteResult,
        },
    )
    _assert_signature(
        RuntimeRecordPort.finalize_run_if_active,
        parameters=("command",),
        type_hints={
            "command": FinalizeRunCommand,
            "return": ConditionalWriteResult,
        },
    )
    assert "CREATED" in (RuntimeRecordPort.start_run_if_created.__doc__ or "")
    finalize_doc = RuntimeRecordPort.finalize_run_if_active.__doc__ or ""
    assert "RunTaskLink" in finalize_doc
    assert "atomically" in finalize_doc
    assert set(ConditionalWriteResult) == {
        ConditionalWriteResult.APPLIED,
        ConditionalWriteResult.PROJECTION_CONFLICT,
        ConditionalWriteResult.NOT_APPLICABLE,
    }


def test_initial_graph_task_transition_and_observation_use_aggregate_commands() -> None:
    contracts = (
        (
            RuntimeRecordPort.create_initial_task_graph_if_current,
            CreateInitialTaskGraphCommand,
            ConditionalWriteResult,
        ),
        (
            RuntimeRecordPort.apply_task_transition_if_current,
            ApplyTaskTransitionCommand,
            ConditionalWriteResult,
        ),
        (
            RuntimeRecordPort.save_observation,
            SaveObservationCommand,
            ObservationWriteResult,
        ),
    )
    for method, command_type, result_type in contracts:
        _assert_signature(
            method,
            parameters=("command",),
            type_hints={
                "command": command_type,
                "return": result_type,
            },
        )
    observation_doc = RuntimeRecordPort.save_observation.__doc__ or ""
    assert "owner graph" in observation_doc
    assert "owner_scope" in observation_doc


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


def test_split_state_and_link_writes_are_not_exposed() -> None:
    removed = {
        "append_task_state_transition",
        "compare_and_set_task",
        "compare_and_set_request_unit",
        "compare_and_set_run_task_link",
    }
    assert all(not hasattr(RuntimeRecordPort, name) for name in removed)


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
    assert method_names == {
        "load_next_restart_recovery_closure",
        "claim_and_apply_restart_recovery",
    }
    removed = {
        "list_runs_pending_restart_recovery",
        "list_tool_calls_pending_restart_recovery",
        "list_run_task_links_pending_restart_recovery",
        "list_tasks_pending_restart_recovery",
        "list_request_units_pending_restart_recovery",
        "claim_and_mark_run_incomplete_if_active",
        "interrupt_tool_call_if_active",
        "compare_and_set_run_task_link_for_restart",
        "compare_and_set_task_for_restart",
        "compare_and_set_request_unit_for_restart",
    }
    assert method_names.isdisjoint(removed)
    assert not any(
        forbidden in name
        for name in method_names
        for forbidden in ("execute", "resume", "invoke", "callback")
    )
    _assert_signature(
        RestartRecoveryPort.load_next_restart_recovery_closure,
        parameters=(),
        type_hints={"return": RestartRecoveryClosure | None},
    )
    _assert_signature(
        RestartRecoveryPort.claim_and_apply_restart_recovery,
        parameters=("command",),
        type_hints={
            "command": ApplyRestartRecoveryCommand,
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
    load_doc = RestartRecoveryPort.load_next_restart_recovery_closure.__doc__ or ""
    normalized_load_doc = " ".join(load_doc.split())
    assert "None only" in normalized_load_doc
    assert "P0PersistenceIntegrityError" in normalized_load_doc
    assert "snapshot" in normalized_load_doc
    assert "closed-set completeness" in normalized_load_doc
    assert "LIMIT 2" in normalized_load_doc
    assert "stream cutoff" in normalized_load_doc
    assert "before materializing" in normalized_load_doc
    apply_doc = RestartRecoveryPort.claim_and_apply_restart_recovery.__doc__ or ""
    assert "exact closure fence" in apply_doc
    assert "zero writes" in apply_doc
    assert "RUNNING ACTION" in apply_doc
    assert "RECONCILIATION_REQUIRED" in apply_doc
    assert "RESULT_UNKNOWN" in apply_doc
    assert "neither INTERRUPTED nor any Run/Task/link" in apply_doc
    assert set(RecoveryWriteResult) == {
        RecoveryWriteResult.APPLIED,
        RecoveryWriteResult.CLOSURE_CONFLICT,
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
