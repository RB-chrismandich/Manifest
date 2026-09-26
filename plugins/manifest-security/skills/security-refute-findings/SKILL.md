---
name: security-refute-findings
description: "Deprecated alias for security-triage-findings — adversarially verify candidate security findings via attacker/victim analysis and diff-anchoring. Invoke security-triage-findings directly; this name forwards to it and will be removed."
---
# Security Finding Refutation (deprecated alias)

**Deprecated.** This skill is a compatibility alias kept during the migration
window. Invoke `manifest-security:security-triage-findings` directly — it is the
canonical adversarial refutation skill and now carries the full gate catalog,
including the removed/delegated-control analysis this alias used to describe
inline. Its contract lives beside this file at
[`../security-triage-findings/SKILL.md`](../security-triage-findings/SKILL.md),
so the link resolves inside an installed bundle.

## Contract preserved by this alias

- **Arguments**: candidate findings, each carrying an index, `scope`
  (`in_diff`/`off_diff`), and cited evidence — identical to
  `security-triage-findings`.
- **Output**: two lists — `survived` (the indices that could not be refuted)
  and `refuted` (`{idx, reason}` records citing `file:line` evidence). An
  empty `survived` list is a valid, common outcome.

Run the canonical skill's procedure against these arguments and return its
output verbatim; this alias does not reimplement the refutation gates.

## Sub-agent dispatch

Follow the [finding refutation dispatch rules](references/security-refute-findings-dispatch.md)
and the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
When at least three candidate findings need refutation, assign one adversarial
`security-reviewer` unit per finding through the current host's native mechanism
and request the strongest supported native model. Each child returns a concrete
verdict with cited evidence for only its assigned finding; the parent applies
the canonical refutation rules directly. Below the threshold, refute inline.
