---
type: llm
focus: last_message
---
- Flags the hardcoded API key as critical and recommends moving it to an environment variable/secret store (and rotating it).
- Flags `pickle.loads` on remote, partner-supplied content as critical unsafe deserialization / RCE, recommending a safe format (e.g. JSON) or signed payloads.
- Findings carry a severity and a location (line or function).
- Does not block or refuse; it reports inline with recommendations.
Pass only if all four hold.
