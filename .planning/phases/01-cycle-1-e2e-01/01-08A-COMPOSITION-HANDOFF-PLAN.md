---
phase: 01-cycle-1-e2e-01
plan: 01-08A-COMPOSITION-HANDOFF
type: tdd
wave: w3-qwen-composition-handoff
depends_on:
  - B_01_08
files_modified:
  - src/mini_agent/bootstrap.py
  - tests/integration/test_offline_composition_root.py
autonomous: true
requirements:
  - E2E01-01
user_setup: []
must_haves:
  truths:
    - "既有build_case_app与execute_case的ScriptedModelProviderV2 public contract、offline_gate lane及RuntimeFaultDirective行为必须保持精确不变。"
    - "新增Qwen seam只接受显式注入的exact QwenResponsesAdapterV2，不读取credential、不创建HTTP client、不访问环境变量，也不持有global Provider或app。"
    - "Qwen seam没有runtime_fault参数或故障注入入口，且每次Case执行重新创建AgentRunService与FastAPI app并使用provider_lane=qwen_baseline。"
    - "Qwen结果必须经过真实HTTP、Runtime、PostgreSQL owner-scoped exact-Run closure、ordered Trace完整值等价检查和既有Eval mapper；不得增加第二reader或从Provider输出补造Evidence。"
    - "httpx.MockTransport integration必须证明真实Qwen adapter输出可走完整本地纵向链，外部网络调用为零，认证owner authority仍只来自HTTP CustomerContext。"
    - "reviewed feature merge与post-merge canonical gate形成B_01_08A_COMPOSITION；它只解锁01-08A runner，不等于credentialed baseline已运行或Case lifecycle已推进。"
  artifacts:
    - "bootstrap.py中的exact QwenResponsesAdapterV2 per-Case injection seam。"
    - "保留既有Scripted seam的回归证据。"
    - "MockTransport Qwen→真实HTTP→Runtime→PostgreSQL→Eval integration证据。"
  key_links:
    - "B_01_08 → 01-08A-COMPOSITION-HANDOFF → B_01_08A_COMPOSITION。"
    - "injected QwenResponsesAdapterV2 → AgentRunService(provider_lane=qwen_baseline) → FastAPI HTTP → authenticated owner-bound exact closure → existing Eval mapper。"
    - "B_01_08A_COMPOSITION → 01-08A Eval-owned runner；01-08A不得以本Plan或execution-owner merge替代feature base。"
---

# Phase 1 Plan 01-08A-COMPOSITION-HANDOFF｜Qwen Composition 注入交接

> **ISSUED TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Plan 文档基于最新 integration 状态起草，但 feature 只能从原 exact `B_01_08 = b8a2cf3efb16138e63769b75aa4950cfec0fae28` 创建。PR #154 的 execution-owner merge、本 Plan merge以及任何更新的 integration SHA都不得替换 feature base。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 只落实 execution map 已批准的 denominator-neutral Composition handoff。业务、Request Understanding、Tool、Memory、Qwen Adapter、Eval与安全语义继续由 active canonical owner拥有；这里不维护第二套合同。Graphify按用户要求保持闲置。

## 目标

在不改变既有离线 Scripted SUT seam 的前提下，为 `OfflineE2E01Composition` 增加一个严格、显式、per-Case 的 `QwenResponsesAdapterV2` 注入入口。该入口只负责把已由调用方构造的 Adapter连接到现有HTTP / Runtime / PostgreSQL / exact-Run evidence / Eval mapper纵向链；credential读取、HTTP client生命周期、Case选择、baseline运行、结果编排与缺凭据处理仍属于后续Eval-owned 01-08A。

本 Packet 不实现baseline runner，不读取`DASHSCOPE_API_KEY`或`DASHSCOPE_BASE_URL`，不执行真实外部网络，不修改Harness Protocol，不推进Coverage Matrix lifecycle，也不创建canonical应用启动入口。

## Preflight evidence

- `CONFIRMED`：唯一 feature input barrier 为 exact `B_01_08 = b8a2cf3efb16138e63769b75aa4950cfec0fae28`，tree `584e5bb2ff7e86e4851a87b3d7af0a29b984f59f`。
- `CONFIRMED`：`B_01_08` 是 reviewed 01-08 feature PR #153 的 squash merge；post-merge canonical full 为 `1975 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：PR #154 merge `f7c9865def8017f50a4cdf28a7f651fd2359f9fb` 只授权执行路由；它不是 feature base。execution map明确要求先形成`B_01_08A_COMPOSITION`，再签发01-08A。
- `CONFIRMED`：`OfflineE2E01Composition.build_case_app`与`execute_case`当前对`ScriptedModelProviderV2`做exact-type校验，装配`provider_lane="offline_gate"`，并允许现有`RuntimeFaultDirective`受控测试路径。
- `CONFIRMED`：当前HTTP结果已经通过认证后绑定的`TrustedOwnerScope`读取single-snapshot exact closure，并以第二reader只确定Trace顺序；两个reader的完整Trace event值必须相等后才调用`map_exact_run_http_result_to_sut_result`。
- `CONFIRMED`：`QwenResponsesAdapterV2`已要求调用方显式注入`base_url`、`api_key`与`httpx.AsyncClient`；它不从环境变量构造自己。
- `CONFIRMED`：`tests/component/model/test_qwen_responses_adapter.py`已有`httpx.MockTransport`响应模式，可作为Integration test的非权威测试构造参考；不得复制Adapter实现或绕开真实Runtime。
- `CONFIRMED`：当前环境缺少`DASHSCOPE_API_KEY`与`DASHSCOPE_BASE_URL`。本 Packet不消费凭据，因此必须保持零外部网络，不能声称credentialed Qwen PASS。
- `OPEN / NONCLAIM`：后续01-08A如何选择Case、为每个Case创建client/Adapter、处理缺凭据并持久化`NOT_RUN`，不由本 Packet实现。
- `OPEN / NONCLAIM`：本 Packet不证明Qwen模型质量、普通pass-rate gate、全部8个Case lifecycle、完整P0或产品ready。

## Task Packet

```yaml
task_id: 01-08A-COMPOSITION-HANDOFF
goal: 为既有真实离线纵向链增加exact QwenResponsesAdapterV2 per-Case注入seam，并以MockTransport验证。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-01-qwen-composition-handoff
base_branch: integration/e2e01-thin
base_sha: b8a2cf3efb16138e63769b75aa4950cfec0fae28
base_tree: 584e5bb2ff7e86e4851a87b3d7af0a29b984f59f
worktree_id: e2e01-01-qwen-composition-handoff
agent_role: tech-lead
owned_files:
  - src/mini_agent/bootstrap.py
  - tests/integration/test_offline_composition_root.py
forbidden_files:
  - all repository files outside the exact two-file owned_files allowlist
  - tests/e2e/test_e2e01_http_eval.py
  - src/mini_agent/evaluation/**
  - src/mini_agent/infrastructure/model/qwen_responses.py
  - src/mini_agent/api/**
  - src/mini_agent/application/**
  - src/mini_agent/core/**
  - other src/mini_agent/infrastructure/**
  - other tests/**
  - tests/conftest.py
  - evals/**
  - alembic/**
  - docs/**
  - .planning/**
  - pyproject.toml
  - uv.lock
  - compose.yaml
  - AGENTS.md
  - PROJECT_DIRECTION.md
  - README.md
  - graphify-out/**
canonical_inputs:
  - AGENTS.md
  - docs/business-capabilities.md
  - PROJECT_DIRECTION.md
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
  - docs/implementation/e2e01-thin-slice-multi-agent-plan.md
  - docs/architecture/intent-design-reference.md
  - docs/architecture/tool-calling-design-reference.md
  - docs/architecture/memory-design-reference.md
  - docs/evaluation/agent-evaluation-strategy.md
  - docs/evaluation/p0-eval-coverage-matrix.md
dependencies:
  - exact B_01_08 = b8a2cf3efb16138e63769b75aa4950cfec0fae28 with post-merge canonical PASS
  - reviewed QwenResponsesAdapterV2 and existing exact Composition owner/reader/mapper chain
  - PR #154 execution route is authorization evidence only and is explicitly not the feature base
contract_changes: ADDITIVE SCOPED COMPOSITION API ONLY; add exact Qwen build/execute methods while preserving the existing Scripted public signatures and semantics byte-for-contract. No product, Provider, Eval artifact, grader, threshold or lifecycle contract changes.
security_impact: SECURITY-SENSITIVE COMPOSITION HANDOFF; preserve HTTP-authenticated owner scope as the only authority, forbid credential/env/client creation in Composition, prohibit Provider/script/response-derived Evidence and raw secret/PII persistence.
eval_impact: DENOMINATOR-NEUTRAL; add zero-external-network Qwen adapter integration evidence only. No Dataset/Case/artifact/grader/result schema/threshold/lifecycle change and no credentialed result claim.
required_checks:
  - exact base head/tree、clean branch、first feature parent、all commits、zero merge、two-file containment与range diff-check全部PASS
  - RED tests-only commit只因exact Qwen Composition public seam不存在而FAIL；既有Scripted focused tests保持PASS
  - existing build_case_app/execute_case signatures、exact Scripted type guard、offline_gate lane与RuntimeFaultDirective行为保持不变
  - Qwen public seam只接受type(adapter) is QwenResponsesAdapterV2，且API中不存在runtime_fault参数
  - 每次Qwen执行创建新的AgentRunService与FastAPI app；测试使用两个distinct adapters证明无global/retained Provider
  - MockTransport返回真实RU-v2与Presentation function envelopes，执行真实HTTP/Runtime/PostgreSQL/exact closure/mapper且外部socket connect为零
  - Qwen RunRecord provider_lane精确为qwen_baseline，结果Evidence/Trace来自owner-scoped exact closure，Trace ordering reader完整值等价仍受检
  - wrong provider、subclass、closed/reused-invalid client或projection failure均fresh bounded fail closed且不泄露credential/response payload
  - focused、existing HTTP/Runtime/evidence/Qwen Adapter neighbors、integration与full serial pytest全部PASS
  - independent exact-head review P0/P1/P2/P3 = 0/0/0/0
  - latest-integration overlay与reviewed feature的2 owned blobs及patch一致，post-merge canonical gates PASS
done_when:
  - feature从exact B_01_08启动，保留独立RED与GREEN commits，fix只追加且不越allowlist
  - existing Scripted seam对调用者与Harness保持原签名、lane、fault hook与结果投影行为
  - exact Qwen seam无credential/env/client/network ownership并拒绝所有非exact Adapter输入
  - 两次distinct MockTransport Adapter执行分别得到独立app/service/run，且均走真实owner-bound HTTP/PostgreSQL/Eval路径
  - reviewed feature串行merge且post-merge full PASS，形成唯一exact B_01_08A_COMPOSITION SHA/tree
rollback:
  - 未merge时关闭draft PR并保留RED/GREEN、review与overlay evidence
  - 已merge且01-08A未merge时普通revert本handoff并复跑全部required_checks；revert SHA不得冒充B_01_08
  - 01-08A或更下游已merge时先按严格逆依赖顺序revert下游，再revert本handoff
  - 禁止reset、force push、删除历史Worktree或清理数据库来伪造rollback
handoff_to: tech-lead
handoff_format: docs/implementation/e2e01-thin-slice-multi-agent-plan.md#10-handoff-模板
output_barrier: B_01_08A_COMPOSITION
```

## Public seam boundary

### Existing Scripted API — exact preservation

以下两个public surface必须保持参数名、类型、返回、exact-type guard、`provider_lane="offline_gate"`与fault semantics不变：

```python
def build_case_app(
    self,
    *,
    scripted_provider: ScriptedModelProviderV2,
    runtime_fault: RuntimeFaultDirective | None,
) -> FastAPI: ...

async def execute_case(
    self,
    *,
    execution_input: EvalCaseExecutionInput,
    scripted_provider: ScriptedModelProviderV2,
    runtime_fault: RuntimeFaultDirective | None,
) -> EvalCaseSutResult | None: ...
```

允许提取private common helper，但不得把public API放宽为任意Protocol、union Provider、任意lane字符串或caller-supplied hook。

### New exact Qwen API

新增两个独立public surface：

```python
def build_qwen_case_app(
    self,
    *,
    qwen_provider: QwenResponsesAdapterV2,
) -> FastAPI: ...

async def execute_qwen_case(
    self,
    *,
    execution_input: EvalCaseExecutionInput,
    qwen_provider: QwenResponsesAdapterV2,
) -> EvalCaseSutResult | None: ...
```

约束：

1. 两个入口均要求`type(qwen_provider) is QwenResponsesAdapterV2`；subclass、duck type、Scripted Provider与`None`全部fresh bounded reject。
2. Qwen API不出现`runtime_fault`、`after_revalidation_hook`、credential、base URL、client factory、Case ID、script或expectations参数。
3. `build_qwen_case_app`每次创建新的`AgentRunService`与FastAPI app，lane固定为`qwen_baseline`，hook固定为`None`。
4. `execute_qwen_case`复用与Scripted路径完全相同的session fixture lookup、ASGI HTTP request、strict `AgentRunResult` decode、HTTP-authenticated owner binding、exact closure、ordered Trace完整值等价检查和mapper。
5. Common helper必须是private、closed projection；不得新增第二套HTTP/Evidence实现，也不得把Provider内部响应、request capture或MockTransport state传给mapper。

## TDD tasks

### Task 1 — RED：冻结Qwen handoff与Scripted不回归

只修改`tests/integration/test_offline_composition_root.py`并提交tests-only RED：

- 反射确认既有`build_case_app`与`execute_case`签名不变，新Qwen API精确存在且无`runtime_fault`；
- exact Adapter type guard拒绝Scripted Provider、subclass与duck type，错误为fresh parameterless `OfflineCompositionError`；
- 使用调用方创建的`httpx.AsyncClient(MockTransport(...))`与`QwenResponsesAdapterV2`，为`E2E01-01`返回真实closed RU-v2与Presentation function envelopes；
- 禁止`socket.connect`，证明MockTransport Qwen调用后仍走真实ASGI HTTP、Runtime、PostgreSQL exact closure与既有mapper；
- 读取owner-scoped Run/Evidence确认`provider_lane == "qwen_baseline"`、RU-v2 parent/children与Observation来自真实持久化闭包；
- 两次执行使用两个distinct client/Adapter，产生distinct app/service/run且没有module-level Provider/client/credential；
- 既有startup、Scripted API、recovery与no-global测试继续通过。

RED只因`build_qwen_case_app` / `execute_qwen_case`缺失而FAIL，不得预改source或放宽旧断言。

### Task 2 — GREEN：增加closed Qwen seam

只修改`src/mini_agent/bootstrap.py`：

- 导入exact `QwenResponsesAdapterV2`；
- 保留既有public Scripted methods原签名与行为；
- 以private closed helper消除HTTP / exact closure / mapper重复；
- 增加上述两个exact Qwen public methods；
- lane在private装配内由调用入口封闭选择，外部不能传入；
- 不导入`os`，不读取env，不创建外部`httpx.AsyncClient`，不构造credential/base URL，不增加global对象。

### Task 3 — Focused hardening

只在两文件allowlist内追加修复：

- signature、exact-type/subclass、fresh bounded error与secret/payload redaction；
- MockTransport envelope调用次数和工具名闭合，禁止test直接调用Adapter后伪造SUT结果；
- Qwen与Scripted连续/交错执行不串owner scope、Run、app、service或Provider identity；
- 保持closure与ordering reader的完整Trace值相等校验；mutation必须fail closed；
- `git diff --check`、逐commit containment、邻近测试、integration与full gate。

不得通过修改Harness、Qwen Adapter、Eval artifacts、grader、Runtime、HTTP handler或Persistence来转绿。

## Verification

```bash
git diff --check
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/integration/test_offline_composition_root.py -q
uv run pytest tests/e2e/test_e2e01_http_eval.py -q
uv run pytest tests/component/model/test_qwen_responses_adapter.py -q
uv run pytest \
  tests/integration/test_http_session_adapter.py \
  tests/integration/test_agent_run_service_v2_persistence.py \
  tests/integration/test_postgres_record_adapters.py \
  tests/integration/evaluation/test_e2e01_offline_harness.py -q
uv run pytest tests/component/application -q
uv run pytest tests/component/evaluation tests/component/model -q
uv run pytest tests/integration tests/e2e -q
uv run pytest
```

机械 containment：

```bash
test "$(git rev-parse b8a2cf3efb16138e63769b75aa4950cfec0fae28^{tree})" = \
  "584e5bb2ff7e86e4851a87b3d7af0a29b984f59f"
test "$(git merge-base HEAD b8a2cf3efb16138e63769b75aa4950cfec0fae28)" = \
  "b8a2cf3efb16138e63769b75aa4950cfec0fae28"
first_feature_commit="$(git rev-list --reverse \
  b8a2cf3efb16138e63769b75aa4950cfec0fae28..HEAD | head -1)"
test "$(git rev-parse "${first_feature_commit}^")" = \
  "b8a2cf3efb16138e63769b75aa4950cfec0fae28"
git log --format='%H %P %s' \
  b8a2cf3efb16138e63769b75aa4950cfec0fae28..HEAD
test "$(git rev-list --merges \
  b8a2cf3efb16138e63769b75aa4950cfec0fae28..HEAD --count)" = "0"
git diff --check b8a2cf3efb16138e63769b75aa4950cfec0fae28...HEAD
git diff --name-only b8a2cf3efb16138e63769b75aa4950cfec0fae28...HEAD
```

Review还必须证明：

- first feature parent精确为`B_01_08`，不是PR #154 execution-owner merge、本Plan merge或其他integration head；
- 全部commits与逐commit changed-files闭合于两个文件；
- 旧Scripted public signatures与Runtime fault测试未变；
- Qwen seam无法接收credential、client factory、lane、hook、script、Case ID或expectations；
- owner scope仍只来自HTTP认证后的`CustomerContext` capture，`run_id`只作opaque correlation；
- mapper输入只由HTTP result与owner-scoped exact closure组成；
- MockTransport只替代外部Qwen HTTP endpoint，不替代本地FastAPI、Runtime、PostgreSQL reader或mapper；
- independent exact-head review为`0/0/0/0`；
- latest-integration overlay的两个owned blobs与reviewed feature相同、patch等价；post-merge full通过后才记录barrier。

## Cross-file impact

- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`已授权本handoff及其exact base/allowlist；本Plan不得修改该owner。
- Qwen Adapter、Harness和baseline tests是下游消费者或独立owner；本 Packet不修改。01-08A必须在`B_01_08A_COMPOSITION`形成后另行签发。
- 仓库级scan确认`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`docs/business-capabilities.md`、`docs/evaluation/agent-evaluation-strategy.md`、`docs/evaluation/p0-eval-coverage-matrix.md`、`.planning/PROJECT.md`、`.planning/STATE.md`、`.planning/ROADMAP.md`、`.planning/REQUIREMENTS.md`与`01-W2-VALIDATION.md`仍含“Composition Root / real SUT未实现”或“01-08A仍由01-08阻断”的旧实现快照。它们不改变本handoff的产品语义或exact base，但会让仓库状态索引落后于`B_01_08`。
- 上述active / derived status文件属于不同single-writer ownership，超出本Plan与feature allowlist；Integrator必须以独立Packet串行对齐并保留Case lifecycle `0/8`、credentialed Qwen `NOT_RUN`等nonclaim。本 Packet不得越权顺手修改，也不得提前声明baseline已运行、lifecycle已推进或产品ready。
- execution-map denominator保持42，本handoff delta为0。
- Graphify保持闲置。

## Handoff

```text
Task Packet: 01-08A-COMPOSITION-HANDOFF
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / lineage / containment:
Existing Scripted API preservation:
Qwen exact-type/no-runtime-fault seam:
Provider lane and per-Case identity:
MockTransport zero-external-network evidence:
HTTP-authenticated owner binding:
Exact-Run mapper boundary:
Contract changes:
Security impact:
Eval impact / denominator:
Latest integration overlay:
PR / merge commit:
Post-merge B_01_08A_COMPOSITION SHA / tree:
Unresolved risks:
Rollback:
Recommended next step:
```

Agent完成不等于`B_01_08A_COMPOSITION`、01-08A、credentialed Qwen PASS、Case lifecycle PASS或P0产品完成。
