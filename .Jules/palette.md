# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-11 - Braille Spinner Accessibility and Compatibility
**Learning:** Using standard bash parameter expansion `${var:offset:length}` for string slicing counts bytes rather than characters. This breaks multibyte UTF-8 characters like Braille spinners (`\u280b`), causing incorrect rendering. Additionally, CLI loading states must hide the cursor (`tput civis`) to prevent distracting flickering and maintain visual polish, and redirect standard output during background jobs to avoid breaking the inline animation.
**Action:** Always use native bash arrays (e.g., `spin=("\u280b" "\u2819")`) for character-level extraction of multibyte sequences instead of string slicing, and ensure the cursor is properly managed (`tput cnorm` to restore) and output safely captured during animated shell prompts.
