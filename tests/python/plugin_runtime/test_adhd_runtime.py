import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


def _runtime(repo_root: Path):
    path = repo_root / "plugins/manifest-i-have-adhd/hooks/always_on.py"
    spec = importlib.util.spec_from_file_location("adhd_runtime", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_claude_hook_resolves_runtime_from_plugin_root() -> None:
    hooks = json.loads(
        Path("plugins/manifest-i-have-adhd/hooks/hooks.json").read_text(
            encoding="utf-8"
        )
    )
    command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert command == "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/always_on.py"


def test_stdout_is_canonical_and_never_reflects_payload(monkeypatch, capsys) -> None:
    runtime = _runtime(Path.cwd())
    secret = "SESSION-PAYLOAD-MUST-NOT-APPEAR"
    payload = json.dumps({"hook_event_name": "SessionStart", "cwd": secret}).encode()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload)))
    assert runtime.main() == 0
    assert secret not in capsys.readouterr().out


def test_diagnostic_contains_only_allowlisted_value_free_fields(tmp_path: Path) -> None:
    runtime = _runtime(Path.cwd())
    diagnostic = runtime.HookDiagnostic(
        "manifest-i-have-adhd", "0.1.0", "native", "invalid-json"
    )
    runtime.record_hook_failure(tmp_path, diagnostic)
    rows = json.loads((tmp_path / "diagnostics/manifest-i-have-adhd.json").read_text())
    assert set(rows[0]) == {"plugin", "version", "harness", "reason"}


def test_diagnostic_rejects_untrusted_identity() -> None:
    runtime = _runtime(Path.cwd())
    for values in (
        ("other", "0.1.0", "native", "invalid-json"),
        ("manifest-i-have-adhd", "9.9.9", "native", "invalid-json"),
        ("manifest-i-have-adhd", "0.1.0", "payload-value", "invalid-json"),
        ("manifest-i-have-adhd", "0.1.0", "native", "secret-error"),
    ):
        with pytest.raises(ValueError):
            runtime.HookDiagnostic(*values)


@pytest.mark.parametrize(
    "existing",
    (
        b"{not-json",
        json.dumps([{"reason": "legacy-free-form-secret"}]).encode(),
        json.dumps(
            [
                {
                    "plugin": "manifest-i-have-adhd",
                    "version": "0.1.0",
                    "harness": "native",
                    "reason": "invalid-json",
                    "token": "must-not-survive",
                }
            ]
        ).encode(),
        b"x" * 4097,
    ),
)
def test_corrupt_legacy_secret_and_oversized_diagnostics_are_dropped(
    tmp_path: Path, existing: bytes
) -> None:
    runtime = _runtime(Path.cwd())
    path = tmp_path / "diagnostics/manifest-i-have-adhd.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(existing)

    runtime.record_hook_failure(
        tmp_path,
        runtime.HookDiagnostic(
            "manifest-i-have-adhd", "0.1.0", "native", "invalid-event"
        ),
    )

    rows = json.loads(path.read_text(encoding="utf-8"))
    assert rows == [
        {
            "harness": "native",
            "plugin": "manifest-i-have-adhd",
            "reason": "invalid-event",
            "version": "0.1.0",
        }
    ]
    assert "secret" not in path.read_text(encoding="utf-8")
