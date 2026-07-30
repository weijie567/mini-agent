"""Closed logical persistence codec for the first E2E-01 thin slice."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from pydantic import (
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_serializer,
    field_validator,
)
from pydantic_core import PydanticSerializationError

from mini_agent.application.records import (
    ConversationRecord,
    ConversationTaskLinkRecord,
    EvalExecutionFailureRecord,
    EvalResultRecord,
    MessageRecord,
    RunTaskLinkRecord,
)
from mini_agent.core.common import (
    ContractModel,
    FrozenJsonDict,
    FrozenJsonList,
    RuntimePrivateModel,
    freeze_json_value,
    thaw_json_value,
)
from mini_agent.core.memory import ContextManifest, OrderObservation
from mini_agent.core.task_state import (
    CandidateValidationDecision,
    InputBinding,
    RequestUnitRecord,
    TaskRecord,
    TaskStateTransition,
)
from mini_agent.core.tool_system import (
    GateDecision,
    MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION,
    ModelVisibleToolsetArtifact,
    ToolAttemptRecord,
    ToolCallRecord,
)
from mini_agent.core.trace import AgentRunRecord, TraceEvent


class P0RecordCode(StrEnum):
    CONVERSATION_RECORD = "conversation_record"
    MESSAGE_RECORD = "message_record"
    REQUEST_UNDERSTANDING_RECORD = "request_understanding_record"
    TASK_RECORD = "task_record"
    REQUEST_UNIT_RECORD = "request_unit_record"
    CONVERSATION_TASK_LINK_RECORD = "conversation_task_link_record"
    RUN_TASK_LINK_RECORD = "run_task_link_record"
    INPUT_BINDING_RECORD = "input_binding_record"
    MODEL_VISIBLE_TOOLSET_ARTIFACT = "model_visible_toolset_artifact"
    AGENT_RUN_RECORD = "agent_run_record"
    GATE_DECISION_RECORD = "gate_decision_record"
    TOOL_CALL_RECORD = "tool_call_record"
    OBSERVATION_RECORD = "observation_record"
    CONTEXT_MANIFEST_RECORD = "context_manifest_record"
    TRACE_EVENT_RECORD = "trace_event_record"
    EVAL_RESULT_RECORD = "eval_result_record"
    EVAL_EXECUTION_FAILURE_RECORD = "eval_execution_failure_record"


class P0LogicalChildCode(StrEnum):
    ACCEPTED_TASK_DELTA = "accepted_task_delta"
    TASK_STATE_TRANSITION = "task_state_transition"
    TOOL_ATTEMPT_RECORD = "tool_attempt_record"


JsonScalar = str | int | float | bool | None
LogicalIdentity = tuple[tuple[str, JsonScalar], ...]


class P0RecordReference(ContractModel):
    relation: str
    target_record_code: P0RecordCode
    target_logical_identity: LogicalIdentity


class _ImmutableJsonModel(RuntimePrivateModel):
    data: Mapping[str, JsonValue]

    @field_validator("data", mode="before")
    @classmethod
    def thaw_json_input(cls, value: Any) -> Any:
        return thaw_json_value(value)

    @field_validator("data")
    @classmethod
    def freeze_json_data(
        cls,
        value: Mapping[str, JsonValue],
    ) -> Mapping[str, JsonValue]:
        return freeze_json_value(value)

    @field_serializer("data")
    def serialize_json_data(
        self,
        value: Mapping[str, JsonValue],
    ) -> dict[str, JsonValue]:
        return thaw_json_value(value)


class P0LogicalChildPayload(_ImmutableJsonModel):
    child_code: P0LogicalChildCode
    parent_record_code: P0RecordCode
    parent_logical_identity: LogicalIdentity
    logical_identity: LogicalIdentity


class P0VersionedPayload(_ImmutableJsonModel):
    record_code: P0RecordCode
    record_schema_version: str
    logical_children: tuple[P0LogicalChildPayload, ...] = ()


class P0PersistenceEnvelope(RuntimePrivateModel):
    record_code: P0RecordCode
    record_schema_version: str
    logical_identity: LogicalIdentity
    direct_owner_customer_id: str | None = None
    record_references: tuple[P0RecordReference, ...] = ()
    payload: P0VersionedPayload


class DecodedP0PersistenceRecord(RuntimePrivateModel):
    record_code: P0RecordCode
    record_schema_version: str
    source_record: ContractModel
    logical_children: tuple[ContractModel, ...] = ()


class P0PersistenceIntegrityCategory(StrEnum):
    MISSING_RECORD_CODE = "MISSING_RECORD_CODE"
    UNKNOWN_RECORD_CODE = "UNKNOWN_RECORD_CODE"
    RECORD_CODE_MISMATCH = "RECORD_CODE_MISMATCH"
    MISSING_RECORD_SCHEMA_VERSION = "MISSING_RECORD_SCHEMA_VERSION"
    UNKNOWN_RECORD_SCHEMA_VERSION = "UNKNOWN_RECORD_SCHEMA_VERSION"
    RECORD_SCHEMA_VERSION_MISMATCH = "RECORD_SCHEMA_VERSION_MISMATCH"
    METADATA_PAYLOAD_MISMATCH = "METADATA_PAYLOAD_MISMATCH"
    SOURCE_MODEL_MISMATCH = "SOURCE_MODEL_MISMATCH"
    PAYLOAD_VALIDATION_FAILED = "PAYLOAD_VALIDATION_FAILED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    OWNER_PROJECTION_MISMATCH = "OWNER_PROJECTION_MISMATCH"
    LINK_PROJECTION_MISMATCH = "LINK_PROJECTION_MISMATCH"
    LINK_CARDINALITY_MISMATCH = "LINK_CARDINALITY_MISMATCH"
    CHILD_MISMATCH = "CHILD_MISMATCH"
    SPECIALIZED_VERSION_MISMATCH = "SPECIALIZED_VERSION_MISMATCH"


class P0PersistenceIntegrityError(Exception):
    """Non-disclosing persistence failure carrying only bounded metadata."""

    __slots__ = ("_category", "_correlation_ref")

    def __init__(
        self,
        category: P0PersistenceIntegrityCategory,
        correlation_ref: UUID,
    ) -> None:
        self._category = category
        self._correlation_ref = correlation_ref
        super().__init__(category.value, str(correlation_ref))

    @property
    def category(self) -> P0PersistenceIntegrityCategory:
        return self._category

    @property
    def correlation_ref(self) -> UUID:
        return self._correlation_ref


class _IntegritySignal(Exception):
    __slots__ = ("category",)

    def __init__(self, category: P0PersistenceIntegrityCategory) -> None:
        self.category = category
        super().__init__(category.value)


class _ClosureStrategy(StrEnum):
    LOCAL_CLOSED = "LOCAL_CLOSED"
    GRAPH_REQUIRED = "GRAPH_REQUIRED"


class _ProjectionClassification(StrEnum):
    DIRECT_OWNER = "DIRECT_OWNER"
    TOP_LEVEL_P0_REFERENCE = "TOP_LEVEL_P0_REFERENCE"
    EXTERNAL_REQUIRED_P0_REFERENCE = "EXTERNAL_REQUIRED_P0_REFERENCE"
    CONDITIONAL_PAYLOAD_CORRELATION = "CONDITIONAL_PAYLOAD_CORRELATION"
    LOGICAL_CHILD_CORRELATION = "LOGICAL_CHILD_CORRELATION"
    PARENT_FIELD_EQUALITY = "PARENT_FIELD_EQUALITY"
    PARENT_LOCAL_CORRELATION = "PARENT_LOCAL_CORRELATION"
    CHILD_TOP_LEVEL_P0_REFERENCE = "CHILD_TOP_LEVEL_P0_REFERENCE"
    PAYLOAD_CORRELATION = "PAYLOAD_CORRELATION"
    RESTRICTED_DIAGNOSTIC_CORRELATION = "RESTRICTED_DIAGNOSTIC_CORRELATION"
    P0_FIRST_SLICE_MUST_BE_EMPTY = "P0_FIRST_SLICE_MUST_BE_EMPTY"


_ProjectionValues = Callable[[Mapping[str, Any]], tuple[JsonScalar, ...]]


@dataclass(frozen=True, slots=True)
class _P0ProjectionDecision:
    field_label: str
    classification: _ProjectionClassification
    relation: str | None = None
    target_record_code: P0RecordCode | None = None
    value_projector: _ProjectionValues | None = None
    minimum: int = 0
    maximum: int | None = None
    unique: bool = False


@dataclass(frozen=True, slots=True)
class P0RecordSchemaSpec:
    record_code: P0RecordCode
    record_schema_version: str
    source_model: type[ContractModel]
    identity_fields: tuple[str, ...]
    direct_owner_field: str | None = None
    projection_decisions: tuple[_P0ProjectionDecision, ...] = ()
    version_mirror_field: str | None = None
    allowed_child_codes: tuple[P0LogicalChildCode, ...] = ()
    specialized_version_validator: Callable[[ContractModel], bool] | None = None


@dataclass(frozen=True, slots=True)
class _P0LogicalChildSchemaSpec:
    child_code: P0LogicalChildCode
    source_model: type[ContractModel]
    parent_record_code: P0RecordCode
    identity_fields: tuple[str, ...]
    closure_strategy: _ClosureStrategy
    projection_decisions: tuple[_P0ProjectionDecision, ...]


def _one(field_name: str) -> _ProjectionValues:
    return lambda data: (data[field_name],)


def _optional(field_name: str) -> _ProjectionValues:
    return lambda data: () if data[field_name] is None else (data[field_name],)


def _many(field_name: str) -> _ProjectionValues:
    return lambda data: tuple(data[field_name])


def _nested_optional(parent_field: str, child_field: str) -> _ProjectionValues:
    return lambda data: (
        () if data[parent_field] is None else (data[parent_field][child_field],)
    )


def _nested_many(parent_field: str, child_field: str) -> _ProjectionValues:
    return lambda data: tuple(item[child_field] for item in data[parent_field])


def _combined(*projectors: _ProjectionValues) -> _ProjectionValues:
    return lambda data: tuple(
        value for projector in projectors for value in projector(data)
    )


def _decision(
    field_label: str,
    classification: _ProjectionClassification,
    *,
    relation: str | None = None,
    target_record_code: P0RecordCode | None = None,
    value_projector: _ProjectionValues | None = None,
    minimum: int = 0,
    maximum: int | None = None,
    unique: bool = False,
) -> _P0ProjectionDecision:
    return _P0ProjectionDecision(
        field_label=field_label,
        classification=classification,
        relation=relation,
        target_record_code=target_record_code,
        value_projector=value_projector,
        minimum=minimum,
        maximum=maximum,
        unique=unique,
    )


_D = _ProjectionClassification
_R = P0RecordCode

_TOP_LEVEL_PROJECTIONS: Mapping[P0RecordCode, tuple[_P0ProjectionDecision, ...]] = (
    MappingProxyType(
        {
            _R.CONVERSATION_RECORD: (
                _decision(
                    "owner_customer_id",
                    _D.DIRECT_OWNER,
                    value_projector=_one("owner_customer_id"),
                    minimum=1,
                    maximum=1,
                ),
            ),
            _R.MESSAGE_RECORD: (
                _decision(
                    "conversation_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="conversation_id",
                    target_record_code=_R.CONVERSATION_RECORD,
                    value_projector=_one("conversation_id"),
                    minimum=1,
                    maximum=1,
                ),
            ),
            _R.TASK_RECORD: (
                _decision(
                    "owner_customer_id",
                    _D.DIRECT_OWNER,
                    value_projector=_one("owner_customer_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "last_outcome_ref?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_optional("last_outcome_ref"),
                    maximum=1,
                ),
            ),
            _R.REQUEST_UNIT_RECORD: (
                _decision(
                    "task_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="task_id",
                    target_record_code=_R.TASK_RECORD,
                    value_projector=_one("task_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "goal_source_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="goal_source_ref",
                    target_record_code=_R.MESSAGE_RECORD,
                    value_projector=_many("goal_source_refs"),
                    minimum=1,
                    unique=True,
                ),
                _decision(
                    "contextualization_ref?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_optional("contextualization_ref"),
                    maximum=1,
                ),
                _decision(
                    "constraint_refs[]",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_many("constraint_refs"),
                    unique=True,
                ),
                _decision(
                    "dependency_refs[]",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_many("dependency_refs"),
                    unique=True,
                ),
                _decision(
                    "input_binding_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="input_binding_ref",
                    target_record_code=_R.INPUT_BINDING_RECORD,
                    value_projector=_many("input_binding_refs"),
                    minimum=1,
                    unique=True,
                ),
                _decision(
                    "observation_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="observation_ref",
                    target_record_code=_R.OBSERVATION_RECORD,
                    value_projector=_many("observation_refs"),
                    unique=True,
                ),
                _decision(
                    "evidence_binding_refs[]",
                    _D.P0_FIRST_SLICE_MUST_BE_EMPTY,
                    value_projector=_many("evidence_binding_refs"),
                    maximum=0,
                ),
                _decision(
                    "pending_action_ref?",
                    _D.P0_FIRST_SLICE_MUST_BE_EMPTY,
                    value_projector=_optional("pending_action_ref"),
                    maximum=0,
                ),
                _decision(
                    "result_refs[]",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_many("result_refs"),
                    unique=True,
                ),
            ),
            _R.CONVERSATION_TASK_LINK_RECORD: (
                _decision(
                    "conversation_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="conversation_id",
                    target_record_code=_R.CONVERSATION_RECORD,
                    value_projector=_one("conversation_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "task_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="task_id",
                    target_record_code=_R.TASK_RECORD,
                    value_projector=_one("task_id"),
                    minimum=1,
                    maximum=1,
                ),
            ),
            _R.RUN_TASK_LINK_RECORD: (
                _decision(
                    "run_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="run_id",
                    target_record_code=_R.AGENT_RUN_RECORD,
                    value_projector=_one("run_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "task_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="task_id",
                    target_record_code=_R.TASK_RECORD,
                    value_projector=_one("task_id"),
                    minimum=1,
                    maximum=1,
                ),
            ),
            _R.INPUT_BINDING_RECORD: (
                _decision(
                    "source_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="source_ref",
                    target_record_code=_R.MESSAGE_RECORD,
                    value_projector=_many("source_refs"),
                    minimum=1,
                    unique=True,
                ),
                _decision(
                    "supersedes?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="supersedes",
                    target_record_code=_R.INPUT_BINDING_RECORD,
                    value_projector=_optional("supersedes"),
                    maximum=1,
                ),
                _decision(
                    "external request_unit_id",
                    _D.EXTERNAL_REQUIRED_P0_REFERENCE,
                    relation="request_unit_id",
                    target_record_code=_R.REQUEST_UNIT_RECORD,
                    minimum=1,
                    maximum=1,
                ),
            ),
            _R.MODEL_VISIBLE_TOOLSET_ARTIFACT: (),
            _R.AGENT_RUN_RECORD: (
                _decision(
                    "conversation_id?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="conversation_id",
                    target_record_code=_R.CONVERSATION_RECORD,
                    value_projector=_optional("conversation_id"),
                    maximum=1,
                ),
            ),
            _R.GATE_DECISION_RECORD: (
                _decision(
                    "context_manifest_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="context_manifest_id",
                    target_record_code=_R.CONTEXT_MANIFEST_RECORD,
                    value_projector=_one("context_manifest_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "argument_binding_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="argument_binding_ref",
                    target_record_code=_R.INPUT_BINDING_RECORD,
                    value_projector=_many("argument_binding_refs"),
                    unique=True,
                ),
                _decision(
                    "model_call_id,provider_tool_call_id?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_combined(
                        _one("model_call_id"),
                        _optional("provider_tool_call_id"),
                    ),
                    minimum=1,
                    maximum=2,
                ),
            ),
            _R.TOOL_CALL_RECORD: (
                _decision(
                    "run_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="run_id",
                    target_record_code=_R.AGENT_RUN_RECORD,
                    value_projector=_one("run_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "task_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="task_id",
                    target_record_code=_R.TASK_RECORD,
                    value_projector=_one("task_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "request_unit_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="request_unit_id",
                    target_record_code=_R.REQUEST_UNIT_RECORD,
                    value_projector=_one("request_unit_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "context_manifest_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="context_manifest_id",
                    target_record_code=_R.CONTEXT_MANIFEST_RECORD,
                    value_projector=_one("context_manifest_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "gate_decision_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="gate_decision_id",
                    target_record_code=_R.GATE_DECISION_RECORD,
                    value_projector=_one("gate_decision_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "argument_binding_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="argument_binding_ref",
                    target_record_code=_R.INPUT_BINDING_RECORD,
                    value_projector=_many("argument_binding_refs"),
                    minimum=1,
                    unique=True,
                ),
                _decision(
                    "model_call_id,provider_tool_call_id?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_combined(
                        _one("model_call_id"),
                        _optional("provider_tool_call_id"),
                    ),
                    minimum=1,
                    maximum=2,
                ),
                _decision(
                    "result_ref?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_optional("result_ref"),
                    maximum=1,
                ),
            ),
            _R.OBSERVATION_RECORD: (
                _decision(
                    "supersedes?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="supersedes",
                    target_record_code=_R.OBSERVATION_RECORD,
                    value_projector=_optional("supersedes"),
                    maximum=1,
                ),
                _decision(
                    "external source_tool_call_id",
                    _D.EXTERNAL_REQUIRED_P0_REFERENCE,
                    relation="source_tool_call_id",
                    target_record_code=_R.TOOL_CALL_RECORD,
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "external source_run_id",
                    _D.EXTERNAL_REQUIRED_P0_REFERENCE,
                    relation="source_run_id",
                    target_record_code=_R.AGENT_RUN_RECORD,
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "external source_task_id",
                    _D.EXTERNAL_REQUIRED_P0_REFERENCE,
                    relation="source_task_id",
                    target_record_code=_R.TASK_RECORD,
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "external source_request_unit_id",
                    _D.EXTERNAL_REQUIRED_P0_REFERENCE,
                    relation="source_request_unit_id",
                    target_record_code=_R.REQUEST_UNIT_RECORD,
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "raw_result_ref?",
                    _D.RESTRICTED_DIAGNOSTIC_CORRELATION,
                    value_projector=_optional("raw_result_ref"),
                    maximum=1,
                ),
                _decision(
                    "source_resource_ref",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_one("source_resource_ref"),
                    minimum=1,
                    maximum=1,
                ),
            ),
            _R.CONTEXT_MANIFEST_RECORD: (
                _decision(
                    "run_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="run_id",
                    target_record_code=_R.AGENT_RUN_RECORD,
                    value_projector=_one("run_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "selected_message_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="selected_message_ref",
                    target_record_code=_R.MESSAGE_RECORD,
                    value_projector=_many("selected_message_refs"),
                    unique=True,
                ),
                _decision(
                    "task_state_ref_and_version?.task_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="task_state_ref",
                    target_record_code=_R.TASK_RECORD,
                    value_projector=_nested_optional(
                        "task_state_ref_and_version",
                        "task_id",
                    ),
                    maximum=1,
                ),
                _decision(
                    "observation_refs_and_versions[].record_ref",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="observation_ref",
                    target_record_code=_R.OBSERVATION_RECORD,
                    value_projector=_nested_many(
                        "observation_refs_and_versions",
                        "record_ref",
                    ),
                    unique=True,
                ),
                _decision(
                    "model_visible_toolset_hash",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="model_visible_toolset_hash",
                    target_record_code=_R.MODEL_VISIBLE_TOOLSET_ARTIFACT,
                    value_projector=_one("model_visible_toolset_hash"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "evidence_refs_and_versions[],action_record_refs[]",
                    _D.P0_FIRST_SLICE_MUST_BE_EMPTY,
                    value_projector=_combined(
                        _many("evidence_refs_and_versions"),
                        _many("action_record_refs"),
                    ),
                    maximum=0,
                ),
                _decision(
                    "model_call_id,truncation_decisions[].source_ref",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_combined(
                        _one("model_call_id"),
                        _nested_many("truncation_decisions", "source_ref"),
                    ),
                    minimum=1,
                ),
            ),
            _R.TRACE_EVENT_RECORD: (
                _decision(
                    "run_id",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="run_id",
                    target_record_code=_R.AGENT_RUN_RECORD,
                    value_projector=_one("run_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "message_ref?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="message_ref",
                    target_record_code=_R.MESSAGE_RECORD,
                    value_projector=_optional("message_ref"),
                    maximum=1,
                ),
                _decision(
                    "task_id?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="task_id",
                    target_record_code=_R.TASK_RECORD,
                    value_projector=_optional("task_id"),
                    maximum=1,
                ),
                _decision(
                    "request_unit_id?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="request_unit_id",
                    target_record_code=_R.REQUEST_UNIT_RECORD,
                    value_projector=_optional("request_unit_id"),
                    maximum=1,
                ),
                _decision(
                    "input_binding_ref?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="input_binding_ref",
                    target_record_code=_R.INPUT_BINDING_RECORD,
                    value_projector=_optional("input_binding_ref"),
                    maximum=1,
                ),
                _decision(
                    "context_manifest_id?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="context_manifest_id",
                    target_record_code=_R.CONTEXT_MANIFEST_RECORD,
                    value_projector=_optional("context_manifest_id"),
                    maximum=1,
                ),
                _decision(
                    "model_visible_toolset_hash?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="model_visible_toolset_hash",
                    target_record_code=_R.MODEL_VISIBLE_TOOLSET_ARTIFACT,
                    value_projector=_optional("model_visible_toolset_hash"),
                    maximum=1,
                ),
                _decision(
                    "argument_binding_refs[]",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="argument_binding_ref",
                    target_record_code=_R.INPUT_BINDING_RECORD,
                    value_projector=_many("argument_binding_refs"),
                    unique=True,
                ),
                _decision(
                    "tool_call_id?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="tool_call_id",
                    target_record_code=_R.TOOL_CALL_RECORD,
                    value_projector=_optional("tool_call_id"),
                    maximum=1,
                ),
                _decision(
                    "observation_ref?",
                    _D.TOP_LEVEL_P0_REFERENCE,
                    relation="observation_ref",
                    target_record_code=_R.OBSERVATION_RECORD,
                    value_projector=_optional("observation_ref"),
                    maximum=1,
                ),
                _decision(
                    "accepted_delta_ref?",
                    _D.LOGICAL_CHILD_CORRELATION,
                    value_projector=_optional("accepted_delta_ref"),
                    maximum=1,
                ),
                _decision(
                    "model_call_id?,presentation_plan_ref?,case_id?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_combined(
                        _optional("model_call_id"),
                        _optional("presentation_plan_ref"),
                        _optional("case_id"),
                    ),
                    maximum=3,
                ),
            ),
            _R.EVAL_RESULT_RECORD: (
                _decision(
                    "trace_ref?",
                    _D.CONDITIONAL_PAYLOAD_CORRELATION,
                    value_projector=_optional("trace_ref"),
                    maximum=1,
                ),
            ),
            _R.EVAL_EXECUTION_FAILURE_RECORD: (
                _decision(
                    "trace_ref?",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_optional("trace_ref"),
                    maximum=1,
                ),
                _decision(
                    "diagnostic_ref?",
                    _D.RESTRICTED_DIAGNOSTIC_CORRELATION,
                    value_projector=_optional("diagnostic_ref"),
                    maximum=1,
                ),
            ),
        }
    )
)

_CHILD_PROJECTIONS: Mapping[P0LogicalChildCode, tuple[_P0ProjectionDecision, ...]] = (
    MappingProxyType(
        {
            P0LogicalChildCode.TASK_STATE_TRANSITION: (
                _decision(
                    "task_id",
                    _D.PARENT_FIELD_EQUALITY,
                    value_projector=_one("task_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "request_unit_id",
                    _D.CHILD_TOP_LEVEL_P0_REFERENCE,
                    relation="request_unit_id",
                    target_record_code=_R.REQUEST_UNIT_RECORD,
                    value_projector=_one("request_unit_id"),
                    minimum=1,
                    maximum=1,
                ),
                _decision(
                    "reason_ref",
                    _D.PAYLOAD_CORRELATION,
                    value_projector=_one("reason_ref"),
                    minimum=1,
                    maximum=1,
                ),
            ),
            P0LogicalChildCode.TOOL_ATTEMPT_RECORD: (
                _decision(
                    "tool_call_id",
                    _D.PARENT_FIELD_EQUALITY,
                    value_projector=_one("tool_call_id"),
                    minimum=1,
                    maximum=1,
                ),
            ),
        }
    )
)


def _record_spec(
    code: P0RecordCode,
    source_model: type[ContractModel],
    identity_fields: tuple[str, ...],
    *,
    direct_owner_field: str | None = None,
    version_mirror_field: str | None = None,
    allowed_child_codes: tuple[P0LogicalChildCode, ...] = (),
    specialized_version_validator: Callable[[ContractModel], bool] | None = None,
) -> P0RecordSchemaSpec:
    return P0RecordSchemaSpec(
        record_code=code,
        record_schema_version=f"{code.value}.p0.v1",
        source_model=source_model,
        identity_fields=identity_fields,
        direct_owner_field=direct_owner_field,
        projection_decisions=_TOP_LEVEL_PROJECTIONS[code],
        version_mirror_field=version_mirror_field,
        allowed_child_codes=allowed_child_codes,
        specialized_version_validator=specialized_version_validator,
    )


_NON_RU_REGISTRY = {
    P0RecordCode.CONVERSATION_RECORD: _record_spec(
        P0RecordCode.CONVERSATION_RECORD,
        ConversationRecord,
        ("conversation_id",),
        direct_owner_field="owner_customer_id",
        version_mirror_field="schema_version",
    ),
    P0RecordCode.MESSAGE_RECORD: _record_spec(
        P0RecordCode.MESSAGE_RECORD,
        MessageRecord,
        ("message_id",),
        version_mirror_field="schema_version",
    ),
    P0RecordCode.TASK_RECORD: _record_spec(
        P0RecordCode.TASK_RECORD,
        TaskRecord,
        ("task_id",),
        direct_owner_field="owner_customer_id",
        allowed_child_codes=(P0LogicalChildCode.TASK_STATE_TRANSITION,),
    ),
    P0RecordCode.REQUEST_UNIT_RECORD: _record_spec(
        P0RecordCode.REQUEST_UNIT_RECORD,
        RequestUnitRecord,
        ("request_unit_id",),
    ),
    P0RecordCode.CONVERSATION_TASK_LINK_RECORD: _record_spec(
        P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
        ConversationTaskLinkRecord,
        ("conversation_id", "task_id", "linked_at"),
        version_mirror_field="schema_version",
    ),
    P0RecordCode.RUN_TASK_LINK_RECORD: _record_spec(
        P0RecordCode.RUN_TASK_LINK_RECORD,
        RunTaskLinkRecord,
        ("run_id", "task_id"),
        version_mirror_field="schema_version",
    ),
    P0RecordCode.INPUT_BINDING_RECORD: _record_spec(
        P0RecordCode.INPUT_BINDING_RECORD,
        InputBinding,
        ("binding_id",),
    ),
    P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT: _record_spec(
        P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
        ModelVisibleToolsetArtifact,
        ("model_visible_toolset_hash",),
        specialized_version_validator=lambda record: (
            record.artifact_schema_version
            == MODEL_VISIBLE_TOOLSET_ARTIFACT_SCHEMA_VERSION
        ),
    ),
    P0RecordCode.AGENT_RUN_RECORD: _record_spec(
        P0RecordCode.AGENT_RUN_RECORD,
        AgentRunRecord,
        ("run_id",),
    ),
    P0RecordCode.GATE_DECISION_RECORD: _record_spec(
        P0RecordCode.GATE_DECISION_RECORD,
        GateDecision,
        ("gate_decision_id",),
    ),
    P0RecordCode.TOOL_CALL_RECORD: _record_spec(
        P0RecordCode.TOOL_CALL_RECORD,
        ToolCallRecord,
        ("tool_call_id",),
        allowed_child_codes=(P0LogicalChildCode.TOOL_ATTEMPT_RECORD,),
    ),
    P0RecordCode.OBSERVATION_RECORD: _record_spec(
        P0RecordCode.OBSERVATION_RECORD,
        OrderObservation,
        ("observation_id",),
    ),
    P0RecordCode.CONTEXT_MANIFEST_RECORD: _record_spec(
        P0RecordCode.CONTEXT_MANIFEST_RECORD,
        ContextManifest,
        ("context_manifest_id",),
    ),
    P0RecordCode.TRACE_EVENT_RECORD: _record_spec(
        P0RecordCode.TRACE_EVENT_RECORD,
        TraceEvent,
        ("trace_event_id",),
    ),
    P0RecordCode.EVAL_RESULT_RECORD: _record_spec(
        P0RecordCode.EVAL_RESULT_RECORD,
        EvalResultRecord,
        ("eval_run_id", "case_id", "lane", "attempt"),
        version_mirror_field="schema_version",
    ),
    P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD: _record_spec(
        P0RecordCode.EVAL_EXECUTION_FAILURE_RECORD,
        EvalExecutionFailureRecord,
        (
            "eval_run_id",
            "lane",
            "case_id",
            "attempt",
            "failure_phase",
            "safe_error_code",
            "occurred_at",
        ),
        version_mirror_field="schema_version",
    ),
}

_NON_RU_PERSISTENCE_REGISTRY: Mapping[
    P0RecordCode,
    P0RecordSchemaSpec,
] = MappingProxyType(_NON_RU_REGISTRY)
del _NON_RU_REGISTRY

_NON_RU_CHILD_SPECS = {
    P0LogicalChildCode.TASK_STATE_TRANSITION: _P0LogicalChildSchemaSpec(
        child_code=P0LogicalChildCode.TASK_STATE_TRANSITION,
        source_model=TaskStateTransition,
        parent_record_code=P0RecordCode.TASK_RECORD,
        identity_fields=("task_id", "request_unit_id", "result_state_version"),
        closure_strategy=_ClosureStrategy.GRAPH_REQUIRED,
        projection_decisions=_CHILD_PROJECTIONS[
            P0LogicalChildCode.TASK_STATE_TRANSITION
        ],
    ),
    P0LogicalChildCode.TOOL_ATTEMPT_RECORD: _P0LogicalChildSchemaSpec(
        child_code=P0LogicalChildCode.TOOL_ATTEMPT_RECORD,
        source_model=ToolAttemptRecord,
        parent_record_code=P0RecordCode.TOOL_CALL_RECORD,
        identity_fields=("tool_call_id", "attempt_no"),
        closure_strategy=_ClosureStrategy.LOCAL_CLOSED,
        projection_decisions=_CHILD_PROJECTIONS[P0LogicalChildCode.TOOL_ATTEMPT_RECORD],
    ),
}

_NON_RU_LOGICAL_CHILD_SPECS: Mapping[
    P0LogicalChildCode,
    _P0LogicalChildSchemaSpec,
] = (
    MappingProxyType(_NON_RU_CHILD_SPECS)
)
del _NON_RU_CHILD_SPECS


def _raise_signal(category: P0PersistenceIntegrityCategory) -> None:
    raise _IntegritySignal(category)


def _logical_identity(
    record: ContractModel,
    identity_fields: tuple[str, ...],
) -> LogicalIdentity:
    data = record.model_dump(mode="json")
    return tuple((field_name, data[field_name]) for field_name in identity_fields)


def _strict_record(
    spec: P0RecordSchemaSpec,
    record: ContractModel,
) -> ContractModel:
    if type(record) is not spec.source_model:
        _raise_signal(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
    if (
        spec.specialized_version_validator is not None
        and not spec.specialized_version_validator(record)
    ):
        _raise_signal(P0PersistenceIntegrityCategory.SPECIALIZED_VERSION_MISMATCH)

    category: P0PersistenceIntegrityCategory | None = None
    validated: ContractModel | None = None
    try:
        validated = spec.source_model.model_validate_json(
            record.model_dump_json(),
            strict=True,
        )
    except (
        TypeError,
        ValueError,
        ValidationError,
        RecursionError,
        PydanticSerializationError,
    ):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if validated is None:
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)

    if (
        spec.version_mirror_field is not None
        and getattr(validated, spec.version_mirror_field) != spec.record_schema_version
    ):
        _raise_signal(P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH)
    return validated


def _projected_values(
    rule: _P0ProjectionDecision,
    data: Mapping[str, Any],
) -> tuple[JsonScalar, ...]:
    if rule.value_projector is None:
        return ()
    values = rule.value_projector(data)
    count = len(values)
    if count < rule.minimum or (rule.maximum is not None and count > rule.maximum):
        _raise_signal(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
    if rule.unique:
        keys = tuple(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            for value in values
        )
        if len(keys) != len(set(keys)):
            _raise_signal(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
    return values


def _reference_for_value(
    rule: _P0ProjectionDecision,
    value: JsonScalar,
) -> P0RecordReference:
    if rule.relation is None or rule.target_record_code is None:
        _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
    target_spec = _NON_RU_PERSISTENCE_REGISTRY[rule.target_record_code]
    if len(target_spec.identity_fields) != 1:
        _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
    return P0RecordReference(
        relation=rule.relation,
        target_record_code=rule.target_record_code,
        target_logical_identity=((target_spec.identity_fields[0], value),),
    )


def _reference_key(
    reference: P0RecordReference,
) -> tuple[str, str, str]:
    return (
        reference.relation,
        reference.target_record_code.value,
        json.dumps(
            reference.target_logical_identity,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


def _strict_reference(
    reference: P0RecordReference,
) -> P0RecordReference:
    if type(reference) is not P0RecordReference:
        _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)

    category: P0PersistenceIntegrityCategory | None = None
    validated: P0RecordReference | None = None
    try:
        raw_json = reference.model_dump_json(warnings=False)
        validated = P0RecordReference.model_validate_json(
            raw_json,
            strict=True,
        )
    except (
        TypeError,
        ValueError,
        ValidationError,
        RecursionError,
        PydanticSerializationError,
    ):
        category = P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
    if category is not None:
        _raise_signal(category)
    if validated is None:
        _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
    return validated


def _normalize_references(
    references: tuple[P0RecordReference, ...],
    *,
    collapse_duplicates: bool = False,
) -> tuple[P0RecordReference, ...]:
    by_key: dict[tuple[str, str, str], P0RecordReference] = {}
    for reference in references:
        canonical = _strict_reference(reference)
        key = _reference_key(canonical)
        if key in by_key and not collapse_duplicates:
            _raise_signal(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        by_key[key] = canonical
    return tuple(by_key[key] for key in sorted(by_key))


def _canonical_target_identity(
    reference: P0RecordReference,
    target_spec: P0RecordSchemaSpec,
) -> P0RecordReference:
    canonical_identity: list[tuple[str, JsonScalar]] = []
    for field_name, value in reference.target_logical_identity:
        field = target_spec.source_model.model_fields.get(field_name)
        if field is None:
            _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)

        category: P0PersistenceIntegrityCategory | None = None
        canonical_value: JsonScalar = None
        raw_value: str | None = None
        canonical_raw: str | None = None
        try:
            raw_value = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            adapter = TypeAdapter(field.rebuild_annotation())
            validated_value = adapter.validate_json(raw_value, strict=True)
            canonical_raw = adapter.dump_json(
                validated_value,
                warnings="error",
            ).decode("utf-8")
            canonical_value = json.loads(canonical_raw)
        except (
            TypeError,
            ValueError,
            ValidationError,
            RecursionError,
            UnicodeDecodeError,
            PydanticSerializationError,
        ):
            category = P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        if category is not None:
            _raise_signal(category)
        if raw_value is None or canonical_raw is None or raw_value != canonical_raw:
            _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        canonical_identity.append((field_name, canonical_value))

    return P0RecordReference(
        relation=reference.relation,
        target_record_code=reference.target_record_code,
        target_logical_identity=tuple(canonical_identity),
    )


def _validate_external_references(
    spec: P0RecordSchemaSpec,
    external_references: tuple[P0RecordReference, ...],
) -> tuple[P0RecordReference, ...]:
    rules = tuple(
        rule
        for rule in spec.projection_decisions
        if rule.classification is _D.EXTERNAL_REQUIRED_P0_REFERENCE
    )
    normalized = _normalize_references(external_references)
    if len(normalized) != len(rules):
        _raise_signal(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)

    accepted: list[P0RecordReference] = []
    for rule in rules:
        matches = tuple(
            reference for reference in normalized if reference.relation == rule.relation
        )
        if len(matches) != 1:
            _raise_signal(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
        reference = matches[0]
        if reference.target_record_code is not rule.target_record_code:
            _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        target_spec = _NON_RU_PERSISTENCE_REGISTRY[
            reference.target_record_code
        ]
        actual_fields = tuple(
            field_name for field_name, _ in reference.target_logical_identity
        )
        if actual_fields != target_spec.identity_fields:
            _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
        accepted.append(_canonical_target_identity(reference, target_spec))
    return tuple(accepted)


def _top_level_projection(
    spec: P0RecordSchemaSpec,
    record: ContractModel,
) -> tuple[str | None, tuple[P0RecordReference, ...]]:
    data = record.model_dump(mode="json")
    direct_owner: str | None = None
    references: list[P0RecordReference] = []
    for rule in spec.projection_decisions:
        values = _projected_values(rule, data)
        if rule.classification is _D.DIRECT_OWNER:
            if len(values) != 1 or not isinstance(values[0], str):
                _raise_signal(P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH)
            direct_owner = values[0]
        elif rule.classification is _D.TOP_LEVEL_P0_REFERENCE:
            references.extend(_reference_for_value(rule, value) for value in values)
        elif rule.classification is _D.P0_FIRST_SLICE_MUST_BE_EMPTY:
            if values:
                _raise_signal(P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH)
    return direct_owner, _normalize_references(tuple(references))


def _child_payloads(
    parent_spec: P0RecordSchemaSpec,
    parent_record: ContractModel,
    parent_identity: LogicalIdentity,
    logical_children: tuple[ContractModel, ...],
) -> tuple[
    tuple[P0LogicalChildPayload, ...],
    tuple[P0RecordReference, ...],
]:
    validated_children: list[tuple[_P0LogicalChildSchemaSpec, ContractModel]] = []
    for child in logical_children:
        child_spec = next(
            (
                spec
                for spec in P0_LOGICAL_CHILD_SPECS.values()
                if type(child) is spec.source_model
            ),
            None,
        )
        if (
            child_spec is None
            or child_spec.child_code not in parent_spec.allowed_child_codes
            or child_spec.parent_record_code is not parent_spec.record_code
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

        category: P0PersistenceIntegrityCategory | None = None
        validated: ContractModel | None = None
        try:
            validated = child_spec.source_model.model_validate_json(
                child.model_dump_json(),
                strict=True,
            )
        except (
            TypeError,
            ValueError,
            ValidationError,
            RecursionError,
            PydanticSerializationError,
        ):
            category = P0PersistenceIntegrityCategory.CHILD_MISMATCH
        if category is not None:
            _raise_signal(category)
        if validated is None:
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        validated_children.append((child_spec, validated))

    if not parent_spec.allowed_child_codes and validated_children:
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

    child_records = tuple(child for _, child in validated_children)
    if parent_spec.record_code is P0RecordCode.REQUEST_UNDERSTANDING_RECORD:
        parent = parent_record
        accepted_refs = tuple(parent.accepted_delta_refs)
        child_ids = tuple(child.accepted_delta_id for child in child_records)
        if (
            len(accepted_refs) != len(set(accepted_refs))
            or len(child_ids) != len(set(child_ids))
            or set(accepted_refs) != set(child_ids)
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        for child in child_records:
            if child.message_ref != parent.message_ref:
                _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
            matches = tuple(
                candidate
                for candidate in parent.candidate_validation
                if candidate.candidate_ref == child.candidate_ref
            )
            if (
                len(matches) != 1
                or matches[0].decision is not CandidateValidationDecision.ACCEPT
            ):
                _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        validated_children.sort(key=lambda item: str(item[1].accepted_delta_id))
    elif parent_spec.record_code is P0RecordCode.TASK_RECORD:
        parent = parent_record
        identities = tuple(
            (
                child.task_id,
                child.request_unit_id,
                child.result_state_version,
            )
            for child in child_records
        )
        result_versions = tuple(child.result_state_version for child in child_records)
        if (
            len(identities) != len(set(identities))
            or len(result_versions) != len(set(result_versions))
            or any(child.task_id != parent.task_id for child in child_records)
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        validated_children.sort(
            key=lambda item: (
                item[1].result_state_version,
                str(item[1].request_unit_id),
            )
        )
    elif parent_spec.record_code is P0RecordCode.TOOL_CALL_RECORD:
        parent = parent_record
        attempt_numbers = tuple(child.attempt_no for child in child_records)
        if (
            any(child.tool_call_id != parent.tool_call_id for child in child_records)
            or tuple(sorted(attempt_numbers))
            != tuple(range(1, parent.attempt_count + 1))
            or len(attempt_numbers) != len(set(attempt_numbers))
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        validated_children.sort(key=lambda item: item[1].attempt_no)

    payloads: list[P0LogicalChildPayload] = []
    child_references: list[P0RecordReference] = []
    for child_spec, validated in validated_children:
        child_data = validated.model_dump(mode="json")
        for rule in child_spec.projection_decisions:
            values = _projected_values(rule, child_data)
            if rule.classification is _D.CHILD_TOP_LEVEL_P0_REFERENCE:
                child_references.extend(
                    _reference_for_value(rule, value) for value in values
                )
        payloads.append(
            P0LogicalChildPayload(
                child_code=child_spec.child_code,
                parent_record_code=parent_spec.record_code,
                parent_logical_identity=parent_identity,
                logical_identity=_logical_identity(
                    validated,
                    child_spec.identity_fields,
                ),
                data=validated.model_dump(mode="json"),
            )
        )
    return (
        tuple(payloads),
        _normalize_references(
            tuple(child_references),
            collapse_duplicates=True,
        ),
    )


def _build_envelope(
    record_code: P0RecordCode,
    record: ContractModel,
    *,
    external_references: tuple[P0RecordReference, ...],
    logical_children: tuple[ContractModel, ...],
) -> P0PersistenceEnvelope:
    spec = _NON_RU_PERSISTENCE_REGISTRY.get(record_code)
    if spec is None:
        category = (
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
            if record_code is P0RecordCode.REQUEST_UNDERSTANDING_RECORD
            else P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
        )
        _raise_signal(category)
    validated = _strict_record(spec, record)
    identity = _logical_identity(validated, spec.identity_fields)
    owner, source_references = _top_level_projection(spec, validated)
    external = _validate_external_references(
        spec,
        external_references,
    )
    children, child_references = _child_payloads(
        spec,
        validated,
        identity,
        logical_children,
    )
    references = _normalize_references(
        (*source_references, *external, *child_references)
    )
    return P0PersistenceEnvelope(
        record_code=record_code,
        record_schema_version=spec.record_schema_version,
        logical_identity=identity,
        direct_owner_customer_id=owner,
        record_references=references,
        payload=P0VersionedPayload(
            record_code=record_code,
            record_schema_version=spec.record_schema_version,
            data=validated.model_dump(mode="json"),
            logical_children=children,
        ),
    )


def _public_error(
    category: P0PersistenceIntegrityCategory,
    correlation_ref: UUID,
) -> P0PersistenceIntegrityError:
    return P0PersistenceIntegrityError(category, correlation_ref)


def encode_persistence_record(
    record_code: P0RecordCode,
    record: ContractModel,
    *,
    external_references: tuple[P0RecordReference, ...] = (),
    logical_children: tuple[ContractModel, ...] = (),
) -> P0PersistenceEnvelope:
    category: P0PersistenceIntegrityCategory | None = None
    result: P0PersistenceEnvelope | None = None
    try:
        if not isinstance(record_code, P0RecordCode):
            _raise_signal(P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE)
        if record_code is P0RecordCode.REQUEST_UNDERSTANDING_RECORD:
            _raise_signal(
                P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
            )
        result = _build_envelope(
            record_code,
            record,
            external_references=external_references,
            logical_children=logical_children,
        )
    except _IntegritySignal as signal:
        category = signal.category
    if category is not None:
        raise _public_error(category, uuid4())
    if result is None:
        raise _public_error(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
            uuid4(),
        )
    return result


def _is_native_json_scalar(value: object) -> bool:
    if value is None or type(value) in (str, bool, int):
        return True
    return type(value) is float and isfinite(value)


def _is_native_json_value(
    value: object,
    *,
    frozen_containers: bool,
) -> bool:
    pending: list[tuple[object, bool]] = [(value, False)]
    active_container_ids: set[int] = set()
    completed_container_ids: set[int] = set()
    while pending:
        current, exiting = pending.pop()
        if _is_native_json_scalar(current):
            continue

        is_mapping = isinstance(current, Mapping)
        is_sequence = (
            type(current) is FrozenJsonList
            if frozen_containers
            else type(current) is list
        )
        if is_mapping:
            if frozen_containers and type(current) is not FrozenJsonDict:
                return False
        elif not is_sequence:
            return False

        container_id = id(current)
        if exiting:
            active_container_ids.remove(container_id)
            completed_container_ids.add(container_id)
            continue
        if container_id in active_container_ids:
            return False
        if container_id in completed_container_ids:
            continue

        active_container_ids.add(container_id)
        pending.append((current, True))
        if is_mapping:
            items = tuple(current.items())
            keys = tuple(key for key, _ in items)
            if any(type(key) is not str for key in keys) or len(keys) != len(set(keys)):
                return False
            pending.extend((nested, False) for _, nested in items)
        else:
            pending.extend((nested, False) for nested in current)
    return True


def _is_native_logical_identity(value: object) -> bool:
    if type(value) is not tuple:
        return False
    return all(
        type(item) is tuple
        and len(item) == 2
        and type(item[0]) is str
        and _is_native_json_scalar(item[1])
        for item in value
    )


def _envelope_has_native_json(envelope: P0PersistenceEnvelope) -> bool:
    if (
        type(envelope) is not P0PersistenceEnvelope
        or type(envelope.record_code) is not P0RecordCode
        or type(envelope.record_schema_version) is not str
        or not _is_native_logical_identity(envelope.logical_identity)
        or (
            envelope.direct_owner_customer_id is not None
            and type(envelope.direct_owner_customer_id) is not str
        )
        or type(envelope.record_references) is not tuple
        or type(envelope.payload) is not P0VersionedPayload
    ):
        return False

    for reference in envelope.record_references:
        if (
            type(reference) is not P0RecordReference
            or type(reference.relation) is not str
            or type(reference.target_record_code) is not P0RecordCode
            or not _is_native_logical_identity(reference.target_logical_identity)
        ):
            return False

    payload = envelope.payload
    if (
        type(payload.record_code) is not P0RecordCode
        or type(payload.record_schema_version) is not str
        or not _is_native_json_value(
            payload.data,
            frozen_containers=True,
        )
        or type(payload.logical_children) is not tuple
    ):
        return False

    for child in payload.logical_children:
        if (
            type(child) is not P0LogicalChildPayload
            or type(child.child_code) is not P0LogicalChildCode
            or type(child.parent_record_code) is not P0RecordCode
            or not _is_native_logical_identity(child.parent_logical_identity)
            or not _is_native_logical_identity(child.logical_identity)
            or not _is_native_json_value(
                child.data,
                frozen_containers=True,
            )
        ):
            return False
    return True


def _json_input(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
) -> str | bytes:
    if isinstance(envelope, P0PersistenceEnvelope):
        category: P0PersistenceIntegrityCategory | None = None
        raw: str | None = None
        try:
            if _envelope_has_native_json(envelope):
                raw = envelope.model_dump_json(warnings="error")
            else:
                category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        except (
            AttributeError,
            TypeError,
            ValueError,
            RecursionError,
            PydanticSerializationError,
        ):
            category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        if category is not None:
            _raise_signal(category)
        if raw is None:
            _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)
        return raw
    if isinstance(envelope, Mapping):
        category: P0PersistenceIntegrityCategory | None = None
        raw: str | None = None
        try:
            if _is_native_json_value(
                envelope,
                frozen_containers=False,
            ):
                raw = json.dumps(
                    thaw_json_value(envelope),
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            else:
                category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        except (
            TypeError,
            ValueError,
            RecursionError,
            PydanticSerializationError,
        ):
            category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        if category is not None:
            _raise_signal(category)
        if raw is None:
            _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)
        return raw
    if isinstance(envelope, (str, bytes)):
        return envelope
    _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)


def _classify_outer(
    raw_json: str | bytes,
    expected_record_code: P0RecordCode,
) -> tuple[P0RecordCode, P0RecordSchemaSpec, dict[str, Any]]:
    category: P0PersistenceIntegrityCategory | None = None
    parsed: object = None
    try:
        parsed = json.loads(raw_json)
    except (
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if not isinstance(parsed, dict):
        _raise_signal(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)

    if "record_code" not in parsed:
        _raise_signal(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)
    raw_code = parsed["record_code"]
    try:
        code = P0RecordCode(raw_code)
    except (TypeError, ValueError):
        code = None
    if code is None:
        _raise_signal(P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE)
    if code is not expected_record_code:
        _raise_signal(P0PersistenceIntegrityCategory.RECORD_CODE_MISMATCH)

    if "record_schema_version" not in parsed:
        _raise_signal(P0PersistenceIntegrityCategory.MISSING_RECORD_SCHEMA_VERSION)
    spec = _NON_RU_PERSISTENCE_REGISTRY[code]
    raw_version = parsed["record_schema_version"]
    if raw_version != spec.record_schema_version:
        known_versions = {
            item.record_schema_version
            for item in _NON_RU_PERSISTENCE_REGISTRY.values()
        }
        category = (
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            if raw_version in known_versions
            else P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
        )
        _raise_signal(category)
    return code, spec, parsed


def _envelope_validation_category(
    error: ValidationError,
) -> P0PersistenceIntegrityCategory:
    for detail in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = detail.get("loc", ())
        if (
            isinstance(location, tuple)
            and len(location) >= 2
            and location[0] == "payload"
            and location[1] == "logical_children"
        ):
            return P0PersistenceIntegrityCategory.CHILD_MISMATCH
    return P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED


def _json_mapping_text(
    value: Mapping[str, JsonValue],
    *,
    failure_category: P0PersistenceIntegrityCategory,
) -> str:
    category: P0PersistenceIntegrityCategory | None = None
    raw: str | None = None
    try:
        raw = json.dumps(
            thaw_json_value(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError):
        category = failure_category
    if category is not None:
        _raise_signal(category)
    if raw is None:
        _raise_signal(failure_category)
    return raw


def _decode(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
    expected_record_code: P0RecordCode,
) -> DecodedP0PersistenceRecord:
    raw_json = _json_input(envelope)
    code, spec, outer_data = _classify_outer(
        raw_json,
        expected_record_code,
    )
    inner_data = outer_data.get("payload")
    if (
        not isinstance(inner_data, dict)
        or inner_data.get("record_code") != code.value
        or inner_data.get("record_schema_version") != spec.record_schema_version
    ):
        _raise_signal(P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH)

    category: P0PersistenceIntegrityCategory | None = None
    validated_envelope: P0PersistenceEnvelope | None = None
    try:
        validated_envelope = P0PersistenceEnvelope.model_validate_json(
            raw_json,
            strict=True,
        )
    except ValidationError as error:
        category = _envelope_validation_category(error)
    except (TypeError, ValueError, RecursionError):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if validated_envelope is None:
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)

    if (
        validated_envelope.payload.record_code is not code
        or validated_envelope.payload.record_schema_version
        != spec.record_schema_version
    ):
        _raise_signal(P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH)

    source_json = _json_mapping_text(
        validated_envelope.payload.data,
        failure_category=(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED),
    )
    source_record: ContractModel | None = None
    category = None
    try:
        source_record = spec.source_model.model_validate_json(
            source_json,
            strict=True,
        )
    except (TypeError, ValueError, ValidationError, RecursionError):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if source_record is None:
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)

    children: list[ContractModel] = []
    for child_payload in validated_envelope.payload.logical_children:
        child_spec = P0_LOGICAL_CHILD_SPECS.get(child_payload.child_code)
        if child_spec is None:
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        child_json = _json_mapping_text(
            child_payload.data,
            failure_category=P0PersistenceIntegrityCategory.CHILD_MISMATCH,
        )
        child: ContractModel | None = None
        category = None
        try:
            child = child_spec.source_model.model_validate_json(
                child_json,
                strict=True,
            )
        except (TypeError, ValueError, ValidationError, RecursionError):
            category = P0PersistenceIntegrityCategory.CHILD_MISMATCH
        if category is not None:
            _raise_signal(category)
        if child is None:
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        children.append(child)

    external_relations = {
        rule.relation
        for rule in spec.projection_decisions
        if rule.classification is _D.EXTERNAL_REQUIRED_P0_REFERENCE
    }
    external_references = tuple(
        reference
        for reference in validated_envelope.record_references
        if reference.relation in external_relations
    )
    expected = _build_envelope(
        code,
        source_record,
        external_references=external_references,
        logical_children=tuple(children),
    )
    if expected.logical_identity != validated_envelope.logical_identity:
        _raise_signal(P0PersistenceIntegrityCategory.IDENTITY_MISMATCH)
    if expected.direct_owner_customer_id != validated_envelope.direct_owner_customer_id:
        _raise_signal(P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH)
    if expected.record_references != validated_envelope.record_references:
        _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
    if expected.payload.logical_children != validated_envelope.payload.logical_children:
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    return DecodedP0PersistenceRecord(
        record_code=code,
        record_schema_version=spec.record_schema_version,
        source_record=source_record,
        logical_children=tuple(children),
    )


def decode_persistence_record(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
    *,
    expected_record_code: P0RecordCode,
    correlation_ref: UUID,
) -> DecodedP0PersistenceRecord:
    if type(correlation_ref) is not UUID:
        raise TypeError("correlation_ref must be UUID")
    if expected_record_code is P0RecordCode.REQUEST_UNDERSTANDING_RECORD:
        raise _public_error(
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION,
            correlation_ref,
        )

    category: P0PersistenceIntegrityCategory | None = None
    result: DecodedP0PersistenceRecord | None = None
    try:
        result = _decode(envelope, expected_record_code)
    except _IntegritySignal as signal:
        category = signal.category
    if category is not None:
        raise _public_error(category, correlation_ref)
    if result is None:
        raise _public_error(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
            correlation_ref,
        )
    return result


# Request Understanding remains an exact-version-only codec surface. Generic
# codec entry points above intentionally serve only the 16 non-RU families.
from pydantic import BaseModel as _P0V2BaseModel

from mini_agent.core.task_state import (
    AcceptedTaskDeltaV2 as _AcceptedTaskDeltaV2,
    RequestUnderstandingRecordV2 as _RequestUnderstandingRecordV2,
)


def _request_understanding_v2_resolved_source_refs(
    data: Mapping[str, Any],
) -> tuple[JsonScalar, ...]:
    return tuple(
        candidate["source_ref"]
        for candidate in data["contextualization"][
            "resolved_reference_candidates"
        ]
    )


def _request_understanding_v2_context_source_refs(
    data: Mapping[str, Any],
) -> tuple[JsonScalar, ...]:
    return tuple(data["contextualization"]["source_message_refs"])


def _request_understanding_v2_input_source_refs(
    data: Mapping[str, Any],
) -> tuple[JsonScalar, ...]:
    return tuple(
        input_candidate["source_ref"]
        for candidate in data["task_delta_candidates"]
        for input_candidate in candidate["input_candidates"]
    )


_REQUEST_UNDERSTANDING_V2_PROJECTIONS = tuple(
    (
        _decision(
            "run_id",
            _D.TOP_LEVEL_P0_REFERENCE,
            relation="run_id",
            target_record_code=_R.AGENT_RUN_RECORD,
            value_projector=_one("run_id"),
            minimum=1,
            maximum=1,
        ),
        _decision(
            "message_ref",
            _D.TOP_LEVEL_P0_REFERENCE,
            relation="message_ref",
            target_record_code=_R.MESSAGE_RECORD,
            value_projector=_one("message_ref"),
            minimum=1,
            maximum=1,
        ),
        _decision(
            "contextualization.resolved_reference_candidates[].source_ref",
            _D.TOP_LEVEL_P0_REFERENCE,
            relation="contextualization_resolved_source_ref",
            target_record_code=_R.MESSAGE_RECORD,
            value_projector=_request_understanding_v2_resolved_source_refs,
        ),
        _decision(
            "contextualization.source_message_refs[]",
            _D.TOP_LEVEL_P0_REFERENCE,
            relation="contextualization_source_message_ref",
            target_record_code=_R.MESSAGE_RECORD,
            value_projector=_request_understanding_v2_context_source_refs,
            minimum=1,
            unique=True,
        ),
        _decision(
            "task_delta_candidates[].input_candidates[].source_ref",
            _D.TOP_LEVEL_P0_REFERENCE,
            relation="task_delta_input_source_ref",
            target_record_code=_R.MESSAGE_RECORD,
            value_projector=_request_understanding_v2_input_source_refs,
        ),
        _decision(
            "accepted_delta_refs[]",
            _D.LOGICAL_CHILD_CORRELATION,
            value_projector=_many("accepted_delta_refs"),
            unique=True,
        ),
        _decision(
            "candidate_validation[].candidate_ref",
            _D.PARENT_LOCAL_CORRELATION,
            value_projector=_nested_many(
                "candidate_validation",
                "candidate_ref",
            ),
            unique=True,
        ),
        _decision(
            "next_move_candidate_ref?",
            _D.PAYLOAD_CORRELATION,
            value_projector=_optional("next_move_candidate_ref"),
            maximum=1,
        ),
    )
)

_ACCEPTED_TASK_DELTA_V2_PROJECTIONS = tuple(
    (
        _decision(
            "candidate_ref",
            _D.PARENT_LOCAL_CORRELATION,
            value_projector=_one("candidate_ref"),
            minimum=1,
            maximum=1,
        ),
        _decision(
            "message_ref",
            _D.PARENT_FIELD_EQUALITY,
            value_projector=_one("message_ref"),
            minimum=1,
            maximum=1,
        ),
        _decision(
            "input_binding_refs[]",
            _D.CHILD_TOP_LEVEL_P0_REFERENCE,
            relation="input_binding_ref",
            target_record_code=_R.INPUT_BINDING_RECORD,
            value_projector=_many("input_binding_refs"),
            minimum=1,
            unique=True,
        ),
        _decision(
            "task_id",
            _D.CHILD_TOP_LEVEL_P0_REFERENCE,
            relation="accepted_delta_task_id",
            target_record_code=_R.TASK_RECORD,
            value_projector=_one("task_id"),
            minimum=1,
            maximum=1,
        ),
    )
)

_REQUEST_UNDERSTANDING_V2_SPEC = P0RecordSchemaSpec(
    record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
    record_schema_version="request_understanding_record.p0.v2",
    source_model=_RequestUnderstandingRecordV2,
    identity_fields=("request_understanding_record_id",),
    projection_decisions=_REQUEST_UNDERSTANDING_V2_PROJECTIONS,
    version_mirror_field="schema_version",
    allowed_child_codes=(P0LogicalChildCode.ACCEPTED_TASK_DELTA,),
)

_ACCEPTED_TASK_DELTA_V2_SPEC = _P0LogicalChildSchemaSpec(
    child_code=P0LogicalChildCode.ACCEPTED_TASK_DELTA,
    source_model=_AcceptedTaskDeltaV2,
    parent_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
    identity_fields=("accepted_delta_id",),
    closure_strategy=_ClosureStrategy.LOCAL_CLOSED,
    projection_decisions=_ACCEPTED_TASK_DELTA_V2_PROJECTIONS,
)

_REQUEST_UNDERSTANDING_V2_CHILD_SPEC_CATALOG: Mapping[
    tuple[P0RecordCode, str, P0LogicalChildCode],
    _P0LogicalChildSchemaSpec,
] = MappingProxyType(
    {
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "request_understanding_record.p0.v2",
            P0LogicalChildCode.ACCEPTED_TASK_DELTA,
        ): _ACCEPTED_TASK_DELTA_V2_SPEC,
    }
)

P0_LOGICAL_CHILD_SPECS: Mapping[
    P0LogicalChildCode,
    _P0LogicalChildSchemaSpec,
] = MappingProxyType(
    {
        P0LogicalChildCode.ACCEPTED_TASK_DELTA: _ACCEPTED_TASK_DELTA_V2_SPEC,
        **_NON_RU_LOGICAL_CHILD_SPECS,
    }
)

P0_RECORD_SCHEMA_VERSION_CATALOG: Mapping[
    tuple[P0RecordCode, str],
    P0RecordSchemaSpec,
] = MappingProxyType(
    {
        **{
            (
                code,
                spec.record_schema_version,
            ): spec
            for code, spec in _NON_RU_PERSISTENCE_REGISTRY.items()
        },
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            "request_understanding_record.p0.v2",
        ): _REQUEST_UNDERSTANDING_V2_SPEC,
    }
)

P0_PERSISTENCE_REGISTRY: Mapping[
    P0RecordCode,
    P0RecordSchemaSpec,
] = MappingProxyType(
    {
        **{
            code: (
                _REQUEST_UNDERSTANDING_V2_SPEC
                if code is P0RecordCode.REQUEST_UNDERSTANDING_RECORD
                else _NON_RU_PERSISTENCE_REGISTRY[code]
            )
            for code in P0RecordCode
        },
    }
)


def _versioned_pair_spec(
    record_code: P0RecordCode,
    schema_version: str,
) -> P0RecordSchemaSpec:
    if type(record_code) is not P0RecordCode:
        _raise_signal(P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE)
    if type(schema_version) is not str:
        _raise_signal(
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
        )
    selected = P0_RECORD_SCHEMA_VERSION_CATALOG.get(
        (record_code, schema_version)
    )
    if selected is not None:
        return selected
    known_versions = {
        known_version
        for _, known_version in P0_RECORD_SCHEMA_VERSION_CATALOG
    }
    category = (
        P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
        if schema_version in known_versions
        else P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
    )
    _raise_signal(category)


def _versioned_runtime_values_match_exactly(
    left: Any,
    right: Any,
) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, _P0V2BaseModel):
        try:
            declared_fields = set(type(left).model_fields)
            left_state_keys = set(left.__dict__)
            right_state_keys = set(right.__dict__)
            left_fields_set = set(left.model_fields_set)
            right_fields_set = set(right.model_fields_set)
        except (AttributeError, TypeError):
            return False
        if (
            left_state_keys != right_state_keys
            or not left_state_keys.issubset(declared_fields)
            or not left_fields_set.issubset(declared_fields)
            or not right_fields_set.issubset(declared_fields)
        ):
            return False
        try:
            left_extra = left.__pydantic_extra__
            right_extra = right.__pydantic_extra__
            left_private = left.__pydantic_private__
            right_private = right.__pydantic_private__
        except (AttributeError, TypeError):
            return False
        if not _versioned_runtime_values_match_exactly(
            left_extra,
            right_extra,
        ):
            return False
        if not _versioned_runtime_values_match_exactly(
            left_private,
            right_private,
        ):
            return False
        return all(
            field_name in left.__dict__
            and field_name in right.__dict__
            and _versioned_runtime_values_match_exactly(
                left.__dict__[field_name],
                right.__dict__[field_name],
            )
            for field_name in type(left).model_fields
        )
    if isinstance(left, tuple):
        return len(left) == len(right) and all(
            _versioned_runtime_values_match_exactly(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, Mapping):
        return (
            tuple(left) == tuple(right)
            and all(
                _versioned_runtime_values_match_exactly(left[key], right[key])
                for key in left
            )
        )
    return left == right


def _versioned_undeclared_model_state_keys(
    value: Any,
    *,
    active_ids: set[int] | None = None,
) -> frozenset[str]:
    visited = active_ids if active_ids is not None else set()
    value_id = id(value)
    if value_id in visited:
        return frozenset()
    if isinstance(value, (_P0V2BaseModel, tuple, list, Mapping)):
        visited.add(value_id)
    try:
        if isinstance(value, _P0V2BaseModel):
            declared_fields = set(type(value).model_fields)
            actual_keys = set(value.__dict__)
            try:
                fields_set = set(value.model_fields_set)
            except (AttributeError, TypeError):
                fields_set = {"invalid_model_fields_set"}
            try:
                extra = value.__pydantic_extra__
                private = value.__pydantic_private__
            except (AttributeError, TypeError):
                return frozenset({"invalid_pydantic_runtime_state"})
            if isinstance(extra, Mapping):
                actual_keys.update(str(key) for key in extra)
            if isinstance(private, Mapping):
                actual_keys.update(str(key) for key in private)
            undeclared = actual_keys.difference(declared_fields)
            undeclared.update(
                str(key)
                for key in fields_set
                if key not in declared_fields
            )
            for field_name in declared_fields:
                if field_name in value.__dict__:
                    undeclared.update(
                        _versioned_undeclared_model_state_keys(
                            value.__dict__[field_name],
                            active_ids=visited,
                        )
                    )
            return frozenset(undeclared)
        if isinstance(value, Mapping):
            result: set[str] = set()
            for nested in value.values():
                result.update(
                    _versioned_undeclared_model_state_keys(
                        nested,
                        active_ids=visited,
                    )
                )
            return frozenset(result)
        if isinstance(value, (tuple, list)):
            result = set()
            for nested in value:
                result.update(
                    _versioned_undeclared_model_state_keys(
                        nested,
                        active_ids=visited,
                    )
                )
            return frozenset(result)
        return frozenset()
    finally:
        visited.discard(value_id)


def _strict_versioned_model(
    value: object,
    source_model: type[ContractModel],
    *,
    failure_category: P0PersistenceIntegrityCategory,
) -> ContractModel:
    if type(value) is not source_model:
        _raise_signal(failure_category)
    canonical_input = value
    if _versioned_undeclared_model_state_keys(canonical_input):
        _raise_signal(failure_category)

    category: P0PersistenceIntegrityCategory | None = None
    raw_json: str | None = None
    rebuilt: ContractModel | None = None
    try:
        raw_json = canonical_input.model_dump_json(warnings="error")
        rebuilt = source_model.model_validate_json(
            raw_json,
            strict=True,
        )
    except (
        AttributeError,
        TypeError,
        ValueError,
        ValidationError,
        RecursionError,
        PydanticSerializationError,
    ):
        category = failure_category
    if category is not None:
        _raise_signal(category)
    if raw_json is None or rebuilt is None:
        _raise_signal(failure_category)
    if not _versioned_runtime_values_match_exactly(canonical_input, rebuilt):
        _raise_signal(failure_category)
    return rebuilt


def _strict_request_understanding_v2(
    record: object,
) -> ContractModel:
    if type(record) is not _RequestUnderstandingRecordV2:
        _raise_signal(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
    if not hasattr(record, "schema_version"):
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)
    if record.schema_version != _REQUEST_UNDERSTANDING_V2_SPEC.record_schema_version:
        _raise_signal(
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
        )
    return _strict_versioned_model(
        record,
        _RequestUnderstandingRecordV2,
        failure_category=(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        ),
    )


def _strict_selected_versioned_record(
    spec: P0RecordSchemaSpec,
    record: object,
) -> ContractModel:
    if type(record) is not spec.source_model:
        _raise_signal(P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH)
    if spec.version_mirror_field is not None:
        if spec.version_mirror_field not in record.__dict__:
            _raise_signal(
                P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
            )
        if (
            record.__dict__[spec.version_mirror_field]
            != spec.record_schema_version
        ):
            _raise_signal(
                P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            )
    if spec.specialized_version_validator is not None:
        specialized_version_matches: bool | None = None
        try:
            specialized_version_matches = spec.specialized_version_validator(
                record
            )
        except (AttributeError, TypeError, ValueError):
            _raise_signal(
                P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
            )
        if specialized_version_matches is not True:
            _raise_signal(
                P0PersistenceIntegrityCategory.SPECIALIZED_VERSION_MISMATCH
            )
    return _strict_versioned_model(
        record,
        spec.source_model,
        failure_category=(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        ),
    )


def _strict_selected_versioned_children(
    spec: P0RecordSchemaSpec,
    logical_children: object,
) -> tuple[ContractModel, ...]:
    if type(logical_children) is not tuple:
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    canonical: list[ContractModel] = []
    for child in logical_children:
        child_spec = next(
            (
                P0_LOGICAL_CHILD_SPECS[child_code]
                for child_code in spec.allowed_child_codes
                if type(child)
                is P0_LOGICAL_CHILD_SPECS[child_code].source_model
            ),
            None,
        )
        if child_spec is None:
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        canonical.append(
            _strict_versioned_model(
                child,
                child_spec.source_model,
                failure_category=(
                    P0PersistenceIntegrityCategory.CHILD_MISMATCH
                ),
            )
        )
    return tuple(canonical)


def _versioned_top_level_projection(
    spec: P0RecordSchemaSpec,
    record: ContractModel,
) -> tuple[str | None, tuple[P0RecordReference, ...]]:
    data = record.model_dump(mode="json", warnings="error")
    direct_owner: str | None = None
    references: list[P0RecordReference] = []
    for rule in spec.projection_decisions:
        values = _projected_values(rule, data)
        if rule.classification is _D.DIRECT_OWNER:
            if len(values) != 1 or not isinstance(values[0], str):
                _raise_signal(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
            direct_owner = values[0]
        elif rule.classification is _D.TOP_LEVEL_P0_REFERENCE:
            references.extend(
                _reference_for_value(rule, value) for value in values
            )
        elif rule.classification is _D.P0_FIRST_SLICE_MUST_BE_EMPTY:
            if values:
                _raise_signal(
                    P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                )
    return (
        direct_owner,
        _normalize_references(
            tuple(references),
            collapse_duplicates=True,
        ),
    )


def _request_understanding_v2_child_payloads(
    parent_record: ContractModel,
    parent_identity: LogicalIdentity,
    logical_children: tuple[ContractModel, ...],
) -> tuple[
    tuple[P0LogicalChildPayload, ...],
    tuple[P0RecordReference, ...],
    tuple[ContractModel, ...],
]:
    if type(logical_children) is not tuple:
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    child_spec = _REQUEST_UNDERSTANDING_V2_CHILD_SPEC_CATALOG[
        (
            P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            _REQUEST_UNDERSTANDING_V2_SPEC.record_schema_version,
            P0LogicalChildCode.ACCEPTED_TASK_DELTA,
        )
    ]
    parent = parent_record
    validated_children: list[ContractModel] = []
    for child in logical_children:
        validated_children.append(
            _strict_versioned_model(
                child,
                _AcceptedTaskDeltaV2,
                failure_category=P0PersistenceIntegrityCategory.CHILD_MISMATCH,
            )
        )

    candidate_order = tuple(
        candidate.candidate_id for candidate in parent.task_delta_candidates
    )
    if len(candidate_order) != len(set(candidate_order)):
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in parent.task_delta_candidates
    }
    decisions_by_id = {
        decision.candidate_ref: decision
        for decision in parent.candidate_validation
    }
    if (
        len(decisions_by_id) != len(parent.candidate_validation)
        or set(decisions_by_id) != set(candidate_by_id)
    ):
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

    accepted_candidate_ids = {
        candidate_id
        for candidate_id, decision in decisions_by_id.items()
        if decision.decision is CandidateValidationDecision.ACCEPT
    }
    rejected_candidate_ids = set(candidate_by_id).difference(
        accepted_candidate_ids
    )
    child_candidate_ids = tuple(
        child.candidate_ref for child in validated_children
    )
    child_ids = tuple(
        child.accepted_delta_id for child in validated_children
    )
    child_pairs = tuple(
        (child.accepted_delta_id, child.task_id)
        for child in validated_children
    )
    if (
        len(child_candidate_ids) != len(set(child_candidate_ids))
        or set(child_candidate_ids) != accepted_candidate_ids
        or set(child_candidate_ids).intersection(rejected_candidate_ids)
        or len(child_ids) != len(set(child_ids))
        or len(child_pairs) != len(set(child_pairs))
        or len(parent.accepted_delta_refs)
        != len(set(parent.accepted_delta_refs))
        or set(parent.accepted_delta_refs) != set(child_ids)
    ):
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

    child_by_candidate = {
        child.candidate_ref: child for child in validated_children
    }
    previous_result_by_task: dict[UUID, int] = {}
    for candidate_id in candidate_order:
        if candidate_id not in accepted_candidate_ids:
            continue
        candidate = candidate_by_id[candidate_id]
        child = child_by_candidate[candidate_id]
        if (
            child.operation is not candidate.operation
            or child.goal_text != candidate.goal_patch
            or child.message_ref != parent.message_ref
            or child.accepted_at != parent.created_at
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

        previous_result = previous_result_by_task.get(child.task_id)
        base_version = child.base_task_state_version
        result_version = child.result_task_state_version
        if previous_result is None:
            if base_version is not None and result_version != base_version + 1:
                _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        elif (
            base_version != previous_result
            or result_version != base_version + 1
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        previous_result_by_task[child.task_id] = result_version

    validated_children.sort(
        key=lambda child: str(child.accepted_delta_id)
    )
    payloads: list[P0LogicalChildPayload] = []
    child_references: list[P0RecordReference] = []
    for child in validated_children:
        child_data = child.model_dump(mode="json", warnings="error")
        for rule in child_spec.projection_decisions:
            values = _projected_values(rule, child_data)
            if rule.classification is _D.CHILD_TOP_LEVEL_P0_REFERENCE:
                child_references.extend(
                    _reference_for_value(rule, value) for value in values
                )
        payloads.append(
            P0LogicalChildPayload(
                child_code=child_spec.child_code,
                parent_record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                parent_logical_identity=parent_identity,
                logical_identity=_logical_identity(
                    child,
                    child_spec.identity_fields,
                ),
                data=child_data,
            )
        )
    return (
        tuple(payloads),
        _normalize_references(
            tuple(child_references),
            collapse_duplicates=True,
        ),
        tuple(validated_children),
    )


def _build_request_understanding_v2_envelope(
    record: object,
    *,
    external_references: tuple[P0RecordReference, ...],
    logical_children: tuple[ContractModel, ...],
) -> P0PersistenceEnvelope:
    if type(external_references) is not tuple:
        _raise_signal(
            P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
        )
    validated = _strict_request_understanding_v2(record)
    identity = _logical_identity(
        validated,
        _REQUEST_UNDERSTANDING_V2_SPEC.identity_fields,
    )
    owner, source_references = _versioned_top_level_projection(
        _REQUEST_UNDERSTANDING_V2_SPEC,
        validated,
    )
    external = _validate_external_references(
        _REQUEST_UNDERSTANDING_V2_SPEC,
        external_references,
    )
    children, child_references, _ = (
        _request_understanding_v2_child_payloads(
            validated,
            identity,
            logical_children,
        )
    )
    references = _normalize_references(
        (*source_references, *external, *child_references),
        collapse_duplicates=True,
    )
    return P0PersistenceEnvelope(
        record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        record_schema_version=(
            _REQUEST_UNDERSTANDING_V2_SPEC.record_schema_version
        ),
        logical_identity=identity,
        direct_owner_customer_id=owner,
        record_references=references,
        payload=P0VersionedPayload(
            record_code=P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            record_schema_version=(
                _REQUEST_UNDERSTANDING_V2_SPEC.record_schema_version
            ),
            data=validated.model_dump(mode="json", warnings="error"),
            logical_children=children,
        ),
    )


def encode_persistence_record_versioned(
    record_code: P0RecordCode,
    schema_version: str,
    record: ContractModel,
    *,
    external_references: tuple[P0RecordReference, ...] = (),
    logical_children: tuple[ContractModel, ...] = (),
) -> P0PersistenceEnvelope:
    category: P0PersistenceIntegrityCategory | None = None
    result: P0PersistenceEnvelope | None = None
    try:
        selected = _versioned_pair_spec(record_code, schema_version)
        if type(external_references) is not tuple:
            _raise_signal(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        if any(
            type(reference) is not P0RecordReference
            or _versioned_undeclared_model_state_keys(reference)
            for reference in external_references
        ):
            _raise_signal(
                P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
            )
        if selected is _REQUEST_UNDERSTANDING_V2_SPEC:
            result = _build_request_understanding_v2_envelope(
                record,
                external_references=external_references,
                logical_children=logical_children,
            )
        else:
            validated_record = _strict_selected_versioned_record(
                selected,
                record,
            )
            validated_children = _strict_selected_versioned_children(
                selected,
                logical_children,
            )
            result = _build_envelope(
                record_code,
                validated_record,
                external_references=external_references,
                logical_children=validated_children,
            )
    except _IntegritySignal as signal:
        category = signal.category
    if category is not None:
        raise _public_error(category, uuid4())
    if result is None:
        raise _public_error(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
            uuid4(),
        )
    return result


def _classify_outer_versioned(
    raw_json: str | bytes,
    expected_record_code: P0RecordCode,
    expected_schema_version: str,
    selected_spec: P0RecordSchemaSpec,
) -> dict[str, Any]:
    category: P0PersistenceIntegrityCategory | None = None
    parsed: object = None
    try:
        parsed = json.loads(raw_json)
    except (
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if not isinstance(parsed, dict):
        _raise_signal(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)

    if "record_code" not in parsed:
        _raise_signal(P0PersistenceIntegrityCategory.MISSING_RECORD_CODE)
    raw_code = parsed["record_code"]
    try:
        code = P0RecordCode(raw_code)
    except (TypeError, ValueError):
        code = None
    if code is None:
        _raise_signal(P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE)
    if code is not expected_record_code:
        _raise_signal(P0PersistenceIntegrityCategory.RECORD_CODE_MISMATCH)

    if "record_schema_version" not in parsed:
        _raise_signal(
            P0PersistenceIntegrityCategory.MISSING_RECORD_SCHEMA_VERSION
        )
    raw_version = parsed["record_schema_version"]
    if type(raw_version) is not str:
        _raise_signal(
            P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
        )
    if raw_version != expected_schema_version:
        known_versions = {
            known_version
            for _, known_version in P0_RECORD_SCHEMA_VERSION_CATALOG
        }
        category = (
            P0PersistenceIntegrityCategory.RECORD_SCHEMA_VERSION_MISMATCH
            if raw_version in known_versions
            else P0PersistenceIntegrityCategory.UNKNOWN_RECORD_SCHEMA_VERSION
        )
        _raise_signal(category)
    return parsed


def _decode_request_understanding_v2(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
    expected_record_code: P0RecordCode,
    expected_schema_version: str,
) -> DecodedP0PersistenceRecord:
    if (
        isinstance(envelope, P0PersistenceEnvelope)
        and _versioned_undeclared_model_state_keys(envelope)
    ):
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)
    raw_json = _json_input(envelope)
    outer_data = _classify_outer_versioned(
        raw_json,
        expected_record_code,
        expected_schema_version,
        _REQUEST_UNDERSTANDING_V2_SPEC,
    )
    inner_data = outer_data.get("payload")
    if (
        not isinstance(inner_data, dict)
        or inner_data.get("record_code") != expected_record_code.value
        or inner_data.get("record_schema_version")
        != expected_schema_version
    ):
        _raise_signal(P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH)

    category: P0PersistenceIntegrityCategory | None = None
    validated_envelope: P0PersistenceEnvelope | None = None
    try:
        validated_envelope = P0PersistenceEnvelope.model_validate_json(
            raw_json,
            strict=True,
        )
    except ValidationError as error:
        category = _envelope_validation_category(error)
    except (TypeError, ValueError, RecursionError):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if validated_envelope is None:
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)
    if (
        validated_envelope.payload.record_code is not expected_record_code
        or validated_envelope.payload.record_schema_version
        != expected_schema_version
    ):
        _raise_signal(P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH)

    source_json = _json_mapping_text(
        validated_envelope.payload.data,
        failure_category=(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
        ),
    )
    source_record: ContractModel | None = None
    category = None
    try:
        source_record = _RequestUnderstandingRecordV2.model_validate_json(
            source_json,
            strict=True,
        )
    except (TypeError, ValueError, ValidationError, RecursionError):
        category = P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
    if category is not None:
        _raise_signal(category)
    if source_record is None:
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)

    children: list[ContractModel] = []
    for child_payload in validated_envelope.payload.logical_children:
        if (
            child_payload.child_code
            is not P0LogicalChildCode.ACCEPTED_TASK_DELTA
        ):
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        child_json = _json_mapping_text(
            child_payload.data,
            failure_category=P0PersistenceIntegrityCategory.CHILD_MISMATCH,
        )
        child: ContractModel | None = None
        category = None
        try:
            child = _AcceptedTaskDeltaV2.model_validate_json(
                child_json,
                strict=True,
            )
        except (TypeError, ValueError, ValidationError, RecursionError):
            category = P0PersistenceIntegrityCategory.CHILD_MISMATCH
        if category is not None:
            _raise_signal(category)
        if child is None:
            _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
        children.append(child)

    expected = _build_request_understanding_v2_envelope(
        source_record,
        external_references=(),
        logical_children=tuple(children),
    )
    if expected.logical_identity != validated_envelope.logical_identity:
        _raise_signal(P0PersistenceIntegrityCategory.IDENTITY_MISMATCH)
    if (
        expected.direct_owner_customer_id
        != validated_envelope.direct_owner_customer_id
    ):
        _raise_signal(
            P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
        )
    if expected.record_references != validated_envelope.record_references:
        _raise_signal(P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH)
    if expected.payload.data != validated_envelope.payload.data:
        _raise_signal(P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED)
    if (
        expected.payload.logical_children
        != validated_envelope.payload.logical_children
    ):
        _raise_signal(P0PersistenceIntegrityCategory.CHILD_MISMATCH)
    return DecodedP0PersistenceRecord(
        record_code=expected_record_code,
        record_schema_version=expected_schema_version,
        source_record=source_record,
        logical_children=tuple(children),
    )


def decode_persistence_record_versioned(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
    *,
    expected_record_code: P0RecordCode,
    expected_schema_version: str,
    correlation_ref: UUID,
) -> DecodedP0PersistenceRecord:
    if type(correlation_ref) is not UUID:
        raise TypeError("correlation_ref must be UUID")

    category: P0PersistenceIntegrityCategory | None = None
    result: DecodedP0PersistenceRecord | None = None
    try:
        selected = _versioned_pair_spec(
            expected_record_code,
            expected_schema_version,
        )
        if (
            isinstance(envelope, P0PersistenceEnvelope)
            and _versioned_undeclared_model_state_keys(envelope)
        ):
            _raise_signal(
                P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED
            )
        if selected is _REQUEST_UNDERSTANDING_V2_SPEC:
            result = _decode_request_understanding_v2(
                envelope,
                expected_record_code,
                expected_schema_version,
            )
        else:
            raw_json = _json_input(envelope)
            _classify_outer_versioned(
                raw_json,
                expected_record_code,
                expected_schema_version,
                selected,
            )
            result = _decode(raw_json, expected_record_code)
    except _IntegritySignal as signal:
        category = signal.category
    if category is not None:
        raise _public_error(category, correlation_ref)
    if result is None:
        raise _public_error(
            P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
            correlation_ref,
        )
    return result
