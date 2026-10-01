---
type: llm
focus: {source: file, path: .github/workflows/ci.yml}
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It installs dependencies with pnpm (e.g. pnpm/action-setup + `pnpm install`), not npm/yarn. Lockfile flags such as --frozen-lockfile are neither required nor penalized.
2. It runs typecheck (`tsc --noEmit` / `pnpm typecheck`) and tests (`vitest` / `pnpm test`).
3. It runs `next build` (or `pnpm build`).
4. It uses Node 22 (matching .nvmrc), not an unrelated default matrix only.
5. It contains no Python, Go, or Terraform jobs.
