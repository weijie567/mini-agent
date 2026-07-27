from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.application.persistence import (
    DecodedP0PersistenceRecord,
    P0PersistenceEnvelope,
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    P0RecordReference,
    decode_persistence_record,
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
    InputBinding,
    RequestUnderstandingRecord,
    RequestUnitRecord,
    TaskRecord,
)
from mini_agent.core.tool_system import (
    GateDecision,
    ModelVisibleToolsetArtifact,
    ToolCallRecord,
    ToolEffect,
)
from mini_agent.core.trace import AgentRunRecord, TraceEvent
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
)

_RecordT = TypeVar("_RecordT", bound=BaseModel)
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


class PostgresRecordAdapter:
    """Synchronous-SQLAlchemy implementation of the frozen async record Ports."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

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
        return P0PersistenceEnvelope.model_validate_json(
            json.dumps(
                raw,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            strict=True,
        )

    @staticmethod
    def _row_key(row: P0RecordModel) -> tuple[str, str]:
        return row.record_code, repr(row.logical_identity)

    @staticmethod
    def _envelope_key(
        envelope: P0PersistenceEnvelope,
    ) -> tuple[str, str]:
        return envelope.record_code.value, repr(
            _json_identity(envelope.logical_identity)
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
        return tuple(
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

    def _decode_row(
        self,
        session: Session,
        row: P0RecordModel,
    ) -> DecodedP0PersistenceRecord:
        try:
            record_code = P0RecordCode(row.record_code)
        except ValueError as exc:
            raise _integrity(
                P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE
            ) from exc
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
    ) -> str | None:
        queue = [root]
        seen: set[tuple[str, str]] = set()
        owners: set[str] = set()
        while queue:
            row = queue.pop()
            key = self._row_key(row)
            if key in seen:
                continue
            seen.add(key)
            self._decode_row(session, row)
            envelope = self._parse_envelope(row.envelope)
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
                    statement = statement.where(
                        or_(
                            P0RecordModel.scope_owner_customer_id
                            == expected_owner,
                            P0RecordModel.scope_owner_customer_id.is_(None),
                        )
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
        return derived_owner

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
        existing = self._row_for_identity(
            session,
            record_code=envelope.record_code,
            logical_identity=envelope.logical_identity,
            for_update=True,
        )
        if existing is not None:
            if existing.envelope != self._envelope_json(envelope):
                raise _integrity(
                    P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                )
            return False

        values = self._projection_values(
            envelope,
            scope_owner_customer_id=envelope.direct_owner_customer_id,
        )
        session.add(P0RecordModel(record_id=uuid4(), **values))
        session.flush()
        return True

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
        inserted = tuple(
            self._persist_one_envelope(session, envelope)
            for envelope in materialized
        )
        session.flush()
        for envelope, was_inserted in zip(materialized, inserted, strict=True):
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
        for envelope, was_inserted in zip(materialized, inserted, strict=True):
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
            derived_owner = self._derive_owner_from_graph(session, row)
            if (
                envelope.record_code in _PRIVATE_RECORD_CODES
                and derived_owner is None
            ):
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
            if was_inserted:
                row.scope_owner_customer_id = derived_owner
                session.flush()
            elif row.scope_owner_customer_id != derived_owner:
                raise _integrity(
                    P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
                )
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

    async def finalize_run_if_active(
        self,
        command: FinalizeRunCommand,
    ) -> ConditionalWriteResult:
        with self.session_factory.begin() as session:
            run_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.AGENT_RUN_RECORD,
                logical_identity=(
                    ("run_id", command.expected_active_record.run_id),
                ),
                for_update=True,
            )
            if run_row is None:
                return ConditionalWriteResult.NOT_APPLICABLE
            run_decoded = self._validate_physical_projection(session, run_row)
            if run_decoded.source_record != command.expected_active_record:
                return ConditionalWriteResult.PROJECTION_CONFLICT

            link_rows: list[P0RecordModel] = []
            for expected_link in sorted(
                command.expected_active_links,
                key=lambda item: str(item.task_id),
            ):
                link_row = self._row_for_identity(
                    session,
                    record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
                    logical_identity=(
                        ("run_id", expected_link.run_id),
                        ("task_id", expected_link.task_id),
                    ),
                    for_update=True,
                )
                if link_row is None:
                    return ConditionalWriteResult.PROJECTION_CONFLICT
                decoded = self._validate_physical_projection(session, link_row)
                if decoded.source_record != expected_link:
                    return ConditionalWriteResult.PROJECTION_CONFLICT
                link_rows.append(link_row)
            for task in command.result_task_records:
                task_row = self._row_for_identity(
                    session,
                    record_code=P0RecordCode.TASK_RECORD,
                    logical_identity=(("task_id", task.task_id),),
                    for_update=True,
                )
                if task_row is None:
                    return ConditionalWriteResult.PROJECTION_CONFLICT
                if (
                    self._validate_physical_projection(
                        session,
                        task_row,
                    ).source_record
                    != task
                ):
                    return ConditionalWriteResult.PROJECTION_CONFLICT

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
                return ConditionalWriteResult.PROJECTION_CONFLICT
            for row, expected_link, terminal_link in zip(
                link_rows,
                command.expected_active_links,
                command.terminal_links,
                strict=True,
            ):
                if not self._replace_row_envelope(
                    session,
                    row,
                    expected_record=expected_link,
                    expected_children=(),
                    next_envelope=encode_persistence_record(
                        P0RecordCode.RUN_TASK_LINK_RECORD,
                        terminal_link,
                    ),
                ):
                    raise _integrity(
                        P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH
                    )
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
            for code, identity, expected in expected_rows:
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
            if any(
                self._row_for_identity(
                    session,
                    record_code=envelope.record_code,
                    logical_identity=envelope.logical_identity,
                    for_update=True,
                )
                is not None
                for envelope in envelopes
            ):
                return ConditionalWriteResult.PROJECTION_CONFLICT
            self._persist_envelopes(session, envelopes)
            return ConditionalWriteResult.APPLIED

    async def apply_task_transition_if_current(
        self,
        command: ApplyTaskTransitionCommand,
    ) -> ConditionalWriteResult:
        with self.session_factory.begin() as session:
            task_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(
                    ("task_id", command.expected_task_record.task_id),
                ),
                for_update=True,
            )
            unit_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                logical_identity=(
                    (
                        "request_unit_id",
                        command.expected_request_unit_record.request_unit_id,
                    ),
                ),
                for_update=True,
            )
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
            inserted = self._persist_envelopes(session, (envelope,))[0]
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

    async def list_trace_events_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> tuple[TraceEvent, ...]:
        return await self._list_for_owner(
            owner_scope=owner_scope,
            record_code=P0RecordCode.TRACE_EVENT_RECORD,
            filters=(P0RecordModel.run_id == run_id,),
            expected_type=TraceEvent,
        )

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
