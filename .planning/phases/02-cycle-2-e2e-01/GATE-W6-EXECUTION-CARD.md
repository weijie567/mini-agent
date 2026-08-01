# Gate W6｜02-07R owner correction and Adapter execution card

状态：`02-07R_COMPLETE / 02-07_AND_02-11_PLANNING_REVIEW`

## Exact input

- Master-plan owner-ruling PR #250 merge successor：
  `89041f73f490831073bcc41b14757a51757248c9` / tree
  `3364efa2fbdd3e64ac5142fbd4562a439713af2a`。
- Reviewed physical barrier：
  `B_C2_PHYSICAL = bf8e88b2c0124aee82dffc7e54ae03ec0fdbea50` / tree
  `fccc5a1f87a0b00dd31ba61ee8c960901c7601da`。
- User ruling：2026-08-02 授权 `02-07R`、slots `26 → 27`，不新增
  wave label。
- Case lifecycle：`E2E01-02/03/05/06 = CONTRACT_DEFINED`。
- `02-07R` planning PR #251 与 implementation PR #252 已reviewed merge；
  `B_C2_BUSINESS_READ_PORTS = c775ef45eb42c9f03e63d0065d493e2fb2a43556` /
  tree `c598651b56db003e6ab77a08d266d709a0ff8e76`，focused `25 passed`、
  neighbor `284 passed`，feature/overlay/remote identity review均PASS。

## Ordered dispatch

```text
02-07R reviewed merge / B_C2_BUSINESS_READ_PORTS
→ review and merge fresh exact 02-07 and 02-11 Plans from that successor
→ at most two non-overlapping writers
→ independent review and serial merge
→ run the one W6-exit canonical full
→ freeze B_C2_INFRA
```

## Review profiles

- `02-07R`：`TARGETED_APPLICATION_PORT`，不运行 migration/full。
- `02-07`：`TARGETED_BUSINESS_ADAPTER`，只涉及 owner-scoped search/shipment Adapter。
- `02-11`：`TARGETED_POSTGRES_RECORDS`，只涉及 records/recovery/atomicity。
- canonical full：只在 `02-07` 与 `02-11` 两个 reviewed merge 后运行一次。

## Stop conditions

出现 contract change、owner conflict、allowlist 扩张、再次增减 slot/wave、
BLOCK/HIGH 无法在当前 Packet 关闭、migration 不唯一、Case lifecycle 证据不足、
exact base/tree/blob/barrier 不相等，立即停止并裁决。

## Current gate

`02-07R` 已完成。`02-07/02-11` 只在两份新 exact Plan 都获得 independent
exact-head `PASS` 并通过同一个 planning PR 合并后可 dispatch；两包文件
零重叠，但仍需独立review、latest overlay 与串行merge。不得复用早期 W6 draft。
