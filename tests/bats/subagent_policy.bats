#!/usr/bin/env bats
# Feature 367 — Sub-agent dispatch guidance enforcement.
# Verifies every skill has a `subagents` disposition in tool_policies and that
# SKILL.md prose triggers do not contradict it. Skills are enumerated
# DYNAMICALLY (no hardcoded count), so a new skill without a disposition fails
# here until it is classified. See configs/claude/references/sub-agent-dispatch.md.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"

# Run a named check implemented in the embedded Python helper; the helper exits
# non-zero and prints offending skills on failure.
run_check() {
    python3 - "$REPO_ROOT" "$1" <<'PY'
import os, sys
import yaml

repo, check = sys.argv[1], sys.argv[2]
skills_dir = os.path.join(repo, ".skillshare/skills")
cfg = os.path.join(repo, "configs/claude/config/command_config.yml")

skills = sorted(
    d for d in os.listdir(skills_dir)
    if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
)
with open(cfg, encoding="utf-8") as fh:
    tp = (yaml.safe_load(fh) or {}).get("tool_policies", {}) or {}
VALID = {"always", "conditional", "never"}
MARKER = "## Sub-agent dispatch"

def body(s):
    with open(os.path.join(skills_dir, s, "SKILL.md"), encoding="utf-8") as fh:
        return fh.read()

def entry(s):
    return tp.get(s) or {}

fail = []

if check == "coverage":          # T1
    for s in skills:
        if "subagents" not in entry(s):
            fail.append(f"{s}: no `subagents` disposition in tool_policies")
elif check == "enum":            # T2
    for s in skills:
        v = entry(s).get("subagents")
        if v is not None and v not in VALID:
            fail.append(f"{s}: invalid subagents value {v!r}")
elif check == "conditional_trigger":   # T3
    for s in skills:
        e = entry(s)
        if e.get("subagents") == "conditional" and not e.get("subagent_trigger"):
            fail.append(f"{s}: conditional but no subagent_trigger")
elif check == "never_rationale":       # T4
    for s in skills:
        e = entry(s)
        if e.get("subagents") == "never":
            if not e.get("subagent_rationale") and "Sub-agents: not used" not in body(s):
                fail.append(f"{s}: never but no rationale (config or SKILL.md)")
elif check == "body_trigger":          # T5
    for s in skills:
        if entry(s).get("subagents") in ("always", "conditional"):
            b = body(s)
            if MARKER not in b:
                fail.append(f"{s}: {entry(s)['subagents']} but no '{MARKER}' section")
            elif "sub-agent-dispatch.md" not in b:
                fail.append(f"{s}: dispatch section does not link the shared selection rules")
elif check == "no_contradiction":      # T6
    for s in skills:
        if entry(s).get("subagents") == "never" and MARKER in body(s):
            fail.append(f"{s}: never but body contains a '{MARKER}' section")
else:
    print(f"unknown check: {check}", file=sys.stderr)
    sys.exit(2)

if fail:
    print(f"{len(fail)} violation(s) for check '{check}':", file=sys.stderr)
    for f in fail:
        print("  - " + f, file=sys.stderr)
    sys.exit(1)
print(f"check '{check}' OK ({len(skills)} skills)")
PY
}

@test "every skill has a subagents disposition (dynamic coverage)" {
    run run_check coverage
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

@test "subagents values are valid enums" {
    run run_check enum
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

@test "conditional skills declare a subagent_trigger" {
    run run_check conditional_trigger
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

@test "never skills carry a rationale" {
    run run_check never_rationale
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

@test "always/conditional skills have an in-body trigger linking the shared rules" {
    run run_check body_trigger
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

@test "never skills do not instruct dispatch (no contradiction)" {
    run run_check no_contradiction
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}
