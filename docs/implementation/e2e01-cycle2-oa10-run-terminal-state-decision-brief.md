# E2E-01 Cycle 2｜OA-10 Run Terminal State Decision Brief

> **NON_NORMATIVE / USER_RULING_APPROVED / OWNER_ALIGNMENT_DRAFT_PREPARED / R1_FINDINGS_REMEDIATED / R2_VERDICT_FAIL / R2_FINDINGS_REMEDIATED / R3_VERDICT_FAIL / R3_FINDINGS_REMEDIATED / R4_VERDICT_FAIL / R4_FINDING_REMEDIATED / R5_VERDICT_FAIL / R5_FINDING_REMEDIATED / R6_EXACT_FILE_REVIEW_PENDING / ACTIVATION_BLOCKED**
>
> 本文只比较 obsolete Run 的 terminal-state 方案，不是 active contract，不修改
> Phase、Case lifecycle、Plan、Task Packet、Worktree、源码、测试、migration 或
> Eval artifact。用户已批准本文 A1 推荐方案；该批准只授权准备 owner alignment，
> 不表示独立 review、merge 或 Activation 已完成。

- **Created:** 2026-07-31
- **Repository baseline inspected:** `8f73b1ef89444bbdccbc50777394bcc420b42b3f`
- **Target:** `E2E01-02/03/05/06`
- **Current Phase 2 status:** `PLANNED_MAPPING_ONLY`
- **Current Case lifecycle:** `CONTRACT_DEFINED`
- **Decision status:** `USER_APPROVED / OWNER_ALIGNMENT_NOT_CLOSED`

## 1. 已批准且两种方案都必须满足的不变量

1. obsolete Run 不发送 `AgentRunResult`、ASSISTANT Message 或其他用户结果。
2. obsolete Run 不覆盖已由新消息 / 新 Run 推进的 Task 或 RequestUnit。
3. 已发生的 Run、ToolCall、attempt 和安全 Trace evidence append-only 保留。
4. unknown、重复或互相矛盾的 interruption / invalidation reason 必须 fail
   closed，不能回退为 `COMPLETED`、safe not-found 或模型自由措辞。

这些不变量已经取得用户批准；第 7 节记录随后取得的 exact status、stop reason 与
`RunStopped` projection 裁决。

## 2. 当前源码事实

以下均为 `CONFIRMED`：

- [`AgentRunStatus`](../../src/mini_agent/core/trace.py) 当前只有 `CREATED`、
  `RUNNING`、`COMPLETED`、`FAILED`、`INCOMPLETE`。
- 同一文件的 `AgentRunRecord` 把 `INCOMPLETE` 精确限制为
  `StopReason.PROCESS_RESTART_DETECTED`；`RunStopped` 必须同时有
  `user_outcome` 与 `stop_reason`。
- [`FinalizeRunCommand`](../../src/mini_agent/application/records.py) 只接受普通
  `COMPLETED` / `FAILED` 终止；[`MarkRunIncompleteForRecoveryCommand`](../../src/mini_agent/application/records.py)
  只接受 restart recovery 的 `INCOMPLETE + PROCESS_RESTART_DETECTED`。
- [`RestartRecoveryService`](../../src/mini_agent/application/restart_recovery_service.py)
  会把 restart 前的 active Run 置为 `INCOMPLETE`、把 active Task / RequestUnit
  置为 `BLOCKED`，并写 `RunStopped(user_outcome=BLOCKED,
  stop_reason=PROCESS_RESTART_DETECTED)`；它不补发旧 HTTP 结果。
- [`ExactRunEvidenceClosure`](../../src/mini_agent/application/records.py) 同样把所有
  `INCOMPLETE` closure 限定为上述 restart 组合。
- [`PostgresRestartRecoveryAdapter`](../../src/mini_agent/infrastructure/persistence/recovery.py)
  只发现 `CREATED / RUNNING` Run；`INCOMPLETE` 已被当作终态而不是待重新执行状态。
- [`AgentRunService`](../../src/mini_agent/application/agent_run_service.py) 当前把
  handler / coroutine cancellation 收口为 `FAILED`，且不写用户结果或
  `RunStopped`。因此“运行时取消”“业务目标取消”和“旧 Run 被新状态取代”当前不是
  同一个已建模概念。
- [`TaskStatus`](../../src/mini_agent/core/task_state.py) 已有 `CANCELLED`，但这是
  Task / RequestUnit 状态，不是 Run 状态。
- [`EvalCaseSut` evidence mapper](../../src/mini_agent/evaluation/harness.py) 的普通
  HTTP Result 路径只接受 `COMPLETED + AgentRunResult`。obsolete no-result Run
  需要由 trajectory / exact closure evidence 评价，不能伪造成普通用户结果。

因此，扩展 `INCOMPLETE` 不是只新增一个 stop reason；专用 terminal status 也不是
只新增一个 Enum 值。两者都会触及 Core validator、Application finalization、
record closure、持久化 projection、Trace / Eval 与测试。

## 3. 决策对象

需要选择 obsolete Run 的 exact 表达：

```text
方案 A：新增专用 terminal state
  A1. SUPERSEDED + STATE_OR_BINDING_INVALIDATED
  A2. CANCELLED  + STATE_OR_BINDING_INVALIDATED

方案 B：扩展现有 INCOMPLETE
  INCOMPLETE + STATE_OR_BINDING_INVALIDATED
```

本节保留裁决前的备选比较记录。用户最终批准的 exact stop reason 是
`STATE_OR_BINDING_INVALIDATED`；任何未来拆分都必须重新经过 Core owner
contract evolution，不能由实现自行收窄。

## 4. 方案 A｜专用 terminal state

### A1. `SUPERSEDED`

语义：

- Run 曾经有效，但在提交结果前已经被更高版本的 Task / binding / accepted
  message 取代。
- 这是一个明确、不可恢复、无用户结果的终态。
- 它不表示进程故障、用户取消业务目标、Handler cancellation 或业务执行失败。

建议的终止投影：

```text
AgentRunStatus.SUPERSEDED
StopReason.STATE_OR_BINDING_INVALIDATED
AgentRunResult = absent
Assistant Message = absent
ResponseRendered = absent
RunStopped.user_outcome = BLOCKED  # audit disposition only; not outbound result
Task / RequestUnit mutation = absent
```

这里复用现有 `RunStopped` 字段，不改变 shared `TraceEvent` structure。
`user_outcome=BLOCKED` 只表示 audit disposition；用户已在第 7 节批准把这一既有
字段用于 `SUPERSEDED`，不把它解释为出站结果。

建议使用独立的 conditional finalization contract，而不是放宽普通
`FinalizeRunCommand`：

```text
expected active Run + exact current owner-scoped Task/link evidence
→ revalidate that old Run is obsolete
→ CAS terminalize Run and close its link
→ append RunStopped
→ write no Task transition, AgentRunResult, Message or ResponseRendered
```

这样可以用 record shape 强制“不覆盖新 Task”，而不是依赖调用方自律。

### A2. `CANCELLED`

物理实现面与 `SUPERSEDED` 相近，但语义风险更高：

- 当前 `TaskStatus.CANCELLED` 表示目标取消；Run 的 coroutine / handler
  cancellation 当前又进入 `FAILED`。
- 如果 obsolete Run 也叫 `CANCELLED`，审计、指标和恢复逻辑将无法只凭 status
  区分“新状态取代旧 Run”“用户取消目标”“请求通道取消”“进程关闭”。
- 未来若真正需要 Run cancellation，还要再次拆 reason 或迁移历史含义。

因此 `CANCELLED` 不适合作为 obsolete Run 的首选名称。若未来引入，它应只表示
明确的 cancellation 语义，不能与 `SUPERSEDED` 互为别名。

## 5. 方案 B｜扩展 `INCOMPLETE`

建议表达：

```text
AgentRunStatus.INCOMPLETE
StopReason.STATE_OR_BINDING_INVALIDATED
AgentRunResult = absent
Task / RequestUnit mutation = absent
```

优点：

- 不新增 `AgentRunStatus` 枚举成员。
- 所有“没有普通用户结果的 Run”表面上归入一个状态。

主要代价：

1. 当前 `INCOMPLETE` 已有精确含义：process restart detected。必须放宽
   `AgentRunRecord`、recovery command、closure validator 和大量测试。
2. restart recovery 会把 active Task 置为 `BLOCKED`；obsolete Run 明确不得覆盖
   新 Task。相同 status 下必须在每个 reader / reducer 根据 stop reason 重新分支。
3. `incomplete_reason`、运行指标和诊断会同时表示“进程中断、需要恢复证据”和
   “已确定永久 obsolete”，语义相反。
4. 任一遗漏 stop-reason 分支都可能把 obsolete Run 误送进 restart recovery，
   或把 restart Run 误判为无需处理的 superseded terminal。
5. exact evidence closure 当前把 `INCOMPLETE` 与
   `PROCESS_RESTART_DETECTED + BLOCKED` 写成 closed matrix；扩展后的兼容与 migration
   面大于新增专用状态。

因此“少一个 Enum 值”没有减少整体状态机复杂度，只把复杂度转移到每个
`INCOMPLETE` consumer。

## 6. 对比矩阵

| 维度 | `SUPERSEDED` | `CANCELLED` | 扩展 `INCOMPLETE` |
|---|---|---|---|
| 业务 / 运行语义 | 精确表达“被新权威状态取代” | 容易与用户、通道、handler 取消混淆 | 把永久 obsolete 与 restart interruption 混合 |
| 与当前 contract 冲突 | 新增闭合分支 | 新增闭合分支且命名冲突 | 直接放宽现有 restart-only invariant |
| Task no-overwrite | 可由独立 finalizer 强制 | 可由独立 finalizer 强制 | 必须与 restart 的 Task=`BLOCKED` 分支并存 |
| restart recovery 隔离 | 清晰；不属于 `INCOMPLETE` | 状态清晰但 cancellation reason 复杂 | 高风险；每个 consumer 必须按 reason 分流 |
| Trace structure | 可保持不变 | 可保持不变 | 可保持不变 |
| `RunStopped` 语义 | 需批准 audit-only `BLOCKED` | 同左 | 同左，且要拆 restart / obsolete |
| 持久化 / decoder | 新 terminal value 与 closed matrix | 新 terminal value 与 closed matrix | 旧 value 新含义；兼容审计更难 |
| Eval / 指标可解释性 | 最强 | 中等 | 最弱 |
| 未来显式 Run cancel | 可独立增加 `CANCELLED` | 已占用并混义 | 仍需新增或继续堆 reason |

## 7. 用户批准的裁决

**已批准 A1：新增 `SUPERSEDED`，不使用 `CANCELLED`，不扩展
`INCOMPLETE`。**

理由：

- obsolete 是由更新的 authoritative state 取代，不是“执行没有完成”的未知状态。
- 可以保留 `INCOMPLETE = PROCESS_RESTART_DETECTED` 的现有 closed invariant，降低
  recovery、persistence 和 Eval 误分流风险。
- `SUPERSEDED` 让 no-result / no-Task-or-RequestUnit-write 形成独立 finalization
  shape，最容易
  机械证明四项已批准不变量。
- `CANCELLED` 可以留给未来明确的用户 / Runtime cancellation contract，不提前混义。

用户在当前 Codex task 批准的 exact ruling：

```text
OA-10 采用 AgentRunStatus.SUPERSEDED +
StopReason.STATE_OR_BINDING_INVALIDATED 表达已被更新状态或绑定取代的旧 Run。
该 Run 不产生 AgentRunResult、ASSISTANT Message 或 ResponseRendered，不更新 Task /
RequestUnit；以独立 conditional finalization 原子关闭 Run / link，并 append-only
保存 RunStopped audit evidence。RunStopped 复用现有 shared TraceEvent structure，
user_outcome=BLOCKED 仅作 audit disposition，不代表已向用户发送 BLOCKED。
CANCELLED 保留给未来显式 cancellation 语义；INCOMPLETE 继续只允许
PROCESS_RESTART_DETECTED。unknown / contradictory reason fail closed。
```

## 8. 已准备、尚未关闭的 owner impact

用户批准 exact ruling 后，当前工作树已准备以下 owner-alignment draft；在独立
exact-file review 与合并前均不视为 `CLOSED`：

- `PROJECT_DIRECTION.md`：Run lifecycle、no-result finalization 与共享 Trace
  projection。
- `docs/architecture/memory-design-reference.md`：record closure、link、恢复与
  append-only evidence。
- `docs/architecture/tool-calling-design-reference.md`：state / binding invalidated
  retry recovery 到 Run terminal 的边界。
- `docs/evaluation/agent-evaluation-strategy.md` 与 Coverage Matrix：no-result
  trajectory evidence，不伪造普通 HTTP Result。
- Cycle 2 scoped Spec：`RM-I01/I04/I05` exact status、stop reason、assertion 与
  physical mapping。
- scoped Spec 已把后续 Core、Application、Persistence、Eval、migration 和 tests
  的目标义务写成合同；本轮没有创建这些实现。

Persistence / Memory impact analysis 的结论是：`record_schema_version` 同时表示
结构与语义，OA-10 改变了 Run、link 与 `RunStopped` 的 closed matrix，因此目标
逻辑版本必须是：

```text
agent_run_record.p0.v1     → agent_run_record.p0.v2
run_task_link_record.p0.v1 → run_task_link_record.p0.v2
trace_event_record.p0.v1   → trace_event_record.p0.v2
```

Trace v2 不新增 shared `TraceEvent` 字段。link v2 允许
`result_task_state_version=null` 与 parent Run=`SUPERSEDED` 共同形成 no-result
terminal closure；它不能写入新 Run 的 Task version。P0 exact-version-only 要求
Activation 前冻结显式 v1→v2 migration、原子 cutover、完整 record-graph validation
与 rollback fence，禁止 mixed active versions、read-time fallback 和无法表示 v2
语义的 downgrade。本次只记录 logical contract 和 migration obligations，没有
创建 physical migration、decoder 或 backward-compatibility runtime。

## 9. Gate

在 owner-alignment 文字完成独立 exact-file review 并合并之前：

```text
OA-10 user ruling = APPROVED
OA-10 owner alignment = DRAFT_PREPARED / NOT_CLOSED
Cycle 2 scoped Spec = REVIEW_DRAFT
Activation = BLOCKED
Planning = NOT_STARTED
E2E01-02/03/05/06 = CONTRACT_DEFINED
```

不得创建 Plan、Task Packet、Worktree、feature branch、migration、功能代码、测试
或 Eval artifact。
