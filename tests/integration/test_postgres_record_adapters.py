from __future__ import annotations

import asyncio
import ast
import inspect
import json
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic_core import to_jsonable_python
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import IntegrityError

from mini_agent.application.persistence import (
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
    ExactRunEvidenceClosure,
    TrustedOwnerScope,
)
from mini_agent.core.identity import CustomerContext
from mini_agent.core.request_understanding import ReferenceSourceKindV2
from mini_agent.core.task_state import DurableResolvedReferenceCandidateV2
from mini_agent.infrastructure.persistence import postgres as postgres_persistence
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
from test_record_contracts import (  # noqa: E402
    _minimal_exact_run_evidence,
    _rebuild_exact_run_evidence,
    _rejected_gate_exact_run_evidence,
    _request_understanding_exact_run_evidence,
    _tool_exact_run_evidence,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def test_postgres_request_understanding_surface_is_v2_only() -> None:
    production_tree = ast.parse(inspect.getsource(postgres_persistence))
    adapter_class = next(
        node
        for node in production_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "PostgresRecordAdapter"
    )
    imported_identifiers = {
        identifier
        for node in production_tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        for identifier in (alias.name, alias.asname)
        if identifier is not None
    }
    production_names = {
        node.id for node in ast.walk(production_tree) if isinstance(node, ast.Name)
    }
    production_attributes = {
        node.attr
        for node in ast.walk(production_tree)
        if isinstance(node, ast.Attribute)
    }
    adapter_methods = {
        node.name
        for node in adapter_class.body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    legacy_types = {
        "AcceptedTaskDelta",
        "CreateInitialTaskGraphCommand",
        "RequestUnderstandingRecord",
    }
    legacy_methods = {
        "create_initial_task_graph_if_current",
        "load_accepted_task_delta_for_owner",
        "load_request_understanding_for_owner",
    }
    assert imported_identifiers.isdisjoint(legacy_types)
    assert production_names.isdisjoint(legacy_types)
    assert adapter_methods.isdisjoint(legacy_methods)
    assert production_attributes.isdisjoint(legacy_methods)
    assert {
        "AcceptedTaskDeltaV2",
        "CreateInitialTaskGraphV2Command",
        "RequestUnderstandingRecordV2",
    } <= imported_identifiers
    assert {
        "create_initial_task_graph_v2_if_current",
        "save_request_understanding_v2_no_task_if_current",
    } <= adapter_methods

    owned_test_paths = (
        Path(__file__),
        Path(__file__).with_name("test_postgres_atomicity.py"),
        Path(__file__).with_name(
            "test_postgres_v2_request_understanding_writes.py"
        ),
    )
    forbidden_test_names = legacy_types | {
        "_initial_graph",
        "_legacy_graph_for",
    }
    for path in owned_test_paths:
        tree = ast.parse(path.read_text())
        referenced_names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        referenced_attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        dynamic_attribute_names = {
            node.args[1].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"delattr", "getattr", "hasattr", "setattr"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        }
        record_case_consumers = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "_record_cases"
                for child in ast.walk(node)
            )
        }
        assert referenced_names.isdisjoint(forbidden_test_names)
        assert referenced_attributes.isdisjoint(legacy_methods)
        assert dynamic_attribute_names.isdisjoint(legacy_methods)
        assert record_case_consumers == (
            {"_non_ru_record_cases"} if path == Path(__file__) else set()
        )

    assert (
        '"request_understanding_record.p0.v1"'
        in inspect.getsource(
            PostgresRecordAdapter._ru_v2_write_check_metadata_rows
        )
    )
    assert all(
        envelope.record_code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
        for envelope in _encoded_non_ru_record_set()
    )


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


def _non_ru_record_cases():
    return tuple(
        case
        for case in _record_cases()
        if case.code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    )


def _encode_non_ru_record_case(
    case,
    *,
    record,
    logical_children,
) -> P0PersistenceEnvelope:
    assert case.code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    return encode_persistence_record(
        case.code,
        record,
        external_references=case.external_references,
        logical_children=logical_children,
    )


def _encoded_non_ru_record_set() -> tuple[P0PersistenceEnvelope, ...]:
    return tuple(
        _encode_non_ru_record_case(
            case,
            record=case.record,
            logical_children=case.logical_children,
        )
        for case in _non_ru_record_cases()
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


async def _seed_non_ru_records(adapter: PostgresRecordAdapter) -> None:
    with adapter.session_factory.begin() as session:
        adapter._persist_envelopes(session, _encoded_non_ru_record_set())


_EXACT_VERSION_BY_CODE = {
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
_EXACT_PRIVATE_CODES = frozenset(
    code
    for code in _EXACT_VERSION_BY_CODE
    if code is not P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT
)


def _reference(
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
                to_jsonable_python(value, serialize_unknown=True),
            ),
        ),
    )


def _closure_envelopes(
    closure: ExactRunEvidenceClosure,
) -> tuple[P0PersistenceEnvelope, ...]:
    records: list[
        tuple[
            P0RecordCode,
            object,
            tuple[P0RecordReference, ...],
            tuple[object, ...],
        ]
    ] = [
        (
            P0RecordCode.CONVERSATION_RECORD,
            closure.conversation_record,
            (),
            (),
        ),
        (
            P0RecordCode.AGENT_RUN_RECORD,
            closure.run_record,
            (),
            (),
        ),
    ]
    records.extend(
        (P0RecordCode.MESSAGE_RECORD, record, (), ())
        for record in closure.message_records
    )
    if closure.request_understanding_record is not None:
        records.append(
            (
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                closure.request_understanding_record,
                (),
                closure.accepted_task_deltas,
            )
        )
    unit_by_binding = {
        binding_ref: unit
        for unit in closure.request_unit_records
        for binding_ref in unit.input_binding_refs
    }
    records.extend(
        (
            P0RecordCode.INPUT_BINDING_RECORD,
            binding,
            (
                _reference(
                    "request_unit_id",
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    "request_unit_id",
                    unit_by_binding[binding.binding_id].request_unit_id,
                ),
            ),
            (),
        )
        for binding in closure.input_binding_records
    )
    transitions_by_task = {
        task.task_id: tuple(
            transition
            for transition in closure.task_state_transitions
            if transition.task_id == task.task_id
        )
        for task in closure.task_records
    }
    records.extend(
        (
            P0RecordCode.TASK_RECORD,
            task,
            (),
            transitions_by_task[task.task_id],
        )
        for task in closure.task_records
    )
    for code, family in (
        (P0RecordCode.REQUEST_UNIT_RECORD, closure.request_unit_records),
        (
            P0RecordCode.CONVERSATION_TASK_LINK_RECORD,
            closure.conversation_task_links,
        ),
        (P0RecordCode.RUN_TASK_LINK_RECORD, closure.run_task_links),
        (P0RecordCode.GATE_DECISION_RECORD, closure.gate_decisions),
    ):
        records.extend((code, record, (), ()) for record in family)
    attempts_by_call = {
        call.tool_call_id: tuple(
            attempt
            for attempt in closure.tool_attempts
            if attempt.tool_call_id == call.tool_call_id
        )
        for call in closure.tool_calls
    }
    records.extend(
        (
            P0RecordCode.TOOL_CALL_RECORD,
            call,
            (),
            attempts_by_call[call.tool_call_id],
        )
        for call in closure.tool_calls
    )
    call_by_result = {
        call.result_ref: call
        for call in closure.tool_calls
        if call.result_ref is not None
    }
    records.extend(
        (
            P0RecordCode.OBSERVATION_RECORD,
            observation,
            (
                _reference(
                    "source_tool_call_id",
                    P0RecordCode.TOOL_CALL_RECORD,
                    "tool_call_id",
                    call_by_result[observation.observation_id].tool_call_id,
                ),
                _reference(
                    "source_run_id",
                    P0RecordCode.AGENT_RUN_RECORD,
                    "run_id",
                    call_by_result[observation.observation_id].run_id,
                ),
                _reference(
                    "source_task_id",
                    P0RecordCode.TASK_RECORD,
                    "task_id",
                    call_by_result[observation.observation_id].task_id,
                ),
                _reference(
                    "source_request_unit_id",
                    P0RecordCode.REQUEST_UNIT_RECORD,
                    "request_unit_id",
                    call_by_result[observation.observation_id].request_unit_id,
                ),
            ),
            (),
        )
        for observation in closure.observation_records
    )
    for code, family in (
        (P0RecordCode.CONTEXT_MANIFEST_RECORD, closure.context_manifests),
        (
            P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
            closure.model_visible_toolset_artifacts,
        ),
        (P0RecordCode.TRACE_EVENT_RECORD, closure.trace_events),
    ):
        records.extend((code, record, (), ()) for record in family)
    return tuple(
        encode_persistence_record_versioned(
            code,
            _EXACT_VERSION_BY_CODE[code],
            record,
            external_references=external_references,
            logical_children=logical_children,
        )
        for code, record, external_references, logical_children in records
    )


def _physical_row(
    envelope: P0PersistenceEnvelope,
    *,
    owner_customer_id: str,
) -> P0RecordModel:
    code = envelope.record_code
    version = _EXACT_VERSION_BY_CODE[code]
    decoded = decode_persistence_record_versioned(
        envelope,
        expected_record_code=code,
        expected_schema_version=version,
        correlation_ref=uuid4(),
    )
    record = decoded.source_record

    def uuid_projection(field_name: str) -> UUID | None:
        value = getattr(record, field_name, None)
        return value if type(value) is UUID else None

    status = getattr(record, "status", None)
    lifecycle_status = status.value if isinstance(status, Enum) else None
    state_version = getattr(record, "state_version", None)
    attempt_count = getattr(record, "attempt_count", None)
    started_at = getattr(record, "started_at", None)
    return P0RecordModel(
        record_id=uuid4(),
        record_code=code.value,
        record_schema_version=version,
        logical_identity=to_jsonable_python(
            envelope.logical_identity,
            serialize_unknown=True,
        ),
        direct_owner_customer_id=envelope.direct_owner_customer_id,
        scope_owner_customer_id=(
            owner_customer_id if code in _EXACT_PRIVATE_CODES else None
        ),
        conversation_id=uuid_projection("conversation_id"),
        run_id=uuid_projection("run_id"),
        task_id=uuid_projection("task_id"),
        request_unit_id=uuid_projection("request_unit_id"),
        lifecycle_status=lifecycle_status,
        state_version=state_version if type(state_version) is int else None,
        attempt_count=attempt_count if type(attempt_count) is int else None,
        recovery_sort_at=(
            started_at
            if code is P0RecordCode.AGENT_RUN_RECORD
            and isinstance(started_at, datetime)
            else None
        ),
        envelope=envelope.model_dump(mode="json"),
    )


def _physical_reference_models(
    envelope: P0PersistenceEnvelope,
) -> tuple[P0RecordReferenceModel, ...]:
    source_identity = to_jsonable_python(
        envelope.logical_identity,
        serialize_unknown=True,
    )
    return tuple(
        P0RecordReferenceModel(
            reference_id=uuid4(),
            source_record_code=envelope.record_code.value,
            source_logical_identity=source_identity,
            ordinal=ordinal,
            relation=reference.relation,
            target_record_code=reference.target_record_code.value,
            target_logical_identity=to_jsonable_python(
                reference.target_logical_identity,
                serialize_unknown=True,
            ),
        )
        for ordinal, reference in enumerate(envelope.record_references)
    )


async def _seed_exact_closure(
    adapter: PostgresRecordAdapter,
    closure: ExactRunEvidenceClosure,
) -> None:
    envelopes = _closure_envelopes(closure)
    with adapter.session_factory.begin() as session:
        session.add_all(
            _physical_row(
                envelope,
                owner_customer_id=closure.conversation_record.owner_customer_id,
            )
            for envelope in envelopes
        )
        session.flush()
        session.add_all(
            reference
            for envelope in envelopes
            for reference in _physical_reference_models(envelope)
        )


def _row_for_code(
    session,
    code: P0RecordCode,
) -> P0RecordModel:
    row = session.scalar(
        select(P0RecordModel).where(P0RecordModel.record_code == code.value)
    )
    assert row is not None
    return row


def _json_set(values: tuple[object, ...]) -> set[str]:
    return {
        json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        for value in values
    }


def _provenance_exact_run_evidence() -> ExactRunEvidenceClosure:
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    record = closure.request_understanding_record
    assert record is not None
    message = closure.message_records[0]
    order_id = "O-1001"
    start = message.content.index(order_id)
    end = start + len(order_id)
    resolved = DurableResolvedReferenceCandidateV2(
        name="order_id",
        candidate_value=order_id,
        source_kind=ReferenceSourceKindV2.RECENT_MESSAGE,
        source_ref=message.message_id,
        source_span_start=start,
        source_span_end_exclusive=end,
        source_quote_sha256=sha256(
            message.content[start:end].encode("utf-8")
        ).hexdigest(),
        confidence=0.99,
    )
    contextualization = record.contextualization.model_copy(
        update={"resolved_reference_candidates": (resolved,)}
    )
    return _rebuild_exact_run_evidence(
        closure,
        request_understanding_record=record.model_copy(
            update={"contextualization": contextualization}
        ),
    )


def _clone_row(
    row: P0RecordModel,
    *,
    logical_identity: list[list[object]] | None = None,
) -> P0RecordModel:
    return P0RecordModel(
        record_id=uuid4(),
        record_code=row.record_code,
        record_schema_version=row.record_schema_version,
        logical_identity=(
            logical_identity
            if logical_identity is not None
            else [["synthetic_id", str(uuid4())]]
        ),
        direct_owner_customer_id=row.direct_owner_customer_id,
        scope_owner_customer_id=row.scope_owner_customer_id,
        conversation_id=row.conversation_id,
        run_id=row.run_id,
        task_id=row.task_id,
        request_unit_id=row.request_unit_id,
        lifecycle_status=row.lifecycle_status,
        state_version=row.state_version,
        attempt_count=row.attempt_count,
        recovery_sort_at=row.recovery_sort_at,
        envelope=json.loads(json.dumps(row.envelope)),
    )


def _clone_references(
    session,
    *,
    source: P0RecordModel,
    clone: P0RecordModel,
) -> None:
    references = tuple(
        session.scalars(
            select(P0RecordReferenceModel)
            .where(
                P0RecordReferenceModel.source_record_code
                == source.record_code,
                P0RecordReferenceModel.source_logical_identity
                == source.logical_identity,
            )
            .order_by(P0RecordReferenceModel.ordinal)
        )
    )
    session.add_all(
        P0RecordReferenceModel(
            reference_id=uuid4(),
            source_record_code=clone.record_code,
            source_logical_identity=clone.logical_identity,
            ordinal=reference.ordinal,
            relation=reference.relation,
            target_record_code=reference.target_record_code,
            target_logical_identity=reference.target_logical_identity,
        )
        for reference in references
    )


async def test_all_non_ru_records_and_five_external_references_round_trip_exactly(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    cases = _non_ru_record_cases()
    try:
        await _seed_non_ru_records(adapter)

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
                code.value
                for code in P0RecordCode
                if code is not P0RecordCode.REQUEST_UNDERSTANDING_RECORD
            }
            assert len(rows) == 16
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
                    _encode_non_ru_record_case(
                        expected,
                        record=expected.record,
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
    conversation = _non_ru_record_cases()[0].record
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
    conversation = _non_ru_record_cases()[0].record
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


async def test_owner_scoped_read_bounds_malformed_physical_envelope(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    conversation = _non_ru_record_cases()[0].record
    raw_secret = "Cookie=p0-session-envelope-secret"
    try:
        await adapter.save_conversation(conversation)
        with adapter.session_factory.begin() as session:
            row = session.scalar(
                select(P0RecordModel).where(
                    P0RecordModel.record_code
                    == P0RecordCode.CONVERSATION_RECORD.value
                )
            )
            assert row is not None
            malformed = json.loads(json.dumps(row.envelope))
            malformed["logical_identity"] = [
                ["conversation_id", {"raw_secret": raw_secret}]
            ]
            row.envelope = malformed

        with pytest.raises(P0PersistenceIntegrityError) as captured:
            await adapter.load_conversation_for_owner(
                owner_scope=_owner_scope(conversation.owner_customer_id),
                conversation_id=conversation.conversation_id,
            )

        _assert_bounded_integrity_error(
            captured.value,
            category=P0PersistenceIntegrityCategory.PAYLOAD_VALIDATION_FAILED,
            forbidden_values=(
                raw_secret,
                "ValidationError",
                "logical_identity",
            ),
        )
    finally:
        engine.dispose()


async def test_owner_scope_is_applied_before_payload_and_stored_owner_never_grants(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    alice_case = _non_ru_record_cases()[0]
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
        for case in _non_ru_record_cases()
        if case.code is P0RecordCode.CONVERSATION_RECORD
    )
    try:
        await _seed_non_ru_records(adapter)
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
        for case in _non_ru_record_cases()
        if case.code is P0RecordCode.CONTEXT_MANIFEST_RECORD
    )
    try:
        await _seed_non_ru_records(adapter)
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
        await _seed_non_ru_records(adapter)
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


def _assert_same_exact_closure(
    actual: ExactRunEvidenceClosure,
    expected: ExactRunEvidenceClosure,
) -> None:
    assert actual.conversation_record == expected.conversation_record
    assert actual.run_record == expected.run_record
    assert (
        actual.request_understanding_record
        == expected.request_understanding_record
    )
    for field_name in (
        "message_records",
        "accepted_task_deltas",
        "input_binding_records",
        "task_records",
        "task_state_transitions",
        "request_unit_records",
        "conversation_task_links",
        "run_task_links",
        "gate_decisions",
        "tool_calls",
        "tool_attempts",
        "observation_records",
        "context_manifests",
        "model_visible_toolset_artifacts",
        "trace_events",
    ):
        assert _json_set(getattr(actual, field_name)) == _json_set(
            getattr(expected, field_name)
        ), field_name


def _assert_canonical_top_level_order(
    closure: ExactRunEvidenceClosure,
) -> None:
    identities_by_code: dict[P0RecordCode, list[str]] = {}
    for envelope in _closure_envelopes(closure):
        identities_by_code.setdefault(envelope.record_code, []).append(
            json.dumps(
                to_jsonable_python(
                    envelope.logical_identity,
                    serialize_unknown=True,
                ),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    for record_code, identities in identities_by_code.items():
        assert identities == sorted(identities), record_code


@pytest.mark.parametrize(
    "closure_factory",
    (
        _minimal_exact_run_evidence,
        lambda: _request_understanding_exact_run_evidence(
            candidate_count=2,
            accepted_count=1,
        ),
        _provenance_exact_run_evidence,
        _tool_exact_run_evidence,
        _rejected_gate_exact_run_evidence,
    ),
    ids=(
        "input-invalid-no-task",
        "ru-v2-partial-accept",
        "ru-v2-contextualization-provenance",
        "get-order-success",
        "gateway-rejected-no-tool",
    ),
)
async def test_exact_run_reader_returns_representative_closed_graphs(
    eval_postgres_namespace,
    closure_factory: Callable[[], ExactRunEvidenceClosure],
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = closure_factory()
    try:
        await _seed_exact_closure(adapter, closure)

        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope(
                closure.conversation_record.owner_customer_id
            ),
            run_id=closure.run_record.run_id,
        )
        repeated = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope(
                closure.conversation_record.owner_customer_id
            ),
            run_id=closure.run_record.run_id,
        )

        assert loaded is not None
        assert repeated == loaded
        _assert_canonical_top_level_order(loaded)
        _assert_same_exact_closure(loaded, closure)
    finally:
        engine.dispose()


async def test_exact_run_reader_prefilters_trusted_owner_before_any_graph_payload(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_select(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(statement.lower().split()))

    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _tool_exact_run_evidence()
    try:
        await _seed_exact_closure(adapter, closure)
        statements.clear()

        foreign = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope("customer-B"),
            run_id=closure.run_record.run_id,
        )
        absent = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope("customer-B"),
            run_id=uuid4(),
        )

        assert foreign is None
        assert absent is None
        assert len(statements) == 2
        assert all("p0_record_references" not in statement for statement in statements)
        assert all("p0_records.record_code =" in statement for statement in statements)
        assert all("p0_records.run_id =" in statement for statement in statements)
        assert all(
            "p0_records.scope_owner_customer_id =" in statement
            for statement in statements
        )
        assert all("limit" in statement for statement in statements)
    finally:
        engine.dispose()


async def test_exact_run_reader_requires_exact_trusted_inputs(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    owner = _owner_scope()
    try:
        with pytest.raises(TypeError):
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=owner.model_dump(),  # type: ignore[arg-type]
                run_id=uuid4(),
            )
        with pytest.raises(TypeError):
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=owner,
                run_id=str(uuid4()),  # type: ignore[arg-type]
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "tamper_kind",
    (
        "ru-v1-physical-version",
        "foreign-scope-child",
        "missing-run-projection",
        "missing-run-reference",
        "invalid-run-reference-relation",
    ),
)
async def test_exact_run_reader_fails_closed_on_version_owner_projection_and_reference_drift(
    eval_postgres_namespace,
    tamper_kind: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _request_understanding_exact_run_evidence(
        candidate_count=1,
        accepted_count=1,
    )
    raw_secret = "Cookie=reader-secret customer-A O-1001"
    try:
        await _seed_exact_closure(adapter, closure)
        with adapter.session_factory.begin() as session:
            if tamper_kind == "ru-v1-physical-version":
                row = _row_for_code(
                    session,
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                )
                row.record_schema_version = (
                    "request_understanding_record.p0.v1"
                )
            else:
                trace = session.scalar(
                    select(P0RecordModel)
                    .where(
                        P0RecordModel.record_code
                        == P0RecordCode.TRACE_EVENT_RECORD.value
                    )
                    .order_by(P0RecordModel.record_id)
                )
                assert trace is not None
                run_reference = session.scalar(
                    select(P0RecordReferenceModel).where(
                        P0RecordReferenceModel.source_record_code
                        == trace.record_code,
                        P0RecordReferenceModel.source_logical_identity
                        == trace.logical_identity,
                        P0RecordReferenceModel.relation == "run_id",
                    )
                )
                assert run_reference is not None
                if tamper_kind == "foreign-scope-child":
                    trace.scope_owner_customer_id = "customer-B"
                elif tamper_kind == "missing-run-projection":
                    trace.run_id = None
                elif tamper_kind == "missing-run-reference":
                    session.delete(run_reference)
                else:
                    run_reference.relation = raw_secret

        with pytest.raises(P0PersistenceIntegrityError) as captured:
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=_owner_scope(),
                run_id=closure.run_record.run_id,
            )
        _assert_bounded_integrity_error(
            captured.value,
            category=captured.value.category,
            forbidden_values=(
                raw_secret,
                "Cookie",
                "customer-A",
                "O-1001",
                "SELECT",
            ),
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("candidate_family", "tamper_kind"),
    (
        ("contextualization", "span-out-of-range"),
        ("contextualization", "quote-hash"),
        ("task-input", "span-out-of-range"),
        ("task-input", "quote-hash"),
    ),
)
async def test_exact_run_reader_replays_ru_v2_message_provenance_exactly(
    eval_postgres_namespace,
    candidate_family: str,
    tamper_kind: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _provenance_exact_run_evidence()
    try:
        await _seed_exact_closure(adapter, closure)
        with adapter.session_factory.begin() as session:
            row = _row_for_code(
                session,
                P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
            )
            envelope = json.loads(json.dumps(row.envelope))
            if candidate_family == "contextualization":
                candidate = envelope["payload"]["data"]["contextualization"][
                    "resolved_reference_candidates"
                ][0]
            else:
                candidate = envelope["payload"]["data"][
                    "task_delta_candidates"
                ][0]["input_candidates"][0]
            if tamper_kind == "span-out-of-range":
                candidate["source_span_end_exclusive"] = 10_000
            else:
                candidate["source_quote_sha256"] = sha256(
                    b"forged quote"
                ).hexdigest()
            row.envelope = envelope

        with pytest.raises(P0PersistenceIntegrityError) as captured:
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=_owner_scope(),
                run_id=closure.run_record.run_id,
            )
        _assert_bounded_integrity_error(
            captured.value,
            category=captured.value.category,
            forbidden_values=(
                closure.message_records[0].content,
                "O-1001",
                "task_delta_candidates",
            ),
        )
    finally:
        engine.dispose()


async def test_rejected_gate_is_found_by_manifest_and_binding_reverse_edges(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _rejected_gate_exact_run_evidence()
    try:
        await _seed_exact_closure(adapter, closure)

        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope(),
            run_id=closure.run_record.run_id,
        )
        assert loaded is not None
        assert loaded.gate_decisions == closure.gate_decisions
        assert loaded.tool_calls == ()

        with adapter.session_factory.begin() as session:
            result = session.execute(
                delete(P0RecordReferenceModel).where(
                    P0RecordReferenceModel.source_record_code
                    == P0RecordCode.GATE_DECISION_RECORD.value,
                    P0RecordReferenceModel.relation == "context_manifest_id",
                )
            )
            assert result.rowcount == 1

        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=_owner_scope(),
                run_id=closure.run_record.run_id,
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("cap_kind", "closure_factory"),
    (
        ("run-root-2", _minimal_exact_run_evidence),
        ("conversation-2", _minimal_exact_run_evidence),
        ("message-65", _minimal_exact_run_evidence),
        (
            "request-understanding-2",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        (
            "task-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        (
            "request-unit-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        (
            "conversation-task-link-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        (
            "run-task-link-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        (
            "input-binding-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        ("context-manifest-3", _minimal_exact_run_evidence),
        ("toolset-artifact-3", _minimal_exact_run_evidence),
        ("gate-decision-2", _rejected_gate_exact_run_evidence),
        ("tool-call-2", _tool_exact_run_evidence),
        ("observation-2", _tool_exact_run_evidence),
        ("trace-event-65", _minimal_exact_run_evidence),
        ("normalized-reference-65", _minimal_exact_run_evidence),
        (
            "accepted-task-delta-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        (
            "task-transition-65",
            lambda: _request_understanding_exact_run_evidence(
                candidate_count=1,
                accepted_count=1,
            ),
        ),
        ("tool-attempt-2", _tool_exact_run_evidence),
    ),
)
async def test_exact_run_reader_enforces_every_frozen_cap_class_before_materialization(
    eval_postgres_namespace,
    cap_kind: str,
    closure_factory: Callable[[], ExactRunEvidenceClosure],
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = closure_factory()
    try:
        await _seed_exact_closure(adapter, closure)
        with adapter.session_factory.begin() as session:
            if cap_kind == "run-root-2":
                source = _row_for_code(
                    session,
                    P0RecordCode.AGENT_RUN_RECORD,
                )
                session.add(_clone_row(source))
            elif cap_kind == "conversation-2":
                source = _row_for_code(
                    session,
                    P0RecordCode.CONVERSATION_RECORD,
                )
                clone = _clone_row(source)
                session.add(clone)
                session.flush()
                message = _row_for_code(
                    session,
                    P0RecordCode.MESSAGE_RECORD,
                )
                highest = session.scalar(
                    select(P0RecordReferenceModel.ordinal)
                    .where(
                        P0RecordReferenceModel.source_record_code
                        == message.record_code,
                        P0RecordReferenceModel.source_logical_identity
                        == message.logical_identity,
                    )
                    .order_by(P0RecordReferenceModel.ordinal.desc())
                    .limit(1)
                )
                assert highest is not None
                session.add(
                    P0RecordReferenceModel(
                        reference_id=uuid4(),
                        source_record_code=message.record_code,
                        source_logical_identity=message.logical_identity,
                        ordinal=highest + 1,
                        relation="conversation_id",
                        target_record_code=source.record_code,
                        target_logical_identity=clone.logical_identity,
                    )
                )
            elif cap_kind == "message-65":
                source = _row_for_code(
                    session,
                    P0RecordCode.MESSAGE_RECORD,
                )
                clones = tuple(_clone_row(source) for _ in range(64))
                session.add_all(clones)
                manifest = _row_for_code(
                    session,
                    P0RecordCode.CONTEXT_MANIFEST_RECORD,
                )
                manifest_clone = _clone_row(manifest)
                manifest_clone.run_id = closure.run_record.run_id
                session.add(manifest_clone)
                session.flush()
                _clone_references(
                    session,
                    source=manifest,
                    clone=manifest_clone,
                )
                session.flush()
                for reference_source, targets in (
                    (manifest, clones[:32]),
                    (manifest_clone, clones[32:]),
                ):
                    highest = session.scalar(
                        select(P0RecordReferenceModel.ordinal)
                        .where(
                            P0RecordReferenceModel.source_record_code
                            == reference_source.record_code,
                            P0RecordReferenceModel.source_logical_identity
                            == reference_source.logical_identity,
                        )
                        .order_by(P0RecordReferenceModel.ordinal.desc())
                        .limit(1)
                    )
                    assert highest is not None
                    session.add_all(
                        P0RecordReferenceModel(
                            reference_id=uuid4(),
                            source_record_code=reference_source.record_code,
                            source_logical_identity=(
                                reference_source.logical_identity
                            ),
                            ordinal=highest + offset,
                            relation="selected_message_ref",
                            target_record_code=source.record_code,
                            target_logical_identity=target.logical_identity,
                        )
                        for offset, target in enumerate(targets, start=1)
                    )
            elif cap_kind == "request-understanding-2":
                source = _row_for_code(
                    session,
                    P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
                )
                session.add(_clone_row(source))
            elif cap_kind in {
                "task-65",
                "request-unit-65",
                "conversation-task-link-65",
                "run-task-link-65",
                "input-binding-65",
            }:
                code = {
                    "task-65": P0RecordCode.TASK_RECORD,
                    "request-unit-65": P0RecordCode.REQUEST_UNIT_RECORD,
                    "conversation-task-link-65": (
                        P0RecordCode.CONVERSATION_TASK_LINK_RECORD
                    ),
                    "run-task-link-65": P0RecordCode.RUN_TASK_LINK_RECORD,
                    "input-binding-65": P0RecordCode.INPUT_BINDING_RECORD,
                }[cap_kind]
                source = _row_for_code(session, code)
                clones = tuple(_clone_row(source) for _ in range(64))
                for clone in clones:
                    clone.run_id = closure.run_record.run_id
                session.add_all(clones)
                if cap_kind == "input-binding-65":
                    session.flush()
                    for clone in clones:
                        _clone_references(
                            session,
                            source=source,
                            clone=clone,
                        )
            elif cap_kind == "context-manifest-3":
                source = _row_for_code(
                    session,
                    P0RecordCode.CONTEXT_MANIFEST_RECORD,
                )
                session.add_all((_clone_row(source), _clone_row(source)))
            elif cap_kind == "toolset-artifact-3":
                source = _row_for_code(
                    session,
                    P0RecordCode.MODEL_VISIBLE_TOOLSET_ARTIFACT,
                )
                first = _clone_row(source)
                second = _clone_row(source)
                session.add_all((first, second))
                session.flush()
                manifest = _row_for_code(
                    session,
                    P0RecordCode.CONTEXT_MANIFEST_RECORD,
                )
                current_count = session.scalar(
                    select(P0RecordReferenceModel.ordinal)
                    .where(
                        P0RecordReferenceModel.source_record_code
                        == manifest.record_code,
                        P0RecordReferenceModel.source_logical_identity
                        == manifest.logical_identity,
                    )
                    .order_by(P0RecordReferenceModel.ordinal.desc())
                    .limit(1)
                )
                assert current_count is not None
                session.add_all(
                    P0RecordReferenceModel(
                        reference_id=uuid4(),
                        source_record_code=manifest.record_code,
                        source_logical_identity=manifest.logical_identity,
                        ordinal=current_count + offset,
                        relation="model_visible_toolset_hash",
                        target_record_code=source.record_code,
                        target_logical_identity=target.logical_identity,
                    )
                    for offset, target in enumerate(
                        (first, second),
                        start=1,
                    )
                )
            elif cap_kind in {
                "gate-decision-2",
                "tool-call-2",
                "observation-2",
            }:
                code = {
                    "gate-decision-2": P0RecordCode.GATE_DECISION_RECORD,
                    "tool-call-2": P0RecordCode.TOOL_CALL_RECORD,
                    "observation-2": P0RecordCode.OBSERVATION_RECORD,
                }[cap_kind]
                source = _row_for_code(session, code)
                clone = _clone_row(source)
                session.add(clone)
                session.flush()
                _clone_references(
                    session,
                    source=source,
                    clone=clone,
                )
            elif cap_kind == "trace-event-65":
                pass
            elif cap_kind == "normalized-reference-65":
                source = _row_for_code(
                    session,
                    P0RecordCode.AGENT_RUN_RECORD,
                )
                target = _row_for_code(
                    session,
                    P0RecordCode.CONVERSATION_RECORD,
                )
                highest = session.scalar(
                    select(P0RecordReferenceModel.ordinal)
                    .where(
                        P0RecordReferenceModel.source_record_code
                        == source.record_code,
                        P0RecordReferenceModel.source_logical_identity
                        == source.logical_identity,
                    )
                    .order_by(P0RecordReferenceModel.ordinal.desc())
                    .limit(1)
                )
                assert highest == 0
                session.add_all(
                    P0RecordReferenceModel(
                        reference_id=uuid4(),
                        source_record_code=source.record_code,
                        source_logical_identity=source.logical_identity,
                        ordinal=index,
                        relation=f"synthetic_relation_{index}",
                        target_record_code=target.record_code,
                        target_logical_identity=target.logical_identity,
                    )
                    for index in range(1, 65)
                )
            else:
                code = {
                    "accepted-task-delta-65": (
                        P0RecordCode.REQUEST_UNDERSTANDING_RECORD
                    ),
                    "task-transition-65": P0RecordCode.TASK_RECORD,
                    "tool-attempt-2": P0RecordCode.TOOL_CALL_RECORD,
                }[cap_kind]
                source = _row_for_code(session, code)
                envelope = json.loads(json.dumps(source.envelope))
                children = envelope["payload"]["logical_children"]
                assert children
                target_count = (
                    2 if cap_kind == "tool-attempt-2" else 65
                )
                envelope["payload"]["logical_children"] = [
                    json.loads(json.dumps(children[0]))
                    for _ in range(target_count)
                ]
                source.envelope = envelope

            if cap_kind == "trace-event-65":
                rows = tuple(
                    session.scalars(
                        select(P0RecordModel).where(
                            P0RecordModel.record_code
                            == P0RecordCode.TRACE_EVENT_RECORD.value
                        )
                    )
                )
                assert len(rows) == 3
                source = rows[0]
                session.add_all(_clone_row(source) for _ in range(62))

        with pytest.raises(P0PersistenceIntegrityError) as captured:
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=_owner_scope(),
                run_id=closure.run_record.run_id,
            )
        assert (
            captured.value.category
            is P0PersistenceIntegrityCategory.LINK_CARDINALITY_MISMATCH
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "evasive_kind",
    (
        "projection-only-extra",
        "reverse-reference-only-extra",
        "cross-run-history-extra",
    ),
)
async def test_exact_run_reader_two_discovery_channels_reject_evasive_extras(
    eval_postgres_namespace,
    evasive_kind: str,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _minimal_exact_run_evidence()
    try:
        await _seed_exact_closure(adapter, closure)
        with adapter.session_factory.begin() as session:
            source = _row_for_code(
                session,
                P0RecordCode.TRACE_EVENT_RECORD,
            )
            clone = _clone_row(source)
            if evasive_kind != "projection-only-extra":
                clone.run_id = (
                    None
                    if evasive_kind == "reverse-reference-only-extra"
                    else uuid4()
                )
            session.add(clone)
            session.flush()
            if evasive_kind != "projection-only-extra":
                run_reference = session.scalar(
                    select(P0RecordReferenceModel).where(
                        P0RecordReferenceModel.source_record_code
                        == source.record_code,
                        P0RecordReferenceModel.source_logical_identity
                        == source.logical_identity,
                        P0RecordReferenceModel.relation == "run_id",
                    )
                )
                assert run_reference is not None
                session.add(
                    P0RecordReferenceModel(
                        reference_id=uuid4(),
                        source_record_code=clone.record_code,
                        source_logical_identity=clone.logical_identity,
                        ordinal=0,
                        relation=run_reference.relation,
                        target_record_code=run_reference.target_record_code,
                        target_logical_identity=(
                            run_reference.target_logical_identity
                        ),
                    )
                )

        with pytest.raises(P0PersistenceIntegrityError):
            await adapter.load_exact_run_evidence_for_owner(
                owner_scope=_owner_scope(),
                run_id=closure.run_record.run_id,
            )
    finally:
        engine.dispose()


async def test_exact_run_reader_queries_reverse_selector_before_projection(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_selector_order(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(statement.lower().split()))

    adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _minimal_exact_run_evidence()
    try:
        await _seed_exact_closure(adapter, closure)
        statements.clear()

        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope(),
            run_id=closure.run_record.run_id,
        )

        assert loaded is not None
        reverse_positions = tuple(
            index
            for index, statement in enumerate(statements)
            if statement.startswith(
                "select distinct "
                "p0_record_references.source_logical_identity"
            )
        )
        projection_positions = tuple(
            index
            for index, statement in enumerate(statements)
            if statement.startswith("select p0_records.logical_identity")
            and "p0_records.run_id =" in statement
        )
        assert reverse_positions
        assert projection_positions
        assert reverse_positions[0] < projection_positions[0]
    finally:
        engine.dispose()


async def test_exact_run_reader_uses_one_repeatable_read_read_only_snapshot(
    eval_postgres_namespace,
) -> None:
    engine = eval_postgres_namespace.build_engine()
    seed_adapter = PostgresRecordAdapter(build_session_factory(engine))
    closure = _minimal_exact_run_evidence()
    statements: list[str] = []
    factory_calls = 0
    updated = False
    try:
        await _seed_exact_closure(seed_adapter, closure)
        message_envelope = next(
            envelope
            for envelope in _closure_envelopes(closure)
            if envelope.record_code is P0RecordCode.MESSAGE_RECORD
        )
        next_envelope = json.loads(message_envelope.model_dump_json())
        next_envelope["payload"]["data"]["content"] = (
            f"{closure.message_records[0].content} after-snapshot"
        )

        @event.listens_for(engine, "after_cursor_execute")
        def update_after_root_snapshot(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            nonlocal updated
            normalized = " ".join(statement.lower().split())
            statements.append(normalized)
            if (
                not updated
                and normalized.startswith("select")
                and "from p0_records" in normalized
                and "p0_records.run_id =" in normalized
                and "p0_records.scope_owner_customer_id =" in normalized
            ):
                updated = True
                with engine.begin() as connection:
                    result = connection.execute(
                        update(P0RecordModel)
                        .where(
                            P0RecordModel.record_code
                            == P0RecordCode.MESSAGE_RECORD.value,
                            P0RecordModel.logical_identity
                            == to_jsonable_python(
                                message_envelope.logical_identity,
                                serialize_unknown=True,
                            ),
                        )
                        .values(envelope=next_envelope)
                    )
                    assert result.rowcount == 1

        real_factory = build_session_factory(engine)

        def counting_factory():
            nonlocal factory_calls
            factory_calls += 1
            return real_factory()

        adapter = PostgresRecordAdapter(counting_factory)
        loaded = await adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope(),
            run_id=closure.run_record.run_id,
        )

        assert updated
        assert factory_calls == 1
        assert loaded is not None
        assert loaded.message_records[0].content == (
            closure.message_records[0].content
        )
        assert sum(
            statement.startswith(
                "set transaction isolation level repeatable read, read only"
            )
            for statement in statements
        ) == 1

        event.remove(engine, "after_cursor_execute", update_after_root_snapshot)
        next_loaded = await seed_adapter.load_exact_run_evidence_for_owner(
            owner_scope=_owner_scope(),
            run_id=closure.run_record.run_id,
        )
        assert next_loaded is not None
        assert next_loaded.message_records[0].content.endswith(
            "after-snapshot"
        )
    finally:
        engine.dispose()
