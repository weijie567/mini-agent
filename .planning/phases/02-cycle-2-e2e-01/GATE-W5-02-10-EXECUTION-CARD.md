# Gate W5｜02-10 physical migration execution card

状态：`W5_COMPLETE / B_C2_PHYSICAL_FROZEN / W6_NOT_STARTED`

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

```text
planning PR #247 merge = 848471a85744a701e409322b7285a979ad104c9d
implementation PR #248 reviewed head = 54e50657edf4ab6e6e47e2025e0347c91bbbd38e
implementation PR #248 merge / B_C2_PHYSICAL = bf8e88b2c0124aee82dffc7e54ae03ec0fdbea50
B_C2_PHYSICAL tree = fccc5a1f87a0b00dd31ba61ee8c960901c7601da
latest-integration overlay tree = fccc5a1f87a0b00dd31ba61ee8c960901c7601da
focused = 66 passed
neighbor = 277 passed
empty DB -> head = PASS
Phase 1 head -> Phase 2 head = PASS
migration head / compile / diff / exact four-file allowlist = PASS
exact-head review = PASS after one HIGH fix
overlay review = PASS / 0 BLOCK / 0 HIGH
canonical full = NOT RUN (W6 exit only)
Case lifecycle / Phase 2 Harness / Eval Result = NOT ADVANCED / NOT RUN
```

初审发现downgrade未锁search/shipment evidence tables的TOCTOU HIGH；修订head在任何
evidence check前以固定顺序`SHARE ROW EXCLUSIVE`同时锁四表，并以两类真实并发测试
证明DML阻断与commit后fail-closed保留。复审确认finding关闭。
