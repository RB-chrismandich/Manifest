"""Security regression tests for --sync-fixtures.

tests/token_benchmark/fixtures/ is a *committed* tree, read by anyone who
clones the repo. sync_fixtures() previously copied ~/.claude/settings.json
into that tree wholesale; _scrub_fixture_pii() strips ANSI escapes and the
operator's home path/username but never redacted values under settings.json's
`env` mapping — a supported place for API keys (e.g. ANTHROPIC_API_KEY). This
module proves a realistic secret placed there can never reach the synced
fixture tree, regardless of which file(s) sync_fixtures() decides to copy.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.harness import sync_fixtures

FAKE_SECRET = "sk-ant-api03-FAKESECRETDONOTUSE1234567890ABCDEFGHIJKLMNOP"


def _all_synced_text(dst: Path) -> str:
    """Concatenate the content of every file written under dst, for a
    single "does this string appear anywhere in the output" assertion."""
    chunks = []
    for path in dst.rglob("*"):
        if path.is_file():
            chunks.append(path.read_text(errors="replace"))
    return "\n".join(chunks)


def _fake_home_with_secret(tmp_path: Path) -> Path:
    """A fake ~ whose settings.json carries a realistic secret under `env`,
    plus the two files the benchmark actually reads (CLAUDE.md, GEMINI.md)
    so a fix that narrows the copy set is still exercised end to end."""
    src = tmp_path / "home"
    (src / ".claude").mkdir(parents=True)
    (src / ".gemini").mkdir(parents=True)

    (src / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_API_KEY": FAKE_SECRET,
                    "SOME_OTHER_FLAG": "true",
                },
                "model": "claude-sonnet-5",
            },
            indent=2,
        )
    )
    (src / ".claude" / "CLAUDE.md").write_text("# Project guide\nNo secrets here.\n")
    (src / ".gemini" / "GEMINI.md").write_text("# Gemini guide\nNo secrets here.\n")
    return src


class TestSyncFixturesNeverLeaksSecrets:
    """#552 follow-up (security): a realistic secret under settings.json's
    `env` mapping must never appear in the synced, committed fixture tree."""

    def test_secret_under_env_does_not_reach_synced_fixtures(self, tmp_path):
        src = _fake_home_with_secret(tmp_path)
        dst = tmp_path / "fixtures"

        sync_fixtures(source_home=src, fixtures_dir=dst)

        synced_text = _all_synced_text(dst)
        assert FAKE_SECRET not in synced_text, (
            "secret value from settings.json's `env` mapping leaked into "
            "the synced (committed) fixture tree"
        )

    def test_settings_json_is_not_copied_into_fixtures(self, tmp_path):
        """The benchmark only ever reads CLAUDE.md/GEMINI.md
        (tests/token_benchmark/benchmarks.py:MANIFEST_SYSTEM_PROMPT_PATHS) —
        settings.json must not be present in the fixture tree at all, not
        merely redacted."""
        src = _fake_home_with_secret(tmp_path)
        dst = tmp_path / "fixtures"

        sync_fixtures(source_home=src, fixtures_dir=dst)

        assert not (dst / ".claude" / "settings.json").exists()

    def test_expected_fixtures_are_still_synced(self, tmp_path):
        """The fix must not regress the actual benchmark inputs."""
        src = _fake_home_with_secret(tmp_path)
        dst = tmp_path / "fixtures"

        sync_fixtures(source_home=src, fixtures_dir=dst)

        assert (
            dst / ".claude" / "CLAUDE.md"
        ).read_text() == "# Project guide\nNo secrets here.\n"
        assert (
            dst / ".gemini" / "GEMINI.md"
        ).read_text() == "# Gemini guide\nNo secrets here.\n"
