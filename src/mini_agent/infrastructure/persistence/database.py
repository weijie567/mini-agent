from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_LOCAL_DATABASE_URL = (
    "postgresql+psycopg://"
    "mini_agent:mini_agent_local_only@localhost:55432/mini_agent"
)


def database_url_from_environment(*, testing: bool = False) -> str:
    variable = "MINI_AGENT_TEST_DATABASE_URL" if testing else "MINI_AGENT_DATABASE_URL"
    if testing:
        return os.environ.get(
            variable,
            os.environ.get("MINI_AGENT_DATABASE_URL", DEFAULT_LOCAL_DATABASE_URL),
        )
    return os.environ.get(variable, DEFAULT_LOCAL_DATABASE_URL)


def build_engine(
    database_url: str | None = None,
    *,
    schema: str | None = None,
) -> Engine:
    resolved_url = database_url or database_url_from_environment()
    if make_url(resolved_url).get_backend_name() != "postgresql":
        raise ValueError("Mini Agent persistence requires PostgreSQL")

    connect_args: dict[str, str] = {}
    if schema is not None:
        from mini_agent.infrastructure.persistence.migrations import (
            validate_schema_name,
        )

        safe_schema = validate_schema_name(schema)
        connect_args["options"] = f"-csearch_path={safe_schema},public"

    return create_engine(
        resolved_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
