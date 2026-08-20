# Requirements

> Supported platforms, CLIs, and versions.

**Last Updated**: 2026-08-20

## Requirements

**For bootstrap.sh (automated setup):**

- macOS 10.15+ or Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)
- Internet connection for package downloads
- npm-compatible environment (auto-installed if missing)

**For manual setup:**

- Bash 4.0+
- Node.js 18+ and npm
- One or more of: Claude CLI, Gemini CLI, Cursor Agent, Codex CLI

**For `parallel_agent.py` (Python agent):**

- Python 3.9+ (3.12+ recommended, auto-detected by bootstrap)
- Install deps: `pip install -r configs/claude/scripts/requirements.txt`
- Key packages: `anthropic`, `google-genai`, `rich`, `pyyaml`, `aiohttp`
- API keys are optional: with `ANTHROPIC_API_KEY`/`GOOGLE_API_KEY` set, the Claude/Gemini
  agents use the SDK; without keys, they fall back to the logged-in `claude`/`gemini` CLIs
  (OAuth subscription login works out of the box)

**For the Stitch Design Skills (optional):**

- A [Google Stitch](https://stitch.withgoogle.com) account/project
- The Stitch MCP server, registered manually — **not** wired into `--install-mcp`. Stitch's
  auth model doesn't fit `configs/claude/config/mcp_servers.yml`'s zero-config remote-HTTP+OAuth
  schema: the official direct-HTTP path (`stitch.googleapis.com` + API-key header) is
  [known broken in Claude Code](https://github.com/anthropics/claude-code/issues/41664)
  (it always attempts OAuth dynamic client registration, which Stitch doesn't support, and
  ignores the header), so the working setup is a local stdio proxy. Run the guided wizard —
  it handles gcloud/API-key auth, project selection, and per-client config generation:

  ```bash
  npx @_davideast/stitch-mcp init
  ```

  See the [Stitch MCP setup guide](https://davideast.github.io/stitch-mcp/setup/) for details.

---

---

[← Getting Started](../GETTING_STARTED.md)
