---
type: llm
focus: last_message
weight: 1
---
Score 1 if the answer is a short, plain Slack-style announcement (roughly one sentence) about CI passing/being green, with no antipattern/knowledge-base analysis attached (no category/severity/detection-cue/prevention-rule fields, no mention of logging a pattern). Score 0 if it produces antipattern-detection output instead of, or in addition to, the announcement.
