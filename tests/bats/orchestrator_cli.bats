#!/usr/bin/env bats
# T015 — daemon CLI / --help

load orchestrator_helper

@test "daemon --help exits 0 and shows usage" {
  run run_daemon --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"usage:"* ]]
  [[ "$output" == *"--phase"* ]]
  [[ "$output" == *"--dry-run"* ]]
}

@test "daemon errors without --repo or --payload" {
  run run_daemon
  [ "$status" -eq 2 ]
  [[ "$output" == *"--repo or --payload"* ]]
}

@test "daemon phase 1 dispatch on fixture yields ok envelope" {
  run run_daemon --phase 1 --payload "${BATS_TEST_DIRNAME}/../python/fixtures/orchestrator/backlog.json" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *'"status": "ok"'* ]]
  [[ "$output" == *'"#11"'* ]]
}
