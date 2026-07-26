from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import create_engine, inspect, text

from mini_agent.infrastructure.persistence.database import (
    DEFAULT_LOCAL_TEST_DATABASE_URL,
    database_url_from_environment,
)
from mini_agent.infrastructure.persistence.migrations import (
    upgrade_database_to_head,
)
from mini_agent.infrastructure.persistence.models import Base


def _extension_schema(database_url: str) -> str | None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return connection.scalar(
                text(
                    """
                    SELECT namespace.nspname
                    FROM pg_extension AS extension
                    JOIN pg_namespace AS namespace
                      ON namespace.oid = extension.extnamespace
                    WHERE extension.extname = 'vector'
                    """
                )
            )
    finally:
        engine.dispose()


def _schema_exists(database_url: str, schema: str) -> bool:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return bool(
                connection.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_namespace
                            WHERE nspname = :schema
                        )
                        """
                    ),
                    {"schema": schema},
                )
            )
    finally:
        engine.dispose()


def test_testing_url_defaults_to_disposable_db_test(monkeypatch) -> None:
    monkeypatch.setenv(
        "MINI_AGENT_DATABASE_URL",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55432/mini_agent",
    )
    monkeypatch.delenv("MINI_AGENT_TEST_DATABASE_URL", raising=False)

    assert database_url_from_environment(testing=True) == (
        DEFAULT_LOCAL_TEST_DATABASE_URL
    )


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "sqlite:///mini_agent_test.db",
        "postgresql+psycopg://mini_agent:local@db.example:55433/mini_agent_test",
        "postgresql+psycopg://mini_agent:local@localhost:55433/mini_agent_test",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55432/mini_agent_test",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent",
        "postgresql://mini_agent:local@127.0.0.1:55433/mini_agent_test",
    ],
)
def test_testing_url_rejects_non_disposable_targets(
    monkeypatch,
    unsafe_url: str,
) -> None:
    monkeypatch.setenv("MINI_AGENT_TEST_DATABASE_URL", unsafe_url)

    with pytest.raises(ValueError, match="disposable db-test"):
        database_url_from_environment(testing=True)


def test_empty_namespace_has_only_alembic_bootstrap(postgres_namespace) -> None:
    engine = postgres_namespace.build_engine()
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        assert not Base.metadata.tables

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == (
                postgres_namespace.schema
            )
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20260726_0001"
            )
    finally:
        engine.dispose()


def test_programmatic_migration_cannot_be_redirected_to_dev_url(
    postgres_namespace_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "MINI_AGENT_DATABASE_URL",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:1/mini_agent",
    )
    namespace = postgres_namespace_factory.create("programmatic-url")
    try:
        assert _schema_exists(namespace.database_url, namespace.schema)
    finally:
        postgres_namespace_factory.drop(namespace)


def test_upgrade_head_is_idempotent(postgres_namespace) -> None:
    upgrade_database_to_head(
        postgres_namespace.database_url,
        schema=postgres_namespace.schema,
    )
    engine = postgres_namespace.build_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
    finally:
        engine.dispose()


def test_eval_run_namespaces_are_isolated(postgres_namespace_factory) -> None:
    left = postgres_namespace_factory.create("eval-run-left")
    right = postgres_namespace_factory.create("eval-run-right")
    left_engine = left.build_engine()
    right_engine = right.build_engine()
    try:
        with left_engine.begin() as connection:
            connection.execute(text("CREATE TABLE namespace_probe (value text NOT NULL)"))
            connection.execute(
                text("INSERT INTO namespace_probe (value) VALUES ('left')")
            )

        with right_engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('namespace_probe')")) is None

        with left_engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM namespace_probe")) == "left"
    finally:
        left_engine.dispose()
        right_engine.dispose()
        postgres_namespace_factory.drop(left)
        postgres_namespace_factory.drop(right)


def test_vector_extension_is_public_and_survives_worker_schema_drop(
    postgres_namespace_factory,
    postgres_database_url: str,
) -> None:
    namespace = postgres_namespace_factory.create("extension-owner")
    assert _extension_schema(postgres_database_url) == "public"

    postgres_namespace_factory.drop(namespace)

    assert not _schema_exists(postgres_database_url, namespace.schema)
    assert _extension_schema(postgres_database_url) == "public"


def test_cleanup_retains_failures_and_continues_other_drops(
    postgres_namespace_factory,
    postgres_database_url: str,
    monkeypatch,
) -> None:
    factory = type(postgres_namespace_factory)(postgres_database_url, "fault")
    failed_first = factory.create("failed-first")
    successful = factory.create("successful")
    failed_second = factory.create("failed-second")
    original_drop: Callable[[str], None] = factory._drop_schema
    failed_schemas = {failed_first.schema, failed_second.schema}

    def injected_drop(schema: str) -> None:
        if schema in failed_schemas:
            raise RuntimeError(f"injected drop failure for {schema}")
        original_drop(schema)

    monkeypatch.setattr(factory, "_drop_schema", injected_drop)
    try:
        with pytest.raises(ExceptionGroup) as captured:
            factory.cleanup()

        assert len(captured.value.exceptions) == 2
        assert set(factory.tracked_schemas) == failed_schemas
        assert not _schema_exists(postgres_database_url, successful.schema)
        assert all(
            _schema_exists(postgres_database_url, schema)
            for schema in failed_schemas
        )
    finally:
        monkeypatch.setattr(factory, "_drop_schema", original_drop)
        factory.cleanup()
