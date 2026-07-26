"""Create the scoped E2E-01 persistence projection.

Revision ID: 20260726_0001
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260726_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_STATUSES = "'CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'INCOMPLETE'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "conversation_records",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_customer_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_conversation_records_owner_customer_id",
        "conversation_records",
        ["owner_customer_id"],
    )

    op.create_table(
        "agent_run_records",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_lane", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=64), nullable=True),
        sa.Column("incomplete_reason", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            f"status IN ({RUN_STATUSES})",
            name="ck_agent_run_records_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation_records.conversation_id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_agent_run_records_status",
        "agent_run_records",
        ["status"],
    )

    op.create_table(
        "message_records",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("controlled_content", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation_records.conversation_id"],
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_message_records_conversation_id",
        "message_records",
        ["conversation_id"],
    )

    op.create_table(
        "model_visible_toolset_artifacts",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("model_visible_toolset_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "provider_visible_tool_specs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("artifact_id"),
        sa.UniqueConstraint(
            "model_visible_toolset_hash",
            name="uq_toolset_artifacts_hash",
        ),
    )

    op.create_table(
        "task_records",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_customer_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("last_outcome_ref", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "state_version >= 0",
            name="ck_task_records_state_version",
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(
        "ix_task_records_owner_customer_id",
        "task_records",
        ["owner_customer_id"],
    )
    op.create_index("ix_task_records_status", "task_records", ["status"])

    op.create_table(
        "input_binding_records",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "normalized_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("authority", sa.String(length=64), nullable=False),
        sa.Column(
            "source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 0",
            name="ck_input_binding_records_version",
        ),
        sa.PrimaryKeyConstraint("binding_id"),
    )

    op.create_table(
        "request_understanding_records",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_ref", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "candidate_validation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "accepted_delta_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("candidate_state_version", sa.Integer(), nullable=False),
        sa.Column("revalidation_state_version", sa.Integer(), nullable=False),
        sa.Column("next_move_candidate_ref", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "candidate_state_version >= 0",
            name="ck_request_understanding_candidate_version",
        ),
        sa.CheckConstraint(
            "revalidation_state_version >= 0",
            name="ck_request_understanding_revalidation_version",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.ForeignKeyConstraint(["message_ref"], ["message_records.message_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )

    op.create_table(
        "request_unit_records",
        sa.Column("request_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "goal_source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "input_binding_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column(
            "result_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state_version >= 0",
            name="ck_request_unit_records_state_version",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["task_records.task_id"]),
        sa.PrimaryKeyConstraint("request_unit_id"),
    )
    op.create_index(
        "ix_request_unit_records_task_id",
        "request_unit_records",
        ["task_id"],
    )

    op.create_table(
        "conversation_task_link_records",
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_reason", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation_records.conversation_id"],
        ),
        sa.ForeignKeyConstraint(["task_id"], ["task_records.task_id"]),
        sa.PrimaryKeyConstraint("link_id"),
    )
    op.create_index(
        "ix_conversation_task_links_conversation",
        "conversation_task_link_records",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_task_links_task",
        "conversation_task_link_records",
        ["task_id"],
    )

    op.create_table(
        "run_task_link_records",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_state_version", sa.Integer(), nullable=False),
        sa.Column("result_state_version", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "base_state_version >= 0",
            name="ck_run_task_links_base_version",
        ),
        sa.CheckConstraint(
            "result_state_version IS NULL OR result_state_version >= base_state_version",
            name="ck_run_task_links_result_version",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task_records.task_id"]),
        sa.PrimaryKeyConstraint("run_id", "task_id"),
    )

    op.create_table(
        "gate_decision_records",
        sa.Column("gate_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("candidate_tool_name", sa.String(length=128), nullable=False),
        sa.Column("canonical_tool_name", sa.String(length=128), nullable=True),
        sa.Column(
            "gate_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("candidate_state_version", sa.Integer(), nullable=False),
        sa.Column("revalidation_state_version", sa.Integer(), nullable=False),
        sa.Column(
            "argument_binding_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "candidate_state_version >= 0",
            name="ck_gate_decision_candidate_version",
        ),
        sa.CheckConstraint(
            "revalidation_state_version >= 0",
            name="ck_gate_decision_revalidation_version",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task_records.task_id"]),
        sa.ForeignKeyConstraint(
            ["request_unit_id"],
            ["request_unit_records.request_unit_id"],
        ),
        sa.PrimaryKeyConstraint("gate_decision_id"),
    )
    op.create_index(
        "ix_gate_decision_records_run_id",
        "gate_decision_records",
        ["run_id"],
    )

    op.create_table(
        "tool_call_records",
        sa.Column("tool_call_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("result_ref", sa.String(length=128), nullable=True),
        sa.Column("validated_task_state_version", sa.Integer(), nullable=False),
        sa.Column(
            "argument_binding_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_tool_call_records_attempt"),
        sa.CheckConstraint(
            "validated_task_state_version >= 0",
            name="ck_tool_call_records_task_version",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task_records.task_id"]),
        sa.ForeignKeyConstraint(
            ["request_unit_id"],
            ["request_unit_records.request_unit_id"],
        ),
        sa.ForeignKeyConstraint(
            ["gate_decision_id"],
            ["gate_decision_records.gate_decision_id"],
        ),
        sa.PrimaryKeyConstraint("tool_call_id"),
    )
    op.create_index(
        "ix_tool_call_records_run_id",
        "tool_call_records",
        ["run_id"],
    )
    op.create_index(
        "ix_tool_call_records_status",
        "tool_call_records",
        ["status"],
    )

    op.create_table(
        "observation_records",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("observation_type", sa.String(length=128), nullable=False),
        sa.Column(
            "minimal_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("visibility", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.ForeignKeyConstraint(
            ["tool_call_id"],
            ["tool_call_records.tool_call_id"],
        ),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_index(
        "ix_observation_records_run_id",
        "observation_records",
        ["run_id"],
    )

    op.create_table(
        "context_manifest_records",
        sa.Column(
            "context_manifest_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("model_call_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "message_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "task_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "observation_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("model_visible_toolset_hash", sa.String(length=64), nullable=False),
        sa.Column("redaction_policy_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.ForeignKeyConstraint(
            ["model_visible_toolset_hash"],
            ["model_visible_toolset_artifacts.model_visible_toolset_hash"],
        ),
        sa.PrimaryKeyConstraint("context_manifest_id"),
    )
    op.create_index(
        "ix_context_manifest_records_run_id",
        "context_manifest_records",
        ["run_id"],
    )

    op.create_table(
        "trace_event_records",
        sa.Column("trace_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "related_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "safe_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.PrimaryKeyConstraint("trace_event_id"),
    )
    op.create_index(
        "ix_trace_event_records_run_id",
        "trace_event_records",
        ["run_id"],
    )

    op.create_table(
        "eval_result_records",
        sa.Column("eval_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("lane", sa.String(length=64), nullable=False),
        sa.Column(
            "version_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "grader_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("critical_failure", sa.Boolean(), nullable=False),
        sa.Column("trace_ref", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run_records.run_id"]),
        sa.PrimaryKeyConstraint("eval_result_id"),
    )
    op.create_index(
        "ix_eval_result_records_case_lane",
        "eval_result_records",
        ["case_id", "lane"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eval_result_records_case_lane",
        table_name="eval_result_records",
    )
    op.drop_table("eval_result_records")
    op.drop_index("ix_trace_event_records_run_id", table_name="trace_event_records")
    op.drop_table("trace_event_records")
    op.drop_index(
        "ix_context_manifest_records_run_id",
        table_name="context_manifest_records",
    )
    op.drop_table("context_manifest_records")
    op.drop_index(
        "ix_observation_records_run_id",
        table_name="observation_records",
    )
    op.drop_table("observation_records")
    op.drop_index("ix_tool_call_records_status", table_name="tool_call_records")
    op.drop_index("ix_tool_call_records_run_id", table_name="tool_call_records")
    op.drop_table("tool_call_records")
    op.drop_index(
        "ix_gate_decision_records_run_id",
        table_name="gate_decision_records",
    )
    op.drop_table("gate_decision_records")
    op.drop_table("run_task_link_records")
    op.drop_index(
        "ix_conversation_task_links_task",
        table_name="conversation_task_link_records",
    )
    op.drop_index(
        "ix_conversation_task_links_conversation",
        table_name="conversation_task_link_records",
    )
    op.drop_table("conversation_task_link_records")
    op.drop_index(
        "ix_request_unit_records_task_id",
        table_name="request_unit_records",
    )
    op.drop_table("request_unit_records")
    op.drop_table("request_understanding_records")
    op.drop_table("input_binding_records")
    op.drop_index("ix_task_records_status", table_name="task_records")
    op.drop_index(
        "ix_task_records_owner_customer_id",
        table_name="task_records",
    )
    op.drop_table("task_records")
    op.drop_table("model_visible_toolset_artifacts")
    op.drop_index(
        "ix_message_records_conversation_id",
        table_name="message_records",
    )
    op.drop_table("message_records")
    op.drop_index("ix_agent_run_records_status", table_name="agent_run_records")
    op.drop_table("agent_run_records")
    op.drop_index(
        "ix_conversation_records_owner_customer_id",
        table_name="conversation_records",
    )
    op.drop_table("conversation_records")
