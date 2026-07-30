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


_LEGACY_APPLICATION_RU_V1_IDENTIFIERS = frozenset(
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
_TARGETED_APPLICATION_MODULES = frozenset(
    {
        "mini_agent.application.ports",
        "mini_agent.application.records",
        "mini_agent.core.request_understanding",
        "mini_agent.core.task_state",
    }
)
_STATIC_VALUE_MISSING = object()


def _static_value(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        values = tuple(_static_value(value) for value in node.elts)
        if any(value is _STATIC_VALUE_MISSING for value in values):
            return _STATIC_VALUE_MISSING
        if isinstance(node, ast.List):
            return list(values)
        if isinstance(node, ast.Set):
            try:
                return set(values)
            except TypeError:
                return _STATIC_VALUE_MISSING
        return values
    if isinstance(node, ast.Dict):
        keys = tuple(_static_value(key) for key in node.keys if key is not None)
        values = tuple(_static_value(value) for value in node.values)
        if (
            len(keys) != len(node.keys)
            or any(value is _STATIC_VALUE_MISSING for value in (*keys, *values))
        ):
            return _STATIC_VALUE_MISSING
        try:
            return dict(zip(keys, values, strict=True))
        except (TypeError, ValueError):
            return _STATIC_VALUE_MISSING
    if (
        isinstance(node, ast.GeneratorExp)
        and len(node.generators) == 1
        and not node.generators[0].ifs
        and not node.generators[0].is_async
        and isinstance(node.generators[0].target, ast.Name)
        and isinstance(node.elt, ast.Name)
        and node.generators[0].target.id == node.elt.id
    ):
        iterable = _static_value(node.generators[0].iter)
        if isinstance(iterable, (list, tuple)):
            return tuple(iterable)
        return _STATIC_VALUE_MISSING
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _static_value(node.operand)
        if not isinstance(operand, (int, float, complex)):
            return _STATIC_VALUE_MISSING
        return +operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        left = _static_value(node.left)
        right = _static_value(node.right)
        if left is _STATIC_VALUE_MISSING or right is _STATIC_VALUE_MISSING:
            return _STATIC_VALUE_MISSING
        try:
            if isinstance(node.op, ast.Add):
                return left + right  # type: ignore[operator]
            if isinstance(node.op, ast.Mult):
                return left * right  # type: ignore[operator]
            if isinstance(node.op, ast.Mod) and isinstance(left, str):
                return left % right
        except (KeyError, TypeError, ValueError):
            return _STATIC_VALUE_MISSING
    if isinstance(node, ast.JoinedStr):
        rendered: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                rendered.append(value.value)
                continue
            if not isinstance(value, ast.FormattedValue):
                return _STATIC_VALUE_MISSING
            static_value = _static_value(value.value)
            if static_value is _STATIC_VALUE_MISSING:
                return _STATIC_VALUE_MISSING
            if value.conversion == ord("r"):
                static_value = repr(static_value)
            elif value.conversion == ord("s"):
                static_value = str(static_value)
            elif value.conversion == ord("a"):
                static_value = ascii(static_value)
            format_spec = (
                _static_value(value.format_spec)
                if value.format_spec is not None
                else ""
            )
            if not isinstance(format_spec, str):
                return _STATIC_VALUE_MISSING
            try:
                rendered.append(format(static_value, format_spec))
            except (TypeError, ValueError):
                return _STATIC_VALUE_MISSING
        return "".join(rendered)
    if isinstance(node, ast.Slice):
        lower = _static_value(node.lower) if node.lower is not None else None
        upper = _static_value(node.upper) if node.upper is not None else None
        step = _static_value(node.step) if node.step is not None else None
        if any(
            value is _STATIC_VALUE_MISSING for value in (lower, upper, step)
        ):
            return _STATIC_VALUE_MISSING
        if not all(value is None or isinstance(value, int) for value in (lower, upper, step)):
            return _STATIC_VALUE_MISSING
        return slice(lower, upper, step)
    if isinstance(node, ast.Subscript):
        container = _static_value(node.value)
        key = _static_value(node.slice)
        if container is _STATIC_VALUE_MISSING or key is _STATIC_VALUE_MISSING:
            return _STATIC_VALUE_MISSING
        try:
            return container[key]  # type: ignore[index]
        except (IndexError, KeyError, TypeError):
            return _STATIC_VALUE_MISSING
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    ):
        receiver = _static_value(node.func.value)
        args = tuple(_static_value(value) for value in node.args)
        keywords = {
            keyword.arg: _static_value(keyword.value)
            for keyword in node.keywords
            if keyword.arg is not None
        }
        if (
            any(value is _STATIC_VALUE_MISSING for value in args)
            or len(keywords) != len(node.keywords)
            or any(value is _STATIC_VALUE_MISSING for value in keywords.values())
        ):
            return _STATIC_VALUE_MISSING
        try:
            if (
                node.func.attr == "join"
                and isinstance(receiver, str)
                and len(args) == 1
                and not keywords
            ):
                return receiver.join(args[0])  # type: ignore[arg-type]
            if node.func.attr == "format" and isinstance(receiver, str):
                return receiver.format(*args, **keywords)
            if (
                node.func.attr == "replace"
                and isinstance(receiver, str)
                and len(args) in {2, 3}
                and not keywords
            ):
                return receiver.replace(*args)  # type: ignore[arg-type]
            if (
                node.func.attr in {"removeprefix", "removesuffix"}
                and isinstance(receiver, str)
                and len(args) == 1
                and isinstance(args[0], str)
                and not keywords
            ):
                return getattr(receiver, node.func.attr)(args[0])
            if (
                node.func.attr == "get"
                and isinstance(receiver, dict)
                and len(args) in {1, 2}
                and not keywords
            ):
                return receiver.get(*args)
        except (IndexError, KeyError, TypeError, ValueError):
            return _STATIC_VALUE_MISSING
    return _STATIC_VALUE_MISSING


def _folded_static_string(node: ast.AST) -> str | None:
    value = _static_value(node)
    return value if isinstance(value, str) else None


def _legacy_application_executable_hits(
    source: str,
    *,
    filename: str,
) -> set[tuple[str, int, str]]:
    tree = ast.parse(source)
    exempt_node_ids: set[int] = set()
    runtime_oracle_call_ids: set[int] = set()
    accepted_delta_family = next(
        identifier
        for identifier in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS
        if identifier.startswith("Accepted") and identifier.endswith("Delta")
    )
    safe_family_labels = {
        accepted_delta_family,
        f"{accepted_delta_family}.input_binding_refs",
    }
    for node in ast.walk(tree):
        targets: tuple[ast.expr, ...] = ()
        if isinstance(node, ast.Assign):
            targets = tuple(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = (node.target,)
        if any(
            isinstance(target, ast.Name)
            and target.id == "_LEGACY_APPLICATION_RU_V1_IDENTIFIERS"
            for target in targets
        ):
            exempt_node_ids.update(id(descendant) for descendant in ast.walk(node))
        if isinstance(node, ast.keyword):
            label = _folded_static_string(node.value)
            if node.arg in {"family_name", "field_name"} and label in (
                safe_family_labels
            ):
                exempt_node_ids.update(
                    id(descendant) for descendant in ast.walk(node)
                )
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "test_application_ru_v1_records_and_ports_are_not_executable"
        ):
            runtime_oracle_call_ids.update(
                id(descendant)
                for descendant in ast.walk(node)
                if isinstance(descendant, ast.Call)
                and isinstance(descendant.func, ast.Name)
                and descendant.func.id == "hasattr"
            )

    hits: set[tuple[str, int, str]] = set()

    def add_hit(node: ast.AST, detail: str) -> None:
        hits.add((filename, getattr(node, "lineno", 0), detail))

    targeted_module_tails = {
        module.rsplit(".", maxsplit=1)[-1]
        for module in _TARGETED_APPLICATION_MODULES
    }
    targeted_module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TARGETED_APPLICATION_MODULES:
                    targeted_module_aliases.add(
                        alias.asname or alias.name.split(".", maxsplit=1)[0]
                    )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                imported_module = f"{node.module}.{alias.name}"
                if imported_module in _TARGETED_APPLICATION_MODULES:
                    targeted_module_aliases.add(alias.asname or alias.name)

    def dotted_name(node: ast.AST) -> str | None:
        parts: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        return ".".join(reversed(parts))

    def is_targeted_container(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return (
                node.id in targeted_module_aliases
                or node.id == "module"
                or node.id.endswith("_module")
                or node.id == "RuntimeRecordPort"
            )
        return dotted_name(node) in _TARGETED_APPLICATION_MODULES

    static_name_domains: dict[str, frozenset[str]] = {}

    def static_string_domain(node: ast.AST) -> frozenset[str] | None:
        value = _static_value(node)
        if isinstance(value, (list, set, tuple)) and all(
            isinstance(item, str) for item in value
        ):
            return frozenset(value)
        if isinstance(node, ast.Name):
            return static_name_domains.get(node.id)
        return None

    for _ in range(3):
        for node in ast.walk(tree):
            targets: tuple[ast.expr, ...] = ()
            value_node: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets = tuple(node.targets)
                value_node = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = (node.target,)
                value_node = node.value
            if value_node is not None:
                domain = static_string_domain(value_node)
                if domain is not None:
                    for target in targets:
                        if isinstance(target, ast.Name):
                            static_name_domains[target.id] = domain
            if isinstance(node, (ast.For, ast.comprehension)):
                domain = static_string_domain(node.iter)
                if domain is not None and isinstance(node.target, ast.Name):
                    static_name_domains[node.target.id] = domain

    dynamic_export_names = {"__getattr__", "__getattribute__"}
    for node in ast.walk(tree):
        if id(node) not in exempt_node_ids:
            folded_value = _folded_static_string(node)
            if folded_value in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                add_hit(node, f"folded-target:{folded_value}")
        if isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if any(alias.name == "*" for alias in node.names) and (
                module_name in _TARGETED_APPLICATION_MODULES
                or module_name.rsplit(".", maxsplit=1)[-1]
                in targeted_module_tails
            ):
                add_hit(node, "target-module-star-import")
            for alias in node.names:
                if alias.name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                    add_hit(node, alias.name)
        if isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            if node.name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                add_hit(node, node.name)
            if node.name in dynamic_export_names:
                add_hit(node, f"dynamic-export:{node.name}")
        if isinstance(node, ast.Name):
            if node.id in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                add_hit(node, node.id)
            if node.id in dynamic_export_names:
                add_hit(node, f"dynamic-export:{node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                add_hit(node, node.attr)
            if node.attr in dynamic_export_names:
                add_hit(node, f"dynamic-export:{node.attr}")
            if (
                node.attr == "__dict__"
                and is_targeted_container(node.value)
            ):
                add_hit(node, "dynamic-module-__dict__")
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
            if call_name in {"getattr", "hasattr", "setattr", "delattr"} and len(
                node.args
            ) >= 2:
                folded_name = _folded_static_string(node.args[1])
                if folded_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                    add_hit(node, f"reflective-target:{folded_name}")
                if (
                    id(node) not in runtime_oracle_call_ids
                    and is_targeted_container(node.args[0])
                    and folded_name is None
                ):
                    dynamic_domain = (
                        static_name_domains.get(node.args[1].id)
                        if isinstance(node.args[1], ast.Name)
                        else None
                    )
                    if dynamic_domain is None or dynamic_domain.intersection(
                        _LEGACY_APPLICATION_RU_V1_IDENTIFIERS
                    ):
                        add_hit(node, f"dynamic-module-reflection:{call_name}")
            if call_name == "get" and node.args:
                folded_name = _folded_static_string(node.args[0])
                if folded_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                    add_hit(node, f"mapping-get-target:{folded_name}")
            if call_name in {
                "__import__",
                "getmodule",
                "globals",
                "import_module",
                "locals",
            }:
                add_hit(node, f"dynamic-access:{call_name}")
            if (
                call_name == "vars"
                and node.args
                and is_targeted_container(node.args[0])
            ):
                add_hit(node, "dynamic-module-vars")
        if isinstance(node, ast.Subscript):
            folded_key = _folded_static_string(node.slice)
            if folded_key in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
                add_hit(node, f"subscript-target:{folded_key}")
    return hits


def test_application_ru_v1_records_and_ports_are_not_executable() -> None:
    repo_root = Path(__file__).parents[3]
    owned_paths = (
        repo_root / "src/mini_agent/application/records.py",
        repo_root / "src/mini_agent/application/ports.py",
        repo_root / "tests/component/application/test_record_contracts.py",
        repo_root / "tests/component/application/test_ports_contract.py",
    )
    executable_hits: set[tuple[str, int, str]] = set()

    for owned_path in owned_paths:
        executable_hits.update(
            _legacy_application_executable_hits(
                owned_path.read_text(encoding="utf-8"),
                filename=owned_path.name,
            )
        )

    assert not executable_hits
    legacy_port_members = frozenset(
        name
        for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS
        if name[:1].islower()
    )
    assert all(
        not hasattr(module, name)
        for module in (application_records_module, application_ports_module)
        for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS
    )
    assert all(not hasattr(RuntimeRecordPort, name) for name in legacy_port_members)
    assert application_ports_module.ModelProviderV2 is ModelProviderV2
    assert (
        application_records_module.SaveRequestUnderstandingV2NoTaskCommand
        is SaveRequestUnderstandingV2NoTaskCommand
    )
    assert (
        application_records_module.CreateInitialTaskGraphV2Command
        is CreateInitialTaskGraphV2Command
    )


def test_application_ru_v1_absence_oracle_rejects_static_and_dynamic_aliases() -> None:
    mutations = (
        'getattr(module, "Request{}Output".format("Understanding"))',
        'getattr(module, "xRequestUnderstandingOutput"[1:])',
        'getattr(module, "%s%s" % ("RequestUnderstanding", "Output"))',
        'legacy_name = "RequestUnderstandingOutput"\ngetattr(module, legacy_name)',
        'vars(module).get("RequestUnderstandingOutput")',
        'module.__dict__.get("RequestUnderstandingOutput")',
        'globals()["RequestUnderstandingOutput"]',
        'getattr(module, "xRequestUnderstandingOutput".removeprefix("x"))',
        "getattr(module, ''.join(part for part in ('Model', 'Provider')))",
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "legacy_name = next(\n"
            "    name\n"
            "    for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS\n"
            "    if hasattr(core_module, name)\n"
            ")\n"
            "getattr(core_module, legacy_name)"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "getattr(core_module, input())"
        ),
        "from mini_agent.application.records import *",
        "def __getattr__(name):\n    return None",
    )
    for mutation in mutations:
        assert _legacy_application_executable_hits(
            mutation,
            filename="mutation.py",
        ), mutation


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
