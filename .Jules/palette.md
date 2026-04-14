# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - CLI Spinner UX

**Learning:** Background spinners in CLI scripts easily get corrupted when
stdout or stderr prints text.
**Action:** When implementing CLI spinners with background tasks, use a subshell
to trap exits, redirect output to a temp file (\`mktemp\`), hide the cursor
(\`tput civis\`), and only display logs if the command fails to ensure smooth UX.
