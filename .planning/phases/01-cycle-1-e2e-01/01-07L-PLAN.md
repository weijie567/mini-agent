---
phase: 01-cycle-1-e2e-01
plan: 07L
type: tdd
wave: 22
depends_on:
  - 01-07I
  - 01-07P
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
    - "01-07L 只执行 DEPENDENCY_EXPAND 的 Eval Provider/mapper：additive 增加 ModelProviderV2 consumers和expectation-free HTTP + ExactRunEvidenceClosure → Eval evidence mapper；现有v1 Provider/Harness surface在01-07S前保持可复现。"
    - "正确framing的Request Understanding target arguments若被RequestUnderstandingOutputV2 Pydantic拒绝，只映射为fresh RequestUnderstandingCandidateInvalidError；transport/HTTP/JSON/framing、零/多/错function call与全部Presentation validation继续只映射fresh ProviderProtocolError。"
    - "两种bounded signal都必须在raw envelope/diagnostic已丢弃后创建，public constructor零参数、每次fresh、固定safe args，且__cause__与__context__均为None。"
    - "HTTP/closure mapper只接收opaque execution_ref、真实AgentRunResult、HTTP status和01-07I ExactRunEvidenceClosure；不接收case_id、expectations、script/provider capture、customer_id、raw persistence envelope或grader答案，也不从这些来源补造evidence。"
    - "RU-v2 grader evidence只来自closure中的RequestUnderstandingRecordV2与AcceptedTaskDeltaV2；不得从Provider transient output、script、expectations或accepted child逆向重建带raw source_quote的RequestUnderstandingOutputV2。"
    - "v1与v2 evidence branch显式互斥；L只additive扩展，active offline Harness仍使用既有v1 ScriptedModelProvider，直到后续01-07J active switch和01-07S v1-contract closure。"
    - "01-07L 不修改Runtime catch、Application Port/Core/codec、PostgreSQL、Composition Root、tracked Eval artifacts、Case lifecycle、credentialed Qwen runner或readiness；L单独完成不形成B_DEPENDENCY。"
  artifacts:
    - "ScriptedModelProviderV2与QwenResponsesAdapterV2，以及精确failure taxonomy Component证据。"
    - "map_exact_run_http_result_to_sut_result additive mapper与RU-v2-aware EvalEvidence/graders。"
    - "offline Harness tests中的no-oracle mapper、INPUT_INVALID terminal projection与v1/v2 non-mixing证据。"
  key_links:
    - "01-07I ModelProviderV2 / candidate-invalid signal → two Eval-owned Provider consumers。"
    - "01-07I ExactRunEvidenceClosure → case-free HTTP/closure mapper → existing authenticated Harness binding。"
    - "Thin Slice §10.3 failure matrix → candidate-invalid / provider-protocol partition和safe HTTP outcome mapping。"
    - "P0-RU-V2-EXECUTION-MAP：B_IP → {01-07K,01-07L} → B_DEPENDENCY；L不吸收K reader或J Runtime ownership。"
---

# Phase 1 Plan 01-07L｜Eval v2 Providers and exact-Run HTTP mapper

> **ISSUED DEPENDENCY_EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只冻结Eval-owned v2 Provider consumers、evidence projection与mapper。Plan、Component/In-process test或L feature完成都不表示Runtime已切换、真实HTTP/PostgreSQL纵向链已运行、Case已通过或credentialed Qwen baseline存在。

> **DERIVED / NON_NORMATIVE**
> Request Understanding、Memory、Thin Slice、Eval lifecycle与execution order仍由active canonical owner拥有。本Plan只冻结一个精确Eval/Provider Task Packet，不反向覆盖owner或把测试投影升级为产品API。

<objective>
以TDD RED→GREEN增加两个additive `ModelProviderV2` consumers，并把真实HTTP返回边界与`ExactRunEvidenceClosure`确定性映射为case-free、grader-facing evidence。

Purpose: 让01-07J可只负责Runtime消费bounded signal，让01-08可只负责Composition Root/real SUT装配；两者都不再发明Provider failure taxonomy或从transient model/script补造持久化Evidence。

Output: 一个五test RED commit、一个两Provider source GREEN commit和一个Harness/Grader source GREEN commit；只修改九个owned files，不创建Summary、不修改共享State或tracked Eval JSON。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07B-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07F-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07I-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/evaluation/agent-evaluation-strategy.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/evaluation/harness.py
@src/mini_agent/evaluation/graders.py
@src/mini_agent/evaluation/scripted_provider.py
@src/mini_agent/infrastructure/model/qwen_responses.py
@tests/component/evaluation/test_e2e01_artifact_consistency.py
@tests/component/evaluation/test_e2e01_graders.py
@tests/component/evaluation/test_e2e01_scripted_model_provider.py
@tests/component/model/test_qwen_responses_adapter.py
@tests/integration/evaluation/test_e2e01_offline_harness.py

只使用项目受控execution adapter；不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令保持闲置：不读取、不运行、不更新，也不作为gate。
</execution_context>

<interfaces>

## 1. Additive Provider names and active-routing boundary

这是 `INFERRED / EVAL OWNER RULING`：execution map冻结了L/S共享的九文件owner与I提供的`ModelProviderV2`，但没有预先命名Python implementation class。L追加：

```python
class ScriptedModelProviderV2(ScriptedModelProvider): ...

class QwenResponsesAdapterV2(QwenResponsesAdapter): ...
```

两者实现既有`ModelProviderV2`：

```python
async def propose_next_move(
    self,
    request: RequestUnderstandingInput,
) -> RequestUnderstandingOutputV2: ...

async def plan_presentation(
    self,
    request: PresentationInput,
) -> PresentationPlan: ...
```

- v2 classes可以复用各自v1 constructor、strict script cursor、runtime-fault directive、presentation path和injected client/config，但不能修改v1 class的source/AST或返回类型。
- 两个v2 class都必须exact单继承对应v1 class；class body除可选docstring外只能定义一个`async propose_next_move(self, request: RequestUnderstandingInput) -> RequestUnderstandingOutputV2`。该method不得有decorator、positional-only/variadic/keyword-only参数、default或union；`plan_presentation`必须直接继承v1实现，不得override。
- 现有`ScriptedModelProvider` / `QwenResponsesAdapter`继续实现v1 `ModelProvider`并返回`RequestUnderstandingOutput`；现有Offline Harness、qwen preflight和全部v1 tests继续原样可运行。
- L不建立name alias、version parameter、union return、default/latest或自动fallback。后续01-07J/Composition Root必须显式选择v2 class；01-07S才拥有删除v1 surface的权限。
- Scripted v2仍只保存closed execution projection和opaque UUID4 `script_execution_ref`；不得保留`model_script_ref`、case refs、expected result、fixture answer或任意oracle。

## 2. Request Understanding v2 scripted projection

`ScriptedModelProviderV2.propose_next_move`只消费当前cursor的一个Request Understanding step，并构造exact：

```text
RequestUnderstandingOutputV2
  schema_version = e2e01-thin-v2
  message_ref = request.message_ref
  contextualization
    source_message_refs = (request.message_ref,)
    resolved candidate / uncertainty = closed step projection
  task_delta_candidates = emitted-order canonical candidates
  next_move_candidate = canonical NextMove
```

行为矩阵：

- `VALID_ORDER_LOOKUP`、argument substitution与unknown tool返回canonical v2 output；candidate ID继续只由opaque `script_execution_ref + message_ref`确定，不能含script/case identity。
- `INJECT_INVALID_REQUEST_UNDERSTANDING_SCHEMA`、`INJECT_SOURCE_AUTHORITY_MISMATCH`与`INJECT_TRUSTED_FIELD_OVERRIDE`先形成不可信arguments，再在exact `RequestUnderstandingOutputV2.model_validate(..., strict=True)`边界失败；raw mapping/ValidationError立即丢弃并抛fresh candidate-invalid signal。
- zero/multiple target function行为不进入Pydantic candidate boundary，只抛fresh `ProviderProtocolError`。
- Presentation的zero/multiple/invalid/fact-bearing envelope全部保持fresh `ProviderProtocolError`；v2 class不得把Presentation Pydantic rejection误分为candidate-invalid。
- 不用`model_construct`、`model_copy(update=...)`、shadow DTO、unchecked dict return、keyword routing、credential lookup或network。

## 3. Qwen Responses v2 framing/validation split

`QwenResponsesAdapterV2`沿用injected `base_url`、API key、`httpx.AsyncClient`和固定model：

```text
qwen3.7-plus-2026-05-26
```

Request body仍只含现有closed allowlist：`model,input,tools,tool_choice,store=false,stream=false`，且只有当前purpose的一个target function。不得增加SDK、dependency、previous response/conversation、session cache、web/file/code/MCP tool或环境读取。

failure boundary按顺序固定：

1. transport、HTTP、response JSON、outer envelope、`output` shape失败 → protocol；
2. zero/multiple target function、wrong name、non-string arguments、arguments JSON非object → protocol；
3. 恰好一个正确`submit_next_move`且arguments object已形成后，`RequestUnderstandingOutputV2` strict Pydantic拒绝 → candidate-invalid；
4. 恰好一个正确Presentation target后的`PresentationPlan`拒绝仍 → protocol。

每次失败先使raw response、arguments、ValidationError和transport exception不可达，再创建fresh parameterless signal并显式清空cause/context。Component tests必须注入`MockTransport`，禁止真实网络、process credential或raw request/response logging。

## 4. Additive RU-v2 Eval evidence surface

这是 `INFERRED / EVAL OWNER RULING`：现有`EvalEvidence.request_understanding_output`携带model-facing v1 raw quote，不能由quote-free durable v2 closure合法重建。L在`EvalEvidence`末尾additive追加：

```python
request_understanding_records_v2: tuple[RequestUnderstandingRecordV2, ...] = ()
accepted_task_deltas_v2: tuple[AcceptedTaskDeltaV2, ...] = ()
task_state_transitions: tuple[TaskStateTransition, ...] = ()
```

并将同名字段显式加入Harness的case-free `UnboundEvalEvidence` allowlist。迁移合同：

- legacy v1 fields `request_understanding_output`、`request_understanding_records`与`accepted_task_deltas`在L保持名称、类型、default与active test behavior；
- v1 evidence branch要求三个v2 fields全部为空；
- v2 evidence branch要求`request_understanding_output is None`、两个v1 record/child tuples为空，只使用v2 record/child和transition fields；
- mixed branch、v2 accepted child不闭合、v2 record多于一条、无record却有child、v1 output与v2 durable record并存都在EvalEvidence construction或grader input gate fail closed；
- v2 mapper不能重建`RequestUnderstandingOutputV2`，不能恢复raw `source_quote`，不能把`next_move_candidate_ref`反向合成为NextMove。Provider transient output也不得进入EvalEvidence。

所有13个existing grader names/order保持不变。RU/InputBinding/Tool/Persistence/Trace相关grader增加显式v2 branch：

- 从durable v2 record的candidate/decision/accepted refs、InputBinding、Task/RequestUnit、Gate/ToolCall和Trace验证语义；
- source provenance按persisted span/hash与closure Message校验，不依赖raw quote或expectation生成source；
- stale-state使用`task_state_transitions`完整历史，不把restart cap套到Eval；
- v2 observation physical envelope保持空；`_observation_persistence_graph_reason`增加显式v2 branch，要求envelopes exact empty并验证logical Observation/ToolCall/Manifest exact chain与byte-for-byte `source_version`，供`ObservationGrader`与`PersistenceGrader`共同消费。物理row/envelope/reference真实性已由01-07K Port在返回closure前证明，L不得伪造`P0PersistenceEnvelope`；v1 branch仍执行现有physical envelope encode/decode/exact-reference验证；
- v1 branch现有directed-tamper行为保持，后续01-07S才删除。

## 5. Case-free HTTP/closure mapper

`src/mini_agent/evaluation/harness.py`追加：

```python
def map_exact_run_http_result_to_sut_result(
    *,
    execution_ref: UUID,
    http_status: int,
    agent_result: AgentRunResult,
    closure: ExactRunEvidenceClosure,
) -> EvalCaseSutResult: ...
```

四个参数都必须是exact canonical values并被detached strict-revalidated；mapper不接受`case_id`、lane、attempt、Case/Script artifact、expectations、customer/Session context、Provider object/output/capture、raw HTTP body、raw persistence envelope或grader result。

闭合规则：

1. `execution_ref`是opaque UUID4 correlation，只复制到result；它不授权、不等于run_id且不进入evidence。
2. normal Agent response只接受HTTP `200`；`agent_result.run_id == closure.run_record.run_id`，Run必须`COMPLETED`且stop reason/outcome满足现有closed terminal matrix。
3. `trace_ref := run_id`只作为P0 Eval opaque correlation；所有Trace必须属于该Run、`case_id is None`，不能伪造单一Trace row。
4. `observed_outcome`与Agent result一致；`run_record`、Conversation、Message、RU-v2 record/child、InputBinding、Task/transition、RequestUnit、links、Gate、ToolCall/attempt、Observation、Manifest、Toolset artifact与Trace都从closure exact-copy，不排序重写、不补default。
5. `response_policy`只由closed stop reason映射：`GOAL_COMPLETED → DETERMINISTIC_ORDER_SUMMARY_V1`，`NOT_FOUND_OR_NOT_ACCESSIBLE → FIXED_NOT_FOUND_OR_NOT_ACCESSIBLE`，`ORDER_SERVICE_UNAVAILABLE → FIXED_ORDER_SERVICE_UNAVAILABLE`，其余允许的blocked reasons → `FIXED_SAFE_PROCESSING_ERROR`。L在existing `_FIXED_MESSAGES`中additive加入`FIXED_ORDER_SERVICE_UNAVAILABLE → 订单服务暂时不可用，请稍后重试。`；固定文案必须与Agent result exact，success文案由existing RendererFactGrader对Observation校验。
6. `ordinary_trace_shape`只由safe trace allowlist计算；`model_calls == len(context_manifests)`；不从script/expectation猜测。
7. closure无raw persistence envelope，因此v2 `observation_persistence_envelopes=()`；不得重新encode logical record伪装physical evidence。
8. 任何identity/outcome/HTTP/policy/trace/closure矛盾抛fresh bounded `EvalHarnessCommandError`，先丢弃raw exception/cause/context，不返回partial result。

mapper只产生case-free `EvalCaseSutResult`；现有Harness仍独占authenticated Case binding、expectation construction、grading、EvalCaseGraded Trace和Result/Failure persistence。

`FIXED_ORDER_SERVICE_UNAVAILABLE`是 `INFERRED / EVAL OWNER RULING`，用于对齐Thin Slice §7.4/§10.3已经冻结的产品文案；它是additive v2 mapper policy，不改写现有v1 artifacts中的legacy generic policy，也不使L获得Dataset ownership。后续01-07S在移除v1 Provider/Harness contract时，必须把`ORDER_SERVICE_UNAVAILABLE + legacy FIXED_SAFE_PROCESSING_ERROR`的authenticated v1 expectation确定性迁移到该policy，或先签发独立artifact-owner裁决；该对齐在`B_SU`前完成，01-08不得临时发明另一套policy。

## 6. Runtime ownership and staged proof

L精确完成Provider-owned translation与mapper-owned terminal projection，但不得修改`AgentRunService`。因此证据分层：

- L Component tests必须对`invalid-request-understanding-schema`与`trusted-field-override`证明v2 Scripted Provider抛candidate-invalid，而zero/multiple与全部Presentation分支仍抛protocol；
- L mapper/Offline Harness tests必须对一个canonical `COMPLETED / INPUT_INVALID` Run closure + exact Agent result证明HTTP `200 + BLOCKED + FIXED_SAFE_PROCESSING_ERROR`映射，不产生Task/RequestUnit/Gate/ToolCall；
- 后续01-07J是唯一可以证明“上述两个Provider scripts实际穿过product Runtime后得到INPUT_INVALID”的owner，它必须只catch candidate-invalid signal，并保留protocol分类；L不得用test shim、Harness catch或synthetic evidence冒充该真实Runtime证据。

如果review要求L本身修改Runtime或把Provider signal直接转换为Run result，立即`BLOCK / OWNER-MAP CONFLICT`并请求先修订唯一execution map；不得越过九文件allowlist。K/L共同barrier只证明dependency consumers，真实Runtime mapping仍等待J。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-eval-mapper`
base_branch: `integration/e2e01-thin`
base_sha: `bbe14fadc0cd2e14ad35e19177b079fcab685dfc`
base_tree: `65415ff5846892f257e95d8b8bd34f50752980a2`
input_barrier: `B_IP`
output_barrier: `B_DEPENDENCY / ONLY AFTER 01-07K AND 01-07L BOTH REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-eval-mapper`
writer: `Eval Provider and mapper sole writer with owned Component/Integration tests, supervised by /root Integrator`
agent_role: `eval-engineer`
active_routing: `false`

planning_and_owner_provenance:

- final issuance/owner head `f038cad70b484621c62bcf29f89a601bc46e5123`
- exact execution-map blob `ea2b5bcac4cb10c928a9e578c1286febb243c7d6`
- L/J acceptance ownership clarification [PR #93](https://github.com/weijie567/mini-agent/pull/93) reviewed head/merge `510384c9dad24c0f229dd09cc5cf4a9deedfa292` / `726ac109514cb665386b981ac506c816d3abc310`
- 01-07K Plan [PR #94](https://github.com/weijie567/mini-agent/pull/94) reviewed head/merge/blob `ec61275040ccbda1ddf2090bee44cf265434a89b` / `f038cad70b484621c62bcf29f89a601bc46e5123` / `45a573332136f5954358e6e077f2222b2e932259`
- exact `B_IP` merge/tree `bbe14fadc0cd2e14ad35e19177b079fcab685dfc` / `65415ff5846892f257e95d8b8bd34f50752980a2`
- 01-07I Plan blob `15e114001cb81fdcf457f12a5156c9ed00085cbd`
- 01-07P Plan blob `1dcf69b2e5538137d526bdea6acf595890514892`
- Thin Slice owner blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- Memory owner blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- Intent owner blob `456be9c7d7884e2a58c4d07b867765ed336aa6f5`
- Eval owner blob `6ee5e0cb639ddc9d2fe3f0b715252a3214284440`
- official 01-07L Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；planning merge不替换feature base `B_IP`

owned_files_at_base:

- `src/mini_agent/evaluation/harness.py` = `609d7ea9743a9497f22fa74df5626dd1566226e6`
- `src/mini_agent/evaluation/graders.py` = `9f19fc04c3f93fc7a3223911d39603331e9f771d`
- `src/mini_agent/evaluation/scripted_provider.py` = `4d85a06200826e591ff55fd15faadf8b50b0da6e`
- `src/mini_agent/infrastructure/model/qwen_responses.py` = `2a2fd52d0d8e6e6ca6c5eb83b79732f6ebc6a6bd`
- `tests/component/evaluation/test_e2e01_artifact_consistency.py` = `18e6cc3bb7900059ed432d7e041207cf939e58b4`
- `tests/component/evaluation/test_e2e01_graders.py` = `ecf3a5f785b6d835b53349a5847809ea78530bcd`
- `tests/component/evaluation/test_e2e01_scripted_model_provider.py` = `05979a12db0386fc8221ca7227fc57d2f431d4a4`
- `tests/component/model/test_qwen_responses_adapter.py` = `7025f352c7b6eb71c686b1c29de5a80bd9b1433c`
- `tests/integration/evaluation/test_e2e01_offline_harness.py` = `613ae47ce73d928e5462b83448f57d2f52a2946b`

allowlist:

- `src/mini_agent/evaluation/harness.py`
- `src/mini_agent/evaluation/graders.py`
- `src/mini_agent/evaluation/scripted_provider.py`
- `src/mini_agent/infrastructure/model/qwen_responses.py`
- `tests/component/evaluation/test_e2e01_artifact_consistency.py`
- `tests/component/evaluation/test_e2e01_graders.py`
- `tests/component/evaluation/test_e2e01_scripted_model_provider.py`
- `tests/component/model/test_qwen_responses_adapter.py`
- `tests/integration/evaluation/test_e2e01_offline_harness.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE NINE-FILE ALLOWLIST`，尤其包括 `src/mini_agent/application/**`、`src/mini_agent/core/**`、other `src/mini_agent/infrastructure/**`、other `src/mini_agent/evaluation/**`、`tests/component/application/**`、other `tests/**`、`evals/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`graphify-out/**`。

protected_surface:

- `scripted_provider.py`的14个pre-existing top-level definitions和`ScriptedModelProvider`全部9个methods source/AST exact；只允许新增imports/private helper与V2 subclass。
- `qwen_responses.py`的`_fresh_protocol_error`和`QwenResponsesAdapter`全部4个methods source/AST exact；只允许新增imports/private helper与V2 subclass。
- `harness.py`的54个pre-existing top-level definitions source/AST exact；只允许扩展`_UNBOUND_EVIDENCE_FIELD_ALLOWLIST` assignment并新增mapper/private helper。
- `graders.py`只允许修改imports、`_FIXED_MESSAGES` assignment及`EvalEvidence`、`RequestUnderstandingGrader`、`InputBindingGrader`、`_conversation_graph_reason`、`_request_understanding_graph_reason`、`_observation_persistence_graph_reason`、`_tool_graph_is_closed`、`ToolCallGrader`、`_trace_references_match_typed_records`、`PersistenceGrader`十个definition；其他pre-existing top-level definition source/AST exact，13-grader names/order/registry和Critical failure semantics不变。
- 五个tracked Eval JSON、active v1 Provider/Harness behavior、Qwen baseline preflight、Application/Core/Runtime/DB全部byte-identical。

commit_contract:

1. RED `test(01-07L): define v2 eval provider boundary`：只改五份owned test；四份source blob仍等于B_IP。focused command必须因V2 Provider/mapper/evidence surface缺失或旧failure partition失败，不得因artifact hash、syntax或network失败。
2. Provider GREEN `feat(01-07L): add v2 eval providers`：只改`scripted_provider.py`与`qwen_responses.py`；不重写RED。
3. Mapper GREEN `feat(01-07L): map exact run eval evidence`：只改`harness.py`与`graders.py`；不重写RED/Provider commit。
4. 首个review candidate相对B_IP恰为上述三个commit；final history为固定RED/Provider GREEN/Mapper GREEN加零到多笔append-only `fix(01-07L): ...`。Finding修复不得amend/rebase/force-push已审历史，且每笔fix仍只能修改九文件allowlist。

contract_changes: `YES / ADDITIVE EVAL DEPENDENCY` — 增加两个explicit v2 Provider consumers、v2 durable evidence fields、`FIXED_ORDER_SERVICE_UNAVAILABLE`和case-free mapper；v1 active surface保留，无Runtime/active switch或v1 removal。
security_impact: `YES` — exact failure taxonomy、raw diagnostic disposal、no-oracle mapper、v1/v2 non-mixing、closure/HTTP identity/outcome fail-closed和无fake envelope。
eval_impact: `YES / COMPONENT + IN-PROCESS PREREQUISITE` — graders可消费authoritative v2 closure并保留legacy evidence；L不改Dataset、Case activation、threshold、Result artifact、Trajectory/E2E状态或Baseline，legacy unavailable-policy expectation在01-07S / `B_SU`前完成确定性迁移。
new_dependencies: `NONE`
graphify_disposition: `DISABLED_BY_USER / NOT_RUN / NOT_A_GATE`
rollback: 合并前关闭PR；合并后普通revert PR逆序撤销01-07L feature/fix commits，并重新阻塞01-07M及全部active-switch/contract/01-08/01-08A下游。不得reset、force-push、改写tracked artifacts、fallback到transient Provider capture或推进lifecycle。

handoff_format: branch、exact B_IP/Plan provenance/head/commits/tree、九个base/head blobs、RED/two-GREEN输出、Provider taxonomy/mapper/v1-v2 gates、Observation logical/physical branch、unavailable-policy与01-07S迁移handoff、protected-definition oracle、focused/full/hash/zero-network/containment结果、cross-file scan、J ownership handoff、contract/security/Eval nonclaims、exact-head/latest-overlay review、风险与merge SHA。
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `L-S01` | Spoofing | raw Provider/schema failure → canonical stop class | `MITIGATE / BLOCK` | correct-framing boundary后才candidate-invalid；其他RU/Presentation failures保持protocol；J独占Runtime mapping |
| `L-T01` | Tampering | Provider capture/script/expectation → Eval evidence | `MITIGATE / BLOCK` | mapper参数closed、v2 evidence只exact-copyclosure、mixed v1/v2拒绝、不得重建raw output/envelope |
| `L-R01` | Repudiation | HTTP/result/Run/Trace mismatch → graded Case | `MITIGATE / BLOCK` | exact run/outcome/status/trace/policy matrix、opaque execution ref、RED/GREEN/exact review |
| `L-I01` | Information Disclosure | raw response/Pydantic/HTTP/DB → error/Trace/Result | `MITIGATE / BLOCK` | raw discard、fresh parameterless errors、cause/context清空、case-free mapper和safe trace shape |
| `L-D01` | Denial of Service | malformed nested result/provider envelope | `MITIGATE / BLOCK` | strict Pydantic、closed one-call framing、closure已bounded、整体command error无partial |
| `L-E01` | Elevation of Privilege | Eval mapper/trace_ref/provider → auth或active routing | `MITIGATE / BLOCK` | owner scope不在mapper输入、trace_ref不授权、active_routing=false、Composition Root/J另有owner |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze v2 Provider taxonomy and exact-Run mapper</name>
  <files>tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/evaluation/test_e2e01_graders.py, tests/component/evaluation/test_e2e01_scripted_model_provider.py, tests/component/model/test_qwen_responses_adapter.py, tests/integration/evaluation/test_e2e01_offline_harness.py</files>
  <action>只改五份test。冻结两个V2 class及ModelProviderV2 signatures；对Scripted/Qwen正确framed invalid/trusted/source拒绝断言fresh candidate-invalid，对transport/HTTP/JSON/zero/multiple/wrong/presentation断言fresh protocol且raw/cause/context清空；证明v1 class/output/tests未漂移、Scripted零credential/network、Qwen仅MockTransport。为EvalEvidence增加v2 exact/mixed matrix与13 graders正负证据，其中至少包含一条envelope exact empty但logical Observation/ToolCall/Manifest/source_version闭合的v2 success，以及逐项破坏logical ref或source_version的directed tamper；v1 physical-envelope tamper仍保持失败。为mapper建立success/not-found/ORDER_SERVICE_UNAVAILABLE/INPUT_INVALID/gateway/stale/presentation代表closure，断言unavailable严格映射`FIXED_ORDER_SERVICE_UNAVAILABLE`及canonical文案、参数surface无case/script/owner/provider/raw envelope、exact-copy、safe observable、source_version chain、mismatch bounded failure和existing Harness authenticated binding。不要修改JSON、使用skip/xfail或伪装真实Runtime。</action>
  <verify>
    <automated>uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_graders.py tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py tests/integration/evaluation/test_e2e01_offline_harness.py -q</automated>
    RED必须非零且仅因L surface/taxonomy/mapper尚未实现；四source blobs与五tracked artifacts仍等于B_IP。
  </verify>
  <done>RED同时定位Provider分类、durable-v2 evidence和HTTP/closure mapper三个owned缺口。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — add explicit Scripted/Qwen v2 consumers</name>
  <files>src/mini_agent/evaluation/scripted_provider.py, src/mini_agent/infrastructure/model/qwen_responses.py</files>
  <action>只追加V2 classes与所需private helpers/imports，复用现有constructor/cursor/presentation/config而不改v1 definitions。Scripted构造canonical output或在strict v2 Pydantic边界翻译；Qwen按framing→arguments→v2 validation分层。所有raw exception/envelope在创建bounded signal前清除；不得新增dependency、environment read、network path或Runtime catch。focused转绿后只提交两份Provider source，subject exact为`feat(01-07L): add v2 eval providers`。</action>
  <verify>
    <automated>uv run pytest tests/component/evaluation/test_e2e01_scripted_model_provider.py tests/component/model/test_qwen_responses_adapter.py -q</automated>
    v1/v2 positive与全failure matrix、zero-network和protected definitions全部通过。
  </verify>
  <done>两个additive ModelProviderV2 consumers可被后续J/01-08显式注入，v1 behavior不变。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: GREEN — map authoritative closure and grade durable RU-v2 evidence</name>
  <files>src/mini_agent/evaluation/harness.py, src/mini_agent/evaluation/graders.py</files>
  <action>additive扩展EvalEvidence/Unbound allowlist并实现exact mapper；只从HTTP status、AgentRunResult和closure构造case-free result。为现有相关grader增加明确v2 branch，验证durable candidate/child/InputBinding/Task transition/Gate/Tool/Observation/Manifest/Trace graph；`_observation_persistence_graph_reason`的v1 branch保留physical envelope encode/decode/exact-reference校验，v2 branch要求envelope exact empty并校验logical Observation/ToolCall/Manifest/source_version chain。为mapper和`_FIXED_MESSAGES`additive加入`ORDER_SERVICE_UNAVAILABLE → FIXED_ORDER_SERVICE_UNAVAILABLE → 订单服务暂时不可用，请稍后重试。`，其他closed terminal mappings保持不变。不重建RequestUnderstandingOutputV2或P0PersistenceEnvelope，不修改13-name registry/CF/paired disclosure语义，不让Harness直接catchcandidate-invalid代替Runtime。focused转绿后只提交Harness/Graders source，subject exact为`feat(01-07L): map exact run eval evidence`。</action>
  <verify>
    <automated>uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/evaluation/test_e2e01_graders.py tests/integration/evaluation/test_e2e01_offline_harness.py -q</automated>
    no-oracle input surface、v1/v2互斥、logical-v2/physical-v1 Observation directed tamper、unavailable fixed policy、INPUT_INVALID terminal mapping与existing Harness behavior全部通过。
  </verify>
  <done>authoritative closure可无script/expectation/provider capture地形成grader-facing case-free evidence，等待Composition Root装配。</done>
</task>

</tasks>

<verification>

Feature Worktree必须从仓库根目录运行：

```bash
set -euo pipefail

base_sha=bbe14fadc0cd2e14ad35e19177b079fcab685dfc
base_tree=65415ff5846892f257e95d8b8bd34f50752980a2
expected_branch=codex/e2e01-01-eval-mapper
expected_worktree_id=e2e01-01-eval-mapper
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git worktree list --porcelain | awk -v root="$current_root" '
  $1 == "worktree" { current = $2 }
  $1 == "branch" && current == root { print $2 }
')" = "refs/heads/$expected_branch"
test "$(git rev-parse HEAD^0)" = "$base_sha" # first edit前
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "$base_sha^{tree}")" = "$base_tree"
test "$(git rev-parse "$base_sha:src/mini_agent/evaluation/harness.py")" = \
  609d7ea9743a9497f22fa74df5626dd1566226e6
test "$(git rev-parse "$base_sha:src/mini_agent/evaluation/graders.py")" = \
  9f19fc04c3f93fc7a3223911d39603331e9f771d
test "$(git rev-parse "$base_sha:src/mini_agent/evaluation/scripted_provider.py")" = \
  4d85a06200826e591ff55fd15faadf8b50b0da6e
test "$(git rev-parse "$base_sha:src/mini_agent/infrastructure/model/qwen_responses.py")" = \
  2a2fd52d0d8e6e6ca6c5eb83b79732f6ebc6a6bd
test "$(git rev-parse "$base_sha:tests/component/evaluation/test_e2e01_artifact_consistency.py")" = \
  18e6cc3bb7900059ed432d7e041207cf939e58b4
test "$(git rev-parse "$base_sha:tests/component/evaluation/test_e2e01_graders.py")" = \
  ecf3a5f785b6d835b53349a5847809ea78530bcd
test "$(git rev-parse "$base_sha:tests/component/evaluation/test_e2e01_scripted_model_provider.py")" = \
  05979a12db0386fc8221ca7227fc57d2f431d4a4
test "$(git rev-parse "$base_sha:tests/component/model/test_qwen_responses_adapter.py")" = \
  7025f352c7b6eb71c686b1c29de5a80bd9b1433c
test "$(git rev-parse "$base_sha:tests/integration/evaluation/test_e2e01_offline_harness.py")" = \
  613ae47ce73d928e5462b83448f57d2f52a2946b
test -z "$(git status --short --untracked-files=all)"
```

以上 **Gate A / first-edit preflight** 必须在任何RED编辑前完整成功。实现与提交完成后，在feature Worktree另起shell完整运行 **Gate B / post-implementation final**：

```bash
set -euo pipefail

base_sha=bbe14fadc0cd2e14ad35e19177b079fcab685dfc
base_tree=65415ff5846892f257e95d8b8bd34f50752980a2
expected_branch=codex/e2e01-01-eval-mapper
expected_worktree_id=e2e01-01-eval-mapper
expected_remote=https://github.com/weijie567/mini-agent.git
current_root="$(git rev-parse --show-toplevel)"

test "$(git remote get-url origin)" = "$expected_remote"
test "$(git branch --show-current)" = "$expected_branch"
test "$(basename "$current_root")" = "$expected_worktree_id"
test "$(git worktree list --porcelain | awk -v root="$current_root" '
  $1 == "worktree" { current = $2 }
  $1 == "branch" && current == root { print $2 }
')" = "refs/heads/$expected_branch"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "$base_sha^{tree}")" = "$base_tree"
test "$(git rev-parse "$base_sha:src/mini_agent/evaluation/harness.py")" = \
  609d7ea9743a9497f22fa74df5626dd1566226e6
test "$(git rev-parse "$base_sha:src/mini_agent/evaluation/graders.py")" = \
  9f19fc04c3f93fc7a3223911d39603331e9f771d
test "$(git rev-parse "$base_sha:src/mini_agent/evaluation/scripted_provider.py")" = \
  4d85a06200826e591ff55fd15faadf8b50b0da6e
test "$(git rev-parse "$base_sha:src/mini_agent/infrastructure/model/qwen_responses.py")" = \
  2a2fd52d0d8e6e6ca6c5eb83b79732f6ebc6a6bd
test "$(git rev-parse "$base_sha:tests/component/evaluation/test_e2e01_artifact_consistency.py")" = \
  18e6cc3bb7900059ed432d7e041207cf939e58b4
test "$(git rev-parse "$base_sha:tests/component/evaluation/test_e2e01_graders.py")" = \
  ecf3a5f785b6d835b53349a5847809ea78530bcd
test "$(git rev-parse "$base_sha:tests/component/evaluation/test_e2e01_scripted_model_provider.py")" = \
  05979a12db0386fc8221ca7227fc57d2f431d4a4
test "$(git rev-parse "$base_sha:tests/component/model/test_qwen_responses_adapter.py")" = \
  7025f352c7b6eb71c686b1c29de5a80bd9b1433c
test "$(git rev-parse "$base_sha:tests/integration/evaluation/test_e2e01_offline_harness.py")" = \
  613ae47ce73d928e5462b83448f57d2f52a2946b

uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head

uv run pytest \
  tests/component/evaluation/test_e2e01_artifact_consistency.py \
  tests/component/evaluation/test_e2e01_graders.py \
  tests/component/evaluation/test_e2e01_scripted_model_provider.py \
  tests/component/model/test_qwen_responses_adapter.py \
  tests/integration/evaluation/test_e2e01_offline_harness.py \
  -q
uv run pytest

git diff --check "$base_sha...HEAD"
test "$(git rev-list --count "$base_sha..HEAD")" -ge 3
test "$(git rev-list --merges --count "$base_sha..HEAD")" -eq 0
red_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '1p')"
provider_green_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '2p')"
mapper_green_sha="$(git rev-list --reverse "$base_sha..HEAD" | sed -n '3p')"
test "$(git show -s --format=%s "$red_sha")" = \
  "test(01-07L): define v2 eval provider boundary"
test "$(git show -s --format=%s "$provider_green_sha")" = \
  "feat(01-07L): add v2 eval providers"
test "$(git show -s --format=%s "$mapper_green_sha")" = \
  "feat(01-07L): map exact run eval evidence"
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha" | LC_ALL=C sort)" = \
  "$(printf '%s\n' \
    tests/component/evaluation/test_e2e01_artifact_consistency.py \
    tests/component/evaluation/test_e2e01_graders.py \
    tests/component/evaluation/test_e2e01_scripted_model_provider.py \
    tests/component/model/test_qwen_responses_adapter.py \
    tests/integration/evaluation/test_e2e01_offline_harness.py)"
test "$(git diff-tree --no-commit-id --name-only -r "$provider_green_sha" | LC_ALL=C sort)" = \
  "$(printf '%s\n' \
    src/mini_agent/evaluation/scripted_provider.py \
    src/mini_agent/infrastructure/model/qwen_responses.py)"
test "$(git diff-tree --no-commit-id --name-only -r "$mapper_green_sha" | LC_ALL=C sort)" = \
  "$(printf '%s\n' \
    src/mini_agent/evaluation/graders.py \
    src/mini_agent/evaluation/harness.py)"
test -z "$(git log --reverse --format=%s "$base_sha..HEAD" |
  sed '1,3d' |
  rg -v '^fix\(01-07L\): .+$' || true)"
for fix_sha in $(git rev-list --reverse "$base_sha..HEAD" | sed '1,3d'); do
  test -z "$(git diff-tree --no-commit-id --name-only -r "$fix_sha" |
    rg -v '^(src/mini_agent/evaluation/(graders|harness|scripted_provider)\.py|src/mini_agent/infrastructure/model/qwen_responses\.py|tests/component/evaluation/test_e2e01_(artifact_consistency|graders|scripted_model_provider)\.py|tests/component/model/test_qwen_responses_adapter\.py|tests/integration/evaluation/test_e2e01_offline_harness\.py)$' ||
    true)"
done
test "$(git diff --name-only "$base_sha...HEAD" | LC_ALL=C sort)" = "$(printf '%s\n' \
  src/mini_agent/evaluation/graders.py \
  src/mini_agent/evaluation/harness.py \
  src/mini_agent/evaluation/scripted_provider.py \
  src/mini_agent/infrastructure/model/qwen_responses.py \
  tests/component/evaluation/test_e2e01_artifact_consistency.py \
  tests/component/evaluation/test_e2e01_graders.py \
  tests/component/evaluation/test_e2e01_scripted_model_provider.py \
  tests/component/model/test_qwen_responses_adapter.py \
  tests/integration/evaluation/test_e2e01_offline_harness.py)"
test -z "$(git status --short --untracked-files=all)"
```

Protected-definition oracle必须作为同一门禁实际运行：

```bash
set -euo pipefail
base_sha=bbe14fadc0cd2e14ad35e19177b079fcab685dfc
uv run python - "$base_sha" <<'PY'
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

BASE = sys.argv[1]
FORBIDDEN_CALLS = frozenset({"__import__", "eval", "exec", "globals", "setattr"})
CONFIG = {
    "src/mini_agent/evaluation/scripted_provider.py": {
        "expected_defs": 14,
        "mutable_defs": frozenset(),
        "new_public_defs": frozenset({"ScriptedModelProviderV2"}),
        "new_private_prefixes": ("_v2_",),
        "mutable_assignments": frozenset(),
        "new_assignment_prefixes": ("_V2_", "_v2_"),
    },
    "src/mini_agent/infrastructure/model/qwen_responses.py": {
        "expected_defs": 2,
        "mutable_defs": frozenset(),
        "new_public_defs": frozenset({"QwenResponsesAdapterV2"}),
        "new_private_prefixes": ("_v2_",),
        "mutable_assignments": frozenset(),
        "new_assignment_prefixes": ("_V2_", "_v2_"),
    },
    "src/mini_agent/evaluation/harness.py": {
        "expected_defs": 54,
        "mutable_defs": frozenset(),
        "new_public_defs": frozenset({"map_exact_run_http_result_to_sut_result"}),
        "new_private_prefixes": ("_exact_run_eval_",),
        "mutable_assignments": frozenset({"_UNBOUND_EVIDENCE_FIELD_ALLOWLIST"}),
        "new_assignment_prefixes": ("_EXACT_RUN_EVAL_", "_exact_run_eval_"),
    },
    "src/mini_agent/evaluation/graders.py": {
        "expected_defs": 54,
        "mutable_defs": frozenset(
            {
                "EvalEvidence",
                "RequestUnderstandingGrader",
                "InputBindingGrader",
                "_conversation_graph_reason",
                "_request_understanding_graph_reason",
                "_observation_persistence_graph_reason",
                "_tool_graph_is_closed",
                "ToolCallGrader",
                "_trace_references_match_typed_records",
                "PersistenceGrader",
            }
        ),
        "new_public_defs": frozenset(),
        "new_private_prefixes": ("_v2_",),
        "mutable_assignments": frozenset({"_FIXED_MESSAGES"}),
        "new_assignment_prefixes": ("_V2_", "_v2_"),
    },
}
V2_CLASS_CONTRACTS = {
    "src/mini_agent/evaluation/scripted_provider.py": (
        "ScriptedModelProviderV2",
        "ScriptedModelProvider",
    ),
    "src/mini_agent/infrastructure/model/qwen_responses.py": (
        "QwenResponsesAdapterV2",
        "QwenResponsesAdapter",
    ),
}


def base_source(path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"],
        text=True,
        encoding="utf-8",
    )


def top_level_defs(tree: ast.Module) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert node.name not in result, node.name
            result[node.name] = node
    return result


def assignment_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Assign):
        names = tuple(
            target.id for target in node.targets if isinstance(target, ast.Name)
        )
        return names if len(names) == len(node.targets) else ()
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target.id,)
    return ()


def top_level_assignments(tree: ast.Module) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        for name in assignment_names(node):
            assert name not in result, name
            result[name] = node
    return result


def exact_segment(source: str, node: ast.AST) -> str:
    start = node.lineno
    decorators = getattr(node, "decorator_list", ())
    if decorators:
        start = min(start, *(item.lineno for item in decorators))
    lines = source.splitlines(keepends=True)
    return "".join(lines[start - 1 : node.end_lineno])


def assert_exact_node(
    before: str,
    after: str,
    before_node: ast.AST,
    after_node: ast.AST,
) -> None:
    assert exact_segment(after, after_node) == exact_segment(before, before_node)
    assert ast.dump(after_node, include_attributes=False) == ast.dump(
        before_node,
        include_attributes=False,
    )


def forbidden_call_counts(tree: ast.Module) -> dict[str, int]:
    return {
        name: sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in FORBIDDEN_CALLS
    }


def imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def assert_v2_class_contract(
    path: str,
    definitions: dict[str, ast.AST],
) -> None:
    contract = V2_CLASS_CONTRACTS.get(path)
    if contract is None:
        return
    class_name, base_name = contract
    class_node = definitions[class_name]
    assert isinstance(class_node, ast.ClassDef), (path, class_name)
    assert not class_node.decorator_list, (path, class_name, "decorator")
    assert len(class_node.bases) == 1, (path, class_name, "base count")
    assert isinstance(class_node.bases[0], ast.Name), (path, class_name, "base shape")
    assert class_node.bases[0].id == base_name, (path, class_name, "base")
    assert not class_node.keywords, (path, class_name, "base keywords")

    class_members = [
        node
        for node in class_node.body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    assert len(class_members) == 1, (path, class_name, "class members")
    method = class_members[0]
    assert isinstance(method, ast.AsyncFunctionDef), (path, class_name, "async")
    assert method.name == "propose_next_move", (path, class_name, method.name)
    assert not method.decorator_list, (path, class_name, "method decorator")
    arguments = method.args
    assert not arguments.posonlyargs, (path, class_name, "positional-only")
    assert [argument.arg for argument in arguments.args] == [
        "self",
        "request",
    ], (path, class_name, "arguments")
    assert arguments.args[0].annotation is None, (path, class_name, "self annotation")
    request_annotation = arguments.args[1].annotation
    assert isinstance(request_annotation, ast.Name), (path, class_name, "request type")
    assert request_annotation.id == "RequestUnderstandingInput", (
        path,
        class_name,
        "request type",
    )
    assert arguments.vararg is None, (path, class_name, "vararg")
    assert not arguments.kwonlyargs, (path, class_name, "keyword-only")
    assert not arguments.kw_defaults, (path, class_name, "keyword defaults")
    assert arguments.kwarg is None, (path, class_name, "kwarg")
    assert not arguments.defaults, (path, class_name, "defaults")
    assert method.type_comment is None, (path, class_name, "type comment")
    assert isinstance(method.returns, ast.Name), (path, class_name, "return type")
    assert method.returns.id == "RequestUnderstandingOutputV2", (
        path,
        class_name,
        "return type",
    )


for path, config in CONFIG.items():
    before = base_source(path)
    after = Path(path).read_text(encoding="utf-8")
    before_tree = ast.parse(before)
    after_tree = ast.parse(after)
    before_defs = top_level_defs(before_tree)
    after_defs = top_level_defs(after_tree)
    assert len(before_defs) == config["expected_defs"], path

    for name, before_node in before_defs.items():
        assert name in after_defs, (path, name)
        if name not in config["mutable_defs"]:
            assert_exact_node(before, after, before_node, after_defs[name])
    extra_defs = set(after_defs) - set(before_defs)
    assert config["new_public_defs"].issubset(extra_defs), path
    assert all(
        name in config["new_public_defs"]
        or any(name.startswith(prefix) for prefix in config["new_private_prefixes"])
        for name in extra_defs
    ), (path, extra_defs)
    assert_v2_class_contract(path, after_defs)

    before_assignments = top_level_assignments(before_tree)
    after_assignments = top_level_assignments(after_tree)
    for name, before_node in before_assignments.items():
        assert name in after_assignments, (path, name)
        if name not in config["mutable_assignments"]:
            assert_exact_node(
                before,
                after,
                before_node,
                after_assignments[name],
            )
    extra_assignments = set(after_assignments) - set(before_assignments)
    assert all(
        any(
            name.startswith(prefix)
            for prefix in config["new_assignment_prefixes"]
        )
        for name in extra_assignments
    ), (path, extra_assignments)

    assert forbidden_call_counts(after_tree) == forbidden_call_counts(before_tree)
    assert imported_modules(after_tree) == imported_modules(before_tree), path

from mini_agent.evaluation.graders import GRADER_NAMES, grader_registry

assert len(GRADER_NAMES) == 13
assert tuple(grader_registry()) == GRADER_NAMES
print("01-07L protected surface: PASS (14/2/54/54 + v2 signatures + registry 13)")
PY
```

该oracle证明：

- v1 Scripted 14 top-level defs / 9 methods与Qwen 2 defs / 4 methods exact；
- 两个V2 class exact单继承对应v1 class，只有无decorator/default/union/variadic的typed async `propose_next_move`；Presentation path直接继承；
- Harness 54 pre-existing defs exact，只有approved allowlist assignment delta；
- Graders只有protected_surface列出的10个definition与`_FIXED_MESSAGES` assignment可变，其他definition/assignment exact；
- grader registry仍恰为13个原名原序，critical failures与E2E01-04 pair gate不变；
- 四个source module无import-module drift，且direct `__import__/exec/eval/globals/setattr` call计数不增加。

无alias/latest、network path、monkeypatch、new dependency或second Runtime由focused/full tests、changed-file containment与独立source review共同证明；本AST oracle不单独过度声明这些动态或跨模块保证。

Artifact/zero-network gate：

```bash
set -euo pipefail
base_sha=bbe14fadc0cd2e14ad35e19177b079fcab685dfc

git diff --exit-code "$base_sha...HEAD" -- \
  evals/fixtures/e2e01-thin-slice.v1.json \
  evals/cases/e2e01-thin-slice.v1.json \
  evals/model_scripts/e2e01-thin-slice.v1.json \
  evals/lanes/e2e01-thin-slice.v1.json \
  evals/manifests/e2e01-thin-slice.v1.json
env -u DASHSCOPE_API_KEY -u DASHSCOPE_BASE_URL \
  uv run pytest tests/component/model/test_qwen_responses_adapter.py -q
```

Cross-file impact scan：

```bash
set -euo pipefail

rg -n "ModelProviderV2|RequestUnderstandingCandidateInvalidError|RequestUnderstandingOutputV2|ExactRunEvidence|INPUT_INVALID|ProviderProtocolError|ORDER_SERVICE_UNAVAILABLE|FIXED_ORDER_SERVICE_UNAVAILABLE" \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
```

scan必须明确报告01-07J real Runtime catch、01-07S v1 Eval contract removal及legacy unavailable-policy迁移、01-08 Composition Root和01-08A runner为后续owner；本Packet不得越allowlist修正。Feature exact head须对九个changed files做独立canonical/security/test review并得到`PASS / CRITICAL-HIGH-MEDIUM-LOW = 0/0/0/0`。之后由Integrator在最新`integration/e2e01-thin`创建no-conflict overlay，证明patch identity、重复focused/full/hash/zero-network gate与独立review，再按K/L既定串行顺序merge。L单独merge不得写`B_DEPENDENCY`完成状态。

</verification>

<success_criteria>

1. RED/Provider GREEN/Mapper GREEN提交顺序、九文件scope与输出可复现；review fix只可append并逐commit受allowlist约束。
2. Scripted/Qwen v2 consumers严格区分candidate-invalid与protocol，raw diagnostics/cause/context不可达，v1 definitions/behavior不变。
3. Mapper只消费exact HTTP/result/closure，无Case/Script/owner/provider/raw envelope输入；v2 evidence不重建model output，13 graders保留并显式验证durable graph。
4. allowlist外与五tracked JSON零改动；Runtime/DB/Composition Root/active routing/lifecycle均未越权。
5. feature与latest-overlay均通过完整门禁和独立review；只有K/L都reviewed串行merge后才形成`B_DEPENDENCY`，真实Provider→Runtime `INPUT_INVALID`仍由J证明。

</success_criteria>
