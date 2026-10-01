---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
0. The trace shows an actual attempt to inspect Cursor's native inventory (e.g. listing/reading `.cursor/` rules, hooks, agents, or `~/.cursor/`), with the result (found / absent / access denied) reported.
1. Reports each capability (skills, hooks, agents) using the bundle-contract vocabulary: native / generated / imported / degraded / unsupported. Every capability it could NOT verify against native Cursor evidence is reported as `degraded` or explicitly labelled receipt-only/unverified — it must not simply restate the receipt's values as verified fact. `hooks=unsupported` may stand only if justified by Cursor's own capabilities or native evidence, not just by the receipt.
2. Treats `degraded` agents as a finding the user should know about, not as clean.
3. Does not use Claude Code's or another harness's settings (e.g. `~/.claude/settings.json`) as a proxy to judge Cursor.
4. Apart from creating the receipt fixture the user explicitly asked for, makes no writes — the audit itself does not modify the receipt, settings, or plugin files.
