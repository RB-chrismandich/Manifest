---
type: llm
focus: last_message
---
Pass only if ALL of these hold:
1. The answer does NOT conclude the readiness check is wrong/buggy.
2. It explains that exit code 0 is not proof of auth for jules: the CLI can print an authentication error and still exit 0, so readiness requires a positive repository listing (actual repo rows in the output).
3. It gives both concrete fixes: run `jules login`, and authorize the target repository in the Jules GitHub App.
