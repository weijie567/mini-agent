---
phase: 01-cycle-1-e2e-01
scope: 01-05-01-07
status: complete
base_sha: c35687dafa3881bb322d91515068d8d39be79df6
created: "2026-07-27"
---

# Phase 1 W2｜Runtime / Infra / Eval Research

> **DERIVED / NON_NORMATIVE**
> 本研究只把 active canonical owner 与 exact integration base 转换为 01-05、01-06、01-07 的实现约束，不拥有产品、架构、契约、Eval Case 生命周期或发布语义。冲突时服从 `AGENTS.md` 和对应 active owner。

## 结论

`CONFIRMED`：exact integration base
`c35687dafa3881bb322d91515068d8d39be79df6` 已合并 01-04E、01-04F、01-04G，并通过 466 项完整回归、独立 review 与 post-merge Graphify gate。W2 可以在不再修改 frozen Core/Application contract、Eval artifact 或 active canonical 文档的前提下，启动三个 ownership 互斥的实现 Packet。

`DECIDED`：

1. 01-05 Runtime、01-06 Infra、01-07 Eval 都从同一个 exact base `c35687d…` 建立独立 branch / Worktree。
2. 三个 Packet 实现期并行，PR 依次按 Runtime → Infra → Eval 串行审查、重验和合并。
3. 每个 PR 在最新 integration head 上做 compatibility replay；不得把后来合并的实现静默当作自己的开发基线。
4. 01-08 独占 Composition Root、真实 Runtime/Infra/Eval wiring、HTTP E2E、PostgreSQL-backed Eval、启动恢复 readiness 与 lifecycle 证据。
5. `QwenResponsesAdapter` 属于 active execution owner 明确分配给 01-07 的实现范围，必须在该 Packet 以现有 `httpx`、mock transport Component tests 和 conditional `qwen_baseline` test落地；不新增 dependency。默认 pytest 继续排除该 marker。真实网络 Baseline 只在 W4 检测到 `DASHSCOPE_API_KEY` 与 `DASHSCOPE_BASE_URL` 时运行；缺失时按 canonical `SKIPPED / NOT_RUN`，它不是离线 release gate。
6. `ordinary_trace_shape` 的本轮安全比较只允许有序 event type、次数和 allowlisted stable status / reason；不得带 ID、订单值、原始 payload 或其他私有事实。若后续要升级为外部契约，先回到 canonical owner 裁决。

## Canonical 输入

- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `docs/business-capabilities.md`
- `docs/architecture/intent-design-reference.md`
- `docs/architecture/tool-calling-design-reference.md`
- `docs/architecture/memory-design-reference.md`
- `docs/evaluation/agent-evaluation-strategy.md`
- `docs/evaluation/p0-eval-coverage-matrix.md`
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`
- 已合并的 01-04D/E/F/G Plan、Summary、源码和测试

研究不得把这些 owner 的内容复制为第二套规范；下列物理文件拆分均为 `INFERRED` 实现建议，只有经 planning PR 合并后才成为 Task Packet allowlist。

## Cross-stream Ownership

| Packet | 唯一 writer 范围 | 不拥有 |
|---|---|---|
| 01-05 Runtime | 新增 Core 纯决策、Application 编排、Component tests | frozen DTO/Port/codec、HTTP、PostgreSQL、Eval artifact/Harness、Composition Root |
| 01-06 Infra | Session / HTTP adapter、PostgreSQL records / recovery / `get_order`、migration、Infra tests | Runtime loop、Eval Harness、canonical docs、Composition Root |
| 01-07 Eval | versioned loader、Scripted / Qwen Provider、13 graders、offline Harness、conditional baseline tests | 五个 JSON artifact、Runtime/Infra（Qwen Adapter精确例外除外）、真实 E2E wiring、凭据、lifecycle |
| 01-08 Integrator | Composition Root、local fixture assembly、真实纵向 wiring与最终证据 | 不反向重定义任何 frozen owner |

三个 W2 allowlist 无文件交集。`pyproject.toml`、`uv.lock`、`tests/conftest.py`、active docs、`.planning/**` 与 Composition Root 均不属于任一并行 writer。

## 01-05 Runtime

### Exact Packet Candidate

- branch: `codex/e2e01-w2-runtime`
- worktree: `/Users/ming/projects/mini-agent-worktrees/e2e01-w2-runtime`
- base: `c35687dafa3881bb322d91515068d8d39be79df6`
- contract changes: `NONE`
- new dependencies: `NONE`

建议只新增：

```text
src/mini_agent/core/request_processing.py
src/mini_agent/core/control_gateway.py
src/mini_agent/core/presentation_policy.py
src/mini_agent/application/agent_run_service.py
src/mini_agent/application/read_tool_executor.py
src/mini_agent/application/deterministic_renderer.py
src/mini_agent/application/restart_recovery_service.py
tests/component/core/test_request_processing.py
tests/component/core/test_control_gateway.py
tests/component/core/test_presentation_policy.py
tests/component/application/test_agent_run_service.py
tests/component/application/test_read_tool_executor.py
tests/component/application/test_deterministic_renderer.py
tests/component/application/test_restart_recovery_service.py
```

冻结文件包括现有 `src/mini_agent/core/**` 与
`src/mini_agent/application/{ports,records,persistence}.py`、所有 Infra / Eval / integration test、artifact、docs、planning、dependency、migration 与 Composition Root 文件。上面三个新增 Core 文件是 allowlist 例外，不得借 glob 修改其他 Core。

### 必须证明的行为

1. trusted `CustomerContext` 先形成 owner scope；message / model 不能生成或覆盖 `customer_id`。
2. 新 Conversation、USER Message、Run `CREATED → RUNNING`、toolset artifact 与第一份 Context Manifest 的 happens-before 顺序可见。
3. Provider 候选经 deterministic validation、Reducer、`InputBinding`、current-state revalidation 和 Control Gateway 后才可能产生 ToolCall。
4. 在 revalidation 与 Gate 之间提供默认 no-op、仅供测试注入的 `AFTER_REVALIDATION_BEFORE_GATE` seam。
5. `get_order` 只从 current binding 构造参数；durable ToolCall dispatch fence `APPLIED` 必须发生在唯一一次 order read 之前。
6. FOUND 保存安全 Observation；foreign / nonexistent 使用同一固定安全响应，零 Observation、零 presentation call。
7. presentation plan 保持 fact-free；deterministic renderer 只从安全 Observation 注入事实。
8. 成功路径恰有 2 次 model call、1 次 ToolCall、1 次 order read、1 个 Observation，Task / RequestUnit `ACTIVE/v1 → COMPLETED/v2`。
9. unknown tool 为 Gateway rejection，零 ToolCall/read/Observation；stale fault 为 canonical
   `ACTIVE/v1 → WAITING_USER/v2 → BLOCKED/v3`。
10. exact usage 不可得时构造 required `TokenCounts(input_tokens=None, output_tokens=None)`，不得填 `0` 或估算。
11. restart recovery 只构造 1–3 个 exact Core TraceEvent 并调用
    `claim_and_apply_restart_recovery()`；不 resume model、不重放 Tool。ACTION reconciliation 阻断 readiness。

Runtime 的私有 `clock`、UUID factory 与 fault hook 可以构造注入，但不得新增共享 Port。

## 01-06 Infrastructure

### Exact Packet Candidate

- branch: `codex/e2e01-w2-infra`
- worktree: `/Users/ming/projects/mini-agent-worktrees/e2e01-w2-infra`
- base: `c35687dafa3881bb322d91515068d8d39be79df6`
- contract changes: `NONE`
- new dependencies: `NONE`

建议 allowlist：

```text
src/mini_agent/api/http.py
src/mini_agent/infrastructure/auth/p0_session.py
src/mini_agent/infrastructure/order/postgres.py
src/mini_agent/infrastructure/persistence/models.py
src/mini_agent/infrastructure/persistence/postgres.py
src/mini_agent/infrastructure/persistence/recovery.py
alembic/versions/20260727_0002_p0_records.py
tests/integration/test_database_migrations.py
tests/integration/test_http_session_adapter.py
tests/integration/test_postgres_record_adapters.py
tests/integration/test_postgres_atomicity.py
tests/integration/test_postgres_recovery.py
tests/integration/test_postgres_get_order.py
```

禁止所有 Runtime / Eval、`tests/conftest.py`、dependency / lockfile、现有 database factory、Alembic bootstrap、Composition Root、docs 与 planning 文件。`models.py`、migration chain 和 migration test 是 01-06 sole-writer 热点。

### Physical Design and Gates

`INFERRED`：使用 `p0_records`、`p0_record_references`、`mock_orders` 三张表：

- `p0_records` 保存 exact envelope 和最小授权 / CAS / recovery projection；code/version closed-set 精确对应现有 17 种 registry record。
- `p0_record_references` 保存 normalized references，source / target composite FK 为 transaction-safe deferred relation；每次写入要求 envelope 和 reference set 一致。
- `mock_orders` 只允许 composite `(customer_id, order_id)` 查询；不得建立或使用先按 `order_id` 取私有 payload 的路径。

必须证明：

1. 17 record exact round-trip 和 5 个 external relation，不复制 Pydantic schema。
2. same identity + same envelope 是 exact replay；same identity + different envelope 是 bounded integrity failure。
3. initial graph、Task transition、Run finalize、Tool dispatch / finalize、Observation 均为单事务 exact CAS。
4. READ dispatch fence commit 后才允许外部读取；ACTION 返回 ledger-required 且零写。
5. recovery closure 使用 repeatable snapshot、每个 max-one family SQL `LIMIT 2`、logical child count preflight。
6. recovery apply 重读 exact closure；`APPLIED` 把状态、关系和 1–3 个 supplied canonical TraceEvents 单次原子提交；所有非 `APPLIED` 结果零 state / Trace writes。
7. Alice 查询 Bob `O-2001` 与不存在 `O-9999` 得到完全相同的 adapter result，且 SQL 同时限定 trusted customer 与 candidate order。
8. Session 只从服务端 fixture/config 创建 `CustomerContext`，raw cookie 不进入 Trace、log、exception 或数据库。
9. `POST /v1/agent/runs` body 只接受 strict `message`；认证先于 handler / Run 创建；response 只含 `run_id`、`outcome`、`message`。

`OPEN`：Docker / PostgreSQL 当前可用性必须在 execution preflight 实测。payload ceiling、statement timeout 与 connection budget没有 canonical 数值，不由 01-06 自行冻结。

## 01-07 Evaluation

### Exact Packet Candidate

- branch: `codex/e2e01-w2-eval`
- worktree: `/Users/ming/projects/mini-agent-worktrees/e2e01-w2-eval`
- base: `c35687dafa3881bb322d91515068d8d39be79df6`
- contract changes: `NONE`
- new dependencies: `NONE`

建议只新增：

```text
src/mini_agent/evaluation/artifacts.py
src/mini_agent/evaluation/scripted_provider.py
src/mini_agent/evaluation/graders.py
src/mini_agent/evaluation/harness.py
src/mini_agent/infrastructure/model/qwen_responses.py
tests/component/evaluation/test_e2e01_versioned_artifact_loader.py
tests/component/evaluation/test_e2e01_scripted_model_provider.py
tests/component/evaluation/test_e2e01_graders.py
tests/component/model/test_qwen_responses_adapter.py
tests/integration/evaluation/test_e2e01_offline_harness.py
tests/baseline/test_qwen_baseline.py
```

禁止修改五个 `evals/**/*.json`、现有 artifact consistency tests、Core / Application / 其他 Infra、`tests/conftest.py`、dependency、migration、Composition Root、docs 与 planning。`infrastructure/model/qwen_responses.py` 是 active Eval ownership 的精确例外；namespace-package 布局不要求新增 `__init__.py`。

### Artifact Integrity

五个 exact-byte hash：

| Artifact | SHA-256 |
|---|---|
| fixture | `3940f5755ab001339d254077b36b3ae2965e590adee43ea0fb4e1d7cd2648c33` |
| cases | `58622417bf2221ded9951a8f41c29bdfd2d5fbe71109ade64c1b52f27ede4440` |
| scripts | `2b42415c1c705b30b34f7a80d810726d59f7891da52daa390208d62fa1aa7176` |
| lanes | `61e43e8a560c3b31d1444759360941bb038d41a94ee1326be7c8cce52808158d` |
| manifest | `ffd9d3f130813e3acec347c4ab23fc4372a0969288c35120e72aa8650fa7b8bd` |

Manifest 继续保持 `CONTRACT_DEFINED`、无 Eval Result / baseline artifact。Loader 必须先读取 fixed manifest raw bytes并与硬编码 manifest SHA-256比对，成功后才能 parse / closed-schema；随后逐个 artifact执行path closure与raw-byte SHA，再 parse其内容。拒绝 absolute path、`..`、symlink escape、duplicate ID、version mismatch与悬空引用。

### Runtime-independent Eval Behavior

1. Scripted Provider 按显式 `model_script_ref` 和 strict cursor 工作，不做关键词路由、不访问网络、不读 model credential。
2. Qwen Adapter 固定 `qwen3.7-plus-2026-05-26` 和 Responses request allowlist：`store=false`、`stream=false`、不发送 previous response / conversation / session cache，只注册本阶段目标 function；零个或多个目标 call、invalid JSON / DTO、raw provider error 均丢弃后映射 fresh parameterless `ProviderProtocolError`。Component tests只用 mock transport。
3. valid output 构造 canonical DTO；raw invalid envelope / lower-level error 丢弃后只暴露 fresh parameterless `ProviderProtocolError`，无 cause/context。
4. stale script 只产生 one-shot fault directive，Provider 不直接改 Runtime state。
5. 精确实现 13 个 artifact-named graders：
   `SchemaGrader`、`IdentityBoundaryGrader`、`RequestUnderstandingGrader`、
   `InputBindingGrader`、`TaskStateGrader`、`ToolCallGrader`、
   `ObservationGrader`、`DisclosureGrader`、`RendererFactGrader`、
   `ErrorMappingGrader`、`TraceCompletenessGrader`、`PersistenceGrader`、
   `ToolsetReplayGrader`。
6. 每个 grader 使用现有 `EvalGraderResult` 和稳定 reason code；至少一个 pass 与定向 tamper fail test。任一适用 Critical failure 强制 Case FAIL。
7. E2E01-04 A/B 缺少配对 case 不能 PASS；比较仅限规定的五个安全 observable。
8. Harness 注入 `EvalCaseSut`、`EvalResultPort` 和 Trace callbacks；invalid execution 写现有 `EvalExecutionFailureRecord`，不得伪造成 Case FAIL。
9. `EvalResultPort` append-only；重复 attempt 不覆盖。`EvalCaseGraded` append 后必须 reload trace 再跑 completeness。

01-07 可以证明 loader、Scripted / Qwen Adapter的离线协议行为、grader 和 fake / in-process Harness 自身；不能声称真实 Runtime、HTTP、PostgreSQL、Trajectory/E2E、Case activation或真实网络 Qwen Baseline已完成。

## Cross-stream Integration Contract

```text
c35687d exact base
  ├─ 01-05 Runtime feature PR
  ├─ 01-06 Infra feature PR
  └─ 01-07 Eval feature PR

serial integration:
  Runtime exact-head review/replay/merge
  → Infra compatibility replay/review/merge
  → Eval compatibility replay/review/merge
  → 01-08 Composition Root and vertical evidence
```

每个 writer 交接必须包含 branch、base、head、commit、tree、实际 changed files、RED/GREEN、focused/full commands、allowlist containment、contract/security/Eval impact、nonclaims 与未决风险。

## Validation Architecture

- 每个原子 task 先 RED 后 GREEN，至少有同 Packet focused command。
- 每个 Packet 结束运行 full `uv run pytest`；代码修改后运行 `graphify update .` 由 Integrator完成 post-merge freshness gate。
- Infra 额外执行 migration upgrade/downgrade/upgrade 和 disposable PostgreSQL tests。
- Eval 额外重算五个 SHA-256、证明无网络与 manifest byte-identical。
- 合并前由独立 reviewer 对 exact published head 做 correctness / security / contract / test-gap review；finding 用追加 commit 修复并复审。
- 01-08 前不能更新 Case lifecycle、Requirements checkbox 或 Phase completion。

## Open Items and Non-blockers

- `OPEN / NON_BLOCKING`：01-08 的 local fixture parser / typed seed assembly 需要 sole owner。
- `OPEN / NON_BLOCKING`：startup readiness 的 HTTP / process 外部表达由 01-08 决定。
- `OPEN / NON_BLOCKING`：真实网络 Qwen Baseline取决于 W4 时的显式 credential / Base URL；缺失不阻塞离线 release gate，但必须准确记录 `SKIPPED / NOT_RUN`。
- `OPEN / NON_BLOCKING`：resource ceilings 没有 canonical 数值；不得由实现任意冻结。

## RESEARCH COMPLETE
