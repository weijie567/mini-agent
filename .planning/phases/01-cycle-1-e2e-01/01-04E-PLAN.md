---
phase: 01-cycle-1-e2e-01
plan: 04E
type: tdd
wave: 6
depends_on:
  - 01-04D
files_modified:
  - docs/architecture/memory-design-reference.md
  - src/mini_agent/core/memory.py
  - tests/component/core/test_memory_trace_presentation_contract.py
autonomous: true
requirements:
  - E2E01-01
  - E2E01-04
user_setup: []
must_haves:
  truths:
    - "ContextManifest keeps one required TokenCounts object, but each direction is nullable when it was not exactly measured."
    - "None means unknown or not exactly measured; integer 0 means an observed exact zero and can never stand for unknown."
    - "Token counts are strict non-negative integers: float, string and bool inputs are rejected instead of coerced."
    - "The first thin slice does not invent a tokenizer, estimate tokens from characters or JSON length, or fill zero because ModelProvider exposes no exact usage."
    - "Changing token-count availability does not change the references that prove what model-visible records were selected."
    - "This pre-executable owner correction does not claim that Provider usage, cost accounting, Runtime, Eval or persistence Adapter behavior is implemented."
  artifacts:
    - "docs/architecture/memory-design-reference.md owns exact nullable token-count semantics."
    - "src/mini_agent/core/memory.py encodes nullable input_tokens and output_tokens while retaining a required TokenCounts object."
    - "tests/component/core/test_memory_trace_presentation_contract.py proves unknown, exact zero and positive count are distinct."
  key_links:
    - "Memory owner semantics map directly to the Core ContextManifest DTO."
    - "The Core contract can represent ContextManifest with TokenCounts(input_tokens=None, output_tokens=None) without fabricating evidence; Runtime construction and persistence remain unimplemented."
    - "Later exact provider usage may populate only values actually measured by an owner-approved source; absence remains None."
---

<objective>
关闭 `ContextManifest.token_counts` 必填但 frozen `ModelProvider` 没有 exact tokenizer / usage 来源的证据伪造风险。

Purpose: 让首切片可以诚实记录“未精确测量”，并保持 `0` 只表示真实的 exact zero。

Output: 一个 Memory semantic-owner 文档、一个 Core DTO 和一个 Core Component test 文件；不修改 Provider Port、Runtime、Eval artifact、Persistence codec 或 Infra。
</objective>

<execution_context>
@AGENTS.md
@.planning/GOVERNANCE.md
@.planning/phases/01-cycle-1-e2e-01/01-04D-SUMMARY.md
@docs/architecture/memory-design-reference.md
@src/mini_agent/core/memory.py
@src/mini_agent/application/ports.py
@tests/component/core/test_memory_trace_presentation_contract.py

本 Plan 使用受控 GSD planner / checker adapter，不调用 stock import、execute、verify、lifecycle mutation 或 ship。Integrator 已从 exact base 预建 execution Worktree；executor 只写本 Packet 三个 owned files。
</execution_context>

<task_packet>
repository: `https://github.com/weijie567/mini-agent`
remote: `origin`
head_branch: `codex/e2e01-01-context-manifest-usage`
base_branch: `integration/e2e01-thin`
base_sha: `a84d30188eaec75e45619e9939180ba78efa3b80`
worktree_id: `e2e01-01-context-manifest-usage`
worktree_path: `/Users/ming/projects/mini-agent-worktrees/e2e01-01-context-manifest-usage`
writer: `Memory semantic-owner sole writer, supervised by /root Integrator`
agent_role: `runtime-engineer`

owned_files:

- `docs/architecture/memory-design-reference.md`
- `src/mini_agent/core/memory.py`
- `tests/component/core/test_memory_trace_presentation_contract.py`

forbidden_files:

- every repository path not listed in `owned_files`
- `AGENTS.md`
- `PROJECT_DIRECTION.md`
- `README.md`
- `.planning/**`
- every other `docs/**` file
- `src/mini_agent/application/**`
- `src/mini_agent/infrastructure/**`
- `src/mini_agent/evaluation/**`
- every other `src/mini_agent/core/**` file
- every other test file
- `evals/**`
- `alembic/**`
- `pyproject.toml`
- `uv.lock`
- `compose.yaml`
- `graphify-out/**`

canonical_inputs:

- `AGENTS.md` sections 1, 3–8 and graphify
- `.planning/GOVERNANCE.md` Task Packet, lifecycle and post-merge Graphify gates
- `docs/architecture/memory-design-reference.md` Context Manifest / token-count semantics at exact `base_sha`
- `src/mini_agent/core/common.py` strictness boundary at exact `base_sha`
- `src/mini_agent/core/memory.py` `TokenCounts` / `ContextManifest` contract at exact `base_sha`
- `src/mini_agent/core/trace.py` nullable `TimingAndUsageSummary` comparison at exact `base_sha`
- `src/mini_agent/application/ports.py` frozen `ModelProvider` boundary at exact `base_sha`

dependencies:

- 01-04D PR #21 merge / exact execution base `a84d30188eaec75e45619e9939180ba78efa3b80`
- post-merge regression `344 passed`
- Graphify gate at the same SHA: 3253 nodes / 5814 edges, zero structural errors, no stale marker
- the planning-status PR containing this Plan must merge before implementation writing starts
- execution must capture the planning merge SHA and this Plan blob from the official integration ref while proving all three owned files remain byte-identical to `base_sha`

required_checks:

- exact branch, base, merge-base and clean-worktree preflight
- RED proves the current DTO cannot represent unknown counts without a fabricated integer
- GREEN makes `TokenCounts.input_tokens` and `output_tokens` nullable with default `None`; `ContextManifest.token_counts` itself remains required
- strict Pydantic extra/type/negative-value checks remain intact
- docs explicitly distinguish `None`, exact `0`, positive exact counts and forbidden estimates
- focused Core tests, complete `uv run pytest`, ruff for the exact Python files, compileall and `git diff --check`
- exact three-file containment and repository cross-file impact scan
- independent exact-head review before PR readiness and merge
- after merge, Integrator-only Graphify AST plus controlled semantic refresh and freshness/health check before 01-04F

done_when:

- exact three-file Packet has one reviewed feature commit
- focused and full regressions pass
- no unresolved `CRITICAL / HIGH / MEDIUM` review finding
- draft PR targets `integration/e2e01-thin`
- merge does not advance Case, Requirement or numbered Phase lifecycle

contract_changes: `YES / MEMORY TOKEN AVAILABILITY SEMANTICS`
security_impact: `YES` — prevents fabricated audit and cost evidence.
eval_impact: `YES / CONTRACT ONLY` — Eval may observe unknown usage as null; no Result or lifecycle evidence is created.
graphify_disposition: `INTEGRATOR POST-MERGE GATE` — writer does not modify `graphify-out/**`; after merge the Integrator runs `graphify update .`, performs the established controlled semantic re-extraction for the changed Memory owner, verifies graph structure/freshness and a clean tracked tree, and blocks 01-04F on failure.
rollback: Close the PR before merge. After merge use a normal revert PR and re-block downstream W2; never reset, force-push or delete shared Worktrees.

handoff_to: `/root Integrator`

handoff_format:

- branch, exact base/planning/head/commit/tree and Plan blob
- actual changed files and exact three-file containment
- RED/GREEN commands, focused/full results and strict coercion matrix
- canonical contract change, security/Eval impact and cross-file scan
- independent exact-head review result
- post-merge Graphify disposition, unresolved risks and rollback
</task_packet>

<threat_model>

| threat_id | category | boundary | disposition | mitigation |
|---|---|---|---|---|
| `CTX-T01` | Tampering | Runtime → ContextManifest | `MITIGATE / BLOCK` | unknown counts remain `None`; zero cannot encode missing evidence |
| `CTX-R01` | Repudiation | ContextManifest → Trace / Eval | `MITIGATE / BLOCK` | docs and tests require exact-measurement semantics and forbid estimates |
| `CTX-I01` | Information Disclosure | Provider diagnostics → audit record | `MITIGATE` | no prompt, raw response, token text, credential or PII is added |
| `CTX-D01` | Denial of Service | token measurement | `AVOID` | no new tokenizer, network call or unbounded input scan is introduced |

</threat_model>

<feature>
  <name>ContextManifest exact-or-unknown token counts</name>
  <files>docs/architecture/memory-design-reference.md, src/mini_agent/core/memory.py, tests/component/core/test_memory_trace_presentation_contract.py</files>
  <behavior>
    - `TokenCounts()` produces `input_tokens=None` and `output_tokens=None`
    - `TokenCounts(input_tokens=0, output_tokens=0)` preserves two observed exact zeros
    - positive exact integer counts remain valid
    - negative integers, floats, strings, booleans and extra fields are rejected under strict Pydantic validation for both directions
    - `ContextManifest` still requires a `token_counts` object; omitting the whole object remains a validation error
  </behavior>
  <implementation>
    Define both fields as `Annotated[int, Field(ge=0, strict=True)] | None = None` (or an exactly equivalent strict-integer annotation). Update Memory section 13.3 to state that each value is present only when exactly measured for that direction; `None` is unknown/not measured, `0` is exact zero, character/byte/JSON-length estimates and caller-filled placeholders are forbidden. State that the current thin-slice ModelProvider exposes no exact usage source, so the Core contract represents unknown usage with a required TokenCounts object whose values are null; later Runtime/Adapter work must not invent evidence.
  </implementation>
</feature>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — freeze exact-or-unknown semantics</name>
  <files>tests/component/core/test_memory_trace_presentation_contract.py</files>
  <read_first>AGENTS.md, docs/architecture/memory-design-reference.md, src/mini_agent/core/memory.py, src/mini_agent/application/ports.py, tests/component/core/test_memory_trace_presentation_contract.py</read_first>
  <action>Add tests for required TokenCounts object, both-null unknown values, exact zero, positive integer values, and strict rejection in each direction of negative integers plus coercible `1.0`, `"1"` and `True`, as well as extra fields. Run only this test file before implementation and record the expected failures caused by mandatory fields and coercive integer parsing.</action>
  <verify>`uv run pytest tests/component/core/test_memory_trace_presentation_contract.py -x` must fail for the new unknown-count assertion before source changes.</verify>
  <acceptance_criteria>
    - the RED test fails because null or default counts are not accepted, not because of syntax/import errors
    - tests explicitly distinguish omitted `token_counts` object from nullable fields inside it
    - tests prove `1.0`, `"1"` and `True` are rejected for both input_tokens and output_tokens
    - tests contain no approximate token-count algorithm
  </acceptance_criteria>
  <done>Current contract's inability to represent unknown exact usage is mechanically reproduced.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN / REFACTOR — implement and document nullable-per-direction counts</name>
  <files>docs/architecture/memory-design-reference.md, src/mini_agent/core/memory.py, tests/component/core/test_memory_trace_presentation_contract.py</files>
  <read_first>AGENTS.md, PROJECT_DIRECTION.md, docs/architecture/memory-design-reference.md, src/mini_agent/core/memory.py, src/mini_agent/core/trace.py, src/mini_agent/application/ports.py, tests/component/core/test_memory_trace_presentation_contract.py</read_first>
  <action>Change only `TokenCounts.input_tokens` and `TokenCounts.output_tokens` to nullable, strict, non-negative integers defaulting to `None`; keep `ContextManifest.token_counts` required. Use `Field(ge=0, strict=True)` or a mechanically equivalent strict integer type. Add the exact owner wording specified in the feature block. Do not add a counter Port, tokenizer, estimate, Provider field, usage mutation or schema fallback. Refactor only within the three-file allowlist.</action>
  <verify>`uv run pytest tests/component/core/test_memory_trace_presentation_contract.py -x` exits 0; then `uv run pytest`, `uv run ruff check src/mini_agent/core/memory.py tests/component/core/test_memory_trace_presentation_contract.py`, `uv run ruff format --check src/mini_agent/core/memory.py tests/component/core/test_memory_trace_presentation_contract.py`, `uv run python -m compileall -q src tests`, and `git diff --check` all exit 0.</verify>
  <acceptance_criteria>
    - both nullable fields default to `None`
    - exact zero round-trips as integer zero
    - the whole `token_counts` object remains mandatory on ContextManifest
    - owner text forbids estimates and placeholder zero
    - full regression passes and changed files are exactly the owned-file subset
  </acceptance_criteria>
  <done>The Core contract can represent an honest required usage snapshot; Runtime construction and persistence remain deferred.</done>
</task>

</tasks>

<verification>

1. Prove exact base, Plan provenance and three-file containment.
2. Run focused RED/GREEN evidence and all canonical offline tests.
3. Run `rg -n "token_counts|input_tokens|output_tokens|None|exact|0|estimate" docs/architecture/memory-design-reference.md src/mini_agent/core/memory.py tests/component/core/test_memory_trace_presentation_contract.py`.
4. Scan active Thin Slice, Eval owner, Application ports/records and Runtime plan consumers; report impacts without modifying forbidden files.
5. Obtain an independent exact-head review and only then mark the draft PR ready.
6. After merge, Integrator runs the declared Graphify AST + semantic freshness gate before 01-04F starts.

</verification>

<success_criteria>

- The Core contract represents unknown exact counts without a fake integer.
- Zero remains evidence of exact zero.
- Coercible float/string/bool values cannot become audit counts.
- No tokenizer or usage Port is invented.
- ContextManifest reference/provenance semantics remain unchanged.
- Full regression and independent review pass at the exact feature head; Runtime/Adapter behavior remains `NOT_IMPLEMENTED`.

</success_criteria>

<output>
After implementation, create the execution handoff outside the feature allowlist with branch/commit/tree, exact changed files, RED/GREEN commands, full regression count, review result, contract/security/Eval impact, cross-file scan and rollback. Integrator alone writes the later Summary/status PR.
</output>
