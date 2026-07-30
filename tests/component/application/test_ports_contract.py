import ast
import inspect
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

import mini_agent.application.ports as application_ports_module
import mini_agent.application.records as application_records_module
from mini_agent.application.ports import (
    AgentRunHandler,
    ConversationRecordPort,
    ExactRunEvidencePort,
    EvalResultPort,
    GetOrderPort,
    ModelProviderV2,
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
    CreateInitialTaskGraphV2Command,
    CreateRunCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    ExactRunEvidenceClosure,
    FinalizeRunCommand,
    FinalizeToolCallCommand,
    InsertOnlyWriteResult,
    NonEmptyString,
    ObservationWriteResult,
    PositiveAttempt,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    SaveRequestUnderstandingV2NoTaskCommand,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
)


class CandidateOnlyProvider:
    async def propose_next_move(self, request: object) -> object:
        raise NotImplementedError

    async def plan_presentation(self, request: object) -> object:
        raise NotImplementedError


def _folded_static_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _folded_static_string(node.left)
        right = _folded_static_string(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        parts = tuple(_folded_static_string(value) for value in node.values)
        return "".join(parts) if all(part is not None for part in parts) else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and len(node.args) == 1
        and not node.keywords
    ):
        separator = _folded_static_string(node.func.value)
        values = node.args[0]
        if separator is not None and isinstance(values, (ast.List, ast.Tuple)):
            parts = tuple(_folded_static_string(value) for value in values.elts)
            return (
                separator.join(parts)
                if all(part is not None for part in parts)
                else None
            )
    return None


def test_application_ru_v1_records_and_ports_are_not_executable() -> None:
    legacy_identifiers = frozenset(
        {
            "AcceptedTaskDelta",
            "CandidateValidationRecord",
            "CreateInitialTaskGraphCommand",
            "ModelProvider",
            "RequestUnderstandingOutput",
            "RequestUnderstandingRecord",
            "SaveRequestUnderstandingCommand",
            "create_initial_task_graph_if_current",
            "load_accepted_task_delta_for_owner",
            "load_request_understanding_for_owner",
        }
    )
    targeted_modules = frozenset(
        {
            "mini_agent.application.ports",
            "mini_agent.application.records",
            "mini_agent.core.request_understanding",
            "mini_agent.core.task_state",
        }
    )
    repo_root = Path(__file__).parents[3]
    owned_paths = (
        repo_root / "src/mini_agent/application/records.py",
        repo_root / "src/mini_agent/application/ports.py",
        repo_root / "tests/component/application/test_record_contracts.py",
        repo_root / "tests/component/application/test_ports_contract.py",
    )
    executable_hits: set[tuple[str, int, str]] = set()

    for owned_path in owned_paths:
        tree = ast.parse(owned_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in targeted_modules and any(
                    alias.name == "*" for alias in node.names
                ):
                    executable_hits.add(
                        (owned_path.name, node.lineno, "target-module-star-import")
                    )
                for alias in node.names:
                    if alias.name in legacy_identifiers:
                        executable_hits.add(
                            (owned_path.name, node.lineno, alias.name)
                        )
            if isinstance(
                node,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ) and node.name in legacy_identifiers:
                executable_hits.add((owned_path.name, node.lineno, node.name))
            if isinstance(node, ast.Name) and node.id in legacy_identifiers:
                executable_hits.add((owned_path.name, node.lineno, node.id))
            if isinstance(node, ast.Attribute) and node.attr in legacy_identifiers:
                executable_hits.add((owned_path.name, node.lineno, node.attr))
            if isinstance(node, ast.Call):
                call_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else (
                        node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else None
                    )
                )
                if call_name in {"getattr", "hasattr", "setattr"} and len(
                    node.args
                ) >= 2:
                    folded_name = _folded_static_string(node.args[1])
                    if folded_name in legacy_identifiers:
                        executable_hits.add(
                            (owned_path.name, node.lineno, folded_name)
                        )
                if call_name in {"__import__", "getmodule", "import_module"}:
                    executable_hits.add(
                        (owned_path.name, node.lineno, call_name)
                    )
            if isinstance(node, ast.Subscript):
                folded_key = _folded_static_string(node.slice)
                if folded_key in legacy_identifiers:
                    executable_hits.add(
                        (owned_path.name, node.lineno, folded_key)
                    )

    assert not executable_hits
    assert not legacy_identifiers.intersection(vars(application_records_module))
    assert not legacy_identifiers.intersection(vars(application_ports_module))
    legacy_port_members = frozenset(
        name for name in legacy_identifiers if name[:1].islower()
    )
    assert not legacy_port_members.intersection(vars(RuntimeRecordPort))
    assert application_ports_module.ModelProviderV2 is ModelProviderV2
    assert (
        application_records_module.SaveRequestUnderstandingV2NoTaskCommand
        is SaveRequestUnderstandingV2NoTaskCommand
    )
    assert (
        application_records_module.CreateInitialTaskGraphV2Command
        is CreateInitialTaskGraphV2Command
    )


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

    assert isinstance(provider, ModelProviderV2)
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
    provider_doc = ModelProviderV2.__doc__ or ""
    assert "ProviderProtocolError" in provider_doc
    assert "from None" in provider_doc
    assert "__cause__" in provider_doc
    assert "__context__" in provider_doc
    assert "after discarding the raw exception" in provider_doc
    assert inspect.signature(ProviderProtocolError).parameters == {}


def test_ports_are_protocols_owned_by_application() -> None:
    assert ModelProviderV2._is_protocol
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
        "save_request_understanding_v2",
        "save_request_understanding_v2_if_current",
        "append_accepted_task_delta_v2",
        "create_initial_task_graph_v2",
        "create_initial_task_graph_latest_if_current",
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
    assert "APPLIED" in finalize_doc
    assert "one transaction" in finalize_doc
    assert "Task" in finalize_doc
    assert "RequestUnit" in finalize_doc
    assert "ASSISTANT Message" in finalize_doc
    assert "terminal Trace" in finalize_doc
    assert "PROJECTION_CONFLICT" in finalize_doc
    assert "NOT_APPLICABLE" in finalize_doc
    assert "zero writes" in finalize_doc
    assert set(ConditionalWriteResult) == {
        ConditionalWriteResult.APPLIED,
        ConditionalWriteResult.PROJECTION_CONFLICT,
        ConditionalWriteResult.NOT_APPLICABLE,
    }


def test_task_transition_and_observation_use_aggregate_commands() -> None:
    contracts = (
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


def test_v2_request_understanding_writes_use_two_exact_conditional_methods() -> None:
    contracts = (
        (
            RuntimeRecordPort.save_request_understanding_v2_no_task_if_current,
            SaveRequestUnderstandingV2NoTaskCommand,
        ),
        (
            RuntimeRecordPort.create_initial_task_graph_v2_if_current,
            CreateInitialTaskGraphV2Command,
        ),
    )
    for method, command_type in contracts:
        _assert_signature(
            method,
            parameters=("command",),
            type_hints={
                "command": command_type,
                "return": ConditionalWriteResult,
            },
        )
        doc = method.__doc__ or ""
        assert "APPLIED" in doc
        assert "PROJECTION_CONFLICT" in doc
        assert "NOT_APPLICABLE" in doc
        assert "zero writes" in doc
        assert "one transaction" in doc
        assert "absent" in doc
        assert "unauthorized" in doc

    no_task_doc = (
        RuntimeRecordPort.save_request_understanding_v2_no_task_if_current.__doc__
        or ""
    )
    graph_doc = (
        RuntimeRecordPort.create_initial_task_graph_v2_if_current.__doc__
        or ""
    )
    assert "never creates a Task" in no_task_doc
    assert "never degrades to the no-task route" in graph_doc


def test_owner_scoped_reads_require_minimal_trusted_owner_scope() -> None:
    scoped_methods = (
        ConversationRecordPort.load_conversation_for_owner,
        ConversationRecordPort.list_messages_for_owner,
        ConversationRecordPort.list_conversation_task_links_for_owner,
        RuntimeRecordPort.load_run_for_owner,
        RuntimeRecordPort.load_task_for_owner,
        RuntimeRecordPort.load_request_unit_for_owner,
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
    normalized_apply_doc = " ".join(apply_doc.split())
    assert "exact closure fence" in normalized_apply_doc
    assert "one atomic transaction" in normalized_apply_doc
    assert "state/link projections" in normalized_apply_doc
    assert "recovery_trace_events" in normalized_apply_doc
    assert "Core/Runtime-produced" in normalized_apply_doc
    assert "CLOSURE_CONFLICT" in normalized_apply_doc
    assert "NOT_APPLICABLE" in normalized_apply_doc
    assert "RECONCILIATION_REQUIRED" in normalized_apply_doc
    assert "zero state writes" in normalized_apply_doc
    assert "zero Trace writes" in normalized_apply_doc
    assert "RuntimeRecordPort.append_trace_event" in normalized_apply_doc
    assert "cannot substitute" in normalized_apply_doc
    assert "RUNNING ACTION" in normalized_apply_doc
    assert "RESULT_UNKNOWN" in normalized_apply_doc
    assert "neither INTERRUPTED nor any Run/Task/link" in normalized_apply_doc
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


def test_model_provider_v2_is_current_and_has_exact_failure_partition() -> None:
    provider = CandidateOnlyProvider()

    assert isinstance(provider, ModelProviderV2)
    _assert_signature(
        ModelProviderV2.propose_next_move,
        parameters=("request",),
        type_hints={
            "request": RequestUnderstandingInput,
            "return": RequestUnderstandingOutputV2,
        },
    )
    _assert_signature(
        ModelProviderV2.plan_presentation,
        parameters=("request",),
        type_hints={
            "request": PresentationInput,
            "return": PresentationPlan,
        },
    )
    normalized_doc = " ".join((ModelProviderV2.__doc__ or "").split())
    for required_term in (
        "correctly framed Request Understanding target function",
        "RequestUnderstandingOutputV2",
        "shape",
        "version",
        "source",
        "authority",
        "InputBinding",
        "trusted",
        "private",
        "RequestUnderstandingCandidateInvalidError",
        "transport",
        "HTTP",
        "JSON",
        "framing",
        "zero",
        "multiple",
        "wrong-name",
        "ProviderProtocolError",
        "PresentationPlan",
        "fresh",
        "raw diagnostic",
        "__cause__",
        "__context__",
    ):
        assert required_term in normalized_doc
    assert inspect.signature(RequestUnderstandingCandidateInvalidError).parameters == {}


def test_exact_run_evidence_port_is_owner_scoped_snapshot_only_boundary() -> None:
    assert ExactRunEvidencePort._is_protocol
    _assert_signature(
        ExactRunEvidencePort.load_exact_run_evidence_for_owner,
        parameters=("owner_scope", "run_id"),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "run_id": UUID,
            "return": ExactRunEvidenceClosure | None,
        },
    )
    signature = inspect.signature(
        ExactRunEvidencePort.load_exact_run_evidence_for_owner
    )
    assert all(
        signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("owner_scope", "run_id")
    )

    normalized_doc = " ".join((ExactRunEvidencePort.__doc__ or "").split())
    for required_term in (
        "None only",
        "absent",
        "unauthorized",
        "ownership-unverified",
        "P0PersistenceIntegrityError",
        "transactionally consistent snapshot",
        "exact fence",
        "strict-decode",
        "database closed set",
        "partial",
        "skip-corrupt",
        "session",
        "does not authorize",
        "does not write",
        "does not claim recovery",
        "does not construct Case",
        "expectation",
        "HTTP",
        "Eval Result",
    ):
        assert required_term in normalized_doc

    annotations = get_type_hints(
        ExactRunEvidencePort.load_exact_run_evidence_for_owner,
        include_extras=True,
    )
    for forbidden_type in ("customer_id", "case_id", "EvalEvidence"):
        assert forbidden_type not in annotations
    for forbidden_method in (
        "save",
        "write",
        "claim_recovery",
        "build_eval_result",
    ):
        assert not hasattr(ExactRunEvidencePort, forbidden_method)
