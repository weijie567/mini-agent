from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import select, update

from mini_agent.application.persistence import (
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
from tests.component.application.test_persistence_contract import _record_cases


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

            external_relations = {
                (reference.source_record_code, reference.relation)
                for reference in references
                if reference.relation
                in {
                    "request_unit_id",
                    "source_tool_call_id",
                    "source_run_id",
                    "source_task_id",
                    "source_request_unit_id",
                }
            }
            assert external_relations == {
                ("input_binding_record", "request_unit_id"),
                ("observation_record", "source_tool_call_id"),
                ("observation_record", "source_run_id"),
                ("observation_record", "source_task_id"),
                ("observation_record", "source_request_unit_id"),
            }
    finally:
        engine.dispose()


async def test_exact_replay_is_idempotent_and_conflicting_replay_is_bounded(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    conversation = _record_cases()[0].record
    try:
        await adapter.save_conversation(conversation)
        await adapter.save_conversation(conversation)

        with adapter.session_factory() as session:
            assert session.scalar(select(P0RecordModel.record_id)) is not None

        conflicting = conversation.model_copy(
            update={"created_at": conversation.created_at.replace(microsecond=1)}
        )
        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.save_conversation(conflicting)

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
