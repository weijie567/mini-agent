---
phase: 01-cycle-1-e2e-01
plan: 07J
type: tdd
wave: 27
depends_on:
  - 01-07I
  - 01-07K
  - 01-07L
  - 01-07M
  - 01-07Q
  - 01-07Y
  - 01-07Z
  - 01-07AA
files_modified:
  - src/mini_agent/application/agent_run_service.py
  - src/mini_agent/application/read_tool_executor.py
  - tests/component/application/test_agent_run_service.py
  - tests/component/application/test_read_tool_executor.py
  - tests/integration/test_agent_run_service_v2_persistence.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "AgentRunService只接受ModelProviderV2，并在active exact-one路径显式调用01-07Y v2 reducer、01-07Z exact-v2 accepted command/Port和01-07AA PostgreSQL writer；不得再调用v1 reducer、v1 command/Port或通过union、alias、fallback、hasattr与dynamic probing选择版本。"
    - "Runtime在Provider调用前通过ConversationRecordPort的owner-scoped read重载authoritative USER Message；Request、v2 reducer与persistence command只消费该持久化Message，command.message只用于首次可靠写入，不能成为第二个authority。"
    - "actual ScriptedModelProviderV2 exact-one success在Control Gateway前原子持久化RU-v2 parent、accepted child、Task、RequestUnit、InputBinding与links；writer未APPLIED时不得产生GateDecision、ToolCall或Observation。"
    - "RequestUnderstandingCandidateInvalidError只在propose_next_move边界被消费并形成COMPLETED/INPUT_INVALID；fresh ProviderProtocolError仍形成PROVIDER_PROTOCOL_ERROR；Runtime不得catch raw ValidationError、ValueError或Exception来伪造该分类。"
    - "FOUND source_version在ReadToolExecutor创建Observation前通过exact canonical GetOrderResult gate；缺失、空、畸形、coercible或不可用统一转为bounded SYSTEM_FAILURE，无Observation、无Manifest #2、无Presentation、无retry、无fallback。"
    - "合法source_version从GetOrderResult到OrderObservation再到Context Manifest #2 byte-for-byte复制；不得parse、normalize、rehash、重算、截断或用record schema、stored_at、fixture、default/latest替代。"
    - "actual AgentRunService + reviewed ScriptedModelProviderV2 + PostgreSQL Adapter + owner-scoped ExactRunEvidencePort证明exact-one成功只产生RU-v2闭合图；invalid-request-understanding-schema与trusted-field-override形成COMPLETED/INPUT_INVALID且零Task/RequestUnit/GateDecision/ToolCall/raw diagnostic。"
    - "zero/all-REJECT、multi-ACCEPT、atomic failure后的重裁决/恢复仍无scoped Runtime outcome owner；01-07J不得自行映射为INPUT_INVALID、成功或业务失败，也不得把01-07Z no-task writer升级为active product route。"
    - "01-07J reviewed merge只形成B_ACTIVE的exact-one E2E01与已定义fault-route范围；不表示zero/multi outcome、01-07S/U/V/W/X、01-08/01-08A、Trajectory/E2E Result或产品readiness完成。"
  artifacts:
    - "AgentRunService的explicit ModelProviderV2、authoritative Message reload、v2 reducer/accepted writer与candidate-invalid mapping。"
    - "ReadToolExecutor的pre-Observation source-version acceptance gate与exact-copy Observation projection。"
    - "Component tests与actual PostgreSQL exact-run Integration oracle。"
  key_links:
    - "01-07L ModelProviderV2 bounded signals → AgentRunService propose_next_move catch boundary。"
    - "owner-scoped persisted Message → 01-07Y validate_and_reduce_initial_request_v2 → 01-07Z CreateInitialTaskGraphV2Command → 01-07AA PostgreSQL writer。"
    - "01-07K GetOrderResult.source_version → ReadToolExecutor acceptance → OrderObservation.source_version → Context Manifest #2 exact version reference。"
    - "B_J_READY = b8d32d50775a0d3f4a0d3e7e609c717f6c540b33 → 01-07J → reviewed B_ACTIVE。"
---

# Phase 1 Plan 01-07J｜Runtime v2 active switch

> **ISSUED ACTIVE SWITCH TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本Packet只切换Application Runtime consumer并关闭source-version acceptance缺口。Plan、RED test或feature head都不表示`B_ACTIVE`已形成；只有exact-head与latest-integration overlay独立审查、串行merge和post-merge gate全部通过后才可命名barrier。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、Tool、source-version、Provider failure与产品结果语义仍由active canonical owner拥有。本Plan只消费reviewed execution map的J ownership，不建立第二套canonical合同。Graphify按用户指令保持闲置，不读取、不运行、不更新、不作为gate。

<objective>
以TDD RED→GREEN把真实`AgentRunService`从legacy v1 Request Understanding路径切换到reviewed RU-v2 exact-one路径，同时在Application read acceptance边界强制可信`source_version`并精确复制到Observation与Manifest。

Purpose: 关闭`B_J_READY`中最后一个active consumer缺口：现有Runtime仍把`RequestUnderstandingOutputV2`交给v1 reducer、调用v1 initial writer，并在Presentation Manifest中用`order-observation.p0.v1` fallback掩盖source version缺失。J必须让真实Scripted Provider v2、Core v2 reducer、Application v2 command、PostgreSQL v2 writer、strict order reader与exact-run evidence闭合，而不越权定义zero/multi outcome或扩展产品readiness。

Output: 一个五文件feature Packet；第一提交只修改三个owned test文件形成可解释RED，第二提交只修改两个owned source文件形成GREEN，review remediation只追加线性fix commits。不得修改Application records/ports、Core、Provider/Eval、Infrastructure、migration、Composition Root、artifact、canonical docs、shared bootstrap或planning State。
</objective>

<preflight_evidence>

- `CONFIRMED`：exact integration与remote均为`B_J_READY=b8d32d50775a0d3f4a0d3e7e609c717f6c540b33`，tree为`a7266cbc58ce541bc6fa839e1a20ab0829f0e781`，post-merge focused+codec 38、neighbor 136、full 1987 passed / 1 deselected / 12 warnings，工作树clean。
- `CONFIRMED`：当前`AgentRunService`仍import/use `ModelProvider`、`validate_and_reduce_initial_request`、`SaveRequestUnderstandingCommand`、`create_initial_task_graph_if_current`，并在Manifest #2保留`order-observation.p0.v1` fallback。
- `CONFIRMED`：当前`ReadToolExecutor`没有把`GetOrderResult.source_version`复制到`OrderObservation`；J的source-version acceptance因此尚未实现。
- `CONFIRMED`：两个owned Component test在B_J_READY为`41 passed`；新Integration test path为ABSENT。
- `OPEN / DERIVED STATUS DEBT`：`.planning/ROADMAP.md`仍写`BLOCKED_BY_B_Q`，`.planning/PROJECT.md`仍写`BLOCKED_BY_B_DEPENDENCY_M`，落后于active execution owner的`B_J_READY`。本Plan one-file allowlist禁止混写；Integrator须在J feature merge后以独立planning-status Packet对齐到实际`B_ACTIVE`或继续阻断状态。该债不覆盖active owner，也不能作为更换feature base的理由。

</preflight_evidence>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07K-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07L-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07M-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Q-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Y-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07Z-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07AA-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/architecture/tool-calling-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/agent_run_service.py
@src/mini_agent/application/read_tool_executor.py
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/core/request_processing.py
@src/mini_agent/core/order.py
@src/mini_agent/evaluation/scripted_provider.py
@src/mini_agent/infrastructure/persistence/postgres.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。
</execution_context>

<interfaces>

## 1. Exact feature identity and ownership

repository: `/Users/ming/projects/mini-agent`

remote: `https://github.com/weijie567/mini-agent.git`

feature_branch: `codex/e2e01-01-runtime-v2-switch`

feature_worktree: `e2e01-01-runtime-v2-switch`

writer: `/root Integrator / Application Runtime five-file sole writer`

pull_request_base: `integration/e2e01-thin`

base_sha: `b8d32d50775a0d3f4a0d3e7e609c717f6c540b33`

base_tree: `a7266cbc58ce541bc6fa839e1a20ab0829f0e781`

input_barrier: `B_J_READY`

output_barrier: `B_ACTIVE / ONLY AFTER REVIEWED SERIAL MERGE AND POST-MERGE GATES`

owned_files_at_base:

- `src/mini_agent/application/agent_run_service.py` = `189914fd2f01b7c8d7077de593d396080013a8b1`
- `src/mini_agent/application/read_tool_executor.py` = `d739ba1500dab5cbaa575a562dfe907ea224648b`
- `tests/component/application/test_agent_run_service.py` = `7998753ae020c27f6b5c8277cc3d19c6c1abf392`
- `tests/component/application/test_read_tool_executor.py` = `4619258d0767431dedf576c2dca2238d4623b04e`
- `tests/integration/test_agent_run_service_v2_persistence.py` = `ABSENT`

allowlist:

- `src/mini_agent/application/agent_run_service.py`
- `src/mini_agent/application/read_tool_executor.py`
- `tests/component/application/test_agent_run_service.py`
- `tests/component/application/test_read_tool_executor.py`
- `tests/integration/test_agent_run_service_v2_persistence.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FIVE-FILE ALLOWLIST`，尤其包括`src/mini_agent/application/records.py`、`src/mini_agent/application/ports.py`、all `src/mini_agent/core/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`tests/conftest.py`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`README.md`、`graphify-out/**`。

Plan branch/worktree从同一exact `B_J_READY`创建并只拥有本Plan文件；Plan reviewed merge只记录签发，不得替换feature `base_sha`。feature必须从上述base另建clean Worktree。

## 2. Authoritative Message and Provider v2 boundary

`AgentRunService.__init__`的`model_provider`必须显式为`ModelProviderV2`。active source不得再import或引用`ModelProvider`、`RequestUnderstandingOutput`、`validate_and_reduce_initial_request`、`InitialRequestDecision`、`SaveRequestUnderstandingCommand`或legacy `create_initial_task_graph_if_current`。

可靠写入Conversation与USER Message后，Runtime必须通过：

```python
await conversation_record_port.list_messages_for_owner(
    owner_scope=owner_scope,
    conversation_id=conversation.conversation_id,
    limit=8,
)
```

获得authoritative message set，并且在Provider调用前验证：

- exact one current USER Message；
- identity、Conversation、direction、schema与trusted write投影一致；
- absent、foreign、duplicate、stale或额外current Message均以bounded `AgentRunExecutionError` fail closed；
- 不扩大到global/other-conversation read，不把空结果与unauthorized区分；
- 后续Message trace ref、Manifest #1、`RequestUnderstandingInput.message_ref/original_query`、authoritative mapping与v2 persistence command只使用重读结果；
- `command.message`在首次append完成后不再参与Request、reducer、binding、trace或Gateway。

`propose_next_move`只捕获两个exact bounded signal：

- `RequestUnderstandingCandidateInvalidError` → `_finish_without_task(... StopReason.INPUT_INVALID)`；
- `ProviderProtocolError` → `_finish_without_task(... StopReason.PROVIDER_PROTOCOL_ERROR)`。

不得捕获raw `pydantic.ValidationError`、`ValueError`、`Exception`、string/category duck type或signal subclass来重新分类。两个error必须保持parameterless/raw-free，Run/Trace/response不得出现raw payload、Pydantic message、attempted trusted field、customer-B、script ref或exception repr。

## 3. V2 reduction, exact-one routing and persistence

Provider成功后，Runtime根据actual emitted candidate identities创建一组`InitialTaskIdentityAllocationV2`；每个candidate分配fresh accepted-delta/Task/RequestUnit/InputBinding identity，另分配fresh RU parent与next-move identity。不得在Provider输出前猜候选数量或从candidate内容派生trusted identity。

Runtime调用：

```python
validate_and_reduce_initial_request_v2(
    request_input=request,
    output=output,
    authoritative_messages={
        message.message_id: message.content
        for message in authoritative_messages
    },
    customer_context=command.customer_context,
    request_understanding_record_id=...,
    candidate_identity_allocations=...,
    next_move_candidate_ref=...,
    now=one_trusted_timestamp,
)
```

只有exact `InitialRequestRoutableTaskGraphDecisionV2`进入本Packet active success route。它必须直接投影为：

```text
CreateInitialTaskGraphV2Command
  owner_scope
  exact Conversation / authoritative Message set / active Run
  SaveRequestUnderstandingV2AcceptedCommand
  exact Task / RequestUnit / InputBinding
  ConversationTaskLink / RunTaskLink
```

所有reducer-created records、accepted child与binding byte-for-byte保留；links使用同一trusted reducer timestamp。调用`create_initial_task_graph_v2_if_current`，只有`APPLIED`可继续append decision Trace、`revalidate_next_move_v2`与Gateway。non-APPLIED或exception进入既有bounded failed-Run cleanup，不创建GateDecision/ToolCall/Observation。

active success path的Trace helper改为只接受v2 routable decision，并从`decision.closure.record`与`decision.task_graph`取message、accepted child、Task、RequestUnit、InputBinding；不得把v2投影为v1 DTO或重建accepted child。

`InitialRequestNoTaskDecisionV2`与`InitialRequestUnroutedTaskGraphsDecisionV2`不属于本Packet product outcome。J不得调用no-task writer后映射结果，也不得把它们分类为INPUT_INVALID/成功/业务失败；必须在任何RU-v2 persistence、Task、Gate或ToolCall前以bounded internal unsupported-outcome boundary停止，由未来scoped outcome owner另行裁决。测试只证明无静默fallback、无v1/v2 write和无产品完成claim。

## 4. FOUND source-version acceptance and exact copy

`GetOrderPort`返回值是不授予authority的Adapter候选。`ReadToolExecutor`在任何terminal success projection、Observation identity分配或Observation write前，必须把FOUND结果重建为exact canonical `GetOrderResult`并验证原对象：

- exact class，不接受subclass/mapping/duck type；
- `outcome=FOUND`、safe `order_summary`与strict `source_version`整体canonical；
- source version匹配Core已冻结exact pattern，拒绝`None`、empty、whitespace、bytes/coercion、bad prefix/version/hash/case/length以及undeclared state；
- rebuilt值与原值exact相等；不得用normalization修复。

validation failure不抛raw错误、不保留cause/context或候选值，统一按现有read system failure路径终结一次ToolCall：`SYSTEM_FAILURE / ORDER_SERVICE_UNAVAILABLE`，无retry、无Observation。

合法FOUND只在terminal ToolCall成功后创建：

```python
OrderObservation(
    ...,
    normalized_value=canonical_result.order_summary,
    source_version=canonical_result.source_version,
)
```

`AgentRunService`收到FOUND execution时再次要求Observation存在且`source_version`为exact non-empty token；Manifest #2的`VersionedRecordRef.version`只使用`observation.source_version`。删除`or "order-observation.p0.v1"`以及任何schema/default fallback。Observation保存、`OBSERVATION_RECORDED` Trace、Manifest #2、Presentation调用的顺序保持canonical。

## 5. Required Component and Integration evidence

`test_read_tool_executor.py`至少冻结：

-合法FOUND source version byte-for-byte进入Observation；
-通过`model_construct`/adversarial exact-instance制造missing、empty、malformed、coercible、undeclared-state或otherwise unusable FOUND candidate时，ToolCall bounded SYSTEM_FAILURE、零Observation、一次read、零retry；
-not-found/system-failure仍不携带source version且既有分类不漂移；
-error/trace/runtime spy状态不含raw bad token或payload。

`test_agent_run_service.py`把所有active fixtures迁移为v2 provider/result，不保留v1 provider compatibility lane，并至少冻结：

-owner-scoped authoritative Message reload发生在Provider前；Provider Request/reducer/persistence只使用重读content，caller对象或stale spy projection不能成为第二authority；
-exact-one v2 command完整字段与Task graph、v2 decision Trace、`revalidate_next_move_v2`、Gateway顺序；
-RuntimeSpy只实现v2 writer；若active source触碰legacy writer则立即失败；
-candidate-invalid与protocol error分类、raw-free、零Task/RequestUnit/Gate/ToolCall；
-bad/missing Observation source version无Manifest #2、无Presentation、无fallback；
-existing Gateway、tool、presentation、terminal aggregate、cancellation与failure cleanup回归保持。

新`tests/integration/test_agent_run_service_v2_persistence.py`只使用actual：

-`AgentRunService`；
-reviewed `ScriptedModelProviderV2`与authenticated in-repo script artifact；
-`PostgresRecordAdapter`作为Conversation/Runtime/Toolset records；
-`PostgresGetOrderAdapter`与isolated PostgreSQL namespace；
-`load_exact_run_evidence_for_owner`。

Integration matrix至少包括：

1. `script:e2e01-01:success` exact-one路径：最终安全结果成功；Gateway前RU-v2完整图已持久化；exact-run reader返回一个RU-v2 parent、一个accepted child与exact Task/RequestUnit/InputBinding/links；无RU-v1；Order Observation与Manifest #2的version精确等于K producer token。
2. `script:fault-provider:invalid-request-understanding-schema`与`script:fault-provider:trusted-field-override`：真实Runtime得到`COMPLETED / INPUT_INVALID`；reader/physical evidence证明无RU、Task、RequestUnit、InputBinding、GateDecision或ToolCall；Trace/Run/result不含raw diagnostic、script payload、attempted owner。
3. 一个真实framing/protocol fault script：仍为`COMPLETED / PROVIDER_PROTOCOL_ERROR`，不被candidate-invalid catch吞并，且同样零Task/Gate/ToolCall。

该Integration oracle不得用RuntimeSpy、Provider capture、script expectation、codec output或raw SQL payload代替exact-run reader。允许用metadata/count查询证明“无v1/无额外family”，但不得读取private payload来证明安全分类。

</interfaces>

<packet_contract>

canonical_inputs:

- `docs/architecture/intent-design-reference.md`：RU-v2 candidate/accepted child、provenance、InputBinding与deterministic validation。
- `docs/architecture/memory-design-reference.md`：trusted owner、Message authority、atomic initial graph、Observation/Evidence/Manifest边界。
- `docs/architecture/tool-calling-design-reference.md`：Gateway前持久化、ToolCall fence、failure/Trace与零retry。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`：01-07J source-version acceptance、exact-copy、SYSTEM_FAILURE与nonclaims。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`：`B_J_READY → 01-07J → B_ACTIVE`、五文件ownership与exact-one/fault acceptance。
- reviewed 01-07I/K/L/M/Q/Y/Z/AA source与tests：signal、Provider v2、strict reader/token、active codec、v2 reducer/commands/PostgreSQL writer。

dependencies:

- `B_J_READY`: exact reviewed integration `b8d32d50775a0d3f4a0d3e7e609c717f6c540b33` / tree `a7266cbc58ce541bc6fa839e1a20ab0829f0e781`。
- `01-07I`: `ModelProviderV2`、`RequestUnderstandingCandidateInvalidError`、ExactRunEvidencePort。
- `01-07L`: actual Scripted/Qwen v2 adapters及bounded candidate-invalid/protocol taxonomy。
- `01-07K/01-07M`: trusted source-version producer与Core final GetOrderResult shape。
- `01-07Q`: public active RU codec v2；J仍显式选择v2 Runtime symbols，不依赖default/latest。
- `01-07Y`: sealed exact-one v2 reducer decision与`revalidate_next_move_v2`。
- `01-07Z/01-07AA`: exact-v2 command/Port与PostgreSQL atomic writer。

contract_changes: `NONE to canonical owner, public schema, Port or persistence contract. YES to scoped active Runtime consumer selection: legacy v1 Runtime path is replaced by explicit v2 exact-one routing, and the already-canonical source-version fail-closed rule becomes enforced.`

security_impact: `YES — active private Runtime path. Trusted owner remains server supplied; persisted owner-scoped Message is sole text authority; candidate-invalid/protocol errors stay fresh and raw-free; bad source versions cannot create Observation/Manifest/Presentation; v2 graph persists before Gateway; no fallback or differentiated unauthorized disclosure.`

eval_impact: `YES — adds Component and PostgreSQL Integration evidence using actual ScriptedModelProviderV2 and exact-run reader. It does not mark EvalCase lifecycle active, produce Trajectory/E2E Result, run credentialed Qwen, or claim product readiness.`

rollback: `合并前关闭PR并删除feature Worktree；合并后先阻断后继签发/新流量，再以普通revert PR撤销01-07J merge并撤销B_ACTIVE claim，恢复B_J_READY为最后reviewed barrier。若01-07S/U/V/W/X或01-08/01-08A已形成，严格按依赖逆序普通revert全部后继后再revert J。不得reset、force-push、改写数据库、恢复silent fallback、删除RU-v2历史或把Plan merge当feature base。`

required_checks:

- `preflight identity`: repository/remote/branch/worktree/base SHA/tree与五文件base blob逐项精确；new Integration test在base为ABSENT；worktree clean；任一偏差`BLOCK`。
- `RED provenance`: first commit只改三个owned tests；focused必须non-zero且失败只因为Runtime仍是v1、缺v2 writer invocation/authoritative reload/source-version copy，不能因fixture、migration、import或test construction错误失败。
- `GREEN`: second commit只改两个owned source files；focused全部转绿；不得修改records/ports/Core/Provider/Infra。
- `focused`: `uv run pytest tests/component/application/test_agent_run_service.py tests/component/application/test_read_tool_executor.py tests/integration/test_agent_run_service_v2_persistence.py -q`；zero failure/skip/xfail。
- `Application regression`: `uv run pytest tests/component/application -q`；zero failure。
- `Runtime/Provider/Infrastructure neighbors`:运行01-07Y Core reducer、01-07L Scripted Provider、01-07K get_order、01-07AA writer与exact-run reader相关tests；zero failure。
- `canonical environment`:从仓库根运行`uv sync --all-groups`、canonical db/db-test health与`uv run alembic upgrade head`。
- `canonical full serial`: `uv run pytest`；exit 0，既有credentialed deselection可保留，warning如实报告且不得新增未裁决warning。
- `source tripwires`: active AgentRunService无v1 reducer/command/Port/writer、fallback/default/latest、raw ValidationError/ValueError/Exception catch或dynamic probing；ReadToolExecutor无token生成/normalize/rehash/record-schema fallback。
- `security matrix`: authoritative read、wrong-owner/empty read、candidate-invalid/protocol distinction、bad token、zero partial graph、no raw diagnostic/PII与pre-Gateway persistence逐项通过。
- `allowlist containment`: `git diff --name-only b8d32d50775a0d3f4a0d3e7e609c717f6c540b33...HEAD`精确等于五项；linear RED→GREEN→append-only fix，零merge commit。
- `cross-file impact scan`:从canonical owner扫描Runtime/Provider/Infra/Eval/Composition/README/status消费者；allowlist外需要对齐项只报告并单独签发，不混入feature。
- `independent exact-head review`: local/PR exact head/tree一致，P0/P1/P2/P3或CRITICAL/HIGH/MEDIUM/LOW全零；所有finding只以append-only fix关闭。
- `latest-integration overlay`:在merge前latest integration clean重放feature patch，记录base/head/tree、patch-id与五个blob；重复focused/Application/neighbors/Alembic/full并取得独立PASS。
- `serial merge/post-merge`:PR先draft；exact-head与overlay均PASS后ready并squash merge；merge tree等于reviewed overlay tree；post-merge重复canonical gates且integration clean后才命名`B_ACTIVE`。

done_when:

- active Runtime无legacy v1 Request Understanding consumer；
- persisted owner-scoped Message是Request/reducer/write唯一authority；
- exact-one actual Scripted Provider v2路径在Gateway前写入完整RU-v2图，并由PostgreSQL exact-run reader闭合；
-两个named candidate-invalid scripts真实穿过Runtime形成COMPLETED/INPUT_INVALID且无Task/Gate/Tool/raw diagnostic；
-protocol fault分类不漂移；
-source version fail closed且合法token byte-for-byte进入Observation/Manifest；
-五文件allowlist、RED→GREEN、focused/Application/neighbors/Alembic/full、exact-head/overlay review、serial merge/post-merge全部可复现；
-只在最终门禁后形成scoped `B_ACTIVE`，所有nonclaims保留。

handoff_to: `/root Integrator`

handoff_format:

- `identity`: repository/remote/base/barrier、feature branch/worktree、linear commits、head/tree、PR；
- `scope`: expected/actual changed files、base/final blobs、dirty/untracked/merge containment；
- `verification`: RED reason、focused/Application/neighbors/db/Alembic/full/source/security/Integration exact-run结果；
- `review`: exact-head与latest-overlay reviewer、SHA/tree、findings/resolutions；
- `contract_and_risk`: contract/security/eval impact、raw/PII、cross-file scan、未执行项、zero/multi nonclaim；
- `integration`: ready/merge SHA/tree、post-merge gates、B_ACTIVE claim或阻断、rollback。

</packet_contract>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze v2 Runtime, bounded signal and source-version oracles</name>
  <files>tests/component/application/test_agent_run_service.py, tests/component/application/test_read_tool_executor.py, tests/integration/test_agent_run_service_v2_persistence.py</files>
  <action>把Component Runtime fixtures迁移到exact v2类型，RuntimeSpy只实现v2 accepted writer，ConversationSpy实现owner-scoped authoritative read；新增candidate-invalid/protocol、authoritative Message、pre-Gateway v2 graph与source-version fail-closed/exact-copy assertions。新增actual ScriptedModelProviderV2 + PostgreSQL + exact-run reader Integration matrix。保留并迁移既有Gateway/tool/presentation/terminal/cancellation/failure tests，不删除安全断言来制造GREEN。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py tests/component/application/test_read_tool_executor.py tests/integration/test_agent_run_service_v2_persistence.py -q</automated>
    必须non-zero；失败只指向active source仍使用v1、未owner-read、未复制/验证source version或未调用v2 PostgreSQL writer。
  </verify>
  <done>三个test文件形成可解释RED，零production改动、零第三test文件。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — switch AgentRunService to exact v2 and enforce source version</name>
  <files>src/mini_agent/application/agent_run_service.py, src/mini_agent/application/read_tool_executor.py</files>
  <action>按Sections 2–4实现explicit ModelProviderV2、authoritative Message reload、v2 allocation/reducer/accepted command/writer/revalidation/Trace投影，以及ReadToolExecutor canonical FOUND gate、Observation exact-copy和Service Manifest fallback removal。保持existing terminal aggregate、Gateway、ToolCall fence、timeout/cancellation与Presentation顺序；不改public records/ports/Core/Infra/Provider。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py tests/component/application/test_read_tool_executor.py tests/integration/test_agent_run_service_v2_persistence.py -q</automated>
  </verify>
  <done>focused全部绿色，actual exact-one路径只写RU-v2，negative routes bounded/raw-free。</done>
</task>

<task type="auto">
  <name>Task 3: Containment, regression and integration gates</name>
  <files>src/mini_agent/application/agent_run_service.py, src/mini_agent/application/read_tool_executor.py, tests/component/application/test_agent_run_service.py, tests/component/application/test_read_tool_executor.py, tests/integration/test_agent_run_service_v2_persistence.py</files>
  <action>只允许append-only remediation。运行Application、Core reducer、Scripted Provider、PostgreSQL get_order/writer/reader neighbors、Alembic与full serial gate；检查v1/fallback/raw-catch/dynamic-probing forbidden symbols、five-file allowlist、linear history与cross-file impact。不得为通过full而修改第三个owner文件。</action>
  <verify>
    <automated>uv run pytest tests/component/application -q</automated>
    <automated>uv run pytest tests/component/core/test_request_processing.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/integration/test_postgres_get_order.py tests/integration/test_postgres_v2_request_understanding_writes.py -q</automated>
    <automated>uv run alembic upgrade head</automated>
    <automated>uv run pytest</automated>
    <automated>git diff --check &amp;&amp; test "$(git diff --name-only b8d32d50775a0d3f4a0d3e7e609c717f6c540b33...HEAD | sort)" = "$(printf '%s\n' src/mini_agent/application/agent_run_service.py src/mini_agent/application/read_tool_executor.py tests/component/application/test_agent_run_service.py tests/component/application/test_read_tool_executor.py tests/integration/test_agent_run_service_v2_persistence.py | sort)"</automated>
  </verify>
  <done>所有适用门禁通过、未执行项准确记录，feature可进入exact-head独立review。</done>
</task>

</tasks>

<verification>

1. Plan reviewed merge只作为issuance evidence；feature仍从exact `B_J_READY=b8d32d50775a0d3f4a0d3e7e609c717f6c540b33`创建。
2. RED只改三个tests并以预期原因失败；GREEN只改两个source并转绿；finding只用append-only fix。
3. source review证明active Runtime没有v1 consumer/fallback/raw catch/dynamic probing，Message authority、source-version exact-copy与pre-Gateway write顺序成立。
4. actual PostgreSQL Integration证明success RU-v2 closure、candidate-invalid INPUT_INVALID与protocol distinction；不以spy/capture/codec替代reader。
5. exact feature head与latest-integration overlay分别取得独立全零review；draft PR head锁定后才ready。
6. squash merge tree精确等于reviewed latest overlay tree；post-merge canonical gates通过后才命名scoped `B_ACTIVE`。

</verification>

<success_criteria>

- AgentRunService active path显式、唯一使用RU-v2 exact-one route。
- owner-scoped durable Message是唯一文本authority。
- candidate-invalid与protocol errors真实穿过Runtime且bounded/raw-free。
- bad source version在Observation前fail closed；合法token exact-copy到Observation/Manifest且无fallback。
- actual Scripted Provider v2 + PostgreSQL + exact-run reader纵向Integration证据通过。
-五文件、线性TDD、全套门禁、双重独立review与merge-tree equality全部满足。
-`B_ACTIVE`只覆盖已审查exact-one与fault routes，不扩张Case/E2E/readiness结论。

</success_criteria>
