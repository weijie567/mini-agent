# Gate W1B｜02-02 执行卡

> **DERIVED EXECUTION CONTROL / USER DIRECTIVE RECORDED**

## 修复后冻结输入

- 历史 `B_C2_W1A = b5de7f4f48404b61d9b4386c99cd2c37e744641a`；因 02-03
  full-gate regression 已被后续 reviewed correction 取代，不再是可执行 base。
- `B_C2_W1_GATE_REPAIRED = 015c1e8be204717dfa1af80d930a8333a41e8b92`
- tree `26b71d2ba3f2c638204cab7c078252c97b374f05`
- `02-03` 已先合入，`02-01` 已通过 reviewed overlay 后合入。
- PR #212 只修正 `test_cycle2_trace_contract.py` 的越界 codec 依赖；独立审阅
  `PASS` 且 canonical full gate 为 `2296 passed, 1 deselected, 12 warnings`。
- 02-01 的 `order_search.py` / `shipment.py` 是 02-02 唯一 typed business DTO 来源。
- 旧 base 上形成的 `ecfad7e22ba542e50256274a94a6bb88fdf49b83` 未经过可合并的
  formal review，保持 quarantined；不得 push、merge、rebase 或充当本轮 reviewed head。
- 本 refreeze planning PR 从 exact `B_C2_W1_GATE_REPAIRED` 创建；merge 后只允许
  `.planning/` 控制面相对该 repaired product base 前移。
- `.planning/PROJECT.md`、`.planning/ROADMAP.md`、`.planning/STATE.md` 当前仍含旧
  `B_C2_W1A` 执行指令；本 two-file PR 不越过 single-writer allowlist 修它们。其
  reviewed merge 后必须创建 dedicated planning-status PR 完成对齐，且该 PR reviewed
  merge 前 `02-02` r2 dispatch 继续 `BLOCKED`。

## 当前用户授权

用户已明确要求：W1 Packet 写完后调用全新窗口审阅，直到通过；随后启动 W1 编程，
实现结束后 code review 直到通过；W2、W3 采用相同模式，W3 完成后停止。

因此无需再次请求中间批准，但必须满足：

1. 本 planning PR 的全新窗口 exact-file review 为 `PASS`。
2. 本 planning PR reviewed merge 后，由 dedicated single-writer planning-status PR
   对齐 `PROJECT.md`、`ROADMAP.md`、`STATE.md` 的 repaired base/tree、旧
   `ecfad7e...` quarantine、r2 ancestry 与 Case 仍为 `CONTRACT_DEFINED`；该状态 PR
   必须经全新窗口 exact-head review 为 `PASS` 并合并。
3. 两个 planning PR 合并后的 integration control head 含 exact `02-02-PLAN.md` blob；相对
   `B_C2_W1_GATE_REPAIRED` 的累计 drift 必须仅为 reviewed planning provenance，
   且 Packet 的 required product/source blobs 全部未变。
4. 新的 r2 implementation branch/Worktree 从上述 exact repaired product base 创建；
   旧 branch/head 只可作为人工对照，不得成为 ancestry 或 merge input。
5. feature Draft PR 通过后，将 exact implementation patch 叠加到冻结的 integration
   control head；该 exact overlay 也必须由全新窗口 review 为 `PASS`。
6. reviewed overlay 合并 successor 冻结为 `B_C2_CORE_123`，完整 W1 gate 通过后才
   签发 W2。

任何 `BLOCK/HIGH`、未处置 `MEDIUM`、allowlist/base/tree 漂移或测试失败都会暂停当前
Packet 的 merge；只允许在原边界内修复并使用另一个全新窗口复审。

## 明确不授权

- 不直接 push `main` 或 active integration branch。
- 不绕过 Draft PR、independent review、latest integration overlay 或 full W1 gate。
- 不在 02-02 实现 persistence/Port/Adapter/Tool/Runtime/Eval lifecycle。
- 不执行 W4 或之后工作；W3 review PASS 后立即停止。
