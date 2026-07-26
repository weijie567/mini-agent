# 第一最薄 E2E-01｜Codex 多 Agent 实施计划

更新日期：2026-07-27｜状态：`ACTIVE / EXECUTION_PLAN`｜适用范围：`E2E01-01`、`E2E01-04`｜性质：`NON_NORMATIVE` 执行消费者

> 本文只拥有第一最薄 E2E-01 的任务拆分、文件 ownership、依赖、集成顺序和交接格式。它不拥有产品、架构、HTTP、Schema、Fixture 语义、Eval 期望或 Case 生命周期。任务描述本身不证明实现完成；第 12 节只能用精确 commit、源码、命令输出和 PR 审查证据更新实时状态。

本文中的“多 Agent”只指 Codex 辅助开发协作，不是 P0 产品能力、Runtime 架构或面向用户的多 Agent 平台。

## 1. 权威边界

实施必须服从：

- [P0 业务能力说明](../business-capabilities.md)；
- [PROJECT_DIRECTION.md](../../PROJECT_DIRECTION.md)；
- [Intent / Request Understanding Design Reference](../architecture/intent-design-reference.md)；
- [Tool Calling Design Reference](../architecture/tool-calling-design-reference.md)；
- [Memory Design Reference](../architecture/memory-design-reference.md)；
- [Agent Evaluation Strategy](../evaluation/agent-evaluation-strategy.md)；
- [P0 Eval Coverage Matrix](../evaluation/p0-eval-coverage-matrix.md)；
- [E2E-01 Thin Slice Implementation Spec](e2e01-thin-slice-implementation-spec.md)。

本文把 Implementation Spec 第 3.1 节的目录示意和第 15 节依赖约束转成可执行工作包。若实施暴露契约问题，先记录问题与影响范围，由对应 canonical owner 裁决后再修改实现；不得让某个 Agent 在自己的分支中静默改变契约。

## 2. 交付目标

本计划完成时，仓库应满足 Implementation Spec 第 16 节 Definition of Done。核心交付链是：

```text
可信 Session
→ Request Understanding / InputBinding
→ 受控 get_order
→ 安全 Observation 或安全归一化结果
→ 确定性 Renderer
→ HTTP 响应
→ Trace
→ 结构化 Eval Result
```

第一轮只覆盖 `E2E01-01/04`。不得提前注册 `get_shipment`，不得把 `create_refund`、RAG、前端或生产集成带入本计划。

## 3. 协作拓扑

```text
Tech Lead / Integrator
├── Runtime Engineer
├── Infra Engineer
├── Eval Engineer
└── Reviewer（只读，在集成门禁执行）
```

- `Tech Lead / Integrator`：管理需求、base SHA、公共接口、合并、Composition Root、最终验证与状态更新。
- `Runtime Engineer`：实现 Core-owned contract 与 Application 行为。
- `Infra Engineer`：实现工具链、PostgreSQL、migration、API / Session、业务与持久化 Adapter。
- `Eval Engineer`：实现合成 Fixture、Case Dataset、Scripted / Qwen Provider Adapter、Harness 与 Grader。
- `Reviewer`：只读检查安全边界、契约漂移、回归和缺失测试，不直接修复。

真正的并行写入必须使用不同 Codex Worktree 和不同 Git branch。单个 Codex 任务内的子 Agent 默认只用于只读探索、审查和测试分析；任何写入 Agent 都不得与其他 Agent 共享 checkout，不具备独立 Worktree 时只能串行写入。

## 4. GitHub PR、Git 与 Worktree 模型

### 4.1 长期分支

| 分支 | 用途 | 写入者 |
|---|---|---|
| `main` | 已接受、已验证的项目基线 | Integrator |
| `integration/e2e01-thin` | 第一切片串行集成 | Integrator |
| `feat/e2e01-runtime-*` | Runtime 工作包 | Runtime Engineer |
| `feat/e2e01-infra-*` | Infrastructure 工作包 | Infra Engineer |
| `feat/e2e01-eval-*` | Eval 工作包 | Eval Engineer |

每个任务包必须记录创建 Worktree 时的 `base_sha`。一个 branch 不能同时被两个 Worktree checkout；一个 Worktree 只承担一个写入 ownership。

### 4.2 集成规则

1. Agent 在自己的 feature branch 内完成 focused verification 和 allowlist 检查。
2. Agent 提交一个可审查的原子 commit，并按第 10 节格式交接。
3. Agent 只 push 自己的 feature branch，并创建 draft PR 到 `integration/e2e01-thin`；不得直接 push integration branch。
4. Reviewer 依据 canonical owner、Task Packet、PR 模板和实际 diff 做只读 review；Review evidence 必须记录 reviewer、被审精确 head SHA、`PASS` / `FAIL`、findings 与 resolution，原 owner 修复发现。
5. Integrator 只在当前 head SHA 的独立 review 为 `PASS`、所有 findings 已关闭或显式裁决且 GitHub conversations 已解决后合并；一次只合并一个 PR。默认对 feature PR 使用 squash merge，并保留 PR 作为审查与交接证据。
6. 下一个待集成分支基于最新 integration head 解决接口差异并重新验证。
7. 完整集成门禁通过后，由 `integration/e2e01-thin` 创建 PR 到 `main`；禁止直接 push `main`。
8. 不复制 `.env`、Cookie、API Key 或其他本机 secret 到 Worktree；真实 Qwen lane 始终是显式、非发布门禁的运行。

禁止多个 Agent 同时直接写 `main`，也禁止以“最后一次覆盖”为冲突处理方式。

### 4.3 GitHub repository gate

开始首个远端 Worktree 任务前必须确认：

- `origin` 精确指向用户确认的 GitHub repository；
- `gh auth status` 对目标 host 和 owner 有效；
- head / base branch 与 Task Packet 一致；
- feature branch 可 push，PR 模板可加载；
- `main` 和 `integration/e2e01-thin` 的目标保护规则禁止直接 push 与 force push，并要求解决 PR conversations。

如果目标是新建空 repository，Integrator 可以一次性 push 当前已确认的 `main` 与 `integration/e2e01-thin` commit 来建立 PR base；必须在 Task / bootstrap 记录中保存精确 SHA，并在基线发布后立即配置目标 repository 实际支持的保护规则。任何后续功能或文档变更都不得借用该例外。

Required status checks 只有在仓库出现真实、可运行的 CI workflow 后才启用；当前不得用尚不存在的 lint、test 或 build 命令创建虚假门禁。只有一个 GitHub 用户时，也不预设会导致自有 PR 无法合并的 required approval 数量；先以 Codex 只读 review、PR 证据和用户合并决策模拟 review，真实协作者加入后再提高审批规则。

如果目标 GitHub 套餐不支持 private repository 的 branch protection，不得静默改为 public，也不得声称 base branch 已受平台保护；必须记录 API 结果和 `OPEN` 风险。在升级套餐或用户裁决可见性之前，项目级禁止 direct push / force push 规则、draft PR、可复现验证和用户 merge 决策只能作为流程门禁，不能描述成 GitHub 已强制执行。

## 5. Single-writer ownership

### 5.1 Integrator 热点

- `src/mini_agent/__init__.py`
- `src/mini_agent/main.py`
- `src/mini_agent/bootstrap.py`
- `AGENTS.md`
- active Product / Architecture / Spec / Validation 文档
- 本实施计划

只有 Composition Root 可以同时引用 Port 与具体 Adapter。其他 Agent 如需改动这些文件，只提交 dependency request，不直接修改。

### 5.2 Runtime Engineer

```text
src/mini_agent/core/**
src/mini_agent/application/**
tests/component/core/**
tests/component/application/**
```

负责：

- `ModelPort` 与 Core-owned DTO；
- Request Understanding validation、Task Reducer、`RequestUnit` 和 `InputBinding`；
- `ToolRegistry`、`ToolExecutor`、Control Gateway 与安全状态迁移；
- Observation / Trace 的 Core 语义；
- `PresentationPlan` Gate、deterministic Renderer 与 `RunResultMapper`。

不得依赖 SQLAlchemy、数据库 Client、FastAPI 或具体 Provider SDK。

### 5.3 Infra Engineer

```text
pyproject.toml
uv.lock
compose.yaml
.env.example
alembic.ini
alembic/**
src/mini_agent/api/**
src/mini_agent/infrastructure/auth/**
src/mini_agent/infrastructure/order/**
src/mini_agent/infrastructure/persistence/**
tests/conftest.py
tests/integration/**
```

负责：

- 固定依赖与本地运行剖面；
- PostgreSQL / pgvector healthcheck、Alembic 和测试 namespace 隔离；
- 可信 Session Adapter 与 HTTP Schema；
- scoped `get_order` Adapter；
- Repository、Trace / Artifact Store 和进程重启恢复。

`pyproject.toml`、`uv.lock`、Alembic revision graph、SQLAlchemy metadata 和 `tests/conftest.py` 在整个 wave 内都由该角色单写。

### 5.4 Eval Engineer

```text
src/mini_agent/infrastructure/model/**
src/mini_agent/evaluation/**
evals/**
tests/component/model/**
tests/component/evaluation/**
tests/e2e/**
tests/baseline/**
```

负责：

- `ScriptedModelProvider` 与 `QwenResponsesAdapter`；
- Fixture、Case Dataset 与 scripted scenario catalog；
- Harness、Grader、`EvalResultRecord` reader / assertion；
- provider / gateway / presentation 故障注入；
- `offline_gate` 与 `qwen_baseline` lane。

`evals/cases/**`、`evals/fixtures/**` 与版本 manifest 在整个 wave 内由该角色单写。

### 5.5 共享接口变更

Core DTO、Port、Trace event schema、ToolSpec canonical serialization / hash 是 Runtime 单写热点。其他角色需要变更时：

1. 提交最小 dependency request；
2. 说明调用方、字段、失败行为和测试；
3. Runtime Engineer 更新 contract 与 Component test；
4. Integrator 合并后，依赖方再适配。

不得复制一套相似 Schema 到 Infrastructure 或 Eval 来绕过依赖。

## 6. 数据模拟 Gate

开发前需要准备数据模拟，但只冻结能够驱动首切片的最小集合，不一次性模拟完整生产环境。

### 6.1 先冻结

- Implementation Spec 第 12 节定义的 Alice / Bob Session、`O-1001`、`O-2001` 和 `O-9999`；
- `e2e01-thin-fixture-v1` 及其 dataset、prompt、tool registry、renderer、redaction 版本；
- `E2E01-01`、`E2E01-04-A/B` 和已定义的安全 / 协议故障变体；
- 同一个 Fixture 驱动数据库 seed、HTTP E2E 和两条 Eval lane。

### 6.2 ownership

- Eval Engineer 拥有 `evals/fixtures/e2e01-thin-slice.v1.json` 这一可执行 Fixture。
- Infra Engineer 只实现读取该 Fixture 并写入隔离 PostgreSQL namespace 的 loader，不维护第二套 seed 常量。
- Runtime Engineer 只拥有解析后的 Port / DTO 约束，不把 Fixture 值写入业务代码。
- Fixture 语义仍由 Implementation Spec 拥有；修改值或版本必须经过 Integrator 的 cross-file impact scan。

### 6.3 暂不准备

- 大规模随机订单、真实客户数据或脱敏生产副本；
- 物流、退款、Policy Corpus 和 Embedding；
- 压测规模数据；
- 用模型临时生成且不可复现的测试数据。

实际失败进入回归集时再增量扩展 Fixture 和 Case，不预先冻结全部普通指标。

## 7. 实施 Wave

### W0：协作与公共边界（串行）

Owner：Integrator。

- 建立 Git baseline、项目 `.codex` 配置与自定义角色。
- 建立 `integration/e2e01-thin`。
- 为每个 Worktree 发出带 `base_sha` 和文件 allowlist 的 Task Packet。
- 确认公共 import surface、Fixture / Dataset 版本和 shared contract 变更流程。

Gate：无未提交改动；配置可被当前 Codex CLI 严格解析；每个任务 ownership 无重叠。

### W1：基础骨架（并行）

`W1-INFRA`：

- 建立 `pyproject.toml`、`uv.lock`、Compose、Alembic 与测试 namespace。
- 证明固定镜像 healthcheck 和空库 migration 路径。

`W1-RUNTIME`：

- 建立纯 Python Core DTO / Port / record semantics 骨架。
- 建立 identity、binding、state、tool、observation、trace 的 Component contract test。

`W1-EVAL`：

- 落盘 Fixture v1、Case v1、lane manifest 和 Scripted scenario catalog。
- 建立 artifact Schema / version consistency checks，并用最小 Core `NextMove` compatibility check 证明非法可信字段在真实 Pydantic 边界 fail-early；不得依赖 Application 或具体 Adapter。

集成顺序：`W1-INFRA` → `W1-RUNTIME` → `W1-EVAL`。每次集成后，下一个分支基于最新 integration head 重新验证。

### W2.0：共享契约冻结（串行）

W2 不得直接从 W1 并行起跑。先执行一个独立的 `W2-CONTRACT-FREEZE` Task Packet，由 Runtime Engineer 单写 Core / Application shared contract，Integrator 负责 active owner 裁决、精确 base、review 和合并；此时不启动任何 W2 写入 Agent。

必须冻结：

1. 补齐第 10 节最低持久化集合中跨 Runtime / Infra / Eval 共用的 `ConversationRecord`、`MessageRecord`、`ConversationTaskLinkRecord`、`RunTaskLinkRecord`、`EvalResultRecord` 与 `EvalExecutionFailureRecord` DTO 或稳定投影边界。
2. 补齐 `RuntimeRecordPort` 的可靠写入、按可信 owner 限定的读取，以及进程重启恢复所需的 Run / ToolCall / Task / RequestUnit 查询与状态更新边界；不得让 Infrastructure 自行发明第二套 DTO。
3. 固定 trusted-field fault 的阶段映射：正常 Provider / Scripted raw candidate 在 Pydantic 阶段以 `INPUT_INVALID` fail-early；Gateway 的 `GATE_REJECTED` 只作为非正常 Adapter 绕过 canonical DTO 时的 defense-in-depth。
4. 固定共享测试 bootstrap：`tests/conftest.py` 继续由 Infra 单写；Eval 只消费 `eval_postgres_namespace` / `postgres_namespace_factory`，新增 fixture 需求必须提交 dependency request。
5. 固定 W3 Composition Root ownership：`src/mini_agent/__init__.py`、`src/mini_agent/main.py`、`src/mini_agent/bootstrap.py` 只由 Integrator 在 W3 串行创建或修改，W2 三个 workstream 都将其列为 forbidden files。

Contract freeze 不得把 pre-review 暴露的冲突留给某个下游 Workstream 猜测。冻结实现必须引用并验证以下 active owner 裁决：

- Tool owner 只在 durable dispatch fence 保证外部调用前已原子持久化 `RUNNING + started ToolAttempt`（此时 `outcome=null`；Action 还包括 `STARTED + idempotency`）后，允许 `CREATED → INTERRUPTED`；该路径保留 `attempt_count=0` 且不伪造 attempt，`RUNNING` 中断保留既有两阶段 attempt，Action 的不确定结果继续服从 Action Ledger。
- Eval owner 以嵌套 `version_manifest` 作为结果唯一版本快照，并按 `PASS / FAIL` 与 `SKIPPED / NOT_RUN` 固定 Outcome、Trace、Grader、Critical failure、latency / usage 的可空规则；早于合法 Case 结果的 Harness / Trace / Grader 故障写入独立 `EvalExecutionFailureRecord`。
- Application use case 接收可信 `CustomerContext`，Persistence Port 只接收由其派生、不可选且仅含 `customer_id` 的 Runtime-private `TrustedOwnerScope`；启动恢复必须使用独立内部 authority / claim，并覆盖活动 `CREATED/RUNNING` Run。
- Task / RequestUnit 更新、Run 恢复 claim 和 `RunTaskLinkRecord` finalize 必须使用版本条件或等效 CAS，不得伪造 `0` 版本或无条件覆盖。

Contract-freeze Task Packet 必须从本次 Integrator alignment PR 合并后的同一个 integration head 创建并记录精确 `base_sha`，不能在本文预填未知 SHA。它的交付必须包含类型 / Port contract tests、active owner 对照、allowlist、完整离线回归和独立 exact-head review。只有该 PR 合并后才能进入下一个串行 gate；W2 三个 Worktree 的实际创建还必须等待下述 01-01–01-03 单 owner contract chain 与 01-04 implementation 依次合并。

实际执行证据：W2.0 已通过 [PR #9](https://github.com/weijie567/mini-agent/pull/9) 合并到 `integration/e2e01-thin`，精确 merge commit 为 `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3`。该结果只证明 Application persistence DTO / Port contract freeze 已合并，不证明具体 Adapter、HTTP、Harness 或纵向切片已经实现。

### W2.0a / Plans 01-01–01-03：persistence schema/version owner chain（串行、已完成）

W2.0 exact-head review 暴露的是需要 owner 裁决的问题，而不是可以由实现分支自行推断的 Core RecordSchema contract。owner chain 已依序完成：

- Plan 01-01 / PR #12：Project Direction 四轴 ownership、五类版本维度、logical / physical migration approval 与 Trace shared-structure authority；
- Plan 01-02 / PR #14：Memory exact-version、owner binding、record-graph integrity、startup recovery readiness 与 migration runtime 行为；
- Plan 01-03 / PR #16 与 clarification PR #17：Thin Slice scoped 17-item registry、66 条 top-level / 7 条 logical-child projection、strict codec API 与 01-04 exact two-file allowlist。

Plan 01-01 integration merge 为 `c96dea9f9f798212227cd05ff2a7b1f029a60287`。Plan 01-02 reviewed remote head 为 `b50038f9ce8398cd01289d38aeec09a183b68692`，integration merge 为 `af5afd2c93d429e1b090bfaf7af22c0fc4ec3c7b`。Plan 01-03 planning [PR #15](https://github.com/weijie567/mini-agent/pull/15)、mapping [PR #16](https://github.com/weijie567/mini-agent/pull/16) 与 projection clarification [PR #17](https://github.com/weijie567/mini-agent/pull/17) 依序合并；01-04 planning [PR #18](https://github.com/weijie567/mini-agent/pull/18) 与 persistence codec [PR #19](https://github.com/weijie567/mini-agent/pull/19) 也已合并。该 owner chain 当时到达 `bde99edec0bbb9ba331c6099c8b467c14fe24e58`；随后 01-04D 将当时的 exact integration head推进为 `a84d30188eaec75e45619e9939180ba78efa3b80`。

独立 Plan Checker 曾发现：把 Project Direction、Memory、Tool、Eval 与 Thin Slice Spec 一次写入同一个 Packet 会跨越多个 canonical ownership boundary。因此 owner decision 固定拆成三个依赖有序的单 owner PR：

1. `01-01 Project Direction persistence ownership / Trace structure decision`：只写 `PROJECT_DIRECTION.md`，固定 semantic/source/Port/adapter 四轴 ownership、版本维度与 `TraceEvent` shared structure / record-version owner。Activation merge SHA `6244756...` 预建的 `codex/e2e01-01-schema-owner-alignment` branch 只用于此 Packet。由于该 execution branch 早于 planning-status PR 创建，本地 checkout 不得作为 Plan provenance；写入前必须从串行合并后的 `origin/integration/e2e01-thin` 解析唯一 planning merge SHA，证明其相对 activation base 只包含声明的 8 个 planning-status 文件、`PROJECT_DIRECTION.md` byte-unchanged，并用 `git show` 读取和记录 Plan blob。
2. `01-02 Memory persistence decode / recovery / migration contract`：`COMPLETE / EVIDENCE_INDEXED`。Planning PR #13 与 owner PR #14 已合并；单写 Memory owner，181 个 serial tests通过，security Reviewer 的初始 HIGH 已修复并由两路 Reviewer 对 current remote exact head 复审为 `PASS`。
3. `01-03 Thin Slice 17-item minimum-persistence schema/version scoped mapping`：`COMPLETE / EVIDENCE_INDEXED`。PR #16 单写 Thin Slice Spec，冻结 17 项 code/version、logical envelope、closed registry / strict codec API 与 01-04 exact two-file contract；PR #17 在同一 owner 内关闭 66 条 top-level / 7 条 child projection gap。两次最终内容均通过 181 个 tests 与 independent exact-head review；辅助模型、Command 或未列入 canonical 表格的对象没有被计入。

当前 `CONFIRMED / IMPLEMENTED_COMPONENT_BOUNDARY` 包括写前 strict Pydantic JSON serialization、随记录保存 schema version、01-01 ownership / version / migration approval、01-02 exact-version / integrity / owner graph / recovery contract，以及 01-03 closed registry / projection / child contract。01-04 已实现 Application logical codec，但 physical Adapter、transaction、Runtime、HTTP、complete graph claim 与 recovery readiness 继续为 `NOT_IMPLEMENTED`。

### W2.0b / Plan 01-04：persistence schema/version implementation（串行、已完成）

01-04 从 exact integration base `9602fc18148b19c841889a8041daf10ccc5b8f1c` 预建 `codex/e2e01-01-persistence-codec` Worktree / branch。它只拥有：

- `src/mini_agent/application/persistence.py`
- `tests/component/application/test_persistence_contract.py`

Task Packet 只实现 owner chain 已批准的 17-item immutable registry、strict JSON codec、66 + 7 projection 与三类 child closure；不得复制 W2.0 DTO、修改 Port、实现授权、complete graph、Repository、table 或 migration。执行前必须先合并独立 planning-status PR，并从 Git object 捕获 exact Plan / Summary provenance。

01-04 的 local final reviewed head 为 `75d1d29c7a0580fe09e3c61ef6f820ec728e0586`，published head 为 `828fdb7f3e1560e6cf35fad763d22ac32798084e`，两者 tree 都是 `71eb2966a984b0e6c9330275b91c26d2861bc658`；PR #19 squash merge 为 `bde99edec0bbb9ba331c6099c8b467c14fe24e58`。exact two-file Packet 共 3642 insertions，通过 134 个 focused / 315 个 full tests、ruff、compileall、containment 与两路 final remote exact-head review。

PR #19 merge 后，Integrator 已在 root integration checkout 串行完成 Graphify AST + semantic refresh：最终 3089 nodes、4822 edges，graph health error 为 0，两个 stale marker 均已清除且 tracked tree clean。Graphify freshness gate 已通过；随后 source audit发现的 Port blocker仍必须由下述 inserted Packet 01-04D 独立关闭。

### W2.0c / Packet 01-04D：Application persistence Port closure（串行、已完成）

01-04 后的 Runtime / Infra / Eval Planner source audit与独立 contract/security review确认四类 frozen contract gap：

1. `RuntimeRecordPort.save_input_binding(record)` 与 `save_observation(record)` 只接收 source DTO，但 01-04 codec 对 `InputBindingRecord` 强制需要 external `request_unit_id`，对 `ObservationRecord` 强制需要 external `source_tool_call_id`、`source_run_id`、`source_task_id`、`source_request_unit_id`。这些值不在当前 Port参数中；Infra从其他 JSONB、写入顺序或关联记录反推会制造未冻结语义。
2. `RequestUnderstanding`、Accepted Delta、Task、RequestUnit、InputBinding 与 Conversation / Run links 当前通过多个独立 Port 写入；Task、RequestUnit 与 `TaskStateTransition` 也分裂推进。崩溃可留下 logical-child或关联图只写入一半的状态，并使 startup readiness长期失败。
3. Run 终态与 `RunTaskLink.result_task_state_version` 当前分裂写入；如果 Run先终结，后续 restart recovery不会再发现它，可能形成永久不完整图。
4. `RestartRecoveryPort` 当前把 discovery、分项 load、claim 与后续 CAS拆成多个调用；`MarkRunIncompleteForRecoveryCommand` 只携带 expected / incomplete Run。它无法让 Adapter证明 Memory 15.2要求的 strict decode、complete closed graph与 conditional claim绑定到同一 transactionally consistent snapshot或等价 fence。

因此 W2 dispatch曾从 `READY`改为 `BLOCKED_ON_01-04D`。Packet 01-04D只允许 Application Port declaration / Command contract与对应 Component contract tests，消费既有 canonical semantics而不修改 semantic owner。它必须：

- 为恰好五个 codec external-required relation提供不可猜测、typed、fail-closed write context；
- 原子创建初始 accepted Task graph，并原子推进 Task、RequestUnit 与 TaskStateTransition；
- 将 Run终态与所有 RunTaskLink结果版本绑定到 exact Task projections后一次提交；
- 冻结完整 recovery graph snapshot/fence、closed-set identity/version条件与 atomic claim / apply边界；
- 保持 Application协调恢复、Core产生合法状态迁移、Infrastructure实现 transaction/fence；
- 不实现数据库、Runtime behavior、HTTP、Provider、Harness或 Composition Root。

01-04D planning [PR #20](https://github.com/weijie567/mini-agent/pull/20) 与 owner [PR #21](https://github.com/weijie567/mini-agent/pull/21) 已依次合并。local final head `d82e394...` 与 published head `581f9d...` 的 tree均为 `fb36154...`；PR #21 squash merge为 `a84d30188eaec75e45619e9939180ba78efa3b80`。exact five-file Packet通过 210 个 focused / 344 个 full tests、ruff、compileall、containment、双路 exact-head review以及 Graphify 3253 nodes / 5814 edges、0 structural error、0 stale marker gate。该结果只关闭 Application Port owner gap，不证明 physical Adapter、Runtime、HTTP或 Eval Harness已经实现。

### W2.0d / Packets 01-04E–01-04G：W2 前置 owner closure（串行、已完成）

最终 Plan Checker 逐项对照 Memory、Application、Thin Slice与 Eval owner后识别出四个不能交给 W2实现分支猜测的问题，并按 ownership合并为三个 dependency Packet：

1. `01-04E` 单写 `memory-design-reference.md`、`core/memory.py`与对应 contract test，把 `ContextManifest.token_counts` 保持为必需对象，但将逐方向计数冻结为 `int | None`：`None` 表示未精确测量，`0` 表示已观测的精确零；不引入推测式 TokenCounter。
2. `01-04F` 单写 Thin Slice scoped owner、两个 versioned semantic artifacts（Case、model script）、一个 version manifest与两个 artifact / catalog tests，共三个 JSON 文件：stale-state场景使用有效 `base_task_state_version = null`，在 revalidation后、Gate前通过 canonical `ApplyTaskTransitionCommand` / `RuntimeRecordPort` 将 Task / RequestUnit从 `ACTIVE/v1` 推进到 `WAITING_USER/v2`，Gateway精确得到 `STATE_VERSION_MISMATCH`，随后从当前投影推进到 `BLOCKED/v3`；总 version delta为2、`TaskStateChanged`为3。该脚本使用独立 `CONTROL_GATEWAY_STALE_STATE_REJECTED` variant，unknown-tool继续使用原 variant与count=2。fact-bearing raw presentation严格校验失败映射为 `PROVIDER_PROTOCOL_ERROR`，零 `PresentationPlanProposed`、零 renderer invocation。本 Packet只冻结可实现契约，不证明 Runtime/Harness可达性。
3. `01-04G` 单写 Application records / Ports与对应 contract tests，由 Core预先产生合法 recovery Trace并放入 `ApplyRestartRecoveryCommand`；Port contract要求 compliant Infra Adapter在 `APPLIED`时将恢复状态与 Trace一次原子提交，并拒绝 recovery事件中的跨类型可选字段污染；conflict、not-applicable与 reconciliation-required保持零写入。本 Packet不实现物理 Adapter事务。

三个 Packet均从 `a84d30188eaec75e45619e9939180ba78efa3b80` 预建互斥 Worktree / branch，并已按 `01-04E` → `01-04F` → `01-04G` 串行取得 exact-head review与 merge。共同 planning PR #22 merge 为 `55b406b30f6f34988fbde88b357fb2a9dcc842e0`；01-04E owner PR #23 merge `be68490b9d8440a29a43fa8143e9dd5d4bcbfeda`，357 个 full tests通过；01-04F owner PR #24 merge `1d47fae3c2a3b910d92acb4713f2015199f54d49`，364 个 full tests通过；01-04G owner PR #25 merge `c35687dafa3881bb322d91515068d8d39be79df6`，466 个 full tests与 Graphify 3353 nodes / 5999 edges / 50 hyperedges、0 structural error、0 stale marker gate通过。`c35687d...` 是 01-05/06/07 唯一 execution base；三个 W2 Worktree 仍必须等待对应 planning PR 合并后的 exact preflight，不能把 planning 完成写成 execution 已启动。

### W2：组件实现（并行）

`W2-RUNTIME`：

- Validator → Reducer → Registry / Gateway → Observation routing → Presentation Gate → Renderer。
- 覆盖身份覆盖、参数替换、旧版本、停止原因和错误映射。
- 只实现冻结后的 Runtime 行为；如需改变共享 DTO / Port，停止并提交 dependency request，不在本分支漂移契约。

`W2-INFRA`：

- Session / HTTP、持久化、作用域 `get_order`、安全分流和重启恢复。
- 证明 Alice 查询 Bob 与查询不存在订单时均不产生私有 Observation。
- 实现冻结 Port 的 PostgreSQL Adapter 和 migration；独占 SQLAlchemy metadata 与 Alembic chain，复用且保持 `tests/conftest.py` 和共享测试 bootstrap byte-identical。

`W2-EVAL`：

- Scripted / Qwen Adapter、Harness、Graders、结构化 Eval Result 和故障注入。
- 默认离线 lane 不读取模型凭据、不访问外部网络。
- 只消费冻结 DTO / Port 与现有 PostgreSQL fixture，不修改 `tests/conftest.py`、migration、Application 或 Composition Root。

Gate：三方只通过冻结的 Port / DTO / Fixture contract 对接；不得修改其他 Workstream 的 owned files。

三个分支对应 Plans 01-05/06/07。只有 planning PR 合并且 post-merge preflight证明 Plan provenance、branch/path均未占用、三个 ownership集合两两无交集后，Integrator 才能在 workflow 外从同一个 01-04G final owner merge `c35687d...` 预建并并行开发；完成后仍串行集成，推荐顺序为 `W2-RUNTIME` → `W2-INFRA` → `W2-EVAL`，每次合并后后续分支都必须基于最新 integration head 重新验证并取得新的 exact-head review。不得调用 stock `gsd-execute-phase` 创建、合并或清理这些 Worktree。

受控 Planner 初审已确认三个边界条件：

- 01-05 Runtime不得把 01-04D–01-04G之后仍属于 physical Adapter / integration的 recovery工作解释成已关闭，也不得再次修改 shared Port。
- 01-06 Infra可以拥有 Infra-local HTTP router / app factory 与 fake handler contract tests，但不得自行发明 Application inbound Port；真实 Runtime wiring留给 01-08。
- 01-07 Eval Harness通过 Eval-local injected fake / in-process SUT callable运行，构造既有 typed Eval records并交给既有 `EvalResultPort`；不得复制 DTO、修改 `tests/conftest.py` 或声称真实 Runtime / HTTP / PostgreSQL纵向证据。

### W3：纵向集成（串行）

Plan 01-08，Owner：Integrator。

- 只在 `bootstrap.py` 装配具体 Adapter。
- 按 Spec 第 10.1 节逐项验证完整写入门禁：
  1. 原始 `Message` 可靠保存后才运行 Request Understanding；
  2. accepted Delta、Task / RequestUnit 与 `InputBinding` 在 Gateway 接受候选前持久化；
  3. `ModelVisibleToolsetArtifact` 在应用接受 Run 前写入，且每个 `ContextManifest` 的 hash 都可解析；
  4. `GateDecision` 在 `ToolCall` 创建前写入，`ToolCall` 关联 decision、validated state version 与 binding refs；
  5. `Observation` 在第二个 `ContextManifest` 和 Presentation 模型调用前写入。
- 从 HTTP 边界运行 `E2E01-01/04`。
- 验证普通 Trace、Context Manifest 和响应不含 Runtime-private 身份或 Bob 数据。
- 产生关联 `trace_ref` 和版本 manifest 的结构化 Eval Result。

### W4：Post-execution 独立审查与发布门禁（不是 GSD Plan）

1. `reviewer` 只读审查安全、架构、契约漂移和测试缺口。
2. 发现由原 owner 修复，Reviewer 不越权写入。
3. 先通过默认离线 `ScriptedModelProvider` 硬门禁。
4. 真实 Qwen 配置存在时才运行 `qwen_baseline`；缺失时必须是 `SKIPPED / NOT_RUN`。
5. 只有所有 DoD 有可复现证据后，才更新 Coverage Matrix 生命周期和 `AGENTS.md` canonical 命令。

W4 是 01-01 至 01-08 执行并集成后的 quality gate，不计入 Phase 1 的八个 numbered Plan；插入式 01-04D / 01-04E / 01-04F / 01-04G只作为阻断依赖 Packet记录，不推进 lifecycle。先由 canonical Coverage Matrix owner更新 lifecycle，再由 Integrator手工同步 derived Requirements / Roadmap / State；不得调用自动 progress / completion API。

## 8. 集成门禁

每个 feature branch 至少通过：

- `git diff --check`；
- task-specific unit / integration / schema check；
- 文件 allowlist 检查；
- 依赖和契约变更说明。

每次 integration merge 至少通过：

- 已存在的离线测试；
- 从空 namespace 应用 migration；
- Fixture / Dataset 版本一致性；
- 受影响 active 文件的 cross-file impact scan。

最终门禁以仓库中真实出现且验证通过的配置为准，唯一 canonical 命令清单见 `AGENTS.md` 第 6 节。W1 已使依赖同步、根目录 Compose 数据库、migration 与当前 `uv run pytest` 套件可执行，但该套件目前只证明 W1 contract / artifact / persistence primitives，不得描述成 HTTP / Trajectory / E2E gate。

以下仍只是 Implementation Spec 的后续目标，当前不得宣称可执行：

```bash
uv run pytest -m qwen_baseline
uv run uvicorn mini_agent.main:app --reload
```

## 9. Task Packet 模板

```yaml
task_id: W?-ROLE-short-name
goal: 一句话描述可验收结果
repository: weijie567/mini-agent
remote: origin
head_branch: feat/e2e01-<role>-<task>
base_branch: integration/e2e01-thin
base_sha: <exact commit>
worktree_id: <public logical id; runtime path is private dispatch data>
agent_role: runtime-engineer | infra-engineer | eval-engineer | reviewer
owned_files:
  - <exact path or narrow glob>
forbidden_files:
  - <shared hotspot or other owner path>
canonical_inputs:
  - <active owner path and relevant section>
dependencies:
  - <merged task or frozen interface>
contract_changes: NONE | <exact contract delta and owner approval>
security_impact: NONE | <affected invariant and verification>
eval_impact: NONE | <affected Case / grader / dataset / gate>
required_checks:
  - <command and expected result>
done_when:
  - <observable acceptance condition>
rollback: <revert / disable / migration rollback procedure>
handoff_to: tech-lead
handoff_format: docs/implementation/e2e01-thin-slice-multi-agent-plan.md#10-handoff-模板
```

一个 GSD Plan 必须且只能对应一个精确 Task Packet。Packet 可以包含多个原子 task，但不得跨 repository、branch、Worktree、writer 或 ownership boundary。

启动检查必须逐字段写入实际值。Task Packet 未给出 `repository`、`remote`、`head_branch`、`base_branch`、`base_sha`、`worktree_id`、`owned_files`、`forbidden_files`、`canonical_inputs`、`dependencies`、`contract_changes`、`security_impact`、`eval_impact`、`required_checks`、`done_when`、`rollback`、`handoff_to` 或 `handoff_format` 时，不启动写入 Agent。没有依赖、禁止文件、契约变化或某类影响时也必须显式填写 `NONE`，不得留空、继承隐含默认值或由 Agent 猜测。

所有写入 Agent 启动前记录 exact base/head、branch、clean state 与 allowlist；结束后对比相对 base 的全部 changed files、commits 和当前 head。出现 scope drift、非预期 commit 或 forbidden file 变化时标记 `BLOCK` 且不得 push。

## 10. Handoff 模板

```text
Task / branch / commit:
Result: COMPLETE | PARTIAL | BLOCKED
Changed files:
Commands run:
Results:
Contract changes: NONE | details
Security impact: NONE | details
Eval impact: NONE | details
Allowlist check:
Assumptions:
Unresolved risks:
Rollback: command / PR / operational procedure
Recommended merge order:
```

`COMPLETE` 只表示该 Task Packet 完成，不表示整个切片已经实现。Integrator 必须从源码和命令输出独立验证后才能更新项目状态。

## 11. GSD 使用边界

GSD 只可作为现有协作模型上的派生编排层。W1 与 W2.0 未使用 GSD；activation feature head `957cabd6b31dd2156848acd515d2e8dc3d19bd50` 已通过双独立 exact-head review，并由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) squash merge 为 integration commit `624475681847be5a8e463e32dafd28a0483b213b`。Plan 01-01 已通过 planning PR #11 / owner PR #12 合并，Plan 01-02 已通过 planning PR #13 / owner PR #14 合并，Plan 01-03 已通过 planning PR #15 / owner PR #16 / clarification PR #17 合并，Plan 01-04 已通过 planning PR #18 / implementation PR #19 合并，Packet 01-04D已通过 planning PR #20 / owner PR #21合并，Packets 01-04E/F/G 已通过 planning PR #22 与 owner PR #23/#24/#25依序合并；当前 Phase 1 正使用受控 planning adapter发布 Plans 01-05/06/07。精确 execution base 为 `c35687dafa3881bb322d91515068d8d39be79df6`，Plan head仍从 Git ref / GitHub PR head外部解析，不在同一 commit内容中自引用硬编码。

### 11.1 Activation Gate（`COMPLETE / EFFECTIVE`）

启用任何会写入 `.planning/` 的 GSD 流程前，Integrator 必须通过一个独立、串行的 activation PR：

- 建立 active owner → GSD 派生文件的显式 mapping 和 blocker conflict review；
- 裁决适用于既有项目的初始化命令，不默认运行 `$gsd-new-project`；
- 给出 `.planning/` 精确 allowlist、single-writer、phase / integration branch 映射和回滚方式；
- 在隔离 Worktree 演练初始化，证明不会覆盖 active canonical owner；
- 记录可复现验证命令，并由独立 Reviewer 对精确 head SHA 给出 `PASS`。

Activation 的派生文件与规则见 [`.planning/GOVERNANCE.md`](../../.planning/GOVERNANCE.md) 和 [`.planning/ACTIVATION.md`](../../.planning/ACTIVATION.md)。Gate 已由 PR #10 完成；后续只读 `$gsd-progress` 仍必须禁止自动 route，`$gsd-health` 必须同时读取 CJS / SDK surface 且不运行 `--repair` / `--force`。Stock `$gsd-import`、`$gsd-plan-phase`、`$gsd-execute-phase`、`$gsd-verify-work` 与 `$gsd-ship` 即使 activation 生效后也保持禁用。

### 11.2 激活后受控使用

- GSD planner / checker 角色只读 canonical inputs 与目标 slot 后提供建议；Integrator 在预建的 dedicated planning-status Worktree / feature branch 中单写最终 Plan / Task Packet。一个 Plan 只映射一个 Packet；不运行会自动更新共享 State 的 stock `$gsd-import` / `$gsd-plan-phase`。
- Activation merge 后首个工作不是直接导入 implementation，而是由 Integrator 预建只写 `PROJECT_DIRECTION.md` 的 01-01 Worktree / branch。01-01 → 01-02 Memory → 01-03 Thin Slice 已按单 owner exact-head PR 串行完成；01-04 已在 exact two-file Packet 内实现该 owner chain且没有重开语义。
- 实际实现由 Integrator 在 workflow 外预建 exact Task Packet Worktree / feature branch，再交给 Codex Agent。多个 Agent 只在 ownership 不重叠时并行；feature PR 指向 integration，Integrator 串行合并。
- `$gsd-code-review` 只在 exact-integration-SHA review-artifact Worktree 中以规范化绝对路径的 exact `--files` 运行；preflight 必须证明 requested=accepted=unique、每项均为仓库内 regular tracked file 且 literal tracked 输出精确等于单个相对路径，workflow transcript 必须报告相同精确数量且不含 stock 的 outside-repository / file-not-found skip 输出，唯一写入为 Phase `REVIEW.md`。
- `$gsd-code-review-fix` 与 `$gsd-validate-phase` 只在 Integrator 预建的 dedicated fix / validation Worktree / branch 中条件运行；precheck exact base/head/allowlist，postcheck 全部 changed files / commits，scope drift 即 `BLOCK` 且不 push。
- `$gsd-eval-review` 只有派生 AI / Eval mapping 明确引用 canonical Eval owner 后才构成 gate；`$gsd-secure-phase` 必须有映射项目安全不变量的完整 `<threat_model>`，zero-threat 不构成通过。
- 会话式验收使用受控 UAT adapter，只产 UAT artifact 且不包含 gap / transition / execute route；stock `$gsd-verify-work` 因没有 `--no-transition` 且会调用禁用的 `phase.complete` 而不运行。
- post-execution quality gate 通过后，先更新 canonical Coverage Matrix lifecycle，再由 Integrator 根据 Summary、PR 和硬证据手工同步 derived Requirements / Roadmap / State。
- Feature → integration 和 integration → `main` 均通过显式 GitHub repository / head / base 创建 PR；不调用 `$gsd-ship`。
- 只有真正独立、生命周期不同的 milestone 才使用 `$gsd-workstreams`；Runtime、Infra、Eval 是同一 E2E 切片的协作模块，不为它们建立三套产品 roadmap。

### 11.3 当前不使用

- 不直接运行 `$gsd-new-project`：仓库已经存在明确 canonical owner、P0 方向、Implementation Spec 和执行 Plan，重新问答生成会制造第二套项目定义。
- 不直接以默认优先级运行 `$gsd-ingest-docs`：本项目采用“专门 owner 仅在自身范围内优先”，不能让通用 `ADR > SPEC > PRD > DOC` 规则静默覆盖跨域 owner。未来如需导入，必须使用显式 manifest、owner mapping 和 blocker conflict review。
- 当前 P0 不运行 `$gsd-new-milestone`、`$gsd-autonomous` 或 `$gsd-phase-autopilot`，也不让 GSD 自动修改 active canonical 文档或 Case 生命周期。
- Stock GSD 1.38.3 的 `$gsd-execute-phase`、`phase.complete`、`requirements.mark-complete` 与 `roadmap.update-plan-progress` 禁用。Execute 会枚举、合并并可能以 `--force` 清理全部非当前 Worktree，还会提前推进 phase lifecycle，与项目 Integrator-owned Worktree / quality gate 冲突。
- Stock `$gsd-import` / `$gsd-plan-phase` 禁用；它们会在 artifact 生成路径写共享 State，且 import 不能在写入前机械保证只替换既有 Roadmap slot。规划时只使用 GSD planner / checker 角色的只读建议，由 Integrator 单写最终 artifact。
- Stock `$gsd-verify-work` 禁用；当前版本没有 `--no-transition`，验收通过路径会进入 transition 并调用 `phase.complete`。UAT 使用无 lifecycle mutation 的受控 adapter。
- `$gsd-ship` 禁用；其单一 base 模型不能表达 feature → integration 与 integration → `main` 两级 PR。
- `.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Integrator 预建 Worktree 的 Codex 多 Agent 并行。

### 11.4 GitHub 映射

| GSD 对象 | GitHub / Codex 对象 |
|---|---|
| Milestone / Phase | integration branch 与最终 PR |
| Plan | 一个精确 Task Packet |
| Wave | 一组由 Integrator 预建、ownership 不重叠的 Worktree tasks |
| Executor | feature branch 的写入 Agent |
| Verification / Review | PR checks、Reviewer findings 与可复现输出 |
| `.planning/` | Integrator 管理的派生执行状态，不拥有产品语义 |

Activation 生效后，Integrator 仍是共享 `.planning/STATE.md`、Roadmap、Requirements 和跨 phase 索引的 single writer；plan-scoped 文件可以通过 Task Packet 分配给独立 Agent，但不得让多个 feature branch 各自推进同一份共享状态。机械检查、GitHub exact-head review 与 PR merge 是完成证据，GSD 文件不能自我证明实现完成。GSD 不获授权创建、合并、清理或 `--force` 操作项目 Worktree。

## 12. 当前状态

| 项目 | 状态 | 证据 |
|---|---|---|
| Git baseline | `CONFIRMED` | baseline commit `5043043` |
| 项目级 Codex roles | `CONFIRMED` | `.codex/config.toml`、`.codex/agents/*.toml` |
| 多 Agent 执行计划 | `CONFIRMED` | 本文 |
| GitHub PR 远程流程 | `REMOTE_CONNECTED / PUBLIC / BASE_BRANCHES_PROTECTED` | `origin=https://github.com/weijie567/mini-agent.git`；当前 integration head 为 `c35687dafa3881bb322d91515068d8d39be79df6`；流程建立审计记录见 [PR #1](https://github.com/weijie567/mini-agent/pull/1)；两个 base branch 均要求 PR、对管理员生效并禁止 force push / deletion；当前没有 required status checks，因为 CI workflow 尚未建立 |
| GSD | `ACTIVE / EFFECTIVE / W2_PLANS_EXACT_HEAD_REVIEW_PENDING` | activation PR #10生效；01-01至01-04G已合并并形成evidence-indexed Summary；01-05/06/07已从同一exact base完成受控planning，初始checker approval已被PR review supersede，当前修正版仍须取得双路exact-head `PASS`并合并 |
| W1 Infra / Runtime | `CONTRACT_IMPLEMENTED / PARTIAL` | [PR #5](https://github.com/weijie567/mini-agent/pull/5) 与 [PR #4](https://github.com/weijie567/mini-agent/pull/4) 已按序合并；存在 `src/`、`pyproject.toml`、`uv.lock`、`compose.yaml`、空业务 migration、Core / Application contracts 与 PostgreSQL namespace tests；不含完整 Adapter、HTTP 或 orchestration |
| W1 Fixture / Eval artifacts | `CONTRACT_IMPLEMENTED / CONTRACT_DEFINED` | [PR #3](https://github.com/weijie567/mini-agent/pull/3) 已双审合并；5 个 versioned JSON artifacts、20 个 focused consistency tests；尚无 Provider Adapter、Harness、Eval Result 或 Baseline |
| W1 集成验证 | `CONFIRMED` | 在仓库根目录执行 `uv sync --all-groups`、两个 Compose health gate、`uv run alembic upgrade head`、`uv run pytest` 与 `uv run pytest -n 8`；serial / xdist 均 `125 passed`，测试 namespace 清理为 0 |
| W2.0 contract freeze | `CONFIRMED / MERGED` | [PR #9](https://github.com/weijie567/mini-agent/pull/9) 已合并；integration exact head `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` |
| W2 dispatch | `BLOCKED_ON_PLANNING_PR / GRAPH_GATE_PASS` | 01-04E/F/G PR #23/#24/#25已合并；W2 exact base `c35687d...`通过466 tests与Graphify gate；01-05/06/07 planning PR尚未合并，三个execution Worktree / branch尚未创建 |
| `E2E01-01/04` 生命周期 | `CONTRACT_DEFINED` | 尚无运行证据 |

W0、W1、W2.0 contract freeze、GSD activation、Plans 01-01–01-04与 inserted Packets 01-04D/E/F/G已完成；numbered Plan evidence口径是4/8，实际 Task Packet口径是8/12，canonical lifecycle与派生 checkbox仍保持0/8。当前先让01-05/06/07 exact-base planning PR通过双路exact-head review并合并，再从 `c35687d...` 预建三路互斥 W2 Worktree；创建前不得声称execution已启动。后续任何“可运行”“已通过”结论都必须附实际commit、命令与输出。
