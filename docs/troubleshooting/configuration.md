# Configuration Problems

> Settings that do not take effect, and plugin convergence.

## Configuration Issues

### services.yml Not Found

**Symptom:**

```text
Warning: No services config, use defaults (all enabled)
```

**Solution:**

```bash
# Deploy configuration
cp -r configs/claude/* ~/.claude/
cp -r configs/claude/.[!.]* ~/.claude/ 2>/dev/null || true

# Or re-run bootstrap
./bootstrap.sh --force
```

---

### Invalid YAML Syntax

**Symptom:**

```text
Error: YAML parsing failed
```

**Solution:**

```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('~/.claude/config/services.yml'))"

# Common issues:
# - Incorrect indentation (must use spaces, not tabs)
# - Missing colons
# - Unquoted strings with special characters

# Restore from the repo source
cp configs/claude/config/services.yml ~/.claude/config/services.yml
```

---

### Configuration Not Updating

**Symptom:** Changes to `services.yml` don't take effect

**Cause:** Configuration is cached or CLI flags override

**Solution:**

```bash
# Restart shell to clear any environment variables
exit
# (Open new terminal)

# Verify configuration is correct
cat ~/.claude/config/services.yml

# Run without CLI flag overrides
~/.claude/scripts/parallel_agent.py "Task"
```

---

### Model Pins Reported as Unverified

**Symptom:**

```text
○ 2 check(s) unverified (no API credentials — run MODEL_CHECK_PROBE=1 model_check.sh for a live CLI probe)
```

**Cause:** On OAuth-only machines (no `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`)
there is no API to list models with, so `check_status.sh` reports the
claude/gemini pins in `parallel_agent.yml` (`model_tiers`) as unverified rather
than falsely green.

**Solution:**

```bash
# Live-verify each pin with a one-shot CLI probe (one tiny LLM call per pin)
MODEL_CHECK_PROBE=1 ~/.claude/scripts/model_check.sh
```

If a pin reports `STALE`, update the corresponding `model_tiers` entry in
`~/.claude/config/parallel_agent.yml` (current Gemini pins:
`gemini-3-flash-preview` / `gemini-3-pro-preview`).

**If the `gemini` probe fails with `IneligibleTierError`**, the pin is not the
problem: free-tier Gemini Code Assist for individuals has been discontinued, and
the CLI dies at the eligibility layer before it ever validates a model
("migrate to the Antigravity suite of products"). Either set `GOOGLE_API_KEY` /
`GEMINI_API_KEY` to reach the API directly, or use the `antigravity` provider —
`agy` serves Gemini models and its pins *are* verified.

**A `SKIPPED: devin (unpinned by design)` line is expected, not a failure.**
devin ships no `model_tiers` block because its catalog is login-gated; `--model`
passes through and the account default stands. To pin real tiers, run
`devin auth login`, then `devin models list`. Note `devin auth status` prints
"Not logged in." while still exiting **0**, so never test devin auth by exit code.

---

## Codex Native Plugin Convergence

Inspect the native inventory with:

```bash
codex plugin list --marketplace manifest --json
```

If convergence fails, the flat `~/.codex/skills` link intentionally remains.
Fix the reported native error, then run:

```bash
manifest bootstrap-sync --source /path/to/Manifest --harness codex --non-interactive --json
```

If Codex still reports `Exceeded skills context budget`, inspect the actual
startup list rather than counting installed plugin skills:

```bash
codex debug prompt-input | jq -r '.[0].content[0].text'
```

A converged Manifest installation exposes only
`manifest-code-quality:antipattern-detect`, `manifest-security:code-audit`, and
`manifest-workspace:help` for implicit routing. Other skills remain installed
and explicitly callable as `$bundle:skill`; their absence from this startup list
is intentional. In a source checkout, regenerate and validate the policy before
rerunning bootstrap:

```bash
uv run python tools/generate_plugin_views.py --repo-root .
uv run python tools/generate_plugin_views.py --check --repo-root .
```

ADHD hook diagnostics live under
`$XDG_STATE_HOME/manifest/diagnostics/manifest-i-have-adhd.json` (or
`~/.local/state/manifest/...`). Records contain only plugin, version, harness,
and a stable reason code. `manifest reconcile --apply` reports this state. The
upstream `i-have-adhd@i-have-adhd` plugin remains installed but is disabled
after the mirrored hook verifies; uninstall restores its prior enabled field
only while that field still equals Manifest's written value.

Antigravity verifies the generated Gemini-extension context asset used by its
Gemini-lineage import path. Devin verifies the generated rule against
`~/.codeium/windsurf/memories/global_rules.md`, which `devin rules` reports as
always-on. If that Devin file already contains different non-empty user content,
bootstrap preserves it and reports the collision; move or merge that content,
then rerun bootstrap so the pinned ADHD rule can be installed.

---

[← Troubleshooting](README.md)
