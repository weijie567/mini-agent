---
phase: 01-cycle-1-e2e-01
plan: 07E
type: tdd
wave: 20
depends_on:
  - 01-07F
files_modified:
  - src/mini_agent/application/persistence.py
  - tests/component/application/test_persistence_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "01-07E 只执行 CODEC_EXPAND：增加 immutable exact code-version catalog、两个显式 exact-version API，以及 Request Understanding v2 的纯 codec projection / local-closure validation；当前 registry、legacy API、active consumers 与路由逐项保持不变。"
    - "P0_RECORD_SCHEMA_VERSION_CATALOG 恰含 18 个 exact (record_code, schema_version) entry；17 个 P0RecordCode 全部保留现有 v1 entry，只有 request_understanding_record 额外拥有 request_understanding_record.p0.v2。"
    - "encode_persistence_record_versioned 与 decode_persistence_record_versioned 强制 caller 同时显式提供 code/version；不接受 alias、inference、union、default/latest、try-other-version、read-time rewrite、backfill 或 reconstruction。"
    - "Request Understanding v2 entry 直接绑定 RequestUnderstandingRecordV2 / AcceptedTaskDeltaV2，使用 request_understanding_record_id identity、exact v2 top-level/child relation projection，并按 persisted candidate emitted order复验完整 local closure。"
    - "Codec 是 deterministic zero-I/O structural gate；它不读取 authoritative Message、不复验 provenance content、不证明 owner graph、business fact、authorization、PostgreSQL support、active routing 或 readiness。"
    - "src/mini_agent/application/persistence.py 在 exact B_F 中的全部 60 个 pre-existing top-level definition source segment 与 AST 均不变、不重绑、不 monkeypatch；allow_changed_existing_symbols=[]。"
    - "本 Packet 不修改 Core、Application records/ports/use case、Provider、Runtime、Infrastructure、PostgreSQL、migration、Eval、Composition Root、active canonical 文档、生命周期或任何现有 consumer。"
  artifacts:
    - "Application persistence source 中的 immutable 18-pair catalog、RU v2 private schema/projection/child binding，以及两个 fixed versioned APIs。"
    - "owned Component test 中的 RED/GREEN catalog、exact dispatch、v2 closure/tamper、legacy parity、protected-v1 与 no-active-routing 证据。"
  key_links:
    - "Thin Slice §10.1.1–10.1.4 exact persistence/version/projection/closure contract → 01-07E additive Application codec implementation。"
    - "01-07O p0-ru-v2-execution-map-r1：exact B_F → 01-07E → reviewed B_FE_EXPAND；01-07I/P 只能从 B_FE_EXPAND 启动。"
---

# Phase 1 Plan 01-07E｜Request Understanding v2 Application persistence codec expand

> **ISSUED CODEC_EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只增加 non-routable exact-version codec surface。任何测试通过都不表示 active registry、legacy codec API、PostgreSQL、Runtime、Provider、Eval、strict owner-scoped reader、Trajectory / E2E Result 或产品 readiness 已切换或完成。

> **DERIVED / NON_NORMATIVE**
> 持久化语义由 Thin Slice scoped owner 与 Memory owner拥有，Request Understanding durable closure由 Intent owner拥有，执行顺序由 `P0-RU-V2-EXECUTION-MAP` 拥有。本 Plan 只把这些现行约束映射为一个精确、可回滚的 Application Task Packet，不反向覆盖 owner。

<objective>
以 TDD RED→GREEN 在 Application persistence codec 尾部追加 immutable 18-pair exact-version catalog、两个 fixed versioned API，以及 Request Understanding v2 的 strict source/child projection与local closure复验，同时 byte/AST保护全部现有v1 top-level definitions和legacy behavior。

Purpose: 形成 reviewed exact `B_FE_EXPAND`，让后续 01-07I / 01-07P 可以从同一个 non-routable additive barrier 分别处理 physical schema / strict reader / Application Port 与 Provider / Eval dependency expand。

Output: 一个 test-only RED commit与一个 additive source GREEN commit；若review发现问题，只追加allowlist内fix commit。不得创建Summary，不得修改共享State。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07F-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07O-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/persistence.py
@src/mini_agent/core/task_state.py
@tests/component/application/test_persistence_contract.py

只使用受控 execution adapter；不得调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。Graphify按用户指令暂停：本Packet不读取、不运行、不更新，也不把它作为gate。
</execution_context>

<interfaces>

## 1. Immutable exact pair catalog

`src/mini_agent/application/persistence.py` 只能在全部既有definitions之后追加独立import/new definitions；不编辑既有import block或任一既有definition。

新增public catalog：

```python
P0_RECORD_SCHEMA_VERSION_CATALOG: Mapping[
    tuple[P0RecordCode, str],
    P0RecordSchemaSpec,
]
```

行为冻结如下：

- 使用 `MappingProxyType` 或等价 immutable mapping；不暴露underlying mutable dict。
- key恰为`(P0RecordCode, exact record_schema_version)`；恰含18项、17种code。
- 17个v1 pair的value直接复用`P0_PERSISTENCE_REGISTRY`中同code的exact frozen spec object，不复制第二套v1语义。
- 唯一新增pair是`(P0RecordCode.REQUEST_UNDERSTANDING_RECORD, "request_understanding_record.p0.v2")`。
- v2 spec直接绑定`RequestUnderstandingRecordV2`，identity fields恰为`("request_understanding_record_id",)`，version mirror恰为`schema_version`，允许唯一child code`accepted_task_delta`。
- Catalog不是active registry，不提供`register()`、dynamic import、string class name、latest/default selector、iteration-order contract或runtime extension。
- `P0_PERSISTENCE_REGISTRY`继续恰含17个active v1 code→spec entry；其中RU仍绑定`RequestUnderstandingRecord`、identity`run_id`、version`request_understanding_record.p0.v1`。
- `P0_LOGICAL_CHILD_SPECS`继续恰含3项；active accepted child仍绑定v1 `AcceptedTaskDelta`。v2 child binding必须由新增private exact-version structure拥有，不能替换该active mapping。

Catalog value的public exact container representation不是canonical owner额外承诺；本Plan只冻结上述Mapping contract、exact key set、direct source-model binding与observable行为。

## 2. Fixed exact-version APIs

新增签名必须逐字等价于：

```python
def encode_persistence_record_versioned(
    record_code: P0RecordCode,
    schema_version: str,
    record: ContractModel,
    *,
    external_references: tuple[P0RecordReference, ...] = (),
    logical_children: tuple[ContractModel, ...] = (),
) -> P0PersistenceEnvelope: ...

def decode_persistence_record_versioned(
    envelope: P0PersistenceEnvelope | Mapping[str, object] | str | bytes,
    *,
    expected_record_code: P0RecordCode,
    expected_schema_version: str,
    correlation_ref: UUID,
) -> DecodedP0PersistenceRecord: ...
```

两个入口必须：

1. 要求caller显式提供exact code与version；`schema_version` / `expected_schema_version`无default。
2. 在处理source model或payload前先做exact pair lookup；pair不存在只产生既有bounded integrity category。
3. 不从record、outer/inner payload、model input/output version、Task state version、active registry或当前默认值推断expected pair。
4. 不在pair miss或validation failure后尝试另一个版本；不做alias、union、default/latest、read-time rewrite、backfill或reconstruction。
5. outer envelope、inner `P0VersionedPayload`、selected spec与source mirror四者exact一致；code/version missing、unknown、expected mismatch、outer/inner mismatch分别使用现有适用`P0PersistenceIntegrityCategory`。
6. source record与logical child使用exact runtime type并经`model_validate_json(..., strict=True)`重建；拒绝subclass、dict替代、undeclared/private/trusted state、serializer warning/error和`model_construct`绕过形成的非法对象。
7. decode只接受现有四种approved input：exact `P0PersistenceEnvelope`、native JSON mapping、`str`、`bytes`；继续禁止Python UUID/datetime coercion、`default=str`和partial return。
8. `P0PersistenceIntegrityError`、`args`、`str`、`repr`与exception chain只保留bounded category和opaque correlation ref，不持有raw payload、quote、PII、Token、Prompt、Cookie、secret或资源存在性。

对17个v1 exact pair，versioned API可以在exact catalog selection后复用legacy pure helpers或legacy public behavior，但不得把active registry当pair lookup fallback。其envelope、decoded source/children、category与legacy语义保持一致。

## 3. Request Understanding v2 top-level projection

RU v2 selected spec的projection恰含以下8条：

| source field | classification | relation / target | rule |
|---|---|---|---|
| `run_id` | `TOP_LEVEL_P0_REFERENCE` | `run_id -> agent_run_record` | exactly one |
| `message_ref` | `TOP_LEVEL_P0_REFERENCE` | `message_ref -> message_record` | exactly one |
| `contextualization.resolved_reference_candidates[].source_ref` | `TOP_LEVEL_P0_REFERENCE` | `contextualization_resolved_source_ref -> message_record` | zero or more；最终reference tuple按key去重 |
| `contextualization.source_message_refs[]` | `TOP_LEVEL_P0_REFERENCE` | `contextualization_source_message_ref -> message_record` | one or more；source field unique；包含parent message |
| `task_delta_candidates[].input_candidates[].source_ref` | `TOP_LEVEL_P0_REFERENCE` | `task_delta_input_source_ref -> message_record` | zero or more；最终reference tuple按key去重 |
| `accepted_delta_refs[]` | `LOGICAL_CHILD_CORRELATION` | child `accepted_task_delta` | unique且与children exact set |
| `candidate_validation[].candidate_ref` | `PARENT_LOCAL_CORRELATION` | parent candidate IDs | exact set、每项一条final decision |
| `next_move_candidate_ref?` | `PAYLOAD_CORRELATION` | no top-level target | zero or one |

补充约束：

- top-level identity只使用`request_understanding_record_id`，不得回退到`run_id`。
- relation target logical identity继续复用现有active target specs；Message identity为`message_id`、AgentRun为`run_id`。
- 不为`model_input_schema_version`、`model_output_schema_version`、`proposed_base_task_state_version`或`validated_task_state_version`生成top-level relation。
- 同一个Message可能被多个candidate或多个projection path引用。各source collection自身的unique规则仍严格验证；汇总到envelope后的相同`(relation,target code,target identity)`可以且必须确定性collapse，最终reference tuple按既有reference key排序。
- Codec不读取Message、不检查span bounds对应哪条Message、不重算`source_quote_sha256`；它只严格验证safe DTO结构。provenance content verification留给后续owner-scoped reader。

## 4. Request Understanding v2 accepted child and local closure

新增private version-specific child spec直接绑定`AcceptedTaskDeltaV2`：

- child code：`accepted_task_delta`
- parent exact pair：`request_understanding_record` + `request_understanding_record.p0.v2`
- identity：`accepted_delta_id`
- closure：`LOCAL_CLOSED`
- projection恰含4条：

| source field | classification | relation / target |
|---|---|---|
| `candidate_ref` | `PARENT_LOCAL_CORRELATION` | parent ACCEPT candidate |
| `message_ref` | `PARENT_FIELD_EQUALITY` | parent message |
| `input_binding_refs[]` | `CHILD_TOP_LEVEL_P0_REFERENCE` | `input_binding_ref -> input_binding_record` |
| `task_id` | `CHILD_TOP_LEVEL_P0_REFERENCE` | `accepted_delta_task_id -> task_record` |

Encode与decode都必须重新验证完整local closure，不能只信任F producer或Pydantic parent validator：

- `task_delta_candidates[].candidate_id` unique且emitted order原样保留。
- `candidate_validation[].candidate_ref` unique并与candidate IDs exact set；每个candidate恰一条final decision。
- `ACCEPT`无reason且恰一child；`REJECT`有封闭reason且无child/Task effect。
- `accepted_delta_refs` unique，并与accepted child IDs、ACCEPT candidate refs形成exact closure；refs表示顺序无关集合。
- child `candidate_ref`唯一命中对应emitted candidate，`operation`与candidate相同，`message_ref == parent.message_ref`，`accepted_at == parent.created_at`。
- child `input_binding_refs` unique；`accepted_delta_id` unique；`(accepted_delta_id, task_id)` unique。
- Task chain只能按parent persisted candidate emitted sequence过滤ACCEPT后计算，绝不按UUID、accepted refs或logical-child storage order推断。
- 每个Task第一项若base为`None`，result必须为正整数；若base为正整数，result必须恰为`base + 1`。后续每项base必须等于前一result且result必须恰为`base + 1`。这只是pure codec可证明的structural chain，不证明first base确为owner实际加载版本。
- 拒绝duplicate base、parallel fork、gap、rollback、reordered candidate replay、missing/extra/duplicate/dangling/wrong-parent/wrong-identity/wrong-time/wrong-operation child。
- zero-candidate、all-reject、partial-accept、multi-accept均可完整闭合。
- logical child payload可以按child identity确定性排序用于canonical storage；该排序不改变、也不能替代candidate emitted order语义。

任一局部不一致整体失败，不返回partial envelope或decoded record。适用category使用既有`CHILD_MISMATCH`、`LINK_*`、`PAYLOAD_VALIDATION_FAILED`等封闭集合；不得增加新enum或caller-controlled error text。

## 5. Legacy protected surface and nonclaims

下列内容保持exact：

- 全部60个pre-existing top-level definitions的source segment与AST。
- `P0_PERSISTENCE_REGISTRY` 17项active v1 mapping及object identity。
- `_TOP_LEVEL_PROJECTIONS`、`_CHILD_PROJECTIONS`、`P0_LOGICAL_CHILD_SPECS`及legacy registry派生行为。
- `encode_persistence_record` / `decode_persistence_record`签名、17-record strict JSON round-trip、error taxonomy与active consumer行为。
- legacy encode拒绝`RequestUnderstandingRecordV2`；legacy decode拒绝v2 envelope。

`B_FE_EXPAND`仍明确不声称：

- active registry switched；
- legacy codec API changed；
- PostgreSQL routed to v2；
- Runtime / Provider / Eval routed to v2；
- v1 contract removed；
- strict owner-scoped reader / provenance content verified；
- owner graph / business fact / authorization proven；
- readiness、Trajectory / E2E Result或P0产品完成。
</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-codec-expand`
base_branch: `integration/e2e01-thin`
base_sha: `034cf57228c4a9da4764b0c7322dc5d34652a09c`
base_tree: `c62d660213d8c74f922a7832ed778f3ac6f3b104`
input_barrier: `B_F`
output_barrier: `B_FE_EXPAND`
worktree_id: `e2e01-01-ru-v2-codec-expand`
writer: `Application persistence codec sole writer with owned test, supervised by /root Integrator`
agent_role: `runtime-engineer`
active_routing: `false`

物理Worktree path只在private dispatch handoff中传递，不写入commit或PR。

canonical_inputs:

- `AGENTS.md` at B_F：blob `e4742ea091b963e6ff77508d43c8d1c9863f69c1`；项目范围、安全、验证、Worktree/PR与Graphify暂停规则。
- `.planning/GOVERNANCE.md` at B_F：blob `bd5c92a7e5369cbeb1d152caa3eed736938e94c4`；Task Packet hard gate、controlled planning adapter、role availability、containment与serial integration。
- `docs/architecture/intent-design-reference.md`：commit `327b39da45cdcf564609a5385d52c4264da2c669`、blob `456be9c7d7884e2a58c4d07b867765ed336aa6f5`；§13 durable identity/projection/exact-set/keyed Task effect。
- `docs/architecture/memory-design-reference.md`：commit `be68490b9d8440a29a43fa8143e9dd5d4bcbfeda`、blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`；exact-version、integrity、owner-scoped reader与zero-I/O codec边界。
- `docs/implementation/e2e01-thin-slice-implementation-spec.md`：commit `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`、blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`；§10.1.1–10.1.4与唯一`P0-RU-V2-CUTOVER-MANIFEST` marker，`manifest_version`必须为`p0-ru-v2-cutover-r1`。
- `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`：commit `4ed68875fdf2330b6947b7f85235cec388d2af14`、blob `d248fc670659eb37bce89d97c7f9f883b69373e7`；唯一`P0-RU-V2-EXECUTION-MAP` marker，`manifest_version`必须为`p0-ru-v2-execution-map-r1`。
- `.planning/phases/01-cycle-1-e2e-01/01-07O-PLAN.md`：commit `274178bad8796e08831dcd9204b6610c19930982`、blob `ef63e5a79b61622e3b495d3ba8d49801e3054cbe`；E的exact branch/worktree/writer/allowlist与`B_F → B_FE_EXPAND` mapping。
- `.planning/phases/01-cycle-1-e2e-01/01-07F-PLAN.md`：merge commit `112d643ec12aa1556c3794874e8cc450f9a8b36b`、blob `d0630bfb9bebd43efbe5c1d8f110ef5dcc897ae1`；F direct-binding与E handoff nonclaims。
- B_F Core v2 source blobs：`request_understanding.py=018ea446517c099cc061de6e99afe55db10e8afb`、`task_state.py=122b62b7a68ae0b92adfb3208ef9845fdd646fbe`、`request_processing.py=261c6318e60756d57d4d15bfcf62b5c2da236760`；E只读消费，不修改。
- B_F owned source/test blobs：`persistence.py=c90105ce6b934763f8deb4c9ae981bcf4f38c0b3`、`test_persistence_contract.py=4284751d2428cbef725611ea07a48b55c87af898`。

planning_and_owner_provenance:

- Intent owner current commit `327b39da45cdcf564609a5385d52c4264da2c669`，blob `456be9c7d7884e2a58c4d07b867765ed336aa6f5`
- Memory owner current commit `be68490b9d8440a29a43fa8143e9dd5d4bcbfeda`，blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- Thin Slice exact encoding commit `a4b1edb4c50a2e3e826571194bac58f7b31eab6d`，blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- Multi-agent execution view commit `4ed68875fdf2330b6947b7f85235cec388d2af14`，blob `d248fc670659eb37bce89d97c7f9f883b69373e7`
- 01-07O Plan commit `274178bad8796e08831dcd9204b6610c19930982`，blob `ef63e5a79b61622e3b495d3ba8d49801e3054cbe`
- 01-07F Plan merge commit `112d643ec12aa1556c3794874e8cc450f9a8b36b`，blob `d0630bfb9bebd43efbe5c1d8f110ef5dcc897ae1`
- reviewed 01-07F feature merge / exact `B_F` `034cf57228c4a9da4764b0c7322dc5d34652a09c`
- 本Plan的official planning merge SHA/blob由Integrator在Plan PR reviewed merge后从official integration ref捕获；planning merge不替换feature execution base `B_F`

owned_files_at_base:

- `src/mini_agent/application/persistence.py` = `c90105ce6b934763f8deb4c9ae981bcf4f38c0b3`
- `tests/component/application/test_persistence_contract.py` = `4284751d2428cbef725611ea07a48b55c87af898`

protected_v1_surface:

- mode: `all-preexisting-top-level-definitions`
- oracle_sha: `034cf57228c4a9da4764b0c7322dc5d34652a09c`
- file: `src/mini_agent/application/persistence.py`
- oracle_blob: `c90105ce6b934763f8deb4c9ae981bcf4f38c0b3`
- allow_changed_existing_symbols: `[]`
- definition count: `60`
- 对每个oracle symbol同时比较`ast.dump(include_attributes=False)`、exact source segment SHA-256和唯一module binding；candidate必须仍恰好一个同名definition/binding。
- 新增AST只允许在完整oracle module prefix之后出现独立`Import`/`ImportFrom`、new-name alias/constant、undecorated class/function definition及其正常内部body；不得编辑、删除、装饰、移动或复制existing definition。
- tail不得对任一protected name执行Assign/AnnAssign/AugAssign/Delete/NamedExpr、`global`/`nonlocal`、attribute mutation、`setattr`/`delattr`、`globals`/`vars`/`exec`/`eval`、monkeypatch或alias-mediated mutation。
- gate内置import alias、direct/aliased setattr、object.__setattr__、globals assignment、del、helper/global和duplicate binding mutants；每个mutant必须被拒绝。

adapter_precheck:

- required_role: `runtime-engineer`
- availability_source: `current Codex collaboration runtime spawn-agent role registry`
- issued_result: `CONFIRMED AVAILABLE`
- dispatch_rule: Integrator在feature首次写入前必须重新确认exact role仍真实可用并记录结果；SDK/local agent-file探测不能替代该检查。缺失或无法确认时`BLOCK`，不得用默认角色静默替代。

owned_files:

- `src/mini_agent/application/persistence.py`
- `tests/component/application/test_persistence_contract.py`

forbidden_files:

- every repository path outside the two exact owned files
- especially `AGENTS.md`、`README.md`、`PROJECT_DIRECTION.md`、`docs/**`、`.planning/**`、`src/mini_agent/core/**`、`src/mini_agent/application/records.py`、`src/mini_agent/application/ports.py`、Application use cases / composition、`src/mini_agent/runtime/**`、`src/mini_agent/infrastructure/**`、`src/mini_agent/evaluation/**`、other `tests/**`、`evals/**`、`alembic/**`、`pyproject.toml`、`uv.lock`、`compose.yaml`、`graphify-out/**`
- any modification/removal/rebinding/monkeypatch of the 60 protected definitions
- active registry switch、legacy API change、Port/consumer wiring、physical schema、migration/backfill/fallback、v1 retirement、lifecycle/readiness claim

dependencies:

- 首次编辑前必须证明branch、clean status、`HEAD == B_F`、tree、merge-base与两个owned blob精确匹配。
- official planning merge必须存在且其两个owned blobs仍等于B_F；Plan merge只提供provenance，不改变feature lineage。
- `P0-RU-V2-CUTOVER-MANIFEST`仍为`p0-ru-v2-cutover-r1`；`P0-RU-V2-EXECUTION-MAP`仍为`p0-ru-v2-execution-map-r1`且E的input/output barrier、branch、worktree、allowlist、protected surface与本Packet完全一致。
- B_F中的`RequestUnderstandingRecordV2`、`AcceptedTaskDeltaV2`及nested durable DTO definitions必须exact存在；01-07E不得修改它们。
- 01-07I/P及全部downstream在01-07E feature exact-head review、latest-integration replay、serial merge与post-merge gate共同形成`B_FE_EXPAND`前保持`BLOCK`。

required_checks:

- catalog immutable、18 exact pairs、17 codes、仅RU dual、17个v1 spec object identity复用、v2 source/identity/version/child exact binding。
- exact public signatures；missing/None/empty/unknown/cross-code version不推断、不fallback。
- 17个v1 pair的versioned encode/decode与legacy semantic parity；现有17-record suite原断言全绿。
- RU v2 zero/all-reject/partial/multi正向round-trip，identity、outer/inner/source mirror、exact decoded types与stable child representation。
- RU v2 exact top-level/child relation tokens、targets、identity fields、deterministic sort、合法duplicate collapse与非法source duplicate rejection。
- v1 source+v2 pair、v2 source+v1 pair、v1 envelope expected v2、v2 envelope expected v1、unknown future、outer/inner/source mirror tamper全部bounded fail closed且不尝试另一版本。
- exact runtime model、subclass/dict、`model_construct`、nested wrong type、undeclared/trusted/private/raw quote、serializer warning/error均拒绝。
- candidate/decision/accepted exact set，missing/extra/duplicate/dangling/wrong-candidate/message/time/operation/binding/pair child，以及per-Task fork/gap/rollback/reordered replay矩阵。
- safe span/hash结构正负矩阵；codec执行期间无Message resolver、Repository、DB、network、identity lookup或provenance content recomputation。
- 60-symbol AST/source/no-rebinding gate与mutation suite全绿。
- legacy `_TOP_LEVEL_PROJECTIONS`、`_CHILD_PROJECTIONS`与reference-producing rule count分别保持`66 / 7 / 45`；v2 private projection另为exact `8 / 4`，不得改写legacy matrices。
- repo consumer scan证明三个新public symbols只出现在owned source/test；没有Application consumer、Infra、Runtime、Provider、Eval、Composition Root或integration-test调用。
- 仓库没有canonical lint、type-check或build命令；不得编造。执行project canonical dependency/database/migration/full-test门禁并如实报告。
- 任一preflight、RED reason、focused/full test、protected-v1、allowlist、consumer scan、review或clean-status失败均`BLOCK`。

cross_file_impact:

- canonical owners与execution map已授权E additive stage；E不修改owner正文。
- 01-07F Core已在B_F reviewed merge；E只消费其public v2 DTO，不反向修改Core contract。
- `B_FE_EXPAND`本身就是F/E共同barrier。`.planning/PROJECT.md`、`REQUIREMENTS.md`、`ROADMAP.md`、`STATE.md`、Validation与Summary可在其后由独立single-writer做派生状态对齐，但该对齐不创建第二道barrier、不改变execution map，也不阻塞01-07I/P。
- 01-07I/P只阻塞到reviewed serial merge形成exact`B_FE_EXPAND`；K/L、M、Q、J、S/U、X、T、W、V继续服从execution map各自downstream barrier。本Packet不声称repository-wide aligned。

commit_protocol:

1. RED commit `test(01-07E): define request understanding v2 codec contract` 只改owned test文件；source blob仍等于B_F。focused command必须因缺少catalog/versioned APIs或新contract assertion失败，不得因syntax、fixture、错误路径或环境失败。
2. GREEN commit `feat(01-07E): add request understanding v2 codec expand` 只改owned source文件；不得重写RED commit。focused、protected-v1、consumer scan、canonical database/full-suite与scope gate全部通过。
3. 正常feature history相对B_F恰为以上两个提交。Review finding先阻止ready；修复只在两文件allowlist内追加`fix(01-07E): ...` commit，对新exact head重新运行完整review与门禁，不得amend/rebase/force-push已审历史。

done_when:

- RED/GREEN commit顺序、failure reason、SHA和输出可复现；changed-file union恰为两文件。
- catalog/API/RU v2 projection/closure满足owner contract；60个v1 definitions与active behavior不变。
- focused、full suite、exact scope、consumer scan、cross-file impact scan与clean status全部通过。
- feature exact head与latest-integration overlay exact head均取得独立review，unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`。
- draft PR精确使用feature head → `integration/e2e01-thin`；reviewed serial merge后才记录`B_FE_EXPAND`，不推进Case/Requirement/Phase lifecycle。

contract_changes: `YES / ADDITIVE CODEC_EXPAND ONLY` — 增加immutable 18-entry exact code-version catalog、两个fixed versioned codec API，以及RU v2 exact source/child/projection/local-closure handling；保持legacy registry/API/consumers/routing。无alias、inference、fallback、migration、physical schema、active switch或v1 retirement。
security_impact: `YES` — 防止version confusion、source-model substitution、raw/private/trusted field持久化、dangling child/Task effect与unsafe error disclosure。Codec保持deterministic zero-I/O，不授予owner/provenance/business authority。
eval_impact: `YES / COMPONENT CONTRACT ONLY` — owned Component test增加catalog、exact dispatch、strict RU v2 round-trip、closure、tamper与legacy non-regression；不改Dataset、Grader、Result、threshold、Case/requirement lifecycle、Trajectory或E2E状态。
new_dependencies: `NONE`
graphify_disposition: `DISABLED_BY_USER / NOT_RUN / NOT_A_GATE`
rollback: 合并前关闭PR；合并后普通revert PR按feature range严格逆序撤销全部01-07E feature/fix commits，重新阻塞`B_FE_EXPAND`及I/P→K/L→M→Q→J→S/U→X→T→W→V。不得reset、force-push、data/schema rollback、fallback、backfill、readiness或lifecycle claim。

handoff_to: `/root Integrator`
handoff_format: branch、exact base/planning/head/commits/tree、owner/Plan与两个base/head blobs、RED/GREEN输出、60-symbol AST/source结果、catalog key dump、focused/database/migration/full-suite结果、changed files/commit containment、consumer/cross-file scan、contract/security/Eval nonclaims、feature/overlay review、风险、`B_FE_EXPAND` merge SHA与rollback。
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUC-S01` | Spoofing | caller/payload → code/version/source model/owner authority | `MITIGATE / BLOCK` | caller显式exact pair、direct source type、no inference/fallback；codec success不授予owner scope |
| `RUC-T01` | Tampering | outer/inner/source/child → decoded closure | `MITIGATE / BLOCK` | four-way version consistency、strict JSON rebuild、exact relation projection、candidate/decision/child/Task-chain closure |
| `RUC-R01` | Repudiation | RED/GREEN/review → evidence | `MITIGATE / BLOCK` | 两个有序atomic commits、base/owner blobs、60-symbol snapshot、full output、exact-head independent review |
| `RUC-I01` | Information Disclosure | raw quote/private payload → durable/error/consumer | `MITIGATE / BLOCK` | safe DTO strict validation、undeclared-state rejection、bounded error、no active consumer、raw marker negative tests |
| `RUC-D01` | Denial of Service | malformed JSON/graph/version confusion → codec | `MITIGATE / BOUNDED` | native JSON gate、bounded cardinality、no I/O/retry/recursive fallback、stable category |
| `RUC-E01` | Elevation of Privilege | codec decode → provenance/owner/business/readiness | `MITIGATE / BLOCK` | PURE_CODEC zero-I/O nonclaim、dependency/active-switch独立barrier与consumer absence scan |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze exact catalog/API, RU v2 closure and protected-v1 matrices</name>
  <files>tests/component/application/test_persistence_contract.py</files>
  <read_first>Thin Slice §10.1.1–10.1.4、Intent §13、Memory §15.2、01-07O execution map、01-07F direct v2 DTO、两个B_F owned blobs与60-symbol oracle</read_first>
  <behavior>
    - immutable 18-pair catalog、17-code/only-RU-dual、v1 spec identity与v2 direct binding。
    - exact signatures、17 v1 parity、RU v2 identity/projection/child/closure/JSON forms。
    - version confusion、source/child tamper、raw/private/undeclared state、bounded error和no fallback。
    - 60个v1 definitions与legacy 17-record behavior不变；无active consumer。
  </behavior>
  <action>只改owned test文件。复用现有`_record_cases()`覆盖17个v1 pair，追加RU v2 fixture与zero/all/partial/multi closure正负矩阵；不修改已有断言，不使用skip/xfail/conditional pass。运行focused command取得真实RED，确认失败只因01-07E public surface尚不存在，然后提交精确RED message。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated>
    RED必须非零退出且失败原因是缺少01-07E catalog/API；source blob、其他test、Core/Infra/Eval/owner文件仍等于base。
  </verify>
  <acceptance_criteria>test文件覆盖must_haves/required_checks；RED commit只含该test文件；无模型、网络、数据库或Graphify依赖。</acceptance_criteria>
  <done>行为先于实现固定，RED原因正确且可复现。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — append isolated exact-version catalog and RU v2 codec path</name>
  <files>src/mini_agent/application/persistence.py</files>
  <read_first>Task 1 RED commit/output、interfaces、60-symbol oracle、existing strict JSON/reference/error patterns与B_F v2 Core DTO</read_first>
  <behavior>
    - 所有RED矩阵转绿；exact pair dispatch始终先于source/payload validation。
    - v1 pair保持legacy parity；v2形成完整safe envelope或bounded failure。
    - existing definitions、registry、legacy API、tests与active consumers保持不变。
  </behavior>
  <action>只在source文件完整existing module之后追加独立imports/new private/public definitions；实现catalog、version-specific RU v2 spec/child/projections、strict actual-state validation、encode/decode与local closure。禁止编辑/重绑existing symbol，禁止Application consumer/Infra/Eval wiring，禁止version fallback/alias/union。focused与mechanical gates转绿后提交精确GREEN message，再运行canonical dependency/database/migration/full-suite与review preflight。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_persistence_contract.py -q</automated>
    GREEN必须零退出；60-symbol gate、catalog dump、legacy parity、consumer absence、scope与full suite随后全部通过。
  </verify>
  <acceptance_criteria>source只做additive tail；catalog/API/closure满足interfaces；无I/O、migration、routing、owner/readiness claim。</acceptance_criteria>
  <done>形成可独立审查的exact feature head，不自行merge或推进lifecycle。</done>
</task>

</tasks>

<verification>

执行顺序不可省略。`B_F`是symbolic barrier名称，不是Git ref；所有Git命令只使用下列exact SHA。

### 1. 首次写入前的 exact preflight

Integrator先在当前Codex collaboration runtime重新确认`runtime-engineer`位于真实可用的specialized role registry，并把结果记录为`AVAILABLE`；缺失时立即`BLOCK`。随后在feature Worktree运行：

```bash
set -euo pipefail

base_sha=034cf57228c4a9da4764b0c7322dc5d34652a09c
base_tree=c62d660213d8c74f922a7832ed778f3ac6f3b104
expected_branch=codex/e2e01-01-ru-v2-codec-expand

test "$(git branch --show-current)" = "$expected_branch"
test "$(git rev-parse HEAD)" = "$base_sha"
test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test -z "$(git status --short --untracked-files=all)"

test "$(git rev-parse "${base_sha}:AGENTS.md")" = e4742ea091b963e6ff77508d43c8d1c9863f69c1
test "$(git rev-parse "${base_sha}:.planning/GOVERNANCE.md")" = bd5c92a7e5369cbeb1d152caa3eed736938e94c4
test "$(git rev-parse "${base_sha}:docs/architecture/intent-design-reference.md")" = 456be9c7d7884e2a58c4d07b867765ed336aa6f5
test "$(git rev-parse "${base_sha}:docs/architecture/memory-design-reference.md")" = 5c27ba3bd2ed74e5164bdd0812133041ed96f242
test "$(git rev-parse "${base_sha}:docs/implementation/e2e01-thin-slice-implementation-spec.md")" = 233a9c06ef6ef9300bef1a0e4f86659b0ec26a13
test "$(git rev-parse "${base_sha}:docs/implementation/e2e01-thin-slice-multi-agent-plan.md")" = d248fc670659eb37bce89d97c7f9f883b69373e7
test "$(git rev-parse "${base_sha}:.planning/phases/01-cycle-1-e2e-01/01-07O-PLAN.md")" = ef63e5a79b61622e3b495d3ba8d49801e3054cbe
test "$(git rev-parse "${base_sha}:.planning/phases/01-cycle-1-e2e-01/01-07F-PLAN.md")" = d0630bfb9bebd43efbe5c1d8f110ef5dcc897ae1
test "$(git rev-parse "${base_sha}:src/mini_agent/core/request_understanding.py")" = 018ea446517c099cc061de6e99afe55db10e8afb
test "$(git rev-parse "${base_sha}:src/mini_agent/core/task_state.py")" = 122b62b7a68ae0b92adfb3208ef9845fdd646fbe
test "$(git rev-parse "${base_sha}:src/mini_agent/core/request_processing.py")" = 261c6318e60756d57d4d15bfcf62b5c2da236760
test "$(git rev-parse "${base_sha}:src/mini_agent/application/persistence.py")" = c90105ce6b934763f8deb4c9ae981bcf4f38c0b3
test "$(git rev-parse "${base_sha}:tests/component/application/test_persistence_contract.py")" = 4284751d2428cbef725611ea07a48b55c87af898

test "$(git show "${base_sha}:docs/implementation/e2e01-thin-slice-implementation-spec.md" | rg -Fc '"manifest_version": "p0-ru-v2-cutover-r1"')" -eq 1
test "$(git show "${base_sha}:docs/implementation/e2e01-thin-slice-multi-agent-plan.md" | rg -Fc '"manifest_version": "p0-ru-v2-execution-map-r1"')" -eq 1
test -z "$(
  git grep -l -E \
    'P0_RECORD_SCHEMA_VERSION_CATALOG|encode_persistence_record_versioned|decode_persistence_record_versioned' \
    "$base_sha" -- src tests || true
)"

git fetch origin integration/e2e01-thin
planning_sha=$(git rev-parse origin/integration/e2e01-thin)
git merge-base --is-ancestor "$base_sha" "$planning_sha"
test "$(git rev-parse "${planning_sha}:src/mini_agent/application/persistence.py")" = c90105ce6b934763f8deb4c9ae981bcf4f38c0b3
test "$(git rev-parse "${planning_sha}:tests/component/application/test_persistence_contract.py")" = 4284751d2428cbef725611ea07a48b55c87af898
test "$(git cat-file -t "${planning_sha}:.planning/phases/01-cycle-1-e2e-01/01-07E-PLAN.md")" = blob
```

### 2. RED与final commit/scope containment

Task 1后保存focused RED command、exit code与缺symbol failure excerpt；证明RED commit只改test且source blob仍是`c90105...`。Task 2及所有review fix完成后运行：

```bash
set -euo pipefail

base_sha=034cf57228c4a9da4764b0c7322dc5d34652a09c
expected_files=$'src/mini_agent/application/persistence.py\ntests/component/application/test_persistence_contract.py'

test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git diff --name-only "${base_sha}...HEAD" | LC_ALL=C sort)" = "$expected_files"
git diff --check "${base_sha}...HEAD"
test "$(git rev-list --count "${base_sha}..HEAD")" -ge 2
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '1p')" = "test(01-07E): define request understanding v2 codec contract"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '2p')" = "feat(01-07E): add request understanding v2 codec expand"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '3,$p' | awk '!/^fix\\(01-07E\\): / {bad++} END {print bad+0}')" -eq 0

red_sha=$(git rev-list --reverse "${base_sha}..HEAD" | sed -n '1p')
green_sha=$(git rev-list --reverse "${base_sha}..HEAD" | sed -n '2p')
test "$(git diff-tree --no-commit-id --name-only -r "$red_sha" | LC_ALL=C sort)" = "tests/component/application/test_persistence_contract.py"
test "$(git diff-tree --no-commit-id --name-only -r "$green_sha" | LC_ALL=C sort)" = "src/mini_agent/application/persistence.py"
test -z "$(git status --short --untracked-files=all)"
```

### 3. Executable 60-symbol source/AST/no-rebinding oracle

```bash
set -euo pipefail
base_sha=034cf57228c4a9da4764b0c7322dc5d34652a09c

uv run python - "$base_sha" <<'PY'
import ast
import hashlib
import subprocess
import sys
from pathlib import Path

ORACLE = sys.argv[1]
PATH = "src/mini_agent/application/persistence.py"

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

def assert_protected(old, new):
    old_tree, new_tree = ast.parse(old), ast.parse(new)
    old_bindings = protected_bindings(old_tree)
    protected = set(old_bindings)
    assert len(protected) == 60, ("oracle-definition-count", len(protected))

    assert new.startswith(old), "existing-module-bytes"
    assert len(new_tree.body) >= len(old_tree.body), "module-body-shortened"
    for old_node, new_node in zip(old_tree.body, new_tree.body, strict=False):
        assert ast.dump(old_node, include_attributes=False) == ast.dump(
            new_node, include_attributes=False
        ), "module-prefix-ast"

    for name, old_nodes in old_bindings.items():
        assert len(old_nodes) == 1, (name, "oracle-count")
        old_node = old_nodes[0]
        new_node = new_tree.body[old_tree.body.index(old_node)]
        assert ast.dump(old_node, include_attributes=False) == ast.dump(
            new_node, include_attributes=False
        ), (name, "ast")
        old_segment = ast.get_source_segment(old, old_node)
        new_segment = ast.get_source_segment(new, new_node)
        assert old_segment is not None and new_segment is not None
        assert hashlib.sha256(old_segment.encode()).digest() == hashlib.sha256(
            new_segment.encode()
        ).digest(), (name, "source")

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
    occupied_names = set().union(*(node_bound_names(node) for node in old_tree.body))
    for node in tail:
        assert isinstance(node, allowed_tail), (type(node).__name__, "tail-node")
        new_names = node_bound_names(node)
        assert occupied_names.isdisjoint(new_names), (
            sorted(occupied_names.intersection(new_names)),
            "module-name-rebind",
        )
        occupied_names.update(new_names)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in protected, (node.name, "definition-rebind")
            assert not node.decorator_list, (node.name, "top-level-decorator")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                assert bound not in protected, (bound, "import-rebind")
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                assert bound not in protected, (bound, "import-from-rebind")
                assert alias.name not in {"setattr", "delattr", "globals", "vars", "exec", "eval"}, (
                    alias.name,
                    "hazardous-import",
                )
        elif isinstance(node, ast.Assign):
            assert all(isinstance(target, ast.Name) for target in node.targets), "non-name-assignment"
        elif isinstance(node, ast.AnnAssign):
            assert isinstance(node.target, ast.Name), "non-name-annassign"

    safe_module_load_calls = {
        "Field",
        "field_validator",
        "model_validator",
        "field_serializer",
        "MappingProxyType",
        "P0RecordSchemaSpec",
        "_P0LogicalChildSchemaSpec",
        "_decision",
        "_one",
        "_optional",
        "_many",
        "_nested_optional",
        "_nested_many",
        "_combined",
        "tuple",
    }
    module_load_calls = ModuleLoadCallCollector()
    for node in tail:
        module_load_calls.visit(node)
    for call in module_load_calls.calls:
        assert isinstance(call.func, ast.Name), (
            ast.dump(call.func, include_attributes=False),
            "module-load-attribute-call",
        )
        assert call.func.id in safe_module_load_calls, (
            call.func.id,
            "module-load-unsafe-call",
        )

    hazardous_calls = {
        "globals",
        "vars",
        "exec",
        "eval",
        "setattr",
        "delattr",
        "getattr",
        "__import__",
    }
    hazardous_attributes = {"setattr", "delattr", "__setattr__", "__delattr__"}

    def is_hazardous_callable_alias(value):
        if isinstance(value, ast.Name):
            return value.id in hazardous_calls
        if isinstance(value, ast.Attribute):
            return value.attr in hazardous_attributes
        return (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "getattr"
            and len(value.args) >= 2
            and isinstance(value.args[1], ast.Constant)
            and value.args[1].value in hazardous_attributes
        )

    for node in ast.walk(ast.Module(body=tail, type_ignores=[])):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            assert node.id not in protected, (node.id, "store-or-delete")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            assert node.id not in hazardous_calls, (
                node.id,
                "hazardous-name-load",
            )
        if isinstance(node, ast.Attribute):
            assert node.attr not in hazardous_attributes, (
                node.attr,
                "hazardous-attribute-access",
            )
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name not in hazardous_calls, (
                    alias.name,
                    "nested-hazardous-import",
                )
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            assert protected.isdisjoint(node.names), (node.names, "global-mutation")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in hazardous_calls, (
                    node.func.id,
                    "dynamic-mutation",
                )
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"__setattr__", "__delattr__"}, (
                    node.func.attr,
                    "attribute-mutation-call",
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            assert not is_hazardous_callable_alias(node.value), (
                ast.dump(node.value, include_attributes=False),
                "hazardous-callable-alias",
            )
        if isinstance(
            node,
            (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete, ast.NamedExpr),
        ):
            targets = getattr(node, "targets", (getattr(node, "target", None),))
            for target in targets:
                if target is not None:
                    assert root_name(target) not in protected, (
                        root_name(target),
                        "protected-target",
                    )
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
        ):
            assert root_name(node.value) not in protected, "protected-dict-mutation"

old = subprocess.check_output(["git", "show", f"{ORACLE}:{PATH}"], text=True)
new = Path(PATH).read_text()
assert_protected(old, new)

protected_name = next(iter(protected_bindings(ast.parse(old))))
mutants = {
    "import-alias": new + f"\nfrom builtins import object as {protected_name}\n",
    "duplicate-binding": new + f"\n{protected_name} = object\n",
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
    "nested-object-alias": new
    + "\ndef _probe_object_alias():\n"
    + "    mutate = object.__setattr__\n"
    + f"    mutate({protected_name}, 'mutated', True)\n",
    "nested-name-alias": new
    + "\ndef _probe_name_alias():\n"
    + "    mutate = setattr\n"
    + f"    mutate({protected_name}, 'mutated', True)\n",
    "nested-import-alias": new
    + "\ndef _probe_import_alias():\n"
    + "    from builtins import setattr as mutate\n"
    + f"    mutate({protected_name}, 'mutated', True)\n",
    "default-arg-alias": new
    + f"\ndef _probe_default_alias(mutate=object.__setattr__):\n"
    + f"    mutate({protected_name}, 'mutated', True)\n",
}
for mutant_name, mutant in mutants.items():
    try:
        assert_protected(old, mutant)
    except AssertionError:
        continue
    raise AssertionError((mutant_name, "mutant-survived"))
print("protected-v1: definitions=60 changed=0 rebound=0 mutants=12/12-rejected")
PY
```

### 4. Focused、catalog与consumer gates

```bash
set -euo pipefail

uv run pytest tests/component/application/test_persistence_contract.py -q

uv run python - <<'PY'
import inspect
from collections import Counter
from types import MappingProxyType

import mini_agent.application.persistence as p
from mini_agent.core.task_state import (
    AcceptedTaskDelta,
    RequestUnderstandingRecord,
    RequestUnderstandingRecordV2,
)

catalog = p.P0_RECORD_SCHEMA_VERSION_CATALOG
assert isinstance(catalog, MappingProxyType)
assert len(catalog) == 18
assert {code for code, _ in catalog} == set(p.P0RecordCode)
counts = Counter(code for code, _ in catalog)
assert counts[p.P0RecordCode.REQUEST_UNDERSTANDING_RECORD] == 2
assert all(
    count == (2 if code is p.P0RecordCode.REQUEST_UNDERSTANDING_RECORD else 1)
    for code, count in counts.items()
)
for code, spec in p.P0_PERSISTENCE_REGISTRY.items():
    assert catalog[(code, spec.record_schema_version)] is spec

v2 = catalog[
    (
        p.P0RecordCode.REQUEST_UNDERSTANDING_RECORD,
        "request_understanding_record.p0.v2",
    )
]
assert v2.source_model is RequestUnderstandingRecordV2
assert v2.identity_fields == ("request_understanding_record_id",)
assert v2.version_mirror_field == "schema_version"
assert v2.allowed_child_codes == (p.P0LogicalChildCode.ACCEPTED_TASK_DELTA,)

assert len(p.P0_PERSISTENCE_REGISTRY) == 17
assert (
    p.P0_PERSISTENCE_REGISTRY[
        p.P0RecordCode.REQUEST_UNDERSTANDING_RECORD
    ].source_model
    is RequestUnderstandingRecord
)
assert len(p.P0_LOGICAL_CHILD_SPECS) == 3
assert (
    p.P0_LOGICAL_CHILD_SPECS[
        p.P0LogicalChildCode.ACCEPTED_TASK_DELTA
    ].source_model
    is AcceptedTaskDelta
)

top = tuple(
    rule
    for spec in p.P0_PERSISTENCE_REGISTRY.values()
    for rule in spec.projection_decisions
)
children = tuple(
    rule
    for spec in p.P0_LOGICAL_CHILD_SPECS.values()
    for rule in spec.projection_decisions
)
reference_classes = {
    "TOP_LEVEL_P0_REFERENCE",
    "EXTERNAL_REQUIRED_P0_REFERENCE",
    "CHILD_TOP_LEVEL_P0_REFERENCE",
}
references = tuple(
    rule
    for rule in (*top, *children)
    if rule.classification.value in reference_classes
)
assert (len(top), len(children), len(references)) == (66, 7, 45)

encode_parameters = inspect.signature(
    p.encode_persistence_record_versioned
).parameters
assert tuple(encode_parameters) == (
    "record_code",
    "schema_version",
    "record",
    "external_references",
    "logical_children",
)
assert encode_parameters["schema_version"].default is inspect.Parameter.empty
assert encode_parameters["external_references"].kind is inspect.Parameter.KEYWORD_ONLY
assert encode_parameters["logical_children"].kind is inspect.Parameter.KEYWORD_ONLY

decode_parameters = inspect.signature(
    p.decode_persistence_record_versioned
).parameters
assert tuple(decode_parameters) == (
    "envelope",
    "expected_record_code",
    "expected_schema_version",
    "correlation_ref",
)
assert all(
    decode_parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    for name in (
        "expected_record_code",
        "expected_schema_version",
        "correlation_ref",
    )
)
assert (
    decode_parameters["expected_schema_version"].default
    is inspect.Parameter.empty
)
print("catalog-gate: entries=18 codes=17 ru_versions=2 legacy=17/66/7/45")
PY

expected_symbol_files=$'src/mini_agent/application/persistence.py\ntests/component/application/test_persistence_contract.py'
actual_symbol_files=$(
  rg -l \
    'P0_RECORD_SCHEMA_VERSION_CATALOG|encode_persistence_record_versioned|decode_persistence_record_versioned' \
    src tests |
    LC_ALL=C sort
)
test "$actual_symbol_files" = "$expected_symbol_files"
```

### 5. Canonical database/full-suite与cross-file scan

从feature Worktree仓库根目录执行并保存完整结果：

```bash
set -euo pipefail
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

若共享已健康container占用Worktree compose端口，必须先以read-only证据确认运行中的canonical db/db-test身份、映射端口与健康状态，再复用它们运行migration/full suite；不得把Worktree compose启动失败报告为通过，也不得擅自删除用户container。

随后从Thin Slice / Intent / Memory / execution map到source、tests及consumer运行cross-file impact scan，列出`CONFIRMED / NOT_FOUND`与全部nonclaims。Graphify不参与。

### 6. Exact-head review、latest-integration replay与merge

1. push feature branch，建立draft PR到`integration/e2e01-thin`；对exact head做独立canonical/ownership/security review，修复后必须重新运行全部gate并review到`0/0/0`。
2. 从latest official integration创建detached或独立overlay，只重放reviewed feature commits；验证两个base blobs未被integration改动、head blobs等于reviewed feature、focused/full suite和consumer scan通过，再做独立overlay review到`0/0/0`。
3. Integrator串行merge；确认remote integration exact merge SHA/tree包含reviewed overlay语义，并把该SHA记录为`B_FE_EXPAND`。
4. `B_FE_EXPAND`本身就是F/E共同barrier，execution map从此允许01-07I/P启动。后续派生状态对齐可以单独执行，但不增加barrier、不改变I/P input barrier，也不阻塞downstream dispatch。

</verification>

<success_criteria>

- Catalog恰为immutable 18 exact pairs，17 codes且only RU dual；legacy active registry仍17 v1。
- 两个fixed APIs只按caller显式exact pair dispatch；无推断、fallback、rewrite或partial return。
- RU v2 source/child/projection/local closure在encode/decode均strict复验；safe structural success不冒充provenance/owner/business authority。
- 60个pre-existing top-level definitions source/AST和legacy behavior不变；changed files恰为两个allowlist path。
- Focused、canonical migration/full suite、consumer absence、feature exact-head review、latest-integration replay/review全部通过。
- reviewed serial merge形成exact `B_FE_EXPAND`；active routing与所有barrier nonclaims保持关闭。

</success_criteria>
