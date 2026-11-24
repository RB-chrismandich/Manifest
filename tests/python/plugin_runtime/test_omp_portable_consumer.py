"""Portable OMP report and consumer integration contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.omp_portable_support import put, run


@pytest.mark.parametrize("failure", [None, "disabled", "stale", "unavailable"])
def test_direct_report_matches_wire_and_preserves_typed_inventory(portable, failure):
    scripts, root, env, cwd = portable
    if failure in {"disabled", "stale"}:
        put(
            root / "plugins/omp-plugins.lock.json",
            {
                "plugins": {
                    "@manifest/workspace": {
                        "version": "old" if failure == "stale" else "1.0.0",
                        "enabled": failure != "disabled",
                    },
                }
            },
        )
    elif failure == "unavailable":
        env["PATH"] = "/nonexistent"
    program = """
import json
import sys

sys.path.insert(0, sys.argv[1])
from _omp_readonly.inspection import inspect_native, inspection_report
from plugin_reconcile import _native_packages, reconcile

typed = inspect_native()
assert isinstance(typed.packages, tuple)
assert isinstance(typed.components, tuple)
assert isinstance(typed.inventory_errors, tuple)
document = inspection_report()
assert document == json.loads(json.dumps(document))
record = document["harnesses"]["omp"]
for field in ("packages", "components", "inventory_errors"):
    assert isinstance(record["native_inspection"][field], list)
packages, error = _native_packages(record)
if sys.argv[2] == "unavailable":
    assert packages is None
    assert error == "native inventory unreadable: OMP plugin list is unavailable"
else:
    assert packages["manifest-workspace"]["status"] == {
        "None": "verified", "disabled": "disabled", "stale": "inconsistent",
    }[sys.argv[2]]
report = reconcile(inspect_omp=True)
assert report["status"] == "degraded"
assert report["verified"] is False
if sys.argv[2] in {"disabled", "stale"}:
    assert any(row["reason"].startswith(sys.argv[2] + ":") for row in report["drift"])
if sys.argv[2] != "unavailable":
    assert any(row["reason"] == "native activation not verified"
               for row in report["unverified"])
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(scripts), str(failure)],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_portable_help_precedes_inventory_lookup(portable):
    scripts, _root, env, cwd = portable
    # A broken HOME and absent CLI must not affect argparse's help path.
    env.update(HOME="relative-home", PATH="/nonexistent")
    result = subprocess.run(
        [sys.executable, "-B", str(scripts / "omp_native_inspection.py"), "--help"],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage:")
    assert "--help" in result.stdout
    assert '"native_inspection"' not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "failure", ["missing", "malformed", "disabled", "stale", "cli", "scope"]
)
def test_bad_native_evidence_fails_closed_in_consumer(portable, failure):
    _scripts, root, env, _cwd = portable
    lock = root / "plugins/omp-plugins.lock.json"
    if failure == "missing":
        lock.unlink()
    elif failure == "malformed":
        lock.write_text("{malformed")
    elif failure in {"disabled", "stale"}:
        put(
            lock,
            {
                "plugins": {
                    "@manifest/workspace": {
                        "version": "old" if failure == "stale" else "1.0.0",
                        "enabled": failure != "disabled",
                    }
                }
            },
        )
    elif failure == "cli":
        Path(env["OMP_TEST_LIST"]).write_text("{malformed")
    else:
        put(
            Path(env["OMP_TEST_LIST"]),
            {
                "marketplace": [
                    {
                        "id": "manifest-workspace@manifest",
                        "scope": [],
                        "entries": [],
                    }
                ],
                "npm": [],
            },
        )
    native = run(portable, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["inventory_errors"]
    assert native["activation"] == "not-observed"
    if failure in {"disabled", "stale"}:
        assert native["packages"][0]["status"] == (
            "disabled" if failure == "disabled" else "inconsistent"
        )
    report = run(portable, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert report["verified"] is False
    if failure in {"disabled", "stale"}:
        assert any(row["reason"].startswith(failure + ":") for row in report["drift"])


def test_exported_report_feeds_existing_consumer_without_mutation(portable):
    _scripts, root, _env, cwd = portable
    before = {
        str(path): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    document = run(portable, "omp_native_inspection.py")
    exported = cwd / "inspection.json"
    put(exported, document)
    report = run(
        portable, "plugin_reconcile.py", "--json", "--native-inspection", str(exported)
    )
    assert report["status"] == "degraded"
    assert report["verified"] is False
    after = {
        str(path): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    assert after == before


def test_unavailable_omp_emits_typed_unverified_report(portable):
    _scripts, _root, env, _cwd = portable
    env["PATH"] = "/nonexistent"
    document = run(portable, "omp_native_inspection.py")
    native = document["harnesses"]["omp"]["native_inspection"]
    assert native["packages"] == []
    assert native["inventory_errors"] == ["OMP plugin list is unavailable"]
    assert native["activation"] == "not-observed"
