# Model Selection

> Which model a run gets, and how stale pins are detected.

**Last Updated**: 2026-08-20

## Model Selection & Credit Fallback

Automatic model tier selection and graceful fallback when quota/credits are exhausted.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef fallback fill:#eab308,stroke:#a16207,color:#fff
    classDef error fill:#ef4444,stroke:#dc2626,color:#fff

    TASK["Task Type"]:::input

    CLASSIFY{"Task<br/>Classification"}:::decision

    SECURITY["Security Review<br/>(auth, crypto, secrets)"]:::process
    REVIEW["Code Review<br/>(general changes)"]:::process
    ANALYZE["Analysis<br/>(bugs, patterns)"]:::process
    IMPROVE["Improvements<br/>(docs, suggestions)"]:::process
    QUICK["Quick Query<br/>(simple questions)"]:::process

    SEC_MODELS["Cursor: advanced<br/>Claude: opus<br/>Gemini: pro"]:::process
    REV_MODELS["Cursor: flash<br/>Claude: sonnet<br/>Gemini: flash"]:::process
    ANA_MODELS["Cursor: flash<br/>Claude: sonnet<br/>Gemini: flash"]:::process
    IMP_MODELS["Cursor: mini<br/>Claude: haiku<br/>Gemini: flash"]:::process
    QCK_MODELS["Cursor: mini<br/>Claude: haiku<br/>Gemini: flash"]:::process

    EXECUTE["Execute with Selected Models"]:::process

    CHECK_ERROR{"Credit/Quota<br/>Error?"}:::decision

    FALLBACK["Fallback to Cheaper Model"]:::fallback
    RETRY["Retry with Fallback"]:::process

    SUCCESS["Return Results"]:::input
    FAIL["Report Error<br/>(all fallbacks exhausted)"]:::error

    TASK --> CLASSIFY

    CLASSIFY -->|Security| SECURITY
    CLASSIFY -->|Review| REVIEW
    CLASSIFY -->|Analyze| ANALYZE
    CLASSIFY -->|Improve| IMPROVE
    CLASSIFY -->|Quick| QUICK

    SECURITY --> SEC_MODELS
    REVIEW --> REV_MODELS
    ANALYZE --> ANA_MODELS
    IMPROVE --> IMP_MODELS
    QUICK --> QCK_MODELS

    SEC_MODELS --> EXECUTE
    REV_MODELS --> EXECUTE
    ANA_MODELS --> EXECUTE
    IMP_MODELS --> EXECUTE
    QCK_MODELS --> EXECUTE

    EXECUTE --> CHECK_ERROR

    CHECK_ERROR -->|Yes| FALLBACK
    CHECK_ERROR -->|No| SUCCESS

    FALLBACK --> RETRY
    RETRY --> CHECK_ERROR

    FALLBACK -.->|All fallbacks tried| FAIL
```

**Cursor Fallback Chain**:

```text
gpt-5.2 (advanced) → gpt-5.1-codex (flash) → gpt-5.1-codex-mini (mini)
```

**Claude Fallback Chain**:

```text
opus → sonnet → haiku
```

**Gemini Fallback Chain**:

```text
gemini-3-pro-preview (pro) → gemini-3-flash-preview (flash)
```

**Codex Fallback Chain**:

```text
gpt-5.6-sol (advanced) → gpt-5.6-terra (flash) → gpt-5.6-luna (mini)
```

**Error Detection**:
The script parses stderr for patterns:

- "credit", "quota", "rate limit", "insufficient"
- Automatically retries with next cheaper model
- Continues with available agents if one exhausts credits

---

## Model Pin Staleness Check

How `model_check.sh` verifies the `model_tiers` pins in `parallel_agent.yml` against live
provider listings, including the opt-in live-probe mode (`MODEL_CHECK_PROBE=1`) for
OAuth-only machines, and how `check_status.sh` reports the result honestly
(stale / unverified / verified). Warn-only: every failure degrades to SKIPPED and the
exit code is always 0.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef ok fill:#22c55e,stroke:#166534,color:#fff
    classDef warn fill:#eab308,stroke:#a16207,color:#fff
    classDef stale fill:#ef4444,stroke:#dc2626,color:#fff

    CALLER["check_status.sh /<br/>/env-check"]:::input
    MODEL_CHECK["model_check.sh<br/>(reads model_tiers pins)"]:::process

    API_KEY{"API key set?<br/>(claude / gemini)"}:::decision
    LISTING["List models via API<br/>(api.anthropic.com /<br/>generativelanguage)"]:::process
    PROBE_OPT{"MODEL_CHECK_PROBE=1<br/>and CLI installed?"}:::decision
    PROBE["Live one-shot probe per pin<br/>(claude --model X -p /<br/>gemini -m X -p)"]:::process

    AGY_LIST["antigravity: agy models<br/>listing check"]:::process
    UNSUP["cursor / codex:<br/>UNSUPPORTED<br/>(no listing command)"]:::warn

    PIN_OK["OK<br/>(pin verified)"]:::ok
    PIN_STALE["STALE<br/>(pin not served)"]:::stale
    PIN_SKIP["SKIPPED<br/>(no credentials /<br/>probe failed)"]:::warn

    AGG{"check_status.sh<br/>aggregation"}:::decision
    REPORT_STALE["⚠ N stale model pin(s) —<br/>update model_tiers"]:::stale
    REPORT_UNVER["○ N check(s) unverified —<br/>run MODEL_CHECK_PROBE=1<br/>for a live CLI probe"]:::warn
    REPORT_OK["✓ all pins verified"]:::ok

    CALLER --> MODEL_CHECK
    MODEL_CHECK --> API_KEY
    MODEL_CHECK --> AGY_LIST
    MODEL_CHECK --> UNSUP
    API_KEY -->|Yes| LISTING
    API_KEY -->|No| PROBE_OPT
    PROBE_OPT -->|Yes| PROBE
    PROBE_OPT -->|No| PIN_SKIP
    LISTING --> PIN_OK
    LISTING --> PIN_STALE
    PROBE --> PIN_OK
    PROBE --> PIN_STALE
    PROBE --> PIN_SKIP
    AGY_LIST --> PIN_OK
    AGY_LIST --> PIN_STALE

    PIN_OK --> AGG
    PIN_STALE --> AGG
    PIN_SKIP --> AGG
    AGG -->|stale > 0| REPORT_STALE
    AGG -->|skipped > 0| REPORT_UNVER
    AGG -->|all OK| REPORT_OK
```

**Check modes per provider**:

| Provider | With API key | Without API key | Notes |
|----------|--------------|-----------------|-------|
| claude | `GET /v1/models` listing | `MODEL_CHECK_PROBE=1`: one tiny `claude --model <pin> -p` call per pin; else SKIPPED | Probe needed because OAuth-only machines have no key — broken pins would otherwise read as green |
| gemini | `GET /v1beta/models` listing | `MODEL_CHECK_PROBE=1`: one tiny `gemini -m <pin> -p` call per pin; else SKIPPED | Pins UNVERIFIED — the CLI is ineligible on a free-tier account (`IneligibleTierError`, migrate to Antigravity), so the probe cannot reach model selection either |
| antigravity | n/a | `agy models` listing (no key needed) | CLI listing only. Match the **slug** form (`gemini-3.6-flash-low`) — agy ≥1.1.8 lists slugs, not the display labels 1.1.1 emitted |
| cursor | n/a | `cursor-agent --list-models` listing, plus a `MODEL_CHECK_PROBE=1` per-pin fallback | The probe runs inside a throwaway temp dir: `cursor-agent` demands `--trust`, and trusting the operator's cwd is not this script's call |
| codex | n/a | `MODEL_CHECK_PROBE=1` probe only | UNSUPPORTED for listing — the CLI exposes no `models`/`--list-models`, so a probe is the only verification path. Needs `--skip-git-repo-check` |
| devin | n/a | listing only, never probed | `devin models list` is login-gated, and `devin -p` **starts an interactive login** when logged out — so probing it would try to log the operator in. Reports SKIPPED (unpinned by design) |

**Honest reporting** (`check_status.sh`):

- Any STALE pins → yellow warning with count (update `model_tiers`)
- Any SKIPPED checks → "unverified" line suggesting `MODEL_CHECK_PROBE=1 model_check.sh`;
  the green "all pins verified" line never overclaims what was actually checked
- All OK → green "Model pin check complete — all pins verified"

---

---

[← Architecture Diagrams](README.md)
