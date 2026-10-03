---
type: llm
focus: last_message
weight: 1
---
Pass if the answer explains that a PR created in the web UI isn't observed by the tool-triggered hook, AND tells the user to run the sync manually for PR #303 (in any form: invoking the issue-sync-pr skill, `issue_support.sh sync-pr 303`, or doing the same updates by hand).
