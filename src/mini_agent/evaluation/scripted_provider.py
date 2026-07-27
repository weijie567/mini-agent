"""Deterministic, explicit-script ModelProvider used by the offline Eval lane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from mini_agent.application.records import ProviderProtocolError
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    InputAuthority,
    InputCandidate,
    InputSourceKind,
    NextMove,
    NextMoveKind,
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
    TaskDeltaCandidate,
    TaskDeltaOperation,
)
from mini_agent.evaluation.artifacts import (
    ArtifactContractError,
    LoadedE2E01Artifacts,
    ModelScriptArtifact,
)


@dataclass(frozen=True, slots=True)
class RuntimeFaultDirective:
    behavior: Literal["ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"]
    boundary: Literal["AFTER_REVALIDATION_BEFORE_GATE"]


def _fresh_protocol_error() -> ProviderProtocolError:
    error = ProviderProtocolError()
    error.__cause__ = None
    error.__context__ = None
    return error


class ScriptedModelProvider:
    """Consume one authenticated model script through a strict purpose cursor."""

    def __init__(
        self,
        artifacts: LoadedE2E01Artifacts,
        *,
        model_script_ref: str,
    ) -> None:
        if type(artifacts) is not LoadedE2E01Artifacts:
            raise ArtifactContractError(
                "ScriptedModelProvider requires authenticated artifacts"
            )
        self._script: ModelScriptArtifact = artifacts.script_by_ref(
            model_script_ref
        )
        self._cursor = 0
        self._runtime_fault_taken = False
        runtime_fault = self._script.runtime_fault
        if runtime_fault is None:
            self._runtime_fault = None
        elif (
            runtime_fault.get("behavior")
            == "ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE"
            and runtime_fault.get("boundary")
            == "AFTER_REVALIDATION_BEFORE_GATE"
        ):
            self._runtime_fault = RuntimeFaultDirective(
                behavior="ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE",
                boundary="AFTER_REVALIDATION_BEFORE_GATE",
            )
        else:
            raise ArtifactContractError("unknown scripted Runtime fault")

    @property
    def model_script_ref(self) -> str:
        """Authenticated scenario identity used by the injected Eval SUT."""

        return self._script.model_script_ref

    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutput:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        step = self._consume_step("REQUEST_UNDERSTANDING")
        behavior = step.get("behavior")
        if behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
        }:
            raise _fresh_protocol_error()

        message_order_number = step.get("message_order_number", "O-1001")
        next_move_order_number = step.get(
            "next_move_order_number",
            message_order_number,
        )
        requested_tool_name = step.get("requested_tool_name", "get_order")
        authority: str = InputAuthority.USER_CLAIM
        arguments: dict[str, object] = {
            "order_id": next_move_order_number,
        }
        task_delta_candidates: list[dict[str, object]] = [
            {
                "candidate_id": uuid5(
                    NAMESPACE_URL,
                    f"{self._script.model_script_ref}:{request.message_ref}",
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
            arguments["customer_id"] = step.get(
                "attempted_customer_id",
                "customer-B",
            )
        elif behavior == "INJECT_UNKNOWN_TOOL_NAME":
            requested_tool_name = step.get(
                "requested_tool_name",
                "get_any_order",
            )
        elif behavior not in {
            "VALID_ORDER_LOOKUP",
            "INJECT_NEXT_MOVE_ARGUMENT_SUBSTITUTION",
        }:
            raise _fresh_protocol_error()

        raw_output = {
            "message_ref": request.message_ref,
            "task_delta_candidates": task_delta_candidates,
            "next_move_candidate": {
                "kind": NextMoveKind.CALL_TOOL,
                "requested_tool_name": requested_tool_name,
                "arguments": arguments,
                "base_task_state_version": None,
            },
        }
        return RequestUnderstandingOutput.model_validate(raw_output)

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan:
        if type(request) is not PresentationInput:
            raise TypeError("request must be PresentationInput")
        step = self._consume_step("PRESENTATION")
        behavior = step.get("behavior")
        if behavior in {
            "INJECT_ZERO_TARGET_FUNCTION_CALLS",
            "INJECT_MULTIPLE_TARGET_FUNCTION_CALLS",
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
        elif behavior == "INJECT_FACT_BEARING_PRESENTATION_ENVELOPE":
            raw_plan = dict(step.get("raw_function_arguments", {}))
        else:
            raise _fresh_protocol_error()

        invalid = False
        plan: PresentationPlan | None = None
        try:
            plan = PresentationPlan.model_validate(raw_plan)
        except ValidationError:
            invalid = True
        if invalid or plan is None:
            raise _fresh_protocol_error()
        return plan

    def take_runtime_fault_directive(self) -> RuntimeFaultDirective | None:
        if self._runtime_fault is None or self._runtime_fault_taken:
            return None
        self._runtime_fault_taken = True
        return self._runtime_fault

    def assert_exhausted(self) -> None:
        if self._cursor != len(self._script.steps):
            raise _fresh_protocol_error()

    def _consume_step(self, expected_purpose: str) -> dict[str, object]:
        if self._cursor >= len(self._script.steps):
            raise _fresh_protocol_error()
        step = self._script.steps[self._cursor]
        if step.get("purpose") != expected_purpose:
            raise _fresh_protocol_error()
        self._cursor += 1
        return dict(step)
