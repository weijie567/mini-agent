# Gate W6｜Adapter and PostgreSQL records execution card

状态：`02-07_COMPLETE / B_C2_BUSINESS_ADAPTERS / 02-11R_PLANNING_REVIEW`

## Exact input

- `02-10R` PR #255/#256、W6 refreeze PR #257 与 `02-07` PR #258 均已 reviewed
  merge。
- Current integration / business Adapter barrier：
  `B_C2_BUSINESS_ADAPTERS = 78bce02c36ada33d6695d5a919d23b61bb8df21e` /
  tree `032e0c5edfb3c2ffc18f34192ae72858bc0cec85`。
- 02-07 evidence：focused `28 passed`、neighbor `392 passed`、compile/diff、
  feature/closure reviews与latest overlay均PASS；owner/package refs 使用 domain-separated
  canonical JSON SHA-256 opaque identity；canonical full未运行。
- `02-11` blocked checkpoint `da8ee98178dc4a69c32253b68cc897c7c5556711` /
  tree `342616a59c06a601871e2733126673e6d0c3baf2` 保持 clean、unpublished；focused
  `109 passed`、neighbor `1340 passed`、compile/diff PASS，但 non-null-base OA-10 因
  缺少 exact historical Task / RequestUnit pre-image 而 fail closed。
- User ruling：2026-08-02 授权有问题按建议修复后继续 W6–W9；PR #259 reviewed
  批准 `02-11R`，slots `29`、
  wave labels `16`、max writers `2`。
- Case lifecycle：`E2E01-02/03/05/06 = CONTRACT_DEFINED`。
- 02-11 checkpoint 不得发布或直接作为 feature head；必须在真实 `02-11R`
  successor 上新建 Worktree 并重冻结回放。

## Ordered dispatch

```text
review and merge exact 02-11R Plan
→ implement/review/overlay/merge 02-11R three-file physical correction
→ freeze B_C2_RECORD_HISTORY_PHYSICAL
→ refreeze/replay 02-11 five-file checkpoint on the real successor
→ independent bounded feature + latest-overlay reviews and serial merge
→ run exactly one W6-exit canonical full
→ freeze B_C2_INFRA
```

## Review profiles

- `02-11R`：`TARGETED_MIGRATION`；只涉及 revision 0006、ORM history model 与
  migration tests；不实现 Adapter。
- `02-11`：`TARGETED_POSTGRES_RECORDS`；只涉及 records/recovery/atomicity，并在
  current replace 同事务写 pre-image、按 owner/identity/version exact read。
- 每次 reviewer 最长 30 秒；超时即中止，不允许无界 history/test 扫描。
- canonical full：只在 `02-11R` 与 replayed `02-11` reviewed merge 后、W6 exit
  运行唯一一次。

## Stop conditions

出现 canonical contract change、owner conflict、allowlist 扩张、再次增减 slot/wave、
BLOCK/HIGH 无法在当前 Packet 关闭、history 从 current row/Memory/模型补造、history
与 current replace 非同一事务、wrong-owner/version history 被接受、迁移前历史回填、
non-empty destructive downgrade、exact reader/CAS fail-open、Case lifecycle 证据不足、
exact base/tree/blob/barrier 不相等，立即停止并裁决。

## Current gate

`02-11R` 只在本 exact Plan 获得 independent exact-file `PASS` 并通过 planning PR
合并后可 dispatch。`02-11` 只在 reviewed `B_C2_RECORD_HISTORY_PHYSICAL` 真实
successor 上重冻结回放；blocked checkpoint 只作 source patch reference。Cases、
Harness/Result 与 canonical full 在此前均不得推进。
