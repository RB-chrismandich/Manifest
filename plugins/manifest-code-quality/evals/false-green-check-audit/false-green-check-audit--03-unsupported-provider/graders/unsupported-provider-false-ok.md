---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the `*) return 0 ;;` default branch in `check_provider` makes any unrecognized/unsupported provider (e.g. calling the script with `jira`, which has no `case` arm) print "OK: $provider is configured" even though nothing was actually checked for it, and proposes distinguishing this "unsupported, cannot verify" outcome from a real OK/pass (e.g. a dedicated exit code or an "UNSUPPORTED: $provider — cannot verify" message instead of the green "OK" line). Score 0 if the default `*)` branch's false-OK behavior is not identified, or the answer only discusses the github/gitlab/linear branches.
