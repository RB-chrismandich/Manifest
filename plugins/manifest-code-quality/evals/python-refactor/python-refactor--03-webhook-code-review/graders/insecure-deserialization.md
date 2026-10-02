---
type: llm
weight: 1
---
Score 1 only if the answer flags `pickle.loads(payload_bytes)` as insecure deserialization / a dangerous operation that can execute arbitrary code from attacker-supplied data, and recommends replacing pickle with a safe serialization format (e.g. `json`) or otherwise avoiding deserializing untrusted bytes with pickle. Score 0 otherwise.
