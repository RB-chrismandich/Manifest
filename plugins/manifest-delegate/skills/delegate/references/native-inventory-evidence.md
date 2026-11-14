# Native-inventory wire evidence

When delegating reconcile or native-inventory work, quote producer-defined field
names for component, package, and inspection records — not reconstructed JSON.
Fixtures must come from those producer dataclass serializers or from captured
real responses; matching self-authored fakes alone do not establish
compatibility.

For OMP-backed inventory, population logic must emit the same field contract as
the core inspection models. Pattern offline checks after serializing producer
objects in a clean process (as in the repository's reconcile native-evidence
regression tests); that is wire evidence only, not live activation
qualification. Record a separate live OMP read-only probe when the brief
requires verified discovery or activation.