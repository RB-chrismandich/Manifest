#!/usr/bin/env python3
"""Reproduce the release-owned policy archive from authoritative sources."""

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path


def archive_bytes(root):
    files = {}
    policy = root / "configs/claude/scripts/manifest_model_policy"
    yaml = root / "plugins/manifest-code-quality/skills/smoke-manage/vendor"
    for path in policy.glob("*.py"):
        files[f"manifest_model_policy/{path.name}"] = path.read_bytes()
    for path in (yaml / "yaml").glob("*.py"):
        files[f"yaml/{path.name}"] = path.read_bytes()
    if not files or "manifest_model_policy/__init__.py" not in files:
        raise ValueError("authoritative policy sources unavailable")
    files["LICENSE.PyYAML"] = (yaml / "LICENSE.PyYAML").read_bytes()
    metadata = "manifest_model_policy-0.1.0.dist-info"
    files[f"{metadata}/METADATA"] = (
        b"Metadata-Version: 2.4\nName: manifest-model-policy\nVersion: 0.1.0\n"
    )
    files[f"{metadata}/RECORD"] = "".join(
        name + ",,\n" for name in sorted(files)
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    path = Path(__file__).resolve()
    content = archive_bytes(path.parents[3])
    target = path.with_name("model-policy.zip")
    if args.check:
        if target.read_bytes() != content:
            print(
                "build-policy: archive differs from authoritative sources",
                file=sys.stderr,
            )
            return 1
    else:
        target.write_bytes(content)
    print(hashlib.sha256(content).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
