# Requirements

> Supported platforms, coding harnesses, and retained integration prerequisites.

**Last Updated**: 2026-11-13

Manifest supports macOS and supported Linux distributions. Install the coding
harnesses you intend to use; bootstrap guides their setup and authentication.

Bootstrap requires a verified `uv` installation at `~/.local/bin/uv` for the
locked Python runtime provisioning. Guidance hooks use
`~/.claude/.venv/bin/python3 -I` with the locked runtime's PyYAML; they do not
install dependencies or access the network to launch. Bootstrap installs
the pinned executable and stops before configuration deployment if verification
fails.

Runtime synchronization remains fail-open: a failed sync warns and continues
bootstrap, but guidance execution requires the runtime to be available. A
completed configuration deployment alone does not prove runtime installation.

Interactive sub-agent work requires the harness-native OMP `task` and `hub`
capabilities. A harness without `task` executes eligible work inline and reports
`DEGRADED`.

Retained noninteractive integrations require their configured provider CLI. Their
model tiers and invocation shapes come from `model_policy.yml`; no provider SDK
is required by the policy runtime.

---

[← Getting Started](../GETTING_STARTED.md)
