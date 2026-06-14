#!/usr/bin/env bash
# Shared helpers for orchestrator bats tests (T006).
ORCH_SCRIPTS_DIR="${BATS_TEST_DIRNAME}/../../configs/claude/scripts"
run_daemon() { PYTHONPATH="$ORCH_SCRIPTS_DIR" python3 -m orchestrator.daemon "$@"; }
