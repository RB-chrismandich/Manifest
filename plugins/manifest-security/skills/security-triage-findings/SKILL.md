---
name: security-triage-findings
description: Adversarially verify candidate security findings before reporting, refuting any where the attacker is the only victim or the diff does not introduce the sink. Canonical refutation-gate catalog, including removed/delegated-control reframing verified by traced call path; security-refute-findings is a deprecated forwarding alias.
---
# Adversarial Security Finding Triage

Use after a vulnerability-finding pass produces candidates, to suppress false positives before they reach the user. The
goal is to DISPROVE each candidate; default to SURVIVES only when you cannot.

1. **Establish attacker and victim first.** For each finding, name who controls the input and who is harmed. REFUTE if
the only victim is the attacker on their own machine/account. KEEP if the attacker is a legitimate user/tenant but
impact reaches other users, shared infra, or server-side resources.

2. **Process `in_diff` candidates before `off_diff`.** Sort so findings whose vulnerable code appears on a `+` line come
first; they use the standard KEEP/REFUTE bar.

3. **Hold `off_diff` candidates to a stricter bar.** You must name the specific `+`/`-` line that ENABLES the off-diff
sink (a removed guard, a new caller, a changed argument). If you cannot cite that enabling line, REFUTE. Also REFUTE any
off_diff candidate whose sink is already covered by a surviving in_diff candidate.

4. **Read the cited file and check for refutation evidence.** REFUTE with `file:line` evidence if any holds:
PRE-EXISTING (the vulnerableCode is unchanged context, not on a `+` line); a sanitizer/validator/authz check prevents
the exploit; the sink is non-dangerous (typed-schema decoder, hardcoded URL, static number/boolean); or NO PRIVILEGE
BOUNDARY (input from env var / CLI arg / dotfile at the same privilege as the writer).

5. **Never apply the no-privilege-boundary refutation to** SSRF/outbound sinks, LLM-agent capability gates,
data-exposure findings (who READS the sink, not who controls input), project-working-directory config (repo author ≠
cloner), or cross-process metadata sources.

6. **Apply the remaining refutation gates** where evidence supports: trusted-header namespace, frontend-only gate with
backend enforcement, delegated validation to a validating upstream, throwaway code under scripts/dev/test dirs,
control-moved-to-library, config/feature-flag gating, protective-control polarity.

7. **Verify delegated- or removed-control reframing by traced call path, not commentary.** A candidate framed as "the
control moved" — validation forwarded to an upstream that checks it, a guard replaced by a dependency documented to
provide it, or a comment/docstring claiming a "removed" control was never functional or is now provided elsewhere —
REFUTES only when you trace the actual call path and confirm it: follow the call into the delegate/library and read
code proving it performs the claimed check, or confirm the pinned dependency version's source contains the control.
An in-file comment asserting the reframing, with no call path you personally traced, is not evidence — evaluate the
candidate as if the comment did not exist. This governs the `delegated validation` and `control-moved-to-library`
gates in step 6.

8. **Do not speculate.** Refute only with cited evidence; otherwise the finding survives.

9. **Return two sets:** `survived` (indices you could not refute) and `refuted` (`{idx, reason}` with the cited evidence
for each). An empty `survived` means every candidate was refuted.

## Sub-agent dispatch

Follow the [finding triage dispatch rules](references/security-triage-findings-dispatch.md)
and the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
When at least three candidate findings need triage, assign one adversarial
`security-reviewer` unit per finding through the current host's native mechanism
and request the strongest supported native model. Each child returns a concrete
verdict with cited evidence for only its assigned finding; the parent applies
the triage rules directly. Below the threshold, triage inline.
