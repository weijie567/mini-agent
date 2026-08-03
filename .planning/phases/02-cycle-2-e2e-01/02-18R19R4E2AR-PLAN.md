---
phase: 02-cycle-2-e2e-01
plan: 02-18R19R4E2AR
type: application-evidence-readiness-contract-replacement
depends_on: [02-18R19R4E2A]
files_modified:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
requirements: [E2E01-01, E2E01-02, E2E01-03, E2E01-04, E2E01-05, E2E01-06]
---

# 02-18R19R4E2AR｜W12 RU v3 Phase 1 + Cycle 2 evidence contract replacement

```yaml
task_id: 02-18R19R4E2AR
goal: 在相同Application ownership与四文件边界内替换尚未执行的R4E2A产品合同，同时补齐Phase 1与Cycle 2的独立staging-only v3 exact evidence reader及global readiness Port，使R4E2B/R4F/Composition可以证明全部16个Phase 1 variants和27个Cycle 2 Cases均消费v3-only actual evidence。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w12-ru-v3-evidence-contract-r1
base_branch: integration/e2e01-cycle2
base_sha: 5b7678c731317cefd2bbd80b5162a535f7ad75e6
base_tree: 2ab154011abc962be9fcf8fe206074c63d9bf58c
worktree_id: e2e01-cycle2-w12-ru-v3-evidence-contract-r1
agent_role: runtime-engineer
writer: w12-ru-v3-evidence-contract-owner
owned_files:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
forbidden_files:
  - all files outside owned_files
  - src/mini_agent/core/**
  - src/mini_agent/application/persistence.py
  - src/mini_agent/application/agent_run_service.py
  - src/mini_agent/infrastructure/**
  - src/mini_agent/evaluation/**
  - alembic/**
  - tests/integration/**
  - tests/e2e/**
  - evals/**
  - docs/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
required_contract_blobs:
  docs/implementation/e2e01-thin-slice-implementation-spec.md: f145f31983022167dae077dc956f13365cf5ff13
  docs/implementation/e2e01-cycle2-implementation-spec.md: 7d62c6990cb4b742071262d2f0d9a52727763b0a
  docs/architecture/intent-design-reference.md: 8fe1120a49ba2b4b4c12f428ada9e199472a0c
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  AGENTS.md: e8721c7845b36d2671b317a0dc1cd44f1b52ee2e
required_dependency_blobs:
  .planning/phases/02-cycle-2-e2e-01/02-18R19R4E2A-PLAN.md: 95dc94060c6398d4bfd8f4c4688dca1eea268d51
  src/mini_agent/application/persistence.py: d556bfd98f4e6d79ddc2ba888b0a1cd1cc8b35e8
  src/mini_agent/core/request_processing.py: 6183510fce33049758ffec9d19ce7e32b6e4dd36
  src/mini_agent/core/task_state.py: 3a279b9156eb03768d58c5aa7029479c1da9a974
required_source_blobs:
  src/mini_agent/application/records.py: b044e550990d932f0d650038237dc17f00380552
  src/mini_agent/application/ports.py: 40d1de351aff85bc5972676a444162aa5db24c5a
  tests/component/application/test_record_contracts.py: f68b0c04c9a2613af7780e2c3b379a2d739f7ec3
  tests/component/application/test_ports_contract.py: d2c4689a4e28213ef2a3036d1b2fb4ca59bd7825
preflight_facts:
  - signed R4E2A Plan已识别Cycle2 v3 evidence/readiness缺口，但其产品尚未开始、无source/test commit或PR，可以由本Plan在执行前安全替换
  - independent blocker裁决确认Phase 1 ExactRunEvidenceClosure仍静态绑定RequestUnderstandingRecordV2 / AcceptedTaskDeltaV2，ExactRunEvidencePort、PostgreSQL reader、Harness与16个variants因此仍形成完整v2 evidence链
  - 仅扩Cycle2ExactRunEvidenceClosure无法满足Thin v3 target manifest及Cycle2 Spec对Phase 1 Grader actual evidence同样v3-only的要求；R4F无权修改Application DTO/Port，R4E2B也无权自行发明该合同
  - 当前active Phase 1与Cycle 2 reader/writer必须在本包及R4E2B/R4F完成前保持不变，故新v3 surface必须是独立staging入口而不是未闭合的原地切换
supersession:
  supersedes_product_contract: 02-18R19R4E2A
  reason: CONFIRMED_W12_BLOCKER_PHASE1_V2_ACTUAL_EVIDENCE
  prior_product_state: NOT_STARTED
  preserved_decisions:
    - Cycle2ExactRunEvidenceClosure gets one exact request_understanding_closures tuple
    - Cycle2 v3 owner-scoped staged reader and global readiness assertion
    - cross-parent per-Task timeline, one-snapshot evidence, no stitching, no active-route change
  added_blocker_scope:
    - independent Phase1 ExactRunEvidenceV3Closure
    - staged Phase1 v3 owner-scoped reader
  forbidden_interpretation: this replacement does not reopen Core, codec, schema, Case, metric, provider, Eval or architecture design
packet_split_ruling:
  - R4E2AR remains one Application writer and the exact same four product files; it only closes a missed consumer of the already-frozen active target
  - R4E2B subsequently implements Phase 1 and Cycle 2 v3 readers/readiness plus physical migration/writers in Infrastructure; R4F consumes both staged readers and changes Eval fields; Composition performs final owner-local canonical method switch
  - no product implementation may begin from R4E2A alone; only this replacement Plan authorizes the four-file product
contract_freeze:
  baseline: 253bb6bd8dc2f84d6ca95a98f625d80fa80e5461
  status: FROZEN
  allowed_changes: only the missing Phase 1 and Cycle 2 v3 evidence/readiness contract required by 16 Phase 1 variants, 27 Cycle 2 Cases, migration and Composition
  forbidden_expansion: new schema version, record family, Case, metric, feature, generic evidence API, public base class, registry, architecture abstraction, database surface, refactor unrelated to the two exact closures or non-blocking optimization
  code_freeze_gate: after reviewed R19R5R merge
owner_decisions:
  - add an independent ExactRunEvidenceV3Closure for Phase 1; it carries the same complete Phase 1 Run evidence families but replaces the legacy v2 parent/children surface with exactly request_understanding_closure: RequestUnderstandingClosureV3 | None and has no RequestUnderstandingRecordV2, AcceptedTaskDeltaV2, v2/v3 union or alias field
  - the Phase 1 v3 closure accepts only the generic e2e01-thin-v2 ADD_GOAL branch. Cycle 2 initial, continuation/SUPPLY_INPUT, v2, future branch, wrong parent/child type, missing/extra/reordered child or partial accepted set fails before Eval
  - aggregate-invalid Phase 1 may carry no RU closure and no accepted Task graph; zero/all-reject records use one exact v3 parent with zero children; partial/multi-accept preserve Candidate order and every accepted child
  - Phase 1 v3 parent must bind the root AgentRunRecord and authoritative Message set; accepted children must resolve exact Task/InputBinding records, preserve Candidate input value/authority/source, and form one contiguous per-Task chain closed by TaskStateTransition/current Task/RequestUnit/RunTaskLink result
  - preserve ExactRunEvidenceClosure and load_exact_run_evidence_for_owner as the current v2 active surface byte-for-byte in public fields/signature/behavior until Composition. Add load_exact_run_evidence_v3_for_owner(owner_scope, run_id) to ExactRunEvidencePort as an explicit inactive staging read returning only ExactRunEvidenceV3Closure
  - the Phase 1 staged reader uses one owner-scoped consistent snapshot; None remains only absent/unauthorized. Selected-owner version/decode/provenance/reference/cardinality/closed-set failure raises bounded P0PersistenceIntegrityError; no second call, expectation, Case, fallback, read-time conversion, repair or grader stitching
  - to avoid duplicating the full Phase 1 non-RU graph rules, records.py may extract only private branch-neutral validation helpers from the existing ExactRunEvidenceClosure validator. Both legacy v2 and new v3 classes must call the same helper and prove behavior parity; no public generic DTO/base/registry/protocol or change to legacy accepted semantics is allowed
  - ExactRunEvidenceV3Closure must reuse the existing private sanitized Binding-validation error boundary: raw Candidate/Binding values are absent from ValidationError str/repr/json/errors input, cause and context. Any private metaclass/helper reuse must preserve the legacy v2 error type, message, location, hide_input behavior and cause/context projection byte-for-byte
  - extend Cycle2ExactRunEvidenceClosure by exactly one default-empty request_understanding_closures: tuple[RequestUnderstandingClosureV3, ...]. Each parent/children closure remains exact, and the enclosing DTO validates unique parent/child identity, root/supporting Run and Message membership, Task/RequestUnit/Binding closure and provenance references
  - Cycle 2 evidence distinguishes no RU aggregate from one persisted zero-Candidate or all-reject parent with zero children; generic partial/multi-accept parents remain legal and preserve Candidate ACCEPT order without flattening, omission or single-child coercion
  - across all Cycle 2 RU parents, reconcile accepted-child effects and task_state_transition_records into one canonical timeline per Task from the applicable RunTaskLink base. Distinct effects cannot overlap/reuse an edge, gaps are forbidden, exact duplicate representations must agree on every shared relation, and the terminal equals current Task/RequestUnit plus applicable link result
  - add load_cycle2_exact_run_evidence_v3_for_owner(owner_scope, run_id) to Cycle2RuntimeRecordPort. It returns the entire Cycle2 graph and all applicable v3 RU closures from one owner-scoped consistent snapshot; selected active graph containing v1/v2/future RU fails closed
  - add assert_request_understanding_v3_ready() to Cycle2RuntimeRecordPort as the single internal no-argument global fence. It returns None only when approved physical cutover is installed, global active v2 residual is zero and all active v3 Phase 1/Cycle 2 parent/child/provenance/owner graphs exact-decode under one consistent fence
  - readiness returns no boolean/count/data, accepts no user/model/Case/owner/bypass/repair input, admits v1 only as archival, grants no dispatch/result authority and fails through existing bounded integrity semantics
  - both staged readers require Infrastructure to re-read authoritative Message content and verify every source span/SHA-256 in the same snapshot; DTO/codec/physical owner/provenance/graph/readiness remain separate gates
  - R4E2AR changes no caller, adapter, database, migration, registry, Runtime service, Composition Root or Eval. Existing active methods and all v2 behavior remain unchanged; final active contract removes/stops legacy v2 read paths only in the reviewed Composition owner-local switch
implementation_tasks:
  - implement ExactRunEvidenceV3Closure plus the minimum private shared Phase 1 graph-validation and sanitized-error reuse; prove the legacy ExactRunEvidenceClosure field set, signatures, accepted/rejected vectors and safe error projection are unchanged
  - implement the Cycle2 request_understanding_closures field and cross-parent graph/timeline validator without changing existing default-empty constructions
  - declare the two staged v3 reader methods and one readiness assertion with exact signatures/docstrings on their existing owner-correct Ports
  - add Phase 1 component vectors for no-record, zero/all-reject, partial/multi-accept and exact Task/Binding/transition/link closure; reject legacy v2 injection, Cycle2 branch, wrong run/message/provenance/task/binding, missing/extra/reordered child, overlap/gap/wrong terminal and reconstructed models
  - add the v3 counterpart of the existing raw-secret Binding validation test and assert the secret is absent from str(error), repr(error), error.json(), error.errors() including input, __cause__ and every context value; keep the legacy six-projection assertions unchanged
  - add Cycle 2 component vectors for no RU, one-parent zero-Candidate, one-parent all-reject, generic partial/multi-accept with exact Candidate order, initial/SUPPLY_INPUT parent sets, dual Binding and cross-parent chain; reject v2, duplicate identity, wrong run/message/task/unit/binding, partial children, overlap/gap/wrong terminal, accepted/transition mismatch, reconstructed nested models and extra fields
  - add Port tests for both owner-scoped staged reader signatures/return types, TrustedOwnerScope requirement, no expectation/Case inputs, readiness zero inputs/None result and unchanged legacy active signatures
contract_changes: IMPLEMENTS_APPROVED_CORRECTION — corrects a missed Phase 1 consumer of the frozen v3-only actual-evidence target before product execution. No canonical contract, Case, metric, schema, business behavior or active route changes.
security_impact: POSITIVE — independent typed v3 closures, one owner-scoped snapshot, authoritative Message provenance and global zero-v2 readiness prevent version confusion, cross-owner stitching and false readiness.
eval_impact: CONTRACT_PREREQUISITE_ONLY — supplies both typed v3 evidence sources R4F must consume; changes no current EvalEvidence field, grader, Case, provider, artifact, dataset, metric or lifecycle.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE
  implementation_review: W12_RU_V3_PHASE1_CYCLE2_EVIDENCE_EXACT_HEAD
  targeted_risk_checks:
    - exact four-file Application allowlist and base/blob containment
    - Phase 1 new class is v3-only with no v2 field/union/alias and legacy class behavior remains exact
    - private validator extraction is minimal and produces zero legacy regression
    - new v3 Binding validation uses the same sanitized error boundary with no raw input projection or exception chaining
    - two staged readers each return a complete one-snapshot closure; no second-call RU stitching
    - Cycle 2 cross-parent and Phase 1 per-Task timelines are contiguous and terminally closed
    - no active service/adapter/Eval/database/migration/registry change
required_checks:
  - uv run pytest tests/component/application/test_record_contracts.py
  - uv run pytest tests/component/application/test_ports_contract.py
  - uv run pytest tests/component/application
  - git diff --check
  - repository-wide read-only impact scan for both ExactRun evidence DTOs/Ports, all constructors/implementers/callers, EvalEvidence consumers, PostgreSQL reader/readiness and final active-switch owners
full_suite_gate: DEFERRED_TO_FINAL_REFROZEN_02_18
done_when:
  - focused and complete Application component suites pass with explicit legacy parity
  - exact four-file scope and unchanged active callers/routes are mechanically proven
  - local independent implementation review and remote exact-head review are PASS with zero open findings
  - product merges as B_C2_W12_RU_V3_EVIDENCE_CONTRACT_R1 and only then 02-18R19R4E2B planning begins
rollback:
  - before R4E2B, revert the four-file inactive product atomically; no data/migration/runtime rollback is needed
  - after R4E2B/R4F but before active cutover, remove Eval consumers then Infrastructure implementations in reverse owner order before reverting this Application contract
  - after Composition activation, stop v3 writes/dispatch, satisfy exact Infrastructure downgrade, reverse Eval/Infrastructure/Application active switches, then remove staged evidence/readiness surfaces
  - any non-reversible v3-only data blocks rollback with zero writes; never re-enable an active v2 reader, delete evidence or bypass readiness
handoff_format:
  - exact branch/base/head/tree, superseded Plan reference and changed files
  - Phase 1/Cycle 2 evidence/Port signatures, legacy parity, commands/results/NOT_RUN and impact scan
  - unchanged active routes, R4E2B/R4F/Composition blockers, risks and rollback
output_barrier: B_C2_W12_RU_V3_EVIDENCE_CONTRACT_R1
handoff_to: tech-lead
```
