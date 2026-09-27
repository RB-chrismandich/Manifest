---
max_turns: 8
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
I have two lists of transaction IDs. Ledger: T100, T101, T102, T104. Bank: T100, T102, T103, T104. Reconcile them — which IDs are only in the ledger and which are only in the bank?
