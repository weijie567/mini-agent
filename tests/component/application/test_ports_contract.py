from pathlib import Path

from mini_agent.application.ports import (
    GetOrderPort,
    ModelProvider,
    RuntimeRecordPort,
    SessionAuthPort,
)


class CandidateOnlyProvider:
    async def propose_next_move(self, request: object) -> object:
        raise NotImplementedError

    async def plan_presentation(self, request: object) -> object:
        raise NotImplementedError


def test_model_provider_surface_only_proposes_validated_candidates() -> None:
    provider = CandidateOnlyProvider()

    assert isinstance(provider, ModelProvider)
    assert not hasattr(provider, "execute_tool")
    assert not hasattr(provider, "save_task")


def test_ports_are_protocols_owned_by_application() -> None:
    assert ModelProvider._is_protocol
    assert SessionAuthPort._is_protocol
    assert GetOrderPort._is_protocol
    assert RuntimeRecordPort._is_protocol


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
