# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2024-04-13 - CLI Spinner UX and Log Output Interleaving

**Learning:** When building CLI spinners that wrap background jobs, interleaving
standard output/error from the job with the carriage-return (`\r`) spinner
characters creates severe visual artifacting and screen reader confusion. The
cursor flashing also creates unnecessary visual noise.
**Action:** Always decouple command execution from UI rendering in spinners. Run
the command in a subshell, hide the cursor (`tput civis`), trap `EXIT` to
restore it, and redirect all stdout/stderr to a temp file, only printing the
log output if the background command fails.
