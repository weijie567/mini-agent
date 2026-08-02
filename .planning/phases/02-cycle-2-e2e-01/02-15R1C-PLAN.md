---
phase: 02-cycle-2-e2e-01
plan: 02-15R1C
type: implementation
wave: W9
depends_on:
  - B_C2_W9_TYPED_READ_EXECUTION
  - B_C2_W9_R1CD_OWNER_APPROVED
files_modified:
  - docs/implementation/e2e01-cycle2-implementation-spec.md
autonomous: false
requirements: [E2E01-02, E2E01-05]
user_setup: []
must_haves:
  truths:
    - "UNIQUE search只从同一owner/current Task的exact Search Observation、CandidateSet和product-description binding形成fresh verified-target capability；owner-scoped business target ref、public summary或模型参数都不能代替它。"
    - "auto target record与Search outcome Task version同一原子提交；partial、wrong-owner、stale、superseded、mapping不唯一或CAS drift全部零写fail closed。"
    - "verified target UUID与owner-scoped business target ref均为Runtime-private；CandidateSet继续不复制target或业务事实，MULTIPLE/ordinal selection语义不变。"
    - "本Packet只补active scoped Spec的逻辑记录与closure，不修改源码、migration、fixture、Eval artifact、Harness、Result或Case lifecycle。"
  artifacts:
    - "Cycle 2 Spec中的OrderCandidateAutoTargetRecord exact logical shape、identity、atomicity、reader/routing与visibility contract。"
  key_links:
    - "B_C2_W9_R1CD_OWNER_APPROVED → reviewed 02-15R1C → B_C2_W9_UNIQUE_TARGET_CONTRACT → 02-15R1D。"
---

# Phase 2 Plan 02-15R1C｜UNIQUE verified-target durability contract

> **EXACT TASK PACKET / W9 SCOPED_SPEC_OWNER_CORRECTION**
>
> PR #281 已 reviewed merge，并从真实 integration successor
> `aef424c0fdd1b2c913a699b6a4f456e14b178eee` / tree
> `dc4662ac4e994811cb8a2160f9678d8f86cfdf61` 批准 W9 在原 wave 内增加
> `02-15R1C → 02-15R1D`，当前 36 slots / 16 wave labels。R1 second-refrozen
> checkpoint保持unpublished；本Packet只定义UNIQUE auto-target durable contract，
> 不把实现偶然行为升级为owner语义。Cases继续为`CONTRACT_DEFINED`。

## Exact Task Packet

```yaml
task_id: 02-15R1C
goal: 在active Cycle 2 scoped Spec中补齐UNIQUE search自动绑定所需的独立durable verified-target capability record及其exact原子闭包。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-unique-target-contract
base_branch: integration/e2e01-cycle2
base_sha: aef424c0fdd1b2c913a699b6a4f456e14b178eee
base_tree: dc4662ac4e994811cb8a2160f9678d8f86cfdf61
planning_control_base_sha: aef424c0fdd1b2c913a699b6a4f456e14b178eee
planning_control_base_tree: dc4662ac4e994811cb8a2160f9678d8f86cfdf61
worktree_id: e2e01-cycle2-w9-unique-target-contract
agent_role: gsd-doc-writer
writer: cycle2-scoped-spec-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - docs/implementation/e2e01-cycle2-implementation-spec.md
forbidden_files:
  - all repository files outside the exact one-file owned_files allowlist
  - src/**
  - tests/**
  - alembic/**
  - evals/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - AGENTS.md sections 3-8
  - docs/architecture/intent-design-reference.md sections 10.4 and 10.7
  - docs/architecture/memory-design-reference.md section 14.4
  - docs/architecture/tool-calling-design-reference.md sections 8.2-8.3
  - Cycle 2 Spec sections 2.4, 3.2, 7.3 and 7.13
  - reviewed Gate P2-A10 owner ruling in the master execution Plan
read_first:
  - docs/implementation/e2e01-cycle2-multi-agent-plan.md
  - docs/implementation/e2e01-cycle2-implementation-spec.md
  - docs/architecture/intent-design-reference.md
  - docs/architecture/memory-design-reference.md
  - docs/architecture/tool-calling-design-reference.md
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: 70c370945ead30be220d127bbbf3fc3c9e4f5dc3
  docs/implementation/e2e01-cycle2-multi-agent-plan.md: 93cca906cb96bd9df36769a856ab7512a4bcf08c
  docs/architecture/memory-design-reference.md: fdcdd3c751eb03b7462257cfd62354c9c2917a69
  docs/architecture/intent-design-reference.md: bfe90f6afa8cd377e8fbcf5f8bf6cdecd570f5a6
  docs/architecture/tool-calling-design-reference.md: 15176cf033ec7b91da1bd96606499ed48fb4d122
  src/mini_agent/core/task_state.py: eb6b429b4e44b58a848faf476681a610670ca83b
  src/mini_agent/core/request_processing.py: 08025e48bfc617b1f4b9f9f2f5759d2f57c6dab6
dependencies:
  - exact B_C2_W9_TYPED_READ_EXECUTION = 1fba65168fb487d3c4a8664213831a9c1c5dc815
  - exact Gate P2-A10 successor = aef424c0fdd1b2c913a699b6a4f456e14b178eee
contract_decisions:
  - add logical record_code order_candidate_auto_target_record with schema_version order_candidate_auto_target_record.p0.v1
  - record identity is one caller-allocated fresh UUID verified_target_ref; it is distinct from owner_scoped_order_target_ref and all InputBinding/Observation/CandidateSet identities
  - record exact-copies owner scope, Conversation/Task/RequestUnit, current product_description query binding, CandidateSet identity/version/result Task version, Search Observation identity/schema/source version, unique observation candidate/source version, order_id, owner-scoped target ref, source ToolCall and one trusted verified_at sample
  - UNIQUE Search Observation, UNIQUE CandidateSet, Task/RequestUnit effect and auto-target record commit in one CAS transaction; no partial or repair-on-read path
  - exact reader projects current Cycle2VerifiedOrderTargetFacts and Cycle2TargetObservationFacts only from the committed record closure; no public-summary/order-number/model reconstruction
  - Core route after R1D uses the current query binding in argument_binding_refs and the independent verified_target_ref; it never creates an order_id USER_CLAIM binding
  - CandidateSet remains target-free and business-fact-free; MULTIPLE and OrderCandidateSelectionRecord contracts remain unchanged
contract_changes: YES — additive scoped logical record and UNIQUE closure required to implement the already-active UNIQUE auto-bind product semantic; no Business/Intent/Memory/Tool owner override.
security_impact: CRITICAL / closes target forgery and authority-reconstruction gap; private refs remain non-visible.
eval_impact: PRE-ACTIVATION CONTRACT SUPPORT ONLY — no Case/artifact/Harness/Result/lifecycle mutation; all four Cases remain CONTRACT_DEFINED.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: TARGETED_CONTRACT_SECURITY
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  targeted_risk_checks:
    - verified_target_ref cannot equal or be derived from owner-scoped target, binding, Observation or candidate ref
    - exact UNIQUE/owner/current/version/mapping closure and same-transaction atomicity
    - no CandidateSet fact/target duplication and no public/Trace disclosure
    - no silent change to MULTIPLE/ordinal or Phase 1 order-id path
    - persistence list/record count/version registry text aligned within the scoped Spec
  focused_checks:
    - rg exact record name/code/version and required field vocabulary
    - rg UNIQUE/MULTIPLE/ordinal/visibility/atomicity statements for contradictions
    - link/path and repository-wide active-reference impact scan
  full_suite_gate: NOT_RUN_FOR_R1C; documentation-only owner correction and next canonical full belongs W12
verification:
  diff_check: git diff --check aef424c0fdd1b2c913a699b6a4f456e14b178eee...HEAD
  allowlist: git diff --name-only exact base...HEAD equals docs/implementation/e2e01-cycle2-implementation-spec.md only
  terminology: rg proves OrderCandidateAutoTargetRecord/code/version/UNIQUE closure appear exactly in the owning sections and no current count remains stale
  cross_file_scan: read-only rg over active Business/Intent/Memory/Tool/Spec/master Plan; consumers need no semantic rewrite because scoped Spec owns concrete Cycle 2 encoding
  full: NOT_RUN_BY_REVIEW_PROFILE
required_checks:
  - exact base/tree/blobs/protection/branch absence/clean preflight PASS
  - one-file Spec diff defines complete record/atomicity/reader/routing/visibility/rollback contract
  - record inventory/count and owner table remain internally aligned
  - no source/test/migration/planning/Eval/graphify change
  - bounded independent exact-head review closes BLOCK/HIGH and disposes MEDIUM
done_when:
  - reviewed exact-one-file PR merges and successor is recorded as B_C2_W9_UNIQUE_TARGET_CONTRACT
  - 02-15R1D freezes only from the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - before merge close PR and retain exact-head evidence
  - after merge revert this exact scoped Spec correction before R1D/R1/R2 depend on it
  - never repair by deriving a target from order_id/public summary/private business ref or by weakening Gateway binding checks
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1C-PLAN.md#handoff
output_barrier: B_C2_W9_UNIQUE_TARGET_CONTRACT
```

## Tasks

1. RED：用当前 active Spec与源码只读证据列明UNIQUE target durability / route
   `NOT_FOUND`，并冻结不会复用的私有 ref / public projection。
2. GREEN：只在scoped Spec owner文件中定义exact record、same-CAS closure、reader /
   route projection、visibility、record inventory与rollback；保持MULTIPLE/ordinal不变。
3. VERIFY：terminology、cross-file impact、exact-one-file diff/containment与20秒bounded
   independent review。

## Handoff

报告exact identity、one-file diff、记录名/code/version、原子闭包、focused/cross-file
checks、review与`B_C2_W9_UNIQUE_TARGET_CONTRACT`；明确源码、migration、fixture、
Application/Infrastructure、Harness、Case lifecycle与Result均未推进。
