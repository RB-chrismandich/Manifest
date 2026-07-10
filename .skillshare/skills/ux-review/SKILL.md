---
name: ux-review
description: Automated UX audit covering accessibility (WCAG 2.2), responsive design, performance budgets (Core Web Vitals), progressive enhancement, color contrast, keyboard navigation, and screen reader compatibility.
---

# UX Review Skill

Perform a comprehensive UX audit on HTML, JSX, or TSX files. Checks cover
accessibility, responsive design, performance indicators, and progressive
enhancement patterns.

## Arguments

- `$ARGUMENTS` -- File or directory to audit (default: current working directory).

---

## Phase 1: File Discovery

Find all auditable files in the target path:

```text
*.html, *.htm, *.jsx, *.tsx, *.vue, *.svelte
```

Skip files in `node_modules/`, `dist/`, `build/`, `.next/`, and vendor directories.

---

## Phase 2: Accessibility Checks (WCAG 2.2)

Scan each file for the following patterns:

### Images and Media

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| Alt text | All `<img>` have non-empty `alt` (or `alt=""` for decorative) | High |
| Video captions | `<video>` elements have `<track kind="captions">` | High |
| SVG accessibility | `<svg>` has `role="img"` and `aria-label` or `<title>` | Medium |

### Semantic Structure

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| Heading hierarchy | No skipped heading levels (h1 -> h3 without h2) | High |
| Landmark regions | Page has `<main>`, `<nav>`, `<header>`, `<footer>` | Medium |
| Lists | Navigation groups use `<ul>`/`<ol>` not `<div>` chains | Low |
| Semantic elements | Prefer `<button>` over `<div onClick>` | High |

### Forms and Interactions

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| Form labels | Every `<input>` has associated `<label>` or `aria-label` | High |
| Error announcements | Form errors use `aria-live` or `role="alert"` | Medium |
| Focus management | Modals trap focus; dialogs restore focus on close | High |
| Skip links | Page has skip-to-content link as first focusable element | Medium |

### ARIA

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| Valid ARIA roles | No invalid `role` values | High |
| Required ARIA attrs | Roles have required attributes (e.g., `aria-checked` for `checkbox`) | High |
| No redundant ARIA | No `role="button"` on `<button>` elements | Low |

---

## Phase 3: Responsive Design

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| Viewport meta | `<meta name="viewport" content="width=device-width, initial-scale=1">` | High |
| Touch targets | Interactive elements have min 44x44px tap targets (check CSS classes) | Medium |
| Responsive images | `<img>` uses `srcset` or `<picture>` for responsive loading | Low |
| Media queries | CSS includes breakpoints for mobile/tablet/desktop | Medium |
| No horizontal scroll | No fixed-width containers > 100vw | Medium |

---

## Phase 4: Performance Indicators

Static analysis checks that indicate Core Web Vitals risk:

| Check | Target | What to Look For |
|-------|--------|-----------------|
| LCP risk | < 2.5s | Hero images without `loading="eager"` or `fetchpriority="high"` |
| FID risk | < 100ms | Inline `<script>` in `<head>` without `defer`/`async` |
| CLS risk | < 0.1 | `<img>` / `<video>` without explicit `width`/`height` |
| Font loading | -- | `font-display: swap` or `optional` in `@font-face` |
| Render blocking | -- | CSS `<link>` without `media` attribute in `<head>` |

---

## Phase 5: Progressive Enhancement

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| No-JS fallback | `<noscript>` provides meaningful fallback | Low |
| CSS-only states | `:hover` has corresponding `:focus-visible` | Medium |
| Color independence | Information not conveyed by color alone (icons, patterns, text) | High |
| Reduced motion | `prefers-reduced-motion` media query present | Medium |

---

## Output Format

```markdown
## UX Review Report

**Target**: {path}
**Files scanned**: {count}
**Timestamp**: {ISO-8601}

### Summary

| Category | Pass | Warn | Fail |
|----------|------|------|------|
| Accessibility | 8 | 2 | 1 |
| Responsive | 4 | 1 | 0 |
| Performance | 3 | 2 | 0 |
| Progressive Enhancement | 2 | 1 | 0 |

### Findings

| Severity | Category | File | Line | Issue | Recommendation |
|----------|----------|------|------|-------|----------------|
| High | A11y | Button.tsx | 23 | `<div onClick>` used instead of `<button>` | Use semantic `<button>` element |
| Medium | Responsive | index.html | 5 | Missing viewport meta tag | Add `<meta name="viewport">` |
| Low | Perf | Hero.tsx | 12 | Hero image missing `fetchpriority` | Add `fetchpriority="high"` |

### Verdict

- **PASS**: No high-severity issues
- **WARN**: High-severity issues found but limited scope
- **FAIL**: Multiple high-severity accessibility or performance issues
```

---

## Safety Checks

- Read-only analysis -- never modify source files
- Skip binary files and minified bundles
- Cap findings at 100 per file to avoid context overflow

## Sub-agent dispatch

When ≥3 independent pages or flows need review, dispatch one sub-agent per page/flow to review it, then merge findings;
below that, review inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `parallel_agent.py` / inline
on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.
