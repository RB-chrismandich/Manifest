---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Says it measures token overhead and response-quality delta caused by Manifest's config across CLI providers (Claude, Gemini CLI, Antigravity CLI).
2. Names the default `workflow` suite (code-review / security-triage / implementation / documentation fixtures scored across none / slim / full context) and the legacy `academic` suite (MMLU, HumanEval, HellaSwag, TruthfulQA).
3. Says it regenerates `docs/TOKEN_BENCHMARK.md` and is monorepo-only (must run from a Manifest checkout).
4. Invents no other suites or outputs.
