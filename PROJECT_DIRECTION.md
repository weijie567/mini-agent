# 消费者订单与配送售后 Agent｜P0 项目方向与架构决策

更新日期：2026-07-26  
状态：P0 当前方向与架构基线

> 本文是当前可执行方向的基线，不是不可变的永久结论。发现新的失败证据或更优候选方案时，按问题说明、影响分析、Eval 对照、owner 裁决和 cross-file alignment 演进；具体证据链见 [`Agent Evaluation Strategy`](docs/evaluation/agent-evaluation-strategy.md#10-eval-作为架构决策证据)。

## 1. 项目定位

- 项目主体是“消费者订单与配送售后 Agent”，不是通用 Agent Runtime。
- P0 只模拟一个自建站，不接入京东、淘宝或其他外部渠道。
- 目标是在最小业务范围内同时展示：请求理解、动态决策、工具调用、安全控制、状态恢复、RAG Evidence、Trace 和 Agent Eval。
- 采用模块化单体。图中的层是逻辑和代码边界，不代表拆成多个微服务。
- 旧 Runtime-first 设计已归档至 `archive/legacy-runtime-first-design-2026-07-23/`，不再作为当前架构基线。

## 2. P0 业务能力与端到端场景

P0 保留四类消费者目标：

1. 查询本人订单、商品和按需物流状态。
2. 识别配送异常。
3. 判断退款资格并解释政策。
4. 创建模拟退款并查询、恢复退款状态。

消费者目标、业务能力和端到端场景是三种不同概念：

- 消费者目标描述用户想完成什么。
- 业务能力是可以被不同场景复用的业务职责，不代表固定执行顺序。
- 端到端场景必须从用户输入开始，经过可信身份、目标定位、数据归属、动态决策和权限控制，以安全回复结束。

### 2.1 P0 业务能力

P0 使用三个稳定业务语义分组表达范围：

| # | 业务能力组 | P0 说明 |
|---|---|---|
| 1 | 订单与物流事实 | 定位本人订单和商品，按需查询订单、Shipment / Package，并基于可信 Observation 判断 P0 配送异常 |
| 2 | 政策 Evidence 与退款判断 | 检索退款政策，组装 Evidence，使用确定性规则判断资格并生成可解释、可确认的方案 |
| 3 | 受控模拟退款与结果恢复 | 通过动作门禁创建一次模拟退款，查询处理状态并恢复 `RESULT_UNKNOWN` |

这三个分组用于产品与架构沟通，不对应 Runtime 中的 `Capability` 对象，也不形成固定的分组到 Tool 路由。P0 业务范围、Tool Catalog、Mock 系统和验收边界以 [`docs/business-capabilities.md`](docs/business-capabilities.md) 为 canonical owner。

Request Understanding、多意图拆分、受控 ReAct、回复披露控制、Run / Task State、Trace 和 Eval 是支撑上述业务能力的 Agent / 平台能力，不单独算作消费者业务能力。

### 2.2 E2E-01：订单定位、物流查询与配送异常判断

这条读操作主流程覆盖自然语言或订单号定位本人订单、候选确认、订单与物流按需查询及配送异常判断：

1. 验证 Session / JWT，从服务端加载可信 `CustomerContext`。
2. 理解用户目标、目标来源和必要参数。
3. 在本人资源范围内定位订单：
   - 明确订单号：使用 `(customer_id, order_id)` 联合查询。
   - 自然语言描述：使用 `customer_id + 时间范围 + 商品名称 / 类别` 搜索本人近期订单。
4. 处理定位结果：
   - 唯一候选：绑定经过归属验证的订单和商品。
   - 多个候选：只展示本人订单的最小必要摘要，返回 `ASK_USER`；用户确认后恢复同一个 RequestUnit。
   - 无结果或无权访问：统一映射为 `NOT_FOUND_OR_NOT_ACCESSIBLE`，不区分资源不存在和不属于当前用户。
5. 根据当前目标和最新 Observation 动态选择下一步：
   - 只问订单：返回最小订单摘要，不查询物流。
   - 询问位置、配送时间或异常：查询关联 Package，并仅在需要时执行配送异常判断。
6. 基于最新物流 Observation 和 P0 规则判断正常、延迟、停滞或签收未收到。
7. 外部事实不足或物流系统不可用时返回 `BLOCKED` 或 `NEED_HUMAN`，不猜测结果。
8. 保存可恢复任务和最新 Observation 引用，经过最小披露控制后回复。

非本人订单是硬安全边界：系统不能透露下单人、地址、支付、物流或订单内容；有效的非本人订单号与随机订单号必须产生相同的外部结果。

### 2.3 E2E-02：退款资格、受控模拟执行与结果恢复

这条决策与写操作主流程覆盖退款咨询、资格判断、明确确认、创建模拟退款、状态查询和未知结果恢复：

1. 接收用户消息，从可信 `CustomerContext` 获取 `customer_id`，识别资格咨询、创建模拟退款、状态查询或未知结果恢复目标。
2. 使用与 E2E-01 相同的目标定位和归属校验能力，定位本人订单、商品或退款记录；不能因为此前会话曾定位成功而跳过本轮授权和归属复核。
3. 无法确认资源属于当前用户时立即结束私有数据和动作路径，返回统一安全答复。
4. 根据当前目标动态收集所需事实：订单、必要时的物流、退款政策 Evidence 和既有退款状态。单纯查询退款状态不强制重新查询物流或政策。
5. 标准化 Observation，并由确定性判断输出：
   - `ELIGIBLE`：生成包含订单、商品、数量、金额、退款方式和影响的明确方案。
   - `NOT_ELIGIBLE`：说明不符合的政策依据，不进入执行。
   - `UNDETERMINED`：说明证据缺失、冲突或系统不可用，不允许执行退款。
6. 对可执行方案返回 `ASK_USER` 请求精确确认；订单、商品、数量、金额、退款方式、用户可见影响、关键 Observation、Evidence / 政策版本或授权发生变化时，原确认失效并必须重新确认。
7. `ActionPolicy` 在执行时重新检查资源归属和授权、关键 Observation 的版本与新鲜度、Evidence 完整性、适用性与新鲜度、精确确认、重复退款和幂等身份。
8. Gate 通过后调用 `create_refund`，并按结果处理：
   - `COMPLETED`：返回模拟退款编号和结果。
   - `PROCESSING`：返回当前状态和后续查询方式。
   - `FAILED`：说明明确失败原因和允许的下一步。
   - `RESULT_UNKNOWN`：禁止再次创建模拟退款，使用原幂等身份调用状态查询并对账恢复。
9. 经过回复披露控制后，向用户返回最终结果；无法在当前预算内恢复时明确返回 `BLOCKED`，不得伪报成功或失败。
10. 保存 Evidence、精确方案、确认、Action Record 和恢复点，允许跨会话继续。

### 2.4 场景覆盖

| 业务能力 | E2E-01 | E2E-02 |
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

这两条端到端场景是产品范围和验收覆盖视图，不是 Runtime 必须逐节点执行的确定性 Workflow。每条场景内部的只读工具路径仍由受控 ReAct 根据目标和最新 Observation 动态形成；归属校验、回复披露、退款确认、ActionPolicy 和未知结果恢复是不可绕过的确定性边界。

P0 Tool Catalog：

```text
search_orders
get_order
get_shipment
retrieve_refund_policy
get_refund_status
create_refund
```

P0 不实现：

- 京东、淘宝等平台适配器。
- 多租户、商家后台、坐席工作台、主管后台和复杂 Case Queue。
- 真实支付、真实退款和真实物流接口。
- 独立公开产品知识服务。
- 退货退款、换货、补发、取消订单、物流催促建单和通用售后 Case。
- 通用 Workflow DSL、DAG 编排器或多 Agent 平台。

## 3. RequestUnit、多意图识别与模型推理

当前项目保留“多意图”作为产品沟通术语，但不建设业务 Intent Classifier。Request Understanding 采用开放目标的 Goal Delta：模型只判断一条新用户消息对一个或多个持久用户目标造成了什么增量变化。

例如：

> 订单 O-1001 的包裹五天没更新了，帮我查一下，如果符合条件就退款。

模型可以产生两个 `ADD_GOAL` 候选：

```text
TD-1 查询订单 O-1001 关联包裹的当前状态，并解释是否异常
TD-2 若当前事实与政策判定符合条件，则在精确确认后创建模拟退款；使用 TD-1 的结果
```

本人订单定位、物流 ToolCall、配送异常判断、政策检索、退款资格判断、方案生成、ActionPolicy 和结果恢复都属于目标内部的动态推进，不再拆成额外 `RequestUnit`。

三者职责不同：

- `TaskDeltaCandidate`：本轮模型提出的新增、修正、补充、取消或确认候选，不是状态或事实。
- `RequestUnit`：Runtime 验证并归并后保存的一个可被用户感知、可独立完成或取消的持久目标。
- `NextMove`：Controlled ReAct 基于最新状态提出的单步计划，不写回 RequestUnit 成为固定流程。

推荐链路：

```text
LLM
  → contextualized_query + TaskDeltaCandidate[]
Runtime
  → 校验来源、Task 绑定、目标粒度、依赖、纠正和确认候选
  → TaskStateReducer 写入 RequestUnit Board
Controlled ReAct
  → 基于新 state_version 和最新 Observation 动态选择 NextMove
```

`TaskDeltaCandidate` 只使用跨领域稳定的状态操作：

```text
ADD_GOAL
AMEND_GOAL
SUPPLY_INPUT
CANCEL_GOAL
CONFIRMATION_CANDIDATE
```

薄 RequestUnit 至少包含：

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

RequestUnit 不携带 `intent_type`、`capability`、`required_arguments`、`allowed_tools`、Handler、Workflow 或固定 Tool 顺序。`open_questions` 只记录当前安全推进真正缺少的信息，不是 Intent 的固定 Slot 表。

模型输出的是候选，程序负责结构校验、状态迁移和权威边界。`observation_refs` 指向带来源、时间和版本的业务 Observation；`evidence_binding_refs` 指向版本化政策 Evidence；输入候选、Observation、Evidence 和 Action Parameter 不得互相替代。

完整契约以 [`docs/architecture/intent-design-reference.md`](docs/architecture/intent-design-reference.md) 为准。

## 4. P0 不采用 Capability Registry 主抽象

第 2 节的“业务能力”是产品范围、职责分解和场景覆盖标签，不对应 Runtime 中的 `Capability` 对象，也不要求建立 Capability Registry 或固定的 Capability-to-Tool 路由。

当前 P0 不采用 `RequestUnit + Capability Registry`。Runtime 的关键机制统一表达为：

```text
RequestUnit Board + Controlled ReAct + ActionPolicy
```

删除 Capability 的原因：

- Capability 容易与 Intent / RequestUnit goal 重复。
- 固定的 Capability → allowed tools 映射会把动态 Agent 再次变成静态路由。
- 每个 Capability 都是死配置时，新增场景容易漏掉模型实际需要的工具。
- P0 只有有限目标和六个工具，不需要再增加一层目录抽象。

`Tool Registry & Executor` 管理已注册工具、完成执行路由并标准化 Observation。每个已注册工具包含：

```text
工具定义（Agent 可见）
  name
  description
  input_schema
  output_schema

Runtime 私有注册信息
  effect: READ | RETRIEVAL | ACTION
  risk
  idempotency
  unknown_result_recovery
  handler
```

P0 在启动时完成 Tool 注册、完整性校验、Provider 名称映射和不可变工具集快照；模型调用与后续 `Control Gateway` 必须使用同一个快照。Tool Registry / Executor、模型可见 Toolset Hash、ToolCall 生命周期、严格超时、中断与结果分流的专项契约以 [`docs/architecture/tool-calling-design-reference.md`](docs/architecture/tool-calling-design-reference.md) 为准。

模型根据最新 Observation 从当前可用的已注册工具中动态选择。Runtime 不预先固定每个 RequestUnit 的工具顺序。

模型无法调用未注册的工具，因此工具覆盖率应通过 Tool Registry 注册检查、场景测试和 Eval 保证，而不是通过 Capability 再包一层。P0 不再为工具元数据定义单独的核心抽象。

## 5. 受控 ReAct

每轮模型只提出一个结构化 `NextMove`：

```text
CALL_TOOL
ASK_USER
PROPOSE_ACTION
FINISH
ESCALATE
```

执行循环：

```text
Model → NextMove → Control Gateway → Tool / ActionPolicy
  ↑                                      ↓
Context ← Run / Task State ← Observation
```

原则：

- 路径由最新 Observation 动态形成，不预设 Tool 顺序。
- 不使用业务 Workflow 或 DAG 表达退款步骤。
- Runtime 状态机只管理运行状态、预算、失败和停止，不规定具体业务流程。
- RequestUnit 的依赖和条件是任务状态，不是硬编码执行图。

`Control Gateway` 对所有 NextMove 负责：

- 使用本次模型调用的同一不可变工具集快照，校验 Provider 名称映射、工具可见性、注册状态和输入 Schema。
- 步数、Token、时间预算。
- 重复调用、无进展和停止条件。
- ASK_USER、FINISH、ESCALATE 等结果合法性。

`ActionPolicy` 只对有副作用的动作负责：

- 所需 Evidence 是否完整、适用且新鲜。
- 用户是否确认了同一个、参数明确的退款动作。
- 当前业务权限是否允许执行。
- 幂等键、重复提交和 `RESULT_UNKNOWN` 恢复。

身份认证不属于 ActionPolicy。

## 6. P0 业务应用架构

本节与当前业务应用架构 V2 的五段主线及右侧平台支撑区一致。图中的区域是模块职责边界，不表示拆成微服务，也不表示一次请求必须固定顺序调用所有区域。

### 6.1 Self-hosted Business Application｜消费者入口与可信身份

- Web Chat UI：消息与流式回复。
- Auth Middleware：验证登录 Session / JWT。
- Conversation API：完成请求 / 响应映射。
- `CustomerContext`：保存可信身份和授权范围，保持 Runtime 私有。
- P0 只有一个自建站消费者入口。

### 6.2 Application Services｜会话与 Agent 运行编排

简称“应用编排层”，只协调用例，不做模型推理：

- `ConversationService`：创建、恢复、关闭对话，选择本轮需要的历史。
- `AgentRunCoordinator`：绑定 CustomerContext，加载 Task / Run 状态，启动或恢复 Runtime。
- `RunResultMapper`：将内部结果安全映射为 `ASK_USER / PROCESSING / COMPLETED / BLOCKED / NEED_HUMAN / NOT_FOUND_OR_NOT_ACCESSIBLE`，并执行最小披露；安全敏感结果绕过模型措辞，普通已授权结果交给确定性 Renderer 注入事实值。
- 协调状态提交和事务边界。

不属于这一层的内容：

- Web、SSE、JWT 等协议细节。
- Task Delta 理解与校验、RequestUnit 状态归并、ReAct、Evidence 判定和 Tool 执行。
- 数据库和外部 API 的具体实现。

### 6.3 Agent Runtime｜理解、动态决策与受控执行

- Request Understanding：Query 上下文化、`TaskDeltaCandidate` 与确定性校验。
- RequestUnit Board。
- Model Context Projector / Context Assembler。
- ReAct Reasoner 与结构化 NextMove。
- Control Gateway、ActionPolicy、Tool Registry & Executor。
- Observation 标准化、Run / Task State 和恢复点。

### 6.4 Business Capabilities｜P0 稳定业务语义

- 订单与物流事实。
- 政策 Evidence 与退款判断。
- 受控模拟退款与结果恢复。

这些是面向业务和架构沟通的稳定分组，不是 `Capability` 对象，不形成固定 Tool 路由。具体工具由 Tool Catalog 管理；Business Tool Adapter 是 Runtime 与业务系统之间的实现边界，不单独画成业务层。

### 6.5 Business Systems｜P0 模拟业务系统

- Mock Order System。
- Mock Shipment System。
- Policy Knowledge Base。
- Mock Refund System。

业务工具执行时由服务端注入 `customer_id` 等可信参数。ToolResult 和失败类型在边界标准化；只有通过资源归属校验的白名单投影才能形成普通业务 Observation，政策 Evidence 由 Evidence Assembler 绑定。不存在、不属于当前用户或无法确认归属的私有资源必须先归一化为 `NOT_FOUND_OR_NOT_ACCESSIBLE`，不得把真实差异送入模型或普通记录域。

Policy Corpus 的受控 ingestion、清洗、结构解析、Chunking，以及 Hybrid Retrieval、RRF、Cross-Encoder、Evidence 组装处理和 RAG Eval 的专项契约以 [`docs/architecture/rag-design-reference.md`](docs/architecture/rag-design-reference.md) 为准；Evidence Binding 的权威字段和生命周期仍以 Memory Design Reference 为准。

### 6.6 AI 与平台支撑

- LLM Provider：只接收 `ModelVisibleContext`，返回结构化 `NextMove`。
- State & Record Stores：持久化 Conversation、Run、Task State，以及独立的 Observation、Evidence Binding 与 Action Ledger 记录域。
- Trace & Agent Eval：支持 Trace Store、Dataset、Report 及 Component / Trajectory / E2E Eval。

该支撑区服务于 Application / Runtime，不是业务请求顺序中的一层。具体存储和 Adapter 选择属于基础设施实现，不改变领域权威边界。

P0 的基础设施实现 profile 已裁决为从第一条可执行订单切片开始统一使用 `PostgreSQL + pgvector + tsvector`，本地开发与可复现测试通过 Docker Compose 启动数据库，不建立 SQLite 过渡实现。订单、物流、Runtime Record 与后续 Policy Corpus 共用这一关系数据库基础设施，但仍按 owner、事务和测试边界维护独立逻辑记录域；`pgvector` 在基础设施中可用不表示第一切片已经实现或使用 RAG。RAG Schema、索引与 `G-RAG-INFRA` 激活门禁以 [RAG Design Reference](docs/architecture/rag-design-reference.md) 为准，第一切片的 Compose、迁移和测试隔离目标契约以 [E2E-01 Thin Slice Implementation Spec](docs/implementation/e2e01-thin-slice-implementation-spec.md) 为准。

上述内容当前仍是 `CONTRACT_DEFINED`：在 `compose.yaml`、Alembic migration、源码与测试真实出现并通过验证前，不得描述为数据库已经启动、Schema 已迁移或 `pgvector` 已可用。

### 6.7 `DEVOPS-01`：完整应用容器化与单机部署演练（`DEFERRED`）

`DEVOPS-01` 是后续工程实践里程碑，用于通过本项目系统练习 Docker、Docker Compose、镜像交付和单机部署；它不是新的消费者业务能力，不属于当前第一最薄切片的完成条件，也不得被描述为生产就绪或已经部署。

触发条件：

- [第一最薄 E2E-01](docs/implementation/e2e01-thin-slice-implementation-spec.md) 达到 `EXECUTABLE`。
- 当前 `db` Compose Harness、Alembic migration、API 和离线 Eval 已分别具备可复现验证入口。

计划范围：

- 为 FastAPI 应用建立可发布的 Docker image，固定基础镜像和依赖版本，使用非 root 用户运行，并验证构建缓存与最小镜像内容。
- 将 Compose 从当前只启动 `db` 的 Harness 扩展为至少包含 `db`、一次性 `migrate` 和 `api`；为 test / eval 提供隔离、可丢弃的 Compose profile 或等价运行入口。
- 建立 service healthcheck、启动依赖、network、开发 volume、日志、环境变量和 secret 边界；仓库只提交无真实凭据的示例配置。
- 保持 Qwen 等 LLM Provider 为外部 Adapter，不把第三方模型服务伪装成项目自有容器。
- 在本地完整启动验证后，补充单台 VPS 或云主机的部署演练、持久数据备份 / 恢复和镜像回滚说明；多节点编排、高可用、自动扩缩容和生产 SLA 不在该里程碑范围。

最小验收：

- 新克隆可以从无业务数据的环境构建镜像，并用一条有文档记录的 Compose 命令启动健康的 `db + migrate + api`。
- migration 失败会阻止 API 被报告为就绪；重复执行不会破坏既有 Schema。
- API 容器可通过 Compose service name 访问 PostgreSQL，开发重启保留预期数据，test / eval 不复用开发业务状态。
- 最终镜像不包含真实凭据，不使用浮动 `latest`，应用进程不以 root 身份运行。
- 单机部署步骤、健康检查、日志检查、备份 / 恢复和回滚均有可复现证据。

激活 `DEVOPS-01` 时必须创建独立 implementation plan，并从当前 `db` Harness 契约出发做 cross-file impact analysis；在此之前，第一切片的 Docker 范围仍仅是本地 PostgreSQL / pgvector Harness。

## 7. 登录、身份同步和订单归属

P0 用户必须先登录自建站，再进入 Agent Chat：

```text
用户登录
  → 自建站验证 Session / JWT
  → 创建 CustomerContext
  → Application 将其绑定到 Agent Run
  → Tool Executor 服务端注入 customer_id
  → Mock Business API 根据 customer_id 隔离订单和退款资源
```

`CustomerContext` 的可信来源是自建站认证系统，不是用户消息，也不是模型推断。

订单归属的最终判断由业务 API 完成。例如 `get_order` 实际执行时同时使用 `order_id` 和服务端注入的 `customer_id`。模型不能提供或覆盖这个 customer_id。

`search_orders` 同样必须以服务端注入的 `customer_id` 为查询范围，候选摘要只能来自当前用户本人的订单。对显式订单号，业务 API 不得把“订单不存在”和“订单不属于当前用户”暴露为两种可区分的外部结果；未经归属验证的订单数据不得进入 ModelVisibleContext、Memory、标准 Observation 或普通 Trace。

这条边界适用于订单、物流、退款和历史任务等全部私有资源，而不只是 `get_order`。任何“不存在”“非本人”或“无法确认归属”的结果都必须在下一次模型调用和普通记录写入之前归一化为 `NOT_FOUND_OR_NOT_ACCESSIBLE`；后续 `RunResultMapper` 只能看到安全结果，不得看到真实差异或原始 ToolResult。

## 8. CustomerContext 与模型隐私边界

`CustomerContext → Agent Runtime` 不表示把全部用户资料交给模型。Runtime 内部必须区分：

### RuntimePrivateContext

- customer_id、认证主体和授权范围。
- Token / Session 引用。
- 原始 PII 或业务系统连接信息。
- 只供 Application、ActionPolicy、Tool Executor 和业务 API 使用。
- 不进入 Prompt、模型 Memory 或普通 Trace。

### ModelVisibleContext

- 本次目标所需的最少订单状态。
- 脱敏后的物流事实。
- 必要的政策 Evidence 和引用。
- 当前 RequestUnit 状态及 `open_questions`。

`Model Context Projector` 负责最小化、脱敏和字段白名单。Trace 同样不得保存原始 Token 或不必要的 PII。

对已确认属于当前用户的普通读取结果，模型只能接收目标所需的安全投影，并返回不含事实值的受控表达计划。内容顺序、语气和批准的表达变体可以由模型选择；订单号、商品名称、数量、日期和状态等事实由确定性 Renderer 从安全投影注入。`fact_refs` 只用于审计，不能替代这一结构性边界。`NOT_FOUND_OR_NOT_ACCESSIBLE` 等安全敏感结果不进入表达模型，直接由 `RunResultMapper` 输出固定安全文案。

## 9. 会话与 Memory 的所有权

“Session”不能作为一个笼统层，因为当前系统包含多种不同的状态与记录域：

| 状态类型 | 所有者 |
|---|---|
| 登录 / 连接 Session | Channel & Interface Adapters |
| Conversation 生命周期和消息历史 | Application Services |
| L0 Run State、RequestUnit Board、L2 Task Working Context | Agent Runtime |
| Observation 与 Evidence Records | Agent Runtime 定义语义；Infrastructure 持久化 |
| Decision & Action Ledger | Agent Runtime / ActionPolicy 定义语义；Infrastructure 持久化 |
| Trace / Context Manifest | Memory Design Reference 定义 Context Manifest；各专项 owner 定义自身 Trace 语义；Infrastructure 持久化 |
| Store、数据库和持久化实现 | Infrastructure |

Memory 语义：

- L0 Run State：当前 ReAct run 的临时状态，由 Runtime 管理。
- L1 Conversation Context：Application 选择需要的对话历史，Runtime 只消费本轮投影。
- L2 Task Working Context：跨会话保存 Task State、RequestUnit Board、目标绑定，以及 Observation、Evidence 和 Action Record 的引用。

L2 不复制权威事实、政策正文、确认或副作用结果。当前业务事实来自受控业务系统形成的 Observation；知识依据来自版本化 Evidence；确认、幂等和执行结果记录在 Decision & Action Ledger。用户陈述和模型总结不得自动升级为业务事实。

## 10. Tool、RAG 与退款动作

Read / Retrieval 工具：

```text
search_orders
get_order
get_shipment
retrieve_refund_policy
get_refund_status
```

Action 工具：

```text
create_refund
```

RAG Evidence 必须保留：

- 来源。
- 版本。
- 位置或文档片段标识。
- 检索时间和新鲜度。
- 引用。
- no-match、stale、conflict 等状态。

P0 的正常政策检索路径使用 Dense + Sparse Hybrid Retrieval、RRF 与 Cross-Encoder；Top-K 和具体模型由 Dataset / Eval 调整。检索内部边界、Evidence 状态和明确延期项见 [`docs/architecture/rag-design-reference.md`](docs/architecture/rag-design-reference.md)。

Evidence 缺失、过期或冲突时，ActionPolicy 必须阻止退款。

用户重复确认不能造成重复退款。`create_refund` 使用可信幂等键；若结果未知，使用同一个幂等身份查询退款状态，不得伪报成功或失败。

## 11. Trace 与 Agent Eval

跨组件 Eval 的通用方法、Eval-driven development、EvalCase、Dataset、Grader、指标 / Gate、报告和架构决策证据以 [`docs/evaluation/agent-evaluation-strategy.md`](docs/evaluation/agent-evaluation-strategy.md) 为准；P0 Case ID、requirement mapping、Critical failure 和激活状态以 [`docs/evaluation/p0-eval-coverage-matrix.md`](docs/evaluation/p0-eval-coverage-matrix.md) 为准。本节只保留项目方向级原则和最小 Trace 要求。

Trace 从第一版开始记录：

- `TaskDeltaCandidate`、来源与校验结果。
- `AcceptedTaskDelta` 及其前后 Task State 版本。
- RequestUnit 状态变化。
- ModelVisibleContext 摘要与 `context_manifest_id`。
- NextMove、Gate Decision、Runtime `tool_call_id`、ToolCall 终态、超时与中断。
- Context Manifest 关联的 `tool_registry_version` 和 `model_visible_toolset_hash`，用于还原模型当时实际可见的 ToolSpec。
- 已通过归属与最小披露校验的业务查询结果形成 Observation；政策检索、Action 结果、失败与安全 RunResult 分别进入 Evidence、Action Ledger、Trace 或 RunResultMapper，不把任意 ToolResult 自动写成 Observation。
- Evidence 引用、ActionPolicy 判定和停止原因。

Trace 不记录 RuntimePrivateContext、原始 Token 或不必要的 PII。

Trace 通过 `context_manifest_id` 关联工具集版本与 Hash，不要求每个事件重复复制完整 Manifest。完整工具调用 Trace 契约和专项 Eval obligations 以 [`docs/architecture/tool-calling-design-reference.md`](docs/architecture/tool-calling-design-reference.md) 为准。

P0 Eval 至少覆盖三层：

- Component：Goal 边界、Task Delta、Input Binding、Query 上下文化、Tool 选择、RAG、Memory、ActionPolicy。
- Trajectory：ReAct 路径、重复调用、预算、停止和恢复。
- E2E：业务结果、订单隔离、安全副作用和用户体验。

Component / Trajectory / E2E 是观察粒度，不是全部 Eval 类型。Product Outcome、Correctness / Grounding / Safety / Robustness / Efficiency / UX / Auditability、Deterministic / Trace / Model / Human Grader 和实现生命周期分别建模；Model、Prompt、RAG 配置和 Runtime 方案作为实验变量比较。

Eval 检查必要约束、禁止行为、权威业务状态和用户结果，不要求每次使用完全相同的合法 Tool 顺序。Eval 贯穿实现全过程：实现前定义最小 Contract，组件实现与 Component Eval 同步增长，第一条 E2E-01 纵向切片尽早验证 Harness，随后再进入包含副作用的 E2E-02。

Critical failure 不能被平均分掩盖。普通质量、延迟、成本和 RAG 阈值必须在可运行 Dataset 与 Baseline 出现后裁决；当前不得预先宣称已经达到阈值。最小安全 Case 与门禁映射不在本节维护第二套清单，统一引用 P0 Eval Coverage Matrix。

`E2E01-01/04` 第一最薄切片的具体 HTTP、Session Fixture、`get_order`、受控表达、持久化、Provider Adapter、Eval 数据与目标命令编码见 [`E2E-01 Thin Slice Implementation Spec`](docs/implementation/e2e01-thin-slice-implementation-spec.md)。该 Spec 只拥有切片实现映射，不改变本节或专项 owner 的通用语义；`E2E01-05` 延至 `get_order` 与 `get_shipment` 同时可用的 E2E-01 扩展阶段。

## 12. 当前架构与图形状态

### 12.1 当前架构基线：业务应用架构 V2

当前最新、唯一的 P0 架构基线是：

- `docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.drawio`
- `docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.svg`
- `docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.png`

该图使用“业务主线 + 关键技术模块”表达模块化单体：

```text
已登录消费者
  → 自建站业务应用与可信身份
  → Application Services
  → Agent Runtime
  → Business Capabilities
  → P0 Mock Business Systems
```

AI 与平台支撑位于主线右侧，为 Application / Runtime 提供模型、状态持久化、Trace 和 Eval，不表示业务请求必须依次经过的一层。

业务能力区只表达三个稳定业务语义：

```text
订单与物流事实
政策 Evidence 与退款判断
受控模拟退款与结果恢复
```

底部只包含四个 P0 Mock 系统：Mock Order System、Mock Shipment System、Policy Knowledge Base 和 Mock Refund System。具体工具名由 `docs/business-capabilities.md` 的 Tool Catalog 管理，不在业务应用架构图中重复维护。

图中的 `Run & Task State` 和 `State & Record Stores` 是视觉分组，不改变 `docs/architecture/memory-design-reference.md` 的语义边界：Observation、Evidence、Decision & Action Ledger 和 Trace 都是与 L2 Task Working Context 分离的记录域；L2 只保存恢复任务所需的引用与最小投影。

### 12.2 配套代码依赖视图

- `docs/architecture/consumer-after-sales-agent-code-layer-dependency-v2.drawio`
- `docs/architecture/consumer-after-sales-agent-code-layer-dependency-v2.svg`
- `docs/architecture/consumer-after-sales-agent-code-layer-dependency-v2.png`

代码依赖 V2 采用“宏观分层 + 关键边界 Ports & Adapters”：接入层依赖应用层的 Inbound Ports，应用层依赖 Agent Runtime / Core，出站 Adapter 反向依赖并实现 Application 或 Core 拥有的 Outbound Ports。Core 禁止依赖具体 Adapter、Web / DB / HTTP / LLM SDK；只有 Bootstrap / Composition Root 可以同时引用 Port 与具体实现。

该图只表达允许的源代码依赖，不拥有 Memory、Evidence、Action Ledger 或存储技术的语义。Conversation 生命周期和消息持久化使用 Application-owned Port；Run / Task State、Observation / Evidence Records、Action Ledger、Trace 与 Context Manifest 使用 Core-owned Port Groups。L2 只保存引用和状态版本。Port 可按 owner、事务和测试边界合并或拆分，不要求一种记录对应一张表或一个 Port。P0 权威状态使用关系数据库，Redis 不属于当前依赖基线；第 6.6 节已选的 PostgreSQL 实现 profile 不需要反向写入这张保持技术中立的依赖图。

### 12.3 业务流程图状态

当前业务流程源文件是：

- `docs/architecture/consumer-after-sales-agent-business-flow-v2.drawio`
- `docs/architecture/consumer-after-sales-agent-business-flow-v2-page-1-order-resolution-query.{svg,png}`
- `docs/architecture/consumer-after-sales-agent-business-flow-v2-page-2-refund-controlled-recovery.{svg,png}`

两页分别对应 E2E-01“订单定位、物流查询与配送异常判断”和 E2E-02“退款资格、受控模拟执行与结果恢复”。流程图用于解释动态路径和安全闭环，不把 Runtime 固化为确定性 Workflow。

Flow V2 已删除退出 P0 的独立公开产品知识分支，并区分 Agent 本轮结果、Task 状态和 Action Ledger 执行状态：对外等待结果为 `ASK_USER`，Task 内部状态为 `WAITING_USER`，退款动作生命周期使用 Memory Design Reference 定义的 Ledger 状态。流程图是配套说明视图，业务范围和状态契约仍服从对应语义 owner。

### 12.4 历史图

- `docs/architecture/consumer-after-sales-agent-business-flow-v1.drawio`
- `docs/architecture/consumer-after-sales-agent-business-flow-v1-page-1-overview.*`

仓库中现存的 V1 流程图只供历史比较，不再作为实现基线。当前讨论与后续实现统一以业务应用架构 V2、`docs/business-capabilities.md` 和各专项 owner 文档为准。
