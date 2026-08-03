---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R5RIR
type: correction
depends_on: [02-18R19R5RI]
files_modified:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - src/mini_agent/infrastructure/cycle2_fixture_seed.py
  - tests/integration/test_agent_run_service_v2_persistence.py
  - tests/integration/test_postgres_recovery.py
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
---

# 02-18R19R5RIR｜W12 PostgreSQL reader fixture correction

```yaml
task_id: 02-18R19R5RIR
goal: 执行已冻结的R19R5RI PostgreSQL exact Gate/AutoTarget reader修复，并仅补正同一Infrastructure owner下W12 fixture中三个现有ToolCallRecordV2遗漏的provider_tool_call_id，使其精确复制同图GateDecisionV2；不改变fixture场景、ID、时间、状态、结果、codec、schema、migration、Application、Eval或Composition。
repository: weijie567/mini-agent
remote: origin
planning_head_branch: codex/e2e01-cycle2-w12-r19r5rir-infrastructure-plan
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
  - src/mini_agent/infrastructure/cycle2_fixture_seed.py
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
  - all R19R5RI canonical inputs and implementation decisions remain unchanged
  - existing GateDecisionV2 and ToolCallRecordV2 exact common-field contract
required_product_blobs:
  docs/implementation/e2e01-cycle2-implementation-spec.md: 7d62c6990cb4b742071262d2f0d9a52727763b0a
  src/mini_agent/application/records.py: 169c65749c4877e18fea5d3d5deae5edd761aee5
  src/mini_agent/infrastructure/persistence/postgres.py: fc62a8ba79357444784a8b38728ddad45f7abeb7
  src/mini_agent/infrastructure/cycle2_fixture_seed.py: a6e3f0e487f8dbf84dc9548cf6052f1b975bb73c
  tests/integration/test_agent_run_service_v2_persistence.py: ff9103b881a4d549f0b14f4fd55b5b96b042a86c
  tests/integration/test_postgres_recovery.py: 47c4f2cb4490381f5dd499ddd942a8046aed9bde
  src/mini_agent/evaluation/graders.py: f4ce1ae31ace18ba7712c40731ddcda4a97b30f4
  src/mini_agent/evaluation/harness.py: 1a3794a37cd9dc3c20ede72cfa729e306a63d65d
  evals/cases/e2e01-cycle2.v1.json: 6b77888471318510f3dcf1d16adebb2f64713d27
  evals/manifests/e2e01-cycle2.v1.json: f2fec57be006f84f67e147f1e2898d36aa07d476
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5R-PLAN.md: cb6b4129ad300b8d51ed5a0e617812610b059a1d
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5RI-PLAN.md: 58b2b8c4a766a53656fa66420fb7b73f96dad713
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
dependencies:
  - contract freeze anchor = 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  - reviewed R19R5R Application product = GitHub verified signed 665925873420ce6002b95414f0190f83a3ccc925
  - reviewed R19R5RI planning control = GitHub verified signed 9a546d0f9c05c3343c87140f3d0c52be50556910
  - this correction Plan must merge signed before cycle2_fixture_seed.py is modified
supersedes:
  - 02-18R19R5RI as the executable allowlist only; all reader decisions, tests, gates and successor boundaries remain in force
confirmed_blocker:
  - after retaining real persisted Gate records, the normal unique database path passes but W12 recovery fixture still fails exact Application validation
  - persisted fixture Gates carry provider_tool_call_id values w12-search, w12-stale-get-shipment and w12-recovery-get-shipment while their exact same-graph ToolCallRecordV2 records carry null
  - reproducer shows every other Gate/Tool common field exact-equal; provider_tool_call_id is the sole mismatch
  - reader-side invention, normalization or omission would violate the frozen exact Gate/Tool contract and is forbidden
implementation_decisions:
  - retain every R19R5RI reader decision unchanged
  - set provider_tool_call_id on exactly the three existing fixture ToolCallRecordV2 constructors to the already persisted same-graph Gate value
  - do not change any deterministic UUID, record role, fixture reference, message, Binding, CandidateSet, Observation, target, state version, timestamp, attempt, result or lifecycle field
  - add no new fixture, schema, marker, record family, codec branch or fallback
  - the exact reader remains fail closed on a real persisted Gate/Tool provider-call mismatch; the fixture is corrected because it is the invalid producer
contract_changes: NONE — fixture conformance fix only; exact Gate/Tool semantics remain frozen.
security_impact: POSITIVE — preserves persisted provider-call identity instead of laundering a contradiction in the reader.
eval_impact: PREREQUISITE_ONLY — no Case/grader/metric change; existing W12 recovery fixture becomes valid evidence for the separately refrozen Eval consumer.
known_successor_blocker:
  - Eval-only consumer, Composition, final 02-18 suite, status writeback and Graphify remain NOT_RUN / NOT_COMPLETE
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: W12_R19R5RIR_POSTGRES_READER_FIXTURE_EXACT_HEAD
  targeted_risk_checks: exact three provider ids only, Gate/Tool common fields, owner scope, marker partition, missing Gate fail-closed, no fixture scenario drift
  baseline_reproduction: uv run pytest -q tests/integration/test_agent_run_service_v2_persistence.py::test_cycle2_unique_first_turn_persists_real_normal_graph_and_exact_evidence tests/integration/test_postgres_recovery.py::test_w12_recovery_setup_reads_exact_root_and_supporting_closure
  focused_tests: uv run pytest -q tests/integration/test_agent_run_service_v2_persistence.py tests/integration/test_postgres_recovery.py tests/integration/test_cycle2_fixture_seed.py
  neighbor_tests: uv run pytest -q tests/integration/test_postgres_v3_request_understanding_writes.py tests/integration/test_e2e01_cycle2_execution_seam.py
  full_suite_gate: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  phase_end_deep_audit: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  graphify_gate: FINAL_REFROZEN_02_18_ONLY
required_checks:
  - exact four-file allowlist, signed-base direct ancestry, required blob pins and git diff --check
  - source diff in cycle2_fixture_seed.py changes only the three ToolCall provider_tool_call_id fields to exact existing Gate values
  - baseline two named paths PASS; recovery evidence supplies exact root/supporting Gates and one reconstructed AutoTarget
  - physical missing-Gate tamper still fails with bounded LINK_PROJECTION_MISMATCH
  - existing fixture-seed suite, focused and neighbor tests PASS
  - no codec/migration/P0RecordCode/Application/Core/Eval/Case/manifest/Composition change
  - local independent review and remote exact-head review PASS with zero P1
expected_results:
  - product changes exactly the four owned files
  - normal unique and W12 recovery PostgreSQL owner readers return complete exact Gate/AutoTarget evidence
  - Eval and Composition remain unchanged and explicitly NOT_RUN / NOT_COMPLETE
done_when:
  - exact product head satisfies all checks and merges reviewed/signed as B_C2_W12_R19R5RIR_POSTGRES_READER_FIXTURE
  - Integrator hands exact signed successor to a new Eval-only planning-control Packet; Code Freeze is not yet claimed
rollback:
  - before successor work, revert the exact four-file Infrastructure/test commit atomically
  - after descendants exist, invalidate and revert descendants first; no migration/data rewrite required
handoff_format:
  - exact branch/base/head/tree, four changed files/blobs, commands/results/NOT_RUN, three-field fixture diff proof, Gate/AutoTarget/tamper matrix, successor blocker and rollback
output_barrier: B_C2_W12_R19R5RIR_POSTGRES_READER_FIXTURE
handoff_to: tech-lead
```
