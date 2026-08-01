"""T5.2b (spec 674) — pruning apm.yml's dangling local-path dependencies.

The two NEGATIVE cases carry the weight. A pruner that removes a live local path
stands down a domain nobody asked about, and one that touches a published
package breaks the install outright. Both are checked explicitly, because a
pruner that removes everything passes every "did it prune?" assertion.
"""

import importlib.util
import pathlib

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs/claude/scripts/apm_prune_dangling_deps.py"
)
_spec = importlib.util.spec_from_file_location("apm_prune", SCRIPT)
apm_prune = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apm_prune)


def _yml(*dep_lines: str) -> list[str]:
    body = [
        "name: someone\n",
        "# Which agent platforms to deploy to.\n",
        "targets:\n",
        "  - claude\n",
        "dependencies:\n",
        "  apm:\n",
    ]
    body += [f"    - {d}\n" for d in dep_lines]
    body += ["  mcp: []\n", "includes: auto\n"]
    return body


def test_dangling_local_path_is_pruned():
    out, removed = apm_prune.prune(_yml("/nope/does/not/exist"))
    assert removed == ["/nope/does/not/exist"]
    assert "/nope/does/not/exist" not in "".join(out)


def test_a_live_local_path_survives(tmp_path):
    live = tmp_path / "real"
    live.mkdir()
    _, removed = apm_prune.prune(_yml(str(live)))
    assert removed == []


def test_a_published_package_is_never_touched():
    out, removed = apm_prune.prune(_yml("some-package@1.2.3"))
    assert removed == []
    assert "some-package@1.2.3" in "".join(out)


def test_comments_and_unrelated_keys_survive():
    # A pyyaml round-trip would delete apm's own explanatory comments.
    out, _ = apm_prune.prune(_yml("/nope"))
    text = "".join(out)
    assert "# Which agent platforms to deploy to." in text
    assert "targets:\n" in text and "  - claude\n" in text
    assert "includes: auto" in text


def test_an_emptied_list_becomes_an_explicit_empty_list():
    out, removed = apm_prune.prune(_yml("/nope/one", "/nope/two"))
    assert len(removed) == 2
    assert "  apm: []\n" in out


def test_a_list_item_outside_dependencies_is_never_pruned():
    # `targets:` holds `- claude`, and a bare walk over every "- " line would
    # eat unrelated lists. The block boundary is what stops it.
    lines = ["targets:\n", "  - /gone/missing\n", "dependencies:\n", "  apm: []\n"]
    out, removed = apm_prune.prune(lines)
    assert removed == []
    assert "  - /gone/missing\n" in out


@pytest.mark.parametrize("value", ["~/nowhere-at-all", "./nope", "../nope"])
def test_relative_and_tilde_paths_count_as_local(value):
    _, removed = apm_prune.prune(_yml(value))
    assert removed == [value]


def test_missing_file_is_not_a_failure(tmp_path):
    assert apm_prune.main(["x", str(tmp_path / "absent.yml")]) == 0


def test_dry_run_writes_nothing(tmp_path):
    f = tmp_path / "apm.yml"
    f.write_text("".join(_yml("/nope")))
    before = f.read_text()
    assert apm_prune.main(["x", str(f), "--dry-run"]) == 0
    assert f.read_text() == before


def test_write_leaves_no_tmp_file_behind(tmp_path):
    # NOT an atomicity check -- writing straight to the path would also pass.
    # Atomicity is unobservable in-process; what is observable is litter.
    f = tmp_path / "apm.yml"
    f.write_text("".join(_yml("/nope")))
    assert apm_prune.main(["x", str(f)]) == 0
    assert "/nope" not in f.read_text()
    assert not (tmp_path / "apm.yml.tmp").exists()


def test_help_exits_zero(capsys):
    assert apm_prune.main(["x", "--help"]) == 0
    assert "Usage:" in capsys.readouterr().out
