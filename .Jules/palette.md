# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-05-23 - Braille Spinner in CLI
**Learning:** Braille spinners (`⠋⠙⠹...`) provide a smoother, more modern feel than ASCII (`-\|/`) and don't require external dependencies.
**Action:** Use Braille characters for progress indicators in shell scripts, but ensure fallback for non-TTY environments.

## 2026-05-23 - CI Linting Hygiene
**Learning:** Pre-existing lint errors in a repo can block new PRs if CI enforces strict checks on entire directories.
**Action:** When CI fails on files you didn't touch, check if the pipeline runs checks on the whole directory. Fix the blocking errors to unblock your changes, but document them as "fix(ci)" commits.
