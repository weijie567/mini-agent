# 第一最薄 E2E-01｜Codex 多 Agent 实施计划

更新日期：2026-07-29｜状态：`ACTIVE / EXECUTION_PLAN`｜适用范围：`E2E01-01`、`E2E01-04`｜性质：`NON_NORMATIVE` 执行消费者

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

三个 Packet均从 `a84d30188eaec75e45619e9939180ba78efa3b80` 预建互斥 Worktree / branch，并已按 `01-04E` → `01-04F` → `01-04G` 串行取得 exact-head review与 merge。共同 planning PR #22 merge 为 `55b406b30f6f34988fbde88b357fb2a9dcc842e0`；01-04E owner PR #23 merge `be68490b9d8440a29a43fa8143e9dd5d4bcbfeda`，357 个 full tests通过；01-04F owner PR #24 merge `1d47fae3c2a3b910d92acb4713f2015199f54d49`，364 个 full tests通过；01-04G owner PR #25 merge `c35687dafa3881bb322d91515068d8d39be79df6`，466 个 full tests与 Graphify 3353 nodes / 5999 edges / 50 hyperedges、0 structural error、0 stale marker gate通过。`c35687d...` 是 01-05/06/07 唯一 execution base；planning PR #26 reviewed head `2922308b...`取得双路`PASS`并squash merge为`968b4a9...`后，post-merge preflight已证明Plan provenance、branch/path未占用与ownership零交集，三个W2 Worktree随后从`c35687d...`创建并派发。该dispatch不构成实现完成证据。

### W2.0e / Packet 01-04H：normal terminal-turn atomicity（串行、阻断 W2 merge）

01-05 Runtime PR #28 的 fresh exact-head review确认：当前实现先通过独立 Task transition把 Task / RequestUnit推进为终态，再提交 `Run(COMPLETED)` / `RunTaskLink`，最后才 best-effort 写 `ASSISTANT Message` 与最低必需 `RunStopped`；后两者失败会被吞掉并仍返回成功。只把 Message / Trace 添加到旧 finalization仍不能回滚已经独立提交的 Task状态，因此不是完整修复。

现有 canonical 语义已经明确：

- Memory owner要求 Conversation原始消息进入 Conversation Store且必须可靠保存；
- Task / RequestUnit状态迁移必须可靠、带版本控制；
- Thin Slice把 `MessageRecord`、Task / Run / link与 `TraceEventRecord`列入既有17项持久化集合，并把 `TaskStateChanged`、`RunStopped`列为对应受控阶段的最低 Trace；
- 只有 Trace扩展字段允许按可观测策略降级，不能把整个 mandatory event当作可丢投影。

本次 planning-status PR 同步修正 Thin Slice 第10.3/11节一个既存冲突：`FAILED` Run没有canonical `stop_reason`或用户结果，而`RunStopped`结构要求两者，因此第一切片只对正常`COMPLETED`与recovery `INCOMPLETE`强制`RunStopped`，未捕获异常的`FAILED`只可靠关闭Run/link并不得伪造Trace。该裁决不新增枚举、HTTP结果或持久化项。

在此前提下，01-04H owner Packet不再修改canonical文档、不新增第18项记录或migration，只单写以下四个 Application owner文件：

```text
src/mini_agent/application/records.py
src/mini_agent/application/ports.py
tests/component/application/test_record_contracts.py
tests/component/application/test_ports_contract.py
```

它扩展既有 `FinalizeRunCommand` / `RuntimeRecordPort.finalize_run_if_active`，使正常 `COMPLETED` terminal turn在一个条件事务中同时提交：

```text
Task / RequestUnit / TaskStateTransition（0或1）
+ TaskStateChanged（与transition一一对应）
+ terminal Run / RunTaskLink
+ exact AgentRunResult binding（只用于校验与 APPLIED 后返回，不是 persistence item）
+ ASSISTANT Message
+ RunStopped
```

无Task的受控终态只包含 `RunStopped`；未捕获异常的 `FAILED` closure不携带Task transition、用户结果、Assistant Message或terminal Trace，也不伪造reason / outcome。`APPLIED`是唯一可返回成功的结果；`PROJECTION_CONFLICT` / `NOT_APPLICABLE`必须零写入全部上述投影。

01-04H planning-status PR由Integrator单写，exact 11-file allowlist为：

```text
README.md
.planning/PROJECT.md
.planning/REQUIREMENTS.md
.planning/ROADMAP.md
.planning/STATE.md
.planning/phases/01-cycle-1-e2e-01/01-04H-PLAN.md
.planning/phases/01-cycle-1-e2e-01/01-05-PLAN.md
.planning/phases/01-cycle-1-e2e-01/01-06-PLAN.md
.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
docs/implementation/e2e01-thin-slice-implementation-spec.md
docs/implementation/e2e01-thin-slice-multi-agent-plan.md
```

其中只有 Thin Slice owner两段文字属于canonical clarification；01-05/01-06只增加historical/non-reusable横幅，其余是派生状态、Plan、Validation与入口对齐。01-04H execution base为`ea0a72fdac597a9ae78b2ed6fa34d14ef2c1eb57`；planning PR #31 reviewed head `c785ad3...` merge为`db6e258...`，Plan/Thin Slice blobs为`386001a8...`/`08d90f1b...`。Feature PR #32 exact head `c0306ef...` / tree `cced2a5...`经local与GitHub transport review均`PASS / NOT_FOUND`，squash merge为当时的integration head `64992cf3bdc6205e00d0c36433309b1657a57531`。Post-merge `560 passed`，Graphify为3485 nodes / 6350 edges / 1340 communities，structural diagnostic为0、无stale marker且tracked tree clean。01-04H因此是`COMPLETE / EVIDENCE_INDEXED`。

01-04H merge后没有force-rebase或把共享owner commit cherry-pick进旧published feature branch。新的single-writer planning-status PR现在签发`01-05R`：execution base固定为`64992cf...`，branch `codex/e2e01-w2-runtime-r`，worktree `e2e01-w2-runtime-r`，ownership仍为历史Runtime精确14文件。历史head `a27141ba902015af34602fe15eeec4ba44482687`只作受控donor与review/RED lineage；移植后只有`agent_run_service.py`及其test可以因消费01-04H而不同，其余12 blobs必须byte-identical。Replacement移除终态前独立Task transition与post-commit best-effort Message/RunStopped，只提交一个complete `FinalizeRunCommand`并只在`APPLIED`后返回。只有01-05R reviewed merge后，才以新的exact integration SHA签发`01-06R`。旧01-05/01-06 Plans与PR #28/#30保持历史证据。

本次01-05R planning-status PR精确allowlist为：

```text
README.md
.planning/PROJECT.md
.planning/REQUIREMENTS.md
.planning/ROADMAP.md
.planning/STATE.md
.planning/phases/01-cycle-1-e2e-01/01-04H-SUMMARY.md
.planning/phases/01-cycle-1-e2e-01/01-05R-PLAN.md
.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
docs/implementation/e2e01-thin-slice-multi-agent-plan.md
```

它不修改历史01-05/01-06 Plans、GOVERNANCE、AGENTS、Thin Slice/Architecture/Business/Eval canonical owners或Case lifecycle。Planning PR本身不证明Runtime已开始或完成；merge后Executor另行记录`PLANNING_CONTRACT_SHA`与Plan/Summary blob，并证明14个Runtime owned paths在`64992cf...`与planning merge之间均不存在。

01-05R随后完成了“planning → execution → exact-head review → latest-integration overlay → serial merge → post-merge verification”闭环。Planning PR [#33](https://github.com/weijie567/mini-agent/pull/33) reviewed head为`db7659b57f326b5da85df388d00dffbb3ec04536`，squash merge为`0f94827386a749cb9f1c20392f95a22c8d4b5c08`，Plan / predecessor Summary blobs分别为`db83429a2025a6fe858ff1629e4db8c95e00b331` / `2e4932be6d7ce7594efaa64815cc3708f640e035`。Runtime feature PR [#34](https://github.com/weijie567/mini-agent/pull/34) exact head / tree为`05f01828f57a106575058d7571ddf31aa1d9a78c` / `a8e0ccb700ae45da5d261850dba01f9ff0dfa8ee`；test-only RED在26项中得到1个预期失败，GREEN后paired / focused / migration / full分别为27 / 100 / 38 / 660项通过。Latest-integration overlay head / tree为`26756ccee19d0cc178f58a686a5fd184d41881b2` / `4b6432082a6c022ae4edee15264c83339fd444a0`，local与GitHub transport review均为`PASS / NOT_FOUND`；squash merge `fb607019130843c94825a47d7822518cbdb2143c`保持相同tree。Post-merge再次取得`660 passed`、migration `38 passed`、compileall / exact-diff通过，Graphify为3788 nodes / 8309 edges / 1353 communities且structural diagnostic为0、无stale marker、tracked tree clean。01-05R因此是`COMPLETE / EVIDENCE_INDEXED`。

现在由新的single-writer planning-status PR签发`01-06R`。Execution base固定为`fb607019130843c94825a47d7822518cbdb2143c`，branch为`codex/e2e01-w2-infra-r`，logical worktree ID为`e2e01-w2-infra-r`，ownership仍为历史Infra精确13文件。历史donor head / tree `054dcaf2d4101b0bd422ddb3b3eb47b734523bc1` / `b0ec302de8dce6f3740c7f9a78fcc4aaa43c85d9`只作受控replay与RED/review lineage；移植后仅`postgres.py`、`test_postgres_record_adapters.py`、`test_postgres_atomicity.py`与`test_postgres_recovery.py`允许因关闭审查发现和消费01-04H而不同，其余9个owned blobs必须与donor byte-identical。Replacement必须同时关闭物理错误解码最小披露、locked RUNNING parent Run fence，以及完整终态Task / RequestUnit / Run / link / Message / Trace同一个PostgreSQL事务与任一child fault全回滚。

本次01-06R planning-status PR精确allowlist为：

```text
README.md
.planning/PROJECT.md
.planning/REQUIREMENTS.md
.planning/ROADMAP.md
.planning/STATE.md
.planning/phases/01-cycle-1-e2e-01/01-05R-SUMMARY.md
.planning/phases/01-cycle-1-e2e-01/01-06R-PLAN.md
.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
docs/implementation/e2e01-thin-slice-multi-agent-plan.md
```

它不修改历史01-05/01-06 Plans、GOVERNANCE、AGENTS、Thin Slice/Architecture/Business/Eval canonical owners或Case lifecycle。Planning PR本身不证明Infra已开始或完成；merge后Executor必须记录新的`PLANNING_CONTRACT_SHA`与Plan/Summary blob，并证明13个Infra owned paths在`fb607019...`与planning merge之间均未改变。

Eval PR #29已从`c4eca0d...`经isolated fix推进到`b8ecbb0a7d69761911213a8433b50c6062116c79`；typed evidence graph、grader-runner、retry/provenance、raw enum/supersedes、strict Observation storage与datetime/UUID subclass findings均已关闭。它在post-Infra overlay `ee46f38...`重复191 focused / 936 full（1 deselected）、40 migration、artifact hash与两条zero-network preflight，并取得双路`PASS / NOT_FOUND`后merge为当时的integration head `eee1c0e...`。

本次01-07A planning-status PR精确allowlist为：

```text
README.md
.planning/PROJECT.md
.planning/REQUIREMENTS.md
.planning/ROADMAP.md
.planning/STATE.md
.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
.planning/phases/01-cycle-1-e2e-01/01-06R-SUMMARY.md
.planning/phases/01-cycle-1-e2e-01/01-07-SUMMARY.md
.planning/phases/01-cycle-1-e2e-01/01-07A-PLAN.md
docs/implementation/e2e01-thin-slice-multi-agent-plan.md
```

该historical planning PR没有修改GOVERNANCE、AGENTS、Business / Eval canonical owners或Case lifecycle。01-07A随后通过PR #37/#38完成，Business / Eval / project-rule状态分别通过PR #39–#41对齐，均未推进Case lifecycle。

本次01-07B planning-status PR精确allowlist为：

```text
README.md
.planning/PROJECT.md
.planning/REQUIREMENTS.md
.planning/ROADMAP.md
.planning/STATE.md
.planning/phases/01-cycle-1-e2e-01/01-07A-SUMMARY.md
.planning/phases/01-cycle-1-e2e-01/01-07B-PLAN.md
.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
docs/implementation/e2e01-thin-slice-multi-agent-plan.md
```

它不修改historical Plans、GOVERNANCE、AGENTS、active canonical owners、源码、测试、Eval artifacts或Case lifecycle。Cross-file scan确认`PROJECT_DIRECTION.md`的实现状态段仍需由其owner独立对齐；当前PR只记录该开放项。Planning PR本身不证明01-07B Eval实现已经开始或完成。

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

三个原始分支对应historical Plans 01-05/06与01-07。planning PR #26与post-merge preflight证明了当时的Plan provenance、branch/path和ownership；三个Worktree从01-04G merge `c35687d...`并行开发。Fresh review暴露01-04H共享owner blocker后，原始Runtime / Infra PR只保留实现与审查证据，不再作为可合并head；01-05R replacement从01-04H exact merge `64992cf...`完成并串行合并为`fb607019...`，01-06R再从该exact SHA完成并合并为`8e21652...`，01-07 Eval通过post-Infra latest overlay复验后合并为当时的integration head `eee1c0e...`。三者均已取得exact-head / overlay review与post-merge gate。不得调用stock `gsd-execute-phase`创建、合并或清理这些Worktree。

受控 Planner 初审已确认三个边界条件：

- 01-05 Runtime不得把 01-04D–01-04H之后仍属于 physical Adapter / integration的 recovery工作解释成已关闭，也不得再次修改 shared Port；replacement Runtime只消费01-04H命令，移除终态前的独立Task transition及post-commit best-effort Message / RunStopped。
- 01-06 Infra可以拥有 Infra-local HTTP router / app factory 与 fake handler contract tests，但不得自行发明 Application inbound Port；replacement Infra实现01-04H同事务、fault rollback与并发winner/conflict，真实 Runtime wiring仍留给 01-08。
- 01-07 Eval Harness通过 Eval-local injected fake / in-process SUT callable运行，构造既有 typed Eval records并交给既有 `EvalResultPort`；不得复制 DTO、修改 `tests/conftest.py` 或声称真实 Runtime / HTTP / PostgreSQL纵向证据。

### W3：纵向集成（串行）

Plan 01-08，Owner：Integrator。

Real Eval接入前的首轮只读planning/checker核查发现三个Runtime-owned Trace blocker：`ContextManifestRecorded.model_call_purpose`、fixed-result `ResponseRendered`与stale-state hook active-run identity。插入式Plan 01-07A据此从`eee1c0e...`执行，已通过planning/Runtime PR #37/#38 reviewed merge为`4cfac0a...`；Business / Eval / project-rule状态PR #39–#41随后形成01-07B execution base `8544137...`。01-07B通过PR #42–#44完成Plan签发、状态对齐、exact six-file feature、双路review、latest-integration overlay与串行merge `ccdafe87...`，Case lifecycle保持0/8。

01-08第二轮preflight确认以下不能由Integrator隐含修补的owner boundary：

- Eval execution boundary：`EvalCaseSut`输入接收完整Case，Scripted Provider保留semantic script/`expected_control_result`，output又要求SUT填semantic `case_id`；nested message/step字段也没有closed projection。Trace grader只检查存在性/计数/时间，未验证normal、not-found、Gateway-reject、Request Understanding/provider/input fault与presentation fault各自的安全因果DAG；
- Request Understanding persistence：Intent owner要求contextualization、actual candidates、validation/accepted/rejected refs、base/result versions与created_at；当前output/record/source、Thin Slice mapping、Application codec却没有形成logical record version与model-output version的闭环；
- P0 `get_order` source version：Memory通用字段可保持optional，但Thin Slice尚未裁决server-private唯一来源/算法；`GetOrderResult`没有version，Runtime把schema-like fallback写入Manifest，现有PersistenceGrader要求Observation/Manifest exact相等；
- Application / Infrastructure evidence boundary：Application没有expectation-free、owner-scoped、transactionally-consistent exact-Run closure DTO/Port；Infra不能直接发明该Port或跨多个session拼接`EvalEvidence`；
- Eval mapper：不存在把真实HTTP结果与Application closure映射为grader-facing `EvalEvidence`的Eval-owner实现，Request Understanding output不能由Provider capture、script或expectations补造；
- ModelProvider failure taxonomy：Thin Slice §10.3已经规定Request Understanding envelope / zero-or-multiple Function Call等协议错误为`PROVIDER_PROTOCOL_ERROR`，而Request Understanding Pydantic/source/authority/InputBinding/trusted-field拒绝为`INPUT_INVALID`；当前Scripted Provider让`ValidationError`逃逸，Qwen Adapter把它与协议错误一起折叠为`ProviderProtocolError`，Runtime也没有可安全捕获的独立bounded signal，两个现有invalid-RU script不能通过real SUT形成canonical结果；
- credentialed Qwen：Adapter与zero-network preflight已存在，但没有消费real SUT的独立runner。

因此先从`8544137...`签发插入式Plan 01-07B，只允许Harness/Grader/Scripted Provider及三份对应tests修改，关闭closed execution input/output、zero-argument non-semantic nonce correlation、actual mismatch与variant-scoped safety-causal Trace gaps。01-07B reviewed merge后，后续ownership与barrier只由下列唯一、可机械解析的execution map表达；周围prose不维护第二套Packet顺序或allowlist。

<!-- P0-RU-V2-EXECUTION-MAP:START -->
```json
{
  "manifest_version": "p0-ru-v2-execution-map-r7",
  "canonical_input": {
    "owner_path": "docs/implementation/e2e01-thin-slice-implementation-spec.md",
    "manifest_version": "p0-ru-v2-cutover-r1",
    "stages": [
      "CORE_EXPAND",
      "CODEC_EXPAND",
      "DEPENDENCY_EXPAND",
      "ACTIVE_SWITCH",
      "CONTRACT"
    ]
  },
  "lineage": {
    "root_barrier": "B_DH",
    "root_sha": "4a7e802e8aebc54e0582a1e4d99f140b56e7b131",
    "remediation_packet": "01-07N",
    "remediation_merge_sha": "a4b1edb4c50a2e3e826571194bac58f7b31eab6d",
    "alignment_packet": "01-07O",
    "active_switch_preflight_remediation": {
      "status": "CONFIRMED_BLOCKER_MAPPED_TO_THREE_PACKETS",
      "input_barrier": "B_Q",
      "input_sha": "2b9fde6f0e09308a53b86a4929ea3b639660f82e",
      "input_tree": "a68738b62695593a114c816cab2264b670494537",
      "blocking_finding": "01-07J four-file Runtime ownership cannot turn a successful ModelProviderV2 output into a canonical v2 durable initial graph because deterministic v2 reduction, Application v2 write commands and Ports, and the PostgreSQL v2 atomic writer are absent",
      "preserves_existing_packet_ids": true,
      "added_packets": [
        "01-07Y",
        "01-07Z",
        "01-07AA"
      ],
      "denominator_delta": 3,
      "feature_base_rule": "01-07Y-and-01-07Z-use-exact-B_Q-not-the-execution-owner-remediation-merge"
    },
    "contract_closure_preflight_remediation": {
      "status": "CONFIRMED_X_ALLOWLIST_GAP",
      "input_barrier": "B_SU",
      "input_sha": "f037582446598512a0132a90504e24b5d701c0f6",
      "input_tree": "4d9eb4b419301cd6b4ec7b272ca6f4bc0290f7cd",
      "blocking_finding": "01-07X three-file ownership omits the AA-owned integration tests that directly call and intentionally preserve the legacy PostgreSQL writer; deleting that writer inside the old allowlist would make the canonical full gate fail or force an out-of-scope test change",
      "preserves_packet_id": true,
      "denominator_delta": 0,
      "added_owned_files": [
        "tests/integration/test_postgres_v2_request_understanding_writes.py"
      ],
      "feature_base_rule": "01-07X-uses-exact-B_SU-not-the-execution-owner-remediation-or-plan-merge"
    },
    "codec_contract_preflight_remediation": {
      "status": "CONFIRMED_PHYSICAL_CATALOG_OWNERSHIP_GAP",
      "input_barrier": "B_X",
      "input_sha": "9e8c70db39786b35c1ebea5070a32a1bc36e0df7",
      "input_tree": "4b01798be73c15ae0b3eda42483078cbd7cdf7dc",
      "blocking_finding": "01-07T cannot reduce the Application executable catalog from 18 pairs to 17 inside its two-file ownership because Infrastructure SQLAlchemy metadata imports that catalog to generate the physical check constraint while migration 0003 must continue admitting both RU-v1 and RU-v2 physical rows",
      "remediation_packet": "01-07T-PHYSICAL-HANDOFF",
      "output_barrier": "B_T_PHYSICAL_HANDOFF",
      "preserves_packet_id": true,
      "preserved_product_packet_id": "01-07T",
      "denominator_delta": 0,
      "physical_pair_count": 18,
      "application_current_pair_count_after_01_07T": 17,
      "feature_base_rule": "01-07T-uses-exact-B_T_PHYSICAL_HANDOFF-not-B_X-or-the-plan-merge"
    },
    "core_contract_preflight_remediation": {
      "status": "CONFIRMED_EVAL_CONSUMER_OWNERSHIP_GAP",
      "input_barrier": "B_W",
      "input_sha": "556ab06cedccabc5e862647570a47adecab33b90",
      "input_tree": "f28f7f18376917ccaac4a79279546e1261248582",
      "blocking_finding": "01-07V Core ownership cannot delete RequestUnderstandingOutput v1 while tests/component/evaluation/test_e2e01_artifact_consistency.py still directly imports and constructs that v1 DTO in an Eval-owner stale-state contract case",
      "remediation_packet": "01-07V-EVAL-HANDOFF",
      "output_barrier": "B_V_READY",
      "preserves_packet_id": true,
      "preserved_product_packet_id": "01-07V",
      "denominator_delta": 0,
      "owned_files": [
        "tests/component/evaluation/test_e2e01_artifact_consistency.py"
      ],
      "feature_base_rule": "01-07V-EVAL-HANDOFF-uses-exact-B_W-not-the-execution-owner-or-plan-merge"
    },
    "qwen_runner_preflight_remediation": {
      "status": "REMEDIATION_COMPLETED",
      "input_barrier": "B_01_08",
      "input_sha": "b8a2cf3efb16138e63769b75aa4950cfec0fae28",
      "input_tree": "584e5bb2ff7e86e4851a87b3d7af0a29b984f59f",
      "blocking_finding": "01-08A Eval ownership cannot connect the reviewed QwenResponsesAdapterV2 to the real HTTP Runtime because OfflineE2E01Composition deliberately exposes only a ScriptedModelProviderV2 execution seam and the Composition Root is an Integrator-owned single-writer boundary",
      "remediation_packet": "01-08A-COMPOSITION-HANDOFF",
      "output_barrier": "B_01_08A_COMPOSITION",
      "output_sha": "c59eaea8bac2b25cc936eb2f47af15b6da1d2595",
      "output_tree": "35cbfd56da031d3e339f7d8060faf7aa70b60d2f",
      "preserves_product_packet_id": true,
      "preserved_product_packet_id": "01-08A",
      "denominator_delta": 0,
      "owned_files": [
        "src/mini_agent/bootstrap.py",
        "tests/integration/test_offline_composition_root.py"
      ],
      "feature_base_rule": "01-08A-COMPOSITION-HANDOFF-uses-exact-B_01_08-not-the-execution-owner-or-plan-merge"
    }
  },
  "pre_core_status_chain": [
    {
      "gate": "B_O_PLANNING_STATUS",
      "writer": "planning-status sole writer",
      "owned_files": [
        ".planning/PROJECT.md",
        ".planning/REQUIREMENTS.md",
        ".planning/ROADMAP.md",
        ".planning/STATE.md",
        ".planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md",
        ".planning/phases/01-cycle-1-e2e-01/01-07N-SUMMARY.md",
        ".planning/phases/01-cycle-1-e2e-01/01-07O-SUMMARY.md"
      ],
      "advances_lifecycle": false
    },
    {
      "gate": "B_O_STATUS",
      "writer": "Project Direction sole writer",
      "owned_files": [
        "PROJECT_DIRECTION.md"
      ],
      "requires": "B_O_PLANNING_STATUS",
      "advances_lifecycle": false
    }
  ],
  "stages": [
    {
      "stage": "CORE_EXPAND",
      "waves": [
        {
          "input_barrier": "B_O_STATUS",
          "output_barrier": "B_F",
          "packets": [
            {
              "packet_id": "01-07F",
              "writer": "Request Understanding Core sole writer",
              "branch": "codex/e2e01-01-ru-v2-core-expand",
              "worktree_id": "e2e01-01-ru-v2-core-expand",
              "owned_files": [
                "src/mini_agent/core/request_understanding.py",
                "src/mini_agent/core/task_state.py",
                "src/mini_agent/core/request_processing.py",
                "tests/component/core/test_request_understanding_contract.py",
                "tests/component/core/test_task_state_contract.py",
                "tests/component/core/test_request_processing.py"
              ],
              "active_routing": false,
              "protected_v1_surface": {
                "mode": "all-preexisting-top-level-definitions",
                "base_sha": "a4b1edb4c50a2e3e826571194bac58f7b31eab6d",
                "files": [
                  "src/mini_agent/core/request_understanding.py",
                  "src/mini_agent/core/task_state.py",
                  "src/mini_agent/core/request_processing.py"
                ],
                "allow_changed_existing_symbols": []
              }
            }
          ]
        }
      ]
    },
    {
      "stage": "CODEC_EXPAND",
      "waves": [
        {
          "input_barrier": "B_F",
          "output_barrier": "B_FE_EXPAND",
          "packets": [
            {
              "packet_id": "01-07E",
              "writer": "Application persistence codec sole writer",
              "branch": "codex/e2e01-01-ru-v2-codec-expand",
              "worktree_id": "e2e01-01-ru-v2-codec-expand",
              "owned_files": [
                "src/mini_agent/application/persistence.py",
                "tests/component/application/test_persistence_contract.py"
              ],
              "active_routing": false,
              "protected_v1_surface": {
                "mode": "all-preexisting-top-level-definitions",
                "base_barrier": "B_F",
                "files": [
                  "src/mini_agent/application/persistence.py"
                ],
                "allow_changed_existing_symbols": []
              }
            }
          ]
        }
      ]
    },
    {
      "stage": "DEPENDENCY_EXPAND",
      "waves": [
        {
          "input_barrier": "B_FE_EXPAND",
          "output_barrier": "B_IP",
          "packets": [
            {
              "packet_id": "01-07I",
              "writer": "Application Port declaration sole writer",
              "branch": "codex/e2e01-01-exact-run-evidence-port",
              "worktree_id": "e2e01-01-exact-run-evidence-port",
              "owned_files": [
                "src/mini_agent/application/records.py",
                "src/mini_agent/application/ports.py",
                "tests/component/application/test_record_contracts.py",
                "tests/component/application/test_ports_contract.py"
              ],
              "active_routing": false,
              "completion_status": "COMPLETE_REVIEWED_MERGED",
              "reviewed_merge_sha": "b14a15d60b17eda8d8b5aed892c5d00f16005310",
              "reviewed_merge_tree": "0825efeff47730e17974ea7d65bfd3af9a58fe51"
            },
            {
              "packet_id": "01-07P",
              "writer": "Infrastructure migration-chain sole writer",
              "branch": "codex/e2e01-01-ru-v2-physical-expand-r1",
              "worktree_id": "e2e01-01-ru-v2-physical-expand-r1",
              "owned_files": [
                "alembic/versions/20260728_0003_request_understanding_v2_expand.py",
                "src/mini_agent/infrastructure/persistence/models.py",
                "tests/integration/test_database_migrations.py"
              ],
              "active_routing": false,
              "review_remediation": {
                "status": "COMPLETE_REVIEWED_MERGED",
                "preserves_packet_id": true,
                "denominator_delta": 0,
                "original_input_barrier": "B_FE_EXPAND",
                "original_branch": "codex/e2e01-01-ru-v2-physical-expand",
                "original_worktree_id": "e2e01-01-ru-v2-physical-expand",
                "original_red_sha": "e6b8e44704357892760ce3b03a6e5201342cc4cb",
                "original_green_head": "14c1abd9e81c91ee38d4324efb0f1b82e2869c17",
                "original_pr": 82,
                "original_disposition": "SUPERSEDED_DO_NOT_MERGE",
                "blocking_finding": "01-07E stage-local consumer-absence oracle rejected the already-authorized physical catalog declaration",
                "application_oracle_fix_pr": 84,
                "application_oracle_fix_merge": "0fb4d0ba5fb9d673f2d116041ce023dd367a52ec",
                "acceptance_input_barrier": "B_I_E_ORACLE_FIX",
                "acceptance_base_sha": "0fb4d0ba5fb9d673f2d116041ce023dd367a52ec",
                "acceptance_base_tree": "53f0d499fe7d62b515cf35382ec7699958bf7bb9",
                "replay_requires_original_patch_equivalence": true,
                "replay_requires_feature_and_latest_overlay_full_gate": true,
                "acceptance_plan_pr": 86,
                "acceptance_plan_merge_sha": "dd4439f1c11853a4f10bca93a6f0cba1fa7c8cdc",
                "acceptance_red_sha": "571d25e950b725a4ba968562ffa1c73b06d3b8f3",
                "acceptance_green_sha": "7521e27f12b99c9e3f5fdaa396ea784599a273c8",
                "acceptance_review_fix_sha": "5328f435fdba41a64512bc810c94a550a1e24c40",
                "acceptance_head_tree": "71d98adc548c690966631851ba18dca63ac9a766",
                "acceptance_feature_pr": 87,
                "acceptance_overlay_base_sha": "dd4439f1c11853a4f10bca93a6f0cba1fa7c8cdc",
                "acceptance_overlay_tree": "65415ff5846892f257e95d8b8bd34f50752980a2",
                "acceptance_merge_sha": "bbe14fadc0cd2e14ad35e19177b079fcab685dfc",
                "acceptance_merge_tree": "65415ff5846892f257e95d8b8bd34f50752980a2"
              }
            }
          ],
          "barrier_evidence": {
            "status": "COMPLETE_REVIEWED_MERGED",
            "barrier": "B_IP",
            "merge_sha": "bbe14fadc0cd2e14ad35e19177b079fcab685dfc",
            "merge_tree": "65415ff5846892f257e95d8b8bd34f50752980a2",
            "feature_union_from_b_fe_count": 8,
            "canonical_full_gate": "1767 passed, 1 deselected, 12 warnings",
            "test_namespace_residual": 0
          }
        },
        {
          "input_barrier": "B_IP",
          "output_barrier": "B_DEPENDENCY",
          "packets": [
            {
              "packet_id": "01-07K",
              "writer": "Infrastructure persistence/read adapter sole writer",
              "branch": "codex/e2e01-01-strict-readers",
              "worktree_id": "e2e01-01-strict-readers",
              "owned_files": [
                "src/mini_agent/infrastructure/persistence/postgres.py",
                "src/mini_agent/infrastructure/order/postgres.py",
                "tests/integration/test_postgres_record_adapters.py",
                "tests/integration/test_postgres_get_order.py"
              ],
              "active_routing": false
            },
            {
              "packet_id": "01-07L",
              "writer": "Eval Provider and mapper sole writer",
              "branch": "codex/e2e01-01-eval-mapper",
              "worktree_id": "e2e01-01-eval-mapper",
              "owned_files": [
                "src/mini_agent/evaluation/harness.py",
                "src/mini_agent/evaluation/graders.py",
                "src/mini_agent/evaluation/scripted_provider.py",
                "src/mini_agent/infrastructure/model/qwen_responses.py",
                "tests/component/evaluation/test_e2e01_artifact_consistency.py",
                "tests/component/evaluation/test_e2e01_graders.py",
                "tests/component/evaluation/test_e2e01_scripted_model_provider.py",
                "tests/component/model/test_qwen_responses_adapter.py",
                "tests/integration/evaluation/test_e2e01_offline_harness.py"
              ],
              "active_routing": false,
              "acceptance_scope": "provider-signal-and-case-free-mapper-only",
              "real_runtime_input_invalid_owner": "01-07J"
            }
          ]
        },
        {
          "input_barrier": "B_DEPENDENCY",
          "output_barrier": "B_DEPENDENCY_M",
          "packets": [
            {
              "packet_id": "01-07M",
              "writer": "Order Core contract sole writer",
              "branch": "codex/e2e01-01-order-source-version-closure",
              "worktree_id": "e2e01-01-order-source-version-closure",
              "owned_files": [
                "src/mini_agent/core/order.py",
                "tests/component/core/test_memory_trace_presentation_contract.py"
              ],
              "active_routing": false
            }
          ]
        }
      ]
    },
    {
      "stage": "ACTIVE_SWITCH",
      "waves": [
        {
          "input_barrier": "B_Q_ORACLE_FIX",
          "output_barrier": "B_Q",
          "packets": [
            {
              "packet_id": "01-07Q",
              "writer": "Application persistence codec active-switch sole writer",
              "branch": "codex/e2e01-01-ru-v2-codec-active-switch",
              "worktree_id": "e2e01-01-ru-v2-codec-active-switch",
              "owned_files": [
                "src/mini_agent/application/persistence.py",
                "tests/component/application/test_persistence_contract.py"
              ],
              "active_routing": true,
              "requires_current_v1_isolation": true,
              "preflight_remediation": {
                "status": "COMPLETE_REVIEWED_MERGED",
                "preserves_packet_id": true,
                "denominator_delta": 0,
                "original_input_barrier": "B_DEPENDENCY_M",
                "blocking_finding": "migration integration oracle cross-owned the Application active registry as permanently all-v1 and would reject the authorized Request Understanding v2 active switch",
                "migration_oracle_fix_pr": 102,
                "migration_oracle_fix_merge": "83bdd112e016850ced35ef0870b78c55bad30a77",
                "acceptance_input_barrier": "B_Q_ORACLE_FIX",
                "acceptance_base_sha": "83bdd112e016850ced35ef0870b78c55bad30a77",
                "acceptance_base_tree": "30594eaa1347f817045a66b9a405d7a38ea24cea",
                "acceptance_requires_feature_and_latest_overlay_full_gate": true
              }
            }
          ]
        },
        {
          "input_barrier": "B_Q",
          "output_barrier": "B_YZ",
          "packets": [
            {
              "packet_id": "01-07Y",
              "writer": "Request Understanding Core v2 initial-decision sole writer",
              "branch": "codex/e2e01-01-ru-v2-initial-decision",
              "worktree_id": "e2e01-01-ru-v2-initial-decision",
              "owned_files": [
                "src/mini_agent/core/request_processing.py",
                "tests/component/core/test_request_processing.py"
              ],
              "active_routing": false,
              "acceptance_requires": [
                "request-understanding-output-v2-to-canonical-v2-closure-without-v1-projection",
                "zero-or-all-reject-or-at-most-one-accepted-thin-slice-decision",
                "exact-current-message-provenance-and-keyed-candidate-decisions",
                "accepted-task-effect-task-request-unit-and-input-binding-bijection",
                "bounded-raw-free-aggregate-and-atomic-failure"
              ]
            },
            {
              "packet_id": "01-07Z",
              "writer": "Application v2 Request Understanding write-contract sole writer",
              "branch": "codex/e2e01-01-ru-v2-write-contract",
              "worktree_id": "e2e01-01-ru-v2-write-contract",
              "owned_files": [
                "src/mini_agent/application/records.py",
                "src/mini_agent/application/ports.py",
                "tests/component/application/test_record_contracts.py",
                "tests/component/application/test_ports_contract.py"
              ],
              "active_routing": false,
              "acceptance_requires": [
                "exact-v2-no-task-write-command-and-port-for-zero-or-all-reject",
                "exact-v2-initial-graph-command-and-port-for-one-accepted-task-effect",
                "owner-bound-conversation-message-run-and-closed-task-graph-preconditions",
                "no-v1-v2-union-alias-inference-fallback-or-partial-command",
                "v1-command-and-port-surface-preserved-until-01-07W"
              ]
            }
          ]
        },
        {
          "input_barrier": "B_YZ",
          "output_barrier": "B_J_READY",
          "packets": [
            {
              "packet_id": "01-07AA",
              "writer": "Infrastructure PostgreSQL v2 Request Understanding writer sole writer",
              "branch": "codex/e2e01-01-ru-v2-atomic-writer",
              "worktree_id": "e2e01-01-ru-v2-atomic-writer",
              "owned_files": [
                "src/mini_agent/infrastructure/persistence/postgres.py",
                "tests/integration/test_postgres_v2_request_understanding_writes.py"
              ],
              "active_routing": false,
              "acceptance_requires": [
                "both-exact-v2-application-write-routes-implemented",
                "explicit-request-understanding-record-p0-v2-versioned-codec-selection",
                "versioned-decode-projection-persist-and-physical-validation-chain-not-encoder-only",
                "same-owner-locked-transaction-and-zero-partial-writes",
                "current-v1-collision-owner-mismatch-and-cas-conflict-fail-closed",
                "exact-replay-preserves-record-identity-created-at-and-row-count",
                "writer-to-owner-scoped-exact-v2-reader-roundtrip",
                "v1-writer-surface-preserved-until-01-07X"
              ]
            }
          ]
        },
        {
          "input_barrier": "B_J_READY",
          "output_barrier": "B_ACTIVE",
          "packets": [
            {
              "packet_id": "01-07J",
              "writer": "Application Runtime consumer sole writer",
              "branch": "codex/e2e01-01-runtime-v2-switch",
              "worktree_id": "e2e01-01-runtime-v2-switch",
              "owned_files": [
                "src/mini_agent/application/agent_run_service.py",
                "src/mini_agent/application/read_tool_executor.py",
                "tests/component/application/test_agent_run_service.py",
                "tests/component/application/test_read_tool_executor.py",
                "tests/integration/test_agent_run_service_v2_persistence.py"
              ],
              "active_routing": true,
              "acceptance_requires": [
                "real-agent-run-service-plus-reviewed-v2-core-application-and-postgres-write-path",
                "successful-scripted-provider-v2-route-persists-v2-parent-children-and-task-effect-before-gateway",
                "actual-agent-run-service-scripted-provider-v2-postgres-exact-run-reader-roundtrip",
                "owner-scoped-authoritative-message-reload-before-v2-reduction",
                "no-runtime-use-of-v1-reducer-command-port-or-postgres-writer",
                "real-agent-run-service-plus-reviewed-01-07l-scripted-provider",
                "invalid-request-understanding-schema-to-completed-input-invalid",
                "trusted-field-override-to-completed-input-invalid",
                "provider-protocol-error-remains-provider-protocol-error",
                "no-task-request-unit-gate-decision-tool-call-or-raw-diagnostic"
              ]
            }
          ]
        }
      ]
    },
    {
      "stage": "CONTRACT",
      "waves": [
        {
          "input_barrier": "B_ACTIVE",
          "output_barrier": "B_SU",
          "packets": [
            {
              "packet_id": "01-07S",
              "writer": "Eval Provider v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-provider-contract",
              "worktree_id": "e2e01-01-ru-v1-provider-contract",
              "owned_files": [
                "src/mini_agent/evaluation/harness.py",
                "src/mini_agent/evaluation/graders.py",
                "src/mini_agent/evaluation/scripted_provider.py",
                "src/mini_agent/infrastructure/model/qwen_responses.py",
                "tests/component/evaluation/test_e2e01_artifact_consistency.py",
                "tests/component/evaluation/test_e2e01_graders.py",
                "tests/component/evaluation/test_e2e01_scripted_model_provider.py",
                "tests/component/model/test_qwen_responses_adapter.py",
                "tests/integration/evaluation/test_e2e01_offline_harness.py"
              ],
              "removes_v1_surface": true
            },
            {
              "packet_id": "01-07U",
              "writer": "Application Runtime v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-runtime-contract",
              "worktree_id": "e2e01-01-ru-v1-runtime-contract",
              "owned_files": [
                "src/mini_agent/application/agent_run_service.py",
                "src/mini_agent/application/read_tool_executor.py",
                "tests/component/application/test_agent_run_service.py",
                "tests/component/application/test_read_tool_executor.py"
              ],
              "removes_v1_surface": true
            }
          ]
        },
        {
          "input_barrier": "B_SU",
          "output_barrier": "B_X",
          "packets": [
            {
              "packet_id": "01-07X",
              "writer": "Infrastructure persistence adapter v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-infra-contract",
              "worktree_id": "e2e01-01-ru-v1-infra-contract",
              "owned_files": [
                "src/mini_agent/infrastructure/persistence/postgres.py",
                "tests/integration/test_postgres_record_adapters.py",
                "tests/integration/test_postgres_atomicity.py",
                "tests/integration/test_postgres_v2_request_understanding_writes.py"
              ],
              "removes_v1_surface": true,
              "acceptance_requires": [
                "legacy-postgres-initial-graph-writer-definition-imports-and-direct-callers-removed",
                "legacy-postgres-request-understanding-and-accepted-delta-readers-and-v1-type-imports-removed",
                "aa-v2-writer-success-conflict-atomicity-and-recovery-lock-order-evidence-preserved",
                "legacy-v2-coexistence-oracles-retired-without-weakening-v2-only-projection-gates",
                "application-v1-command-and-port-remain-isolated-until-01-07W",
                "feature-starts-from-exact-B_SU"
              ]
            }
          ]
        },
        {
          "input_barrier": "B_X",
          "output_barrier": "B_T_PHYSICAL_HANDOFF",
          "packets": [
            {
              "packet_id": "01-07T-PHYSICAL-HANDOFF",
              "writer": "Infrastructure physical codec catalog handoff sole writer",
              "branch": "codex/e2e01-01-ru-physical-catalog-handoff",
              "worktree_id": "e2e01-01-ru-physical-catalog-handoff",
              "owned_files": [
                "src/mini_agent/infrastructure/persistence/models.py",
                "tests/integration/test_database_migrations.py"
              ],
              "remediation": true,
              "removes_v1_surface": false,
              "acceptance_requires": [
                "sqlalchemy-physical-18-pair-allowset-no-longer-imports-the-application-executable-catalog",
                "migration-0003-and-physical-RU-v1-and-v2-admissibility-remain-unchanged",
                "application-catalog-may-transition-from-expanded-18-pair-to-current-17-pair-without-physical-metadata-drift",
                "no-v1-codec-dto-fallback-backfill-or-readiness-claim",
                "remediation-starts-from-exact-B_X"
              ]
            }
          ]
        },
        {
          "input_barrier": "B_T_PHYSICAL_HANDOFF",
          "output_barrier": "B_T",
          "packets": [
            {
              "packet_id": "01-07T",
              "writer": "Application persistence codec v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-codec-contract",
              "worktree_id": "e2e01-01-ru-v1-codec-contract",
              "owned_files": [
                "src/mini_agent/application/persistence.py",
                "tests/component/application/test_persistence_contract.py"
              ],
              "removes_v1_surface": true,
              "acceptance_requires": [
                "application-executable-catalog-and-active-registry-close-to-17-current-pairs",
                "RU-v1-parent-child-codec-and-generic-or-versioned-success-paths-removed",
                "16-non-RU-generic-codec-callers-preserved",
                "RU-callers-require-the-exact-versioned-v2-path",
                "physical-18-pair-allowset-remains-owned-by-Infrastructure",
                "feature-starts-from-exact-B_T_PHYSICAL_HANDOFF"
              ]
            }
          ]
        },
        {
          "input_barrier": "B_T",
          "output_barrier": "B_W",
          "packets": [
            {
              "packet_id": "01-07W",
              "writer": "Application Port and records v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-application-contract",
              "worktree_id": "e2e01-01-ru-v1-application-contract",
              "owned_files": [
                "src/mini_agent/application/records.py",
                "src/mini_agent/application/ports.py",
                "tests/component/application/test_record_contracts.py",
                "tests/component/application/test_ports_contract.py"
              ],
              "removes_v1_surface": true
            }
          ]
        },
        {
          "input_barrier": "B_W",
          "output_barrier": "B_V_READY",
          "packets": [
            {
              "packet_id": "01-07V-EVAL-HANDOFF",
              "writer": "Eval artifact consistency v1-consumer handoff sole writer",
              "branch": "codex/e2e01-01-ru-v1-eval-consumer-handoff",
              "worktree_id": "e2e01-01-ru-v1-eval-consumer-handoff",
              "owned_files": [
                "tests/component/evaluation/test_e2e01_artifact_consistency.py"
              ],
              "remediation": true,
              "removes_v1_surface": true,
              "acceptance_requires": [
                "artifact-consistency-test-no-longer-imports-or-constructs-RequestUnderstandingOutput-v1",
                "stale-new-goal-base-version-case-uses-exact-RequestUnderstandingOutputV2-schema-contextualization-and-validation-error",
                "fact-bearing-PresentationPlan-rejection-evidence-remains-unchanged",
                "no-Eval-artifact-Dataset-grader-source-or-denominator-change",
                "01-07V-Core-owned-files-remain-byte-identical",
                "remediation-starts-from-exact-B_W"
              ]
            }
          ]
        },
        {
          "input_barrier": "B_V_READY",
          "output_barrier": "B_RU_V2_CONTRACT",
          "packets": [
            {
              "packet_id": "01-07V",
              "writer": "Request Understanding Core v1-contract sole writer",
              "branch": "codex/e2e01-01-ru-v1-core-contract",
              "worktree_id": "e2e01-01-ru-v1-core-contract",
              "owned_files": [
                "src/mini_agent/core/request_understanding.py",
                "src/mini_agent/core/task_state.py",
                "src/mini_agent/core/request_processing.py",
                "tests/component/core/test_control_gateway.py",
                "tests/component/core/test_identity_contract.py",
                "tests/component/core/test_request_understanding_contract.py",
                "tests/component/core/test_task_state_contract.py",
                "tests/component/core/test_request_processing.py"
              ],
              "removes_v1_surface": true,
              "must_be_last": true,
              "acceptance_requires": [
                "Core-v1-RequestUnderstandingOutput-record-child-reducer-and-direct-consumers-removed",
                "RequestUnderstandingInput-and-all-v2-types-reducers-and-current-contracts-preserved",
                "all-non-Core-direct-v1-consumers-are-NOT_FOUND-before-feature-start",
                "feature-starts-from-exact-B_V_READY-not-B_W-or-the-execution-owner-merge"
              ]
            }
          ]
        }
      ]
    }
  ],
  "post_contract_route": {
    "input_barrier": "B_01_08",
    "input_sha": "b8a2cf3efb16138e63769b75aa4950cfec0fae28",
    "input_tree": "584e5bb2ff7e86e4851a87b3d7af0a29b984f59f",
    "waves": [
      {
        "input_barrier": "B_01_08",
        "output_barrier": "B_01_08A_COMPOSITION",
        "output_sha": "c59eaea8bac2b25cc936eb2f47af15b6da1d2595",
        "output_tree": "35cbfd56da031d3e339f7d8060faf7aa70b60d2f",
        "packets": [
          {
            "packet_id": "01-08A-COMPOSITION-HANDOFF",
            "writer": "Composition Root Integrator sole writer",
            "branch": "codex/e2e01-01-qwen-composition-handoff",
            "worktree_id": "e2e01-01-qwen-composition-handoff",
            "owned_files": [
              "src/mini_agent/bootstrap.py",
              "tests/integration/test_offline_composition_root.py"
            ],
            "remediation": true,
            "denominator_delta": 0,
            "acceptance_requires": [
              "existing-offline-scripted-provider-execution-contract-remains-exact-and-unchanged",
              "new-qwen-execution-seam-accepts-only-QwenResponsesAdapterV2-and-no-runtime-fault-directive",
              "qwen-provider-lane-is-qwen_baseline-and-each-case-receives-a-distinct-injected-adapter-and-app-service",
              "qwen-http-result-uses-the-same-authenticated-owner-bound-exact-closure-and-eval-mapper",
              "no-global-provider-client-credential-read-or-network-owned-by-composition",
              "mock-transport-integration-proves-real-http-runtime-postgres-evidence-with-zero-external-network",
              "feature-starts-from-exact-B_01_08-not-the-execution-owner-or-plan-merge"
            ]
          }
        ]
      },
      {
        "input_barrier": "B_01_08A_COMPOSITION",
        "input_sha": "c59eaea8bac2b25cc936eb2f47af15b6da1d2595",
        "input_tree": "35cbfd56da031d3e339f7d8060faf7aa70b60d2f",
        "output_barrier": "B_01_08A",
        "output_sha": "11d6d0886d34a64b37ca34b0cfbc1aa1434b3044",
        "output_tree": "2814fdccb79a6739b33156a4ca13e104ea64daf2",
        "packets": [
          {
            "packet_id": "01-08A",
            "writer": "Eval credentialed Qwen runner sole writer",
            "branch": "codex/e2e01-01-qwen-baseline-runner",
            "worktree_id": "e2e01-01-qwen-baseline-runner",
            "owned_files": [
              "src/mini_agent/evaluation/harness.py",
              "tests/integration/evaluation/test_e2e01_offline_harness.py",
              "tests/baseline/test_qwen_baseline.py"
            ],
            "acceptance_requires": [
              "runner-connects-only-reviewed-QwenResponsesAdapterV2-to-reviewed-composition-qwen-seam",
              "each-case-uses-a-distinct-injected-qwen-adapter-with-no-global-client-or-provider",
              "case-and-script-expectations-remain-authenticated-harness-only-and-never-enter-the-provider-or-sut-input",
              "missing-DASHSCOPE_API_KEY-or-DASHSCOPE_BASE_URL-persists-empty-NOT_RUN-and-performs-zero-network",
              "credential-complete-path-runs-only-under-explicit-qwen_baseline-marker",
              "qwen-results-remain-informational-and-do-not-define-an-ordinary-pass-rate-release-gate",
              "no-failure-taxonomy-artifact-grader-threshold-lifecycle-or-composition-change",
              "feature-starts-from-exact-B_01_08A_COMPOSITION-not-the-execution-owner-or-plan-merge"
            ]
          }
        ]
      }
    ],
    "output_barrier": "B_01_08A",
    "output_sha": "11d6d0886d34a64b37ca34b0cfbc1aa1434b3044",
    "output_tree": "2814fdccb79a6739b33156a4ca13e104ea64daf2",
    "denominator_delta": 0,
    "credential_state_at_preflight": "MISSING_REQUIRED_ENV",
    "missing_credential_outcome": "NOT_RUN_OR_PYTEST_SKIPPED_WITH_ZERO_NETWORK"
  },
  "serial_order": [
    "01-07F",
    "01-07E",
    "01-07I+01-07P",
    "01-07K+01-07L",
    "01-07M",
    "01-07Q",
    "01-07Y+01-07Z",
    "01-07AA",
    "01-07J",
    "01-07S+01-07U",
    "01-07X",
    "01-07T-PHYSICAL-HANDOFF",
    "01-07T",
    "01-07W",
    "01-07V-EVAL-HANDOFF",
    "01-07V"
  ],
  "denominator": {
    "previous_target": 29,
    "added_packets": [
      "01-07N",
      "01-07O",
      "01-07P",
      "01-07Q",
      "01-07S",
      "01-07T",
      "01-07U",
      "01-07V",
      "01-07W",
      "01-07X",
      "01-07Y",
      "01-07Z",
      "01-07AA"
    ],
    "target": 42,
    "conditional_packet": {
      "packet_id": "01-07R",
      "status": "INACTIVE_OWNER_RULING_REQUIRED",
      "purpose": "physical-v1-representation-retirement",
      "activation_requires_execution_map_revision": true,
      "target_if_activated": 43
    }
  },
  "barrier_nonclaims": {
    "B_FE_EXPAND": [
      "active-registry-not-switched",
      "legacy-codec-api-unchanged",
      "postgresql-not-routed-to-v2",
      "runtime-provider-eval-not-routed-to-v2",
      "v1-contract-not-removed",
      "readiness-not-proven"
    ],
    "B_Q": [
      "runtime-v2-success-path-not-routable",
      "v2-initial-decision-and-write-contracts-not-implemented",
      "postgresql-v2-writer-not-implemented",
      "b-active-not-formed",
      "readiness-not-proven"
    ],
    "B_YZ": [
      "postgresql-v2-writer-not-implemented",
      "runtime-not-routed-to-v2",
      "v1-compatibility-surface-not-removed",
      "readiness-not-proven"
    ],
    "B_J_READY": [
      "runtime-not-routed-to-v2",
      "b-active-not-formed",
      "v1-compatibility-surface-not-removed",
      "composition-root-http-eval-not-proven",
      "readiness-not-proven"
    ],
    "B_ACTIVE": [
      "scoped-e2e01-exact-one-accepted-and-defined-fault-routes-only",
      "zero-or-all-reject-runtime-user-outcome-not-routed",
      "multi-accepted-runtime-user-outcome-not-routed",
      "atomic-write-failure-redecision-or-recovery-outcome-not-routed",
      "v1-compatibility-surface-not-removed",
      "composition-root-http-eval-not-proven",
      "readiness-not-proven"
    ],
    "B_T_PHYSICAL_HANDOFF": [
      "application-executable-catalog-not-yet-closed-to-current-17-pairs",
      "application-and-core-v1-contract-not-removed",
      "historical-physical-v1-rows-not-migrated-or-deleted",
      "physical-v1-representation-retirement-01-07R-not-activated",
      "readiness-not-proven"
    ],
    "B_W": [
      "eval-artifact-consistency-v1-output-consumer-not-yet-removed",
      "core-v1-contract-not-yet-removed",
      "historical-physical-v1-rows-not-migrated-or-deleted",
      "physical-v1-representation-retirement-01-07R-not-activated",
      "composition-root-http-eval-not-proven",
      "readiness-not-proven"
    ],
    "B_V_READY": [
      "core-v1-contract-not-yet-removed",
      "historical-physical-v1-rows-not-migrated-or-deleted",
      "physical-v1-representation-retirement-01-07R-not-activated",
      "composition-root-http-eval-not-proven",
      "readiness-not-proven"
    ],
    "B_01_08": [
      "credentialed-qwen-runner-not-implemented",
      "credentialed-qwen-result-not-run",
      "canonical-case-lifecycle-owner-not-aligned",
      "canonical-product-startup-not-implemented",
      "readiness-not-proven"
    ],
    "B_01_08A_COMPOSITION": [
      "credentialed-qwen-runner-not-implemented",
      "credentialed-qwen-result-not-run",
      "canonical-case-lifecycle-owner-not-aligned",
      "canonical-product-startup-not-implemented",
      "readiness-not-proven"
    ],
    "B_01_08A": [
      "credentialed-qwen-result-not-run",
      "canonical-case-lifecycle-owner-not-aligned",
      "canonical-product-startup-not-implemented",
      "post-execution-quality-gate-not-completed",
      "readiness-not-proven"
    ]
  },
  "next_after_contract": "01-08",
  "next_after_B_01_08": "01-08A-COMPOSITION-HANDOFF",
  "next_after_B_01_08A": "POST_EXECUTION_QUALITY"
}
```
<!-- P0-RU-V2-EXECUTION-MAP:END -->

该map只拥有execution拆分，不覆盖Thin Slice、Intent、Memory、Tool、Business或Eval语义；symbolic barrier只有对应Packet完成exact-head review、latest-integration replay与串行merge后才实例化。F与E可以使用独立Worktree，但F先从status-aligned `B_O_STATUS`形成`B_F`，E只能再从reviewed `B_F`形成`B_FE_EXPAND`；两者不再从`B_DH`同base并行。`B_FE_EXPAND`仍是non-routable additive barrier，不能被解释为active registry、PostgreSQL、Runtime、Provider/Eval、v1 contract或readiness已经切换。

`p0-ru-v2-execution-map-r7`保留r6的全部42分母、physical handoff、T/W/V产品Packet ID与denominator-neutral `01-08A-COMPOSITION-HANDOFF`。handoff Plan / feature PR #155/#156从exact `B_01_08`形成`B_01_08A_COMPOSITION = c59eaea8bac2b25cc936eb2f47af15b6da1d2595`、tree `35cbfd56da031d3e339f7d8060faf7aa70b60d2f`；01-08A Plan / feature PR #157/#158再从该exact barrier形成`B_01_08A = 11d6d0886d34a64b37ca34b0cfbc1aa1434b3044`、tree `2814fdccb79a6739b33156a4ca13e104ea64daf2`。runner与latest-integration overlay均通过独立`P0/P1/P2/P3 = 0/0/0/0`审查，post-merge canonical full为`1991 passed, 1 deselected, 12 warnings`。当前环境仍缺少两项DASHSCOPE输入，显式marker只在PostgreSQL持久化三条empty `NOT_RUN`且证明零外网后`SKIPPED`；因此`B_01_08A`不包含credentialed Qwen结果、普通质量阈值、canonical lifecycle裁决、产品启动或readiness。下一 execution route 是post-execution quality gate。

01-07C / 01-07G 已从共同 execution base `3f0753f7bef87fc02f314e28fe8b07860a819701` 完成“单目标Plan → owner feature → exact-head review → latest-integration overlay → 串行merge”。01-07G planning / feature PR #48/#50形成merge `bfc63c9444ee1af204cc3806eac7e7e84fc1bb19`；01-07C原feature PR #51因review发现`run_id`与durable contextualization缺口而关闭保留，r1 Plan / feature PR #52/#53关闭问题并形成共同 barrier `B_CG = 327b39da45cdcf564609a5385d52c4264da2c669`、tree `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887`。该barrier的default full offline suite为`1493 passed, 1 deselected, 12 warnings`；Graphify受控全量重建为`3098 nodes / 16904 edges / 68 hyperedges / 135 communities`，记录`699`个dangling endpoint、`687`组directed与`713`组undirected collapse candidate、`0` missing endpoint与`0` self-loop。Status-evidence review发现Project Direction仍保留C未开始快照后，独立exact one-file owner PR #54以`0/0/0` review与1493-test full gate关闭并merge `ffcc562487be458073f4229e4f6f7b353bc8d9e0`；该证据对齐不替换`B_CG`。01-07C / 01-07G因此为`COMPLETE / EVIDENCE_INDEXED`。

01-07D / 01-07H 已完成“Plan → feature → exact-head review → latest-integration replay → 串行merge”，状态为`COMPLETE / EVIDENCE_INDEXED`：

- 01-07D Plan / feature [PR #56](https://github.com/weijie567/mini-agent/pull/56) / [PR #59](https://github.com/weijie567/mini-agent/pull/59) 形成merge `5f793fd9aa667073c0a465383459fefb979d09c4`；01-07H Plan / feature [PR #57](https://github.com/weijie567/mini-agent/pull/57) / [PR #60](https://github.com/weijie567/mini-agent/pull/60) 随后形成共同barrier `B_DH = 4a7e802e8aebc54e0582a1e4d99f140b56e7b131`、tree `a5a60292ccdf116aba4dacaaea366576e183c532`。共同barrier的完整串行suite为`1507 passed, 1 deselected, 12 warnings`；[PR #61](https://github.com/weijie567/mini-agent/pull/61) 已索引两份Summary与派生状态。
- exact `B_DH` preflight发现旧的E/F同base并行授权无法闭合nested DTO、closed rejection、provenance replay和v1/v2 cutover。01-07N Plan / owner [PR #62](https://github.com/weijie567/mini-agent/pull/62) / [PR #63](https://github.com/weijie567/mini-agent/pull/63) 已以reviewed merge `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`、tree `469e26460c1041d9ca5042d39ae9a57ded7d5442` 冻结 `p0-ru-v2-cutover-r1`；这项remediation没有实现任何Core、codec、migration或active routing。
- 01-07O Plan [PR #64](https://github.com/weijie567/mini-agent/pull/64) 的reviewed head `9d9afe6b1242667c6e71d16d6f4fae8ea2956fa8`以final `blocker/critical/major/minor = 0/0/0/0`通过，squash merge为`274178bad8796e08831dcd9204b6610c19930982`，Plan blob为`ef63e5a79b61622e3b495d3ba8d49801e3054cbe`。owner feature从exact remediation merge `a4b1edb...`执行，exact head `1fa6550ac22255a49a34e912f1e1b6d047431750`与latest-integration overlay `8d7ac2f65ad12673ba778ca6d9093415c994c878`均以final `0/0/0/0`通过；[PR #65](https://github.com/weijie567/mini-agent/pull/65) reviewed merge为`73320913a9321c52c220104f66ed295d692a0c33`、tree `359eb1961157f71e1b3cc48b50a901e831cb0be9`。
- PR #65 reviewed merge当时只解锁两道status barrier；planning-status PR #67与Project Direction PR #68随后依次形成`B_O_PLANNING_STATUS`与`B_O_STATUS = 73696a138eb13fc4a90a0f760b13865f53d08704`。01-07F Plan / feature PR #70/#71再形成`B_F = 034cf57228c4a9da4764b0c7322dc5d34652a09c`，01-07E Plan / correction / feature PR #72/#73/#74形成共同non-routable `B_FE_EXPAND = 294ada386ec160ec2a48fc8883b5a38f1880e4ba`。这些barrier与后续状态对齐均不推进canonical lifecycle；该map当时允许01-07I / 01-07P从exact `B_FE_EXPAND`启动，当前P acceptance route已由下方review-remediation lineage替换。
- 01-07I Plan / feature [PR #80](https://github.com/weijie567/mini-agent/pull/80) / [PR #83](https://github.com/weijie567/mini-agent/pull/83) 已从exact `B_FE_EXPAND`完成RED/GREEN、exact-head与latest-overlay独立`0/0/0/0`审查，并reviewed merge为`b14a15d60b17eda8d8b5aed892c5d00f16005310`、tree `0825efeff47730e17974ea7d65bfd3af9a58fe51`。01-07P Plan [PR #81](https://github.com/weijie567/mini-agent/pull/81) 与原始feature [PR #82](https://github.com/weijie567/mini-agent/pull/82) 同样从`B_FE_EXPAND`形成三文件RED `e6b8e447...` / GREEN `14c1abd...`；focused 48、database regression 119与shared dev 0003 migration通过，但full gate唯一失败于01-07E把阶段性symbol absence永久化的test oracle，故原PR #82已按`SUPERSEDED_DO_NOT_MERGE`关闭且未merge。
- dedicated Application oracle-fix [PR #84](https://github.com/weijie567/mini-agent/pull/84) 只改`tests/component/application/test_persistence_contract.py`，经四轮append-only修复在exact head `1e28b85e1bbf3b0f85561092d6e639b2ffaebfa2`取得独立`CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`；pre-P full为`1759 passed, 1 deselected`，叠加原P patch后focused 48、database 119与full `1767 passed, 1 deselected`。reviewed merge `0fb4d0ba5fb9d673f2d116041ce023dd367a52ec`、tree `53f0d499fe7d62b515cf35382ec7699958bf7bb9`命名为review-remediation replay base `B_I_E_ORACLE_FIX`，不新增Packet或改变39分母。
- canonical execution-owner remediation [PR #85](https://github.com/weijie567/mini-agent/pull/85) 与r1 Plan [PR #86](https://github.com/weijie567/mini-agent/pull/86) 依次把同一01-07P Packet的acceptance route固定为exact `B_I_E_ORACLE_FIX`，不增加Wave 21依赖或第40个Packet。replacement [PR #87](https://github.com/weijie567/mini-agent/pull/87) 形成fresh RED `571d25e...` / GREEN `7521e27...`，GREEN patch SHA-256精确等于原始`4e85ed...`；首轮review发现downgrade lock oracle可绕过后，以append-only `5328f435fdba41a64512bc810c94a550a1e24c40`修复并取得feature/latest-overlay独立`0/0/0/0`。
- 01-07P feature与基于Plan merge `dd4439f1c11853a4f10bca93a6f0cba1fa7c8cdc`的latest overlay均通过focused 48、database regression 119与full `1767 passed, 1 deselected, 12 warnings`；overlay tree `65415ff5846892f257e95d8b8bd34f50752980a2`经review后由PR #87串行merge为`B_IP = bbe14fadc0cd2e14ad35e19177b079fcab685dfc`，merge tree保持相同。exact barrier再次通过canonical full gate，且`B_FE_EXPAND...B_IP`的source/test/infra union恰为I四文件、P三文件与oracle-fix一文件共8项。该完成证据只证明01-07I/P dependency-expand，不把原full失败改写为通过，也不声称active routing、Runtime/Provider/Eval或产品readiness已完成。
- 01-07K Plan / feature [PR #94](https://github.com/weijie567/mini-agent/pull/94) / [PR #96](https://github.com/weijie567/mini-agent/pull/96) reviewed merge为`27d084a9eeacb4c3819b94df16e8922927fd2888`；01-07L Plan / security amendment / feature [PR #95](https://github.com/weijie567/mini-agent/pull/95) / [PR #97](https://github.com/weijie567/mini-agent/pull/97) / [PR #98](https://github.com/weijie567/mini-agent/pull/98) reviewed merge为`e54a6a4d77208695440c2caf03c3ab32f9d37108`，形成exact `B_DEPENDENCY`、tree `0a1b159c4a272d4c78cb708abddcebe4f60f0ce0`。K/L从同一`B_IP`使用互斥ownership实现并由Integrator串行merge；该barrier不包含Core closure或active switch。
- 01-07M Plan / Plan-shell correction / feature [PR #99](https://github.com/weijie567/mini-agent/pull/99) / [PR #100](https://github.com/weijie567/mini-agent/pull/100) / [PR #101](https://github.com/weijie567/mini-agent/pull/101) 从exact `B_DEPENDENCY`完成两文件Core closure、exact-head与latest-overlay独立`0/0/0/0`审查，并reviewed merge为`B_DEPENDENCY_M = 42fa2ec7ef1a61a2edfd78d69ca4e6a5d32aa1c3`、tree `d8530e665333a6dbc6f8ea53f909dfc3f909d7e6`；canonical full gate为`1901 passed, 1 deselected, 12 warnings`。该barrier只解锁01-07Q，不执行Application active codec或Runtime switch。
- 01-07Q preflight在exact `B_DEPENDENCY_M`发现migration integration test把Application active registry跨owner冻结为17项全v1；Q两文件合法切换后会被该非owned oracle错误阻断。dedicated migration-oracle fix [PR #102](https://github.com/weijie567/mini-agent/pull/102) 只改`tests/integration/test_database_migrations.py`，移除该跨owner断言，同时保留17个physical codes、18个expanded pairs、catalog、downgrade fail-closed/locking与migration-chain门禁；exact head `17285fdf3e99a4d41dbb6932d2fcc200e0418f99`经独立`0/0/0/0`审查，focused migration为`48 passed`、full为`1901 passed, 1 deselected, 12 warnings`。reviewed merge `B_Q_ORACLE_FIX = 83bdd112e016850ced35ef0870b78c55bad30a77`、tree `30594eaa1347f817045a66b9a405d7a38ea24cea`只修正quality-gate ownership；它保留01-07Q Packet、branch/worktree、两文件allowlist和39分母，不实现active switch。
- 01-07Q Plan / category amendment / feature [PR #104](https://github.com/weijie567/mini-agent/pull/104) / [PR #105](https://github.com/weijie567/mini-agent/pull/105) / [PR #106](https://github.com/weijie567/mini-agent/pull/106) 已完成codec public active mapping、legacy-v1 isolation、exact-head与latest-overlay独立`0/0/0/0`审查，并reviewed merge为exact `B_Q = 2b9fde6f0e09308a53b86a4929ea3b639660f82e`、tree `a68738b62695593a114c816cab2264b670494537`。B_Q focused codec为233、K isolation为50、migration为48，canonical full为`1901 passed, 1 deselected, 12 warnings`；该barrier仍不表示Runtime v2成功路径或PostgreSQL v2 initial graph已经可达。
- exact B_Q的J preflight以实际`ScriptedModelProviderV2` success确认现有Runtime仍把`RequestUnderstandingOutputV2`交给exact-v1 reducer并形成`COMPLETED / INPUT_INVALID`；Application原子命令/Port和PostgreSQL initial-graph writer也仍是v1-only。两份独立只读ownership review均判定J四文件allowlist无法合法形成`B_ACTIVE`，且v2→v1 projection、union、alias、fallback或只让negative scripts通过均违反canonical contract。因此r2新增01-07Y / 01-07Z / 01-07AA并把目标分母从39修正为42；该execution-owner remediation不实现三项依赖或Runtime routing。
- 用户已明确要求暂时停用Graphify；后续不运行或引用Graphify，也不再把其freshness作为status、F/E或共同barrier的门禁。历史Graphify输出只保留为既有ignored artifact，不参与当前完成结论。

- 01-07I以Application Port declaration owner身份同时冻结exact-Run Evidence Port和fresh parameterless、raw-diagnostic-free的Request Understanding candidate-invalid signal；`ModelProvider`合同明确只有Request Understanding output的Pydantic/trusted-field拒绝使用该signal，framing/transport/zero-or-multiple/wrong-call及Presentation校验仍使用fresh `ProviderProtocolError`。建议精确owner files为`src/mini_agent/application/records.py`、`src/mini_agent/application/ports.py`及现有records/ports contract tests；它不得实现Runtime catch或Adapter。
- 01-07H只做additive expand：增加optional且present时strict-pattern的`GetOrderResult.source_version`，non-FOUND继续禁止；它不得在01-07K producer前拒绝legacy `FOUND + None`，也不得声称final matrix已完成。相关FOUND test stubs可在其精确allowlist内前置迁移为显式合法test token，但test token不构成authority。
- 01-07Y由Core owner从`RequestUnderstandingOutputV2`产生确定性candidate decision、真实Task effect、InputBinding、Task / RequestUnit和quote-free `RequestUnderstandingClosureV2`。它必须保存0..n actual candidates及keyed ACCEPT/REJECT，P0 scoped active decision只能形成零个或一个accepted child；zero/all-REJECT形成无Task closure，一个ACCEPT形成与`base=null/result=1`精确闭合的Task effect，不能把aggregate invalid伪装成REJECT或把v2投影为v1。
- 01-07Z只增加两个互斥、exact-v2 Application write contract：zero/all-REJECT的no-task closure route，以及一个ACCEPT的initial Task graph route。两个command / Port都必须绑定可信Conversation / Message / active Run root；accepted route还须闭合Task、RequestUnit、InputBinding、link与per-child Task effect。不得用optional/union command、legacy alias或Runtime dynamic probing；现有v1 command/Port只作为隔离兼容面保留到01-07W。
- 01-07AA只实现上述两个Port的PostgreSQL同事务writer：显式选择`request_understanding_record.p0.v2` versioned codec，且从decode、projection、persist、physical validation到owner closure全链使用由writer静态提供的exact expected-version map，不能只替换encoder后继续调用legacy-v1 helper，也不能从envelope/payload推断版本。它锁定owner-consistent roots，拒绝同Run current-v1 collision、owner/version/closure/CAS conflict，并以fault injection证明任一失败零写入。writer必须经01-07K exact-v2 owner-scoped reader回读；v1 writer只作为未路由兼容面保留到01-07X。AA不修改migration、Application contract、Core或Runtime。
- 01-07J只能从reviewed `B_J_READY`切换Runtime。除既有`INPUT_INVALID`职责外，它必须使用01-07Y reducer、01-07Z exact-v2 command/Port与01-07AA writer；actual `ScriptedModelProviderV2` success必须先通过现有owner-scoped Conversation Port重读authoritative Message，再在Gateway前持久化v2 parent/children/Task effect，active path不得把caller `command.message`当作第二个authority，也不得再引用v1 reducer/command/Port/writer。J还须在任何Observation/Manifest前把缺失、空、坏格式或不可用source version的FOUND映射为bounded SYSTEM_FAILURE；不得fallback、重算、retry或创建半成品Evidence。只在Runtime的`propose_next_move`边界消费01-07I signal并形成`COMPLETED / INPUT_INVALID`，不得直接catch raw `pydantic.ValidationError`、`ValueError`或`Exception`，不得记录raw diagnostics，也不得创建Task / RequestUnit / GateDecision / ToolCall；`ProviderProtocolError`仍映射`PROVIDER_PROTOCOL_ERROR`。J必须使用实际`AgentRunService + reviewed 01-07L Scripted Provider`分别运行`invalid-request-understanding-schema`与`trusted-field-override`，证明两者形成`COMPLETED / INPUT_INVALID`且没有Task / RequestUnit / GateDecision / ToolCall或raw diagnostic，同时以真实Runtime回归证明protocol fault仍形成`PROVIDER_PROTOCOL_ERROR`。除Component tests外，J必须用actual Scripted Provider V2 + AgentRunService + PostgreSQL Adapter + exact-Run reader的integration oracle证明正常exact-one success路径只写RU-v2且闭合owner graph；该oracle不能由RuntimeSpy、Provider capture、script expectation或codec输出替代。Zero/all-REJECT与multi-ACCEPT的Runtime用户结果、以及atomic failure后的重裁决/恢复结果尚未由scoped outcome owner冻结，J不得自行映射；因此`B_ACTIVE`只覆盖exact-one accepted E2E01与已定义fault routes，不声明通用RU-v2产品路由完成。
- 01-07K在同一次owner-scoped PostgreSQL读取与strict safe-projection校验后生成并返回deterministic source version；不得二次查询、扩大predicate、把test/fixture/schema version当authority或放松01-07J fail-closed gate。
- 01-07L在HTTP/closure mapper之外消费01-07I signal：Scripted Provider与Qwen Adapter都只把Request Understanding output Pydantic拒绝映射为该signal，Presentation校验与transport/HTTP/JSON/zero-or-multiple/wrong-name继续映射`ProviderProtocolError`，并清除raw exception cause/context。L必须在Provider Component层分别证明`invalid-request-understanding-schema`与`trusted-field-override`产生fresh 01-07I signal，并证明协议分支不漂移；Harness只可验证case-free mapper和actual-evidence contract，不得catch该signal、合成Run或把mapper fixture声称为真实Runtime `INPUT_INVALID`证据。最终两个named scripts穿过真实Runtime后形成`COMPLETED / INPUT_INVALID`的验收唯一归01-07J。其Qwen ownership沿用01-07 Plan §Task Packet Scope明确的“sole Infra path is Eval-owned Qwen ModelProvider Adapter”，不推广为通用Infrastructure/model ownership。建议消费files包括两个Provider实现、对应Component tests与必要的offline Harness test。01-07K继续只拥有strict reader/order physical adapter。
- 01-07M只在01-07K/01-07L共同barrier后由Core owner收紧`GetOrderResult.FOUND` validator为non-empty exact-pattern source version必填，保留non-FOUND prohibition并运行full suite；不得修改Infra/Runtime或把persisted historical `OrderObservation.source_version?`全局升级为required。01-07M reviewed merge前01-08保持blocked。
- I/J/L的STRIDE gate同时防止Tampering/Spoofing（Adapter不得用错误类型自行改写canonical stop classification）与Information Disclosure（signal必须fresh、parameterless，`str`/`repr`/`args`不含raw value，`__cause__`/`__context__`为`None`，Run/Trace/response不保留原始Pydantic/Provider诊断）；每个consumer test都必须分别断言分类和清除边界。
- 后续green migration、failure taxonomy、physical persistence、active switch与v1 contract closure跨越不同ownership boundary，必须逐Packet形成Plan、独立通过focused/full gate、exact-head review与串行merge。原目标29增加01-07N/O/P/Q/S/T/U/V/W/X与本次01-07Y/Z/AA后固定为42；01-07R默认inactive，只有owner裁决要求physical v1 representation retirement、先修订上述execution map时才激活并把目标变为43。任何其他新增依赖也必须先修订唯一map与分母，不得只改prose。
- 只在 `bootstrap.py` 装配具体 Adapter；01-07K拥有strict evidence reader/order-version producer、01-07L拥有HTTP/closure mapper及上述Eval-owned Provider consumers，01-08不重复实现。
- 按 Spec 第 10.1 节逐项验证完整写入门禁：
  1. 原始 `Message` 可靠保存后才运行 Request Understanding；
  2. accepted Delta、Task / RequestUnit 与 `InputBinding` 在 Gateway 接受候选前持久化；
  3. `ModelVisibleToolsetArtifact` 在应用接受 Run 前写入，且每个 `ContextManifest` 的 hash 都可解析；
  4. `GateDecision` 在 `ToolCall` 创建前写入，`ToolCall` 关联 decision、validated state version 与 binding refs；
  5. `Observation` 在第二个 `ContextManifest` 和 Presentation 模型调用前写入。
- 从 HTTP 边界运行 `E2E01-01/04`。
- 验证普通 Trace、Context Manifest 和响应不含 Runtime-private 身份或 Bob 数据。
- 产生关联 `trace_ref` 和版本 manifest 的结构化 Eval Result。
- Default offline Composition Root显式注入每Case独立的Scripted Provider；现有Scripted Provider不能作为global concurrent local app singleton。`request_understanding_output`只能来自01-07C–01-07F冻结并持久化的RU record/child closure，再由01-07K读取、01-07L映射；不能从Provider transient capture、accepted delta、script或expectations逆向合成。`trace_ref := run_id`只可作为P0 Eval bridge的opaque correlation，owner scope仍必须来自实际Session context，不能把它当作授权或伪造单一Trace record。`mini_agent.main:app`的默认local Provider不属于离线最小纵向Packet；credentialed Qwen runner只由01-08A拥有，不能从Eval fixture猜测产品运行语义。01-08A只连接并执行01-07L已经reviewed的Qwen Adapter，不得再重新定义failure taxonomy。

### W4：Post-execution 独立审查与发布门禁（不是 GSD Plan）

1. `reviewer` 只读审查安全、架构、契约漂移和测试缺口。
2. 发现由原 owner 修复，Reviewer 不越权写入。
3. 先通过默认离线 `ScriptedModelProvider` 硬门禁。
4. 真实 Qwen 配置存在时才运行 `qwen_baseline`；缺失时必须是 `SKIPPED / NOT_RUN`。
5. 只有所有 DoD 有可复现证据后，才更新 Coverage Matrix 生命周期和 `AGENTS.md` canonical 命令。

W4 是 01-01 至 01-08A 执行并集成后的 quality gate，不计入 Phase 1 的八个 numbered Plan；插入式 01-04D–01-04H、上方execution map明确列出的01-07系列Packet与01-08A只作为阻断依赖记录，不推进 lifecycle。先由 canonical Coverage Matrix owner更新 lifecycle，再由 Integrator手工同步 derived Requirements / Roadmap / State；不得调用自动 progress / completion API。

截至 2026-07-31，W4 的 code review / fix、Validation、controlled UAT、Case activation、exhaustive Result、`REGRESSION_GATE` synchronization、Eval re-audit、mandatory Security re-review、execution-plan与`.planning`派生状态同步均已完成。实现分母保持 `42/42`；当前release gate只剩`RTA-D01`用户确认，以及显式integration → `main` PR的最终合并决定。两项待决事项不是实现缺口，且完成前不推进GSD Phase completion transition。

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

最终门禁以仓库中真实出现且验证通过的配置为准，唯一 canonical 命令清单见 `AGENTS.md` 第 6 节。W1/W2、01-08 与 01-08A 已使依赖同步、根目录 Compose 数据库、migration、显式 `OfflineE2E01Composition`、real `EvalCaseSut`、PostgreSQL exact owner-scoped evidence reader 及直接 HTTP → Runtime → PostgreSQL 离线纵向 evidence 可由当前 `uv run pytest` 套件复现。六个 authenticated physical Case、manifest 与 loader 已原子进入 `REGRESSION_GATE`；默认门禁覆盖全部 16 个 authenticated variants，聚合为 `16 PASS / 0 FAIL / 0 Critical failure / 0 execution failure`。Exact security re-review barrier `22c4cfa672e7a4a91916100e9868585e6b2bcdf9` 的 canonical 串行套件为 `2007 passed, 1 deselected, 12 warnings`。Derived `CONTRACT_DEFINED` bundle 仍须在 SUT / Provider / Trace / Grader / Result 前 fail closed；上述证据不得描述成 canonical 产品启动、真实 credentialed Qwen Baseline、完整 E2E-01 / P0 或 readiness。

Credential-aware Qwen runner 及其 opt-in 命令已经实现，但默认 suite 通过 `-m "not qwen_baseline"` 排除真实外部 marker。当前环境缺少凭据时，该命令持久化空 `NOT_RUN` 后 expected skip；真实 credentialed Qwen Baseline Result 仍未运行：

```bash
uv run pytest -m qwen_baseline
```

Canonical 产品进程启动仍是后续目标；当前不得宣称下列命令可用：

```bash
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

GSD 只可作为现有协作模型上的派生编排层。W1 与 W2.0 未使用 GSD；activation feature head `957cabd6b31dd2156848acd515d2e8dc3d19bd50` 已通过双独立 exact-head review，并由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) squash merge 为 integration commit `624475681847be5a8e463e32dafd28a0483b213b`。Plan 01-01至01-04G已通过PR #11–#25完成；historical Plans 01-05/06/07通过planning PR #26发布并形成PR #28/#30/#29。受控adapter随后以PR #31/#32完成01-04H，以PR #33/#34完成01-05R，以PR #35/#36完成01-06R，在PR #29 latest overlay复验后串行合并01-07，并以PR #37/#38完成01-07A；PR #39–#41形成01-07B execution base `8544137...`。01-07B继续使用GSD planner/checker只读建议与Integrator single-writer planning-status PR，通过PR #42–#43签发并对齐状态，再由PR #44 exact six-file feature、双review与latest-integration overlay完成merge `ccdafe87...`；[01-07B Summary](../../.planning/phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md)索引精确证据。01-07C经PR #46签发、PR #49纠正公开路径、PR #52纠正review暴露的Plan缺口，并由PR #53完成r1 feature；01-07G经PR #48/#50完成Plan与feature。两者从同一execution base出发，最终共同barrier为`327b39d...`；Project Direction状态由独立owner PR #54对齐并merge `ffcc562...`，不改变execution base；[01-07C Summary](../../.planning/phases/01-cycle-1-e2e-01/01-07C-SUMMARY.md)与[01-07G Summary](../../.planning/phases/01-cycle-1-e2e-01/01-07G-SUMMARY.md)索引精确证据。01-07D / 01-07H通过Plan PR #56/#57与feature PR #59/#60完成并形成`B_DH = 4a7e802...`，PR #61索引证据；01-07N再通过Plan/owner PR #62/#63关闭cutover裁决并形成`a4b1edb...`。01-07O Plan / owner PR #64/#65已完成并形成`7332091...`；planning-status与Project Direction PR #67/#68随后形成`B_O_STATUS = 73696a1...`，01-07F Plan / feature PR #70/#71形成`B_F = 034cf57...`，01-07E Plan / correction / feature PR #72/#73/#74形成`B_FE_EXPAND = 294ada3...`。PR #75–#78已完成F/E派生状态、Project Direction、README与owner closure；I由PR #80/#83完成，P原始PR #82被review finding阻断并关闭，PR #84形成`B_I_E_ORACLE_FIX = 0fb4d0b...`，PR #85/#86固定replacement route与Plan，PR #87最终形成`B_IP = bbe14fa...`。PR #88记录I/P canonical status，PR #89/#90/#91/#92依次完成planning-status、Project Direction、README与owner closure。K由PR #94/#96完成，L由PR #95/#97/#98完成并形成`B_DEPENDENCY = e54a6a4...`；M由PR #99/#100/#101完成并形成`B_DEPENDENCY_M = 42fa2ec...`。PR #102形成Q的quality-gate replay base `B_Q_ORACLE_FIX = 83bdd11...`；Q再由Plan / category amendment / feature PR #104–#106形成exact `B_Q = 2b9fde6...`。J preflight随后确认三道跨owner依赖缺失，r2 execution-owner remediation PR #107只修订唯一map与42分母；Y/Z Plan与feature PR #108–#111串行形成`B_YZ = d704b87...`，AA及其closure/codec quality-gate remediation PR #112–#120形成`B_J_READY = b8d32d5...`，J Plan、exact-reader scope alignment与feature PR #121–#124最终形成scoped `B_ACTIVE = 7f92b5e...`。Planning-derived status、Project Direction与README PR #125–#128随后按single-writer边界索引该证据；这些status merge与本次execution-owner prose closure都不修改marker-bounded map、不创建新barrier，也不替换S/U的原exact `B_ACTIVE` feature base。Stock mutating workflow继续禁用。

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
| GitHub PR 远程流程 | `REMOTE_CONNECTED / PUBLIC / BASE_BRANCHES_PROTECTED` | `origin=https://github.com/weijie567/mini-agent.git`；D/H feature PR #59/#60形成`B_DH = 4a7e802...`，01-07N Plan/owner PR #62/#63形成remediation merge `a4b1edb...`，01-07O Plan/owner PR #64/#65形成`7332091...`；流程建立审计记录见 [PR #1](https://github.com/weijie567/mini-agent/pull/1)；两个 base branch 均要求 PR、对管理员生效并禁止 force push / deletion；当前没有 required status checks，因为 CI workflow 尚未建立 |
| GSD | `ACTIVE / EFFECTIVE / IMPLEMENTATION_42_OF_42 / QUALITY_GATES_COMPLETE / RELEASE_DECISIONS_PENDING` | activation PR #10生效；execution-map denominator保持42，全部 implementation targets 已完成；PR #172–#186完成review / fix、Validation、controlled UAT、Eval activation / Results / regression gate 与mandatory Eval / Security re-review；不调用自动 lifecycle transition |
| W1 Infra / Runtime | `OFFLINE_VERTICAL_IMPLEMENTED / PRODUCT_STARTUP_PARTIAL` | W1/W2已实现Core / Application / Runtime / Session HTTP / PostgreSQL与恢复边界；PR #153新增显式offline Composition Root与真实纵向装配；仍不含canonical产品进程入口、默认local Provider或生产外部系统接入 |
| W1 Fixture / Eval artifacts | `REGRESSION_GATE / REAL_OFFLINE_SUT_AND_QWEN_RUNNER_IMPLEMENTED` | [PR #3](https://github.com/weijie567/mini-agent/pull/3) 初始合并5个versioned JSON artifacts；PR #29实现Provider Adapter、Harness、Graders与Result/Failure machinery；PR #153装配real HTTP / Runtime / PostgreSQL Eval SUT；PR #158增加credential-aware Qwen runner；PR #184将六个 authenticated physical Case、manifest 与 loader 原子同步为`REGRESSION_GATE`；仍无credentialed Qwen Baseline Result |
| W1 集成验证 | `CONFIRMED / DEFAULT_REGRESSION_GATE` | Phase Review findings经PR #161/#162修复；PR #181–#184形成全部16 variants的默认gate、聚合Result及`REGRESSION_GATE`同步；exact security re-review barrier `22c4cfa...` 的canonical依赖同步、两个Compose health gate、Alembic与串行full为`2007 passed, 1 deselected, 12 warnings` |
| W2.0 contract freeze | `CONFIRMED / MERGED` | [PR #9](https://github.com/weijie567/mini-agent/pull/9) 已合并；integration exact head `85eb2a7fc4cc131e67e44dbba132b526e36ae6a3` |
| W2 dispatch | `RU_V2_CONTRACT_AND_01_08A_REVIEWED_MERGED / IMPLEMENTATION_42_OF_42 / QUALITY_GATES_COMPLETE` | PR #149形成`B_RU_V2_CONTRACT = 5c84e0e...`；PR #153形成`B_01_08 = b8a2cf3...`；PR #156形成`B_01_08A_COMPOSITION = c59eaea...`；PR #158形成`B_01_08A = 11d6d08...`；后续quality evidence不替换产品实现barrier |
| `E2E01-01/04` 生命周期 | `REGRESSION_GATE / LIFECYCLE_VALID_RESULTS_PRESENT` | Coverage Matrix owner经PR #178/#180激活为`EXECUTABLE`，PR #181/#182形成全部16 variants的默认gate与聚合Result，PR #183/#184完成`REGRESSION_GATE`裁决及artifact同步；controlled UAT为scoped `PASS`，但`end_user_uat = NOT_RUN` |

W0、W1、W2.0 contract freeze、GSD activation、01-07全链、RU v1 contract closure与01-08/01-08A均已有reviewed feature和post-merge证据；全部42个implementation targets已完成。Canonical Case lifecycle已由对应owner推进为`REGRESSION_GATE`，派生状态也已同步；Requirements / Phase completion transition仅因最终release决策保持锁定。本execution owner不维护第二份Case lifecycle。PR #107、01-07X preflight remediation、01-07T physical handoff remediation、01-07V Eval handoff remediation与01-08A Composition handoff route只修订execution / acceptance route；所有handoff均为denominator-neutral，不增加42 target。

PR #187–#195已按single-writer顺序对齐Business、Project Direction、Thin Slice Spec、`AGENTS.md`、Eval owners、execution plan、`.planning`派生状态与`README.md`。本次最终execution-owner收口不修改marker-bounded execution map、分母或任何Case语义；派生状态不得反向覆盖active owner。

产品实现 barrier仍是exact `B_01_08A = 11d6d0886d34a64b37ca34b0cfbc1aa1434b3044`；post-execution evidence和状态PR不替换该barrier。Current release closure只保留`RTA-D01`的最终用户风险确认与integration → `main`合并决定；mandatory Security re-review为`235 CLOSED + 1 ACCEPTED + 0 OPEN`，release用户确认尚未完成。当前缺少`DASHSCOPE_API_KEY`与`DASHSCOPE_BASE_URL`，因此实际credentialed baseline仍为`NOT_RUN / SKIPPED`，且不得把runner实现解释为credentialed Qwen结果、canonical产品启动、完整P0或readiness。
