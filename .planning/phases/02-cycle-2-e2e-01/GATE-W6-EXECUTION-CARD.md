# Gate W6｜02-10R physical correction and Adapter execution card

状态：`02-10R_PLANNING_REVIEW / 02-07_AND_02-11_PAUSED`

## Exact input

- Master-plan owner-ruling PR #254 merge successor：
  `d05933238db26939e06421d148060c513a0aed6a` / tree
  `d37da0d30f2d76c7a572d1900ea6c50bb9a5db90`。
- Reviewed business Port barrier：
  `B_C2_BUSINESS_READ_PORTS = c775ef45eb42c9f03e63d0065d493e2fb2a43556` /
  tree `c598651b56db003e6ab77a08d266d709a0ff8e76`。
- User ruling：2026-08-02 授权按建议加入 `02-10R`、slots `27 → 28`，不新增
  wave label。
- Confirmed physical gap：search authority 无 `status`，且没有承载 Adapter-assigned
  `snapshot_resource_ref` 的 durable restricted raw snapshot record。
- Case lifecycle：`E2E01-02/03/05/06 = CONTRACT_DEFINED`。
- 原 `02-07/02-11` Plans 与两个 implementation Worktrees 均 clean/paused，不可 dispatch。

## Ordered dispatch

```text
review and merge exact 02-10R Plan
→ implement/review/serial-merge 02-10R
→ freeze B_C2_SEARCH_AUTHORITY_PHYSICAL
→ re-freeze and review 02-07 + 02-11 exact Plans from the real successor
→ at most two non-overlapping writers
→ independent bounded review + latest overlays + serial merges
→ run the one W6-exit canonical full
→ freeze B_C2_INFRA
```

## Review profiles

- `02-10R`：`TARGETED_MIGRATION`，只涉及 revision 0005、ORM parity 与 migration tests。
- `02-07`：`TARGETED_BUSINESS_ADAPTER`，成功 search 在同一事务读取权威行并追加 raw snapshot。
- `02-11`：`TARGETED_POSTGRES_RECORDS`，只涉及 records/recovery/atomicity。
- 每次 reviewer 最长 45 秒；超时即中止，不允许无界 history/test 扫描。
- canonical full：只在三个 correction/Adapter/records feature 都 reviewed merge 后运行一次。

## Stop conditions

出现 canonical contract change、owner conflict、allowlist 扩张、再次增减 slot/wave、
BLOCK/HIGH 无法在当前 Packet 关闭、migration 不唯一、status 被猜测、snapshot ref
由数据库生成、raw snapshot 被普通 Trace/model/HTTP 披露、Case lifecycle 证据不足、
exact base/tree/blob/barrier 不相等，立即停止并裁决。

## Current gate

只允许 `02-10R` 在 exact Plan independent review/merge 后 dispatch。真实实现 merge 前，
`02-07/02-11` 继续暂停；之后必须重新冻结 base/tree/blobs 与 snapshot append 事务语义，
不得复用现有 stale Plans、branches 或 Worktrees。
