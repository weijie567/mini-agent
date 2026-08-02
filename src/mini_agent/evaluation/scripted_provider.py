"""Deterministic, execution-only ModelProvider used by the offline Eval lane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from mini_agent.application.records import (
    Cycle2ControlPurpose,
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
)
from mini_agent.core.common import FrozenJsonDict, freeze_json_value
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    Cycle2ControlCandidate,
    Cycle2ControlCandidateKind,
    Cycle2InitialRequestUnderstandingOutputV2,
    Cycle2InitialTaskDeltaCandidateV2,
    Cycle2InputCandidate,
    InputAuthority,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    QueryContextualizationCandidateV2,
    ReferenceSourceKindV2,
    RequestUnderstandingInput,
    RequestUnderstandingOutputV2,
    TaskDeltaOperation,
)
from mini_agent.evaluation.artifacts import (
    ArtifactContractError,
    ModelScriptArtifact,
)


@dataclass(frozen=True, slots=True)
class RuntimeFaultDirective:
    behavior: Literal["ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"]
    boundary: Literal["AFTER_REVALIDATION_BEFORE_GATE"]


@dataclass(frozen=True, slots=True)
class Cycle2ScriptDirective:
    """A model candidate or fault directive, never SUT evidence or a result."""

    purpose: Literal[
        "REQUEST_UNDERSTANDING",
        "CONTROL_CANDIDATE",
        "FAULT_DIRECTIVE",
    ]
    behavior: str
    candidate_arguments: FrozenJsonDict
    fault_ref: str | None


@dataclass(frozen=True, slots=True)
class _OrderLookupStep:
    behavior: Literal[
        "VALID_ORDER_LOOKUP",
        "INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION",
    ]
    message_order_number: str
    next_move_order_number: str


@dataclass(frozen=True, slots=True)
class _RequestProtocolFaultStep:
    behavior: Literal[
        "INJECT_ZERO_TARGET_FUNCTION_CALLS",
        "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
    ]


@dataclass(frozen=True, slots=True)
class _InvalidRequestSchemaStep:
    behavior: Literal["INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA"]


@dataclass(frozen=True, slots=True)
class _SourceAuthorityMismatchStep:
    behavior: Literal["INJECT_SOURCE_AUTHORITY_MISMATCH"]
    message_order_number: str


@dataclass(frozen=True, slots=True)
class _TrustedFieldOverrideStep:
    behavior: Literal["INJECT_TRUSTED_FIELD_OVERRIDE"]
    message_order_number: str
    attempted_customer_id: str


@dataclass(frozen=True, slots=True)
class _UnknownToolStep:
    behavior: Literal["INJECT_UNKNOWN_TOOL_NAME"]
    message_order_number: str
    requested_tool_name: str


@dataclass(frozen=True, slots=True)
class _ValidPresentationStep:
    behavior: Literal["VALID_ORDER_SUMMARY_PLAN"]


@dataclass(frozen=True, slots=True)
class _PresentationFaultStep:
    behavior: Literal[
        "INJECT_ZERO_TARGET_FUNCTION_CALLS",
        "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
        "INJECT_INVALID_PRESENTATION_SCHEMA",
        "INJECT_FACT_BEARING_PRESENTATION_ENVELOPE",
    ]


_RequestStep: TypeAlias = (
    _OrderLookupStep
    | _RequestProtocolFaultStep
    | _InvalidRequestSchemaStep
    | _SourceAuthorityMismatchStep
    | _TrustedFieldOverrideStep
    | _UnknownToolStep
)
_PresentationStep: TypeAlias = _ValidPresentationStep | _PresentationFaultStep
_ExecutableStep: TypeAlias = (
    _RequestStep | _PresentationStep | Cycle2ScriptDirective
)
_REQUEST_STEP_TYPES = (
    _OrderLookupStep,
    _RequestProtocolFaultStep,
    _InvalidRequestSchemaStep,
    _SourceAuthorityMismatchStep,
    _TrustedFieldOverrideStep,
    _UnknownToolStep,
)
_PRESENTATION_STEP_TYPES = (
    _ValidPresentationStep,
    _PresentationFaultStep,
)
_CYCLE2_BEHAVIORS = {
    "REQUEST_UNDERSTANDING": frozenset(
        {
            "PROPOSE_SEARCH_ORDERS",
            "PROPOSE_CANDIDATE_SELECTION",
            "PROPOSE_GET_ORDER",
            "PROPOSE_GET_SHIPMENT",
        }
    ),
    "CONTROL_CANDIDATE": frozenset(
        {
            "PROPOSE_GET_ORDER",
            "PROPOSE_GET_SHIPMENT",
            "PROPOSE_ORDER_SUMMARY",
            "PROPOSE_CANDIDATE_QUESTION",
            "PROPOSE_SHIPMENT_ASSESSMENT",
            "PROPOSE_FIXED_RESPONSE",
        }
    ),
    "FAULT_DIRECTIVE": frozenset(
        {
            "INJECT_TOOL_FAULT",
            "INJECT_RUNTIME_RECOVERY_FAULT",
        }
    ),
}
_CYCLE2_FAULT_REFS = frozenset(
    {
        "fault:get-shipment:transient-once-v1",
        "fault:get-shipment:transient-always-v1",
        "fault:get-shipment:source-integrity-v1",
        "fault:get-shipment:timeout-after-dispatch-once-v1",
        "fault:get-shipment:restart-after-retry-finalize-v1",
        "fault:get-shipment:restart-after-retry-finalize-state-invalidated-v1",
        "fault:get-shipment:restart-with-unfinished-attempt-v1",
    }
)


def _fresh_protocol_error() -> ProviderProtocolError:
    error = ProviderProtocolError()
    error.__cause__ = None
    error.__context__ = None
    return error


def _required_string(
    step: Mapping[str, object],
    key: str,
    *,
    default: str,
) -> str:
    value = step.get(key, default)
    if not isinstance(value, str) or not value:
        raise ArtifactContractError("script executable field is invalid")
    return value


def _project_request_step(
    step: Mapping[str, object],
    behavior: str,
) -> _RequestStep:
    if behavior in {
        "VALID_ORDER_LOOKUP",
        "INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION",
    }:
        message_order_number = _required_string(
            step,
            "message_order_number",
            default="O-1001",
        )
        return _OrderLookupStep(
            behavior=behavior,
            message_order_number=message_order_number,
            next_move_order_number=_required_string(
                step,
                "next_move_order_number",
                default=message_order_number,
            ),
        )
    if behavior in {
        "INJECT_ZERO_TARGET_FUNCTION_CALLS",
        "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
    }:
        return _RequestProtocolFaultStep(behavior=behavior)
    if behavior == "INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA":
        return _InvalidRequestSchemaStep(behavior=behavior)
    if behavior == "INJECT_SOURCE_AUTHORITY_MISMATCH":
        return _SourceAuthorityMismatchStep(
            behavior=behavior,
            message_order_number=_required_string(
                step,
                "message_order_number",
                default="O-1001",
            ),
        )
    if behavior == "INJECT_TRUSTED_FIELD_OVERRIDE":
        return _TrustedFieldOverrideStep(
            behavior=behavior,
            message_order_number=_required_string(
                step,
                "message_order_number",
                default="O-1001",
            ),
            attempted_customer_id=_required_string(
                step,
                "attempted_customer_id",
                default="customer-B",
            ),
        )
    if behavior == "INJECT_UNKNOWN_TOOL_NAME":
        return _UnknownToolStep(
            behavior=behavior,
            message_order_number=_required_string(
                step,
                "message_order_number",
                default="O-1001",
            ),
            requested_tool_name=_required_string(
                step,
                "requested_tool_name",
                default="get_any_order",
            ),
        )
    raise ArtifactContractError(
        "unknown scripted Request Understanding behavior"
    )


def _project_step(step: Mapping[str, object]) -> _ExecutableStep:
    purpose = step.get("purpose")
    behavior = step.get("behavior")
    if not isinstance(behavior, str) or not behavior:
        raise ArtifactContractError("script behavior is invalid")
    if (
        purpose == "REQUEST_UNDERSTANDING"
        and behavior not in _CYCLE2_BEHAVIORS["REQUEST_UNDERSTANDING"]
    ):
        return _project_request_step(step, behavior)
    if purpose == "PRESENTATION":
        if behavior == "VALID_ORDER_SUMMARY_PLAN":
            return _ValidPresentationStep(behavior=behavior)
        if behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
            "INJECT_INVALID_PRESENTATION_SCHEMA",
            "INJECT_FACT_BEARING_PRESENTATION_ENVELOPE",
        }:
            return _PresentationFaultStep(behavior=behavior)
        raise ArtifactContractError("unknown scripted Presentation behavior")
    if purpose in _CYCLE2_BEHAVIORS:
        required_keys = {"purpose", "behavior", "candidate_arguments"}
        allowed_keys = (
            required_keys | {"fault_ref"}
            if purpose == "FAULT_DIRECTIVE"
            else required_keys
        )
        candidate_arguments = step.get("candidate_arguments")
        if (
            set(step) != allowed_keys
            or behavior not in _CYCLE2_BEHAVIORS[purpose]
            or not isinstance(candidate_arguments, Mapping)
            or not all(isinstance(key, str) for key in candidate_arguments)
        ):
            raise ArtifactContractError("invalid Cycle 2 scripted directive")
        fault_ref = step.get("fault_ref")
        if purpose == "FAULT_DIRECTIVE":
            if fault_ref not in _CYCLE2_FAULT_REFS or candidate_arguments:
                raise ArtifactContractError("invalid Cycle 2 fault directive")
        elif fault_ref is not None:
            raise ArtifactContractError("Cycle 2 candidate cannot carry a fault")
        if purpose == "REQUEST_UNDERSTANDING":
            expected_arguments: Mapping[str, object]
            if behavior == "PROPOSE_SEARCH_ORDERS":
                expected_arguments = {"product_description": "鞋"}
            elif behavior == "PROPOSE_CANDIDATE_SELECTION":
                expected_arguments = {
                    "candidate_ordinal": candidate_arguments.get(
                        "candidate_ordinal"
                    )
                }
                if expected_arguments["candidate_ordinal"] not in {2, 6}:
                    raise ArtifactContractError(
                        "invalid Cycle 2 ordinal candidate"
                    )
            else:
                expected_arguments = {"order_id": "O-1001"}
            if dict(candidate_arguments) != expected_arguments:
                raise ArtifactContractError(
                    "invalid Cycle 2 Request Understanding candidate"
                )
        elif purpose == "CONTROL_CANDIDATE" and candidate_arguments:
            raise ArtifactContractError("Cycle 2 control candidate must be fact-free")
        frozen_arguments = freeze_json_value(dict(candidate_arguments))
        if not isinstance(frozen_arguments, FrozenJsonDict):
            raise ArtifactContractError("Cycle 2 candidate arguments are invalid")
        return Cycle2ScriptDirective(
            purpose=purpose,
            behavior=behavior,
            candidate_arguments=frozen_arguments,
            fault_ref=fault_ref,
        )
    raise ArtifactContractError("unknown scripted model-call purpose")


class ScriptedModelProviderV2:
    """Consume a closed executable projection through a strict purpose cursor."""

    __slots__ = (
        "_cursor",
        "_runtime_fault",
        "_runtime_fault_taken",
        "_script_execution_ref",
        "_steps",
    )

    def __init__(
        self,
        script: ModelScriptArtifact,
        *,
        script_execution_ref: UUID,
    ) -> None:
        if type(script) is not ModelScriptArtifact:
            raise ArtifactContractError(
                "ScriptedModelProvider requires an authenticated model script"
            )
        if (
            type(script_execution_ref) is not UUID
            or script_execution_ref.version != 4
        ):
            raise ArtifactContractError(
                "script execution identity must be an opaque UUID4"
            )
        self._script_execution_ref = script_execution_ref
        self._steps = tuple(_project_step(step) for step in script.steps)
        self._cursor = 0
        self._runtime_fault_taken = False
        runtime_fault = script.runtime_fault
        if runtime_fault is None:
            self._runtime_fault = None
        elif (
            runtime_fault.get("behavior")
            == "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"
            and runtime_fault.get("boundary") == "AFTER_REVALIDATION_BEFORE_GATE"
        ):
            self._runtime_fault = RuntimeFaultDirective(
                behavior="ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE",
                boundary="AFTER_REVALIDATION_BEFORE_GATE",
            )
        else:
            raise ArtifactContractError("unknown scripted Runtime fault")

    @property
    def script_execution_ref(self) -> UUID:
        """Return only the opaque per-attempt Provider identity."""

        return self._script_execution_ref

    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutputV2:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        status, output = _v2_project_scripted_request(
            provider=self,
            request=request,
        )
        self = None  # type: ignore[assignment]
        request = None  # type: ignore[assignment]
        if status == "CANDIDATE_INVALID":
            raise _v2_fresh_candidate_invalid_error()
        if status != "SUCCESS" or output is None:
            raise _fresh_protocol_error()
        return output

    async def propose_cycle2_initial(
        self,
        request: RequestUnderstandingInput,
    ) -> Cycle2InitialRequestUnderstandingOutputV2:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        output = _project_cycle2_initial(self, request)
        self = None  # type: ignore[assignment]
        request = None  # type: ignore[assignment]
        if output is None:
            raise _fresh_protocol_error()
        return output

    async def propose_cycle2_continuation(
        self,
        request: RequestUnderstandingInput,
    ) -> Cycle2InputCandidate:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        output = _project_cycle2_continuation(self, request)
        self = None  # type: ignore[assignment]
        request = None  # type: ignore[assignment]
        if output is None:
            raise _fresh_protocol_error()
        return output

    async def propose_cycle2_control(
        self,
        request: RequestUnderstandingInput,
        purpose: Cycle2ControlPurpose,
    ) -> Cycle2ControlCandidate:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        if type(purpose) is not Cycle2ControlPurpose:
            raise TypeError("purpose must be Cycle2ControlPurpose")
        output = _project_cycle2_control(self, purpose)
        self = None  # type: ignore[assignment]
        request = None  # type: ignore[assignment]
        purpose = None  # type: ignore[assignment]
        if output is None:
            raise _fresh_protocol_error()
        return output

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan:
        plan: PresentationPlan | None = None
        failed = False
        try:
            plan = self._project_presentation(request)
        except ProviderProtocolError:
            failed = True
        if failed:
            self = None  # type: ignore[assignment]
            request = None  # type: ignore[assignment]
            raise _fresh_protocol_error()
        assert plan is not None
        return plan

    def _project_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan:
        if type(request) is not PresentationInput:
            raise TypeError("request must be PresentationInput")
        step = self._consume_presentation_step()
        behavior = step.behavior
        if behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
            "INJECT_FACT_BEARING_PRESENTATION_ENVELOPE",
        }:
            raise _fresh_protocol_error()
        if behavior == "VALID_ORDER_SUMMARY_PLAN":
            raw_plan: dict[str, object] = {
                "template_id": "ORDER_STATUS_SUMMARY_V1",
                "tone": "WARM",
                "opening_variant": "ACKNOWLEDGE",
                "field_order": [
                    "ORDER_NUMBER",
                    "STATUS",
                    "ITEMS",
                    "ORDERED_AT",
                    "STATUS_UPDATED_AT",
                ],
                "closing_variant": "OFFER_FOLLOW_UP",
            }
        elif behavior == "INJECT_INVALID_PRESENTATION_SCHEMA":
            raw_plan = {
                "template_id": "UNKNOWN_TEMPLATE",
                "tone": "WARM",
                "opening_variant": "ACKNOWLEDGE",
                "field_order": [],
                "closing_variant": "OFFER_FOLLOW_UP",
            }
        else:
            raise _fresh_protocol_error()

        plan: PresentationPlan | None = None
        try:
            plan = PresentationPlan.model_validate(raw_plan)
        except ValidationError:
            pass
        if plan is None:
            raise _fresh_protocol_error()
        return plan

    def take_runtime_fault_directive(self) -> RuntimeFaultDirective | None:
        if self._runtime_fault is None or self._runtime_fault_taken:
            return None
        self._runtime_fault_taken = True
        return self._runtime_fault

    def take_cycle2_directive(
        self,
        purpose: Literal[
            "REQUEST_UNDERSTANDING",
            "CONTROL_CANDIDATE",
            "FAULT_DIRECTIVE",
        ],
    ) -> Cycle2ScriptDirective:
        """Consume the next exact Cycle 2 candidate/fault directive by purpose."""

        if purpose not in _CYCLE2_BEHAVIORS:
            raise TypeError("purpose must be a closed Cycle 2 directive purpose")
        step = self._consume_step()
        if not isinstance(step, Cycle2ScriptDirective) or step.purpose != purpose:
            raise _fresh_protocol_error()
        return step

    def assert_exhausted(self) -> None:
        if self._cursor != len(self._steps):
            raise _fresh_protocol_error()

    def _consume_request_step(self) -> _RequestStep:
        step = self._consume_step()
        if type(step) not in _REQUEST_STEP_TYPES:
            raise _fresh_protocol_error()
        return step

    def _consume_presentation_step(self) -> _PresentationStep:
        step = self._consume_step()
        if type(step) not in _PRESENTATION_STEP_TYPES:
            raise _fresh_protocol_error()
        return step

    def _consume_step(self) -> _ExecutableStep:
        if self._cursor >= len(self._steps):
            raise _fresh_protocol_error()
        step = self._steps[self._cursor]
        self._cursor += 1
        return step


def _take_cycle2_candidate(
    provider: ScriptedModelProviderV2,
    purpose: Literal["REQUEST_UNDERSTANDING", "CONTROL_CANDIDATE"],
) -> Cycle2ScriptDirective | None:
    try:
        return provider.take_cycle2_directive(purpose)
    except ProviderProtocolError:
        return None


def _project_cycle2_initial(
    provider: ScriptedModelProviderV2,
    request: RequestUnderstandingInput,
) -> Cycle2InitialRequestUnderstandingOutputV2 | None:
    directive = _take_cycle2_candidate(provider, "REQUEST_UNDERSTANDING")
    if directive is None or directive.behavior != "PROPOSE_SEARCH_ORDERS":
        return None
    product_description = directive.candidate_arguments.get(
        "product_description"
    )
    if type(product_description) is not str:
        return None
    goal = f"查找最近购买的{product_description}订单"
    try:
        return Cycle2InitialRequestUnderstandingOutputV2(
            schema_version="e2e01-cycle2-initial.p0.v1",
            message_ref=request.message_ref,
            contextualization=QueryContextualizationCandidateV2(
                text=goal,
                resolved_reference_candidates=(),
                uncertainties=(),
                source_message_refs=(request.message_ref,),
            ),
            task_delta_candidates=(
                Cycle2InitialTaskDeltaCandidateV2(
                    candidate_id=uuid5(
                        NAMESPACE_URL,
                        f"{provider.script_execution_ref}:cycle2-initial-delta",
                    ),
                    operation=TaskDeltaOperation.ADD_GOAL,
                    goal_patch=goal,
                    input_candidates=(
                        Cycle2InputCandidate(
                            name="product_description",
                            candidate_value=product_description,
                            source_ref=request.message_ref,
                            source_quote=product_description,
                            confidence=0.99,
                        ),
                    ),
                    confidence=0.99,
                ),
            ),
            next_move_candidate=NextMove(
                kind=NextMoveKind.CALL_TOOL,
                requested_tool_name="search_orders",
                arguments={"product_description": product_description},
                base_task_state_version=None,
            ),
        )
    except (TypeError, ValueError):
        return None


def _project_cycle2_continuation(
    provider: ScriptedModelProviderV2,
    request: RequestUnderstandingInput,
) -> Cycle2InputCandidate | None:
    directive = _take_cycle2_candidate(provider, "REQUEST_UNDERSTANDING")
    if directive is None:
        return None
    projected = {
        "PROPOSE_CANDIDATE_SELECTION": (
            "candidate_ordinal",
            directive.candidate_arguments.get("candidate_ordinal"),
        ),
        "PROPOSE_GET_ORDER": (
            "order_id",
            directive.candidate_arguments.get("order_id"),
        ),
        "PROPOSE_GET_SHIPMENT": (
            "order_id",
            directive.candidate_arguments.get("order_id"),
        ),
    }.get(directive.behavior)
    if projected is None:
        return None
    name, value = projected
    source_quote = (
        request.original_query
        if name == "candidate_ordinal"
        else str(value)
    )
    try:
        return Cycle2InputCandidate(
            name=name,
            candidate_value=value,
            source_ref=request.message_ref,
            source_quote=source_quote,
            confidence=0.99,
        )
    except (TypeError, ValueError):
        return None


def _project_cycle2_control(
    provider: ScriptedModelProviderV2,
    purpose: Cycle2ControlPurpose,
) -> Cycle2ControlCandidate | None:
    directive = _take_cycle2_candidate(provider, "CONTROL_CANDIDATE")
    if directive is None:
        return None
    behavior = directive.behavior
    if (
        purpose is Cycle2ControlPurpose.PROPOSE_GET_ORDER
        and behavior == "PROPOSE_GET_ORDER"
    ):
        return Cycle2ControlCandidate(
            kind=Cycle2ControlCandidateKind.CALL_TOOL,
            requested_tool_name="get_order",
        )
    if purpose is Cycle2ControlPurpose.PROPOSE_POST_ORDER:
        if behavior == "PROPOSE_ORDER_SUMMARY":
            return Cycle2ControlCandidate(
                kind=Cycle2ControlCandidateKind.FINISH,
            )
        if behavior == "PROPOSE_GET_SHIPMENT":
            return Cycle2ControlCandidate(
                kind=Cycle2ControlCandidateKind.CALL_TOOL,
                requested_tool_name="get_shipment",
            )
        return None
    matching_finish = {
        Cycle2ControlPurpose.PROPOSE_CANDIDATE_QUESTION: (
            "PROPOSE_CANDIDATE_QUESTION"
        ),
        Cycle2ControlPurpose.PROPOSE_SHIPMENT_ASSESSMENT: (
            "PROPOSE_SHIPMENT_ASSESSMENT"
        ),
        Cycle2ControlPurpose.PROPOSE_FIXED_RESPONSE: "PROPOSE_FIXED_RESPONSE",
    }.get(purpose)
    if behavior != matching_finish:
        return None
    return Cycle2ControlCandidate(kind=Cycle2ControlCandidateKind.FINISH)


def _v2_fresh_candidate_invalid_error(
) -> RequestUnderstandingCandidateInvalidError:
    error = RequestUnderstandingCandidateInvalidError()
    error.__cause__ = None
    error.__context__ = None
    return error


def _v2_project_scripted_request(
    *,
    provider: ScriptedModelProviderV2,
    request: RequestUnderstandingInput,
) -> tuple[str, RequestUnderstandingOutputV2 | None]:
    output: RequestUnderstandingOutputV2 | None = None
    try:
        step = provider._consume_request_step()
        behavior = step.behavior
        if behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
        }:
            return "PROTOCOL_ERROR", None

        message_order_number = "O-1001"
        next_move_order_number = message_order_number
        requested_tool_name = "get_order"
        attempted_customer_id: str | None = None
        if type(step) is _OrderLookupStep:
            message_order_number = step.message_order_number
            next_move_order_number = step.next_move_order_number
        elif type(step) is _SourceAuthorityMismatchStep:
            message_order_number = step.message_order_number
            next_move_order_number = message_order_number
        elif type(step) is _TrustedFieldOverrideStep:
            message_order_number = step.message_order_number
            next_move_order_number = message_order_number
            attempted_customer_id = step.attempted_customer_id
        elif type(step) is _UnknownToolStep:
            message_order_number = step.message_order_number
            next_move_order_number = message_order_number
            requested_tool_name = step.requested_tool_name
        elif type(step) is not _InvalidRequestSchemaStep:
            return "PROTOCOL_ERROR", None

        arguments: dict[str, object] = {
            "order_id": next_move_order_number,
        }
        task_delta_candidates: tuple[dict[str, object], ...] = (
            {
                "candidate_id": uuid5(
                    NAMESPACE_URL,
                    (
                        "script-execution:"
                        f"{provider.script_execution_ref}:{request.message_ref}"
                    ),
                ),
                "operation": TaskDeltaOperation.ADD_GOAL,
                "goal_patch": "查询指定订单状态",
                "input_candidates": (
                    {
                        "name": "order_id",
                        "candidate_value": message_order_number,
                        "semantic_role": "TARGET_RESOURCE_IDENTIFIER",
                        "authority": InputAuthority.USER_CLAIM,
                        "source_kind": InputSourceKind.CURRENT_MESSAGE,
                        "source_ref": request.message_ref,
                        "source_quote": message_order_number,
                        "confidence": 1.0,
                    },
                ),
                "confidence": 1.0,
            },
        )
        schema_version = "e2e01-thin-v2"
        if behavior == "INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA":
            schema_version = "e2e01-thin-v1"
            task_delta_candidates = ()
        elif behavior == "INJECT_SOURCE_AUTHORITY_MISMATCH":
            task_delta_candidates[0]["input_candidates"][0][  # type: ignore[index]
                "authority"
            ] = InputAuthority.MODEL_INFERENCE
        elif behavior == "INJECT_TRUSTED_FIELD_OVERRIDE":
            assert attempted_customer_id is not None
            arguments["customer_id"] = attempted_customer_id
        elif behavior not in {
            "VALID_ORDER_LOOKUP",
            "INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION",
            "INJECT_UNKNOWN_TOOL_NAME",
        }:
            return "PROTOCOL_ERROR", None

        raw_arguments: dict[str, object] = {
            "schema_version": schema_version,
            "message_ref": request.message_ref,
            "contextualization": {
                "text": request.original_query,
                "resolved_reference_candidates": (
                    {
                        "name": "order_id",
                        "candidate_value": message_order_number,
                        "source_kind": ReferenceSourceKindV2.CURRENT_MESSAGE,
                        "source_ref": request.message_ref,
                        "source_quote": message_order_number,
                        "confidence": 1.0,
                    },
                ),
                "uncertainties": (),
                "source_message_refs": (request.message_ref,),
            },
            "task_delta_candidates": task_delta_candidates,
            "next_move_candidate": {
                "kind": NextMoveKind.CALL_TOOL,
                "requested_tool_name": requested_tool_name,
                "arguments": arguments,
                "base_task_state_version": None,
            },
        }
        output = RequestUnderstandingOutputV2.model_validate(
            raw_arguments,
            strict=True,
        )
    except ValidationError:
        return "CANDIDATE_INVALID", None
    except Exception:
        return "PROTOCOL_ERROR", None
    if output is None:
        return "PROTOCOL_ERROR", None
    return "SUCCESS", output
