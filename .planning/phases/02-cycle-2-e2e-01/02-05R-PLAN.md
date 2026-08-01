---
phase: 02-cycle-2-e2e-01
plan: 02-05R
type: remediation
wave: W3R
depends_on:
  - B_C2_SELECTED_TARGET_GATEWAY
files_modified:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
autonomous: false
requirements:
  - E2E01-02
  - E2E01-03
  - E2E01-05
  - E2E01-06
user_setup: []
must_haves:
  truths:
    - "existing-Task continuation InputBindingV2 write 绑定 current owner/Conversation/USER Message/Task/RequestUnit，并以一个 CAS 同步推进 Task/RequestUnit version。"
    - "candidate_ordinal 不得走普通 continuation writer；ordinal InputBindingV2、RequestUnit ref、SelectionRecord、canonical UUID selected target、pending closure 与 Task/RequestUnit v→v+1 必须在同一个 CAS 中形成。"
    - "GateDecisionV2、AuthorizedToolCommandV2 与 CREATED ToolCallRecordV2 的 verified_target_ref 和 argument_binding_refs 精确闭合；非 APPLIED 结果全部零写。"
    - "v1 Application command/Port 保持兼容；新 v2 command/Port 在 codec/Runtime cutover 前 inactive。"
  artifacts:
    - "continuation InputBindingV2 current-owner read/write closure 与 conditional Port。"
    - "修正后的 ordinal-selection single-CAS command/Port closure。"
    - "CreateToolCallV2Command 与 conditional initial ToolCall v2 insert boundary。"
  key_links:
    - "B_C2_SELECTED_TARGET_GATEWAY → reviewed 02-05R → B_C2_W4_READY。"
    - "02-06/08/09/13 只能从真实 reviewed 02-05R successor 重新冻结。"
---

# Phase 2 Plan 02-05R｜Continuation binding and atomic selection writer

> **EXACT TASK PACKET / W3R TARGETED_ATOMICITY**
>
> 本 Packet 以 reviewed 02-04R 的真实 merge successor 为唯一 base。独立 planning
> review `PASS` 且本 Plan merge 前不得创建 implementation Worktree。该 Packet 合并后
> 才能把真实 successor 命名为 `B_C2_W4_READY`；不得预填 W4 base。

## 目标与边界

在 Application owner 内补齐三个 inactive v2 原子边界：existing-Task continuation
`InputBindingV2` writer、ordinal selection single-CAS，以及 accepted Gate / authorized
command / initial ToolCall v2 的 durable insert closure。现有 ordinal helper 错误假定
ordinal binding 已在 selection CAS 前写入当前 RequestUnit；本 Packet 必须删除该前置
写入假设，并把 binding 与 selection effect 一次提交。

`OrderCandidateSelectionRecord.selected_target_ref` 只持久化新生成 UUID 的 canonical
lowercase text，满足 `str(UUID(text)) == text`；Application / Tool logical identity 继续
使用同一 UUID。它不得等于、派生自或哈希自 `owner_scoped_order_target_ref`、摘要、订单号
或 payload。v1 records / Ports、active codec、Infrastructure adapter、Runtime dispatch、
migration 与 Eval lifecycle 均不切换。

## Exact Task Packet

```yaml
task_id: 02-05R
goal: 实现 continuation InputBindingV2、ordinal selection single-CAS 与 Gate/Command/ToolCall v2 initial insert 的 Application 原子闭包。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-continuation-selection-writer
base_branch: integration/e2e01-cycle2
base_sha: 53e36aa88fab1ab99d2b076a1d731f63dced064a
base_tree: 3f9852e825a69c9ceb8a19e18c810263ef74349e
planning_control_base_sha: 53e36aa88fab1ab99d2b076a1d731f63dced064a
planning_control_base_tree: 3f9852e825a69c9ceb8a19e18c810263ef74349e
worktree_id: e2e01-cycle2-continuation-selection-writer
agent_role: runtime-engineer
writer: runtime-engineer-application-contract
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent final exact-head review PASS; never use admin bypass
owned_files:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
forbidden_files:
  - all repository files outside the exact four-file owned_files allowlist
  - src/mini_agent/core/**
  - src/mini_agent/infrastructure/**
  - src/mini_agent/runtime.py
  - src/mini_agent/bootstrap.py
  - tests/** except the exact two owned Application test files
  - evals/**
  - alembic/**
  - docs/**
  - .planning/**
  - pyproject.toml
  - uv.lock
  - compose.yaml
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - AGENTS.md sections 3-8
  - PROJECT_DIRECTION.md sections 8-9
  - docs/architecture/intent-design-reference.md sections 10.4.1 and 10.7
  - docs/architecture/tool-calling-design-reference.md sections 8.2-8.3 and 10
  - docs/architecture/memory-design-reference.md Claim / target / Observation boundaries
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.4, 7.13 and 8
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-05R
read_first:
  - AGENTS.md sections 3-8
  - docs/architecture/intent-design-reference.md sections 10.4-10.7
  - docs/architecture/tool-calling-design-reference.md sections 8.2-8.3 and 10
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 7.4, 7.13 and 8
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md slot 02-05R
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/tool_system.py
  - src/mini_agent/core/control_gateway.py
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  PROJECT_DIRECTION.md: ed0ae8482c2d43278a1dd984d5ff55da5265cfda
  docs/architecture/intent-design-reference.md: bfe90f6afa8cd377e8fbcf5f8bf6cdecd570f5a6
  docs/architecture/tool-calling-design-reference.md: c696e172da82f9343a50f563922dfbd4abe29509
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  docs/implementation/e2e01-cycle2-implementation-spec.md: 57ec11693e74f52326e44ebb961ff009a48375be
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 226f527ad9c5bb8683d425cf23c8f3878200d1e6
  src/mini_agent/core/task_state.py: eb6b429b4e44b58a848faf476681a610670ca83b
  src/mini_agent/core/tool_system.py: 12b03785234772dd5ecde4b07162eaced04d92b4
  src/mini_agent/core/control_gateway.py: 1658feab7d3448157631a85ff3d7dfcb01023f74
  src/mini_agent/application/records.py: 1d7be4b01c52f397f1a5c7b74fcd4c68aea54728
  src/mini_agent/application/ports.py: cc075fe7910b3e4eb660bb528f7dda1a26a52869
  tests/component/core/test_task_state_contract.py: 9f922ca2f1b1223c43bb19feb7da16b1a7cf0c17
  tests/component/core/test_tool_system_contract.py: b5be2e7f6129adf3cf0c3c239c035c9d7b72163a
  tests/component/core/test_control_gateway.py: 11b54e0a7b5e21e67380050451c76f79c27238b8
  tests/component/application/test_record_contracts.py: e663a55a3d6ff416f7376e6249b84b62a0fc04d0
  tests/component/application/test_ports_contract.py: 8f530a793a4c59921e9fc6521212331d4fec3ebf
dependencies:
  - exact B_C2_SELECTED_TARGET_GATEWAY = 53e36aa88fab1ab99d2b076a1d731f63dced064a
  - exact B_C2_SELECTED_TARGET_GATEWAY tree = 3f9852e825a69c9ceb8a19e18c810263ef74349e
  - PR #225 feature/residual/latest-integration overlay review PASS and merge tree equals reviewed overlay tree
  - InputBindingV2, GateDecisionV2 and AuthorizedToolCommandV2 are inactive imported Core contracts
  - selected-target UUID remains logical Tool/Gateway identity; canonical string persistence is owned here
contract_changes: NONE — implement the active W3R owner ruling without changing canonical business, Tool or Case semantics.
security_impact: HIGH / ATOMICITY + AUTHORIZATION GRAPH — reject pre-CAS binding, half-write, stale/foreign closure, target derivation, mixed refs and Gate/Command/ToolCall drift.
eval_impact: COMPONENT ONLY — add deterministic Application command/Port vectors; create no Eval artifact, Case activation, Result or lifecycle transition.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_ATOMICITY
  targeted_risk_checks:
    - ordinary continuation current-owner/current-message closure and candidate_ordinal exclusion
    - ordinal binding plus selection effect single-CAS with zero half-write
    - canonical lowercase UUID text and exact UUID round-trip without target derivation
    - exact Task/RequestUnit v-to-v-plus-one allowed delta
    - GateDecisionV2/AuthorizedToolCommandV2/ToolCallRecordV2 target and binding exact-copy
    - genuine in-process Gateway authorization provenance; serialized/copied/unsealed Gate is inert
    - current RequestUnit InputBindingV2 resolution and target/ref separation
    - v1 CreateToolCallCommand and RuntimeRecordPort compatibility
    - every non-APPLIED conditional write result grants zero write/dispatch authority
  focused_tests: uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q
  neighbor_tests: uv run pytest tests/component/core/test_task_state_contract.py tests/component/core/test_tool_system_contract.py tests/component/core/test_control_gateway.py tests/component/core/test_candidate_selection_contract.py tests/component/core/test_cycle2_memory_contract.py -q
  full_suite_gate: NOT_RUN_FOR_02_05R; next canonical full is W6 exit
  phase_end_deep_audit: W12_ONLY
verification:
  focused: uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q
  neighbor: uv run pytest tests/component/core/test_task_state_contract.py tests/component/core/test_tool_system_contract.py tests/component/core/test_control_gateway.py tests/component/core/test_candidate_selection_contract.py tests/component/core/test_cycle2_memory_contract.py -q
  compile: uv run python -m compileall -q src/mini_agent/application/records.py src/mini_agent/application/ports.py tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py
  diff_check: git diff --check 53e36aa88fab1ab99d2b076a1d731f63dced064a...HEAD
  migration: NOT_RUN — 02-10 owns physical migration/cutover
  integration: NOT_RUN_PER_PACKET
  full: NOT_RUN_BY_REVIEW_PROFILE
latest_integration_overlay: REQUIRED — before merge replay the exact four-file patch on current integration, prove frozen dependency blobs unchanged, and obtain independent targeted exact-head overlay review PASS.
required_checks:
  - exact base/tree, required blobs, branch/worktree absence, clean state and branch protection preflight PASS
  - changed files equal the exact four-file allowlist; no Core, Infrastructure, migration, Runtime, Eval, docs/planning or Graphify changes
  - exact v1 Application command/Port shapes remain compatible; all new records and Port methods are inactive Cycle 2 additions
  - ordinary continuation loads one current trusted owner/Conversation/saved USER Message/Task/RequestUnit/binding closure and rejects absent versus unauthorized without disclosure
  - ordinary continuation accepts only InputBindingV2 order_id/product_description/shipment_not_received; candidate_ordinal is rejected outside selection CAS
  - new binding source_refs equal the exact saved USER Message; binding id is new; optional supersedes resolves to the one current same-name binding and no other binding is replaced
  - ordinary continuation advances Task and RequestUnit exactly once; Task changes only state_version/updated_at, RequestUnit changes only input_binding_refs/state_version/updated_at, all other fields and status remain exact
  - every stale/foreign/wrong-direction/wrong-message/wrong-version/duplicate/ref-mismatch continuation command fails before write; every non-APPLIED Port result means binding/refs/versions all remain absent
  - ordinal selection loaded closure proves current owner/Conversation/Run/Task/RequestUnit/CandidateSet/Observation/query binding/pending question and one saved USER selection Message, but contains no prewritten ordinal binding/ref
  - selection command carries one exact InputBindingV2(name=candidate_ordinal); binding id equals request ordinal_input_binding_ref, strict ordinal matches, source_refs equal the saved Message and the base RequestUnit does not already contain the ref
  - selection single CAS writes ordinal binding, appends exactly its RequestUnit ref, writes one SelectionRecord and a fresh UUID selected target, closes the exact pending question, sets Task WAITING_USER-to-ACTIVE and advances Task/RequestUnit v-to-v-plus-one
  - selection Task delta is limited to status/state_version/updated_at; RequestUnit delta is limited to status/state_version/updated_at/input_binding_refs/open_questions; Observation/Evidence/result/pending-action/goal/dependency and other fields cannot change
  - SelectionRecord selected_target_ref is canonical lowercase UUID text with str(UUID(text)) == text and exact equality to the command logical UUID; it is not equal to or derived from owner_scoped_order_target_ref, summary, order id or payload hash
  - preexisting ordinal ref, consumed capability, duplicate SelectionRecord, stale CandidateSet, wrong owner/message/ordinal/target/version or CAS conflict produces zero binding/selection/target/pending/version writes
  - CreateToolCallV2Command accepts only exact accepted GateDecisionV2, matching AuthorizedToolCommandV2, clean CREATED ToolCallRecordV2, current Task/RequestUnit and exact current InputBindingV2 records
  - initial ToolCall creation must re-prove the supplied Gate/command through the public non-bypassable Gateway authorization path (or an owner-equivalent exact check); a serialized, model-validated, copied, constructed or otherwise unsealed Gate is audit evidence only and cannot authorize insert
  - Gate/command/ToolCall canonical tool, gate id, model/context/provider ids where represented, validated version, argument_binding_refs and verified_target_ref form one exact graph; Gate validated arguments equal Authorized command arguments
  - every argument_binding_ref is unique, belongs to the current RequestUnit and resolves to exactly one current InputBindingV2; verified_target_ref is never an argument binding ref
  - direct/search target is null as defined by the accepted Gate; selected get_order/get_shipment target is the same non-null UUID across Gate/command/ToolCall; no fallback or target inference is allowed
  - created ToolCall v2 is CREATED with attempt_count=0, attempts empty and no terminal/result/recovery projection; a Gate cannot create more than one ToolCall under the conditional Port
  - Cycle2RuntimeRecordPort gains exact current-owner load/apply methods for continuation and conditional initial ToolCall v2 insert; every non-APPLIED result is explicitly zero-write; v1 RuntimeRecordPort is unchanged
  - raw constructed/subclass/coerced/extra-field records and mixed v1/v2 graphs fail closed; no command or Port declaration grants Handler dispatch
  - focused/neighbor/compile/diff checks PASS; canonical full accurately NOT RUN
  - independent final exact-head review PASS with 0 BLOCK/HIGH; MEDIUM fixed or accepted with evidence; LOW/INFO recorded
  - PR targets integration/e2e01-cycle2 and remote head equals reviewed exact head
done_when:
  - continuation, ordinal single-CAS and initial ToolCall v2 graph satisfy all positive/negative vectors without active cutover
  - focused/neighbor transcripts and feature/overlay exact-head reviews PASS
  - reviewed PR is serially merged and exact successor is frozen as B_C2_W4_READY
rollback:
  - before merge close the draft PR and retain review evidence
  - after merge use a normal exact four-file revert PR before any W4 codec/Runtime/migration consumer merge
  - never reset, force-push, delete evidence, restore pre-CAS ordinal writes, derive target or permit partial commit as rollback
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-05R-PLAN.md#handoff
output_barrier: B_C2_W4_READY
```

## Tasks

### Task 1 — RED：冻结 continuation / selection / ToolCall v2 oracle

先增加普通 continuation、ordinal single-CAS、Gate/Command/ToolCall v2 graph 与 v1
compatibility vectors。旧测试中 pre-CAS ordinal binding 已存在、selected target 等于
owner-scoped opaque ref 的期望必须改为 canonical fail-closed，不保留双行为。

### Task 2 — GREEN：continuation 与 ordinal selection 原子 writer

新增普通 continuation current-owner command/Port；修正 selection closure，使 ordinal
binding 只由 selection command 携带并与 pending closure、SelectionRecord、fresh UUID
target 和版本推进在一个 conditional write 中形成。普通 writer 明确拒绝 ordinal。

### Task 3 — GREEN：initial ToolCall v2 durable graph

新增 `CreateToolCallV2Command` 与 conditional Cycle 2 Port，闭合 accepted Gate、authorized
command、current InputBindingV2 与 clean CREATED ToolCallRecordV2。不得复用 v1 insert、
生成 Handler dispatch authority或提前切 active codec。完成 focused/neighbor/compile/
containment 后做窄范围 TARGETED_ATOMICITY review。

## W3R gate

```text
product base == 53e36aa88fab1ab99d2b076a1d731f63dced064a
AND product tree == 3f9852e825a69c9ceb8a19e18c810263ef74349e
AND PR #225 state == MERGED
AND PR #225 merge tree == reviewed overlay tree
AND this exact Plan is present in reviewed planning provenance
AND all required product blobs equal the frozen literals
AND implementation branch/worktree do not already exist
AND planning review verdict == PASS
```

任一条件不成立即 `BLOCK`；不得扩大 allowlist、复制 Core owner type、先写 ordinal
binding、把 opaque owner ref 当 UUID、允许半写或提前把 v2 切为 active。

## Handoff

只报告 exact base/head/tree、branch/PR、实际四文件、focused/neighbor结果、targeted
review disposition、atomicity/target identity、contract/security/Eval impact与下一 barrier。
明确标记 active codec/Infrastructure/Runtime/migration/full/Eval lifecycle 均未推进。
