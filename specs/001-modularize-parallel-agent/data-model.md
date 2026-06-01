# Data Model: Parallel Agent Orchestration Modularization

**Branch**: `001-modularize-parallel-agent` | **Phase**: 1 | **Date**: 2026-05-31

This document describes the module architecture — the "data model" for a structural
refactoring is the package layout and the public interface each module exposes.

---

## Package Structure

```text
configs/claude/scripts/
├── parallel_agent.py          # Thin entry-point shim (replaces monolith)
└── agents/                    # New Python package
    ├── __init__.py            # Re-exports key public symbols
    ├── config.py              # Configuration and logging infrastructure
    ├── validation.py          # Two-tier validation engine
    ├── synthesis.py           # Agent disagreement synthesis engine
    ├── runners.py             # Agent base class and concrete implementations
    ├── orchestrator.py        # Multi-agent orchestration and credit checking
    └── cli.py                 # CLI entry point (argparse + main())
```

---

## Module Interfaces

### `agents/config.py`

**Responsibility**: All runtime configuration, structured logging, and rate limiting.

| Symbol | Type | Description |
|--------|------|-------------|
| `Config` | class | Loads and exposes YAML config with dot-notation access |
| `ServiceConfig` | class | Per-service configuration (model, timeout, enabled flag) |
| `Logger` | class | Structured logger with JSON output and log rotation |
| `RateLimiter` | class | Token-bucket rate limiter for API call pacing |

**Dependencies**: standard library only (no cross-module imports from agents/).

---

### `agents/validation.py`

**Responsibility**: Tier 1 (blocking) and Tier 2 (advisory) quality gate evaluation.

| Symbol | Type | Description |
|--------|------|-------------|
| `ValidationEngine` | class | Evaluates agent outputs against validation criteria |

**Imports from agents/**: `config.Config`, `config.Logger`

---

### `agents/synthesis.py`

**Responsibility**: Consensus detection and synthesis prompt generation.

| Symbol | Type | Description |
|--------|------|-------------|
| `SynthesisEngine` | class | Detects low-consensus cases and synthesizes resolutions |

**Imports from agents/**: `config.Config`, `config.Logger`

---

### `agents/runners.py`

**Responsibility**: Individual agent execution — one class per supported LLM provider.

| Symbol | Type | Description |
|--------|------|-------------|
| `BaseAgent` | abstract class | Shared interface: `run()`, credit exhaustion detection |
| `ClaudeAgent` | class | Anthropic Claude implementation |
| `GeminiAgent` | class | Google Gemini implementation |
| `CursorAgent` | class | Cursor IDE agent implementation |
| `CodexAgent` | class | OpenAI Codex implementation |

**Imports from agents/**: `config.Config`, `config.ServiceConfig`, `config.Logger`,
`config.RateLimiter`

---

### `agents/orchestrator.py`

**Responsibility**: Coordinating multiple agents concurrently and scoring consensus.

| Symbol | Type | Description |
|--------|------|-------------|
| `Orchestrator` | class | Runs agents in parallel, aggregates results, scores consensus |
| `check_credits` | async function | Verifies API credit availability before orchestration |

**Imports from agents/**: all runner classes, `config.*`, `validation.ValidationEngine`,
`synthesis.SynthesisEngine`

---

### `agents/cli.py`

**Responsibility**: CLI argument parsing and the script entry point.

| Symbol | Type | Description |
|--------|------|-------------|
| `main` | async function | Parses args, constructs agents, delegates to Orchestrator |

**Imports from agents/**: all modules (highest fan-in; this is by design for a CLI entry point)

---

### `agents/__init__.py`

Re-exports the symbols most likely to be imported by tests or external tooling:

```python
from agents.config import Config, ServiceConfig, Logger, RateLimiter
from agents.validation import ValidationEngine
from agents.synthesis import SynthesisEngine
from agents.runners import BaseAgent, ClaudeAgent, GeminiAgent, CursorAgent, CodexAgent
from agents.orchestrator import Orchestrator, check_credits
from agents.cli import main
```

---

### `parallel_agent.py` (entry-point shim)

```python
#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from agents.cli import main

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Dependency Graph

```text
cli.py
 ├── orchestrator.py
 │    ├── runners.py
 │    │    └── config.py
 │    ├── validation.py
 │    │    └── config.py
 │    └── synthesis.py
 │         └── config.py
 └── config.py

config.py → (stdlib only)
```

No circular dependencies. `config.py` is the leaf; `cli.py` is the root.

---

## State Transitions

This feature has no runtime state changes — it is a structural refactoring. The
behavior of each module mirrors the behavior of the corresponding code block in the
original monolith.

---

## Test Module Map

| Source module | Test file |
|---------------|-----------|
| `agents/config.py` | `tests/python/agents/test_config.py` |
| `agents/validation.py` | `tests/python/agents/test_validation.py` |
| `agents/synthesis.py` | `tests/python/agents/test_synthesis.py` |
| `agents/runners.py` | `tests/python/agents/test_runners.py` |
| `agents/orchestrator.py` | `tests/python/agents/test_orchestrator.py` |
| `agents/cli.py` | `tests/python/agents/test_cli.py` |
| Integration (all modules) | `tests/python/test_parallel_agent.py` (imports updated) |
