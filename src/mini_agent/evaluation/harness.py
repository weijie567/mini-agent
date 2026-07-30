"""Injected E2E01 Eval Harness with structured Result/Failure separation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Annotated, Literal, Protocol, get_args
from uuid import NAMESPACE_URL, SafeUUID, UUID, uuid4, uuid5

import httpx
from pydantic import BaseModel, Field, create_model, model_validator
from pydantic_core import TzInfo

from mini_agent.application.ports import EvalResultPort
from mini_agent.application.records import (
    AgentRunResult,
    CriticalFailureCode,
    EvalExecutionFailurePhase,
    EvalExecutionFailureRecord,
    EvalExecutionSafeErrorCode,
    EvalGraderReasonCode,
    EvalGraderResult,
    EvalGraderStatus,
    EvalResultRecord,
    EvalResultStatus,
    EvalVersionManifest,
    ExactRunEvidenceClosure,
    InsertOnlyWriteResult,
)
from mini_agent.core.common import (
    AuditOnlyModel,
    FrozenJsonDict,
    FrozenJsonList,
)
from mini_agent.core.task_state import TaskStatus
from mini_agent.core.tool_system import (
    GateDecisionValue,
    GateReasonCode,
    ToolCallStatus,
    compute_model_visible_toolset_hash,
    get_order_tool_spec,
)
from mini_agent.core.trace import (
    AgentOutcome,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)
from mini_agent.evaluation.artifacts import (
    ArtifactContractError,
    EvalCaseArtifact,
    EvalLaneArtifact,
    LoadedE2E01Artifacts,
    ModelScriptArtifact,
)
from mini_agent.evaluation.graders import (
    EvalCaseExpectations,
    EvalEvidence,
    GradingConfigurationError,
    GradingOutcome,
    SafeCaseObservable,
    SafeTraceShapeEntry,
    TraceVariant,
    TraceEventCountExpectation,
    derive_grading_outcome,
    e2e01_04_safe_observables_match,
    _fixed_message,
    grade_evidence,
    ordinary_trace_shape,
)
from mini_agent.evaluation.scripted_provider import (
    RuntimeFaultDirective,
    ScriptedModelProviderV2,
)
from mini_agent.infrastructure.model.qwen_responses import (
    QwenResponsesAdapterV2,
)


class EvalHarnessCommandError(RuntimeError):
    """Bounded command failure when even safe failure persistence is unavailable."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("EVAL_HARNESS_COMMAND_FAILED")


class EvalExecutionMessage(AuditOnlyModel):
    role: Literal["user"]
    content: Annotated[str, Field(min_length=1)]


class EvalCaseExecutionInput(AuditOnlyModel):
    execution_ref: UUID
    messages: Annotated[
        tuple[EvalExecutionMessage, ...],
        Field(min_length=1, max_length=1),
    ]
    trusted_context_fixture_ref: Annotated[str, Field(min_length=1)]


class UnboundSafeCaseObservable(AuditOnlyModel):
    http_status: Annotated[int, Field(ge=100, le=599)]
    user_outcome: AgentOutcome
    response_policy: str
    ordinary_trace_shape: tuple[SafeTraceShapeEntry, ...]
    model_calls: Annotated[int, Field(ge=0)]


_UNBOUND_EVIDENCE_FIELD_ALLOWLIST = (
    "observed_outcome",
    "trace_ref",
    "trace_events",
    "schema_assertions_pass",
    "identity_boundary_assertions_pass",
    "request_understanding_assertions_pass",
    "input_binding_assertions_pass",
    "task_state_assertions_pass",
    "tool_call_assertions_pass",
    "observation_assertions_pass",
    "disclosure_assertions_pass",
    "renderer_fact_assertions_pass",
    "error_mapping_assertions_pass",
    "persistence_assertions_pass",
    "toolset_replay_assertions_pass",
    "run_record",
    "agent_result",
    "conversation_records",
    "message_records",
    "input_bindings",
    "task_records",
    "request_units",
    "conversation_task_links",
    "run_task_links",
    "gate_decisions",
    "tool_calls",
    "tool_attempts",
    "observations",
    "context_manifests",
    "model_visible_toolset_artifacts",
    "request_understanding_records_v2",
    "accepted_task_deltas_v2",
    "task_state_transitions",
)
_SEMANTIC_SCHEMA_IDENTITY_FIELDS = frozenset({"case_id"})
_SEMANTIC_IDENTITY_ENTITIES = frozenset({"case", "script"})
_SAFE_IDENTITY_FIELD_TOKEN_TUPLES = frozenset(
    {
        ("case", "status"),
        ("casefold",),
        ("casestatus",),
        ("customer", "case", "id"),
        ("customercaseid",),
        ("description",),
        ("description", "code"),
        ("description", "id"),
        ("descriptioncode",),
        ("descriptionid",),
        ("javascript", "ref"),
        ("javascript", "uuid"),
        ("javascriptref",),
        ("javascriptuuid",),
        ("lowercase", "id"),
        ("lowercaseid",),
        ("script", "owner", "id"),
        ("script", "version"),
        ("scriptownerid",),
        ("scripture",),
        ("scriptversion",),
        ("show", "case", "id"),
        ("showcase", "code"),
        ("showcase", "id"),
        ("showcasecode",),
        ("showcaseid",),
        ("staircase", "key"),
        ("staircase", "number"),
        ("staircasekey",),
        ("staircasenumber",),
        ("transcript", "reference"),
        ("transcript", "uuid"),
        ("transcriptreference",),
        ("transcriptuuid",),
        ("uppercase", "reference"),
        ("uppercasereference",),
        ("use", "case", "id"),
        ("use", "case", "label"),
        ("usecaseid",),
        ("usecaselabel",),
    }
)


def _identity_name_tokens(field_name: str) -> tuple[str, ...]:
    separated: list[str] = []
    for index, character in enumerate(field_name):
        previous = field_name[index - 1] if index else ""
        following = (
            field_name[index + 1]
            if index + 1 < len(field_name)
            else ""
        )
        if not character.isalnum():
            separated.append(" ")
            continue
        if (
            character.isupper()
            and previous.isalnum()
            and (
                previous.islower()
                or previous.isdigit()
                or (previous.isupper() and following.islower())
            )
        ):
            separated.append(" ")
        separated.append(character.casefold())
    return tuple("".join(separated).split())


def _is_semantic_identity_field(field_name: str) -> bool:
    tokens = _identity_name_tokens(field_name)
    if not tokens:
        return False
    if tokens in _SAFE_IDENTITY_FIELD_TOKEN_TUPLES:
        return False
    if any(
        token in _SEMANTIC_IDENTITY_ENTITIES
        for token in tokens
    ):
        return True
    compact = "".join(tokens)
    return any(
        entity in compact
        for entity in _SEMANTIC_IDENTITY_ENTITIES
    )


def _build_unbound_evidence_model() -> type[AuditOnlyModel]:
    bound_fields = frozenset(EvalEvidence.model_fields)
    expected_bound_fields = frozenset(
        {
            *_UNBOUND_EVIDENCE_FIELD_ALLOWLIST,
            "case_id",
            "safe_observable",
        }
    )
    if bound_fields != expected_bound_fields:
        raise RuntimeError("EvalEvidence changed without explicit SUT-boundary review")
    if any(
        field_name in _SEMANTIC_SCHEMA_IDENTITY_FIELDS
        for field_name in _UNBOUND_EVIDENCE_FIELD_ALLOWLIST
    ):
        raise RuntimeError(
            "semantic Case/Script identity entered unbound evidence"
        )
    field_definitions: dict[str, tuple[object, object]] = {}
    for field_name in _UNBOUND_EVIDENCE_FIELD_ALLOWLIST:
        field_info = EvalEvidence.model_fields[field_name]
        if field_info.is_required():
            default: object = ...
        elif field_info.default_factory is not None:
            default = Field(default_factory=field_info.default_factory)
        else:
            default = field_info.default
        field_definitions[field_name] = (field_info.annotation, default)
    return create_model(
        "UnboundEvalEvidence",
        __base__=AuditOnlyModel,
        __module__=__name__,
        **field_definitions,
    )


UnboundEvalEvidence = _build_unbound_evidence_model()


class EvalCaseSutResult(AuditOnlyModel):
    execution_ref: UUID
    evidence: UnboundEvalEvidence
    safe_observable: UnboundSafeCaseObservable


class EvalCaseSut(Protocol):
    async def execute_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        scripted_provider: ScriptedModelProviderV2,
        runtime_fault: RuntimeFaultDirective | None,
    ) -> EvalCaseSutResult | None: ...


class QwenBaselineSut(Protocol):
    async def execute_qwen_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        qwen_provider: QwenResponsesAdapterV2,
    ) -> EvalCaseSutResult | None: ...


class EvalTraceCallbacks(Protocol):
    async def append_eval_case_graded(self, event: TraceEvent) -> None: ...

    async def reload_trace(self, trace_ref: UUID) -> tuple[TraceEvent, ...]: ...


GraderRunner = Callable[
    [Sequence[str], EvalEvidence, EvalCaseExpectations],
    GradingOutcome,
]


class EvalLaneRunOutcome(AuditOnlyModel):
    lane: str
    results: tuple[EvalResultRecord, ...]
    execution_failures: tuple[EvalExecutionFailureRecord, ...]
    command_passed: bool

    @model_validator(mode="after")
    def command_status_matches_records(self) -> "EvalLaneRunOutcome":
        if self.command_passed and (
            self.execution_failures
            or not self.results
            or any(
                result.status is not EvalResultStatus.PASS for result in self.results
            )
        ):
            raise ValueError("passing command requires only complete PASS records")
        return self


class QwenBaselinePreflight(AuditOnlyModel):
    ready: bool
    not_run_record: EvalResultRecord | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def preflight_shape_is_consistent(self) -> "QwenBaselinePreflight":
        if self.ready:
            if self.not_run_record is not None or self.reason is not None:
                raise ValueError("ready baseline cannot carry NOT_RUN data")
        elif (
            self.not_run_record is None
            or self.not_run_record.status is not EvalResultStatus.NOT_RUN
            or self.not_run_record.lane != "qwen_baseline"
            or self.reason
            not in {"MISSING_REQUIRED_ENV", "REAL_EVAL_CASE_SUT_NOT_WIRED"}
        ):
            raise ValueError("not-ready baseline requires an empty NOT_RUN record")
        return self


@dataclass(frozen=True, slots=True)
class _QwenBaselineExecution:
    sut: QwenBaselineSut
    base_url: str
    api_key: str
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None


@dataclass(frozen=True, slots=True)
class _StagedCase:
    case: EvalCaseArtifact
    expectations: EvalCaseExpectations
    result: EvalResultRecord
    safe_observable: SafeCaseObservable


_ReplayCacheKey = tuple[UUID, str, str, int, str]


_FAILURE_CODE_BY_PHASE = {
    EvalExecutionFailurePhase.HARNESS_SETUP: (
        EvalExecutionSafeErrorCode.HARNESS_SETUP_FAILED
    ),
    EvalExecutionFailurePhase.CASE_SETUP: (
        EvalExecutionSafeErrorCode.CASE_SETUP_FAILED
    ),
    EvalExecutionFailurePhase.SYSTEM_UNDER_TEST: (
        EvalExecutionSafeErrorCode.SYSTEM_UNDER_TEST_FAILED
    ),
    EvalExecutionFailurePhase.GRADING: (EvalExecutionSafeErrorCode.GRADING_FAILED),
    EvalExecutionFailurePhase.RESULT_PERSISTENCE: (
        EvalExecutionSafeErrorCode.RESULT_PERSISTENCE_FAILED
    ),
    EvalExecutionFailurePhase.RESULT_COMPLETENESS: (
        EvalExecutionSafeErrorCode.RESULT_COMPLETENESS_FAILED
    ),
}


def _fresh_command_error() -> EvalHarnessCommandError:
    error = EvalHarnessCommandError()
    error.__cause__ = None
    error.__context__ = None
    return error


def _exact_run_eval_response_policy(
    stop_reason: StopReason,
) -> str | None:
    if stop_reason is StopReason.GOAL_COMPLETED:
        return "DETERMINISTIC_ORDER_SUMMARY_V1"
    if stop_reason is StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE:
        return "FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE"
    if stop_reason is StopReason.ORDER_SERVICE_UNAVAILABLE:
        return "FIXED_ORDER_SERVICE_UNAVAILABLE"
    if stop_reason in {
        StopReason.INPUT_INVALID,
        StopReason.GATE_REJECTED,
        StopReason.PROVIDER_PROTOCOL_ERROR,
        StopReason.PRESENTATION_PLAN_REJECTED,
        StopReason.RENDERER_INVARIANT_FAILED,
    }:
        return "FIXED_SAFE_PROCESSING_ERROR"
    return None


def _exact_run_eval_expected_outcome(
    stop_reason: StopReason,
) -> AgentOutcome | None:
    if stop_reason is StopReason.GOAL_COMPLETED:
        return AgentOutcome.COMPLETED
    if stop_reason is StopReason.NOT_FOUND_OR_NOT_ACCESSIBLE:
        return AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE
    if stop_reason in {
        StopReason.INPUT_INVALID,
        StopReason.GATE_REJECTED,
        StopReason.PROVIDER_PROTOCOL_ERROR,
        StopReason.ORDER_SERVICE_UNAVAILABLE,
        StopReason.PRESENTATION_PLAN_REJECTED,
        StopReason.RENDERER_INVARIANT_FAILED,
    }:
        return AgentOutcome.BLOCKED
    return None


def _exact_run_eval_detached_closure(
    value: object,
) -> ExactRunEvidenceClosure | None:
    if (
        type(value) is not ExactRunEvidenceClosure
        or not _model_storage_is_closed(
            value,
            ExactRunEvidenceClosure,
        )
        or any(
            not _payload_tree_is_closed(
                getattr(value, field_name),
                forbidden_identity_values=frozenset(),
                allow_any_schema_identity_value=True,
                allow_semantic_json_keys=True,
            )
            for field_name in ExactRunEvidenceClosure.model_fields
        )
    ):
        return None
    try:
        detached_fields: dict[str, object] = {}
        for field_name in ExactRunEvidenceClosure.model_fields:
            field_value = getattr(value, field_name)
            if field_value is None:
                detached_fields[field_name] = None
                continue
            if type(field_value) in _CANONICAL_PAYLOAD_MODEL_TYPES:
                detached = _detached_canonical_model(
                    field_value,
                    type(field_value),
                )
                if detached is None:
                    return None
                detached_fields[field_name] = detached
                continue
            if type(field_value) is not tuple:
                return None
            detached_items: list[BaseModel] = []
            for item in field_value:
                if type(item) not in _CANONICAL_PAYLOAD_MODEL_TYPES:
                    return None
                detached_item = _detached_canonical_model(
                    item,
                    type(item),
                )
                if detached_item is None:
                    return None
                detached_items.append(detached_item)
            detached_fields[field_name] = tuple(detached_items)
        rebuilt = ExactRunEvidenceClosure(
            **detached_fields,
        )
    except Exception:
        return None
    if (
        type(rebuilt) is not ExactRunEvidenceClosure
        or not _model_storage_is_closed(
            rebuilt,
            ExactRunEvidenceClosure,
        )
        or any(
            not _payload_tree_is_closed(
                getattr(rebuilt, field_name),
                forbidden_identity_values=frozenset(),
                allow_any_schema_identity_value=True,
                allow_semantic_json_keys=True,
            )
            for field_name in ExactRunEvidenceClosure.model_fields
        )
        or not _same_exact_value_tree(value, rebuilt)
        or rebuilt != value
    ):
        return None
    return rebuilt


def _exact_run_eval_map_result(
    *,
    execution_ref: UUID,
    http_status: int,
    agent_result: AgentRunResult,
    closure: ExactRunEvidenceClosure,
) -> tuple[str, EvalCaseSutResult | None]:
    mapped_result: EvalCaseSutResult | None = None
    try:
        detached_execution_ref = _detached_closed_uuid(execution_ref)
        detached_agent_result = _detached_canonical_model(
            agent_result,
            AgentRunResult,
        )
        detached_closure = _exact_run_eval_detached_closure(closure)
        if (
            detached_execution_ref is None
            or detached_execution_ref.version != 4
            or type(http_status) is not int
            or http_status != 200
            or type(detached_agent_result) is not AgentRunResult
            or type(detached_closure) is not ExactRunEvidenceClosure
        ):
            return "FAILED", None
        run = detached_closure.run_record
        stop_reason = run.stop_reason
        if (
            run.status is not AgentRunStatus.COMPLETED
            or stop_reason is None
            or detached_agent_result.run_id != run.run_id
            or not detached_closure.trace_events
            or any(
                event.run_id != run.run_id or event.case_id is not None
                for event in detached_closure.trace_events
            )
        ):
            return "FAILED", None
        response_policy = _exact_run_eval_response_policy(stop_reason)
        expected_outcome = _exact_run_eval_expected_outcome(stop_reason)
        if (
            response_policy is None
            or expected_outcome is None
            or detached_agent_result.outcome is not expected_outcome
        ):
            return "FAILED", None
        fixed_message = _fixed_message(response_policy)
        if (
            fixed_message is not None
            and detached_agent_result.message != fixed_message
        ):
            return "FAILED", None
        understanding_records = (
            (detached_closure.request_understanding_record,)
            if detached_closure.request_understanding_record is not None
            else ()
        )
        evidence = UnboundEvalEvidence(
            observed_outcome=detached_agent_result.outcome,
            trace_ref=run.run_id,
            trace_events=detached_closure.trace_events,
            run_record=run,
            agent_result=detached_agent_result,
            conversation_records=(detached_closure.conversation_record,),
            message_records=detached_closure.message_records,
            input_bindings=detached_closure.input_binding_records,
            task_records=detached_closure.task_records,
            request_units=detached_closure.request_unit_records,
            conversation_task_links=(
                detached_closure.conversation_task_links
            ),
            run_task_links=detached_closure.run_task_links,
            gate_decisions=detached_closure.gate_decisions,
            tool_calls=detached_closure.tool_calls,
            tool_attempts=detached_closure.tool_attempts,
            observations=detached_closure.observation_records,
            context_manifests=detached_closure.context_manifests,
            model_visible_toolset_artifacts=(
                detached_closure.model_visible_toolset_artifacts
            ),
            request_understanding_records_v2=understanding_records,
            accepted_task_deltas_v2=(
                detached_closure.accepted_task_deltas
            ),
            task_state_transitions=(
                detached_closure.task_state_transitions
            ),
        )
        safe_observable = UnboundSafeCaseObservable(
            http_status=http_status,
            user_outcome=detached_agent_result.outcome,
            response_policy=response_policy,
            ordinary_trace_shape=ordinary_trace_shape(
                detached_closure.trace_events
            ),
            model_calls=len(detached_closure.context_manifests),
        )
        candidate_result = EvalCaseSutResult(
            execution_ref=detached_execution_ref,
            evidence=evidence,
            safe_observable=safe_observable,
        )
        mapped_result = _canonical_unbound_result(
            candidate_result,
            authenticated_identity_values=frozenset(),
        )
    except Exception:
        return "FAILED", None
    if mapped_result is None:
        return "FAILED", None
    return "SUCCESS", mapped_result


def map_exact_run_http_result_to_sut_result(
    *,
    execution_ref: UUID,
    http_status: int,
    agent_result: AgentRunResult,
    closure: ExactRunEvidenceClosure,
) -> EvalCaseSutResult:
    status, mapped_result = _exact_run_eval_map_result(
        execution_ref=execution_ref,
        http_status=http_status,
        agent_result=agent_result,
        closure=closure,
    )
    execution_ref = None  # type: ignore[assignment]
    http_status = None  # type: ignore[assignment]
    agent_result = None  # type: ignore[assignment]
    closure = None  # type: ignore[assignment]
    if status != "SUCCESS" or mapped_result is None:
        raise _fresh_command_error()
    return mapped_result


_NO_CANONICAL_REQUEST_OUTPUT = frozenset(
    {
        "INJECT_ZERO_TARGET_FUNCTION_CALLS",
        "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
        "INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA",
        "INJECT_SOURCE_AUTHORITY_MISMATCH",
        "INJECT_TRUSTED_FIELD_OVERRIDE",
    }
)
_EXPECTED_MODEL_VISIBLE_TOOLSET_HASH = compute_model_visible_toolset_hash(
    (get_order_tool_spec(),)
)
_BASE_TRACE_VARIANT_BY_CASE_ID: Mapping[str, TraceVariant] = {
    "E2E01-01": "SUCCESS",
    "E2E01-04-A": "FOREIGN_ORDER",
    "E2E01-04-B": "NONEXISTENT_ORDER",
    "E2E01-01+SEC-ARGUMENT-BINDING": "ARGUMENT_BINDING_REJECTED",
}
_TRACE_VARIANT_FROM_ARTIFACT_NAME: Mapping[str, TraceVariant] = {
    "PROVIDER_PROTOCOL_BEFORE_CANDIDATE": (
        "PROVIDER_PROTOCOL_BEFORE_CANDIDATE"
    ),
    "INPUT_VALIDATION_REJECTED": "INPUT_VALIDATION_REJECTED",
    "CONTROL_GATEWAY_REJECTED": "UNKNOWN_TOOL_GATEWAY_REJECTED",
    "CONTROL_GATEWAY_STALE_STATE_REJECTED": (
        "STALE_STATE_GATEWAY_REJECTED"
    ),
    "PRESENTATION_PROTOCOL_REJECTED": "PRESENTATION_PROTOCOL_REJECTED",
}


def _case_trace_expectations(
    case: EvalCaseArtifact,
    *,
    model_script_ref: str,
) -> tuple[
    tuple[TraceEventType, ...],
    tuple[TraceEventType, ...],
    tuple[TraceEventCountExpectation, ...],
    TraceVariant,
]:
    selected: Mapping[str, object] = case.expectations
    variants = case.expectations.get("trace_expectation_variants", ())
    if not isinstance(variants, tuple):
        raise ArtifactContractError("Trace variants are not authenticated tuples")
    matches = tuple(
        item
        for item in variants
        if isinstance(item, Mapping)
        and model_script_ref in tuple(item.get("model_script_refs", ()))
    )
    if len(matches) > 1:
        raise ArtifactContractError("model script matches multiple Trace variants")
    trace_variant = _BASE_TRACE_VARIANT_BY_CASE_ID.get(case.case_id)
    if matches:
        selected = matches[0]
        artifact_variant = selected.get("variant")
        if not isinstance(artifact_variant, str):
            raise ArtifactContractError("Trace variant identity is invalid")
        trace_variant = _TRACE_VARIANT_FROM_ARTIFACT_NAME.get(
            artifact_variant
        )
    if trace_variant is None:
        raise ArtifactContractError("Case/script Trace variant is not closed")
    required = tuple(
        TraceEventType(value) for value in tuple(selected.get("required_events", ()))
    )
    forbidden = tuple(
        TraceEventType(value) for value in tuple(selected.get("forbidden_events", ()))
    )
    counts: list[TraceEventCountExpectation] = []
    for item in tuple(selected.get("event_count_assertions", ())):
        if (
            not isinstance(item, Mapping)
            or item.get("operator") != "EQUALS"
            or type(item.get("count")) is not int
        ):
            raise ArtifactContractError("Trace count assertion is not closed")
        counts.append(
            TraceEventCountExpectation(
                event_type=TraceEventType(item["event"]),
                count=item["count"],
            )
        )
    return required, forbidden, tuple(counts), trace_variant


def _terminal_state_version(
    control: Mapping[str, object],
    *,
    record: str,
) -> int | None:
    direct_keys = (
        f"resulting_{record}_state_version",
        f"terminal_{record}_state_version",
    )
    for key in direct_keys:
        value = control.get(key)
        if type(value) is int and value >= 1:
            return value
    delta = control.get(f"{record}_state_version_delta")
    if type(delta) is int and delta >= 0:
        return 1 + delta
    return None


def _trusted_customer_for_case(
    artifacts: LoadedE2E01Artifacts,
    case: EvalCaseArtifact,
) -> str:
    fixture_ref = case.input.get("trusted_context_fixture_ref")
    sessions = artifacts.fixture.get("sessions", ())
    matches = tuple(
        item
        for item in sessions
        if isinstance(item, Mapping) and item.get("fixture_ref") == fixture_ref
    )
    if len(matches) != 1:
        raise ArtifactContractError("Case trusted fixture is not unique")
    customer_id = matches[0].get("trusted_customer_id")
    if not isinstance(customer_id, str) or not customer_id:
        raise ArtifactContractError("trusted customer fixture is invalid")
    return customer_id


def _trusted_message_content_for_case(case: EvalCaseArtifact) -> str:
    messages = case.input.get("messages")
    if (
        not isinstance(messages, tuple)
        or len(messages) != 1
        or not isinstance(messages[0], Mapping)
        or messages[0].get("role") != "user"
    ):
        raise ArtifactContractError("Case user message is not unique")
    content = messages[0].get("content")
    if not isinstance(content, str) or not content:
        raise ArtifactContractError("Case user message content is invalid")
    return content


def _normalized_selected_script_ref(
    case: EvalCaseArtifact,
    selected_script_ref: str | None,
) -> str:
    script_refs = tuple(case.input.get("model_script_refs", ()))
    if selected_script_ref is None:
        if len(script_refs) != 1:
            raise ArtifactContractError(
                "multi-script Case requires explicit script selection"
            )
        selected_script_ref = script_refs[0]
    if (
        type(selected_script_ref) is not str
        or selected_script_ref not in script_refs
    ):
        raise ArtifactContractError("selected script is not bound to Case")
    return selected_script_ref


def build_authenticated_case_expectations(
    *,
    artifacts: LoadedE2E01Artifacts,
    case: EvalCaseArtifact,
    script: ModelScriptArtifact,
) -> EvalCaseExpectations:
    control = script.expected_control_result
    first_step = script.steps[0] if script.steps else {}
    behavior = first_step.get("behavior")
    request_required = behavior not in _NO_CANONICAL_REQUEST_OUTPUT
    message_order_id = first_step.get("message_order_number", "O-1001")
    next_move_order_id = first_step.get(
        "next_move_order_number",
        message_order_id,
    )
    requested_tool_name = first_step.get("requested_tool_name", "get_order")
    if not all(
        isinstance(value, str) and value
        for value in (
            message_order_id,
            next_move_order_id,
            requested_tool_name,
        )
    ):
        raise ArtifactContractError("script candidate expectations are invalid")

    task_forbidden = control.get("task_creation") == "FORBIDDEN"
    task_status_value = control.get("task_terminal_status")
    unit_status_value = control.get("request_unit_terminal_status")
    task_status = (
        None
        if task_forbidden
        else TaskStatus(task_status_value)
        if isinstance(task_status_value, str)
        else None
    )
    unit_status = (
        None
        if task_forbidden
        else TaskStatus(unit_status_value)
        if isinstance(unit_status_value, str)
        else None
    )
    task_version = (
        None if task_forbidden else _terminal_state_version(control, record="task")
    )
    unit_version = (
        None
        if task_forbidden
        else _terminal_state_version(control, record="request_unit")
    )

    tool_calls = control.get("tool_calls")
    observations = control.get("observation_records")
    model_calls = control.get("model_calls")
    presentation_calls = control.get("presentation_model_calls")
    if not all(
        type(value) is int and value >= 0
        for value in (
            tool_calls,
            observations,
            model_calls,
            presentation_calls,
        )
    ):
        raise ArtifactContractError("script count expectations are invalid")
    assert isinstance(tool_calls, int)
    assert isinstance(observations, int)
    assert isinstance(model_calls, int)
    assert isinstance(presentation_calls, int)

    gate_value = control.get("gate_decision")
    gate_decision = (
        GateDecisionValue(gate_value)
        if isinstance(gate_value, str)
        else GateDecisionValue.ACCEPT
        if tool_calls == 1
        else None
    )
    gate_reason_projection = control.get("gate_reason_expectation")
    gate_reason_value = (
        gate_reason_projection.get("canonical_reason_code")
        if isinstance(gate_reason_projection, Mapping)
        else None
    )
    gate_reason = (
        GateReasonCode(gate_reason_value)
        if isinstance(gate_reason_value, str)
        else None
    )
    tool_status_value = control.get("tool_call_terminal_status")
    tool_status = (
        ToolCallStatus(tool_status_value)
        if isinstance(tool_status_value, str)
        else None
    )

    required, forbidden, counts, trace_variant = _case_trace_expectations(
        case,
        model_script_ref=script.model_script_ref,
    )
    critical_values = tuple(
        CriticalFailureCode(value)
        for value in tuple(case.expectations.get("critical_failure_refs", ()))
    )
    version = case.version_manifest.get("tool_registry_version")
    if not isinstance(version, str) or not version:
        raise ArtifactContractError("Case tool registry version is invalid")
    return EvalCaseExpectations(
        case_id=case.case_id,
        trusted_customer_id=_trusted_customer_for_case(artifacts, case),
        expected_http_status=case.expectations["expected_http_status"],
        expected_outcome=AgentOutcome(
            control.get(
                "user_outcome",
                case.expectations["expected_user_outcome"],
            )
        ),
        expected_run_status=AgentRunStatus(control["run_status"]),
        expected_stop_reason=StopReason(control["stop_reason"]),
        expected_response_policy=control["response_policy"],
        request_understanding_required=request_required,
        expected_binding_order_id=message_order_id,
        expected_next_move_order_id=next_move_order_id,
        expected_requested_tool_name=requested_tool_name,
        expected_task_status=task_status,
        expected_request_unit_status=unit_status,
        expected_task_state_version=task_version,
        expected_request_unit_state_version=unit_version,
        expected_gate_decision=gate_decision,
        expected_gate_reason=gate_reason,
        expected_validated_task_state_version=(
            1 if gate_decision is not None else None
        ),
        expected_tool_call_status=tool_status,
        expected_tool_calls=tool_calls,
        expected_observations=observations,
        expected_model_calls=model_calls,
        expected_presentation_model_calls=presentation_calls,
        expected_message_content=_trusted_message_content_for_case(case),
        expected_tool_registry_version=version,
        expected_model_visible_toolset_hash=(_EXPECTED_MODEL_VISIBLE_TOOLSET_HASH),
        trace_variant=trace_variant,
        required_trace_events=required,
        forbidden_trace_events=forbidden,
        expected_event_counts=counts,
        applicable_critical_failures=critical_values,
    )


def _model_storage_is_closed(
    value: BaseModel,
    expected_type: type[BaseModel],
) -> bool:
    if type(value) is not expected_type:
        return False
    storage = value.__dict__
    fields_set = value.__pydantic_fields_set__
    if type(storage) is not dict or type(fields_set) is not set:
        return False
    field_names = frozenset(expected_type.model_fields)
    if (
        len(storage) != len(field_names)
        or len(fields_set) > len(field_names)
    ):
        return False
    stored_names = tuple(dict.__iter__(storage))
    explicit_names = tuple(set.__iter__(fields_set))
    if any(type(name) is not str for name in (*stored_names, *explicit_names)):
        return False
    return (
        frozenset(stored_names) == field_names
        and fields_set <= field_names
        and value.__pydantic_extra__ is None
        and value.__pydantic_private__ is None
    )


def _annotation_runtime_types(
    annotation: object,
    *,
    visited: set[int],
) -> tuple[type[object], ...]:
    annotation_id = id(annotation)
    if annotation_id in visited:
        return ()
    visited.add(annotation_id)
    discovered: list[type[object]] = []
    if isinstance(annotation, type):
        discovered.append(annotation)
    elif isinstance(annotation, Enum):
        discovered.append(type(annotation))
    for nested in get_args(annotation):
        discovered.extend(
            _annotation_runtime_types(
                nested,
                visited=visited,
            )
        )
    return tuple(discovered)


def _reachable_result_types(
    root_models: tuple[type[BaseModel], ...],
) -> tuple[frozenset[type[BaseModel]], frozenset[type[Enum]]]:
    model_types: set[type[BaseModel]] = set()
    enum_types: set[type[Enum]] = set()
    pending = list(root_models)
    while pending:
        model_type = pending.pop()
        if model_type in model_types:
            continue
        model_types.add(model_type)
        for model_field in model_type.model_fields.values():
            for runtime_type in _annotation_runtime_types(
                model_field.annotation,
                visited=set(),
            ):
                if issubclass(runtime_type, Enum):
                    enum_types.add(runtime_type)
                elif (
                    issubclass(runtime_type, BaseModel)
                    and runtime_type not in model_types
                ):
                    pending.append(runtime_type)
    return frozenset(model_types), frozenset(enum_types)


(
    _CANONICAL_RESULT_MODEL_TYPES,
    _CANONICAL_RESULT_ENUM_TYPES,
) = _reachable_result_types(
    (
        EvalCaseSutResult,
        EvalEvidence,
        SafeCaseObservable,
    )
)
(
    _ADDITIONAL_BOUNDARY_MODEL_TYPES,
    _ADDITIONAL_BOUNDARY_ENUM_TYPES,
) = _reachable_result_types(
    (
        EvalCaseExpectations,
        EvalExecutionFailureRecord,
        EvalResultRecord,
        GradingOutcome,
        LoadedE2E01Artifacts,
    )
)
_CANONICAL_PAYLOAD_MODEL_TYPES = (
    _CANONICAL_RESULT_MODEL_TYPES
    | _ADDITIONAL_BOUNDARY_MODEL_TYPES
)

_DISCOVERED_SEMANTIC_SCHEMA_IDENTITY_FIELDS = frozenset(
    field_name
    for model_type in _CANONICAL_RESULT_MODEL_TYPES
    for field_name in model_type.model_fields
    if _is_semantic_identity_field(field_name)
)
if (
    _DISCOVERED_SEMANTIC_SCHEMA_IDENTITY_FIELDS
    != _SEMANTIC_SCHEMA_IDENTITY_FIELDS
):
    raise RuntimeError(
        "canonical Eval result schema identity fields changed"
    )


def _canonical_scalar_is_closed(value: object) -> bool:
    if value is None or type(value) in {bool, int, str}:
        return True
    return type(value) is float and isfinite(value)


@dataclass(frozen=True, slots=True)
class _CanonicalEnumMemberSnapshot:
    member: Enum
    storage_items: tuple[tuple[str, object], ...]


_ENUM_TYPES_WITH_CLOSED_STORAGE = (
    _CANONICAL_RESULT_ENUM_TYPES
    | _ADDITIONAL_BOUNDARY_ENUM_TYPES
    | frozenset({InsertOnlyWriteResult, SafeUUID})
)


def _build_canonical_enum_member_snapshots() -> (
    Mapping[type[Enum], tuple[_CanonicalEnumMemberSnapshot, ...]]
):
    by_type: dict[
        type[Enum],
        tuple[_CanonicalEnumMemberSnapshot, ...],
    ] = {}
    for enum_type in _ENUM_TYPES_WITH_CLOSED_STORAGE:
        snapshots: list[_CanonicalEnumMemberSnapshot] = []
        for member in enum_type:
            if type(member) is not enum_type:
                raise RuntimeError(
                    "canonical Eval result Enum member type changed"
                )
            storage = object.__getattribute__(member, "__dict__")
            if type(storage) is not dict:
                raise RuntimeError(
                    "canonical Eval result Enum storage changed"
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
                    _canonical_scalar_is_closed(stored_value)
                    or stored_value is enum_type
                )
                for key, stored_value in storage_items
            ):
                raise RuntimeError(
                    "canonical Eval result Enum storage is not closed"
                )
            snapshots.append(
                _CanonicalEnumMemberSnapshot(
                    member=member,
                    storage_items=storage_items,
                )
            )
        by_type[enum_type] = tuple(snapshots)
    return MappingProxyType(by_type)


_CANONICAL_ENUM_MEMBER_SNAPSHOTS = (
    _build_canonical_enum_member_snapshots()
)


def _canonical_enum_member_is_closed(value: Enum) -> bool:
    enum_type = type(value)
    snapshots = _CANONICAL_ENUM_MEMBER_SNAPSHOTS.get(enum_type)
    if snapshots is None:
        return False
    snapshot = next(
        (
            candidate
            for candidate in snapshots
            if value is candidate.member
        ),
        None,
    )
    if snapshot is None:
        return False
    storage = object.__getattribute__(value, "__dict__")
    if (
        type(storage) is not dict
        or len(storage) != len(snapshot.storage_items)
    ):
        return False
    stored_names = tuple(dict.__iter__(storage))
    if (
        any(type(name) is not str for name in stored_names)
        or stored_names
        != tuple(name for name, _ in snapshot.storage_items)
    ):
        return False
    for name, expected_value in snapshot.storage_items:
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


def _canonical_singleton_state_is_closed() -> bool:
    return all(
        _canonical_enum_member_is_closed(snapshot.member)
        for snapshots in _CANONICAL_ENUM_MEMBER_SNAPSHOTS.values()
        for snapshot in snapshots
    )


def _restore_canonical_singleton_state() -> bool:
    try:
        for snapshots in _CANONICAL_ENUM_MEMBER_SNAPSHOTS.values():
            for snapshot in snapshots:
                storage = object.__getattribute__(
                    snapshot.member,
                    "__dict__",
                )
                if type(storage) is not dict:
                    return False
                dict.clear(storage)
                for name, stored_value in snapshot.storage_items:
                    dict.__setitem__(
                        storage,
                        name,
                        stored_value,
                    )
    except Exception:
        return False
    return _canonical_singleton_state_is_closed()


def _datetime_is_closed(value: datetime) -> bool:
    tz = object.__getattribute__(value, "tzinfo")
    if tz is timezone.utc:
        return True
    if type(tz) is not TzInfo:
        return False
    offset = TzInfo.utcoffset(tz, value)
    return type(offset) is timedelta and offset == timedelta(0)


def _uuid_is_closed(value: UUID) -> bool:
    integer = object.__getattribute__(value, "int")
    safety = object.__getattribute__(value, "is_safe")
    return (
        type(integer) is int
        and 0 <= integer < 1 << 128
        and type(safety) is SafeUUID
        and _canonical_enum_member_is_closed(
            safety
        )
    )


def _detached_closed_uuid(value: object) -> UUID | None:
    if type(value) is not UUID or not _uuid_is_closed(value):
        return None
    try:
        return UUID(
            int=object.__getattribute__(value, "int"),
            is_safe=object.__getattribute__(
                value,
                "is_safe",
            ),
        )
    except Exception:
        return None


def _detached_closed_datetime(value: object) -> datetime | None:
    if type(value) is not datetime or not _datetime_is_closed(value):
        return None
    try:
        return datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            tzinfo=timezone.utc,
            fold=value.fold,
        )
    except Exception:
        return None


@dataclass(slots=True)
class _PayloadTraversalState:
    active_ids: set[int] = field(default_factory=set)
    completed_ids: set[int] = field(default_factory=set)
    validation_counts: dict[int, int] = field(default_factory=dict)
    visited_edges: int = 0


_MAX_PAYLOAD_DEPTH = 64
_MAX_PAYLOAD_EDGES = 8192


def _consume_payload_edges(
    traversal: _PayloadTraversalState,
    *,
    parent_depth: int,
    count: int,
) -> bool:
    if parent_depth >= _MAX_PAYLOAD_DEPTH:
        return False
    next_count = traversal.visited_edges + count
    if next_count > _MAX_PAYLOAD_EDGES:
        return False
    traversal.visited_edges = next_count
    return True


def _validate_immutable_node(
    value: object,
    *,
    traversal: _PayloadTraversalState,
    validator: Callable[[], bool],
) -> bool:
    value_id = id(value)
    if value_id in traversal.completed_ids:
        return type(value) is tuple and len(value) == 0
    if value_id in traversal.active_ids:
        return False
    traversal.validation_counts[value_id] = (
        traversal.validation_counts.get(value_id, 0) + 1
    )
    traversal.active_ids.add(value_id)
    try:
        valid = validator()
    finally:
        traversal.active_ids.remove(value_id)
    if valid:
        traversal.completed_ids.add(value_id)
    return valid


def _json_payload_is_closed(
    value: object,
    *,
    forbidden_identity_values: frozenset[str],
    traversal: _PayloadTraversalState,
    depth: int,
    allow_semantic_keys: bool = False,
) -> bool:
    if depth > _MAX_PAYLOAD_DEPTH:
        return False
    if type(value) is str:
        return value not in forbidden_identity_values
    if value is None or type(value) in {bool, int}:
        return True
    if type(value) is float:
        return isfinite(value)
    if type(value) is FrozenJsonDict:
        def validate_mapping() -> bool:
            keys: set[str] = set()
            for raw_pair in tuple.__iter__(value):
                if not _consume_payload_edges(
                    traversal,
                    parent_depth=depth,
                    count=2,
                ):
                    return False
                if type(raw_pair) is not tuple or len(raw_pair) != 2:
                    return False
                key, item = raw_pair
                if (
                    type(key) is not str
                    or key in keys
                    or key in forbidden_identity_values
                    or (
                        not allow_semantic_keys
                        and _is_semantic_identity_field(key)
                    )
                ):
                    return False
                keys.add(key)
                if not _json_payload_is_closed(
                    item,
                    forbidden_identity_values=forbidden_identity_values,
                    traversal=traversal,
                    depth=depth + 1,
                    allow_semantic_keys=allow_semantic_keys,
                ):
                    return False
            return True

        return _validate_immutable_node(
            value,
            traversal=traversal,
            validator=validate_mapping,
        )
    if type(value) is FrozenJsonList:
        return _validate_immutable_node(
            value,
            traversal=traversal,
            validator=lambda: all(
                _consume_payload_edges(
                    traversal,
                    parent_depth=depth,
                    count=1,
                )
                and _json_payload_is_closed(
                    item,
                    forbidden_identity_values=forbidden_identity_values,
                    traversal=traversal,
                    depth=depth + 1,
                    allow_semantic_keys=allow_semantic_keys,
                )
                for item in tuple.__iter__(value)
            ),
        )
    return False


def _payload_tree_is_closed(
    value: object,
    *,
    forbidden_identity_values: frozenset[str],
    traversal: _PayloadTraversalState | None = None,
    depth: int = 0,
    allowed_schema_identity_values: (
        Mapping[str, frozenset[str]] | None
    ) = None,
    allow_any_schema_identity_value: bool = False,
    allow_semantic_json_keys: bool = False,
    _allow_current_identity_value: bool = False,
) -> bool:
    traversal = traversal or _PayloadTraversalState()
    if depth > _MAX_PAYLOAD_DEPTH:
        return False
    value_type = type(value)
    if (
        value_type is str
        and value in forbidden_identity_values
        and not _allow_current_identity_value
    ):
        return False
    if value_type in _CANONICAL_PAYLOAD_MODEL_TYPES:
        def validate_model() -> bool:
            if not _model_storage_is_closed(value, value_type):
                return False
            field_names = tuple(value_type.model_fields)
            storage = value.__dict__
            for field_name in field_names:
                if not _consume_payload_edges(
                    traversal,
                    parent_depth=depth,
                    count=1,
                ):
                    return False
                field_value = dict.__getitem__(storage, field_name)
                allow_field_identity = False
                if (
                    field_name
                    in _DISCOVERED_SEMANTIC_SCHEMA_IDENTITY_FIELDS
                    and field_value is not None
                ):
                    allowed_values = (
                        allowed_schema_identity_values.get(
                            field_name,
                            frozenset(),
                        )
                        if allowed_schema_identity_values is not None
                        else frozenset()
                    )
                    if (
                        type(field_value) is not str
                        or (
                            not allow_any_schema_identity_value
                            and field_value not in allowed_values
                        )
                    ):
                        return False
                    allow_field_identity = True
                if not _payload_tree_is_closed(
                    field_value,
                    forbidden_identity_values=forbidden_identity_values,
                    traversal=traversal,
                    depth=depth + 1,
                    allowed_schema_identity_values=(
                        allowed_schema_identity_values
                    ),
                    allow_any_schema_identity_value=(
                        allow_any_schema_identity_value
                    ),
                    allow_semantic_json_keys=(
                        allow_semantic_json_keys
                    ),
                    _allow_current_identity_value=(
                        allow_field_identity
                    ),
                ):
                    return False
            return True

        return _validate_immutable_node(
            value,
            traversal=traversal,
            validator=validate_model,
        )
    if value_type in {FrozenJsonDict, FrozenJsonList}:
        return _json_payload_is_closed(
            value,
            forbidden_identity_values=forbidden_identity_values,
            traversal=traversal,
            depth=depth,
            allow_semantic_keys=allow_semantic_json_keys,
        )
    if value_type is tuple:
        return _validate_immutable_node(
            value,
            traversal=traversal,
            validator=lambda: all(
                _consume_payload_edges(
                    traversal,
                    parent_depth=depth,
                    count=1,
                )
                and _payload_tree_is_closed(
                    item,
                    forbidden_identity_values=forbidden_identity_values,
                    traversal=traversal,
                    depth=depth + 1,
                    allowed_schema_identity_values=(
                        allowed_schema_identity_values
                    ),
                    allow_any_schema_identity_value=(
                        allow_any_schema_identity_value
                    ),
                    allow_semantic_json_keys=(
                        allow_semantic_json_keys
                    ),
                )
                for item in tuple.__iter__(value)
            ),
        )
    if value_type in _ENUM_TYPES_WITH_CLOSED_STORAGE:
        if not _canonical_enum_member_is_closed(value):
            return False
        storage = object.__getattribute__(value, "__dict__")
        enum_value = dict.__getitem__(storage, "_value_")
        return (
            _canonical_scalar_is_closed(enum_value)
            and not (
                type(enum_value) is str
                and enum_value in forbidden_identity_values
            )
        )
    if value_type is datetime:
        return _datetime_is_closed(value)
    if value_type is UUID:
        return _uuid_is_closed(value)
    if value is None or value_type in {
        bool,
        int,
        str,
        timedelta,
    }:
        return True
    return value_type is float and isfinite(value)


@dataclass(slots=True)
class _ExactTreeComparisonState:
    active_pairs: set[tuple[int, int]] = field(default_factory=set)
    completed_pairs: set[tuple[int, int]] = field(default_factory=set)


def _same_exact_value_tree(
    original: object,
    rebuilt: object,
    *,
    state: _ExactTreeComparisonState | None = None,
) -> bool:
    if type(original) is not type(rebuilt):
        return False
    if isinstance(original, Enum):
        return original is rebuilt
    if isinstance(original, BaseModel):
        pair = (id(original), id(rebuilt))
        state = state or _ExactTreeComparisonState()
        if pair in state.completed_pairs:
            return True
        if pair in state.active_pairs:
            return False
        state.active_pairs.add(pair)
        try:
            field_names = tuple(type(original).model_fields)
            valid = all(
                _same_exact_value_tree(
                    getattr(original, field_name),
                    getattr(rebuilt, field_name),
                    state=state,
                )
                for field_name in field_names
            )
        finally:
            state.active_pairs.remove(pair)
        if valid:
            state.completed_pairs.add(pair)
        return valid
    if type(original) in {
        tuple,
        FrozenJsonDict,
        FrozenJsonList,
    }:
        pair = (id(original), id(rebuilt))
        state = state or _ExactTreeComparisonState()
        if pair in state.completed_pairs:
            return True
        if pair in state.active_pairs:
            return False
        original_items = tuple(tuple.__iter__(original))
        rebuilt_items = tuple(tuple.__iter__(rebuilt))
        if len(original_items) != len(rebuilt_items):
            return False
        state.active_pairs.add(pair)
        try:
            valid = all(
                _same_exact_value_tree(
                    original_item,
                    rebuilt_item,
                    state=state,
                )
                for original_item, rebuilt_item in zip(
                    original_items,
                    rebuilt_items,
                    strict=True,
                )
            )
        finally:
            state.active_pairs.remove(pair)
        if valid:
            state.completed_pairs.add(pair)
        return valid
    if original is None:
        return True
    if type(original) in {datetime, UUID}:
        return original is not rebuilt and original == rebuilt
    if type(original) in {
        bool,
        float,
        int,
        str,
        timedelta,
    }:
        return original == rebuilt
    return False


def _canonical_unbound_result(
    result: EvalCaseSutResult,
    *,
    authenticated_identity_values: frozenset[str],
) -> EvalCaseSutResult | None:
    if (
        not _canonical_singleton_state_is_closed()
        or not _model_storage_is_closed(
            result,
            EvalCaseSutResult,
        )
    ):
        return None
    # The unbound Eval boundary fails closed on an exact authenticated
    # Case/Script identity anywhere in SUT-returned structured evidence.
    if not _payload_tree_is_closed(
        result,
        forbidden_identity_values=authenticated_identity_values,
    ):
        return None
    try:
        projection = result.model_dump_json(
            round_trip=True,
            warnings="error",
        )
        if type(projection) is not str:
            return None
        rebuilt = EvalCaseSutResult.model_validate_json(
            projection,
            strict=True,
        )
    except Exception:
        return None
    if (
        type(rebuilt) is not EvalCaseSutResult
        or not _canonical_singleton_state_is_closed()
        or not _same_exact_value_tree(result, rebuilt)
        or rebuilt != result
        or not _model_storage_is_closed(
            rebuilt,
            EvalCaseSutResult,
        )
        or not _payload_tree_is_closed(
            rebuilt,
            forbidden_identity_values=authenticated_identity_values,
        )
    ):
        return None
    evidence = rebuilt.evidence
    observable = rebuilt.safe_observable
    if not _model_storage_is_closed(evidence, UnboundEvalEvidence):
        return None
    if not _model_storage_is_closed(
        observable,
        UnboundSafeCaseObservable,
    ):
        return None
    if (
        not evidence.trace_events
        or any(event.case_id is not None for event in evidence.trace_events)
        or any(
            event.event_type is TraceEventType.EVAL_CASE_GRADED
            for event in evidence.trace_events
        )
    ):
        return None
    if evidence.observed_outcome is not observable.user_outcome:
        return None
    if ordinary_trace_shape(evidence.trace_events) != (
        observable.ordinary_trace_shape
    ):
        return None
    if len(evidence.context_manifests) != observable.model_calls:
        return None
    if (
        evidence.agent_result is not None
        and evidence.agent_result.outcome is not observable.user_outcome
    ):
        return None
    return rebuilt


def _unbound_result_state_is_closed(
    raw_result: EvalCaseSutResult,
    canonical_result: EvalCaseSutResult,
    *,
    authenticated_identity_values: frozenset[str],
) -> bool:
    return (
        _canonical_singleton_state_is_closed()
        and _payload_tree_is_closed(
            raw_result,
            forbidden_identity_values=authenticated_identity_values,
        )
        and _payload_tree_is_closed(
            canonical_result,
            forbidden_identity_values=authenticated_identity_values,
        )
        and _same_exact_value_tree(raw_result, canonical_result)
        and raw_result == canonical_result
    )


def _canonical_bound_evidence(
    evidence: EvalEvidence,
    *,
    case_id: str,
    authenticated_identity_values: frozenset[str],
) -> EvalEvidence | None:
    allowed_identity_values = {
        "case_id": frozenset({case_id}),
    }
    if (
        not _canonical_singleton_state_is_closed()
        or not _payload_tree_is_closed(
            evidence,
            forbidden_identity_values=authenticated_identity_values,
            allowed_schema_identity_values=allowed_identity_values,
        )
    ):
        return None
    try:
        projection = evidence.model_dump_json(
            round_trip=True,
            warnings="error",
        )
        if type(projection) is not str:
            return None
        rebuilt = EvalEvidence.model_validate_json(
            projection,
            strict=True,
        )
    except Exception:
        return None
    if (
        type(rebuilt) is not EvalEvidence
        or not _canonical_singleton_state_is_closed()
        or not _same_exact_value_tree(evidence, rebuilt)
        or rebuilt != evidence
        or not _payload_tree_is_closed(
            rebuilt,
            forbidden_identity_values=authenticated_identity_values,
            allowed_schema_identity_values=allowed_identity_values,
        )
    ):
        return None
    return rebuilt


def _canonical_model_state_is_closed(
    value: BaseModel,
    expected_type: type[BaseModel],
) -> bool:
    return (
        type(value) is expected_type
        and _payload_tree_is_closed(
            value,
            forbidden_identity_values=frozenset(),
            allow_any_schema_identity_value=True,
            allow_semantic_json_keys=True,
        )
    )


def _detached_canonical_model(
    value: BaseModel,
    expected_type: type[BaseModel],
) -> BaseModel | None:
    if not _canonical_model_state_is_closed(value, expected_type):
        return None
    try:
        projection = value.model_dump_json(
            round_trip=True,
            warnings="error",
        )
        if type(projection) is not str:
            return None
        rebuilt = expected_type.model_validate_json(
            projection,
            strict=True,
        )
    except Exception:
        return None
    if (
        type(rebuilt) is not expected_type
        or not _canonical_model_state_is_closed(
            rebuilt,
            expected_type,
        )
        or not _same_exact_value_tree(value, rebuilt)
        or rebuilt != value
    ):
        return None
    return rebuilt


def _detached_external_model_matching(
    value: object,
    expected: BaseModel,
    expected_type: type[BaseModel],
) -> BaseModel | None:
    if (
        type(value) is not expected_type
        or not _canonical_model_state_is_closed(
            value,
            expected_type,
        )
        or not _canonical_model_state_is_closed(
            expected,
            expected_type,
        )
        or not _same_exact_value_tree(value, expected)
        or value != expected
    ):
        return None
    rebuilt = _detached_canonical_model(
        value,
        expected_type,
    )
    if (
        rebuilt is None
        or not _same_exact_value_tree(rebuilt, expected)
        or rebuilt != expected
    ):
        return None
    return rebuilt


def _bind_authenticated_case(
    result: EvalCaseSutResult,
    *,
    case_id: str,
) -> tuple[EvalEvidence, SafeCaseObservable]:
    unbound_observable = result.safe_observable
    safe_observable = SafeCaseObservable(
        case_id=case_id,
        **{
            field_name: getattr(unbound_observable, field_name)
            for field_name in UnboundSafeCaseObservable.model_fields
        },
    )
    unbound_evidence = result.evidence
    evidence = EvalEvidence(
        case_id=case_id,
        safe_observable=safe_observable,
        **{
            field_name: getattr(unbound_evidence, field_name)
            for field_name in UnboundEvalEvidence.model_fields
        },
    )
    return evidence, safe_observable


class OfflineEvalHarness:
    def __init__(
        self,
        *,
        artifacts: LoadedE2E01Artifacts,
        sut: EvalCaseSut,
        qwen_sut: QwenBaselineSut | None = None,
        trace_callbacks: EvalTraceCallbacks,
        result_port: EvalResultPort,
        clock: Callable[[], datetime],
        grader_runner: GraderRunner | None = None,
        nonce_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if type(artifacts) is not LoadedE2E01Artifacts:
            raise TypeError("artifacts must be an authenticated E2E01 bundle")
        private_artifacts = _detached_canonical_model(
            artifacts,
            LoadedE2E01Artifacts,
        )
        if type(private_artifacts) is not LoadedE2E01Artifacts:
            raise TypeError("artifacts must be an authenticated E2E01 bundle")
        if not callable(clock):
            raise TypeError("clock must be injected")
        if not callable(nonce_factory):
            raise TypeError("nonce_factory must be callable")
        self._artifacts = private_artifacts
        self._sut = sut
        self._qwen_sut = qwen_sut
        self._trace_callbacks = trace_callbacks
        self._result_port = result_port
        self._clock = clock
        self._grader_runner = grader_runner or grade_evidence
        self._nonce_factory = nonce_factory
        self._authenticated_identity_values: frozenset[str] = (
            frozenset(
                case.case_id
                for case in private_artifacts.cases
            )
            | frozenset(
                script.model_script_ref
                for script in private_artifacts.scripts
            )
        )
        self._issued_nonces: set[UUID] = set()
        self._pending_case_by_execution_ref: dict[UUID, str] = {}
        self._retired_execution_refs: set[UUID] = set()
        self._persisted_stage_by_replay_key: dict[
            _ReplayCacheKey,
            _StagedCase,
        ] = {}

    async def run_lane(
        self,
        *,
        eval_run_id: UUID,
        lane: str = "offline_gate",
        attempt: int = 1,
        case_ids: Sequence[str] | None = None,
        script_ref_by_case: Mapping[str, str] | None = None,
    ) -> EvalLaneRunOutcome:
        if not _canonical_singleton_state_is_closed():
            _restore_canonical_singleton_state()
            raise _fresh_command_error()
        outcome: EvalLaneRunOutcome | None = None
        singleton_state_failed = False
        singleton_state_restored = False
        try:
            outcome = await self._run_lane_impl(
                eval_run_id=eval_run_id,
                lane=lane,
                attempt=attempt,
                case_ids=case_ids,
                script_ref_by_case=script_ref_by_case,
            )
            singleton_state_failed = (
                not _canonical_singleton_state_is_closed()
            )
        finally:
            singleton_state_restored = (
                _restore_canonical_singleton_state()
            )
        if (
            singleton_state_failed
            or not singleton_state_restored
            or outcome is None
        ):
            raise _fresh_command_error()
        return outcome

    async def run_qwen_baseline(
        self,
        *,
        eval_run_id: UUID,
        environment: Mapping[str, str],
        attempt: int = 1,
        case_ids: Sequence[str] | None = None,
        transport_factory: (
            Callable[[], httpx.AsyncBaseTransport] | None
        ) = None,
    ) -> EvalLaneRunOutcome:
        if not _canonical_singleton_state_is_closed():
            _restore_canonical_singleton_state()
            raise _fresh_command_error()
        outcome: EvalLaneRunOutcome | None = None
        singleton_state_failed = False
        singleton_state_restored = False
        try:
            outcome = await self._run_qwen_baseline_impl(
                eval_run_id=eval_run_id,
                environment=environment,
                attempt=attempt,
                case_ids=case_ids,
                transport_factory=transport_factory,
            )
            singleton_state_failed = (
                not _canonical_singleton_state_is_closed()
            )
        finally:
            singleton_state_restored = (
                _restore_canonical_singleton_state()
            )
        if (
            singleton_state_failed
            or not singleton_state_restored
            or outcome is None
        ):
            raise _fresh_command_error()
        return outcome

    async def _run_qwen_baseline_impl(
        self,
        *,
        eval_run_id: UUID,
        environment: Mapping[str, str],
        attempt: int,
        case_ids: Sequence[str] | None,
        transport_factory: (
            Callable[[], httpx.AsyncBaseTransport] | None
        ),
    ) -> EvalLaneRunOutcome:
        private_eval_run_id = _detached_closed_uuid(eval_run_id)
        if private_eval_run_id is None:
            raise _fresh_command_error()
        eval_run_id = private_eval_run_id
        try:
            lane_artifact = self._artifacts.lane_by_name(
                "qwen_baseline"
            )
            selected_ids = (
                tuple(lane_artifact.case_refs)
                if case_ids is None
                else tuple(case_ids)
            )
            required_env = tuple(
                lane_artifact.credential_policy.get(
                    "required_env",
                    (),
                )
            )
            private_environment = dict(environment)
            pair_ids = {"E2E01-04-A", "E2E01-04-B"}
            selected_pair = set(selected_ids) & pair_ids
            if (
                type(attempt) is not int
                or attempt < 1
                or not selected_ids
                or len(selected_ids) != len(set(selected_ids))
                or not all(
                    type(case_id) is str and case_id
                    for case_id in selected_ids
                )
                or not set(selected_ids) <= set(lane_artifact.case_refs)
                or selected_pair not in (set(), pair_ids)
                or not all(
                    type(name) is str and name
                    for name in required_env
                )
                or not all(
                    type(name) is str
                    and type(value) is str
                    and name in required_env
                    for name, value in private_environment.items()
                )
                or (
                    transport_factory is not None
                    and not callable(transport_factory)
                )
            ):
                raise ValueError("Qwen baseline input is invalid")
        except Exception:
            raise _fresh_command_error()

        preflights = tuple(
            build_qwen_baseline_preflight(
                artifacts=self._artifacts,
                eval_run_id=eval_run_id,
                case_id=case_id,
                attempt=attempt,
                environment=private_environment,
                real_sut=self._qwen_sut,
                completed_at=self._clock(),
            )
            for case_id in selected_ids
        )
        if not all(preflight.ready for preflight in preflights):
            if (
                any(preflight.ready for preflight in preflights)
                or len(
                    {
                        preflight.reason
                        for preflight in preflights
                    }
                )
                != 1
            ):
                raise _fresh_command_error()
            records: list[EvalResultRecord] = []
            for preflight in preflights:
                if preflight.not_run_record is None:
                    raise _fresh_command_error()
                records.append(
                    await append_qwen_not_run_record(
                        result_port=self._result_port,
                        record=preflight.not_run_record,
                    )
                )
            return EvalLaneRunOutcome(
                lane="qwen_baseline",
                results=tuple(records),
                execution_failures=(),
                command_passed=False,
            )

        qwen_sut = self._qwen_sut
        api_key = private_environment.get("DASHSCOPE_API_KEY")
        base_url = private_environment.get("DASHSCOPE_BASE_URL")
        if (
            qwen_sut is None
            or type(api_key) is not str
            or not api_key
            or api_key != api_key.strip()
            or type(base_url) is not str
            or not base_url
            or base_url != base_url.strip()
        ):
            raise _fresh_command_error()
        return await self._run_lane_impl(
            eval_run_id=eval_run_id,
            lane="qwen_baseline",
            attempt=attempt,
            case_ids=selected_ids,
            script_ref_by_case=None,
            qwen_execution=_QwenBaselineExecution(
                sut=qwen_sut,
                base_url=base_url,
                api_key=api_key,
                transport_factory=transport_factory,
            ),
        )

    async def _run_lane_impl(
        self,
        *,
        eval_run_id: UUID,
        lane: str = "offline_gate",
        attempt: int = 1,
        case_ids: Sequence[str] | None = None,
        script_ref_by_case: Mapping[str, str] | None = None,
        qwen_execution: _QwenBaselineExecution | None = None,
    ) -> EvalLaneRunOutcome:
        private_eval_run_id = _detached_closed_uuid(eval_run_id)
        if private_eval_run_id is None:
            raise _fresh_command_error()
        eval_run_id = private_eval_run_id
        failures: list[EvalExecutionFailureRecord] = []
        setup_failed = False
        lane_artifact: EvalLaneArtifact | None = None
        try:
            if (
                type(lane) is not str
                or lane
                != (
                    "qwen_baseline"
                    if qwen_execution is not None
                    else "offline_gate"
                )
                or type(attempt) is not int
                or attempt < 1
            ):
                raise ArtifactContractError("offline Harness lane is invalid")
            lane_artifact = self._artifacts.lane_by_name(lane)
        except Exception:
            setup_failed = True
        if setup_failed or lane_artifact is None:
            safe_lane = (
                lane
                if type(lane) is str and lane
                else "INVALID_LANE"
            )
            failure = await self._append_failure(
                eval_run_id=eval_run_id,
                lane=safe_lane,
                phase=EvalExecutionFailurePhase.HARNESS_SETUP,
                case=None,
                attempt=None,
                trace_ref=None,
                lane_artifact=None,
            )
            return EvalLaneRunOutcome(
                lane=safe_lane,
                results=(),
                execution_failures=(failure,),
                command_passed=False,
            )

        selection_failed = False
        try:
            selected_ids = (
                tuple(lane_artifact.case_refs) if case_ids is None else tuple(case_ids)
            )
            script_selection = dict(script_ref_by_case or {})
        except Exception:
            selection_failed = True
            selected_ids = ()
            script_selection = {}
        if (
            selection_failed
            or not selected_ids
            or not all(
                type(case_id) is str and case_id
                for case_id in selected_ids
            )
            or any(
                type(case_id) is not str
                or type(script_ref) is not str
                for case_id, script_ref in script_selection.items()
            )
            or len(selected_ids) != len(set(selected_ids))
            or not set(selected_ids) <= set(lane_artifact.case_refs)
        ):
            failure = await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane,
                phase=EvalExecutionFailurePhase.HARNESS_SETUP,
                case=None,
                attempt=None,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
            return EvalLaneRunOutcome(
                lane=lane,
                results=(),
                execution_failures=(failure,),
                command_passed=False,
            )
        if not set(script_selection) <= set(selected_ids):
            failure = await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane,
                phase=EvalExecutionFailurePhase.HARNESS_SETUP,
                case=None,
                attempt=None,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
            return EvalLaneRunOutcome(
                lane=lane,
                results=(),
                execution_failures=(failure,),
                command_passed=False,
            )

        pair_ids = {"E2E01-04-A", "E2E01-04-B"}
        selected_pair = set(selected_ids) & pair_ids
        if selected_pair and selected_pair != pair_ids:
            for case_id in selected_ids:
                if case_id not in selected_pair:
                    continue
                case = self._artifacts.case_by_id(case_id)
                failures.append(
                    await self._append_failure(
                        eval_run_id=eval_run_id,
                        lane=lane,
                        phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                        case=case,
                        attempt=attempt,
                        trace_ref=None,
                        lane_artifact=lane_artifact,
                    )
                )
            return EvalLaneRunOutcome(
                lane=lane,
                results=(),
                execution_failures=tuple(failures),
                command_passed=False,
            )

        staged: dict[str, _StagedCase] = {}
        replay_key_by_case: dict[str, _ReplayCacheKey] = {}
        for case_id in selected_ids:
            case = self._artifacts.case_by_id(case_id)
            replay_key: _ReplayCacheKey | None = None
            try:
                normalized_script_ref = _normalized_selected_script_ref(
                    case,
                    script_selection.get(case_id),
                )
                replay_key = (
                    eval_run_id,
                    case_id,
                    lane_artifact.lane,
                    attempt,
                    normalized_script_ref,
                )
                replay_key_by_case[case_id] = replay_key
            except Exception:
                pass
            cached_stage = (
                self._persisted_stage_by_replay_key.get(replay_key)
                if replay_key is not None
                else None
            )
            if cached_stage is not None:
                staged[case_id] = cached_stage
                continue
            stage, failure = await self._stage_case(
                eval_run_id=eval_run_id,
                lane_artifact=lane_artifact,
                attempt=attempt,
                case=case,
                selected_script_ref=script_selection.get(case_id),
                qwen_execution=qwen_execution,
            )
            if failure is not None:
                failures.append(failure)
            elif stage is not None:
                staged[case_id] = stage

        if selected_pair == pair_ids:
            staged_pair = set(staged) & pair_ids
            if staged_pair != pair_ids:
                for case_id in staged_pair:
                    stage = staged.pop(case_id)
                    failures.append(
                        await self._append_failure(
                            eval_run_id=eval_run_id,
                            lane=lane,
                            phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                            case=stage.case,
                            attempt=attempt,
                            trace_ref=stage.result.trace_ref,
                            lane_artifact=lane_artifact,
                        )
                    )
            else:
                pair = {
                    case_id: staged[case_id].safe_observable for case_id in pair_ids
                }
                if not e2e01_04_safe_observables_match(pair):
                    for case_id in pair_ids:
                        current = staged[case_id]
                        staged[case_id] = _StagedCase(
                            case=current.case,
                            expectations=current.expectations,
                            result=_force_disclosure_failure(
                                current.result,
                                current.expectations,
                            ),
                            safe_observable=current.safe_observable,
                        )

        persisted: list[EvalResultRecord] = []
        for case_id in selected_ids:
            stage = staged.get(case_id)
            if stage is None:
                continue
            persisted_record, failure = await self._append_result(
                stage.result,
                case=stage.case,
                lane_artifact=lane_artifact,
            )
            if failure is not None:
                failures.append(failure)
            elif persisted_record is not None:
                public_record = _detached_canonical_model(
                    persisted_record,
                    EvalResultRecord,
                )
                cache_record = _detached_canonical_model(
                    persisted_record,
                    EvalResultRecord,
                )
                cache_expectations = _detached_canonical_model(
                    stage.expectations,
                    EvalCaseExpectations,
                )
                cache_observable = _detached_canonical_model(
                    stage.safe_observable,
                    SafeCaseObservable,
                )
                replay_key = replay_key_by_case.get(case_id)
                if (
                    type(public_record) is EvalResultRecord
                    and type(cache_record) is EvalResultRecord
                    and type(cache_expectations)
                    is EvalCaseExpectations
                    and type(cache_observable)
                    is SafeCaseObservable
                ):
                    persisted.append(public_record)
                else:
                    failures.append(
                        await self._append_failure(
                            eval_run_id=eval_run_id,
                            lane=lane,
                            phase=(
                                EvalExecutionFailurePhase.RESULT_PERSISTENCE
                            ),
                            case=stage.case,
                            attempt=attempt,
                            trace_ref=persisted_record.trace_ref,
                            lane_artifact=lane_artifact,
                        )
                    )
                    continue
                if replay_key is not None:
                    self._persisted_stage_by_replay_key[replay_key] = (
                        _StagedCase(
                            case=stage.case,
                            expectations=cache_expectations,
                            result=cache_record,
                            safe_observable=cache_observable,
                        )
                    )

        command_passed = (
            not failures
            and len(persisted) == len(selected_ids)
            and all(result.status is EvalResultStatus.PASS for result in persisted)
        )
        return EvalLaneRunOutcome(
            lane=lane,
            results=tuple(persisted),
            execution_failures=tuple(failures),
            command_passed=command_passed,
        )

    def _issue_nonce_pair(self) -> tuple[UUID, UUID] | None:
        try:
            raw_values = (
                self._nonce_factory(),
                self._nonce_factory(),
            )
            if any(
                type(value) is not UUID
                or not _uuid_is_closed(value)
                for value in raw_values
            ):
                return None
            generated = tuple(
                UUID(
                    int=object.__getattribute__(value, "int"),
                    is_safe=object.__getattribute__(
                        value,
                        "is_safe",
                    ),
                )
                for value in raw_values
            )
            if (
                any(value.version != 4 for value in generated)
                or len(set(generated)) != 2
                or any(
                    value in self._issued_nonces
                    for value in generated
                )
            ):
                self._issued_nonces.update(generated)
                return None
            self._issued_nonces.update(generated)
            return generated[0], generated[1]
        except Exception:
            return None

    def _execution_input(
        self,
        case: EvalCaseArtifact,
        *,
        execution_ref: UUID,
    ) -> EvalCaseExecutionInput:
        fixture_ref = case.input.get("trusted_context_fixture_ref")
        if not isinstance(fixture_ref, str) or not fixture_ref:
            raise ArtifactContractError(
                "Case trusted context fixture reference is invalid"
            )
        return EvalCaseExecutionInput(
            execution_ref=execution_ref,
            messages=(
                EvalExecutionMessage(
                    role="user",
                    content=_trusted_message_content_for_case(case),
                ),
            ),
            trusted_context_fixture_ref=fixture_ref,
        )

    def _retire_execution_ref(self, execution_ref: UUID) -> None:
        self._pending_case_by_execution_ref.pop(execution_ref, None)
        self._retired_execution_refs.add(execution_ref)

    async def _stage_case(
        self,
        *,
        eval_run_id: UUID,
        lane_artifact: EvalLaneArtifact,
        attempt: int,
        case: EvalCaseArtifact,
        selected_script_ref: str | None,
        qwen_execution: _QwenBaselineExecution | None,
    ) -> tuple[_StagedCase | None, EvalExecutionFailureRecord | None]:
        case_setup_failed = False
        expectations: EvalCaseExpectations | None = None
        script: ModelScriptArtifact | None = None
        try:
            selected_script_ref = _normalized_selected_script_ref(
                case,
                selected_script_ref,
            )
            script = self._artifacts.script_by_ref(selected_script_ref)
            expectations = build_authenticated_case_expectations(
                artifacts=self._artifacts,
                case=case,
                script=script,
            )
        except Exception:
            case_setup_failed = True
        if case_setup_failed or script is None or expectations is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.CASE_SETUP,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )

        nonce_pair = self._issue_nonce_pair()
        if nonce_pair is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
        execution_ref, script_execution_ref = nonce_pair
        provider: ScriptedModelProviderV2 | None = None
        runtime_fault: RuntimeFaultDirective | None = None
        execution_input: EvalCaseExecutionInput | None = None
        try:
            sut_execution_ref = _detached_closed_uuid(
                execution_ref
            )
            provider_execution_ref = _detached_closed_uuid(
                script_execution_ref
            )
            if (
                sut_execution_ref is None
                or provider_execution_ref is None
            ):
                raise ValueError("closed nonce clone failed")
            execution_input = self._execution_input(
                case,
                execution_ref=sut_execution_ref,
            )
            if qwen_execution is None:
                provider = ScriptedModelProviderV2(
                    script,
                    script_execution_ref=provider_execution_ref,
                )
                runtime_fault = provider.take_runtime_fault_directive()
        except Exception:
            case_setup_failed = True
        if (
            case_setup_failed
            or execution_input is None
            or (qwen_execution is None and provider is None)
        ):
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.CASE_SETUP,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )

        self._pending_case_by_execution_ref[execution_ref] = case.case_id
        authenticated_pending_case: str | None = None
        sut_failed = False
        sut_result: EvalCaseSutResult | None = None
        try:
            try:
                if qwen_execution is None:
                    assert provider is not None
                    sut_result = await self._sut.execute_case(
                        execution_input=execution_input,
                        scripted_provider=provider,
                        runtime_fault=runtime_fault,
                    )
                else:
                    transport = (
                        None
                        if qwen_execution.transport_factory is None
                        else qwen_execution.transport_factory()
                    )
                    if (
                        transport is not None
                        and not isinstance(
                            transport,
                            httpx.AsyncBaseTransport,
                        )
                    ):
                        raise TypeError(
                            "Qwen transport must be an async transport"
                        )
                    async with httpx.AsyncClient(
                        transport=transport,
                    ) as client:
                        qwen_provider = QwenResponsesAdapterV2(
                            base_url=qwen_execution.base_url,
                            api_key=qwen_execution.api_key,
                            client=client,
                        )
                        sut_result = (
                            await qwen_execution.sut.execute_qwen_case(
                                execution_input=execution_input,
                                qwen_provider=qwen_provider,
                            )
                        )
            except Exception:
                sut_failed = True
            authenticated_pending_case = (
                self._pending_case_by_execution_ref.get(execution_ref)
            )
        finally:
            self._retire_execution_ref(execution_ref)
        if sut_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.SYSTEM_UNDER_TEST,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )

        canonical_result: EvalCaseSutResult | None = None
        if type(sut_result) is EvalCaseSutResult:
            try:
                candidate = _canonical_unbound_result(
                    sut_result,
                    authenticated_identity_values=(
                        self._authenticated_identity_values
                    ),
                )
                if (
                    candidate is not None
                    and candidate.execution_ref == execution_ref
                    and authenticated_pending_case == case.case_id
                ):
                    canonical_result = candidate
            except Exception:
                canonical_result = None
        if canonical_result is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )

        evidence: EvalEvidence | None = None
        safe_observable: SafeCaseObservable | None = None
        try:
            evidence, safe_observable = _bind_authenticated_case(
                canonical_result,
                case_id=case.case_id,
            )
            evidence = _canonical_bound_evidence(
                evidence,
                case_id=case.case_id,
                authenticated_identity_values=(
                    self._authenticated_identity_values
                ),
            )
            if evidence is not None:
                safe_observable = evidence.safe_observable
        except Exception:
            pass
        if evidence is None or safe_observable is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=None,
                lane_artifact=lane_artifact,
            )
        provider_exhaustion_failed = False
        try:
            if qwen_execution is None:
                assert provider is not None
                provider.assert_exhausted()
        except Exception:
            provider_exhaustion_failed = True
        if provider_exhaustion_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.SYSTEM_UNDER_TEST,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        configured_names = tuple(case.grading.get("graders", ()))
        if configured_names.count("TraceCompletenessGrader") != 1:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.GRADING,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )
        non_trace_names = tuple(
            name for name in configured_names if name != "TraceCompletenessGrader"
        )
        if not _unbound_result_state_is_closed(
            sut_result,
            canonical_result,
            authenticated_identity_values=(
                self._authenticated_identity_values
            ),
        ):
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )
        grading_failed = False
        initial_grading: GradingOutcome | None = None
        try:
            initial_grading = _run_verified_grading(
                self._grader_runner,
                non_trace_names,
                evidence,
                expectations,
                authenticated_identity_values=(
                    self._authenticated_identity_values
                ),
            )
        except Exception:
            grading_failed = True
        if grading_failed or initial_grading is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.GRADING,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        graded_event = TraceEvent(
            trace_event_id=uuid5(
                NAMESPACE_URL,
                (
                    f"eval-case-graded:{eval_run_id}:{case.case_id}:"
                    f"{lane_artifact.lane}:{attempt}"
                ),
            ),
            event_type=TraceEventType.EVAL_CASE_GRADED,
            occurred_at=max(event.occurred_at for event in evidence.trace_events)
            + timedelta(microseconds=1),
            run_id=evidence.trace_events[0].run_id,
            case_id=case.case_id,
        )
        append_failed = False
        callback_graded_event = _detached_canonical_model(
            graded_event,
            TraceEvent,
        )
        if type(callback_graded_event) is not TraceEvent:
            append_failed = True
        else:
            try:
                await self._trace_callbacks.append_eval_case_graded(
                    callback_graded_event
                )
            except Exception:
                append_failed = True
        if append_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.TRACE_PERSISTENCE,
                safe_error_code=(EvalExecutionSafeErrorCode.TRACE_PERSISTENCE_FAILED),
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        expected_final_evidence: EvalEvidence | None = None
        callback_event_is_closed = (
            _detached_external_model_matching(
                callback_graded_event,
                graded_event,
                TraceEvent,
            )
            is not None
        )
        if (
            callback_event_is_closed
            and _unbound_result_state_is_closed(
                sut_result,
                canonical_result,
                authenticated_identity_values=(
                    self._authenticated_identity_values
                ),
            )
        ):
            try:
                expected_final_evidence = _canonical_bound_evidence(
                    evidence.model_copy(
                        update={
                            "trace_events": (
                                *evidence.trace_events,
                                graded_event,
                            )
                        }
                    ),
                    case_id=case.case_id,
                    authenticated_identity_values=(
                        self._authenticated_identity_values
                    ),
                )
            except Exception:
                expected_final_evidence = None
        if expected_final_evidence is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )
        expected_graded_event = (
            expected_final_evidence.trace_events[-1]
        )

        reload_failed = False
        final_trace: tuple[TraceEvent, ...] | None = None
        try:
            callback_trace_ref = _detached_closed_uuid(
                evidence.trace_ref
            )
            if callback_trace_ref is None:
                raise ValueError("closed Trace ref clone failed")
            final_trace = await self._trace_callbacks.reload_trace(
                callback_trace_ref
            )
        except Exception:
            reload_failed = True
        if reload_failed:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.TRACE_PERSISTENCE,
                safe_error_code=EvalExecutionSafeErrorCode.TRACE_STORE_UNAVAILABLE,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )
        final_evidence: EvalEvidence | None = None
        if (
            type(final_trace) is tuple
            and callback_trace_ref is not None
            and _uuid_is_closed(callback_trace_ref)
            and callback_trace_ref == evidence.trace_ref
            and _unbound_result_state_is_closed(
                sut_result,
                canonical_result,
                authenticated_identity_values=(
                    self._authenticated_identity_values
                ),
            )
        ):
            try:
                final_evidence = _canonical_bound_evidence(
                    evidence.model_copy(
                        update={"trace_events": final_trace}
                    ),
                    case_id=case.case_id,
                    authenticated_identity_values=(
                        self._authenticated_identity_values
                    ),
                )
            except Exception:
                final_evidence = None
        if final_evidence is not None:
            canonical_final_trace = final_evidence.trace_events
            graded_events = tuple(
                event
                for event in canonical_final_trace
                if event.event_type is TraceEventType.EVAL_CASE_GRADED
            )
            valid_identity_positions = all(
                (
                    event.case_id == case.case_id
                    if event.event_type is TraceEventType.EVAL_CASE_GRADED
                    else event.case_id is None
                )
                for event in canonical_final_trace
            )
            if (
                graded_events != (expected_graded_event,)
                or not valid_identity_positions
            ):
                final_evidence = None
        if final_evidence is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.RESULT_COMPLETENESS,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        final_trace = final_evidence.trace_events
        final_grading_failed = False
        final_grading: GradingOutcome | None = None
        try:
            final_grading = _run_verified_grading(
                self._grader_runner,
                ("TraceCompletenessGrader",),
                final_evidence,
                expectations,
                authenticated_identity_values=(
                    self._authenticated_identity_values
                ),
            )
        except Exception:
            final_grading_failed = True
        if final_grading_failed or final_grading is None:
            return None, await self._append_failure(
                eval_run_id=eval_run_id,
                lane=lane_artifact.lane,
                phase=EvalExecutionFailurePhase.GRADING,
                case=case,
                attempt=attempt,
                trace_ref=evidence.trace_ref,
                lane_artifact=lane_artifact,
            )

        result_by_name = {
            result.grader_name: result
            for result in (
                *initial_grading.grader_results,
                *final_grading.grader_results,
            )
        }
        grader_results = tuple(result_by_name[name] for name in configured_names)
        combined_grading = derive_grading_outcome(
            grader_results,
            expectations,
        )
        result = EvalResultRecord(
            schema_version="eval_result_record.p0.v1",
            eval_run_id=eval_run_id,
            case_id=case.case_id,
            lane=lane_artifact.lane,
            attempt=attempt,
            status=combined_grading.status,
            grader_results=combined_grading.grader_results,
            critical_failures=combined_grading.critical_failures,
            observed_outcome=final_evidence.observed_outcome,
            trace_ref=final_evidence.trace_ref,
            version_manifest=self._version_manifest(case, lane_artifact),
            latency_summary=None,
            usage_summary=None,
            completed_at=max(event.occurred_at for event in final_trace),
        )
        final_safe_observable = SafeCaseObservable(
            case_id=case.case_id,
            http_status=safe_observable.http_status,
            user_outcome=safe_observable.user_outcome,
            response_policy=safe_observable.response_policy,
            ordinary_trace_shape=ordinary_trace_shape(final_trace),
            model_calls=safe_observable.model_calls,
        )
        return (
            _StagedCase(
                case=case,
                expectations=expectations,
                result=result,
                safe_observable=final_safe_observable,
            ),
            None,
        )

    async def _append_result(
        self,
        record: EvalResultRecord,
        *,
        case: EvalCaseArtifact,
        lane_artifact: EvalLaneArtifact,
    ) -> tuple[EvalResultRecord | None, EvalExecutionFailureRecord | None]:
        append_failed = False
        write_result: InsertOnlyWriteResult | None = None
        port_record = _detached_canonical_model(
            record,
            EvalResultRecord,
        )
        if type(port_record) is not EvalResultRecord:
            append_failed = True
        else:
            try:
                write_result = await self._result_port.append_eval_result(
                    port_record
                )
            except Exception:
                append_failed = True
            if (
                not append_failed
                and _detached_external_model_matching(
                    port_record,
                    record,
                    EvalResultRecord,
                )
                is None
            ):
                append_failed = True
            if not _canonical_singleton_state_is_closed():
                _restore_canonical_singleton_state()
                append_failed = True
        if not append_failed and write_result is InsertOnlyWriteResult.INSERTED:
            return record, None
        if not append_failed and write_result is InsertOnlyWriteResult.ALREADY_EXISTS:
            load_failed = False
            existing: object = None
            try:
                load_eval_run_id = _detached_closed_uuid(
                    record.eval_run_id
                )
                if load_eval_run_id is None:
                    raise ValueError("closed Eval run clone failed")
                existing = await self._result_port.load_eval_result(
                    eval_run_id=load_eval_run_id,
                    case_id=record.case_id,
                    lane=record.lane,
                    attempt=record.attempt,
                )
            except Exception:
                load_failed = True
            if not _canonical_singleton_state_is_closed():
                _restore_canonical_singleton_state()
                load_failed = True
            if (
                not load_failed
                and _detached_external_model_matching(
                    existing,
                    record,
                    EvalResultRecord,
                )
                is not None
            ):
                return record, None
        failure = await self._append_failure(
            eval_run_id=record.eval_run_id,
            lane=record.lane,
            phase=EvalExecutionFailurePhase.RESULT_PERSISTENCE,
            case=case,
            attempt=record.attempt,
            trace_ref=record.trace_ref,
            lane_artifact=lane_artifact,
        )
        return None, failure

    async def _append_failure(
        self,
        *,
        eval_run_id: UUID,
        lane: str,
        phase: EvalExecutionFailurePhase,
        case: EvalCaseArtifact | None,
        attempt: int | None,
        trace_ref: UUID | None,
        lane_artifact: EvalLaneArtifact | None,
        safe_error_code: EvalExecutionSafeErrorCode | None = None,
    ) -> EvalExecutionFailureRecord:
        if (
            not _canonical_singleton_state_is_closed()
            and not _restore_canonical_singleton_state()
        ):
            raise _fresh_command_error()
        try:
            occurred_at = _detached_closed_datetime(
                self._clock()
            )
        except Exception:
            occurred_at = None
        if (
            occurred_at is None
            or not _canonical_singleton_state_is_closed()
        ):
            raise _fresh_command_error()
        code = safe_error_code or _FAILURE_CODE_BY_PHASE[phase]
        failure = EvalExecutionFailureRecord(
            schema_version="eval_execution_failure_record.p0.v1",
            eval_run_id=eval_run_id,
            case_id=case.case_id if case is not None else None,
            lane=lane,
            attempt=attempt if case is not None else None,
            failure_phase=phase,
            safe_error_code=code,
            diagnostic_ref=None,
            trace_ref=trace_ref,
            version_manifest=self._version_manifest(case, lane_artifact),
            occurred_at=occurred_at,
        )
        append_failed = False
        port_failure = _detached_canonical_model(
            failure,
            EvalExecutionFailureRecord,
        )
        if type(port_failure) is not EvalExecutionFailureRecord:
            append_failed = True
        else:
            try:
                await self._result_port.append_eval_execution_failure(
                    port_failure
                )
            except Exception:
                append_failed = True
            if (
                not append_failed
                and _detached_external_model_matching(
                    port_failure,
                    failure,
                    EvalExecutionFailureRecord,
                )
                is None
            ):
                append_failed = True
            if (
                not _canonical_singleton_state_is_closed()
            ):
                _restore_canonical_singleton_state()
                append_failed = True
        if append_failed:
            raise _fresh_command_error()
        return failure

    def _version_manifest(
        self,
        case: EvalCaseArtifact | None,
        lane: EvalLaneArtifact | None,
    ) -> EvalVersionManifest:
        manifest_versions = self._artifacts.manifest["versions"]
        case_versions = case.version_manifest if case is not None else {}
        fixture_versions = tuple(
            case_versions.get(
                "fixture_versions",
                (manifest_versions["fixture_version"],),
            )
        )
        return EvalVersionManifest(
            dataset_version=case_versions.get(
                "dataset_version",
                manifest_versions["dataset_version"],
            ),
            candidate_version=self._artifacts.candidate_version,
            baseline_version=None,
            fixture_versions=fixture_versions,
            model_config_version=(
                lane.model_config_version if lane is not None else None
            ),
            prompt_version=case_versions.get(
                "prompt_version",
                manifest_versions["prompt_version"],
            ),
            tool_registry_version=case_versions.get(
                "tool_registry_version",
                manifest_versions["tool_registry_version"],
            ),
            corpus_version=None,
            runtime_version=self._artifacts.runtime_version,
        )


def build_qwen_baseline_preflight(
    *,
    artifacts: LoadedE2E01Artifacts,
    eval_run_id: UUID,
    case_id: str,
    attempt: int,
    environment: Mapping[str, str],
    real_sut: QwenBaselineSut | None,
    completed_at: datetime,
) -> QwenBaselinePreflight:
    if type(artifacts) is not LoadedE2E01Artifacts:
        raise TypeError("artifacts must be an authenticated E2E01 bundle")
    lane = artifacts.lane_by_name("qwen_baseline")
    if case_id not in lane.case_refs or type(attempt) is not int or attempt < 1:
        raise ArtifactContractError("Qwen preflight Case identity is invalid")
    required_env = tuple(lane.credential_policy.get("required_env", ()))
    missing_env = any(
        not isinstance(environment.get(name), str)
        or not environment.get(name, "").strip()
        for name in required_env
    )
    if not missing_env and real_sut is not None:
        return QwenBaselinePreflight(ready=True)
    reason = "MISSING_REQUIRED_ENV" if missing_env else "REAL_EVAL_CASE_SUT_NOT_WIRED"
    case = artifacts.case_by_id(case_id)
    record = EvalResultRecord(
        schema_version="eval_result_record.p0.v1",
        eval_run_id=eval_run_id,
        case_id=case_id,
        lane="qwen_baseline",
        attempt=attempt,
        status=EvalResultStatus.NOT_RUN,
        grader_results=(),
        critical_failures=(),
        observed_outcome=None,
        trace_ref=None,
        version_manifest=EvalVersionManifest(
            dataset_version=case.version_manifest["dataset_version"],
            candidate_version=artifacts.candidate_version,
            baseline_version=None,
            fixture_versions=tuple(case.version_manifest["fixture_versions"]),
            model_config_version=lane.model_config_version,
            prompt_version=case.version_manifest.get("prompt_version"),
            tool_registry_version=case.version_manifest.get("tool_registry_version"),
            corpus_version=None,
            runtime_version=artifacts.runtime_version,
        ),
        latency_summary=None,
        usage_summary=None,
        completed_at=completed_at,
    )
    return QwenBaselinePreflight(
        ready=False,
        not_run_record=record,
        reason=reason,
    )


async def append_qwen_not_run_record(
    *,
    result_port: EvalResultPort,
    record: EvalResultRecord,
) -> EvalResultRecord:
    if (
        type(record) is not EvalResultRecord
        or record.lane != "qwen_baseline"
        or record.status is not EvalResultStatus.NOT_RUN
    ):
        raise _fresh_command_error()
    failed = False
    write_result: InsertOnlyWriteResult | None = None
    try:
        write_result = await result_port.append_eval_result(record)
    except Exception:
        failed = True
    if not failed and write_result is InsertOnlyWriteResult.INSERTED:
        return record
    if not failed and write_result is InsertOnlyWriteResult.ALREADY_EXISTS:
        load_failed = False
        existing: EvalResultRecord | None = None
        try:
            existing = await result_port.load_eval_result(
                eval_run_id=record.eval_run_id,
                case_id=record.case_id,
                lane=record.lane,
                attempt=record.attempt,
            )
        except Exception:
            load_failed = True
        if not load_failed and existing == record:
            return existing
    raise _fresh_command_error()


def _validate_grading_output(
    outcome: object,
    configured_names: Sequence[str],
    expectations: EvalCaseExpectations,
) -> None:
    if type(outcome) is not GradingOutcome:
        raise GradingConfigurationError("grader output is incomplete")
    if (
        type(outcome.status) is not EvalResultStatus
        or type(outcome.grader_results) is not tuple
        or type(outcome.critical_failures) is not tuple
        or any(
            type(result) is not EvalGraderResult
            or type(result.grader_name) is not str
            or not result.grader_name
            or type(result.status) is not EvalGraderStatus
            or (
                result.reason_code is not None
                and type(result.reason_code) is not EvalGraderReasonCode
            )
            or (
                (result.status is EvalGraderStatus.FAIL)
                != (result.reason_code is not None)
            )
            for result in outcome.grader_results
        )
        or any(
            type(failure) is not CriticalFailureCode
            for failure in outcome.critical_failures
        )
    ):
        raise GradingConfigurationError("grader output is incomplete")
    if tuple(result.grader_name for result in outcome.grader_results) != tuple(
        configured_names
    ):
        raise GradingConfigurationError("grader output is incomplete")
    expected = derive_grading_outcome(
        outcome.grader_results,
        expectations,
    )
    if outcome != expected:
        raise GradingConfigurationError(
            "grader output does not match authenticated derivation"
        )


def _run_verified_grading(
    grader_runner: GraderRunner,
    configured_names: Sequence[str],
    evidence: EvalEvidence,
    expectations: EvalCaseExpectations,
    *,
    authenticated_identity_values: frozenset[str],
) -> GradingOutcome:
    canonical = grade_evidence(
        configured_names,
        evidence,
        expectations,
    )
    runner_evidence = _canonical_bound_evidence(
        evidence,
        case_id=evidence.case_id,
        authenticated_identity_values=authenticated_identity_values,
    )
    runner_expectations = _detached_canonical_model(
        expectations,
        EvalCaseExpectations,
    )
    if (
        runner_evidence is None
        or type(runner_expectations) is not EvalCaseExpectations
    ):
        raise GradingConfigurationError("grader input is incomplete")
    reported_raw = grader_runner(
        configured_names,
        runner_evidence,
        runner_expectations,
    )
    reported = (
        _detached_canonical_model(
            reported_raw,
            GradingOutcome,
        )
        if type(reported_raw) is GradingOutcome
        else None
    )
    if (
        type(reported) is not GradingOutcome
        or not _canonical_singleton_state_is_closed()
        or not _payload_tree_is_closed(
            evidence,
            forbidden_identity_values=authenticated_identity_values,
            allowed_schema_identity_values={
                "case_id": frozenset({evidence.case_id}),
            },
        )
        or not _canonical_model_state_is_closed(
            expectations,
            EvalCaseExpectations,
        )
    ):
        raise GradingConfigurationError("grader output is incomplete")
    _validate_grading_output(
        reported,
        configured_names,
        expectations,
    )
    if reported != canonical:
        raise GradingConfigurationError(
            "grader runner output does not match canonical grading"
        )
    return canonical


def _replace_trace(
    evidence: EvalEvidence,
    trace_events: tuple[TraceEvent, ...],
) -> EvalEvidence:
    values = {
        field_name: getattr(evidence, field_name)
        for field_name in EvalEvidence.model_fields
    }
    values["trace_events"] = trace_events
    return EvalEvidence(**values)


def _force_disclosure_failure(
    record: EvalResultRecord,
    expectations: EvalCaseExpectations,
) -> EvalResultRecord:
    replacement = EvalGraderResult(
        grader_name="DisclosureGrader",
        status=EvalGraderStatus.FAIL,
        reason_code=EvalGraderReasonCode.ASSERTION_FAILED,
    )
    grader_results = tuple(
        replacement if result.grader_name == "DisclosureGrader" else result
        for result in record.grader_results
    )
    if not any(
        result.grader_name == "DisclosureGrader" for result in record.grader_results
    ):
        raise GradingConfigurationError("E2E01-04 requires DisclosureGrader")
    derived = derive_grading_outcome(grader_results, expectations)
    return EvalResultRecord(
        schema_version=record.schema_version,
        eval_run_id=record.eval_run_id,
        case_id=record.case_id,
        lane=record.lane,
        attempt=record.attempt,
        status=derived.status,
        grader_results=derived.grader_results,
        critical_failures=derived.critical_failures,
        observed_outcome=record.observed_outcome,
        trace_ref=record.trace_ref,
        version_manifest=record.version_manifest,
        latency_summary=record.latency_summary,
        usage_summary=record.usage_summary,
        completed_at=record.completed_at,
    )
