---
name: prompt-optimize
description: "Use when a user asks to create, optimize, refactor, or harden a raw prompt into a production-ready skill template (\"optimize this prompt\", \"turn this into a skill\", \"harden this prompt for automation\")."
---

# Prompt Optimize

Refactor a raw, unoptimized prompt into a hardened, production-ready skill template. Strip conversational
preamble, metadata explanations, and post-generation fluff from the output — return only the finished template.

## Constraints (apply once, embed into the output's `<constraints>` block)

- **Absolute paths**: no tildes (`~`) or unexpanded environment variables; resolve to fully qualified paths.
- **Match the target project's existing script-language convention**: do not assume Python over Bash, or vice
  versa — check what the surrounding codebase already uses (e.g. this repo's canonical convention is `.sh`,
  documented in `docs/CODING_STANDARDS.md`) and follow it.
- **Idempotency**: operations must be safe to re-run on a schedule without creating duplicates, breaking
  environment state, or fragmenting folders.

## Worked example

Raw prompt: "write something that syncs skills to all the home targets"

Optimized:

```xml
<problem_structure>
  <problem_definition>
    Sync the plugin skill tree (plugins/<bundle>/skills/) to every configured home deploy target (~/.claude, Cursor, Gemini, Codex, Antigravity)
    and report which targets changed.
  </problem_definition>
  <preliminary_context>
    Repo root contains plugins/<bundle>/skills/ (source of truth; .apm/skills is a generated mirror); home targets are listed in
    configs/claude/config/services.yml.
  </preliminary_context>
  <constraints>
    - Use absolute paths for source and every target; no tilde expansion left unresolved.
    - Follow the repo's existing script convention (bash, per docs/CODING_STANDARDS.md) rather than
      introducing a new language.
    - Re-running the sync must be a no-op when nothing changed (idempotent).
  </constraints>
  <desired_output>
    A summary table: target path, sync status (updated/unchanged/skipped), and reason if skipped.
  </desired_output>
</problem_structure>
```

Use judgment on which optional sections below apply to a given prompt — these are not a mandatory checklist.

## Target Serialization Schema

Return the output using this layout so downstream agent layers can parse it deterministically:

<problem_structure>
  <problem_definition>
    [Action-oriented task statement with precise boolean endpoints or metrics]
  </problem_definition>

  <preliminary_context>
    [Hardware targets, active software toolchains, API endpoints, and dependency states]
  </preliminary_context>

  <constraints>
    - Enforce absolute path strings; no raw tilde (~) directory configurations allowed.
    - Match the target project's existing script-language convention rather than assuming Python.
    - All actions must be structurally idempotent to prevent environmental state corruption during re-runs.
    - [Additional task-specific constraints]
  </constraints>

  <desired_output>
    [Strict formatting payload requirements: JSON object layouts, XML schemas, or fixed markdown tables]
  </desired_output>
</problem_structure>

## Optional Blueprints

If the task classification clearly matches one of these, use it as a shape guide — otherwise adapt freely:

### Blueprint A: Local Automation & Systems Operations

Task: Enforce deterministic system configuration, file syncing, or environment updates.

Format Requirements:

1. **Risk Profiling**: Enumerate environment dependencies or state impacts.
2. **Implementation Block**: Production-grade code or configuration values.
3. **State Verification**: A machine-executable verification string (e.g., dry-run flag) to prove success.

### Blueprint B: Data Streams & Algorithmic Analysis

Objective: Ingest, filter, and calculate multi-variable metrics or quantitative signals.

Format Requirements:

1. **Schema Validation**: Explicit safety check for missing elements, null responses, or noise.
2. **Compute Matrix**: Step-by-step logic calculating intermediate vectors before writing final fields.
3. **Fallback Logic**: Precise execution paths if input data streams fail schema validation.

### Blueprint C: Multi-Agent Choreography & State Handoffs

Task: Orchestrate task states across multiple specialized tool wrappers or sub-agents.

Format Requirements:

1. **Constitution Compliance**: Immediate boundary verification before spawning worker threads.
2. **State Payload Specification**: Strict definitions of variables passed across isolation boundaries.
3. **Execution Telemetry JSON**:

```json
{
  "plan_status": "success | failed",
  "steps_executed": [],
  "resulting_state": {},
  "telemetry": ""
}
```
