"""Add immutable owner-scoped record-state history storage.

Revision ID: 20260802_0006
Revises: 20260802_0005
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0006"
down_revision: str | Sequence[str] | None = "20260802_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade record state history while durable evidence exists"
)
_APPEND_ONLY_MESSAGE = "record state history is append-only"
_APPEND_ONLY_FUNCTION = "p0_record_state_history_reject_mutation"
_ROW_MUTATION_TRIGGER = "trg_p0_record_state_history_reject_row_mutation"
_TRUNCATE_TRIGGER = "trg_p0_record_state_history_reject_truncate"
_HISTORY_CODE_VERSION_PAIRS = (
    ("task_record", "task_record.p0.v1"),
    ("request_unit_record", "request_unit_record.p0.v1"),
)
_HISTORY_RECORD_CODES = tuple(code for code, _ in _HISTORY_CODE_VERSION_PAIRS)
_HISTORY_RECORD_CODE_CHECK = (
    "record_code IN ("
    + ", ".join(f"'{code}'" for code in _HISTORY_RECORD_CODES)
    + ")"
)
_HISTORY_CODE_VERSION_CHECK = " OR ".join(
    f"(record_code = '{code}' AND record_schema_version = '{version}')"
    for code, version in _HISTORY_CODE_VERSION_PAIRS
)


def upgrade() -> None:
    op.create_table(
        "p0_record_state_history",
        sa.Column(
            "history_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("record_code", sa.String(), nullable=False),
        sa.Column("record_schema_version", sa.String(), nullable=False),
        sa.Column("logical_identity", postgresql.JSONB(), nullable=False),
        sa.Column("scope_owner_customer_id", sa.String(), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("envelope", postgresql.JSONB(), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            _HISTORY_RECORD_CODE_CHECK,
            name="ck_p0_record_state_history_code_closed",
        ),
        sa.CheckConstraint(
            _HISTORY_CODE_VERSION_CHECK,
            name="ck_p0_record_state_history_code_version_closed",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(logical_identity) = 'array'",
            name="ck_p0_record_state_history_logical_identity_array",
        ),
        sa.CheckConstraint(
            "length(scope_owner_customer_id) > 0",
            name="ck_p0_record_state_history_owner_nonempty",
        ),
        sa.CheckConstraint(
            "state_version > 0",
            name="ck_p0_record_state_history_state_version_positive",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(envelope) = 'object'",
            name="ck_p0_record_state_history_envelope_object",
        ),
        sa.PrimaryKeyConstraint("history_id"),
        sa.UniqueConstraint(
            "record_code",
            "logical_identity",
            "state_version",
            name="uq_p0_record_state_history_logical_version",
        ),
    )
    op.create_index(
        "ix_p0_record_state_history_owner_lookup",
        "p0_record_state_history",
        (
            "scope_owner_customer_id",
            "record_code",
            "logical_identity",
            "state_version",
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_APPEND_ONLY_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $append_only$
            BEGIN
                RAISE EXCEPTION USING
                    ERRCODE = '55000',
                    MESSAGE = '{_APPEND_ONLY_MESSAGE}';
                RETURN NULL;
            END;
            $append_only$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {_ROW_MUTATION_TRIGGER}
            BEFORE UPDATE OR DELETE ON p0_record_state_history
            FOR EACH ROW
            EXECUTE FUNCTION {_APPEND_ONLY_FUNCTION}()
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {_TRUNCATE_TRIGGER}
            BEFORE TRUNCATE ON p0_record_state_history
            FOR EACH STATEMENT
            EXECUTE FUNCTION {_APPEND_ONLY_FUNCTION}()
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE p0_record_state_history IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    history_exists = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM p0_record_state_history)"
        )
    )
    if history_exists is not False:
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)

    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS {_ROW_MUTATION_TRIGGER} "
            "ON p0_record_state_history"
        )
    )
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS {_TRUNCATE_TRIGGER} "
            "ON p0_record_state_history"
        )
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_APPEND_ONLY_FUNCTION}()"))
    op.drop_index(
        "ix_p0_record_state_history_owner_lookup",
        table_name="p0_record_state_history",
    )
    op.drop_table("p0_record_state_history")
