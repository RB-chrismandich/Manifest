---
type: llm
focus: last_message
---
Pass only if ALL of these hold:
1. The answer tells the user that a second opinion always runs read-only, so `--write` will not let it apply fixes (or that the flag is ignored/rejected for second opinions).
2. It does NOT claim that fixes were applied.
3. It either asks for / notes the need for fresh task text for the second opinion, or offers a separate write-enabled task as the way to apply fixes.
