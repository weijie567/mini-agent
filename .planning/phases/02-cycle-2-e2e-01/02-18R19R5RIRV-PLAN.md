---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R5RIRV
type: verification_correction
depends_on: [02-18R19R5RIR]
files_modified:
  - src/mini_agent/infrastructure/persistence/postgres.py
  - src/mini_agent/infrastructure/cycle2_fixture_seed.py
  - tests/integration/test_agent_run_service_v2_persistence.py
  - tests/integration/test_postgres_recovery.py
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
---

# 02-18R19R5RIRV｜W12 Infrastructure verification correction

```yaml
task_id: 02-18R19R5RIRV
goal: 冻结R19R5RIR四文件Infrastructure候选的真实验证结果；仅把一个由已签名Application current-query合同与旧neighbor测试期待冲突造成的可复现失败，裁决为必须由紧随其后的单文件test-conformance Packet关闭的W12 blocker；不得在reader中归一化历史CandidateSet，不得扩大Infrastructure产品范围。
repository: weijie567/mini-agent
remote: origin
planning_head_branch: codex/e2e01-cycle2-w12-r19r5rirv-verification-plan
head_branch: codex/e2e01-cycle2-w12-r19r5ri-infrastructure-evidence
base_branch: integration/e2e01-cycle2
product_base_sha: 665925873420ce6002b95414f0190f83a3ccc925
base_sha: 665925873420ce6002b95414f0190f83a3ccc925
base_tree: a8f0f1a1745fa437189c4ceb27f2b7f4639aa4a0
exact_product_candidate_sha: 2857341ff74f1b558c0962caec76f2f68e657c82
exact_product_candidate_tree: 332ba0bda792b7a8e8100c4b3a3af950581d9109
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
  - tests/integration/test_e2e01_cycle2_execution_seam.py
  - src/mini_agent/application/**
  - src/mini_agent/core/**
  - src/mini_agent/evaluation/**
  - alembic/**
  - evals/**
  - docs/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - GitHub verified signed R19R5R Application contract at 665925873420ce6002b95414f0190f83a3ccc925
  - Cycle2ExactRunEvidenceClosure current CandidateSet query, Gate/ToolCall and AutoTarget validators in src/mini_agent/application/records.py blob 169c65749c4877e18fea5d3d5deae5edd761aee5
  - R19R5RIR exact reader/fixture decisions remain unchanged
required_product_blobs:
  src/mini_agent/application/records.py: 169c65749c4877e18fea5d3d5deae5edd761aee5
  src/mini_agent/infrastructure/persistence/postgres.py: 11b28b592e6b2b83b16e19a17b385ba84a5e38ed
  src/mini_agent/infrastructure/cycle2_fixture_seed.py: a3895d739b7656c089034d474f39d6250cbd03cf
  tests/integration/test_agent_run_service_v2_persistence.py: 32f65cf4440783de5cb0232ff2a163e22599b5d0
  tests/integration/test_postgres_recovery.py: a2417ad9b7bbf2ee10bbac1e4744906943718933
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5RIR-PLAN.md: f757f194d0b44a75b402c646c82a66b47693ae66
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
dependencies:
  - contract freeze anchor = 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  - reviewed R19R5R Application product = GitHub verified signed 665925873420ce6002b95414f0190f83a3ccc925
  - reviewed R19R5RIR planning control = GitHub verified signed 4e0196948da5d92784f4eb6c864cf0755835a91b
  - exact Infrastructure candidate parent = 665925873420ce6002b95414f0190f83a3ccc925
supersedes:
  - 02-18R19R5RIR verification outcome only; its four-file allowlist, implementation decisions, contract freeze and successor boundaries remain in force
confirmed_results:
  - baseline two named blocker paths = 2 passed in 2.97s
  - focused Infrastructure/fixture/recovery suite = 40 passed in 17.01s
  - neighbor suite = 37 passed / 1 failed in 36.32s
  - sole failure = tests/integration/test_e2e01_cycle2_execution_seam.py::test_exact_reader_loads_referenced_binding_absent_from_current_unit
confirmed_neighbor_conflict:
  - the old test replaces current RequestUnit.input_binding_refs with a new binding while retaining the historical CandidateSet query/source ToolCall as authoritative, then expects exact evidence to remain valid
  - the frozen Application validator rejects that graph with exact cause Cycle 2 exact evidence CandidateSet current query mismatch
  - returning the historical CandidateSet as current, rewriting its query ref, omitting Gate/AutoTarget, or otherwise laundering the contradiction in the PostgreSQL reader is forbidden
  - the failing file is outside the Infrastructure owner and cannot be edited in this Packet
implementation_decisions:
  - do not change exact product candidate 2857341ff74f1b558c0962caec76f2f68e657c82
  - permit Infrastructure review and merge only if independent exact review confirms the four-file candidate, the 2/40 pass evidence, and no neighbor failure other than the one frozen above
  - treat the sole neighbor failure as an explicit HIGH successor blocker, not as PASS, flaky behavior, or non-blocking optimization
  - immediately after the signed Infrastructure merge, freeze a single-file test-conformance Packet for tests/integration/test_e2e01_cycle2_execution_seam.py that changes only this obsolete expectation to assert bounded fail-closed behavior
  - no Eval consumer, Composition product, Code Freeze, final suite or status advancement may begin until that successor Packet merges and the exact neighbor command passes
contract_changes: NONE — preserves the signed Application current-query contract; only an obsolete integration-test expectation is queued for conformance.
security_impact: POSITIVE — prevents the persistence reader from presenting historical query authority as current authority.
eval_impact: NONE — no Case, grader, metric, manifest or lifecycle change; successor changes one integration test expectation only.
known_successor_blocker:
  - single-file current-query test-conformance Packet is REQUIRED immediately after Infrastructure merge
  - Eval-only consumer, Composition, final 02-18 suite, status writeback and Graphify remain NOT_RUN / NOT_COMPLETE
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: W12_R19R5RIRV_EXACT_FOUR_FILE_HEAD_WITH_ONE_ADJUDICATED_NEIGHBOR_BLOCKER
  targeted_risk_checks: exact product head/tree/blobs, Gate/AutoTarget owner closure, three fixture provider ids, missing Gate fail-closed, exact sole neighbor failure and frozen current-query cause
  focused_tests: uv run pytest -q tests/integration/test_agent_run_service_v2_persistence.py tests/integration/test_postgres_recovery.py tests/integration/test_cycle2_fixture_seed.py
  neighbor_tests: uv run pytest -q tests/integration/test_postgres_v3_request_understanding_writes.py tests/integration/test_e2e01_cycle2_execution_seam.py
  full_suite_gate: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  phase_end_deep_audit: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  graphify_gate: FINAL_REFROZEN_02_18_ONLY
required_checks:
  - exact four-file allowlist, signed-base direct ancestry, pinned head/tree/blobs and git diff --check
  - baseline two named paths and focused suite PASS
  - neighbor command produces exactly 37 PASS and the one named current-query test failure; any additional or different failure blocks merge
  - independent reviewer confirms the failure comes from the frozen CandidateSet current query validator after the test creates an internally stale graph
  - no reader normalization, Application/Core/Eval/Composition/migration/schema/codec/Case/manifest change
  - local independent review and remote exact-head review PASS with zero unadjudicated P1
expected_results:
  - exact Infrastructure candidate merges without modification and with one explicitly carried successor blocker
  - current-query contradiction remains fail closed
  - no downstream phase starts before the single-file conformance successor closes the blocker
done_when:
  - exact product candidate merges reviewed/signed as B_C2_W12_R19R5RIR_POSTGRES_READER_FIXTURE
  - Integrator freezes and executes the required single-file test-conformance Packet from that exact signed product successor
rollback:
  - before successor work, revert the exact four-file Infrastructure commit atomically
  - after descendants exist, invalidate and revert descendants first; no migration/data rewrite required
handoff_format:
  - exact branch/base/head/tree/blobs, 2/40/37+1 results, sole failure/cause, review verdict, signed merge SHA, mandatory successor and rollback
output_barrier: B_C2_W12_R19R5RIRV_VERIFICATION_CORRECTION
handoff_to: tech-lead
```
