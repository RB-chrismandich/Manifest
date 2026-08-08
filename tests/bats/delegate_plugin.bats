#!/usr/bin/env bats
# T035: hook-wiring gate for plugins/manifest-delegate/hooks/hooks.json — no
# repo precedent exists for this shape, so this file IS the gate. Asserts the
# hooks.json declares exactly Stop/SessionStart/SessionEnd with timeouts
# 900/5/5, referenced scripts exist and are executable, ${CLAUDE_PLUGIN_ROOT}
# is used (no absolute paths), and the Stop wrapper timeout outlasts the
# code-level gate-budget cap (840s, data-model.md review_gate.budget_seconds).

setup() {
  ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
  PLUGIN_DIR="$ROOT/plugins/manifest-delegate"
  HOOKS_JSON="$PLUGIN_DIR/hooks/hooks.json"
}

@test "hooks.json is valid JSON" {
  python3 -c "import json; json.load(open('$HOOKS_JSON'))"
}

@test "hooks.json declares exactly Stop, SessionStart, SessionEnd" {
  run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))
keys = sorted(d.get('hooks', {}).keys())
assert keys == ['SessionEnd', 'SessionStart', 'Stop'], keys
print('ok')
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "hooks.json timeouts are 900/5/5 for Stop/SessionStart/SessionEnd" {
  run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))['hooks']
def timeout_of(event):
    return d[event][0]['hooks'][0]['timeout']
assert timeout_of('Stop') == 900, timeout_of('Stop')
assert timeout_of('SessionStart') == 5, timeout_of('SessionStart')
assert timeout_of('SessionEnd') == 5, timeout_of('SessionEnd')
print('ok')
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "hooks.json commands use \${CLAUDE_PLUGIN_ROOT}, never an absolute path" {
  run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))['hooks']
for event, entries in d.items():
    for entry in entries:
        for h in entry['hooks']:
            cmd = h['command']
            assert '\${CLAUDE_PLUGIN_ROOT}' in cmd, (event, cmd)
            assert '$PLUGIN_DIR' not in cmd, (event, cmd)
print('ok')
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "hooks.json referenced scripts exist and are executable" {
  run python3 -c "
import json, os, re
d = json.load(open('$HOOKS_JSON'))['hooks']
plugin_dir = '$PLUGIN_DIR'
for entries in d.values():
    for entry in entries:
        for h in entry['hooks']:
            cmd = h['command']
            rel = re.search(r'\\\$\{CLAUDE_PLUGIN_ROOT\}(/[^ ]+)', cmd).group(1)
            path = plugin_dir + rel
            assert os.path.isfile(path), path
            assert os.access(path, os.X_OK), path
print('ok')
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "stop_gate_hook.py and session_hook.py are --help compliant" {
  run python3 "$PLUGIN_DIR/scripts/stop_gate_hook.py" --help
  [ "$status" -eq 0 ]
  run python3 "$PLUGIN_DIR/scripts/session_hook.py" --help
  [ "$status" -eq 0 ]
}

@test "stop hook wrapper timeout outlasts the gate backend budget cap" {
  # The wrapper subprocess timeout must EXCEED the backend budget cap
  # (GATE_BUDGET_CAP_SECONDS=840, data-model.md review_gate.budget_seconds 1-840)
  # so the gate reaches its own backend timeout and reaps the detached backend
  # BEFORE the wrapper kills delegate.py. Equal timeouts (the old <=840 assertion)
  # were a guaranteed collision — codex adversarial-review fix; the 840s cap was
  # itself "900s hook window minus overhead". Python drift guard:
  # tests/python/test_stop_gate_hook.py.
  run python3 -c "
import re
src = open('$PLUGIN_DIR/scripts/stop_gate_hook.py').read()
m = re.search(r'GATE_WRAPPER_TIMEOUT_SECONDS\s*=\s*(\d+)', src)
assert m, 'no GATE_WRAPPER_TIMEOUT_SECONDS constant found'
val = int(m.group(1))
assert val > 840, val
assert 'timeout=GATE_WRAPPER_TIMEOUT_SECONDS' in src, 'wrapper does not use the constant'
print('ok', val)
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "SessionStart/SessionEnd hooks respond exit 0 to a minimal payload (no gate subcommand invoked)" {
  # T031 (gate subcommand) may not exist yet in a concurrently-edited
  # delegate.py; session_hook.py never calls delegate.py, so this is safe to
  # assert unconditionally.
  run bash -c "echo '{\"hook_event_name\":\"SessionStart\",\"session_id\":\"t1\",\"transcript_path\":\"/tmp/x.jsonl\"}' | python3 '$PLUGIN_DIR/scripts/session_hook.py'"
  [ "$status" -eq 0 ]
  run bash -c "echo '{\"hook_event_name\":\"SessionEnd\",\"session_id\":\"t1\"}' | python3 '$PLUGIN_DIR/scripts/session_hook.py'"
  [ "$status" -eq 0 ]
}

@test "stop_gate_hook.py fails open (exit 0) when transcript_path is missing" {
  # Tolerant of gate subcommand (T031) not existing yet — this path never
  # reaches delegate.py because transcript_path is absent.
  run bash -c "echo '{\"hook_event_name\":\"Stop\"}' | python3 '$PLUGIN_DIR/scripts/stop_gate_hook.py'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"systemMessage"* ]]
}

# T045: registration gates — plugin.json skills array, marketplace.json entry,
# skill_policies bundle block + expected_total, backends.json<->parallel_agent.yml
# binary drift, services.yml reader<->write_services_config() drift.

@test "plugin.json declares an explicit skills array with delegate + delegate-setup" {
  run python3 -c "
import json
d = json.load(open('$PLUGIN_DIR/.claude-plugin/plugin.json'))
skills = d.get('skills')
assert isinstance(skills, list) and skills, skills
names = sorted(s.rstrip('/').split('/')[-1] for s in skills)
assert names == ['delegate', 'delegate-setup'], names
print('ok')
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "marketplace.json has a manifest-delegate entry sourced at plugins/manifest-delegate" {
  run python3 -c "
import json
d = json.load(open('$ROOT/.claude-plugin/marketplace.json'))
plugins = d.get('plugins', d) if isinstance(d, dict) else d
entries = plugins if isinstance(plugins, list) else plugins.get('plugins', [])
match = [p for p in entries if p.get('name') == 'manifest-delegate']
assert match, 'no manifest-delegate entry found'
assert match[0].get('source') == './plugins/manifest-delegate', match[0]
print('ok')
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "skill_policies.yml has a manifest-delegate bundle block matching plugin.json skills, counted in expected_total" {
  run python3 -c "
import yaml, json
sp = yaml.safe_load(open('$ROOT/configs/claude/config/skill_policies.yml'))
bundle = sp.get('manifest-delegate') or sp.get('bundles', {}).get('manifest-delegate')
assert bundle, 'manifest-delegate bundle block missing'
assert sorted(bundle) == ['delegate', 'delegate-setup'], bundle
pj = json.load(open('$PLUGIN_DIR/.claude-plugin/plugin.json'))
pj_names = sorted(s.rstrip('/').split('/')[-1] for s in pj['skills'])
assert sorted(bundle) == pj_names, (bundle, pj_names)
total = sp.get('expected_total')
assert isinstance(total, int) and total > 0, total
print('ok', total)
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "backends.json binaries stay consistent with parallel_agent.yml cli_agents for shared backend ids" {
  run python3 -c "
import json, re
backends = json.load(open('$PLUGIN_DIR/config/backends.json'))['backends']
by_id = {b['id']: b['binary'] for b in backends}
raw = open('$ROOT/configs/claude/config/parallel_agent.yml').read()
sec = re.search(r'^cli_agents:\n(.*?)(?=^\S|\Z)', raw, re.S | re.M).group(1)
entries = {}
for m in re.finditer(r'^  (\w[\w-]*):\n(?:    .*\n)*', sec, re.M):
    name = m.group(1)
    binm = re.search(r'binary:\s*(\S+)', m.group(0))
    if binm:
        entries[name] = binm.group(1)
shared = set(by_id) & set(entries)
assert shared, 'no shared backend ids found between registries'
mismatches = {k: (by_id[k], entries[k]) for k in shared if by_id[k] != entries[k]}
assert not mismatches, mismatches
print('ok', sorted(shared))
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}

@test "services.yml fixed-format reader stays matched to write_services_config() in bootstrap/lib/config.sh" {
  run python3 -c "
import re, yaml
svc = yaml.safe_load(open('$ROOT/configs/claude/config/services.yml'))
keys = set(svc.get('services', {}).keys())
assert keys, 'services.yml has no services'
src = open('$ROOT/bootstrap/lib/config.sh').read()
m = re.search(r'write_services_config\(\)\s*\{.*?\n\}', src, re.S)
assert m, 'write_services_config() not found'
body = m.group(0)
written_keys = set(re.findall(r'^  (\w[\w-]*):\s*$', body, re.M))
assert written_keys, 'no service keys found in write_services_config()'
missing = keys - written_keys
assert not missing, ('services.yml keys not written by write_services_config()', missing)
print('ok', sorted(keys))
"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ok"* ]]
}
