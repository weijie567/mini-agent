# Gate W9｜Owner correction execution card

状态：`B_C2_W9_TYPED_READ_EXECUTION / 02-15R1_SECOND_REFREEZE_REVIEW`

## Exact input

- `B_C2_EVAL_MACHINERY = d6fdcbb3cdd4e6bb41fb2ae0b1ff5b80629b4efb` /
  tree `8ab6f2aeab53bfae73edff219cab70623c437ebc`。
- PR #268/#269 已reviewed批准W9在原wave内串行`02-15R0→R1→R2→02-15`，
  32 slots / 16 wave labels；PR #273又reviewed批准R1A Core correction，当前
  33 slots / 16 wave labels。
- Case lifecycle仍为`CONTRACT_DEFINED`；Phase 2 Harness dispatch与Result为零。
- PR #270/#271已reviewed完成R0；真实
  `B_C2_W9_SEED_CONTRACT = 95b2acf3be79bba1d6e40ba8a56bffc9109b54d6` /
  tree `466e07a4aec381967c5bc59c248207f111bb97f3`。R0禁止W9预置Runtime graph。
- PR #274/#275已reviewed完成R1A；真实
  `B_C2_W9_INITIAL_RU = 2fb68b0210a865c293bcb7f471b38c728dcbb7dd` /
  tree `b0dfc7802b81bee21168c4e79e2d046a642d0162`。
- PR #276已reviewed重冻结R1；success-path executor gap经PR #277 reviewed批准
  `02-15R1B`，当前34 slots / 16 wave labels；R1 checkpoint未发布。
- PR #278/#279已reviewed完成R1B；真实
  `B_C2_W9_TYPED_READ_EXECUTION = 1fba65168fb487d3c4a8664213831a9c1c5dc815` /
  tree `ec3c8c501c3c6385cef834f8a5efd1056642087d`。focused `68 passed`、neighbor
  `446 passed`；R1 checkpoint仍未发布，必须从该真实successor重新实现。

## Ordered dispatch

```text
02-15R0 exact Spec seed contract → review/merge B_C2_W9_SEED_CONTRACT
→ 02-15R1A Core initial product-description RU → review/merge B_C2_W9_INITIAL_RU
→ 02-15R1B typed read-execution envelope → review/merge B_C2_W9_TYPED_READ_EXECUTION
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

当前只允许`02-15R1` exact-six-file second-refreeze planning/review；R1实现、R2/02-15尚未冻结。
