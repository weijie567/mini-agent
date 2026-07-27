---
phase: 01-cycle-1-e2e-01
plan: 07C
subsystem: request-understanding-durable-semantics
tags:
  - request-understanding
  - persistence
  - versioning
  - security
status: complete_evidence_indexed
completed_at: "2026-07-28T02:29:17+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-28"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 3f0753f7bef87fc02f314e28fe8b07860a819701
planning_merge: 79ae0a921cb8a6ff64f308ddf377c93354701cf8
published_head: b39a0374dbe55321da630c74479ba5e4c0e31785
integration_merge: 327b39da45cdcf564609a5385d52c4264da2c669
key_files:
  modified:
    - docs/architecture/intent-design-reference.md
metrics:
  feature_commits: 1
  files_changed: 1
  full_tests_passed: 1493
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07C｜Request Understanding Durable Semantic Ruling Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 01-07C owner ruling 与可复现证据，不拥有 Request Understanding、Thin Slice mapping、DTO、codec、物理持久化、Eval 或 lifecycle 语义。规范性内容仍由 [Intent owner](../../../docs/architecture/intent-design-reference.md) 与 [01-07C Plan](01-07C-PLAN.md) 持有。

## Outcome

`01-07C` 已在 Intent owner 单文件范围内冻结 durable Request Understanding 的语义边界：

- `run_id` 仅由服务端可信绑定，不进入模型输出，也不要求模型回显；`message_ref` 仍须与服务端值精确匹配；
- durable contextualization projection 本身必须保存，不得从普通上下文重新生成、猜测或补造；
- actual candidate、validation decision、accepted / rejected closure、child refs 与可信 `created_at` 形成 exact durable closure；
- logical record version 与 model-output schema version 是独立版本轴；exact-version、compatibility、migration、rollback 与 readiness 均 fail closed；
- 本 Packet 不分配 Thin Slice exact version，不定义 DTO、registry、codec、table、migration 或 Runtime consumer；这些仍由 01-07D/E/F 后续 owner Packet 关闭。

这些是 owner-document contract 证据，不是 Request Understanding runtime persistence、真实 HTTP / PostgreSQL、Trajectory / E2E Result 或 Case PASS。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Original Plan PR / merge | [#46](https://github.com/weijie567/mini-agent/pull/46) / `f1bf2b3f2c8cd9fa61711dde7c0e94365c54b583` |
| Public-path correction PR / merge | [#49](https://github.com/weijie567/mini-agent/pull/49) / `267fd0eba99b892b2b02c4cb99e40e7233856c11` |
| Superseded feature attempt | [#51](https://github.com/weijie567/mini-agent/pull/51) closed Draft；exact-head review `CRITICAL / HIGH / MEDIUM = 0 / 1 / 1` |
| r1 Plan correction PR / merge | [#52](https://github.com/weijie567/mini-agent/pull/52) / `79ae0a921cb8a6ff64f308ddf377c93354701cf8` |
| r1 Plan blob | `66a3a974f5d7408239b8ba3691abdb0c1781fa63` |
| Execution base / parent | `3f0753f7bef87fc02f314e28fe8b07860a819701` |
| Local feature head / remote reviewed head | `db648c5900459e711144a43d6438ce2232050d1d` / `b39a0374dbe55321da630c74479ba5e4c0e31785` |
| Remote tree / owner blob | `c35ba0736b99d045f9290569ac739dea252b85e4` / `456be9c7d7884e2a58c4d07b867765ed336aa6f5` |
| Feature PR / merge | [#53](https://github.com/weijie567/mini-agent/pull/53) / `327b39da45cdcf564609a5385d52c4264da2c669` |
| Project Direction owner status alignment | [#54](https://github.com/weijie567/mini-agent/pull/54) / `ffcc562487be458073f4229e4f6f7b353bc8d9e0`；status-only，不替换`B_CG` |
| Latest-integration overlay | base `79ae0a921cb8a6ff64f308ddf377c93354701cf8` / head `7c1102619e283e3cdbaeb171541f32c70d8d4403` / tree `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887` |
| Integration merge / tree | `327b39da45cdcf564609a5385d52c4264da2c669` / `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887` |
| Scope | exact one commit、one owned file；`170+ / 11-` |
| Feature / independent review / overlay tests | 各 `1493 passed, 1 deselected, 12 warnings` |
| Independent review | superseded findings已关闭；r1 feature与latest overlay均 `PASS / CRITICAL-HIGH-MEDIUM = 0/0/0` |

Local 与 remote feature commit 仅 metadata 不同；parent、tree、owner blob 与内容相同。旧 PR #51 未 force-push、rebase 或改写，保留为 review evidence。

## Post-merge Gate

在共同 exact integration merge `327b39da45cdcf564609a5385d52c4264da2c669` 上：

- default full offline suite 为 `1493 passed, 1 deselected, 12 warnings`；
- Graphify 先因增量候选缩减触发 shrink guard，随后执行受控全量安全重建；最终为 `3098 nodes / 16904 edges / 68 hyperedges / 135 communities`，`built_at_commit` 精确绑定该 merge；
- Graphify health 记录 `699` 个 dangling endpoint edge、`687` 组 directed与`713` 组 undirected collapse candidate，且 `missing endpoint = 0`、`self-loop = 0`；按 Graphify 规则公开警告但不伪装为全绿；
- stale marker 不存在，tracked integration Worktree clean。

## Security, Eval and Lifecycle Boundary

- **Security:** trusted identity、owner scope、raw Provider / Prompt / Token /诊断与 PII 边界没有扩大；可信 `run_id` 不由模型生成或覆盖。
- **Eval:** 仍缺 01-07D exact mapping、01-07E codec、01-07F Core consumer，以及后续真实 Runtime / PostgreSQL / HTTP / Eval mapper 纵向证据。
- **Lifecycle:** `requirements_completed` 为空；`E2E01-01/04` 与派生 checkbox 继续保持 `CONTRACT_DEFINED / 0/8`。与 01-07G 共同完成后，Task Packet 证据口径从 `14/29` 更新为 `16/29`，不等于产品或 Phase 完成 55.2%。
- **Handoff:** `327b39d...` / tree `49ad0f3...` 是 `B_CG`；01-07D 与 01-07H 必须分别通过独立 single-target planning PR 签发同一 execution base，之后才可在互不重叠的 Worktree 并行写入。

## Self-Check: PASSED WITH RECORDED GRAPH HEALTH WARNINGS

- feature lineage、exact scope、review、merge、测试与 Graphify 证据均有精确引用；
- 已显式保留 DTO / mapping / codec / Runtime / Infra / Eval / lifecycle 缺口；
- 未把 owner ruling、Graphify 警告或 Component 测试描述为完整切片通过。
