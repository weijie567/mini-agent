# Gate W9｜Owner correction execution card

状态：`B_C2_W9_R1_SIXTH_REFREEZE / 02-15R1I_PLAN_REVIEW`

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
- PR #280已reviewed完成R1 second-refreeze planning；writer随后只读确认UNIQUE
  search outcome没有durable verified-target capability/Core route。PR #281已reviewed
  批准`02-15R1C → 02-15R1D`，当前36 slots / 16 wave labels；真实
  `B_C2_W9_R1CD_OWNER_APPROVED = aef424c0fdd1b2c913a699b6a4f456e14b178eee` /
  tree `dc4662ac4e994811cb8a2160f9678d8f86cfdf61`。旧R1 checkpoint继续未发布。
- PR #282/#283已reviewed完成R1C planning/implementation；真实
  `B_C2_W9_UNIQUE_TARGET_CONTRACT = dd1e972763534198e6d2601baa2b60bb3312ad80` /
  tree `394d022adfa80ef4d935216393fecf19892d4316`。R1C只补active scoped Spec，
  Core/Application/Infrastructure与Case lifecycle均未推进。
- PR #284-#296已reviewed完成R1D/R1E/R1F/R1G/R1H、各自planning与R1第六次
  refreeze；真实current integration为
  `B_C2_W9_R1_SIXTH_REFREEZE = 24f1e181b54b0ae4d2889c653f4651064ce081e1` /
  tree `99f48fcde988b71adb5d0e19df99f69fd1b8854b`。当前40 slots / 16 wave labels。
- R1第六次writer确认Gateway Observation-history集合缺陷；用户授权按建议修复，
  `02-15R1I`把总slot数调整为41、不新增wave label；R1 WIP继续未发布。

## Ordered dispatch

```text
02-15R0 exact Spec seed contract → review/merge B_C2_W9_SEED_CONTRACT
→ 02-15R1A Core initial product-description RU → review/merge B_C2_W9_INITIAL_RU
→ 02-15R1B typed read-execution envelope → review/merge B_C2_W9_TYPED_READ_EXECUTION
→ 02-15R1C UNIQUE target durability Spec → review/merge B_C2_W9_UNIQUE_TARGET_CONTRACT
→ 02-15R1D UNIQUE auto-target Core route → review/merge B_C2_W9_UNIQUE_TARGET_CORE
→ 02-15R1E/F/G/H UNIQUE/Shipment Gateway/route corrections
→ sixth-refreeze 02-15R1
→ 02-15R1I Gateway Observation history correction
→ seventh-refreeze 02-15R1 Application normal entry → review/merge
→ refreeze 02-15R2 Infrastructure normal evidence/dispatch/typed seed → review/merge
→ refreeze original 02-15 composition-only seam
```

每一步只从前一步真实reviewed successor冻结；不得预填SHA或跨owner并包。

## Stop conditions

出现fixture-name/static-digest/oracle反推seed、Application/Infrastructure逻辑进入
bootstrap、`http.py`无证据变化、artifact/lifecycle mutation、Harness dispatch/Result、
allowlist/owner/base/tree/blob不匹配，立即停止并裁决。

## Current gate

当前只允许`02-15R1I` exact-two-file planning/review；R1 WIP未发布，R2/02-15尚未冻结。
