---
name: false-green-check-audit
description: Use when writing or reviewing a health-check, status, validation, or CI gate that can SKIP verifying something (missing credential, unsupported provider, absent tool) — ensure a skipped/unverifiable check never renders as a green pass, and add a verification path through the credential or channel the user actually uses (e.g. an OAuth CLI, not an assumed API key).
---
# Audit Checks for False-Green (Skip ≠ Pass)

When "it read as green but was actually broken," the failure was the checker that couldn't see the break, not just the
broken thing. Close the blind spot, don't only fix the instance.

1. **Find every degrade-instead-of-verify path.** Grep the checker for `SKIPPED`, `UNSUPPORTED`, "no credentials", `||
   true`, early `return 0` on a missing precondition. Each is a candidate false-green: the thing was never checked,
   yet the summary may count it as fine.
2. **Separate "verified OK" from "could not verify" in the summary.** The overall/green line is green only when checks
   actually passed; unverifiable checks render as a distinct warn/info state (e.g. "N unverified — run X to verify")
   with the remediation, never folded into the pass count. Count and surface every non-OK class (including
   always-UNSUPPORTED ones) — a reviewer or bot will correctly flag a summary that claims "all verified" while some
   checks were skipped.
3. **Ask why it skipped.** Usually the check assumed one access path — an API key, a specific binary, a network
   listing endpoint — that the real environment lacks because the user authenticates differently (OAuth/subscription
   CLI login, SSO, a proxy). The blind spot is the gap between the assumed path and the real one.
4. **Add verification through the channel the user actually uses.** If the API-key path is unavailable but an
   OAuth-authenticated CLI is on PATH, do a cheap live one-shot through that CLI (tiny call, `--version`, a
   model/identifier probe) and classify the result (reachable / not-found→stale / unclassifiable→still skip). Gate the
   live path behind an opt-in flag if it costs money or latency.
5. **Harden the probe loop.** Redirect `</dev/null` so the probed CLI doesn't drain the iteration's stdin and check
   only the first item (see shell-audit-errexit).
6. **Regression-test the honesty property.** Assert that with the precondition absent, the summary does NOT print the
   green "all good" line, and that an unverifiable item is reported as unverified — not as pass.
