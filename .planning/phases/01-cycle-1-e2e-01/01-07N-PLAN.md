---
phase: 01-cycle-1-e2e-01
plan: 07N
type: execute
wave: 17
depends_on:
  - 01-07D
  - 01-07H
files_modified:
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "第一薄切片以一个 marker-bounded JSON manifest 冻结 RU v2 model-facing / durable-safe nested shapes、closed rejection enum、failure partition、provenance responsibilities 和 owner-neutral cutover protocol；prose 不维护第二套合同。"
    - "`ResolvedReferenceCandidateV2.source_quote` 在 scoped model output 中必需且为 1..128 Unicode code points；write-time validator 生成 span/hash 后立即丢弃，任何 durable v2 shape 都禁止 raw quote。"
    - "整体 schema/version/trusted-field/provenance invalid 与 CAS/commit/atomic-closure failure 都不形成 durable candidate REJECT；只有完整 safe canonical projection 上的候选级确定性失败使用封闭 rejection enum。"
    - "pure codec 只验证 caller-supplied exact code/version、strict DTO、safe projection 与 local closure；owner-scoped reader 在交付可消费记录前加载 authoritative Message 并重算 span/hash，固定 decode API 不增加 resolver、Repository 或 I/O。"
    - "scoped owner 只冻结 `CORE_EXPAND → CODEC_EXPAND → DEPENDENCY_EXPAND → ACTIVE_SWITCH → CONTRACT` 和 exact temporary API；Packet ID、branch、Worktree、writer、allowlist、分母及集成顺序仍由独立 execution-plan owner 映射。"
    - "01-07N reviewed merge后只授权 single-writer execution-plan alignment Packet；该 alignment reviewed merge前，01-07F/E及其他cutover实现全部BLOCK。"
    - "本 Packet 只修改 Thin Slice scoped owner；不修改 Intent / Memory、multi-agent execution plan、Python、数据库、Eval、planning状态、lifecycle或readiness。"
  artifacts:
    - "docs/implementation/e2e01-thin-slice-implementation-spec.md 中唯一的 P0 RU v2 cutover manifest 与解释性映射。"
  key_links:
    - "01-07N 从 exact `B_DH = 4a7e802...` 执行；01-07D的RU v2 mapping与01-07H的additive Core/Order表示均已reviewed merge。"
    - "01-07N reviewed merge后，独立 execution-plan alignment Packet单写 `docs/implementation/e2e01-thin-slice-multi-agent-plan.md`；其reviewed merge前不得签发F/E。"
---

# Phase 1 Plan 01-07N｜Request Understanding v2 cutover remediation ruling

> **ISSUED SCOPED-CONTRACT REMEDIATION TASK PACKET / IMPLEMENTATION NOT STARTED**
> `B_DH` 已满足原 01-07D/H barrier，但 implementation preflight 证明直接并行签发 E/F 会让实现层发明 nested DTO 与 rejection taxonomy，并在 v1 consumers、single-version codec registry、database CHECK 与 authoritative provenance replay 之间形成不可串行全绿的依赖环。本 Packet 只修复 Thin Slice exact encoding 与 owner-neutral cutover protocol，不拥有执行拆分。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 不拥有产品或 Request Understanding 通用语义。P0 scoped encoding authority 是本 Packet 的唯一 owned file；Intent 与 Memory owners继续拥有上游语义和owner-scoped recovery/readiness，multi-agent plan继续拥有Packet/Worktree/集成顺序。Plan、源码、测试和`.planning/`状态都不能反向覆盖这些owner。

<objective>
在 Thin Slice scoped owner中关闭01-07E/F preflight发现的四类合同阻断：nested exact shape、bounded rejection/failure partition、fixed codec API下的provenance责任，以及不涉及执行所有权的exact expand/switch/contract协议。

Purpose: 为后续single-writer execution-plan alignment提供可机械验证的canonical input，使Core、Application、Infra、Runtime和Eval可以按ownership迁移，不引入optional-v2、fallback、自动migration、跨owner mega-packet或失败full suite。

Output: 恰好一个owner commit，只修改`docs/implementation/e2e01-thin-slice-implementation-spec.md`；不修改multi-agent plan、源码、数据库、Eval、状态或lifecycle。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-07D-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07H-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/implementation/e2e01-thin-slice-multi-agent-plan.md

01-07D/H Summary只从planning provenance捕获，不进入exact `B_DH` execution base。不得调用stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation或`gsd-ship`。不得把当前v1源码行为或本Plan当作canonical owner。
</execution_context>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-v2-cutover-ruling`
base_branch: `integration/e2e01-thin`
base_sha: `4a7e802e8aebc54e0582a1e4d99f140b56e7b131`
base_tree: `a5a60292ccdf116aba4dacaaea366576e183c532`
planning_context_sha: `6b1d21f9459903a097bc147309454562e2f72181`
planning_context_tree: `93d9048d1590af58922a111235fb7fe654a8400c`
worktree_id: `e2e01-01-ru-v2-cutover-ruling`
writer: `Thin Slice scoped-contract sole writer, supervised by /root Integrator`
agent_role: `gsd-doc-writer`

物理Worktree path只由Integrator私下dispatch，不写入Plan、commit或PR。

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
- every other `docs/implementation/**` path
- `docs/evaluation/**`
- `src/**`
- `tests/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- execution base / tree（exact `B_DH`）：`4a7e802e8aebc54e0582a1e4d99f140b56e7b131` / `a5a60292ccdf116aba4dacaaea366576e183c532`
- planning context / tree：`6b1d21f9459903a097bc147309454562e2f72181` / `93d9048d1590af58922a111235fb7fe654a8400c`
- Thin Slice owner blob：`9973767330083e4e69b3d5ae10a768386bad8276`
- Intent owner blob：`456be9c7d7884e2a58c4d07b867765ed336aa6f5`
- 01-07D / 01-07H Plan blobs：`e63b844301f8d74da80bc8a1d01bbf3eea689de8` / `52ffe6652284d75b8f2546d50439762b63dfdfa0`
- planning-context-only 01-07D / 01-07H Summary blobs：`73a161baaad4924c3c913847a63325c27a4d1fcb` / `99b47ea3f9b1faee3a836a3d2d051e0259d47d73`
- Governance / project rules blobs：`bd5c92a7e5369cbeb1d152caa3eed736938e94c4` / `e4742ea091b963e6ff77508d43c8d1c9863f69c1`

dependencies:

- 本Plan的planning-status PR必须先取得独立exact-head `PASS`并reviewed merge；Executor记录official planning commit与本Plan blob。
- feature Worktree必须从固定`base_sha` clean创建；planning commit只作为captured Git object读取，不改变execution base。
- preflight必须证明feature HEAD/tree恰为exact `B_DH`，两个owner、两个predecessor Plan、governance blobs与本Packet一致；Summary只从planning commit捕获。任一drift都`BLOCK`。
- 01-07N reviewed merge前，execution-plan alignment Packet不得planning/dispatch；alignment reviewed merge前，01-07F/E及其他cutover实现一律`BLOCK`。原E/F同base并行路径不能继续使用。
- 本Packet不批准Packet/Worktree映射、physical migration、active switch、legacy contract或readiness；这些只能由后续owner-specific Packet逐项批准。

required_checks:

- exact branch/base/tree/merge-base/clean state、owner/Plan/governance blobs、captured Summary与唯一planning provenance preflight
- 相对exact `B_DH`恰好一个feature commit、changed-file set恰好等于唯一owned file
- 单一bounded JSON manifest parser精确验证model-facing/durable-safe字段、literal、cardinality、conditional rule、ordering与禁止字段
- 同一parser验证closed rejection enum与failure partition；unknown/free text/duplicate/caller reason与错误bucket均fail closed
- 同一parser验证write validator、pure codec与owner-scoped reader恰好三个角色；codec无resolver/Repository/I/O，reader未复验前不得声明content verified
- 同一parser验证owner-neutral stage顺序、exact temporary API、active/non-routable状态与contract gate；manifest不得包含Packet ID、branch、Worktree、writer、allowlist、分母或integration order
- 17个top-level record code保持恰好17；expand active registry仍17，version catalog恰18个exact `(code, version)` entry且只有RU多一个v2 entry
- negative mutations至少覆盖missing field、optional quote、duplicate/unknown reason、错误failure bucket、stage reorder、错误17/18 count、第二个dual-version code与execution-owner字段注入
- local links、术语scan、`git diff --check`与full `uv run pytest`
- repository-wide impact scan记录全部v1 source/test/eval/migration consumers，只记录不修改forbidden files
- independent exact-head canonical/ownership/security review；unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`
- latest-integration overlay不改写feature lineage，重复parser、diff-check、focused scan与full suite

done_when:

- Thin Slice owner对nested DTO、rejection partition、provenance responsibility和owner-neutral cutover形成唯一、可机械验证的合同
- 一个commit只改一个owned file，所有required checks通过
- execution-plan alignment获得完整canonical input；其reviewed merge前所有cutover实现保持BLOCK
- exact feature与latest-integration overlay均通过独立review；draft PR指向`integration/e2e01-thin`

contract_changes: `YES / SCOPED THIN-SLICE CONTRACT` — 补齐P0 RU v2 nested encoding、候选拒绝、provenance责任和owner-neutral exact-version cutover protocol；不改变Intent/Memory通用语义或execution ownership。
security_impact: `YES` — 阻断caller-controlled reason、raw quote持久化、codec越权读取私有消息、未验证span/hash被当作可信provenance、整体invalid伪装为REJECT，以及v1/v2 fallback造成的version confusion。
eval_impact: `YES / CONTRACT INPUT ONLY` — 让contextualization、uncertainty、候选拒绝与provenance verification可重放评分；不修改Dataset、Grader、Result、threshold或Case lifecycle。
new_dependencies: `NONE`
nonclaims: `NO IMPLEMENTATION CLAIM` — 不声称execution-plan alignment、01-07F/E、Python DTO、codec、Runtime、数据库、migration、Trace/Eval reader、Trajectory/E2E Result或P0产品已实现、验证或ready。
graphify_disposition: `INTEGRATOR POST-MERGE SEMANTIC GATE` — feature writer不得修改`graphify-out/**`；reviewed merge后由Integrator运行semantic refresh并核对Intent/Memory→Thin Slice→execution plan关系；无法运行时记录`NOT_RUN`并保持alignment blocked。
rollback: 合并前关闭PR；合并后普通revert PR并重新阻塞execution-plan alignment、01-07F/E及全部cutover实现。不得reset、force-push、保留双版本fallback、自动backfill或用旧源码行为替代owner合同。

handoff_to: `/root Integrator`

handoff_format:

- repository / remote / branch / worktree_id / agent role
- exact base/tree/planning/head/commit/tree、Plan/owner blobs
- exact one-file feature与overlay containment
- manifest hash、nested DTO、reason enum、failure partition、provenance responsibility与owner-neutral cutover
- commands / exact results、cross-file impact、contract/security/Eval impact
- independent feature/overlay reviews、residual risks与rollback
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUC-S01` | Spoofing | Provider/caller → source/authority/version | `MITIGATE / BLOCK` | exact fields、authority重判与caller-supplied exact version；不允许trusted identity |
| `RUC-T01` | Tampering | raw quote/span/hash/dual version → durable record | `MITIGATE / BLOCK` | required bounded quote、authoritative exact match、trusted span/hash、exact catalog key、无fallback |
| `RUC-R01` | Repudiation | candidate rejection → durable audit | `MITIGATE / BLOCK` | keyed closed enum；无free text；aggregate-invalid与commit failure不能伪装成REJECT |
| `RUC-I01` | Information Disclosure | codec/reader → private message | `MITIGATE / BLOCK` | pure codec zero-I/O；owner-scoped reader按可信身份加载且只交付validated projection |
| `RUC-D01` | Denial of Service | malformed shape/version/provenance | `MITIGATE / BOUNDED` | strict cardinality、bounded quote、closed enum与bounded exact-version dispatch |
| `RUC-E01` | Elevation of Privilege | decoded/staged v2 → authority/readiness | `MITIGATE / BLOCK` | codec success只表示structural closure；expand不得进入active writer或ready claim |

</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Freeze exact nested shapes in one manifest</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
在第5.1与第10.1节建立且只建立一次`P0-RU-V2-CUTOVER-MANIFEST` marker-bounded JSON合同；prose只解释manifest。

`ResolvedReferenceCandidateV2`字段恰为`name`、`candidate_value`、`source_kind`、`source_ref`、`source_quote`、`confidence`。`name="order_id"`；source kind为`CURRENT_MESSAGE | RECENT_MESSAGE`；quote必需且1..128 Unicode code points；confidence为0..1；禁止trusted/business字段。

`UncertaintyV2`字段恰为`name`、`candidate_values`、`reason_code`、`source_message_refs`。reason为`MISSING_REFERENCE | MULTIPLE_PLAUSIBLE_REFERENCES`；refs为1..8 unique；missing values恰0，multiple values为2..8 unique；保持emitted order。

`QueryContextualizationCandidateV2`字段恰为`text`、`resolved_reference_candidates`、`uncertainties`、`source_message_refs`；resolved/uncertainties均0..n，refs为1..8 unique且含current message，每个resolved source_ref都在refs中。

`DurableResolvedReferenceCandidateV2`与`DurableInputCandidateV2`按manifest exact fields保存安全投影；raw quote一律`FORBIDDEN`。direct-binding type names恰为`RequestUnderstandingOutputV2`、`CandidateValidationRecordV2`、`AcceptedTaskDeltaV2`、`RequestUnderstandingRecordV2`。现有v1 classes在expand期保持不变，不使用alias、union或optional-v2 field。
  </action>
  <verify>
    <automated>set -euo pipefail
spec=docs/implementation/e2e01-thin-slice-implementation-spec.md
git diff --check 4a7e802e8aebc54e0582a1e4d99f140b56e7b131 -- "$spec"
test "$(rg -Fxc '<!-- P0-RU-V2-CUTOVER-MANIFEST:START -->' "$spec")" -eq 1
test "$(rg -Fxc '<!-- P0-RU-V2-CUTOVER-MANIFEST:END -->' "$spec")" -eq 1</automated>
  </verify>
  <done>单一manifest拥有model-facing与durable-safe exact shape；scoped raw quote必需，durable raw quote禁止。</done>
</task>

<task type="auto">
  <name>Task 2: Close rejection, failures and provenance responsibility</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
同一manifest中的`candidate_rejection_reason_codes`按顺序恰为：

`OPERATION_NOT_SUPPORTED`、`GOAL_PATCH_NOT_ACTIONABLE`、`REQUIRED_INPUT_MISSING`、`INPUT_VALUE_INVALID`、`REFERENCE_UNRESOLVED`、`REFERENCE_AMBIGUOUS`、`NEXT_MOVE_INCONSISTENT`。

`failure_partition`恰含三组：整体schema/version/trusted/provenance失败进入`aggregate_invalid_no_record`；上述七码进入`candidate_reject`；CAS、Task commit、durable closure commit失败进入`atomic_failure_no_record`。不得跨bucket或写caller text。

`provenance_responsibilities`恰含`WRITE_VALIDATOR`、`PURE_CODEC`、`OWNER_SCOPED_READER`三个有序角色。前者owner-scoped读取authoritative Message、exact unique quote match、生成span/hash并丢弃raw；codec只做exact code/version dispatch、strict DTO、safe projection/local closure和zero-I/O；reader按trusted owner重读Message、检查bounds/hash并在交付前fail closed。四个authority state互不替代。
  </action>
  <verify>
    <automated>set -euo pipefail
spec=docs/implementation/e2e01-thin-slice-implementation-spec.md
! git diff --unified=0 4a7e802e8aebc54e0582a1e4d99f140b56e7b131 -- "$spec" | rg -n 'decode_persistence_record\\([^)]*(resolver|repository)'
rg -F -q 'CandidateRejectionReasonCode' "$spec"
rg -F -q 'owner-scoped strict reader' "$spec"</automated>
  </verify>
  <done>candidate REJECT、aggregate-invalid、atomic failure和三段provenance责任封闭且互不冒充。</done>
</task>

<task type="auto">
  <name>Task 3: Freeze owner-neutral cutover and run exact gates</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md</files>
  <action>
同一manifest只冻结owner-neutral协议：

1. stages恰为`CORE_EXPAND → CODEC_EXPAND → DEPENDENCY_EXPAND → ACTIVE_SWITCH → CONTRACT`。
2. active registry保持17个code；immutable version catalog概念恰18个`(code, version)` entry，只有`request_understanding_record`拥有v1/v2两项。
3. versioned codec API恰为`encode_persistence_record_versioned`和`decode_persistence_record_versioned`；caller必须同时给`record_code`与`schema_version`。
4. 禁止version inference、alias、union、default/latest、try-other-version、read-time rewrite、backfill/reconstruction与expand active routing。
5. v1缺失contextualization/candidates/model versions/keyed effects时不可推断或升级；存在未隔离current v1 row时active switch/contract/readiness失败。Core v1 surface最后contract。
6. manifest显式禁止execution-owner字段；另一个single-writer alignment Packet负责Packet/branch/Worktree/writer/allowlist/分母/integration mapping，其reviewed merge前不执行任何stage。

运行下述同一个exact-equality parser、10类negative mutation、17/18 denominator检查、full suite、impact scan和independent review。
  </action>
  <verify>
    <automated>set -euo pipefail
base_sha=4a7e802e8aebc54e0582a1e4d99f140b56e7b131
spec=docs/implementation/e2e01-thin-slice-implementation-spec.md
test "$(git merge-base "$base_sha" HEAD)" = "$base_sha"
test "$(git rev-list --count "$base_sha..HEAD")" -eq 1
test "$(git diff --name-only "$base_sha...HEAD" | LC_ALL=C sort)" = "$spec"
git diff --check "$base_sha"...HEAD
uv run python - <<'PY'
import copy
import json
import re
from pathlib import Path

SPEC = Path("docs/implementation/e2e01-thin-slice-implementation-spec.md")
START = "<!-- P0-RU-V2-CUTOVER-MANIFEST:START -->"
END = "<!-- P0-RU-V2-CUTOVER-MANIFEST:END -->"
expected = {
    "manifest_version": "p0-ru-v2-cutover-r1",
    "model_types": {
        "ResolvedReferenceCandidateV2": {
            "fields": ["name", "candidate_value", "source_kind", "source_ref", "source_quote", "confidence"],
            "rules": ["name=order_id", "candidate-value=non-empty-string", "source-kind=CURRENT_MESSAGE|RECENT_MESSAGE", "source-quote=required:1..128-unicode-code-points", "confidence=0..1", "forbid-trusted-and-business-fields"],
        },
        "UncertaintyV2": {
            "fields": ["name", "candidate_values", "reason_code", "source_message_refs"],
            "rules": ["name=order_id", "reason=MISSING_REFERENCE|MULTIPLE_PLAUSIBLE_REFERENCES", "missing-values=0", "multiple-values=2..8-unique", "source-message-refs=1..8-unique", "preserve-emitted-order"],
        },
        "QueryContextualizationCandidateV2": {
            "fields": ["text", "resolved_reference_candidates", "uncertainties", "source_message_refs"],
            "rules": ["text=non-empty-string", "resolved=0..n", "uncertainties=0..n", "source-message-refs=1..8-unique-includes-current", "resolved-source-ref-in-source-message-refs"],
        },
    },
    "durable_types": {
        "DurableResolvedReferenceCandidateV2": {
            "fields": ["name", "candidate_value", "source_kind", "source_ref", "source_span_start", "source_span_end_exclusive", "source_quote_sha256", "confidence"],
            "raw_source_quote": "FORBIDDEN",
        },
        "DurableInputCandidateV2": {
            "fields": ["name", "candidate_value", "semantic_role", "authority", "source_kind", "source_ref", "source_span_start", "source_span_end_exclusive", "source_quote_sha256", "confidence"],
            "raw_source_quote": "FORBIDDEN",
        },
        "direct_binding_types": ["RequestUnderstandingOutputV2", "CandidateValidationRecordV2", "AcceptedTaskDeltaV2", "RequestUnderstandingRecordV2"],
    },
    "candidate_rejection_reason_codes": ["OPERATION_NOT_SUPPORTED", "GOAL_PATCH_NOT_ACTIONABLE", "REQUIRED_INPUT_MISSING", "INPUT_VALUE_INVALID", "REFERENCE_UNRESOLVED", "REFERENCE_AMBIGUOUS", "NEXT_MOVE_INCONSISTENT"],
    "failure_partition": {
        "aggregate_invalid_no_record": ["MODEL_INPUT_SCHEMA_INVALID", "MODEL_OUTPUT_SCHEMA_INVALID", "MODEL_SCHEMA_VERSION_INVALID", "TRUSTED_OR_PRIVATE_FIELD_PRESENT", "SOURCE_PROVENANCE_INVALID"],
        "candidate_reject": ["OPERATION_NOT_SUPPORTED", "GOAL_PATCH_NOT_ACTIONABLE", "REQUIRED_INPUT_MISSING", "INPUT_VALUE_INVALID", "REFERENCE_UNRESOLVED", "REFERENCE_AMBIGUOUS", "NEXT_MOVE_INCONSISTENT"],
        "atomic_failure_no_record": ["TASK_STATE_CAS_CONFLICT", "TASK_COMMIT_FAILED", "DURABLE_CLOSURE_COMMIT_FAILED"],
    },
    "provenance_responsibilities": {
        "WRITE_VALIDATOR": ["owner-scoped-authoritative-message-read", "exact-unique-quote-match", "derive-span-and-sha256", "discard-raw-quote"],
        "PURE_CODEC": ["exact-code-version-dispatch", "strict-dto-validation", "safe-projection-and-local-closure-only", "zero-io"],
        "OWNER_SCOPED_READER": ["trusted-owner-message-read", "span-bounds-check", "exact-slice-sha256-recheck", "fail-closed-before-consumption"],
    },
    "authority_states": ["codec-decode-success", "provenance-content-verified", "owner-graph-complete", "business-fact-evidence-or-authorization"],
    "cutover": {
        "stages": ["CORE_EXPAND", "CODEC_EXPAND", "DEPENDENCY_EXPAND", "ACTIVE_SWITCH", "CONTRACT"],
        "active_registry_code_count": 17,
        "version_catalog_entry_count": 18,
        "dual_version_record_codes": ["request_understanding_record"],
        "versioned_codec_apis": ["encode_persistence_record_versioned", "decode_persistence_record_versioned"],
        "caller_must_supply": ["record_code", "schema_version"],
        "forbidden_behaviors": ["version-inference", "alias", "union-version-field", "default-or-latest", "try-other-version", "read-time-rewrite", "backfill-or-reconstruction", "expand-path-active-routing"],
        "legacy_data": {"inferable": False, "backfill": False, "active_switch_requires_current_v1_isolation": True},
        "execution_owner_fields_forbidden": ["packet_id", "branch", "worktree", "writer", "allowlist", "denominator", "integration_order"],
    },
}

def wrap(value):
    return f"{START}\n```json\n{json.dumps(value, indent=2)}\n```\n{END}"

def parse_contract(text):
    assert text.count(START) == 1 and text.count(END) == 1
    match = re.search(
        re.escape(START) + r"\n```json\n(?P<body>.*?)\n```\n" + re.escape(END),
        text,
        re.S,
    )
    assert match is not None
    actual = json.loads(match.group("body"))
    assert actual == expected
    return actual

source = SPEC.read_text()
manifest = parse_contract(source)
mutants = []
item = copy.deepcopy(expected); item["model_types"]["ResolvedReferenceCandidateV2"]["fields"].remove("confidence"); mutants.append(item)
item = copy.deepcopy(expected); item["model_types"]["ResolvedReferenceCandidateV2"]["rules"][3] = "source-quote=optional"; mutants.append(item)
item = copy.deepcopy(expected); item["candidate_rejection_reason_codes"].append("INPUT_VALUE_INVALID"); mutants.append(item)
item = copy.deepcopy(expected); item["candidate_rejection_reason_codes"].append("UNKNOWN"); mutants.append(item)
item = copy.deepcopy(expected); item["failure_partition"]["candidate_reject"].append("SOURCE_PROVENANCE_INVALID"); mutants.append(item)
item = copy.deepcopy(expected); item["cutover"]["stages"].reverse(); mutants.append(item)
item = copy.deepcopy(expected); item["cutover"]["active_registry_code_count"] = 18; mutants.append(item)
item = copy.deepcopy(expected); item["cutover"]["version_catalog_entry_count"] = 17; mutants.append(item)
item = copy.deepcopy(expected); item["cutover"]["dual_version_record_codes"].append("task_record"); mutants.append(item)
item = copy.deepcopy(expected); item["cutover"]["packet_id"] = "01-07F"; mutants.append(item)
for mutant in mutants:
    try:
        parse_contract(wrap(mutant))
    except (AssertionError, json.JSONDecodeError):
        continue
    raise AssertionError("mutation unexpectedly accepted")

registry = re.search(
    r"<!-- P0-PERSISTENCE-REGISTRY:START -->\n(?P<body>.*?)\n"
    r"<!-- P0-PERSISTENCE-REGISTRY:END -->",
    source,
    re.S,
)
assert registry is not None
rows = [line for line in registry.group("body").splitlines() if line.startswith("| `")]
assert len(rows) == 17
assert manifest["cutover"]["active_registry_code_count"] == len(rows)
assert manifest["cutover"]["version_catalog_entry_count"] == len(rows) + 1
print("ru_v2_manifest=PASS mutations=10 registry=17 catalog=18")
PY
uv run pytest
rg -n 'RequestUnderstanding(Output|Record)|e2e01-thin-v1|request_understanding_record\\.p0\\.v1|source_quote|decode_persistence_record|ck_p0_records_code_version_closed' docs src tests evals alembic .planning >/dev/null</automated>
  </verify>
  <done>manifest exact equality、10类negative mutation、17/18 counts、one-file containment、full suite、impact scan与independent review通过；只授权execution-plan alignment。</done>
</task>

</tasks>

<verification>

- exact `B_DH` base/tree与captured planning/owner blobs全部匹配
- changed files = `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- commit count = 1；commit subject = `docs(01-07N): freeze RU v2 cutover manifest`
- exact manifest parser报告`ru_v2_manifest=PASS mutations=10 registry=17 catalog=18`
- `git diff --check`
- `uv run pytest`
- independent exact-head与latest-integration overlay review为`PASS / 0/0/0/0`
- PR template如实记录contract/security/Eval impact、未执行项、nonclaims、risk与rollback

</verification>

<success_criteria>

- Thin Slice scoped owner已关闭阻断RU v2 staged implementation的四类合同缺口。
- 未修改execution owner、通用owner、源码、数据库、Eval或lifecycle，未批准fallback、active switch或ready claim。
- reviewed merge与Graphify semantic gate完成后只签发single-writer execution-plan alignment；其reviewed merge前F/E继续BLOCK。

</success_criteria>
