---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says generic YAML linting cannot catch this class of bug (include/merge semantics, duplicate keys, unknown fields) and is not sufficient.
2. It recommends Glance's own validator/assembled view (`config:validate` and/or `config:print`) as the pre-deploy gate.
3. It says to run it in the real runtime image (glanceapp/glance, same tag) with the config mounted the way it is at deploy, passing placeholder values for env vars like DOMAIN.
4. It highlights using the assembled output (`config:print`) to see the post-include structure.
