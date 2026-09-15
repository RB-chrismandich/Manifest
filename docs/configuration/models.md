# Model Selection

> Model tiers and CLI fallback for retained single-provider integrations.

**Last Updated**: 2026-09-12

## Model policy

`~/.claude/config/model_policy.yml` maps portable tiers to provider-native model
names. It also defines provider order, fallback chains, a default timeout, and
CLI argument shapes. CDDL, delegation, SkillClaw, and model checking consume
this policy to select one provider route.

The policy loader rejects malformed required YAML. Optional agent-roster data is
allowed to be absent or malformed and resolves to an empty mapping, so reconcile
remains nonfatal.

## Interactive dispatch

Model policy does not choose workers for interactive work. OMP `task` batches
use the role selection in the orchestration guide: `scout`, `reviewer`,
`security-reviewer`, `sonic`, or the omitted default implementation worker.

---

[← Configuration](README.md)
