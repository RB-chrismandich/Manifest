# CLI fallback dispatch (platforms without Task)

Use when the session **does not** expose native Task / sub-agent tools (Gemini
CLI, Codex, Antigravity, etc.). **Claude Code** and **Cursor** should use Task
sub-agents instead (`developer-dispatch.md`, `reviewer-dispatch.md`).

## Invoke seam

```bash
# Orchestrator assembles dispatch markdown (paths filled in), then:
printf '%s' "$dispatch_body" | \
  python3 ~/.claude/scripts/cddl_invoke.py \
    --charter ~/.claude/prompts/cddl/qa-critic.md
```

Environment overrides (same precedence as synthesis):

| Variable | Meaning |
|----------|---------|
| `CDDL_INVOKE_PROVIDER` | `antigravity`, `cursor`, `gemini`, `codex`, `claude` |
| `CDDL_INVOKE_CLI` | Binary override (`agy`, `cursor-agent`, …) |

Default `provider: auto` walks `parallel_agent.yml` → `synthesis.provider_order`
(first CLI on PATH wins).

## Model tier

Role charters use `model: sonnet` (etc.) in frontmatter. `cddl_invoke.py`
resolves the tier via `model_tiers.<provider>.<tier>` in `parallel_agent.yml`.
Override per call with `--model-tier flash`.

## Orchestrator duties (unchanged)

- Still **never** write implementation code on CLI fallback paths.
- Parse `cddl-verdict` blocks from stdout (`prompts/verdict-format.md`).
- Persist raw output to `iterations/<n>/<persona>.md`.
- Run verification between developer output and critic passes.

## Developer persona

The developer **cannot** use `cddl_invoke.py` alone — they must edit the repo.
On CLI-only platforms the orchestrator runs the developer work **inline** in
the main session (only when Task is unavailable), or asks the operator to switch
to Cursor / Claude Code for full CDDL. Critics and developer-reviewer always
use `cddl_invoke.py` when Task is absent.
