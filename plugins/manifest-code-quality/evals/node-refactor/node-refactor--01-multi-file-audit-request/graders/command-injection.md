---
type: llm
weight: 1
---
Score 1 only if the answer flags `exec(\`convert ${filename} output.png\`, cb)` in `src/handlers/upload.ts` as a command injection vulnerability because `filename` is interpolated unsanitized into a shell command run via `exec`, rates it Critical, AND proposes replacing `exec` with `execFile("convert", [filename, "output.png"], cb)` (or equivalent argument-array API) to avoid shell interpretation. Score 0 otherwise.
