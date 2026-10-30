"""Fail-closed checks for SkillClaw's finite provider-egress detection policy."""

import json
import os
import re
import subprocess
from pathlib import Path

from .scrub import redact_text

_JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def _decoded_view(text: str) -> str:
    def decode(match: re.Match) -> str:
        try:
            return json.loads(match[0])
        except ValueError:
            return match[0]

    return _JSON_STRING.sub(decode, text)


def assert_clean(text: str) -> None:
    """Require an affirmative empty detector report; never expose its output."""
    config = Path(__file__).with_name("provider-gitleaks.toml")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GITLEAKS_")
    }
    try:
        result = subprocess.run(
            [
                "gitleaks",
                "stdin",
                "--config",
                str(config),
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
            input=text + "\n" + _decoded_view(text),
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
            env=environment,
            cwd=config.parent,
        )
        if json.loads(result.stdout) != []:
            raise ValueError("nonempty or invalid report")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "SkillClaw residual-secret check failed; provider blocked"
        ) from exc


def prepare_prompt(prompt: str) -> str:
    """Sanitize the final composed prompt and enforce the outbound policy."""
    cleaned = redact_text(prompt)
    assert_clean(cleaned)
    return cleaned
