import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from mini_agent.core.task_state import (
    ORDER_CANDIDATE_SET_RECORD_SCHEMA_VERSION,
    ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION,
    OrderCandidateSelectionRecord,
    OrderCandidateSelectionRequest,
    OrderCandidateSetEntry,
    OrderCandidateSetOutcome,
    OrderCandidateSetRecord,
    compute_order_candidate_set_version,
    validate_candidate_set_supersession,
    validate_current_candidate_selection,
)

NOW = datetime(2030, 1, 1, 12, 34, 56, 123456, tzinfo=UTC)
OWNER = "owner-scope:session-1"
CANDIDATE_VERSION_1 = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "1" * 64
)
CANDIDATE_VERSION_2 = (
    "mock-order-search-candidate-source-version.p0.v1:sha256:" + "2" * 64
)
SNAPSHOT_VERSION = (
    "mock-order-search-snapshot-source-version.p0.v1:sha256:" + "a" * 64
)


def _entry(ordinal: int, *, candidate_ref: UUID | None = None) -> OrderCandidateSetEntry:
    return OrderCandidateSetEntry(
        ordinal=ordinal,
        observation_candidate_ref=candidate_ref or uuid4(),
        candidate_source_version=(
            CANDIDATE_VERSION_1 if ordinal == 1 else CANDIDATE_VERSION_2
        ),
    )


def _candidate_set_values(**overrides: object) -> dict[str, object]:
    entries = (_entry(1), _entry(2))
    values: dict[str, object] = {
        "candidate_set_id": uuid4(),
        "private_owner_scope_ref": OWNER,
        "conversation_id": uuid4(),
        "task_id": uuid4(),
        "request_unit_id": uuid4(),
        "outcome": OrderCandidateSetOutcome.MULTIPLE,
        "base_task_state_version": 3,
        "result_task_state_version": 4,
        "selection_expected_task_state_version": 4,
        "query_binding_refs": (uuid4(), uuid4()),
        "source_tool_call_id": uuid4(),
        "search_observation_ref": uuid4(),
        "search_observation_record_schema_version": (
            ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION
        ),
        "search_observation_source_version": SNAPSHOT_VERSION,
        "ordered_candidates": entries,
        "created_at": NOW,
        "valid_until": NOW + timedelta(minutes=15),
        "supersedes_candidate_set_ref": None,
    }
    values.update(overrides)
    values["candidate_set_version"] = compute_order_candidate_set_version(
        **{
            key: value
            for key, value in values.items()
            if key != "candidate_set_version"
        }
    )
    return values


def _candidate_set(**overrides: object) -> OrderCandidateSetRecord:
    return OrderCandidateSetRecord.model_validate(_candidate_set_values(**overrides))


def _selection_request(
    *,
    ordinal: int = 2,
    source_message_ref: UUID | None = None,
    binding_ref: UUID | None = None,
) -> OrderCandidateSelectionRequest:
    return OrderCandidateSelectionRequest(
        source_message_ref=source_message_ref or uuid4(),
        ordinal_input_binding_ref=binding_ref or uuid4(),
        ordinal=ordinal,
    )


def _validate_success(
    candidate_set: OrderCandidateSetRecord,
    request: OrderCandidateSelectionRequest,
    **overrides: object,
) -> OrderCandidateSetEntry:
    arguments: dict[str, object] = {
        "current_candidate_sets": (candidate_set,),
        "request": request,
        "trusted_owner_scope_ref": candidate_set.private_owner_scope_ref,
        "conversation_id": candidate_set.conversation_id,
        "task_id": candidate_set.task_id,
        "request_unit_id": candidate_set.request_unit_id,
        "pending_candidate_set_ref": candidate_set.candidate_set_id,
        "current_task_state_version": 4,
        "current_query_binding_refs": candidate_set.query_binding_refs,
        "trusted_now": NOW + timedelta(minutes=14, seconds=59),
    }
    arguments.update(overrides)
    return validate_current_candidate_selection(**arguments)


def test_candidate_set_is_fact_free_and_uses_exact_field_surface() -> None:
    candidate_set = _candidate_set()

    assert candidate_set.record_schema_version == (
        ORDER_CANDIDATE_SET_RECORD_SCHEMA_VERSION
    )
    assert tuple(OrderCandidateSetEntry.model_fields) == (
        "ordinal",
        "observation_candidate_ref",
        "candidate_source_version",
    )
    assert tuple(OrderCandidateSetRecord.model_fields) == (
        "candidate_set_id",
        "private_owner_scope_ref",
        "conversation_id",
        "task_id",
        "request_unit_id",
        "outcome",
        "base_task_state_version",
        "result_task_state_version",
        "selection_expected_task_state_version",
        "query_binding_refs",
        "source_tool_call_id",
        "search_observation_ref",
        "search_observation_record_schema_version",
        "search_observation_source_version",
        "ordered_candidates",
        "candidate_set_version",
        "created_at",
        "valid_until",
        "supersedes_candidate_set_ref",
    )
    forbidden = {
        "customer_id",
        "order_id",
        "order_number",
        "public_summary",
        "owner_scoped_order_ref",
        "raw_result_ref",
    }
    assert forbidden.isdisjoint(OrderCandidateSetRecord.model_fields)
    assert forbidden.isdisjoint(OrderCandidateSetEntry.model_fields)


def test_candidate_set_version_matches_independent_canonical_payload() -> None:
    candidate_set_id = UUID("00000000-0000-0000-0000-000000000001")
    conversation_id = UUID("00000000-0000-0000-0000-000000000002")
    task_id = UUID("00000000-0000-0000-0000-000000000003")
    request_unit_id = UUID("00000000-0000-0000-0000-000000000004")
    query_ref_high = UUID("00000000-0000-0000-0000-000000000099")
    query_ref_low = UUID("00000000-0000-0000-0000-000000000011")
    tool_call_id = UUID("00000000-0000-0000-0000-000000000005")
    observation_id = UUID("00000000-0000-0000-0000-000000000006")
    candidate_ref = UUID("00000000-0000-0000-0000-000000000007")
    entry = OrderCandidateSetEntry(
        ordinal=1,
        observation_candidate_ref=candidate_ref,
        candidate_source_version=CANDIDATE_VERSION_1,
    )
    created_at = datetime(2030, 1, 1, 0, 0, 0, 1, tzinfo=UTC)
    valid_until = created_at + timedelta(minutes=15)

    actual = compute_order_candidate_set_version(
        candidate_set_id=candidate_set_id,
        private_owner_scope_ref=OWNER,
        conversation_id=conversation_id,
        task_id=task_id,
        request_unit_id=request_unit_id,
        outcome=OrderCandidateSetOutcome.UNIQUE,
        base_task_state_version=8,
        result_task_state_version=10,
        selection_expected_task_state_version=None,
        query_binding_refs=(query_ref_high, query_ref_low),
        source_tool_call_id=tool_call_id,
        search_observation_ref=observation_id,
        search_observation_record_schema_version=(
            ORDER_SEARCH_OBSERVATION_RECORD_SCHEMA_VERSION
        ),
        search_observation_source_version=SNAPSHOT_VERSION,
        ordered_candidates=(entry,),
        created_at=created_at,
        valid_until=valid_until,
        supersedes_candidate_set_ref=None,
    )
    independent_payload = {
        "record_schema_version": "order_candidate_set_record.p0.v1",
        "candidate_set_id": str(candidate_set_id),
        "private_owner_scope_ref": OWNER,
        "conversation_id": str(conversation_id),
        "task_id": str(task_id),
        "request_unit_id": str(request_unit_id),
        "outcome": "UNIQUE",
        "base_task_state_version": 8,
        "result_task_state_version": 10,
        "selection_expected_task_state_version": None,
        "query_binding_refs": [str(query_ref_low), str(query_ref_high)],
        "source_tool_call_id": str(tool_call_id),
        "search_observation_ref": str(observation_id),
        "search_observation_record_schema_version": (
            "order_search_observation_record.p0.v1"
        ),
        "search_observation_source_version": SNAPSHOT_VERSION,
        "ordered_candidates": [
            {
                "ordinal": 1,
                "observation_candidate_ref": str(candidate_ref),
                "candidate_source_version": CANDIDATE_VERSION_1,
            }
        ],
        "created_at": "2030-01-01T00:00:00.000001Z",
        "valid_until": "2030-01-01T00:15:00.000001Z",
        "supersedes_candidate_set_ref": None,
    }
    canonical_bytes = json.dumps(
        independent_payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected = (
        "order-candidate-set.p0.v1:sha256:"
        + hashlib.sha256(canonical_bytes).hexdigest()
    )

    assert actual == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"result_task_state_version": 3},
        {"selection_expected_task_state_version": 5},
        {"valid_until": NOW + timedelta(minutes=14)},
        {"query_binding_refs": (UUID(int=1), UUID(int=1))},
        {"private_owner_scope_ref": " "},
    ],
)
def test_candidate_set_rejects_invalid_version_ttl_and_scope(
    overrides: dict[str, object],
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        _candidate_set(**overrides)


def test_candidate_set_rejects_hash_mismatch_and_non_contiguous_entries() -> None:
    values = _candidate_set_values()
    values["candidate_set_version"] = (
        "order-candidate-set.p0.v1:sha256:" + "0" * 64
    )
    with pytest.raises(ValidationError, match="canonical payload"):
        OrderCandidateSetRecord.model_validate(values)

    with pytest.raises((ValidationError, ValueError), match="contiguous"):
        _candidate_set(ordered_candidates=(_entry(1), _entry(3)))


def test_unique_and_multiple_candidate_set_shapes_are_closed() -> None:
    unique_entry = _entry(1)
    unique = _candidate_set(
        outcome=OrderCandidateSetOutcome.UNIQUE,
        ordered_candidates=(unique_entry,),
        selection_expected_task_state_version=None,
    )
    assert unique.selection_expected_task_state_version is None

    with pytest.raises((ValidationError, ValueError), match="UNIQUE"):
        _candidate_set(
            outcome=OrderCandidateSetOutcome.UNIQUE,
            ordered_candidates=(_entry(1), _entry(2)),
            selection_expected_task_state_version=None,
        )
    with pytest.raises((ValidationError, ValueError), match="MULTIPLE"):
        _candidate_set(
            outcome=OrderCandidateSetOutcome.MULTIPLE,
            ordered_candidates=(_entry(1),),
            selection_expected_task_state_version=4,
        )


def test_current_candidate_selection_accepts_only_before_ttl_boundary() -> None:
    candidate_set = _candidate_set()
    request = _selection_request(ordinal=2)

    selected = _validate_success(candidate_set, request)
    assert selected == candidate_set.ordered_candidates[1]

    with pytest.raises(ValueError, match="expired"):
        _validate_success(
            candidate_set,
            request,
            trusted_now=candidate_set.valid_until,
        )


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"current_candidate_sets": ()}, "exactly one"),
        ({"pending_candidate_set_ref": None}, "pending"),
        ({"pending_candidate_set_ref": UUID(int=99)}, "pending"),
        ({"trusted_owner_scope_ref": "owner-scope:other"}, "owner"),
        ({"conversation_id": UUID(int=99)}, "conversation"),
        ({"task_id": UUID(int=99)}, "task_id"),
        ({"request_unit_id": UUID(int=99)}, "request_unit_id"),
        ({"current_task_state_version": 5}, "Task version"),
        ({"current_query_binding_refs": (UUID(int=99),)}, "query binding"),
    ],
)
def test_current_candidate_selection_rejects_open_or_wrong_closure(
    override: dict[str, object],
    match: str,
) -> None:
    candidate_set = _candidate_set()
    with pytest.raises(ValueError, match=match):
        _validate_success(candidate_set, _selection_request(), **override)


def test_current_candidate_selection_rejects_multiple_superseded_and_bad_ordinal() -> None:
    candidate_set = _candidate_set()
    request = _selection_request()

    with pytest.raises(ValueError, match="exactly one"):
        _validate_success(
            candidate_set,
            request,
            current_candidate_sets=(candidate_set, candidate_set),
        )
    with pytest.raises(ValueError, match="superseded"):
        _validate_success(
            candidate_set,
            request,
            superseded_candidate_set_refs=(candidate_set.candidate_set_id,),
        )
    with pytest.raises(ValidationError):
        _selection_request(ordinal=0)
    with pytest.raises(ValidationError):
        _selection_request(ordinal=6)


def _selection_record(
    candidate_set: OrderCandidateSetRecord,
    request: OrderCandidateSelectionRequest,
    *,
    selected_index: int = 1,
) -> OrderCandidateSelectionRecord:
    selected = candidate_set.ordered_candidates[selected_index]
    return OrderCandidateSelectionRecord(
        selection_id=uuid4(),
        private_owner_scope_ref=candidate_set.private_owner_scope_ref,
        conversation_id=candidate_set.conversation_id,
        task_id=candidate_set.task_id,
        request_unit_id=candidate_set.request_unit_id,
        source_message_ref=request.source_message_ref,
        ordinal_input_binding_ref=request.ordinal_input_binding_ref,
        candidate_set_ref=candidate_set.candidate_set_id,
        candidate_set_version=candidate_set.candidate_set_version,
        search_observation_ref=candidate_set.search_observation_ref,
        search_observation_record_schema_version=(
            candidate_set.search_observation_record_schema_version
        ),
        observation_candidate_ref=selected.observation_candidate_ref,
        candidate_source_version=selected.candidate_source_version,
        owner_scoped_order_target_ref="owner-order:2",
        selected_target_ref="verified-target:2",
        base_task_state_version=4,
        result_task_state_version=5,
        selected_at=NOW + timedelta(minutes=1),
    )


def test_conflicting_source_message_selection_fails_closed() -> None:
    candidate_set = _candidate_set()
    request = _selection_request(ordinal=1)
    conflict = _selection_record(candidate_set, request, selected_index=1)

    with pytest.raises(ValueError, match="conflicting"):
        _validate_success(
            candidate_set,
            request,
            existing_selection_records=(conflict,),
        )


def test_selection_record_is_private_fact_free_and_version_monotonic() -> None:
    candidate_set = _candidate_set()
    selection = _selection_record(candidate_set, _selection_request())

    assert "ordinal" not in OrderCandidateSelectionRecord.model_fields
    assert "order_number" not in OrderCandidateSelectionRecord.model_fields
    assert "public_summary" not in OrderCandidateSelectionRecord.model_fields
    assert selection.result_task_state_version > selection.base_task_state_version

    payload = selection.model_dump()
    payload["result_task_state_version"] = selection.base_task_state_version
    with pytest.raises(ValidationError, match="greater"):
        OrderCandidateSelectionRecord.model_validate(payload)


def test_candidate_set_supersession_is_append_only_same_context() -> None:
    previous = _candidate_set()
    current = _candidate_set(
        base_task_state_version=previous.result_task_state_version,
        result_task_state_version=previous.result_task_state_version + 1,
        selection_expected_task_state_version=previous.result_task_state_version + 1,
        supersedes_candidate_set_ref=previous.candidate_set_id,
        private_owner_scope_ref=previous.private_owner_scope_ref,
        conversation_id=previous.conversation_id,
        task_id=previous.task_id,
        request_unit_id=previous.request_unit_id,
        created_at=previous.created_at + timedelta(minutes=1),
        valid_until=previous.valid_until + timedelta(minutes=1),
    )

    validate_candidate_set_supersession(current=current, previous=previous)

    wrong_owner = _candidate_set(
        base_task_state_version=4,
        result_task_state_version=5,
        selection_expected_task_state_version=5,
        supersedes_candidate_set_ref=previous.candidate_set_id,
        conversation_id=previous.conversation_id,
        task_id=previous.task_id,
        request_unit_id=previous.request_unit_id,
        created_at=previous.created_at + timedelta(minutes=1),
        valid_until=previous.valid_until + timedelta(minutes=1),
        private_owner_scope_ref="owner-scope:other",
    )
    with pytest.raises(ValueError, match="owner"):
        validate_candidate_set_supersession(
            current=wrong_owner,
            previous=previous,
        )
