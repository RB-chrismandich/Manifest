# Authentication Problems

> Login, token, and credential failures per provider.

**Last Updated**: 2026-08-20

## Authentication Issues

> **API keys are optional.** The Claude/Gemini agents select an execution backend
> per run: the provider SDK when its package and API key
> (`ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) are both present, otherwise the
> logged-in `claude` / `gemini` CLI (OAuth/subscription login). As long as the
> CLIs are authenticated, orchestration works without any API key.

### Claude CLI: "Not authenticated"

**Symptom:**

```text
Error: You are not authenticated. Run 'claude auth login'
```

**Solution:**

```bash
# Log in to Claude CLI (OAuth/subscription login — no API key required)
claude auth login

# Verify authentication
claude auth status
```

**API key (optional, for the SDK backend):**

1. Visit: <https://console.anthropic.com/account/keys>
2. Create new API key
3. Export it as `ANTHROPIC_API_KEY` to make the orchestrator use the SDK
   backend instead of the CLI fallback

---

### Synthesis fails with no synthesizer available

**Symptom:**

```text
Synthesis unavailable: no CLI on PATH for configured providers ...
```

(or the same message in JSON `error` when consensus is low)

**Cause:** Low-consensus synthesis merges agent disagreements via a single
headless CLI. With `synthesis.provider: auto` (default), the first provider in
`synthesis.provider_order` that is on PATH wins (`antigravity` → `cursor` →
`gemini` → `codex` → `claude`). Override with `SYNTH_PROVIDER` or `SYNTH_CLI`.

**Solution:**

```bash
# Antigravity (default first in provider_order)
agy --version

# Cursor
cursor-agent --version

# Claude OAuth path
claude auth login

# Force a provider in ~/.claude/config/parallel_agent.yml
#   synthesis:
#     provider: cursor   # or antigravity, gemini, codex, claude
# Or env for one run:
SYNTH_PROVIDER=cursor manifest parallel-agent --json ...

# Headless/CI: Anthropic SDK only when explicitly configured
#   synthesis:
#     provider: sdk
# and export ANTHROPIC_API_KEY
```

**Related seams** (same `cli_agents` registry, different env prefixes):

| Seam | Script / skill | Env overrides |
|------|----------------|---------------|
| CDDL critics | `cddl_invoke.py`, `/spec-implement-loop` | `CDDL_INVOKE_PROVIDER`, `CDDL_INVOKE_CLI` |
| SkillClaw evolve | `skillclaw_evolve.py`, `/skill-evolve` | `EVOLVE_PROVIDER`, `EVOLVE_CLI` |

On Gemini/Codex/Antigravity without native Task, CDDL critics use
`cddl_invoke.py` (see `.apm/skills/spec-implement-loop/prompts/cli-dispatch.md`).

---

### Gemini CLI: "Authentication failed"

**Symptom:**

```text
Error: Invalid API key
```

**Solution:**

```bash
# Authenticate with Gemini CLI
gemini  # first run prompts a Google OAuth login

# Verify authentication
gemini auth status
```

**API key (optional, for the SDK backend):**

1. Visit: <https://makersuite.google.com/app/apikey>
2. Create new API key
3. Export it as `GOOGLE_API_KEY` to make the orchestrator use the SDK
   backend instead of the CLI fallback

---

### Cursor: "Command not found"

**Symptom:**

```bash
cursor: command not found
```

**Solution:**

Cursor is a desktop application, not a CLI tool. The Manifest integration expects Cursor
to be installed but doesn't directly invoke it via command line in the current implementation.

**Workaround:**

```bash
# Disable Cursor in configuration
./bootstrap.sh --reconfigure --disable-cursor

# Or use --no-cursor flag
~/.claude/scripts/parallel_agent.py --no-claude "Task"
```

**Note:** Cursor integration may be implemented differently in your environment.
Check your specific Cursor setup for command-line access.

---

---

[← Troubleshooting](README.md)
