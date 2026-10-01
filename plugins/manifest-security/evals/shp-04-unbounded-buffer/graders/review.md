---
type: llm
focus: last_message
---
- Flags that `.read()` buffers an unbounded untrusted upstream body into memory (memory exhaustion / DoS), and recommends iterating line-by-line and aborting past a byte cap.
- Bonus (not required): recommends explicit handling of upstream failures that returns a fixed generic error to the client rather than exception text.
Pass if the first holds.
