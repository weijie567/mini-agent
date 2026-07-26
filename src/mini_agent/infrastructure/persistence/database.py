from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_LOCAL_DATABASE_URL = (
    "postgresql+psycopg://mini_agent:mini_agent_local_only@127.0.0.1:55432/mini_agent"
)
DEFAULT_LOCAL_TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "mini_agent:mini_agent_local_only@127.0.0.1:55433/mini_agent_test"
)
_DISPOSABLE_TEST_DATABASE_ERROR = (
    "integration tests require the local disposable db-test at "
    "127.0.0.1:55433/mini_agent_test without URL query or fragment"
)
_LIBPQ_TEST_ROUTING_ENVIRONMENT_VARIABLES = frozenset(
    {
        "PGDATABASE",
        "PGHOST",
        "PGHOSTADDR",
        "PGLOADBALANCEHOSTS",
        "PGOPTIONS",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "PGTARGETSESSIONATTRS",
    }
)
_TEST_DATABASE_CONNECT_ARGS: dict[str, object] = {
    "host": "127.0.0.1",
    "hostaddr": "127.0.0.1",
    "port": 55433,
    "dbname": "mini_agent_test",
}


def validate_test_database_url(database_url: str) -> str:
    if not isinstance(database_url, str) or "?" in database_url or "#" in database_url:
        raise ValueError(_DISPOSABLE_TEST_DATABASE_ERROR)
    try:
        parsed: URL = make_url(database_url)
    except (ArgumentError, TypeError) as exc:
        raise ValueError(_DISPOSABLE_TEST_DATABASE_ERROR) from exc
    is_disposable_target = (
        parsed.drivername == "postgresql+psycopg"
        and parsed.host == "127.0.0.1"
        and parsed.port == 55433
        and parsed.database == "mini_agent_test"
        and not parsed.query
    )
    if not is_disposable_target:
        raise ValueError(_DISPOSABLE_TEST_DATABASE_ERROR)
    return database_url


def validate_test_connection_environment() -> None:
    configured = sorted(
        variable
        for variable in _LIBPQ_TEST_ROUTING_ENVIRONMENT_VARIABLES
        if variable in os.environ
    )
    if configured:
        names = ", ".join(configured)
        raise ValueError(
            f"integration tests reject libpq routing environment variables: {names}"
        )


def test_database_connect_args(database_url: str) -> dict[str, object]:
    validate_test_database_url(database_url)
    validate_test_connection_environment()
    return dict(_TEST_DATABASE_CONNECT_ARGS)


def guard_test_database_engine(engine: Engine) -> Engine:
    @event.listens_for(engine, "do_connect")
    def _guard_connection(
        _dialect: object,
        _connection_record: object,
        _connection_args: list[object],
        connection_parameters: dict[str, object],
    ) -> None:
        validate_test_connection_environment()
        connection_parameters.update(_TEST_DATABASE_CONNECT_ARGS)

    @event.listens_for(engine, "checkout")
    def _guard_checkout(
        _dbapi_connection: object,
        _connection_record: object,
        _connection_proxy: object,
    ) -> None:
        validate_test_connection_environment()

    return engine


def database_url_from_environment(*, testing: bool = False) -> str:
    if testing:
        validate_test_connection_environment()
        return validate_test_database_url(
            os.environ.get(
                "MINI_AGENT_TEST_DATABASE_URL",
                DEFAULT_LOCAL_TEST_DATABASE_URL,
            )
        )
    return os.environ.get("MINI_AGENT_DATABASE_URL", DEFAULT_LOCAL_DATABASE_URL)


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


def build_test_engine(
    database_url: str | None = None,
    *,
    schema: str | None = None,
) -> Engine:
    resolved_url = database_url or database_url_from_environment(testing=True)
    connect_args = test_database_connect_args(resolved_url)
    if schema is not None:
        from mini_agent.infrastructure.persistence.migrations import (
            validate_schema_name,
        )

        safe_schema = validate_schema_name(schema)
        connect_args["options"] = f"-csearch_path={safe_schema},public"

    engine = create_engine(
        resolved_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    return guard_test_database_engine(engine)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
