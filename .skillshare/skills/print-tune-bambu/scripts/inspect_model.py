#!/usr/bin/env python3
"""Measure the geometry facts that actually drive slicer settings.

Settings advice is only as good as its premises. "It has steep overhangs" or
"it's tall and tippy" are claims about the mesh, and this script turns them into
numbers so the recommendation can cite them instead of guessing from a filename.

Reports, as JSON: bounding box, volume, bed-contact area, overhang area split by
slope band, bridge candidates, tipping aspect ratio, and mesh watertightness.

Usage:
    inspect_model.py MODEL [MODEL ...] [--orient auto] [--pretty]

Supports STL (binary and ASCII), 3MF, and OBJ. Pure standard library; uses numpy
if present purely for speed on large meshes.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

# Slope is measured from the horizontal plane, matching Bambu Studio's
# "Threshold angle": 0 deg is a flat downward face, 90 deg is a vertical wall.
# Bands are chosen around the decisions they inform.
SLOPE_BANDS = [
    (0, 10, "flat_0_10", "bridging / needs support or is a bridge"),
    (10, 30, "shallow_10_30", "unprintable unsupported on most materials"),
    (30, 45, "moderate_30_45", "marginal; supportable by slowing overhang speed"),
    (45, 60, "steep_45_60", "normally fine with cooling"),
    (60, 90, "near_vertical_60_90", "no concern"),
]

BED_TOL = 0.05  # mm; a facet this close to z_min is touching the plate
BRIDGE_MIN_HEIGHT = 0.5  # mm above the plate before a flat-down face counts as a bridge


# ---------------------------------------------------------------------------
# loaders — each returns a flat list of triangles [((x,y,z),(x,y,z),(x,y,z)), ...]


def load_stl(path: Path) -> list:
    data = path.read_bytes()
    # An ASCII STL starts with "solid", but so do some binary files written by
    # sloppy exporters, so confirm against the declared triangle count instead.
    if len(data) >= 84:
        (count,) = struct.unpack("<I", data[80:84])
        if len(data) == 84 + count * 50:
            return _load_stl_binary(data, count)
    if data[:5].lower().startswith(b"solid"):
        return _load_stl_ascii(data.decode("utf-8", "replace"))
    raise ValueError(f"{path.name}: not a recognizable STL")


def _load_stl_binary(data: bytes, count: int) -> list:
    tris = []
    off = 84
    for _ in range(count):
        vals = struct.unpack_from("<12fH", data, off)
        tris.append((vals[3:6], vals[6:9], vals[9:12]))
        off += 50
    return tris


def _load_stl_ascii(text: str) -> list:
    tris, verts = [], []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            verts.append(tuple(float(x) for x in line.split()[1:4]))
            if len(verts) == 3:
                tris.append(tuple(verts))
                verts = []
    return tris


def _safe_xml(data: bytes, label: str) -> bytes:
    """Refuse XML carrying a DTD before handing it to ElementTree.

    3MF files are routinely downloaded from model-sharing sites, so they are
    untrusted input. Entity declarations are the vector for both XXE file reads
    and billion-laughs expansion, and no legitimate 3MF needs a DTD, so the
    cheapest correct defense is to reject them outright rather than parse and hope.
    """
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise ValueError(
            f"{label}: XML declares a DTD/entities; refusing to parse untrusted markup"
        )
    return data


def load_3mf(path: Path) -> list:
    tris = []
    with zipfile.ZipFile(path) as zf:
        models = [n for n in zf.namelist() if n.endswith(".model")]
        if not models:
            raise ValueError(f"{path.name}: no .model part inside the 3MF")
        for name in models:
            root = ET.fromstring(_safe_xml(zf.read(name), f"{path.name}:{name}"))
            ns = {"c": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            # `ns` is bound as a default so each .model part keeps its own
            # namespace; a late-binding closure would apply the last one to all.
            find = (
                (lambda el, tag, _ns=ns: el.findall(f".//c:{tag}", _ns))
                if ns
                else (lambda el, tag, _ns=None: el.findall(f".//{tag}"))
            )
            for mesh in find(root, "mesh"):
                pts = [
                    (float(v.get("x")), float(v.get("y")), float(v.get("z")))
                    for v in find(mesh, "vertex")
                ]
                for t in find(mesh, "triangle"):
                    try:
                        tris.append(
                            (
                                pts[int(t.get("v1"))],
                                pts[int(t.get("v2"))],
                                pts[int(t.get("v3"))],
                            )
                        )
                    except (IndexError, TypeError):
                        continue
    return tris


def load_obj(path: Path) -> list:
    pts, tris = [], []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            pts.append(tuple(float(x) for x in line.split()[1:4]))
        elif line.startswith("f "):
            idx = [int(tok.split("/")[0]) for tok in line.split()[1:]]
            idx = [i - 1 if i > 0 else len(pts) + i for i in idx]
            for k in range(1, len(idx) - 1):  # fan-triangulate n-gons
                tris.append((pts[idx[0]], pts[idx[k]], pts[idx[k + 1]]))
    return tris


LOADERS = {".stl": load_stl, ".3mf": load_3mf, ".obj": load_obj}


# ---------------------------------------------------------------------------
# geometry


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def analyze(tris: list) -> dict:
    if not tris:
        raise ValueError("mesh contains no triangles")

    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    bbox = {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
    }
    dims = [bbox["max"][i] - bbox["min"][i] for i in range(3)]
    z_min = bbox["min"][2]

    total_area = 0.0
    volume6 = 0.0
    bed_area = 0.0
    band_area = defaultdict(float)
    bridge_area = 0.0
    bridge_pts = []
    degenerate = 0
    edges = defaultdict(int)

    for a, b, c in tris:
        n = _cross(_sub(b, a), _sub(c, a))
        mag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if mag < 1e-12:
            degenerate += 1
            continue
        area = mag / 2.0
        total_area += area
        # Signed volume of the tetrahedron to the origin; sums to the enclosed
        # volume for a closed, consistently-wound mesh.
        volume6 += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )

        for p, q in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((_key(p), _key(q))))] += 1

        nz = n[2] / mag
        if nz < 0:  # downward-facing: the only facets that can need support
            slope = math.degrees(math.acos(min(1.0, -nz)))
            for lo, hi, key, _ in SLOPE_BANDS:
                if lo <= slope < hi or (hi == 90 and slope >= 60):
                    band_area[key] += area
                    break
            zc = (a[2] + b[2] + c[2]) / 3.0
            if slope < 10:
                if zc <= z_min + BED_TOL:
                    bed_area += area
                elif zc >= z_min + BRIDGE_MIN_HEIGHT:
                    bridge_area += area
                    bridge_pts.extend([a, b, c])

    volume_mm3 = abs(volume6) / 6.0
    open_edges = sum(1 for count in edges.values() if count != 2)

    # The flat band lumps together three situations with opposite fixes: the face
    # resting on the plate (no action), a bridge anchored at both ends (tune
    # bridge flow/cooling), and a genuinely floating flat face (needs support).
    # Reporting them merged is what makes naive advice recommend supports for a
    # part whose "overhang" is just its own bottom.
    band_area["flat_0_10"] = max(0.0, band_area["flat_0_10"] - bed_area - bridge_area)
    floating_flat = band_area["flat_0_10"]

    downward = sum(band_area.values()) + bed_area + bridge_area
    bands = {}
    for _, _, key, meaning in SLOPE_BANDS:
        bands[key] = {
            "area_mm2": round(band_area[key], 2),
            "pct_of_downward": round(100 * band_area[key] / downward, 1)
            if downward
            else 0.0,
            "meaning": meaning,
        }
    bands["flat_0_10"]["meaning"] = (
        "floating flat face, excludes bed contact and bridges — needs support"
    )

    footprint_min = min(dims[0], dims[1])
    result = {
        "triangles": len(tris),
        "degenerate_triangles": degenerate,
        "watertight": open_edges == 0,
        "open_edges": open_edges,
        "bbox_mm": {k: [round(v, 3) for v in val] for k, val in bbox.items()},
        "dims_mm": {
            "x": round(dims[0], 3),
            "y": round(dims[1], 3),
            "z": round(dims[2], 3),
        },
        "volume_cm3": round(volume_mm3 / 1000.0, 3),
        "surface_area_cm2": round(total_area / 100.0, 2),
        "bed_contact_area_mm2": round(bed_area, 2),
        "overhang_by_slope": bands,
        "support_needed_area_mm2": round(floating_flat + band_area["shallow_10_30"], 2),
        "bridge_area_mm2": round(bridge_area, 2),
        "tipping_aspect_ratio": round(dims[2] / footprint_min, 2)
        if footprint_min > 0.01
        else None,
    }

    if bridge_pts:
        bxs = [p[0] for p in bridge_pts]
        bys = [p[1] for p in bridge_pts]
        result["largest_bridge_extent_mm"] = {
            "x": round(max(bxs) - min(bxs), 2),
            "y": round(max(bys) - min(bys), 2),
        }

    result["flags"] = _flags(result)
    return result


def _key(p):
    # Quantize to 1 micron so float noise from the exporter does not split a
    # shared edge into two, which would fake a non-watertight mesh.
    return (round(p[0], 3), round(p[1], 3), round(p[2], 3))


def _flags(r: dict) -> list[str]:
    out = []
    if not r["watertight"]:
        out.append(
            f"MESH NOT WATERTIGHT ({r['open_edges']} open edges) — slicing may produce "
            "missing walls or phantom infill; repair before tuning settings"
        )
    if r["degenerate_triangles"]:
        out.append(f"{r['degenerate_triangles']} zero-area triangles")
    if r["support_needed_area_mm2"] > 1.0:
        out.append(
            f"{r['support_needed_area_mm2']} mm2 of unsupported faces below 30 deg (bed contact and "
            "bridges already excluded) — supports or a reorientation are in play"
        )
    if r["bridge_area_mm2"] > 1.0:
        ext = r.get("largest_bridge_extent_mm", {})
        span = max(ext.get("x", 0), ext.get("y", 0))
        out.append(f"{r['bridge_area_mm2']} mm2 of bridging, spanning up to ~{span} mm")
    if r["bed_contact_area_mm2"] < 100:
        out.append(
            f"only {r['bed_contact_area_mm2']} mm2 touching the plate — adhesion and warping risk"
        )
    if r["tipping_aspect_ratio"] and r["tipping_aspect_ratio"] > 4:
        out.append(
            f"aspect ratio {r['tipping_aspect_ratio']}:1 — tall and narrow, prone to ringing and knock-over"
        )
    dims = r["dims_mm"]
    if max(dims["x"], dims["y"]) > 325 or dims["z"] > 320:
        out.append("exceeds the H2D 325x320x325 single-nozzle envelope")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("models", nargs="+")
    ap.add_argument(
        "--pretty", action="store_true", help="human-readable summary instead of JSON"
    )
    args = ap.parse_args()

    results = {}
    for m in args.models:
        path = Path(m).expanduser()
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            sys.exit(1)
        loader = LOADERS.get(path.suffix.lower())
        if loader is None:
            print(
                f"error: unsupported format {path.suffix!r} (want .stl/.3mf/.obj)",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            results[str(path)] = analyze(loader(path))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    if not args.pretty:
        print(json.dumps(results, indent=2))
        return

    for name, r in results.items():
        d = r["dims_mm"]
        print(f"\n{name}")
        print(
            f"  {d['x']} x {d['y']} x {d['z']} mm   {r['volume_cm3']} cm3   {r['triangles']} tris"
        )
        print(
            f"  bed contact {r['bed_contact_area_mm2']} mm2   aspect {r['tipping_aspect_ratio']}:1"
        )
        shown = [
            (k, b) for k, b in r["overhang_by_slope"].items() if b["area_mm2"] > 0.01
        ]
        if shown:
            print("  downward faces by slope from horizontal:")
            for key, band in shown:
                print(
                    f"    {key:<20} {band['area_mm2']:>9} mm2  ({band['pct_of_downward']}%)  {band['meaning']}"
                )
        else:
            print(
                "  downward faces: all bed contact — nothing overhanging in this orientation"
            )
        for f in r["flags"] or ["no geometry concerns detected"]:
            print(f"  ! {f}")


if __name__ == "__main__":
    main()
