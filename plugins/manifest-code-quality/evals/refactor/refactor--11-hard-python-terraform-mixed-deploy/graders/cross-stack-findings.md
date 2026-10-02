---
type: llm
weight: 1
---
Score 1 only if the answer gives findings for BOTH files, each with the matching engine's distinctive lens: (1) `iam.tf` — `aws_iam_policy.deploy` grants `Action = "*"` / `Resource = "*"`, a wildcard/admin-equivalent policy, with a fix that scopes it to specific least-privilege actions and resources; AND (2) `notify.py` — `subprocess.run(cmd, shell=True)` running a command string built via an f-string that interpolates `payload`/`url` directly, a shell command-injection vulnerability, with a fix that drops `shell=True` and passes the command as a list (e.g. `subprocess.run(["curl", "-X", "POST", "-d", payload, url])`) or uses a proper HTTP client instead. Score 0 if either finding is missing, or if the answer only reviews one of the two files/engines and treats the other as out of scope or gives it only generic advice.
