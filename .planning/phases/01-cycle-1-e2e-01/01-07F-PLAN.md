---
phase: 01-cycle-1-e2e-01
plan: 07F
type: tdd
wave: 19
depends_on:
  - 01-07O
files_modified:
  - src/mini_agent/core/request_understanding.py
  - src/mini_agent/core/task_state.py
  - src/mini_agent/core/request_processing.py
  - tests/component/core/test_request_understanding_contract.py
  - tests/component/core/test_task_state_contract.py
  - tests/component/core/test_request_processing.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07F 只执行 CORE_EXPAND：增加显式 Request Understanding v2 model-facing、durable-safe DTO 与纯确定性 projection / local-closure validation；当前 v1 类型、函数、active consumers 和路由逐项保持不变。"
    - "RequestUnderstandingOutputV2 显式要求 e2e01-thin-v2，保存恰好一个实际 contextualization、0..n 个按 emitted order 保留且 candidate_id 唯一的 Candidate；它不接受 v1 alias、union、fallback、default/latest 或版本推断。"
    - "所有 model-facing source_quote 必填且为 1..128 Unicode code points；trusted owner scope 提供 authoritative immutable message 后，纯 Core 路径只接受 exact unique occurrence，按 Python str code-point offset 生成 span 与 lowercase SHA-256，并在 durable projection 中彻底移除 raw quote。"
    - "RequestUnderstandingRecordV2 使用独立 record identity、三个 exact schema axes、实际 contextualization / candidates、keyed candidate decisions、accepted refs、NextMove audit refs/versions和可信 UTC created_at；AcceptedTaskDeltaV2 作为 parent-local child 内联唯一 keyed Task effect。"
    - "candidate / decision / accepted child / Task effect 满足 exact-set、唯一引用、按 emitted candidate sequence 的 per-Task version chain 与同一可信 UTC sample；zero-candidate、all-reject、partial-accept、multi-accept 全部只能形成完整闭包或 bounded failure，不能形成 partial record。"
    - "现有三个 Core source 文件在 protected oracle a4b1edb4c50a2e3e826571194bac58f7b31eab6d 中的全部 41 个 top-level definition source segment 与 AST 均不变、不重绑、不 monkeypatch；allow_changed_existing_symbols=[]。"
    - "本 Packet 不修改 Application codec / registry、Provider、Runtime consumer、Ports、Infrastructure、数据库、migration、Eval、Composition Root、active canonical 文档、生命周期或任何 v1 consumer。"
  artifacts:
    - "三个 Core source 文件中的 additive v2 DTO、封闭 failure taxonomy、pure source-provenance projection 与 local-closure builder/validator。"
    - "三个 owned Component test 文件中的 RED/GREEN contract、provenance、closure、protected-v1 与 no-active-routing 证据。"
  key_links:
    - "Intent owner §13 durable identity / version / projection / exact-set / keyed Task effect / trusted-time rules → Thin Slice p0-ru-v2-cutover-r1 exact encoding → 01-07F additive Core types and pure validation。"
    - "01-07O p0-ru-v2-execution-map-r1：exact B_O_STATUS → 01-07F → reviewed B_F；01-07E 只能从 B_F 启动。"
---

# Phase 1 Plan 01-07F｜Request Understanding v2 Core expand

> **ISSUED CORE_EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只增加 non-routable v2 Core surface。任何测试通过都不表示 codec、Provider、Runtime、PostgreSQL、Eval mapper、active switch、Trajectory / E2E Result 或产品 readiness 已完成。

> **DERIVED / NON_NORMATIVE**
> Request Understanding 语义由 Intent owner 拥有，第一薄切片 exact encoding 由 Thin Slice scoped owner 拥有，执行顺序由 `P0-RU-V2-EXECUTION-MAP` 拥有。本 Plan 只把三者映射为一个精确、可回滚的 Core Task Packet，不反向覆盖 owner。

<objective>
以 TDD RED→GREEN 增加显式 Request Understanding v2 model-facing / durable-safe DTO、封闭 failure taxonomy、纯 source-provenance projection 和 local durable closure validation，同时 byte/AST 保护全部现有 v1 top-level definitions。

Purpose: 形成 reviewed exact `B_F`，让 01-07E 可以在下一独立 Worktree 从该 barrier 增加 exact-version、non-routable Application codec catalog entry。

Output: 三个 test-only RED 文件与三个 additive Core GREEN 文件，形成两个有序原子提交；不创建 Summary、不修改共享 State。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07D-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07N-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07O-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/core/request_understanding.py
@src/mini_agent/core/task_state.py
@src/mini_agent/core/request_processing.py
@tests/component/core/test_request_understanding_contract.py
@tests/component/core/test_task_state_contract.py
@tests/component/core/test_request_processing.py

只使用受控 execution adapter；不得调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。Graphify 按用户指令暂停：本 Packet 不读取、不运行、不更新，也不把它作为 gate。
</execution_context>

<interfaces>

## 1. Model-facing direct binding

`src/mini_agent/core/request_understanding.py` 只能在全部既有定义之后追加新 import / definition；既有 import 可以保持原样。下列 public v2 types 是 Thin Slice manifest 的直接实现：

```python
class ResolvedReferenceCandidateV2(ModelVisibleModel):
    name: Literal["order_id"]
    candidate_value: NonEmptyString
    source_kind: ReferenceSourceKindV2  # CURRENT_MESSAGE | RECENT_MESSAGE
    source_ref: UUID
    source_quote: Annotated[str, Field(min_length=1, max_length=128)]
    confidence: Confidence

class UncertaintyV2(ModelVisibleModel):
    name: Literal["order_id"]
    candidate_values: tuple[NonEmptyString, ...]
    reason_code: UncertaintyReasonCodeV2
    source_message_refs: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=8)]

class QueryContextualizationCandidateV2(ModelVisibleModel):
    text: NonEmptyString
    resolved_reference_candidates: tuple[ResolvedReferenceCandidateV2, ...]
    uncertainties: tuple[UncertaintyV2, ...]
    source_message_refs: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=8)]

class RequestUnderstandingOutputV2(ModelVisibleModel):
    schema_version: Literal["e2e01-thin-v2"]
    message_ref: UUID
    contextualization: QueryContextualizationCandidateV2
    task_delta_candidates: tuple[TaskDeltaCandidate, ...]
    next_move_candidate: NextMove
```

约束：

- `schema_version` 没有 default；调用方必须显式提供 exact literal。
- `UncertaintyReasonCodeV2` 只有 `MISSING_REFERENCE` 与 `MULTIPLE_PLAUSIBLE_REFERENCES`。前者 `candidate_values` 恰为 0；后者恰为 2..8 且 unique。`source_message_refs` 始终 1..8 unique；所有 tuple 保留 emitted order，不排序。
- `QueryContextualizationCandidateV2.source_message_refs` unique；所有 resolved `source_ref` 都在其中。`RequestUnderstandingOutputV2` 再要求 parent `message_ref` 在其中。
- v2 structural Candidate cardinality 是 0..n，`candidate_id` unique。
- `task_delta_candidates` 绑定现有 protected `TaskDeltaCandidate` / `InputCandidate`，`next_move_candidate` 绑定现有 protected `NextMove`；这是 manifest 未另命名 nested shape 的实现映射，不是把 v1 output alias / union 成 v2。外层 v2 validator额外要求每个 InputCandidate `source_quote` 不超过128 code points、`source_ref == parent.message_ref`、`authority=USER_CLAIM`、`source_kind=CURRENT_MESSAGE`。
- 当前薄切片只包含新目标 `ADD_GOAL`；v2 outer validator继续要求`next_move_candidate.base_task_state_version is None`。positive version即使能单独构造为`NextMove`，也不能进入canonical `RequestUnderstandingOutputV2`；sentinel `0`仍由`NextMove` strict field直接拒绝。
- `ResolvedReferenceCandidateV2` 允许 `RECENT_MESSAGE` 只表示 model candidate；能否形成 durable projection仍取决于 trusted owner scope提供对应 authoritative message和 exact provenance。
- 所有 class 继续继承 frozen、extra-forbid contract base；禁止 `customer_id`、authorization、business fact、Tool execution、span/hash、record identity、Task effect或可信时间进入 model-facing types。

## 2. Durable direct binding and implementation-local containers

`src/mini_agent/core/task_state.py` 追加：

- `DurableResolvedReferenceCandidateV2`：字段顺序恰为 `name, candidate_value, source_kind, source_ref, source_span_start, source_span_end_exclusive, source_quote_sha256, confidence`。
- `DurableInputCandidateV2`：字段顺序恰为 `name, candidate_value, semantic_role, authority, source_kind, source_ref, source_span_start, source_span_end_exclusive, source_quote_sha256, confidence`。
- `CandidateRejectionReasonCode`：按 manifest 顺序封闭为 `OPERATION_NOT_SUPPORTED, GOAL_PATCH_NOT_ACTIONABLE, REQUIRED_INPUT_MISSING, INPUT_VALUE_INVALID, REFERENCE_UNRESOLVED, REFERENCE_AMBIGUOUS, NEXT_MOVE_INCONSISTENT`。
- `RequestUnderstandingAggregateFailureCodeV2`：按 manifest 顺序封闭为 `MODEL_INPUT_SCHEMA_INVALID, MODEL_OUTPUT_SCHEMA_INVALID, MODEL_SCHEMA_VERSION_INVALID, TRUSTED_OR_PRIVATE_FIELD_PRESENT, SOURCE_PROVENANCE_INVALID`。
- `RequestUnderstandingAtomicFailureCodeV2`：按 manifest 顺序封闭为 `TASK_STATE_CAS_CONFLICT, TASK_COMMIT_FAILED, DURABLE_CLOSURE_COMMIT_FAILED`。
- `CandidateValidationRecordV2(candidate_ref, decision, reason_code)`：`ACCEPT` 无 reason；`REJECT` 只接受封闭 candidate reason；禁止自由文本。
- `AcceptedTaskDeltaV2`：字段顺序恰为现有 `accepted_delta_id, candidate_ref, message_ref, operation, goal_text, input_binding_refs, accepted_at`，再内联 `task_id, base_task_state_version, result_task_state_version`；时间必须 UTC，base 不使用0，result为正整数。
- `RequestUnderstandingRecordV2`：字段顺序恰为 `request_understanding_record_id, run_id, message_ref, schema_version, model_input_schema_version, model_output_schema_version, contextualization, task_delta_candidates, candidate_validation, accepted_delta_refs, proposed_base_task_state_version, validated_task_state_version, next_move_candidate_ref, created_at`。

三个 record literals 分别是：

```text
schema_version=request_understanding_record.p0.v2
model_input_schema_version=e2e01-thin-v1
model_output_schema_version=e2e01-thin-v2
```

`source_span_start` 是 strict non-negative int；`source_span_end_exclusive` 是 strict int且必须大于start；`source_quote_sha256`完整匹配`^[0-9a-f]{64}$`。两个 durable leaf 完全没有 `source_quote`。

manifest 没有为 parent 内的两个无 raw-quote container 分配 Python 名称。实现可追加 `DurableQueryContextualizationCandidateV2` 与 `DurableTaskDeltaCandidateV2` 作为 **implementation-local typed containers**：

- 前者只把 `QueryContextualizationCandidateV2.resolved_reference_candidates` 替换为 durable leaf，其余字段与顺序不变；
- 后者只把 `TaskDeltaCandidate.input_candidates` 替换为 durable leaf，其余字段与顺序不变；
- 它们不建立新 record code、schema version、canonical owner或外部 compatibility promise。

`RequestUnderstandingRecordV2` 不含 `accepted_task_deltas`、`task_state_version_bindings`、global base/result或parallel version arrays。`AcceptedTaskDeltaV2` 仍由 record code `accepted_task_delta` 表示 parent-local logical child。

## 3. Pure projection and closure API

`src/mini_agent/core/request_processing.py` 在既有 v1 reducer之后追加独立 v2 API：

```python
class RequestUnderstandingV2Error(ValueError):
    reason_code: (
        RequestUnderstandingAggregateFailureCodeV2
        | RequestUnderstandingAtomicFailureCodeV2
    )

class RequestUnderstandingClosureV2(RuntimePrivateModel):
    record: RequestUnderstandingRecordV2
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...]

def build_request_understanding_closure_v2(
    *,
    request_input: RequestUnderstandingInput,
    output: RequestUnderstandingOutputV2,
    authoritative_messages: Mapping[UUID, str],
    request_understanding_record_id: UUID,
    candidate_validation: tuple[CandidateValidationRecordV2, ...],
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...],
    proposed_base_task_state_version: PositiveStateVersion | None,
    validated_task_state_version: PositiveStateVersion | None,
    next_move_candidate_ref: UUID | None,
    now: datetime,
) -> RequestUnderstandingClosureV2: ...
```

该名称和 runtime-private wrapper 是实现局部 API，不新增 canonical 持久化字段。它必须：

1. 要求 exact `RequestUnderstandingInput`、exact `RequestUnderstandingOutputV2`、exact child/decision DTO和 UTC `now`；dict、v1 output、subclass、missing参数或`model_construct`后形成的非法结构均 fail closed。`request_input.model_fields_set`必须显式包含`schema_version`，不接受protected v1 DTO的construction default替代本次实际gate。record的`run_id`与`model_input_schema_version`必须分别直接取自本次实际通过exact gate的`request_input.run_id`与`request_input.schema_version`，不能从常量、output、Prompt或当前默认值推断；`request_input.message_ref == output.message_ref`。
2. `authoritative_messages` 是 trusted caller 已在 owner scope加载的 immutable message projection；Core不做I/O、不解析身份、不授予 owner scope。当前message的authoritative原文还必须与实际validated `request_input.original_query` exact相等。缺ref、非字符串、空原文、quote等于整条原文、零次或多次 exact occurrence均抛出只含稳定分类的 bounded `SOURCE_PROVENANCE_INVALID`。
3. 对每个 resolved/input quote不做 trim、case-fold、Unicode normalization、regex近似或模糊匹配；枚举 overlapping exact occurrence，要求恰好一次；使用 Python `str` code-point start/end和`sha256(exact_slice.encode("utf-8")).hexdigest()`构造 durable leaf。
4. source quote还必须精确覆盖对应 `candidate_value` 的受控 order-id来源；沿用 existing normalization只能用于该 candidate/value一致性检查，不能用于定位quote。durable projection保存 emitted candidate value，不把它改写为 business fact。
5. record只由 trusted arguments与实际 output safe projection构建；model/caller没有span/hash字段入口。形成durable leaf后，返回对象与builder的bounded error均不保留raw quote；Provider schema `ValidationError` 的对外redaction仍由后续Adapter owner负责，本Packet不建立active transport。
6. emitted candidate IDs、validation refs、accepted decisions、accepted child candidate refs和accepted delta IDs满足exact-set；每个ACCEPT恰好一个child且无reason，每个REJECT有封闭reason且无child/effect；child `message_ref == parent.message_ref`，accepted ID和`(accepted_delta_id, task_id)`均unique。
7. `accepted_delta_refs`按 child 输入顺序保存但closure按set比较；Task version chain只按 emitted candidate sequence过滤ACCEPT，不按UUID、refs或caller order重排。每个新Task的base为None、result为正整数；同一Task后续effect的base必须等于前一result且result严格递增，拒绝fork、gap、rollback与重复base。当前成功测试固定`None → 1`，但不把所有未来initial version静默缩窄为1。
8. parent `created_at`与全部child `accepted_at`精确等于同一个 trusted UTC `now`。NextMove versions在无`next_move_candidate_ref`时必须全部为None；ref存在时两个version仍各自optional，不借本Packet发明owner未冻结的额外presence matrix。
9. zero-candidate、all-reject、partial-accept和multi-accept均可形成完整closure；任一不一致只返回bounded error，不返回partial record。Schema/version/private/provenance错误只使用aggregate bucket；trusted decision/child/Task-effect无法闭合只使用atomic `DURABLE_CLOSURE_COMMIT_FAILED`；candidate rejection reason永不被用来伪装前两类失败。

直接构造 durable DTO只证明严格结构，不证明span/hash authority或owner scope；active write必须经后续 trusted Application/Runtime consumer调用该builder，owner-scoped read仍由后续strict reader重新读取authoritative message并验证exact slice/hash。本Packet没有active consumer。
</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-core-expand`
base_branch: `integration/e2e01-thin`
base_sha: `73696a138eb13fc4a90a0f760b13865f53d08704`
base_tree: `952ba7a87354cab1fba42f13eb1546e01f97f1c2`
input_barrier: `B_O_STATUS`
output_barrier: `B_F`
worktree_id: `e2e01-01-ru-v2-core-expand`
writer: `Request Understanding Core sole writer with owned tests, supervised by /root Integrator`
agent_role: `runtime-engineer`
active_routing: `false`

物理 Worktree path 只在 private dispatch handoff 中传递，不写入 commit 或 PR。

planning_and_owner_provenance:

- Intent owner current commit `327b39da45cdcf564609a5385d52c4264da2c669`，blob `456be9c7d7884e2a58c4d07b867765ed336aa6f5`
- Memory owner current commit `be68490b9d8440a29a43fa8143e9dd5d4bcbfeda`，blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- Thin Slice exact encoding commit `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`，blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- Multi-agent execution view commit `4ed68875fdf2330b6947b7f85235cec388d2af14`，blob `d248fc670659eb37bce89d97c7f9f883b69373e7`
- 01-07C Plan commit `79ae0a921cb8a6ff64f308ddf377c93354701cf8`，blob `66a3a974f5d7408239b8ba3691abdb0c1781fa63`
- 01-07D Plan commit `5d72cb70bf5dc97ae2f74ab1697a61e77a23b725`，blob `e63b844301f8d74da80bc8a1d01bbf3eea689de8`
- 01-07N Plan commit `7dccac2eeffbc018fc901be2bce37978fb64c64a`，blob `f679872c424a53e9acbe59a4d5bc116d13b1dcc1`
- 01-07O Plan commit `274178bad8796e08831dcd9204b6610c19930982`，blob `ef63e5a79b61622e3b495d3ba8d49801e3054cbe`
- `PROJECT_DIRECTION.md` status barrier commit `73696a138eb13fc4a90a0f760b13865f53d08704`，blob `2d5484570b3a15a8f16d1fde51e619df330d93ca`
- 本 Plan 的 official planning merge SHA / blob由Integrator在Plan PR reviewed merge后从official integration ref捕获；planning merge不替换feature execution base `B_O_STATUS`

owned_files_at_base:

- `src/mini_agent/core/request_understanding.py` = `77bf975bd34212041458cc212cc92b2f8cb11b7b`
- `src/mini_agent/core/task_state.py` = `311767a7045063846ca9527dc6298e00350cc4ba`
- `src/mini_agent/core/request_processing.py` = `ac71ef9c2c462a4e66787310d2d0131cdce4d7b0`
- `tests/component/core/test_request_understanding_contract.py` = `c05721ab372e531ced1612a855b7947ec0f4a7de`
- `tests/component/core/test_task_state_contract.py` = `666850342ff7add16eeda243876913b1221d1a34`
- `tests/component/core/test_request_processing.py` = `a55fa199502f79010f92a65ef708b5a9522bbce0`

protected_v1_surface:

- mode: `all-preexisting-top-level-definitions`
- oracle_sha: `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`
- files: 三个 owned Core source 文件
- allow_changed_existing_symbols: `[]`
- oracle blobs与`owned_files_at_base`中三个source blob相同
- definition counts: request_understanding=15、task_state=13、request_processing=13，总计41
- 对每个oracle symbol同时比较 `ast.dump(include_attributes=False)` 与 exact source segment SHA-256；candidate必须仍恰好一个同名module binding
- 新增AST只允许append-only import、new-name alias/constant、undecorated class/function definition；任何tail binding不得覆盖baseline或同tail名称。检测Import/ImportFrom alias、Store/Delete/AugAssign/NamedExpr、`global`/`nonlocal`、protected attribute assignment、`setattr`/`delattr`、`globals`/`vars`/`exec`/`eval`与module-load call等重绑或间接mutation
- module-load expression只允许origin可证明为`pydantic`且exact name为`Field`、`field_validator`、`model_validator`或`field_serializer`的bare call；禁止别名化hazardous callable和attribute-call
- gate内置import-alias、`del`、`globals()`、helper/global、direct/aliased `setattr`和`object.__setattr__` mutants；每个mutant必须被拒绝
- 新imports使用独立追加语句，新definitions追加在最后；不编辑已有definition source segment

owned_files:

- `src/mini_agent/core/request_understanding.py`
- `src/mini_agent/core/task_state.py`
- `src/mini_agent/core/request_processing.py`
- `tests/component/core/test_request_understanding_contract.py`
- `tests/component/core/test_task_state_contract.py`
- `tests/component/core/test_request_processing.py`

forbidden_files:

- every repository path outside the six exact owned files
- especially `AGENTS.md`、`README.md`、`PROJECT_DIRECTION.md`、`docs/**`、`.planning/**`、`src/mini_agent/application/**`、other `src/mini_agent/core/**`、`src/mini_agent/runtime/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`graphify-out/**`
- any modification/removal/rebinding/monkeypatch of the 41 protected v1 definitions
- Application codec/catalog/versioned API、Port、physical schema、Provider/Runtime/Eval consumer、active registry/routing、v1 retirement、migration/backfill/fallback

dependencies:

- 首次编辑前必须证明branch、clean status、`HEAD == B_O_STATUS`、tree、merge-base与六个owned blob精确匹配。
- official planning merge必须存在且其六个owned blob仍等于B_O_STATUS；Plan merge只提供provenance，不改变feature lineage。
- `P0-RU-V2-CUTOVER-MANIFEST`必须仍是`p0-ru-v2-cutover-r1`；`P0-RU-V2-EXECUTION-MAP`必须仍是`p0-ru-v2-execution-map-r1`且F的input/output barrier、branch、worktree、allowlist、protected surface与本Packet完全一致。
- 01-07E planning/dispatch在01-07F feature exact-head review、latest-integration replay、serial merge与post-merge gate共同形成`B_F`前保持`BLOCK`。

required_checks:

- v2 fields、field order、literal versions、enum order、cardinality、uniqueness、extra-forbid、frozen与no-alias矩阵。
- 0/129 quote、missing/extra field、wrong source kind、uncertainty reason/cardinality/ref uniqueness、missing current message、duplicate candidate ID、positive/zero base Task version均fail closed；`model_construct`绕过outer invariant也在builder再次拒绝。
- builder必须绑定exact实际`RequestUnderstandingInput`且其`model_fields_set`显式包含`schema_version`；missing/defaulted/wrong/dict/subclass/`model_construct`非法input、input/output message mismatch与authoritative current message mismatch均bounded fail closed，record直接保存该input实际通过的schema version而非当前常量/default。
- durable raw quote/identity/private-field extra拒绝，span/hash strict matrix与三个schema axes独立。
- Unicode exact unique span/hash positive；zero/multiple/full-message/trim/casefold/Unicode-normalization negatives；resolved/input两类quote都投影且返回闭包不含raw quote。
- zero/all-reject/partial/multi closure、missing/extra/duplicate/dangling/wrong-candidate child、accepted set、message/timestamp mismatch与per-Task chain fork/gap/rollback/reorder矩阵。
- 所有 v1 Component tests保持原断言全绿，41-symbol AST/source gate全绿。
- repo source consumer scan证明v2 symbols只出现在三个owned source和三个owned tests；没有Application/Infra/Eval/Runtime active import。
- 仓库没有canonical lint、type-check或build命令；不得编造。执行project canonical dependency/database/full-test门禁并如实报告。
- 任一preflight、RED reason、focused/full test、protected-v1、allowlist、consumer scan、review或clean-status失败均`BLOCK`。

cross_file_impact:

- canonical owners与execution map已授权F additive stage；F不修改owner正文。
- README latest integration overlay只做derived status alignment，不改变B_O_STATUS feature base或F contract。
- `.planning/PROJECT.md`、`REQUIREMENTS.md`、`ROADMAP.md`、`STATE.md`、Validation与Summary会在F/E均reviewed merge后由独立single-writer status barrier统一对齐；feature writer不得越界。
- 01-07E、I/P、K/L、M、Q、J、S/U、X、T、W、V保持downstream blocked；本Packet不声称repository-wide aligned。

commit_protocol:

1. RED commit `test(01-07F): define request understanding v2 core contract` 只改三个 owned test 文件；三个 source blob仍等于B_O_STATUS。focused command必须因缺少新v2 symbols/API或新contract assertion失败，不得因syntax、fixture、错误路径或环境失败。
2. GREEN commit `feat(01-07F): add request understanding v2 core expand` 只改三个 owned source 文件；不得重写RED commit。focused、protected-v1、consumer scan、canonical database/full-suite与scope gate全部通过。
3. 正常feature history相对B_O_STATUS恰为以上两个提交。Review finding先阻止ready；修复只在六文件allowlist内追加`fix(01-07F): ...` commit，对新exact head重新运行完整review与门禁，不得amend/rebase/force-push已审历史。

done_when:

- RED/GREEN commit顺序、failure reason、SHA和输出可复现；changed-file union恰为六文件。
- v2 direct types、safe projection、closed failure taxonomy与local closure满足owner/manifest；41个v1 definition source/AST与active behavior不变。
- focused、full suite、exact scope、consumer scan、cross-file impact scan与clean status全部通过。
- feature exact head与latest-integration overlay exact head均取得独立review，unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`。
- draft PR精确使用feature head → `integration/e2e01-thin`；reviewed serial merge后才记录`B_F`，不推进Case/Requirement/Phase lifecycle。

contract_changes: `YES / ADDITIVE CORE_EXPAND ONLY` — 增加显式RU v2 model-facing与durable-safe DTO、封闭failure taxonomy、pure provenance projection和exact local closure；保持全部v1 definitions与active consumers。无alias、union、fallback、migration、codec、registry、physical schema、active routing或v1 retirement。
security_impact: `YES` — exact owner-scoped provenance输入、raw-quote消除、trusted identity/time/version分离、private-field排除、candidate/child/Task-effect closure、bounded failure与no-partial-record；Core接收authoritative message projection不自行证明owner scope，后续trusted consumer和strict reader仍必须分别建立write/read authority。
eval_impact: `YES / COMPONENT CONTRACT ONLY` — owned Component tests增加v2 DTO/provenance/closure与v1 non-regression；不改Dataset、Grader、Result、threshold、Case、requirement lifecycle、Trajectory或E2E状态。
new_dependencies: `NONE`
graphify_disposition: `DISABLED_BY_USER / NOT_RUN / NOT_A_GATE`
rollback: 合并前关闭PR；合并后普通revert PR按feature range严格逆序撤销全部01-07F feature/fix commits，重新阻塞`B_F`及E→I/P→K/L→M→Q→J→S/U→X→T→W→V。不得reset、force-push、schema/data rollback、fallback、backfill、readiness或lifecycle claim。

handoff_to: `/root Integrator`
handoff_format: branch、exact base/planning/head/commits/tree、owner/Plan与六个base/head blobs、RED/GREEN输出、41-symbol AST/source结果、focused/database/full-suite结果、changed files/commit containment、consumer/cross-file scan、contract/security/Eval nonclaims、feature/overlay review、风险、`B_F` merge SHA与rollback。
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUV2-S01` | Spoofing | model/caller → identity、owner scope、span/hash、Task effect、time | `MITIGATE / BLOCK` | model DTO无可信字段；builder只接收trusted caller参数并自行派生span/hash；Core不声称owner scope，active consumer/reader仍需后续gate |
| `RUV2-T01` | Tampering | output/candidate/decision/child → durable closure | `MITIGATE / BLOCK` | frozen extra-forbid DTO、exact versions、exact-set closure、unique refs/pairs、per-Task sequence chain与no-partial return |
| `RUV2-R01` | Repudiation | RED/GREEN/review → evidence | `MITIGATE / BLOCK` | 两个有序atomic commits、base/owner blobs、41-symbol snapshot、full output、exact-head independent review |
| `RUV2-I01` | Information Disclosure | raw quote/private field → durable/exception/active consumer | `MITIGATE / BLOCK` | 1..128 transient quote、exact projection后消除、durable leaf无quote、bounded error、consumer absence scan |
| `RUV2-D01` | Denial of Service | malformed/ambiguous provenance或graph → reducer | `MITIGATE / BOUNDED` | bounded cardinality、exact occurrence scan、stable error、无I/O、无retry/recursive fallback |
| `RUV2-E01` | Elevation of Privilege | Claim/model inference/codec success → business authority | `MITIGATE / BLOCK` | input仍为Claim；codec/read/owner/business authority四态分离；F不路由、不授权、不产生Observation/Evidence |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze v2 DTO, provenance, closure and protected-v1 matrices</name>
  <files>tests/component/core/test_request_understanding_contract.py, tests/component/core/test_task_state_contract.py, tests/component/core/test_request_processing.py</files>
  <read_first>Intent owner §6/7/8/13、Memory exact-version/integrity rules、Thin Slice §5.1/§10.1.1 manifest、01-07O execution map、六个 B_O_STATUS owned blobs与protected oracle</read_first>
  <behavior>
    - model-facing exact fields/literals/reasons/cardinality/order/frozen/extra/null-base rules。
    - durable leaf/record/child exact fields、span/hash、UTC、three-version axes、raw/private exclusion。
    - exact Unicode provenance projection和zero/all/partial/multi local closure正负矩阵。
    - 41个v1 definitions source/AST unchanged且无top-level rebinding/monkeypatch；现有v1行为继续通过。
  </behavior>
  <action>只改三个test文件。用新v2类型/API imports和行为测试冻结本Plan的完整矩阵，包括exact实际`RequestUnderstandingInput`绑定、positive/zero base-version与`model_construct`绕过；Component tests不执行Git命令，41-symbol oracle comparison和mutation suite由本Plan verification中的独立机械gate负责。运行focused command取得真实RED，确认失败仅指向尚不存在的新v2 surface，然后提交精确RED message。</action>
  <verify>
    <automated>uv run pytest tests/component/core/test_request_understanding_contract.py tests/component/core/test_task_state_contract.py tests/component/core/test_request_processing.py -q</automated>
    RED必须非零退出且失败原因是缺少01-07F新增surface；三个source blobs、其他test、Application/Infra/Eval/owner文件仍等于base。
  </verify>
  <acceptance_criteria>三个test文件覆盖must_haves/required_checks；RED commit只包含三个test文件；无skip/xfail/conditional pass、无模型/网络/数据库依赖。</acceptance_criteria>
  <done>行为先于实现固定，RED原因正确且可复现。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — append isolated v2 Core types and pure closure path</name>
  <files>src/mini_agent/core/request_understanding.py, src/mini_agent/core/task_state.py, src/mini_agent/core/request_processing.py</files>
  <read_first>Task 1 RED commit/output、interfaces、41-symbol oracle、existing strict/frozen model patterns与bounded v1 reducer</read_first>
  <behavior>
    - 所有RED矩阵转绿；projection exact-copy并只生成safe span/hash。
    - 完整或bounded failure二选一；不返回partial record、不泄漏raw input。
    - existing v1 definitions、tests、imports by active consumers和运行行为不变。
  </behavior>
  <action>只在三个source文件的既有definitions之后追加独立imports/new definitions；实现interfaces中的v2 types、enums、implementation-local containers、bounded error、runtime-private closure和pure builder。禁止编辑/装饰/重绑任何existing symbol，禁止Application/Infra/Eval wiring，禁止version fallback/alias/union。focused与mechanical gates转绿后提交精确GREEN message，再运行canonical database/full-suite与review preflight。</action>
  <verify>
    <automated>uv sync --all-groups
uv run pytest tests/component/core/test_request_understanding_contract.py tests/component/core/test_task_state_contract.py tests/component/core/test_request_processing.py -q
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest</automated>
  </verify>
  <acceptance_criteria>三个source文件只包含additive imports/definitions；focused/full、protected-v1、scope与consumer scan全绿；没有active routing或downstream source import。</acceptance_criteria>
  <done>01-07F Core expand完成，feature可进入exact-head review但尚未形成B_F。</done>
</task>

</tasks>

<verification>

```bash
set -euo pipefail

base_sha=73696a138eb13fc4a90a0f760b13865f53d08704
base_tree=952ba7a87354cab1fba42f13eb1546e01f97f1c2
oracle_sha=a4b1edb4c50a2e3e826571194bac58f7b31eab6d
expected_branch=codex/e2e01-01-ru-v2-core-expand

test "$(git branch --show-current)" = "$expected_branch"
test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "${base_sha}:src/mini_agent/core/request_understanding.py")" = 77bf975bd34212041458cc212cc92b2f8cb11b7b
test "$(git rev-parse "${base_sha}:src/mini_agent/core/task_state.py")" = 311767a7045063846ca9527dc6298e00350cc4ba
test "$(git rev-parse "${base_sha}:src/mini_agent/core/request_processing.py")" = ac71ef9c2c462a4e66787310d2d0131cdce4d7b0
test "$(git rev-parse "${base_sha}:tests/component/core/test_request_understanding_contract.py")" = c05721ab372e531ced1612a855b7947ec0f4a7de
test "$(git rev-parse "${base_sha}:tests/component/core/test_task_state_contract.py")" = 666850342ff7add16eeda243876913b1221d1a34
test "$(git rev-parse "${base_sha}:tests/component/core/test_request_processing.py")" = a55fa199502f79010f92a65ef708b5a9522bbce0

expected_files=$'src/mini_agent/core/request_processing.py\nsrc/mini_agent/core/request_understanding.py\nsrc/mini_agent/core/task_state.py\ntests/component/core/test_request_processing.py\ntests/component/core/test_request_understanding_contract.py\ntests/component/core/test_task_state_contract.py'
test "$(git diff --name-only "${base_sha}...HEAD" | LC_ALL=C sort)" = "$expected_files"
git diff --check "${base_sha}...HEAD"
test "$(git rev-list --count "${base_sha}..HEAD")" -ge 2
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '1p')" = "test(01-07F): define request understanding v2 core contract"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '2p')" = "feat(01-07F): add request understanding v2 core expand"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '3,$p' | awk '!/^fix\\(01-07F\\): / {bad++} END {print bad+0}')" -eq 0

red_sha=$(git rev-list --reverse "${base_sha}..HEAD" | sed -n '1p')
green_sha=$(git rev-list --reverse "${base_sha}..HEAD" | sed -n '2p')
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha" | LC_ALL=C sort)" = $'tests/component/core/test_request_processing.py\ntests/component/core/test_request_understanding_contract.py\ntests/component/core/test_task_state_contract.py'
test "$(git diff-tree --no-commit-id --name-only -r "$green_sha" | LC_ALL=C sort)" = $'src/mini_agent/core/request_processing.py\nsrc/mini_agent/core/request_understanding.py\nsrc/mini_agent/core/task_state.py'

uv run python - "$oracle_sha" <<'PY'
import ast
import hashlib
import subprocess
import sys
from pathlib import Path

ORACLE = sys.argv[1]
FILES = (
    "src/mini_agent/core/request_understanding.py",
    "src/mini_agent/core/task_state.py",
    "src/mini_agent/core/request_processing.py",
)

def protected_bindings(tree):
    result = {}
    for node in tree.body:
        names = []
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        for name in names:
            result.setdefault(name, []).append(node)
    return result

def root_name(node):
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None

def node_bound_names(node):
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return {node.name}
    if isinstance(node, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom):
        if node.module == "__future__":
            return set()
        return {alias.asname or alias.name for alias in node.names}
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()

def import_origins(nodes):
    result = {}
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                result[alias.asname or alias.name] = (node.module, alias.name)
    return result

class ModuleLoadCallCollector(ast.NodeVisitor):
    def __init__(self):
        self.calls = []

    def visit_Call(self, node):
        self.calls.append(node)
        self.generic_visit(node)

    def _visit_function_shell(self, node):
        for decorator in node.decorator_list:
            self.visit(decorator)
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        if node.args.vararg is not None and node.args.vararg.annotation is not None:
            self.visit(node.args.vararg.annotation)
        if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
            self.visit(node.args.kwarg.annotation)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_FunctionDef(self, node):
        self._visit_function_shell(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function_shell(node)

    def visit_Lambda(self, node):
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)

def assert_protected(path, old, new):
    old_tree, new_tree = ast.parse(old), ast.parse(new)
    old_bindings = protected_bindings(old_tree)
    protected = set(old_bindings)

    # Strong append-only invariant: all pre-existing module bytes and AST nodes
    # remain the exact prefix; only a controlled tail may be added.
    assert new.startswith(old), (path, "existing-module-bytes")
    assert len(new_tree.body) >= len(old_tree.body), (path, "module-body-shortened")
    for old_node, new_node in zip(old_tree.body, new_tree.body, strict=False):
        assert ast.dump(old_node, include_attributes=False) == ast.dump(
            new_node, include_attributes=False
        ), (path, "module-prefix-ast")

    for name, old_nodes in old_bindings.items():
        assert len(old_nodes) == 1, (path, name, "oracle-count")
        old_node = old_nodes[0]
        new_node = new_tree.body[old_tree.body.index(old_node)]
        assert ast.dump(old_node, include_attributes=False) == ast.dump(
            new_node, include_attributes=False
        ), (path, name, "ast")
        old_segment = ast.get_source_segment(old, old_node)
        new_segment = ast.get_source_segment(new, new_node)
        assert old_segment is not None and new_segment is not None
        assert hashlib.sha256(old_segment.encode()).digest() == hashlib.sha256(new_segment.encode()).digest(), (path, name, "source")

    allowed_tail = (
        ast.Import,
        ast.ImportFrom,
        ast.Assign,
        ast.AnnAssign,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
    )
    tail = new_tree.body[len(old_tree.body):]
    baseline_names = set().union(
        *(node_bound_names(node) for node in old_tree.body)
    )
    occupied_names = set(baseline_names)
    for node in tail:
        assert isinstance(node, allowed_tail), (path, type(node).__name__, "tail-node")
        new_names = node_bound_names(node)
        assert occupied_names.isdisjoint(new_names), (
            path,
            sorted(occupied_names.intersection(new_names)),
            "module-name-rebind",
        )
        occupied_names.update(new_names)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in protected, (path, node.name, "definition-rebind")
            assert not node.decorator_list, (path, node.name, "top-level-decorator")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                assert bound not in protected, (path, bound, "import-rebind")
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                assert bound not in protected, (path, bound, "import-from-rebind")
        elif isinstance(node, ast.Assign):
            assert all(isinstance(target, ast.Name) for target in node.targets), (
                path,
                "non-name-assignment",
            )
            assert all(target.id not in protected for target in node.targets), (
                path,
                "assignment-rebind",
            )
        elif isinstance(node, ast.AnnAssign):
            assert isinstance(node.target, ast.Name), (path, "non-name-annassign")
            assert node.target.id not in protected, (path, node.target.id, "annassign-rebind")

    safe_pydantic_calls = {
        "Field",
        "field_validator",
        "model_validator",
        "field_serializer",
    }
    origins = import_origins((*old_tree.body, *tail))
    safe_call_names = {
        bound
        for bound, origin in origins.items()
        if origin[0] == "pydantic"
        and origin[1] in safe_pydantic_calls
        and bound == origin[1]
    }
    module_load_calls = ModuleLoadCallCollector()
    for node in tail:
        module_load_calls.visit(node)
    for call in module_load_calls.calls:
        assert isinstance(call.func, ast.Name), (
            path,
            ast.dump(call.func, include_attributes=False),
            "module-load-attribute-call",
        )
        assert call.func.id in safe_call_names, (
            path,
            call.func.id,
            "module-load-unsafe-call",
        )

    hazardous_calls = {"globals", "vars", "exec", "eval", "setattr", "delattr"}
    for node in ast.walk(ast.Module(body=tail, type_ignores=[])):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            assert node.id not in protected, (path, node.id, "store-or-delete")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            assert protected.isdisjoint(node.names), (path, node.names, "global-mutation")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in hazardous_calls, (
                path,
                node.func.id,
                "dynamic-mutation",
            )
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            targets = getattr(node, "targets", (getattr(node, "target", None),))
            for target in targets:
                if target is not None:
                    assert root_name(target) not in protected, (
                        path,
                        root_name(target),
                        "protected-target",
                    )
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
        ):
            assert root_name(node.value) not in protected, (
                path,
                root_name(node.value),
                "protected-dict-mutation",
            )

for path in FILES:
    old = subprocess.check_output(["git", "show", f"{ORACLE}:{path}"], text=True)
    new = Path(path).read_text()
    assert_protected(path, old, new)

    protected_name = next(iter(protected_bindings(ast.parse(old))))
    mutants = {
        "import-alias": new + f"\nfrom builtins import object as {protected_name}\n",
        "delete": new + f"\ndel {protected_name}\n",
        "globals": new + f"\nglobals()[{protected_name!r}] = object()\n",
        "helper-global": new
        + f"\ndef _mutate_protected():\n    global {protected_name}\n    {protected_name} = object\n",
        "setattr": new + f"\nsetattr({protected_name}, 'mutated', True)\n",
        "aliased-setattr": new
        + "\nfrom builtins import setattr as mutate\n"
        + f"_mutation_result = mutate({protected_name}, 'mutated', True)\n",
        "attribute-setattr": new
        + f"\n_mutation_result = object.__setattr__({protected_name}, 'mutated', True)\n",
    }
    for mutant_name, mutant in mutants.items():
        try:
            assert_protected(path, old, mutant)
        except AssertionError:
            continue
        raise AssertionError((path, mutant_name, "mutant-survived"))
print("protected-v1: 41 definitions unchanged")
PY

uv run pytest tests/component/core/test_request_understanding_contract.py tests/component/core/test_task_state_contract.py tests/component/core/test_request_processing.py -q

test -z "$(rg -l 'RequestUnderstandingOutputV2|RequestUnderstandingRecordV2|build_request_understanding_closure_v2' src/mini_agent/application src/mini_agent/infrastructure src/mini_agent/evaluation evals tests/integration || true)"

uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
docker compose exec -T db sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose --profile test exec -T db-test sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
uv run alembic upgrade head
uv run pytest

rg -n 'RequestUnderstanding(Output|Record)V2|Durable(Input|ResolvedReference)CandidateV2|CandidateRejectionReasonCode|build_request_understanding_closure_v2|e2e01-thin-v2|request_understanding_record\\.p0\\.v2' \
  AGENTS.md README.md PROJECT_DIRECTION.md docs .planning src tests evals \
  --glob '!graphify-out/**'
test -z "$(git status --short --untracked-files=all)"
```

Feature exact-head handoff后，Integrator必须：

1. 取得independent canonical/ownership/security/test review；
2. 在不改写feature lineage的独立overlay Worktree把feature head应用到latest `integration/e2e01-thin`，重跑protected/focused/full门禁并再次review exact overlay head；
3. 使用项目PR template发布feature → integration draft PR，关闭全部actionable conversation；
4. 只在两次review与全部checks通过后ready并serial merge；
5. 从official remote integration ref捕获exact merge SHA作为`B_F`。planning merge、feature head或本地overlay均不能替代`B_F`。

共享PostgreSQL服务只按narrow命令启动/保持；未获明确teardown ownership不得执行`down`、`down -v`、prune、volume/data删除或影响其他任务。
</verification>

<success_criteria>

1. 显式v2 output/contextualization/provenance/durable record/child与封闭failure sets逐项匹配`p0-ru-v2-cutover-r1`，没有版本alias、fallback、inference或raw quote持久化。
2. pure builder只从trusted caller加载的authoritative message projection派生safe span/hash，local closure对zero/all/partial/multi与Task version chain全部fail closed。
3. 41个v1 top-level definitions的AST/source、现有v1 tests和active consumer imports全部不变；F没有active routing。
4. 两个有序atomic commits、六文件containment、focused/full/database、cross-file scan、feature/overlay exact-head reviews全部有可复现证据。
5. reviewed serial merge后形成exact `B_F`，才允许从该SHA签发01-07E；不推进Case、Requirement、Phase或产品完成状态。

</success_criteria>

<output>
完成后不创建Summary或修改共享planning/status。Executor只按`handoff_format`交接；Integrator reviewed merge后记录exact `B_F`并串行启动01-07E。
</output>
