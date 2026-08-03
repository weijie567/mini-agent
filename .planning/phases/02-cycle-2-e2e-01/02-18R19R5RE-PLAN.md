---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R5RE
type: correction
depends_on: [02-18R19R5R, 02-18R19R5RIR, 02-18R19R5RIT]
files_modified:
  - src/mini_agent/evaluation/graders.py
  - src/mini_agent/evaluation/harness.py
  - tests/component/evaluation/test_e2e01_graders.py
  - tests/integration/evaluation/test_e2e01_offline_harness.py
requirements: [E2E01-02, E2E01-03, E2E01-05, E2E01-06]
---

# 02-18R19R5RE｜W12 Eval exact Gate / AutoTarget consumer

```yaml
task_id: 02-18R19R5RE
goal: 只让现有Cycle2ExactRunEvidenceClosure中的GateDecisionV2与OrderCandidateAutoTargetRecord进入现有Eval evidence seam，并纠正REQ_BINDING对fresh accepted Claim与query-origin Tool target的混淆；不新增合同、Case、指标、record family、schema、fixture、artifact或运行架构。
repository: weijie567/mini-agent
remote: origin
planning_head_branch: codex/e2e01-cycle2-w12-r19r5re-eval-plan
head_branch: codex/e2e01-cycle2-w12-r19r5re-eval-consumer
base_branch: integration/e2e01-cycle2
product_base_sha: 341ad204e9dab96349d5d5b48725ec789524e632
base_sha: 341ad204e9dab96349d5d5b48725ec789524e632
base_tree: 80d5002b941be78eab9ad385c42da93da374348b
worktree_id: e2e01-cycle2-w12-r19r5re-eval-consumer
planning_control_base_sha: 341ad204e9dab96349d5d5b48725ec789524e632
planning_control_base_tree: 80d5002b941be78eab9ad385c42da93da374348b
agent_role: eval-engineer
writer: cycle2-w12-eval-exact-evidence-owner
owned_files:
  - src/mini_agent/evaluation/graders.py
  - src/mini_agent/evaluation/harness.py
  - tests/component/evaluation/test_e2e01_graders.py
  - tests/integration/evaluation/test_e2e01_offline_harness.py
forbidden_files:
  - all files outside owned_files
  - evals/**
  - src/mini_agent/core/**
  - src/mini_agent/application/**
  - src/mini_agent/infrastructure/**
  - src/mini_agent/bootstrap.py
  - tests/integration/test_e2e01_cycle2_execution_seam.py
  - docs/**
  - .planning/**
  - alembic/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - frozen docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.2.1.2, 7.3.4, 7.5, 9.2.3, 9.4 and 9.5
  - signed Application exact Gate/AutoTarget closure at 665925873420ce6002b95414f0190f83a3ccc925
  - signed PostgreSQL exact reader/fixture at b4fa0c4a6657e4abb209d8eaf7a37fd5bf1bc5e6
  - signed current-query conformance at 341ad204e9dab96349d5d5b48725ec789524e632
required_product_blobs:
  docs/implementation/e2e01-cycle2-implementation-spec.md: 7d62c6990cb4b742071262d2f0d9a52727763b0a
  src/mini_agent/application/records.py: 169c65749c4877e18fea5d3d5deae5edd761aee5
  src/mini_agent/core/task_state.py: 3a279b9156eb03768d58c5aa7029479c1da9a974
  src/mini_agent/core/tool_system.py: d5763899da0590f1b5da1a7d32c907a4da9a16b4
  src/mini_agent/evaluation/graders.py: f4ce1ae31ace18ba7712c40731ddcda4a97b30f4
  src/mini_agent/evaluation/harness.py: 1a3794a37cd9dc3c20ede72cfa729e306a63d65d
  tests/component/evaluation/test_e2e01_graders.py: bf544eecc49396d6a65cc163ac972f84ac1a94fc
  tests/integration/evaluation/test_e2e01_offline_harness.py: c28357ea81ae6ea24a82dbe330441f31536b6c25
  evals/cases/e2e01-cycle2.v1.json: 6b77888471318510f3dcf1d16adebb2f64713d27
  evals/manifests/e2e01-cycle2.v1.json: f2fec57be006f84f67e147f1e2898d36aa07d476
required_planning_control_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5R-PLAN.md: cb6b4129ad300b8d51ed5a0e617812610b059a1d
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5RI-PLAN.md: 58b2b8c4a766a53656fa66420fb7b73f96dad713
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5RIR-PLAN.md: f757f194d0b44a75b402c646c82a66b47693ae66
  .planning/phases/02-cycle-2-e2e-01/02-18R19R5RIT-PLAN.md: 1491cacf499d4ec4e54232b3d3f97dccc944d757
  .planning/GOVERNANCE.md: f5ec0fe4b83a23b590457e0b407f3f9135dbf4f7
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
dependencies:
  - contract freeze anchor = 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  - reviewed R19R5R Application evidence = GitHub verified signed 665925873420ce6002b95414f0190f83a3ccc925
  - reviewed R19R5RIR Infrastructure reader/fixture = GitHub verified signed b4fa0c4a6657e4abb209d8eaf7a37fd5bf1bc5e6
  - reviewed R19R5RIT current-query conformance = GitHub verified signed 341ad204e9dab96349d5d5b48725ec789524e632
  - planning-control PR for this exact Plan must merge signed before product writes begin; reject any product-file drift from the pinned base
supersedes:
  - 02-18R19R5 as an executable Packet; it remains historical planning evidence
  - only its obsolete assumption that Trace can replace actual GateDecisionV2/AutoTarget owner records and its former three-file allowlist
confirmed_blockers:
  - Cycle2EvalEvidence and its unbound allowlist currently omit closure.gate_decision_records and closure.auto_target_records, so the exact reader evidence is discarded before grading
  - REQ_BINDING($TASK_VERSION_AT_GATE) currently requires the graded Claim binding_id in Gate Trace and ToolCall.argument_binding_refs; correct get_shipment instead carries product-query target origin while order_id and shipment_not_received are separate fresh accepted Claims
  - Cycle 2 ToolCallGrader currently checks only referenced Binding existence and attempt_count shape; direct unbound SUT evidence can omit, duplicate or drift actual Gate/target authority after the Application closure is mapped
  - complete Eval suites currently produce 894 PASS plus exactly one known qwen-runner real-PostgreSQL Composition failure; that failure is the already-frozen Composition successor blocker and must not be hidden or reclassified by this Packet
implementation_decisions:
  - add exact gate_decisions: tuple[GateDecisionV2, ...] and auto_targets: tuple[OrderCandidateAutoTargetRecord, ...] to Cycle2EvalEvidence; require exact type/storage/canonical round-trip and unique Gate/target identities
  - extend only the existing unbound Cycle 2 allowlist and mapper to copy closure.gate_decision_records and closure.auto_target_records byte-semantically; missing, duplicate, unused or drifted families fail closed at the Eval seam
  - every root/supporting ToolCall resolves exactly one accepted GateDecisionV2 by gate_decision_id; Gate and ToolCall exact-copy model_call_id, context_manifest_id, provider_tool_call_id, canonical tool, ordered argument_binding_refs, validated Task version and verified_target_ref, with Gate.decided_at not after ToolCall.started_at
  - keep Gate as authority and use root GATE_DECISION_RECORDED Trace only as an exact available projection cross-check; supporting Runs are not required to invent root Trace events
  - require every ToolCall to close to its exact Run partition, Task, RequestUnit, ContextManifest and trusted owner; owner or cross-family drift fails before tool-result grading
  - preserve candidate_ordinal / $SELECTION_EXPECTED_TASK_VERSION logic byte-semantically
  - for $TASK_VERSION_AT_GATE require exactly one current same-name accepted Binding owned by exactly one current RequestUnit and same Task, sourced by exactly one authenticated USER Message and accepted Request Understanding v3 child with causal timestamps
  - for order_id require the current fresh child to supersede exactly one historical accepted same-value order_id Claim with a distinct USER source and nondecreasing timestamps; an old unsuperseded Claim cannot satisfy REQ_BINDING
  - prove Claim applicability through the actual accepted Gate/Tool snapshot for the same current Task/RequestUnit and relevant Task version; never require order_id or shipment_not_received Claim ids to join a UNIQUE/ordinal product-query target-origin Tool argument list
  - permit only the already-frozen SUPERSEDED / STATE_OR_BINDING_INVALIDATED no-result recovery shape to grade its persisted v3 Gate/Tool snapshot while the final Task is v4 and the fresh child remains current; do not create recovery Claims or relax ordinary paths
  - close UNIQUE AutoTarget only through the exact current query Binding, CandidateSet, Search Observation, search_orders source ToolCall, owner, target, order/version and timestamp family already enforced by Application; ordinal Selection remains disjoint and no public summary, Claim value or result Observation manufactures authority
  - add positive get_order/get_shipment query-origin and recovery quadrants plus bounded tamper negatives for dropped/duplicate/wrong Gate, wrong AutoTarget, stale/fabricated Claim, wrong source/current owner/Task/Unit/version/ref and target drift
  - keep Case/manifest/fixture/script/lane/artifact/enum registration bytes unchanged; no new grader, predicate, metric, threshold or lifecycle is authorized
contract_changes: NONE — consumes already-signed exact evidence and implements the frozen R19R2 Claim/target-origin separation without changing any owner contract.
security_impact: POSITIVE — actual Gate and target authority remain owner-scoped and distinct from user Claims; value equality, Trace-only projection and public summaries cannot grant target authority.
eval_impact: CORRECTION — existing REQ_BINDING and ToolCallGrader consume actual Gate/AutoTarget evidence and fail closed on provenance drift; no Case, metric, threshold, manifest or lifecycle change.
known_successor_blocker:
  - qwen-runner mock transport real-PostgreSQL Composition test remains the one explicit active-reader failure until the separately frozen Composition Packet
  - Composition, final 02-18 suite, status writeback and Graphify remain NOT_RUN / NOT_COMPLETE
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: W12_R19R5RE_EVAL_EXACT_EVIDENCE_EXACT_HEAD
  targeted_risk_checks: exact mapper inclusion, Gate/Tool one-to-one closure, owner/Run/Task/Unit/Manifest/version identity, fresh Claim/query-origin separation, AutoTarget/ordinal disjointness and bounded recovery exception
  focused_tests: uv run pytest -q tests/component/evaluation/test_e2e01_graders.py tests/integration/evaluation/test_e2e01_offline_harness.py::test_canonical_result_enum_types_are_import_time_closed
  neighbor_tests: uv run pytest -q tests/component/evaluation tests/integration/evaluation
  full_suite_gate: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  phase_end_deep_audit: FINAL_REFROZEN_02_18_AFTER_COMPOSITION
  graphify_gate: FINAL_REFROZEN_02_18_ONLY
required_checks:
  - exact four-file allowlist, signed-base direct ancestry, required blob pins and git diff --check
  - mapper and unbound evidence retain exact Gate/AutoTarget families; drop/duplicate/unused/wrong common-field/target tampering fails closed
  - direct current Claim and get_shipment query-origin Tool both satisfy REQ_BINDING(order_id); old, wrong-source, non-current or malformed supersession Claims fail
  - each root/supporting ToolCall has exactly one accepted exact Gate and closes to Run/Task/Unit/Manifest/trusted owner; root Trace projection cannot replace Gate authority
  - UNIQUE AutoTarget exact graph passes and AutoTarget/ordinal/Claim families remain disjoint
  - state-invalidated recovery resolves retained v3 fresh child against its frozen Gate/Tool snapshot and rejects v2 old Claim
  - Case/manifest blobs remain exactly 6b77888471318510f3dcf1d16adebb2f64713d27 / f2fec57be006f84f67e147f1e2898d36aa07d476
  - focused tests PASS; complete Eval suites have no failure other than the exact named Composition successor blocker; local independent review and remote exact-head review PASS with zero P1
expected_results:
  - product changes exactly the four owned Eval files
  - 27 existing Cycle 2 Case paths and all existing Phase 1 authenticated variants retain their frozen identity and semantics
  - the exact reviewed product merge establishes W12 Code Freeze; only reproducible Composition/final-gate blockers may modify code afterward
done_when:
  - exact product head satisfies all required checks and merges reviewed/signed as B_C2_W12_R19R5RE_EVAL_EXACT_EVIDENCE
  - Integrator declares Code Freeze and refreezes a Composition-only Packet from that exact signed successor
rollback:
  - before Composition, revert the exact four-file Eval consumer atomically
  - after Composition descendants exist, deactivate and revert descendants first; no Case/fixture/artifact/schema/data rollback applies
handoff_format:
  - exact branch/base/head/tree and four changed files/blobs
  - commands/results/one named carried Composition failure, predicate/tamper evidence, contract/security/Eval impact, Code Freeze status and rollback
output_barrier: B_C2_W12_R19R5RE_EVAL_EXACT_EVIDENCE
handoff_to: tech-lead
```
