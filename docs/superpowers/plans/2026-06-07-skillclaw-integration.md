# SkillClaw Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture CLI-agent sessions through SkillClaw's local proxy and turn evolved `SKILL.md` files into reviewed PRs into `.retired skill supply/skills/`, fully managed by `bootstrap.sh` and fail-open by design.

**Architecture:** A new `bootstrap/lib/skillclaw.sh` installs/configures SkillClaw, `chmod 700`s its storage, writes fail-open runtime shell-wrapper functions, and supervises the proxy daemon. Capture is always-on and lossy; evolution + promotion run on demand via `scripts/skillclaw_promote.sh` (orchestrator) + `scripts/skillclaw_promote.py` (classify/validate) + `scripts/skillclaw_scrub.py` (secret redaction), reusing `git_ops.sh pr-create`. A `/skill-evolve` skill is the user entry point. Nothing reaches `.retired skill supply/skills/` without a merged PR.

**Tech Stack:** Bash (3.2-compatible, `set -euo pipefail`), Python 3.10+ (stdlib + PyYAML), bats (bats-support/bats-assert) for shell tests, pytest for Python tests, `git_ops.sh` for platform-agnostic PR creation, SkillClaw (Python, OpenAI/Anthropic-compatible proxy).

**Reference spec:** `docs/superpowers/specs/2026-06-07-skillclaw-integration-design.md`

**Conventions to follow (verified in-repo):**
- Scripts: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`, `set -euo pipefail`, dry-run default + `--apply` (mirror `branch_clean.sh`), python3 heredoc for YAML reads.
- bats: `load '../test_helper/bats-support/load'` + `bats-assert`, sandbox via `mktemp -d`, stub `print_*` helpers, `source` the lib under test.
- Toggle plumbing mirrors `antigravity` exactly across `config.sh` (defaults, arg-parse, `parse_services_config` awk, `load_existing_config`, `write_services_config`).
- Default toggle state is **disabled** (opt-in).

**Fixed defaults used throughout this plan:**
- Proxy port: `8765` · Storage root: `~/.skillclaw` · Evolve mode: `workflow`
- Staging branch prefix: `skillclaw/evolve-` · PR base: `main`
- Local evolve model default: Ollama `qwen2.5-coder` at `http://127.0.0.1:11434/v1`; cloud fallback: Anthropic `claude-haiku-4-5-20251001`.
- Concrete wrapped agents in V1: `claude` (ANTHROPIC_BASE_URL), `codex` (OPENAI_BASE_URL `/v1`). `gemini`/`cursor-agent` are a documented follow-up (Task 12) pending base-URL-support verification.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `bootstrap/lib/config.sh` (modify) | Add `skillclaw` toggle: default, arg-parse, awk parse, load, write. |
| `configs/claude/config/services.yml` (modify) | Committed registry: add `skillclaw:` block (`enabled: false`). |
| `configs/claude/config/skillclaw.yml` (create) | SkillClaw runtime config: port, storage, evolve provider/model, promotion settings. |
| `bootstrap/lib/skillclaw.sh` (create) | Install, non-interactive setup, `chmod 700`, wrapper write/remove, daemon lifecycle + supervisor. |
| `bootstrap.sh` (modify) | Source new lib; call install/config/deploy; summaries; help. |
| `configs/claude/scripts/skillclaw_scrub.py` (create) | Redact secrets from captured session files before evolve. |
| `configs/claude/scripts/skillclaw_promote.py` (create) | Classify evolved skills (NEW/CHANGED/UNCHANGED) + validate frontmatter → JSON. |
| `configs/claude/scripts/skillclaw_promote.sh` (create) | Orchestrate scrub→evolve→classify→verify→branch→`pr-create`. Dry-run default. |
| `.retired skill supply/skills/skill-evolve/SKILL.md` (create) | `/skill-evolve` entry point. |
| `.retired skill supply/skills/health-check/SKILL.md` (modify) | Add SkillClaw daemon/port/wrappers/perms checks. |
| `.retired skill supply/skills/sync-configs/SKILL.md` (modify) | Cover `skillclaw.yml` drift. |
| `tests/bats/skillclaw_config.bats` (create) | Toggle plumbing tests. |
| `tests/bats/skillclaw_lib.bats` (create) | Wrapper write/remove, chmod 700, daemon helper tests. |
| `tests/bats/skillclaw_promote.bats` (create) | Orchestrator idempotency + dry-run (mocked) tests. |
| `tests/python/test_skillclaw_scrub.py` (create) | Redaction tests. |
| `tests/python/test_skillclaw_promote.py` (create) | Classify + validation tests. |
| `CLAUDE.md`, `.claude/CLAUDE.md`, `docs/` (modify) | Document toggle, loop, kill switch, follow-ups. |

---

## Task 1: Config toggle plumbing

**Files:**
- Modify: `bootstrap/lib/config.sh` (defaults ~L25-39, arg-parse ~L125-135, awk ~L195-245, load ~L270-285, write heredoc ~L345-355)
- Modify: `configs/claude/config/services.yml`
- Test: `tests/bats/skillclaw_config.bats`

- [ ] **Step 1: Write the failing test**

Create `tests/bats/skillclaw_config.bats`:

```bash
#!/usr/bin/env bats
# Tests for SkillClaw toggle plumbing in bootstrap/lib/config.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/skillclaw_config.XXXXXX")
    export SERVICES_CONFIG="$SANDBOX/config/services.yml"
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/config.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "default skillclaw toggle is disabled (opt-in)" {
    set_bootstrap_defaults
    assert_equal "$ENABLE_SKILLCLAW" "false"
    assert_equal "$SKILLCLAW_SET" "false"
}

@test "--enable-skillclaw sets the toggle" {
    set_bootstrap_defaults
    parse_bootstrap_args --enable-skillclaw
    assert_equal "$ENABLE_SKILLCLAW" "true"
    assert_equal "$SKILLCLAW_SET" "true"
}

@test "write_services_config emits skillclaw section with enabled: false" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false
    export ENABLE_GH=auto ENABLE_GLAB=auto
    run write_services_config
    assert_success
    grep -q "^  skillclaw:" "$SERVICES_CONFIG"
    grep -A4 "^  skillclaw:" "$SERVICES_CONFIG" | grep -q "enabled: false"
}

@test "parse_services_config round-trips skillclaw enabled: true" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=true
    export ENABLE_GH=auto ENABLE_GLAB=auto
    write_services_config
    parse_services_config
    assert_equal "$FILE_SKILLCLAW" "true"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_config.bats`
Expected: FAIL — `ENABLE_SKILLCLAW: unbound variable` / no `skillclaw:` section.

- [ ] **Step 3: Add the default and the explicit-set tracker**

In `bootstrap/lib/config.sh`, in `set_bootstrap_defaults`, after the `ENABLE_ANTIGRAVITY=true` line add:

```bash
    ENABLE_SKILLCLAW=false
```

and after `ANTIGRAVITY_SET=false` add:

```bash
    SKILLCLAW_SET=false
```

- [ ] **Step 4: Add argument parsing**

In `parse_bootstrap_args`, after the `--disable-antigravity)` case block add:

```bash
            --enable-skillclaw)
                ENABLE_SKILLCLAW=true
                SKILLCLAW_SET=true
                shift
                ;;
            --disable-skillclaw)
                ENABLE_SKILLCLAW=false
                SKILLCLAW_SET=true
                shift
                ;;
```

- [ ] **Step 5: Add awk parsing in `parse_services_config`**

Add `FILE_SKILLCLAW=""` next to the other `FILE_*` initializers. In the awk program, add a section matcher next to the antigravity one:

```awk
            /^[[:space:]]*skillclaw:/ { section="skillclaw"; subsection="" }
```

and in **both** the `enabled: true` and `enabled: false` blocks add:

```awk
                if (section == "skillclaw") print "FILE_SKILLCLAW=true;"
```

```awk
                if (section == "skillclaw") print "FILE_SKILLCLAW=false;"
```

- [ ] **Step 6: Add load-existing wiring**

In `load_existing_config`, after the antigravity block add:

```bash
        if [[ "$SKILLCLAW_SET" == false && -n "$FILE_SKILLCLAW" ]]; then
            ENABLE_SKILLCLAW=$FILE_SKILLCLAW
        fi
```

- [ ] **Step 7: Add the write heredoc block**

In `write_services_config`, after the `antigravity:` block (before `# Git CLI tools`) add:

```bash
  # SkillClaw - auto-evolves SKILL.md skills from captured CLI-agent sessions
  # Install: bash scripts/install_skillclaw.sh  (managed by bootstrap/lib/skillclaw.sh)
  skillclaw:
    enabled: $ENABLE_SKILLCLAW
    command: skillclaw
    description: "Captures CLI-agent sessions; evolves skills into review PRs (opt-in)"
    proxy_port: 8765
    storage: ~/.skillclaw
EOF
```

> NOTE: the existing heredoc terminates with `EOF`; insert this block **inside** the existing heredoc body (before the `# Git CLI tools` comment line), do **not** add a second `EOF`. The `EOF` above is shown only to mark where the surrounding heredoc already ends.

- [ ] **Step 8: Update the committed registry**

In `configs/claude/config/services.yml`, after the `antigravity:` block add:

```yaml
  # SkillClaw - auto-evolves SKILL.md skills from captured CLI-agent sessions
  # Install: bash scripts/install_skillclaw.sh  (managed by bootstrap/lib/skillclaw.sh)
  skillclaw:
    enabled: false
    command: skillclaw
    description: "Captures CLI-agent sessions; evolves skills into review PRs (opt-in)"
    proxy_port: 8765
    storage: ~/.skillclaw
```

- [ ] **Step 9: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_config.bats`
Expected: PASS (4 tests).

- [ ] **Step 10: Validate YAML + lint**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/services.yml'))" && echo OK
shellcheck bootstrap/lib/config.sh
```
Expected: `OK`, shellcheck clean.

- [ ] **Step 11: Commit**

```bash
git add bootstrap/lib/config.sh configs/claude/config/services.yml tests/bats/skillclaw_config.bats
git commit -m "feat(bootstrap): add skillclaw service toggle (default disabled)"
```

---

## Task 2: SkillClaw runtime config file

**Files:**
- Create: `configs/claude/config/skillclaw.yml`
- Test: `tests/bats/skillclaw_config.bats` (append one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/bats/skillclaw_config.bats`:

```bash
@test "skillclaw.yml exists and has required keys" {
    local f="$REPO_ROOT/configs/claude/config/skillclaw.yml"
    [ -f "$f" ]
    run python3 -c "import yaml,sys; c=yaml.safe_load(open('$f')); \
        assert c['proxy']['port']==8765; \
        assert c['storage']['root']=='~/.skillclaw'; \
        assert c['evolve']['mode']=='workflow'; \
        assert c['promotion']['branch_prefix']=='skillclaw/evolve-'; \
        assert c['evolve']['provider']['primary']['base_url']; \
        print('ok')"
    assert_success
    assert_output --partial "ok"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_config.bats -f "skillclaw.yml exists"`
Expected: FAIL — file not found.

- [ ] **Step 3: Create the config file**

Create `configs/claude/config/skillclaw.yml`:

```yaml
# SkillClaw runtime configuration
# Consumed by bootstrap/lib/skillclaw.sh and scripts/skillclaw_*.{sh,py}.
# This file is deployed to ~/.claude/config/skillclaw.yml.

proxy:
  port: 8765
  host: 127.0.0.1

storage:
  root: ~/.skillclaw          # chmod 700 by bootstrap; holds session capture + evolved lib
  sessions: ~/.skillclaw/sessions
  evolved: ~/.skillclaw/skills

# Which CLI agents get fail-open wrapper functions. Only agents whose SDK honors a
# base-URL override that SkillClaw can serve. claude + codex are verified-supported;
# gemini/cursor-agent are commented out pending base-URL-support verification (Task 12).
capture:
  agents:
    - name: claude
      env: ANTHROPIC_BASE_URL
      path: ""
    - name: codex
      env: OPENAI_BASE_URL
      path: /v1
    # - name: gemini        # enable only after verifying base-URL support
    #   env: OPENAI_BASE_URL
    #   path: /v1

evolve:
  mode: workflow              # fixed pipeline (deterministic); not "agent" mode
  provider:
    # Local-first: zero API cost, no rate limits. Falls back to cloud if unreachable.
    primary:
      kind: local
      base_url: http://127.0.0.1:11434/v1   # Ollama OpenAI-compatible endpoint
      model: qwen2.5-coder
    fallback:
      kind: cloud
      provider: anthropic
      model: claude-haiku-4-5-20251001

promotion:
  branch_prefix: skillclaw/evolve-
  pr_base: main
  pr_labels:
    - needs-review
    - follow-up
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_config.bats -f "skillclaw.yml exists"`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
yamllint configs/claude/config/skillclaw.yml
git add configs/claude/config/skillclaw.yml tests/bats/skillclaw_config.bats
git commit -m "feat(config): add skillclaw.yml runtime config (local-first evolve)"
```

---

## Task 3: skillclaw.sh — install, non-interactive setup, chmod 700

**Files:**
- Create: `bootstrap/lib/skillclaw.sh`
- Test: `tests/bats/skillclaw_lib.bats`

- [ ] **Step 1: Write the failing test**

Create `tests/bats/skillclaw_lib.bats`:

```bash
#!/usr/bin/env bats
# Tests for bootstrap/lib/skillclaw.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/skillclaw_lib.XXXXXX")
    export SKILLCLAW_HOME="$SANDBOX/.skillclaw"
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { echo "ERR: $*"; }
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/skillclaw.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "skillclaw_init_storage creates dirs with 700 perms" {
    run skillclaw_init_storage
    assert_success
    [ -d "$SKILLCLAW_HOME" ]
    [ -d "$SKILLCLAW_HOME/sessions" ]
    [ -d "$SKILLCLAW_HOME/skills" ]
    local mode
    mode=$(stat -f '%Lp' "$SKILLCLAW_HOME" 2>/dev/null || stat -c '%a' "$SKILLCLAW_HOME")
    assert_equal "$mode" "700"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_lib.bats`
Expected: FAIL — file not found / function undefined.

- [ ] **Step 3: Create the lib with storage + install + setup**

Create `bootstrap/lib/skillclaw.sh`:

```bash
#!/usr/bin/env bash
# skillclaw.sh - Install, configure, and manage the SkillClaw capture proxy.
#
# Responsibilities:
#   - Install SkillClaw (pip) when enabled.
#   - chmod 700 the capture storage (secrets honeypot — Tier 1).
#   - Non-interactive `skillclaw setup` from configs/claude/config/skillclaw.yml.
#   - Write/remove fail-open runtime wrapper functions (see skillclaw_wrappers).
#   - Daemon lifecycle + crash supervisor (see skillclaw_daemon).
#
# Sourced by bootstrap.sh. bash 3.2-compatible.

# Storage root is overridable for tests.
SKILLCLAW_HOME="${SKILLCLAW_HOME:-$HOME/.skillclaw}"
SKILLCLAW_PORT="${SKILLCLAW_PORT:-8765}"

# Create capture storage with locked-down perms. Secrets may transit here.
skillclaw_init_storage() {
    print_step "Preparing SkillClaw storage at $SKILLCLAW_HOME..."
    mkdir -p "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
    chmod 700 "$SKILLCLAW_HOME" "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
    print_success "SkillClaw storage ready (700)"
}

# Install SkillClaw via pip if missing.
install_skillclaw() {
    if [[ "${ENABLE_SKILLCLAW:-false}" != true ]]; then
        return 0
    fi
    if command -v skillclaw >/dev/null 2>&1; then
        print_info "SkillClaw already installed"
        return 0
    fi
    print_step "Installing SkillClaw..."
    if command -v pipx >/dev/null 2>&1; then
        pipx install skillclaw || { print_error "pipx install skillclaw failed"; return 1; }
    elif command -v pip3 >/dev/null 2>&1; then
        pip3 install --user skillclaw || { print_error "pip3 install skillclaw failed"; return 1; }
    else
        print_error "Neither pipx nor pip3 found; cannot install SkillClaw"
        return 1
    fi
    print_success "SkillClaw installed"
}

# Non-interactive setup from skillclaw.yml. Idempotent.
configure_skillclaw() {
    if [[ "${ENABLE_SKILLCLAW:-false}" != true ]]; then
        return 0
    fi
    skillclaw_init_storage
    local cfg="${SKILLCLAW_CONFIG:-$HOME/.claude/config/skillclaw.yml}"
    if [[ ! -f "$cfg" ]]; then
        print_warning "skillclaw.yml not found at $cfg; skipping setup"
        return 0
    fi
    print_step "Configuring SkillClaw (non-interactive)..."
    # `skillclaw setup` reads provider/model/storage flags; values come from skillclaw.yml.
    local port storage
    port=$(python3 -c "import yaml; print(yaml.safe_load(open('$cfg'))['proxy']['port'])")
    storage=$(python3 -c "import yaml,os; print(os.path.expanduser(yaml.safe_load(open('$cfg'))['storage']['root']))")
    if command -v skillclaw >/dev/null 2>&1; then
        skillclaw setup --non-interactive --port "$port" --storage "$storage" \
            || print_warning "skillclaw setup returned non-zero (continuing)"
    fi
    print_success "SkillClaw configured (port $port, storage $storage)"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_lib.bats`
Expected: PASS (1 test).

- [ ] **Step 5: Lint + commit**

```bash
shellcheck bootstrap/lib/skillclaw.sh
git add bootstrap/lib/skillclaw.sh tests/bats/skillclaw_lib.bats
git commit -m "feat(bootstrap): skillclaw lib install/setup + chmod 700 storage"
```

---

## Task 4: skillclaw.sh — fail-open runtime wrapper functions

**Files:**
- Modify: `bootstrap/lib/skillclaw.sh`
- Test: `tests/bats/skillclaw_lib.bats` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/bats/skillclaw_lib.bats`:

```bash
@test "skillclaw_write_wrappers writes a guarded, marker-delimited block" {
    local profile="$SANDBOX/.zshrc"
    touch "$profile"
    run skillclaw_write_wrappers "$profile"
    assert_success
    grep -q ">>> MANIFEST SKILLCLAW WRAPPERS >>>" "$profile"
    grep -q "<<< MANIFEST SKILLCLAW WRAPPERS <<<" "$profile"
    grep -q "SKILLCLAW_BYPASS" "$profile"
    grep -q "max-time 0.3" "$profile"
    grep -q 'claude()' "$profile"
    grep -q 'codex()' "$profile"
    # No hard top-level export of the base URL (must be per-invocation):
    run grep -E '^export ANTHROPIC_BASE_URL=' "$profile"
    assert_failure
}

@test "skillclaw_write_wrappers is idempotent (single block on re-run)" {
    local profile="$SANDBOX/.zshrc"
    touch "$profile"
    skillclaw_write_wrappers "$profile"
    skillclaw_write_wrappers "$profile"
    run grep -c ">>> MANIFEST SKILLCLAW WRAPPERS >>>" "$profile"
    assert_output "1"
}

@test "skillclaw_remove_wrappers strips the block" {
    local profile="$SANDBOX/.zshrc"
    touch "$profile"
    skillclaw_write_wrappers "$profile"
    run skillclaw_remove_wrappers "$profile"
    assert_success
    run grep -c "MANIFEST SKILLCLAW WRAPPERS" "$profile"
    assert_output "0"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_lib.bats -f wrappers`
Expected: FAIL — functions undefined.

- [ ] **Step 3: Implement wrapper write/remove**

Append to `bootstrap/lib/skillclaw.sh`:

```bash
SKILLCLAW_WRAP_BEGIN="# >>> MANIFEST SKILLCLAW WRAPPERS >>>"
SKILLCLAW_WRAP_END="# <<< MANIFEST SKILLCLAW WRAPPERS <<<"

# Remove any existing managed wrapper block from a profile file (idempotent).
skillclaw_remove_wrappers() {
    local profile="$1"
    [[ -f "$profile" ]] || return 0
    # Delete the inclusive marker block.
    sed -e "/$SKILLCLAW_WRAP_BEGIN/,/$SKILLCLAW_WRAP_END/d" "$profile" > "${profile}.tmp" \
        && mv "${profile}.tmp" "$profile"
}

# Write the fail-open runtime wrapper block. The health probe runs at INVOCATION
# time (not shell init), capped at 0.3s, and degrades to direct-to-provider.
skillclaw_write_wrappers() {
    local profile="$1"
    mkdir -p "$(dirname "$profile")"
    touch "$profile"
    skillclaw_remove_wrappers "$profile"
    cat >> "$profile" << EOF
$SKILLCLAW_WRAP_BEGIN
# Managed by bootstrap/lib/skillclaw.sh — do not edit between these markers.
export SKILLCLAW_PORT="\${SKILLCLAW_PORT:-$SKILLCLAW_PORT}"
_skillclaw_up() {
    curl -sf --max-time 0.3 "http://127.0.0.1:\${SKILLCLAW_PORT}/health" >/dev/null 2>&1
}
_skillclaw_run() {
    # \$1=env var name, \$2=base url, rest=command
    local var="\$1" url="\$2"; shift 2
    if [ -z "\${SKILLCLAW_BYPASS:-}" ] && _skillclaw_up; then
        env "\$var=\$url" "\$@"
    else
        "\$@"
    fi
}
claude() { _skillclaw_run ANTHROPIC_BASE_URL "http://127.0.0.1:\${SKILLCLAW_PORT}" command claude "\$@"; }
codex()  { _skillclaw_run OPENAI_BASE_URL    "http://127.0.0.1:\${SKILLCLAW_PORT}/v1" command codex "\$@"; }
$SKILLCLAW_WRAP_END
EOF
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_lib.bats -f wrappers`
Expected: PASS (3 tests).

- [ ] **Step 5: Verify generated block is valid shell**

Run:
```bash
tmp=$(mktemp); ( source bootstrap/lib/skillclaw.sh; skillclaw_write_wrappers "$tmp" )
bash -n "$tmp" && zsh -n "$tmp" 2>/dev/null; echo "syntax ok"; rm -f "$tmp"
```
Expected: `syntax ok` (no parse errors from either shell).

- [ ] **Step 6: Lint + commit**

```bash
shellcheck bootstrap/lib/skillclaw.sh
git add bootstrap/lib/skillclaw.sh tests/bats/skillclaw_lib.bats
git commit -m "feat(bootstrap): fail-open runtime wrapper functions for skillclaw capture"
```

---

## Task 5: skillclaw.sh — daemon lifecycle + crash supervisor

**Files:**
- Modify: `bootstrap/lib/skillclaw.sh`
- Test: `tests/bats/skillclaw_lib.bats` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/bats/skillclaw_lib.bats`:

```bash
@test "skillclaw_daemon status reports stopped when no pid" {
    export SKILLCLAW_PIDFILE="$SANDBOX/skillclaw.pid"
    run skillclaw_daemon status
    assert_failure
    assert_output --partial "stopped"
}

@test "skillclaw_supervisor_unit emits launchd plist on darwin" {
    run skillclaw_supervisor_unit darwin "$SANDBOX/out"
    assert_success
    [ -f "$SANDBOX/out" ]
    grep -q "KeepAlive" "$SANDBOX/out"
    grep -q "com.manifest.skillclaw" "$SANDBOX/out"
}

@test "skillclaw_supervisor_unit emits systemd unit on linux" {
    run skillclaw_supervisor_unit linux "$SANDBOX/out"
    assert_success
    grep -q "Restart=on-failure" "$SANDBOX/out"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_lib.bats -f "daemon\|supervisor"`
Expected: FAIL — functions undefined.

- [ ] **Step 3: Implement daemon lifecycle + supervisor unit emitter**

Append to `bootstrap/lib/skillclaw.sh`:

```bash
SKILLCLAW_PIDFILE="${SKILLCLAW_PIDFILE:-$SKILLCLAW_HOME/skillclaw.pid}"

# start|stop|status for the capture daemon. Capture is lossy-by-design; a dead
# daemon must never block agents (the wrappers already fail open).
skillclaw_daemon() {
    local action="${1:-status}"
    case "$action" in
        start)
            command -v skillclaw >/dev/null 2>&1 || { print_error "skillclaw not installed"; return 1; }
            skillclaw start --daemon --port "$SKILLCLAW_PORT" || return 1
            print_success "SkillClaw daemon started on $SKILLCLAW_PORT"
            ;;
        stop)
            skillclaw stop >/dev/null 2>&1 || true
            print_info "SkillClaw daemon stopped"
            ;;
        status)
            if [[ -f "$SKILLCLAW_PIDFILE" ]] && kill -0 "$(cat "$SKILLCLAW_PIDFILE")" 2>/dev/null; then
                echo "running"
                return 0
            fi
            echo "stopped"
            return 1
            ;;
        *)
            print_error "usage: skillclaw_daemon start|stop|status"
            return 2
            ;;
    esac
}

# Emit a platform supervisor unit so a crashed daemon auto-restarts (§5.3).
# $1 = platform (darwin|linux), $2 = output path.
skillclaw_supervisor_unit() {
    local platform="$1" out="$2"
    local bin; bin="$(command -v skillclaw 2>/dev/null || echo skillclaw)"
    mkdir -p "$(dirname "$out")"
    case "$platform" in
        darwin)
            cat > "$out" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.manifest.skillclaw</string>
  <key>ProgramArguments</key>
  <array>
    <string>$bin</string><string>start</string><string>--port</string><string>$SKILLCLAW_PORT</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
            ;;
        linux)
            cat > "$out" << EOF
[Unit]
Description=SkillClaw capture proxy
[Service]
ExecStart=$bin start --port $SKILLCLAW_PORT
Restart=on-failure
[Install]
WantedBy=default.target
EOF
            ;;
        *)
            print_error "unknown platform: $platform"
            return 1
            ;;
    esac
}

# Install + load the supervisor for the current platform (best-effort).
skillclaw_install_supervisor() {
    case "$(uname -s)" in
        Darwin)
            local plist="$HOME/Library/LaunchAgents/com.manifest.skillclaw.plist"
            skillclaw_supervisor_unit darwin "$plist"
            launchctl unload "$plist" >/dev/null 2>&1 || true
            launchctl load "$plist" >/dev/null 2>&1 || print_warning "launchctl load failed (continuing)"
            ;;
        Linux)
            local unit="$HOME/.config/systemd/user/skillclaw.service"
            skillclaw_supervisor_unit linux "$unit"
            systemctl --user daemon-reload >/dev/null 2>&1 || true
            systemctl --user enable --now skillclaw.service >/dev/null 2>&1 \
                || print_warning "systemctl enable failed (continuing)"
            ;;
    esac
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_lib.bats -f "daemon\|supervisor"`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

```bash
shellcheck bootstrap/lib/skillclaw.sh
git add bootstrap/lib/skillclaw.sh tests/bats/skillclaw_lib.bats
git commit -m "feat(bootstrap): skillclaw daemon lifecycle + crash supervisor units"
```

---

## Task 6: Wire skillclaw into bootstrap.sh

**Files:**
- Modify: `bootstrap.sh` (lib list ~L77-88, main install/deploy flow, reconfigure summary, service summary print, disable path)
- Modify: `bootstrap/lib/skillclaw.sh` (add a single `enable`/`disable` entry point)
- Test: `tests/bats/skillclaw_lib.bats` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/bats/skillclaw_lib.bats`:

```bash
@test "skillclaw_apply_state disable removes wrappers and stops daemon" {
    local profile="$SANDBOX/.zshrc"; touch "$profile"
    export SHELL_PROFILE_FILE="$profile"
    skillclaw_write_wrappers "$profile"
    # stub daemon to avoid invoking real skillclaw
    skillclaw_daemon() { echo "daemon $1"; }
    ENABLE_SKILLCLAW=false run skillclaw_apply_state
    assert_success
    run grep -c "MANIFEST SKILLCLAW WRAPPERS" "$profile"
    assert_output "0"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_lib.bats -f apply_state`
Expected: FAIL — `skillclaw_apply_state` undefined.

- [ ] **Step 3: Add the enable/disable entry point**

Append to `bootstrap/lib/skillclaw.sh`:

```bash
# Apply the desired state based on ENABLE_SKILLCLAW. Called from bootstrap main.
# Writes wrappers to SHELL_PROFILE_FILE (set by configure_shell_profile_state).
skillclaw_apply_state() {
    local profile="${SHELL_PROFILE_FILE:-$HOME/.zshrc}"
    if [[ "${ENABLE_SKILLCLAW:-false}" == true ]]; then
        configure_skillclaw
        skillclaw_write_wrappers "$profile"
        skillclaw_install_supervisor
        skillclaw_daemon start || print_warning "Could not start SkillClaw daemon (wrappers fail open)"
        print_success "SkillClaw enabled (capture via $profile)"
    else
        skillclaw_remove_wrappers "$profile"
        skillclaw_daemon stop || true
        print_info "SkillClaw disabled (wrappers removed)"
    fi
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_lib.bats -f apply_state`
Expected: PASS.

- [ ] **Step 5: Source the lib in bootstrap.sh**

In `bootstrap.sh`, in `load_bootstrap_libs`, add `"skillclaw.sh"` to the `libs` array after `"mcp.sh"`:

```bash
        "mcp.sh"
        "skillclaw.sh"
```

- [ ] **Step 6: Install + apply in main flow**

In `bootstrap.sh` `main()`, after `install_codex` add (install step):

```bash
        install_skillclaw
```

and after `deploy_configs` / `run_bootstrap_hook "after_deploy"` (so `~/.claude/config/skillclaw.yml` exists), add:

```bash
    skillclaw_apply_state
```

In `run_reconfigure()`, after `write_services_config` add the same line:

```bash
        skillclaw_apply_state
```

- [ ] **Step 7: Add to the service summaries + help**

In `main()`'s "Services to configure" block and `run_reconfigure()`'s changes block, add a SkillClaw line mirroring Antigravity, e.g. in `main()`:

```bash
    echo "  SkillClaw:   $(if [[ "$ENABLE_SKILLCLAW" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
```

In `bootstrap/lib/config.sh` `print_bootstrap_help`, after the antigravity help lines add:

```bash
    echo "  --enable-skillclaw     Enable SkillClaw session capture (default: disabled)"
    echo "  --disable-skillclaw    Disable SkillClaw session capture"
```

- [ ] **Step 8: Run full bats suite + lint**

Run:
```bash
bats tests/bats/skillclaw_config.bats tests/bats/skillclaw_lib.bats
shellcheck bootstrap.sh bootstrap/lib/skillclaw.sh bootstrap/lib/config.sh
```
Expected: all PASS, shellcheck clean.

- [ ] **Step 9: Commit**

```bash
git add bootstrap.sh bootstrap/lib/skillclaw.sh bootstrap/lib/config.sh tests/bats/skillclaw_lib.bats
git commit -m "feat(bootstrap): wire skillclaw install/apply into main + reconfigure"
```

---

## Task 7: Secret scrubber — `skillclaw_scrub.py`

**Files:**
- Create: `configs/claude/scripts/skillclaw_scrub.py`
- Test: `tests/python/test_skillclaw_scrub.py`

- [ ] **Step 1: Write the failing test**

Create `tests/python/test_skillclaw_scrub.py`:

```python
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_scrub as scrub  # noqa: E402


def test_redacts_anthropic_and_openai_keys():
    text = "key sk-ant-api03-ABCDEF123456 and sk-proj-XYZ987654321 done"
    out = scrub.redact_text(text)
    assert "sk-ant-api03-ABCDEF123456" not in out
    assert "sk-proj-XYZ987654321" not in out
    assert out.count(scrub.REDACTED) == 2


def test_redacts_auth_headers():
    text = "Authorization: Bearer abcdef.GHIJ-klmno\nx-api-key: secret-token-value"
    out = scrub.redact_text(text)
    assert "abcdef.GHIJ-klmno" not in out
    assert "secret-token-value" not in out


def test_scrub_file_rewrites_in_place(tmp_path):
    p = tmp_path / "session.json"
    p.write_text(json.dumps({"msg": "my key is sk-ant-api03-DEADBEEF00000000"}))
    changed = scrub.scrub_file(p)
    assert changed is True
    assert "sk-ant-api03-DEADBEEF00000000" not in p.read_text()


def test_clean_file_unchanged(tmp_path):
    p = tmp_path / "session.json"
    p.write_text('{"msg": "nothing secret here"}')
    assert scrub.scrub_file(p) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_scrub.py -v`
Expected: FAIL — `ModuleNotFoundError: skillclaw_scrub`.

- [ ] **Step 3: Implement the scrubber**

Create `configs/claude/scripts/skillclaw_scrub.py`:

```python
#!/usr/bin/env python3
"""Redact secrets from captured SkillClaw session files before evolution.

Defense-in-depth for the capture honeypot (spec §6): even with chmod 700, we
strip API keys and auth headers from session payloads at rest. Run as a sweep
before evolve/promote. Idempotent.

Usage:
    skillclaw_scrub.py <sessions_dir>     # scrub all *.json/*.jsonl in place
    skillclaw_scrub.py --check <dir>      # exit 1 if any secret remains
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REDACTED = "[REDACTED]"

# Ordered, conservative patterns. Each captures the *secret span* only.
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([A-Za-z0-9._-]+)"),
    re.compile(r"(?i)(x-api-key:\s*)([A-Za-z0-9._-]+)"),
    re.compile(r"(?i)(anthropic-api-key:\s*)([A-Za-z0-9._-]+)"),
]


def redact_text(text: str) -> str:
    """Return text with all known secret patterns replaced by REDACTED."""
    out = text
    for pat in _PATTERNS:
        if pat.groups == 2:
            out = pat.sub(lambda m: m.group(1) + REDACTED, out)
        else:
            out = pat.sub(REDACTED, out)
    return out


def scrub_file(path: Path) -> bool:
    """Rewrite path in place if it contains secrets. Return True if changed."""
    original = path.read_text(encoding="utf-8", errors="replace")
    cleaned = redact_text(original)
    if cleaned != original:
        path.write_text(cleaned, encoding="utf-8")
        return True
    return False


def _iter_session_files(root: Path):
    for ext in ("*.json", "*.jsonl", "*.txt"):
        yield from root.rglob(ext)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--check", action="store_true", help="exit 1 if secrets remain")
    args = ap.parse_args(argv)

    root = Path(args.directory).expanduser()
    if not root.is_dir():
        print(f"skillclaw_scrub: not a directory: {root}", file=sys.stderr)
        return 2

    leaked = False
    changed = 0
    for f in _iter_session_files(root):
        if args.check:
            if redact_text(
                f.read_text(encoding="utf-8", errors="replace")
            ) != f.read_text(encoding="utf-8", errors="replace"):
                print(f"secret found in {f}", file=sys.stderr)
                leaked = True
        else:
            if scrub_file(f):
                changed += 1
    if args.check:
        return 1 if leaked else 0
    print(f"scrubbed {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_scrub.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
chmod +x configs/claude/scripts/skillclaw_scrub.py
git add configs/claude/scripts/skillclaw_scrub.py tests/python/test_skillclaw_scrub.py
git commit -m "feat(scripts): skillclaw secret scrubber for captured sessions"
```

---

## Task 8: Classifier/validator — `skillclaw_promote.py`

**Files:**
- Create: `configs/claude/scripts/skillclaw_promote.py`
- Test: `tests/python/test_skillclaw_promote.py`

> **Spec reconciliation (§4/§9 "verify gate"):** the spec calls for running the
> `verify` skill on each candidate. `verify` runs *language toolchains* (linters,
> unit tests) on a project — it has nothing to act on for a markdown `SKILL.md`.
> The skill-appropriate realization of that gate is **structural validation**:
> required frontmatter (`name`, `description`) must be present and well-formed, or
> the candidate is dropped with a logged reason (never silently). That is what
> `validate_skill` implements below. This is a deliberate, documented substitution,
> not a dropped requirement.

- [ ] **Step 1: Write the failing test**

Create `tests/python/test_skillclaw_promote.py`:

```python
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_promote as promote  # noqa: E402

VALID = "---\nname: foo\ndescription: does foo\n---\n# Foo\nbody\n"


def _skill(dirpath: Path, name: str, body: str) -> Path:
    d = dirpath / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body)
    return d


def test_classify_new_changed_unchanged(tmp_path):
    evolved = tmp_path / "evolved"
    committed = tmp_path / "committed"
    _skill(evolved, "alpha", VALID.replace("foo", "alpha"))  # NEW
    _skill(evolved, "beta", VALID.replace("foo", "beta") + "more\n")  # CHANGED
    _skill(committed, "beta", VALID.replace("foo", "beta"))
    _skill(evolved, "gamma", VALID.replace("foo", "gamma"))  # UNCHANGED
    _skill(committed, "gamma", VALID.replace("foo", "gamma"))

    result = promote.classify(evolved, committed)
    status = {c["name"]: c["status"] for c in result}
    assert status["alpha"] == "NEW"
    assert status["beta"] == "CHANGED"
    assert status["gamma"] == "UNCHANGED"


def test_validate_rejects_missing_frontmatter(tmp_path):
    d = _skill(tmp_path, "bad", "# no frontmatter\n")
    ok, reason = promote.validate_skill(d / "SKILL.md")
    assert ok is False
    assert "frontmatter" in reason.lower()


def test_validate_accepts_complete_frontmatter(tmp_path):
    d = _skill(tmp_path, "good", VALID)
    ok, reason = promote.validate_skill(d / "SKILL.md")
    assert ok is True
    assert reason == ""


def test_main_emits_promotable_json(tmp_path, capsys):
    evolved = tmp_path / "evolved"
    committed = tmp_path / "committed"
    _skill(evolved, "alpha", VALID.replace("foo", "alpha"))
    _skill(committed, "_", VALID)  # ensure committed dir exists
    rc = promote.main([str(evolved), str(committed)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in payload["promote"]}
    assert "alpha" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_promote.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement classifier/validator**

Create `configs/claude/scripts/skillclaw_promote.py`:

```python
#!/usr/bin/env python3
"""Classify evolved SkillClaw skills vs the committed library and validate them.

Pure logic for the promote bridge. Emits JSON the shell orchestrator consumes:
which skills to promote (NEW or CHANGED) and which were dropped (failed
validation), with reasons. No git side effects here.

Usage:
    skillclaw_promote.py <evolved_dir> <committed_dir> [--skill NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FRONTMATTER_KEYS = ("name", "description")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> dict | None:
    """Return YAML-ish frontmatter as a dict, or None if absent/malformed."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end].strip().splitlines()
    fm: dict[str, str] = {}
    for line in block:
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def validate_skill(skill_md: Path) -> tuple[bool, str]:
    """Validate a SKILL.md has name+description frontmatter. (bool, reason)."""
    text = _read(skill_md)
    fm = parse_frontmatter(text)
    if fm is None:
        return False, "missing or malformed frontmatter"
    for key in FRONTMATTER_KEYS:
        if not fm.get(key):
            return False, f"frontmatter missing required key: {key}"
    return True, ""


def classify(evolved_dir: Path, committed_dir: Path) -> list[dict]:
    """Classify each evolved skill as NEW/CHANGED/UNCHANGED vs committed."""
    out: list[dict] = []
    for skill_md in sorted(evolved_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        committed = committed_dir / name / "SKILL.md"
        if not committed.exists():
            status = "NEW"
        elif _read(committed) == _read(skill_md):
            status = "UNCHANGED"
        else:
            status = "CHANGED"
        out.append({"name": name, "status": status, "path": str(skill_md)})
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("evolved_dir")
    ap.add_argument("committed_dir")
    ap.add_argument("--skill", help="restrict to a single skill name")
    args = ap.parse_args(argv)

    evolved = Path(args.evolved_dir).expanduser()
    committed = Path(args.committed_dir).expanduser()
    if not evolved.is_dir():
        print(f"skillclaw_promote: evolved dir not found: {evolved}", file=sys.stderr)
        return 2

    candidates = classify(evolved, committed)
    promote, dropped = [], []
    for c in candidates:
        if args.skill and c["name"] != args.skill:
            continue
        if c["status"] == "UNCHANGED":
            continue
        ok, reason = validate_skill(Path(c["path"]))
        if ok:
            promote.append(c)
        else:
            dropped.append({**c, "reason": reason})

    json.dump({"promote": promote, "dropped": dropped}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_promote.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
chmod +x configs/claude/scripts/skillclaw_promote.py
git add configs/claude/scripts/skillclaw_promote.py tests/python/test_skillclaw_promote.py
git commit -m "feat(scripts): skillclaw promote classifier + frontmatter validator"
```

---

## Task 9: Orchestrator — `skillclaw_promote.sh`

**Files:**
- Create: `configs/claude/scripts/skillclaw_promote.sh`
- Test: `tests/bats/skillclaw_promote.bats`

- [ ] **Step 1: Write the failing test**

Create `tests/bats/skillclaw_promote.bats`:

```bash
#!/usr/bin/env bats
# Tests for scripts/skillclaw_promote.sh (mocked git_ops + skillclaw)

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/skillclaw_promote.XXXXXX")
    export SKILLCLAW_EVOLVED="$SANDBOX/evolved"
    export SKILLCLAW_COMMITTED="$SANDBOX/committed"
    export SKILLCLAW_SESSIONS="$SANDBOX/sessions"
    mkdir -p "$SKILLCLAW_EVOLVED/alpha" "$SKILLCLAW_COMMITTED" "$SKILLCLAW_SESSIONS"
    printf -- '---\nname: alpha\ndescription: d\n---\nbody\n' > "$SKILLCLAW_EVOLVED/alpha/SKILL.md"

    # Mock git_ops.sh + skillclaw on PATH
    export MOCK_BIN="$SANDBOX/bin"; mkdir -p "$MOCK_BIN"
    cat > "$MOCK_BIN/git_ops.sh" << 'EOF'
#!/usr/bin/env bash
echo "git_ops.sh $*" >> "$SKILLCLAW_PROMOTE_LOG"
[ "$1" = "pr-create" ] && echo "https://example.test/pr/1"
exit 0
EOF
    cat > "$MOCK_BIN/skillclaw" << 'EOF'
#!/usr/bin/env bash
echo "skillclaw $*" >> "$SKILLCLAW_PROMOTE_LOG"
exit 0
EOF
    chmod +x "$MOCK_BIN/git_ops.sh" "$MOCK_BIN/skillclaw"
    export SKILLCLAW_GITOPS="$MOCK_BIN/git_ops.sh"
    export PATH="$MOCK_BIN:$PATH"
    export SKILLCLAW_PROMOTE_LOG="$SANDBOX/log"
    : > "$SKILLCLAW_PROMOTE_LOG"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "dry-run prints diff table and makes no PR" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    assert_output --partial "alpha"
    assert_output --partial "NEW"
    run grep -c "pr-create" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "0"
}

@test "--apply with no open PR creates exactly one PR" {
    export SKILLCLAW_OPEN_PR=""   # consumed by the open-PR check stub
    run bash "$SCRIPT" --apply --no-evolve
    assert_success
    run grep -c "pr-create" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "1"
}

@test "--apply aborts when an open evolve PR already exists (Option A)" {
    export SKILLCLAW_OPEN_PR="https://example.test/pr/9"
    run bash "$SCRIPT" --apply --no-evolve
    assert_failure
    assert_output --partial "open"
    run grep -c "pr-create" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "0"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_promote.bats`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Implement the orchestrator**

Create `configs/claude/scripts/skillclaw_promote.sh`:

```bash
#!/usr/bin/env bash
# skillclaw_promote.sh - Turn evolved SkillClaw skills into a review PR.
#
# Pipeline: idempotency check -> preflight -> scrub -> evolve -> classify ->
# verify -> stage branch (per-skill commits) -> git_ops pr-create.
# Dry-run by default; --apply required to branch/commit/PR. Never touches main
# directly, never force-pushes. Implements Option A: aborts if an open
# skillclaw/evolve-* PR already exists (override with --force-new).
#
# Usage: skillclaw_promote.sh [--apply] [--skill NAME] [--no-evolve] [--force-new]
#
# Env overrides (for tests): SKILLCLAW_EVOLVED, SKILLCLAW_COMMITTED,
#   SKILLCLAW_SESSIONS, SKILLCLAW_GITOPS, SKILLCLAW_OPEN_PR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITOPS="${SKILLCLAW_GITOPS:-${SCRIPT_DIR}/git_ops.sh}"
CFG="${SKILLCLAW_CONFIG:-${SCRIPT_DIR}/../config/skillclaw.yml}"

EVOLVED="${SKILLCLAW_EVOLVED:-$HOME/.skillclaw/skills}"
SESSIONS="${SKILLCLAW_SESSIONS:-$HOME/.skillclaw/sessions}"
# Committed library: the physical retired skill supply source of truth. The deployed script
# lives in ~/.claude/scripts, so locate the repo via MANIFEST_ROOT (exported by
# bootstrap into the shell profile); fall back to repo-relative when run in-tree.
COMMITTED="${SKILLCLAW_COMMITTED:-${MANIFEST_ROOT:-${SCRIPT_DIR}/../../..}/.retired skill supply/skills}"
BRANCH_PREFIX="skillclaw/evolve-"
PR_BASE="main"

APPLY=false; SKILL=""; DO_EVOLVE=true; FORCE_NEW=false

err() { echo "skillclaw-promote: $*" >&2; }
usage_error() { err "$*"; exit 2; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=true; shift ;;
        --skill) [[ $# -ge 2 ]] || usage_error "--skill needs a name"; SKILL="$2"; shift 2 ;;
        --no-evolve) DO_EVOLVE=false; shift ;;
        --force-new) FORCE_NEW=true; shift ;;
        -*) usage_error "unknown flag: $1" ;;
        *) usage_error "unexpected argument: $1" ;;
    esac
done

# 0. Idempotency (Option A): one open evolve PR at a time.
open_pr() {
    if [[ -n "${SKILLCLAW_OPEN_PR:-}" ]]; then
        echo "$SKILLCLAW_OPEN_PR"; return 0
    fi
    "$GITOPS" pr-list --search "head:${BRANCH_PREFIX}" --state open 2>/dev/null \
        | grep -Eo 'https?://[^ ]+' | head -1 || true
}
if [[ "$APPLY" == true && "$FORCE_NEW" == false ]]; then
    existing="$(open_pr)"
    if [[ -n "$existing" ]]; then
        err "an open evolve PR already exists: $existing"
        err "review/merge it first, or pass --force-new"
        exit 1
    fi
fi

# 1. Scrub captured sessions (best-effort; never blocks).
if [[ -d "$SESSIONS" ]]; then
    python3 "${SCRIPT_DIR}/skillclaw_scrub.py" "$SESSIONS" >/dev/null 2>&1 || true
fi

# 2. Evolve (skip with --no-evolve; e.g. tests / re-run on existing library).
if [[ "$DO_EVOLVE" == true ]]; then
    if command -v skillclaw >/dev/null 2>&1; then
        skillclaw evolve --mode workflow >/dev/null 2>&1 || err "evolve returned non-zero (continuing)"
    fi
fi

# 3. Classify + validate.
classify_json="$(python3 "${SCRIPT_DIR}/skillclaw_promote.py" "$EVOLVED" "$COMMITTED" \
    ${SKILL:+--skill "$SKILL"})"

# Print the human diff table.
echo "Evolved skill candidates:"
echo "$classify_json" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d["promote"]:
    print(f"  {c[\"status\"]:9} {c[\"name\"]}")
for c in d["dropped"]:
    print(f"  DROPPED   {c[\"name\"]}  ({c[\"reason\"]})")
if not d["promote"]:
    print("  (nothing to promote)")
'

promote_names="$(echo "$classify_json" | python3 -c 'import json,sys; print(" ".join(c["name"] for c in json.load(sys.stdin)["promote"]))')"

if [[ -z "$promote_names" ]]; then
    echo "Nothing to promote."
    exit 0
fi

if [[ "$APPLY" != true ]]; then
    echo ""
    echo "Dry run — re-run with --apply to open a review PR."
    exit 0
fi

# 4. Stage a branch with one commit per skill, then open a PR.
count="$(echo "$promote_names" | wc -w | tr -d ' ')"
branch="${BRANCH_PREFIX}${count}-$(git rev-parse --short HEAD)"
git switch -c "$branch"

for name in $promote_names; do
    dest="${COMMITTED}/${name}"
    mkdir -p "$dest"
    cp "${EVOLVED}/${name}/SKILL.md" "${dest}/SKILL.md"
    git add "${dest}/SKILL.md"
    git commit -m "skill(${name}): evolve via SkillClaw" >/dev/null
done

body="$(printf 'Auto-evolved by SkillClaw. Skills: %s\n\nProvenance: %s\nReview each commit independently; drop a skill by reverting its commit.' \
    "$promote_names" "$SESSIONS")"

pr_url="$("$GITOPS" pr-create --base "$PR_BASE" --head "$branch" \
    --title "SkillClaw: evolve ${count} skill(s)" --body "$body" \
    --label needs-review --label follow-up)"

echo "Opened review PR: $pr_url"
```

- [ ] **Step 4: Make the test's open-PR + git ops hermetic**

The two `--apply` tests must not run real `git`. Add a guard so `git` is mocked in tests: in `setup()` of `skillclaw_promote.bats`, append a `git` stub to `$MOCK_BIN`:

```bash
    cat > "$MOCK_BIN/git" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  rev-parse) echo "abc1234" ;;
  switch|add|commit) : ;;
  *) : ;;
esac
exit 0
EOF
    chmod +x "$MOCK_BIN/git"
```

(Re-run after adding the stub.)

- [ ] **Step 5: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_promote.bats`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint + commit**

```bash
shellcheck configs/claude/scripts/skillclaw_promote.sh
chmod +x configs/claude/scripts/skillclaw_promote.sh
git add configs/claude/scripts/skillclaw_promote.sh tests/bats/skillclaw_promote.bats
git commit -m "feat(scripts): skillclaw_promote orchestrator (dry-run default, Option A)"
```

---

## Task 10: `/skill-evolve` skill

**Files:**
- Create: `.retired skill supply/skills/skill-evolve/SKILL.md`
- Test: `tests/bats/skillclaw_promote.bats` (append a presence/lint check)

- [ ] **Step 1: Write the failing test**

Append to `tests/bats/skillclaw_promote.bats`:

```bash
@test "skill-evolve SKILL.md has valid frontmatter and points at the script" {
    local f="$REPO_ROOT/.retired skill supply/skills/skill-evolve/SKILL.md"
    [ -f "$f" ]
    head -1 "$f" | grep -q '^---$'
    grep -q "^name: skill-evolve$" "$f"
    grep -q "skillclaw_promote.sh" "$f"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_promote.bats -f "skill-evolve"`
Expected: FAIL — file not found.

- [ ] **Step 3: Create the skill**

Create `.retired skill supply/skills/skill-evolve/SKILL.md`:

```markdown
---
name: skill-evolve
description: |
  Turn SkillClaw's evolved skills into a reviewed PR into .retired skill supply/skills/.
  Dry-run by default (shows the diff table and makes no changes); --apply opens a
  single review PR with one commit per skill. Requires the SkillClaw daemon
  (enable via ./bootstrap.sh --enable-skillclaw). Never writes to the source of
  truth directly — every change goes through PR review.
---

# Evolve Skills (SkillClaw)

Promote skills SkillClaw has evolved from captured CLI-agent sessions into the
committed `.retired skill supply/skills/` library — gated behind PR review.

Backed by `~/.claude/scripts/skillclaw_promote.sh`, which classifies evolved
skills (NEW/CHANGED/UNCHANGED), drops any that fail `verify`/frontmatter checks,
scrubs captured sessions of secrets, and opens one review PR per batch.

## When to use

- After a stretch of work captured by the SkillClaw proxy, to harvest refined skills.
- To review what SkillClaw would propose before committing anything (dry-run).

## Task

1. **Preview (dry-run, default — makes no changes):**

   ```bash
   ~/.claude/scripts/skillclaw_promote.sh --no-evolve
   ```

   Prints the candidate table (NEW / CHANGED / DROPPED + reason). Use `--no-evolve`
   to classify the existing evolved library without re-running evolution.

2. **Evolve fresh, then preview:**

   ```bash
   ~/.claude/scripts/skillclaw_promote.sh
   ```

3. **Open the review PR (one PR, one commit per skill):**

   ```bash
   ~/.claude/scripts/skillclaw_promote.sh --apply
   ```

   Aborts if an open `skillclaw/evolve-*` PR already exists — review/merge that
   first, or pass `--force-new`. Scope to one skill with `--skill <name>`.

4. **Review the PR** like any other: each skill is its own commit; revert a commit
   to drop a single skill. Merge to deploy via the normal `bootstrap.sh` skill sync.

## Notes

- If the daemon is down, capture simply didn't happen — fix it with
  `/health-check` then `./bootstrap.sh --enable-skillclaw`. Nothing here mutates
  `.retired skill supply/skills/` without a merged PR.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_promote.bats -f "skill-evolve"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .retired skill supply/skills/skill-evolve/SKILL.md tests/bats/skillclaw_promote.bats
git commit -m "feat(skill): add /skill-evolve entry point for skillclaw promotion"
```

---

## Task 11: health-check + sync-configs coverage

**Files:**
- Modify: `.retired skill supply/skills/health-check/SKILL.md`
- Modify: `.retired skill supply/skills/sync-configs/SKILL.md`

- [ ] **Step 1: Read the current health-check skill**

Run: `sed -n '1,80p' .retired skill supply/skills/health-check/SKILL.md` to find the checks list/section.

- [ ] **Step 2: Add a SkillClaw section to health-check**

In `.retired skill supply/skills/health-check/SKILL.md`, under the existing checks, add:

```markdown
## SkillClaw (if enabled)

Only when `skillclaw.enabled: true` in `~/.claude/config/services.yml`:

```bash
# Daemon health (fail-open: a red here means capture is off, not that agents are broken)
curl -sf --max-time 0.3 http://127.0.0.1:8765/health && echo "daemon: up" || echo "daemon: down"

# Wrapper functions present in the shell profile
grep -q "MANIFEST SKILLCLAW WRAPPERS" "${ZDOTDIR:-$HOME}/.zshrc" && echo "wrappers: present" || echo "wrappers: MISSING"

# Storage locked down (must be 700)
stat -f '%Lp' ~/.skillclaw 2>/dev/null || stat -c '%a' ~/.skillclaw
```

Report `daemon: down` as INFO (capture paused, agents unaffected), but
`wrappers: MISSING` or storage perms != 700 as WARN.
```

- [ ] **Step 3: Add a SkillClaw drift check to sync-configs**

In `.retired skill supply/skills/sync-configs/SKILL.md`, where it lists config files to diff, add `skillclaw.yml`:

```markdown
- `config/skillclaw.yml` — SkillClaw runtime config (port, storage, evolve provider,
  promotion settings). Compare `configs/claude/config/skillclaw.yml` (source) against
  the deployed `~/.claude/config/skillclaw.yml`; flag drift in port or storage root.
```

- [ ] **Step 4: Validate frontmatter unchanged + commit**

Run:
```bash
head -1 .retired skill supply/skills/health-check/SKILL.md | grep -q '^---$' && echo OK
head -1 .retired skill supply/skills/sync-configs/SKILL.md | grep -q '^---$' && echo OK
```
Expected: `OK` twice.

```bash
git add .retired skill supply/skills/health-check/SKILL.md .retired skill supply/skills/sync-configs/SKILL.md
git commit -m "docs(skills): add skillclaw checks to health-check + sync-configs"
```

---

## Task 12: Documentation + follow-ups

**Files:**
- Modify: `CLAUDE.md`, `.claude/CLAUDE.md`
- Create: `docs/SKILLCLAW.md`

- [ ] **Step 1: Add the service toggle + command rows to `CLAUDE.md`**

In `CLAUDE.md` under "Service Toggles", after the antigravity line add:

```text
--enable-skillclaw / --disable-skillclaw   # SkillClaw session capture (default: disabled)
```

In the "Available Commands" table add:

```text
| `/skill-evolve` | Promote SkillClaw-evolved skills into a review PR (dry-run default) | NO |
```

- [ ] **Step 2: Note the proposer/source-of-truth boundary in `.claude/CLAUDE.md`**

In `.claude/CLAUDE.md` under "Skill Management (retired skill supply)", add a bullet:

```markdown
- **SkillClaw** (optional, opt-in via `./bootstrap.sh --enable-skillclaw`) is a *proposer*:
  it evolves skills from captured CLI-agent sessions and opens review PRs into
  `.retired skill supply/skills/` via `/skill-evolve`. It never writes the source of truth
  directly. Capture is fail-open (a dead daemon degrades to direct-to-provider) and
  storage is `chmod 700`. See `docs/SKILLCLAW.md`.
```

- [ ] **Step 3: Write the dedicated doc**

Create `docs/SKILLCLAW.md`:

```markdown
# SkillClaw Integration

SkillClaw captures CLI-agent sessions through a local proxy and evolves reusable
`SKILL.md` skills. In Manifest it is a **PR-gated proposer**: nothing reaches the
committed `.retired skill supply/skills/` library without a merged PR.

## Enable / disable

```bash
./bootstrap.sh --enable-skillclaw     # install, configure, write wrappers, start daemon
./bootstrap.sh --disable-skillclaw    # remove wrappers, stop daemon (full revert)
```

## How capture works (fail-open)

Shell **wrapper functions** (`claude`, `codex`) check the daemon's health at
invocation time (300ms cap). If it's up, the agent is routed through
`http://127.0.0.1:8765`; if it's down or `SKILLCLAW_BYPASS=1` is set, the agent talks
to its provider directly, unchanged. The daemon is never in the critical path.

Capture is **lossy by design**: a crash drops the in-flight session (a supervisor
restarts the daemon). Evolution is statistical over many sessions, so loss is noise.

## Promote evolved skills

```bash
~/.claude/scripts/skillclaw_promote.sh            # evolve + preview (dry-run)
~/.claude/scripts/skillclaw_promote.sh --no-evolve  # preview existing library only
~/.claude/scripts/skillclaw_promote.sh --apply    # open ONE review PR (commit per skill)
```

Only one open `skillclaw/evolve-*` PR at a time (Option A); `--force-new` overrides.

## Security

- Storage `~/.skillclaw/` is `chmod 700`.
- `skillclaw_scrub.py` redacts API keys / auth headers from captured sessions before
  evolution.

## Follow-ups (not in V1)

- **gemini / cursor-agent capture:** add wrappers only after verifying each CLI honors a
  base-URL override SkillClaw can serve (Anthropic + OpenAI CLIs are verified; Gemini was
  not in SkillClaw's documented compatible-agent list).
- **TLS:** http-localhost works for the verified CLIs; add local TLS termination only if a
  specific SDK rejects http.
- **Evolve model defaults:** confirm the Ollama model + cloud fallback tier in `skillclaw.yml`.
- **Shared team storage (S3/OSS)** and cross-device sync.
```

- [ ] **Step 4: Markdown lint (if configured) + commit**

Run: `git add CLAUDE.md .claude/CLAUDE.md docs/SKILLCLAW.md && git commit -m "docs: document SkillClaw integration, kill switch, and follow-ups"`

---

## Final Verification

- [ ] **Run the full new test surface:**

```bash
bats tests/bats/skillclaw_config.bats tests/bats/skillclaw_lib.bats tests/bats/skillclaw_promote.bats
pytest tests/python/test_skillclaw_scrub.py tests/python/test_skillclaw_promote.py -v
shellcheck bootstrap.sh bootstrap/lib/skillclaw.sh bootstrap/lib/config.sh configs/claude/scripts/skillclaw_promote.sh
yamllint configs/claude/config/skillclaw.yml configs/claude/config/services.yml
```
Expected: all green.

- [ ] **Confirm fail-open by inspection:** with the daemon stopped, `claude --version` (via the wrapper) still runs against the real provider — the wrapper's `_skillclaw_up` returns non-zero and falls through to `command claude`.

- [ ] **Confirm no source-of-truth mutation without PR:** `skillclaw_promote.sh` (no `--apply`) leaves `git status` clean.
