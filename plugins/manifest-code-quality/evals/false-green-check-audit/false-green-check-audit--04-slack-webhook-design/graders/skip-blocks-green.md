---
type: llm
weight: 1
---
Score 1 only if the recommended design makes a skipped/unverified Slack check prevent the suite from reporting an overall green/pass: the overall verdict is only green when there are zero failures AND zero skips (e.g. skips excluded from any `all(...)`-style reduction and forcing a distinct PARTIAL/UNVERIFIED verdict), and the run exits non-zero (or otherwise signals not-green to CI) when anything was skipped. Score 0 if a skip could still be represented by a truthy value that feeds a pass reduction, or the overall result can be green/exit 0 while the Slack check was never verified.
