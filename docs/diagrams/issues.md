# Issue Management

> Tracker architecture, the sync hooks, and the autonomous developer loop.

**Last Updated**: 2026-08-20

## Issue Management Architecture

Shows the two issue management commands and how they interact with different platforms.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef output fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef platform fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef agent fill:#3b82f6,stroke:#1d4ed8,color:#fff

    USER["User"]:::input

    subgraph "Issue Commands"
        PRIORITIZE["/issue-prioritize<br/>Read-only ranking"]:::process
        TRIAGE["/issue-triage<br/>Backlog hygiene"]:::process
    end

    subgraph "Platform Detection"
        DETECT["git_platform.sh"]:::process
        GH["GitHub (gh)"]:::platform
        GL["GitLab (glab)"]:::platform
        LIN["Linear (linear_ops.sh)"]:::platform
        DETECT --> GH
        DETECT --> GL
        DETECT --> LIN
    end

    subgraph "Issue Prioritization Flow"
        FETCH["Fetch Open Issues"]:::process
        FILTER["Filter Excluded Labels"]:::process
        HEURISTIC["Heuristic Pre-Scoring<br/>Impact × 3 + Urgency × 2<br/>+ Readiness × 2 - Risk"]:::process
        AGENT_REFINE["Agent-Refined Scoring<br/>(top 5-7 only)"]:::agent
        RANK["Rank & Tiebreak"]:::process
        REPORT["Prioritization Report"]:::output
        FETCH --> FILTER --> HEURISTIC --> AGENT_REFINE --> RANK --> REPORT
    end

    subgraph "Issue Triage Flow"
        FETCH_LIN["Fetch Linear Issues"]:::process
        DUP["Duplicate Detection<br/>Fuzzy title matching"]:::process
        STALE["Staleness Detection<br/>File refs + inactivity"]:::process
        PRI_VAL["Priority Validation<br/>Agent consensus"]:::agent
        TRIAGE_REPORT["Triage Report + Actions"]:::output
        FETCH_LIN --> DUP --> STALE --> PRI_VAL --> TRIAGE_REPORT
    end

    USER --> PRIORITIZE
    USER --> TRIAGE
    PRIORITIZE --> DETECT
    GH --> FETCH
    GL --> FETCH
    LIN --> FETCH
    TRIAGE --> FETCH_LIN
    LIN --> FETCH_LIN
```

**Key differences**:

- **issue-prioritize**: Multi-platform (GitHub, GitLab, Linear), read-only, scoring-focused
- **issue-triage**: Linear-only, performs mutations (mark duplicates, close stale), hygiene-focused

**Scoring formula**: `Priority Score = (Impact × 3) + (Urgency × 2) + (Readiness × 2) - Risk`

**Tiebreakers**: bugs > features, unblockers > isolated, planned > unplanned, older > newer

---

## Issue-Linking Hooks (issue-sync-commit / issue-sync-pr)

How the issue-linking hooks keep the GitHub/GitLab issue tracker in sync as commits
land and PRs/MRs open. A single PostToolUse dispatcher (`issue_support_hook.sh`)
classifies the Bash command that just ran and, only on success, routes to the shared
engine (`issue_support.sh`). The engine is **fail-open**: `sync-pr`/`sync-commit`
always exit 0 (bounded by a per-hook `run_with_timeout`), so a git action is never
blocked. An optional native `git post-commit` hook covers commits made outside an
AI tool.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef platform fill:#3b82f6,stroke:#1d4ed8,color:#fff
    classDef skip fill:#e5e7eb,stroke:#6b7280,color:#374151

    INSTALL["install_issue_hooks.sh --enable [--native]<br/>flips tool_policies gate +<br/>writes PostToolUse entry"]:::config

    subgraph "Triggers"
        TOOLUSE["PostToolUse payload (stdin JSON)<br/>after a Bash command"]:::input
        NATIVE["git post-commit hook<br/>(--native, non-AI commits)"]:::input
    end

    HOOK["issue_support_hook.sh<br/>classify command + success"]:::process
    CLASS{"Command class?<br/>(gh/glab/git_ops pr-create<br/>· git commit · none)"}:::decision
    OK{"Tool succeeded?<br/>(is_error / error)"}:::decision

    ENGINE["issue_support.sh<br/>sync-pr N / sync-commit HEAD<br/>(run_with_timeout, fail-open exit 0)"]:::process
    GATE{"tool_policies gate<br/>enabled?"}:::decision

    RESOLVE["resolve_candidates()<br/>branch-prefix · PR/MR body<br/>· commit-message #N refs"]:::process
    OFFER["offer_create()<br/>(no ref → dedup search,<br/>interactive create 'planned')"]:::process

    subgraph "process_issue (per linked #N)"
        TRANSITION["transition_issue<br/>forward-only label advance<br/>planned→in-progress→needs-review"]:::process
        BACKLINK["comment_backlink<br/>(idempotent marker)"]:::process
        CLOSEKW["ensure_closing_keyword<br/>Closes #N (PR only)"]:::process
    end

    GIT_OPS["git_ops.sh → gh / glab"]:::platform
    NOOP["exit 0 (no-op)"]:::skip

    INSTALL -.->|registers| TOOLUSE
    INSTALL -.->|installs| NATIVE
    TOOLUSE --> HOOK
    NATIVE --> ENGINE
    HOOK --> OK
    OK -->|No| NOOP
    OK -->|Yes| CLASS
    CLASS -->|pr| ENGINE
    CLASS -->|commit| ENGINE
    CLASS -->|none| NOOP
    ENGINE --> GATE
    GATE -->|No| NOOP
    GATE -->|Yes| RESOLVE
    RESOLVE -->|refs found| TRANSITION
    RESOLVE -->|none| OFFER
    OFFER --> TRANSITION
    TRANSITION --> BACKLINK --> CLOSEKW
    TRANSITION --> GIT_OPS
    BACKLINK --> GIT_OPS
    CLOSEKW --> GIT_OPS
```

**Trigger → target mapping**:

| Trigger | Hook class | Engine call | Status target | Extra action |
|---------|-----------|-------------|---------------|--------------|
| PR/MR created (`gh`/`glab`/`git_ops.sh pr-create`) | `pr` | `sync-pr N` | `needs-review` | back-link comment + ensure `Closes #N` |
| `git commit` / `git_ops.sh commit` | `commit` | `sync-commit HEAD` | `in-progress` | back-link comment (only advances issues already `planned`) |
| any other Bash command | `none` | — | — | no-op (exit 0) |

**Key properties**:

- **Opt-in & reversible**: `install_issue_hooks.sh --enable/--remove` flips the
  `tool_policies.{issue-sync-pr,issue-sync-commit}.enabled` gate and idempotently
  adds/removes the PostToolUse entry in `~/.claude/settings.json`. `--native` adds a
  guarded `git post-commit` hook (refuses to clobber a pre-existing one).
- **Fail-open**: `sync-pr`/`sync-commit` always exit 0; an internal `__inner`
  re-exec is bounded by `hook_timeout_seconds` (default 5s) so a slow tracker
  degrades to a warning — a re-run heals it (FR-017).
- **Idempotent**: comment back-links carry a `<!-- issue-support:sync v1 ... -->`
  marker; `Closes #N` and label transitions are skipped when already satisfied.
- **Forward-only lifecycle**: `planned → in-progress → needs-review → done` — a
  transition never moves an issue backward (rank check in `transition_issue`).
- **Issue resolution**: a linked issue is found from the branch numeric prefix
  (`017-foo` → `#17`), `#N` refs in the PR/MR body, and commit-message references.

---

## Autonomous Issue Developer (/issue-dev-auto)

How `/issue-dev-auto` (engine: `auto_issue_dev.sh`) develops **exactly one** opted-in
issue per invocation and opens a PR for review — never merging. `/loop` re-runs the
skill with fresh context for the next issue. Selection is opt-in (the `auto-dev`
label) and dependency-aware: issues with unmet `depends on #N` / `blocked by #N`
references are tagged `blocked-dependency` and skipped. Status sync and `Closes #N`
are delegated to the issue-linking hooks (above).

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef success fill:#22c55e,stroke:#166534,color:#fff
    classDef warning fill:#eab308,stroke:#a16207,color:#fff
    classDef stop fill:#e5e7eb,stroke:#6b7280,color:#374151

    LOOP["/loop /issue-dev-auto<br/>(fresh context per run)"]:::input
    PREFLIGHT["Preflight:<br/>install_issue_hooks.sh --enable<br/>+ gh/glab auth check"]:::process

    NEXT["auto_issue_dev.sh next-issue --json<br/>list 'auto-dev' open issues,<br/>drop 'blocked-dependency',<br/>oldest-first"]:::process
    DEPCHECK{"check-deps:<br/>unmet #N refs?"}:::decision
    MARK_DEP["mark-dependency<br/>add 'blocked-dependency' label<br/>+ deduped comment, skip"]:::warning

    READY{"Ready issue<br/>found?"}:::decision
    STOP_EMPTY["Exit 3 → announce<br/>'queue empty', STOP"]:::stop

    BRANCH["git switch -c N-slug<br/>(numeric prefix links #N)"]:::process
    TDD["test-driven-development:<br/>failing test → implement → green"]:::process
    VERIFY{"/project-verify<br/>tests + security pass?"}:::decision

    PR["git_ops.sh pr-create<br/>→ PR hook injects Closes #N,<br/>moves #N to needs-review"]:::success
    DRAFT["pr-create --draft [WIP]<br/>+ mark-blocked (needs-human label)"]:::warning
    SUMMARY["Print one-line summary;<br/>STOP (one issue per run)"]:::stop

    LOOP --> PREFLIGHT --> NEXT
    NEXT --> READY
    READY -->|No| STOP_EMPTY
    READY -->|candidate| DEPCHECK
    DEPCHECK -->|unmet| MARK_DEP
    MARK_DEP --> NEXT
    DEPCHECK -->|all met| BRANCH
    BRANCH --> TDD --> VERIFY
    VERIFY -->|Yes| PR
    VERIFY -->|No / stuck| DRAFT
    PR --> SUMMARY
    DRAFT --> SUMMARY
```

**Engine subcommands** (`auto_issue_dev.sh`, wraps `git_ops.sh`):

| Subcommand | Behavior | Exit |
|------------|----------|------|
| `next-issue [--json]` | First READY `auto-dev` issue (oldest-first, deps met) | `0` ready / `3` none |
| `check-deps <N> [--json]` | Parse `depends on / blocked by / requires / needs #N`; verify each ref is closed/merged | `0` ready / `2` unmet / `1` missing |
| `mark-blocked <N> <reason>` | Add `needs-human` label + deduped comment (fail-open) | `0` |
| `mark-dependency <N> <refs>` | Add `blocked-dependency` label + deduped comment (fail-open) | `0` |

**Invariants**:

- **Never merges** — stops at PR-open; a human reviews and merges.
- **One issue per invocation** — the loop lives in `/loop`, not inside the skill.
- **Opt-in only** — issues without the `auto-dev` label are never touched.
- **On failure** — push WIP, open a **draft** PR (no `Closes`), and `mark-blocked`
  so a human inspects partial work; if there are no commits, skip the draft.
- **Status hand-off** — `planned → in-progress → needs-review` and `Closes #N` are
  applied by the issue-linking hooks, not by this engine (see previous section).

**Labels** (`labels.yml`): `auto-dev` (opt-in selection), `blocked-dependency`
(unmet dependency, excluded until the blocker merges), `needs-human` (auto-dev
could not complete; needs a human).

---

---

[← Architecture Diagrams](README.md)
