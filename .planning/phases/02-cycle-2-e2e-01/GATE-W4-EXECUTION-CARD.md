# Gate W4｜Leaves execution card

状态：`W3R_COMPLETE / B_C2_W4_READY_CONFIRMED / W4_PLAN_REFREEZE_REVIEW`

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
- owner-ruling PR [#221](https://github.com/weijie567/mini-agent/pull/221) 已按 branch
  protection squash merge；`B_C2_W3R_RULING = ed61f4d4da9c75386aa96857a5e77e06de4c4804`，
  tree `02c06f70459cf9593946c599a2de33d1c5a15a91` 与 reviewed remote-head tree 相等。
- 02-02R planning PR #222 与 implementation PR #223 已 reviewed merge；真实
  `B_C2_INPUT_BINDING_V2 = 5efd8fabc5c7af5100e10535e983c424e3fd7ad4`，tree
  `5a5b3081bb816f5b276b53de9922173290c9f9ca` 与 reviewed overlay tree 相等。
- 02-04R planning PR #224 与 implementation PR #225 已 bounded
  feature/residual/latest-integration overlay review `PASS` 并 merge；真实
  `B_C2_SELECTED_TARGET_GATEWAY = 53e36aa88fab1ab99d2b076a1d731f63dced064a`，
  tree `3f9852e825a69c9ceb8a19e18c810263ef74349e` 与 reviewed overlay tree 相等。
- 02-05R planning PR #226 与 implementation PR #227 已 bounded
  feature/residual/latest-integration overlay review `PASS` 并 merge；两个 reviewer HIGH
  （caller-derived UUIDv4 与 module-level issuance token）均在原 Packet 内关闭。真实
  `B_C2_W4_READY = 5f2fa6d28575bcdcaf8a4c650469acc7dd19b7de`，tree
  `174fbebcfa622336ffeade113cfae74a5611edae` 与 reviewed overlay tree相等；focused
  `409 passed`、neighbor `363 passed`，full/migration/Runtime/Infrastructure/Eval
  lifecycle 均未运行或推进。

## Confirmed W4 preflight blocker and owner ruling

W4 preflight 已确认旧 barrier 上没有 existing-Task continuation InputBinding writer；
ordinal binding 若先落盘会推进 Task version 并使 CandidateSet expected version自失效；
Gateway 又只接受 direct `order_id` Claim，无法授权 selection 后的 `get_order`；Claim
name 同时存在 `shipment_not_received` / `not_received_claim` 漂移。

用户已授权先修复再开始 W4。当前 owner ruling 固定：

- 保留 v1 owner model，新增 inactive `InputBindingV2`，并以 exact order-id identity
  conversion 演进到 `input_binding_record.p0.v2`；
- ordinal binding 与 selection effect 在同一个 CAS 中持久化；
- `get_order` 保留 direct binding 路径；selected path 使用
  `argument_binding_refs=[ordinal_input_binding_ref]` 与独立
  `verified_target_ref=selected_target_ref`。`GateDecisionRecord` 演进到 v2，
  Gate/Authorized command/ToolCall exact-copy target；`get_shipment` 同样禁止 mixed refs；
- Claim canonical name 统一为 `shipment_not_received`；
- 增加 `02-02R/02-04R/02-05R` 与 `W3R`，最大 writer 仍为 2。

02-05R 已关闭 exact Application dependency与受控 selected-target issuance。真实
`B_C2_W4_READY` 已形成；四个 W4 implementation Packet 均只能以该 exact SHA/tree作为
product base，不能以当前 planning-control successor 或未来串行 merge successor替代。

## Packet freeze 与批次

旧 02-06 内容已从真实 barrier 完整重冻结；02-08/09/13 exact Plan亦由Integrator在
dedicated planning-status Worktree逐个单写。四份 Plan 必须分别取得全新 independent
exact-file planning review `PASS`，并通过同一 planning PR 合并为 provenance；此前不得
创建对应实现 branch / Worktree。

四个 Packet 的 frozen product input 统一为：

- `B_C2_W4_READY = 5f2fa6d28575bcdcaf8a4c650469acc7dd19b7de`
- tree `174fbebcfa622336ffeade113cfae74a5611edae`
- implementation branches在本次 refreeze preflight均为 local / remote `NOT_FOUND`
- owned-file intersections两两为零；new Cycle 2 Eval artifact paths在base为`NOT_FOUND`

```text
Batch A: 02-06 Exact persistence codec || 02-13 Eval bundle/loader
Batch B: 02-08 Request understanding/routing || 02-09 executor/recovery
```

- writer 并发上限为 2；每个 Packet 独立 branch / Worktree；owned files 两两无交集。
- 建议串行 merge：`02-06 → 02-13 → 02-08 → 02-09`。
- 四个 implementation Packet 的 product `base_sha` 都必须重冻结为真实
  `B_C2_W4_READY`；不得继续使用 `B_C2_APP_CONTRACT` 或猜测 successor。每次 merge
  前必须在 latest integration 上形成 reviewed overlay。

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

本卡已记录的三项 correction、W3R 与 22-slot amendment 已由当前用户指令授权；它们
不再是 stop condition。除此以外，出现新的 contract change、owner conflict、allowlist
扩大、Wave/Packet 数量变化、无法在原 Packet 内关闭的 BLOCK/HIGH、exact barrier
不一致、02-06 conversion 无法唯一表达、02-13 lifecycle activation 证据不足或任一
W4 allowlist overlap，立即停止。

## W4 exit

四个 reviewed PR 全部串行合并后才冻结 `B_C2_LEAVES`。只运行 W4
integration-focused/neighbor checks 与 Phase 1 直接相关回归；不运行 canonical full、
Phase 级全面深审、Phase 2 Harness/Eval Result，也不推进 Case lifecycle。
