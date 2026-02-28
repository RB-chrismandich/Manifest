---
name: performance-check
description: |
  Frontend performance audit: bundle size analysis, Core Web Vitals targets,
  lazy loading, image optimization, caching strategy, code splitting, and
  render-blocking resource detection.
---

# Performance Check Skill

Analyze frontend projects for performance issues using static analysis. Focuses
on Core Web Vitals targets, bundle efficiency, and loading strategy.

## Arguments

- `$ARGUMENTS` -- File or directory to audit (default: current working directory).

---

## Phase 1: Project Detection

Identify the frontend framework and build system:

| Framework        | Indicators                            |
| ---------------- | ------------------------------------- |
| Next.js          | `next.config.*`, `.next/`             |
| Vite             | `vite.config.*`                       |
| Webpack          | `webpack.config.*`                    |
| Create React App | `react-scripts` in `package.json`     |
| Plain HTML       | `*.html` without framework indicators |

---

## Phase 2: Core Web Vitals Static Analysis

Check for patterns that impact each vital metric.

### LCP (Largest Contentful Paint) -- Target: < 2.5s

| Check                 | Pattern                                                  | Severity |
| --------------------- | -------------------------------------------------------- | -------- |
| Hero image priority   | `<img>` in first viewport without `fetchpriority="high"` | High     |
| Preload hints         | No `<link rel="preload">` for LCP resource               | Medium   |
| Server-side rendering | Check for SSR/SSG configuration                          | Medium   |
| Font preloading       | Web fonts without `<link rel="preload" as="font">`       | Medium   |
| Lazy hero image       | Hero/above-fold `<img>` with `loading="lazy"`            | High     |

### FID / INP (Interaction to Next Paint) -- Target: < 100ms / < 200ms

| Check                    | Pattern                                            | Severity |
| ------------------------ | -------------------------------------------------- | -------- |
| Sync scripts in head     | `<script>` without `defer` or `async` in `<head>`  | High     |
| Long tasks               | `document.addEventListener` with heavy computation | Medium   |
| Main thread blocking     | Large synchronous imports in entry files           | Medium   |
| Event handler complexity | Complex inline handlers (`onClick` with awaits)    | Low      |

### CLS (Cumulative Layout Shift) -- Target: < 0.1

| Check            | Pattern                                            | Severity |
| ---------------- | -------------------------------------------------- | -------- |
| Image dimensions | `<img>` without `width` and `height`               | High     |
| Dynamic content  | Injected content above fold without reserved space | Medium   |
| Font display     | Missing `font-display: swap` or `optional`         | Medium   |
| Ad/embed slots   | Iframes without explicit dimensions                | Medium   |
| Aspect ratio     | No `aspect-ratio` CSS for media containers         | Low      |

---

## Phase 3: Bundle Analysis

If build output or config is available, analyze bundle efficiency.

| Check           | What                                                  | Severity |
| --------------- | ----------------------------------------------------- | -------- |
| Bundle size     | Main bundle > 250KB (gzipped)                         | High     |
| Chunk count     | Single monolithic bundle (no code splitting)          | Medium   |
| Tree shaking    | Importing entire libraries (`import _ from 'lodash'`) | High     |
| Duplicate deps  | Same package at multiple versions in lock file        | Medium   |
| Dynamic imports | No `import()` or `React.lazy` usage for routes        | Medium   |
| CSS bundle      | CSS > 100KB without splitting/purging                 | Medium   |

### Common Tree-Shaking Violations

| Pattern                                     | Better Alternative                                      |
| ------------------------------------------- | ------------------------------------------------------- |
| `import _ from 'lodash'`                    | `import debounce from 'lodash/debounce'`                |
| `import * as Icons from '@heroicons/react'` | `import { ArrowIcon } from '@heroicons/react/24/solid'` |
| `import moment from 'moment'`               | `import { format } from 'date-fns'`                     |

---

## Phase 4: Loading Strategy

| Check           | Pattern                                          | Severity |
| --------------- | ------------------------------------------------ | -------- |
| Lazy loading    | Below-fold images without `loading="lazy"`       | Medium   |
| Route splitting | All routes in single bundle                      | High     |
| Prefetching     | No `<link rel="prefetch">` for likely next pages | Low      |
| Service worker  | No SW registration for caching (PWA)             | Low      |
| Compression     | No gzip/brotli config in server or build         | Medium   |

---

## Phase 5: Image Optimization

| Check             | Pattern                                                    | Severity |
| ----------------- | ---------------------------------------------------------- | -------- |
| Modern formats    | Using `.png`/`.jpg` instead of `.webp`/`.avif`             | Medium   |
| Responsive images | No `srcset` or `<picture>` for different viewports         | Medium   |
| Oversized images  | Image files > 500KB in source                              | High     |
| SVG optimization  | SVG files without minification (> 10KB with whitespace)    | Low      |
| Sprite usage      | Many small icon files instead of sprite sheet or icon font | Low      |

---

## Phase 6: Caching Strategy

| Check            | Pattern                                                                 | Severity |
| ---------------- | ----------------------------------------------------------------------- | -------- |
| Cache headers    | Static assets without `Cache-Control` hints in config                   | Medium   |
| Content hashing  | Output filenames without hash (e.g., `bundle.js` vs `bundle.a1b2c3.js`) | High     |
| Immutable assets | Hashed files without `immutable` cache directive                        | Low      |
| API caching      | No SWR/React Query/TanStack Query for data fetching                     | Low      |

---

## Output Format

```markdown
## Performance Check Report

**Target**: {path}
**Framework**: {detected-framework}
**Timestamp**: {ISO-8601}

### Core Web Vitals Risk

| Metric  | Target  | Risk Level | Key Issues                  |
| ------- | ------- | ---------- | --------------------------- |
| LCP     | < 2.5s  | Medium     | Hero image not preloaded    |
| FID/INP | < 200ms | Low        | Scripts properly deferred   |
| CLS     | < 0.1   | High       | 5 images missing dimensions |

### Bundle Analysis

| Metric              | Value          | Status |
| ------------------- | -------------- | ------ |
| Main bundle (est.)  | ~180KB gz      | pass   |
| Code splitting      | Yes (4 chunks) | pass   |
| Tree shaking issues | 2 found        | warn   |

### Findings

| Severity | Category | File       | Line | Issue                      | Impact                 |
| -------- | -------- | ---------- | ---- | -------------------------- | ---------------------- |
| High     | CLS      | Hero.tsx   | 12   | Image missing width/height | Layout shift on load   |
| High     | Bundle   | utils.ts   | 1    | `import _ from 'lodash'`   | +70KB to bundle        |
| Medium   | LCP      | index.html | 8    | No font preload            | Delayed text rendering |

### Verdict

- **PASS**: No high-severity performance issues
- **WARN**: Some optimization opportunities
- **FAIL**: Critical performance issues likely impacting Core Web Vitals
```

---

## Safety Checks

- Read-only analysis -- never modify source files or build output
- Skip `node_modules/`, `dist/`, `build/`, `.next/` contents
- Image size checks use file metadata only (no image processing)
- Cap findings at 50 per category
