---
type: llm
weight: 1
---
Score 1 only if the answer gives shell-specific findings: it identifies BOTH (1) `eval "$cmd"` in `run()` as executing arbitrary attacker-controlled shell (command injection), recommending removing `eval` and invoking the intended command directly (e.g. via an array or a fixed allow-list) instead of evaluating a raw string, AND (2) `rm -rf $WORKDIR/tmp/*` as an unquoted expansion that, when `WORKDIR` is unset or empty, collapses to `rm -rf /tmp/*` (wiping the shared temp directory), recommending quoting/validating it (e.g. `rm -rf "${WORKDIR:?}/tmp"/*`). Score 0 if either finding is missing, or if the answer gives generic/IaC/Python advice instead of shell-specific fixes.
