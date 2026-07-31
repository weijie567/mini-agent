---
phase: 01-cycle-1-e2e-01
scope: 01-05-01-07
status: complete
base_sha: c35687dafa3881bb322d91515068d8d39be79df6
created: "2026-07-27"
---

# Phase 1 W2｜Implementation Pattern Map

> **DERIVED / NON_NORMATIVE**
> 本文件只帮助 executor复用当前仓库的物理模式。它不拥有语义；找不到本地 analog时明确标记 `NOT_FOUND`，不得用臆造模式覆盖 active owner。

## Shared Conventions

| Concern | Existing pattern | W2 rule |
|---|---|---|
| Contract model | `src/mini_agent/core/common.py::ContractModel` | 复用 immutable、`extra="forbid"`、validated default；不新建第二套 base model |
| Visibility | `ModelVisibleModel`、`RuntimePrivateModel`、`AuditOnlyModel`、`UserVisibleModel` | 新 typed seam使用正确现有 visibility；不得用普通 dict绕过 |
| Enum | Core/Application 的 `StrEnum` | 稳定状态 / reason使用已冻结 enum；不得复制同名字符串常量 |
| Ports | `src/mini_agent/application/ports.py` 的 runtime-checkable `Protocol` | Adapter实现现有 Port；01-05/06/07不得扩展 shared Port |
| Commands/records | `src/mini_agent/application/records.py` | 编排构造已有 command/record；不要定义相同语义 DTO |
| Persistence codec | `src/mini_agent/application/persistence.py` | Infra必须调用 closed registry codec并保留 bounded integrity error |
| Tests | `tests/component/**` 的table-driven positive/negative contract tests | 每个安全边界至少有通过、定向篡改、zero-side-effect断言 |
| Integration DB | `tests/conftest.py::PostgresNamespaceFactory` | 复用 disposable per-test schema；保持该共享文件byte-identical |
| Package layout | `src/mini_agent/infrastructure/` 可作为 namespace package | 只在 exact allowlist明确要求时新增 `__init__.py`；不要做无关 re-export |

## 01-05 Runtime

| New file | Closest analog / input | Pattern to reuse |
|---|---|---|
| `core/request_processing.py` | `core/request_understanding.py`、`core/task_state.py` | pure deterministic function + frozen typed input/output；validation与reducer不做 I/O |
| `core/control_gateway.py` | `core/tool_system.py` | closed enum reason、immutable snapshot、fail-closed exact comparison |
| `core/presentation_policy.py` | `core/presentation.py` | fact-free typed plan与strict projection allowlist |
| `application/agent_run_service.py` | `application/ports.py` + aggregate commands in `records.py` | constructor-injected Ports；explicit happens-before；每个条件写只接受exact success result |
| `application/read_tool_executor.py` | ToolCall records/commands in `records.py` | `CREATED → RUNNING → terminal`；dispatch fence成功后才调用 external read |
| `application/deterministic_renderer.py` | `core/order.py::SafeOrderProjection` + `core/presentation.py` + `records.py::AgentRunResult` | renderer仅从approved projection取事实；同模块完成bounded result mapping与固定安全文案，不读取raw Provider payload |
| `application/restart_recovery_service.py` | `RestartRecoveryPort` + recovery command models | load closure → construct exact command → claim/apply；不resume/replay |

`NOT_FOUND`：仓库尚无 Application service implementation或composition example。Executor必须从现有 Port/command contract组合，不能把测试 fake升级成production pattern，也不能创建 `bootstrap.py`。

Runtime tests沿用现有 Component contract tests的factory + parametrize模式；以spy/fake Port记录调用顺序和次数，不引入真实 PostgreSQL、HTTP或Eval artifact解析。

## 01-06 Infrastructure

| New/modified file | Closest analog / input | Pattern to reuse |
|---|---|---|
| `infrastructure/persistence/models.py` | 当前 declarative `Base` | 单一 metadata owner；SQL constraint/index命名明确且可由migration test检验 |
| `infrastructure/persistence/postgres.py` | `persistence/database.py::build_session_factory` | sync SQLAlchemy 2 `Session.begin()`；helper不commit；owner scope进入SQL predicate |
| `infrastructure/persistence/recovery.py` | existing recovery Port/commands | stable lock order、bounded query、repeatable snapshot与serializable apply |
| `alembic/versions/20260727_0002_p0_records.py` | `20260726_0001_initial_persistence.py` | typed revision metadata、schema-aware Alembic op、safe downgrade；不碰shared vector extension |
| `infrastructure/auth/p0_session.py` | `SessionAuthPort` + identity models | config/fixture constructor injection；raw cookie只做lookup，不进入records/errors |
| `infrastructure/order/postgres.py` | `GetOrderPort` + order typed records | single owner-scoped composite query；未授权与不存在同一结果 |
| `api/http.py` | Thin Slice HTTP spec + `AgentRunHandler` | injected app/router factory；strict request/response allowlist；auth先于handler |
| Infra tests | `test_database_migrations.py` + `tests/conftest.py` | disposable schema、explicit DDL/introspection、rollback/atomicity injection |

`NOT_FOUND`：仓库没有现成 HTTP router / FastAPI error-mapping implementation。01-06只能按 frozen HTTP contract写 injected factory，不得猜测全局 app、server启动或Composition Root。

Infra不得通过 JSON containment实现授权，不得从stored owner反向创建 trusted scope，不得捕获 broad exception后返回not-found。Migration / model / adapter必须共享一套表名、constraint和projection定义。

## 01-07 Evaluation

| New file | Closest analog / input | Pattern to reuse |
|---|---|---|
| `evaluation/artifacts.py` | `test_e2e01_artifact_consistency.py` | fixed path map、exact bytes SHA before parse、closed ID/ref/version validation |
| `evaluation/scripted_provider.py` | `test_e2e01_scripted_scenario_catalog.py` + `ModelProvider` | explicit script ref + strict cursor；canonical DTO construction；raw error discard |
| `infrastructure/model/qwen_responses.py` | Thin Slice Spec `QwenResponsesAdapter` + existing `httpx` dependency + `ModelProvider` | explicit request field allowlist、exact one target function call、canonical DTO validation、fresh bounded error；Component tests使用mock transport |
| `evaluation/graders.py` | existing `EvalGraderResult` / reason / CF enums | deterministic typed evidence grading；stable reason codes；CF never averaged away |
| `evaluation/harness.py` | `EvalResultPort`、Eval records、`EvalCaseGraded` Trace type | injected SUT/Trace/Result callbacks；Result与ExecutionFailure严格分离；append-only |
| Eval tests | current artifact/catalog tests + pytest marker config | tamper-copy fixture、path/hash/ref negatives、mock-transport no-network assertion、pass + fail grader pair、conditional qwen baseline |

`NOT_FOUND`：仓库没有 existing Harness、grader registry、Scripted Provider、Qwen Adapter或real SUT adapter。Qwen的规范性 request/response边界来自 Thin Slice Spec，不得从其他SDK猜测；01-07不能把mock transport或fake/in-process evidence称为真实网络 Baseline、HTTP/PostgreSQL/Trajectory E2E。

Artifact测试修改副本或 `tmp_path`，不得改五个tracked JSON。`ProviderProtocolError` 必须是fresh parameterless instance并清除 cause/context；failure record不得保存raw exception、Prompt、Token或客户/订单PII。

## Hotspots and Stop Conditions

- `src/mini_agent/application/{ports,records,persistence}.py`
- 所有现有 `src/mini_agent/core/*.py`（只有01-05 allowlist中的三个新文件例外）
- `tests/conftest.py`
- `pyproject.toml`、`uv.lock`
- `alembic/env.py`、`alembic.ini`
- 五个 `evals/**/*.json`
- `docs/**`、`.planning/**`
- Composition Root、app startup与Graphify artifacts
- `src/mini_agent/infrastructure/**`（01-07 exact `infrastructure/model/qwen_responses.py` 例外）

任何 executor发现必须修改以上热点才能继续时，立即停止并交给 Integrator做owner / cross-file影响裁决；不得扩大allowlist。

## PATTERN MAPPING COMPLETE
