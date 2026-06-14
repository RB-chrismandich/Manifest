"""R1 — backend prompt construction + envelope extraction (pure, unit-testable)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import backend  # noqa: E402


def test_build_prompt_includes_phase_and_payload():
    p = backend.build_prompt({"phase": 3, "inputs": {"spec": "x"}})
    assert "[CURRENT PHASE 3]" in p
    assert '"spec": "x"' in p
    assert "EXACTLY ONE response envelope" in p


def test_extract_strict_json():
    assert backend.extract_envelope('{"phase":1,"status":"ok"}') == {"phase": 1, "status": "ok"}


def test_extract_envelope_from_noisy_output():
    noisy = 'Sure! Here is the envelope:\n{"phase": 1, "status": "ok", "payload": {"a": 1}}\nDone.'
    env = backend.extract_envelope(noisy)
    assert env == {"phase": 1, "status": "ok", "payload": {"a": 1}}


def test_extract_handles_nested_and_strings_with_braces():
    text = 'noise {"phase":1,"payload":{"msg":"a } b"},"status":"ok"} trailing'
    env = backend.extract_envelope(text)
    assert env["payload"]["msg"] == "a } b" and env["status"] == "ok"


def test_extract_handles_escaped_quotes_in_strings():  # C2 / C1 regression
    # noisy output forces the brace-balancing fallback; the string value contains
    # an escaped quote AND a brace — the escape must not prematurely end the string
    text = 'Here:\n{"status":"ok","payload":{"msg":"a \\" b } c"}} done'
    env = backend.extract_envelope(text)
    assert env is not None
    assert env["payload"]["msg"] == 'a " b } c'


def test_extract_returns_none_when_no_object():
    assert backend.extract_envelope("no json here") is None
    assert backend.extract_envelope("[1,2,3]") is None   # array is not an envelope
