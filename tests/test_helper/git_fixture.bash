# git_fixture.bash — shared git-identity fixture for bats suites that
# create real git repos as test fixtures. (Its original consumers,
# apm_publish_gate.bats and apm_install_verify.bats, were retired by spec 674
# Phase 5; it is kept for any suite needing one.) Pins a deterministic commit
# identity and disables GPG signing via GIT_CONFIG_* environment overrides
# (git >= 2.31) so the suite neither depends on nor fights the operator's
# global git config or commit/tag signing setup.
#
# Convention: load with `load '../test_helper/git_fixture.bash'` and call
# git_fixture_env from setup() / git_fixture_unset from teardown() — same
# pattern as tests/test_helper/stub_home_runtime.bash.

git_fixture_env() {
    export GIT_CONFIG_COUNT=4
    export GIT_CONFIG_KEY_0=user.name
    export GIT_CONFIG_VALUE_0=cddl-test
    export GIT_CONFIG_KEY_1=user.email
    export GIT_CONFIG_VALUE_1=cddl-test@example.invalid
    export GIT_CONFIG_KEY_2=tag.gpgsign
    export GIT_CONFIG_VALUE_2=false
    export GIT_CONFIG_KEY_3=commit.gpgsign
    export GIT_CONFIG_VALUE_3=false
}

git_fixture_unset() {
    unset GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0 GIT_CONFIG_KEY_1 \
        GIT_CONFIG_VALUE_1 GIT_CONFIG_KEY_2 GIT_CONFIG_VALUE_2 GIT_CONFIG_KEY_3 GIT_CONFIG_VALUE_3
}
