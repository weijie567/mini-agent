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

from mini_agent.application.persistence import (
    P0_PERSISTENCE_REGISTRY,
    P0RecordCode,
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_RECORD_CODES = tuple(code.value for code in P0RecordCode)
_CODE_VERSION_PAIRS = tuple(
    (code.value, spec.record_schema_version)
    for code, spec in P0_PERSISTENCE_REGISTRY.items()
)
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
    conversation_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True)
    )
    run_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    task_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    request_unit_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True)
    )
    lifecycle_status: Mapped[str | None] = mapped_column(String)
    state_version: Mapped[int | None] = mapped_column(BigInteger)
    attempt_count: Mapped[int | None] = mapped_column(Integer)
    recovery_sort_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
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
    __table_args__ = (
        PrimaryKeyConstraint("customer_id", "order_id"),
    )

    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    order_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
