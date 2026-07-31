---
phase: 01-cycle-1-e2e-01
plan: 07A
type: tdd
wave: 13
depends_on:
  - 01-07
files_modified:
  - src/mini_agent/application/agent_run_service.py
  - tests/component/application/test_agent_run_service.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Every real ContextManifestRecorded event identifies its exact model-call purpose as REQUEST_UNDERSTANDING or PRESENTATION."
    - "Every normal returned AgentRunResult is preceded by exactly one real ResponseRendered event, including fixed safe failures and not-found; failures before deterministic rendering have none, while a later terminal-aggregate failure preserves the one reached-stage event but returns no result."
    - "The post-revalidation/pre-Gateway Runtime-local hook receives the active run_id together with the exact Task and RequestUnit projections."
    - "The stale-state Eval adapter can therefore apply ACTIVE/v1 to WAITING_USER/v2 and append its real TaskStateChanged against the active Run before Gateway rejection creates BLOCKED/v3."
    - "No Eval SUT, grader or evidence reader may synthesize missing purpose, ResponseRendered or TaskStateChanged fields/events."
    - "This Packet changes no Core Trace DTO, Application Port, persistence aggregate, Eval artifact, Composition Root or lifecycle state."
  artifacts:
    - "AgentRunService emits purpose-authenticated ContextManifestRecorded and one real ResponseRendered per normal result."
    - "AfterRevalidationHook receives explicit run identity without gaining persistence, Provider or Tool authority."
    - "Component tests reproduce all three real-Eval blockers before implementation and close them without synthetic evidence."
  key_links:
    - "The first and second _save_manifest call sites map respectively to REQUEST_UNDERSTANDING and PRESENTATION."
    - "DeterministicRenderer.map_result maps to a standalone ResponseRendered event before the existing terminal aggregate commit."
    - "AgentRunService passes running_run.run_id to AfterRevalidationHook; a later 01-08 adapter uses only canonical RuntimeRecordPort writes and Trace append."
---

# Phase 1 Plan 01-07A｜Runtime Trace alignment before vertical integration

> **ISSUED DEPENDENCY TASK PACKET / IMPLEMENTATION NOT STARTED**
> 受控 GSD planner / checker 对 exact integration `eee1c0e...` 的只读核查发现：01-07 的真实 grader会拒绝当前 Runtime 缺失的 `model_call_purpose`、fixed-result `ResponseRendered`与 stale-state hook run identity。根据项目 ownership 规则，这些 Runtime-owned 修复不能隐含塞入 Integrator-owned 01-08。本 Packet先用 exact two-file Runtime ownership关闭阻断，再由新的 reviewed integration SHA签发 01-08。

> **DERIVED / NON_NORMATIVE**
> 本 Plan只把 active Thin Slice / Trace / Eval owner与真实执行反馈转换为可执行 Task Packet，不拥有产品、Core Trace schema、Application Port、Eval Case、lifecycle或发布语义。

<objective>
关闭真实 E2E01 Eval 接入前的三个 Runtime Trace gap，同时保持 frozen DTO / Port / terminal aggregate不变。

Purpose: 让后续 01-08 从 PostgreSQL真实记录直接形成 Eval evidence，而不在 Eval SUT中补造 `model_call_purpose`、`ResponseRendered`或 stale-state `TaskStateChanged`。

Output: exact two-file Runtime Packet；一个 test-only RED commit与一个对应 GREEN / REFACTOR commit。不创建 Composition Root、real SUT、Evidence reader、HTTP E2E或 Eval Result。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-05R-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-05R-SUMMARY.md
@.planning/phases/01-cycle-1-e2e-01/01-07-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-07-SUMMARY.md
@docs/implementation/e2e01-thin-slice-implementation-spec.md
@docs/evaluation/p0-eval-coverage-matrix.md
@src/mini_agent/application/agent_run_service.py
@src/mini_agent/application/records.py
@src/mini_agent/core/trace.py
@src/mini_agent/evaluation/graders.py
@tests/component/application/test_agent_run_service.py

本 Plan使用受控 GSD planner / checker adapter，不调用 stock plan / execute / verify / lifecycle mutation / ship。planning-status PR必须先合并；随后 Integrator从固定 execution base建立独立 branch / Worktree，并从 official planning merge读取本 Plan。Executor只能写exact two owned files。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-runtime-trace-alignment`
base_branch: `integration/e2e01-thin`
base_sha: `eee1c0e46e1bca1160dea54d586d477c173daadc`
base_tree: `762bcb22284f3b5fdbc2ace1ef28ec982fc3a65d`
worktree_id: `e2e01-01-runtime-trace-alignment`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-01-runtime-trace-alignment`
writer: `Runtime sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer`

owned_files:

- `src/mini_agent/application/agent_run_service.py`
- `tests/component/application/test_agent_run_service.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/**`
- `evals/**`
- every other `src/mini_agent/application/**` file
- `src/mini_agent/core/**`
- `src/mini_agent/infrastructure/**`
- `src/mini_agent/evaluation/**`
- any future Composition Root or app-entrypoint path absent at `base_sha`
- every other test file
- `tests/conftest.py`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8 and graphify
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` sections 5.1, 10.3, 11 and 13.2
- `docs/architecture/memory-design-reference.md` Context Manifest / Trace boundaries
- `docs/evaluation/agent-evaluation-strategy.md` typed evidence and failure separation
- `docs/evaluation/p0-eval-coverage-matrix.md` E2E01-01/04 and Critical failures
- frozen Core/Application DTO / Port source at `base_sha`
- exact 01-07 grader behavior at `base_sha`

dependencies:

- Runtime replacement merge `fb607019130843c94825a47d7822518cbdb2143c`
- Infra replacement merge `8e21652fbfcba4e9efb351e298b9a0c58f4a46d8`
- Eval merge / exact execution base `eee1c0e46e1bca1160dea54d586d477c173daadc`
- post-merge gates at the execution base: `191` Eval focused, `40` migration and `936 passed, 1 deselected` full
- this planning-status PR must merge before any Runtime write
- execution preflight records `PLANNING_CONTRACT_SHA`, Plan blob and 01-07 Summary blob from official `origin/integration/e2e01-thin`, then proves both owned files are byte-identical between `base_sha` and planning merge
- 01-08 remains unissued until this Packet obtains reviewed merge and post-merge gates

required_checks:

- exact base, branch, merge-base, planning provenance and clean-worktree preflight
- one test-only RED commit proving all three blockers against unchanged production
- first Context Manifest Trace carries `REQUEST_UNDERSTANDING`; second carries `PRESENTATION`; count and purpose match actual model calls
- provider-before-candidate, input-invalid, Gate reject, not-found, order failure, presentation protocol/gate, renderer failure and success each have exactly one `ResponseRendered` when a normal result is returned
- exception / cancellation paths that fail before deterministic rendering retain zero `ResponseRendered` and zero fabricated `RunStopped`
- terminal aggregate conflict/error/cancellation after a successful standalone render preserves exactly one reached-stage `ResponseRendered` but returns no result and commits no ASSISTANT Message or `RunStopped`
- `ResponseRendered` remains a standalone normal Trace event before the existing terminal aggregate; `FinalizeRunCommand` exact terminal event set is unchanged
- hook receives exact `running_run.run_id`, Task and RequestUnit after revalidation and before reload/Gateway
- component stale helper uses the explicit run identity and preserves `TaskStateChanged == 3`; non-stale paths do not gain an event
- no Core Trace field/validator, Application record/Port, Eval artifact/grader or persistence schema change
- directed component, inherited Runtime focused, migration, full, compileall and `git diff --check` gates
- exact two-file feature and latest-integration overlay containment
- independent correctness/security/contract/test-gap review against exact feature and overlay heads
- read-only cross-file impact scan; any required forbidden-file change stops execution and returns to owner planning

done_when:

- one real test-only RED and one corresponding GREEN / REFACTOR commit are recorded in order
- feature and overlay changed-file sets both equal exact two owned files
- no grader-side enrichment or synthetic Trace workaround is introduced
- no unresolved `CRITICAL / HIGH / MEDIUM` review finding remains
- draft PR targets `integration/e2e01-thin` and records all nonclaims
- merge does not advance Case, Requirement or numbered Phase lifecycle

contract_changes: `YES / RUNTIME-LOCAL HOOK CONTEXT ONLY` — `AfterRevalidationHook` receives the active `run_id`; no public DTO, Port, HTTP or persistence contract changes.
security_impact: `YES` — prevents fabricated or misattributed Trace evidence and preserves fail-closed result semantics.
eval_impact: `YES / IMPLEMENTATION ALIGNMENT ONLY` — makes existing canonical grader requirements observable from real Runtime records; creates no Eval Result or Case PASS.
new_dependencies: `NONE`
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer never modifies `graphify-out/**`; after reviewed merge the Integrator runs Graphify AST refresh, verifies structure/freshness/no stale marker and blocks 01-08 on failure.
rollback: Close before merge or use a normal revert PR and re-block 01-08. Never reset, force-push, rewrite history or remove shared Worktrees.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan/Summary blobs
- exact two-file feature/overlay containment
- RED and GREEN commits plus directed/focused/migration/full commands
- purpose/result/hook behavior matrices
- contract/security/Eval impact and nonclaims
- independent feature/overlay reviews
- cross-file scan, unresolved risks and rollback
</task_packet>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `RTA-T01` | Tampering | Runtime → Context Manifest Trace | `MITIGATE / BLOCK` | purpose is supplied by the exact internal call site, never inferred by Eval |
| `RTA-T02` | Tampering | Runtime hook → stale-state Trace | `MITIGATE / BLOCK` | hook receives active run identity; later adapter must use canonical conditional write and real Trace append |
| `RTA-R01` | Repudiation | deterministic result → Trace | `MITIGATE / BLOCK` | every normal returned result has exactly one real `ResponseRendered` before terminal commit |
| `RTA-I01` | Information Disclosure | fixed error rendering → Trace | `MITIGATE` | event carries only allowlisted references; no message text, identity, provider envelope or raw failure |
| `RTA-D01` | Denial of Service | Trace append → terminal result | `ACCEPT / BOUNDED` | existing failure handling remains fail closed; Trace append failure cannot produce a successful return |
| `RTA-E01` | Elevation of Privilege | Eval hook → Runtime | `MITIGATE / BLOCK` | hook gains only active run identity, no trusted customer, Tool, Provider or direct Adapter authority |

</threat_model>

<feature>
  <name>Purpose-authenticated model-call Trace</name>
  <files>src/mini_agent/application/agent_run_service.py, tests/component/application/test_agent_run_service.py</files>
  <behavior>
    - `_save_manifest` requires a Runtime-selected purpose value
    - first call emits `model_call_purpose="REQUEST_UNDERSTANDING"`
    - second call emits `model_call_purpose="PRESENTATION"`
    - no purpose is copied from Provider output, script or Eval artifact
  </behavior>
</feature>

<feature>
  <name>One real rendering event per normal result</name>
  <files>src/mini_agent/application/agent_run_service.py, tests/component/application/test_agent_run_service.py</files>
  <behavior>
    - every `_finish_without_task` and `_finish_with_task` normal result appends one `ResponseRendered`
    - success no longer uses a separate duplicate path
    - event contains only applicable run/task/request-unit/Observation/presentation references
    - pre-render `FAILED` exceptional closure emits no user result and no `ResponseRendered`
    - post-render terminal aggregate failure preserves the one actual event but emits no returned result, ASSISTANT Message or `RunStopped`
    - existing exact terminal aggregate remains TaskStateChanged?/RunStopped only
  </behavior>
</feature>

<feature>
  <name>Explicit active-Run identity for stale-state seam</name>
  <files>src/mini_agent/application/agent_run_service.py, tests/component/application/test_agent_run_service.py</files>
  <behavior>
    - `AfterRevalidationHook(run_id, task, request_unit)` receives the exact active Run identity
    - no-op and every test hook adopt the explicit signature
    - invocation stays after canonical revalidation and before Task/RequestUnit reload and Gateway
    - existing component stale transition continues to use `ApplyTaskTransitionCommand(APPLIED)` and appends `TaskStateChanged` with the supplied run_id
  </behavior>
</feature>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — reproduce the three real-Eval Trace blockers</name>
  <files>tests/component/application/test_agent_run_service.py</files>
  <read_first>AGENTS.md, docs/implementation/e2e01-thin-slice-implementation-spec.md, src/mini_agent/application/agent_run_service.py, src/mini_agent/application/records.py, src/mini_agent/core/trace.py, src/mini_agent/evaluation/graders.py, tests/component/application/test_agent_run_service.py</read_first>
  <action>Add focused assertions that real ContextManifestRecorded events expose exact call purposes; every normal result path has exactly one ResponseRendered; pre-render failed exception/cancellation paths have none; a terminal aggregate failure after rendering preserves only its one reached-stage event and no result/ASSISTANT/RunStopped; and a new three-argument hook receives the active run_id before Gateway. Keep production unchanged, run the directed file and retain contract-related failures rather than syntax/import failures. Commit only the test file as `test(01-07A): expose real runtime trace gaps`.</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py -x</automated>
    Expected RED against unchanged production must come from the new purpose, fixed-result rendering or hook assertions; import, fixture and syntax failures do not qualify. Record the separate base result `27 passed`.
  </verify>
  <acceptance_criteria>
    - failures directly demonstrate missing purpose, missing fixed-result ResponseRendered and old hook call shape
    - tests cover success, no-Task fixed failure, with-Task fixed failure, not-found, pre-render FAILED and post-render terminal failure boundaries
    - tests do not construct synthetic EvalEvidence or patch persisted Trace after execution
    - changed-file set is exactly the single test file
  </acceptance_criteria>
  <done>All three blockers are reproduced against the exact integration implementation.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN / REFACTOR — emit real Trace and pass explicit run identity</name>
  <files>src/mini_agent/application/agent_run_service.py, tests/component/application/test_agent_run_service.py</files>
  <read_first>Task 1 RED commit, src/mini_agent/application/agent_run_service.py, src/mini_agent/application/records.py, src/mini_agent/core/trace.py, tests/component/application/test_agent_run_service.py</read_first>
  <action>Require an explicit purpose in `_save_manifest`, populate the existing Trace field at both call sites, centralize one standalone ResponseRendered append in the two normal finish boundaries, remove the successful path's duplicate append, and change the Runtime-local hook signature/invocation to include `running_run.run_id`. Preserve the exact terminal aggregate and all Provider/Gateway/Tool/persistence behavior. Update existing hooks/tests only as required by the new Runtime-local signature. Commit both files as `fix(01-07A): align runtime trace with real eval`.</action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py -x</automated>
    The inherited Runtime focused suite, database availability, persistent development-DB migration check, isolated fresh-schema migration regression, complete offline suite, compileall and `git diff --check` are mandatory Packet gates in verification steps 3–5.
  </verify>
  <acceptance_criteria>
    - purpose counts equal actual model-call counts on every tested trajectory
    - exactly one ResponseRendered precedes RunStopped for every normal returned result
    - pre-render FAILED closure has no ResponseRendered or fabricated RunStopped
    - post-render terminal failure retains exactly one actual ResponseRendered but no returned result, ASSISTANT Message or RunStopped
    - hook receives the exact active run_id and retains its post-revalidation/pre-Gateway position
    - no forbidden file, dependency, DTO, Port, artifact or lifecycle change appears
  </acceptance_criteria>
  <done>Real Runtime Trace satisfies existing Eval requirements without any Eval-side enrichment.</done>
</task>

</tasks>

<verification>

1. Prove exact base/planning provenance, clean Worktree and two-file containment.
2. Retain the real test-only RED before production change.
3. Start only the Integrator-owned Compose project: `db` is the existing persistent development service, while `db-test` is disposable. `alembic upgrade head` below validates the persistent development DB; the later migration regression creates and uses its independent fresh schema on `db-test`:

```bash
uv sync --all-groups
docker compose -p mini-agent -f /Users/ming/projects/mini-agent/compose.yaml up --wait -d db
docker compose -p mini-agent -f /Users/ming/projects/mini-agent/compose.yaml --profile test up --wait -d db-test
uv run alembic upgrade head
```

4. Run the directed component file and inherited Runtime focused matrix:

```bash
uv run pytest tests/component/application/test_agent_run_service.py -x
uv run pytest \
  tests/component/core/test_request_processing.py \
  tests/component/core/test_control_gateway.py \
  tests/component/core/test_presentation_policy.py \
  tests/component/application/test_agent_run_service.py \
  tests/component/application/test_read_tool_executor.py \
  tests/component/application/test_deterministic_renderer.py \
  tests/component/application/test_restart_recovery_service.py -x
```

5. Run `uv run pytest tests/integration/test_database_migrations.py -x`, complete `uv run pytest`, `uv run python -m compileall -q src tests` and `git diff --check`.
6. Inspect actual Trace matrices for purpose, ResponseRendered count/order, pre/post-render failure distinction and stale-state hook identity.
7. Build a latest-integration overlay if integration advanced; prove the overlay changes exactly the same two files and repeat all gates.
8. Obtain independent correctness/security/contract/test-gap reviews on exact feature and overlay heads.
9. Integrator merges serially, reruns full/migration/Graphify gates, closes the separate active-owner status alignment and only then issues 01-08 from the new exact integration SHA.

</verification>

<success_criteria>

- Existing canonical Trace/Eval expectations can be satisfied from real Runtime output.
- No missing Trace field/event is synthesized by the future Eval SUT.
- Frozen terminal-turn atomicity and every existing Runtime behavior remain green.
- Exact two-file scope, TDD lineage, independent review and latest-integration evidence are reproducible.
- Case lifecycle remains unchanged and 01-08 remains blocked until reviewed merge.

</success_criteria>

<output>
Execution writes no Summary or shared State. It returns the declared handoff with exact provenance, commits, two-file containment, behavior matrices, checks, reviews, nonclaims and rollback. Integrator alone writes later Summary/status, Graphify evidence and the exact-base 01-08 Plan.
</output>
