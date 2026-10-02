---
type: llm
focus: last_message
---
- Reports a server-side request forgery (SSRF) finding.
- Traces the source (`request.args["url"]`, attacker-controlled) to the sink (`requests.get(url)`).
- Names concrete impact reachable from the VPC (e.g. cloud metadata endpoint / internal admin APIs).
- Recommends a concrete fix that validates the RESOLVED destination IP (block private/loopback/link-local/metadata ranges, or a host allowlist) AND handles redirects (`allow_redirects=False`, or re-validate every redirect hop). Validating only the initial URL/hostname string does NOT satisfy this.
- Does NOT pad the report with non-security nits (timeout length, HTML parsing robustness) presented as security findings.
Pass only if all five hold.
