# Synthesis CLI Auth Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make low-consensus synthesis work for OAuth-only Claude Code users by invoking `claude -p` (with SDK fallback when configured), using the same backend resolution as the primary claude agent.

**Architecture:** Move shared `select_backend()` to `agents/config.py`. Add `synthesis.backend` config (`auto`|`cli`|`sdk`, default `auto`). Refactor `SynthesisEngine.synthesize()` to resolve backend via `_resolve_synthesis_backend()`, short-circuit when neither CLI nor API key exists, then call `_invoke_claude_cli()` or the existing SDK path. CLI invoke mirrors `CLIAgent` subprocess conventions including timeout kill and `output` strategy support.

**Tech Stack:** Python 3 (asyncio, pytest), YAML.

**Spec:** `docs/superpowers/specs/2026-07-13-synthesis-cli-auth-design.md`

**Working directory:** repo root. Paths below are repo-relative.

**Test command used throughout:**

```bash
python3 -m pytest tests/python/agents/test_synthesis.py tests/python/agents/test_cli.py tests/python/agents/test_config.py -v
```

## Global Constraints

- Synthesis failures must never crash orchestration — return `triggered: true` error envelopes.
- `stdin=DEVNULL` on CLI subprocess (issue #306).
- On timeout/cancel: `proc.kill()` + `await proc.wait()` before returning (issue #306).
- `auto` backend uses same `select_backend()` precedence as primary claude agent, except short-circuit when neither CLI nor key exists (no doomed SDK call).
- Do not import `CLIAgent` from synthesis — inline subprocess only.
- Keep existing JSON fence stripping and error shapes in `synthesize()`.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `configs/claude/scripts/agents/config.py` | Modify | Host `select_backend()`; add `synthesis` defaults incl. `backend: auto` |
| `configs/claude/scripts/agents/cli.py` | Modify | Import `select_backend` from config; remove local definition |
| `configs/claude/scripts/agents/synthesis.py` | Modify | Backend resolution, CLI invoke, refactored `synthesize()` |
| `configs/claude/config/parallel_agent.yml` | Modify | Add `synthesis.backend: auto` |
| `tests/python/agents/test_cli.py` | Modify | Import `select_backend` from `agents.config` |
| `tests/python/agents/test_synthesis.py` | Modify | CLI path, backend resolution, timeout kill tests |
| `tests/python/agents/test_config.py` | Modify | `synthesis` defaults + YAML sync test |
| `docs/TROUBLESHOOTING.md` | Modify | Synthesis auth subsection |
| `docs/CONFIGURATION.md` | Modify | Document `synthesis.backend` |
| `docs/ARCHITECTURE_DIAGRAMS.md` | Modify | Synthesis auth note |
| `configs/claude/references/parallel-agent.md` | Modify | Synthesis auth paragraph |

---

### Task 1: Relocate `select_backend()` to `agents/config.py`

**Files:**
- Modify: `configs/claude/scripts/agents/config.py`
- Modify: `configs/claude/scripts/agents/cli.py`
- Modify: `tests/python/agents/test_cli.py`

**Interfaces:**
- Produces: `agents.config.select_backend(has_sdk: bool, has_key: bool, has_cli: bool) -> str | None`

- [ ] **Step 1: Add function to `config.py`**

Insert after the `Config` class (before `ServiceConfig`), copying verbatim from `cli.py`:

```python
def select_backend(has_sdk: bool, has_key: bool, has_cli: bool) -> str | None:
    """Pick SDK vs CLI for claude/gemini providers.

    SDK when package + API key present; else CLI when binary on PATH; else SDK
    as last resort; None when nothing available.
    """
    if has_sdk and has_key:
        return "sdk"
    if has_cli:
        return "cli"
    if has_sdk:
        return "sdk"
    return None
```

Update the comment in `_default_config()` at `cli_agents.claude` from
`agents.cli.select_backend` → `agents.config.select_backend`.

- [ ] **Step 2: Update `cli.py`**

Remove the local `select_backend` function. Add to imports from `agents.config`:

```python
from agents.config import (
    HAS_ANTHROPIC,
    HAS_GENAI,
    HAS_GENAI_NEW,
    Config,
    Logger,
    RateLimiter,
    genai,
    select_backend,
)
```

- [ ] **Step 3: Update test import**

In `tests/python/agents/test_cli.py`, change:

```python
from agents.cli import select_backend
```

to:

```python
from agents.config import select_backend
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/python/agents/test_cli.py::TestSelectBackend -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/agents/config.py configs/claude/scripts/agents/cli.py tests/python/agents/test_cli.py
git commit -m "refactor(agents): move select_backend to config module"
```

---

### Task 2: Add `synthesis.backend` configuration

**Files:**
- Modify: `configs/claude/config/parallel_agent.yml`
- Modify: `configs/claude/scripts/agents/config.py`
- Test: `tests/python/agents/test_config.py`

**Interfaces:**
- Produces: `config.get("synthesis.backend", "auto")` returns `"auto"` from defaults and repo YAML

- [ ] **Step 1: Write failing sync test**

Append to `tests/python/agents/test_config.py`:

```python
class TestSynthesisConfig:
    def test_default_config_has_synthesis_backend(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert config.get("synthesis.backend") == "auto"
        assert config.get("synthesis.enabled") is True
        assert config.get("synthesis.threshold") == 0.50

    def test_synthesis_defaults_match_repo_yaml(self, tmp_path):
        with open(REPO_YAML) as f:
            repo = yaml.safe_load(f)
        defaults = Config(config_path=str(tmp_path / "none.yml")).config
        assert repo["synthesis"] == defaults["synthesis"]
```

(Ensure `REPO_YAML` and `import yaml` exist at file top — copy from existing sync tests.)

- [ ] **Step 2: Run test to verify failure**

Run: `python3 -m pytest tests/python/agents/test_config.py::TestSynthesisConfig -v`
Expected: FAIL (`synthesis` missing from defaults / YAML mismatch)

- [ ] **Step 3: Add to `parallel_agent.yml`**

Under existing `synthesis:` block, add:

```yaml
  backend: auto   # auto | cli | sdk
```

- [ ] **Step 4: Add to `_default_config()` in `config.py`**

Insert before `"validation":` in the returned dict:

```python
            "synthesis": {
                "enabled": True,
                "threshold": 0.50,
                "model": "sonnet",
                "timeout": 300,
                "backend": "auto",
            },
```

- [ ] **Step 5: Run test to verify pass**

Run: `python3 -m pytest tests/python/agents/test_config.py::TestSynthesisConfig -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add configs/claude/config/parallel_agent.yml configs/claude/scripts/agents/config.py tests/python/agents/test_config.py
git commit -m "feat(config): add synthesis.backend setting"
```

---

### Task 3: Backend resolution helper + auth short-circuit

**Files:**
- Modify: `configs/claude/scripts/agents/synthesis.py`
- Test: `tests/python/agents/test_synthesis.py`

**Interfaces:**
- Produces: `SynthesisEngine._resolve_synthesis_backend(self) -> str | None`
- Consumes: `select_backend` from `agents.config`, `shutil.which`, `os.environ.get("ANTHROPIC_API_KEY")`

- [ ] **Step 1: Write failing tests**

Append to `tests/python/agents/test_synthesis.py`:

```python
class TestSynthesisBackendResolution:
    def test_auto_prefers_cli_without_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(
            "agents.synthesis.shutil.which", lambda _: "/usr/bin/claude"
        )
        engine = _make_engine(tmp_path)
        assert engine._resolve_synthesis_backend() == "cli"

    def test_auto_prefers_sdk_with_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(
            "agents.synthesis.shutil.which", lambda _: "/usr/bin/claude"
        )
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = True
        try:
            engine = _make_engine(tmp_path)
            assert engine._resolve_synthesis_backend() == "sdk"
        finally:
            synth_module.HAS_ANTHROPIC = original

    def test_auto_neither_cli_nor_key_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: None)
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = True
        try:
            engine = _make_engine(tmp_path)
            assert engine._resolve_synthesis_backend() is None
        finally:
            synth_module.HAS_ANTHROPIC = original

    def test_backend_cli_forces_cli_even_with_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(
            "agents.synthesis.shutil.which", lambda _: "/usr/bin/claude"
        )
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "cli"
        assert engine._resolve_synthesis_backend() == "cli"

    def test_backend_sdk_forces_sdk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agents.synthesis.shutil.which", lambda _: "/usr/bin/claude"
        )
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = True
        try:
            engine = _make_engine(tmp_path)
            engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
            assert engine._resolve_synthesis_backend() == "sdk"
        finally:
            synth_module.HAS_ANTHROPIC = original

    def test_invalid_backend_falls_back_to_auto(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(
            "agents.synthesis.shutil.which", lambda _: "/usr/bin/claude"
        )
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "bogus"
        assert engine._resolve_synthesis_backend() == "cli"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/python/agents/test_synthesis.py::TestSynthesisBackendResolution -v`
Expected: FAIL (`AttributeError: _resolve_synthesis_backend`)

- [ ] **Step 3: Implement helper in `synthesis.py`**

Add imports at top:

```python
import contextlib
import shutil
import tempfile
```

Add to imports from config:

```python
from agents.config import HAS_ANTHROPIC, Config, Logger, select_backend
```

Add method on `SynthesisEngine`:

```python
def _resolve_synthesis_backend(self) -> str | None:
    raw = self.config.get("synthesis.backend", "auto")
    if raw not in ("auto", "cli", "sdk"):
        if self.logger:
            self.logger.warning(f"invalid synthesis.backend={raw!r}, using auto")
        raw = "auto"

    has_cli = bool(shutil.which("claude"))
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if raw == "cli":
        return "cli" if has_cli else None
    if raw == "sdk":
        return "sdk" if HAS_ANTHROPIC else None
    # auto
    if not has_key and not has_cli:
        return None
    return select_backend(has_sdk=HAS_ANTHROPIC, has_key=has_key, has_cli=has_cli)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/python/agents/test_synthesis.py::TestSynthesisBackendResolution -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/agents/synthesis.py tests/python/agents/test_synthesis.py
git commit -m "feat(synthesis): add backend resolution helper"
```

---

### Task 4: CLI invoke path + wire into `synthesize()`

**Files:**
- Modify: `configs/claude/scripts/agents/synthesis.py`
- Test: `tests/python/agents/test_synthesis.py`

**Interfaces:**
- Produces: `SynthesisEngine._invoke_claude_cli(self, prompt: str) -> str`
  Raises `TimeoutError`, `RuntimeError` on CLI failure
- Modifies: `synthesize()` to call resolution → CLI or SDK

- [ ] **Step 1: Write failing CLI tests**

Append to `test_synthesis.py`:

```python
class TestSynthesisCliInvoke:
    def _engine_with_template(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "Task: {ORIGINAL_TASK}"
        return engine

    def test_cli_success_parses_json(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        async def fake_exec(*cmd, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(
                return_value=(b'{"unified_recommendation": "merged"}', b"")
            )
            proc.returncode = 0
            proc.kill = MagicMock()
            proc.wait = AsyncMock()
            return proc

        monkeypatch.setattr(synth_module.asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: "/usr/bin/claude")

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["unified_recommendation"] == "merged"
        assert result["triggered"] is True

    def test_cli_nonzero_exit_returns_error(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        async def fake_exec(*cmd, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b"not logged in"))
            proc.returncode = 1
            proc.kill = MagicMock()
            proc.wait = AsyncMock()
            return proc

        monkeypatch.setattr(synth_module.asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: "/usr/bin/claude")

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["triggered"] is True
        assert "not logged in" in result["error"]

    def test_auto_neither_auth_returns_combined_error(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        client_factory = MagicMock()
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setattr(
            synth_module, "AsyncAnthropic", client_factory, raising=False
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: None)

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["triggered"] is True
        assert "ANTHROPIC_API_KEY" in result["error"]
        assert "claude" in result["error"].lower()
        client_factory.assert_not_called()

    def test_cli_timeout_kills_child(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        async def fake_exec(*cmd, **kwargs):
            return proc

        monkeypatch.setattr(synth_module.asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: "/usr/bin/claude")
        engine = self._engine_with_template(tmp_path)
        engine.config.config.setdefault("synthesis", {})["timeout"] = 1

        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        proc.kill.assert_called_once()
        proc.wait.assert_called_once()
        assert result["error"] == "timeout"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/python/agents/test_synthesis.py::TestSynthesisCliInvoke -v`
Expected: FAIL

- [ ] **Step 3: Implement `_invoke_claude_cli` and refactor `synthesize()`**

Add helper methods on `SynthesisEngine` (argv building can mirror `CLIAgent._build_command` logic inline — read `runners.py:473-512` for reference):

```python
def _build_claude_cli_command(self, prompt: str, output_file: str | None) -> list[str]:
    spec = self.config.get("cli_agents.claude") or {}
    binary = spec.get("binary", "claude")
    model_tier = self.config.get("synthesis.model", "sonnet")
    model_name = self.config.get(f"model_tiers.claude.{model_tier}", model_tier)

    def subst(arg: str) -> str:
        return arg.replace("{output_file}", output_file or "").replace(
            "{model}", model_name
        )

    def subst_prompt(arg: str) -> str:
        if "{prompt}" in arg:
            return prompt.join(subst(piece) for piece in arg.split("{prompt}"))
        return subst(arg)

    cmd = [binary]
    for arg in spec.get("base_args", []):
        s = subst(arg)
        if s:
            cmd.append(s)
    if model_name:
        cmd += [a for a in (subst(a) for a in spec.get("model_args", [])) if a]
    for arg in spec.get("prompt_args", ["-p", "{prompt}"]):
        s = subst_prompt(arg)
        if s or "{prompt}" in arg:
            cmd.append(s)
    return cmd


async def _invoke_claude_cli(self, prompt: str) -> str:
    spec = self.config.get("cli_agents.claude") or {}
    output_strategy = spec.get("output", "stdout")
    output_file = None
    if output_strategy == "file_then_stdout":
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="synthesis_out_"
        ) as tmp:
            output_file = tmp.name

    cmd = self._build_claude_cli_command(prompt, output_file)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(err or f"claude exited {proc.returncode}")
        text = ""
        if (
            output_strategy == "file_then_stdout"
            and output_file
            and os.path.exists(output_file)
        ):
            with open(output_file) as f:
                text = f.read().strip()
        if not text:
            text = stdout.decode("utf-8", errors="ignore").strip()
        return text
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    finally:
        if output_file:
            with contextlib.suppress(OSError):
                os.unlink(output_file)
```

Refactor the invoke section of `synthesize()` (replace the block starting at `# Execute synthesis using Claude`):

```python
        backend = self._resolve_synthesis_backend()
        if backend is None:
            if self.logger:
                self.logger.warning("Synthesis unavailable: no claude CLI and no ANTHROPIC_API_KEY")
            return {
                "triggered": True,
                "error": (
                    "Synthesis requires claude CLI (run `claude /login`) or "
                    "ANTHROPIC_API_KEY (set synthesis.backend: sdk)"
                ),
                "unified_recommendation": "Synthesis failed",
            }

        if self.logger:
            self.logger.info(f"Synthesis using claude backend: {backend}")

        timeout = self.config.get("synthesis.timeout", 300)

        try:
            if backend == "cli":
                synthesis_text = await asyncio.wait_for(
                    self._invoke_claude_cli(prompt), timeout=timeout
                )
            else:
                if not HAS_ANTHROPIC:
                    if self.logger:
                        self.logger.warning("Anthropic SDK not available, cannot synthesize")
                    return None
                client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                model = self.config.get("synthesis.model", "sonnet")
                model_name = self.config.get(
                    f"model_tiers.claude.{model}", "claude-sonnet-4-6"
                )
                response = await asyncio.wait_for(
                    client.messages.create(
                        model=model_name,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                    timeout=timeout,
                )
                synthesis_text = response.content[0].text

            # ... existing JSON parse block unchanged ...
```

Wrap CLI path timeout to kill child: inside `_invoke_claude_cli`, the outer `asyncio.wait_for` in `synthesize()` will cancel `communicate()` — ensure the `CancelledError` handler in `_invoke_claude_cli` runs (as shown above). For `TimeoutError` from `wait_for`, the existing except block handles it.

Update module docstring to reflect new dependencies.

- [ ] **Step 4: Run full synthesis test suite**

Run: `python3 -m pytest tests/python/agents/test_synthesis.py -v`
Expected: PASS (all tests including existing SDK mocks)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/agents/synthesis.py tests/python/agents/test_synthesis.py
git commit -m "feat(synthesis): invoke claude CLI for OAuth auth"
```

---

### Task 5: Documentation

**Files:**
- Modify: `docs/TROUBLESHOOTING.md`
- Modify: `docs/CONFIGURATION.md`
- Modify: `docs/ARCHITECTURE_DIAGRAMS.md`
- Modify: `configs/claude/references/parallel-agent.md`

- [ ] **Step 1: Add TROUBLESHOOTING subsection**

Under the parallel agent / OAuth section, add **Synthesis fails with API key error**:

- Symptom: `Could not resolve authentication method` during synthesis
- Cause: synthesis previously required SDK; fixed in this change — ensure `claude` CLI is on PATH and logged in, or set `synthesis.backend: sdk` + `ANTHROPIC_API_KEY`

- [ ] **Step 2: Document `synthesis.backend` in CONFIGURATION.md**

In the synthesis config table, add row for `backend` with values `auto|cli|sdk`.

- [ ] **Step 3: Update ARCHITECTURE_DIAGRAMS.md**

Add note under SynthesisEngine bullet: uses same backend resolution as primary claude when `auto`.

- [ ] **Step 4: Update parallel-agent.md reference**

One paragraph on synthesis auth backends.

- [ ] **Step 5: Commit**

```bash
git add docs/TROUBLESHOOTING.md docs/CONFIGURATION.md docs/ARCHITECTURE_DIAGRAMS.md configs/claude/references/parallel-agent.md
git commit -m "docs: document synthesis CLI auth alignment"
```

---

## Plan self-review

| Spec requirement | Task |
|------------------|------|
| `synthesis.backend` config | Task 2 |
| Move `select_backend` to config | Task 1 |
| `_resolve_synthesis_backend` short-circuit | Task 3 |
| CLI subprocess with DEVNULL, kill on timeout | Task 4 |
| `output` strategy support | Task 4 (`file_then_stdout`) |
| `import shutil` | Task 3 |
| SDK path retained | Task 4 |
| Tests (all listed cases) | Tasks 3–4 |
| Docs | Task 5 |
| No orchestration crash | Task 4 error envelopes |

No placeholders. Types consistent across tasks.
