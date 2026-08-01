"""Closed Cycle 2 result mapping layered over stable Phase 1 references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mini_agent.core.trace import AgentOutcome, StopReasonV2


PHASE1_RESULT_MAPPER_CONTRACT = "e2e01-thin-slice.result-mapper.p0.v1"


class ImportedMapperReference(StrEnum):
    """Identity-only imports; their conditions and results stay Phase 1-owned."""

    ORDER_SUCCESS = "P1-RM-ORDER-SUCCESS"
    GATE_REJECTED = "P1-RM-GATE-REJECTED"
    ORDER_SERVICE_UNAVAILABLE = "P1-RM-ORDER-SERVICE-UNAVAILABLE"
    PROCESS_RESTART = "P1-RM-PROCESS-RESTART"


class Cycle2MapperSignal(StrEnum):
    """Mutually-exclusive, already-validated Runtime-private dispositions."""

    SEARCH_BINDING_CLARIFICATION = "SEARCH_BINDING_CLARIFICATION"
    SEARCH_MULTIPLE = "SEARCH_MULTIPLE"
    CANDIDATE_REFRESH_REQUIRED = "CANDIDATE_REFRESH_REQUIRED"
    CLAIM_TARGET_CLARIFICATION = "CLAIM_TARGET_CLARIFICATION"
    SEARCH_NO_MATCH = "SEARCH_NO_MATCH"
    PRIVATE_RESOURCE_NOT_FOUND = "PRIVATE_RESOURCE_NOT_FOUND"
    INTERNAL_RETRY_AUTHORIZED = "INTERNAL_RETRY_AUTHORIZED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    RUN_BUDGET_EXHAUSTED = "RUN_BUDGET_EXHAUSTED"
    ORDER_SEARCH_UNAVAILABLE = "ORDER_SEARCH_UNAVAILABLE"
    SHIPMENT_SERVICE_UNAVAILABLE = "SHIPMENT_SERVICE_UNAVAILABLE"
    CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY = (
        "CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY"
    )
    SHIPMENT_RELATION_CARDINALITY = "SHIPMENT_RELATION_CARDINALITY"
    SHIPMENT_BORN_STALE = "SHIPMENT_BORN_STALE"
    NO_SHIPMENT = "NO_SHIPMENT"
    SHIPMENT_FACTS_INSUFFICIENT = "SHIPMENT_FACTS_INSUFFICIENT"
    SHIPMENT_ASSESSMENT_READY = "SHIPMENT_ASSESSMENT_READY"
    ORDINARY_OBSOLETE_RUN = "ORDINARY_OBSOLETE_RUN"
    AUTHORITATIVE_EXECUTION_INTERRUPTED = (
        "AUTHORITATIVE_EXECUTION_INTERRUPTED"
    )
    RETRY_RECOVERY_OBSOLETE_RUN = "RETRY_RECOVERY_OBSOLETE_RUN"
    CONTRADICTORY_INTERRUPTION_EVIDENCE = (
        "CONTRADICTORY_INTERRUPTION_EVIDENCE"
    )


class MapperDisposition(StrEnum):
    EMIT = "EMIT"
    INTERNAL_RETRY = "INTERNAL_RETRY"
    SUPPRESS_OBSOLETE_RUN = "SUPPRESS_OBSOLETE_RUN"
    NO_STATE_MUTATION = "NO_STATE_MUTATION"


class ResponsePolicy(StrEnum):
    NONE = "NONE"
    CLARIFICATION_FIXED = "CLARIFICATION_FIXED"
    CANDIDATE_SUMMARY_DETERMINISTIC = "CANDIDATE_SUMMARY_DETERMINISTIC"
    CANDIDATE_REFRESH_FIXED = "CANDIDATE_REFRESH_FIXED"
    CLAIM_TARGET_CLARIFICATION_FIXED = "CLAIM_TARGET_CLARIFICATION_FIXED"
    SAFE_NOT_FOUND_FIXED = "SAFE_NOT_FOUND_FIXED"
    DEPENDENCY_BLOCKED_FIXED = "DEPENDENCY_BLOCKED_FIXED"
    INTEGRITY_BLOCKED_FIXED = "INTEGRITY_BLOCKED_FIXED"
    NO_SHIPMENT_NEED_HUMAN_FIXED = "NO_SHIPMENT_NEED_HUMAN_FIXED"
    FACTS_INSUFFICIENT_NEED_HUMAN_FIXED = (
        "FACTS_INSUFFICIENT_NEED_HUMAN_FIXED"
    )
    SHIPMENT_ASSESSMENT_DETERMINISTIC = (
        "SHIPMENT_ASSESSMENT_DETERMINISTIC"
    )


@dataclass(frozen=True, slots=True)
class Cycle2ResultMapping:
    row_id: str
    disposition: MapperDisposition
    stop_reason: StopReasonV2 | None
    outcome: AgentOutcome | None
    response_policy: ResponsePolicy


_DELTA_ROWS: dict[Cycle2MapperSignal, Cycle2ResultMapping] = {
    Cycle2MapperSignal.SEARCH_BINDING_CLARIFICATION: Cycle2ResultMapping(
        "RM-01", MapperDisposition.EMIT, StopReasonV2.CLARIFICATION_REQUIRED,
        AgentOutcome.ASK_USER, ResponsePolicy.CLARIFICATION_FIXED,
    ),
    Cycle2MapperSignal.SEARCH_MULTIPLE: Cycle2ResultMapping(
        "RM-02", MapperDisposition.EMIT,
        StopReasonV2.CANDIDATE_CLARIFICATION_REQUIRED, AgentOutcome.ASK_USER,
        ResponsePolicy.CANDIDATE_SUMMARY_DETERMINISTIC,
    ),
    Cycle2MapperSignal.CANDIDATE_REFRESH_REQUIRED: Cycle2ResultMapping(
        "RM-03", MapperDisposition.EMIT,
        StopReasonV2.CANDIDATE_REFRESH_REQUIRED, AgentOutcome.ASK_USER,
        ResponsePolicy.CANDIDATE_REFRESH_FIXED,
    ),
    Cycle2MapperSignal.CLAIM_TARGET_CLARIFICATION: Cycle2ResultMapping(
        "RM-04", MapperDisposition.EMIT,
        StopReasonV2.CLAIM_TARGET_CLARIFICATION_REQUIRED,
        AgentOutcome.ASK_USER, ResponsePolicy.CLAIM_TARGET_CLARIFICATION_FIXED,
    ),
    Cycle2MapperSignal.SEARCH_NO_MATCH: Cycle2ResultMapping(
        "RM-05", MapperDisposition.EMIT,
        StopReasonV2.NOT_FOUND_OR_NOT_ACCESSIBLE,
        AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        ResponsePolicy.SAFE_NOT_FOUND_FIXED,
    ),
    Cycle2MapperSignal.PRIVATE_RESOURCE_NOT_FOUND: Cycle2ResultMapping(
        "RM-06", MapperDisposition.EMIT,
        StopReasonV2.NOT_FOUND_OR_NOT_ACCESSIBLE,
        AgentOutcome.NOT_FOUND_OR_NOT_ACCESSIBLE,
        ResponsePolicy.SAFE_NOT_FOUND_FIXED,
    ),
    Cycle2MapperSignal.INTERNAL_RETRY_AUTHORIZED: Cycle2ResultMapping(
        "RM-07", MapperDisposition.INTERNAL_RETRY, None, None,
        ResponsePolicy.NONE,
    ),
    Cycle2MapperSignal.RETRY_EXHAUSTED: Cycle2ResultMapping(
        "RM-08", MapperDisposition.EMIT,
        StopReasonV2.DEPENDENCY_RETRY_EXHAUSTED, AgentOutcome.BLOCKED,
        ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.RUN_BUDGET_EXHAUSTED: Cycle2ResultMapping(
        "RM-09", MapperDisposition.EMIT,
        StopReasonV2.DEPENDENCY_EXECUTION_INTERRUPTED, AgentOutcome.BLOCKED,
        ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.ORDER_SEARCH_UNAVAILABLE: Cycle2ResultMapping(
        "RM-10", MapperDisposition.EMIT,
        StopReasonV2.ORDER_SEARCH_UNAVAILABLE, AgentOutcome.BLOCKED,
        ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.SHIPMENT_SERVICE_UNAVAILABLE: Cycle2ResultMapping(
        "RM-11", MapperDisposition.EMIT,
        StopReasonV2.SHIPMENT_SERVICE_UNAVAILABLE, AgentOutcome.BLOCKED,
        ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.CYCLE2_PROTOCOL_OR_SOURCE_INTEGRITY: Cycle2ResultMapping(
        "RM-12", MapperDisposition.EMIT,
        StopReasonV2.INTEGRITY_CHECK_FAILED, AgentOutcome.BLOCKED,
        ResponsePolicy.INTEGRITY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.SHIPMENT_RELATION_CARDINALITY: Cycle2ResultMapping(
        "RM-13", MapperDisposition.EMIT,
        StopReasonV2.INTEGRITY_CHECK_FAILED, AgentOutcome.BLOCKED,
        ResponsePolicy.INTEGRITY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.SHIPMENT_BORN_STALE: Cycle2ResultMapping(
        "RM-14", MapperDisposition.EMIT,
        StopReasonV2.SHIPMENT_SNAPSHOT_STALE, AgentOutcome.BLOCKED,
        ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.NO_SHIPMENT: Cycle2ResultMapping(
        "RM-15", MapperDisposition.EMIT,
        StopReasonV2.SHIPMENT_DATA_UNAVAILABLE, AgentOutcome.NEED_HUMAN,
        ResponsePolicy.NO_SHIPMENT_NEED_HUMAN_FIXED,
    ),
    Cycle2MapperSignal.SHIPMENT_FACTS_INSUFFICIENT: Cycle2ResultMapping(
        "RM-16", MapperDisposition.EMIT,
        StopReasonV2.SHIPMENT_DATA_UNAVAILABLE, AgentOutcome.NEED_HUMAN,
        ResponsePolicy.FACTS_INSUFFICIENT_NEED_HUMAN_FIXED,
    ),
    Cycle2MapperSignal.SHIPMENT_ASSESSMENT_READY: Cycle2ResultMapping(
        "RM-18", MapperDisposition.EMIT, StopReasonV2.GOAL_COMPLETED,
        AgentOutcome.COMPLETED,
        ResponsePolicy.SHIPMENT_ASSESSMENT_DETERMINISTIC,
    ),
    Cycle2MapperSignal.ORDINARY_OBSOLETE_RUN: Cycle2ResultMapping(
        "RM-I01", MapperDisposition.SUPPRESS_OBSOLETE_RUN,
        StopReasonV2.STATE_OR_BINDING_INVALIDATED, None, ResponsePolicy.NONE,
    ),
    Cycle2MapperSignal.AUTHORITATIVE_EXECUTION_INTERRUPTED: Cycle2ResultMapping(
        "RM-I02", MapperDisposition.EMIT,
        StopReasonV2.DEPENDENCY_EXECUTION_INTERRUPTED, AgentOutcome.BLOCKED,
        ResponsePolicy.DEPENDENCY_BLOCKED_FIXED,
    ),
    Cycle2MapperSignal.RETRY_RECOVERY_OBSOLETE_RUN: Cycle2ResultMapping(
        "RM-I04", MapperDisposition.SUPPRESS_OBSOLETE_RUN,
        StopReasonV2.STATE_OR_BINDING_INVALIDATED, None, ResponsePolicy.NONE,
    ),
    Cycle2MapperSignal.CONTRADICTORY_INTERRUPTION_EVIDENCE: Cycle2ResultMapping(
        "RM-I05", MapperDisposition.NO_STATE_MUTATION, None, None,
        ResponsePolicy.NONE,
    ),
}


class RunResultMapper:
    """Set-based effective mapper with a closed, inspectable Cycle 2 delta."""

    imported_contract = PHASE1_RESULT_MAPPER_CONTRACT
    imported_references = tuple(ImportedMapperReference)
    delta_signals = tuple(Cycle2MapperSignal)

    def __init__(self) -> None:
        if set(_DELTA_ROWS) != set(Cycle2MapperSignal):
            raise RuntimeError("Cycle 2 mapper delta is incomplete")
        row_ids = tuple(row.row_id for row in _DELTA_ROWS.values())
        if len(row_ids) != len(set(row_ids)):
            raise RuntimeError("Cycle 2 mapper row identities overlap")
        forbidden = {"RM-17", "RM-I03"}
        if forbidden.intersection(row_ids):
            raise RuntimeError("forbidden mapper identity present")
        if {ref.value for ref in ImportedMapperReference}.intersection(row_ids):
            raise RuntimeError("imported and delta mapper identities overlap")

    def import_reference(
        self,
        reference: ImportedMapperReference,
    ) -> ImportedMapperReference:
        """Return a stable reference without restating its source semantics."""

        if type(reference) is not ImportedMapperReference:
            raise ValueError("canonical imported mapper reference required")
        return reference

    def map_cycle2(self, signal: Cycle2MapperSignal) -> Cycle2ResultMapping:
        """Map one exact discriminator; unknown values never fall through."""

        if type(signal) is not Cycle2MapperSignal:
            raise ValueError("canonical Cycle 2 mapper signal required")
        return _DELTA_ROWS[signal]

    @property
    def delta_rows(self) -> tuple[Cycle2ResultMapping, ...]:
        return tuple(_DELTA_ROWS[signal] for signal in Cycle2MapperSignal)
