# Spec & Plan Systems Map

> Which planning system to use, when — and what each directory is for

**Last Updated**: 2026-06-29
**Audience**: Contributors, AI agents

This repo accumulated four complementary planning/specification systems. They
are not competing — each owns a distinct lifecycle stage and audience.

| System | Location | Owns | Use when |
|--------|----------|------|----------|
| **Speckit** | `specs/` (artifacts) + `.specify/` (templates, scripts, constitution, extensions) | Full feature lifecycle — the constitution's nine-phase **state-gated lifecycle**: Specify → Clarify → Spec-Review (product) → Plan → Task Creation → Analyze → Spec-Review (technical) → Implement → Verify task-by-task, with hard phase-gating, the smoke-test Verify gate, and the project constitution (Principle VI) | Building a new feature of any real size. Entry point: `/speckit-specify`, or `/lifecycle` to drive the full gated flow |
| **Superpowers design docs** | `docs/superpowers/specs/` (designs) + `docs/superpowers/plans/` (implementation plans) | Dated design-decision history from the superpowers brainstorm→plan workflow | Recording a reviewed design for a focused change (e.g. a subsystem swap); historical reference |
| **Plan-manage lifecycle** | `configs/claude/.plans/` (deployed to `~/.claude/.plans/`) | Lightweight operational plans on target machines: CREATE → ACTIVE → COMPLETED (`.archive/`) / ABANDONED (`.abandoned/`) | Day-to-day orchestrated work tracking via `/plan-manage`; not tied to this repo's features |
| **Lesson journal** | `.Jules/` (`bolt.md`, `forge.md`, `palette.md`, `sentinel.md`) | Dated lessons learned (performance, security, UI, tooling) captured by agents during sessions | Append-only knowledge capture; consult when a task touches a previously-burned area |

## Rules of thumb

- **New feature?** Speckit. The constitution (`.specify/memory/constitution.md`)
  is non-negotiable and its gates (parallel-agent cross-verification, quality
  tiers) apply to the resulting PRs.
- **Design review for a focused swap/refactor?** A superpowers design doc is
  enough; link it from the implementing PR.
- **Tracking multi-step operational work on a deployed machine?** `/plan-manage`
  with `configs/claude/.plans/`.
- **Learned something the hard way?** Append to the matching `.Jules/` file
  (or via the `learning-loop` skill into `knowledge_base.yml`).
- A speckit feature's spec directory is permanent history; when delivered, its
  status line is marked **Delivered** (specs/ has no archive subdirectory —
  that convention belongs to `configs/claude/.plans/`).

## Related

- [docs/COMMANDS.md](COMMANDS.md) — canonical slash-command table
- [configs/claude/.plans/README.md](../configs/claude/.plans/README.md) — plan lifecycle reference
- [.specify/memory/constitution.md](../.specify/memory/constitution.md) — project constitution
