# 消费者订单与配送售后 Agent｜Memory Design Reference

更新日期：2026-07-26  
状态：P0 规范性设计参考  
适用范围：消费者订单、配送异常、退款判断、受控模拟退款执行与结果恢复  
关联基线：[PROJECT_DIRECTION.md](../../PROJECT_DIRECTION.md) 第 3、5、8、9、10 节；Tool 调用机制见 [Tool Calling Design Reference](tool-calling-design-reference.md)；通用评测方法见 [Agent Evaluation Strategy](../evaluation/agent-evaluation-strategy.md)

本文细化当前项目的 Memory、Run / Task State、Observation、Evidence、Action Record 与 Trace 边界。它不把 Memory 设计成一套通用认知系统，而是为 P0 售后 Agent 定义可实现、可恢复、可审计、可评价的状态模型。

文中的“必须”“不得”表示 P0 约束；“可以”“建议”表示允许按实现情况调整。

## 1. 核心结论

当前项目不采用下面这种纵向记忆模型：

```text
短期记忆
  → 长期记忆
  → 向量记忆
```

P0 采用三层运行上下文：

1. `L0 Run State`：单次 Agent Run 的临时控制状态，不属于长期 Memory。
2. `L1 Conversation Context`：维持一次 Conversation 内的语言连续性。
3. `L2 Task Working Context`：跨 Run、跨 Conversation 恢复售后任务的核心状态。

同时保留两个与 Memory 平行、但不可被 Memory 替代的记录域：

1. `Observation & Evidence Records`：记录业务系统观察和 RAG Evidence。
2. `Decision & Action Ledger`：记录决策输入、确认、门禁、幂等、执行和恢复。

`Trace / Context Manifest` 属于平台可观测与 Eval 支撑，不属于 Memory。未来的 `Reviewed Experience` 和 `Explicit Preference` 也是独立的可选上下文源，不是 L2 的后备层。

一句话约束：

> Memory 负责帮助 Agent 继续工作，但不能负责证明事实、授予权限、确认动作或伪造审计真相。

## 2. 从 MOCA 重构中吸收的教训

MOCA 的问题不是简单的“记忆保存得不够多”，而是不同语义被放入了同一个 Memory 抽象。

| 现象 | 根因 | 当前项目的设计决策 |
|---|---|---|
| Session Memory 以 thread 为核心，但业务工作以 case 为核心 | 按时间和聊天线程分层，没有按业务作用域分层 | 核心改为 task-scoped `Task Working Context` |
| 一个 thread 难以表达多个 case，一个 case 也可能跨 thread | Conversation 和业务任务被错误地假设为一对一 | `Conversation : Task = M:N` |
| Long-term / case memory 表存在，但长期没有有效数据 | 没有明确生产者、消费者、失效规则和 Eval | 没有完整闭环的层不进入 P0 |
| AgentState 持有大量原始、标准化、摘要和动作字段 | 运行状态、上下文、业务事实、审计记录边界混乱 | L0、L1、L2、Observation/Evidence、Ledger 分开 |
| 活跃 case 状态和历史 case precedent 名称相近 | 当前工作上下文和历史经验被误认为可以互相回退 | 活跃 Task 与 Reviewed Experience 永不互相 fallback |
| 业务事实、Evidence、审批、Trace 被称为 Memory | 上下文被误认为权威来源 | 每类数据必须声明 authority 与 visibility |
| 为缓存、向量检索和长期记忆提前建设基础设施 | 先建设存储，后寻找真实需求 | P0 使用确定性查询和单一持久化权威，测量后再扩展 |

因此，本设计的第一分层轴不是“保存多久”，而是：

1. 数据属于哪个业务作用域。
2. 数据对什么事情具有权威性。
3. 数据如何产生、修正、失效和删除。
4. 数据是否允许进入模型上下文。

## 3. 四个强制分类维度

每类持久化记录都必须明确以下维度，不能只依靠表名推断语义。

### 3.1 Scope

| Scope | 含义 |
|---|---|
| `RUN` | 一次模型推理与工具循环 |
| `CONVERSATION` | 一次用户对话 |
| `TASK` | 一个可恢复的售后目标链 |
| `CUSTOMER` | 当前登录消费者；只允许私有作用域使用 |
| `GLOBAL_KNOWLEDGE` | 版本化退款政策语料 |

P0 不引入 tenant、merchant、team 等多租户作用域。

### 3.2 Authority

| Authority Class | 含义 | 例子 |
|---|---|---|
| `TRUSTED_PRIVATE` | 来自认证或服务端注入，只供 Runtime 私有组件使用 | `customer_id`、授权范围 |
| `BUSINESS_OBSERVATION` | 通过受控工具从业务系统观察到的标准化结果 | 订单状态、物流状态、退款状态 |
| `VERSIONED_EVIDENCE` | 可追溯、可引用、有适用范围的知识证据 | 退款政策片段和版本 |
| `DETERMINISTIC_DERIVATION` | 确定性代码根据已知输入计算的结果 | 退款资格判断 |
| `USER_CLAIM` | 用户陈述，只能作为待验证输入 | “包裹五天没更新” |
| `MODEL_INFERENCE` | 模型推断或摘要，只能作为候选和上下文 | 目标候选、Conversation 摘要 |
| `CONTEXTUAL_ONLY` | 只用于辅助解释或相似性参考 | 已审核历史先例 |

### 3.3 Lifecycle

| Lifecycle | 含义 |
|---|---|
| `EPHEMERAL` | Run 结束即可清理 |
| `CHECKPOINTED` | 为崩溃恢复而短期保存 |
| `CURRENT_PROJECTION` | 当前 Task 或 Conversation 的可变投影 |
| `VERSIONED_RECORD` | 不覆盖历史，以新版本或纠正记录取代旧版本 |
| `REVIEWED` | 经过人工审核后才能供后续任务使用 |

### 3.4 Visibility

| Visibility | 含义 |
|---|---|
| `RUNTIME_PRIVATE` | 不得进入 Prompt、模型 Memory 或普通 Trace |
| `MODEL_VISIBLE` | 经过最小化、脱敏和白名单投影后可进入模型 |
| `AUDIT_ONLY` | 只用于审计、回放或 Eval，不进入普通 Prompt |
| `USER_VISIBLE` | 可以通过安全回复向当前用户披露 |

私有资源未通过归属校验时，其真实 payload 不能进入上述普通记录流。实现如因安全调查确需保留，只能写入与模型、Memory、标准 Observation、Context Manifest 和普通 Trace 隔离的受限诊断域，并受独立访问与保留策略控制。

## 4. 总体结构

```mermaid
flowchart LR
    L0["L0 Run State<br/>单次运行、临时"] --> CA["Context Assembler"]
    L1["L1 Conversation Context<br/>对话连续性"] --> CA
    L2["L2 Task Working Context<br/>跨会话任务状态、核心"] --> CA
    OBS["Fresh Observations<br/>业务系统仍是当前事实源"] --> CA
    EVI["RAG Evidence<br/>版本化知识证据"] --> CA
    CA --> MVC["ModelVisibleContext"]
    MVC --> MODEL["LLM / ReAct Reasoner"]

    PRIVATE["RuntimePrivateContext<br/>身份、权限、customer_id"] --> GATE["Control Gateway / ActionPolicy / Tool Executor"]

    L2 -. "引用" .-> RECORDS["Observation & Evidence Records"]
    L2 -. "引用" .-> LEDGER["Decision & Action Ledger"]
    CA -. "记录选择结果" .-> MANIFEST["Context Manifest / Trace"]

    FUTURE["Reviewed Experience / Explicit Preference<br/>未来可选、contextual only"] -. "可选输入" .-> CA
```

这些组件不是一条逐层回退链：

- L1 找不到业务事实时，不能用 Conversation 摘要补齐。
- L2 中的旧 Observation 过期时，必须重新调用业务工具，不能用历史先例替代。
- 当前政策 Evidence 缺失时，不能用过去案例证明当前退款资格。
- Action Ledger 找不到有效确认时，不能从聊天摘要推断用户已经确认。

## 5. 什么属于 Memory，什么不属于

| 数据 | 所属域 | 是否属于 Memory | 对什么具有权威性 |
|---|---|---:|---|
| 当前 step、预算、重试和停止状态 | L0 Run State | 否，属于运行状态 | 当前 Run 的执行控制 |
| 最近消息和对话投影 | L1 Conversation Context | 是 | 用户和系统说过什么 |
| RequestUnit 与任务推进状态 | L2 Task Working Context | 是 | Task 工作流状态 |
| `customer_id`、认证主体、授权范围 | RuntimePrivateContext | 否 | 当前身份与授权 |
| 订单、物流、退款当前状态 | Business System / Observation | 否 | 外部业务系统是当前事实源 |
| 退款政策 | Policy Knowledge Base / Evidence | 否 | 指定版本与适用范围内的知识证据 |
| 待确认退款方案、确认、幂等和执行结果 | Decision & Action Ledger | 否 | 动作生命周期和审计 |
| 已通过归属边界的原始 ToolResult | Raw Observation Record / 受限诊断域 | 否 | 某次工具调用返回了什么 |
| Trace 与 Context Manifest | Trace Store | 否 | 系统当时做了什么、看到了什么 |
| 历史成功案例 | Reviewed Experience | 否 | 只提供 contextual reference |
| 用户明确要求记住的软偏好 | Explicit Preference | 独立可选域 | 只对非安全偏好有效 |

## 6. L0 Run State

### 6.1 作用域

`L0 Run State` 只属于一次 `AgentRun`，不能作为跨任务的长期记忆。

### 6.2 保存内容

```text
run_id
conversation_id
current_step
budget
attempt_count
current_next_move
in_flight_tool_call_ref?
transient_observation_refs[]
stop_reason?
checkpoint_version
started_at
updated_at
```

可以包含：

- 当前受控 ReAct 进行到哪一步。
- 步数、Token、时间和工具预算。
- 当前 `NextMove`。
- 工具超时或重试所需的临时引用。
- 当前 Run 的停止、失败和恢复状态。

不得包含：

- 可跨 Conversation 复用的任务权威状态。
- 用户身份或 Token 原文。
- 作为当前业务事实长期使用的 ToolResult 副本。
- 从模型推理中自动产生的长期偏好。

### 6.3 持久化

- 正常 Run 可以只保留必要 checkpoint。
- 发生进程崩溃、工具超时或流式响应中断时，可以从 checkpoint 恢复。
- Run 完成后，L0 可以压缩或按运行保留策略清理。
- L0 被持久化不等于它升级为长期 Memory。

## 7. L1 Conversation Context

### 7.1 目标

L1 只解决 Conversation 内的语言连续性：

- 用户说“第二个”“那个包裹”时知道他在指什么。
- Runtime 知道上一轮向用户询问了什么。
- 本轮 Request Understanding 能看到必要的最近对话。

L1 不负责业务任务恢复，也不负责证明事实。

### 7.2 建议契约

```text
ConversationContextProjection
  conversation_id
  recent_message_refs[]
  pending_question_ref?
  unresolved_mention_refs[]
  linked_task_ids[]
  optional_summary?
  summary_source_message_refs[]
  projection_version
  projected_at
  expires_at?
```

消息原文应保存在 Conversation Store。L1 是本轮选择出来的投影，不必复制完整聊天记录。

### 7.3 摘要规则

Conversation 摘要如果启用，必须：

1. 标记为 `MODEL_INFERENCE`。
2. 保留来源消息范围。
3. 可以被重新生成或完全丢弃。
4. 不得生成新的订单号、金额、状态、确认或政策结论。
5. 不得把用户陈述升级成 `BUSINESS_OBSERVATION`。
6. 不得成为退款动作确认的唯一证据。

P0 可以先使用最近消息、待回答问题和精确引用，不实现滚动摘要。只有 Context Token Eval 表明确有需要时再增加。

### 7.4 生命周期

- Conversation 关闭不等于 Task 关闭。
- Conversation 可以清理或压缩，但关联的 Task 可以继续存在。
- L1 的保留周期不能控制 Action Ledger 或 Task State 的保留周期。

## 8. L2 Task Working Context

### 8.1 Task 的定义

Task 是一个可恢复的售后业务目标链，不等于：

- 一次用户消息。
- 一次模型推理。
- 一个 Conversation。
- 一个工具调用。
- 一个单独 Intent 标签。

示例：

```text
针对订单 O-1001 调查配送异常；
如果退款政策允许，则生成退款方案；
用户确认后执行退款并恢复最终结果。
```

这可以是一个 Task，内部包含相互依赖的多个 RequestUnit：

```text
RU-1 查询关联包裹的当前状态，并解释是否异常
RU-2 若当前事实与政策判定符合条件，则在精确确认后创建模拟退款
```

订单定位、ToolCall、配送异常或退款资格的确定性判断、政策检索、动作门禁和结果恢复属于目标内部推进，不额外建立 RequestUnit。Request Understanding 的 Goal Delta 与 RequestUnit 粒度以 [Intent / Request Understanding Design Reference](intent-design-reference.md) 为准。

如果一条消息中包含彼此独立的目标，例如查询两个无关订单，则应建立两个 Task 或两个可独立推进的 Task 分支，而不是把全部状态混在同一个 Conversation Memory 中。

### 8.2 L2 是现有 Task State 的规范化视图

`Task Working Context` 不要求再创建一套与 `RequestUnit Board` 重复的领域模型。

推荐解释：

```text
Task Working Context
  = Task State
  + RequestUnit Board
  + 当前目标绑定
  + Observation / Evidence / Action 引用
  + 恢复所需的最小投影
```

具体实现可以是一个 Task 聚合、若干关系表和一个物化投影，不要求存在名为 `task_working_context` 的单表。

### 8.3 建议契约

```text
TaskWorkingContext
  task_id
  private_owner_scope
  status
  request_unit_refs[]
  target_refs[]
  open_questions[]
  observation_refs[]
  evidence_bindings[]
  pending_action_ref?
  last_outcome_ref?
  state_version
  created_at
  updated_at
```

字段说明：

- `private_owner_scope`：包含用于数据库隔离的 `customer_id`，只允许 Runtime 私有组件读取，不进入 Prompt。
- `request_unit_refs`：指向 Runtime 已校验的 RequestUnit，不保存未经校验的模型候选。
- `target_refs`：经过归属验证的订单、商品、物流或退款引用。
- `open_questions`：聚合当前各 RequestUnit 为安全推进真正缺少的信息，不是固定 Intent Slot 表。
- `observation_refs`：指向标准化 Observation；可以带最小当前投影，但不能冒充外部事实源。
- `evidence_bindings`：指向某个判断所使用的 Evidence、版本、适用范围和新鲜度。
- `pending_action_ref`：指向 Action Ledger 中尚待确认或执行的精确方案。
- `last_outcome_ref`：指向最近一次完成、失败或未知结果记录。
- `state_version`：用于并发控制、恢复和确认失效判断。

### 8.4 Task 状态

P0 可以采用以下最小状态集合；具体命名可在实现时调整：

```text
ACTIVE
WAITING_USER
PENDING_ACTION
ACTION_IN_PROGRESS
RECOVERING
COMPLETED
BLOCKED
CANCELLED
```

状态迁移必须由程序控制。模型只能提出候选 `NextMove`，不能直接把 Task 标记为完成、已确认或已退款。

### 8.5 权威边界

L2 对以下内容具有权威性：

- 当前 Task 包含哪些经过验证的 RequestUnit。
- RequestUnit 当前处于什么执行状态。
- 当前有哪些等待补充的开放问题。
- 当前绑定了哪些目标引用。
- 当前使用了哪些 Observation、Evidence 和 Action Record。
- Task 是否正在等待用户、执行、恢复或已经结束。

L2 对以下内容不具有最终权威性：

- 用户当前是否仍然有权访问某个订单。
- 订单、物流、退款的最新状态。
- 当前政策正文和适用版本。
- 用户是否确认了一个参数已经变化的退款方案。
- 副作用是否真实发生。

这些内容必须在需要时回到对应权威源复核。

## 9. Observation 与 Evidence

### 9.1 Claim、Observation、Evidence 必须分开

| 类型 | 来源 | 是否可以直接作为业务事实 |
|---|---|---:|
| User Claim | 用户消息 | 否 |
| Model Inference | Request Understanding、摘要、Reasoner | 否 |
| Tool Observation | 经过注册工具、业务 API 归属校验和标准化后的结果 | 可以作为某个时间点的已验证观察 |
| RAG Evidence | 版本化语料检索结果 | 可以证明对应知识内容，但不能证明当前订单状态 |
| Deterministic Derivation | 规则代码 | 只对明确输入和规则版本有效 |
| Reviewed Precedent | 历史案例 | 否，只能辅助参考 |

用户说“包裹五天没更新”时：

1. L1 保存这句话的消息引用。
2. Request Understanding 可以生成配送异常调查候选。
3. Runtime 调用 `get_shipment`。
4. 标准化 ToolResult 形成 `ShipmentObservation`。
5. 确定性诊断依据 Observation 判断是否停滞。

不得在第 1 或第 2 步把用户陈述直接升级为 verified fact。

### 9.2 Observation 建议字段

```text
observation_id
source_tool
source_resource_ref
source_version?
normalized_type
normalized_value
observed_at
recorded_at
valid_until?
supersedes?
raw_result_ref?
visibility
```

时间必须分开：

- `observed_at`：业务事实在什么时候被观察到。
- `recorded_at`：本系统在什么时候写入记录。
- `valid_until`：什么时候必须重新获取。

原始 ToolResult 可以保留在独立记录中用于诊断，但进入 Prompt 的只能是标准化、最小化和脱敏后的投影。

对订单、物流、退款和历史任务等私有资源，只有已确认属于当前用户的数据才能形成标准 Observation。`NOT_FOUND`、`NOT_OWNED` 或 `OWNERSHIP_UNVERIFIED` 等内部结果必须先折叠为 `NOT_FOUND_OR_NOT_ACCESSIBLE`，不创建含资源内容的 Observation，也不让 Context Manifest 或后续模型调用引用真实差异。

### 9.3 Evidence Binding 建议字段

```text
evidence_binding_id
task_id
request_unit_id
purpose
document_ref
document_version
section_ref
applicability
retrieved_at
valid_until?
conflict_status
citation
```

Evidence 必须绑定使用目的。例如同一政策片段可以用于解释，但不一定足够支持退款执行。

RAG Retriever 负责找知识；Evidence Assembler 负责版本、冲突、适用范围和引用；TaskWorkingContext 只保存绑定引用。Policy Corpus 受控 ingestion、清洗、结构解析、Chunking、Hybrid Retrieval、RRF、Cross-Encoder 和 Evidence 组装处理的内部契约见 [RAG Design Reference](rag-design-reference.md)；本文继续拥有 Evidence Binding 的权威字段、生命周期与引用语义。

## 10. Decision & Action Ledger

### 10.1 为什么不能放进 Memory

待确认动作、用户确认、退款调用和未知结果恢复具有安全与审计语义。它们不能依靠：

- Conversation 摘要。
- 模型自行回忆。
- L2 中一个布尔字段。
- “用户刚才好像同意了”的自然语言推断。

因此必须使用独立、结构化、可追加的 Ledger。

### 10.2 建议记录

```text
DecisionActionRecord
  record_id
  task_id
  request_unit_id
  run_id
  action_type
  proposal_payload
  proposal_hash
  input_observation_refs[]
  evidence_binding_refs[]
  policy_or_rule_version
  gate_decisions[]
  confirmation_message_ref?
  confirmation_hash?
  idempotency_key?
  attempt_no
  execution_status
  external_result_ref?
  observed_at
  recorded_at
```

`execution_status` 至少能表达：

```text
PROPOSED
AWAITING_CONFIRMATION
CONFIRMED
STARTED
COMPLETED
FAILED
RESULT_UNKNOWN
RECONCILED
INVALIDATED
```

### 10.3 精确确认绑定

用户确认必须绑定到同一个精确方案：

```text
proposal_hash = hash(
  action_type,
  resource_refs,
  quantity,
  amount,
  refund_method,
  user_visible_impact,
  critical_observation_versions,
  evidence_versions
)
```

以下任一项变化，原确认必须失效：

- 订单或商品。
- 数量。
- 金额。
- 退款方式。
- 用户可见影响。
- 关键 Observation。
- Evidence 或政策版本。
- 当前授权范围。

L2 只保存 `pending_action_ref`，不能复制一个脱离 Ledger 的“已确认”标志。

## 11. Conversation、Task、RequestUnit 与 Run 的关系

推荐关系：

```text
Customer      1:N Conversation
Customer      1:N Task
Conversation  M:N Task
Task          1:N RequestUnit
Task          1:N ObservationBinding
Task          1:N EvidenceBinding
Task          1:N DecisionActionRecord
Conversation  1:N AgentRun
AgentRun      M:N Task
```

### 11.1 Conversation 与 Task 必须多对多

原因：

- 一个 Conversation 可以同时讨论多个订单和多个独立目标。
- 一个 Task 可以在另一个 Conversation 中继续。
- 一次 Run 可以从一条多意图消息更新多个 Task。
- Conversation 的关闭、归档或压缩不能隐式关闭 Task。

建议关系记录：

```text
ConversationTaskLink
  conversation_id
  task_id
  link_reason
  linked_at
  last_active_at
  status
```

即使 P0 UI 一次只突出显示一个活动 Task，存储模型也不得假设 `conversation.task_id` 是唯一外键。

### 11.2 身份隔离

Task、Conversation、Observation、Action Record 的加载必须在服务端使用当前可信 `customer_id` 限定：

```text
(customer_id, task_id)
(customer_id, conversation_id)
(customer_id, order_id)
(customer_id, refund_id)
```

模型不得生成或覆盖 `customer_id`。未经当前 Run 重新授权和归属复核，历史 Task 不能直接解锁私有资源或副作用。

## 12. 写入路径

### 12.1 总原则

模型和工具都不能直接写 Memory。

```text
LLM 产生候选
  → Runtime 结构校验
  → 服务端权限与作用域校验
  → 私有资源归属结果归一化
  → 标准化事件或命令
  → 确定性 Reducer 更新 Task State
```

工具只返回标准化 ToolResult；Runtime 判断它是否形成 Observation、绑定到哪个 Task，以及哪些字段允许进入模型。

### 12.2 建议事件

```text
MessageAccepted
TaskDeltasValidated
TaskLinkedToConversation
TargetResolved
ObservationRecorded
EvidenceBound
UserCorrectionAccepted
ActionProposed
ActionConfirmationRecorded
ActionInvalidated
ActionStarted
ActionCompleted
ActionFailed
ActionResultUnknown
ActionReconciled
TaskCompleted
TaskBlocked
```

不要求实现完整 Event Sourcing。最低要求是：

- 当前 Task 状态有版本控制。
- 关键动作记录 append-only。
- 能知道某个状态由什么输入和记录产生。
- 纠正通过新记录 supersede 旧记录，不静默篡改审计历史。

### 12.3 写入可靠性

| 写入 | 可靠性要求 |
|---|---|
| Conversation 原始消息 | 必须可靠保存 |
| Task / RequestUnit 状态迁移 | 必须可靠、带版本控制 |
| Observation / Evidence 绑定 | 关键决策前必须成功 |
| 退款方案与确认 | 必须先持久化再允许执行 |
| Action Attempt / Result | 必须与幂等和恢复身份关联 |
| Conversation 摘要 | 可以异步、失败可重建 |
| Trace 扩展字段 | 可以按可观测策略降级，但不能伪造成功 |

副作用执行附近应使用事务、唯一约束、幂等键或 Outbox 等机制保证：

- 不因响应失败丢失已开始的动作记录。
- 不因进程重启重复创建退款。
- `RESULT_UNKNOWN` 可以使用原身份对账。

## 13. 读取与 Context Assembly

### 13.1 两阶段加载

为了支持指代解析、多意图和跨会话恢复，又避免把所有历史塞进 Prompt，建议采用两阶段加载。

第一阶段，用于 Request Understanding：

```text
当前用户消息
+ 最近 Conversation 投影
+ 当前 Conversation 关联的活动 Task 索引
+ 当前可信但最小化的运行约束
```

活动 Task 索引只包含：

- `task_id` 的模型安全别名。
- 用户可识别的最小目标摘要。
- 当前状态。
- 已脱敏目标标签。

第二阶段，在 `TaskDeltaCandidate` 经过校验、Reducer 写入 RequestUnit 并完成 Task 绑定后：

```text
精确加载目标 TaskWorkingContext
+ 刷新需要的新鲜 Observation
+ 检索并绑定所需 Evidence
+ 加载相关 Pending Action 引用
+ 组装本轮 ModelVisibleContext
```

不得在第一阶段对当前用户的全部历史 Task 做无界向量搜索。

### 13.2 Context 优先级

Context Assembler 推荐按以下优先级处理冲突：

1. Runtime 私有安全约束和服务端授权。
2. 当前用户消息。
3. 当前 Task 与 RequestUnit 状态。
4. 新鲜的标准化 Observation。
5. 当前适用的版本化 Evidence。
6. Pending Action 的用户可见投影。
7. 最近 Conversation 消息。
8. Conversation 摘要。
9. 已审核历史经验或明确偏好。

低优先级内容不得覆盖高优先级内容。Runtime 私有字段只影响控制和投影，不直接进入模型。

### 13.3 Context Manifest

每次模型调用应生成一个可审计的 Context Manifest：

```text
context_manifest_id
run_id
model_call_id
tool_registry_version
model_visible_toolset_hash
selected_message_refs[]
task_state_ref_and_version?
observation_refs_and_versions[]
evidence_refs_and_versions[]
action_record_refs[]
redaction_policy_version
truncation_decisions[]
token_counts
assembled_at
```

Context Manifest 记录“模型实际看到了哪些输入”，用于：

- 重放。
- Eval。
- 调试错误 Task 绑定。
- 检查过期事实。
- 分析 Token 成本。

其中：

- `tool_registry_version` 标识本次模型调用使用的完整 Runtime 工具注册配置版本。
- `model_visible_toolset_hash` 标识经过 Provider 名称与 Schema 适配后，模型实际看到的 ToolSpec 集合；它必须能解析到不可变的安全 Toolset Artifact。
- `task_state_ref_and_version` 只有在模型调用实际加载了既有目标 Task 时才存在。当前消息尚未绑定既有 Task 的首次 Request Understanding 调用可以为空；Reducer 创建 Task 后，后续 Gate、Trace 和模型调用必须引用真实的 Task state version，不得使用伪造的 `0` 版本。
- `token_counts` 对象本身必须存在；其中 `input_tokens` 与 `output_tokens` 只在对应方向由批准来源精确测量时记录。`None` 表示未知或未精确测量，整数 `0` 表示已观测到的精确零，正整数表示对应的精确计数，三者不得互相替代。
- 当前第一薄切片的 `ModelProvider` 不暴露 exact usage 来源，因此 Core 必须使用字段均为 `None` 的必填 `TokenCounts` 对象诚实表达未知。后续 Runtime / Adapter 只能写入实际精确测量的值；不得从字符数、字节数或序列化 JSON 长度估算 Token，不得为补齐 Schema 填充占位 `0`，也不得用其他 fallback 伪造使用量证据。
- Tool Calling 系统负责生成、冻结和校验工具集；Context Manifest 负责保存本次模型调用对该工具集的引用。具体 Hash、Artifact 和同快照校验规则以 [Tool Calling Design Reference](tool-calling-design-reference.md) 为准。
- Context Manifest 不保存 Handler、Provider 密钥、可信 `customer_id`、授权范围或其他 Runtime 私有注册内容。

它不得保存模型隐藏思维链，也不得成为业务事实权威源。

## 14. 新鲜度、纠正与失效

### 14.1 新鲜度

不同数据应有不同的新鲜度策略：

| 数据 | 建议策略 |
|---|---|
| 订单商品静态信息 | 源版本变化时刷新 |
| 订单状态 | 进入依赖该状态的判断或动作前刷新 |
| 物流状态 | 配送异常诊断和退款判断前按 TTL 刷新 |
| 退款状态 | 查询、恢复和重复检查前刷新 |
| 政策 Evidence | 检查版本、适用范围、有效期和冲突 |
| 用户消息 | 不过期，但后续消息可以纠正 |
| 模型摘要 | 随 Conversation 投影重建 |
| Pending Action | 任一绑定输入变化即失效 |

跨会话恢复时，默认恢复的是 Task 结构和引用，不是无条件相信旧事实。

### 14.2 用户纠正

用户说“不是第二个，是第一个订单”时：

1. 保存新的用户消息。
2. 记录一个纠正候选。
3. Runtime 重新执行目标解析和归属校验。
4. 更新 Task 目标绑定并增加 `state_version`。
5. 将依赖旧目标的派生判断、Evidence Binding 和 Pending Action 标记为失效。

用户纠正不能直接覆盖业务 API 返回的当前事实。如果用户和业务系统冲突，应保留 claim 与 observation 两条记录，并根据场景重新查询或询问。

### 14.3 并发与版本

- Task 更新应使用 optimistic locking、CAS 或等效版本检查。
- 旧 Run 不得覆盖新 Run 已更新的 Task。
- 确认必须引用对应的 `task_state_version` 和 `proposal_hash`。
- 对同一个幂等动作，只允许一个有效执行身份。

### 14.4 E2E-01 Cycle 2 candidate、freshness 与 derivation alignment

Memory owner 对 `E2E01-02/03/05/06` 增加以下通用规则：

1. **候选能力的 authority 与 durability。** CandidateSet 是绑定当前 owner、
   Task、RequestUnit、来源 Observation 和 state version 的 Runtime-private
   selection capability；它不是业务事实。任一 current-set uniqueness、record
   graph、owner scope、来源引用、版本、过期或 supersession 校验失败，都不得生成
   selection、verified target 或后续业务 ToolCall。恢复只能从同一
   owner-scoped exact closure 唯一解析，不能从模型摘要、展示文本或其他 Task 猜测
   target。
2. **birth-stale fail closed。** 业务读取即使 Schema 合法，只要在 Runtime
   acceptance 时已经 stale，就不形成新的 standard Observation。刷新失败也不得
   把旧 Observation 作为“截至之前”的替代事实投影给模型、Renderer 或新的派生
   结果。具体 5 分钟 TTL、时间字段编码与 reason code 属于 Cycle 2 scoped Spec。
3. **确定性派生绑定。** Shipment Assessment 必须引用 exact owner scope、Task /
   RequestUnit / state version、verified target、Shipment Observation 及其
   source version、适用 Claim binding、规则版本和一次可信 UTC `assessed_at`。
   新 Observation、target / Task version、Claim correction 或 rule version 变化
   时，旧派生结果不再 current；新记录通过 supersession 引用旧记录，禁止原地
   改写。replay 使用记录中的 exact 输入与可信时间，不能以当前默认值重算历史。
4. **authority metadata 只被传播，不被重建。** Memory 保存和校验业务 source
   authority 的安全 ref / version，不因此成为来源 owner；不得从用户可见字段、
   数据库 `recorded_at`、当前代码默认值或 downstream projection 反推 source
   version。业务 source authority 的语义服从
   [P0 业务能力说明](../business-capabilities.md)，具体 producer implementation、
   canonical bytes、record shape 与 restricted propagation 由 scoped Spec
   拥有。

120 小时停滞阈值、primary-result precedence 和四类 Shipment Assessment 的业务
含义由 Business owner 拥有。Memory 只拥有上述 derivation binding、currentness、
supersession 与 replay 通则；具体编码、reason code serialization、
`rule_version` 与测试向量只在
[E2E-01 Cycle 2 Implementation Spec](../implementation/e2e01-cycle2-implementation-spec.md)
正式 Activation 后由其 scoped 拥有。该 delegation 不推进 Case lifecycle，也不
表示对应记录、Port 或持久化已经实现。

### 14.5 `SUPERSEDED` Run 的 no-result closure

Memory owner 消费
[Project Direction §9.2](../../PROJECT_DIRECTION.md#92-e2e-01-cycle-2-shared-runtime-owner-alignment)
对 obsolete Run 的 Core lifecycle 裁决，并固定以下 record-closure 规则：

1. 只有同一 transactionally consistent snapshot 或等价 fence 中的 owner-scoped
   exact current Run、Task、RequestUnit 与 `RunTaskLink` closure，能够唯一证明旧
   Run 已被更新状态或绑定取代时，才允许 conditional finalizer 使用
   `SUPERSEDED + STATE_OR_BINDING_INVALIDATED`。模型、旧缓存、展示文本、网络连接
   状态或单条未经闭合验证的记录都不能作出该裁决。
2. finalization 不更新 Task / RequestUnit，不创建新 state version，也不追加旧 Run
   发起的 `TaskStateChanged`。已有
   `RunTaskLink.result_task_state_version` 保持 `null`；它不声称旧 Run 产生了
   Task result，也不能复制新 Run 已推进的 Task version。该 link 由 parent
   Run=`SUPERSEDED` 逻辑关闭，不再被 active-run / restart-recovery reader 认作可
   恢复 link。
3. Run terminal CAS、link no-result closure 与
   `RunStopped(stop_reason=STATE_OR_BINDING_INVALIDATED,
   user_outcome=BLOCKED)` 必须形成一个失败原子的持久化操作或可证明等价的原子
   边界。`BLOCKED` 只是 audit disposition；不得形成 `AgentRunResult`、ASSISTANT
   Message、`ResponseRendered`、Observation、Evidence 或用户回复。已经发生的
   Run、ToolCall、attempt 与安全 Trace evidence append-only 保留。
4. `INCOMPLETE` 继续只表示 `PROCESS_RESTART_DETECTED`，并继续使用既有
   restart-recovery closure；`CANCELLED` 不作为 obsolete Run 的别名。reason
   unknown、重复、非唯一、互相矛盾，或 current closure 无法唯一证明 obsolete
   时，必须服从
   [Core Runtime / Project Direction owner 的 canonical fence](../../PROJECT_DIRECTION.md#92-e2e-01-cycle-2-shared-runtime-owner-alignment)：
   不得猜测 `SUPERSEDED`，不得写入 / 推进 Task、RequestUnit 或产生用户结果，
   也不得据此改变 Run terminal、RunTaskLink、Task、RequestUnit、ToolCall 或
   attempt。现有执行继续被 fence，只能进入受限的 integrity failure /
   operator-resolution 路径，直到 exact closure 得到唯一修复。

该语义把 `AgentRunRecord`、`RunTaskLinkRecord` 与 `TraceEventRecord` 的目标逻辑
版本分别从 `agent_run_record.p0.v1`、`run_task_link_record.p0.v1`、
`trace_event_record.p0.v1` 提升为 `agent_run_record.p0.v2`、
`run_task_link_record.p0.v2`、`trace_event_record.p0.v2`；Trace v2 不新增 shared
字段，只扩展已批准的 terminal / stop-reason closed matrix。P0
`exact-version-only` 仍然成立：Cycle 2 Activation 前必须有显式 v1→v2 data /
physical migration、完整 record-graph validation、原子 cutover、审计证据、失败
原子性与 rollback fence；不得让 v1 / v2 同时成为 active version，不得在 request
或 recovery read 中 fallback、upgrade、downgrade 或重写。这里定义的是目标语义，
不主张 migration、codec、reader、conditional finalizer 或 Eval closure 已实现。

## 15. 存储与检索策略

### 15.1 P0 存储

P0 使用一个持久化关系数据库作为以下数据的权威存储：

- Conversation 和 Message。
- Run checkpoint。
- Task 和 RequestUnit。
- ConversationTaskLink。
- Observation / Evidence Binding。
- Decision & Action Ledger。
- Trace / Context Manifest。

Memory 领域契约不能依赖某个数据库特性。当前 P0 实现 profile 已在 [PROJECT_DIRECTION.md](../../PROJECT_DIRECTION.md) 中裁决为从第一条可执行订单切片开始统一使用 `PostgreSQL + pgvector + tsvector`，本地开发与测试通过 Docker Compose 启动，不保留 SQLite 过渡基线；该选择只约束当前基础设施实现，不改变本节的记录语义、Port 所有权、事务义务或可见性边界。具体 Compose、迁移与 RAG 激活要求分别服从 [E2E-01 Thin Slice Implementation Spec](../implementation/e2e01-thin-slice-implementation-spec.md) 和 [RAG Design Reference](rag-design-reference.md)。

### 15.2 持久化读取、解码与逻辑版本

本节消费 [PROJECT_DIRECTION.md](../../PROJECT_DIRECTION.md) 第 9.1 节的持久化四轴 ownership 与版本维度，并在 Memory owner 范围内固定 P0 的读取、完整性失败、启动恢复和 migration 行为。它是一条行为契约，不要求或定义名为 `PersistenceEnvelope`、`RecordSchemaSpec`、decoder、registry 或特定 Port 的实现 API，也不分配 Thin Slice Spec 第 10.1 节 17 项最低持久化记录的 item code 或 exact version；这些具体映射继续由后续 Thin Slice scoped owner 裁决。

#### 15.2.1 Ownership 与 exact-version 门禁

持久化不会合并四种 ownership：

- `semantic owner` 定义逻辑记录、必填字段、不变量、逻辑 `record_schema_version`、兼容与迁移语义，以及安全失败行为。
- `Python source owner` 只决定代码位置和依赖方向；记录位于某个 package 不会转移其语义 ownership。
- `Port declaration owner` 只定义调用边界、用例协调位置和事务义务；Port 的源码位置不会改写入参或返回记录的语义 owner。
- `adapter owner` 只保存和读取物理数据，并实现已经批准的 table / column / JSONB mapping、事务和 physical / data migration；Infrastructure 不得从物理形状发明逻辑字段、版本或兼容规则。

以下五个版本维度必须保持独立：

| 版本维度 | 本节约束 |
|---|---|
| `record_schema_version` | 某类持久化逻辑记录的结构与语义版本，由该记录的 `semantic owner` 批准 |
| `state_version` | Task / RequestUnit 等工作投影的 optimistic concurrency / CAS 版本 |
| `artifact_schema_version` | 可重放 Artifact 内容及 Hash 输入契约的版本 |
| `tool_registry_version` | 一次 Runtime 启动实际使用的完整工具注册配置快照版本 |
| Eval `version_manifest` | 一次 Eval 运行引用的 Dataset、Candidate、Baseline、Prompt / Model、Toolset 等单一版本快照 |

P0 采用 `exact-version-only`。对已经从存储读取、准备按预期语义类型使用的 record、row 或 envelope，必须先确认其 record identity 与非空逻辑 `record_schema_version` 精确等于 active runtime 为该 `semantic owner` 批准的唯一版本，并确认 metadata 与 payload 的 identity / version 一致；通过后才能执行完整的 owner model validation。首版不存在多版本候选选择。

以下情况统一属于内部 persistence integrity failure：

- record identity 或 `record_schema_version` 缺失、未知、不受支持、与预期不匹配，或 metadata 与 payload 声明不一致；
- 必填字段缺失、出现 owner model 禁止的额外字段、字段类型错误，或 payload 损坏；
- payload 无法完整通过对应 `semantic owner` 批准的模型与不变量校验。

发生 integrity failure 时，整个读取必须 fail closed。不得返回 partial object 或用户可见部分事实，不得按 current model “尽量解析”、强制补齐或选择 `fallback-to-latest`，也不得以 `state_version`、`artifact_schema_version`、`tool_registry_version` 或 Eval `version_manifest` 代替或推断 `record_schema_version`。

#### 15.2.2 Owner-scoped 结果、可信范围与诊断

读取必须区分两个阶段：

1. 在任何 payload 被读取前，owner-scoped 查询得到 no-row、unauthorized 或 ownership-unverified 时，继续返回同一个不可区分的安全结果；这不是 persistence integrity failure，也不得泄露记录是否存在。
2. 只有 storage row 已经按服务端可信 scope 读出后，才可能发现 identity、version 或完整 payload 的 integrity failure。此时完整读取 fail closed，不能把失败伪装成安全 `None`；内部必须保留稳定且受限的 integrity-failure category 与不含 PII 的 correlation reference，对外响应、普通 Trace 和模型上下文仍不得暴露资源存在与否。

本节只规定行为差异，不规定 return type、exception、decoder 或 registry API。对外最小披露与内部错误可诊断性必须同时成立。

Persisted `owner_customer_id`、关联 ID、metadata 或 payload 不能创建、覆盖或扩大 `CustomerContext`、`TrustedOwnerScope` 或内部 recovery authority。用户请求路径的可信范围只能由服务端认证上下文派生；启动恢复的内部 authority 也只能用于发现与条件 claim，不能使无效记录变得可信。

Owner-scoped query 的物理过滤只是 pre-payload 安全边界，不是最终归属证明。Strict decode 后，任何携带 `owner_customer_id` 或等价 owner projection 的记录都必须与本次服务端 `TrustedOwnerScope` 精确一致。物理查询 scope 与 decoded owner 不一致属于 persistence integrity failure；不得将其降级为 absent / unauthorized，不得把记录重新绑定到当前 scope，也不得用 persisted owner 字段反向授权。

对于按其 `semantic owner` 契约不携带 owner 字段的关联记录，必须通过同一个受控 record graph 中 owner-bearing root 的精确匹配证明归属，并严格解码、验证从 root 到该记录的全部关联边。孤立、归属不明、跨 owner 或无法形成闭合归属证明的记录属于 integrity failure；调用方提供的 ID、单条 payload 内的关联声明或物理外键本身都不能替代该证明。

任何 integrity failure 都不得形成 Observation、Evidence、Context Manifest、模型输入、用户可见部分事实或权威状态迁移。受限内部诊断可以保留稳定失败类别、approved record kind、expected / observed version category 和不含 PII 的 correlation reference，但不得记录 raw payload、原始 Token、完整 `CustomerContext`、Cookie、secret 或不必要 PII。

#### 15.2.3 Startup recovery 与 readiness

Recovery discovery 继续使用独立内部 authority，但 active Run 及其恢复所需必备关联记录的 strict decode 与 conditional claim 必须位于一个 transactionally consistent snapshot 中，或使用能证明等价效果的 fencing / version-CAS。等价机制必须确保 claim 仍以本次完成严格解码的同一组记录投影为条件；不得以无锁预扫描或 stale decode 结果授权后续 claim。缺少该一致性保证时，recovery / startup readiness 必须失败。

Recovery strict decode 必须在同一 transactionally consistent snapshot 或等价 fence 内验证完整关联闭包，而不是只验证每条 payload 可以独立构造模型。该闭包至少覆盖关联 Conversation、active Run、该 Run 的 `RunTaskLink`、linked Task、RequestUnit，以及本次 recovery 决策所需的 ToolCall，并必须同时证明：

- 所有 owner-bearing root 的 decoded owner 一致，且内部 recovery authority 没有被 persisted owner projection 扩大；
- `Run.conversation_id`、`RunTaskLink.run_id / task_id`、`RequestUnit.task_id`，以及所需 ToolCall 的 `run_id / task_id / request_unit_id` 都指向同一条受控关联链；
- link 方向、对应关系、`semantic owner` 批准的 required cardinality 与 closed set 均成立，任何会影响恢复状态迁移或副作用判断的关联记录都没有被遗漏或留在未经验证的闭包外。

跨 owner、跨 Run、跨 Task、跨 Conversation 的引用，关联缺失、多余或冲突，以及 required cardinality / closed-set violation 都属于 persistence integrity failure。即使闭包中的每条 payload 分别通过 owner model validation，也不能据此 claim。具体 record identity、exact version 和 cardinality 编码仍由对应 `semantic owner` 与 Thin Slice scoped owner 定义，本文不分配实现 API。

只有同时满足以下条件，才允许 conditional claim：

1. active Run 及其恢复所需的全部必备关联记录都通过预期 record identity、exact `record_schema_version` 和完整 payload validation；
2. owner 一致性、完整关联闭包、跨记录引用、required cardinality 与 closed set 全部通过验证；
3. strict decode、record graph validation 与 claim 之间的 transactionally consistent snapshot 或等价 fencing / version-CAS 门禁成立，且 claim 条件覆盖本次已验证闭包，闭包任一相关变化都会使 claim 失效。

在所需恢复投影全部严格解码并通过上述门禁之前，不得执行依赖状态迁移或副作用。遇到无法安全解码的 active recovery candidate、必备关联记录或任何 record graph validation failure 时，恢复流程必须：

- 不 claim，不写 Task、Run 或 ToolCall 状态；
- 不调用模型、Tool 或 Renderer，也不 dispatch 任何副作用；
- 不伪造 `INCOMPLETE`、`INTERRUPTED`、attempt、Observation 或 Action result；
- 不跳过该记录、不把它当作已恢复，也不通过自动重复执行掩盖问题；
- 只记录有界、受限的 integrity condition，并让 recovery / startup readiness 保持失败，直到显式修复、`semantic owner` 批准的 migration 或 operator resolution 完成。

CAS conflict / not-applicable 与 integrity failure 必须分开。前者表示自一致性快照之后状态已被合法推进或条件不再适用，应从新的受控状态重新判定；后者表示记录根本不能被安全解释。两者都不得触发无条件覆盖，CAS conflict 也不能把 integrity failure 降级为普通竞争。

本节只规定恢复的语义原子性和 readiness，不定义具体 decoder、registry、transaction 或 Port API。ToolCall 生命周期、durable dispatch fence，以及 Action `RESULT_UNKNOWN` 的权威恢复语义继续服从 [Tool Calling Design Reference](tool-calling-design-reference.md)；本文不得借完整性恢复改写 Tool / Action 状态机。

#### 15.2.4 P0 migration runtime 边界

P0 只接受 active runtime 已批准的 exact current version，不提供：

- multi-version runtime compatibility 或 payload migration graph；
- read-time upgrade、downgrade、rewrite 或 delete；
- 自动 quarantine service；
- 普通 request / recovery read 顺便执行的 migration。

Future logical version 必须先由对应 `semantic owner` 明确定义 source / target version、转换不变量、安全影响、审计证据、失败原子性和 rollback。若 migration 涉及 `TraceEvent` / `TraceEventRecord` shared structure 或 specialized payload，还必须遵守 `PROJECT_DIRECTION.md` 第 9.1 节的 Core Runtime / Project Direction owner 与对应 specialized owner 联合批准关系。

只有上述语义规则批准后，Infrastructure 才能通过显式、可审计且可 rollback 的 physical / data migration 实施。Migration 成功并通过批准的验证之前，新 runtime 不得报告 ready；失败不得留下部分转换后可被普通读取消费的状态。普通 request 和 recovery read 永远不得静默迁移、重写、删除或隔离未知 persisted data。

ToolCall、Action `RESULT_UNKNOWN` 与 Eval record 的专项字段、状态和 payload 继续服从各自 canonical owner；Memory 本节不改变 Tool / Eval owner、Eval Case 生命周期或 Thin Slice scoped mapping。以上均为目标行为契约，不主张 codec、Adapter、业务表、migration 或 startup recovery 已落地。

### 15.3 Redis

P0 不使用 Redis 作为任何 Memory、Task、确认或动作结果的权威源。

未来只有在测量证明有必要时，Redis 才可以用于：

- 缓存。
- 分布式锁。
- 限流。
- 短期流式连接状态。

缓存丢失不得改变任务真相或导致动作重复。

### 15.4 向量检索

P0 不需要向量数据库管理活动 Task。

| 目标 | 检索方式 |
|---|---|
| 当前 Conversation | 精确 `conversation_id` |
| 活动 Task | `(customer_id, task_id)`、状态和关联表 |
| 订单、物流、退款目标 | 经过授权的业务引用和确定性查询 |
| Pending Action | `task_id + proposal_hash` |
| 退款政策 | RAG Retriever |
| 未来 Reviewed Experience | 先 metadata filter，Eval 证明需要后再增加向量召回 |

活动任务不能仅通过语义相似度自动绑定。多个候选时必须询问用户。

## 16. 模块所有权

| 模块 | Memory 相关职责 |
|---|---|
| `ConversationService` | Conversation 生命周期、消息保存、L1 选择 |
| `AgentRunCoordinator` | 绑定 CustomerContext，加载 Run / Task，协调事务 |
| `Request Understanding` | 只产生 Query 上下文化与 `TaskDeltaCandidate`，不直接写状态 |
| `TaskDelta Validator / RequestUnit Board / Task Reducer` | 校验候选、写入薄 RequestUnit、推进 Task、维护版本 |
| `Model Context Projector / Context Assembler` | 最小化、脱敏、排序和组装模型上下文 |
| `Tool Registry & Executor` | 冻结模型可见工具集，执行已通过 Gate 的注册工具，服务端注入可信参数；调用生命周期以 Tool Calling Design Reference 为准 |
| `Observation Normalizer` | 把 ToolResult 转为标准化 Observation |
| `Evidence Assembler` | 维护 Evidence 版本、适用范围、冲突和引用 |
| `Control Gateway` | 校验 NextMove、预算、重复调用和停止条件 |
| `ActionPolicy` | 基于当前权威输入检查确认、权限、Evidence 和幂等 |
| `Infrastructure Stores` | 持久化实现，不定义领域语义 |
| `Trace / Eval` | 记录 Context Manifest、结果和评价数据 |

不建议建立一个包含所有读写逻辑的 `MemoryService` 或 `memory/` 巨型模块。模块名称应反映真实语义，例如：

```text
conversation
task_state
context_projection
observations
evidence
action_ledger
trace
```

## 17. P0 必须实现与明确延后

### 17.1 P0 必须实现

- L0 Run checkpoint 与失败恢复。
- L1 最近消息选择和 Conversation 投影。
- L2 Task / RequestUnit 的持久化状态。
- Conversation 与 Task 多对多关联。
- Claim、Observation、Evidence 分离。
- Observation 的来源、时间和新鲜度。
- Evidence Binding 的版本、适用范围和引用。
- Pending Action 的精确方案与确认绑定。
- Action Ledger、幂等和 `RESULT_UNKNOWN` 恢复。
- 包含工具注册版本与模型可见 Toolset Hash 的 Context Manifest。
- CustomerContext 私有边界与跨用户隔离。
- 私有资源归属失败在 Observation、Memory、Context Manifest 和普通 Trace 之前统一安全归一化。
- Task 版本控制、纠正和确认失效。

### 17.2 P0 明确不实现

- 通用长期记忆。
- 自动用户画像。
- 自动提炼用户偏好。
- 模型自由读写的 Memory Tool。
- 活动 Task 的向量检索。
- 未审核的跨任务经验自动复用。
- “从所有历史中自主寻找经验”的 Agent。
- Redis 权威状态。
- 独立 Memory 微服务。
- 完整 Event Sourcing 平台。

### 17.3 未来可选

#### Reviewed Experience

只有 Task 结束后才可以生成候选：

```text
Closed Task
  → Experience Candidate
  → Human Review
  → Searchable Reviewed Experience
```

要求：

- 默认只读。
- `CONTEXTUAL_ONLY`。
- 先使用 metadata 检索。
- 不证明当前事实、政策、授权或确认。
- 不作为 L2 找不到状态时的 fallback。

#### Explicit Preference

只允许保存用户明确表达并允许修改、查看、删除的软偏好，例如回复语言或解释详细程度。

不得保存或推断：

- 安全规则例外。
- 自动退款授权。
- 身份与权限。
- 未经用户确认的敏感画像。
- 从普通售后聊天自动总结的长期性格或消费能力判断。

## 18. Eval 与验收

Memory 设计必须通过行为 Eval，而不是以“数据库有几张表”作为完成标准。

本节拥有 Memory、Task State、Observation / Evidence 引用、Action Ledger 和 Context Manifest 的专项行为 obligations；通用 EvalCase、Dataset 生命周期、Grader、Critical failure、Gate 与跨组件覆盖服从 [Agent Evaluation Strategy](../evaluation/agent-evaluation-strategy.md) 和 [P0 Eval Coverage Matrix](../evaluation/p0-eval-coverage-matrix.md)。场景只有在可复现 Harness 中运行后才能从 `CONTRACT_DEFINED` 进入 `EXECUTABLE`。

| Eval 场景 | 预期结果 |
|---|---|
| 同一 Conversation 中说“第二个订单” | 只使用当前用户候选，正确解析或 `ASK_USER` |
| 同一 Conversation 同时讨论两个无关订单 | 建立并隔离两个 Task，不串联 Observation 和结果 |
| 在新 Conversation 继续旧退款 | 在当前身份范围内精确恢复 Task；多候选时询问 |
| 用户纠正订单目标 | 新版本覆盖工作投影，依赖旧目标的确认失效 |
| 旧物流状态已经过期 | 执行判断或动作前重新查询 |
| 政策版本变化 | 旧 Evidence Binding 和退款方案重新评估 |
| 用户曾说“可以退款” | 不把用户陈述当政策 Evidence 或动作确认 |
| 未授权订单号出现在消息中 | 消息引用可以保留用户原话，但任何真实资源内容不进入 ModelVisibleContext、Memory、标准 Observation 或普通 Trace |
| 订单、物流、退款或历史任务不存在、非本人或无法确认归属 | 统一安全 outcome；不持久化含资源内容的普通 Observation，不让后续模型看到真实差异 |
| `create_refund` 返回 `RESULT_UNKNOWN` | 使用原幂等身份查询恢复，不重复创建 |
| 使用历史 Context Manifest 重放模型调用 | 能通过 `model_visible_toolset_hash` 解析当时完整的 Provider-visible ToolSpec，且不暴露 Runtime 私有注册信息 |
| Conversation 摘要丢失 | Task 正确性和动作安全不受影响 |
| 历史先例与当前政策冲突 | 当前政策优先，先例只能作为背景 |
| 两个 Run 并发更新同一 Task | 旧版本写入失败，不覆盖新状态 |

建议持续跟踪：

```text
wrong_task_binding_rate
cross_customer_leakage_rate
stale_observation_action_rate
claim_promoted_to_fact_rate
confirmation_invalidation_accuracy
task_recovery_success_rate
result_unknown_reconciliation_rate
context_token_count
context_relevance_precision
ledger_completeness
```

其中以下指标 P0 目标必须为零：

- 跨用户数据泄露。
- 使用失效确认执行退款。
- `RESULT_UNKNOWN` 后重复创建退款。
- 用户或模型陈述被静默升级为业务事实。

## 19. 新 Memory 能力的准入检查

以后增加任何所谓“Memory 层”之前，必须回答：

1. 谁产生它？
2. 谁读取它？
3. 它帮助完成哪个用户目标？
4. 它对什么具有权威性？
5. 它什么时候失效？
6. 用户或系统如何纠正和删除它？
7. 它是否允许进入模型？
8. 没有它时系统会出现什么可测量的问题？
9. 用什么 Eval 证明它比现有确定性检索更好？

任何一个问题没有明确答案，都不应进入 P0。

## 20. 与旧架构术语的映射

`PROJECT_DIRECTION.md` 已在 2026-07-25 同步采用本节规范术语。以下映射用于解释仍可能出现在历史文档或待修订图形中的旧表达：

| 旧术语 | 本文规范术语 |
|---|---|
| `L0 Run State` | 保留，但明确它是运行状态，不是长期 Memory |
| `L1 Conversation Context` | 保留，强调它只是本轮 Conversation 投影 |
| `L2 Task Memory` | 改称 `L2 Task Working Context` 或 `Durable Task State` |
| 可信事实 | 改为带来源、版本和时间的 `ObservationRef` |
| Evidence | 保存在 Evidence 域，L2 只保存 `EvidenceBinding` |
| 待确认动作 | 保存在 Action Ledger，L2 只保存 `pending_action_ref` |
| 执行结果 | 保存在业务系统与 Action Ledger，L2 只保存结果引用和任务投影 |
| Trace | 独立的可观测与 Eval 记录，不参与事实 fallback |

“由 Runtime 管理”只说明业务责任属于 Agent Runtime，不意味着这些数据必须放在同一个对象、同一张表或同一个 Memory 模块中。

## 21. 最终设计原则

1. Scope-first：先确定 Run、Conversation、Task、Customer 或 Knowledge 作用域。
2. Authority-first：先确定谁能证明什么，再决定是否保存到上下文。
3. Task-centered：跨会话恢复围绕 Task，而不是围绕聊天摘要。
4. Reference-over-copy：L2 优先保存 Observation、Evidence 和 Action 引用，而不是复制权威内容。
5. Deterministic writes：LLM 产生候选，程序校验和更新状态。
6. Fresh-before-action：动作前重新检查授权、事实、Evidence、确认和幂等。
7. No implicit promotion：用户陈述、模型摘要和历史经验不得自动升级为事实。
8. No fallback across authorities：Conversation、Task、Evidence、Ledger 和 Experience 不互相冒充。
9. Minimal model context：只向模型投影当前目标所需的最小数据。
10. Eval before expansion：没有可测量价值的长期记忆、向量检索和缓存不建设。
