# Mini Agent

面向已登录消费者的“订单与配送售后 Agent”P0。当前项目用一个自建站和可复现的合成数据模拟 Order、Shipment、Policy Knowledge 与 Refund 边界；P0 不连接真实电商、支付、退款或物流系统。

## 当前进度

W1 基础骨架与 W2 组件实现已经进入 `integration/e2e01-thin`：

- Python / uv 工具链、固定版本 PostgreSQL + pgvector、Alembic 与隔离测试 namespace；
- Core / Application 的身份、Request Understanding、Task、Tool、Observation、Trace 等 contract；
- 受控 Runtime、Session / HTTP Adapter、PostgreSQL record / `get_order` Adapter与恢复路径；
- `e2e01-thin-fixture-v1`、versioned Eval artifacts、Scripted / Qwen Provider Adapter、Harness、Graders及结构化 Result / Failure machinery；
- 当前 exact integration `ccdafe87...` 已包含 01-07B Eval evidence boundary；代码门禁为 `762` 项 Plan focused、`40` 项 migration 与 `1493 passed, 1 deselected` 的默认离线测试。

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

`W2-CONTRACT-FREEZE` 已通过 PR #9 合并，GSD activation 已由 [PR #10](https://github.com/weijie567/mini-agent/pull/10) 生效。Plan 01-01至01-04H的planning与owner链已通过PR #11–#32依序合并；01-05R Runtime通过 [PR #33](https://github.com/weijie567/mini-agent/pull/33) / [PR #34](https://github.com/weijie567/mini-agent/pull/34)完成，01-06R Infrastructure通过 [PR #35](https://github.com/weijie567/mini-agent/pull/35) / [PR #36](https://github.com/weijie567/mini-agent/pull/36)完成，01-07 Eval [PR #29](https://github.com/weijie567/mini-agent/pull/29)在latest-integration overlay复验后完成。01-07A又通过 [PR #37](https://github.com/weijie567/mini-agent/pull/37) / [PR #38](https://github.com/weijie567/mini-agent/pull/38)完成真实 Runtime Trace alignment；Business、Eval与项目规则的证据状态分别经PR #39–#41对齐。01-07B planning / status PR #42–#43签发固定base后，[PR #44](https://github.com/weijie567/mini-agent/pull/44)以exact six-file ownership完成Eval evidence boundary并merge为`ccdafe87d5f118b729d6f3fff8635a0b92f3e3c5`。当前代码门禁为762项Plan focused、40项migration与1493项默认离线测试（另1项`qwen_baseline` deselected），Graphify为4648 nodes / 17000 edges / 1373 communities。historical Runtime [PR #28](https://github.com/weijie567/mini-agent/pull/28)与Infra [PR #30](https://github.com/weijie567/mini-agent/pull/30)只保留review evidence，不rebase/force-push。

01-08 preflight发现的Case/Script/output oracle与variant-scoped Trace precedence阻断已由01-07B关闭；SUT / Scripted Provider现在只接收closed execution projection，Harness独自完成one-time correlation与authenticated Case binding。仍不能隐含塞入Composition Root的owner blocker包括：Request Understanding最低持久化字段、logical record version与model-output version的owner ruling/mapping/codec/Core闭环；P0 `get_order` canonical source-version算法与独立Core/Order DTO；Application expectation-free exact-Run Evidence Port、Infra strict reader与Eval mapper；invalid-RU Pydantic/trusted-field到`COMPLETED / INPUT_INVALID`的Application signal / Runtime / Scripted-Qwen分类闭环；以及credentialed Qwen runner。[01-07C Plan](.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md)已经签发固定的Intent-owner单文件Task Packet，但feature实现尚未开始；01-07G仍待独立planning PR签发。当前`PROJECT_DIRECTION.md`仍保留01-07B时点的16-Plan易漂移计数，因active owner边界不在本planning Packet内，必须通过紧随其后的独立owner PR移除或对齐；在此之前不声称cross-file完全aligned，也不启动01-07G planning或C/G feature dispatch。后续按`{01-07C RU semantic ruling, 01-07G Thin Slice source-version ruling} → {01-07D RU exact mapping, 01-07H Core/Order DTO} → {01-07E persistence codec, 01-07F RU Core} → 01-07I Application Evidence Port / Provider failure contract → 01-07J Runtime / INPUT_INVALID mapping → {01-07K Infra reader, 01-07L Eval mapper / Scripted-Qwen consumers} → 01-08 → 01-08A`逐级推进；每个花括号内的Packet都必须由Integrator串行合并形成共同的新exact SHA，下一组才能签发。I/J/L分别由Application Port、Runtime和01-07既有Eval owner通过独立tests关闭错误分类，不把raw异常或diagnostics带入Run/Trace。当前目标Task Packet完成口径为`14/28`，磁盘正式签发17个Plan；Case lifecycle仍保持`0/8`，尚无真实HTTP/PostgreSQL Eval Result或完整切片通过结论。若owner裁决要求额外migration、全局Memory version升级或新的外部契约，必须先新增Packet并更新分母，不能把它隐含塞入既有slot。实时状态与证据见[01-07B Summary](.planning/phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md)与[多 Agent 实施计划](docs/implementation/e2e01-thin-slice-multi-agent-plan.md)。

## GSD

GSD 只作为派生的规划、审查和验证层，不能成为产品、架构、契约或 Eval 语义的第二套 canonical owner。Activation 已随 PR #10 合并而生效；后续仍必须按 [GSD Governance](.planning/GOVERNANCE.md)、[Activation Record](.planning/ACTIVATION.md) 与[当前派生 State](.planning/STATE.md) 受控使用。

当前明确禁用 stock `gsd-import`、`gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、`phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 和 `gsd-ship`。规划使用 GSD planner / checker 角色的只读建议，由 Integrator 在 dedicated planning-status Worktree 单写最终 Plan；UAT 使用无 lifecycle mutation 的受控 adapter。`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` 只关闭 GSD 自管并行 / Worktree，不关闭 Codex 多 Agent：Integrator 仍在 workflow 外预建精确 Task Packet Worktree / feature branch，Agent 实现并创建 draft feature → integration PR，Integrator 串行合并，最后显式创建 integration → `main` PR。Code review、fix、validation、Eval / Security audit 与 UAT 的条件和 containment gate 以 Governance 为准。
