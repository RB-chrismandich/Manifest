# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-06-08 - Rich Terminal UI Persistence

**Learning:** By default, rich `Progress` and `Live` instances leave their
final output in the terminal scrollback, causing unnecessary clutter during
repeated script executions.
**Action:** Instantiate these UI components with `transient=True` to
automatically clear them upon completion, keeping the user's terminal history
clean.

## 2026-06-10 - CLI Spinner Terminal UX

**Learning:** In bash scripts, hiding the cursor for a cleaner spinner requires
careful lifecycle management. Relying solely on an `EXIT` trap is insufficient,
as `SIGINT` (Ctrl+C) bypasses it, leaving the user with a broken (invisible)
cursor. Output buffering is also crucial to prevent standard output from
clobbering the spinner line.
**Action:** Always buffer output to a temp file, print it only on error, and
trap `INT`, `TERM`, and `EXIT` to ensure `tput cnorm` restores the terminal
cursor regardless of how the script terminates.

## 2024-06-16 - Add rich styling to status in CLI table output

**Learning:** The CLI tool outputs the agent status ("complete" / "failed") but doesn't utilize `rich` color tags
for status text within the summary table in `orchestrator.py`, leading to poor visual contrast.
**Action:** Enhance the `table.add_row` call to include color tags for the status string.

## 2026-06-19 - Semantic Colors for CLI Validation States

**Learning:** Binary green/red schemes in CLI outputs fail to communicate
intermediate states like warnings or manual review requests, confusing users
when a process didn't fully fail but isn't fully approved.
**Action:** Use a three-color semantic system (green=success, yellow=warning/review,
red=error/blocked) for validation verdicts to provide nuanced visual feedback.

## 2026-06-21 - Semantic Colors for CLI States

**Learning:** In CLI status tables (like `check_status.sh`), using a red cross (`✗`) for intentionally disabled
services communicates a false error state, increasing cognitive overload. A three-color semantic system
(green=success/enabled, yellow=warning/inactive/disabled, red=error/blocked) provides nuanced visual
feedback and accurately reflects intermediate, non-error states.
**Action:** When designing or refactoring CLI outputs, explicitly reserve red (`RED`) for critical failures
or blocked states, and use yellow (`YELLOW`) with an appropriate icon (like `○` or `⚠`) for optional,
inactive, or intentionally disabled components.

## 2026-06-22 - Semantic Errors in CLI Logs

**Learning:** When errors are printed to the terminal without distinct red color formatting, they easily blend
in with standard text, reducing the user's ability to quickly spot failures in busy output streams.
**Action:** Consistently apply semantic red styling (`\033[0;31m`) to standard error messages in bash
scripts to ensure they stand out visually and draw immediate attention.

## 2026-06-23 - Semantic Icons in Markdown Reports

**Learning:** When generating markdown summaries, using a failure icon (like a cross) for non-active or disabled
states causes confusion. A binary pass/fail schema fails to represent intermediate neutral states correctly.
**Action:** Always use a three-state semantic system (e.g., success, error, and neutral/disabled) for status icons
in generated reports.

## 2026-06-25 - Missing Optional CLIs Representation

**Learning:** Missing optional CLIs (like Claude and Gemini when disabled or uninstalled) should not be
represented as critical errors with a red cross (`✗`). This creates a false error state and panic for users.
**Action:** Use a neutral yellow circle (`○`) and hide installation hints behind verbose flags for optional
components that are not strictly required for the core application to function.

## 2026-07-06 - Semantic Optional Files

**Learning:** When displaying missing optional files in CLI scripts (like `research.md`), using a red cross (`✗`)
creates a false sense of error for users. A missing optional file is an expected, neutral state.
**Action:** Use a yellow circle (`○`) for missing optional files, reserving the red cross strictly for required
files or critical errors.

## 2026-07-23 - Warning symbols for check_optional_file

**Learning:** By modifying `check_optional_file` and `check_optional_dir` in bash utilities to use
semantic yellow circle icons (○) or warning icons for optional files instead of a red cross or
standard checkmark, we clarify to the user that missing optional configurations are neutral,
inactive, or non-blocking, thus reducing false-error anxiety during status commands.
**Action:** Use variant bash functions like `check_optional_file` rather than overriding base
`check_file` behavior to ensure global required errors aren't inadvertently suppressed, applying
standard semantic formatting for DX terminal outputs.

## 2026-07-29 - Semantic Colors for CLI Standard Errors

**Learning:** When errors are printed to the terminal without distinct red color
formatting, they easily blend in with standard text, reducing the user's ability
to quickly spot failures in busy output streams.
**Action:** Consistently apply semantic red styling (`\033[0;31m`) to standard
error messages in bash scripts to ensure they stand out visually and draw
immediate attention.
