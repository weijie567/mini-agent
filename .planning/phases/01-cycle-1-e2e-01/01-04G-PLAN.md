---
phase: 01-cycle-1-e2e-01
plan: 04G
type: tdd
wave: 8
depends_on:
  - 01-04F
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
    - "RestartRecoveryPort requires a compliant Adapter to commit an APPLIED Run, Task, RequestUnit, ToolCall, RunTaskLink and exact recovery Trace projection in one atomic transaction; this Packet does not implement the Adapter."
    - "Recovery Trace is produced by Core/Runtime and carried by ApplyRestartRecoveryCommand; Infrastructure does not invent lifecycle events."
    - "The command contains exactly one RunStopped event, exactly one TaskStateChanged per Task transition, and exactly one ToolCallInterrupted per ToolCall transition."
    - "RunStopped records BLOCKED / PROCESS_RESTART_DETECTED for the same Run; every ToolCallInterrupted and TaskStateChanged event binds the exact transitioned identity."
    - "CLOSURE_CONFLICT, NOT_APPLICABLE and RECONCILIATION_REQUIRED commit neither state nor Trace."
    - "A post-commit append_trace_event call cannot substitute for the atomic recovery command."
    - "Every recovery event rejects unrelated non-empty optional TraceEvent fields, preventing cross-kind audit payload contamination."
    - "No TraceEvent structural field, event vocabulary, StopReason or recovery state transition is redesigned."
  artifacts:
    - "ApplyRestartRecoveryCommand owns a bounded exact recovery_trace_events tuple."
    - "RestartRecoveryPort documents state-and-Trace atomicity for APPLIED and zero writes for every other result."
    - "Application contract tests reject missing, extra, duplicate, wrong-run, wrong-kind and wrong-projection recovery events."
  key_links:
    - "Task transitions map bijectively to TaskStateChanged events."
    - "ToolCall transitions map bijectively to ToolCallInterrupted events."
    - "Run transition maps to one RunStopped event carrying PROCESS_RESTART_DETECTED."
    - "claim_and_apply_restart_recovery persists the entire command or no command projection."
---

<objective>
关闭 startup recovery 状态提交成功但 mandatory Trace 只能事后追加的永久 crash window。

Purpose: 冻结 recovery 状态事实与审计事实不可分裂的 Application Port contract，同时保持 Core 产生状态/Trace、Infrastructure 只做原子持久化的边界；本 Packet 不实现物理事务。

Output: 两个 Application contract 文件和两个既有 Component contract tests；不修改 Core Trace schema、Runtime behavior、数据库 Adapter 或 migration。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-04D-SUMMARY.md
@src/mini_agent/application/records.py
@src/mini_agent/application/ports.py
@src/mini_agent/core/trace.py
@tests/component/application/test_record_contracts.py
@tests/component/application/test_ports_contract.py

本 Plan 使用受控 GSD planner / checker adapter。Integrator 已预建独立 execution Worktree；executor 只能写 exact four-file allowlist。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-recovery-trace-atomicity`
base_branch: `integration/e2e01-thin`
base_sha: `a84d30188eaec75e45619e9939180ba78efa3b80`
worktree_id: `e2e01-01-recovery-trace-atomicity`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-01-recovery-trace-atomicity`
writer: `Application recovery/Trace boundary sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer`

owned_files:

- `src/mini_agent/application/records.py`
- `src/mini_agent/application/ports.py`
- `tests/component/application/test_record_contracts.py`
- `tests/component/application/test_ports_contract.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/**`
- `src/mini_agent/application/persistence.py`
- `src/mini_agent/core/**`
- `src/mini_agent/infrastructure/**`
- `src/mini_agent/evaluation/**`
- every other test file
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8 and graphify
- `.planning/GOVERNANCE.md` Task Packet, lifecycle and post-merge Graphify gates
- `PROJECT_DIRECTION.md` Application/Core Port ownership
- `docs/architecture/memory-design-reference.md` restart recovery and Trace audit semantics
- `docs/architecture/tool-calling-design-reference.md` ToolCall interruption semantics
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` scoped recovery behavior
- `src/mini_agent/core/trace.py`, `src/mini_agent/core/task_state.py`, `src/mini_agent/core/tool_system.py` and exact Application records/ports at `base_sha`

dependencies:

- 01-04D PR #21 merge / exact execution base `a84d30188eaec75e45619e9939180ba78efa3b80`
- 01-04E and 01-04F owner PRs plus their Integrator-owned Graphify gates must complete before any 01-04G implementation write; executor captures the official integration SHA containing both dependencies, proves all four G-owned files are byte-identical to `base_sha`, and reads the merged contracts through Git even though this disjoint branch retains `base_sha`
- before PR readiness, the complete G branch must revalidate against the latest integration head containing E and F
- planning-status PR containing this Plan must merge before implementation writing starts
- executor captures planning merge / Plan blob from the official ref and proves all four owned files were unchanged by planning

required_checks:

- exact base, branch, merge-base, planning provenance and clean-worktree preflight
- RED demonstrates current command can be valid without any recovery Trace
- GREEN adds `recovery_trace_events: tuple[TraceEvent, ...]` with bounded length 1..3 for the current max-one Task / ToolCall slice
- exact Run/Task/Tool event bijection, identity, event type, terminal status, stop reason and timestamp/projection binding
- per-kind allowed-field checks reject every unrelated non-empty optional TraceEvent projection and cross-kind contamination
- Port docs require one atomic transaction for APPLIED and zero state/Trace writes for all other RecoveryWriteResult values
- existing normal `RuntimeRecordPort.append_trace_event` remains available but is explicitly insufficient for recovery atomicity
- focused Application tests, full `uv run pytest`, exact-file ruff/format, compileall and `git diff --check`
- exact four-file containment, cross-file impact scan and independent exact-head review
- after merge, Integrator-only `graphify update .` freshness/health check before W2 planning

done_when:

- exact four-file Packet has one reviewed feature commit
- command and Port cannot express APPLIED recovery without exact Trace
- focused/full regression passes
- draft PR targets `integration/e2e01-thin` and is merged after 01-04F
- no Case, Requirement or numbered Phase lifecycle advances

contract_changes: `YES / APPLICATION RECOVERY-TRACE ATOMICITY`
security_impact: `YES` — eliminates a crash window that could erase audit evidence for security-relevant recovery transitions.
eval_impact: `YES / CONTRACT ONLY` — later Trajectory/E2E graders can require recovery Trace; no Eval result is created.
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer does not modify `graphify-out/**`; after merge the Integrator runs `graphify update .`, verifies graph structure/freshness, no stale marker and a clean tracked tree, and blocks W2 planning on failure.
rollback: Close before merge or use a normal revert PR and re-block W2. Never reset, force-push, delete shared Worktrees or rewrite persisted history.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan blob
- exact four-file containment
- RED/GREEN commands, event bijection and per-kind allowed-field matrix
- Port APPLIED/non-APPLIED atomicity contract and explicit Adapter nonclaim
- focused/full results, contract/security/Eval impact and cross-file scan
- independent exact-head review, post-merge Graphify disposition, unresolved risks and rollback
</task_packet>

<interfaces>

Add to `ApplyRestartRecoveryCommand`:

```python
recovery_trace_events: Annotated[
    tuple[TraceEvent, ...],
    Field(min_length=1, max_length=3),
]
```

Exact event set:

- one `TraceEventType.RUN_STOPPED`
  - `run_id == expected_closure.active_run_record.run_id`
  - `user_outcome is AgentOutcome.BLOCKED`
  - `stop_reason is StopReason.PROCESS_RESTART_DETECTED`
  - `occurred_at == run_transition.incomplete_record.completed_at`
- for each `ApplyTaskTransitionCommand`, exactly one `TraceEventType.TASK_STATE_CHANGED`
  - same `run_id`
  - `task_id == next_task_record.task_id`
  - `request_unit_id == next_request_unit_record.request_unit_id`
  - `occurred_at == task_state_transition.changed_at`
- for each `InterruptToolCallForRecoveryCommand`, exactly one `TraceEventType.TOOL_CALL_INTERRUPTED`
  - same `run_id`
  - `tool_call_id == interrupted_record.tool_call_id`
  - `tool_call_terminal_status is ToolCallStatus.INTERRUPTED`
  - `occurred_at == interrupted_record.finished_at`

All `trace_event_id` values are unique. No other event type is accepted. The exact set is 1–3 events because the first slice caps Task and ToolCall recovery families at one each.

Per-event exact projection allowlist:

- common required fields for every event: `trace_event_id`, `event_type`, `occurred_at`, `run_id`;
- `RUN_STOPPED` additionally allows only `user_outcome` and `stop_reason`;
- `TASK_STATE_CHANGED` additionally allows only `task_id` and `request_unit_id`;
- `TOOL_CALL_INTERRUPTED` additionally allows only `tool_call_id` and `tool_call_terminal_status`;
- every other optional `TraceEvent` field must retain its canonical empty default (`None` or an empty tuple). A non-empty `case_id`, message/model/context/toolset/gate/Observation/presentation/timing field, a cross-kind Task/Tool/Run field, or non-empty `argument_binding_refs` invalidates the command.

Port outcome semantics:

```text
APPLIED
  → revalidate exact closure/fence
  → compliant Adapter must commit every state/link projection and every recovery_trace_event atomically

CLOSURE_CONFLICT | NOT_APPLICABLE | RECONCILIATION_REQUIRED
  → zero state writes
  → zero Trace writes
```

Integrity failure still raises the existing bounded `P0PersistenceIntegrityError`.

</interfaces>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `REC-R01` | Repudiation | recovery state → Trace | `MITIGATE / BLOCK` | state and exact Core-produced events share one atomic command/transaction |
| `REC-T01` | Tampering | Runtime command → Adapter | `MITIGATE / BLOCK` | command validates event bijection, identities, types, statuses, timestamps and exact per-kind allowed fields |
| `REC-S01` | Spoofing | Infrastructure → Core event | `MITIGATE` | Adapter persists supplied canonical TraceEvent only; it never synthesizes one |
| `REC-D01` | Denial of Service | recovery event set | `MITIGATE` | tuple is bounded to 1..3 and duplicates/extras fail before Adapter work |
| `REC-E01` | Elevation of Privilege | non-APPLIED outcome | `MITIGATE / BLOCK` | conflict/not-applicable/reconciliation guarantee zero state and Trace writes |

</threat_model>

<feature>
  <name>Atomic restart recovery state and Trace</name>
  <files>src/mini_agent/application/records.py, src/mini_agent/application/ports.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <behavior>
    - a CREATED Run recovery requires only one matching RunStopped event
    - a Run with one active Task and one active ToolCall requires RunStopped + TaskStateChanged + ToolCallInterrupted
    - missing, extra, duplicate, wrong-run, wrong-identity, wrong-kind, wrong-status or wrong-time events fail command validation
    - any unrelated optional or cross-kind TraceEvent projection fails command validation
    - non-APPLIED Port results persist neither projections nor events
  </behavior>
  <implementation>Import and consume existing Core TraceEvent types only. Add the exact field, event bijection and per-kind allowed-field validator rules in the interfaces block, update Port documentation, and keep all existing recovery closure/fence/bijection checks. Do not change Core Trace schema or create a recovery-only Trace DTO.</implementation>
</feature>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — prove current recovery command permits Trace loss</name>
  <files>tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <read_first>AGENTS.md, src/mini_agent/application/records.py, src/mini_agent/application/ports.py, src/mini_agent/core/trace.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</read_first>
  <action>Extend the existing recovery command factories/tests with the exact Trace sets in the interfaces block. Add negative tests for every missing/extra/duplicate/wrong binding category, plus cross-kind/unrelated optional payload contamination on each allowed event (for example RunStopped with task_id, TaskStateChanged with tool_call_id or non-empty argument_binding_refs, and ToolCallInterrupted with user_outcome or model fields). Add Port documentation assertions for APPLIED atomicity / non-APPLIED zero writes. Run focused tests before source changes and record failure because the field/contract is absent.</action>
  <verify>`uv run pytest tests/component/application/test_record_contracts.py tests/component/application/test_ports_contract.py -x` must fail on the new recovery-Trace contract before GREEN changes.</verify>
  <acceptance_criteria>
    - RED failure is caused by absent recovery_trace_events behavior
    - tests use only existing TraceEvent/Core enums
    - CREATED and RUNNING closure shapes are both covered
    - RUNNING ACTION / RECONCILIATION_REQUIRED remains zero-write
  </acceptance_criteria>
  <done>The permanent post-commit Trace gap is mechanically demonstrated.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN / REFACTOR — freeze exact event bijection and Port atomicity</name>
  <files>src/mini_agent/application/records.py, src/mini_agent/application/ports.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</files>
  <read_first>AGENTS.md, PROJECT_DIRECTION.md, docs/architecture/memory-design-reference.md, docs/implementation/e2e01-thin-slice-implementation-spec.md, src/mini_agent/application/records.py, src/mini_agent/application/ports.py, src/mini_agent/core/trace.py, tests/component/application/test_record_contracts.py, tests/component/application/test_ports_contract.py</read_first>
  <action>Add the exact field, event bijection, per-kind allowed-field validator and Port wording from the interfaces block. Preserve all existing closure/fence/state/link checks and normal append_trace_event capability. Do not add StopReasons, result enum values, retries, Adapter logic or Core fields. Refactor only within the four-file allowlist.</action>
  <verify>Run focused tests, then `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` on the exact four files, `uv run python -m compileall -q src tests`, and `git diff --check`; all exit 0.</verify>
  <acceptance_criteria>
    - command requires 1..3 events and validates the exact set
    - one RunStopped is always required
    - Task/Tool event cardinality equals actual transition cardinality
    - unrelated optional and cross-kind event projections are rejected
    - non-APPLIED result wording explicitly guarantees zero Trace writes
    - Core Trace files and every forbidden file remain byte-identical
    - full regression and exact four-file containment pass
  </acceptance_criteria>
  <done>The Application Port contract cannot express an APPLIED recovery without its complete bounded Trace projection; physical atomicity remains for the Adapter to implement and prove.</done>
</task>

</tasks>

<verification>

1. Prove exact base/planning provenance and four-file containment.
2. Capture RED/GREEN evidence and run all canonical offline tests.
3. Inspect every `ApplyRestartRecoveryCommand` constructor and every RestartRecoveryPort method signature/doc.
4. Run cross-file impact scan over Runtime/Infra plans, persistence codec and Thin Slice Spec; report without forbidden-file writes.
5. Obtain independent exact-head review before PR readiness and serial merge.
6. After merge, Integrator runs the declared Graphify freshness/health gate before W2 planning.

</verification>

<success_criteria>

- The Port contract requires APPLIED recovery to carry an atomic, exact and bounded Trace set; no physical Adapter is implemented here.
- The Port contract requires every non-APPLIED result to remain a total zero-write outcome.
- A compliant Infrastructure Adapter cannot synthesize or omit Core recovery events.
- No Core Trace schema or result vocabulary changes.
- Full regression and exact-head review pass; physical transaction behavior remains `NOT_IMPLEMENTED`.

</success_criteria>

<output>
Execution handoff reports branch/commit/tree, exact files, RED/GREEN commands, event matrix, full regression count, review result, contract/security/Eval impact and rollback. Integrator alone writes later Summary/status.
</output>
