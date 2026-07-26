# Mini Agent Runtime — Project Brief

> Status: `DRAFT / NON_NORMATIVE / NOT IMPLEMENTED / NOT VERIFIED`
>
> Date: `2026-07-22`
>
> Purpose: define the project's job-seeking goal, P0 boundary, core technical claim, non-goals, and completion evidence before implementation begins.

## 1. Project Statement

本项目拟从零实现一个轻量、framework-free 的 `Agent Runtime`，并通过一个有边界的消费者订单与配送支持 Agent 验证其核心机制。

项目不以完成一套完整客服系统为目标。它的技术主角是 Runtime；消费者订单与配送支持只是 `Reference Application`，用于让 Runtime 遇到真实、连贯、可复现的问题。

一句话定位：

> Build a lightweight Agent Runtime from first principles, then validate it through a bounded Consumer Order & Delivery Support Agent.

## 2. Job-seeking Goal

项目主要证明 `AI Agent Developer` 能力，并辅助证明 Agent 产品范围控制与评测设计能力。

完成后应能够用仓库证据回答：

- Agent Loop 如何驱动 LLM、Tool、State 与外部系统？
- Function Calling 为什么只是调用建议，程序如何完成受控执行？
- Tool Registry、Tool Executor 与 Capability Registry 为什么需要分离？
- 如何理解和拆分一条包含多个诉求的用户消息？
- Memory 如何保存任务事实，而不把模型猜测升级为事实？
- RAG 如何提供可追溯证据，并在无证据时安全失败？
- 高风险 Action 如何经过权限、确认、幂等和审计控制？
- 如何通过 Trace 与 Evaluation 判断 Agent 为什么成功或失败？
- 自研 Runtime 与 LangGraph、OpenAI Agents SDK 等框架分别适用于什么情况？

## 3. Product Shape

```text
Consumer Chat Entry
        ↓
Order & Delivery Support Reference Application
Request Understanding、Capability、Domain State、Policy、Domain Tools
        ↓
Agent Runtime
Loop、Generic State、Tool Execution、Memory Integration、Control、Trace
        ↓
Model Provider / Store / Retriever / Mock External Services
```

### 3.1 Runtime 是通用执行层

Runtime 可以认识：

- `Message`
- `RequestUnit`
- `CapabilityCandidate`
- `ToolCall`
- `ToolResult`
- `RunState`
- `RunResult`
- `TraceEvent`
- 通用 Evidence envelope

Runtime 不应硬编码：

- `Order`
- `Shipment`
- `DeliveryException`
- `DeliveryPolicy`
- `DeliverySupportCase`

### 3.2 Reference Application 是领域层

Reference Application 负责：

- 订单与配送领域的 Request Understanding schema。
- 有界 Capability Catalog。
- Order、Shipment、Policy 等领域对象及其语义。
- Capability 到允许工具、前置条件和风险等级的映射。
- 领域证据组装。
- 消费者可观察的回答、确认、失败和人工接管行为。

## 4. P0 Problem Space

P0 聚焦：

> Consumer Order & Delivery Support

它不是完整售后系统，但也不只支持“签收未收到”一个问题。

P0 支持以下相互关联的消费者目标：

- 查询订单是否创建、取消、出库或发货。
- 查询包裹当前状态、最近物流节点和预计送达信息。
- 理解和处理配送延迟、长时间未更新、派送失败、签收未收到等异常。
- 查询与配送状态、异常处理相关的政策知识。
- 在满足前置条件并取得明确确认后，创建一条模拟的配送支持 Case。
- 对复合诉求进行拆分，并在多轮对话中继续未完成任务。

## 5. P0 Capability Catalog

| Capability | 用户目标 | 主要机制 |
|---|---|---|
| `order_status_lookup` | 查询订单当前业务状态 | Request Understanding、单 Tool Call |
| `shipment_tracking` | 查询物流状态、节点与预计送达 | 多 Tool 串行调用、Context Assembly |
| `delivery_exception_resolution` | 理解并处理配送异常 | 多步调查、RAG、Memory、Guardrails |
| `delivery_policy_qa` | 查询配送及异常处理政策 | RAG、Citation、No-evidence Handling |

Capability 是稳定的用户任务能力，不等于传统的一问一类 Intent。

以下不是 Capability：

- `open_delivery_support_case`：有副作用的 Action Tool。
- `OUT_OF_SCOPE`：Routing Result。
- `NEEDS_USER_INPUT`：Run Result。
- `DELIVERED_NOT_RECEIVED`：`delivery_exception_resolution` 下的领域异常类型。

## 6. Request Understanding Paradigm

P0 不建立平铺、穷举式 Intent Taxonomy，也不把所有 Tools 无差别交给模型。

采用：

> Dynamic Request Decomposition + Bounded Capability Registry + Controlled Execution

一条用户消息可以生成一个或多个 `RequestUnit`：

```json
{
  "request_units": [
    {
      "id": "ru_1",
      "goal": "查询订单当前物流位置",
      "capability": "shipment_tracking",
      "arguments": {
        "order_id": "O-123"
      },
      "status": "READY"
    },
    {
      "id": "ru_2",
      "goal": "解释物流三天未更新的原因和处理方式",
      "capability": "delivery_exception_resolution",
      "arguments": {
        "order_id": "O-123",
        "reported_issue": "NO_RECENT_UPDATE"
      },
      "status": "READY"
    }
  ]
}
```

LLM 负责提出 Request Unit、候选 Capability 与参数；程序负责：

- 验证 Capability 是否存在。
- 校验 Capability 参数 schema。
- 根据 Capability Contract 计算 missing fields。
- 限制可见与可调用的 Tools。
- 执行权限、审批、预算、重试和终止控制。

## 7. P0 Runtime Scope

- Model Adapter
- Message contract
- Agent Loop
- Generic Run State
- Request Unit representation
- Capability Registry 与 validation
- Function Calling parsing
- Tool Registry
- Tool Executor
- Tool schema validation
- 多 Tool Call 的串行 / 并行策略
- `max_steps`、timeout、retry 与 termination
- 重复调用检测
- Conversation History
- Structured Working Memory
- 可恢复的跨轮次 / 跨会话任务状态
- RAG / Retriever integration
- Guarded Action execution
- Trace / Observability event
- Evaluation harness
- 标准化 Run Result

## 8. Proposed P0 Tools

### Read Tools

- `get_order`
- `get_shipment`
- `retrieve_delivery_policy`

### Action Tool

- `open_delivery_support_case`

`open_delivery_support_case` 只创建本项目模拟环境中的内部支持 Case。它不代表真实承运商 Claim、退款、补发或赔偿已经成立。

### Human Responsibility Exit

- `ESCALATED` Run Result，必要时附带 handoff reason。

人工接管可以由 Runtime 结果表示，不要求伪造一个真实外部人工服务系统。

## 9. Anchor Scenario

P0 最重要的端到端场景是：

> “订单显示已签收，但我没有收到，帮我处理一下。”

它是 `delivery_exception_resolution` 的高密度验证场景，不是项目唯一支持的问题。

该场景应覆盖：

- Request Understanding 与缺失信息追问。
- Order / Shipment 多 Tool 调用。
- 配送政策 RAG。
- 领域 Evidence Assembly。
- Action proposal 与明确确认。
- 幂等 Case 创建。
- Tool failure、无证据和人工接管。
- 完整 Trace 与 E2E Evaluation。

## 10. P0 Non-goals

- 完整消费者客服平台。
- 完整售后能力矩阵。
- 退款、换货、维修、发票、优惠券等独立业务域。
- 坐席工作台、运营后台或消费者账户中心。
- 真实订单、真实物流、真实承运商 Claim 或真实支付集成。
- 多 Agent 协作。
- 通用 Workflow DSL 或 DAG 编排平台。
- 分布式 Runtime。
- P0 MCP integration。
- 同时接入大量 Model Providers。
- 生产部署、真实客户、采用率、ROI 或商业价值声明。
- 在第二个不同 Reference Application 验证前声称 Runtime 已经通用。

## 11. Implementation Principles

- Failure-driven evolution：每个抽象由可复现的问题驱动。
- Trace from day one：第一版 Loop 就产生结构化 Trace。
- Eval alongside capability：每增加能力，同步增加测试和 Eval Case。
- One provider first：先接一个模型，再验证 Adapter 是否可替换。
- Framework-free does not mean library-free：不使用 Agent orchestration framework，但允许使用 HTTP、JSON Schema、数据库和向量检索等基础库。
- Side effects are controlled：模型只能提出 Action，程序拥有执行权。
- Domain truth stays outside Runtime：Runtime 不解释订单、物流和政策语义。
- No capability inflation：新增 Capability 必须带来新的用户目标或新的 Runtime 验证价值。

## 12. Completion Evidence

P0 完成至少需要：

1. 一套可阅读、可测试的 Runtime 代码。
2. 四项 Capability 的可复现示例。
3. 一条完整 Anchor Scenario Demo。
4. 一条失败与恢复 Demo。
5. 每次运行的结构化 Trace。
6. Tool、Request Understanding、Retrieval、Action 与 E2E Eval。
7. 有副作用动作的权限、确认、幂等和审计证据。
8. 一个可恢复未完成任务的 Memory 示例。
9. 一个极小的非售后 Agent 复用同一 Runtime 的验证。
10. 一份与主流 Agent framework 的概念映射和取舍说明。

## 13. Truth and Reference Boundary

- 所有订单、物流、政策与 Case 数据均使用明确标记的 synthetic fixtures。
- 公开承运商流程只用于证明相关消费者任务存在，不表示本项目复刻了其内部 Agent 或获得真实 API 权限。
- FedEx 的公开流程包含 Tracking、Report Missing Package、Case Number 和 Support Ticket 查询；UPS 与 USPS 使用不同的 Claim / Missing Mail Search 规则。因此本项目采用自己的 synthetic `DeliverySupportCase`，不声称它是统一行业对象。
- 设计参考：[FedEx Missing Package](https://www.fedex.com/en-us/customer-support/faqs/receiving/tracking-questions/fedex-says-delivered-but-no-package.html)、[UPS File a Claim](https://www.ups.com/us/en/support/file-a-claim)、[USPS Missing Mail](https://www.usps.com/help/missing-mail.htm)。
- Request Understanding 参考 task / flow / playbook-oriented approaches：[Rasa CALM Conversation Design](https://rasa.com/docs/learn/best-practices/conversation-design/)、[Dialogflow CX Playbooks](https://docs.cloud.google.com/dialogflow/cx/docs/concept/playbook)。

## 14. Document Set

- [Project Outline](./PROJECT_OUTLINE.md)：整体演进路线与学习顺序。
- [Delivery Support Scenario Contract](./DELIVERY_SUPPORT_SCENARIO_CONTRACT.md)：P0 Request Unit、Capability、Tool、状态、Guardrail 与 Eval 行为合同。

上述文件在用户明确接受前均保持 Draft。
