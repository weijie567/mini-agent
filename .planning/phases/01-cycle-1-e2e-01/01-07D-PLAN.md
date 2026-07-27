---
phase: 01-cycle-1-e2e-01
plan: 07D
type: execute
wave: 16
depends_on:
  - 01-07C
  - 01-07G
files_modified:
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "第一薄切片将 Request Understanding input、model output 与 durable logical record 固定为互不替代的 `e2e01-thin-v1`、`e2e01-thin-v2` 与 `request_understanding_record.p0.v2`；不存在 alias、fallback 或隐式推导。"
    - "`RequestUnderstandingRecord` 以独立 `request_understanding_record_id` 为 identity，保存恰好一个实际 contextualization、全部实际 emitted candidates、逐候选最终 decision、accepted child exact-set、NextMove 审计版本和可信时间；不得从最终 Task State 重建。"
    - "`AcceptedTaskDelta` 是父记录 local logical child，内联 `task_id`、`base_task_state_version?`、`result_task_state_version`；`(accepted_delta_id, task_id)` 唯一绑定实际 effect，不存在全局或平行 Task-version binding array。"
    - "v2 结构支持 owner 已定义的零到多个 Candidate、ACCEPT、REJECT 和部分接受闭包；当前 E2E01 成功轨迹仍恰为一个 accepted `ADD_GOAL`。"
    - "17 个 top-level record code 保持恰好 17；marker-bounded registry / top-level projection / child projection / local closure 分别恰为 17 / 70 / 8 / 11 行，并导出恰好 49 条 `P0RecordReference` projection rule。"
    - "整体 invalid Provider output 不产生 durable Request Understanding record；raw Provider、Prompt、Token、诊断、可信身份或授权字段都不进入记录。"
    - "本 Packet 只修改 Thin Slice scoped owner；01-07E 实现 codec / registry encode-decode，01-07F 实现 Request Understanding Core DTO / reducer，但二者必须等到 reviewed D+H serial-integration common barrier 后才可 planning/dispatch；本 Packet 不修改任何代码、数据库、Eval 或 lifecycle。"
    - "01-07D 或 01-07H 任一单独 merge、两个未串行集成的 branch heads、planning artifact 或 overlay 都不能授权 01-07E / 01-07F。"
  artifacts:
    - "docs/implementation/e2e01-thin-slice-implementation-spec.md 中唯一的 RU v2 scoped field/version/closure mapping 与 marker-bounded matrices。"
  key_links:
    - "Intent owner blob `456be9c7d7884e2a58c4d07b867765ed336aa6f5` 的通用 durable semantics 被逐字段映射到 Thin Slice owner，不被缩窄或重写。"
    - "01-07D 与 01-07H 必须分别取得独立 exact-head review、由 Integrator 串行合并并记录同时包含两者的 exact common barrier；只有该 barrier 才能授权 01-07E / 01-07F planning 或 dispatch，D 或 H 单独 merge 均不授权。"
---

# Phase 1 Plan 01-07D｜Request Understanding v2 exact mapping

> **ISSUED SCOPED-CONTRACT TASK PACKET / IMPLEMENTATION NOT STARTED**
> 01-07C 已在 Intent owner 冻结 durable aggregate、独立版本轴和 exact-set closure；当前 Thin Slice Spec 仍把 model output `e2e01-thin-v1` 与 logical record `request_understanding_record.p0.v1` 混用，并保留旧的最小 record shape。本 Packet 只把 owner 裁决映射为第一薄切片可直接实现的 exact fields、versions、relations 与 mechanical denominator。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 不拥有 Request Understanding 语义。语义 authority 是 Intent owner，scoped encoding authority 是本 Packet 唯一 owned file；Plan、当前代码和 `.planning/` 状态都不能反向覆盖它。

<objective>
在 Thin Slice scoped owner 中冻结 Request Understanding durable v2 的 exact schema axes、parent / logical-child fields、0..n closure、projection relation tokens、compatibility 和下游 ownership。

Purpose: 先形成无歧义的D侧mapping；只有D与H均reviewed、串行集成并记录exact common barrier后，01-07E codec与01-07F Core才可planning/dispatch并分别消费该contract，消除version confusion、candidate reconstruction、dangling accepted effect与旧v1 fallback。

Output: 仅修改 `docs/implementation/e2e01-thin-slice-implementation-spec.md` 的一个合同提交；不修改 Python、数据库、Runtime、Eval、Trace reader 或 lifecycle。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07G-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md

不得把 01-07C / 01-07G Summary 当作 execution-base input：固定 base 中不存在这些 Summary。执行只使用下述 exact commits、Plans、blobs 与两个 active owner blobs。不得调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。
</execution_context>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-exact-mapping`
base_branch: `integration/e2e01-thin`
base_sha: `327b39da45cdcf564609a5385d52c4264da2c669`
base_tree: `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887`
worktree_id: `e2e01-01-ru-exact-mapping`
writer: `Thin Slice scoped-contract sole writer, supervised by /root Integrator`
agent_role: `gsd-doc-writer`

物理 Worktree path 只由 Integrator 私下 dispatch，不写入 Plan、commit 或 PR。

owned_files:

- `docs/implementation/e2e01-thin-slice-implementation-spec.md`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/business-capabilities.md`
- `docs/architecture/**`
- `docs/evaluation/**`
- every other `docs/implementation/**` path
- `src/**`
- `tests/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- execution base / tree：`327b39da45cdcf564609a5385d52c4264da2c669` / `49ad0f3f5fc2c0cbe507763aca12bb6825fb7887`
- Thin Slice owner blob：`538105706f471dabe9cf8964d1026c4abf484356`
- Intent owner blob：`456be9c7d7884e2a58c4d07b867765ed336aa6f5`
- 01-07C Plan blob：`66a3a974f5d7408239b8ba3691abdb0c1781fa63`
- 01-07G Plan blob：`72c866f0afac449c7c9970c223c9eb182fb1e780`
- 01-07G scoped-owner merge `bfc63c9444ee1af204cc3806eac7e7e84fc1bb19`
- 01-07C revised Plan commit `79ae0a921cb8a6ff64f308ddf377c93354701cf8`
- 01-07C owner merge / C+G common barrier `327b39da45cdcf564609a5385d52c4264da2c669`

dependencies:

- 本 Plan 的 planning-status PR 必须先取得独立 exact-head `PASS` 并 reviewed merge；Executor 记录 official planning commit 与本 Plan blob。
- feature Worktree 必须从固定 `base_sha` clean 创建；planning commit 只作为 captured Git object 读取，不改变 execution base。
- preflight 必须同时证明两个 owner blobs和两个 Plan blobs与本 Packet完全一致；任一 byte drift 都 `BLOCK`。
- 01-07D与01-07H是从同一C/G barrier签发的Wave 16 peer Packet，彼此不形成`depends_on`；其共同下游依赖只能由两者独立review后串行集成形成。
- 01-07D 与 01-07H feature PR 必须各自取得独立 exact-head `PASS`，再由 Integrator 串行合并到 `integration/e2e01-thin`；并行、单边或未 reviewed 的 merge 不构成下游依赖。
- Integrator 必须在第二个 merge 后记录一个 exact common barrier SHA，并证明该 barrier 同时包含 reviewed 01-07D 与 reviewed 01-07H 的 exact commits / owner blobs。
- 01-07E / 01-07F 的 planning 与 dispatch 在上述 D+H common barrier 记录完成前一律 `BLOCK`；D merge alone、H merge alone、两个未串行集成的 branch heads或任一 planning artifact都不能授权 E/F。

required_checks:

- exact branch/base/tree/merge-base/clean state、owner/Plan blob 与唯一 planning provenance preflight
- 相对 base 恰好一个 feature commit、changed-file set 恰好等于唯一 owned file
- registry 仍恰好 17 个 top-level code；只把 RU identity/version 改为本 Packet exact mapping
- 三个 schema axes 与 Task concurrency axis 独立；无 alias、fallback、default inference 或 compatibility guessing
- parent fields、logical child fields、cardinality、authority、timestamps 与 invalid-output no-record 规则逐项明确
- marker-bounded parser 证明 17 / 70 / 8 / 11 rows、8 个 marker 各出现一次、46 + 3 = 49 条 reference rules
- compatibility parser证明两个marker-bounded contract的13个exact key各恰好一次且value逐字相等；synthetic exact contract通过，30个ALLOWED / duplicate / unknown / unbounded-v1 mutations全部按预期fail closed
- 同一个parser对固定B_CG owner必须只以`MISSING_RU_V2: exact registry row`失败，对feature/overlay owner必须通过；其他negative reason或B_CG意外通过都`BLOCK`
- focused forbidden-content / version / relation scans、local links、`git diff --check` 与 full `uv run pytest`
- repository-wide cross-file impact scan只记录 01-07E/F 等 downstream consumer，不修改 forbidden files
- independent exact-head canonical / ownership / security review；unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`
- 第一个 C/G 后续 merge 已存在时，以最新 integration head 构造不改写 feature lineage 的 overlay，重复 parser、diff-check、focused scan 与 full suite

done_when:

- Thin Slice owner形成唯一、完整、可机械解析的 RU v2 mapping
- 一个 commit只改一个 owned file，所有 exact count、relation 与 compatibility gate通过
- 01-07E/F ownership清晰，无 Python / codec / Runtime / DB / Eval / lifecycle scope 混入
- exact feature与latest-integration overlay均通过独立review和全部要求检查；随后仍须等待01-07H reviewed merge、串行集成和D+H exact common barrier，D完成本身不授权E/F
- draft PR指向 `integration/e2e01-thin`，记录contract/security/Eval impact、nonclaims、rollback和residual risks

contract_changes: `YES / SCOPED THIN-SLICE CONTRACT` — 把 Intent owner durable aggregate 映射为 RU logical v2、model output v2、exact fields、logical child与矩阵关系；不改变通用语义。
security_impact: `YES` — 阻断 version confusion、身份伪造、raw Provider泄露、candidate重建、dangling ACCEPT与无归属Task effect。
eval_impact: `YES / CONTRACT INPUT ONLY` — 让实际 contextualization、Candidate、decision与Task effect可重放/评分；不修改Dataset、Grader、Result、threshold或Case lifecycle。
new_dependencies: `NONE`
nonclaims: `NO IMPLEMENTATION CLAIM` — 不声称01-07E/F、Python DTO、codec、Runtime、DB、migration、Trace/Eval reader、Trajectory/E2E Result或P0产品已实现/验证/ready。
graphify_disposition: `INTEGRATOR POST-MERGE SEMANTIC GATE` — feature writer不得修改`graphify-out/**`；D与H均reviewed、串行合并并记录exact common barrier后，Integrator运行项目支持的semantic update并以source scan核对Intent owner→Thin Slice→01-07E/F关系；无法运行时记录`NOT_RUN`，且D单独merge不得触发E/F planning/dispatch或声称graph fresh。
rollback: 合并前关闭PR；合并后普通revert PR，使D+H common barrier失效并重新阻塞01-07E/F planning/dispatch。不得reset、force-push、read fallback、静默backfill或伪造旧runtime readiness。

handoff_to: `/root Integrator`

handoff_format:

- repository / remote / branch / worktree_id / agent role
- exact base/tree/planning/head/commit/tree、Plan/owner blobs
- exact one-file feature与overlay containment
- 17 / 70 / 8 / 11 / 49 inventory及parser输出
- schema-axis、parent、child、closure、migration与nonclaim decisions
- commands / exact results、cross-file impact、contract/security/Eval impact
- independent feature/overlay reviews、residual risks与rollback
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUM-S01` | Spoofing | user/model/provider → record identity/version/time | `MITIGATE / BLOCK` | independent Runtime identity、exact versions与trusted UTC；模型不能提供或覆盖 |
| `RUM-T01` | Tampering | candidate/decision/child → Task effect | `MITIGATE / BLOCK` | exact-set local closure、unique `(accepted_delta_id, task_id)`、49-rule parser与atomic aggregate |
| `RUM-R01` | Repudiation | emitted model output → durable audit | `MITIGATE / BLOCK` | 保存实际 contextualization/candidates，不从最终状态重建；每个decision与effect可追溯 |
| `RUM-I01` | Information Disclosure | Provider / trusted context → durable record | `MITIGATE / BLOCK` | 禁止raw payload、Prompt、Token、diagnostic、customer/authorization/private binding |
| `RUM-D01` | Denial of Service | unknown/mismatched v1/v2 → reader | `MITIGATE / BOUNDED` | exact-version fail closed；无fallback、read migration或retry loop |
| `RUM-E01` | Elevation of Privilege | model candidate → authoritative Task mutation | `MITIGATE / BLOCK` | Candidate只是提议；仅确定性validation/reducer产生accepted child和Task effect |

</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Freeze exact schema axes, parent fields and accepted child</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
在第5节与第10.1节同步冻结：

1. `RequestUnderstandingInput.schema_version`保持唯一literal `e2e01-thin-v1`；`RequestUnderstandingOutput.schema_version`与model output唯一literal改为`e2e01-thin-v2`；二者无alias/fallback。
2. `RequestUnderstandingRecord.schema_version`是logical mirror `request_understanding_record.p0.v2`，registry code仍是`request_understanding_record`；其identity改为`request_understanding_record_id`，`run_id`仅关联`agent_run_record`，`message_ref`仅关联`message_record`。
3. Parent字段完整且无额外替代表达：`request_understanding_record_id`、`run_id`、`message_ref`、`schema_version`、`model_input_schema_version`、`model_output_schema_version`、恰好一个`contextualization`、实际`task_delta_candidates[]`、`candidate_validation[]`、`accepted_delta_refs[]`、`proposed_base_task_state_version?`、`validated_task_state_version?`、`next_move_candidate_ref?`、`created_at`。
4. `contextualization`严格使用Intent owner的`QueryContextualizationCandidate`字段：`text`、`resolved_reference_candidates[]`、`uncertainties[]`、`source_message_refs[]`；保存实际validated projection。`task_delta_candidates[]`同样保存Provider实际emitted canonical candidates，禁止从Accepted Delta、Task或回复重建。
5. `AcceptedTaskDelta`继续是`accepted_task_delta` parent-local child，在既有字段上内联`task_id`、`base_task_state_version?`、`result_task_state_version`；`(accepted_delta_id, task_id)`唯一。删除/禁止任何父级`task_state_version_bindings[]`、global base/result或无法关联的parallel arrays。
6. v2 structural cardinality为0..n candidates；每项恰好一个ACCEPT/REJECT。ACCEPT恰好一个child/effect且无reason；REJECT携带keyed bounded `reason_code`且无child/effect。当前E2E01成功收窄为一个accepted `ADD_GOAL`、new Task base=`null`、result=`1`。
7. `created_at`与全部accepted child `accepted_at`来自同一次trusted UTC sample；replay不刷新。整体provider/schema/version invalid时不创建durable RU record。明确禁止raw provider/prompt/token/diagnostic/trusted identity/private fields。
  </action>
  <verify>
    <automated>set -euo pipefail
spec=docs/implementation/e2e01-thin-slice-implementation-spec.md
git diff --check 327b39da45cdcf564609a5385d52c4264da2c669 -- "$spec"
for exact_required in \
  'RequestUnderstandingInput.schema_version' \
  'e2e01-thin-v1' \
  'RequestUnderstandingOutput.schema_version' \
  'e2e01-thin-v2' \
  'RequestUnderstandingRecord.schema_version' \
  'request_understanding_record.p0.v2' \
  'request_understanding_record_id' \
  'run_id' \
  'message_ref' \
  'model_input_schema_version' \
  'model_output_schema_version' \
  'contextualization' \
  'task_delta_candidates[]' \
  'candidate_validation[]' \
  'accepted_delta_refs[]' \
  'proposed_base_task_state_version?' \
  'validated_task_state_version?' \
  'next_move_candidate_ref?' \
  'created_at' \
  'AcceptedTaskDelta' \
  'task_id' \
  'base_task_state_version?' \
  'result_task_state_version'
do
  rg -F -q -- "$exact_required" "$spec"
done</automated>
人工逐项对照Intent owner第6、7、13节，确认没有省略、重建、version alias或global Task-effect binding。
  </verify>
  <done>三个schema axis、完整parent、inline child、0..n closure、可信时间与invalid-output no-record规则唯一且可实现。</done>
</task>

<task type="auto">
  <name>Task 2: Freeze marker matrices, exact counts and compatibility boundary</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
保留17-row registry marker pair，并把唯一RU row精确改为：

```text
| RequestUnderstandingRecord | request_understanding_record | request_understanding_record.p0.v2 | Request Understanding | RequestUnderstandingRecord | request_understanding_record_id | run_id -> agent_run_record; message_ref -> message_record |
```

实际Markdown row仍按既有列使用backtick。Top-level projection保留62个非RU rows，并把RU rows精确设为以下8项，得到70 rows：

| field | classification | exact relation token / target | exact cardinality |
|---|---|---|---|
| `run_id` | `TOP_LEVEL_P0_REFERENCE` | `run_id -> agent_run_record` | `exactly one；correlation only，不是本记录 identity` |
| `message_ref` | `TOP_LEVEL_P0_REFERENCE` | `message_ref -> message_record` | `exactly one；correlation only，不是本记录 identity` |
| `contextualization.resolved_reference_candidates[].source_ref` | `TOP_LEVEL_P0_REFERENCE` | `contextualization_resolved_source_ref -> message_record` | `zero or more；reference tuple unique` |
| `contextualization.source_message_refs[]` | `TOP_LEVEL_P0_REFERENCE` | `contextualization_source_message_ref -> message_record` | `one or more；unique；must include parent message_ref` |
| `task_delta_candidates[].input_candidates[].source_ref` | `TOP_LEVEL_P0_REFERENCE` | `task_delta_input_source_ref -> message_record` | `zero or more；reference tuple unique` |
| `accepted_delta_refs[]` | `LOGICAL_CHILD_CORRELATION` | `child code accepted_task_delta` | `与 children identities 一一对应且顺序无关` |
| `candidate_validation[].candidate_ref` | `PARENT_LOCAL_CORRELATION` | `parent task_delta_candidates[].candidate_id` | `与 emitted candidate_id exact set；每个恰好一个 final decision` |
| `next_move_candidate_ref?` | `PAYLOAD_CORRELATION` | `no top-level target` | `zero or one` |

Child projection在现有7 rows中新增唯一第8 row：`AcceptedTaskDelta | task_id | CHILD_TOP_LEVEL_P0_REFERENCE | accepted_delta_task_id -> task_record | exactly one`；其余7 rows的field、classification、target与cardinality逐字保持不变。

新增唯一marker pair `P0-PERSISTENCE-LOCAL-CLOSURE:START/END`，采用`scope | local field / relation | exact closure rule`三列且恰好包含以下11个exact rows：

| scope | local field / relation | exact closure rule |
|---|---|---|
| `RequestUnderstandingRecord` | `contextualization` | `exactly one；actual validated QueryContextualizationCandidate projection，never reconstructed` |
| `RequestUnderstandingRecord` | `task_delta_candidates[].candidate_id` | `0..n；candidate_id unique；actual emitted canonical candidates` |
| `RequestUnderstandingRecord` | `candidate_validation[].candidate_ref` | `exactly same candidate_id set；exactly one final decision per candidate` |
| `CandidateValidationRecord` | `decision=ACCEPT` | `exactly one AcceptedTaskDelta child by candidate_ref；reason_code absent` |
| `CandidateValidationRecord` | `decision=REJECT` | `bounded reason_code required；no accepted child or Task effect` |
| `RequestUnderstandingRecord` | `accepted_delta_refs[]` | `unique；exact same set as AcceptedTaskDelta.accepted_delta_id and ACCEPT children` |
| `AcceptedTaskDelta` | `candidate_ref` | `exactly one emitted candidate with ACCEPT decision；one child per accepted candidate` |
| `AcceptedTaskDelta` | `(accepted_delta_id, task_id)` | `unique pair；binds exactly one inline Task effect` |
| `AcceptedTaskDelta` | `base_task_state_version? + result_task_state_version` | `new Task base null and result positive；existing Task uses exact CAS base/result；no global or parallel binding` |
| `RequestUnderstandingRecord` | `next_move_candidate_ref? + proposed_base_task_state_version? + validated_task_state_version?` | `zero or one correlated NextMove audit；never substitutes AcceptedTaskDelta Task effect` |
| `RequestUnderstandingRecord` | `created_at + AcceptedTaskDelta.accepted_at` | `one trusted UTC sample；idempotent replay never refreshes` |

机械denominator固定为：17 registry rows、70 top projection rows、8 child rows、11 local-closure rows；四对START/END marker共8个exact marker string且各出现一次。Reference-producing rows固定为top-level 46（43旧rules + 3新message relations）和child 3（2旧rules + accepted task relation），总计49；不得保留旧66/7/45。

Compatibility固定为exact-v2-only。新增唯一marker pair `P0-RU-V2-COMPATIBILITY:START/END`；marker内部只能出现`key: value`行，以下11个key各恰好一次且value逐字相等，不允许未知key、重复key、冲突value或额外 prose：

```text
current_logical_record_version: request_understanding_record.p0.v2
model_input_schema_version: e2e01-thin-v1
model_output_schema_version: e2e01-thin-v2
schema_aliases: NONE
schema_fallback: FORBIDDEN
automatic_v1_to_v2_inference: FORBIDDEN
automatic_v1_to_v2_migration: FORBIDDEN
automatic_v1_to_v2_backfill: FORBIDDEN
global_task_state_version_binding: FORBIDDEN
parallel_task_state_version_arrays: FORBIDDEN
retained_v1_runtime_readiness: BLOCK_WITH_NEW_MIGRATION_PACKET
```

另新增唯一marker pair `P0-RU-V1-HISTORICAL-DENIED:START/END`，内部也只能有以下两个exact key/value；owner中任何`request_understanding_record.p0.v1`字样只能位于该显式historical/denied block，block外出现即`BLOCK`：

```text
historical_logical_record_version: request_understanding_record.p0.v1
historical_runtime_status: DENIED_NOT_CURRENT
```

若任何保留的v1 durable data必须进入runtime readiness，新增Packet必须带source/target、数据denominator、atomicity、security/Eval和rollback。最后写明01-07E独占codec/registry encode/decode，01-07F独占Core DTO/validator/reducer；但两者的planning/dispatch都必须等待01-07D与01-07H分别reviewed、串行集成并记录exact common barrier，D merge alone不授权。本Packet不改代码、DB、Eval、Trace或lifecycle。
  </action>
  <verify>
    <automated>set -euo pipefail
uv run python - <<'PY'
from pathlib import Path
import re
import subprocess

BASE = "327b39da45cdcf564609a5385d52c4264da2c669"
SPEC = "docs/implementation/e2e01-thin-slice-implementation-spec.md"

def cells(line: str) -> tuple[str, ...]:
    return tuple(
        cell.strip().replace("`", "")
        for cell in line.strip().strip("|").split("|")
    )

def rows_for(text: str, name: str) -> tuple[tuple[str, ...], ...]:
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    assert text.count(start) == 1, f"MARKER_COUNT:{start}"
    assert text.count(end) == 1, f"MARKER_COUNT:{end}"
    assert text.index(start) < text.index(end), f"MARKER_ORDER:{name}"
    body = text.split(start, 1)[1].split(end, 1)[0]
    return tuple(cells(line) for line in body.splitlines() if line.startswith("| `"))

base_text = subprocess.check_output(
    ["git", "show", f"{BASE}:{SPEC}"], text=True
)
base_registry = rows_for(base_text, "P0-PERSISTENCE-REGISTRY")
base_top = rows_for(base_text, "P0-PERSISTENCE-PROJECTION")
base_child = rows_for(base_text, "P0-PERSISTENCE-CHILD-PROJECTION")

def reference_keys(
    top: tuple[tuple[str, ...], ...],
    child: tuple[tuple[str, ...], ...],
) -> frozenset[tuple[str, ...]]:
    top_classes = {"TOP_LEVEL_P0_REFERENCE", "EXTERNAL_REQUIRED_P0_REFERENCE"}
    keys = {row[:4] for row in top if row[2] in top_classes}
    keys |= {row[:4] for row in child if row[2] == "CHILD_TOP_LEVEL_P0_REFERENCE"}
    return frozenset(keys)

base_reference_keys = reference_keys(base_top, base_child)
assert len(base_reference_keys) == 45, "UNEXPECTED_B_CG_REFERENCE_DENOMINATOR"

expected_registry_ru = (
    "RequestUnderstandingRecord",
    "request_understanding_record",
    "request_understanding_record.p0.v2",
    "Request Understanding",
    "RequestUnderstandingRecord",
    "request_understanding_record_id",
    "run_id -> agent_run_record; message_ref -> message_record",
)
expected_ru_top = {
    ("RequestUnderstandingRecord", "run_id", "TOP_LEVEL_P0_REFERENCE", "run_id -> agent_run_record", "exactly one；correlation only，不是本记录 identity"),
    ("RequestUnderstandingRecord", "message_ref", "TOP_LEVEL_P0_REFERENCE", "message_ref -> message_record", "exactly one；correlation only，不是本记录 identity"),
    ("RequestUnderstandingRecord", "contextualization.resolved_reference_candidates[].source_ref", "TOP_LEVEL_P0_REFERENCE", "contextualization_resolved_source_ref -> message_record", "zero or more；reference tuple unique"),
    ("RequestUnderstandingRecord", "contextualization.source_message_refs[]", "TOP_LEVEL_P0_REFERENCE", "contextualization_source_message_ref -> message_record", "one or more；unique；must include parent message_ref"),
    ("RequestUnderstandingRecord", "task_delta_candidates[].input_candidates[].source_ref", "TOP_LEVEL_P0_REFERENCE", "task_delta_input_source_ref -> message_record", "zero or more；reference tuple unique"),
    ("RequestUnderstandingRecord", "accepted_delta_refs[]", "LOGICAL_CHILD_CORRELATION", "child code accepted_task_delta", "与 children identities 一一对应且顺序无关"),
    ("RequestUnderstandingRecord", "candidate_validation[].candidate_ref", "PARENT_LOCAL_CORRELATION", "parent task_delta_candidates[].candidate_id", "与 emitted candidate_id exact set；每个恰好一个 final decision"),
    ("RequestUnderstandingRecord", "next_move_candidate_ref?", "PAYLOAD_CORRELATION", "no top-level target", "zero or one"),
}
expected_child = {
    ("AcceptedTaskDelta", "candidate_ref", "PARENT_LOCAL_CORRELATION", "parent candidate_validation[].candidate_ref", "exactly one parent match，且 decision 必须为 ACCEPT"),
    ("AcceptedTaskDelta", "message_ref", "PARENT_FIELD_EQUALITY", "parent RequestUnderstandingRecord.message_ref", "exactly equal"),
    ("AcceptedTaskDelta", "input_binding_refs[]", "CHILD_TOP_LEVEL_P0_REFERENCE", "input_binding_ref -> input_binding_record", "one or more；unique"),
    ("AcceptedTaskDelta", "task_id", "CHILD_TOP_LEVEL_P0_REFERENCE", "accepted_delta_task_id -> task_record", "exactly one"),
    ("TaskStateTransition", "task_id", "PARENT_FIELD_EQUALITY", "parent TaskRecord.task_id", "exactly equal"),
    ("TaskStateTransition", "request_unit_id", "CHILD_TOP_LEVEL_P0_REFERENCE", "request_unit_id -> request_unit_record", "exactly one"),
    ("TaskStateTransition", "reason_ref", "PAYLOAD_CORRELATION", "reason target kind not frozen", "exactly one scalar"),
    ("ToolAttemptRecord", "tool_call_id", "PARENT_FIELD_EQUALITY", "parent ToolCallRecord.tool_call_id", "exactly equal"),
}
expected_local = {
    ("RequestUnderstandingRecord", "contextualization", "exactly one；actual validated QueryContextualizationCandidate projection，never reconstructed"),
    ("RequestUnderstandingRecord", "task_delta_candidates[].candidate_id", "0..n；candidate_id unique；actual emitted canonical candidates"),
    ("RequestUnderstandingRecord", "candidate_validation[].candidate_ref", "exactly same candidate_id set；exactly one final decision per candidate"),
    ("CandidateValidationRecord", "decision=ACCEPT", "exactly one AcceptedTaskDelta child by candidate_ref；reason_code absent"),
    ("CandidateValidationRecord", "decision=REJECT", "bounded reason_code required；no accepted child or Task effect"),
    ("RequestUnderstandingRecord", "accepted_delta_refs[]", "unique；exact same set as AcceptedTaskDelta.accepted_delta_id and ACCEPT children"),
    ("AcceptedTaskDelta", "candidate_ref", "exactly one emitted candidate with ACCEPT decision；one child per accepted candidate"),
    ("AcceptedTaskDelta", "(accepted_delta_id, task_id)", "unique pair；binds exactly one inline Task effect"),
    ("AcceptedTaskDelta", "base_task_state_version? + result_task_state_version", "new Task base null and result positive；existing Task uses exact CAS base/result；no global or parallel binding"),
    ("RequestUnderstandingRecord", "next_move_candidate_ref? + proposed_base_task_state_version? + validated_task_state_version?", "zero or one correlated NextMove audit；never substitutes AcceptedTaskDelta Task effect"),
    ("RequestUnderstandingRecord", "created_at + AcceptedTaskDelta.accepted_at", "one trusted UTC sample；idempotent replay never refreshes"),
}
new_reference_keys = {
    ("RequestUnderstandingRecord", "contextualization.resolved_reference_candidates[].source_ref", "TOP_LEVEL_P0_REFERENCE", "contextualization_resolved_source_ref -> message_record"),
    ("RequestUnderstandingRecord", "contextualization.source_message_refs[]", "TOP_LEVEL_P0_REFERENCE", "contextualization_source_message_ref -> message_record"),
    ("RequestUnderstandingRecord", "task_delta_candidates[].input_candidates[].source_ref", "TOP_LEVEL_P0_REFERENCE", "task_delta_input_source_ref -> message_record"),
    ("AcceptedTaskDelta", "task_id", "CHILD_TOP_LEVEL_P0_REFERENCE", "accepted_delta_task_id -> task_record"),
}
expected_compatibility = {
    "current_logical_record_version": "request_understanding_record.p0.v2",
    "model_input_schema_version": "e2e01-thin-v1",
    "model_output_schema_version": "e2e01-thin-v2",
    "schema_aliases": "NONE",
    "schema_fallback": "FORBIDDEN",
    "automatic_v1_to_v2_inference": "FORBIDDEN",
    "automatic_v1_to_v2_migration": "FORBIDDEN",
    "automatic_v1_to_v2_backfill": "FORBIDDEN",
    "global_task_state_version_binding": "FORBIDDEN",
    "parallel_task_state_version_arrays": "FORBIDDEN",
    "retained_v1_runtime_readiness": "BLOCK_WITH_NEW_MIGRATION_PACKET",
}
expected_historical_denial = {
    "historical_logical_record_version": "request_understanding_record.p0.v1",
    "historical_runtime_status": "DENIED_NOT_CURRENT",
}

def parse_key_value_contract(
    text: str,
    name: str,
    expected: dict[str, str],
) -> tuple[int, int]:
    start_token = f"<!-- {name}:START -->"
    end_token = f"<!-- {name}:END -->"
    assert text.count(start_token) == 1, f"{name}_START_MARKER_COUNT"
    assert text.count(end_token) == 1, f"{name}_END_MARKER_COUNT"
    start = text.index(start_token)
    end = text.index(end_token)
    assert start < end, f"{name}_MARKER_ORDER"
    body = text[start + len(start_token):end]
    parsed: dict[str, str] = {}
    for line in (line.strip() for line in body.splitlines() if line.strip()):
        match = re.fullmatch(r"([a-z0-9_]+): ([A-Za-z0-9_.-]+)", line)
        assert match is not None, f"{name}_MALFORMED_LINE:{line}"
        key, value = match.groups()
        assert key in expected, f"{name}_UNKNOWN_KEY:{key}"
        assert key not in parsed, f"{name}_DUPLICATE_KEY:{key}"
        parsed[key] = value
    assert set(parsed) == set(expected), f"{name}_KEY_SET"
    for key, expected_value in expected.items():
        assert parsed[key] == expected_value, f"{name}_VALUE:{key}"
    outside = text[:start] + text[end + len(end_token):]
    for key in expected:
        assert not re.search(
            rf"(?m)^[ \t]*{re.escape(key)}[ \t]*:", outside
        ), f"{name}_KEY_OUTSIDE_MARKER:{key}"
    return start, end + len(end_token)

def validate_compatibility(text: str) -> None:
    parse_key_value_contract(
        text,
        "P0-RU-V2-COMPATIBILITY",
        expected_compatibility,
    )
    historical_start, historical_end = parse_key_value_contract(
        text,
        "P0-RU-V1-HISTORICAL-DENIED",
        expected_historical_denial,
    )
    outside_historical = text[:historical_start] + text[historical_end:]
    assert (
        "request_understanding_record.p0.v1" not in outside_historical
    ), "UNBOUNDED_RU_V1_DECLARATION"

def render_contract(name: str, values: dict[str, str]) -> str:
    lines = [f"<!-- {name}:START -->"]
    lines.extend(f"{key}: {value}" for key, value in values.items())
    lines.append(f"<!-- {name}:END -->")
    return "\n".join(lines)

synthetic_exact_contract = "\n".join(
    (
        render_contract("P0-RU-V2-COMPATIBILITY", expected_compatibility),
        render_contract(
            "P0-RU-V1-HISTORICAL-DENIED",
            expected_historical_denial,
        ),
    )
)
validate_compatibility(synthetic_exact_contract)

def expect_compatibility_failure(
    label: str,
    mutated: str,
    expected_reason: str,
) -> None:
    try:
        validate_compatibility(mutated)
    except AssertionError as error:
        assert str(error) == expected_reason, (
            f"MUTATION_WRONG_REASON:{label}:{error}"
        )
    else:
        raise AssertionError(f"MUTATION_UNEXPECTED_PASS:{label}")

mutation_count = 0
for name, values in (
    ("P0-RU-V2-COMPATIBILITY", expected_compatibility),
    ("P0-RU-V1-HISTORICAL-DENIED", expected_historical_denial),
):
    for key, value in values.items():
        exact_line = f"{key}: {value}"
        expect_compatibility_failure(
            f"{name}:{key}:ALLOWED",
            synthetic_exact_contract.replace(
                exact_line,
                f"{key}: ALLOWED",
                1,
            ),
            f"{name}_VALUE:{key}",
        )
        mutation_count += 1
        expect_compatibility_failure(
            f"{name}:{key}:duplicate",
            synthetic_exact_contract.replace(
                exact_line,
                f"{exact_line}\n{exact_line}",
                1,
            ),
            f"{name}_DUPLICATE_KEY:{key}",
        )
        mutation_count += 1

for name in (
    "P0-RU-V2-COMPATIBILITY",
    "P0-RU-V1-HISTORICAL-DENIED",
):
    expect_compatibility_failure(
        f"{name}:unknown",
        synthetic_exact_contract.replace(
            f"<!-- {name}:START -->",
            f"<!-- {name}:START -->\nunknown_compatibility_key: FORBIDDEN",
            1,
        ),
        f"{name}_UNKNOWN_KEY:unknown_compatibility_key",
    )
    mutation_count += 1

expect_compatibility_failure(
    "schema_aliases:conflicting_duplicate",
    synthetic_exact_contract.replace(
        "schema_aliases: NONE",
        "schema_aliases: NONE\nschema_aliases: ALLOWED",
        1,
    ),
    "P0-RU-V2-COMPATIBILITY_DUPLICATE_KEY:schema_aliases",
)
mutation_count += 1
expect_compatibility_failure(
    "positive_current_v1_outside_denied_context",
    synthetic_exact_contract
    + "\nCurrent logical version: request_understanding_record.p0.v1",
    "UNBOUNDED_RU_V1_DECLARATION",
)
mutation_count += 1
assert mutation_count == 30, f"MUTATION_COUNT:{mutation_count}"
print("compatibility_synthetic=PASS")
print("compatibility_mutations=PASS count=30")

def validate(text: str) -> None:
    registry = rows_for(text, "P0-PERSISTENCE-REGISTRY")
    ru_registry = tuple(row for row in registry if row[0] == "RequestUnderstandingRecord")
    if expected_registry_ru not in ru_registry:
        raise AssertionError("MISSING_RU_V2: exact registry row")
    assert not any(
        row[0] == "RequestUnderstandingRecord"
        and (row[2] == "request_understanding_record.p0.v1" or row[5] == "run_id")
        for row in registry
    ), "STALE_RU_V1_IDENTITY_OR_VERSION"
    assert ru_registry == (expected_registry_ru,), "RU_REGISTRY_EXTRA_ROW"
    assert len(registry) == 17, f"REGISTRY_COUNT:{len(registry)}"
    assert tuple(
        row for row in registry if row[0] != "RequestUnderstandingRecord"
    ) == tuple(
        row for row in base_registry if row[0] != "RequestUnderstandingRecord"
    ), "NON_RU_REGISTRY_DRIFT"

    top = rows_for(text, "P0-PERSISTENCE-PROJECTION")
    child = rows_for(text, "P0-PERSISTENCE-CHILD-PROJECTION")
    local = rows_for(text, "P0-PERSISTENCE-LOCAL-CLOSURE")
    assert (len(top), len(child), len(local)) == (70, 8, 11), (
        f"DENOMINATOR:{len(top)}/{len(child)}/{len(local)}"
    )
    assert {row for row in top if row[0] == "RequestUnderstandingRecord"} == expected_ru_top, "RU_TOP_LEVEL_ROWS"
    assert tuple(
        row for row in top if row[0] != "RequestUnderstandingRecord"
    ) == tuple(
        row for row in base_top if row[0] != "RequestUnderstandingRecord"
    ), "NON_RU_TOP_LEVEL_DRIFT"
    assert set(child) == expected_child, "RU_CHILD_ROWS"
    assert set(local) == expected_local, "RU_LOCAL_CLOSURE_ROWS"

    top_ref_count = sum(
        row[2] in {"TOP_LEVEL_P0_REFERENCE", "EXTERNAL_REQUIRED_P0_REFERENCE"}
        for row in top
    )
    child_ref_count = sum(row[2] == "CHILD_TOP_LEVEL_P0_REFERENCE" for row in child)
    assert (top_ref_count, child_ref_count, top_ref_count + child_ref_count) == (46, 3, 49), "REFERENCE_DENOMINATOR"
    actual_reference_keys = reference_keys(top, child)
    assert actual_reference_keys == base_reference_keys | new_reference_keys, "REFERENCE_CLOSURE_SET"

    stale_denominators = (
        "Top-level marker-bounded matrix 恰含 66 行",
        "logical-child matrix 恰含 7 行",
        "66/7/45",
        "66 / 7 / 45",
    )
    assert not any(value in text for value in stale_denominators), "STALE_66_7_DENOMINATOR"
    assert not re.search(r"(?:reference rules?|P0RecordReference)[^\n]{0,48}(?:恰含|exactly|固定为)[^\n]{0,16}\b45\b", text, re.IGNORECASE), "STALE_45_DENOMINATOR"
    validate_compatibility(text)

try:
    validate(base_text)
except AssertionError as error:
    assert str(error) == "MISSING_RU_V2: exact registry row", (
        f"B_CG_NEGATIVE_WRONG_REASON:{error}"
    )
else:
    raise AssertionError("B_CG_NEGATIVE_UNEXPECTED_PASS")

print("B_CG_negative=MISSING_RU_V2: exact registry row")
validate(Path(SPEC).read_text())
print("current_spec=PASS counts=17/70/8/11 refs=49")
PY
git diff --check 327b39da45cdcf564609a5385d52c4264da2c669
uv run pytest</automated>
再执行focused scan，确认v1→v2 migration/backfill/fallback全部显式否定，且cross-file impact只进入handoff。
  </verify>
  <done>四张marker table与49条reference rules机械闭合；v1数据不会被推断为v2；E/F ownership明确，且只有reviewed D+H serial-integration common barrier才可授权其planning/dispatch。</done>
</task>

</tasks>

<verification>

```bash
set -euo pipefail
base_sha=327b39da45cdcf564609a5385d52c4264da2c669
base_tree=49ad0f3f5fc2c0cbe507763aca12bb6825fb7887
owned_file=docs/implementation/e2e01-thin-slice-implementation-spec.md

test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git rev-parse "${base_sha}:$owned_file")" = 538105706f471dabe9cf8964d1026c4abf484356
test "$(git rev-parse "${base_sha}:docs/architecture/intent-design-reference.md")" = 456be9c7d7884e2a58c4d07b867765ed336aa6f5
test "$(git rev-parse "${base_sha}:.planning/phases/01-cycle-1-e2e-01/01-07C-PLAN.md")" = 66a3a974f5d7408239b8ba3691abdb0c1781fa63
test "$(git rev-parse "${base_sha}:.planning/phases/01-cycle-1-e2e-01/01-07G-PLAN.md")" = 72c866f0afac449c7c9970c223c9eb182fb1e780
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-list --count "${base_sha}..HEAD")" -eq 1
test "$(git diff --name-only "${base_sha}...HEAD")" = "$owned_file"
git diff --check "${base_sha}...HEAD"

for exact_required in \
  'P0-RU-V2-COMPATIBILITY:START' \
  'P0-RU-V2-COMPATIBILITY:END' \
  'current_logical_record_version: request_understanding_record.p0.v2' \
  'model_input_schema_version: e2e01-thin-v1' \
  'model_output_schema_version: e2e01-thin-v2' \
  'request_understanding_record.p0.v2' \
  'e2e01-thin-v1' \
  'e2e01-thin-v2' \
  'request_understanding_record_id' \
  'model_input_schema_version' \
  'model_output_schema_version' \
  'contextualization_resolved_source_ref -> message_record' \
  'contextualization_source_message_ref -> message_record' \
  'task_delta_input_source_ref -> message_record' \
  'accepted_delta_task_id -> task_record' \
  'P0-PERSISTENCE-LOCAL-CLOSURE:START' \
  'P0-PERSISTENCE-LOCAL-CLOSURE:END' \
  'schema_aliases: NONE' \
  'schema_fallback: FORBIDDEN' \
  'automatic_v1_to_v2_inference: FORBIDDEN' \
  'automatic_v1_to_v2_migration: FORBIDDEN' \
  'automatic_v1_to_v2_backfill: FORBIDDEN' \
  'global_task_state_version_binding: FORBIDDEN' \
  'parallel_task_state_version_arrays: FORBIDDEN' \
  'P0-RU-V1-HISTORICAL-DENIED:START' \
  'historical_logical_record_version: request_understanding_record.p0.v1' \
  'historical_runtime_status: DENIED_NOT_CURRENT' \
  'P0-RU-V1-HISTORICAL-DENIED:END' \
  'retained_v1_runtime_readiness: BLOCK_WITH_NEW_MIGRATION_PACKET'
do
  rg -F -q -- "$exact_required" "$owned_file"
done
for impact_term in \
  RequestUnderstandingRecord \
  RequestUnderstandingOutput \
  AcceptedTaskDelta \
  candidate_validation \
  accepted_delta_refs \
  schema_version
do
  rg -F -n -- "$impact_term" docs/architecture docs/implementation src tests evals >/dev/null
done
uv run pytest
```

Executor必须先逐字运行Task 2同一个marker parser；它必须报告`compatibility_synthetic=PASS`、`compatibility_mutations=PASS count=30`、`B_CG_negative=MISSING_RU_V2: exact registry row`且当前owner通过，任何mutation意外通过、错误failure reason、B_CG意外通过或current owner失败都`BLOCK`。随后记录exact feature head review。Integrator在合并前再以最新`origin/integration/e2e01-thin`构造overlay，重复parser、focused scan、`git diff --check`与full suite；overlay不rebase、不force-push、不改写已reviewed feature commit。D与H随后必须各自reviewed并由Integrator串行合并；只有记录同时包含两者exact commits / owner blobs的common barrier后，01-07E/F才可planning或dispatch。任一scope drift、count/token mismatch、test failure、owner conflict、单边merge授权或unresolved `CRITICAL / HIGH / MEDIUM`均为`BLOCK`。
</verification>

<source_audit>

| source | item | coverage |
|---|---|---|
| GOAL | E2E01-01/04 Request Understanding durable exact mapping | Task 1–2 |
| REQ | `E2E01-01`, `E2E01-04` | Task 1–2 |
| CONTEXT | 本 Packet 全部冻结 rulings | Task 1–2；无 deferred item |
| RESEARCH | 新外部依赖 / library | `NONE`；沿用现有 owner 与 Markdown parser pattern |

结论：全部 source item `COVERED`，无 scope reduction、无 deferred implementation。
</source_audit>

<success_criteria>

1. Thin Slice owner明确区分input v1、output v2与logical record v2，并保存完整实际closure。
2. Registry / projection / child / local closure精确为17 / 70 / 8 / 11，reference rules精确为49。
3. v1没有自动推断、migration、backfill或read fallback；需要保留数据时明确BLOCK并新增migration Packet。
4. Feature相对固定base只有一个commit和一个owned file，full suite与独立feature/overlay review通过。
5. 01-07D与01-07H均独立reviewed、由Integrator串行合并且D+H exact common barrier已记录后，才允许01-07E/F planning或dispatch；任何单边merge均不授权。
6. Python、codec、Runtime、DB、Eval、Trace reader、Graphify artifact和lifecycle均保持未修改。

</success_criteria>

<output>
Executor不创建Summary或共享State，只按`handoff_format`交接。只有reviewed merge、Integrator post-merge Graphify/source gate和独立status PR才能索引01-07D完成证据；本Plan或owner文档本身不证明实现已完成。
</output>
