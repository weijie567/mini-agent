# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

W1 基础骨架与 W2 组件实现已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- 受控 Runtime、Session / HTTP Adapter、PostgreSQL record / `get_order` Adapter与恢复路径；
- `e2e01-thin-fixture-v1`、versioned Eval artifacts、Scripted / Qwen Provider Adapter、Harness、Graders及结构化 Result / Failure machinery；
- 01-07B Eval evidence boundary、01-07C/01-07G owner rulings已完成；01-07D / 01-07H又通过Plan与feature PR #56/#57/#59/#60形成共同barrier `B_DH = 4a7e802e8aebc54e0582a1e4d99f140b56e7b131`。01-07N/O随后冻结RU v2 cutover合同与唯一execution map，派生状态和Project Direction已通过PR #67/#68依次对齐；这些证据不表示01-07F/E或真实纵向链已实现。

这不表示首条纵向切片已经可运行或 Case 已通过。Composition Root、real `EvalCaseSut`、PostgreSQL evidence reader、真实 HTTP → Runtime → PostgreSQL → Eval 纵向装配、Trajectory / E2E Result与 credentialed Qwen runner仍未实现；Case 生命周期继续是 `CONTRACT_DEFINED`。

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

`W2-CONTRACT-FREEZE` 已通过 PR #9 合并，GSD activation 已由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) 生效。Plan 01-01至01-04H的planning与owner链已通过PR #11–#32依序合并；01-05R Runtime通过 [PR #33](https://github.com/weijie567/mini-agent/pull/33) / [PR #34](https://github.com/weijie567/mini-agent/pull/34)完成，01-06R Infrastructure通过 [PR #35](https://github.com/weijie567/mini-agent/pull/35) / [PR #36](https://github.com/weijie567/mini-agent/pull/36)完成，01-07 Eval [PR #29](https://github.com/weijie567/mini-agent/pull/29)在latest-integration overlay复验后完成。01-07A又通过 [PR #37](https://github.com/weijie567/mini-agent/pull/37) / [PR #38](https://github.com/weijie567/mini-agent/pull/38)完成真实 Runtime Trace alignment；Business、Eval与项目规则的证据状态分别经PR #39–#41对齐。01-07B planning / status PR #42–#43签发固定base后，[PR #44](https://github.com/weijie567/mini-agent/pull/44)以exact six-file ownership完成Eval evidence boundary。01-07G owner [PR #50](https://github.com/weijie567/mini-agent/pull/50)与01-07C r1 owner [PR #53](https://github.com/weijie567/mini-agent/pull/53)随后从共同base完成双review、latest-integration overlay与串行merge，形成exact barrier `B_CG = 327b39da45cdcf564609a5385d52c4264da2c669`。01-07D / 01-07H通过Plan PR #56/#57与feature PR #59/#60从`B_CG`执行并串行形成`B_DH = 4a7e802e8aebc54e0582a1e4d99f140b56e7b131`；01-07N Plan / owner PR #62/#63随后冻结`p0-ru-v2-cutover-r1`，01-07O Plan / owner PR #64/#65冻结唯一execution map，PR #66–#68依次完成execution owner、派生状态与Project Direction对齐。用户已明确暂时停用Graphify；后续不运行或引用Graphify，也不把freshness作为当前或后续barrier门禁。historical Runtime [PR #28](https://github.com/weijie567/mini-agent/pull/28)与Infra [PR #30](https://github.com/weijie567/mini-agent/pull/30)只保留review evidence，不rebase/force-push。

01-08 preflight发现的Case/Script/output oracle与variant-scoped Trace precedence阻断已由01-07B关闭；SUT / Scripted Provider现在只接收closed execution projection，Harness独自完成one-time correlation与authenticated Case binding。01-07C/D/N已依次冻结Request Understanding durable aggregate、Thin Slice exact mapping与RU v2 cutover合同；01-07G/H已冻结P0 `get_order` source-version authority和additive Core representation。当前`B_O_STATUS`已形成，下一步由01-07F从该exact barrier执行`CORE_EXPAND`并形成`B_F`；01-07E只能再从reviewed `B_F`执行`CODEC_EXPAND`。其余writer、allowlist、barrier与顺序只以[多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)中的`P0-RU-V2-EXECUTION-MAP`为准，README不维护第二套易漂移计数或顺序。Case / Requirement lifecycle仍为`0/8`，尚无真实HTTP/PostgreSQL Eval Result、credentialed Qwen baseline或完整切片通过结论；实时派生状态见[STATE](.planning/STATE.md)与[ROADMAP](.planning/ROADMAP.md)。

## GSD

GSD 只作为派生的规划、审查和验证层，不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。Activation 已随 PR #10 合并而生效；后续仍必须按 [GSD Governance](.planning/GOVERNANCE.md)、[Activation Record](.planning/ACTIVATION.md) 与[当前派生 State](.planning/STATE.md) 受控使用。

当前明确禁用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 和 `gsd-ship`。规划使用 GSD planner / checker 角色的只读建议，由 Integrator 在 dedicated planning-status Worktree 单写最终 Plan；UAT 使用无 lifecycle mutation 的受控 adapter。`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Codex 多 Agent：Integrator 仍在 workflow 外预建精确 Task Packet Worktree / feature branch，Agent 实现并创建 draft feature → integration PR，Integrator 串行合并，最后显式创建 integration → `main` PR。Code review、fix、validation、Eval / Security audit 与 UAT 的条件和 containment gate 以 Governance 为准。
