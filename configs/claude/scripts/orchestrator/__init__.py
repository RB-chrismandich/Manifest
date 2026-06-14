"""Autonomous Issue Implementation Orchestrator.

A long-running daemon drives one GitHub/GitLab issue at a time through six
runtime phases to a clean Pull Request, invoking a stateless decision engine
once per phase under a strict machine-parseable JSON envelope contract.

Spec: specs/004-autonomous-issue-orchestrator/spec.md
Modules:
  engine    - stateless decision-engine adapter: payload build, envelope validation,
              severity derivation, deterministic prioritization core
  pipeline  - per-run state machine, no-automation gating, dependency-cycle detection
  daemon    - long-running poll/dispatch loop + CLI
  consensus - gate cross-verification over parallel_agent.py (FR-034)   [US2]
  audit     - append-only JSONL audit trail (FR-029)                    [US5]
  redact    - secret/PII redaction before persistence (FR-038)          [US5]
"""

__version__ = "0.1.0"
