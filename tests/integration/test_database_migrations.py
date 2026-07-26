from __future__ import annotations

from uuid import uuid4

from sqlalchemy import inspect, select, text

from mini_agent.infrastructure.persistence.migrations import (
    upgrade_database_to_head,
)
from mini_agent.infrastructure.persistence.models import Base, ConversationRow

EXPECTED_RECORD_TABLES = {
    "agent_run_records",
    "context_manifest_records",
    "conversation_records",
    "conversation_task_link_records",
    "eval_result_records",
    "gate_decision_records",
    "input_binding_records",
    "message_records",
    "model_visible_toolset_artifacts",
    "observation_records",
    "request_understanding_records",
    "request_unit_records",
    "run_task_link_records",
    "task_records",
    "tool_call_records",
    "trace_event_records",
}

REQUIRED_COLUMNS = {
    "conversation_records": {
        "conversation_id",
        "owner_customer_id",
        "created_at",
    },
    "message_records": {
        "message_id",
        "conversation_id",
        "direction",
        "controlled_content",
        "received_at",
    },
    "request_understanding_records": {
        "run_id",
        "message_ref",
        "schema_version",
        "candidate_validation",
        "accepted_delta_refs",
        "candidate_state_version",
        "revalidation_state_version",
        "next_move_candidate_ref",
    },
    "task_records": {
        "task_id",
        "owner_customer_id",
        "status",
        "state_version",
        "created_at",
        "updated_at",
        "last_outcome_ref",
    },
    "request_unit_records": {
        "request_unit_id",
        "task_id",
        "goal_source_refs",
        "input_binding_refs",
        "status",
        "state_version",
        "result_refs",
    },
    "conversation_task_link_records": {
        "conversation_id",
        "task_id",
        "link_reason",
        "created_at",
        "ended_at",
    },
    "run_task_link_records": {
        "run_id",
        "task_id",
        "base_state_version",
        "result_state_version",
    },
    "input_binding_records": {
        "binding_id",
        "name",
        "normalized_value",
        "authority",
        "source_refs",
        "validation_status",
        "version",
        "created_at",
        "updated_at",
    },
    "model_visible_toolset_artifacts": {
        "schema_version",
        "model_visible_toolset_hash",
        "provider_visible_tool_specs",
    },
    "agent_run_records": {
        "run_id",
        "conversation_id",
        "status",
        "provider_lane",
        "started_at",
        "completed_at",
        "stop_reason",
        "incomplete_reason",
    },
    "gate_decision_records": {
        "gate_decision_id",
        "candidate_tool_name",
        "canonical_tool_name",
        "gate_results",
        "candidate_state_version",
        "revalidation_state_version",
        "argument_binding_refs",
        "decision",
        "reason_code",
    },
    "tool_call_records": {
        "tool_call_id",
        "gate_decision_id",
        "status",
        "attempt",
        "failure_code",
        "result_ref",
        "validated_task_state_version",
        "argument_binding_refs",
    },
    "observation_records": {
        "observation_id",
        "source",
        "observation_type",
        "minimal_value",
        "observed_at",
        "visibility",
    },
    "context_manifest_records": {
        "model_call_ref",
        "message_refs",
        "task_refs",
        "observation_refs",
        "model_visible_toolset_hash",
        "redaction_policy_version",
    },
    "trace_event_records": {
        "event_type",
        "related_ids",
        "safe_fields",
        "occurred_at",
    },
    "eval_result_records": {
        "case_id",
        "lane",
        "version_manifest",
        "grader_results",
        "critical_failure",
        "trace_ref",
    },
}


def test_empty_namespace_upgrades_to_head(postgres_namespace) -> None:
    engine = postgres_namespace.build_engine()
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert tables == EXPECTED_RECORD_TABLES | {"alembic_version"}

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == (
                postgres_namespace.schema
            )
            assert connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20260726_0001"
            )
    finally:
        engine.dispose()


def test_revision_table_set_matches_sqlalchemy_metadata(postgres_namespace) -> None:
    engine = postgres_namespace.build_engine()
    try:
        migrated_tables = set(inspect(engine).get_table_names()) - {
            "alembic_version"
        }
        assert migrated_tables == set(Base.metadata.tables)
    finally:
        engine.dispose()


def test_initial_projection_contains_scoped_required_fields(
    postgres_namespace,
) -> None:
    engine = postgres_namespace.build_engine()
    try:
        inspector = inspect(engine)
        for table_name, required_columns in REQUIRED_COLUMNS.items():
            actual_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            assert required_columns <= actual_columns

        conversation_columns = {
            column["name"]
            for column in inspector.get_columns("conversation_records")
        }
        assert "task_id" not in conversation_columns
    finally:
        engine.dispose()


def test_pgvector_is_available_without_vector_schema(
    postgres_namespace,
) -> None:
    engine = postgres_namespace.build_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ) == "0.8.2"
            assert connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND udt_name = 'vector'
                    """
                )
            ) == 0
    finally:
        engine.dispose()


def test_upgrade_head_is_idempotent(postgres_namespace) -> None:
    upgrade_database_to_head(
        postgres_namespace.database_url,
        schema=postgres_namespace.schema,
    )
    engine = postgres_namespace.build_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
    finally:
        engine.dispose()


def test_eval_run_namespaces_do_not_share_business_state(
    postgres_namespace_factory,
) -> None:
    left = postgres_namespace_factory.create("eval-run-left")
    right = postgres_namespace_factory.create("eval-run-right")
    conversation_id = uuid4()

    left_engine = left.build_engine()
    right_engine = right.build_engine()
    try:
        with left_engine.begin() as connection:
            connection.execute(
                ConversationRow.__table__.insert().values(
                    conversation_id=conversation_id,
                    owner_customer_id="customer-A",
                )
            )

        with left_engine.connect() as connection:
            assert connection.scalar(
                select(ConversationRow.owner_customer_id).where(
                    ConversationRow.conversation_id == conversation_id
                )
            ) == "customer-A"

        with right_engine.connect() as connection:
            assert connection.scalar(
                select(text("count(*)")).select_from(ConversationRow.__table__)
            ) == 0
    finally:
        left_engine.dispose()
        right_engine.dispose()
        postgres_namespace_factory.drop(left)
        postgres_namespace_factory.drop(right)
