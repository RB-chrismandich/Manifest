# SkillClaw Problems

> Capture, ingest, and evolve failures.

## SkillClaw Issues

SkillClaw is opt-in and disabled by default. These issues only apply when
`--enable-skillclaw` has been used.

### Evolve Produced No Candidates

**Symptom:** `/skill-evolve` or `skillclaw_promote.sh` reports zero candidates.

**Diagnosis — check each step in order:**

1. Confirm `claude -p` is reachable (requires a Claude Max subscription; no API key needed):

   ```bash
   echo "ping" | claude -p "Reply with pong"
   ```

2. Check whether ingest populated sessions:

   ```bash
   ls ~/.skillclaw/sessions/
   ```

   If empty, transcripts may not have been ingested yet. Run ingest manually and
   verify that `~/.claude/projects/` contains `.jsonl` files:

   ```bash
   ls ~/.claude/projects/**/*.jsonl 2>/dev/null | head -5
   ```

3. Review `window_days` and `settle_minutes` in `~/.skillclaw/config.yml`. If
   `settle_minutes` is larger than the age of your most recent session, that
   session will be skipped until it has cooled down.

**Fix:** Adjust the window/settle values, re-run ingest, then re-run evolve.

---

### Candidate Rejected During Promote

**Symptom:** Promote logs a warning such as `WARN: candidate rejected — <reason>`.

**Diagnosis:** Rejected candidates are preserved for inspection:

```bash
ls ~/.skillclaw/skills/rejected/
```

Review the rejected skill file and the accompanying `*.reason` file (if present)
to understand why it was filtered out (e.g. low confidence score, duplicate of an
existing skill, scrub flagged a secret).

**Fix:** Edit the candidate to address the rejection reason, then re-run:

```bash
~/.claude/scripts/skillclaw_promote.sh --apply
```

---

### Disable / Teardown SkillClaw

To fully remove SkillClaw (strips any legacy shell-wrapper block and removes the
retired launchd unit if present):

```bash
./bootstrap.sh --disable-skillclaw
```

---

### Storage Permissions

**Symptom:** Capture fails with a permission error on `~/.skillclaw/`.

**Check:**

```bash
stat -c '%a' ~/.skillclaw 2>/dev/null || stat -f '%Lp' ~/.skillclaw
```

The directory must be `700`. If it is not:

```bash
chmod 700 ~/.skillclaw
```

---

### Promote Opened No PR

**Symptom:** Running `/skill-evolve` or `skillclaw_promote.sh` completes without opening a PR.

**Cause:** Dry-run is the default. The script prints what it would do but does not push.

**Fix:**

```bash
~/.claude/scripts/skillclaw_promote.sh --apply
```

If it still aborts with "open PR already exists":

```bash
# The script refuses to create a second PR while skillclaw/evolve-* is open.
# Close or merge the existing PR first, or override:
~/.claude/scripts/skillclaw_promote.sh --apply --force-new
```

---

---

[← Troubleshooting](README.md)
