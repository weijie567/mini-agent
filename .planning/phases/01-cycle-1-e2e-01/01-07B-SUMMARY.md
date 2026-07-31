---
phase: 01-cycle-1-e2e-01
plan: 07B
subsystem: eval-evidence-boundary
tags:
  - evaluation
  - evidence
  - trace
  - security
status: complete_evidence_indexed
completed_at: "2026-07-27T23:33:50+08:00"
duration: "NOT_RECORDED"
completed: "2026-07-27"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: 8544137cfbcaebda603cd3000312fb5d2406327c
planning_merge: a1b04f26f668fd0842ad635ccf75d2a91220285c
published_head: d7fcfd345327b34df9af36459a2c5ea461e040d0
integration_merge: ccdafe87d5f118b729d6f3fff8635a0b92f3e3c5
key_files:
  modified:
    - src/mini_agent/evaluation/harness.py
    - src/mini_agent/evaluation/graders.py
    - src/mini_agent/evaluation/scripted_provider.py
    - tests/component/evaluation/test_e2e01_graders.py
    - tests/component/evaluation/test_e2e01_scripted_model_provider.py
    - tests/integration/evaluation/test_e2e01_offline_harness.py
metrics:
  feature_commits: 3
  files_changed: 6
  harness_tests_passed: 367
  owned_tests_passed: 725
  plan_focused_tests_passed: 762
  migration_tests_passed: 40
  full_tests_passed: 1493
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07B｜Eval Evidence Boundary Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并的 01-07B 实现与可复现证据，不拥有产品、Case、Dataset、Trace DTO、持久化、lifecycle 或发布语义。规范性边界仍服从 active canonical owners 与 [01-07B Plan](01-07B-PLAN.md)。

## Outcome

`01-07B` 已在 exact six-file Eval ownership 内关闭 01-08 preflight 暴露的 oracle 与 Trace precedence 阻断：

- SUT 只接收 opaque one-time `execution_ref`、closed role/content message 与可信 Session fixture ref，不接收 semantic Case / Script identity、expectations、grading 或答案字段；
- `ScriptedModelProvider` 只保留 closed behavior step、runtime fault directive 与独立 opaque execution identity，不保留完整 Script artifact 或 `expected_control_result`；
- SUT 只回传 unbound evidence / observable；Harness 在 one-time correlation、exact closed-tree、canonical rebuild 与 agreement 验证后独自绑定 authenticated `case_id`；
- `TraceCompletenessGrader` 对现有 16 个 script / 9 类 trajectory 验证 occurrence-aware、variant-scoped safety-causal partial order，缺失 endpoint 或适用 edge swap 失败，合法无关事件仍可通过；
- actual / expected mismatch 进入普通 grader `FAIL`，不能被 oracle-derived evidence 覆盖为 `PASS`；
- Harness 私有 correlation、Trace、ResultPort、grader、nonce、clock、replay cache 与公开 outcome 使用独立 canonical copies；所有 injected seam 的普通、`BaseException` 与 cancellation 出口恢复 canonical singleton state；
- exact replay 只复用成功持久化的完整 canonical stage；冲突 duplicate 不覆盖历史。

这些是 Component / in-process Eval 证据，不是 real `EvalCaseSut`、HTTP / PostgreSQL 纵向链、Trajectory / E2E Result 或 Case PASS。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Planning PR / merge | [#42](https://github.com/weijie567/mini-agent/pull/42) / `a1b04f26f668fd0842ad635ccf75d2a91220285c` |
| Planning contract blob | `6cd1b5a4c4d554f4adced7394f41de21cb0e7163` |
| Project Direction pre-execution status PR / merge | [#43](https://github.com/weijie567/mini-agent/pull/43) / `2adceaf11da995faa1c77d9173180579e09b0bdf` |
| Execution base | `8544137cfbcaebda603cd3000312fb5d2406327c` |
| Test-only RED | `8978655a68ca3364bedc021ecbac681ddce77990` |
| GREEN | `9a9680496dee49ca746a8d5f89e1c7ecebce07e4` |
| Final reviewed / remote head / tree | `d7fcfd345327b34df9af36459a2c5ea461e040d0` / `a806c2974f703c8cad2d39b142744e7eb14c8383` |
| Feature PR / evidence | [#44](https://github.com/weijie567/mini-agent/pull/44) / [final evidence](https://github.com/weijie567/mini-agent/pull/44#issuecomment-5093244542) |
| Latest-integration overlay | base `2adceaf11da995faa1c77d9173180579e09b0bdf` / head `91a62371280b98335b84fc7329e2efdad32d673f` / tree `8ccee77e93d241486d9c9ecddc881a6f410d58c0` |
| Integration merge / tree | `ccdafe87d5f118b729d6f3fff8635a0b92f3e3c5` / `8ccee77e93d241486d9c9ecddc881a6f410d58c0` |
| Scope / provenance | exact six owned files；RED → GREEN → one review-fix；feature / overlay aggregate patch-id与文件 blobs一致 |
| Harness / owned / Plan focused | `367 passed` / `725 passed` / `762 passed` |
| Migration / full | `40 passed` / `1493 passed, 1 deselected, 12 warnings` |
| Determinism | `PYTHONHASHSEED=1/2/42` 各 `725 passed` |
| Baseline preflight | missing env 与 synthetic env + real SUT not wired 均为 expected `SKIPPED / NOT_RUN`，零网络 |
| Independent review | final feature / overlay 双 reviewer `PASS`；unresolved Critical / High / Medium 均为 `NOT_FOUND` |

普通 HTTPS push 因 low-speed timeout 未更新 ref；Integrator 通过 Git Data API 逐层校验 blob、tree 与 reviewed commit object，并以 `force=false` 更新 feature ref。远端 PR head 已复读为 `d7fcfd34...`；该传输 fallback 不改变文件 tree 或 review 结论。

PR #44 最初把遗漏 `test_e2e01_artifact_consistency.py` 的五文件子集结果 `748 passed`误标为 Plan focused。Status exact-head review发现后，Integrator在相同代码 merge `ccdafe87...` 上按 Plan 原始六文件命令复跑为`762 passed`；full suite的`1493 passed`已包含这14项测试，代码结论不变，远端证据以纠正说明为准。

## Post-merge Gate

在 exact integration merge `ccdafe87...` 上：

- default full offline suite 为 `1493 passed, 1 deselected, 12 warnings`；
- `graphify update .` 完成 AST refresh，得到 4648 nodes、17000 edges、1373 communities；
- stale marker 不存在，tracked integration Worktree clean。

## Security, Eval and Lifecycle Boundary

- **Security:** semantic Case / Script identity、grader oracle、raw Provider context、Prompt、Token、credential、内部异常文本和不必要 PII 不跨越 SUT / Provider / Result 边界；`customer_id` 与授权语义没有变化。
- **Eval:** 仍缺 real `EvalCaseSut`、Request Understanding durable semantic / mapping / codec / Core 闭环、P0 `get_order` source-version / Core DTO、Application Evidence Port、PostgreSQL reader、Eval mapper、Composition Root、真实 HTTP / Trajectory / E2E Result 与 credentialed Qwen runner。
- **Lifecycle:** `requirements_completed` 为空；`E2E01-01/04` 与派生 checkbox 继续保持 `CONTRACT_DEFINED / 0/8`。Task Packet 证据口径从 `13/28` 更新为 `14/28`，不等于产品或 Phase 完成 50%。
- **Handoff:** 01-07C RU semantic ruling 与 01-07G Thin Slice `get_order` source-version ruling可在本状态对齐 PR reviewed merge后的同一 exact integration SHA 上分别签发；两个 owner Packet 可并行写入独立 Worktree，但仍由 Integrator 串行合并形成下一 barrier。

## Self-Check: PASSED

- planning、RED/GREEN、feature、overlay、merge、测试、review、Graphify 与远端证据均有精确引用。
- feature / overlay changed-file set均精确等于 six-file allowlist，merge tree等于 reviewed overlay tree。
- 已显式保留真实纵向链、credentialed Baseline 与 `0/8` lifecycle 缺口，没有把 in-process Harness 证据描述成 Case PASS。
