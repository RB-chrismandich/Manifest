# Contract: Evolve Library Prompt ({{LIBRARY}})

**Applies to**: `skillclaw_evolve.py` library rendering +
`configs/claude/prompts/skillclaw_evolve.md` template.

Format (one line per library skill, sorted by name):

```text
- <name> — <description>
```

Rules:
1. `description` is read from the skill's SKILL.md frontmatter.
2. Fail-open: missing/unparsable frontmatter → `- <name>` (name-only line);
   a parse error never aborts evolve.
3. Multi-line descriptions are flattened to one line (whitespace-collapsed),
   truncated at 200 chars to bound prompt cost (~80 skills × ≤200 chars).
4. Empty library renders `(empty)` (unchanged).
5. Template instruction wording: "do NOT duplicate these skills — match by
   purpose, not just name; if a session shows an improvement to one of these,
   propose it under the EXISTING name."

Test obligations (tests/python/test_skillclaw_evolve.py):
- prompt contains `name — description` for a committed skill with frontmatter
- skill with broken frontmatter yields name-only line, run succeeds
- description >200 chars is truncated
