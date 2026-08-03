---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R5RIT
type: test_conformance
depends_on: [02-18R19R5RIRV]
files_modified:
  - tests/integration/test_e2e01_cycle2_execution_seam.py
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
---

# 02-18R19R5RIT｜W12 current-query test conformance

```yaml
task_id: 02-18R19R5RIT
goal: 关闭R19R5RIRV唯一mandatory HIGH；仅把一个遗留integration测试从接受historical CandidateSet作为current authority的旧期待，改为验证已冻结Application current-query合同下PostgreSQL exact reader以LINK_PROJECTION_MISMATCH fail closed；不修改任何产品代码、合同、fixture、Case、grader或Composition实现。
repository: weijie567/mini-agent
remote: origin
planning_head_branch: codex/e2e01-cycle2-w12-r19r5rit-current-query-test-plan
head_branch: codex/e2e01-cycle2-w12-r19r5rit-current-query-test-conformance
base_branch: integration/e2e01-cycle2
product_base_sha: b4fa0c4a6657e4abb209d8eaf7a37fd5bf1bc5e6
base_sha: b4fa0c4a6657e4abb209d8eaf7a37fd5bf1bc5e6
base_tree: 91be9f4164df7257a26c5ab227ca17ce326e0fb2
worktree_id: e2e01-cycle2-w12-r19r5rit-current-query-test-conformance
agent_role: tech-lead
writer: cycle2-w12-composition-integration-test-owner
owned_files:
  - tests/integration/test_e2e01_cycle2_execution_seam.py
forbidden_files:
  - all files outside owned_files
  - src/**
  - alembic/**
  - evals/**
  - docs/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - GitHub verified signed R19R5R Application current-query contract in src/mini_agent/application/records.py
  - GitHub verified signed R19R5RIR Infrastructure exact Gate/AutoTarget reader at b4fa0c4a6657e4abb209d8eaf7a37fd5bf1bc5e6
  - signed R19R5RIRV adjudication that requires this exact immediate successor
required_product_blobs:
  tests/integration/test_e2e01_cycle2_execution_seam.py: ef31ffa6fc69c4950b0ff615eaddcc1bb81dc96e
  src/mini_agent/application/records.py: 169c65749c4877e18fea5d3d5deae5edd761aee5
  src/mini_agent/infrastructure/persistence/postgres.py: 11b28b592e6b2b83b16e19a17b385ba84a5e38ed
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5RIRV-PLAN.md: a3a36bdfd401ee3b3de10eba6b4d1f08b15a02b8
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
dependencies:
  - contract freeze anchor = 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  - reviewed R19R5RIR Infrastructure product = GitHub verified signed b4fa0c4a6657e4abb209d8eaf7a37fd5bf1bc5e6
  - reviewed R19R5RIRV planning control = GitHub verified signed 5498e90dc34a46263ebfb7d6793d8c0017bb810b
confirmed_blocker:
  - exact neighbor command produced 37 PASS and one failure at test_exact_reader_loads_referenced_binding_absent_from_current_unit
  - the helper replaces current RequestUnit product binding while retaining the historical CandidateSet query and source ToolCall, creating an internally stale evidence graph
  - signed Application requires the leaf CandidateSet query binding to equal the current RequestUnit product binding and correctly rejects this graph
  - reader normalization, CandidateSet rewriting or weakening Application validation is forbidden
implementation_decisions:
  - rename only the affected test to state that a historical CandidateSet query is rejected after current binding replacement
  - retain the existing setup and mutation helper so the physical stale graph is reproduced unchanged
  - replace the obsolete successful-reread and subsequent unrelated codec corruption assertions with a direct adapter assertion for P0PersistenceIntegrityCategory.LINK_PROJECTION_MISMATCH
  - add only the required P0PersistenceIntegrityCategory import in the same file
  - do not change shared helpers, fixtures, production code, error mapping, test bootstrap or any other test
contract_changes: NONE — test is conformed to the already signed current-query contract.
security_impact: POSITIVE — regression evidence now enforces that historical query authority cannot masquerade as current authority.
eval_impact: NONE — integration test expectation only; no Eval Case, grader, metric, manifest or lifecycle change.
known_successor_blocker:
  - Eval-only consumer, Composition, final 02-18 suite, status writeback and Graphify remain NOT_RUN / NOT_COMPLETE
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: W12_R19R5RIT_SINGLE_TEST_CURRENT_QUERY_CONFORMANCE_EXACT_HEAD
  targeted_risk_checks: exact one-file diff, unchanged stale-graph setup, direct bounded category assertion, no broad exception or production change
  focused_tests: uv run pytest -q tests/integration/test_e2e01_cycle2_execution_seam.py::test_exact_reader_rejects_historical_candidate_query_after_current_binding_replaced
  neighbor_tests: uv run pytest -q tests/integration/test_postgres_v3_request_understanding_writes.py tests/integration/test_e2e01_cycle2_execution_seam.py
  full_suite_gate: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  phase_end_deep_audit: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  graphify_gate: FINAL_REFROZEN_02_18_ONLY
required_checks:
  - exact single-file allowlist, signed-base direct ancestry, required blobs and git diff --check
  - affected test retains the same real PostgreSQL setup and stale current/historical binding mutation
  - direct adapter raises exact LINK_PROJECTION_MISMATCH; no generic Exception assertion
  - exact neighbor command changes from 37 PASS plus one named failure to all 38 PASS
  - no src/fixture/helper/Case/grader/manifest/Composition implementation change
  - local independent review and remote exact-head review PASS with zero P1
expected_results:
  - the carried mandatory HIGH is closed with one test-only diff
  - the frozen current-query invariant remains fail closed and has reproducible regression evidence
  - only after signed merge may the Integrator freeze the Eval-only consumer Packet
done_when:
  - exact single-file product head passes focused and neighbor tests and merges reviewed/signed as B_C2_W12_R19R5RIT_CURRENT_QUERY_TEST_CONFORMANCE
  - Integrator hands the exact signed successor to a new Eval-only planning-control Packet; Code Freeze is not yet claimed
rollback:
  - revert the single-file test-only squash; no product code, migration or data rollback applies
handoff_format:
  - exact branch/base/head/tree/blob, one-file diff proof, focused/neighbor results, review verdict, signed merge SHA, successor blocker and rollback
output_barrier: B_C2_W12_R19R5RIT_CURRENT_QUERY_TEST_CONFORMANCE
handoff_to: tech-lead
```
