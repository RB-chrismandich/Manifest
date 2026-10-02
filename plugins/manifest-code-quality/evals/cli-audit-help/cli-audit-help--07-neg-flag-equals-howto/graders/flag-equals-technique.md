---
type: llm
weight: 1
---
Score 1 only if the answer explains handling both forms in an argument-parsing loop using a `case` pattern such as `--flag=*)` combined with parameter expansion (e.g. `value="${1#*=}"`) for the `=`-joined form, plus a separate `--flag)` branch that does `shift` and reads the next positional argument for the space-separated form. Score 0 if it does not cover both forms or gives no concrete working pattern.
