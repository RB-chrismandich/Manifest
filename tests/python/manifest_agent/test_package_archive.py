from __future__ import annotations

from pathlib import Path

from tools.project_checks.package_archive import (
    BLOCKED,
    FAIL,
    PASS,
    REQUIRED,
    validate_archive,
)


def test_package_archive_round_trips_required_roots(tmp_path: Path) -> None:
    for name in REQUIRED:
        path = tmp_path / name
        if name == "bootstrap.sh":
            path.write_text(
                "#!/usr/bin/env bash\n"
                'test -f "$(dirname "$0")/bootstrap/payload.txt"\n',
                encoding="utf-8",
            )
        elif "." in Path(name).name:
            path.write_text("content\n", encoding="utf-8")
        else:
            path.mkdir()
            (path / "payload.txt").write_text("content\n", encoding="utf-8")
    status, diagnostic = validate_archive(tmp_path)

    assert status == PASS
    assert diagnostic == ""
    assert not list(tmp_path.glob("*.tar.gz"))
    (tmp_path / "bootstrap.sh").write_text(
        "#!/usr/bin/env bash\nexit 1\n", encoding="utf-8"
    )
    status, diagnostic = validate_archive(tmp_path)
    assert status == FAIL
    assert "packaged bootstrap --help failed" in diagnostic


def test_package_archive_blocks_when_required_input_is_missing(tmp_path: Path) -> None:
    status, diagnostic = validate_archive(tmp_path)

    assert status == BLOCKED
    assert "required package inputs unavailable" in diagnostic
