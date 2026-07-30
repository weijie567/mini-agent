---
phase: 01-cycle-1-e2e-01
plan: 07W
type: tdd
wave: 31
depends_on:
  - 01-07T
files_modified:
  - src/mini_agent/application/records.py
  - src/mini_agent/application/ports.py
  - tests/component/application/test_record_contracts.py
  - tests/component/application/test_ports_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Application不再定义或导出v1 ModelProvider、SaveRequestUnderstandingCommand或CreateInitialTaskGraphCommand；ModelProviderV2与三个exact-v2 Request Understanding write command保持唯一current Application contract。"
    - "RuntimeRecordPort不再暴露create_initial_task_graph_if_current、load_request_understanding_for_owner或load_accepted_task_delta_for_owner；两个exact-v2 conditional write methods及其他非RU Port保持原signature与最小披露语义。"
    - "records.py与ports.py不再导入Application所不需要的RequestUnderstandingOutput、RequestUnderstandingRecord或AcceptedTaskDelta v1；Core v1 type definitions只留给后续01-07V，不在W越权修改。"
    - "owned Component contracts以AST/API guard证明legacy definition/import/member/direct、alias、star或reflective lookup为零，同时证明V2后缀symbols、bounded errors、trusted-owner roots与atomic write合同未退化。"
    - "reviewed merge与post-merge gate只形成B_W；当前Eval owner仍有一个allowlist外RequestUnderstandingOutput v1 consumer，必须先通过pre-01-07V owner-remediation gate，不能由W越界删除或把B_W误称为已解锁V。"
  artifacts:
    - "Application records/ports current-v2-only public surface及四文件absence/presence Component evidence。"
    - "ModelProviderV2 exact signatures、两个RU-v2 writer Port、owner-scoped current read inventory与其他Application contracts回归证据。"
  key_links:
    - "B_T → 01-07W → B_W。"
    - "AgentRunService → ModelProviderV2 → SaveRequestUnderstandingV2NoTaskCommand / CreateInitialTaskGraphV2Command → exact-v2 RuntimeRecordPort methods。"
    - "B_W → pre-01-07V Eval-owner remediation gate → 01-07V；Core v1 contract closure只能在该blocker关闭后从新的exact共同barrier另行签发。"
---

# Phase 1 Plan 01-07W｜Application Port / records v1-contract closure

> **ISSUED CONTRACT-CLOSURE TASK PACKET / IMPLEMENTATION NOT STARTED**
> 只有feature从exact `B_T`完成RED/GREEN、独立exact-head review、latest-integration overlay、串行merge与post-merge gate后才可命名`B_W`。Plan merge、RED/GREEN head或review artifact均不是barrier。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、安全、Eval与产品结果语义仍由active canonical owner拥有。本Plan只消费`p0-ru-v2-execution-map-r4`中的W ownership，不建立第二套合同。Graphify按用户指令保持闲置，不读取、不运行、不更新、不作为gate。

<objective>
删除Application records/Ports中已无production consumer的RU-v1 command、Provider、writer/read methods及其v1 type imports，使Application公开执行合同只保留ModelProviderV2、exact-v2 write commands与两个互斥v2 conditional Port methods。

Purpose: 01-07J/S/U/X/T已经依次关闭active Runtime、Provider/Eval、Runtime test double、Infrastructure Adapter和codec的v1可执行面。exact `B_T`上剩余Application compatibility surface只在本Packet四文件ownership内；W可以删除它而不修改Core v1 definitions、physical rows、migration或其他owner。

Output: 四文件TDD feature。RED冻结legacy absence/current-v2 presence；GREEN删除source surface并迁移owned Component contracts。Core v1 types留给01-07V。
</objective>

<preflight_evidence>

- `CONFIRMED`：input barrier为exact `B_T = 06cf4e45b89cfb3d403b1e09e832a0d13e62f8c2`，tree `a0f39e78fa90dfa4a1dc779fda61ea6604cfddfd`。
- `CONFIRMED`：01-07T reviewed feature head `48b76203514e05c2e33a898f22ff8ec5f02a962d`以`PASS P0/P1/P2/P3 = 0/0/0/0`通过，PR #142 merge为上述barrier。
- `CONFIRMED`：T post-merge gate为focused/neighbor `327 passed`，canonical full `1965 passed, 1 deselected, 12 warnings`。
- `CONFIRMED`：W-owned base blobs：
  - `src/mini_agent/application/records.py = 50eac0b74f0a691fc0a476cc9407052c5a28970e`
  - `src/mini_agent/application/ports.py = 3a769a2c51ce30b530beff09961ed91a33be0c62`
  - `tests/component/application/test_record_contracts.py = 30d7334d4e7c6e379f15817c3d0361e47e9b672f`
  - `tests/component/application/test_ports_contract.py = 1d5536c8cc3d3932ce0076f77fd3a21258028306`
- `CONFIRMED`：四文件focused baseline为`373 passed`。
- `CONFIRMED`：`records.py`对`RequestUnderstandingRecord` / `AcceptedTaskDelta`的可执行使用只属于`SaveRequestUnderstandingCommand`与`CreateInitialTaskGraphCommand`；`CandidateValidationDecision`仍被v2 validators使用，不能随v1 command误删。
- `CONFIRMED`：`ports.py`的v1 surface为`ModelProvider → RequestUnderstandingOutput`、legacy graph command/method，以及两个返回v1 Core record的owner-scoped reader；当前production Runtime、Provider/Eval和Infrastructure均无这些方法的direct caller。
- `CONFIRMED`：allowlist外大部分legacy exact names为Core 01-07V definitions/consumers或既有absence-contract字符串；W不得把静态guard字符串误判为可执行caller，也不得修改这些文件。
- `CONFIRMED / DOWNSTREAM BLOCKER`：`tests/component/evaluation/test_e2e01_artifact_consistency.py`（exact `B_T` blob `25cbbc7d1134c4c7c12611f3b0b179e15427e98c`）仍在line 19导入并于line 550实例化Core v1 `RequestUnderstandingOutput`。该文件曾属01-07S Eval ownership，当前实现与01-07S的v2-only acceptance不一致；它不阻断W四文件closure，但阻断01-07V在自身Core allowlist内删除v1 type。
- `CONFIRMED`：current Application v2 surface为`ModelProviderV2`、`SaveRequestUnderstandingV2AcceptedCommand`、`SaveRequestUnderstandingV2NoTaskCommand`、`CreateInitialTaskGraphV2Command`、`save_request_understanding_v2_no_task_if_current`与`create_initial_task_graph_v2_if_current`。
- `OPEN / NONCLAIM`：W不删除Core `RequestUnderstandingOutput`、`RequestUnderstandingRecord`、`AcceptedTaskDelta`或v1 reducer；这些只可由01-07V在Eval owner remediation形成新的exact共同barrier后处理，不能直接以raw `B_W`为feature base。
- `OPEN / BLOCKED-BY-OWNER-REMEDIATION`：`B_W`形成后，Integrator必须先为上述Eval consumer完成owner裁决、独立Task Packet、reviewed merge与post-merge gate，再签发01-07V；不得让W或V越权修改该Eval test，也不得把01-07S Plan目标当作当前已实现事实。
- `OPEN / NONCLAIM`：W不扫描、迁移、回填或删除historical physical RU-v1 rows，不改migration，不激活01-07R。
- `OPEN / NONCLAIM`：W不完成zero/all-REJECT或multi-ACCEPT产品结果、atomic failure恢复、真实HTTP Trajectory/E2E、Case PASS或产品readiness。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07J-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07S-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07U-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07X-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07T-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@tests/component/application/test_record_contracts.py
@tests/component/application/test_ports_contract.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-ru-v1-application-contract`

feature_worktree: `e2e01-01-ru-v1-application-contract`

writer: `/root Integrator / Application Port and records four-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `06cf4e45b89cfb3d403b1e09e832a0d13e62f8c2`

base_tree: `a0f39e78fa90dfa4a1dc779fda61ea6604cfddfd`

input_barrier: `B_T`

output_barrier: `B_W / ONLY AFTER REVIEWED FEATURE MERGE AND POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/application/records.py = 50eac0b74f0a691fc0a476cc9407052c5a28970e`
- `src/mini_agent/application/ports.py = 3a769a2c51ce30b530beff09961ed91a33be0c62`
- `tests/component/application/test_record_contracts.py = 30d7334d4e7c6e379f15817c3d0361e47e9b672f`
- `tests/component/application/test_ports_contract.py = 1d5536c8cc3d3932ce0076f77fd3a21258028306`

allowlist: exact four paths above.

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FOUR-FILE ALLOWLIST`，尤其包括other `src/mini_agent/application/**`、all `src/mini_agent/core/**`、`src/mini_agent/evaluation/**`、`src/mini_agent/infrastructure/**`、other `tests/**`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree只拥有本Plan文件。feature必须从上述exact `B_T`另建clean Worktree；不得使用T feature head、本Plan merge、status/doc merge或任何其他SHA作为feature base。

## 2. Exact Application RU-v1 deletion boundary

`records.py`删除：

- v1 Core imports `RequestUnderstandingRecord`与`AcceptedTaskDelta`；
- `SaveRequestUnderstandingCommand`；
- `CreateInitialTaskGraphCommand`及其legacy exact-one graph validator。

`ports.py`删除：

- `ModelProvider`及v1 `RequestUnderstandingOutput` import；
- `CreateInitialTaskGraphCommand` import；
- v1 Core imports `RequestUnderstandingRecord`与`AcceptedTaskDelta`；
- `RuntimeRecordPort.create_initial_task_graph_if_current`；
- `RuntimeRecordPort.load_request_understanding_for_owner`；
- `RuntimeRecordPort.load_accepted_task_delta_for_owner`。

owned tests删除对应imports、v1 fixture builders、v1 command/graph tests、field/cardinality cases与legacy Port signature/read-shape cases；其中`test_record_contracts.py`的v1-only `CandidateValidationRecord` import/fixtures也必须删除，`CandidateValidationRecordV2`与`CandidateValidationDecision`保留。

W必须保留：

- `RequestUnderstandingInput`，它仍是`ModelProviderV2.propose_next_move`输入；
- `ModelProviderV2` exact signatures、failure taxonomy与Presentation method；
- `RequestUnderstandingRecordV2`、`AcceptedTaskDeltaV2`和三个v2 Application command；
- 两个互斥exact-v2 conditional write Port methods及其APPLIED/zero-write/minimal-disclosure docs；
- `RuntimeRecordPort`全部非RU write/read能力；
- v2 validators所需`CandidateValidationDecision`及`AcceptedTaskDelta`作为逻辑family名称的安全错误字符串；
- conversation/message/link及其他非RU `p0.v1` schema strings，它们不是RU-v1 contract。

不得增加unversioned alias、latest selector、union/optional command、v2→v1 projection、fallback、dynamic capability probing、`__getattr__`或第二个public Provider/Port。

## 3. Component contract migration and absence oracle

RED必须在两个owned test文件增加结构化absence/presence证据，并在base source上仅因上述legacy surface存在而失败。最终guard至少覆盖：

- exact `ImportFrom` name与alias、star import；
- exact class / async method definition；
- exact `Name` / `Attribute` direct reference；
- `getattr` / `hasattr` / `setattr`、module/global subscript、`__import__` / `import_module`及`inspect.getmodule`等reflective access；
- compile-time folded DTO/member name字符串；不得用拆词、format、join或下标绕过；
- runtime module/class export absence；
- 两个owned test自身不再import/instantiate `RequestUnderstandingOutput`、`RequestUnderstandingRecord`、`AcceptedTaskDelta`或`CandidateValidationRecord` v1，也不再通过legacy fixtures间接构造这些types。

guard必须结构化扫描全部四个owned files：两份production source检查import/definition/reference/reflection/export，两份owned tests检查import/fixture/construct/signature/member access。guard中唯一集中声明的exact target literal set，以及v2安全错误中的family-label字符串，不算executable dependency；除此之外不得豁免目标名称。带显式`V2`后缀的symbols不得被模糊substring误报。

`test_record_contracts.py`移除`_request_understanding`、`_accepted_delta`、`_initial_graph`及仅服务legacy command的tests。current v2 command的owner/message/run roots、zero/all-REJECT与exact-one accepted closure、strict/frozen/extra、nested exact-type、timestamp、InputBinding/Task/RequestUnit/link/cardinality证据必须保留。

`test_ports_contract.py`把Provider安全合同迁移到`ModelProviderV2`，owner-scoped read inventory移除两个legacy readers，并冻结RuntimeRecordPort不存在三个legacy members。其他trusted-owner read shape、bounded errors、tool/recovery/evidence Port contracts保持。

## 4. Commit, review and barrier protocol

1. RED commit只修改两个owned test，增加legacy absence/current-v2 presence guard；在exact `B_T` source应产生可解释失败。
2. GREEN commit在四文件内删除source surface并迁移owned tests；不得amend/rebase掉RED。
3. findings只用append-only allowlist fix commits关闭。
4. exact review验证first parent exact `B_T`、linear/no merge、四文件scope、Application legacy executable依赖为零、Core/Infra/codec blobs不变。
5. PASS后在包含本Plan merge的latest integration做throwaway overlay，证明owned blobs与reviewed patch一致。
6. reviewed feature串行merge后复跑focused、Application/Runtime/Infrastructure neighbors与canonical full；共同tree才形成`B_W`。随后进入pre-01-07V Eval-owner remediation gate，不能直接签发V。

</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: RED — 冻结Application current-v2-only records / Port surface</name>
  <files>tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <action>增加exact AST/API/runtime absence guard，禁止legacy Provider、commands、writer/read methods及v1 imports，同时确认ModelProviderV2、三个v2 commands、两个v2 conditional Port methods与其他非RU contract仍存在。先只提交tests并记录可解释RED。</action>
  <verify><automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q</automated></verify>
  <done>RED只命中W-owned legacy surface，不误报V2后缀、Core定义或非RU v1 schema strings。</done>
</task>

<task type="auto">
  <name>Task 2: GREEN — 删除Application RU-v1 contract并迁移Component tests</name>
  <files>src/mini_agent/application/records.py, src/mini_agent/application/ports.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <action>删除Section 2的legacy classes/imports/methods；移除owned v1 fixtures/tests，Provider安全合同迁移到ModelProviderV2，owner-read inventory收敛为current/non-RU能力。保留全部v2 command/Port validators、trusted roots、strict/frozen/error与atomic/minimal-disclosure证据。</action>
  <verify><automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q</automated></verify>
  <done>四文件无legacy executable依赖；current v2与其他Application contracts通过，实际变更不出allowlist。</done>
</task>

<task type="auto">
  <name>Task 3: exact review、latest overlay与B_W gate</name>
  <files>exact four-file allowlist</files>
  <action>运行containment、AST/API guard、focused、Application/Runtime/Infrastructure neighbors、integration/full及independent review；PASS后overlay、串行merge与post-merge canonical gates。不得同步status或提前启动V。</action>
  <verify><automated>uv run pytest</automated></verify>
  <done>共同post-merge tree形成可复现B_W，并把allowlist外Eval blocker交接给pre-01-07V owner-remediation gate。</done>
</task>

</tasks>

<verification>

```bash
git diff --check
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q
uv run pytest tests/component/application -q
uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py -q
uv run pytest tests/integration/test_agent_run_service_v2_persistence.py tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_v2_request_understanding_writes.py -q
uv run pytest tests/integration -q
uv run pytest
```

额外检查：

- first feature commit parent exact `06cf4e45b89cfb3d403b1e09e832a0d13e62f8c2`，linear/no merge；
- changed files exact四文件；
- six exact legacy public targets（`ModelProvider`、两个commands与三个RuntimeRecordPort members）及其v1 return/import dependencies为零；
- owned tests的`RequestUnderstandingOutput`、`RequestUnderstandingRecord`、`AcceptedTaskDelta`与`CandidateValidationRecord` v1 executable dependency为零；
- three v2 commands、ModelProviderV2及两个v2 conditional Port methods保持exact；
- allowlist外Core/Infra/codec/migration blobs不变；
- independent review `0/0/0/0`；
- overlay owned blobs与patch一致；
- post-merge full通过后才记录`B_W`。

</verification>

<contract_changes>

`SCOPED / EXECUTION-MAP AUTHORIZED`：删除已无active consumer的Application RU-v1 Provider、commands、writer/read Port surface与对应v1 imports；Application公开执行合同收敛到current v2。Core v1 definitions、physical18、migration、其他Application contracts与RU-v2 exact semantics不变。

</contract_changes>

<security_impact>

`BOUNDARY PRESERVING / DEFENSE IN DEPTH`：删除v1 Provider与writer/read入口，避免版本fallback或旧DTO重新获得可调用面。current v2 write仍要求trusted owner roots、exact authoritative Message/Run graph、条件原子提交与bounded errors；owner-scoped reads继续隐藏absent与unauthorized。W不连接外部系统、不记录raw payload/secret/PII。

</security_impact>

<eval_impact>

`COMPONENT CONTRACT UPDATE ONLY / DOWNSTREAM EVAL GAP RECORDED`：更新Application records/Ports Component evidence；active Eval Provider/mapper已在01-07S收敛到v2，但artifact-consistency test仍有一个v1 DTO subcase，必须由pre-01-07V Eval-owner remediation单独迁移。W不触碰该test、不新增/激活Dataset Case，不改变Trajectory/E2E Result、grader或42 denominator。

</eval_impact>

<rollback>

未merge：关闭draft PR并保留RED/review证据。已merge但V未形成：普通revert W merge并复跑Application、Runtime/Infrastructure neighbors与full，恢复`B_T`定义的隔离compatibility surface；revert产生新SHA/tree，不得冒充原exact barrier，也不得reset/force。

若已有下游`B_RU_V2_CONTRACT`，按`V → W`逆序普通revert并逐步复跑对应gate。W不迁移physical rows，rollback不得声称恢复或删除数据库内容。

</rollback>

<handoff>

```text
Task Packet: 01-07W
Base SHA / tree:
Branch / Worktree:
RED commit and expected failure:
GREEN/fix commits:
Reviewed exact head / tree:
Actual changed files:
Commands and exact results:
Allowlist / containment result:
Legacy absence / current-v2 preservation:
Contract changes:
Security impact:
Eval impact:
Latest integration overlay evidence:
PR / merge commit:
Post-merge B_W SHA / tree:
Pre-01-07V Eval-owner blocker status:
Unresolved risks:
Rollback:
Recommended next step:
```

Agent完成不等于`B_W`、`B_RU_V2_CONTRACT`、01-08或P0产品完成。

</handoff>

<cross_file_impact>

- execution-owner r4原定`B_T → W → V`顺序；exact `B_T` preflight确认W可执行，但V存在allowlist外Eval consumer blocker。W后必须先由dedicated execution-owner Packet更新marker-bounded map，再走pre-01-07V Eval-owner remediation gate；不得以本Plan静默覆盖旧map，也不得直接签发V。
- T physical handoff、codec Plan与历史migration正文不改；physical18继续由Infrastructure/migration owner持有。
- Core v1 types与其Component tests留给V；W不越界删除。`test_e2e01_artifact_consistency.py`留给独立Eval owner remediation，W/V均不得修改。
- derived State/Roadmap/Requirements/status仍由dedicated status Packet更新；W不越界修改。
- active canonical owner无需语义改写；本Packet只实施已批准execution-map closure。
- Graphify保持闲置。

</cross_file_impact>
