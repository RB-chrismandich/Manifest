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


def test_harness_stub_advances_argv_specific_response_sequences(tmp_path: Path) -> None:
    stub = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
    log = tmp_path / "argv.jsonl"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "isolated-home"),
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_STATE": str(tmp_path / "state.json"),
        "HARNESS_STUB_RESPONSES": json.dumps(
            {
                "responses": [
                    {
                        "argv": ["plugin", "list"],
                        "sequence": [{"stdout": "before"}, {"stdout": "after"}],
                    }
                ]
            }
        ),
    }

    first = subprocess.run(
        (str(stub), "plugin", "list"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    second = subprocess.run(
        (str(stub), "plugin", "list"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    exhausted = subprocess.run(
        (str(stub), "plugin", "list"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert (first.returncode, first.stdout) == (0, "before")
    assert (second.returncode, second.stdout) == (0, "after")
    assert exhausted.returncode == 2
    assert "response sequence exhausted" in exhausted.stderr


def test_harness_stub_logs_an_unconfigured_argv_before_failing(tmp_path: Path) -> None:
    stub = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
    log = tmp_path / "argv.jsonl"
    env = {
        "PATH": os.environ["PATH"],
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_RESPONSES": json.dumps({"responses": []}),
    }

    result = subprocess.run(
        (str(stub), "plugin", "unlisted"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "no configured response" in result.stderr
    assert json.loads(log.read_text(encoding="utf-8")) == [
        "harness-stub",
        "plugin",
        "unlisted",
    ]
