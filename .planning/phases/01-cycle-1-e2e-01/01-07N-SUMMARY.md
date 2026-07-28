---
phase: 01-cycle-1-e2e-01
plan: 07N
subsystem: request-understanding-v2-cutover-remediation
tags:
  - request-understanding
  - cutover
  - versioning
  - security
status: complete_evidence_indexed
completed_at: "2026-07-28T15:52:25+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-28"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 4a7e802e8aebc54e0582a1e4d99f140b56e7b131
planning_merge: 7dccac2eeffbc018fc901be2bce37978fb64c64a
published_head: 68a283f7160801033138aa399d26475317470028
integration_merge: a4b1edb4c50a2e3e826571194bac58f7b31eab6d
key_files:
  modified:
    - docs/implementation/e2e01-thin-slice-implementation-spec.md
metrics:
  feature_commits: 1
  files_changed: 1
  full_tests_passed: 1507
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07N｜Request Understanding v2 Cutover Remediation Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的01-07N cutover合同与可复现证据，不拥有通用Request Understanding、Core DTO、Application codec、migration、active routing、Eval或lifecycle语义。规范性内容仍由[Thin Slice owner](../../../docs/implementation/e2e01-thin-slice-implementation-spec.md)与[01-07N Plan](01-07N-PLAN.md)持有。

## Outcome

`01-07N`在Thin Slice owner单文件范围内冻结`p0-ru-v2-cutover-r1`，关闭旧E/F同base并行授权无法封闭的四类合同缺口：

- nested DTO与closed rejection边界；
- raw quote只用于当前Run的可信provenance replay，durable projection不保存raw quote；
- v1/v2按`CORE_EXPAND → CODEC_EXPAND → DEPENDENCY_EXPAND → ACTIVE_SWITCH → CONTRACT`分阶段迁移；
- 每个阶段的nonclaims、回滚与active-routing禁止项。

N只裁决cutover合同，不实现Core、codec、physical migration、Runtime、Provider/Eval、active registry或v1 removal。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / head / merge | [#62](https://github.com/weijie567/mini-agent/pull/62) / `8c9b37361b4e994a75bc813fd2c7f509f0bf5f90` / `7dccac2eeffbc018fc901be2bce37978fb64c64a` |
| Planning tree / Plan blob | `51bb417a9b26fe6df64d3adf555f99540c5f7654` / `f679872c424a53e9acbe59a4d5bc116d13b1dcc1` |
| Execution base | `4a7e802e8aebc54e0582a1e4d99f140b56e7b131` (`B_DH`) |
| Feature head / tree / owner blob | `68a283f7160801033138aa399d26475317470028` / `c75ba993d217901ba13c8c818cb901f336d0f2ad` / `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13` |
| Latest-integration overlay head / tree | `e6e14bf03bffd7323377cf25492cf2b9d323757d` / `469e26460c1041d9ca5042d39ae9a57ded7d5442` |
| Feature / overlay patch-id | `92daa4325143f94b6da88966a819d09637be0794`（identical） |
| Feature PR / integration merge / tree | [#63](https://github.com/weijie567/mini-agent/pull/63) / `a4b1edb4c50a2e3e826571194bac58f7b31eab6d` / `469e26460c1041d9ca5042d39ae9a57ded7d5442` |
| Mechanical contract gates | exact manifest byte equality；10/10 mutations；registry `17` / catalog `18`；future-symbol leakage `0` |
| Feature / overlay full suite | 各`1507 passed, 1 deselected, 12 warnings`；feature run `48.14s` |
| Independent review | feature与latest overlay均`PASS / CRITICAL-HIGH-MEDIUM-LOW = 0/0/0/0` |

## Security, Eval and Lifecycle Boundary

- **Security:** trusted identity、owner scope与最小披露没有扩大；raw Provider payload、Prompt、Token、PII与raw quote仍禁止进入普通durable/Trace/Eval surface。
- **Eval:** 本Packet只有owner contract与机械mutation/full-suite证据；没有新增EvalCase、Grader、Result或真实SUT证据。
- **Lifecycle:** `requirements_completed`为空；canonical lifecycle与派生checkbox保持`0/8`。N完成后reviewed feature口径从`18/39`变为`19/39`。
- **Handoff:** N只解锁01-07O execution-map alignment；不能直接签发F/E或解释为RU v2已可路由。

## Self-Check: PASSED

- exact lineage、one-file scope、patch identity、review、merge与测试证据均已索引；
- Core、codec、migration、routing、Eval与lifecycle缺口均明确保留；
- 用户已暂停Graphify，图不属于本Packet完成门禁。
