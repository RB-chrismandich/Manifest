# Agent Execution Problems

> Agents that hang, fail, or return nothing.

**Last Updated**: 2026-08-20

## Agent Execution Issues

### Agent Status: "missing"

**Symptom:**

```json
{
  "agents": {
    "claude": {"status": "missing"}
  }
}
```

**Solution:**

```bash
# Check if CLI is installed
which claude
which gemini
which cursor-agent

# If missing, install
npm install -g @anthropic-ai/claude-code
npm install -g @google/gemini-cli
curl https://cursor.com/install -fsS | bash

# Verify installation
claude --version
gemini --version
cursor-agent --version
```

---

### Agent Status: "failed"

**Symptom:**

```json
{
  "agents": {
    "claude": {"status": "failed", "output": "Error: ..."}
  }
}
```

**Causes:**

1. **Authentication failure** → See [Authentication Issues](authentication.md)
2. **Quota exceeded** → Wait or select a lower retained model tier in
   `model_policy.yml`
3. **Timeout** → Divide independent work into smaller OMP `task` units

**Solution:**

```bash
# Check authentication
claude auth status
gemini auth status

# Inspect configured runtime status
manifest check-status
```

---

### Codex: Session Storage Not Writable

**Symptom:**

```text
Warning: Codex runtime unavailable, disabling Codex agent
Reason: Session directory is not writable: /Users/<user>/.manifest/codex/sessions
```

**Why this happens:**

Codex CLI requires writable session storage even in non-interactive `exec` mode.

**Preferred fix (repair ~/.manifest permissions):**

```bash
sudo chown -R "$(whoami)" ~/.manifest
chmod -R u+rwX ~/.manifest
```

**Engineering workaround (use a custom Codex state path):**

```bash
# 1) Create a writable Manifest state directory
mkdir -p ~/.manifest/custom-codex-state

# 2) Point Codex state to it
export CODEX_HOME="$HOME/.manifest/custom-codex-state"

# 3) Re-run the retained status check
manifest check-status
```

**Tradeoff:** This avoids permission issues but uses a separate Codex state/config history path.

---

### OMP Task Unavailable

**Symptom:** An interactive harness does not expose OMP `task`.

**Solution:** Execute the independent units inline, report `DEGRADED`, and do not
fall back to a provider CLI. When OMP is available, dispatch all independent units in
one `task` batch and use `hub` only for coordination or waiting.

---

---

[← Troubleshooting](README.md)
