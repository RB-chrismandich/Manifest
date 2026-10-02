---
type: llm
weight: 1
---
The script uses `set -eu` WITHOUT `pipefail`. Score 1 only if the answer does NOT claim that the `ls ... | head` pipelines currently abort the script (under bare `set -e` a pipeline's status is the last command's, so an upstream SIGPIPE is not fatal). Mentioning SIGPIPE as a latent risk that becomes fatal if `pipefail` is added, or as advisory, is fine and scores 1. Score 0 if it states or ranks the head pipeline as an active abort/Critical bug under the current flags.
