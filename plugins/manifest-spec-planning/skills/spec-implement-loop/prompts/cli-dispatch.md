# CLI fallback dispatch (platforms without Task)

Use when the session **does not** expose native Task / sub-agent tools (Gemini
CLI, Codex, Antigravity, Devin, etc.). **Claude Code** and **Cursor** should use Task
sub-agents instead (`developer-dispatch.md`, `reviewer-dispatch.md`).

## Invoke seam

```bash
# Orchestrator assembles dispatch markdown (paths filled in), then:
printf '%s' "$dispatch_body" | \
  python3 <BUNDLE_ROOT>/runtime/cddl/cddl_invoke.py \
    --charter qa-critic
```

Environment overrides (same precedence as synthesis):

| Variable | Meaning |
|----------|---------|
| `CDDL_INVOKE_PROVIDER` | `antigravity`, `cursor`, `gemini`, `codex`, `claude`, `devin` |
| `CDDL_INVOKE_CLI` | Binary override (`agy`, `cursor-agent`, `devin`, …) |

Default `provider: auto` walks `runtime/config/review_models.json` → `provider_order`
(first CLI on PATH wins).

## Model tier

Role charters use `model: sonnet` (etc.) in frontmatter. `cddl_invoke.py`
resolves the tier via `providers.<provider>.models.<tier>` in `runtime/config/review_models.json`.
Override per call with `--model-tier flash`.

Devin is a native no-model route: it invokes
`devin --permission-mode auto -p <prompt>` and ignores charter model tiers.

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
