# Python Parallel Agent - Installation & Usage

## Quick Start

### 1. Check Python Version

**Important**: If you have multiple Python versions installed, use a stable version (3.9-3.12):

```bash
# Check which Python you're using
python3 --version

# macOS users: If you see Python 3.15+ (alpha), use system Python instead
/usr/bin/python3 --version  # Usually Python 3.9 (stable)
```

**Known Issue**: Python 3.15 alpha versions may have package compatibility issues. Use the
bootstrap script (which auto-selects stable Python) or manually use `/usr/bin/python3`
on macOS.

### 2. Install Dependencies

```bash
cd ~/.claude/scripts

# If using system Python 3.9 (macOS with multiple versions)
/usr/bin/python3 -m pip install --user -r requirements.txt

# Or if your default python3 is stable
python3 -m pip install --user -r requirements.txt
```

Or with a virtual environment (recommended):

```bash
cd ~/.claude/scripts
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
pip install -r requirements.txt
```

### 2. Set Authentication

#### Option A: OAuth (Recommended for Gemini)

```bash
# Gemini - OAuth (same as gemini CLI)
gemini auth login
# OR use gcloud
gcloud auth application-default login

# Claude - API Key (only option currently)
export ANTHROPIC_API_KEY="sk-ant-..."
```

#### Option B: API Keys (Works for both)

```bash
# Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# Gemini (if not using OAuth)
export GOOGLE_API_KEY="..."
```

**Recommendation:** Use OAuth for Gemini (more secure, auto-refreshes), API key for Claude.

### 3. Run the Prototype

**Note**: If you used `/usr/bin/python3` to install dependencies, use it to run the script too:

```bash
# Basic usage (use same Python version that has packages installed)
/usr/bin/python3 parallel_agent.py "What is 2+2?"
# OR if your default python3 has packages
python3 parallel_agent.py "What is 2+2?"

# With JSON output
python3 parallel_agent.py --json "Explain async programming"

# Code review mode
python3 parallel_agent.py --review /path/to/file.py

# With validation
python3 parallel_agent.py --json --validate "Review this code"

# Single agent mode
python3 parallel_agent.py --claude-only "Your question"
```

**Troubleshooting**: If you get "ModuleNotFoundError", ensure you're using the same
Python version that you installed packages with:

```bash
# Check which Python has packages
/usr/bin/python3 -m pip list | grep anthropic
python3 -m pip list | grep anthropic

# Use whichever shows the packages
```

## Features Implemented

✅ **Async-first architecture** using `asyncio`
✅ **Rate limiting** with token bucket algorithm
✅ **Official API clients** (Claude via `anthropic`, Gemini via `google-generativeai`)
✅ **Cursor fallback** (shells out to existing cursor CLI)
✅ **JSON output** matching Bash schema
✅ **Rich CLI output** with progress indicators and formatted tables
✅ **Configuration file** support (`~/.claude/config/parallel_agent.yml`)
✅ **Cross-verification** with consensus scoring
✅ **Timeout handling** per agent
✅ **Model tier resolution** (haiku/sonnet/opus, flash/pro)

## Features TODO

⏳ **Credit fallback** (opus→sonnet→haiku on quota exhaustion)
⏳ **Output file writing** (currently only prints to stdout)
⏳ **Synthesis agent** (for low consensus scenarios)
⏳ **Validation criteria** (full Tier 1/Tier 2 implementation)
⏳ **Streaming responses** (real-time progress)
⏳ **Retry logic** with exponential backoff
⏳ **Agent caching** (avoid redundant API calls)

## Configuration

Edit `~/.claude/config/parallel_agent.yml` to customize:

- Rate limits per agent
- Model tier mappings
- Timeout values
- Retry behavior
- Consensus thresholds
- Output preferences

See the file for full documentation.

## Testing

### Test Configuration Loading

```python
python3 -c "
from parallel_agent import Config
config = Config()
print('Claude models:', config.get('model_tiers.claude'))
print('Rate limits:', config.get('rate_limits'))
"
```

### Test Rate Limiter

```python
python3 -c "
import asyncio
from parallel_agent import RateLimiter

async def test():
    limiter = RateLimiter(requests_per_minute=60, burst_size=5)
    for i in range(10):
        await limiter.acquire()
        print(f'Request {i+1} - tokens: {limiter.tokens:.2f}')

asyncio.run(test())
"
```

### Test Without API Keys (Cursor only)

```bash
python parallel_agent.py --cursor-only "Test prompt"
```

## Migration from Bash

The Python implementation maintains compatibility with the Bash version:

1. **Same CLI flags**: `--json`, `--validate`, `--review`, `--timeout`, etc.
2. **Same JSON schema**: Output structure matches for easy migration
3. **Same config location**: Uses `~/.claude/config/`
4. **Coexistence**: Can run both `.sh` and `.py` in parallel

To switch default:

```bash
# In bootstrap.sh or your shell profile
export MANIFEST_PARALLEL_AGENT_IMPL=python  # or 'bash'

# Then create an alias
alias parallel_agent='python ~/.claude/scripts/parallel_agent.py'
```

## Performance Comparison

| Metric | Bash | Python |
|--------|------|--------|
| Startup time | ~50ms | ~200ms (includes import overhead) |
| Concurrent execution | Sequential with background jobs | True async with asyncio |
| Rate limiting | Simple sleep-based | Token bucket with burst |
| API client | Manual HTTP/curl | Official SDKs with retry logic |
| Error handling | Exit codes + trap | Structured exceptions |
| Memory usage | ~5MB | ~50MB (Python runtime) |

## Troubleshooting

### ImportError: anthropic

```bash
pip install anthropic
```

### ImportError: google.generativeai

```bash
pip install google-generativeai
```

### Rate limiting still occurring

Check your `parallel_agent.yml` rate limits and adjust:

```yaml
rate_limits:
  gemini:
    requests_per_minute: 15  # Lower if hitting limits
```

### Cursor agent not working

Ensure cursor CLI is installed and in PATH:

```bash
which cursor
# If not found, download from https://cursor.sh
```

## Next Steps

1. Install dependencies: `pip install -r requirements.txt`
2. Set API keys (see above)
3. Test with simple prompt: `python parallel_agent.py "Hello world"`
4. Compare with Bash version: `bash parallel_agent.sh "Hello world"`
5. Report any schema mismatches or bugs

## Contributing

See `.claude/.plans/20260210-parallel-agent-python-rewrite.md` for the full implementation roadmap.
