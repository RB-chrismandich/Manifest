# Feature Specification: VisualSmoke Agent Harness

**Feature Directory**: `specs/520-visual-smoke-agent`

**Created**: 2026-07-13

**Status**: Planning

---

## 1. Context & Purpose
VisualSmoke is an autonomous, browser-driven end-to-end verification agent harness. It extends Manifest's [smoke test orchestrator](file:///Users/chrismandich/Documents/GitHub/Manifest/specs/363-smoke-test-orchestrator/spec.md) by introducing an LLM-driven interaction mode that verifies visual fidelity, user flow correctness, accessibility, and performance budgets.

Instead of writing brittle CSS/XPath-based tests, an agent describes the visual target or user flow in plain language, and the VisualSmoke runner executes, audits, and validates the UI.

---

## 2. Requirements & User Scenarios

### US1: Visual Regression and UI Auditing
*   **Scenario**: When the CDDL or verification gate runs, the VisualSmoke agent executes the target flow inside a headless Chromium instance driven by Playwright.
*   **Behavior**:
    *   Takes page screenshots at key step transitions.
    *   Compares the current render against a baseline visual template using structural similarity algorithms.
    *   Flags pixel-level regressions, layout drift, and contrast violations.

### US2: WCAG 2.2 AA Accessibility Checks
*   **Scenario**: The runner automatically checks page structure and accessibility features during execution.
*   **Behavior**:
    *   Validates ARIA roles, input labels, color contrast ratios, focus rings, and screen-reader compatibility.
    *   Fails closed (exit code `1`) if critical accessibility gates are violated.

### US3: Performance payload and core web vitals gating
*   **Scenario**: VisualSmoke captures telemetry data during E2E page loads.
*   **Behavior**:
    *   Measures Largest Contentful Paint (LCP), Cumulative Layout Shift (CLS), First Input Delay (FID).
    *   Tracks network payload size (e.g. bundle size limits) and warns on bloated transfers.

---

## 3. Data Formats & Integration

### Test Definition Schema (YAML)
VisualSmoke tests are integrated into the existing `smoke-catalog/<app>.yaml` format using the `ui` type with `mode: agent`:

```yaml
tests:
  - id: verify-login-flow
    tier: Lite
    steps:
      - name: complete-login
        type: ui
        mode: agent
        description: "Log in with test user credentials, click submit, and verify dashboard is visible"
        credentials:
          username: "${env.TEST_USER}"
          password: "${env.TEST_PASSWORD}"
        assertions:
          - visual_match: "dashboard_golden.png"
          - accessibility: "WCAG-AA"
          - perf_budget:
              lcp_ms: 2500
```
