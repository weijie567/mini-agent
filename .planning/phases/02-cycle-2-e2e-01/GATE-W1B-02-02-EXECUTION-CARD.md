# Gate W1B｜02-02 执行卡

> **DERIVED EXECUTION CONTROL / USER DIRECTIVE RECORDED**

## 冻结输入

- `B_C2_W1A = b5de7f4f48404b61d9b4386c99cd2c37e744641a`
- tree `d1eb4d469cc0d9f41672f1e9294be3fbb18e23ec`
- `02-03` 已先合入，`02-01` 已通过 reviewed overlay 后合入。
- 02-01 的 `order_search.py` / `shipment.py` 是 02-02 唯一 typed business DTO 来源。
- Planning PR #210 已从 exact `B_C2_W1A` 创建并 reviewed merge；该 merge 只推进
  `.planning/` 控制面，不替换 `B_C2_W1A` 产品 implementation base。

## 当前用户授权

用户已明确要求：W1 Packet 写完后调用全新窗口审阅，直到通过；随后启动 W1 编程，
实现结束后 code review 直到通过；W2、W3 采用相同模式，W3 完成后停止。

因此无需再次请求中间批准，但必须满足：

1. 本 planning PR 的全新窗口 exact-file review 为 `PASS`。
2. 合并后的 integration control head 含 exact `02-02-PLAN.md` blob；相对
   `B_C2_W1A` 的累计 drift 必须仅为 reviewed planning provenance，且 Packet 的
   required product/source blobs 全部未变。
3. implementation branch/Worktree 仍从上述 exact product base `B_C2_W1A` 创建。
4. feature Draft PR 通过后，将 exact implementation patch 叠加到冻结的 integration
   control head；该 exact overlay 也必须由全新窗口 review 为 `PASS`。
5. reviewed overlay 合并 successor 冻结为 `B_C2_CORE_123`，完整 W1 gate 通过后才
   签发 W2。

任何 `BLOCK/HIGH`、未处置 `MEDIUM`、allowlist/base/tree 漂移或测试失败都会暂停当前
Packet 的 merge；只允许在原边界内修复并使用另一个全新窗口复审。

## 明确不授权

- 不直接 push `main` 或 active integration branch。
- 不绕过 Draft PR、independent review、latest integration overlay 或 full W1 gate。
- 不在 02-02 实现 persistence/Port/Adapter/Tool/Runtime/Eval lifecycle。
- 不执行 W4 或之后工作；W3 review PASS 后立即停止。
