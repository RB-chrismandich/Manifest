---
name: learning-capture
description: Append, query, increment, and render structured lessons from an XDG-owned JSONL knowledge base; capture is advisory and independent of the primary task verdict.
---

# Learning Capture

Run `scripts/learning_capture.py` with `add`, `query`, `increment`, `list`,
`stats`, or `sync-docs`. Run `contract` for the machine-readable command and
option surface consumed by other plugin bundles.
Records are append-only JSON Lines at
`$XDG_DATA_HOME/manifest/knowledge/entries.jsonl`.

Legacy cross-domain calls remain supported: `add` accepts title, description,
tags, confidence, severity, detection cue, prevention rule, provenance, and
source; `query` accepts category, language, tag, and `--format llm` filters.
Underscored category names are canonical, while hyphenated aliases remain
accepted. IDs use `KB-NNN`; `increment` updates occurrences and last-seen
metadata atomically. `sync-docs` renders the JSONL records to
`docs/KNOWLEDGE_BASE.md` or an explicit `--output` path without YAML or shared
assistant settings.

Required capture fields are category, language, and either finding text or a
description. Never discard existing records. A malformed existing record must
surface an error instead of being overwritten. The store is capped at 500
entries.

Cross-domain consumers invoke `manifest-workspace:learning-capture`; capture failure is
advisory and must not change their primary verdict.
