---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R5RI
type: correction
depends_on: [02-18R19R5R]
files_modified:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - tests/integration/test_agent_run_service_v2_persistence.py
  - tests/integration/test_postgres_recovery.py
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
---

# 02-18R19R5RI｜W12 PostgreSQL exact Gate / AutoTarget reader

```yaml
task_id: 02-18R19R5RI
goal: 只让现有PostgreSQL Cycle 2 exact owner reader返回已持久化的GateDecisionV2，并把现有marker-backed OrderCandidateSelectionRecord重建为已生效的OrderCandidateAutoTargetRecord；将两类现有record family原样供应给Cycle2ExactRunEvidenceClosure，不改变物理格式、codec、migration、Port、Application、Eval或Composition。
repository: weijie567/mini-agent
remote: origin
planning_head_branch: codex/e2e01-cycle2-w12-r19r5ri-infrastructure-plan
head_branch: codex/e2e01-cycle2-w12-r19r5ri-infrastructure-evidence
base_branch: integration/e2e01-cycle2
product_base_sha: 665925873420ce6002b95414f0190f83a3ccc925
base_sha: 665925873420ce6002b95414f0190f83a3ccc925
base_tree: a8f0f1a1745fa437189c4ceb27f2b7f4639aa4a0
worktree_id: e2e01-cycle2-w12-r19r5ri-infrastructure-evidence
agent_role: infra-engineer
writer: cycle2-w12-postgres-exact-reader-owner
owned_files:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - tests/integration/test_agent_run_service_v2_persistence.py
  - tests/integration/test_postgres_recovery.py
forbidden_files:
  - all files outside owned_files
  - src/mini_agent/application/**
  - src/mini_agent/core/**
  - src/mini_agent/evaluation/**
  - src/mini_agent/infrastructure/persistence/models.py
  - src/mini_agent/infrastructure/persistence/database.py
  - alembic/**
  - evals/**
  - docs/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.3.4, 7.4, 7.5 and 11.3
  - existing GateDecisionV2 physical record/version and owner-scoped row decoder
  - existing marker-backed OrderCandidateSelectionRecord codec and _cycle2_auto_target_from_selection reconstruction
  - reviewed Cycle2ExactRunEvidenceClosure Gate/AutoTarget owner families from 02-18R19R5R
required_product_blobs:
  docs/implementation/e2e01-cycle2-implementation-spec.md: 7d62c6990cb4b742071262d2f0d9a52727763b0a
  src/mini_agent/application/records.py: 169c65749c4877e18fea5d3d5deae5edd761aee5
  src/mini_agent/infrastructure/persistence/postgres.py: fc62a8ba79357444784a8b38728ddad45f7abeb7
  tests/integration/test_agent_run_service_v2_persistence.py: ff9103b881a4d549f0b14f4fd55b5b96b042a86c
  tests/integration/test_postgres_recovery.py: 47c4f2cb4490381f5dd499ddd942a8046aed9bde
  src/mini_agent/evaluation/graders.py: f4ce1ae31ace18ba7712c40731ddcda4a97b30f4
  src/mini_agent/evaluation/harness.py: 1a3794a37cd9dc3c20ede72cfa729e306a63d65d
  evals/cases/e2e01-cycle2.v1.json: 6b77888471318510f3dcf1d16adebb2f64713d27
  evals/manifests/e2e01-cycle2.v1.json: f2fec57be006f84f67e147f1e2898d36aa07d476
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5R-PLAN.md: cb6b4129ad300b8d51ed5a0e617812610b059a1d
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
dependencies:
  - contract freeze anchor = 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  - reviewed R19R5R Application product = GitHub verified signed 665925873420ce6002b95414f0190f83a3ccc925
  - planning-control PR for this exact Plan must merge signed before product writes begin
  - product worktree remains pinned to the exact product_base_sha above; the later planning-only merge is base-only and must not change any owned product blob
confirmed_blocker:
  - exact named unique first-turn and W12 recovery PostgreSQL tests both fail with P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH after R19R5R because _cycle2_exact_run_evidence omits gate_decision_records and auto_target_records
  - current reader already reads every root/supporting ToolCall and already persists GateDecisionV2 under gate_decision_record.p0.v2
  - current reader already identifies marker-backed selections and calls _cycle2_auto_target_from_selection, but discards the reconstructed AutoTarget while removing the marker record from ordinal selections
  - baseline reproduction = 2 failed in 5.25s for the two exact named tests below
implementation_decisions:
  - while partitioning persisted selection rows, retain every exact reconstructed OrderCandidateAutoTargetRecord in a dedicated tuple and retain only true ordinal rows in candidate_selection_records
  - for every supplied root/supporting ToolCallRecordV2, owner-scope load exactly one GateDecisionV2 by its gate_decision_id through the existing _cycle2_row boundary and existing gate_decision_record.p0.v2 codec
  - missing Gate, wrong physical/source type, owner mismatch, duplicate/reused identity or malformed marker reconstruction fails through the existing bounded P0 persistence integrity boundary; no fallback to Trace or ToolCall fields
  - pass sorted exact gate_decision_records and auto_target_records to Cycle2ExactRunEvidenceClosure; the Application closure remains the final graph validator
  - preserve the existing ordinal-vs-marker partition and marker codec byte-for-byte; do not introduce a new record code, schema version, marker grammar or migration
  - the reader may load only records reachable from supplied ToolCalls/CandidateSets; it does not enumerate unrelated owner records or broaden disclosure
  - add positive assertions for real unique flow and W12 recovery root/supporting flow, plus physical tamper/missing-owner-record fail-closed checks at the reader boundary
contract_changes: NONE — consumes the already reviewed internal Application fields and existing physical codecs; no active owner, schema/version, record family, Port, persistence format or lifecycle change.
security_impact: POSITIVE — prevents the physical reader from dropping actual Gate/target authority and forbids inference from Trace, ToolCall target value or public candidate data.
eval_impact: PREREQUISITE_ONLY — no Eval file, Case, manifest, grader or metric change; makes the existing exact reader usable by the separately refrozen Eval consumer packet.
known_successor_blocker:
  - after this merge, the Eval-only consumer must be re-run/refrozen against exact Gate/AutoTarget families and the known Composition test
  - Composition Root, final 02-18 full suite, status writeback and Graphify remain NOT_RUN / NOT_COMPLETE
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: W12_R19R5RI_POSTGRES_EXACT_READER_EXACT_HEAD
  targeted_risk_checks: exact owner-scoped Gate lookup, root/supporting ToolCall completeness, marker-to-AutoTarget reconstruction, ordinal partition, missing/corrupt record fail-closed, no foreign-owner disclosure
  baseline_reproduction: uv run pytest -q tests/integration/test_agent_run_service_v2_persistence.py::test_cycle2_unique_first_turn_persists_real_normal_graph_and_exact_evidence tests/integration/test_postgres_recovery.py::test_w12_recovery_setup_reads_exact_root_and_supporting_closure
  focused_tests: uv run pytest -q tests/integration/test_agent_run_service_v2_persistence.py tests/integration/test_postgres_recovery.py
  neighbor_tests: uv run pytest -q tests/integration/test_postgres_v3_request_understanding_writes.py tests/integration/test_e2e01_cycle2_execution_seam.py
  full_suite_gate: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  phase_end_deep_audit: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  graphify_gate: FINAL_REFROZEN_02_18_ONLY
required_checks:
  - exact three-file allowlist, signed-base direct ancestry, required blob pins and git diff --check
  - baseline two exact failures become PASS without changing their product scenario, storage schema or owner identity
  - every supplied ToolCall has one exact persisted GateDecisionV2; missing/wrong-owner/wrong-type/reused Gate fails closed through bounded integrity error
  - UNIQUE marker record reconstructs exactly one AutoTarget and never appears as ordinal Selection; real ordinal row remains ordinal and never becomes AutoTarget
  - root and supporting source ToolCalls both load their own Gate records; foreign owner records remain absent and secret/foreign fixture markers do not enter serialized evidence
  - no changes to migration chain, codec catalog/version, marker grammar, P0RecordCode, Application/Core/Eval/Case/manifest/Composition
  - focused and neighbor tests PASS; local independent review and remote exact-head review PASS with zero P1
expected_results:
  - product changes exactly the three owned files
  - PostgreSQL owner reader returns complete exact Gate/AutoTarget evidence for normal unique and W12 recovery graphs
  - Eval and Composition remain unchanged and explicitly NOT_RUN / NOT_COMPLETE in this Packet
done_when:
  - exact product head satisfies all required checks and merges reviewed/signed as B_C2_W12_R19R5RI_POSTGRES_EXACT_READER
  - Integrator hands the exact signed successor to a new Eval-only planning-control Packet; Code Freeze is not yet claimed
rollback:
  - before successor work, revert the exact Infrastructure/test commit atomically
  - after descendants exist, invalidate and revert descendants first; no migration or data rewrite is required
handoff_format:
  - exact branch/base/head/tree, three changed files and resulting blobs
  - commands/results/NOT_RUN, Gate/AutoTarget/ordinal/tamper matrix, contract/security/Eval impact, known successor blocker and rollback
output_barrier: B_C2_W12_R19R5RI_POSTGRES_EXACT_READER
handoff_to: tech-lead
```
