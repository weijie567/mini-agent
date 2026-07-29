---
phase: 01-cycle-1-e2e-01
plan: 07S
type: tdd
wave: 28
depends_on:
  - 01-07I
  - 01-07L
  - 01-07J
files_modified:
  - src/mini_agent/evaluation/harness.py
  - src/mini_agent/evaluation/graders.py
  - src/mini_agent/evaluation/scripted_provider.py
  - src/mini_agent/infrastructure/model/qwen_responses.py
  - tests/component/evaluation/test_e2e01_artifact_consistency.py
  - tests/component/evaluation/test_e2e01_graders.py
  - tests/component/evaluation/test_e2e01_scripted_model_provider.py
  - tests/component/model/test_qwen_responses_adapter.py
  - tests/integration/evaluation/test_e2e01_offline_harness.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Eval与Provider active source只消费ModelProviderV2、RequestUnderstandingOutputV2、RequestUnderstandingRecordV2和AcceptedTaskDeltaV2；不得保留v1 Provider实现、v1 RU output/evidence branch、union/fallback或dynamic version selection。"
    - "ScriptedModelProviderV2与QwenResponsesAdapterV2必须成为独立canonical Provider实现，不得再继承或委托legacy Provider；既有bounded candidate-invalid/protocol taxonomy、raw-data detachment与traceback-local安全保证保持。"
    - "Offline Harness必须显式构造并向真实EvalCaseSut传入ScriptedModelProviderV2；case/script expectations仍只在authenticated Harness边界绑定，不得进入Provider、case-free mapper或EvalEvidence。"
    - "EvalEvidence与13个grader只接受durable v2 RU record/accepted child/task transition闭包；删去transient v1 RequestUnderstandingOutput、v1 durable record/child与伪造physical envelope分支，bypass/mixed/noncanonical输入继续fail closed。"
    - "tracked evals/*.v1.json文件及其中稳定artifact/provider标签保持byte-identical；它们是Dataset/fixture版本标识，不得被解释为仍存在的Python v1 Provider合同，也不得由S越权修改。"
    - "01-07S不得修改Application Runtime、Application Port/records、Core、PostgreSQL、migration、Composition Root、tracked Eval artifacts、canonical owner或lifecycle；S单独merge不形成B_SU。"
  artifacts:
    - "四个source文件中的v2-only Provider/Harness/Grader surface。"
    - "五个owned test文件中的Provider v2、v2-only evidence、failure taxonomy、artifact non-activation和offline Harness证据。"
  key_links:
    - "01-07L additive Provider/mapper surface → 01-07S destructive v1-contract closure。"
    - "ScriptedModelProviderV2 → EvalCaseSut.execute_case → actual AgentRunService ModelProviderV2 boundary。"
    - "ExactRunEvidenceClosure → case-free mapper → v2-only EvalEvidence → 13 deterministic graders。"
    - "B_ACTIVE = 7f92b5e... → 01-07S；与同base的01-07U均reviewed串行merge后才形成B_SU。"
---

# Phase 1 Plan 01-07S｜Eval Provider v1-contract closure

> **ISSUED CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只删除Eval / Provider owner内已被01-07L/J替代的Request Understanding v1合同。Plan、RED test、feature head或单独S merge均不形成`B_SU`；只有S与U各自完成exact-head review、latest-integration replay、串行merge和共同post-merge gate后才可命名该barrier。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、Eval lifecycle与Thin Slice业务语义仍由active canonical owner拥有。本Plan只消费marker-bounded execution map中的S ownership，不建立第二套产品或架构合同。Graphify按用户指令保持闲置，不读取、不运行、不更新、不作为gate。

<objective>
以TDD RED→GREEN关闭Eval Provider owner中仍保留的RU-v1双轨面，使offline Harness、Scripted/Qwen Provider、case-free mapper、EvalEvidence与grader只接受reviewed v2合同。

Purpose: `B_ACTIVE`上的真实Runtime已只接受`ModelProviderV2`，但Eval owner仍通过legacy Provider基类/继承、Harness v1 provider annotation/constructor，以及EvalEvidence/grader的v1/v2双分支保留可路由v1表面。S删除这些兼容面，并保持artifact输入、failure taxonomy、安全边界及v2 evidence oracle不退化。

Output: 一个九文件feature Packet。第一提交修改owned tests形成可解释RED；第二提交只修改四个owned source文件形成GREEN；review remediation只追加线性fix commits。不得创建Summary、修改共享State或改写tracked Eval JSON。
</objective>

<preflight_evidence>

- `CONFIRMED`：feature input必须是exact `B_ACTIVE=7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`，tree `f70b20215e569acf3ad196cc050e9a23700d4bae`；后续PR #125–#129均为status/docs-only，`git diff B_ACTIVE..integration -- src tests`为空。
- `CONFIRMED`：`harness.py`仍import、annotation、construct `ScriptedModelProvider`；`scripted_provider.py`与`qwen_responses.py`仍以V2 subclass继承v1 Provider并保留`RequestUnderstandingOutput`生成路径。
- `CONFIRMED`：`EvalEvidence`仍含`request_understanding_output`、`request_understanding_records`、`accepted_task_deltas`及`observation_persistence_envelopes`，grader仍保留双分支；01-07L明确这些legacy fields/branches只保留到01-07S。
- `CONFIRMED`：J-owned `tests/integration/test_agent_run_service_v2_persistence.py`在allowlist外仍直接import `ScriptedModelProviderV2`；S必须保留这个canonical public name，不能把V2偷偷重命名成legacy name。
- `CONFIRMED`：tracked `evals/*.v1.json`与`tests/component/model/test_e2e01_scripted_scenario_catalog.py`在S allowlist外；其中`ScriptedModelProvider`/`QwenResponsesAdapter`字符串只可作为冻结artifact标签保留，S不得借合同清理越权改写。
- `OPEN / NONCLAIM`：zero/all-REJECT、multi-ACCEPT、atomic recovery、Infrastructure/Application/Core v1 surface与Composition Root仍由后续owner处理；S不得实现或宣称完成。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07L-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07J-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/evaluation/agent-evaluation-strategy.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/evaluation/harness.py
@src/mini_agent/evaluation/graders.py
@src/mini_agent/evaluation/scripted_provider.py
@src/mini_agent/infrastructure/model/qwen_responses.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-v1-provider-contract`

feature_worktree: `e2e01-01-ru-v1-provider-contract`

writer: `/root Integrator / Eval Provider nine-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`

base_tree: `f70b20215e569acf3ad196cc050e9a23700d4bae`

input_barrier: `B_ACTIVE`

output_barrier: `B_SU / ONLY AFTER 01-07S AND 01-07U REVIEWED SERIAL MERGES AND JOINT POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/evaluation/harness.py` = `20979ff414e9da19a09d9ab1c10cdc7113985e6b`
- `src/mini_agent/evaluation/graders.py` = `e1fdd3e18882cd95e5f5edcf848ae95eb988098f`
- `src/mini_agent/evaluation/scripted_provider.py` = `c62c659fc7e3023ae4196db6b108f126b0307051`
- `src/mini_agent/infrastructure/model/qwen_responses.py` = `9dc181f212fb08f2ef975c6e7eee52d003415d3e`
- `tests/component/evaluation/test_e2e01_artifact_consistency.py` = `0263e4f9ca981f309996efd5f291d4e6ba5e6cd7`
- `tests/component/evaluation/test_e2e01_graders.py` = `da14aa0afb0aff188059ad9572ae04249220b505`
- `tests/component/evaluation/test_e2e01_scripted_model_provider.py` = `d0777f5c2433683bec1a4d5b4048fd2b65bf13ce`
- `tests/component/model/test_qwen_responses_adapter.py` = `8109b1d19e67f8598660f82bcbb42449fbe7f87b`
- `tests/integration/evaluation/test_e2e01_offline_harness.py` = `af6836bbcfb22a591b5097ce6e94506b206d9d74`

allowlist: the exact nine paths above.

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE NINE-FILE ALLOWLIST`，尤其包括`evals/**`、`src/mini_agent/application/**`、`src/mini_agent/core/**`、other `src/mini_agent/infrastructure/**`、other `tests/**`、`tests/conftest.py`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree从latest integration创建并只拥有本Plan文件；Plan merge只记录签发，不得替换feature `base_sha`。feature必须从上述exact base另建clean Worktree。

## 2. Provider v2-only contract

- `ScriptedModelProviderV2`保留public name，直接拥有constructor、cursor/runtime-fault、v2 `propose_next_move`、Presentation与exhaustion行为；其MRO不得包含legacy `ScriptedModelProvider`，module不得再定义或导出后者。
- `QwenResponsesAdapterV2`保留public name，直接拥有injected HTTP configuration、v2 `propose_next_move`与Presentation；其MRO不得包含legacy `QwenResponsesAdapter`，module不得再定义或导出后者。
- 两个Provider必须结构化满足`ModelProviderV2`，不得满足或引用`ModelProvider`；active module source不得import或construct`RequestUnderstandingOutput`。
- 可以提取private非Provider helper，但不得建立public alias、version parameter、union return、default/latest或fallback。Harness与tests必须显式使用V2 public name。
- candidate-invalid与protocol partition、fresh parameterless signals、cause/context清空、raw envelope/credential/identity从最终traceback frame locals不可达等01-07L安全合同保持。

## 3. EvalEvidence and grader v2-only contract

- `EvalEvidence`删除`request_understanding_output`、`request_understanding_records`、`accepted_task_deltas`和`observation_persistence_envelopes`字段；相同名称不得以property、alias、extra、compat parser或unchecked dict保留。
- `_UNBOUND_EVIDENCE_FIELD_ALLOWLIST`与case-free mapper同步删除上述字段；mapper仍只从`ExactRunEvidenceClosure` exact-copy logical v2 records，不fabricate transient output或physical envelope。
- 13个grader名称、顺序、reason taxonomy与authenticated expectation boundary保持；RU/InputBinding/Task/Tool/Observation/Persistence/Trace路径只走v2 durable graph。
- no-RU terminal evidence允许v2 tuples全空；有v2 parent时accepted refs与children必须闭合；mixed/bypass/noncanonical Pydantic实例仍在construction或grader strict revalidation fail closed。
- 删除legacy branch不能用放宽required-record、减少identity/source-version校验、读取expectation补evidence或删除directed-tamper矩阵替代。v2 source span/hash、Task transition、Tool/Gate/Observation/Manifest、owner/Run identity与exact source-version gates保持。

## 4. Artifact and naming boundary

- `evals/*.v1.json` byte-identical，manifest hash与artifact paths不变；S没有Dataset writer权限。
- artifact内`provider_adapter` / `provider`的稳定字符串标签不自动等于Python class import name。Artifact consistency test必须显式区分“冻结数据标签”与“active code只有V2 Provider”。
- 不修改artifact loader、Case schema、expectations或lane activation；不把S描述为Dataset v2 migration、Case PASS、credentialed Qwen baseline或真实HTTP装配。

## 5. Commit, replay and barrier protocol

1. RED commit只修改owned tests，至少证明legacy Provider symbol/继承、Harness legacy construction与EvalEvidence legacy fields当前存在而失败。
2. GREEN source commit只修改四个owned source；test migration/remediation使用后续线性commit，不得rewrite history。
3. exact-head review前必须证明base/parent/allowlist、无merge commit、所有v1 RU symbols在四source与五tests中为零；非RU `*.p0.v1`/artifact filename/version常量不作为机械删除目标。
4. S exact-head PASS后，在latest integration上建立只读/throwaway overlay，验证无冲突、禁止文件blob与功能gate；S可先串行merge，但不得命名`B_SU`。
5. U从同一原exact B_ACTIVE独立实现并review；两者均merge后才运行joint post-merge gate并记录`B_SU`。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结Provider继承清除、Harness v2注入和EvalEvidence v2-only surface</name>
  <files>五个owned test文件</files>
  <action>
    新增/迁移测试，要求两个V2 Provider不再有legacy基类或symbol，Harness协议与constructor只接受ScriptedModelProviderV2，EvalEvidence schema不含四个legacy field，13 grader只消费v2 evidence。保留failure taxonomy、raw-local扫描、artifact byte/hash与case/script不渗入证据的既有测试。仅提交测试并记录可解释RED；不得通过删除所有断言制造RED。
  </action>
  <verify>
    <automated>uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_graders.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py tests/integration/evaluation/test_e2e01_offline_harness.py -q</automated>
  </verify>
  <done>RED只由待删除legacy surface触发；无越权文件。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — Provider与Harness切为v2-only</name>
  <files>scripted_provider.py, qwen_responses.py, harness.py及相关owned tests</files>
  <action>
    将两个V2 Provider改为独立实现并删除legacy class/output path；Harness import、Protocol与case staging显式使用ScriptedModelProviderV2。保持public constructor、script cursor、runtime fault、Presentation、Qwen request allowlist与bounded failure安全合同。更新owned tests但不得修改tracked artifacts或J-owned integration test。
  </action>
  <verify>
    <automated>uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py tests/integration/test_agent_run_service_v2_persistence.py -q</automated>
  </verify>
  <done>active Provider/Harness code无legacy Provider或RequestUnderstandingOutput依赖，J exact-run integration仍绿。</done>
</task>

<task type="auto">
  <name>Task 3: GREEN — EvalEvidence与13 grader删除v1 branch</name>
  <files>graders.py, harness.py及三个owned Eval tests</files>
  <action>
    删除四个legacy evidence fields、unbound allowlist项、v1 validation/graph/grader/persistence分支与相应旧fixture；把保留的通用grader test迁移到durable v2 evidence。继续覆盖no-RU terminal、exact-one、tamper、noncanonical bypass、identity/source provenance、source-version、trace与safe response policy。
  </action>
  <verify>
    <automated>uv run pytest tests/component/evaluation/test_e2e01_graders.py tests/integration/evaluation/test_e2e01_offline_harness.py -q</automated>
  </verify>
  <done>EvalEvidence只存在v2 RU闭包；13 grader和offline Harness gates全绿。</done>
</task>

<task type="auto">
  <name>Task 4: exact-head review、latest overlay与S merge gate</name>
  <files>exact nine-file allowlist</files>
  <action>
    执行scope/commit containment、`git diff --check`、targeted、Eval-owned、Application neighbor、database/full gates和独立exact-head review。Reviewer发现必须在线性fix commit关闭并重审。PASS后在latest integration重放；确认与U独立同base且S单独不命名B_SU。
  </action>
  <verify>
    <automated>uv run pytest</automated>
  </verify>
  <done>reviewed S可串行merge，contract/security/eval影响与未决范围完整交接。</done>
</task>

</tasks>

<verification>

最低机械gate：

```bash
git diff --check
uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_graders.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py tests/integration/evaluation/test_e2e01_offline_harness.py -q
uv run pytest tests/integration/test_agent_run_service_v2_persistence.py tests/component/application/test_agent_run_service.py -q
uv run pytest tests/component/evaluation tests/component/model/test_qwen_responses_adapter.py tests/integration/evaluation -q
uv run pytest
```

exact-head与latest overlay必须额外检查：

- parent chain以exact `B_ACTIVE`起始、无merge commit；
- changed files精确包含于九文件allowlist；
- `evals/**`及全部禁止文件blob与base一致；
- source不再定义/import legacy Provider与v1 RU output/evidence fields；
- frozen artifact SHA和lane/script labels不变；
- independent reviewer `P0/P1/P2/P3 = 0/0/0/0`。

</verification>

<contract_changes>

`SCOPED / EXECUTION-MAP AUTHORIZED`：只在Eval Provider owner内删除RU-v1 compatibility surface；active canonical产品、Intent、Memory、Tool、Eval lifecycle语义不变。`ScriptedModelProviderV2`、`QwenResponsesAdapterV2`、v2-only `EvalEvidence`与case-free mapper成为该owner唯一实现面。

</contract_changes>

<security_impact>

`SECURITY_PRESERVING`：不改变可信身份来源、授权、资源归属、最小披露、Evidence或Action边界。必须保持Provider bounded signal raw-detachment、Harness oracle isolation、case/script identity不进入SUT evidence，以及v2 durable provenance/identity fail-closed。

</security_impact>

<eval_impact>

`COMPONENT / INTEGRATION CONTRACT MIGRATION ONLY`：把既有Eval Component/Integration oracle从双轨迁到v2-only；不修改Dataset、不新增Case、不推进`CONTRACT_DEFINED / 0/8` lifecycle，不宣称Trajectory/E2E PASS或credentialed baseline。

</eval_impact>

<rollback>

若exact-head或overlay失败，不合并feature，保留branch/commit/test输出供审查；修复必须追加allowlist内线性commit。若merge后发现回归，以普通revert S merge恢复，不reset/force，不修改S/U原exact base或冻结execution map。

</rollback>

<handoff>

- branch / exact head / tree / parent chain；
- 实际changed files与allowlist containment；
- RED/GREEN/fix commits；
- 执行命令、通过/失败/未执行项；
- legacy symbol scan、artifact byte/hash、neighbor/full结果；
- independent exact-head与latest-overlay verdict；
- contract/security/eval impact与OPEN风险；
- 明确`S MERGED != B_SU`，等待同base 01-07U reviewed merge和joint post-merge gate。

</handoff>
