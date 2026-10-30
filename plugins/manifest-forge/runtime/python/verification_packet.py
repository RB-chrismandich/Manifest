"""Prepare a reviewer packet under a fail-closed, finite secret-detection policy."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_JSON_FIELD = re.compile(r'("(?:[^"\\]|\\.)*")\s*:\s*')
_JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_BARE_FIELD = re.compile(r"(?<![\w\"'])(['\w.-]+)\s*[:=]")
_SECRET_SUFFIXES = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "privatekey",
    "credential",
    "credentials",
)


def sensitive(key: str) -> bool:
    """Recognize credential-bearing field names, including JSON escaped names."""
    return re.sub(r"[^a-z0-9]", "", key.lower()).endswith(_SECRET_SUFFIXES)


def scrub_fields(text: str) -> str:
    """Scrub complete JSON credential values; refuse ambiguous multiline fields."""
    # A regex redactor can erase a multiline value's label but leave its body.
    # Only complete JSON values are structurally safe to remove here.
    for match in _BARE_FIELD.finditer(text):
        if sensitive(match[1]):
            raise ValueError("unstructured credential requires local review")
    decoder = json.JSONDecoder()
    spans = []
    end = 0
    for match in _JSON_FIELD.finditer(text):
        if match.start() < end or not sensitive(json.loads(match[1])):
            continue
        _, size = decoder.raw_decode(text[match.end() :])
        end = match.end() + size
        spans.append((match.end(), end))
    for start, end in reversed(spans):
        text = text[:start] + '"<REDACTED>"' + text[end:]
    return text


def decoded_view(text: str) -> str:
    """Inspect JSON escapes and diff-prefixed lines without altering the packet."""

    def decode(match: re.Match) -> str:
        try:
            return json.loads(match[0])
        except ValueError:
            return match[0]

    return _JSON_STRING.sub(decode, re.sub(r"(?m)^[ +\-]", "", text))


def prepare(text: str, runtime: Path) -> str:
    """Return sanitized text only after an independent complete scan succeeds."""
    scrubbed = scrub_fields(text)
    redacted = subprocess.run(
        [str(runtime / "bin/audit_log.sh"), "redact"],
        input=scrubbed,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout
    if text and not redacted:
        raise ValueError("empty redaction result")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GITLEAKS_")
    }
    result = subprocess.run(
        [
            "gitleaks",
            "stdin",
            "--config",
            str(runtime / "config/verification-gitleaks.toml"),
            "--gitleaks-ignore-path",
            os.devnull,
            "--ignore-gitleaks-allow",
            "--max-decode-depth",
            "5",
            "--max-target-megabytes",
            "0",
            "--no-banner",
            "--redact",
            "--log-level",
            "error",
            "--report-format",
            "json",
            "--report-path",
            "-",
            "--exit-code",
            "1",
        ],
        # Scan the exact outgoing text as well as a decoded inspection view.
        input=redacted + "\n" + decoded_view(redacted),
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
        env=environment,
        cwd=runtime,
    )
    if json.loads(result.stdout) != []:
        raise ValueError("residual scan did not attest an empty finding list")
    return redacted


def main() -> int:
    try:
        text = sys.stdin.read()
        sys.stdout.write(prepare(text, Path(__file__).resolve().parents[1]))
    except (OSError, ValueError, subprocess.SubprocessError):
        # Never print input, subprocess output, or detector finding details.
        print("verification packet sanitation or residual scan failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
