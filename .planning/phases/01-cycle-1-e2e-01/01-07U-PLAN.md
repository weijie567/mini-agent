---
phase: 01-cycle-1-e2e-01
plan: 07U
type: tdd
wave: 28
depends_on:
  - 01-07J
files_modified:
  - src/mini_agent/application/agent_run_service.py
  - src/mini_agent/application/read_tool_executor.py
  - tests/component/application/test_agent_run_service.py
  - tests/component/application/test_read_tool_executor.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Application Runtime active source必须继续只接受ModelProviderV2、validate_and_reduce_initial_request_v2、CreateInitialTaskGraphV2Command与create_initial_task_graph_v2_if_current；不得出现v1 reducer、command、Port调用、alias、fallback、union或dynamic probing。"
    - "01-07J已经删除production Runtime的RU-v1调用面；01-07U只关闭owned tests中剩余的legacy create_initial_task_graph_if_current test-double method，并把v2-only AST/API guard固定为可复现合同，不能为了制造实现量改写已reviewed J source。"
    - "ReadToolExecutor不拥有Request Understanding版本路由，source与Component test应保持B_ACTIVE blob不变；get_order source_version的mock-order-source-version.p0.v1格式是01-07G/K/M业务事实合同，不属于U删除范围。"
    - "conversation/message/link、Presentation、tool registry、redaction及order source-version中的p0.v1/v1字符串不是RU-v1 Runtime surface；U不得用全局字符串替换破坏其他owner合同。"
    - "01-07U不得修改Application Port/records、Core、Eval Provider、PostgreSQL、migration、Composition Root、canonical owner或lifecycle；U单独merge不形成B_SU。"
  artifacts:
    - "AgentRunService v2-only source/AST contract test与不再暴露legacy writer method的Runtime test double。"
    - "B_ACTIVE source blob preservation、focused Runtime regression与S/U共同barrier证据。"
  key_links:
    - "01-07J active Runtime switch → 01-07U owner-local compatibility-test closure。"
    - "AgentRunService → ModelProviderV2 → v2 reducer → v2 Application command/Port。"
    - "B_ACTIVE = 7f92b5e... → 01-07U；与同base的01-07S均reviewed串行merge后才形成B_SU。"
---

# Phase 1 Plan 01-07U｜Application Runtime v1-contract closure

> **ISSUED CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只关闭Application Runtime owner中01-07J切换后仍残留于测试替身的RU-v1兼容方法，并固化production source无v1 routing的结构证据。Plan、RED/GREEN head或单独U merge均不形成`B_SU`。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、Tool、source-version与产品结果语义仍由active canonical owner拥有。本Plan只消费marker-bounded execution map中的U ownership，不建立第二套合同。Graphify按用户指令保持闲置，不读取、不运行、不更新、不作为gate。

<objective>
以最小TDD变更关闭Application Runtime owner最后一处可调用RU-v1 test surface，同时证明01-07J已reviewed的production Runtime仍是显式v2-only。

Purpose: `B_ACTIVE`上的`AgentRunService`已经不再import/use v1 reducer、command或writer，但`tests/component/application/test_agent_run_service.py`中的Runtime port double仍定义`create_initial_task_graph_if_current`。该方法会让owned contract test继续暴露一个看似可路由的legacy入口。U删除该入口并以AST/source guard证明没有通过substring、alias或dynamic probing恢复v1。

Output: 一个四文件allowlist、预期只修改一个owned test文件的feature Packet。RED commit先增加精确结构断言；GREEN commit再删除legacy test-double method。两个production source和`test_read_tool_executor.py`预期byte-identical；任何必须修改它们的发现都应先BLOCK并重新裁决，而不是扩张U。
</objective>

<preflight_evidence>

- `CONFIRMED`：feature input必须是exact `B_ACTIVE=7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`，tree `f70b20215e569acf3ad196cc050e9a23700d4bae`；PR #125–#130均为planning/status/docs-only，`git diff B_ACTIVE..integration -- src tests`为空。
- `CONFIRMED`：AST扫描在两个production source中没有`ModelProvider`、`RequestUnderstandingOutput`、`validate_and_reduce_initial_request`、`SaveRequestUnderstandingCommand`或`create_initial_task_graph_if_current` exact legacy symbol；`AgentRunService`只引用相应V2合同。
- `CONFIRMED`：唯一剩余owner-local legacy callable是`test_agent_run_service.py`测试替身在line 390定义的async `create_initial_task_graph_if_current`；它只抛AssertionError，production从不调用。
- `CONFIRMED`：`read_tool_executor.py`没有RU版本依赖；其中`mock-order-source-version.p0.v1:sha256:*`正则及对应tests来自独立order source-version合同，必须保留。
- `CONFIRMED`：B_ACTIVE四文件focused baseline为`83 passed`。
- `OPEN / NONCLAIM`：S Provider/Eval closure、X/T/W/V下游owner、zero/all-REJECT、multi-ACCEPT、atomic recovery、Composition Root与真实E2E仍未由U完成。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07J-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07S-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/architecture/tool-calling-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/agent_run_service.py
@src/mini_agent/application/read_tool_executor.py
@tests/component/application/test_agent_run_service.py
@tests/component/application/test_read_tool_executor.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-v1-runtime-contract`

feature_worktree: `e2e01-01-ru-v1-runtime-contract`

writer: `/root Integrator / Application Runtime four-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `7f92b5e0a05714a6a9d7325861499d7cc0bf04dd`

base_tree: `f70b20215e569acf3ad196cc050e9a23700d4bae`

input_barrier: `B_ACTIVE`

output_barrier: `B_SU / ONLY AFTER 01-07S AND 01-07U REVIEWED SERIAL MERGES AND JOINT POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/application/agent_run_service.py` = `63af627943a50fea6a1f733c4a071c259bac6c5f`
- `src/mini_agent/application/read_tool_executor.py` = `23eee37237554749b18e25a5a9ab9b8a6f942c5d`
- `tests/component/application/test_agent_run_service.py` = `1af49601ee8da86de1ef3c2552c9164547bf520e`
- `tests/component/application/test_read_tool_executor.py` = `8fc5d27194fd8a17173c99899ed2f9b8efc7a8d6`

allowlist: the exact four paths above.

expected_actual_change:

- `tests/component/application/test_agent_run_service.py`

expected_byte_identical:

- `src/mini_agent/application/agent_run_service.py`
- `src/mini_agent/application/read_tool_executor.py`
- `tests/component/application/test_read_tool_executor.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FOUR-FILE ALLOWLIST`，尤其包括`src/mini_agent/application/records.py`、`src/mini_agent/application/ports.py`、all `src/mini_agent/core/**`、`src/mini_agent/evaluation/**`、`src/mini_agent/infrastructure/**`、other `tests/**`、`tests/conftest.py`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree从latest integration创建并只拥有本Plan文件；Plan merge只记录签发，不得替换feature `base_sha`。feature必须从上述exact base另建clean Worktree。

## 2. Exact RU-v1 symbol boundary

U的删除目标只包括以下exact legacy symbols在四文件owner中的definition/import/call：

- `ModelProvider`
- `RequestUnderstandingOutput`
- `validate_and_reduce_initial_request`
- `SaveRequestUnderstandingCommand`
- `CreateInitialTaskGraphCommand`
- `create_initial_task_graph_if_current`

带显式`V2`后缀的symbol不匹配legacy target。AST gate必须按exact identifier / attribute比较，不能用会把`*_v2`误报的模糊substring作为唯一证据。

以下字符串属于其他active合同，不是U删除目标：

- `e2e01-thin-v1`：当前`RequestUnderstandingInput` schema，由后续Core/Application contract owner裁决；
- `conversation_record.p0.v1`、`message_record.p0.v1`、link schema：通用Memory/Application records；
- `mock-order-source-version.p0.v1:*`：authoritative order source-version；
- `runtime-tools-v1`、Presentation template/version、redaction version：Tool/Presentation/Trace合同。

U不得修改或重命名这些内容。

## 3. Test-double and source contract

- `_RecordPort`（或当前等价Runtime port test double）删除`create_initial_task_graph_if_current` method；不得以alias、`__getattr__`、dynamic dispatch、optional callback或catch-all mock保留。
- 同一test double继续只实现被active tests实际需要的v2 writer与其他Runtime port方法；现有fault injection、aggregate terminal、atomic failure和safe cleanup tests保持。
- source guard必须对module/class AST验证exact legacy definition/import/call均为零，同时明确v2 identifiers仍存在；不能只依赖`inspect.getsource` substring。
- `AgentRunService`与`ReadToolExecutor`production blobs应与B_ACTIVE一致。若新测试证明production source确有此前漏掉的exact legacy面，立即`BLOCK / OWNER PREFLIGHT DRIFT`并修订Plan；不得在未裁决时顺手改source。
- 删除测试替身方法不表示Application Port的v1 method已删除；`ports.py`明确由01-07W拥有。U只证明active Runtime及其owned tests不再消费/模拟该面。

## 4. Commit, replay and barrier protocol

1. RED commit只在`test_agent_run_service.py`增加AST/API guard，证明legacy test-double method使新合同失败。
2. GREEN commit只在同一文件删除该method；不得amend/rebase掉RED证据。
3. exact-head review前必须证明feature从exact B_ACTIVE线性起始、changed files精确为预期单文件、三个expected-byte-identical blobs不变、83 focused及neighbor/full gates通过。
4. U exact-head PASS后，先在包含reviewed S merge的latest integration上做overlay；S/U file ownership不重叠，不得以Plan/status merge替换feature base。
5. S/U均reviewed串行merge后运行joint post-merge focused、Application/Eval neighbor、database/full gate；只有该共同tree可命名`B_SU`。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结Application Runtime v2-only AST/API surface</name>
  <files>tests/component/application/test_agent_run_service.py</files>
  <action>
    增加AST-based contract test：AgentRunService production class没有六个exact legacy definition/import/call，仍显式引用V2 Provider/reducer/command/writer；owned Runtime test double也不得定义legacy writer。保留现有运行时negative source assertion作为邻接证据。先只提交新test并记录它因test-double method存在而RED。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py -q</automated>
  </verify>
  <done>RED只指向line 390 legacy test-double method，不误报V2或非RU version strings。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — 删除legacy Runtime test-double writer</name>
  <files>tests/component/application/test_agent_run_service.py</files>
  <action>
    删除`create_initial_task_graph_if_current` async method，不增加alias/fallback；运行所有既有Runtime component测试，证明active path只调用v2 writer。确认两个source与ReadToolExecutor test保持base blob。
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py tests/component/application/test_read_tool_executor.py -q</automated>
  </verify>
  <done>83 focused PASS，changed file只有test_agent_run_service.py，production source byte-identical。</done>
</task>

<task type="auto">
  <name>Task 3: exact-head review、latest overlay与共同B_SU gate</name>
  <files>exact four-file allowlist；实际一文件</files>
  <action>
    执行scope/commit containment、AST scan、focused、Application、S-owned Eval neighbor、database/full gates和独立exact-head review。PASS后在latest integration replay；S/U逐个串行merge。两者都在同一共同tree通过post-merge gate后才记录B_SU。
  </action>
  <verify>
    <automated>uv run pytest</automated>
  </verify>
  <done>reviewed U与reviewed S共同形成可复现B_SU；未推进Case lifecycle或下游owner。</done>
</task>

</tasks>

<verification>

最低机械gate：

```bash
git diff --check
uv run pytest tests/component/application/test_agent_run_service.py tests/component/application/test_read_tool_executor.py -q
uv run pytest tests/integration/test_agent_run_service_v2_persistence.py tests/component/evaluation/test_e2e01_scripted_model_provider.py -q
uv run pytest tests/component/application tests/integration/test_agent_run_service_v2_persistence.py -q
uv run pytest
```

exact-head与latest overlay必须额外检查：

- parent chain以exact `B_ACTIVE`起始、无merge commit；
- changed files精确为`tests/component/application/test_agent_run_service.py`；
- 三个expected-byte-identical owned blob与base一致；
- exact legacy AST symbol为零，V2 symbols仍存在；
- order source-version、Memory/link、Tool/Presentation/redaction version strings未变；
- independent reviewer `P0/P1/P2/P3 = 0/0/0/0`；
- S/U共同merge-tree equality与joint post-merge full gate。

</verification>

<contract_changes>

`SCOPED / EXECUTION-MAP AUTHORIZED`：删除Application Runtime owner测试替身中最后一个RU-v1 writer callable，并把01-07J production v2-only状态固化为AST contract。Application Port/Core等v1定义仍等待W/V owner，不在U中修改。

</contract_changes>

<security_impact>

`NONE / BOUNDARY PRESERVING`：不改变可信身份、授权、资源归属、Evidence、Action或source-version边界；production source预期byte-identical。测试继续证明v1 writer不可被active Runtime调用。

</security_impact>

<eval_impact>

`COMPONENT CONTRACT ONLY`：增加/收紧Runtime v2-only Component oracle；不修改Dataset、grader、Case或Result，不推进`CONTRACT_DEFINED / 0/8` lifecycle，不宣称Trajectory/E2E PASS。

</eval_impact>

<rollback>

若exact-head或overlay失败，不合并U；修复只能追加allowlist内线性commit。若U merge后、`B_SU`形成前发现回归，可以普通revert U merge；若`B_SU`或下游X/T/W/V barrier已形成，必须按`V → W → T → X`逆序撤销下游，再按实际S/U merge逆序revert，不得reset/force，不修改原exact base或冻结execution map。

</rollback>

<handoff>

- branch / exact head / tree / parent chain；
- 实际单文件diff与四文件allowlist、三blob equality；
- RED/GREEN/fix commits；
- AST exact-symbol scan与non-target version preservation；
- focused/neighbor/full命令及结果；
- independent exact-head、latest-overlay与joint barrier verdict；
- contract/security/eval impact与OPEN风险；
- 明确`U MERGED != B_SU`，只有S/U共同reviewed tree通过post-merge gate才形成barrier。

</handoff>
