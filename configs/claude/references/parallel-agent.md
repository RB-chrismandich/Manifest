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

| Task Type | Cursor | Claude | Gemini | Reason |
|-----------|--------|--------|--------|--------|
| Security | advanced | opus | pro | Maximum capability for critical code |
| Review | flash | sonnet | flash | Balanced performance/cost |
| Analyze | flash | sonnet | flash | Good reasoning without opus cost |
| Improve | mini | haiku | flash | Lighter models for suggestions |
| Quick | mini | haiku | flash | Speed for simple queries |

**Model Tier Mappings:**

| Tier | Cursor | Claude | Gemini | Codex | Antigravity |
|------|--------|--------|--------|-------|-------------|
| mini/haiku | gpt-5.1-codex-mini | claude-haiku-4-5-20251001 | - | gpt-5.4-mini | Gemini 3.5 Flash (Low) |
| flash/sonnet | gpt-5.1-codex | claude-sonnet-4-6 | gemini-3-flash-preview | gpt-5.4 | Gemini 3.5 Flash (High) |
| advanced/opus/pro | gpt-5.2 | claude-opus-4-8 | gemini-3-pro-preview | gpt-5.5 | Claude Opus 4.6 (Thinking) |
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

## Credit Exhaustion Fallback

The script automatically detects credit/quota exhaustion and falls back:

- **Cursor**: gpt-5.2 → gpt-5.1-codex → gpt-5.1-codex-mini → auto
- **Claude**: fable → opus → sonnet → haiku
- **Codex**: gpt-5.5 → gpt-5.4 → gpt-5.4-mini
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
      "model": "gpt-5.1-codex|auto",
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
    }
  },
  "output_files": {
    "cursor": "/path/to/cursor_output.txt",
    "gemini": "/path/to/gemini_output.txt",
    "claude": "/path/to/claude_output.txt",
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
| `CURSOR_MODEL_MINI` | Model name for 'mini' tier | `gpt-5.1-codex-mini` |
| `CURSOR_MODEL_FLASH` | Model name for 'flash' tier | `gpt-5.1-codex` |
| `CURSOR_MODEL_ADVANCED` | Model name for 'advanced' tier | `gpt-5.2` |
| `GEMINI_MODEL_FLASH` | Model name for 'flash' tier | `gemini-3-flash-preview` |
| `GEMINI_MODEL_PRO` | Model name for 'pro' tier | `gemini-3-pro-preview` |
| `CHECK_CREDITS_PREFLIGHT` | Enable pre-flight credit check | `false` |

## Output Location

All outputs are stored in: `~/.claude/.agent_outputs/`

Files generated per run:

- `cursor_YYYYMMDD_HHMMSS.txt` - Cursor Agent output
- `gemini_YYYYMMDD_HHMMSS.txt` - Gemini CLI output
- `claude_YYYYMMDD_HHMMSS.txt` - Claude CLI output
- `summary_YYYYMMDD_HHMMSS.md` - Markdown summary
- `results_YYYYMMDD_HHMMSS.json` - JSON output (if --json)
