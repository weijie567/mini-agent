"""Qwen Responses API Adapter for the informational baseline lane."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from mini_agent.application.records import (
    ProviderProtocolError,
    RequestUnderstandingCandidateInvalidError,
)
from mini_agent.core.presentation import PresentationInput, PresentationPlan
from mini_agent.core.request_understanding import (
    RequestUnderstandingInput,
    RequestUnderstandingOutput,
    RequestUnderstandingOutputV2,
)


QWEN_MODEL_SNAPSHOT = "qwen3.7-plus-2026-05-26"
_OutputModel = TypeVar("_OutputModel", bound=BaseModel)
_REQUEST_UNDERSTANDING_OUTPUT_SCHEMA = RequestUnderstandingOutput.model_json_schema()
_PRESENTATION_PLAN_SCHEMA = PresentationPlan.model_json_schema()
_V2_REQUEST_UNDERSTANDING_OUTPUT_SCHEMA = (
    RequestUnderstandingOutputV2.model_json_schema()
)


def _fresh_protocol_error() -> ProviderProtocolError:
    error = ProviderProtocolError()
    error.__cause__ = None
    error.__context__ = None
    return error


class QwenResponsesAdapter:
    """Map the closed Responses function envelope to canonical model outputs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient,
    ) -> None:
        if (
            not isinstance(base_url, str)
            or not base_url
            or base_url != base_url.strip()
        ):
            raise ValueError("base_url must be a concrete injected value")
        try:
            parsed_url = httpx.URL(base_url)
        except Exception:
            raise ValueError("base_url must be a valid HTTP URL") from None
        if parsed_url.scheme not in {"http", "https"} or parsed_url.host is None:
            raise ValueError("base_url must be a valid HTTP URL")
        if not isinstance(api_key, str) or not api_key or api_key != api_key.strip():
            raise ValueError("api_key must be a concrete injected value")
        if not isinstance(client, httpx.AsyncClient):
            raise TypeError("client must be an injected httpx.AsyncClient")
        self._endpoint = f"{base_url.rstrip('/')}/responses"
        self._api_key = api_key
        self._client = client

    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutput:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        return await self._invoke(
            request=request,
            target_name="submit_next_move",
            description="Submit one Request Understanding candidate.",
            output_model=RequestUnderstandingOutput,
            output_schema=_REQUEST_UNDERSTANDING_OUTPUT_SCHEMA,
        )

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan:
        if type(request) is not PresentationInput:
            raise TypeError("request must be PresentationInput")
        return await self._invoke(
            request=request,
            target_name="submit_presentation_plan",
            description="Submit one fact-free presentation plan.",
            output_model=PresentationPlan,
            output_schema=_PRESENTATION_PLAN_SCHEMA,
        )

    async def _invoke(
        self,
        *,
        request: RequestUnderstandingInput | PresentationInput,
        target_name: str,
        description: str,
        output_model: type[_OutputModel],
        output_schema: dict[str, object],
    ) -> _OutputModel:
        target_tool = {
            "type": "function",
            "name": target_name,
            "description": description,
            "parameters": deepcopy(output_schema),
        }
        body = {
            "model": QWEN_MODEL_SNAPSHOT,
            "input": request.model_dump(mode="json"),
            "tools": [target_tool],
            "tool_choice": {
                "type": "function",
                "name": target_name,
            },
            "store": False,
            "stream": False,
        }
        failed = False
        parsed_output: _OutputModel | None = None
        try:
            response = await self._client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            envelope = response.json()
            if not isinstance(envelope, dict):
                raise ValueError
            raw_output = envelope.get("output")
            if not isinstance(raw_output, list):
                raise ValueError
            function_calls = [
                item
                for item in raw_output
                if isinstance(item, dict) and item.get("type") == "function_call"
            ]
            if len(function_calls) != 1:
                raise ValueError
            function_call = function_calls[0]
            if function_call.get("name") != target_name:
                raise ValueError
            raw_arguments = function_call.get("arguments")
            if not isinstance(raw_arguments, str):
                raise ValueError
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError
            parsed_output = output_model.model_validate(arguments)
        except (
            httpx.HTTPError,
            json.JSONDecodeError,
            ValidationError,
            TypeError,
            ValueError,
        ):
            failed = True
        except Exception:
            failed = True
        if failed or parsed_output is None:
            raise _fresh_protocol_error()
        return parsed_output


def _v2_fresh_candidate_invalid_error(
) -> RequestUnderstandingCandidateInvalidError:
    error = RequestUnderstandingCandidateInvalidError()
    error.__cause__ = None
    error.__context__ = None
    return error


async def _v2_invoke_request_understanding(
    adapter: QwenResponsesAdapter,
    request: RequestUnderstandingInput,
) -> tuple[str, RequestUnderstandingOutputV2 | None]:
    target_name = "submit_next_move"
    target_tool = {
        "type": "function",
        "name": target_name,
        "description": "Submit one Request Understanding candidate.",
        "parameters": deepcopy(_V2_REQUEST_UNDERSTANDING_OUTPUT_SCHEMA),
    }
    body = {
        "model": QWEN_MODEL_SNAPSHOT,
        "input": request.model_dump(mode="json"),
        "tools": [target_tool],
        "tool_choice": {
            "type": "function",
            "name": target_name,
        },
        "store": False,
        "stream": False,
    }
    raw_arguments: str | None = None
    try:
        response = await adapter._client.post(
            adapter._endpoint,
            headers={
                "Authorization": f"Bearer {adapter._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        candidate_envelope = response.json()
        if not isinstance(candidate_envelope, dict):
            raise ValueError
        candidate_output = candidate_envelope.get("output")
        if not isinstance(candidate_output, list):
            raise ValueError
        function_calls = [
            item
            for item in candidate_output
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        if len(function_calls) != 1:
            raise ValueError
        function_call = function_calls[0]
        if function_call.get("name") != target_name:
            raise ValueError
        candidate_arguments = function_call.get("arguments")
        if not isinstance(candidate_arguments, str):
            raise ValueError
        raw_arguments = candidate_arguments
        decoded_arguments = json.loads(raw_arguments)
        if not isinstance(decoded_arguments, dict):
            raise ValueError
        if decoded_arguments is None:
            raise ValueError
    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        return "PROTOCOL_ERROR", None
    except Exception:
        return "PROTOCOL_ERROR", None

    parsed_output: RequestUnderstandingOutputV2 | None = None
    try:
        parsed_output = RequestUnderstandingOutputV2.model_validate_json(
            raw_arguments,
            strict=True,
        )
    except ValidationError:
        return "CANDIDATE_INVALID", None
    except Exception:
        return "PROTOCOL_ERROR", None
    if parsed_output is None:
        return "PROTOCOL_ERROR", None
    return "SUCCESS", parsed_output


class QwenResponsesAdapterV2(QwenResponsesAdapter):
    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutputV2:
        if type(request) is not RequestUnderstandingInput:
            raise TypeError("request must be RequestUnderstandingInput")
        status, output = await _v2_invoke_request_understanding(self, request)
        self = None  # type: ignore[assignment]
        request = None  # type: ignore[assignment]
        if status == "CANDIDATE_INVALID":
            raise _v2_fresh_candidate_invalid_error()
        if status != "SUCCESS" or output is None:
            raise _fresh_protocol_error()
        return output

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan:
        plan: PresentationPlan | None = None
        failed = False
        try:
            plan = await super().plan_presentation(request)
        except ProviderProtocolError:
            failed = True
        if failed:
            self = None  # type: ignore[assignment]
            request = None  # type: ignore[assignment]
            raise _fresh_protocol_error()
        assert plan is not None
        return plan
