from __future__ import annotations

import ast
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from mini_agent.application.persistence import (
    P0_RECORD_SCHEMA_VERSION_CATALOG,
    P0RecordCode,
)
from mini_agent.core.order import OrderStatus
from mini_agent.core.trace import AgentRunRecord, AgentRunStatus, AgentRunRecordV2
from mini_agent.infrastructure.persistence import models as persistence_models
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
    MockOrderSearchDocumentModel,
    MockOrderSearchSnapshotModel,
    MockShipmentModel,
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

_MIGRATION_REVISION = "20260728_0003"
_PREVIOUS_MIGRATION_REVISION = "20260727_0002"
_CYCLE2_MIGRATION_REVISION = "20260731_0004"
_CYCLE2_PREVIOUS_MIGRATION_REVISION = _MIGRATION_REVISION
_SEARCH_AUTHORITY_MIGRATION_REVISION = "20260802_0005"
_SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION = _CYCLE2_MIGRATION_REVISION
_SEARCH_AUTHORITY_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260802_0005_cycle2_search_authority_correction.py"
)
_CYCLE2_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260731_0004_cycle2_records_v2.py"
)
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260728_0003_request_understanding_v2_expand.py"
)
_MODELS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src/mini_agent/infrastructure/persistence/models.py"
)
_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade request understanding v2 physical schema while v2 records exist"
)
_CYCLE2_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade cycle2 physical schema after v2-only evidence"
)
_SEARCH_AUTHORITY_UPGRADE_BLOCKED_MESSAGE = (
    "cannot correct order search authority from invalid source rows"
)
_SEARCH_AUTHORITY_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade order search authority while durable evidence exists"
)
_ORDER_STATUS_VALUES = tuple(status.value for status in OrderStatus)
_V1_CODE_VERSION_PAIRS = (
    ("agent_run_record", "agent_run_record.p0.v1"),
    ("context_manifest_record", "context_manifest_record.p0.v1"),
    ("conversation_record", "conversation_record.p0.v1"),
    ("conversation_task_link_record", "conversation_task_link_record.p0.v1"),
    (
        "eval_execution_failure_record",
        "eval_execution_failure_record.p0.v1",
    ),
    ("eval_result_record", "eval_result_record.p0.v1"),
    ("gate_decision_record", "gate_decision_record.p0.v1"),
    ("input_binding_record", "input_binding_record.p0.v1"),
    ("message_record", "message_record.p0.v1"),
    (
        "model_visible_toolset_artifact",
        "model_visible_toolset_artifact.p0.v1",
    ),
    ("observation_record", "observation_record.p0.v1"),
    (
        "request_understanding_record",
        "request_understanding_record.p0.v1",
    ),
    ("request_unit_record", "request_unit_record.p0.v1"),
    ("run_task_link_record", "run_task_link_record.p0.v1"),
    ("task_record", "task_record.p0.v1"),
    ("tool_call_record", "tool_call_record.p0.v1"),
    ("trace_event_record", "trace_event_record.p0.v1"),
)
_EXPANDED_CODE_VERSION_PAIRS = (
    *_V1_CODE_VERSION_PAIRS,
    (
        "request_understanding_record",
        "request_understanding_record.p0.v2",
    ),
)
_CYCLE2_CODE_VERSION_PAIRS = (
    *_EXPANDED_CODE_VERSION_PAIRS,
    ("order_search_observation_record", "order_search_observation_record.p0.v1"),
    ("order_candidate_set_record", "order_candidate_set_record.p0.v1"),
    (
        "order_candidate_selection_record",
        "order_candidate_selection_record.p0.v1",
    ),
    ("shipment_observation_record", "shipment_observation_record.p0.v1"),
    ("shipment_assessment_record", "shipment_assessment_record.p0.v1"),
    ("input_binding_record", "input_binding_record.p0.v2"),
    ("gate_decision_record", "gate_decision_record.p0.v2"),
    ("tool_call_record", "tool_call_record.p0.v2"),
    ("agent_run_record", "agent_run_record.p0.v2"),
    ("run_task_link_record", "run_task_link_record.p0.v2"),
    ("trace_event_record", "trace_event_record.p0.v2"),
)
_REQUEST_UNDERSTANDING_V1_PAIR = (
    "request_understanding_record",
    "request_understanding_record.p0.v1",
)
_ACTIVE_CODE_VERSION_PAIRS = tuple(
    pair
    for pair in _CYCLE2_CODE_VERSION_PAIRS
    if pair != _REQUEST_UNDERSTANDING_V1_PAIR
)


def _search_snapshot_payload(
    *,
    customer_id: str = "customer-snapshot",
    candidate_count: int = 1,
    truncated: bool = False,
) -> dict[str, object]:
    return {
        "source_version_schema": ("mock-order-search-snapshot-source-version.p0.v1"),
        "owner_customer_id": customer_id,
        "normalized_query": "轻量跑鞋",
        "ordered_at_from": "2026-05-04T08:00:00.000000Z",
        "ordered_at_to": "2026-08-02T08:00:00.000000Z",
        "max_candidates": 5,
        "matching_rule_version": "order-search-matching.p0.v1",
        "ordered_candidates": [
            {
                "ordinal": ordinal,
                "owner_scoped_order_ref": f"order-ref-{ordinal}",
                "candidate_source_version": (
                    "mock-order-search-candidate-source-version.p0.v1:sha256:"
                    + f"{ordinal:064x}"
                ),
            }
            for ordinal in range(1, candidate_count + 1)
        ],
        "truncated": truncated,
    }


def _insert_legacy_search_authority(
    connection,
    *,
    customer_id: str,
    order_id: str,
    order_number: str | None = None,
    order_payload: object | None = None,
) -> None:
    search_order_number = order_number or order_id
    payload = (
        {"order_number": order_id, "status": OrderStatus.SHIPPED.value}
        if order_payload is None
        else order_payload
    )
    connection.execute(
        text(
            """
            INSERT INTO mock_orders (customer_id, order_id, order_payload)
            VALUES (:customer_id, :order_id, CAST(:order_payload AS jsonb))
            """
        ),
        {
            "customer_id": customer_id,
            "order_id": order_id,
            "order_payload": json.dumps(payload, separators=(",", ":")),
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO mock_order_search_documents (
                customer_id,
                order_id,
                line_ordinal,
                ordered_at,
                order_number,
                product_name,
                quantity,
                product_category,
                search_aliases
            ) VALUES (
                :customer_id,
                :order_id,
                1,
                :ordered_at,
                :order_number,
                'legacy search item',
                1,
                'legacy-category',
                CAST('["legacy"]' AS jsonb)
            )
            """
        ),
        {
            "customer_id": customer_id,
            "order_id": order_id,
            "ordered_at": datetime(2026, 7, 20, tzinfo=timezone.utc),
            "order_number": search_order_number,
        },
    )


def _module_literal(tree: ast.Module, name: str) -> object:
    matches = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        )
        or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        )
    ]
    assert len(matches) == 1
    match = matches[0]
    value = match.value
    assert value is not None
    return ast.literal_eval(value)


def _literal_pair_tuple(tree: ast.Module, name: str) -> tuple[tuple[str, str], ...]:
    matches = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        )
    ]
    assert len(matches) == 1
    value = matches[0].value
    assert isinstance(value, ast.Tuple)
    assert all(
        isinstance(pair, ast.Tuple)
        and len(pair.elts) == 2
        and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str)
            for item in pair.elts
        )
        for pair in value.elts
    )
    literal = ast.literal_eval(value)
    assert isinstance(literal, tuple)
    return literal


def _physical_probe_values(
    record_code: str,
    record_schema_version: str,
    *,
    record_id: UUID | None = None,
    marker: str = "physical-constraint-probe",
) -> dict[str, object]:
    probe_id = record_id or uuid4()
    return {
        "record_id": probe_id,
        "record_code": record_code,
        "record_schema_version": record_schema_version,
        "logical_identity": [["physical_probe_id", str(probe_id)]],
        "envelope": {"physical_probe": marker},
    }


def _insert_physical_probe(
    connection,
    record_code: str,
    record_schema_version: str,
    *,
    record_id: UUID | None = None,
    marker: str = "physical-constraint-probe",
) -> UUID:
    values = _physical_probe_values(
        record_code,
        record_schema_version,
        record_id=record_id,
        marker=marker,
    )
    connection.execute(P0RecordModel.__table__.insert().values(**values))
    stored_id = values["record_id"]
    assert isinstance(stored_id, UUID)
    return stored_id


def _insert_agent_run_envelope(
    connection,
    record: AgentRunRecord,
    *,
    scope_owner_customer_id: str,
) -> tuple[UUID, dict[str, object]]:
    logical_identity = [["run_id", str(record.run_id)]]
    raw_envelope: dict[str, object] = {
        "record_code": P0RecordCode.AGENT_RUN_RECORD.value,
        "record_schema_version": "agent_run_record.p0.v1",
        "logical_identity": logical_identity,
        "direct_owner_customer_id": None,
        "record_references": [],
        "payload": {
            "data": record.model_dump(mode="json", warnings="error"),
            "record_code": P0RecordCode.AGENT_RUN_RECORD.value,
            "record_schema_version": "agent_run_record.p0.v1",
            "logical_children": [],
        },
    }
    record_id = uuid4()
    connection.execute(
        P0RecordModel.__table__.insert().values(
            record_id=record_id,
            record_code=P0RecordCode.AGENT_RUN_RECORD.value,
            record_schema_version="agent_run_record.p0.v1",
            logical_identity=logical_identity,
            direct_owner_customer_id=None,
            scope_owner_customer_id=scope_owner_customer_id,
            conversation_id=record.conversation_id,
            run_id=record.run_id,
            lifecycle_status=record.status.value,
            recovery_sort_at=record.started_at,
            envelope=raw_envelope,
        )
    )
    return record_id, raw_envelope


def _record_row(engine: Engine, record_id: UUID) -> dict[str, object]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(P0RecordModel.__table__).where(
                    P0RecordModel.record_id == record_id
                )
            )
            .mappings()
            .one()
        )
        return dict(row)


def _migration_revision(engine: Engine) -> str:
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert isinstance(revision, str)
    return revision


def _schema_structure(engine: Engine) -> tuple[object, ...]:
    inspector = inspect(engine)
    tables = tuple(sorted(inspector.get_table_names()))
    table_details: list[tuple[object, ...]] = []
    for table_name in tables:
        columns = tuple(
            sorted(
                (
                    column["name"],
                    str(column["type"]),
                    bool(column["nullable"]),
                    str(column.get("default")),
                )
                for column in inspector.get_columns(table_name)
            )
        )
        checks = tuple(
            sorted(item["name"] for item in inspector.get_check_constraints(table_name))
        )
        indexes = tuple(
            sorted(
                (
                    item["name"],
                    tuple(item["column_names"]),
                    bool(item["unique"]),
                )
                for item in inspector.get_indexes(table_name)
                if not item.get("duplicates_constraint")
            )
        )
        uniques = tuple(
            sorted(
                (
                    item["name"],
                    tuple(item["column_names"]),
                )
                for item in inspector.get_unique_constraints(table_name)
            )
        )
        foreign_keys = tuple(
            sorted(
                (
                    item["name"],
                    tuple(item["constrained_columns"]),
                    item["referred_table"],
                    tuple(item["referred_columns"]),
                    tuple(sorted(item["options"].items())),
                )
                for item in inspector.get_foreign_keys(table_name)
            )
        )
        primary_key = tuple(
            inspector.get_pk_constraint(table_name)["constrained_columns"]
        )
        table_details.append(
            (
                table_name,
                columns,
                checks,
                indexes,
                uniques,
                foreign_keys,
                primary_key,
            )
        )
    return tables, tuple(table_details)


def _record_check_definitions(engine: Engine) -> dict[str, str]:
    return {
        item["name"]: item["sqltext"]
        for item in inspect(engine).get_check_constraints("p0_records")
    }


def _assert_lock_timeout(
    engine: Engine,
    statement,
    *,
    parameters: dict[str, object] | None = None,
) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL lock_timeout = '500ms'"))
            with pytest.raises(OperationalError) as captured:
                connection.execute(statement, parameters or {})
            assert getattr(captured.value.orig, "sqlstate", None) == "55P03"
        finally:
            transaction.rollback()


def _wait_for_real_downgrade_lock(
    engine: Engine,
    *,
    schema: str,
    relation_name: str = "p0_records",
    timeout_seconds: float = 5.0,
) -> None:
    lock_observed = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_locks AS held
            JOIN pg_class AS relation
              ON relation.oid = held.relation
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = :schema
              AND relation.relname = :relation_name
              AND held.mode = 'ShareRowExclusiveLock'
              AND held.granted
              AND EXISTS (
                  SELECT 1
                  FROM pg_locks AS waiting
                  WHERE waiting.pid = held.pid
                    AND waiting.relation = held.relation
                    AND waiting.mode = 'AccessExclusiveLock'
                    AND NOT waiting.granted
              )
        )
        """
    )
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        with engine.connect() as connection:
            if (
                connection.scalar(
                    lock_observed,
                    {"schema": schema, "relation_name": relation_name},
                )
                is True
            ):
                return
        sleep(0.01)
    pytest.fail(
        "real downgrade did not hold ShareRowExclusiveLock "
        f"on {relation_name} while waiting for destructive DDL"
    )


def _wait_for_pending_table_lock(
    engine: Engine,
    *,
    schema: str,
    relation_name: str,
    mode: str,
    timeout_seconds: float = 5.0,
) -> None:
    pending_lock = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_locks AS waiting
            JOIN pg_class AS relation
              ON relation.oid = waiting.relation
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = :schema
              AND relation.relname = :relation_name
              AND waiting.mode = :mode
              AND NOT waiting.granted
        )
        """
    )
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        with engine.connect() as connection:
            if (
                connection.scalar(
                    pending_lock,
                    {
                        "schema": schema,
                        "relation_name": relation_name,
                        "mode": mode,
                    },
                )
                is True
            ):
                return
        sleep(0.01)
    pytest.fail(f"downgrade did not wait for {mode} on {relation_name}")


def test_request_understanding_v2_expand_migration_source_is_self_contained() -> None:
    assert _MIGRATION_PATH.is_file()
    source = _MIGRATION_PATH.read_text()
    tree = ast.parse(source)

    imports: set[tuple[str, tuple[tuple[str, str | None], ...]]] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.add(
                (
                    "",
                    tuple((item.name, item.asname) for item in node.names),
                )
            )
        elif isinstance(node, ast.ImportFrom):
            imports.add(
                (
                    node.module or "",
                    tuple((item.name, item.asname) for item in node.names),
                )
            )
    assert imports == {
        ("__future__", (("annotations", None),)),
        ("collections.abc", (("Sequence", None),)),
        ("", (("sqlalchemy", "sa"),)),
        ("alembic", (("op", None),)),
    }
    assert "mini_agent" not in source
    assert not any(
        isinstance(
            node,
            (
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        )
        for node in ast.walk(tree)
    )

    assert _module_literal(tree, "revision") == _MIGRATION_REVISION
    assert _module_literal(tree, "down_revision") == _PREVIOUS_MIGRATION_REVISION
    assert _module_literal(tree, "branch_labels") is None
    assert _module_literal(tree, "depends_on") is None
    assert _literal_pair_tuple(tree, "_V1_CODE_VERSION_PAIRS") == (
        _V1_CODE_VERSION_PAIRS
    )
    assert _literal_pair_tuple(tree, "_EXPANDED_CODE_VERSION_PAIRS") == (
        _EXPANDED_CODE_VERSION_PAIRS
    )

    op_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        )
    }
    assert op_calls == {
        "create_check_constraint",
        "drop_constraint",
        "get_bind",
    }

    downgrade_matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    ]
    assert len(downgrade_matches) == 1
    downgrade_source = ast.get_source_segment(source, downgrade_matches[0])
    assert downgrade_source is not None

    class _NormalizeStringWhitespace(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.Constant:
            if isinstance(node.value, str):
                return ast.copy_location(
                    ast.Constant(value=" ".join(node.value.split())),
                    node,
                )
            return node

    expected_downgrade = ast.parse(
        """
def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("LOCK TABLE p0_records IN SHARE ROW EXCLUSIVE MODE")
    )
    has_v2_records = connection.scalar(
        sa.text(
            "SELECT EXISTS ( "
            "SELECT 1 FROM p0_records "
            "WHERE record_code = 'request_understanding_record' "
            "AND record_schema_version = "
            "'request_understanding_record.p0.v2'"
            " )"
        )
    )
    if has_v2_records is not False:
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
    _replace_code_version_constraint(_V1_CODE_VERSION_PAIRS)
"""
    )
    actual_downgrade = ast.parse(downgrade_source)
    normalizer = _NormalizeStringWhitespace()
    assert ast.dump(
        normalizer.visit(actual_downgrade),
        include_attributes=False,
    ) == ast.dump(
        normalizer.visit(expected_downgrade),
        include_attributes=False,
    )
    assert _DOWNGRADE_BLOCKED_MESSAGE in source
    assert "SELECT COUNT" not in source.upper()
    assert "UPDATE p0_records" not in source
    assert "DELETE FROM p0_records" not in source


def test_request_understanding_v2_expand_is_single_linear_alembic_head() -> None:
    script = ScriptDirectory.from_config(
        alembic_config(
            DEFAULT_LOCAL_TEST_DATABASE_URL,
            testing=True,
        )
    )

    assert tuple(script.get_heads()) == (_SEARCH_AUTHORITY_MIGRATION_REVISION,)
    revision = script.get_revision(_MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == _PREVIOUS_MIGRATION_REVISION


def test_cycle2_physical_revision_is_single_linear_alembic_head() -> None:
    assert _CYCLE2_MIGRATION_PATH.is_file()
    script = ScriptDirectory.from_config(
        alembic_config(DEFAULT_LOCAL_TEST_DATABASE_URL, testing=True)
    )

    revision = script.get_revision(_CYCLE2_MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == _CYCLE2_PREVIOUS_MIGRATION_REVISION
    assert tuple(script.get_heads()) == (_SEARCH_AUTHORITY_MIGRATION_REVISION,)


def test_search_authority_correction_is_single_linear_alembic_head() -> None:
    assert _SEARCH_AUTHORITY_MIGRATION_PATH.is_file()
    script = ScriptDirectory.from_config(
        alembic_config(DEFAULT_LOCAL_TEST_DATABASE_URL, testing=True)
    )

    revision = script.get_revision(_SEARCH_AUTHORITY_MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION
    assert tuple(script.get_heads()) == (_SEARCH_AUTHORITY_MIGRATION_REVISION,)


def test_search_authority_correction_source_is_self_contained_and_frozen() -> None:
    source = _SEARCH_AUTHORITY_MIGRATION_PATH.read_text()
    tree = ast.parse(source)

    assert "mini_agent" not in source
    assert _module_literal(tree, "revision") == _SEARCH_AUTHORITY_MIGRATION_REVISION
    assert _module_literal(tree, "down_revision") == (
        _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION
    )
    assert _module_literal(tree, "branch_labels") is None
    assert _module_literal(tree, "depends_on") is None
    assert _module_literal(tree, "_ORDER_STATUS_VALUES") == _ORDER_STATUS_VALUES
    assert _module_literal(tree, "_ORDER_STATUS_CHECK") == (
        "status IN ('CREATED', 'PAID', 'FULFILLING', 'SHIPPED', "
        "'DELIVERED', 'CANCELLED')"
    )
    assert _SEARCH_AUTHORITY_UPGRADE_BLOCKED_MESSAGE in source
    assert _SEARCH_AUTHORITY_DOWNGRADE_BLOCKED_MESSAGE in source
    assert "server_default" not in source


def test_phase1_head_upgrade_converts_exact_v1_record_and_downgrades_losslessly(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("cycle2-convert-round-trip")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    source = AgentRunRecord(
        run_id=uuid4(),
        status=AgentRunStatus.CREATED,
        provider_lane="migration-test-provider",
        started_at=datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc),
    )
    try:
        command.downgrade(config, _CYCLE2_PREVIOUS_MIGRATION_REVISION)
        with engine.begin() as connection:
            record_id, original_envelope = _insert_agent_run_envelope(
                connection,
                source,
                scope_owner_customer_id="customer-migration",
            )

        command.upgrade(config, _CYCLE2_MIGRATION_REVISION)
        converted = _record_row(engine, record_id)
        assert converted["record_schema_version"] == "agent_run_record.p0.v2"
        converted_record = AgentRunRecordV2.model_validate(
            converted["envelope"]["payload"]["data"]
        )
        assert converted_record.run_id == source.run_id
        assert converted["scope_owner_customer_id"] == "customer-migration"

        command.downgrade(config, _CYCLE2_PREVIOUS_MIGRATION_REVISION)
        restored = _record_row(engine, record_id)
        assert restored["record_schema_version"] == "agent_run_record.p0.v1"
        assert restored["envelope"] == original_envelope
        assert restored["scope_owner_customer_id"] == "customer-migration"
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_cycle2_upgrade_prevalidates_whole_set_before_any_v2_write(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("cycle2-atomic-prevalidation")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    source = AgentRunRecord(
        run_id=uuid4(),
        status=AgentRunStatus.CREATED,
        provider_lane="atomicity-test-provider",
        started_at=datetime(2026, 7, 31, 8, 1, tzinfo=timezone.utc),
    )
    try:
        command.downgrade(config, _CYCLE2_PREVIOUS_MIGRATION_REVISION)
        with engine.begin() as connection:
            record_id, original_envelope = _insert_agent_run_envelope(
                connection,
                source,
                scope_owner_customer_id="customer-atomicity",
            )
            invalid_id = _insert_physical_probe(
                connection,
                "gate_decision_record",
                "gate_decision_record.p0.v1",
                marker="must-not-leak-from-invalid-graph",
            )

        with pytest.raises(RuntimeError) as captured:
            command.upgrade(config, _CYCLE2_MIGRATION_REVISION)

        assert str(captured.value) == (
            "cycle2 record migration graph is not exactly convertible"
        )
        assert "must-not-leak-from-invalid-graph" not in str(captured.value)
        assert _migration_revision(engine) == _CYCLE2_PREVIOUS_MIGRATION_REVISION
        unchanged = _record_row(engine, record_id)
        assert unchanged["record_schema_version"] == "agent_run_record.p0.v1"
        assert unchanged["envelope"] == original_envelope
        assert _record_row(engine, invalid_id)["record_schema_version"] == (
            "gate_decision_record.p0.v1"
        )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_cycle2_downgrade_blocks_new_top_level_evidence_before_mutation(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("cycle2-downgrade-fence")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        with engine.begin() as connection:
            record_id = _insert_physical_probe(
                connection,
                "shipment_assessment_record",
                "shipment_assessment_record.p0.v1",
                marker="must-not-leak-from-v2-only-evidence",
            )
        before = _record_row(engine, record_id)

        with pytest.raises(RuntimeError) as captured:
            command.downgrade(config, _CYCLE2_PREVIOUS_MIGRATION_REVISION)

        assert str(captured.value) == _CYCLE2_DOWNGRADE_BLOCKED_MESSAGE
        assert "must-not-leak-from-v2-only-evidence" not in str(captured.value)
        assert _migration_revision(engine) == _SEARCH_AUTHORITY_MIGRATION_REVISION
        assert _record_row(engine, record_id) == before
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_empty_and_phase1_head_upgrade_paths_converge_to_exact_structure(
    postgres_namespace_factory,
) -> None:
    empty_path = postgres_namespace_factory.create("cycle2-empty-path")
    phase1_path = postgres_namespace_factory.create("cycle2-phase1-path")
    empty_engine = empty_path.build_engine()
    phase1_engine = phase1_path.build_engine()
    phase1_config = alembic_config(
        phase1_path.database_url,
        schema=phase1_path.schema,
        testing=True,
    )
    try:
        empty_structure = _schema_structure(empty_engine)
        command.downgrade(
            phase1_config,
            _CYCLE2_PREVIOUS_MIGRATION_REVISION,
        )
        command.upgrade(phase1_config, _SEARCH_AUTHORITY_MIGRATION_REVISION)

        assert _migration_revision(empty_engine) == (
            _SEARCH_AUTHORITY_MIGRATION_REVISION
        )
        assert _migration_revision(phase1_engine) == (
            _SEARCH_AUTHORITY_MIGRATION_REVISION
        )
        assert _schema_structure(phase1_engine) == empty_structure
    finally:
        empty_engine.dispose()
        phase1_engine.dispose()
        postgres_namespace_factory.drop(empty_path)
        postgres_namespace_factory.drop(phase1_path)


def test_search_authority_upgrade_backfills_status_and_preserves_order_payload_bytes(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("search-authority-backfill")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    payload = {
        "order_number": "O-8101",
        "status": OrderStatus.SHIPPED.value,
        "line_items": [{"product_name": "legacy search item", "quantity": 1}],
        "ordered_at": "2026-07-20T00:00:00Z",
        "status_updated_at": "2026-07-21T00:00:00Z",
    }
    try:
        command.downgrade(config, _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION)
        with engine.begin() as connection:
            _insert_legacy_search_authority(
                connection,
                customer_id="customer-backfill",
                order_id="O-8101",
                order_payload=payload,
            )
        with engine.connect() as connection:
            before_bytes = connection.scalar(
                text(
                    "SELECT convert_to(order_payload::text, 'UTF8') "
                    "FROM mock_orders WHERE customer_id = :customer_id "
                    "AND order_id = :order_id"
                ),
                {"customer_id": "customer-backfill", "order_id": "O-8101"},
            )

        command.upgrade(config, _SEARCH_AUTHORITY_MIGRATION_REVISION)

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT status FROM mock_order_search_documents "
                    "WHERE customer_id = :customer_id AND order_id = :order_id"
                ),
                {"customer_id": "customer-backfill", "order_id": "O-8101"},
            ).one()
            after_bytes = connection.scalar(
                text(
                    "SELECT convert_to(order_payload::text, 'UTF8') "
                    "FROM mock_orders WHERE customer_id = :customer_id "
                    "AND order_id = :order_id"
                ),
                {"customer_id": "customer-backfill", "order_id": "O-8101"},
            )
        assert row.status == OrderStatus.SHIPPED.value
        assert after_bytes == before_bytes
        assert _migration_revision(engine) == _SEARCH_AUTHORITY_MIGRATION_REVISION
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize(
    ("order_payload", "search_order_number"),
    (
        ({"order_number": "O-8201"}, "O-8201"),
        ({"order_number": "O-8201", "status": None}, "O-8201"),
        ({"order_number": "O-8201", "status": 3}, "O-8201"),
        ({"order_number": "O-8201", "status": "UNKNOWN"}, "O-8201"),
        ({"order_number": "O-9999", "status": "SHIPPED"}, "O-8201"),
        ({"order_number": "O-8201", "status": "SHIPPED"}, "O-9999"),
        (["not-an-object"], "O-8201"),
    ),
)
def test_search_authority_upgrade_rejects_invalid_source_atomically(
    postgres_namespace_factory,
    order_payload: object,
    search_order_number: str,
) -> None:
    namespace = postgres_namespace_factory.create("search-authority-invalid-source")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        command.downgrade(config, _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION)
        with engine.begin() as connection:
            _insert_legacy_search_authority(
                connection,
                customer_id="customer-invalid",
                order_id="O-8201",
                order_number=search_order_number,
                order_payload=order_payload,
            )
            original_payload = connection.scalar(
                text(
                    "SELECT order_payload FROM mock_orders "
                    "WHERE customer_id = 'customer-invalid'"
                )
            )

        with pytest.raises(RuntimeError) as captured:
            command.upgrade(config, _SEARCH_AUTHORITY_MIGRATION_REVISION)

        assert str(captured.value) == _SEARCH_AUTHORITY_UPGRADE_BLOCKED_MESSAGE
        assert _migration_revision(engine) == (
            _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION
        )
        inspector = inspect(engine)
        assert "status" not in {
            column["name"]
            for column in inspector.get_columns("mock_order_search_documents")
        }
        assert "mock_order_search_snapshots" not in inspector.get_table_names()
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT order_payload FROM mock_orders "
                        "WHERE customer_id = 'customer-invalid'"
                    )
                )
                == original_payload
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM mock_order_search_documents")
                )
                == 1
            )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_search_status_constraint_is_exact_closed_core_enum(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    ordered_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    try:
        assert persistence_models._ORDER_STATUS_VALUES == _ORDER_STATUS_VALUES
        with engine.begin() as connection:
            connection.execute(
                MockOrderModel.__table__.insert().values(
                    customer_id="customer-status",
                    order_id="O-8301",
                    order_payload={
                        "order_number": "O-8301",
                        "status": OrderStatus.CREATED.value,
                    },
                )
            )
            for ordinal, status in enumerate(_ORDER_STATUS_VALUES, start=1):
                connection.execute(
                    MockOrderSearchDocumentModel.__table__.insert().values(
                        customer_id="customer-status",
                        order_id="O-8301",
                        line_ordinal=ordinal,
                        ordered_at=ordered_at,
                        order_number="O-8301",
                        status=status,
                        product_name=f"status-{status}",
                        quantity=1,
                        product_category="status-test",
                        search_aliases=[],
                    )
                )

        with engine.connect() as connection:
            assert (
                tuple(
                    connection.scalars(
                        select(MockOrderSearchDocumentModel.status).order_by(
                            MockOrderSearchDocumentModel.line_ordinal
                        )
                    )
                )
                == _ORDER_STATUS_VALUES
            )

        for line_ordinal, invalid_status in ((10, None), (11, "UNKNOWN"), (12, 3)):
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        MockOrderSearchDocumentModel.__table__.insert().values(
                            customer_id="customer-status",
                            order_id="O-8301",
                            line_ordinal=line_ordinal,
                            ordered_at=ordered_at,
                            order_number="O-8301",
                            status=invalid_status,
                            product_name="invalid-status",
                            quantity=1,
                            product_category="status-test",
                            search_aliases=[],
                        )
                    )
    finally:
        engine.dispose()


def test_raw_search_snapshot_is_owner_scoped_and_canonical_shape_only(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    snapshot_ref = uuid4()
    five_candidate_ref = uuid4()
    observed_at = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    payload = _search_snapshot_payload()
    five_candidate_payload = _search_snapshot_payload(
        candidate_count=5,
        truncated=True,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                MockOrderSearchSnapshotModel.__table__.insert().values(
                    snapshot_resource_ref=snapshot_ref,
                    customer_id="customer-snapshot",
                    observed_at=observed_at,
                    snapshot_payload=payload,
                )
            )
            connection.execute(
                MockOrderSearchSnapshotModel.__table__.insert().values(
                    snapshot_resource_ref=five_candidate_ref,
                    customer_id="customer-snapshot",
                    observed_at=observed_at,
                    snapshot_payload=five_candidate_payload,
                )
            )

        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(MockOrderSearchSnapshotModel.snapshot_payload).where(
                        MockOrderSearchSnapshotModel.customer_id == "customer-snapshot",
                        MockOrderSearchSnapshotModel.snapshot_resource_ref
                        == snapshot_ref,
                    )
                )
                == payload
            )
            assert (
                connection.scalar(
                    select(MockOrderSearchSnapshotModel.snapshot_resource_ref).where(
                        MockOrderSearchSnapshotModel.customer_id == "customer-foreign",
                        MockOrderSearchSnapshotModel.snapshot_resource_ref
                        == snapshot_ref,
                    )
                )
                is None
            )
            assert (
                connection.scalar(
                    select(func.count()).select_from(MockOrderSearchSnapshotModel)
                )
                == 2
            )

        invalid_payloads: list[dict[str, object]] = []
        extra_top_level = _search_snapshot_payload()
        extra_top_level["private_raw"] = "forbidden"
        invalid_payloads.append(extra_top_level)
        wrong_owner = _search_snapshot_payload(customer_id="customer-foreign")
        invalid_payloads.append(wrong_owner)
        truncated_too_early = _search_snapshot_payload(truncated=True)
        invalid_payloads.append(truncated_too_early)
        float_max_candidates = _search_snapshot_payload()
        float_max_candidates["max_candidates"] = 5.0
        invalid_payloads.append(float_max_candidates)
        for candidate_update in (
            {"ordinal": 2},
            {"owner_scoped_order_ref": ""},
            {"candidate_source_version": "invalid-token"},
            {"extra": "forbidden"},
        ):
            nested_invalid = _search_snapshot_payload()
            candidate = nested_invalid["ordered_candidates"][0]
            assert isinstance(candidate, dict)
            candidate.update(candidate_update)
            invalid_payloads.append(nested_invalid)
        float_ordinal = _search_snapshot_payload()
        candidate = float_ordinal["ordered_candidates"][0]
        assert isinstance(candidate, dict)
        candidate["ordinal"] = 1.0
        invalid_payloads.append(float_ordinal)
        second_ordinal_drift = _search_snapshot_payload(
            candidate_count=5,
            truncated=True,
        )
        candidate = second_ordinal_drift["ordered_candidates"][1]
        assert isinstance(candidate, dict)
        candidate["ordinal"] = 3
        invalid_payloads.append(second_ordinal_drift)
        non_object_candidate = _search_snapshot_payload()
        candidates = non_object_candidate["ordered_candidates"]
        assert isinstance(candidates, list)
        candidates[0] = "not-an-object"
        invalid_payloads.append(non_object_candidate)
        missing_candidate_key = _search_snapshot_payload()
        candidate = missing_candidate_key["ordered_candidates"][0]
        assert isinstance(candidate, dict)
        candidate.pop("candidate_source_version")
        invalid_payloads.append(missing_candidate_key)

        for invalid_payload in invalid_payloads:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        MockOrderSearchSnapshotModel.__table__.insert().values(
                            snapshot_resource_ref=uuid4(),
                            customer_id="customer-snapshot",
                            observed_at=observed_at,
                            snapshot_payload=invalid_payload,
                        )
                    )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    MockOrderSearchSnapshotModel.__table__.insert().values(
                        snapshot_resource_ref=snapshot_ref,
                        customer_id="customer-snapshot",
                        observed_at=observed_at,
                        snapshot_payload=payload,
                    )
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize("evidence_kind", ("search-document", "raw-snapshot"))
def test_search_authority_downgrade_blocks_durable_evidence_before_mutation(
    postgres_namespace_factory,
    evidence_kind: str,
) -> None:
    namespace = postgres_namespace_factory.create(
        f"search-authority-downgrade-{evidence_kind}"
    )
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    marker = f"must-not-leak-{evidence_kind}"
    try:
        with engine.begin() as connection:
            if evidence_kind == "search-document":
                connection.execute(
                    MockOrderModel.__table__.insert().values(
                        customer_id="customer-downgrade",
                        order_id="O-8401",
                        order_payload={
                            "order_number": "O-8401",
                            "status": OrderStatus.SHIPPED.value,
                        },
                    )
                )
                connection.execute(
                    MockOrderSearchDocumentModel.__table__.insert().values(
                        customer_id="customer-downgrade",
                        order_id="O-8401",
                        line_ordinal=1,
                        ordered_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                        order_number="O-8401",
                        status=OrderStatus.SHIPPED.value,
                        product_name=marker,
                        quantity=1,
                        product_category="downgrade-test",
                        search_aliases=[],
                    )
                )
            else:
                connection.execute(
                    MockOrderSearchSnapshotModel.__table__.insert().values(
                        snapshot_resource_ref=uuid4(),
                        customer_id="customer-snapshot",
                        observed_at=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
                        snapshot_payload=_search_snapshot_payload(),
                    )
                )

        with pytest.raises(RuntimeError) as captured:
            command.downgrade(
                config,
                _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION,
            )

        assert str(captured.value) == _SEARCH_AUTHORITY_DOWNGRADE_BLOCKED_MESSAGE
        assert marker not in str(captured.value)
        assert _migration_revision(engine) == _SEARCH_AUTHORITY_MIGRATION_REVISION
        inspector = inspect(engine)
        assert "mock_order_search_snapshots" in inspector.get_table_names()
        assert "status" in {
            column["name"]
            for column in inspector.get_columns("mock_order_search_documents")
        }
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_empty_search_authority_downgrade_is_reversible_and_preserves_orders(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("search-authority-empty-downgrade")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                MockOrderModel.__table__.insert().values(
                    customer_id="customer-order-only",
                    order_id="O-8501",
                    order_payload={"order_number": "O-8501", "status": "PAID"},
                )
            )

        command.downgrade(config, _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION)

        inspector = inspect(engine)
        assert "mock_order_search_snapshots" not in inspector.get_table_names()
        assert "status" not in {
            column["name"]
            for column in inspector.get_columns("mock_order_search_documents")
        }
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM mock_orders "
                        "WHERE customer_id = 'customer-order-only'"
                    )
                )
                == 1
            )

        command.upgrade(config, _SEARCH_AUTHORITY_MIGRATION_REVISION)
        assert _migration_revision(engine) == _SEARCH_AUTHORITY_MIGRATION_REVISION
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_search_authority_downgrade_lock_blocks_snapshot_dml(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("search-authority-lock-contract")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    barrier_connection = engine.connect()
    barrier_transaction = barrier_connection.begin()
    executor = ThreadPoolExecutor(max_workers=1)
    downgrade_future = None
    try:
        assert (
            barrier_connection.scalar(
                text("SELECT count(*) FROM mock_order_search_snapshots")
            )
            == 0
        )
        downgrade_future = executor.submit(
            command.downgrade,
            config,
            _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION,
        )
        _wait_for_real_downgrade_lock(
            engine,
            schema=namespace.schema,
            relation_name="mock_order_search_snapshots",
        )

        _assert_lock_timeout(
            engine,
            MockOrderSearchSnapshotModel.__table__.insert().values(
                snapshot_resource_ref=uuid4(),
                customer_id="customer-lock",
                observed_at=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
                snapshot_payload=_search_snapshot_payload(customer_id="customer-lock"),
            ),
        )
        _assert_lock_timeout(
            engine,
            MockOrderSearchSnapshotModel.__table__.update().values(
                observed_at=datetime(2026, 8, 2, 8, 1, tzinfo=timezone.utc)
            ),
        )
    finally:
        barrier_transaction.rollback()
        barrier_connection.close()
        executor.shutdown(wait=True)

    try:
        assert downgrade_future is not None
        assert downgrade_future.result(timeout=10) is None
        assert _migration_revision(engine) == (
            _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION
        )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_search_authority_downgrade_waits_for_prior_snapshot_then_fails_bounded(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("search-authority-prior-snapshot")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    marker = "must-not-leak-prior-search-snapshot"
    writer_connection = engine.connect()
    writer_transaction = writer_connection.begin()
    executor = ThreadPoolExecutor(max_workers=1)
    downgrade_future = None
    snapshot_ref = uuid4()
    try:
        payload = _search_snapshot_payload()
        payload["normalized_query"] = marker
        writer_connection.execute(
            MockOrderSearchSnapshotModel.__table__.insert().values(
                snapshot_resource_ref=snapshot_ref,
                customer_id="customer-snapshot",
                observed_at=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
                snapshot_payload=payload,
            )
        )

        downgrade_future = executor.submit(
            command.downgrade,
            config,
            _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION,
        )
        _wait_for_pending_table_lock(
            engine,
            schema=namespace.schema,
            relation_name="mock_order_search_snapshots",
            mode="ShareRowExclusiveLock",
        )

        writer_transaction.commit()
        writer_connection.close()
        writer_transaction = None
        writer_connection = None

        with pytest.raises(RuntimeError) as captured:
            downgrade_future.result(timeout=10)
        assert str(captured.value) == _SEARCH_AUTHORITY_DOWNGRADE_BLOCKED_MESSAGE
        assert marker not in str(captured.value)
        assert _migration_revision(engine) == _SEARCH_AUTHORITY_MIGRATION_REVISION
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(MockOrderSearchSnapshotModel.snapshot_resource_ref).where(
                        MockOrderSearchSnapshotModel.snapshot_resource_ref
                        == snapshot_ref
                    )
                )
                == snapshot_ref
            )
    finally:
        if writer_transaction is not None:
            writer_transaction.rollback()
        if writer_connection is not None:
            writer_connection.close()
        executor.shutdown(wait=True)
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


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
            "mock_order_search_documents",
            "mock_order_search_snapshots",
            "mock_orders",
            "mock_shipments",
            "p0_record_references",
            "p0_records",
        }
        assert set(Base.metadata.tables) == {
            "mock_order_search_documents",
            "mock_order_search_snapshots",
            "mock_orders",
            "mock_shipments",
            "p0_record_references",
            "p0_records",
        }
        assert P0RecordModel.__tablename__ == "p0_records"
        assert P0RecordReferenceModel.__tablename__ == "p0_record_references"
        assert MockOrderModel.__tablename__ == "mock_orders"
        assert MockOrderSearchDocumentModel.__tablename__ == (
            "mock_order_search_documents"
        )
        assert MockOrderSearchSnapshotModel.__tablename__ == (
            "mock_order_search_snapshots"
        )
        assert MockShipmentModel.__tablename__ == "mock_shipments"

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == (
                postgres_namespace.schema
            )
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == (_SEARCH_AUTHORITY_MIGRATION_REVISION)
    finally:
        engine.dispose()


def test_sqlalchemy_metadata_owns_exact_expanded_physical_pair_set() -> None:
    models_source = _MODELS_PATH.read_text()
    models_tree = ast.parse(models_source)
    application_catalog_name = "P0_RECORD_SCHEMA_VERSION_CATALOG"

    def folded_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = folded_string(node.left)
            right = folded_string(node.right)
            return left + right if left is not None and right is not None else None
        return None

    def import_roots(tree: ast.AST) -> set[str]:
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(
                    alias.name.split(".", maxsplit=1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                roots.add(node.module.split(".", maxsplit=1)[0])
        return roots

    application_imports = [
        node
        for node in ast.walk(models_tree)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("mini_agent.application")
        )
        or (
            isinstance(node, ast.Import)
            and any(
                alias.name.startswith("mini_agent.application") for alias in node.names
            )
        )
    ]
    assert len(application_imports) == 1
    application_import = application_imports[0]
    assert isinstance(application_import, ast.ImportFrom)
    assert application_import.module == "mini_agent.application.persistence"
    assert [(alias.name, alias.asname) for alias in application_import.names] == [
        ("P0RecordCode", None)
    ]

    assert not any(
        (
            isinstance(node, ast.ImportFrom)
            and node.module == "mini_agent.application.persistence"
            and any(alias.name == application_catalog_name for alias in node.names)
        )
        or (isinstance(node, ast.Name) and node.id == application_catalog_name)
        or (isinstance(node, ast.Attribute) and node.attr == application_catalog_name)
        or (folded_string(node) == application_catalog_name)
        for node in ast.walk(models_tree)
    )
    assert not {
        node.id
        for node in ast.walk(models_tree)
        if isinstance(node, ast.Name)
        and node.id
        in {
            "__import__",
            "eval",
            "exec",
            "getattr",
            "globals",
            "locals",
            "vars",
        }
    }
    assert not {
        node.attr
        for node in ast.walk(models_tree)
        if isinstance(node, ast.Attribute)
        and node.attr
        in {
            "__dict__",
            "__globals__",
            "__module__",
            "__subclasses__",
            "import_module",
        }
    }
    unsafe_import_roots = {"builtins", "importlib", "sys"}
    assert not import_roots(models_tree) & unsafe_import_roots
    adversarial_imports = ast.parse(
        "from importlib import import_module as load_module\n"
        "from builtins import vars as namespace\n"
    )
    assert import_roots(adversarial_imports) & unsafe_import_roots == {
        "builtins",
        "importlib",
    }

    physical_literal = _literal_pair_tuple(
        models_tree,
        "_PHYSICAL_CODE_VERSION_PAIRS",
    )
    assert physical_literal == _CYCLE2_CODE_VERSION_PAIRS
    assert len(physical_literal) == len(set(physical_literal)) == 29

    code_version_assignments = [
        node
        for node in models_tree.body
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_CODE_VERSION_PAIRS"
        )
    ]
    assert len(code_version_assignments) == 1
    expected_derivation = ast.parse(
        "tuple(sorted(_PHYSICAL_CODE_VERSION_PAIRS))",
        mode="eval",
    ).body
    assert ast.dump(
        code_version_assignments[0].value,
        include_attributes=False,
    ) == ast.dump(expected_derivation, include_attributes=False)

    assert len(persistence_models._RECORD_CODES) == 22
    assert set(persistence_models._RECORD_CODES) == {
        code for code, _ in _CYCLE2_CODE_VERSION_PAIRS
    }
    physical_pairs = persistence_models._CODE_VERSION_PAIRS
    assert physical_pairs == tuple(sorted(_CYCLE2_CODE_VERSION_PAIRS))

    catalog_pairs = tuple(
        sorted(
            (code.value, schema_version)
            for code, schema_version in P0_RECORD_SCHEMA_VERSION_CATALOG
        )
    )
    active_pairs = tuple(sorted(_ACTIVE_CODE_VERSION_PAIRS))
    request_understanding_v1_pair = {_REQUEST_UNDERSTANDING_V1_PAIR}

    assert catalog_pairs in {active_pairs, physical_pairs}
    assert set(active_pairs) < set(physical_pairs)
    assert set(physical_pairs) - set(active_pairs) == (request_understanding_v1_pair)
    assert frozenset(set(physical_pairs) - set(catalog_pairs)) in {
        frozenset(),
        frozenset(request_understanding_v1_pair),
    }


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
            column["name"] for column in inspector.get_columns("p0_record_references")
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
        assert {
            column["name"]
            for column in inspector.get_columns("mock_order_search_documents")
        } == {
            "customer_id",
            "order_id",
            "line_ordinal",
            "ordered_at",
            "order_number",
            "status",
            "product_name",
            "quantity",
            "product_category",
            "search_aliases",
        }
        assert {
            column["name"]
            for column in inspector.get_columns("mock_order_search_snapshots")
        } == {
            "snapshot_resource_ref",
            "customer_id",
            "observed_at",
            "snapshot_payload",
        }
        search_columns = {
            column["name"]: column
            for column in inspector.get_columns("mock_order_search_documents")
        }
        snapshot_columns = {
            column["name"]: column
            for column in inspector.get_columns("mock_order_search_snapshots")
        }
        assert search_columns["status"]["nullable"] is False
        assert search_columns["status"]["default"] is None
        assert snapshot_columns["snapshot_resource_ref"]["nullable"] is False
        assert snapshot_columns["snapshot_resource_ref"]["default"] is None
        assert {
            column["name"] for column in inspector.get_columns("mock_shipments")
        } == {
            "customer_id",
            "order_id",
            "package_id",
            "shipment_payload",
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
            for item in inspector.get_check_constraints("p0_record_references")
        } == {"ck_p0_record_references_ordinal_nonnegative"}
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
        assert foreign_keys["fk_p0_record_references_source"]["referred_columns"] == [
            "record_code",
            "logical_identity",
        ]
        assert foreign_keys["fk_p0_record_references_source"]["options"] == {
            "ondelete": "CASCADE",
            "initially": "DEFERRED",
            "deferrable": True,
        }
        assert foreign_keys["fk_p0_record_references_target"]["referred_columns"] == [
            "record_code",
            "logical_identity",
        ]
        assert foreign_keys["fk_p0_record_references_target"]["options"] == {
            "ondelete": "RESTRICT",
            "initially": "DEFERRED",
            "deferrable": True,
        }
        assert inspector.get_pk_constraint("mock_orders")["constrained_columns"] == [
            "customer_id",
            "order_id",
        ]
        assert inspector.get_pk_constraint("mock_order_search_documents")[
            "constrained_columns"
        ] == ["customer_id", "order_id", "line_ordinal"]
        assert inspector.get_pk_constraint("mock_order_search_snapshots")[
            "constrained_columns"
        ] == ["snapshot_resource_ref"]
        assert inspector.get_pk_constraint("mock_shipments")["constrained_columns"] == [
            "customer_id",
            "order_id",
            "package_id",
        ]
        search_foreign_keys = inspector.get_foreign_keys("mock_order_search_documents")
        shipment_foreign_keys = inspector.get_foreign_keys("mock_shipments")
        assert len(search_foreign_keys) == len(shipment_foreign_keys) == 1
        assert search_foreign_keys[0]["constrained_columns"] == [
            "customer_id",
            "order_id",
        ]
        assert shipment_foreign_keys[0]["constrained_columns"] == [
            "customer_id",
            "order_id",
        ]
        assert search_foreign_keys[0]["options"] == {"ondelete": "CASCADE"}
        assert shipment_foreign_keys[0]["options"] == {"ondelete": "CASCADE"}
        assert inspector.get_foreign_keys("mock_order_search_snapshots") == []
        assert {
            item["name"]
            for item in inspector.get_check_constraints("mock_order_search_documents")
        } == {
            "ck_mock_order_search_documents_line_ordinal_positive",
            "ck_mock_order_search_documents_quantity_positive",
            "ck_mock_order_search_documents_search_aliases_array",
            "ck_mock_order_search_documents_status_closed",
        }
        assert {
            item["name"]
            for item in inspector.get_check_constraints("mock_order_search_snapshots")
        } == {
            "ck_mock_order_search_snapshots_candidates_closed",
            "ck_mock_order_search_snapshots_payload_closed",
        }
        assert {
            item["name"] for item in inspector.get_check_constraints("mock_shipments")
        } == {"ck_mock_shipments_payload_object"}
        assert {
            item["name"]
            for item in inspector.get_indexes("mock_order_search_documents")
            if not item.get("duplicates_constraint")
        } == {"ix_mock_order_search_documents_owner_window"}
        assert {
            item["name"]
            for item in inspector.get_indexes("mock_order_search_snapshots")
            if not item.get("duplicates_constraint")
        } == {"ix_mock_order_search_snapshots_owner_ref"}
        assert {
            item["name"]
            for item in inspector.get_indexes("mock_shipments")
            if not item.get("duplicates_constraint")
        } == {"ix_mock_shipments_owner_order"}
    finally:
        engine.dispose()


def test_cycle2_mock_tables_enforce_owner_order_shape_and_allow_two_packages(
    postgres_namespace,
) -> None:
    engine = postgres_namespace.build_engine()
    ordered_at = datetime(2026, 7, 20, 2, 15, tzinfo=timezone.utc)
    try:
        with engine.begin() as connection:
            connection.execute(
                MockOrderModel.__table__.insert().values(
                    customer_id="customer-A",
                    order_id="O-1001",
                    order_payload={"order_number": "O-1001"},
                )
            )
            connection.execute(
                MockOrderSearchDocumentModel.__table__.insert().values(
                    customer_id="customer-A",
                    order_id="O-1001",
                    line_ordinal=1,
                    ordered_at=ordered_at,
                    order_number="O-1001",
                    status=OrderStatus.SHIPPED.value,
                    product_name="轻量跑鞋",
                    quantity=1,
                    product_category="running-shoes",
                    search_aliases=["跑鞋", "轻量跑鞋"],
                )
            )
            connection.execute(
                MockShipmentModel.__table__.insert(),
                (
                    {
                        "customer_id": "customer-A",
                        "order_id": "O-1001",
                        "package_id": "PKG-1",
                        "shipment_payload": {"status": "IN_TRANSIT"},
                    },
                    {
                        "customer_id": "customer-A",
                        "order_id": "O-1001",
                        "package_id": "PKG-2",
                        "shipment_payload": {"status": "DELIVERED"},
                    },
                ),
            )

        with engine.connect() as connection:
            assert (
                connection.scalar(select(func.count()).select_from(MockShipmentModel))
                == 2
            )

        invalid_search_values = (
            {"line_ordinal": 0, "quantity": 1, "search_aliases": []},
            {"line_ordinal": 2, "quantity": 0, "search_aliases": []},
            {"line_ordinal": 2, "quantity": 1, "search_aliases": {}},
        )
        for values in invalid_search_values:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        MockOrderSearchDocumentModel.__table__.insert().values(
                            customer_id="customer-A",
                            order_id="O-1001",
                            ordered_at=ordered_at,
                            order_number="O-1001",
                            status=OrderStatus.SHIPPED.value,
                            product_name="invalid",
                            product_category="invalid",
                            **values,
                        )
                    )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    MockShipmentModel.__table__.insert().values(
                        customer_id="customer-B",
                        order_id="O-1001",
                        package_id="PKG-foreign",
                        shipment_payload={},
                    )
                )

        with engine.begin() as connection:
            connection.execute(
                MockOrderModel.__table__.delete().where(
                    MockOrderModel.customer_id == "customer-A",
                    MockOrderModel.order_id == "O-1001",
                )
            )
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count()).select_from(MockOrderSearchDocumentModel)
                )
                == 0
            )
            assert (
                connection.scalar(select(func.count()).select_from(MockShipmentModel))
                == 0
            )
    finally:
        engine.dispose()


def test_expanded_physical_constraint_accepts_only_exact_catalog_pairs(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("expanded-pair-matrix")
    engine = namespace.build_engine()
    try:
        with engine.begin() as connection:
            for record_code, schema_version in _CYCLE2_CODE_VERSION_PAIRS:
                _insert_physical_probe(
                    connection,
                    record_code,
                    schema_version,
                )

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM p0_records")) == 29

        unsupported_pairs = (
            (
                "conversation_record",
                "request_understanding_record.p0.v2",
            ),
            (
                "request_understanding_record",
                "request_understanding_record.p0.v3",
            ),
            (
                "request_understanding_record",
                "request_understanding_record.p0.v2 ",
            ),
            ("unknown_record", "unknown_record.p0.v1"),
        )
        for record_code, schema_version in unsupported_pairs:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    _insert_physical_probe(
                        connection,
                        record_code,
                        schema_version,
                    )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_existing_v1_physical_row_is_unchanged_by_expand_upgrade(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("expand-preserves-v1")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    record_id = uuid4()
    try:
        command.downgrade(config, _PREVIOUS_MIGRATION_REVISION)
        assert _migration_revision(engine) == _PREVIOUS_MIGRATION_REVISION

        with engine.begin() as connection:
            _insert_physical_probe(
                connection,
                "request_understanding_record",
                "request_understanding_record.p0.v1",
                record_id=record_id,
                marker="preserved-v1-physical-row",
            )
        before = _record_row(engine, record_id)

        command.upgrade(config, _MIGRATION_REVISION)

        assert _migration_revision(engine) == _MIGRATION_REVISION
        assert _record_row(engine, record_id) == before
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_expand_downgrade_upgrade_without_v2_rows_changes_only_check_body(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("expand-cycle-no-v2")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        command.downgrade(config, _MIGRATION_REVISION)
        expanded_structure = _schema_structure(engine)
        expanded_checks = _record_check_definitions(engine)
        assert _migration_revision(engine) == _MIGRATION_REVISION

        command.downgrade(config, _PREVIOUS_MIGRATION_REVISION)

        v1_structure = _schema_structure(engine)
        v1_checks = _record_check_definitions(engine)
        assert _migration_revision(engine) == _PREVIOUS_MIGRATION_REVISION
        assert v1_structure == expanded_structure
        assert set(v1_checks) == set(expanded_checks)
        assert (
            v1_checks["ck_p0_records_code_version_closed"]
            != expanded_checks["ck_p0_records_code_version_closed"]
        )
        assert {
            name: definition
            for name, definition in v1_checks.items()
            if name != "ck_p0_records_code_version_closed"
        } == {
            name: definition
            for name, definition in expanded_checks.items()
            if name != "ck_p0_records_code_version_closed"
        }

        command.upgrade(config, _MIGRATION_REVISION)

        assert _migration_revision(engine) == _MIGRATION_REVISION
        assert _schema_structure(engine) == expanded_structure
        assert _record_check_definitions(engine) == expanded_checks
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_expand_downgrade_with_v2_row_fails_closed_and_atomically(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("expand-downgrade-v2")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    record_id = uuid4()
    try:
        command.downgrade(config, _MIGRATION_REVISION)
        with engine.begin() as connection:
            _insert_physical_probe(
                connection,
                "request_understanding_record",
                "request_understanding_record.p0.v2",
                record_id=record_id,
                marker="must-not-appear-in-downgrade-error",
            )
        before = _record_row(engine, record_id)

        with pytest.raises(RuntimeError) as captured:
            command.downgrade(config, _PREVIOUS_MIGRATION_REVISION)

        assert str(captured.value) == _DOWNGRADE_BLOCKED_MESSAGE
        assert "must-not-appear-in-downgrade-error" not in str(captured.value)
        assert str(record_id) not in str(captured.value)
        assert _migration_revision(engine) == _MIGRATION_REVISION
        assert _record_row(engine, record_id) == before

        with engine.begin() as connection:
            second_v2_id = _insert_physical_probe(
                connection,
                "request_understanding_record",
                "request_understanding_record.p0.v2",
                marker="expanded-constraint-remains",
            )
        assert _record_row(engine, second_v2_id)["record_schema_version"] == (
            "request_understanding_record.p0.v2"
        )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                _insert_physical_probe(
                    connection,
                    "conversation_record",
                    "request_understanding_record.p0.v2",
                )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_cycle2_downgrade_locks_both_evidence_tables_against_all_dml(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("cycle2-evidence-lock-contract")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    marker = "must-not-cross-cycle2-downgrade-lock"
    try:
        with engine.begin() as connection:
            connection.execute(
                MockOrderModel.__table__.insert().values(
                    customer_id="customer-lock",
                    order_id="O-7001",
                    order_payload={"order_number": "O-7001"},
                )
            )

        ddl_barrier_connection = engine.connect()
        ddl_barrier_transaction = ddl_barrier_connection.begin()
        downgrade_executor = ThreadPoolExecutor(max_workers=1)
        downgrade_future = None
        try:
            assert (
                ddl_barrier_connection.scalar(
                    text("SELECT count(*) FROM mock_shipments")
                )
                == 0
            )
            downgrade_future = downgrade_executor.submit(
                command.downgrade,
                config,
                _CYCLE2_PREVIOUS_MIGRATION_REVISION,
            )
            _wait_for_real_downgrade_lock(
                engine,
                schema=namespace.schema,
                relation_name="mock_shipments",
            )

            blocked_statements = (
                (
                    text(
                        """
                        INSERT INTO mock_order_search_documents (
                            customer_id, order_id, line_ordinal, ordered_at,
                            order_number, product_name, quantity,
                            product_category, search_aliases
                        ) VALUES (
                            :customer_id, :order_id, 1, :ordered_at,
                            :order_number, :marker, 1, :marker,
                            CAST(:search_aliases AS jsonb)
                        )
                        """
                    ),
                    {
                        "customer_id": "customer-lock",
                        "order_id": "O-7001",
                        "ordered_at": datetime(
                            2026,
                            7,
                            31,
                            8,
                            0,
                            tzinfo=timezone.utc,
                        ),
                        "order_number": "O-7001",
                        "marker": marker,
                        "search_aliases": '["blocked"]',
                    },
                ),
                (
                    text(
                        "UPDATE mock_order_search_documents "
                        "SET product_name = :marker "
                        "WHERE customer_id = :customer_id"
                    ),
                    {"marker": marker, "customer_id": "customer-lock"},
                ),
                (
                    text(
                        "DELETE FROM mock_order_search_documents "
                        "WHERE customer_id = :customer_id"
                    ),
                    {"customer_id": "customer-lock"},
                ),
                (
                    text(
                        """
                        INSERT INTO mock_shipments (
                            customer_id, order_id, package_id, shipment_payload
                        ) VALUES (
                            :customer_id, :order_id, :package_id,
                            CAST(:shipment_payload AS jsonb)
                        )
                        """
                    ),
                    {
                        "customer_id": "customer-lock",
                        "order_id": "O-7001",
                        "package_id": "PKG-blocked",
                        "shipment_payload": '{"marker":"blocked"}',
                    },
                ),
                (
                    text(
                        "UPDATE mock_shipments "
                        "SET shipment_payload = CAST(:shipment_payload AS jsonb) "
                        "WHERE customer_id = :customer_id"
                    ),
                    {
                        "shipment_payload": '{"marker":"blocked"}',
                        "customer_id": "customer-lock",
                    },
                ),
                (
                    text("DELETE FROM mock_shipments WHERE customer_id = :customer_id"),
                    {"customer_id": "customer-lock"},
                ),
            )
            for statement, parameters in blocked_statements:
                _assert_lock_timeout(
                    engine,
                    statement,
                    parameters=parameters,
                )

        finally:
            ddl_barrier_transaction.rollback()
            ddl_barrier_connection.close()
            downgrade_executor.shutdown(wait=True)

        assert downgrade_future is not None
        assert downgrade_future.result(timeout=10) is None
        assert _migration_revision(engine) == _CYCLE2_PREVIOUS_MIGRATION_REVISION
        inspector = inspect(engine)
        assert "mock_order_search_documents" not in inspector.get_table_names()
        assert "mock_shipments" not in inspector.get_table_names()
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM mock_orders "
                        "WHERE customer_id = 'customer-lock' "
                        "AND order_id = 'O-7001'"
                    )
                )
                == 1
            )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize(
    "evidence_table",
    ("mock_order_search_documents", "mock_shipments"),
)
def test_cycle2_downgrade_waits_for_prior_evidence_insert_then_fails_bounded(
    postgres_namespace_factory,
    evidence_table: str,
) -> None:
    namespace = postgres_namespace_factory.create(f"cycle2-prior-{evidence_table}")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    marker = f"must-not-leak-{evidence_table}"
    writer_connection = None
    writer_transaction = None
    downgrade_executor = ThreadPoolExecutor(max_workers=1)
    downgrade_future = None
    try:
        with engine.begin() as connection:
            connection.execute(
                MockOrderModel.__table__.insert().values(
                    customer_id="customer-prior-writer",
                    order_id="O-7002",
                    order_payload={"order_number": "O-7002"},
                )
            )

        writer_connection = engine.connect()
        writer_transaction = writer_connection.begin()
        if evidence_table == "mock_order_search_documents":
            writer_connection.execute(
                MockOrderSearchDocumentModel.__table__.insert().values(
                    customer_id="customer-prior-writer",
                    order_id="O-7002",
                    line_ordinal=1,
                    ordered_at=datetime(
                        2026,
                        7,
                        31,
                        8,
                        1,
                        tzinfo=timezone.utc,
                    ),
                    order_number="O-7002",
                    status=OrderStatus.SHIPPED.value,
                    product_name=marker,
                    quantity=1,
                    product_category="migration-lock-test",
                    search_aliases=["blocked"],
                )
            )
        else:
            writer_connection.execute(
                MockShipmentModel.__table__.insert().values(
                    customer_id="customer-prior-writer",
                    order_id="O-7002",
                    package_id="PKG-prior-writer",
                    shipment_payload={"marker": marker},
                )
            )

        downgrade_future = downgrade_executor.submit(
            command.downgrade,
            config,
            _CYCLE2_PREVIOUS_MIGRATION_REVISION,
        )
        _wait_for_pending_table_lock(
            engine,
            schema=namespace.schema,
            relation_name=evidence_table,
            mode="ShareRowExclusiveLock",
        )

        writer_transaction.commit()
        writer_connection.close()
        writer_transaction = None
        writer_connection = None

        with pytest.raises(RuntimeError) as captured:
            downgrade_future.result(timeout=10)
        expected_message = (
            _SEARCH_AUTHORITY_DOWNGRADE_BLOCKED_MESSAGE
            if evidence_table == "mock_order_search_documents"
            else _CYCLE2_DOWNGRADE_BLOCKED_MESSAGE
        )
        assert str(captured.value) == expected_message
        assert marker not in str(captured.value)
        assert _migration_revision(engine) == _SEARCH_AUTHORITY_MIGRATION_REVISION
        assert evidence_table in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert (
                connection.scalar(text(f"SELECT count(*) FROM {evidence_table}")) == 1
            )
    finally:
        if writer_transaction is not None:
            writer_transaction.rollback()
        if writer_connection is not None:
            writer_connection.close()
        downgrade_executor.shutdown(wait=True)
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_real_downgrade_share_row_exclusive_lock_blocks_insert_and_update(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("expand-lock-contract")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    existing_id = uuid4()
    recovery_id = uuid4()
    try:
        command.downgrade(config, _MIGRATION_REVISION)
        with engine.begin() as connection:
            _insert_physical_probe(
                connection,
                "conversation_record",
                "conversation_record.p0.v1",
                record_id=existing_id,
                marker="lock-existing-row",
            )

        ddl_barrier_connection = engine.connect()
        ddl_barrier_transaction = ddl_barrier_connection.begin()
        downgrade_executor = ThreadPoolExecutor(max_workers=1)
        downgrade_future = None
        try:
            assert (
                ddl_barrier_connection.scalar(
                    text("SELECT 1 FROM p0_records WHERE record_id = :record_id"),
                    {"record_id": existing_id},
                )
                == 1
            )
            downgrade_future = downgrade_executor.submit(
                command.downgrade,
                config,
                _PREVIOUS_MIGRATION_REVISION,
            )
            _wait_for_real_downgrade_lock(
                engine,
                schema=namespace.schema,
            )

            _assert_lock_timeout(
                engine,
                P0RecordModel.__table__.insert().values(
                    **_physical_probe_values(
                        "request_understanding_record",
                        "request_understanding_record.p0.v2",
                        record_id=recovery_id,
                        marker="blocked-insert",
                    )
                ),
            )
            _assert_lock_timeout(
                engine,
                P0RecordModel.__table__.update()
                .where(P0RecordModel.record_id == existing_id)
                .values(lifecycle_status="BLOCKED_UPDATE"),
            )

            assert (
                ddl_barrier_connection.scalar(text("SELECT count(*) FROM p0_records"))
                == 1
            )
            assert (
                ddl_barrier_connection.scalar(
                    select(P0RecordModel.lifecycle_status).where(
                        P0RecordModel.record_id == existing_id
                    )
                )
                is None
            )
        finally:
            ddl_barrier_transaction.rollback()
            ddl_barrier_connection.close()
            downgrade_executor.shutdown(wait=True)

        assert downgrade_future is not None
        downgrade_future.result(timeout=10)
        assert _migration_revision(engine) == _PREVIOUS_MIGRATION_REVISION

        with engine.begin() as connection:
            _insert_physical_probe(
                connection,
                "conversation_record",
                "conversation_record.p0.v1",
                record_id=recovery_id,
                marker="write-recovers-after-downgrade-lock",
            )
            connection.execute(
                P0RecordModel.__table__.update()
                .where(P0RecordModel.record_id == existing_id)
                .values(lifecycle_status="RECOVERED_AFTER_DOWNGRADE"),
            )
        assert _record_row(engine, recovery_id)["envelope"] == {
            "physical_probe": "write-recovers-after-downgrade-lock"
        }
        assert _record_row(engine, existing_id)["lifecycle_status"] == (
            "RECOVERED_AFTER_DOWNGRADE"
        )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


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
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20260726_0001"
            )

        command.upgrade(config, "head")
        inspector.clear_cache()
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "mock_order_search_documents",
            "mock_order_search_snapshots",
            "mock_orders",
            "mock_shipments",
            "p0_record_references",
            "p0_records",
        }
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == _SEARCH_AUTHORITY_MIGRATION_REVISION
            )
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
