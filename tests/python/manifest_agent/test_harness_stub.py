"""Tests for the response-driven native harness fixture."""

import json
import os
import subprocess
from pathlib import Path


def test_harness_stub_is_response_driven_and_logs_json_argv(tmp_path: Path) -> None:
    stub = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
    log = tmp_path / "argv.jsonl"
    env = {
        "PATH": os.environ["PATH"],
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_RESPONSES": json.dumps(
            {"stdout": "listed\n", "stderr": "warning\n", "returncode": 3}
        ),
    }

    result = subprocess.run(
        (str(stub), "plugin", "list", "argument with spaces"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 3
    assert result.stdout == "listed\n"
    assert result.stderr == "warning\n"
    assert json.loads(log.read_text(encoding="utf-8")) == [
        "harness-stub",
        "plugin",
        "list",
        "argument with spaces",
    ]


def test_harness_stub_selects_an_argv_specific_response(tmp_path: Path) -> None:
    stub = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
    log = tmp_path / "argv.jsonl"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "isolated-home"),
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_RESPONSES": json.dumps(
            {
                "responses": [
                    {"argv": ["plugin", "list"], "stdout": "selected"},
                ],
                "default": {"stderr": "unexpected", "returncode": 9},
            }
        ),
    }

    result = subprocess.run(
        (str(stub), "plugin", "list"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert result.stdout == "selected"
    assert result.stderr == ""
