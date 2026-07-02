#!/usr/bin/env bats
# Guardrail-registry invariants for configs/claude/config/knowledge_base.yml
# (spec 457, contracts/registry-schema.md). The registry is the single source
# of truth for proactive-coding anti-patterns consumed by the CLAUDE.md digest,
# references/antipatterns.md, the code-quality skill, and the ai-code-audit
# skill. These tests pin the schema so captures and edits cannot silently
# break downstream consumers.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
KB="$REPO_ROOT/configs/claude/config/knowledge_base.yml"

GUARDRAIL_TAGS="arch async-state error-handling security dependency iteration"

@test "knowledge_base.yml is valid YAML and passes yamllint" {
    run python3 -c "import yaml; yaml.safe_load(open('$KB'))"
    assert_success
    if command -v yamllint >/dev/null 2>&1; then
        run yamllint "$KB"
        assert_success
    fi
}

@test "severity values are within the allowed enum" {
    run python3 - "$KB" <<'EOF'
import sys, yaml
allowed = {"critical", "high", "medium", "low", "info"}
entries = yaml.safe_load(open(sys.argv[1]))["entries"]
bad = [e["id"] for e in entries if "severity" in e and e["severity"] not in allowed]
if bad:
    sys.exit(f"invalid severity on: {bad}")
EOF
    assert_success
}

@test "every research-seed entry has a prevention_rule and exactly one guardrail tag" {
    run python3 - "$KB" <<'EOF'
import sys, yaml
tags = {"arch", "async-state", "error-handling", "security", "dependency", "iteration"}
entries = yaml.safe_load(open(sys.argv[1]))["entries"]
seeds = [e for e in entries if e.get("provenance") == "research-seed"]
if not seeds:
    sys.exit("no research-seed entries found")
missing_rule = [e["id"] for e in seeds if not str(e.get("prevention_rule", "")).strip()]
bad_tags = [e["id"] for e in seeds if len(tags & set(e.get("tags", []))) != 1]
if missing_rule or bad_tags:
    sys.exit(f"missing prevention_rule: {missing_rule}; !=1 guardrail tag: {bad_tags}")
EOF
    assert_success
}

@test "session-capture entries follow the same guardrail conventions" {
    # Same invariants as seeds, applied to entries captured after ship —
    # keeps SC-005 (capture-to-active) honest. Passes vacuously until the
    # first capture lands.
    run python3 - "$KB" <<'EOF'
import sys, yaml
tags = {"arch", "async-state", "error-handling", "security", "dependency", "iteration"}
entries = yaml.safe_load(open(sys.argv[1]))["entries"]
caps = [e for e in entries if e.get("provenance") == "session-capture"]
missing_rule = [e["id"] for e in caps if not str(e.get("prevention_rule", "")).strip()]
bad_tags = [e["id"] for e in caps if len(tags & set(e.get("tags", []))) != 1]
if missing_rule or bad_tags:
    sys.exit(f"missing prevention_rule: {missing_rule}; !=1 guardrail tag: {bad_tags}")
EOF
    assert_success
}

@test "all six guardrail categories are represented" {
    run python3 - "$KB" <<'EOF'
import sys, yaml
tags = {"arch", "async-state", "error-handling", "security", "dependency", "iteration"}
entries = yaml.safe_load(open(sys.argv[1]))["entries"]
present = {t for e in entries for t in e.get("tags", []) if t in tags}
missing = tags - present
if missing:
    sys.exit(f"guardrail categories with zero entries: {sorted(missing)}")
EOF
    assert_success
}

@test "guardrail-tagged entry count meets the SC-001 floor (>=25)" {
    run python3 - "$KB" <<'EOF'
import sys, yaml
tags = {"arch", "async-state", "error-handling", "security", "dependency", "iteration"}
entries = yaml.safe_load(open(sys.argv[1]))["entries"]
n = sum(1 for e in entries if tags & set(e.get("tags", [])))
if n < 25:
    sys.exit(f"only {n} guardrail-tagged entries (floor: 25)")
EOF
    assert_success
}

@test "entry IDs are unique" {
    run python3 - "$KB" <<'EOF'
import sys, yaml
from collections import Counter
entries = yaml.safe_load(open(sys.argv[1]))["entries"]
dupes = [i for i, c in Counter(e["id"] for e in entries).items() if c > 1]
if dupes:
    sys.exit(f"duplicate entry IDs: {dupes}")
EOF
    assert_success
}
