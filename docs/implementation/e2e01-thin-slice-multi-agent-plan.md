# 第一最薄 E2E-01｜Codex 多 Agent 实施计划

更新日期：2026-07-26｜状态：`ACTIVE / EXECUTION_PLAN`｜适用范围：`E2E01-01`、`E2E01-04`｜性质：`NON_NORMATIVE` 执行消费者

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

Contract-freeze Task Packet 必须从本次 Integrator alignment PR 合并后的同一个 integration head 创建并记录精确 `base_sha`，不能在本文预填未知 SHA。它的交付必须包含类型 / Port contract tests、active owner 对照、allowlist、完整离线回归和独立 exact-head review。只有该 PR 合并后，Integrator 才能从同一精确 freeze SHA 创建三个 W2 Worktree 和 feature branch。

### W2：组件实现（并行）

`W2-RUNTIME`：

- Validator → Reducer → Registry / Gateway → Observation routing → Presentation Gate → Renderer。
- 覆盖身份覆盖、参数替换、旧版本、停止原因和错误映射。
- 只实现冻结后的 Runtime 行为；如需改变共享 DTO / Port，停止并提交 dependency request，不在本分支漂移契约。

`W2-INFRA`：

- Session / HTTP、持久化、作用域 `get_order`、安全分流和重启恢复。
- 证明 Alice 查询 Bob 与查询不存在订单时均不产生私有 Observation。
- 实现冻结 Port 的 PostgreSQL Adapter 和 migration；独占 `tests/conftest.py`、SQLAlchemy metadata、Alembic chain 与共享测试 bootstrap。

`W2-EVAL`：

- Scripted / Qwen Adapter、Harness、Graders、结构化 Eval Result 和故障注入。
- 默认离线 lane 不读取模型凭据、不访问外部网络。
- 只消费冻结 DTO / Port 与现有 PostgreSQL fixture，不修改 `tests/conftest.py`、migration、Application 或 Composition Root。

Gate：三方只通过冻结的 Port / DTO / Fixture contract 对接；不得修改其他 Workstream 的 owned files。

三个分支从同一 freeze SHA 创建并行开发；完成后仍串行集成，推荐顺序为 `W2-RUNTIME` → `W2-INFRA` → `W2-EVAL`，每次合并后后续分支都必须基于最新 integration head 重新验证并取得新的 exact-head review。

### W3：纵向集成（串行）

Owner：Integrator。

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

### W4：独立审查与发布门禁

1. `reviewer` 只读审查安全、架构、契约漂移和测试缺口。
2. 发现由原 owner 修复，Reviewer 不越权写入。
3. 先通过默认离线 `ScriptedModelProvider` 硬门禁。
4. 真实 Qwen 配置存在时才运行 `qwen_baseline`；缺失时必须是 `SKIPPED / NOT_RUN`。
5. 只有所有 DoD 有可复现证据后，才更新 Coverage Matrix 生命周期和 `AGENTS.md` canonical 命令。

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
required_checks:
  - <command and expected result>
done_when:
  - <observable acceptance condition>
handoff_to: tech-lead
handoff_format: docs/implementation/e2e01-thin-slice-multi-agent-plan.md#10-handoff-模板
```

Task Packet 未给出 `repository`、`remote`、`head_branch`、`base_branch`、`base_sha`、`worktree_id`、`owned_files`、`forbidden_files`、`dependencies`、`required_checks`、`done_when` 或 `handoff_format` 时，不启动写入 Agent。没有依赖或禁止文件时也必须显式填写 `NONE`，不得留空或由 Agent 猜测。

## 10. Handoff 模板

```text
Task / branch / commit:
Result: COMPLETE | PARTIAL | BLOCKED
Changed files:
Commands run:
Results:
Contract changes: NONE | details
Allowlist check:
Assumptions:
Unresolved risks:
Recommended merge order:
```

`COMPLETE` 只表示该 Task Packet 完成，不表示整个切片已经实现。Integrator 必须从源码和命令输出独立验证后才能更新项目状态。

## 11. GSD 使用边界

GSD 只可作为现有协作模型上的选择性编排层，当前状态保持 `PROPOSED / NOT_INITIALIZED`。W1 明确不使用 GSD，直接执行本文已经批准的 Task Packet。

### 11.1 Activation Gate（`OPEN`）

启用任何会写入 `.planning/` 的 GSD 流程前，Integrator 必须通过一个独立、串行的 activation PR：

- 建立 active owner → GSD 派生文件的显式 mapping 和 blocker conflict review；
- 裁决适用于既有项目的初始化命令，不默认运行 `$gsd-new-project`；
- 给出 `.planning/` 精确 allowlist、single-writer、phase / integration branch 映射和回滚方式；
- 在隔离 Worktree 演练初始化，证明不会覆盖 active canonical owner；
- 记录可复现验证命令，并由独立 Reviewer 对精确 head SHA 给出 `PASS`。

上述 Gate 未完成前，不运行 `$gsd-plan-phase`、`$gsd-execute-phase`、`$gsd-verify-work`、`$gsd-code-review` 或其他依赖 phase / roadmap 状态的流程，也不把它们列为 W1 required checks。

### 11.2 激活后可选使用

- 后续尚未规划的独立 phase 使用 `$gsd-plan-phase` 生成可验证计划，再由 canonical owner 审查。
- 已批准 phase 使用 `$gsd-execute-phase --wave N` 分批执行；每个写入 executor 仍必须映射到独立 Worktree、feature branch 和 PR。
- 集成后使用 `$gsd-verify-work`、`$gsd-code-review` 或安全专项技能补充 UAT、代码审查和验证证据。
- 只有真正独立、生命周期不同的 milestone 才使用 `$gsd-workstreams`；Runtime、Infra、Eval 是同一 E2E 切片的协作模块，不为它们建立三套产品 roadmap。

### 11.3 当前不使用

- 不直接运行 `$gsd-new-project`：仓库已经存在明确 canonical owner、P0 方向、Implementation Spec 和执行 Plan，重新问答生成会制造第二套项目定义。
- 不直接以默认优先级运行 `$gsd-ingest-docs`：本项目采用“专门 owner 仅在自身范围内优先”，不能让通用 `ADR > SPEC > PRD > DOC` 规则静默覆盖跨域 owner。未来如需导入，必须使用显式 manifest、owner mapping 和 blocker conflict review。
- 第一切片成为 `EXECUTABLE` 前不运行 `$gsd-autonomous`，也不让 GSD 自动修改 active canonical 文档或 Case 生命周期。

### 11.4 GitHub 映射

| GSD 对象 | GitHub / Codex 对象 |
|---|---|
| Milestone / Phase | integration branch 与最终 PR |
| Plan | 一个或多个 Task Packet |
| Wave | 一组无文件冲突的 Worktree tasks |
| Executor | feature branch 的写入 Agent |
| Verification / Review | PR checks、Reviewer findings 与可复现输出 |
| `.planning/` | Integrator 管理的派生执行状态，不拥有产品语义 |

如果后续正式启用 GSD，Integrator 是共享 `.planning/STATE.md`、Roadmap 和跨 phase 索引的 single writer；plan-scoped 文件可以通过 Task Packet 分配给独立 Agent，但不得让多个 feature branch 各自推进同一份共享状态。

## 12. 当前状态

| 项目 | 状态 | 证据 |
|---|---|---|
| Git baseline | `CONFIRMED` | baseline commit `5043043` |
| 项目级 Codex roles | `CONFIRMED` | `.codex/config.toml`、`.codex/agents/*.toml` |
| 多 Agent 执行计划 | `CONFIRMED` | 本文 |
| GitHub PR 远程流程 | `REMOTE_CONNECTED / PUBLIC / BASE_BRANCHES_PROTECTED` | `origin=https://github.com/weijie567/mini-agent.git`；`main=5d668f71b565dff9ecf353d215c41affe86cb637`，W1 integration baseline `00f09d99aa12ffa1f58a684b6f4c28ce97d82ed9`；流程建立审计记录见 [PR #1](https://github.com/weijie567/mini-agent/pull/1)；两个 base branch 均要求 PR、对管理员生效并禁止 force push / deletion；当前没有 required status checks，因为 CI workflow 尚未建立 |
| GSD | `PROPOSED / NOT_INITIALIZED` | `.planning/STATE.md` 不存在，当前为 flat mode、0 workstreams |
| W1 Infra / Runtime | `CONTRACT_IMPLEMENTED / PARTIAL` | [PR #5](https://github.com/weijie567/mini-agent/pull/5) 与 [PR #4](https://github.com/weijie567/mini-agent/pull/4) 已按序合并；存在 `src/`、`pyproject.toml`、`uv.lock`、`compose.yaml`、空业务 migration、Core / Application contracts 与 PostgreSQL namespace tests；不含完整 Adapter、HTTP 或 orchestration |
| W1 Fixture / Eval artifacts | `CONTRACT_IMPLEMENTED / CONTRACT_DEFINED` | [PR #3](https://github.com/weijie567/mini-agent/pull/3) 已双审合并；5 个 versioned JSON artifacts、20 个 focused consistency tests；尚无 Provider Adapter、Harness、Eval Result 或 Baseline |
| W1 集成验证 | `CONFIRMED` | 在仓库根目录执行 `uv sync --all-groups`、两个 Compose health gate、`uv run alembic upgrade head`、`uv run pytest` 与 `uv run pytest -n 8`；serial / xdist 均 `125 passed`，测试 namespace 清理为 0 |
| W2 dispatch | `PENDING_SERIAL_CONTRACT_FREEZE` | 必须先完成 W2.0，共享 DTO / Port / recovery / bootstrap / Composition Root ownership 冻结后才能创建并行 Worktree |
| `E2E01-01/04` 生命周期 | `CONTRACT_DEFINED` | 尚无运行证据 |

W0 与 W1 基础骨架已经完成。下一步是 W2.0 串行共享契约冻结；在其 exact-head review 与合并完成前，不派发 W2 写入任务。后续任何“可运行”“已通过”结论都必须附实际 commit、命令与输出。
