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
import glob, os, re, sys
import yaml

repo, check = sys.argv[1], sys.argv[2]
skills_dir = os.path.join(repo, ".apm/skills")
cfg = os.path.join(repo, "configs/claude/config/command_config.yml")

skills = sorted(
    d for d in os.listdir(skills_dir)
    if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
)
with open(cfg, encoding="utf-8") as fh:
    policy = yaml.safe_load(fh) or {}
tp = policy.get("tool_policies", {}) or {}
VALID = {"always", "conditional", "never"}
MARKER = "## Sub-agent dispatch"

def body(s):
    with open(os.path.join(skills_dir, s, "SKILL.md"), encoding="utf-8") as fh:
        return fh.read()

def entry(s):
    return tp.get(s) or {}

def dispatch_section(s):
    """The '## Sub-agent dispatch' section body, or '' when absent."""
    out, on = [], False
    for line in body(s).splitlines():
        if line.startswith(MARKER):
            on = True
            continue
        if on and line.startswith("## "):
            break
        if on:
            out.append(line)
    return "\n".join(out)

def bundled_omp_contract(s):
    """Return whether the source skill links a resolvable, local OMP contract."""
    sources = glob.glob(os.path.join(repo, "plugins", "*", "skills", s, "SKILL.md"))
    if len(sources) != 1:
        return False
    source = sources[0]
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    section, on = [], False
    for line in text.splitlines():
        if line.startswith(MARKER):
            on = True
            continue
        if on and line.startswith("## "):
            break
        if on:
            section.append(line)
    section_text = "\n".join(section)
    links = re.findall(r"`([^`]+\.md)`", section_text)
    links += re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", section_text)
    for link in links:
        candidate = os.path.normpath(os.path.join(os.path.dirname(source), link))
        if os.path.isfile(candidate):
            with open(candidate, encoding="utf-8") as fh:
                if re.search(r"\bOMP\b.*`task`", fh.read(), re.I):
                    return True
    return False

fail = []

if check == "retired_config":    # T0
    retired = {
        "parallel_agents", "subagent_model", "session_model",
        "session_model_rationale", "harness_routing", "consensus",
        "synthesis_priority", "error_recovery", "task_model_defaults",
        "parallel_agent", "script_path", "output_dir", "default_options",
        "modes",
    }
    def walk(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key) in retired:
                    fail.append(f"{child_path}: retired coordinator setting")
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
    walk(policy)
elif check == "coverage":          # T1
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
    local_dispatch_ref = re.compile(
        r"\[[^\]]+\]\((references/[A-Za-z0-9_-]+-dispatch\.md)\)"
    )
    shared_dispatch_ref = "sub-agent-dispatch.md"
    for s in skills:
        if entry(s).get("subagents") not in ("always", "conditional"):
            continue
        b = body(s)
        if MARKER not in b:
            fail.append(f"{s}: {entry(s)['subagents']} but no '{MARKER}' section")
            continue
        section = dispatch_section(s)
        match = local_dispatch_ref.search(section)
        if match:
            path = os.path.join(skills_dir, s, match.group(1))
            if not os.path.isfile(path):
                fail.append(
                    f"{s}: local dispatch reference does not resolve: {match.group(1)}"
                )
        elif shared_dispatch_ref not in section:
            fail.append(
                f"{s}: dispatch section does not link a selection-reference contract"
            )
elif check == "no_contradiction":      # T6
    # A `never` skill may not contain an explicit OMP task dispatch. The body
    # section heading catches declared dispatch guidance; matching task calls
    # catches an undeclared dispatch that would otherwise evade the policy.
    DISPATCH_RE = re.compile(r"\btask\s*\(", re.I)
    for s in skills:
        if entry(s).get("subagents") != "never":
            continue
        b = body(s)
        if MARKER in b:
            fail.append(f"{s}: never but body contains a '{MARKER}' section")
        hits = [i + 1 for i, line in enumerate(b.splitlines()) if DISPATCH_RE.search(line)]
        if hits:
            fail.append(
                f"{s}: never but body dispatches a sub-agent at line(s) "
                f"{', '.join(map(str, hits))} (task(...)) — reclassify as "
                f"conditional or remove the dispatch"
            )
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

@test "command policy has no custom coordinator settings or provider-model routing" {
    run run_check retired_config
    [ "$status" -eq 0 ] || { echo "$output"; false; }
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

@test "always/conditional skills have an in-body selection-reference contract" {
    run run_check body_trigger
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

@test "never skills do not instruct dispatch (no contradiction)" {
    run run_check no_contradiction
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}
