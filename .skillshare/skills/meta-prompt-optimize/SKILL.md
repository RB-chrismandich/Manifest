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
    Operate as a deterministic, machine-to-machine prompt refactoring pipeline handling payloads from the scheduled
    task pipeline. Processing involves four cycles: Deconstruct, Normalize, Inject Safeguards, and Cleanse.
  </preliminary_context>

  <constraints>
    - Enforce absolute path strings; no raw tilde (~) directory configurations allowed.
    - Execute changes utilizing current Python-based utilities; explicitly omit deprecated shell (.sh) actions.
    - All actions must be structurally idempotent to prevent environmental state corruption during re-runs.
    - Explicitly preserve any literal schema templates (like XML tags or JSON layouts) inside the refactored output. Do
      not consume, delete, or over-summarize these structural templates during the normalization process, as they are
      required instructions for downstream agents.
  </constraints>

  <desired_output>
    Return the payload strictly mapped to the following mandatory XML-tag-demarcated schema so downstream agent
    layers can parse it deterministically:

    ```xml
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
        [Strict formatting payload requirements: JSON object layouts, XML schemas, or fixed markdown tables]

        Depending on the task classification parsed during the sequence, map the payload to one of these execution
        structures:

        Blueprint A: Local Automation & Systems Operations

        - Risk Profiling: Enumerate environment dependencies or state impacts.
        - Implementation Block: Production-grade code or configuration values.
        - State Verification: A machine-executable verification string (e.g., dry-run flag) to prove success.

        Blueprint B: Data Streams & Algorithmic Analysis

        - Schema Validation: Explicit safety check for missing elements, null responses, or noise.
        - Compute Matrix: Step-by-step logic calculating intermediate vectors before writing final fields.
        - Fallback Logic: Precise execution paths if input data streams fail schema validation.

        Blueprint C: Multi-Agent Choreography & State Handoffs

        - Constitution Compliance: Immediate boundary verification before spawning worker threads.
        - State Payload Specification: Strict definitions of variables passed across isolation boundaries.
        - Execution Telemetry JSON:

        ```json
        {
          "plan_status": "success | failed",
          "steps_executed": [],
          "resulting_state": {},
          "telemetry": ""
        }
        ```

      </desired_output>
    </problem_structure>
    ```

  </desired_output>
</problem_structure>
