"""Admit and atomically convert the reviewed Cycle 2 record families.

Revision ID: 20260731_0004
Revises: 20260728_0003
Create Date: 2026-07-31
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mini_agent.application.persistence import (
    P0ConversionReadiness,
    P0PersistenceEnvelope,
    P0RecordCode,
    P0RecordReference,
    classify_p0_conversion_readiness,
    decode_persistence_record_versioned,
    encode_persistence_record_versioned,
)
from mini_agent.application.records import (
    RUN_TASK_LINK_RECORD_V2_SCHEMA_VERSION,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    ToolRetryRecoveryDecisionRecordV2,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    InputBinding,
    InputBindingV2,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
)
from mini_agent.core.tool_system import (
    ExecutionPolicy,
    GateDecision,
    GateDecisionV2,
    RegistrySnapshot,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolEffect,
    ToolRegistration,
    build_cycle2_registry_snapshot,
    get_order_tool_spec,
)
from mini_agent.core.trace import (
    AgentRunRecord,
    AgentRunRecordV2,
    TraceEvent,
    TraceEventV2,
)

revision: str = "20260731_0004"
down_revision: str | Sequence[str] | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RECORD_CODE_CONSTRAINT = "ck_p0_records_code_closed"
_CODE_VERSION_CONSTRAINT = "ck_p0_records_code_version_closed"
_MIGRATION_BLOCKED_MESSAGE = "cycle2 record migration graph is not exactly convertible"
_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade cycle2 physical schema after v2-only evidence"
)

_HISTORICAL_CODE_VERSION_PAIRS = (
    ("agent_run_record", "agent_run_record.p0.v1"),
    ("context_manifest_record", "context_manifest_record.p0.v1"),
    ("conversation_record", "conversation_record.p0.v1"),
    ("conversation_task_link_record", "conversation_task_link_record.p0.v1"),
    ("eval_execution_failure_record", "eval_execution_failure_record.p0.v1"),
    ("eval_result_record", "eval_result_record.p0.v1"),
    ("gate_decision_record", "gate_decision_record.p0.v1"),
    ("input_binding_record", "input_binding_record.p0.v1"),
    ("message_record", "message_record.p0.v1"),
    ("model_visible_toolset_artifact", "model_visible_toolset_artifact.p0.v1"),
    ("observation_record", "observation_record.p0.v1"),
    ("request_understanding_record", "request_understanding_record.p0.v1"),
    ("request_unit_record", "request_unit_record.p0.v1"),
    ("run_task_link_record", "run_task_link_record.p0.v1"),
    ("task_record", "task_record.p0.v1"),
    ("tool_call_record", "tool_call_record.p0.v1"),
    ("trace_event_record", "trace_event_record.p0.v1"),
    ("request_understanding_record", "request_understanding_record.p0.v2"),
)

_CYCLE2_NEW_PAIRS = (
    ("order_search_observation_record", "order_search_observation_record.p0.v1"),
    ("order_candidate_set_record", "order_candidate_set_record.p0.v1"),
    ("order_candidate_selection_record", "order_candidate_selection_record.p0.v1"),
    ("shipment_observation_record", "shipment_observation_record.p0.v1"),
    ("shipment_assessment_record", "shipment_assessment_record.p0.v1"),
)

_CONVERSION_PAIRS = (
    (
        "input_binding_record",
        "input_binding_record.p0.v1",
        "input_binding_record.p0.v2",
    ),
    (
        "gate_decision_record",
        "gate_decision_record.p0.v1",
        "gate_decision_record.p0.v2",
    ),
    ("tool_call_record", "tool_call_record.p0.v1", "tool_call_record.p0.v2"),
    ("agent_run_record", "agent_run_record.p0.v1", "agent_run_record.p0.v2"),
    (
        "run_task_link_record",
        "run_task_link_record.p0.v1",
        "run_task_link_record.p0.v2",
    ),
    ("trace_event_record", "trace_event_record.p0.v1", "trace_event_record.p0.v2"),
)

_PHYSICAL_CODE_VERSION_PAIRS = (
    *_HISTORICAL_CODE_VERSION_PAIRS,
    *_CYCLE2_NEW_PAIRS,
    ("input_binding_record", "input_binding_record.p0.v2"),
    ("gate_decision_record", "gate_decision_record.p0.v2"),
    ("tool_call_record", "tool_call_record.p0.v2"),
    ("agent_run_record", "agent_run_record.p0.v2"),
    ("run_task_link_record", "run_task_link_record.p0.v2"),
    ("trace_event_record", "trace_event_record.p0.v2"),
)

_V2_BY_CODE = {code: target for code, _, target in _CONVERSION_PAIRS}
_V1_BY_CODE = {code: source for code, source, _ in _CONVERSION_PAIRS}
_NEW_CODES = tuple(code for code, _ in _CYCLE2_NEW_PAIRS)


def _condition(pairs: Sequence[tuple[str, str]]) -> str:
    return " OR ".join(
        f"(record_code = '{code}' AND record_schema_version = '{version}')"
        for code, version in pairs
    )


def _replace_record_constraints(pairs: Sequence[tuple[str, str]]) -> None:
    op.drop_constraint(_CODE_VERSION_CONSTRAINT, "p0_records", type_="check")
    op.drop_constraint(_RECORD_CODE_CONSTRAINT, "p0_records", type_="check")
    codes = tuple(dict.fromkeys(code for code, _ in pairs))
    op.create_check_constraint(
        _RECORD_CODE_CONSTRAINT,
        "p0_records",
        "record_code IN (" + ", ".join(f"'{code}'" for code in codes) + ")",
    )
    op.create_check_constraint(
        _CODE_VERSION_CONSTRAINT,
        "p0_records",
        _condition(pairs),
    )


def _phase1_registry_snapshot() -> RegistrySnapshot:
    return RegistrySnapshot.build(
        tool_registry_version="e2e01-thin-tools-v1",
        registrations=(
            ToolRegistration(
                tool_spec=get_order_tool_spec(),
                provider_visible_name="get_order",
                effect=ToolEffect.READ,
                risk="LOW",
                idempotency="READ_ONLY",
                handler_ref="orders.get_order",
                execution_policy=ExecutionPolicy(
                    timeout_ms=500,
                    max_attempts=1,
                    interrupt_behavior="MARK_INTERRUPTED",
                ),
            ),
        ),
    )


def _envelope(raw: object) -> P0PersistenceEnvelope:
    return P0PersistenceEnvelope.model_validate_json(
        json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
        strict=True,
    )


def _reorder_json_like(raw: object, template: object) -> object:
    if isinstance(raw, dict) and isinstance(template, dict):
        result = {
            key: _reorder_json_like(raw[key], template[key])
            for key in template
            if key in raw
        }
        result.update((key, value) for key, value in raw.items() if key not in result)
        return result
    if isinstance(raw, list) and isinstance(template, list):
        return [
            _reorder_json_like(
                value,
                template[index] if index < len(template) else None,
            )
            for index, value in enumerate(raw)
        ]
    return raw


def _decode_input(raw: object, code: str, version: str) -> object:
    model_by_pair = {
        ("input_binding_record", "input_binding_record.p0.v2"): InputBindingV2,
        ("gate_decision_record", "gate_decision_record.p0.v2"): GateDecisionV2,
        ("tool_call_record", "tool_call_record.p0.v2"): ToolCallRecordV2,
        ("agent_run_record", "agent_run_record.p0.v2"): AgentRunRecordV2,
        (
            "run_task_link_record",
            RUN_TASK_LINK_RECORD_V2_SCHEMA_VERSION,
        ): RunTaskLinkRecordV2,
        ("trace_event_record", "trace_event_record.p0.v2"): TraceEventV2,
        (
            "request_understanding_record",
            "request_understanding_record.p0.v2",
        ): RequestUnderstandingRecordV2,
    }
    model = model_by_pair.get((code, version))
    if model is None or not isinstance(raw, dict):
        return raw
    normalized = json.loads(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    payload = normalized.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return raw
    source = model.model_validate_json(
        json.dumps(payload["data"], ensure_ascii=False, separators=(",", ":")),
        strict=True,
    )
    payload["data"] = _reorder_json_like(
        payload["data"],
        source.model_dump(mode="json", warnings="error"),
    )
    children = payload.get("logical_children")
    if code == "tool_call_record" and isinstance(children, list):
        child_model_by_code = {
            "tool_attempt_record": ToolAttemptRecordV2,
            "tool_retry_recovery_decision_record": ToolRetryRecoveryDecisionRecordV2,
        }
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get("data"), dict):
                return raw
            child_model = child_model_by_code.get(child.get("child_code"))
            if child_model is None:
                return raw
            parsed_child = child_model.model_validate_json(
                json.dumps(child["data"], ensure_ascii=False, separators=(",", ":")),
                strict=True,
            )
            child["data"] = _reorder_json_like(
                child["data"],
                parsed_child.model_dump(mode="json", warnings="error"),
            )
    elif code == "request_understanding_record" and isinstance(children, list):
        for child in children:
            if (
                not isinstance(child, dict)
                or child.get("child_code") != "accepted_task_delta"
                or not isinstance(child.get("data"), dict)
            ):
                return raw
            parsed_child = AcceptedTaskDeltaV2.model_validate_json(
                json.dumps(
                    child["data"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )
            child["data"] = _reorder_json_like(
                child["data"],
                parsed_child.model_dump(mode="json", warnings="error"),
            )
    return normalized


def _references(
    connection: sa.Connection, row: Mapping[str, Any]
) -> tuple[P0RecordReference, ...]:
    raw_references = (
        connection.execute(
            sa.text(
                """
            SELECT ordinal, relation, target_record_code, target_logical_identity
            FROM p0_record_references
            WHERE source_record_code = :record_code
              AND source_logical_identity = CAST(:logical_identity AS jsonb)
            ORDER BY ordinal
            """
            ),
            {
                "record_code": row["record_code"],
                "logical_identity": json.dumps(
                    row["logical_identity"], separators=(",", ":")
                ),
            },
        )
        .mappings()
        .all()
    )
    if tuple(reference["ordinal"] for reference in raw_references) != tuple(
        range(len(raw_references))
    ):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    return tuple(
        P0RecordReference.model_validate_json(
            json.dumps(
                {
                    "relation": reference["relation"],
                    "target_record_code": reference["target_record_code"],
                    "target_logical_identity": reference["target_logical_identity"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
        for reference in raw_references
    )


def _enum_value(value: object) -> str | None:
    return str(value.value) if isinstance(value, Enum) else None


def _external_references(
    code: str,
    references: tuple[P0RecordReference, ...],
) -> tuple[P0RecordReference, ...]:
    if code != "input_binding_record":
        return ()
    return tuple(
        reference
        for reference in references
        if reference.relation == "request_unit_id"
        and reference.target_record_code is P0RecordCode.REQUEST_UNIT_RECORD
    )


def _projection(
    envelope: P0PersistenceEnvelope, record: object, code: str
) -> dict[str, object]:
    def uuid_field(name: str) -> UUID | None:
        value = getattr(record, name, None)
        return value if type(value) is UUID else None

    state_version = getattr(record, "state_version", None)
    attempt_count = getattr(record, "attempt_count", None)
    return {
        "record_schema_version": envelope.record_schema_version,
        "logical_identity": [list(item) for item in envelope.logical_identity],
        "direct_owner_customer_id": envelope.direct_owner_customer_id,
        "conversation_id": uuid_field("conversation_id"),
        "run_id": uuid_field("run_id"),
        "task_id": uuid_field("task_id"),
        "request_unit_id": uuid_field("request_unit_id"),
        "lifecycle_status": _enum_value(getattr(record, "status", None)),
        "state_version": state_version if type(state_version) is int else None,
        "attempt_count": attempt_count if type(attempt_count) is int else None,
        "recovery_sort_at": getattr(record, "started_at", None)
        if code == "agent_run_record"
        else None,
    }


def _assert_physical_projection(
    row: Mapping[str, Any],
    envelope: P0PersistenceEnvelope,
    record: object,
) -> None:
    expected = _projection(envelope, record, row["record_code"])
    if any(row[field] != value for field, value in expected.items()):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    if (
        row["scope_owner_customer_id"] is None
        and envelope.direct_owner_customer_id is not None
    ):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    if (
        envelope.direct_owner_customer_id is not None
        and row["scope_owner_customer_id"] != envelope.direct_owner_customer_id
    ):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)


def _decode_rows(
    connection: sa.Connection,
) -> tuple[list[Mapping[str, Any]], dict[UUID, tuple[object, tuple[object, ...]]]]:
    rows = list(
        connection.execute(
            sa.text(
                "SELECT * FROM p0_records ORDER BY record_code, record_id FOR UPDATE"
            )
        ).mappings()
    )
    decoded: dict[UUID, tuple[object, tuple[object, ...]]] = {}
    known_pairs = set(_PHYSICAL_CODE_VERSION_PAIRS)
    for row in rows:
        pair = (row["record_code"], row["record_schema_version"])
        if pair not in known_pairs:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        envelope = _envelope(row["envelope"])
        references = _references(connection, row)
        if (
            envelope.record_code.value != row["record_code"]
            or envelope.record_schema_version != row["record_schema_version"]
            or [list(item) for item in envelope.logical_identity]
            != row["logical_identity"]
            or envelope.record_references != references
        ):
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        if pair == (
            "request_understanding_record",
            "request_understanding_record.p0.v1",
        ):
            continue
        result = decode_persistence_record_versioned(
            _decode_input(
                row["envelope"],
                row["record_code"],
                row["record_schema_version"],
            ),
            expected_record_code=P0RecordCode(row["record_code"]),
            expected_schema_version=row["record_schema_version"],
            correlation_ref=uuid4(),
        )
        _assert_physical_projection(row, envelope, result.source_record)
        decoded[row["record_id"]] = (result.source_record, result.logical_children)
    return rows, decoded


def _index_decoded(
    rows: Sequence[Mapping[str, Any]],
    decoded: Mapping[UUID, tuple[object, tuple[object, ...]]],
) -> dict[tuple[str, UUID], object]:
    result: dict[tuple[str, UUID], object] = {}
    identity_field = {
        "task_record": "task_id",
        "request_unit_record": "request_unit_id",
        "input_binding_record": "binding_id",
    }
    for row in rows:
        field = identity_field.get(row["record_code"])
        item = decoded.get(row["record_id"])
        if field is None or item is None:
            continue
        identity = getattr(item[0], field, None)
        if type(identity) is not UUID or (row["record_code"], identity) in result:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        result[(row["record_code"], identity)] = item[0]
    return result


def _trusted_owner_scope(customer_id: str) -> TrustedOwnerScope:
    context = CustomerContext(
        subject_ref="cycle2-migration-subject",
        customer_id=customer_id,
        auth_scopes=frozenset({"orders:read"}),
        authenticated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        session_ref_hash="cycle2-migration-session",
    )
    return TrustedOwnerScope.from_customer_context(context)


def _classification(
    row: Mapping[str, Any],
    source: object,
    children: tuple[object, ...],
    index: Mapping[tuple[str, UUID], object],
    active_versions: tuple[str, ...],
    references: tuple[P0RecordReference, ...],
) -> P0ConversionReadiness:
    kwargs: dict[str, object] = {}
    if row["record_code"] == "tool_call_record":
        if type(source) is not ToolCallRecord:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        task = index.get(("task_record", source.task_id))
        request_unit = index.get(("request_unit_record", source.request_unit_id))
        bindings = tuple(
            index.get(("input_binding_record", binding_id))
            for binding_id in source.argument_binding_refs
        )
        if (
            type(task) is not TaskRecord
            or type(request_unit) is not RequestUnitRecord
            or any(type(binding) is not InputBinding for binding in bindings)
            or type(row["scope_owner_customer_id"]) is not str
        ):
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        kwargs = {
            "owner_scope": _trusted_owner_scope(row["scope_owner_customer_id"]),
            "source_task_record": task,
            "source_request_unit_record": request_unit,
            "source_argument_binding_records": bindings,
            "source_registry_snapshot": _phase1_registry_snapshot(),
            "target_registry_snapshot": build_cycle2_registry_snapshot(),
        }
    return classify_p0_conversion_readiness(
        P0RecordCode(row["record_code"]),
        row["record_schema_version"],
        _V2_BY_CODE[row["record_code"]],
        source,
        active_schema_versions=active_versions,
        external_references=_external_references(
            row["record_code"],
            references,
        ),
        source_logical_children=children,
        **kwargs,
    )


def _prepare_upgrade(
    connection: sa.Connection,
) -> list[tuple[UUID, P0PersistenceEnvelope, object]]:
    rows, decoded = _decode_rows(connection)
    index = _index_decoded(rows, decoded)
    versions_by_code = {
        code: tuple(
            sorted(
                {
                    row["record_schema_version"]
                    for row in rows
                    if row["record_code"] == code
                }
            )
        )
        for code in _V2_BY_CODE
    }
    prepared: list[tuple[UUID, P0PersistenceEnvelope, object]] = []
    for row in rows:
        if row["record_code"] not in _V2_BY_CODE:
            continue
        source_and_children = decoded.get(row["record_id"])
        if source_and_children is None:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        source, children = source_and_children
        references = _references(connection, row)
        readiness = _classification(
            row,
            source,
            children,
            index,
            versions_by_code[row["record_code"]],
            references,
        )
        if not readiness.is_ready or readiness.target_record is None:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        target = encode_persistence_record_versioned(
            P0RecordCode(row["record_code"]),
            _V2_BY_CODE[row["record_code"]],
            readiness.target_record,
            external_references=_external_references(
                row["record_code"],
                references,
            ),
            logical_children=readiness.target_logical_children,
        )
        if target.logical_identity != _envelope(row["envelope"]).logical_identity:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        if target.record_references != references:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
        prepared.append((row["record_id"], target, readiness.target_record))
    return prepared


def _write_prepared(
    connection: sa.Connection,
    prepared: Sequence[tuple[UUID, P0PersistenceEnvelope, object]],
) -> None:
    for record_id, envelope, record in prepared:
        values = _projection(envelope, record, envelope.record_code.value)
        values["envelope"] = envelope.model_dump(mode="json", warnings="error")
        result = connection.execute(
            sa.text(
                """
                UPDATE p0_records
                SET record_schema_version = :record_schema_version,
                    logical_identity = CAST(:logical_identity AS jsonb),
                    direct_owner_customer_id = :direct_owner_customer_id,
                    conversation_id = :conversation_id,
                    run_id = :run_id,
                    task_id = :task_id,
                    request_unit_id = :request_unit_id,
                    lifecycle_status = :lifecycle_status,
                    state_version = :state_version,
                    attempt_count = :attempt_count,
                    recovery_sort_at = :recovery_sort_at,
                    envelope = CAST(:envelope AS jsonb)
                WHERE record_id = :record_id
                """
            ),
            {
                **values,
                "logical_identity": json.dumps(
                    values["logical_identity"], separators=(",", ":")
                ),
                "envelope": json.dumps(
                    values["envelope"], ensure_ascii=False, separators=(",", ":")
                ),
                "record_id": record_id,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)


def _create_cycle2_tables() -> None:
    op.create_table(
        "mock_order_search_documents",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("line_ordinal", sa.Integer(), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_number", sa.String(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("product_category", sa.String(), nullable=False),
        sa.Column("search_aliases", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "line_ordinal > 0",
            name="ck_mock_order_search_documents_line_ordinal_positive",
        ),
        sa.CheckConstraint(
            "quantity > 0", name="ck_mock_order_search_documents_quantity_positive"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(search_aliases) = 'array'",
            name="ck_mock_order_search_documents_search_aliases_array",
        ),
        sa.ForeignKeyConstraint(
            ("customer_id", "order_id"),
            ("mock_orders.customer_id", "mock_orders.order_id"),
            name="fk_mock_order_search_documents_order",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("customer_id", "order_id", "line_ordinal"),
    )
    op.create_index(
        "ix_mock_order_search_documents_owner_window",
        "mock_order_search_documents",
        ("customer_id", "ordered_at", "order_number", "order_id", "line_ordinal"),
    )
    op.create_table(
        "mock_shipments",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("package_id", sa.String(), nullable=False),
        sa.Column("shipment_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(shipment_payload) = 'object'",
            name="ck_mock_shipments_payload_object",
        ),
        sa.ForeignKeyConstraint(
            ("customer_id", "order_id"),
            ("mock_orders.customer_id", "mock_orders.order_id"),
            name="fk_mock_shipments_order",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("customer_id", "order_id", "package_id"),
    )
    op.create_index(
        "ix_mock_shipments_owner_order",
        "mock_shipments",
        ("customer_id", "order_id"),
    )


def _reverse_record(
    record: object, code: str, children: tuple[object, ...]
) -> tuple[object, tuple[object, ...]]:
    data = record.model_dump(mode="json", warnings="error")
    target_children: tuple[object, ...] = ()
    if code == "input_binding_record":
        if type(record) is not InputBindingV2 or record.name != "order_id" or children:
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        target = InputBinding.model_validate_json(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
    elif code == "gate_decision_record":
        if (
            type(record) is not GateDecisionV2
            or record.verified_target_ref is not None
            or record.validated_arguments is not None
            or children
        ):
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        data.pop("verified_target_ref")
        data.pop("validated_arguments")
        target = GateDecision.model_validate_json(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
    elif code == "agent_run_record":
        if type(record) is not AgentRunRecordV2 or children:
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        target = AgentRunRecord.model_validate_json(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
    elif code == "run_task_link_record":
        if type(record) is not RunTaskLinkRecordV2 or children:
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        data.pop("record_schema_version")
        data["schema_version"] = "run_task_link_record.p0.v1"
        target = RunTaskLinkRecord.model_validate_json(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
    elif code == "trace_event_record":
        if type(record) is not TraceEventV2 or children:
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        target = TraceEvent.model_validate_json(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
    else:
        if (
            type(record) is not ToolCallRecordV2
            or record.canonical_tool_name.value != "get_order"
            or record.tool_registry_version
            != build_cycle2_registry_snapshot().tool_registry_version
            or record.verified_target_ref is not None
            or record.recovery_disposition is not None
            or record.recovery_decision_ref is not None
            or any(type(child) is not ToolAttemptRecordV2 for child in children)
        ):
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        attempts = tuple(
            ToolAttemptRecord.model_validate(
                {
                    "tool_call_id": child.tool_call_id,
                    "attempt_no": child.attempt_no,
                    "started_at": child.started_at,
                    "finished_at": child.finished_at,
                    "outcome": child.outcome,
                    "failure_code": child.failure_code,
                },
                strict=True,
            )
            for child in children
        )
        for child in children:
            if (
                child.timeout_phase is not record.timeout_phase
                and child.timeout_phase is not None
            ):
                raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        for field in (
            "private_owner_scope_ref",
            "verified_target_ref",
            "attempts",
            "recovery_disposition",
            "recovery_decision_ref",
        ):
            data.pop(field)
        data["tool_registry_version"] = (
            _phase1_registry_snapshot().tool_registry_version
        )
        target = ToolCallRecord.model_validate_json(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
        target_children = attempts
    return target, target_children


def _prepare_downgrade(
    connection: sa.Connection,
) -> list[tuple[UUID, P0PersistenceEnvelope, object]]:
    has_v2_only_rows = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM mock_order_search_documents
                UNION ALL SELECT 1 FROM mock_shipments
                UNION ALL SELECT 1 FROM p0_records WHERE record_code = ANY(:new_codes)
            )
            """
        ),
        {"new_codes": list(_NEW_CODES)},
    )
    if has_v2_only_rows is not False:
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
    rows, decoded = _decode_rows(connection)
    versions_by_code = {
        code: {
            row["record_schema_version"] for row in rows if row["record_code"] == code
        }
        for code in _V2_BY_CODE
    }
    if any(len(versions) > 1 for versions in versions_by_code.values()):
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)

    reverse_records: dict[UUID, tuple[object, tuple[object, ...]]] = {}
    for row in rows:
        if (
            row["record_code"] in _V2_BY_CODE
            and row["record_schema_version"] == _V2_BY_CODE[row["record_code"]]
        ):
            source, children = decoded[row["record_id"]]
            reverse_records[row["record_id"]] = _reverse_record(
                source,
                row["record_code"],
                children,
            )
    reverse_decoded = dict(decoded)
    reverse_decoded.update(reverse_records)
    index = _index_decoded(rows, reverse_decoded)
    prepared: list[tuple[UUID, P0PersistenceEnvelope, object]] = []
    for row in rows:
        if (
            row["record_code"] not in _V2_BY_CODE
            or row["record_schema_version"] != _V2_BY_CODE[row["record_code"]]
        ):
            continue
        source, children = decoded[row["record_id"]]
        target_record, target_children = reverse_records[row["record_id"]]
        references = _references(connection, row)
        target = encode_persistence_record_versioned(
            P0RecordCode(row["record_code"]),
            _V1_BY_CODE[row["record_code"]],
            target_record,
            external_references=_external_references(
                row["record_code"],
                references,
            ),
            logical_children=target_children,
        )
        if target.record_references != references:
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        forward_row = dict(row)
        forward_row["record_schema_version"] = _V1_BY_CODE[row["record_code"]]
        readiness = _classification(
            forward_row,
            target_record,
            target_children,
            index,
            (_V1_BY_CODE[row["record_code"]],),
            references,
        )
        if (
            not readiness.is_ready
            or readiness.target_record != source
            or readiness.target_logical_children != children
        ):
            raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
        prepared.append((row["record_id"], target, target_record))
    return prepared


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE p0_records, p0_record_references IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    try:
        prepared = _prepare_upgrade(connection)
    except RuntimeError as error:
        if str(error) == _MIGRATION_BLOCKED_MESSAGE:
            raise
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE) from None
    except Exception:
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE) from None
    _replace_record_constraints(_PHYSICAL_CODE_VERSION_PAIRS)
    _create_cycle2_tables()
    _write_prepared(connection, prepared)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE p0_records, p0_record_references, "
            "mock_order_search_documents, mock_shipments "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    try:
        prepared = _prepare_downgrade(connection)
    except RuntimeError as error:
        if str(error) == _DOWNGRADE_BLOCKED_MESSAGE:
            raise
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE) from None
    except Exception:
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE) from None
    _write_prepared(connection, prepared)
    op.drop_table("mock_shipments")
    op.drop_table("mock_order_search_documents")
    _replace_record_constraints(_HISTORICAL_CODE_VERSION_PAIRS)
