# Contract: Hook trigger & installation

How the two skills are wired to fire. Installer: `configs/claude/scripts/install_issue_hooks.sh` (idempotent, `--help`, guarded — Constitution V).

## Primary: unified `PostToolUse` hook (cross-tool)

Installed via the `ai-hooks-integration` mechanism into the active tool's settings (Claude Code `settings.json` `hooks.PostToolUse`, and the Gemini/Cursor equivalents the unified installer manages). One entry per skill, matched on the Bash command text.

| Skill | Matcher (command text) | Action |
|-------|------------------------|--------|
| `pr-issue-sync` | `pr-create` \| `gh pr create` \| `glab mr create` | `issue_support.sh sync-pr <resolved PR number>` |
| `commit-issue-sync` | `git commit` (and `git_ops.sh`-mediated commits) | `issue_support.sh sync-commit HEAD` |

**Payload → engine mapping**: the hook reads the canonical normalized payload (tool, command, exit code). It invokes the engine ONLY when the matched command **succeeded** (a failed `git commit`/`pr create` must not trigger a sync). The dispatcher does **not** parse the PR number out of command stdout (fragile across `gh`/`glab` output formats); it calls `issue_support.sh sync-pr` with no argument and the engine **self-resolves** the current branch's open PR/MR via `pr-view`. If that lookup returns nothing (e.g. detached PR, or `glab mr view` can't resolve an MR for the branch), `sync-pr` degrades to a non-blocking warning (fail-open) — the issue still gets kept current by the next commit hook, or via a manual `sync-pr <N>`.

**Timeout**: the hook entry sets `timeout` ≥ `hook_timeout_seconds`; the engine enforces its own soft timeout inside that budget and always exits 0.

## Secondary: native `post-commit` git hook (opt-in fallback)

For commits made outside an AI tool. `install_issue_hooks.sh --native` writes `.git/hooks/post-commit` calling `issue_support.sh sync-commit HEAD` **only if**:
- no existing `post-commit` hook is present (refuse to clobber; print guidance to merge manually), and
- the installer appends, never overwrites, when it owns an existing managed block (delimited by `# >>> issue-support >>>` / `# <<< issue-support <<<`).

The native hook is intentionally commit-only — there is no native git event for PR creation.

## Idempotency / install guarantees (testable)
| ID | Guarantee | Maps to |
|----|-----------|---------|
| H1 | Re-running the installer does not create duplicate hook entries (settings or native block) | Constitution V, FR-015 |
| H2 | Installer never overwrites a foreign `post-commit` hook | Constitution V |
| H3 | Hooks are opt-in: absent `enabled: true` (or `--enable`), install is a no-op that explains how to enable | FR-015 |
| H4 | A failed underlying git/PR command does NOT fire the engine | (correctness) |
| H5 | Uninstall (`--remove`) cleanly removes both the settings entry and the managed native block | retire/cleanup hygiene |

## Disable / uninstall
`install_issue_hooks.sh --remove` removes the managed entries from settings and the delimited native block, leaving the skills and engine in place (FR-015: disable without removing skills).
