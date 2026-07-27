"""Qwen Responses API Adapter for the informational baseline lane."""

from __future__ import annotations

import httpx

from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
)


QWEN_MODEL_SNAPSHOT = "qwen3.7-plus-2026-05-26"


class QwenResponsesAdapter:
    """Map the closed Responses function envelope to canonical model outputs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient,
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
