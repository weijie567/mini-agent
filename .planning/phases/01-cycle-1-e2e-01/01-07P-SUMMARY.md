---
phase: 01-cycle-1-e2e-01
plan: 07P
subsystem: request-understanding-v2-physical-dependency-expand
tags:
  - request-understanding
  - infrastructure
  - persistence
  - migration
  - security
status: complete_evidence_indexed
completed_at: "2026-07-29T03:41:19+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-29"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 0fb4d0ba5fb9d673f2d116041ce023dd367a52ec
planning_merge: dd4439f1c11853a4f10bca93a6f0cba1fa7c8cdc
published_head: 5328f435fdba41a64512bc810c94a550a1e24c40
integration_merge: bbe14fadc0cd2e14ad35e19177b079fcab685dfc
key_files:
  modified:
    - alembic/versions/20260728_0003_request_understanding_v2_expand.py
    - src/mini_agent/infrastructure/persistence/models.py
    - tests/integration/test_database_migrations.py
metrics:
  feature_commits: 3
  files_changed: 3
  focused_tests_passed: 48
  database_tests_passed: 119
  full_tests_passed: 1767
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07P｜Request Understanding v2 Physical Dependency Expand Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引 01-07P `DEPENDENCY_EXPAND` 的已合并 physical persistence 实现、review remediation 与可复现证据，不拥有 Request Understanding、Memory、logical codec、reader/writer、Runtime、Provider/Eval、active switch 或 lifecycle 语义。规范性内容仍由 [Memory owner](../../../docs/architecture/memory-design-reference.md)、[Thin Slice owner](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)、[execution map](../../../docs/implementation/e2e01-thin-slice-multi-agent-plan.md) 与 [01-07P Plan](01-07P-PLAN.md) 持有。

## Outcome

`01-07P` 最终从 reviewed `B_I_E_ORACLE_FIX` 以 additive、non-routable 方式完成 physical dependency expand：

- SQLAlchemy metadata与新 self-contained Alembic revision `20260728_0003` 精确允许17个 record code / 18个 code-version pair，唯一双版本 code 是 `request_understanding_record`；
- upgrade只原子替换同名 closed check，不修改、迁移、重写或回填既有 row；
- downgrade在同一 migration transaction 内先取得 `SHARE ROW EXCLUSIVE` table lock，再执行 bounded `EXISTS`；存在 RU-v2 row 时以固定无 PII 诊断 fail closed；
- AST/source-order oracle覆盖整个 `downgrade()`，真实 PostgreSQL 并发测试证明 downgrade 持锁时 `INSERT` / `UPDATE` 均以 `55P03` 被阻断，释放后可完成到 `0002` 且 v1 writes 恢复；
- 没有切换 active registry、codec/read/write routing、Runtime、Provider/Eval或 v1 contract。

原始 PR #82 的三文件实现保留为 RED/GREEN 与阶段性 oracle 冲突证据并已关闭、未合并。Dedicated 01-07E oracle fix 与 canonical execution-owner remediation完成后，01-07P-r1从 exact remediation base重放同一原始 patch，再追加一项 downgrade oracle fix并完成独立审查。PR #87 的 reviewed serial merge形成：

- `B_IP = bbe14fadc0cd2e14ad35e19177b079fcab685dfc`
- tree `65415ff5846892f257e95d8b8bd34f50752980a2`

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Original Plan / feature lineage | [#81](https://github.com/weijie567/mini-agent/pull/81) merge `7a476bada3fb13a7c1eee90023c18569f7407d48`；[#82](https://github.com/weijie567/mini-agent/pull/82) head `14c1abd9e81c91ee38d4324efb0f1b82e2869c17`，closed / unmerged |
| Oracle fix PR / head / merge | [#84](https://github.com/weijie567/mini-agent/pull/84) / `1e28b85e1bbf3b0f85561092d6e639b2ffaebfa2` / `0fb4d0ba5fb9d673f2d116041ce023dd367a52ec`（`B_I_E_ORACLE_FIX`） |
| Execution-owner remediation | [#85](https://github.com/weijie567/mini-agent/pull/85) / head `2fcc29f17bf9a4ce1bd6df28de112c0e8309131b` / merge `67e7aacca0c7db46e0f87e2a817aea47fa15aeb7` |
| R1 Planning PR / head / merge | [#86](https://github.com/weijie567/mini-agent/pull/86) / `b664737cc85e40ea6bbd0789785277a6b55b3166` / `dd4439f1c11853a4f10bca93a6f0cba1fa7c8cdc` |
| Final Plan blob | `1dcf69b2e5538137d526bdea6acf595890514892` |
| R1 execution base | `0fb4d0ba5fb9d673f2d116041ce023dd367a52ec`（`B_I_E_ORACLE_FIX`） |
| R1 RED / GREEN / final fix | `571d25e950b725a4ba968562ffa1c73b06d3b8f3` / `7521e27f12b99c9e3f5fdaa396ea784599a273c8` / `5328f435fdba41a64512bc810c94a550a1e24c40` |
| Feature head / tree | `5328f435fdba41a64512bc810c94a550a1e24c40` / `71d98adc548c690966631851ba18dca63ac9a766` |
| Original / replay GREEN patch | byte-identical patch SHA `4e85ed2fc3d14277339e4d15e9d2ba6de847c1cc24f7bbc55835a482323521f2` |
| Latest-integration overlay base / tree | `dd4439f1c11853a4f10bca93a6f0cba1fa7c8cdc` / `65415ff5846892f257e95d8b8bd34f50752980a2` |
| Replacement feature PR / merge / tree | [#87](https://github.com/weijie567/mini-agent/pull/87) / `bbe14fadc0cd2e14ad35e19177b079fcab685dfc` / `65415ff5846892f257e95d8b8bd34f50752980a2` |
| Scope | exact 3 commits、3 owned files；RED → GREEN replay → append-only downgrade oracle fix |
| Focused / database / full suite | `48 passed`；`119 passed`；`1767 passed, 1 deselected, 12 warnings` |
| Independent review | 首轮 `0/0/1/0`并BLOCK；修复后feature与latest overlay均 `0/0/0/0`、`PASS / MERGE` |
| Exact `B_IP` validation | Alembic head `20260728_0003`；full `1767 passed, 1 deselected, 12 warnings`；namespace contamination `0` |

01-07P 的三个 owned blob 为：

- `20260728_0003_request_understanding_v2_expand.py = bcd7dd85b4c5b82c764942ff0faf019d9e4744d0`
- `models.py = 892e8db7523ce1cd6c1032a9a6ad7d9d656f50fa`
- `test_database_migrations.py = 0db4cd0c369def837e656e1ae4824f793258c25e`

## Security, Eval and Lifecycle Boundary

- **Security:** exact pair admission不授予身份或 owner authority；unsupported pair、migration drift与 unsafe downgrade fail closed。Downgrade只观察 boolean existence，诊断不包含 row identity、owner、payload、count或 caller-controlled值。
- **Eval:** 只新增 migration / physical persistence integration contract，为后续 strict reader提供依赖；没有 Dataset、Grader、Trajectory、E2E Result、threshold或 Case lifecycle 变化。
- **Lifecycle:** `requirements_completed` 为空，canonical Case / Requirement 与派生 checkbox 均保持 `0/8`。
- **Nonclaims:** physical coexistence不等于 logical payload正确、active registry、reader/writer、Runtime、Provider/Eval、v1 retirement、真实 HTTP→PostgreSQL→Eval 纵向链或 readiness。

## Self-Check: PASSED

- 原始 blocked lineage、dedicated oracle remediation、r1 Plan、patch equivalence、feature/overlay review、serial merge与 exact `B_IP` 均有精确索引；
- three-file allowlist、linear migration chain、18-pair parity与 fail-closed downgrade证据闭合；
- 未把 physical admission、Component/Integration tests或 `B_IP` 描述为 active switch、Case PASS或产品完成。
