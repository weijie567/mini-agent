from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from functools import wraps
from hashlib import sha256
from types import MappingProxyType
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
    encode_persistence_record_versioned,
)
from mini_agent.application.records import (
    AcceptedOrderSearchQueryBindingReadClosure,
    AcceptedOrdinalBindingReadClosure,
    AppendInitialToolAttemptV2Command,
    AppendRecoveredToolAttemptV2Command,
    AppendToolAttemptV2Command,
    ApplyContinuationInputBindingV2Command,
    ApplyOrderCandidateSelectionV2Command,
    ApplyOrderSearchOutcomeV2Command,
    ApplyTaskTransitionCommand,
    AgentRunResult,
    ConditionalWriteResult,
    ContinuationInputBindingReadClosure,
    ConversationRecord,
    ConversationTaskLinkRecord,
    CreateCycle2InitialTaskGraphCommand,
    CreateCycle2RunRootCommand,
    CreateInitialTaskGraphV2Command,
    CreateRunCommand,
    CreateToolCallCommand,
    CreateToolCallV2Command,
    Cycle2DispatchFenceWriteResult,
    Cycle2CurrentSessionTaskClosure,
    Cycle2ExactRunEvidenceClosure,
    Cycle2ReadDispatchGrant,
    Cycle2RunBudgetPolicyEvidence,
    Cycle2WriteResult,
    DispatchToolCallCommand,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    ExactRunEvidenceClosure,
    FinalizeBudgetExhaustedToolRecoveryV2Command,
    FinalizeCreatedToolRecoveryV2Command,
    FinalizeRunCommand,
    FinalizeCycle2RunCommand,
    FinalizeStateInvalidatedToolRecoveryV2Command,
    FinalizeSupersededRunV2Command,
    FinalizeToolCallCommand,
    FinalizeToolAttemptV2Command,
    FinalizeUnfinishedToolRecoveryV2Command,
    InsertOnlyWriteResult,
    MessageRecord,
    MessageDirection,
    ObservationWriteResult,
    OrderCandidateSelectionReadClosure,
    OrderSearchCurrentReadClosure,
    RunTaskLinkRecord,
    RunTaskLinkRecordV2,
    SaveOrderObservationV2Command,
    SaveShipmentAssessmentV2Command,
    SaveShipmentObservationV2Command,
    SaveObservationCommand,
    SaveRequestUnderstandingV2NoTaskCommand,
    ToolDispatchFenceWriteResult,
    ToolRetryRecoveryDecisionRecordV2,
    ToolRetryRecoveryReadClosureV2,
    TransitionRunCommand,
    TrustedOwnerScope,
    InitialToolCallV2ReadClosure,
    ShipmentAssessmentReadClosure,
    ShipmentNotReceivedClaimReadClosure,
    StartCycle2RunCommand,
    SupersededRunInvalidationKind,
    SupersededRunReadClosure,
)
from mini_agent.core.memory import (
    ContextManifest,
    OrderObservation,
    SearchOrdersObservation,
    ShipmentObservation,
)
from mini_agent.core.shipment import ShipmentAssessment
from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2,
    InputBinding,
    InputBindingV2,
    OrderCandidateAutoTargetRecord,
    OrderCandidateSelectionRecord,
    OrderCandidateSelectionRequest,
    OrderCandidateSetRecord,
    RequestUnderstandingRecordV2,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
)
from mini_agent.core.tool_system import (
    GateDecision,
    GateDecisionV2,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolAttemptRecordV2,
    ToolCallRecord,
    ToolCallRecordV2,
    ToolCallStatus,
    ToolEffect,
)
from mini_agent.core.control_gateway import (
    Cycle2TargetObservationFacts,
    Cycle2VerifiedOrderTargetFacts,
)
from mini_agent.core.trace import (
    AgentRunRecord,
    AgentRunRecordV2,
    AgentRunStatus,
    AgentRunStatusV2,
    StopReason,
    TraceEvent,
    TraceEventV2,
    TraceEventType,
)
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
    P0RecordStateHistoryModel,
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
        P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
        P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
        P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
        P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
        P0RecordCode.SHIPMENT_ASSESSMENT_RECORD,
    }
)
_CYCLE2_VERSION_BY_CODE = MappingProxyType(
    {
        P0RecordCode.CONVERSATION_RECORD: "conversation_record.p0.v1",
        P0RecordCode.MESSAGE_RECORD: "message_record.p0.v1",
        P0RecordCode.TASK_RECORD: "task_record.p0.v1",
        P0RecordCode.REQUEST_UNIT_RECORD: "request_unit_record.p0.v1",
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
            "conversation_task_link_record.p0.v1"
        ),
        P0RecordCode.CONTEXT_MANIFEST_RECORD: "context_manifest_record.p0.v1",
        P0RecordCode.OBSERVATION_RECORD: "observation_record.p0.v1",
        P0RecordCode.INPUT_BINDING_RECORD: "input_binding_record.p0.v2",
        P0RecordCode.GATE_DECISION_RECORD: "gate_decision_record.p0.v2",
        P0RecordCode.TOOL_CALL_RECORD: "tool_call_record.p0.v2",
        P0RecordCode.AGENT_RUN_RECORD: "agent_run_record.p0.v2",
        P0RecordCode.RUN_TASK_LINK_RECORD: "run_task_link_record.p0.v2",
        P0RecordCode.TRACE_EVENT_RECORD: "trace_event_record.p0.v2",
        P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD: (
            "order_search_observation_record.p0.v1"
        ),
        P0RecordCode.ORDER_CANDIDATE_SET_RECORD: (
            "order_candidate_set_record.p0.v1"
        ),
        P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD: (
            "order_candidate_selection_record.p0.v1"
        ),
        P0RecordCode.SHIPMENT_OBSERVATION_RECORD: (
            "shipment_observation_record.p0.v1"
        ),
        P0RecordCode.SHIPMENT_ASSESSMENT_RECORD: (
            "shipment_assessment_record.p0.v1"
        ),
    }
)
_CYCLE2_INPUT_BINDING_VERSIONS = frozenset(
    {"input_binding_record.p0.v1", "input_binding_record.p0.v2"}
)
_PHYSICAL_OBSERVATION_RECORD_CODES = (
    P0RecordCode.OBSERVATION_RECORD,
    P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
    P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
)
_CYCLE2_MODEL_BY_PAIR = MappingProxyType(
    {
        (P0RecordCode.INPUT_BINDING_RECORD, "input_binding_record.p0.v2"): InputBindingV2,
        (P0RecordCode.GATE_DECISION_RECORD, "gate_decision_record.p0.v2"): GateDecisionV2,
        (P0RecordCode.TOOL_CALL_RECORD, "tool_call_record.p0.v2"): ToolCallRecordV2,
        (P0RecordCode.AGENT_RUN_RECORD, "agent_run_record.p0.v2"): AgentRunRecordV2,
        (P0RecordCode.RUN_TASK_LINK_RECORD, "run_task_link_record.p0.v2"): RunTaskLinkRecordV2,
        (P0RecordCode.TRACE_EVENT_RECORD, "trace_event_record.p0.v2"): TraceEventV2,
        (P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD, "order_search_observation_record.p0.v1"): SearchOrdersObservation,
        (P0RecordCode.ORDER_CANDIDATE_SET_RECORD, "order_candidate_set_record.p0.v1"): OrderCandidateSetRecord,
        (P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD, "order_candidate_selection_record.p0.v1"): OrderCandidateSelectionRecord,
        (P0RecordCode.SHIPMENT_OBSERVATION_RECORD, "shipment_observation_record.p0.v1"): ShipmentObservation,
        (P0RecordCode.SHIPMENT_ASSESSMENT_RECORD, "shipment_assessment_record.p0.v1"): ShipmentAssessment,
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
_RU_V2_WRITE_VERSION_BY_CODE = MappingProxyType(
    {
        P0RecordCode.CONVERSATION_RECORD: "conversation_record.p0.v1",
        P0RecordCode.MESSAGE_RECORD: "message_record.p0.v1",
        P0RecordCode.AGENT_RUN_RECORD: "agent_run_record.p0.v1",
        P0RecordCode.REQUEST_UNDERSTANDING_RECORD: (
            "request_understanding_record.p0.v2"
        ),
        P0RecordCode.TASK_RECORD: "task_record.p0.v1",
        P0RecordCode.REQUEST_UNIT_RECORD: "request_unit_record.p0.v1",
        P0RecordCode.INPUT_BINDING_RECORD: "input_binding_record.p0.v1",
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD: (
            "conversation_task_link_record.p0.v1"
        ),
        P0RecordCode.RUN_TASK_LINK_RECORD: "run_task_link_record.p0.v1",
    }
)
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


class _RuV2WriteNotApplicable(Exception):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()


class _RuV2WriteProjectionConflict(Exception):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()


class _Cycle2NotApplicable(Exception):
    __slots__ = ()


class _Cycle2ProjectionConflict(Exception):
    __slots__ = ()


class _Cycle2AlreadyApplied(Exception):
    __slots__ = ()


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
        envelope_references = _exact_run_parse_envelope(
            row.envelope
        ).record_references
        normalized = tuple(
            P0RecordReference.model_validate_json(
                json.dumps(
                    {
                        "relation": reference.relation,
                        "target_record_code": (
                            P0RecordCode.OBSERVATION_RECORD.value
                            if ordinal < len(envelope_references)
                            and envelope_references[
                                ordinal
                            ].target_record_code
                            is P0RecordCode.OBSERVATION_RECORD
                            and reference.target_record_code
                            in {
                                code.value
                                for code in _PHYSICAL_OBSERVATION_RECORD_CODES
                            }
                            else reference.target_record_code
                        ),
                        "target_logical_identity": (
                            reference.target_logical_identity
                        ),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                strict=True,
            )
            for ordinal, reference in enumerate(references)
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

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        cycle2_clock: Callable[[], datetime] | None = None,
        cycle2_run_budget_policy: Cycle2RunBudgetPolicyEvidence | None = None,
        cycle2_session_owners: Mapping[str, str] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._cycle2_clock = cycle2_clock
        self._cycle2_run_budget_policy = cycle2_run_budget_policy
        self._cycle2_session_owners = MappingProxyType(
            dict(cycle2_session_owners or {})
        )

    @staticmethod
    def _cycle2_version(
        record_code: P0RecordCode,
        record: BaseModel | None = None,
    ) -> str:
        if record_code is P0RecordCode.INPUT_BINDING_RECORD and record is not None:
            if type(record) is InputBinding:
                return "input_binding_record.p0.v1"
            if type(record) is InputBindingV2:
                return "input_binding_record.p0.v2"
        version = _CYCLE2_VERSION_BY_CODE.get(record_code)
        if version is None:
            raise _integrity(P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE)
        return version

    @classmethod
    def _cycle2_encode(
        cls,
        record_code: P0RecordCode,
        record: BaseModel,
        *,
        logical_children: tuple[BaseModel, ...] = (),
        external_references: tuple[P0RecordReference, ...] = (),
    ) -> P0PersistenceEnvelope:
        if (
            record_code is P0RecordCode.GATE_DECISION_RECORD
            and type(record) is GateDecisionV2
        ):
            record = GateDecisionV2.model_validate_json(
                record.model_dump_json(warnings="error"),
                strict=True,
            )
        version = cls._cycle2_version(record_code, record)
        if record_code in {
            P0RecordCode.CONVERSATION_RECORD,
            P0RecordCode.MESSAGE_RECORD,
            P0RecordCode.TASK_RECORD,
            P0RecordCode.REQUEST_UNIT_RECORD,
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            P0RecordCode.CONTEXT_MANIFEST_RECORD,
        } or (
            record_code is P0RecordCode.INPUT_BINDING_RECORD
            and type(record) is InputBinding
        ):
            envelope = encode_persistence_record(
                record_code,
                record,
                logical_children=logical_children,
                external_references=external_references,
            )
            decoded = cls._decode_envelope(
                envelope,
                expected_code=record_code,
            )
        else:
            return cls._ru_v2_write_encode(
                record_code,
                record,
                schema_version=version,
                external_references=external_references,
                logical_children=logical_children,
            )
        if (
            decoded.source_record != record
            or decoded.logical_children != logical_children
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        return envelope

    @classmethod
    def _cycle2_encode_input_binding(
        cls,
        record: InputBindingV2,
        *,
        request_unit_id: UUID,
    ) -> P0PersistenceEnvelope:
        return cls._cycle2_encode(
            P0RecordCode.INPUT_BINDING_RECORD,
            record,
            external_references=(
                _external_reference(
                    "request_unit_id",
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    "request_unit_id",
                    request_unit_id,
                ),
            ),
        )

    @classmethod
    def _cycle2_projection_values(
        cls,
        envelope: P0PersistenceEnvelope,
        decoded: DecodedP0PersistenceRecord,
        *,
        owner_customer_id: str,
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
            if envelope.record_code is P0RecordCode.AGENT_RUN_RECORD
            else None
        )
        return {
            "record_code": envelope.record_code.value,
            "record_schema_version": envelope.record_schema_version,
            "logical_identity": _json_identity(envelope.logical_identity),
            "direct_owner_customer_id": envelope.direct_owner_customer_id,
            "scope_owner_customer_id": owner_customer_id,
            "conversation_id": uuid_projection("conversation_id"),
            "run_id": uuid_projection("run_id"),
            "task_id": uuid_projection("task_id"),
            "request_unit_id": uuid_projection("request_unit_id"),
            "lifecycle_status": lifecycle_status,
            "state_version": state_version if type(state_version) is int else None,
            "attempt_count": attempt_count if type(attempt_count) is int else None,
            "recovery_sort_at": (
                recovery_sort_at
                if type(recovery_sort_at) is datetime
                else None
            ),
            "envelope": envelope.model_dump(mode="json"),
        }

    @staticmethod
    def _cycle2_versioned_decode_input(
        row: P0RecordModel | P0RecordStateHistoryModel,
        record_code: P0RecordCode,
    ) -> dict[str, Any]:
        raw = json.loads(
            json.dumps(row.envelope, ensure_ascii=False, separators=(",", ":"))
        )
        model_type = _CYCLE2_MODEL_BY_PAIR.get(
            (record_code, row.record_schema_version)
        )
        if model_type is None:
            return raw
        payload = raw.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return raw
        try:
            rebuilt = model_type.model_validate_json(
                json.dumps(payload["data"], ensure_ascii=False, separators=(",", ":")),
                strict=True,
            )
            payload["data"] = rebuilt.model_dump(mode="json")
            children = payload.get("logical_children")
            if isinstance(children, list):
                ordered_children = []
                for child in children:
                    if not isinstance(child, dict) or not isinstance(child.get("data"), dict):
                        ordered_children.append(child)
                        continue
                    child_type = {
                        "tool_attempt_record": ToolAttemptRecordV2,
                        "tool_retry_recovery_decision_record": (
                            ToolRetryRecoveryDecisionRecordV2
                        ),
                    }.get(child.get("child_code"))
                    if child_type is not None:
                        child_record = child_type.model_validate_json(
                            json.dumps(child["data"], ensure_ascii=False, separators=(",", ":")),
                            strict=True,
                        )
                        child["data"] = child_record.model_dump(mode="json")
                    ordered_children.append(
                        {
                            key: child[key]
                            for key in (
                                "data",
                                "child_code",
                                "parent_record_code",
                                "parent_logical_identity",
                                "logical_identity",
                            )
                            if key in child
                        }
                    )
                payload["logical_children"] = ordered_children
        except (TypeError, ValueError, ValidationError, RecursionError):
            return raw
        raw["record_references"] = [
            {
                key: reference[key]
                for key in (
                    "relation",
                    "target_record_code",
                    "target_logical_identity",
                )
                if key in reference
            }
            for reference in raw.get("record_references", [])
            if isinstance(reference, dict)
        ]
        raw["payload"] = {
            key: payload[key]
            for key in (
                "data",
                "record_code",
                "record_schema_version",
                "logical_children",
            )
            if key in payload
        }
        return {
            key: raw[key]
            for key in (
                "record_code",
                "record_schema_version",
                "logical_identity",
                "direct_owner_customer_id",
                "record_references",
                "payload",
            )
            if key in raw
        }

    @staticmethod
    def _ru_v2_write_decode_cycle2(
        envelope: P0PersistenceEnvelope | dict[str, Any],
        *,
        record_code: P0RecordCode,
        schema_version: str,
    ) -> DecodedP0PersistenceRecord:
        return decode_persistence_record_versioned(
            envelope,
            expected_record_code=record_code,
            expected_schema_version=schema_version,
            correlation_ref=uuid4(),
        )

    @classmethod
    def _cycle2_decode_row(
        cls,
        session: Session,
        row: P0RecordModel,
        *,
        owner_customer_id: str,
        expected_code: P0RecordCode | None = None,
        expected_versions: frozenset[str] | None = None,
    ) -> DecodedP0PersistenceRecord:
        record_code = _RECORD_CODE_BY_VALUE.get(row.record_code)
        if record_code is None:
            raise _integrity(P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE)
        if expected_code is not None and record_code is not expected_code:
            raise _integrity(P0PersistenceIntegrityCategory.RECORD_CODE_MISMATCH)
        allowed_versions = expected_versions
        if allowed_versions is None:
            allowed_versions = frozenset({cls._cycle2_version(record_code)})
        if row.record_schema_version not in allowed_versions:
            raise _integrity(
                P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            )
        if row.scope_owner_customer_id != owner_customer_id:
            raise _integrity(
                P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
            )
        envelope = _exact_run_parse_envelope(row.envelope)
        decoded = cls._ru_v2_write_decode_cycle2(
            cls._cycle2_versioned_decode_input(row, record_code),
            record_code=record_code,
            schema_version=row.record_schema_version,
        )
        expected_projection = cls._cycle2_projection_values(
            envelope,
            decoded,
            owner_customer_id=owner_customer_id,
        )
        for field_name, value in expected_projection.items():
            if getattr(row, field_name) != value:
                category = (
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                    if field_name == "scope_owner_customer_id"
                    else P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
                raise _integrity(category)
        if (
            envelope.record_code is not record_code
            or envelope.record_schema_version != row.record_schema_version
            or (
                envelope.direct_owner_customer_id is not None
                and envelope.direct_owner_customer_id != owner_customer_id
            )
            or _exact_run_normalized_references(session, row)
            != envelope.record_references
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        return decoded

    @classmethod
    def _cycle2_validate_reference_targets(
        cls,
        session: Session,
        envelope: P0PersistenceEnvelope,
        *,
        owner_customer_id: str,
        pending_keys: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        for logical_reference in envelope.record_references:
            reference = cls._cycle2_physical_reference(
                session,
                logical_reference,
                owner_customer_id=owner_customer_id,
                pending_keys=pending_keys,
            )
            key = (
                reference.target_record_code.value,
                _canonical_identity_text(
                    _json_identity(reference.target_logical_identity)
                ),
            )
            if key in pending_keys:
                continue
            statement = select(P0RecordModel).where(
                P0RecordModel.record_code == reference.target_record_code.value,
                P0RecordModel.logical_identity
                == _json_identity(reference.target_logical_identity),
            )
            if reference.target_record_code in _PRIVATE_RECORD_CODES:
                statement = statement.where(
                    P0RecordModel.scope_owner_customer_id == owner_customer_id
                )
            else:
                statement = statement.where(
                    P0RecordModel.scope_owner_customer_id.is_(None)
                )
            target = session.scalar(statement.limit(1))
            if target is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            if reference.target_record_code in _PRIVATE_RECORD_CODES:
                allowed_versions = (
                    _CYCLE2_INPUT_BINDING_VERSIONS
                    if reference.target_record_code
                    is P0RecordCode.INPUT_BINDING_RECORD
                    else frozenset(
                        {cls._cycle2_version(reference.target_record_code)}
                    )
                )
                cls._cycle2_decode_row(
                    session,
                    target,
                    owner_customer_id=owner_customer_id,
                    expected_code=reference.target_record_code,
                    expected_versions=allowed_versions,
                )

    @classmethod
    def _cycle2_physical_reference(
        cls,
        session: Session,
        reference: P0RecordReference,
        *,
        owner_customer_id: str,
        pending_keys: frozenset[tuple[str, str]] = frozenset(),
    ) -> P0RecordReference:
        if reference.target_record_code is not P0RecordCode.OBSERVATION_RECORD:
            return reference
        identity = _json_identity(reference.target_logical_identity)
        identity_text = _canonical_identity_text(identity)
        pending_codes = {
            code
            for code in _PHYSICAL_OBSERVATION_RECORD_CODES
            if (code.value, identity_text) in pending_keys
        }
        persisted_codes = {
            record_code
            for value in session.scalars(
                select(P0RecordModel.record_code)
                .where(
                    P0RecordModel.record_code.in_(
                        tuple(
                            code.value
                            for code in _PHYSICAL_OBSERVATION_RECORD_CODES
                        )
                    ),
                    P0RecordModel.logical_identity == identity,
                    P0RecordModel.scope_owner_customer_id
                    == owner_customer_id,
                )
                .limit(2)
            )
            if (record_code := _RECORD_CODE_BY_VALUE.get(value)) is not None
        }
        physical_codes = pending_codes | persisted_codes
        if len(physical_codes) != 1:
            category = (
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                if physical_codes
                else P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
            raise _integrity(category)
        physical_code = next(iter(physical_codes))
        if physical_code is P0RecordCode.OBSERVATION_RECORD:
            return reference
        return P0RecordReference(
            relation=reference.relation,
            target_record_code=physical_code,
            target_logical_identity=reference.target_logical_identity,
        )

    @classmethod
    def _cycle2_row(
        cls,
        session: Session,
        *,
        owner_customer_id: str,
        record_code: P0RecordCode,
        logical_identity: tuple[tuple[str, object], ...],
        for_update: bool = False,
        expected_versions: frozenset[str] | None = None,
    ) -> tuple[P0RecordModel, DecodedP0PersistenceRecord] | None:
        statement = select(P0RecordModel).where(
            P0RecordModel.record_code == record_code.value,
            P0RecordModel.logical_identity == _json_identity(logical_identity),
            P0RecordModel.scope_owner_customer_id == owner_customer_id,
        )
        if for_update:
            statement = statement.with_for_update()
        rows = tuple(session.scalars(statement.limit(2)))
        if not rows:
            return None
        if len(rows) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        row = rows[0]
        decoded = cls._cycle2_decode_row(
            session,
            row,
            owner_customer_id=owner_customer_id,
            expected_code=record_code,
            expected_versions=expected_versions,
        )
        cls._cycle2_validate_reference_targets(
            session,
            _exact_run_parse_envelope(row.envelope),
            owner_customer_id=owner_customer_id,
        )
        return row, decoded

    @classmethod
    def _cycle2_rows(
        cls,
        session: Session,
        *,
        owner_customer_id: str,
        record_code: P0RecordCode,
        predicates: tuple[object, ...] = (),
        for_update: bool = False,
        expected_versions: frozenset[str] | None = None,
    ) -> tuple[tuple[P0RecordModel, DecodedP0PersistenceRecord], ...]:
        statement = (
            select(P0RecordModel)
            .where(
                P0RecordModel.record_code == record_code.value,
                P0RecordModel.scope_owner_customer_id == owner_customer_id,
                *predicates,
            )
            .order_by(P0RecordModel.logical_identity)
        )
        if for_update:
            statement = statement.with_for_update()
        rows = tuple(session.scalars(statement))
        result = []
        for row in rows:
            decoded = cls._cycle2_decode_row(
                session,
                row,
                owner_customer_id=owner_customer_id,
                expected_code=record_code,
                expected_versions=expected_versions,
            )
            cls._cycle2_validate_reference_targets(
                session,
                _exact_run_parse_envelope(row.envelope),
                owner_customer_id=owner_customer_id,
            )
            result.append((row, decoded))
        return tuple(result)

    @classmethod
    def _cycle2_insert(
        cls,
        session: Session,
        envelopes: tuple[P0PersistenceEnvelope, ...],
        *,
        owner_customer_id: str,
    ) -> None:
        keys = frozenset(cls._envelope_key(envelope) for envelope in envelopes)
        for envelope in envelopes:
            cls._cycle2_validate_reference_targets(
                session,
                envelope,
                owner_customer_id=owner_customer_id,
                pending_keys=keys,
            )
        for envelope in sorted(envelopes, key=cls._envelope_key):
            decoded = cls._ru_v2_write_decode_cycle2(
                envelope,
                record_code=envelope.record_code,
                schema_version=envelope.record_schema_version,
            )
            values = cls._cycle2_projection_values(
                envelope,
                decoded,
                owner_customer_id=owner_customer_id,
            )
            inserted = session.scalar(
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
            if inserted is None:
                raise _Cycle2ProjectionConflict() from None
        session.flush()
        for envelope in envelopes:
            session.add_all(
                cls._reference_model(
                    envelope,
                    ordinal=ordinal,
                    reference=cls._cycle2_physical_reference(
                        session,
                        reference,
                        owner_customer_id=owner_customer_id,
                    ),
                )
                for ordinal, reference in enumerate(envelope.record_references)
            )
        session.flush()

    @classmethod
    def _cycle2_archive_preimage(
        cls,
        session: Session,
        row: P0RecordModel,
        decoded: DecodedP0PersistenceRecord,
        *,
        owner_customer_id: str,
    ) -> None:
        record_code = _RECORD_CODE_BY_VALUE.get(row.record_code)
        if record_code not in {
            P0RecordCode.TASK_RECORD,
            P0RecordCode.REQUEST_UNIT_RECORD,
        }:
            return
        source_record = decoded.source_record
        if (
            record_code is P0RecordCode.TASK_RECORD
            and type(source_record) is not TaskRecord
        ) or (
            record_code is P0RecordCode.REQUEST_UNIT_RECORD
            and type(source_record) is not RequestUnitRecord
        ):
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        state_version = cast(TaskRecord | RequestUnitRecord, source_record).state_version
        if (
            type(state_version) is not int
            or state_version < 1
            or row.state_version != state_version
            or row.scope_owner_customer_id != owner_customer_id
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        values = {
            "history_id": uuid4(),
            "record_code": row.record_code,
            "record_schema_version": row.record_schema_version,
            "logical_identity": row.logical_identity,
            "scope_owner_customer_id": owner_customer_id,
            "state_version": state_version,
            "envelope": row.envelope,
        }
        inserted = session.scalar(
            postgresql_insert(P0RecordStateHistoryModel)
            .values(**values)
            .on_conflict_do_nothing(
                constraint="uq_p0_record_state_history_logical_version"
            )
            .returning(P0RecordStateHistoryModel.history_id)
        )
        if inserted is not None:
            return
        existing = tuple(
            session.scalars(
                select(P0RecordStateHistoryModel)
                .where(
                    P0RecordStateHistoryModel.record_code == row.record_code,
                    P0RecordStateHistoryModel.logical_identity
                    == row.logical_identity,
                    P0RecordStateHistoryModel.state_version == state_version,
                )
                .limit(2)
            )
        )
        if len(existing) != 1:
            raise _Cycle2ProjectionConflict() from None
        historical = existing[0]
        if any(
            (
                historical.record_schema_version != row.record_schema_version,
                historical.scope_owner_customer_id != owner_customer_id,
                historical.envelope != row.envelope,
            )
        ):
            raise _Cycle2ProjectionConflict() from None
        verified = cls._cycle2_historical_row(
            session,
            owner_customer_id=owner_customer_id,
            record_code=record_code,
            logical_identity=cast(
                tuple[tuple[str, object], ...],
                _exact_run_parse_envelope(row.envelope).logical_identity,
            ),
            state_version=state_version,
        )
        if (
            verified is None
            or verified.source_record != decoded.source_record
            or verified.logical_children != decoded.logical_children
        ):
            raise _Cycle2ProjectionConflict() from None

    @classmethod
    def _cycle2_historical_row(
        cls,
        session: Session,
        *,
        owner_customer_id: str,
        record_code: P0RecordCode,
        logical_identity: tuple[tuple[str, object], ...],
        state_version: int,
    ) -> DecodedP0PersistenceRecord | None:
        expected_version = cls._cycle2_version(record_code)
        rows = tuple(
            session.scalars(
                select(P0RecordStateHistoryModel)
                .where(
                    P0RecordStateHistoryModel.scope_owner_customer_id
                    == owner_customer_id,
                    P0RecordStateHistoryModel.record_code == record_code.value,
                    P0RecordStateHistoryModel.logical_identity
                    == _json_identity(logical_identity),
                    P0RecordStateHistoryModel.state_version == state_version,
                )
                .limit(2)
            )
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        row = rows[0]
        if (
            row.record_schema_version != expected_version
            or row.scope_owner_customer_id != owner_customer_id
            or row.record_code != record_code.value
            or row.logical_identity != _json_identity(logical_identity)
            or row.state_version != state_version
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        envelope = _exact_run_parse_envelope(row.envelope)
        decoded = cls._ru_v2_write_decode_cycle2(
            cls._cycle2_versioned_decode_input(row, record_code),
            record_code=record_code,
            schema_version=expected_version,
        )
        source_record = decoded.source_record
        if (
            record_code is P0RecordCode.TASK_RECORD
            and type(source_record) is not TaskRecord
        ) or (
            record_code is P0RecordCode.REQUEST_UNIT_RECORD
            and type(source_record) is not RequestUnitRecord
        ):
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        historical_record = cast(
            TaskRecord | RequestUnitRecord,
            source_record,
        )
        if (
            envelope.record_code is not record_code
            or envelope.record_schema_version != expected_version
            or _json_identity(envelope.logical_identity) != row.logical_identity
            or (
                envelope.direct_owner_customer_id is not None
                and envelope.direct_owner_customer_id != owner_customer_id
            )
            or historical_record.state_version != state_version
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        if (
            record_code is P0RecordCode.TASK_RECORD
            and (
                cast(TaskRecord, source_record).owner_customer_id
                != owner_customer_id
            )
        ):
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        cls._cycle2_validate_reference_targets(
            session,
            envelope,
            owner_customer_id=owner_customer_id,
        )
        return decoded

    @classmethod
    def _cycle2_replace(
        cls,
        session: Session,
        row: P0RecordModel,
        *,
        owner_customer_id: str,
        expected_record: BaseModel,
        expected_children: tuple[BaseModel, ...] = (),
        next_envelope: P0PersistenceEnvelope,
    ) -> None:
        decoded = cls._cycle2_decode_row(
            session,
            row,
            owner_customer_id=owner_customer_id,
            expected_code=next_envelope.record_code,
        )
        if (
            decoded.source_record != expected_record
            or decoded.logical_children != expected_children
        ):
            raise _Cycle2NotApplicable() from None
        cls._cycle2_validate_reference_targets(
            session,
            next_envelope,
            owner_customer_id=owner_customer_id,
        )
        next_decoded = cls._ru_v2_write_decode_cycle2(
            next_envelope,
            record_code=next_envelope.record_code,
            schema_version=next_envelope.record_schema_version,
        )
        values = cls._cycle2_projection_values(
            next_envelope,
            next_decoded,
            owner_customer_id=owner_customer_id,
        )
        cls._cycle2_archive_preimage(
            session,
            row,
            decoded,
            owner_customer_id=owner_customer_id,
        )
        result = session.execute(
            update(P0RecordModel)
            .where(
                P0RecordModel.record_id == row.record_id,
                P0RecordModel.envelope == row.envelope,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise _Cycle2NotApplicable() from None
        session.execute(
            delete(P0RecordReferenceModel).where(
                P0RecordReferenceModel.source_record_code == row.record_code,
                P0RecordReferenceModel.source_logical_identity
                == row.logical_identity,
            )
        )
        session.add_all(
            cls._reference_model(
                next_envelope,
                ordinal=ordinal,
                reference=cls._cycle2_physical_reference(
                    session,
                    reference,
                    owner_customer_id=owner_customer_id,
                ),
            )
            for ordinal, reference in enumerate(next_envelope.record_references)
        )
        session.flush()

    def _cycle2_trusted_now(self) -> datetime:
        if self._cycle2_clock is None:
            raise _integrity(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)
        trusted_now = self._cycle2_clock()
        if type(trusted_now) is not datetime or trusted_now.tzinfo is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        if trusted_now.utcoffset() != UTC.utcoffset(trusted_now):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        return trusted_now

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
        if row.record_code in {
            P0RecordCode.TASK_RECORD.value,
            P0RecordCode.REQUEST_UNIT_RECORD.value,
        }:
            if owner is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
            try:
                self._cycle2_archive_preimage(
                    session,
                    row,
                    decoded,
                    owner_customer_id=owner,
                )
            except _Cycle2ProjectionConflict:
                return False
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

    @staticmethod
    def _ru_v2_write_version(record_code: P0RecordCode) -> str:
        expected_version = _RU_V2_WRITE_VERSION_BY_CODE.get(record_code)
        if expected_version is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
            )
        return expected_version

    @classmethod
    def _ru_v2_write_encode(
        cls,
        record_code: P0RecordCode,
        record: BaseModel,
        *,
        schema_version: str | None = None,
        external_references: tuple[P0RecordReference, ...] = (),
        logical_children: tuple[BaseModel, ...] = (),
    ) -> P0PersistenceEnvelope:
        expected_version = (
            cls._ru_v2_write_version(record_code)
            if schema_version is None
            else schema_version
        )
        envelope = encode_persistence_record_versioned(
            record_code,
            expected_version,
            record,
            external_references=external_references,
            logical_children=logical_children,
        )
        decoded = decode_persistence_record_versioned(
            envelope,
            expected_record_code=record_code,
            expected_schema_version=expected_version,
            correlation_ref=uuid4(),
        )
        if (
            decoded.source_record != record
            or decoded.logical_children != logical_children
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        return envelope

    @classmethod
    def _ru_v2_write_projection_values(
        cls,
        envelope: P0PersistenceEnvelope,
        decoded: DecodedP0PersistenceRecord,
        *,
        owner_customer_id: str,
    ) -> dict[str, object]:
        record_code = envelope.record_code
        expected_version = cls._ru_v2_write_version(record_code)
        if (
            envelope.record_schema_version != expected_version
            or decoded.record_code is not record_code
            or decoded.record_schema_version != expected_version
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            )
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
            "record_schema_version": expected_version,
            "logical_identity": _json_identity(envelope.logical_identity),
            "direct_owner_customer_id": envelope.direct_owner_customer_id,
            "scope_owner_customer_id": owner_customer_id,
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
                if type(recovery_sort_at) is datetime
                else None
            ),
            "envelope": envelope.model_dump(mode="json"),
        }

    @classmethod
    def _ru_v2_write_validate_row(
        cls,
        session: Session,
        row: P0RecordModel,
        *,
        expected_code: P0RecordCode,
        owner_customer_id: str,
    ) -> tuple[DecodedP0PersistenceRecord, P0PersistenceEnvelope]:
        expected_version = cls._ru_v2_write_version(expected_code)
        if row.record_code != expected_code.value:
            raise _integrity(
                P0PersistenceIntegrityCategory.RECORD_CODE_MISMATCH
            )
        if row.record_schema_version != expected_version:
            raise _integrity(
                P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            )
        if row.scope_owner_customer_id != owner_customer_id:
            raise _integrity(
                P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
            )
        envelope = _exact_run_parse_envelope(row.envelope)
        decoded = decode_persistence_record_versioned(
            _exact_run_versioned_decode_input(row, expected_code),
            expected_record_code=expected_code,
            expected_schema_version=expected_version,
            correlation_ref=uuid4(),
        )
        expected_projection = cls._ru_v2_write_projection_values(
            envelope,
            decoded,
            owner_customer_id=owner_customer_id,
        )
        for field_name, value in expected_projection.items():
            if getattr(row, field_name) != value:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                    if field_name == "scope_owner_customer_id"
                    else P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
        if (
            envelope.record_code is not expected_code
            or envelope.record_schema_version != expected_version
            or (
                envelope.direct_owner_customer_id is not None
                and envelope.direct_owner_customer_id != owner_customer_id
            )
            or _exact_run_normalized_references(session, row)
            != envelope.record_references
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        return decoded, envelope

    @staticmethod
    def _ru_v2_write_metadata_for_run(
        session: Session,
        *,
        record_code: P0RecordCode,
        run_id: UUID,
    ) -> tuple[object, ...]:
        return tuple(
            session.execute(
                select(
                    P0RecordModel.record_id,
                    P0RecordModel.record_code,
                    P0RecordModel.logical_identity,
                    P0RecordModel.record_schema_version,
                    P0RecordModel.scope_owner_customer_id,
                    P0RecordModel.run_id,
                )
                .where(
                    P0RecordModel.record_code == record_code.value,
                    P0RecordModel.run_id == run_id,
                )
                .order_by(P0RecordModel.logical_identity)
                .limit(2)
                .with_for_update()
            )
        )

    @staticmethod
    def _ru_v2_write_metadata_for_identity(
        session: Session,
        *,
        record_code: P0RecordCode,
        logical_identity: tuple[tuple[str, object], ...],
    ) -> tuple[object, ...]:
        return tuple(
            session.execute(
                select(
                    P0RecordModel.record_id,
                    P0RecordModel.record_code,
                    P0RecordModel.logical_identity,
                    P0RecordModel.record_schema_version,
                    P0RecordModel.scope_owner_customer_id,
                    P0RecordModel.run_id,
                )
                .where(
                    P0RecordModel.record_code == record_code.value,
                    P0RecordModel.logical_identity
                    == _json_identity(logical_identity),
                )
                .order_by(P0RecordModel.logical_identity)
                .limit(2)
                .with_for_update()
            )
        )

    @classmethod
    def _ru_v2_write_check_metadata_rows(
        cls,
        rows: tuple[object, ...],
        *,
        record_code: P0RecordCode,
        owner_customer_id: str,
        allowed_identity: list[list[object]] | None,
    ) -> None:
        for metadata in rows:
            if metadata.scope_owner_customer_id != owner_customer_id:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
        if len(rows) > 1:
            raise _RuV2WriteProjectionConflict() from None
        if not rows:
            return
        metadata = rows[0]
        expected_version = cls._ru_v2_write_version(record_code)
        if metadata.record_schema_version != expected_version:
            if (
                record_code is P0RecordCode.REQUEST_UNDERSTANDING_RECORD
                and metadata.record_schema_version
                == "request_understanding_record.p0.v1"
            ):
                raise _RuV2WriteProjectionConflict() from None
            raise _integrity(
                P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            )
        if (
            metadata.record_code != record_code.value
            or metadata.run_id is None
            and record_code
            in {
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                P0RecordCode.RUN_TASK_LINK_RECORD,
            }
        ):
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        if (
            allowed_identity is None
            or metadata.logical_identity != allowed_identity
        ):
            raise _RuV2WriteProjectionConflict() from None

    @classmethod
    def _ru_v2_write_check_same_run(
        cls,
        session: Session,
        *,
        run_id: UUID,
        owner_customer_id: str,
        allowed_ru_identity: list[list[object]] | None,
        allowed_run_link_identity: list[list[object]] | None,
    ) -> None:
        for record_code, allowed_identity in (
            (
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                allowed_ru_identity,
            ),
            (
                P0RecordCode.RUN_TASK_LINK_RECORD,
                allowed_run_link_identity,
            ),
        ):
            rows = cls._ru_v2_write_metadata_for_run(
                session,
                record_code=record_code,
                run_id=run_id,
            )
            cls._ru_v2_write_check_metadata_rows(
                rows,
                record_code=record_code,
                owner_customer_id=owner_customer_id,
                allowed_identity=allowed_identity,
            )

    @classmethod
    def _ru_v2_write_lock_roots(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        conversation: ConversationRecord,
        messages: tuple[MessageRecord, ...],
        run: AgentRunRecord,
    ) -> tuple[P0RecordModel, ...]:
        expected_roots: tuple[
            tuple[
                P0RecordCode,
                tuple[tuple[str, object], ...],
                BaseModel,
            ],
            ...,
        ] = (
            (
                P0RecordCode.CONVERSATION_RECORD,
                (("conversation_id", conversation.conversation_id),),
                conversation,
            ),
            *(
                (
                    P0RecordCode.MESSAGE_RECORD,
                    (("message_id", message.message_id),),
                    message,
                )
                for message in messages
            ),
            (
                P0RecordCode.AGENT_RUN_RECORD,
                (("run_id", run.run_id),),
                run,
            ),
        )
        locked: list[P0RecordModel] = []
        for record_code, identity, expected in sorted(
            expected_roots,
            key=lambda item: (
                item[0].value,
                _canonical_identity_text(_json_identity(item[1])),
            ),
        ):
            row = session.scalar(
                select(P0RecordModel)
                .where(
                    P0RecordModel.record_code == record_code.value,
                    P0RecordModel.logical_identity
                    == _json_identity(identity),
                    P0RecordModel.scope_owner_customer_id
                    == owner_scope.customer_id,
                )
                .with_for_update()
            )
            if row is None:
                raise _RuV2WriteNotApplicable() from None
            decoded, _envelope = cls._ru_v2_write_validate_row(
                session,
                row,
                expected_code=record_code,
                owner_customer_id=owner_scope.customer_id,
            )
            if decoded.source_record != expected or decoded.logical_children:
                raise _RuV2WriteProjectionConflict() from None
            locked.append(row)
        return tuple(locked)

    @staticmethod
    def _ru_v2_write_row_key(
        record_code: P0RecordCode,
        logical_identity: tuple[tuple[str, object], ...],
    ) -> tuple[str, str]:
        return (
            record_code.value,
            _canonical_identity_text(_json_identity(logical_identity)),
        )

    @classmethod
    def _ru_v2_write_validate_closed_rows(
        cls,
        rows: tuple[P0RecordModel, ...],
        *,
        owner_customer_id: str,
    ) -> None:
        by_key: dict[
            tuple[str, str],
            tuple[P0RecordModel, P0PersistenceEnvelope],
        ] = {}
        for row in rows:
            record_code = _RECORD_CODE_BY_VALUE.get(row.record_code)
            if (
                record_code is None
                or record_code not in _RU_V2_WRITE_VERSION_BY_CODE
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
                )
            _decoded, envelope = cls._ru_v2_write_validate_row(
                session=cast(Session, row._sa_instance_state.session),
                row=row,
                expected_code=record_code,
                owner_customer_id=owner_customer_id,
            )
            key = (
                record_code.value,
                _canonical_identity_text(row.logical_identity),
            )
            if key in by_key:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                )
            by_key[key] = (row, envelope)
        for _row, envelope in by_key.values():
            for reference in envelope.record_references:
                target_key = (
                    reference.target_record_code.value,
                    _canonical_identity_text(
                        _json_identity(reference.target_logical_identity)
                    ),
                )
                if target_key not in by_key:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                    )

    @classmethod
    def _ru_v2_write_target_rows(
        cls,
        session: Session,
        envelopes: tuple[P0PersistenceEnvelope, ...],
        *,
        owner_customer_id: str,
    ) -> tuple[P0RecordModel, ...] | None:
        metadata_by_key: dict[tuple[str, str], object] = {}
        for envelope in sorted(envelopes, key=cls._envelope_key):
            rows = cls._ru_v2_write_metadata_for_identity(
                session,
                record_code=envelope.record_code,
                logical_identity=envelope.logical_identity,
            )
            cls._ru_v2_write_check_metadata_rows(
                rows,
                record_code=envelope.record_code,
                owner_customer_id=owner_customer_id,
                allowed_identity=_json_identity(envelope.logical_identity),
            )
            if rows:
                metadata_by_key[cls._envelope_key(envelope)] = rows[0]
        if not metadata_by_key:
            return None
        if len(metadata_by_key) != len(envelopes):
            raise _RuV2WriteProjectionConflict() from None
        loaded: list[P0RecordModel] = []
        for envelope in sorted(envelopes, key=cls._envelope_key):
            metadata = metadata_by_key[cls._envelope_key(envelope)]
            row = session.scalar(
                select(P0RecordModel)
                .where(
                    P0RecordModel.record_id == metadata.record_id,
                    P0RecordModel.record_code == envelope.record_code.value,
                    P0RecordModel.logical_identity
                    == _json_identity(envelope.logical_identity),
                    P0RecordModel.scope_owner_customer_id
                    == owner_customer_id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if row is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
            decoded, persisted_envelope = cls._ru_v2_write_validate_row(
                session,
                row,
                expected_code=envelope.record_code,
                owner_customer_id=owner_customer_id,
            )
            desired_decoded = decode_persistence_record_versioned(
                envelope,
                expected_record_code=envelope.record_code,
                expected_schema_version=cls._ru_v2_write_version(
                    envelope.record_code
                ),
                correlation_ref=uuid4(),
            )
            if (
                persisted_envelope.model_dump(mode="json")
                != envelope.model_dump(mode="json")
                or decoded != desired_decoded
            ):
                raise _RuV2WriteProjectionConflict() from None
            loaded.append(row)
        return tuple(loaded)

    @classmethod
    def _ru_v2_write_insert_targets(
        cls,
        session: Session,
        envelopes: tuple[P0PersistenceEnvelope, ...],
        *,
        owner_customer_id: str,
    ) -> tuple[P0RecordModel, ...]:
        for envelope in sorted(envelopes, key=cls._envelope_key):
            decoded = decode_persistence_record_versioned(
                envelope,
                expected_record_code=envelope.record_code,
                expected_schema_version=cls._ru_v2_write_version(
                    envelope.record_code
                ),
                correlation_ref=uuid4(),
            )
            values = cls._ru_v2_write_projection_values(
                envelope,
                decoded,
                owner_customer_id=owner_customer_id,
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
            if inserted_record_id is None:
                raise _RuV2WriteProjectionConflict() from None
        session.flush()
        for envelope in sorted(envelopes, key=cls._envelope_key):
            session.add_all(
                cls._reference_model(
                    envelope,
                    ordinal=ordinal,
                    reference=reference,
                )
                for ordinal, reference in enumerate(
                    envelope.record_references
                )
            )
        session.flush()
        loaded: list[P0RecordModel] = []
        for envelope in sorted(envelopes, key=cls._envelope_key):
            row = session.scalar(
                select(P0RecordModel)
                .where(
                    P0RecordModel.record_code == envelope.record_code.value,
                    P0RecordModel.logical_identity
                    == _json_identity(envelope.logical_identity),
                    P0RecordModel.scope_owner_customer_id
                    == owner_customer_id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if row is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.MISSING_RECORD_CODE
                )
            cls._ru_v2_write_validate_row(
                session,
                row,
                expected_code=envelope.record_code,
                owner_customer_id=owner_customer_id,
            )
            loaded.append(row)
        return tuple(loaded)

    @classmethod
    def _ru_v2_write_apply(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        conversation: ConversationRecord,
        messages: tuple[MessageRecord, ...],
        run: AgentRunRecord,
        envelopes: tuple[P0PersistenceEnvelope, ...],
        expected_ru_identity: tuple[tuple[str, object], ...],
        expected_run_link_identity: tuple[tuple[str, object], ...] | None,
    ) -> None:
        root_rows = cls._ru_v2_write_lock_roots(
            session,
            owner_scope=owner_scope,
            conversation=conversation,
            messages=messages,
            run=run,
        )
        cls._ru_v2_write_check_same_run(
            session,
            run_id=run.run_id,
            owner_customer_id=owner_scope.customer_id,
            allowed_ru_identity=_json_identity(expected_ru_identity),
            allowed_run_link_identity=(
                _json_identity(expected_run_link_identity)
                if expected_run_link_identity is not None
                else None
            ),
        )
        target_rows = cls._ru_v2_write_target_rows(
            session,
            envelopes,
            owner_customer_id=owner_scope.customer_id,
        )
        if target_rows is not None:
            cls._ru_v2_write_validate_closed_rows(
                (*root_rows, *target_rows),
                owner_customer_id=owner_scope.customer_id,
            )
            return
        inserted_rows = cls._ru_v2_write_insert_targets(
            session,
            envelopes,
            owner_customer_id=owner_scope.customer_id,
        )
        cls._ru_v2_write_validate_closed_rows(
            (*root_rows, *inserted_rows),
            owner_customer_id=owner_scope.customer_id,
        )
        run_row = next(
            row
            for row in root_rows
            if row.record_code == P0RecordCode.AGENT_RUN_RECORD.value
        )
        cls._touch_recovery_anchor(session, run_row)

    @_bounded_database_failures
    async def save_request_understanding_v2_no_task_if_current(
        self,
        command: SaveRequestUnderstandingV2NoTaskCommand,
    ) -> ConditionalWriteResult:
        try:
            with self.session_factory.begin() as session:
                envelope = self._ru_v2_write_encode(
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                    command.request_understanding_record,
                )
                self._ru_v2_write_apply(
                    session,
                    owner_scope=command.owner_scope,
                    conversation=command.expected_conversation_record,
                    messages=command.expected_message_records,
                    run=command.expected_active_run_record,
                    envelopes=(envelope,),
                    expected_ru_identity=envelope.logical_identity,
                    expected_run_link_identity=None,
                )
        except _RuV2WriteNotApplicable:
            return ConditionalWriteResult.NOT_APPLICABLE
        except _RuV2WriteProjectionConflict:
            return ConditionalWriteResult.PROJECTION_CONFLICT
        return ConditionalWriteResult.APPLIED

    @_bounded_database_failures
    async def create_initial_task_graph_v2_if_current(
        self,
        command: CreateInitialTaskGraphV2Command,
    ) -> ConditionalWriteResult:
        try:
            with self.session_factory.begin() as session:
                request_unit = command.initial_request_unit.initial_record
                envelopes = (
                    self._ru_v2_write_encode(
                        P0RecordCode.TASK_RECORD,
                        command.initial_task.initial_record,
                    ),
                    self._ru_v2_write_encode(
                        P0RecordCode.REQUEST_UNIT_RECORD,
                        request_unit,
                    ),
                    self._ru_v2_write_encode(
                        P0RecordCode.INPUT_BINDING_RECORD,
                        command.input_binding.record,
                        external_references=(
                            _external_reference(
                                "request_unit_id",
                                P0RecordCode.REQUEST_UNIT_RECORD,
                                "request_unit_id",
                                command.input_binding.request_unit_id,
                            ),
                        ),
                    ),
                    self._ru_v2_write_encode(
                        P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                        command.request_understanding.record,
                        logical_children=(
                            command.request_understanding.accepted_delta,
                        ),
                    ),
                    self._ru_v2_write_encode(
                        P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                        command.conversation_task_link,
                    ),
                    self._ru_v2_write_encode(
                        P0RecordCode.RUN_TASK_LINK_RECORD,
                        command.run_task_link.active_record,
                    ),
                )
                ru_envelope = next(
                    envelope
                    for envelope in envelopes
                    if envelope.record_code
                    is P0RecordCode.REQUEST_UNDERSTANDING_RECORD
                )
                run_link_envelope = next(
                    envelope
                    for envelope in envelopes
                    if envelope.record_code
                    is P0RecordCode.RUN_TASK_LINK_RECORD
                )
                self._ru_v2_write_apply(
                    session,
                    owner_scope=command.owner_scope,
                    conversation=command.expected_conversation_record,
                    messages=command.expected_message_records,
                    run=command.expected_active_run_record,
                    envelopes=envelopes,
                    expected_ru_identity=ru_envelope.logical_identity,
                    expected_run_link_identity=(
                        run_link_envelope.logical_identity
                    ),
                )
        except _RuV2WriteNotApplicable:
            return ConditionalWriteResult.NOT_APPLICABLE
        except _RuV2WriteProjectionConflict:
            return ConditionalWriteResult.PROJECTION_CONFLICT
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
            run_rows = tuple(
                session.scalars(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.AGENT_RUN_RECORD.value,
                        P0RecordModel.run_id == record.run_id,
                    )
                    .limit(2)
                )
            )
            if (
                len(run_rows) == 1
                and run_rows[0].record_schema_version
                == "agent_run_record.p0.v2"
                and run_rows[0].scope_owner_customer_id is not None
            ):
                self._cycle2_decode_row(
                    session,
                    run_rows[0],
                    owner_customer_id=run_rows[0].scope_owner_customer_id,
                    expected_code=P0RecordCode.AGENT_RUN_RECORD,
                )
                self._cycle2_insert(
                    session,
                    (envelope,),
                    owner_customer_id=run_rows[0].scope_owner_customer_id,
                )
                return
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

    @classmethod
    def _cycle2_current_task_unit_bindings(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        for_update: bool = False,
    ) -> tuple[TaskRecord, RequestUnitRecord, tuple[InputBindingV2, ...]] | None:
        owner = owner_scope.customer_id
        task_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.TASK_RECORD,
            logical_identity=(("task_id", task_id),),
            for_update=for_update,
        )
        unit_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            logical_identity=(("request_unit_id", request_unit_id),),
            for_update=for_update,
        )
        if task_loaded is None or unit_loaded is None:
            return None
        task = task_loaded[1].source_record
        unit = unit_loaded[1].source_record
        if type(task) is not TaskRecord or type(unit) is not RequestUnitRecord:
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        bindings: list[InputBindingV2] = []
        for binding_id in unit.input_binding_refs:
            loaded = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.INPUT_BINDING_RECORD,
                logical_identity=(("binding_id", binding_id),),
                for_update=for_update,
                expected_versions=frozenset({"input_binding_record.p0.v2"}),
            )
            if loaded is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            binding = loaded[1].source_record
            if type(binding) is not InputBindingV2:
                raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
            bindings.append(binding)
        if len({binding.binding_id for binding in bindings}) != len(bindings):
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        return task, unit, tuple(bindings)

    @staticmethod
    def _cycle2_auto_target_marker(
        record: OrderCandidateAutoTargetRecord,
    ) -> str:
        supersedes = (
            "none"
            if record.supersedes_verified_target_ref is None
            else str(record.supersedes_verified_target_ref)
        )
        return f"cycle2-auto:{record.order_id}:{supersedes}"

    @classmethod
    def _cycle2_auto_target_selection(
        cls,
        *,
        auto_target: OrderCandidateAutoTargetRecord,
        source_message_ref: UUID,
    ) -> OrderCandidateSelectionRecord:
        """Persist the reviewed auto-target through the existing selection family.

        The marker is infrastructure-private and unambiguously disjoint from the
        UUID-valued ``selected_target_ref`` issued for an ordinal selection.
        """

        return OrderCandidateSelectionRecord(
            selection_id=auto_target.verified_target_ref,
            private_owner_scope_ref=auto_target.private_owner_scope_ref,
            conversation_id=auto_target.conversation_id,
            task_id=auto_target.task_id,
            request_unit_id=auto_target.request_unit_id,
            source_message_ref=source_message_ref,
            ordinal_input_binding_ref=auto_target.query_input_binding_ref,
            candidate_set_ref=auto_target.candidate_set_ref,
            candidate_set_version=auto_target.candidate_set_version,
            search_observation_ref=auto_target.search_observation_ref,
            search_observation_record_schema_version=(
                auto_target.search_observation_record_schema_version
            ),
            observation_candidate_ref=auto_target.observation_candidate_ref,
            candidate_source_version=auto_target.candidate_source_version,
            owner_scoped_order_target_ref=(
                auto_target.owner_scoped_order_target_ref
            ),
            selected_target_ref=cls._cycle2_auto_target_marker(auto_target),
            base_task_state_version=auto_target.base_task_state_version,
            result_task_state_version=auto_target.result_task_state_version,
            selected_at=auto_target.verified_at,
        )

    @staticmethod
    def _cycle2_parse_auto_target_marker(
        marker: str,
    ) -> tuple[str, UUID | None] | None:
        prefix = "cycle2-auto:"
        if not marker.startswith(prefix):
            return None
        remainder = marker[len(prefix) :]
        order_id, separator, supersedes_text = remainder.partition(":")
        if not separator or not order_id:
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        if supersedes_text == "none":
            return order_id, None
        try:
            supersedes = UUID(supersedes_text)
        except ValueError:
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            ) from None
        if supersedes.version != 4 or str(supersedes) != supersedes_text:
            raise _integrity(
                P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
            )
        return order_id, supersedes

    @classmethod
    def _cycle2_auto_target_from_selection(
        cls,
        *,
        record: OrderCandidateSelectionRecord,
        candidate_set: OrderCandidateSetRecord,
    ) -> OrderCandidateAutoTargetRecord | None:
        parsed = cls._cycle2_parse_auto_target_marker(
            record.selected_target_ref
        )
        if parsed is None:
            return None
        order_id, supersedes = parsed
        entries = tuple(
            entry
            for entry in candidate_set.ordered_candidates
            if entry.observation_candidate_ref
            == record.observation_candidate_ref
            and entry.candidate_source_version
            == record.candidate_source_version
        )
        if len(entries) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        return OrderCandidateAutoTargetRecord(
            verified_target_ref=record.selection_id,
            private_owner_scope_ref=record.private_owner_scope_ref,
            conversation_id=record.conversation_id,
            task_id=record.task_id,
            request_unit_id=record.request_unit_id,
            query_input_binding_ref=record.ordinal_input_binding_ref,
            candidate_set_ref=record.candidate_set_ref,
            candidate_set_version=record.candidate_set_version,
            source_tool_call_id=candidate_set.source_tool_call_id,
            search_observation_ref=record.search_observation_ref,
            search_observation_record_schema_version=(
                record.search_observation_record_schema_version
            ),
            search_observation_source_version=(
                candidate_set.search_observation_source_version
            ),
            observation_candidate_ref=record.observation_candidate_ref,
            candidate_source_version=record.candidate_source_version,
            owner_scoped_order_target_ref=(
                record.owner_scoped_order_target_ref
            ),
            order_id=order_id,
            base_task_state_version=record.base_task_state_version,
            result_task_state_version=record.result_task_state_version,
            verified_at=record.selected_at,
            supersedes_verified_target_ref=supersedes,
        )

    @classmethod
    def _cycle2_target_facts(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        task: TaskRecord,
        unit: RequestUnitRecord,
        bindings: tuple[InputBindingV2, ...],
        for_update: bool = False,
    ) -> tuple[
        tuple[Cycle2VerifiedOrderTargetFacts, ...],
        tuple[Cycle2TargetObservationFacts, ...],
    ]:
        owner = owner_scope.customer_id
        candidate_sets = {
            record.candidate_set_id: record
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
                predicates=(
                    P0RecordModel.task_id == task.task_id,
                    P0RecordModel.request_unit_id == unit.request_unit_id,
                ),
                for_update=for_update,
            )
            for record in (decoded.source_record,)
            if type(record) is OrderCandidateSetRecord
        }
        capabilities: list[
            tuple[
                int,
                datetime,
                UUID,
                str,
                UUID,
                UUID,
                str,
            ]
        ] = []
        for _, decoded in cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
            predicates=(
                P0RecordModel.task_id == task.task_id,
                P0RecordModel.request_unit_id == unit.request_unit_id,
            ),
            for_update=for_update,
        ):
            selection = decoded.source_record
            if type(selection) is not OrderCandidateSelectionRecord:
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            candidate_set = candidate_sets.get(selection.candidate_set_ref)
            if candidate_set is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            auto_target = cls._cycle2_auto_target_from_selection(
                record=selection,
                candidate_set=candidate_set,
            )
            if auto_target is not None:
                verified_ref = auto_target.verified_target_ref
                order_id = auto_target.order_id
                input_ref = auto_target.query_input_binding_ref
            else:
                try:
                    verified_ref = UUID(selection.selected_target_ref)
                except ValueError:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                    ) from None
                if verified_ref.version != 4:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                    )
                entries = tuple(
                    entry
                    for entry in candidate_set.ordered_candidates
                    if entry.observation_candidate_ref
                    == selection.observation_candidate_ref
                    and entry.candidate_source_version
                    == selection.candidate_source_version
                )
                if len(entries) != 1:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                    )
                observation_loaded = cls._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
                    logical_identity=(("observation_id", selection.search_observation_ref),),
                    for_update=for_update,
                )
                if (
                    observation_loaded is None
                    or type(observation_loaded[1].source_record)
                    is not SearchOrdersObservation
                ):
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                    )
                observation = cast(
                    SearchOrdersObservation,
                    observation_loaded[1].source_record,
                )
                public_candidates = tuple(
                    candidate
                    for candidate in observation.normalized_value.ordered_candidates
                    if candidate.observation_candidate_ref
                    == entries[0].observation_candidate_ref
                    and candidate.candidate_source_version
                    == entries[0].candidate_source_version
                )
                private_targets = tuple(
                    target
                    for target in observation.candidate_target_bindings
                    if target.observation_candidate_ref
                    == entries[0].observation_candidate_ref
                    and target.candidate_source_version
                    == entries[0].candidate_source_version
                    and target.owner_scoped_order_ref
                    == selection.owner_scoped_order_target_ref
                )
                if len(public_candidates) != 1 or len(private_targets) != 1:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                    )
                order_id = public_candidates[0].public_summary.order_number
                input_ref = selection.ordinal_input_binding_ref
            capabilities.append(
                (
                    selection.result_task_state_version,
                    selection.selected_at,
                    verified_ref,
                    order_id,
                    input_ref,
                    candidate_set.search_observation_ref,
                    candidate_set.search_observation_source_version,
                )
            )
        eligible = tuple(
            capability
            for capability in capabilities
            if capability[0] <= task.state_version
        )
        if not eligible:
            return (), ()
        highest_version = max(item[0] for item in eligible)
        current = tuple(item for item in eligible if item[0] == highest_version)
        if len(current) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        _, _, verified_ref, order_id, input_ref, search_ref, search_version = (
            current[0]
        )
        if input_ref not in {binding.binding_id for binding in bindings}:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        source_ref = search_ref
        source_version = search_version
        order_observations: list[OrderObservation] = []
        for observation_ref in unit.observation_refs:
            loaded = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.OBSERVATION_RECORD,
                logical_identity=(("observation_id", observation_ref),),
                for_update=for_update,
            )
            if loaded is None:
                continue
            observation = loaded[1].source_record
            if type(observation) is not OrderObservation:
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            if observation.source_resource_ref == order_id:
                order_observations.append(observation)
        if len(order_observations) > 1:
            order_observations.sort(
                key=lambda record: (record.recorded_at, str(record.observation_id))
            )
        if order_observations:
            latest = order_observations[-1]
            source_ref = latest.observation_id
            source_version = latest.source_version
        target = Cycle2VerifiedOrderTargetFacts(
            verified_target_ref=verified_ref,
            private_owner_scope_ref=owner,
            owner_customer_id=owner,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            task_state_version=task.state_version,
            order_id=order_id,
            source_observation_ref=source_ref,
            source_observation_version=source_version,
            input_binding_refs=(input_ref,),
            superseded_by=None,
        )
        observation_facts = Cycle2TargetObservationFacts(
            observation_ref=source_ref,
            observation_version=source_version,
            private_owner_scope_ref=owner,
            owner_customer_id=owner,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            task_state_version=task.state_version,
            verified_target_ref=verified_ref,
            input_binding_refs=(input_ref,),
            superseded_by=None,
        )
        return (target,), (observation_facts,)

    def _cycle2_session_is_authorized(
        self,
        *,
        session_ref_hash: str,
        owner_customer_id: str,
    ) -> bool:
        return (
            type(session_ref_hash) is str
            and bool(session_ref_hash)
            and self._cycle2_session_owners.get(session_ref_hash)
            == owner_customer_id
        )

    @classmethod
    def _cycle2_current_session_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        session_ref_hash: str,
        trusted_now: datetime,
        for_update: bool = False,
    ) -> Cycle2CurrentSessionTaskClosure | None:
        owner = owner_scope.customer_id
        link_rows = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            for_update=for_update,
        )
        active_links = tuple(
            cast(ConversationTaskLinkRecord, decoded.source_record)
            for _, decoded in link_rows
            if type(decoded.source_record) is ConversationTaskLinkRecord
            and decoded.source_record.ended_at is None
        )
        if not active_links:
            return None
        if len(active_links) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        link = active_links[0]
        conversation = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            logical_identity=(("conversation_id", link.conversation_id),),
            for_update=for_update,
        )
        unit_rows = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            predicates=(P0RecordModel.task_id == link.task_id,),
            for_update=for_update,
        )
        if conversation is None or len(unit_rows) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        unit_record = unit_rows[0][1].source_record
        if type(unit_record) is not RequestUnitRecord:
            raise _integrity(
                P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
            )
        current = cls._cycle2_current_task_unit_bindings(
            session,
            owner_scope=owner_scope,
            task_id=link.task_id,
            request_unit_id=unit_record.request_unit_id,
            for_update=for_update,
        )
        if current is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        task, unit, bindings = current
        candidate_rows = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
            predicates=(
                P0RecordModel.task_id == task.task_id,
                P0RecordModel.request_unit_id == unit.request_unit_id,
            ),
            for_update=for_update,
        )
        all_sets = tuple(
            cast(OrderCandidateSetRecord, decoded.source_record)
            for _, decoded in candidate_rows
            if type(decoded.source_record) is OrderCandidateSetRecord
        )
        superseded_refs = tuple(
            cast(UUID, record.supersedes_candidate_set_ref)
            for record in all_sets
            if record.supersedes_candidate_set_ref is not None
        )
        current_sets = tuple(
            record
            for record in all_sets
            if record.candidate_set_id not in set(superseded_refs)
            and (
                record.result_task_state_version == task.state_version
                or record.selection_expected_task_state_version
                == task.state_version
            )
        )
        if len(current_sets) > 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        observations: list[SearchOrdersObservation] = []
        auto_targets: list[OrderCandidateAutoTargetRecord] = []
        if current_sets:
            candidate_set = current_sets[0]
            loaded_observation = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
                logical_identity=(
                    ("observation_id", candidate_set.search_observation_ref),
                ),
                for_update=for_update,
            )
            if (
                loaded_observation is None
                or type(loaded_observation[1].source_record)
                is not SearchOrdersObservation
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            observations.append(
                cast(
                    SearchOrdersObservation,
                    loaded_observation[1].source_record,
                )
            )
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
                predicates=(
                    P0RecordModel.task_id == task.task_id,
                    P0RecordModel.request_unit_id == unit.request_unit_id,
                ),
                for_update=for_update,
            ):
                selection = decoded.source_record
                if (
                    type(selection) is OrderCandidateSelectionRecord
                    and selection.candidate_set_ref
                    == candidate_set.candidate_set_id
                ):
                    auto = cls._cycle2_auto_target_from_selection(
                        record=selection,
                        candidate_set=candidate_set,
                    )
                    if auto is not None:
                        auto_targets.append(auto)
        selections = tuple(
            cast(OrderCandidateSelectionRecord, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
                predicates=(
                    P0RecordModel.task_id == task.task_id,
                    P0RecordModel.request_unit_id == unit.request_unit_id,
                ),
                for_update=for_update,
            )
            if type(decoded.source_record) is OrderCandidateSelectionRecord
            and cls._cycle2_parse_auto_target_marker(
                decoded.source_record.selected_target_ref
            ) is None
        )
        return Cycle2CurrentSessionTaskClosure(
            owner_scope=owner_scope,
            session_ref_hash=session_ref_hash,
            conversation_record=cast(
                ConversationRecord, conversation[1].source_record
            ),
            current_conversation_task_link_record=link,
            current_task_record=task,
            current_request_unit_record=unit,
            current_input_binding_records=bindings,
            current_candidate_set_records=current_sets,
            current_search_observation_records=tuple(observations),
            current_auto_target_records=tuple(auto_targets),
            superseded_candidate_set_refs=superseded_refs,
            existing_selection_records=selections,
            trusted_now=trusted_now,
        )

    @_bounded_database_failures
    async def load_current_session_task_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        session_ref_hash: str,
        trusted_now: datetime,
    ) -> Cycle2CurrentSessionTaskClosure | None:
        if not self._cycle2_session_is_authorized(
            session_ref_hash=session_ref_hash,
            owner_customer_id=owner_scope.customer_id,
        ):
            return None
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                )
                return self._cycle2_current_session_closure(
                    session,
                    owner_scope=owner_scope,
                    session_ref_hash=session_ref_hash,
                    trusted_now=trusted_now,
                )

    @_bounded_database_failures
    async def insert_cycle2_run_root_if_current(
        self,
        command: CreateCycle2RunRootCommand,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        if not self._cycle2_session_is_authorized(
            session_ref_hash=command.session_ref_hash,
            owner_customer_id=owner,
        ):
            return Cycle2WriteResult.NOT_APPLICABLE
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_current_session_closure(
                    session,
                    owner_scope=command.owner_scope,
                    session_ref_hash=command.session_ref_hash,
                    trusted_now=command.user_message_record.received_at,
                    for_update=True,
                )
                if current != command.current_session_closure:
                    raise _Cycle2NotApplicable() from None
                envelopes = []
                if current is None:
                    envelopes.append(
                        self._cycle2_encode(
                            P0RecordCode.CONVERSATION_RECORD,
                            command.conversation_record,
                        )
                    )
                else:
                    loaded_conversation = self._cycle2_row(
                        session,
                        owner_customer_id=owner,
                        record_code=P0RecordCode.CONVERSATION_RECORD,
                        logical_identity=((
                            "conversation_id",
                            command.conversation_record.conversation_id,
                        ),),
                        for_update=True,
                    )
                    if (
                        loaded_conversation is None
                        or loaded_conversation[1].source_record
                        != command.conversation_record
                    ):
                        raise _Cycle2NotApplicable() from None
                envelopes.extend(
                    (
                        self._cycle2_encode(
                            P0RecordCode.MESSAGE_RECORD,
                            command.user_message_record,
                        ),
                        self._cycle2_encode(
                            P0RecordCode.AGENT_RUN_RECORD,
                            command.created_run_record,
                        ),
                    )
                )
                if command.active_run_task_link_record is not None:
                    envelopes.append(
                        self._cycle2_encode(
                            P0RecordCode.RUN_TASK_LINK_RECORD,
                            command.active_run_task_link_record,
                        )
                    )
                self._cycle2_insert(
                    session,
                    tuple(envelopes),
                    owner_customer_id=owner,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def start_cycle2_run_if_created(
        self,
        command: StartCycle2RunCommand,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.AGENT_RUN_RECORD,
                    logical_identity=((
                        "run_id",
                        command.expected_created_run_record.run_id,
                    ),),
                    for_update=True,
                )
                if loaded is None:
                    raise _Cycle2NotApplicable() from None
                if command.expected_active_run_task_link_record is not None:
                    link = command.expected_active_run_task_link_record
                    loaded_link = self._cycle2_row(
                        session,
                        owner_customer_id=owner,
                        record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
                        logical_identity=(
                            ("run_id", link.run_id),
                            ("task_id", link.task_id),
                        ),
                        for_update=True,
                    )
                    if loaded_link is None or loaded_link[1].source_record != link:
                        raise _Cycle2NotApplicable() from None
                self._cycle2_replace(
                    session,
                    loaded[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_created_run_record,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.AGENT_RUN_RECORD,
                        command.next_running_run_record,
                    ),
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def create_cycle2_initial_task_graph_if_current(
        self,
        command: CreateCycle2InitialTaskGraphCommand,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        graph = command.reducer_decision.task_graph
        try:
            with self.session_factory.begin() as session:
                roots = []
                for code, identity, expected in (
                    (
                        P0RecordCode.CONVERSATION_RECORD,
                        (("conversation_id", command.expected_conversation_record.conversation_id),),
                        command.expected_conversation_record,
                    ),
                    (
                        P0RecordCode.MESSAGE_RECORD,
                        (("message_id", command.expected_user_message_record.message_id),),
                        command.expected_user_message_record,
                    ),
                    (
                        P0RecordCode.AGENT_RUN_RECORD,
                        (("run_id", command.expected_running_run_record.run_id),),
                        command.expected_running_run_record,
                    ),
                ):
                    loaded = self._cycle2_row(
                        session,
                        owner_customer_id=owner,
                        record_code=code,
                        logical_identity=identity,
                        for_update=True,
                    )
                    if loaded is None or loaded[1].source_record != expected:
                        raise _Cycle2NotApplicable() from None
                    roots.append(loaded)
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode(
                            P0RecordCode.TASK_RECORD,
                            graph.task,
                        ),
                        self._cycle2_encode(
                            P0RecordCode.REQUEST_UNIT_RECORD,
                            graph.request_unit,
                        ),
                        self._cycle2_encode_input_binding(
                            graph.input_binding,
                            request_unit_id=graph.request_unit.request_unit_id,
                        ),
                        self._cycle2_encode(
                            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
                            command.conversation_task_link_record,
                        ),
                        self._cycle2_encode(
                            P0RecordCode.RUN_TASK_LINK_RECORD,
                            command.active_run_task_link_record,
                        ),
                        *(
                            self._cycle2_encode(
                                P0RecordCode.TRACE_EVENT_RECORD,
                                trace,
                            )
                            for trace in command.ordinary_trace_records
                        ),
                    ),
                    owner_customer_id=owner,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def finalize_cycle2_run_if_current(
        self,
        command: FinalizeCycle2RunCommand,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                run = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.AGENT_RUN_RECORD,
                    logical_identity=((
                        "run_id",
                        command.expected_running_run_record.run_id,
                    ),),
                    for_update=True,
                )
                if run is None:
                    raise _Cycle2NotApplicable() from None
                link_row = None
                if command.expected_active_run_task_link_record is not None:
                    link = command.expected_active_run_task_link_record
                    link_row = self._cycle2_row(
                        session,
                        owner_customer_id=owner,
                        record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
                        logical_identity=(
                            ("run_id", link.run_id),
                            ("task_id", link.task_id),
                        ),
                        for_update=True,
                    )
                    if link_row is None or link_row[1].source_record != link:
                        raise _Cycle2NotApplicable() from None
                    current = self._cycle2_current_task_unit_bindings(
                        session,
                        owner_scope=command.owner_scope,
                        task_id=link.task_id,
                        request_unit_id=cast(
                            RequestUnitRecord,
                            command.current_request_unit_record,
                        ).request_unit_id,
                        for_update=True,
                    )
                    if current is None or current[:2] != (
                        command.current_task_record,
                        command.current_request_unit_record,
                    ):
                        raise _Cycle2NotApplicable() from None
                self._cycle2_replace(
                    session,
                    run[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_running_run_record,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.AGENT_RUN_RECORD,
                        command.terminal_run_record,
                    ),
                )
                if link_row is not None:
                    self._cycle2_replace(
                        session,
                        link_row[0],
                        owner_customer_id=owner,
                        expected_record=cast(
                            RunTaskLinkRecordV2,
                            command.expected_active_run_task_link_record,
                        ),
                        next_envelope=self._cycle2_encode(
                            P0RecordCode.RUN_TASK_LINK_RECORD,
                            cast(
                                RunTaskLinkRecordV2,
                                command.terminal_run_task_link_record,
                            ),
                        ),
                    )
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode(
                            P0RecordCode.MESSAGE_RECORD,
                            command.assistant_message_record,
                        ),
                        *(
                            self._cycle2_encode(
                                P0RecordCode.TRACE_EVENT_RECORD,
                                trace,
                            )
                            for trace in command.ordinary_trace_records
                        ),
                    ),
                    owner_customer_id=owner,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @classmethod
    def _cycle2_exact_run_evidence(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> Cycle2ExactRunEvidenceClosure | None:
        owner = owner_scope.customer_id
        run_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", run_id),),
        )
        if run_loaded is None:
            return None
        run = run_loaded[1].source_record
        if type(run) is not AgentRunRecordV2:
            raise _integrity(
                P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
            )
        conversation_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            logical_identity=(("conversation_id", run.conversation_id),),
        )
        if conversation_loaded is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        message_rows = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.MESSAGE_RECORD,
            predicates=(P0RecordModel.conversation_id == run.conversation_id,),
        )
        messages = tuple(
            cast(MessageRecord, decoded.source_record)
            for _, decoded in message_rows
            if type(decoded.source_record) is MessageRecord
            and (
                decoded.source_record.received_at == run.started_at
                or (
                    run.completed_at is not None
                    and decoded.source_record.received_at == run.completed_at
                )
            )
        )
        links = tuple(
            cast(RunTaskLinkRecordV2, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
                predicates=(P0RecordModel.run_id == run_id,),
            )
            if type(decoded.source_record) is RunTaskLinkRecordV2
        )
        tasks: list[TaskRecord] = []
        units: list[RequestUnitRecord] = []
        bindings: list[InputBindingV2] = []
        for link in links:
            unit_rows = cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                predicates=(P0RecordModel.task_id == link.task_id,),
            )
            if len(unit_rows) != 1:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            unit = unit_rows[0][1].source_record
            if type(unit) is not RequestUnitRecord:
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            current = cls._cycle2_current_task_unit_bindings(
                session,
                owner_scope=owner_scope,
                task_id=link.task_id,
                request_unit_id=unit.request_unit_id,
            )
            if current is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            task, current_unit, current_bindings = current
            tasks.append(task)
            units.append(current_unit)
            bindings.extend(current_bindings)
        traces = tuple(
            cast(TraceEventV2, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.TRACE_EVENT_RECORD,
                predicates=(P0RecordModel.run_id == run_id,),
            )
            if type(decoded.source_record) is TraceEventV2
        )
        terminal_result = None
        if run.status is AgentRunStatusV2.COMPLETED:
            assistants = tuple(
                message
                for message in messages
                if message.direction is MessageDirection.ASSISTANT
            )
            stopped = tuple(
                trace
                for trace in traces
                if trace.event_type is TraceEventType.RUN_STOPPED
                and trace.user_outcome is not None
            )
            if len(assistants) != 1 or len(stopped) != 1:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                )
            terminal_result = AgentRunResult(
                run_id=run.run_id,
                outcome=cast(Any, stopped[0].user_outcome),
                message=assistants[0].content,
            )
        return Cycle2ExactRunEvidenceClosure(
            owner_scope=owner_scope,
            conversation_record=cast(
                ConversationRecord, conversation_loaded[1].source_record
            ),
            run_record=run,
            message_records=tuple(
                sorted(messages, key=lambda record: (record.received_at, str(record.message_id)))
            ),
            run_task_link_records=links,
            task_records=tuple(tasks),
            request_unit_records=tuple(units),
            input_binding_records=tuple(bindings),
            trace_records=tuple(
                sorted(traces, key=lambda record: (record.occurred_at, str(record.trace_event_id)))
            ),
            terminal_result=terminal_result,
        )

    @_bounded_database_failures
    async def load_cycle2_exact_run_evidence_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> Cycle2ExactRunEvidenceClosure | None:
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                )
                return self._cycle2_exact_run_evidence(
                    session,
                    owner_scope=owner_scope,
                    run_id=run_id,
                )

    @classmethod
    def _cycle2_continuation_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        message_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_now: datetime,
        for_update: bool = False,
    ) -> ContinuationInputBindingReadClosure | None:
        owner = owner_scope.customer_id
        roots: list[BaseModel] = []
        for code, identity, expected_type in (
            (
                P0RecordCode.CONVERSATION_RECORD,
                (("conversation_id", conversation_id),),
                ConversationRecord,
            ),
            (
                P0RecordCode.MESSAGE_RECORD,
                (("message_id", message_id),),
                MessageRecord,
            ),
        ):
            loaded = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=code,
                logical_identity=identity,
                for_update=for_update,
            )
            if loaded is None:
                return None
            record = loaded[1].source_record
            if type(record) is not expected_type:
                raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
            roots.append(record)
        links = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            predicates=(
                P0RecordModel.conversation_id == conversation_id,
                P0RecordModel.task_id == task_id,
            ),
            for_update=for_update,
        )
        if not links:
            return None
        if len(links) != 1 or type(links[0][1].source_record) is not ConversationTaskLinkRecord:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        current = cls._cycle2_current_task_unit_bindings(
            session,
            owner_scope=owner_scope,
            task_id=task_id,
            request_unit_id=request_unit_id,
            for_update=for_update,
        )
        if current is None:
            return None
        task, unit, bindings = current
        return ContinuationInputBindingReadClosure(
            owner_scope=owner_scope,
            trusted_conversation_record=cast(ConversationRecord, roots[0]),
            current_conversation_task_link_record=cast(
                ConversationTaskLinkRecord, links[0][1].source_record
            ),
            saved_user_message_record=cast(MessageRecord, roots[1]),
            current_task_record=task,
            current_request_unit_record=unit,
            current_input_binding_records=bindings,
            trusted_now=trusted_now,
        )

    @_bounded_database_failures
    async def load_continuation_input_binding_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        message_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_now: datetime,
    ) -> ContinuationInputBindingReadClosure | None:
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                return self._cycle2_continuation_closure(
                    session,
                    owner_scope=owner_scope,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    task_id=task_id,
                    request_unit_id=request_unit_id,
                    trusted_now=trusted_now,
                )

    @_bounded_database_failures
    async def apply_continuation_input_binding_if_current(
        self,
        command: ApplyContinuationInputBindingV2Command,
    ) -> Cycle2WriteResult:
        closure = command.loaded_closure
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_continuation_closure(
                    session,
                    owner_scope=closure.owner_scope,
                    conversation_id=closure.trusted_conversation_record.conversation_id,
                    message_id=closure.saved_user_message_record.message_id,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=closure.current_request_unit_record.request_unit_id,
                    trusted_now=closure.trusted_now,
                    for_update=True,
                )
                if current != closure:
                    raise _Cycle2NotApplicable() from None
                owner = closure.owner_scope.customer_id
                task_row = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=(("task_id", closure.current_task_record.task_id),),
                    for_update=True,
                )
                unit_row = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                    logical_identity=(("request_unit_id", closure.current_request_unit_record.request_unit_id),),
                    for_update=True,
                )
                if task_row is None or unit_row is None:
                    raise _Cycle2NotApplicable() from None
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode_input_binding(
                            command.new_input_binding_record,
                            request_unit_id=closure.current_request_unit_record.request_unit_id,
                        ),
                    ),
                    owner_customer_id=owner,
                )
                self._cycle2_replace(
                    session,
                    task_row[0],
                    owner_customer_id=owner,
                    expected_record=closure.current_task_record,
                    next_envelope=self._cycle2_encode(P0RecordCode.TASK_RECORD, command.next_task_record),
                )
                self._cycle2_replace(
                    session,
                    unit_row[0],
                    owner_customer_id=owner,
                    expected_record=closure.current_request_unit_record,
                    next_envelope=self._cycle2_encode(P0RecordCode.REQUEST_UNIT_RECORD, command.next_request_unit_record),
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def load_initial_tool_call_v2_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_read_at: datetime,
    ) -> InitialToolCallV2ReadClosure | None:
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                current = self._cycle2_current_task_unit_bindings(
                    session,
                    owner_scope=owner_scope,
                    task_id=task_id,
                    request_unit_id=request_unit_id,
                )
                if current is None:
                    return None
                task, unit, bindings = current
                targets, target_observations = self._cycle2_target_facts(
                    session,
                    owner_scope=owner_scope,
                    task=task,
                    unit=unit,
                    bindings=bindings,
                )
                return InitialToolCallV2ReadClosure(
                    owner_scope=owner_scope,
                    current_task_record=task,
                    current_request_unit_record=unit,
                    current_input_binding_records=bindings,
                    current_verified_order_targets=targets,
                    current_target_observations=target_observations,
                    trusted_read_at=trusted_read_at,
                )

    @_bounded_database_failures
    async def insert_initial_tool_call_v2_if_current(
        self,
        command: CreateToolCallV2Command,
    ) -> Cycle2WriteResult:
        closure = command.loaded_closure
        owner = closure.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_current_task_unit_bindings(
                    session,
                    owner_scope=closure.owner_scope,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=closure.current_request_unit_record.request_unit_id,
                    for_update=True,
                )
                if current != (
                    closure.current_task_record,
                    closure.current_request_unit_record,
                    closure.current_input_binding_records,
                ):
                    raise _Cycle2NotApplicable() from None
                gate_id = command.created_record.gate_decision_id
                existing = self._cycle2_rows(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TOOL_CALL_RECORD,
                    predicates=(P0RecordModel.task_id == closure.current_task_record.task_id,),
                    for_update=True,
                )
                if any(
                    type(decoded.source_record) is ToolCallRecordV2
                    and decoded.source_record.gate_decision_id == gate_id
                    for _, decoded in existing
                ):
                    raise _Cycle2ProjectionConflict() from None
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode(
                            P0RecordCode.GATE_DECISION_RECORD,
                            command.gate_decision,
                        ),
                        self._cycle2_encode(
                            P0RecordCode.TOOL_CALL_RECORD,
                            command.created_record,
                            logical_children=command.created_record.attempts,
                        ),
                    ),
                    owner_customer_id=owner,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def finalize_tool_attempt_if_current(
        self,
        command: FinalizeToolAttemptV2Command,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TOOL_CALL_RECORD,
                    logical_identity=(("tool_call_id", command.expected_running_record.tool_call_id),),
                    for_update=True,
                )
                if loaded is None:
                    raise _Cycle2NotApplicable() from None
                decisions = tuple(
                    child
                    for child in loaded[1].logical_children
                    if type(child) is ToolRetryRecoveryDecisionRecordV2
                )
                if len(decisions) > 1:
                    raise _integrity(
                        P0PersistenceIntegrityCategory.CHILD_MISMATCH
                    )
                expected_children: tuple[BaseModel, ...] = (
                    command.expected_running_record.attempts
                    if not decisions
                    else (
                        command.expected_running_record.attempts[0],
                        decisions[0],
                        *command.expected_running_record.attempts[1:],
                    )
                )
                next_children: tuple[BaseModel, ...] = (
                    command.next_record.attempts
                    if not decisions
                    else (
                        command.next_record.attempts[0],
                        decisions[0],
                        *command.next_record.attempts[1:],
                    )
                )
                self._cycle2_replace(
                    session,
                    loaded[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_running_record,
                    expected_children=expected_children,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.TOOL_CALL_RECORD,
                        command.next_record,
                        logical_children=next_children,
                    ),
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @classmethod
    def _cycle2_retry_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        tool_call_id: UUID,
        trusted_read_at: datetime,
        run_budget_policy: Cycle2RunBudgetPolicyEvidence,
        for_update: bool = False,
    ) -> ToolRetryRecoveryReadClosureV2 | None:
        owner = owner_scope.customer_id
        loaded_tool = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.TOOL_CALL_RECORD,
            logical_identity=(("tool_call_id", tool_call_id),),
            for_update=for_update,
        )
        if loaded_tool is None:
            return None
        tool = loaded_tool[1].source_record
        if type(tool) is not ToolCallRecordV2:
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        current = cls._cycle2_current_task_unit_bindings(
            session,
            owner_scope=owner_scope,
            task_id=tool.task_id,
            request_unit_id=tool.request_unit_id,
            for_update=for_update,
        )
        if current is None:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        task, unit, bindings = current
        run_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", tool.run_id),),
            for_update=for_update,
        )
        link_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            logical_identity=(("run_id", tool.run_id), ("task_id", tool.task_id)),
            for_update=for_update,
        )
        if run_loaded is None or link_loaded is None:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        run = run_loaded[1].source_record
        link = link_loaded[1].source_record
        if type(run) is not AgentRunRecordV2 or type(link) is not RunTaskLinkRecordV2:
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        decisions = tuple(
            child
            for child in loaded_tool[1].logical_children
            if type(child) is ToolRetryRecoveryDecisionRecordV2
        )
        attempts = tuple(
            child
            for child in loaded_tool[1].logical_children
            if type(child) is ToolAttemptRecordV2
        )
        if attempts != tool.attempts or len(decisions) > 1:
            raise _integrity(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        return ToolRetryRecoveryReadClosureV2(
            owner_scope=owner_scope,
            active_run_record=run,
            active_run_task_link_record=link,
            current_task_record=task,
            current_request_unit_record=unit,
            current_input_binding_records=bindings,
            tool_call_record=tool,
            recovery_decision_records=cast(
                tuple[ToolRetryRecoveryDecisionRecordV2, ...], decisions
            ),
            trusted_read_at=trusted_read_at,
            run_budget_policy=run_budget_policy,
        )

    @_bounded_database_failures
    async def load_tool_retry_recovery_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        tool_call_id: UUID,
    ) -> ToolRetryRecoveryReadClosureV2 | None:
        trusted_now = self._cycle2_trusted_now()
        policy = self._cycle2_run_budget_policy
        if policy is None:
            raise _integrity(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                return self._cycle2_retry_closure(
                    session,
                    owner_scope=owner_scope,
                    tool_call_id=tool_call_id,
                    trusted_read_at=trusted_now,
                    run_budget_policy=policy,
                )

    def _cycle2_append_attempt(
        self,
        *,
        loaded_closure: ToolRetryRecoveryReadClosureV2,
        append_command: AppendToolAttemptV2Command,
        recovery_decision: ToolRetryRecoveryDecisionRecordV2 | None,
    ) -> Cycle2ReadDispatchGrant:
        owner_scope = loaded_closure.owner_scope
        owner = owner_scope.customer_id
        policy = self._cycle2_run_budget_policy
        if policy is None:
            return Cycle2ReadDispatchGrant(
                write_result=Cycle2DispatchFenceWriteResult.NOT_APPLICABLE
            )
        trusted_now = self._cycle2_trusted_now()
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_retry_closure(
                    session,
                    owner_scope=owner_scope,
                    tool_call_id=loaded_closure.tool_call_record.tool_call_id,
                    trusted_read_at=trusted_now,
                    run_budget_policy=policy,
                    for_update=True,
                )
                if (
                    current.owner_scope != loaded_closure.owner_scope
                    or current.active_run_record
                    != loaded_closure.active_run_record
                    or current.active_run_task_link_record
                    != loaded_closure.active_run_task_link_record
                    or current.current_task_record
                    != loaded_closure.current_task_record
                    or current.current_request_unit_record
                    != loaded_closure.current_request_unit_record
                    or current.current_input_binding_records
                    != loaded_closure.current_input_binding_records
                    or current.tool_call_record
                    != loaded_closure.tool_call_record
                    or current.recovery_decision_records
                    != loaded_closure.recovery_decision_records
                    or current.run_budget_policy
                    != loaded_closure.run_budget_policy
                    or current.trusted_read_at < loaded_closure.trusted_read_at
                ):
                    raise _Cycle2NotApplicable() from None
                if append_command.expected_record != current.tool_call_record:
                    raise _Cycle2NotApplicable() from None
                remaining = current.remaining_run_time_budget_ms()
                if remaining < 1:
                    raise _Cycle2NotApplicable() from None
                loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TOOL_CALL_RECORD,
                    logical_identity=(("tool_call_id", current.tool_call_record.tool_call_id),),
                    for_update=True,
                )
                if loaded is None:
                    raise _Cycle2NotApplicable() from None
                attempts = append_command.next_running_record.attempts
                children: tuple[BaseModel, ...] = (
                    attempts
                    if recovery_decision is None
                    else (attempts[0], recovery_decision, *attempts[1:])
                )
                self._cycle2_replace(
                    session,
                    loaded[0],
                    owner_customer_id=owner,
                    expected_record=current.tool_call_record,
                    expected_children=loaded[1].logical_children,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.TOOL_CALL_RECORD,
                        append_command.next_running_record,
                        logical_children=children,
                    ),
                )
        except _Cycle2NotApplicable:
            return Cycle2ReadDispatchGrant(
                write_result=Cycle2DispatchFenceWriteResult.NOT_APPLICABLE
            )
        except _Cycle2ProjectionConflict:
            return Cycle2ReadDispatchGrant(
                write_result=Cycle2DispatchFenceWriteResult.PROJECTION_CONFLICT
            )
        return Cycle2ReadDispatchGrant(
            write_result=Cycle2DispatchFenceWriteResult.APPLIED,
            tool_call_id=append_command.next_running_record.tool_call_id,
            attempt_no=append_command.started_attempt.attempt_no,
            trusted_fenced_at=trusted_now,
            effective_timeout_ms=min(500, remaining),
        )

    async def append_initial_tool_attempt_if_current(
        self,
        command: AppendInitialToolAttemptV2Command,
    ) -> Cycle2ReadDispatchGrant:
        return self._cycle2_append_attempt(
            loaded_closure=command.loaded_closure,
            append_command=command.attempt_append_command,
            recovery_decision=None,
        )

    async def append_recovered_tool_attempt_if_current(
        self,
        command: AppendRecoveredToolAttemptV2Command,
    ) -> Cycle2ReadDispatchGrant:
        return self._cycle2_append_attempt(
            loaded_closure=command.loaded_closure,
            append_command=command.attempt_append_command,
            recovery_decision=command.recovery_decision_record,
        )

    def _cycle2_recovery_is_applied(
        self,
        session: Session,
        *,
        loaded_closure: ToolRetryRecoveryReadClosureV2,
        terminal_record: ToolCallRecordV2,
        recovery_decision: ToolRetryRecoveryDecisionRecordV2 | None,
        for_update: bool,
    ) -> bool:
        persisted = self._cycle2_row(
            session,
            owner_customer_id=loaded_closure.owner_scope.customer_id,
            record_code=P0RecordCode.TOOL_CALL_RECORD,
            logical_identity=((
                "tool_call_id",
                loaded_closure.tool_call_record.tool_call_id,
            ),),
            for_update=for_update,
        )
        desired_children: tuple[BaseModel, ...] = (
            *terminal_record.attempts,
            *((recovery_decision,) if recovery_decision is not None else ()),
        )
        return persisted is not None and (
            persisted[1].source_record == terminal_record
            and persisted[1].logical_children == desired_children
        )

    def _cycle2_finalize_recovery_in_transaction(
        self,
        session: Session,
        *,
        loaded_closure: ToolRetryRecoveryReadClosureV2,
        terminal_record: ToolCallRecordV2,
        recovery_decision: ToolRetryRecoveryDecisionRecordV2 | None,
    ) -> None:
        policy = self._cycle2_run_budget_policy
        if policy is None:
            raise _Cycle2NotApplicable() from None
        trusted_now = self._cycle2_trusted_now()
        owner = loaded_closure.owner_scope.customer_id
        desired_children: tuple[BaseModel, ...] = (
            *terminal_record.attempts,
            *((recovery_decision,) if recovery_decision is not None else ()),
        )
        if self._cycle2_recovery_is_applied(
            session,
            loaded_closure=loaded_closure,
            terminal_record=terminal_record,
            recovery_decision=recovery_decision,
            for_update=True,
        ):
            raise _Cycle2AlreadyApplied() from None
        current = self._cycle2_retry_closure(
            session,
            owner_scope=loaded_closure.owner_scope,
            tool_call_id=loaded_closure.tool_call_record.tool_call_id,
            trusted_read_at=trusted_now,
            run_budget_policy=policy,
            for_update=True,
        )
        if current != loaded_closure:
            raise _Cycle2NotApplicable() from None
        loaded = self._cycle2_row(
            session,
            owner_customer_id=loaded_closure.owner_scope.customer_id,
            record_code=P0RecordCode.TOOL_CALL_RECORD,
            logical_identity=(("tool_call_id", current.tool_call_record.tool_call_id),),
            for_update=True,
        )
        if loaded is None:
            raise _Cycle2NotApplicable() from None
        self._cycle2_replace(
            session,
            loaded[0],
            owner_customer_id=loaded_closure.owner_scope.customer_id,
            expected_record=current.tool_call_record,
            expected_children=loaded[1].logical_children,
            next_envelope=self._cycle2_encode(
                P0RecordCode.TOOL_CALL_RECORD,
                terminal_record,
                logical_children=desired_children,
            ),
        )

    def _cycle2_finalize_recovery(
        self,
        *,
        loaded_closure: ToolRetryRecoveryReadClosureV2,
        terminal_record: ToolCallRecordV2,
        recovery_decision: ToolRetryRecoveryDecisionRecordV2 | None,
    ) -> Cycle2WriteResult:
        try:
            with self.session_factory.begin() as session:
                self._cycle2_finalize_recovery_in_transaction(
                    session,
                    loaded_closure=loaded_closure,
                    terminal_record=terminal_record,
                    recovery_decision=recovery_decision,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        except _Cycle2AlreadyApplied:
            return Cycle2WriteResult.ALREADY_APPLIED
        return Cycle2WriteResult.APPLIED

    async def finalize_created_tool_recovery_if_current(
        self,
        command: FinalizeCreatedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        return self._cycle2_finalize_recovery(
            loaded_closure=command.loaded_closure,
            terminal_record=command.terminal_tool_call_record,
            recovery_decision=None,
        )

    async def finalize_unfinished_tool_recovery_if_current(
        self,
        command: FinalizeUnfinishedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        return self._cycle2_finalize_recovery(
            loaded_closure=command.loaded_closure,
            terminal_record=command.terminal_tool_call_record,
            recovery_decision=command.recovery_decision_record,
        )

    async def finalize_budget_exhausted_tool_recovery_if_current(
        self,
        command: FinalizeBudgetExhaustedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        return self._cycle2_finalize_recovery(
            loaded_closure=command.loaded_closure,
            terminal_record=command.terminal_tool_call_record,
            recovery_decision=command.recovery_decision_record,
        )

    @_bounded_database_failures
    async def save_order_observation_if_current(
        self,
        command: SaveOrderObservationV2Command,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_current_task_unit_bindings(
                    session,
                    owner_scope=command.owner_scope,
                    task_id=command.expected_task_record.task_id,
                    request_unit_id=(
                        command.expected_request_unit_record.request_unit_id
                    ),
                    for_update=True,
                )
                if current is None or current[:2] != (
                    command.expected_task_record,
                    command.expected_request_unit_record,
                ):
                    raise _Cycle2NotApplicable() from None
                tool_loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TOOL_CALL_RECORD,
                    logical_identity=((
                        "tool_call_id",
                        command.source_tool_call_record.tool_call_id,
                    ),),
                    for_update=True,
                )
                task_loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=((
                        "task_id",
                        command.expected_task_record.task_id,
                    ),),
                    for_update=True,
                )
                unit_loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                    logical_identity=((
                        "request_unit_id",
                        command.expected_request_unit_record.request_unit_id,
                    ),),
                    for_update=True,
                )
                if (
                    tool_loaded is None
                    or task_loaded is None
                    or unit_loaded is None
                    or tool_loaded[1].source_record
                    != command.source_tool_call_record
                ):
                    raise _Cycle2NotApplicable() from None
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode(
                            P0RecordCode.OBSERVATION_RECORD,
                            command.observation_record,
                            external_references=(
                                _external_reference(
                                    "source_tool_call_id",
                                    P0RecordCode.TOOL_CALL_RECORD,
                                    "tool_call_id",
                                    command.source_tool_call_record.tool_call_id,
                                ),
                                _external_reference(
                                    "source_run_id",
                                    P0RecordCode.AGENT_RUN_RECORD,
                                    "run_id",
                                    command.source_tool_call_record.run_id,
                                ),
                                _external_reference(
                                    "source_task_id",
                                    P0RecordCode.TASK_RECORD,
                                    "task_id",
                                    command.source_tool_call_record.task_id,
                                ),
                                _external_reference(
                                    "source_request_unit_id",
                                    P0RecordCode.REQUEST_UNIT_RECORD,
                                    "request_unit_id",
                                    command.source_tool_call_record.request_unit_id,
                                ),
                            ),
                        ),
                    ),
                    owner_customer_id=owner,
                )
                self._cycle2_replace(
                    session,
                    task_loaded[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_task_record,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.TASK_RECORD,
                        command.next_task_record,
                    ),
                )
                self._cycle2_replace(
                    session,
                    unit_loaded[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_request_unit_record,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.REQUEST_UNIT_RECORD,
                        command.next_request_unit_record,
                    ),
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def save_shipment_observation_if_current(
        self,
        command: SaveShipmentObservationV2Command,
    ) -> Cycle2WriteResult:
        owner = command.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_current_task_unit_bindings(
                    session,
                    owner_scope=command.owner_scope,
                    task_id=command.expected_task_record.task_id,
                    request_unit_id=command.expected_request_unit_record.request_unit_id,
                    for_update=True,
                )
                if current is None or current[:2] != (
                    command.expected_task_record,
                    command.expected_request_unit_record,
                ):
                    raise _Cycle2NotApplicable() from None
                tool_loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TOOL_CALL_RECORD,
                    logical_identity=(("tool_call_id", command.source_tool_call_record.tool_call_id),),
                    for_update=True,
                )
                if (
                    tool_loaded is None
                    or tool_loaded[1].source_record != command.source_tool_call_record
                ):
                    raise _Cycle2NotApplicable() from None
                observations = self._cycle2_rows(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
                    predicates=(
                        P0RecordModel.task_id == command.expected_task_record.task_id,
                        P0RecordModel.request_unit_id
                        == command.expected_request_unit_record.request_unit_id,
                    ),
                    for_update=True,
                )
                records = tuple(
                    decoded.source_record for _, decoded in observations
                )
                if any(type(record) is not ShipmentObservation for record in records):
                    raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
                superseded = {
                    cast(ShipmentObservation, record).supersedes
                    for record in records
                    if cast(ShipmentObservation, record).supersedes is not None
                }
                current_records = tuple(
                    cast(ShipmentObservation, record)
                    for record in records
                    if cast(ShipmentObservation, record).observation_id not in superseded
                    and cast(ShipmentObservation, record).verified_order_target_ref
                    == command.observation_record.verified_order_target_ref
                )
                expected_previous = (
                    ()
                    if command.previous_observation_record is None
                    else (command.previous_observation_record,)
                )
                if current_records != expected_previous:
                    raise _Cycle2NotApplicable() from None
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode(
                            P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
                            command.observation_record,
                        ),
                    ),
                    owner_customer_id=owner,
                )
                task_loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=((
                        "task_id",
                        command.expected_task_record.task_id,
                    ),),
                    for_update=True,
                )
                unit_loaded = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                    logical_identity=((
                        "request_unit_id",
                        command.expected_request_unit_record.request_unit_id,
                    ),),
                    for_update=True,
                )
                if task_loaded is None or unit_loaded is None:
                    raise _Cycle2NotApplicable() from None
                self._cycle2_replace(
                    session,
                    task_loaded[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_task_record,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.TASK_RECORD,
                        command.next_task_record,
                    ),
                )
                self._cycle2_replace(
                    session,
                    unit_loaded[0],
                    owner_customer_id=owner,
                    expected_record=command.expected_request_unit_record,
                    next_envelope=self._cycle2_encode(
                        P0RecordCode.REQUEST_UNIT_RECORD,
                        command.next_request_unit_record,
                    ),
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @classmethod
    def _cycle2_source_message(
        cls,
        session: Session,
        *,
        owner_customer_id: str,
        binding: InputBindingV2,
        for_update: bool,
    ) -> MessageRecord:
        if len(binding.source_refs) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner_customer_id,
            record_code=P0RecordCode.MESSAGE_RECORD,
            logical_identity=(("message_id", binding.source_refs[0]),),
            for_update=for_update,
        )
        if loaded is None or type(loaded[1].source_record) is not MessageRecord:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        return cast(MessageRecord, loaded[1].source_record)

    @classmethod
    def _cycle2_assessment_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        verified_order_target_ref: str,
        trusted_assessed_at: datetime,
        for_update: bool = False,
    ) -> ShipmentAssessmentReadClosure | None:
        owner = owner_scope.customer_id
        task_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.TASK_RECORD,
            logical_identity=(("task_id", task_id),),
            for_update=for_update,
        )
        unit_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            logical_identity=(("request_unit_id", request_unit_id),),
            for_update=for_update,
        )
        links = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            predicates=(P0RecordModel.task_id == task_id,),
            for_update=for_update,
        )
        if task_loaded is None or unit_loaded is None or len(links) != 1:
            return None
        task = task_loaded[1].source_record
        unit = unit_loaded[1].source_record
        link = links[0][1].source_record
        if (
            type(task) is not TaskRecord
            or type(unit) is not RequestUnitRecord
            or type(link) is not ConversationTaskLinkRecord
        ):
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        conversation_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            logical_identity=(("conversation_id", link.conversation_id),),
            for_update=for_update,
        )
        if conversation_loaded is None or type(conversation_loaded[1].source_record) is not ConversationRecord:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        observations = tuple(
            cast(ShipmentObservation, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.SHIPMENT_OBSERVATION_RECORD,
                predicates=(
                    P0RecordModel.task_id == task_id,
                    P0RecordModel.request_unit_id == request_unit_id,
                ),
                for_update=for_update,
            )
            if type(decoded.source_record) is ShipmentObservation
            and decoded.source_record.verified_order_target_ref
            == verified_order_target_ref
        )
        superseded_refs = {
            record.supersedes for record in observations if record.supersedes is not None
        }
        current_observations = tuple(
            record for record in observations if record.observation_id not in superseded_refs
        )
        if len(current_observations) != 1:
            if not current_observations:
                return None
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        current_observation = current_observations[0]
        binding_rows = []
        for binding_id in unit.input_binding_refs:
            loaded = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.INPUT_BINDING_RECORD,
                logical_identity=(("binding_id", binding_id),),
                for_update=for_update,
                expected_versions=_CYCLE2_INPUT_BINDING_VERSIONS,
            )
            if loaded is None:
                raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
            binding_rows.append(loaded[1].source_record)
        legacy = tuple(record for record in binding_rows if type(record) is InputBinding)
        queries = []
        ordinals = []
        claims = []
        for record in binding_rows:
            if type(record) is not InputBindingV2:
                continue
            binding = cast(InputBindingV2, record)
            message = cls._cycle2_source_message(
                session,
                owner_customer_id=owner,
                binding=binding,
                for_update=for_update,
            )
            common = dict(
                binding_ref=binding.binding_id,
                private_owner_scope_ref=owner,
                conversation_id=link.conversation_id,
                task_id=task.task_id,
                request_unit_id=unit.request_unit_id,
                source_message_record=message,
                accepted_at=binding.updated_at,
            )
            if binding.name == "product_description":
                queries.append(
                    AcceptedOrderSearchQueryBindingReadClosure(
                        normalized_query=cast(str, binding.normalized_value),
                        accepted_task_state_version=task.state_version,
                        current_task_state_version=task.state_version,
                        **common,
                    )
                )
            elif binding.name == "candidate_ordinal":
                ordinals.append(
                    AcceptedOrdinalBindingReadClosure(
                        normalized_ordinal=cast(int, binding.normalized_value),
                        task_state_version=task.state_version,
                        **common,
                    )
                )
            elif binding.name == "shipment_not_received":
                if binding.normalized_value is not True:
                    raise _integrity(P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH)
                claims.append(
                    ShipmentNotReceivedClaimReadClosure(
                        task_state_version=task.state_version,
                        verified_order_target_ref=verified_order_target_ref,
                        **common,
                    )
                )
        assessment_rows = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.SHIPMENT_ASSESSMENT_RECORD,
            predicates=(
                P0RecordModel.task_id == task_id,
                P0RecordModel.request_unit_id == request_unit_id,
            ),
            for_update=for_update,
        )
        assessments = tuple(
            cast(ShipmentAssessment, decoded.source_record)
            for _, decoded in assessment_rows
            if type(decoded.source_record) is ShipmentAssessment
            and decoded.source_record.verified_order_target_ref
            == verified_order_target_ref
        )
        assessment_superseded = {
            item.supersedes_assessment_ref
            for item in assessments
            if item.supersedes_assessment_ref is not None
        }
        current_assessments = tuple(
            item for item in assessments if item.assessment_id not in assessment_superseded
        )
        if len(current_assessments) > 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        return ShipmentAssessmentReadClosure(
            owner_scope=owner_scope,
            trusted_conversation_record=cast(ConversationRecord, conversation_loaded[1].source_record),
            current_task_record=task,
            current_request_unit_record=unit,
            current_observation_record=current_observation,
            current_observation_ref=current_observation.observation_id,
            superseded_observation_records=tuple(
                record for record in observations if record != current_observation
            ),
            verified_order_target_ref=verified_order_target_ref,
            trusted_assessed_at=trusted_assessed_at,
            current_input_binding_records=cast(tuple[InputBinding, ...], legacy),
            current_query_bindings=tuple(queries),
            current_ordinal_bindings=tuple(ordinals),
            current_claim_bindings=tuple(claims),
            current_assessment_records=current_assessments,
        )

    @_bounded_database_failures
    async def load_shipment_assessment_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        task_id: UUID,
        request_unit_id: UUID,
        verified_order_target_ref: str,
        trusted_assessed_at: datetime,
    ) -> ShipmentAssessmentReadClosure | None:
        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                return self._cycle2_assessment_closure(
                    session,
                    owner_scope=owner_scope,
                    task_id=task_id,
                    request_unit_id=request_unit_id,
                    verified_order_target_ref=verified_order_target_ref,
                    trusted_assessed_at=trusted_assessed_at,
                )

    @_bounded_database_failures
    async def save_shipment_assessment_if_current(
        self,
        command: SaveShipmentAssessmentV2Command,
    ) -> Cycle2WriteResult:
        closure = command.loaded_closure
        owner = closure.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_assessment_closure(
                    session,
                    owner_scope=closure.owner_scope,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=closure.current_request_unit_record.request_unit_id,
                    verified_order_target_ref=closure.verified_order_target_ref,
                    trusted_assessed_at=closure.trusted_assessed_at,
                    for_update=True,
                )
                try:
                    closure.require_same_persisted_graph(cast(ShipmentAssessmentReadClosure, current))
                except (TypeError, ValueError):
                    raise _Cycle2NotApplicable() from None
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode(
                            P0RecordCode.SHIPMENT_ASSESSMENT_RECORD,
                            command.assessment_record,
                        ),
                    ),
                    owner_customer_id=owner,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @classmethod
    def _cycle2_query_binding_closure(
        cls,
        session: Session,
        *,
        owner_customer_id: str,
        conversation_id: UUID,
        task: TaskRecord,
        unit: RequestUnitRecord,
        binding: InputBindingV2,
        accepted_task_state_version: int,
        for_update: bool,
    ) -> AcceptedOrderSearchQueryBindingReadClosure:
        if binding.name != "product_description":
            raise _integrity(P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH)
        message = cls._cycle2_source_message(
            session,
            owner_customer_id=owner_customer_id,
            binding=binding,
            for_update=for_update,
        )
        return AcceptedOrderSearchQueryBindingReadClosure(
            binding_ref=binding.binding_id,
            normalized_query=cast(str, binding.normalized_value),
            private_owner_scope_ref=owner_customer_id,
            conversation_id=conversation_id,
            task_id=task.task_id,
            request_unit_id=unit.request_unit_id,
            accepted_task_state_version=accepted_task_state_version,
            current_task_state_version=task.state_version,
            source_message_record=message,
            accepted_at=binding.updated_at,
        )

    @classmethod
    def _cycle2_search_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        run_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_read_at: datetime,
        for_update: bool = False,
    ) -> OrderSearchCurrentReadClosure | None:
        owner = owner_scope.customer_id
        conversation = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            logical_identity=(("conversation_id", conversation_id),),
            for_update=for_update,
        )
        run = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", run_id),),
            for_update=for_update,
        )
        current = cls._cycle2_current_task_unit_bindings(
            session,
            owner_scope=owner_scope,
            task_id=task_id,
            request_unit_id=request_unit_id,
            for_update=for_update,
        )
        if conversation is None or run is None or current is None:
            return None
        conversation_record = conversation[1].source_record
        run_record = run[1].source_record
        task, unit, bindings = current
        if type(conversation_record) is not ConversationRecord or type(run_record) is not AgentRunRecordV2:
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        if len(bindings) != 1 or bindings[0].name != "product_description":
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        all_sets = tuple(
            cast(OrderCandidateSetRecord, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
                predicates=(
                    P0RecordModel.task_id == task_id,
                    P0RecordModel.request_unit_id == request_unit_id,
                ),
                for_update=for_update,
            )
            if type(decoded.source_record) is OrderCandidateSetRecord
            and decoded.source_record.query_binding_refs == (bindings[0].binding_id,)
        )
        superseded = {
            record.supersedes_candidate_set_ref
            for record in all_sets
            if record.supersedes_candidate_set_ref is not None
        }
        current_sets = tuple(
            record
            for record in all_sets
            if record.candidate_set_id not in superseded
            and record.result_task_state_version == task.state_version
        )
        if len(current_sets) > 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        candidate_set = current_sets[0] if current_sets else None
        accepted_version = (
            min(record.base_task_state_version for record in all_sets)
            if all_sets
            else task.state_version
        )
        query = cls._cycle2_query_binding_closure(
            session,
            owner_customer_id=owner,
            conversation_id=conversation_id,
            task=task,
            unit=unit,
            binding=bindings[0],
            accepted_task_state_version=accepted_version,
            for_update=for_update,
        )
        source = None
        observation = None
        auto_targets: tuple[OrderCandidateAutoTargetRecord, ...] = ()
        if candidate_set is not None:
            loaded_source = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.TOOL_CALL_RECORD,
                logical_identity=(("tool_call_id", candidate_set.source_tool_call_id),),
                for_update=for_update,
            )
            loaded_observation = cls._cycle2_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
                logical_identity=(("observation_id", candidate_set.search_observation_ref),),
                for_update=for_update,
            )
            if loaded_source is None or loaded_observation is None:
                raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
            source = loaded_source[1].source_record
            observation = loaded_observation[1].source_record
            if type(source) is not ToolCallRecordV2 or type(observation) is not SearchOrdersObservation:
                raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
            reconstructed = []
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
                predicates=(
                    P0RecordModel.task_id == task_id,
                    P0RecordModel.request_unit_id == request_unit_id,
                ),
                for_update=for_update,
            ):
                record = decoded.source_record
                if (
                    type(record) is OrderCandidateSelectionRecord
                    and record.candidate_set_ref == candidate_set.candidate_set_id
                ):
                    auto_target = cls._cycle2_auto_target_from_selection(
                        record=record,
                        candidate_set=candidate_set,
                    )
                    if auto_target is not None:
                        reconstructed.append(auto_target)
            auto_targets = tuple(reconstructed)
            if len(auto_targets) > 1:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                )
        return OrderSearchCurrentReadClosure(
            owner_scope=owner_scope,
            trusted_conversation_record=cast(ConversationRecord, conversation_record),
            source_run_record=cast(AgentRunRecordV2, run_record),
            current_query_binding=query,
            current_task_record=task,
            current_request_unit_record=unit,
            current_candidate_source_tool_call_record=cast(ToolCallRecordV2 | None, source),
            current_search_observation_record=cast(SearchOrdersObservation | None, observation),
            current_candidate_set_record=candidate_set,
            current_auto_target_records=auto_targets,
            trusted_read_at=trusted_read_at,
        )

    @_bounded_database_failures
    async def load_order_search_current_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        run_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        trusted_read_at: datetime,
    ) -> OrderSearchCurrentReadClosure | None:
        with self.session_factory() as session:
            with session.begin():
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                return self._cycle2_search_closure(
                    session,
                    owner_scope=owner_scope,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    task_id=task_id,
                    request_unit_id=request_unit_id,
                    trusted_read_at=trusted_read_at,
                )

    @_bounded_database_failures
    async def apply_order_search_outcome_if_current(
        self,
        command: ApplyOrderSearchOutcomeV2Command,
    ) -> Cycle2WriteResult:
        closure = command.loaded_read_closure
        owner = command.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_search_closure(
                    session,
                    owner_scope=command.owner_scope,
                    conversation_id=command.trusted_conversation_record.conversation_id,
                    run_id=command.source_run_record.run_id,
                    task_id=command.expected_task_record.task_id,
                    request_unit_id=command.expected_request_unit_record.request_unit_id,
                    trusted_read_at=closure.trusted_read_at,
                    for_update=True,
                )
                try:
                    closure.require_same_persisted_graph(cast(OrderSearchCurrentReadClosure, current))
                except (TypeError, ValueError):
                    raise _Cycle2NotApplicable() from None
                tool = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TOOL_CALL_RECORD,
                    logical_identity=(("tool_call_id", command.source_tool_call_record.tool_call_id),),
                    for_update=True,
                )
                task = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=(("task_id", command.expected_task_record.task_id),),
                    for_update=True,
                )
                unit = self._cycle2_row(
                    session,
                    owner_customer_id=owner,
                    record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                    logical_identity=(("request_unit_id", command.expected_request_unit_record.request_unit_id),),
                    for_update=True,
                )
                if tool is None or task is None or unit is None or tool[1].source_record != command.source_tool_call_record:
                    raise _Cycle2NotApplicable() from None
                candidate_records = [
                    self._cycle2_encode(P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD, command.search_observation_record),
                    self._cycle2_encode(P0RecordCode.ORDER_CANDIDATE_SET_RECORD, command.candidate_set_record),
                ]
                if command.auto_target_record is not None:
                    candidate_records.append(
                        self._cycle2_encode(
                            P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
                            self._cycle2_auto_target_selection(
                                auto_target=command.auto_target_record,
                                source_message_ref=(
                                    command.current_query_binding.source_message_record.message_id
                                ),
                            ),
                        )
                    )
                self._cycle2_insert(
                    session,
                    tuple(candidate_records),
                    owner_customer_id=owner,
                )
                self._cycle2_replace(session, task[0], owner_customer_id=owner, expected_record=command.expected_task_record, next_envelope=self._cycle2_encode(P0RecordCode.TASK_RECORD, command.next_task_record))
                self._cycle2_replace(session, unit[0], owner_customer_id=owner, expected_record=command.expected_request_unit_record, next_envelope=self._cycle2_encode(P0RecordCode.REQUEST_UNIT_RECORD, command.next_request_unit_record))
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @classmethod
    def _cycle2_selection_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        selection_request: OrderCandidateSelectionRequest,
        trusted_now: datetime,
        for_update: bool = False,
    ) -> OrderCandidateSelectionReadClosure | None:
        owner = owner_scope.customer_id
        conversation = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            logical_identity=(("conversation_id", conversation_id),),
            for_update=for_update,
        )
        current = cls._cycle2_current_task_unit_bindings(
            session,
            owner_scope=owner_scope,
            task_id=task_id,
            request_unit_id=request_unit_id,
            for_update=for_update,
        )
        message = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.MESSAGE_RECORD,
            logical_identity=(("message_id", selection_request.source_message_ref),),
            for_update=for_update,
        )
        if conversation is None or current is None or message is None:
            return None
        task, unit, bindings = current
        candidates = tuple(
            cast(OrderCandidateSetRecord, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SET_RECORD,
                predicates=(
                    P0RecordModel.task_id == task_id,
                    P0RecordModel.request_unit_id == request_unit_id,
                ),
                for_update=for_update,
            )
            if type(decoded.source_record) is OrderCandidateSetRecord
        )
        superseded_refs = tuple(
            cast(UUID, record.supersedes_candidate_set_ref)
            for record in candidates
            if record.supersedes_candidate_set_ref is not None
        )
        current_sets = tuple(
            record
            for record in candidates
            if record.candidate_set_id not in set(superseded_refs)
            and record.selection_expected_task_state_version == task.state_version
        )
        if not current_sets:
            return None
        if len(current_sets) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        candidate_set = current_sets[0]
        observation_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.ORDER_SEARCH_OBSERVATION_RECORD,
            logical_identity=(("observation_id", candidate_set.search_observation_ref),),
            for_update=for_update,
        )
        if observation_loaded is None or type(observation_loaded[1].source_record) is not SearchOrdersObservation:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        observation = cast(SearchOrdersObservation, observation_loaded[1].source_record)
        query_records = tuple(
            binding
            for binding in bindings
            if binding.binding_id in candidate_set.query_binding_refs
        )
        if len(query_records) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        query = cls._cycle2_query_binding_closure(
            session,
            owner_customer_id=owner,
            conversation_id=conversation_id,
            task=task,
            unit=unit,
            binding=query_records[0],
            accepted_task_state_version=candidate_set.base_task_state_version,
            for_update=for_update,
        )
        matching_entries = tuple(
            entry
            for entry in candidate_set.ordered_candidates
            if entry.ordinal == selection_request.ordinal
        )
        if len(matching_entries) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        selected = matching_entries[0]
        matching_targets = tuple(
            target
            for target in observation.candidate_target_bindings
            if target.observation_candidate_ref == selected.observation_candidate_ref
            and target.candidate_source_version == selected.candidate_source_version
        )
        if len(matching_targets) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        run_rows = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            predicates=(P0RecordModel.conversation_id == conversation_id,),
            for_update=for_update,
        )
        active_runs = tuple(
            cast(AgentRunRecordV2, decoded.source_record)
            for _, decoded in run_rows
            if type(decoded.source_record) is AgentRunRecordV2
            and decoded.source_record.status is AgentRunStatusV2.RUNNING
        )
        if len(active_runs) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        run = active_runs[0]
        link_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            logical_identity=(("run_id", run.run_id), ("task_id", task_id)),
            for_update=for_update,
        )
        if link_loaded is None or type(link_loaded[1].source_record) is not RunTaskLinkRecordV2:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        selections = tuple(
            cast(OrderCandidateSelectionRecord, decoded.source_record)
            for _, decoded in cls._cycle2_rows(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD,
                predicates=(
                    P0RecordModel.task_id == task_id,
                    P0RecordModel.request_unit_id == request_unit_id,
                ),
                for_update=for_update,
            )
            if type(decoded.source_record) is OrderCandidateSelectionRecord
            and decoded.source_record.candidate_set_ref == candidate_set.candidate_set_id
            and cls._cycle2_parse_auto_target_marker(
                decoded.source_record.selected_target_ref
            ) is None
        )
        return OrderCandidateSelectionReadClosure(
            owner_scope=owner_scope,
            trusted_conversation_record=cast(ConversationRecord, conversation[1].source_record),
            current_run_record=run,
            current_run_task_link_record=cast(RunTaskLinkRecordV2, link_loaded[1].source_record),
            current_task_record=task,
            current_request_unit_record=unit,
            current_candidate_set_record=candidate_set,
            search_observation_record=observation,
            selection_request=selection_request,
            saved_selection_message_record=cast(MessageRecord, message[1].source_record),
            current_query_binding=query,
            pending_candidate_set_ref=candidate_set.candidate_set_id,
            current_query_binding_refs=candidate_set.query_binding_refs,
            resolved_owner_scoped_order_target_ref=matching_targets[0].owner_scoped_order_ref,
            superseded_candidate_set_refs=superseded_refs,
            existing_selection_records=selections,
            trusted_now=trusted_now,
        )

    @_bounded_database_failures
    async def load_order_candidate_selection_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        conversation_id: UUID,
        task_id: UUID,
        request_unit_id: UUID,
        selection_request: OrderCandidateSelectionRequest,
        trusted_now: datetime,
    ) -> OrderCandidateSelectionReadClosure | None:
        with self.session_factory() as session:
            with session.begin():
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                return self._cycle2_selection_closure(
                    session,
                    owner_scope=owner_scope,
                    conversation_id=conversation_id,
                    task_id=task_id,
                    request_unit_id=request_unit_id,
                    selection_request=selection_request,
                    trusted_now=trusted_now,
                )

    @_bounded_database_failures
    async def apply_order_candidate_selection_if_current(
        self,
        command: ApplyOrderCandidateSelectionV2Command,
    ) -> Cycle2WriteResult:
        try:
            command.require_live_target_issuance()
        except ValueError:
            return Cycle2WriteResult.NOT_APPLICABLE
        closure = command.loaded_closure
        owner = closure.owner_scope.customer_id
        try:
            with self.session_factory.begin() as session:
                current = self._cycle2_selection_closure(
                    session,
                    owner_scope=closure.owner_scope,
                    conversation_id=closure.conversation_id,
                    task_id=closure.current_task_record.task_id,
                    request_unit_id=closure.current_request_unit_record.request_unit_id,
                    selection_request=closure.selection_request,
                    trusted_now=closure.trusted_now,
                    for_update=True,
                )
                if current != closure:
                    raise _Cycle2NotApplicable() from None
                task = self._cycle2_row(session, owner_customer_id=owner, record_code=P0RecordCode.TASK_RECORD, logical_identity=(("task_id", closure.current_task_record.task_id),), for_update=True)
                unit = self._cycle2_row(session, owner_customer_id=owner, record_code=P0RecordCode.REQUEST_UNIT_RECORD, logical_identity=(("request_unit_id", closure.current_request_unit_record.request_unit_id),), for_update=True)
                if task is None or unit is None:
                    raise _Cycle2NotApplicable() from None
                self._cycle2_insert(
                    session,
                    (
                        self._cycle2_encode_input_binding(
                            command.ordinal_input_binding_record,
                            request_unit_id=closure.current_request_unit_record.request_unit_id,
                        ),
                        self._cycle2_encode(P0RecordCode.ORDER_CANDIDATE_SELECTION_RECORD, command.selection_record),
                    ),
                    owner_customer_id=owner,
                )
                self._cycle2_replace(session, task[0], owner_customer_id=owner, expected_record=closure.current_task_record, next_envelope=self._cycle2_encode(P0RecordCode.TASK_RECORD, command.next_task_record))
                self._cycle2_replace(session, unit[0], owner_customer_id=owner, expected_record=closure.current_request_unit_record, next_envelope=self._cycle2_encode(P0RecordCode.REQUEST_UNIT_RECORD, command.next_request_unit_record))
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

    @classmethod
    def _cycle2_superseded_closure(
        cls,
        session: Session,
        *,
        owner_scope: TrustedOwnerScope,
        obsolete_run_id: UUID,
        replacement_run_id: UUID,
        request_unit_id: UUID,
        trusted_current_evidence_at: datetime,
        for_update: bool = False,
    ) -> SupersededRunReadClosure | None:
        owner = owner_scope.customer_id
        obsolete_run_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", obsolete_run_id),),
            for_update=for_update,
        )
        replacement_run_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", replacement_run_id),),
            for_update=for_update,
        )
        if obsolete_run_loaded is None or replacement_run_loaded is None:
            return None
        obsolete_run = obsolete_run_loaded[1].source_record
        replacement_run = replacement_run_loaded[1].source_record
        if type(obsolete_run) is not AgentRunRecordV2 or type(replacement_run) is not AgentRunRecordV2:
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        obsolete_links = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            predicates=(P0RecordModel.run_id == obsolete_run_id,),
            for_update=for_update,
        )
        replacement_links = cls._cycle2_rows(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            predicates=(P0RecordModel.run_id == replacement_run_id,),
            for_update=for_update,
        )
        if len(obsolete_links) != 1 or len(replacement_links) != 1:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        obsolete_link = obsolete_links[0][1].source_record
        replacement_link = replacement_links[0][1].source_record
        if type(obsolete_link) is not RunTaskLinkRecordV2 or type(replacement_link) is not RunTaskLinkRecordV2:
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        task_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.TASK_RECORD,
            logical_identity=(("task_id", obsolete_link.task_id),),
            for_update=for_update,
        )
        unit_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.REQUEST_UNIT_RECORD,
            logical_identity=(("request_unit_id", request_unit_id),),
            for_update=for_update,
        )
        if task_loaded is None or unit_loaded is None:
            raise _integrity(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        task = task_loaded[1].source_record
        unit = unit_loaded[1].source_record
        conversation_loaded = cls._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.CONVERSATION_RECORD,
            logical_identity=(("conversation_id", obsolete_run.conversation_id),),
            for_update=for_update,
        )
        if (
            type(task) is not TaskRecord
            or type(unit) is not RequestUnitRecord
            or conversation_loaded is None
            or type(conversation_loaded[1].source_record) is not ConversationRecord
        ):
            raise _integrity(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
        obsolete_task: TaskRecord | None = None
        obsolete_unit: RequestUnitRecord | None = None
        obsolete_binding_refs: tuple[UUID, ...] = ()
        invalidated_binding_refs: tuple[UUID, ...] = ()
        invalidation_kind = SupersededRunInvalidationKind.TASK_VERSION_ADVANCED
        if obsolete_link.base_task_state_version is not None:
            historical_task = cls._cycle2_historical_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(("task_id", obsolete_link.task_id),),
                state_version=obsolete_link.base_task_state_version,
            )
            historical_unit = cls._cycle2_historical_row(
                session,
                owner_customer_id=owner,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                logical_identity=(("request_unit_id", request_unit_id),),
                state_version=obsolete_link.base_task_state_version,
            )
            if historical_task is None or historical_unit is None:
                return None
            historical_task_record = historical_task.source_record
            historical_unit_record = historical_unit.source_record
            if (
                type(historical_task_record) is not TaskRecord
                or type(historical_unit_record) is not RequestUnitRecord
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            obsolete_task = historical_task_record
            obsolete_unit = historical_unit_record
            removed_binding_refs = tuple(
                binding_ref
                for binding_ref in obsolete_unit.input_binding_refs
                if binding_ref not in set(unit.input_binding_refs)
            )
            if removed_binding_refs:
                invalidation_kind = (
                    SupersededRunInvalidationKind.BINDING_INVALIDATED
                )
                obsolete_binding_refs = removed_binding_refs
                invalidated_binding_refs = removed_binding_refs
        try:
            return SupersededRunReadClosure(
                owner_scope=owner_scope,
                trusted_conversation_record=cast(ConversationRecord, conversation_loaded[1].source_record),
                expected_active_run_record=obsolete_run,
                expected_active_link_record=obsolete_link,
                current_authoritative_run_record=replacement_run,
                current_authoritative_link_record=replacement_link,
                current_task_record=task,
                current_request_unit_record=unit,
                obsolete_task_record=obsolete_task,
                obsolete_request_unit_record=obsolete_unit,
                trusted_current_evidence_at=trusted_current_evidence_at,
                invalidation_kind=invalidation_kind,
                obsolete_binding_refs=obsolete_binding_refs,
                invalidated_binding_refs=invalidated_binding_refs,
            )
        except (TypeError, ValueError, ValidationError, RecursionError):
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            ) from None

    @_bounded_database_failures
    async def load_superseded_run_closure_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        obsolete_run_id: UUID,
        replacement_run_id: UUID,
        request_unit_id: UUID,
    ) -> SupersededRunReadClosure | None:
        trusted_now = self._cycle2_trusted_now()
        with self.session_factory() as session:
            with session.begin():
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                return self._cycle2_superseded_closure(
                    session,
                    owner_scope=owner_scope,
                    obsolete_run_id=obsolete_run_id,
                    replacement_run_id=replacement_run_id,
                    request_unit_id=request_unit_id,
                    trusted_current_evidence_at=trusted_now,
                )

    def _cycle2_superseded_is_applied(
        self,
        session: Session,
        command: FinalizeSupersededRunV2Command,
        *,
        for_update: bool,
    ) -> bool:
        closure = command.loaded_closure
        owner = closure.owner_scope.customer_id
        persisted_run = self._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", command.superseded_run_record.run_id),),
            for_update=for_update,
        )
        persisted_link = self._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            logical_identity=(("run_id", command.no_result_link_record.run_id), ("task_id", command.no_result_link_record.task_id)),
            for_update=for_update,
        )
        persisted_trace = self._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.TRACE_EVENT_RECORD,
            logical_identity=(("trace_event_id", command.run_stopped_trace_record.trace_event_id),),
            for_update=for_update,
        )
        return (
            persisted_run is not None
            and persisted_link is not None
            and persisted_trace is not None
            and persisted_run[1].source_record == command.superseded_run_record
            and persisted_link[1].source_record == command.no_result_link_record
            and persisted_trace[1].source_record == command.run_stopped_trace_record
        )

    def _cycle2_finalize_superseded_in_transaction(
        self,
        session: Session,
        command: FinalizeSupersededRunV2Command,
    ) -> None:
        closure = command.loaded_closure
        owner = closure.owner_scope.customer_id
        if self._cycle2_superseded_is_applied(
            session,
            command,
            for_update=True,
        ):
            raise _Cycle2AlreadyApplied() from None
        current = self._cycle2_superseded_closure(
            session,
            owner_scope=closure.owner_scope,
            obsolete_run_id=closure.expected_active_run_record.run_id,
            replacement_run_id=closure.current_authoritative_run_record.run_id,
            request_unit_id=closure.current_request_unit_record.request_unit_id,
            trusted_current_evidence_at=closure.trusted_current_evidence_at,
            for_update=True,
        )
        if current != closure:
            raise _Cycle2NotApplicable() from None
        run_loaded = self._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(("run_id", closure.expected_active_run_record.run_id),),
            for_update=True,
        )
        link_loaded = self._cycle2_row(
            session,
            owner_customer_id=owner,
            record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
            logical_identity=(("run_id", closure.expected_active_run_record.run_id), ("task_id", closure.expected_active_link_record.task_id)),
            for_update=True,
        )
        if run_loaded is None or link_loaded is None:
            raise _Cycle2NotApplicable() from None
        self._cycle2_replace(
            session,
            run_loaded[0],
            owner_customer_id=owner,
            expected_record=closure.expected_active_run_record,
            next_envelope=self._cycle2_encode(P0RecordCode.AGENT_RUN_RECORD, command.superseded_run_record),
        )
        self._cycle2_replace(
            session,
            link_loaded[0],
            owner_customer_id=owner,
            expected_record=closure.expected_active_link_record,
            next_envelope=self._cycle2_encode(P0RecordCode.RUN_TASK_LINK_RECORD, command.no_result_link_record),
        )
        self._cycle2_insert(
            session,
            (self._cycle2_encode(P0RecordCode.TRACE_EVENT_RECORD, command.run_stopped_trace_record),),
            owner_customer_id=owner,
        )

    @_bounded_database_failures
    async def finalize_superseded_run_if_current(
        self,
        command: FinalizeSupersededRunV2Command,
    ) -> Cycle2WriteResult:
        try:
            with self.session_factory.begin() as session:
                self._cycle2_finalize_superseded_in_transaction(session, command)
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        except _Cycle2AlreadyApplied:
            return Cycle2WriteResult.ALREADY_APPLIED
        return Cycle2WriteResult.APPLIED

    @_bounded_database_failures
    async def finalize_state_invalidated_tool_recovery_if_current(
        self,
        command: FinalizeStateInvalidatedToolRecoveryV2Command,
    ) -> Cycle2WriteResult:
        try:
            with self.session_factory.begin() as session:
                self._cycle2_finalize_recovery_in_transaction(
                    session,
                    loaded_closure=command.loaded_closure,
                    terminal_record=command.terminal_tool_call_record,
                    recovery_decision=command.recovery_decision_record,
                )
                self._cycle2_finalize_superseded_in_transaction(
                    session,
                    command.superseded_run_command,
                )
        except _Cycle2NotApplicable:
            return Cycle2WriteResult.NOT_APPLICABLE
        except _Cycle2ProjectionConflict:
            return Cycle2WriteResult.PROJECTION_CONFLICT
        except _Cycle2AlreadyApplied:
            # A composed OA-10 command is idempotent only when both the Tool
            # terminal and the no-result Run closure are already exact.
            with self.session_factory() as session:
                if self._cycle2_recovery_is_applied(
                    session,
                    loaded_closure=command.loaded_closure,
                    terminal_record=command.terminal_tool_call_record,
                    recovery_decision=command.recovery_decision_record,
                    for_update=False,
                ) and self._cycle2_superseded_is_applied(
                    session,
                    command.superseded_run_command,
                    for_update=False,
                ):
                    return Cycle2WriteResult.ALREADY_APPLIED
            return Cycle2WriteResult.PROJECTION_CONFLICT
        return Cycle2WriteResult.APPLIED

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
