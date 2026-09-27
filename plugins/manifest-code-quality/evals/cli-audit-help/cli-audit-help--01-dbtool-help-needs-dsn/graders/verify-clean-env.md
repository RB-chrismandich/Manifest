---
type: llm
weight: 1
---
Score 1 only if the answer recommends verifying the fix by running `dbtool --help` in a stripped/clean environment — explicitly mentioning something like an empty/fresh `HOME` (e.g. `env HOME=/tmp/empty-$$ ./dbtool --help; echo $?`) or a fresh clone/CI-like environment with `DB_DSN` unset — not just "test that it works now". Score 0 if no clean-environment verification step is mentioned.
