"""Unit tests for the adversarial-design-loop render gate's pure helpers.

The Playwright render path needs a browser and is exercised by the plugin's
own projects; these tests cover the argument surface, the fonts-ready JS
builder, and the ink scan on a synthetic PNG.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "stitch-design"
    / "skills"
    / "render-verify"
    / "scripts"
    / "render_and_scan.py"
)


@pytest.fixture(scope="module")
def ras():
    spec = importlib.util.spec_from_file_location("render_and_scan", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frame_size_parses_and_is_case_insensitive(ras):
    assert ras.frame_size("360x360") == (360, 360)
    assert ras.frame_size("1280X720") == (1280, 720)


def test_fonts_ready_js_covers_every_weight(ras):
    js = ras.fonts_ready_js("Space Grotesk", ["400", "700"])
    for weight in ("400", "700"):
        assert f"document.fonts.load(\"{weight} 20px 'Space Grotesk'\"" in js
        assert f'"{weight}": document.fonts.check(' in js
    assert "document.fonts.ready" in js


def test_parse_args_defaults(ras):
    args = ras.parse_args(["in.html", "out.png"])
    assert (args.frame, args.scale) == ("360x360", 2)
    assert args.font_weights == "400,700"
    assert args.radius_limit is None
    assert not args.scan_only


def test_scan_reports_ink_and_enforces_radius_limit(ras, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    img = Image.new("RGB", (40, 40), (0, 0, 0))
    for x in range(30, 38):
        for y in range(30, 38):
            img.putpixel((x, y), (255, 255, 255))
    png = tmp_path / "screen.png"
    img.save(png)

    base = [
        "in.html",
        str(png),
        "--scan-only",
        "--frame",
        "40x40",
        "--min-pixels",
        "10",
    ]
    assert ras.scan(ras.parse_args(base)) == 0
    # the white block reaches ~r=24.7 from center; a tighter limit must fail
    assert ras.scan(ras.parse_args([*base, "--radius-limit", "20"])) == 1
    assert ras.scan(ras.parse_args([*base, "--radius-limit", "30"])) == 0
