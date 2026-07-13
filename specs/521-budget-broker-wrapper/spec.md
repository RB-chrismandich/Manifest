# Feature Specification: BudgetBroker Command Interceptor Wrapper

**Feature Directory**: `specs/521-budget-broker-wrapper`

**Created**: 2026-07-13

**Status**: Planning

> **Note**: Specification only — no `budget_broker` wrapper is wired into `CLIAgent` yet. Session credit fallback remains in `parallel_agent.yml` / `agents/runners.py`.

---

## 1. Context & Purpose
BudgetBroker is an orchestration interceptor that dynamically monitors, manages, and curbs API token spend and model fallback behaviors across parallel LLM agent calls.

In accordance with user requirements, BudgetBroker operates as a local command-line wrapper script that intercepts outgoing CLI calls (e.g. `claude`, `gemini`, `cursor-agent`, `agy`) and dynamically intercepts them to prevent API cost overruns and handle rate limits gracefully.

---

## 2. Requirements & Execution Model

### US1: Local CLI Wrapper Interception
*   **Scenario**: When `CLIAgent` executes a vendor binary, the execution routes through `budget_broker` wrapper.
*   **Behavior**:
    *   Estimates the prompt token count before dispatch.
    *   Validates session spend limits from a local database or tracking file.
    *   Saves token consumption logs in `~/.claude/.agent_outputs/budget.log`.

### US2: Auto-Summary Trigger
*   **Scenario**: BudgetBroker detects that the estimated token count of the prompt history exceeds the budget threshold (e.g. 70% of model limit).
*   **Behavior**:
    *   Triggers the `context-chronicler` to summarize the history and emit a state checkpoint.
    *   Resets the context window for the runner before proceeding.

### US3: Graceful Model Downgrade & Fallback
*   **Scenario**: The vendor binary exits with a quota or rate-limit error.
*   **Behavior**:
    *   BudgetBroker intercepts the failure code, catches the specific error signature, and rewrites the arguments to target the next cheaper fallback model tier.
    *   Retries the execution immediately, transparently returning the result to the caller.
