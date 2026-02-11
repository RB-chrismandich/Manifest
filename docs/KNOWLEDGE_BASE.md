# Knowledge Base — Captured Learnings & Best Practices

> A living document of patterns, antipatterns, tool discoveries, and configuration
> insights captured during development with the Manifest orchestration framework.

**Last Updated**: 2026-02-11T22:00:00-08:00
**Source**: `configs/claude/config/knowledge_base.yml` (machine-readable), this file (human-readable)
**Managed by**: `learning-loop` skill, `antipattern-detect` skill

---

## Overview

This knowledge base serves as the human-readable companion to
`configs/claude/config/knowledge_base.yml` (the machine-readable source of truth).
Entries are captured automatically by the `learning-loop` skill and analyzed by the
`antipattern-detect` skill. Both skills write structured records to the YAML config
and surface summaries here for team reference.

## How to Contribute

| Action | Command | Description |
|--------|---------|-------------|
| Capture a new learning | `/learning-loop` | Records a pattern, tool discovery, or config insight |
| Detect antipatterns | `/antipattern-detect` | Analyzes recent code for known antipatterns |
| Manual entry | Edit this file + `knowledge_base.yml` | Add both human-readable and machine-readable records |

When adding entries manually, ensure both this document **and**
`configs/claude/config/knowledge_base.yml` are updated to stay in sync.

### Categories

| Category | Description | Example |
|----------|-------------|---------|
| Pattern | Recommended coding patterns | "Use ruff instead of flake8+black+isort" |
| Antipattern | Detected issues to avoid | "Bare except clauses hide real errors" |
| Tool Discovery | New/better tooling | "golangci-lint replaces individual Go linters" |
| Config Insight | Configuration tips | "ESLint flat config requires eslint.config.js" |

### Confidence Levels

- **High**: Confirmed across multiple occurrences or from authoritative sources
- **Medium**: Observed once with strong evidence
- **Low**: Preliminary observation, needs more data

---

## Patterns

Recommended patterns discovered through development and cross-agent consensus.

| ID | Language | Title | Category | Description |
|----|----------|-------|----------|-------------|
| | | | | |

---

## Antipatterns

Detected antipatterns that should be avoided. Each entry includes the context in
which it was found and the recommended alternative.

| ID | Language | Title | Category | Severity | Occurrences | Description | Alternative |
|----|----------|-------|----------|----------|-------------|-------------|-------------|
| ANTI-001 | bash | Unquoted variable expansion in shell commands | security | high | 8 | User-controlled values passed to `bash -c`, `eval`, or unquoted in command strings cause command injection (CWE-78) | Always quote variables; use arrays for command arguments; avoid `bash -c` with interpolated strings |
| ANTI-002 | bash | Insecure temporary file/directory creation | security | high | 3 | Using predictable temp paths or `mkdir` without `mktemp` enables symlink attacks (CWE-377) | Always use `mktemp -d` with templates; set `umask 0077`; use trap for cleanup |
| ANTI-003 | yaml | Stale file-path references in pre-commit hooks | architecture | medium | 3 | Local pre-commit hooks reference old directory paths after refactors, causing hooks to silently never match any files | Update all path patterns in `.pre-commit-config.yaml` as part of every directory restructuring; add a CI check that validates hook file patterns match existing paths |
| ANTI-004 | markdown | Markdown table column style violations (MD060) | naming | low | 902 | Tables use compact pipe style (no spaces around pipes in separator rows) which violates markdownlint MD060; not auto-fixable by `--fix` | Add `"MD060": false` to `.markdownlintrc` if compact style is intentional, or reformat all table separator rows to use spaced style |
| ANTI-005 | markdown | Documentation path drift after directory moves | architecture | medium | 9+ | After moving files to new directories, documentation references to old paths remain stale across multiple files | Create a checklist or script that greps for old path prefixes after any directory restructuring commit |

### ANTI-001: Unquoted Variable Expansion in Shell Commands

- **Category**: security
- **Language**: bash
- **Severity**: high
- **Occurrences**: 8
- **First seen**: 2026-01-01 (estimated from git history)
- **Last seen**: 2026-02-11

**Problem**: User-controlled or external values are interpolated directly into
`bash -c` strings, `eval` calls, or unquoted command arguments. This allows an
attacker (or an unexpected input value) to inject arbitrary shell commands
(CWE-78). This vulnerability has been discovered and fixed 8 separate times
across parallel_agent.sh, bootstrap config parsing, API key setup, and
CursorAgent integration.

**Example** (bad):

```bash
bash -c "process_file $USER_INPUT"
```

**Fix** (good):

```bash
# Use arrays and proper quoting
local -a cmd=(process_file "$USER_INPUT")
"${cmd[@]}"
```

**Detection**: shellcheck SC2086 (double-quote to prevent globbing/splitting),
SC2116 (useless echo), manual review of `bash -c` and `eval` usage. Run
`grep -rn 'bash -c\|eval ' scripts/` to audit.

### ANTI-002: Insecure Temporary File/Directory Creation

- **Category**: security
- **Language**: bash
- **Severity**: high
- **Occurrences**: 3
- **First seen**: 2026-01-15 (estimated from git history)
- **Last seen**: 2026-02-05

**Problem**: Temporary directories or files created using predictable paths
(e.g., `/tmp/myapp_output`) without `mktemp` are vulnerable to symlink attacks
and race conditions (CWE-377). This was fixed three times in
`parallel_agent.sh`, each time for a different code path that created temp
artifacts.

**Example** (bad):

```bash
OUTPUT_DIR="/tmp/agent_outputs"
mkdir -p "$OUTPUT_DIR"
```

**Fix** (good):

```bash
umask 0077
OUTPUT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent_outputs.XXXXXX")
trap 'rm -rf "$OUTPUT_DIR"' EXIT
```

**Detection**: shellcheck SC2086, grep for hardcoded `/tmp/` paths without
`mktemp`. The pre-commit hook `detect-private-key` catches secrets but not
insecure temp usage; consider adding a custom hook.

### ANTI-003: Stale File-Path References in Pre-commit Hooks

- **Category**: architecture
- **Language**: yaml
- **Severity**: medium
- **Occurrences**: 3
- **First seen**: 2026-02-11
- **Last seen**: 2026-02-11

**Problem**: Three local hooks in `.pre-commit-config.yaml` used `files:` regex
patterns that referenced `^\.claude/` paths, but the directory was renamed to
`configs/claude/` in commit `e48d369`. These hooks silently matched zero files
and never executed. **Fixed**: paths updated and `check-command-frontmatter`
replaced with `check-stale-repo-paths` in the same session.

**Detection**: After any directory move/rename, run
`grep -n 'files:' .pre-commit-config.yaml` and verify each pattern matches at
least one file in the repo. The new `check-stale-repo-paths` hook automates
this for documentation files.

### ANTI-004: Markdown Table Column Style Violations (MD060)

- **Category**: naming
- **Language**: markdown
- **Severity**: low
- **Occurrences**: 902
- **First seen**: 2026-01-01 (estimated)
- **Last seen**: 2026-02-11

**Problem**: 902 markdownlint MD060 violations across 48 markdown files. The
rule requires consistent spacing around pipe characters in table separator
rows. The project's `.markdownlintrc` does not disable this rule, but
`markdownlint --fix` cannot auto-fix MD060. This means every `pre-commit run`
reports these violations (or would, if run in strict mode) but they cannot be
resolved automatically.

**Example** (bad):

```markdown
| Column A | Column B |
|----------|----------|
```

**Fix** (good):

```markdown
| Column A | Column B |
| -------- | -------- |
```

Alternatively, disable the rule if compact style is preferred:

```json
{
  "MD060": false
}
```

**Detection**: `markdownlint --disable MD013 MD033 MD041 -- '**/*.md'`; filter
for MD060. Decision needed: either reformat all 48 files or disable the rule.

### ANTI-005: Documentation Path Drift After Directory Restructuring

- **Category**: architecture
- **Language**: markdown
- **Severity**: medium
- **Occurrences**: 9+
- **First seen**: 2026-02-11
- **Last seen**: 2026-02-11

**Problem**: When directories are renamed or restructured (e.g., `.claude/` to
`configs/claude/`), documentation files that reference the old paths become
stale. Commit `0e42667` fixed 9 stale paths across 4 docs files, but the
`.pre-commit-config.yaml` was missed entirely (see ANTI-003). This pattern
recurs because there is no automated check for path references in docs.

**Example** (bad):

```markdown
See [command config](../configs/claude/config/command_config.yml) for details.
```

**Fix** (good):

```markdown
See [command config](configs/claude/config/command_config.yml) for details.
```

**Detection**: After any directory rename, run
`grep -rn 'old_directory_name/' docs/ *.md .pre-commit-config.yaml` to find
stale references. Consider adding a CI job that checks for broken relative
links in markdown files (e.g., `markdown-link-check`).

---

## Tool Discoveries

New or better tooling identified during development.

| ID | Tool | Replaces | Category | Description |
|----|------|----------|----------|-------------|
| TD-001 | ruff | flake8, isort, pycodestyle | python-linting | Ruff is a single, fast Rust-based linter and formatter that replaces flake8, isort, pycodestyle, and several other Python tools. Significantly faster and supports auto-fix for most rules. |

---

## Configuration Insights

Lessons learned about configuration, thresholds, and environment setup.

| ID | Area | Title | Description |
|----|------|-------|-------------|
| CI-001 | markdownlint | MD060 rule requires explicit decision | The MD060 (table-column-style) rule is enabled by default and triggers 902 violations across 48 files. Since `--fix` cannot auto-fix this rule, either disable it in `.markdownlintrc` or reformat all tables. A decision should be made and documented. |
| CI-002 | pre-commit | Local hook file patterns must be updated on directory moves | Pre-commit local hooks use `files:` regex patterns that are not validated against the actual file tree. After directory restructuring, hooks can silently stop matching. Validate patterns after every rename. |

---

## References

- **Machine-readable source**: [`configs/claude/config/knowledge_base.yml`](../configs/claude/config/knowledge_base.yml)
- **Learning loop skill**: [`configs/claude/skills/learning-loop/`](../configs/claude/skills/learning-loop/)
- **Antipattern detection skill**: [`configs/claude/skills/antipattern-detect/`](../configs/claude/skills/antipattern-detect/)
- **Metrics dashboard**: [METRICS.md](METRICS.md)
- **Orchestration guide**: [`.claude/CLAUDE.md`](../.claude/CLAUDE.md)
