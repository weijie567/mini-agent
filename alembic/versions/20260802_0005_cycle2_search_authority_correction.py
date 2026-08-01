"""Correct the Cycle 2 order-search authority storage.

Revision ID: 20260802_0005
Revises: 20260731_0004
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0005"
down_revision: str | Sequence[str] | None = "20260731_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_BLOCKED_MESSAGE = (
    "cannot correct order search authority from invalid source rows"
)
_DOWNGRADE_BLOCKED_MESSAGE = (
    "cannot downgrade order search authority while durable evidence exists"
)
_ORDER_STATUS_VALUES = (
    "CREATED",
    "PAID",
    "FULFILLING",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
)
_ORDER_STATUS_CHECK = (
    "status IN ('CREATED', 'PAID', 'FULFILLING', 'SHIPPED', 'DELIVERED', 'CANCELLED')"
)
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


def _prevalidate_existing_search_documents(connection: sa.Connection) -> None:
    invalid_source_exists = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM mock_order_search_documents AS search_document
                LEFT JOIN mock_orders AS owned_order
                  ON owned_order.customer_id = search_document.customer_id
                 AND owned_order.order_id = search_document.order_id
                WHERE owned_order.customer_id IS NULL
                   OR jsonb_typeof(owned_order.order_payload)
                        IS DISTINCT FROM 'object'
                   OR jsonb_typeof(owned_order.order_payload -> 'order_number')
                        IS DISTINCT FROM 'string'
                   OR owned_order.order_payload ->> 'order_number'
                        IS DISTINCT FROM search_document.order_id
                   OR search_document.order_number
                        IS DISTINCT FROM search_document.order_id
                   OR jsonb_typeof(owned_order.order_payload -> 'status')
                        IS DISTINCT FROM 'string'
                   OR owned_order.order_payload ->> 'status'
                        NOT IN (
                            'CREATED', 'PAID', 'FULFILLING',
                            'SHIPPED', 'DELIVERED', 'CANCELLED'
                        )
            )
            """
        )
    )
    if invalid_source_exists is not False:
        raise RuntimeError(_UPGRADE_BLOCKED_MESSAGE)


def _backfill_search_status(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE mock_order_search_documents AS search_document
            SET status = owned_order.order_payload ->> 'status'
            FROM mock_orders AS owned_order
            WHERE owned_order.customer_id = search_document.customer_id
              AND owned_order.order_id = search_document.order_id
            """
        )
    )
    missing_status_exists = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM mock_order_search_documents
                WHERE status IS NULL
            )
            """
        )
    )
    if missing_status_exists is not False:
        raise RuntimeError(_UPGRADE_BLOCKED_MESSAGE)


def _create_raw_snapshot_table() -> None:
    op.create_table(
        "mock_order_search_snapshots",
        sa.Column(
            "snapshot_resource_ref",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            _SEARCH_SNAPSHOT_PAYLOAD_CHECK,
            name="ck_mock_order_search_snapshots_payload_closed",
        ),
        sa.CheckConstraint(
            _SEARCH_SNAPSHOT_CANDIDATES_CHECK,
            name="ck_mock_order_search_snapshots_candidates_closed",
        ),
        sa.PrimaryKeyConstraint("snapshot_resource_ref"),
    )
    op.create_index(
        "ix_mock_order_search_snapshots_owner_ref",
        "mock_order_search_snapshots",
        ("customer_id", "snapshot_resource_ref"),
    )


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE mock_orders, mock_order_search_documents "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    try:
        _prevalidate_existing_search_documents(connection)
    except RuntimeError as error:
        if str(error) == _UPGRADE_BLOCKED_MESSAGE:
            raise
        raise RuntimeError(_UPGRADE_BLOCKED_MESSAGE) from None
    except Exception:
        raise RuntimeError(_UPGRADE_BLOCKED_MESSAGE) from None

    op.add_column(
        "mock_order_search_documents",
        sa.Column("status", sa.String(), nullable=True),
    )
    try:
        _backfill_search_status(connection)
    except RuntimeError as error:
        if str(error) == _UPGRADE_BLOCKED_MESSAGE:
            raise
        raise RuntimeError(_UPGRADE_BLOCKED_MESSAGE) from None
    except Exception:
        raise RuntimeError(_UPGRADE_BLOCKED_MESSAGE) from None
    op.create_check_constraint(
        "ck_mock_order_search_documents_status_closed",
        "mock_order_search_documents",
        _ORDER_STATUS_CHECK,
    )
    op.alter_column(
        "mock_order_search_documents",
        "status",
        existing_type=sa.String(),
        nullable=False,
    )
    _create_raw_snapshot_table()


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE mock_orders, mock_order_search_documents, "
            "mock_order_search_snapshots IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    durable_evidence_exists = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM mock_order_search_documents
                UNION ALL
                SELECT 1 FROM mock_order_search_snapshots
            )
            """
        )
    )
    if durable_evidence_exists is not False:
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)

    op.drop_index(
        "ix_mock_order_search_snapshots_owner_ref",
        table_name="mock_order_search_snapshots",
    )
    op.drop_table("mock_order_search_snapshots")
    op.drop_constraint(
        "ck_mock_order_search_documents_status_closed",
        "mock_order_search_documents",
        type_="check",
    )
    op.drop_column("mock_order_search_documents", "status")
