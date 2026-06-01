# Research: Parallel Agent Orchestration Modularization

**Branch**: `001-modularize-parallel-agent` | **Phase**: 0 | **Date**: 2026-05-31

## Module Boundary Decision

**Decision**: 6-module split — `config`, `validation`, `synthesis`, `runners`,
`orchestrator`, `cli` — plus `__init__.py`. This expands the user's proposed 5-module
split by separating `Orchestrator` from the concrete agent classes.

**Rationale**: The `Orchestrator` class spans ~416 lines and the five concrete agent
classes (BaseAgent + four implementations) span ~535 lines. Combining them into a single
`runners.py` would produce ~951 lines, nearly doubling SC-004's 500-line ceiling. The
natural seam between "individual agent execution" and "multi-agent coordination" maps
cleanly to two separate files.

**Alternatives considered**:
- 5-module split per original proposal (config, runners, synthesis, validation, cli):
  rejected — would put all agent classes + Orchestrator into runners.py (~951 lines).
- 7+ module split (e.g., separate `base_agent.py` from concrete agents): rejected —
  the concrete agent classes are 69–146 lines each and tightly coupled to `BaseAgent`;
  splitting them adds complexity with no readability gain.

**Module line estimates** (source class lines + ~15 lines of module-level boilerplate):

| Module | Contents | Est. Lines |
|--------|----------|-----------|
| `agents/config.py` | Config, ServiceConfig, Logger, RateLimiter | ~226 |
| `agents/validation.py` | ValidationEngine | ~415 |
| `agents/synthesis.py` | SynthesisEngine | ~145 |
| `agents/runners.py` | BaseAgent, ClaudeAgent, GeminiAgent, CursorAgent, CodexAgent | ~550 |
| `agents/orchestrator.py` | Orchestrator, check_credits | ~540 |
| `agents/cli.py` | main(), argparse setup, module-level script code | ~290 |
| `agents/__init__.py` | Re-exports of public symbols | ~30 |

`runners.py` (~550) and `orchestrator.py` (~540) slightly exceed SC-004's 500-line
target; see Complexity Tracking in plan.md for justification.

---

## Entry Point Strategy

**Decision**: `parallel_agent.py` becomes a thin shim (~10 lines) that imports
`agents.cli.main` and calls it.

**Rationale**: Every existing caller (CI workflows, user shell scripts, deployment docs)
references `parallel_agent.py` by path. Keeping the file as the entry point requires
zero changes to any external caller while all business logic migrates into the package.

**Alternatives considered**:
- Delete `parallel_agent.py` and rely on `python -m agents.cli`: rejected — breaks all
  existing callers without any benefit; requires documenting a new invocation path.
- Create a separate thin wrapper script: rejected — redundant with keeping parallel_agent.py.

---

## Package Location

**Decision**: Package directory at `configs/claude/scripts/agents/`.

**Rationale**: Co-located with the entry point shim. The existing test setup already
adds `configs/claude/scripts/` to `sys.path`, so `agents` is importable as a
subpackage without any path changes in tests or CI.

**Alternatives considered**:
- `configs/claude/scripts/src/agents/` (src layout): rejected — adds a path level with
  no benefit for a CLI tool; would require changing `sys.path` in tests.
- Top-level `agents/` at repo root: rejected — doesn't follow the existing `configs/`
  deployment model.

---

## Behavioral Equivalence Testing

**Decision**: Two-layer verification.

Layer 1 — existing test suite: Run `pytest tests/python/test_parallel_agent.py` before
(with original file) and after (with updated imports). All tests must pass both times.
The test covers: Config, ServiceConfig, Logger, RateLimiter, ValidationEngine,
SynthesisEngine, BaseAgent, CodexAgent, Orchestrator, and CLI argument parsing —
sufficient class-level coverage for structural equivalence.

Layer 2 — CLI smoke test: Capture JSON output of a dry-run invocation before
modularization (`python parallel_agent.py --json --claude-only "smoke test"`), then
replay the same invocation after and diff the output structure (not content, since LLM
responses vary). Exit code and JSON schema shape must be identical.

**Rationale**: The existing test suite was specifically written to cover all major
classes; it provides a natural pre/post regression gate. The CLI smoke test catches any
import-time errors not covered by unit tests (e.g., missing `__all__` exports, circular
imports).

**Alternatives considered**:
- Full integration test with live agents: rejected — requires API keys; flaky in CI.
- Manual inspection only: rejected — too error-prone for a 2145-line migration.

---

## Import Compatibility for Test File

**Decision**: Update `tests/python/test_parallel_agent.py` to import from the package:
```
from agents.config import Config, ServiceConfig, Logger, RateLimiter
from agents.validation import ValidationEngine
from agents.synthesis import SynthesisEngine
from agents.runners import BaseAgent, CodexAgent
from agents.orchestrator import Orchestrator
```

The `sys.path.insert(0, SCRIPTS_DIR)` line remains unchanged (SCRIPTS_DIR still points
to `configs/claude/scripts/`, where the `agents/` package will live).

**Rationale**: Direct per-module imports verify that each module is independently
importable (FR-004) and that the test suite exercises the actual modular structure
rather than a re-export facade.

**Alternatives considered**:
- Keep imports via `parallel_agent` shim (which re-exports everything): rejected —
  this would not exercise FR-004 or SC-005; the test would pass even with broken
  per-module imports.

---

## Per-Module Unit Test Strategy

**Decision**: One new test file per module, placed in `tests/python/agents/`:
- `test_config.py`: tests moved/adapted from existing TestConfig, TestServiceConfig
- `test_validation.py`: tests moved/adapted from existing TestValidationEngine
- `test_synthesis.py`: tests moved/adapted from existing TestSynthesisEngine
- `test_runners.py`: tests moved/adapted from existing TestBaseAgent, TestCodexAgent
- `test_orchestrator.py`: tests moved/adapted from existing TestOrchestrator
- `test_cli.py`: tests moved/adapted from existing CLI argument parsing tests

The existing `tests/python/test_parallel_agent.py` is updated (imports only) and kept
as the integration-level regression file.

**Rationale**: Moving tests to per-module files satisfies FR-008 and SC-005. Adapting
existing tests (rather than writing new ones from scratch) reduces risk of divergence
and ensures coverage parity.
