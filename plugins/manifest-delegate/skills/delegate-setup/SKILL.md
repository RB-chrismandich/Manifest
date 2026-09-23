---
name: delegate-setup
description: Check backend readiness (Codex, Claude, Antigravity, Cursor, Devin, Jules) via parallel probes; reports state and a fix per backend.
---

# Delegate Setup

Runs `plugins/manifest-delegate/scripts/delegate.py setup` to report readiness
for every backend in the registry (`config/backends.json`), or one backend
with `--backend <id>`. Use before delegating a task when unsure a backend is
usable, or when a `task`/`review` call fails with "backend unavailable".

## Running it

```bash
delegate.py setup [--backend <id>] [--json]
```

All probes run in parallel with a bounded per-probe timeout and finish in
under 30 seconds. No probe ever prompts for input.

## Reading the report

```text
backend      state              version   fix
codex        ready              1.x       —
claude       not_authenticated  2.x       run: claude  (then /login)
antigravity  disabled_workspace 1.1.8     enable in $XDG_CONFIG_HOME/manifest/services.yml (workspace layer outranks user enable)
cursor       ready              2026.x    —
devin        disabled_workspace 3000.x    enable in $XDG_CONFIG_HOME/manifest/services.yml (workspace layer outranks user enable)
```

Devin ships **disabled** in `services.yml` (opt-in: `./bootstrap.sh
--enable-devin`), so a `disabled_workspace` row for it is the default state,
not a fault.

Jules also ships disabled in bootstrap (`--enable-jules` opts in). Its probe
requires a positive repository listing, not just exit zero: the CLI can print
authentication errors and still exit zero. Run `jules login` and authorize the
repository in the Jules GitHub App. The report does not invent an account name
from repository rows, and empty output means access is unverified. Existing
services files that predate Jules can opt out with `--disable-jules`.

States: `ready`, `not_installed`, `not_authenticated`, `disabled_workspace`,
`disabled_user`, `retired`, `error`. The `fix` column is the exact remediation
— follow it verbatim rather than guessing (install command, login command, or
which config file/layer to edit). `--json` rows additionally carry `identity`
(the authenticated account, populated only when `state` is `ready`).

## Config layers

Two places control whether a backend is even considered enabled, and they do
not have equal authority:

- **Workspace** `$XDG_CONFIG_HOME/manifest/services.yml` (default
  `~/.config/manifest/services.yml`) — a service disabled here is
  disabled everywhere in this workspace, regardless of user config.
  `disabled_workspace` means this layer is the blocker; user config cannot
  override it.
- **User** `delegation.json` (or `delegation.yml` when PyYAML is available) —
  per-user enable/default settings. `disabled_user` means the user config is
  the blocker and editing it is sufficient.

When both exist, workspace `services.yml` always wins. If no user config file
exists, factory defaults apply.

Gate-toggle flags (`--enable-review-gate`, `--gate-backend`,
`--disable-review-gate`) are a separate concern from readiness — see below.

## Soft review gate (US4)

The gate is a Stop hook (`plugins/manifest-delegate/hooks/hooks.json`) that,
when enabled, runs one read-only review delegation on the finishing turn's
edits and can block with `{"decision":"block","reason":...}` for the
developer to see. It is OFF by default.

```bash
delegate.py setup --enable-review-gate [--gate-backend <id>]
delegate.py setup --disable-review-gate
```

Enabling writes `review_gate.enabled: true` (and `review_gate.gate_backend`
if given) to the user config. The gate always fails open: a probe timeout,
missing backend, or any other failure emits `allow` plus a
`systemMessage` explaining the skip — it never blocks a session by accident.

**One gate at a time.** This gate and the legacy `openai-codex` /
`codex-plugin-cc` stop-time review gate are mutually exclusive — running both
double-reviews every Stop and can double-block. Disable the baseline gate
before enabling this one (see `plugins/manifest-delegate/MIGRATION.md`), and
never enable both simultaneously.

## Native-host prerequisites

This command reports only external backend readiness. A `ready` row does **not**
prove that OMP has discovered `delegate-runner`, that Claude Code has discovered
`manifest-delegate:delegate-runner`, or that either host can allocate the
runner's configured model and tool. Check discovery and the host's native
dispatch capability before claiming native relay availability.

Install and upgrade each host through its own inventory. After registering the
Manifest marketplace, OMP uses `omp plugin install manifest-delegate@manifest`;
Claude Code uses its native marketplace/plugin install and update interface
(for example, `claude plugin update manifest-delegate@manifest`). Reload the
host after update and verify its discovered agent roster. Do not copy plugin
trees or use shared-home symlinks as a substitute for either host's native
install.

Managed stale installations may be updated, uninstalled, or repaired only
through their owning receipt or native plugin mechanism after ownership is
checked. Never edit `~/.omp/agent/skills`, remove user-authored files, mutate
an unknown home installation, or uninstall the upstream Codex plugin merely as
an incidental setup action.
