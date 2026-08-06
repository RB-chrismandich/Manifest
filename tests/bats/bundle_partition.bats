#!/usr/bin/env bats
# T3.6 (spec 674) — the partition invariants, checked WITHOUT the claude CLI.
#
# `grep -c 'claude plugin' .github/workflows/ci.yml` was 0 before this feature:
# CI never installs that CLI. So every gate phrased as
# `claude plugin validate --strict` is either unrunnable there or skips green,
# and a skip that renders as a pass is the exact false green this phase exists
# to remove. These assertions are pure python3 + bats and therefore always run.
#
# The invariant that matters most is IDENTITY, not count. A misplaced skill --
# one assigned to the wrong bundle -- keeps every total correct and ships that
# skill into a domain the user never installed. Totals cannot see it; the
# symmetric-difference checks below can.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
REGISTRY="$REPO_ROOT/configs/claude/config/skill_policies.yml"
MARKETPLACE="$REPO_ROOT/.claude-plugin/marketplace.json"

py() { python3 - "$@"; }

@test "every manifest's skills[] path exists on disk, including independent addons" {
    run py <<'PY'
import json, pathlib, sys
root = pathlib.Path(".")
missing = []
docker_skills = []
for pj in sorted(root.glob("plugins/*/.claude-plugin/plugin.json")):
    man = json.loads(pj.read_text())
    base = pj.parent.parent
    for rel in man.get("skills", []):
        if man["name"] == "manifest-docker":
            docker_skills.append(rel)
        if not (base / rel[2:] / "SKILL.md").is_file():
            missing.append(f"{man['name']}:{rel}")
if not docker_skills:
    missing.append("manifest-docker: no declared skills")
print("MISSING=" + ",".join(missing) if missing else "MISSING=")
sys.exit(1 if missing else 0)
PY
    assert_success
}

@test "the domain-plus-policy-addon manifest union equals the registry key set" {
    # Both directions on purpose: one direction alone lets a skill be dropped
    # from the manifests (ships nowhere) or invented in them (installs nothing).
    run py <<'PY'
import json, pathlib, sys
reg = pathlib.Path("configs/claude/config/skill_policies.yml").read_text()
registry = set()
seen = False
for line in reg.splitlines():
    if line.startswith("bundles:"):
        seen = True; continue
    if seen and line.startswith("    - "):
        registry.add(line.strip()[2:].strip())
    elif seen and line and not line.startswith(" "):
        seen = False
manifests = set()
docker_skills = set()
for pj in pathlib.Path(".").glob("plugins/*/.claude-plugin/plugin.json"):
    manifest = json.loads(pj.read_text())
    names = {rel.rsplit("/", 1)[-1] for rel in manifest.get("skills", [])}
    if manifest["name"] == "manifest-docker":
        docker_skills = names
        continue
    for rel in manifest.get("skills", []):
        manifests.add(rel.rsplit("/", 1)[-1])
marketplace = json.loads(pathlib.Path(".claude-plugin/marketplace.json").read_text())
marketplace_names = {entry["name"] for entry in marketplace["plugins"]}
only_reg = sorted(registry - manifests)
only_man = sorted(manifests - registry)
docker_in_registry = sorted(registry & docker_skills)
if "manifest-docker" not in marketplace_names:
    print("MISSING INDEPENDENT MARKETPLACE ADDON: manifest-docker")
if not docker_skills:
    print("MISSING INDEPENDENT ADDON SKILLS: manifest-docker")
if only_reg: print("IN REGISTRY NOT MANIFESTS:", only_reg)
if only_man: print("IN MANIFESTS NOT REGISTRY:", only_man)
if docker_in_registry: print("INDEPENDENT ADDON IN POLICY REGISTRY:", docker_in_registry)
sys.exit(1 if (only_reg or only_man or docker_in_registry or
               "manifest-docker" not in marketplace_names or not docker_skills) else 0)
PY
    assert_success
}

@test "domain and addon partitions are disjoint and match their explicit totals" {
    run py <<'PY'
import json, pathlib, re, sys
text = pathlib.Path("configs/claude/config/skill_policies.yml").read_text()
domain_expected = int(re.search(r"^domain_expected_total:\s*(\d+)", text, re.M).group(1))
addon_expected = int(re.search(r"^addon_expected_total:\s*(\d+)", text, re.M).group(1))
expected = int(re.search(r"^expected_total:\s*(\d+)", text, re.M).group(1))
seen, dupes, domain_total = {}, [], 0
docker_skills = set()
for pj in sorted(pathlib.Path(".").glob("plugins/manifest-*/.claude-plugin/plugin.json")) + [pathlib.Path("plugins/stitch-design/.claude-plugin/plugin.json")]:
    man = json.loads(pj.read_text())
    if man["name"] == "manifest-docker":
        docker_skills = {rel.rsplit("/", 1)[-1] for rel in man.get("skills", [])}
        continue
    for rel in man.get("skills", []):
        name = rel.rsplit("/", 1)[-1]
        domain_total += 1
        if name in seen:
            dupes.append(f"{name} in {seen[name]} and {man['name']}")
        seen[name] = man["name"]
addon_names = {
    path.parent.name
    for path in pathlib.Path("plugins/adversarial-design-loop/skills").glob("*/SKILL.md")
}
addon_total = len(addon_names)
overlap = sorted(set(seen) & addon_names)
independent_overlap = sorted((set(seen) | addon_names) & docker_skills)
if dupes: print("DUPLICATED:", dupes)
if overlap: print("DOMAIN/ADDON OVERLAP:", overlap)
if not docker_skills: print("MISSING INDEPENDENT ADDON SKILLS: manifest-docker")
if independent_overlap: print("INDEPENDENT ADDON OVERLAP:", independent_overlap)
if domain_total != domain_expected:
    print(f"DOMAIN {domain_total} != domain_expected_total {domain_expected}")
if addon_total != addon_expected:
    print(f"ADDON {addon_total} != addon_expected_total {addon_expected}")
if domain_total + addon_total != expected:
    print(f"TOTAL {domain_total + addon_total} != expected_total {expected}")
sys.exit(1 if (
    dupes or overlap or not docker_skills or independent_overlap or
    domain_total != domain_expected or addon_total != addon_expected or
    domain_total + addon_total != expected
) else 0)
PY
    assert_success
}

@test "each marketplace entry's version matches its plugin.json byte-for-byte" {
    # Measured: plugin.json wins at install time and the entry's copy is
    # silently ignored, with only --strict noticing. Users would install 1.1.0
    # while the marketplace advertised 1.0.0, with nothing red anywhere.
    run py <<'PY'
import json, pathlib, sys
mk = json.loads(pathlib.Path(".claude-plugin/marketplace.json").read_text())
bad = []
for e in mk["plugins"]:
    pj = pathlib.Path("plugins") / e["name"] / ".claude-plugin" / "plugin.json"
    if not pj.is_file():
        bad.append(f"{e['name']}: no plugin.json"); continue
    man = json.loads(pj.read_text())
    if man.get("version") != e.get("version"):
        bad.append(f"{e['name']}: entry {e.get('version')} vs manifest {man.get('version')}")
if bad: print("VERSION DRIFT:", bad)
sys.exit(1 if bad else 0)
PY
    assert_success
}

@test "manifests carry no marketplace-only or forbidden keys" {
    # `strict` and `category` belong to the marketplace ENTRY; the validator
    # warns on them in plugin.json. `$schema`'s declared URL 404s. `dependencies`
    # buys installation but not resolution, so it ships absent, not empty.
    run py <<'PY'
import json, pathlib, sys
bad = []
for pj in sorted(pathlib.Path(".").glob("plugins/*/.claude-plugin/plugin.json")):
    man = json.loads(pj.read_text())
    for key in ("$schema", "dependencies", "strict", "category"):
        if key in man:
            bad.append(f"{man['name']}: {key}")
if bad: print("FORBIDDEN KEYS:", bad)
sys.exit(1 if bad else 0)
PY
    assert_success
}

@test "the generated mirror resolves 1:1 with the plugin sources" {
    run bash -c "
        src=\$(find '$REPO_ROOT/plugins' -path '*/skills/*/SKILL.md' | wc -l | tr -d ' ')
        mir=\$(find '$REPO_ROOT/.apm/skills' -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')
        [ \"\$src\" = \"\$mir\" ] || { echo \"src=\$src mirror=\$mir\"; exit 1; }
        echo \"\$src\""
    assert_success
}

@test "the mirror contains real files, never symlinks" {
    # A committed-symlink mirror would deploy links resolving to \$HOME/plugins/...
    # -- a path on no machine -- while every repo-side gate stayed green, because
    # ci.yml uses `find -L` and the bats fixtures build real dirs.
    run bash -c "find '$REPO_ROOT/.apm/skills' -type l | wc -l | tr -d ' '"
    assert_output "0"
}

@test "every skill's frontmatter parses and declares name + description" {
    # `claude plugin validate --strict` caught pr-address-comments here: an
    # unquoted description containing ': ' parsed as a nested key, and that skill
    # loaded with EMPTY metadata -- it could never trigger. No other gate in this
    # repo noticed, so the invariant is pinned here where it always runs.
    run py <<'PY'
import pathlib, sys
try:
    import yaml
except ImportError:
    print("pyyaml missing"); sys.exit(0)
bad = []
for f in sorted(pathlib.Path(".").glob("plugins/*/skills/*/SKILL.md")):
    t = f.read_text(encoding="utf-8")
    if not t.startswith("---"):
        bad.append(f"{f.parent.name}: no frontmatter"); continue
    try:
        d = yaml.safe_load(t.split("---", 2)[1])
        if not isinstance(d, dict) or "name" not in d or "description" not in d:
            bad.append(f"{f.parent.name}: missing name/description")
    except Exception as exc:
        bad.append(f"{f.parent.name}: {str(exc).splitlines()[0][:60]}")
if bad: print("BAD FRONTMATTER:", bad)
sys.exit(1 if bad else 0)
PY
    assert_success
}

@test "each skill's BUNDLE matches the registry, not merely its name" {
    # The blind spot every set-based check has. A skill moved to the wrong bundle
    # -- directory AND manifest together -- keeps the union, the total and the
    # disjointness all correct, and ships that skill into a domain the user never
    # installed. Only a name->bundle comparison sees it. T3.6's own disjointness
    # assertion cannot.
    run py <<'PY'
import json, pathlib, sys
text = pathlib.Path("configs/claude/config/skill_policies.yml").read_text()
registry, bundle, seen = {}, None, False
for line in text.splitlines():
    if line.startswith("bundles:"):
        seen = True; continue
    if not seen:
        continue
    stripped = line.split("#", 1)[0].rstrip()
    if stripped.startswith("  ") and stripped.endswith(":") and not stripped.startswith("    "):
        bundle = stripped.strip()[:-1]
    elif line.startswith("    - ") and bundle:
        registry[line.strip()[2:].strip()] = bundle
    elif line and not line.startswith(" "):
        seen = False

wrong = []
for pj in sorted(pathlib.Path(".").glob("plugins/*/.claude-plugin/plugin.json")):
    man = json.loads(pj.read_text())
    if man["name"] == "manifest-docker":
        for rel in man.get("skills", []):
            name = rel.rsplit("/", 1)[-1]
            if name in registry:
                wrong.append(f"{name}: independent manifest-docker skill is in registry")
        continue
    for rel in man.get("skills", []):
        name = rel.rsplit("/", 1)[-1]
        want = registry.get(name)
        if want != man["name"]:
            wrong.append(f"{name}: manifest={man['name']} registry={want}")
if wrong: print("WRONG BUNDLE:", wrong)
sys.exit(1 if wrong else 0)
PY
    assert_success
}

@test "plugin bodies carry QUALIFIED cross-skill names" {
    # Post-cutover a bare /name is an Unknown command in Claude Code. This is
    # the shipped form, so it is the one that must be qualified.
    run bash -c "python3 '$REPO_ROOT/configs/claude/scripts/skill_reference_check.py' 2>/dev/null | tail -1"
    assert_output --partial "blocking=0"
}

@test "the MIRROR carries BARE names, because its consumers have no namespace" {
    # ~/.manifest/skills is a FLAT tree read by cursor, gemini, codex,
    # antigravity and devin. None of them know a bundle namespace, so a
    # qualified name there points at a command that cannot exist. One source,
    # two renderings.
    run bash -c "grep -rlE '/manifest-[a-z-]+:|/stitch-design:' '$REPO_ROOT/.apm/skills/' 2>/dev/null | wc -l | tr -d ' '"
    assert_output "0"
}

@test "the mirror still carries the reference, just unqualified" {
    # Guards against the bare-rendering being a blunt delete: stripping the
    # whole reference would also produce zero qualified names.
    run bash -c "grep -c '/docs-improve' '$REPO_ROOT/.apm/skills/docs-all/SKILL.md'"
    assert_success
    [ "$output" -ge 1 ]
}
