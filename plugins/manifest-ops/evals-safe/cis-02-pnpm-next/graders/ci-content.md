---
type: llm
focus: {source: file, path: .github/workflows/ci.yml}
weight: 1
---
Assess the workflow. It must install dependencies through pnpm rather than npm or yarn, run TypeScript type checking and the Vitest test suite, and build the Next.js app. Use Node 22 as specified by `.nvmrc`; a matrix limited to unrelated defaults does not pass. Do not add Python, Go, or Terraform jobs. Lockfile-only flags are optional.
