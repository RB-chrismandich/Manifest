# Manifest

[![Manifest CI](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml/badge.svg)](https://github.com/ReefBytes/Manifest/actions/workflows/ci.yml)

> OMP-native AI coding workflow configuration for Claude Code, Cursor IDE, Gemini CLI,
> Codex CLI, Antigravity IDE, and the Devin CLI

[Jules](docs/JULES.md) is an optional remote GitHub task backend: bootstrap with
`--enable-jules`, authenticate through browser OAuth, and submit through `/delegate`
or the official `jules` issue-label workflow.

**Last Updated**: 2026-10-07

Manifest deploys shared guides, skills, prompts, and scripts to `~/.claude/`,
`~/.cursor/`, `~/.gemini/`, `~/.codex/`, and `~/.antigravity/`. Interactive
sub-agent work uses OMP-native `task` batches and `hub` coordination; the parent
agent validates and aggregates evidence. Retained single-provider tools use
`model_policy.yml` for model tiers and CLI fallback.

**Core Capabilities**: OMP task batches | Native validation tiers | Model policy
| Production-grade templates

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/ReefBytes/Manifest.git
cd Manifest

# Run bootstrap (macOS/Linux)
./bootstrap.sh

# Optional: configure MCP servers (interactive per-server selection)
./bootstrap.sh --install-mcp

# Confirm the installed CLI surface
~/.local/bin/manifest --help
```

Context7 uses a one-time device OAuth login. Its long-lived credential stays in
`~/.config/context7/credentials.json`; subsequent installs reuse it across all
enabled harnesses without installing duplicate Context7 rules or skills.

> **`./bootstrap.sh` is not side-effect-free on the working tree.** Every run
> no longer invokes retired skill supply (removed 2026-07-27, feature 522 FR-021a).
> The project-scoped Copilot target `.github/skills/` is no longer synced.
> to own, so the write is expected — but do not run bootstrap expecting a clean
> `git status`, and do not commit `.github/skills/`.

⏱️ **Time to setup**: ~5 minutes | 💻 **Platforms**: macOS (Intel/Apple Silicon), Linux (Debian, RHEL, Arch, openSUSE)
🐍 **Python**: 3.9+ (Phase 3 features require Python; bootstrap auto-detects and prefers 3.12+)

---

## Architecture

```text
User → Supported coding harness → /skill or task
                                      ↓
                         OMP task batches (≤32 ready units)
                                      ↓
                          Child workers execute one unit
                                      ↓
                    Parent validates evidence and aggregates results
```

Noninteractive single-provider integrations (such as CDDL, delegation, and
SkillClaw) resolve their provider CLI and model tier from `model_policy.yml`.

**Visual Documentation**: [Architecture Diagrams](docs/diagrams/README.md) -
Mermaid flowcharts showing bootstrap, execution, validation, and consensus flows

---

## Plugin Eval Scorecard

<!-- eval-scorecard:begin -->

Each plugin is measured with `claude plugin eval --ablation with-without --judge-model opus`.
Cases normally run 3× with and without the plugin; Δ is the mean score lift. Coverage below
is partial where shown. Tool-restricted, unscaffolded, or provider-session-limited runs are not valid scores;
the two single-case suites are newly added coverage.

| Plugin | Coverage / suite | Passed | With | Without | Δ | Evidence-backed update |
|---|---:|---:|---:|---:|---:|---|
| `manifest-code-quality` | 188/188 reconciled; false-green remeasured on v0.6.6 | 162/188 | 0.960 | 0.884 | +0.075 | Case 04 scorer passed 2/3 after two edits; the failed answer specifies CI skips as non-passing, but judges still failed it (content/rubric disagreement) |
| `manifest-forge` | 91/91 reconciled; five skill batches rerun after reset | 81/91 | 0.972 | 0.837 | +0.135 | Merged complete case-level runs; rerun batches had zero session errors |
| `manifest-workspace` | 86/86 reconciled; five skill batches rerun after reset | 64/86 | 0.890 | 0.544 | +0.347 | Merged complete case-level runs; rerun batches had zero session errors |
| `manifest-ops` | 84 scenarios measured: 69 original + 15 safe re-authored equivalents | 64/84 | 0.916 | 0.643 | +0.273 | Latest safe ablation: 10/15 pass, 0 run errors; `cdd-04`/`crf-04` remain 0/3; original scaffold scripts untouched |
| `manifest-security` | 53/53 reconciled; seven skill batches rerun after reset | 48/53 | 0.953 | 0.845 | +0.108 | Corrected `chw-01` tool access; replaced all session-limited cases; rerun batches had zero session errors |
| `manifest-docs` | 20/20 (v0.6.5) | 14/20 | 0.958 | 0.854 | +0.104 | Case 06 improved; case 01 edit reverted; cases 09/13 regress; 17/18 fail in both arms |
| `manifest-delegate` | 15/15 (v0.2.1) | 13/15 | 0.944 | 0.657 | +0.287 | Envelope-trigger description: case 08 0.20 → 1.00 with the skill firing 3/3, no rerun regression; setup-01/06 fail in both arms without a Bash grant |
| `manifest-i-have-adhd` | 7/7 (v0.2.6) | 6/7 | 0.968 | 0.493 | +0.475 | Cases 02/04 pass all runs; case 01 remains 2/3 (tangent offer displaced next action) |
| `manifest-spec-planning` | 1/1 | 1/1 | 1.000 | 1.000 | +0.000 | Added webhook-storage trade-off case |
| `stitch-design` | 1/1 | 1/1 | 1.000 | 1.000 | +0.000 | Added modal accessibility audit case |

Recorded spend across 71 result JSONs: $672.76, including failed, confounded, and provider-limited runs.
The 15 original Ops scaffold scripts were not executed; safe equivalents are documented in `plugins/manifest-ops/evals-safe/README.md`.
Case-level failures and the code-quality grader disagreement remain visible; these are not counted as passes.

<!-- eval-scorecard:end -->

---

## Documentation

| Page | Answers |
|------|---------|
| [Getting Started](docs/GETTING_STARTED.md) | How do I install it and make the first run work? |
| [Features](docs/FEATURES.md) | What does Manifest actually do? |
| [Requirements](docs/getting-started/requirements.md) | What platforms and CLI versions are supported? |
| [Commands](docs/COMMANDS.md) | What can I invoke, and how do I write my own? |
| [Configuration](docs/configuration/README.md) | Which setting lives in which file? |
| [Troubleshooting](docs/troubleshooting/README.md) | Something broke — where do I look? |
| [Architecture Diagrams](docs/diagrams/README.md) | How do the pieces fit together? |
| [Project Structure](docs/PROJECT_STRUCTURE.md) | Where does everything live in this repo? |
| [Testing](docs/TESTING.md) | How do I run the test suites? |
| [Model Policy](docs/MODEL-POLICY.md) | Which model runs a session, sub-agent, or turn? |
| [Full docs index](docs/README.md) | Everything else. |

## License

This project is licensed under a Proprietary License - see the [LICENSE](LICENSE) file for details.

**Key Restrictions:**

- ✅ Use and modify for personal/internal purposes
- ❌ Distribution, sale, or sublicensing without written permission from ReefBytes
- ❌ Commercial use requires explicit authorization

For licensing inquiries: [ReefBytes/Manifest](https://github.com/ReefBytes/Manifest)

---

## Related Projects

- [Claude Code](https://claude.ai/code) - Official Anthropic CLI
- [Cursor](https://cursor.sh) - AI-powered IDE
- [Google Gemini CLI](https://www.npmjs.com/package/@google/gemini-cli) - Gemini command-line interface
- [OpenAI Codex CLI](https://github.com/openai/codex) - Codex terminal coding agent

---

## Support

- **Issues**: [GitHub Issues](https://github.com/ReefBytes/Manifest/issues)
- **Documentation**: [docs/](docs/)
- **AI Context**: Read [CLAUDE.md](CLAUDE.md) for Claude Code integration details
