# Gate W5｜02-10 physical migration execution card

状态：`W4_COMPLETE / B_C2_LEAVES_CONFIRMED / 02-10_PLAN_REVIEW`

## Exact input

- Dependency barrier：`B_C2_LEAVES = fc3a603b963ea54c597e00847ac816050bd007bf` /
  tree `01b33357c15d16ee2c1dc15194254f86dd07252c`。
- Current integration/status successor：`21e8b6b15461f1c0513194213cd9b05f1e74c515` /
  tree `041c55e8b6e96ac3100d48376a80c75aaff1e43a`。
- W4 exit：integration-focused `726 passed`、neighbor-only `877 passed`、
  Phase 1 direct regression `398 passed`；canonical full未运行，Case仍`CONTRACT_DEFINED`。
- `02-10` implementation branch、Worktree与`20260731_0004`在freeze preflight均不存在。

## Review profile

`TARGETED_MIGRATION`：只审exact migration/model/test diff、两条升级路径、complete
prevalidation/atomic cutover、physical admission、Phase1 byte identity和downgrade fence。
不复审W1–W4，不运行canonical full；W6 exit拥有下一次full。

## Packet freeze

```text
02-10 planning review PASS
→ exact four-file implementation
→ focused + neighbor + two upgrade paths
→ exact-head review PASS
→ latest-integration overlay PASS
→ reviewed PR merge
→ B_C2_PHYSICAL
```

## Stop conditions

发现migration无法唯一转换、需要修改application codec/canonical owner、扩大allowlist、
修改历史revision、出现零转换之外的partial failure，或BLOCK/HIGH无法在四文件内关闭，
立即停止并裁决。

## W5 exit

只记录empty DB与Phase1 head两条upgrade path、focused/neighbor及downgrade fence；
不运行canonical full，不启动W6实现，不推进Case lifecycle或Phase2 Eval Result。
