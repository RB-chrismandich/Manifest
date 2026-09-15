# Service Configuration

> Enable coding harnesses and optional integrations.

**Last Updated**: 2026-09-12

`~/.claude/config/services.yml` records enabled harnesses and opt-in components.
Bootstrap writes the file during setup; use `./bootstrap.sh --reconfigure` to
change the selection.

Service state does not control OMP worker selection. Interactive work uses the
harness-native `task` and `hub` contract. Retained noninteractive integrations
resolve a single available provider through `model_policy.yml` and report a
clear route or failure.

---

[← Configuration](README.md)
