# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

W1 基础骨架与 W2 组件实现已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- 受控 Runtime、Session / HTTP Adapter、PostgreSQL record / `get_order` Adapter与恢复路径；
- `e2e01-thin-fixture-v1`、versioned Eval artifacts、Scripted / Qwen Provider Adapter、Harness、Graders及结构化 Result / Failure machinery；
- 01-07B至01-07I/P已依序形成既有`B_CG`、`B_DH`、`B_O_STATUS`、`B_F`、`B_FE_EXPAND`与`B_IP`；01-07K/L/M/Q再通过PR #94–#106形成`B_DEPENDENCY`、`B_DEPENDENCY_M`与`B_Q`。Execution-owner r2 PR #107增加J所需的Y/Z/AA，PR #108–#120依序形成`B_YZ`与`B_J_READY`；J Plan、scope alignment与Runtime feature PR #121–#124最终形成scoped `B_ACTIVE = 7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`、tree `f70b20215e569acf3ad196cc050e9a23700d4bae`。Planning-derived status与Project Direction PR #125–#127只索引该证据；本README同样不创建新barrier，execution-owner current-status prose仍待独立对齐。

这不表示首条纵向切片已经可运行或 Case 已通过。K的strict exact-Run PostgreSQL reader已经实现，但Composition Root、real `EvalCaseSut`及其PostgreSQL `EvalEvidence` reader、真实 HTTP → Runtime → PostgreSQL → Eval 纵向装配、Trajectory / E2E Result与credentialed Qwen runner仍未实现；Case生命周期继续是`CONTRACT_DEFINED`。

实时范围与权威边界见：

- [业务能力说明](docs/business-capabilities.md)
- [P0 架构方向](PROJECT_DIRECTION.md)
- [E2E01 最薄切片 Implementation Spec](docs/implementation/e2e01-thin-slice-implementation-spec.md)
- [多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)
- [项目协作规则与 canonical 命令](AGENTS.md)

## 本地开发

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 与 Docker Compose。从仓库根目录执行：

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

`db` 使用持久 volume；`db-test` 使用可丢弃的 tmpfs。测试只允许连接 `127.0.0.1:55433/mini_agent_test`，并为每个 worker / Eval Run 建立独立 schema。当前没有 canonical 的应用启动命令，因为 Composition Root 和 HTTP 纵向链尚未实现。

## 为什么先准备模拟数据

开发前需要冻结最小、确定性的 synthetic fixture，而不是等待生产数据，也不是一次性仿真完整生产环境。当前唯一 fixture 是 [`e2e01-thin-fixture-v1`](evals/fixtures/e2e01-thin-slice.v1.json)，它同时服务后续数据库 seed、HTTP E2E 和 Eval：

- Alice 可以访问 `O-1001`；
- Bob 拥有 `O-2001`，用于验证跨用户访问不泄漏；
- `O-9999` 是不得写入数据库的不存在订单 sentinel；
- Fixture、Case dataset、model-script catalog 与 lane artifact 都有固定版本，其 SHA-256 由 versioned manifest 记录；manifest 自身由 Git 版本化。

真实失败出现后再增量加入回归集；fixture 不包含真实客户、真实订单或生产凭据。

## 多 Agent 与 GitHub 流程

仓库是公开的：[weijie567/mini-agent](https://github.com/weijie567/mini-agent)。`main` 与 `integration/e2e01-thin` 受 branch protection 保护，开发变更必须走 feature branch 和 PR。

```text
每个 Task Packet 的 exact frozen SHA
├── ownership / dependency 允许时：多个 worktree 并行
└── shared contract 或 exact-base 依赖时：reviewed merge 后串行签发
        ↓ feature branch 独立验证与只读 review
Integrator 串行合并到 integration
        ↓ 完整 E2E gate
integration PR → main
```

写入 Agent 必须使用不同 Git Worktree、branch 和互不重叠的文件 ownership。一个 GSD Plan 只映射一个精确 Task Packet；Packet 不得跨 repository、branch、Worktree、writer 或 ownership boundary。每个 Packet 都要包含精确 `base_sha`、repository、head/base branch、allowlist、forbidden files、依赖、验证命令、契约变化、安全 / Eval 影响、回滚和交接格式；禁止直接 push `main` 或 integration。

`W2-CONTRACT-FREEZE`已通过PR #9合并，GSD activation已由[PR #10](https://github.com/weijie567/mini-agent/pull/10)生效。截至PR #92，仓库已记录01-01至`B_IP`的planning、feature、review remediation与status-alignment lineage；其中被finding阻断或关闭未合并的候选只保留失败证据，不能冒充reviewed barrier。K/L Plan与feature [PR #94](https://github.com/weijie567/mini-agent/pull/94)–[PR #98](https://github.com/weijie567/mini-agent/pull/98)形成`B_DEPENDENCY = e54a6a4...`，M [PR #99](https://github.com/weijie567/mini-agent/pull/99)–[PR #101](https://github.com/weijie567/mini-agent/pull/101)形成`B_DEPENDENCY_M = 42fa2ec...`，Q remediation与Plan/feature [PR #102](https://github.com/weijie567/mini-agent/pull/102)–[PR #106](https://github.com/weijie567/mini-agent/pull/106)形成`B_Q = 2b9fde6...`。Execution-map r2 [PR #107](https://github.com/weijie567/mini-agent/pull/107)后，Y/Z [PR #108](https://github.com/weijie567/mini-agent/pull/108)–[PR #111](https://github.com/weijie567/mini-agent/pull/111)形成`B_YZ = d704b87...`，AA与quality-gate remediation [PR #112](https://github.com/weijie567/mini-agent/pull/112)–[PR #120](https://github.com/weijie567/mini-agent/pull/120)形成`B_J_READY = b8d32d5...`，J [PR #121](https://github.com/weijie567/mini-agent/pull/121)–[PR #124](https://github.com/weijie567/mini-agent/pull/124)形成scoped `B_ACTIVE = 7f92b5e...`。完整writer、allowlist、barrier与顺序只以[多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)为准；README不维护第二套执行map或计数。用户已明确暂时停用Graphify；后续不运行或引用Graphify，也不把freshness作为当前或后续barrier门禁。historical Runtime [PR #28](https://github.com/weijie567/mini-agent/pull/28)与Infra [PR #30](https://github.com/weijie567/mini-agent/pull/30)只保留review evidence，不rebase/force-push。

01-08 preflight发现的Case/Script/output oracle与variant-scoped Trace precedence阻断已由01-07B关闭；K/L/M/Q/Y/Z/AA/J又完成strict reader/source version、v2 Provider/mapper、Core closure、active codec、v2 reducer/write contracts、PostgreSQL atomic writers与Runtime exact-one active switch。当前scoped `B_ACTIVE = 7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`只覆盖exact-one accepted E2E01与已定义candidate-invalid/protocol/source-version fault routes；zero/all-REJECT、multi-ACCEPT、atomic failure恢复和v1 contract closure仍未完成。01-07S/U已从原exact `B_ACTIVE`解锁，planning/status/README/execution-owner alignment都不得替换该feature base或提前形成`B_SU`。Case / Requirement lifecycle仍为`0/8`，尚无Composition Root、real `EvalCaseSut`与PostgreSQL `EvalEvidence` reader、真实HTTP Trajectory/E2E Result、credentialed Qwen baseline或完整切片通过结论；实时派生状态见[STATE](.planning/STATE.md)与[ROADMAP](.planning/ROADMAP.md)。

## GSD

GSD 只作为派生的规划、审查和验证层，不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。Activation 已随 PR #10 合并而生效；后续仍必须按 [GSD Governance](.planning/GOVERNANCE.md)、[Activation Record](.planning/ACTIVATION.md) 与[当前派生 State](.planning/STATE.md) 受控使用。

当前明确禁用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 和 `gsd-ship`。规划使用 GSD planner / checker 角色的只读建议，由 Integrator 在 dedicated planning-status Worktree 单写最终 Plan；UAT 使用无 lifecycle mutation 的受控 adapter。`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Codex 多 Agent：Integrator 仍在 workflow 外预建精确 Task Packet Worktree / feature branch，Agent 实现并创建 draft feature → integration PR，Integrator 串行合并，最后显式创建 integration → `main` PR。Code review、fix、validation、Eval / Security audit 与 UAT 的条件和 containment gate 以 Governance 为准。
