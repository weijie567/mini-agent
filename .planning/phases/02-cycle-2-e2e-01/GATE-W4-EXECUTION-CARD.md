# Gate W4｜Leaves execution card

状态：`W4_BATCH_A_AND_02_08_AND_R1_R2_R3_MERGED / B_C2_02_09_READY / 02-09_REFROZEN_PLAN_REVIEW`

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
- W4 planning provenance PR #228 已 merge 为
  `2e85326ecace4840d5b88bf4d273e5753213a84e`；当时四个原 W4 Packet 都以
  `B_C2_W4_READY` 为 product base。02-09 的该历史 freeze 已被当前 R1/R2/R3 correction
  与真实 successor refreeze替换；Case lifecycle始终保持 `CONTRACT_DEFINED`。
- 02-06 implementation PR #229 已 reviewed merge 为
  `B_C2_CODEC = 6514c7d0ebdd7c34fb2ec531460053ee21095fdf` / tree
  `8f901e3f7cf1d01fe2dc5e150bd7ef1738dd5cbe`；02-13 PR #230 随后 merge 为
  `B_C2_EVAL_BUNDLE = 15d3bd41f83b0ae42e01aae48e0682d1d1ba66ed` / tree
  `f91732eabf3672961681383a92cf578b999be604`。两次 merge tree 都与 reviewed
  latest-integration overlay tree 相等。
- 02-09 owner-gap ruling PR #231 已 reviewed merge 为
  `B_C2_RECOVERY_OWNER_RULING = 0cc780ff34793a17c202fdae499b63601845a4ac` /
  tree `bef2ce71b1a7f45ef99fbffd0ae16d29163a6692`。02-08 PR #232 再 merge 为
  `B_C2_RU_ROUTING = d0f37e2d064689bfe1ba708db57b015ee8d2af29` / tree
  `252a092b962327471facbf34b163536fc4d41ea3`，与 reviewed overlay tree 相等。
- 02-09R1 planning PR #233 与 implementation PR #234 已 reviewed merge 为
  `B_C2_RECOVERY_CORE = fe627a5d81d909e096e9e60773fcca03b51f84be` / tree
  `42767c8535dbc05837ab9dabeee2c1432813e0fb`，与 reviewed overlay tree相等；
  focused `144 passed`、neighbor `558 passed`、compile/diff通过，full未运行。
- 02-09R2 planning PR #235、CREATED-path correction PR #236 与 implementation
  PR #237 已 reviewed merge 为 `B_C2_RECOVERY_APP_CONTRACT =
  46a0b1f67153846dee6441ce47b7b5d5de4bc4d7` / tree
  `9c58a0885c93146017d352a5df11b48f5f9240af`，与 reviewed overlay tree相等；
  初审发现的 CREATED/no-attempt shared v2 Port BLOCK 已修复并 residual `PASS`，
  focused `416 passed`、neighbor `576 passed`、compile/diff通过，full未运行。
- 02-09R3 planning PR #238 与 implementation PR #239 已 reviewed merge；R3 初审
  发现 decision spec 泄漏到 unversioned global catalog，修复后仅保留
  `tool_call_record.p0.v2` version-keyed registration，legacy counts恢复为3/8。真实
  `B_C2_02_09_READY = cdf8c194ff80c9f47d6587bef9b5b386f29e5341` / tree
  `2e82f1b9708f44df1bec7b16eaa7774e55d60ed3`，与 reviewed overlay tree相等；
  focused `243 passed`、neighbor `560 passed`、compile/diff通过，full未运行。

## Historical W4 preflight blocker and owner ruling

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

## Confirmed 02-09 recovery owner gap

02-09 已从 exact `B_C2_W4_READY` 完成 preflight，但只读 owner review 证明现有
`Cycle2RuntimeRecordPort` / command 与 Core closed matrix不能共同表达：

- 保留 unfinished attempt 而只终止 parent ToolCall 的 restart closure；
- durable `ToolRetryRecoveryDecisionRecordV2` 与 recovered second fence 的同一 CAS；
- attempt 1 保持 `RETRY_SCHEDULED` 时的 `RUN_BUDGET_EXHAUSTED` parent terminal。

历史 02-09 Worktree 保持 clean、没有 source change 或 implementation commit；旧 02-09
Plan 曾正确标记 `BLOCKED / HISTORICAL W4 FREEZE`。PR #231 已裁决 decision 为 ToolCall v2
logical child、budget evidence 来自 owner-scoped reader并在 CAS 内重算、budget terminal
保留 attempt 1 并投影原 `FAILED / TIMED_OUT`。correction 必须按
`02-09R1 → 02-09R2 → 02-09R3` single-writer 串行执行；每个后继 Plan 只能用前驱真实
reviewed merge SHA/tree重冻结，不得预测。该链现已完成；原 02-09 已从真实
`B_C2_02_09_READY` 重冻结，等待独立 planning review。

## Packet freeze 与批次

旧 02-06 内容已从真实 barrier 完整重冻结；02-08/09/13 exact Plan亦由Integrator在
dedicated planning-status Worktree逐个单写。四份 Plan 必须分别取得全新 independent
exact-file planning review `PASS`，并通过同一 planning PR 合并为 provenance；此前不得
创建对应实现 branch / Worktree。

前三个原 W4 Packet 的历史 frozen product input 为：

- `B_C2_W4_READY = 5f2fa6d28575bcdcaf8a4c650469acc7dd19b7de`
- tree `174fbebcfa622336ffeade113cfae74a5611edae`
- 最终 02-09 的当前 frozen product input 独立为
  `B_C2_02_09_READY = cdf8c194ff80c9f47d6587bef9b5b386f29e5341` / tree
  `2e82f1b9708f44df1bec7b16eaa7774e55d60ed3`
- 02-09 replacement implementation branch
  `codex/e2e01-cycle2-read-executor-recovery-r1` 在 refreeze preflight 为 local / remote
  `NOT_FOUND`；owned-file overlap仍为零

```text
Batch A: 02-06 Exact persistence codec || 02-13 Eval bundle/loader — MERGED
Batch B: 02-08 Request understanding/routing — MERGED
W4R: 02-09R1 + 02-09R2 + 02-09R3 — MERGED
W4 resumed: refrozen 02-09 executor/recovery — PLAN REVIEW
```

- writer 并发上限为 2；每个 Packet 独立 branch / Worktree；owned files 两两无交集。
- 实际/后续串行 merge：`02-06 → 02-13 → owner ruling → 02-08 → 02-09R1 →
  02-09R2 → 02-09R3 → refrozen 02-09`。
- 02-06/13/08 保留各自已 reviewed 的历史 product base；最终 02-09 只使用真实
  `B_C2_02_09_READY`，不得复用 `B_C2_W4_READY`、planning-control SHA 或猜测 successor。
  merge 前必须在 latest integration 上形成 reviewed overlay。

## Review profiles

| Packet | implementation review | Per-packet full suite |
|---|---|---|
| `02-06` | `TARGETED_CONTRACT` | `NOT RUN` |
| `02-08` | `TARGETED_SECURITY` | `NOT RUN` |
| `02-09` | `TARGETED_HIGH_RISK` | `NOT RUN` |
| `02-13` | `TARGETED_EVAL_INTEGRITY` | `NOT RUN` |
| `02-09R1` | `TARGETED_CORE_RECOVERY` | `NOT RUN` |
| `02-09R2` | `TARGETED_ATOMIC_RECOVERY_CONTRACT` | `NOT RUN` |
| `02-09R3` | `TARGETED_CHILD_CODEC` | `NOT RUN` |

每个 Packet 只审 exact base/head/ancestry/commit/allowlist、当前 diff、直接 owner、
focused/neighbor tests 与 own security invariants。已 reviewed upstream barrier 作为
imported evidence，不重复 W3 式全量审计或 canonical full。finding remediation 只重跑
受影响 focused/neighbor；最终候选稳定后再做 final exact-head review。

## Stop conditions

本卡已记录的 W3R 与 W4R correction、25-slot / 15-wave-label amendment 已由当前用户
“有问题先修复”指令收口；它们不再是 stop condition。除此以外，出现新的 contract
change、owner conflict、allowlist
扩大、Wave/Packet 数量变化、无法在原 Packet 内关闭的 BLOCK/HIGH、exact barrier
不一致、02-06 conversion 无法唯一表达、02-13 lifecycle activation 证据不足或任一
W4 allowlist overlap，立即停止。

## W4 exit

原四个 reviewed implementation 中的 02-06/13/08、W4R 三个 correction 与最终
refrozen 02-09 全部串行合并后才冻结 `B_C2_LEAVES`。只运行 W4
integration-focused/neighbor checks 与 Phase 1 直接相关回归；不运行 canonical full、
Phase 级全面深审、Phase 2 Harness/Eval Result，也不推进 Case lifecycle。
