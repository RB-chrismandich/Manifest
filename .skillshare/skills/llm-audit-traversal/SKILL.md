---
name: llm-audit-traversal
description: Review code that writes files using names/paths parsed from LLM output for path traversal and indirect prompt-injection sinks
---
# LLM-Output Path Traversal Audit

1. Find every file/dir write where a path component (`name`, `slug`, `filename`) comes from parsed model output — a regex capture, a fenced block, or a JSON field from a model response.
2. Flag absolute-path escape: in Python `Path(base) / name` **discards `base` entirely** when `name` is absolute (`/Users/x/.claude/skills/...`). Confirm whether the join can be hijacked this way.
3. Flag `../` traversal: `Path("/a/b") / "../../etc/x"` resolves outside `base`.
4. Inspect the extractor regex/parser. A permissive capture like `[^\n]+` admits slashes, dots, and absolute paths; require a strict slug allowlist such as `^[a-z0-9][a-z0-9-]{0,63}$`.
5. Require a containment check before the sink: `d = (base/name).resolve(); d.relative_to(base.resolve())` (raises on escape). Allowlist alone is not enough — keep both.
6. Map the indirect prompt-injection surface: any text the model ingests (web fetches, Read/WebFetch tool output, shared transcripts, `tool_result` blocks) can coerce the chosen `name`. One payload in one ingested session suffices; downstream promotion/glob gating does not save you because the write already landed.
7. Report each LLM-derived path component reaching `mkdir`/`open`/`write_text` without BOTH the slug allowlist and the `resolve().relative_to()` containment guard.
