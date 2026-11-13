# Requirements

> Supported platforms, coding harnesses, and retained integration prerequisites.

**Last Updated**: 2026-11-13

Manifest supports macOS and supported Linux distributions. Install the coding
harnesses you intend to use; bootstrap guides their setup and authentication.

Bootstrap requires a verified `uv` installation at `~/.local/bin/uv` for the
Python runtime and guidance hook dependency provisioning. Bootstrap installs
the pinned executable and stops before configuration deployment if verification
fails.

Interactive sub-agent work requires the harness-native OMP `task` and `hub`
capabilities. A harness without `task` executes eligible work inline and reports
`DEGRADED`.

Retained noninteractive integrations require their configured provider CLI. Their
model tiers and invocation shapes come from `model_policy.yml`; no provider SDK
is required by the policy runtime.

---

[← Getting Started](../GETTING_STARTED.md)
