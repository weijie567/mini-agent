---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R4FR
type: planning-control-correction
depends_on: [02-18R19R4F]
files_modified:
  - .planning/phases/02-cycle-2-e2e-01/02-18R19R4FR-PLAN.md
requirements: [E2E01-01, E2E01-02, E2E01-03, E2E01-04, E2E01-05, E2E01-06]
---

# 02-18R19R4FR｜R4F staging gate 与 Composition activation gate 纠正

```yaml
task_id: 02-18R19R4FR
goal: 只纠正02-18R19R4F中“Composition明确延期”与“要求Composition测试在R4F全绿”的自相矛盾门禁；保持R4F十文件产品合同、所有Case/Fixture/指标、R19R5R与最终Composition顺序不变，并把唯一Qwen Composition active-reader失败锁定为后续必须转绿的可复现W12 blocker。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w12-r4fr-gate-correction
base_branch: integration/e2e01-cycle2
base_sha: 9731ef040d1c45b3c5987b4d31e24ceab6de65d0
base_tree: 7a573172ece6e460297044711c5c9f91935a5811
worktree_id: e2e01-cycle2-w12-r4fr-gate-correction
agent_role: tech-lead
writer: w12-planning-status-owner
owned_files:
  - .planning/phases/02-cycle-2-e2e-01/02-18R19R4FR-PLAN.md
forbidden_files:
  - all files outside owned_files
required_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R4F-PLAN.md: 54261bcf6c623595730445980456be5647fe9849
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
  src/mini_agent/bootstrap.py: 0a63c08d454383bc73363a43622f12567cec259e
  src/mini_agent/evaluation/harness.py: 08b96716da4dab0ec9555ae16af6c37d1a7d5cfe
  tests/integration/evaluation/test_e2e01_offline_harness.py: 34f0871b3976f3158f9c605ac2d9ff976641f07d
supersedes:
  - only 02-18R19R4F review_profile.focused_tests
  - only 02-18R19R4F required_checks focused-test entry
  - only 02-18R19R4F required_checks entry for complete component/integration Eval suites
  - only 02-18R19R4F done_when wording that incorrectly requires the deferred Composition active-reader test to pass before R4F staging merge
preserves:
  - every 02-18R19R4F owner_decision, implementation task, ten-file allowlist, contract freeze, security/Eval impact, artifact chain and rollback rule
  - no v2 Eval field, ExactRunEvidenceClosure fallback, skip, xfail, compatibility decoder or dual-read authority may be added
  - R4F -> R19R5R -> Code Freeze -> reviewed Composition -> final 02-18 gate order
confirmed_blocker:
  test: tests/integration/evaluation/test_e2e01_offline_harness.py::test_qwen_runner_mock_transport_runs_real_postgres_composition
  failure_phase: SYSTEM_UNDER_TEST
  exact_cause:
    - src/mini_agent/bootstrap.py仍调用active v2 load_exact_run_evidence_for_owner
    - src/mini_agent/bootstrap.py仍按ExactRunEvidenceClosure.model_fields重建旧closure
    - R4F按冻结合同只接受ExactRunEvidenceV3Closure，因此正确地fail closed
  owner: downstream Composition Root single-writer
  prohibited_workaround:
    - do not modify, skip, xfail, remove or permanently disable the test in R4F
    - do not add a v2-to-v3 Eval conversion or fallback
    - do not change Bootstrap, Application, Infrastructure or Composition in R4F
  mandatory_resolution: reviewed Composition必须切换到staged v3 owner-scoped reader并重建ExactRunEvidenceV3Closure，使该原测试无修改PASS；否则W12与final gate均不得完成
corrected_r4f_gate:
  bounded_selection_rule: the two `-k not` commands are staging-only green-subset measurements that supersede the two contradictory unfiltered R4F commands; they do not alter test collection or satisfy the separately mandatory blocker fingerprint
  focused_tests:
    - uv run pytest -q tests/component/evaluation/test_e2e01_graders.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/evaluation/test_e2e01_artifact_consistency.py tests/integration/evaluation/test_e2e01_offline_harness.py -k 'not test_qwen_runner_mock_transport_runs_real_postgres_composition'
  neighbor_tests:
    - uv run pytest -q tests/component/evaluation/test_e2e01_versioned_artifact_loader.py tests/component/application/test_ports_contract.py tests/component/application/test_agent_run_service.py tests/integration/test_postgres_v3_request_understanding_writes.py
  eval_scope_tests:
    - uv run pytest -q tests/component/evaluation tests/integration/evaluation -k 'not test_qwen_runner_mock_transport_runs_real_postgres_composition'
  blocker_fingerprint:
    - run the exact named Composition test without skip/xfail and require it to be the only Eval-scope failure
    - any second failure, changed failure phase, changed test body or fallback behavior blocks R4F
  merge_semantics: B_C2_W12_RU_V3_EVAL_CONSUMER is a reviewed staging barrier only; it does not claim active Composition, complete Eval suite, W12 or P0 completion
  successor_base: rebuild the ten-file R4F product commit directly from the signed 02-18R19R4FR merge; stale pre-correction product commit cannot be merged
composition_gate:
  trigger: only after reviewed R19R5R merge establishes Code Freeze
  allowed_change: only owner-local active switches and exact Composition/acceptance test corrections required by this named failure and the 27 Cycle2 / 16 Phase1 gates
  required_pass:
    - the unchanged named Qwen Composition test
    - complete tests/component/evaluation tests/integration/evaluation
    - final refrozen 02-18 canonical suite
  no_scope_expansion: no new schema version, record family, Case, Fixture, lane, metric, threshold, feature or architecture abstraction
contract_changes: NONE — this Plan changes only planning-control gate attribution; R4F product contracts and canonical owners remain byte-semantically unchanged.
security_impact: NONE — the correction preserves v3-only fail-closed behavior and explicitly forbids a legacy fallback.
eval_impact: GATE_CORRECTION_ONLY — the named active-route test remains enabled and failing until its Composition owner fixes it; all other R4F Eval checks must pass with zero unexpected failure.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE
  implementation_review: inherited from 02-18R19R4F after direct successor rebuild
  full_suite_gate: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
required_checks:
  - exact one-file Plan containment and base/blob pins
  - git diff --check
  - independent review confirms the correction neither changes a product contract nor weakens/removes/skips the named test
done_when:
  - this exact Plan merges after local and remote exact-head PASS
  - R4F product is rebuilt from this signed successor and meets corrected_r4f_gate with no failure other than the locked Composition fingerprint
  - R19R5R is refrozen only from the reviewed R4F product successor
rollback:
  - before R4F product merge, revert this single Plan and retain the original R4F P1 merge block
  - after R4F product merge, invalidate R4F/R19R5R/Composition descendants before reverting; never reinterpret the staging barrier as W12 completion
handoff_format:
  - exact base/head/tree and one changed Plan
  - inherited R4F contract proof, corrected commands, locked blocker fingerprint and downstream mandatory PASS gate
output_barrier: B_C2_W12_R4F_GATE_CORRECTION
handoff_to: tech-lead
```
