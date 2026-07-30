---
phase: 01-cycle-1-e2e-01
plan: 01-08A
type: tdd
wave: w3-credentialed-qwen-baseline
depends_on:
  - B_01_08A_COMPOSITION
files_modified:
  - src/mini_agent/evaluation/harness.py
  - tests/integration/evaluation/test_e2e01_offline_harness.py
  - tests/baseline/test_qwen_baseline.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup:
  - "真实外部Qwen仅在显式pytest qwen_baseline marker且DASHSCOPE_API_KEY与DASHSCOPE_BASE_URL均存在时运行；当前环境缺失，必须NOT_RUN / SKIPPED。"
must_haves:
  truths:
    - "runner只连接reviewed QwenResponsesAdapterV2与reviewed OfflineE2E01Composition.execute_qwen_case seam，不复制或修改Composition、Adapter、Runtime、reader或mapper。"
    - "每个Case创建distinct httpx.AsyncClient、QwenResponsesAdapterV2和Composition app/service；不存在global client、Provider或credential。"
    - "Case/script expectations只留在Harness内用于认证选择、binding与grading；Qwen Adapter及SUT输入只接收真实Runtime生成的model input和closed EvalCaseExecutionInput，不接收script、case_id或expected result。"
    - "缺少任一required env时，所选Case逐个持久化empty NOT_RUN，返回非通过的既有EvalLaneRunOutcome，不创建client/Adapter且外部网络调用为零。"
    - "credential-complete的真实网络路径只存在于显式qwen_baseline marker test；默认pytest继续排除它，MockTransport runner Integration仍属于默认零外网门禁。"
    - "Qwen结果是informational baseline：不新增ordinary pass-rate阈值或release gate；Critical failure仍按既有grader/result语义记录，不伪造PASS。"
    - "reviewed feature merge与post-merge canonical gate形成B_01_08A；它不自动推进0/8 lifecycle，不证明产品ready，也不创建canonical应用启动。"
  artifacts:
    - "OfflineEvalHarness中的closed qwen_baseline orchestration入口及QwenBaselineSut Protocol。"
    - "missing-credential multi-Case NOT_RUN persistence与zero-network Integration evidence。"
    - "MockTransport all-three-Case Qwen runner evidence和marker-isolated真实credentialed entrypoint。"
  key_links:
    - "B_01_08A_COMPOSITION → 01-08A → B_01_08A。"
    - "pytest qwen_baseline → explicit env read → preflight → per-Case client/Adapter → execute_qwen_case → existing grading/persistence。"
    - "missing env → per-Case EvalResultRecord(NOT_RUN, empty evidence/usage/latency) → Postgres EvalResultPort → pytest SKIPPED。"
---

# Phase 1 Plan 01-08A｜Credentialed Qwen Baseline Runner

> **ISSUED TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Plan文档可以基于最新integration起草，但feature只能从exact `B_01_08A_COMPOSITION = c59eaea8bac2b25cc936eb2f47af15b6da1d2595`创建。本Plan merge、execution-owner/Composition Plan merge或任何更新的integration SHA都不得替换feature base。

> **DERIVED / NON_NORMATIVE**
> Qwen Adapter、Composition、业务、Request Understanding、Memory、Tool、Eval artifact/grader/result与安全语义继续由各自active owner拥有。本Plan只实现已批准的Eval runner orchestration，不维护第二套合同。Graphify按用户要求保持闲置。

## 目标

在`OfflineEvalHarness`中增加独立的`qwen_baseline`运行入口：调用方显式传入环境映射；preflight缺凭据时，在零client/零Adapter/零外网条件下为所选Case持久化empty `NOT_RUN`。凭据完整时，runner为每个Case创建独立`httpx.AsyncClient`和exact `QwenResponsesAdapterV2`，只调用reviewed Composition `execute_qwen_case`，随后复用既有Case绑定、Trace append/reload、grader、A/B安全等价和PostgreSQL Result/Failure持久化路径。

真实网络入口只放在`tests/baseline/test_qwen_baseline.py`的显式marker内。默认离线测试以`httpx.MockTransport`覆盖相同runner，但不得替代Composition真实ASGI HTTP、Runtime、PostgreSQL exact closure或mapper。

## Preflight evidence

- `CONFIRMED`：唯一feature input barrier为`B_01_08A_COMPOSITION = c59eaea8bac2b25cc936eb2f47af15b6da1d2595`，tree `35cbfd56da031d3e339f7d8060faf7aa70b60d2f`。
- `CONFIRMED`：该barrier来自reviewed feature PR #156；feature/latest overlay/post-merge full均为`1978 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：Composition已提供exact `build_qwen_case_app` / `execute_qwen_case`；Qwen路径固定`provider_lane="qwen_baseline"`、无runtime fault、credential/env/client/network ownership，并复用HTTP-authenticated owner-bound exact closure与mapper。
- `CONFIRMED`：`QwenResponsesAdapterV2`要求显式`base_url`、`api_key`与`httpx.AsyncClient`，固定模型snapshot，不读取env。
- `CONFIRMED`：`OfflineEvalHarness`当前只接受`lane="offline_gate"`，在`_stage_case`中构造`ScriptedModelProviderV2`并将其传给SUT；不能把该Provider包装后送入Qwen seam，否则script/expectations会跨越SUT边界。
- `CONFIRMED`：既有`build_qwen_baseline_preflight`和`append_qwen_not_run_record`已定义single-Case empty NOT_RUN与insert-only持久化；runner必须复用而非复制结果构造/幂等规则。
- `CONFIRMED`：qwen lane artifact包含`E2E01-01`、`E2E01-04-A`、`E2E01-04-B`，`release_gate=false`且`ordinary_pass_rate_gate=NOT_DEFINED`。
- `CONFIRMED`：当前进程环境中`DASHSCOPE_API_KEY`和`DASHSCOPE_BASE_URL`均缺失；值未读取或输出。因此本次真实marker证据只能是持久化`NOT_RUN`后`SKIPPED`，不能运行外网或声称PASS。
- `OPEN / NONCLAIM`：本Packet不定义重复采样、成本/延迟阈值、普通质量阈值、报告聚合、candidate/baseline比较或线上监控。
- `OPEN / NONCLAIM`：本Packet不修改Case lifecycle、Coverage Matrix、artifact bytes、grader语义、Runtime failure taxonomy、Composition或canonical应用启动。

## Task Packet

```yaml
task_id: 01-08A
goal: 在既有Harness与Composition/Qwen seam之间建立credential-aware、per-Case隔离、可持久化的informational baseline runner。
repository: weijie567/mini-agent
remote: origin
head_branch: codex/e2e01-01-qwen-baseline-runner
base_branch: integration/e2e01-thin
base_sha: c59eaea8bac2b25cc936eb2f47af15b6da1d2595
base_tree: 35cbfd56da031d3e339f7d8060faf7aa70b60d2f
worktree_id: e2e01-01-qwen-baseline-runner
agent_role: eval-engineer
owned_files:
  - src/mini_agent/evaluation/harness.py
  - tests/integration/evaluation/test_e2e01_offline_harness.py
  - tests/baseline/test_qwen_baseline.py
forbidden_files:
  - all repository files outside the exact three-file owned_files allowlist
  - src/mini_agent/bootstrap.py
  - src/mini_agent/infrastructure/model/qwen_responses.py
  - src/mini_agent/evaluation/artifacts.py
  - src/mini_agent/evaluation/graders.py
  - src/mini_agent/evaluation/scripted_provider.py
  - other src/mini_agent/**
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
  - exact B_01_08A_COMPOSITION = c59eaea8bac2b25cc936eb2f47af15b6da1d2595 with post-merge canonical PASS
  - reviewed QwenResponsesAdapterV2, Composition qwen seam, OfflineEvalHarness graders/ResultPort and qwen lane artifact
contract_changes: ADDITIVE EVAL ORCHESTRATION API ONLY; add QwenBaselineSut Protocol, optional qwen_sut injection and run_qwen_baseline method returning existing EvalLaneRunOutcome. Preserve offline run_lane signature/behavior, Eval artifacts, Result/Failure DTOs, graders, thresholds and lifecycle.
security_impact: SECURITY-SENSITIVE EVAL INTEGRATION; never pass case/script/expectations to Qwen Provider/SUT, never source owner identity from env/model, keep secrets local to per-Case Adapter construction, persist no credential/raw response and perform zero network before ready preflight.
eval_impact: INFORMATIONAL BASELINE RUNNER; default offline denominator and execution-map denominator remain unchanged, missing credentials persist NOT_RUN, credentialed records use qwen_baseline lane and existing graders without ordinary pass-rate release gate.
required_checks:
  - exact base head/tree、clean branch、first feature parent、all commits、zero merge、three-file containment与range diff-check全部PASS
  - RED tests-only commit只因runner/QwenBaselineSut API不存在或preflight尚未接入而FAIL；既有offline Harness与baseline preflight tests保持PASS
  - OfflineEvalHarness.run_lane public signature、offline_gate validation、Scripted provider/runtime fault路径与all existing tests精确不变
  - qwen_sut未注入或任一env缺失时，selected Case逐个insert-only持久化empty NOT_RUN；transport factory、client、Adapter、Composition execute与socket/HTTP均零调用
  - selected Case必须是qwen lane exact subset，E2E01-04 A/B仍保持paired completeness；invalid/duplicate/unknown selection在写入和network前bounded fail closed
  - credential-shaped MockTransport执行三个Case；每Casedistinct transport/client/Adapter，SUT只收到execution_input与qwen_provider且无script/case_id/expectations/runtime_fault
  - real Composition MockTransport路径产生qwen_baseline Run、owner-bound exact closure、真实RU-v2/Observation和A/B安全等价，再由现有grader/Trace/ResultPort持久化
  - Adapter/client/transport/Provider exception映射到existing SYSTEM_UNDER_TEST failure，secret/base URL/raw provider payload不进入Result/Failure/Trace
  - marker test只在显式qwen_baseline读取os env；missing path持久化NOT_RUN后pytest.skip，complete path不注入MockTransport且不以普通FAIL率阻断release
  - focused、existing offline Harness、Qwen Adapter/Composition neighbors、integration与full default serial pytest全部PASS
  - explicit missing-env marker command PASS with one SKIPPED after persisted assertions and zero network；本环境不得执行credentialed network
  - independent exact-head review P0/P1/P2/P3 = 0/0/0/0
  - latest-integration overlay与reviewed feature的3 owned blobs及patch一致，post-merge canonical gates PASS
done_when:
  - feature从exact B_01_08A_COMPOSITION启动，保留独立RED与GREEN commits，fix只追加且不越allowlist
  - missing env对default三个qwen Case持久化三个empty NOT_RUN并返回command_passed=false，未构造任何network-owned对象
  - MockTransport all-three-Case runner完成真实Composition纵向链且复用existing grading/persistence，distinct per-Case Adapter/client得到可证据化
  - 默认pytest仍零外网并排除marker，explicit missing marker如实SKIPPED；未伪造credentialed结果
  - reviewed feature串行merge且post-merge full PASS，形成唯一exact B_01_08A SHA/tree
rollback:
  - 未merge时关闭draft PR并保留RED/GREEN、review与overlay evidence
  - 已merge且无下游时普通revert本runner并复跑required checks；revert SHA不得冒充B_01_08A_COMPOSITION
  - 有下游时先按严格逆依赖顺序revert下游，再revert本runner
  - Eval Result测试记录位于隔离test namespace；不得删生产数据、reset、force push或清理共享数据库来伪造rollback
handoff_to: tech-lead
handoff_format: docs/implementation/e2e01-thin-slice-multi-agent-plan.md#10-handoff-模板
output_barrier: B_01_08A
```

## Runner design boundary

### Additive Harness API

新增`QwenBaselineSut` Protocol，只公开reviewed Composition seam的最小形状：

```python
class QwenBaselineSut(Protocol):
    async def execute_qwen_case(
        self,
        *,
        execution_input: EvalCaseExecutionInput,
        qwen_provider: QwenResponsesAdapterV2,
    ) -> EvalCaseSutResult | None: ...
```

`OfflineEvalHarness.__init__`只增加keyword-only可选`qwen_sut: QwenBaselineSut | None = None`；现有Composition `build_harness()`不传该参数时，offline行为必须逐字节兼容。新增：

```python
async def run_qwen_baseline(
    self,
    *,
    eval_run_id: UUID,
    environment: Mapping[str, str],
    attempt: int = 1,
    case_ids: Sequence[str] | None = None,
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
) -> EvalLaneRunOutcome: ...
```

调用方不能传Adapter、client、Provider lane、script、expectations、owner identity或runtime fault。runner只从authenticated artifacts选择Case/script expectations用于Harness grading；Qwen Adapter由runner以validated env和每Case新client构造。

### Preflight and NOT_RUN

1. 先closed-copy并验证`eval_run_id`、attempt、environment和Case selection；default为qwen lane三个Case，duplicate/unknown/partial A/B全部在任何写入或network前拒绝。
2. 对每个selected Case调用既有`build_qwen_baseline_preflight`。任一required env缺失或`qwen_sut=None`时，所有selected Case必须得到相同reason，并通过`append_qwen_not_run_record`逐个持久化。
3. missing path返回既有`EvalLaneRunOutcome(lane="qwen_baseline", results=<NOT_RUN records>, execution_failures=(), command_passed=False)`；不新增Result/Outcome schema。
4. preflight完成前不得调用transport factory、构造`httpx.AsyncClient`/Adapter、访问Composition或触发DNS/socket/HTTP。
5. insert conflict或existing record不等于expected record时fresh bounded command error；不得覆盖。

### Credential-complete execution

1. `run_qwen_baseline`把validated base URL/api key保存在单次调用的private frozen execution config中，不写对象字段、global、Trace、Result、Failure或日志。
2. `_run_lane_impl`只在private qwen execution config存在时接受`lane="qwen_baseline"`；public `run_lane`仍只能接受`offline_gate`。
3. `_stage_case`仍解析authenticated script以形成expectations，但qwen分支不构造`ScriptedModelProviderV2`，不生成runtime fault，也不把script/expectations传给qwen_sut或Adapter。
4. 每Case调用`transport_factory()`（测试）或使用default external HTTP transport（marker），创建新的`httpx.AsyncClient`与exact `QwenResponsesAdapterV2`；client context结束后不保留Adapter。
5. 只调用`qwen_sut.execute_qwen_case(execution_input=..., qwen_provider=...)`。其输出继续走现有execution-ref correlation、authenticated Case binding、grader、Trace callback、A/B equivalence、append-only Result/Failure。
6. transport factory、client、Adapter、Qwen或SUT异常只产生既有bounded execution failure；不得带出secret、endpoint、raw response或traceback local。

## TDD tasks

### Task 1 — RED：冻结runner、missing preflight与oracle isolation

只修改两份tests并提交tests-only RED：

- `tests/integration/evaluation/test_e2e01_offline_harness.py`
  - runner public signature和existing `run_lane` signature不回归；
  - default三Case missing-env、missing-sut分别持久化empty NOT_RUN，零transport/client/Adapter/SUT；
  - invalid/duplicate/partial A/B selection在写入/network前失败；
  - credential-shaped MockTransport使用三份distinct transport/client/Adapter；capture SUT只收到closed execution input和exact Adapter；
  - monkeypatch Scripted Provider构造为forbidden，证明qwen path不创建script Provider或runtime fault；
  - actual mismatch、A/B安全等价、Trace append/reload、Result/Failure与replay继续走既有Harness逻辑。
- `tests/baseline/test_qwen_baseline.py`
  - 升级为真实PostgreSQL Composition runner entrypoint；
  - missing env先验证三条persisted empty NOT_RUN与zero external HTTP，再`pytest.skip`；
  - complete env使用default transport，不注入MockTransport，运行后只把结果作为informational evidence；不设普通pass-rate阈值，不打印secret；
  - Critical failures与execution failures保留现有显式失败语义。

RED只能因`QwenBaselineSut` / `qwen_sut` / `run_qwen_baseline`不存在而失败；不得预改Harness source、Composition或Adapter。

### Task 2 — GREEN：实现closed baseline orchestration

只修改`src/mini_agent/evaluation/harness.py`：

- 导入`httpx`与exact `QwenResponsesAdapterV2`；
- 增加Protocol、private frozen execution config、optional constructor injection和public runner；
- 复用preflight/NOT_RUN append、selection、`_stage_case`后半段、grader、Trace与Result persistence；
- qwen分支不构造Scripted Provider，不把authenticated expectations送入SUT/Adapter；
- 保持existing offline path public signature与行为。

### Task 3 — Focused hardening

只在三文件allowlist内追加修复：

- env mapping/whitespace/URL/transport output、subclass/duck SUT与wrong Adapter path的bounded处理；
- per-Case client/Adapter identity与cleanup，即使中途失败也不复用或泄露；
- missing/preflight insert-only replay/conflict、partial result与secret/payload traceback扫描；
- explicit missing marker、focused neighbors、integration、full、containment与overlay gate。

不得修改artifact、grader、failure taxonomy、Composition、Adapter或threshold来转绿。

## Verification

```bash
git diff --check
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/integration/evaluation/test_e2e01_offline_harness.py -q
uv run pytest tests/baseline/test_qwen_baseline.py -m qwen_baseline -q
env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL \
  uv run pytest tests/baseline/test_qwen_baseline.py -m qwen_baseline -q
uv run pytest \
  tests/integration/test_offline_composition_root.py \
  tests/e2e/test_e2e01_http_eval.py \
  tests/component/model/test_qwen_responses_adapter.py -q
uv run pytest tests/component/evaluation tests/component/model -q
uv run pytest tests/integration tests/e2e -q
uv run pytest
```

当前环境禁止执行credential-complete外网命令；只有两项env均真实存在时才运行：

```bash
uv run pytest -m qwen_baseline tests/baseline/test_qwen_baseline.py -x
```

机械 containment：

```bash
test "$(git rev-parse c59eaea8bac2b25cc936eb2f47af15b6da1d2595^{tree})" = \
  "35cbfd56da031d3e339f7d8060faf7aa70b60d2f"
test "$(git merge-base HEAD c59eaea8bac2b25cc936eb2f47af15b6da1d2595)" = \
  "c59eaea8bac2b25cc936eb2f47af15b6da1d2595"
first_feature_commit="$(git rev-list --reverse \
  c59eaea8bac2b25cc936eb2f47af15b6da1d2595..HEAD | head -1)"
test "$(git rev-parse "${first_feature_commit}^")" = \
  "c59eaea8bac2b25cc936eb2f47af15b6da1d2595"
git log --format='%H %P %s' \
  c59eaea8bac2b25cc936eb2f47af15b6da1d2595..HEAD
test "$(git rev-list --merges \
  c59eaea8bac2b25cc936eb2f47af15b6da1d2595..HEAD --count)" = "0"
git diff --check c59eaea8bac2b25cc936eb2f47af15b6da1d2595...HEAD
git diff --name-only c59eaea8bac2b25cc936eb2f47af15b6da1d2595...HEAD
```

Review还必须证明：

- first feature parent精确为`B_01_08A_COMPOSITION`，不是本Plan merge或其他integration head；
- 全部commits与逐commit changed-files闭合于三个文件；
- public offline Harness签名、Scripted Provider/runtime fault与default lane behavior未变；
- missing path在构造任何network-owned对象前完成选择、NOT_RUN与insert-only persistence；
- credentialed qwen path没有把script、case_id、expectations、owner identity或runtime fault送入Provider/SUT；
- 每Casedistinct client/Adapter，default external transport只可由marker调用；
- real Composition仍是owner-bound exact closure与mapper唯一来源；
- informational result没有普通pass-rate/release gate或lifecycle claim；
- independent exact-head review为`0/0/0/0`；
- latest-integration overlay的三个owned blobs与reviewed feature相同、patch等价；post-merge full通过后才记录barrier。

## Cross-file impact

- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`已拥有本Packet exact route/allowlist/base rule；本Plan不得修改。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`已拥有`pytest -m qwen_baseline`、required env、fixed model和独立Result目标；本Packet消费而不重定义。
- `docs/evaluation/agent-evaluation-strategy.md`与Coverage Matrix继续拥有grader/lifecycle；本Packet不得推进`0/8`或定义普通阈值。
- `AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、业务/Eval owner与`.planning`状态索引仍有01-08前旧实现快照；它们属于已登记的独立single-writer alignment debt。本feature不得越界修改，Integrator须后续串行收口。
- execution-map denominator保持42，本Packet不增加Task denominator；Graphify保持闲置。

## Handoff

```text
Task Packet: 01-08A
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / lineage / containment:
Offline Harness compatibility:
Missing env / NOT_RUN persistence:
Per-Case client / Adapter identity:
Expectation isolation:
MockTransport real Composition evidence:
Explicit marker result:
Credentialed network disposition:
Contract changes:
Security impact:
Eval impact / denominator / lifecycle:
Latest integration overlay:
PR / merge commit:
Post-merge B_01_08A SHA / tree:
Unresolved risks:
Rollback:
Recommended next step:
```

Agent完成不等于`B_01_08A`、credentialed Qwen PASS、Case lifecycle PASS、canonical application startup或P0产品完成。
