---
type: llm
weight: 1
---
Score 1 only if the answer gives findings for BOTH files, each with the matching engine's distinctive lens: (1) `run-release.sh` — `source "$CONFIG_PATH"` executes the externally-supplied config path as shell code with no validation, which is arbitrary code execution if `$CONFIG_PATH` is (or points at) attacker-influenceable content, with a fix that avoids sourcing it directly — e.g. parsing only the expected variables, using a restricted/validated format, or strictly validating the path before sourcing; AND (2) `token-gen/main.go` — `generateToken` seeds and draws from `math/rand` to build a token used for service auth, making the token predictable/guessable, with a fix that uses `crypto/rand` instead. Score 0 if either finding is missing, or if the answer only reviews one of the two files/engines and treats the other as out of scope or gives it only generic advice.
