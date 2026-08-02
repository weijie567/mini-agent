---
phase: 02-cycle-2-e2e-01
plan: 02-15R1F
type: implementation
wave: W9
depends_on:
  - B_C2_W9_UNIQUE_TARGET_GATE
files_modified:
  - docs/implementation/e2e01-cycle2-implementation-spec.md
autonomous: false
requirements: [E2E01-03, E2E01-05, E2E01-06]
user_setup: []
must_haves:
  truths:
    - "get_shipment只消费current verified target，不要求为UNIQUE或ordinal路径伪造order_id USER_CLAIM。"
    - "argument_binding_refs精确复制形成current target的origin binding：direct order_id、UNIQUE product_description或ordinal candidate_ordinal三者之一；verified_target_ref保持独立。"
    - "自然语言描述询问物流的search_orders→get_order→get_shipment目标链与7.3.4/7.4 target closure一致。"
  artifacts:
    - "Scoped Spec exact get_shipment target-origin binding correction。"
  key_links:
    - "B_C2_W9_UNIQUE_TARGET_GATE → reviewed 02-15R1F → B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT → 02-15R1G。"
---

# Phase 2 Plan 02-15R1F｜Shipment verified-target origin-binding contract

> **EXACT TASK PACKET / W9 SPEC_OWNER_CORRECTION**
>
> 第四次R1实现对照确认：第7.11节要求自然语言描述询问物流经
> `search_orders → get_order → get_shipment`，第7.3.4/7.4节又明确UNIQUE与ordinal
> target分别绑定`product_description`与`candidate_ordinal`；但第7.5节仍把
> `get_shipment.argument_binding_refs`限定为`order_id` binding，现有Gateway同样只
> 接受该形状。禁止Application通过伪造order-id Claim修复。本Packet只由scoped Spec
> owner裁决target-origin binding语义，不修改源码、测试、artifact或Case lifecycle。

## Exact Task Packet

```yaml
task_id: 02-15R1F
goal: 对齐get_shipment与reviewed verified-target origin binding，使direct、UNIQUE和ordinal三条路径各自保留原binding authority并复用同一exact target closure。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-cycle2-w9-shipment-target-binding-contract
base_branch: integration/e2e01-cycle2
base_sha: 10ea5a58352ff06d59da5d7293d5b423588a317b
base_tree: d32a4db85ac5ac739d753325b4e8caadf90dd481
planning_control_base_sha: 10ea5a58352ff06d59da5d7293d5b423588a317b
planning_control_base_tree: d32a4db85ac5ac739d753325b4e8caadf90dd481
worktree_id: e2e01-cycle2-w9-shipment-target-binding-contract
agent_role: tech-lead
writer: cycle2-scoped-spec-owner
pull_request_base: integration/e2e01-cycle2
pull_request_mode: draft until independent exact-head review PASS; never use admin bypass
owned_files:
  - docs/implementation/e2e01-cycle2-implementation-spec.md
forbidden_files:
  - all repository files outside the exact one-file owned_files allowlist
  - src/**
  - tests/**
  - evals/**
  - alembic/**
  - .planning/**
  - AGENTS.md
  - graphify-out/**
canonical_inputs:
  - docs/business-capabilities.md
  - docs/architecture/intent-design-reference.md
  - docs/architecture/tool-calling-design-reference.md
  - docs/architecture/memory-design-reference.md
  - docs/implementation/e2e01-cycle2-implementation-spec.md sections 3.2, 7.3.4, 7.4, 7.5 and 7.11
required_product_blobs:
  AGENTS.md: 5904da48f4e3a2d95e86ffa04ebe29694caf5c0a
  docs/implementation/e2e01-cycle2-implementation-spec.md: b0d3ad29a86365903b1c2c3af3f809556c8a9c2d
dependencies:
  - exact B_C2_W9_UNIQUE_TARGET_GATE = dfcaec66a29e79198e72dad99189bc3886d6aa81
contract_decisions:
  - get_shipment requires one current verified target and exact current target Observation closure
  - argument_binding_refs equals the target's one exact origin InputBinding ref; accepted names are order_id for direct target, product_description for UNIQUE auto target, or candidate_ordinal for ordinal selected target
  - argument order_id must equal verified target order_id; binding value is not promoted or rewritten into an order fact
  - verified_target_ref remains separate from argument_binding_refs and is exact-copied through Gate/AuthorizedCommand/ToolCall
  - no fallback between binding families; wrong name/ref, stale/superseded target, owner/version/Observation drift reject
contract_changes: YES — scoped Spec correction resolves an internal contradiction required by the already-scoped three-tool natural-language Shipment flow.
security_impact: CRITICAL / target-bound Shipment authorization; no authority expansion beyond an existing exact verified target.
eval_impact: CONTRACT ALIGNMENT ONLY — Cases remain CONTRACT_DEFINED; no artifact/Harness/Result mutation.
review_profile:
  planning_review: INDEPENDENT_EXACT_FILE_PASS
  implementation_review: INDEPENDENT_EXACT_FILE_PASS
  reviewer_timeout: 20_SECONDS_MAX; interrupt and narrow immediately on timeout
  targeted_risk_checks:
    - no fabricated order_id Claim or public-summary authority
    - exact target origin binding and verified_target_ref separation
    - direct/UNIQUE/ordinal paths remain disjoint
    - 7.3.4/7.4/7.5/7.11 cross-section alignment
  full_suite_gate: NOT_APPLICABLE_DOCUMENT_ONLY
verification:
  terminology: rg and exact section comparison
  links: repository-local path/link scan
  diff_check: git diff --check 10ea5a58352ff06d59da5d7293d5b423588a317b...HEAD
  allowlist: exact one file
required_checks:
  - exact base/tree/blob/protection/branch absence/clean preflight PASS
  - one-file Spec diff removes the contradiction without claiming implementation
  - cross-file impact scan records Core/Application follow-up as 02-15R1G/R1, not silent alignment
  - bounded independent exact-head review PASS
done_when:
  - reviewed one-file PR merges as B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT
  - Core correction may freeze only from the real successor; Cases remain CONTRACT_DEFINED
rollback:
  - close before merge or revert exact documentation commit before Core/Application depend on it
  - never repair by weakening verified-target closure or inventing order_id InputBinding
handoff_to: tech-lead
handoff_format: .planning/phases/02-cycle-2-e2e-01/02-15R1F-PLAN.md#handoff
output_barrier: B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT
```

## Tasks

1. RED：列出7.3.4/7.4/7.5/7.11的exact矛盾与安全影响。
2. GREEN：只修改scoped Spec，定义target-origin binding矩阵及禁止fallback。
3. VERIFY：术语、跨节对照、one-file containment与20秒bounded review。

## Handoff

报告exact identity、one-file diff、三条binding family矩阵、review与
`B_C2_W9_SHIPMENT_TARGET_BINDING_CONTRACT`；明确Core/Application/DB/HTTP/Eval均未推进。
