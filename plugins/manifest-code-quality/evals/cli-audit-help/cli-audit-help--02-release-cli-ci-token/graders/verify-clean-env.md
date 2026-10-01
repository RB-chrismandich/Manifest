---
type: llm
weight: 1
---
Score 1 only if the answer recommends verifying with a clean/empty `HOME` locally (e.g. `env HOME=/tmp/empty-$$ ./release-cli --help; echo $?`) to reproduce the CI failure before trusting a fix, rather than relying only on the fact that it now works on a machine that already has the token file. Score 0 if no such clean-env verification is suggested.
