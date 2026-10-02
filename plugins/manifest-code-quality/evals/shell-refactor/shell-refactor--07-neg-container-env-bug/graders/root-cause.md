---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the minimal/base Docker image does not have `HOME` set in its environment (no matching passwd entry / no ENV HOME set), so under `set -u` (nounset) the reference to `$HOME` aborts the script with "unbound variable", AND proposes a fix such as setting `ENV HOME=/root` (or an appropriate home dir) in the image, exporting `HOME` in the entrypoint, or using a default expansion like `${HOME:-/root}`. Score 0 otherwise.
