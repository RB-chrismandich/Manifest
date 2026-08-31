# Generic CLI Agent Refactor + Model Refresh + Antigravity Agent — Implementation Plan

> **EXECUTED 2026-06-11 — read this first.** All 10 tasks are complete. The task
> bodies below are preserved as written before execution; where review or live
> verification forced a change, the SPEC and the code are authoritative, not the
> task text. Deviations applied during execution:
>
> 1. **`prompt_args` schema slot** (commit `752ada5`): live testing revealed
>    `agy --print` is a Go flag that takes the prompt as its *value* — a trailing
>    positional prompt is silently swallowed. `CLIAgent` gained
>    `prompt_args` (default `["{prompt}"]`); antigravity uses
>    `base_args: []` + `prompt_args: ["--print", "{prompt}"]`, superseding the
>    `base_args: ["--print"]` + positional-prompt shape in Tasks 1-2 below.
> 2. **Missing `binary` raises `ValueError`** (commit `838f484`): review hardening;
>    supersedes the `spec["binary"]` direct access shown in Task 2.
> 3. **Empty-arg filter in `_build_command`** (commit `838f484`): args that
>    substitute to `""` (stray `{output_file}` with no file) are dropped from argv.
> 4. **Codex tier IDs** (commit `fed4f27`, per Task 5's own decision rules):
>    `o4-mini/o3/o3-pro` → `gpt-5.4-mini/gpt-5.4/gpt-5.5`; tests updated in the
>    same commit. Task 1/2 snippets predate the Task 5 refresh by design.
> 5. **Sync test also covers `rate_limits`** (commit `fed4f27`), with
>    `tokens_per_minute` reconciled into `config.py` defaults.
> 6. **Bootstrap scope** : agy detection shipped in the deploy summary only
>    (`bootstrap/lib/deploy.sh`); no `install.sh`/`auth.sh` agy auth-detection
>    was added — agy has no non-interactive auth-status command to probe, and
>    `check_status.sh` covers CLI availability.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `CursorAgent`/`CodexAgent` classes with one YAML-driven `CLIAgent`, add Antigravity (`agy`) as the 5th parallel agent, refresh all model tier pins, govern `spec_review.sh`'s model from the same registry, and add a warn-only model staleness check.

**Architecture:** `CLIAgent(BaseAgent)` reads per-provider command shape from a new `cli_agents:` config block (binary, base_args, model_args, output strategy). All provider variation is data. Model tiers stay pinned in `parallel_agent.yml` (mirrored in `config.py` defaults, kept in sync by a test); a new `model_check.sh` compares pins against live provider listings.

**Tech Stack:** Python 3 (asyncio, pytest, pytest-asyncio), Bash (bats-core), YAML.

**Spec:** `docs/superpowers/specs/2026-06-11-cli-agent-refactor-design.md`

**Working directory:** repo root (the worktree). All paths below are repo-relative.

**Test commands used throughout:**

```bash
python3 -m pytest tests/python/agents/ tests/python/test_parallel_agent.py -v   # python
bats tests/bats/<file>.bats                                                      # shell
```

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `configs/claude/config/parallel_agent.yml` | Modify | Add `cli_agents:`, antigravity entries, refreshed `model_tiers` |
| `configs/claude/scripts/agents/config.py` | Modify | Mirror the same additions in `_default_config()` + `ServiceConfig` defaults |
| `configs/claude/scripts/agents/runners.py` | Modify | Add `CLIAgent`; delete `CursorAgent`, `CodexAgent` |
| `configs/claude/scripts/agents/cli.py` | Modify | Construct `CLIAgent` per provider; antigravity flags |
| `configs/claude/scripts/agents/__init__.py` | Modify | Export `CLIAgent` instead of removed classes |
| `configs/claude/scripts/agents/orchestrator.py` | Modify | `check_credits`: config-resolved model IDs + antigravity entry |
| `configs/claude/scripts/test_oauth.py` | Modify | `CursorAgent` → `CLIAgent("cursor", ...)` |
| `configs/claude/scripts/spec_review.sh` | Modify | `SPEC_REVIEW_MODEL` seam |
| `configs/claude/scripts/model_check.sh` | Create | Warn-only staleness checker (functions, source-able) |
| `configs/claude/scripts/check_status.sh` | Modify | Antigravity rows; invoke `model_check.sh` |
| `configs/claude/config/command_config.yml` | Modify | `task_model_defaults`: fable for security; antigravity column |
| `bootstrap/lib/deploy.sh` | Modify | agy CLI detection in install summary |
| `tests/python/agents/test_runners.py` | Modify | `CLIAgent` tests replace `CodexAgent` tests |
| `tests/python/agents/test_config.py` | Modify | `cli_agents` defaults + repo-YAML sync test |
| `tests/python/test_parallel_agent.py` | Modify | Port `TestCodexAgent` → `TestCLIAgent` |
| `tests/bats/spec_review.bats` | Modify | Model seam tests |
| `tests/bats/model_check.bats` | Create | Staleness checker tests |
| Docs (`configs/claude/CLAUDE.md`, `configs/claude/references/parallel-agent.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/CONFIGURATION.md`) | Modify | 5-agent tables, new flags, refreshed tier names |

---

### Task 1: `cli_agents` config block (YAML + defaults + sync test)

**Files:**
- Modify: `configs/claude/config/parallel_agent.yml`
- Modify: `configs/claude/scripts/agents/config.py`
- Test: `tests/python/agents/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/python/agents/test_config.py`:

```python
# ---------------------------------------------------------------------------
# cli_agents config block
# ---------------------------------------------------------------------------

import yaml

REPO_YAML = REPO_ROOT / "configs" / "claude" / "config" / "parallel_agent.yml"


class TestCliAgentsConfig:
    def test_default_config_has_cli_agents(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        for provider in ("cursor", "codex", "antigravity"):
            spec = config.get(f"cli_agents.{provider}")
            assert spec is not None, f"missing cli_agents.{provider}"
            assert "binary" in spec
            assert "model_args" in spec
            assert spec.get("output") in ("stdout", "file_then_stdout")

    def test_default_config_has_antigravity_entries(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert config.get("rate_limits.antigravity.requests_per_minute") == 100
        assert config.get("credit_fallback.antigravity") == [
            "advanced",
            "flash",
            "mini",
        ]
        tiers = config.get("model_tiers.antigravity")
        assert set(tiers) == {"mini", "flash", "advanced"}

    def test_defaults_match_repo_yaml(self, tmp_path):
        """config.py defaults and parallel_agent.yml must never disagree."""
        with open(REPO_YAML) as f:
            repo = yaml.safe_load(f)
        defaults = Config(config_path=str(tmp_path / "none.yml")).config
        for section in ("cli_agents", "model_tiers", "credit_fallback"):
            assert repo[section] == defaults[section], (
                f"{section} drifted between parallel_agent.yml and "
                f"config.py _default_config()"
            )
```

If `test_config.py` lacks a `REPO_ROOT`, add at the top (same pattern as `test_runners.py`):

```python
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/python/agents/test_config.py -v -k CliAgents`
Expected: FAIL (`cli_agents.cursor` is None; `defaults_match_repo_yaml` mismatch)

- [ ] **Step 3: Add `cli_agents` + antigravity entries to `parallel_agent.yml`**

In `configs/claude/config/parallel_agent.yml`, add under `rate_limits:` after the `codex:` entry:

```yaml
  antigravity:
    requests_per_minute: 100
    burst_size: 10
```

Add to `model_tiers:` after the `codex:` entry (exact slugs are re-verified in Task 5):

```yaml
  antigravity:
    mini: "Gemini 3.5 Flash (Low)"
    flash: "Gemini 3.5 Flash (High)"
    advanced: "Claude Opus 4.6 (Thinking)"
```

Add to `credit_fallback:`:

```yaml
  antigravity:
    - advanced
    - flash
    - mini
```

Add a new top-level block after `model_tiers:`:

```yaml
# CLI agent command definitions (consumed by CLIAgent in agents/runners.py).
# base_args: always passed. model_args: appended only when a model is resolved
# (dropped atomically for tier "auto" — no dangling flags). {output_file} in
# base_args triggers tempfile creation; output "file_then_stdout" reads it
# with priority file > stdout > stderr-on-error.
cli_agents:
  cursor:
    binary: cursor
    base_args: []
    model_args: ["--model", "{model}"]
    output: stdout
  codex:
    binary: codex
    base_args: ["exec", "--full-auto", "--color", "never",
                "--output-last-message", "{output_file}"]
    model_args: ["--model", "{model}"]
    output: file_then_stdout
  antigravity:
    binary: agy
    base_args: ["--print"]
    model_args: ["--model", "{model}"]
    output: stdout
```

- [ ] **Step 4: Mirror in `config.py` `_default_config()` and `ServiceConfig`**

In `configs/claude/scripts/agents/config.py`, replace the `_default_config` body sections:

In `"rate_limits"` add: `"antigravity": {"requests_per_minute": 100, "burst_size": 10},`

Replace the `"model_tiers"` dict with (note: `cursor` was previously missing from defaults — add it so the sync test can hold):

```python
            "model_tiers": {
                "claude": {
                    "haiku": "claude-haiku-4-5-20251001",
                    "sonnet": "claude-sonnet-4-5-20250929",
                    "opus": "claude-opus-4-6",
                },
                "gemini": {
                    "flash": "gemini-3-flash-preview",
                    "pro": "gemini-3-pro-preview",
                },
                "cursor": {
                    "mini": "gpt-5.1-codex-mini",
                    "flash": "gpt-5.1-codex",
                    "advanced": "gpt-5.2",
                },
                "codex": {
                    "mini": "o4-mini",
                    "flash": "o3",
                    "advanced": "o3-pro",
                },
                "antigravity": {
                    "mini": "Gemini 3.5 Flash (Low)",
                    "flash": "Gemini 3.5 Flash (High)",
                    "advanced": "Claude Opus 4.6 (Thinking)",
                },
            },
            "cli_agents": {
                "cursor": {
                    "binary": "cursor",
                    "base_args": [],
                    "model_args": ["--model", "{model}"],
                    "output": "stdout",
                },
                "codex": {
                    "binary": "codex",
                    "base_args": [
                        "exec", "--full-auto", "--color", "never",
                        "--output-last-message", "{output_file}",
                    ],
                    "model_args": ["--model", "{model}"],
                    "output": "file_then_stdout",
                },
                "antigravity": {
                    "binary": "agy",
                    "base_args": ["--print"],
                    "model_args": ["--model", "{model}"],
                    "output": "stdout",
                },
            },
```

In `"credit_fallback"` add: `"antigravity": ["advanced", "flash", "mini"],`

In `ServiceConfig._load()` all-enabled defaults, add `"antigravity": {"enabled": True},` after `"codex"`.

(Model *values* here still match today's YAML; Task 5 refreshes both sides together. The sync test only demands they agree.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/python/agents/test_config.py -v`
Expected: PASS (all, including pre-existing tests)

Run: `python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/parallel_agent.yml'))" && yamllint configs/claude/config/parallel_agent.yml`
Expected: no output / no errors

- [ ] **Step 6: Commit**

```bash
git add configs/claude/config/parallel_agent.yml configs/claude/scripts/agents/config.py tests/python/agents/test_config.py
git commit -m "feat(agents): add cli_agents config block and antigravity entries"
```

---

### Task 2: `CLIAgent` class

**Files:**
- Modify: `configs/claude/scripts/agents/runners.py`
- Test: `tests/python/agents/test_runners.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/python/agents/test_runners.py` (and add `CLIAgent` to the existing `from agents.runners import ...` line):

```python
# ---------------------------------------------------------------------------
# CLIAgent
# ---------------------------------------------------------------------------


class TestCLIAgentCommandAssembly:
    def test_unknown_provider_raises(self, tmp_path):
        with pytest.raises(ValueError, match="no cli_agents config"):
            CLIAgent(
                "nonexistent",
                model="flash",
                rate_limiter=_make_limiter(),
                config=_make_config(tmp_path),
            )

    def test_codex_auto_drops_model_args_atomically(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello", output_file="/tmp/out.txt")
        assert agent.model_name is None
        assert "--model" not in cmd  # no dangling flag
        assert cmd[0] == "codex"
        assert cmd[-1] == "hello"  # prompt is last
        assert "/tmp/out.txt" in cmd  # {output_file} substituted

    def test_codex_tier_resolves_via_model_tiers(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="mini",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello", output_file="/tmp/out.txt")
        i = cmd.index("--model")
        assert cmd[i + 1] == "o4-mini"

    def test_cursor_tier_resolves_via_model_tiers(self, tmp_path):
        # Deliberate behavior change: cursor now honors model_tiers.cursor
        # (the old CursorAgent passed the raw tier string through).
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        i = cmd.index("--model")
        assert cmd[i + 1] == "gpt-5.1-codex"

    def test_custom_model_passes_through(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="custom-model-123",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        assert agent.model_name == "custom-model-123"

    def test_antigravity_command_shape(self, tmp_path):
        agent = CLIAgent(
            "antigravity",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        assert cmd[0] == "agy"
        assert cmd[1] == "--print"
        i = cmd.index("--model")
        assert cmd[i + 1] == "Gemini 3.5 Flash (High)"
        assert cmd[-1] == "hello"


class TestCLIAgentExecution:
    def test_missing_binary(self, tmp_path, monkeypatch):
        import shutil

        monkeypatch.setattr(shutil, "which", lambda _: None)
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = asyncio.run(agent._execute_impl("test", "prompt"))
        assert result["status"] == "missing"
        assert "codex" in result["error"]

    def test_stdout_strategy_collects_stdout(self, tmp_path):
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = agent._collect_output(0, b"the answer\n", b"", None)
        assert result["status"] == "complete"
        assert result["output"] == "the answer"

    def test_file_strategy_prefers_file_over_stdout(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        out = tmp_path / "out.txt"
        out.write_text("from file\n")
        result = agent._collect_output(0, b"from stdout", b"", str(out))
        assert result["output"] == "from file"

    def test_file_strategy_falls_back_to_stdout(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        out = tmp_path / "empty.txt"
        out.write_text("")
        result = agent._collect_output(0, b"from stdout", b"", str(out))
        assert result["output"] == "from stdout"

    def test_no_output_nonzero_exit_is_failed(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = agent._collect_output(1, b"", b"boom", None)
        assert result["status"] == "failed"
        assert "boom" in result["error"]

    def test_real_subprocess_roundtrip(self, tmp_path):
        """End-to-end through create_subprocess_exec using /bin/echo as the binary."""
        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "echo",
            "base_args": ["prefix"],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        config.config["model_tiers"]["fake"] = {"flash": "fake-model-1"}
        agent = CLIAgent(
            "fake", model="flash", rate_limiter=_make_limiter(), config=config
        )
        result = asyncio.run(agent._execute_impl("hello world", "prompt"))
        assert result["status"] == "complete"
        assert result["output"] == "prefix --model fake-model-1 hello world"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/python/agents/test_runners.py -v -k CLIAgent`
Expected: FAIL with `ImportError: cannot import name 'CLIAgent'`

- [ ] **Step 3: Implement `CLIAgent` in `runners.py`**

Add after the `GeminiAgent` class (before `CursorAgent`, which is removed in Task 3):

```python
# ---------------------------------------------------------------------------
# CLIAgent
# ---------------------------------------------------------------------------


class CLIAgent(BaseAgent):
    """Generic CLI-based agent driven by the cli_agents config block.

    All provider variation (binary, argument shape, output capture) is data in
    parallel_agent.yml — adding a CLI provider is a configuration change, not a
    new class. Args are always exec'd as a list (never a shell string).
    """

    def __init__(
        self,
        provider: str,
        model: str = "flash",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Optional[Logger] = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        config = config or Config()
        super().__init__(
            provider,
            model,
            timeout,
            rate_limiter,
            config,
            logger,
            streaming,
            progress_callback,
        )
        spec = config.get(f"cli_agents.{provider}")
        if not spec:
            raise ValueError(f"no cli_agents config for provider: {provider}")
        self.binary = spec["binary"]
        self.base_args = list(spec.get("base_args", []))
        self.model_args = list(spec.get("model_args", []))
        self.output_strategy = spec.get("output", "stdout")
        self.model_name = self._resolve_model(model)

    def _resolve_model(self, tier: str) -> Optional[str]:
        """Resolve model tier to full model name. Returns None for 'auto'."""
        if tier == "auto":
            return None
        resolved = self.config.get(f"model_tiers.{self.name}.{tier}")
        return resolved if resolved else tier

    def _build_command(
        self, prompt: str, output_file: Optional[str] = None
    ) -> List[str]:
        """Assemble argv: binary + base_args + optional model group + prompt.

        model_args are appended only when a model is resolved — the group is
        dropped atomically, so an optional model can never leave a dangling flag.
        """

        def _subst(arg: str) -> str:
            arg = arg.replace("{output_file}", output_file or "")
            arg = arg.replace("{model}", self.model_name or "")
            return arg

        cmd = [self.binary] + [_subst(a) for a in self.base_args]
        if self.model_name:
            cmd += [_subst(a) for a in self.model_args]
        cmd.append(prompt)
        return cmd

    def _collect_output(
        self, returncode: int, stdout: bytes, stderr: bytes, output_file: Optional[str]
    ) -> Dict:
        """Apply the provider's output strategy: file > stdout > stderr-on-error."""
        output = ""
        if output_file and os.path.exists(output_file):
            with open(output_file, "r") as f:
                output = f.read().strip()
        if not output:
            output = stdout.decode("utf-8", errors="ignore").strip()
        if not output and returncode != 0:
            return {
                "status": "failed",
                "error": stderr.decode("utf-8", errors="ignore"),
                "output": "",
                "model": self.model_name or "auto",
            }
        return {
            "status": "complete",
            "output": output,
            "model": self.model_name or "auto",
            "validated": False,
        }

    async def _execute_impl(self, prompt: str, mode: str) -> Dict:
        import shutil
        import tempfile

        if not shutil.which(self.binary):
            return {
                "status": "missing",
                "error": f"{self.binary} command not found",
                "output": "",
            }

        output_file = None
        if self.output_strategy == "file_then_stdout":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix=f"{self.name}_out_"
            ) as tmp:
                output_file = tmp.name

        try:
            cmd = self._build_command(prompt, output_file)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return self._collect_output(proc.returncode, stdout, stderr, output_file)
        finally:
            if output_file:
                try:
                    os.unlink(output_file)
                except OSError:
                    pass
```

Also add `List` to the existing `typing` import in `runners.py` if not present (it is: `from typing import Any, Dict, List, Optional`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/python/agents/test_runners.py -v`
Expected: PASS (new CLIAgent tests AND the legacy CodexAgent tests — both classes coexist until Task 3)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/agents/runners.py tests/python/agents/test_runners.py
git commit -m "feat(agents): add generic YAML-driven CLIAgent"
```

**Deliberate behavior changes vs the old classes (documented for review):**
1. Cursor now resolves tiers through `model_tiers.cursor` (the old class passed raw tier strings like "flash" to `cursor --model`; the YAML mapping existed but was dead).
2. Cursor inherits Codex's more forgiving success rule (non-empty output counts as success even on non-zero exit; old CursorAgent failed on any non-zero exit).
3. Cursor output is now `.strip()`ed.

---

### Task 3: Migrate call sites, delete old classes

**Files:**
- Modify: `configs/claude/scripts/agents/runners.py` (delete `CursorAgent`, `CodexAgent`)
- Modify: `configs/claude/scripts/agents/cli.py:23-29, 239-261`
- Modify: `configs/claude/scripts/agents/__init__.py:22-23, 44-45`
- Modify: `configs/claude/scripts/test_oauth.py:240, 280-288`
- Modify: `tests/python/agents/test_runners.py` (drop `TestCodexAgent`, import)
- Modify: `tests/python/test_parallel_agent.py:33, 620-662`

- [ ] **Step 1: Update existing tests to target `CLIAgent`**

In `tests/python/agents/test_runners.py`: change the import to `from agents.runners import BaseAgent, CLIAgent` and **delete** the whole `TestCodexAgent` class (lines 88-111) — its four cases are superseded by `TestCLIAgentCommandAssembly`/`TestCLIAgentExecution` from Task 2.

In `tests/python/test_parallel_agent.py`: change line 33 to

```python
from agents.runners import BaseAgent, CLIAgent  # noqa: E402
```

and replace the `TestCodexAgent` class body (keep the class as the CLI-agent regression suite):

```python
class TestCodexAgent:
    """Codex behavior through the generic CLIAgent (regression for the refactor)."""

    def test_resolve_model_auto(self, tmp_path):
        """Auto tier resolves to None (let codex choose)."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "auto", 60, limiter, config=config)
        assert agent.model_name is None

    def test_resolve_model_named_tier(self, tmp_path):
        """Named tier resolves to correct model from config."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "mini", 60, limiter, config=config)
        assert agent.model_name == "o4-mini"

    def test_resolve_model_custom(self, tmp_path):
        """Custom model name passes through as-is."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "custom-model-123", 60, limiter, config=config)
        assert agent.model_name == "custom-model-123"

    @pytest.mark.asyncio
    async def test_execute_missing_codex(self, tmp_path, monkeypatch):
        """Returns 'missing' status when codex is not installed."""
        import shutil

        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "auto", 60, limiter, config=config)

        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        result = await agent._execute_impl("test prompt", "prompt")
        assert result["status"] == "missing"
```

- [ ] **Step 2: Run tests to verify current state**

Run: `python3 -m pytest tests/python/agents/test_runners.py tests/python/test_parallel_agent.py -v -k "Codex or CLIAgent"`
Expected: PASS already (CLIAgent exists since Task 2) — these are now pinned to the new API before the deletion.

- [ ] **Step 3: Delete `CursorAgent` and `CodexAgent` from `runners.py`**

Remove both class blocks (the `# CursorAgent` and `# CodexAgent` sections, currently `runners.py:402-585`). `CLIAgent` remains the last class in the file.

- [ ] **Step 4: Update `__init__.py`**

In `configs/claude/scripts/agents/__init__.py`: in the `from agents.runners import (...)` block replace the two names `CodexAgent, CursorAgent,` with `CLIAgent,`; in `__all__` replace `"CursorAgent", "CodexAgent",` with `"CLIAgent",`.

- [ ] **Step 5: Update `cli.py` construction**

Replace the import block (`cli.py:23-29`):

```python
from agents.runners import (
    BaseAgent,
    ClaudeAgent,
    CLIAgent,
    GeminiAgent,
)
```

Replace the cursor/codex construction blocks (`cli.py:239-261`):

```python
    cli_limiters = {
        "cursor": cursor_limiter,
        "codex": codex_limiter,
    }
    cli_models = {
        "cursor": args.cursor_model,
        "codex": args.codex_model,
    }
    for provider in ("cursor", "codex"):
        if enabled[provider]:
            agents.append(
                CLIAgent(
                    provider,
                    cli_models[provider],
                    timeout,
                    cli_limiters[provider],
                    config=config,
                    logger=logger,
                    streaming=streaming,
                )
            )
```

(Antigravity joins this loop in Task 4.)

- [ ] **Step 6: Update `test_oauth.py`**

Line 240: `from agents.runners import ClaudeAgent, GeminiAgent, CLIAgent`
Lines 280-288: replace `CursorAgent(` with `CLIAgent("cursor", ` keeping the remaining arguments unchanged, and update the print strings from `CursorAgent` to `CLIAgent(cursor)`.

- [ ] **Step 7: Run the full python suite**

Run: `python3 -m pytest tests/python/ -v`
Expected: PASS, zero references to removed classes

Run: `grep -rn "CursorAgent\|CodexAgent" configs/ tests/ --include="*.py"`
Expected: no output

- [ ] **Step 8: Commit**

```bash
git add configs/claude/scripts/agents/ configs/claude/scripts/test_oauth.py tests/python/
git commit -m "refactor(agents): replace CursorAgent/CodexAgent with CLIAgent at all call sites"
```

---

### Task 4: Antigravity wiring (flags, services, check_credits)

**Files:**
- Modify: `configs/claude/scripts/agents/cli.py`
- Modify: `configs/claude/scripts/agents/orchestrator.py` (`check_credits`)
- Test: `tests/python/test_parallel_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/python/test_parallel_agent.py`:

```python
# ---------------------------------------------------------------------------
# Antigravity agent wiring
# ---------------------------------------------------------------------------


class TestAntigravityAgent:
    def test_antigravity_tier_resolution(self, tmp_path):
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("antigravity", "advanced", 60, limiter, config=config)
        assert agent.name == "antigravity"
        assert agent.model_name == "Claude Opus 4.6 (Thinking)"
        assert agent.binary == "agy"

    def test_antigravity_missing_binary(self, tmp_path, monkeypatch):
        import shutil

        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        agent = CLIAgent("antigravity", "flash", 60, RateLimiter(), config=config)
        result = asyncio.run(agent._execute_impl("test", "prompt"))
        assert result["status"] == "missing"

    def test_services_default_includes_antigravity(self, tmp_path):
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        assert sc.is_enabled("antigravity") is True


class TestCLIFlagsAntigravity:
    """The CLI surface advertises antigravity flags."""

    SCRIPT = str(REPO_ROOT / "configs" / "claude" / "scripts" / "parallel_agent.py")

    def test_help_lists_antigravity_flags(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, self.SCRIPT, "--help"],
            capture_output=True,
            text=True,
        )
        assert "--antigravity-model" in result.stdout
        assert "--antigravity-only" in result.stdout
        assert "--no-antigravity" in result.stdout
```

(`asyncio`, `sys`, `REPO_ROOT`, `Config`, `RateLimiter`, `ServiceConfig` are already imported/defined in this file — verify at the top before running.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/python/test_parallel_agent.py -v -k Antigravity`
Expected: `test_services_default_includes_antigravity` PASSES (Task 1 added it); the help-flag test FAILS; tier test PASSES. (Only the CLI surface is missing.)

- [ ] **Step 3: Add antigravity to `cli.py`**

Argument definitions (after the `--codex-model` / `--codex-only` / `--no-codex` lines):

```python
    parser.add_argument(
        "--antigravity-model", default="flash", help="Antigravity model tier"
    )
    parser.add_argument(
        "--antigravity-only", action="store_true", help="Run only Antigravity"
    )
    parser.add_argument(
        "--no-antigravity", action="store_true", help="Disable Antigravity agent"
    )
```

Rate limiter (after `codex_limiter`):

```python
    antigravity_limiter = RateLimiter(**config.get("rate_limits.antigravity", {}))
```

`enabled` map: add `"antigravity": services.is_enabled("antigravity"),`
`only_flags` map: add `"antigravity": args.antigravity_only,`
`--no-*` overrides: add

```python
    if args.no_antigravity:
        enabled["antigravity"] = False
```

Extend the Task 3 construction loop:

```python
    cli_limiters = {
        "cursor": cursor_limiter,
        "codex": codex_limiter,
        "antigravity": antigravity_limiter,
    }
    cli_models = {
        "cursor": args.cursor_model,
        "codex": args.codex_model,
        "antigravity": args.antigravity_model,
    }
    for provider in ("cursor", "codex", "antigravity"):
```

- [ ] **Step 4: Add antigravity to `check_credits` in `orchestrator.py`**

After the `results["cursor"] = {"status": "assumed_available"}` line:

```python
    # Antigravity (subscription CLI, no credit API to probe)
    import shutil as _shutil

    if _shutil.which("agy"):
        results["antigravity"] = {"status": "assumed_available"}
    else:
        results["antigravity"] = {"status": "not_installed"}
```

(The function already does `import shutil` lower down for codex; hoist a single `import shutil` to the top of `check_credits` and drop the duplicate instead of aliasing, if preferred — either way only one import remains.)

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/python/ -v`
Expected: PASS

Manual smoke (requires agy installed):

```bash
configs/claude/scripts/parallel_agent.py --antigravity-only --no-stream "Reply with exactly: OK"
```

Expected: table output with one `Antigravity` row, status `✔ complete`.

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/agents/cli.py configs/claude/scripts/agents/orchestrator.py tests/python/test_parallel_agent.py
git commit -m "feat(agents): wire antigravity (agy) as 5th parallel agent"
```

---

### Task 5: Model refresh (verify live, then pin)

**Files:**
- Modify: `configs/claude/config/parallel_agent.yml` (`model_tiers`, `credit_fallback.claude`)
- Modify: `configs/claude/scripts/agents/config.py` (same values)
- Modify: `configs/claude/scripts/agents/orchestrator.py` (`check_credits` hardcoded IDs)
- Modify: `configs/claude/config/command_config.yml` (`task_model_defaults`)
- Test: `tests/python/agents/test_config.py` (sync test from Task 1 keeps both sides honest)

- [ ] **Step 1: Verify current model IDs live**

Run each; record results:

```bash
# Anthropic (skip if no key; then rely on documented IDs below)
curl -s https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
  | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data']]"

# Gemini (skip if no key)
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" \
  | python3 -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin).get('models',[])]"

# Antigravity catalog + slug format
agy models
agy --model "Gemini 3.5 Flash (High)" -p "Reply with exactly: OK"

# Codex / Cursor: check the CLI's error listing for valid models
codex exec --model definitely-not-a-model "hi" 2>&1 | head -5
cursor --help 2>&1 | grep -iA3 model
```

**Decision rules (apply to every provider):**
- Claude: known-current IDs are `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`, `claude-fable-5`; confirm against the API listing when a key is available.
- Gemini: pick the GA (non `-preview`) IDs for the newest Flash and Pro families the listing returns (expected families: gemini-3.5-flash, gemini-3.1-pro). If only previews exist, pin the preview ID.
- Antigravity: pin the exact strings `agy models` prints, in the exact accepted `--model` format (verify the smoke call returns OK; if it rejects display names, use the format its error message suggests).
- Cursor/Codex: pin what their CLI/docs report as current; if a CLI gives no listing and docs are inconclusive, keep the existing pin and note it in the commit message (the staleness check from Task 7 will keep watching it).

- [ ] **Step 2: Update `model_tiers` in BOTH `parallel_agent.yml` and `config.py` with verified IDs**

The claude block becomes (verbatim — these IDs are confirmed-current):

```yaml
  claude:
    haiku: "claude-haiku-4-5-20251001"
    sonnet: "claude-sonnet-4-6"
    opus: "claude-opus-4-8"
    fable: "claude-fable-5"
```

Gemini/cursor/codex/antigravity blocks: the IDs recorded in Step 1. Update `config.py` `_default_config()` `model_tiers` to the identical values.

Update `credit_fallback.claude` in both files:

```yaml
  claude:
    - fable
    - opus
    - sonnet
    - haiku
```

(`config.py`: `"claude": ["fable", "opus", "sonnet", "haiku"],`)

- [ ] **Step 3: Replace hardcoded IDs in `check_credits`**

`orchestrator.py` `check_credits` hardcodes three IDs. Make them config-resolved:

- `orchestrator.py:484` `model="claude-haiku-4-5-20251001"` → `model=config.get("model_tiers.claude.haiku", "claude-haiku-4-5-20251001")`
- `orchestrator.py:511` and `:519` `"gemini-3-flash-preview"` → `config.get("model_tiers.gemini.flash", "gemini-3-flash-preview")` (assign once to a local `gemini_flash = ...` above the `if HAS_GENAI_NEW:` branch and use it in both)
- `orchestrator.py:547` `"o4-mini"` → `config.get("model_tiers.codex.mini", "o4-mini")`

- [ ] **Step 4: Update `task_model_defaults` in `command_config.yml`**

In the `task_model_defaults:` section (`command_config.yml:432-...`), update the `security` entry and add antigravity to every task type:

```yaml
  security:
    cursor: advanced
    claude: fable
    gemini: pro
    antigravity: advanced
    reason: "Security-critical code requires maximum model capability"
```

For `review`, `analyze`, `issue_triage`, `issue_prioritize`: add `antigravity: flash`.
For `improve` and `quick`: add `antigravity: mini`.
All other values unchanged.

- [ ] **Step 5: Run tests + lint**

Run: `python3 -m pytest tests/python/ -v`
Expected: PASS — in particular `test_defaults_match_repo_yaml` proves YAML and `config.py` agree, and the Task 2/3 tier tests still pass because they read from the same defaults. **If any tier test pinned an old ID (e.g. `o4-mini` changed in Step 1), update that test's expected value in the same commit.**

Run: `yamllint configs/claude/config/parallel_agent.yml configs/claude/config/command_config.yml`
Expected: clean

- [ ] **Step 6: Live smoke test (best-effort, requires keys/CLIs)**

```bash
configs/claude/scripts/parallel_agent.py --check-credits
```

Expected: JSON with `claude/gemini/cursor/codex/antigravity` entries; no `quota_exceeded` caused by an invalid model ID (an invalid pin shows up as an API "model not found" error here).

- [ ] **Step 7: Commit**

```bash
git add configs/claude/config/ configs/claude/scripts/agents/
git commit -m "feat(models): refresh model tier pins (fable/opus-4-8/sonnet-4-6, gemini 3.5/3.1, agy catalog)"
```

---

### Task 6: `SPEC_REVIEW_MODEL` seam in `spec_review.sh`

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing bats tests**

Append to `tests/bats/spec_review.bats`:

```bash
# ---------------------------------------------------------------------------
# SPEC_REVIEW_MODEL seam
# ---------------------------------------------------------------------------

@test "resolve_review_model honors explicit SPEC_REVIEW_MODEL" {
    source "$SCRIPT"
    SPEC_REVIEW_MODEL="My Model X"
    run resolve_review_model
    assert_success
    assert_output "My Model X"
}

@test "resolve_review_model reads model_tiers.antigravity.advanced for agy" {
    cat > "$SANDBOX/pa.yml" <<'EOF'
model_tiers:
  antigravity:
    advanced: "Claude Opus 4.6 (Thinking)"
EOF
    source "$SCRIPT"
    SPEC_REVIEW_MODEL=""
    SPEC_REVIEW_CLI="agy"
    SPEC_REVIEW_CONFIG="$SANDBOX/pa.yml"
    run resolve_review_model
    assert_success
    assert_output "Claude Opus 4.6 (Thinking)"
}

@test "resolve_review_model is empty for non-agy CLI without explicit model" {
    cat > "$SANDBOX/pa.yml" <<'EOF'
model_tiers:
  antigravity:
    advanced: "Claude Opus 4.6 (Thinking)"
EOF
    source "$SCRIPT"
    SPEC_REVIEW_MODEL=""
    SPEC_REVIEW_CLI="gemini"
    SPEC_REVIEW_CONFIG="$SANDBOX/pa.yml"
    run resolve_review_model
    assert_success
    assert_output ""
}

@test "resolve_review_model fails open when config is missing" {
    source "$SCRIPT"
    SPEC_REVIEW_MODEL=""
    SPEC_REVIEW_CLI="agy"
    SPEC_REVIEW_CONFIG="$SANDBOX/does-not-exist.yml"
    run resolve_review_model
    assert_success
    assert_output ""
}

@test "run_reviewer passes --model when a model resolves" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakecli" <<'EOF'
#!/usr/bin/env bash
echo "ARGS:$*"
EOF
    chmod +x "$SANDBOX/bin/fakecli"
    source "$SCRIPT"
    SPEC_REVIEW_CLI="$SANDBOX/bin/fakecli"
    SPEC_REVIEW_MODEL="Tier-X"
    run run_reviewer "prompt body"
    assert_success
    assert_output --partial "--model Tier-X"
}

@test "run_reviewer omits --model when nothing resolves" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakecli" <<'EOF'
#!/usr/bin/env bash
echo "ARGS:$*"
EOF
    chmod +x "$SANDBOX/bin/fakecli"
    source "$SCRIPT"
    SPEC_REVIEW_CLI="$SANDBOX/bin/fakecli"
    SPEC_REVIEW_MODEL=""
    SPEC_REVIEW_CONFIG="$SANDBOX/does-not-exist.yml"
    run run_reviewer "prompt body"
    assert_success
    refute_output --partial "--model"
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats tests/bats/spec_review.bats`
Expected: new tests FAIL (`resolve_review_model: command not found`); existing tests PASS.

- [ ] **Step 3: Implement the seam**

In `configs/claude/scripts/spec_review.sh`, after line 11 (`SPEC_REVIEW_CLI=...`) add:

```bash
SPEC_REVIEW_MODEL="${SPEC_REVIEW_MODEL:-}"
SPEC_REVIEW_CONFIG="${SPEC_REVIEW_CONFIG:-$HOME/.claude/config/parallel_agent.yml}"
```

Add before `run_reviewer` (around line 103):

```bash
# resolve_review_model -> model name on stdout, or empty. Precedence:
# explicit SPEC_REVIEW_MODEL env always wins; otherwise, only for the default
# agy reviewer, fall back to model_tiers.antigravity.advanced from the shared
# parallel_agent.yml registry (a non-agy CLI would reject agy model names).
# Fail-open: any read/parse problem yields empty (reviewer uses its default).
resolve_review_model() {
    if [[ -n "$SPEC_REVIEW_MODEL" ]]; then
        printf '%s' "$SPEC_REVIEW_MODEL"
        return 0
    fi
    [[ "$SPEC_REVIEW_CLI" == "agy" ]] || return 0
    [[ -f "$SPEC_REVIEW_CONFIG" ]] || return 0
    python3 - "$SPEC_REVIEW_CONFIG" 2>/dev/null <<'PY' || true
import sys

import yaml

try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f) or {}
    model = (cfg.get("model_tiers") or {}).get("antigravity", {}).get("advanced", "")
    if model:
        print(model, end="")
except Exception:
    pass
PY
}
```

Replace `run_reviewer` (lines 105-108):

```bash
# run_reviewer PROMPT -> raw reviewer output. stdin carries the prompt body; the -p
# instruction is short. Model comes from resolve_review_model (may be empty).
# Errors propagate (caller decides fail-open vs surface).
run_reviewer() {
    local prompt="$1" model
    model="$(resolve_review_model)"
    local cli_args=()
    [[ -n "$model" ]] && cli_args+=(--model "$model")
    cli_args+=(-p "Cross-reference the artifacts above per the instructions; output only the specified blocks or NO_ISSUES.")
    printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" "${cli_args[@]}"
}
```

(Bash 3.2 note, matching this script's existing constraints: `cli_args+=()` on an array declared empty is safe here because the `-p` element is always appended before expansion — `"${cli_args[@]}"` never expands an empty array under `set -u`.)

- [ ] **Step 4: Run tests**

Run: `bats tests/bats/spec_review.bats && shellcheck configs/claude/scripts/spec_review.sh`
Expected: all PASS, shellcheck clean

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): govern reviewer model from shared model_tiers registry"
```

---

### Task 7: `model_check.sh` staleness checker + `check_status.sh` wiring

**Files:**
- Create: `configs/claude/scripts/model_check.sh`
- Modify: `configs/claude/scripts/check_status.sh`
- Test: `tests/bats/model_check.bats`

- [ ] **Step 1: Write the failing bats tests**

Create `tests/bats/model_check.bats`:

```bash
#!/usr/bin/env bats
# Tests for configs/claude/scripts/model_check.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/model_check.sh"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/model_check.XXXXXX")
    cat > "$SANDBOX/pa.yml" <<'EOF'
model_tiers:
  antigravity:
    flash: "Gemini 3.5 Flash (High)"
    advanced: "Claude Opus 4.6 (Thinking)"
  codex:
    mini: "o4-mini"
EOF
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "model_check.sh exits 0 even with no providers available" {
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml" PATH="/usr/bin:/bin" run bash "$SCRIPT"
    assert_success
}

@test "list_tiers emits tier/model pairs from config" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run list_tiers antigravity
    assert_success
    assert_output --partial "flash	Gemini 3.5 Flash (High)"
    assert_output --partial "advanced	Claude Opus 4.6 (Thinking)"
}

@test "check_cli_provider reports OK for models present in listing" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<'EOF'
#!/usr/bin/env bash
printf 'Gemini 3.5 Flash (High)\nClaude Opus 4.6 (Thinking)\n'
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy"
    assert_success
    assert_output --partial "OK: model_tiers.antigravity.flash"
    assert_output --partial "OK: model_tiers.antigravity.advanced"
}

@test "check_cli_provider reports STALE for models missing from listing" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<'EOF'
#!/usr/bin/env bash
printf 'Gemini 9 Ultra\n'
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy"
    assert_success
    assert_output --partial "STALE: model_tiers.antigravity.flash = Gemini 3.5 Flash (High) not in provider listing"
}

@test "check_cli_provider skips when binary is missing" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/nope" "$SANDBOX/bin/nope"
    assert_success
    assert_output --partial "SKIPPED: antigravity"
}

@test "check_api_provider skips without credentials" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    ANTHROPIC_API_KEY="" run check_api_provider claude
    assert_success
    assert_output --partial "SKIPPED: claude (no credentials)"
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats tests/bats/model_check.bats`
Expected: FAIL (script does not exist)

- [ ] **Step 3: Create `model_check.sh`**

Create `configs/claude/scripts/model_check.sh` (then `chmod +x` it):

```bash
#!/usr/bin/env bash
# model_check.sh — warn-only staleness check of model_tiers pins against live
# provider listings. Never blocks: every failure degrades to SKIPPED and the
# exit code is always 0. Invoked by check_status.sh and /health-check.
#
# Report lines: OK / STALE / SKIPPED / UNSUPPORTED
# Usage: model_check.sh   (env: MODEL_CHECK_CONFIG overrides the config path)
set -uo pipefail

MODEL_CHECK_CONFIG="${MODEL_CHECK_CONFIG:-$HOME/.claude/config/parallel_agent.yml}"

# list_tiers PROVIDER -> "tier<TAB>model" lines from model_tiers.<provider>
list_tiers() {
    local provider="$1"
    [[ -f "$MODEL_CHECK_CONFIG" ]] || return 0
    python3 - "$MODEL_CHECK_CONFIG" "$provider" 2>/dev/null <<'PY' || true
import sys

import yaml

try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f) or {}
    tiers = (cfg.get("model_tiers") or {}).get(sys.argv[2]) or {}
    for tier, model in tiers.items():
        print(f"{tier}\t{model}")
except Exception:
    pass
PY
}

# check_cli_provider PROVIDER BINARY LIST_CMD... -> report lines
check_cli_provider() {
    local provider="$1" binary="$2"
    shift 2
    if ! command -v "$binary" >/dev/null 2>&1; then
        echo "SKIPPED: $provider ($binary not installed)"
        return 0
    fi
    local listing
    if ! listing="$("$@" 2>/dev/null)"; then
        echo "SKIPPED: $provider (model listing failed)"
        return 0
    fi
    local tier model
    while IFS=$'\t' read -r tier model; do
        [[ -z "${model:-}" ]] && continue
        if grep -qiF "$model" <<<"$listing"; then
            echo "OK: model_tiers.$provider.$tier = $model"
        else
            echo "STALE: model_tiers.$provider.$tier = $model not in provider listing"
        fi
    done < <(list_tiers "$provider")
}

# check_api_provider PROVIDER -> report lines (claude|gemini), creds-gated
check_api_provider() {
    local provider="$1" listing=""
    case "$provider" in
        claude)
            if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
                echo "SKIPPED: claude (no credentials)"
                return 0
            fi
            listing="$(curl -sf --max-time 10 https://api.anthropic.com/v1/models \
                -H "x-api-key: $ANTHROPIC_API_KEY" \
                -H "anthropic-version: 2023-06-01" 2>/dev/null)" || {
                echo "SKIPPED: claude (models endpoint unreachable)"
                return 0
            }
            ;;
        gemini)
            if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
                echo "SKIPPED: gemini (no credentials)"
                return 0
            fi
            listing="$(curl -sf --max-time 10 \
                "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" 2>/dev/null)" || {
                echo "SKIPPED: gemini (models endpoint unreachable)"
                return 0
            }
            ;;
        *)
            echo "UNSUPPORTED: $provider (no listing source)"
            return 0
            ;;
    esac
    local tier model
    while IFS=$'\t' read -r tier model; do
        [[ -z "${model:-}" ]] && continue
        if grep -qiF "$model" <<<"$listing"; then
            echo "OK: model_tiers.$provider.$tier = $model"
        else
            echo "STALE: model_tiers.$provider.$tier = $model not in provider listing"
        fi
    done < <(list_tiers "$provider")
}

main() {
    check_api_provider claude
    check_api_provider gemini
    check_cli_provider antigravity agy agy models
    # Cursor and Codex CLIs expose no model-listing command (verified at
    # implementation; revisit when they grow one).
    echo "UNSUPPORTED: cursor (no listing command)"
    echo "UNSUPPORTED: codex (no listing command)"
    exit 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

Run: `chmod +x configs/claude/scripts/model_check.sh`

**Implementation-time check:** if Step 1 of Task 5 found a working `cursor`/`codex` listing command, swap the matching `UNSUPPORTED` line for a `check_cli_provider` call here and update the bats expectations accordingly.

- [ ] **Step 4: Run tests**

Run: `bats tests/bats/model_check.bats && shellcheck configs/claude/scripts/model_check.sh`
Expected: PASS, shellcheck clean

- [ ] **Step 5: Wire into `check_status.sh` + add antigravity rows**

In `configs/claude/scripts/check_status.sh`:

a) Services parsing — after the `codex_enabled=` line (line 49) add:

```bash
    antigravity_enabled=$(grep -A1 "^  antigravity:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
```

b) Count — after the codex count line (line 55):

```bash
    [[ "$antigravity_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
```

and change the header `Enabled Services (${enabled_count}/4):` → `(${enabled_count}/5):`

c) After the Codex enabled/disabled block (line 82) add:

```bash
    if [[ "$antigravity_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Antigravity"
    else
        echo -e "  ${RED}✗${NC} Antigravity (disabled)"
    fi
```

d) CLI tools — after the codex block (line 152) add:

```bash
antigravity_installed=false
if command -v agy &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Antigravity CLI (agy) installed"
    antigravity_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which agy)"
    fi
else
    echo -e "  ${YELLOW}○${NC} Antigravity CLI (agy) not installed (optional)"
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    ${BLUE}→${NC} Install: agy install  (https://antigravity.google)"
    fi
fi
```

e) Overall status — after the codex `working_agents` line (line 244):

```bash
[[ "$antigravity_installed" == true && "$antigravity_enabled" == "true" ]] && working_agents=$((working_agents + 1))
```

f) Model staleness section — before the `# Overall status` block (line 236):

```bash
# Model staleness (warn-only; full detail via model_check.sh directly)
echo -e "${BOLD}Model Pins:${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$SCRIPT_DIR/model_check.sh" ]]; then
    while IFS= read -r line; do
        case "$line" in
            OK:*)          [[ "$VERBOSE" == true ]] && echo -e "  ${GREEN}✓${NC} ${line#OK: }" ;;
            STALE:*)       echo -e "  ${YELLOW}⚠${NC}  ${line#STALE: }" ;;
            SKIPPED:*)     [[ "$VERBOSE" == true ]] && echo -e "  ${YELLOW}○${NC} ${line#SKIPPED: }" ;;
            UNSUPPORTED:*) [[ "$VERBOSE" == true ]] && echo -e "  ${YELLOW}○${NC} ${line#UNSUPPORTED: }" ;;
        esac
    done < <("$SCRIPT_DIR/model_check.sh")
    echo -e "  ${GREEN}✓${NC} Model pin check complete (stale pins above, if any)"
else
    echo -e "  ${YELLOW}○${NC} model_check.sh not found — skipping"
fi
echo ""
```

- [ ] **Step 6: Verify manually**

Run: `bash configs/claude/scripts/check_status.sh --verbose`
Expected: Antigravity rows in Services/CLI/Overall; a `Model Pins:` section; exit 0.

Run: `shellcheck configs/claude/scripts/check_status.sh`
Expected: no new warnings beyond pre-existing ones.

- [ ] **Step 7: Commit**

```bash
git add configs/claude/scripts/model_check.sh configs/claude/scripts/check_status.sh tests/bats/model_check.bats
git commit -m "feat(health): warn-only model staleness check + antigravity status rows"
```

---

### Task 8: Bootstrap agy detection

**Files:**
- Modify: `bootstrap/lib/deploy.sh` (install summary, near line 572)

- [ ] **Step 1: Extend the antigravity summary block**

`bootstrap/lib/deploy.sh:572-580` currently reports the Antigravity app. Extend it to also report the agy CLI. Inside the `if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then` block, after the existing app-found reporting, add:

```bash
        if command -v agy >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} antigravity CLI (agy) installed"
        else
            echo -e "  ${YELLOW}○${NC} antigravity CLI (agy) not found — parallel-agent participation needs it"
            echo -e "    ${BLUE}→${NC} Install via the Antigravity IDE, then run: agy install"
        fi
```

(Match the exact color-variable names used in that function — `GREEN`/`YELLOW`/`BLUE`/`NC` per `bootstrap/lib/common.sh`.)

- [ ] **Step 2: Run the bats suite for bootstrap + lint**

Run: `bats tests/bats/bootstrap_services.bats tests/bats/deploy_antigravity.bats && shellcheck bootstrap/lib/deploy.sh`
Expected: PASS / clean

- [ ] **Step 3: Commit**

```bash
git add bootstrap/lib/deploy.sh
git commit -m "feat(bootstrap): report agy CLI availability in antigravity summary"
```

---

### Task 9: Documentation sweep

**Files:**
- Modify: `configs/claude/CLAUDE.md` (orchestration guide — "(Gemini, Cursor, Claude CLI)" intro, example commands)
- Modify: `configs/claude/references/parallel-agent.md` (flag table, model tiers)
- Modify: `CLAUDE.md` + `README.md` + `AGENTS.md` (agent lists "Cursor, Gemini CLI, Claude CLI" → include Codex + Antigravity; 4 → 5 agents)
- Modify: `docs/CONFIGURATION.md` (model tier reference)

- [ ] **Step 1: Find every stale reference**

```bash
grep -rn "claude-opus-4-6\|claude-sonnet-4-5\|gemini-3-flash-preview\|gemini-3-pro-preview\|o4-mini\|gpt-5.1" \
  --include="*.md" . | grep -v ".git/" | grep -v "docs/superpowers/"
grep -rln "Gemini, Cursor, Claude CLI" --include="*.md" .
```

- [ ] **Step 2: Update each hit**

For every file found:
- Replace old model IDs with the Task 5 verified pins.
- Agent enumerations become "(Gemini, Cursor, Claude CLI, Codex, Antigravity)".
- In `configs/claude/references/parallel-agent.md`: add `--antigravity-model`, `--antigravity-only`, `--no-antigravity` to the flag table; add the antigravity tier rows (mini/flash/advanced with the pinned agy catalog names); add a short "Known correlation" note: *antigravity serves Gemini/Claude model families also present via direct API; consensus scores can be inflated by same-family agreement, and agy's catalog may lag the direct API (e.g. Opus 4.6 vs 4.8) — `agy models` is its ground truth.*
- In `configs/claude/CLAUDE.md` quick-usage examples, add one antigravity example:

```bash
# Antigravity-only quick query
~/.claude/scripts/parallel_agent.py --antigravity-only --antigravity-model flash "Quick question"
```

- In `docs/CONFIGURATION.md`, document the new `cli_agents:` block (copy the YAML block from Task 1 with one sentence: "adding a CLI provider is configuration-only — define its command shape here plus `model_tiers`/`rate_limits`/`credit_fallback` entries").

- [ ] **Step 3: Verify no stale IDs remain**

Run the Step 1 greps again.
Expected: no hits outside `docs/superpowers/` (specs/plans are historical records) and `CHANGELOG`-style files.

- [ ] **Step 4: Commit**

```bash
git add -A -- '*.md'
git commit -m "docs: 5-agent orchestration, antigravity flags, refreshed model pins"
```

---

### Task 10: Full verification

- [ ] **Step 1: Full test suites**

```bash
python3 -m pytest tests/python/ -v
bats tests/bats/
```

Expected: all PASS

- [ ] **Step 2: Lint everything touched**

```bash
shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh
yamllint configs/claude/config/*.yml
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/parallel_agent.yml'))"
```

Expected: clean (no new warnings vs `main`)

- [ ] **Step 3: End-to-end smoke (best-effort, requires CLIs/keys)**

```bash
configs/claude/scripts/parallel_agent.py --json --no-stream --timeout 120 "What is 2+2? Answer with one digit."
configs/claude/scripts/check_status.sh
```

Expected: JSON result with up to 5 agent entries (missing CLIs report `status: missing`, run still completes); status report shows 5 services.

- [ ] **Step 4: Independent spec/plan cross-reference**

```bash
~/.claude/scripts/spec_review.sh \
  --spec docs/superpowers/specs/2026-06-11-cli-agent-refactor-design.md \
  --plan docs/superpowers/plans/2026-06-11-cli-agent-refactor.md
```

Expected: `✓ No inconsistencies found` (or address findings)

- [ ] **Step 5: Final commit if anything changed**

```bash
git status --short
# commit any remaining fixes with message: "chore: final verification fixes for CLI agent refactor"
```
