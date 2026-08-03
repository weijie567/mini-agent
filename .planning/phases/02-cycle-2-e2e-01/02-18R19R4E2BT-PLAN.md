---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R4E2BT
type: verification-fixture-contract-alignment
depends_on: [02-18R19R4E2AR]
files_modified:
  - tests/integration/evaluation/test_e2e01_offline_harness.py
  - tests/integration/test_e2e01_cycle2_execution_seam.py
requirements: [E2E01-01, E2E01-02, E2E01-03, E2E01-04, E2E01-05, E2E01-06]
---

# 02-18R19R4E2BT｜W12 integration verification fixture alignment

```yaml
task_id: 02-18R19R4E2BT
goal: 在两个现有Integration测试文件内，对齐已经合并的Cycle2RequestUnderstandingProvider v3 staging方法与canonical Eval result enum集合，关闭R4E2B完整Integration门禁中可在其clean base精确复现的10个测试阻断；不修改生产代码、合同、Case、指标、架构或active route。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w12-r4e2bt-test-compat
base_branch: integration/e2e01-cycle2
base_sha: ef41d749d538db5f8cee53be2c152cf1275856a0
base_tree: 9508f638718190b2f37c1982f0a87d7e619adf8e
worktree_id: e2e01-cycle2-w12-r4e2bt-test-compat
agent_role: eval-engineer
writer: w12-integration-verification-fixture-owner
owned_files:
  - tests/integration/evaluation/test_e2e01_offline_harness.py
  - tests/integration/test_e2e01_cycle2_execution_seam.py
forbidden_files:
  - all files outside owned_files
  - src/**
  - alembic/**
  - evals/**
  - docs/**
  - .planning/**
  - AGENTS.md
  - pyproject.toml
  - uv.lock
  - graphify-out/**
required_contract_blobs:
  docs/evaluation/agent-evaluation-strategy.md: 8a44696b5d781d40b3e6ff22b771c48d2d57006e
  docs/implementation/e2e01-cycle2-implementation-spec.md: 7d62c6990cb4b742071262d2f0d9a52727763b0a
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
required_dependency_blobs:
  src/mini_agent/application/ports.py: 38c909155afac43e4880cbc54c0e6b3ecfd056a3
  src/mini_agent/evaluation/graders.py: d8cfbb5faf06e83c438e627bf455b2fb8425b409
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
required_source_blobs:
  tests/integration/evaluation/test_e2e01_offline_harness.py: 9a28f226ca257b5a3a14e294d1630480b56f144a
  tests/integration/test_e2e01_cycle2_execution_seam.py: 816c35260ae2245cbdc0df490a659a9be0648281
canonical_inputs:
  - docs/evaluation/agent-evaluation-strategy.md@8a44696b5d781d40b3e6ff22b771c48d2d57006e
  - docs/implementation/e2e01-cycle2-implementation-spec.md@7d62c6990cb4b742071262d2f0d9a52727763b0a
  - AGENTS.md@e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
dependencies:
  - merged Cycle2RequestUnderstandingProvider v3 staging surface in src/mini_agent/application/ports.py@38c909155afac43e4880cbc54c0e6b3ecfd056a3
  - merged canonical result enum closure in src/mini_agent/evaluation/graders.py@d8cfbb5faf06e83c438e627bf455b2fb8425b409
  - R4E2B product remains a separate exact five-file Packet and is not imported into this branch
preflight_facts:
  - clean base ef41d749上的完整Integration门禁为10 failed；其中9项由_Cycle2DirectProvider未实现已经合并的propose_cycle2_continuation_v3 Protocol方法导致，1项由canonical result enum名称断言未同步已经合并的grader闭集导致
  - 两个失败均可在不含R4E2B五文件产品改动的clean base上精确复现，因此不是R4E2B Infrastructure回归；但R4E2B Plan明确要求完整Integration PASS，必须先关闭而不能用pre-existing waiver绕过
  - 生产Provider Protocol、v3 staging语义与grader enum闭集已经冻结；本Packet只能修正测试double和精确名称断言，不得反向修改生产合同
contract_freeze:
  baseline: 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  status: FROZEN
  allowed_changes: only exact verification-fixture alignment required to make the already-frozen W12 Integration gate executable
  forbidden_expansion: production behavior, provider contract, reducer semantics, Eval Case, grader metric, enum membership, result schema, active route, architecture abstraction or unrelated cleanup
  code_freeze_gate: after reviewed R19R5R merge
owner_decisions:
  provider_fixture:
    - add propose_cycle2_continuation_v3 only to _Cycle2DirectProvider and construct the already-frozen Cycle2ContinuationRequestUnderstandingOutputV2 envelope with schema e2e01-cycle2-continuation.p0.v2, current message_ref, contextualization text 选择当前订单候选, empty resolved/uncertainty tuples, current-only source_message_refs and exactly one TaskDeltaOperation.SUPPLY_INPUT candidate
    - freeze that candidate to a fresh candidate_id UUID distinct from message_ref, target_task_alias=current-task, target_request_unit_alias=current-request, outer confidence=0.99, and exactly one candidate_ordinal=2 input from the current message with source_quote=第二 and inner confidence=0.99; do not copy the whole original_query used by the legacy v2 method, reuse Message/Task/RequestUnit identity as candidate_id, or return a presence-only/None stub
    - preserve every existing initial/control response, test input, fixture seed, HTTP path and assertion; add no fallback, branching feature or production adapter
  enum_fixture:
    - update only the exact expected type-name set so it equals the already-imported _CANONICAL_RESULT_ENUM_TYPES at base: include ImportedMapperReference and Cycle2MappingSourceKind, and remove SupersededRunInvalidationKind which is not in the active grader closure
    - do not change the canonical tuple, enum definitions, comparison logic, grader behavior, Case, metric or result artifact
  integration_order:
    - merge this test-only blocker Packet before reviewing the R4E2B prospective merge tree; R4E2B retains its exact five-file allowlist and does not absorb either repair file
    - after this Packet is merged, validate the prospective integration tree containing this repair plus exact R4E2B product head; no gate waiver is permitted
implementation_tasks:
  - import the already-frozen continuation v3 output and candidate types in the execution-seam test and implement the missing exact Protocol method on _Cycle2DirectProvider
  - add one direct async regression that invokes propose_cycle2_continuation_v3 with a real RequestUnderstandingInput-shaped current message and asserts strict validation plus every frozen envelope/candidate/source field, including fresh candidate_id != message_ref and both outer/inner confidence values; a runtime-checkable attribute-presence assertion alone is insufficient
  - align the offline-harness canonical enum type-name assertion with the current imported grader closure
  - run both focused failures, their complete containing modules and the complete Integration suite from the isolated Packet worktree
  - prove exact two-file scope and unchanged production tree; after merge, run the R4E2B prospective-merge Integration gate
contract_changes: NONE — test fixtures consume already-merged frozen contracts; no owner semantics change.
security_impact: NONE — no production identity, authorization, owner, Evidence, CAS, idempotency or side-effect boundary changes.
eval_impact: VERIFICATION_FIXTURE_ONLY — restores exact test coverage of the existing grader enum closure and v3 staging Provider Protocol without adding Case, metric, threshold or Result semantics.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE
  implementation_review: W12_INTEGRATION_FIXTURE_EXACT_HEAD
  targeted_risk_checks:
    - exact two-test-file allowlist and zero production diff
    - continuation v3 test double returns the existing exact schema/operation/aliases/input candidate and grants no extra behavior
    - enum expected set equals current canonical tuple without modifying the tuple itself
    - clean-base 10 failures close and complete Integration becomes green
  focused_tests:
    - direct strict continuation-v3 provider envelope regression
    - canonical result enum type-name closure regression
  neighbor_tests:
    - complete tests/integration/test_e2e01_cycle2_execution_seam.py
    - complete tests/integration/evaluation/test_e2e01_offline_harness.py
  full_suite_gate: complete tests/integration on exact product head, then complete tests/integration on prospective integration tree with exact R4E2B head
  phase_end_deep_audit: DEFERRED_TO_FINAL_REFROZEN_02_18
required_checks:
  - uv run pytest -q tests/integration/evaluation/test_e2e01_offline_harness.py::test_canonical_result_enum_types_are_import_time_closed
  - uv run pytest -q tests/integration/test_e2e01_cycle2_execution_seam.py::test_direct_provider_v3_continuation_is_exact_frozen_envelope
  - uv run pytest -q tests/integration/test_e2e01_cycle2_execution_seam.py
  - uv run pytest -q tests/integration/evaluation/test_e2e01_offline_harness.py
  - uv run pytest -q tests/integration
  - git diff --check
  - exact changed-file containment and zero src/alembic/evals/docs/.planning/graphify-out product diff
required_check_expectations:
  - every pytest command exits 0 with zero failure, Critical failure or execution failure
  - git diff --check exits 0 and exact changed files equal the two owned test files
  - prospective R4E2B merge validation exits 0 before R4E2B exact-head review can pass
full_suite_gate: DEFERRED_TO_FINAL_REFROZEN_02_18
done_when:
  - both formerly failing surfaces and the complete Integration suite pass on this exact head
  - exact two-file implementation scope and zero production diff are mechanically proven
  - local independent implementation review and remote exact-head review are PASS with zero open findings
  - product merges as B_C2_W12_INTEGRATION_FIXTURE_ALIGNMENT; R4E2B prospective merge tree then satisfies its complete Integration gate
rollback:
  - revert this two-test-file Packet atomically before final W12 gate only if the corresponding production Protocol/grader contracts are also reverted by their owners
  - never weaken runtime Protocol checks, remove v3 staging, suppress the enum closure assertion, skip tests or convert the Integration gate into a waiver
handoff_format:
  - exact branch/base/head/tree and changed files
  - focused/module/Integration commands and results
  - explicit NONE contract/security/production impact, allowlist proof and prospective R4E2B merge-gate result
output_barrier: B_C2_W12_INTEGRATION_FIXTURE_ALIGNMENT
handoff_to: tech-lead
```
