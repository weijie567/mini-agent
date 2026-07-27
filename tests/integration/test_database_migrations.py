from __future__ import annotations

from collections.abc import Callable

import pytest
from alembic import command
from sqlalchemy import inspect, text

from mini_agent.infrastructure.persistence.database import (
    DEFAULT_LOCAL_DATABASE_URL,
    DEFAULT_LOCAL_TEST_DATABASE_URL,
    build_engine,
    build_test_engine,
    database_url_from_environment,
    validate_test_database_url,
)
from mini_agent.infrastructure.persistence.migrations import (
    alembic_config,
    upgrade_database_to_head,
)
from mini_agent.infrastructure.persistence.models import (
    Base,
    MockOrderModel,
    P0RecordModel,
    P0RecordReferenceModel,
)

_LIBPQ_ROUTING_ENVIRONMENT_CASES = [
    ("PGHOSTADDR", "203.0.113.10"),
    ("PGHOST", "db.example"),
    ("PGPORT", "5432"),
    ("PGDATABASE", "mini_agent"),
    ("PGSERVICE", "production"),
    ("PGSERVICEFILE", "/tmp/unsafe-pg-service.conf"),
    ("PGSYSCONFDIR", "/tmp/unsafe-pg-system"),
    ("PGTARGETSESSIONATTRS", "read-write"),
    ("PGLOADBALANCEHOSTS", "random"),
    ("PGOPTIONS", "-csearch_path=public"),
]


def _extension_schema(database_url: str) -> str | None:
    engine = build_test_engine(database_url)
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
    engine = build_test_engine(database_url)
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
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?host=db.example",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?port=5432",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?dbname=mini_agent",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?hostaddr=203.0.113.10",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?service=production",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test?sslmode=disable",
        "postgresql+psycopg://mini_agent:local@127.0.0.1:55433/mini_agent_test#fragment",
        "postgresql+psycopg://mini_agent:local?host=db.example@127.0.0.1:55433/mini_agent_test",
        "postgresql+psycopg://mini_agent:local#fragment@127.0.0.1:55433/mini_agent_test",
    ],
)
def test_testing_url_rejects_non_disposable_targets(
    monkeypatch,
    unsafe_url: str,
) -> None:
    monkeypatch.setenv("MINI_AGENT_TEST_DATABASE_URL", unsafe_url)

    with pytest.raises(ValueError, match="disposable db-test"):
        database_url_from_environment(testing=True)


def test_encoded_password_cannot_override_test_target() -> None:
    encoded_user_info_url = (
        "postgresql+psycopg://mini_agent:"
        "local%3Fhost%3Ddb.example%26port%3D5432%23fragment"
        "@127.0.0.1:55433/mini_agent_test"
    )

    assert validate_test_database_url(encoded_user_info_url) == encoded_user_info_url


@pytest.mark.parametrize(
    ("variable", "value"),
    _LIBPQ_ROUTING_ENVIRONMENT_CASES,
)
def test_testing_connection_rejects_libpq_routing_environment(
    monkeypatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=variable):
        database_url_from_environment(testing=True)


def test_test_engine_rechecks_routing_environment_before_each_connection(
    postgres_database_url: str,
    monkeypatch,
) -> None:
    engine = build_test_engine(postgres_database_url)
    try:
        with engine.connect() as connection:
            connection_info = connection.connection.driver_connection.info
            assert connection_info.host == "127.0.0.1"
            assert connection_info.hostaddr == "127.0.0.1"
            assert connection_info.port == 55433
            assert connection_info.dbname == "mini_agent_test"

        monkeypatch.setenv("PGHOSTADDR", "203.0.113.10")
        with pytest.raises(ValueError, match="PGHOSTADDR"):
            engine.connect()

        monkeypatch.delenv("PGHOSTADDR")
        with engine.connect() as connection:
            connection_info = connection.connection.driver_connection.info
            assert connection_info.host == "127.0.0.1"
            assert connection_info.hostaddr == "127.0.0.1"
            assert connection_info.port == 55433
            assert connection_info.dbname == "mini_agent_test"
    finally:
        engine.dispose()


def test_development_engine_does_not_enable_test_environment_guard(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.10")

    engine = build_engine(DEFAULT_LOCAL_DATABASE_URL)
    try:
        assert engine.url.database == "mini_agent"
    finally:
        engine.dispose()


def test_namespace_has_exact_p0_schema_at_head(postgres_namespace) -> None:
    engine = postgres_namespace.build_engine()
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "mock_orders",
            "p0_record_references",
            "p0_records",
        }
        assert set(Base.metadata.tables) == {
            "mock_orders",
            "p0_record_references",
            "p0_records",
        }
        assert P0RecordModel.__tablename__ == "p0_records"
        assert P0RecordReferenceModel.__tablename__ == "p0_record_references"
        assert MockOrderModel.__tablename__ == "mock_orders"

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == (
                postgres_namespace.schema
            )
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == ("20260727_0002")
    finally:
        engine.dispose()


def test_p0_schema_columns_constraints_indexes_and_foreign_keys(
    postgres_namespace,
) -> None:
    engine = postgres_namespace.build_engine()
    try:
        inspector = inspect(engine)
        assert {column["name"] for column in inspector.get_columns("p0_records")} == {
            "record_id",
            "record_code",
            "record_schema_version",
            "logical_identity",
            "direct_owner_customer_id",
            "scope_owner_customer_id",
            "conversation_id",
            "run_id",
            "task_id",
            "request_unit_id",
            "lifecycle_status",
            "state_version",
            "attempt_count",
            "recovery_sort_at",
            "envelope",
            "stored_at",
        }
        assert {
            column["name"]
            for column in inspector.get_columns("p0_record_references")
        } == {
            "reference_id",
            "source_record_code",
            "source_logical_identity",
            "ordinal",
            "relation",
            "target_record_code",
            "target_logical_identity",
        }
        assert {column["name"] for column in inspector.get_columns("mock_orders")} == {
            "customer_id",
            "order_id",
            "order_payload",
            "stored_at",
        }

        record_unique_names = {
            item["name"] for item in inspector.get_unique_constraints("p0_records")
        }
        assert record_unique_names == {"uq_p0_records_code_identity"}
        record_check_names = {
            item["name"] for item in inspector.get_check_constraints("p0_records")
        }
        assert record_check_names == {
            "ck_p0_records_attempt_count",
            "ck_p0_records_code_closed",
            "ck_p0_records_code_version_closed",
            "ck_p0_records_envelope_object",
            "ck_p0_records_logical_identity_array",
            "ck_p0_records_state_version",
        }
        assert {
            item["name"]
            for item in inspector.get_indexes("p0_records")
            if not item.get("duplicates_constraint")
        } == {
            "ix_p0_records_code_request_unit",
            "ix_p0_records_code_run_status",
            "ix_p0_records_code_task_status",
            "ix_p0_records_recovery_candidate",
            "ix_p0_records_scope_owner_code",
        }

        reference_unique_names = {
            item["name"]
            for item in inspector.get_unique_constraints("p0_record_references")
        }
        assert reference_unique_names == {
            "uq_p0_record_references_source_ordinal",
            "uq_p0_record_references_source_relation_target",
        }
        assert {
            item["name"]
            for item in inspector.get_indexes("p0_record_references")
            if not item.get("duplicates_constraint")
        } == {"ix_p0_record_references_target"}
        foreign_keys = {
            foreign_key["name"]: foreign_key
            for foreign_key in inspector.get_foreign_keys("p0_record_references")
        }
        assert set(foreign_keys) == {
            "fk_p0_record_references_source",
            "fk_p0_record_references_target",
        }
        assert foreign_keys["fk_p0_record_references_source"][
            "referred_columns"
        ] == ["record_code", "logical_identity"]
        assert foreign_keys["fk_p0_record_references_source"]["options"] == {
            "ondelete": "CASCADE",
            "initially": "DEFERRED",
            "deferrable": True,
        }
        assert foreign_keys["fk_p0_record_references_target"][
            "referred_columns"
        ] == ["record_code", "logical_identity"]
        assert foreign_keys["fk_p0_record_references_target"]["options"] == {
            "ondelete": "RESTRICT",
            "initially": "DEFERRED",
            "deferrable": True,
        }
        assert inspector.get_pk_constraint("mock_orders")["constrained_columns"] == [
            "customer_id",
            "order_id",
        ]
    finally:
        engine.dispose()


def test_disposable_namespace_upgrade_downgrade_upgrade(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("migration-cycle")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        command.downgrade(config, "20260726_0001")
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {"alembic_version"}
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "20260726_0001"

        command.upgrade(config, "head")
        inspector.clear_cache()
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "mock_orders",
            "p0_record_references",
            "p0_records",
        }
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "20260727_0002"
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


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


def test_programmatic_migration_rejects_libpq_routing_environment(
    postgres_namespace,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGSERVICE", "production")
    with pytest.raises(ValueError, match="PGSERVICE"):
        upgrade_database_to_head(
            postgres_namespace.database_url,
            schema=postgres_namespace.schema,
            testing=True,
        )

    monkeypatch.delenv("PGSERVICE")
    upgrade_database_to_head(
        postgres_namespace.database_url,
        schema=postgres_namespace.schema,
        testing=True,
    )


def test_upgrade_head_is_idempotent(postgres_namespace) -> None:
    upgrade_database_to_head(
        postgres_namespace.database_url,
        schema=postgres_namespace.schema,
        testing=True,
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
            connection.execute(
                text("CREATE TABLE namespace_probe (value text NOT NULL)")
            )
            connection.execute(
                text("INSERT INTO namespace_probe (value) VALUES ('left')")
            )

        with right_engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT to_regclass('namespace_probe')")) is None
            )

        with left_engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT value FROM namespace_probe")) == "left"
            )
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
            _schema_exists(postgres_database_url, schema) for schema in failed_schemas
        )
    finally:
        monkeypatch.setattr(factory, "_drop_schema", original_drop)
        factory.cleanup()


def test_drop_and_cleanup_reject_libpq_routing_environment(
    postgres_namespace_factory,
    postgres_database_url: str,
    monkeypatch,
) -> None:
    factory = type(postgres_namespace_factory)(postgres_database_url, "routing")
    first = factory.create("first")
    second = factory.create("second")

    monkeypatch.setenv("PGHOSTADDR", "203.0.113.10")
    with pytest.raises(ValueError, match="PGHOSTADDR"):
        factory.drop(first)
    assert set(factory.tracked_schemas) == {first.schema, second.schema}

    with pytest.raises(ExceptionGroup) as captured:
        factory.cleanup()
    assert len(captured.value.exceptions) == 2
    assert set(factory.tracked_schemas) == {first.schema, second.schema}

    monkeypatch.delenv("PGHOSTADDR")
    factory.cleanup()
    assert not factory.tracked_schemas
    assert not _schema_exists(postgres_database_url, first.schema)
    assert not _schema_exists(postgres_database_url, second.schema)
