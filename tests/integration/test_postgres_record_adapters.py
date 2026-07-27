from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError

from mini_agent.application.persistence import (
    P0PersistenceIntegrityCategory,
    P0PersistenceIntegrityError,
    P0RecordCode,
    decode_persistence_record,
    encode_persistence_record,
)
from mini_agent.application.records import TrustedOwnerScope
from mini_agent.core.identity import CustomerContext
from mini_agent.infrastructure.persistence.database import build_session_factory
from mini_agent.infrastructure.persistence.models import (
    P0RecordModel,
    P0RecordReferenceModel,
)
from mini_agent.infrastructure.persistence.postgres import PostgresRecordAdapter

_COMPONENT_APPLICATION_TESTS = (
    Path(__file__).parents[1] / "component" / "application"
)
sys.path.append(str(_COMPONENT_APPLICATION_TESTS))
from test_persistence_contract import _record_cases  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _owner_scope(customer_id: str = "customer-A") -> TrustedOwnerScope:
    context = CustomerContext.model_validate(
        {
            "subject_ref": f"subject-{customer_id}",
            "customer_id": customer_id,
            "auth_scopes": frozenset({"orders:read"}),
            "authenticated_at": "2026-07-27T08:00:00Z",
            "session_ref_hash": "0" * 64,
        }
    )
    return TrustedOwnerScope.from_customer_context(context)


def _encoded_record_set():
    return tuple(
        encode_persistence_record(
            case.code,
            case.record,
            external_references=case.external_references,
            logical_children=case.logical_children,
        )
        for case in _record_cases()
    )


def _assert_bounded_integrity_error(
    error: P0PersistenceIntegrityError,
    *,
    category: P0PersistenceIntegrityCategory,
    forbidden_values: tuple[str, ...],
) -> None:
    assert error.category is category
    assert error.__cause__ is None
    assert error.__context__ is None
    projection = f"{error!s} {error!r} {error.args!r}"
    assert all(value not in projection for value in forbidden_values)


async def _seed_all_records(adapter: PostgresRecordAdapter) -> None:
    with adapter.session_factory.begin() as session:
        adapter._persist_envelopes(session, _encoded_record_set())


async def test_all_17_records_and_five_external_references_round_trip_exactly(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    cases = _record_cases()
    try:
        await _seed_all_records(adapter)

        with adapter.session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(P0RecordModel).order_by(P0RecordModel.record_code)
                )
            )
            references = tuple(
                session.scalars(
                    select(P0RecordReferenceModel).order_by(
                        P0RecordReferenceModel.source_record_code,
                        P0RecordReferenceModel.ordinal,
                    )
                )
            )

            assert {row.record_code for row in rows} == {
                code.value for code in P0RecordCode
            }
            assert len(rows) == 17
            for row in rows:
                decoded = decode_persistence_record(
                    row.envelope,
                    expected_record_code=P0RecordCode(row.record_code),
                    correlation_ref=UUID(int=800),
                )
                expected = next(case for case in cases if case.code is decoded.record_code)
                assert decoded.source_record == expected.record
                assert decoded.logical_children == expected.logical_children
                normalized = tuple(
                    reference
                    for reference in references
                    if reference.source_record_code == row.record_code
                    and reference.source_logical_identity == row.logical_identity
                )
                envelope_references = json.loads(
                    encode_persistence_record(
                        expected.code,
                        expected.record,
                        external_references=expected.external_references,
                        logical_children=expected.logical_children,
                    ).model_dump_json()
                )["record_references"]
                assert [
                    {
                        "relation": reference.relation,
                        "target_record_code": reference.target_record_code,
                        "target_logical_identity": reference.target_logical_identity,
                    }
                    for reference in normalized
                ] == envelope_references

            expected_external_relations = {
                ("input_binding_record", "request_unit_id"),
                ("observation_record", "source_tool_call_id"),
                ("observation_record", "source_run_id"),
                ("observation_record", "source_task_id"),
                ("observation_record", "source_request_unit_id"),
            }
            external_relations = {
                (reference.source_record_code, reference.relation)
                for reference in references
                if (reference.source_record_code, reference.relation)
                in expected_external_relations
            }
            assert external_relations == expected_external_relations
    finally:
        engine.dispose()


async def test_exact_replay_is_idempotent_and_conflicting_replay_is_bounded(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    conversation = _record_cases()[0].record
    insert_barrier = threading.Barrier(2)
    local_state = threading.local()

    def synchronize_record_inserts(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if (
            statement.lstrip().upper().startswith("INSERT INTO P0_RECORDS")
            and not getattr(local_state, "record_insert_seen", False)
        ):
            local_state.record_insert_seen = True
            insert_barrier.wait(timeout=10)

    def save_in_thread(record) -> None:
        asyncio.run(adapter.save_conversation(record))

    event.listen(engine, "before_cursor_execute", synchronize_record_inserts)
    try:
        await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(save_in_thread, conversation),
                asyncio.to_thread(save_in_thread, conversation),
            ),
            timeout=15,
        )
        event.remove(
            engine,
            "before_cursor_execute",
            synchronize_record_inserts,
        )

        with adapter.session_factory() as session:
            assert session.scalar(select(P0RecordModel.record_id)) is not None

        conflicting = conversation.model_copy(
            update={"created_at": conversation.created_at.replace(microsecond=1)}
        )
        with pytest.raises(P0PersistenceIntegrityError) as captured:
            await adapter.save_conversation(conflicting)
        _assert_bounded_integrity_error(
            captured.value,
            category=P0PersistenceIntegrityCategory.METADATA_PAYLOAD_MISMATCH,
            forbidden_values=(
                conversation.owner_customer_id,
                "p0-session-alice",
                "Cookie",
                "UniqueViolation",
            ),
        )

        with adapter.session_factory() as session:
            rows = tuple(session.scalars(select(P0RecordModel)))
            assert len(rows) == 1
            decoded = decode_persistence_record(
                rows[0].envelope,
                expected_record_code=P0RecordCode.CONVERSATION_RECORD,
                correlation_ref=UUID(int=801),
            )
            assert decoded.source_record == conversation
    finally:
        if event.contains(
            engine,
            "before_cursor_execute",
            synchronize_record_inserts,
        ):
            event.remove(
                engine,
                "before_cursor_execute",
                synchronize_record_inserts,
            )
        engine.dispose()


async def test_unknown_physical_record_code_has_no_raw_exception_context_or_secret(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    conversation = _record_cases()[0].record
    secret_record_code = "unknown-Cookie-p0-session-alice-customer-A"
    try:
        await adapter.save_conversation(conversation)
        with adapter.session_factory() as session:
            row = session.scalar(select(P0RecordModel))
            assert row is not None
            row.record_code = secret_record_code
            with pytest.raises(P0PersistenceIntegrityError) as captured:
                adapter._decode_row(session, row)
            session.rollback()

        _assert_bounded_integrity_error(
            captured.value,
            category=P0PersistenceIntegrityCategory.UNKNOWN_RECORD_CODE,
            forbidden_values=(secret_record_code, "Cookie", "p0-session-alice"),
        )
    finally:
        engine.dispose()


async def test_owner_scope_is_applied_before_payload_and_stored_owner_never_grants(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    alice_case = _record_cases()[0]
    bob_conversation = alice_case.record.model_copy(
        update={
            "conversation_id": UUID(int=991),
            "owner_customer_id": "customer-B",
        }
    )
    try:
        await adapter.save_conversation(alice_case.record)
        await adapter.save_conversation(bob_conversation)

        assert (
            await adapter.load_conversation_for_owner(
                owner_scope=_owner_scope("customer-A"),
                conversation_id=bob_conversation.conversation_id,
            )
            is None
        )

        with adapter.session_factory.begin() as session:
            session.execute(
                update(P0RecordModel)
                .where(
                    P0RecordModel.record_code
                    == P0RecordCode.CONVERSATION_RECORD.value,
                    P0RecordModel.logical_identity
                    == [["conversation_id", str(bob_conversation.conversation_id)]],
                )
                .values(scope_owner_customer_id="customer-A")
            )

        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.load_conversation_for_owner(
                owner_scope=_owner_scope("customer-A"),
                conversation_id=bob_conversation.conversation_id,
            )
    finally:
        engine.dispose()


async def test_owner_graph_rejects_null_scope_on_private_linked_target(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    conversation = next(
        case.record
        for case in _record_cases()
        if case.code is P0RecordCode.CONVERSATION_RECORD
    )
    try:
        await _seed_all_records(adapter)
        with adapter.session_factory.begin() as session:
            result = session.execute(
                update(P0RecordModel)
                .where(
                    P0RecordModel.record_code
                    == P0RecordCode.CONVERSATION_RECORD.value,
                    P0RecordModel.conversation_id
                    == conversation.conversation_id,
                )
                .values(scope_owner_customer_id=None)
            )
            assert result.rowcount == 1

        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.list_messages_for_owner(
                owner_scope=_owner_scope(conversation.owner_customer_id),
                conversation_id=conversation.conversation_id,
                limit=10,
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("tamper_kind", ("gap", "reordered"))
async def test_normalized_reference_ordinals_reject_drift(
    eval_postgres_namespace,
    tamper_kind: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    manifest = next(
        case.record
        for case in _record_cases()
        if case.code is P0RecordCode.CONTEXT_MANIFEST_RECORD
    )
    try:
        await _seed_all_records(adapter)
        with adapter.session_factory.begin() as session:
            references = tuple(
                session.scalars(
                    select(P0RecordReferenceModel)
                    .where(
                        P0RecordReferenceModel.source_record_code
                        == P0RecordCode.CONTEXT_MANIFEST_RECORD.value
                    )
                    .order_by(P0RecordReferenceModel.ordinal)
                )
            )
            assert len(references) >= 2
            if tamper_kind == "gap":
                references[-1].ordinal += 1
            else:
                first, second = references[:2]
                temporary = len(references) + 10
                first_ordinal = first.ordinal
                second_ordinal = second.ordinal
                first.ordinal = temporary
                session.flush()
                second.ordinal = first_ordinal
                session.flush()
                first.ordinal = second_ordinal

        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.load_context_manifest_for_owner(
                owner_scope=_owner_scope(),
                context_manifest_id=manifest.context_manifest_id,
            )
    finally:
        engine.dispose()


async def test_reference_ordinal_database_constraint_rejects_negative_tamper(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    try:
        await _seed_all_records(adapter)
        with pytest.raises(IntegrityError):
            with adapter.session_factory.begin() as session:
                reference_id = session.scalar(
                    select(P0RecordReferenceModel.reference_id)
                    .order_by(P0RecordReferenceModel.reference_id)
                    .limit(1)
                )
                assert reference_id is not None
                session.execute(
                    update(P0RecordReferenceModel)
                    .where(
                        P0RecordReferenceModel.reference_id == reference_id
                    )
                    .values(ordinal=-1)
                )
    finally:
        engine.dispose()
