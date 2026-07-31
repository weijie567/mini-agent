---
phase: 01-cycle-1-e2e-01
plan: 05R
type: tdd
wave: 10
depends_on:
  - 01-04H
files_modified:
  - src/mini_agent/core/request_processing.py
  - src/mini_agent/core/control_gateway.py
  - src/mini_agent/core/presentation_policy.py
  - src/mini_agent/application/agent_run_service.py
  - src/mini_agent/application/read_tool_executor.py
  - src/mini_agent/application/deterministic_renderer.py
  - src/mini_agent/application/restart_recovery_service.py
  - tests/component/core/test_request_processing.py
  - tests/component/core/test_control_gateway.py
  - tests/component/core/test_presentation_policy.py
  - tests/component/application/test_agent_run_service.py
  - tests/component/application/test_read_tool_executor.py
  - tests/component/application/test_deterministic_renderer.py
  - tests/component/application/test_restart_recovery_service.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Runtime derives every owner scope and GetOrderQuery.customer_id from trusted CustomerContext; message and Provider output cannot create, replace or expand identity."
    - "Request Understanding candidates pass deterministic validation, Reducer, InputBinding and current-state revalidation before Control Gateway can approve a ToolCall."
    - "Gateway accepts provider-visible get_order.order_id only when the normalized candidate exactly equals the current InputBinding; any Provider replacement yields ARGUMENT_BINDING_MISMATCH with zero ToolCall/read, while an accepted GetOrderQuery uses customer_id=trusted plus order_id=bound."
    - "The exact immutable Tool Registry snapshot, canonical name, closed schema, READ effect, binding references and current Task state version are revalidated fail closed."
    - "GateDecision is recorded before ToolCall creation, and the durable ToolCall dispatch fence must return APPLIED before the single allowed get_order read."
    - "FOUND produces one safe OrderObservation before presentation; foreign and nonexistent orders produce the same bounded result with zero Observation and zero presentation model call."
    - "PresentationPlan remains fact-free; deterministic rendering injects facts only from the approved safe Observation projection."
    - "The success path uses exactly two model calls, one ToolCall, one order read and one Observation, then moves Task and RequestUnit from ACTIVE/v1 to COMPLETED/v2."
    - "Unknown tool rejection produces zero ToolCall/read/Observation; the stale-state seam yields ACTIVE/v1 → WAITING_USER/v2 → BLOCKED/v3 with STATE_VERSION_MISMATCH."
    - "Missing exact provider usage is represented by required TokenCounts(input_tokens=None, output_tokens=None), never estimated values or placeholder zero."
    - "Restart recovery builds the exact bounded Core Trace projection and calls only claim_and_apply_restart_recovery; it never resumes a model call or replays a Tool."
    - "Every normal COMPLETED path constructs one closed FinalizeRunCommand containing the optional Task transition, terminal result, exact ASSISTANT Message and exact terminal Trace set; Runtime performs no earlier terminal Task write and no later best-effort terminal projection."
    - "Only a terminal aggregate result of APPLIED authorizes Runtime to return AgentRunResult; conflict, exception and cancellation cannot expose success or leave a Runtime-originated partial terminal turn."
  artifacts:
    - "Three new Core modules provide pure deterministic request, Gateway and presentation decisions without I/O."
    - "Four new Application modules implement injected orchestration, read-tool lifecycle, deterministic rendering with bounded result mapping, and restart recovery."
    - "Seven new Component test files cover positive, directed tamper, zero-side-effect, ordering, budget and recovery behavior."
  key_links:
    - "AgentRunService maps Provider candidates through request_processing and control_gateway before ReadToolExecutor."
    - "ReadToolExecutor maps the approved binding and trusted owner context to GetOrderPort only after an APPLIED dispatch fence."
    - "OrderObservation is the only fact-bearing input to presentation_policy and DeterministicRenderer."
    - "RestartRecoveryService maps RestartRecoveryClosure to one ApplyRestartRecoveryCommand carrying the exact recovery Trace set."
---

# Phase 1 Plan 01-05R｜W2 Runtime replacement

> **ISSUED REPLACEMENT TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Plan 是历史 01-05 / Draft PR #28 的唯一 replacement Packet。它从 01-04H reviewed integration merge `64992cf...` 重新建立 execution identity，只移植历史 head `a27141b...` 的 14 个 owned paths并消费新的 terminal-turn aggregate；历史 Plan、branch 与 PR 保持不可变证据，绝不 rebase、force-push或冒充本 Packet。

> **DERIVED / NON_NORMATIVE**
> 本 Plan 只把 active canonical owner、冻结的 01-04E/F/G contract 与 W2 Research/Validation/Patterns 转换为一个可执行 Runtime Task Packet。它不拥有产品、架构、DTO/Port、Eval Case 生命周期或发布语义；冲突时服从 `AGENTS.md` 和对应 active owner。

<objective>
在不改写历史 PR #28 的前提下，受控移植其 exact 14-file Runtime 实现，并以新的 TDD regression 修复 terminal-turn split-write blocker；同时保持身份、状态、Tool、Observation、Presentation、Trace、cancellation 与 restart recovery 的确定性边界。

Purpose: 让后续 01-06R 能实现 01-04H 的物理事务，让 01-08 Integrator 可以消费一个不会自行制造 partial terminal success 的 Runtime。Eval PR #29 继续保持独立 feature ownership，只在 Runtime / Infra merge 后做 latest-integration replay。

Output: 精确新增七个 Runtime source files与七个 Component test files；其中十二个非 terminal-consumer paths必须与历史 donor head byte-identical，`agent_run_service.py`及其测试在 donor基础上消费01-04H。不得修改现有 Core/Application contract、Infra、Eval artifact、active docs、Composition Root或依赖。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-W2-RESEARCH.md
@.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
@.planning/phases/01-cycle-1-e2e-01/01-W2-PATTERNS.md
@.planning/phases/01-cycle-1-e2e-01/01-04G-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-04H-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-04H-SUMMARY.md
@src/mini_agent/core/common.py
@src/mini_agent/core/identity.py
@src/mini_agent/core/memory.py
@src/mini_agent/core/order.py
@src/mini_agent/core/presentation.py
@src/mini_agent/core/request_understanding.py
@src/mini_agent/core/task_state.py
@src/mini_agent/core/tool_system.py
@src/mini_agent/core/trace.py
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py

本 Plan 只有在 planning PR 合并后、Integrator 从 `<task_packet>.base_sha` 预建独立 execution Worktree，并记录 branch / merge-base / clean-state / Plan provenance 证据后才可执行。Executor只能写 `<task_packet>.owned_files` 的精确 14 文件；所有引用文件均为只读输入。历史 Task 1/2及非终态的Task 3 RED/GREEN只作为可验证 lineage，不伪造第二次RED；replacement新增的terminal aggregate tests必须在consumer source修改前取得真实RED，再GREEN。所有移植、RED/GREEN与fix提交顺序进入handoff。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-w2-runtime-r`
base_branch: `integration/e2e01-thin`
base_sha: `64992cf3bdc6205e00d0c36433309b1657a57531`
worktree_id: `e2e01-w2-runtime-r`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-w2-runtime-r`
writer: `Runtime sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer`

owned_files:

- `src/mini_agent/core/request_processing.py`
- `src/mini_agent/core/control_gateway.py`
- `src/mini_agent/core/presentation_policy.py`
- `src/mini_agent/application/agent_run_service.py`
- `src/mini_agent/application/read_tool_executor.py`
- `src/mini_agent/application/deterministic_renderer.py`
- `src/mini_agent/application/restart_recovery_service.py`
- `tests/component/core/test_request_processing.py`
- `tests/component/core/test_control_gateway.py`
- `tests/component/core/test_presentation_policy.py`
- `tests/component/application/test_agent_run_service.py`
- `tests/component/application/test_read_tool_executor.py`
- `tests/component/application/test_deterministic_renderer.py`
- `tests/component/application/test_restart_recovery_service.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/**`
- every existing `src/mini_agent/core/*.py`
- `src/mini_agent/application/ports.py`
- `src/mini_agent/application/records.py`
- `src/mini_agent/application/persistence.py`
- `src/mini_agent/application/__init__.py`
- `src/mini_agent/application/run_result_mapper.py`
- `src/mini_agent/__init__.py`
- `src/mini_agent/main.py`
- `src/mini_agent/bootstrap.py`
- `src/mini_agent/api/**`
- `src/mini_agent/infrastructure/**`
- `src/mini_agent/evaluation/**`
- every existing test file
- `tests/component/application/test_run_result_mapper.py`
- `tests/conftest.py`
- `tests/integration/**`
- `tests/e2e/**`
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8 and graphify
- `PROJECT_DIRECTION.md` Runtime / Application / Core ownership and controlled ReAct
- `docs/business-capabilities.md` E2E-01/04 and P0 user-visible boundaries
- `docs/architecture/intent-design-reference.md` candidate, InputBinding, Reducer and revalidation
- `docs/architecture/tool-calling-design-reference.md` immutable snapshot, Gateway and ToolCall lifecycle
- `docs/architecture/memory-design-reference.md` ContextManifest, Observation, Trace and restart recovery
- `docs/evaluation/agent-evaluation-strategy.md` Component/Trajectory/E2E evidence separation
- `docs/evaluation/p0-eval-coverage-matrix.md` E2E01-01/04 and Critical failures
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` scoped behavior, budgets and error mapping
- frozen Core/Application source at `base_sha`

dependencies:

- 01-04H reviewed Application owner merge is the exact execution base `64992cf3bdc6205e00d0c36433309b1657a57531`; it includes 01-04E token availability, 01-04F reachable fault scripts, 01-04G recovery Trace atomicity and the complete terminal-turn command
- this Plan must merge through the dedicated planning-status path before implementation writes begin
- executor records `PLANNING_CONTRACT_SHA`, the merged Plan blob and 01-04H Summary blob; all 14 owned paths must be absent at both `base_sha` and the planning merge before first write
- 01-04H Plan blob at execution base is `386001a8b642569729f33c61ee7b2b570e1d0135`; historical 01-05 Plan blob is `eb30055147723ee27c26fcd99604fc6ee9284644`
- historical donor PR #28/head `a27141ba902015af34602fe15eeec4ba44482687`/tree `1f0a190efe78e0353f9d7f14906c38c56033708f` is a read-only replay source and review/RED evidence, never an execution base or merge target
- the donor range from `c35687dafa3881bb322d91515068d8d39be79df6` changes exactly the same 14 owned paths; every donor commit must be preflighted against that allowlist before controlled replay
- 01-06R remains `NOT_ISSUED` until this Packet obtains reviewed merge and a new exact integration SHA; Eval PR #29 does not import Runtime and remains Draft pending latest-integration replay

required_checks:

- exact base, branch, merge-base, planning provenance and clean-worktree preflight
- exact donor range/commit/file containment and no historical branch/PR mutation
- inherited behavior cites historical RED/GREEN lineage and obtains focused GREEN after replay; replacement terminal aggregate obtains a new expected RED before consumer source changes, then focused GREEN
- exact owner scope, argument binding, current-state and immutable snapshot checks
- GateDecision-before-ToolCall and APPLIED-dispatch-fence-before-read happens-before assertions
- success/foreign/nonexistent/unknown-tool/stale/provider/presentation/system-failure behavior and bounded stop mapping
- exact model/tool/read/Observation budgets and no-retry/no-parallel assertions
- required unknown TokenCounts semantics
- exact recovery event/state/link bijection and zero resume/replay assertions
- no standalone terminal Task transition, ASSISTANT Message append, TaskStateChanged append or RunStopped append on normal COMPLETED paths
- exact no-Task `(RunStopped,)` and with-Task `(TaskStateChanged, RunStopped)` terminal event sets, timestamps, identities, result/message binding and only-APPLIED return
- Packet focused command, full `uv run pytest`, `compileall`, `git diff --check` and exact 14-file set equality
- feature ownership is computed only from `git diff --name-only 64992cf3bdc6205e00d0c36433309b1657a57531...<feature-head>`; its normalized path set and cardinality must equal `owned_files` exactly, so a missing planned file and an extra file both fail
- relative to donor head, the twelve owned paths other than `src/mini_agent/application/agent_run_service.py` and `tests/component/application/test_agent_run_service.py` must have exact blob equality; only those two terminal consumer paths may intentionally differ
- latest-integration compatibility is computed from `git diff --name-only <overlay-parent>...<overlay-head>`; that normalized path set and cardinality must also equal the same exact 14 `owned_files`, while sibling files already present in the overlay parent remain outside the diff
- cross-file impact scan reported read-only; any required forbidden-file change stops execution
- independent correctness/security/contract/test-gap review against exact published head

done_when:

- controlled donor replay is exact and inherited lineage/focused checks are recorded; the replacement terminal task has ordered RED/GREEN evidence
- exact 14-file Packet has `set(feature diff) == set(owned_files)` relative to the original `64992cf...` feature base
- twelve non-terminal-consumer owned blobs equal donor head exactly and the remaining pair changes only to consume 01-04H
- full regression is green from the project root
- draft PR targets `integration/e2e01-thin` and reports all nonclaims
- no Case, Requirement or numbered Phase lifecycle advances

contract_changes: `NONE` — consume frozen DTO, enum, Port, record, command, persistence and artifact contracts; new private implementation types/callable seams are non-canonical and cannot expand shared Ports.
security_impact: `YES` — implements trusted identity, deterministic argument binding, stale-state rejection, durable dispatch, minimal disclosure, restart no-replay and one-shot terminal success/Trace/Message repudiation boundaries.
eval_impact: `YES / COMPONENT BEHAVIOR ONLY` — creates no Eval Result, Case activation, baseline or lifecycle evidence; 01-07 does not import or instantiate Runtime.
new_dependencies: `NONE`
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer never modifies `graphify-out/**`; after merge Integrator runs `graphify update .`, verifies freshness/health and blocks downstream integration on failure.
rollback: Close before merge or use a normal revert PR and re-block 01-06R issuance, Eval latest-integration replay and 01-08. Historical PR #28 and Eval feature evidence remain untouched. Never reset, force-push, delete shared Worktrees or rewrite persisted history.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan blob
- donor head/tree/range, per-commit containment and controlled replay commit
- exact equality between the 14-file allowlist and `64992cf...<feature-head>` actual changed-file set
- exact donor blob equality for twelve paths and intentional delta for the terminal consumer pair
- historical RED/GREEN lineage plus replacement terminal RED/GREEN/optional REFACTOR commits and commands
- focused/full/compileall/diff-check results and final test counts
- identity, binding, Gate, dispatch, presentation, Trace and recovery behavior matrix
- contract/security/Eval impact, cross-file scan, nonclaims and unresolved risks
- independent exact-head review, overlay-parent-relative latest-integration compatibility, rollback and 01-08 handoff
</task_packet>

<scope_exception>

This Plan intentionally contains 14 files:

- seven production modules, each paired one-to-one with exactly one Component test:
  - `core/request_processing.py` ↔ `test_request_processing.py`
  - `core/control_gateway.py` ↔ `test_control_gateway.py`
  - `core/presentation_policy.py` ↔ `test_presentation_policy.py`
  - `application/agent_run_service.py` ↔ `test_agent_run_service.py`
  - `application/read_tool_executor.py` ↔ `test_read_tool_executor.py`
  - `application/deterministic_renderer.py` ↔ `test_deterministic_renderer.py`
  - `application/restart_recovery_service.py` ↔ `test_restart_recovery_service.py`
- all 14 files belong to one Runtime branch, one Runtime writer and fixed Plan `01-05R`;
- the work is bounded by three atomic TDD checkpoints: request/Gateway, read/presentation, and orchestration/recovery;
- these private implementation stages form one directed Runtime chain. Splitting them into separate Plans/Packets would create cross-Packet dependencies on non-canonical private seams before 01-08 composition.

Therefore the `>10 files` planner warning is accepted for this cohesive Packet, while the blocker threshold remains 15 files. Any fifteenth changed file, any second writer/branch, or any shared-contract change is a blocker and requires Integrator re-planning.

</scope_exception>

<interfaces>

The following names are local implementation seams, not new canonical contracts:

```text
core.request_processing
  InitialRequestDecision
  RevalidatedNextMove
  validate_and_reduce_initial_request(...)
  revalidate_next_move(...)

core.control_gateway
  evaluate_control_gateway(...) -> GateDecision

core.presentation_policy
  validate_presentation_plan(...) -> PresentationPlan

application.read_tool_executor
  ReadToolExecutor.execute_get_order(...)

application.deterministic_renderer
  DeterministicRenderer.render_order_summary(...)
  DeterministicRenderer.map_result(...)

application.agent_run_service
  AfterRevalidationHook
  AgentRunService.handle(command: AgentRunCommand) -> AgentRunResult

application.restart_recovery_service
  RestartRecoveryService.recover_pending(...)
```

Pure Core rules:

- Core modules perform no I/O and import no Application or Infrastructure module.
- Typed local decisions use the existing visibility/model conventions; ordinary dicts do not replace frozen DTOs.
- Validation accepts exactly one current-message `ADD_GOAL` candidate for this slice, builds one normalized `InputBinding`, and gives the initial Task and RequestUnit `ACTIVE` with `state_version=1`.
- `revalidate_next_move` normalizes but never overwrites the Provider candidate. It carries the candidate `get_order.order_id`, the current normalized InputBinding reference/value and `validated_task_state_version=1` as distinct typed inputs for deterministic comparison.
- Gateway first requires normalized candidate `get_order.order_id == InputBinding.normalized_value`; any mismatch rejects with existing `ARGUMENT_BINDING_MISMATCH`, exposes no authorized command and creates no ToolCall/read. Only an exact match may proceed to the exact canonical tool name, registry version/snapshot, closed argument schema, binding refs, READ effect and current Task/RequestUnit status/version checks. It uses existing `GateReasonCode` members only; no duplicate strings or new enum values.
- After the injected stale transition advances current state to version 2, the decision must reject with existing `STATE_VERSION_MISMATCH`.
- presentation policy accepts only the existing fact-free `PresentationPlan` shape and the safe Observation provenance needed by deterministic rendering.
- `SafeOrderProjection.order_number` is a downstream Observation/renderer output field only. It is never used as the Provider-visible Tool argument or `GetOrderQuery` input field; those frozen input fields are `order_id`.

Application orchestration rules:

```text
trusted CustomerContext
  → TrustedOwnerScope
  → model-visible toolset artifact persisted/resolvable
  → Conversation + USER Message
  → Run CREATED → RUNNING
  → ContextManifest #1 with TokenCounts(None, None)
  → Provider candidate
  → deterministic validation / Reducer / InputBinding
  → complete initial graph persisted
  → current-state revalidation
  → optional AFTER_REVALIDATION_BEFORE_GATE hook
  → reload current Task/RequestUnit
  → GateDecision persisted
  → ToolCall CREATED
  → durable dispatch fence APPLIED
  → exactly one owner-scoped get_order read
  → ToolCall/attempt terminal projection
  → FOUND only: safe Observation persisted
  → ContextManifest #2 with TokenCounts(None, None)
  → fact-free PresentationPlan
  → deterministic renderer
  → construct exact terminal Task transition/result/ASSISTANT Message/Trace
  → one FinalizeRunCommand conditional write
  → APPLIED only
  → return AgentRunResult
```

`AfterRevalidationHook` is constructor-injected, defaults to no-op and receives the exact current Task and RequestUnit projections. It is a Runtime-local seam that 01-08 may wire to an independently implemented Eval SUT adapter; 01-07 does not import or instantiate `AgentRunService`. Runtime does not parse script references or hard-code fixture IDs. A hook-side non-`APPLIED` conditional write propagates as an integration execution failure rather than being converted into a product Case result.

Normal terminal-turn rules:

- Runtime computes one `completed_at` and uses it for `terminal_record.completed_at`, ASSISTANT `MessageRecord.received_at` and `RunStopped.occurred_at`.
- With no Task/link, `FinalizeRunCommand` carries empty link/Task sets, no Task transition, the exact `terminal_result`, one ASSISTANT Message and exactly `(RunStopped,)`.
- With one Task/link, Runtime constructs but does not separately persist `ApplyTaskTransitionCommand`; `FinalizeRunCommand` carries that transition, its exact next Task, the terminal Run/link, result, ASSISTANT Message and ordered `(TaskStateChanged, RunStopped)`.
- `TaskStateChanged.occurred_at` equals the nested transition `changed_at`; `RunStopped` binds the exact Run, stop reason, outcome and completion timestamp.
- Runtime performs no `apply_task_transition_if_current` for the normal terminal state and no post-commit `append_message` or terminal `append_trace_event`.
- `ConditionalWriteResult.APPLIED` is the only successful commit point and the only path that sets the local committed-result cursor or returns `AgentRunResult`. `PROJECTION_CONFLICT`, `NOT_APPLICABLE`, exception or cancellation returns no success.
- Exceptional `FAILED` closure continues to use the same Port but carries no Task transition, terminal result, ASSISTANT Message or terminal Trace; it does not fabricate a stop reason/outcome.
- After `APPLIED`, Runtime has no terminal persistence await. Physical same-transaction proof and rollback on any child write remain the separately issued 01-06R responsibility.

Read Tool rules:

```text
CreateToolCallCommand
  → insert_tool_call
  → DispatchToolCallCommand
  → start_tool_call_if_created == APPLIED
  → GetOrderPort.get_order(GetOrderQuery(customer_id=trusted, order_id=bound))
  → FinalizeToolCallCommand
  → FOUND only: SaveObservationCommand
```

Every other `ToolDispatchFenceWriteResult` produces zero external dispatch. P0 uses attempt 1 only and performs no retry. An Action result remains `ACTION_LEDGER_REQUIRED` and is never executed in this slice.

Expected path matrix:

| path | Run stop | Task result | model/tool/read/Observation |
|---|---|---|---|
| found success | `GOAL_COMPLETED` | `COMPLETED/v2` | `2 / 1 / 1 / 1` |
| foreign or nonexistent | `NOT_FOUND_OR_NOT_ACCESSIBLE` | `COMPLETED/v2` | `1 / 1 / 1 / 0`; no presentation call |
| Provider argument replacement | `GATE_REJECTED` | `BLOCKED/v2` | `1 / 0 / 0 / 0`; Gate reason `ARGUMENT_BINDING_MISMATCH` |
| unknown tool | `GATE_REJECTED` | `BLOCKED/v2` | `1 / 0 / 0 / 0` |
| stale state | `GATE_REJECTED` | `WAITING_USER/v2 → BLOCKED/v3` | `1 / 0 / 0 / 0`; Gate reason `STATE_VERSION_MISMATCH` |
| RU schema/protocol failure | `PROVIDER_PROTOCOL_ERROR` | no Task graph | `1 / 0 / 0 / 0` |
| RU source/authority/trusted-field invalid | `INPUT_INVALID` | no Task graph | `1 / 0 / 0 / 0` |
| order system failure | `ORDER_SERVICE_UNAVAILABLE` | `BLOCKED/v2` | `1 / 1 / 1 / 0` |
| presentation protocol failure | `PROVIDER_PROTOCOL_ERROR` | `BLOCKED/v2` | `2 / 1 / 1 / 1`; Observation retained; no proposed/render event |
| presentation policy rejection | `PRESENTATION_PLAN_REJECTED` | `BLOCKED/v2` | `2 / 1 / 1 / 1`; no renderer |
| renderer invariant failure | `RENDERER_INVARIANT_FAILED` | `BLOCKED/v2` | `2 / 1 / 1 / 1`; no unsafe fallback |

Foreign and nonexistent outcomes use the same `AgentRunResult.outcome` and exact fixed message. Bounded mappers never include raw Provider/Tool exceptions, customer identity, order payload or internal record IDs.

Restart recovery rules:

- CREATED Run: one `RunStopped(BLOCKED, PROCESS_RESTART_DETECTED)`.
- Each recoverable Task: one exact Task/RequestUnit transition to `BLOCKED` and one matching `TaskStateChanged`.
- Each active READ ToolCall: one transition to `INTERRUPTED` and one matching `ToolCallInterrupted`.
- RUNNING Action: return/propagate `RECONCILIATION_REQUIRED`; no state/Trace write and readiness cannot pass.
- Service calls only `RestartRecoveryPort.load_next_restart_recovery_closure()` and `claim_and_apply_restart_recovery()`; it never substitutes `RuntimeRecordPort.append_trace_event`.
- `CLOSURE_CONFLICT`, `NOT_APPLICABLE` and `RECONCILIATION_REQUIRED` are returned as non-ready outcomes for 01-08 to handle; Runtime does not loop indefinitely, resume or redispatch.

</interfaces>

<threat_model>

| threat_id | severity | category | boundary | disposition | mitigation / blocking test |
|---|---|---|---|---|---|
| `RT-S01` | HIGH | Spoofing | message/model → trusted identity | `MITIGATE / BLOCK` | only `CustomerContext` creates `TrustedOwnerScope` and `GetOrderQuery.customer_id`; trusted-field injection is rejected before Gate |
| `RT-T01` | HIGH | Tampering | Provider candidate → InputBinding | `MITIGATE / BLOCK` | normalized candidate must exactly equal the current binding; directed `O-1001 → O-2001/O-9999` replacements yield `ARGUMENT_BINDING_MISMATCH` with zero ToolCall/read and are never sanitized into approval |
| `RT-T02` | HIGH | Tampering | revalidated move → Gateway | `MITIGATE / BLOCK` | immutable snapshot, exact name/schema/effect/binding/current version checks; stale state yields `STATE_VERSION_MISMATCH` |
| `RT-E01` | HIGH | Elevation of Privilege | Gateway → Tool executor | `MITIGATE / BLOCK` | rejected/unknown/Action candidates produce no ToolCall; Action remains ledger-required |
| `RT-R01` | HIGH | Repudiation | ToolCall persistence → external read | `MITIGATE / BLOCK` | GateDecision precedes ToolCall and only APPLIED dispatch fence permits the unique read |
| `RT-D01` | MEDIUM | Denial of Service | Provider/Tool loop | `MITIGATE` | maximum two model calls, one ToolCall, one read, attempt 1, no retry and no parallel path |
| `RT-I01` | HIGH | Information Disclosure | Observation → presentation/user | `MITIGATE / BLOCK` | fact-free plan and deterministic renderer consume only safe Observation projection |
| `RT-T03` | HIGH | Tampering | Provider presentation → renderer | `MITIGATE / BLOCK` | invalid/fact-bearing plan cannot reach renderer; protocol/policy failures use bounded mapper |
| `RT-I02` | HIGH | Information Disclosure | owner-scoped order result → user | `MITIGATE / BLOCK` | foreign and nonexistent paths have identical outcome/message, zero Observation and no presentation call |
| `RT-R02` | MEDIUM | Repudiation | state/tool/Observation → Trace | `MITIGATE` | spy Ports assert required event ordering, cardinality and stop reason without raw payload or identity |
| `RT-R03` | HIGH | Repudiation | restart state → recovery Trace | `MITIGATE / BLOCK` | exact events travel inside `ApplyRestartRecoveryCommand` and are never appended after the atomic claim |
| `RT-T04` | HIGH | Tampering | restart → external Tool/Action | `MITIGATE / BLOCK` | no model resume, Tool replay or Action guess; reconciliation blocks readiness |
| `RT-R04` | HIGH | Repudiation | normal result → Task/Run/Message/Trace | `MITIGATE / BLOCK` | Runtime submits exactly one closed `FinalizeRunCommand`; tests forbid an earlier terminal Task write, later best-effort Message/Trace or success before `APPLIED` |
| `RT-T05` | HIGH | Tampering | terminal aggregate identities/timestamps | `MITIGATE / BLOCK` | exact Application validator plus directed Runtime tests bind Message/result/Run/Conversation/Task/RequestUnit/outcome/reason and one completion timestamp |
| `RT-D02` | HIGH | Denial of Service | terminal child write / CAS → caller | `TRANSFER / BLOCK 01-06R` | Runtime produces one aggregate and returns no result on non-APPLIED/error/cancellation; physical rollback for every child-write fault is required from 01-06R |
| `RT-I03` | HIGH | Information Disclosure | terminal validation/error → log/result | `MITIGATE / BLOCK` | use only exact bounded records and existing sanitized Application validation; no raw message, identity or Adapter exception enters Trace/result/log assertions |

</threat_model>

<feature>
  <name>E2E01-01/04 deterministic Runtime behavior</name>
  <files>the exact 14-file owned_files list in task_packet</files>
  <behavior>
    - trusted identity, current-message provenance, deterministic binding and Reducer produce one owner-bound ACTIVE/v1 Task graph
    - immutable Gateway approval is the only path to a ToolCall; stale/unknown/tampered candidates fail closed with zero forbidden side effects
    - durable READ lifecycle, safe Observation, fact-free presentation and deterministic rendering enforce one bounded controlled-ReAct turn
    - Application orchestration records exact ordering, budgets, terminal projections and bounded results
    - restart recovery produces exact atomic command input and never resumes or replays work
  </behavior>
  <implementation>Use the exact local seam names and behavioral matrix in the interfaces block. Reuse only frozen Core/Application DTOs, records, commands, enums and Ports. Constructor-inject all I/O, clock, UUID factory, registry snapshot/artifact and optional fault hook. Do not create a second Runtime contract, generic workflow engine, capability classifier, Tool allowlist per RequestUnit, raw dict transport or Composition Root.</implementation>
</feature>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: controlled donor replay and RED for split terminal writes</name>
  <files>all exact 14 owned_files; RED edit only tests/component/application/test_agent_run_service.py after the controlled replay</files>
  <read_first>AGENTS.md, .planning/GOVERNANCE.md, this Plan from PLANNING_CONTRACT_SHA, 01-04H Plan/Summary, historical 01-05 Plan, PR #28 review evidence, donor commit range d696b9c^..a27141b, src/mini_agent/application/records.py, src/mini_agent/application/ports.py</read_first>
  <action>
PRECHECK: Prove execution HEAD and merge-base equal 64992cf3bdc6205e00d0c36433309b1657a57531, branch/worktree match this Packet, status is clean, all 14 owned paths are absent at execution base and PLANNING_CONTRACT_SHA, and the historical donor range changes exactly the same 14 paths. Enumerate every donor commit and reject replay if any commit touches a fifteenth path.

REPLAY: Apply the historical donor range without creating a merge, rebase or commit on the historical branch. Before repair, prove all 14 staged/worktree blobs equal donor head a27141ba902015af34602fe15eeec4ba44482687, then create one atomic replay commit named `chore(01-05R): replay reviewed runtime donor`. Historical PR #28 remains untouched.

RED: Update only `test_agent_run_service.py` so its Runtime spy treats `FinalizeRunCommand` as one aggregate and can prove zero partial projection on non-APPLIED. Cover with-Task and no-Task normal completion, exact result/ASSISTANT Message/timestamps, ordered terminal events, absence of standalone terminal Task transition/Message/Trace writes, APPLIED-after-which-no-await, aggregate conflict/error/cancellation, and FAILED's four empty terminal projections. Replace the two historical tests that accepted missing post-commit Message/RunStopped with assertions that those standalone Ports are never invoked. Run the focused AgentRun test before production changes. It must fail because the donor still performs split terminal writes, not because of import, malformed fixture or unrelated behavior. Commit `test(01-05R): require atomic terminal turn consumption`.
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py -x</automated>
  </verify>
  <acceptance_criteria>
    - donor replay commit contains exactly the 14 owned files and every blob initially equals a27141b
    - historical branch and Draft PR #28 remain unchanged
    - RED is reproducible on the replayed donor with production source unchanged
    - RED specifically exposes the earlier terminal Task write and later best-effort Message/RunStopped path
    - FAILED closure fixture requires no fabricated result, Message or terminal Trace
    - no forbidden file changes
  </acceptance_criteria>
  <done>The replacement branch has auditable historical lineage and a new failing contract test that precisely reproduces the remaining PR #28 blocker against 01-04H.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN / REFACTOR consume the atomic terminal-turn aggregate</name>
  <files>src/mini_agent/application/agent_run_service.py, tests/component/application/test_agent_run_service.py</files>
  <read_first>Task 1 RED output, 01-04H FinalizeRunCommand/RuntimeRecordPort contract tests, active Thin Slice §10.3/11, historical Runtime cancellation/failure tests</read_first>
  <action>
GREEN: Change only `agent_run_service.py` plus any fixture/assertion completion inside its paired test. For every normal product stop, compute `completed_at` once, construct the exact terminal `AgentRunResult`, ASSISTANT `MessageRecord`, `RunStopped`, and—when a Task exists—the unpersisted `ApplyTaskTransitionCommand` plus `TaskStateChanged`. Send the complete projection through one `finalize_run_if_active(FinalizeRunCommand(...))`. Remove the normal terminal call to `apply_task_transition_if_current`, standalone terminal `TaskStateChanged`, `_publish_committed_result`, post-commit ASSISTANT append, post-commit `RunStopped` append and degradation-warning path. Only APPLIED sets the local committed cursor and returns the result. There is no terminal persistence await after APPLIED.

Preserve the non-terminal stale-state hook transition, USER Message persistence, non-terminal Trace, Tool lifecycle/cancellation finalization, current-Task reload failure closure and restart recovery behavior. Exceptional FAILED finalization carries no task_transition, terminal_result, assistant_message or terminal_trace_events. Do not modify shared contract files or turn physical Adapter rollback into a Runtime claim.

REFACTOR: Keep exact terminal builders private to `agent_run_service.py`; do not add a file or shared Port. Run directed terminal tests, all seven Packet focused files, migration regression and full suite. Commit `fix(01-05R): consume atomic terminal turn aggregate`; optional later fix commits remain inside the same pair and require fresh exact-head review.
  </action>
  <verify>
    <automated>uv run pytest tests/component/application/test_agent_run_service.py -x</automated>
  </verify>
  <acceptance_criteria>
    - no-Task normal completion submits exactly one aggregate with only RunStopped
    - with-Task normal completion submits exactly one aggregate with the Task transition and ordered TaskStateChanged, RunStopped
    - result, Message, Run, Conversation, Task, RequestUnit, outcome, stop reason and timestamps are exactly bound
    - no normal terminal path calls standalone Task transition, ASSISTANT append or terminal Trace append
    - only APPLIED returns AgentRunResult; conflict/error/cancellation returns no success and Runtime initiates no split terminal write
    - APPLIED is followed by no persistence await
    - FAILED projection remains empty for all four 01-04H terminal fields
    - inherited identity/Gateway/read/presentation/cancellation/failure/recovery matrices remain green
    - the remaining twelve owned blobs equal donor head and base-to-head diff is exactly all 14 owned paths
  </acceptance_criteria>
  <done>The Runtime consumes 01-04H as the sole normal terminal commit point without claiming the future PostgreSQL transaction or vertical integration.</done>
</task>

</tasks>

<verification>

1. Prove exact execution base `64992cf3bdc6205e00d0c36433309b1657a57531`, official planning provenance, branch/worktree and initially absent owned files. Resolve `PLANNING_CONTRACT_SHA` to the official integration ref after this planning PR merges; read this Plan and 01-04H Summary from that Git object.
2. Record donor head/tree/range, prove every donor commit stays inside the 14-file allowlist, create one controlled replay commit, then retain the replacement terminal RED output/commit and GREEN output/commit in order. Historical RED/GREEN remains lineage, not a fabricated new run.
3. Run the exact Packet focused gate:

```bash
uv run pytest \
  tests/component/core/test_request_processing.py \
  tests/component/core/test_control_gateway.py \
  tests/component/core/test_presentation_policy.py \
  tests/component/application/test_agent_run_service.py \
  tests/component/application/test_read_tool_executor.py \
  tests/component/application/test_deterministic_renderer.py \
  tests/component/application/test_restart_recovery_service.py -x
```

4. From the execution Worktree root run the configured repository full gate. Reuse the Integrator-owned Compose project so parallel Worktrees do not create competing fixed-port projects; the migration regression itself uses disposable `db-test` schemas:

```bash
uv sync --all-groups
docker compose -p mini-agent \
  -f /Users/ming/projects/mini-agent/compose.yaml \
  --profile test up --wait -d db-test
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest
```

5. Run `uv run python -m compileall -q src tests` and `git diff --check`. Do not invent app-start, repository-wide lint, type-check or build gates.
6. Compute normalized paths for `git diff --name-only 64992cf3bdc6205e00d0c36433309b1657a57531...<feature-head>` and prove exact set equality with all 14 `owned_files`: cardinality 14, no missing planned path and no extra path. Every frozen Core/Application contract, dependency, artifact, active doc, Composition Root and Graphify path remains byte-identical in that range.
7. Compare every owned path to donor head `a27141ba902015af34602fe15eeec4ba44482687`: exactly `agent_run_service.py` and `test_agent_run_service.py` may differ; the other twelve blob IDs must be byte-identical. Prove `records.py`, `ports.py` and all 01-04H tests are unchanged from execution base.
8. Perform a read-only cross-file impact scan from canonical owners. If a required correction falls outside the allowlist, stop and hand it to Integrator rather than writing it.
9. Create an independent temporary compatibility overlay whose parent is the latest official integration head, apply the published feature delta there without rebasing, force-pushing or otherwise rewriting the published feature branch, and record exact `OVERLAY_PARENT` / `OVERLAY_HEAD`. Rerun focused/full gates, then compute normalized paths for `git diff --name-only <overlay-parent>...<overlay-head>` and prove exact set equality with the same 14 `owned_files`; pre-existing planning/Eval files remain in the overlay parent and outside this diff. Obtain independent correctness/security/contract/test-gap review against the resulting exact overlay head.
10. Integrator reviews and merges 01-05R first, runs full/Graphify gates, and only then issues 01-06R from the new exact integration SHA. Eval PR #29 remains Draft until both replacement merges and its own latest-integration replay/review pass.

</verification>

<nonclaims>

- No HTTP route, SessionAuth, 401/422/500 transport mapping or application startup is implemented.
- No PostgreSQL Adapter, migration, physical transaction, closed-set query or readiness endpoint is implemented or verified.
- No real Provider SDK/raw-envelope decoder, Eval artifact loader, Scripted Provider, Harness, grader, EvalResult or Qwen baseline is implemented.
- No Composition Root, local fixture seed assembly, real Runtime/Infra/Eval wiring, Trajectory/E2E result, Case activation, Requirement completion or Phase completion is produced.
- No `get_shipment`, RAG Evidence, refund, Action Ledger execution or `create_refund` behavior is added.
- Component spy/fake evidence is not HTTP/PostgreSQL/production evidence.
- Runtime construction of recovery commands is not proof that a physical Adapter commits them atomically; physical persistence remains an independent Infra responsibility and the combined evidence gate belongs to 01-08.
- A Runtime guarantee of “no terminal persistence await after APPLIED” is not HTTP delivery, PostgreSQL rollback, exactly-once response delivery or crash-recovery proof.

</nonclaims>

<handoff>

01-06R is not yet issued. Only after this Packet receives exact-head PASS, reviewed merge, full regression and Graphify gate may the Integrator create a new planning-status PR that freezes that then-current integration SHA, the historical 13-file Infra ownership, both Infra review findings and physical terminal aggregate rollback tests.

01-07 Eval PR #29 head `b8ecbb0a7d69761911213a8433b50c6062116c79` has a bounded independent PASS for its own exact feature head, but remains Draft. It must not import or instantiate `AgentRunService`, `AfterRevalidationHook` or other Runtime-private code. After Runtime and Infra merge, Integrator must build a latest-integration overlay, rerun its focused/full/zero-network gates and obtain a fresh exact-head review before merge.

01-08 Integrator alone:

- imports these Runtime services into `bootstrap.py`;
- registers and persists the concrete `get_order` snapshot/artifact;
- wires Session, HTTP, PostgreSQL records/recovery/order, Provider and Eval SUT;
- adapts the independently implemented Eval stale-fault directive to the Runtime-local `AfterRevalidationHook`, including non-`APPLIED` → `EvalExecutionFailure` handling;
- decides external startup readiness behavior for non-ready recovery outcomes;
- proves Message-before-RU, accepted-graph-before-Gate, Gate-before-Tool, fence-before-read and Observation-before-presentation across concrete adapters;
- runs HTTP E2E01-01/04, privacy, PostgreSQL-backed Trace/Eval and final lifecycle gates;
- updates no canonical contract without a separate owner decision.

</handoff>

<success_criteria>

- Controlled donor replay is auditable; the new terminal regression has reproducible RED followed by GREEN; inherited historical behavior and optional refactors remain green.
- Exact focused and full repository gates pass at the reviewed feature head and latest-integration overlay; both normalized changed-file sets equal the exact 14 `owned_files`, using `64992cf...feature-head` for ownership and `overlay-parent...overlay-head` for compatibility.
- Exactly twelve owned blobs equal historical donor head; only the AgentRun consumer/test pair differs to consume 01-04H.
- Runtime enforces trusted identity, deterministic binding, stale-state rejection, immutable Gateway and durable read dispatch with zero forbidden side effects.
- Success, not-found/privacy, unknown-tool, protocol/system/presentation and restart behavior match the frozen path matrix.
- Presentation facts originate only from safe Observation, and Trace/results contain no raw payload, raw Token or private identity.
- Restart recovery never resumes/replays and carries the exact atomic Trace input required by 01-04G.
- Every normal terminal path uses one complete 01-04H aggregate, has no split terminal write, and returns only after APPLIED.
- Actual feature changes equal the exact 14 files; contract changes and new dependencies remain `NONE`.
- Handoff states Component-only evidence and preserves every 01-08 composition/E2E boundary.

</success_criteria>

<output>
Execution writes no Summary or shared State. It returns a handoff reporting donor/replay lineage, replacement RED/GREEN/REFACTOR commits, exact files/blob equality, focused/full counts, terminal and inherited behavior matrices, threats, independent review, latest-integration compatibility, nonclaims, rollback and 01-06R/01-08 dependencies. Integrator alone creates a later Summary/status PR and Graphify artifacts after reviewed merge.
</output>
