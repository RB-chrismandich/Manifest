# Headless CDDL Invocation API

`cddl_invoke.py` is a separate stdin-driven API for noninteractive callers that
need a single provider invocation. It is **not** an interactive sub-agent
dispatch mechanism and must not be used when OMP `task` is unavailable.

Interactive CDDL uses the OMP workflow in `../SKILL.md`: batch ready personas
with `task`, coordinate only with `hub`, keep children from redispatching, and
have the parent parse verdicts, gate progress, validate, and aggregate. If
`task` is unavailable, perform that workflow inline and report `DEGRADED`.

## Noninteractive invocation

```bash
printf '%s' "$prompt" | python3 <BUNDLE_ROOT>/runtime/cddl/cddl_invoke.py \
  --charter qa-critic
```

`CDDL_INVOKE_PROVIDER` and `CDDL_INVOKE_CLI` configure this API only. Its
provider ordering and role-model resolution are owned by the retained
noninteractive model policy. Callers must handle its output and errors as an
API result; this document does not define an interactive fallback.
