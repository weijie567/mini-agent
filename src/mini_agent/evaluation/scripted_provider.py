"""Deterministic, explicit-script ModelProvider used by the offline Eval lane."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
)
from mini_agent.evaluation.artifacts import LoadedE2E01Artifacts


@dataclass(frozen=True, slots=True)
class RuntimeFaultDirective:
    behavior: str
    boundary: str


class ScriptedModelProvider:
    """Consume one authenticated model script through a strict purpose cursor."""

    def __init__(
        self,
        artifacts: LoadedE2E01Artifacts,
        *,
        model_script_ref: str,
    ) -> None:
        raise NotImplementedError

    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutput:
        raise NotImplementedError

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan:
        raise NotImplementedError

    def take_runtime_fault_directive(self) -> RuntimeFaultDirective | None:
        raise NotImplementedError

    def assert_exhausted(self) -> None:
        raise NotImplementedError
