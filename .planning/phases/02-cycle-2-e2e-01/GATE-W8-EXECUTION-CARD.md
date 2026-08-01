# Gate W8｜Graders and offline Harness machinery execution card

状态：`B_C2_RUNTIME_CONFIRMED / 02-14_PLANNING_REVIEW`

## Exact input

- `B_C2_RUNTIME = d02b8f2e43431b1f8f6a615b13f4e792ea250bde` / tree
  `8bd3ba88a8ae4bfdd0a16e3e0ad0e82c739f6a84`。
- PR #264/#265 已reviewed完成W7 planning / implementation；focused `85 passed`、
  neighbor `1346 passed`、compile/diff/containment均PASS。
- Case lifecycle：`E2E01-02/03/05/06 = CONTRACT_DEFINED`；Phase 2 Harness dispatch
  与Eval Result仍为零。
- 只读预审确认现有whole-batch lifecycle检查已位于nonce、Provider、SUT、Trace、
  Grader、Result之前；W8强化但不绕过该顺序。

## Ordered dispatch

```text
review and merge exact 02-14 Plan
→ create one four-file Eval Worktree from B_C2_RUNTIME
→ focused + neighbor + compile/diff
→ bounded exact-head review and latest-integration identity/overlay
→ serial merge and freeze B_C2_EVAL_MACHINERY
```

## Review profile

- `02-14 = TARGETED_EVAL_MACHINERY`；只写graders、Harness与两个既有测试文件。
- reviewer最长20秒；超时立即中止并缩窄，不运行测试或history扫描。
- W8不运行canonical full，不dispatch Phase 2 SUT/Provider/Trace/Grader/Result chain，
  不生成lifecycle-valid Result，不推进Case。

## Stop conditions

出现canonical contract/lifecycle/artifact change、allowlist扩张、Phase 1 registry漂移、
宽松grader fallback、Case ID/Provider/SUT输出成为profile authority、Provider/script/
expectation补造SUT evidence、raw ordinary Trace泄露、OA-10伪造Result或状态、lane/
lifecycle hold绕过、exact base/tree/blob/protection不相等，立即停止并裁决。

## Current gate

`02-14` 只在exact Plan与本Card获得independent `PASS`并通过planning PR合并后可
dispatch。feature必须保持四文件边界、latest-tree复验与bounded review；Cases全程
保持`CONTRACT_DEFINED`。
