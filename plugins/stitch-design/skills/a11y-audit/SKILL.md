---
name: a11y-audit
description: Focused accessibility audit against WCAG 2.2 AA standards. Checks ARIA best practices, semantic HTML, focus management, color contrast, keyboard navigation, skip links, alt text, form labels, and error announcements.
---

# Accessibility Audit Skill

Deep accessibility audit focused exclusively on WCAG 2.2 AA conformance. This skill
provides more detailed a11y analysis than the broader `ux-review` skill.

## Arguments

- `$ARGUMENTS` -- File or directory to audit (default: current working directory).

---

## Phase 1: File Discovery

Scan for auditable files:

```text
*.html, *.htm, *.jsx, *.tsx, *.vue, *.svelte, *.css, *.scss
```

Skip `node_modules/`, `dist/`, `build/`, `.next/`, and vendor directories.

---

## Phase 2: WCAG 2.2 AA Checks

Organize checks by WCAG principle.

### Perceivable (WCAG 1.x)

| Criterion | Check | How |
|-----------|-------|-----|
| 1.1.1 Non-text Content | All `<img>` have `alt` attribute | Grep for `<img` without `alt` |
| 1.1.1 Non-text Content | All `<svg>` have accessible name | Check for `aria-label`, `aria-labelledby`, or `<title>` |
| 1.2.2 Captions | `<video>` has `<track kind="captions">` | Grep for `<video` without track |
| 1.3.1 Info and Relationships | Heading hierarchy is sequential | Parse h1-h6 order per page |
| 1.3.1 Info and Relationships | Tables have `<th>` and `scope` | Grep for `<table` without `<th` |
| 1.3.5 Input Purpose | Inputs have `autocomplete` where applicable | Check login/address forms |
| 1.4.3 Contrast (Minimum) | Text has 4.5:1 contrast ratio | Flag hardcoded color pairs to review |
| 1.4.4 Resize Text | No `font-size` in `px` below 12px | Grep CSS for small px values |
| 1.4.10 Reflow | No horizontal scroll at 320px viewport | Check for fixed widths > 320px |
| 1.4.11 Non-text Contrast | UI components have 3:1 contrast | Flag border/outline colors for review |
| 1.4.12 Text Spacing | No `!important` on line-height/letter-spacing | Grep CSS |
| 1.4.13 Content on Hover | Tooltips are dismissible and persistent | Check tooltip implementations |

### Operable (WCAG 2.x)

| Criterion | Check | How |
|-----------|-------|-----|
| 2.1.1 Keyboard | All interactive elements are keyboard-accessible | Detect `onClick` without `onKeyDown` or `role="button"` |
| 2.1.2 No Keyboard Trap | Focus is not trapped (except modals) | Check for `tabindex="-1"` patterns |
| 2.4.1 Bypass Blocks | Skip-to-content link present | Check first `<a>` or `<button>` in `<body>` |
| 2.4.2 Page Titled | `<title>` element is present and descriptive | Grep `<title>` |
| 2.4.3 Focus Order | `tabindex` values are 0 or -1 (no positive values) | Grep for `tabindex="[1-9]"` |
| 2.4.4 Link Purpose | Links have descriptive text (no bare "click here") | Grep for generic link text |
| 2.4.7 Focus Visible | `:focus` or `:focus-visible` styles defined | Grep CSS for focus styles |
| 2.5.3 Label in Name | Visible label matches accessible name | Flag `aria-label` that differs from visible text |
| 2.5.8 Target Size | Interactive elements >= 24x24px (AA) | Flag elements with small explicit sizes |

### Understandable (WCAG 3.x)

| Criterion | Check | How |
|-----------|-------|-----|
| 3.1.1 Language | `<html>` has `lang` attribute | Grep for `<html` without `lang` |
| 3.2.2 On Input | No unexpected context changes on input | Flag `onChange` navigation |
| 3.3.1 Error Identification | Form errors are announced | Check for `aria-live`, `role="alert"`, `aria-invalid` |
| 3.3.2 Labels | All form controls have labels | Check `<label>`, `aria-label`, `aria-labelledby` |

### Robust (WCAG 4.x)

| Criterion | Check | How |
|-----------|-------|-----|
| 4.1.2 Name, Role, Value | Custom widgets have correct ARIA roles | Check custom components for `role`, `aria-*` |
| 4.1.3 Status Messages | Status updates use `aria-live` | Grep for toast/notification patterns |

---

## Phase 3: ARIA Best Practices

Beyond WCAG, check for common ARIA misuse:

| Issue | Pattern | Severity |
|-------|---------|----------|
| Redundant roles | `<button role="button">` | Low |
| Invalid role values | `role="custom-thing"` | High |
| Missing required attrs | `role="checkbox"` without `aria-checked` | High |
| `aria-hidden` on focusable | `aria-hidden="true"` with `tabindex="0"` | High |
| Orphan `aria-describedby` | `aria-describedby` pointing to nonexistent ID | Medium |

---

## Output Format

```markdown
## Accessibility Audit Report

**Target**: {path}
**Standard**: WCAG 2.2 AA
**Files scanned**: {count}
**Timestamp**: {ISO-8601}

### Conformance Summary

| Principle | Checks | Pass | Fail | N/A |
|-----------|--------|------|------|-----|
| 1. Perceivable | 12 | 9 | 2 | 1 |
| 2. Operable | 9 | 7 | 1 | 1 |
| 3. Understandable | 4 | 4 | 0 | 0 |
| 4. Robust | 3 | 2 | 1 | 0 |
| ARIA Best Practices | 5 | 4 | 1 | 0 |

### Violations

| WCAG | Severity | File | Line | Issue | Fix |
|------|----------|------|------|-------|-----|
| 1.1.1 | High | Card.tsx | 15 | Image missing alt text | Add descriptive `alt` attribute |
| 2.1.1 | High | Menu.tsx | 42 | `<div onClick>` not keyboard accessible | Use `<button>` or add `onKeyDown` + `role` |
| 2.4.3 | Medium | Nav.tsx | 8 | `tabindex="5"` creates unexpected focus order | Use `tabindex="0"` instead |

### Verdict

- **AA Conformant**: All checks pass
- **Partial**: Some violations found but core navigation works
- **Non-conformant**: Critical violations blocking keyboard/screen reader access
```

---

## Safety Checks

- Read-only analysis -- never modify source files
- Skip minified and bundled files
- Note checks that require manual verification (color contrast, cognitive load)
- Cap findings at 100 per file

## Sub-agent dispatch

Follow the bundled `sub-agent-dispatch.md` selection rules. Dispatches use the
pinned `sonnet` model.

When ≥3 target files or pages need auditing, dispatch one sub-agent per file/page to audit it, then merge
findings; below that, audit inline. Pick the mechanism per the shared Sub-Agent Selection Rules
use native sub-agents when available, or `manifest-workspace:parallel-agent` /
inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.
