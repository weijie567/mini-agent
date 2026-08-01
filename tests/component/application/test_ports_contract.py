import ast
import inspect
from datetime import datetime
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

import mini_agent.application.ports as application_ports_module
import mini_agent.application.records as application_records_module
from mini_agent.application.ports import (
    AgentRunHandler,
    ConversationRecordPort,
    Cycle2RuntimeRecordPort,
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
    AppendToolAttemptV2Command,
    ApplyContinuationInputBindingV2Command,
    ApplyOrderCandidateSelectionV2Command,
    ApplyOrderSearchOutcomeV2Command,
    ApplyRestartRecoveryCommand,
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    Cycle2DispatchFenceWriteResult,
    Cycle2WriteResult,
    ContinuationInputBindingReadClosure,
    CreateInitialTaskGraphV2Command,
    CreateRunCommand,
    CreateToolCallCommand,
    CreateToolCallV2Command,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    ExactRunEvidenceClosure,
    FinalizeRunCommand,
    FinalizeSupersededRunV2Command,
    FinalizeToolCallCommand,
    FinalizeToolAttemptV2Command,
    InsertOnlyWriteResult,
    InitialToolCallV2ReadClosure,
    NonEmptyString,
    ObservationWriteResult,
    OrderCandidateSelectionReadClosure,
    OrderSearchCurrentReadClosure,
    PositiveAttempt,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    SaveRequestUnderstandingV2NoTaskCommand,
    SaveObservationCommand,
    SaveShipmentAssessmentV2Command,
    SaveShipmentObservationV2Command,
    ShipmentAssessmentReadClosure,
    SupersededRunReadClosure,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
)
from mini_agent.core.task_state import OrderCandidateSelectionRequest


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
    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    exempt_node_ids: set[int] = set()
    invalid_legacy_set_declarations: list[ast.AST] = []
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
            value_node = (
                node.value
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                else None
            )
            if (
                isinstance(value_node, ast.Call)
                and isinstance(value_node.func, ast.Name)
                and value_node.func.id == "frozenset"
                and len(value_node.args) == 1
                and not value_node.keywords
            ):
                declared_values = _static_value(value_node.args[0])
            else:
                declared_values = _static_value(value_node) if value_node else None
            if (
                isinstance(declared_values, (list, set, tuple, frozenset))
                and all(isinstance(value, str) for value in declared_values)
                and frozenset(declared_values)
                == _LEGACY_APPLICATION_RU_V1_IDENTIFIERS
            ):
                exempt_node_ids.update(
                    id(descendant) for descendant in ast.walk(node)
                )
            else:
                invalid_legacy_set_declarations.append(node)
        if isinstance(node, ast.keyword):
            label = _folded_static_string(node.value)
            if node.arg in {"family_name", "field_name"} and label in (
                safe_family_labels
            ):
                exempt_node_ids.update(
                    id(descendant) for descendant in ast.walk(node)
                )

    hits: set[tuple[str, int, str]] = set()

    def add_hit(node: ast.AST, detail: str) -> None:
        hits.add((filename, getattr(node, "lineno", 0), detail))

    for declaration in invalid_legacy_set_declarations:
        add_hit(declaration, "invalid-legacy-identifier-set")

    targeted_module_tails = {
        module.rsplit(".", maxsplit=1)[-1]
        for module in _TARGETED_APPLICATION_MODULES
    }
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

    def lexical_scope(node: ast.AST) -> ast.AST:
        current = node
        while id(current) in parents:
            current = parents[id(current)]
            if isinstance(
                current,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
            ):
                return current
        return tree

    def target_binds_name(target: ast.AST, name: str) -> bool:
        return any(
            isinstance(descendant, ast.Name)
            and isinstance(descendant.ctx, ast.Store)
            and descendant.id == name
            for descendant in ast.walk(target)
        )

    def node_position(node: ast.AST) -> tuple[int, int]:
        return (
            getattr(node, "lineno", 0),
            getattr(node, "col_offset", 0),
        )

    def import_binding(
        node: ast.Import | ast.ImportFrom,
        name: str,
    ) -> bool | None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                if bound_name == name:
                    return alias.name in _TARGETED_APPLICATION_MODULES
            return None
        for alias in node.names:
            bound_name = alias.asname or alias.name
            if bound_name != name:
                continue
            imported_name = (
                f"{node.module}.{alias.name}"
                if node.module is not None
                else alias.name
            )
            return (
                imported_name in _TARGETED_APPLICATION_MODULES
                or (
                    node.level > 0
                    and alias.name in targeted_module_tails
                )
                or (
                    node.module == "mini_agent.application.ports"
                    and alias.name == "RuntimeRecordPort"
                )
            )
        return None

    def scope_parameter_names(scope: ast.AST) -> set[str]:
        if not isinstance(
            scope,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return set()
        arguments = scope.args
        return {
            argument.arg
            for argument in (
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
            )
        } | {
            argument.arg
            for argument in (arguments.vararg, arguments.kwarg)
            if argument is not None
        }

    def node_contains(ancestor: ast.AST, descendant: ast.AST) -> bool:
        current = descendant
        while id(current) in parents:
            current = parents[id(current)]
            if current is ancestor:
                return True
        return False

    def binding_dominates_use(
        binding: ast.AST,
        *,
        use: ast.AST,
        scope: ast.AST,
    ) -> bool:
        for owner in ast.walk(scope):
            if owner is not scope and lexical_scope(owner) is not scope:
                continue
            for _field_name, value in ast.iter_fields(owner):
                if not isinstance(value, list):
                    continue
                for index, item in enumerate(value):
                    if item is not binding:
                        continue
                    return any(
                        isinstance(later, ast.AST)
                        and (
                            later is use
                            or node_contains(later, use)
                        )
                        for later in value[index + 1 :]
                    )
        return False

    def parameter_default(
        scope: ast.AST,
        name: str,
    ) -> ast.AST | None:
        if not isinstance(
            scope,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return None
        positional = (*scope.args.posonlyargs, *scope.args.args)
        defaults_by_name = {
            argument.arg: default
            for argument, default in zip(
                positional[-len(scope.args.defaults) :],
                scope.args.defaults,
                strict=True,
            )
        } if scope.args.defaults else {}
        defaults_by_name.update(
            {
                argument.arg: default
                for argument, default in zip(
                    scope.args.kwonlyargs,
                    scope.args.kw_defaults,
                    strict=True,
                )
                if default is not None
            }
        )
        return defaults_by_name.get(name)

    def container_binding_in_scope(
        name: str,
        *,
        before: ast.AST,
        scope: ast.AST,
        visited: frozenset[tuple[int, str]],
    ) -> tuple[bool, bool]:
        bindings: list[tuple[int, int, ast.AST, ast.AST | bool | None]] = []
        is_parameter = name in scope_parameter_names(scope)
        has_local_binding = is_parameter
        for candidate in ast.walk(scope):
            if candidate is scope or lexical_scope(candidate) is not scope:
                continue
            binding_value: ast.AST | bool | None = None
            binds = False
            if isinstance(candidate, (ast.Import, ast.ImportFrom)):
                imported_target = import_binding(candidate, name)
                if imported_target is not None:
                    binds = True
                    binding_value = imported_target
            elif isinstance(candidate, ast.Assign):
                matching_targets = [
                    target
                    for target in candidate.targets
                    if target_binds_name(target, name)
                ]
                if matching_targets:
                    binds = True
                    binding_value = (
                        candidate.value
                        if len(candidate.targets) == 1
                        and isinstance(candidate.targets[0], ast.Name)
                        else None
                    )
            elif isinstance(candidate, ast.AnnAssign) and target_binds_name(
                candidate.target,
                name,
            ):
                binds = True
                binding_value = (
                    candidate.value
                    if isinstance(candidate.target, ast.Name)
                    else None
                )
            elif isinstance(candidate, ast.NamedExpr) and target_binds_name(
                candidate.target,
                name,
            ):
                binds = True
                binding_value = (
                    candidate.value
                    if isinstance(candidate.target, ast.Name)
                    else None
                )
            elif isinstance(
                candidate,
                (ast.AugAssign, ast.For, ast.AsyncFor, ast.comprehension),
            ) and target_binds_name(candidate.target, name):
                binds = True
            if not binds:
                continue
            has_local_binding = True
            if node_position(candidate) < node_position(before):
                bindings.append(
                    (*node_position(candidate), candidate, binding_value)
                )

        def binding_targets_container(
            binding: ast.AST,
            value: ast.AST | bool | None,
        ) -> bool:
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            return is_targeted_container(
                value,
                at=binding,
                visited=visited,
            )

        parameter_value = parameter_default(scope, name)
        possible_target = (
            parameter_value is not None
            and is_targeted_container(
                parameter_value,
                at=scope,
                visited=visited,
            )
        )
        dominating = [
            binding
            for binding in bindings
            if isinstance(
                binding[2],
                (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign),
            )
            and binding_dominates_use(binding[2], use=before, scope=scope)
        ]
        dominating_position = (-1, -1)
        if dominating:
            latest_dominating = max(dominating, key=lambda item: item[:2])
            dominating_position = latest_dominating[:2]
            possible_target = binding_targets_container(
                latest_dominating[2],
                latest_dominating[3],
            )
        possible_target = possible_target or any(
            binding[:2] > dominating_position
            and not binding_dominates_use(
                binding[2],
                use=before,
                scope=scope,
            )
            and binding_targets_container(binding[2], binding[3])
            for binding in bindings
        )
        if not bindings:
            return has_local_binding, possible_target
        return True, possible_target

    def qualified_root_is_unshadowed(
        node: ast.AST,
        *,
        at: ast.AST,
    ) -> bool:
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return False

        def package_status_in_scope(
            scope: ast.AST,
            *,
            initial_status: bool,
        ) -> tuple[bool, bool]:
            bindings: list[tuple[int, int, ast.AST, bool]] = []
            has_binding = root.id in scope_parameter_names(scope)
            if has_binding:
                initial_status = False
            for candidate in ast.walk(scope):
                if candidate is scope or lexical_scope(candidate) is not scope:
                    continue
                is_package_import = False
                binds = False
                if isinstance(candidate, ast.Import):
                    for alias in candidate.names:
                        bound_name = (
                            alias.asname
                            or alias.name.split(".", maxsplit=1)[0]
                        )
                        if bound_name == root.id:
                            binds = True
                            is_package_import = (
                                alias.name == "mini_agent"
                                or alias.name.startswith("mini_agent.")
                            )
                elif isinstance(candidate, ast.ImportFrom):
                    binds = import_binding(candidate, root.id) is not None
                elif isinstance(candidate, ast.Assign):
                    binds = any(
                        target_binds_name(target, root.id)
                        for target in candidate.targets
                    )
                elif isinstance(candidate, ast.AnnAssign):
                    binds = target_binds_name(candidate.target, root.id)
                elif isinstance(candidate, ast.NamedExpr):
                    binds = target_binds_name(candidate.target, root.id)
                elif isinstance(
                    candidate,
                    (ast.AugAssign, ast.For, ast.AsyncFor, ast.comprehension),
                ):
                    binds = target_binds_name(candidate.target, root.id)
                if not binds:
                    continue
                has_binding = True
                if node_position(candidate) < node_position(at):
                    bindings.append(
                        (
                            *node_position(candidate),
                            candidate,
                            is_package_import,
                        )
                    )
            dominating = [
                binding
                for binding in bindings
                if isinstance(
                    binding[2],
                    (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign),
                )
                and binding_dominates_use(
                    binding[2],
                    use=at,
                    scope=scope,
                )
            ]
            dominating_position = (-1, -1)
            possible_package = initial_status
            if dominating:
                latest_dominating = max(
                    dominating,
                    key=lambda item: item[:2],
                )
                dominating_position = latest_dominating[:2]
                possible_package = latest_dominating[3]
            possible_package = possible_package or any(
                binding[:2] > dominating_position
                and not binding_dominates_use(
                    binding[2],
                    use=at,
                    scope=scope,
                )
                and binding[3]
                for binding in bindings
            )
            return has_binding, possible_package

        function_scope = lexical_scope(at)
        _module_bound, possible_package = package_status_in_scope(
            tree,
            initial_status=True,
        )
        if function_scope is tree:
            return possible_package
        _local_bound, possible_package = package_status_in_scope(
            function_scope,
            initial_status=possible_package,
        )
        return possible_package

    def is_targeted_container(
        node: ast.AST,
        *,
        at: ast.AST,
        visited: frozenset[tuple[int, str]] = frozenset(),
    ) -> bool:
        qualified_name = dotted_name(node)
        if qualified_name in _TARGETED_APPLICATION_MODULES:
            return qualified_root_is_unshadowed(node, at=at)
        if not isinstance(node, ast.Name):
            return False
        scope = lexical_scope(at)
        lookup_key = (id(scope), node.id)
        if lookup_key in visited:
            return False
        next_visited = visited | {lookup_key}
        has_binding, is_target = container_binding_in_scope(
            node.id,
            before=at,
            scope=scope,
            visited=next_visited,
        )
        if has_binding:
            return is_target
        if scope is not tree:
            has_binding, is_target = container_binding_in_scope(
                node.id,
                before=at,
                scope=tree,
                visited=next_visited,
            )
            if has_binding:
                return is_target
        return node.id == "module" or node.id.endswith("_module")

    def direct_static_string_domain(node: ast.AST) -> frozenset[str] | None:
        value = _static_value(node)
        if isinstance(value, (list, set, tuple)) and all(
            isinstance(item, str) for item in value
        ):
            return frozenset(value)
        return None

    def assigned_value_in_scope(
        name: str,
        *,
        before: ast.AST,
        scope: ast.AST,
    ) -> ast.AST | None:
        assignments: list[tuple[int, int, ast.AST]] = []
        ambiguous_binding = False
        for candidate in ast.walk(scope):
            if candidate is scope or lexical_scope(candidate) is not scope:
                continue
            if getattr(candidate, "lineno", 0) >= getattr(before, "lineno", 0):
                continue
            targets: tuple[ast.AST, ...] = ()
            value: ast.AST | None = None
            if isinstance(candidate, ast.Assign):
                targets = tuple(candidate.targets)
                value = candidate.value
            elif isinstance(candidate, ast.AnnAssign):
                targets = (candidate.target,)
                value = candidate.value
            elif isinstance(candidate, ast.NamedExpr):
                targets = (candidate.target,)
                value = candidate.value
            elif isinstance(
                candidate,
                (ast.AugAssign, ast.For, ast.AsyncFor, ast.comprehension),
            ):
                targets = (candidate.target,)
            if not any(target_binds_name(target, name) for target in targets):
                continue
            if (
                value is None
                or len(targets) != 1
                or not isinstance(targets[0], ast.Name)
            ):
                ambiguous_binding = True
                continue
            assignments.append(
                (
                    getattr(candidate, "lineno", 0),
                    getattr(candidate, "col_offset", 0),
                    value,
                )
            )
        if ambiguous_binding or len(assignments) != 1:
            return None
        return max(assignments, key=lambda item: item[:2])[2]

    def static_string_domain(
        node: ast.AST,
        *,
        before: ast.AST,
        scope: ast.AST,
        visited: frozenset[str] = frozenset(),
    ) -> frozenset[str] | None:
        direct = direct_static_string_domain(node)
        if direct is not None:
            return direct
        if not isinstance(node, ast.Name) or node.id in visited:
            return None
        assigned = assigned_value_in_scope(node.id, before=before, scope=scope)
        if assigned is None:
            return None
        return static_string_domain(
            assigned,
            before=before,
            scope=scope,
            visited=visited | {node.id},
        )

    def nearest_loop_domain(
        name_node: ast.Name,
        *,
        call: ast.Call,
    ) -> tuple[bool, frozenset[str] | None]:
        name = name_node.id
        scope = lexical_scope(call)
        current: ast.AST = call
        while id(current) in parents:
            current = parents[id(current)]
            if isinstance(current, (ast.For, ast.AsyncFor)) and target_binds_name(
                current.target,
                name,
            ):
                return True, static_string_domain(
                    current.iter,
                    before=call,
                    scope=scope,
                )
            if isinstance(
                current,
                (ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp),
            ):
                for generator in reversed(current.generators):
                    if target_binds_name(generator.target, name):
                        return True, static_string_domain(
                            generator.iter,
                            before=call,
                            scope=scope,
                        )
            if current is scope:
                break
        return False, None

    def is_exact_runtime_oracle_call(node: ast.Call) -> bool:
        if (
            not isinstance(node.func, ast.Name)
            or node.func.id != "hasattr"
            or len(node.args) != 2
            or node.keywords
            or not isinstance(node.args[0], ast.Name)
            or not isinstance(node.args[1], ast.Name)
        ):
            return False
        negation = parents.get(id(node))
        assertion = parents.get(id(negation)) if negation is not None else None
        if not (
            isinstance(negation, ast.UnaryOp)
            and isinstance(negation.op, ast.Not)
            and negation.operand is node
            and isinstance(assertion, ast.Assert)
            and assertion.test is negation
            and assertion.msg is None
        ):
            return False
        function = lexical_scope(node)
        if (
            not isinstance(function, ast.FunctionDef)
            or function.name
            != "test_application_ru_v1_records_and_ports_are_not_executable"
            or function not in tree.body
            or function.decorator_list
            or function.args.args
            or function.args.posonlyargs
            or function.args.kwonlyargs
            or function.args.vararg is not None
            or function.args.kwarg is not None
        ):
            return False
        if any(
            isinstance(descendant, (ast.Return, ast.Raise, ast.Break, ast.Continue))
            for descendant in ast.walk(function)
        ):
            return False

        def direct_negative_hasattr(
            statement: ast.stmt,
        ) -> tuple[str, str, ast.Call] | None:
            if (
                not isinstance(statement, ast.Assert)
                or statement.msg is not None
                or not isinstance(statement.test, ast.UnaryOp)
                or not isinstance(statement.test.op, ast.Not)
                or not isinstance(statement.test.operand, ast.Call)
            ):
                return None
            call = statement.test.operand
            if (
                not isinstance(call.func, ast.Name)
                or call.func.id != "hasattr"
                or len(call.args) != 2
                or call.keywords
                or not isinstance(call.args[0], ast.Name)
                or not isinstance(call.args[1], ast.Name)
            ):
                return None
            return call.args[0].id, call.args[1].id, call

        module_loops = [
            statement
            for statement in function.body
            if isinstance(statement, ast.For)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "legacy_name"
            and isinstance(statement.iter, ast.Name)
            and statement.iter.id == "_LEGACY_APPLICATION_RU_V1_IDENTIFIERS"
            and not statement.orelse
        ]
        port_loops = [
            statement
            for statement in function.body
            if isinstance(statement, ast.For)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "legacy_port_member"
            and isinstance(statement.iter, ast.Name)
            and statement.iter.id == "legacy_port_members"
            and not statement.orelse
        ]
        if len(module_loops) != 1 or len(port_loops) != 1:
            return False
        module_assertions = [
            direct_negative_hasattr(statement)
            for statement in module_loops[0].body
        ]
        port_assertions = [
            direct_negative_hasattr(statement)
            for statement in port_loops[0].body
        ]
        if (
            [
                assertion[:2] if assertion is not None else None
                for assertion in module_assertions
            ]
            != [
                ("application_records_module", "legacy_name"),
                ("application_ports_module", "legacy_name"),
            ]
            or [
                assertion[:2] if assertion is not None else None
                for assertion in port_assertions
            ]
            != [("RuntimeRecordPort", "legacy_port_member")]
        ):
            return False

        legacy_set_stores = [
            descendant
            for descendant in ast.walk(function)
            if isinstance(descendant, ast.Name)
            and isinstance(descendant.ctx, ast.Store)
            and descendant.id == "_LEGACY_APPLICATION_RU_V1_IDENTIFIERS"
        ]
        if legacy_set_stores:
            return False
        port_member_assignments = [
            statement
            for statement in function.body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "legacy_port_members"
        ]
        expected_port_members = ast.parse(
            "frozenset("
            "name for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS "
            "if name[:1].islower()"
            ")",
            mode="eval",
        ).body
        if (
            len(port_member_assignments) != 1
            or ast.dump(
                port_member_assignments[0].value,
                include_attributes=False,
            )
            != ast.dump(expected_port_members, include_attributes=False)
        ):
            return False
        expected_calls = {
            assertion[2]
            for assertion in (*module_assertions, *port_assertions)
            if assertion is not None
        }
        return node in expected_calls

    def runtime_oracle_function_is_exact(function: ast.FunctionDef) -> bool:
        expected_signature_calls = [
            descendant
            for descendant in ast.walk(function)
            if isinstance(descendant, ast.Call)
            and isinstance(descendant.func, ast.Name)
            and descendant.func.id == "hasattr"
            and len(descendant.args) == 2
            and isinstance(descendant.args[0], ast.Name)
            and isinstance(descendant.args[1], ast.Name)
            and (
                (
                    descendant.args[0].id
                    in {
                        "application_records_module",
                        "application_ports_module",
                    }
                    and descendant.args[1].id == "legacy_name"
                )
                or (
                    descendant.args[0].id == "RuntimeRecordPort"
                    and descendant.args[1].id == "legacy_port_member"
                )
            )
        ]
        return (
            len(expected_signature_calls) == 3
            and all(
                is_exact_runtime_oracle_call(call)
                for call in expected_signature_calls
            )
        )

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
            if (
                isinstance(node, ast.FunctionDef)
                and node.name
                == "test_application_ru_v1_records_and_ports_are_not_executable"
                and not runtime_oracle_function_is_exact(node)
            ):
                add_hit(node, "invalid-runtime-absence-oracle-shape")
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
                and is_targeted_container(node.value, at=node)
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
                exact_runtime_oracle = is_exact_runtime_oracle_call(node)
                runtime_function = lexical_scope(node)
                has_runtime_oracle_signature = (
                    call_name == "hasattr"
                    and isinstance(runtime_function, ast.FunctionDef)
                    and runtime_function.name
                    == "test_application_ru_v1_records_and_ports_are_not_executable"
                    and isinstance(node.args[0], ast.Name)
                    and isinstance(node.args[1], ast.Name)
                    and (
                        (
                            node.args[0].id
                            in {
                                "application_records_module",
                                "application_ports_module",
                            }
                            and node.args[1].id == "legacy_name"
                        )
                        or (
                            node.args[0].id == "RuntimeRecordPort"
                            and node.args[1].id == "legacy_port_member"
                        )
                    )
                )
                if has_runtime_oracle_signature and not exact_runtime_oracle:
                    add_hit(node, "invalid-runtime-absence-oracle")
                if (
                    not exact_runtime_oracle
                    and is_targeted_container(node.args[0], at=node)
                    and folded_name is None
                ):
                    has_loop_domain, dynamic_domain = (
                        nearest_loop_domain(node.args[1], call=node)
                        if isinstance(node.args[1], ast.Name)
                        else (False, None)
                    )
                    if dynamic_domain is None or dynamic_domain.intersection(
                        _LEGACY_APPLICATION_RU_V1_IDENTIFIERS
                    ) or not has_loop_domain:
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
                and is_targeted_container(node.args[0], at=node)
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
    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:
        assert not hasattr(application_records_module, legacy_name)
        assert not hasattr(application_ports_module, legacy_name)
    for legacy_port_member in legacy_port_members:
        assert not hasattr(RuntimeRecordPort, legacy_port_member)
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
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    assert not hasattr(core_module, input())"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        leaked = hasattr(application_records_module, legacy_name)"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        assert hasattr(application_records_module, legacy_name)"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        if hasattr(application_records_module, legacy_name):\n"
            "            pass"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "ru = core_module\n"
            "getattr(ru, input())"
        ),
        (
            "from mini_agent.application.ports import RuntimeRecordPort as RRP\n"
            "getattr(RRP, input())"
        ),
        (
            "import mini_agent.application.records\n"
            "getattr(mini_agent.application.records, input())"
        ),
        (
            "import mini_agent.core.request_understanding\n"
            "vars(mini_agent.core.request_understanding)"
        ),
        (
            "import mini_agent.application.records\n"
            "def inspect(record, condition):\n"
            "    if condition:\n"
            "        mini_agent = record\n"
            "    return getattr(mini_agent.application.records, input())"
        ),
        (
            "import mini_agent.application.records\n"
            "def inspect(records):\n"
            "    for mini_agent in records:\n"
            "        pass\n"
            "    return getattr(mini_agent.application.records, input())"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(record, condition):\n"
            "    ru = core_module\n"
            "    if condition:\n"
            "        ru = record\n"
            "    return getattr(ru, input())"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(record, condition):\n"
            "    if condition:\n"
            "        ru = core_module\n"
            "    else:\n"
            "        ru = record\n"
            "    return getattr(ru, input())"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(records):\n"
            "    ru = core_module\n"
            "    for ru in records:\n"
            "        pass\n"
            "    return getattr(ru, input())"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(ru=core_module):\n"
            "    return getattr(ru, input())"
        ),
        "from . import records as ru\ngetattr(ru, input())",
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def check():\n"
            "    for name in ('safe_name',):\n"
            "        assert not hasattr(core_module, name)\n"
            "    for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        getattr(core_module, name)"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    legacy_port_members = frozenset(\n"
            "        name for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS\n"
            "        if name[:1].islower()\n"
            "    )\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        if False:\n"
            "            assert not hasattr(\n"
            "                application_records_module, legacy_name\n"
            "            )\n"
            "        assert not hasattr(application_ports_module, legacy_name)\n"
            "    for legacy_port_member in legacy_port_members:\n"
            "        assert not hasattr(RuntimeRecordPort, legacy_port_member)"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    legacy_port_members = frozenset(\n"
            "        name for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS\n"
            "        if name[:1].islower()\n"
            "    )\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        continue\n"
            "        assert not hasattr(\n"
            "            application_records_module, legacy_name\n"
            "        )\n"
            "        assert not hasattr(application_ports_module, legacy_name)\n"
            "    for legacy_port_member in legacy_port_members:\n"
            "        assert not hasattr(RuntimeRecordPort, legacy_port_member)"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    _LEGACY_APPLICATION_RU_V1_IDENTIFIERS = ()\n"
            "    legacy_port_members = frozenset(\n"
            "        name for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS\n"
            "        if name[:1].islower()\n"
            "    )\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        assert not hasattr(\n"
            "            application_records_module, legacy_name\n"
            "        )\n"
            "        assert not hasattr(application_ports_module, legacy_name)\n"
            "    for legacy_port_member in legacy_port_members:\n"
            "        assert not hasattr(RuntimeRecordPort, legacy_port_member)"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    legacy_port_members = frozenset(\n"
            "        name for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS\n"
            "        if name[:1].islower()\n"
            "    )\n"
            "    pass"
        ),
        (
            "def test_application_ru_v1_records_and_ports_are_not_executable():\n"
            "    legacy_port_members = frozenset(\n"
            "        name for name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS\n"
            "        if name[:1].islower()\n"
            "    )\n"
            "    for legacy_name in _LEGACY_APPLICATION_RU_V1_IDENTIFIERS:\n"
            "        pass\n"
            "    for legacy_port_member in legacy_port_members:\n"
            "        pass"
        ),
        "from mini_agent.application.records import *",
        "def __getattr__(name):\n    return None",
    )
    for mutation in mutations:
        assert _legacy_application_executable_hits(
            mutation,
            filename="mutation.py",
        ), mutation


def test_application_ru_v1_absence_oracle_allows_rebound_instance_reflection() -> None:
    safe_sources = (
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(record):\n"
            "    ru = core_module\n"
            "    ru = record\n"
            "    return getattr(ru, input())"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(core_module):\n"
            "    return hasattr(core_module, input())"
        ),
        (
            "import mini_agent.core.request_understanding as core_module\n"
            "def inspect(ru):\n"
            "    return vars(ru)"
        ),
        (
            "def inspect(mini_agent):\n"
            "    return getattr(\n"
            "        mini_agent.core.request_understanding, input()\n"
            "    )"
        ),
        (
            "import mini_agent\n"
            "def inspect(record):\n"
            "    mini_agent = record\n"
            "    return vars(mini_agent.core.request_understanding)"
        ),
    )
    for safe_source in safe_sources:
        assert not _legacy_application_executable_hits(
            safe_source,
            filename="safe_source.py",
        ), safe_source


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


def test_cycle2_runtime_record_port_is_independent_and_exactly_typed() -> None:
    assert Cycle2RuntimeRecordPort._is_protocol
    assert Cycle2RuntimeRecordPort is not RuntimeRecordPort
    for method_name in (
        "load_continuation_input_binding_closure_for_owner",
        "apply_continuation_input_binding_if_current",
        "load_order_search_current_closure_for_owner",
        "apply_order_search_outcome_if_current",
        "load_order_candidate_selection_closure_for_owner",
        "apply_order_candidate_selection_if_current",
        "load_initial_tool_call_v2_closure_for_owner",
        "insert_initial_tool_call_v2_if_current",
        "append_tool_attempt_if_current",
        "finalize_tool_attempt_if_current",
        "save_shipment_observation_if_current",
        "load_shipment_assessment_closure_for_owner",
        "save_shipment_assessment_if_current",
        "load_superseded_run_closure_for_owner",
        "finalize_superseded_run_if_current",
    ):
        assert hasattr(Cycle2RuntimeRecordPort, method_name)
        assert not hasattr(RuntimeRecordPort, method_name)

    _assert_signature(
        Cycle2RuntimeRecordPort.apply_continuation_input_binding_if_current,
        parameters=("command",),
        type_hints={
            "command": ApplyContinuationInputBindingV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.apply_order_search_outcome_if_current,
        parameters=("command",),
        type_hints={
            "command": ApplyOrderSearchOutcomeV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.apply_order_candidate_selection_if_current,
        parameters=("command",),
        type_hints={
            "command": ApplyOrderCandidateSelectionV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.insert_initial_tool_call_v2_if_current,
        parameters=("command",),
        type_hints={
            "command": CreateToolCallV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.append_tool_attempt_if_current,
        parameters=("command",),
        type_hints={
            "command": AppendToolAttemptV2Command,
            "return": Cycle2DispatchFenceWriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.finalize_tool_attempt_if_current,
        parameters=("command",),
        type_hints={
            "command": FinalizeToolAttemptV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.save_shipment_observation_if_current,
        parameters=("command",),
        type_hints={
            "command": SaveShipmentObservationV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.save_shipment_assessment_if_current,
        parameters=("command",),
        type_hints={
            "command": SaveShipmentAssessmentV2Command,
            "return": Cycle2WriteResult,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.finalize_superseded_run_if_current,
        parameters=("command",),
        type_hints={
            "command": FinalizeSupersededRunV2Command,
            "return": Cycle2WriteResult,
        },
    )


def test_cycle2_owner_scoped_readers_are_keyword_only_exact_closures() -> None:
    _assert_signature(
        Cycle2RuntimeRecordPort.load_continuation_input_binding_closure_for_owner,
        parameters=(
            "owner_scope",
            "conversation_id",
            "message_id",
            "task_id",
            "request_unit_id",
            "trusted_now",
        ),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "conversation_id": UUID,
            "message_id": UUID,
            "task_id": UUID,
            "request_unit_id": UUID,
            "trusted_now": datetime,
            "return": ContinuationInputBindingReadClosure | None,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.load_order_search_current_closure_for_owner,
        parameters=(
            "owner_scope",
            "conversation_id",
            "run_id",
            "task_id",
            "request_unit_id",
            "trusted_read_at",
        ),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "conversation_id": UUID,
            "run_id": UUID,
            "task_id": UUID,
            "request_unit_id": UUID,
            "trusted_read_at": datetime,
            "return": OrderSearchCurrentReadClosure | None,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.load_order_candidate_selection_closure_for_owner,
        parameters=(
            "owner_scope",
            "conversation_id",
            "task_id",
            "request_unit_id",
            "selection_request",
            "trusted_now",
        ),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "conversation_id": UUID,
            "task_id": UUID,
            "request_unit_id": UUID,
            "selection_request": OrderCandidateSelectionRequest,
            "trusted_now": datetime,
            "return": OrderCandidateSelectionReadClosure | None,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.load_initial_tool_call_v2_closure_for_owner,
        parameters=(
            "owner_scope",
            "task_id",
            "request_unit_id",
            "trusted_read_at",
        ),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "task_id": UUID,
            "request_unit_id": UUID,
            "trusted_read_at": datetime,
            "return": InitialToolCallV2ReadClosure | None,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.load_shipment_assessment_closure_for_owner,
        parameters=(
            "owner_scope",
            "task_id",
                "request_unit_id",
                "verified_order_target_ref",
                "trusted_assessed_at",
            ),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "task_id": UUID,
            "request_unit_id": UUID,
                "verified_order_target_ref": NonEmptyString,
                "trusted_assessed_at": datetime,
                "return": ShipmentAssessmentReadClosure | None,
        },
    )
    _assert_signature(
        Cycle2RuntimeRecordPort.load_superseded_run_closure_for_owner,
        parameters=(
            "owner_scope",
            "obsolete_run_id",
            "replacement_run_id",
            "request_unit_id",
        ),
        type_hints={
            "owner_scope": TrustedOwnerScope,
            "obsolete_run_id": UUID,
            "replacement_run_id": UUID,
            "request_unit_id": UUID,
            "return": SupersededRunReadClosure | None,
        },
    )
    for method in (
        Cycle2RuntimeRecordPort.load_continuation_input_binding_closure_for_owner,
        Cycle2RuntimeRecordPort.load_order_search_current_closure_for_owner,
        Cycle2RuntimeRecordPort.load_order_candidate_selection_closure_for_owner,
        Cycle2RuntimeRecordPort.load_initial_tool_call_v2_closure_for_owner,
        Cycle2RuntimeRecordPort.load_shipment_assessment_closure_for_owner,
        Cycle2RuntimeRecordPort.load_superseded_run_closure_for_owner,
    ):
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for name, parameter in inspect.signature(method).parameters.items()
            if name != "self"
        )


def test_cycle2_port_docs_freeze_atomicity_and_no_authority_semantics() -> None:
    normalized_doc = " ".join((Cycle2RuntimeRecordPort.__doc__ or "").split())
    for required_term in (
        "Inactive",
        "exact-version-only",
        "transactionally consistent",
        "owner-scoped",
        "not caller-signed trust tokens",
        "re-read",
        "exact-compare",
        "atomic CAS",
        "absent",
        "unauthorized",
        "dangling",
        "duplicate",
        "wrong-owner",
        "partial",
        "mixed-version",
        "contradictory",
        "fails closed",
        "APPLIED",
        "zero writes",
        "Tool dispatch",
        "business-fact authority",
        "user-visible result authority",
    ):
        assert required_term in normalized_doc
    dispatch_doc = " ".join(
        (
            Cycle2RuntimeRecordPort.append_tool_attempt_if_current.__doc__
            or ""
        ).split()
    )
    assert "Only ``APPLIED``" in dispatch_doc
    assert "never grant dispatch" in dispatch_doc
    search_read_doc = " ".join(
        (
            Cycle2RuntimeRecordPort.load_order_search_current_closure_for_owner.__doc__
            or ""
        ).split()
    )
    for required_term in (
        "current query",
        "CandidateSet",
        "Search aggregate",
        "partial graph fails closed",
    ):
        assert required_term in search_read_doc
    search_write_doc = " ".join(
        (
            Cycle2RuntimeRecordPort.apply_order_search_outcome_if_current.__doc__
            or ""
        ).split()
    )
    for required_term in (
        "in-transaction read",
        "loaded_read_closure",
        "require_same_persisted_graph",
        "zero writes",
        "current Search graph",
    ):
        assert required_term in search_write_doc
    selection_write_doc = " ".join(
        (
            Cycle2RuntimeRecordPort
            .apply_order_candidate_selection_if_current.__doc__
            or ""
        ).split()
    )
    for required_term in (
        "command.require_live_target_issuance()",
        "immediately before",
        "copied",
        "deserialized",
        "reconstructed",
        "replay-bound",
        "zero writes",
    ):
        assert required_term in selection_write_doc
    assessment_write_doc = " ".join(
        (
            Cycle2RuntimeRecordPort.save_shipment_assessment_if_current.__doc__
            or ""
        ).split()
    )
    for required_term in (
        "same write transaction",
        "every current typed binding",
        "every Shipment Observation",
        "current Assessment",
        "exact-compare",
        "require_same_persisted_graph",
        "caller-provided completeness is never trusted",
    ):
        assert required_term in assessment_write_doc
    oa10_doc = " ".join(
        (
            Cycle2RuntimeRecordPort.finalize_superseded_run_if_current.__doc__
            or ""
        ).split()
    )
    for forbidden_write in (
        "Task",
        "RequestUnit",
        "Message",
        "AgentRunResult",
        "ResponseRendered",
    ):
        assert forbidden_write in oa10_doc
