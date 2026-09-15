# Performance & Output Problems

> Slow runs and malformed or missing output.

**Last Updated**: 2026-08-20

## Performance Issues

### OMP Task Takes Too Long

**Symptom:** Independent work waits too long for completion.

**Solution:**

- Split the work into smaller independent units and dispatch them in one OMP `task`
  batch (at most 32 per wave).
- Use `hub` only to coordinate or wait for children.
- For retained single-provider workflows, select an appropriate tier in
  `model_policy.yml` and inspect availability with `manifest check-status`.
- If OMP `task` is unavailable, execute inline and report `DEGRADED`.

---

## Output Issues

### Structured Output Malformed

**Symptom:** A supported tool emits malformed structured output.

**Solution:**

```bash
# Inspect the retained runtime configuration and status
manifest check-status --verbose

# Validate a saved JSON response
python3 -m json.tool < response.json
```

### Output Truncated or Missing

**Solution:** Consult the affected retained tool's documented output contract and
inspect its status with `manifest check-status`. OMP task results are session-scoped;
the parent should aggregate required evidence before the session ends.

---

---

[← Troubleshooting](README.md)
