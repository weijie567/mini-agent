# Consumer Order & Delivery Support — Scenario Contract

> Status: `DRAFT / NON_NORMATIVE / NOT IMPLEMENTED / NOT VERIFIED`
>
> Date: `2026-07-22`
>
> Purpose: define the P0 observable behavior of the Order & Delivery Support Reference Application, including request decomposition, capability routing, tools, state, guardrails, failure behavior, and evaluation cases.

## 1. Contract Boundary

本文定义消费者订单与配送支持 Reference Application 的行为合同，不定义：

- Python class 或 package layout。
- 数据库、向量库或 Web framework。
- Prompt 全文。
- 具体模型、embedding model、top-k 或数值预算。
- 真实承运商 API。
- 已实现或已验证的系统事实。

本文所有领域数据与 Tool 结果均为后续实现使用的 synthetic fixtures。

## 2. Modeling Decision

P0 不使用“一条消息只能分类成一个 Intent”的平铺 Intent Taxonomy。

采用：

```text
User Message + Conversation State
        ↓
Request Understanding / Decomposition
        ↓
RequestUnit[]
        ↓
Capability Validation and Routing
        ↓
Capability-specific Tool / RAG / Workflow Boundary
        ↓
Runtime-controlled Execution
```

核心概念：

| 概念 | 回答的问题 | 示例 |
|---|---|---|
| `RequestUnit` | 用户当前有哪个可独立完成的目标？ | 查询包裹位置 |
| `Capability` | 系统用哪项稳定能力完成该目标？ | `shipment_tracking` |
| `Argument / Slot` | 完成能力还需要哪些信息？ | `order_id` |
| `Tool` | 程序具体调用什么？ | `get_shipment` |
| `Domain State` | 当前已经确认了哪些领域事实？ | `observed_shipment_status=DELIVERED` |
| `Action` | 哪个有副作用的操作可能被执行？ | `open_delivery_support_case` |
| `RunResult` | 本次运行为什么结束？ | `NEEDS_USER_INPUT` |

## 3. Actors and Domain Objects

### 3.1 Actors

- `Consumer`：提出订单与配送支持请求。
- `Agent Runtime`：驱动模型、Capability、Tool、State 与 Trace。
- `Reference Application`：拥有订单与配送领域合同。
- `Mock Order Service`：提供 synthetic Order data。
- `Mock Shipment Service`：提供 synthetic Shipment data。
- `Policy Retriever`：检索 synthetic delivery policy corpus。
- `Mock Support Case Service`：创建 synthetic Delivery Support Case。
- `Human Responsibility Boundary`：当自动处理不安全或证据不足时接管责任。

### 3.2 Domain Objects

- `Order`
- `Shipment`
- `DeliveryPolicyEvidence`
- `DeliverySupportCase`

这些对象属于 Reference Application，不属于通用 Runtime。

## 4. Request Understanding Contract

### 4.1 Request Envelope

建议的模型输出：

```json
{
  "scope": "SUPPORTED",
  "request_units": [
    {
      "id": "ru_1",
      "goal": "查询订单当前物流位置",
      "capability": "shipment_tracking",
      "arguments": {
        "order_id": "O-123"
      },
      "dependencies": [],
      "status": "CANDIDATE"
    },
    {
      "id": "ru_2",
      "goal": "解释物流三天没有更新的原因和处理方式",
      "capability": "delivery_exception_resolution",
      "arguments": {
        "order_id": "O-123",
        "reported_issue": "NO_RECENT_UPDATE"
      },
      "dependencies": ["ru_1"],
      "status": "CANDIDATE"
    }
  ]
}
```

### 4.2 Scope Values

- `SUPPORTED`：所有 Request Unit 都可映射到 P0 Capability。
- `PARTIALLY_SUPPORTED`：至少一个 Request Unit 可处理，至少一个不可处理。
- `UNSUPPORTED`：当前请求不属于 P0。
- `UNCLEAR`：无法可靠识别目标，需要澄清。

`OUT_OF_SCOPE` 不建模为 Intent；它是 `UNSUPPORTED` Routing Result。

### 4.3 Request Unit Status

- `CANDIDATE`：模型提出，尚未验证。
- `NEEDS_INPUT`：缺少 Capability 必需参数。
- `READY`：Capability 与参数已验证，可执行。
- `IN_PROGRESS`
- `COMPLETED`
- `BLOCKED`
- `ESCALATED`
- `FAILED`

### 4.4 Responsibility Split

LLM 负责：

- 识别用户自然语言目标。
- 将复合消息拆为一个或多个 Request Unit。
- 提出候选 Capability。
- 从消息和可信对话状态中提取候选参数。

程序负责：

- 拒绝 Registry 中不存在的 Capability。
- 根据 Capability schema 校验 arguments。
- 根据 `required_arguments` 和当前 State 计算 missing fields。
- 合并多个 Request Unit 共享的已验证参数。
- 验证依赖关系。
- 选择允许暴露的 Tools。
- 决定是否允许执行 Action。

模型输出的 `status` 只是候选值；程序验证后才产生 authoritative Request Unit status。

## 5. Capability Registry Contract

### 5.1 `order_status_lookup`

**User goal**

- 查询订单是否创建、取消、出库或发货。

**Examples**

- “订单 O-123 发货了吗？”
- “我的订单为什么还没出库？”
- “这个订单是不是取消了？”

**Required arguments**

- `order_id`

**Allowed tools**

- `get_order`

**Risk class**

- `READ_ONLY`

### 5.2 `shipment_tracking`

**User goal**

- 查询包裹当前状态、最近节点和预计送达信息。

**Examples**

- “包裹到哪里了？”
- “预计什么时候送到？”
- “最近一次物流更新是什么？”

**Required arguments**

- `order_id`，或已经可信关联的 `shipment_id`

**Allowed tools**

- `get_order`
- `get_shipment`

**Risk class**

- `READ_ONLY`

### 5.3 `delivery_exception_resolution`

**User goal**

- 理解并处理配送异常。

**Supported reported issues**

- `DELIVERY_DELAYED`
- `NO_RECENT_UPDATE`
- `DELIVERY_ATTEMPT_FAILED`
- `DELIVERED_NOT_RECEIVED`
- `OTHER_DELIVERY_EXCEPTION`

**Examples**

- “物流三天没有更新了。”
- “为什么派送失败？”
- “订单显示签收，但我没收到。”
- “包裹一直延迟，应该怎么办？”

**Required arguments**

- `order_id`
- `reported_issue`；若无法确定，则由澄清问题补充

**Allowed tools**

- `get_order`
- `get_shipment`
- `retrieve_delivery_policy`
- `open_delivery_support_case`，仅在满足 Action Gate 时

**Risk class**

- `READ_THEN_MAY_PROPOSE_ACTION`

### 5.4 `delivery_policy_qa`

**User goal**

- 查询配送时效、状态含义和异常处理政策。

**Examples**

- “多久没有物流更新才算异常？”
- “派送失败后还会重新派送吗？”
- “显示签收但没收到应该怎么办？”

**Required arguments**

- `policy_topic`，可由用户问题构造

**Allowed tools**

- `retrieve_delivery_policy`

**Risk class**

- `READ_ONLY`

### 5.5 Registry Rules

- Capability ID 必须来自 closed Registry。
- 新增自然语言表达不要求新增 Capability。
- 新增配送异常优先扩展 `reported_issue`，而不是新增 Capability。
- 新 Capability 必须代表新的稳定用户目标或新的执行合同。
- Capability Contract 拥有 required arguments、allowed tools、risk class 和 completion condition。

## 6. Tool Contract Summary

### 6.1 `get_order`

**Type**: `READ_TOOL`

**Purpose**: 查询 synthetic Order，并在服务端验证当前 Consumer 是否有权访问。

**Model-supplied input**

- `order_id`

**Runtime-injected context**

- authenticated synthetic `principal_id`

模型不得自行提供或覆盖 `principal_id`。

**Results**

- `SUCCESS`
- `NOT_FOUND`
- `UNAUTHORIZED`
- `TEMPORARY_FAILURE`

### 6.2 `get_shipment`

**Type**: `READ_TOOL`

**Purpose**: 查询 synthetic Shipment 的当前状态、节点、预计送达和 delivery evidence。

**Input**

- `shipment_id`，通常来自可信的 Order Tool Result

**Results**

- `SUCCESS`
- `NOT_FOUND`
- `TEMPORARY_FAILURE`
- `STALE_DATA`

### 6.3 `retrieve_delivery_policy`

**Type**: `RETRIEVAL_TOOL`

**Purpose**: 检索 synthetic delivery policy corpus。

**Input**

- `query`
- 可选 metadata filters

**Result requirements**

- Evidence ID
- Source document ID
- Relevant excerpt or normalized evidence
- Retrieval score or rank
- Version / effective metadata when available

空结果、低相关结果和冲突证据必须显式表示，不得伪装为成功命中。

### 6.4 `open_delivery_support_case`

**Type**: `ACTION_TOOL`

**Purpose**: 在 synthetic support system 中创建内部 Delivery Support Case。

**Preconditions**

- Order ownership verified。
- Relevant Shipment facts retrieved。
- Applicable policy evidence available，或 policy 明确允许人工 Case。
- User has explicitly confirmed the proposed action。
- Idempotency key generated by trusted code。

**Trusted inputs**

- `principal_id`
- `idempotency_key`
- verified evidence references

这些值不得由模型自由生成后直接执行。

**Results**

- `CREATED` with synthetic `case_id`
- `ALREADY_EXISTS` with existing `case_id`
- `PRECONDITION_FAILED`
- `UNAUTHORIZED`
- `RESULT_UNKNOWN`
- `TEMPORARY_FAILURE`

该 Action 不代表承运商 Claim、退款、补发或赔偿成功。

## 7. Domain and Working State

建议的领域 Working State：

```json
{
  "request_units": [],
  "order_id": null,
  "verified_order_ref": null,
  "shipment_id": null,
  "reported_issue": null,
  "observed_shipment_status": null,
  "shipment_evidence_refs": [],
  "policy_evidence_refs": [],
  "proposed_action": null,
  "approval_status": "NOT_REQUESTED",
  "support_case_id": null
}
```

Rules：

- 用户陈述进入 `reported_issue`，不能直接写成 `observed_shipment_status`。
- Tool Result 才能更新 verified order / shipment facts。
- 模型推测不能写入 verified facts。
- Approval 只能由明确用户响应更新。
- Action Result 才能写入 `support_case_id`。

## 8. Runtime Run Results

- `COMPLETED`
- `NEEDS_USER_INPUT`
- `APPROVAL_REQUIRED`
- `PARTIALLY_COMPLETED`
- `ESCALATED`
- `FAILED`

Run Result 与 Request Unit status 分离。一次 Run 可以结束于 `NEEDS_USER_INPUT`，同时保留多个尚未完成的 Request Unit。

## 9. Core Scenarios

### 9.1 Order Status Lookup

```text
User asks whether an order has shipped
→ decompose to order_status_lookup
→ compute missing order_id
→ ask once if missing
→ get_order
→ explain verified status
→ complete Request Unit
```

### 9.2 Shipment Tracking

```text
User asks where the package is
→ decompose to shipment_tracking
→ resolve order_id
→ get_order
→ obtain trusted shipment_id
→ get_shipment
→ explain current status and latest event
→ complete Request Unit
```

### 9.3 Delivery Policy Q&A

```text
User asks a general delivery-policy question
→ decompose to delivery_policy_qa
→ retrieve_delivery_policy
→ answer with evidence references
→ no relevant evidence: say evidence is unavailable and avoid invention
```

### 9.4 Compound Request

Example：

> “订单 O-123 到哪里了，怎么三天都没有更新？”

Expected decomposition：

```text
RU-1 shipment_tracking
RU-2 delivery_exception_resolution(NO_RECENT_UPDATE), depends on RU-1
```

Runtime 应复用 `order_id`、Order Result 与 Shipment Result，不重复请求用户或无意义重复调用工具。

## 10. Anchor Scenario: Delivered but Not Received

User request：

> “订单显示已签收，但我没有收到，帮我处理一下。”

Expected behavior：

1. 产生 `delivery_exception_resolution` Request Unit，`reported_issue=DELIVERED_NOT_RECEIVED`。
2. Order ID 缺失时返回 `NEEDS_USER_INPUT`，不得猜测。
3. 调用 `get_order` 并验证归属。
4. 从可信 Order Result 获取 Shipment ID。
5. 调用 `get_shipment`。
6. 只有 Tool Result 显示已签收时，才确认 `observed_shipment_status=DELIVERED`。
7. 检索适用的 missing-delivery policy。
8. Reference Application 组装 Order、Shipment 与 Policy evidence。
9. 给出证据化处理建议。
10. 如适用，提出创建内部 Delivery Support Case，并返回 `APPROVAL_REQUIRED`。
11. 用户明确确认后，Runtime 构造 trusted idempotency key 并执行 Action Tool。
12. `CREATED` 或 `ALREADY_EXISTS` 时返回唯一 Case ID。
13. `RESULT_UNKNOWN` 时不得宣称创建成功，应查询、恢复或转人工。
14. 保存完整 Trace。

## 11. Memory Contract

### 11.1 Conversation History

- 保存当前对话中的 user / assistant / tool messages。
- 受 context budget 控制。

### 11.2 Structured Working Memory

- 保存 Request Unit、verified facts、missing inputs、evidence refs、approval 与 action result。
- 不把模型自然语言总结自动升级为 verified fact。

### 11.3 Recoverable Task Memory

P0 可以用以下方式验证跨会话恢复，而不创建“调查进度查询”这一独立 Capability：

```text
Session A：用户提供 Order ID，Agent 完成调查，但用户尚未确认 Action
Session B：用户说“继续处理刚才那个配送问题”
→ 恢复未完成 Request Unit、verified facts 和 approval state
→ 不重复查询已确认且仍有效的事实
→ 继续请求确认或刷新过期证据
```

必须定义 TTL、事实新鲜度与冲突更新策略后，才能复用旧 Tool Result。

## 12. Guardrails

- 未验证 Order ownership，不得展示订单或物流详情。
- 用户陈述不得直接成为 verified shipment fact。
- Tool Call 建议不等于执行授权。
- Action Tool 不得在明确用户确认前执行。
- `principal_id`、权限结论和 idempotency key 不由模型决定。
- 无适用政策证据时，不得编造赔偿、退款、补发或时限承诺。
- 不得把内部 Case 创建描述成承运商 Claim 成功。
- 同一语义 Action 不得因重试或重复确认产生多个 Case。
- Tool timeout 后必须区分 `FAILED` 与 `RESULT_UNKNOWN`。
- 超过 step、time、retry 或 token budget 时必须有界结束。
- 部分支持的复合请求应说明哪些完成、哪些转交，不得静默丢弃 Request Unit。

## 13. Failure and Recovery

| Failure | Required behavior |
|---|---|
| Unknown Capability | Reject candidate; clarify or mark unsupported |
| Missing arguments | Compute programmatically; request only necessary information |
| Invalid Tool arguments | Do not execute; repair once within budget |
| Order not found | Explain safely; do not continue with guessed data |
| Unauthorized Order | Do not reveal existence or details beyond safe error contract |
| Shipment Tool timeout | Bounded retry; then degrade or escalate |
| Stale Shipment data | Mark staleness and avoid definitive claim |
| RAG no evidence | State evidence unavailable; do not invent policy |
| Conflicting evidence | Preserve conflict; do not silently choose one source |
| Duplicate Tool Call | Suppress or stop according to semantic fingerprint policy |
| Action result unknown | Reconcile by idempotency key before retry |
| Max steps reached | Return `FAILED` or `ESCALATED` with traceable reason |

## 14. Evaluation Cases

| ID | Input / condition | Expected contract behavior |
|---|---|---|
| `RU-01` | “订单 O-123 发货了吗？” | One `order_status_lookup` Request Unit |
| `RU-02` | “我的包裹到哪了？” without Order ID | `shipment_tracking` + `NEEDS_USER_INPUT` |
| `RU-03` | “订单 O-123 到哪了，怎么三天没更新？” | Two Request Units with dependency |
| `RU-04` | “签收了但我没收到” | `delivery_exception_resolution` with reported issue |
| `RU-05` | “多久没更新算异常？” | `delivery_policy_qa`, no Order ID required unless policy requires context |
| `RU-06` | Delivery question plus refund request | `PARTIALLY_SUPPORTED`; preserve both goals |
| `RU-07` | Ambiguous “帮我看看这个” | `UNCLEAR`, ask clarification |
| `RU-08` | Unrelated product recommendation | `UNSUPPORTED`, no domain Tool Call |
| `TOOL-01` | Valid Order | Correct `get_order` args; principal injected by Runtime |
| `TOOL-02` | Unauthorized Order | No Order detail leakage; stop affected Request Units |
| `TOOL-03` | Shipment timeout | Bounded retry then degrade / escalate |
| `TOOL-04` | Model requests unregistered Tool | Reject before dispatch |
| `RAG-01` | Policy corpus contains applicable evidence | Retrieve and cite correct evidence |
| `RAG-02` | No applicable evidence | No fabricated policy or promise |
| `RAG-03` | Conflicting policy evidence | Expose conflict and escalate or request decision |
| `ACT-01` | Action proposed but user has not confirmed | `APPROVAL_REQUIRED`; no Action Tool Call |
| `ACT-02` | User confirms and preconditions pass | Create one synthetic Case |
| `ACT-03` | User repeats confirmation | `ALREADY_EXISTS` or same Case ID; no duplicate |
| `ACT-04` | Action returns `RESULT_UNKNOWN` | Reconcile before retry; do not claim success |
| `MEM-01` | User resumes an unfinished task | Restore valid state; refresh stale facts |
| `LOOP-01` | Model repeats equivalent Tool Call | Detect duplicate and recover or terminate |
| `LOOP-02` | Model never converges | Stop at budget and return traceable result |
| `E2E-01` | Delivered-not-received happy path | Complete evidence → approval → one Case creation |
| `E2E-02` | Delivered-not-received with no RAG evidence | No action promise; safe escalation |

## 15. P0 Acceptance Conditions

- 一个消息可以产生多个 Request Unit。
- Capability 只来自 closed Registry。
- 新表达或异常变体不自动产生新的 Capability。
- Missing fields 由程序根据 Capability Contract 计算。
- Request Unit、Capability、Tool、Action 与 Run Result 在 Trace 中可区分。
- Runtime 不包含 Order、Shipment 或 DeliveryPolicy 的业务解释逻辑。
- Anchor Scenario 能端到端运行并覆盖确认、幂等和失败恢复。
- 四项 Capability 均有至少一个成功用例和一个失败 / 边界用例。
- Eval 不只检查最终文本，还检查 Request Unit、Tool、Evidence、Action 与终止状态。
- 所有真实业务相关声明都有明确 synthetic / reference boundary。

## 16. Source and Inference Boundary

### Confirmed public workflow references

- [FedEx: delivery notification but package not found](https://www.fedex.com/en-us/customer-support/faqs/receiving/tracking-questions/fedex-says-delivered-but-no-package.html)
- [UPS: file and review a claim](https://www.ups.com/us/en/support/file-a-claim)
- [USPS: Missing Mail Search](https://www.usps.com/help/missing-mail.htm)

这些来源确认 Tracking、Missing Package Report、Claim / Search Request 等消费者任务存在，但不证明其内部 conversational Agent 自动执行了全部流程。

### Agent modeling references

- [Rasa CALM conversation design](https://rasa.com/docs/learn/best-practices/conversation-design/)
- [Dialogflow CX Playbooks](https://docs.cloud.google.com/dialogflow/cx/docs/concept/playbook)
- [Dialogflow CX Intents](https://docs.cloud.google.com/dialogflow/cx/docs/concept/intent)
- [Dialogflow CX Parameters](https://docs.cloud.google.com/dialogflow/cx/docs/concept/parameter)

本项目采用 Request Unit + Capability Registry 是基于上述模式作出的项目设计裁决，不声称它是唯一行业标准。

## 17. Related Documents

- [Project Brief](./PROJECT_BRIEF.md)
- [Project Outline](./PROJECT_OUTLINE.md)
