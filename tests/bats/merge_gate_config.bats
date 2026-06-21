#!/usr/bin/env bats
# Guards the Constitution Principle II risk noted in validation_criteria.yml: the merge gate
# must keep cross_verification blocking; the PR-open gate must leave it advisory.

ROOT="$BATS_TEST_DIRNAME/../.."
VC="$ROOT/configs/claude/config/validation_criteria.yml"

@test "auto-issue-dev-merge keeps cross_verification in Tier-1 (blocking — Principle II)" {
    run python3 -c "
import yaml
o=yaml.safe_load(open('$VC'))['command_overrides']['auto-issue-dev-merge']
assert 'cross_verification' in o['tier1_checks'], o['tier1_checks']
print('ok')"
    [ "$status" -eq 0 ]
}

@test "auto-issue-dev (PR-open) omits cross_verification (advisory consensus)" {
    run python3 -c "
import yaml
o=yaml.safe_load(open('$VC'))['command_overrides']['auto-issue-dev']
assert 'cross_verification' not in o.get('tier1_checks',[]), o.get('tier1_checks')
print('ok')"
    [ "$status" -eq 0 ]
}
