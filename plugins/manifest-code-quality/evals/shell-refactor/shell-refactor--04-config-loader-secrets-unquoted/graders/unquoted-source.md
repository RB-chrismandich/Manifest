---
type: llm
weight: 1
---
Score 1 only if the answer flags `source ./config/$ENV.sh` as an unquoted variable expansion in a sourced path — subject to word-splitting/glob risk and unpredictable behavior if `ENV` is unset, empty, or contains unexpected characters — AND recommends quoting it (`source "./config/${ENV}.sh"`) and/or validating `ENV` against an allow-list before sourcing arbitrary code. Score 0 otherwise.
