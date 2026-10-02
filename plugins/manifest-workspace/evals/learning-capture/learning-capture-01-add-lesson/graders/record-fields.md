---
type: llm
focus: {source: file, path: data/manifest/knowledge/entries.jsonl}
weight: 2
---
The file is a JSON Lines store. Pass only if ALL hold:
1. Every line is valid JSON.
2. There is exactly one new record for this lesson, with category `antipattern`, language `bash`, confidence `high`, and an id of the form `KB-NNN`.
3. The record's description/text states that `$?` after `if !` is always 0 (inverted status), and it carries the detection cue and prevention rule (`cmd || status=$?` or equivalent).
