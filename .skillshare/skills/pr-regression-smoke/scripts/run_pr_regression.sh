#!/usr/bin/env bash
# run_pr_regression.sh — complete regression + smoke test for the Manifest repo.
#
# Mirrors the gates in .github/workflows/ci.yml (shellcheck, array-expansion,
# yamllint, markdownlint, bats, pytest) and adds a deployed-environment smoke
# pass (bootstrap re-deploy, env health, live orchestration probe).
#
# Why a script and not freehand commands: a PR gate needs a *reliable* verdict.
# A script aggregates every phase's real exit code into one number, so the
# pass/warn/fail decision is deterministic and reproducible rather than
# something a reader has to eyeball from scrolled-past output.
#
# Exit codes (chosen so this can gate a merge or feed a hook):
#   0 = PASS  every gate clean
#   1 = WARN  no regressions, but a non-blocking smoke check degraded
#   2 = FAIL  a regression gate failed (lint/test/deploy)
set -u

SCRIPT_NAME="run_pr_regression.sh"
err() { echo "${SCRIPT_NAME}: $*" >&2; }

usage() {
  cat <<'EOF'
Usage: run_pr_regression.sh [options]
Complete regression (lint/bats/pytest) + smoke (deploy/env/orchestration) for Manifest.
  --skip-regression     Skip the regression suite
  --skip-smoke          Skip the smoke pass
  --skip-deploy         Within smoke, skip the bootstrap re-deploy
  --skip-orchestration  Within smoke, skip the live parallel_agent probe (costs an API call)
  --quick               Regression lint+bats only; skip pytest and the whole smoke pass
  -h, --help            Show this help and exit
Exit: 0 = PASS, 1 = WARN (non-blocking), 2 = FAIL (regression).
EOF
}

# --- Parse args BEFORE any repo/tool lookup so --help works in any environment.
SKIP_REGRESSION=0 SKIP_SMOKE=0 SKIP_DEPLOY=0 SKIP_ORCH=0 QUICK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-regression) SKIP_REGRESSION=1 ;;
    --skip-smoke) SKIP_SMOKE=1 ;;
    --skip-deploy) SKIP_DEPLOY=1 ;;
    --skip-orchestration) SKIP_ORCH=1 ;;
    --quick) QUICK=1 ;;
    -h|--help) usage; exit 0 ;;
    *) err "unknown option: $1"; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  err "not inside a git repository"; exit 2
}
cd "$REPO_ROOT" || { err "cannot cd to repo root"; exit 2; }

# --- Result accumulation ----------------------------------------------------
declare -a R_PHASE R_NAME R_STATUS R_SUMMARY
FAILS=0 WARNS=0

record() { # record <phase> <name> <status> <summary>
  R_PHASE+=("$1"); R_NAME+=("$2"); R_STATUS+=("$3"); R_SUMMARY+=("$4")
  case "$3" in fail) FAILS=$((FAILS + 1));; warn) WARNS=$((WARNS + 1));; esac
}

# run_step <phase> <name> <mode:hard|soft> <command-string>
#   hard: a non-zero exit is a regression  -> fail
#   soft: a non-zero exit is a degradation -> warn (e.g. unauthenticated env)
run_step() {
  local phase="$1" name="$2" mode="$3" cmd="$4" log rc
  log="$(mktemp)"
  echo "▶ ${phase}: ${name}"
  if bash -c "$cmd" >"$log" 2>&1; then
    record "$phase" "$name" pass "ok"
  else
    rc=$?
    local tail_line
    tail_line="$(grep -vE '^\s*$' "$log" | tail -1)"
    if [ "$mode" = soft ]; then
      record "$phase" "$name" warn "rc=${rc}: ${tail_line:0:80}"
      err "WARN ${name} (rc=${rc}) — see below"
    else
      record "$phase" "$name" fail "rc=${rc}: ${tail_line:0:80}"
      err "FAIL ${name} (rc=${rc}) — see below"
    fi
    tail -25 "$log" | sed 's/^/    /'
  fi
  rm -f "$log"
}

# Mark a step skipped because a required tool is absent (skip != fail).
need() { # need <tool> <phase> <name>
  command -v "$1" >/dev/null 2>&1 && return 0
  record "$2" "$3" skip "tool '$1' not installed"
  echo "▶ ${2}: ${3} — skip ('$1' not installed)"
  return 1
}

# --- Regression suite (mirrors ci.yml) --------------------------------------
run_regression() {
  echo "═══ Regression ═══"
  if need shellcheck Regression shellcheck-scripts; then
    run_step Regression shellcheck-scripts hard 'shellcheck -S warning configs/claude/scripts/*.sh'
    run_step Regression shellcheck-bootstrap hard 'shellcheck -S warning bootstrap.sh bootstrap/lib/*.sh'
  fi
  run_step Regression array-expansion-lint hard 'tests/lint/check_array_expansion.sh'
  # Invoke yamllint as a module: the bare console-script shim can fail to exec
  # under `bash -c` on some Python installs (the shebang falls through to sh),
  # whereas `python3 -m yamllint` is portable.
  if python3 -c 'import yamllint' 2>/dev/null; then
    run_step Regression yamllint hard 'python3 -m yamllint configs/claude/config/*.yml'
  else
    record Regression yamllint skip "python 'yamllint' module not installed"
    echo "▶ Regression: yamllint — skip (module not installed)"
  fi
  # markdownlint-cli2 auto-discovers .markdownlint.jsonc; run via npx (no global install).
  run_step Regression markdownlint hard 'npx --no-install markdownlint-cli2 AGENTS.md CLAUDE.md README.md "docs/*.md" 2>/dev/null'

  # Generated-artifact drift. Adding/renaming a skill must be reflected in
  # docs/COMMANDS.md, the GEMINI.md/AGENTS.md command index, and the per-skill
  # Cursor rules — CI fails the build otherwise. These mirror those CI gates so
  # the drift is caught here, before the push, not after.
  run_step Regression commands-doc-drift hard 'configs/claude/scripts/generate_commands_doc.py --check'
  # No --check on the cursor generator: regenerate, then a dirty rules/ tree is drift.
  run_step Regression cursor-rule-drift hard \
    'bash configs/claude/scripts/generate_cursor_rules.sh >/dev/null 2>&1; [ -z "$(git status --porcelain configs/cursor/rules/)" ]'

  # bats: prefer the repo-pinned binary, fall back to a PATH install.
  local bats_bin="bats"
  [ -x ./node_modules/.bin/bats ] && bats_bin="./node_modules/.bin/bats"
  if need "${bats_bin%% *}" Regression bats || [ -x ./node_modules/.bin/bats ]; then
    run_step Regression bats hard "${bats_bin} tests/bats/"
  fi

  if [ "$QUICK" = 1 ]; then
    record Regression pytest skip "--quick mode"
    echo "▶ Regression: pytest — skip (--quick)"
    return
  fi
  if need python3 Regression pytest; then
    run_step Regression pytest hard 'python3 -m pytest tests/python/ -q'
  fi
}

# --- Smoke pass (deployed environment) --------------------------------------
run_smoke() {
  echo "═══ Smoke ═══"
  # Bootstrap re-deploy: a broken deploy path is a genuine regression a PR can
  # introduce, so this gate is hard. --skip-install/--skip-auth keep it fast and
  # non-interactive; --force avoids the overwrite prompt.
  if [ "$SKIP_DEPLOY" = 1 ]; then
    record Smoke bootstrap-deploy skip "--skip-deploy"
    echo "▶ Smoke: bootstrap-deploy — skip"
  else
    run_step Smoke bootstrap-deploy hard './bootstrap.sh --skip-install --skip-auth --force'
  fi

  # Env health is soft: disabled agents or missing auth are normal local states,
  # not regressions the PR caused.
  run_step Smoke env-health soft "$HOME/.claude/scripts/check_status.sh"

  if [ "$SKIP_ORCH" = 1 ]; then
    record Smoke orchestration skip "--skip-orchestration"
    echo "▶ Smoke: orchestration — skip"
  else
    # One real round-trip through the orchestrator proves agents respond
    # end-to-end. claude-only keeps it to a single cheap call; soft because an
    # unauthenticated machine should warn, not block a code PR.
    run_step Smoke orchestration soft \
      "$HOME/.claude/scripts/parallel_agent.py --json --claude-only --timeout 90 'Reply with the single word OK'"
  fi
}

# --- Drive ------------------------------------------------------------------
[ "$SKIP_REGRESSION" = 1 ] || run_regression
if [ "$QUICK" = 1 ]; then
  SKIP_SMOKE=1
fi
[ "$SKIP_SMOKE" = 1 ] || run_smoke

# --- Report -----------------------------------------------------------------
echo ""
echo "## PR Regression + Smoke Report"
echo ""
echo "| Phase | Check | Status | Summary |"
echo "|-------|-------|--------|---------|"
i=0
while [ "$i" -lt "${#R_NAME[@]}" ]; do
  printf '| %s | %s | %s | %s |\n' \
    "${R_PHASE[$i]}" "${R_NAME[$i]}" "${R_STATUS[$i]}" "${R_SUMMARY[$i]}"
  i=$((i + 1))
done
echo ""

if [ "$FAILS" -gt 0 ]; then
  echo "**Verdict: FAIL** — ${FAILS} gate(s) failed, ${WARNS} warning(s)."
  exit 2
elif [ "$WARNS" -gt 0 ]; then
  echo "**Verdict: WARN** — 0 failures, ${WARNS} non-blocking warning(s)."
  exit 1
fi
echo "**Verdict: PASS** — all gates clean."
exit 0
