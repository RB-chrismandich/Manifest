# Worked Examples

> Complete configurations for common setups.

## Examples

### Example 1: Lightweight Security Scan

```bash
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  --timeout 120 \
  --review auth.py
```

**Effect:**

- Uses cheapest models (mini/haiku)
- 2-minute timeout
- Still runs Tier 1 security validation

### Example 2: Deep Security Analysis

```bash
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --gemini-model pro \
  --timeout 900 \
  --full-output \
  --validate \
  --review auth.py
```

**Effect:**

- Uses the highest-capability model tier
- 15-minute timeout
- Full output (no truncation)
- Explicit validation checks

### Example 3: Single Agent with Custom Output

```bash
~/.claude/scripts/parallel_agent.py \
  --claude-only \
  --claude-model sonnet \
  --json \
  --output /tmp/analysis \
  "Analyze this codebase"
```

**Effect:**

- Only Claude runs (no Cursor/Gemini)
- JSON output format
- Custom output directory

---

---

[← Configuration](README.md)
