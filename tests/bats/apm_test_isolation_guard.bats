#!/usr/bin/env bats
# Guard: a suite that drives a GATED writer must isolate the domain registry.
#
# Activating SC-006 turned six tests red at once. None was a regression — five
# suites read the repo's LIVE apm_domains.yml, so they asserted on a legacy
# writer that correctly stands down for an APM-owned domain. They passed in CI
# (registry empty) and failed on any machine with a domain activated.
#
# That is ambient state deciding a test's outcome, and fixing the six found says
# nothing about the seventh. This enumerates rather than lists: any suite that
# invokes deploy_home_skills or sync-skills.sh must also set
# MANIFEST_APM_DOMAINS, or it is reading the developer's machine.
#
# Opt out in the file with:  # apm-isolation: exempt — <why>

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

BATS_DIR="$BATS_TEST_DIRNAME"

@test "every suite driving a gated writer isolates MANIFEST_APM_DOMAINS" {
    local offenders=()
    local f
    for f in "$BATS_DIR"/*.bats; do
        grep -q '# apm-isolation: exempt' "$f" && continue
        grep -qE 'deploy_home_skills|sync-skills\.sh' "$f" || continue
        grep -q 'MANIFEST_APM_DOMAINS' "$f" || offenders+=("$(basename "$f")")
    done

    if [[ ${#offenders[@]} -gt 0 ]]; then
        printf 'suite drives a gated writer without isolating the registry: %s\n' \
            "${offenders[@]}"
        printf 'Add to setup():\n  export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"\n'
        printf '  printf %s > "$MANIFEST_APM_DOMAINS"\n' "'domains: []\\n'"
        return 1
    fi
}

@test "the guard actually enumerates — it finds suites, not zero" {
    # A guard whose scan matches nothing passes forever. Assert it is really
    # looking at files that drive the gated writer.
    local seen=0 f
    for f in "$BATS_DIR"/*.bats; do
        grep -qE 'deploy_home_skills|sync-skills\.sh' "$f" && seen=$((seen + 1))
    done
    [ "$seen" -gt 3 ] || {
        echo "scan matched only $seen suites — the pattern has probably drifted"
        return 1
    }
}

@test "the guard detects a planted violation" {
    # Proves the check can fail. Without this, a typo'd grep would report clean
    # forever — the same vacuum the guard exists to close.
    local tmp="$BATS_TEST_TMPDIR/planted.bats"
    printf '#!/usr/bin/env bats\n@test "x" {\n  deploy_home_skills a b\n}\n' > "$tmp"

    run grep -q 'MANIFEST_APM_DOMAINS' "$tmp"
    assert_failure   # planted file is a violation by construction
    run grep -qE 'deploy_home_skills|sync-skills\.sh' "$tmp"
    assert_success   # and the scan pattern does match it
}
