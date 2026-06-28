---
name: browser-test
description: DEPRECATED — superseded by the smoke-orchestrator skill (UI steps with mode agent). Kept one release for migration. Manages legacy browser-use YAML prompts in tests/browser/; migrate via python3 -m smoke_orchestrator.migrate tests/browser --app <app>.
---

# Browser Test Skill

> **⚠️ DEPRECATED — superseded by `smoke-orchestrator`.** Browser E2E now lives in
> the smoke catalog as `type: ui, mode: agent` steps (same browser-use engine,
> plus tiering / state-chaining / JUnit / secret redaction). Migrate existing
> prompts with `python3 -m smoke_orchestrator.migrate tests/browser --app <app>`,
> then author new browser tests via `/smoke-orchestrator`. Kept one release to
> ease migration; will be removed.

AI-powered end-to-end browser testing using [browser-use](https://github.com/browser-use/browser-use).
Manages YAML test prompts in `tests/browser/` and executes them via the browser-use CLI.
Complements static analysis skills (a11y-audit, ux-review, performance-check) with
actual runtime browser validation.

## Arguments

- `$ARGUMENTS` -- One of:
  - Path to a test directory (default: `tests/browser/`)
  - Path to a specific YAML test file
  - A natural-language task description (runs as ad-hoc test)
  - `create` -- Generate new test prompts based on recent code changes
  - `list` -- List all existing browser test files
  - `dry-run` -- Validate YAML test files without executing

---

## Auto-Trigger Criteria

This skill suggests creating or updating browser tests when it detects:

| Change Type | Detection | Example |
|-------------|-----------|---------|
| New page/route | New file in `pages/`, `app/`, `routes/` | `app/settings/page.tsx` |
| New API resolver | New GraphQL resolver or REST endpoint | `resolvers.ts` changes |
| Auth changes | Files matching `auth`, `login`, `session` | `middleware/auth.ts` |
| Form additions | New `<form>` elements or form handlers | `components/checkout-form.tsx` |

When auto-triggered, suggest test prompts inline without blocking workflow.

---

## Instructions

### Step 0: Consult Knowledge Base

Before starting, check for known patterns relevant to browser testing:

```bash
~/.claude/scripts/learning_capture.sh query --language typescript --format llm
~/.claude/scripts/learning_capture.sh query --language general --format llm
```

If the knowledge base contains relevant antipatterns or insights:

- Include them as additional considerations when generating test prompts
- Flag known UI/UX issues that tests should cover

This step is **non-blocking** -- if the knowledge base is empty or the query fails,
proceed with the standard workflow.

### Phase 1: Environment Detection

Check for browser-use availability and test infrastructure:

```bash
# Check browser-use CLI
command -v browser-use

# Check Python environment
python3 -c "import browser_use" 2>/dev/null

# Check for existing test directory
ls tests/browser/*.yaml 2>/dev/null
```

**If browser-use is not installed**:

- Report as `skip` (not `fail`)
- Print install instructions:

  ```bash
  pip install browser-use
  # or
  pipx install browser-use
  ```

- Continue with test prompt creation/validation (YAML-only, no execution)

### Phase 2: Test Discovery

Scan for YAML test prompts:

```bash
find tests/browser/ -name "*.yaml" -o -name "*.yml" | sort
```

For each file, validate the schema:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `task` | Yes | string | Natural language task for the browser agent |
| `judge_context` | Yes | list[string] | Success criteria for evaluation |
| `max_steps` | No | int (default: 15) | Maximum agent steps |
| `url` | No | string | Starting URL (overrides task navigation) |
| `tags` | No | list[string] | Categorization tags (smoke, auth, crud, a11y) |

Report invalid YAML files with specific validation errors.

### Phase 3: Execute Tests

For each valid test file, run via the wrapper script:

```bash
~/.claude/scripts/browser_test.sh run tests/browser/smoke-test.yaml
```

Or for all tests:

```bash
~/.claude/scripts/browser_test.sh run-all tests/browser/
```

**Execution behavior**:

- 60-second timeout per test (configurable via `--timeout`)
- Headless mode by default (`--headless`)
- Screenshots saved to `/tmp/browser_test_screenshots/`
- Results captured as JSON

**For `create` mode**: Analyze recent code changes and generate YAML test prompts:

1. Run `git diff --name-only HEAD~1` to identify changed files
2. Filter for frontend/API changes matching auto-trigger criteria
3. For each change, generate a YAML test prompt with:
   - Descriptive `task` covering the user-facing behavior
   - Specific `judge_context` for success validation
   - Appropriate `max_steps` based on complexity
   - `tags` matching the change type (smoke, auth, crud, form)
4. Write to `tests/browser/<feature-name>.yaml`

**For `dry-run` mode**: Validate all YAML files without browser execution:

1. Parse each YAML file
2. Validate schema (task, judge_context required)
3. Report valid/invalid files
4. Estimate token cost based on max_steps

### Phase 4: Results Report

Generate a structured report:

```markdown
## Browser Test Report

**Project**: {absolute-path}
**Tests**: {total} total, {passed} passed, {failed} failed, {skipped} skipped
**Timestamp**: {ISO-8601}

### Results

| Test | Status | Steps | Duration | Summary |
|------|--------|-------|----------|---------|
| smoke-test.yaml | pass | 5/10 | 12s | Homepage loaded, nav visible |
| auth-flow.yaml | fail | 15/15 | 45s | Login button not found |
| checkout.yaml | skip | - | - | browser-use not installed |

### Failures

#### auth-flow.yaml
- **Task**: Navigate to login page, enter credentials, verify dashboard
- **Failed at step**: 8 — Could not find login button
- **Judge context**: "User must reach the dashboard after login"
- **Screenshot**: /tmp/browser_test_screenshots/auth-flow-step8.png

### Verdict

- **PASS**: All tests passed
- **WARN**: Some tests skipped (tool missing)
- **FAIL**: One or more tests failed
```

---

## Parallel Agent Integration

This skill uses parallel agents **conditionally**:

| Trigger | Reason |
|---------|--------|
| Critical user flows (auth, payment) | Cross-verify test prompt quality |
| 3+ test files in a single run | Validate coverage completeness |
| Test failures on critical paths | Get multiple perspectives on fix |

When triggered:

```bash
~/.claude/scripts/parallel_agent.py --json --validate --timeout 600 \
  --cursor-model flash --claude-model sonnet \
  "Review these browser test definitions for completeness and correctness: <YAML_CONTENTS>"
```

---

## Non-Blocking Behavior

This skill follows the auto-trigger pattern:

- **Never blocks** user workflow or command execution
- **Suggests tests** when code changes match trigger criteria
- **Reports inline** without interrupting primary tasks
- **Degrades gracefully** when browser-use is not installed

---

## Safety Checks

- Never install packages -- report missing tools with install instructions
- Never modify source code -- only creates/updates files in `tests/browser/`
- Respect `.gitignore` -- do not scan ignored directories
- Cap test execution at 60 seconds per test (configurable)
- Cap max_steps at 25 to limit LLM token consumption
- Save screenshots to temp directory, not project tree
- Sanitize test prompts to avoid exposing real credentials

---

## YAML Test Prompt Format

```yaml
# tests/browser/smoke-test.yaml
task: "Navigate to http://localhost:3000 and verify the homepage loads correctly"
judge_context:
  - "The page must load without JavaScript errors"
  - "The main navigation must be visible"
  - "The page title must match the app name"
max_steps: 10
url: "http://localhost:3000"
tags: [smoke, homepage]
```

### Common Test Categories

| Tag | Purpose | Example |
|-----|---------|---------|
| `smoke` | Basic page load and navigation | Homepage renders, nav works |
| `auth` | Authentication flows | Login, logout, session persistence |
| `crud` | Create/read/update/delete operations | Add item, edit, delete |
| `form` | Form submissions and validation | Submit form, check validation errors |
| `a11y` | Runtime accessibility checks | Keyboard navigation, screen reader |
| `perf` | Performance measurement | Page load time, interaction delay |

---

## Learning Capture (Optional)

After completing test execution, capture significant findings:

1. For recurring test failures:

   ```bash
   ~/.claude/scripts/learning_capture.sh add \
     --category antipattern --language typescript \
     --title "<failure pattern>" \
     --description "<what failed and recommended fix>" \
     --source browser-test --confidence medium
   ```

2. For new testing patterns discovered:

   ```bash
   ~/.claude/scripts/learning_capture.sh add \
     --category pattern --language general \
     --title "<testing pattern>" \
     --description "<what works well for browser testing>" \
     --source browser-test --confidence medium
   ```

3. This step is **non-blocking** -- failures in learning capture should not affect the test report.
