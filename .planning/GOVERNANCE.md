# Mini Agent｜GSD 派生层治理

> **DERIVED / NON_NORMATIVE**
> 本文件拥有的仅是 GSD 执行层治理，不拥有产品、架构、契约、HTTP、Schema、Fixture、Eval 语义或 Case 生命周期。项目级 canonical 规则仍由 [AGENTS.md](../AGENTS.md) 拥有；发生冲突时本文件必须阻断，不得反向覆盖 active owner。

## 1. Owner Mapping 与冲突优先级

| 语义范围 | Canonical owner | GSD 派生消费者 |
|---|---|---|
| P0 业务范围、两条 E2E、Tool Catalog、Mock 系统 | [business-capabilities.md](../docs/business-capabilities.md) | `PROJECT.md`、`REQUIREMENTS.md`、`ROADMAP.md` |
| P0 架构方向 | [PROJECT_DIRECTION.md](../PROJECT_DIRECTION.md) | Phase / dependency 摘要 |
| Request Understanding / `InputBinding` | [intent-design-reference.md](../docs/architecture/intent-design-reference.md) | Task Packet canonical inputs |
| Tool lifecycle / Gateway / Trace | [tool-calling-design-reference.md](../docs/architecture/tool-calling-design-reference.md) | Task Packet、Review / Security gate |
| Memory / Observation / Evidence / Action Ledger | [memory-design-reference.md](../docs/architecture/memory-design-reference.md) | Task Packet、Review / recovery gate |
| RAG | [rag-design-reference.md](../docs/architecture/rag-design-reference.md) | Phase 3 mapping |
| P0 图形架构基线与图形索引 | [consumer-after-sales-agent-business-application-architecture-v2.drawio](../docs/architecture/consumer-after-sales-agent-business-application-architecture-v2.drawio) 与 [architecture/README.md](../docs/architecture/README.md) | 只作导航；图形不得覆盖语义 owner |
| Eval 方法、Dataset、Grader、Gate | [agent-evaluation-strategy.md](../docs/evaluation/agent-evaluation-strategy.md) | validation / eval review 索引 |
| P0 Case ID、mapping、Critical failure、生命周期 | [p0-eval-coverage-matrix.md](../docs/evaluation/p0-eval-coverage-matrix.md) | `REQUIREMENTS.md`、Roadmap Phase mapping |
| `E2E01-01/04` scoped 实现契约 | [e2e01-thin-slice-implementation-spec.md](../docs/implementation/e2e01-thin-slice-implementation-spec.md) | Phase 1 Plans |
| `E2E01-02/03/05/06` scoped 实现契约 | [e2e01-cycle2-implementation-spec.md](../docs/implementation/e2e01-cycle2-implementation-spec.md) | Phase 2 dependency / ownership / risk map 与后续受控 Plan |
| Wave、ownership、Task Packet、集成顺序 | [e2e01-thin-slice-multi-agent-plan.md](../docs/implementation/e2e01-thin-slice-multi-agent-plan.md) | Phase 1 wave / status |
| Phase 2 Wave、ownership、Task Packet、集成顺序 | [e2e01-cycle2-multi-agent-plan.md](../docs/implementation/e2e01-cycle2-multi-agent-plan.md) | Phase 2 branch / wave / status |

专门 owner **只在自身范围内优先**。不得用文档类别、提交时间、文件新旧或 `.planning/` 生成顺序静默覆盖其他 owner；绝不采用 “newest wins”。

### 冲突处理

1. 标记冲突为 `BLOCK`，记录涉及范围、文件、语义和下游影响。
2. 定位对应 specialized canonical owner；跨 owner 时逐项列出，不使用通用文档优先级代替裁决。
3. 停止受影响 Plan 的 import / execution / merge。
4. 由 owner / Integrator 完成问题说明、影响分析、裁决与 cross-file alignment。
5. 重新运行适用机械检查和独立 exact-head review 后，Integrator 才能同步 `.planning/` 派生视图。

## 2. 写入 Ownership 与外部执行模型

- `.planning/STATE.md`、`.planning/ROADMAP.md`、`.planning/REQUIREMENTS.md`、跨 phase index 和 shared progress 仅由 Integrator 在从 exact integration SHA 预建的 dedicated planning-status Worktree / feature branch 中串行写入，并通过 PR 合并；不得直接写 active integration branch。
- Plan-scoped artifact 只有在 Task Packet 明确分配路径、branch 和 writer 时才可写入；feature Worktree 不得各自推进共享 State，也不得直接修改 active canonical owner。
- `pyproject.toml`、lockfile、migration chain、共享测试 bootstrap、Composition Root 与 active canonical docs 继续服从 [AGENTS.md](../AGENTS.md) 的 single-writer 规则。
- GSD 自动生成内容若超出 Task Packet allowlist，视为 `BLOCK`；立即停止并保留现场，不以事后删改掩盖越界。

Stock GSD 1.38.3 的 Worktree / lifecycle 模型与本项目不兼容，因此实际写入执行固定为：

1. Integrator 在任何 workflow 外，按精确 Task Packet 预建一个 Worktree 和一个 feature branch。
2. Codex Agent 只在该 Worktree 内实现 Task Packet；可以与 ownership 不重叠的其他 Agent 并行。
3. Agent 完成 precheck、实现、postcheck 和 handoff，只向 Task Packet 指定的 remote / head branch push。
4. Feature branch 创建 draft PR 到 Task Packet 指定的 integration branch。
5. Integrator 串行 review、重验与合并；后续分支针对新的 exact integration head 重新验证。

`.planning/config.json` 的 `parallelization=false` 与 `workflow.use_worktrees=false` **只关闭 GSD 自己的并行和 Worktree 管理**。它们不关闭 Codex 多 Agent，也不禁止 Integrator 在 workflow 外预建隔离 Worktree。

## 3. Task Packet 硬门禁

一个 GSD Plan 必须且只能映射到一个精确 Task Packet。Packet 可以包含多个原子 task，但不得跨 repository、branch、Worktree、writer 或 ownership boundary。

每个写入 Task Packet 必须显式包含：

- `repository`、`remote`、`head_branch`、`base_branch`、精确 `base_sha` 和 `worktree_id`；
- `owned_files` 精确 allowlist 与 `forbidden_files`；
- `canonical_inputs`、`dependencies`、`required_checks` 及预期结果；
- `done_when`、`handoff_to` 与 `handoff_format`；
- `contract_changes`、`security_impact`、`eval_impact` 与 `rollback`。
- `review_profile`，至少逐项冻结 `planning_review`、`implementation_review`、
  `targeted_risk_checks`、`focused_tests`、`neighbor_tests`、`full_suite_gate` 与
  `phase_end_deep_audit`；不得用笼统的“按需 review / test”代替。

启动前必须逐字段记录实际值。没有依赖、禁止文件、契约变化或某类影响时也必须显式写 `NONE`；不得留空、继承隐含默认值或由 Agent 猜测。同一 Wave 内一个文件只有一个 writer。

Phase 2 从 W4 起采用风险分级审阅：每个 Packet 仍需 independent exact-head code
review，但默认只审当前 Packet diff、直接 canonical owner、focused / neighbor tests
与 Packet 自己拥有的安全不变量。未修改的 reviewed upstream barrier 作为 imported
evidence；完整 canonical suite、Phase 级 Eval / Security / UAT 与跨 Wave 全量深审只在
对应 `review_profile.full_suite_gate` / `phase_end_deep_audit` 指定的 barrier 运行。
finding remediation 只重跑受影响 focused / neighbor；最终候选稳定后再做 final
exact-head review。任何 contract change、allowlist 扩大、ownership 越界、Wave / Packet
数量变化或无法在原 Packet 内关闭的 BLOCK / HIGH 仍须停止并请求裁决。

所有写入型 specialized workflow 还必须执行 containment check：

- precheck：精确 `base_sha`、当前 head、branch、clean state、allowlist 和禁止文件；
- adapter precheck：所需 GSD agent role 必须在当前 Codex collaboration runtime 中真实可用；SDK 的本地 agent-file 探测不能替代该检查，缺失 role 时为 `BLOCK`；
- postcheck：相对 base 的全部 changed files、全部 commits、当前 head 与预期输出；
- 任一 scope drift、非预期 commit 或禁止文件变化都标记 `BLOCK`，不得 push；
- GSD 永远没有创建、合并、清理或 `--force` 操作项目 Worktree 的授权。

## 4. Severity Mapping 与处置

| GSD / Review 输出 | 项目严重度 | 处置 |
|---|---|---|
| Import `[BLOCKER]` | `BLOCK` | 禁止写 Plan、执行或合并；先完成 owner 裁决 |
| Import `[WARNING]` | `HIGH` 或 `MEDIUM` | 停止 import；Integrator 先分类并记录影响，只有用户显式批准后才能继续，不得自动批准 |
| Code review `CRITICAL` | `BLOCK` | 禁止 merge / release；必须修复并重新 exact-head review |
| GSD `WARNING` | Integrator 显式分类为 `HIGH` 或 `MEDIUM` | 不得静默降级；记录依据、owner 与 resolution |
| `HIGH` | High-risk gate failure | 修复或由 canonical owner 显式裁决；未关闭前不得 release |
| `MEDIUM` | Required resolution | 修复、补测或记录有证据的风险接受；不得遗漏 |
| `INFO` | `LOW / INFO` | 记录为非阻断建议，不得伪装成已修复 |

任何安全不变量、Critical failure、身份 / 资源归属、Evidence、确认、幂等或 `RESULT_UNKNOWN` 违规，无论工具标签为何，均至少按 `BLOCK` 处理。

## 5. GitHub / Worktree Mapping

| GSD 对象 | GitHub / Codex 对象 |
|---|---|
| Phase | 对应 phase-specific integration branch 上的一个可验证阶段 |
| Plan | 一个精确 Task Packet |
| Wave | 一组 ownership 不重叠、由 Integrator 预建的独立 Worktree |
| Executor | 只写 Task Packet feature branch 的 Codex Agent |
| Review / Verification | GitHub exact-head review、机械检查与证据索引 |
| Release | 显式 GitHub feature → integration 与 integration → `main` PR |

Phase-specific branch mapping：

| Phase | Integration branch | 状态与 base chain |
|---|---|---|
| Phase 1 / Cycle 1 | `integration/e2e01-thin` | `HISTORICAL / RELEASED`；保留原 PR、Activation 与 release 证据，不重命名、不复用 |
| Phase 2 / Cycle 2 | `integration/e2e01-cycle2` | `ACTIVE / W4 02-06+13+08+02-09R1+R2 MERGED / 02-09 BLOCKED / W4R 02-09R3 PLAN REVIEW`；真实 current integration / `B_C2_RECOVERY_APP_CONTRACT = 46a0b1f67153846dee6441ce47b7b5d5de4bc4d7` / tree `9c58a0885c93146017d352a5df11b48f5f9240af`；PR #237 已关闭 R2 shared Application recovery contract，当前只从该真实 predecessor重冻结 R3，最终02-09仍不得预测；Case仍为`CONTRACT_DEFINED` |

`.planning/config.json` 的 `git.base_branch=integration/e2e01-cycle2` 只提供 branch
mapping，不授权 GSD 创建、合并、清理 Worktree 或绕过 exact Task Packet。Gate P2-C
已完成且历史证据证明 `B_C2_START` 与 `B_C2_OWNER_ALIGNED` SHA / tree 相同；后续每个
Packet 仍必须从真实 reviewed dependency barrier 冻结 product base，并在 GitHub
远端重新核验当前 integration head 与 branch protection。

执行规则：

1. Feature branch 只 push 到 Task Packet 指定的 repository / head branch。
2. Feature PR 先以 draft PR 指向 Task Packet 指定的 integration branch。
3. Integrator 逐个集成；每次 merge 后，下一个分支针对最新 integration head 重验并取得新的 exact-head review。
4. 完整 phase gate 通过后，使用该 Phase mapping 的显式 integration head 与
   `base=main` 创建 release PR；Phase 1 历史值为
   `head=integration/e2e01-thin`，Phase 2 目标值为
   `head=integration/e2e01-cycle2`。
5. 禁止直接 push `main` 或 active integration branch；GSD `branching_strategy=none` 不提供例外。
6. 不调用 stock `gsd-ship`：它的单一 base 模型不能表达本项目 feature → integration 与 integration → `main` 两级 PR。

## 6. Phase Post-execution Quality Gate

以下是 Phase Plans 全部执行并串行集成后的质量门禁，**不是额外 Plan，也不计入 Plan count**：

```text
exact-integration-SHA code review artifact
→ dedicated fix PR（有 finding 时，修复后重复 review）
→ dedicated validation PR（需要补缺时）
→ Eval / Security audit（满足前置 contract 时）
→ controlled UAT artifact
→ canonical lifecycle owner update
→ Integrator 手工同步 derived Requirements / Roadmap / State
→ 显式 integration → main GitHub PR
```

- `gsd-code-review` 只能在以 exact integration SHA 创建的只读 review-artifact Worktree 中，以 `--files=<normalized absolute exact list>` 运行；相对路径禁止使用，因为当前 macOS 的 `realpath` 不支持 workflow 使用的 GNU `-m` 选项。Preflight 必须确认 requested / accepted 数量完全相等、每个绝对路径均位于 repository 内且是 tracked file；workflow transcript 必须包含同一精确数量的 `File scope: <N> files from --files override`，并且不含 stock 实际输出 `Error: File path outside repository, skipping:` 或 `Warning: File not found, skipping:`。唯一允许写入的是对应 Phase 的 `REVIEW.md`；它不得修改源码、共享状态或其他 artifact。
- `gsd-code-review-fix` 仅在 Integrator 预建的 dedicated fix Worktree / feature branch 中条件使用，并服从第 3 节 precheck / postcheck；发现 scope drift 时 `BLOCK` 且不 push。
- `gsd-validate-phase` 仅在 Integrator 预建的 dedicated validation Worktree / feature branch 中条件使用；测试或验证补缺必须作为独立 Task Packet / PR，不能直接修改 integration。
- `gsd-eval-review` 只有在派生 AI / Eval mapping 明确引用 [canonical Eval owner](../docs/evaluation/agent-evaluation-strategy.md) 后才构成 gate；该 mapping 必须是 `DERIVED / NON_NORMATIVE`，不得创造第二套 Eval 语义。
- `gsd-secure-phase` 必须以完整 `<threat_model>` 映射 [AGENTS.md](../AGENTS.md) 的身份、资源归属、最小披露、Evidence、确认、ActionPolicy、幂等与 `RESULT_UNKNOWN` 等安全不变量。零条 threat 不构成通过。
- Stock `gsd-verify-work` 禁用：GSD 1.38.3 没有 `--no-transition` 模式，Security gate 满足后会自动进入 transition 并调用禁用的 `phase.complete`。会话式验收改由受控 UAT adapter 生成 artifact；adapter 只读取 exact integration evidence、记录用户验收结果，不运行 gap / transition / execute route，也不能替代 canonical 自动化命令、Trajectory / E2E Eval 或 GitHub review。
- 质量门禁完成后，先由 [Coverage Matrix](../docs/evaluation/p0-eval-coverage-matrix.md) canonical owner 根据硬证据更新 Case lifecycle；随后 Integrator 手工同步派生 Requirements / Roadmap / State。
- 禁止 `phase.complete`、`requirements.mark-complete`、`roadmap.update-plan-progress` 及其他自动 lifecycle mutation。
- release 只使用显式 GitHub head / base PR；不调用 `gsd-ship`。

### 6.1 Code Review Scope Adapter

Integrator 先把 Task Packet 的精确文件放入 `review_paths` Bash array；路径不得包含逗号，因为 stock `--files` 以逗号分隔。启动前运行：

```bash
review_repo_root=$(git rev-parse --show-toplevel) || exit 1
review_repo_root=$(realpath "$review_repo_root") || exit 1
review_requested_count=${#review_paths[@]}
review_accepted_count=0
review_absolute_paths=()
review_relative_paths=()

for review_input in "${review_paths[@]}"; do
  review_abs=$(realpath "$review_input") || exit 1
  test -f "$review_abs" || exit 1
  case "$review_abs" in
    *','*|*$'\n'*) exit 1 ;;
  esac
  case "$review_abs" in
    "$review_repo_root"/*) ;;
    *) exit 1 ;;
  esac
  review_rel=${review_abs#"$review_repo_root"/}
  review_tracked_output=$(
    git --literal-pathspecs -C "$review_repo_root" \
      ls-files --error-unmatch -- "$review_rel"
  ) || exit 1
  test "$review_tracked_output" = "$review_rel" || exit 1
  review_absolute_paths+=("$review_abs")
  review_relative_paths+=("$review_rel")
  review_accepted_count=$((review_accepted_count + 1))
done

review_unique_count=$(printf '%s\n' "${review_absolute_paths[@]}" | LC_ALL=C sort -u | wc -l | tr -d ' ')
test "$review_requested_count" -gt 0
test "$review_accepted_count" -eq "$review_requested_count"
test "$review_unique_count" -eq "$review_requested_count"
```

用 canonical accepted list 生成 stock 参数，并以 GSD 1.38.3 相同的 scope 逻辑完成机械 rehearsal：

```bash
review_files_arg=$(IFS=,; printf '%s' "${review_absolute_paths[*]}")
test -n "$review_files_arg"

review_scope_output=$(
  review_stock_files=()
  IFS=',' read -ra review_stock_inputs <<< "$review_files_arg"
  for review_stock_input in "${review_stock_inputs[@]}"; do
    review_stock_abs=$(
      realpath -m "$review_stock_input" 2>/dev/null || echo "$review_stock_input"
    )
    if [[ "$review_stock_abs" != "$review_repo_root"* ]]; then
      echo "Error: File path outside repository, skipping: $review_stock_input"
      continue
    fi
    if [ -f "$review_repo_root/$review_stock_input" ] || [ -f "$review_stock_input" ]; then
      review_stock_files+=("$review_stock_input")
    else
      echo "Warning: File not found, skipping: $review_stock_input"
    fi
  done
  echo "File scope: ${#review_stock_files[@]} files from --files override"
)

review_expected_scope="File scope: $review_requested_count files from --files override"

review_assert_scope() {
  local review_assert_text=$1
  local review_expected_occurrences=$2
  local review_scope_occurrences
  local review_outside_occurrences
  local review_missing_occurrences
  review_scope_occurrences=$(
    printf '%s\n' "$review_assert_text" |
      rg -Fxc "$review_expected_scope" || true
  )
  review_outside_occurrences=$(
    printf '%s\n' "$review_assert_text" |
      rg -Fc 'Error: File path outside repository, skipping:' || true
  )
  review_missing_occurrences=$(
    printf '%s\n' "$review_assert_text" |
      rg -Fc 'Warning: File not found, skipping:' || true
  )
  review_scope_occurrences=${review_scope_occurrences:-0}
  review_outside_occurrences=${review_outside_occurrences:-0}
  review_missing_occurrences=${review_missing_occurrences:-0}
  test "$review_scope_occurrences" -eq "$review_expected_occurrences" || return 1
  test "$review_outside_occurrences" -eq 0 || return 1
  test "$review_missing_occurrences" -eq 0 || return 1
}

review_assert_scope "$review_scope_output" 1
```

随后以 Codex command `$gsd-code-review <phase> --files="<review_files_arg>"` 传入同一字节串。GSD 1.38.3 会在 scope 初始化与 post-processing 各打印一次相同 scope；Integrator 必须把未改写的 workflow transcript 放入 `review_workflow_transcript`，运行 `review_assert_scope "$review_workflow_transcript" 2`，并确认 `REVIEW.md` 的 reviewed-file 清单与 `review_rel` 集合精确相等。

任一计数不一致、literal tracked 输出不等于单个 `review_rel`、任一 skip 前缀出现、transcript 未捕获或最终 review artifact 未覆盖全部 requested files，均为 `BLOCK`。

### 6.2 受控 Planning Adapter

1. Integrator 从 exact integration SHA 预建 dedicated planning-status Worktree / feature branch，并定义只允许一个目标 Plan、对应 Task Packet、必要共享派生索引的精确 allowlist。
2. GSD planner / checker 角色只读 canonical inputs、目标 Roadmap slot 与 Task Packet 模板；只在 handoff 中返回建议，不写文件、不调用 stock `gsd-import` / `gsd-plan-phase`。
3. Integrator 逐项裁决建议，在该 Worktree 中单写最终 Plan / Task Packet；precheck 必须证明目标 slot 唯一且不存在同名 Plan，postcheck 必须证明没有重复 slot、无 scope drift、无未授权 lifecycle mutation。
4. Planning artifact 经独立 exact-head review 和 PR 合并后才可作为下游执行输入；Plan 本身仍不证明实现完成。

### 6.3 受控 UAT Adapter

1. Integrator 从 exact integration SHA 预建 UAT-artifact Worktree / feature branch，allowlist 只含对应 Phase 的 UAT artifact。
2. Adapter 复用 `gsd-verify-work` 的用户可观察验收点选择与逐项记录方法，但不调用 stock workflow entrypoint 或任何 GSD state mutation。
3. 每个验收项只记录 `PASS`、`ISSUE` 或 `SKIPPED`、用户输入、可复现证据引用与未决风险；不得由模型根据自动化测试替用户宣告通过。
4. 结束时只生成 / 更新 UAT artifact 并执行 changed-file containment check；不创建 gap plan、不调用 transition / execute route、不更新 Roadmap / Requirements / State。
5. UAT artifact 通过独立 PR 交由用户 / Integrator 裁决；发现 issue 时另建精确 Task Packet，不在 UAT branch 直接修源码。

## 7. Evidence 与工具健康纪律

以下才是完成结论的硬证据：

- 当前源码与精确 commit / tree；
- canonical 命令、focused tests、migration、Trajectory / E2E Eval 的实际输出；
- 文件 allowlist 与 `git diff --check`；
- 独立 Reviewer 对精确 head SHA 的结果和已解决 findings；
- GitHub PR、conversation resolution 与 merge commit。

GSD Roadmap、State、Plan、Summary、Review、UAT 或 Verification 文档只索引证据，不能自我证明“已实现 / 已验证 / 可运行”。

GSD 健康必须同时读取两个表面，并保留原始分类：

- CJS `validate health --raw`；
- SDK `query validate.health`。

两者 warning code 或对象模型不一致时标为 `OPEN / TOOL_SURFACE_DRIFT`，不得把其中一个结果改写成整体 healthy。`--repair`、`--force` 或 Worktree 删除必须有独立显式授权；本 activation 没有该授权。

`gsd-sdk query init.phase-op` 的本地 agent-file 探测与 Codex collaboration role registry 是两个不同表面。每次 conditional workflow 启动前都必须同时确认 `phase_found`、phase path / artifact prerequisites 和所需 Codex role；不得因 SDK 返回 phase metadata 就推断执行 Agent 已可用。

## 8. Workflow Matrix

| 分类 | Workflow / API | 当前策略 |
|---|---|---|
| Safe read-only | `gsd-progress` | 只读查看；关闭 / 拒绝任何自动 next-route |
| Safe read-only | `gsd-health` | 同时读取 CJS 与 SDK surface；不运行 `--repair` / `--force` |
| Safe planning advisory | GSD planner / checker roles | 只读 canonical inputs 与目标 slot；输出建议，不写共享 State。Integrator 在 dedicated planning-status Worktree 中创建一对一 Plan / Task Packet 并通过 PR 合并 |
| Conditional review artifact | `gsd-code-review` | exact-integration-SHA review-artifact Worktree + normalized absolute exact `--files`；literal tracked exact-match，requested=accepted=unique=transcript scope，且 stock 两种真实 skip 输出均为零；只写 Phase `REVIEW.md` |
| Conditional fix | `gsd-code-review-fix` | 预建 dedicated fix Worktree / branch；精确 Task Packet 与 containment check |
| Conditional validation | `gsd-validate-phase` | 预建 dedicated validation Worktree / branch；补缺走独立 PR |
| Conditional Eval audit | `gsd-eval-review` | 先有引用 canonical Eval owner 的派生 mapping；否则不构成 gate |
| Conditional security audit | `gsd-secure-phase` | 完整 `<threat_model>` 映射安全不变量；zero-threat 不通过 |
| Conditional UAT | controlled UAT adapter | 只产 UAT artifact；不调用 stock `gsd-verify-work`，不进入 gap / transition / execute route |
| Disabled | `gsd-import`, `gsd-plan-phase` | 不运行 stock entrypoint；两者会写共享 State，import 对既有 Roadmap slot 的 replacement 也没有可机械保证的 pre-write contract |
| Disabled | `gsd-verify-work` | 不运行；当前版本没有 `--no-transition`，可达路径会调用 `phase.complete` |
| Disabled | `gsd-execute-phase` | 不运行；stock workflow 会枚举、合并并可能以 `--force` 清理所有非当前 Worktree，还会提前推进 phase lifecycle |
| Disabled | `phase.complete` | 不运行；Phase 完成必须等待 post-execution quality gate 与 canonical lifecycle owner |
| Disabled | `requirements.mark-complete` | 不运行；canonical Case lifecycle 不能由派生 checkbox 改写 |
| Disabled | `roadmap.update-plan-progress` | 不运行；Integrator 基于 Summary、PR 与硬证据手工同步 |
| Disabled | `gsd-ship` | 不运行；不能表达两级 PR 模型 |
| Disabled | `gsd-autonomous`, `gsd-phase-autopilot` | 不运行；会绕过 owner、Task Packet、PR 或交互 gate |
| Disabled | `gsd-new-project`, `gsd-new-milestone` | 当前 P0 不运行；仓库已有 canonical 项目与 milestone 定义 |
| Disabled | 自动 lifecycle mutations | 不运行任何自动 phase / requirement / roadmap transition |

通用 `gsd-ingest-docs` 也保持禁用，除非另有显式 owner manifest、blocker conflict review 与独立批准；不得用通用文档优先级覆盖 specialized owner。

## 9. 为什么部分 stock lifecycle workflow 被禁用

GSD 1.38.3 的 stock `gsd-execute-phase` 会管理其视野内的非当前 Worktree，包括枚举、合并、清理以及在路径上使用 `--force`；同时会调用 `roadmap.update-plan-progress` 和 `phase.complete`。这与本项目“每个 Task Packet 一个预建 Worktree、Integrator 串行合并、质量 gate 后才更新 lifecycle”的规则冲突。

因此 `parallelization=false` 与 `workflow.use_worktrees=false` 是防误触控制，而不是执行授权。实际写入由 Codex Agent 在 Integrator 预建 Worktree 中完成；GSD 只提供受控 planning / review / validation artifact。

Stock `gsd-ship` 只有单一 base 概念，不能同时表达 feature → integration 和 integration → `main`。所有 feature / release PR 必须显式给出 GitHub repository、head 与 base。

Stock `gsd-plan-phase` 会在 artifact 生成路径中执行 `state.planned-phase`，stock `gsd-import` finalizer 会更新 Plans / State，且不能在写入前机械保证“替换一个既有 slot、绝不重复”。因此两者不作为本项目写入入口；GSD planner / checker 角色只提供只读建议，最终 Plan 由 Integrator 在 dedicated planning-status Worktree 中单写并通过 PR 合并。

Stock `gsd-verify-work` 在验收通过路径上会自动进入 transition，而 transition 会调用本项目禁用的 `phase.complete`。当前版本没有 `--no-transition`，因此改用不包含 lifecycle route 的受控 UAT adapter。

## 10. Rollback

- Activation merge 前：关闭 PR，并按用户 / Integrator 的显式决定回收该 feature branch / Worktree；integration 无变化。
- Activation merge 后：使用普通 revert PR 撤销 activation commit；不得 destructive reset、`--force` cleanup 或直接删除 canonical 文件。
- 发生 owner 冲突、状态损坏、scope drift 或越界写入时：暂停 GSD 写入、保留 diff / log / commit 证据、禁止 push，由 Integrator 完成 impact scan。
- 修复期间继续使用既有 Task Packet + Integrator 预建 Worktree + Codex Agent + GitHub PR 流程；不授权 GSD 创建、合并或清理 Worktree。
