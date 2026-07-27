"""Add the closed P0 record, reference, and mock-order tables.

Revision ID: 20260727_0002
Revises: 20260726_0001
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260727_0002"
down_revision: str | Sequence[str] | None = "20260726_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RECORD_CODES = (
    "conversation_record",
    "message_record",
    "request_understanding_record",
    "task_record",
    "request_unit_record",
    "conversation_task_link_record",
    "run_task_link_record",
    "input_binding_record",
    "model_visible_toolset_artifact",
    "agent_run_record",
    "gate_decision_record",
    "tool_call_record",
    "observation_record",
    "context_manifest_record",
    "trace_event_record",
    "eval_result_record",
    "eval_execution_failure_record",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "p0_records",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_code", sa.String(), nullable=False),
        sa.Column("record_schema_version", sa.String(), nullable=False),
        sa.Column("logical_identity", postgresql.JSONB(), nullable=False),
        sa.Column("direct_owner_customer_id", sa.String(), nullable=True),
        sa.Column("scope_owner_customer_id", sa.String(), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lifecycle_status", sa.String(), nullable=True),
        sa.Column("state_version", sa.BigInteger(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=True),
        sa.Column(
            "recovery_sort_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "envelope",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count IS NULL OR attempt_count >= 0",
            name="ck_p0_records_attempt_count",
        ),
        sa.CheckConstraint(
            f"record_code IN ({_quoted(_RECORD_CODES)})",
            name="ck_p0_records_code_closed",
        ),
        sa.CheckConstraint(
            " OR ".join(
                f"(record_code = '{code}' "
                f"AND record_schema_version = '{code}.p0.v1')"
                for code in _RECORD_CODES
            ),
            name="ck_p0_records_code_version_closed",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(envelope) = 'object'",
            name="ck_p0_records_envelope_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(logical_identity) = 'array'",
            name="ck_p0_records_logical_identity_array",
        ),
        sa.CheckConstraint(
            "state_version IS NULL OR state_version >= 1",
            name="ck_p0_records_state_version",
        ),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint(
            "record_code",
            "logical_identity",
            name="uq_p0_records_code_identity",
        ),
    )
    op.create_index(
        "ix_p0_records_scope_owner_code",
        "p0_records",
        ["scope_owner_customer_id", "record_code"],
    )
    op.create_index(
        "ix_p0_records_code_run_status",
        "p0_records",
        ["record_code", "run_id", "lifecycle_status"],
    )
    op.create_index(
        "ix_p0_records_code_task_status",
        "p0_records",
        ["record_code", "task_id", "lifecycle_status"],
    )
    op.create_index(
        "ix_p0_records_code_request_unit",
        "p0_records",
        ["record_code", "request_unit_id"],
    )
    op.create_index(
        "ix_p0_records_recovery_candidate",
        "p0_records",
        ["recovery_sort_at", "record_id"],
        postgresql_where=sa.text(
            "record_code = 'agent_run_record' "
            "AND lifecycle_status IN ('CREATED', 'RUNNING')"
        ),
    )

    op.create_table(
        "p0_record_references",
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_code", sa.String(), nullable=False),
        sa.Column("source_logical_identity", postgresql.JSONB(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(), nullable=False),
        sa.Column("target_record_code", sa.String(), nullable=False),
        sa.Column("target_logical_identity", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_p0_record_references_ordinal_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_code", "source_logical_identity"],
            ["p0_records.record_code", "p0_records.logical_identity"],
            name="fk_p0_record_references_source",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["target_record_code", "target_logical_identity"],
            ["p0_records.record_code", "p0_records.logical_identity"],
            name="fk_p0_record_references_target",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("reference_id"),
        sa.UniqueConstraint(
            "source_record_code",
            "source_logical_identity",
            "ordinal",
            name="uq_p0_record_references_source_ordinal",
        ),
        sa.UniqueConstraint(
            "source_record_code",
            "source_logical_identity",
            "relation",
            "target_record_code",
            "target_logical_identity",
            name="uq_p0_record_references_source_relation_target",
        ),
    )
    op.create_index(
        "ix_p0_record_references_target",
        "p0_record_references",
        ["target_record_code", "target_logical_identity"],
    )

    op.create_table(
        "mock_orders",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("order_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("customer_id", "order_id"),
    )


def downgrade() -> None:
    op.drop_table("mock_orders")
    op.drop_index(
        "ix_p0_record_references_target",
        table_name="p0_record_references",
    )
    op.drop_table("p0_record_references")
    op.drop_index(
        "ix_p0_records_recovery_candidate",
        table_name="p0_records",
    )
    op.drop_index(
        "ix_p0_records_code_request_unit",
        table_name="p0_records",
    )
    op.drop_index(
        "ix_p0_records_code_task_status",
        table_name="p0_records",
    )
    op.drop_index(
        "ix_p0_records_code_run_status",
        table_name="p0_records",
    )
    op.drop_index(
        "ix_p0_records_scope_owner_code",
        table_name="p0_records",
    )
    op.drop_table("p0_records")
