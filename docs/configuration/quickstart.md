# Configuration Quickstart

> The settings most users change first.

**Last Updated**: 2026-09-12

1. Use `services.yml` to enable only the supported coding harnesses you use.
2. Review `command_config.yml` when a skill needs an OMP task-batch policy.
3. Set `model_policy.yml` only for retained noninteractive single-provider
   integrations.
4. Leave validation tiers in `validation_criteria.yml` unless the command has a
   documented safety reason for an override.

Interactive sub-agent work is OMP-native: send all ready independent units in
one `task` call, use `hub` only for coordination, and validate evidence in the
parent. If task dispatch is unavailable, work inline and report `DEGRADED`.

---

[← Configuration](README.md)
