# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - Better CLI Feedback with Braille and Cursor Management
**Learning:** Using simple ASCII characters for CLI spinners is often jarring and unpolished. Furthermore, displaying noisy command output during a long-running process disrupts the visual flow, while leaving the cursor blinking mid-spinner distracts from the operation.
**Action:** Always implement robust cursor management (`tput civis`/`tput cnorm`), utilize native Bash arrays with Braille characters for smooth animations, and conditionally show stderr outputs *only* on failure by redirecting to a temporary log file. Trap interrupts cleanly to restore terminal state.
