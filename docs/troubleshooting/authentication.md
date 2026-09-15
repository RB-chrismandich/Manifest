# Authentication Problems

> Login, token, and credential failures per provider.

**Last Updated**: 2026-08-20

## Authentication Issues

> **API keys are optional.** The Claude/Gemini agents select an execution backend
> per run: the provider SDK when its package and API key
> (`ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) are both present, otherwise the
> logged-in `claude` / `gemini` CLI (OAuth/subscription login). As long as the
> CLIs are authenticated, orchestration works without any API key.

### Claude CLI: "Not authenticated"

**Symptom:**

```text
Error: You are not authenticated. Run 'claude auth login'
```

**Solution:**

```bash
# Log in to Claude CLI (OAuth/subscription login — no API key required)
claude auth login

# Verify authentication
claude auth status
```

**API key (optional, for the SDK backend):**

1. Visit: <https://console.anthropic.com/account/keys>
2. Create new API key
3. Export it as `ANTHROPIC_API_KEY` to make the orchestrator use the SDK
   backend instead of the CLI fallback

---

### Retained single-provider route unavailable

**Cause:** The configured provider CLI is not authenticated or the selected route in
`model_policy.yml` is unavailable.

**Solution:**

```bash
# Inspect configured runtime status
manifest check-status

# Authenticate the relevant retained provider CLI
claude auth login
gemini auth status
```

CDDL and SkillClaw retain their documented, stdin-driven provider seams. Configure
their routes through `model_policy.yml` or their existing environment overrides.

---

### Gemini CLI: "Authentication failed"

**Symptom:**

```text
Error: Invalid API key
```

**Solution:**

```bash
# Authenticate with Gemini CLI
gemini  # first run prompts a Google OAuth login

# Verify authentication
gemini auth status
```

**API key (optional, for the SDK backend):**

1. Visit: <https://makersuite.google.com/app/apikey>
2. Create new API key
3. Export it as `GOOGLE_API_KEY` to make the orchestrator use the SDK
   backend instead of the CLI fallback

---

### Cursor: "Command not found"

**Symptom:**

```bash
cursor: command not found
```

**Solution:**

Cursor is a desktop application, not a CLI tool. The Manifest integration expects Cursor
to be installed but doesn't directly invoke it via command line in the current implementation.

**Workaround:**

```bash
# Disable Cursor in configuration when it is not available
./bootstrap.sh --reconfigure --disable-cursor
```

**Note:** Cursor integration may be implemented differently in your environment.
Check your specific Cursor setup for command-line access.

---

---

[← Troubleshooting](README.md)
