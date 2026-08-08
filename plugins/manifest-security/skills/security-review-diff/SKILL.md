---
name: security-review-diff
description: Use when asked to review a change or diff for security vulnerabilities — applies a disciplined source-to-sink method that reports only real findings, not robustness or best-practice nits. To verify/refute an existing candidate list, use security-refute-findings.
---
# Diff Security Review

A focused method for reviewing a code change (unified diff + changed files) for *security* vulnerabilities, distinct
from general code quality. Recurs constantly: the discipline is in what you DON'T report.

1. **Read every changed file in full first.** The diff shows only `+` lines; the vulnerability often lives in the
   unchanged context (the sink, the caller, the validator being bypassed). Resolve the real repo path — provided paths
   like `/home/user/repo/...` are often wrong; fall back to `<cwd>/<relative-path>` or `Glob` for the basename.

2. **Enumerate the new sinks the diff introduces:** filesystem writes, URL/SSRF, shell/exec, SQL, deserialization,
   HTML/template rendering, auth/authz gates, logging of secrets. For each, name it explicitly.

3. **Trace each sink back to a source.** Ask: can attacker-controlled input reach this sink? Distinguish *trusted
   internal data* (config built by your own code, responses from an authenticated upstream API, in-process Python
   objects) from *untrusted-principal input* (request params, third-party feed contents, user files). A
   path-traversal-shaped interpolation fed only by internal config is not a finding.

4. **Apply the security-vs-robustness filter — the core discipline.** Do NOT promote to a finding:
   - Missing rate-limit / politeness throttles (e.g. `min_interval` defaults) — not a security boundary.
   - Broad `except Exception` that is *fail-closed* (treats the dataset as empty, denies) — only fail-*open*
     (default-allow, skipped auth check) is a finding.
   - A transient-failure-abort that's a reliability regression, not a security one.
   - Best-practice/hardening with no concrete source→sink impact.

5. **Check the specific high-value patterns:** parser-differential between a new bulk path and the old per-item path,
   allowlist/gate omission on a sibling code path, removal of a fail-closed validator, new logging of PII/secrets, and
   (for LLM/agent code) indirect-prompt-injection where model output flows into a path or command.

6. **Return only genuine source→sink findings with an effective security impact.** If none, return an empty findings
   list and state plainly why each candidate was rejected (trusted source, fail-closed, not a boundary).
