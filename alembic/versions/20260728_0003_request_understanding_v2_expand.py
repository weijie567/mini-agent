"""Admit the Request Understanding v2 physical code/version pair.

Revision ID: 20260728_0003
Revises: 20260727_0002
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0003"
down_revision: str | Sequence[str] | None = "20260727_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
)

_CODE_VERSION_CONSTRAINT = "ck_p0_records_code_version_closed"
_DOWNGRADE_BLOCKED_MESSAGE = "cannot downgrade request understanding v2 physical schema while v2 records exist"


def _code_version_condition(
    pairs: tuple[tuple[str, str], ...],
) -> str:
    conditions: list[str] = []
    for record_code, schema_version in pairs:
        conditions.append(
            f"(record_code = '{record_code}' "
            f"AND record_schema_version = '{schema_version}')"
        )
    return " OR ".join(conditions)


def _replace_code_version_constraint(
    pairs: tuple[tuple[str, str], ...],
) -> None:
    op.drop_constraint(
        _CODE_VERSION_CONSTRAINT,
        "p0_records",
        type_="check",
    )
    op.create_check_constraint(
        _CODE_VERSION_CONSTRAINT,
        "p0_records",
        _code_version_condition(pairs),
    )


def upgrade() -> None:
    _replace_code_version_constraint(_EXPANDED_CODE_VERSION_PAIRS)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE p0_records IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    has_v2_records = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM p0_records
                WHERE record_code = 'request_understanding_record'
                  AND record_schema_version =
                      'request_understanding_record.p0.v2'
            )
            """
        )
    )
    if has_v2_records is not False:
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)

    _replace_code_version_constraint(_V1_CODE_VERSION_PAIRS)
