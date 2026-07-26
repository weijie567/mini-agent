from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import DropSchema

from mini_agent.infrastructure.persistence.database import (
    build_engine,
    database_url_from_environment,
)
from mini_agent.infrastructure.persistence.migrations import (
    upgrade_database_to_head,
)

_LABEL_PATTERN = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class PostgresTestNamespace:
    database_url: str
    schema: str

    def build_engine(self) -> Engine:
        return build_engine(self.database_url, schema=self.schema)


class PostgresNamespaceFactory:
    def __init__(self, database_url: str, worker_id: str) -> None:
        self.database_url = database_url
        self.worker_id = worker_id
        self._session_token = uuid4().hex[:10]
        self._counter = 0
        self._schemas: list[str] = []

    def create(self, eval_run_id: str = "worker") -> PostgresTestNamespace:
        self._counter += 1
        label = _LABEL_PATTERN.sub("_", eval_run_id.lower()).strip("_") or "run"
        identity = (
            f"{self.worker_id}:{self._session_token}:{self._counter}:{eval_run_id}"
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        schema = f"test_{label[:30]}_{self.worker_id[:8]}_{digest}"
        self._schemas.append(schema)
        upgrade_database_to_head(self.database_url, schema=schema)
        return PostgresTestNamespace(self.database_url, schema)

    def drop(self, namespace: PostgresTestNamespace) -> None:
        if namespace.schema not in self._schemas:
            return
        engine = create_engine(self.database_url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                connection.execute(
                    DropSchema(namespace.schema, cascade=True, if_exists=True)
                )
        finally:
            engine.dispose()
            self._schemas.remove(namespace.schema)

    def cleanup(self) -> None:
        if not self._schemas:
            return
        engine = create_engine(self.database_url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                for schema in reversed(self._schemas):
                    connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()
            self._schemas.clear()


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    database_url = database_url_from_environment(testing=True)
    if make_url(database_url).get_backend_name() != "postgresql":
        pytest.fail("integration tests require PostgreSQL; SQLite is not supported")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised only on environment failure
        pytest.fail(
            "PostgreSQL is unavailable; start it with `docker compose up -d db` "
            f"before running integration tests: {exc}"
        )
    finally:
        engine.dispose()
    return database_url


@pytest.fixture(scope="session")
def postgres_worker_id(request: pytest.FixtureRequest) -> str:
    worker_input = getattr(request.config, "workerinput", None)
    if isinstance(worker_input, dict):
        return str(worker_input.get("workerid", "worker"))
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


@pytest.fixture(scope="session")
def postgres_namespace_factory(
    postgres_database_url: str,
    postgres_worker_id: str,
) -> Iterator[PostgresNamespaceFactory]:
    factory = PostgresNamespaceFactory(postgres_database_url, postgres_worker_id)
    yield factory
    factory.cleanup()


@pytest.fixture(scope="session")
def postgres_namespace(
    postgres_namespace_factory: PostgresNamespaceFactory,
) -> PostgresTestNamespace:
    return postgres_namespace_factory.create("worker")


@pytest.fixture
def eval_postgres_namespace(
    postgres_namespace_factory: PostgresNamespaceFactory,
    request: pytest.FixtureRequest,
) -> Iterator[PostgresTestNamespace]:
    namespace = postgres_namespace_factory.create(request.node.nodeid)
    yield namespace
    postgres_namespace_factory.drop(namespace)
