# 消费者订单与配送售后 Agent｜P0 业务能力说明

更新日期：2026-07-31<br>
文档状态：P0 目标业务范围  
适用读者：业务、产品、研发、测试及项目评审人员

> 本文回答“P0 用哪一条最小但完整的业务纵向切片证明 Agent 架构成立”。仓库已完成第一最薄 `E2E01-01/04` 的 W1 / W2、RU v2 contract closure、offline Composition、真实 `EvalCaseSut`、PostgreSQL exact owner-scoped evidence reader、HTTP → Runtime → PostgreSQL 纵向装配和 credential-aware Qwen runner。六个 authenticated physical Case、manifest 与 loader 当前为 `REGRESSION_GATE`；默认 `uv run pytest` 覆盖全部 16 个 authenticated variants，聚合结果为 `16 PASS / 0 FAIL / 0 Critical failure / 0 execution failure`，exact security re-review barrier `22c4cfa...` 的 canonical 串行套件为 `2007 passed, 1 deselected, 12 warnings`。Controlled UAT 由获授权的 `CODEX_INTEGRATOR` 直接驱动同一纵向链并作 scoped `PASS`，但 `end_user_uat` 仍为 `NOT_RUN`。真实 credentialed Qwen Baseline Result、canonical 产品启动、E2E-01 其余 Case、E2E-02、RAG / policy 与模拟退款完整链仍不属于已完成能力。因此本文描述的仍是 **P0 目标能力与验收边界**，不代表完整 P0 已开发完成、生产就绪或接入真实电商系统；详细实现状态与证据见[多 Agent 实施计划](implementation/e2e01-thin-slice-multi-agent-plan.md)与[Phase 01 Eval Results](../.planning/phases/01-cycle-1-e2e-01/01-EVAL-RESULTS.md)。

## 1. P0 目标与定位

P0 的目标不是建设一个缩小版电商售后平台，而是证明系统能够把大模型的语言理解和动态推理，放进一个可信、可控、可恢复、可评估的 Agent Runtime 中。

P0 只保留四类消费者目标：

1. 使用订单号或自然语言描述定位本人订单和商品。
2. 查询按需物流状态并识别配送异常。
3. 判断模拟退款资格并解释政策依据。
4. 在精确确认后创建一次模拟退款，并查询或恢复退款状态。

P0 通过两条端到端场景完成证明：

- **E2E-01：订单定位、物流查询与配送异常判断。**
- **E2E-02：退款资格、受控模拟执行与结果恢复。**

其中最重要的黄金场景是：

> “订单 O-1001 的包裹五天没更新了，帮我查一下，如果符合条件就退款。”

这一条输入能够同时验证：

- 多意图理解、拆分、依赖和条件。
- 本人订单定位与资源归属边界。
- 根据当前目标动态选择工具，而不是固定执行 Workflow。
- 物流事实查询与异常判断。
- 退款政策 RAG、Evidence 和确定性资格判断。
- 参数明确的退款方案与用户确认。
- `ActionPolicy`、授权、幂等和重复提交保护。
- `RESULT_UNKNOWN` 查询恢复。
- 跨轮任务状态、Trace 和 Agent Eval。

### 1.1 P0 范围原则

1. **只保留能证明新 Agent 机制的业务能力。** 单纯增加领域广度、但不增加新的 Agent 架构证明，不进入 P0。
2. **只实现一个代表性副作用动作。** P0 只有 `create_refund`；它用于证明确认、授权、Evidence、幂等和恢复门禁。
3. **真实复杂度用有状态 Mock 表达。** Mock 必须支持正常、拒绝、处理中、重复请求和结果未知，不能固定返回成功。
4. **读路径动态，安全边界确定。** Tool 顺序可以变化，但身份、归属、Evidence、确认、ActionPolicy 和未知结果恢复不可绕过。
5. **业务完成与 Agent 回合完成分开。** Agent 可以完成一次状态查询，但退款业务仍可能处于处理中。

## 2. P0 能力范围

### 2.1 三组核心业务能力

| # | 业务能力组 | P0 说明 |
|---|---|---|
| 1 | 订单与物流事实 | 定位本人订单和商品，按需查询订单、Shipment / Package，并基于可信事实判断 P0 配送异常 |
| 2 | 政策 Evidence 与退款判断 | 检索退款政策，组装 Evidence，使用确定性规则判断资格并生成可解释、可确认的方案 |
| 3 | 受控模拟退款与结果恢复 | 通过动作门禁创建一次模拟退款，查询处理状态并恢复 `RESULT_UNKNOWN` |

这三个分组是面向业务和架构沟通的稳定语义，不对应 Runtime 中的 `Capability` 对象，也不要求建立 Capability Registry 或固定的分组到工具路由。

### 2.2 Agent 与安全支撑能力

以下能力用于证明 Agent 架构，但不额外计入消费者业务能力：

- 可信 `CustomerContext`、本人资源归属和最小披露。
- 自然语言 Request Understanding。
- 保守的 Query 上下文化和指代消解。
- 多意图拆分及 `RequestUnit` 依赖、条件和状态管理。
- `RequestUnit Board + Controlled ReAct + ActionPolicy`。
- Tool Registry、Schema 校验、Observation 标准化和停止条件。
- ModelVisibleContext 与 RuntimePrivateContext 隔离。
- 跨轮、跨会话任务恢复。
- Trace、Dataset 和 Component / Trajectory / E2E Eval。
- 贯穿代码实现、纵向切片、回归和发布门禁的 Eval-driven development。

本文统一使用“多意图”描述一条消息中包含多个开放用户目标；它不表示预定义的业务 Intent 分类、Capability 分类或固定路由。

### 2.3 P0 明确不包含

P0 不实现：

- 物流催促建单或承运商升级；P0 只判断异常并返回允许的下一步。
- 取消未发货订单。
- 退货退款、退货面单、上门取件、退货物流和仓库验收。
- 换货、补发、库存预占和新的商品履约。
- 通用售后 Case 和跨类型售后进度中心。
- 真实退款到账、银行卡或支付渠道结算。
- 申诉、CRM、Ticket、坐席工作台或完整人工接管；P0 只允许返回 `NEED_HUMAN`。
- 独立公开产品知识服务；退款政策检索已经足以验证 RAG 与 Evidence。
- 京东、淘宝等外部渠道和真实订单、物流、支付接口。
- 多租户、商家后台、主管后台和复杂 Case Queue。
- 多 Agent 平台、通用 Workflow DSL、DAG 编排器或微服务拆分。
- 自动用户画像、自动长期偏好提炼和通用长期记忆。

`NEED_HUMAN` 在 P0 中是明确的停止结果，不代表系统已经创建人工工单。回复必须说明 P0 暂不支持继续自动处理，但不得伪造工单编号或人工 SLA。

## 3. 请求理解、Query 上下文化与 Slot

### 3.1 保留原始 Query，保守补全上下文

系统可以解析“这个”“还是没到”“刚才那笔退款”等指代和省略，但必须：

- 永远保留 `original_query`。
- 生成独立的 `contextualized_query`，不能覆盖原始消息。
- 为补全出的订单、商品或退款引用记录信息来源。
- 将低置信度内容放入 `uncertainties`，不能改写成业务事实。
- 不在 Query 改写阶段判断配送异常、退款资格或动作结果。

例如：

```json
{
  "original_query": "还是没有",
  "contextualized_query": "查询订单 O-1001 的模拟退款状态，用户表示仍未看到完成结果",
  "resolved_references": {
    "order_id": {
      "value": "O-1001",
      "source": "conversation_context"
    }
  },
  "uncertainties": []
}
```

系统不能仅凭这句话改写成“退款已超时”或“退款失败”；这些结论必须来自受控业务事实。

### 3.2 RequestUnit

P0 的 Request Understanding 不输出业务 Intent 分类，而是输出开放目标的 `TaskDeltaCandidate[]`。稳定操作只有：

```text
ADD_GOAL
AMEND_GOAL
SUPPLY_INPUT
CANCEL_GOAL
CONFIRMATION_CANDIDATE
```

Runtime 校验来源、Task 绑定、目标粒度、依赖、纠正和确认候选后，通过确定性 Reducer 写入 `RequestUnit Board`。一个 `RequestUnit` 表示一个可被用户感知、可独立完成或取消的持久目标；订单定位、ToolCall、RAG 检索、确定性判断、授权检查和动作恢复不是额外 RequestUnit。

推荐字段：

```text
request_unit_id
task_id
goal_text
goal_source_refs
contextualization_ref
constraint_refs
dependency_refs
input_binding_refs
open_questions
observation_refs
evidence_binding_refs
pending_action_ref
result_refs
status
state_version
```

`RequestUnit` 是可推进、可暂停、可恢复的任务状态，不是 Intent 的改名，也不是固定 Workflow 节点。它不携带 `intent_type`、`capability`、`required_arguments`、`allowed_tools`、Handler 或固定 Tool 顺序。

完整的模型输入输出、Task Delta 校验和 Reducer 契约以 [Intent / Request Understanding Design Reference](architecture/intent-design-reference.md) 为准。

### 3.3 最小必要 Slot / InputBinding

P0 可以继续用“Slot”作为沟通词，但实现契约称为 `InputBinding`。模型只产生带来源的 Candidate Input；可信身份、业务 Observation、政策 Evidence 和动作参数分别由对应的确定性边界产生。

| 分类 | P0 字段或引用 | 产生者 |
|---|---|---|
| Candidate Input | `order_id`、订单时间 / 商品描述、`item_id`、`package_id`、`refund_id`、原因和数量候选 | 模型候选，仍是 Claim / Inference |
| 可信身份 | `customer_id` | 服务端可信上下文，只存在于 Runtime 私有边界 |
| 已验证资源 | `order_ref`、`item_ref`、`package_ref`、`refund_ref` | 业务 API + Runtime 归属校验 |
| 业务 Observation | `order_observation_ref`、`shipment_observation_ref`、`refund_observation_ref` | 受控 Business Tool / API |
| 政策 Evidence | `policy_evidence_binding_ref`、`policy_version`、`policy_citation` | Retriever + Evidence Assembler |
| 退款方案 | `item_id`、`quantity`、`refund_amount`、`refund_method` | 确定性方案组装与 Action Ledger |
| 执行控制 | `proposal_id`、`confirmation_id`、`idempotency_key` | Runtime / ActionPolicy / Action Ledger |

Candidate Input 必须带来源和权威性：

```json
{
  "order_id": {
    "candidate_value": "O-1001",
    "authority": "USER_CLAIM",
    "source_kind": "CURRENT_MESSAGE",
    "source_ref": "msg_101",
    "source_quote": "订单 O-1001",
    "confidence": 0.99
  }
}
```

业务 API 验证后创建新的 Verified Target Ref，不能把原 Candidate 原地升级成业务事实。后台已经能够可靠取得的信息不重复询问；只有当前目标的安全下一步确实需要、且无法从可信系统取得的信息，才进入 `open_questions`。P0 不采用“Slot 为空就问”的表单策略。

P0 不定义库存、仓库、退货方式、换货规格、支付渠道结算或人工工单 Slot。

### 3.4 状态语义

Agent 本轮结果：

```text
ASK_USER
PROCESSING
COMPLETED
BLOCKED
NEED_HUMAN
NOT_FOUND_OR_NOT_ACCESSIBLE
```

退款资格结果：

```text
ELIGIBLE
NOT_ELIGIBLE
UNDETERMINED
```

模拟退款动作结果：

```text
COMPLETED
PROCESSING
FAILED
RESULT_UNKNOWN
```

三类结果不得混用：

- `ELIGIBLE` 不代表退款已经执行。
- 用户确认不代表退款已经成功。
- 模拟退款 `COMPLETED` 只表示 Mock Refund System 中的操作完成，不代表银行卡或真实支付渠道到账。
- Agent 本轮 `COMPLETED` 不代表退款业务一定结束。
- `RESULT_UNKNOWN` 不等于明确失败。

## 4. 两条核心端到端场景

### 4.1 E2E-01：订单定位、物流查询与配送异常判断

典型输入：

- “帮我看看最近买的那双鞋。”
- “订单 O-1001 到哪了？”
- “这个包裹五天没更新，是不是延误了？”

流程：

1. 验证 Session / JWT，从服务端加载可信 `CustomerContext`。
2. 理解用户目标、目标来源和必要参数。
3. 在本人资源范围内定位订单：
   - 明确订单号：使用 `(customer_id, order_id)` 联合查询。
   - 自然语言描述：使用 `customer_id + 时间范围 + 商品名称 / 类别` 搜索本人近期订单。
4. 处理定位结果：
   - 唯一候选：绑定订单和商品。
   - 多个候选：只展示本人订单的最小摘要，返回 `ASK_USER`。
   - 无结果或无权访问：返回统一的 `NOT_FOUND_OR_NOT_ACCESSIBLE`。
5. 根据当前目标动态选择下一步：
   - 只问订单：返回最小订单摘要，不查询物流。
   - 询问位置、配送时间或异常：查询关联 Package。
6. 基于最新物流 Observation 和 P0 规则判断正常、延迟、停滞或签收未收到。
7. 外部事实不足或物流系统不可用时返回 `BLOCKED` 或 `NEED_HUMAN`，不猜测结果。
8. 保存可恢复任务和最新 Observation 引用，经过最小披露控制后回复。

业务结果：

- 用户能用自然语言安全定位本人订单。
- 简单订单查询不会固定调用物流服务。
- 配送异常只基于可信物流事实判断。
- 错误订单号和非本人订单号不会泄露资源是否存在或订单内容。

### 4.2 E2E-02：退款资格、受控模拟执行与结果恢复

典型输入：

- “这个订单可以退款吗？”
- “如果符合条件就帮我退款。”
- “我确认按刚才的方案退款。”
- “刚才退款到底成功了吗？”

流程：

1. 验证身份并定位本人订单、商品或既有退款记录。
2. 根据当前目标动态读取必要事实：
   - 资格咨询：订单、必要物流事实和退款政策 Evidence。
   - 创建模拟退款：资格结果、精确方案、确认、授权和既有退款。
   - 状态查询：既有退款状态，不固定重新查询物流或政策。
3. 校验政策 Evidence 的来源、版本、适用性、新鲜度和冲突状态。
4. 使用确定性规则输出：
   - `ELIGIBLE`：生成包含订单、商品、数量、模拟金额、退款方式和影响的方案。
   - `NOT_ELIGIBLE`：解释不符合的事实和政策依据，不进入执行。
   - `UNDETERMINED`：说明证据或系统不足，不进入执行。
5. 模型提出结构化 `PROPOSE_ACTION`，Runtime 校验并映射为用户可见的 `ASK_USER`，等待用户对同一个精确方案确认。
6. 用户确认后，`ActionPolicy` 在执行瞬间重新检查：
   - 当前身份、授权和资源归属。
   - 关键 Observation 的版本与新鲜度。
   - Evidence 完整性、适用性和新鲜度。
   - 订单、商品、数量、金额、方式和方案版本。
   - 是否存在重复退款。
   - 可信幂等身份。
7. Gate 通过后调用 `create_refund`。
8. 根据动作结果处理：
   - `COMPLETED`：返回模拟退款编号和结果。
   - `PROCESSING`：返回当前状态和查询方式。
   - `FAILED`：说明明确失败原因和允许的下一步。
   - `RESULT_UNKNOWN`：禁止再次创建，使用原幂等身份查询恢复。
9. 在恢复预算内仍无法确认时返回 `BLOCKED`，不得伪报成功或失败。
10. 保存 Evidence、方案、确认、Action Record 和恢复点，允许跨会话继续。

业务结果：

- 模型不负责自行决定退款资格或金额。
- 没有有效 Evidence 和精确确认时不会执行退款。
- 重复确认只会产生一次模拟退款。
- 响应丢失或结果未知不会造成重复退款。

### 4.3 黄金场景中的多意图推进

对于：

> “订单 O-1001 的包裹五天没更新了，帮我查一下，如果符合条件就退款。”

系统应按依赖逐步推进：

```text
RU-1 查询订单 O-1001 关联包裹的当前状态，并解释是否异常
RU-2 若当前事实与政策判定符合条件，则在精确确认后创建模拟退款
```

系统在这两个目标内部动态完成本人订单定位、物流查询、异常判断、政策检索、资格判断、方案、确认、动作门禁和结果恢复。这些是 Tool、确定性派生和 Action Ledger 步骤，不是额外 RequestUnit。

这仍是一条产品验收路径，不是 Runtime 中硬编码的 DAG。模型根据最新 Observation 提出 `NextMove`；Runtime 只保证目标依赖、用户条件和安全边界不可被绕过。

## 5. 最小业务接口、工具与 Mock 系统

### 5.1 业务应用架构中的稳定语义

业务应用架构图不应直接铺开 `Order Tool`、`Shipment Tool` 或具体方法名。P0 的第 4 区只需要表达三个稳定业务分组：

```text
订单与物流事实
政策 Evidence 与退款判断
受控模拟退款与结果恢复
```

这些分组只用于说明业务语义，不表示 Capability Registry，也不形成固定的分组到工具路由。

### 5.2 P0 Tool Catalog

具体工具名属于 Tool Catalog、接口契约或技术逻辑视图。

Read / Retrieval：

```text
search_orders
get_order
get_shipment
retrieve_refund_policy
get_refund_status
```

Action：

```text
create_refund
```

每个工具包含 Agent 可见的：

```text
name
description
input_schema
output_schema
```

以及 Runtime 私有的：

```text
effect: READ | RETRIEVAL | ACTION
risk
idempotency
unknown_result_recovery
handler
```

`create_refund` 是 P0 唯一 Action，只能在 `ActionPolicy` 通过后执行。

### 5.3 四个 Mock Business Systems

P0 只需要：

| Mock 系统 | 最小职责 |
|---|---|
| Mock Order System | 本人订单搜索、订单详情、商品与履约状态、资源归属 |
| Mock Shipment System | Package 状态、物流节点、承诺时效和异常所需事实 |
| Policy Knowledge Base | 退款政策 Corpus、版本、引用、适用范围和冲突测试数据 |
| Mock Refund System | 模拟退款创建、状态查询、幂等、失败和 `RESULT_UNKNOWN` |

不需要 Payment Channel、Inventory、WMS、Reverse Logistics、RMA、CRM 或 Ticket System。

Mock 系统必须提供可控测试分支，至少包括：

- 正常成功。
- 明确不符合条件。
- 多候选和无结果。
- 过期、缺失或冲突 Evidence。
- 重复确认。
- `PROCESSING`。
- 明确失败。
- `RESULT_UNKNOWN` 和后续恢复。

## 6. 关键业务与安全规则

1. 只服务已登录消费者。
2. `customer_id` 只来自服务端可信上下文，用户和模型不能生成或修改。
3. 所有私有资源查询使用 `customer_id + resource_id` 或等价归属约束。
4. 订单、物流、退款和历史任务等私有资源在“不存在”“不属于当前用户”或“无法确认归属”时，统一映射为 `NOT_FOUND_OR_NOT_ACCESSIBLE`，外部不得区分真实原因。
5. 归属失败必须在模型之前完成安全归一化；未经归属验证的原始结果和私有字段不能进入模型上下文、Memory、标准 Observation 或普通 Trace。
6. 已确认属于当前用户的资源也只能形成按当前目标裁剪的白名单投影；原始 ToolResult 不能直接用于模型表达或用户回复。
7. Tool 路径根据当前目标和 Observation 动态形成，不固定调用全部工具。
8. 用户陈述和模型推断不是业务事实；关键事实必须来自受控 Mock 系统。
9. 退款资格必须由确定性规则基于当前事实和有效 Evidence 计算。
10. 退款执行必须绑定参数明确的方案和用户对该方案的精确确认。
11. 订单、商品、数量、金额、退款方式、用户可见影响、关键 Observation、Evidence / 政策版本或授权变化时，旧确认失效。
12. `create_refund` 必须具备重复检查和语义幂等。
13. `RESULT_UNKNOWN` 只能查询恢复，不能再次创建模拟退款。
14. 跨会话恢复时必须重新校验身份、资源归属和事实新鲜度。
15. P0 不把模拟退款 `COMPLETED` 表述为真实支付渠道到账。
16. 回复、模型上下文、Memory 和 Trace 均遵循最小披露原则。

## 7. 用户结果与 P0 验收

### 7.1 用户可见结果

| 结果 | 含义 |
|---|---|
| `ASK_USER` | 目标、资源或必要参数不明确，或者精确模拟退款方案正在等待用户确认 |
| `PROCESSING` | 模拟退款已受理但尚未结束 |
| `COMPLETED` | 当前用户目标已经完成 |
| `BLOCKED` | Evidence、系统能力或恢复预算不足，当前不能继续 |
| `NEED_HUMAN` | P0 无法继续自动处理；不代表已经创建人工工单 |
| `NOT_FOUND_OR_NOT_ACCESSIBLE` | 资源不存在或当前用户无权访问，外部不区分原因 |

对已确认属于当前用户的订单，状态型回复最多披露：用户可见订单号、订单状态、商品名称与数量、下单时间和状态更新时间。内部主键、`customer_id`、地址、支付、风控字段和原始 ToolResult 不属于用户结果。

模型可以决定上述已批准内容的顺序、语气和表达变体，但订单号、数量、日期、状态和商品名称等事实值必须由确定性代码从白名单订单摘要注入。`fact_refs` 只能辅助审计，不能单独证明自由文本没有暗示其他信息。`NOT_FOUND_OR_NOT_ACCESSIBLE` 等安全敏感结果必须绕过模型措辞并使用固定安全回复。

### 7.2 Agent 架构验收清单

P0 达到目标时，应至少证明：

- 用户能用订单号或自然语言描述定位本人订单。
- 多个候选时只展示本人订单的最小必要摘要。
- 本人订单的订单号、商品、数量、日期和状态由确定性代码从安全投影注入，模型只产生受控表达计划。
- 简单订单查询不会无条件调用物流服务。
- 物流异常判断只使用最新可信 Observation。
- 黄金场景能够拆分两个持久用户目标，而不把 Tool、RAG、判断和 Gate 过度拆成 `RequestUnit`。
- 政策检索保留来源、版本、引用和新鲜度。
- Evidence 缺失、过期或冲突时不会执行退款。
- `NOT_ELIGIBLE` 和 `UNDETERMINED` 都不能进入退款执行。
- 没有精确确认时不会调用 `create_refund`。
- 关键参数变化后旧确认自动失效。
- 重复确认只创建一次模拟退款。
- `RESULT_UNKNOWN` 使用原幂等身份查询恢复，不盲目重试。
- 用户能在新会话恢复未完成任务，但必须重新通过身份和资源校验。
- 非本人订单号与随机订单号产生相同安全结果。
- 私有资源安全结果在模型前归一化，不形成含真实资源内容的标准 Observation，也不调用模型自由措辞。
- Trace 能还原 `TaskDeltaCandidate`、校验结果、RequestUnit、NextMove、Gate Decision、ToolCall、Observation、Evidence 和停止原因。
- Eval 能覆盖 Component、Trajectory 和 E2E 三个层级。

上述条目拥有业务成功与验收语义；通用 Eval 方法、Dataset / Grader / Gate 生命周期见 [Agent Evaluation Strategy](evaluation/agent-evaluation-strategy.md)，P0 Case 映射见 [P0 Eval Coverage Matrix](evaluation/p0-eval-coverage-matrix.md)。

### 7.3 两条 E2E 覆盖矩阵

| 能力 | E2E-01 | E2E-02 |
|---|:---:|:---:|
| 可信身份与资源归属 | ✓ | ✓ |
| 订单与商品定位 | ✓ | ✓ |
| 订单详情查询 | ✓ | 按需 |
| 物流状态查询 | ✓ | 作为退款判断输入时按需，产出 Observation |
| 配送异常判断 | ✓ | 作为退款判断输入时按需，产出确定性判断 |
| 政策 Evidence |  | ✓ |
| 退款资格与解释 |  | ✓ |
| 精确方案与确认 |  | ✓ |
| 受控模拟退款 |  | ✓ |
| 状态查询与未知结果恢复 |  | ✓ |
| 跨轮、跨会话任务恢复 | ✓ | ✓ |
| Trace 与 Agent Eval | ✓ | ✓ |

## 8. P0 之后的业务路线图

此前讨论的 8 个高频闭环保留为演进方向，不纳入 P0 验收：

| 高频闭环 | 阶段建议 | 引入的主要新复杂度 |
|---|---|---|
| 物流查询和催促 | 查询纳入 P0；催促进入 P1 | P1 增加催促 Case、SLA、重复建单和升级 |
| 取消未发货订单 | P1 | 履约竞态、取消动作和取消后退款 |
| 仅退款 | P0 | 以模拟退款纵向切片纳入 |
| 售后进度查询 | P1 | 通用 AftersaleCase 和跨类型状态模型 |
| 被拒解释与最小人工交接 | P1 | 原因代码、补充 Evidence、最小 Ticket |
| 退货退款 | P2 | 逆向物流、退货授权和仓库验收 |
| 换货或补发 | P2 | 库存、规格、新履约和二次物流 |
| 真实退款到账查询 | P3 | 支付渠道、结算状态、对账和真实 SLA |

后续能力进入新阶段前，应满足：

1. P0 两条 E2E 已通过稳定自动化验收。
2. 新能力确实需要验证新的 Agent 或业务安全机制。
3. 新增业务系统和状态复杂度有明确边界。
4. 不以增加 Tool 数量代替 Agent 架构质量。

## 9. 当前材料与追溯关系

本文与以下现有材料的核心方向一致：

- [P0 项目方向与架构决策](../PROJECT_DIRECTION.md)：四类消费者目标、两条 E2E、`RequestUnit Board + Controlled ReAct + ActionPolicy`。
- [Agent Evaluation Strategy](evaluation/agent-evaluation-strategy.md)：Eval-driven development、通用 EvalCase、Dataset、Grader、Gate、报告与架构决策证据。
- [P0 Eval Coverage Matrix](evaluation/p0-eval-coverage-matrix.md)：两条 E2E 的 Case ID、requirement mapping、Critical failure 与激活顺序。
- [Intent / Request Understanding Design Reference](architecture/intent-design-reference.md)：Query 上下文化、开放目标 `TaskDeltaCandidate`、`InputBinding`、确定性校验与薄 RequestUnit。
- [Tool Calling Design Reference](architecture/tool-calling-design-reference.md)：Tool Registry / Executor、不可变工具集快照、Control Gateway 工具校验、ToolCall 生命周期、超时、中断及工具调用 Trace / Eval。
- [业务应用架构 V2](architecture/consumer-after-sales-agent-business-application-architecture-v2.png)：Application、Runtime、三个稳定业务能力分组、四个 Mock 系统及 AI / 平台支撑。
- [E2E-01：订单定位、物流查询与配送异常判断](architecture/consumer-after-sales-agent-business-flow-v2-page-1-order-resolution-query.png)。
- [E2E-02：退款资格、受控模拟执行与结果恢复](architecture/consumer-after-sales-agent-business-flow-v2-page-2-refund-controlled-recovery.png)。
- [Memory Design Reference](architecture/memory-design-reference.md)：状态分层、权威边界和跨会话恢复。

当前 active Markdown 与 V2 图形统一使用“多意图”表述；active Markdown 的 Request Understanding 专项契约使用开放目标 `TaskDeltaCandidate`，不采用业务 Intent / Capability 分类或 RequestUnit Tool allowlist，V2 图形只保留通用 Request Understanding / RequestUnit Board 抽象。独立公开产品知识服务已经退出 P0；Tool Catalog 保持 6 个工具；Mock Business Systems 保持 4 个；Flow V2 区分 Observation、Evidence、Agent 本轮结果、Task 状态和 Action Ledger 状态；代码依赖 V2 区分 Application-owned Conversation Port 与 Core-owned State / Record / Observability Port Groups，并明确关系数据库是 P0 权威状态源，Redis 不在当前依赖基线。

上述同步不改变以下语义 owner：

1. 业务范围、两条 E2E、Tool Catalog 和 Mock 系统以本文为准。
2. Request Understanding、Query 上下文化、Task Delta 与 `InputBinding` 以 [Intent Design Reference](architecture/intent-design-reference.md) 为准。
3. Tool Registry / Executor、工具集快照、Gateway 工具校验、ToolCall 生命周期、超时与中断以 [Tool Calling Design Reference](architecture/tool-calling-design-reference.md) 为准。
4. Memory、Observation、Evidence 与 Action Ledger 语义以 [Memory Design Reference](architecture/memory-design-reference.md) 为准。
5. 通用 Eval 方法、Case 契约、Dataset 生命周期、Grader 和 Gate 以 [Agent Evaluation Strategy](evaluation/agent-evaluation-strategy.md) 为准；Coverage Matrix 只维护派生的验证映射。
6. [业务应用架构 V2](architecture/consumer-after-sales-agent-business-application-architecture-v2.png) 是当前架构基线；配套图形不得覆盖上述语义 owner。

本文是当前 **P0 业务范围**。后续路线图中的能力不应被解释为已经承诺实现或已经纳入 P0。
