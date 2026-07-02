# Contract: Anti-Pattern Registry Entry Schema

**Consumers**: `code-quality` skill, `ai-code-audit` skill, CLAUDE.md digest generation, `learning_capture.sh` (writer), `sync-docs` (doc generation)
**Store**: `configs/claude/config/knowledge_base.yml` → `entries:` list

## Contract

Additive extension of the existing entry shape. Existing consumers MUST continue to work with entries lacking the new fields; new consumers MUST tolerate entries that have only the legacy fields.

```yaml
# Seeded guardrail entry (full shape)
- id: ANTI-010                      # required, unique, ANTI-### sequence
  title: "Catch-log-return-undefined (swallowed error)"   # required
  category: antipattern             # required, unchanged enum
  language: general                 # required: general|bash|python|typescript|javascript|go|terraform|yaml
  description: >                    # required
    A catch block logs the error and returns nothing, so callers receive
    undefined/None with no failure signal and crash later or corrupt state.
  tags: [error-handling, cwe-703]   # required; EXACTLY ONE guardrail-category tag:
                                    #   arch|async-state|error-handling|security|dependency|iteration
  confidence: high                  # required, existing enum
  created: 2026-07-01               # required
  last_seen: 2026-07-01             # required
  occurrences: 0                    # required (0 allowed for seeds)
  source: registry-seed             # required; captures keep existing source values
  severity: high                    # NEW optional: critical|high|medium|low|info
  detection_cue:                    # NEW optional: string OR per-language map
    typescript: "catch (e) { console.error(e) } with no rethrow/return in an async fn"
    python: "except Exception: log(...) then falling off the function end"
    bash: "cmd || echo 'warn' with no exit/return; errors continue silently"
  prevention_rule: >                # NEW optional; REQUIRED on seeded entries
    Every catch must propagate a usable signal: rethrow, return a typed
    error/fallback the caller checks, or route to a central handler that
    notifies the caller. Never log-and-fall-through.
  provenance: research-seed         # NEW optional: research-seed|session-capture
```

## Invariants (bats-enforced)

1. `severity`, when present, ∈ {critical, high, medium, low, info}.
2. Every entry with `provenance: research-seed` has a non-empty `prevention_rule` and exactly one guardrail-category tag.
3. Union of guardrail-category tags across seeded entries = all six categories.
4. Count of entries carrying a guardrail-category tag ≥ 25.
5. File passes `yamllint` and loads via `yaml.safe_load`.
6. `learning_capture.sh` round-trip: writing an entry with the new fields preserves them; writing a legacy entry (no new fields) still succeeds.

## Compatibility

- `learning_capture.sh` gains optional flags/env for the new fields; invocation without them is byte-compatible with today's behavior.
- `docs/KNOWLEDGE_BASE.md` regeneration (`sync-docs`) must render the new fields when present (prevention rule shown; detection cues summarized).
