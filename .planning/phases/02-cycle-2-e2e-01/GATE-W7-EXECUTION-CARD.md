# Gate W7｜Runtime mapper and Renderer execution card

状态：`B_C2_INFRA_CONFIRMED / 02-12_PLANNING_REVIEW`

## Exact input

- `B_C2_INFRA = 6217b2213d576dab052dc70e223f8cf02c9c577b` / tree
  `7de3e6db75ebc58fcf4d15c46538ded424564d8c`。
- W6 canonical gate：`2840 passed, 1 deselected, 12 warnings`；依赖同步、两套
  PostgreSQL service、migration head均PASS。
- `02-07/02-11R/02-11` feature、fix与bounded reviews均已reviewed merge。
- Case lifecycle：`E2E01-02/03/05/06 = CONTRACT_DEFINED`；Phase 2 Harness dispatch
  与Eval Result仍为零。
- User ruling：完成W6后继续W7/W8/W9，有问题按Integrator建议修复。

## Ordered dispatch

```text
review and merge exact 02-12 Plan
→ create one eight-file Runtime Worktree from B_C2_INFRA
→ focused + neighbor + compile/diff
→ bounded exact-head review and latest-integration identity/overlay
→ serial merge and freeze B_C2_RUNTIME
```

## Review profile

- `02-12 = TARGETED_RUNTIME`；只写AgentRunService、RunResultMapper、deterministic
  Renderer、presentation contracts/policy与三个component tests。
- reviewer最长30秒；超时立即中止并缩窄，不运行测试或history扫描。
- W7不运行canonical full，不dispatch Harness，不生成Eval Result，不推进Case。

## Stop conditions

出现canonical contract/Port/record change、allowlist扩张、Phase 1 mapper语义复制或
漂移、first-match precedence、unmapped/overlap、模型生成事实、private/stale/foreign
字段进入context/Renderer/outbound、order-only调用shipment、ordinal重跑search、
obsolete/RM-I05出站、exact base/tree/blob/protection不相等，立即停止并裁决。

## Current gate

`02-12` 只在exact Plan与本Card获得independent `PASS`并通过planning PR合并后可
dispatch。feature必须保持八文件边界、latest-tree复验与bounded review；Cases全程
保持`CONTRACT_DEFINED`。
