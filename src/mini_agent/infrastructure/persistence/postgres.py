from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from enum import Enum
from functools import wraps
from hashlib import sha256
from typing import Any, ParamSpec, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python
from sqlalchemy import and_, delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.application.persistence import (
    DecodedP0PersistenceRecord,
    P0PersistenceEnvelope,
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    P0RecordReference,
    decode_persistence_record,
    decode_persistence_record_versioned,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyTaskTransitionCommand,
    ConditionalWriteResult,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateInitialTaskGraphCommand,
    CreateRunCommand,
    CreateToolCallCommand,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    ExactRunEvidenceClosure,
    FinalizeRunCommand,
    FinalizeToolCallCommand,
    InsertOnlyWriteResult,
    MessageRecord,
    ObservationWriteResult,
    RunTaskLinkRecord,
    SaveObservationCommand,
    ToolDispatchFenceWriteResult,
    TransitionRunCommand,
    TrustedOwnerScope,
)
from mini_agent.core.memory import ContextManifest, OrderObservation
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    AcceptedTaskDeltaV2,
    InputBinding,
    RequestUnderstandingRecord,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
)
from mini_agent.core.tool_system import (
    GateDecision,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolCallRecord,
    ToolCallStatus,
    ToolEffect,
)
from mini_agent.core.trace import (
    AgentRunRecord,
    AgentRunStatus,
    StopReason,
    TraceEvent,
    TraceEventType,
)
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
)

_RecordT = TypeVar("_RecordT", bound=BaseModel)
_ResultT = TypeVar("_ResultT")
_Params = ParamSpec("_Params")
_PRIVATE_RECORD_CODES = frozenset(
    {
        P0RecordCode.CONVERSATION_RECORD,
        P0RecordCode.MESSAGE_RECORD,
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        P0RecordCode.TASK_RECORD,
        P0RecordCode.REQUEST_UNIT_RECORD,
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
        P0RecordCode.RUN_TASK_LINK_RECORD,
        P0RecordCode.INPUT_BINDING_RECORD,
        P0RecordCode.AGENT_RUN_RECORD,
        P0RecordCode.GATE_DECISION_RECORD,
        P0RecordCode.TOOL_CALL_RECORD,
        P0RecordCode.OBSERVATION_RECORD,
        P0RecordCode.CONTEXT_MANIFEST_RECORD,
        P0RecordCode.TRACE_EVENT_RECORD,
    }
)
_RECORD_CODE_BY_VALUE = {code.value: code for code in P0RecordCode}
_NORMAL_TERMINAL_TRACE_EVENT_TYPES = frozenset(
    {
        TraceEventType.TASK_STATE_CHANGED,
        TraceEventType.RUN_STOPPED,
    }
)
_ACTIVE_TOOL_CALL_STATUSES = frozenset(
    {
        ToolCallStatus.CREATED,
        ToolCallStatus.RUNNING,
    }
)
_EXACT_RUN_VERSION_BY_CODE = {
    P0RecordCode.CONVERSATION_RECORD: "conversation_record.p0.v1",
    P0RecordCode.MESSAGE_RECORD: "message_record.p0.v1",
    P0RecordCode.REQUEST_UNDERSTANDING_RECORD: (
        "request_understanding_record.p0.v2"
    ),
    P0RecordCode.TASK_RECORD: "task_record.p0.v1",
    P0RecordCode.REQUEST_UNIT_RECORD: "request_unit_record.p0.v1",
    P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
        "conversation_task_link_record.p0.v1"
    ),
    P0RecordCode.RUN_TASK_LINK_RECORD: "run_task_link_record.p0.v1",
    P0RecordCode.INPUT_BINDING_RECORD: "input_binding_record.p0.v1",
    P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT: (
        "model_visible_toolset_artifact.p0.v1"
    ),
    P0RecordCode.AGENT_RUN_RECORD: "agent_run_record.p0.v1",
    P0RecordCode.GATE_DECISION_RECORD: "gate_decision_record.p0.v1",
    P0RecordCode.TOOL_CALL_RECORD: "tool_call_record.p0.v1",
    P0RecordCode.OBSERVATION_RECORD: "observation_record.p0.v1",
    P0RecordCode.CONTEXT_MANIFEST_RECORD: "context_manifest_record.p0.v1",
    P0RecordCode.TRACE_EVENT_RECORD: "trace_event_record.p0.v1",
}
_EXACT_RUN_PRIVATE_CODES = frozenset(
    code
    for code in _EXACT_RUN_VERSION_BY_CODE
    if code is not P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT
)
_EXACT_RUN_FAMILY_CAP = {
    P0RecordCode.CONVERSATION_RECORD: 1,
    P0RecordCode.MESSAGE_RECORD: 64,
    P0RecordCode.REQUEST_UNDERSTANDING_RECORD: 1,
    P0RecordCode.TASK_RECORD: 64,
    P0RecordCode.REQUEST_UNIT_RECORD: 64,
    P0RecordCode.CONVERSATION_TASK_LINK_RECORD: 64,
    P0RecordCode.RUN_TASK_LINK_RECORD: 64,
    P0RecordCode.INPUT_BINDING_RECORD: 64,
    P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT: 2,
    P0RecordCode.AGENT_RUN_RECORD: 1,
    P0RecordCode.GATE_DECISION_RECORD: 1,
    P0RecordCode.TOOL_CALL_RECORD: 1,
    P0RecordCode.OBSERVATION_RECORD: 1,
    P0RecordCode.CONTEXT_MANIFEST_RECORD: 2,
    P0RecordCode.TRACE_EVENT_RECORD: 64,
}
_EXACT_RUN_REFERENCE_CAP = 64
_EXACT_RUN_RAW_CHILD_CAP = {
    P0RecordCode.REQUEST_UNDERSTANDING_RECORD: 64,
    P0RecordCode.TASK_RECORD: 64,
    P0RecordCode.TOOL_CALL_RECORD: 1,
}
_EXACT_RUN_PROJECTION_CODES = (
    P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
    P0RecordCode.TASK_RECORD,
    P0RecordCode.REQUEST_UNIT_RECORD,
    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
    P0RecordCode.RUN_TASK_LINK_RECORD,
    P0RecordCode.AGENT_RUN_RECORD,
    P0RecordCode.TOOL_CALL_RECORD,
    P0RecordCode.CONTEXT_MANIFEST_RECORD,
    P0RecordCode.TRACE_EVENT_RECORD,
)
_EXACT_RUN_FORWARD_RELATIONS = frozenset(
    {
        (
            P0RecordCode.MESSAGE_RECORD,
            "conversation_id",
            P0RecordCode.CONVERSATION_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "run_id",
            P0RecordCode.AGENT_RUN_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "message_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "contextualization_resolved_source_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "contextualization_source_message_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "task_delta_input_source_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "input_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "accepted_delta_task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNIT_RECORD,
            "task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNIT_RECORD,
            "goal_source_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNIT_RECORD,
            "input_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.REQUEST_UNIT_RECORD,
            "observation_ref",
            P0RecordCode.OBSERVATION_RECORD,
        ),
        (
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            "conversation_id",
            P0RecordCode.CONVERSATION_RECORD,
        ),
        (
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            "task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.RUN_TASK_LINK_RECORD,
            "run_id",
            P0RecordCode.AGENT_RUN_RECORD,
        ),
        (
            P0RecordCode.RUN_TASK_LINK_RECORD,
            "task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.INPUT_BINDING_RECORD,
            "source_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.INPUT_BINDING_RECORD,
            "supersedes",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.INPUT_BINDING_RECORD,
            "request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
        ),
        (
            P0RecordCode.AGENT_RUN_RECORD,
            "conversation_id",
            P0RecordCode.CONVERSATION_RECORD,
        ),
        (
            P0RecordCode.GATE_DECISION_RECORD,
            "context_manifest_id",
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
        ),
        (
            P0RecordCode.GATE_DECISION_RECORD,
            "argument_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.TOOL_CALL_RECORD,
            "run_id",
            P0RecordCode.AGENT_RUN_RECORD,
        ),
        (
            P0RecordCode.TOOL_CALL_RECORD,
            "task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.TOOL_CALL_RECORD,
            "request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
        ),
        (
            P0RecordCode.TOOL_CALL_RECORD,
            "context_manifest_id",
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
        ),
        (
            P0RecordCode.TOOL_CALL_RECORD,
            "gate_decision_id",
            P0RecordCode.GATE_DECISION_RECORD,
        ),
        (
            P0RecordCode.TOOL_CALL_RECORD,
            "argument_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.OBSERVATION_RECORD,
            "supersedes",
            P0RecordCode.OBSERVATION_RECORD,
        ),
        (
            P0RecordCode.OBSERVATION_RECORD,
            "source_tool_call_id",
            P0RecordCode.TOOL_CALL_RECORD,
        ),
        (
            P0RecordCode.OBSERVATION_RECORD,
            "source_run_id",
            P0RecordCode.AGENT_RUN_RECORD,
        ),
        (
            P0RecordCode.OBSERVATION_RECORD,
            "source_task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.OBSERVATION_RECORD,
            "source_request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            "run_id",
            P0RecordCode.AGENT_RUN_RECORD,
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            "selected_message_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            "task_state_ref",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            "observation_ref",
            P0RecordCode.OBSERVATION_RECORD,
        ),
        (
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            "model_visible_toolset_hash",
            P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "run_id",
            P0RecordCode.AGENT_RUN_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "message_ref",
            P0RecordCode.MESSAGE_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "task_id",
            P0RecordCode.TASK_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "input_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "context_manifest_id",
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "model_visible_toolset_hash",
            P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "argument_binding_ref",
            P0RecordCode.INPUT_BINDING_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "tool_call_id",
            P0RecordCode.TOOL_CALL_RECORD,
        ),
        (
            P0RecordCode.TRACE_EVENT_RECORD,
            "observation_ref",
            P0RecordCode.OBSERVATION_RECORD,
        ),
        (
            P0RecordCode.TASK_RECORD,
            "request_unit_id",
            P0RecordCode.REQUEST_UNIT_RECORD,
        ),
    }
)
_EXACT_RUN_REVERSE_RELATIONS = {
    P0RecordCode.REQUEST_UNDERSTANDING_RECORD: (
        ("run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("accepted_delta_task_id", P0RecordCode.TASK_RECORD),
    ),
    P0RecordCode.REQUEST_UNIT_RECORD: (
        ("task_id", P0RecordCode.TASK_RECORD),
    ),
    P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
        ("task_id", P0RecordCode.TASK_RECORD),
    ),
    P0RecordCode.RUN_TASK_LINK_RECORD: (
        ("run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("task_id", P0RecordCode.TASK_RECORD),
    ),
    P0RecordCode.INPUT_BINDING_RECORD: (
        ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
    ),
    P0RecordCode.GATE_DECISION_RECORD: (
        ("context_manifest_id", P0RecordCode.CONTEXT_MANIFEST_RECORD),
        ("argument_binding_ref", P0RecordCode.INPUT_BINDING_RECORD),
    ),
    P0RecordCode.TOOL_CALL_RECORD: (
        ("run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("task_id", P0RecordCode.TASK_RECORD),
        ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
    ),
    P0RecordCode.OBSERVATION_RECORD: (
        ("source_tool_call_id", P0RecordCode.TOOL_CALL_RECORD),
        ("source_run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("source_task_id", P0RecordCode.TASK_RECORD),
        ("source_request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
    ),
    P0RecordCode.CONTEXT_MANIFEST_RECORD: (
        ("run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("task_state_ref", P0RecordCode.TASK_RECORD),
    ),
    P0RecordCode.TRACE_EVENT_RECORD: (
        ("run_id", P0RecordCode.AGENT_RUN_RECORD),
        ("task_id", P0RecordCode.TASK_RECORD),
        ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
        ("tool_call_id", P0RecordCode.TOOL_CALL_RECORD),
    ),
    P0RecordCode.TASK_RECORD: (
        ("request_unit_id", P0RecordCode.REQUEST_UNIT_RECORD),
    ),
}


class P0PersistenceSystemError(Exception):
    """Bounded database failure with no caller-controlled diagnostic."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("PERSISTENCE_SYSTEM_FAILURE")


class _FinalizeRunNotApplicable(Exception):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()


class _FinalizeRunProjectionConflict(Exception):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()


def _bounded_database_failures(
    operation: Callable[_Params, Awaitable[_ResultT]],
) -> Callable[_Params, Awaitable[_ResultT]]:
    @wraps(operation)
    async def bounded_operation(
        *args: _Params.args,
        **kwargs: _Params.kwargs,
    ) -> _ResultT:
        safe_failure: P0PersistenceSystemError | None = None
        try:
            result = await operation(*args, **kwargs)
        except SQLAlchemyError:
            safe_failure = P0PersistenceSystemError()
        else:
            return result
        raise safe_failure from None

    return bounded_operation


def _integrity(
    category: P0PersistenceIntegrityCategory,
) -> P0PersistenceIntegrityError:
    return P0PersistenceIntegrityError(category, uuid4())


def _json_identity(
    logical_identity: tuple[tuple[str, object], ...],
) -> list[list[object]]:
    return cast(
        list[list[object]],
        to_jsonable_python(logical_identity, serialize_unknown=True),
    )


def _canonical_identity_text(logical_identity: list[list[object]]) -> str:
    return json.dumps(
        logical_identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _enum_value(value: object) -> str | None:
    if isinstance(value, Enum):
        return str(value.value)
    return None


def _external_reference(
    relation: str,
    target_code: P0RecordCode,
    field_name: str,
    value: object,
) -> P0RecordReference:
    return P0RecordReference(
        relation=relation,
        target_record_code=target_code,
        target_logical_identity=(
            (
                field_name,
                cast(
                    str | int | float | bool | None,
                    to_jsonable_python(value, serialize_unknown=True),
                ),
            ),
        ),
    )


def _exact_run_key(
    record_code: P0RecordCode,
    logical_identity: list[list[object]],
) -> tuple[P0RecordCode, str]:
    return (
        record_code,
        _canonical_identity_text(logical_identity),
    )


def _exact_run_parse_envelope(
    raw: dict[str, Any],
) -> P0PersistenceEnvelope:
    parsed: P0PersistenceEnvelope | None = None
    validation_failed = False
    try:
        parsed = P0PersistenceEnvelope.model_validate_json(
            json.dumps(
                raw,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError, RecursionError):
        validation_failed = True
    if validation_failed or parsed is None:
        raise _integrity(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        ) from None
    return parsed


def _exact_run_normalized_references(
    session: Session,
    row: P0RecordModel,
) -> tuple[P0RecordReference, ...]:
    references = tuple(
        session.scalars(
            select(P0RecordReferenceModel)
            .where(
                P0RecordReferenceModel.source_record_code
                == row.record_code,
                P0RecordReferenceModel.source_logical_identity
                == row.logical_identity,
            )
            .order_by(
                P0RecordReferenceModel.ordinal,
                P0RecordReferenceModel.relation,
                P0RecordReferenceModel.target_record_code,
                P0RecordReferenceModel.target_logical_identity,
            )
            .limit(_EXACT_RUN_REFERENCE_CAP + 1)
        )
    )
    if len(references) > _EXACT_RUN_REFERENCE_CAP:
        raise _integrity(
            P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
        )
    if tuple(reference.ordinal for reference in references) != tuple(
        range(len(references))
    ):
        raise _integrity(
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
    normalized: tuple[P0RecordReference, ...] | None = None
    validation_failed = False
    try:
        normalized = tuple(
            P0RecordReference.model_validate_json(
                json.dumps(
                    {
                        "relation": reference.relation,
                        "target_record_code": reference.target_record_code,
                        "target_logical_identity": (
                            reference.target_logical_identity
                        ),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )
            for reference in references
        )
    except (TypeError, ValueError, ValidationError, RecursionError):
        validation_failed = True
    if validation_failed or normalized is None:
        raise _integrity(
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        ) from None
    return normalized


def _exact_run_raw_child_count(row: P0RecordModel) -> int | None:
    if not isinstance(row.envelope, dict):
        return None
    payload = row.envelope.get("payload")
    if not isinstance(payload, dict):
        return None
    children = payload.get("logical_children")
    if not isinstance(children, list):
        return None
    return len(children)


def _exact_run_reorder_json_like(
    raw: object,
    template: object,
) -> object:
    if isinstance(raw, dict) and isinstance(template, dict):
        result = {
            key: _exact_run_reorder_json_like(raw[key], template[key])
            for key in template
            if key in raw
        }
        result.update(
            (key, value)
            for key, value in raw.items()
            if key not in result
        )
        return result
    if isinstance(raw, list) and isinstance(template, list):
        return [
            _exact_run_reorder_json_like(
                value,
                template[index] if index < len(template) else None,
            )
            for index, value in enumerate(raw)
        ]
    return raw


def _exact_run_versioned_decode_input(
    row: P0RecordModel,
    record_code: P0RecordCode,
) -> dict[str, Any]:
    if record_code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD:
        return row.envelope
    raw = json.loads(
        json.dumps(
            row.envelope,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return row.envelope
    source_data = payload.get("data")
    child_payloads = payload.get("logical_children")
    if not isinstance(source_data, dict) or not isinstance(
        child_payloads,
        list,
    ):
        return row.envelope
    source: RequestUnderstandingRecordV2 | None = None
    children: tuple[AcceptedTaskDeltaV2, ...] | None = None
    validation_failed = False
    try:
        source = RequestUnderstandingRecordV2.model_validate_json(
            json.dumps(
                source_data,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
        children = tuple(
            AcceptedTaskDeltaV2.model_validate_json(
                json.dumps(
                    child["data"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )
            for child in child_payloads
            if isinstance(child, dict) and isinstance(child.get("data"), dict)
        )
        if len(children) != len(child_payloads):
            validation_failed = True
    except (TypeError, ValueError, ValidationError, RecursionError):
        validation_failed = True
    if validation_failed or source is None or children is None:
        return row.envelope
    payload["data"] = _exact_run_reorder_json_like(
        source_data,
        source.model_dump(mode="json"),
    )
    for child_payload, child in zip(child_payloads, children):
        child_payload["data"] = _exact_run_reorder_json_like(
            child_payload["data"],
            child.model_dump(mode="json"),
        )
    return raw


def _exact_run_projection_values(
    *,
    record_code: P0RecordCode,
    envelope: P0PersistenceEnvelope,
    decoded: DecodedP0PersistenceRecord,
    scope_owner_customer_id: str | None,
) -> dict[str, object]:
    record = decoded.source_record

    def uuid_projection(field_name: str) -> UUID | None:
        value = getattr(record, field_name, None)
        return value if type(value) is UUID else None

    lifecycle_status = _enum_value(getattr(record, "status", None))
    state_version = getattr(record, "state_version", None)
    attempt_count = getattr(record, "attempt_count", None)
    recovery_sort_at = (
        getattr(record, "started_at", None)
        if record_code is P0RecordCode.AGENT_RUN_RECORD
        else None
    )
    return {
        "record_code": record_code.value,
        "record_schema_version": _EXACT_RUN_VERSION_BY_CODE[record_code],
        "logical_identity": _json_identity(envelope.logical_identity),
        "direct_owner_customer_id": envelope.direct_owner_customer_id,
        "scope_owner_customer_id": scope_owner_customer_id,
        "conversation_id": uuid_projection("conversation_id"),
        "run_id": uuid_projection("run_id"),
        "task_id": uuid_projection("task_id"),
        "request_unit_id": uuid_projection("request_unit_id"),
        "lifecycle_status": lifecycle_status,
        "state_version": (
            state_version if type(state_version) is int else None
        ),
        "attempt_count": (
            attempt_count if type(attempt_count) is int else None
        ),
        "recovery_sort_at": (
            recovery_sort_at
            if isinstance(recovery_sort_at, datetime)
            else None
        ),
    }


def _exact_run_decode_spec(
    row: P0RecordModel,
) -> tuple[P0RecordCode, str]:
    record_code = _RECORD_CODE_BY_VALUE.get(row.record_code)
    if record_code is None:
        raise _integrity(
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
        )
    expected_version = _EXACT_RUN_VERSION_BY_CODE.get(record_code)
    if expected_version is None:
        raise _integrity(
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
    if row.record_schema_version != expected_version:
        raise _integrity(
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
        )
    raw_child_count = _exact_run_raw_child_count(row)
    raw_child_cap = _EXACT_RUN_RAW_CHILD_CAP.get(record_code)
    if (
        raw_child_count is not None
        and raw_child_cap is not None
        and raw_child_count > raw_child_cap
    ):
        raise _integrity(
            P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
        )
    return record_code, expected_version


def _exact_run_validate_decoded_row(
    session: Session,
    row: P0RecordModel,
    *,
    record_code: P0RecordCode,
    decoded: DecodedP0PersistenceRecord,
    trusted_owner_customer_id: str,
) -> tuple[
    P0PersistenceEnvelope,
    tuple[P0RecordReference, ...],
]:
    envelope = _exact_run_parse_envelope(row.envelope)
    references = _exact_run_normalized_references(session, row)
    expected_scope_owner = (
        trusted_owner_customer_id
        if record_code in _EXACT_RUN_PRIVATE_CODES
        else None
    )
    if (
        row.scope_owner_customer_id != expected_scope_owner
        or (
            envelope.direct_owner_customer_id is not None
            and envelope.direct_owner_customer_id
            != trusted_owner_customer_id
        )
    ):
        raise _integrity(
            P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
        )
    if references != envelope.record_references:
        raise _integrity(
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
    expected_projection = _exact_run_projection_values(
        record_code=record_code,
        envelope=envelope,
        decoded=decoded,
        scope_owner_customer_id=expected_scope_owner,
    )
    for field_name, expected_value in expected_projection.items():
        if getattr(row, field_name) != expected_value:
            if field_name in {
                "direct_owner_customer_id",
                "scope_owner_customer_id",
            }:
                category = (
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
            elif field_name == "logical_identity":
                category = P0PersistenceIntegrityCategory.IDENTITY_MISMATCH
            elif field_name == "record_schema_version":
                category = (
                    P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
                )
            else:
                category = (
                    P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
            raise _integrity(category)
    return envelope, references


class PostgresRecordAdapter:
    """Synchronous-SQLAlchemy implementation of the frozen async record Ports."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    @_bounded_database_failures
    async def load_exact_run_evidence_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> ExactRunEvidenceClosure | None:
        if type(owner_scope) is not TrustedOwnerScope:
            raise TypeError("owner_scope must be exact TrustedOwnerScope")
        if type(run_id) is not UUID:
            raise TypeError("run_id must be exact UUID")

        trusted_owner = owner_scope.customer_id
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL "
                        "REPEATABLE READ, READ ONLY"
                    )
                )
                roots = tuple(
                    session.scalars(
                        select(P0RecordModel)
                        .where(
                            P0RecordModel.record_code
                            == P0RecordCode.AGENT_RUN_RECORD.value,
                            P0RecordModel.run_id == run_id,
                            P0RecordModel.scope_owner_customer_id
                            == trusted_owner,
                        )
                        .order_by(P0RecordModel.record_id)
                        .limit(2)
                    )
                )
                if not roots:
                    return None
                if len(roots) != 1:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                    )

                root = roots[0]
                root_key = _exact_run_key(
                    P0RecordCode.AGENT_RUN_RECORD,
                    root.logical_identity,
                )
                selected: dict[
                    tuple[P0RecordCode, str],
                    P0RecordModel,
                ] = {root_key: root}
                references_by_key: dict[
                    tuple[P0RecordCode, str],
                    tuple[P0RecordReference, ...],
                ] = {}

                def rows_for_code(
                    record_code: P0RecordCode,
                ) -> tuple[P0RecordModel, ...]:
                    return tuple(
                        row
                        for (code, _identity), row in selected.items()
                        if code is record_code
                    )

                def add_identity(
                    record_code: P0RecordCode,
                    logical_identity: list[list[object]],
                ) -> bool:
                    if record_code not in _EXACT_RUN_VERSION_BY_CODE:
                        raise _integrity(
                            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                        )
                    key = _exact_run_key(record_code, logical_identity)
                    if key in selected:
                        return False
                    family_cap = _EXACT_RUN_FAMILY_CAP[record_code]
                    if len(rows_for_code(record_code)) >= family_cap:
                        raise _integrity(
                            P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                        )
                    statement = select(P0RecordModel).where(
                        P0RecordModel.record_code == record_code.value,
                        P0RecordModel.logical_identity == logical_identity,
                    )
                    if record_code in _EXACT_RUN_PRIVATE_CODES:
                        statement = statement.where(
                            P0RecordModel.scope_owner_customer_id
                            == trusted_owner
                        )
                    else:
                        statement = statement.where(
                            P0RecordModel.scope_owner_customer_id.is_(None)
                        )
                    candidates = tuple(
                        session.scalars(
                            statement
                            .order_by(P0RecordModel.record_id)
                            .limit(2)
                        )
                    )
                    if not candidates:
                        raise _integrity(
                            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                        )
                    if len(candidates) != 1:
                        raise _integrity(
                            P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                        )
                    selected[key] = candidates[0]
                    return True

                root_record_code, root_expected_version = (
                    _exact_run_decode_spec(root)
                )
                root_decoded = decode_persistence_record_versioned(
                    _exact_run_versioned_decode_input(
                        root,
                        root_record_code,
                    ),
                    expected_record_code=root_record_code,
                    expected_schema_version=root_expected_version,
                    correlation_ref=uuid4(),
                )
                _root_envelope, root_references = (
                    _exact_run_validate_decoded_row(
                        session,
                        root,
                        record_code=root_record_code,
                        decoded=root_decoded,
                        trusted_owner_customer_id=trusted_owner,
                    )
                )
                references_by_key[root_key] = root_references

                while True:
                    selected_count_before = len(selected)
                    anchor_identities = {
                        record_code: tuple(
                            row.logical_identity
                            for row in rows_for_code(record_code)
                        )
                        for record_code in _EXACT_RUN_FAMILY_CAP
                    }
                    for (
                        source_code,
                        reverse_edges,
                    ) in _EXACT_RUN_REVERSE_RELATIONS.items():
                        edge_filters = [
                            and_(
                                P0RecordReferenceModel.relation == relation,
                                P0RecordReferenceModel.target_record_code
                                == target_code.value,
                                P0RecordReferenceModel.target_logical_identity
                                == target_identity,
                            )
                            for relation, target_code in reverse_edges
                            for target_identity in anchor_identities[target_code]
                        ]
                        if not edge_filters:
                            continue
                        family_cap = _EXACT_RUN_FAMILY_CAP[source_code]
                        identities = tuple(
                            session.scalars(
                                select(
                                    P0RecordReferenceModel.source_logical_identity
                                )
                                .distinct()
                                .where(
                                    P0RecordReferenceModel.source_record_code
                                    == source_code.value,
                                    or_(*edge_filters),
                                )
                                .order_by(
                                    P0RecordReferenceModel.source_logical_identity
                                )
                                .limit(family_cap + 1)
                            )
                        )
                        if len(identities) > family_cap:
                            raise _integrity(
                                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                            )
                        for identity in identities:
                            add_identity(source_code, identity)

                    task_ids = tuple(
                        sorted(
                            {
                                row.task_id
                                for row in rows_for_code(
                                    P0RecordCode.TASK_RECORD
                                )
                                if type(row.task_id) is UUID
                            },
                            key=str,
                        )
                    )
                    request_unit_ids = tuple(
                        sorted(
                            {
                                row.request_unit_id
                                for row in rows_for_code(
                                    P0RecordCode.REQUEST_UNIT_RECORD
                                )
                                if type(row.request_unit_id) is UUID
                            },
                            key=str,
                        )
                    )
                    for record_code in _EXACT_RUN_PROJECTION_CODES:
                        projection_filters = [
                            P0RecordModel.run_id == run_id,
                        ]
                        if task_ids:
                            projection_filters.append(
                                P0RecordModel.task_id.in_(task_ids)
                            )
                        if request_unit_ids:
                            projection_filters.append(
                                P0RecordModel.request_unit_id.in_(
                                    request_unit_ids
                                )
                            )
                        family_cap = _EXACT_RUN_FAMILY_CAP[record_code]
                        identities = tuple(
                            session.scalars(
                                select(P0RecordModel.logical_identity)
                                .where(
                                    P0RecordModel.record_code
                                    == record_code.value,
                                    P0RecordModel.scope_owner_customer_id
                                    == trusted_owner,
                                    or_(*projection_filters),
                                )
                                .order_by(P0RecordModel.logical_identity)
                                .limit(family_cap + 1)
                            )
                        )
                        if len(identities) > family_cap:
                            raise _integrity(
                                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                            )
                        for identity in identities:
                            add_identity(record_code, identity)

                    for key, row in tuple(selected.items()):
                        source_code = key[0]
                        references = references_by_key.get(key)
                        if references is None:
                            references = _exact_run_normalized_references(
                                session,
                                row,
                            )
                            references_by_key[key] = references
                        for reference in references:
                            relation_key = (
                                source_code,
                                reference.relation,
                                reference.target_record_code,
                            )
                            if (
                                relation_key
                                not in _EXACT_RUN_FORWARD_RELATIONS
                            ):
                                raise _integrity(
                                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                                )
                            add_identity(
                                reference.target_record_code,
                                _json_identity(
                                    reference.target_logical_identity
                                ),
                            )

                    if len(selected) == selected_count_before:
                        break

                raw_child_totals = {
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD: 0,
                    P0RecordCode.TASK_RECORD: 0,
                    P0RecordCode.TOOL_CALL_RECORD: 0,
                }
                for record_code in raw_child_totals:
                    for row in rows_for_code(record_code):
                        count = _exact_run_raw_child_count(row)
                        if count is not None:
                            raw_child_totals[record_code] += count
                if (
                    raw_child_totals[
                        P0RecordCode.REQUEST_UNDERSTANDING_RECORD
                    ]
                    > 64
                    or raw_child_totals[P0RecordCode.TASK_RECORD] > 64
                    or raw_child_totals[P0RecordCode.TOOL_CALL_RECORD] > 1
                ):
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                    )

                decoded_by_code: dict[
                    P0RecordCode,
                    list[DecodedP0PersistenceRecord],
                ] = {
                    record_code: []
                    for record_code in _EXACT_RUN_FAMILY_CAP
                }
                for key, row in sorted(
                    selected.items(),
                    key=lambda item: (item[0][0].value, item[0][1]),
                ):
                    record_code, expected_version = _exact_run_decode_spec(
                        row
                    )
                    decoded = decode_persistence_record_versioned(
                        _exact_run_versioned_decode_input(row, record_code),
                        expected_record_code=record_code,
                        expected_schema_version=expected_version,
                        correlation_ref=uuid4(),
                    )
                    _envelope, references = (
                        _exact_run_validate_decoded_row(
                            session,
                            row,
                            record_code=record_code,
                            decoded=decoded,
                            trusted_owner_customer_id=trusted_owner,
                        )
                    )
                    initial_references = references_by_key.get(key)
                    if (
                        initial_references is not None
                        and references != initial_references
                    ):
                        raise _integrity(
                            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                        )
                    decoded_by_code[record_code].append(decoded)

                exact_source_types = {
                    P0RecordCode.CONVERSATION_RECORD: ConversationRecord,
                    P0RecordCode.MESSAGE_RECORD: MessageRecord,
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD: (
                        RequestUnderstandingRecordV2
                    ),
                    P0RecordCode.TASK_RECORD: TaskRecord,
                    P0RecordCode.REQUEST_UNIT_RECORD: RequestUnitRecord,
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
                        ConversationTaskLinkRecord
                    ),
                    P0RecordCode.RUN_TASK_LINK_RECORD: RunTaskLinkRecord,
                    P0RecordCode.INPUT_BINDING_RECORD: InputBinding,
                    P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT: (
                        ModelVisibleToolsetArtifact
                    ),
                    P0RecordCode.AGENT_RUN_RECORD: AgentRunRecord,
                    P0RecordCode.GATE_DECISION_RECORD: GateDecision,
                    P0RecordCode.TOOL_CALL_RECORD: ToolCallRecord,
                    P0RecordCode.OBSERVATION_RECORD: OrderObservation,
                    P0RecordCode.CONTEXT_MANIFEST_RECORD: ContextManifest,
                    P0RecordCode.TRACE_EVENT_RECORD: TraceEvent,
                }
                for record_code, decoded_records in decoded_by_code.items():
                    expected_type = exact_source_types[record_code]
                    if any(
                        type(decoded.source_record) is not expected_type
                        for decoded in decoded_records
                    ):
                        raise _integrity(
                            P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                        )

                conversations = decoded_by_code[
                    P0RecordCode.CONVERSATION_RECORD
                ]
                runs = decoded_by_code[P0RecordCode.AGENT_RUN_RECORD]
                if len(conversations) != 1 or len(runs) != 1:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                    )
                request_understanding_rows = decoded_by_code[
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD
                ]
                if len(request_understanding_rows) > 1:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                    )
                request_understanding = (
                    cast(
                        RequestUnderstandingRecordV2,
                        request_understanding_rows[0].source_record,
                    )
                    if request_understanding_rows
                    else None
                )
                accepted_task_deltas = tuple(
                    cast(AcceptedTaskDeltaV2, child)
                    for decoded in request_understanding_rows
                    for child in decoded.logical_children
                )
                task_state_transitions = tuple(
                    cast(TaskStateTransition, child)
                    for decoded in decoded_by_code[P0RecordCode.TASK_RECORD]
                    for child in decoded.logical_children
                )
                tool_attempts = tuple(
                    cast(ToolAttemptRecord, child)
                    for decoded in decoded_by_code[
                        P0RecordCode.TOOL_CALL_RECORD
                    ]
                    for child in decoded.logical_children
                )
                if (
                    any(
                        type(child) is not AcceptedTaskDeltaV2
                        for child in accepted_task_deltas
                    )
                    or any(
                        type(child) is not TaskStateTransition
                        for child in task_state_transitions
                    )
                    or any(
                        type(child) is not ToolAttemptRecord
                        for child in tool_attempts
                    )
                ):
                    raise _integrity(
                        P0PersistenceIntegrityCategory.CHILD_MISMATCH
                    )

                def sources(
                    record_code: P0RecordCode,
                ) -> tuple[BaseModel, ...]:
                    return tuple(
                        decoded.source_record
                        for decoded in decoded_by_code[record_code]
                    )

                messages = cast(
                    tuple[MessageRecord, ...],
                    sources(P0RecordCode.MESSAGE_RECORD),
                )
                if request_understanding is not None:
                    message_by_id = {
                        message.message_id: message for message in messages
                    }
                    provenance_candidates = (
                        *request_understanding.contextualization
                        .resolved_reference_candidates,
                        *(
                            candidate
                            for task_delta in (
                                request_understanding.task_delta_candidates
                            )
                            for candidate in task_delta.input_candidates
                        ),
                    )
                    for candidate in provenance_candidates:
                        message = message_by_id.get(candidate.source_ref)
                        if message is None:
                            raise _integrity(
                                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                            )
                        start = candidate.source_span_start
                        end = candidate.source_span_end_exclusive
                        if not 0 <= start < end <= len(message.content):
                            raise _integrity(
                                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                            )
                        digest = sha256(
                            message.content[start:end].encode("utf-8")
                        ).hexdigest()
                        if digest != candidate.source_quote_sha256:
                            raise _integrity(
                                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                            )

                closure: ExactRunEvidenceClosure | None = None
                closure_failed = False
                try:
                    closure = ExactRunEvidenceClosure(
                        conversation_record=cast(
                            ConversationRecord,
                            conversations[0].source_record,
                        ),
                        run_record=cast(
                            AgentRunRecord,
                            runs[0].source_record,
                        ),
                        message_records=messages,
                        request_understanding_record=request_understanding,
                        accepted_task_deltas=accepted_task_deltas,
                        input_binding_records=cast(
                            tuple[InputBinding, ...],
                            sources(P0RecordCode.INPUT_BINDING_RECORD),
                        ),
                        task_records=cast(
                            tuple[TaskRecord, ...],
                            sources(P0RecordCode.TASK_RECORD),
                        ),
                        task_state_transitions=task_state_transitions,
                        request_unit_records=cast(
                            tuple[RequestUnitRecord, ...],
                            sources(P0RecordCode.REQUEST_UNIT_RECORD),
                        ),
                        conversation_task_links=cast(
                            tuple[ConversationTaskLinkRecord, ...],
                            sources(
                                P0RecordCode.CONVERSATION_TASK_LINK_RECORD
                            ),
                        ),
                        run_task_links=cast(
                            tuple[RunTaskLinkRecord, ...],
                            sources(P0RecordCode.RUN_TASK_LINK_RECORD),
                        ),
                        gate_decisions=cast(
                            tuple[GateDecision, ...],
                            sources(P0RecordCode.GATE_DECISION_RECORD),
                        ),
                        tool_calls=cast(
                            tuple[ToolCallRecord, ...],
                            sources(P0RecordCode.TOOL_CALL_RECORD),
                        ),
                        tool_attempts=tool_attempts,
                        observation_records=cast(
                            tuple[OrderObservation, ...],
                            sources(P0RecordCode.OBSERVATION_RECORD),
                        ),
                        context_manifests=cast(
                            tuple[ContextManifest, ...],
                            sources(P0RecordCode.CONTEXT_MANIFEST_RECORD),
                        ),
                        model_visible_toolset_artifacts=cast(
                            tuple[ModelVisibleToolsetArtifact, ...],
                            sources(
                                P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT
                            ),
                        ),
                        trace_events=cast(
                            tuple[TraceEvent, ...],
                            sources(P0RecordCode.TRACE_EVENT_RECORD),
                        ),
                    )
                except (
                    TypeError,
                    ValueError,
                    ValidationError,
                    RecursionError,
                ):
                    closure_failed = True
                if closure_failed or closure is None:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                    ) from None
                return closure

    @staticmethod
    def _decode_envelope(
        envelope: P0PersistenceEnvelope | dict[str, Any],
        *,
        expected_code: P0RecordCode | None = None,
    ) -> DecodedP0PersistenceRecord:
        raw = (
            envelope
            if isinstance(envelope, dict)
            else envelope.model_dump(mode="json")
        )
        return decode_persistence_record(
            raw,
            expected_record_code=expected_code,
            correlation_ref=uuid4(),
        )

    @staticmethod
    def _envelope_json(envelope: P0PersistenceEnvelope) -> dict[str, Any]:
        return envelope.model_dump(mode="json")

    @staticmethod
    def _parse_envelope(raw: dict[str, Any]) -> P0PersistenceEnvelope:
        parsed: P0PersistenceEnvelope | None = None
        validation_failed = False
        try:
            parsed = P0PersistenceEnvelope.model_validate_json(
                json.dumps(
                    raw,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )
        except (TypeError, ValueError, ValidationError, RecursionError):
            validation_failed = True
        if validation_failed or parsed is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
            ) from None
        return parsed

    @staticmethod
    def _row_key(row: P0RecordModel) -> tuple[str, str]:
        return (
            row.record_code,
            _canonical_identity_text(row.logical_identity),
        )

    @staticmethod
    def _envelope_key(
        envelope: P0PersistenceEnvelope,
    ) -> tuple[str, str]:
        return (
            envelope.record_code.value,
            _canonical_identity_text(
                _json_identity(envelope.logical_identity)
            ),
        )

    @staticmethod
    def _projection_values(
        envelope: P0PersistenceEnvelope,
        *,
        scope_owner_customer_id: str | None,
    ) -> dict[str, object]:
        decoded = PostgresRecordAdapter._decode_envelope(
            envelope,
            expected_code=envelope.record_code,
        )
        record = decoded.source_record

        def uuid_projection(field_name: str) -> UUID | None:
            value = getattr(record, field_name, None)
            return value if isinstance(value, UUID) else None

        lifecycle_status = _enum_value(getattr(record, "status", None))
        state_version = getattr(record, "state_version", None)
        attempt_count = getattr(record, "attempt_count", None)
        recovery_sort_at = (
            getattr(record, "started_at", None)
            if envelope.record_code is P0RecordCode.AGENT_RUN_RECORD
            else None
        )
        return {
            "record_code": envelope.record_code.value,
            "record_schema_version": envelope.record_schema_version,
            "logical_identity": _json_identity(envelope.logical_identity),
            "direct_owner_customer_id": envelope.direct_owner_customer_id,
            "scope_owner_customer_id": scope_owner_customer_id,
            "conversation_id": uuid_projection("conversation_id"),
            "run_id": uuid_projection("run_id"),
            "task_id": uuid_projection("task_id"),
            "request_unit_id": uuid_projection("request_unit_id"),
            "lifecycle_status": lifecycle_status,
            "state_version": (
                state_version if isinstance(state_version, int) else None
            ),
            "attempt_count": (
                attempt_count if isinstance(attempt_count, int) else None
            ),
            "recovery_sort_at": (
                recovery_sort_at
                if isinstance(recovery_sort_at, datetime)
                else None
            ),
            "envelope": envelope.model_dump(mode="json"),
        }

    def _row_for_identity(
        self,
        session: Session,
        *,
        record_code: P0RecordCode,
        logical_identity: tuple[tuple[str, object], ...],
        for_update: bool = False,
        owner_scope: TrustedOwnerScope | None = None,
    ) -> P0RecordModel | None:
        statement = select(P0RecordModel).where(
            P0RecordModel.record_code == record_code.value,
            P0RecordModel.logical_identity == _json_identity(logical_identity),
        )
        if owner_scope is not None:
            statement = statement.where(
                P0RecordModel.scope_owner_customer_id
                == owner_scope.customer_id
            )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def _normalized_references(
        self,
        session: Session,
        row: P0RecordModel,
    ) -> tuple[P0RecordReference, ...]:
        references = tuple(
            session.scalars(
                select(P0RecordReferenceModel)
                .where(
                    P0RecordReferenceModel.source_record_code
                    == row.record_code,
                    P0RecordReferenceModel.source_logical_identity
                    == row.logical_identity,
                )
                .order_by(P0RecordReferenceModel.ordinal)
            )
        )
        if tuple(reference.ordinal for reference in references) != tuple(
            range(len(references))
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        normalized: tuple[P0RecordReference, ...] | None = None
        validation_failed = False
        try:
            normalized = tuple(
                P0RecordReference.model_validate_json(
                    json.dumps(
                        {
                            "relation": reference.relation,
                            "target_record_code": reference.target_record_code,
                            "target_logical_identity": (
                                reference.target_logical_identity
                            ),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    strict=True,
                )
                for reference in references
            )
        except (TypeError, ValueError, ValidationError, RecursionError):
            validation_failed = True
        if validation_failed or normalized is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            ) from None
        return normalized

    def _decode_row(
        self,
        session: Session,
        row: P0RecordModel,
    ) -> DecodedP0PersistenceRecord:
        record_code = _RECORD_CODE_BY_VALUE.get(row.record_code)
        if record_code is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
            )
        decoded = self._decode_envelope(
            row.envelope,
            expected_code=record_code,
        )
        envelope = self._parse_envelope(row.envelope)
        if (
            row.record_schema_version != envelope.record_schema_version
            or row.logical_identity != _json_identity(envelope.logical_identity)
            or row.direct_owner_customer_id
            != envelope.direct_owner_customer_id
            or self._normalized_references(session, row)
            != envelope.record_references
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        return decoded

    def _derive_owner_from_graph(
        self,
        session: Session,
        root: P0RecordModel,
        *,
        expected_owner: str | None = None,
        validate_physical_projections: bool = True,
    ) -> str | None:
        queue = [root]
        seen: set[tuple[str, str]] = set()
        owners: set[str] = set()
        visited: list[
            tuple[
                P0RecordModel,
                P0RecordCode,
                P0PersistenceEnvelope,
            ]
        ] = []
        while queue:
            row = queue.pop()
            key = self._row_key(row)
            if key in seen:
                continue
            seen.add(key)
            self._decode_row(session, row)
            envelope = self._parse_envelope(row.envelope)
            record_code = _RECORD_CODE_BY_VALUE.get(row.record_code)
            if record_code is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
                )
            visited.append((row, record_code, envelope))
            if envelope.direct_owner_customer_id is not None:
                owners.add(envelope.direct_owner_customer_id)
            for reference in envelope.record_references:
                statement = select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == reference.target_record_code.value,
                    P0RecordModel.logical_identity
                    == _json_identity(reference.target_logical_identity),
                )
                if expected_owner is not None:
                    if reference.target_record_code in _PRIVATE_RECORD_CODES:
                        statement = statement.where(
                            P0RecordModel.scope_owner_customer_id
                            == expected_owner
                        )
                    else:
                        statement = statement.where(
                            P0RecordModel.scope_owner_customer_id.is_(None),
                        )
                target = session.scalar(statement)
                if target is None:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                    )
                queue.append(target)
        if len(owners) > 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
            )
        derived_owner = next(iter(owners), None)
        if expected_owner is not None and derived_owner != expected_owner:
            raise _integrity(
                P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
            )
        if validate_physical_projections:
            for row, record_code, envelope in visited:
                projected_owner = (
                    derived_owner
                    if record_code in _PRIVATE_RECORD_CODES
                    else None
                )
                expected = self._projection_values(
                    envelope,
                    scope_owner_customer_id=projected_owner,
                )
                for field_name, value in expected.items():
                    if getattr(row, field_name) != value:
                        raise _integrity(
                            P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                            if field_name == "scope_owner_customer_id"
                            else P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                        )
        return derived_owner

    def _lock_rows_stably(
        self,
        session: Session,
        rows: Iterable[P0RecordModel],
    ) -> tuple[P0RecordModel, ...]:
        unique_rows = {
            row.record_id: row
            for row in rows
        }
        locked: list[P0RecordModel] = []
        for row in sorted(unique_rows.values(), key=self._row_key):
            locked_row = session.scalar(
                select(P0RecordModel)
                .where(P0RecordModel.record_id == row.record_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if locked_row is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            locked.append(locked_row)
        return tuple(locked)

    @staticmethod
    def _touch_recovery_anchor(
        session: Session,
        run_row: P0RecordModel,
    ) -> None:
        if run_row.record_code != P0RecordCode.AGENT_RUN_RECORD.value:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        result = session.execute(
            update(P0RecordModel)
            .where(
                P0RecordModel.record_id == run_row.record_id,
                P0RecordModel.envelope == run_row.envelope,
            )
            .values(stored_at=P0RecordModel.stored_at)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )

    def _validate_physical_projection(
        self,
        session: Session,
        row: P0RecordModel,
        *,
        expected_owner: str | None = None,
    ) -> DecodedP0PersistenceRecord:
        envelope = self._parse_envelope(row.envelope)
        derived_owner = self._derive_owner_from_graph(
            session,
            row,
            expected_owner=expected_owner,
        )
        expected = self._projection_values(
            envelope,
            scope_owner_customer_id=derived_owner,
        )
        for field_name, value in expected.items():
            if getattr(row, field_name) != value:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                    if field_name == "scope_owner_customer_id"
                    else P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
        return self._decode_row(session, row)

    def _persist_one_envelope(
        self,
        session: Session,
        envelope: P0PersistenceEnvelope,
    ) -> bool:
        values = self._projection_values(
            envelope,
            scope_owner_customer_id=envelope.direct_owner_customer_id,
        )
        inserted_record_id = session.scalar(
            postgresql_insert(P0RecordModel)
            .values(record_id=uuid4(), **values)
            .on_conflict_do_nothing(
                index_elements=(
                    P0RecordModel.record_code,
                    P0RecordModel.logical_identity,
                )
            )
            .returning(P0RecordModel.record_id)
        )
        return inserted_record_id is not None

    @staticmethod
    def _reference_model(
        envelope: P0PersistenceEnvelope,
        *,
        ordinal: int,
        reference: P0RecordReference,
    ) -> P0RecordReferenceModel:
        return P0RecordReferenceModel(
            reference_id=uuid4(),
            source_record_code=envelope.record_code.value,
            source_logical_identity=_json_identity(envelope.logical_identity),
            ordinal=ordinal,
            relation=reference.relation,
            target_record_code=reference.target_record_code.value,
            target_logical_identity=_json_identity(
                reference.target_logical_identity
            ),
        )

    def _persist_envelopes(
        self,
        session: Session,
        envelopes: Iterable[P0PersistenceEnvelope],
    ) -> tuple[bool, ...]:
        materialized = tuple(envelopes)
        ordered = tuple(
            sorted(
                enumerate(materialized),
                key=lambda item: self._envelope_key(item[1]),
            )
        )
        inserted_by_index = [False] * len(materialized)
        for index, envelope in ordered:
            inserted_by_index[index] = self._persist_one_envelope(
                session,
                envelope,
            )
        inserted = tuple(inserted_by_index)
        session.flush()
        rows_by_index: dict[int, P0RecordModel] = {}
        for index, envelope in ordered:
            was_inserted = inserted[index]
            row = self._row_for_identity(
                session,
                record_code=envelope.record_code,
                logical_identity=envelope.logical_identity,
                for_update=True,
            )
            if row is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.MISSING_RECORD_CODE
                )
            rows_by_index[index] = row
            if row.envelope != self._envelope_json(envelope):
                raise _integrity(
                    P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
            if was_inserted:
                session.add_all(
                    self._reference_model(
                        envelope,
                        ordinal=ordinal,
                        reference=reference,
                    )
                    for ordinal, reference in enumerate(
                        envelope.record_references
                    )
                )
            elif (
                self._normalized_references(session, row)
                != envelope.record_references
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
        session.flush()
        for index, envelope in ordered:
            row = rows_by_index[index]
            derived_owner = self._derive_owner_from_graph(
                session,
                row,
                validate_physical_projections=False,
            )
            if (
                envelope.record_code in _PRIVATE_RECORD_CODES
                and derived_owner is None
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
            if inserted[index]:
                row.scope_owner_customer_id = derived_owner
            elif row.scope_owner_customer_id != derived_owner:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
        session.flush()
        for index, _envelope in ordered:
            row = rows_by_index[index]
            self._validate_physical_projection(session, row)
        return inserted

    def _replace_row_envelope(
        self,
        session: Session,
        row: P0RecordModel,
        *,
        expected_record: BaseModel,
        expected_children: tuple[BaseModel, ...],
        next_envelope: P0PersistenceEnvelope,
    ) -> bool:
        decoded = self._validate_physical_projection(session, row)
        if (
            decoded.source_record != expected_record
            or decoded.logical_children != expected_children
        ):
            return False
        owner = row.scope_owner_customer_id
        next_values = self._projection_values(
            next_envelope,
            scope_owner_customer_id=owner,
        )
        result = session.execute(
            update(P0RecordModel)
            .where(
                P0RecordModel.record_id == row.record_id,
                P0RecordModel.envelope == row.envelope,
            )
            .values(**next_values)
        )
        if result.rowcount != 1:
            return False
        session.execute(
            delete(P0RecordReferenceModel).where(
                P0RecordReferenceModel.source_record_code == row.record_code,
                P0RecordReferenceModel.source_logical_identity
                == row.logical_identity,
            )
        )
        session.add_all(
            self._reference_model(
                next_envelope,
                ordinal=ordinal,
                reference=reference,
            )
            for ordinal, reference in enumerate(
                next_envelope.record_references
            )
        )
        session.flush()
        session.expire_all()
        next_row = self._row_for_identity(
            session,
            record_code=next_envelope.record_code,
            logical_identity=next_envelope.logical_identity,
            for_update=True,
        )
        if next_row is None:
            raise _integrity(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)
        self._validate_physical_projection(
            session,
            next_row,
            expected_owner=owner,
        )
        return True

    def _owner_scoped_row(
        self,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        record_code: P0RecordCode,
        logical_identity: tuple[tuple[str, object], ...],
    ) -> P0RecordModel | None:
        row = self._row_for_identity(
            session,
            record_code=record_code,
            logical_identity=logical_identity,
            owner_scope=owner_scope,
        )
        if row is None:
            return None
        self._validate_physical_projection(
            session,
            row,
            expected_owner=owner_scope.customer_id,
        )
        return row

    async def put_toolset_artifact(
        self,
        artifact: ModelVisibleToolsetArtifact,
    ) -> None:
        envelope = encode_persistence_record(
            P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
            artifact,
        )
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    async def get_toolset_artifact(
        self,
        model_visible_toolset_hash: str,
    ) -> ModelVisibleToolsetArtifact | None:
        with self.session_factory() as session:
            row = self._row_for_identity(
                session,
                record_code=P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
                logical_identity=(
                    ("model_visible_toolset_hash", model_visible_toolset_hash),
                ),
            )
            if row is None:
                return None
            decoded = self._validate_physical_projection(session, row)
            return cast(ModelVisibleToolsetArtifact, decoded.source_record)

    async def save_conversation(self, record: ConversationRecord) -> None:
        envelope = encode_persistence_record(
            P0RecordCode.CONVERSATION_RECORD,
            record,
        )
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    async def append_message(self, record: MessageRecord) -> None:
        envelope = encode_persistence_record(P0RecordCode.MESSAGE_RECORD, record)
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    async def load_conversation_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
    ) -> ConversationRecord | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            identity=(("conversation_id", conversation_id),),
            expected_type=ConversationRecord,
        )

    @_bounded_database_failures
    async def list_messages_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        limit: int,
    ) -> tuple[MessageRecord, ...]:
        with self.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.MESSAGE_RECORD.value,
                        P0RecordModel.scope_owner_customer_id
                        == owner_scope.customer_id,
                        P0RecordModel.conversation_id == conversation_id,
                    )
                    .order_by(P0RecordModel.stored_at, P0RecordModel.record_id)
                    .limit(limit)
                )
            )
            return tuple(
                cast(
                    MessageRecord,
                    self._validate_physical_projection(
                        session,
                        row,
                        expected_owner=owner_scope.customer_id,
                    ).source_record,
                )
                for row in rows
            )

    async def list_conversation_task_links_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
    ) -> tuple[ConversationTaskLinkRecord, ...]:
        return await self._list_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            filters=(P0RecordModel.conversation_id == conversation_id,),
            expected_type=ConversationTaskLinkRecord,
        )

    async def insert_run(
        self,
        command: CreateRunCommand,
    ) -> InsertOnlyWriteResult:
        envelope = encode_persistence_record(
            P0RecordCode.AGENT_RUN_RECORD,
            command.created_record,
        )
        with self.session_factory.begin() as session:
            inserted = self._persist_envelopes(session, (envelope,))[0]
        return (
            InsertOnlyWriteResult.INSERTED
            if inserted
            else InsertOnlyWriteResult.ALREADY_EXISTS
        )

    async def start_run_if_created(
        self,
        command: TransitionRunCommand,
    ) -> ConditionalWriteResult:
        with self.session_factory.begin() as session:
            row = self._row_for_identity(
                session,
                record_code=P0RecordCode.AGENT_RUN_RECORD,
                logical_identity=(
                    ("run_id", command.expected_active_record.run_id),
                ),
                for_update=True,
            )
            if row is None:
                return ConditionalWriteResult.NOT_APPLICABLE
            next_envelope = encode_persistence_record(
                P0RecordCode.AGENT_RUN_RECORD,
                command.next_record,
            )
            if not self._replace_row_envelope(
                session,
                row,
                expected_record=command.expected_active_record,
                expected_children=(),
                next_envelope=next_envelope,
            ):
                return ConditionalWriteResult.PROJECTION_CONFLICT
            return ConditionalWriteResult.APPLIED

    def _finalize_run_in_transaction(
        self,
        session: Session,
        command: FinalizeRunCommand,
    ) -> None:
        run_row = self._row_for_identity(
            session,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(
                ("run_id", command.expected_active_record.run_id),
            ),
        )
        if run_row is None:
            raise _FinalizeRunNotApplicable() from None

        link_closure_statement = (
            select(P0RecordModel)
            .where(
                P0RecordModel.record_code
                == P0RecordCode.RUN_TASK_LINK_RECORD.value,
                P0RecordModel.run_id
                == command.expected_active_record.run_id,
            )
            .limit(2)
        )
        prelock_link_rows = tuple(
            session.scalars(link_closure_statement)
        )
        if len(prelock_link_rows) != len(command.expected_active_links):
            raise _FinalizeRunProjectionConflict() from None

        run_row = self._lock_rows_stably(session, (run_row,))[0]
        run_decoded = self._validate_physical_projection(session, run_row)
        if run_decoded.source_record != command.expected_active_record:
            raise _FinalizeRunProjectionConflict() from None

        active_tool_call_rows = tuple(
            session.scalars(
                select(P0RecordModel)
                .where(
                    P0RecordModel.record_code
                    == P0RecordCode.TOOL_CALL_RECORD.value,
                    P0RecordModel.run_id
                    == command.expected_active_record.run_id,
                    P0RecordModel.lifecycle_status.in_(
                        (
                            ToolCallStatus.CREATED.value,
                            ToolCallStatus.RUNNING.value,
                        )
                    ),
                )
                .order_by(P0RecordModel.record_id)
                .limit(2)
            )
        )
        for active_tool_call_row in active_tool_call_rows:
            active_tool_call = self._validate_physical_projection(
                session,
                active_tool_call_row,
            ).source_record
            if type(active_tool_call) is not ToolCallRecord:
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            if (
                active_tool_call.run_id
                != command.expected_active_record.run_id
                or active_tool_call.status
                not in _ACTIVE_TOOL_CALL_STATUSES
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
        if active_tool_call_rows:
            raise _FinalizeRunProjectionConflict() from None

        link_rows = tuple(session.scalars(link_closure_statement))
        if len(link_rows) != len(command.expected_active_links):
            raise _FinalizeRunProjectionConflict() from None

        expected_task: TaskRecord | None = None
        task_row: P0RecordModel | None = None
        expected_unit: RequestUnitRecord | None = None
        unit_row: P0RecordModel | None = None
        if command.result_task_records:
            expected_task = (
                command.task_transition.expected_task_record
                if command.task_transition is not None
                else command.result_task_records[0]
            )
            task_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", expected_task.task_id),),
            )
            if task_row is None:
                raise _FinalizeRunProjectionConflict() from None
        if command.task_transition is not None:
            expected_unit = (
                command.task_transition.expected_request_unit_record
            )
            unit_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                logical_identity=(
                    ("request_unit_id", expected_unit.request_unit_id),
                ),
            )
            if unit_row is None:
                raise _FinalizeRunProjectionConflict() from None

        closure_rows_to_lock = [
            *link_rows,
            *((task_row,) if task_row is not None else ()),
            *((unit_row,) if unit_row is not None else ()),
        ]
        locked_by_id = {
            row.record_id: row
            for row in self._lock_rows_stably(
                session,
                closure_rows_to_lock,
            )
        }
        link_rows = tuple(
            locked_by_id[row.record_id]
            for row in link_rows
        )
        if task_row is not None:
            task_row = locked_by_id[task_row.record_id]
        if unit_row is not None:
            unit_row = locked_by_id[unit_row.record_id]

        link_by_task: dict[UUID, P0RecordModel] = {}
        for row in link_rows:
            decoded_link = self._validate_physical_projection(
                session,
                row,
            ).source_record
            if type(decoded_link) is not RunTaskLinkRecord:
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            link_by_task[decoded_link.task_id] = row
        expected_link_by_task = {
            link.task_id: link
            for link in command.expected_active_links
        }
        if set(link_by_task) != set(expected_link_by_task):
            raise _FinalizeRunProjectionConflict() from None
        for task_id, row in link_by_task.items():
            if (
                self._validate_physical_projection(
                    session,
                    row,
                ).source_record
                != expected_link_by_task[task_id]
            ):
                raise _FinalizeRunProjectionConflict() from None

        task_children: tuple[BaseModel, ...] = ()
        if expected_task is not None:
            assert task_row is not None
            task_decoded = self._validate_physical_projection(
                session,
                task_row,
            )
            if task_decoded.source_record != expected_task:
                raise _FinalizeRunProjectionConflict() from None
            task_children = cast(
                tuple[BaseModel, ...],
                task_decoded.logical_children,
            )
        if expected_unit is not None:
            assert unit_row is not None
            unit_decoded = self._validate_physical_projection(
                session,
                unit_row,
            )
            if (
                unit_decoded.source_record != expected_unit
                or unit_decoded.logical_children
            ):
                raise _FinalizeRunProjectionConflict() from None

        output_envelopes: list[P0PersistenceEnvelope] = []
        if command.assistant_message is not None:
            output_envelopes.append(
                encode_persistence_record(
                    P0RecordCode.MESSAGE_RECORD,
                    command.assistant_message,
                )
            )
        output_envelopes.extend(
            encode_persistence_record(
                P0RecordCode.TRACE_EVENT_RECORD,
                event,
            )
            for event in command.terminal_trace_events
        )
        for envelope in output_envelopes:
            if (
                self._row_for_identity(
                    session,
                    record_code=envelope.record_code,
                    logical_identity=envelope.logical_identity,
                )
                is not None
            ):
                raise _FinalizeRunProjectionConflict() from None

        if command.task_transition is not None:
            assert task_row is not None
            assert unit_row is not None
            next_task = encode_persistence_record(
                P0RecordCode.TASK_RECORD,
                command.task_transition.next_task_record,
                logical_children=(
                    *task_children,
                    command.task_transition.task_state_transition,
                ),
            )
            if not self._replace_row_envelope(
                session,
                task_row,
                expected_record=(
                    command.task_transition.expected_task_record
                ),
                expected_children=task_children,
                next_envelope=next_task,
            ):
                raise _FinalizeRunProjectionConflict() from None
            if not self._replace_row_envelope(
                session,
                unit_row,
                expected_record=(
                    command.task_transition.expected_request_unit_record
                ),
                expected_children=(),
                next_envelope=encode_persistence_record(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    command.task_transition.next_request_unit_record,
                ),
            ):
                raise _FinalizeRunProjectionConflict() from None

        if not self._replace_row_envelope(
            session,
            run_row,
            expected_record=command.expected_active_record,
            expected_children=(),
            next_envelope=encode_persistence_record(
                P0RecordCode.AGENT_RUN_RECORD,
                command.terminal_record,
            ),
        ):
            raise _FinalizeRunProjectionConflict() from None

        terminal_link_by_task = {
            link.task_id: link
            for link in command.terminal_links
        }
        for task_id in sorted(link_by_task, key=str):
            if not self._replace_row_envelope(
                session,
                link_by_task[task_id],
                expected_record=expected_link_by_task[task_id],
                expected_children=(),
                next_envelope=encode_persistence_record(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    terminal_link_by_task[task_id],
                ),
            ):
                raise _FinalizeRunProjectionConflict() from None

        if output_envelopes and not all(
            self._persist_envelopes(session, output_envelopes)
        ):
            raise _FinalizeRunProjectionConflict() from None

    @_bounded_database_failures
    async def finalize_run_if_active(
        self,
        command: FinalizeRunCommand,
    ) -> ConditionalWriteResult:
        try:
            with self.session_factory.begin() as session:
                self._finalize_run_in_transaction(session, command)
        except _FinalizeRunNotApplicable:
            return ConditionalWriteResult.NOT_APPLICABLE
        except _FinalizeRunProjectionConflict:
            return ConditionalWriteResult.PROJECTION_CONFLICT
        return ConditionalWriteResult.APPLIED

    async def create_initial_task_graph_if_current(
        self,
        command: CreateInitialTaskGraphCommand,
    ) -> ConditionalWriteResult:
        expected_rows = (
            (
                P0RecordCode.CONVERSATION_RECORD,
                ((
                    "conversation_id",
                    command.expected_conversation_record.conversation_id,
                ),),
                command.expected_conversation_record,
            ),
            (
                P0RecordCode.MESSAGE_RECORD,
                (("message_id", command.expected_message_record.message_id),),
                command.expected_message_record,
            ),
            (
                P0RecordCode.AGENT_RUN_RECORD,
                (("run_id", command.expected_active_run_record.run_id),),
                command.expected_active_run_record,
            ),
        )
        with self.session_factory.begin() as session:
            locked_expected_rows: dict[P0RecordCode, P0RecordModel] = {}
            for code, identity, expected in sorted(
                expected_rows,
                key=lambda item: (
                    item[0].value,
                    _canonical_identity_text(_json_identity(item[1])),
                ),
            ):
                row = self._row_for_identity(
                    session,
                    record_code=code,
                    logical_identity=identity,
                    for_update=True,
                    owner_scope=command.owner_scope,
                )
                if row is None:
                    return ConditionalWriteResult.NOT_APPLICABLE
                decoded = self._validate_physical_projection(
                    session,
                    row,
                    expected_owner=command.owner_scope.customer_id,
                )
                if decoded.source_record != expected:
                    return ConditionalWriteResult.PROJECTION_CONFLICT
                locked_expected_rows[code] = row

            request_unit = command.initial_request_unit.initial_record
            envelopes = (
                encode_persistence_record(
                    P0RecordCode.TASK_RECORD,
                    command.initial_task.initial_record,
                ),
                encode_persistence_record(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    request_unit,
                ),
                *(
                    encode_persistence_record(
                        P0RecordCode.INPUT_BINDING_RECORD,
                        binding.record,
                        external_references=(
                            _external_reference(
                                "request_unit_id",
                                P0RecordCode.REQUEST_UNIT_RECORD,
                                "request_unit_id",
                                binding.request_unit_id,
                            ),
                        ),
                    )
                    for binding in command.input_bindings
                ),
                encode_persistence_record(
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                    command.request_understanding.record,
                    logical_children=command.request_understanding.accepted_deltas,
                ),
                encode_persistence_record(
                    P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                    command.conversation_task_link,
                ),
                encode_persistence_record(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    command.run_task_link.active_record,
                ),
            )
            for envelope in sorted(envelopes, key=self._envelope_key):
                if self._row_for_identity(
                    session,
                    record_code=envelope.record_code,
                    logical_identity=envelope.logical_identity,
                    for_update=True,
                ) is not None:
                    return ConditionalWriteResult.PROJECTION_CONFLICT
            self._persist_envelopes(session, envelopes)
            self._touch_recovery_anchor(
                session,
                locked_expected_rows[P0RecordCode.AGENT_RUN_RECORD],
            )
            return ConditionalWriteResult.APPLIED

    async def apply_task_transition_if_current(
        self,
        command: ApplyTaskTransitionCommand,
    ) -> ConditionalWriteResult:
        with self.session_factory.begin() as session:
            rows: dict[P0RecordCode, P0RecordModel | None] = {}
            identities = (
                (
                    P0RecordCode.TASK_RECORD,
                    (("task_id", command.expected_task_record.task_id),),
                ),
                (
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    (
                        (
                            "request_unit_id",
                            command.expected_request_unit_record.request_unit_id,
                        ),
                    ),
                ),
            )
            for code, identity in sorted(
                identities,
                key=lambda item: (
                    item[0].value,
                    _canonical_identity_text(_json_identity(item[1])),
                ),
            ):
                rows[code] = self._row_for_identity(
                    session,
                    record_code=code,
                    logical_identity=identity,
                    for_update=True,
                )
            task_row = rows[P0RecordCode.TASK_RECORD]
            unit_row = rows[P0RecordCode.REQUEST_UNIT_RECORD]
            if task_row is None or unit_row is None:
                return ConditionalWriteResult.NOT_APPLICABLE
            task_decoded = self._validate_physical_projection(session, task_row)
            unit_decoded = self._validate_physical_projection(session, unit_row)
            if (
                task_decoded.source_record != command.expected_task_record
                or unit_decoded.source_record
                != command.expected_request_unit_record
            ):
                return ConditionalWriteResult.PROJECTION_CONFLICT
            next_task = encode_persistence_record(
                P0RecordCode.TASK_RECORD,
                command.next_task_record,
                logical_children=(
                    *task_decoded.logical_children,
                    command.task_state_transition,
                ),
            )
            next_unit = encode_persistence_record(
                P0RecordCode.REQUEST_UNIT_RECORD,
                command.next_request_unit_record,
            )
            if not self._replace_row_envelope(
                session,
                task_row,
                expected_record=command.expected_task_record,
                expected_children=task_decoded.logical_children,
                next_envelope=next_task,
            ):
                return ConditionalWriteResult.PROJECTION_CONFLICT
            if not self._replace_row_envelope(
                session,
                unit_row,
                expected_record=command.expected_request_unit_record,
                expected_children=(),
                next_envelope=next_unit,
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
            return ConditionalWriteResult.APPLIED

    async def save_context_manifest(self, record: ContextManifest) -> None:
        envelope = encode_persistence_record(
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
            record,
        )
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    async def save_gate_decision(self, record: GateDecision) -> None:
        envelope = encode_persistence_record(
            P0RecordCode.GATE_DECISION_RECORD,
            record,
        )
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    async def insert_tool_call(
        self,
        command: CreateToolCallCommand,
    ) -> InsertOnlyWriteResult:
        envelope = encode_persistence_record(
            P0RecordCode.TOOL_CALL_RECORD,
            command.created_record,
        )
        with self.session_factory.begin() as session:
            run_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.AGENT_RUN_RECORD,
                logical_identity=(
                    ("run_id", command.created_record.run_id),
                ),
                for_update=True,
            )
            if run_row is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            decoded_run = self._validate_physical_projection(
                session,
                run_row,
            ).source_record
            if (
                type(decoded_run) is not AgentRunRecord
                or decoded_run.run_id != command.created_record.run_id
                or decoded_run.status is not AgentRunStatus.RUNNING
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            inserted = self._persist_envelopes(session, (envelope,))[0]
            if inserted:
                self._touch_recovery_anchor(session, run_row)
        return (
            InsertOnlyWriteResult.INSERTED
            if inserted
            else InsertOnlyWriteResult.ALREADY_EXISTS
        )

    async def start_tool_call_if_created(
        self,
        command: DispatchToolCallCommand,
    ) -> ToolDispatchFenceWriteResult:
        if command.expected_created_record.effect is ToolEffect.ACTION:
            return ToolDispatchFenceWriteResult.ACTION_LEDGER_REQUIRED
        with self.session_factory.begin() as session:
            row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TOOL_CALL_RECORD,
                logical_identity=(
                    (
                        "tool_call_id",
                        command.expected_created_record.tool_call_id,
                    ),
                ),
                for_update=True,
            )
            if row is None:
                return ToolDispatchFenceWriteResult.NOT_APPLICABLE
            if not self._replace_row_envelope(
                session,
                row,
                expected_record=command.expected_created_record,
                expected_children=(),
                next_envelope=encode_persistence_record(
                    P0RecordCode.TOOL_CALL_RECORD,
                    command.running_record,
                    logical_children=(command.started_attempt,),
                ),
            ):
                return ToolDispatchFenceWriteResult.STATUS_CONFLICT
            return ToolDispatchFenceWriteResult.APPLIED

    async def finalize_tool_call_attempt_if_running(
        self,
        command: FinalizeToolCallCommand,
    ) -> ConditionalWriteResult:
        with self.session_factory.begin() as session:
            row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TOOL_CALL_RECORD,
                logical_identity=(
                    (
                        "tool_call_id",
                        command.expected_running_record.tool_call_id,
                    ),
                ),
                for_update=True,
            )
            if row is None:
                return ConditionalWriteResult.NOT_APPLICABLE
            if not self._replace_row_envelope(
                session,
                row,
                expected_record=command.expected_running_record,
                expected_children=(command.expected_started_attempt,),
                next_envelope=encode_persistence_record(
                    P0RecordCode.TOOL_CALL_RECORD,
                    command.terminal_record,
                    logical_children=(command.finalized_attempt,),
                ),
            ):
                return ConditionalWriteResult.PROJECTION_CONFLICT
            return ConditionalWriteResult.APPLIED

    async def save_observation(
        self,
        command: SaveObservationCommand,
    ) -> ObservationWriteResult:
        source = command.source_tool_call_record
        references = (
            _external_reference(
                "source_tool_call_id",
                P0RecordCode.TOOL_CALL_RECORD,
                "tool_call_id",
                source.tool_call_id,
            ),
            _external_reference(
                "source_run_id",
                P0RecordCode.AGENT_RUN_RECORD,
                "run_id",
                source.run_id,
            ),
            _external_reference(
                "source_task_id",
                P0RecordCode.TASK_RECORD,
                "task_id",
                source.task_id,
            ),
            _external_reference(
                "source_request_unit_id",
                P0RecordCode.REQUEST_UNIT_RECORD,
                "request_unit_id",
                source.request_unit_id,
            ),
        )
        envelope = encode_persistence_record(
            P0RecordCode.OBSERVATION_RECORD,
            command.observation_record,
            external_references=references,
        )
        with self.session_factory.begin() as session:
            source_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TOOL_CALL_RECORD,
                logical_identity=(("tool_call_id", source.tool_call_id),),
                for_update=True,
                owner_scope=command.owner_scope,
            )
            if source_row is None:
                return ObservationWriteResult.SOURCE_PROJECTION_CONFLICT
            decoded = self._validate_physical_projection(
                session,
                source_row,
                expected_owner=command.owner_scope.customer_id,
            )
            if decoded.source_record != source:
                return ObservationWriteResult.SOURCE_PROJECTION_CONFLICT
            inserted = self._persist_envelopes(session, (envelope,))[0]
            return (
                ObservationWriteResult.INSERTED
                if inserted
                else ObservationWriteResult.ALREADY_APPLIED
            )

    async def append_trace_event(self, record: TraceEvent) -> None:
        envelope = encode_persistence_record(
            P0RecordCode.TRACE_EVENT_RECORD,
            record,
        )
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    @_bounded_database_failures
    async def _load_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        record_code: P0RecordCode,
        identity: tuple[tuple[str, object], ...],
        expected_type: type[_RecordT],
    ) -> _RecordT | None:
        with self.session_factory() as session:
            row = self._owner_scoped_row(
                session,
                owner_scope=owner_scope,
                record_code=record_code,
                logical_identity=identity,
            )
            if row is None:
                return None
            record = self._decode_row(session, row).source_record
            if type(record) is not expected_type:
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            return cast(_RecordT, record)

    @_bounded_database_failures
    async def _list_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        record_code: P0RecordCode,
        filters: tuple[object, ...],
        expected_type: type[_RecordT],
    ) -> tuple[_RecordT, ...]:
        with self.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code == record_code.value,
                        P0RecordModel.scope_owner_customer_id
                        == owner_scope.customer_id,
                        *filters,
                    )
                    .order_by(P0RecordModel.stored_at, P0RecordModel.record_id)
                )
            )
            records: list[_RecordT] = []
            for row in rows:
                record = self._validate_physical_projection(
                    session,
                    row,
                    expected_owner=owner_scope.customer_id,
                ).source_record
                if type(record) is not expected_type:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                    )
                records.append(cast(_RecordT, record))
            return tuple(records)

    async def load_run_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> AgentRunRecord | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            identity=(("run_id", run_id),),
            expected_type=AgentRunRecord,
        )

    async def load_task_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
    ) -> TaskRecord | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.TASK_RECORD,
            identity=(("task_id", task_id),),
            expected_type=TaskRecord,
        )

    async def load_request_unit_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        request_unit_id: UUID,
    ) -> RequestUnitRecord | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            identity=(("request_unit_id", request_unit_id),),
            expected_type=RequestUnitRecord,
        )

    async def load_request_understanding_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> RequestUnderstandingRecord | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            identity=(("run_id", run_id),),
            expected_type=RequestUnderstandingRecord,
        )

    @_bounded_database_failures
    async def load_accepted_task_delta_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        accepted_delta_id: UUID,
    ) -> AcceptedTaskDelta | None:
        with self.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel).where(
                        P0RecordModel.record_code
                        == P0RecordCode.REQUEST_UNDERSTANDING_RECORD.value,
                        P0RecordModel.scope_owner_customer_id
                        == owner_scope.customer_id,
                    )
                )
            )
            found: list[AcceptedTaskDelta] = []
            for row in rows:
                decoded = self._validate_physical_projection(
                    session,
                    row,
                    expected_owner=owner_scope.customer_id,
                )
                found.extend(
                    child
                    for child in decoded.logical_children
                    if isinstance(child, AcceptedTaskDelta)
                    and child.accepted_delta_id == accepted_delta_id
                )
            if len(found) > 1:
                raise _integrity(
                    P0PersistenceIntegrityCategory.CHILD_MISMATCH
                )
            return found[0] if found else None

    async def load_input_binding_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        binding_id: UUID,
    ) -> InputBinding | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.INPUT_BINDING_RECORD,
            identity=(("binding_id", binding_id),),
            expected_type=InputBinding,
        )

    async def load_context_manifest_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        context_manifest_id: UUID,
    ) -> ContextManifest | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.CONTEXT_MANIFEST_RECORD,
            identity=(("context_manifest_id", context_manifest_id),),
            expected_type=ContextManifest,
        )

    async def load_gate_decision_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        gate_decision_id: UUID,
    ) -> GateDecision | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.GATE_DECISION_RECORD,
            identity=(("gate_decision_id", gate_decision_id),),
            expected_type=GateDecision,
        )

    async def load_tool_call_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        tool_call_id: UUID,
    ) -> ToolCallRecord | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.TOOL_CALL_RECORD,
            identity=(("tool_call_id", tool_call_id),),
            expected_type=ToolCallRecord,
        )

    async def load_observation_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        observation_id: UUID,
    ) -> OrderObservation | None:
        return await self._load_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.OBSERVATION_RECORD,
            identity=(("observation_id", observation_id),),
            expected_type=OrderObservation,
        )

    async def list_run_task_links_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> tuple[RunTaskLinkRecord, ...]:
        return await self._list_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            filters=(P0RecordModel.run_id == run_id,),
            expected_type=RunTaskLinkRecord,
        )

    @_bounded_database_failures
    async def list_trace_events_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> tuple[TraceEvent, ...]:
        with self.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value,
                        P0RecordModel.scope_owner_customer_id
                        == owner_scope.customer_id,
                        P0RecordModel.run_id == run_id,
                    )
                    .order_by(
                        P0RecordModel.stored_at,
                        P0RecordModel.record_id,
                    )
                )
            )
            physical_history: list[tuple[datetime, TraceEvent]] = []
            for row in rows:
                record = self._validate_physical_projection(
                    session,
                    row,
                    expected_owner=owner_scope.customer_id,
                ).source_record
                if type(record) is not TraceEvent:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                    )
                physical_history.append(
                    (row.stored_at, cast(TraceEvent, record))
                )

        ordered: list[TraceEvent] = []
        group_start = 0
        while group_start < len(physical_history):
            stored_at = physical_history[group_start][0]
            group_end = group_start + 1
            while (
                group_end < len(physical_history)
                and physical_history[group_end][0] == stored_at
            ):
                group_end += 1
            group = tuple(
                event
                for _, event in physical_history[group_start:group_end]
            )
            event_by_type = {
                event.event_type: event
                for event in group
            }
            is_normal_terminal_tie = (
                len(group) == 2
                and set(event_by_type)
                == _NORMAL_TERMINAL_TRACE_EVENT_TYPES
                and event_by_type[
                    TraceEventType.TASK_STATE_CHANGED
                ].occurred_at
                <= event_by_type[TraceEventType.RUN_STOPPED].occurred_at
                and event_by_type[
                    TraceEventType.RUN_STOPPED
                ].stop_reason
                is not StopReason.PROCESS_RESTART_DETECTED
            )
            if is_normal_terminal_tie:
                ordered.extend(
                    (
                        event_by_type[TraceEventType.TASK_STATE_CHANGED],
                        event_by_type[TraceEventType.RUN_STOPPED],
                    )
                )
            else:
                ordered.extend(group)
            group_start = group_end
        return tuple(ordered)

    async def append_eval_result(
        self,
        record: EvalResultRecord,
    ) -> InsertOnlyWriteResult:
        envelope = encode_persistence_record(
            P0RecordCode.EVAL_RESULT_RECORD,
            record,
        )
        with self.session_factory.begin() as session:
            inserted = self._persist_envelopes(session, (envelope,))[0]
        return (
            InsertOnlyWriteResult.INSERTED
            if inserted
            else InsertOnlyWriteResult.ALREADY_EXISTS
        )

    async def load_eval_result(
        self,
        *,
        eval_run_id: UUID,
        case_id: str,
        lane: str,
        attempt: int,
    ) -> EvalResultRecord | None:
        with self.session_factory() as session:
            row = self._row_for_identity(
                session,
                record_code=P0RecordCode.EVAL_RESULT_RECORD,
                logical_identity=(
                    ("eval_run_id", eval_run_id),
                    ("case_id", case_id),
                    ("lane", lane),
                    ("attempt", attempt),
                ),
            )
            if row is None:
                return None
            return cast(
                EvalResultRecord,
                self._validate_physical_projection(session, row).source_record,
            )

    async def list_eval_results(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalResultRecord, ...]:
        with self.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.EVAL_RESULT_RECORD.value,
                        P0RecordModel.envelope["payload"]["data"][
                            "eval_run_id"
                        ].astext
                        == str(eval_run_id),
                    )
                    .order_by(P0RecordModel.stored_at, P0RecordModel.record_id)
                )
            )
            return tuple(
                cast(
                    EvalResultRecord,
                    self._validate_physical_projection(
                        session,
                        row,
                    ).source_record,
                )
                for row in rows
            )

    async def append_eval_execution_failure(
        self,
        record: EvalExecutionFailureRecord,
    ) -> None:
        envelope = encode_persistence_record(
            P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD,
            record,
        )
        with self.session_factory.begin() as session:
            self._persist_envelopes(session, (envelope,))

    async def list_eval_execution_failures(
        self,
        *,
        eval_run_id: UUID,
    ) -> tuple[EvalExecutionFailureRecord, ...]:
        with self.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD.value,
                        P0RecordModel.envelope["payload"]["data"][
                            "eval_run_id"
                        ].astext
                        == str(eval_run_id),
                    )
                    .order_by(P0RecordModel.stored_at, P0RecordModel.record_id)
                )
            )
            return tuple(
                cast(
                    EvalExecutionFailureRecord,
                    self._validate_physical_projection(
                        session,
                        row,
                    ).source_record,
                )
                for row in rows
            )
