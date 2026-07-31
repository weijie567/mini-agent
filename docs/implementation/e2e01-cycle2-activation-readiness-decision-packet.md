# E2E-01 Cycle 2｜Activation Readiness Decision Packet v0.1

> **NON_NORMATIVE / USER_RULINGS_RECORDED / OWNER_ALIGNMENT_DRAFT_PREPARED / OA10_USER_APPROVED / R1_FINDINGS_REMEDIATED / R2_VERDICT_FAIL / R2_FINDINGS_REMEDIATED / R3_VERDICT_FAIL / R3_FINDINGS_REMEDIATED / R4_VERDICT_FAIL / R4_FINDING_REMEDIATED / R5_VERDICT_FAIL / R5_FINDING_REMEDIATED / R6_EXACT_FILE_REVIEW_PENDING / ACTIVATION_BLOCKED**
>
> 本文只帮助用户裁决 `OA-01..OA-11` 的 owner-alignment 路线，不是 active
> implementation contract，不修改任何 canonical owner、Phase 状态、Case
> lifecycle、Plan、Task Packet、Worktree、源码、测试或 Eval artifact。
>
> 用户已经对 `OA-01..OA-11` 作出本文件第 7 节记录的分项裁决；用户批准不等于
> owner alignment 已合并。只有后续 canonical owner alignment 变更经过独立审阅
> 并合并，才能把对应 `OA-*` 标为 `CLOSED`。`OA-10` exact Run terminal 推荐方案
> 已获用户批准。第一轮 owner-alignment exact-file review 的 `1 BLOCK + 2 HIGH +
> 1 LOW` 已按用户授权定向修订；第二轮 review 的 verdict 为
> `FAIL / 1 BLOCK + 1 HIGH`，也已按用户授权作最小修订。第三轮 review 的 verdict
> 为 `FAIL / 1 HIGH + 1 MEDIUM + 1 LOW`；用户已裁决 `CF-13` exact owner 语义，
> 本轮只修订对应 mapping、三个 fixture identity 和历史 SHA provenance 标签。
> 第四轮 review 的 verdict 为 `FAIL / 1 HIGH`：Cycle 2 delta Mapper 遗漏 imported
> Phase 1 `GATE_REJECTED` 与 `ORDER_SERVICE_UNAVAILABLE` 合同。用户已授权只修
> Phase 2 import / delta 边界，不修改 Phase 1 Spec、代码或共享 owner。第五轮
> review 的 verdict 为 `FAIL / 1 HIGH`：Phase 1 order success 与 process restart
> 仍被 `RM-17/RM-I03` 重复拥有；本轮把它们改为 imported reference rows，并继续
> 保持 Phase 1 与共享 owner 只读。第六轮 review 尚未完成，本 Packet 不能自证
> Activation Readiness。

- **Created:** 2026-07-31
- **Target phase:** Phase 2｜Cycle 2｜完成 E2E-01
- **Target contract:** [E2E-01 Cycle 2 Implementation Spec](e2e01-cycle2-implementation-spec.md)
- **Repository HEAD at analysis:** `8f73b1ef89444bbdccbc50777394bcc420b42b3f`
- **Historical single-spec R3-reviewed target SHA-256:** `eeae4923c771a1ffababba1d17c6aa30b6627318aabfae4e839d7f29d8c71520`
- **Historical single-spec M-01-remediated target SHA-256:** `5209c968302293b83e67c1a861d31c1a5218028fcdc6f6d58b35c7f8faff2732`
- **Current owner-aligned draft SHA-256:** `f25a7cab888fe7a5c59f6e664f25130f802bdab2ff7108507e25f0f77b60ba55`
- **OA-10 decision brief SHA-256:** `c8b6f6f75e2980838ec54577a051df4f1bed1e2b5f1b48990ba00c0545541183`
- **Owner-alignment R1 verdict:** `FAIL / 1 BLOCK + 2 HIGH + 1 LOW`
- **R1 remediation scope:** `RM-I05 fail-closed；tool_call_record.p0.v2；13th OA-10
  Trajectory；Coverage wording`
- **Owner-alignment R2 verdict:** `FAIL / 1 BLOCK + 1 HIGH`
- **R2 remediation scope:** `RequestUnit canonical fence；RM-I01/I04 exclusive
  recovery shape；RM-14 born-stale success-only scope`
- **Owner-alignment R3 verdict:** `FAIL / 1 HIGH + 1 MEDIUM + 1 LOW`
- **R3 remediation scope:** `CF-13 owner semantics 与 exact row trigger；3 个
  longitudinal fixture identities；historical single-spec SHA provenance label`
- **Owner-alignment R4 verdict:** `FAIL / 1 HIGH`
- **R4 remediation scope:** `完整 import Phase 1 post-Run mapper；Phase 2 table
  只拥有 delta；RM-12 exclude imported paths；C2-MAPPER-01 验证 union`
- **Owner-alignment R5 verdict:** `FAIL / 1 HIGH`
- **R5 remediation scope:** `import Phase 1 §8.1 order success + §10.4 restart；
  remove RM-17/RM-I03 from delta；four imported regression refs`
- **Owner-alignment R6 review:** `PENDING`
- **Current mechanical recheck:** `PASS`（`git diff --check`；14 个 longitudinal /
  13 个 Trajectory，且每个 Trajectory 恰有一个 `REQ_STOP`；9 个 JSON blocks；
  12 个引用 `CF-13` 的 exact rows 均含 model / Presentation bypass predicate；
  4 个 imported Mapper refs 均存在且 `RM-17/RM-I03` 不在 delta table，union
  ownership 机械检查通过；10 个目标 Markdown 的 180 个本地链接和 58 个
  fragment 为 0 error；独立 semantic R6 review 仍为 `PENDING`，本检查不是独立
  exact-file review，也不是 Activation PR 的 exact-head review）
- **Phase 2 status:** `PLANNED_MAPPING_ONLY`
- **Target Case lifecycle:** `E2E01-02/03/05/06 = CONTRACT_DEFINED`
- **Activation:** `NOT_STARTED`

## 1. 本次审批要决定什么

本次只决定：

1. 每个 `OA-*` 应由上游 owner 增加通用规则、条件式委托 scoped encoding，还是
   只确认现有规则已经覆盖。
2. 哪些精确字段、数值、truth table 和 Eval encoding 应继续只由 scoped
   implementation spec 拥有，避免在多个 owner 中复制第二套正文。
3. 哪些当前差异是显式 contract evolution，不能被实现或 Plan 静默吸收。
4. 后续 owner-alignment 变更应满足的可证伪关闭条件。

本次不决定：

- canonical owner 的最终文字或 commit。
- scoped contract Activation。
- Phase 2 Plan、Task Packet、Wave、branch、Worktree 或 `base_sha`。
- Python DTO、Port、migration、Fixture、测试或产品代码。
- Case 从 `CONTRACT_DEFINED` 进入 `EXECUTABLE`。

## 2. 证据分类与裁决词汇

本文使用：

- `CONFIRMED`：当前 active owner、源码或状态文件中可以直接复核。
- `CONTRACT_GAP`：草案需要的语义尚未由 active owner 精确拥有。
- `RECOMMENDED`：本 Packet 初版中的建议标签；当前以第 7 节用户裁决为准，不能再
  用该标签推断审批状态。
- `USER_APPROVED`：用户已批准建议方向，但不表示 owner 文档已经审阅、合并或
  `CLOSED`。
- `CONDITIONALLY_APPROVED`：用户批准方向并同时冻结 owner / scoped
  implementation 的分工条件。
- `USER_APPROVED / OWNER_RULE_EVOLUTION`：用户已批准 exact owner semantics，但
  owner 文档仍需独立 review 与合并后才 `CLOSED`。
- `OPEN`：尚未取得可追溯裁决或合并证据。

建议裁决类型：

| 类型 | 含义 |
|---|---|
| `OWNER_RULE_EVOLUTION` | canonical owner 增加新的通用语义、不变量或生命周期规则 |
| `SCOPED_DELEGATION` | owner 保留通用规则，只把 Phase 2 exact encoding 条件式委托给目标 Spec |
| `REFERENCE_CONFIRMATION` | 既有 owner 已覆盖通用语义；只确认引用与 scoped Schema 边界，不改写规则 |
| `LIFECYCLE_HOLD` | 批准合同映射但保持 Case 为 `CONTRACT_DEFINED` |
| `BLOCK` | owner 拒绝或无法唯一裁决；Spec 返回 `REVIEW_DRAFT` 修订，不得 Activation |

`SCOPED_DELEGATION` 必须同时写清：

- 只适用于 `E2E01-02/03/05/06`。
- 只在目标 Spec 正式 Activation 后生效。
- 不把 exact encoding 升级为整个 P0 的通用语义。
- Business、Intent、Tool、Memory、Eval 或 Core Trace 的通用不变量仍由原 owner
  保留。

## 3. 总体裁决摘要

| Alignment | 当前判断 | 用户裁决 | Activation 前最低证据 |
|---|---|---|---|
| `OA-01` | 通用业务流程已存在；exact 搜索编码缺失 | `USER_APPROVED / SCOPED_DELEGATION` | Business / Intent 条件式委托 exact 窗口、matching、alias、排序与上限 |
| `OA-02` | 最小披露原则已存在；候选域白名单缺失 | `USER_APPROVED / SCOPED_DELEGATION` | Business / Memory / Presentation 明确各可见域只消费目标 Spec 的 exact projection |
| `OA-03` | InputBinding、Observation、CAS 通则已存在；候选选择能力闭包缺失 | `USER_APPROVED / OWNER_RULE_EVOLUTION + SCOPED_DELEGATION` | Intent / Memory / Core Runtime 批准 ordinal binding、私有 target mapping、版本与恢复语义 |
| `OA-04` | `get_shipment` 在 Catalog；active Package cardinality 未定义 | `USER_APPROVED / OWNER_RULE_EVOLUTION + SCOPED_DELEGATION` | Business 批准 `0..1` invariant；Tool 委托 exact Schema / outcome |
| `OA-05` | Observation freshness 通则已存在；Shipment exact truth table 缺失 | `USER_APPROVED / OWNER_RULE_EVOLUTION + SCOPED_DELEGATION` | Business 批准字段交叉不变量；Memory 批准 birth-stale / 5-minute scoped policy |
| `OA-06` | 四类物流结果已存在；确定性 precedence / replay 缺失 | `CONDITIONALLY_APPROVED` | Business 拥有 120 小时、precedence、业务含义；Spec 只拥有编码 / shape / reason serialization / rule version / vectors |
| `OA-07` | Tool 有有限重试通则；attempt truth table 与 recovery record 缺失 | `CONDITIONALLY_APPROVED` | Tool 演进通用 attempt / retry / recovery；logical child 变化推进 `tool_call_record.p0.v2`；Spec 保留 500ms / max 2 / exact retryable codes；shared Trace structure 不变 |
| `OA-08` | `source_version` 通则已存在；三个 source authority 的 exact producer 缺失 | `CONDITIONALLY_APPROVED` | Business 拥有 source authority 语义；Spec 拥有具体 producer implementation / canonical bytes |
| `OA-09` | 公私 DTO、ToolSpec 与 toolset hash 分离已存在 | `USER_APPROVED / REFERENCE_CONFIRMATION + SCOPED_DELEGATION` | 确认无需改通用规则，只委托两个 Tool 的 exact schemas |
| `OA-10` | 用户结果集合已存在；Phase 2 mapper、stop reason 与 obsolete Run 语义缺失 | `USER_APPROVED / OWNER_RULE_EVOLUTION` | `SUPERSEDED + STATE_OR_BINDING_INVALIDATED`；no result / no Task or RequestUnit write；audit-only `RunStopped.user_outcome=BLOCKED`；v2 record migration contract |
| `OA-11` | EvalCase / lifecycle 通则与四个 Case 已存在；physical mapping 缺失 | `USER_APPROVED / SCOPED_DELEGATION + LIFECYCLE_HOLD` | Eval owner 委托 exact 14 longitudinal + 13 Trajectory encoding，同时明确 Case 仍为 `CONTRACT_DEFINED` |

汇总：

```text
USER_APPROVED:             OA-01 / OA-02 / OA-03 / OA-04 / OA-05 / OA-09 / OA-11
CONDITIONALLY_APPROVED:     OA-06 / OA-07 / OA-08
USER_APPROVED/EVOLUTION:    OA-10
```

用户裁决不等于 owner alignment `CLOSED`。任一变更未通过独立 exact-file review /
合并时，不能用“实现细节”绕过；目标 Spec 与 Activation 继续 `BLOCKED`。

## 4. 逐项裁决记录

### OA-01｜订单搜索窗口、matching 与稳定候选

**Current — CONFIRMED**

- Business owner 已定义本人范围的自然语言近期订单搜索、唯一候选与多候选路径：
  [Business E2E-01](../business-capabilities.md#41-e2e-01订单定位物流查询与配送异常判断)。
- Intent owner 已定义 Candidate Input、指代输入，以及“可先安全搜索、再在多候选时
  询问”的通用边界：
  [InputBinding](../architecture/intent-design-reference.md#10-slot--input-binding-设计)。

**Gap — CONTRACT_GAP**

active owner 未精确拥有 90 天、最多 5 个、NFKC / casefold、substring、category /
alias authority、稳定排序、截断和 refinement。它们当前只存在于目标 Spec
[§7.1–7.2](e2e01-cycle2-implementation-spec.md#71-可信时间和搜索窗口)。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Business owner 条件式委托 Phase 2 exact search semantics；同时确认 alias authority
  必须来自版本化受控配置或 Fixture，不能由模型、用户消息或当前实现偶然产生。
- Intent owner 确认 query description 仍是 Candidate / Claim；搜索结果经过业务
  owner 验证后才能形成 target ref。
- exact 数值、normalization、matching、排序和 truncation 只保留在目标 Spec。

**Closure check**

- [ ] Business 与 Intent 都有可追溯的条件式 delegation。
- [ ] owner 文档没有复制第二套 matching truth table。
- [ ] owner 拒绝任一 D1 输入时，`OA-01=BLOCK` 并修订目标 Spec。

### OA-02｜候选最小披露与可见域

**Current — CONFIRMED**

- Business owner 要求本人候选只展示最小摘要，并要求事实值由确定性代码注入：
  [业务与安全规则](../business-capabilities.md#6-关键业务与安全规则)、
  [用户可见结果](../business-capabilities.md#71-用户可见结果)。
- Project Direction 已区分 `RuntimePrivateContext` 与 `ModelVisibleContext`：
  [CustomerContext 与模型隐私边界](../../PROJECT_DIRECTION.md#8-customercontext-与模型隐私边界)。
- Memory owner 已区分 Observation 的来源、可见性与受限 raw result：
  [Observation](../architecture/memory-design-reference.md#9-observation-与-evidence)。

**Gap — CONTRACT_GAP**

候选专用的 Agent-visible、HTTP、Renderer、Observation、普通 Trace 与 audit-only
白名单，以及 UTC 日期、最多 3 个 matching items 和禁止 count 字段，尚无 active
exact owner。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- 三个 owner 保留通用隐私和最小披露规则，条件式委托目标 Spec
  [§7.2.2](e2e01-cycle2-implementation-spec.md#722-agent-visible-output-与各可见域白名单)
  拥有 Phase 2 exact whitelist。
- 不扩大全局 `OrderSummaryProjection`，不把候选 projection 复制到 Memory 或
  Trace owner。
- Presentation / Channel 只能消费 approved safe projection，不能读取
  Runtime-private result 再自行删字段。

**Closure check**

- [ ] 各可见域的 producer 与 consumer 唯一。
- [ ] model / HTTP / Renderer / ordinary Trace 均无 target mapping、owner scope、
  source token、raw payload 或未批准 count。

### OA-03｜候选集、序号绑定、CAS 与恢复闭包

**Current — CONFIRMED**

- Intent owner 已拥有 Candidate Input、`verified_target_ref` 和 current binding：
  [§10.3–10.4](../architecture/intent-design-reference.md#103-candidate-input-最小字段)。
- Memory owner 已拥有 Task working context、Observation ref、CAS、supersession 和
  owner-scoped exact read 通则：
  [Task Working Context](../architecture/memory-design-reference.md#8-l2-task-working-context)、
  [并发与版本](../architecture/memory-design-reference.md#143-并发与版本)、
  [owner-scoped read](../architecture/memory-design-reference.md#1522-owner-scoped-结果可信范围与诊断)。

**Gap — CONTRACT_GAP**

当前 owner 没有定义 durable candidate selection capability、runtime-private
`candidate_ref → owner-scoped target` mapping、current-set uniqueness、selection
expected version、exact hash、原子选择、重启恢复和 closed-set 校验。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Intent owner 增加通用 ordinal-reference 规则：只有当前 Task 唯一、未过期、
  未 supersede、版本匹配的候选能力才能生成 verified target。
- Memory owner 增加 candidate capability 的 authority、visibility、durability、
  supersession、owner-scoped recovery 和 fail-closed record-graph 规则。
- Core Runtime / Project Direction owner 明确 `OrderCandidateSetRecord` /
  `OrderCandidateSelectionRecord` 的 shared Task-state ownership；具体 DTO、
  content hash、15 分钟 TTL 和 field mapping 委托目标 Spec
  [§7.3–7.4](e2e01-cycle2-implementation-spec.md#73-searchordersobservation-与-ordercandidatesetrecord)。

**Closure check**

- [ ] CandidateSet 不复制业务事实或 target。
- [ ] target mapping 对模型、Renderer、HTTP 和普通 Trace 不可见。
- [ ] restart 后可以在同一 owner / Task / Observation / version 闭包内唯一解析。
- [ ] 任一 missing、duplicate、expired、wrong-owner 或 CAS mismatch 都不调用业务
  Tool。

### OA-04｜`get_shipment` 与 active Package cardinality

**Current — CONFIRMED**

- `get_shipment` 已属于 P0 Tool Catalog：
  [Business Tool Catalog](../business-capabilities.md#52-p0-tool-catalog)。
- Business E2E-01 已要求物流目标查询关联 Package，但没有定义 active Package
  cardinality。

**Gap — CONTRACT_GAP**

`get_shipment(order_id)`、owner-scoped Order → active Package 的 `0..1` invariant，
以及多 active Package 的 deterministic integrity failure 尚未由 active Business
owner 裁决。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Business owner 增加 P0 `0..1 active Package per Order` 规则；`>1` 是内部 source
  integrity failure，不得选择任一 Package，也不得披露数量。
- Tool owner 条件式委托目标 Spec
  [§7.5.1–7.5.2](e2e01-cycle2-implementation-spec.md#751-inputowner-relation-与-agent-visible-output)
  拥有 Agent-visible Schema、Runtime-private query/result 和 exact outcome code。
- verified `order_id` 只能来自 current binding / selected target，`customer_id`
  继续由服务端注入。

**Closure check**

- [ ] zero / one / multiple active Package 各有唯一 outcome。
- [ ] cardinality violation 不重试、不形成 Shipment Observation、不泄露 Package。
- [ ] 如果 Business owner 不接受 `0..1`，`OA-04=BLOCK`，不得由实现挑选 Package。

### OA-05｜Shipment projection、时间不变量与 freshness

**Current — CONFIRMED**

- Business owner 要求配送异常只基于最新可信物流 Observation。
- Memory owner 已规定物流在诊断前按 TTL 刷新、Observation 分离
  `observed_at / recorded_at / valid_until`：
  [Observation 字段](../architecture/memory-design-reference.md#92-observation-建议字段)、
  [新鲜度](../architecture/memory-design-reference.md#141-新鲜度)。

**Gap — CONTRACT_GAP**

Shipment 字段组合、status/event-time 交叉不变量、5 分钟 TTL、读取即 stale、
`FACTS_INSUFFICIENT` 与 source integrity failure 的边界尚未由 owner 精确裁决。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Business owner 增加 P0 Shipment 事实有效组合与“缺事实”和“矛盾事实”不可混用的
  规则。
- Memory owner 明确 birth-stale result 不形成新的 standard Observation，旧
  Observation 也不能作为 fallback；exact 5 分钟 TTL 和字段编码委托目标 Spec
  [§7.5.3–7.7](e2e01-cycle2-implementation-spec.md#753-shipment-projection-truth-table)。

**Closure check**

- [ ] fresh / stale 的判定只使用可信时钟。
- [ ] contradictory source 进入 integrity failure；合法但不足进入
  `FACTS_INSUFFICIENT`。
- [ ] stale refresh failure 不产生新的事实，也不复用旧事实完成目标。

### OA-06｜确定性物流 Assessment

**Current — CONFIRMED**

- Business owner 已要求 `NORMAL / DELAYED / STALLED / DELIVERED_NOT_RECEIVED`
  四类判断，但未定义 exact precedence、阈值和 reason code。
- Memory owner 已区分 Claim、Observation 与 Deterministic Derivation，并要求纠正
  和新版本使旧派生结果失效。

**Gap — CONTRACT_GAP**

120 小时阈值、四类 precedence、Claim current binding、可信 `assessed_at`、
`rule_version`、reason code、supersession 与 replay 尚无 active exact owner。

**Ruling — CONDITIONALLY_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Business owner 拥有 120 小时停滞阈值、
  `DELIVERED_NOT_RECEIVED > STALLED > DELAYED > NORMAL` primary-result
  precedence 和四类结果的业务含义。
- Memory owner 增加 deterministic derivation 必须绑定 exact Observation、Claim、
  rule version 和 trusted time，并通过新记录 supersede、不得原地覆盖的通则。
- 目标 Spec [§7.8](e2e01-cycle2-implementation-spec.md#78-确定性-shipmentassessment)
  只拥有具体编码、record shape、reason code serialization、`rule_version` 与测试
  向量；不能把这些实现编码反向升级为 Business owner。

**Closure check**

- [ ] 同一输入、rule version 和可信时间产生唯一 primary result / reason code。
- [ ] 用户“未收到”保持 Claim；没有 current target binding 时先 `ASK_USER`。
- [ ] replay 不刷新 `assessed_at`，Observation / Claim / rule 变化使旧 assessment
  失效。

### OA-07｜attempt-level timeout、retry 与 crash recovery

**Current — CONFIRMED**

- Tool owner 已拥有有限 timeout、Read retry、durable dispatch fence、ToolCall /
  ToolAttempt 和 interruption 通则：
  [ToolCall lifecycle](../architecture/tool-calling-design-reference.md#9-toolexecutor-与-toolcall-生命周期)、
  [timeout / retry / interrupt](../architecture/tool-calling-design-reference.md#10-超时重试与中断)。
- Tool owner 明确把每个 Tool 的 numeric timeout、attempt 数和 transient code 留给
  scoped implementation contract：
  [尚待实现阶段裁决](../architecture/tool-calling-design-reference.md#17-尚待实现阶段裁决)。
- 当前 `ToolAttemptRecord` 尚不能表达 attempt-level `timeout_phase` 或
  `retry_decision`；这是 proposal，不是已实现事实。

**Gap — CONTRACT_GAP**

attempt finalize truth table、`TIMEOUT ⇔ TOOL_CALL_TIMEOUT ⇔ timeout_phase present`、
retry-decision persistence、timeout→success 历史、recovery decision 和 no-progress
闭包需要 Tool owner 演进。

**Ruling — CONDITIONALLY_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Tool owner 增加 attempt-level completion / retry / recovery 语义；500ms、最多
  2 attempts 和 exact retryable codes 仍委托目标 Spec
  [§7.9](e2e01-cycle2-implementation-spec.md#79-超时与有限重试)。
- `ToolAttemptRecord` 是 `ToolCallRecord` logical child；child 新增
  `timeout_phase` / `retry_decision` 与 closed matrix，按已批准版本规则推进父记录
  为 `tool_call_record.p0.v2`，不建立独立 top-level attempt record。Activation 前
  必须冻结 v1→v2 conversion、atomic cutover、失败原子性和 rollback fence。
- shared `TraceEvent` structure 不变；attempt / recovery 专项 payload 继续归 Tool
  owner。若实现设计还需改变共享 Trace 字段或公共结构，必须另行提交影响分析并
  取得 Core Runtime / Project Direction owner 裁决。
- Eval owner 只消费 Tool / Trace 事实并断言，不反向拥有 timeout 或 retry 语义。

**Closure check**

- [ ] truth table 对全部 finalized attempt 组合是完整且互斥的。
- [ ] attempt 1 timeout、attempt 2 success 时保留 attempt 1 的 timeout 与 retry
  evidence。
- [ ] restart 不倒填未观察到的 outcome；不会创建第三次 attempt 或第二个同语义
  ToolCall。
- [ ] `tool_call_record.p0.v2` conversion 保留 parent refs、status、
  `attempt_count`、child identity / order 与既有 outcome；新增字段只按 Tool owner
  exact conversion table 唯一重建，无法唯一重建则 migration fail closed，不允许
  默认补值或 mixed active versions。

### OA-08｜source-version authority 与传播链

**Current — CONFIRMED**

- Memory Observation 已有 `source_resource_ref` 与 `source_version` 通则。
- Tool owner 已区分 safe ToolResult 与受限 `raw_result_ref`，并禁止原始结果直接
  进入 Prompt。
- Project Direction 已明确 adapter 不能从物理形状发明 semantic contract。

**Gap — CONTRACT_GAP**

order candidate、search snapshot 和 Shipment source version 的唯一 producer、
canonical bytes、传播链、受限 reader 和禁止消费者只在目标 Spec 中精确存在。

**Ruling — CONDITIONALLY_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- Business owner 拥有 source authority 语义：权威来自受控业务系统在可信 owner
  scope 下完成的一次读取；消费者不得从展示字段、数据库时间或当前代码重新计算
  authority。具体 Infrastructure Adapter 类不是业务 canonical owner。
- Memory owner 条件式委托 exact Observation propagation、restricted target mapping
  和 version binding。
- Tool owner 条件式委托 Runtime-private result / restricted raw ref 的 exact
  传播；model-visible toolset hash 继续只包含 ToolSpec。
- 具体 producer implementation 与 exact canonical bytes 留在目标 Spec
  [search version](e2e01-cycle2-implementation-spec.md#724-search-source-version-canonical-contract)、
  [Shipment version](e2e01-cycle2-implementation-spec.md#754-shipment-source-version-canonical-contract)。

**Closure check**

- [ ] 每个 version / snapshot ref 只有一个 producer。
- [ ] Search Observation、CandidateSet、Selection、Shipment Observation 和
  Assessment 的 version 传播可闭合验证。
- [ ] 任何 model / Renderer / HTTP / ordinary Trace 消费 authority metadata 都是
  `BLOCK`。

### OA-09｜Agent-visible 与 Runtime-private Tool contract 分离

**Current — CONFIRMED**

- Tool owner 已精确区分 `ToolSpec`、`ToolRegistration`、Runtime-private execution
  信息和 Provider-visible toolset：
  [核心概念](../architecture/tool-calling-design-reference.md#4-核心概念)。
- toolset hash 明确排除 Handler、身份、授权和其他 private 字段：
  [Hash 规范](../architecture/tool-calling-design-reference.md#54-hash-规范)。
- Business 与 Project Direction 已要求 owner validation、safe projection 和
  Runtime-private / Model-visible 分离。

**Gap — CONTRACT_GAP**

通用语义没有冲突；尚缺的是 `search_orders` / `get_shipment` 的 exact scoped
schemas、restricted raw result 与 source authority 应用。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- 采用 `REFERENCE_CONFIRMATION`：不修改上述通用规则。
- Business 与 Tool owner 只条件式委托两个 Tool 的 exact visible/private schemas
  给目标 Spec [§7.2、§7.5](e2e01-cycle2-implementation-spec.md#72-search_orders-可见性与-source-version-contract)。
- Project Direction 只增加 scoped owner 引用或影响说明，不复制 Schema。

**Closure check**

- [ ] `model_visible_toolset_hash` 只随 Provider-visible ToolSpec 变化。
- [ ] Runtime-private authority metadata、handler、owner scope 或 raw result 变化
  不单独改变 model-visible hash。
- [ ] Provider / business Adapter 不拥有第二套 DTO。

### OA-10｜Result Mapper、stop reason 与 obsolete Run

**Current — CONFIRMED**

- Business owner 已定义 `ASK_USER / COMPLETED / BLOCKED / NEED_HUMAN /
  NOT_FOUND_OR_NOT_ACCESSIBLE` 等用户结果：
  [用户可见结果](../business-capabilities.md#71-用户可见结果)。
- Project Direction 已把 `RunResultMapper` 放在 Application，并把 shared Run /
  Trace structure 交给 Core Runtime / Project Direction owner。
- 当前 Core `StopReason` 与 `AgentRunRecord` 只覆盖 Phase 1；特别是当前
  `INCOMPLETE` 只允许 `PROCESS_RESTART_DETECTED`。

**Gap — CONTRACT_GAP**

Phase 2 service unavailable、retry exhaustion、integrity、stale、facts insufficient
与 `INTERRUPTED` 的完整 mapper 仍需显式 owner evolution。obsolete Run 的四项安全
不变量与 exact terminal projection 已取得用户裁决，但 owner alignment 尚未完成
独立审阅 / 合并，源码和 persistence 仍只有 v1 Phase 1 matrix。

**Ruling — USER_APPROVED / OWNER ALIGNMENT NOT CLOSED**

- exact terminal 使用
  `AgentRunStatus.SUPERSEDED +
  StopReason.STATE_OR_BINDING_INVALIDATED`。obsolete Run 不产生
  `AgentRunResult`、ASSISTANT Message、`ResponseRendered` 或 Task / RequestUnit
  mutation；已发生的安全 audit evidence append-only 保留。
- 独立 conditional finalizer 只在 owner-scoped exact current closure 唯一证明旧
  Run obsolete 时 CAS 终止 Run、逻辑关闭 link 并 append `RunStopped`。
  `RunTaskLink.result_task_state_version=null`；不得复制新 Run 的 Task version。
- `RunStopped.user_outcome=BLOCKED` 仅作 audit disposition，shared
  `TraceEvent` structure 不变；`CANCELLED` 保留，`INCOMPLETE` 继续只对应
  `PROCESS_RESTART_DETECTED`。
- unknown / duplicate / contradictory / non-unique reason 不得进入
  `RunResultMapper`，不得猜测 `SUPERSEDED`、生成用户结果，或改变 Run terminal /
  link / Task / RequestUnit / ToolCall / attempt；现有执行保持 fenced，只进入受限
  integrity / operator-resolution path。
- [OA-10 Run Terminal State Decision Brief](e2e01-cycle2-oa10-run-terminal-state-decision-brief.md)
  保留方案比较与源码影响。根据 Project Direction 的逻辑版本规则，目标 records
  为 `agent_run_record.p0.v2`、`run_task_link_record.p0.v2` 与
  `trace_event_record.p0.v2`；Activation 前必须冻结 exact-version-only migration、
  atomic cutover 与 rollback fence，本轮不创建 migration。
- Application `RunResultMapper` 只消费最终批准的 truth table，不拥有业务或 Run
  lifecycle 语义。

**Closure check**

- [ ] 每个 allowlisted internal outcome / failure code 恰好命中一条 `RM-*`。
- [ ] 每个 `INTERRUPTED` 恰好命中一条 `RM-I*`。
- [ ] obsolete Run 不发送响应、不覆盖新 Task，但保留 append-only audit evidence。
- [ ] unknown / contradictory reason fail closed，不 fallback 到 completed 或
  safe-not-found。
- [ ] v2 Run / link / Trace closure 与 v1→v2 migration / rollback contract 可机械
  验证，且 shared Trace 字段结构未改变。
- [ ] mandatory OA-10 Trajectory 同时证明 `SUPERSEDED`、null link result、
  audit-only `RunStopped(BLOCKED)`、attempt 2 absent，以及 no Agent result /
  Message / ResponseRendered / Task mutation。

### OA-11｜EvalCase mapping、Trajectory 与 lifecycle

**Current — CONFIRMED**

- Eval owner 已定义通用 `EvalCase`、Dataset、Result、Critical failure 与 lifecycle：
  [EvalCase](../evaluation/agent-evaluation-strategy.md#5-通用-evalcase-契约)、
  [Case lifecycle](../evaluation/agent-evaluation-strategy.md#51-case-生命周期)。
- Coverage Matrix 已拥有 `E2E01-02/03/05/06` 的业务期望、Critical failure 和
  Cycle 2 顺序：
  [E2E-01 cases](../evaluation/p0-eval-coverage-matrix.md#31-e2e-01订单定位物流查询与配送异常)、
  [Cycle 2](../evaluation/p0-eval-coverage-matrix.md#cycle-2完成-e2e-01)。

**Gap — CONTRACT_GAP**

14 个 longitudinal variants、13 个 mandatory non-HTTP trajectories、typed
predicate grammar、pair identity、完整 input / grading / version manifest 和
`CF-*` 引用尚无 active scoped encoding owner。

**Ruling — USER_APPROVED + LIFECYCLE_HOLD / OWNER ALIGNMENT NOT CLOSED**

- Eval Strategy owner 条件式委托目标 Spec
  [§9](e2e01-cycle2-implementation-spec.md#9-eval-contract) 拥有本阶段 exact
  physical encoding，但保留通用 EvalCase / Result / Grader 语义。
- Coverage Matrix owner批准四个 Case 与 14 variants / 13 trajectories 的 mapping；
  同时作出 `LIFECYCLE_HOLD`：合同和未来 artifacts 都不能自行把 Case 推进为
  `EXECUTABLE`。
- Intent、Tool、Memory、Business 与 Core Trace owner 只批准 predicate alias
  指向自身记录 / 事件；Eval 不复制或改写其字段语义。

**Closure check**

- [ ] 14 个 longitudinal + 13 个 trajectory Case 都可唯一编码。
- [ ] `E2E01-05` pair 使用相同 RegistrySnapshot、toolset hash、provider mapping
  和 fixture identity。
- [ ] Activation 后 Case 仍为 `CONTRACT_DEFINED`；只有 authenticated artifacts、
  loader、Harness result 和 Coverage Matrix owner 后续裁决才能进入
  `EXECUTABLE`。

## 5. 当前 owner-alignment 顺序与状态

本节只是依赖顺序，不是 Phase 2 Plan 或 Task Packet。

```text
用户分项裁决已记录
  ↓
OA-10 SUPERSEDED exact ruling 已批准
  ↓
全部 OA 的 owner-alignment draft 已准备
  ↓
R1 exact-file review = FAIL（1 BLOCK + 2 HIGH + 1 LOW）
  ↓
用户授权的 R1 remediation 已准备
  ↓
R2 exact-file review = FAIL（1 BLOCK + 1 HIGH）
  ↓
用户授权的 R2 最小 remediation 已准备
  ↓
R3 exact-file review = FAIL（1 HIGH + 1 MEDIUM + 1 LOW）
  ↓
用户裁决 CF-13，并授权 R3 remediation
  ↓
R4 exact-file review = FAIL（1 HIGH）
  ↓
用户授权 R4 remediation：Phase 1 import + Phase 2 delta
  ↓
R5 exact-file review = FAIL（1 HIGH）
  ↓
同一授权范围内修复 order-success / restart import overlap
  ↓
cross-file conflict scan + R6 独立 owner-alignment exact-file review
  ↓
owner-alignment merge
  ↓
独立 Activation PR（此时才允许创建）
```

当前 draft 已按 Business → Intent / Memory / Core Runtime → Tool → Eval 的 owner
依赖顺序准备。OA-10 不再等待用户选项，但 exact-file review、owner-alignment
merge 与后续 Activation gate 仍逐项阻断；不得因为裁决已记录就跳到 Activation。

写入型 owner alignment 必须遵守一个文件一个明确 writer、single-writer 热点串行和
独立 PR；本文不预建 branch、Worktree、Packet 或 SHA。

## 6. Cross-file impact inventory

用户批准后，本轮已准备下列 owner-alignment draft。这里的“已准备”只表示当前
working tree 有未合并文档变更，不表示独立 review、commit、PR 或 merge：

| 文件 | 作用 | 当前是否修改 |
|---|---|---:|
| `docs/business-capabilities.md` | `OA-01/02/04/05/06/08/09` Business ruling；`OA-10` no-outbound-result 边界并引用 Core lifecycle | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `PROJECT_DIRECTION.md` | Core Runtime、Application mapper、strict unknown-reason fence（含 Task / RequestUnit）、ToolCall / Run / link / Trace v2 records、shared Trace 与 scoped owner mapping | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `docs/architecture/intent-design-reference.md` | `OA-01/03` ordinal binding 与 delegation | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `docs/architecture/memory-design-reference.md` | `OA-02/03/05/06/08/10` record / freshness / recovery / no-result closure、按 Core owner 对齐的 Task / RequestUnit fence 与 v2 cutover | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `docs/architecture/tool-calling-design-reference.md` | `OA-04/07/08/09/10` Tool / attempt evolution、`tool_call_record.p0.v2`、Task / RequestUnit fence 与 invalidated recovery handoff | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `docs/evaluation/agent-evaluation-strategy.md` | `OA-07/10/11` 通用 Eval delegation 与 13-case no-result trajectory evidence | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `docs/evaluation/p0-eval-coverage-matrix.md` | `OA-10/11` exact 14 + 13 mapping、CF-13 owner trigger、Task / RequestUnit no-write evidence、lifecycle hold 与状态措辞 | `R5_REVIEWED_UNCHANGED / R6_PENDING` |
| `docs/implementation/e2e01-cycle2-implementation-spec.md` | 消费全部 owner ruling；import Phase 1 Mapper 且只拥有 Phase 2 delta；order success / restart 使用 imported refs；收紧 `RM-I05`、四类 v2 migration 与第 13 个 Trajectory；保持 `REVIEW_DRAFT` | `R5_FINDING_REMEDIATED / R6_PENDING` |
| `docs/implementation/e2e01-cycle2-oa10-run-terminal-state-decision-brief.md` | 保留三方案比较并记录用户批准 `SUPERSEDED` | `USER_APPROVED / STATUS_SYNCED / R6_PENDING` |
| `docs/implementation/e2e01-cycle2-activation-readiness-decision-packet.md` | 汇总用户裁决、R1/R2/R3/R4/R5 remediation、关闭证据和 review / Activation 边界；不自证 readiness | `R5_FINDING_REMEDIATED / R6_PENDING` |

只有 owner alignment 合并并准备 Activation PR 时，才评估：

- `AGENTS.md` active owner 清单。
- `.planning/ROADMAP.md`、`.planning/REQUIREMENTS.md`、`.planning/STATE.md` 的派生
  状态。
- `.planning/GOVERNANCE.md` 的 owner mapping。
- `.planning/ACTIVATION.md` 是否只需引用而不应覆盖其既有 GSD activation 历史。
- 架构 README / 图形是否真的受语义变化影响。

在正式影响扫描前，不把这些文件预先加入 allowlist，也不把“可能受影响”描述成
“必须修改”。

## 7. 用户审批 Gate

用户裁决及关闭状态如下：

| Alignment | 用户裁决 | Closure |
|---|---|---|
| `OA-01` | `APPROVED` | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-02` | `APPROVED` | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-03` | `APPROVED` | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-04` | `APPROVED` | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-05` | `APPROVED` | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-06` | `CONDITIONALLY_APPROVED`：Business owns 120h / precedence / business meaning | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-07` | `CONDITIONALLY_APPROVED`：Tool general semantics + `tool_call_record.p0.v2`；Spec exact budget / codes；shared Trace unchanged | `OWNER_ALIGNMENT_DRAFT_PREPARED / R1_FINDING_REMEDIATED / NOT_CLOSED` |
| `OA-08` | `CONDITIONALLY_APPROVED`：Business source authority；Spec producer implementation / canonical bytes | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-09` | `APPROVED` | `OWNER_ALIGNMENT_DRAFT_PREPARED / NOT_CLOSED` |
| `OA-10` | `APPROVED`：`SUPERSEDED + STATE_OR_BINDING_INVALIDATED`、no result / no Task or RequestUnit write、strict unknown-reason fence、audit-only `BLOCKED`、`INCOMPLETE` restart-only；Phase 1 Mapper imported unchanged，Phase 2 只拥有 delta | `OWNER_ALIGNMENT_DRAFT_PREPARED / R1_R2_R4_R5_FINDINGS_REMEDIATED / NOT_CLOSED` |
| `OA-11` | `APPROVED + LIFECYCLE_HOLD`：14 longitudinal + 13 Trajectory；`CF-13` 只覆盖模型 / Presentation / Renderer 绕过安全 projection 后自行生成、修改或错误表达 approved 订单 / 物流事实或 deterministic `ShipmentAssessment.primary_result` | `OWNER_ALIGNMENT_DRAFT_PREPARED / R1_R2_R3_FINDINGS_REMEDIATED / NOT_CLOSED` |

批准本 Gate 只授权准备 canonical owner alignment 变更；仍不授权 Activation、
Plan、Task Packet、Worktree 或功能代码。

## 8. Packet Acceptance Criteria

- [ ] `OA-01..OA-11` 每项都区分 Current、Gap、Recommendation 与 Closure check。
- [ ] 所有 owner 规则正文仍留在 canonical owner，目标 Spec 只接收明确的 scoped
  delegation。
- [ ] `OA-03/04/05/06/07/10` 被明确标记为 contract evolution，不能由实现偷渡。
- [ ] `OA-09` 不重复已有 Tool visibility / hash 规则。
- [ ] `OA-11` 明确保持四个 Case 为 `CONTRACT_DEFINED`。
- [ ] 本 Packet 不创建 Plan、Task Packet、branch、Worktree、源码、测试、migration
  或 Eval artifact。
- [ ] 用户批准、owner alignment、Activation exact-head review 和 Activation merge
  被保留为不同证据。

---

*Next allowed step: 冻结 R5-remediated owner-alignment 文件并执行第六轮独立
exact-file review。只有 R6 review PASS 且 owner alignment 合并后，才可另行准备
Activation；当前不推进 Plan、Task Packet、Worktree 或功能代码。*
