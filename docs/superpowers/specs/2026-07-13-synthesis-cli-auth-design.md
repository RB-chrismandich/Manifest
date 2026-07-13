# Synthesis CLI Auth Alignment

**Date**: 2026-07-13
**Status**: Approved (spec-review revisions applied)
**Scope**: Fix `SynthesisEngine` authentication so low-consensus synthesis works
for OAuth-only Claude Code users (CLI login, no `ANTHROPIC_API_KEY`), matching
how the primary claude parallel agent already runs.

---

## Problem

When `parallel_agent.py` consensus falls below the synthesis threshold (default
50%), `SynthesisEngine.synthesize()` in `agents/synthesis.py` calls
`AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))` directly. The
Anthropic SDK requires a billed API key; it does not reuse the Claude Code CLI
OAuth session.

Primary agents do not have this gap. For claude (and gemini), `agents/cli.py`
uses `select_backend()`:

1. SDK when the package is installed **and** the API key env var is set
2. Otherwise CLI when the provider binary is on `PATH` (`claude -p`, etc.)
3. Otherwise SDK as a last resort (ADC/OAuth on SDK — rarely used for Anthropic)

Most Manifest users authenticate via `claude /login` (subscription OAuth) without
exporting `ANTHROPIC_API_KEY`. The primary claude agent runs fine; synthesis
fails with:

```text
Could not resolve authentication method. Expected either api_key or auth_token to be set...
```

This breaks disagreement resolution out of the box despite a working orchestration
run.

---

## Decision summary

| Item | Choice |
|------|--------|
| Approach | **A — inline CLI invoke in `synthesis.py`** with shared `select_backend()` |
| Backend config | `synthesis.backend`: `auto` \| `cli` \| `sdk` |
| Default | `auto` — same resolution as the primary claude agent |
| SDK path | Retained for explicit `sdk` backend or `auto` when CLI unavailable |
| `select_backend()` location | Move from `agents/cli.py` → `agents/config.py` (avoid circular imports) |

Alternatives rejected:

- **Reuse `CLIAgent.execute()`** — pulls in rate limiter, credit-fallback chain,
  and agent lifecycle for a single headless call; heavier than needed.
- **New `ClaudeInvoker` module** — clean DRY but touches hot runner paths for a
  narrow bug; defer unless duplication becomes painful.

---

## Configuration

Add to `parallel_agent.yml` under `synthesis:` (and matching defaults in
`agents/config.py`):

```yaml
synthesis:
  enabled: true
  threshold: 0.50
  model: "sonnet"
  timeout: 300
  backend: auto   # auto | cli | sdk
```

| `backend` | Behavior |
|-----------|----------|
| `auto` (default) | `select_backend(HAS_ANTHROPIC, bool(ANTHROPIC_API_KEY), shutil.which("claude"))` — identical to primary claude agent |
| `cli` | Force `claude -p` via `cli_agents.claude` argv shape; fail with actionable message if binary missing or auth fails |
| `sdk` | Force `AsyncAnthropic`; require `ANTHROPIC_API_KEY` (headless/CI explicit opt-in) |

Invalid values log a warning and fall back to `auto`.

---

## Architecture

### Backend resolution (shared)

Move `select_backend()` from `agents/cli.py` to `agents/config.py`. Update
`cli.py` to import it from config. No behavior change for primary agents.

Add `_resolve_synthesis_backend(config) -> str | None` in `synthesis.py` (or
config) that wraps `select_backend()` for synthesis-specific overrides:

```python
def _resolve_synthesis_backend(config, *, has_sdk, has_key, has_cli) -> str | None:
    raw = config.get("synthesis.backend", "auto")
    if raw not in ("auto", "cli", "sdk"):
        logger.warning(f"invalid synthesis.backend={raw!r}, using auto")
        raw = "auto"
    if raw == "cli":
        return "cli" if has_cli else None
    if raw == "sdk":
        return "sdk" if has_sdk else None
    # auto — same precedence as primary claude agent, BUT short-circuit when
    # neither auth path exists so we never fall through to a doomed SDK call.
    if not has_key and not has_cli:
        return None
    return select_backend(has_sdk=has_sdk, has_key=has_key, has_cli=has_cli)
```

When `_resolve_synthesis_backend` returns `None`, return immediately with
`triggered: true` and an error naming both `claude /login` (or install `claude`
CLI) and `ANTHROPIC_API_KEY` — do **not** invoke `AsyncAnthropic`.

### Synthesis invoke path

After building the synthesis prompt (unchanged), `SynthesisEngine.synthesize()`:

```text
_resolve_synthesis_backend(config)
    │
    ├─ None ──► combined auth error (no invoke)
    │
    ├─ cli ──► _invoke_claude_cli(prompt)
    │           subprocess: cli_agents.claude argv
    │           (claude [--model <tier>] -p <prompt>)
    │
    └─ sdk ──► _invoke_claude_sdk(prompt)  [existing AsyncAnthropic path]
```

**CLI subprocess details** (mirror `CLIAgent._execute_impl` conventions):

- Build argv from `config.get("cli_agents.claude")` — same keys as primary agent
  (`binary`, `base_args`, `model_args`, `prompt_args`)
- Honor the configured `output` strategy from `cli_agents.claude.output`:
  - `stdout` — read process stdout (current claude default)
  - `file_then_stdout` — create a tempfile when `{output_file}` appears in
    `base_args`, read file with priority file > stdout > stderr-on-error, unlink
    in `finally` (same priority as `CLIAgent._collect_output`)
  - Any other value → log warning and treat as `stdout`
- `stdin=DEVNULL` (headless `-p` must not block on inherited stdin; issue #306)
- Capture stdout/stderr; nonzero exit → structured error (do not treat stderr as
  synthesis JSON)
- Model tier from `synthesis.model` → `model_tiers.claude.<tier>`
- Timeout via `asyncio.wait_for` around `proc.communicate()` using
  `synthesis.timeout` (default 300s). On `TimeoutError` or task cancellation,
  **kill the child** (`proc.kill()` + `await proc.wait()`) before returning —
  same leak prevention as `CLIAgent._execute_impl` (issue #306)

**Response parsing** (unchanged): extract JSON from response text, strip
`` ```json `` fences, `json.loads`, set `triggered: true`.

If `_resolve_synthesis_backend` returns `None`, log warning and return
`{"triggered": true, "error": "...", "unified_recommendation": "Synthesis failed"}`
with a message naming both auth paths (`claude /login` or install CLI; or set
`ANTHROPIC_API_KEY` / `synthesis.backend: sdk`).

### Module dependency update

`synthesis.py` module docstring today says "depends on agents.config and stdlib
only." Update to: depends on `agents.config` (+ optional Anthropic SDK,
stdlib `asyncio`, `shutil`, `tempfile`, `contextlib`). Import `select_backend`
from config; import `CLIAgent` is **not** required (inline subprocess keeps
synthesis lightweight). Add `import shutil` for `shutil.which("claude")`.

---

## Data flow

Unchanged until the invoke step:

1. Orchestrator runs N agents → `agent_results`
2. Consensus scorer → `consensus_score`
3. If score < threshold and synthesis enabled → `SynthesisEngine.synthesize()`
4. Template fill (`synthesis.md`) → prompt string
5. **New:** backend resolution → CLI or SDK invoke → raw text
6. JSON parse → attach under `consensus["synthesis"]` in orchestrator output

No changes to CLI flags, JSON schema fields, or consensus scoring.

---

## Error handling

| Condition | Result |
|-----------|--------|
| Consensus ≥ threshold | `None` (skip synthesis) — unchanged |
| Empty template / prompt | `None` — unchanged |
| `backend: cli`, binary missing | `triggered: true`, error cites `claude` not on PATH + install hint |
| `backend: cli`, nonzero exit / auth error | `triggered: true`, error includes stderr (truncated if huge) |
| `backend: sdk`, no key | `triggered: true`, error cites `ANTHROPIC_API_KEY` — unchanged message shape |
| `backend: auto`, neither CLI nor key | Immediate return (no SDK invoke); error mentions `claude /login` and `ANTHROPIC_API_KEY` |
| Timeout | `triggered: true`, `error: "timeout"`; child process killed before return |
| Invalid JSON in model output | `triggered: true`, `error: "json_parse_failed"`, raw text in `unified_recommendation` — unchanged |
| Anthropic SDK not installed, backend resolves to sdk | Warning + graceful failure (same as today when `HAS_ANTHROPIC` is false) |

Synthesis failures must never crash orchestration — existing contract preserved.

Logging: on invoke, log chosen backend at INFO
(`Synthesis using claude backend: cli|sdk`).

---

## Testing

Extend `tests/python/agents/test_synthesis.py`:

1. **`test_auto_prefers_cli_without_api_key`** — mock `shutil.which("claude")`,
   no `ANTHROPIC_API_KEY`, assert subprocess invoked (not `AsyncAnthropic`)
2. **`test_auto_prefers_sdk_with_api_key`** — key set, assert SDK path (existing
   mock pattern)
3. **`test_backend_cli_forces_cli_even_with_key`** — key set + `backend: cli`,
   assert subprocess
4. **`test_backend_sdk_forces_sdk`** — `backend: sdk`, assert SDK even if CLI on PATH
5. **`test_cli_success_parses_json`** — mock `create_subprocess_exec` returning
   valid JSON stdout
6. **`test_cli_nonzero_exit_returns_error`** — exit 1 + stderr → error envelope
7. **`test_cli_uses_synthesis_model_tier`** — assert `--model` arg matches
   `model_tiers.claude.sonnet`
8. **`test_invalid_backend_falls_back_to_auto`** — unknown value → auto behavior
9. **`test_auto_neither_cli_nor_key_returns_combined_error`** — no subprocess,
   no SDK call; error mentions both auth paths
10. **`test_cli_timeout_kills_child`** — mock subprocess where `communicate`
    raises `TimeoutError`; assert `proc.kill` called
11. **`test_cli_file_then_stdout_strategy`** — config with `output:
    file_then_stdout`; assert tempfile output is read
12. **Update `select_backend` import** — `tests/python/agents/test_cli.py` imports
    from `agents.config` after relocation

No live network or real `claude` binary required — all subprocess/SDK paths mocked.

Optional: one bats smoke asserting `parallel_agent.yml` contains
`synthesis.backend` (config drift guard).

---

## Documentation

| File | Change |
|------|--------|
| `docs/TROUBLESHOOTING.md` | New subsection under parallel agent: synthesis auth failures → check `claude /login` or set `synthesis.backend: sdk` + key |
| `docs/CONFIGURATION.md` | Document `synthesis.backend` |
| `docs/ARCHITECTURE_DIAGRAMS.md` | Note synthesis uses same backend selection as primary claude when `auto` |
| `configs/claude/references/parallel-agent.md` | One paragraph on synthesis auth |

Out of scope: changing primary agent `select_backend()` precedence; refactoring
`CLIAgent` to share code with synthesis (acceptable duplication for now).

---

## Success criteria

1. OAuth-only user (`claude /login`, no API key) gets successful synthesis when
   consensus is low and `claude` is on PATH.
2. User with `ANTHROPIC_API_KEY` and `backend: auto` continues to use SDK (no
   behavior regression).
3. `backend: sdk` and `backend: cli` override `auto` as documented.
4. All existing synthesis unit tests pass; new tests cover CLI path.
5. Orchestration never crashes on synthesis auth failure.
