from __future__ import annotations

import asyncio
import ast
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from mini_agent.application.persistence import (
    P0_RECORD_SCHEMA_VERSION_CATALOG,
    P0RecordCode,
    encode_persistence_record,
    encode_persistence_record_versioned,
)
from mini_agent.application.records import (
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    MessageDirection,
)
from mini_agent.core.order import OrderStatus
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    DurableTaskDeltaCandidateV2,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.trace import (
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    StopReason,
)
from mini_agent.infrastructure.persistence import models as persistence_models
from mini_agent.infrastructure.persistence.database import (
    DEFAULT_LOCAL_DATABASE_URL,
    DEFAULT_LOCAL_TEST_DATABASE_URL,
    build_engine,
    build_session_factory,
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
    P0RecordStateHistoryModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_agent_run_service import (  # noqa: E402
    _dnr_v3_staging_command,
    _generic_v3_staging_command,
)
from test_record_contracts import _initial_v2_graph  # noqa: E402

_INTEGRATION_TESTS = Path(__file__).parent
sys.path.append(str(_INTEGRATION_TESTS))
from test_postgres_v3_request_understanding_writes import (  # noqa: E402
    _seed_continuation_roots,
    _seed_phase1_roots,
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
_RECORD_HISTORY_MIGRATION_REVISION = "20260802_0006"
_RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION = (
    _SEARCH_AUTHORITY_MIGRATION_REVISION
)
_RU_V3_MIGRATION_REVISION = "20260803_0007"
_RU_V3_PREVIOUS_MIGRATION_REVISION = _RECORD_HISTORY_MIGRATION_REVISION
_RU_V3_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260803_0007_request_understanding_v3_cutover.py"
)
_RECORD_HISTORY_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260802_0006_cycle2_record_state_history.py"
)
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
_RECORD_HISTORY_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade record state history while durable evidence exists"
)
_RECORD_HISTORY_APPEND_ONLY_MESSAGE = "record state history is append-only"
_RU_V3_UPGRADE_BLOCKED_MESSAGE = (
    "request understanding v3 cutover graph is not exactly convertible"
)
_RU_V3_DOWNGRADE_BLOCKED_MESSAGE = (
    "request understanding v3 downgrade graph is not exactly reversible"
)
_RECORD_HISTORY_APPEND_ONLY_FUNCTION = (
    "p0_record_state_history_reject_mutation"
)
_RECORD_HISTORY_ROW_MUTATION_TRIGGER = (
    "trg_p0_record_state_history_reject_row_mutation"
)
_RECORD_HISTORY_TRUNCATE_TRIGGER = (
    "trg_p0_record_state_history_reject_truncate"
)
_RECORD_HISTORY_CODE_VERSION_PAIRS = (
    ("task_record", "task_record.p0.v1"),
    ("request_unit_record", "request_unit_record.p0.v1"),
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
    (
        "request_understanding_record",
        "request_understanding_record.p0.v3",
    ),
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


async def _insert_generic_v2_source_from_v3_command(
    adapter: PostgresRecordAdapter,
    staged,
) -> dict[str, object]:
    await _seed_phase1_roots(adapter, staged)
    source = staged.request_understanding.record
    source_children = staged.request_understanding.accepted_task_deltas
    record = RequestUnderstandingRecordV2(
        request_understanding_record_id=(
            source.request_understanding_record_id
        ),
        run_id=source.run_id,
        message_ref=source.message_ref,
        schema_version="request_understanding_record.p0.v2",
        model_input_schema_version=source.model_input_schema_version,
        model_output_schema_version=source.model_output_schema_version,
        contextualization=source.contextualization,
        task_delta_candidates=tuple(
            DurableTaskDeltaCandidateV2(**candidate.model_dump())
            for candidate in source.task_delta_candidates
        ),
        candidate_validation=source.candidate_validation,
        accepted_delta_refs=source.accepted_delta_refs,
        proposed_base_task_state_version=(
            source.proposed_base_task_state_version
        ),
        validated_task_state_version=source.validated_task_state_version,
        next_move_candidate_ref=source.next_move_candidate_ref,
        created_at=source.created_at,
    )
    children = tuple(
        AcceptedTaskDeltaV2(**child.model_dump())
        for child in source_children
    )
    ru = encode_persistence_record_versioned(
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        "request_understanding_record.p0.v2",
        record,
        logical_children=children,
    )
    generated = []
    for graph in getattr(staged, "accepted_task_graphs", ()):
        unit = graph.initial_request_unit.initial_record
        generated.extend(
            (
                adapter._ru_v2_write_encode(
                    P0RecordCode.TASK_RECORD,
                    graph.initial_task.initial_record,
                ),
                adapter._ru_v2_write_encode(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    unit,
                ),
                *(
                    adapter._ru_v2_write_encode(
                        P0RecordCode.INPUT_BINDING_RECORD,
                        binding.record,
                        external_references=tuple(
                            reference
                            for reference in adapter._cycle2_encode_input_binding(
                                binding.record,
                                request_unit_id=binding.request_unit_id,
                            ).record_references
                            if reference.relation == "request_unit_id"
                        ),
                    )
                    for binding in graph.input_bindings
                ),
                adapter._ru_v2_write_encode(
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                    graph.conversation_task_link,
                ),
                adapter._ru_v2_write_encode(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    graph.run_task_link.active_record,
                ),
            )
        )
    with adapter.session_factory.begin() as session:
        roots = adapter._ru_v2_write_lock_roots(
            session,
            owner_scope=staged.owner_scope,
            conversation=staged.expected_conversation_record,
            messages=staged.expected_message_records,
            run=staged.expected_active_run_record,
        )
        adapter._ru_v3_insert_phase1_envelopes(
            session,
            owner_customer_id=staged.owner_scope.customer_id,
            root_rows=roots,
            envelopes=(ru, *generated),
        )
    return ru.model_dump(mode="json")


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


def _history_probe_values(
    record_code: P0RecordCode,
    *,
    identity: UUID | None = None,
    owner_customer_id: str = "customer-history",
    state_version: int = 1,
    history_id: UUID | None = None,
) -> dict[str, object]:
    record_identity = identity or uuid4()
    created_at = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    if record_code is P0RecordCode.TASK_RECORD:
        record = TaskRecord(
            task_id=record_identity,
            owner_customer_id=owner_customer_id,
            status=TaskStatus.ACTIVE,
            state_version=state_version,
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=state_version - 1),
        )
    elif record_code is P0RecordCode.REQUEST_UNIT_RECORD:
        record = RequestUnitRecord(
            request_unit_id=record_identity,
            task_id=uuid4(),
            goal_text="history physical probe",
            goal_source_refs=(uuid4(),),
            input_binding_refs=(uuid4(),),
            status=TaskStatus.ACTIVE,
            state_version=state_version,
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=state_version - 1),
        )
    else:
        raise ValueError("history probe supports only Task or RequestUnit")
    envelope = encode_persistence_record(record_code, record)
    raw_envelope = envelope.model_dump(mode="json")
    return {
        "history_id": history_id or uuid4(),
        "record_code": record_code.value,
        "record_schema_version": envelope.record_schema_version,
        "logical_identity": raw_envelope["logical_identity"],
        "scope_owner_customer_id": owner_customer_id,
        "state_version": state_version,
        "envelope": raw_envelope,
    }


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
        with engine.begin() as connection:
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

    assert tuple(script.get_heads()) == (_RU_V3_MIGRATION_REVISION,)
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
    assert tuple(script.get_heads()) == (_RU_V3_MIGRATION_REVISION,)


def test_search_authority_correction_is_single_linear_alembic_head() -> None:
    assert _SEARCH_AUTHORITY_MIGRATION_PATH.is_file()
    script = ScriptDirectory.from_config(
        alembic_config(DEFAULT_LOCAL_TEST_DATABASE_URL, testing=True)
    )

    revision = script.get_revision(_SEARCH_AUTHORITY_MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == _SEARCH_AUTHORITY_PREVIOUS_MIGRATION_REVISION
    assert tuple(script.get_heads()) == (_RU_V3_MIGRATION_REVISION,)


def test_record_history_correction_is_single_linear_alembic_head() -> None:
    assert _RECORD_HISTORY_MIGRATION_PATH.is_file()
    script = ScriptDirectory.from_config(
        alembic_config(DEFAULT_LOCAL_TEST_DATABASE_URL, testing=True)
    )

    revision = script.get_revision(_RECORD_HISTORY_MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION
    assert tuple(script.get_heads()) == (_RU_V3_MIGRATION_REVISION,)


def test_request_understanding_v3_cutover_is_single_linear_alembic_head() -> None:
    assert _RU_V3_MIGRATION_PATH.is_file()
    script = ScriptDirectory.from_config(
        alembic_config(DEFAULT_LOCAL_TEST_DATABASE_URL, testing=True)
    )

    revision = script.get_revision(_RU_V3_MIGRATION_REVISION)
    assert revision is not None
    assert revision.down_revision == _RU_V3_PREVIOUS_MIGRATION_REVISION
    assert tuple(script.get_heads()) == (_RU_V3_MIGRATION_REVISION,)


def test_pre_v3_revision_rejects_v3_physical_pair(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-pre-head-reject")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                _insert_physical_probe(
                    connection,
                    "request_understanding_record",
                    "request_understanding_record.p0.v3",
                )
        assert _migration_revision(engine) == _RU_V3_PREVIOUS_MIGRATION_REVISION
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_ru_v3_upgrade_and_downgrade_preserve_exact_phase1_closure(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-round-trip")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_seed_phase1_roots(adapter, graph))
        assert asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(graph)
        ) is ConditionalWriteResult.APPLIED
        with engine.begin() as connection:
            source_row = connection.execute(
                text(
                    """
                    SELECT * FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                      AND record_schema_version =
                          'request_understanding_record.p0.v2'
                    """
                )
            ).mappings().one()
            record_id = source_row["record_id"]
            source_envelope = json.loads(json.dumps(source_row["envelope"]))
            source_references = tuple(
                tuple(reference.values())
                for reference in connection.execute(
                    text(
                        """
                        SELECT ordinal, relation, target_record_code,
                               target_logical_identity
                        FROM p0_record_references
                        WHERE source_record_code =
                                  'request_understanding_record'
                          AND source_logical_identity =
                              CAST(:identity AS jsonb)
                        ORDER BY ordinal
                        """
                    ),
                    {
                        "identity": json.dumps(
                            source_row["logical_identity"],
                            separators=(",", ":"),
                        )
                    },
                ).mappings()
            )
            archival_id = _insert_physical_probe(
                connection,
                "request_understanding_record",
                "request_understanding_record.p0.v1",
                marker="archival-v1-must-remain",
            )
        command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        converted = _record_row(engine, record_id)
        assert converted["record_schema_version"] == (
            "request_understanding_record.p0.v3"
        )
        evidence = asyncio.run(
            adapter.load_exact_run_evidence_v3_for_owner(
                owner_scope=graph.owner_scope,
                run_id=graph.expected_active_run_record.run_id,
            )
        )
        assert evidence is not None
        closure = evidence.request_understanding_closure
        assert closure is not None
        assert closure.record.request_understanding_record_id == (
            graph.request_understanding.record.request_understanding_record_id
        )
        assert tuple(
            child.accepted_delta_id for child in closure.accepted_task_deltas
        ) == (graph.request_understanding.accepted_delta.accepted_delta_id,)
        assert _record_row(engine, archival_id)["envelope"][
            "physical_probe"
        ] == "archival-v1-must-remain"

        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        restored = _record_row(engine, record_id)
        assert restored["record_schema_version"] == (
            "request_understanding_record.p0.v2"
        )
        assert restored["envelope"] == source_envelope
        with engine.connect() as connection:
            restored_references = tuple(
                tuple(reference.values())
                for reference in connection.execute(
                    text(
                        """
                        SELECT ordinal, relation, target_record_code,
                               target_logical_identity
                        FROM p0_record_references
                        WHERE source_record_code =
                                  'request_understanding_record'
                          AND source_logical_identity =
                              CAST(:identity AS jsonb)
                        ORDER BY ordinal
                        """
                    ),
                    {
                        "identity": json.dumps(
                            restored["logical_identity"],
                            separators=(",", ":"),
                        )
                    },
                ).mappings()
            )
        assert restored_references == source_references
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize(
    "candidate_values",
    (
        (),
        ("BAD",),
        ("O-1001", "BAD"),
        ("O-1001", "O-1002"),
    ),
)
def test_ru_v3_cutover_preserves_zero_reject_partial_and_multi_order(
    postgres_namespace_factory,
    candidate_values: tuple[str, ...],
) -> None:
    namespace = postgres_namespace_factory.create(
        f"ru-v3-shape-{len(candidate_values)}-{uuid4().hex[:6]}"
    )
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    staged = _generic_v3_staging_command(candidate_values)
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        source_envelope = asyncio.run(
            _insert_generic_v2_source_from_v3_command(adapter, staged)
        )
        command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        evidence = asyncio.run(
            adapter.load_exact_run_evidence_v3_for_owner(
                owner_scope=staged.owner_scope,
                run_id=staged.expected_active_run_record.run_id,
            )
        )
        assert evidence is not None
        assert evidence.request_understanding_closure == (
            staged.request_understanding
        )
        assert {task.task_id for task in evidence.task_records} == {
            graph.initial_task.initial_record.task_id
            for graph in getattr(staged, "accepted_task_graphs", ())
        }

        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        with engine.connect() as connection:
            restored = connection.execute(
                text(
                    """
                    SELECT envelope FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                    """
                )
            ).mappings().one()["envelope"]
        assert restored == source_envelope
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_ru_v3_upgrade_bad_provenance_is_atomic_and_bounded(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-bad-provenance")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_seed_phase1_roots(adapter, graph))
        assert asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(graph)
        ) is ConditionalWriteResult.APPLIED
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT record_id, envelope FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                    """
                )
            ).mappings().one()
            record_id = row["record_id"]
            envelope = json.loads(json.dumps(row["envelope"]))
            envelope["payload"]["data"]["task_delta_candidates"][0][
                "input_candidates"
            ][0]["source_quote_sha256"] = "0" * 64
            connection.execute(
                text(
                    """
                    UPDATE p0_records
                    SET envelope = CAST(:envelope AS jsonb)
                    WHERE record_id = :record_id
                    """
                ),
                {
                    "record_id": record_id,
                    "envelope": json.dumps(envelope, separators=(",", ":")),
                },
            )
        before = _record_row(engine, record_id)
        with pytest.raises(RuntimeError) as captured:
            command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        assert str(captured.value) == _RU_V3_UPGRADE_BLOCKED_MESSAGE
        assert _migration_revision(engine) == _RU_V3_PREVIOUS_MIGRATION_REVISION
        assert _record_row(engine, record_id) == before
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    """
                    SELECT count(*) FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                      AND record_schema_version =
                          'request_understanding_record.p0.v3'
                    """
                )
            ) == 0
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_ru_v3_upgrade_rejects_direct_assistant_message_atomically(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-assistant-message")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    staged = _generic_v3_staging_command(())
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_insert_generic_v2_source_from_v3_command(adapter, staged))
        current_message = next(
            message
            for message in staged.expected_message_records
            if message.message_id == staged.request_understanding.record.message_ref
        )
        with adapter.session_factory.begin() as session:
            loaded = adapter._cycle2_row(
                session,
                owner_customer_id=staged.owner_scope.customer_id,
                record_code=P0RecordCode.MESSAGE_RECORD,
                logical_identity=(("message_id", current_message.message_id),),
                for_update=True,
            )
            assert loaded is not None
            adapter._cycle2_replace(
                session,
                loaded[0],
                owner_customer_id=staged.owner_scope.customer_id,
                expected_record=current_message,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.MESSAGE_RECORD,
                    current_message.model_copy(
                        update={"direction": MessageDirection.ASSISTANT}
                    ),
                ),
            )
        with pytest.raises(RuntimeError) as captured:
            command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        assert str(captured.value) == _RU_V3_UPGRADE_BLOCKED_MESSAGE
        assert _migration_revision(engine) == _RU_V3_PREVIOUS_MIGRATION_REVISION
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    """
                    SELECT count(*) FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                      AND record_schema_version =
                          'request_understanding_record.p0.v2'
                    """
                )
            ) == 1
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_ru_v3_upgrade_rejects_canonical_initial_effect_drift_atomically(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-effect-drift")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_seed_phase1_roots(adapter, graph))
        assert asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(graph)
        ) is ConditionalWriteResult.APPLIED
        task = graph.initial_task.initial_record
        with adapter.session_factory.begin() as session:
            loaded = adapter._cycle2_row(
                session,
                owner_customer_id=graph.owner_scope.customer_id,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", task.task_id),),
                for_update=True,
            )
            assert loaded is not None
            adapter._cycle2_replace(
                session,
                loaded[0],
                owner_customer_id=graph.owner_scope.customer_id,
                expected_record=task,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.TASK_RECORD,
                    task.model_copy(update={"status": TaskStatus.WAITING_USER}),
                ),
            )
        with pytest.raises(RuntimeError) as captured:
            command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        assert str(captured.value) == _RU_V3_UPGRADE_BLOCKED_MESSAGE
        assert _migration_revision(engine) == _RU_V3_PREVIOUS_MIGRATION_REVISION
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize("direction", ("upgrade", "downgrade"))
def test_ru_v3_cutover_rejects_ended_initial_conversation_link_atomically(
    postgres_namespace_factory,
    direction: str,
) -> None:
    namespace = postgres_namespace_factory.create(f"ru-v3-ended-link-{direction}")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_seed_phase1_roots(adapter, graph))
        assert asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(graph)
        ) is ConditionalWriteResult.APPLIED
        if direction == "downgrade":
            command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        link = graph.conversation_task_link
        with adapter.session_factory.begin() as session:
            loaded = adapter._cycle2_row(
                session,
                owner_customer_id=graph.owner_scope.customer_id,
                record_code=P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                logical_identity=adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                    link,
                ).logical_identity,
                for_update=True,
            )
            assert loaded is not None
            adapter._cycle2_replace(
                session,
                loaded[0],
                owner_customer_id=graph.owner_scope.customer_id,
                expected_record=link,
                next_envelope=adapter._cycle2_encode(
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                    link.model_copy(
                        update={
                            "ended_at": link.linked_at + timedelta(milliseconds=1)
                        }
                    ),
                ),
            )
        with pytest.raises(RuntimeError) as captured:
            if direction == "upgrade":
                command.upgrade(config, _RU_V3_MIGRATION_REVISION)
            else:
                command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        assert str(captured.value) == (
            _RU_V3_UPGRADE_BLOCKED_MESSAGE
            if direction == "upgrade"
            else _RU_V3_DOWNGRADE_BLOCKED_MESSAGE
        )
        assert _migration_revision(engine) == (
            _RU_V3_PREVIOUS_MIGRATION_REVISION
            if direction == "upgrade"
            else _RU_V3_MIGRATION_REVISION
        )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize("drift_non_transition_field", (False, True))
def test_ru_v3_upgrade_validates_closed_phase1_transition_history(
    postgres_namespace_factory,
    drift_non_transition_field: bool,
) -> None:
    namespace = postgres_namespace_factory.create(
        f"ru-v3-advanced-effect-{drift_non_transition_field}"
    )
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_seed_phase1_roots(adapter, graph))
        assert asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(graph)
        ) is ConditionalWriteResult.APPLIED
        task = graph.initial_task.initial_record
        unit = graph.initial_request_unit.initial_record
        changed_at = task.updated_at + timedelta(milliseconds=1)
        next_task = task.model_copy(
            update={
                "status": TaskStatus.WAITING_USER,
                "state_version": 2,
                "updated_at": changed_at,
            }
        )
        next_unit = unit.model_copy(
            update={
                "status": TaskStatus.WAITING_USER,
                "state_version": 2,
                "updated_at": changed_at,
            }
        )
        transition = ApplyTaskTransitionCommand(
            expected_task_record=task,
            next_task_record=next_task,
            expected_request_unit_record=unit,
            next_request_unit_record=next_unit,
            task_state_transition=TaskStateTransition(
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                from_status=TaskStatus.ACTIVE,
                to_status=TaskStatus.WAITING_USER,
                base_state_version=1,
                result_state_version=2,
                reason_ref=graph.request_understanding.record.run_id,
                changed_at=changed_at,
            ),
        )
        assert asyncio.run(
            adapter.apply_task_transition_if_current(transition)
        ) is ConditionalWriteResult.APPLIED
        active_link = graph.run_task_link.active_record
        active_run = graph.expected_active_run_record
        with adapter.session_factory.begin() as session:
            link_row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.RUN_TASK_LINK_RECORD.value,
                    P0RecordModel.run_id == active_link.run_id,
                    P0RecordModel.task_id == active_link.task_id,
                )
            )
            run_row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.AGENT_RUN_RECORD.value,
                    P0RecordModel.run_id == active_run.run_id,
                )
            )
            assert link_row is not None and run_row is not None
            terminal_link = active_link.model_copy(
                update={"result_task_state_version": 2}
            )
            terminal_run = active_run.model_copy(
                update={
                    "status": AgentRunStatus.COMPLETED,
                    "completed_at": changed_at,
                    "stop_reason": StopReason.GOAL_COMPLETED,
                }
            )
            link_envelope = encode_persistence_record_versioned(
                P0RecordCode.RUN_TASK_LINK_RECORD,
                "run_task_link_record.p0.v1",
                terminal_link,
            )
            run_envelope = encode_persistence_record_versioned(
                P0RecordCode.AGENT_RUN_RECORD,
                "agent_run_record.p0.v1",
                terminal_run,
            )
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == link_row.record_id)
                .values(envelope=link_envelope.model_dump(mode="json"))
            )
            session.execute(
                update(P0RecordModel)
                .where(P0RecordModel.record_id == run_row.record_id)
                .values(
                    envelope=run_envelope.model_dump(mode="json"),
                    lifecycle_status=AgentRunStatus.COMPLETED.value,
                )
            )
        later_changed_at = changed_at + timedelta(milliseconds=1)
        final_task = next_task.model_copy(
            update={
                "status": TaskStatus.BLOCKED,
                "state_version": 3,
                "updated_at": later_changed_at,
            }
        )
        final_unit = next_unit.model_copy(
            update={
                "status": TaskStatus.BLOCKED,
                "state_version": 3,
                "updated_at": later_changed_at,
            }
        )
        later_transition = ApplyTaskTransitionCommand(
            expected_task_record=next_task,
            next_task_record=final_task,
            expected_request_unit_record=next_unit,
            next_request_unit_record=final_unit,
            task_state_transition=TaskStateTransition(
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                from_status=TaskStatus.WAITING_USER,
                to_status=TaskStatus.BLOCKED,
                base_state_version=2,
                result_state_version=3,
                reason_ref=uuid4(),
                changed_at=later_changed_at,
            ),
        )
        assert asyncio.run(
            adapter.apply_task_transition_if_current(later_transition)
        ) is ConditionalWriteResult.APPLIED
        if drift_non_transition_field:
            with adapter.session_factory.begin() as session:
                loaded = adapter._cycle2_row(
                    session,
                    owner_customer_id=graph.owner_scope.customer_id,
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=(("task_id", task.task_id),),
                    for_update=True,
                )
                assert loaded is not None
                adapter._cycle2_replace(
                    session,
                    loaded[0],
                    owner_customer_id=graph.owner_scope.customer_id,
                    expected_record=final_task,
                    expected_children=(
                        transition.task_state_transition,
                        later_transition.task_state_transition,
                    ),
                    next_envelope=adapter._cycle2_encode(
                        P0RecordCode.TASK_RECORD,
                        final_task.model_copy(
                            update={
                                "created_at": final_task.created_at
                                + timedelta(milliseconds=1)
                            }
                        ),
                        logical_children=(
                            transition.task_state_transition,
                            later_transition.task_state_transition,
                        ),
                    ),
                )
            with pytest.raises(RuntimeError) as captured:
                command.upgrade(config, _RU_V3_MIGRATION_REVISION)
            assert str(captured.value) == _RU_V3_UPGRADE_BLOCKED_MESSAGE
            assert _migration_revision(engine) == (
                _RU_V3_PREVIOUS_MIGRATION_REVISION
            )
        else:
            command.upgrade(config, _RU_V3_MIGRATION_REVISION)
            assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
            assert asyncio.run(
                adapter.assert_request_understanding_v3_ready()
            ) is None
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize(
    "target_record_code",
    ("task_record", "request_unit_record"),
)
def test_ru_v3_upgrade_rejects_malformed_referenced_closure_atomically(
    postgres_namespace_factory,
    target_record_code: str,
) -> None:
    namespace = postgres_namespace_factory.create(
        f"ru-v3-bad-{target_record_code}"
    )
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    graph = _initial_v2_graph()
    try:
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        asyncio.run(_seed_phase1_roots(adapter, graph))
        assert asyncio.run(
            adapter.create_initial_task_graph_v2_if_current(graph)
        ) is ConditionalWriteResult.APPLIED
        with engine.begin() as connection:
            target_row = connection.execute(
                text(
                    """
                    SELECT record_id FROM p0_records
                    WHERE record_code = :record_code
                    """
                ),
                {"record_code": target_record_code},
            ).mappings().one()
            connection.execute(
                text(
                    """
                    UPDATE p0_records
                    SET envelope = CAST('{}' AS jsonb)
                    WHERE record_id = :record_id
                    """
                ),
                {"record_id": target_row["record_id"]},
            )
        before = _record_row(engine, target_row["record_id"])

        with pytest.raises(RuntimeError) as captured:
            command.upgrade(config, _RU_V3_MIGRATION_REVISION)

        assert str(captured.value) == _RU_V3_UPGRADE_BLOCKED_MESSAGE
        assert _migration_revision(engine) == _RU_V3_PREVIOUS_MIGRATION_REVISION
        assert _record_row(engine, target_row["record_id"]) == before
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    """
                    SELECT count(*) FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                      AND record_schema_version =
                          'request_understanding_record.p0.v3'
                    """
                )
            ) == 0
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_ru_v3_downgrade_blocks_cycle2_continuation_without_mutation(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("ru-v3-downgrade-blocker")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    staged = _dnr_v3_staging_command(with_current_dnr=True)
    try:
        _seed_continuation_roots(adapter, staged)
        assert asyncio.run(
            adapter.apply_continuation_task_delta_if_current(staged)
        ).value == "APPLIED"
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT record_id FROM p0_records
                    WHERE record_code = 'request_understanding_record'
                    """
                )
            ).mappings().one()
        before = _record_row(engine, row["record_id"])

        with pytest.raises(RuntimeError) as captured:
            command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)

        assert str(captured.value) == _RU_V3_DOWNGRADE_BLOCKED_MESSAGE
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
        assert _record_row(engine, row["record_id"]) == before
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize("direction", ("upgrade", "downgrade"))
def test_ru_v3_cutover_lock_blocks_record_and_reference_dml(
    postgres_namespace_factory,
    direction: str,
) -> None:
    namespace = postgres_namespace_factory.create(f"ru-v3-{direction}-lock")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    if direction == "upgrade":
        command.downgrade(config, _RU_V3_PREVIOUS_MIGRATION_REVISION)
        migrate = lambda: command.upgrade(config, _RU_V3_MIGRATION_REVISION)
        expected_revision = _RU_V3_MIGRATION_REVISION
    else:
        migrate = lambda: command.downgrade(
            config,
            _RU_V3_PREVIOUS_MIGRATION_REVISION,
        )
        expected_revision = _RU_V3_PREVIOUS_MIGRATION_REVISION
    barrier_connection = engine.connect()
    barrier_transaction = barrier_connection.begin()
    executor = ThreadPoolExecutor(max_workers=1)
    future = None
    try:
        barrier_connection.execute(
            text("LOCK TABLE p0_records IN ACCESS SHARE MODE")
        )
        future = executor.submit(migrate)
        _wait_for_real_downgrade_lock(
            engine,
            schema=namespace.schema,
            relation_name="p0_records",
        )
        _assert_lock_timeout(
            engine,
            text(
                """
                INSERT INTO p0_records (
                    record_id, record_code, record_schema_version,
                    logical_identity, envelope
                ) VALUES (
                    :record_id, 'conversation_record',
                    'conversation_record.p0.v1',
                    CAST(:identity AS jsonb), CAST(:envelope AS jsonb)
                )
                """
            ),
            parameters={
                "record_id": uuid4(),
                "identity": json.dumps([["conversation_id", str(uuid4())]]),
                "envelope": "{}",
            },
        )
        _assert_lock_timeout(
            engine,
            text(
                """
                INSERT INTO p0_record_references (
                    reference_id, source_record_code,
                    source_logical_identity, ordinal, relation,
                    target_record_code, target_logical_identity
                ) VALUES (
                    :reference_id, 'conversation_record',
                    CAST(:source_identity AS jsonb), 0, 'probe',
                    'conversation_record',
                    CAST(:target_identity AS jsonb)
                )
                """
            ),
            parameters={
                "reference_id": uuid4(),
                "source_identity": json.dumps(
                    [["conversation_id", str(uuid4())]]
                ),
                "target_identity": json.dumps(
                    [["conversation_id", str(uuid4())]]
                ),
            },
        )
    finally:
        barrier_transaction.rollback()
        barrier_connection.close()
        executor.shutdown(wait=True)
    assert future is not None
    assert future.result(timeout=10) is None
    assert _migration_revision(engine) == expected_revision
    engine.dispose()
    postgres_namespace_factory.drop(namespace)


def test_record_history_correction_source_is_self_contained_and_frozen() -> None:
    source = _RECORD_HISTORY_MIGRATION_PATH.read_text()
    tree = ast.parse(source)

    assert "mini_agent" not in source
    assert _module_literal(tree, "revision") == _RECORD_HISTORY_MIGRATION_REVISION
    assert _module_literal(tree, "down_revision") == (
        _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION
    )
    assert _module_literal(tree, "branch_labels") is None
    assert _module_literal(tree, "depends_on") is None
    assert _module_literal(tree, "_HISTORY_CODE_VERSION_PAIRS") == (
        _RECORD_HISTORY_CODE_VERSION_PAIRS
    )
    assert _RECORD_HISTORY_DOWNGRADE_BLOCKED_MESSAGE in source
    assert _RECORD_HISTORY_APPEND_ONLY_MESSAGE in source
    assert _RECORD_HISTORY_APPEND_ONLY_FUNCTION in source
    assert _RECORD_HISTORY_ROW_MUTATION_TRIGGER in source
    assert _RECORD_HISTORY_TRUNCATE_TRIGGER in source
    assert "FROM p0_records" not in source
    assert "INSERT INTO p0_record_state_history" not in source


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
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
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
        command.upgrade(phase1_config, _RU_V3_MIGRATION_REVISION)

        assert _migration_revision(empty_engine) == (
            _RU_V3_MIGRATION_REVISION
        )
        assert _migration_revision(phase1_engine) == (
            _RU_V3_MIGRATION_REVISION
        )
        assert _schema_structure(phase1_engine) == empty_structure
        with phase1_engine.connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(P0RecordStateHistoryModel)
            ) == 0
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
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
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
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
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


def test_record_history_upgrade_does_not_backfill_current_records(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("record-history-no-backfill")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    try:
        command.downgrade(config, _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION)
        history_values = (
            _history_probe_values(P0RecordCode.TASK_RECORD),
            _history_probe_values(P0RecordCode.REQUEST_UNIT_RECORD),
        )
        with engine.begin() as connection:
            for values in history_values:
                connection.execute(
                    P0RecordModel.__table__.insert().values(
                        record_id=uuid4(),
                        record_code=values["record_code"],
                        record_schema_version=values["record_schema_version"],
                        logical_identity=values["logical_identity"],
                        direct_owner_customer_id=(
                            values["scope_owner_customer_id"]
                            if values["record_code"] == "task_record"
                            else None
                        ),
                        scope_owner_customer_id=values[
                            "scope_owner_customer_id"
                        ],
                        state_version=values["state_version"],
                        envelope=values["envelope"],
                    )
                )

        command.upgrade(config, _RECORD_HISTORY_MIGRATION_REVISION)

        with engine.connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(P0RecordModel)
            ) == 2
            assert connection.scalar(
                select(func.count()).select_from(P0RecordStateHistoryModel)
            ) == 0
        assert _migration_revision(engine) == _RECORD_HISTORY_MIGRATION_REVISION
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_record_history_admission_owner_lookup_and_current_row_decoupling(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    task_identity = uuid4()
    task_v1 = _history_probe_values(
        P0RecordCode.TASK_RECORD,
        identity=task_identity,
        state_version=1,
    )
    request_unit = _history_probe_values(P0RecordCode.REQUEST_UNIT_RECORD)
    task_v2 = _history_probe_values(
        P0RecordCode.TASK_RECORD,
        identity=task_identity,
        state_version=2,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                P0RecordStateHistoryModel.__table__.insert(),
                (task_v1, request_unit, task_v2),
            )

        with engine.connect() as connection:
            assert connection.scalar(
                select(P0RecordStateHistoryModel.history_id).where(
                    P0RecordStateHistoryModel.scope_owner_customer_id
                    == "customer-history",
                    P0RecordStateHistoryModel.record_code == "task_record",
                    P0RecordStateHistoryModel.logical_identity
                    == task_v1["logical_identity"],
                    P0RecordStateHistoryModel.state_version == 1,
                )
            ) == task_v1["history_id"]
            assert connection.scalar(
                select(P0RecordStateHistoryModel.history_id).where(
                    P0RecordStateHistoryModel.scope_owner_customer_id
                    == "customer-foreign",
                    P0RecordStateHistoryModel.record_code == "task_record",
                    P0RecordStateHistoryModel.logical_identity
                    == task_v1["logical_identity"],
                    P0RecordStateHistoryModel.state_version == 1,
                )
            ) is None

        conflicting_duplicate = {
            **task_v1,
            "history_id": uuid4(),
            "envelope": {"private_conflict": "must-fail-closed"},
        }
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    P0RecordStateHistoryModel.__table__.insert().values(
                        **conflicting_duplicate
                    )
                )

        current_record_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                P0RecordModel.__table__.insert().values(
                    record_id=current_record_id,
                    record_code=task_v2["record_code"],
                    record_schema_version=task_v2["record_schema_version"],
                    logical_identity=task_v2["logical_identity"],
                    direct_owner_customer_id="customer-history",
                    scope_owner_customer_id="customer-history",
                    state_version=task_v2["state_version"],
                    envelope=task_v2["envelope"],
                )
            )
            connection.execute(
                P0RecordModel.__table__.delete().where(
                    P0RecordModel.record_id == current_record_id
                )
            )
        with engine.connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(P0RecordStateHistoryModel)
            ) == 3
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("update", "drop_history_id"),
    (
        ({"record_code": "agent_run_record"}, False),
        ({"record_schema_version": "request_unit_record.p0.v1"}, False),
        ({"logical_identity": {"task_id": "not-an-array"}}, False),
        ({"scope_owner_customer_id": ""}, False),
        ({"state_version": 0}, False),
        ({"envelope": ["not-an-object"]}, False),
        ({}, True),
    ),
)
def test_record_history_rejects_invalid_physical_admission(
    eval_postgres_namespace,
    update: dict[str, object],
    drop_history_id: bool,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    values = {
        **_history_probe_values(P0RecordCode.TASK_RECORD),
        **update,
    }
    try:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                if drop_history_id:
                    connection.execute(
                        text(
                            """
                            INSERT INTO p0_record_state_history (
                                record_code,
                                record_schema_version,
                                logical_identity,
                                scope_owner_customer_id,
                                state_version,
                                envelope
                            ) VALUES (
                                'task_record',
                                'task_record.p0.v1',
                                '[]'::jsonb,
                                'customer-history',
                                1,
                                '{}'::jsonb
                            )
                            """
                        )
                    )
                else:
                    connection.execute(
                        P0RecordStateHistoryModel.__table__.insert().values(
                            **values
                        )
                    )
    finally:
        engine.dispose()


def test_record_history_schema_is_exact_and_has_no_current_row_foreign_key(
    postgres_namespace,
) -> None:
    engine = postgres_namespace.build_engine()
    try:
        assert persistence_models._HISTORY_CODE_VERSION_PAIRS == (
            _RECORD_HISTORY_CODE_VERSION_PAIRS
        )
        inspector = inspect(engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("p0_record_state_history")
        }
        assert set(columns) == {
            "history_id",
            "record_code",
            "record_schema_version",
            "logical_identity",
            "scope_owner_customer_id",
            "state_version",
            "envelope",
            "archived_at",
        }
        assert columns["history_id"]["nullable"] is False
        assert columns["history_id"]["default"] is None
        assert columns["archived_at"]["nullable"] is False
        assert columns["archived_at"]["default"] is not None
        assert inspector.get_pk_constraint("p0_record_state_history")[
            "constrained_columns"
        ] == ["history_id"]
        assert {
            item["name"]
            for item in inspector.get_unique_constraints(
                "p0_record_state_history"
            )
        } == {"uq_p0_record_state_history_logical_version"}
        assert {
            item["name"]
            for item in inspector.get_check_constraints(
                "p0_record_state_history"
            )
        } == {
            "ck_p0_record_state_history_code_closed",
            "ck_p0_record_state_history_code_version_closed",
            "ck_p0_record_state_history_envelope_object",
            "ck_p0_record_state_history_logical_identity_array",
            "ck_p0_record_state_history_owner_nonempty",
            "ck_p0_record_state_history_state_version_positive",
        }
        indexes = {
            item["name"]: item
            for item in inspector.get_indexes("p0_record_state_history")
            if not item.get("duplicates_constraint")
        }
        assert set(indexes) == {"ix_p0_record_state_history_owner_lookup"}
        assert indexes["ix_p0_record_state_history_owner_lookup"][
            "column_names"
        ] == [
            "scope_owner_customer_id",
            "record_code",
            "logical_identity",
            "state_version",
        ]
        assert inspector.get_foreign_keys("p0_record_state_history") == []
        with engine.connect() as connection:
            triggers = set(
                connection.scalars(
                    text(
                        """
                        SELECT trigger.tgname
                        FROM pg_trigger AS trigger
                        JOIN pg_class AS relation
                          ON relation.oid = trigger.tgrelid
                        JOIN pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = current_schema()
                          AND relation.relname = 'p0_record_state_history'
                          AND NOT trigger.tgisinternal
                        """
                    )
                )
            )
            functions = set(
                connection.scalars(
                    text(
                        """
                        SELECT procedure.proname
                        FROM pg_proc AS procedure
                        JOIN pg_namespace AS namespace
                          ON namespace.oid = procedure.pronamespace
                        WHERE namespace.nspname = current_schema()
                          AND procedure.proname =
                              :append_only_function
                        """
                    ),
                    {
                        "append_only_function": (
                            _RECORD_HISTORY_APPEND_ONLY_FUNCTION
                        )
                    },
                )
            )
        assert triggers == {
            _RECORD_HISTORY_ROW_MUTATION_TRIGGER,
            _RECORD_HISTORY_TRUNCATE_TRIGGER,
        }
        assert functions == {_RECORD_HISTORY_APPEND_ONLY_FUNCTION}
        assert P0RecordStateHistoryModel.__table__.c.history_id.default is None
        assert (
            P0RecordStateHistoryModel.__table__.c.history_id.server_default
            is None
        )
        assert (
            P0RecordStateHistoryModel.__table__.c.archived_at.server_default
            is not None
        )
    finally:
        engine.dispose()


def test_record_history_database_is_append_only_but_accepts_insert(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("record-history-append-only")
    engine = namespace.build_engine()
    values = _history_probe_values(
        P0RecordCode.TASK_RECORD,
        owner_customer_id="must-not-leak-append-only-owner",
    )

    def stored_row() -> dict[str, object]:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    select(P0RecordStateHistoryModel.__table__).where(
                        P0RecordStateHistoryModel.history_id
                        == values["history_id"]
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)

    try:
        with engine.begin() as connection:
            connection.execute(
                P0RecordStateHistoryModel.__table__.insert().values(**values)
            )
        original = stored_row()

        rejected_mutations = (
            P0RecordStateHistoryModel.__table__.update()
            .where(
                P0RecordStateHistoryModel.history_id == values["history_id"]
            )
            .values(envelope={"private_marker": "must-not-leak-update"}),
            P0RecordStateHistoryModel.__table__.delete().where(
                P0RecordStateHistoryModel.history_id == values["history_id"]
            ),
            text("TRUNCATE TABLE p0_record_state_history"),
        )
        for mutation in rejected_mutations:
            with pytest.raises(DBAPIError) as captured:
                with engine.begin() as connection:
                    connection.execute(mutation)

            driver_error = captured.value.orig
            assert getattr(driver_error, "sqlstate", None) == "55000"
            primary_message = driver_error.diag.message_primary
            assert primary_message == _RECORD_HISTORY_APPEND_ONLY_MESSAGE
            assert "must-not-leak-append-only-owner" not in primary_message
            assert "must-not-leak-update" not in primary_message
            assert str(values["history_id"]) not in primary_message
            assert stored_row() == original

        second_values = _history_probe_values(
            P0RecordCode.REQUEST_UNIT_RECORD,
            owner_customer_id="customer-history-second-insert",
        )
        with engine.begin() as connection:
            connection.execute(
                P0RecordStateHistoryModel.__table__.insert().values(
                    **second_values
                )
            )
        with engine.connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(P0RecordStateHistoryModel)
            ) == 2
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


@pytest.mark.parametrize(
    "record_code",
    (P0RecordCode.TASK_RECORD, P0RecordCode.REQUEST_UNIT_RECORD),
)
def test_record_history_downgrade_blocks_any_history_before_mutation(
    postgres_namespace_factory,
    record_code: P0RecordCode,
) -> None:
    namespace = postgres_namespace_factory.create(
        f"record-history-downgrade-{record_code.value}"
    )
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    values = _history_probe_values(
        record_code,
        owner_customer_id="must-not-leak-history-owner",
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                P0RecordStateHistoryModel.__table__.insert().values(**values)
            )

        with pytest.raises(RuntimeError) as captured:
            command.downgrade(
                config,
                _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION,
            )

        assert str(captured.value) == _RECORD_HISTORY_DOWNGRADE_BLOCKED_MESSAGE
        assert "must-not-leak-history-owner" not in str(captured.value)
        assert str(values["history_id"]) not in str(captured.value)
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
        assert "p0_record_state_history" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(
                select(P0RecordStateHistoryModel.history_id)
            ) == values["history_id"]
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_empty_record_history_downgrade_is_reversible_and_preserves_current_rows(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("record-history-empty-downgrade")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    current = _history_probe_values(P0RecordCode.TASK_RECORD)
    current_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                P0RecordModel.__table__.insert().values(
                    record_id=current_id,
                    record_code=current["record_code"],
                    record_schema_version=current["record_schema_version"],
                    logical_identity=current["logical_identity"],
                    direct_owner_customer_id=current[
                        "scope_owner_customer_id"
                    ],
                    scope_owner_customer_id=current[
                        "scope_owner_customer_id"
                    ],
                    state_version=current["state_version"],
                    envelope=current["envelope"],
                )
            )

        command.downgrade(config, _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION)
        assert "p0_record_state_history" not in inspect(engine).get_table_names()
        assert _migration_revision(engine) == (
            _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION
        )
        assert _record_row(engine, current_id)["record_id"] == current_id

        command.upgrade(config, _RECORD_HISTORY_MIGRATION_REVISION)
        with engine.connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(P0RecordStateHistoryModel)
            ) == 0
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_record_history_downgrade_lock_blocks_history_dml(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("record-history-lock-contract")
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
        assert barrier_connection.scalar(
            select(func.count()).select_from(P0RecordStateHistoryModel)
        ) == 0
        downgrade_future = executor.submit(
            command.downgrade,
            config,
            _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION,
        )
        _wait_for_real_downgrade_lock(
            engine,
            schema=namespace.schema,
            relation_name="p0_record_state_history",
        )

        _assert_lock_timeout(
            engine,
            P0RecordStateHistoryModel.__table__.insert().values(
                **_history_probe_values(P0RecordCode.TASK_RECORD)
            ),
        )
        _assert_lock_timeout(
            engine,
            P0RecordStateHistoryModel.__table__.update().values(
                archived_at=datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)
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
            _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION
        )
    finally:
        engine.dispose()
        postgres_namespace_factory.drop(namespace)


def test_record_history_downgrade_waits_for_prior_insert_then_fails_bounded(
    postgres_namespace_factory,
) -> None:
    namespace = postgres_namespace_factory.create("record-history-prior-insert")
    engine = namespace.build_engine()
    config = alembic_config(
        namespace.database_url,
        schema=namespace.schema,
        testing=True,
    )
    writer_connection = engine.connect()
    writer_transaction = writer_connection.begin()
    executor = ThreadPoolExecutor(max_workers=1)
    downgrade_future = None
    values = _history_probe_values(
        P0RecordCode.TASK_RECORD,
        owner_customer_id="must-not-leak-prior-history",
    )
    try:
        writer_connection.execute(
            P0RecordStateHistoryModel.__table__.insert().values(**values)
        )
        downgrade_future = executor.submit(
            command.downgrade,
            config,
            _RECORD_HISTORY_PREVIOUS_MIGRATION_REVISION,
        )
        _wait_for_pending_table_lock(
            engine,
            schema=namespace.schema,
            relation_name="p0_record_state_history",
            mode="ShareRowExclusiveLock",
        )

        writer_transaction.commit()
        writer_connection.close()
        writer_transaction = None
        writer_connection = None

        with pytest.raises(RuntimeError) as captured:
            downgrade_future.result(timeout=10)
        assert str(captured.value) == _RECORD_HISTORY_DOWNGRADE_BLOCKED_MESSAGE
        assert "must-not-leak-prior-history" not in str(captured.value)
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
        with engine.connect() as connection:
            assert connection.scalar(
                select(P0RecordStateHistoryModel.history_id)
            ) == values["history_id"]
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
            "p0_record_state_history",
            "p0_records",
        }
        assert set(Base.metadata.tables) == {
            "mock_order_search_documents",
            "mock_order_search_snapshots",
            "mock_orders",
            "mock_shipments",
            "p0_record_references",
            "p0_record_state_history",
            "p0_records",
        }
        assert P0RecordModel.__tablename__ == "p0_records"
        assert P0RecordReferenceModel.__tablename__ == "p0_record_references"
        assert P0RecordStateHistoryModel.__tablename__ == (
            "p0_record_state_history"
        )
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
            ) == (_RU_V3_MIGRATION_REVISION)
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
    assert len(physical_literal) == len(set(physical_literal)) == 30

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
            assert connection.scalar(text("SELECT count(*) FROM p0_records")) == 30

        unsupported_pairs = (
            (
                "conversation_record",
                "request_understanding_record.p0.v2",
            ),
            (
                "request_understanding_record",
                "request_understanding_record.p0.v4",
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
        assert _migration_revision(engine) == _RU_V3_MIGRATION_REVISION
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
            "p0_record_state_history",
            "p0_records",
        }
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == _RU_V3_MIGRATION_REVISION
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
