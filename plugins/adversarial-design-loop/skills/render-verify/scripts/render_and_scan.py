#!/usr/bin/env python3
"""Faithful render + pixel-forensic ink scan for design-loop screens.

Renders an exported HTML screen with Playwright — hard-failing if declared
webfont weights did not load or the screen container is not the declared
frame size — then scans the captured PNG per distinct ink color: pixel
count, maximum radial reach from center, and maximum x/y extent, optionally
enforcing a radial clearance limit (round displays).

The generator's own thumbnails are never authoritative; this capture is.
Dependencies: playwright (with Chromium installed), Pillow.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_SELECTORS = ".device-display,.screen-container,.hardware-bezel,#screen,.screen"


def _add_render_flags(p: argparse.ArgumentParser) -> None:
    add = p.add_argument
    add("--frame", default="360x360", help="expected WxH of the container")
    add("--scale", type=int, default=2, help="device scale factor (default: 2)")
    add("--font-family", default=None, help="webfont family that must load")
    add("--font-weights", default="400,700", help="weights to assert (comma-sep)")
    add(
        "--selectors", default=DEFAULT_SELECTORS, help="container selectors, first wins"
    )
    add("--settle-ms", type=int, default=1500, help="settle time before assertions")


def _add_scan_flags(p: argparse.ArgumentParser) -> None:
    add = p.add_argument
    add("--bg", default=None, help="background hex to skip (default: pixel 1,1)")
    add("--bg-delta", type=int, default=12, help="channel-sum delta counted as bg")
    add("--min-pixels", type=int, default=40, help="drop inks below this pixel count")
    add(
        "--radius-limit",
        type=float,
        default=None,
        help="fail (exit 1) if any ink's r_max exceeds this, in frame px",
    )
    add("--scan-only", action="store_true", help="skip rendering; scan existing PNG")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="render_and_scan.py",
        description="Render an HTML screen faithfully, then scan inks per color.",
    )
    p.add_argument("in_html", type=Path, help="exported screen HTML")
    p.add_argument("out_png", type=Path, help="capture destination PNG")
    _add_render_flags(p)
    _add_scan_flags(p)
    return p.parse_args(argv)


def fonts_ready_js(family: str, weights: list[str]) -> str:
    charset = "0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ:-/%°"
    loads = ",\n    ".join(
        f'document.fonts.load("{w} 20px \'{family}\'", "{charset}")' for w in weights
    )
    checks = ",\n    ".join(
        f'"{w}": document.fonts.check("{w} 20px \'{family}\'")' for w in weights
    )
    return (
        "async () => {\n"
        "  await Promise.all([\n    " + loads + "\n  ]);\n"
        "  await document.fonts.ready;\n"
        "  return {\n    " + checks + "\n  };\n"
        "}"
    )


def frame_size(spec: str) -> tuple[int, int]:
    w, h = spec.lower().split("x")
    return int(w), int(h)


def render(args: argparse.Namespace) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "render_and_scan.py: playwright not installed "
            "(pip install playwright && playwright install chromium)"
        )

    frame_w, frame_h = frame_size(args.frame)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": frame_w + 80, "height": frame_h + 80},
            device_scale_factor=args.scale,
        )
        page.goto(args.in_html.resolve().as_uri())
        page.wait_for_timeout(args.settle_ms)
        if args.font_family:
            weights = [w.strip() for w in args.font_weights.split(",") if w.strip()]
            checks = page.evaluate(fonts_ready_js(args.font_family, weights))
            missing = [w for w, ok in checks.items() if not ok]
            if missing:
                sys.exit(
                    f"FAIL: font '{args.font_family}' weight(s) not loaded: "
                    f"{', '.join(missing)}"
                )
        element = None
        for sel in args.selectors.split(","):
            element = page.query_selector(sel.strip())
            if element:
                break
        if element is None:
            sys.exit(f"FAIL: no container matched selectors: {args.selectors}")
        box = element.bounding_box()
        got = (round(box["width"]), round(box["height"]))
        if got != (frame_w, frame_h):
            sys.exit(
                f"FAIL: container is {got[0]}x{got[1]}, expected {frame_w}x{frame_h}"
            )
        element.screenshot(path=str(args.out_png))
        browser.close()


def scan(args: argparse.Namespace) -> int:
    try:
        from PIL import Image
    except ImportError:
        sys.exit("render_and_scan.py: Pillow not installed (pip install Pillow)")

    frame_w, _ = frame_size(args.frame)
    img = Image.open(args.out_png).convert("RGB")
    scale = img.width / frame_w
    cx, cy = img.width / 2, img.height / 2
    if args.bg:
        raw = args.bg.lstrip("#")
        bg = tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
    else:
        bg = img.getpixel((1, 1))

    # per ink: [pixel count, max radius, max |x|, max |y|] in frame px
    stats: dict[tuple[int, int, int], list[float]] = defaultdict(
        lambda: [0, 0.0, 0.0, 0.0]
    )
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            color = pixels[x, y]
            if (
                sum(abs(a - b) for a, b in zip(color, bg, strict=False))
                <= args.bg_delta
            ):
                continue
            r = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / scale
            s = stats[color]
            s[0] += 1
            s[1] = max(s[1], r)
            s[2] = max(s[2], abs(x - cx) / scale)
            s[3] = max(s[3], abs(y - cy) / scale)

    rows = [(c, s) for c, s in stats.items() if s[0] >= args.min_pixels]
    rows.sort(key=lambda item: -item[1][0])
    print(f"{'hex':>8} {'n':>8} {'r_max':>7} {'x_max':>7} {'y_max':>7}")
    failed = False
    for color, (n, r_max, x_max, y_max) in rows[:20]:
        hex_color = "#{:02X}{:02X}{:02X}".format(*color)
        flag = ""
        if args.radius_limit is not None and r_max > args.radius_limit:
            flag = "  EXCEEDS LIMIT"
            failed = True
        print(
            f"{hex_color:>8} {int(n):>8} {r_max:7.1f} {x_max:7.1f} {y_max:7.1f}{flag}"
        )
    if failed:
        print(f"FAIL: ink(s) exceed radius limit {args.radius_limit}")
        return 1
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.scan_only:
        render(args)
    return scan(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
