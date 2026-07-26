from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Physical persistence metadata; Core contracts remain owned by Core."""


class ConversationRow(Base):
    __tablename__ = "conversation_records"

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    owner_customer_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )

class AgentRunRow(Base):
    __tablename__ = "agent_run_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'INCOMPLETE')",
            name="ck_agent_run_records_status",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation_records.conversation_id"),
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider_lane: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(64))
    incomplete_reason: Mapped[str | None] = mapped_column(String(128))


class MessageRow(Base):
    __tablename__ = "message_records"

    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation_records.conversation_id"),
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(32))
    controlled_content: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ModelVisibleToolsetArtifactRow(Base):
    __tablename__ = "model_visible_toolset_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "model_visible_toolset_hash",
            name="uq_toolset_artifacts_hash",
        ),
    )

    artifact_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64))
    model_visible_toolset_hash: Mapped[str] = mapped_column(String(64))
    provider_visible_tool_specs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TaskRow(Base):
    __tablename__ = "task_records"
    __table_args__ = (
        CheckConstraint(
            "state_version >= 0",
            name="ck_task_records_state_version",
        ),
    )

    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    owner_customer_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    state_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_outcome_ref: Mapped[str | None] = mapped_column(String(128))


class InputBindingRow(Base):
    __tablename__ = "input_binding_records"
    __table_args__ = (
        CheckConstraint(
            "version >= 0",
            name="ck_input_binding_records_version",
        ),
    )

    binding_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    normalized_value: Mapped[Any] = mapped_column(JSONB)
    authority: Mapped[str] = mapped_column(String(64))
    source_refs: Mapped[list[str]] = mapped_column(JSONB)
    validation_status: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class RequestUnderstandingRow(Base):
    __tablename__ = "request_understanding_records"
    __table_args__ = (
        CheckConstraint(
            "candidate_state_version >= 0",
            name="ck_request_understanding_candidate_version",
        ),
        CheckConstraint(
            "revalidation_state_version >= 0",
            name="ck_request_understanding_revalidation_version",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        primary_key=True,
    )
    message_ref: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("message_records.message_id"),
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    candidate_validation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    accepted_delta_refs: Mapped[list[str]] = mapped_column(JSONB)
    candidate_state_version: Mapped[int] = mapped_column(Integer)
    revalidation_state_version: Mapped[int] = mapped_column(Integer)
    next_move_candidate_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class RequestUnitRow(Base):
    __tablename__ = "request_unit_records"
    __table_args__ = (
        CheckConstraint(
            "state_version >= 0",
            name="ck_request_unit_records_state_version",
        ),
    )

    request_unit_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("task_records.task_id"),
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    goal_source_refs: Mapped[list[str]] = mapped_column(JSONB)
    input_binding_refs: Mapped[list[str]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32))
    state_version: Mapped[int] = mapped_column(Integer)
    result_refs: Mapped[list[str]] = mapped_column(JSONB)


class ConversationTaskLinkRow(Base):
    __tablename__ = "conversation_task_link_records"
    __table_args__ = (
        Index(
            "ix_conversation_task_links_conversation",
            "conversation_id",
        ),
        Index("ix_conversation_task_links_task", "task_id"),
    )

    link_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation_records.conversation_id"),
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("task_records.task_id"),
    )
    link_reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunTaskLinkRow(Base):
    __tablename__ = "run_task_link_records"
    __table_args__ = (
        CheckConstraint(
            "base_state_version >= 0",
            name="ck_run_task_links_base_version",
        ),
        CheckConstraint(
            "result_state_version IS NULL OR result_state_version >= base_state_version",
            name="ck_run_task_links_result_version",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        primary_key=True,
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("task_records.task_id"),
        primary_key=True,
    )
    base_state_version: Mapped[int] = mapped_column(Integer)
    result_state_version: Mapped[int | None] = mapped_column(Integer)


class GateDecisionRow(Base):
    __tablename__ = "gate_decision_records"
    __table_args__ = (
        CheckConstraint(
            "candidate_state_version >= 0",
            name="ck_gate_decision_candidate_version",
        ),
        CheckConstraint(
            "revalidation_state_version >= 0",
            name="ck_gate_decision_revalidation_version",
        ),
    )

    gate_decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        index=True,
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("task_records.task_id"),
    )
    request_unit_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("request_unit_records.request_unit_id"),
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    candidate_tool_name: Mapped[str] = mapped_column(String(128))
    canonical_tool_name: Mapped[str | None] = mapped_column(String(128))
    gate_results: Mapped[dict[str, Any]] = mapped_column(JSONB)
    candidate_state_version: Mapped[int] = mapped_column(Integer)
    revalidation_state_version: Mapped[int] = mapped_column(Integer)
    argument_binding_refs: Mapped[list[str]] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ToolCallRow(Base):
    __tablename__ = "tool_call_records"
    __table_args__ = (
        CheckConstraint("attempt >= 1", name="ck_tool_call_records_attempt"),
        CheckConstraint(
            "validated_task_state_version >= 0",
            name="ck_tool_call_records_task_version",
        ),
    )

    tool_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        index=True,
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("task_records.task_id"),
    )
    request_unit_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("request_unit_records.request_unit_id"),
    )
    gate_decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("gate_decision_records.gate_decision_id"),
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    result_ref: Mapped[str | None] = mapped_column(String(128))
    validated_task_state_version: Mapped[int] = mapped_column(Integer)
    argument_binding_refs: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ObservationRow(Base):
    __tablename__ = "observation_records"

    observation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        index=True,
    )
    tool_call_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tool_call_records.tool_call_id"),
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(128))
    observation_type: Mapped[str] = mapped_column(String(128))
    minimal_value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    visibility: Mapped[str] = mapped_column(String(64))


class ContextManifestRow(Base):
    __tablename__ = "context_manifest_records"

    context_manifest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    model_call_ref: Mapped[str] = mapped_column(String(128))
    message_refs: Mapped[list[str]] = mapped_column(JSONB)
    task_refs: Mapped[list[str]] = mapped_column(JSONB)
    observation_refs: Mapped[list[str]] = mapped_column(JSONB)
    model_visible_toolset_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "model_visible_toolset_artifacts.model_visible_toolset_hash",
        ),
    )
    redaction_policy_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TraceEventRow(Base):
    __tablename__ = "trace_event_records"

    trace_event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(128))
    related_ids: Mapped[dict[str, str]] = mapped_column(JSONB)
    safe_fields: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class EvalResultRow(Base):
    __tablename__ = "eval_result_records"
    __table_args__ = (
        Index("ix_eval_result_records_case_lane", "case_id", "lane"),
    )

    eval_result_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_run_records.run_id"),
    )
    schema_version: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[str] = mapped_column(String(128))
    lane: Mapped[str] = mapped_column(String(64))
    version_manifest: Mapped[dict[str, str]] = mapped_column(JSONB)
    grader_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    critical_failure: Mapped[bool] = mapped_column(Boolean)
    trace_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
