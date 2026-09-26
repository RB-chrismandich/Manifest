---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It recommends `promtool check config` for prometheus.yml and `promtool check rules` for rule files.
2. It says to run promtool from the same prom/prometheus:v2.54.1 image (version-matched to runtime), with files mounted as in deploy.
3. It says yamllint is fast feedback but necessary-not-sufficient; the app's parser is the gate.
