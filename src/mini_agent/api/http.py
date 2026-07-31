from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mini_agent.application.ports import AgentRunHandler, SessionAuthPort
from mini_agent.application.records import AgentRunCommand, AgentRunResult


class _AgentRunRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message: Annotated[str, Field(min_length=1, max_length=4000)]


def create_agent_app(
    *,
    session_auth: SessionAuthPort,
    handler: AgentRunHandler,
) -> FastAPI:
    """Create an injected HTTP boundary without selecting global dependencies."""

    app = FastAPI()

    @app.post(
        "/v1/agent/runs",
        response_model=AgentRunResult,
        response_model_exclude_none=False,
    )
    async def create_agent_run(
        request: _AgentRunRequest,
        opaque_session_id: Annotated[
            str | None,
            Cookie(alias="p0_session"),
        ] = None,
    ) -> AgentRunResult:
        customer_context = (
            None
            if opaque_session_id is None
            else await session_auth.authenticate(opaque_session_id)
        )
        if customer_context is None:
            raise HTTPException(status_code=401, detail="UNAUTHORIZED")
        return await handler.handle(
            AgentRunCommand(
                customer_context=customer_context,
                message=request.message,
            )
        )

    return app
