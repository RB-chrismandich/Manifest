# Validation Criteria

> Blocking and advisory concerns used by Manifest skills.

**Last Updated**: 2026-09-12

`~/.claude/config/validation_criteria.yml` defines the validation vocabulary.
Tier 1 is blocking for security, error handling, and breaking changes. Tier 2
is advisory for bugs, performance, maintainability, and tests.

A skill's `command_config.yml` policy selects its tier and may require OMP
independent review. The parent validates each worker's evidence and makes the
final disposition; no text-overlap consensus service is involved.

The unattended verification gate keeps its injected single-reviewer seam and
fails closed on missing, malformed, incomplete, or out-of-range output.

---

[← Configuration](README.md)
