---
phase: 01-cycle-1-e2e-01
plan: 04F
type: execute
wave: 7
depends_on:
  - 01-04E
files_modified:
  - docs/implementation/e2e01-thin-slice-implementation-spec.md
  - evals/model_scripts/e2e01-thin-slice.v1.json
  - evals/cases/e2e01-thin-slice.v1.json
  - evals/manifests/e2e01-thin-slice.v1.json
  - tests/component/evaluation/test_e2e01_artifact_consistency.py
  - tests/component/model/test_e2e01_scripted_scenario_catalog.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "A normal ScriptedModelProvider returns canonical RequestUnderstandingOutput with base_task_state_version=null for the first new goal."
    - "The stale-state gate fault is injected after canonical output and state revalidation, before the Gate decision, through RuntimeRecordPort.apply_task_transition_if_current with an ACTIVE/v1 to WAITING_USER/v2 Task and RequestUnit transition."
    - "That race yields GATE_REJECTED with exact GateReasonCode.STATE_VERSION_MISMATCH and never creates a ToolCall."
    - "Gateway rejection then uses the current WAITING_USER/v2 projection for a second canonical transition to BLOCKED/v3; total version delta is 2 and total TaskStateChanged count is 3 including initial creation."
    - "The stale-state script has its own CONTROL_GATEWAY_STALE_STATE_REJECTED trace variant; unknown-tool rejection remains in CONTROL_GATEWAY_REJECTED with its existing two TaskStateChanged events."
    - "Fact-bearing raw presentation output fails the Provider/Pydantic boundary as PROVIDER_PROTOCOL_ERROR; no PresentationPlanProposed event and no Renderer call occur."
    - "No model_construct, shadow DTO, copied contract or noncanonical object is permitted."
    - "The correction is an explicit pre-executable contract bug fix: no Baseline or Eval Result exists, Case lifecycle stays CONTRACT_DEFINED, and manifest hashes are recalculated from exact bytes."
  artifacts:
    - "Thin Slice Spec states the exact injection boundaries and error mappings."
    - "Model-script and Case artifacts contain only paths contractually implementable through frozen strict DTOs and Ports."
    - "The version manifest pins corrected exact artifact bytes."
    - "Two Component tests mechanically reject recurrence of the impossible paths."
  key_links:
    - "Valid provider output → post-revalidation canonical Task/RequestUnit transition → Control Gateway → STATE_VERSION_MISMATCH → canonical BLOCKED transition."
    - "Fact-bearing raw provider envelope → strict PresentationPlan validation failure → ProviderProtocolError → zero PresentationPlanProposed."
    - "Case trace variants and model-script expected_control_result use the same stop reason and event counts."
    - "Every script ref belongs to exactly one trace variant; stale-state and unknown-tool scripts do not share an incompatible event-count assertion."
---

<objective>
修正两条 versioned Eval fault scenario 与 frozen strict DTO 不可同时成立的 Thin Slice scoped contract。

Purpose: 让 01-05 Runtime 与 01-07 Eval 取得同一条可由 canonical DTO / Port 实现的故障契约，而不添加测试后门或第二套 DTO；本 Packet 不产生实际 Runtime 可达性证据。

Output: 一个 scoped implementation owner、两个 versioned semantic artifacts（Case、model script）、一个 version manifest和两个现有 consistency tests；共三个 JSON 文件，不修改 Core/Application DTO、Runtime、Provider Adapter 或 Harness。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-04E-PLAN.md
@docs/architecture/intent-design-reference.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@src/mini_agent/core/request_understanding.py
@src/mini_agent/core/presentation.py
@src/mini_agent/core/tool_system.py
@src/mini_agent/application/ports.py

本 Plan 使用受控 GSD planner / checker adapter。Integrator 已预建独立 execution Worktree；executor 只能修改 exact six-file allowlist。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-eval-contract-alignment`
base_branch: `integration/e2e01-thin`
base_sha: `a84d30188eaec75e45619e9939180ba78efa3b80`
worktree_id: `e2e01-01-eval-contract-alignment`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-01-eval-contract-alignment`
writer: `Thin Slice scoped owner / Eval-artifact alignment sole writer, supervised by /root Integrator`
agent_role: `eval-engineer`

owned_files:

- `docs/implementation/e2e01-thin-slice-implementation-spec.md`
- `evals/model_scripts/e2e01-thin-slice.v1.json`
- `evals/cases/e2e01-thin-slice.v1.json`
- `evals/manifests/e2e01-thin-slice.v1.json`
- `tests/component/evaluation/test_e2e01_artifact_consistency.py`
- `tests/component/model/test_e2e01_scripted_scenario_catalog.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- all other active owner docs
- `src/**`
- every other test file
- all other `evals/**` artifacts, including fixture and lane files
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8 and graphify
- `.planning/GOVERNANCE.md` owner mapping, Task Packet and lifecycle gates
- `docs/architecture/intent-design-reference.md` new-goal base-version validation
- `docs/architecture/tool-calling-design-reference.md` Gateway and `STATE_VERSION_MISMATCH`
- `docs/architecture/memory-design-reference.md` Task status/version semantics
- `docs/evaluation/agent-evaluation-strategy.md` as read-only Eval method owner
- `docs/evaluation/p0-eval-coverage-matrix.md` as read-only Case/lifecycle owner
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` scoped Eval data/command contract at exact `base_sha`
- `src/mini_agent/core/request_understanding.py`, `src/mini_agent/core/task_state.py`, `src/mini_agent/core/presentation.py`, `src/mini_agent/core/trace.py`, `src/mini_agent/core/tool_system.py` and `src/mini_agent/application/ports.py` at exact `base_sha`

dependencies:

- exact execution base / 01-04D merge `a84d30188eaec75e45619e9939180ba78efa3b80`
- 01-04E Memory owner PR and its Integrator-owned Graphify gate must complete before any 01-04F implementation write; executor captures that official integration SHA, proves all six F-owned files are byte-identical to `base_sha`, and reads the merged E contract through Git even though this disjoint branch retains `base_sha`
- before PR readiness, the complete F branch must revalidate against the latest integration head containing E
- the planning-status PR containing this Plan must merge before implementation writing starts
- executor captures planning merge / Plan blob from the official ref and proves all six owned files were unchanged by planning

required_checks:

- exact base, branch, merge-base and clean-worktree preflight
- RED tests construct the canonical DTOs and prove current stale/fact-bearing expectations are unreachable
- model-script catalog uses a valid provider step plus an explicit Runtime race descriptor for stale state
- exact `STATE_VERSION_MISMATCH` replaces the current OPEN reason
- fact-bearing presentation is a raw-envelope protocol violation with `PROVIDER_PROTOCOL_ERROR`, zero proposed-plan events and zero renderer calls
- Case trace variants cover every script ref exactly once after removing the impossible gate-rejected presentation variant
- manifest SHA-256 values equal exact corrected Case and script bytes
- JSON parse, focused artifact tests, complete `uv run pytest`, exact-file formatting/lint, compileall and `git diff --check`
- six-file containment, active cross-file impact scan and independent exact-head review
- after merge, Integrator-only Graphify AST plus controlled semantic refresh and freshness/health check before 01-04G

done_when:

- exact six-file Packet has one reviewed feature commit
- no impossible canonical-object path remains in Spec, Case, script or tests
- focused/full regressions pass
- draft PR targets `integration/e2e01-thin`, is integrated after 01-04E and does not advance lifecycle

contract_changes: `YES / PRE-EXECUTABLE THIN-SLICE EVAL CONTRACT BUG FIX`
security_impact: `YES` — removes DTO bypass pressure and preserves fail-closed Provider/Gateway boundaries.
eval_impact: `YES / ARTIFACT EXPECTATION CORRECTION` — no Case result or Baseline exists; lifecycle remains `CONTRACT_DEFINED`.
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer does not modify `graphify-out/**`; after merge the Integrator runs `graphify update .`, performs the established controlled semantic re-extraction for the changed Thin Slice owner, verifies graph structure/freshness and a clean tracked tree, and blocks 01-04G on failure.
rollback: Close before merge or use a normal revert PR after merge; re-block Runtime/Eval before reverting. No reset, force-push or artifact history deletion.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan blob
- exact six-file containment
- RED/GREEN commands and strict DTO reachability evidence
- old/new script refs, canonical transition matrix, versions/deltas/event counts and stop reasons
- Case/script SHA-256 values and exact manifest entries
- focused/full results, contract/security/Eval impact and lifecycle nonclaim
- independent exact-head review, post-merge Graphify disposition, unresolved risks and rollback
</task_packet>

<interfaces>

Stale-state scenario target:

```text
ScriptedModelProvider
  → valid RequestUnderstandingOutput
  → NextMove.base_task_state_version = null
Reducer
  → Task / RequestUnit ACTIVE / state_version = 1
Runtime deterministic fault seam
  → boundary = AFTER_REVALIDATION_BEFORE_GATE
  → ApplyTaskTransitionCommand
  → RuntimeRecordPort.apply_task_transition_if_current
  → Task / RequestUnit ACTIVE/v1 → WAITING_USER/v2
  → TaskStateChanged
Control Gateway
  → validated_task_state_version = 1
  → current_task_state_version = 2
  → state_version_valid = false
  → reason_code = STATE_VERSION_MISMATCH
  → GATE_REJECTED
  → ToolCall count = 0
Rejection state handler
  → ApplyTaskTransitionCommand
  → Task / RequestUnit WAITING_USER/v2 → BLOCKED/v3
  → TaskStateChanged
```

Artifact representation must use:

- model script ref: `script:fault-runtime:state-advanced-before-gate`
- provider step behavior: `VALID_ORDER_LOOKUP`
- a separate runtime fault descriptor with behavior `ADVANCE_TASK_STATE_AFTER_REVALIDATION_BEFORE_GATE`
- `transition_port: RuntimeRecordPort.apply_task_transition_if_current`
- `from_status: ACTIVE`
- `to_status: WAITING_USER`
- `validated_task_state_version: 1`
- `current_task_state_version: 2`
- `terminal_task_state_version: 3`
- `task_state_version_delta: 2`
- `request_unit_state_version_delta: 2`
- `TaskStateChanged` exact count `3`（initial creation + injected transition + rejection-to-blocked）
- exact confirmed reason `STATE_VERSION_MISMATCH`
- move the stale script into a dedicated `CONTROL_GATEWAY_STALE_STATE_REJECTED` Case trace variant with `TaskStateChanged == 3` and `GateDecisionRecorded == 1`
- keep `script:fault-provider:unknown-tool-name` alone in the existing `CONTROL_GATEWAY_REJECTED` variant with its existing `TaskStateChanged == 2` and `GateDecisionRecorded == 1`

The injected transition must update both Task and RequestUnit through one canonical `ApplyTaskTransitionCommand`, carry an opaque UUID `reason_ref`, and persist/emit its matching `TaskStateChanged`. If the conditional write is not `APPLIED`, the lane records an Eval execution failure instead of fabricating a Gateway result. Direct in-memory version mutation is forbidden.

Presentation raw-envelope target:

```text
raw function arguments contain a forbidden fact/free-text field
  → strict PresentationPlan Pydantic validation fails
  → fresh parameterless ProviderProtocolError
  → PROVIDER_PROTOCOL_ERROR
  → PresentationPlanProposed count = 0
  → Renderer count = 0
```

Artifact representation must use:

- model script ref: `script:fault-presentation:fact-bearing-envelope`
- behavior: `INJECT_FACT_BEARING_PRESENTATION_ENVELOPE`
- the script belongs to the existing `PRESENTATION_PROTOCOL_REJECTED` trace variant
- remove the now-empty/impossible `PRESENTATION_PLAN_GATE_REJECTED` trace variant

</interfaces>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `EVAL-T01` | Tampering | Scripted Provider → canonical DTO | `MITIGATE / BLOCK` | tests forbid model_construct, shadow objects and invalid canonical returns |
| `EVAL-S01` | Spoofing | fault script → Runtime state | `MITIGATE / BLOCK` | state advance occurs only through canonical ApplyTaskTransitionCommand + RuntimeRecordPort, updates Task/RequestUnit together and emits Trace; direct version mutation is forbidden |
| `EVAL-R01` | Repudiation | artifact → manifest | `MITIGATE / BLOCK` | exact bytes are pinned by recalculated SHA-256 and classified as a pre-executable bug fix |
| `EVAL-I01` | Information Disclosure | raw presentation output → Trace | `MITIGATE / BLOCK` | raw body/facts are discarded before bounded error; proposed-plan count stays zero |
| `EVAL-E01` | Elevation of Privilege | invalid DTO → Gate | `MITIGATE / BLOCK` | only canonical Pydantic output can reach Gateway/Presentation Gate |

</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — prove both artifact paths contradict frozen DTOs</name>
  <files>tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/model/test_e2e01_scripted_scenario_catalog.py</files>
  <read_first>AGENTS.md, docs/implementation/e2e01-thin-slice-implementation-spec.md, src/mini_agent/core/request_understanding.py, src/mini_agent/core/presentation.py, src/mini_agent/core/tool_system.py, src/mini_agent/application/ports.py, evals/cases/e2e01-thin-slice.v1.json, evals/model_scripts/e2e01-thin-slice.v1.json, tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/model/test_e2e01_scripted_scenario_catalog.py</read_first>
  <action>Add assertions that a non-null first-new-goal base version fails RequestUnderstandingOutput validation and a fact-bearing raw Presentation payload fails strict PresentationPlan validation. Add desired artifact assertions for the exact target representation in the interfaces block, including the canonical ACTIVE/v1 → WAITING_USER/v2 → BLOCKED/v3 chain, delta 2, the dedicated stale-state variant with three TaskStateChanged events, and the unchanged unknown-tool variant with two. Run the two focused files before artifact changes and record failure due to current expectations, not syntax/import errors.</action>
  <verify>`uv run pytest tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/model/test_e2e01_scripted_scenario_catalog.py -x` must fail on the new alignment assertions before GREEN changes.</verify>
  <acceptance_criteria>
    - canonical validation failures are reproduced with public Pydantic APIs
    - no test uses model_construct, model_copy update bypass, dict return or shadow DTO
    - RED identifies both current unreachable expected stop reasons
  </acceptance_criteria>
  <done>The two contradictions are executable test evidence rather than planning inference.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — align stale-state race at the Runtime/Gateway boundary</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md, evals/model_scripts/e2e01-thin-slice.v1.json, evals/cases/e2e01-thin-slice.v1.json, tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/model/test_e2e01_scripted_scenario_catalog.py</files>
  <read_first>AGENTS.md, docs/architecture/intent-design-reference.md, docs/architecture/tool-calling-design-reference.md, docs/implementation/e2e01-thin-slice-implementation-spec.md, src/mini_agent/core/request_understanding.py, src/mini_agent/core/tool_system.py, evals/model_scripts/e2e01-thin-slice.v1.json, evals/cases/e2e01-thin-slice.v1.json, tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/model/test_e2e01_scripted_scenario_catalog.py</read_first>
  <action>Apply the exact stale-state representation from the interfaces block. Provider output stays valid and null-based. Rename the script ref, update every bidirectional Case reference, set the exact confirmed Gate reason, and document that Harness activates a Runtime-only post-revalidation/pre-Gate seam by submitting an exact ApplyTaskTransitionCommand through RuntimeRecordPort. Freeze ACTIVE/v1 → WAITING_USER/v2 as the injected transition, WAITING_USER/v2 → BLOCKED/v3 as the rejection transition, version deltas 2 and exact TaskStateChanged count 3. Split the stale script into `CONTROL_GATEWAY_STALE_STATE_REJECTED`; leave unknown-tool alone in `CONTROL_GATEWAY_REJECTED` with count 2. Remove old `INJECT_STALE_TASK_STATE_VERSION` and `OPEN_NOT_FOUND_IN_ACTIVE_TOOL_OWNER` occurrences.</action>
  <verify>`rg -n "INJECT_STALE_TASK_STATE_VERSION|OPEN_NOT_FOUND_IN_ACTIVE_TOOL_OWNER" docs/implementation/e2e01-thin-slice-implementation-spec.md evals tests/component/evaluation/test_e2e01_artifact_consistency.py tests/component/model/test_e2e01_scripted_scenario_catalog.py` returns no match; exact new ref/behavior/reason appear in Spec, artifacts and tests.</verify>
  <acceptance_criteria>
    - provider step is `VALID_ORDER_LOOKUP`
    - proposed base version remains null
    - Runtime fault descriptor records the Port, both statuses, versions 1 and 2, opaque reason correlation and conditional APPLIED requirement
    - expected stop reason is GATE_REJECTED with STATE_VERSION_MISMATCH
    - terminal Task/RequestUnit version is 3, both deltas are 2 and TaskStateChanged count is 3
    - stale-state and unknown-tool scripts are in separate variants with counts 3 and 2 respectively
    - ToolCall/order-read/Observation counts remain zero
  </acceptance_criteria>
  <done>The versioned artifacts specify a stale-state path implementable through canonical DTO/Port boundaries; Runtime/Harness execution remains unimplemented.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: GREEN / REFACTOR — align fact-bearing raw presentation and manifest hashes</name>
  <files>docs/implementation/e2e01-thin-slice-implementation-spec.md, evals/model_scripts/e2e01-thin-slice.v1.json, evals/cases/e2e01-thin-slice.v1.json, evals/manifests/e2e01-thin-slice.v1.json, tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/model/test_e2e01_scripted_scenario_catalog.py</files>
  <read_first>AGENTS.md, docs/business-capabilities.md, docs/implementation/e2e01-thin-slice-implementation-spec.md, src/mini_agent/core/presentation.py, src/mini_agent/application/ports.py, evals/model_scripts/e2e01-thin-slice.v1.json, evals/cases/e2e01-thin-slice.v1.json, evals/manifests/e2e01-thin-slice.v1.json, tests/component/evaluation/test_e2e01_artifact_consistency.py, tests/component/model/test_e2e01_scripted_scenario_catalog.py</read_first>
  <action>Apply the exact presentation representation from the interfaces block. Move the renamed fact-bearing raw-envelope script into PRESENTATION_PROTOCOL_REJECTED, set PROVIDER_PROTOCOL_ERROR, require zero PresentationPlanProposed and renderer calls, and remove the impossible gate-rejected variant. Recalculate SHA-256 for the exact Case and script bytes and update only their two manifest entries. Document why v1 is corrected in place: explicit bug fix before EXECUTABLE/Baseline/Result, with Git/PR and hashes providing audit history; do not change lifecycle or claim a run.</action>
  <verify>Parse exactly `evals/model_scripts/e2e01-thin-slice.v1.json`, `evals/cases/e2e01-thin-slice.v1.json` and `evals/manifests/e2e01-thin-slice.v1.json`; run the two focused tests plus `uv run pytest`; independently compute `shasum -a 256` for the Case/script files and compare to their two manifest entries; run exact-file ruff check/format, compileall and `git diff --check`.</verify>
  <acceptance_criteria>
    - fact-bearing raw output maps to PROVIDER_PROTOCOL_ERROR
    - PresentationPlanProposed count is zero and Renderer count is zero
    - every script ref is covered exactly once by a Case trace variant
    - manifest hashes match exact bytes
    - Case lifecycle remains CONTRACT_DEFINED and no result/baseline flag changes
    - changed files are exactly the six-file allowlist
  </acceptance_criteria>
  <done>All corrected artifacts are strict, internally closed and byte-pinned.</done>
</task>

</tasks>

<verification>

1. Prove exact base/planning provenance and six-file containment.
2. Run JSON parsing, focused artifact/catalog tests and full canonical tests.
3. Verify current public DTO validation directly; never infer reachability from JSON alone.
4. Recompute manifest hashes from exact bytes.
5. Run repository cross-file scan across Eval owner, coverage matrix, Runtime Plan, Eval Plan and active Thin Slice consumers; report forbidden-file impacts.
6. Obtain independent exact-head review before PR readiness.
7. After merge, Integrator runs the declared Graphify AST + semantic freshness gate before 01-04G starts.

</verification>

<success_criteria>

- Versioned artifacts specify both fault scenarios without violating frozen DTO/Port boundaries; actual Runtime/Harness reachability remains `NOT_IMPLEMENTED`.
- No bypass object or second contract exists.
- Stop reasons, canonical state transitions, version deltas and Trace variants match exact specified stages.
- Manifest hashes match corrected bytes.
- Full regression and exact-head review pass; lifecycle remains unchanged.

</success_criteria>

<output>
Execution handoff reports branch/commit/tree, exact files, RED/GREEN evidence, old/new script refs, stop/event mapping, hashes, full test count, review result, contract/security/Eval impact and rollback. Integrator alone writes Summary/status after merge.
</output>
