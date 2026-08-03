"""Atomically cut Request Understanding storage from v2 to exact v3.

Revision ID: 20260803_0007
Revises: 20260802_0006
Create Date: 2026-08-03
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op
from pydantic import ValidationError

from mini_agent.application.persistence import (
    P0PersistenceEnvelope,
    P0PersistenceIntegrityError,
    P0RecordCode,
    P0RecordReference,
    decode_persistence_record_versioned,
    encode_persistence_record_versioned,
)
from mini_agent.application.records import (
    ConversationTaskLinkRecord,
    MessageRecord,
    MessageDirection,
    RunTaskLinkRecord,
)
from mini_agent.core.request_processing import InitialAcceptedTaskGraphV2
from mini_agent.core.task_state import (
    AcceptedAddGoalTaskDeltaV3,
    AcceptedSupplyInputTaskDeltaV3,
    AcceptedTaskDeltaV2,
    DurablePhase1AddGoalTaskDeltaCandidateV3,
    DurableTaskDeltaCandidateV2,
    InputBinding,
    RequestUnderstandingRecordV2,
    RequestUnderstandingRecordV3,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
    TaskStatus,
)
from mini_agent.core.trace import AgentRunRecord, AgentRunStatus

revision: str = "20260803_0007"
down_revision: str | Sequence[str] | None = "20260802_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE_VERSION_CONSTRAINT = "ck_p0_records_code_version_closed"
_SOURCE_VERSION = "request_understanding_record.p0.v2"
_TARGET_VERSION = "request_understanding_record.p0.v3"
_MIGRATION_BLOCKED_MESSAGE = (
    "request understanding v3 cutover graph is not exactly convertible"
)
_DOWNGRADE_BLOCKED_MESSAGE = (
    "request understanding v3 downgrade graph is not exactly reversible"
)

_PREVIOUS_CODE_VERSION_PAIRS = (
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
    ("request_understanding_record", _SOURCE_VERSION),
    ("order_search_observation_record", "order_search_observation_record.p0.v1"),
    ("order_candidate_set_record", "order_candidate_set_record.p0.v1"),
    ("order_candidate_selection_record", "order_candidate_selection_record.p0.v1"),
    ("shipment_observation_record", "shipment_observation_record.p0.v1"),
    ("shipment_assessment_record", "shipment_assessment_record.p0.v1"),
    ("input_binding_record", "input_binding_record.p0.v2"),
    ("gate_decision_record", "gate_decision_record.p0.v2"),
    ("tool_call_record", "tool_call_record.p0.v2"),
    ("agent_run_record", "agent_run_record.p0.v2"),
    ("run_task_link_record", "run_task_link_record.p0.v2"),
    ("trace_event_record", "trace_event_record.p0.v2"),
)
_TARGET_CODE_VERSION_PAIRS = (
    *_PREVIOUS_CODE_VERSION_PAIRS,
    ("request_understanding_record", _TARGET_VERSION),
)


def _condition(pairs: Sequence[tuple[str, str]]) -> str:
    return " OR ".join(
        f"(record_code = '{code}' AND record_schema_version = '{version}')"
        for code, version in pairs
    )


def _replace_constraint(pairs: Sequence[tuple[str, str]]) -> None:
    op.drop_constraint(_CODE_VERSION_CONSTRAINT, "p0_records", type_="check")
    op.create_check_constraint(
        _CODE_VERSION_CONSTRAINT,
        "p0_records",
        _condition(pairs),
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


def _decode_input(
    raw: object,
    *,
    version: str,
) -> object:
    if not isinstance(raw, dict):
        return raw
    normalized = json.loads(
        json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    )
    payload = normalized.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return raw
    parent_type = (
        RequestUnderstandingRecordV2
        if version == _SOURCE_VERSION
        else RequestUnderstandingRecordV3
    )
    parent = parent_type.model_validate_json(
        json.dumps(payload["data"], ensure_ascii=False, separators=(",", ":")),
        strict=True,
    )
    payload["data"] = _reorder_json_like(
        payload["data"],
        parent.model_dump(mode="json", warnings="error"),
    )
    children = payload.get("logical_children")
    if not isinstance(children, list):
        return raw
    for child in children:
        if (
            not isinstance(child, dict)
            or child.get("child_code") != "accepted_task_delta"
            or not isinstance(child.get("data"), dict)
        ):
            return raw
        child_type = AcceptedTaskDeltaV2
        if version == _TARGET_VERSION:
            child_type = {
                "ADD_GOAL": AcceptedAddGoalTaskDeltaV3,
                "SUPPLY_INPUT": AcceptedSupplyInputTaskDeltaV3,
            }.get(child["data"].get("operation"))
            if child_type is None:
                return raw
        parsed = child_type.model_validate_json(
            json.dumps(
                child["data"],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
        child["data"] = _reorder_json_like(
            child["data"],
            parsed.model_dump(mode="json", warnings="error"),
        )
    return normalized


def _references(
    connection: sa.Connection,
    row: Mapping[str, Any],
) -> tuple[P0RecordReference, ...]:
    raw = (
        connection.execute(
            sa.text(
                """
                SELECT ordinal, relation, target_record_code,
                       target_logical_identity
                FROM p0_record_references
                WHERE source_record_code = :record_code
                  AND source_logical_identity =
                      CAST(:logical_identity AS jsonb)
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
    if tuple(item["ordinal"] for item in raw) != tuple(range(len(raw))):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    return tuple(
        P0RecordReference.model_validate_json(
            json.dumps(
                {
                    "relation": item["relation"],
                    "target_record_code": item["target_record_code"],
                    "target_logical_identity": item["target_logical_identity"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
        for item in raw
    )


def _enum_value(value: object) -> str | None:
    return str(value.value) if isinstance(value, Enum) else None


def _projection(
    envelope: P0PersistenceEnvelope,
    record: object,
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
        "recovery_sort_at": (
            getattr(record, "started_at", None)
            if envelope.record_code is P0RecordCode.AGENT_RUN_RECORD
            else None
        ),
    }


def _assert_projection(
    row: Mapping[str, Any],
    envelope: P0PersistenceEnvelope,
    record: object,
    *,
    error_message: str,
) -> None:
    expected = _projection(envelope, record)
    if any(row[field] != value for field, value in expected.items()):
        raise RuntimeError(error_message)
    owner = row["scope_owner_customer_id"]
    if type(owner) is not str or not owner:
        raise RuntimeError(error_message)
    if (
        envelope.direct_owner_customer_id is not None
        and envelope.direct_owner_customer_id != owner
    ):
        raise RuntimeError(error_message)


def _assert_reference_targets(
    connection: sa.Connection,
    *,
    owner_customer_id: str,
    references: tuple[P0RecordReference, ...],
    error_message: str,
    visited: set[tuple[str, str]] | None = None,
) -> None:
    expected_versions = {
        P0RecordCode.AGENT_RUN_RECORD: frozenset({"agent_run_record.p0.v1"}),
        P0RecordCode.CONTEXT_MANIFEST_RECORD: frozenset(
            {"context_manifest_record.p0.v1"}
        ),
        P0RecordCode.CONVERSATION_RECORD: frozenset(
            {"conversation_record.p0.v1"}
        ),
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD: frozenset(
            {"conversation_task_link_record.p0.v1"}
        ),
        P0RecordCode.GATE_DECISION_RECORD: frozenset(
            {"gate_decision_record.p0.v1"}
        ),
        P0RecordCode.INPUT_BINDING_RECORD: frozenset(
            {"input_binding_record.p0.v1"}
        ),
        P0RecordCode.MESSAGE_RECORD: frozenset({"message_record.p0.v1"}),
        P0RecordCode.OBSERVATION_RECORD: frozenset(
            {"observation_record.p0.v1"}
        ),
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD: frozenset(
            {_SOURCE_VERSION, _TARGET_VERSION}
        ),
        P0RecordCode.REQUEST_UNIT_RECORD: frozenset(
            {"request_unit_record.p0.v1"}
        ),
        P0RecordCode.RUN_TASK_LINK_RECORD: frozenset(
            {"run_task_link_record.p0.v1"}
        ),
        P0RecordCode.TASK_RECORD: frozenset({"task_record.p0.v1"}),
        P0RecordCode.TOOL_CALL_RECORD: frozenset(
            {"tool_call_record.p0.v1"}
        ),
        P0RecordCode.TRACE_EVENT_RECORD: frozenset(
            {"trace_event_record.p0.v1"}
        ),
    }
    seen = set() if visited is None else visited
    for reference in references:
        identity_text = json.dumps(
            [list(item) for item in reference.target_logical_identity],
            separators=(",", ":"),
        )
        reference_key = (reference.target_record_code.value, identity_text)
        if reference_key in seen:
            continue
        seen.add(reference_key)
        rows = (
            connection.execute(
                sa.text(
                    """
                    SELECT *
                    FROM p0_records
                    WHERE record_code = :record_code
                      AND logical_identity = CAST(:logical_identity AS jsonb)
                    LIMIT 2
                    """
                ),
                {
                    "record_code": reference.target_record_code.value,
                    "logical_identity": identity_text,
                },
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            raise RuntimeError(error_message)
        row = rows[0]
        target_owner = row["scope_owner_customer_id"]
        if (
            reference.target_record_code
            is P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT
        ):
            if target_owner is not None:
                raise RuntimeError(error_message)
        elif target_owner != owner_customer_id:
            raise RuntimeError(error_message)
        allowed_versions = expected_versions.get(reference.target_record_code)
        if (
            allowed_versions is None
            or row["record_schema_version"] not in allowed_versions
        ):
            raise RuntimeError(error_message)
        expected_version = row["record_schema_version"]
        target_envelope = _envelope(row["envelope"])
        target_references = _references(connection, row)
        decoded = decode_persistence_record_versioned(
            row["envelope"],
            expected_record_code=reference.target_record_code,
            expected_schema_version=expected_version,
            correlation_ref=uuid4(),
        )
        if (
            target_envelope.record_references != target_references
            or target_envelope.record_code is not reference.target_record_code
            or target_envelope.record_schema_version != expected_version
        ):
            raise RuntimeError(error_message)
        _assert_projection(
            row,
            target_envelope,
            decoded.source_record,
            error_message=error_message,
        )
        _assert_reference_targets(
            connection,
            owner_customer_id=owner_customer_id,
            references=target_references,
            error_message=error_message,
            visited=seen,
        )


def _authoritative_message(
    connection: sa.Connection,
    *,
    owner_customer_id: str,
    message_id: UUID,
    error_message: str,
) -> MessageRecord:
    rows = (
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM p0_records
                WHERE record_code = 'message_record'
                  AND record_schema_version = 'message_record.p0.v1'
                  AND logical_identity = CAST(:logical_identity AS jsonb)
                  AND scope_owner_customer_id = :owner_customer_id
                LIMIT 2
                """
            ),
            {
                "logical_identity": json.dumps(
                    [["message_id", str(message_id)]], separators=(",", ":")
                ),
                "owner_customer_id": owner_customer_id,
            },
        )
        .mappings()
        .all()
    )
    if len(rows) != 1:
        raise RuntimeError(error_message)
    row = rows[0]
    envelope = _envelope(row["envelope"])
    references = _references(connection, row)
    decoded = decode_persistence_record_versioned(
        row["envelope"],
        expected_record_code=P0RecordCode.MESSAGE_RECORD,
        expected_schema_version="message_record.p0.v1",
        correlation_ref=uuid4(),
    )
    if (
        envelope.record_references != references
        or type(decoded.source_record) is not MessageRecord
        or decoded.logical_children
    ):
        raise RuntimeError(error_message)
    _assert_projection(
        row,
        envelope,
        decoded.source_record,
        error_message=error_message,
    )
    return decoded.source_record


def _exact_owned_record(
    connection: sa.Connection,
    *,
    owner_customer_id: str,
    record_code: P0RecordCode,
    schema_version: str,
    logical_identity: tuple[tuple[str, UUID], ...],
    error_message: str,
) -> tuple[object, tuple[object, ...]]:
    identity_json = json.dumps(
        [[name, str(value)] for name, value in logical_identity],
        separators=(",", ":"),
    )
    rows = (
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM p0_records
                WHERE record_code = :record_code
                  AND record_schema_version = :schema_version
                  AND logical_identity = CAST(:logical_identity AS jsonb)
                  AND scope_owner_customer_id = :owner_customer_id
                LIMIT 2
                """
            ),
            {
                "record_code": record_code.value,
                "schema_version": schema_version,
                "logical_identity": identity_json,
                "owner_customer_id": owner_customer_id,
            },
        )
        .mappings()
        .all()
    )
    if len(rows) != 1:
        raise RuntimeError(error_message)
    row = rows[0]
    envelope = _envelope(row["envelope"])
    references = _references(connection, row)
    decoded = decode_persistence_record_versioned(
        row["envelope"],
        expected_record_code=record_code,
        expected_schema_version=schema_version,
        correlation_ref=uuid4(),
    )
    if (
        envelope.record_code is not record_code
        or envelope.record_schema_version != schema_version
        or [list(item) for item in envelope.logical_identity]
        != row["logical_identity"]
        or envelope.record_references != references
    ):
        raise RuntimeError(error_message)
    _assert_projection(
        row,
        envelope,
        decoded.source_record,
        error_message=error_message,
    )
    return decoded.source_record, decoded.logical_children


def _owned_state_record_at_version(
    connection: sa.Connection,
    *,
    owner_customer_id: str,
    record_code: P0RecordCode,
    schema_version: str,
    logical_identity: tuple[tuple[str, UUID], ...],
    state_version: int,
    error_message: str,
) -> tuple[object, tuple[object, ...]]:
    current, current_children = _exact_owned_record(
        connection,
        owner_customer_id=owner_customer_id,
        record_code=record_code,
        schema_version=schema_version,
        logical_identity=logical_identity,
        error_message=error_message,
    )
    current_version = getattr(current, "state_version", None)
    if current_version == state_version:
        return current, current_children
    if type(current_version) is not int or current_version < state_version:
        raise RuntimeError(error_message)
    identity_json = json.dumps(
        [[name, str(value)] for name, value in logical_identity],
        separators=(",", ":"),
    )
    rows = (
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM p0_record_state_history
                WHERE record_code = :record_code
                  AND record_schema_version = :schema_version
                  AND logical_identity = CAST(:logical_identity AS jsonb)
                  AND scope_owner_customer_id = :owner_customer_id
                  AND state_version = :state_version
                LIMIT 2
                """
            ),
            {
                "record_code": record_code.value,
                "schema_version": schema_version,
                "logical_identity": identity_json,
                "owner_customer_id": owner_customer_id,
                "state_version": state_version,
            },
        )
        .mappings()
        .all()
    )
    if len(rows) != 1:
        raise RuntimeError(error_message)
    row = rows[0]
    envelope = _envelope(row["envelope"])
    decoded = decode_persistence_record_versioned(
        row["envelope"],
        expected_record_code=record_code,
        expected_schema_version=schema_version,
        correlation_ref=uuid4(),
    )
    if (
        envelope.record_code is not record_code
        or envelope.record_schema_version != schema_version
        or [list(item) for item in envelope.logical_identity]
        != row["logical_identity"]
        or getattr(decoded.source_record, "state_version", None)
        != state_version
    ):
        raise RuntimeError(error_message)
    return decoded.source_record, decoded.logical_children


def _assert_provenance(
    connection: sa.Connection,
    *,
    owner_customer_id: str,
    record: RequestUnderstandingRecordV3,
    error_message: str,
) -> None:
    run, run_children = _exact_owned_record(
        connection,
        owner_customer_id=owner_customer_id,
        record_code=P0RecordCode.AGENT_RUN_RECORD,
        schema_version="agent_run_record.p0.v1",
        logical_identity=(("run_id", record.run_id),),
        error_message=error_message,
    )
    if type(run) is not AgentRunRecord or run_children:
        raise RuntimeError(error_message)
    projections: list[object] = list(
        record.contextualization.resolved_reference_candidates
    )
    for candidate in record.task_delta_candidates:
        if type(candidate) is not DurablePhase1AddGoalTaskDeltaCandidateV3:
            raise RuntimeError(error_message)
        projections.extend(candidate.input_candidates)
    direct_source_refs = {
        record.message_ref,
        *record.contextualization.source_message_refs,
        *(
            source_ref
            for uncertainty in record.contextualization.uncertainties
            for source_ref in uncertainty.source_message_refs
        ),
    }
    projection_source_refs = {
        getattr(projection, "source_ref", None) for projection in projections
    }
    if any(type(source_ref) is not UUID for source_ref in projection_source_refs):
        raise RuntimeError(error_message)
    messages: dict[UUID, MessageRecord] = {}
    for source_ref in direct_source_refs | projection_source_refs:
        message = _authoritative_message(
            connection,
            owner_customer_id=owner_customer_id,
            message_id=source_ref,
            error_message=error_message,
        )
        if (
            message.conversation_id != run.conversation_id
            or (
                source_ref == record.message_ref
                and message.direction is not MessageDirection.USER
            )
            or (
                source_ref in projection_source_refs
                and message.direction is not MessageDirection.USER
            )
        ):
            raise RuntimeError(error_message)
        messages[source_ref] = message
    for projection in projections:
        source_ref = getattr(projection, "source_ref", None)
        start = getattr(projection, "source_span_start", None)
        end = getattr(projection, "source_span_end_exclusive", None)
        digest = getattr(projection, "source_quote_sha256", None)
        if (
            type(source_ref) is not UUID
            or type(start) is not int
            or type(end) is not int
            or type(digest) is not str
        ):
            raise RuntimeError(error_message)
        message = messages.get(source_ref)
        if (
            message is None
            or start < 0
            or end <= start
            or end > len(message.content)
            or sha256(message.content[start:end].encode("utf-8")).hexdigest()
            != digest
        ):
            raise RuntimeError(error_message)


def _assert_phase1_effect_closure(
    connection: sa.Connection,
    *,
    owner_customer_id: str,
    record: RequestUnderstandingRecordV2,
    children: tuple[AcceptedTaskDeltaV2, ...],
    error_message: str,
) -> None:
    run, run_children = _exact_owned_record(
        connection,
        owner_customer_id=owner_customer_id,
        record_code=P0RecordCode.AGENT_RUN_RECORD,
        schema_version="agent_run_record.p0.v1",
        logical_identity=(("run_id", record.run_id),),
        error_message=error_message,
    )
    if type(run) is not AgentRunRecord or run_children:
        raise RuntimeError(error_message)
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in record.task_delta_candidates
    }
    for child in children:
        candidate = candidate_by_id.get(child.candidate_ref)
        if (
            candidate is None
            or len(candidate.input_candidates) != 1
            or child.message_ref != record.message_ref
            or child.operation is not candidate.operation
            or child.goal_text != candidate.goal_patch
        ):
            raise RuntimeError(error_message)
        current_task, current_task_children = _exact_owned_record(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.TASK_RECORD,
            schema_version="task_record.p0.v1",
            logical_identity=(("task_id", child.task_id),),
            error_message=error_message,
        )
        unit_rows = (
            connection.execute(
                sa.text(
                    """
                    SELECT request_unit_id
                    FROM p0_records
                    WHERE record_code = 'request_unit_record'
                      AND record_schema_version = 'request_unit_record.p0.v1'
                      AND task_id = :task_id
                      AND scope_owner_customer_id = :owner_customer_id
                    LIMIT 2
                    """
                ),
                {
                    "task_id": child.task_id,
                    "owner_customer_id": owner_customer_id,
                },
            )
            .mappings()
            .all()
        )
        if len(unit_rows) != 1 or type(unit_rows[0]["request_unit_id"]) is not UUID:
            raise RuntimeError(error_message)
        current_unit, current_unit_children = _exact_owned_record(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            schema_version="request_unit_record.p0.v1",
            logical_identity=(("request_unit_id", unit_rows[0]["request_unit_id"]),),
            error_message=error_message,
        )
        if len(child.input_binding_refs) != 1:
            raise RuntimeError(error_message)
        binding, binding_children = _exact_owned_record(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.INPUT_BINDING_RECORD,
            schema_version="input_binding_record.p0.v1",
            logical_identity=(("binding_id", child.input_binding_refs[0]),),
            error_message=error_message,
        )
        if (
            type(current_task) is not TaskRecord
            or type(current_unit) is not RequestUnitRecord
            or type(binding) is not InputBinding
            or current_unit_children
            or binding_children
        ):
            raise RuntimeError(error_message)
        task, task_children = _owned_state_record_at_version(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.TASK_RECORD,
            schema_version="task_record.p0.v1",
            logical_identity=(("task_id", child.task_id),),
            state_version=child.result_task_state_version,
            error_message=error_message,
        )
        unit, unit_children = _owned_state_record_at_version(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            schema_version="request_unit_record.p0.v1",
            logical_identity=(("request_unit_id", unit_rows[0]["request_unit_id"]),),
            state_version=child.result_task_state_version,
            error_message=error_message,
        )
        if (
            type(task) is not TaskRecord
            or type(unit) is not RequestUnitRecord
            or task_children
            or unit_children
        ):
            raise RuntimeError(error_message)
        try:
            InitialAcceptedTaskGraphV2(
                accepted_delta=child,
                input_binding=binding,
                task=task,
                request_unit=unit,
            )
        except (TypeError, ValueError, ValidationError, RecursionError):
            raise RuntimeError(error_message) from None
        candidate_input = candidate.input_candidates[0]
        normalized_value = candidate_input.candidate_value.strip()
        if normalized_value[:2].casefold() == "o-":
            normalized_value = f"O-{normalized_value[2:]}"
        if (
            binding.name != candidate_input.name
            or binding.normalized_value != normalized_value
            or binding.authority is not candidate_input.authority
            or binding.source_refs != (candidate_input.source_ref,)
        ):
            raise RuntimeError(error_message)

        if (
            current_task.task_id != child.task_id
            or current_unit.task_id != child.task_id
            or current_task.state_version != current_unit.state_version
            or current_task.status is not current_unit.status
        ):
            raise RuntimeError(error_message)
        expected_version = 1
        expected_status = TaskStatus.ACTIVE
        before_task = task
        before_unit = unit
        for transition in current_task_children:
            if (
                type(transition) is not TaskStateTransition
                or transition.task_id != child.task_id
                or transition.request_unit_id != current_unit.request_unit_id
                or transition.base_state_version != expected_version
                or transition.result_state_version != expected_version + 1
                or transition.from_status is not expected_status
                or transition.changed_at < before_task.updated_at
                or transition.changed_at < before_unit.updated_at
                or transition.changed_at > current_task.updated_at
            ):
                raise RuntimeError(error_message)
            after_task, _after_task_children = _owned_state_record_at_version(
                connection,
                owner_customer_id=owner_customer_id,
                record_code=P0RecordCode.TASK_RECORD,
                schema_version="task_record.p0.v1",
                logical_identity=(("task_id", child.task_id),),
                state_version=transition.result_state_version,
                error_message=error_message,
            )
            after_unit, after_unit_children = _owned_state_record_at_version(
                connection,
                owner_customer_id=owner_customer_id,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                schema_version="request_unit_record.p0.v1",
                logical_identity=(
                    ("request_unit_id", current_unit.request_unit_id),
                ),
                state_version=transition.result_state_version,
                error_message=error_message,
            )
            if (
                type(after_task) is not TaskRecord
                or type(after_unit) is not RequestUnitRecord
                or after_unit_children
                or after_task
                != before_task.model_copy(
                    update={
                        "status": transition.to_status,
                        "state_version": transition.result_state_version,
                        "updated_at": transition.changed_at,
                    }
                )
                or after_unit
                != before_unit.model_copy(
                    update={
                        "status": transition.to_status,
                        "state_version": transition.result_state_version,
                        "updated_at": transition.changed_at,
                    }
                )
            ):
                raise RuntimeError(error_message)
            before_task = after_task
            before_unit = after_unit
            expected_version = transition.result_state_version
            expected_status = transition.to_status
        if (
            expected_version != current_task.state_version
            or expected_status is not current_task.status
            or before_task != current_task
            or before_unit != current_unit
        ):
            raise RuntimeError(error_message)

        expected_conversation_link = ConversationTaskLinkRecord(
            schema_version="conversation_task_link_record.p0.v1",
            conversation_id=run.conversation_id,
            task_id=child.task_id,
            link_reason="CURRENT_MESSAGE_ACCEPTED_DELTA",
            linked_at=child.accepted_at,
            ended_at=None,
        )
        conversation_link_envelope = encode_persistence_record_versioned(
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            "conversation_task_link_record.p0.v1",
            expected_conversation_link,
        )
        conversation_link, conversation_link_children = _exact_owned_record(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            schema_version="conversation_task_link_record.p0.v1",
            logical_identity=conversation_link_envelope.logical_identity,
            error_message=error_message,
        )
        expected_run_link = RunTaskLinkRecord(
            schema_version="run_task_link_record.p0.v1",
            run_id=record.run_id,
            task_id=child.task_id,
            base_task_state_version=None,
            result_task_state_version=None,
        )
        run_link_envelope = encode_persistence_record_versioned(
            P0RecordCode.RUN_TASK_LINK_RECORD,
            "run_task_link_record.p0.v1",
            expected_run_link,
        )
        run_link, run_link_children = _exact_owned_record(
            connection,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            schema_version="run_task_link_record.p0.v1",
            logical_identity=run_link_envelope.logical_identity,
            error_message=error_message,
        )
        active_run = run.status in (
            AgentRunStatus.CREATED,
            AgentRunStatus.RUNNING,
        )
        expected_terminal_result: int | None = None
        if not active_run:
            if run.completed_at is None:
                raise RuntimeError(error_message)
            eligible_versions = []
            for version in range(
                child.result_task_state_version,
                current_task.state_version + 1,
            ):
                state, _state_children = _owned_state_record_at_version(
                    connection,
                    owner_customer_id=owner_customer_id,
                    record_code=P0RecordCode.TASK_RECORD,
                    schema_version="task_record.p0.v1",
                    logical_identity=(("task_id", child.task_id),),
                    state_version=version,
                    error_message=error_message,
                )
                if (
                    type(state) is TaskRecord
                    and state.updated_at <= run.completed_at
                ):
                    eligible_versions.append(version)
            if not eligible_versions:
                raise RuntimeError(error_message)
            expected_terminal_result = max(eligible_versions)
        if (
            type(conversation_link) is not ConversationTaskLinkRecord
            or conversation_link.schema_version
            != expected_conversation_link.schema_version
            or conversation_link.conversation_id
            != expected_conversation_link.conversation_id
            or conversation_link.task_id != expected_conversation_link.task_id
            or conversation_link.link_reason
            != expected_conversation_link.link_reason
            or conversation_link.linked_at != expected_conversation_link.linked_at
            or conversation_link.ended_at is not None
            or conversation_link_children
            or type(run_link) is not RunTaskLinkRecord
            or run_link.run_id != expected_run_link.run_id
            or run_link.task_id != expected_run_link.task_id
            or run_link.base_task_state_version is not None
            or (
                active_run
                and run_link.result_task_state_version is not None
            )
            or (
                not active_run
                and run_link.result_task_state_version
                != expected_terminal_result
            )
            or run_link_children
        ):
            raise RuntimeError(error_message)


def _decode_ru_row(
    connection: sa.Connection,
    row: Mapping[str, Any],
    *,
    version: str,
    error_message: str,
) -> tuple[
    P0PersistenceEnvelope,
    RequestUnderstandingRecordV2 | RequestUnderstandingRecordV3,
    tuple[
        AcceptedTaskDeltaV2
        | AcceptedAddGoalTaskDeltaV3
        | AcceptedSupplyInputTaskDeltaV3,
        ...,
    ],
]:
    envelope = _envelope(row["envelope"])
    references = _references(connection, row)
    if (
        row["record_code"] != P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value
        or row["record_schema_version"] != version
        or envelope.record_code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
        or envelope.record_schema_version != version
        or [list(item) for item in envelope.logical_identity]
        != row["logical_identity"]
        or envelope.record_references != references
    ):
        raise RuntimeError(error_message)
    decoded = decode_persistence_record_versioned(
        _decode_input(row["envelope"], version=version),
        expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        expected_schema_version=version,
        correlation_ref=uuid4(),
    )
    expected_parent = (
        RequestUnderstandingRecordV2
        if version == _SOURCE_VERSION
        else RequestUnderstandingRecordV3
    )
    expected_child = (
        AcceptedTaskDeltaV2
        if version == _SOURCE_VERSION
        else AcceptedAddGoalTaskDeltaV3
    )
    if type(decoded.source_record) is not expected_parent or any(
        type(child) is not expected_child for child in decoded.logical_children
    ):
        raise RuntimeError(error_message)
    _assert_projection(
        row,
        envelope,
        decoded.source_record,
        error_message=error_message,
    )
    owner = row["scope_owner_customer_id"]
    if type(owner) is not str:
        raise RuntimeError(error_message)
    _assert_reference_targets(
        connection,
        owner_customer_id=owner,
        references=references,
        error_message=error_message,
    )
    if version == _SOURCE_VERSION:
        _assert_phase1_effect_closure(
            connection,
            owner_customer_id=owner,
            record=decoded.source_record,
            children=decoded.logical_children,
            error_message=error_message,
        )
    else:
        _assert_provenance(
            connection,
            owner_customer_id=owner,
            record=decoded.source_record,
            error_message=error_message,
        )
        reversible_record, reversible_children = _to_v2(
            decoded.source_record,
            decoded.logical_children,
        )
        _assert_phase1_effect_closure(
            connection,
            owner_customer_id=owner,
            record=reversible_record,
            children=reversible_children,
            error_message=error_message,
        )
    return envelope, decoded.source_record, decoded.logical_children


def _to_v3(
    source: RequestUnderstandingRecordV2,
    children: tuple[AcceptedTaskDeltaV2 | AcceptedAddGoalTaskDeltaV3, ...],
) -> tuple[RequestUnderstandingRecordV3, tuple[AcceptedAddGoalTaskDeltaV3, ...]]:
    if any(type(child) is not AcceptedTaskDeltaV2 for child in children):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    candidates = tuple(
        DurablePhase1AddGoalTaskDeltaCandidateV3(**candidate.model_dump())
        for candidate in source.task_delta_candidates
        if type(candidate) is DurableTaskDeltaCandidateV2
    )
    if len(candidates) != len(source.task_delta_candidates):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    child_by_candidate = {
        child.candidate_ref: AcceptedAddGoalTaskDeltaV3(**child.model_dump())
        for child in children
    }
    if len(child_by_candidate) != len(children):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    target_children = tuple(
        child_by_candidate[candidate.candidate_id]
        for candidate in candidates
        if candidate.candidate_id in child_by_candidate
    )
    if len(target_children) != len(children):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)
    target = RequestUnderstandingRecordV3(
        request_understanding_record_id=source.request_understanding_record_id,
        run_id=source.run_id,
        message_ref=source.message_ref,
        record_schema_version=_TARGET_VERSION,
        model_input_schema_version=source.model_input_schema_version,
        model_output_schema_version=source.model_output_schema_version,
        contextualization=source.contextualization,
        task_delta_candidates=candidates,
        candidate_validation=source.candidate_validation,
        accepted_delta_refs=source.accepted_delta_refs,
        proposed_base_task_state_version=(
            source.proposed_base_task_state_version
        ),
        validated_task_state_version=source.validated_task_state_version,
        next_move_candidate_ref=source.next_move_candidate_ref,
        created_at=source.created_at,
    )
    return target, target_children


def _to_v2(
    source: RequestUnderstandingRecordV3,
    children: tuple[
        AcceptedTaskDeltaV2
        | AcceptedAddGoalTaskDeltaV3
        | AcceptedSupplyInputTaskDeltaV3,
        ...,
    ],
) -> tuple[RequestUnderstandingRecordV2, tuple[AcceptedTaskDeltaV2, ...]]:
    if (
        source.model_input_schema_version != "e2e01-thin-v1"
        or source.model_output_schema_version != "e2e01-thin-v2"
        or any(
            type(candidate) is not DurablePhase1AddGoalTaskDeltaCandidateV3
            for candidate in source.task_delta_candidates
        )
        or any(type(child) is not AcceptedAddGoalTaskDeltaV3 for child in children)
    ):
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
    target_candidates = tuple(
        DurableTaskDeltaCandidateV2(**candidate.model_dump())
        for candidate in source.task_delta_candidates
    )
    child_by_candidate = {
        child.candidate_ref: AcceptedTaskDeltaV2(**child.model_dump())
        for child in children
    }
    target_children = tuple(
        sorted(
            (
                child_by_candidate[candidate.candidate_id]
                for candidate in target_candidates
                if candidate.candidate_id in child_by_candidate
            ),
            key=lambda child: str(child.accepted_delta_id),
        )
    )
    if len(target_children) != len(children):
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE)
    target = RequestUnderstandingRecordV2(
        request_understanding_record_id=source.request_understanding_record_id,
        run_id=source.run_id,
        message_ref=source.message_ref,
        schema_version=_SOURCE_VERSION,
        model_input_schema_version=source.model_input_schema_version,
        model_output_schema_version=source.model_output_schema_version,
        contextualization=source.contextualization,
        task_delta_candidates=target_candidates,
        candidate_validation=source.candidate_validation,
        accepted_delta_refs=source.accepted_delta_refs,
        proposed_base_task_state_version=(
            source.proposed_base_task_state_version
        ),
        validated_task_state_version=source.validated_task_state_version,
        next_move_candidate_ref=source.next_move_candidate_ref,
        created_at=source.created_at,
    )
    return target, target_children


def _ru_rows(
    connection: sa.Connection,
    *,
    version: str,
) -> list[Mapping[str, Any]]:
    return list(
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM p0_records
                WHERE record_code = 'request_understanding_record'
                  AND record_schema_version = :version
                ORDER BY record_id
                FOR UPDATE
                """
            ),
            {"version": version},
        ).mappings()
    )


def _prepare(
    connection: sa.Connection,
    *,
    source_version: str,
    target_version: str,
    error_message: str,
) -> list[tuple[UUID, P0PersistenceEnvelope, object]]:
    prepared: list[tuple[UUID, P0PersistenceEnvelope, object]] = []
    for row in _ru_rows(connection, version=source_version):
        source_envelope, source, children = _decode_ru_row(
            connection,
            row,
            version=source_version,
            error_message=error_message,
        )
        if source_version == _SOURCE_VERSION:
            if type(source) is not RequestUnderstandingRecordV2:
                raise RuntimeError(error_message)
            target, target_children = _to_v3(source, children)
        else:
            if type(source) is not RequestUnderstandingRecordV3:
                raise RuntimeError(error_message)
            target, target_children = _to_v2(source, children)
        target_envelope = encode_persistence_record_versioned(
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            target_version,
            target,
            logical_children=target_children,
        )
        if (
            target_envelope.logical_identity != source_envelope.logical_identity
            or target_envelope.record_references
            != source_envelope.record_references
        ):
            raise RuntimeError(error_message)
        decoded_target = decode_persistence_record_versioned(
            target_envelope,
            expected_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            expected_schema_version=target_version,
            correlation_ref=uuid4(),
        )
        if (
            decoded_target.source_record != target
            or decoded_target.logical_children != target_children
        ):
            raise RuntimeError(error_message)
        if target_version == _TARGET_VERSION:
            owner = row["scope_owner_customer_id"]
            if type(owner) is not str:
                raise RuntimeError(error_message)
            _assert_provenance(
                connection,
                owner_customer_id=owner,
                record=target,
                error_message=error_message,
            )
        prepared.append((row["record_id"], target_envelope, target))
    return prepared


def _write_prepared(
    connection: sa.Connection,
    prepared: Sequence[tuple[UUID, P0PersistenceEnvelope, object]],
) -> None:
    for record_id, envelope, record in prepared:
        values = _projection(envelope, record)
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
                    values["envelope"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "record_id": record_id,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE)


def _assert_postcondition(
    connection: sa.Connection,
    *,
    forbidden_version: str,
    current_version: str,
    error_message: str,
) -> None:
    residual = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM p0_records
            WHERE record_code = 'request_understanding_record'
              AND record_schema_version = :version
            """
        ),
        {"version": forbidden_version},
    )
    if residual != 0:
        raise RuntimeError(error_message)
    for row in _ru_rows(connection, version=current_version):
        _decode_ru_row(
            connection,
            row,
            version=current_version,
            error_message=error_message,
        )


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE p0_records, p0_record_references "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    try:
        prepared = _prepare(
            connection,
            source_version=_SOURCE_VERSION,
            target_version=_TARGET_VERSION,
            error_message=_MIGRATION_BLOCKED_MESSAGE,
        )
        _replace_constraint(_TARGET_CODE_VERSION_PAIRS)
        _write_prepared(connection, prepared)
        _assert_postcondition(
            connection,
            forbidden_version=_SOURCE_VERSION,
            current_version=_TARGET_VERSION,
            error_message=_MIGRATION_BLOCKED_MESSAGE,
        )
    except RuntimeError as error:
        if str(error) == _MIGRATION_BLOCKED_MESSAGE:
            raise error from None
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE) from None
    except (
        AssertionError,
        KeyError,
        P0PersistenceIntegrityError,
        RecursionError,
        TypeError,
        ValidationError,
        ValueError,
    ):
        raise RuntimeError(_MIGRATION_BLOCKED_MESSAGE) from None


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE p0_records, p0_record_references "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    try:
        prepared = _prepare(
            connection,
            source_version=_TARGET_VERSION,
            target_version=_SOURCE_VERSION,
            error_message=_DOWNGRADE_BLOCKED_MESSAGE,
        )
        _write_prepared(connection, prepared)
        _assert_postcondition(
            connection,
            forbidden_version=_TARGET_VERSION,
            current_version=_SOURCE_VERSION,
            error_message=_DOWNGRADE_BLOCKED_MESSAGE,
        )
        _replace_constraint(_PREVIOUS_CODE_VERSION_PAIRS)
    except RuntimeError as error:
        if str(error) == _DOWNGRADE_BLOCKED_MESSAGE:
            raise error from None
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE) from None
    except (
        AssertionError,
        KeyError,
        P0PersistenceIntegrityError,
        RecursionError,
        TypeError,
        ValidationError,
        ValueError,
    ):
        raise RuntimeError(_DOWNGRADE_BLOCKED_MESSAGE) from None
