# Implementation Plan: Parallel Agent Orchestration Modularization

**Branch**: `001-modularize-parallel-agent` | **Date**: 2026-05-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-modularize-parallel-agent/spec.md`

## Summary

Split `configs/claude/scripts/parallel_agent.py` (2145 lines, 73 functions) into a
6-module `agents/` Python package co-located with the entry point, preserving the
existing CLI interface, updating test imports, and adding per-module unit tests. The
entry point shim remains at `parallel_agent.py` for full backward compatibility.

## Technical Context

**Language/Version**: Python 3.9+ (3.12+ preferred; bootstrap auto-detects)

**Primary Dependencies**: asyncio (stdlib), rich, pyyaml, anthropic (optional),
google.genai (optional) — no new dependencies introduced by this change

**Storage**: N/A

**Testing**: pytest (`tests/python/`)

**Target Platform**: macOS (Intel/Apple Silicon) + Linux (Debian, RHEL, Arch, openSUSE)

**Project Type**: CLI tool with Python package internals

**Performance Goals**: No measurable performance regression vs. current implementation;
import overhead from package structure MUST be negligible (<50ms additional startup)

**Constraints**: Each new module MUST be under 500 lines; runners.py and orchestrator.py
are accepted exceptions (see Complexity Tracking)

**Scale/Scope**: 2145-line monolith → 6 focused modules + entry point shim + 6 new
per-module test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | ✅ Pass | All changes within `configs/claude/scripts/`; deployment path unchanged |
| II. Parallel Agent Orchestration | ✅ Required (MUST) | This is a >200-line modification; the constitution states MUST for cross-verification before merge. Parallel agent review (`~/.claude/scripts/parallel_agent.py --review`) is a hard gate, not advisory — see T030 (moved to pre-merge gate, not polish) |
| III. Consensus-Driven Decisions | ✅ N/A | Applies to PR review phase, not planning |
| IV. Skill-First Extensibility | ✅ Pass | No new skills added; no scripts expanded beyond their scope |
| V. Bootstrap Reproducibility | ✅ Pass | Entry point path unchanged; `bootstrap.sh` deploy logic unaffected |

**Post-design re-check** (after Phase 1): All gates still pass. The 6-module layout
introduces no new deployment concerns and the shim pattern keeps `parallel_agent.py`
at its existing path. Principle II requires parallel agent review as a hard merge gate
(not advisory); T030 in tasks.md is positioned accordingly.

## Project Structure

### Documentation (this feature)

```text
specs/001-modularize-parallel-agent/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (module interface map)
├── quickstart.md        # Phase 1 output (developer verification guide)
├── contracts/
│   └── cli-contract.md  # CLI interface contract (regression gate)
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code (repository root)

```text
configs/claude/scripts/
├── parallel_agent.py              # Entry-point shim (replaces monolith)
└── agents/                        # New Python package
    ├── __init__.py                # Re-exports all public symbols
    ├── config.py                  # Config, ServiceConfig, Logger, RateLimiter
    ├── validation.py              # ValidationEngine
    ├── synthesis.py               # SynthesisEngine
    ├── runners.py                 # BaseAgent + ClaudeAgent, GeminiAgent, CursorAgent, CodexAgent
    ├── orchestrator.py            # Orchestrator, check_credits
    └── cli.py                     # main(), argparse setup

tests/python/
├── test_parallel_agent.py         # Existing integration test (imports updated)
└── agents/                        # New per-module unit tests
    ├── __init__.py
    ├── test_config.py
    ├── test_validation.py
    ├── test_synthesis.py
    ├── test_runners.py
    ├── test_orchestrator.py
    └── test_cli.py
```

**Structure Decision**: Single project layout. The `agents/` package lives inside
`configs/claude/scripts/` (alongside the entry point) so `sys.path` handling in tests
requires no changes. New test files mirror the module layout under `tests/python/agents/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| `runners.py` ~550 lines (SC-004 ceiling: 500) | All five agent classes (BaseAgent + four implementations) share the same interface and are tightly coupled; they belong together | Splitting BaseAgent from concrete classes would create a circular import (concrete classes import BaseAgent; BaseAgent defines the interface all use) or require a third module just for the base, adding complexity with no readability gain |
| `orchestrator.py` ~540 lines (SC-004 ceiling: 500) | `Orchestrator` is a single cohesive class with no extractable sub-concern; `check_credits` is a utility function closely tied to it | Extracting sub-methods of Orchestrator into helper modules would create a one-to-many import graph that is harder to read than the current single class |
