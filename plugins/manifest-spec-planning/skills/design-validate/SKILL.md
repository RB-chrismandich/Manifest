---
name: design-validate
description: After drafting a design but before writing the spec, validate the debatable/assumption-laden choices with targeted external research
---
# Research-Validate Design Before Spec

Trigger: a design is drafted and the user says "research that this is the best approach", or you are about to
commit a spec that rests on unverified assumptions (an endpoint exists, a single-call alternative beats a two-call
plan, a sidecar is the only path).

1. Extract every load-bearing assumption from the draft: claimed API capabilities, "X is the only way",
   data-source choices, library/tooling picks, rate-limit guesses. List them explicitly.
2. Rank assumptions by blast radius — which ones, if wrong, force a redesign (vs cosmetic). Research the
   high-blast-radius ones first.
3. For each, run a focused query (WebSearch / official docs / Context7 / client source). Prefer primary sources
   (vendor API reference, the actual client code) over blog posts.
4. Look specifically for a SIMPLER path the draft missed — a single endpoint that returns current+forecast in one
   call, a built-in default that removes a subrequest, an existing connector in a sibling repo that already
   documents an undocumented endpoint.
5. For each assumption, record the verdict: confirmed / refuted / improved-alternative-found, with the source URL.
6. Fold confirmed improvements back into the design (e.g. drop a second dependency when one call suffices); for
   refuted assumptions, redesign before writing anything.
7. Note any prerequisite the research surfaced that must be verified at build time (a published status-page slug
   must exist, a token must return data) and mark it build-and-verify.
8. Only then write the spec, and state in it which choices were research-validated and which remain
   build-and-verify, with citations.

## Sub-agent dispatch

This skill uses the shared OMP dispatch contract in
`../../runtime/references/sub-agent-dispatch.md`: submit all ready independent
units in one `task` call, in waves of at most 32; children execute directly and
never redispatch; use `hub` only to coordinate or wait; and the parent validates
and aggregates evidence. If `task` is unavailable, work inline and report
`DEGRADED`.

When ≥3 load-bearing assumptions need validation, dispatch one read-only
research unit per assumption in a single OMP `task` call (in waves of at most
32), using `scout`. Each child researches only its assigned assumption and
never re-dispatches. The parent directly compares and records the cited
evidence; it does not synthesize text overlap. Use `hub` only to coordinate or
wait. If `task` is unavailable, research inline and report `DEGRADED`. Below
the threshold, research inline.
