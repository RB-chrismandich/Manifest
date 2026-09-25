"""Regression tests for the shipped stitch-design post-process runtime.

F-7: ``resolveLocalFile`` in ``post_process.ts`` used to try the raw
``localPath`` first, so an HTML file could pull in filesystem-absolute paths
(``/etc/hosts``), ``..`` escapes, and symlinks pointing outside ``--base-dir``.
The shipped ``runtime/dist/post-process.mjs`` must now inline only regular
files inside the base dir.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_DIST = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "stitch-design"
    / "runtime"
    / "dist"
    / "post-process.mjs"
)

_SECRET = b"SECRET-BYTES"

# Valid 1x1 PNG.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_post_process_inlines_only_files_inside_base_dir(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node executable is unavailable; cannot run post-process.mjs")

    app = tmp_path / "app"
    app.mkdir()
    (app / "logo.png").write_bytes(_PNG_1X1)
    (tmp_path / "secret.png").write_bytes(_SECRET)
    (app / "link.png").symlink_to("../secret.png")
    page = app / "page.html"
    page.write_text(
        '<img src="logo.png">'
        '<img src="../secret.png">'
        '<img src="/etc/hosts">'
        '<img src="link.png">',
        encoding="utf-8",
    )

    result = subprocess.run(
        [node, str(_DIST), "app/page.html", "--base-dir", "app", "--json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    html = page.read_text(encoding="utf-8")

    # The file inside the base dir is inlined.
    assert "data:image/png;base64," in html

    # Nothing outside the base dir leaks into the output.
    assert base64.b64encode(_SECRET).decode() not in html

    # The three rejected references are left unchanged.
    assert 'src="../secret.png"' in html
    assert 'src="/etc/hosts"' in html
    assert 'src="link.png"' in html

    # The escape attempts are refused explicitly; the non-image path is
    # rejected silently by the extension gate.
    assert result.stderr.count("Refusing") == 2

    stats = json.loads(result.stdout.split("--- JSON Stats ---", 1)[1])
    assert stats["totalSrcInlined"] == 1
    assert stats["totalSkippedNotFound"] == 3
