"""Direct coverage for tools/check_runtime_source_directives.py.

The scanner ships wired into ``check_bundle_link_references.scan()`` (and so
into CI), but wiring is not coverage: neutering ``scan_bundle`` to ``return []``
leaves the entire 59-test bundle-link suite green, because every one of those
tests asserts *absence* of findings and a no-op scanner satisfies that
vacuously. The tests below are therefore built to fail on that mutant -- each
asserts a finding is *produced*, not merely that none is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT_DIR_HEADER = 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'


def _scanner():
    """Load the scanner as a fresh module instance (harness convention)."""
    spec = importlib.util.spec_from_file_location(
        "check_runtime_source_directives",
        _REPO_ROOT / "tools/check_runtime_source_directives.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bundle(
    tmp_path: Path, script_body: str, *, siblings: tuple[str, ...] = ()
) -> Path:
    """Write a bundle with runtime/bin/entry.sh plus any sibling targets."""
    bin_dir = tmp_path / "plugins" / "demo-bundle" / "runtime" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "entry.sh").write_text(
        _SCRIPT_DIR_HEADER + script_body, encoding="utf-8"
    )
    for rel in siblings:
        target = bin_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# stub\n", encoding="utf-8")
    return bin_dir.parents[1]


# --- defects: must be flagged (these fail under a no-op scan_bundle) --------


def test_flags_script_dir_source_whose_target_is_absent(tmp_path: Path) -> None:
    findings = _scanner().scan_bundle(
        _bundle(tmp_path, 'source "${SCRIPT_DIR}/lib/helper.sh"\n')
    )

    assert len(findings) == 1
    _, line, kind, value, message = findings[0]
    assert (line, kind) == (2, "missing-source-target")
    assert value == 'source "${SCRIPT_DIR}/lib/helper.sh"'
    assert "lib/helper.sh" in message


def test_flags_forge_runtime_dir_source_whose_target_is_absent(tmp_path: Path) -> None:
    findings = _scanner().scan_bundle(
        _bundle(tmp_path, 'source "$FORGE_RUNTIME_DIR/bin/lib/absent.sh"\n')
    )

    assert [f[2] for f in findings] == ["missing-source-target"]


def test_flags_dot_directive_the_same_as_source(tmp_path: Path) -> None:
    findings = _scanner().scan_bundle(
        _bundle(tmp_path, '. "${SCRIPT_DIR}/lib/absent.sh"\n')
    )

    assert [f[2] for f in findings] == ["missing-source-target"]


def test_flags_a_real_dependency_when_its_target_is_removed(tmp_path: Path) -> None:
    """End-to-end on real content: manifest-forge's own runtime/bin tree, with
    the one file pr_merge_loop.sh sources deleted. Guards the exact dependency
    class the scanner was written for (no SKILL.md ever mentions it)."""
    import shutil

    src = _REPO_ROOT / "plugins/manifest-forge/runtime"
    bundle = tmp_path / "plugins" / "manifest-forge"
    shutil.copytree(src, bundle / "runtime")
    sourced = bundle / "runtime/bin/lib/pr_merge_loop_gh.sh"
    assert sourced.is_file(), "fixture premise: the real dependency exists"
    sourced.unlink()

    findings = _scanner().scan_bundle(bundle)

    assert [(f[0].name, f[2]) for f in findings] == [
        ("pr_merge_loop.sh", "missing-source-target")
    ]


# --- non-defects: must NOT be flagged --------------------------------------


def test_does_not_flag_source_whose_target_resolves(tmp_path: Path) -> None:
    findings = _scanner().scan_bundle(
        _bundle(
            tmp_path,
            'source "${SCRIPT_DIR}/lib/helper.sh"\n',
            siblings=("lib/helper.sh",),
        )
    )

    assert findings == []


def test_leaves_unrecognised_source_forms_unresolved(tmp_path: Path) -> None:
    """A literal or differently-anchored target is not guessed at -- the
    scanner's stated philosophy, and the reason it never false-positives on
    ``source /etc/profile``-style lines."""
    findings = _scanner().scan_bundle(
        _bundle(
            tmp_path, 'source "$SOME_OTHER_VAR/lib/absent.sh"\nsource /etc/absent.sh\n'
        )
    )

    assert findings == []


# --- corpus guard ----------------------------------------------------------


def test_every_real_source_directive_in_the_repo_still_resolves() -> None:
    """The live invariant CI enforces. Paired with the positive tests above so
    a silently-disabled scanner cannot make this pass vacuously."""
    scanner = _scanner()

    assert scanner.scan(_REPO_ROOT) == []
