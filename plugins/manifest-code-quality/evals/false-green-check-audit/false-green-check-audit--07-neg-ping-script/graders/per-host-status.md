---
type: llm
weight: 1
---
Score 1 only if the answer gives a script that pings EACH of 10.0.0.1, 10.0.0.2 and 10.0.0.3 (e.g. a loop), prints an explicit OK or FAIL line per host based on that host's ping result, and continues to the remaining hosts after a failure (it does not exit on the first failed ping). Score 0 if it stops at the first failure, prints no per-host FAIL status, or only mentions the commands without a working per-host OK/FAIL control flow.
