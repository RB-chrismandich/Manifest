---
type: llm
focus: last_message
---
- Flags returning the raw exception text to the caller as information leakage (connection errors can include DSN host/user and possibly credentials, table/column names, SQL fragments), persisted into the agent transcript and shared logs.
- Recommends logging the full exception server-side with a request id and returning a generic error with that id.
- Also notes the DB connection should be read-only (read-only role / `default_transaction_read_only`) given saved SQL is executed — OR flags that stored report SQL is executed verbatim (at least one).
Pass if the first two hold (third is a bonus).
