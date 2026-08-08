---
name: test-isolate-ambient
description: Design tests that replace real home, XDG state, network, installed harnesses, and repository globals with explicit fixtures so broken code cannot pass on ambient state.
---

# Isolate Ambient State

Name every ambient input the behavior could read: home, XDG roots, network,
`PATH`, installed harness inventory, credentials, repository state, and time.
Redirect each to a throwaway fixture and vary the decisive input inside the
test.

For installed plugin runtime tests, use an empty `HOME`, isolated XDG roots,
`UV_NO_NETWORK=1`, fixture harness binaries only, and a working directory with
no source checkout. Execute commands by their bundle-local entry points and
assert that missing state produces an explicit degraded result rather than a
false green.

Prove the test fails against the legacy behavior before accepting the fix.
