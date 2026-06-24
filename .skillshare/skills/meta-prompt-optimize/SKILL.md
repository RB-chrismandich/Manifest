---
name: meta-prompt-optimize
description: |
  Auto-trigger when users ask to create, optimize, refactor, or structure a new agent prompt or skill template.
  Ingests unoptimized input prompts and outputs a structurally pristine, normalized system skill template using XML schemas.
---

<problem_structure>
  <problem_definition>
    Ingest unoptimized input prompts and output a structurally pristine, hardened, production-ready system skill
    template. Eliminate all conversational preamble, metadata explanations, and post-generation fluff.
  </problem_definition>

  <preliminary_context>
    Pipeline executes four processing cycles: 1. Deconstruct intent/context, 2. Normalize to XML schema, 3. Inject
    safeguards (absolute paths, pythonic runtime, idempotency), 4. Cleanse conversational tags.
  </preliminary_context>

  <constraints>
    - Enforce absolute path strings; no raw tilde (~) directory configurations allowed.
    - Execute changes utilizing current Python-based utilities; explicitly omit deprecated shell (.sh) actions.
    - All actions must be structurally idempotent to prevent environmental state corruption during re-runs.
  </constraints>

  <desired_output>
    The output must adhere strictly to bare XML schemas without markdown wrappers, mapping to Blueprint A (Local
    Automation), Blueprint B (Data Streams), or Blueprint C (Multi-Agent Choreography):

<problem_structure>
  <problem_definition>
    [Action-oriented task statement with precise boolean endpoints or metrics]
  </problem_definition>

  <preliminary_context>
    [Hardware targets, active software toolchains, API endpoints, and dependency states]
  </preliminary_context>

  <constraints>
    - Enforce absolute path strings; no raw tilde (~) directory configurations allowed.
    - Execute changes utilizing current Python-based utilities; explicitly omit deprecated shell (.sh) actions.
    - All actions must be structurally idempotent to prevent environmental state corruption during re-runs.
    - [Additional task-specific constraints]
  </constraints>

  <desired_output>
    [Strict formatting payload requirements: JSON object layouts, XML schemas, or fixed markdown tables. Include
    specific Blueprint requirements (Risk Profiling/Implementation Block/State Verification for A; Schema
    Validation/Compute Matrix/Fallback Logic for B; Constitution Compliance/State Payload Specification/Execution
    Telemetry JSON for C). Execution Telemetry JSON must follow this exact layout:]

    {
      "plan_status": "success | failed",
      "steps_executed": [],
      "resulting_state": {},
      "telemetry": ""
    }
  </desired_output>
</problem_structure>
  </desired_output>
</problem_structure>
