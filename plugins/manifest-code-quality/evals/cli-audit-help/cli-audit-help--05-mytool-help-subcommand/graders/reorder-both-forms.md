---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the `state_file` existence check runs before BOTH the `--help`/`-h` case block and the `help` subcommand branch, so a user with no state file (e.g. before running `mytool init`) can't get usage output from either form, AND recommends moving the help handling — covering `-h`, `--help`, and the `help` subcommand — above the `state_file` check. Score 0 if it only fixes one of the two forms, or doesn't move the handling above the `state_file` check.
