#!/usr/bin/env python3
"""Redact secrets from captured SkillClaw session files before evolution.

Defense-in-depth for the capture honeypot (spec §6): even with chmod 700, we
strip API keys and auth headers from session payloads at rest. Run as a sweep
before evolve/promote. Idempotent.

Usage:
    skillclaw_scrub.py <sessions_dir>     # scrub all *.json/*.jsonl in place
    skillclaw_scrub.py --check <dir>      # exit 1 if any secret remains
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REDACTED = "[REDACTED]"

# Ordered, conservative patterns. Each captures the *secret span* only.
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([A-Za-z0-9._-]+)"),
    re.compile(r"(?i)(x-api-key:\s*)([A-Za-z0-9._-]+)"),
    re.compile(r"(?i)(anthropic-api-key:\s*)([A-Za-z0-9._-]+)"),
]


_JSON_FIELD = re.compile(r'("(?:[^"\\]|\\.)*")\s*:\s*')
_BARE_FIELD = re.compile(r"(?<![\w\"'])(['\w.-]+)\s*[:=]")
_HEADER = re.compile(
    r"(?im)^(authorization|cookie|set-cookie|x-api-key|anthropic-api-key):[^\r\n]*"
    r"(?:\r?\n[ \t]+[^\r\n]*)*"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----.*?-----END \1-----", re.DOTALL
)


def sensitive(key: str) -> bool:
    """Identify credential-valued structured fields without inspecting their value."""
    return re.sub(r"[^a-z0-9]", "", key.lower()).endswith(
        (
            "password",
            "passwd",
            "secret",
            "token",
            "apikey",
            "privatekey",
            "credential",
            "credentials",
            "cookie",
            "authorization",
        )
    )


def redact_text(text: str) -> str:
    """Scrub known forms; reject ambiguous assignments before losing context."""
    out = _HEADER.sub(lambda match: match[1] + ": " + REDACTED, text)
    out = _PRIVATE_KEY.sub(REDACTED, out)
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", out):
        raise RuntimeError("SkillClaw incomplete private key; provider blocked")
    for match in _BARE_FIELD.finditer(out):
        if (
            sensitive(match[1])
            and not out[match.end() :].split("\n", 1)[0].strip() == REDACTED
        ):
            raise RuntimeError(
                "SkillClaw unstructured credential requires local review"
            )
    spans = []
    end = 0
    for match in _JSON_FIELD.finditer(out):
        if match.start() < end or not sensitive(json.loads(match[1])):
            continue
        try:
            _, size = json.JSONDecoder().raw_decode(out[match.end() :])
        except ValueError as exc:
            raise RuntimeError(
                "SkillClaw incomplete credential field; provider blocked"
            ) from exc
        end = match.end() + size
        suffix = out[end:].lstrip()
        if suffix and suffix[0] not in ",}]":
            raise RuntimeError(
                "SkillClaw ambiguous credential expression; provider blocked"
            )
        spans.append((match.end(), end))
    for start, end in reversed(spans):
        out = out[:start] + json.dumps(REDACTED) + out[end:]
    for pat in _PATTERNS:
        if pat.groups == 2:
            out = pat.sub(lambda m: m.group(1) + REDACTED, out)
        else:
            out = pat.sub(REDACTED, out)
    return out


def redact_value(value):
    """Sanitize decoded structures before serialization or truncation."""
    if isinstance(value, dict):
        return {
            key: REDACTED if sensitive(key) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def scrub_file(path: Path) -> bool:
    """Rewrite path in place if it contains secrets. Return True if changed."""
    original = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        value = json.loads(original)
        redacted = redact_value(value)
        cleaned = original if redacted == value else json.dumps(redacted, indent=2)
    elif path.suffix == ".jsonl":
        values = [json.loads(line) for line in original.splitlines() if line.strip()]
        redacted = redact_value(values)
        cleaned = (
            original
            if redacted == values
            else "\n".join(json.dumps(value) for value in redacted) + "\n"
        )
    else:
        cleaned = redact_text(original)
    if cleaned != original:
        path.write_text(cleaned, encoding="utf-8")
        return True
    return False


def _iter_session_files(root: Path):
    for ext in ("*.json", "*.jsonl", "*.txt"):
        yield from root.rglob(ext)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--check", action="store_true", help="exit 1 if secrets remain")
    args = ap.parse_args(argv)

    root = Path(args.directory).expanduser()
    if not root.is_dir():
        print("skillclaw_scrub: directory unavailable", file=sys.stderr)
        return 2

    from .provider_safety import assert_clean

    changed = 0
    try:
        for f in _iter_session_files(root):
            if args.check:
                content = f.read_text(encoding="utf-8")
                if redact_text(content) != content:
                    raise RuntimeError("redaction needed")
            else:
                changed += scrub_file(f)
                content = f.read_text(encoding="utf-8")
            assert_clean(content)
    except (OSError, ValueError, RuntimeError):
        print("skillclaw_scrub: sanitation or residual check failed", file=sys.stderr)
        return 1
    if not args.check:
        print(f"scrubbed {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
