---
phase: 01-cycle-1-e2e-01
plan: 07E
subsystem: request-understanding-v2-application-persistence-codec-expand
tags:
  - request-understanding
  - application
  - persistence
  - versioning
  - security
status: complete_evidence_indexed
completed_at: "2026-07-28T21:03:56+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-28"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 034cf57228c4a9da4764b0c7322dc5d34652a09c
planning_merge: f08098c23ee10b133b5c7da015159ed84fe72754
planning_correction_merge: 3c90cd70a2bc23a8e5e5fc9f89bfacfc5ed3ae90
published_head: a412f92ab953719b0663727fc9d7fca8e8748419
integration_merge: 294ada386ec160ec2a48fc8883b5a38f1880e4ba
key_files:
  modified:
    - src/mini_agent/application/persistence.py
    - tests/component/application/test_persistence_contract.py
metrics:
  feature_commits: 4
  files_changed: 2
  focused_tests_passed: 233
  full_tests_passed: 1671
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07E｜Request Understanding v2 Application Persistence Codec Expand Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引 01-07E `CODEC_EXPAND` 的已合并实现与可复现证据，不拥有 Request Understanding、Memory、physical persistence、Runtime、Provider/Eval、active switch 或 lifecycle 语义。规范性内容仍由 [Thin Slice owner](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)、[execution map](../../../docs/implementation/e2e01-thin-slice-multi-agent-plan.md) 与 [01-07E Plan](01-07E-PLAN.md) 持有。

## Outcome

`01-07E` 已从 reviewed exact `B_F` 增加 additive、non-routable Application codec surface：

- immutable `P0_RECORD_SCHEMA_VERSION_CATALOG` 恰含 18 个 exact `(record_code, schema_version)` pair、17 个 code，只有 Request Understanding 同时拥有 v1/v2；17 个 v1 value直接复用 active registry exact spec object；
- `encode_persistence_record_versioned` / `decode_persistence_record_versioned` 只接受 caller 显式 exact pair，不推断、alias、default/latest、try-other、rewrite、backfill或fallback；
- RU v2 形成 exact 8+4 projection、version-bound accepted child spec、deterministic reference collapse、candidate/decision/accepted closure 与按 candidate 顺序验证的 per-Task state-version chain；
- 非字符串 outer schema metadata、source/model state、identity/link/child/closure tamper与version confusion均产生 bounded error；17个v1 pair的versioned错误类别保持legacy parity；
- 60 个既有 v1 top-level definition 与 legacy registry/API/consumer保持不变。

PR #74 的 reviewed serial merge形成 F/E共同、不可路由的 exact barrier：

- `B_FE_EXPAND = 294ada386ec160ec2a48fc8883b5a38f1880e4ba`
- tree `97b0928100edae965004338d52ce87dff7325fd1`

该 barrier 已允许 01-07I / 01-07P 从同一 exact SHA 分别规划 Application Port与migration-chain dependency expand；本次状态对齐不创建第二道barrier，也不阻塞其启动。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / head / merge | [#72](https://github.com/weijie567/mini-agent/pull/72) / `fb2a4407753ac2153dbe9ea3670a6d7a0205341a` / `f08098c23ee10b133b5c7da015159ed84fe72754` |
| Plan correction PR / head / merge | [#73](https://github.com/weijie567/mini-agent/pull/73) / `710588fd949c7abfdf400b545dafebb88e2ffd52` / `3c90cd70a2bc23a8e5e5fc9f89bfacfc5ed3ae90` |
| Final Plan blob | `7dd2c9047bebcb9ad29435900ee0030922a5973a` |
| Execution base | `034cf57228c4a9da4764b0c7322dc5d34652a09c`（`B_F`） |
| Feature head / tree | `a412f92ab953719b0663727fc9d7fca8e8748419` / `294d455924e03cc0bab605c07dafb271dae415f6` |
| Latest-integration overlay base / head / tree | `3c90cd70a2bc23a8e5e5fc9f89bfacfc5ed3ae90` / `4c73026142337af1b9d0118bfe57f33fda972228` / `97b0928100edae965004338d52ce87dff7325fd1` |
| Feature PR / integration merge / tree | [#74](https://github.com/weijie567/mini-agent/pull/74) / `294ada386ec160ec2a48fc8883b5a38f1880e4ba` / `97b0928100edae965004338d52ce87dff7325fd1` |
| Scope | exact 4 commits、2 owned files；RED → GREEN → 2 review fixes |
| RED / focused / full suite | `138 passed / 66 expected failures`；final `233 passed`；`1671 passed, 1 deselected, 12 warnings` |
| Protected-v1 oracle | `definitions=60 changed=0 rebound=0 mutants=12/12-rejected` |
| Catalog / legacy / consumer | `18 entries / 17 codes / RU dual`；legacy `17/66/7/45`；public symbols只在owned source/test出现 |
| Independent review | 首轮 `CRITICAL/HIGH/MEDIUM = 0/2/1`并BLOCK；修复后feature与latest overlay均 `0/0/0`、`PASS / MERGE` |

`B_FE_EXPAND` 上两个 owned blob 为：

- `persistence.py = 1e085e066847b69fd4f49e6b8ce6c732391644b3`
- `test_persistence_contract.py = 5d74dc57878d19bbdfe8e0b537f65b4bdfe8e4b7`

## Security, Eval and Lifecycle Boundary

- **Security:** exact pair lookup先于source/payload处理；version confusion、source substitution、undeclared/private state、dangling child、Task chain tamper与raw diagnostic均fail closed。Codec是zero-I/O纯函数，成功不授予身份、owner scope、provenance或readiness。
- **Eval:** 只新增 Application Component contract；没有 Dataset、Grader、Trajectory、E2E Result、threshold或 Case lifecycle 变化。
- **Lifecycle:** `requirements_completed` 为空，canonical Case / Requirement与派生checkbox继续保持 `0/8`。
- **Nonclaims:** active registry、legacy API、PostgreSQL schema/reader、Runtime、Provider/Eval consumer、v1 contract与readiness均未切换。

## Self-Check: PASSED

- exact lineage、Plan correction、RED/GREEN/fix history、feature/overlay双review、merge tree与测试证据均可复现；
- two-file allowlist、60-symbol oracle、catalog、consumer与full gate闭合；
- `B_FE_EXPAND`只作为non-routable additive barrier，不被描述为真实纵向链、Case PASS或产品完成。
