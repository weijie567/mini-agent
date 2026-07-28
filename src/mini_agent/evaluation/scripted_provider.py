"""Deterministic, execution-only ModelProvider used by the offline Eval lane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from mini_agent.application.records import (
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
)
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputSourceKind,
    NextMoveKind,
    ReferenceSourceKindV2,
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
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
_ExecutableStep: TypeAlias = _RequestStep | _PresentationStep
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
    if purpose == "REQUEST_UNDERSTANDING":
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
    raise ArtifactContractError("unknown scripted model-call purpose")


class ScriptedModelProvider:
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
    ) -> RequestUnderstandingOutput:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        step = self._consume_request_step()
        behavior = step.behavior
        if behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
        }:
            raise _fresh_protocol_error()

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

        authority: str = InputAuthority.USER_CLAIM
        arguments: dict[str, object] = {
            "order_id": next_move_order_number,
        }
        task_delta_candidates: list[dict[str, object]] = [
            {
                "candidate_id": uuid5(
                    NAMESPACE_URL,
                    (
                        "script-execution:"
                        f"{self._script_execution_ref}:{request.message_ref}"
                    ),
                ),
                "operation": TaskDeltaOperation.ADD_GOAL,
                "goal_patch": "查询指定订单状态",
                "input_candidates": [
                    {
                        "name": "order_id",
                        "candidate_value": message_order_number,
                        "semantic_role": "TARGET_RESOURCE_IDENTIFIER",
                        "authority": authority,
                        "source_kind": InputSourceKind.CURRENT_MESSAGE,
                        "source_ref": request.message_ref,
                        "source_quote": message_order_number,
                        "confidence": 1.0,
                    }
                ],
                "confidence": 1.0,
            }
        ]

        if behavior == "INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA":
            task_delta_candidates = []
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
            raise _fresh_protocol_error()

        return RequestUnderstandingOutput.model_validate(
            {
                "message_ref": request.message_ref,
                "task_delta_candidates": task_delta_candidates,
                "next_move_candidate": {
                    "kind": NextMoveKind.CALL_TOOL,
                    "requested_tool_name": requested_tool_name,
                    "arguments": arguments,
                    "base_task_state_version": None,
                },
            }
        )

    async def plan_presentation(
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


def _v2_fresh_candidate_invalid_error(
) -> RequestUnderstandingCandidateInvalidError:
    error = RequestUnderstandingCandidateInvalidError()
    error.__cause__ = None
    error.__context__ = None
    return error


def _v2_project_scripted_request(
    *,
    provider: ScriptedModelProvider,
    request: RequestUnderstandingInput,
    step: _RequestStep,
) -> RequestUnderstandingOutputV2:
    behavior = step.behavior
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
        raise _fresh_protocol_error()

    authority: InputAuthority = InputAuthority.USER_CLAIM
    arguments: dict[str, object] = {
        "order_id": next_move_order_number,
    }
    candidate_id = uuid5(
        NAMESPACE_URL,
        (
            "script-execution:"
            f"{provider.script_execution_ref}:{request.message_ref}"
        ),
    )
    task_delta_candidates: tuple[dict[str, object], ...] = (
        {
            "candidate_id": candidate_id,
            "operation": TaskDeltaOperation.ADD_GOAL,
            "goal_patch": "查询指定订单状态",
            "input_candidates": (
                {
                    "name": "order_id",
                    "candidate_value": message_order_number,
                    "semantic_role": "TARGET_RESOURCE_IDENTIFIER",
                    "authority": authority,
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
        raise _fresh_protocol_error()

    raw_arguments: dict[str, object] | None = {
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
    output: RequestUnderstandingOutputV2 | None = None
    failed = False
    try:
        output = RequestUnderstandingOutputV2.model_validate(
            raw_arguments,
            strict=True,
        )
    except ValidationError:
        failed = True
    raw_arguments = None
    if failed or output is None:
        raise _v2_fresh_candidate_invalid_error()
    return output


class ScriptedModelProviderV2(ScriptedModelProvider):
    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutputV2:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        step = self._consume_request_step()
        if step.behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
        }:
            raise _fresh_protocol_error()
        return _v2_project_scripted_request(
            provider=self,
            request=request,
            step=step,
        )
