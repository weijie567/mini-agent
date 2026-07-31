# Gate W2｜02-04 执行卡

> **DERIVED EXECUTION CONTROL / USER DIRECTIVE RECORDED**

## 冻结输入

- `B_C2_CORE_123 = 241cf6b83761f5d91da5de7719f26838e2626e26`
- tree `83fcbf90770ffdc30ef37e35e94169bcb9ead3b3`
- PR #214 将四份 status index 独立审阅至 `PASS` 后合入；merge successor
  `2aec3663a5d8e2456e6bf69f37ac1f8f343a6c19`。
- PR #215 的 02-02 feature 与 latest integration overlay 均经全新任务审阅为
  `PASS`；merge successor 即 `B_C2_CORE_123`。
- W1 canonical full gate：`2340 passed, 1 deselected, 12 warnings`。
- `E2E01-02/03/05/06` 仍为 `CONTRACT_DEFINED`；W1 Core contracts 完成不等于
  Case 可执行、Eval evidence 或 lifecycle advancement。

## 当前用户授权

用户已明确要求：每个 Wave 的 Packet 写完后调用全新任务审阅，直到通过；随后启动
编程，实现结束后 code review 直到通过；W2、W3 采用同一模式，W3 完成后停止。

因此无需再次请求中间批准，但必须满足：

1. 本 six-file planning PR 的全新任务 exact-file review 为 `PASS`。
2. GitHub `integration/e2e01-cycle2` branch protection 必须可机械读取：PR required、
   enforce admins / linear history / conversation resolution 开启，force push / deletion
   关闭；任一缺失即 `BLOCK`，不得用 admin bypass。
3. reviewed planning PR 合并后，相对 `B_C2_CORE_123` 的累计 pre-dispatch drift
   只能是本 PR 的六份 `.planning/` 文件；Packet required source blobs 全部不变。
4. 新 implementation branch/Worktree 从 exact `B_C2_CORE_123` 创建；不得从 planning
   merge successor 或其他未冻结产品 base 猜测创建。
5. feature Draft PR 只改 Packet 四文件并运行 focused/neighbor/full gate；exact feature
   head 必须由全新任务 code review 至 `PASS`。
6. feature patch 叠加到冻结 integration control head 后，exact overlay 也必须由另一
   全新任务 review 为 `PASS`，且 test-merge tree 与 reviewed overlay tree 相同。
7. reviewed merge successor 冻结为 `B_C2_TOOL`；只有该 barrier 与完整 W2 gate 成立
   才签发 W3 `02-05`。

任何 `BLOCK/HIGH`、未处置 `MEDIUM`、allowlist/base/tree/blob 漂移或测试失败都会暂停
当前 Packet merge；只允许在原四文件实现边界或六文件 planning 边界内修复，并使用
新的独立任务重新审阅。

## 本 Wave 实现什么

- 两个新增 Read Tool 的 closed agent-visible schema。
- `search_orders/get_order/get_shipment` exact immutable registry/policy contract。
- inactive additive v2 ToolCall/attempt/retry/recovery closed matrix。
- pure Cycle 2 Gateway binding/state/snapshot/owner/budget decision helper。

## 明确不授权

- 不修改 Phase 1 active v1 Tool DTO/Gateway 行为。
- 不修改 `bootstrap.py`、Composition Root、Persistence codec、Application Port、Adapter、
  Executor、Runtime orchestration、HTTP、Renderer、Eval artifact 或 Case lifecycle。
- 不注册 `create_refund`、`PROPOSE_ACTION`、confirmation 或 ActionPolicy capability。
- 不直接 push `main` 或 active integration branch，不绕过 Draft PR、review、overlay 或
  full gate。
- 不执行 W4 或之后工作；W3 review `PASS` 后立即停止。
