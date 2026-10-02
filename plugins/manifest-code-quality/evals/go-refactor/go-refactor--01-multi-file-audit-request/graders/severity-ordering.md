---
type: llm
weight: 1
---
Score 1 only if both the SQL injection (`fmt.Sprintf` query in GetUserByName) and the command injection (`sh -c` in RunUserScript) are placed in the highest severity/priority tier of the answer (e.g. "Critical", "Immediate", or the first items of the priority list). The ignored `createToken` error may be ranked at any tier (a silently empty session token can legitimately be Critical). Score 0 if either injection is ranked below a style/quality/documentation finding.
