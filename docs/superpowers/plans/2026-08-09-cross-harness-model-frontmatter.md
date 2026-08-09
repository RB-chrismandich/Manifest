# Cross-Harness Model Frontmatter and Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Let skills declare ordered per-harness model tiers and choose automatic or confirmed fallback across Codex,
Gemini, Antigravity, and Cursor.

**Architecture:** Introduce one shared manifest_model_policy package consumed by frontmatter validation, generated
plugin views, parallel-agent, and manifest-delegate. Keep concrete model IDs in parallel_agent.yml, parse optional
skill-local tier chains, classify only approved provider failures as fallback-eligible, and centralize
confirmation/non-interactive decisions in a reusable controller.

**Tech Stack:** Python 3.11, YAML, dataclasses and enums, existing agents runners, manifest-delegate, Click/argparse
CLIs, pytest, Bats.

## Global Constraints

- Canonical frontmatter keys are models and model_fallback.
- Canonical harness names are claude, codex, gemini, cursor, antigravity, and devin; agy normalizes to antigravity.
- Skill files contain portable tiers, never concrete provider model IDs.
- Concrete model IDs and default chains remain centralized in configs/claude/config/parallel_agent.yml.
- CLI/session override wins over skill frontmatter, which wins over global configuration.
- Global fallback mode defaults to confirm.
- auto is the final tier only for harnesses whose native invocation supports omitted model selection.
- Fallback-eligible failures: unsupported/unavailable model, rate limit, transient provider error, capacity exhaustion,
  quota rejection, and billing rejection.
- Blocking failures: authentication, invalid configuration, unsafe request, malformed output, and task/application
  error.
- Non-interactive execution never prompts and switches only when auto is explicitly authorized.
- Skills without model metadata preserve current behavior.
- Frontmatter growth must remain within the repository context-budget gates.

---

## File Structure

- Create `configs/claude/scripts/manifest_model_policy/`: single shared parser, resolver, classifier, and fallback
  controller.
- Modify root pyproject.toml and configs/claude/pyproject.toml: package the shared module in both runtimes.
- Modify configs/claude/config/parallel_agent.yml and command_config.yml: defaults and documented routing.
- Modify configs/claude/scripts/agents/runners.py: ordered chain execution and confirmation.
- Modify plugins/manifest-delegate/manifest_delegate/: skill-policy input, classified fallback, and structured recovery.
- Modify tools/generate_plugin_views.py and Cursor generators: validate and translate model metadata.
- Modify tests/bats/context_budget.bats and add focused Python tests.

### Task 1: Create the Shared Frontmatter Model

**Files:**

- Create: `configs/claude/scripts/manifest_model_policy/__init__.py`
- Create: configs/claude/scripts/manifest_model_policy/frontmatter.py
- Modify: pyproject.toml
- Modify: configs/claude/pyproject.toml
- Test: tests/python/model_policy/test_frontmatter.py

**Interfaces:**

- Produces ModelFallbackMode(StrEnum): AUTO and CONFIRM.
- Produces SkillModelPolicy(chains: Mapping[str, tuple[str, ...]], fallback_mode: ModelFallbackMode | None).
- Produces parse_skill_model_policy(path: Path) -> SkillModelPolicy.
- Produces normalize_harness(name: str) -> str.

- [ ] **Step 1: Write failing parser tests**

```python
def test_parses_ordered_harness_chains(tmp_path):
    skill = write_skill(
        tmp_path,
        {
            "models": {
                "codex": ["advanced", "flash", "auto"],
                "agy": ["advanced", "flash", "auto"],
            },
            "model_fallback": {"mode": "confirm"},
        },
    )
    policy = parse_skill_model_policy(skill)
    assert policy.chains["codex"] == ("advanced", "flash", "auto")
    assert policy.chains["antigravity"] == ("advanced", "flash", "auto")
    assert policy.fallback_mode is ModelFallbackMode.CONFIRM
```

Also test unknown harnesses, duplicate agy/antigravity definitions, empty chains, duplicate tiers, non-final auto,
unknown modes, malformed YAML, and absent metadata.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/model_policy/test_frontmatter.py -q

Expected: FAIL because manifest_model_policy does not exist.

- [ ] **Step 3: Implement strict parsing**

```python
@dataclass(frozen=True)
class SkillModelPolicy:
    chains: Mapping[str, tuple[str, ...]]
    fallback_mode: ModelFallbackMode | None = None


def normalize_harness(name: str) -> str:
    normalized = "antigravity" if name == "agy" else name
    if normalized not in SUPPORTED_HARNESSES:
        raise ModelPolicyError(f"unknown harness {name!r}")
    return normalized
```

Parse only the first YAML frontmatter block. Do not silently drop invalid keys or values.

- [ ] **Step 4: Package the shared module once**

Configure both wheels to include configs/claude/scripts/manifest_model_policy as import package manifest_model_policy.
Do not copy the module into src/manifest_agent or manifest-delegate.

- [ ] **Step 5: Run parser and packaging tests**

Run: uv run pytest tests/python/model_policy/test_frontmatter.py
tests/python/manifest_agent/test_offline_installation.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/manifest_model_policy pyproject.toml \
  configs/claude/pyproject.toml tests/python/model_policy/test_frontmatter.py
git commit -m "feat(models): parse cross-harness skill policy"
```

### Task 2: Add Tier Resolution and Global Policy

**Files:**

- Create: configs/claude/scripts/manifest_model_policy/resolver.py
- Modify: configs/claude/config/parallel_agent.yml
- Modify: configs/claude/config/command_config.yml
- Modify: configs/claude/scripts/agents/config.py
- Test: tests/python/model_policy/test_resolver.py
- Test: tests/python/agents/test_config.py

**Interfaces:**

- Produces ResolvedModel(tier: str, model_id: str | None).
- Produces resolve_chain(config: Mapping, harness: str, tiers: Sequence[str]) -> tuple[ResolvedModel, ...].
- Produces effective_fallback_mode(cli_mode, skill_mode, global_mode) -> ModelFallbackMode.

- [ ] **Step 1: Write failing resolution tests**

Test Codex GPT tier resolution, Gemini, Antigravity/agy, Cursor, native auto, missing tiers, absent skill policy, and
precedence:

```python
assert effective_fallback_mode(
    cli_mode=None,
    skill_mode=ModelFallbackMode.AUTO,
    global_mode=ModelFallbackMode.CONFIRM,
) is ModelFallbackMode.AUTO
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/model_policy/test_resolver.py tests/python/agents/test_config.py -q

Expected: FAIL because the resolver and global mode do not exist.

- [ ] **Step 3: Add global defaults**

In parallel_agent.yml add:

```yaml
model_fallback:
  mode: confirm
  chains:
    codex: [advanced, flash, mini, auto]
    gemini: [pro, flash, auto]
    antigravity: [advanced, flash, mini, auto]
    cursor: [advanced, flash, mini, auto]
```

Keep model_tiers as the only concrete-ID mapping. command_config.yml references this canonical source and contains no
duplicate IDs.

- [ ] **Step 4: Implement ordered resolution**

Resolve portable tiers through model_tiers.<harness>.<tier>. Represent auto as model_id=None. Reject auto for a harness
whose registry model arguments cannot be omitted.

- [ ] **Step 5: Keep config fallback literals in sync**

Update agents.config._default_config() and its drift tests so no-file behavior exactly matches parallel_agent.yml.

- [ ] **Step 6: Run resolver tests**

Run: uv run pytest tests/python/model_policy/test_resolver.py tests/python/agents/test_config.py -q

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add configs/claude/scripts/manifest_model_policy/resolver.py \
  configs/claude/config/parallel_agent.yml \
  configs/claude/config/command_config.yml \
  configs/claude/scripts/agents/config.py \
  tests/python/model_policy/test_resolver.py tests/python/agents/test_config.py
git commit -m "feat(models): resolve portable fallback chains"
```

### Task 3: Classify Failures and Decide Fallback

**Files:**

- Create: configs/claude/scripts/manifest_model_policy/failures.py
- Create: configs/claude/scripts/manifest_model_policy/controller.py
- Test: tests/python/model_policy/test_failures.py
- Test: tests/python/model_policy/test_controller.py

**Interfaces:**

- Produces FailureClass enum with MODEL_UNAVAILABLE, RATE_LIMIT, TRANSIENT, CAPACITY, QUOTA, BILLING, AUTH, CONFIG,
  SAFETY, MALFORMED_OUTPUT, TASK_ERROR, UNKNOWN.
- Produces FallbackAction enum with RETRY, STOP, and NEEDS_CONFIRMATION.
- Produces classify_failure(returncode: int | None, stderr: str, error: Exception | None) -> FailureClass.
- Produces FallbackDecision(action, current, proposed, failure, message).
- Produces FallbackController.decide(index: int, failure: FailureClass) -> FallbackDecision.

- [ ] **Step 1: Write table-driven classifier tests**

Include real-shaped messages for HTTP 429, RESOURCE_EXHAUSTED, overloaded/capacity, payment required, insufficient
quota, authentication, invalid model config, safety refusal, malformed result envelope, and a failing user test command.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/model_policy/test_failures.py tests/python/model_policy/test_controller.py -q

Expected: FAIL because classifier/controller modules do not exist.

- [ ] **Step 3: Implement ordered, anchored classification**

Prefer structured exception/status fields when available. Text patterns must be provider-scoped and boundary-aware;
never classify stdout answer text. Unknown errors block.

```python
FALLBACK_ELIGIBLE = {
    FailureClass.MODEL_UNAVAILABLE,
    FailureClass.RATE_LIMIT,
    FailureClass.TRANSIENT,
    FailureClass.CAPACITY,
    FailureClass.QUOTA,
    FailureClass.BILLING,
}
```

- [ ] **Step 4: Implement confirmation decisions**

confirm returns a proposal containing current model, proposed model, classified reason, and whether auto changes
billing/capability. A declined confirmation returns STOP. Non-interactive plus confirm mode returns NEEDS_CONFIRMATION
without calling the prompt callback.

- [ ] **Step 5: Run classifier/controller tests**

Run: uv run pytest tests/python/model_policy/test_failures.py tests/python/model_policy/test_controller.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/manifest_model_policy/failures.py \
  configs/claude/scripts/manifest_model_policy/controller.py \
  tests/python/model_policy/test_failures.py \
  tests/python/model_policy/test_controller.py
git commit -m "feat(models): classify and authorize fallback"
```

### Task 4: Wire Policy into Parallel-Agent Runners

**Files:**

- Modify: configs/claude/scripts/agents/runners.py
- Modify: configs/claude/scripts/agents/cli.py
- Modify: configs/claude/scripts/agents/orchestrator.py
- Test: tests/python/agents/test_runners.py
- Test: tests/python/agents/test_cli.py

**Interfaces:**

- Adds BaseAgent(model_chain, fallback_mode, interactive, confirm_callback).
- Adds CLI options --skill-path PATH and --model-fallback auto|confirm.
- Result fields: model_attempts, fallback_reason, fallback_confirmed.

- [ ] **Step 1: Replace one-shot credit tests with chain tests**

Add tests for advanced -> flash -> auto, rate limit, transient provider error, billing rejection, confirmation
accepted/declined, non-interactive stop, and auth/config/task errors that never switch.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/agents/test_runners.py tests/python/agents/test_cli.py -q

Expected: FAIL because BaseAgent supports only one automatic credit fallback.

- [ ] **Step 3: Refactor BaseAgent around the shared controller**

Replace credit_fallback_used with ordered attempt records:

```python
for index, resolved in enumerate(self.model_chain):
    self.model = resolved.tier
    self.model_name = resolved.model_id
    try:
        return await self._execute_current(prompt, mode)
    except Exception as error:
        failure = classify_failure(None, _stderr(error), error)
        decision = self.fallback_controller.decide(index, failure)
        if decision.action is not FallbackAction.RETRY:
            return self._failed_result(error, decision)
```

Remove the fixed three-attempt limit; the validated chain length is the limit. Extract `_execute_current(prompt, mode)`
for one model attempt and `_failed_result(error, decision)` for the terminal structured result before using them in the
loop.

- [ ] **Step 4: Parse skill policy at the CLI boundary**

When --skill-path is present, parse its frontmatter and select the active harness chain. Apply explicit --model and
--model-fallback overrides before constructing agents.

- [ ] **Step 5: Add interactive confirmation**

Use one injected callback so tests do not patch input. CLI confirmation names both model tiers/IDs and the classified
failure. JSON mode and non-interactive mode never prompt.

- [ ] **Step 6: Run runner tests**

Run: uv run pytest tests/python/agents/test_runners.py tests/python/agents/test_cli.py
tests/python/agents/test_config.py -q

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add configs/claude/scripts/agents/runners.py \
  configs/claude/scripts/agents/cli.py \
  configs/claude/scripts/agents/orchestrator.py \
  tests/python/agents/test_runners.py tests/python/agents/test_cli.py
git commit -m "feat(parallel-agent): honor skill model fallback policy"
```

### Task 5: Wire Policy into manifest-delegate

**Files:**

- Modify: plugins/manifest-delegate/manifest_delegate/cli.py
- Modify: plugins/manifest-delegate/manifest_delegate/backend.py
- Modify: plugins/manifest-delegate/manifest_delegate/task.py
- Modify: plugins/manifest-delegate/manifest_delegate/worker.py
- Modify: plugins/manifest-delegate/manifest_delegate/jobstore.py
- Test: tests/python/test_delegate_config.py
- Test: tests/python/test_delegate_jobs.py
- Test: tests/python/test_delegate_faults.py

**Interfaces:**

- Adds delegate options --skill-path and --model-fallback.
- Job record fields: model_chain, model_attempts, fallback_mode, fallback_pending.
- Background/non-interactive confirmation returns structured recovery instead of prompting.

- [ ] **Step 1: Add failing foreground and background tests**

Cover auto fallback, confirmation accepted/declined, background confirm producing fallback_pending, resume retaining the
original policy, agy normalization, and blocking auth/config/task errors.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/test_delegate_config.py tests/python/test_delegate_jobs.py
tests/python/test_delegate_faults.py -q

Expected: FAIL because delegate stores one concrete model only.

- [ ] **Step 3: Resolve and persist the chain before dispatch**

At the task boundary, parse --skill-path, apply precedence, resolve the backend chain, and write the complete portable
and concrete attempts to the job record. Validate these fields in jobstore before atomic writes.

- [ ] **Step 4: Retry in the worker only when authorized**

The worker classifies stderr/exception data, asks only in a foreground interactive process, and advances on AUTO. A
background or JSON confirmation requirement finishes with state fallback_pending and an envelope naming the next model
and rerun command.

- [ ] **Step 5: Preserve context on retry**

Reuse the same prompt file and sandbox/write mode. If the backend produced a valid session_ref before failing, use
resume only when the registry declares resume support; otherwise start the next model fresh with the original prompt.

- [ ] **Step 6: Run delegate tests**

Run: uv run pytest tests/python/test_delegate_config.py tests/python/test_delegate_jobs.py
tests/python/test_delegate_faults.py tests/python/test_delegate_registry.py -q

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add plugins/manifest-delegate/manifest_delegate \
  tests/python/test_delegate_config.py tests/python/test_delegate_jobs.py \
  tests/python/test_delegate_faults.py tests/python/test_delegate_registry.py
git commit -m "feat(delegate): apply ordered model fallback policy"
```

### Task 6: Validate and Translate Frontmatter in Generated Views

**Files:**

- Modify: tools/generate_plugin_views.py
- Modify: configs/claude/scripts/generate_cursor_rules.sh
- Modify: tests/python/manifest_agent/test_generate_plugin_views.py
- Modify: tests/bats/generate_cursor_rules.bats
- Modify: tests/bats/bundle_partition.bats
- Modify: tests/bats/context_budget.bats

**Interfaces:**

- Consumes parse_skill_model_policy().
- Preserves portable metadata in Manifest source skills.
- Emits native model fields only where the target schema supports equivalent semantics.
- Emits launcher guidance where native fallback chains are unsupported.

- [ ] **Step 1: Add failing generation tests**

Use a fixture skill with all four requested harness chains and confirm:

- Codex/Gemini/Cursor/Antigravity views parse.
- agy is normalized.
- Unsupported native fields are absent.
- The generated body points to the Manifest model-aware launcher when native fallback cannot be represented.
- The source frontmatter remains unchanged.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/manifest_agent/test_generate_plugin_views.py -q && bats
tests/bats/generate_cursor_rules.bats

Expected: FAIL because generators ignore model policy.

- [ ] **Step 3: Add shared validation to generation**

Every SKILL.md is parsed through parse_skill_model_policy during generation and --check. Invalid metadata fails with
bundle and skill paths.

- [ ] **Step 4: Translate only supported native semantics**

If a native schema supports one model, emit the first tier's resolved native field and retain fallback guidance in the
body. If it cannot express a model safely, omit the field and add the exact manifest model-aware invocation instruction.
Never emit a Claude model alias into Cursor, Codex, Gemini, or Antigravity metadata.

- [ ] **Step 5: Ratchet the budget**

Update context_budget.bats to count models and model_fallback as part of raw frontmatter. Set the new cap to measured
total plus 800 bytes, matching the existing documented headroom policy.

- [ ] **Step 6: Run generation and budget tests**

```bash
PYTHONPATH=src uv run python tools/generate_plugin_views.py --check --repo-root .
bats tests/bats/generate_cursor_rules.bats tests/bats/bundle_partition.bats \
  tests/bats/context_budget.bats
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/generate_plugin_views.py \
  configs/claude/scripts/generate_cursor_rules.sh \
  tests/python/manifest_agent/test_generate_plugin_views.py \
  tests/bats/generate_cursor_rules.bats tests/bats/bundle_partition.bats \
  tests/bats/context_budget.bats
git commit -m "feat(skills): generate cross-harness model policy"
```

### Task 7: Add Direct Skill Handoff and Documentation

**Files:**

- Modify: src/manifest_agent/cli.py
- Create: src/manifest_agent/skill_run.py
- Test: tests/python/manifest_agent/test_skill_run.py
- Modify: docs/CONFIGURATION.md
- Modify: docs/MODEL-POLICY.md
- Modify: docs/SKILL-NAMING.md
- Modify: CHANGELOG.md

**Interfaces:**

- Adds CLI: manifest skill-run SKILL_PATH --harness NAME [--model-fallback MODE] [--non-interactive].
- Uses native in-session selection where available; otherwise launches a model-targeted CLI handoff with the skill body
  and task context.
- Produces SkillRunReport(harness, attempts, final_model, output, failure, fallback_decisions).

- [ ] **Step 1: Write failing skill-run tests**

Test direct Codex, Gemini, Antigravity, and Cursor invocation; final auto omission; confirmation; non-interactive
recovery; prompt/context preservation; and exact blocking classifications.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/manifest_agent/test_skill_run.py -q

Expected: FAIL because skill-run does not exist.

- [ ] **Step 3: Implement the model-targeted launcher**

Use the harness registry's argv templates and CommandRunner. Construct the prompt from the skill body plus explicit task
text; never serialize credentials or full ambient transcripts. Return a ServiceReport-like JSON record containing
attempts, final model, and fallback decisions.

- [ ] **Step 4: Add CLI confirmation and recovery output**

Interactive text mode uses click.confirm. JSON/non-interactive mode returns one recovery command with --model-fallback
auto or an explicit selected tier.

- [ ] **Step 5: Document schema and precedence**

Document the exact frontmatter example, agy normalization, global confirm default, failure classes, auto final fallback,
non-interactive behavior, and how native versus handoff execution differs.

- [ ] **Step 6: Run focused verification**

```bash
uv run pytest tests/python/model_policy tests/python/agents \
  tests/python/manifest_agent/test_skill_run.py \
  tests/python/test_delegate_config.py tests/python/test_delegate_faults.py -q
bats tests/bats/generate_cursor_rules.bats tests/bats/context_budget.bats
pre-commit run --files configs/claude/scripts/manifest_model_policy/frontmatter.py \
  configs/claude/scripts/agents/runners.py \
  plugins/manifest-delegate/manifest_delegate/worker.py \
  src/manifest_agent/skill_run.py
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/cli.py src/manifest_agent/skill_run.py \
  tests/python/manifest_agent/test_skill_run.py docs/CONFIGURATION.md \
  docs/MODEL-POLICY.md docs/SKILL-NAMING.md CHANGELOG.md
git commit -m "docs(models): document skill fallback policy"
```
