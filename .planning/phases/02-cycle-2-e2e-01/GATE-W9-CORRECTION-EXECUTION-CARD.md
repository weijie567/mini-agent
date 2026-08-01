# Gate W9｜Owner correction execution card

状态：`B_C2_EVAL_MACHINERY_CONFIRMED / 02-15R0_PLANNING_REVIEW`

## Exact input

- `B_C2_EVAL_MACHINERY = d6fdcbb3cdd4e6bb41fb2ae0b1ff5b80629b4efb` /
  tree `8ab6f2aeab53bfae73edff219cab70623c437ebc`。
- PR #268/#269 已reviewed批准W9在原wave内串行`02-15R0→R1→R2→02-15`，
  32 slots / 16 wave labels。
- Case lifecycle仍为`CONTRACT_DEFINED`；Phase 2 Harness dispatch与Result为零。

## Ordered dispatch

```text
02-15R0 exact Spec seed contract → review/merge B_C2_W9_SEED_CONTRACT
→ refreeze 02-15R1 Application normal entry → review/merge
→ refreeze 02-15R2 Infrastructure normal evidence/dispatch/typed seed → review/merge
→ refreeze original 02-15 composition-only seam
```

每一步只从前一步真实reviewed successor冻结；不得预填SHA或跨owner并包。

## Stop conditions

出现fixture-name/static-digest/oracle反推seed、Application/Infrastructure逻辑进入
bootstrap、`http.py`无证据变化、artifact/lifecycle mutation、Harness dispatch/Result、
allowlist/owner/base/tree/blob不匹配，立即停止并裁决。

## Current gate

当前只允许`02-15R0`单文件Spec correction planning/review；R1/R2/02-15尚未冻结。
