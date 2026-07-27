---
phase: 01-cycle-1-e2e-01
plan: 07C
type: execute
wave: 15
depends_on:
  - 01-07B
files_modified:
  - docs/architecture/intent-design-reference.md
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Request Understanding 的 durable aggregate 保存经过确定性校验的 canonical projection，而不是 raw Provider response、Prompt、Token、异常或诊断文本。"
    - "logical record schema version、model input/output schema version 与 Task State concurrency version 是三个独立版本轴；任何一轴不得被另一轴隐式替代或推导。"
    - "持久化闭包能够逐一追溯 contextualization、全部 emitted candidates、每个 candidate 的唯一 validation decision、accepted/rejected 结果以及按 Task / accepted delta 关联的 base/result Task State versions。"
    - "整体 schema-invalid 的模型输出不产生伪造的 canonical RequestUnderstandingRecord；零候选、多候选与部分接受均有闭合且无 dangling reference 的通用语义。"
    - "P0 继续 exact-version-only；unknown、future 或 mismatched logical version fail closed，不做 fallback、best-effort decode、read-time rewrite 或静默 downgrade。"
    - "本 Packet 只裁决 Intent owner 语义，不选择 Thin Slice exact version string，不修改 Python DTO、codec、数据库、Runtime、Eval 或 lifecycle。"
  artifacts:
    - "intent-design-reference.md 中新增或修订的 durable aggregate、版本轴、closure、时间、兼容、迁移与 rollback 规范。"
  key_links:
    - "01-07D 把本 owner 裁决映射为 Thin Slice exact field names / logical version string；01-07E 与 01-07F 分别实现 codec 与 Core DTO。"
    - "01-07D 与 01-07H 只能从 01-07C/01-07G 均 reviewed merge 后形成的共同 exact integration SHA 签发。"
---

# Phase 1 Plan 01-07C｜Request Understanding durable semantic ruling

> **ISSUED OWNER-RULING TASK PACKET / IMPLEMENTATION NOT STARTED**
> 当前源码把模型输出版本 `e2e01-thin-v1` 写入 `RequestUnderstandingRecord.schema_version`，而 persistence codec 又把同一字段解释为 logical record version `request_understanding_record.p0.v1`；现有 durable record 同时缺少 canonical owner 要求的 contextualization、实际 candidates、`created_at` 与可关联的 per-Task base/result version closure。本 Packet 只由 Intent canonical owner 裁决这些通用语义。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 只把 active owner、源码反馈与后续 ownership barrier 转成一个精确 Task Packet。最终 Request Understanding 语义只由 `docs/architecture/intent-design-reference.md` 拥有；本 Plan、`.planning/` 状态与实现现状均不得反向覆盖它。

<objective>
在 Intent canonical owner 中冻结 Request Understanding durable aggregate 的通用闭包、独立版本轴、可信时间、exact-version compatibility 和 migration / rollback 规则。

Purpose: 消除 logical record version 与 model schema version 混用，以及现有持久化最小字段无法重建 / 审计实际 candidate closure 的阻断。

Output: 仅修改 `docs/architecture/intent-design-reference.md` 的一个文档提交。Thin Slice exact mapping、Application codec、Core implementation、数据库和 Runtime 均留给后续独立 Packet。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-cycle-1-e2e-01/01-07B-SUMMARY.md
@docs/architecture/intent-design-reference.md
@docs/architecture/memory-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@PROJECT_DIRECTION.md
@src/mini_agent/core/request_understanding.py
@src/mini_agent/core/task_state.py
@src/mini_agent/core/request_processing.py
@src/mini_agent/application/persistence.py
@src/mini_agent/application/records.py

本 Plan 使用受控 GSD planner / checker adapter，不调用 stock `gsd-plan-phase`、`gsd-execute-phase`、`gsd-verify-work`、lifecycle mutation 或 `gsd-ship`。planning-status PR 必须先 reviewed merge；随后 Integrator 从固定 execution base 建立 feature Worktree，并从 official planning merge 读取本 Plan。Executor 只能写唯一 owned file。
</execution_context>

<packet_contract>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-ru-semantic-ruling`
base_branch: `integration/e2e01-thin`
base_sha: `3f0753f7bef87fc02f314e28fe8b07860a819701`
base_tree: `b5214d3b7140ca305566a9cb802a21388a92464c`
worktree_id: `e2e01-01-ru-semantic-ruling`
writer: `Intent canonical-owner sole writer, supervised by /root Integrator`
agent_role: `gsd-doc-writer`

物理 Worktree path 只由 Integrator 在 private dispatch handoff 中传递，不持久化到公开 Plan 或 PR；公开身份只使用 `worktree_id`。

owned_files:

- `docs/architecture/intent-design-reference.md`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- every other `docs/**` path, including `docs/architecture/memory-design-reference.md` and `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- `src/**`
- `tests/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8
- `docs/architecture/intent-design-reference.md`, especially Request Understanding output, validation, audit and minimum-persistence sections
- `docs/architecture/memory-design-reference.md` exact-version-only, Task State / record ownership and Context Manifest rules
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` as a scoped consumer, not a semantic owner
- current source at `base_sha` as implementation feedback, not normative design

dependencies:

- 01-07B reviewed merge and status alignment exact execution base `3f0753f7bef87fc02f314e28fe8b07860a819701`
- this planning-status PR reviewed merge before any feature write
- `PROJECT_DIRECTION.md` at the planning base still reports the volatile derived count as `16` signed Plans; that active-owner file is outside this planning Packet. The planning PR must record the difference, then a separate Project Direction owner PR must remove or align the volatile count before 01-07G planning or C/G feature dispatch
- 01-07G is a same-wave independent owner ruling from the same `base_sha`; neither C nor G depends on the other
- 01-07D / 01-07H remain blocked until both C and G owner PRs are serially merged and a common exact integration barrier is recorded
- 01-07E / 01-07F remain blocked until the later D/H common barrier

required_checks:

- exact base, tree, branch, merge-base, clean Worktree, planning Plan blob and owner-file byte-identity preflight
- one and only one feature commit relative to `base_sha`
- changed-file set exactly equals `docs/architecture/intent-design-reference.md`
- owner explicitly separates `record_schema_version`, `model_output_schema_version` and Task State concurrency versions; if model input version is audit-relevant, it must have one explicit durable representation or reference rather than an implicit inference
- owner explicitly chooses aggregate identity and retry/replay semantics for `request_understanding_record_id` versus `run_id`; the two identifiers must not be silently conflated
- stored content is a canonical validated projection, never raw Provider payload, Prompt, Token, private reasoning, exception or diagnostic text
- contextualization has one unambiguous durable representation or explicit absence rule consistent with the owner’s Eval / audit requirements
- emitted candidate IDs are unique; persisted validation candidate set exactly equals the emitted candidate set; every candidate has exactly one stable decision
- every `ACCEPT` binds exactly one accepted delta; every `REJECT` has a stable reason and binds no accepted delta
- `accepted_delta_refs` exactly equals the accepted children with no missing, extra, duplicate or dangling reference
- zero-candidate, multi-candidate and partial-accept cases preserve a closed aggregate; Thin Slice’s narrower one-accepted-child rule remains a downstream mapping decision
- base/result Task State versions are keyed by Task identity or accepted delta relationship; no unassociated parallel arrays or one global version may represent multiple candidates / Tasks
- overall schema-invalid output creates no canonical RequestUnderstandingRecord; downstream bounded failure taxonomy remains owned by 01-07I/J/L
- `created_at` is generated by a trusted server UTC clock, cannot come from user/model input, does not refresh on idempotent replay, and has an explicit ordering/equality rule relative to accepted child timestamps
- a breaking durable-shape change requires a new logical record version; the exact P0 string and codec mapping remain owned by 01-07D/E
- exact-version-only semantics reject unknown, future and mismatched versions; no fallback, best-effort decode, read-time rewrite or silent downgrade
- future migration guidance names source/target versions, closure invariants, security/Eval impact, atomic failure behavior and rollback/readiness constraints; an old runtime unable to read a new record cannot be reported ready after rollback
- cross-file impact scan classifies every affected consumer as downstream work, aligned reference, or explicit non-impact; forbidden-file edits stop the Packet
- the known `PROJECT_DIRECTION.md` signed-Plan-count mismatch is explicitly recorded as a deferred owner-boundary alignment, not silently called aligned; execution preflight requires the separate owner PR evidence
- `git diff --check`, focused `rg` owner checks, Markdown frontmatter/local-link checks where applicable, `uv run pytest`, and independent exact-head canonical/ownership/security review
- latest-integration overlay proves the sole owner change remains compatible after the first C/G owner PR is merged; no rebase or force-push rewrites reviewed lineage

done_when:

- canonical Intent owner contains one internally consistent durable aggregate and version-evolution ruling covering all required checks
- one feature commit changes exactly one owned file
- no Thin Slice exact string, Python DTO, codec, SQL, Runtime, Eval or lifecycle change is smuggled into this Packet
- exact feature and latest-integration overlay checks pass
- unresolved `CRITICAL / HIGH / MEDIUM = 0 / 0 / 0`
- draft PR targets `integration/e2e01-thin` and records contract change, nonclaims, checks, risks and rollback
- Project Direction’s volatile signed-Plan count is aligned or removed by a separate reviewed owner PR before 01-07G planning or C/G feature dispatch
- merge does not advance Case / Requirement / numbered Phase lifecycle

contract_changes: `YES / CANONICAL INTENT SEMANTICS` — freezes the durable Request Understanding aggregate, independent version axes, closure and compatibility / migration rules. Exact Thin Slice fields/version strings and all code remain downstream.
security_impact: `YES` — prevents version confusion, forged timestamps, dangling accepted-delta audit state, raw Provider disclosure and fail-open decoding.
eval_impact: `YES / CONTRACT INPUT ONLY` — makes actual contextualization/candidates/validation/version closure durably gradeable; no Dataset, Grader, threshold, Result or lifecycle change.
new_dependencies: `NONE`
graphify_disposition: `INTEGRATOR POST-MERGE SEMANTIC GATE` — feature writer never changes `graphify-out/**`; after merge the Integrator must run the project-supported documentation semantic refresh if available, otherwise record `NOT_RUN` and verify the owner/consumer graph by source scan without claiming semantic graph freshness.
rollback: Close before merge or use a normal revert PR and re-block 01-07D–01-08A. Never reset, force-push, rewrite reviewed history or claim a rollback-ready runtime that cannot read the integration record version.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan blob
- exact one-file feature/overlay containment
- owner decisions for identity, canonical projection, contextualization, closure, timestamps and each independent version axis
- compatibility/migration/rollback matrix
- commands and exact results
- cross-file impact map, contract/security/Eval impact and explicit nonclaims
- separate Project Direction owner-alignment PR/merge evidence for the volatile signed-Plan count
- independent feature/overlay reviews and unresolved risks
</packet_contract>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RUS-S01` | Spoofing | user/model → record identity/time/version | `MITIGATE / BLOCK` | identity、logical version 与 UTC time 由可信代码提供，模型字段不能覆盖 |
| `RUS-T01` | Tampering | candidates/validation → accepted deltas | `MITIGATE / BLOCK` | exact-set closure、每候选唯一 decision 与无 dangling accepted ref |
| `RUS-R01` | Repudiation | model output → Task State mutation | `MITIGATE / BLOCK` | durable canonical projection、model-output version 与 keyed base/result versions 可追溯 |
| `RUS-I01` | Information Disclosure | Provider internals → durable store / Trace | `MITIGATE / BLOCK` | 禁止 raw payload、Prompt、Token、异常、私有推理和不必要 source quote / PII |
| `RUS-D01` | Denial of Service | unknown/future record version → reader | `MITIGATE / BOUNDED` | exact-version fail closed；显式 migration，无 read-time rewrite/retry loop |
| `RUS-E01` | Elevation of Privilege | model candidate → accepted Task mutation | `MITIGATE / BLOCK` | candidate 只是一项提议；确定性 validation 与 accepted binding 闭包不可绕过 |

</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Freeze durable aggregate and independent version axes</name>
  <files>docs/architecture/intent-design-reference.md</files>
  <action>
在现有 Request Understanding canonical owner 内对齐并规范 durable aggregate：定义 identity/replay、canonical validated projection、contextualization、candidate/validation/accepted/rejected closure、按 Task 或 accepted delta 关联的 base/result versions，以及可信 `created_at`。明确 logical record、model input/output 和 Task State concurrency versions 互不替代；不要指定 Thin Slice exact string 或实现字段。
  </action>
  <verify>
    <automated>test "$(git diff --name-only 3f0753f7bef87fc02f314e28fe8b07860a819701...HEAD)" = "docs/architecture/intent-design-reference.md"
rg -n 'request_understanding_record_id|record_schema_version|model.*schema_version|contextualization|task_delta_candidates|candidate_validation|accepted_delta|created_at|base.*state_version|result.*state_version' docs/architecture/intent-design-reference.md >/dev/null</automated>
对照 owner 现有 minimum-persistence 列表与当前 source/codec 冲突，确认所有字段都有唯一语义、cardinality、authority、closure 与 retention/minimization 规则。
  </verify>
  <done>
通用零/一/多候选与部分接受均可闭合审计；invalid overall output 不产生伪 record；不存在 version/timestamp/identity 混用。
  </done>
</task>

<task type="auto">
  <name>Task 2: Freeze compatibility, migration and rollback safety</name>
  <files>docs/architecture/intent-design-reference.md</files>
  <action>
把 breaking-shape evolution、exact-version-only decode、unknown/future/mismatch failure、显式 migration 与 rollback/readiness 约束写入同一 owner。说明 downstream Thin Slice mapping、codec、Core implementation分别由01-07D/E/F消费；不要修改消费者文件。
  </action>
  <verify>
    <automated>git diff --check 3f0753f7bef87fc02f314e28fe8b07860a819701...HEAD
rg -n 'exact-version|unknown|future|fallback|migration|rollback|downgrade' docs/architecture/intent-design-reference.md >/dev/null
uv run pytest</automated>
运行 repository-wide impact scan，特别核对 Memory owner、Thin Slice Spec、PROJECT_DIRECTION、current RU DTO/construction/codec 与 tests；记录差异但不越界修复。
  </verify>
  <done>
owner 规则可让下游实现者唯一判断合法 record、版本兼容与 rollback 条件，且跨 owner 差异被显式列入 handoff。
  </done>
</task>

</tasks>

<verification>

```bash
set -euo pipefail

base_sha=3f0753f7bef87fc02f314e28fe8b07860a819701
base_tree=b5214d3b7140ca305566a9cb802a21388a92464c
owned_file=docs/architecture/intent-design-reference.md

test "$(git rev-parse "${base_sha}^{tree}")" = "$base_tree"
test "$(git merge-base HEAD "$base_sha")" = "$base_sha"
test "$(git rev-list --count "${base_sha}..HEAD")" -eq 1
test "$(git diff --name-only "${base_sha}...HEAD")" = "$owned_file"
git diff --check "${base_sha}...HEAD"

rg -n \
  'request_understanding_record_id|record_schema_version|model.*schema_version|contextualization|task_delta_candidates|candidate_validation|accepted_delta|rejected_candidate|created_at|base.*state_version|result.*state_version|exact-version|compatib|migration|rollback|fallback' \
  "$owned_file"

rg -n \
  'RequestUnderstandingRecord|RequestUnderstandingOutput|schema_version|candidate_validation|created_at|rollback' \
  PROJECT_DIRECTION.md docs/architecture docs/implementation src tests

uv run pytest
```

Planning provenance 与 latest-integration overlay 另按 `<packet_contract>` 记录。任何 required forbidden-file alignment、scope drift、test failure 或 unresolved `CRITICAL / HIGH / MEDIUM` 都是 `BLOCK`。
</verification>

<success_criteria>

1. Intent canonical owner 形成可实现、可审计、fail-closed 的 durable aggregate 与独立版本轴裁决。
2. Feature branch 相对固定 base 只有一个 commit、一个 changed file。
3. Thin Slice exact mapping、codec、Core、数据库、Runtime、Eval 与 lifecycle 均保持未修改。
4. Feature 与 latest-integration overlay 获得独立 exact-head review，阻断级 finding 为零。
5. C/G 串行 merge 后才记录共同 barrier 并签发 01-07D / 01-07H。

</success_criteria>

<output>
完成后不创建 Summary；Executor 按 `handoff_format` 向 Integrator 交接。只有 reviewed merge、post-merge gate 和后续独立 status PR 才能把 01-07C 标记为 `TASK_PACKET_COMPLETE / EVIDENCE_INDEXED`。
</output>
