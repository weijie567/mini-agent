# Gate W3｜02-05 执行卡

> **DERIVED EXECUTION CONTROL / USER DIRECTIVE RECORDED**

## 冻结输入

- `B_C2_TOOL = f9a2a75135ba63347e81e13f2b981cf550977875`
- tree `59afeccec3705b7bae754c00b012f669a049a9ac`
- PR #216 的 W2 planning provenance 经全新任务审阅为 `PASS` 后合入。
- PR #217 的 02-04 feature exact head 与 latest integration overlay 均经全新任务
  审阅为 `PASS`；merge successor 即 `B_C2_TOOL`。
- W2 canonical full gate：`2499 passed, 1 deselected, 12 warnings`。
- `E2E01-02/03/05/06` 仍为 `CONTRACT_DEFINED`；W2 Tool/Application contract 的出现
  不等于 Tool active、Case executable、Eval Result 或 lifecycle advancement。

## 当前用户授权

用户已明确要求：每个 Wave 的 Packet 写完后调用全新任务审阅，直到通过；随后启动
编程，实现结束后 code review 直到通过；W3 采用同一模式，W3 完成后停止。

因此无需再次请求中间批准，但必须满足：

1. 本 six-file planning PR 的全新任务 exact-file review 为 `PASS`。
2. GitHub `integration/e2e01-cycle2` branch protection 可机械读取：PR required、
   enforce admins / linear history / conversation resolution 开启，force push / deletion
   关闭；任一缺失即 `BLOCK`，不得用 admin bypass。
3. reviewed planning PR 合并后，相对 `B_C2_TOOL` 的累计 pre-dispatch drift 只能是
   本 PR 的六份 `.planning/` 文件；Packet required source blobs 全部不变。
4. 新 implementation branch/Worktree 从 exact `B_C2_TOOL` 创建；不得从 planning
   merge successor 或其他未冻结产品 base 猜测创建。
5. feature Draft PR 只改 Packet 四文件并运行 focused/neighbor/full gate；exact feature
   head 必须由全新任务 code review 至 `PASS`。
6. feature patch 叠加到冻结 integration control head 后，exact overlay 也必须由另一
   全新任务 review 为 `PASS`，且 test-merge tree 与 reviewed overlay tree 相同。
7. reviewed merge successor 冻结为 `B_C2_APP_CONTRACT` 后立即停止；不签发、规划、
   创建或执行 W4。

任何 `BLOCK/HIGH`、未处置 `MEDIUM`、allowlist/base/tree/blob 漂移或测试失败都会暂停
当前 Packet merge；只允许在原四文件实现边界或六文件 planning 边界内修复，并使用
新的独立任务重新审阅。

## 本 Wave 实现什么

- 五个 Cycle 2 logical record/projection 的 strict Application command/read closure。
- ToolCall/attempt、AgentRun、RunTaskLink、TraceEvent 四个 v2 parent family 的 inactive
  Application aggregate contract。
- CandidateSet/search、ordinal selection、attempt fence/finalize、Shipment
  Observation/Assessment 与 OA-10 no-result 的原子 Port declaration。
- owner-scoped exact read、absent/unauthorized indistinguishability 与 integrity
  fail-closed Component evidence。

## 明确不授权

- 不修改 Core、active Phase 1 `RuntimeRecordPort` / `RestartRecoveryPort`、existing
  Adapter 或 v1 command/reader。
- 不实现 codec、migration、数据库表/SQL、PostgreSQL Adapter、retry/recovery executor、
  Runtime orchestration、Composition Root、HTTP、Renderer 或 Eval artifact/lifecycle。
- 不注册或触发 Action、confirmation、ActionPolicy、idempotency、Action Ledger 或
  `RESULT_UNKNOWN` side-effect recovery。
- 不直接 push `main` 或 active integration branch，不绕过 Draft PR、review、overlay 或
  full gate。
- W3 闭环后不继续 W4。
