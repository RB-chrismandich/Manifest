---
type: llm
focus: {source: file, path: docs/ingest-flow.md}
---
The diagram shows this order and nothing invented in between: cli `ingest` command → config.load (db_path) → ingest.run → ingest.read_csv (csv.DictReader) → ingest.normalize (lower-cases event) → store.save → SQLite `events` table INSERT. Omitting config.load or the one-line ingest.run pass-through is fine; wrong order, invented steps (validation service, queue, cache) or missing store.save fail. Syntax must be valid Mermaid.
