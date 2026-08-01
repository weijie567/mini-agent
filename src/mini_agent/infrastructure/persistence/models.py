from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from mini_agent.application.persistence import P0RecordCode


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_RECORD_CODES = tuple(code.value for code in P0RecordCode)
_ORDER_STATUS_VALUES = (
    "CREATED",
    "PAID",
    "FULFILLING",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
)
_ORDER_STATUS_CHECK = "status IN (" + _sql_values(_ORDER_STATUS_VALUES) + ")"
_SEARCH_SNAPSHOT_PAYLOAD_CHECK = """
jsonb_typeof(snapshot_payload) = 'object'
AND snapshot_payload ?& ARRAY[
    'source_version_schema',
    'owner_customer_id',
    'normalized_query',
    'ordered_at_from',
    'ordered_at_to',
    'max_candidates',
    'matching_rule_version',
    'ordered_candidates',
    'truncated'
]
AND (
    snapshot_payload - ARRAY[
        'source_version_schema',
        'owner_customer_id',
        'normalized_query',
        'ordered_at_from',
        'ordered_at_to',
        'max_candidates',
        'matching_rule_version',
        'ordered_candidates',
        'truncated'
    ]::text[]
) = '{}'::jsonb
AND jsonb_typeof(snapshot_payload -> 'source_version_schema') = 'string'
AND snapshot_payload ->> 'source_version_schema' =
    'mock-order-search-snapshot-source-version.p0.v1'
AND jsonb_typeof(snapshot_payload -> 'owner_customer_id') = 'string'
AND snapshot_payload ->> 'owner_customer_id' = customer_id
AND jsonb_typeof(snapshot_payload -> 'normalized_query') = 'string'
AND length(snapshot_payload ->> 'normalized_query') BETWEEN 1 AND 80
AND jsonb_typeof(snapshot_payload -> 'ordered_at_from') = 'string'
AND snapshot_payload ->> 'ordered_at_from' ~
    '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}Z$'
AND jsonb_typeof(snapshot_payload -> 'ordered_at_to') = 'string'
AND snapshot_payload ->> 'ordered_at_to' ~
    '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}Z$'
AND snapshot_payload ->> 'ordered_at_from' <=
    snapshot_payload ->> 'ordered_at_to'
AND (
    (snapshot_payload ->> 'ordered_at_to')::timestamptz
    - (snapshot_payload ->> 'ordered_at_from')::timestamptz
) = INTERVAL '90 days'
AND jsonb_typeof(snapshot_payload -> 'max_candidates') = 'number'
AND snapshot_payload ->> 'max_candidates' = '5'
AND jsonb_typeof(snapshot_payload -> 'matching_rule_version') = 'string'
AND snapshot_payload ->> 'matching_rule_version' =
    'order-search-matching.p0.v1'
AND jsonb_typeof(snapshot_payload -> 'ordered_candidates') = 'array'
AND jsonb_array_length(snapshot_payload -> 'ordered_candidates') BETWEEN 1 AND 5
AND jsonb_typeof(snapshot_payload -> 'truncated') = 'boolean'
AND (
    snapshot_payload -> 'truncated' = 'false'::jsonb
    OR jsonb_array_length(snapshot_payload -> 'ordered_candidates') = 5
)
"""


def _search_snapshot_candidate_check(index: int) -> str:
    candidate = f"(snapshot_payload -> 'ordered_candidates' -> {index})"
    return f"""
(
    jsonb_array_length(snapshot_payload -> 'ordered_candidates') <= {index}
    OR (
        jsonb_typeof({candidate}) = 'object'
        AND {candidate} ?& ARRAY[
            'ordinal',
            'owner_scoped_order_ref',
            'candidate_source_version'
        ]
        AND (
            {candidate} - ARRAY[
                'ordinal',
                'owner_scoped_order_ref',
                'candidate_source_version'
            ]::text[]
        ) = '{{}}'::jsonb
        AND jsonb_typeof({candidate} -> 'ordinal') = 'number'
        AND {candidate} ->> 'ordinal' = '{index + 1}'
        AND jsonb_typeof({candidate} -> 'owner_scoped_order_ref') = 'string'
        AND length({candidate} ->> 'owner_scoped_order_ref') > 0
        AND jsonb_typeof({candidate} -> 'candidate_source_version') = 'string'
        AND {candidate} ->> 'candidate_source_version' ~
            '^mock-order-search-candidate-source-version\\.p0\\.v1:sha256:[0-9a-f]{{64}}$'
    )
)
"""


_SEARCH_SNAPSHOT_CANDIDATES_CHECK = " AND ".join(
    _search_snapshot_candidate_check(index) for index in range(5)
)
_PHYSICAL_CODE_VERSION_PAIRS = (
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
    (
        "request_understanding_record",
        "request_understanding_record.p0.v2",
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
_CODE_VERSION_PAIRS = tuple(sorted(_PHYSICAL_CODE_VERSION_PAIRS))
_CODE_VERSION_CHECK = " OR ".join(
    f"(record_code = '{code}' AND record_schema_version = '{version}')"
    for code, version in _CODE_VERSION_PAIRS
)


class Base(DeclarativeBase):
    """SQLAlchemy metadata for the closed P0 physical persistence schema."""


class P0RecordModel(Base):
    __tablename__ = "p0_records"
    __table_args__ = (
        UniqueConstraint(
            "record_code",
            "logical_identity",
            name="uq_p0_records_code_identity",
        ),
        CheckConstraint(
            f"record_code IN ({_sql_values(_RECORD_CODES)})",
            name="ck_p0_records_code_closed",
        ),
        CheckConstraint(
            _CODE_VERSION_CHECK,
            name="ck_p0_records_code_version_closed",
        ),
        CheckConstraint(
            "jsonb_typeof(logical_identity) = 'array'",
            name="ck_p0_records_logical_identity_array",
        ),
        CheckConstraint(
            "jsonb_typeof(envelope) = 'object'",
            name="ck_p0_records_envelope_object",
        ),
        CheckConstraint(
            "state_version IS NULL OR state_version >= 1",
            name="ck_p0_records_state_version",
        ),
        CheckConstraint(
            "attempt_count IS NULL OR attempt_count >= 0",
            name="ck_p0_records_attempt_count",
        ),
        Index(
            "ix_p0_records_scope_owner_code",
            "scope_owner_customer_id",
            "record_code",
        ),
        Index(
            "ix_p0_records_code_run_status",
            "record_code",
            "run_id",
            "lifecycle_status",
        ),
        Index(
            "ix_p0_records_code_task_status",
            "record_code",
            "task_id",
            "lifecycle_status",
        ),
        Index(
            "ix_p0_records_code_request_unit",
            "record_code",
            "request_unit_id",
        ),
        Index(
            "ix_p0_records_recovery_candidate",
            "recovery_sort_at",
            "record_id",
            postgresql_where=text(
                "record_code = 'agent_run_record' "
                "AND lifecycle_status IN ('CREATED', 'RUNNING')"
            ),
        ),
    )

    record_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    record_code: Mapped[str] = mapped_column(String, nullable=False)
    record_schema_version: Mapped[str] = mapped_column(String, nullable=False)
    logical_identity: Mapped[list[list[Any]]] = mapped_column(JSONB, nullable=False)
    direct_owner_customer_id: Mapped[str | None] = mapped_column(String)
    scope_owner_customer_id: Mapped[str | None] = mapped_column(String)
    conversation_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    run_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    task_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    request_unit_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    lifecycle_status: Mapped[str | None] = mapped_column(String)
    state_version: Mapped[int | None] = mapped_column(BigInteger)
    attempt_count: Mapped[int | None] = mapped_column(Integer)
    recovery_sort_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class P0RecordReferenceModel(Base):
    __tablename__ = "p0_record_references"
    __table_args__ = (
        CheckConstraint(
            "ordinal >= 0",
            name="ck_p0_record_references_ordinal_nonnegative",
        ),
        ForeignKeyConstraint(
            ("source_record_code", "source_logical_identity"),
            ("p0_records.record_code", "p0_records.logical_identity"),
            name="fk_p0_record_references_source",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ("target_record_code", "target_logical_identity"),
            ("p0_records.record_code", "p0_records.logical_identity"),
            name="fk_p0_record_references_target",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "source_record_code",
            "source_logical_identity",
            "ordinal",
            name="uq_p0_record_references_source_ordinal",
        ),
        UniqueConstraint(
            "source_record_code",
            "source_logical_identity",
            "relation",
            "target_record_code",
            "target_logical_identity",
            name="uq_p0_record_references_source_relation_target",
        ),
        Index(
            "ix_p0_record_references_target",
            "target_record_code",
            "target_logical_identity",
        ),
    )

    reference_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_record_code: Mapped[str] = mapped_column(String, nullable=False)
    source_logical_identity: Mapped[list[list[Any]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    relation: Mapped[str] = mapped_column(String, nullable=False)
    target_record_code: Mapped[str] = mapped_column(String, nullable=False)
    target_logical_identity: Mapped[list[list[Any]]] = mapped_column(
        JSONB,
        nullable=False,
    )


class MockOrderModel(Base):
    __tablename__ = "mock_orders"
    __table_args__ = (PrimaryKeyConstraint("customer_id", "order_id"),)

    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    order_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class MockOrderSearchDocumentModel(Base):
    __tablename__ = "mock_order_search_documents"
    __table_args__ = (
        PrimaryKeyConstraint("customer_id", "order_id", "line_ordinal"),
        ForeignKeyConstraint(
            ("customer_id", "order_id"),
            ("mock_orders.customer_id", "mock_orders.order_id"),
            name="fk_mock_order_search_documents_order",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "line_ordinal > 0",
            name="ck_mock_order_search_documents_line_ordinal_positive",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_mock_order_search_documents_quantity_positive",
        ),
        CheckConstraint(
            "jsonb_typeof(search_aliases) = 'array'",
            name="ck_mock_order_search_documents_search_aliases_array",
        ),
        CheckConstraint(
            _ORDER_STATUS_CHECK,
            name="ck_mock_order_search_documents_status_closed",
        ),
        Index(
            "ix_mock_order_search_documents_owner_window",
            "customer_id",
            "ordered_at",
            "order_number",
            "order_id",
            "line_ordinal",
        ),
    )

    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    line_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    order_number: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    product_category: Mapped[str] = mapped_column(String, nullable=False)
    search_aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class MockOrderSearchSnapshotModel(Base):
    __tablename__ = "mock_order_search_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("snapshot_resource_ref"),
        CheckConstraint(
            _SEARCH_SNAPSHOT_PAYLOAD_CHECK,
            name="ck_mock_order_search_snapshots_payload_closed",
        ),
        CheckConstraint(
            _SEARCH_SNAPSHOT_CANDIDATES_CHECK,
            name="ck_mock_order_search_snapshots_candidates_closed",
        ),
        Index(
            "ix_mock_order_search_snapshots_owner_ref",
            "customer_id",
            "snapshot_resource_ref",
        ),
    )

    snapshot_resource_ref: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class MockShipmentModel(Base):
    __tablename__ = "mock_shipments"
    __table_args__ = (
        PrimaryKeyConstraint("customer_id", "order_id", "package_id"),
        ForeignKeyConstraint(
            ("customer_id", "order_id"),
            ("mock_orders.customer_id", "mock_orders.order_id"),
            name="fk_mock_shipments_order",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "jsonb_typeof(shipment_payload) = 'object'",
            name="ck_mock_shipments_payload_object",
        ),
        Index(
            "ix_mock_shipments_owner_order",
            "customer_id",
            "order_id",
        ),
    )

    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    package_id: Mapped[str] = mapped_column(String, nullable=False)
    shipment_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
