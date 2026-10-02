---
type: llm
weight: 1
---
Score 1 only if the answer flags that the `/login` route does no type/schema validation of `req.body.email` before use — the only check is the regex format test (which itself is the ReDoS risk), there is no check that it is a string with a bounded length (e.g. zod/joi/yup schema, `typeof email === "string"`, a max length before running the regex) — and recommends adding request validation at the route boundary. Score 0 if this is missing from the findings.
