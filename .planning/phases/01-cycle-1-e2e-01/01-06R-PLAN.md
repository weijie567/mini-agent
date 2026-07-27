---
phase: 01-cycle-1-e2e-01
plan: 06R
type: tdd
wave: 11
depends_on:
  - 01-05R
files_modified:
  - src/mini_agent/api/http.py
  - src/mini_agent/infrastructure/auth/p0_session.py
  - src/mini_agent/infrastructure/order/postgres.py
  - src/mini_agent/infrastructure/persistence/models.py
  - src/mini_agent/infrastructure/persistence/postgres.py
  - src/mini_agent/infrastructure/persistence/recovery.py
  - alembic/versions/20260727_0002_p0_records.py
  - tests/integration/test_database_migrations.py
  - tests/integration/test_http_session_adapter.py
  - tests/integration/test_postgres_record_adapters.py
  - tests/integration/test_postgres_atomicity.py
  - tests/integration/test_postgres_recovery.py
  - tests/integration/test_postgres_get_order.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "Infrastructure implements the frozen HTTP, Session, owner-scoped order, persistence and recovery Ports without changing Core/Application contracts."
    - "All 17 P0 record codes and five command-supplied external relations round-trip through the existing strict codec and normalized physical references."
    - "TrustedOwnerScope participates in the SQL predicate before private payload selection; stored owner metadata never grants authority."
    - "Foreign O-2001 and nonexistent O-9999 are indistinguishable and expose no private payload or raw database diagnostic."
    - "Malformed physical envelopes and normalized references produce only fresh bounded integrity errors with no raw Pydantic value, cause or context."
    - "insert_tool_call locks and strictly validates its parent Run as RUNNING before any ToolCall/reference write; recovery-first cannot create a late orphan ToolCall."
    - "FinalizeRunCommand APPLIED commits optional Task/RequestUnit transition, terminal Run/link, ASSISTANT Message and exact terminal Trace in one PostgreSQL transaction."
    - "Every terminal child-write fault, stale CAS and non-APPLIED result rolls back the entire physical aggregate."
    - "Recovery APPLIED atomically commits state/link projections with exact recovery Trace; every non-APPLIED result commits neither state nor Trace."
    - "This Packet does not create Composition Root, global app startup, Runtime/Eval wiring, Trajectory/E2E Result or product-completion evidence."
  artifacts:
    - "A schema-aware migration/models pair for p0_records, normalized references and mock_orders."
    - "PostgreSQL adapters for frozen record, recovery and owner-scoped get_order Ports."
    - "Injected HTTP/Session boundary and exact six integration-test files."
  key_links:
    - "FinalizeRunCommand maps to one physical transaction over Task/RequestUnit/Run/link/Message/Trace projections."
    - "CreateToolCallCommand maps to a locked, strictly decoded RUNNING parent Run before insert."
    - "Physical envelope/reference parsing maps all validation failures to bounded persistence integrity categories."
    - "TrustedOwnerScope maps to scope_owner_customer_id in the SQL predicate before decode."
---

# Phase 1 Plan 01-06R｜W2 Infrastructure replacement

> **ISSUED REPLACEMENT TASK PACKET / IMPLEMENTATION NOT STARTED**
> 本 Plan 是 historical 01-06 / Draft PR #30 的唯一 replacement Packet。它从 01-05R reviewed merge `fb607019...` 建立新的 execution identity，只受控 replay historical head `054dcaf...` 的 exact 13 files，再关闭两项 Infra review HIGH与01-04H physical terminal transaction。历史Plan、branch与PR保持不可变证据，绝不rebase、force-push或冒充本Packet。

> **DERIVED / NON_NORMATIVE**
> 本 Plan只把active canonical owner、01-04D/G/H contracts、01-05R reviewed Runtime consumer与historical Infra review evidence转换为可执行Task Packet。它不拥有产品、Core/Application contract、Eval Case、lifecycle或发布语义。

<objective>
在不改写 historical PR #30 的前提下，受控 replay其 exact 13-file Infrastructure实现，修复physical parsing disclosure与recovery-first late ToolCall，并把01-04H complete terminal aggregate作为一个PostgreSQL条件事务提交。

Purpose: 为后续Eval latest-integration replay与01-08真实纵向wiring提供不会泄露raw validation、不会制造orphan ToolCall、不会提交partial terminal turn的physical Adapter。

Output: exact 13-file Packet；最终只允许`postgres.py`与三份定向integration tests相对donor改变，其他九个owned blobs必须byte-identical。不修改Runtime、Eval、canonical docs、Composition Root、dependency或shared test bootstrap。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-W2-RESEARCH.md
@.planning/phases/01-cycle-1-e2e-01/01-W2-PATTERNS.md
@.planning/phases/01-cycle-1-e2e-01/01-W2-VALIDATION.md
@.planning/phases/01-cycle-1-e2e-01/01-04G-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-04H-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-05R-PLAN.md
@.planning/phases/01-cycle-1-e2e-01/01-05R-SUMMARY.md
@src/mini_agent/application/ports.py
@src/mini_agent/application/records.py
@src/mini_agent/application/persistence.py
@src/mini_agent/core/identity.py
@src/mini_agent/core/order.py
@src/mini_agent/core/trace.py
@src/mini_agent/infrastructure/persistence/database.py
@src/mini_agent/infrastructure/persistence/models.py
@alembic/versions/20260726_0001_initial_persistence.py
@tests/conftest.py
@tests/integration/test_database_migrations.py

本 Plan只有在planning PR合并后、Integrator从`<task_packet>.base_sha`预建独立execution Worktree，并记录branch / merge-base / clean-state / Plan provenance后才可执行。Executor只能写exact 13 owned files。Historical donor只提供受控blob lineage；每组replacement production change前都必须先取得对应真实RED，形成两个可独立执行的RED→GREEN循环。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-w2-infra-r`
base_branch: `integration/e2e01-thin`
base_sha: `fb607019130843c94825a47d7822518cbdb2143c`
base_tree: `4b6432082a6c022ae4edee15264c83339fd444a0`
worktree_id: `e2e01-w2-infra-r`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-w2-infra-r`
writer: `Infrastructure sole writer, supervised by /root Integrator`
agent_role: `infra-engineer`

owned_files:

- `src/mini_agent/api/http.py`
- `src/mini_agent/infrastructure/auth/p0_session.py`
- `src/mini_agent/infrastructure/order/postgres.py`
- `src/mini_agent/infrastructure/persistence/models.py`
- `src/mini_agent/infrastructure/persistence/postgres.py`
- `src/mini_agent/infrastructure/persistence/recovery.py`
- `alembic/versions/20260727_0002_p0_records.py`
- `tests/integration/test_database_migrations.py`
- `tests/integration/test_http_session_adapter.py`
- `tests/integration/test_postgres_record_adapters.py`
- `tests/integration/test_postgres_atomicity.py`
- `tests/integration/test_postgres_recovery.py`
- `tests/integration/test_postgres_get_order.py`

allowed_donor_deltas:

- `src/mini_agent/infrastructure/persistence/postgres.py`
- `tests/integration/test_postgres_record_adapters.py`
- `tests/integration/test_postgres_atomicity.py`
- `tests/integration/test_postgres_recovery.py`

required_donor_equal_blobs:

- `alembic/versions/20260727_0002_p0_records.py` = `4e4c214a6f95dcf87997f88ab5478b18ed46d488`
- `src/mini_agent/api/http.py` = `d42e9c6440f5206e68844c81a44516a3308f84f2`
- `src/mini_agent/infrastructure/auth/p0_session.py` = `d37721111e2a05115f68a0fc13230982b2b744f2`
- `src/mini_agent/infrastructure/order/postgres.py` = `e1909e06bac2e64b8349154f66c2b777164f1847`
- `src/mini_agent/infrastructure/persistence/models.py` = `a11b31ea8137dcf04b69dccf42489d6f02adeccd`
- `src/mini_agent/infrastructure/persistence/recovery.py` = `706fc32bcbd29ef4d5f342533d7b0a35d34ad900`
- `tests/integration/test_database_migrations.py` = `38ef3db1a1ee6cb7131a97f88bce89d9c88892ba`
- `tests/integration/test_http_session_adapter.py` = `ce5daaa2d044ebe3c8b80ae77b02abcc5b51a5b5`
- `tests/integration/test_postgres_get_order.py` = `df6bef3de4c4925f4ccbc2cdf6bc071beb2a0b42`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- `docs/**`
- `src/mini_agent/core/**`
- `src/mini_agent/application/**`
- `src/mini_agent/evaluation/**`
- `src/mini_agent/bootstrap.py`
- `src/mini_agent/main.py`
- `src/mini_agent/infrastructure/persistence/database.py`
- every other Infrastructure file
- every other test file
- `tests/conftest.py`
- `evals/**`
- `alembic/env.py`
- `alembic.ini`
- every other Alembic revision
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 0–8 and graphify
- `docs/business-capabilities.md` P0 E2E-01, Mock Order and disclosure boundary
- `docs/architecture/intent-design-reference.md` trusted RequestUnit/InputBinding boundary
- `docs/architecture/tool-calling-design-reference.md` dispatch fence, ToolCall and restart semantics
- `docs/architecture/memory-design-reference.md` owner-scoped persistence, exact decode, terminal/recovery Trace
- `docs/evaluation/agent-evaluation-strategy.md` Trace/Eval evidence boundary
- `docs/implementation/e2e01-thin-slice-implementation-spec.md` HTTP, Session, get_order, persistence and error mapping
- frozen Core/Application source at `base_sha`

dependencies:

- 01-05R reviewed merge `fb607019130843c94825a47d7822518cbdb2143c` is the exact execution base and includes the complete Runtime terminal aggregate consumer
- this Plan must merge through a dedicated planning-status PR before implementation writes begin
- executor records `PLANNING_CONTRACT_SHA`, merged Plan blob and 01-05R Summary blob, then proves all 13 owned paths are byte-identical between `base_sha` and the planning merge
- historical donor PR #30/head `054dcaf2d4101b0bd422ddb3b3eb47b734523bc1`/tree `b0ec302de8dce6f3740c7f9a78fcc4aaa43c85d9` is a read-only replay source, never an execution base or merge target
- donor range `c35687dafa3881bb322d91515068d8d39be79df6..054dcaf2d4101b0bd422ddb3b3eb47b734523bc1` contains five linear commits and exact 13 owned paths
- all 13 owned paths are unchanged from donor base `c35687d...` to execution base `fb607019...`; current base has two pre-existing paths and eleven absent paths
- Eval PR #29 remains Draft and must wait for this Packet's reviewed merge plus its own latest-integration replay/review

required_checks:

- exact base, branch, merge-base, planning provenance and clean-worktree preflight
- donor five-commit/per-commit/cumulative exact 13-file containment and no historical PR mutation
- replay point has 13/13 donor blob equality
- first test-only RED covers raw envelope/reference disclosure and both recovery/ToolCall orderings; second test-only RED covers complete terminal physical aggregate/rollback only after the first GREEN
- owner-scoped reads/recovery expose no raw secret, Pydantic detail, cause or context
- recovery-first rejects late ToolCall before any write; insert-first causes recovery conflict/reload and no orphan
- with-Task/no-Task COMPLETED and FAILED terminal sets match 01-04H exactly
- every terminal child fault, stale CAS and non-APPLIED path restores the complete before-snapshot
- migration upgrade→downgrade→upgrade, 17-code/five-reference round-trip, exact replay and recovery bounds remain green
- trusted Session, auth-before-handler and O-2001/O-9999 indistinguishability remain donor-equal and green
- Packet focused, full, compileall, `git diff --check` and exact 13-file set equality
- final four allowed-delta blobs differ from donor and nine required-equality blobs equal donor exactly
- latest-integration overlay diff also equals exact 13 owned paths and passes focused/full gates
- independent correctness/security/contract/test-gap review against exact feature and overlay heads
- read-only cross-file impact scan; any required forbidden-file change stops execution

done_when:

- replay, two directed test-only RED commits and their two corresponding GREEN commits are recorded in executable order
- feature and overlay changed-file sets both equal exact 13 owned paths
- four allowed-delta blobs contain only reviewed fixes and nine other owned blobs equal donor exactly
- physical aggregate APPLIED is all-or-nothing; every child fault/non-APPLIED result leaves zero partial projection
- raw physical validation and database failures expose only bounded errors
- draft PR targets `integration/e2e01-thin` and reports all nonclaims
- no Case, Requirement or numbered Phase lifecycle advances

contract_changes: `NONE`
security_impact: `YES` — implements trusted identity, least-disclosure reads, bounded persistence failures, parent-Run ToolCall fence and physical terminal/recovery atomicity already frozen by canonical owners.
eval_impact: `YES / INFRASTRUCTURE EVIDENCE ONLY` — supplies PostgreSQL/HTTP integration evidence and persists existing Eval record types; no grader, Harness, Result, Case or lifecycle change.
new_dependencies: `NONE`
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer never modifies `graphify-out/**`; Integrator runs Graphify only after reviewed merge.
rollback: Close before merge or use a normal revert PR plus safe migration downgrade in an explicitly targeted disposable schema. Never reset, force-push, delete shared Worktrees, drop an unknown database/schema or rewrite migration history.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan/Summary blobs
- donor base/head/tree/range, five-commit containment and replay commit
- exact 13-file feature/overlay containment, four intentional deltas and nine donor-equal blobs
- real RED plus both GREEN commits and commands
- migration/17-record/five-reference/replay/strict decode evidence
- disclosure, two-order ToolCall/recovery and terminal child-fault transaction matrices
- Session/HTTP/get_order privacy evidence
- focused/full/compileall/diff-check and latest-integration compatibility
- contract/security/Eval impact, independent review, nonclaims, risks and rollback
</task_packet>

<scope_exception>

This cohesive Packet intentionally contains 13 files:

- seven production boundary files: migration, models, persistence, recovery, owner-scoped order, Session and HTTP;
- six direct integration-test files;
- all use one Infrastructure branch, one writer, one frozen Application Port/codec input and one PostgreSQL schema chain;
- nine final blobs are mechanically constrained to donor equality; only four files contain new judgmental changes.

Splitting migration/models from persistence/recovery or Session/order/HTTP from their shared trusted-identity boundary would create cross-Packet ownership and transaction gaps. Thirteen is above the normal review warning but below the 15-file blocker. Any fourteenth changed file, second writer or shared-contract change is a blocker requiring Integrator re-planning.

</scope_exception>

<interfaces>

Bounded physical validation:

```text
raw p0_records.envelope
  → canonical decode_persistence_record(...)
  → strict P0PersistenceEnvelope projection check
  → strict normalized P0RecordReference parity
  → DecodedP0PersistenceRecord
```

- Envelope validation failures map to existing `PAYLOAD_VALIDATION_FAILED`.
- Normalized reference failures map to existing `LINK_PROJECTION_MISMATCH`.
- No new public error enum or exception is introduced.
- The original Pydantic/SQL value, `ValidationError`, cause and context are discarded; the bounded integrity error is raised outside the catch block with `from None`.

Late ToolCall fence:

```text
CreateToolCallCommand
  → lock parent AgentRunRecord FOR UPDATE
  → strict physical decode
  → require AgentRunStatus.RUNNING
  → insert ToolCall + references
  → touch recovery anchor
```

Missing or non-RUNNING parent Run fails before every ToolCall/reference write. Recovery-first produces a bounded rejection; insert-first makes recovery re-evaluate the changed closure and cannot leave an orphan.

Complete terminal transaction:

```text
FinalizeRunCommand
  → stable lock/preflight of every expected row
  → optional Task/RequestUnit CAS + TaskStateTransition
  → terminal AgentRunRecord
  → terminal RunTaskLinkRecord
  → ASSISTANT MessageRecord
  → ordered terminal TraceEvent records
  → COMMIT
```

- `terminal_result` validates result/message/Trace binding and is not an eighteenth record.
- With Task: exact `(TaskStateChanged, RunStopped)`.
- Without Task: exact `(RunStopped,)`.
- FAILED: no task transition, terminal result, ASSISTANT Message or terminal Trace.
- Any child CAS/fault raises an internal payload-free rollback sentinel out of the transaction; only outside the transaction may the Adapter return `PROJECTION_CONFLICT`.
- Returning normally from a partially mutated `with begin()` block is forbidden.

All other schema, recovery closure, Session, HTTP and get_order behavior remains the historical donor implementation and frozen canonical contract.

</interfaces>

<threat_model>

| threat_id | severity | category | boundary | disposition | mitigation / blocking test |
|---|---|---|---|---|---|
| `IF-S01` | HIGH | Spoofing | HTTP/model → identity | `MITIGATE / BLOCK` | Session adapter alone creates CustomerContext; body forbids trusted identity fields |
| `IF-T01` | HIGH | Tampering | physical envelope/reference → DTO | `MITIGATE / BLOCK` | strict canonical decode, projection/reference parity and adversarial malformed rows |
| `IF-T04` | HIGH | Tampering | restart recovery → late ToolCall | `MITIGATE / BLOCK` | locked/decoded parent Run must be RUNNING; both concurrency orders prove no orphan |
| `IF-R03` | HIGH | Repudiation | recovery state → recovery Trace | `MITIGATE / BLOCK` | existing one-transaction recovery command and exact state/Trace rollback |
| `IF-R04` | HIGH | Repudiation | terminal state → result/Message/Trace | `MITIGATE / BLOCK` | one physical terminal transaction plus every-child fault injection |
| `IF-I01` | HIGH | Information Disclosure | private order/records → caller | `MITIGATE / BLOCK` | trusted owner SQL predicate before payload decode; foreign/nonexistent same result |
| `IF-I04` | HIGH | Information Disclosure | physical validation → exception | `MITIGATE / BLOCK` | bounded category, fresh integrity error, `from None`, raw-secret assertions |
| `IF-D01` | MEDIUM | Denial of Service | recovery closure materialization | `MITIGATE` | bounded LIMIT/cardinality/closure fence retained byte-identical |
| `IF-D02` | HIGH | Denial of Service | transaction/lock race | `MITIGATE / BLOCK` | stable lock order, SERIALIZABLE recovery and deterministic no-sleep order tests |
| `IF-E01` | HIGH | Elevation of Privilege | user/model → owner scope | `MITIGATE / BLOCK` | no Gateway/identity contract change; stored metadata never grants authority |

</threat_model>

<feature>
  <name>E2E01-01/04 physical Infrastructure boundaries</name>
  <files>the exact 13-file owned_files list in task_packet</files>
  <behavior>
    - strict 17-record/five-reference PostgreSQL round-trip and bounded physical validation
    - trusted Session/HTTP identity and owner-scoped get_order privacy
    - durable dispatch/recovery ordering with no late orphan ToolCall
    - complete terminal Task/Run/Message/Trace physical transaction and rollback
  </behavior>
  <implementation>Reuse only frozen DTOs, records, commands, enums, codec and Ports. Do not add a generic repository, new persistence error taxonomy, second schema, Composition Root or application startup path.</implementation>
</feature>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: controlled donor replay and disclosure/fence RED</name>
  <files>all exact 13 owned_files for replay; RED edits only tests/integration/test_postgres_record_adapters.py, tests/integration/test_postgres_atomicity.py and tests/integration/test_postgres_recovery.py</files>
  <read_first>AGENTS.md, this Plan from PLANNING_CONTRACT_SHA, 01-05R Summary, historical 01-06 Plan, PR #30 review evidence, donor five-commit range, records.py, ports.py and persistence.py</read_first>
  <action>
PRECHECK: Prove execution HEAD/merge-base equal fb607019130843c94825a47d7822518cbdb2143c, branch/worktree match this Packet, status is clean, planning provenance resolves, all 13 paths are unchanged between base and PLANNING_CONTRACT_SHA, and every donor commit stays inside the same 13-file allowlist.

REPLAY: Materialize donor head 054dcaf2d4101b0bd422ddb3b3eb47b734523bc1 as exact 13 blobs without merge/rebase/history mutation. Prove 13/13 equality, then commit `chore(01-06R): replay reviewed infra donor`.

RED: Production remains donor-equal. Extend only the three allowed tests to cover malformed envelope/reference disclosure on owner read/recovery plus deterministic recovery-first and insert-first ToolCall schedules. Use barriers/events, never sleep. Do not add terminal aggregate/child-fault tests yet. Run the directed tests and retain a real contract-related failure. Commit `test(01-06R): expose persistence disclosure and toolcall fence gaps`.
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py -x</automated>
  </verify>
  <acceptance_criteria>
    - replay commit is exact 13 donor blobs and historical PR #30 is unchanged
    - RED modifies only three test files while all production files remain donor-equal
    - RED failures are caused only by raw disclosure or the missing RUNNING fence
    - no sleep, malformed fixture, import failure or forbidden-file change explains RED
  </acceptance_criteria>
  <done>The replacement branch has auditable donor lineage and reproducible failing regressions for bounded decode and the late-ToolCall fence.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: bound physical decode and reject late ToolCalls</name>
  <files>src/mini_agent/infrastructure/persistence/postgres.py, tests/integration/test_postgres_record_adapters.py, tests/integration/test_postgres_atomicity.py, tests/integration/test_postgres_recovery.py</files>
  <read_first>Task 1 RED output, canonical codec error translation, historical phantom/reverse-lock tests and exact parent Run contract</read_first>
  <action>
Map strict envelope parsing failure to PAYLOAD_VALIDATION_FAILED and normalized-reference parsing failure to LINK_PROJECTION_MISMATCH without retaining raw ValidationError/value/cause/context. Raise a fresh bounded integrity error outside catch blocks with `from None`.

In insert_tool_call, lock the parent Run, strictly decode its physical projection, require AgentRunRecord with status RUNNING, and only then insert ToolCall/references and touch the recovery anchor. Missing/non-RUNNING Run produces bounded failure and zero write. Make both deterministic concurrency orders GREEN without weakening the existing closure fence. Commit `fix(01-06R): bound persistence decode and reject late tool calls`.
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_record_adapters.py tests/integration/test_postgres_atomicity.py tests/integration/test_postgres_recovery.py -x</automated>
  </verify>
  <acceptance_criteria>
    - owner read/recovery expose no raw secret, Pydantic detail, cause or context
    - recovery-first cannot insert a ToolCall after Run becomes INCOMPLETE
    - insert-first makes recovery conflict/reload and leaves no orphan
    - existing replay/reverse-lock/closure/owner checks remain green
  </acceptance_criteria>
  <done>Physical validation is bounded and ToolCall creation is fenced by the locked current Run state.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: commit the complete terminal turn in one PostgreSQL transaction</name>
  <files>src/mini_agent/infrastructure/persistence/postgres.py, tests/integration/test_postgres_atomicity.py</files>
  <read_first>Task 2 GREEN output, 01-04H FinalizeRunCommand validator/tests, 01-05R Runtime consumer/tests and existing transaction helpers</read_first>
  <action>
RED: Keep the Task 2 production head unchanged. Extend only test_postgres_atomicity.py with with-Task/no-Task/FAILED terminal projection, every Task/RequestUnit/Run/link/Message/Trace child/reference fault, stale/non-APPLIED zero-write and concurrent winner/loser cases. Run that directed file, retain a real incomplete-transaction failure, and commit `test(01-06R): expose terminal atomicity gaps`.

Rewrite finalize_run_if_active to preflight/lock all expected projections in stable order and apply optional Task/RequestUnit transition, terminal Run/link, ASSISTANT Message and exact terminal Trace inside one transaction. terminal_result is validation-only. With Task uses ordered TaskStateChanged/RunStopped; no Task uses RunStopped; FAILED keeps all four optional terminal projections empty.

Any child CAS/fault after mutation begins must escape the transaction via a payload-free internal rollback sentinel; translate it to PROJECTION_CONFLICT only after rollback. Add per-child/reference fault injection and concurrent winner/loser assertions proving complete before-snapshot restoration on every failure. Commit `feat(01-06R): commit terminal turn in one postgres transaction`.
  </action>
  <verify>
    <automated>uv run pytest tests/integration/test_postgres_atomicity.py -x</automated>
  </verify>
  <acceptance_criteria>
    - terminal RED changes only test_postgres_atomicity.py while production remains at the Task 2 GREEN head
    - terminal RED fails for incomplete physical transaction/rollback, not disclosure/fence regression, fixture setup or import failure
    - APPLIED persists the exact complete with/no Task aggregate
    - FAILED persists no result/message/terminal Trace or Task transition
    - every injected child/reference fault rolls back all projections
    - NOT_APPLICABLE, PROJECTION_CONFLICT and stale winner/loser paths commit zero partial writes
    - no physical transaction claim extends to HTTP delivery or cross-service exactly-once
  </acceptance_criteria>
  <done>The frozen Runtime terminal command has an all-or-nothing PostgreSQL implementation with directed rollback evidence.</done>
</task>

</tasks>

<verification>

1. Prove exact base `fb607019130843c94825a47d7822518cbdb2143c`, official planning provenance, branch/worktree and 13 owned-path base state. Read the Plan/Summary from `PLANNING_CONTRACT_SHA`.
2. Prove donor base/head/tree/range and five-commit containment; create one exact replay commit, then retain two real RED commits and their corresponding GREEN commits in order.
3. Start only the Integrator-owned Compose project and disposable test database:

```bash
uv sync --all-groups
docker compose -p mini-agent -f /Users/ming/projects/mini-agent/compose.yaml up --wait -d db
docker compose -p mini-agent -f /Users/ming/projects/mini-agent/compose.yaml --profile test up --wait -d db-test
uv run alembic upgrade head
```

4. Run migration and exact Packet focused gates:

```bash
uv run pytest tests/integration/test_database_migrations.py -x
uv run pytest \
  tests/integration/test_http_session_adapter.py \
  tests/integration/test_postgres_get_order.py \
  tests/integration/test_postgres_record_adapters.py \
  tests/integration/test_postgres_atomicity.py \
  tests/integration/test_postgres_recovery.py -x
```

5. Run `uv run pytest`, `uv run python -m compileall -q src tests` and `git diff --check`. Do not invent repository-wide lint/type/build gates.
6. Prove migration upgrade→downgrade→upgrade in disposable namespaces; record 17-code/five-reference, exact replay/conflict, owner scope, recovery bounds and both concurrency-order matrices.
7. Compute `git diff --name-only fb607019130843c94825a47d7822518cbdb2143c...<feature-head>` and prove exact set/cardinality equality with 13 owned files.
8. Compare final owned blobs to donor: four allowed-delta paths differ and nine fixed blob IDs match exactly. Shared contracts, Runtime, Eval, docs, dependencies and Graphify remain base-identical.
9. Perform read-only cross-file scan. Required forbidden-file correction blocks execution.
10. Create a detached compatibility overlay on latest official integration, apply only the published feature delta, record `OVERLAY_PARENT` / `OVERLAY_HEAD`, prove overlay diff exact 13, rerun focused/full/migration and obtain independent exact-head review.
11. Publish a Draft PR to `integration/e2e01-thin`, verify remote blobs/PR scope equal the reviewed local head, then Integrator serially merges and runs full/migration/Graphify post-merge gates.

</verification>

<nonclaims>

- No Core/Application DTO, Port, enum, codec, Trace or Eval contract changes.
- No Composition Root, global FastAPI startup, Runtime/Infra/Eval wiring or application launch command.
- No Trajectory/E2E Result, Case activation, Requirement/Phase completion or credentialed Qwen baseline.
- No real external order, payment, refund or logistics integration; `create_refund` remains out of scope.
- Component/integration transaction evidence is not HTTP response delivery, cross-service exactly-once or production evidence.
- `terminal_result` is not persisted as an eighteenth record; it only binds existing result/message/Trace projections.
- Historical PR #30 remains review evidence and is not repaired, rebased or merged.

</nonclaims>

<handoff>

After reviewed merge, the Integrator builds a latest-integration overlay for Eval PR #29 head `b8ecbb0a7d69761911213a8433b50c6062116c79`, reruns grader/harness/full/zero-network gates and obtains fresh exact-head review before serial merge.

01-08 alone imports Runtime/Infra/Eval into `bootstrap.py`, seeds the concrete registry/artifact/order/session fixtures, adapts the controlled Eval stale-state seam, proves HTTP→Runtime→PostgreSQL→Provider/Harness ordering and runs real E2E01-01/04 privacy/Trace/Eval gates.

No later consumer may treat this Packet as product completion, production deployment or Case lifecycle evidence.

</handoff>

<success_criteria>

- Controlled donor replay and two directed RED→GREEN cycles are auditable and ordered.
- Feature and latest-integration overlay focused/full/migration gates pass at independently reviewed exact heads.
- Feature/overlay diffs equal exact 13 owned files; four intentional deltas and nine donor-equal blobs satisfy the fixed matrix.
- Physical parsing never leaks raw Pydantic/SQL/secret content.
- Both ToolCall/recovery orderings preserve current-state and no-orphan invariants.
- Every normal terminal APPLIED is a complete one-transaction Task/Run/Message/Trace aggregate; every fault/non-APPLIED path is zero-partial.
- Trusted identity, owner-scoped SQL, foreign/nonexistent equivalence, recovery bounds and existing donor behavior remain green.
- Contract changes and new dependencies remain `NONE`; lifecycle remains `0/8`.

</success_criteria>

<output>
Execution writes no Summary or shared State. It returns a handoff with donor/replay lineage, both real RED commits and both corresponding GREEN commits, exact file/blob matrices, migration/transaction/concurrency/disclosure evidence, focused/full counts, independent feature/overlay review, nonclaims, rollback and Eval/01-08 dependencies. Integrator alone creates later Summary/status and Graphify artifacts after reviewed merge.
</output>
