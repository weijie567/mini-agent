# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

W1 基础骨架与 W2 组件实现已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- 受控 Runtime、Session / HTTP Adapter、PostgreSQL record / `get_order` Adapter与恢复路径；
- `e2e01-thin-fixture-v1`、versioned Eval artifacts、Scripted / Qwen Provider Adapter、Harness、Graders及结构化 Result / Failure machinery；
- 01-07B Eval evidence boundary、01-07C/01-07G owner rulings与active/derived状态已由PR #44/#50/#53–#55依次索引；01-07D / 01-07H Plan又经PR #56/#57以final `0/0/0/0` review签发。两份feature的共同execution base仍冻结为`B_CG = 327b39da45cdcf564609a5385d52c4264da2c669`，planning merge SHA不替换它；D/H状态是`PLANNED / FEATURE_DISPATCH_NEXT`，不是feature complete。

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

`W2-CONTRACT-FREEZE` 已通过 PR #9 合并，GSD activation 已由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) 生效。Plan 01-01至01-04H的planning与owner链已通过PR #11–#32依序合并；01-05R Runtime通过 [PR #33](https://github.com/weijie567/mini-agent/pull/33) / [PR #34](https://github.com/weijie567/mini-agent/pull/34)完成，01-06R Infrastructure通过 [PR #35](https://github.com/weijie567/mini-agent/pull/35) / [PR #36](https://github.com/weijie567/mini-agent/pull/36)完成，01-07 Eval [PR #29](https://github.com/weijie567/mini-agent/pull/29)在latest-integration overlay复验后完成。01-07A又通过 [PR #37](https://github.com/weijie567/mini-agent/pull/37) / [PR #38](https://github.com/weijie567/mini-agent/pull/38)完成真实 Runtime Trace alignment；Business、Eval与项目规则的证据状态分别经PR #39–#41对齐。01-07B planning / status PR #42–#43签发固定base后，[PR #44](https://github.com/weijie567/mini-agent/pull/44)以exact six-file ownership完成Eval evidence boundary。01-07G owner [PR #50](https://github.com/weijie567/mini-agent/pull/50)与01-07C r1 owner [PR #53](https://github.com/weijie567/mini-agent/pull/53)随后从共同base完成双review、latest-integration overlay与串行merge，形成exact barrier `B_CG = 327b39da45cdcf564609a5385d52c4264da2c669`。01-07D [PR #56](https://github.com/weijie567/mini-agent/pull/56)与01-07H [PR #57](https://github.com/weijie567/mini-agent/pull/57)已分别签发独立Plan：merge / Plan blob为`5d72cb70bf5dc97ae2f74ab1697a61e77a23b725` / `e63b844301f8d74da80bc8a1d01bbf3eea689de8`与`e6c8cbaf782ac64e0fced492b9b552f246d0e940` / `52ffe6652284d75b8f2546d50439762b63dfdfa0`；两者仍从`B_CG`执行，D/H feature allowlist机械交集为0。D/H Plan overlay full分别为`1493 passed, 1 deselected, 12 warnings in 87.91s`与`1493 passed, 1 deselected, 12 warnings in 86.92s`；这只证明Plan输入兼容，不证明feature完成。最近一次Graphify完成点是PR #55 merge `676980e7244fcb1af670b66abdde205fe17cb65a`，早于PR #56/#57；D/H Plan与本次状态对齐的semantic refresh由Integrator在状态合并后执行。historical Runtime [PR #28](https://github.com/weijie567/mini-agent/pull/28)与Infra [PR #30](https://github.com/weijie567/mini-agent/pull/30)只保留review evidence，不rebase/force-push。

01-08 preflight发现的Case/Script/output oracle与variant-scoped Trace precedence阻断已由01-07B关闭；SUT / Scripted Provider现在只接收closed execution projection，Harness独自完成one-time correlation与authenticated Case binding。01-07C已冻结Request Understanding durable aggregate、candidate closure与logical/model独立version语义；01-07G已冻结P0 `get_order` canonical source-version authority、算法、fixed vectors与exact-copy边界。01-07D / 01-07H Plan已经签发，但对应mapping与DTO feature尚未开始；当前没有D/H Summary、feature branch、commit或PR。下一步从`B_CG = 327b39d...`创建两个独立feature Worktree / branch：D只写Thin Slice implementation spec，H只写Core/Order source与三份owned tests；两个feature都须exact-head review、latest-integration overlay并由Integrator串行merge形成共同barrier，01-07E/F在此之前持续blocked。后续按`{01-07D, 01-07H} → {01-07E persistence codec, 01-07F RU Core} → 01-07I Application Evidence Port / Provider failure contract → 01-07J Runtime / INPUT_INVALID and version acceptance → {01-07K Infra reader/version producer, 01-07L Eval mapper / Scripted-Qwen consumers} → 01-07M Core source-version closure → 01-08 → 01-08A`逐级推进。H/J/K/M继续保持additive且legacy `FOUND + None`合法 → fail-closed → producer → Core closure的green migration；I/J/L分别由Application Port、Runtime和01-07既有Eval owner关闭错误分类。当前目标Task Packet完成证据仍为`16/29`，numbered Plan evidence仍为`7/8`，正式签发为20个Plan；Case / Requirement lifecycle仍为`0/8`，尚无真实HTTP/PostgreSQL Eval Result或完整切片通过结论。实时状态与证据见[01-07D Plan](.planning/phases/01-cycle-1-e2e-01/01-07D-PLAN.md)、[01-07H Plan](.planning/phases/01-cycle-1-e2e-01/01-07H-PLAN.md)与[多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。

## GSD

GSD 只作为派生的规划、审查和验证层，不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。Activation 已随 PR #10 合并而生效；后续仍必须按 [GSD Governance](.planning/GOVERNANCE.md)、[Activation Record](.planning/ACTIVATION.md) 与[当前派生 State](.planning/STATE.md) 受控使用。

当前明确禁用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 和 `gsd-ship`。规划使用 GSD planner / checker 角色的只读建议，由 Integrator 在 dedicated planning-status Worktree 单写最终 Plan；UAT 使用无 lifecycle mutation 的受控 adapter。`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Codex 多 Agent：Integrator 仍在 workflow 外预建精确 Task Packet Worktree / feature branch，Agent 实现并创建 draft feature → integration PR，Integrator 串行合并，最后显式创建 integration → `main` PR。Code review、fix、validation、Eval / Security audit 与 UAT 的条件和 containment gate 以 Governance 为准。
