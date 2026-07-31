---
phase: 01-cycle-1-e2e-01
plan: 07
subsystem: evaluation
tags:
  - evaluation
  - graders
  - qwen
status: complete_evidence_indexed
completed_at: "2026-07-27T07:40:38Z"
duration: "NOT_RECORDED"
completed: "2026-07-27"
requirements:
  - E2E01-01
  - E2E01-04
requirements_completed: []
execution_base: c35687dafa3881bb322d91515068d8d39be79df6
planning_merge: 968b4a9fffa446a789f69cce9f04e1c49148d40f
published_head: b8ecbb0a7d69761911213a8433b50c6062116c79
integration_merge: eee1c0e46e1bca1160dea54d586d477c173daadc
key_files:
  added:
    - src/mini_agent/evaluation/artifacts.py
    - src/mini_agent/evaluation/graders.py
    - src/mini_agent/evaluation/harness.py
    - src/mini_agent/evaluation/scripted_provider.py
    - src/mini_agent/infrastructure/model/qwen_responses.py
    - tests/baseline/test_qwen_baseline.py
    - tests/component/evaluation/test_e2e01_graders.py
    - tests/component/evaluation/test_e2e01_scripted_model_provider.py
    - tests/component/evaluation/test_e2e01_versioned_artifact_loader.py
    - tests/component/model/test_qwen_responses_adapter.py
    - tests/integration/evaluation/test_e2e01_offline_harness.py
metrics:
  feature_commits: 15
  files_changed: 11
  focused_tests_passed: 191
  migration_tests_passed: 40
  full_tests_passed: 936
  full_tests_deselected: 1
---

# Phase 1 Packet 01-07｜W2 Offline Eval Summary

> **DERIVED / NON_NORMATIVE**
> 本 Summary 只索引已合并 Eval loader、Provider、grader、Harness与 baseline prerequisite 的 Component / in-process 证据，不拥有产品、Runtime / Infra contract、Case lifecycle或发布语义。规范性边界仍服从 active canonical owners 与 [01-07 Plan](01-07-PLAN.md)。

## Outcome

`01-07` 已在原并行 feature identity上完成实现，并在 Runtime / Infra reviewed merge后通过 latest-integration overlay：

- manifest、fixture、case、model script与lane按 closed path / exact-byte SHA-256 / version / reference graph认证；
- `ScriptedModelProvider` 按 model-purpose、script cursor与版本绑定离线执行，非法输出只产生 fresh bounded protocol error；
- `QwenResponsesAdapter` 使用固定模型与 closed request/response allowlist，Component test只使用 MockTransport；
- 13 个 grader完全从 authenticated expectations与 typed evidence计算，不读取 legacy assertion booleans，也不能被自定义 runner绕过；
- `OfflineEvalHarness` 严格区分 complete Case Result 与 execution-system failure，确保 pair completeness、append-only attempt与 Trace finalization；
- `E2E01-04-A/B` 的安全 observable equivalence由 Harness成对验证；
- default lane无网络，`qwen_baseline` 在缺凭据或没有 real `EvalCaseSut` 时写入空 `NOT_RUN`并可报告 expected skip；
- primitive subclass、raw enum、supersedes、Observation storage和 typed reference graph审查缺口均已关闭。

本 Packet使用 injected synthetic / in-process SUT证明 Eval machinery，不把它描述为真实 Runtime、HTTP、PostgreSQL Trajectory / E2E或产品完成。

## Exact Evidence

| Evidence | Exact value / result |
|---|---|
| Original planning PR / merge | [#26](https://github.com/weijie567/mini-agent/pull/26) / `968b4a9fffa446a789f69cce9f04e1c49148d40f` |
| 01-07 Plan Git blob / exact-byte SHA-256 | `7019e29e061e38c8f9ba81141e153d6486e4cfba` / `dac5514b69b5d0d7b57b6b75c15267d1cf63919f0d9c12407cdba6a8c13dfce3` |
| Feature PR / reviewed head / tree | [#29](https://github.com/weijie567/mini-agent/pull/29) / `b8ecbb0a7d69761911213a8433b50c6062116c79` / `4c894379c4e6add7ac2c1c88da0d43d18c15a480` |
| Latest integration overlay | parent `8e21652fbfcba4e9efb351e298b9a0c58f4a46d8` / head `ee46f38b14a1a8d8a1c98cbfb9d1f4c6a3a06ace` / tree `762bcb22284f3b5fdbc2ace1ef28ec982fc3a65d` |
| Integration merge / tree | `eee1c0e46e1bca1160dea54d586d477c173daadc` / `762bcb22284f3b5fdbc2ace1ef28ec982fc3a65d` |
| Scope / range-diff | exact 11 owned files；15 commits全部 `=`；feature/overlay owned blobs相同 |
| Focused / migration / full | `191 passed` / `40 passed` / `936 passed, 1 deselected` |
| Baseline preflight | missing env → `MISSING_REQUIRED_ENV`；credential-shaped env + no real SUT → `REAL_EVAL_CASE_SUT_NOT_WIRED`；两者均 expected skip且零网络 |
| Independent review | feature `PASS / NOT_FOUND`；latest-integration overlay双路 `PASS / NOT_FOUND` |

Artifact exact-byte SHA-256：

- fixture `3940f5755ab001339d254077b36b3ae2965e590adee43ea0fb4e1d7cd2648c33`
- cases `58622417bf2221ded9951a8f41c29bdfd2d5fbe71109ade64c1b52f27ede4440`
- model scripts `2b42415c1c705b30b34f7a80d810726d59f7891da52daa390208d62fa1aa7176`
- lanes `61e43e8a560c3b31d1444759360941bb038d41a94ee1326be7c8cce52808158d`
- manifest `ffd9d3f130813e3acec347c4ab23fc4372a0969288c35120e72aa8650fa7b8bd`

## Post-merge Gate

在 exact integration merge `eee1c0e...` 上：

- Eval focused suite为 `191 passed`；
- migration regression为 `40 passed`；
- default full offline suite为 `936 passed, 1 deselected`；
- 两条 baseline preflight均得到预期的 `NOT_RUN / SKIPPED` 且零网络；
- compileall与 `git diff --check` 通过；
- `graphify update .` 得到 4354 nodes、12277 edges、1376 communities；
- stale marker不存在，tracked integration Worktree clean。

## Open 01-07A / 01-08 Integration Blockers

真实纵向证据不得由 Eval 层补造。下列1–3由Runtime-owned `01-07A`作为01-08前置条件关闭：

1. `ContextManifestRecorded` 写入真实 `model_call_purpose`，分别为 `REQUEST_UNDERSTANDING` 与 `PRESENTATION`；
2. 每条受控固定错误 / not-found结果在真实 deterministic rendering 点产生 `ResponseRendered`；
3. stale-state hook通过 canonical `ApplyTaskTransitionCommand`形成 `ACTIVE/v1 → WAITING_USER/v2`并追加真实第二个 `TaskStateChanged`，随后 Gateway拒绝和终态形成第三个；

`01-07A` reviewed merge后，01-08只负责Composition Root与纵向接入：

4. real `EvalCaseSut` 从 HTTP / PostgreSQL / Runtime实际记录读取 typed evidence，不重编码 Observation、不复制 artifact事实、不合成缺失 Trace。

## Security, Eval and Lifecycle Boundary

- **Security:** artifact provenance、no-network、bounded failure、no-leak grading与 pair equivalence 已有 Eval Component证据。
- **Eval:** real SUT不存在时 baseline保持 `NOT_RUN`；没有任何 credentialed Qwen Result或真实 HTTP / PostgreSQL Case PASS。
- **Lifecycle:** `requirements_completed`为空；`E2E01-01/04`、numbered Phase与派生checkbox均未推进。
- **Cross-file status:** business / Eval active owners中的实现状态文字仍停留在W1，须由对应owner独立对齐；本Summary不静默覆盖它们。
- **Handoff:** 先由Runtime sole writer执行01-07A；其merge与owner status alignment通过后，01-08再由Integrator single-writer接入 Composition Root、real Eval SUT、PostgreSQL evidence reader与纵向门禁。

## Self-Check: PASSED

- feature、overlay、merge、artifact hash、测试、preflight、review与Graphify证据均有精确引用。
- feature与overlay changed-file set均精确等于11-file allowlist。
- 已显式记录 real 01-08 blockers，没有用 synthetic evidence掩盖 Runtime / Infra缺口。
