# Parallel Agent Reference

> Full flags, model tiers, credit fallback, JSON schema, env vars, and output
> location for `~/.claude/scripts/parallel_agent.py`. Referenced from CLAUDE.md.

## Options

| Option | Description |
|--------|-------------|
| `--json` | Output JSON for programmatic parsing |
| `--full-output` | Include complete agent outputs (no truncation) |
| `--validate` | Check outputs against success criteria |
| `--review <file>` | Code review mode |
| `--analyze <file>` | Bug/security analysis mode |
| `--improve <file>` | Improve observation YAML mode |
| `--cursor-only` | Run only Cursor Agent |
| `--gemini-only` | Run only Gemini CLI |
| `--claude-only` | Run only Claude CLI |
| `--codex-only` | Run only Codex CLI |
| `--antigravity-only` | Run only Antigravity (agy) |
| `--no-claude` | Disable Claude CLI (enabled by default) |
| `--no-antigravity` | Disable Antigravity for this run |
| `--cursor-model <tier>` | Cursor model: mini, flash, advanced, auto (default: flash) |
| `--claude-model <tier>` | Claude model: haiku, sonnet, opus, fable (default: sonnet) |
| `--antigravity-model <tier>` | Antigravity model: mini, flash, advanced (default: flash) |
| `--check-credits` | Run pre-flight credit check |
| `--timeout <sec>` | Timeout per agent (default: 120) |
| `--output <dir>` | Custom output directory |

**Note on Sandboxed Environments**: When running from Task subagents or other sandboxed
contexts, the script automatically detects write permission issues and falls back to
`/tmp/.claude_agent_outputs_$$`. If you encounter file creation errors, manually specify
an output directory with `--output /tmp/agent_outputs`.

## Model Selection

The orchestrating agent (Claude) selects models based on task complexity:

| Task Type | Cursor | Claude | Gemini | Antigravity | Reason |
|-----------|--------|--------|--------|-------------|--------|
| Security | advanced | opus | pro | advanced | Maximum capability for critical code |
| Review | flash | sonnet | flash | flash | Balanced performance/cost |
| Analyze | flash | sonnet | flash | flash | Good reasoning without opus cost |
| Improve | mini | haiku | flash | mini | Lighter models for suggestions |
| Quick | mini | haiku | flash | mini | Speed for simple queries |

**Model Tier Mappings:**

| Tier | Cursor | Claude | Gemini | Codex | Antigravity |
|------|--------|--------|--------|-------|-------------|
| mini/haiku | cursor-grok-4.5-low | claude-haiku-4-5 | - | gpt-5.6-luna | gemini-3.6-flash-low |
| flash/sonnet | cursor-grok-4.5-medium | claude-sonnet-5 | gemini-3-flash-preview | gpt-5.6-terra | gemini-3.6-flash-high |
| advanced/opus/pro | cursor-grok-4.5-high | claude-opus-5 | gemini-3-pro-preview | gpt-5.6-sol | claude-opus-4-6-thinking |
| fable (security) | - | claude-fable-5 | - | - | - |

**Known correlation**: Antigravity serves Gemini/Claude model families also present via
direct API; consensus scores can be inflated by same-family agreement, and agy's catalog
may lag the direct API (e.g. Opus 4.6 vs 4.8) — `agy models` is its ground truth
(checked by `model_check.sh`).

## Execution Backend (SDK vs CLI)

Claude and Gemini agents pick an execution backend per run (`agents.cli.select_backend`):

1. **SDK** — when the provider package (`anthropic` / `google-generativeai`) AND its
   API key (`ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) are both present.
2. **CLI fallback** — otherwise, when the provider CLI (`claude` / `gemini`) is on
   PATH. OAuth/subscription logins work here with no API key — this is the default
   path on machines authenticated via `claude login` / gemini OAuth.
3. **SDK with its own auth** (ADC/OAuth) as a last resort, else the provider is
   skipped with a warning.

Command shapes come from `cli_agents.claude` / `cli_agents.gemini` in
`parallel_agent.yml`. Pin staleness on OAuth-only machines is checked with
`MODEL_CHECK_PROBE=1 model_check.sh` (live one-shot CLI probe per pin).

## Synthesis auth

When consensus is low, `SynthesisEngine` merges agent outputs. Configure
`synthesis.backend` in `parallel_agent.yml`:

- **`auto`** (default) — same backend selection as the primary claude agent
- **`cli`** — always `claude -p` (OAuth/subscription login)
- **`sdk`** — always Anthropic SDK (`ANTHROPIC_API_KEY`; headless/CI)

## Credit Exhaustion Fallback

The script automatically detects credit/quota exhaustion and falls back:

- **Cursor**: cursor-grok-4.5-high → cursor-grok-4.5-medium → cursor-grok-4.5-low → auto
- **Claude**: fable → opus → sonnet → haiku
- **Codex**: gpt-5.6-sol → gpt-5.6-terra → gpt-5.6-luna
- **Antigravity**: advanced → flash → mini

Detection methods:

1. Parse stderr for credit/quota error patterns after execution
2. Optional pre-flight check with `--check-credits` flag

## JSON Output Schema

```json
{
  "timestamp": "YYYYMMDD_HHMMSS",
  "mode": "review|analyze|prompt",
  "prompt": "The task description",
  "agents": {
    "cursor": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "model": "cursor-grok-4.5-medium|auto",
      "credit_fallback": false,
      "output": "Agent response..."
    },
    "gemini": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "output": "Agent response..."
    },
    "claude": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "model": "sonnet|haiku|opus",
      "credit_fallback": false,
      "output": "Agent response..."
    },
    "antigravity": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "model": "flash|mini|advanced",
      "credit_fallback": false,
      "output": "Agent response..."
    }
  },
  "output_files": {
    "cursor": "/path/to/cursor_output.txt",
    "gemini": "/path/to/gemini_output.txt",
    "claude": "/path/to/claude_output.txt",
    "antigravity": "/path/to/antigravity_output.txt",
    "summary": "/path/to/summary.md"
  },
  "cross_verification": {
    "consensus_score": 85,
    "confidence": "high|medium|low",
    "agent_count": 5
  }
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_INCLUDE_DIRS` | Colon-separated directories for Gemini | `$(pwd):~/.claude:~/.gemini` |
| `CHECK_CREDITS_PREFLIGHT` | Enable pre-flight credit check | `false` |

## Output Location

All outputs are stored in: `~/.claude/.agent_outputs/`

Files generated per run:

- `cursor_YYYYMMDD_HHMMSS.txt` - Cursor Agent output
- `gemini_YYYYMMDD_HHMMSS.txt` - Gemini CLI output
- `claude_YYYYMMDD_HHMMSS.txt` - Claude CLI output
- `antigravity_YYYYMMDD_HHMMSS.txt` - Antigravity (agy) output
- `summary_YYYYMMDD_HHMMSS.md` - Markdown summary
- `results_YYYYMMDD_HHMMSS.json` - JSON output (if --json)
