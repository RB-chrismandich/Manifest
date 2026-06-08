# SkillClaw Integration

> PR-gated session capture that evolves reusable skills from your CLI-agent workflow

**Last Updated**: 2026-06-07
**Audience**: Operators, developers
**Prerequisites**: Manifest installed (`./bootstrap.sh`)

SkillClaw captures CLI-agent sessions through a local proxy and evolves reusable
`SKILL.md` skills. In Manifest it is a **PR-gated proposer**: nothing reaches the
committed `.skillshare/skills/` library without a merged PR.

## Enable / disable

```bash
./bootstrap.sh --enable-skillclaw     # install, configure, write wrappers, start daemon
./bootstrap.sh --disable-skillclaw    # remove wrappers, stop daemon (full revert)
```

## How capture works (fail-open)

Shell **wrapper functions** (`claude`, `codex`) check the daemon's health at
invocation time (300ms cap). If it's up, the agent is routed through
`http://127.0.0.1:8765`; if it's down or `SKILLCLAW_BYPASS=1` is set, the agent talks
to its provider directly, unchanged. The daemon is never in the critical path.

Capture is **lossy by design**: a crash drops the in-flight session (a supervisor
restarts the daemon). Evolution is statistical over many sessions, so loss is noise.

## Promote evolved skills

```bash
~/.claude/scripts/skillclaw_promote.sh            # evolve + preview (dry-run)
~/.claude/scripts/skillclaw_promote.sh --no-evolve  # preview existing library only
~/.claude/scripts/skillclaw_promote.sh --apply    # open ONE review PR (commit per skill)
```

Only one open `skillclaw/evolve-*` PR at a time (Option A); `--force-new` overrides.

## Security

- Storage `~/.skillclaw/` is `chmod 700`.
- `skillclaw_scrub.py` redacts API keys / auth headers from captured sessions before
  evolution.

## Follow-ups (not in V1)

- **gemini / cursor-agent capture:** add wrappers only after verifying each CLI honors a
  base-URL override SkillClaw can serve (Anthropic + OpenAI CLIs are verified; Gemini was
  not in SkillClaw's documented compatible-agent list).
- **TLS:** http-localhost works for the verified CLIs; add local TLS termination only if a
  specific SDK rejects http.
- **Evolve model defaults:** confirm the Ollama model + cloud fallback tier in `skillclaw.yml`.
- **Shared team storage (S3/OSS)** and cross-device sync.

---

## Related Documents

- [Commands Guide](COMMANDS.md) - Full command reference including `/skill-evolve`
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - SkillClaw capture & evolve pipeline diagram
- [Getting Started](GETTING_STARTED.md) - First-time Manifest setup
- [README.md](../README.md) - Project overview and SkillClaw feature summary
