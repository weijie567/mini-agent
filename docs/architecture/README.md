# 消费者订单与配送售后 Agent｜架构图索引

更新日期：2026-07-25  
状态：P0 当前架构与配套视图索引

## 语义 Owner

- P0 业务范围、两条 E2E、Tool Catalog、四个 Mock 系统和业务验收边界：[business-capabilities.md](../business-capabilities.md)
- 当前项目方向与 Runtime 主干：[PROJECT_DIRECTION.md](../../PROJECT_DIRECTION.md)
- Eval-driven development、通用 EvalCase、Dataset 生命周期、Grader、Gate、报告与架构决策证据：[Agent Evaluation Strategy](../evaluation/agent-evaluation-strategy.md)
- P0 Case ID、requirement mapping、Critical failure 和激活状态：[P0 Eval Coverage Matrix](../evaluation/p0-eval-coverage-matrix.md)
- Request Understanding、Query 上下文化、`TaskDeltaCandidate`、`InputBinding` 与确定性校验：[intent-design-reference.md](intent-design-reference.md)
- Tool Registry / Executor、不可变工具集快照、Provider 名称映射、Control Gateway 工具校验、ToolCall 生命周期、超时、中断及工具调用 Trace / Eval：[tool-calling-design-reference.md](tool-calling-design-reference.md)
- Memory、Run / Task State、Observation、Evidence、Action Ledger 与 Context Manifest：[memory-design-reference.md](memory-design-reference.md)
- Policy Corpus 受控 ingestion、清洗、结构解析、Chunking、Hybrid Retrieval、RRF、Cross-Encoder、Evidence 组装处理与 RAG Eval：[rag-design-reference.md](rag-design-reference.md)

图形用于表达这些 owner 的派生视图；图中简写不得覆盖对应文档的语义。

## 当前架构基线：业务应用架构 V2

- 可编辑源文件：`consumer-after-sales-agent-business-application-architecture-v2.drawio`
- SVG：`consumer-after-sales-agent-business-application-architecture-v2.svg`
- PNG：`consumer-after-sales-agent-business-application-architecture-v2.png`

业务应用架构 V2 是当前最新、唯一的 P0 架构基线。它采用“业务主线 + 关键技术模块”的表达方式：

```text
已登录消费者
  → 自建站业务应用与可信身份
  → Application Services
  → Agent Runtime
  → Business Capabilities
  → P0 Mock Business Systems
```

图中的运行核心是：

```text
RequestUnit Board + Controlled ReAct + ActionPolicy
```

其中 Request Understanding 使用开放目标 `TaskDeltaCandidate`，由确定性 Validator / Reducer 写入薄 RequestUnit；不使用业务 Intent / Capability 分类、RequestUnit Tool allowlist 或固定 Tool 路由。详细契约见 [Intent / Request Understanding Design Reference](intent-design-reference.md)。

业务能力区只表达“订单与物流事实、政策 Evidence 与退款判断、受控模拟退款与结果恢复”三个稳定业务语义；底部只包含 Mock Order System、Mock Shipment System、Policy Knowledge Base 和 Mock Refund System。具体工具名由 Tool Catalog 管理。

RAG 的 P0 内部链路采用 `Hard Gate → Dense + Sparse → RRF → Cross-Encoder → EvidenceAssembler`。它不增加独立知识服务、Relation Expansion 或 Knowledge Graph；详细契约见 [RAG Design Reference](rag-design-reference.md)。

`RegistrySnapshot`、模型可见 Toolset Hash、ToolCall 生命周期、Provider 名称映射和中断记录属于 `Tool Registry & Executor`、`Control Gateway` 与 Trace / Eval 内部契约，不新增独立服务或业务组件，因此不在业务应用架构图中展开；详细语义见 [Tool Calling Design Reference](tool-calling-design-reference.md)。

LLM、状态持久化、Trace 和 Agent Eval 位于右侧平台支撑区，不表示业务请求必须顺序经过的一层。Eval 采用贯穿实现全过程的 Eval-driven development，而不是架构图中的固定串行节点；通用方法和 P0 Case mapping 分别见 Agent Evaluation Strategy 与 P0 Eval Coverage Matrix。图中的 `Run & Task State` 与 `State & Record Stores` 是视觉分组；Observation、Evidence、Decision & Action Ledger 和 Trace 仍按 Memory Design Reference 分域，L2 Task Working Context 只保留引用与最小投影。

P0 不包含独立公开产品知识服务、Capability Registry、外部渠道适配、多 Agent、Workflow DSL 或微服务拆分。

## 配套代码分层与允许依赖 V2

- 可编辑源文件：`consumer-after-sales-agent-code-layer-dependency-v2.drawio`
- SVG：`consumer-after-sales-agent-code-layer-dependency-v2.svg`
- PNG：`consumer-after-sales-agent-code-layer-dependency-v2.png`

这张图只表达源代码依赖，不表达运行时调用顺序，也不拥有 Memory、状态或存储技术的语义。代码宏观分为接入层、应用层、核心层和基础设施层；关键外部边界采用 Ports & Adapters：

```text
Inbound Adapter → Inbound Port
Application → Core
Outbound Adapter → Application-owned / Core-owned Port
Adapter → External Client
```

Application / Core 分别拥有自身职责范围内的 Port；核心层不得依赖具体 Adapter、Web / DB / HTTP / LLM SDK。`Bootstrap / Composition Root` 是唯一允许同时引用 Port 与具体 Adapter 并完成依赖注入的位置。

V2 将 L2 明确为 `Task Working Context`，只保存 `ObservationRef`、`EvidenceBinding`、`ActionRef` 与状态版本。Conversation 生命周期和消息持久化通过 Application-owned Port 访问；Run / Task State、Observation / Evidence Records、Action Ledger、Trace 和 Context Manifest 通过 Core-owned Port Groups 访问。Port 按 owner、事务和测试边界拆分，不要求一种记录对应一张表或一个 Port。P0 权威状态使用关系数据库，Redis 不属于当前依赖基线。

## 业务流程图 V2

- 两页可编辑源文件：`consumer-after-sales-agent-business-flow-v2.drawio`
- E2E-01：
  - `consumer-after-sales-agent-business-flow-v2-page-1-order-resolution-query.svg`
  - `consumer-after-sales-agent-business-flow-v2-page-1-order-resolution-query.png`
- E2E-02：
  - `consumer-after-sales-agent-business-flow-v2-page-2-refund-controlled-recovery.svg`
  - `consumer-after-sales-agent-business-flow-v2-page-2-refund-controlled-recovery.png`

两页目标分别是“订单定位、物流查询与配送异常判断”和“退款资格、受控模拟执行与结果恢复”。它们用于解释动态路径和安全闭环，不把 Runtime 固化为确定性 Workflow。

Flow V2 已删除退出 P0 的独立公开产品知识分支，并明确区分 Agent 本轮结果、Task 状态与 Action Ledger 执行状态。Task 等待用户时使用 `WAITING_USER`，对外仍映射为 `ASK_USER`；退款动作使用 Memory Design Reference 定义的 Ledger 状态。两页仍是配套说明视图，业务范围与状态契约分别服从 `business-capabilities.md` 和 Memory Design Reference。

## 历史参考

- `consumer-after-sales-agent-business-flow-v1.drawio`：三页旧流程源文件。
- `consumer-after-sales-agent-business-flow-v1-page-1-overview.*`：旧流程第 1 页导出。

历史图不再作为实现基线。此前 README 中引用但仓库实际不存在的 `consumer-after-sales-agent-p0-architecture.*`、`consumer-after-sales-agent-business-runtime-architecture.*` 和 `consumer-after-sales-agent-logical-architecture.*` 已从 active 索引移除。
