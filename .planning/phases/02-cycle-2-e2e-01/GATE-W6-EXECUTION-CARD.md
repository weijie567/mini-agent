# Gate W6｜Adapter and PostgreSQL records execution card

状态：`02-10R_COMPLETE / B_C2_SEARCH_AUTHORITY_PHYSICAL / 02-07_AND_02-11_PLANNING_REVIEW`

## Exact input

- `02-10R` planning PR #255 与 implementation PR #256 已reviewed merge。
- Current integration / physical correction barrier：
  `B_C2_SEARCH_AUTHORITY_PHYSICAL = 64254f170ced8a71d58fd2f0b0d1adfaa8f275a5` /
  tree `ad332f6b862d34feec342c57e679d7234179e24e`。
- 02-10R evidence：focused `74 passed`、neighbor `85 passed`、empty/Phase1 upgrade、
  migration head、compile/diff、feature/overlay reviews均PASS；canonical full未运行。
- User ruling：2026-08-02 授权按建议完成 W6/W7，并继续 W8/W9；slots `28`、
  wave labels `16`、max writers `2`。
- Case lifecycle：`E2E01-02/03/05/06 = CONTRACT_DEFINED`。
- 原 `02-07/02-11` Plans 与 implementation Worktrees 均 clean/paused；新 Packet
  使用 `-r1` branches/Worktrees，不 reset、不复用旧 ancestry。

## Ordered dispatch

```text
review and merge second-refrozen exact 02-07 + 02-11 Plans
→ create at most two new non-overlapping -r1 Worktrees
→ independent bounded feature reviews
→ Integrator latest-integration overlays + serial merges
→ run exactly one W6-exit canonical full
→ freeze B_C2_INFRA
```

## Review profiles

- `02-07`：`TARGETED_BUSINESS_ADAPTER`；成功 search 在一次 authority SELECT 后于
  同一事务追加 Adapter-assigned restricted raw snapshot。
- `02-11`：`TARGETED_POSTGRES_RECORDS`；只涉及 records/recovery/atomicity。
- 每次 reviewer 最长 45 秒；超时即中止，不允许无界 history/test 扫描。
- canonical full：只在 `02-07` 与 `02-11` 两个 reviewed merge 后运行一次。

## Stop conditions

出现 canonical contract change、owner conflict、allowlist 扩张、再次增减 slot/wave、
BLOCK/HIGH 无法在当前 Packet 关闭、authority second SELECT、snapshot 与 authority
事务分离、snapshot ref 非 Adapter 随机分配、raw snapshot 披露、exact reader/CAS
fail-open、Case lifecycle 证据不足、exact base/tree/blob/barrier 不相等，立即停止并裁决。

## Current gate

`02-07/02-11` 只在两份 second-refrozen exact Plan 都获得 independent exact-head
`PASS` 并通过同一个 planning PR 合并后可 dispatch。两包文件零重叠，但仍需各自
review、latest overlay 与串行merge。任何旧 W6 Plan/branch/Worktree 都不可执行。
