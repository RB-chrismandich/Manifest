# Sub-Agent Dispatch and Selection Rules

> Read-on-demand policy packaged with the Spec Planning bundle. Skills that fan
> work out link here instead of depending on repository configuration or docs.

## Mechanisms

| Mechanism | Use for | Availability |
|-----------|---------|--------------|
| Native Task/Agent sub-agents | Parallel reads, fan-out research, broad audits, and CDDL personas | Claude Code and Cursor |
| `[[skill:manifest-workspace:parallel-agent]]` | Independent cross-model verification of one artifact or decision | Cross-platform |
| `cddl_invoke.py` | One read-only CDDL critic or developer-reviewer through an installed native CLI | Cross-platform |
| Inline work | Trivial work or platforms without a suitable dispatch seam | Cross-platform |

## Selection rules

- Use native sub-agents when at least three independent units exist or the
  owning skill states a lower threshold.
- Below the threshold, work inline; dispatch overhead is not justified.
- Use `[[skill:manifest-workspace:parallel-agent]]` for independent
  cross-model verification, not as a replacement for separated CDDL personas.
- On Gemini, Codex, Antigravity, or Devin, use `cddl_invoke.py` for read-only
  CDDL critics. The developer remains inline because it must edit the tree.
- Never leave an assistant without an executable fallback.

## Model selection

Default native sub-agents to Sonnet unless the owning skill or CDDL charter
requires stronger reasoning. Use Haiku only for mechanical reads or transforms,
and reserve Opus for genuinely difficult correctness or security analysis.

CDDL subprocesses resolve charter tiers through the adjacent
`../config/review_models.json`. Devin is intentionally a no-model provider and
uses `devin --permission-mode auto -p <prompt>`.

## Lifecycle and recursion

- Give each sub-agent one bounded task and the exact artifact paths it needs.
- Await every dispatch and merge its result before advancing the workflow.
- A dispatched sub-agent performs its work directly and does not fan out again.
- Read-only critics never edit code; only the developer role may write.

## Skill authoring convention

Every dispatching skill must state in its own body:

1. The unit of work and dispatch threshold.
2. The native mechanism and cross-platform fallback.
3. The selected model tier or charter-controlled model policy.
4. That child agents execute directly without redispatching.

Keep provider commands, model mappings, and executable order in the bundled
`../config/review_models.json` and `../cddl/cddl_invoke.py`. Do not reference
assistant-home files or repository-only policy documents from installed skills.
