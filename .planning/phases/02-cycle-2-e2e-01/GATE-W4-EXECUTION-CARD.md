# Gate W4｜Leaves execution card

状态：`W3_REVIEWED_MERGE_CONFIRMED / W4_PACKET_FREEZE_IN_PROGRESS`

## Exact input

- `B_C2_APP_CONTRACT = 86d1b8357f817882b017e5c4306ec855e0b288e6`
- tree `b27f5f805c85e8ce76c30be254a004cb5f127b4e`
- W3 planning PR [#218](https://github.com/weijie567/mini-agent/pull/218) 与
  implementation PR [#219](https://github.com/weijie567/mini-agent/pull/219) 已 merge。
- PR #219 / squash message 持久记录 feature 与 latest-integration overlay review
  `PASS`、`0 BLOCK / 0 HIGH`、两个 `MEDIUM CLOSED`；GitHub review/comment/check
  object 为空，因此原始 Codex reviewer transcript 为 `NOT_FOUND`，不得改写为
  GitHub approval。
- merge tree 与 reviewed overlay tree 相等，W3 exact product diff 仅 02-05 四文件。

## Packet freeze 与批次

四个 exact Plan / Task Packet 必须逐个在 dedicated planning-status worktree 中由
Integrator 单写，并分别取得全新 independent exact-file planning review `PASS`；此前
不得创建对应实现 branch / Worktree。

```text
Batch A: 02-06 Exact persistence codec || 02-13 Eval bundle/loader
Batch B: 02-08 Request understanding/routing || 02-09 executor/recovery
```

- writer 并发上限为 2；每个 Packet 独立 branch / Worktree；owned files 两两无交集。
- 建议串行 merge：`02-06 → 02-13 → 02-08 → 02-09`。
- 四个 implementation Packet 的 product `base_sha` 都是 exact
  `B_C2_APP_CONTRACT`；planning provenance 只推进 integration control head，不改变
  product base。每次 merge 前必须在 latest integration 上形成 reviewed overlay。

## Review profiles

| Packet | implementation review | Per-packet full suite |
|---|---|---|
| `02-06` | `TARGETED_CONTRACT` | `NOT RUN` |
| `02-08` | `TARGETED_SECURITY` | `NOT RUN` |
| `02-09` | `TARGETED_HIGH_RISK` | `NOT RUN` |
| `02-13` | `TARGETED_EVAL_INTEGRITY` | `NOT RUN` |

每个 Packet 只审 exact base/head/ancestry/commit/allowlist、当前 diff、直接 owner、
focused/neighbor tests 与 own security invariants。已 reviewed upstream barrier 作为
imported evidence，不重复 W3 式全量审计或 canonical full。finding remediation 只重跑
受影响 focused/neighbor；最终候选稳定后再做 final exact-head review。

## Stop conditions

出现以下任一项立即停止：contract change、owner conflict、allowlist 扩大、Wave/Packet
数量变化、无法在原 Packet 内关闭的 BLOCK/HIGH、exact barrier 不一致、02-06 conversion
无法唯一表达、02-13 lifecycle activation 证据不足或任一 W4 allowlist overlap。

## W4 exit

四个 reviewed PR 全部串行合并后才冻结 `B_C2_LEAVES`。只运行 W4
integration-focused/neighbor checks 与 Phase 1 直接相关回归；不运行 canonical full、
Phase 级全面深审、Phase 2 Harness/Eval Result，也不推进 Case lifecycle。
