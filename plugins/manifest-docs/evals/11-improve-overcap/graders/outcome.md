---
type: llm
focus: trace
---
From the trace, judge the final state of the troubleshooting content. Pass only if: (1) no troubleshooting page is over 200 lines (split by subject such as install/auth/ingest, or cut); (2) the planted filler ("It is important to note", "simply", "Needless to say", "Please note that", "basically", "Obviously", "In this document we will") is gone from the final troubleshooting content; (3) if split, docs/README.md (or a troubleshooting hub) links every resulting page; (4) no error-code heading (INSTALL-01…INGEST-24) was silently lost: each was kept, merged, or dropped with the reply saying why (e.g. nothing in the code raises it).
