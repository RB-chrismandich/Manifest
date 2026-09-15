# Using Commands

> Invoke skills and use OMP task batches safely.

**Last Updated**: 2026-09-12

Run `/help <query>` in a supported coding harness to discover skills, then invoke
the selected skill as `/skill-name`.

When a skill has independent work, follow its OMP policy: send all ready units in
one `task` call (at most 32 per wave), assign each child one unit, use `hub` only
for coordination or waiting, and validate returned evidence in the parent. If
`task` is unavailable, execute inline and report `DEGRADED`.

Independent review is risk-based, not size-based: one capable reviewer is the
default, and a second independent review is requested only for a confirmed risk
condition recorded in the report.

Do not invoke provider CLIs as an interactive sub-agent fallback. The retained
single-provider CLI integrations are configured separately through
`model_policy.yml`.

---

[← Getting Started](../GETTING_STARTED.md)
