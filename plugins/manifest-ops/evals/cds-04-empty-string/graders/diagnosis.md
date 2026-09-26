---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It explains that when HTTP_PROXY is unset, the passthrough injects an empty string `""`, which the app's parser rejects.
2. It recommends omitting the key entirely when unset (e.g. a separate override file/profile per host, or conditional env) and/or making the config use a literal/default instead of the var.
3. It does NOT recommend setting HTTP_PROXY to a dummy/fake URL as the fix.
