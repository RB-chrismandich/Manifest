---
name: llm-invoke-stdin
description: Use when a script needs to call an LLM/agent CLI (claude -p, gemini -p, agy -p) as a step — pipe the prompt via stdin behind an injectable seam so it is ARG_MAX-safe and testable offline.
---
# Invoke an LLM CLI as a Pipeline Step (stdin seam)

Several pipelines shell out to a headless agent CLI to distill/review content.
The robust, testable shape is the same every time.

1. **Feed the prompt on stdin, not argv.** A distillation/review prompt can be
   hundreds of KB (token_budget × ~4 chars); passing it as a CLI argument risks
   `OSError: Argument list too long` (`ARG_MAX`, ~1 MB on macOS). Pipe it instead:
   ```python
   proc = subprocess.run([cli, "-p"], input=prompt, capture_output=True, text=True)
   ```
   ```bash
   printf '%s' "$prompt" | "$REVIEWER_CLI" -p "<short instruction>"
   ```
   Keep only a short fixed instruction as the argv; the large body goes through the pipe.
2. **Put the CLI behind a named, injectable seam** (env var or function), e.g.
   `SPEC_REVIEW_CLI="${SPEC_REVIEW_CLI:-agy}"` / `run_reviewer()`. Name it for the
   *role* (reviewer), not the vendor, so swapping `gemini`→`agy` is a one-line change.
3. **Make tests inject a stub** through that seam (a fake executable on PATH or an
   injected runner) so the suite never hits the network, the real account, or quota.
4. **Verify the prompt/instruction is model-agnostic** before swapping engines, and
   keep the invocation body unchanged across a swap (behavior-preserving rename).
5. **Fail open / propagate cleanly per context:** a background/hook caller swallows
   reviewer errors (exit 0, never block); an on-demand caller surfaces a clear error.
6. **Smoke-test the real CLI end-to-end once** through the pipeline before shipping
   (see verify-premise) — confirm stdin read, exit 0, no permission hang.
