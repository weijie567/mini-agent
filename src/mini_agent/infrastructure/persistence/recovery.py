from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0RecordCode,
    encode_persistence_record,
)
from mini_agent.application.records import (
    ApplyRestartRecoveryCommand,
    RecoveryWriteResult,
    RestartRecoveryClosure,
    TaskRecoveryAggregate,
    ToolCallRecoveryAggregate,
)
from mini_agent.core.task_state import RequestUnitRecord, TaskRecord
from mini_agent.core.tool_system import ToolCallRecord, ToolCallStatus, ToolEffect
from mini_agent.core.trace import AgentRunRecord, AgentRunStatus
from mini_agent.infrastructure.persistence.models import P0RecordModel
from mini_agent.infrastructure.persistence.postgres import (
    PostgresRecordAdapter,
    _integrity,
)


class PostgresRestartRecoveryAdapter(PostgresRecordAdapter):
    """Bounded restart-closure loader and atomic state-plus-Trace writer."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__(session_factory)

    @staticmethod
    def _bounded_rows(
        session: Session,
        statement,
        *,
        family: str,
    ) -> tuple[P0RecordModel, ...]:
        rows = tuple(session.scalars(statement.limit(2)))
        if len(rows) > 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )
        return rows

    @staticmethod
    def _preflight_child_count(
        row: P0RecordModel,
        *,
        maximum: int,
    ) -> None:
        payload = row.envelope.get("payload")
        children = payload.get("logical_children") if isinstance(payload, dict) else None
        if not isinstance(children, list) or len(children) > maximum:
            raise _integrity(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

    def _closure_fence(
        self,
        session: Session,
        rows: Iterable[P0RecordModel],
    ) -> UUID:
        materialized: list[dict[str, Any]] = []
        for row in sorted(rows, key=self._row_key):
            materialized.append(
                {
                    "record_code": row.record_code,
                    "logical_identity": row.logical_identity,
                    "envelope": row.envelope,
                    "references": tuple(
                        reference.model_dump(mode="json")
                        for reference in self._normalized_references(session, row)
                    ),
                }
            )
        encoded = json.dumps(
            materialized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return UUID(bytes=hashlib.sha256(encoded).digest()[:16])

    def _load_closure_in_transaction(
        self,
        session: Session,
        *,
        run_id: UUID | None = None,
        for_update: bool = False,
    ) -> RestartRecoveryClosure | None:
        run_statement = (
            select(P0RecordModel)
            .where(
                P0RecordModel.record_code
                == P0RecordCode.AGENT_RUN_RECORD.value,
                P0RecordModel.lifecycle_status.in_(
                    (
                        AgentRunStatus.CREATED.value,
                        AgentRunStatus.RUNNING.value,
                    )
                ),
            )
            .order_by(
                P0RecordModel.recovery_sort_at,
                P0RecordModel.record_id,
            )
        )
        if run_id is not None:
            run_statement = run_statement.where(P0RecordModel.run_id == run_id)
        candidate_rows = tuple(session.scalars(run_statement.limit(2)))
        if not candidate_rows:
            return None
        run_row = candidate_rows[0]
        run_decoded = self._validate_physical_projection(session, run_row)
        run_record = run_decoded.source_record
        if not isinstance(run_record, AgentRunRecord):
            raise _integrity(
                P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
            )
        owner = run_row.scope_owner_customer_id
        if owner is None or run_record.conversation_id is None:
            raise _integrity(
                P0PersistenceIntegrityCategory.OWNER_PROJECTION_MISMATCH
            )

        conversation_statement = select(P0RecordModel).where(
            P0RecordModel.record_code
            == P0RecordCode.CONVERSATION_RECORD.value,
            P0RecordModel.conversation_id == run_record.conversation_id,
            P0RecordModel.scope_owner_customer_id == owner,
        )
        conversation_link_statement = select(P0RecordModel).where(
            P0RecordModel.record_code
            == P0RecordCode.CONVERSATION_TASK_LINK_RECORD.value,
            P0RecordModel.conversation_id == run_record.conversation_id,
            P0RecordModel.scope_owner_customer_id == owner,
        )
        run_link_statement = select(P0RecordModel).where(
            P0RecordModel.record_code
            == P0RecordCode.RUN_TASK_LINK_RECORD.value,
            P0RecordModel.run_id == run_record.run_id,
            P0RecordModel.scope_owner_customer_id == owner,
        )
        tool_statement = select(P0RecordModel).where(
            P0RecordModel.record_code == P0RecordCode.TOOL_CALL_RECORD.value,
            P0RecordModel.run_id == run_record.run_id,
            P0RecordModel.lifecycle_status.in_(("CREATED", "RUNNING")),
            P0RecordModel.scope_owner_customer_id == owner,
        )
        conversation_rows = self._bounded_rows(
            session,
            conversation_statement,
            family="conversation",
        )
        conversation_link_rows = self._bounded_rows(
            session,
            conversation_link_statement,
            family="conversation_task_link",
        )
        run_link_rows = self._bounded_rows(
            session,
            run_link_statement,
            family="run_task_link",
        )
        tool_rows = self._bounded_rows(
            session,
            tool_statement,
            family="tool_call",
        )
        if len(conversation_rows) != 1:
            raise _integrity(
                P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
            )

        task_rows: tuple[P0RecordModel, ...] = ()
        unit_rows: tuple[P0RecordModel, ...] = ()
        if run_link_rows:
            task_id = run_link_rows[0].task_id
            if task_id is None:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
                )
            task_statement = select(P0RecordModel).where(
                P0RecordModel.record_code == P0RecordCode.TASK_RECORD.value,
                P0RecordModel.task_id == task_id,
                P0RecordModel.scope_owner_customer_id == owner,
            )
            unit_statement = select(P0RecordModel).where(
                P0RecordModel.record_code
                == P0RecordCode.REQUEST_UNIT_RECORD.value,
                P0RecordModel.task_id == task_id,
                P0RecordModel.scope_owner_customer_id == owner,
            )
            task_rows = self._bounded_rows(
                session,
                task_statement,
                family="task",
            )
            unit_rows = self._bounded_rows(
                session,
                unit_statement,
                family="request_unit",
            )
            if len(task_rows) != 1 or len(unit_rows) != 1:
                raise _integrity(
                    P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
                )

        if run_record.status is AgentRunStatus.CREATED and any(
            (
                conversation_link_rows,
                run_link_rows,
                task_rows,
                unit_rows,
                tool_rows,
            )
        ):
            raise _integrity(P0PersistenceIntegrityCategory.CHILD_MISMATCH)

        for task_row in task_rows:
            self._preflight_child_count(task_row, maximum=1)
        for tool_row in tool_rows:
            self._preflight_child_count(tool_row, maximum=1)

        all_rows = (
            run_row,
            *conversation_rows,
            *conversation_link_rows,
            *run_link_rows,
            *task_rows,
            *unit_rows,
            *tool_rows,
        )
        if for_update:
            locked_by_key = {
                self._row_key(row): row
                for row in self._lock_rows_stably(session, all_rows)
            }

            def locked_rows(
                rows: Iterable[P0RecordModel],
            ) -> tuple[P0RecordModel, ...]:
                return tuple(
                    locked_by_key[self._row_key(row)]
                    for row in rows
                )

            run_row = locked_by_key[self._row_key(run_row)]
            conversation_rows = locked_rows(conversation_rows)
            conversation_link_rows = locked_rows(conversation_link_rows)
            run_link_rows = locked_rows(run_link_rows)
            task_rows = locked_rows(task_rows)
            unit_rows = locked_rows(unit_rows)
            tool_rows = locked_rows(tool_rows)
            all_rows = (
                run_row,
                *conversation_rows,
                *conversation_link_rows,
                *run_link_rows,
                *task_rows,
                *unit_rows,
                *tool_rows,
            )
        decoded_rows = {
            self._row_key(row): self._validate_physical_projection(
                session,
                row,
                expected_owner=owner,
            )
            for row in all_rows
        }

        task_aggregates: tuple[TaskRecoveryAggregate, ...] = ()
        if task_rows:
            decoded_task = decoded_rows[self._row_key(task_rows[0])]
            if not isinstance(decoded_task.source_record, TaskRecord):
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            task_aggregates = (
                TaskRecoveryAggregate(
                    task_record=decoded_task.source_record,
                    task_state_transitions=decoded_task.logical_children,
                ),
            )

        request_units: tuple[RequestUnitRecord, ...] = ()
        if unit_rows:
            unit = decoded_rows[self._row_key(unit_rows[0])].source_record
            if not isinstance(unit, RequestUnitRecord):
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            request_units = (unit,)

        tool_aggregates: tuple[ToolCallRecoveryAggregate, ...] = ()
        if tool_rows:
            decoded_tool = decoded_rows[self._row_key(tool_rows[0])]
            if not isinstance(decoded_tool.source_record, ToolCallRecord):
                raise _integrity(
                    P0PersistenceIntegrityCategory.SOURCE_MODEL_MISMATCH
                )
            tool_aggregates = (
                ToolCallRecoveryAggregate(
                    tool_call_record=decoded_tool.source_record,
                    tool_attempt_records=decoded_tool.logical_children,
                ),
            )

        return RestartRecoveryClosure(
            closure_fence=self._closure_fence(session, all_rows),
            conversation_record=decoded_rows[
                self._row_key(conversation_rows[0])
            ].source_record,
            active_run_record=run_record,
            conversation_task_links=tuple(
                decoded_rows[self._row_key(row)].source_record
                for row in conversation_link_rows
            ),
            run_task_links=tuple(
                decoded_rows[self._row_key(row)].source_record
                for row in run_link_rows
            ),
            task_aggregates=task_aggregates,
            request_unit_records=request_units,
            tool_call_aggregates=tool_aggregates,
        )

    async def load_next_restart_recovery_closure(
        self,
    ) -> RestartRecoveryClosure | None:
        with self.session_factory() as session:
            session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            )
            try:
                closure = self._load_closure_in_transaction(session)
                session.commit()
                return closure
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _is_concurrency_conflict(exc: OperationalError) -> bool:
        original = exc.orig
        sqlstate = getattr(original, "sqlstate", None) or getattr(
            original,
            "pgcode",
            None,
        )
        return sqlstate in {"40001", "40P01"}

    def _persist_recovery_trace(
        self,
        session: Session,
        event,
    ) -> None:
        self._persist_envelopes(
            session,
            (
                encode_persistence_record(
                    P0RecordCode.TRACE_EVENT_RECORD,
                    event,
                ),
            ),
        )

    def _apply_recovery_in_transaction(
        self,
        session: Session,
        command: ApplyRestartRecoveryCommand,
    ) -> RecoveryWriteResult:
        current = self._load_closure_in_transaction(
            session,
            run_id=command.expected_closure.active_run_record.run_id,
            for_update=True,
        )
        if current is None:
            return RecoveryWriteResult.NOT_APPLICABLE
        if current != command.expected_closure:
            return RecoveryWriteResult.CLOSURE_CONFLICT
        if any(
            aggregate.tool_call_record.effect is ToolEffect.ACTION
            and aggregate.tool_call_record.status is ToolCallStatus.RUNNING
            for aggregate in current.tool_call_aggregates
        ):
            return RecoveryWriteResult.RECONCILIATION_REQUIRED

        run_row = self._row_for_identity(
            session,
            record_code=P0RecordCode.AGENT_RUN_RECORD,
            logical_identity=(
                ("run_id", current.active_run_record.run_id),
            ),
            for_update=True,
        )
        if run_row is None or not self._replace_row_envelope(
            session,
            run_row,
            expected_record=command.run_transition.expected_active_record,
            expected_children=(),
            next_envelope=encode_persistence_record(
                P0RecordCode.AGENT_RUN_RECORD,
                command.run_transition.incomplete_record,
            ),
        ):
            return RecoveryWriteResult.CLOSURE_CONFLICT

        tool_aggregate_by_id = {
            aggregate.tool_call_record.tool_call_id: aggregate
            for aggregate in current.tool_call_aggregates
        }
        for transition in command.tool_call_transitions:
            row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TOOL_CALL_RECORD,
                logical_identity=(
                    ("tool_call_id", transition.active_record.tool_call_id),
                ),
                for_update=True,
            )
            aggregate = tool_aggregate_by_id[transition.active_record.tool_call_id]
            if row is None or not self._replace_row_envelope(
                session,
                row,
                expected_record=transition.active_record,
                expected_children=aggregate.tool_attempt_records,
                next_envelope=encode_persistence_record(
                    P0RecordCode.TOOL_CALL_RECORD,
                    transition.interrupted_record,
                    logical_children=aggregate.tool_attempt_records,
                ),
            ):
                return RecoveryWriteResult.CLOSURE_CONFLICT

        task_aggregate_by_id = {
            aggregate.task_record.task_id: aggregate
            for aggregate in current.task_aggregates
        }
        for transition in command.task_transitions:
            task_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.TASK_RECORD,
                logical_identity=(
                    ("task_id", transition.expected_task_record.task_id),
                ),
                for_update=True,
            )
            unit_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.REQUEST_UNIT_RECORD,
                logical_identity=(
                    (
                        "request_unit_id",
                        transition.expected_request_unit_record.request_unit_id,
                    ),
                ),
                for_update=True,
            )
            aggregate = task_aggregate_by_id[
                transition.expected_task_record.task_id
            ]
            if task_row is None or unit_row is None:
                return RecoveryWriteResult.CLOSURE_CONFLICT
            if not self._replace_row_envelope(
                session,
                task_row,
                expected_record=transition.expected_task_record,
                expected_children=aggregate.task_state_transitions,
                next_envelope=encode_persistence_record(
                    P0RecordCode.TASK_RECORD,
                    transition.next_task_record,
                    logical_children=(
                        *aggregate.task_state_transitions,
                        transition.task_state_transition,
                    ),
                ),
            ):
                return RecoveryWriteResult.CLOSURE_CONFLICT
            if not self._replace_row_envelope(
                session,
                unit_row,
                expected_record=transition.expected_request_unit_record,
                expected_children=(),
                next_envelope=encode_persistence_record(
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    transition.next_request_unit_record,
                ),
            ):
                return RecoveryWriteResult.CLOSURE_CONFLICT

        expected_link_by_task = {
            link.task_id: link for link in current.run_task_links
        }
        for terminal_link in command.terminal_run_task_links:
            expected_link = expected_link_by_task[terminal_link.task_id]
            link_row = self._row_for_identity(
                session,
                record_code=P0RecordCode.RUN_TASK_LINK_RECORD,
                logical_identity=(
                    ("run_id", expected_link.run_id),
                    ("task_id", expected_link.task_id),
                ),
                for_update=True,
            )
            if link_row is None or not self._replace_row_envelope(
                session,
                link_row,
                expected_record=expected_link,
                expected_children=(),
                next_envelope=encode_persistence_record(
                    P0RecordCode.RUN_TASK_LINK_RECORD,
                    terminal_link,
                ),
            ):
                return RecoveryWriteResult.CLOSURE_CONFLICT

        for trace_event in command.recovery_trace_events:
            self._persist_recovery_trace(session, trace_event)
        return RecoveryWriteResult.APPLIED

    async def claim_and_apply_restart_recovery(
        self,
        command: ApplyRestartRecoveryCommand,
    ) -> RecoveryWriteResult:
        with self.session_factory() as session:
            try:
                session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                )
                result = self._apply_recovery_in_transaction(session, command)
                if result is RecoveryWriteResult.APPLIED:
                    session.commit()
                else:
                    session.rollback()
                return result
            except OperationalError as exc:
                session.rollback()
                if self._is_concurrency_conflict(exc):
                    return RecoveryWriteResult.CLOSURE_CONFLICT
                raise
            except Exception:
                session.rollback()
                raise
