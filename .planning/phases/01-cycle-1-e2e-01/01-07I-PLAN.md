---
phase: 01-cycle-1-e2e-01
plan: 07I
type: tdd
wave: 21
depends_on:
  - 01-07E
  - 01-07F
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
    - "01-07I 只执行 DEPENDENCY_EXPAND 的 Application declaration：冻结 expectation-free、owner-scoped、transactionally-consistent exact-Run closure DTO/Port，以及 fresh parameterless、raw-diagnostic-free 的 Request Understanding candidate-invalid signal。"
    - "01-07I additive 增加 ModelProviderV2，其 propose_next_move 精确返回 RequestUnderstandingOutputV2；现有 v1 ModelProvider byte/AST与全部active consumers保持不变，直到后续active switch与01-07W v1-contract closure。"
    - "正确 RU function framing 后的 RequestUnderstandingOutputV2 Pydantic/trusted-field 拒绝使用 RequestUnderstandingCandidateInvalidError；transport、HTTP、JSON/framing、零/多/错 function call 与全部 Presentation validation 仍使用 fresh ProviderProtocolError。"
    - "ExactRunEvidenceClosure 只携带一个真实 Run 的 strictly decoded logical record graph；不携带 case_id、expectations、script/provider capture、AgentRunResult、HTTP observable、EvalEvidence、raw persistence envelope、closure fence或独立 customer_id 字段。"
    - "Infrastructure 必须在一个 transactionally consistent snapshot 或等价 exact fence 内证明 owner root、exact version、provenance、relation/cardinality 与数据库 closed-set completeness；Application DTO 只验证所供应 graph，不能证明数据库没有漏行。"
    - "01-07I 不实现任何 Runtime catch、Provider translation、PostgreSQL Adapter、Eval mapper、Composition Root、active routing、v1 retirement、Case lifecycle 或 readiness。"
  artifacts:
    - "Application-owned RequestUnderstandingCandidateInvalidError、ExactRunEvidenceClosure 与 ExactRunEvidencePort。"
    - "Additive ModelProviderV2 target/failure taxonomy，以及 records/ports Component contract tests。"
  key_links:
    - "Memory owner §15.2 exact-version/owner-graph/transactional-read rules → ExactRunEvidencePort read contract。"
    - "Thin Slice §10.1/§10.3 RU v2/failure partition → additive ModelProviderV2与两个 bounded signal。"
    - "P0-RU-V2-EXECUTION-MAP：B_FE_EXPAND → {01-07I,01-07P} → B_IP；I 单独 reviewed merge 不形成新的 symbolic barrier。"
---

# Phase 1 Plan 01-07I｜Application exact-Run evidence boundary

> **ISSUED DEPENDENCY_EXPAND TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Packet 只冻结 Application declaration。任何测试通过都不表示 PostgreSQL reader、Provider/Runtime consumer、Eval mapper、active switch、Trajectory / E2E Result 或产品 readiness 已完成。

> **DERIVED / NON_NORMATIVE**
> Memory、Request Understanding、Thin Slice 与 Eval 语义仍由对应 active owner 拥有。本 Plan 只把现行规则映射为一个精确、可回滚的 Application Task Packet，不维护第二套 canonical 语义。

<objective>
以 TDD RED→GREEN 增加 exact-Run logical evidence closure、owner-scoped read Port、独立 RU candidate-invalid signal和additive `ModelProviderV2`，同时完整保留现有v1 `ModelProvider`。

Purpose: 让后续 01-07K 能实现一次快照的 strict PostgreSQL reader，让 01-07L/01-07J 能分别实现 Provider translation 与 Runtime `INPUT_INVALID` mapping，而不由下游 owner 发明 Application 合同。

Output: 一个 test-only RED commit和一个 source-only GREEN commit；只修改四个 owned files，不创建 Summary、不修改共享 State。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07E-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07F-PLAN.md
@docs/architecture/memory-design-reference.md
@docs/architecture/intent-design-reference.md
@docs/evaluation/agent-evaluation-strategy.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@tests/component/application/test_record_contracts.py
@tests/component/application/test_ports_contract.py

只使用项目受控 execution adapter；不得调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。Graphify 按用户指令保持闲置：不读取、不运行、不更新，也不作为 gate。
</execution_context>

<interfaces>

## 1. Bounded Request Understanding signal

`src/mini_agent/application/records.py` 增加：

```python
class RequestUnderstandingCandidateInvalidError(Exception):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("REQUEST_UNDERSTANDING_CANDIDATE_INVALID")
```

合同：

- public constructor严格零参数；`inspect.signature(...).parameters == {}`。
- 每次 translation 创建新实例；`args` 恰为固定一项，`str` / `repr` 不含 raw payload、Pydantic diagnostic、Prompt、Token、URL、identity 或 PII。
- 它直接继承 `Exception`，不继承或 alias `ProviderProtocolError`、`ValueError`、Pydantic exception。
- Adapter 必须先丢弃 raw exception/envelope，再创建并抛出 signal；暴露给 Application 时 `__cause__ is None` 且 `__context__ is None`。本 Packet 只声明和测试 signal 自身，不实现 Adapter translation。

## 2. Additive ModelProviderV2 and failure partition

现有 `ModelProvider` 的名称、doc、`Protocol` / `runtime_checkable`、两个methods和全部annotations保持byte/AST不变。`src/mini_agent/application/ports.py` 另行追加：

```python
@runtime_checkable
class ModelProviderV2(Protocol):
    """Bounded Request Understanding v2 and Presentation candidate provider."""

    async def propose_next_move(
        self,
        request: RequestUnderstandingInput,
    ) -> RequestUnderstandingOutputV2: ...

    async def plan_presentation(
        self,
        request: PresentationInput,
    ) -> PresentationPlan: ...
```

`ModelProviderV2` docstring精确说明：

- 对正确 RU target function 的 arguments 做 `RequestUnderstandingOutputV2` validation；Pydantic shape/version/source/authority/InputBinding/trusted-or-private-field 拒绝映射为 fresh `RequestUnderstandingCandidateInvalidError`。
- transport、HTTP、JSON/framing、零个/多个/wrong-name target call 继续映射 fresh `ProviderProtocolError`。
- `plan_presentation` 的 transport/framing/target/`PresentationPlan` validation 全部继续映射 fresh `ProviderProtocolError`。
- 两种 bounded error 都只能在 raw diagnostic 已被丢弃后暴露，且 cause/context 清空。

这是 `INFERRED / APPLICATION OWNER RULING`：execution map 冻结了I/J/L→W的expand/switch/contract ownership，但没有预先命名Python symbol。additive v2 Protocol让01-07L实现v2 Provider、01-07J切换Runtime、01-07W最后移除v1 Application Port，而不在DEPENDENCY_EXPAND提前改写active v1合同。`active_routing=false`：I不修改任何现有 consumer/implementation。

禁止 v1/v2 union、alias、default/latest、fallback或第二个临时 Provider Protocol。

## 3. ExactRunEvidenceClosure

`src/mini_agent/application/records.py` 增加 frozen、strict、Runtime-private：

```python
class ExactRunEvidenceClosure(_StrictRuntimePrivateRecord):
    conversation_record: ConversationRecord
    run_record: AgentRunRecord
    message_records: tuple[MessageRecord, ...]
    request_understanding_record: RequestUnderstandingRecordV2 | None
    accepted_task_deltas: tuple[AcceptedTaskDeltaV2, ...]
    input_binding_records: tuple[InputBinding, ...]
    task_records: tuple[TaskRecord, ...]
    task_state_transitions: tuple[TaskStateTransition, ...]
    request_unit_records: tuple[RequestUnitRecord, ...]
    conversation_task_links: tuple[ConversationTaskLinkRecord, ...]
    run_task_links: tuple[RunTaskLinkRecord, ...]
    gate_decisions: tuple[GateDecision, ...]
    tool_calls: tuple[ToolCallRecord, ...]
    tool_attempts: tuple[ToolAttemptRecord, ...]
    observation_records: tuple[OrderObservation, ...]
    context_manifests: tuple[ContextManifest, ...]
    model_visible_toolset_artifacts: tuple[ModelVisibleToolsetArtifact, ...]
    trace_events: tuple[TraceEvent, ...]
```

字段顺序、名称与类型是本 Packet 冻结的 downstream contract；所有字段都不提供default，`request_understanding_record`只是唯一nullable字段。调用方必须显式给出所有family，空family显式为`()`、无RU显式为`None`，避免mapper用expectations猜测“未返回”与“确实为空”。

这是 `INFERRED / APPLICATION OWNER RULING`：canonical owner要求expectation-free exact-Run closure，但没有预先命名Python symbol或字段。上述名称与surface只在Application declaration范围内消除下游歧义，不覆盖各记录的semantic owner。

不得复用 `TaskRecoveryAggregate` 或 `ToolCallRecoveryAggregate`：其 P0 restart caps 不能表达 stale-state Eval 路径中 Task v1→v2→v3 的两个 transition。closure 直接携带 transition/attempt families，并按实际 `state_version` / `attempt_count` 验证完整历史。

模型必须对所供应 graph 至少证明：

1. `run_record.conversation_id` 非空且精确等于 `conversation_record.conversation_id`；所有 Message / ConversationTaskLink 属于该 Conversation。
2. 每个 identity family 唯一；所有 Trace 绑定 exact Run；不得出现 foreign Run、Conversation 或 owner。
3. 可选 RU v2 record 的 `run_id` 等于 root Run、`message_ref` 命中本 closure Message；无 RU record 时 accepted child 必须为空。
4. RU `accepted_delta_refs` 与 accepted children identity exact-set；child 的 message、candidate、Task 与 InputBinding refs全部闭合。
5. `run_task_links` 的 Run 均为 root，Task refs 与 `task_records` exact-set；每个 Task owner 精确等于 Conversation owner，ConversationTaskLink / RequestUnit只引用 closure Task。
6. 每个 Task 的 transitions 按 result version 形成完整、唯一、连续的 `2..task.state_version` history，status/time/Task/RequestUnit引用闭合；不能套用 restart `max_length=1`。
7. 每个 ToolCall 的 Run/Task/RequestUnit/Manifest/Gate/InputBinding refs闭合；attempts 恰为唯一连续 `1..attempt_count` 并保持既有 lifecycle consistency。
8. GateDecision、Observation、ContextManifest、ModelVisibleToolsetArtifact 与 Trace 中所有 populated top-level refs都在 closure 内解析；Observation source Run 必须是 root。
9. 任一 duplicate、dangling、missing、extra、cross-run、cross-owner、version/history fork 或局部关系冲突导致整体 validation failure；不返回 partial closure。

Application validation只证明“给定 graph 内部闭合”。数据库是否还存在未供应 row、metadata/envelope/reference是否与 decoded source exact一致、RU v2 provenance是否经 authoritative Message重算，仍由 01-07K 在同一 snapshot/fence 中证明。

closure故意不包含`P0PersistenceEnvelope`：`application.persistence`已经依赖`application.records`，反向导入会形成循环；复制一个近似envelope又会制造第二套codec合同。01-07L只可把本Port返回的authoritative decoded records映射为grader-facing evidence，若现有PersistenceGrader仍要求raw envelope，必须在01-07L/owner范围显式裁决，不能借01-07I复制或伪造。

明确禁止字段/能力：

- `case_id`、Case expectation、requirement/lifecycle、Dataset/script refs、Provider raw/capture；
- `AgentRunResult`、HTTP response/status、safe observable、grader Result或 `EvalEvidence`；
- raw persistence row/envelope、SQL/session/transaction handle、closure fence；
- 独立 `customer_id` / auth scope字段；可信 scope只存在于 Port input，nested owner projection只用于strict comparison，不能授权。

## 4. ExactRunEvidencePort

`src/mini_agent/application/ports.py` 增加：

```python
@runtime_checkable
class ExactRunEvidencePort(Protocol):
    async def load_exact_run_evidence_for_owner(
        self,
        *,
        owner_scope: TrustedOwnerScope,
        run_id: UUID,
    ) -> ExactRunEvidenceClosure | None: ...
```

Port doc必须冻结：

- `None` 只表示 payload read 前的 absent / unauthorized / ownership-unverified，不可区分且不泄漏存在性。
- 一旦 owner-root row 被选中，identity/version/decode/provenance/owner-graph/relation/cardinality/closed-set失败必须抛 bounded `P0PersistenceIntegrityError`；不得返回 `None`、partial、skip-corrupt或换 session重试。
- Infrastructure 在一次 transactionally consistent snapshot 或等价 exact fence 内 strict-decode并证明数据库 closed set；不得通过多个独立 Port调用或session拼接 grader-facing evidence。
- Port只返回 logical closure；不授权、不写入、不claim recovery、不构造 Case/expectation/HTTP/Eval Result。

</interfaces>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-exact-run-evidence-port`
base_branch: `integration/e2e01-thin`
base_sha: `294ada386ec160ec2a48fc8883b5a38f1880e4ba`
base_tree: `97b0928100edae965004338d52ce87dff7325fd1`
input_barrier: `B_FE_EXPAND`
output_barrier: `B_IP / ONLY AFTER 01-07I AND 01-07P BOTH REVIEWED-SERIAL-MERGED`
worktree_id: `e2e01-01-exact-run-evidence-port`
writer: `Application Port declaration sole writer with owned tests, supervised by /root Integrator`
agent_role: `runtime-engineer`
active_routing: `false`

planning_and_owner_provenance:

- exact execution map/status commit `dcbba968cb1368d0a5a82e0d0203e4bbb6fc4c63`，multi-agent plan blob `243862e72ab72f885279eda5b1a89548fa2a1159`
- exact `B_FE_EXPAND` merge `294ada386ec160ec2a48fc8883b5a38f1880e4ba`，tree `97b0928100edae965004338d52ce87dff7325fd1`
- Thin Slice owner blob `233a9c06ef6ef9300bef1a0e4f86659b0ec26a13`
- Memory owner blob `5c27ba3bd2ed74e5164bdd0812133041ed96f242`
- Eval owner blob `6ee5e0cb639ddc9d2fe3f0b715252a3214284440`
- 01-07F Plan blob `d0630bfb9bebd43efbe5c1d8f110ef5dcc897ae1`
- 01-07E Plan blob `7dd2c9047bebcb9ad29435900ee0030922a5973a`
- official 01-07I Plan merge SHA/blob由Integrator在Plan PR reviewed merge后捕获；planning merge不替换feature base `B_FE_EXPAND`

owned_files_at_base:

- `src/mini_agent/application/records.py` = `f3435494b7c0d17953ba5685cfaf68ef737d44c8`
- `src/mini_agent/application/ports.py` = `190de70529d57e1faa9a681bf4c577f1597fef35`
- `tests/component/application/test_record_contracts.py` = `d3561b2a51a188e44e5908713074116131982da5`
- `tests/component/application/test_ports_contract.py` = `0b9b82c2d4f345e8da2656ee1a59ce1fe917d402`

allowlist:

- `src/mini_agent/application/records.py`
- `src/mini_agent/application/ports.py`
- `tests/component/application/test_record_contracts.py`
- `tests/component/application/test_ports_contract.py`

forbidden_files: `ALL REPOSITORY FILES OUTSIDE THE FOUR-FILE ALLOWLIST`，尤其包括 `src/mini_agent/application/agent_run_service.py`、`src/mini_agent/application/read_tool_executor.py`、`src/mini_agent/application/persistence.py`、`src/mini_agent/evaluation/**`、`src/mini_agent/infrastructure/**`、`alembic/**`、`tests/conftest.py`、`pyproject.toml`、`uv.lock`、`docs/**`、`.planning/**`、`AGENTS.md`、`PROJECT_DIRECTION.md`、`graphify-out/**`。

protected_surface:

- `records.py` 在B_FE_EXPAND的59个pre-existing top-level class/function definition source segment与AST全部不变；允许新增imports/new definitions，不得重绑、monkeypatch或修改existing definition。
- `ports.py` 在B_FE_EXPAND的9个pre-existing Protocol definitions全部source/AST不变；`ModelProvider`也不得修改。只允许新增imports与新definitions。
- 禁止修改任何现有 v1 Core/Application DTO、active Runtime behavior或Adapter implementation。

commit_contract:

1. RED `test(01-07I): define exact run evidence boundary`：只改两个 owned test文件；source blobs仍等于base。focused command必须因缺少新symbols/target contract失败，不得因syntax、fixture、数据库或环境失败。
2. GREEN `feat(01-07I): add exact run evidence port`：只改两个 owned source文件；不重写RED。
3. 正常feature history相对B_FE_EXPAND恰为上述两个commit。Finding修复只能追加 `fix(01-07I): ...`，不得amend/rebase/force-push已审历史。

contract_changes: `YES / ADDITIVE APPLICATION DEPENDENCY ONLY` — 新增exact-Run closure/Port、bounded invalid signal与ModelProviderV2；现有ModelProvider/consumer/Adapter/DB/codec不变，无active switch或v1 removal。
security_impact: `YES` — owner-scoped不可区分read、one-snapshot closed graph、cross-owner/run rejection、raw diagnostic disposal与精确failure taxonomy；Port/data不授权。
eval_impact: `YES / COMPONENT CONTRACT ONLY` — 为后续真实 PostgreSQL evidence reader/mapper提供expectation-free输入；不改Dataset、Grader、Result、threshold、Case lifecycle或任何Trajectory/E2E状态。
new_dependencies: `NONE`
graphify_disposition: `DISABLED_BY_USER / NOT_RUN / NOT_A_GATE`
rollback: 合并前关闭PR；合并后普通revert PR逆序撤销01-07I feature/fix commits，并重新阻塞01-07K/01-07L/01-07J及其全部下游。不得reset、force-push、fallback、schema/data rewrite或lifecycle claim。

handoff_format: branch、exact feature base/Plan provenance/head/commits/tree、四个base/head blobs、RED/GREEN输出、protected-surface结果、focused/full gate、changed files/commit containment、consumer/cross-file scan、contract/security/Eval nonclaims、exact-head与overlay review、风险和merge SHA。
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `ERI-S01` | Spoofing | persisted IDs/owner projection → trusted scope | `MITIGATE / BLOCK` | scope只来自TrustedOwnerScope；root/decoded owner exact compare；payload不能扩大身份 |
| `ERI-T01` | Tampering | partial/foreign graph → closure | `MITIGATE / BLOCK` | strict models、identity uniqueness、relation-driven exact sets、complete Task/Tool child histories |
| `ERI-R01` | Repudiation | multi-session stitch/RED-GREEN/review | `MITIGATE / BLOCK` | one-snapshot Port义务、exact base/blobs、atomic commits、exact-head review |
| `ERI-I01` | Information Disclosure | raw Provider/DB diagnostic、Case metadata → signal/closure | `MITIGATE / BLOCK` | parameterless fixed signal、cause/context清空、forbidden fields、None不可区分 |
| `ERI-D01` | Denial of Service | corrupt/unbounded relation graph → reader | `TRANSFER / BOUNDED` | I冻结整体fail-closed；K必须relation-driven bounded read/closed-set检测，不能partial或retry stitch |
| `ERI-E01` | Elevation of Privilege | Port/closure/physical record → authority/readiness | `MITIGATE / BLOCK` | declaration/decoded graph不授权、不路由、不写入、不claim readiness |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze signal, v2 Provider target and exact-Run closure/Port</name>
  <files>tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <action>只改两个test文件。冻结public names、exact field order/types、strict/frozen/extra behavior、minimal no-RU graph、RU v2 zero/all/partial/multi candidate graph、stale-state双transition graph、Tool attempt closure，以及duplicate/dangling/missing/extra/cross-run/cross-owner负例。断言signal零参数/fresh/fixed-safe/no-subclass/no-raw；断言additive ModelProviderV2 exact annotations/failure taxonomy且v1 ModelProvider未改；断言Port exact signature、runtime-checkable与None-vs-integrity/one-snapshot doc。测试不得连接DB、HTTP、Provider或Eval，不得用skip/xfail。</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q</automated>
    RED必须非零且只因01-07I surface/contract尚未出现；两个source blob仍等于B_FE_EXPAND。
  </verify>
  <done>行为合同先于实现固定，RED原因正确且可复现。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — declare bounded signal and exact-Run evidence boundary</name>
  <files>src/mini_agent/application/records.py, src/mini_agent/application/ports.py</files>
  <action>只改两个source文件。增加bounded signal和strict logical closure/validators；追加ModelProviderV2与ExactRunEvidencePort，现有ModelProvider保持exact。复用现有owner models与relation semantics，但不要复用restart caps、复制EvalEvidence或实现任何consumer/Adapter。focused转绿后提交GREEN，再运行protected-surface、consumer absence、canonical database/full和scope gates。</action>
  <verify>
    <automated>uv sync --all-groups
uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -q
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest</automated>
  </verify>
  <done>01-07I exact-head可进入独立review；单独完成仍不形成B_IP。</done>
</task>

</tasks>

<verification>

Feature writer与Integrator必须保存以下可复现证据：

```bash
set -euo pipefail

base_sha=294ada386ec160ec2a48fc8883b5a38f1880e4ba
base_tree=97b0928100edae965004338d52ce87dff7325fd1
expected_branch=codex/e2e01-01-exact-run-evidence-port

test "$(git branch --show-current)" = "$expected_branch"
test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-parse "${base_sha}:src/mini_agent/application/records.py")" = f3435494b7c0d17953ba5685cfaf68ef737d44c8
test "$(git rev-parse "${base_sha}:src/mini_agent/application/ports.py")" = 190de70529d57e1faa9a681bf4c577f1597fef35
test "$(git rev-parse "${base_sha}:tests/component/application/test_record_contracts.py")" = d3561b2a51a188e44e5908713074116131982da5
test "$(git rev-parse "${base_sha}:tests/component/application/test_ports_contract.py")" = 0b9b82c2d4f345e8da2656ee1a59ce1fe917d402

expected_files=$'src/mini_agent/application/ports.py\nsrc/mini_agent/application/records.py\ntests/component/application/test_ports_contract.py\ntests/component/application/test_record_contracts.py'
test "$(git diff --name-only "${base_sha}...HEAD" | LC_ALL=C sort)" = "$expected_files"
git diff --check "${base_sha}...HEAD"

test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '1p')" = \
  "test(01-07I): define exact run evidence boundary"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '2p')" = \
  "feat(01-07I): add exact run evidence port"
test "$(git log --reverse --format=%s "${base_sha}..HEAD" | sed -n '3,$p' | awk '!/^fix\\(01-07I\\): / {bad++} END {print bad+0}')" -eq 0

uv run pytest \
  tests/component/application/test_record_contracts.py \
  tests/component/application/test_ports_contract.py \
  -q
uv run python -m compileall -q src tests
git status --short
```

Protected oracle必须用 `git show "$base_sha:$file"` 与candidate AST/source比较，证明：

- `records.py` 59个pre-existing class/function definition全部保持一个同名binding且source segment/AST不变；
- `ports.py` 全部9个existing Protocol source/AST不变，包括v1 `ModelProvider`；
- 新symbol没有重绑existing name、decorator monkeypatch、dynamic `setattr/exec/eval/globals`或module-level mutation。

Consumer/cross-file impact scan：

```bash
git diff --name-only "${base_sha}...HEAD" | LC_ALL=C sort
rg -n "RequestUnderstandingCandidateInvalidError|ExactRunEvidence(Closure|Port)|ModelProviderV2" \
  src/mini_agent tests \
  --glob '*.py'
rg -n "RequestUnderstandingOutputV2|propose_next_move" \
  src/mini_agent/application/agent_run_service.py \
  src/mini_agent/evaluation/scripted_provider.py \
  src/mini_agent/infrastructure/model/qwen_responses.py
```

第一个scan的新symbol只允许出现在四文件allowlist；第二个scan用于证明existing consumers仍未切换，不授权修改它们。随后从仓库根目录执行canonical五命令：

```bash
uv sync --all-groups
docker compose up --wait -d db
docker compose --profile test up --wait -d db-test
uv run alembic upgrade head
uv run pytest
```

Feature exact head必须先独立review，`CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`；再在latest integration创建只读overlay并重复scope/focused/full/protected gates。01-07I与01-07P串行review/merge；只有第二个reviewed merge完成且共同tree验证通过，才记录`B_IP`。

</verification>

<success_criteria>

1. RED/GREEN提交顺序、scope和失败/通过输出可复现。
2. 四个public symbols、closure field surface、graph validator与Provider failure partition满足本Plan。
3. 59 + 9个pre-existing definitions全部不变。
4. 四文件allowlist外零改动；Runtime/Provider/DB/Eval均未active switch。
5. feature和latest-overlay均独立review通过；I单独merge不误报B_IP。

</success_criteria>
