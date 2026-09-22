# Features

> What Manifest does, feature by feature.

**Last Updated**: 2026-09-12

## Features

- **Native task batches**: OMP batches independent units through `task` and
  `hub`; Claude Code uses discovered native Agents. The parent validates
  attributed evidence and aggregates results.
- **Clear degraded mode**: If the current host's native dispatch is unavailable,
  ordinary interactive work proceeds inline and reports `DEGRADED`; explicitly
  requested external backend work remains parent-owned dispatcher work.
- **Native validation guidance**: Tier 1 covers security, error handling, and
  breaking changes; Tier 2 covers quality concerns.
- **Single-provider model policy**: `model_policy.yml` gives retained
  noninteractive tools provider order, model tiers, CLI invocation shapes, and
  bounded fallback without becoming an interactive dispatcher.
- **Cross-platform configuration**: Shared guides and skills support Claude
  Code, Cursor, Gemini CLI, Codex CLI, Antigravity, and opt-in Devin on macOS
  and supported Linux distributions.
- **Unified Label Management**: A canonical registry syncs labels across
  GitHub, GitLab, and Linear.
- **Autonomous Issue Development** (`/issue-dev-auto`): Picks the next
  `auto-dev` issue, implements it test-first, and opens a PR for review.
- **Repo Hygiene Sweep** (`/repo-clean`): Review-then-confirm cleanup of open
  PRs and stale, merged, or gone branches.
- **Issue-Linking Git Hooks** (`/issue-sync-pr`, `/issue-sync-commit`):
  fail-open hooks that synchronize linked issue status and back-links.
- **Plugin Bundles**: Skills ship in plugin bundles and refresh with
  `claude plugin update <bundle>@manifest`.
- **SkillClaw Integration** (opt-in): Captures sessions and proposes evolved
  skills in a review PR without directly changing the source of truth.
- **Proton Pass Credential Retrieval** (`/pass-cli`): Retrieves credentials
  without writing them to repository files.
- **Stitch Design Skills**: Design, code-generation, and design-system
  workflows backed by the Stitch MCP server.

---

---

[← Manifest README](../README.md)
