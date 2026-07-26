# Mini Agent Runtime 项目大纲

> 状态：`DRAFT / NON_NORMATIVE / NOT IMPLEMENTED / NOT VERIFIED`
>
> 日期：`2026-07-22`
>
> 用途：记录一个独立、求职导向的 Agent Runtime 学习与实现项目大纲。
>
> 权威边界：本文只是新项目的初始 Scope Draft，不是已经接受的产品、架构或实现结论，也不改变 MOCA2 的现有 active baseline。

## 1. 项目核心定位

本项目拟定位为：

> 一个从零实现、不依赖现成 Agent orchestration framework 的轻量 Agent Runtime；通过一个有边界的 Consumer Order & Delivery Support Agent，验证 Agent Loop、Request Decomposition、Capability Routing、Function Calling、Memory、RAG、Guardrails、Trace 与 Evaluation 等核心机制。

项目的技术主角是 `Agent Runtime`，消费者订单与配送支持只是 `Reference Application`。

项目主要用于证明：

- 能够亲手搭建并解释 Agent 的底层执行机制。
- 理解 LLM、Runtime、Tool、Memory、RAG 与确定性程序之间的责任边界。
- 能够发现并处理 Agent 在真实运行中出现的失败、重复调用、权限、终止和状态问题。
- 能够通过 Trace 与 Evaluation 复现、解释和验证 Agent 行为。
- 能够说明何时适合自研 Runtime，何时适合使用 LangGraph、OpenAI Agents SDK 等框架。

## 2. 项目不是完整客服系统

P0 不追求：

- 完整售后业务能力矩阵。
- 完整消费者客服平台。
- 坐席工作台或运营后台。
- 覆盖退款、换货、维修、发票、优惠券等大量业务。
- 多 Agent 协作平台。
- 通用 Workflow DSL 或 DAG 编排器。
- 真实支付、真实退款或真实物流系统集成。
- 生产部署、真实客户或商业效果声明。
- 为展示技术名词而同时接入大量模型、框架或协议。

## 3. Runtime 与 Reference Application 的边界

```text
消费者聊天入口
        ↓
Order & Delivery Support Reference Application
Request Unit、Capability、领域工具、配送知识、业务规则
        ↓
Agent Runtime
Loop、State、Tool Execution、Memory Integration、Failure Control、Trace
        ↓
Model Provider / Database / Retriever / External API
```

### 3.1 Agent Runtime 负责

- `Agent Loop`
- `Agent State`
- Message 与 Event contract
- Model Adapter
- Function Calling 解析
- Tool Registry
- Tool Executor
- Tool schema validation
- 多 Tool Call 调度
- `max_steps`、timeout 与 termination
- retry、重复调用检测与失败恢复
- Memory 接入与生命周期协调
- RAG / Retriever 接入与证据传递
- Approval / Guardrail 执行控制
- Trace / Observability event
- 标准化 Run Result

### 3.2 Order & Delivery Support Reference Application 负责

- 领域 System Prompt 与行为边界。
- Request Unit、Capability 与 argument schema。
- Order、Shipment、DeliveryPolicy 与 DeliverySupportCase 等领域对象。
- 订单状态、物流跟踪、配送异常和配送政策的业务解释。
- Capability 到 allowed tools、required arguments 与 risk class 的映射。
- 消费者身份、订单归属与操作授权要求。
- 何时继续调查、请求确认或转人工。

### 3.3 基础设施负责

- 模型推理或 API。
- 数据存储。
- 文档索引与向量检索。
- 外部订单、物流或动作服务。

Runtime 使用这些能力，但不等于这些基础设施本身。

### 3.4 为什么 Runtime 不包含订单类型，却能运行订单与配送场景

这里不存在“Runtime 一边不认识订单，一边又亲自组装订单证据”的设计。正确的责任划分是：

```text
Agent Runtime
只认识：ToolCall、ToolResult、RunState、Message、EvidenceEnvelope

Order & Delivery Support Reference Application
认识：Order、Shipment、PolicyEvidence、DeliverySupportCase
```

例如，Runtime 可以提供通用的 Tool 执行和上下文传递机制：

```text
ToolCall(name, arguments)
ToolResult(tool_call_id, status, payload, error)
EvidenceEnvelope(source, content, metadata)
```

但以下领域对象及其解释规则由 Order & Delivery Support Reference Application 拥有：

```text
Order
Shipment
AfterSalesPolicy
DeliverySupportCase
```

Reference Application 负责把 `Order + Shipment + PolicyEvidence` 转换为本次模型调用需要的领域上下文；Runtime 只负责在正确时机调用这个能力、传递结果、维护执行状态和记录 Trace。Runtime 不需要知道 `shipment.status = DELIVERED` 在订单与配送业务上意味着什么。

## 4. P0 Problem Space 与 Capability Catalog

Reference Application 处理一个有边界的消费者订单与配送支持领域，但不建立“一条消息只能分类成一个 Intent”的平铺 Taxonomy。

一条消息可以动态拆为一个或多个 `RequestUnit`，再映射到 closed `Capability Registry`：

```text
User Message + Conversation State
        ↓
Request Understanding / Decomposition
        ↓
RequestUnit[]
        ↓
Capability Validation and Routing
        ↓
Tool / RAG / Controlled Workflow
```

P0 Capability：

| Capability | 用户目标 | 主要验证机制 |
|---|---|---|
| `order_status_lookup` | 查询订单是否创建、取消、出库或发货 | Request Understanding、单 Tool Call |
| `shipment_tracking` | 查询包裹状态、节点与预计送达 | 多 Tool 串行、Context Assembly |
| `delivery_exception_resolution` | 理解并处理延迟、无更新、派送失败、签收未收到 | 多步调查、RAG、Memory、Guardrails |
| `delivery_policy_qa` | 查询配送及异常处理政策 | RAG、Citation、No-evidence Handling |

`open_delivery_support_case` 是 `delivery_exception_resolution` 可能调用的 Action Tool，不是 Intent 或 Capability；`OUT_OF_SCOPE` 是 Routing Result，不是 Intent。

最重要的 Anchor Scenario 是：

> “订单显示已签收，但我没有收到，帮我处理一下。”

建议主路径：

1. 产生 `delivery_exception_resolution` Request Unit，`reported_issue=DELIVERED_NOT_RECEIVED`。
2. 提取 Order ID；缺失时向消费者追问。
3. 通过 `get_order` 查询订单并验证归属。
4. 通过 `get_shipment` 查询物流事实。
5. 通过 RAG 检索适用的 missing-delivery policy。
6. Reference Application 的 Context / Evidence Assembler 组装 Order、Shipment 与 Policy evidence。
7. 给出证据化处理建议，并在适用时提出创建内部 Delivery Support Case。
8. 明确确认后调用 `open_delivery_support_case`。
9. 返回唯一 synthetic Case ID；结果未知时不得宣称成功。
10. 保存完整 Trace 和可评测结果。

## 5. P0 场景与边界

| 场景 | 期望行为 | 主要验证能力 |
|---|---|---|
| 查询订单是否发货 | `order_status_lookup` | Request Understanding、单 Tool Call |
| 查询包裹位置 | `shipment_tracking` | 多 Tool 串行、可信 ID 传递 |
| 物流长时间未更新 | `delivery_exception_resolution` | 异常调查、RAG |
| 派送失败 | `delivery_exception_resolution` | Tool Result Interpretation、Policy |
| 签收未收到 | Anchor Scenario | RAG、Action Gate、Idempotency |
| 查询一般配送政策 | `delivery_policy_qa` | Retrieval、Citation |
| 同时查询位置和异常原因 | 拆为多个有依赖的 Request Unit | Request Decomposition、Shared State |
| 缺少 Order ID | 统一追问，不猜测 | Required Argument Validation |
| Order 不存在或未授权 | 不泄露并安全结束 | Authorization、Guardrails |
| Tool timeout 或失败 | 有界重试、降级或转人工 | Failure Recovery |
| RAG 无证据或证据冲突 | 明示边界，不编造政策 | Grounding、RAG Failure Handling |
| 无关或部分支持的复合请求 | 保留所有目标并明确处理边界 | Partial Routing、Run Result |

## 6. 建议的 P0 Tool Set

### 只读工具

- `get_order`
- `get_shipment`
- `retrieve_delivery_policy`

### 有副作用动作

- `open_delivery_support_case`

### 人工责任出口

- `ESCALATED` Run Result，附带可追踪的 handoff reason

Runtime 应区分 `READ_TOOL` 与 `ACTION_TOOL`。模型可以提出 Tool Call，但程序负责权限检查、参数验证、审批与实际执行。

## 7. 分阶段实现大纲

### Phase 0：初始化独立项目并冻结范围

- 建立独立项目目录与最小 README。
- 确认项目定位、P0 Problem Space、Capability Catalog 与 Anchor Scenario。
- 定义 Non-goals、完成标准与证据要求。
- 定义 Runtime、Reference Application 与 Infrastructure 的代码边界。

### Phase 1：可追踪的最小 Agent Loop

- Message contract
- Model Adapter
- Tool Definition
- Tool Registry
- Tool Executor
- Agent State
- Agent Loop
- `max_steps`
- 标准化 Run Result
- JSONL 或等价 Trace Event

目标：使用一个只读 Tool 跑通 `LLM → Tool Call → Tool Result → LLM → Final Answer`。

### Phase 2：健壮的 Tool System

- JSON Schema 参数校验。
- 未注册 Tool 处理。
- Tool exception、timeout 与 retry。
- Tool Result 与 `tool_call_id` 关联。
- 多 Tool Call 的串行 / 并行策略。
- 重复 Tool Call 检测。
- 统一失败协议。

### Phase 3：Request Understanding

- 定义可观察、可评测的 `RequestUnit[]` 结构化输出。
- 支持一条消息拆为多个目标及依赖关系。
- 通过 closed Capability Registry 验证候选 Capability。
- LLM 提取候选 arguments；程序根据 Capability Contract 计算 missing fields。
- 对比传统单 Intent Router、直接 Tool Selection 与 Request Unit + Capability routing 的取舍。
- Runtime 不硬编码订单与配送 Capability；Reference Application 拥有领域 schema。

### Phase 4：Memory

- Conversation History。
- Structured Working Memory。
- 跨轮次 Agent State persistence。
- 明确的 Memory write / read policy。
- 通过恢复未完成 Request Unit 验证跨会话 Task Memory，不为展示 Memory 发明独立业务能力。
- 验证错误记忆、过期信息与冲突更新。

### Phase 5：RAG

- Document loading。
- Chunking 与 metadata。
- Indexing。
- Query construction。
- Retrieval。
- Evidence assembly。
- Citation。
- 无结果和冲突证据处理。
- Retrieval 与 grounded-answer evaluation。

### Phase 6：Guarded Action

- 增加 `open_delivery_support_case`。
- 身份与订单归属检查。
- Action 前置条件。
- 明确消费者确认。
- `idempotency_key`。
- Critical Audit。
- 超时后的执行结果确认。
- 失败恢复与人工接管。

### Phase 7：Evaluation Consolidation

- Tool contract test。
- Request Understanding eval。
- Retrieval eval。
- Tool / Action selection eval。
- Action safety eval。
- End-to-end task completion eval。
- 每个 Eval Case 可追溯到完整 Trace。

Evaluation 不能只判断最终文本，还应验证实际工具、参数、证据、审批、动作结果和终止状态。

### Phase 8：求职展示与框架对照

- 三分钟主路径 Demo。
- 一个失败与恢复 Demo。
- Runtime 架构图。
- 可展开的 Trace。
- Eval 报告。
- 有证据的失败案例与设计取舍。
- 使用同一场景对照 LangGraph 或 OpenAI Agents SDK 的抽象。
- 用一个极小的第二 Agent 验证 Runtime 没有硬编码订单与配送领域。

## 8. 实现原则

- 采用 failure-driven evolution：每个抽象都由可复现问题驱动。
- Trace 从第一版开始，而不是最后补充。
- Eval 随能力逐步增加，而不是项目结束后一次性补齐。
- P0 只连接一个 Model Provider；接口先稳定，再验证替换能力。
- “不使用 Agent framework”不等于“不使用任何基础库”。
- 不重新实现 HTTP、JSON、数据库、Tokenizer 或向量数学等通用基础设施。
- MCP 暂不进入 P0；Tool Contract 稳定后，可作为 Tool Provider adapter 加入。
- 在第二个不同场景验证前，不声称 Runtime 已经“通用”。
- 不为了抽象完整性提前建设插件平台、Workflow DSL、分布式执行或多 Agent。

## 9. 建议的 Run Result

Runtime 应让一次运行以明确状态结束，例如：

- `COMPLETED`
- `NEEDS_USER_INPUT`
- `APPROVAL_REQUIRED`
- `ESCALATED`
- `FAILED`

避免只把模型自然语言作为任务是否完成的唯一依据。

## 10. P0 完成标准

- Runtime 核心不包含 Order、Shipment、DeliveryPolicy 等领域类型。
- 复合消息能够拆为 Request Unit，并映射到 closed Capability Registry；Anchor Scenario 能够端到端运行。
- 缺失信息、工具失败、无 RAG 证据、未确认动作和重复动作均有可复现用例。
- 每次运行都有完整 Trace。
- Tool、Request Understanding、Capability Routing、Retrieval、Action 与 E2E 均有对应验证。
- 有副作用动作经过权限、确认与幂等控制。
- Runtime 能以明确 Run Result 结束，且不会无限循环。
- 一个极小的第二 Agent 可以复用同一个 Runtime。
- README、Demo 和面试材料只陈述已有仓库证据，不声称生产部署或真实业务验证。

## 11. 预期求职证据

最终项目应优先产出：

1. 一套可阅读、可测试的 Agent Runtime 代码。
2. 一条完整消费者订单与配送支持 Demo。
3. 一条失败与恢复 Demo。
4. 一份完整 Agent Trace。
5. 一套可重复运行的 Eval。
6. 一份“问题—根因—方案—验证—取舍”记录。
7. 一篇 Runtime 逐步演进文章。
8. 一份与主流 Agent framework 的概念映射和选择依据。

## 12. Pre-code Artifacts

进入代码前的两份 Draft artifact 已建立：

1. [Project Brief](./PROJECT_BRIEF.md)：项目定位、P0 Problem Space、Capability Catalog、Non-goals 与完成证据。
2. [Delivery Support Scenario Contract](./DELIVERY_SUPPORT_SCENARIO_CONTRACT.md)：Request Unit、Capability、Anchor Scenario、Tool、State、Guardrail 与 Eval Cases。

两者经用户明确接受后，再进入第一个实现切片：

> 实现带 `max_steps` 与 Trace 的最小 Agent Loop，并使用一个只读 Tool 跑通完整循环。
