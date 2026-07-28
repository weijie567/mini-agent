---
phase: 01-cycle-1-e2e-01
plan: 07I
subsystem: request-understanding-v2-application-dependency-expand
tags:
  - request-understanding
  - application
  - persistence
  - eval
  - security
status: complete_evidence_indexed
completed_at: "2026-07-29T01:52:37+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-29"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 294ada386ec160ec2a48fc8883b5a38f1880e4ba
planning_merge: 24451c7103b553023546549aebdeb3e3421cbe8a
published_head: b67023c141f5cbc71dcfc00758f8b6ab0af4de48
integration_merge: b14a15d60b17eda8d8b5aed892c5d00f16005310
key_files:
  modified:
    - src/mini_agent/application/records.py
    - src/mini_agent/application/ports.py
    - tests/component/application/test_record_contracts.py
    - tests/component/application/test_ports_contract.py
metrics:
  feature_commits: 9
  files_changed: 4
  focused_tests_passed: 357
  full_tests_passed: 1759
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07I｜Request Understanding v2 Application Dependency Expand Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引 01-07I `DEPENDENCY_EXPAND` 的已合并实现与可复现证据，不拥有 Request Understanding、Memory、physical persistence、Provider Adapter、Runtime、Eval mapper、active switch 或 lifecycle 语义。规范性内容仍由 [Intent owner](../../../docs/architecture/intent-design-reference.md)、[Memory owner](../../../docs/architecture/memory-design-reference.md)、[Thin Slice owner](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)、[execution map](../../../docs/implementation/e2e01-thin-slice-multi-agent-plan.md) 与 [01-07I Plan](01-07I-PLAN.md) 持有。

## Outcome

`01-07I` 已从 exact `B_FE_EXPAND` 以 additive、non-routable 方式增加 Application dependency surface：

- `RequestUnderstandingCandidateInvalidError` 是 parameterless、固定诊断、与 `ProviderProtocolError` 分离的 bounded signal；
- `ModelProviderV2` 显式返回 `RequestUnderstandingOutputV2`，现有 v1 `ModelProvider` 与 active consumers 保持不变；
- `ExactRunEvidenceClosure` 表达 expectation-free、owner-scoped、exact-Run logical record graph，并对 identity、relation、cardinality、version/history、provenance 与 root reachability 做整体闭合校验；
- `ExactRunEvidencePort` 冻结不可区分的 absent / unauthorized read、同一 transactionally-consistent snapshot 或等价 exact fence、strict decode 与数据库 closed-set 责任；
- 没有实现 PostgreSQL reader、Provider translation、Runtime catch、Eval mapper、Composition Root、active routing 或 v1 retirement。

01-07I 的 reviewed merge 本身不形成 symbolic barrier；01-07P 随后完成 remediation replay、review 与串行合并后才共同形成 `B_IP`。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / head / merge | [#80](https://github.com/weijie567/mini-agent/pull/80) / `2deb556fc13e23ef200b7b56a3aff9439a74b671` / `24451c7103b553023546549aebdeb3e3421cbe8a` |
| Final Plan blob | `15e114001cb81fdcf457f12a5156c9ed00085cbd` |
| Execution base | `294ada386ec160ec2a48fc8883b5a38f1880e4ba`（`B_FE_EXPAND`） |
| Feature head / tree | `b67023c141f5cbc71dcfc00758f8b6ab0af4de48` / `c2d2b90c3be8206441e28ec7d3a92718cf940884` |
| Latest-integration overlay base / tree | `7a476bada3fb13a7c1eee90023c18569f7407d48` / `0825efeff47730e17974ea7d65bfd3af9a58fe51` |
| Feature PR / integration merge / tree | [#83](https://github.com/weijie567/mini-agent/pull/83) / `b14a15d60b17eda8d8b5aed892c5d00f16005310` / `0825efeff47730e17974ea7d65bfd3af9a58fe51` |
| Scope | exact 9 commits、4 owned files；RED → GREEN → 7 append-only review fixes |
| Focused / full suite | final `357 passed`；`1759 passed, 1 deselected, 12 warnings` |
| Independent review | feature与latest overlay最终均为 `CRITICAL/HIGH/MEDIUM/LOW = 0/0/0/0`、`PASS / MERGE` |

01-07I 的四个 owned blob 为：

- `ports.py = 4b4d5c7556f13a072a8fb83cfcf539441f76eaa1`
- `records.py = 53372a47d1aded5f02afa958f7dcec96fccf1688`
- `test_ports_contract.py = 3e0143a67b7ff1bdd229938d9264c6414f40e911`
- `test_record_contracts.py = 4ad7cec6e5dcc230c4007ecca08eabbc41a05acc`

## Security, Eval and Lifecycle Boundary

- **Security:** Port input只接受可信 `owner_scope` 与 exact `run_id`；`None` 不区分不存在和未授权，已选 owner root 后的 integrity failure fail closed。Closure不携带独立 `customer_id`、Case expectation、raw envelope、HTTP observable或 grader Result。
- **Eval:** 只新增 expectation-free evidence closure / Port 的 Application Component contract，为后续 01-07K/01-07L 提供边界；没有 Dataset、Grader、Trajectory、E2E Result、threshold或 Case lifecycle 变化。
- **Lifecycle:** `requirements_completed` 为空，canonical Case / Requirement 与派生 checkbox 均保持 `0/8`。
- **Nonclaims:** PostgreSQL exact reader、physical closed-set proof、Provider Adapter、Runtime mapping、Eval evidence mapper、active routing、v1 retirement与 readiness 均未完成。

## Self-Check: PASSED

- exact base、Plan、feature、overlay、review、merge、scope与测试证据均有精确索引；
- four-file allowlist、owner-scoped closure与 protected-v1 gate闭合；
- 未把 Application declaration、Component tests或单独 I merge描述为 `B_IP`、真实纵向链、Case PASS或产品完成。
